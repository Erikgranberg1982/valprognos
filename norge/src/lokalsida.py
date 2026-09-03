"""Sidor för fylkestings- och kommunestyrevalget 2027.

Tre sidtyper:

  /lokalvalg/                      översikt, riksnivå och alla fylken
  /lokalvalg/fylke/<slug>/         en sida per fylke, 14 stycken
  /lokalvalg/kommune/<slug>/       en sida per kommun, 357 stycken

Kommunsidorna är många men billiga: samma mall, och söken efter dem är
konkret ("Bergen kommunestyrevalg", "valgresultat Tromsø"). En kommun är
dessutom det område folk har starkast relation till.

Osäkerheten redovisas på varje sida, eftersom den är väsentligt större än i
stortingsprognosen och läsaren annars kan tro annat.
"""
from __future__ import annotations

import html as html_mod
import re
import unicodedata
from datetime import date
from pathlib import Path

import config as cfg
import lokala_koalitioner as lk
import lokalmodell
import norsk_dashboard as nd
import seo

ROT = Path(__file__).resolve().parent.parent

VALDAG = lokalmodell.VALDAG_2027
LOKALT = lokalmodell.LOKALT

# Partiordning på lokalsidorna: samma politiska ordning som riksprognosen,
# med lokala listor sist eftersom de inte hör på skalan.
ORDNING = nd.ORDNING + [LOKALT]

LOKALT_NAMN = "Lokale lister og andre"


def slug(namn: str) -> str:
    """Gör ett områdesnamn till en URL-del.

    Norska tecken translittereras hellre än tas bort: "Trøndelag" ska bli
    "trondelag", inte "trndelag". Fylkessuffix behålls som del av slugen,
    eftersom det särskiljer likanamnade kommuner.
    """
    text = lokalmodell.ssb.normalisera(namn).lower()
    for fran, till in (("æ", "ae"), ("ø", "o"), ("å", "a"), ("ö", "o"),
                       ("ä", "a"), ("ü", "u")):
        text = text.replace(fran, till)
    # Övriga diakriter tas bort via normalisering, t.ex. á -> a.
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _langt_datum() -> str:
    d = date.fromisoformat(VALDAG)
    return f"{d.day}. {nd.MANADER_NO[d.month - 1]} {d.year}"


def _partinamn(parti: str) -> str:
    return LOKALT_NAMN if parti == LOKALT else cfg.PARTINAMN.get(parti, parti)


def _kortnamn(parti: str) -> str:
    return "Lokale" if parti == LOKALT else seo.KORTNAMN.get(parti, parti)


def _farg(parti: str) -> str:
    # Lokala listor har ingen partifärg. Grått markerar att de inte ligger på
    # höger-vänsterskalan och inte prognosticeras.
    return "#8496a4" if parti == LOKALT else cfg.PARTIFARG[parti]


def _tabellrader(data: dict) -> str:
    andelar = data["andelar"]
    mandat = data["mandat"]
    forra = data["forra_andelar"]
    rader = []
    for parti in ORDNING:
        if parti not in andelar:
            continue
        andel = andelar[parti]
        tidigare = forra.get(parti)
        forandring = (andel - tidigare) if tidigare is not None else None
        konstant = (' <span class="konstant" title="Lokale lister holdes '
                    'konstante, se metoden nederst">fast</span>'
                    if parti == LOKALT else "")
        rader.append(f"""      <tr>
        <td class="parti"><span class="prick" style="background:{_farg(parti)}"></span>
            <strong>{_kortnamn(parti)}</strong>
            <span class="partinamn">{html_mod.escape(_partinamn(parti))}</span>{konstant}</td>
        <td class="tal"><strong>{nd._tal(andel)}&nbsp;%</strong></td>
        <td class="tal">{nd._diff(forandring)}</td>
        <td class="tal"><strong>{mandat.get(parti, 0)}</strong></td>
        <td class="tal">{nd._tal(tidigare) if tidigare is not None else '&ndash;'}&nbsp;%</td>
      </tr>""")
    return "\n".join(rader)


