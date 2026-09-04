"""Fristående sida med de prognosticerade riksdagsledamöterna.

346 namn är för många för att rymmas i huvudsidans detaljvyer, så de får en
egen sida med sökning och partifilter. Varje rad visar varför personen hamnat
i just den valkretsen.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

import config as cfg

ROT = Path(__file__).resolve().parent.parent

METOD = {
    # Etiketten säger vad som är värt att veta. De flesta kandidater står på
    # en enda lista och tar platsen i listordning, vilket inte behöver märkas
    # ut. Bara den som står på flera listor har behövt placeras.
    "listordning": ("", "sakert"),
    "historisk_valkrets_2022": ("Står på flera listor", "medel"),
    "hemvalkrets_2026": ("Står på flera listor", "medel"),
    "dubbelvalsavveckling": ("Ärvde ledig plats", "medel"),
}


def _las() -> pd.DataFrame:
    for fil in (ROT / "output" / "kandidatprognos_riksdag.csv",
                ROT / "data" / "kandidater" / "kandidatprognos_riksdag.csv.gz"):
        if fil.exists():
            try:
                return pd.read_csv(fil, dtype=str)
            except Exception:
                continue
    return pd.DataFrame()


def _seo_taggar(antal: int) -> str:
    import seo
    titel = f"Riksdagen 2026: alla {antal} prognosticerade ledamöter"
    besk = (f"Sökbar lista över de {antal} personer som enligt prognosen tar "
            "plats i riksdagen efter valet 2026, med parti, valkrets, ålder "
            "och plats på valsedeln.")
    return seo.metataggar(titel, besk, "ledamoter_2026.html")


def skriv(katalog: Path) -> Path | None:
    """Skriver sidan och en CSV med samma innehåll."""
    df = _las()
    if df.empty:
        return None

    df = df.copy()
    df["ord"] = pd.to_numeric(df["ordning"], errors="coerce")
    df = df.sort_values(["valkretsnamn", "parti", "ord"])

    rader = []
    for _, r in df.iterrows():
        txt, niv = METOD.get(r["kandidatval_metod"], (r["kandidatval_metod"], "medel"))
        alder = r.get("alder_pa_valdagen")
        alder = f"{int(float(alder))}" if pd.notna(alder) and str(alder).strip() else ""
        uppgift = str(r.get("valsedelsuppgift") or "").strip()
        if uppgift == "nan":
            uppgift = ""
        varning = str(r.get("listval_varning") or "").strip()
        varn = ('<span class="v" title="' + varning.replace('"', "&quot;")[:300] +
                '">osäker lista</span>') if varning and varning != "nan" else ""
        ort = r.get("folkbokforingskommun")
        rader.append(
            f'<tr data-p="{r["parti"]}">'
            f'<td class="n" title="{uppgift}">{r["namn"]}'
            f'{chr(10) if False else ""}'
            + (f'<div class="upp">{uppgift}</div>' if uppgift else '') + '</td>'
            f'<td><span class="pp p{r["parti"]}">{r["parti"]}</span></td>'
            f'<td>{r["valkretsnamn"]}</td>'
            f'<td class="t">{alder}</td>'
            f'<td class="o">{ort if pd.notna(ort) else ""}</td>'
            f'<td class="t">{int(r["ord"])}</td>'
            f'<td class="l">{r["listbeteckning"]}</td>'
            f'<td>' + (f'<span class="m {niv}">{txt}</span>' if txt else '')
            + f'{varn}</td></tr>')

    farg = "\n".join(f".p{p}{{background:{c}}}" for p, c in cfg.PARTIFARG.items())
    ordning = df.groupby("parti").size().sort_values(ascending=False).index
    knappar = "".join(f'<button data-f="{p}">{p}</button>' for p in ordning)

    html = _MALL.format(antal=len(df),
        ga=cfg.google_analytics(),
        seo_taggar=_seo_taggar(len(df)),
        valkretsar=df["valkretsnamn"].nunique(),
                        farg=farg, knappar=knappar, rader="".join(rader))

    katalog.mkdir(parents=True, exist_ok=True)
    ut = katalog / "ledamoter_2026.html"
    ut.write_text(html, encoding="utf-8")

    kol = ["namn", "parti", "valkretsnamn", "alder_pa_valdagen",
           "folkbokforingskommun", "ordning", "listbeteckning",
           "kandidatval_metod", "prioritetsskäl"]
    csv = df[[k for k in kol if k in df.columns]].copy()
    csv.columns = ["namn", "parti", "valkrets", "alder", "bor_i", "listplats",
                   "lista", "metod", "skal"][:len(csv.columns)]
    csv.to_csv(katalog / "ledamoter_2026.csv", index=False)
    return ut


_MALL = '''<!doctype html><html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Riksdagen 2026 – prognosticerade ledamöter</title>
{seo_taggar}
{ga}
<link href="https://fonts.googleapis.com/css2?family=Work+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
:root{{--bg:#fff;--text:#003D63;--svag:#69727D;--linje:#E3E8F0;--panel:#F1F3FA;
--korall:#EF7466;--korall-ljus:#FBE4E0}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0E1621;--text:#EAF0F7;--svag:#93A2B5;
--linje:#22303F;--panel:#16202E;--korall-ljus:#3A2320}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--text);
font:14px/1.55 'Work Sans',-apple-system,sans-serif;padding:28px 22px 70px}}
.w{{max-width:1240px;margin:0 auto}}
h1{{font-size:27px;font-weight:800;letter-spacing:-.8px;margin:0 0 4px}}
.sub{{color:var(--svag);font-size:14px;margin-bottom:20px}}
.styr{{display:flex;flex-wrap:wrap;gap:9px;align-items:center;margin-bottom:16px}}
input{{font:inherit;padding:8px 15px;border:1px solid var(--linje);border-radius:28px;
background:var(--bg);color:var(--text);min-width:230px}}
button{{font:inherit;font-size:12.5px;font-weight:700;padding:6px 14px;cursor:pointer;
border:1px solid var(--linje);border-radius:28px;background:var(--bg);color:var(--svag)}}
button:hover{{border-color:var(--korall);color:var(--korall)}}
button.on{{background:var(--korall);color:#fff;border-color:var(--korall)}}
table{{width:100%;border-collapse:collapse}}
th{{text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.9px;
color:var(--svag);padding:11px 9px;background:var(--panel);position:sticky;top:0}}
td{{padding:8px 9px;border-top:1px solid var(--linje);vertical-align:top}}
tr:hover td{{background:var(--panel)}}
.n{{font-weight:600;white-space:nowrap}}
.upp{{font-weight:400;font-size:11.5px;color:var(--svag);white-space:normal;
max-width:230px;margin-top:1px}}
.t{{text-align:right;font-variant-numeric:tabular-nums;color:var(--svag)}}
.o,.l{{color:var(--svag);font-size:12.5px}}
.pp{{display:inline-block;min-width:30px;text-align:center;padding:2px 7px;
border-radius:5px;font-size:11px;font-weight:800;color:#fff}}
{farg}
.pSD{{color:#333}}.pMP{{color:#1a3d0a}}
.m{{display:inline-block;font-size:11px;font-weight:600;padding:2px 9px;
border-radius:28px;white-space:nowrap}}
.m.sakert{{background:rgba(125,186,116,.2);color:#3f7a36}}
.m.medel{{background:var(--panel);color:var(--svag)}}
.v{{display:block;margin-top:3px;font-size:10.5px;color:var(--korall);cursor:help}}
.tbaka{{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;
font-weight:600;color:var(--korall);text-decoration:none;margin-bottom:12px;
padding:5px 11px 5px 8px;border:1px solid var(--kant,rgba(0,0,0,.12));
border-radius:99px;background:var(--panel);transition:.15s}}
.tbaka:hover{{background:var(--korall);color:#fff;border-color:var(--korall)}}
.rakn{{color:var(--svag);font-size:13px;margin:10px 0}}
.not{{margin-top:26px;padding:14px 17px;background:var(--panel);
border-left:3px solid var(--korall);border-radius:0 8px 8px 0;
font-size:12.5px;color:var(--svag);max-width:860px;line-height:1.65}}
</style></head><body><div class="w">
<a class="tbaka" href="index.html"><span>&#8592;</span> Tillbaka till prognosen</a>
<h1>Riksdagen 2026</h1>
<div class="sub">{antal} prognosticerade ledamöter i {valkretsar} valkretsar</div>
<div class="styr">
  <input id="s" type="search" placeholder="Sök namn, valkrets eller ort...">
  <button data-f="" class="on">Alla</button>{knappar}
</div>
<div class="rakn" id="r"></div>
<table><thead><tr><th>Namn</th><th>Parti</th><th>Valkrets</th><th>Ålder</th>
<th>Bor i</th><th>Plats</th><th>Lista</th><th>Varför</th></tr></thead>
<tbody id="k">{rader}</tbody></table>
<div class="not"><strong>Om prognosen.</strong> Mandaten fördelas först per parti
och valkrets, sedan fylls varje valkrets uppifrån och ned i listordning. En
kandidat som blir vald i flera valkretsar behåller en plats och de övriga går
till nästa namn på listan, vilket motsvarar vallagens dubbelvalsavveckling.
Personröster kan flytta namn förbi varandra och ingår inte.
Ett backtest mot 2022 ger rätt valkrets för 96 procent av de sittande ledamöter
som behåller sin plats.</div>
</div>
<script>
var s=document.getElementById('s'),k=document.getElementById('k'),
    r=document.getElementById('r'),f='';
function upd(){{
  var q=s.value.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,''),n=0;
  [].forEach.call(k.rows,function(row){{
    var txt=row.textContent.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');
    var ok=(!f||row.dataset.p===f)&&(!q||txt.indexOf(q)>=0);
    row.hidden=!ok; if(ok)n++;
  }});
  r.textContent=n+(n===1?' ledamot':' ledamöter');
}}
s.addEventListener('input',upd);
[].forEach.call(document.querySelectorAll('button'),function(b){{
  b.addEventListener('click',function(){{
    document.querySelectorAll('button').forEach(function(x){{x.classList.remove('on')}});
    b.classList.add('on'); f=b.dataset.f; upd();
  }});
}});
upd();
</script></body></html>'''
