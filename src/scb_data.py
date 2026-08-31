"""Hämtar valresultat och regional partisympati från SCB:s öppna API.

Två datakällor används:
  1. Historiska valresultat (ME0104) för region-, kommun- och riksdagsval, som
     ger differensen mellan lokalval och riksdagsval per parti och område.
  2. Partisympatiundersökningen (ME0201) per landsdel, som ger en färsk
     geografisk signal. Den mäter riksdagssympati, inte regionvalsavsikt, och
     redovisas i tio grova landsdelar snarare än per region.
"""
from __future__ import annotations

import csv as _csv
import json
from pathlib import Path

import pandas as pd
import requests

ROT = Path(__file__).resolve().parent.parent
CACHE = ROT / "data" / "scb"
BAS = "https://api.scb.se/OV0104/v1/doris/sv/ssd/ME"
HEADERS = {"User-Agent": "svensk-valprediktor/0.1", "Content-Type": "application/json"}

# SCB använder FP som kod för Liberalerna i valresultaten.
SCB_PARTI = {"M": "M", "C": "C", "FP": "L", "KD": "KD", "MP": "MP",
             "S": "S", "V": "V", "SD": "SD", "ÖVRIGA": "ÖVRIGA"}
SCB_PARTIKODER = list(SCB_PARTI)

# Riksdagsvalkrets till region. Skåne har tre valkretsar och Västra Götaland
# fyra, så de måste summeras för att kunna jämföras med regionvalen.
VALKRETS_TILL_REGION = {
    "VR2": "01L", "VR3": "03L", "VR4": "04L", "VR5": "05L", "VR6": "06L",
    "VR7": "07L", "VR8": "08L", "VR10": "10L",
    "VR12": "12L", "VR13": "12L", "VR14": "12L",
    "VR15": "13L",
    "VR17": "14L", "VR18": "14L", "VR19": "14L", "VR20": "14L",
    "VR21": "17L", "VR22": "18L", "VR23": "19L", "VR24": "20LG",
    "VR25": "21L", "VR26": "22L", "VR27": "23L", "VR28": "24L", "VR29": "25L",
}

REGIONER = {
    "01L": "Stockholm", "03L": "Uppsala", "04L": "Sörmland",
    "05L": "Östergötland", "06L": "Jönköping", "07L": "Kronoberg",
    "08L": "Kalmar", "10L": "Blekinge", "12L": "Skåne", "13L": "Halland",
    "14L": "Västra Götaland", "17L": "Värmland", "18L": "Örebro",
    "19L": "Västmanland", "20LG": "Dalarna", "21L": "Gävleborg",
    "22L": "Västernorrland", "23L": "Jämtland Härjedalen",
    "24L": "Västerbotten", "25L": "Norrbotten",
}

# Landsdelarna i partisympatiundersökningen, med de regioner de täcker.
# Gotland saknar regionval och ingår därför inte.
LANDSDEL_TILL_REGION = {
    "0180": ["01L"], "SE01exkl0180": ["01L"],
    "SE12": ["03L", "04L", "05L", "19L", "18L"],
    "SE09": ["06L", "07L", "08L"],
    "0030": ["12L"], "SE04exkl0030": ["10L", "12L"],
    "1480": ["14L"], "SE0Aexkl1480": ["13L", "14L"],
    "SE06": ["17L", "20LG", "21L"],
    "SE07+SE08": ["22L", "23L", "24L", "25L"],
}


def _post(tabell: str, query: list, cachenamn: str, tvinga: bool = False) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    fil = CACHE / f"{cachenamn}.json"
    if fil.exists() and not tvinga:
        return json.loads(fil.read_text(encoding="utf-8"))
    svar = requests.post(f"{BAS}/{tabell}", headers=HEADERS,
                         json={"query": query, "response": {"format": "json"}},
                         timeout=90)
    svar.raise_for_status()
    data = svar.json()
    fil.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def _till_dataframe(data: dict, kolumner: list[str]) -> pd.DataFrame:
    rader = []
    for post in data.get("data", []):
        nyckel = post["key"]
        if len(nyckel) != len(kolumner):
            continue
        try:
            varde = float(str(post["values"][0]).replace(" ", "").replace(",", "."))
        except (ValueError, IndexError, TypeError):
            continue
        rad = dict(zip(kolumner, nyckel))
        rad["varde"] = varde
        rader.append(rad)
    return pd.DataFrame(rader)


