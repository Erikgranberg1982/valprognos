"""Bygger den publicerade sidan för den norska prognosen.

Egen modul i stället för en anpassning av dashboard.py. Den svenska
dashboarden är 2 700 rader och bygger sidor för kommun- och regionval,
kandidatlistor och ledamotslistor, som alla saknar norsk motsvarighet i dag.
Att skala ner den vore mer arbete än att skriva det som faktiskt ska visas.

Sidan hämtar ingenting utifrån: logotypen bäddas in som data-URI och grafen
ritas som inline-SVG. Den fungerar därför även utan nätverk och kan läggas
var som helst.
"""
from __future__ import annotations

import base64
import html as html_mod
import json
from datetime import date
from pathlib import Path

import pandas as pd

import config as cfg
import seo

ROT = Path(__file__).resolve().parent.parent

# Lysios palett, samma som den svenska sidan.
KORALL = "#EF7466"
KORALL_MORK = "#D95B4C"
MORKBLA = "#003D63"
SAND = "#FAF2E8"
LJUSBLA = "#F1F3FA"
GRON = "#7DBA74"

# Partierna i politisk ordning, vänster till höger. Samma ordning som
# Wikipedias tabell och norsk vana, till skillnad från cfg.PARTIER.
ORDNING = ["R", "SV", "MDG", "Ap", "Sp", "V", "KrF", "H", "FrP"]

# Månadsnamnen skrivs ut i stället för att hämtas ur strftime, som följer
# systemets locale. Sidan är på norska, så namnen är på bokmål.
MANADER_NO = ["januar", "februar", "mars", "april", "mai", "juni", "juli",
              "august", "september", "oktober", "november", "desember"]


def _langt_datum(d: date) -> str:
    return f"{d.day}. {MANADER_NO[d.month - 1]} {d.year}"


def _tal(varde: float, decimaler: int = 1) -> str:
    """Formaterar ett tal med komma som decimaltecken, som norsk standard."""
    return f"{varde:.{decimaler}f}".replace(".", ",")


def _heltal(varde: int) -> str:
    """Tusentalsavgränsare som hårt mellanslag, som norsk standard."""
    return f"{int(varde):,}".replace(",", "\u00a0")


def _logotyp(filnamn: str) -> str:
    """Läser en logotyp från assets/ och returnerar den som data-URI."""
    fil = ROT / "assets" / filnamn
    if not fil.exists():
        return ""
    return ("data:image/png;base64,"
            + base64.b64encode(fil.read_bytes()).decode("ascii"))


def _diff(varde, enhet: str = "") -> str:
    """Formaterar en förändring mot förra valet med tecken och färg."""
    if varde is None or pd.isna(varde):
        return '<span class="nodata">&ndash;</span>'
    klass = "upp" if varde > 0 else ("ned" if varde < 0 else "stilla")
    tecken = "+" if varde > 0 else ""
    if isinstance(varde, (int,)) or float(varde).is_integer():
        text = f"{tecken}{int(varde)}"
    else:
        text = f"{tecken}{_tal(varde)}"
    return f'<span class="{klass}">{text}{enhet}</span>'


