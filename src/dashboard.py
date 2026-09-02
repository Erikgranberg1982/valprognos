"""Genererar en fristående HTML-dashboard i Lysio Researchs grafiska profil.

Profilen är avläst från lysio.se: korall #EF7466 som primärfärg, mörkblå
#003D63 för text och rubriker, sand #FAF2E8 och ljusblå #F1F3FA som
sektionsbakgrunder, Work Sans som typsnitt.
"""
from __future__ import annotations

import base64
import gzip
import json
from html import escape as html_escape
from pathlib import Path

import pandas as pd

import config as cfg
import modell

ROT = Path(__file__).resolve().parent.parent

# Kommundata läggs i en egen fil intill sidan, så att den kan hämtas separat.
KOMMUNFIL = "kommuner.json"

# Kandidatprognosen är omkring 440 kB rå och behövs bara för den som öppnar ett
# område. Den läggs därför i en egen fil som hämtas vid klick, till skillnad
# från kommundatan som bäddas in eftersom den behövs direkt.
KANDIDATFIL = "kandidater.json"

# --- Lysio Research grafiska profil ------------------------------------------
KORALL = "#EF7466"
KORALL_MORK = "#D95B4C"
KORALL_LJUS = "#FBE4E0"
MORKBLA = "#003D63"
SAND = "#FAF2E8"
LJUSBLA = "#F1F3FA"
GRON = "#7DBA74"


def _stapel(procent: float, farg: str, maxvarde: float = 35.0) -> str:
    bredd = max(0.6, min(100.0, procent / maxvarde * 100))
    return f'<div class="stapel" style="width:{bredd:.1f}%;background:{farg}"></div>'


