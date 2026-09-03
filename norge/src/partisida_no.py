"""Bygger en sida per parti.

Skälet är sökmässigt: söken efter opinionsdata är partispecifik. Folk skriver
"Frp meningsmåling" eller "klarer KrF sperregrensen", inte "valgprognose".
Rikssidan kan inte ranka på nio partinamn samtidigt, och konkurrenterna har
redan egna partisidor: politpro.eu har /norge/partier/fremskrittspartiet och
pollofpolls har sina partiprofiler.

Sidorna är inte tomma skal byggda för sökmotorer. Var och en svarar på tre
frågor som rikssidan bara antyder: var partiet ligger nu, hur många mandat det
ger, och om det klarar sperregrensen. Den sista är den intressanta, eftersom
modellen svarar med en sannolikhet och en förklaring av vad spärren faktiskt
gör, vilket ingen nyhetsartikel gör.
"""
from __future__ import annotations

import html as html_mod
from datetime import date
from pathlib import Path

import pandas as pd

import config as cfg
import norsk_dashboard as nd
import seo

ROT = Path(__file__).resolve().parent.parent


def _minigraf(trend: pd.DataFrame, parti: str, sparr: float = 4.0,
              bredd: int = 860, hojd: int = 260) -> str:
    """Ritar ett partis kurva med spärrlinjen tydligt markerad.

    Bara det egna partiet visas. Poängen med sidan är att göra ett partis läge
    mot spärren läsbart, och nio kurvor gör just det svårare.
    """
    if trend is None or trend.empty or parti not in trend:
        return ""

    marg_v, marg_h, marg_o, marg_u = 44, 14, 16, 30
    rit_b, rit_h = bredd - marg_v - marg_h, hojd - marg_o - marg_u
    datum = pd.to_datetime(trend["datum"])
    t0, t1 = datum.min(), datum.max()
    spann = max((t1 - t0).days, 1)
    varden = trend[parti].astype(float)
    tak = max(6.0, float(varden.max()) * 1.25)

    def x(d):
        return marg_v + (pd.Timestamp(d) - t0).days / spann * rit_b

    def y(v):
        return marg_o + rit_h - min(float(v), tak) / tak * rit_h

    farg = cfg.PARTIFARG[parti]
    delar = [f'<svg viewBox="0 0 {bredd} {hojd}" class="graf" role="img" '
             f'aria-label="Oppslutning over tid for {cfg.PARTINAMN[parti]}">']

    for niva in range(0, int(tak) + 1, 2):
        yy = y(niva)
        delar.append(f'<line x1="{marg_v}" y1="{yy:.1f}" '
                     f'x2="{bredd - marg_h}" y2="{yy:.1f}" class="rutnat"/>')
        delar.append(f'<text x="{marg_v - 8}" y="{yy + 4:.1f}" class="axel" '
                     f'text-anchor="end">{niva}</text>')

    # Ytan under kurvan, för att göra nivån lättare att läsa.
    punkter = [(x(d), y(v)) for d, v in zip(datum, varden)]
    yta = (f"{marg_v},{marg_o + rit_h} "
           + " ".join(f"{px:.1f},{py:.1f}" for px, py in punkter)
           + f" {punkter[-1][0]:.1f},{marg_o + rit_h}")
    delar.append(f'<polygon points="{yta}" fill="{farg}" opacity="0.12"/>')

    if sparr < tak:
        ys = y(sparr)
        delar.append(f'<line x1="{marg_v}" y1="{ys:.1f}" '
                     f'x2="{bredd - marg_h}" y2="{ys:.1f}" class="sparr"/>')
        delar.append(f'<text x="{bredd - marg_h - 4}" y="{ys - 7:.1f}" '
                     f'class="sparrtext" text-anchor="end">'
                     f'sperregrense 4 %</text>')

    for ar in range(t0.year, t1.year + 1):
        for manad in (1, 7):
            punkt = pd.Timestamp(year=ar, month=manad, day=1)
            if not (t0 <= punkt <= t1):
                continue
            delar.append(f'<text x="{x(punkt):.1f}" y="{hojd - 10}" '
                         f'class="axel" text-anchor="middle">'
                         f'{ar if manad == 1 else "juli"}</text>')

    delar.append('<polyline points="'
                 + " ".join(f"{px:.1f},{py:.1f}" for px, py in punkter)
                 + f'" fill="none" stroke="{farg}" stroke-width="2.6" '
                 f'stroke-linejoin="round"/>')
    delar.append(f'<circle cx="{punkter[-1][0]:.1f}" '
                 f'cy="{punkter[-1][1]:.1f}" r="4.5" fill="{farg}"/>')
    delar.append("</svg>")
    return "".join(delar)


