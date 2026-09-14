"""Utfall per kommun och region, sökbart.

Startsidan visar bara topplistor. Den här sidan låter läsaren slå upp sin egen
kommun och se valresultatet, prognosen och vad som krävs för majoritet.
"""
from __future__ import annotations

import base64
import csv
import gzip
import json
import re
from collections import defaultdict
from pathlib import Path

import config as cfg
import seo

ROT = Path(__file__).resolve().parent.parent


def _facit(fil: Path) -> dict:
    ut: dict = defaultdict(dict)
    if not fil.exists():
        return {}
    with open(fil, encoding="utf-8") as f:
        for rad in csv.DictReader(f):
            ut[rad["omrade_kod"]][rad["parti"]] = {
                "p": float(rad["procent"]), "m": int(rad["mandat"]),
                "namn": rad.get("omrade_namn", "")}
    return dict(ut)


def _prognosdata() -> tuple[list, list]:
    """Områdesprognoserna ur den byggda prognossidan."""
    fil = ROT / "output" / "prognos_2026.html"
    if not fil.exists():
        return [], []
    h = fil.read_text(encoding="utf-8")
    m = re.search(r"const LOKAL = (\{.*?\});", h, re.S)
    if not m:
        return [], []
    d = json.loads(m.group(1))
    kom = []
    if d.get("kommun_gz"):
        kom = json.loads(gzip.decompress(base64.b64decode(d["kommun_gz"])))
    return d.get("region", []), kom


def _norm(kod: str) -> str:
    siffror = str(kod).strip().rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return siffror.zfill(2) if len(siffror) <= 2 else siffror


def _koalitioner() -> list:
    try:
        import lokala_koalitioner
        return lokala_koalitioner.las()
    except Exception:
        return []


def _bygg(niva: str, prognos: list, facitfil: Path) -> list:
    facit = {_norm(k): v for k, v in _facit(facitfil).items()}
    pk = {_norm(p.get("kod", "")): p for p in prognos}
    try:
        import lokala_koalitioner
        styren = lokala_koalitioner.las_kommunstyren()
    except Exception:
        styren = {}

    ut = []
    for kod, partier in sorted(facit.items()):
        namn = next(iter(partier.values())).get("namn", "")
        p = pk.get(kod, {})
        mandat = {q: v["m"] for q, v in partier.items() if v["m"]}
        totalt = sum(mandat.values())
        if not totalt:
            continue
        majoritet = totalt // 2 + 1

        rader = []
        fel = []
        for parti in cfg.PARTIER:
            if parti not in partier:
                continue
            pstod = p.get("stod", {}).get(parti)
            pmandat = p.get("mandat", {}).get(parti)
            diff = (pstod - partier[parti]["p"]) if pstod is not None else None
            if diff is not None:
                fel.append(abs(diff))
            rader.append({
                "p": parti, "r": round(partier[parti]["p"], 1),
                "m": partier[parti]["m"],
                "pp": round(pstod, 1) if pstod is not None else None,
                "pm": pmandat,
                "d": round(diff, 1) if diff is not None else None,
            })
        # Lokala partier, som modellen inte skattar var för sig.
        lokala = [{"p": q, "r": round(v["p"], 1), "m": v["m"]}
                  for q, v in sorted(partier.items(), key=lambda x: -x[1]["m"])
                  if q not in cfg.PARTIER and v["m"]]

        vanster = sum(mandat.get(q, 0) for q in cfg.BLOCK["vanster"])
        hoger = sum(mandat.get(q, 0) for q in cfg.BLOCK["hoger"])

        # Vilka koalitioner som når majoritet med det faktiska resultatet.
        # Ett styre är en politisk överenskommelse, så det här säger vad som
        # är aritmetiskt möjligt, inte vad partierna vill.
        koal = []
        for k in _koalitioner():
            delar = k["partier"]
            if isinstance(delar, str):
                delar = [d.strip() for d in delar.split("+")]
            m = sum(mandat.get(d, 0) for d in delar)
            koal.append({"n": k["namn"], "p": "+".join(delar), "m": m,
                         "ja": m >= majoritet})
        koal.sort(key=lambda x: -x["m"])

        # Det sittande styret, som jämförelsepunkt: höll det efter valet?
        styre = None
        if niva == "kommun":
            sitt = styren.get(kod)
            if sitt:
                # SKR skriver ÖP för lokala partier. Valresultatet har dem
                # med egna förkortningar, så de summeras ihop.
                lokalmandat = sum(m for q, m in mandat.items()
                                  if q not in cfg.PARTIER)
                m = sum(lokalmandat if q == "ÖP" else mandat.get(q, 0)
                        for q in sitt["partier"])
                styre = {"p": "+".join(
                    sitt.get("lokalt_namn") or q if q == "ÖP" else q
                    for q in sitt["partier"]),
                    "m": m, "ja": m >= majoritet,
                    "fore": sitt.get("majoritet", "")}
        ut.append({
            "kod": kod, "namn": namn, "niva": niva,
            "tot": totalt, "maj": majoritet,
            "v": vanster, "h": hoger, "o": totalt - vanster - hoger,
            "rader": rader, "lokala": lokala, "koal": koal,
            "styre": styre,
            "mae": round(sum(fel) / len(fel), 2) if fel else None,
        })
    return ut


