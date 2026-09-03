"""Hämtar resultat från kommunestyre- och fylkestingsvalget hos SSB.

Två tabeller, båda med godkända röster per parti och område:

  01180  Kommunestyrevalget, 1945 till 2023
  01181  Fylkestingsvalget, 1975 till 2023

De nio riksdagspartierna redovisas var för sig. Lokala partier ligger i tre
poster som modellen behandlar som en klump, eftersom de inte kan
prognosticeras var för sig:

  91  Lokale lister
  92  Andre lister
  90  Felleslister, med underposter 90a till 90h

Felleslistorna är gemensamma listor där två eller flera partier ställer upp
tillsammans. De hör historiskt hemma i äldre val och är nästan borta 2023, men
räknas till LOKALT eftersom rösterna inte går att fördela på de ingående
partierna.

Övriga rikstäckande småpartier, som Pensjonistpartiet, Industri- og
Næringspartiet och Demokratene, räknas också till LOKALT. Det är en förenkling:
de är inte lokala, men de prognosticeras inte av modellen och deras
lokalvalsstöd följer inte rikstrenden för de nio partierna. Att hålla dem
konstanta är rimligare än att skala dem med ett annat partis trend.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent
CACHE = ROT / "data" / "ssb"

API = "https://data.ssb.no/api/v0/no/table"

TABELL_KOMMUN = "01180"
TABELL_FYLKE = "01181"

# De nio partier modellen prognosticerar, med SSB:s partikoder.
PARTIKOD = {
    "01": "Ap", "02": "FrP", "03": "H", "04": "KrF", "08": "MDG",
    "55": "R", "05": "Sp", "06": "SV", "07": "V",
}

# Samlingsposten för allt annat: lokala listor, felleslistor och
# rikstäckande småpartier utanför de nio.
LOKALT = "LOKALT"

# Aggregatrader som SSB lägger in bland områdena. De är summor och skulle
# annars behandlas som ett eget område: "Hele landet" gav ett kommunestyre
# med 9 115 platser.
AGGREGAT = {"Hele landet", "Hele landet uten Oslo", "Uoppgitt"}


def _hamta(tabell: str, ar: str, cachenamn: str,
           innehall: str = "Godkjente1") -> dict:
    """Hämtar en tabell för ett år, med cache på disk.

    Valresultat ändras inte i efterhand, så en gång hämtad data kan ligga
    kvar. Det gör också bygget oberoende av att SSB svarar.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    fil = CACHE / f"{cachenamn}.json"
    if fil.exists():
        return json.loads(fil.read_text(encoding="utf-8"))

    fraga = {
        "query": [
            {"code": "Region", "selection": {"filter": "all", "values": ["*"]}},
            {"code": "PolitParti", "selection": {"filter": "all", "values": ["*"]}},
            {"code": "ContentsCode",
             "selection": {"filter": "item", "values": [innehall]}},
            {"code": "Tid", "selection": {"filter": "item", "values": [ar]}},
        ],
        "response": {"format": "json-stat2"},
    }
    begaran = urllib.request.Request(
        f"{API}/{tabell}", data=json.dumps(fraga).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(begaran, timeout=120) as svar:
        data = json.load(svar)
    fil.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def _tolka(data: dict) -> dict[str, dict[str, float]]:
    """Plockar ut röster per område och parti ur ett json-stat2-svar.

    Områden vars samtliga värden saknas hoppas över: SSB returnerar rader för
    kommuner som inte fanns vid valet i fråga.
    """
    dim = data["dimension"]
    regioner = list(dim["Region"]["category"]["index"])
    partier = list(dim["PolitParti"]["category"]["index"])
    regionnamn = dim["Region"]["category"]["label"]
    varden = data["value"]

    ut: dict[str, dict[str, float]] = {}
    i = 0
    for region in regioner:
        rader: dict[str, float] = {}
        for partikod in partier:
            v = varden[i]
            i += 1
            if v is None:
                continue
            namn = PARTIKOD.get(partikod, LOKALT)
            rader[namn] = rader.get(namn, 0.0) + float(v)
        namn_ = regionnamn[region]
        if not rader or sum(rader.values()) <= 0 or namn_ in AGGREGAT:
            continue
        ut[namn_] = rader
    return ut


def hamta_kommunval(ar: str = "2023") -> dict[str, dict[str, float]]:
    """Röster per kommun och parti i kommunestyrevalget."""
    return _tolka(_hamta(TABELL_KOMMUN, ar, f"kommunval_{ar}"))


def hamta_fylkesval(ar: str = "2023") -> dict[str, dict[str, float]]:
    """Röster per fylke och parti i fylkestingsvalget.

    Tabellen innehåller både fylken och kommuner, eftersom
    fylkestingsrösterna redovisas ned på kommunnivå. Fylkena filtreras ut i
    fylkesnivåer(), som känner igen dem på namn.
    """
    return _tolka(_hamta(TABELL_FYLKE, ar, f"fylkesval_{ar}"))


TABELL_KOMMUNSTYRE = "04813"


def hamta_kommunestyre_storlek(ar: str = "2023") -> dict[str, int]:
    """Faktiskt antal kommunestyremedlemmer per kommun.

    Tabell 04813 redovisar valda medlemmar per parti, och summan per kommun är
    kommunestyrets storlek. Att hämta den är att föredra framför att skatta
    den ur invånarantalet: kommunen beslutar själv sin storlek inom lagens
    ram, och en skattning ur lagens golv blev i genomsnitt 4,3 platser fel.
    """
    # Tabellen räknar valda medlemmar, inte röster, så ContentsCode skiljer.
    data = _hamta(TABELL_KOMMUNSTYRE, ar, f"kommunstyre_{ar}",
                  innehall="Medlemmer")
    dim = data["dimension"]
    regioner = list(dim["Region"]["category"]["index"])
    partier = list(dim["PolitParti"]["category"]["index"])
    regionnamn = dim["Region"]["category"]["label"]
    varden = data["value"]

    ut: dict[str, int] = {}
    i = 0
    for region in regioner:
        summa = 0
        for _ in partier:
            v = varden[i]
            i += 1
            if v:
                summa += int(v)
        namn_ = regionnamn[region]
        if summa and namn_ not in AGGREGAT:
            ut[normalisera(namn_)] = summa
    return ut


# Fylkena 2024, efter regionreformens delvisa återgång. Koderna är SSB:s
# officiella fylkeskoder, och en kommunkods två första siffror är kommunens
# fylke. Oslo är både kommun och fylke: kommunestyret fyller fylkestingets
# roll, så Oslo har inget separat fylkestingsval.
FYLKESNAMN = {
    "03": "Oslo", "11": "Rogaland", "15": "Møre og Romsdal",
    "18": "Nordland", "31": "Østfold", "32": "Akershus", "33": "Buskerud",
    "34": "Innlandet", "39": "Vestfold", "40": "Telemark", "42": "Agder",
    "46": "Vestland", "50": "Trøndelag", "55": "Troms", "56": "Finnmark",
}

KLASS_API = "https://data.ssb.no/api/klass/v1/classifications"


def kommun_till_fylke(datum: str = "2024-01-01") -> dict[str, str]:
    """Kommunnamn till fylkesnamn, via SSB:s kommunklassifikation.

    Kommunkodens två första siffror är fylkeskoden. Resultatet cachas, dels
    för att bygget inte ska bero på att API:et svarar, dels för att
    indelningen bara ändras vid kommunreformer.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    fil = CACHE / f"kommuner_{datum}.json"
    if fil.exists():
        koder = json.loads(fil.read_text(encoding="utf-8"))
    else:
        begaran = urllib.request.Request(
            f"{KLASS_API}/131/codesAt?date={datum}",
            headers={"Accept": "application/json"})
        with urllib.request.urlopen(begaran, timeout=60) as svar:
            koder = json.load(svar)["codes"]
        fil.write_text(json.dumps(koder, ensure_ascii=False), encoding="utf-8")

    ut = {}
    for post in koder:
        kod = str(post["code"]).zfill(4)
        fylke = FYLKESNAMN.get(kod[:2])
        if not fylke:
            continue
        # Varje namnform pekar på samma fylke, så att valtabellens stavning
        # träffar oavsett vilken variant den använder.
        for variant in _namnvarianter(post["name"]):
            ut[variant] = fylke
    return ut


# Giltighetssuffix som SSB sätter på områden vars indelning gällt en viss
# period, till exempel "Alta (2020-2023)". Suffixet är inte en del av namnet
# och måste bort vid matchning mellan årgångar: annars matchar 2019-data inte
# 2023-data, vilket tappade 114 av 357 kommuner i backtestet.
import re as _re

_PERIODSUFFIX = _re.compile(r"\s*\((?:-?\d{4}|\d{4}\s*-\s*\d{0,4})\)\s*$")

# Fylkessuffix som däremot ska behållas: det särskiljer likanamnade kommuner,
# som Våler (Innlandet) och Våler (Østfold).


def _namnvarianter(namn: str) -> list[str]:
    """Alla former ett områdesnamn kan skrivas i, för matchning.

    Tre saker måste hanteras:

      1. Tvåspråkiga namn skrivs med paralleller åtskilda med bindestreck, och
         formerna stämmer inte alltid mellan SSB:s tabeller: valtabellen
         skriver "Kárásjohka - Karasjok" medan klassifikationen skriver
         "Kárášjohka", med š i stället för s.
      2. Giltighetssuffix som "(2020-2023)" hör till indelningen, inte namnet.
      3. Fylkessuffix som "(Innlandet)" ska däremot behållas, eftersom det
         faktiskt särskiljer två olika kommuner med samma namn.

    Samtliga varianter returneras så att någon av dem träffar.
    """
    varianter = []
    for del_ in namn.split(" - "):
        rent = del_.strip()
        if not rent:
            continue
        varianter.append(rent)
        utan = _PERIODSUFFIX.sub("", rent).strip()
        if utan and utan != rent:
            varianter.append(utan)
    return varianter or [namn.strip()]


def normalisera(namn: str) -> str:
    """Områdets namn utan giltighetssuffix, för jämförelse mellan årgångar."""
    return _PERIODSUFFIX.sub("", _namnvarianter(namn)[0]).strip()


def _rensa_namn(namn: str) -> str:
    """Områdets primära namn, alltså delen före en eventuell parallellform."""
    return _namnvarianter(namn)[0]


def aggregera_till_fylke(roster: dict[str, dict[str, float]],
                         datum: str = "2024-01-01") -> dict[str, dict[str, float]]:
    """Summerar kommunvisa fylkestingsröster till fylkesnivå.

    SSB:s fylkestingstabell redovisar rösterna per kommun, inte per fylke, så
    summeringen måste göras här. Oslo utesluts: kommunen har inget
    fylkestingsval, och dess rader i tabellen är tomma.
    """
    karta = kommun_till_fylke(datum)
    ut: dict[str, dict[str, float]] = {}
    okanda = []
    for omrade, rader in roster.items():
        fylke = next((karta[v] for v in _namnvarianter(omrade) if v in karta),
                     None)
        if fylke is None:
            okanda.append(omrade)
            continue
        if fylke == "Oslo":
            continue
        mal = ut.setdefault(fylke, {})
        for parti, v in rader.items():
            mal[parti] = mal.get(parti, 0.0) + v
    if okanda:
        # Nedlagda kommuner och namnvarianter. Rapporteras men stoppar inte:
        # de utgör en liten andel och saknar plats i dagens indelning.
        print(f"  {len(okanda)} områden utan fylkestillhörighet, "
              f"t.ex. {okanda[:3]}")
    return ut