def _andelar(df: pd.DataFrame) -> pd.DataFrame:
    """Räknar om rösttal till andelar inom varje område och år."""
    total = (df.groupby(["omrade", "ar"], as_index=False)["varde"].sum()
             .rename(columns={"varde": "totalt"}))
    m = df.merge(total, on=["omrade", "ar"])
    m = m[m["totalt"] > 0].copy()
    m["andel"] = m["varde"] / m["totalt"] * 100
    return m.pivot_table(index=["omrade", "ar"], columns="parti", values="andel")


def hamta_regionval(ar: list[str] | None = None, tvinga: bool = False) -> pd.DataFrame:
    """Regionfullmäktigvalets resultat per region, som andelar."""
    ar = ar or ["2018", "2022"]
    q = [
        {"code": "Region", "selection": {"filter": "item", "values": list(REGIONER)}},
        {"code": "Partimm", "selection": {"filter": "item", "values": SCB_PARTIKODER}},
        {"code": "ContentsCode", "selection": {"filter": "item", "values": ["ME0104B4"]}},
        {"code": "Tid", "selection": {"filter": "item", "values": ar}},
    ]
    data = _post("ME0104/ME0104B/ME0104T2", q, f"regionval_{'_'.join(ar)}", tvinga)
    df = _till_dataframe(data, ["omrade", "parti", "ar"])
    df["parti"] = df["parti"].map(SCB_PARTI)
    return _andelar(df)


def hamta_riksdagsval_per_region(ar: list[str] | None = None,
                                 tvinga: bool = False) -> pd.DataFrame:
    """Riksdagsvalets resultat aggregerat till regioner, som andelar."""
    ar = ar or ["2018", "2022"]
    q = [
        {"code": "Region", "selection": {"filter": "item",
                                        "values": list(VALKRETS_TILL_REGION)}},
        {"code": "Partimm", "selection": {"filter": "item", "values": SCB_PARTIKODER}},
        {"code": "ContentsCode", "selection": {"filter": "item", "values": ["ME0104B6"]}},
        {"code": "Tid", "selection": {"filter": "item", "values": ar}},
    ]
    data = _post("ME0104/ME0104C/ME0104T3", q, f"riksdagsval_vk_{'_'.join(ar)}", tvinga)
    df = _till_dataframe(data, ["omrade", "parti", "ar"])
    df["parti"] = df["parti"].map(SCB_PARTI)
    df["omrade"] = df["omrade"].map(VALKRETS_TILL_REGION)
    df = df.dropna(subset=["omrade", "parti"])
    df = df.groupby(["omrade", "parti", "ar"], as_index=False)["varde"].sum()
    return _andelar(df)


def hamta_riksdagsval_per_valkrets_roster(ar: list[str] | None = None,
                                          tvinga: bool = False) -> pd.DataFrame:
    """Riksdagsvalets rösttal per riksdagsvalkrets.

    Returnerar råa rösttal, inte andelar. Används när nationella mandat behöver
    brytas ned till de 29 riksdagsvalkretsarna.
    """
    ar = ar or ["2022"]
    valkretsar = [f"VR{i}" for i in range(1, 30)]
    q = [
        {"code": "Region", "selection": {"filter": "item", "values": valkretsar}},
        {"code": "Partimm", "selection": {"filter": "item", "values": SCB_PARTIKODER}},
        {"code": "ContentsCode", "selection": {"filter": "item", "values": ["ME0104B6"]}},
        {"code": "Tid", "selection": {"filter": "item", "values": ar}},
    ]
    data = _post("ME0104/ME0104C/ME0104T3", q,
                 f"riksdagsval_valkrets_roster_{'_'.join(ar)}", tvinga)
    df = _till_dataframe(data, ["omrade", "parti", "ar"])
    if df.empty:
        return pd.DataFrame()
    df["parti"] = df["parti"].map(SCB_PARTI)
    df = df.dropna(subset=["parti"])
    df["omrade"] = df["omrade"].astype(str).str.extract(r"VR(\d+)", expand=False).str.zfill(2)
    df = df.dropna(subset=["omrade"])
    return df.pivot_table(index=["omrade", "ar"], columns="parti", values="varde", aggfunc="sum")