def _stapelgraf(data: dict, bredd: int = 860) -> str:
    """Vågrät stapelgraf över andelarna. Enklare att läsa än en tidsserie.

    Ingen tidsserie finns per område: underlaget är två valresultat, inte en
    mätserie. Att rita en linje mellan två punkter skulle antyda mer
    information än vi har.
    """
    andelar = data["andelar"]
    poster = [(p, andelar[p]) for p in ORDNING if p in andelar and andelar[p] > 0.05]
    if not poster:
        return ""
    hogst = max(v for _, v in poster)
    radhojd, marg = 30, 74
    hojd = len(poster) * radhojd + 12
    skala = (bredd - marg - 60) / max(hogst, 1.0)

    delar = [f'<svg viewBox="0 0 {bredd} {hojd}" class="staplar" role="img" '
             f'aria-label="Oppslutning per parti">']
    for i, (parti, varde) in enumerate(poster):
        y = i * radhojd + 6
        langd = max(2.0, varde * skala)
        delar.append(f'<text x="{marg - 8}" y="{y + 15}" class="staplenamn" '
                     f'text-anchor="end">{_kortnamn(parti)}</text>')
        delar.append(f'<rect x="{marg}" y="{y}" width="{langd:.1f}" '
                     f'height="20" rx="3" fill="{_farg(parti)}"/>')
        delar.append(f'<text x="{marg + langd + 7:.1f}" y="{y + 15}" '
                     f'class="staplevarde">{nd._tal(varde)} %</text>')
    delar.append("</svg>")
    return "".join(delar)


def _styre(data: dict) -> tuple[str, str]:
    """Mandatläget i korthet, för nyckeltalskortet och översiktstabellen."""
    s = lk.sammanfatta(data["mandat"], data["platser"])
    return s["lage"], s["forklaring"]


def _styreavsnitt(data: dict) -> str:
    """Avsnittet om möjliga styren.

    Redovisar vilka konstellationer som når egen majoritet. Modulen avgör
    inte vad som är politiskt troligt: lokala styren beror på personer och
    sakfrågor som ingen modell ser. Det står också i texten.
    """
    s = lk.sammanfatta(data["mandat"], data["platser"])
    if not s["styren"]:
        innehall = ('<p class="ledtext">Ingen av de vanlige '
                    'konstellasjonene får flertall i prognosen. Da må styret '
                    'bygges på en løsning som er spesifikk for dette '
                    'området.</p>')
    else:
        rader = []
        for st in s["styren"]:
            partier = "".join(
                f'<span class="prick" style="background:{_farg(p)}" '
                f'title="{html_mod.escape(_partinamn(p))}"></span>'
                for p in st["partier"])
            marginal = ("på vippen" if st["marginal"] == 0
                        else f"{st['marginal']} over")
            rader.append(f"""      <tr>
        <td><strong>{html_mod.escape(st['namn'])}</strong>
            <div class="beskrivning">{html_mod.escape(st['beskrivning'])}</div></td>
        <td class="partiprickar">{partier}</td>
        <td class="tal"><strong>{st['mandat']}</strong></td>
        <td class="tal spann">{marginal}</td>
      </tr>""")
        innehall = f"""  <div class="tabellhölje">
    <table>
      <thead><tr><th>Konstellasjon</th><th>Partier</th>
        <th class="tal">Mandater</th><th class="tal">Margin</th></tr></thead>
      <tbody>
{chr(10).join(rader)}
      </tbody>
    </table>
  </div>"""

    return f"""
<section>
  <h2>Mulige styrer</h2>
  <p class="ledtext">{html_mod.escape(s['forklaring'])} Det trengs
    {s['behovs']} av {data['platser']} mandater for flertall.</p>
{innehall}
  <p class="ledtext" style="margin-top:16px">Tabellen viser hvilke
    konstellasjoner som får flertall i prognosen, ikke hva som er politisk
    sannsynlig. Lokale styrer avgjøres av personer og enkeltsaker som ingen
    modell fanger, og samarbeid over blokkgrensen er vanlig: Senterpartiet
    styrer med Høyre og Frp i Bergen, og lokale lister sitter i posisjon i et
    stort antall kommuner.</p>
</section>"""


