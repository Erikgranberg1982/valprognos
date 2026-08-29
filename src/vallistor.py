"""Kandidat- och vallisteprognos från Valmyndighetens kandidaturfil.

Modellen i projektet räknar mandat per parti och valområde. Den här modulen
kopplar de mandaten till Valmyndighetens namnvalsedlar och plockar kandidater i
listordning. Det är en approximation: personröster och faktisk röstfördelning
mellan flera namnvalsedlar inom samma parti är ännu okända.
"""
from __future__ import annotations

import re
from pathlib import Path
import zipfile
import numpy as np
import pandas as pd
import requests

import config as cfg

ROT = Path(__file__).resolve().parent.parent
CACHE = ROT / "data" / "valmyndigheten"
OUTPUT = ROT / "output"

KANDIDATURER_URL = "https://data.val.se/filer/val2026/parti/kandidaturer.csv"
DELTAGANDE_PARTIER_URL = "https://data.val.se/filer/val2026/parti/deltagande-partier.csv"
KANDIDATURER_2022_URL = "https://data.val.se/filer/val2022/parti/kandidaturer.zip"

VALTYP_FOR_NIVA = {"riksdag": "RD", "region": "RF", "kommun": "KF"}
NIVA_FOR_VALTYP = {"RD": "riksdag", "R": "region", "RF": "region", "KF": "kommun"}

PARTIKOD_TILL_PARTI = {
    "0001": "M",
    "0002": "S",
    "0003": "L",
    "0004": "C",
    "0005": "V",
    "0055": "MP",
    "0068": "KD",
    "0110": "SD",
}

PARTIBETECKNING_TILL_PARTI = {
    "moderaterna": "M",
    "arbetarepartiet-socialdemokraterna": "S",
    "liberalerna (tidigare folkpartiet)": "L",
    "centerpartiet": "C",
    "vänsterpartiet": "V",
    "miljöpartiet de gröna": "MP",
    "kristdemokraterna": "KD",
    "sverigedemokraterna": "SD",
}

KOLUMN_MAP = {
    "VALTYP": "valtyp",
    "VALOMRÅDESKOD": "valomradeskod",
    "VALOMRÅDESNAMN": "valomradesnamn",
    "VALKRETSKOD": "valkretskod",
    "VALKRETSNAMN": "valkretsnamn",
    "PARTIBETECKNING": "partibeteckning",
    "PARTIFÖRKORTNING": "partiforkortning",
    "PARTIKOD": "partikod",
    "VALSEDELSSTATUS": "valsedelsstatus",
    "LISTNUMMER": "listnummer",
    "VALKRETSBETECKNING PÅ VALSEDELN": "valkretsbeteckning",
    "ORDNING": "ordning",
    "ANMÄLDAKANDIDATER": "anmalda_kandidater",
    "SAMTYCKE": "samtycke",
    "FÖRKLARING": "forklaring",
    "KANDIDATNUMMER": "kandidatnummer",
    "NAMN": "namn",
    "ÅLDER_PÅ_VALDAGEN": "alder_pa_valdagen",
    "KÖN": "kon",
    "FOLKBOKFÖRINGSKOMMUN": "folkbokforingskommun",
    "VALSEDELSUPPGIFT": "valsedelsuppgift",
    "ANTAL VALSEDLAR FÖR DEN SPECIFIKA LISTAN": "antal_valsedlar",
    "GILTIG": "giltig",
}

DELTAGANDE_KOLUMN_MAP = {
    "VALTYP": "valtyp",
    "VALOMRÅDESKOD": "valomradeskod",
    "VALOMRÅDESNAMN": "valomradesnamn",
    "VALKRETSKOD": "valkretskod",
    "VALKRETSNAMN": "valkretsnamn",
    "LÄNSKOD": "lanskod",
    "LÄNSNAMN": "lansnamn",
    "PARTIBETECKNING": "partibeteckning",
    "PARTIFÖRKORTNING": "partiforkortning",
    "PARTIKOD": "partikod",
    "ANMÄLNINGSDATUM": "anmalningsdatum",
    "BESLUTSDATUM": "beslutsdatum",
    "DIARIENUMMER": "diarienummer",
    "REGISTRERADPARTIBETECKNING": "registrerad_partibeteckning",
    "ANMÄLDAKANDIDATER": "anmalda_kandidater",
    "DELTAGANDEGRUND": "deltagandegrund",
}

KANDIDATKOLUMNER = [
    "niva", "valtyp", "omrade_kod", "omrade_namn", "valkretskod",
    "valkretsnamn", "prognos_parti", "parti", "partibeteckning", "partiforkortning",
    "prognosmandat_parti", "listnummer", "listnamn", "listbeteckning",
    "listval_metod", "listval_varning", "valkretsmetod", "kandidatval_metod",
    "historisk_valkrets_2022", "hemvalkrets_2026", "prioritetsskäl",
    "deltagandegrund", "listmandat", "mandat_i_lista", "ordning",
    "kandidatnummer", "namn", "alder_pa_valdagen", "kon", "folkbokforingskommun",
    "valsedelsuppgift", "kalla",
]

LAN_TILL_RD_VALKRETS = {
    "03": "03", "04": "04", "05": "05", "06": "06", "07": "07", "08": "08",
    "09": "09", "10": "10", "13": "15", "17": "21", "18": "22", "19": "23",
    "20": "24", "21": "25", "22": "26", "23": "27", "24": "28", "25": "29",
}

SPECIALKOMMUN_TILL_RD_VALKRETS = {
    "stockholm": "01",
    "malmö": "11",
    "gotland": "09",
    "göteborg": "16",
}

UTELAMNADE_KOLUMNER = [
    "niva", "valtyp", "omrade_kod", "omrade_namn", "valkretskod",
    "valkretsnamn", "parti", "mandat", "antal_listor", "valkretsmetod", "skäl",
    "listnummer", "listnamn",
]


def _hamta(url: str, filnamn: str, tvinga: bool = False) -> Path:
    """Hämtar en rådatafil och cachelagrar den lokalt."""
    CACHE.mkdir(parents=True, exist_ok=True)
    fil = CACHE / filnamn
    if fil.exists() and not tvinga:
        return fil

    svar = requests.get(
        url,
        headers={"User-Agent": "svensk-valprediktor/0.1"},
        timeout=180,
    )
    svar.raise_for_status()
    fil.write_bytes(svar.content)
    return fil


def hamta_kandidaturfil(tvinga: bool = False) -> Path:
    """Hämtar Valmyndighetens fil med alla kandidaturer i valet 2026."""
    return _hamta(KANDIDATURER_URL, "kandidaturer_2026.csv", tvinga)


def hamta_deltagande_partier_fil(tvinga: bool = False) -> Path:
    """Hämtar Valmyndighetens fil med alla deltagande partier i valet 2026."""
    return _hamta(DELTAGANDE_PARTIER_URL, "deltagande_partier_2026.csv", tvinga)


def hamta_kandidaturfil_2022(tvinga: bool = False) -> Path:
    """Hämtar Valmyndighetens kandidaturfil från valet 2022."""
    return _hamta(KANDIDATURER_2022_URL, "kandidaturer_2022.zip", tvinga)


def _norm(text: object) -> str:
    return " ".join(str(text or "").strip().casefold().split())



# Kommun till riksdagsvalkrets. Ett län är en valkrets, utom Stockholm, Skåne
# och Västra Götaland som är delade. Används för att placera en kandidat i sin
# hemvalkrets när partiet har mandat där.
_HEMVALKRETS: dict[str, str] | None = None


def _hemvalkrets_tabell() -> dict[str, str]:
    global _HEMVALKRETS
    if _HEMVALKRETS is not None:
        return _HEMVALKRETS
    fil = Path(__file__).resolve().parent.parent / "data" / "kommun_riksdagsvalkrets.csv"
    ut: dict[str, str] = {}
    if fil.exists():
        try:
            tabell = pd.read_csv(fil, dtype=str)
            for _, rad in tabell.iterrows():
                ut[_norm(rad["kommun"])] = str(rad["valkrets"])
        except Exception:
            pass
    _HEMVALKRETS = ut
    return ut



