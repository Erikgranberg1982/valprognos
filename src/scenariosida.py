"""Bygger scenariosidan: tänkta utfall för riksdagen och vad de gör med mandaten."""
from __future__ import annotations

import json
from pathlib import Path

import config as cfg
import scenarier


def _mandatstapel(mandat: dict, farger: dict) -> str:
    """Vågrät stapel över kammarens 349 mandat, sorterad vänster till höger."""
    ordning = ["V", "S", "MP", "C", "L", "M", "KD", "SD"]
    ovriga = [p for p in mandat if p not in ordning and mandat[p] > 0]
    bitar = []
    for p in ordning + ovriga:
        n = mandat.get(p, 0)
        if n <= 0:
            continue
        bredd = n / cfg.MANDAT_TOTALT * 100
        f = farger.get(p, "#7B3FA0")
        bitar.append(
            f'<span class="mb" style="width:{bredd:.3f}%;background:{f}" '
            f'data-tip="{p}: {n} mandat"></span>')
    return "".join(bitar)


def skriv(katalog: Path, baslinje, meta: dict) -> Path:
    utfall = scenarier.kor_alla(baslinje)

    farger = dict(cfg.PARTIFARG)
    for u in utfall:
        vp = u["scenario"].valkretsparti
        if vp:
            farger[vp["kod"]] = vp["farg"]

    flikar, paneler = [], []
    for i, u in enumerate(utfall):
        s = u["scenario"]
        aktiv = " on" if i == 0 else ""
        flikar.append(
            f'<button class="sflik{aktiv}" data-s="{s.id}">'
            f'<span class="sn">{i + 1}</span>{s.namn}</button>')
        paneler.append(_panel(u, farger, dold=i > 0))

    html = _MALL.format(
        flikar="".join(flikar),
        paneler="".join(paneler),
        dagar=meta.get("dagar_kvar", ""),
        matningar=meta.get("antal_matningar", 0),
        antal=len(utfall),
    )
    katalog.mkdir(parents=True, exist_ok=True)
    ut = katalog / "scenarier_2026.html"
    ut.write_text(html, encoding="utf-8")
    return ut


def _panel(u: dict, farger: dict, dold: bool) -> str:
    s = u["scenario"]
    bas, nytt = u["mandat_bas"], u["mandat_nytt"]
    rb, rn = u["roster_bas"], u["roster_nytt"]

    # Partitabell: bara de partier som rör sig, plus ett eventuellt nytt parti.
    rader = []
    partier = list(cfg.PARTIER) + [p for p in nytt if p not in cfg.PARTIER]
    for p in partier:
        mb, mn = bas.get(p, 0), nytt.get(p, 0)
        vb, vn = rb.get(p, 0.0), rn.get(p, 0.0)
        if mb == mn and abs(vn - vb) < 0.05:
            continue
        d = mn - mb
        kl = "upp" if d > 0 else ("ned" if d < 0 else "noll")
        vp = s.valkretsparti
        namn = vp["namn"] if (vp and p == vp["kod"]) else cfg.PARTINAMN.get(p, p)
        if p not in cfg.PARTIER:
            rost = f'{vp["andel_i_valkrets"]:.0f} % i Örebro län'
        elif abs(vn - vb) < 0.005:
            rost = f'{vb:.1f} % <span class="of">oförändrat</span>'
        else:
            rost = f'{vb:.1f} → {vn:.1f} %' 
        rader.append(
            f'<tr><td><span class="pp" style="background:{farger.get(p, "#7B3FA0")}">'
            f'</span>{namn}</td>'
            f'<td class="ta">{rost}</td>'
            f'<td class="ta"><strong>{mb} → {mn}</strong></td>'
            f'<td class="ta {kl}">{d:+d}</td></tr>')

    # Koalitioner: visa dem som ändras eller ligger nära majoritet.
    krader = []
    for k in u["koalitioner"]:
        andrad = k["majoritet_fore"] != k["majoritet_efter"]
        d = k["diff"]
        kl = "upp" if d > 0 else ("ned" if d < 0 else "noll")
        maj_f = "★" if k["majoritet_fore"] else "–"
        maj_e = "★" if k["majoritet_efter"] else "–"
        markera = ' class="andrad"' if andrad else ""
        krader.append(
            f'<tr{markera}><td>{k["namn"]}</td>'
            f'<td class="ta">{k["fore"]} <span class="maj">{maj_f}</span></td>'
            f'<td class="ta">{k["efter"]} <span class="maj">{maj_e}</span></td>'
            f'<td class="ta {kl}">{d:+d}</td></tr>')

    vinnare = max(u["koalitioner"], key=lambda k: k["efter"])
    byten = [k for k in u["koalitioner"] if k["majoritet_fore"] != k["majoritet_efter"]]
    if byten:
        sammanfattning = (
            f"{len(byten)} regeringsalternativ byter läge: "
            + ", ".join(
                f'<em>{k["namn"]}</em> '
                + ("når majoritet" if k["majoritet_efter"] else "tappar majoriteten")
                for k in byten) + ".")
    else:
        sammanfattning = ("Inget regeringsalternativ byter läge. "
                          "Mandaten flyttar sig, men majoritetsbilden står kvar.")

    return f'''
<section class="spanel" id="s-{s.id}"{' hidden' if dold else ''}>
  <h2>Frågan</h2>
  <div class="rub">{s.fraga}</div>
  <div class="kort">
    <p class="besk">{s.beskrivning}</p>
  </div>

  <h2>Riksdagen i scenariot</h2>
  <div class="rub">Så skulle mandaten falla</div>
  <div class="kort">
    <div class="stapelrad"><span class="setikett">Prognos</span>
      <div class="stapel">{_mandatstapel(u["mandat_bas"], farger)}</div></div>
    <div class="stapelrad"><span class="setikett">Scenario</span>
      <div class="stapel">{_mandatstapel(u["mandat_nytt"], farger)}</div></div>
    <table class="tab">
      <thead><tr><th>Parti</th><th class="ta">Väljarstöd</th>
      <th class="ta">Mandat</th><th class="ta">Ändring</th></tr></thead>
      <tbody>{"".join(rader)}</tbody>
    </table>
    <p class="fot">Partier som varken tappar väljare eller mandat visas inte.
    Ett parti märkt <em>oförändrat</em> kan ändå tappa mandat: när ett nytt
    parti tar sig över spärren delas samma {cfg.MANDAT_TOTALT} mandat på fler,
    och alla andra späds ut. Mandaten summerar alltid till
    {cfg.MANDAT_TOTALT}.</p>
  </div>

  <h2>Följden</h2>
  <div class="rub">Vad det gör med regeringsunderlagen</div>
  <div class="kort">
    <p class="besk">{sammanfattning}</p>
    <table class="tab">
      <thead><tr><th>Alternativ</th><th class="ta">Prognos</th>
      <th class="ta">Scenario</th><th class="ta">Ändring</th></tr></thead>
      <tbody>{"".join(krader)}</tbody>
    </table>
    <p class="fot">★ betyder minst 175 mandat. Alternativen överlappar och
    summerar inte till hundra procent. Att ett underlag räcker i mandat
    betyder inte att partierna vill regera ihop.</p>
  </div>

  <div class="varn">
    <div class="vk"><div class="vrub">Reservation</div><p>{s.forbehall}</p></div>
    <div class="vk"><div class="vrub">Vad scenariot inte är</div>
    <p>Det här är ingen prognos och ingen sannolikhet. Scenariot svarar på
    frågan <em>om detta händer, vad följer då</em>. Modellens egen prognos
    finns på startsidan.</p></div>
  </div>
</section>'''


