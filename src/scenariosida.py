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


def skriv(katalog: Path, baslinje, meta: dict, matningar=None) -> Path:
    utfall = scenarier.kor_alla(baslinje, matningar, meta.get("dagar_kvar"))

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
        ga=cfg.google_analytics(),
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


def _spurtunderlag(u: dict, farger: dict) -> str:
    """Visar tidigare valspurter och hur de läggs på dagens läge."""
    info = u["scenario"].spurtdata
    if not info:
        return ""

    val = info["val"]
    flera = len(val) > 1
    dk = info["dagar_kvar"]

    # Valen ligger på olika avstånd från valdagen, vilket måste synas i
    # rubriken: 2010 års siffra är från 66 dagar före valet, 2006 års från 2.
    kolumner = ""
    for v in val:
        if v.get("enskild_matning"):
            inst = v.get("institut")
            varning = (f'En enda mätning från {inst}, inte en sammanvägning: '
                       f'bär både slumpfel och {inst}s egen husfaktor.'
                       if inst else
                       'Enskild mätning, inte en sammanvägning över flera '
                       'institut.')
            kolumner += (f'<th class="ta" data-tip="{v["referenstext"]}, '
                         f'{v["dagar_fore_val"]} dagar före valet. {varning}">'
                         f'{v["ar"]}<span class="ast">*</span></th>')
        else:
            kolumner += (f'<th class="ta" data-tip="Sammanvägning av '
                         f'{v["antal_matningar"]} mätningar {v["referensdatum"]}, '
                         f'{dk} dagar före valet.">{v["ar"]}</th>')
    snittkol = '<th class="ta">Snitt</th>' if flera else ""

    rader = []
    for p in cfg.PARTIER:
        celler = []
        for v in val:
            if p not in v["spurt"]:
                celler.append('<td class="ta noll" data-tip="Partiet '
                              'redovisades inte separat detta val">–</td>')
                continue
            x = v["spurt"][p]
            kl = "upp" if x > 0.05 else ("ned" if x < -0.05 else "noll")
            celler.append(f'<td class="ta {kl}">{x:+.2f}</td>')
        if flera:
            x = info["spurt"][p]
            kl = "upp" if x > 0.05 else ("ned" if x < -0.05 else "noll")
            celler.append(f'<td class="ta {kl}"><strong>{x:+.2f}</strong></td>')

        # Markera partier där valen pekar åt olika håll.
        varden = [v["spurt"][p] for v in val if p in v["spurt"]]
        oense = flera and len(varden) > 1 and p not in info["eniga_partier"]
        markering = ' class="oense"' if oense else ""
        rader.append(
            f'<tr{markering}><td><span class="pp" '
            f'style="background:{cfg.PARTIFARG[p]}"></span>{cfg.PARTINAMN[p]}'
            + ('<span class="flagga" data-tip="Valen pekar åt olika håll">≠</span>'
               if oense else "") + '</td>'
            + "".join(celler)
            + f'<td class="ta">{u["roster_bas"][p]:.1f}</td>'
              f'<td class="ta"><strong>{u["roster_nytt"][p]:.1f}</strong></td></tr>')

    def _lista(namn):
        """En, två eller flera: 'A', 'A och B', 'A, B och C'."""
        namn = [str(x) for x in namn]
        if len(namn) <= 1:
            return "".join(namn)
        return ", ".join(namn[:-1]) + " och " + namn[-1]

    egna = [v for v in val if not v.get("enskild_matning")]
    lanade = [v for v in val if v.get("enskild_matning")]

    if egna:
        egen_txt = (
            " För " + _lista([v["ar"] for v in egna]) +
            f" jämförs modellens egen sammanvägning {dk} dagar före valdagen, "
            "alltså exakt samma avstånd som i dag.")
    else:
        egen_txt = ""

    if lanade:
        bitar = ", ".join(
            f'{v["ar"]} från {v["referenstext"][0].lower() + v["referenstext"][1:]}, '
            f'{v["dagar_fore_val"]} dagar före valet'
            for v in lanade)
        egen_txt += (
            f" För {_lista([v['ar'] for v in lanade])} saknar modellen "
            "mätningar och siffran kommer i stället från en enskild mätning "
            f"hämtad för hand: {bitar}.")
        med_inst = [v for v in lanade if v.get("institut")]
        instdel = ""
        if med_inst:
            instdel = (
                " " + " ".join(
                    f'{v["ar"]} års tal kommer från en enda mätning av '
                    f'{v["institut"]}, vilket är en svagare grund än en '
                    f'sammanvägning: det bär både slumpfelet i en enskild '
                    f'mätning och {v["institut"]}s egen husfaktor.'
                    for v in med_inst))
        lanad_txt = (
            " Avstånden skiljer sig alltså åt, vilket är en verklig svaghet: "
            "2010 års siffra beskriver ett helt kvartal, medan 2006 och 2014 "
            "ligger nära vårt eget avstånd. Kolumner märkta med <em>*</em> är "
            "enskilda mätningar, inte sammanvägningar." + instdel)
    else:
        lanad_txt = ""

    if flera:
        ense = info["eniga_partier"]
        slutkommentar = (
            f'Bara {len(ense)} av {len(cfg.PARTIER)} partier rörde sig åt '
            f'samma håll i båda valen: '
            f'{" och ".join(cfg.PARTINAMN[p] for p in ense)}. '
            f'Övriga är markerade med <em>≠</em>. Det är i sig ett resultat: '
            f'valspurten har inget stabilt mönster, och genomsnittet av två '
            f'motsatta rörelser säger mindre än de två rörelserna var för sig.'
            if ense else
            'Inget parti rörde sig åt samma håll i båda valen.')
    else:
        slutkommentar = (
            'Underlaget är ett enda val. Jämför med scenariot som väger in '
            '2018 för att se hur olika två valrörelser kan se ut.')

    return f'''
  <h2>Underlaget</h2>
  <div class="rub">Vad som hände på upploppet</div>
  <div class="kort">
    <p class="besk">I dag är det {dk} dagar kvar till valdagen. Kolumnerna
    visar hur långt varje parti flyttade sig mellan opinionsläget och det
    faktiska valresultatet i tidigare val.{egen_txt}{lanad_txt}</p>
    <div class="rulla">
    <table class="tab">
      <thead><tr><th>Parti</th>{kolumner}{snittkol}
      <th class="ta">Prognos i dag</th>
      <th class="ta">Med spurten</th></tr></thead>
      <tbody>{"".join(rader)}</tbody>
    </table>
    </div>
    <p class="fot">{slutkommentar} Jämförelsedatumet flyttar sig med
    kalendern: när det är tio dagar kvar jämförs läget med tio dagar före
    valdagen i de tidigare valen. Nivåerna skalas om till hundra procent
    ({info["obalanserad_summa"]:.1f} procent före omskalning) innan mandaten
    fördelas.</p>
  </div>'''


