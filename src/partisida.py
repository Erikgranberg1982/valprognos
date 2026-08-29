"""Partisida på riksdagsnivå: trend, mandat, valkretsar och kandidater.

Samlar allt som gäller ett parti på ett ställe. Huvudsidan visar partierna
sida vid sida, men den som vill följa ett enskilt parti behöver se dess trend,
var mandaten hamnar geografiskt och vilka personer som väntas ta dem.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import config as cfg

ROT = Path(__file__).resolve().parent.parent

METOD = {
    "historisk_valkrets_2022": ("Satt här 2022", "sakert"),
    "hemvalkrets_2026": ("Bor i valkretsen", "sakert"),
    "dubbelvalsavveckling": ("Tog ledig plats", "medel"),
    "listordning": ("Listordning", "medel"),
}


def _kandidater() -> pd.DataFrame:
    for fil in (ROT / "output" / "kandidatprognos_riksdag.csv",
                ROT / "data" / "kandidater" / "kandidatprognos_riksdag.csv.gz"):
        if fil.exists():
            try:
                return pd.read_csv(fil, dtype=str)
            except Exception:
                continue
    return pd.DataFrame()


def _bygg_partidata(sammanfattning: pd.DataFrame, trend: pd.DataFrame,
                    kandidater: pd.DataFrame) -> dict:
    """Samlar allt per parti i en struktur som sidan kan rendera."""
    ut = {}
    for _, rad in sammanfattning.iterrows():
        parti = rad["parti"]
        kand = kandidater[kandidater["parti"] == parti].copy() \
            if not kandidater.empty else pd.DataFrame()

        valkretsar = []
        if not kand.empty:
            kand["ord"] = pd.to_numeric(kand["ordning"], errors="coerce")
            for vk, grupp in kand.groupby("valkretsnamn", sort=True):
                namn = []
                for _, k in grupp.sort_values("ord").iterrows():
                    txt, niv = METOD.get(k["kandidatval_metod"],
                                         (k["kandidatval_metod"], "medel"))
                    varning = str(k.get("listval_varning") or "").strip()
                    uppgift = str(k.get("valsedelsuppgift") or "").strip()
                    if not uppgift or uppgift == "nan":
                        alder = k.get("alder_pa_valdagen")
                        bitar = []
                        if pd.notna(alder) and str(alder).strip():
                            bitar.append(f"{int(float(alder))} år")
                        ort = str(k.get("folkbokforingskommun") or "").strip()
                        if ort and ort != "nan":
                            bitar.append(ort)
                        uppgift = ", ".join(bitar)
                    namn.append({
                        "n": str(k["namn"]),
                        "u": uppgift,
                        "p": int(k["ord"]) if pd.notna(k["ord"]) else 0,
                        "l": str(k.get("listbeteckning") or ""),
                        "m": txt,
                        "niva": niv,
                        "v": varning if varning and varning != "nan" else None,
                    })
                valkretsar.append({"vk": str(vk), "mandat": len(grupp),
                                   "kandidater": namn})
            valkretsar.sort(key=lambda x: (-x["mandat"], x["vk"]))

        ut[parti] = {
            "namn": cfg.PARTINAMN.get(parti, parti),
            "farg": cfg.PARTIFARG.get(parti, "#888"),
            "prognos": round(float(rad["prognos"]), 1),
            "p10": round(float(rad["p10"]), 1),
            "p90": round(float(rad["p90"]), 1),
            "forra": round(float(rad["forra_stod"]), 1) if pd.notna(rad.get("forra_stod")) else None,
            "diff": round(float(rad["forandring"]), 1) if pd.notna(rad.get("forandring")) else None,
            "mandat": int(rad["mandat_median"]),
            "mandat_p10": int(rad["mandat_p10"]),
            "mandat_p90": int(rad["mandat_p90"]),
            "forra_mandat": int(rad["forra_mandat"]) if pd.notna(rad.get("forra_mandat")) else None,
            "mandatdiff": int(rad["mandatforandring"]) if pd.notna(rad.get("mandatforandring")) else None,
            "over_sparr": round(float(rad["sannolikhet_over_sparr"]), 4),
            "trend": [round(float(v), 2) for v in trend[parti]] if parti in trend.columns else [],
            "valkretsar": valkretsar,
            "antal_kandidater": int(len(kand)) if not kand.empty else 0,
        }
    return ut


def skriv(katalog: Path, sammanfattning: pd.DataFrame,
          trend: pd.DataFrame, meta: dict) -> Path | None:
    kandidater = _kandidater()
    data = _bygg_partidata(sammanfattning, trend, kandidater)
    if not data:
        return None

    ordning = sorted(data, key=lambda p: -data[p]["prognos"])
    flikar = "".join(
        f'<button class="pflik" data-p="{p}" style="--f:{data[p]["farg"]}">'
        f'<span class="pk">{p}</span>'
        f'<span class="pv">{data[p]["prognos"]:.1f}%</span></button>'
        for p in ordning)

    datum = [d.strftime("%Y-%m-%d") for d in trend["datum"]] if "datum" in trend else []

    html = _MALL.format(
        flikar=flikar,
        data=json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        datum=json.dumps(datum),
        forsta=ordning[0],
        dagar=meta.get("dagar_kvar", 0),
        matningar=meta.get("antal_matningar", 0),
        genererad=meta.get("genererad", ""),
    )
    katalog.mkdir(parents=True, exist_ok=True)
    ut = katalog / "partier_2026.html"
    ut.write_text(html, encoding="utf-8")
    return ut


_MALL = """<!doctype html><html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Partierna i riksdagsvalet 2026</title>
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
.flikar{{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0 26px}}
.pflik{{font:inherit;cursor:pointer;border:1.5px solid var(--linje);
border-radius:12px;background:var(--kort);color:var(--text);padding:9px 15px;
display:flex;flex-direction:column;align-items:flex-start;min-width:78px}}
.pflik:hover{{border-color:var(--f)}}
.pflik.on{{border-color:var(--f);border-width:2px;padding:8px 14px}}
.pk{{font-weight:800;font-size:14px;color:var(--f)}}
.pv{{font-size:12px;color:var(--svag);font-variant-numeric:tabular-nums}}
h2{{font-size:11.5px;text-transform:uppercase;letter-spacing:1.5px;
color:var(--svag);font-weight:700;margin:34px 0 3px}}
.rub{{font-size:23px;font-weight:700;letter-spacing:-.6px;margin:0 0 16px}}
.kort{{background:var(--kort);border:1px solid var(--linje);border-radius:16px;
padding:24px;box-shadow:var(--skugga)}}
.tal{{display:flex;flex-wrap:wrap;gap:34px;margin-bottom:6px}}
.tl .n{{font-size:38px;font-weight:800;letter-spacing:-1.6px;line-height:1.1}}
.tl .e{{font-size:12.5px;color:var(--svag)}}
.d{{font-size:14px;font-weight:700;margin-left:7px}}
.d.upp{{color:var(--gron)}}.d.ned{{color:var(--korall)}}
canvas{{width:100%;height:auto;display:block}}
.vkrad{{display:grid;grid-template-columns:230px 1fr;gap:16px;padding:14px 0;
border-top:1px solid var(--linje)}}
.vknamn{{font-weight:700;font-size:14px}}
.vkmandat{{font-size:12px;color:var(--svag)}}
.knamn{{display:flex;flex-wrap:wrap;gap:6px}}
.kb{{display:inline-flex;align-items:baseline;gap:6px;background:var(--panel);
border-radius:7px;padding:4px 10px 4px 7px;font-size:12.5px;cursor:help}}
.kb:hover{{background:var(--korall-ljus);color:var(--korall-mork)}}
.kn{{font-size:10px;font-weight:700;color:var(--svag);min-width:13px;text-align:right}}
.km{{font-size:10px;padding:1px 7px;border-radius:28px;margin-left:2px}}
.km.sakert{{background:rgba(125,186,116,.2);color:#3f7a36}}
.km.medel{{background:var(--linje);color:var(--svag)}}
.notis{{background:var(--panel);border-left:3px solid var(--korall);
padding:14px 18px;border-radius:0 8px 8px 0;font-size:13px;color:var(--svag);
margin-top:16px;max-width:900px;line-height:1.65}}
.steg{{display:flex;gap:14px;margin-bottom:13px;align-items:flex-start}}
.snr{{flex:none;width:27px;height:27px;border-radius:50%;background:var(--korall);
color:#fff;font-weight:800;font-size:13px;display:flex;align-items:center;
justify-content:center}}
.steg strong{{display:block;font-size:14px;margin-bottom:1px}}
.steg p{{margin:0;font-size:13px;color:var(--svag);max-width:700px}}
.varn{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));
gap:13px;margin-top:20px}}
.vk{{background:var(--panel);border-radius:12px;padding:15px 17px}}
.vrub{{font-size:11px;text-transform:uppercase;letter-spacing:1px;font-weight:700;
color:var(--korall);margin-bottom:5px}}
.vk p{{margin:0;font-size:12.5px;color:var(--svag);line-height:1.6}}
</style></head><body>
<header><div class="w"><h1>Partierna i riksdagsvalet 2026</h1>
<div class="sub">{dagar} dagar till valdagen · {matningar} mätningar i modellen</div>
</div></header>
<div class="w">
<div class="flikar">{flikar}</div>
<div id="innehall"></div>