def hamta_psu_landsdel(matmanader: list[str] | None = None,
                       tvinga: bool = False) -> pd.DataFrame:
    """Partisympati per landsdel från partisympatiundersökningen.

    Observera att undersökningen mäter riksdagssympati, inte regionvalsavsikt,
    och att indelningen är tio grova landsdelar. Den används därför som
    geografisk signal, inte som direkt regionvalsprognos.
    """
    matmanader = matmanader or ["2025M05", "2026M05"]
    grupper = list(LANDSDEL_TILL_REGION) + ["Z01"]
    q = [
        {"code": "Sverige10grupper", "selection": {"filter": "item", "values": grupper}},
        {"code": "Partisympati", "selection": {"filter": "item",
         "values": ["m", "c", "l", "kd", "mp", "s", "v", "SD", "övr"]}},
        {"code": "ContentsCode", "selection": {"filter": "item", "values": ["ME0201A1"]}},
        {"code": "Tid", "selection": {"filter": "item", "values": matmanader}},
    ]
    data = _post("ME0201/ME0201B/Partisympati102", q,
                 f"psu_landsdel_{'_'.join(matmanader)}", tvinga)
    df = _till_dataframe(data, ["landsdel", "parti", "tid"])
    df["parti"] = df["parti"].str.upper().replace({"ÖVR": "ÖVRIGA"})
    return df.pivot_table(index=["landsdel", "tid"], columns="parti", values="varde")


def hamta_kommunval(ar: list[str] | None = None, kommuner: list[str] | None = None,
                    tvinga: bool = False) -> pd.DataFrame:
    """Kommunfullmäktigvalets resultat per kommun, som andelar."""
    ar = ar or ["2018", "2022"]
    q = [
        {"code": "Partimm", "selection": {"filter": "item", "values": SCB_PARTIKODER}},
        {"code": "ContentsCode", "selection": {"filter": "item", "values": ["ME0104B1"]}},
        {"code": "Tid", "selection": {"filter": "item", "values": ar}},
    ]
    koder = kommuner or _kommunkoder("ME0104/ME0104A/ME0104T1")
    q.insert(0, {"code": "Region", "selection": {"filter": "item", "values": koder}})
    data = _post("ME0104/ME0104A/ME0104T1", q, f"kommunval_{'_'.join(ar)}", tvinga)
    df = _till_dataframe(data, ["omrade", "parti", "ar"])
    df["parti"] = df["parti"].map(SCB_PARTI)
    return _andelar(df)


def _kommunkoder(tabell: str) -> list[str]:
    """Hämtar samtliga kommunkoder ur en tabells metadata."""
    fil = CACHE / f"meta_{tabell.replace('/', '_')}.json"
    if fil.exists():
        meta = json.loads(fil.read_text(encoding="utf-8"))
    else:
        svar = requests.get(f"{BAS}/{tabell}", headers={"User-Agent": HEADERS["User-Agent"]},
                            timeout=60)
        svar.raise_for_status()
        meta = svar.json()
        CACHE.mkdir(parents=True, exist_ok=True)
        fil.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    for v in meta.get("variables", []):
        if v["code"] == "Region":
            return [k for k in v["values"] if k.isdigit() and len(k) == 4]
    return []