def _logotyp(filnamn: str) -> str:
    """Läser en logotyp från assets/ och returnerar den som data-URI.

    Logotyperna bäddas in i sidan i stället för att hämtas från lysio.se, så att
    den publicerade sidan inte beror på att filerna ligger kvar där. De är
    palett-PNG på några kilobyte styck.
    """
    fil = ROT / "assets" / filnamn
    if not fil.exists():
        return ""
    kodad = base64.b64encode(fil.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{kodad}"


def _diff(varde, decimaler: int = 1) -> str:
    """Formaterar en förändring mot förra valet med tecken och färg."""
    if varde is None:
        return '<span class="diff lika">–</span>'
    try:
        tal = float(varde)
    except (TypeError, ValueError):
        return '<span class="diff lika">–</span>'
    if tal != tal:
        return '<span class="diff lika">–</span>'
    klass = "upp" if tal > 0 else ("ned" if tal < 0 else "lika")
    if abs(tal) < 0.05:
        return '<span class="diff lika">\u00b10</span>'
    tecken = "+" if tal > 0 else "\u2212"
    return f'<span class="diff {klass}">{tecken}{abs(tal):.{decimaler}f}</span>'


def _pil() -> str:
    """Pilikonen som Lysio använder i sina knappar."""
    return ('<svg class="pil" viewBox="0 0 16 16" aria-hidden="true">'
            '<path d="M1 8h12M9 4l4 4-4 4" fill="none" stroke="currentColor" '
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>')


# Partiernas ordning i kammaren, vänster till höger på den politiska skalan.
KAMMARORDNING = ["V", "S", "MP", "C", "L", "KD", "M", "SD"]


def _riksdagsledamoter() -> dict[str, list[str]]:
    """Ledamöterna per parti, i den ordning de tar plats i kammaren.

    Används för att sätta namn på varje punkt i kammargrafiken, så att den som
    hovrar ser vem platsen tillhör och inte bara vilket parti.
    """
    for fil in (ROT / "output" / "kandidatprognos_riksdag.csv",
                ROT / "data" / "kandidater" / "kandidatprognos_riksdag.csv.gz"):
        if not fil.exists():
            continue
        try:
            df = pd.read_csv(fil, dtype=str)
        except Exception:
            continue
        ut: dict[str, list[str]] = {}
        for parti, grupp in df.groupby("parti"):
            grupp = grupp.copy()
            grupp["ord"] = pd.to_numeric(grupp["ordning"], errors="coerce")
            rader = []
            for _, r in grupp.sort_values(["valkretsnamn", "ord"]).iterrows():
                uppgift = str(r.get("valsedelsuppgift") or "").strip()
                if uppgift == "nan":
                    uppgift = ""
                rader.append(f'{r["namn"]}\n{uppgift}\n{r["valkretsnamn"]}'
                             .replace("\n\n", "\n"))
            ut[str(parti)] = rader
        return ut
    return {}


def _kammare(mandat: dict[str, int], vansterblock: int) -> str:
    """Ritar riksdagskammaren som en halvcirkel med en punkt per mandat.

    Partierna placeras i politisk ordning från vänster till höger. Två markörer
    ritas: majoritetsgränsen vid plats 175, som i en symmetrisk halvcirkel alltid
    ligger i mitten, och gränsen där vänsterblockets mandat faktiskt slutar.
    Avståndet mellan dem visar hur långt blocket är från, eller över, majoritet.
    """
    platser = modell.kammarplatser()

    # Bygg en lista med ett parti per plats, i kammarordning.
    sekvens = []
    for parti in KAMMARORDNING:
        sekvens.extend([parti] * int(mandat.get(parti, 0)))
    # Eventuella tomma platser om summan avviker.
    sekvens.extend([None] * (len(platser) - len(sekvens)))

    # Namnen på ledamöterna, så att varje punkt kan berätta vem den tillhör.
    ledamoter = _riksdagsledamoter()
    raknare: dict[str, int] = {}

    prickar = []
    for plats, parti in zip(platser, sekvens):
        farg = cfg.PARTIFARG.get(parti, "#D5DCE6") if parti else "#D5DCE6"
        titel = ""
        if parti:
            i = raknare.get(parti, 0)
            raknare[parti] = i + 1
            namn = ledamoter.get(parti, [])
            if i < len(namn):
                text = html_escape(namn[i])
                titel = f"<title>{text}</title>"
            else:
                titel = f"<title>{parti}</title>"
        prickar.append(
            f'<circle cx="{plats["x"]:.4f}" cy="{plats["y"]:.4f}" r="0.042" '
            f'fill="{farg}" class="plats">{titel}</circle>'
        )

    # Majoritetsgränsen ritas där plats 175 faktiskt ligger, inte i geometrisk
    # mitt. Läget visar därför direkt hur långt från majoritet vänsterblocket är.
    import math as _math

    def _radiell(vinkel, r1, r2):
        return (r1 * _math.cos(vinkel), -r1 * _math.sin(vinkel),
                r2 * _math.cos(vinkel), -r2 * _math.sin(vinkel))

    # Majoritetsgränsen: plats 175 av 349, mitten i en symmetrisk halvcirkel.
    mv = platser[cfg.MANDAT_TOTALT // 2]["vinkel"]
    mx1, my1, mx2, my2 = _radiell(mv, 0.86, 2.16)
    mex, mey = 2.44 * _math.cos(mv), -2.44 * _math.sin(mv)

    # Blockgränsen: där vänsterblockets sista mandat ligger.
    i_block = min(max(vansterblock, 1), len(platser)) - 1
    bv = platser[i_block]["vinkel"]
    # Lägg gränsen mellan sista och nästa plats för att undvika överlapp.
    if i_block + 1 < len(platser):
        bv = (bv + platser[i_block + 1]["vinkel"]) / 2
    bx1, by1, bx2, by2 = _radiell(bv, 0.86, 2.16)
    bex, bey = 2.26 * _math.cos(bv), -2.26 * _math.sin(bv)
    # Visa blockgränsen bara när den är tydligt skild från mitten.
    visa_block = abs(vansterblock - cfg.MANDAT_TOTALT // 2) >= 6

    blocktext = ""
    if abs(vansterblock - cfg.MANDAT_TOTALT // 2) >= 6:
        over = vansterblock - (cfg.MANDAT_TOTALT // 2 + 1)
        riktning = f"{abs(over)} mandat {'över' if over > 0 else 'under'}"
        blocktext = (f", det röda där vänsterblockets {vansterblock} mandat slutar, "
                     f"{riktning} majoritet")

    blockmarkor = ""
    if visa_block:
        blockmarkor = f"""
        <line x1="{bx1:.4f}" y1="{by1:.4f}" x2="{bx2:.4f}" y2="{by2:.4f}"
              class="blocklinje"/>
        <g transform="translate({bex:.4f} {bey:.4f})">
          <rect x="-0.235" y="-0.098" width="0.47" height="0.196" rx="0.098"
                class="blockplatta"/>
          <text x="0" y="0.004" class="blocketikett"
                text-anchor="middle">{vansterblock}</text>
        </g>"""

    # Legend med mandatantal per parti.
    legend = []
    for parti in KAMMARORDNING:
        antal = int(mandat.get(parti, 0))
        if antal == 0:
            continue
        legend.append(
            f'<div class="kammarlegend-item">'
            f'<span class="legendprick" style="background:{cfg.PARTIFARG[parti]}"></span>'
            f'<strong>{parti}</strong><span class="legendantal">{antal}</span></div>'
        )

    return f"""
    <div class="kammarkort">
      <svg viewBox="-2.62 -2.76 5.24 3.04" class="kammare"
           role="img" aria-label="Riksdagens 349 mandat fördelade i halvcirkel">
        {''.join(prickar)}
        <line x1="{mx1:.4f}" y1="{my1:.4f}" x2="{mx2:.4f}" y2="{my2:.4f}"
              class="majoritetslinje"/>
        <g transform="translate({mex:.4f} {mey:.4f})">
          <rect x="-0.235" y="-0.098" width="0.47" height="0.196" rx="0.098"
                class="majoritetsplatta"/>
          <text x="0" y="0.004" class="majoritetsetikett"
                text-anchor="middle">175</text>
        </g>
        {blockmarkor}
        <text x="0" y="-0.62" class="kammartext">{sum(mandat.values())}</text>
        <text x="0" y="-0.36" class="kammartext liten">mandat totalt</text>
      </svg>
      <div class="kammarlegend">{''.join(legend)}</div>
      <div class="kammarnotis">Prognosens medianutfall. Det streckade
      strecket är majoritetsgränsen vid 175 mandat{blocktext}.</div>
    </div>"""


def _lokal_sektion(regioner: pd.DataFrame | None,
                   kommuner: pd.DataFrame | None,
                   valkretsar: pd.DataFrame | None = None) -> tuple[str, str, str]:
    """Bygger data och tabellsektion för region- och kommunval.

    Returnerar tre delar: sektionens HTML, JSON med regiondata och sammanfattning
    som bäddas in i sidan, samt JSON med kommundata som läggs i en egen fil.
    Kommundata är omkring 90 kB och behövs bara för den som faktiskt växlar till
    kommunvalet, så den hämtas separat vid klick.
    """
    partier = list(cfg.PARTIER) + ["ÖVRIGA"]

    def tal(varde, decimaler=1):
        """Returnerar ett rundat tal eller None, aldrig NaN som bryter JSON."""
        if varde is None:
            return None
        try:
            flyt = float(varde)
        except (TypeError, ValueError):
            return None
        if flyt != flyt:  # NaN
            return None
        return round(flyt, decimaler)

    def paketera(df, niva):
        if df is None or df.empty:
            return []
        ut = []
        for omrade, rad in df.iterrows():
            post = {
                "kod": str(omrade),
                "namn": str(rad["namn"]),
                "mandat_totalt": int(rad["mandat_totalt"]),
                "majoritet": int(rad["majoritet"]),
                "v": int(rad["mandat_vanster"]),
                "h": int(rad["mandat_hoger"]),
                "o": int(rad["mandat_ovriga"]),
                "m_vanster": int(rad.get("mandat_vanster_ren", 0)),
                "m_c": int(rad.get("mandat_c", 0)),
                "m_borg": int(rad.get("mandat_borgerliga", 0)),
                "m_sd": int(rad.get("mandat_sd_ensam", 0)),
                "m_ovr": int(rad.get("mandat_utanfor", 0)),
                "valkretsar": vk_per_kommun.get(str(omrade).zfill(4)),
                "lage": str(rad.get("lage", "okant")),
                "lagetext": str(rad.get("lage_text", "")),
                "lagebesk": str(rad.get("lage_beskrivning", "")),
                "stod": {p: tal(rad.get(f"stod_{p}")) for p in partier
                         if f"stod_{p}" in rad},
                "mandat": {p: int(rad[f"mandat_{p}"]) for p in partier
                           if f"mandat_{p}" in rad},
                # Jämförelse med förra valet.
                "diff": {p: tal(rad.get(f"diff_{p}")) for p in partier
                         if f"diff_{p}" in rad},
                "mandatdiff": {p: (int(rad[f"mandatdiff_{p}"])
                                   if rad.get(f"mandatdiff_{p}") is not None else None)
                               for p in partier if f"mandatdiff_{p}" in rad},
                "diff_v": (int(rad["diff_vanster"])
                           if rad.get("diff_vanster") is not None else None),
                "diff_h": (int(rad["diff_hoger"])
                           if rad.get("diff_hoger") is not None else None),
                "diff_o": (int(rad["diff_ovriga"])
                           if rad.get("diff_ovriga") is not None else None),
            }
            # Bara mandattalen per område. Namn, partier och antal styren är
            # lika för alla områden och ligger i data.koalitioner, vilket
            # sparar omkring 140 kB i kommundatan.
            koal = [int(rad[f"koal_{k['id']}"]) for k in koalitioner_def
                    if f"koal_{k['id']}" in rad]
            if koal:
                post["koal"] = koal

            # Namngivet lokalt parti, där en mätning finns.
            if rad.get("lokalt_parti"):
                post["lokal"] = {
                    "namn": str(rad["lokalt_parti"]),
                    "stod": tal(rad.get("lokalt_stod")),
                    "mandat": int(rad.get("lokalt_mandat") or 0),
                    "matt": bool(rad.get("lokalt_matt")),
                    "kalla": (str(rad["lokalt_kalla"])
                              if rad.get("lokalt_kalla") else None),
                }
            ut.append(post)
        return sorted(ut, key=lambda x: x["namn"])

    import lokala_koalitioner
    koalitioner_def = lokala_koalitioner.las()

    # Valkretsarnas prognos, grupperad på kommunkod så att detaljvyn bara
    # behöver slå upp den kommun som visas.
    vk_per_kommun = {}
    if valkretsar is not None and not valkretsar.empty:
        for kod, grupp in valkretsar.groupby("kommunkod"):
            poster = []
            for _, rad in grupp.iterrows():
                stod, diff = {}, {}
                for parti in cfg.PARTIER:
                    varde = rad.get(parti)
                    if varde is not None and pd.notna(varde):
                        stod[parti] = round(float(varde), 1)
                    d = rad.get(f"diff_{parti}")
                    if d is not None and pd.notna(d):
                        diff[parti] = round(float(d), 1)
                poster.append({"namn": str(rad["valkretsnamn"]),
                               "stod": stod, "diff": diff})
            vk_per_kommun[str(kod).zfill(4)] = poster

    regiondata = paketera(regioner, "region")
    kommundata = paketera(kommuner, "kommun")

    def styresammanfattning(poster):
        """Grupperar områdena efter mandatläge.

        Tidigare räknades vänster- och högermajoritet enligt riksdagsvalets
        blockindelning. Lokalt blev det missvisande, eftersom C där oftare
        styr med de borgerliga än med vänstern.
        """
        raknare = {}
        for p in poster:
            raknare[p["lage"]] = raknare.get(p["lage"], 0) + 1
        return {
            "egen_majoritet": raknare.get("vanster", 0),
            "kravs_c": raknare.get("vanster_c", 0) + raknare.get("borgerlig_c", 0),
            "hoger": (raknare.get("hoger_sd", 0) + raknare.get("hoger_flera", 0)),
            "lokala": raknare.get("lokala_vagmastare", 0),
            "oklart": raknare.get("oklart", 0),
            "antal": len(poster),
        }

    data = {
        "region": regiondata,
        "kommun_fil": KOMMUNFIL,
        "kommun_antal": len(kommundata),
        "sammanfattning": {
            "region": styresammanfattning(regiondata),
            "kommun": styresammanfattning(kommundata),
        },
        "partier": partier,
        "farger": {p: cfg.PARTIFARG.get(p, "#9AA6B5") for p in partier},
        "koalitioner": [{
            "namn": k["namn"],
            "partier": "+".join(k["partier"]),
            "kommun": k["kommuner_2022"],
            "region": k["regioner_2022"],
        } for k in koalitioner_def],
    }

    partihuvud = "".join(f'<th class="tal">{p}</th>' for p in partier)
    partihuvud_sort = "".join(
        f'<th class="tal"><button class="sortknapp" data-sort="stod:{p}">{p}</button></th>'
        for p in partier)
    metod_html = _metod_lokal()
    lokala_matningar_html = _lokala_matningar_html(regioner, kommuner)

    html = f"""
<div id="lokalvy" hidden>
  <div class="omradesrad">
    <input class="sokruta" id="lokalsok" type="search"
           placeholder="Sök område ..." autocomplete="off">
    <button class="knapp sekundar" id="rensaomrade" hidden>Visa alla</button>
  </div>

  <div id="omradesdetalj" hidden></div>

  <div id="lokaloversikt">
    <div class="styrerad" id="styrerad"></div>
    <div class="klicktips" id="klicktips"></div>
    <div class="tabellwrap"><table class="sorterbar">
      <thead><tr>
        <th><button class="sortknapp" data-sort="namn">Område</button></th>
        {partihuvud_sort}
        <th class="tal"><button class="sortknapp" data-sort="mandat_totalt">Mandat</button></th>
        <th class="tal"><button class="sortknapp" data-sort="m_vanster">V+S+MP</button></th>
        <th class="tal"><button class="sortknapp" data-sort="m_c">C</button></th>
        <th class="tal"><button class="sortknapp" data-sort="m_borg">M+KD+L</button></th>
        <th class="tal"><button class="sortknapp" data-sort="m_sd">SD</button></th>
        <th class="tal"><button class="sortknapp" data-sort="m_ovr">Övr</button></th>
        <th><button class="sortknapp" data-sort="lagetext">Mandatläge</button></th>
      </tr></thead>
      <tbody id="lokalkropp"></tbody>
    </table></div>
    <div class="notis" id="lokalnotis"></div>
  </div>

  {lokala_matningar_html}

  {metod_html}

</div>
"""
    kommun_json = json.dumps(kommundata, ensure_ascii=False, separators=(",", ":"))
    # Kommundata bäddas in gzip-komprimerad och base64-kodad. Rå JSON är 137 kB
    # men komprimerad bara omkring 29 kB, vilket är litet nog att ligga i sidan.
    # Alternativet, att hämta en separat fil, fungerar inte när sidan öppnas
    # direkt från filsystemet eftersom webbläsaren blockerar fetch mot file://.
    data["kommun_gz"] = base64.b64encode(
        gzip.compress(kommun_json.encode("utf-8"), 9)).decode("ascii")


    return (html, json.dumps(data, ensure_ascii=False), kommun_json)


def _metod_lokal() -> str:
    """Metodbeskrivning för region- och kommunprognosen.

    Läggs in i sidan och visas i den lokala vyn, eftersom beräkningen skiljer
    sig väsentligt från riksdagsprognosen och osäkerheten är större.
    """
    import kommunmodell
    import lokala_partier
    import regionmodell

    psu_procent = regionmodell.PSU_VIKT * 100
    psu_kommun = kommunmodell.PSU_VIKT_KOMMUN * 100
    kvot_riksdag = lokala_partier.NIVAKVOT["riksdagsvalkrets"]
    kvot_region = lokala_partier.NIVAKVOT["region"]

    return f"""
<h2>Metod</h2>
<div class="sektionsrubrik">Så beräknas region och kommun</div>

<div class="metodkort">
  <p class="metodingress">Opinionsmätningar för region- och kommunvalen är
  sällsynta. För de få områden där en fullständig mätning finns vägs den in med
  hög vikt, se tabellen ovan. För övriga bygger prognosen på områdets eget
  resultat i förra lokalvalet, skalat med rikstrenden. Osäkerheten är omkring
  dubbelt så stor som för riksdagsvalet.</p>

  <div class="metodsteg">
    <div class="steg">
      <div class="stegnr">1</div>
      <div class="stegtext">
        <strong>Områdets eget förra resultat</strong>
        <p>Utgångspunkten är hur området faktiskt röstade i förra lokalvalet.
        Det fångar automatiskt att väljare röstar annorlunda i kommun- och
        regionval än i riksdagsvalet, och att lokala partier är starka på vissa
        håll.</p>
      </div>
    </div>
    <div class="steg">
      <div class="stegnr">2</div>
      <div class="stegtext">
        <strong>Rikstrenden sedan dess</strong>
        <p>Varje parti skalas med hur mycket det gått upp eller ner nationellt.
        Ett parti som fått 2,3 procent i en kommun och sedan vuxit från 5,3 till
        6,5 procent i riket hamnar på 2,3 × 6,5/5,3, alltså 2,8 procent.</p>
      </div>
    </div>
    <div class="steg">
      <div class="stegnr">3</div>
      <div class="stegtext">
        <strong>Lokala partier och mandat</strong>
        <p>Lokala partier hålls på förra valets nivå. För
        <strong>regionvalet</strong> vägs {psu_procent:.0f} procent in från
        SCB:s partisympatiundersökning per landsdel; för kommunvalet används
        den inte, eftersom landsdelarna är för grova för en enskild kommun.
        Mandaten fördelas sedan med jämkade uddatalsmetoden.</p>
      </div>
    </div>
  </div>

  <table class="metodtabell">
    <thead><tr><th>Träffsäkerhet</th><th class="tal">Regionval</th>
      <th class="tal">Kommunval</th></tr></thead>
    <tbody>
      <tr><td>Medianfel</td>
        <td class="tal pos">1,0</td><td class="tal pos">1,2</td></tr>
      <tr><td>Medelfel</td>
        <td class="tal">1,2</td><td class="tal">2,0</td></tr>
      <tr><td>Nio fall av tio inom</td>
        <td class="tal">2,4</td><td class="tal">4,6</td></tr>
      <tr><td>Andel inom 3 procentenheter</td>
        <td class="tal">96%</td><td class="tal">81%</td></tr>
    </tbody>
  </table>
  <p class="metodnot">Procentenheter, uppmätt genom att förutsäga valet 2022
  med enbart data från 2018. Kommunerna är svårare än regionerna eftersom de är
  mindre och lokala förhållanden väger tyngre. Enstaka kommuner slår kraftigt
  fel när ett parti byter skepnad lokalt, exempelvis genom en utbrytning eller
  en ny lista, vilket är skälet att medelfelet är högre än medianfelet.</p>

  <div class="metodrutor">
    <div class="metodruta">
      <div class="mrubrik">Träffsäkerhet</div>
      <p>Ett test där bara 2018 års data används för att förutsäga valet 2022
      ger ett medelabsolutfel på <strong>1,2 procentenheter</strong> för
      regionvalet och <strong>2,0</strong> för kommunvalet. Riksdagsprognosen
      ligger på 0,6 nära valdagen. Kommunerna är svårast: de är minst, och
      lokala förhållanden väger tyngst där.</p>
    </div>
    <div class="metodruta">
      <div class="mrubrik">Varför inte SCB på kommunnivå</div>
      <p>Partisympatiundersökningen delar landet i tio landsdelar. Västsverige
      rymmer både Göteborg och Öckerö, som röstar helt olika, så signalen blir
      missvisande för en enskild kommun. Med vikten 0,25 steg felet från 2,40
      till 2,50 procentenheter, värst för SD, V och KD.</p>
    </div>
    <div class="metodruta">
      <div class="mrubrik">Spärrar och mandat</div>
      <p>Regionvalet har tre procents spärr, kommunvalet i praktiken två.
      Fullmäktiges storlek läses ur SCB:s valresultat, eftersom varje kommun
      och region beslutar sin egen: kommunerna varierar mellan 21 och 101
      ledamöter.</p>
    </div>
    <div class="metodruta">
      <div class="mrubrik">Koalitioner</div>
      <p>Vänster mot höger är för grovt lokalt. Efter valet 2022 har 101 av 290
      kommuner ett blocköverskridande styre, och SCB räknar 84 olika
      konstellationer. C räknas därför inte till något block, och tabellen visar
      mandatläge i stället för blockmajoritet.</p>
    </div>
    <div class="metodruta">
      <div class="mrubrik">Lokala partier</div>
      <p>SCB redovisar lokala partier samlat som ÖVRIGA, så de kan inte
      prognosticeras var för sig. De hålls på förra valets nivå. Där ett parti
      har en egen publicerad mätning bryts det ut och redovisas med namn.</p>
    </div>
    <div class="metodruta">
      <div class="mrubrik">Riksdagen via valkretsen</div>
      <p>Ett parti når riksdagen med fyra procent i landet eller tolv i en
      valkrets. Den andra vägen är svår: ett lokalt parti behåller bara omkring
      {kvot_riksdag*100:.0f} procent av sitt kommunvalsstöd i riksdagsvalet, och
      {kvot_region*100:.0f} procent i regionvalet.</p>
    </div>
  </div>

  <p class="metodnot">Vad modellen inte fångar: lokala förhållanden som ett
  avhopp, en ny lista eller en lokal stridsfråga kan flytta stora väljarandelar
  utan att synas i något historiskt mönster. Gotland saknar regionval och ingår
  inte i regionprognosen.</p>
</div>
"""


def _lokala_matningar_html(regioner=None, kommuner=None) -> str:
    """Redovisar de lokala mätningar som används i prognosen.

    Bara mätningar som faktiskt vägs in listas. En ofullständig mätning
    påverkar inte prognosen och hör därför inte hemma i redovisningen.
    """
    import lokala_partier

    tabell = lokala_partier.las_matningar()
    if tabell.empty:
        return ""

    nivanamn = {"kommun": "Kommunval", "region": "Regionval",
                "riksdagsvalkrets": "Riksdagsval i valkretsen"}

    rader = []
    # Varje mätning redovisas för sig. Ett område kan ha mätts flera gånger,
    # och prognosen använder bara den nyaste, men de äldre är ändå underlag
    # läsaren bör kunna se.
    if "datum" in tabell.columns:
        tabell = tabell.sort_values("datum", ascending=False)
    for _, rad in tabell.iterrows():
        matning = lokala_partier.beskriv_matning(rad)
        if not matning["anvands"]:
            continue

        celler = []
        for parti in cfg.PARTIER:
            varde = matning["partier"].get(parti)
            celler.append(f'<td class="tal">{varde:.1f}</td>' if varde is not None
                          else '<td class="tal dim">–</td>')

        lokalcell = ('<td class="tal"><strong>'
                     f'{matning["lokalt_stod"]:.1f}</strong></td>'
                     if matning["lokalt_stod"] is not None
                     else '<td class="tal dim">–</td>')

        uppdrag = (f' för {matning["uppdragsgivare"]}'
                   if matning["uppdragsgivare"] else "")
        urval = (f' · {matning["urval"]:,} svarande'.replace(",", "\u00a0")
                 if matning["urval"] else "")

        rader.append(f"""
        <tr>
          <td class="inst">{matning['institut']}{uppdrag}
            <div class="matningsmeta">{nivanamn.get(rad['niva'], rad['niva'])}
            i {rad['omrade_namn']}{urval}</div></td>
          <td class="datum">{matning['datum']}</td>
          {''.join(celler)}
          {lokalcell}
          <td class="tal"><span class="viktbricka">
            {matning['vikt']*100:.0f}%</span></td>
        </tr>""")

    if not rader:
        return ""

    partihuvud = "".join(f'<th class="tal">{p}</th>' for p in cfg.PARTIER)

    return f"""
<h2 id="lokala-matningar">Lokala mätningar</h2>
<div class="sektionsrubrik">Mätningar för enskilda kommuner och regioner</div>
<div class="tabellwrap"><table>
  <thead><tr><th>Mätning</th><th>Datum</th>{partihuvud}
    <th class="tal">Lokalt</th><th class="tal">Vikt</th></tr></thead>
  <tbody>{''.join(rader)}</tbody>
</table></div>
<div class="notis">Lokala mätningar vägs samman med modellens skattning på samma
sätt som SCB:s partisympatiundersökning i regionprognosen, men med högre vikt
eftersom de gäller exakt det område de används på. Vikten halveras på
{cfg.LOKAL_MATNING_HALVERINGSTID:.0f} dagar.</div>
"""


def bygg(sammanfattning: pd.DataFrame, block: dict, regeringar: pd.DataFrame,
         trend: pd.DataFrame, husfaktorer: pd.DataFrame,
         matningar: pd.DataFrame, meta: dict,
         regioner: pd.DataFrame | None = None,
         kommuner: pd.DataFrame | None = None,
         valkretsar: pd.DataFrame | None = None) -> str:

    # Antalet ledamöter räknas ur kandidatprognosen. Det är normalt 349, men
    # blir lägre om någon valkrets saknar användbar vallista.
    antal_ledamoter = (sum(len(v) for v in _riksdagsledamoter().values())
                       or cfg.MANDAT_TOTALT)

    # --- Partirader
    partirader = []
    for _, r in sammanfattning.iterrows():
        p = r["parti"]
        farg = cfg.PARTIFARG[p]
        risk = ""
        if r["sannolikhet_over_sparr"] < 0.98:
            risk = (f'<span class="risk">'
                    f'{cfg.formatera_sannolikhet(r["sannolikhet_over_sparr"])} '
                    f'över spärren</span>')
        partirader.append(f"""
        <tr>
          <td class="parti"><a class="partilank"
              href="partier_2026.html#{p}" title="Se {r['namn']} i detalj">
              <span class="prick" style="background:{farg}"></span>
              <strong>{p}</strong><span class="fullnamn">{r['namn']}</span>
              {_pil()}</a></td>
          <td class="stapelcell">{_stapel(r['prognos'], farg)}</td>
          <td class="tal"><strong>{r['prognos']:.1f}%</strong></td>
          <td class="tal">{_diff(r.get('forandring'))}</td>
          <td class="spann">{r['p10']:.1f}–{r['p90']:.1f}</td>
          <td class="tal">{r['mandat_median']}</td>
          <td class="tal">{_diff(r.get('mandatforandring'), 0)}</td>
          <td class="spann">{r['mandat_p10']}–{r['mandat_p90']}{risk}</td>
        </tr>""")

    # --- Kammaren: medianmandat per parti
    mandat_median = {r["parti"]: int(r["mandat_median"])
                     for _, r in sammanfattning.iterrows()}
    # Justera så summan blir exakt 349; medianer summerar inte nödvändigtvis.
    diff = cfg.MANDAT_TOTALT - sum(mandat_median.values())
    if diff != 0 and mandat_median:
        storst = max(mandat_median, key=mandat_median.get)
        mandat_median[storst] += diff
    kammare = _kammare(mandat_median, int(block["vanster"]["mandat_median"]))

    # --- Blockkort
    v, h = block["vanster"], block["hoger"]
    blockkort = []
    for b, farg in ((v, "#EE2020"), (h, "#52BDEC")):
        andel = b["sannolikhet_majoritet"] * 100
        blockkort.append(f"""
        <div class="kort blockkort">
          <div class="kortetikett">{b['namn']}</div>
          <div class="blockmandat">{b['mandat_median']}<span class="enhet">mandat</span></div>
          <div class="blockspann">80%-spann {b['mandat_p10']}–{b['mandat_p90']}</div>
          <div class="mandatbar">
            <div class="mandatfyll" style="width:{min(100, b['mandat_median']/349*100):.1f}%;
                 background:{farg}"></div>
            <div class="majoritetsmarke" title="175 mandat"></div>
          </div>
          <div class="blocksannolikhet">
            <div class="sannolikhetstal">{cfg.formatera_sannolikhet(b['sannolikhet_majoritet'])}</div>
            <div class="sannolikhetstext">sannolikhet för egen majoritet</div>
          </div>
        </div>""")

    # --- Regeringsalternativ
    regrader = []
    for _, r in regeringar.iterrows():
        andel = r["sannolikhet"] * 100
        farg = GRON if andel >= 50 else (KORALL if andel >= 10 else "#B7C1D2")
        regrader.append(f"""
        <tr>
          <td class="regnamn"><strong>{r['namn']}</strong>
              <div class="regbesk">{r['beskrivning']}</div></td>
          <td class="regpartier"><span class="chip">{r['partier']}</span></td>
          <td class="tal">{r['mandat_median']}</td>
          <td class="spann">{r['mandat_p10']}–{r['mandat_p90']}</td>
          <td class="sannolikhetscell">
            <div class="minibar"><div class="minifyll"
                 style="width:{andel:.1f}%;background:{farg}"></div></div>
            <span class="sannolikhetsprocent">{cfg.formatera_sannolikhet(r['sannolikhet'])}</span>
          </td>
        </tr>""")

    # --- Husfaktorer
    hfrader = []
    if not husfaktorer.empty:
        for _, r in husfaktorer.sort_values("institut").iterrows():
            celler = "".join(
                f'<td class="hf {"pos" if r[p] > 0.15 else "neg" if r[p] < -0.15 else ""}">'
                f'{r[p]:+.1f}</td>' for p in cfg.PARTIER
            )
            hfrader.append(f'<tr><td class="inst">{r["institut"]}</td>'
                           f'<td class="tal dim">{int(r["antal_matningar"])}</td>{celler}</tr>')

    # --- Institutsöversikt: varje instituts bidrag till prognosen
    per_institut = (matningar.groupby("institut")
                    .agg(antal=("datum", "size"),
                         inom=("inom_fonster", "sum"),
                         viktandel=("viktandel", "sum"),
                         senaste=("datum", "max"))
                    .sort_values("viktandel", ascending=False).reset_index())

    instkort = []
    for _, r in per_institut.iterrows():
        namn = r["institut"]
        kvalvikt = cfg.INSTITUT.get(namn, {}).get("vikt", cfg.STANDARD_VIKT)
        urval = cfg.INSTITUT.get(namn, {}).get("typiskt_urval", cfg.STANDARD_URVAL)
        alder = (pd.Timestamp(meta["senaste_matning"]) - r["senaste"]).days
        inaktiv = " inaktiv" if r["viktandel"] < 0.05 else ""
        varning = ('<div class="instvarning">Utanför tidsfönstret</div>'
                   if r["viktandel"] < 0.05 else "")
        instkort.append(f"""
        <button class="instkort{inaktiv}" data-institut="{namn}">
          <div class="instnamn">{namn}</div>
          <div class="instvikt">{r['viktandel']:.1f}<span class="enhet">% av vikten</span></div>
          <div class="instbar"><div class="instfyll"
               style="width:{min(100, r['viktandel']*3.5):.1f}%"></div></div>
          <div class="instmeta">
            {int(r['antal'])} mätningar · {int(r['inom'])} i modellen<br>
            senaste {r['senaste'].date()} ({alder} dgr)<br>
            kvalitetsvikt {kvalvikt:.2f} · urval ~{urval:,}
          </div>
          {varning}
          <div class="instlank">Visa alla mätningar {_pil()}</div>
        </button>""".replace(",", " "))

    # --- Senaste mätningar
    senaste = matningar.head(15)
    senasterader = []
    for _, r in senaste.iterrows():
        celler = "".join(
            f'<td class="tal parti-{p}">{r[p]:.1f}</td>' for p in cfg.PARTIER
        )
        vikt = (f'<span class="viktbricka">{r["viktandel"]:.1f}%</span>'
                if r["inom_fonster"] else '<span class="viktbricka noll">–</span>')
        senasterader.append(f"""
        <tr>
          <td class="inst">{r['institut']}</td>
          <td class="datum">{r['datum'].date()}<span class="alder">{int(r['alder_dagar'])} dgr</span></td>
          {celler}
          <td class="tal blockcell v">{r['block_v']:.1f}</td>
          <td class="tal blockcell h">{r['block_h']:.1f}</td>
          <td class="tal">{vikt}</td>
        </tr>""")

    # --- Alla mätningar per institut, som JSON för filtrering i webbläsaren
    alla = {}
    for namn, grupp in matningar.groupby("institut"):
        alla[namn] = [{
            "datum": rad["datum"].strftime("%Y-%m-%d"),
            "alder": int(rad["alder_dagar"]),
            "inom": bool(rad["inom_fonster"]),
            "vikt": round(float(rad["viktandel"]), 2),
            "bv": round(float(rad["block_v"]), 1),
            "bh": round(float(rad["block_h"]), 1),
            **{p: (round(float(rad[p]), 1) if pd.notna(rad[p]) else None) for p in cfg.PARTIER},
        } for _, rad in grupp.sort_values("datum", ascending=False).iterrows()]

    trend_json = json.dumps({
        "datum": [d.strftime("%Y-%m-%d") for d in trend["datum"]],
        "serier": {p: [round(float(x), 2) for x in trend[p]] for p in cfg.PARTIER},
        "farger": cfg.PARTIFARG,
    })
    alla_json = json.dumps(alla, ensure_ascii=False)
    partier_json = json.dumps(cfg.PARTIER)
    partifarg_json = json.dumps(cfg.PARTIFARG)
    lokal_html, lokal_json, kommun_json = _lokal_sektion(
        regioner, kommuner, valkretsar)
    logo_farg = _logotyp("lysio-logo-farg.png")
    logo_vit = _logotyp("lysio-logo-vit.png")
    partier_lokal_json = json.dumps(list(cfg.PARTIER) + ["ÖVRIGA"])
    kammarordning_json = json.dumps(KAMMARORDNING)
    block_v_json = json.dumps(cfg.BLOCK["vanster"])
    block_h_json = json.dumps(cfg.BLOCK["hoger"])

    partikolumner = "".join(f'<th class="tal">{p}</th>' for p in cfg.PARTIER)
    # Svenskt talformat använder mellanslag som tusentalsavgränsare.
    sim_text = f"{meta['antal_simuleringar']:,}".replace(",", "\u00a0")
    ga = cfg.google_analytics()

    return f"""<!doctype html>
<html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Valprognos 2026</title>

{ga}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Work+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root {{
  --korall:{KORALL}; --korall-mork:{KORALL_MORK}; --korall-ljus:{KORALL_LJUS};
  --morkbla:{MORKBLA}; --sand:{SAND}; --ljusbla:{LJUSBLA}; --gron:{GRON};
  --bg:#ffffff; --panel:{LJUSBLA}; --text:{MORKBLA}; --svag:#69727D;
  --linje:#E3E8F0; --kortbg:#ffffff;
  --skugga:0 2px 4px 0 rgba(183,193,210,.35);
  --skugga-hog:0 15px 30px 0 rgba(21,28,39,.12);
  --markorbg:{MORKBLA}; --markortext:#ffffff;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg:#0E1621; --panel:#16202E; --text:#EAF0F7; --svag:#93A2B5;
    --linje:#22303F; --kortbg:#16202E; --sand:#1D2632; --ljusbla:#16202E;
    --korall-ljus:#3A2320;
    --skugga:0 2px 4px 0 rgba(0,0,0,.4);
    --skugga-hog:0 15px 30px 0 rgba(0,0,0,.45);
    --markorbg:#EAF0F7; --markortext:#0E1621;
  }}
}}
:root[data-theme="dark"] {{
  --bg:#0E1621; --panel:#16202E; --text:#EAF0F7; --svag:#93A2B5;
  --linje:#22303F; --kortbg:#16202E; --sand:#1D2632; --ljusbla:#16202E;
  --korall-ljus:#3A2320;
  --skugga:0 2px 4px 0 rgba(0,0,0,.4);
  --skugga-hog:0 15px 30px 0 rgba(0,0,0,.45);
  --markorbg:#EAF0F7; --markortext:#0E1621;
}}
* {{ box-sizing:border-box; }}
html {{ scroll-behavior:smooth; }}
body {{ margin:0; background:var(--bg); color:var(--text);
  font-family:'Work Sans',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  font-size:15px; line-height:1.6; -webkit-font-smoothing:antialiased; }}
/* Sidans bredd. Kommuntabellen med sjutton kolumner behöver omkring 1190
   pixlar, så 1320 rymmer den utan horisontell scroll och lämnar marginal.
   Läsbar text mår illa av alltför långa rader, så brödtext och metodavsnitt
   begränsas separat nedan. */
.wrap {{ max-width:1320px; margin:0 auto; padding:0 28px 96px; }}

/* --- Sidhuvud --- */
.topp {{ background:var(--sand); border-bottom:1px solid var(--linje); margin-bottom:0; }}
.toppinner {{ max-width:1320px; margin:0 auto; padding:16px 28px;
  display:flex; align-items:center; justify-content:space-between; gap:20px; }}
.logo {{ display:inline-flex; align-items:center; text-decoration:none; }}
/* Färgvarianten är bred med bubblorna till vänster, den vita är kvadratisk med
   bubblorna ovanför ordmärket. Den vita används bara i mörkt läge. */
/* En variant åt gången. Båda logotyperna ligger alltid i sidan och CSS avgör
   vilken som visas, så att växlingen sker utan omladdning.

   Lösningen använder opacity i stället för display, eftersom bilderna då kan
   staplas ovanpå varandra i samma ruta. Det gör att exakt en är synlig i alla
   tre lägen: systemstandard, explicit ljust och explicit mörkt, utan att
   regelordningen behöver stämma. */
.logoruta {{ position:relative; display:inline-flex; align-items:center;
  height:54px; }}
.logoruta img {{ display:block; width:auto; transition:opacity .12s; }}
.logo-ljus {{ height:46px; opacity:1; }}
.logo-mork {{ height:54px; opacity:0; position:absolute; left:0;
  top:50%; transform:translateY(-50%); pointer-events:none; }}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) .logo-ljus {{ opacity:0; }}
  :root:not([data-theme="light"]) .logo-mork {{ opacity:1; }}
}}
:root[data-theme="dark"] .logo-ljus {{ opacity:0; }}
:root[data-theme="dark"] .logo-mork {{ opacity:1; }}
:root[data-theme="light"] .logo-ljus {{ opacity:1; }}
:root[data-theme="light"] .logo-mork {{ opacity:0; }}
.temaknapp {{ background:none; border:1px solid var(--linje); color:var(--svag);
  border-radius:28px; padding:7px 15px; font:inherit; font-size:13px; font-weight:500;
  cursor:pointer; }}
.temaknapp:hover {{ border-color:var(--korall); color:var(--korall); }}

.hero {{ background:var(--sand); padding:38px 0 46px; }}
.heroinner {{ max-width:1320px; margin:0 auto; padding:0 28px; }}
.etikett {{ display:inline-block; background:var(--korall); color:#fff;
  font-size:11px; font-weight:700; letter-spacing:1.4px; text-transform:uppercase;
  padding:5px 13px; border-radius:28px; margin-bottom:16px; }}
h1 {{ margin:0 0 12px; font-size:clamp(30px,4.6vw,46px); font-weight:800;
  letter-spacing:-1.3px; line-height:1.1; }}
.ingress {{ font-size:16px; color:var(--svag); max-width:620px; margin:0; }}
.nyckeltal {{ display:flex; flex-wrap:wrap; gap:34px; margin-top:28px;
  padding-top:24px; border-top:1px solid rgba(0,61,99,.14); }}
.nyckel .n {{ font-size:26px; font-weight:800; letter-spacing:-.7px; line-height:1.15; }}
.nyckel .e {{ font-size:12px; color:var(--svag); font-weight:500; }}

/* --- Sektioner --- */
h2 {{ font-size:12px; text-transform:uppercase; letter-spacing:1.6px;
  color:var(--svag); margin:52px 0 4px; font-weight:700; }}
.sektionsrubrik {{ font-size:25px; font-weight:700; letter-spacing:-.7px;
  margin:0 0 18px; }}
/* Radlängd. Vid 1320 pixlar blir löpande text för bred för bekväm läsning,
   så textblock begränsas till omkring nittio tecken medan tabeller och
   grafik får utnyttja hela bredden. */
.notis {{ background:var(--panel); border-left:3px solid var(--korall);
  padding:14px 18px; border-radius:0 8px 8px 0; font-size:13.5px; color:var(--svag);
  margin-top:14px; max-width:900px; }}

/* --- Kort --- */
.kort {{ background:var(--kortbg); border:1px solid var(--linje); border-radius:16px;
  padding:24px; box-shadow:var(--skugga); }}
.blockrad {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(290px,1fr)); gap:18px; }}
.kortetikett {{ font-size:12px; color:var(--svag); font-weight:700;
  letter-spacing:1.1px; text-transform:uppercase; }}
.blockmandat {{ font-size:52px; font-weight:800; line-height:1.05; letter-spacing:-2.2px;
  margin-top:4px; }}
.blockmandat .enhet {{ font-size:14px; font-weight:600; color:var(--svag);
  letter-spacing:0; margin-left:8px; }}
.blockspann {{ font-size:13px; color:var(--svag); }}
.mandatbar {{ position:relative; height:9px; background:var(--panel);
  border-radius:5px; margin:16px 0 4px; overflow:hidden; }}
.mandatfyll {{ height:100%; border-radius:5px; }}
.majoritetsmarke {{ position:absolute; left:50.14%; top:-3px; bottom:-3px; width:2px;
  background:var(--text); opacity:.55; }}
.blocksannolikhet {{ margin-top:14px; padding-top:14px; border-top:1px solid var(--linje);
  display:flex; align-items:baseline; gap:10px; }}
.sannolikhetstal {{ font-size:28px; font-weight:800; letter-spacing:-1px; color:var(--korall); }}
.sannolikhetstext {{ font-size:12.5px; color:var(--svag); }}

/* --- Tabeller --- */
.tabellwrap {{ overflow-x:auto; border:1px solid var(--linje); border-radius:14px;
  background:var(--kortbg); }}
table {{ width:100%; border-collapse:collapse; }}
th {{ text-align:left; font-size:10.5px; text-transform:uppercase; letter-spacing:.9px;
  color:var(--svag); font-weight:700; padding:13px 12px; background:var(--panel);
  white-space:nowrap; position:sticky; top:0; }}
td {{ padding:11px 12px; border-top:1px solid var(--linje); vertical-align:middle; }}
tbody tr:hover {{ background:var(--panel); }}
.parti {{ white-space:nowrap; }}
/* Partinamnet leder till partisidan med trend, valkretsar och kandidater. */
.partilank {{ display:inline-flex; align-items:center; gap:2px;
  text-decoration:none; color:inherit; }}
.partilank .pil {{ width:13px; height:13px; margin-left:5px; color:var(--korall);
  opacity:0; transition:opacity .15s, transform .15s; }}
tr:hover .partilank .pil {{ opacity:1; transform:translateX(2px); }}
.partilank:hover strong {{ color:var(--korall); }}
.prick {{ display:inline-block; width:11px; height:11px; border-radius:50%;
  margin-right:9px; vertical-align:-1px; }}
.fullnamn {{ color:var(--svag); font-size:13px; margin-left:7px; }}
.stapelcell {{ width:30%; min-width:130px; }}
.stapel {{ height:20px; border-radius:4px; }}
.tal {{ text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }}
.dim {{ color:var(--svag); }}
.spann {{ text-align:right; color:var(--svag); font-size:13px; white-space:nowrap;
  font-variant-numeric:tabular-nums; }}
.risk {{ display:block; color:var(--korall-mork); font-size:11px; font-weight:600; }}
.inst {{ font-weight:600; white-space:nowrap; }}
.datum {{ white-space:nowrap; font-size:13.5px; }}
.alder {{ display:block; font-size:11px; color:var(--svag); }}
.blockcell {{ font-weight:600; }}
.blockcell.v {{ color:#EE2020; }} .blockcell.h {{ color:#0F8FCC; }}
.blockcell.c {{ color:#0B7A2E; }} .blockcell.sd {{ color:#A89000; }}
:root[data-theme="dark"] .blockcell.sd,
:root:not([data-theme="light"]) .blockcell.sd {{ color:#DDDD00; }}
:root[data-theme="dark"] .blockcell.c,
:root:not([data-theme="light"]) .blockcell.c {{ color:#7ED694; }}
.viktbricka {{ display:inline-block; background:var(--korall-ljus); color:var(--korall-mork);
  font-weight:700; font-size:12px; padding:3px 9px; border-radius:28px; }}
.viktbricka.noll {{ background:var(--panel); color:var(--svag); }}
.regnamn {{ max-width:330px; }}
.regbesk {{ color:var(--svag); font-size:12.5px; margin-top:3px; line-height:1.45; }}
.chip {{ display:inline-block; background:var(--panel); border:1px solid var(--linje);
  border-radius:28px; padding:3px 11px; font-size:12px; font-weight:600;
  color:var(--svag); white-space:nowrap; }}
.sannolikhetscell {{ width:190px; white-space:nowrap; }}
.minibar {{ display:inline-block; width:108px; height:9px; background:var(--panel);
  border-radius:5px; overflow:hidden; vertical-align:middle; }}
.minifyll {{ height:100%; border-radius:5px; }}
.sannolikhetsprocent {{ display:inline-block; min-width:52px; text-align:right;
  font-weight:700; font-variant-numeric:tabular-nums; margin-left:8px; font-size:13.5px; }}
.hf {{ text-align:right; font-size:13px; font-variant-numeric:tabular-nums;
  color:var(--svag); }}
.hf.pos {{ color:var(--gron); font-weight:600; }}
.hf.neg {{ color:var(--korall); font-weight:600; }}

/* --- Institutskort --- */
.instrad {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(215px,1fr)); gap:14px; }}
.instkort {{ text-align:left; font:inherit; color:inherit; cursor:pointer;
  background:var(--kortbg); border:1px solid var(--linje); border-radius:14px;
  padding:18px; transition:border-color .15s, box-shadow .15s, transform .15s; }}
.instkort:hover {{ border-color:var(--korall); box-shadow:var(--skugga-hog);
  transform:translateY(-2px); }}
.instkort.aktiv {{ border-color:var(--korall); border-width:2px; padding:17px; }}
.instkort.inaktiv {{ opacity:.62; }}
.instnamn {{ font-weight:700; font-size:15.5px; }}
.instvikt {{ font-size:27px; font-weight:800; letter-spacing:-1px; color:var(--korall);
  line-height:1.2; margin-top:2px; }}
.instvikt .enhet {{ font-size:12px; font-weight:600; color:var(--svag);
  letter-spacing:0; margin-left:4px; }}
.instbar {{ height:5px; background:var(--panel); border-radius:3px; overflow:hidden;
  margin:9px 0 11px; }}
.instfyll {{ height:100%; background:var(--korall); border-radius:3px; }}
.instmeta {{ font-size:11.5px; color:var(--svag); line-height:1.65; }}
.instvarning {{ margin-top:8px; font-size:11px; font-weight:600; color:var(--korall-mork);
  background:var(--korall-ljus); padding:3px 9px; border-radius:28px; display:inline-block; }}
.instlank {{ margin-top:11px; font-size:12.5px; font-weight:700; color:var(--korall);
  display:flex; align-items:center; gap:6px; }}
.pil {{ width:14px; height:14px; transition:transform .15s; }}
.instkort:hover .pil {{ transform:translateX(3px); }}

/* --- Detaljvy --- */
.detalj {{ margin-top:18px; display:none; }}
.detalj.visas {{ display:block; }}
.detaljtopp {{ display:flex; align-items:center; justify-content:space-between;
  gap:16px; flex-wrap:wrap; margin-bottom:14px; }}
.detaljrubrik {{ font-size:20px; font-weight:700; letter-spacing:-.5px; }}
.detaljrubrik span {{ color:var(--svag); font-weight:500; font-size:14px; margin-left:9px; }}
.knapp {{ display:inline-flex; align-items:center; gap:7px; background:var(--korall);
  color:#fff; border:none; border-radius:28px; padding:9px 19px; font:inherit;
  font-size:13.5px; font-weight:600; cursor:pointer; transition:background .15s; }}
.knapp:hover {{ background:var(--korall-mork); }}
.knapp.sekundar {{ background:transparent; color:var(--korall);
  border:1.5px solid var(--korall); }}
.knapp.sekundar:hover {{ background:var(--korall); color:#fff; }}
tr.utanfor td {{ opacity:.5; }}

.kammarkort {{ background:var(--kortbg); border:1px solid var(--linje);
  border-radius:16px; padding:26px 24px 20px; box-shadow:var(--skugga); }}
.kammare {{ width:100%; max-width:700px; height:auto; display:block; margin:0 auto; }}
.plats {{ transition:opacity .12s; }}
.kammare:hover .plats {{ opacity:.42; }}
.kammare .plats:hover {{ opacity:1; }}
.majoritetslinje {{ stroke:var(--markorbg); stroke-width:.026;
  stroke-dasharray:.07 .05; stroke-linecap:round; opacity:.85; }}
.majoritetsetikett {{ fill:var(--markortext); font-family:'Work Sans',sans-serif;
  font-size:.135px; font-weight:800; letter-spacing:-.004px;
  dominant-baseline:middle; }}
.majoritetsplatta {{ fill:var(--markorbg); stroke:var(--kortbg); stroke-width:.018; }}
.blocklinje {{ stroke:#EE2020; stroke-width:.032; stroke-linecap:round; opacity:.9; }}
.blockplatta {{ fill:#EE2020; stroke:var(--kortbg); stroke-width:.018; }}
.blocketikett {{ fill:#fff; font-family:'Work Sans',sans-serif; font-size:.135px;
  font-weight:800; letter-spacing:-.004px; dominant-baseline:middle; }}
.kammartext {{ fill:var(--text); font-family:'Work Sans',sans-serif;
  font-size:.20px; font-weight:800; text-anchor:middle; letter-spacing:-.006px; }}
.kammartext.liten {{ fill:var(--svag); font-size:.098px; font-weight:600; }}
.kammarlegend {{ display:flex; flex-wrap:wrap; justify-content:center; gap:8px 20px;
  margin-top:14px; padding-top:16px; border-top:1px solid var(--linje); }}
.kammarlegend-item {{ display:flex; align-items:center; gap:6px; font-size:13px; }}
.kammarnotis {{ text-align:center; font-size:12.5px; color:var(--svag);
  margin-top:12px; max-width:560px; margin-left:auto; margin-right:auto;
  line-height:1.55; }}
.legendantal {{ font-weight:700; font-variant-numeric:tabular-nums; color:var(--svag); }}
/* Egen tooltip, se skriptet. Browserns egen dröjer för länge. */
.snabbtip {{ position:fixed; z-index:999; pointer-events:none;
  background:var(--text); color:var(--bg); padding:8px 12px; border-radius:9px;
  font-size:12.5px; line-height:1.45; max-width:320px;
  box-shadow:0 6px 20px rgba(0,0,0,.22); }}
.snabbtip strong {{ display:block; font-size:13.5px; }}
.snabbtip span {{ display:block; opacity:.82; }}
.snabbtip[hidden] {{ display:none; }}
canvas {{ width:100%; height:auto; display:block; }}
.grafkort {{ background:var(--kortbg); border:1px solid var(--linje);
  border-radius:16px; padding:20px; box-shadow:var(--skugga); }}
.nivaval {{ display:flex; flex-wrap:wrap; gap:8px; margin:26px 0 8px;
  padding-bottom:14px; border-bottom:1px solid var(--linje); align-items:center; }}
/* Fördjupningssidorna. De låg tidigare som diskreta textlänkar i
   nivåraden och upptäcktes inte, så de får egna kort. */
.fordjupning {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
  gap:14px; margin:18px 0 4px; }}
.fkort {{ display:block; text-decoration:none; color:inherit;
  background:var(--kortbg); border:1px solid var(--linje); border-radius:14px;
  padding:16px 20px; transition:border-color .15s, box-shadow .15s; }}
.fkort:hover {{ border-color:var(--korall); box-shadow:var(--skugga-hog); }}
.ftitel {{ display:flex; align-items:center; gap:7px; font-size:15px;
  font-weight:700; color:var(--korall); }}
.ftext {{ font-size:13px; color:var(--svag); margin-top:2px; }}
.fkort .pil {{ width:15px; height:15px; transition:transform .15s; }}
.fkort:hover .pil {{ transform:translateX(3px); }}
.nivaknapp {{ background:transparent; color:var(--korall); font:inherit;
  font-size:13.5px; font-weight:600; border:1.5px solid var(--korall);
  border-radius:28px; padding:8px 19px; cursor:pointer; transition:all .15s; }}
.nivaknapp:hover {{ background:var(--korall-ljus); }}
.nivaknapp.aktiv {{ background:var(--korall); color:#fff; }}
.omradesrad {{ display:flex; flex-wrap:wrap; align-items:center; gap:10px;
  margin:22px 0 16px; }}
.sokruta {{ flex:1; min-width:180px; max-width:300px; font:inherit; font-size:13.5px;
  padding:9px 16px; border:1px solid var(--linje); border-radius:28px;
  background:var(--kortbg); color:var(--text); }}
.sokruta:focus {{ outline:none; border-color:var(--korall); }}
.laddar {{ text-align:center; color:var(--svag); padding:26px 12px;
  font-size:13.5px; }}
/* Raderna är klickbara. Eftersom hover inte finns på touchskärmar markeras
   det med en pil i sista kolumnen och en uppmaning ovanför tabellen. */
tr.klickbar {{ cursor:pointer; }}
tr.klickbar:hover {{ background:var(--korall-ljus); }}
tr.klickbar:hover .inst {{ color:var(--korall-mork); }}
tr.klickbar:focus-visible {{ outline:2px solid var(--korall); outline-offset:-2px; }}
/* Pilen sitter intill områdesnamnet i stället för i en egen kolumn längst
   till höger. Tabellen är bredare än sin behållare och scrollar horisontellt,
   så en kolumn där hade legat utanför synfältet. */
.radpil {{ display:inline-flex; margin-left:7px; color:var(--korall);
  opacity:.5; vertical-align:-2px; }}
.radpil .pil {{ width:14px; height:14px; }}
.omradesnamn {{ font-weight:600; }}
.lokalprick {{ display:inline-block; margin-left:7px; font-size:10.5px;
  font-weight:700; padding:1px 7px; border-radius:28px;
  background:var(--korall-ljus); color:var(--korall-mork); cursor:help;
  vertical-align:1px; }}
.lokalnotis a {{ color:var(--korall-mork); font-weight:700; }}
tr.klickbar:hover .radpil {{ opacity:1; }}
tr.klickbar:hover .radpil .pil {{ transform:translateX(2px); }}

/* Sorterbara rubriker. Knappen ärver rubrikens utseende så att tabellen ser
   oförändrad ut, med en pil som visar aktiv kolumn och riktning. */
.sorterbar th {{ padding:0; }}
.sortknapp {{ width:100%; background:none; border:none; font:inherit;
  color:inherit; letter-spacing:inherit; text-transform:inherit;
  cursor:pointer; padding:13px 12px; text-align:left; position:relative;
  display:block; }}
.tal .sortknapp {{ text-align:right; padding-right:19px; }}
.sortknapp:hover {{ color:var(--korall); }}
.sortknapp::after {{ content:'↕'; position:absolute; right:5px;
  opacity:0; font-size:10px; font-weight:400; }}
.tal .sortknapp::after {{ right:5px; }}
.sortknapp:hover::after {{ opacity:.45; }}
.sortknapp.sorterad {{ color:var(--korall); }}
.sortknapp.sorterad::after {{ content:'↑'; opacity:1; font-size:11px;
  font-weight:700; }}
.sortknapp.sorterad.fallande::after {{ content:'↓'; }}
.sortknapp:focus-visible {{ outline:2px solid var(--korall); outline-offset:-2px; }}

.klicktips {{ display:flex; align-items:center; gap:9px; margin:0 0 14px;
  padding:11px 15px; background:var(--korall-ljus); border-radius:10px;
  font-size:13.5px; font-weight:600; color:var(--korall-mork); max-width:900px; }}
.klicktips .pil {{ flex:none; width:16px; height:16px; }}

.detaljkort {{ background:var(--kortbg); border:1px solid var(--linje);
  border-radius:16px; padding:24px; box-shadow:var(--skugga); }}
.detaljhuvud {{ display:flex; align-items:flex-start; justify-content:space-between;
  gap:16px; flex-wrap:wrap; margin-bottom:18px; }}
.detaljnamn {{ font-size:26px; font-weight:800; letter-spacing:-.9px; line-height:1.15; }}
.detaljmeta {{ font-size:13px; color:var(--svag); margin-top:2px; }}

/* Mandatbandet visar partierna i politisk ordning med majoritetsgränsen
   utsatt, så det går att se direkt vem som är nära att styra. */
.mandatband {{ position:relative; display:flex; height:34px; border-radius:7px;
  overflow:hidden; background:var(--panel); }}
.bandbit {{ height:100%; }}
.bandgrans {{ position:absolute; top:-4px; bottom:-4px; width:2px;
  background:var(--text); opacity:.85; }}
.bandgrans::after {{ content:''; position:absolute; left:-3px; top:-3px;
  width:8px; height:8px; border-radius:50%; background:var(--text); }}
.bandlegend {{ display:flex; justify-content:space-between; gap:12px;
  margin-top:9px; font-size:12.5px; color:var(--svag); }}
.bandlegend .bl {{ font-weight:600; }}
.bandlegend .v {{ color:#EE2020; }}
.bandlegend .h {{ color:#0F8FCC; }}

.dstaplar {{ margin-top:22px; padding-top:18px; border-top:1px solid var(--linje);
  display:flex; flex-direction:column; gap:9px; }}
.kammargrid {{ display:grid; grid-template-columns:1.55fr 1fr; gap:22px;
  align-items:center; margin-bottom:20px; }}
.kammare.liten {{ max-width:100%; }}
.kammare.liten .majoritetslinje {{ stroke-width:.034; }}
.blockhalva {{ display:flex; flex-direction:column; gap:12px; }}
.blockpost .bpnamn {{ white-space:nowrap; }}
.blockpost {{ background:var(--panel); border-radius:11px; padding:13px 16px; }}
.bpnamn {{ font-size:11.5px; text-transform:uppercase; letter-spacing:1px;
  color:var(--svag); font-weight:700; }}
.bpvarde {{ font-size:27px; font-weight:800; letter-spacing:-1px; line-height:1.2; }}
.bpvarde.v {{ color:#EE2020; }} .bpvarde.h {{ color:#0F8FCC; }}
.bpvarde.c {{ color:#0B7A2E; }} .bpvarde.sd {{ color:#A89000; }}
.bpvarde.o {{ color:var(--svag); }}
:root[data-theme="dark"] .bpvarde.sd,
:root:not([data-theme="light"]) .bpvarde.sd {{ color:#DDDD00; }}
:root[data-theme="dark"] .bpvarde.c,
:root:not([data-theme="light"]) .bpvarde.c {{ color:#7ED694; }}
.lagetext {{ margin:11px 0 0; font-size:13px; color:var(--svag);
  line-height:1.55; }}
.kammargrid .blockhalva {{ display:grid;
  grid-template-columns:repeat(auto-fit,minmax(88px,1fr)); gap:10px; }}
.diff {{ font-size:13px; font-weight:700; letter-spacing:0; }}
.diff.upp {{ color:var(--gron); }}
.diff.ned {{ color:var(--korall); }}
.diff.lika {{ color:var(--svag); }}
.dstapelhuvud {{ display:grid; grid-template-columns:118px 1fr 54px 62px 96px;
  gap:11px; font-size:10.5px; text-transform:uppercase; letter-spacing:.9px;
  color:var(--svag); font-weight:700; padding-bottom:5px; }}
.dstapelhuvud span:nth-child(3), .dstapelhuvud span:nth-child(4) {{ text-align:right; }}
.dstapelhuvud span:nth-child(5) {{ text-align:right; }}
.kallmarke {{ display:inline-block; font-size:11px; font-weight:700;
  padding:2px 9px; border-radius:28px; white-space:nowrap; }}
.kallmarke.matt {{ background:rgba(125,186,116,.2); color:var(--gron); }}
.kallmarke.skalat {{ background:var(--panel); color:var(--svag); }}
.kallcell {{ font-size:12.5px; color:var(--svag); max-width:340px; }}
.matningsmeta {{ font-size:11.5px; color:var(--svag); font-weight:400;
  margin-top:2px; }}
/* Kandidatprognosen. Namnen ligger som brickor som radbryter i stället för
   som en lista, så att ett parti med trettio mandat tar tre rader och inte
   trettio. */
.kandblock {{ margin-top:22px; padding-top:20px;
  border-top:1px solid var(--linje); }}
.kandparti {{ margin-bottom:14px; }}
.kandhuvud {{ display:flex; align-items:center; gap:8px; margin-bottom:7px;
  font-size:13.5px; }}
.kandmandat {{ color:var(--svag); font-size:12.5px; }}
.kandvarn {{ font-size:10.5px; font-weight:700; padding:1px 8px;
  border-radius:28px; background:var(--korall-ljus); color:var(--korall-mork);
  cursor:help; }}
.kandnamn {{ display:flex; flex-wrap:wrap; gap:5px; }}
.kandbricka {{ display:inline-flex; align-items:baseline; gap:5px;
  background:var(--panel); border-radius:6px; padding:3px 9px 3px 6px;
  font-size:12.5px; cursor:help; white-space:nowrap; }}
.kandbricka:hover {{ background:var(--korall-ljus); color:var(--korall-mork); }}
.kandnr {{ font-size:10px; font-weight:700; color:var(--svag);
  font-variant-numeric:tabular-nums; min-width:12px; text-align:right; }}
.kandbricka:hover .kandnr {{ color:var(--korall); }}
.kandladdar, .kandfel {{ font-size:13px; color:var(--svag); margin:6px 0 0; }}
.kandfel {{ color:var(--korall-mork); max-width:620px; line-height:1.6; }}
.kandfel code {{ background:var(--panel); padding:1px 6px; border-radius:4px;
  font-size:12px; }}
.kandsaknas {{ margin-top:14px; padding:12px 16px; background:var(--panel);
  border-radius:10px; font-size:12.5px; color:var(--svag); }}
.kandsaknas ul {{ margin:6px 0 0; padding-left:18px; }}
.kandsaknas li {{ margin-bottom:3px; }}
@media (max-width:640px) {{
  .kandbricka {{ font-size:11.5px; padding:3px 7px 3px 5px; }}
}}

.vkblock {{ margin-top:22px; padding-top:20px;
  border-top:1px solid var(--linje); }}
.vkblock .tabellwrap {{ border:none; }}
.vkblock th {{ padding:8px 10px; }}
.vkblock td {{ padding:8px 10px; }}
.vkdiff {{ display:block; font-size:10.5px; font-weight:600; }}
.vkdiff.upp {{ color:var(--gron); }}
.vkdiff.ned {{ color:var(--korall); }}

.metodkort {{ background:var(--kortbg); border:1px solid var(--linje);
  border-radius:16px; padding:26px; box-shadow:var(--skugga); }}
.metodingress {{ font-size:15px; margin:0 0 22px; max-width:660px; }}
.metodsteg {{ display:flex; flex-direction:column; gap:14px;
  padding-bottom:22px; margin-bottom:22px; border-bottom:1px solid var(--linje); }}
.steg {{ display:flex; gap:15px; align-items:flex-start; }}
.stegnr {{ flex:none; width:30px; height:30px; border-radius:50%;
  background:var(--korall); color:#fff; font-weight:800; font-size:14px;
  display:flex; align-items:center; justify-content:center; }}
.stegtext strong {{ display:block; font-size:14.5px; margin-bottom:2px; }}
.stegtext p {{ margin:0; font-size:13.5px; color:var(--svag); max-width:640px; }}
.metodtabell {{ width:100%; border-collapse:collapse; max-width:560px;
  margin-bottom:6px; }}
.metodtabell th {{ background:transparent; padding:8px 10px 7px;
  border-bottom:1px solid var(--linje); position:static; }}
.metodtabell td {{ padding:7px 10px; font-size:13.5px; }}
.metodtabell .pos {{ color:var(--gron); font-weight:700; }}
.metodtabell .neg {{ color:var(--korall); font-weight:700; }}
.metodnot {{ font-size:12.5px; color:var(--svag); max-width:660px;
  margin:10px 0 0; line-height:1.6; }}
.metodrutor {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(238px,1fr));
  gap:14px; margin-top:24px; padding-top:22px; border-top:1px solid var(--linje); }}
.metodruta {{ background:var(--panel); border-radius:12px; padding:16px 18px; }}
.mrubrik {{ font-size:11.5px; text-transform:uppercase; letter-spacing:1px;
  font-weight:700; color:var(--korall); margin-bottom:6px; }}
.metodruta p {{ margin:0; font-size:13px; color:var(--svag); line-height:1.6; }}
.koalblock {{ margin-top:22px; padding-top:20px;
  border-top:1px solid var(--linje); }}
.koalrubrik {{ font-size:12px; text-transform:uppercase; letter-spacing:1.3px;
  font-weight:700; color:var(--svag); margin-bottom:12px; }}
.koalhuvud, .koalrad {{ display:grid;
  grid-template-columns:168px 1fr 46px 88px 62px; gap:11px; align-items:center; }}
.koalhuvud {{ font-size:10.5px; text-transform:uppercase; letter-spacing:.9px;
  color:var(--svag); font-weight:700; padding-bottom:6px; }}
.koalhuvud span:nth-child(3) {{ text-align:right; }}
.koalhuvud span:nth-child(5) {{ text-align:right; }}
.koalrad {{ padding:7px 0; border-top:1px solid var(--linje); }}
.koalrad.vinner .knamn {{ font-weight:700; }}
.knamn {{ font-size:13.5px; line-height:1.3; }}
.kpartier {{ display:block; font-size:11.5px; color:var(--svag); font-weight:500; }}
.kbar {{ position:relative; height:16px; background:var(--panel);
  border-radius:4px; overflow:hidden; }}
.kfyll {{ height:100%; background:var(--svag); opacity:.45; border-radius:4px; }}
.koalrad.vinner .kfyll {{ background:var(--gron); opacity:1; }}
.kgrans {{ position:absolute; top:-2px; bottom:-2px; width:2px;
  background:var(--text); opacity:.6; }}
.kmandat {{ text-align:right; font-weight:700; font-variant-numeric:tabular-nums;
  font-size:13.5px; }}
.kmarke {{ display:inline-block; font-size:11px; font-weight:700;
  padding:2px 9px; border-radius:28px; white-space:nowrap; }}
.kmarke.ja {{ background:rgba(125,186,116,.2); color:var(--gron); }}
.kmarke.nej {{ background:var(--panel); color:var(--svag);
  font-variant-numeric:tabular-nums; }}
.kstyr {{ text-align:right; font-size:13px; color:var(--svag);
  font-variant-numeric:tabular-nums; }}
.koalnot {{ font-size:12px; color:var(--svag); margin:12px 0 0; line-height:1.6; }}
@media (max-width:640px) {{
  .koalhuvud, .koalrad {{ grid-template-columns:120px 1fr 38px 34px 40px; gap:7px; }}
  .kmarke.ja {{ padding:2px 5px; font-size:10px; }}
}}
.lokalnotis {{ margin-top:18px; background:var(--korall-ljus);
  border-left:3px solid var(--korall); border-radius:0 8px 8px 0;
  padding:13px 16px; font-size:13px; color:var(--text); }}
.ddiff {{ text-align:right; font-variant-numeric:tabular-nums; }}
.dstapelrad {{ display:grid; grid-template-columns:118px 1fr 54px 62px 96px;
  align-items:center; gap:11px; }}
.dparti {{ font-weight:700; font-size:13px; line-height:1.25;
  overflow-wrap:anywhere; }}
.dstapelyta {{ background:var(--panel); border-radius:4px; height:20px; }}
.dstapel {{ height:100%; border-radius:4px; min-width:2px; }}
.dvarde {{ text-align:right; font-weight:700; font-variant-numeric:tabular-nums;
  font-size:13.5px; }}
.dmandat {{ text-align:right; font-size:12.5px; color:var(--svag);
  font-variant-numeric:tabular-nums; }}
@media (max-width:700px) {{
  .kammargrid {{ grid-template-columns:1fr; }}
  .blockhalva {{ flex-direction:row; }}
  .blockpost {{ flex:1; }}
}}
@media (max-width:560px) {{
  .dstapelrad, .dstapelhuvud {{ grid-template-columns:84px 1fr 46px 44px 58px;
    gap:7px; }}
  .detaljnamn {{ font-size:21px; }}
  .bpvarde {{ font-size:22px; }}
}}
.styrerad {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:12px; margin-bottom:16px; }}
.styrekort {{ background:var(--panel); border:1px solid var(--linje);
  border-radius:12px; padding:14px 16px; }}
.styrekort .n {{ font-size:27px; font-weight:800; letter-spacing:-1px; line-height:1.15; }}
.styrekort .e {{ font-size:12px; color:var(--svag); font-weight:500; }}
/* Mandatläget färgas efter vem som når majoritet, inte efter block. Lägen där
   ingen har egen majoritet får en neutral färg, eftersom utfallet där avgörs av
   förhandlingar snarare än av mandaten. */
.lagemarke {{ display:inline-block; font-size:11.5px; font-weight:700;
  padding:3px 10px; border-radius:28px; white-space:nowrap; cursor:help; }}
.lagemarke.vanster {{ background:rgba(238,32,32,.13); color:#C81E1E; }}
.lagemarke.vanster_c {{ background:rgba(0,153,51,.14); color:#0B7A2E; }}
.lagemarke.borgerlig_c {{ background:rgba(0,153,51,.14); color:#0B7A2E; }}
.lagemarke.hoger_sd {{ background:rgba(82,189,236,.18); color:#0F7FB5; }}
.lagemarke.hoger_flera {{ background:rgba(82,189,236,.18); color:#0F7FB5; }}
.lagemarke.lokala_vagmastare {{ background:var(--korall-ljus);
  color:var(--korall-mork); }}
.lagemarke.oklart {{ background:var(--panel); color:var(--svag); }}
:root[data-theme="dark"] .lagemarke.vanster,
:root:not([data-theme="light"]) .lagemarke.vanster {{ color:#FF8A8A; }}
:root[data-theme="dark"] .lagemarke.hoger_sd,
:root[data-theme="dark"] .lagemarke.hoger_flera,
:root:not([data-theme="light"]) .lagemarke.hoger_sd,
:root:not([data-theme="light"]) .lagemarke.hoger_flera {{ color:#7CCBF0; }}
:root[data-theme="dark"] .lagemarke.vanster_c,
:root[data-theme="dark"] .lagemarke.borgerlig_c,
:root:not([data-theme="light"]) .lagemarke.vanster_c,
:root:not([data-theme="light"]) .lagemarke.borgerlig_c {{ color:#7ED694; }}
.grafyta {{ position:relative; }}
#trend {{ cursor:crosshair; }}
.tooltip {{ position:absolute; pointer-events:none; z-index:5;
  background:var(--kortbg); border:1px solid var(--linje); border-radius:11px;
  box-shadow:var(--skugga-hog); padding:11px 13px; min-width:132px;
  font-size:12.5px; line-height:1.5; transition:opacity .09s; }}
.tooltip[hidden] {{ display:none; }}
.tooltipdatum {{ font-weight:700; font-size:12px; color:var(--svag);
  letter-spacing:.4px; text-transform:uppercase; margin-bottom:7px;
  padding-bottom:6px; border-bottom:1px solid var(--linje); }}
.tooltiprad {{ display:flex; align-items:center; gap:7px; white-space:nowrap; }}
.tooltiprad .tp {{ width:9px; height:9px; border-radius:50%; flex:none; }}
.tooltiprad .tn {{ font-weight:700; width:24px; }}
.tooltiprad .tv {{ margin-left:auto; font-weight:600;
  font-variant-numeric:tabular-nums; }}
.tooltipblock {{ margin-top:7px; padding-top:6px; border-top:1px solid var(--linje);
  font-size:12px; color:var(--svag); }}
.tooltipblock div {{ display:flex; gap:9px; }}
.tooltipblock span {{ margin-left:auto; font-weight:700;
  font-variant-numeric:tabular-nums; }}
.legend {{ display:flex; flex-wrap:wrap; gap:14px; margin-top:14px;
  padding-top:14px; border-top:1px solid var(--linje); }}
.legenditem {{ display:flex; align-items:center; gap:6px; font-size:12.5px;
  font-weight:600; color:var(--svag); }}
.legendprick {{ width:10px; height:10px; border-radius:50%; }}

footer {{ margin-top:60px; padding:26px 0 0; border-top:2px solid var(--korall);
  color:var(--svag); font-size:12.5px; line-height:1.75; }}
footer strong:first-child {{ display:inline; }}
footer {{ max-width:1320px; }}
.metodkort p, .metodnot, .metodingress {{ max-width:820px; }}
footer strong {{ color:var(--text); }}
@media (max-width:640px) {{
  .nyckeltal {{ gap:22px; }} .blockmandat {{ font-size:42px; }}
  .instrad {{ grid-template-columns:1fr 1fr; }}
}}
</style></head><body>

<div class="topp"><div class="toppinner">
  <a class="logo" href="https://lysio.se" target="_blank" rel="noopener"
     aria-label="Lysio Research">
    <span class="logoruta">
      <img class="logo-ljus" src="{logo_farg}" alt="Lysio Research"
           width="188" height="88">
      <img class="logo-mork" src="{logo_vit}" alt="" aria-hidden="true"
           width="97" height="88">
    </span>
  </a>
  <button class="temaknapp" id="tema">Mörkt läge</button>
</div></div>

<div class="hero"><div class="heroinner">
  <span class="etikett">Valprognos</span>
  <h1>Valet 2026</h1>
  <p class="ingress">Prognos för alla tre val: riksdag, region och kommun.
  Bygger på {meta['antal_matningar']} opinionsmätningar från
  {meta['antal_institut']} institut, justerade för husfaktorer och simulerade
  {sim_text} gånger.</p>
  <div class="nyckeltal">
    <div class="nyckel"><div class="n">{meta['dagar_kvar']}</div>
      <div class="e">dagar till valdagen</div></div>
    <div class="nyckel"><div class="n">{meta['antal_matningar']}</div>
      <div class="e">mätningar i modellen</div></div>
    <div class="nyckel"><div class="n">{meta['antal_institut']}</div>
      <div class="e">institut</div></div>
    <div class="nyckel"><div class="n">{meta['senaste_matning']}</div>
      <div class="e">senaste mätning</div></div>
  </div>
</div></div>

<div class="wrap">

<div class="nivaval">
  <button class="nivaknapp aktiv" data-niva="riksdag">Riksdagsval</button>
  <button class="nivaknapp" data-niva="region">Regionval</button>
  <button class="nivaknapp" data-niva="kommun">Kommunval</button>
</div>

<div id="riksdagsvy">

<div class="fordjupning">
  <a class="fkort" href="partier_2026.html">
    <div class="ftitel">Parti för parti {_pil()}</div>
    <div class="ftext">Trend, mandat och i vilka valkretsar de hamnar</div>
  </a>
  <a class="fkort" href="ledamoter_2026.html">
    <div class="ftitel">Alla ledamöter {_pil()}</div>
    <div class="ftext">Samtliga {antal_ledamoter} prognosticerade riksdagsledamöter</div>
  </a>
  <a class="fkort" href="scenarier_2026.html">
    <div class="ftitel">Scenarier {_pil()}</div>
    <div class="ftext">Om L klarar spärren, om sommartrenden håller, om valspurten upprepar sig</div>
  </a>
</div>
<h2>Prognos</h2>
<div class="sektionsrubrik">Så skulle riksdagen se ut</div>
{kammare}

<div class="sektionsrubrik" style="margin-top:44px">Blocken</div>
<div class="blockrad">{''.join(blockkort)}</div>
<div class="notis">Ett block behöver 175 av 349 mandat för egen majoritet, markerat
med strecket i mandatstapeln. Sannolikheten att inget block når dit är
{cfg.formatera_sannolikhet(block['oavgjort'])}.</div>

<h2>Partier</h2>
<div class="sektionsrubrik">Väljarstöd och mandat</div>
<div class="tabellwrap"><table>
<thead><tr><th>Parti</th><th>Stöd</th><th>Prognos</th><th class="tal">Mot 2022</th>
<th>80%-spann</th><th>Mandat</th><th class="tal">Mot 2022</th>
<th>Mandatspann</th></tr></thead>
<tbody>{''.join(partirader)}</tbody></table></div>

<h2>Utveckling</h2>
<div class="sektionsrubrik">Trend över tid</div>
<div class="grafkort">
  <div class="grafyta">
    <canvas id="trend" width="1080" height="360"></canvas>
    <div class="tooltip" id="tooltip" hidden></div>
  </div>
  <div class="legend">{''.join(
      f'<div class="legenditem"><span class="legendprick" style="background:{cfg.PARTIFARG[p]}"></span>{p}</div>'
      for p in cfg.PARTIER)}</div>
</div>

<h2>Regeringsbildning</h2>
<div class="sektionsrubrik">Möjliga underlag</div>
<div class="tabellwrap"><table>
<thead><tr><th>Alternativ</th><th>Partier</th><th>Mandat</th><th>Spann</th>
<th>Sannolikhet för majoritet</th></tr></thead>
<tbody>{''.join(regrader)}</tbody></table></div>
<div class="notis">Sannolikheten avser att partierna tillsammans når minst 175 mandat.
Den säger inget om partiernas vilja att regera ihop, bara om det aritmetiska
underlaget finns. Alternativen överlappar och summerar därför inte till 100 procent.</div>

<h2>Källor</h2>
<div class="sektionsrubrik">Instituten och deras genomslag</div>
<div class="instrad">{''.join(instkort)}</div>
<div class="notis">Viktandelen visar hur mycket varje institut faktiskt påverkar
prognosen. Den beror på kvalitetsvikt, urvalsstorlek och framför allt hur färska
mätningarna är: vikten halveras var {cfg.HALVERINGSTID_DAGAR:.0f}:e dag. Ett institut
som mäter sällan får därför litet genomslag även med hög kvalitetsvikt.
Klicka på ett institut för att se alla dess mätningar.</div>

<div class="detalj" id="detalj">
  <div class="detaljtopp">
    <div class="detaljrubrik" id="detaljrubrik"></div>
    <button class="knapp sekundar" id="stang">Stäng</button>
  </div>
  <div class="tabellwrap"><table>
    <thead><tr><th>Datum</th><th>Ålder</th>{partikolumner}
    <th class="tal">V+S+MP+C</th><th class="tal">L+M+KD+SD</th><th class="tal">Vikt</th></tr></thead>
    <tbody id="detaljkropp"></tbody>
  </table></div>
</div>

<h2>Senast publicerat</h2>
<div class="sektionsrubrik">De femton senaste mätningarna</div>
<div class="tabellwrap"><table>
<thead><tr><th>Institut</th><th>Datum</th>{partikolumner}
<th class="tal">V+S+MP+C</th><th class="tal">L+M+KD+SD</th><th class="tal">Vikt</th></tr></thead>
<tbody>{''.join(senasterader)}</tbody></table></div>
<div class="notis">Siffrorna är instituten egna, opåverkade av modellens
husfaktorjustering. Viktkolumnen visar mätningens andel av modellens totala vikt;
ett streck betyder att mätningen ligger utanför tidsfönstret på
{cfg.MAX_ALDER_DAGAR:.0f} dagar.</div>

<h2>Metod</h2>
<div class="sektionsrubrik">Husfaktorer</div>
<div class="tabellwrap"><table>
<thead><tr><th>Institut</th><th class="tal">Mätn.</th>
{''.join(f'<th class="tal">{p}</th>' for p in cfg.PARTIER)}</tr></thead>
<tbody>{''.join(hfrader)}</tbody></table></div>
<div class="notis">Husfaktorn är institutets systematiska avvikelse från övriga
institut, i procentenheter. Ett positivt värde betyder att institutet mäter
partiet högre än konsensus. Modellen korrigerar bort
{cfg.HUSFAKTOR_DAMPNING*100:.0f} procent av den skattade avvikelsen.</div>

</div>

{lokal_html}

<footer>
  <strong>Om modellen.</strong> Mätningarna viktas efter institutets kvalitet,
  urvalsstorlek och färskhet (halveringstid {cfg.HALVERINGSTID_DAGAR:.0f} dagar),
  justeras för husfaktorer och körs genom {sim_text} simulerade
  valutfall. Mandaten fördelas med jämkade uddatalsmetoden och fyraprocentsspärren,
  räknat på riket som en valkrets. I verkligheten fördelas 310 fasta mandat i 29
  valkretsar och 39 utjämningsmandat korrigerar avvikelsen. Utjämningen räcker
  inte alltid hela vägen: mot 2018 och 2022 träffar förenklingen exakt, men 2010
  och 2014 hade den gett små partier några mandat för mycket på de storas
  bekostnad. Osäkerheten är kalibrerad mot valet 2022, där modellen hade ett medelabsolutfel
  på 0,73 procentenheter och gav vänsterblocket 174 mandat mot faktiska 173.
  Kalibreringen vilar på en enda valcykel och bör tolkas med det i åtanke.<br>
  <strong>Källa.</strong> Opinionsmätningar sammanställda på svenska Wikipedia.
  Genererad {meta['genererad']}.
</footer>

</div>
<script>
const T = {trend_json};
const ALLA = {alla_json};
const PARTIER = {partier_json};
const FARGER = {partifarg_json};

  /* --- Snabb tooltip ---------------------------------------------------
     Webbläsarens egen title-tooltip dröjer nästan en sekund, vilket gör att
     de flesta aldrig upptäcker den. Vi flyttar texten till data-tip och ritar
     en egen ruta som visas direkt. */
  (function() {{
    const ruta = document.createElement('div');
    ruta.className = 'snabbtip';
    ruta.hidden = true;
    document.body.appendChild(ruta);

    function text(el) {{
      if (el.getAttribute('data-tip')) return el.getAttribute('data-tip');

      /* SVG-element bär sin tooltip i ett title-barn, inte i ett attribut. */
      let t = el.getAttribute('title');
      if (!t) {{
        const barn = el.querySelector ? el.querySelector(':scope > title') : null;
        if (barn) {{
          t = barn.textContent;
          barn.remove();            // annars visar webbläsaren sin egen ändå
        }}
      }} else {{
        el.removeAttribute('title');
      }}
      if (t) el.setAttribute('data-tip', t);
      return t;
    }}

    function visa(el, x, y) {{
      const t = text(el);
      if (!t) return;
      ruta.innerHTML = t.split('\\n').map(function(rad, i) {{
        return i === 0 ? '<strong>' + rad + '</strong>' : '<span>' + rad + '</span>';
      }}).join('');
      ruta.hidden = false;
      const b = ruta.getBoundingClientRect();
      let vx = x + 14, vy = y + 16;
      if (vx + b.width > window.innerWidth - 8) vx = x - b.width - 14;
      if (vy + b.height > window.innerHeight - 8) vy = y - b.height - 14;
      ruta.style.left = Math.max(8, vx) + 'px';
      ruta.style.top = Math.max(8, vy) + 'px';
    }}

    /* SVG-element saknar closest i äldre webbläsare, därav kontrollen. */
    function traff(mal) {{
      if (!mal) return null;
      /* Kammarens punkter är SVG-cirklar med ett title-barn. */
      if (mal.tagName === 'circle' || mal.tagName === 'title') {{
        return mal.tagName === 'title' ? mal.parentNode : mal;
      }}
      if (!mal.closest) return null;
      return mal.closest('[title],[data-tip]');
    }}

    document.addEventListener('mouseover', function(e) {{
      const el = traff(e.target);
      if (el) visa(el, e.clientX, e.clientY);
    }});
    document.addEventListener('mousemove', function(e) {{
      if (ruta.hidden) return;
      const el = traff(e.target);
      if (el) visa(el, e.clientX, e.clientY);
      else ruta.hidden = true;
    }});
    document.addEventListener('mouseout', function(e) {{
      if (!traff(e.relatedTarget)) ruta.hidden = true;
    }});
    document.addEventListener('click', function() {{ ruta.hidden = true; }});
  }})();

/* --- Tema --- */
(function() {{
  const knapp = document.getElementById('tema');
  const rot = document.documentElement;
  let sparat = null;
  try {{ sparat = localStorage.getItem('valprognos-tema'); }} catch (e) {{}}
  if (sparat) rot.setAttribute('data-theme', sparat);
  function motet() {{
    return rot.getAttribute('data-theme') ||
      (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  }}
  function uppdatera() {{ knapp.textContent = motet() === 'dark' ? 'Ljust läge' : 'Mörkt läge'; }}
  uppdatera();
  knapp.addEventListener('click', () => {{
    const ny = motet() === 'dark' ? 'light' : 'dark';
    rot.setAttribute('data-theme', ny);
    try {{ localStorage.setItem('valprognos-tema', ny); }} catch (e) {{}}
    uppdatera(); ritaTrend();
  }});
}})();

/* --- Trendgraf --- */
/* Geometrin sparas vid varje ritning så att hover-logiken kan översätta
   muspositionen till ett dataindex, och rita markörer på rätt plats. */
let G = null;
let hoverIndex = -1;

function ritaTrend() {{
  const c = document.getElementById('trend');
  if (!c) return;
  const dpr = window.devicePixelRatio || 1;
  const W = c.clientWidth || 1080, H = 360;
  c.width = W * dpr; c.height = H * dpr;
  const g = c.getContext('2d');
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, W, H);

  const stil = getComputedStyle(document.documentElement);
  const linjefarg = stil.getPropertyValue('--linje').trim() || '#E3E8F0';
  const textfarg = stil.getPropertyValue('--svag').trim() || '#69727D';

  const mL = 42, mR = 52, mT = 16, mB = 30;
  const bw = W - mL - mR, bh = H - mT - mB;
  const n = T.datum.length;
  if (!n) return;
  let max = 0;
  for (const p in T.serier) for (const v of T.serier[p]) if (v > max) max = v;
  max = Math.ceil(max / 5) * 5;

  const x = i => mL + (n < 2 ? bw / 2 : i / (n - 1) * bw);
  const y = v => mT + bh - v / max * bh;
  G = {{ mL, mR, mT, mB, bw, bh, n, max, W, H, x, y }};

  g.strokeStyle = linjefarg; g.fillStyle = textfarg; g.lineWidth = 1;
  g.font = "11px 'Work Sans',sans-serif";
  for (let v = 0; v <= max; v += 5) {{
    g.beginPath(); g.moveTo(mL, y(v)); g.lineTo(mL + bw, y(v)); g.stroke();
    g.textAlign = 'right'; g.textBaseline = 'middle';
    g.fillText(v + '%', mL - 8, y(v));
  }}
  g.textAlign = 'center'; g.textBaseline = 'top';
  const steg = Math.max(1, Math.floor(n / 7));
  for (let i = 0; i < n; i += steg) g.fillText(T.datum[i].slice(2, 7), x(i), mT + bh + 9);

  g.lineWidth = 2.4; g.lineJoin = 'round'; g.lineCap = 'round';
  for (const p in T.serier) {{
    g.strokeStyle = T.farger[p]; g.beginPath();
    T.serier[p].forEach((v, i) => i ? g.lineTo(x(i), y(v)) : g.moveTo(x(i), y(v)));
    g.stroke();
  }}

  /* Etiketterna till höger skjuts isär så att partier med snarlikt stöd inte
     skriver över varandra. Vi sorterar på slutvärde och håller ett minsta
     avstånd mellan intilliggande etiketter. */
  const etiketter = Object.keys(T.serier)
    .map(p => ({{ p, v: T.serier[p][n - 1] }}))
    .sort((a, b) => b.v - a.v);
  const minAvstand = 13;
  let forra = -Infinity;
  for (const e of etiketter) {{
    let ey = y(e.v);
    if (ey - forra < minAvstand) ey = forra + minAvstand;
    forra = ey;
    e.y = ey;
  }}
  g.textAlign = 'left'; g.textBaseline = 'middle';
  g.font = "bold 11.5px 'Work Sans',sans-serif";
  for (const e of etiketter) {{
    g.strokeStyle = T.farger[e.p]; g.lineWidth = 1.2;
    /* Liten ledarlinje när etiketten flyttats från sitt egentliga läge. */
    const sant = y(e.v);
    if (Math.abs(e.y - sant) > 1.5) {{
      g.beginPath();
      g.moveTo(mL + bw + 2, sant);
      g.lineTo(mL + bw + 6, e.y);
      g.stroke();
    }}
    g.fillStyle = T.farger[e.p];
    g.fillText(e.p, mL + bw + 9, e.y);
  }}
  g.font = "11px 'Work Sans',sans-serif";

  /* Hovermarkörer: lodrät ledlinje och en ring per parti vid valt datum. */
  if (hoverIndex >= 0 && hoverIndex < n) {{
    const hx = x(hoverIndex);
    g.save();
    g.strokeStyle = textfarg; g.lineWidth = 1; g.globalAlpha = .5;
    g.setLineDash([3, 3]);
    g.beginPath(); g.moveTo(hx, mT); g.lineTo(hx, mT + bh); g.stroke();
    g.restore();

    for (const p in T.serier) {{
      const v = T.serier[p][hoverIndex];
      if (v === undefined || v === null) continue;
      const py = y(v);
      g.beginPath(); g.arc(hx, py, 4.2, 0, Math.PI * 2);
      g.fillStyle = T.farger[p]; g.fill();
      g.strokeStyle = stil.getPropertyValue('--kortbg').trim() || '#fff';
      g.lineWidth = 1.8; g.stroke();
    }}
  }}
}}
ritaTrend();

/* --- Valnivåer: riksdag, region, kommun --- */
const LOKAL = {lokal_json};
(function() {{
  if (!LOKAL) return;

  const vy = document.getElementById('lokalvy');
  const riksvy = document.getElementById('riksdagsvy');
  const kropp = document.getElementById('lokalkropp');
  const styrerad = document.getElementById('styrerad');
  const notis = document.getElementById('lokalnotis');
  const sok = document.getElementById('lokalsok');
  const detalj = document.getElementById('omradesdetalj');
  const oversikt = document.getElementById('lokaloversikt');
  const rensa = document.getElementById('rensaomrade');
  const knappar = document.querySelectorAll('.nivaknapp');
  if (!kropp || !riksvy) return;

  const PART = LOKAL.partier;
  const FARG = LOKAL.farger;
  const KAMMARORDNING = {kammarordning_json};
  /* Samma pilikon som Lysio använder i sina knappar. */
  const PIL = '<svg class="pil" viewBox="0 0 16 16" aria-hidden="true">' +
    '<path d="M1 8h12M9 4l4 4-4 4" fill="none" stroke="currentColor" ' +
    'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  /* Lokala partier saknar etablerad partifärg och får korallen ur profilen. */
  const LOKALFARG = '{KORALL}';
  const ETIKETT = {{ region: 'regioner', kommun: 'kommuner' }};
  const TAK = {{ region: 999, kommun: 40 }};

  let niva = 'riksdag';
  let valtOmrade = null;
  /* Sorteringen. Områdesnamn sorteras stigande, tal fallande, eftersom man
     nästan alltid vill se var ett parti är starkast först. */
  let sortNyckel = 'namn';
  let sortFallande = false;
  let kommunerLaddade = false;
  let laddning = null;

  /* Ortnamn har å, ä och ö. Sökningen normaliserar bort diakritiska tecken så
     att "malmo" hittar Malmö och "angelholm" hittar Ängelholm. */
  function normalisera(text) {{
    return (text || '').toLowerCase().normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '');
  }}

  /* Kommundata ligger komprimerad i sidan och packas upp första gången någon
     växlar till kommunvalet. DecompressionStream finns i alla moderna
     webbläsare; saknas den faller vi tillbaka på en inbyggd inflate. */
  function packaUpp(b64) {{
    const binar = atob(b64);
    const bytes = new Uint8Array(binar.length);
    for (let i = 0; i < binar.length; i++) bytes[i] = binar.charCodeAt(i);

    if (typeof DecompressionStream === 'function') {{
      const strom = new Blob([bytes]).stream()
        .pipeThrough(new DecompressionStream('gzip'));
      return new Response(strom).json();
    }}
    return Promise.reject(new Error('DecompressionStream saknas'));
  }}

  function hamtaKommuner() {{
    if (kommunerLaddade) return Promise.resolve(true);
    if (laddning) return laddning;
    if (!LOKAL.kommun_gz) return Promise.resolve(false);

    laddning = packaUpp(LOKAL.kommun_gz)
      .then(function(data) {{
        LOKAL.kommun = data;
        kommunerLaddade = true;
        return true;
      }})
      .catch(function() {{ laddning = null; return false; }});
    return laddning;
  }}

  function meddela(text) {{
    kropp.innerHTML = '<tr><td colspan="99" class="laddar">' + text + '</td></tr>';
  }}

  /* Kammargeometri beräknas i webbläsaren, eftersom mandattalet varierar
     mellan områden. Samma princip som riksdagskammaren: rader vars längd är
     proportionell mot radiens båglängd, vilket ger jämn täthet. */
  function kammarplatser(totalt, rader) {{
    /* Fler rader ger tätare kammare. Kvadratroten ur mandattalet delat på 1.1
       ger 6 rader för 41 mandat och 9 för 101, vilket ser jämnt ut. */
    rader = rader || Math.max(4, Math.min(11, Math.round(Math.sqrt(totalt) / 1.4)));
    /* Innerradien flyttas utåt för små kammare, så att den innersta raden inte
       blir påtagligt kortare än den yttersta. Med få mandat blir bågen annars
       gles i mitten. */
    const rInner = totalt < 90 ? 1.35 : 1.0;
    const rYttre = 2.05;
    const radier = [];
    for (let i = 0; i < rader; i++) {{
      radier.push(rInner + (rYttre - rInner) * i / (rader - 1));
    }}
    const summa = radier.reduce(function(a, b) {{ return a + b; }}, 0);
    const antal = radier.map(function(r) {{
      return Math.max(1, Math.round(totalt * r / summa));
    }});
    /* Justera så att summan blir exakt. */
    let diff = antal.reduce(function(a, b) {{ return a + b; }}, 0) - totalt;
    while (diff > 0) {{
      const i = antal.indexOf(Math.max.apply(null, antal));
      antal[i] -= 1; diff -= 1;
    }}
    while (diff < 0) {{
      const i = antal.indexOf(Math.min.apply(null, antal));
      antal[i] += 1; diff += 1;
    }}

    const platser = [];
    for (let i = 0; i < radier.length; i++) {{
      const r = radier[i], n = antal[i];
      for (let j = 0; j < n; j++) {{
        const t = n === 1 ? 0.5 : j / (n - 1);
        const vinkel = Math.PI * (1 - t);
        platser.push({{ x: r * Math.cos(vinkel), y: -r * Math.sin(vinkel),
                       vinkel: vinkel, r: r }});
      }}
    }}
    platser.sort(function(a, b) {{
      return (b.vinkel - a.vinkel) || (a.r - b.r);
    }});
    return platser;
  }}

  function ritaKammare(post) {{
    const tot = post.mandat_totalt;
    if (!tot) return '';
    const platser = kammarplatser(tot);
    const radie = Math.max(0.034, Math.min(0.075, 1.35 / Math.sqrt(tot) * 0.52));

    /* Partierna placeras i politisk ordning. Ett namngivet lokalt parti
       placeras sist, eftersom det står utanför blocken. */
    const ordning = KAMMARORDNING.slice();
    const sekvens = [];
    ordning.forEach(function(p) {{
      const n = post.mandat[p] || 0;
      for (let i = 0; i < n; i++) sekvens.push(p);
    }});
    if (post.lokal && post.lokal.mandat) {{
      for (let i = 0; i < post.lokal.mandat; i++) sekvens.push('__lokal');
    }}
    const ovr = post.mandat['ÖVRIGA'] || 0;
    for (let i = 0; i < ovr; i++) sekvens.push('ÖVRIGA');

    const prickar = platser.map(function(plats, i) {{
      const p = sekvens[i];
      const farg = p === '__lokal' ? LOKALFARG : (p ? (FARG[p] || '#9AA6B5') : '#D5DCE6');
      const namn = p === '__lokal' ? (post.lokal ? post.lokal.namn : '') : (p || '');
      return '<circle cx="' + plats.x.toFixed(4) + '" cy="' + plats.y.toFixed(4) +
        '" r="' + radie.toFixed(4) + '" fill="' + farg + '"><title>' + namn +
        '</title></circle>';
    }}).join('');

    /* Majoritetsgränsen ritas där platsen för majoritet ligger. */
    const gi = Math.min(post.majoritet - 1, platser.length - 1);
    const gv = platser[gi].vinkel;
    const gx1 = 0.86 * Math.cos(gv), gy1 = -0.86 * Math.sin(gv);
    const gx2 = 2.16 * Math.cos(gv), gy2 = -2.16 * Math.sin(gv);
    const ex = 2.40 * Math.cos(gv), ey = -2.40 * Math.sin(gv);

    return '<svg viewBox="-2.66 -2.78 5.32 3.06" class="kammare liten" ' +
      'role="img" aria-label="Mandatfördelning i ' + post.namn + '">' +
      prickar +
      '<line x1="' + gx1.toFixed(4) + '" y1="' + gy1.toFixed(4) + '" x2="' +
      gx2.toFixed(4) + '" y2="' + gy2.toFixed(4) + '" class="majoritetslinje"/>' +
      '<g transform="translate(' + ex.toFixed(4) + ' ' + ey.toFixed(4) + ')">' +
      '<rect x="-0.25" y="-0.10" width="0.50" height="0.20" rx="0.10" ' +
      'class="majoritetsplatta"/><text x="0" y="0.004" ' +
      'class="majoritetsetikett" text-anchor="middle">' + post.majoritet +
      '</text></g>' +
      '<text x="0" y="-0.62" class="kammartext">' + tot + '</text>' +
      '<text x="0" y="-0.36" class="kammartext liten">mandat</text>' +
      '</svg>';
  }}

  /* Formaterar en förändring mot förra valet med tecken och färg. */
  function diffMarke(varde, enhet) {{
    if (varde === null || varde === undefined) return '';
    const tecken = varde > 0 ? '+' : (varde < 0 ? '' : '\u00b1');
    const klass = varde > 0 ? 'upp' : (varde < 0 ? 'ned' : 'lika');
    const text = varde === 0 ? '0' : tecken + varde.toFixed(enhet === '%' ? 1 : 0);
    return '<span class="diff ' + klass + '">' + text +
      (enhet === '%' ? '' : '') + '</span>';
  }}

  /* --- Detaljvy för ett enskilt område --- */
  function ritaDetalj(post) {{
    /* Alla partier i området, inklusive ett namngivet lokalt parti. */
    const poster = PART.filter(function(p) {{ return (post.stod[p] || 0) > 0.05; }})
      .map(function(p) {{
        return {{ namn: p, stod: post.stod[p] || 0, mandat: post.mandat[p] || 0,
                 farg: FARG[p] || '#9AA6B5', diff: post.diff ? post.diff[p] : null,
                 mandatdiff: post.mandatdiff ? post.mandatdiff[p] : null }};
      }});
    if (post.lokal && post.lokal.stod) {{
      poster.push({{ namn: post.lokal.namn, stod: post.lokal.stod,
                    mandat: post.lokal.mandat, farg: LOKALFARG,
                    diff: null, mandatdiff: null, lokal: true }});
    }}
    poster.sort(function(a, b) {{ return b.stod - a.stod; }});

    const max = Math.max.apply(null, poster.map(function(r) {{ return r.stod; }}));
    const staplar = poster.map(function(r) {{
      const bredd = max > 0 ? (r.stod / max * 100) : 0;
      const mandattext = r.mandat + (r.mandat === 1 ? ' mandat' : ' mandat');
      return '<div class="dstapelrad">' +
        '<div class="dparti"><span class="prick" style="background:' + r.farg +
        '"></span>' + r.namn + '</div>' +
        '<div class="dstapelyta"><div class="dstapel" style="width:' +
        bredd.toFixed(1) + '%;background:' + r.farg + '"></div></div>' +
        '<div class="dvarde">' + r.stod.toFixed(1) + '%</div>' +
        '<div class="ddiff">' + diffMarke(r.diff, '%') + '</div>' +
        '<div class="dmandat">' + mandattext + ' ' +
        diffMarke(r.mandatdiff, 'm') + '</div>' +
        '</div>';
    }}).join('');

    /* Mandatband i politisk ordning, med majoritetsgränsen utsatt. */
    const tot = post.mandat_totalt;
    const gransProcent = (post.majoritet / tot * 100).toFixed(2);
    const bandordning = KAMMARORDNING.filter(function(p) {{
      return (post.mandat[p] || 0) > 0;
    }});
    /* Namnen på dem som tar mandaten, om kandidatdatan hunnit hämtas.
       Bandet visar dem i tooltipen så att den som hovrar ser vilka platserna
       tillhör, inte bara hur många partiet har. */
    function bandnamn(parti, antal) {{
      const omr = KAND && KAND[niva] && KAND[niva][post.kod];
      if (!omr) return '';
      const pp = (omr.partier || []).filter(function(x) {{ return x.p === parti; }})[0];
      if (!pp || !pp.k) return '';
      return '\\n' + pp.k.slice(0, antal).map(function(t, i) {{
        return (i + 1) + '. ' + kandidatnamn(t).namn;
      }}).join('\\n');
    }}

    let band = bandordning.map(function(p) {{
      const antal = post.mandat[p] || 0;
      const andel = antal / tot * 100;
      const titel = p + ': ' + antal + (antal === 1 ? ' mandat' : ' mandat') +
                    bandnamn(p, antal);
      return '<div class="bandbit" title="' + titel.replace(/"/g, '&quot;') +
        '" style="width:' + andel.toFixed(2) + '%;background:' + FARG[p] + '"></div>';
    }}).join('');
    if (post.lokal && post.lokal.mandat) {{
      const ltitel = (post.lokal.namn + ': ' + post.lokal.mandat + ' mandat' +
                      bandnamn(post.lokal.namn, post.lokal.mandat));
      band += '<div class="bandbit" title="' + ltitel.replace(/"/g, '&quot;') +
        '" style="width:' +
        (post.lokal.mandat / tot * 100).toFixed(2) + '%;background:' +
        LOKALFARG + '"></div>';
    }}
    if (post.mandat['ÖVRIGA']) {{
      band += '<div class="bandbit" title="Övriga ' + post.mandat['ÖVRIGA'] +
        '" style="width:' + (post.mandat['ÖVRIGA'] / tot * 100).toFixed(2) +
        '%;background:#9AA6B5"></div>';
    }}

    /* Notis om det lokala partiet, med källa och hur stödet skattats. */
    let lokalnotis = '';
    if (post.lokal) {{
      const hur = post.lokal.matt
        ? ('Egen mätning: ' + (post.lokal.kalla || 'okänd källa') + '.')
        : ('Ingen mätning finns för denna nivå. Stödet är skalat från partiets ' +
           'mätning på en annan nivå.');
      lokalnotis = '<div class="lokalnotis"><strong>' + post.lokal.namn +
        '</strong> redovisas separat i stället för att ingå i ÖVRIGA. ' + hur +
        ' <a href="#lokala-matningar">Se alla lokala mätningar</a></div>';
    }}

    /* Koalitionerna visar vilka konstellationer som når majoritet. Vänster mot
       höger räcker inte lokalt: blocköverskridande styren är vanligast. */
    let koalhtml = '';
    if (post.koal && post.koal.length && LOKAL.koalitioner) {{
      /* Mandattalen ligger per område, definitionerna i LOKAL.koalitioner. */
      const sorterade = post.koal.map(function(mandat, i) {{
        const def = LOKAL.koalitioner[i] || {{}};
        return {{
          namn: def.namn || '', partier: def.partier || '',
          mandat: mandat, majoritet: mandat >= post.majoritet,
          styr2022: niva === 'kommun' ? def.kommun : def.region,
        }};
      }}).sort(function(a, b) {{
        return (b.majoritet - a.majoritet) || (b.mandat - a.mandat);
      }});

      const rader = sorterade.map(function(k) {{
        const diff = k.mandat - post.majoritet;
        const marke = k.majoritet
          ? '<span class="kmarke ja">Majoritet</span>'
          : '<span class="kmarke nej">' + diff + '</span>';
        const bredd = Math.min(100, k.mandat / post.mandat_totalt * 100);
        return '<div class="koalrad' + (k.majoritet ? ' vinner' : '') + '">' +
          '<div class="knamn">' + k.namn +
          '<span class="kpartier">' + k.partier + '</span></div>' +
          '<div class="kbar"><div class="kfyll" style="width:' + bredd.toFixed(1) +
          '%"></div><div class="kgrans" style="left:' +
          (post.majoritet / post.mandat_totalt * 100).toFixed(2) + '%"></div></div>' +
          '<div class="kmandat">' + k.mandat + '</div>' +
          '<div class="kstatus">' + marke + '</div>' +
          '<div class="kstyr">' + (k.styr2022 || 0) + '</div>' +
          '</div>';
      }}).join('');
      koalhtml =
        '<div class="koalblock">' +
          '<div class="koalrubrik">Möjliga styren</div>' +
          '<div class="koalhuvud"><span>Koalition</span><span></span>' +
          '<span>Mandat</span><span></span><span>Styr nu</span></div>' +
          rader +
          '<p class="koalnot">Talet i sista kolumnen är hur många ' +
          (niva === 'kommun' ? 'kommuner' : 'regioner') + ' koalitionen faktiskt ' +
          'styr under mandatperioden 2022 till 2026. Prognosen visar var den ' +
          'skulle kunna nå majoritet, inte var partierna vill styra ihop.</p>' +
        '</div>';
    }}

    /* Valkretsar visas bara för de kommuner som är indelade i flera. Spärren
       är då tre procent i stället för två, vilket avgör om små partier får
       mandat. Mandaten fördelas ändå på kommunnivå, se notisen. */
    let vkhtml = '';
    if (post.valkretsar && post.valkretsar.length > 1) {{
      const rubriker = PART.filter(function(p) {{ return p !== 'ÖVRIGA'; }});
      const huvud = rubriker.map(function(p) {{
        return '<th class="tal">' + p + '</th>';
      }}).join('');

      const kroppen = post.valkretsar.map(function(vk) {{
        const celler = rubriker.map(function(p) {{
          const v = vk.stod[p];
          if (v === undefined) return '<td class="tal dim">–</td>';
          const d = vk.diff[p];
          let pil = '';
          if (d !== undefined && Math.abs(d) >= 0.5) {{
            pil = '<span class="vkdiff ' + (d > 0 ? 'upp' : 'ned') + '">' +
                  (d > 0 ? '+' : '') + d.toFixed(1) + '</span>';
          }}
          return '<td class="tal">' + v.toFixed(1) + pil + '</td>';
        }}).join('');
        return '<tr><td class="inst">' + vk.namn + '</td>' + celler + '</tr>';
      }}).join('');

      vkhtml =
        '<div class="vkblock">' +
          '<div class="koalrubrik">Valkretsar</div>' +
          '<div class="tabellwrap"><table>' +
            '<thead><tr><th>Valkrets</th>' + huvud + '</tr></thead>' +
            '<tbody>' + kroppen + '</tbody>' +
          '</table></div>' +
          '<p class="koalnot">Kommunen är indelad i ' + post.valkretsar.length +
          ' valkretsar, vilket höjer småpartispärren från två till tre procent. ' +
          'Mandaten fördelas ändå proportionellt över hela kommunen genom ' +
          'utjämningsmandat, så fördelningen ovan görs på kommunnivå.</p>' +
        '</div>';
    }}

    /* Kandidatprognosen ligger i en egen fil och hämtas vid första klicket.
       Blocket ritas tomt först och fylls i när datan kommit. */
    const kandhtml = '<div class="kandblock" id="kandblock"></div>';

    detalj.innerHTML =
      '<div class="detaljkort">' +
        '<div class="detaljhuvud">' +
          '<div><div class="detaljnamn">' + post.namn + '</div>' +
          '<div class="detaljmeta">' + tot + ' mandat · ' + post.majoritet +
          ' för majoritet</div></div>' +
          '<span class="lagemarke ' + post.lage + '">' + post.lagetext +
          '</span>' +
        '</div>' +
        '<div class="kammargrid">' +
          '<div class="kammarhalva">' + ritaKammare(post) + '</div>' +
          '<div class="blockhalva">' +
            '<div class="blockpost"><div class="bpnamn">V+S+MP</div>' +
            '<div class="bpvarde v">' + (post.m_vanster || 0) + '</div></div>' +
            '<div class="blockpost"><div class="bpnamn">C</div>' +
            '<div class="bpvarde c">' + (post.m_c || 0) + '</div></div>' +
            '<div class="blockpost"><div class="bpnamn">M+KD+L</div>' +
            '<div class="bpvarde h">' + (post.m_borg || 0) + '</div></div>' +
            '<div class="blockpost"><div class="bpnamn">SD</div>' +
            '<div class="bpvarde sd">' + (post.m_sd || 0) + '</div></div>' +
            ((post.m_ovr || 0) > 0
              ? '<div class="blockpost"><div class="bpnamn">Lokala partier</div>' +
                '<div class="bpvarde o">' + post.m_ovr + '</div></div>'
              : '') +
          '</div>' +
        '</div>' +
        '<div class="mandatband">' + band +
          '<div class="bandgrans" style="left:' + gransProcent + '%"></div>' +
        '</div>' +
        (post.lagebesk ? '<p class="lagetext">' + post.lagebesk + '</p>' : '') +
        '<div class="dstaplar">' +
          '<div class="dstapelhuvud"><span>Parti</span><span></span>' +
          '<span>Stöd</span><span>Mot 2022</span><span>Mandat</span></div>' +
          staplar +
        '</div>' +
        koalhtml +
        vkhtml +
        kandhtml +
        lokalnotis +
      '</div>';
    detalj.hidden = false;
    oversikt.hidden = true;
    rensa.hidden = false;

    ritaKandidater(post);
  }}

  /* Plockar ut värdet som ska sorteras på. Nyckeln "stod:KD" betyder partiets
     stöd, övriga nycklar är fält direkt på posten. */
  function sortVarde(post, nyckel) {{
    if (nyckel.indexOf('stod:') === 0) {{
      const parti = nyckel.slice(5);
      const v = post.stod ? post.stod[parti] : null;
      return (typeof v === 'number') ? v : -1;
    }}
    const v = post[nyckel];
    if (typeof v === 'number') return v;
    return v === undefined || v === null ? '' : String(v);
  }}

  function sortera(poster) {{
    const nyckel = sortNyckel;
    return poster.sort(function(a, b) {{
      const va = sortVarde(a, nyckel), vb = sortVarde(b, nyckel);
      let jmf;
      if (typeof va === 'number' && typeof vb === 'number') {{
        jmf = va - vb;
      }} else {{
        jmf = String(va).localeCompare(String(vb), 'sv');
      }}
      /* Lika värden sorteras på namn, så ordningen blir stabil och läsbar. */
      if (jmf === 0) return a.namn.localeCompare(b.namn, 'sv');
      return sortFallande ? -jmf : jmf;
    }});
  }}

  function uppdateraSortMarken() {{
    document.querySelectorAll('.sortknapp').forEach(function(k) {{
      const aktiv = k.dataset.sort === sortNyckel;
      k.classList.toggle('sorterad', aktiv);
      k.classList.toggle('fallande', aktiv && sortFallande);
      k.setAttribute('aria-sort', aktiv
        ? (sortFallande ? 'descending' : 'ascending') : 'none');
    }});
  }}


  /* --- Kandidatprognos ------------------------------------------------
     Vilka personer som väntas ta mandaten. Datan ligger i en egen fil
     eftersom den är stor och bara behövs när ett område öppnats. */
  let KAND = null;
  let kandLaddning = null;

  /* Kandidatdatan ligger i en egen fil eftersom den är 434 kB och bara behövs
     när ett område öppnas. Sidan väger därmed 266 kB i stället för 435. */
  let kandFel = null;

  function hamtaKandidater() {{
    if (KAND) return Promise.resolve(KAND);
    if (kandLaddning) return kandLaddning;

    kandLaddning = fetch('{KANDIDATFIL}')
      .then(function(svar) {{
        if (!svar.ok) throw new Error('HTTP ' + svar.status);
        return svar.json();
      }})
      .then(function(data) {{ KAND = data; return data; }})
      .catch(function() {{
        kandLaddning = null;
        /* Webbläsaren blockerar filhämtning från file://. Skilj det från
           att filen faktiskt saknas på servern. */
        kandFel = (location.protocol === 'file:') ? 'lokal' : 'saknas';
        return null;
      }});
    return kandLaddning;
  }}

  function kandidatnamn(text) {{
    /* Lagrade som "Namn|valsedelsuppgift|listplats". Uppgiften är den text
       partiet tryckt på valsedeln: ålder, ort och titel. */
    const delar = String(text).split('|');
    return {{ namn: delar[0], uppgift: delar[1] || '', plats: delar[2] || '' }};
  }}

  function ritaKandidater(post) {{
    const block = document.getElementById('kandblock');
    if (!block) return;

    block.innerHTML = '<div class="koalrubrik">Vilka som tar mandaten</div>' +
      '<p class="kandladdar">Hämtar kandidater ...</p>';

    hamtaKandidater().then(function(data) {{
      if (!block.isConnected) return;
      const omr = data && data[niva] && data[niva][post.kod];

      if (!omr) {{
        let text;
        if (kandFel === 'lokal') {{
          text = 'Kandidatprognosen ligger i filen kandidater.json bredvid ' +
                 'sidan. Webbläsaren blockerar den när sidan öppnas direkt ' +
                 'från Finder. Kör <code>python3 -m http.server</code> i ' +
                 'mappen och öppna <code>localhost:8000</code>, eller titta ' +
                 'på den publicerade sidan.';
        }} else if (kandFel === 'saknas') {{
          text = 'Filen kandidater.json kunde inte läsas. Kontrollera att den ' +
                 'ligger i samma mapp som sidan.';
        }} else {{
          text = 'Ingen kandidatprognos finns för det här området. Partiernas ' +
                 'listor för 2026 gick inte att matcha mot området i ' +
                 'Valmyndighetens underlag.';
        }}
        block.innerHTML = '<div class="koalrubrik">Vilka som tar mandaten</div>' +
          '<p class="kandfel">' + text + '</p>';
        return;
      }}

      const partier = (omr.partier || []).filter(function(p) {{ return p.m > 0; }});
      const rader = partier.map(function(p) {{
        const farg = FARGER[p.p] || 'var(--svag)';
        /* Namnen läggs som brickor som radbryter, så att ett parti med
           trettio mandat inte blir en trettio rader lång lista. */
        const brickor = p.k.slice(0, p.m).map(function(text, i) {{
          const k = kandidatnamn(text);
          /* Listplatsen är kandidatens ordning på valsedeln. Den kan ligga
             högre än mandatets nummer när någon längre upp inte tar sin
             plats, så båda visas. */
          const valsedel = p.ln
            ? '\\nValsedel ' + p.ln + (p.lb ? ' · ' + p.lb : '')
            : '';
          const titel = k.namn + (k.uppgift ? '\\n' + k.uppgift : '') +
                        valsedel +
                        (k.plats ? '\\nPlats ' + k.plats + ' på valsedeln' : '') +
                        '\\nTar mandat ' + (i + 1) + ' av ' + p.m + ' för ' + p.p;
          return '<span class="kandbricka" title="' +
                 titel.replace(/"/g, '&quot;') + '">' +
                 '<span class="kandnr">' + (i + 1) + '</span>' + k.namn +
                 '</span>';
        }}).join('');

        /* Bara den som står på flera listor behöver märkas ut. */
        const flagga = p.niva === 'osakert'
          ? '<span class="kandvarn" title="' +
            (p.v || '').replace(/"/g, '&quot;') + '">flera listor</span>'
          : '';

        return '<div class="kandparti">' +
          '<div class="kandhuvud">' +
            '<span class="prick" style="background:' + farg + '"></span>' +
            '<strong>' + p.p + '</strong>' +
            '<span class="kandmandat">' + p.m +
            (p.m === 1 ? ' mandat' : ' mandat') + '</span>' + flagga +
          '</div>' +
          '<div class="kandnamn">' + brickor + '</div>' +
        '</div>';
      }}).join('');

      const saknas = (omr.saknas || []).map(function(x) {{
        return '<li><strong>' + x.p + '</strong> (' + x.m + ' mandat): ' +
               x.skal + '</li>';
      }}).join('');
      const saknasblock = saknas
        ? '<div class="kandsaknas"><strong>Utan kandidatprognos</strong>' +
          '<ul>' + saknas + '</ul></div>'
        : '';

      const osakra = partier.filter(function(p) {{ return p.niva === 'osakert'; }}).length;
      const osakertext = osakra
        ? ' För ' + osakra + (osakra === 1 ? ' parti' : ' partier') +
          ' finns flera listor i området, och den med flest tryckta valsedlar ' +
          'används. Håll muspekaren över märkningen för detaljer.'
        : '';

      block.innerHTML =
        '<div class="koalrubrik">Vilka som tar mandaten</div>' +
        rader + saknasblock +
        '<p class="koalnot">Kandidaterna hämtas i listordning från ' +
        'Valmyndighetens registrerade listor. Personröster kan flytta namn ' +
        'förbi varandra och ingår inte i prognosen.' + osakertext +
        '</p>';
    }});
  }}

  function ritaOversikt() {{
    detalj.hidden = true;
    oversikt.hidden = false;
    rensa.hidden = true;

    const alla = LOKAL[niva] || [];
    if (!alla.length) return;

    const fraga = normalisera(sok.value.trim());
    let poster = fraga
      ? alla.filter(function(p) {{ return normalisera(p.namn).includes(fraga); }})
      : alla.slice();

    poster = sortera(poster);

    const totalt = poster.length;
    const kapat = !fraga && totalt > TAK[niva];
    if (kapat) poster = poster.slice(0, TAK[niva]);

    kropp.innerHTML = poster.map(function(p) {{
      const stod = PART.map(function(x) {{
        const v = p.stod[x];
        return '<td class="tal">' + (v === undefined ? '–' : v.toFixed(1)) + '</td>';
      }}).join('');
      /* Områden med en egen lokal mätning märks ut, så att det syns i listan
         och inte bara när man öppnat detaljvyn. */
      const lokalmarke = p.lokal
        ? '<span class="lokalprick" title="' + p.lokal.namn +
          ' redovisas separat, se Lokala mätningar">' + p.lokal.namn + '</span>'
        : '';
      return '<tr class="klickbar" data-kod="' + p.kod + '">' +
        '<td class="inst"><span class="omradesnamn">' + p.namn + '</span>' +
        lokalmarke +
        '<span class="radpil" aria-hidden="true">' + PIL + '</span></td>' + stod +
        '<td class="tal dim">' + p.mandat_totalt + '</td>' +
        '<td class="tal blockcell v">' + (p.m_vanster || 0) + '</td>' +
        '<td class="tal blockcell c">' + (p.m_c || 0) + '</td>' +
        '<td class="tal blockcell h">' + (p.m_borg || 0) + '</td>' +
        '<td class="tal blockcell sd">' + (p.m_sd || 0) + '</td>' +
        '<td class="tal dim">' + (p.m_ovr || 0) + '</td>' +
        '<td><span class="lagemarke ' + p.lage + '" title="' +
        (p.lagebesk || '') + '">' + p.lagetext + '</span></td></tr>';
    }}).join('');

    /* Uppmaningen ligger som eget element ovanför tabellen i stället för
       nedsänkt i notisen, eftersom hover-effekten inte syns på touchskärmar. */
    const tips = document.getElementById('klicktips');
    if (tips) {{
      const vad = niva === 'kommun' ? 'en kommun' : 'en region';
      tips.innerHTML = PIL + '<span>Klicka på ' + vad + ' för mandatfördelning, ' +
        'jämförelse med förra valet och möjliga styren. Klicka på en ' +
        'kolumnrubrik för att sortera, till exempel för att se var ett parti är ' +
        'starkast.</span>';
    }}

    const sam = LOKAL.sammanfattning[niva] || {{}};
    styrerad.innerHTML =
      '<div class="styrekort"><div class="n">' + (sam.egen_majoritet || 0) + '</div>' +
      '<div class="e">där V+S+MP når majoritet själva</div></div>' +
      '<div class="styrekort"><div class="n">' + (sam.kravs_c || 0) + '</div>' +
      '<div class="e">där C avgör vem som kan styra</div></div>' +
      '<div class="styrekort"><div class="n">' + (sam.hoger || 0) + '</div>' +
      '<div class="e">där borgerliga når majoritet</div></div>' +
      '<div class="styrekort"><div class="n">' +
      ((sam.lokala || 0) + (sam.oklart || 0)) + '</div>' +
      '<div class="e">utan tydlig majoritet</div></div>';

    let text = 'Mandatläget säger vem som kan nå majoritet, inte vem som ' +
      'kommer att styra. Det avgörs av förhandlingar. C räknas inte till något ' +
      'block: efter valet 2022 ingick partiet i 135 kommunstyren, varav 55 med ' +
      'de borgerliga, 48 med båda sidorna och 32 med vänstern. Prognosen bygger ' +
      'på områdets eget resultat i förra ' + niva + 'valet, skalat med ' +
      'rikstrenden. Lokala partier redovisas samlat som ÖVRIGA och hålls på ' +
      'förra valets nivå.';
    if (kapat) {{
      text = 'Visar de ' + TAK[niva] + ' första av ' + totalt + ' ' +
        ETIKETT[niva] + ' i bokstavsordning. Sök för att hitta ett område. ' + text;
    }} else if (fraga) {{
      text = totalt + (totalt === 1 ? ' träff' : ' träffar') + ' på "' +
        sok.value + '". ' + text;
    }}
    notis.textContent = text;
    uppdateraSortMarken();
  }}

  function rita() {{
    if (valtOmrade) {{
      const alla = LOKAL[niva] || [];
      const post = alla.filter(function(p) {{ return p.kod === valtOmrade; }})[0];
      if (post) {{ ritaDetalj(post); return; }}
      valtOmrade = null;
    }}
    ritaOversikt();
  }}

  function visaNiva(ny) {{
    niva = ny;
    valtOmrade = null;
    knappar.forEach(function(k) {{
      k.classList.toggle('aktiv', k.dataset.niva === ny);
    }});

    if (ny === 'riksdag') {{
      riksvy.hidden = false;
      vy.hidden = true;
      return;
    }}
    riksvy.hidden = true;
    vy.hidden = false;
    sok.value = '';

    if (ny === 'kommun' && !kommunerLaddade) {{
      detalj.hidden = true;
      oversikt.hidden = false;
      meddela('Läser in ' + LOKAL.kommun_antal + ' kommuner ...');
      hamtaKommuner().then(function(lyckades) {{
        if (lyckades) {{
          rita();
        }} else {{
          meddela('Kommundata kunde inte packas upp. Prova en nyare webbläsare.');
        }}
      }});
      return;
    }}
    rita();
  }}

  knappar.forEach(function(k) {{
    k.addEventListener('click', function() {{ visaNiva(k.dataset.niva); }});
  }});

  /* Rubrikerna sorterar. Ett andra klick på samma kolumn vänder ordningen. */
  document.querySelectorAll('.sortknapp').forEach(function(knapp) {{
    knapp.addEventListener('click', function() {{
      const nyckel = knapp.dataset.sort;
      if (nyckel === sortNyckel) {{
        sortFallande = !sortFallande;
      }} else {{
        sortNyckel = nyckel;
        /* Tal börjar fallande, text stigande. */
        sortFallande = nyckel !== 'namn' && nyckel !== 'lagetext';
      }}
      valtOmrade = null;
      ritaOversikt();
    }});
  }});

  kropp.addEventListener('click', function(e) {{
    const rad = e.target.closest('tr.klickbar');
    if (!rad) return;
    valtOmrade = rad.dataset.kod;
    rita();
  }});

  rensa.addEventListener('click', function() {{
    valtOmrade = null;
    ritaOversikt();
  }});

  sok.addEventListener('input', function() {{
    valtOmrade = null;
    ritaOversikt();
  }});
}})();

/* --- Hover på trendgrafen --- */
(function() {{
  const c = document.getElementById('trend');
  const tip = document.getElementById('tooltip');
  if (!c || !tip) return;

  /* Blocken definieras här så tooltipen kan visa blocksummor per datum. */
  const BLOCK_V = {block_v_json};
  const BLOCK_H = {block_h_json};

  function indexFor(klientX) {{
    if (!G) return -1;
    const rect = c.getBoundingClientRect();
    /* Canvas är skalad med CSS, så vi räknar om till ritytans koordinater. */
    const skala = G.W / rect.width;
    const px = (klientX - rect.left) * skala;
    /* Hela canvasen är aktiv, inte bara ritområdet: marginalen till höger
       rymmer partietiketterna och ska ändå svara på hover. */
    if (px < G.mL - 14 || px > G.W - 2) return -1;
    if (G.n < 2) return 0;
    const andel = Math.max(0, Math.min(1, (px - G.mL) / G.bw));
    return Math.round(andel * (G.n - 1));
  }}

  function summa(partier, i) {{
    let s = 0;
    for (const p of partier) {{
      const v = T.serier[p] && T.serier[p][i];
      if (typeof v === 'number') s += v;
    }}
    return s;
  }}

  function visaTooltip(i, klientX) {{
    /* Partierna sorteras efter stöd vid just detta datum, störst först. */
    const rader = Object.keys(T.serier)
      .map(p => ({{ p, v: T.serier[p][i] }}))
      .filter(r => typeof r.v === 'number')
      .sort((a, b) => b.v - a.v)
      .map(r =>
        '<div class="tooltiprad">' +
        '<span class="tp" style="background:' + T.farger[r.p] + '"></span>' +
        '<span class="tn">' + r.p + '</span>' +
        '<span class="tv">' + r.v.toFixed(1) + '%</span></div>'
      ).join('');

    tip.innerHTML =
      '<div class="tooltipdatum">' + T.datum[i] + '</div>' + rader +
      '<div class="tooltipblock">' +
      '<div>V+S+MP+C<span>' + summa(BLOCK_V, i).toFixed(1) + '%</span></div>' +
      '<div>L+M+KD+SD<span>' + summa(BLOCK_H, i).toFixed(1) + '%</span></div>' +
      '</div>';
    tip.hidden = false;

    /* Placera tooltipen vid markören, men håll den inom grafytan. */
    const rect = c.getBoundingClientRect();
    const px = G.x(i) / (G.W / rect.width);
    const bredd = tip.offsetWidth;
    let vanster = px + 16;
    if (vanster + bredd > rect.width - 4) vanster = px - bredd - 16;
    if (vanster < 4) vanster = 4;
    tip.style.left = vanster + 'px';
    tip.style.top = '10px';
  }}

  function pekaPa(klientX) {{
    const i = indexFor(klientX);
    if (i < 0) {{ dolj(); return; }}
    if (i !== hoverIndex) {{ hoverIndex = i; ritaTrend(); }}
    visaTooltip(i, klientX);
  }}

  function dolj() {{
    if (hoverIndex !== -1) {{ hoverIndex = -1; ritaTrend(); }}
    tip.hidden = true;
  }}

  c.addEventListener('mousemove', e => pekaPa(e.clientX));
  c.addEventListener('mouseleave', dolj);
  /* Touch: samma logik, men förhindra att sidan skrollar under dragningen. */
  c.addEventListener('touchstart', e => {{
    if (e.touches[0]) pekaPa(e.touches[0].clientX);
  }}, {{ passive: true }});
  c.addEventListener('touchmove', e => {{
    if (e.touches[0]) {{ e.preventDefault(); pekaPa(e.touches[0].clientX); }}
  }});
  c.addEventListener('touchend', dolj);
}})();
let omritning;
window.addEventListener('resize', () => {{
  clearTimeout(omritning); omritning = setTimeout(ritaTrend, 140);
}});

/* --- Institutsdetaljer --- */
(function() {{
  const detalj = document.getElementById('detalj');
  const rubrik = document.getElementById('detaljrubrik');
  const kropp = document.getElementById('detaljkropp');
  let oppen = null;

  function visa(namn) {{
    const rader = ALLA[namn] || [];
    rubrik.innerHTML = namn + '<span>' + rader.length + ' mätningar</span>';
    kropp.innerHTML = rader.map(r => {{
      const celler = PARTIER.map(p =>
        '<td class="tal">' + (r[p] === null ? '–' : r[p].toFixed(1)) + '</td>').join('');
      const vikt = r.inom
        ? '<span class="viktbricka">' + r.vikt.toFixed(1) + '%</span>'
        : '<span class="viktbricka noll">–</span>';
      return '<tr class="' + (r.inom ? '' : 'utanfor') + '">' +
        '<td class="datum">' + r.datum + '</td>' +
        '<td class="dim">' + r.alder + ' dgr</td>' + celler +
        '<td class="tal blockcell v">' + r.bv.toFixed(1) + '</td>' +
        '<td class="tal blockcell h">' + r.bh.toFixed(1) + '</td>' +
        '<td class="tal">' + vikt + '</td></tr>';
    }}).join('');
    detalj.classList.add('visas');
    detalj.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
  }}

  document.querySelectorAll('.instkort').forEach(kort => {{
    kort.addEventListener('click', () => {{
      const namn = kort.dataset.institut;
      document.querySelectorAll('.instkort').forEach(k => k.classList.remove('aktiv'));
      if (oppen === namn) {{ detalj.classList.remove('visas'); oppen = null; return; }}
      kort.classList.add('aktiv'); oppen = namn; visa(namn);
    }});
  }});
  document.getElementById('stang').addEventListener('click', () => {{
    detalj.classList.remove('visas'); oppen = null;
    document.querySelectorAll('.instkort').forEach(k => k.classList.remove('aktiv'));
  }});
}})();
</script>
</body></html>""", kommun_json


def spara(html: str, kommun_json: str | None = None,
          kandidat_json: str | None = None) -> Path:
    """Skriver sidan till output/.

    Filen heter index.html eftersom statisk hosting som GitHub Pages hämtar den
    automatiskt på rotadressen. En kopia sparas som prognos.html för den som är
    van vid det namnet lokalt.
    """
    katalog = ROT / "output"
    katalog.mkdir(parents=True, exist_ok=True)
    ut = katalog / "index.html"
    ut.write_text(html, encoding="utf-8")
    (katalog / "prognos.html").write_text(html, encoding="utf-8")
    # Kommundata bäddas in komprimerad i sidan, så någon separat fil behövs
    # inte. Den skrivs ändå ut för den som vill använda datan för egen analys.
    if kommun_json and kommun_json != "[]":
        (katalog / KOMMUNFIL).write_text(kommun_json, encoding="utf-8")
    if kandidat_json:
        (katalog / KANDIDATFIL).write_text(kandidat_json, encoding="utf-8")
    return ut