def _metodavsnitt() -> str:
    return f"""
<section>
  <h2>Slik er prognosen laget</h2>
  <p class="ledtext">Utgangspunktet er områdets eget resultat i lokalvalget
    2023. Hvert partis nivå skaleres med hvor mye partiet har endret seg i
    riksopinionen siden den gang.</p>
  <p class="ledtext"><strong>Endringen dempes.</strong> Lokalvalg følger ikke
    riksopinionen fullt ut: velgerne stemmer på lokale kandidater og lokale
    saker, og et parti som dobler seg nasjonalt dobler seg ikke i kommunene.
    Målt på lokalvalgene 2019 til 2023 slår omtrent to tredeler av
    opinionsbevegelsen gjennom lokalt, og prognosen bruker det. Uten dempingen
    ville Fremskrittspartiet, som har gått fra 13,9 til 31,0 prosent i
    riksopinionen siden 2023, havnet på nivåer partiet aldri har vært i
    nærheten av i et lokalvalg.</p>
  <p class="ledtext"><strong>Lokale lister holdes konstante</strong> på nivået
    fra 2023. De kan ikke prognostiseres: det finnes ingen målinger per
    kommune, og en lokal liste avhenger av personer og enkeltsaker som ikke
    vises i riksopinionen. I kommunevalget 2023 fikk lokale lister til sammen
    9,5 prosent av stemmene.</p>
  <p class="ledtext">Mandatene fordeles med St.&nbsp;Laguës modifiserte metode
    og første delingstall 1,4, som ved stortingsvalg. Men her finnes
    <strong>ingen sperregrense og ingen utjevningsmandater</strong>: hvert
    område fordeler sine egne mandater. Den reelle terskelen følger av hvor
    mange plasser forsamlingen har.</p>
  <p class="ledtext"><strong>Usikkerheten er betydelig større enn i
    stortingsprognosen.</strong> Tre grunner: det finnes ingen målinger per
    kommune eller fylke, riksopinionen måler stortingsvalg og ikke lokalvalg,
    og lokale lister holdes konstante. Et backtest der resultatet fra 2019 ble
    skalert fram til 2023 traff med 1,5 prosentpoeng i snitt per parti på
    fylkesnivå og 3,3 på kommunenivå. Til sammenligning gir stortingsprognosen
    0,7 prosentpoeng en uke før valget.</p>
  <p class="ledtext">Tallene beskriver altså retningen, ikke det presise
    utfallet. Særlig på kommunenivå kan lokale forhold flytte store
    velgergrupper uten at noe av det vises i riksopinionen.</p>
</section>"""


def _sidhuvud(titel: str, beskrivning: str, url: str, brodsmulor: list,
              extra_stil: str = "", rot: str = "../") -> str:
    return f"""<!doctype html>
<html lang="no">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html_mod.escape(titel)} · Lysio Research</title>
{seo.metataggar(titel, beskrivning, url)}
{seo.strukturerad_data_brodsmulor(brodsmulor)}
{cfg.google_analytics()}
<style>
{nd.STIL}
  .staplar {{ width: 100%; height: auto; display: block; }}
  .staplenamn {{ fill: var(--text); font-size: 12px; font-weight: 620; }}
  .staplevarde {{ fill: var(--svag); font-size: 12px; }}
  .konstant {{ font-size: .72rem; background: var(--ljusbla);
               color: var(--svag); padding: 1px 6px; border-radius: 4px;
               margin-left: 5px; }}
  .brodsmula {{ font-size: .87rem; color: var(--svag); padding-top: 26px; }}
  .brodsmula a {{ color: var(--morkbla); }}
  .omradelank {{ display: inline-block; border: 1px solid var(--linje);
                 border-radius: 8px; padding: 5px 11px; margin: 0 5px 7px 0;
                 text-decoration: none; color: var(--text); font-size: .88rem; }}
  .omradelank:hover {{ background: var(--ljusbla); }}
  .partiprickar {{ white-space: nowrap; }}
  .partiprickar .prick {{ margin-right: 3px; }}
  .sokruta {{ width: 100%; max-width: 380px; padding: 9px 13px;
              border: 1px solid var(--linje); border-radius: 9px;
              font-size: .95rem; margin-bottom: 14px; }}
{extra_stil}
</style>
</head>
<body>
{nd.toppmeny("lokalvalg", rot)}
<div class="omslag">
"""


