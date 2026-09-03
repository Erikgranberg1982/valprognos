"""Konfiguration: partier, block, regeringsalternativ och institutsparametrar.

Norsk uppsättning. Stortingsvalet hålls andra måndagen i september vart fjärde
år, nästa gång 2029. Valsystemet skiljer sig från det svenska på tre punkter
som påverkar modellen:

  1. 169 mandat, varav 150 distriktsmandat i 19 valdistrikt och 19
     utjämningsmandat, ett per distrikt.
  2. Sainte-Laguë med första divisor 1,4, inte 1,2.
  3. Fyraprocentsspärren gäller bara utjämningsmandaten. Ett parti under
     spärren kan ändå vinna distriktsmandat, vilket Venstre gjorde 2025 med
     3,69 procent och tre mandat.

Punkt 3 innebär att fordela_mandat i modell.py måste skrivas om: den svenska
versionen nollar partier under spärren helt.
"""

VALDAG = "2029-09-10"

PARTIER = ["R", "SV", "Ap", "Sp", "MDG", "KrF", "V", "H", "FrP"]

PARTINAMN = {
    "R": "Rødt",
    "SV": "Sosialistisk Venstreparti",
    "Ap": "Arbeiderpartiet",
    "Sp": "Senterpartiet",
    "MDG": "Miljøpartiet De Grønne",
    "KrF": "Kristelig Folkeparti",
    "V": "Venstre",
    "H": "Høyre",
    "FrP": "Fremskrittspartiet",
}

PARTIFARG = {
    "R": "#8B0000", "SV": "#EB2E2D", "Ap": "#E8112D", "Sp": "#00843D",
    "MDG": "#5A9E3F", "KrF": "#FFBE00", "V": "#00807B", "H": "#0065F1",
    "FrP": "#004F80",
}

# Blockindelning. Norsk politik talar om rød-grønn respektive borgerlig sida.
# Senterpartiet har regerat med Ap men samarbetat borgerligt tidigare, och
# placeringen bör ses över.
BLOCK = {
    "vanster": ["R", "SV", "Ap", "Sp", "MDG"],
    "hoger": ["KrF", "V", "H", "FrP"],
}
BLOCKNAMN = {"vanster": "Rødgrønn side", "hoger": "Borgerlig side"}

# Fyra procent, men i Norge gäller spärren BARA utjämningsmandaten. Ett parti
# under spärren kan vinna distriktsmandat på egen styrka i ett distrikt, vilket
# Venstre gjorde 2025 med 3,69 procent och tre mandat.
SPARRGRANS = 0.04
MANDAT_TOTALT = 169

# 150 distriktsmandat i 19 valdistrikt plus 19 utjämningsmandat, ett per
# distrikt. Fördelningen av distriktsmandat mellan distrikt räknas om varje val
# efter befolkning och yta.
FASTA_MANDAT = 150
UTJAMNINGSMANDAT = MANDAT_TOTALT - FASTA_MANDAT

# Sainte-Laguë med första divisor 1,4. Sverige använder 1,2.
FORSTA_DIVISOR = 1.4

# Egen majoritet i Stortinget. 85 av 169.
MAJORITET = MANDAT_TOTALT // 2 + 1

# Norge har ingen motsvarighet till den svenska valkretsspärren på tolv
# procent. Ett parti kommer in via distriktsmandat utan någon tröskel alls,
# bara genom att vara tillräckligt stort i ett distrikt.
VALKRETS_SPARR = None

# Stortingsvalet 8 september 2025, faktiskt utfall. Jämförelsepunkt så att
# förändringen sedan förra valet går att läsa direkt.
VALRESULTAT_2025 = {
    "R": 5.32, "SV": 5.63, "Ap": 28.02, "Sp": 5.59, "MDG": 4.74,
    "KrF": 4.20, "V": 3.69, "H": 14.65, "FrP": 23.85,
}

# Mandat per parti i stortingsvalet 2025. Venstre fick tre mandat med 3,69
# procent, alltså under spärren: distriktsmandat kräver ingen tröskel.
MANDAT_2025 = {
    "R": 9, "SV": 9, "Ap": 53, "Sp": 9, "MDG": 8,
    "KrF": 7, "V": 3, "H": 24, "FrP": 47,
}