def kommunnamn() -> dict[str, str]:
    """Kod till namn för samtliga kommuner."""
    fil = CACHE / "meta_ME0104_ME0104A_ME0104T1.json"
    if not fil.exists():
        _kommunkoder("ME0104/ME0104A/ME0104T1")
    meta = json.loads(fil.read_text(encoding="utf-8"))
    for v in meta.get("variables", []):
        if v["code"] == "Region":
            return {k: t for k, t in zip(v["values"], v["valueTexts"])
                    if k.isdigit() and len(k) == 4}
    return {}


def hamta_riksdagsval_per_kommun(ar: list[str] | None = None,
                                 tvinga: bool = False) -> pd.DataFrame:
    """Riksdagsvalets resultat per kommun, som andelar.

    Används som referens för kommunvalsprognosen: skillnaden mellan hur en
    kommun röstar i riksdagsvalet och i kommunvalet är det modellen bygger på.
    """
    ar = ar or ["2018", "2022"]
    koder = _kommunkoder("ME0104/ME0104C/ME0104T3")
    if not koder:
        raise RuntimeError("Kunde inte läsa kommunkoder ur riksdagsvalstabellen.")
    q = [
        {"code": "Region", "selection": {"filter": "item", "values": koder}},
        {"code": "Partimm", "selection": {"filter": "item", "values": SCB_PARTIKODER}},
        {"code": "ContentsCode", "selection": {"filter": "item", "values": ["ME0104B6"]}},
        {"code": "Tid", "selection": {"filter": "item", "values": ar}},
    ]
    data = _post("ME0104/ME0104C/ME0104T3", q, f"riksdagsval_kommun_{'_'.join(ar)}", tvinga)
    df = _till_dataframe(data, ["omrade", "parti", "ar"])
    df["parti"] = df["parti"].map(SCB_PARTI)
    return _andelar(df.dropna(subset=["parti"]))


def _beslutade_storlekar(niva: str = "kommun") -> dict[str, int]:
    """Fullmäktigestorlekar som gäller i valet 2026, enligt Valmyndigheten.

    Varje kommun beslutar själv hur många ledamöter fullmäktige ska ha, och
    beslutet ska fattas före mars månad valåret. Trettiotvå kommuner ändrade
    sin storlek inför 2026: Filipstad minskade från 37 till 25 och Tyresö ökade
    från 51 till 61. SCB publicerar storlekarna först efter valet, så siffrorna
    är hämtade ur Valmyndighetens fil över fasta valkretsmandat.
    """
    fil = ROT / "data" / "fullmaktigestorlek_2026.csv"
    if not fil.exists():
        return {}
    ut = {}
    with open(fil, encoding="utf-8") as f:
        for rad in _csv.DictReader(f):
            if (rad.get("niva") or "").strip() != niva:
                continue
            kod = (rad.get("omrade_kod") or "").strip()
            try:
                ut[kod] = int(rad["mandat_2026"])
            except (KeyError, TypeError, ValueError):
                continue
    return ut


def hamta_fullmaktigestorlek(ar: str = "2022", tvinga: bool = False) -> dict[str, int]:
    """Antal mandat i varje kommunfullmäktige.

    För valet 2026 används Valmyndighetens beslutade storlekar. Saknas en
    kommun där faller den tillbaka på storleken i förra valet, summerad ur
    SCB:s valresultat.
    """
    beslutade = _beslutade_storlekar("kommun")
    koder = _kommunkoder("ME0104/ME0104A/ME0104T1")
    q = [
        {"code": "Region", "selection": {"filter": "item", "values": koder}},
        {"code": "Parti", "selection": {"filter": "item", "values": SCB_PARTIKODER}},
        {"code": "ContentsCode", "selection": {"filter": "item", "values": ["ME0104C1"]}},
        {"code": "Tid", "selection": {"filter": "item", "values": [ar]}},
    ]
    data = _post("ME0104/ME0104A/Kfmandat", q, f"kf_mandat_{ar}", tvinga)
    df = _till_dataframe(data, ["omrade", "parti", "ar"])
    if df.empty:
        return dict(beslutade)
    summa = df.groupby("omrade")["varde"].sum()
    ur_scb = {k: int(v) for k, v in summa.items() if v > 0}
    ur_scb.update(beslutade)
    return ur_scb