def _sidfot() -> str:
    return """
<footer>
  <p>Bygget av Lysio Research. Valgresultater fra
    <a href="https://www.ssb.no/">SSB</a>, tabell 01180
    (kommunestyrevalget), 01181 (fylkestingsvalget) og 04813
    (kommunestyrestørrelser). Riksopinionen bygger på Wikipedias
    sammenstilling av norske meningsmålinger.</p>
  <p>En prognose er ikke en spådom, og på lokalt nivå er usikkerheten stor.
    Se metoden over.</p>
</footer>

</div>
</body>
</html>
"""


def bygg_omrade(namn: str, data: dict, niva: str) -> str:
    """Bygger sidan för ett fylke eller en kommun."""
    rent = lokalmodell.ssb.normalisera(namn)
    nivanamn = "fylkestingsvalget" if niva == "fylke" else "kommunestyrevalget"
    forsamling = "fylkestinget" if niva == "fylke" else "kommunestyret"

    storst = max((p for p in data["andelar"]), key=lambda p: data["andelar"][p])
    andel = data["andelar"][storst]
    rubrik, styretext = _styre(data)

    titel = f"{rent} {nivanamn} 2027"
    if len(titel) > seo.TITEL_MAX:
        titel = f"{rent} {'fylkesting' if niva == 'fylke' else 'kommunevalg'} 2027"
    beskrivning = (
        f"{_kortnamn(storst)} størst med {nd._tal(andel)} % i prognosen for "
        f"{nivanamn} 2027 i {rent}. {data['platser']} mandater i "
        f"{forsamling}, fordelt etter riksopinionen og resultatet i 2023.")

    url = f"{seo.BAS_URL}/lokalvalg/{niva}/{slug(namn)}/"
    brodsmulor = [("Valgprognose", f"{seo.BAS_URL}/"),
                  ("Lokalvalget 2027", f"{seo.BAS_URL}/lokalvalg/"),
                  (rent, url)]

    return (_sidhuvud(titel, beskrivning, url, brodsmulor,
                      rot="../../../") + f"""
<nav class="brodsmula"><a href="../../../">Valgprognose</a> &rsaquo;
  <a href="../../">Lokalvalget 2027</a> &rsaquo; {html_mod.escape(rent)}</nav>

<header>
  <h1>{html_mod.escape(rent)}</h1>
  <p class="underrubrik">Prognose for {nivanamn} {_langt_datum()}</p>
</header>

<div class="nyckeltal">
  <div class="kort">
    <div class="etikett">Størst parti</div>
    <div class="varde" style="color:{_farg(storst)}">{_kortnamn(storst)} {nd._tal(andel)}&nbsp;%</div>
    <div class="not">{html_mod.escape(_partinamn(storst))}</div>
  </div>
  <div class="kort">
    <div class="etikett">Mandater</div>
    <div class="varde">{data['platser']}</div>
    <div class="not">i {forsamling}</div>
  </div>
  <div class="kort">
    <div class="etikett">Styre</div>
    <div class="varde">{rubrik}</div>
    <div class="not">{html_mod.escape(styretext)}</div>
  </div>
  <div class="kort">
    <div class="etikett">Lokale lister</div>
    <div class="varde">{nd._tal(data['andelar'].get(LOKALT, 0.0))}&nbsp;%</div>
    <div class="not">{data['mandat'].get(LOKALT, 0)} mandater, holdt konstant
      fra 2023</div>
  </div>
</div>

<section>
  <h2>Oppslutning</h2>
  {_stapelgraf(data)}
</section>

<section>
  <h2>Prognose per parti</h2>
  <div class="tabellhölje">
    <table>
      <thead><tr><th>Parti</th><th class="tal">Prognose</th>
        <th class="tal">Mot 2023</th><th class="tal">Mandater</th>
        <th class="tal">2023</th></tr></thead>
      <tbody>
{_tabellrader(data)}
      </tbody>
    </table>
  </div>
</section>
{_styreavsnitt(data)}
{_metodavsnitt()}
""" + _sidfot())