# Namnen behålls som alias så att kod som ännu inte anpassats inte kraschar
# tyst på en saknad nyckel.
VALRESULTAT_FORRA = VALRESULTAT_2025
MANDAT_FORRA = MANDAT_2025

# --- Institutsparametrar -----------------------------------------------------
# Vikter och modellparametrar läses från CSV i data/ så att de kan justeras
# utan kodändring. Se data/institut_vikter.csv och data/modellparametrar.csv.
import csv as _csv
from pathlib import Path as _Path

_DATA = _Path(__file__).resolve().parent.parent / "data"

STANDARD_URVAL = 1200
STANDARD_VIKT = 0.80


def _las_institut():
    fil = _DATA / "institut_vikter.csv"
    ut = {}
    if not fil.exists():
        return ut
    with open(fil, encoding="utf-8") as f:
        for rad in _csv.DictReader(f):
            namn = (rad.get("institut") or "").strip()
            if not namn:
                continue
            try:
                vikt = float(rad["vikt"])
            except (KeyError, TypeError, ValueError):
                vikt = STANDARD_VIKT
            try:
                urval = int(float(rad["typiskt_urval"]))
            except (KeyError, TypeError, ValueError):
                urval = STANDARD_URVAL
            ut[namn] = {
                "vikt": vikt,
                "typiskt_urval": urval,
                "metod": (rad.get("metod") or "").strip(),
            }
    return ut


def _las_parametrar():
    fil = _DATA / "modellparametrar.csv"
    ut = {}
    if not fil.exists():
        return ut
    with open(fil, encoding="utf-8") as f:
        for rad in _csv.DictReader(f):
            namn = (rad.get("parameter") or "").strip()
            if not namn:
                continue
            try:
                ut[namn] = float(rad["varde"])
            except (KeyError, TypeError, ValueError):
                pass
    return ut


INSTITUT = _las_institut()
_P = _las_parametrar()

# Tidsvikt: nyare mätningar väger tyngre via exponentiell avklingning.
HALVERINGSTID_DAGAR = _P.get("halveringstid_dagar", 30.0)
MAX_ALDER_DAGAR = _P.get("max_alder_dagar", 365.0)
HUSFAKTOR_FONSTER_DAGAR = _P.get("husfaktor_fonster_dagar", 540.0)
HUSFAKTOR_DAMPNING = _P.get("husfaktor_dampning", 0.75)
MIN_MATNINGAR_HUSFAKTOR = int(_P.get("min_matningar_husfaktor", 4))
NATIONELLT_FEL_SD = _P.get("nationellt_fel_sd", 0.022)
PARTIFEL_SD = _P.get("partifel_sd", 0.011)
TREND_DRIFT_SD_PER_MANAD = _P.get("trend_drift_sd_per_manad", 0.010)
# Mättnadspunkt för driften, i månader. Se modell.simulera.
DRIFT_MATTNAD_MANADER = _P.get("drift_mattnad_manader", 18.0)
ANTAL_SIMULERINGAR = int(_P.get("antal_simuleringar", 40000))

ANVAND_VALDAGSKORRIGERING = bool(_P.get("anvand_valdagskorrigering", 0))

# Lokala mätningar tappar vikt långsammare än riksmätningar. En lokal mätning
# mäter det område den gäller, medan alternativet är en extrapolering från
# rikstrenden. Se lokala_partier.vikt_for_matning.
LOKAL_MATNING_HALVERINGSTID = _P.get("lokal_matning_halveringstid", 120.0)
LOKAL_MATNING_MAXVIKT = _P.get("lokal_matning_maxvikt", 0.9)


def _las_valdagskorrigering():
    """Historiskt observerad skevhet per parti, i procentenheter.

    Positivt värde betyder att partiet underskattats i mätningarna och därför
    ska justeras upp. Baseras på backtest mot valet 2022 och är avstängd som
    standard, se ANVAND_VALDAGSKORRIGERING.
    """
    fil = _DATA / "valdagskorrigering.csv"
    ut = {}
    if not fil.exists():
        return ut
    with open(fil, encoding="utf-8") as f:
        for rad in _csv.DictReader(f):
            parti = (rad.get("parti") or "").strip()
            if parti not in PARTIER:
                continue
            try:
                ut[parti] = float(rad["korrigering"])
            except (KeyError, TypeError, ValueError):
                pass
    return ut


