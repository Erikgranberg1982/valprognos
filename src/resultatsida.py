"""Valresultatet 2026 med prognosen som jämförelse.

Sidan finns för att prognosen ska gå att bedöma. Den visar utfallet bredvid
det modellen sa två dagar innan, vilka regeringsunderlag som faktiskt når
majoritet, och vilket av scenarierna som kom närmast.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import config as cfg
import seo

ROT = Path(__file__).resolve().parent.parent


def las_resultat() -> dict:
    fil = ROT / "data" / "valresultat_2026.csv"
    if not fil.exists():
        return {}
    ut = {}
    with open(fil, encoding="utf-8") as f:
        for rad in csv.DictReader(f):
            ut[rad["parti"]] = {
                "procent": float(rad["procent"]),
                "mandat": int(rad["mandat"]),
                "status": rad.get("status", ""),
            }
    return ut


def las_slutprognos(katalog: Path) -> dict:
    fil = katalog / "huvudprognos.csv"
    if not fil.exists():
        return {}
    ut = {}
    with open(fil, encoding="utf-8") as f:
        for rad in csv.DictReader(f):
            ut[rad["parti"]] = {
                "stod": float(rad["stod"]),
                "mandat": int(rad["mandat"]),
                "over_sparr": float(rad["sannolikhet_over_sparr"]),
            }
    return ut


def las_scenarier(katalog: Path) -> dict:
    fil = katalog / "scenarier.csv"
    if not fil.exists():
        return {}
    ut: dict[str, dict] = {}
    with open(fil, encoding="utf-8") as f:
        for rad in csv.DictReader(f):
            if rad["parti"] not in cfg.PARTIER or not rad["stod"]:
                continue
            ut.setdefault(rad["scenario_namn"], {})[rad["parti"]] = {
                "stod": float(rad["stod"]), "mandat": int(rad["mandat"])}
    return ut


def _lokala_niva(regioner: list, kommuner: list) -> dict:
    """Utvärderar region- och kommunprognosen mot utfallet."""
    import utvardering
    return {
        "region": utvardering.utvardera_niva(
            regioner, ROT / "data" / "valresultat_region_2026.csv"),
        "kommun": utvardering.utvardera_niva(
            kommuner, ROT / "data" / "valresultat_kommun_2026.csv"),
    }


def _nivablock(namn: str, d: dict, forklaring: str) -> str:
    if not d:
        return ""
    lista = lambda rader: "".join(
        f'<tr><td>{o["namn"]}</td><td class="ta">{o["mae"]:.2f}</td>'
        f'<td class="ta dim">{o["mandatfel"]}</td></tr>' for o in rader)
    return f'''
  <div class="nivakort">
    <div class="nivarub">{namn}</div>
    <div class="nyckel">
      <div><div class="n">{d["mae"]:.2f}</div>
        <div class="e">procentenheters medelfel</div></div>
      <div><div class="n">{d["median"]:.2f}</div>
        <div class="e">median</div></div>
      <div><div class="n">{d["antal"]}</div>
        <div class="e">områden</div></div>
    </div>
    <p class="fot">{forklaring}</p>
    <div class="tvakol">
      <div>
        <table><thead><tr><th>Träffade bäst</th><th class="ta">pe</th>
        <th class="ta">mandat</th></tr></thead>
        <tbody>{lista(d["basta"])}</tbody></table>
      </div>
      <div>
        <table><thead><tr><th>Träffade sämst</th><th class="ta">pe</th>
        <th class="ta">mandat</th></tr></thead>
        <tbody>{lista(d["samsta"])}</tbody></table>
      </div>
    </div>
  </div>'''


def skriv(katalog: Path, slutprognos: Path,
          regioner: list | None = None,
          kommuner: list | None = None) -> Path | None:
    resultat = las_resultat()
    if not resultat:
        return None
    prognos = las_slutprognos(slutprognos)
    scen = las_scenarier(slutprognos)

    # --- Partitabellen ---------------------------------------------------
    rader = []
    fel_stod, fel_mandat = [], []
    for parti in sorted(cfg.PARTIER, key=lambda p: -resultat[p]["mandat"]):
        r = resultat[parti]
        p = prognos.get(parti, {})
        ds = p.get("stod", 0) - r["procent"]
        dm = p.get("mandat", 0) - r["mandat"]
        fel_stod.append(abs(ds))
        fel_mandat.append(abs(dm))
        kl = "ned" if dm < 0 else ("upp" if dm > 0 else "noll")
        rader.append(
            f'<tr><td><span class="pp" style="background:'
            f'{cfg.PARTIFARG[parti]}"></span>{cfg.PARTINAMN[parti]}</td>'
            f'<td class="ta"><strong>{r["procent"]:.1f} %</strong></td>'
            f'<td class="ta"><strong>{r["mandat"]}</strong></td>'
            f'<td class="ta dim">{p.get("stod", 0):.1f} %</td>'
            f'<td class="ta dim">{p.get("mandat", 0)}</td>'
            f'<td class="ta {kl}">{dm:+d}</td></tr>')

    mae = sum(fel_stod) / len(fel_stod)
    mandatfel = sum(fel_mandat)

    # --- Regeringsunderlag med faktiskt utfall ---------------------------
    koal = []
    for alt in cfg.REGERINGSALTERNATIV:
        m = sum(resultat.get(p, {}).get("mandat", 0) for p in alt["partier"])
        koal.append((alt["namn"], "+".join(alt["partier"]), m))
    for namn, kod in (("Vänstersidan V+S+MP+C", "V+S+MP+C"),
                      ("Högersidan M+KD+L+SD", "M+KD+L+SD")):
        m = sum(resultat[p]["mandat"] for p in kod.split("+"))
        koal.append((namn, kod, m))
    koal.sort(key=lambda x: -x[2])

    krader = []
    for namn, partier, m in koal:
        diff = m - 175
        marke = ('<span class="kmarke ja">Majoritet</span>' if m >= 175
                 else f'<span class="kmarke nej">{diff}</span>')
        bredd = min(100, m / cfg.MANDAT_TOTALT * 100)
        krader.append(
            f'<div class="koalrad{" vinner" if m >= 175 else ""}">'
            f'<div class="knamn">{namn}<span class="kpartier">{partier}'
            f'</span></div>'
            f'<div class="kbar"><div class="kfyll" style="width:{bredd:.1f}%">'
            f'</div><div class="kgrans" style="left:'
            f'{175 / cfg.MANDAT_TOTALT * 100:.2f}%"></div></div>'
            f'<div class="kmandat">{m}</div>'
            f'<div class="kstatus">{marke}</div></div>')

    # --- Scenarierna, rangordnade -----------------------------------------
    srader = []
    lista = [("Huvudprognosen", {p: {"stod": prognos[p]["stod"],
                                     "mandat": prognos[p]["mandat"]}
                                 for p in prognos})]
    lista += list(scen.items())
    med_fel = []
    for namn, varden in lista:
        f_stod = [abs(varden[p]["stod"] - resultat[p]["procent"])
                  for p in cfg.PARTIER if p in varden]
        f_mand = sum(abs(varden[p]["mandat"] - resultat[p]["mandat"])
                     for p in cfg.PARTIER if p in varden)
        med_fel.append((namn, sum(f_stod) / len(f_stod), f_mand))
    med_fel.sort(key=lambda x: x[1])
    for i, (namn, fel, fm) in enumerate(med_fel):
        klass = " basta" if i == 0 else (
            " huvud" if namn == "Huvudprognosen" else "")
        srader.append(
            f'<tr class="{klass.strip()}"><td>{namn}</td>'
            f'<td class="ta"><strong>{fel:.2f}</strong></td>'
            f'<td class="ta dim">{fm}</td></tr>')

    # Region och kommun, om prognosdatan finns.
    lokalt = _lokala_niva(regioner or [], kommuner or [])
    lokalhtml = ""
    if lokalt.get("region") or lokalt.get("kommun"):
        lokalhtml = (
            '<h2>Region och kommun</h2>'
            '<div class="rub">Hur väl träffade de lokala prognoserna</div>'
            '<div class="kort">'
            '<p class="besk">Riksprognosen bygger på opinionsmätningar. För '
            'region och kommun finns nästan inga mätningar, så de härleds ur '
            'områdets eget resultat i förra valet skalat med rikstrenden. '
            'Felen är därför väntat större.</p>'
            + _nivablock("Regionfullmäktige", lokalt.get("region", {}),
                         "Tjugo regioner. Samma metod som kommunerna, men "
                         "med SCB:s partisympatiundersökning som extra "
                         "underlag.")
            + _nivablock("Kommunfullmäktige", lokalt.get("kommun", {}),
                         "290 kommuner. Små kommuner är svårast: där kan "
                         "ett lokalt parti eller en enskild kandidat flytta "
                         "flera procentenheter utan att synas i rikstrenden.")
            + '</div>')

    status = next(iter(resultat.values()))["status"]
    titel = "Valresultat 2026 mot prognosen"
    besk = (f"Riksdagsvalet 13 september 2026: S {resultat['S']['procent']:.1f} %, "
            f"M {resultat['M']['procent']:.1f} %, SD {resultat['SD']['procent']:.1f} %. "
            f"Jämfört med prognosen två dagar innan, som hade ett "
            f"medelabsolutfel på {mae:.2f} procentenheter.")

    html = _MALL.format(
        ga=cfg.google_analytics(),
        seo_taggar=seo.metataggar(titel, besk, "valresultat_2026.html"),
        rader="".join(rader),
        krader="".join(krader),
        srader="".join(srader),
        mae=f"{mae:.2f}",
        mandatfel=mandatfel,
        status=status,
        basta=med_fel[0][0],
        basta_fel=f"{med_fel[0][1]:.2f}",
        l_sparr=f"{prognos.get('L', {}).get('over_sparr', 0) * 100:.0f}",
        lokalhtml=lokalhtml,
        valdag=cfg.VALDAG,
    )
    katalog.mkdir(parents=True, exist_ok=True)
    ut = katalog / "valresultat_2026.html"
    ut.write_text(html, encoding="utf-8")
    return ut


_MALL = """<!doctype html><html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Valresultat 2026 mot prognosen</title>
{seo_taggar}
{ga}
<link href="https://fonts.googleapis.com/css2?family=Work+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{{--bg:#fff;--text:#003D63;--svag:#69727D;--linje:#E3E8F0;--panel:#F1F3FA;
--kort:#fff;--korall:#EF7466;--korall-mork:#D95B4C;--korall-ljus:#FBE4E0;--gron:#7DBA74;
--skugga:0 2px 4px 0 rgba(183,193,210,.35)}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0E1621;--text:#EAF0F7;--svag:#93A2B5;
--linje:#22303F;--panel:#16202E;--kort:#16202E;--korall-ljus:#3A2320;
--skugga:0 2px 4px 0 rgba(0,0,0,.4)}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--text);
font:15px/1.6 'Work Sans',-apple-system,sans-serif;padding:0 0 80px}}
.w{{max-width:1000px;margin:0 auto;padding:0 24px}}
header{{background:var(--panel);border-bottom:1px solid var(--linje);
padding:26px 0 22px;margin-bottom:26px}}
h1{{font-size:29px;font-weight:800;letter-spacing:-1px;margin:0 0 4px}}
.sub{{color:var(--svag);font-size:14px}}
.tbaka{{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;
font-weight:600;color:var(--korall);text-decoration:none;margin-bottom:12px;
padding:5px 11px 5px 8px;border:1px solid rgba(0,0,0,.12);
border-radius:99px;background:var(--panel);transition:.15s}}
.tbaka:hover{{background:var(--korall);color:#fff;border-color:var(--korall)}}
h2{{font-size:11.5px;text-transform:uppercase;letter-spacing:1.5px;
color:var(--svag);font-weight:700;margin:34px 0 3px}}
.rub{{font-size:23px;font-weight:700;letter-spacing:-.6px;margin:0 0 16px}}
.kort{{background:var(--kort);border:1px solid var(--linje);border-radius:16px;
padding:24px;box-shadow:var(--skugga)}}
.besk{{margin:0 0 4px;font-size:14px;line-height:1.7;max-width:760px}}
.besk strong{{font-weight:700}}
table{{width:100%;border-collapse:collapse;margin-top:16px;font-size:13.5px}}
th{{text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:1px;
color:var(--svag);font-weight:700;padding:0 9px 7px 0;
border-bottom:1px solid var(--linje)}}
td{{padding:9px 9px 9px 0;border-bottom:1px solid var(--linje)}}
tr:last-child td{{border-bottom:none}}
.ta{{text-align:right;font-variant-numeric:tabular-nums}}
.dim{{color:var(--svag)}}
.upp{{color:var(--gron);font-weight:700}}
.ned{{color:var(--korall);font-weight:700}}
.noll{{color:var(--svag)}}
.pp{{display:inline-block;width:10px;height:10px;border-radius:3px;
margin-right:8px}}
tr.basta td{{background:rgba(125,186,116,.14);font-weight:600}}
tr.huvud td{{background:var(--korall-ljus)}}
.koalrad{{display:grid;grid-template-columns:210px 1fr 46px 92px;gap:11px;
align-items:center;padding:9px 0;border-bottom:1px solid var(--linje)}}
.koalrad:last-child{{border-bottom:none}}
.knamn{{font-size:13.5px;font-weight:600;line-height:1.3}}
.kpartier{{display:block;font-size:11px;color:var(--svag);font-weight:400}}
.kbar{{position:relative;height:10px;background:var(--panel);border-radius:5px}}
.kfyll{{height:100%;background:#c3ccda;border-radius:5px}}
.koalrad.vinner .kfyll{{background:var(--gron)}}
.kgrans{{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--text);
opacity:.5}}
.kmandat{{text-align:right;font-weight:700;font-variant-numeric:tabular-nums}}
.kmarke{{font-size:11px;padding:2px 9px;border-radius:20px;white-space:nowrap}}
.kmarke.ja{{background:rgba(125,186,116,.2);color:#3f7a36}}
.kmarke.nej{{background:var(--panel);color:var(--svag)}}
.fot{{margin:14px 0 0;font-size:12px;color:var(--svag);line-height:1.6}}
.nyckel{{display:flex;flex-wrap:wrap;gap:34px;margin:6px 0 4px}}
.nyckel .n{{font-size:34px;font-weight:800;letter-spacing:-1.4px;line-height:1.15}}
.nyckel .e{{font-size:12.5px;color:var(--svag)}}
.nivakort{{border-top:1px solid var(--linje);padding-top:20px;margin-top:22px}}
.nivakort:first-of-type{{border-top:none;padding-top:0;margin-top:14px}}
.nivarub{{font-size:16px;font-weight:700;margin-bottom:4px}}
.tvakol{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));
gap:24px;margin-top:6px}}
@media(max-width:640px){{.koalrad{{grid-template-columns:1fr 46px 78px}}
.kbar{{display:none}}}}
</style></head><body>
<header><div class="w">
<a class="tbaka" href="index.html"><span>&#8592;</span> Till prognosen</a>
<h1>Valresultatet mot prognosen</h1>
<div class="sub">Riksdagsvalet {valdag} · {status}</div>
</div></header>
<div class="w">

<h2>Utfallet</h2>
<div class="rub">Så gick valet</div>
<div class="kort">
  <div class="nyckel">
    <div><div class="n">{mae}</div><div class="e">procentenheters medelfel</div></div>
    <div><div class="n">{mandatfel}</div><div class="e">felplacerade mandat</div></div>
  </div>
  <table>
    <thead><tr><th>Parti</th><th class="ta">Resultat</th><th class="ta">Mandat</th>
    <th class="ta">Prognos</th><th class="ta">Prognos</th>
    <th class="ta">Diff</th></tr></thead>
    <tbody>{rader}</tbody>
  </table>
  <p class="fot">Prognosen är den som frystes två dagar före valet. Liberalerna
  är det stora felet: modellen gav {l_sparr} procents sannolikhet att partiet
  skulle klara spärren och noll mandat i punktskattningen, men utfallet blev
  nitton mandat.</p>
</div>

<h2>Regeringsunderlag</h2>
<div class="rub">Vilka som når majoritet med det faktiska resultatet</div>
<div class="kort">
  <p class="besk">Räknat på valresultatet, inte på prognosen. Att ett underlag
  räcker i mandat betyder inte att partierna vill regera ihop.</p>
  {krader}
  <p class="fot">Strecket markerar 175 mandat. Ingen av de två sidorna nådde
  egen majoritet.</p>
</div>

{lokalhtml}

<h2>Träffsäkerhet</h2>
<div class="rub">Vilken variant kom närmast</div>
<div class="kort">
  <p class="besk">Sidan publicerade sex scenarier vid sidan av huvudprognosen.
  Här rangordnas de efter medelabsolutfelet i procent, inte efter mandat:
  ett parti som ligger nära spärren ger nitton mandats utslag oavsett hur
  nära procenttalet låg, vilket skulle låta Liberalerna avgöra hela
  rangordningen. <strong>{basta}</strong> träffade bäst med {basta_fel}
  procentenheters medelfel.</p>
  <table>
    <thead><tr><th>Variant</th><th class="ta">Medelfel, pe</th>
    <th class="ta">Mandat i fel parti</th></tr></thead>
    <tbody>{srader}</tbody>
  </table>
  <p class="fot">De två bästa varianterna byggde båda på att de färskaste
  mätningarna vägde för lite i huvudprognosen. Det stämde 2026, men gick emot
  ett backtest mot 2018 och 2022 som gjordes före valet och då visade
  motsatsen.</p>
</div>

</div></body></html>"""