def skriv(katalog: Path) -> Path | None:
    regioner, kommuner = _prognosdata()
    data = (_bygg("region", regioner,
                  ROT / "data" / "valresultat_region_2026.csv")
            + _bygg("kommun", kommuner,
                    ROT / "data" / "valresultat_kommun_2026.csv"))
    if not data:
        return None

    titel = "Valresultat per kommun och region 2026"
    besk = ("Slå upp valresultatet i din kommun eller region: mandat per "
            "parti, vad som krävs för majoritet och hur nära prognosen låg.")

    html = _MALL.format(
        ga=cfg.google_analytics(),
        seo_taggar=seo.metataggar(titel, besk, "omraden_2026.html"),
        data=json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        farger=json.dumps(cfg.PARTIFARG, ensure_ascii=False),
        antal_kommun=sum(1 for d in data if d["niva"] == "kommun"),
        antal_region=sum(1 for d in data if d["niva"] == "region"),
    )
    katalog.mkdir(parents=True, exist_ok=True)
    ut = katalog / "omraden_2026.html"
    ut.write_text(html, encoding="utf-8")
    return ut


_MALL = """<!doctype html><html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Valresultat per kommun och region 2026</title>
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
border-radius:99px;background:var(--kort);transition:.15s}}
.tbaka:hover{{background:var(--korall);color:#fff;border-color:var(--korall)}}
.styr{{display:flex;flex-wrap:wrap;gap:10px;margin:0 0 18px}}
#sok{{flex:1;min-width:220px;font:inherit;font-size:15px;padding:10px 15px;
border:1.5px solid var(--linje);border-radius:12px;background:var(--kort);
color:var(--text)}}
#sok:focus{{outline:none;border-color:var(--korall)}}
.nivaknapp{{font:inherit;font-size:13px;font-weight:600;cursor:pointer;
padding:9px 16px;border:1.5px solid var(--linje);border-radius:12px;
background:var(--kort);color:var(--text)}}
.nivaknapp.on{{border-color:var(--korall);color:var(--korall)}}
.rakn{{color:var(--svag);font-size:13px;margin:0 0 14px}}
.omrade{{background:var(--kort);border:1px solid var(--linje);
border-radius:14px;padding:18px 20px;margin-bottom:12px;box-shadow:var(--skugga)}}
.onamn{{font-size:18px;font-weight:700;letter-spacing:-.4px}}
.ometa{{font-size:12.5px;color:var(--svag);margin-bottom:12px}}
.oniva{{display:inline-block;font-size:11px;font-weight:700;padding:2px 9px;
border-radius:20px;margin-left:9px;vertical-align:middle;
background:var(--panel);color:var(--svag)}}
.oniva.region{{background:rgba(0,61,99,.1);color:var(--text)}}
.olage{{display:inline-block;font-size:11px;font-weight:700;padding:2px 9px;
border-radius:20px;margin-left:6px;vertical-align:middle}}
.olage.v{{background:rgba(238,32,32,.15);color:#c11}}
.olage.h{{background:rgba(82,189,236,.2);color:#1a6b94}}
.olage.o{{background:var(--korall-ljus);color:var(--korall-mork)}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.9px;
color:var(--svag);font-weight:700;padding:0 8px 6px 0;
border-bottom:1px solid var(--linje)}}
td{{padding:6px 8px 6px 0;border-bottom:1px solid var(--linje)}}
tr:last-child td{{border-bottom:none}}
.ta{{text-align:right;font-variant-numeric:tabular-nums}}
.dim{{color:var(--svag)}}
.traff{{color:var(--gron);font-weight:700}}
.miss{{color:var(--korall);font-weight:700}}
.mitt{{font-weight:600}}
.pp{{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:7px}}
tr.lokal td{{background:var(--panel)}}
.tomt{{color:var(--svag);padding:30px 0;text-align:center}}
.koalrub{{font-size:10px;text-transform:uppercase;letter-spacing:.9px;
color:var(--svag);font-weight:700;margin:16px 0 8px}}
.koallista{{display:flex;flex-wrap:wrap;gap:7px}}
.krad{{display:flex;align-items:baseline;gap:7px;background:var(--panel);
border-radius:9px;padding:5px 11px;font-size:12px}}
.krad.ja{{background:rgba(125,186,116,.18)}}
.kp{{font-weight:700}}
.km{{font-variant-numeric:tabular-nums;font-weight:700}}
.kt{{color:var(--svag);font-size:11px}}
.krad.ja .kt{{color:#3f7a36;font-weight:600}}
.krad.sitt{{border:1.5px solid var(--korall)}}
@media(max-width:560px){{.dolj{{display:none}}}}
</style></head><body>
<header><div class="w">
<a class="tbaka" href="index.html"><span>&#8592;</span> Till valresultatet</a>
<h1>Utfall per kommun och region</h1>
<div class="sub">{antal_kommun} kommuner och {antal_region} regioner ·
mandat, majoritetsläge och hur nära prognosen låg</div>
</div></header>
<div class="w">
<div class="styr">
  <input id="sok" type="search" placeholder="Sök kommun eller region...">
  <button class="nivaknapp on" data-niva="">Alla</button>
  <button class="nivaknapp" data-niva="kommun">Kommuner</button>
  <button class="nivaknapp" data-niva="region">Regioner</button>
</div>
<div class="rakn" id="rakn"></div>
<div id="lista"></div>
</div>
<script>
var DATA = {data};
var FARG = {farger};
var niva = '';

function kort(o) {{
  var lage = o.v >= o.maj ? ['v', 'Vänstermajoritet']
    : (o.h >= o.maj ? ['h', 'Högermajoritet'] : ['o', 'Övriga avgör']);
  var rader = o.rader.map(function (r) {{
    var kl = r.d === null ? 'dim'
      : (Math.abs(r.d) < 1 ? 'traff' : (Math.abs(r.d) >= 2 ? 'miss' : 'mitt'));
    return '<tr><td><span class="pp" style="background:' +
      (FARG[r.p] || '#8892a4') + '"></span>' + r.p + '</td>' +
      '<td class="ta"><strong>' + r.r.toFixed(1) + ' %</strong></td>' +
      '<td class="ta"><strong>' + r.m + '</strong></td>' +
      '<td class="ta dim dolj">' + (r.pp === null ? '–' : r.pp.toFixed(1) + ' %') + '</td>' +
      '<td class="ta dim dolj">' + (r.pm === null ? '–' : r.pm) + '</td>' +
      '<td class="ta ' + kl + '">' + (r.d === null ? '–' : (r.d > 0 ? '+' : '') + r.d.toFixed(1)) + '</td></tr>';
  }}).join('');
  var lokala = o.lokala.map(function (l) {{
    return '<tr class="lokal"><td colspan="1">' + l.p + '</td>' +
      '<td class="ta"><strong>' + l.r.toFixed(1) + ' %</strong></td>' +
      '<td class="ta"><strong>' + l.m + '</strong></td>' +
      '<td class="ta dim dolj" colspan="3">lokalt parti, ingen egen prognos</td></tr>';
  }}).join('');
  var sitt = o.styre ? '<div class="krad sitt' + (o.styre.ja ? ' ja' : '') +
    '"><span class="kp">' + o.styre.p + '</span>' +
    '<span class="km">' + o.styre.m + '</span>' +
    '<span class="kt">' + (o.styre.ja ? 'majoritet' : (o.styre.m - o.maj)) +
    ' · styr i dag</span></div>' : '';
  var koal = sitt + (o.koal || []).map(function (k) {{
    return '<div class="krad' + (k.ja ? ' ja' : '') + '">' +
      '<span class="kp">' + k.p + '</span>' +
      '<span class="km">' + k.m + '</span>' +
      '<span class="kt">' + (k.ja ? 'majoritet' : (k.m - o.maj)) + '</span>' +
      '</div>';
  }}).join('');
  return '<div class="omrade">' +
    '<div class="onamn">' + o.namn +
      '<span class="oniva ' + o.niva + '">' +
      (o.niva === 'region' ? 'Regionfullmäktige' : 'Kommunfullmäktige') +
      '</span>' +
      '<span class="olage ' + lage[0] + '">' + lage[1] + '</span></div>' +
    '<div class="ometa">' + o.tot + ' mandat, ' + o.maj + ' krävs för majoritet · ' +
      'vänster ' + o.v + ', höger ' + o.h + ', övriga ' + o.o +
      (o.mae === null ? '' : ' · prognosens medelfel ' + o.mae.toFixed(2) + ' pe') +
    '</div>' +
    '<table><thead><tr><th>Parti</th><th class="ta">Resultat</th>' +
    '<th class="ta">Mandat</th><th class="ta dolj">Prognos</th>' +
    '<th class="ta dolj">Mandat</th><th class="ta">Diff</th></tr></thead>' +
    '<tbody>' + rader + lokala + '</tbody></table>' +
    (koal ? '<div class="koalrub">Möjliga majoriteter</div>' +
            '<div class="koallista">' + koal + '</div>' : '') +
    '</div>';
}}

function rita() {{
  var q = document.getElementById('sok').value.trim().toLowerCase();
  var träff = DATA.filter(function (o) {{
    return (!niva || o.niva === niva) &&
           (!q || o.namn.toLowerCase().indexOf(q) >= 0);
  }});
  document.getElementById('rakn').textContent =
    träff.length + (träff.length === 1 ? ' område' : ' områden');
  document.getElementById('lista').innerHTML = träff.length
    ? träff.slice(0, 40).map(kort).join('') +
      (träff.length > 40 ? '<div class="tomt">Visar de 40 första. Sök för att smalna av.</div>' : '')
    : '<div class="tomt">Ingen träff.</div>';
}}

document.getElementById('sok').addEventListener('input', rita);
var knappar = document.querySelectorAll('.nivaknapp');
for (var i = 0; i < knappar.length; i++) {{
  knappar[i].addEventListener('click', function () {{
    for (var j = 0; j < knappar.length; j++) knappar[j].classList.remove('on');
    this.classList.add('on');
    niva = this.getAttribute('data-niva');
    rita();
  }});
}}
rita();
</script>
</body></html>"""