def _matningsrader(matningar: pd.DataFrame, parti: str, antal: int = 12) -> str:
    rader = []
    for _, r in matningar.head(antal).iterrows():
        varde = float(r[parti])
        klass = "ned" if varde < 4.0 else ""
        rader.append(f"""      <tr>
        <td>{html_mod.escape(str(r['institut']))}</td>
        <td class="tal">{pd.Timestamp(r['datum']).date().isoformat()}</td>
        <td class="tal"><strong class="{klass}">{nd._tal(varde)}&nbsp;%</strong></td>
        <td class="tal">{nd._tal(float(r['viktandel']))}&nbsp;%</td>
      </tr>""")
    return "\n".join(rader)


def bygg(parti: str, rad, sammanfattning: pd.DataFrame, trend: pd.DataFrame,
         matningar: pd.DataFrame, meta: dict) -> str:
    """Bygger HTML för ett partis sida."""
    valdag = date.fromisoformat(cfg.VALDAG)
    namn = cfg.PARTINAMN[parti]
    kort = seo.KORTNAMN.get(parti, parti)
    farg = cfg.PARTIFARG[parti]
    url = seo.partiurl(parti)

    titel = seo.parti_titel(parti, rad["prognos"])
    beskrivning = seo.parti_beskrivning(parti, rad, valdag)
    fragor = seo.parti_fragor(parti, rad, valdag)

    over = rad["sannolikhet_over_sparr"]
    if over >= 0.98:
        sparrklass, sparrtext = "upp", "Trygt over sperregrensen"
    elif over <= 0.02:
        sparrklass, sparrtext = "ned", "Under sperregrensen"
    else:
        sparrklass = "upp" if over >= 0.5 else "ned"
        sparrtext = (f"{cfg.formatera_sannolikhet(over)} sjanse for å klare "
                     f"sperregrensen")

    forra = cfg.VALRESULTAT_2025.get(parti)
    forra_mandat = cfg.MANDAT_2025.get(parti)

    # Länkar till de andra partierna, så att sidorna binds ihop internt.
    andra = "".join(
        f'<a class="partilank" href="../{seo.SLUG[p]}/" '
        f'style="border-color:{cfg.PARTIFARG[p]}">'
        f'<span class="prick" style="background:{cfg.PARTIFARG[p]}"></span>'
        f'{seo.KORTNAMN.get(p, p)}</a>'
        for p in nd.ORDNING if p != parti)

    fragehtml = "".join(
        f'<details class="fraga"><summary>{html_mod.escape(f)}</summary>'
        f'<p>{html_mod.escape(s)}</p></details>' for f, s in fragor)

    return f"""<!doctype html>
<html lang="no">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html_mod.escape(titel)} · Lysio Research</title>
{seo.metataggar(titel, beskrivning, url)}
{seo.strukturerad_data_fragor(fragor)}
{seo.strukturerad_data_brodsmulor([
    ("Valgprognose", f"{seo.BAS_URL}/"),
    (namn, url)])}
{cfg.google_analytics()}
<style>
{nd.STIL}
  .partiheader {{ border-left: 5px solid {farg}; padding-left: 18px; margin: 22px 0 8px; }}
  .stortal {{ font-size: 3.1rem; font-weight: 680; letter-spacing: -.03em;
              line-height: 1; color: {farg}; }}
  .partilank {{ display: inline-flex; align-items: center; gap: 6px;
                border: 1px solid var(--linje); border-left-width: 3px;
                border-radius: 8px; padding: 6px 12px; margin: 0 6px 8px 0;
                text-decoration: none; color: var(--text); font-size: .9rem;
                font-weight: 600; }}
  .partilank:hover {{ background: var(--ljusbla); }}
  .fraga {{ border-bottom: 1px solid var(--linje); padding: 12px 0; }}
  .fraga summary {{ cursor: pointer; font-weight: 620; }}
  .fraga p {{ color: var(--svag); margin: 9px 0 2px; max-width: 74ch; }}
  .brodsmula {{ font-size: .87rem; color: var(--svag); padding-top: 26px; }}
  .brodsmula a {{ color: var(--morkbla); }}
</style>
</head>
<body>
<div class="omslag">

<nav class="brodsmula"><a href="../../">Valgprognose {valdag.year}</a>
  &rsaquo; {html_mod.escape(namn)}</nav>

<header>
  <div class="partiheader">
    <h1>{html_mod.escape(namn)}</h1>
    <p class="underrubrik">Meningsmålinger og mandatprognose for
      stortingsvalget {nd._langt_datum(valdag)}</p>
  </div>
</header>

<div class="nyckeltal">
  <div class="kort">
    <div class="etikett">Oppslutning nå</div>
    <div class="stortal">{nd._tal(rad['prognos'])}&nbsp;%</div>
    <div class="not">80&nbsp;%-intervall {nd._tal(rad['p10'])}&ndash;{nd._tal(rad['p90'])}&nbsp;%
      {f"&middot; {nd._diff(rad.get('forandring'))} mot 2025" if forra else ""}</div>
  </div>
  <div class="kort">
    <div class="etikett">Mandater</div>
    <div class="stortal">{int(rad['mandat_median'])}</div>
    <div class="not">intervall {int(rad['mandat_p10'])}&ndash;{int(rad['mandat_p90'])}
      {f"&middot; {nd._diff(rad.get('mandatforandring'))} mot 2025" if forra_mandat is not None else ""}</div>
  </div>
  <div class="kort">
    <div class="etikett">Sperregrensen</div>
    <div class="varde {sparrklass}">{sparrtext}</div>
    <div class="not">Grensen på fire prosent gjelder bare
      utjevningsmandatene</div>
  </div>
  <div class="kort">
    <div class="etikett">Ved valget 2025</div>
    <div class="varde">{nd._tal(forra) if forra else '&ndash;'}&nbsp;%</div>
    <div class="not">{forra_mandat if forra_mandat is not None else '&ndash;'} mandater</div>
  </div>
</div>

<section>
  <h2>Oppslutning over tid</h2>
  <p class="ledtext">Tidsvektet snitt av meningsmålingene. Den stiplede linjen
    er sperregrensen på fire prosent, som avgjør retten til
    utjevningsmandater.</p>
  {_minigraf(trend, parti)}
</section>

<section>
  <h2>Spørsmål og svar</h2>
  {fragehtml}
</section>

<section>
  <h2>Siste målinger for {html_mod.escape(kort)}</h2>
  <p class="ledtext">Vekten viser hvor mye hver måling påvirker prognosen.
    Målinger under fire prosent er markert.</p>
  <div class="tabellhölje">
    <table>
      <thead><tr><th>Byrå</th><th class="tal">Dato</th>
        <th class="tal">{html_mod.escape(kort)}</th>
        <th class="tal">Vekt</th></tr></thead>
      <tbody>
{_matningsrader(matningar, parti)}
      </tbody>
    </table>
  </div>
</section>

<section>
  <h2>Andre partier</h2>
  <p class="ledtext">Samme tall for de øvrige partiene.</p>
  <div>{andra}</div>
  <p class="ledtext" style="margin-top:14px">
    <a href="../../">Se hele prognosen med mandatfordeling i Stortinget</a></p>
</section>

<footer>
  <p>Bygget {meta['genererad']} av Lysio Research. Målingene er hentet fra
    Wikipedias sammenstilling av norske meningsmålinger, som bygger på
    <a href="https://www.pollofpolls.no/">pollofpolls.no</a>. Valgresultater
    per valgdistrikt fra <a href="https://www.ssb.no/">SSB</a>, tabell 08092.
    Mandatreglene følger
    <a href="https://lovdata.no/lov/2002-06-28-57">valgloven</a>.</p>
  <p>En prognose er ikke en spådom. Den beskriver hva målingene sier i dag,
    med den usikkerheten historien tilsier.</p>
</footer>

</div>
</body>
</html>
"""


def skriv_alla(sammanfattning: pd.DataFrame, trend: pd.DataFrame,
               matningar: pd.DataFrame, meta: dict,
               katalog: Path) -> list[Path]:
    """Skriver en sida per parti under katalog/parti/<slug>/index.html.

    Katalogstrukturen ger rena adresser utan filändelse, vilket är att
    föredra framför parti/rodt.html.
    """
    utfiler = []
    indexerad = sammanfattning.set_index("parti")
    for parti in cfg.PARTIER:
        if parti not in indexerad.index:
            continue
        rad = indexerad.loc[parti]
        html = bygg(parti, rad, sammanfattning, trend, matningar, meta)
        mapp = katalog / "parti" / seo.SLUG[parti]
        mapp.mkdir(parents=True, exist_ok=True)
        fil = mapp / "index.html"
        fil.write_text(html, encoding="utf-8")
        utfiler.append(fil)
    return utfiler