def _trendgraf(trend: pd.DataFrame, bredd: int = 880, hojd: int = 320) -> str:
    """Ritar trendkurvorna som inline-SVG.

    Ingen grafbibliotek behövs för nio linjer, och en inbäddad SVG gör sidan
    oberoende av externa skript.
    """
    if trend is None or trend.empty:
        return '<p class="nodata">Grunnlaget rekker ikke til en trendkurve.</p>'

    marg_v, marg_h, marg_o, marg_u = 42, 12, 14, 30
    rit_b = bredd - marg_v - marg_h
    rit_h = hojd - marg_o - marg_u

    datum = pd.to_datetime(trend["datum"])
    t0, t1 = datum.min(), datum.max()
    spann = max((t1 - t0).days, 1)
    hogsta = max(8.0, float(trend[[p for p in ORDNING if p in trend]].max().max()))
    tak = (int(hogsta / 5) + 1) * 5

    def x(d) -> float:
        return marg_v + (pd.Timestamp(d) - t0).days / spann * rit_b

    def y(v: float) -> float:
        return marg_o + rit_h - min(v, tak) / tak * rit_h

    delar = [f'<svg viewBox="0 0 {bredd} {hojd}" class="graf" '
             f'role="img" aria-label="Oppslutning over tid per parti">']

    # Vågräta hjälplinjer och procentskala.
    for niva in range(0, tak + 1, 5):
        yy = y(niva)
        delar.append(f'<line x1="{marg_v}" y1="{yy:.1f}" x2="{bredd - marg_h}" '
                     f'y2="{yy:.1f}" class="rutnat"/>')
        delar.append(f'<text x="{marg_v - 8}" y="{yy + 4:.1f}" '
                     f'class="axel" text-anchor="end">{niva}</text>')

    # Fyraprocentsspärren, den linje som avgör utjämningsmandaten.
    ys = y(4.0)
    delar.append(f'<line x1="{marg_v}" y1="{ys:.1f}" x2="{bredd - marg_h}" '
                 f'y2="{ys:.1f}" class="sparr"/>')
    delar.append(f'<text x="{bredd - marg_h - 4}" y="{ys - 6:.1f}" '
                 f'class="sparrtext" text-anchor="end">'
                 f'sperregrense 4 %</text>')

    # Årsmarkeringar.
    for ar in range(t0.year, t1.year + 1):
        for manad in (1, 7):
            punkt = pd.Timestamp(year=ar, month=manad, day=1)
            if not (t0 <= punkt <= t1):
                continue
            xx = x(punkt)
            delar.append(f'<line x1="{xx:.1f}" y1="{marg_o}" x2="{xx:.1f}" '
                         f'y2="{marg_o + rit_h}" class="rutnat"/>')
            etikett = str(ar) if manad == 1 else "juli"
            delar.append(f'<text x="{xx:.1f}" y="{hojd - 10}" class="axel" '
                          f'text-anchor="middle">{etikett}</text>')

    for parti in ORDNING:
        if parti not in trend:
            continue
        punkter = " ".join(f"{x(d):.1f},{y(float(v)):.1f}"
                           for d, v in zip(datum, trend[parti]))
        delar.append(f'<polyline points="{punkter}" fill="none" '
                     f'stroke="{cfg.PARTIFARG[parti]}" stroke-width="2.1" '
                     f'stroke-linejoin="round"/>')
        # Partibokstaven vid kurvans slut, så att ingen förklaringsruta behövs.
        sista = float(trend[parti].iloc[-1])
        delar.append(f'<text x="{x(datum.iloc[-1]) + 5:.1f}" '
                     f'y="{y(sista) + 4:.1f}" class="kurvnamn" '
                     f'fill="{cfg.PARTIFARG[parti]}">{parti}</text>')

    delar.append("</svg>")
    return "".join(delar)