_MALL = """<!doctype html><html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Scenarier för riksdagsvalet 2026</title>
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
.w{{max-width:1180px;margin:0 auto;padding:0 24px}}
header{{background:var(--panel);border-bottom:1px solid var(--linje);
padding:26px 0 22px;margin-bottom:26px}}
h1{{font-size:29px;font-weight:800;letter-spacing:-1px;margin:0 0 4px}}
.sub{{color:var(--svag);font-size:14px}}
.tbaka{{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;
font-weight:600;color:var(--korall);text-decoration:none;margin-bottom:12px;
padding:5px 11px 5px 8px;border:1px solid rgba(0,0,0,.12);
border-radius:99px;background:var(--panel);transition:.15s}}
.tbaka:hover{{background:var(--korall);color:#fff;border-color:var(--korall)}}
.flikar{{display:flex;flex-wrap:wrap;gap:9px;margin:20px 0 26px}}
.sflik{{font:inherit;cursor:pointer;border:1.5px solid var(--linje);
border-radius:12px;background:var(--kort);color:var(--text);
padding:11px 17px 11px 13px;display:flex;align-items:center;gap:10px;
font-weight:600;font-size:14px;text-align:left;transition:.15s}}
.sflik:hover{{border-color:var(--korall)}}
.sflik.on{{border-color:var(--korall);border-width:2px;padding:10px 16px 10px 12px;
background:var(--korall-ljus)}}
.sn{{flex:none;width:23px;height:23px;border-radius:50%;background:var(--korall);
color:#fff;font-weight:800;font-size:12px;display:flex;align-items:center;
justify-content:center}}
h2{{font-size:11.5px;text-transform:uppercase;letter-spacing:1.5px;
color:var(--svag);font-weight:700;margin:34px 0 3px}}
.rub{{font-size:23px;font-weight:700;letter-spacing:-.6px;margin:0 0 16px}}
.kort{{background:var(--kort);border:1px solid var(--linje);border-radius:16px;
padding:24px;box-shadow:var(--skugga)}}
.besk{{margin:0 0 4px;font-size:14px;line-height:1.7;max-width:780px}}
.besk em{{font-style:normal;font-weight:700}}
.stapelrad{{display:flex;align-items:center;gap:13px;margin-bottom:9px}}
.setikett{{flex:none;width:74px;font-size:11px;text-transform:uppercase;
letter-spacing:1px;font-weight:700;color:var(--svag)}}
.stapel{{flex:1;display:flex;height:27px;border-radius:6px;overflow:hidden;
background:var(--panel)}}
.mb{{height:100%;cursor:help;transition:.1s}}
.mb:hover{{filter:brightness(1.15)}}
.tab{{width:100%;border-collapse:collapse;margin-top:18px;font-size:13.5px}}
.tab th{{text-align:left;font-size:10.5px;text-transform:uppercase;
letter-spacing:1px;color:var(--svag);font-weight:700;padding:0 9px 7px 0;
border-bottom:1px solid var(--linje)}}
.tab td{{padding:9px 9px 9px 0;border-bottom:1px solid var(--linje)}}
.tab tr:last-child td{{border-bottom:none}}
.ta{{text-align:right;font-variant-numeric:tabular-nums}}
.upp{{color:var(--gron);font-weight:700}}
.ned{{color:var(--korall);font-weight:700}}
.noll{{color:var(--svag)}}
.maj{{font-size:11px;color:var(--svag);margin-left:3px}}
tr.andrad td{{background:var(--korall-ljus)}}
.pp{{display:inline-block;width:10px;height:10px;border-radius:3px;
margin-right:8px;vertical-align:baseline}}
.fot{{margin:14px 0 0;font-size:12px;color:var(--svag);line-height:1.6}}
.fot em{{font-style:normal;font-weight:700;color:var(--text)}}
.of{{font-size:11px;color:var(--svag);font-weight:600}}
.varn{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
gap:13px;margin-top:22px}}
.vk{{background:var(--panel);border-radius:12px;padding:16px 18px}}
.vrub{{font-size:11px;text-transform:uppercase;letter-spacing:1px;font-weight:700;
color:var(--korall);margin-bottom:5px}}
.vk p{{margin:0;font-size:12.5px;color:var(--svag);line-height:1.65}}
.vk em{{font-style:normal;font-weight:600;color:var(--text)}}
#tip{{position:fixed;z-index:99;background:var(--text);color:var(--bg);
font-size:12px;font-weight:600;padding:5px 10px;border-radius:7px;
pointer-events:none;opacity:0;transition:opacity .08s}}
@media(max-width:640px){{
  .setikett{{width:56px;font-size:10px}}
  .sflik{{flex:1 1 100%}}
  .tab{{font-size:12.5px}}
}}
</style></head><body>
<header><div class="w">
<a class="tbaka" href="index.html"><span>&#8592;</span> Tillbaka till prognosen</a>
<h1>Scenarier för riksdagsvalet</h1>
<div class="sub">{antal} tänkta utfall · {dagar} dagar till valdagen ·
{matningar} mätningar i modellen</div>
</div></header>
<div class="w">
<div class="flikar">{flikar}</div>
{paneler}

<h2>Om sidan</h2>
<div class="rub">Så räknas ett scenario</div>
<div class="kort">
  <p class="besk">Varje scenario utgår från modellens viktade snitt och flyttar
  väljarstöd mellan partier. Rösterna uppstår inte ur tomma intet: det ett parti
  vinner tas från andra, så förflyttningen summerar till noll. Mandaten fördelas
  därefter med jämkade uddatalsmetoden, samma metod som i huvudprognosen och i
  det verkliga valet.</p>
  <p class="besk">Scenarierna är valda för att de sitter nära en tröskel, där
  små förändringar i väljarstöd ger stora utslag i mandat. De är inga
  prognoser och har ingen sannolikhet knuten till sig.</p>
</div>
</div>
<div id="tip"></div>
<script>
var flikar = document.querySelectorAll('.sflik');
for (var i = 0; i < flikar.length; i++) {{
  flikar[i].addEventListener('click', function () {{
    var id = this.getAttribute('data-s');
    for (var j = 0; j < flikar.length; j++) flikar[j].classList.remove('on');
    this.classList.add('on');
    var paneler = document.querySelectorAll('.spanel');
    for (var k = 0; k < paneler.length; k++) {{
      paneler[k].hidden = (paneler[k].id !== 's-' + id);
    }}
    location.hash = id;
  }});
}}

/* Egen tooltip, eftersom webbläsarens title dröjer ungefär en sekund. */
var tip = document.getElementById('tip');
document.addEventListener('mouseover', function (e) {{
  var t = e.target.closest('[data-tip]');
  if (!t) return;
  tip.textContent = t.getAttribute('data-tip');
  tip.style.opacity = '1';
}});
document.addEventListener('mousemove', function (e) {{
  if (tip.style.opacity !== '1') return;
  var x = e.clientX + 13, y = e.clientY - 32;
  if (x + tip.offsetWidth > window.innerWidth - 8)
    x = e.clientX - tip.offsetWidth - 13;
  tip.style.left = x + 'px';
  tip.style.top = Math.max(4, y) + 'px';
}});
document.addEventListener('mouseout', function (e) {{
  if (e.target.closest('[data-tip]')) tip.style.opacity = '0';
}});

if (location.hash) {{
  var m = document.querySelector('.sflik[data-s="' + location.hash.slice(1) + '"]');
  if (m) m.click();
}}
</script>
</body></html>"""