def hamta_regionmandat(ar: str = "2022", tvinga: bool = False) -> dict[str, int]:
    """Antal mandat i varje regionfullmäktige, summerat från valresultatet."""
    q = [
        {"code": "Region", "selection": {"filter": "item", "values": list(REGIONER)}},
        {"code": "Parti", "selection": {"filter": "item", "values": SCB_PARTIKODER}},
        {"code": "ContentsCode", "selection": {"filter": "item", "values": ["ME0104C2"]}},
        {"code": "Tid", "selection": {"filter": "item", "values": [ar]}},
    ]
    try:
        data = _post("ME0104/ME0104B/Ltmandat", q, f"lt_mandat_{ar}", tvinga)
    except requests.HTTPError:
        return {}
    df = _till_dataframe(data, ["omrade", "parti", "ar"])
    if df.empty:
        return {}
    summa = df.groupby("omrade")["varde"].sum()
    return {k: int(v) for k, v in summa.items() if v > 0}


def hamta_regionval_mandat(ar: str = "2022",
                           tvinga: bool = False) -> dict[str, dict[str, int]]:
    """Mandat per parti och region i regionvalet, som jämförelsepunkt."""
    q = [
        {"code": "Region", "selection": {"filter": "item", "values": list(REGIONER)}},
        {"code": "Parti", "selection": {"filter": "item", "values": SCB_PARTIKODER}},
        {"code": "ContentsCode", "selection": {"filter": "item", "values": ["ME0104C2"]}},
        {"code": "Tid", "selection": {"filter": "item", "values": [ar]}},
    ]
    data = _post("ME0104/ME0104B/Ltmandat", q, f"lt_mandat_parti_{ar}", tvinga)
    df = _till_dataframe(data, ["omrade", "parti", "ar"])
    if df.empty:
        return {}
    df["parti"] = df["parti"].map(SCB_PARTI)
    df = df.dropna(subset=["parti"])
    ut: dict[str, dict[str, int]] = {}
    for (omrade, parti), grupp in df.groupby(["omrade", "parti"]):
        ut.setdefault(omrade, {})[parti] = int(grupp["varde"].sum())
    return ut


def hamta_kommunval_mandat(ar: str = "2022",
                           tvinga: bool = False) -> dict[str, dict[str, int]]:
    """Mandat per parti och kommun i kommunvalet, som jämförelsepunkt."""
    koder = _kommunkoder("ME0104/ME0104A/ME0104T1")
    q = [
        {"code": "Region", "selection": {"filter": "item", "values": koder}},
        {"code": "Parti", "selection": {"filter": "item", "values": SCB_PARTIKODER}},
        {"code": "ContentsCode", "selection": {"filter": "item", "values": ["ME0104C1"]}},
        {"code": "Tid", "selection": {"filter": "item", "values": [ar]}},
    ]
    data = _post("ME0104/ME0104A/Kfmandat", q, f"kf_mandat_parti_{ar}", tvinga)
    df = _till_dataframe(data, ["omrade", "parti", "ar"])
    if df.empty:
        return {}
    df["parti"] = df["parti"].map(SCB_PARTI)
    df = df.dropna(subset=["parti"])
    ut: dict[str, dict[str, int]] = {}
    for (omrade, parti), grupp in df.groupby(["omrade", "parti"]):
        ut.setdefault(omrade, {})[parti] = int(grupp["varde"].sum())
    return ut


if __name__ == "__main__":
    rg = hamta_regionval()
    rd = hamta_riksdagsval_per_region()
    print(f"Regionval: {len(rg)} region-år, riksdagsval: {len(rd)} region-år")
    gemensam = rg.index.intersection(rd.index)
    diff = (rg.loc[gemensam] - rd.loc[gemensam])
    print("\nDifferens regionval minus riksdagsval, medel per parti:")
    print(diff.mean().round(2).to_string())
    psu = hamta_psu_landsdel()
    print(f"\nPSU per landsdel: {len(psu)} rader")