def _kammare(sammanfattning: pd.DataFrame) -> str:
    """Ritar Stortinget som en halvcirkel av 169 platser."""
    import math

    mandat = {r["parti"]: int(r["mandat_median"])
              for _, r in sammanfattning.iterrows()}
    # Platserna fylls vänster till höger i politisk ordning.
    kö: list[str] = []
    for parti in ORDNING:
        kö.extend([parti] * mandat.get(parti, 0))

    totalt = len(kö)
    if totalt == 0:
        return ""

    rader, r_inner, r_yttre = 8, 1.0, 2.0
    radier = [r_inner + (r_yttre - r_inner) * i / (rader - 1) for i in range(rader)]
    langd = sum(radier)
    antal = [max(1, round(totalt * r / langd)) for r in radier]
    while sum(antal) > totalt:
        antal[antal.index(max(antal))] -= 1
    while sum(antal) < totalt:
        antal[antal.index(min(antal))] += 1

    platser = []
    for r, n in zip(radier, antal):
        for j in range(n):
            t = 0.5 if n == 1 else j / (n - 1)
            vinkel = math.pi * (1 - t)
            platser.append((vinkel, r))
    platser.sort(key=lambda p: (-p[0], p[1]))

    bredd, hojd, skala = 620, 330, 145
    cx, cy = bredd / 2, hojd - 18
    delar = [f'<svg viewBox="0 0 {bredd} {hojd}" class="kammare" role="img" '
             f'aria-label="Mandatfordeling i Stortinget">']
    for (vinkel, r), parti in zip(platser, kö):
        px = cx + math.cos(vinkel) * r * skala
        py = cy - math.sin(vinkel) * r * skala
        delar.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5.2" '
                     f'fill="{cfg.PARTIFARG[parti]}"/>')
    # Majoritetsstrecket i mitten.
    delar.append(f'<line x1="{cx}" y1="{cy - r_yttre * skala - 12}" x2="{cx}" '
                 f'y2="{cy - r_inner * skala + 16}" class="mittlinje"/>')
    delar.append(f'<text x="{cx}" y="{cy - r_yttre * skala - 18}" '
                 f'class="kammartext" text-anchor="middle">'
                 f'{cfg.MAJORITET} mandater gir flertall</text>')
    delar.append("</svg>")
    return "".join(delar)


def _partitabell(sammanfattning: pd.DataFrame) -> str:
    rader = []
    for _, r in sammanfattning.iterrows():
        parti = r["parti"]
        sannolikhet = r["sannolikhet_over_sparr"]
        # Spärren avgör bara utjämningsmandaten, så en låg sannolikhet betyder
        # inte att partiet blir utan mandat. Det ska framgå.
        if sannolikhet >= 0.98:
            sparr = '<span class="stilla">over</span>'
        else:
            sparr = (f'<span class="{"ned" if sannolikhet < 0.5 else "upp"}">'
                     f'{cfg.formatera_sannolikhet(sannolikhet)}</span>')
        rader.append(f"""      <tr>
        <td class="parti"><span class="prick" style="background:{cfg.PARTIFARG[parti]}"></span>
            <strong>{parti}</strong> <span class="partinamn">{html_mod.escape(cfg.PARTINAMN[parti])}</span></td>
        <td class="tal"><strong>{_tal(r['prognos'])}&nbsp;%</strong></td>
        <td class="tal">{_diff(r.get('forandring'))}</td>
        <td class="tal spann">{_tal(r['p10'])}&ndash;{_tal(r['p90'])}</td>
        <td class="tal"><strong>{int(r['mandat_median'])}</strong></td>
        <td class="tal">{_diff(r.get('mandatforandring'))}</td>
        <td class="tal spann">{int(r['mandat_p10'])}&ndash;{int(r['mandat_p90'])}</td>
        <td class="tal">{sparr}</td>
      </tr>""")
    return "\n".join(rader)


def _regeringstabell(regeringar: pd.DataFrame) -> str:
    rader = []
    for _, r in regeringar.iterrows():
        bredd = max(0.5, r["sannolikhet"] * 100)
        rader.append(f"""      <tr>
        <td><strong>{html_mod.escape(r['namn'])}</strong>
            <div class="beskrivning">{html_mod.escape(r['beskrivning'])}</div></td>
        <td class="tal">{int(r['mandat_median'])}
            <span class="spann">({int(r['mandat_p10'])}&ndash;{int(r['mandat_p90'])})</span></td>
        <td class="sannolikhetscell">
          <div class="sannolikhetsrad">
            <div class="mini"><div class="minifyll" style="width:{bredd:.1f}%"></div></div>
            <span class="sannolikhetstal">{cfg.formatera_sannolikhet(r['sannolikhet'])}</span>
          </div>
        </td>
      </tr>""")
    return "\n".join(rader)


