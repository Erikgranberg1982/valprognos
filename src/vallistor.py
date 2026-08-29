"""Kandidat- och vallisteprognos från Valmyndighetens kandidaturfil.

Modellen i projektet räknar mandat per parti och valområde. Den här modulen
kopplar de mandaten till Valmyndighetens namnvalsedlar och plockar kandidater i
listordning. Det är en approximation: personröster och faktisk röstfördelning
mellan flera namnvalsedlar inom samma parti är ännu okända.
"""
from __future__ import annotations

import re
from pathlib import Path
import numpy as np
import pandas as pd
import requests

import config as cfg

ROT = Path(__file__).resolve().parent.parent
CACHE = ROT / "data" / "valmyndigheten"
OUTPUT = ROT / "output"

KANDIDATURER_URL = "https://data.val.se/filer/val2026/parti/kandidaturer.csv"
DELTAGANDE_PARTIER_URL = "https://data.val.se/filer/val2026/parti/deltagande-partier.csv"

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
    "deltagandegrund", "listmandat", "mandat_i_lista", "ordning",
    "kandidatnummer", "namn", "alder_pa_valdagen", "kon",
    "folkbokforingskommun", "valsedelsuppgift", "kalla",
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


def _norm(text: object) -> str:
    return " ".join(str(text or "").strip().casefold().split())


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
    if listor.empty:
        return listor
    namn = _norm(valkretsnamn)
    beteckning = listor["listbeteckning"].map(_norm)
    hela = beteckning.eq("hela landet")
    match = beteckning.eq(namn) | beteckning.str.contains(namn, regex=False)
    lokala = listor[match & ~hela]
    if not lokala.empty:
        return lokala
    hela_listor = listor[hela]
    if not hela_listor.empty:
        return hela_listor
    return listor[match] if match.any() else listor


def _riksdagsmandat_per_valkrets(sammanfattning: pd.DataFrame,
                                 index: VallisteIndex,
                                 omrade: str | None = None) -> pd.DataFrame:
    """Bryter ned nationella partimandat till riksdagsvalkretsar.

    Valmyndighetens antal valsedlar används som fördelningsnyckel. Det är ett
    praktiskt proxy-mått för valkretsstorlek när modellen bara har nationellt
    partistöd.
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

    for parti, antal_partimandat in partimandat.items():
        if antal_partimandat <= 0:
            continue
        alla_listor = _listor_for(index, "RD", parti, "00")
        vikter = {}
        listor_per_vk = {}
        for _, vk in valkretsar.iterrows():
            listor = _rd_listor_i_valkrets(alla_listor, vk["valkretsnamn"])
            listor_per_vk[vk["valkretskod"]] = listor
            vikt = float(listor["antal_valsedlar"].sum()) if not listor.empty else 0.0
            vikter[vk["valkretskod"]] = vikt

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
            })
    return pd.DataFrame(rader)


def _valj_kandidater(index: VallisteIndex, valtyp: str, valomradeskod: str,
                     omradesnamn: str, parti: str, partimandat: int,
                     listor: pd.DataFrame, valda: set[str],
                     valkretskod: str = "", valkretsnamn: str = "") -> list[dict]:
    if partimandat <= 0 or listor.empty:
        return []

    listor = listor.drop_duplicates("listnummer")
    listmandat = _fordela_mandat(listor.set_index("listnummer")["antal_valsedlar"],
                                 partimandat)
    rader = []
    listor = listor.set_index("listnummer", drop=False)

    for listnummer, mandat in sorted(listmandat.items(), key=lambda x: (-x[1], x[0])):
        if mandat <= 0 or listnummer not in listor.index:
            continue
        lista = listor.loc[listnummer]
        parti_label = str(lista["partiforkortning"] or lista["partibeteckning"])
        kandidater = index.kandidater_for_lista(
            valtyp, valomradeskod, lista["partinyckel"], listnummer)
        lista_valkretskod = str(lista.get("valkretskod") or "")
        lista_valkretsnamn = str(lista.get("valkretsnamn") or lista["listbeteckning"] or "")
        plats = 0
        for _, kandidat in kandidater.iterrows():
            kandidatnyckel = str(kandidat.get("kandidatnummer") or "").strip()
            if not kandidatnyckel:
                kandidatnyckel = f"{parti}:{_norm(kandidat.get('namn'))}"
            if kandidatnyckel in valda:
                continue
            valda.add(kandidatnyckel)
            plats += 1
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
                            omrade: str | None = None) -> pd.DataFrame:
    """Predikterar riksdagsledamöter via prognosmandat per parti och valkrets."""
    index = index if index is not None else VallisteIndex(
        las_kandidaturer(), las_deltagande_partier())
    nedbrutet = _riksdagsmandat_per_valkrets(sammanfattning, index, omrade)
    rader = []
    valda_per_parti = {p: set() for p in cfg.PARTIER}

    for _, rad in nedbrutet.iterrows():
        parti = rad["parti"]
        rader.extend(_valj_kandidater(
            index=index,
            valtyp="RD",
            valomradeskod="00",
            omradesnamn="Riket",
            parti=parti,
            partimandat=int(rad["mandat"]),
            listor=rad["listor"],
            valda=valda_per_parti.setdefault(parti, set()),
            valkretskod=rad["valkretskod"],
            valkretsnamn=rad["valkretsnamn"],
        ))
    return pd.DataFrame(rader, columns=KANDIDATKOLUMNER)


def kandidatprognos_lokal(niva: str, sammanfattning: pd.DataFrame,
                          index: VallisteIndex | None = None,
                          omrade: str | None = None) -> pd.DataFrame:
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

    if "riksdag" in valda_nivaer:
        ut["riksdag"] = kandidatprognos_riksdag(
            res["sammanfattning"], index, omrade)

    if "region" in valda_nivaer:
        import regionmodell
        regioner = regionmodell.sammanfatta(regionmodell.prognos_per_region(res["snitt"]))
        ut["region"] = kandidatprognos_lokal("region", regioner, index, omrade)

    if "kommun" in valda_nivaer:
        import kommunmodell
        kommuner = kommunmodell.sammanfatta(kommunmodell.prognos_per_kommun(res["snitt"]))
        ut["kommun"] = kandidatprognos_lokal("kommun", kommuner, index, omrade)

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
    print("  Kandidaterna tas i listordning; personröster ingår inte.\n")


if __name__ == "__main__":
    import prognos
    from datetime import date

    df = prognos.las_matningar(prognos.ROT / "data" / "matningar.csv")
    referens = df["datum"].max().date()
    res = prognos.kor_prognos(df, referens, date.fromisoformat(cfg.VALDAG))
    skriv_terminal(skriv_kandidatprognoser(res))