VALDAGSKORRIGERING = _las_valdagskorrigering()

# Google Analytics. Tom sträng stänger av mätningen på samtliga sidor.
GA_MATNING_ID = "G-8C4Y5LMHXS"


def google_analytics() -> str:
    """Mätkoden, eller tom sträng om ingen mätning är konfigurerad.

    Läggs på alla sidor så att statistiken täcker hela webbplatsen och inte
    bara startsidan. Dubbla klamrar eftersom mallarna är f-strängar.
    """
    if not GA_MATNING_ID:
        return ""
    return f"""
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id={GA_MATNING_ID}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{{{dataLayer.push(arguments);}}}}
  gtag('js', new Date());
  gtag('config', '{GA_MATNING_ID}');
</script>
"""


# Aggregat som inte är råmätningar och därför måste exkluderas.
EXKLUDERA = ["Poll of polls", "Mätningarnas mätning", "Svensk väljaropinion",
             "Valprognos 2026", "Sammanvägningar", "Valet"]

# --- Regeringsalternativ -----------------------------------------------------
# Varje alternativ: partier som ingår i underlaget (regering eller stöd).
# 'krav' anger extra villkor utöver 50 % av mandaten.
REGERINGSALTERNATIV = [
    {
        "id": "ap_ensam",
        "namn": "Ap-regjering med støtte til venstre",
        "partier": ["Ap", "SV", "Sp", "R", "MDG"],
        "beskrivning": "Dagens ordning: Ap regjerer og søker støtte hos SV, "
                       "Sp, R og MDG fra sak til sak.",
    },
    {
        "id": "ap_sv_sp",
        "namn": "Ap+SV+Sp",
        "partier": ["Ap", "SV", "Sp"],
        "beskrivning": "Det rødgrønne grunnlaget fra 2021, uten R og MDG.",
    },
    {
        "id": "ap_sv",
        "namn": "Ap+SV",
        "partier": ["Ap", "SV"],
        "beskrivning": "Smal venstreregjering uten Senterpartiet.",
    },
    {
        "id": "frp_h",
        "namn": "FrP+H",
        "partier": ["FrP", "H"],
        "beskrivning": "Borgerlig topartiregjering. FrP er etter 2025 det "
                       "største partiet på borgerlig side.",
    },
    {
        "id": "frp_h_krf",
        "namn": "FrP+H+KrF",
        "partier": ["FrP", "H", "KrF"],
        "beskrivning": "Borgerlig regjering uten Venstre.",
        "krav": {"minst": {"KrF": 0.04}},
    },
    {
        "id": "borgerlig_fyra",
        "namn": "Borgerlig firepartiregjering",
        "partier": ["FrP", "H", "KrF", "V"],
        "beskrivning": "Hele den borgerlige siden, tilsvarende "
                       "Solberg-koalisjonen 2018 til 2020.",
    },
    {
        "id": "h_krf_v",
        "namn": "H+KrF+V uten FrP",
        "partier": ["H", "KrF", "V"],
        "beskrivning": "Borgerlig sentrumsregjering som utelukker FrP. "
                       "Krever et svært sterkt Høyre.",
    },
    {
        "id": "ap_h",
        "namn": "Ap+H over blokkgrensen",
        "partier": ["Ap", "H"],
        "beskrivning": "Storkoalisjon mellom de to tradisjonelle "
                       "styringspartiene. Har aldri vært prøvd i Norge.",
    },
    {
        "id": "ap_sp_krf_v",
        "namn": "Ap+Sp+KrF+V",
        "partier": ["Ap", "Sp", "KrF", "V"],
        "beskrivning": "Sentrumsregjering over blokkgrensen, uten SV og FrP.",
    },
]

def formatera_sannolikhet(p: float) -> str:
    """Formaterar en sannolikhet så att små men reella värden inte blir "0%".

    En sannolikhet på 0,46 procent är inte noll, och avrundning till heltal
    skulle felaktigt framställa utfallet som uteslutet.
    """
    procent = p * 100
    if p <= 0:
        return "0%"
    if p >= 1:
        return "100%"
    if procent < 1:
        return f"<1% ({procent:.2f}%)"
    if procent < 10:
        return f"{procent:.1f}%"
    return f"{procent:.0f}%"