def _matningstabell(matningar: pd.DataFrame, antal: int = 15) -> str:
    rader = []
    for _, r in matningar.head(antal).iterrows():
        celler = "".join(
            f'<td class="tal">{_tal(float(r[p]))}</td>' for p in ORDNING)
        urval = (f"{int(r['urval'])}" if pd.notna(r.get("urval")) else "&ndash;")
        if r.get("urval_gissat"):
            urval = f'{urval}<span class="gissat" title="Utvalget mangler hos kilden, byråets typiske utvalg er brukt">*</span>'
        rader.append(f"""      <tr>
        <td>{html_mod.escape(str(r['institut']))}</td>
        <td class="tal">{pd.Timestamp(r['datum']).date().isoformat()}</td>
        <td class="tal">{urval}</td>
        {celler}
        <td class="tal">{_tal(float(r['viktandel']))}&nbsp;%</td>
      </tr>""")
    return "\n".join(rader)


# Sidans CSS, färdig och delad. Partisidorna importerar samma sträng så
# att de två sidtyperna inte glider ifrån varandra. Färdigrenderad, inte
# en mall: klamrarna är riktiga CSS-klamrar och färgerna är insatta.
STIL = """  :root {
    --korall: #EF7466; --korall-mork: #D95B4C; --morkbla: #003D63;
    --sand: #FAF2E8; --ljusbla: #F1F3FA; --gron: #7DBA74;
    --text: #14232e; --svag: #5d7080; --linje: #e3e8ee; --vit: #fff;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--sand); color: var(--text);
    font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
          "Helvetica Neue", Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  .omslag { max-width: 1080px; margin: 0 auto; padding: 0 20px 72px; }
  header { padding: 34px 0 26px; }
  header img { height: 34px; }
  h1 { font-size: 2.1rem; line-height: 1.2; margin: 22px 0 6px; letter-spacing: -.02em; }
  .underrubrik { color: var(--svag); font-size: 1.05rem; margin: 0; }
  section { background: var(--vit); border-radius: 14px; padding: 26px 28px;
             margin-bottom: 22px; border: 1px solid var(--linje); }
  h2 { font-size: 1.22rem; margin: 0 0 6px; }
  .ledtext { color: var(--svag); font-size: .93rem; margin: 0 0 18px; max-width: 74ch; }
  .nyckeltal { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
                margin-bottom: 22px; }
  .kort { background: var(--vit); border: 1px solid var(--linje); border-radius: 14px; padding: 18px 20px; }
  .kort .etikett { color: var(--svag); font-size: .78rem; text-transform: uppercase;
                    letter-spacing: .07em; margin-bottom: 7px; }
  .partilista { text-transform: none; letter-spacing: 0; opacity: .75; }
  .kort .varde { font-size: 1.85rem; font-weight: 650; line-height: 1.1; letter-spacing: -.02em; }
  .kort .not { color: var(--svag); font-size: .84rem; margin-top: 5px; }
  table { width: 100%; border-collapse: collapse; font-size: .93rem; }
  th, td { padding: 9px 8px; border-bottom: 1px solid var(--linje); text-align: left; }
  th { font-size: .75rem; text-transform: uppercase; letter-spacing: .05em;
        color: var(--svag); font-weight: 600; }
  td.tal, th.tal { text-align: right; font-variant-numeric: tabular-nums; }
  tbody tr:hover { background: var(--ljusbla); }
  .tabellhölje { overflow-x: auto; }
  .parti { white-space: nowrap; }
  .prick { display: inline-block; width: 10px; height: 10px; border-radius: 50%;
            margin-right: 7px; vertical-align: middle; }
  .partinamn { color: var(--svag); font-size: .85rem; }
  .spann { color: var(--svag); font-variant-numeric: tabular-nums; }
  .upp { color: #1a7f4f; font-weight: 600; }
  .ned { color: var(--korall-mork); font-weight: 600; }
  .stilla, .nodata { color: var(--svag); }
  .gissat { color: var(--korall-mork); font-weight: 700; }
  .graf, .kammare { width: 100%; height: auto; display: block; }
  .rutnat { stroke: var(--linje); stroke-width: 1; }
  .sparr { stroke: var(--korall); stroke-width: 1.4; stroke-dasharray: 5 4; }
  .sparrtext { fill: var(--korall-mork); font-size: 11px; font-weight: 600; }
  .axel { fill: var(--svag); font-size: 11px; }
  .kurvnamn { font-size: 12px; font-weight: 700; }
  .mittlinje { stroke: var(--morkbla); stroke-width: 1.4; stroke-dasharray: 4 4; }
  .kammartext { fill: var(--svag); font-size: 12px; }
  .beskrivning { color: var(--svag); font-size: .85rem; margin-top: 3px; max-width: 60ch; }
  .sannolikhetscell { width: 210px; }
  .sannolikhetsrad { display: flex; align-items: center; gap: 10px; }
  .mini { flex: 1; height: 8px; background: var(--ljusbla); border-radius: 4px; overflow: hidden; }
  .minifyll { height: 100%; background: var(--korall); border-radius: 4px; }
  .sannolikhetstal { font-variant-numeric: tabular-nums; font-weight: 650;
                      min-width: 62px; text-align: right; font-size: .9rem; }
  .blockrad { display: grid; gap: 14px; grid-template-columns: 1fr 1fr; }
  @media (max-width: 720px) { .blockrad { grid-template-columns: 1fr; }
    h1 { font-size: 1.6rem; } section { padding: 20px 18px; } }
  footer { color: var(--svag); font-size: .86rem; padding: 8px 0 0; max-width: 78ch; }
  footer a { color: var(--morkbla); }
  .fraga { border-bottom: 1px solid var(--linje); padding: 12px 0; }
  .fraga summary { cursor: pointer; font-weight: 620; }
  .fraga p { color: var(--svag); margin: 9px 0 2px; max-width: 74ch; }
  .partilank { display: inline-flex; align-items: center; gap: 6px;
               border: 1px solid var(--linje); border-left-width: 3px;
               border-radius: 8px; padding: 6px 12px; margin: 0 6px 8px 0;
               text-decoration: none; color: var(--text); font-size: .9rem;
               font-weight: 600; }
  .partilank:hover { background: var(--ljusbla); }
  code { background: var(--ljusbla); padding: 1px 5px; border-radius: 4px; font-size: .88em; }"""