# Hur många riksdagslistor varje kandidat står på. Regeln om historisk
# valkrets och hemvalkrets gäller bara den som står på flera listor: den som
# bara står på en har ingen valfrihet, och ska följa listordningen.
_LISTOR_PER_KANDIDAT: dict[tuple[str, str], int] | None = None

# Från och med så här många listor räknas kandidaten som rikstäckande.
FLERLISTEGRANS = 2


def _listor_per_kandidat() -> dict[tuple[str, str], int]:
    global _LISTOR_PER_KANDIDAT
    if _LISTOR_PER_KANDIDAT is not None:
        return _LISTOR_PER_KANDIDAT
    ut: dict[tuple[str, str], int] = {}
    try:
        k = las_kandidaturer()
        rd = k[k["valtyp"].eq("RD")]
        if "giltig" in rd.columns:
            rd = rd[rd["giltig"]]
        for _, rad in rd.iterrows():
            nyckel = (str(rad.get("parti") or ""), _norm(rad.get("namn")))
            if nyckel[0] and nyckel[1]:
                ut[nyckel] = ut.get(nyckel, 0) + 1
    except Exception:
        pass
    _LISTOR_PER_KANDIDAT = ut
    return ut


def star_pa_flera_listor(parti: str, namn: object) -> bool:
    """Om kandidaten står på flera riksdagslistor och alltså kan placeras."""
    return _listor_per_kandidat().get(
        (str(parti), _norm(namn)), 1) >= FLERLISTEGRANS

def hemvalkrets_for_kandidat(folkbokforingskommun: object) -> str:
    """Riksdagsvalkretsen som kandidatens hemkommun tillhör.

    En kandidat som står på flera listor placeras hellre i sin hemvalkrets än
    där hen råkar stå högst. Regeln är en approximation av vad
    dubbelvalsavvecklingen ger: personröster är oftast starkast på hemorten,
    och den som blir vald på flera håll behåller platsen där personrösternas
    andel är högst.
    """
    kommun = _norm(folkbokforingskommun)
    if not kommun:
        return ""
    return _hemvalkrets_tabell().get(kommun, "")

def _zfill_text(varde: object, langd: int) -> str:
    text = str(varde or "").strip()
    return text.zfill(langd) if text else ""