def _trendunderlag(u: dict, farger: dict) -> str:
    """Visar de mätningar trendlinjen bygger på och lutningen per parti."""
    info = u["scenario"].trenddata
    if not info:
        return ""

    huvuden = "".join(f'<th class="ta">{p}</th>' for p in cfg.PARTIER)
    rader = []
    for r in info["matningar"]:
        datum = r["datum"]
        datum = datum.date().isoformat() if hasattr(datum, "date") else str(datum)[:10]
        celler = "".join(f'<td class="ta">{r[p]:.1f}</td>' for p in cfg.PARTIER)
        rader.append(f'<tr><td>{r["institut"]}</td><td class="ta">{datum}</td>'
                     f'{celler}</tr>')

    lut = info["lutning_per_manad"]
    lutceller = []
    for p in cfg.PARTIER:
        v = lut[p]
        kl = "upp" if v > 0.05 else ("ned" if v < -0.05 else "noll")
        lutceller.append(f'<td class="ta {kl}">{v:+.2f}</td>')
    rader.append(f'<tr class="lutrad"><td><strong>Per månad</strong></td>'
                 f'<td class="ta">–</td>{"".join(lutceller)}</tr>')

    slut = "".join(f'<td class="ta"><strong>{u["roster_nytt"][p]:.1f}</strong></td>'
                   for p in cfg.PARTIER)
    rader.append(f'<tr class="lutrad"><td><strong>Valdagen</strong></td>'
                 f'<td class="ta">13 sep</td>{slut}</tr>')

    return f'''
  <h2>Underlaget</h2>
  <div class="rub">Mätningarna trenden bygger på</div>
  <div class="kort">
    <p class="besk">{info["antal"]} mätningar från
    {" och ".join(info["institut"])} mellan {info["forsta"]} och
    {info["sista"]}. En rät linje läggs genom varje partis värden och
    förlängs till valdagen.</p>
    <div class="rulla">
    <table class="tab">
      <thead><tr><th>Institut</th><th class="ta">Datum</th>{huvuden}</tr></thead>
      <tbody>{"".join(rader)}</tbody>
    </table>
    </div>
    <p class="fot">Linjerna dras oberoende av varandra, så de summerar inte
    till hundra. Rakt fram till valdagen ger summan
    {info["obalanserad_summa"]:.1f} procent, som skalas om till hundra innan
    mandaten fördelas. Demoskop publicerade ingen mätning i juli, vilket en
    regression mot datum hanterar utan problem.</p>
  </div>'''