def bygg(sammanfattning: pd.DataFrame, block: dict, regeringar: pd.DataFrame,
         trend: pd.DataFrame, matningar: pd.DataFrame, meta: dict,
         husfaktorer: pd.DataFrame | None = None) -> str:
    """Bygger hela sidan som en enda HTML-sträng."""
    logo = _logotyp("lysio-logo-farg.png")
    valdag = date.fromisoformat(cfg.VALDAG)

    v, h = block["vanster"], block["hoger"]
    ledande = v if v["mandat_median"] >= h["mandat_median"] else h
    storsta = sammanfattning.iloc[0]

    # Partier vars mandat hänger på fyraprocentsspärren.
    spannande = [r for _, r in sammanfattning.iterrows()
                 if 0.05 < r["sannolikhet_over_sparr"] < 0.95]
    if spannande:
        namn = ", ".join(f"{r['parti']} ({cfg.formatera_sannolikhet(r['sannolikhet_over_sparr'])})"
                         for r in spannande)
        sparrtext = (f"Sperregrensen er uavgjort for {namn}. Et parti under "
                     f"fire prosent mister utjevningsmandatene, men beholder "
                     f"de distriktsmandatene det vinner på egen styrke.")
    else:
        sparrtext = ("Ingen partier ligger nå så nær sperregrensen at "
                     "utfallet er uavgjort.")

    partikolumner = "".join(f'<th class="tal">{p}</th>' for p in ORDNING)

    # Sökoptimerad titel och beskrivning, samt de frågor som besvaras synligt
    # längre ner på sidan. Frågorna måste finnas i texten för att få ligga i
    # den strukturerade datan.
    sidtitel = seo.riks_titel(valdag, storsta["parti"], storsta["prognos"])
    sidbeskrivning = seo.riks_beskrivning(sammanfattning, meta, block, valdag)
    fragor = seo.riks_fragor(sammanfattning, block, meta, valdag)
    fragehtml = "".join(
        f'<details class="fraga"><summary>{html_mod.escape(f)}</summary>'
        f'<p>{html_mod.escape(s)}</p></details>' for f, s in fragor)
    partilankar = "".join(
        f'<a class="partilank" href="parti/{seo.SLUG[p]}/" '
        f'style="border-color:{cfg.PARTIFARG[p]}">'
        f'<span class="prick" style="background:{cfg.PARTIFARG[p]}"></span>'
        f'{seo.KORTNAMN.get(p, p)}</a>' for p in ORDNING)

    husfaktorstabell = ""
    if husfaktorer is not None and not husfaktorer.empty:
        hrader = []
        for _, r in husfaktorer.iterrows():
            celler = "".join(f'<td class="tal">{_diff(r[p])}</td>'
                             for p in ORDNING if p in r)
            hrader.append(f'      <tr><td>{html_mod.escape(str(r["institut"]))}</td>'
                          f'<td class="tal">{int(r["antal_matningar"])}</td>'
                          f'{celler}</tr>')
        husfaktorstabell = f"""
  <section>
    <h2>Byråeffekter</h2>
    <p class="ledtext">Hvert byrås systematiske avvik fra de øvrige byråene,
      i prosentpoeng. Modellen trekker fra
      {cfg.HUSFAKTOR_DAMPNING:.0%} av avviket før snittet beregnes.
      Effektene summerer til null per parti, så de måler forskjeller mellom
      byråer og ikke en felles nivåforskyvning.</p>
    <div class="tabellhölje">
      <table>
        <thead><tr><th>Byrå</th><th class="tal">Målinger</th>
          {partikolumner}</tr></thead>
        <tbody>
{chr(10).join(hrader)}
        </tbody>
      </table>
    </div>
  </section>"""

    return f"""<!doctype html>
<html lang="no">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html_mod.escape(sidtitel)} · Lysio Research</title>
{seo.metataggar(sidtitel, sidbeskrivning, seo.BAS_URL + "/")}
{seo.strukturerad_data_riks(sammanfattning, meta, valdag)}
{seo.strukturerad_data_fragor(fragor)}
{cfg.google_analytics()}
<style>
{STIL}
</style>
</head>
<body>
<div class="omslag">

<header>
  {'<img src="' + logo + '" alt="Lysio Research">' if logo else '<strong>Lysio Research</strong>'}
  <h1>Valgprognose {valdag.year}</h1>
  <p class="underrubrik">Stortingsvalget {_langt_datum(valdag)}
     &middot; {meta['dagar_kvar']} dager igjen</p>
</header>

<div class="nyckeltal">
  <div class="kort">
    <div class="etikett">Største parti</div>
    <div class="varde" style="color:{cfg.PARTIFARG[storsta['parti']]}">{storsta['parti']} {_tal(storsta['prognos'])}&nbsp;%</div>
    <div class="not">{html_mod.escape(cfg.PARTINAMN[storsta['parti']])}, {int(storsta['mandat_median'])} mandater</div>
  </div>
  <div class="kort">
    <div class="etikett">Størst blokk</div>
    <div class="varde">{ledande['mandat_median']} mandater</div>
    <div class="not">{html_mod.escape(ledande['namn'])} &middot;
      flertall i {cfg.formatera_sannolikhet(ledande['sannolikhet_majoritet'])} av simuleringene</div>
  </div>
  <div class="kort">
    <div class="etikett">Grunnlag</div>
    <div class="varde">{meta['antal_matningar']} målinger</div>
    <div class="not">{meta['antal_institut']} byråer, siste {meta['senaste_matning']}</div>
  </div>
  <div class="kort">
    <div class="etikett">Simuleringer</div>
    <div class="varde">{_heltal(meta['antal_simuleringar'])}</div>
    <div class="not">per kjøring, med mandater beregnet i 19 valgdistrikter</div>
  </div>
</div>

<section>
  <h2>Prognose per parti</h2>
  <p class="ledtext">Intervallet dekker fire av fem utfall i simuleringen.
    Kolonnen til høyre viser sannsynligheten for at partiet kommer over fire
    prosent. {sparrtext}</p>
  <div class="tabellhölje">
    <table>
      <thead><tr>
        <th>Parti</th><th class="tal">Prognose</th><th class="tal">Mot 2025</th>
        <th class="tal">80&nbsp;%-intervall</th><th class="tal">Mandater</th>
        <th class="tal">Mot 2025</th><th class="tal">Intervall</th>
        <th class="tal">Over sperregrensen</th>
      </tr></thead>
      <tbody>
{_partitabell(sammanfattning)}
      </tbody>
    </table>
  </div>
</section>

<section>
  <h2>Tall for hvert parti</h2>
  <p class="ledtext">Egen side per parti med oppslutning over tid, siste
    målinger og hva prognosen sier om sperregrensen.</p>
  <div>{partilankar}</div>
</section>

<section>
  <h2>Stortinget</h2>
  <p class="ledtext">169 mandater, medianutfallet i simuleringen. 150
    distriktsmandater fordeles i 19 valgdistrikter uten sperregrense, og 19
    utjevningsmandater, ett per distrikt, fordeles bare mellom partier over
    fire prosent.</p>
  {_kammare(sammanfattning)}
  <div class="blockrad">
    <div class="kort">
      <div class="etikett">{html_mod.escape(v['namn'])}
        <span class="partilista">{'+'.join(cfg.BLOCK['vanster'])}</span></div>
      <div class="varde">{v['mandat_median']} mandater</div>
      <div class="not">intervall {v['mandat_p10']}&ndash;{v['mandat_p90']} &middot;
        {_tal(v['roster'])}&nbsp;% av stemmene &middot;
        flertall {cfg.formatera_sannolikhet(v['sannolikhet_majoritet'])}</div>
    </div>
    <div class="kort">
      <div class="etikett">{html_mod.escape(h['namn'])}
        <span class="partilista">{'+'.join(cfg.BLOCK['hoger'])}</span></div>
      <div class="varde">{h['mandat_median']} mandater</div>
      <div class="not">intervall {h['mandat_p10']}&ndash;{h['mandat_p90']} &middot;
        {_tal(h['roster'])}&nbsp;% av stemmene &middot;
        flertall {cfg.formatera_sannolikhet(h['sannolikhet_majoritet'])}</div>
    </div>
  </div>
  <p class="ledtext" style="margin-top:16px">De to blokkene deler alle 169
    mandater mellom seg, og siden tallet er oddetall, når alltid én av dem 85.
    Sannsynlighetene summerer derfor til hundre prosent. Senterpartiet er her
    plassert på rødgrønn side, men har samarbeidet borgerlig tidligere, så
    blokkinndelingen er en forenkling.</p>
</section>

<section>
  <h2>Regjeringsalternativer</h2>
  <p class="ledtext">Sannsynligheten for at partiene til sammen får eget
    flertall, {cfg.MAJORITET} av 169 mandater. Alternativene utelukker ikke
    hverandre, og flertall i mandater betyr ikke at partiene faktisk danner
    regjering.</p>
  <div class="tabellhölje">
    <table>
      <thead><tr><th>Alternativ</th><th class="tal">Mandater</th>
        <th>Sannsynlighet for flertall</th></tr></thead>
      <tbody>
{_regeringstabell(regeringar)}
      </tbody>
    </table>
  </div>
</section>

<section>
  <h2>Oppslutning over tid</h2>
  <p class="ledtext">Tidsvektet snitt av målingene, beregnet rullerende. Den
    stiplede linjen er sperregrensen på fire prosent.</p>
  {_trendgraf(trend)}
</section>

<section>
  <h2>Siste målinger</h2>
  <p class="ledtext">Vekten viser hvor mye hver måling påvirker prognosen.
    Den faller med alderen, halveringstiden er
    {cfg.HALVERINGSTID_DAGAR:.0f} dager, og vokser med kvadratroten av
    utvalget. En stjerne ved utvalget betyr at tallet mangler hos kilden, og
    at byråets typiske utvalg er brukt.</p>
  <div class="tabellhölje">
    <table>
      <thead><tr><th>Byrå</th><th class="tal">Dato</th>
        <th class="tal">Utvalg</th>{partikolumner}<th class="tal">Vekt</th></tr></thead>
      <tbody>
{_matningstabell(matningar)}
      </tbody>
    </table>
  </div>
</section>
{husfaktorstabell}

<section>
  <h2>Spørsmål og svar</h2>
  {fragehtml}
</section>

<section>
  <h2>Slik beregnes prognosen</h2>
  <p class="ledtext">Målingene vektes sammen etter tre kriterier: byråets
    kvalitet, kvadratroten av utvalget, og hvor ny målingen er, med
    {cfg.HALVERINGSTID_DAGAR:.0f} dagers halveringstid. Hvert byrås
    systematiske avvik anslås og trekkes delvis fra. Usikkerheten legges på i
    tre ledd: et korrelert blokkavvik, et partispesifikt avvik, og en drift som
    vokser med tiden til valgdagen, men flater ut etter omtrent to år.</p>
  <p class="ledtext">Mandatene beregnes ikke ut fra landsandelen alene, men
    distriktsvis. Landstrenden skaleres til 19 valgdistrikter med hvert
    distrikts historiske profil, og deretter fordeles mandatene etter
    valgloven: St.&nbsp;Laguës modifiserte metode med første delingstall 1,4,
    distriktsmandater uten sperregrense, og utjevningsmandater bare til partier
    over fire prosent. Dette er nødvendig nettopp i Norge, fordi et parti under
    sperregrensen kan vinne distriktsmandater på egen styrke. Venstre fikk tre
    mandater i 2025 med 3,69 prosent.</p>
  <p class="ledtext">Mandatfordelingen er verifisert: den gjengir
    stortingsvalgene 2021 og 2025 eksakt, uten avvik for noe parti.
    Distriktsmodellen treffer innenfor seks mandater av 169 når den prøves ut
    av utvalg, med forrige valgs profil. Usikkerheten er kalibrert mot de fire
    valgene 2013 til 2025, og 80-prosentintervallene dekket utfallet i 77
    prosent av tilfellene i den testen.</p>
</section>

<footer>
  <p>Bygget {meta['genererad']} av Lysio Research. Målingene er hentet fra
    Wikipedias sammenstilling av norske meningsmålinger, som i sin tur bygger
    på <a href="https://www.pollofpolls.no/">pollofpolls.no</a>.
    Valgresultater per valgdistrikt fra
    <a href="https://www.ssb.no/">SSB</a>, tabell 08092.
    Mandatreglene følger <a href="https://lovdata.no/lov/2002-06-28-57">valgloven</a>.</p>
  <p>En prognose er ikke en spådom. Den beskriver hva målingene sier i dag,
    med den usikkerheten historien tilsier. Med {meta['dagar_kvar']} dager
    igjen til valgdagen kan mye endre seg.</p>
</footer>

</div>
</body>
</html>
"""


def spara(html: str, katalog: Path | None = None) -> Path:
    """Skriver sidan till output/norge/.

    Underkatalogen speglar publiceringsadressen: sidan ligger under /norge/ i
    samma repo som den svenska prognosen, så att den inte kolliderar med
    index.html i roten.

    Miljövariabeln NORSK_OUTPUT pekar om katalogen. Den används i
    arbetsflödet, där sidan ska hamna i repotets gemensamma output/norge/ och
    inte i norge/output/norge/.
    """
    if katalog is None:
        from os import environ
        override = environ.get("NORSK_OUTPUT")
        katalog = (Path(override) if override else ROT / "output" / "norge")
    katalog.mkdir(parents=True, exist_ok=True)
    ut = katalog / "index.html"
    ut.write_text(html, encoding="utf-8")
    return ut