def _talserie(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(
        serie.astype(str).str.replace(" ", "", regex=False).str.replace(",", ".", regex=False),
        errors="coerce",
    )


def _partikod_till_parti(rad: pd.Series) -> str | None:
    fork = str(rad.get("partiforkortning") or "").strip().upper()
    if fork in cfg.PARTIER:
        return fork
    kod = _zfill_text(rad.get("partikod"), 4)
    if kod in PARTIKOD_TILL_PARTI:
        return PARTIKOD_TILL_PARTI[kod]
    return PARTIBETECKNING_TILL_PARTI.get(_norm(rad.get("partibeteckning")))


def _listbeteckning(rad: pd.Series) -> str:
    for kolumn in ("valkretsbeteckning", "valkretsnamn", "valomradesnamn"):
        varde = str(rad.get(kolumn) or "").strip()
        if varde:
            return varde
    return "Hela valområdet"


def _listnamn(rad: pd.Series) -> str:
    parti = str(rad.get("partibeteckning") or rad.get("parti") or "").strip()
    beteckning = str(rad.get("listbeteckning") or "").strip()
    if parti and beteckning:
        return f"{parti} - {beteckning}"
    return parti or beteckning


def _expandera_listsegment(segment: str, valkretsnamn: list[str]) -> str:
    segment = segment.strip()
    norm_segment = _norm(segment)
    if not norm_segment:
        return segment

    for namn in valkretsnamn:
        norm_namn = _norm(namn)
        if norm_namn == norm_segment or norm_namn.startswith(norm_segment):
            return namn

    match = re.match(r"^(\d+)\b", segment)
    if match:
        prefix = f"{match.group(1)} "
        traffar = [namn for namn in valkretsnamn if str(namn).startswith(prefix)]
        if len(traffar) == 1:
            return traffar[0]
    return segment


def _expandera_listbeteckning(beteckning: str, valkretsnamn: list[str]) -> str:
    if not beteckning or " och " not in beteckning:
        return beteckning
    delar = [_expandera_listsegment(del_text, valkretsnamn)
             for del_text in beteckning.split(" och ")]
    return " och ".join(delar)


def _forbattra_listbeteckningar(df: pd.DataFrame) -> pd.DataFrame:
    """Försöker laga avkortade listnamn med valområdets valkretsnamn."""
    ut = df.copy()
    for (_valtyp, _omrade), idx in ut.groupby(["valtyp", "valomradeskod"]).groups.items():
        valkretsnamn = sorted({
            str(v).strip() for v in ut.loc[idx, "valkretsnamn"].unique()
            if str(v).strip()
        })
        if not valkretsnamn:
            continue
        beteckningar = ut.loc[idx, "listbeteckning"].drop_duplicates()
        mapping = {
            beteckning: _expandera_listbeteckning(str(beteckning), valkretsnamn)
            for beteckning in beteckningar
        }
        ut.loc[idx, "listbeteckning"] = ut.loc[idx, "listbeteckning"].map(mapping)
    return ut


def las_kandidaturer(tvinga: bool = False) -> pd.DataFrame:
    """Läser och normaliserar Valmyndighetens kandidaturfil."""
    fil = hamta_kandidaturfil(tvinga)
    df = pd.read_csv(
        fil,
        sep=";",
        dtype=str,
        encoding="utf-8-sig",
        keep_default_na=False,
    ).rename(columns=KOLUMN_MAP)

    for kolumn in KOLUMN_MAP.values():
        if kolumn not in df.columns:
            df[kolumn] = ""
        df[kolumn] = df[kolumn].astype(str).str.strip()

    df["partikod"] = df["partikod"].map(lambda x: _zfill_text(x, 4))
    df["listnummer"] = df["listnummer"].map(lambda x: _zfill_text(x, 5))
    df["ordning"] = _talserie(df["ordning"])
    df["antal_valsedlar"] = _talserie(df["antal_valsedlar"]).fillna(0.0)
    df["giltig"] = df["giltig"].str.upper().eq("J")
    df["niva"] = df["valtyp"].map(NIVA_FOR_VALTYP)
    df["parti"] = df.apply(_partikod_till_parti, axis=1)
    df["partinyckel"] = df["parti"].fillna("").astype(str)
    utan_partikod = df["partinyckel"].eq("")
    df.loc[utan_partikod, "partinyckel"] = df.loc[utan_partikod, "partibeteckning"].map(_norm)
    df["listbeteckning"] = df.apply(_listbeteckning, axis=1)
    df = _forbattra_listbeteckningar(df)
    df["listnamn"] = df.apply(_listnamn, axis=1)
    return df


def las_kandidaturer_2022(tvinga: bool = False) -> pd.DataFrame:
    """Läser och normaliserar Valmyndighetens kandidaturfil för valet 2022."""
    fil = hamta_kandidaturfil_2022(tvinga)
    with zipfile.ZipFile(fil) as zf:
        with zf.open("kandidaturer.csv") as fh:
            df = pd.read_csv(
                fh,
                sep=";",
                dtype=str,
                encoding="utf-8-sig",
                keep_default_na=False,
            ).rename(columns=KOLUMN_MAP)

    for kolumn in KOLUMN_MAP.values():
        if kolumn not in df.columns:
            df[kolumn] = ""
        df[kolumn] = df[kolumn].astype(str).str.strip()

    df["partikod"] = df["partikod"].map(lambda x: _zfill_text(x, 4))
    df["listnummer"] = df["listnummer"].map(lambda x: _zfill_text(x, 5))
    df["valkretskod"] = df["valkretskod"].map(lambda x: _zfill_text(x, 2))
    df["ordning"] = _talserie(df["ordning"])
    df["giltig"] = df["giltig"].str.upper().eq("J")
    df["niva"] = df["valtyp"].map(NIVA_FOR_VALTYP)
    df["parti"] = df.apply(_partikod_till_parti, axis=1)
    df["partinyckel"] = df["parti"].fillna("").astype(str)
    utan_partikod = df["partinyckel"].eq("")
    df.loc[utan_partikod, "partinyckel"] = df.loc[utan_partikod, "partibeteckning"].map(_norm)
    df["listbeteckning"] = df.apply(_listbeteckning, axis=1)
    df = _forbattra_listbeteckningar(df)
    df["listnamn"] = df.apply(_listnamn, axis=1)
    df["namn_norm"] = df["namn"].map(_norm)
    return df


def las_deltagande_partier(tvinga: bool = False) -> pd.DataFrame:
    """Läser deltagande partier och normaliserar partinycklar."""
    fil = hamta_deltagande_partier_fil(tvinga)
    df = pd.read_csv(
        fil,
        sep=";",
        dtype=str,
        encoding="utf-8-sig",
        keep_default_na=False,
    ).rename(columns=DELTAGANDE_KOLUMN_MAP)

    for kolumn in DELTAGANDE_KOLUMN_MAP.values():
        if kolumn not in df.columns:
            df[kolumn] = ""
        df[kolumn] = df[kolumn].astype(str).str.strip()

    df["partikod"] = df["partikod"].map(lambda x: _zfill_text(x, 4))
    df["valomradeskod"] = df.apply(
        lambda r: str(r["valomradeskod"]).zfill(4 if r["valtyp"] == "KF" else 2),
        axis=1,
    )
    df["niva"] = df["valtyp"].map(NIVA_FOR_VALTYP)
    df["parti"] = df.apply(_partikod_till_parti, axis=1)
    df["partinyckel"] = df["parti"].fillna("").astype(str)
    utan_partikod = df["partinyckel"].eq("")
    df.loc[utan_partikod, "partinyckel"] = df.loc[utan_partikod, "partibeteckning"].map(_norm)
    return df


def vallistor(kandidaturer: pd.DataFrame | None = None) -> pd.DataFrame:
    """Sammanfattar alla namnvalsedlar, en rad per unik lista."""
    df = kandidaturer if kandidaturer is not None else las_kandidaturer()
    df = df[df["listnummer"] != ""].copy()
    if df.empty:
        return pd.DataFrame()

    def unik_text(serie: pd.Series) -> str:
        varden = sorted({str(v).strip() for v in serie if str(v).strip()})
        return varden[0] if len(varden) == 1 else ""

    grupper = [
        "valtyp", "niva", "valomradeskod", "valomradesnamn", "partikod",
        "partibeteckning", "partiforkortning", "parti", "partinyckel", "listnummer",
        "listbeteckning", "listnamn",
    ]
    ut = (df.groupby(grupper, dropna=False)
          .agg(
              antal_kandidater=("kandidatnummer", "nunique"),
              antal_valsedlar=("antal_valsedlar", "max"),
              valkretskod=("valkretskod", unik_text),
              valkretsnamn=("valkretsnamn", unik_text),
              valkretsar=("valkretskod", "nunique"),
          )
          .reset_index())
    giltiga = (df[df["giltig"]].groupby(grupper, dropna=False)["kandidatnummer"]
               .nunique()
               .rename("antal_giltiga")
               .reset_index())
    ut = ut.merge(giltiga, on=grupper, how="left")
    ut["antal_giltiga"] = ut["antal_giltiga"].fillna(0).astype(int)
    return ut.sort_values(["valtyp", "valomradeskod", "partibeteckning", "listnummer"])


def _partinyckel(parti: str) -> str:
    if parti in cfg.PARTIER:
        return parti
    return _norm(parti)


def _riksdagsmandat_2022_per_valkrets() -> dict[tuple[str, str], int]:
    """Härleder partimandat 2022 per valkrets från SCB:s rösttal."""
    try:
        import scb_data
        roster = scb_data.hamta_riksdagsval_per_valkrets_roster(["2022"])
    except Exception:
        return {}

    if roster.empty:
        return {}

    try:
        roster_2022 = roster.xs("2022", level="ar")
    except (KeyError, ValueError):
        return {}

    ut: dict[tuple[str, str], int] = {}
    for parti, partimandat in cfg.MANDAT_2022.items():
        if parti not in roster_2022.columns:
            continue
        fordelning = _fordela_mandat(roster_2022[parti], partimandat)
        for valkretskod, mandat in fordelning.items():
            if mandat > 0:
                ut[(parti, str(valkretskod).zfill(2))] = int(mandat)
    return ut



# Valkretsnamn i Riksdagens register till Valmyndighetens tvåsiffriga koder.
_VALKRETSKOD_FOR_NAMN: dict[str, str] | None = None


def _valkretskoder() -> dict[str, str]:
    """Kopplar valkretsens namn till dess kod, från 2022 års kandidaturfil."""
    global _VALKRETSKOD_FOR_NAMN
    if _VALKRETSKOD_FOR_NAMN is not None:
        return _VALKRETSKOD_FOR_NAMN
    ut: dict[str, str] = {}
    try:
        # Valkretsarnas namn och koder hämtas från SCB. Riksdagens register
        # skriver dem utan ordet valkrets, så båda formerna läggs in.
        import requests
        svar = requests.get(
            "https://api.scb.se/OV0104/v1/doris/sv/ssd/ME/ME0104/ME0104C/ME0104T3",
            headers={"User-Agent": "svensk-valprediktor/0.1"}, timeout=30)
        for variabel in svar.json()["variables"]:
            if variabel["code"] != "Region":
                continue
            for kod, namn in zip(variabel["values"], variabel["valueTexts"]):
                if not kod.startswith("VR") or kod == "VR00":
                    continue
                siffror = "".join(c for c in kod if c.isdigit()).zfill(2)
                for variant in (namn, namn.replace(" valkrets", ""),
                                namn.replace("s valkrets", "")):
                    ut.setdefault(_norm(variant), siffror)
            break
    except Exception:
        pass
    _VALKRETSKOD_FOR_NAMN = ut
    return ut


def _invalda_facit() -> dict[tuple[str, str], str]:
    """Var varje riksdagsledamot faktiskt valdes in 2022.

    Källa är Riksdagens öppna data, sparad i data/invalda_riksdag_2022.csv.
    Det är facit och ersätter modellens egen skattning, som gissade fel för
    partiledare: de står som plats ett på trettio till sextio listor samtidigt,
    alla registrerade på valområdet Riket, så listorna säger inget om var de
    faktiskt tog plats.
    """
    fil = Path(__file__).resolve().parent.parent / "data" / "invalda_riksdag_2022.csv"
    if not fil.exists():
        return {}
    koder = _valkretskoder()
    ut: dict[tuple[str, str], str] = {}
    try:
        tabell = pd.read_csv(fil, dtype=str)
    except Exception:
        return {}
    for _, rad in tabell.iterrows():
        parti = str(rad.get("parti") or "").strip()
        namn = _norm(rad.get("namn"))
        kod = koder.get(_norm(rad.get("valkrets")), "")
        if parti and namn and kod:
            ut[(parti, namn)] = kod
    return ut

def _invalda_riksdag_2022_proxy() -> dict[tuple[str, str], str]:
    """Proxy för var toppnamn blev invalda 2022.

    Valmyndighetens personröstfil saknar en enkel invald-flagga i rådatafilen.
    Vi använder därför 2022 års kandidaturfil och SCB:s rösttal: partiets
    faktiska 2022-mandat bryts ned på valkretsar och de översta giltiga namnen
    på respektive valkretslista antas vara invalda där. Det räcker som
    geografisk prioritering för återkommande nationella toppnamn 2026.
    """
    mandat = _riksdagsmandat_2022_per_valkrets()
    if not mandat:
        return {}

    try:
        kandidaturer = las_kandidaturer_2022()
    except Exception:
        return {}

    rd = kandidaturer[
        kandidaturer["valtyp"].eq("RD")
        & kandidaturer["parti"].isin(cfg.PARTIER)
        & kandidaturer["giltig"]
        & kandidaturer["ordning"].notna()
        & kandidaturer["namn_norm"].ne("")
    ].copy()
    if rd.empty:
        return {}

    ut: dict[tuple[str, str], str] = {}
    for (parti, valkretskod), antal in mandat.items():
        grupp = rd[(rd["parti"].eq(parti)) & (rd["valkretskod"].eq(valkretskod))]
        if grupp.empty:
            continue
        listor, _metod, _varning, skäl = _valj_lista(vallistor(grupp))
        if skäl is not None or listor.empty:
            continue
        listnummer = str(listor.iloc[0]["listnummer"])
        kandidater = (grupp[grupp["listnummer"].eq(listnummer)]
                      .sort_values(["ordning", "kandidatnummer"])
                      .drop_duplicates("namn_norm"))
        for _, kandidat in kandidater.head(int(antal)).iterrows():
            ut[(parti, str(kandidat["namn_norm"]))] = valkretskod
    return ut


class VallisteIndex:
    """Snabba uppslag för listor och kandidater.

    Kandidaturfilen är stor nog för att upprepade DataFrame-filter blir dyrt.
    Indexet byggs en gång och används sedan av riksdags-, region- och
    kommunprognosen.
    """

    def __init__(self, kandidaturer: pd.DataFrame,
                 deltagande_partier: pd.DataFrame | None = None):
        self.kandidaturer = kandidaturer
        self.listor = vallistor(kandidaturer)
        self.deltagande_partier = (
            deltagande_partier if deltagande_partier is not None else pd.DataFrame()
        )
        self._lagg_till_deltagandegrund()
        self._listor_by_alias: dict[tuple[str, str, str], pd.DataFrame] = {}
        self._kandidater_by_lista: dict[tuple[str, str, str, str], pd.DataFrame] = {}
        # Facit från Riksdagens register, kompletterat med modellens egen
        # skattning för namn som inte finns där, exempelvis ledamöter som
        # bytt namn eller kandidater som aldrig tog plats.
        self.invalda_riksdag_2022 = _invalda_riksdag_2022_proxy()
        self.invalda_riksdag_2022.update(_invalda_facit())
        self._bygg_listindex()
        self._bygg_kandidatindex()

    def _lagg_till_deltagandegrund(self) -> None:
        if self.listor.empty:
            self.listor["deltagandegrund"] = ""
            return
        if self.deltagande_partier.empty:
            self.listor["deltagandegrund"] = ""
            return

        deltagande = (self.deltagande_partier
                      .groupby(["valtyp", "valomradeskod", "partikod", "partinyckel"],
                               dropna=False)["deltagandegrund"]
                      .agg(lambda s: ",".join(sorted({str(v) for v in s if str(v)})))
                      .reset_index())
        self.listor = self.listor.merge(
            deltagande,
            on=["valtyp", "valomradeskod", "partikod", "partinyckel"],
            how="left",
        )
        self.listor["deltagandegrund"] = self.listor["deltagandegrund"].fillna("")

    def _bygg_listindex(self) -> None:
        if self.listor.empty:
            return
        omradesgrupper = {
            (str(vtyp), str(omrade)): grupp.copy()
            for (vtyp, omrade), grupp in self.listor.groupby(
                ["valtyp", "valomradeskod"], dropna=False)
        }
        for (valtyp, omrade), grupp in omradesgrupper.items():
            self._listor_by_alias[(valtyp, omrade, _partinyckel("ÖVRIGA"))] = (
                self._ovriga_listor(grupp)
            )

        for (valtyp, omrade, partinyckel), grupp in self.listor.groupby(
            ["valtyp", "valomradeskod", "partinyckel"], dropna=False
        ):
            aliases = {str(partinyckel)}
            aliases.update(grupp["partibeteckning"].map(_norm))
            aliases.update(grupp["partiforkortning"].map(_norm))
            aliases.discard("")
            for alias in aliases:
                self._listor_by_alias[(str(valtyp), str(omrade), alias)] = grupp.copy()

    def _ovriga_listor(self, grupp: pd.DataFrame) -> pd.DataFrame:
        ovriga = grupp[~grupp["parti"].isin(cfg.PARTIER)].copy()
        if ovriga.empty:
            return ovriga
        representerade = ovriga[ovriga["deltagandegrund"].astype(str).str.contains("R")]
        return representerade if not representerade.empty else ovriga

    def _bygg_kandidatindex(self) -> None:
        kandidater = self.kandidaturer[
            self.kandidaturer["listnummer"].ne("")
            & self.kandidaturer["giltig"]
            & self.kandidaturer["ordning"].notna()
        ].drop_duplicates(["listnummer", "ordning", "kandidatnummer"])

        if kandidater.empty:
            return
        for nyckel, grupp in kandidater.groupby(
            ["valtyp", "valomradeskod", "partinyckel", "listnummer"], dropna=False
        ):
            self._kandidater_by_lista[tuple(str(x) for x in nyckel)] = (
                grupp.sort_values(["ordning", "kandidatnummer"]).copy()
            )

    def listor_for(self, valtyp: str, parti: str,
                   valomradeskod: str | None = None) -> pd.DataFrame:
        kod = "" if valomradeskod is None else str(valomradeskod).zfill(
            4 if valtyp == "KF" else 2)
        alias = _partinyckel(parti)
        if valomradeskod is not None:
            return self._listor_by_alias.get((valtyp, kod, alias), pd.DataFrame())

        delar = []
        for (vtyp, _omrade, nyckel), grupp in self._listor_by_alias.items():
            if vtyp == valtyp and nyckel == alias:
                delar.append(grupp)
        if not delar:
            return pd.DataFrame()
        return pd.concat(delar, ignore_index=True).drop_duplicates(
            ["valtyp", "valomradeskod", "partinyckel", "listnummer"])

    def kandidater_for_lista(self, valtyp: str, valomradeskod: str,
                             partinyckel: str, listnummer: str) -> pd.DataFrame:
        nyckel = (valtyp, valomradeskod, str(partinyckel), listnummer)
        return self._kandidater_by_lista.get(nyckel, pd.DataFrame())

    def historisk_riksdagsvalkrets(self, parti: str, namn: object) -> str:
        return self.invalda_riksdag_2022.get((parti, _norm(namn)), "")


def _listor_for(index: VallisteIndex, valtyp: str, parti: str,
                valomradeskod: str | None = None) -> pd.DataFrame:
    return index.listor_for(valtyp, parti, valomradeskod)


def _fordela_mandat(vikter: pd.Series, mandat: int) -> dict[str, int]:
    """Fördelar mandat mellan listor med samma jämkade uddatal som modellen."""
    mandat = int(mandat)
    if mandat <= 0 or vikter.empty:
        return {}

    vikter = vikter.fillna(0.0).astype(float)
    if (vikter <= 0).all():
        vikter = pd.Series(1.0, index=vikter.index)
    else:
        vikter = vikter.clip(lower=0.0)

    tilldelning = {str(k): 0 for k in vikter.index}
    divisorer = {str(k): 1.2 for k in vikter.index}
    vikt = {str(k): float(v) for k, v in vikter.items()}
    for _ in range(mandat):
        vinnare = max(vikt, key=lambda k: vikt[k] / divisorer[k])
        tilldelning[vinnare] += 1
        divisorer[vinnare] = 2 * tilldelning[vinnare] + 1
    return tilldelning


def _mandat_i_rad(rad: pd.Series) -> dict[str, int]:
    mandat = {}
    for parti in cfg.PARTIER:
        varde = rad.get(f"mandat_{parti}")
        if varde is None or pd.isna(varde):
            continue
        mandat[parti] = int(varde)

    ovriga = rad.get("mandat_ÖVRIGA")
    if ovriga is not None and not pd.isna(ovriga) and int(ovriga) > 0:
        mandat["ÖVRIGA"] = int(ovriga)

    lokalt = rad.get("lokalt_parti")
    lokalt_mandat = rad.get("lokalt_mandat")
    if lokalt and lokalt_mandat is not None and not pd.isna(lokalt_mandat):
        antal = int(lokalt_mandat)
        if antal > 0:
            mandat[str(lokalt)] = antal
    return mandat


def _omradesfilter(df: pd.DataFrame, omrade: str | None) -> pd.DataFrame:
    if not omrade:
        return df
    sok = _norm(omrade)
    index_match = df.index.astype(str).map(_norm).str.contains(sok, regex=False)
    namn_match = df["namn"].astype(str).map(_norm).str.contains(sok, regex=False)
    return df[index_match | namn_match]


def _uteslut_parti(listor: pd.DataFrame, parti: str | None) -> pd.DataFrame:
    if not parti or listor.empty:
        return listor
    sok = _norm(parti)
    mask = (
        listor["partibeteckning"].map(_norm).eq(sok)
        | listor["partiforkortning"].map(_norm).eq(sok)
        | listor["partinyckel"].astype(str).map(_norm).eq(sok)
    )
    return listor[~mask]


def _utelamna(utelamnade: list[dict] | None, valtyp: str, valomradeskod: str,
              omradesnamn: str, parti: str, partimandat: int, skäl: str,
              listor: pd.DataFrame | None = None,
              valkretskod: str = "", valkretsnamn: str = "",
              valkretsmetod: str = "") -> None:
    if utelamnade is None:
        return
    listor = listor if listor is not None else pd.DataFrame()
    utelamnade.append({
        "niva": NIVA_FOR_VALTYP.get(valtyp, valtyp),
        "valtyp": valtyp,
        "omrade_kod": valomradeskod,
        "omrade_namn": omradesnamn,
        "valkretskod": valkretskod,
        "valkretsnamn": valkretsnamn,
        "parti": parti,
        "mandat": int(partimandat),
        "antal_listor": int(len(listor)),
        "valkretsmetod": valkretsmetod,
        "skäl": skäl,
        "listnummer": ";".join(listor.get("listnummer", pd.Series(dtype=str)).astype(str).tolist()),
        "listnamn": " | ".join(listor.get("listnamn", pd.Series(dtype=str)).astype(str).tolist()),
    })


def _valj_lista(listor: pd.DataFrame) -> tuple[pd.DataFrame, str, str, str | None]:
    """Väljer lista enligt konservativ regel.

    Returnerar vald lista, metod, varning och eventuellt utelämningsskäl.
    """
    listor = listor.drop_duplicates("listnummer").copy()
    if listor.empty:
        return listor, "", "", "saknar matchande lista"
    if len(listor) == 1:
        return listor, "exakt_en_lista", "", None

    antal = pd.to_numeric(listor["antal_valsedlar"], errors="coerce").fillna(0.0)
    max_antal = float(antal.max())
    if max_antal <= 0:
        return listor, "", "", "flera listor och saknar valsedelsantal"

    topp = listor[antal.eq(max_antal)]
    if len(topp) != 1:
        return listor, "", "", "flera listor med samma högsta valsedelsantal"

    vald = topp.copy()
    total = float(antal.sum())
    andel = max_antal / total * 100 if total > 0 else 0.0
    varning = (
        "Vald som proxy eftersom listan har flest tryckta valsedlar; "
        "faktisk röstfördelning mellan listor är okänd."
    )
    if andel < 50:
        varning += f" Listan står bara för {andel:.1f} procent av listupplagan."
    return vald, "proxy_flest_valsedlar", varning, None


def _valj_identisk_topplista(index: VallisteIndex, valtyp: str, valomradeskod: str,
                            parti: str, listor: pd.DataFrame,
                            partimandat: int) -> tuple[pd.DataFrame, str, str, str | None]:
    """Löser listnummerdubletter när toppnamnen är identiska."""
    antal = pd.to_numeric(listor["antal_valsedlar"], errors="coerce").fillna(0.0)
    max_antal = float(antal.max()) if not antal.empty else 0.0
    topp = listor[antal.eq(max_antal)].drop_duplicates("listnummer").copy()
    if max_antal <= 0 or len(topp) <= 1:
        return listor, "", "", "flera listor med samma högsta valsedelsantal"

    jamfor_antal = max(int(partimandat), 1)
    sekvenser = []
    for _, lista in topp.iterrows():
        kandidater = index.kandidater_for_lista(
            valtyp, valomradeskod, lista["partinyckel"], str(lista["listnummer"]))
        sekvens = tuple(kandidater.sort_values(["ordning", "kandidatnummer"])
                        .head(jamfor_antal)["namn"].map(_norm).tolist())
        sekvenser.append(sekvens)

    if not sekvenser or not sekvenser[0] or any(s != sekvenser[0] for s in sekvenser[1:]):
        return listor, "", "", "flera listor med samma högsta valsedelsantal"

    vald = topp.sort_values("listnummer").head(1).copy()
    varning = (
        "Flera listnummer har samma valsedelsantal, men toppnamnen som behövs "
        "för mandatprognosen är identiska; lägsta listnummer används som proxy."
    )
    return vald, "proxy_identisk_topplista", varning, None


def _rd_valkretsar(index: VallisteIndex, omrade: str | None = None) -> pd.DataFrame:
    vk = (index.kandidaturer[index.kandidaturer["valtyp"].eq("RD")]
          [["valkretskod", "valkretsnamn"]]
          .drop_duplicates()
          .sort_values("valkretskod"))
    if omrade:
        sok = _norm(omrade)
        mask = (
            vk["valkretskod"].astype(str).map(_norm).str.contains(sok, regex=False)
            | vk["valkretsnamn"].astype(str).map(_norm).str.contains(sok, regex=False)
        )
        vk = vk[mask]
    return vk


def _rd_listor_i_valkrets(listor: pd.DataFrame, valkretsnamn: str) -> pd.DataFrame:
    """Listorna som ett parti ställer upp med i en riksdagsvalkrets.

    En lista kan heta som valkretsen, som länet, eller HELA LANDET. Skåne,
    Stockholm och Västra Götaland är delade i flera valkretsar, och där kan
    partiet ha en gemensam länslista: Kristdemokraterna har en lista kallad
    Skåne län som gäller i alla fyra skånska valkretsar.

    Matchningen görs därför i tre steg: exakt valkretsnamn, sedan länslista,
    sedan HELA LANDET. Enbart en delsträngsjämförelse räcker inte, eftersom
    Skåne län inte innehåller Skåne läns södra utan tvärtom.
    """
    if listor.empty:
        return listor

    namn = _norm(valkretsnamn)
    beteckning = listor["listbeteckning"].map(_norm)
    hela = beteckning.eq("hela landet")

    # Länets namn: Skåne läns södra -> skane lan
    lan = namn
    for suffix in (" läns södra", " läns västra", " läns norra och östra",
                   " läns norra", " läns östra", " läns"):
        if lan.endswith(suffix):
            lan = lan[: -len(suffix)] + " län"
            break

    exakt = listor[beteckning.eq(namn) & ~hela]
    if not exakt.empty:
        return exakt

    # Länslista som täcker flera valkretsar, eller namn som innehåller
    # valkretsens namn. Den väljs framför HELA LANDET även när den senare har
    # större upplaga, eftersom en lista med länets namn är den partiet
    # kampanjar med lokalt. Vilken väljarna faktiskt använder går inte att veta
    # före valet, så valet markeras som osäkert.
    lansmatch = (beteckning.eq(lan) | beteckning.str.contains(namn, regex=False))
    lokala = listor[lansmatch & ~hela]
    if not lokala.empty:
        if hela.any():
            lokala = lokala.copy()
            lokala["listval_notis"] = (
                "Partiet har både en lista för länet och en för hela landet. "
                "Länslistan används, eftersom den är den partiet kampanjar med "
                "lokalt, men vilken väljarna faktiskt lägger går inte att veta "
                "före valet.")
        return lokala

    hela_listor = listor[hela]
    if not hela_listor.empty:
        return hela_listor
    return listor


def _riksdagsmandat_per_valkrets(sammanfattning: pd.DataFrame,
                                 index: VallisteIndex,
                                 omrade: str | None = None) -> pd.DataFrame:
    """Bryter ned nationella partimandat till riksdagsvalkretsar.

    SCB:s rösttal 2022 per valkrets används som geografisk bas och skalas med
    den nationella prognosförändringen för partiet. Om SCB-underlaget saknas
    används Valmyndighetens listupplaga som nödfallback.
    """
    sm = sammanfattning.set_index("parti")
    partimandat = {
        parti: int(sm.at[parti, "mandat_median"])
        for parti in cfg.PARTIER
        if parti in sm.index
    }
    diff = cfg.MANDAT_TOTALT - sum(partimandat.values())
    if diff and partimandat:
        storst = max(partimandat, key=partimandat.get)
        partimandat[storst] = max(0, partimandat[storst] + diff)

    valkretsar = _rd_valkretsar(index, omrade)
    rader = []
    rostbas = pd.DataFrame()
    try:
        import scb_data
        roster = scb_data.hamta_riksdagsval_per_valkrets_roster(["2022"])
        rostbas = roster.xs("2022", level="ar") if not roster.empty else pd.DataFrame()
    except Exception:
        rostbas = pd.DataFrame()

    for parti, antal_partimandat in partimandat.items():
        if antal_partimandat <= 0:
            continue
        alla_listor = _listor_for(index, "RD", parti, "00")
        vikter = {}
        listor_per_vk = {}
        for _, vk in valkretsar.iterrows():
            listor = _rd_listor_i_valkrets(alla_listor, vk["valkretsnamn"])
            listor_per_vk[vk["valkretskod"]] = listor

        if not rostbas.empty and parti in rostbas.columns:
            prognoskolumn = "stod_medel" if "stod_medel" in sm.columns else "prognos"
            trend = float(sm.at[parti, prognoskolumn]) / cfg.VALRESULTAT_2022.get(parti, 1.0)
            for _, vk in valkretsar.iterrows():
                kod = str(vk["valkretskod"]).zfill(2)
                vikter[kod] = float(rostbas[parti].get(kod, 0.0)) * trend
            valkretsmetod = "scb_roster_2022_trend"
        else:
            for _, vk in valkretsar.iterrows():
                kod = str(vk["valkretskod"]).zfill(2)
                listor = listor_per_vk.get(kod, pd.DataFrame())
                vikter[kod] = float(listor["antal_valsedlar"].sum()) if not listor.empty else 0.0
            valkretsmetod = "valsedelsupplaga_proxy"

        vk_mandat = _fordela_mandat(pd.Series(vikter), antal_partimandat)
        for _, vk in valkretsar.iterrows():
            kod = vk["valkretskod"]
            antal = vk_mandat.get(kod, 0)
            if antal <= 0:
                continue
            rader.append({
                "valkretskod": kod,
                "valkretsnamn": vk["valkretsnamn"],
                "parti": parti,
                "mandat": antal,
                "listor": listor_per_vk.get(kod, pd.DataFrame()),
                "valkretsmetod": valkretsmetod,
            })
    return pd.DataFrame(rader)


def _valj_kandidater(index: VallisteIndex, valtyp: str, valomradeskod: str,
                     omradesnamn: str, parti: str, partimandat: int,
                     listor: pd.DataFrame, valda: set[str],
                     valkretskod: str = "", valkretsnamn: str = "",
                     valkretsmetod: str = "",
                     reserverade_valkretsar: set[str] | None = None,
                     utelamnade: list[dict] | None = None) -> list[dict]:
    if partimandat <= 0 or listor.empty:
        if partimandat > 0:
            _utelamna(utelamnade, valtyp, valomradeskod, omradesnamn, parti,
                      partimandat, "saknar matchande lista",
                      valkretskod=valkretskod, valkretsnamn=valkretsnamn,
                      valkretsmetod=valkretsmetod)
        return []

    listor, listval_metod, listval_varning, skäl = _valj_lista(listor)
    if skäl == "flera listor med samma högsta valsedelsantal":
        listor, listval_metod, listval_varning, skäl = _valj_identisk_topplista(
            index, valtyp, valomradeskod, parti, listor, partimandat)
    if skäl is not None:
        _utelamna(utelamnade, valtyp, valomradeskod, omradesnamn, parti,
                  partimandat, skäl, listor,
                  valkretskod=valkretskod, valkretsnamn=valkretsnamn,
                  valkretsmetod=valkretsmetod)
        return []

    listmandat = {str(listor.iloc[0]["listnummer"]): int(partimandat)}
    rader = []
    listor = listor.set_index("listnummer", drop=False)
    reserverade_valkretsar = reserverade_valkretsar or set()

    for listnummer, mandat in sorted(listmandat.items(), key=lambda x: (-x[1], x[0])):
        if mandat <= 0 or listnummer not in listor.index:
            continue
        lista = listor.loc[listnummer]
        notis = str(lista.get("listval_notis") or "").strip()
        if notis and not listval_varning:
            listval_varning = notis
        parti_label = str(lista["partiforkortning"] or lista["partibeteckning"])
        kandidater = index.kandidater_for_lista(
            valtyp, valomradeskod, lista["partinyckel"], listnummer)
        if valtyp == "RD" and not kandidater.empty and valkretskod:
            kandidater = kandidater.copy()
            kandidater["historisk_valkrets_2022"] = kandidater["namn"].map(
                lambda namn: index.historisk_riksdagsvalkrets(parti, namn)
            )
            kandidater["hemvalkrets_2026"] = kandidater[
                "folkbokforingskommun"].map(hemvalkrets_for_kandidat)

            # Prioritetsordning för vem som tar mandatet i valkretsen:
            #   0  var invald här 2022
            #   1  har sin hemkommun här
            #   2  övriga, enligt listordning
            # Kandidater som hör hemma i en annan valkrets sorteras sist, så
            # att ett nationellt toppnamn inte tar en plats där hen inte hör
            # hemma bara för att hen står överst på listan.
            har_kod = str(valkretskod).zfill(2)
            har_namn = str(valkretsnamn or "")

            # Ingen omsortering här. Vallagen fyller platserna i listordning,
            # och först därefter löses dubbelvalen. Se _losa_dubbelval.
            kandidater = kandidater.sort_values(["ordning", "kandidatnummer"])
        lista_valkretskod = str(lista.get("valkretskod") or "")
        lista_valkretsnamn = str(lista.get("valkretsnamn") or lista["listbeteckning"] or "")
        plats = 0
        for _, kandidat in kandidater.iterrows():
            historisk_vk = index.historisk_riksdagsvalkrets(parti, kandidat.get("namn"))
            kandidatnyckel = str(kandidat.get("kandidatnummer") or "").strip()
            if not kandidatnyckel:
                kandidatnyckel = f"{parti}:{_norm(kandidat.get('namn'))}"
            if kandidatnyckel in valda:
                continue
            valda.add(kandidatnyckel)
            plats += 1
            hemvk = hemvalkrets_for_kandidat(kandidat.get("folkbokforingskommun"))
            if valtyp == "RD" and historisk_vk and historisk_vk == str(valkretskod).zfill(2):
                kandidatval_metod = "historisk_valkrets_2022"
                prioritetsskal = "Var invald i valkretsen 2022."
            elif valtyp == "RD" and hemvk and hemvk == str(valkretsnamn or ""):
                kandidatval_metod = "hemvalkrets_2026"
                prioritetsskal = (
                    f"Folkbokförd i {kandidat.get('folkbokforingskommun')}, "
                    "som ligger i valkretsen.")
            else:
                kandidatval_metod = "listordning"
                prioritetsskal = (
                    f"Plats {int(kandidat['ordning'])} på listan."
                    if valtyp == "RD" else "")
            rader.append({
                "niva": NIVA_FOR_VALTYP.get(valtyp, valtyp),
                "valtyp": valtyp,
                "omrade_kod": valomradeskod,
                "omrade_namn": omradesnamn,
                "valkretskod": valkretskod or lista_valkretskod,
                "valkretsnamn": valkretsnamn or lista_valkretsnamn,
                "prognos_parti": parti,
                "parti": parti if parti != "ÖVRIGA" else parti_label,
                "partibeteckning": lista["partibeteckning"],
                "partiforkortning": lista["partiforkortning"],
                "prognosmandat_parti": int(partimandat),
                "listnummer": listnummer,
                "listnamn": lista["listnamn"],
                "listbeteckning": lista["listbeteckning"],
                "listval_metod": listval_metod,
                "listval_varning": listval_varning,
                "valkretsmetod": valkretsmetod,
                "kandidatval_metod": kandidatval_metod,
                "historisk_valkrets_2022": historisk_vk,
                "hemvalkrets_2026": hemvk if valtyp == "RD" else "",
                "prioritetsskäl": prioritetsskal,
                "deltagandegrund": str(lista.get("deltagandegrund") or ""),
                "listmandat": int(mandat),
                "mandat_i_lista": plats,
                "ordning": int(kandidat["ordning"]),
                "kandidatnummer": str(kandidat.get("kandidatnummer") or ""),
                "namn": kandidat["namn"],
                "alder_pa_valdagen": kandidat.get("alder_pa_valdagen", ""),
                "kon": kandidat.get("kon", ""),
                "folkbokforingskommun": kandidat.get("folkbokforingskommun", ""),
                "valsedelsuppgift": kandidat.get("valsedelsuppgift", ""),
                "kalla": KANDIDATURER_URL,
            })
            if plats >= mandat:
                break
    return rader


def kandidatprognos_riksdag(sammanfattning: pd.DataFrame,
                            index: VallisteIndex | None = None,
                            omrade: str | None = None,
                            utelamnade: list[dict] | None = None) -> pd.DataFrame:
    """Predikterar riksdagsledamöter enligt vallagens ordning.

    Valet går till i två steg, och modellen följer samma ordning.

    Först fylls varje valkrets platser uppifrån och ned i listordning, utan
    hänsyn till var kandidaten hör hemma. Ett namn som står högt på en
    rikstäckande lista blir därför preliminärt vald i flera valkretsar
    samtidigt, precis som i verkligheten.

    Sedan löses dubbelvalen. En kandidat som valts i flera valkretsar behåller
    en plats och de övriga återförklaras lediga, varpå nästa namn på just den
    listan tar över. Vallagen ger platsen där jämförelsetalet är högst, vilket
    kräver rösträkning. Modellen väljer i stället den valkrets där kandidaten
    satt 2022, annars hemkommunens valkrets, annars den där partiet är
    starkast. Det är en approximation, men den bygger på rätt mekanism: en
    person tar en plats, och den lediga går till nästa på listan.

    En tidigare version hoppade i stället över kandidater som hörde hemma i en
    annan valkrets redan i första steget. Det gav mandat till namn långt ner på
    listorna även när den överhoppade inte fick något mandat alls någon
    annanstans, vilket vallagen inte tillåter.
    """
    index = index if index is not None else VallisteIndex(
        las_kandidaturer(), las_deltagande_partier())
    nedbrutet = _riksdagsmandat_per_valkrets(sammanfattning, index, omrade)
    if nedbrutet.empty:
        return pd.DataFrame(columns=KANDIDATKOLUMNER)

    # Steg 1: fyll varje valkrets i listordning. Samma person kan bli vald i
    # flera valkretsar, vilket löses i steg 2.
    preliminart: list[dict] = []
    for _, rad in nedbrutet.iterrows():
        preliminart.extend(_valj_kandidater(
            index=index,
            valtyp="RD",
            valomradeskod="00",
            omradesnamn="Riket",
            parti=rad["parti"],
            partimandat=int(rad["mandat"]),
            listor=rad["listor"],
            valda=set(),          # ingen global spärr i första steget
            valkretskod=rad["valkretskod"],
            valkretsnamn=rad["valkretsnamn"],
            valkretsmetod=rad.get("valkretsmetod", ""),
            reserverade_valkretsar=set(),
            utelamnade=utelamnade,
        ))

    return _losa_dubbelval(preliminart, nedbrutet, index, utelamnade)



def _ersattarrad(tom: dict, kandidat) -> dict:
    """Bygger raden för den som tar över en ledig plats."""
    rad = dict(tom)
    rad.update({
        "namn": kandidat["namn"],
        "ordning": int(kandidat["ordning"]),
        "kandidatnummer": str(kandidat.get("kandidatnummer") or ""),
        "alder_pa_valdagen": kandidat.get("alder_pa_valdagen", ""),
        "kon": kandidat.get("kon", ""),
        "folkbokforingskommun": kandidat.get("folkbokforingskommun", ""),
        "valsedelsuppgift": kandidat.get("valsedelsuppgift", ""),
        "kandidatval_metod": "dubbelvalsavveckling",
        "prioritetsskäl": (
            f"Platsen blev ledig när {tom['namn']} tog sitt mandat i en annan "
            "valkrets. Nästa möjliga namn på listan tar över."),
    })
    return rad


def _losa_dubbelval(preliminart: list[dict], nedbrutet: pd.DataFrame,
                    index: VallisteIndex,
                    utelamnade: list[dict] | None) -> pd.DataFrame:
    """Löser dubbelval och fyller de platser som blir lediga.

    Motsvarar vallagens dubbelvalsavveckling: den som valts i flera valkretsar
    behåller en plats, övriga återförklaras lediga och går till nästa namn på
    listan i den valkretsen.
    """
    def nyckel(rad):
        nr = str(rad.get("kandidatnummer") or "").strip()
        return f'{rad["prognos_parti"]}:{nr}' if nr else \
               f'{rad["prognos_parti"]}:{_norm(rad.get("namn"))}'

    # Vilka valkretsar varje person valts i
    platser: dict[str, list[dict]] = {}
    for rad in preliminart:
        platser.setdefault(nyckel(rad), []).append(rad)

    # Partiets styrka per valkrets, för att avgöra var en person stannar när
    # varken 2022 eller hemkommunen pekar ut en valkrets.
    styrka = {}
    for _, rad in nedbrutet.iterrows():
        styrka[(rad["parti"], str(rad["valkretskod"]).zfill(2))] = int(rad["mandat"])

    behalls: dict[str, dict] = {}
    lediga: list[dict] = []
    for _, rader in platser.items():
        if len(rader) == 1:
            behalls[id(rader[0])] = rader[0]
            continue

        parti = rader[0]["prognos_parti"]
        namn = rader[0].get("namn")
        hist = index.historisk_riksdagsvalkrets(parti, namn)
        hem = hemvalkrets_for_kandidat(rader[0].get("folkbokforingskommun"))

        def rang(rad):
            kod = str(rad.get("valkretskod") or "").zfill(2)
            if hist and kod == hist:
                return (0, 0)
            if hem and str(rad.get("valkretsnamn") or "") == hem:
                return (1, 0)
            return (2, -styrka.get((parti, kod), 0))

        rader = sorted(rader, key=rang)
        behalls[id(rader[0])] = rader[0]
        lediga.extend(rader[1:])

    # Fyll de lediga platserna med nästa namn på respektive lista.
    tagna = {nyckel(r) for r in behalls.values()}
    resultat = list(behalls.values())

    # Lediga platser fylls iterativt, som vallagen föreskriver.
    #
    # Nästa namn på listan tar över platsen. Om det namnet redan tagit en plats
    # någon annanstans går turen vidare till nästa. En kandidat hoppas alltså
    # bara över när hen faktiskt är vald, aldrig för att hen skulle kunna bli
    # det i en annan valkrets.
    #
    # Eftersom en person kan bli vald i flera valkretsar även i det här steget
    # körs det om tills inget mer ändras: varje ny dubbelvinst löses på samma
    # sätt som den första omgången.
    def _kandidatlista(tom):
        parti = tom["prognos_parti"]
        kand = index.kandidater_for_lista(
            "RD", tom["omrade_kod"], parti, tom["listnummer"])
        if kand.empty:
            return None
        return kand.sort_values(["ordning", "kandidatnummer"])

    for _ in range(10):   # konvergerar normalt på ett par varv
        nya_lediga = []
        tilldelade = {}   # kandidatnyckel -> lista med platser hen tagit

        for tom in lediga:
            kand = _kandidatlista(tom)
            if kand is None:
                continue
            parti = tom["prognos_parti"]
            for _, kandidat in kand.iterrows():
                nr = str(kandidat.get("kandidatnummer") or "").strip()
                kn = f"{parti}:{nr}" if nr else f"{parti}:{_norm(kandidat.get('namn'))}"
                if kn in tagna:
                    continue
                rad = _ersattarrad(tom, kandidat)
                tilldelade.setdefault(kn, []).append(rad)
                break

        if not tilldelade:
            break

        # Den som tagit plats i flera valkretsar behåller en, resten blir lediga
        for kn, rader in tilldelade.items():
            if len(rader) == 1:
                resultat.append(rader[0])
                tagna.add(kn)
                continue

            parti = rader[0]["prognos_parti"]
            namn = rader[0].get("namn")
            hist = index.historisk_riksdagsvalkrets(parti, namn)
            hem = hemvalkrets_for_kandidat(rader[0].get("folkbokforingskommun"))

            def _rang(rad):
                kod = str(rad.get("valkretskod") or "").zfill(2)
                if hist and kod == hist:
                    return (0, 0)
                if hem and str(rad.get("valkretsnamn") or "") == hem:
                    return (1, 0)
                return (2, -styrka.get((parti, kod), 0))

            rader = sorted(rader, key=_rang)
            resultat.append(rader[0])
            tagna.add(kn)
            nya_lediga.extend(rader[1:])

        lediga = nya_lediga
        if not lediga:
            break

    return pd.DataFrame(resultat, columns=KANDIDATKOLUMNER)


def kandidatprognos_lokal(niva: str, sammanfattning: pd.DataFrame,
                          index: VallisteIndex | None = None,
                          omrade: str | None = None,
                          utelamnade: list[dict] | None = None) -> pd.DataFrame:
    """Predikterar kandidater i region- eller kommunfullmäktige."""
    if niva not in ("region", "kommun"):
        raise ValueError("niva måste vara 'region' eller 'kommun'")
    index = index if index is not None else VallisteIndex(
        las_kandidaturer(), las_deltagande_partier())
    valtyp = VALTYP_FOR_NIVA[niva]
    sammanfattning = _omradesfilter(sammanfattning, omrade)

    rader = []
    for omradeskod, rad in sammanfattning.iterrows():
        if niva == "region":
            valomradeskod = str(omradeskod)[:2].zfill(2)
        else:
            valomradeskod = str(omradeskod).zfill(4)
        valda_i_omrade: dict[str, set[str]] = {}
        lokalt_parti = rad.get("lokalt_parti")
        for parti, mandat in _mandat_i_rad(rad).items():
            if mandat <= 0:
                continue
            listor = _listor_for(index, valtyp, parti, valomradeskod)
            if parti == "ÖVRIGA":
                listor = _uteslut_parti(listor, lokalt_parti)
            rader.extend(_valj_kandidater(
                index=index,
                valtyp=valtyp,
                valomradeskod=valomradeskod,
                omradesnamn=str(rad["namn"]),
                parti=parti,
                partimandat=mandat,
                listor=listor,
                valda=valda_i_omrade.setdefault(parti, set()),
                utelamnade=utelamnade,
            ))
    return pd.DataFrame(rader, columns=KANDIDATKOLUMNER)


def kandidatprognoser(res: dict, niva: str | None = None,
                      omrade: str | None = None,
                      tvinga_vallistor: bool = False,
                      index: VallisteIndex | None = None) -> dict[str, pd.DataFrame]:
    """Bygger kandidatprognoser för en eller flera valnivåer."""
    index = index if index is not None else VallisteIndex(
        las_kandidaturer(tvinga=tvinga_vallistor),
        las_deltagande_partier(tvinga=tvinga_vallistor),
    )
    valda_nivaer = ["riksdag", "region", "kommun"] if niva is None else [niva]
    ut = {}
    utelamnade: list[dict] = []

    if "riksdag" in valda_nivaer:
        ut["riksdag"] = kandidatprognos_riksdag(
            res["sammanfattning"], index, omrade, utelamnade)

    if "region" in valda_nivaer:
        import regionmodell
        regioner = regionmodell.sammanfatta(regionmodell.prognos_per_region(res["snitt"]))
        ut["region"] = kandidatprognos_lokal("region", regioner, index, omrade, utelamnade)

    if "kommun" in valda_nivaer:
        import kommunmodell
        kommuner = kommunmodell.sammanfatta(kommunmodell.prognos_per_kommun(res["snitt"]))
        ut["kommun"] = kandidatprognos_lokal("kommun", kommuner, index, omrade, utelamnade)

    ut["utelamnade"] = pd.DataFrame(utelamnade, columns=UTELAMNADE_KOLUMNER)
    return ut


def skriv_kandidatprognoser(res: dict, niva: str | None = None,
                            omrade: str | None = None,
                            tvinga_vallistor: bool = False,
                            output_dir: Path | None = None) -> dict[str, dict]:
    """Sparar vallisteöversikt och kandidatprognoser till output/."""
    output_dir = output_dir or OUTPUT
    output_dir.mkdir(parents=True, exist_ok=True)
    kandidaturer = las_kandidaturer(tvinga=tvinga_vallistor)
    deltagande_partier = las_deltagande_partier(tvinga=tvinga_vallistor)
    index = VallisteIndex(kandidaturer, deltagande_partier)

    listfil = output_dir / "vallistor_2026.csv"
    index.listor.to_csv(listfil, index=False, encoding="utf-8")

    prognoser = kandidatprognoser(
        res,
        niva=niva,
        omrade=omrade,
        tvinga_vallistor=False,
        index=index,
    )
    ut: dict[str, dict] = {
        "vallistor": {"fil": listfil, "antal": len(index.listor)}
    }
    for nyckel, df in prognoser.items():
        fil = output_dir / f"kandidatprognos_{nyckel}.csv"
        df.to_csv(fil, index=False, encoding="utf-8")
        ut[nyckel] = {"fil": fil, "antal": len(df)}
    return ut


def skriv_terminal(utfiler: dict[str, dict]) -> None:
    print("\nKandidat- och vallistefiler")
    print("-" * 66)
    for niva, info in utfiler.items():
        print(f"  {niva:<10}{info['antal']:>6} rader  {info['fil']}")
    print("  Listval: exakt en lista används direkt; unik störst upplaga används med varning.")
    print("  Oklara flerlistelägen sparas som utelämnade med skäl; personröster ingår inte.\n")


if __name__ == "__main__":
    import prognos
    from datetime import date

    df = prognos.las_matningar(prognos.ROT / "data" / "matningar.csv")
    referens = df["datum"].max().date()
    res = prognos.kor_prognos(df, referens, date.fromisoformat(cfg.VALDAG))
    skriv_terminal(skriv_kandidatprognoser(res))