<h2>Metod</h2>
<div class="rub">Så tas prognosen fram</div>
<div class="kort">
  <div class="steg"><div class="snr">1</div><div><strong>Partiets stöd</strong>
  <p>Opinionsmätningar viktas efter institutets kvalitet, urvalsstorlek och
  färskhet, justeras för husfaktorer och körs genom 40 000 simulerade
  valutfall.</p></div></div>
  <div class="steg"><div class="snr">2</div><div><strong>Mandat per valkrets</strong>
  <p>Partiets riksmandat fördelas på de 29 valkretsarna med partiets egen
  röstfördelning 2022, skalad med dagens rikstrend. Starka valkretsar får
  mandat först.</p></div></div>
  <div class="steg"><div class="snr">3</div><div><strong>Vem som tar mandatet</strong>
  <p>Varje valkrets fylls uppifrån och ned i listordning. En kandidat som blir
  vald i flera valkretsar behåller en plats och de övriga går till nästa namn
  på listan, vilket motsvarar vallagens dubbelvalsavveckling.</p></div></div>

  <div class="varn">
    <div class="vk"><div class="vrub">Personröster ingår inte</div>
    <p>En kandidat med minst fem procent personröster går före listan. Det går
    inte att förutse, så prognosen bygger enbart på listordning. Enskilda namn
    kan därför bytas ut mot andra på samma lista.</p></div>

    <div class="vk"><div class="vrub">Var toppnamn tar plats</div>
    <p>Partiledare står ofta först på trettio till sextio listor samtidigt.
    Vallagen ger platsen där jämförelsetalet är högst, vilket kräver
    rösträkning. Modellen använder valkretsen personen satt i 2022, sedan
    hemkommunen.</p></div>

    <div class="vk"><div class="vrub">Flera listor per parti</div>
    <p>Ett parti kan ha både en rikstäckande lista och en för länet. Vilken
    väljarna använder är okänt före valet. Listor märkta osäker lista är valda
    på antagandet att den lokala används.</p></div>

    <div class="vk"><div class="vrub">Träffsäkerhet</div>
    <p>Ett test mot 2022 ger rätt valkrets för 96 procent av de sittande
    ledamöter som behåller sin plats. Riksdagsprognosen har ett medelabsolutfel
    på 0,7 procentenheter nära valdagen.</p></div>
  </div>