def bygg_oversikt(fylken: dict, kommuner: dict, riksprognos: dict) -> str:
    """Översiktssidan för lokalvalet."""
    trend = lokalmodell.rikstrend(riksprognos)
    url = f"{seo.BAS_URL}/lokalvalg/"

    fylkesrader = []
    for namn in sorted(fylken):
        d = fylken[namn]
        storst = max(d["andelar"], key=lambda p: d["andelar"][p])
        rubrik, _ = _styre(d)
        fylkesrader.append(f"""      <tr>
        <td><a href="fylke/{slug(namn)}/">{html_mod.escape(namn)}</a></td>
        <td class="parti"><span class="prick" style="background:{_farg(storst)}"></span>
            {_kortnamn(storst)} {nd._tal(d['andelar'][storst])}&nbsp;%</td>
        <td class="tal">{d['platser']}</td>
        <td>{rubrik}</td>
        <td class="tal">{nd._tal(d['andelar'].get(LOKALT, 0.0))}&nbsp;%</td>
      </tr>""")

    # Kommunerna är för många för en tabell. De listas som länkar med ett
    # sökfält, vilket är snabbare att använda än 357 rader.
    kommunlankar = "".join(
        f'<a class="omradelank" href="kommune/{slug(n)}/">'
        f'{html_mod.escape(lokalmodell.ssb.normalisera(n))}</a>'
        for n in sorted(kommuner, key=lokalmodell.ssb.normalisera))

    # Riksnivå för lokalvalet: summera mandaten över alla kommuner.
    riksmandat: dict[str, int] = {}
    for d in kommuner.values():
        for parti, m in d["mandat"].items():
            riksmandat[parti] = riksmandat.get(parti, 0) + m
    totalt_mandat = sum(riksmandat.values())
    riksrader = "".join(
        f"""      <tr>
        <td class="parti"><span class="prick" style="background:{_farg(p)}"></span>
            <strong>{_kortnamn(p)}</strong></td>
        <td class="tal">{riksmandat.get(p, 0)}</td>
        <td class="tal">{nd._tal(riksmandat.get(p, 0) / totalt_mandat * 100)}&nbsp;%</td>
        <td class="tal">{nd._tal(trend.get(p, 1.0), 2) if p != LOKALT else 'fast'}</td>
      </tr>""" for p in ORDNING if p in riksmandat)

    # Fördelningen av styrelägen, för översiktstabellen.
    lagen = ["Rødgrønt flertall", "Borgerlig flertall",
             "Lokale lister i flertall", "Vippeposisjon"]
    rakning = {l: {"kommun": 0, "fylke": 0} for l in lagen}
    for niva, omraden in (("kommun", kommuner), ("fylke", fylken)):
        for d in omraden.values():
            lage = lk.sammanfatta(d["mandat"], d["platser"])["lage"]
            if lage in rakning:
                rakning[lage][niva] += 1
    styrerader = "".join(
        f"""      <tr>
        <td>{l}</td>
        <td class="tal"><strong>{rakning[l]['kommun']}</strong></td>
        <td class="tal">{nd._tal(rakning[l]['kommun'] / max(len(kommuner), 1) * 100)}&nbsp;%</td>
        <td class="tal">{rakning[l]['fylke']}</td>
      </tr>""" for l in lagen)

    titel = "Prognose lokalvalget 2027"
    beskrivning = (
        f"Prognose for fylkestings- og kommunestyrevalget 13. september 2027. "
        f"{len(fylken)} fylker og {len(kommuner)} kommuner, basert på "
        f"resultatet i 2023 skalert med riksopinionen.")

    return (_sidhuvud(titel, beskrivning, url,
                      [("Valgprognose", f"{seo.BAS_URL}/"),
                       ("Lokalvalget 2027", url)]) + f"""
<nav class="brodsmula"><a href="../">Valgprognose stortingsvalget</a>
  &rsaquo; Lokalvalget 2027</nav>

<header>
  <h1>Lokalvalget 2027</h1>
  <p class="underrubrik">Fylkestings- og kommunestyrevalg
    {_langt_datum()} &middot; {len(fylken)} fylker og
    {len(kommuner)} kommuner</p>
</header>

<section>
  <h2>Fylkestingene</h2>
  <p class="ledtext">Oslo har ikke fylkesting: kommunestyret fyller den
    rollen, så Oslo finnes bare blant kommunene.</p>
  <div class="tabellhölje">
    <table>
      <thead><tr><th>Fylke</th><th>Størst parti</th>
        <th class="tal">Mandater</th><th>Styre</th>
        <th class="tal">Lokale</th></tr></thead>
      <tbody>
{chr(10).join(fylkesrader)}
      </tbody>
    </table>
  </div>
</section>

<section>
  <h2>Mandater i alle kommunestyrer</h2>
  <p class="ledtext">Summen av {totalt_mandat} mandater i landets
    {len(kommuner)} kommunestyrer. Kolonnen til høyre viser hvor mye partiet
    har endret seg i riksopinionen siden lokalvalget 2023, altså den faktoren
    prognosen bygger på.</p>
  <div class="tabellhölje">
    <table>
      <thead><tr><th>Parti</th><th class="tal">Mandater</th>
        <th class="tal">Andel</th><th class="tal">Endring i opinionen</th></tr></thead>
      <tbody>
{riksrader}
      </tbody>
    </table>
  </div>
</section>

<section>
  <h2>Styre i kommunene</h2>
  <p class="ledtext">Hvor mange kommuner hver side får flertall i på egen
    hånd. Der ingen side rekker fram avgjør lokale lister eller samarbeid
    over blokkgrensen, og det er vanligere enn blokktenkningen antyder: etter
    valget 2023 hadde borgerlig side eget flertall i 63 kommuner og rødgrønn
    side i 148.</p>
  <div class="tabellhölje">
    <table>
      <thead><tr><th>Utfall</th><th class="tal">Kommuner</th>
        <th class="tal">Andel</th><th class="tal">Fylkesting</th></tr></thead>
      <tbody>
{styrerader}
      </tbody>
    </table>
  </div>
</section>

<section>
  <h2>Kommunene</h2>
  <p class="ledtext">Alle {len(kommuner)} kommuner. Skriv i feltet for å
    filtrere.</p>
  <input class="sokruta" type="search" id="sok" placeholder="Søk etter kommune"
         aria-label="Søk etter kommune">
  <div id="kommuneliste">{kommunlankar}</div>
</section>
{_metodavsnitt()}

<script>
// Enkel filtrering. Ingen data hämtas, länkarna finns redan i sidan, så den
// fungerar även utan skript.
(function () {{
  var falt = document.getElementById('sok');
  var lankar = Array.prototype.slice.call(
      document.querySelectorAll('#kommuneliste .omradelank'));
  falt.addEventListener('input', function () {{
    var q = falt.value.trim().toLowerCase();
    lankar.forEach(function (a) {{
      a.hidden = q !== '' && a.textContent.toLowerCase().indexOf(q) === -1;
    }});
  }});
}})();
</script>
""" + _sidfot())