def _valkretsrakning(u: dict, farger: dict) -> str:
    """Visar mandatfördelningen inne i valkretsen, mandat för mandat."""
    vp = u["scenario"].valkretsparti
    vr = scenarier.valkretsrakning(u["roster_nytt"], vp)
    kod, namn = vp["kod"], vp["namn"]

    rutor = []
    for i, steg in enumerate(vr["steg"], 1):
        p = steg["parti"]
        egen = " egen" if p == kod else ""
        etikett = namn if p == kod else p
        rutor.append(
            f'<div class="mruta{egen}" data-tip="Mandat {i} till {etikett}, '
            f'kvot {steg["kvot"]:.2f}">'
            f'<span class="mnr">{i}</span>'
            f'<span class="mpil" style="background:{farger.get(p, "#7B3FA0")}"></span>'
            f'<span class="mp">{etikett if p == kod else p}</span>'
            f'<span class="mkv">{steg["kvot"]:.2f}</span></div>')

    behovs = vr["behovs_for_nasta"]
    nasta = vr["vunna"] + 1
    egna = [(i, x["kvot"]) for i, x in enumerate(vr["steg"], 1)
            if x["parti"] == kod]
    nummer = ", ".join(str(i) for i, _ in egna[:-1])
    nummer = f"{nummer} och {egna[-1][0]}" if len(egna) > 1 else str(egna[0][0])
    forsta_kvot = egna[0][1]
    fler = (f" respektive {egna[-1][1]:.2f}" if len(egna) > 1 else "")
    ORD = {1: "ett", 2: "två", 3: "tre", 4: "fyra", 5: "fem", 6: "sex",
           12: "tolv", 14: "fjorton", 15: "femton", 18: "arton", 24: "tjugofyra"}
    andel = int(round(vp["andel_i_valkrets"]))
    slutsats = (f'{ORD.get(andel, andel)} procent räcker alltså till '
                f'{ORD.get(vr["vunna"], vr["vunna"])} mandat, inte '
                f'{ORD.get(nasta, nasta)}.').capitalize()
    return f'''
  <h2>Räkningen i valkretsen</h2>
  <div class="rub">Varför {namn} får {vr["vunna"]} mandat</div>
  <div class="kort">
    <p class="besk">Örebro län har {vr["platser"]} fasta mandat. De fördelas
    med jämkade uddatalsmetoden: varje partis röstandel delas med 1,2, sedan
    3, 5, 7 och så vidare, och mandatet går till den högsta kvoten. Eftersom
    {namn} tar {vp["andel_i_valkrets"]:.0f} procent av rösterna delar
    riksdagspartierna på de återstående
    {100 - vp["andel_i_valkrets"]:.0f} procenten.</p>
    <div class="mrutor">{"".join(rutor)}</div>
    <p class="fot">{namn} tar mandat {nummer} med kvoten
    {forsta_kvot:.2f}{fler}. För ett {nasta}:e mandat skulle kvoten behöva slå
    {vr["sista_kvot"]:.2f}, alltså den sista som gav mandat. Med
    {vr["vunna"]} mandat blir nästa divisor {2 * vr["vunna"] + 1}, så det hade
    krävt <em>{behovs:.0f} procent</em> i valkretsen i stället för
    {vp["andel_i_valkrets"]:.0f}. {slutsats}</p>
  </div>'''


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

    vr_html = _valkretsrakning(u, farger) if s.valkretsparti else ""
    if s.trend:
        vr_html = _trendunderlag(u, farger)
    elif s.valspurt:
        vr_html = _spurtunderlag(u, farger)

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

  {vr_html}

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
.mrutor{{display:flex;flex-wrap:wrap;gap:7px;margin-top:18px}}
.mruta{{display:flex;align-items:center;gap:6px;background:var(--panel);
border-radius:9px;padding:7px 11px 7px 8px;font-size:12px;cursor:help;
border:1.5px solid transparent}}
.mruta.egen{{border-color:#7B3FA0;background:var(--kort)}}
.mnr{{font-size:10px;font-weight:800;color:var(--svag);min-width:13px}}
.mpil{{width:8px;height:8px;border-radius:2px;flex:none}}
.mp{{font-weight:700}}
.mkv{{color:var(--svag);font-variant-numeric:tabular-nums;font-size:11px}}
.rulla{{overflow-x:auto}}
.lutrad td{{border-top:2px solid var(--linje);background:var(--panel)}}
.flagga{{margin-left:7px;font-weight:800;color:var(--korall);cursor:help}}
.ast{{color:var(--korall);font-weight:800}}
.tab th[data-tip]{{cursor:help}}
tr.oense td:first-child{{font-weight:600}}
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