</div>

<div class="notis">Prognosen visar det mest sannolika utfallet, inte ett facit.
Mandatspannen anger var åtta av tio simuleringar hamnar. Genererad
{genererad}.</div>
</div>
<script>
var D={data}, DATUM={datum}, valt='{forsta}';

function diff(v,enhet){{
  if(v===null||v===undefined) return '';
  var t=(v>0?'+':'')+v.toFixed(enhet==='m'?0:1);
  return '<span class="d '+(v>0?'upp':'ned')+'">'+t+'</span>';
}}

function rita(p){{
  var d=D[p];
  var vk=d.valkretsar.map(function(v){{
    var namn=v.kandidater.map(function(k){{
      var titel=k.n+(k.u?'\\n'+k.u:'')+
                '\\nPlats '+k.p+' på listan '+k.l+
                '\\n'+k.m+(k.v?'\\n'+k.v:'');
      return '<span class="kb" title="'+titel.replace(/"/g,'&quot;')+'">'+
             '<span class="kn">'+k.p+'</span>'+k.n+
             '<span class="km '+k.niva+'">'+k.m+'</span></span>';
    }}).join('');
    return '<div class="vkrad"><div><div class="vknamn">'+v.vk+'</div>'+
           '<div class="vkmandat">'+v.mandat+(v.mandat===1?' mandat':' mandat')+
           '</div></div><div class="knamn">'+namn+'</div></div>';
  }}).join('');

  document.getElementById('innehall').innerHTML =
    '<h2>'+p+'</h2><div class="rub">'+d.namn+'</div>'+
    '<div class="kort"><div class="tal">'+
      '<div class="tl"><div class="n" style="color:'+d.farg+'">'+
        d.prognos.toFixed(1)+'%'+diff(d.diff)+'</div>'+
        '<div class="e">av rösterna, spann '+d.p10.toFixed(1)+'–'+d.p90.toFixed(1)+'</div></div>'+
      '<div class="tl"><div class="n">'+d.mandat+diff(d.mandatdiff,'m')+'</div>'+
        '<div class="e">mandat, spann '+d.mandat_p10+'–'+d.mandat_p90+'</div></div>'+
      '<div class="tl"><div class="n">'+d.valkretsar.length+'</div>'+
        '<div class="e">valkretsar med mandat</div></div>'+
    '</div>'+
    '<canvas id="tg" height="230"></canvas></div>'+
    '<h2>Var mandaten hamnar</h2>'+
    '<div class="rub">Valkretsar och vilka som tar platserna</div>'+
    '<div class="kort">'+vk+'</div>';

  ritaTrend(p);
}}

function ritaTrend(p){{
  var c=document.getElementById('tg'); if(!c) return;
  var d=D[p], v=d.trend; if(!v.length) return;
  var dpr=window.devicePixelRatio||1, W=c.clientWidth, H=230;
  c.width=W*dpr; c.height=H*dpr;
  var g=c.getContext('2d'); g.setTransform(dpr,0,0,dpr,0,0); g.clearRect(0,0,W,H);
  var st=getComputedStyle(document.documentElement);
  var lin=st.getPropertyValue('--linje').trim(), sv=st.getPropertyValue('--svag').trim();
  var mL=40,mR=16,mT=14,mB=26, bw=W-mL-mR, bh=H-mT-mB, n=v.length;
  var max=Math.ceil(Math.max.apply(null,v)/5)*5||5;
  var x=function(i){{return mL+(n<2?bw/2:i/(n-1)*bw)}};
  var y=function(t){{return mT+bh-t/max*bh}};
  g.strokeStyle=lin; g.fillStyle=sv; g.lineWidth=1;
  g.font="11px 'Work Sans',sans-serif";
  for(var t=0;t<=max;t+=5){{
    g.beginPath(); g.moveTo(mL,y(t)); g.lineTo(mL+bw,y(t)); g.stroke();
    g.textAlign='right'; g.textBaseline='middle'; g.fillText(t+'%',mL-7,y(t));
  }}
  g.textAlign='center'; g.textBaseline='top';
  var steg=Math.max(1,Math.floor(n/6));
  for(var i=0;i<n;i+=steg) if(DATUM[i]) g.fillText(DATUM[i].slice(2,7),x(i),mT+bh+8);
  g.strokeStyle=d.farg; g.lineWidth=2.4; g.lineJoin='round'; g.beginPath();
  v.forEach(function(t,i){{ i?g.lineTo(x(i),y(t)):g.moveTo(x(i),y(t)) }});
  g.stroke();
}}

document.querySelectorAll('.pflik').forEach(function(b){{
  b.addEventListener('click',function(){{
    document.querySelectorAll('.pflik').forEach(function(x){{x.classList.remove('on')}});
    b.classList.add('on'); valt=b.dataset.p; rita(valt);
  }});
}});
document.querySelector('.pflik[data-p="{forsta}"]').classList.add('on');
rita(valt);
var om; window.addEventListener('resize',function(){{
  clearTimeout(om); om=setTimeout(function(){{ritaTrend(valt)}},150);
}});
</script></body></html>"""
