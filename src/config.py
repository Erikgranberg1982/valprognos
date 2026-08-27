"""Konfiguration: partier, block, regeringsalternativ och institutsparametrar."""

VALDAG = "2026-09-13"

PARTIER = ["V", "S", "MP", "C", "L", "M", "KD", "SD"]

PARTINAMN = {
    "V": "Vänsterpartiet",
    "S": "Socialdemokraterna",
    "MP": "Miljöpartiet",
    "C": "Centerpartiet",
    "L": "Liberalerna",
    "M": "Moderaterna",
    "KD": "Kristdemokraterna",
    "SD": "Sverigedemokraterna",
}

PARTIFARG = {
    "V": "#AF0000", "S": "#EE2020", "MP": "#83CF39", "C": "#009933",
    "L": "#006AB3", "M": "#52BDEC", "KD": "#2B4C9B", "SD": "#DDDD00",
}

# Blockindelning enligt Wikipedias kolumnrubriker.
BLOCK = {
    "vanster": ["V", "S", "MP", "C"],
    "hoger": ["L", "M", "KD", "SD"],
}
BLOCKNAMN = {"vanster": "V+S+MP+C", "hoger": "L+M+KD+SD"}

SPARRGRANS = 0.04   # 4 % riksspärr
MANDAT_TOTALT = 349
FASTA_MANDAT = 310  # resten är utjämningsmandat

# Riksdagsvalet har två vägar till mandat: fyra procent i hela landet, eller
# tolv procent i en enskild valkrets. Den andra vägen används i praktiken bara
# av starka lokala partier och har inte gett mandat sedan 1900-talet, men den
# finns i vallagen och kan bli relevant 2026.
VALKRETS_SPARR = 0.12

# Riksdagsvalet 2022, faktiskt utfall. Används som jämförelsepunkt i prognosen
# så att förändringen sedan förra valet går att läsa direkt.
VALRESULTAT_2022 = {
    "V": 6.75, "S": 30.33, "MP": 5.08, "C": 6.71,
    "L": 4.61, "M": 19.10, "KD": 5.34, "SD": 20.54,
}

# Mandat per parti i riksdagsvalet 2022.
MANDAT_2022 = {
    "V": 24, "S": 107, "MP": 18, "C": 24,
    "L": 16, "M": 68, "KD": 19, "SD": 73,
}

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
ANTAL_SIMULERINGAR = int(_P.get("antal_simuleringar", 40000))

ANVAND_VALDAGSKORRIGERING = bool(_P.get("anvand_valdagskorrigering", 0))


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

# Aggregat som inte är råmätningar och därför måste exkluderas.
EXKLUDERA = ["Poll of polls", "Mätningarnas mätning", "Svensk väljaropinion",
             "Valprognos 2026", "Sammanvägningar", "Valet"]

# --- Regeringsalternativ -----------------------------------------------------
# Varje alternativ: partier som ingår i underlaget (regering eller stöd).
# 'krav' anger extra villkor utöver 50 % av mandaten.
REGERINGSALTERNATIV = [
    {
        "id": "tidoe",
        "namn": "Fortsatt Tidöstyre (M+KD+L med SD-stöd)",
        "partier": ["M", "KD", "L", "SD"],
        "beskrivning": "Nuvarande konstellation: M, KD och L i regering med SD som samarbetsparti.",
    },
    {
        "id": "s_ledd_vanster",
        "namn": "S-ledd regering med V, MP och C",
        "partier": ["S", "V", "MP", "C"],
        "beskrivning": "Klassiskt rödgrönt underlag utökat med C.",
    },
    {
        "id": "s_mp_c",
        "namn": "S+MP+C",
        "partier": ["S", "MP", "C"],
        "beskrivning": "Mittenvänsterregering utan V, kräver att C klarar spärren.",
        "krav": {"minst": {"C": 0.04}},
    },
    {
        "id": "s_c_kd_mp",
        "namn": "S+C+KD+MP",
        "partier": ["S", "C", "KD", "MP"],
        "beskrivning": "Blocköverskridande mittenregering där KD bryter med Tidösamarbetet.",
    },
    {
        "id": "alliansen",
        "namn": "Alliansen (M+KD+C+L)",
        "partier": ["M", "KD", "C", "L"],
        "beskrivning": "Den återuppståndna Alliansen, borgerlig regering utan SD-stöd.",
    },
    {
        "id": "s_m_blocköverskridande",
        "namn": "Blocköverskridande S+M",
        "partier": ["S", "M"],
        "beskrivning": "Stor koalition mellan de två största partierna.",
    },
    {
        "id": "s_m_c_l",
        "namn": "Mittenkoalition S+M+C+L",
        "partier": ["S", "M", "C", "L"],
        "beskrivning": "Bred mittenregering som utesluter både V och SD.",
    },
    {
        "id": "hoger_utan_l",
        "namn": "M+KD+SD utan L",
        "partier": ["M", "KD", "SD"],
        "beskrivning": "Högerregering där L faller under spärren eller lämnar samarbetet.",
    },
    {
        "id": "s_ensam_minoritet",
        "namn": "S-ledd minoritet utan C",
        "partier": ["S", "V", "MP"],
        "beskrivning": "Rödgrönt underlag utan C, kräver mycket starkt S-resultat.",
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