def skriv_alla(riksprognos: dict, katalog: Path) -> dict:
    """Bygger samtliga lokalvalssidor. Returnerar räknare och adresser."""
    fylken = lokalmodell.prognos(riksprognos, "fylke")
    kommuner = lokalmodell.prognos(riksprognos, "kommun")

    bas = katalog / "lokalvalg"
    bas.mkdir(parents=True, exist_ok=True)
    (bas / "index.html").write_text(
        bygg_oversikt(fylken, kommuner, riksprognos), encoding="utf-8")

    adresser = [f"{seo.BAS_URL}/lokalvalg/"]
    # URL-delen är norsk ("kommune") medan modellens nivånamn är svenskt
    # ("kommun"), så båda anges.
    for urldel, intern_niva, omraden in (("fylke", "fylke", fylken),
                                         ("kommune", "kommun", kommuner)):
        for namn, d in omraden.items():
            mapp = bas / urldel / slug(namn)
            mapp.mkdir(parents=True, exist_ok=True)
            (mapp / "index.html").write_text(
                bygg_omrade(namn, d, intern_niva), encoding="utf-8")
            adresser.append(f"{seo.BAS_URL}/lokalvalg/{urldel}/{slug(namn)}/")

    return {"fylken": len(fylken), "kommuner": len(kommuner),
            "adresser": adresser}
