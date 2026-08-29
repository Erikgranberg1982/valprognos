"""Kommunvalsprognos, byggd på samma princip som regionmodellen.

Kommunvalen skiljer sig från regionvalen på tre sätt som modellen måste hantera:

  1. Lokala partier är betydligt starkare. I flera kommuner är de största
     partiet, och i enstaka fall styr de ensamma. De hålls därför konstanta på
     sin nivå från förra valet, precis som i regionmodellen men med större vikt.
  2. Det finns ingen småpartispärr i kommunvalet. I stället krävs i praktiken
     att partiet når en mandatkvot, vilket ger en effektiv spärr som beror på
     fullmäktiges storlek.
  3. Fullmäktiges storlek varierar från 21 till 101 ledamöter efter kommunens
     invånarantal.

Prognosen är med nödvändighet osäkrare än riksdagsprognosen: det finns inga
opinionsmätningar per kommun, och lokala förhållanden som en avhoppad
kommunalråd eller en lokal stridsfråga kan flytta stora andelar väljare.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config as cfg
import lokala_koalitioner
import lokala_partier
import regionmodell
import scb_data

# Fallvärde när fullmäktiges faktiska storlek inte kan hämtas. De flesta
# kommuner ligger på 31 till 41 ledamöter.
STANDARD_FULLMAKTIGE = 41

# Effektiv spärr för ÖVRIGA, se fordela_kommunmandat. Lägre än i regionvalet
# eftersom kommunfullmäktige är mindre och mandatkvoten därmed lägre.
OVRIGA_EFFEKTIV_SPARR = 3.5

# Småpartispärren i kommunvalet beror på valkretsindelningen: tre procent i en
# kommun med flera valkretsar, två procent i en kommun med en enda. Sjutton av
# 290 kommuner är valkretsindelade. Källa: vallagen och Valmyndigheten.
#
# Regeln är tydligt synlig i utfallet 2022. Av partierna som landade mellan två
# och tre procent fick 154 av 158 mandat i enkretskommuner, men noll av åtta i
# de valkretsindelade.
SPARR_EN_VALKRETS = 2.0
SPARR_FLERA_VALKRETSAR = 3.0


def _valkretsindelning() -> dict[str, int]:
    """Antal valkretsar per kommun, från data/kommun_valkretsar.csv."""
    from pathlib import Path
    fil = Path(__file__).resolve().parent.parent / "data" / "kommun_valkretsar.csv"
    if not fil.exists():
        return {}
    try:
        tabell = pd.read_csv(fil, dtype={"kommunkod": str})
    except Exception:
        return {}
    return {str(r["kommunkod"]).zfill(4): int(r["antal_valkretsar"])
            for _, r in tabell.iterrows()}


VALKRETSAR = _valkretsindelning()


def sparr_for_kommun(kommunkod: str) -> float:
    """Småpartispärren i procent för en kommun."""
    antal = VALKRETSAR.get(str(kommunkod).zfill(4), 1)
    return (SPARR_FLERA_VALKRETSAR if antal > 1 else SPARR_EN_VALKRETS)

# SCB:s partisympatiundersökning används inte på kommunnivå. Undersökningen är
# indelad i tio landsdelar, vilket är för grovt för en enskild kommun:
# Västsverige rymmer både Göteborg och Öckerö, som röstar helt olika. Ett
# backtest mot kommunvalet 2022 visar att den försämrar prognosen, från 2,40
# till 2,50 procentenheters medelabsolutfel med vikten 0,25. Värst blir det för
# partier som varierar kraftigt inom en landsdel: SD, V och KD.
#
# Regionmodellen använder den däremot, se regionmodell.PSU_VIKT, eftersom en
# region ligger närmare en landsdel i storlek.
PSU_VIKT_KOMMUN = float(cfg._P.get("psu_vikt_kommun", 0.0))


def _lansdel_for_kommun(kommunkod: str) -> str | None:
    """Kommunkodens två första siffror är länskoden.

    Länet översätts till den landsdel som SCB:s partisympatiundersökning
    använder, så att kommunprognosen kan dra nytta av samma regionala signal
    som regionprognosen.
    """
    lan = kommunkod[:2]
    regionkod = {"01": "01L", "03": "03L", "04": "04L", "05": "05L", "06": "06L",
                 "07": "07L", "08": "08L", "09": None, "10": "10L", "12": "12L",
                 "13": "13L", "14": "14L", "17": "17L", "18": "18L", "19": "19L",
                 "20": "20LG", "21": "21L", "22": "22L", "23": "23L", "24": "24L",
                 "25": "25L"}.get(lan)
    if regionkod is None:
        return None
    for landsdel, regioner in scb_data.LANDSDEL_TILL_REGION.items():
        if regionkod in regioner:
            return landsdel
    return None


def _blanda_in_psu(profil: pd.DataFrame) -> pd.DataFrame:
    """Väger in SCB:s partisympati per landsdel i kommunens profil.

    Avstängd som standard, se PSU_VIKT_KOMMUN. Funktionen finns kvar för den
    som vill experimentera med en låg vikt via psu_vikt_kommun i
    data/modellparametrar.csv.
    """
    try:
        psu = scb_data.hamta_psu_landsdel().reset_index()
    except Exception:
        return profil
    if psu.empty:
        return profil

    senaste = sorted(psu["tid"].unique())[-1]
    aktuell = (psu[psu["tid"] == senaste].drop(columns=["tid"])
               .set_index("landsdel").apply(pd.to_numeric, errors="coerce"))
    if "Z01" not in aktuell.index:
        return profil
    psu_profil = aktuell.drop(index="Z01").div(aktuell.loc["Z01"], axis=1)

    vikt = PSU_VIKT_KOMMUN
    ut = profil.copy()
    landsdelar = {k: _lansdel_for_kommun(str(k)) for k in ut.index}

    for parti in ut.columns:
        if parti not in psu_profil.columns:
            continue
        faktorer = []
        for kommun in ut.index:
            landsdel = landsdelar.get(kommun)
            varde = (psu_profil.at[landsdel, parti]
                     if landsdel in psu_profil.index else np.nan)
            faktorer.append(varde if np.isfinite(varde) else np.nan)
        psu_serie = pd.Series(faktorer, index=ut.index)
        ut[parti] = np.where(psu_serie.notna(),
                             (1.0 - vikt) * ut[parti] + vikt * psu_serie.fillna(1.0),
                             ut[parti])
    return ut


def skatta_differenser(vikt_2022: float = 0.7) -> pd.DataFrame:
    """Differensen mellan kommunval och riksdagsval per kommun och parti."""
    kommunval = scb_data.hamta_kommunval()
    riksdagsval = scb_data.hamta_riksdagsval_per_kommun()

    gemensam = kommunval.index.intersection(riksdagsval.index)
    if len(gemensam) == 0:
        raise RuntimeError("Inga gemensamma kommun-år mellan kommun- och riksdagsval.")

    diff = (kommunval.loc[gemensam] - riksdagsval.loc[gemensam]).reset_index()
    vikter = {"2022": vikt_2022, "2018": 1.0 - vikt_2022}
    diff["vikt"] = diff["ar"].map(vikter).fillna(0.0)

    partikolumner = [k for k in diff.columns if k not in ("omrade", "ar", "vikt")]
    rader = []
    for omrade, grupp in diff.groupby("omrade"):
        if grupp["vikt"].sum() <= 0:
            continue
        post = {"omrade": omrade}
        for parti in partikolumner:
            varden = grupp[parti]
            giltiga = varden.notna()
            post[parti] = (float(np.average(varden[giltiga], weights=grupp["vikt"][giltiga]))
                           if giltiga.any() else 0.0)
        rader.append(post)
    return pd.DataFrame(rader).set_index("omrade")


def prognos_per_kommun(riksprognos: pd.Series,
                       kommuner: list[str] | None = None) -> pd.DataFrame:
    """Bygger kommunvalsprognos per kommun.

    Samma princip som regionmodellen: kommunens eget resultat i förra
    kommunvalet skalas med hur mycket partiet gått upp eller ner nationellt.
    Se regionmodell.prognos_per_region för varför metoden valdes.

    Kommunprognosen är osäkrare än regionprognosen. Kommunerna är mindre, och
    lokala förhållanden som ett avhopp eller en ny lista väger tyngre där.
    """
    forra_lokalt = scb_data.hamta_kommunval(ar=[regionmodell.FORRA_VALET])
    forra_lokalt = (forra_lokalt.reset_index()
                    .set_index("omrade").drop(columns=["ar"]))
    trend = regionmodell._rikstrend(riksprognos)
    namn = scb_data.kommunnamn()

    urval = kommuner or list(forra_lokalt.index)

    rader = []
    for omrade in urval:
        if omrade not in forra_lokalt.index:
            continue

        post = {"omrade": omrade, "namn": namn.get(omrade, str(omrade))}
        for parti in cfg.PARTIER:
            if parti not in forra_lokalt.columns:
                continue
            bas = forra_lokalt.at[omrade, parti]
            if not np.isfinite(bas):
                bas = 0.05
            post[parti] = max(0.05, float(bas) * trend.get(parti, 1.0))

        ovriga = np.nan
        if "ÖVRIGA" in forra_lokalt.columns:
            ovriga = forra_lokalt.at[omrade, "ÖVRIGA"]
        post["ÖVRIGA"] = float(ovriga) if np.isfinite(ovriga) else 5.0
        rader.append(post)

    if not rader:
        raise RuntimeError("Ingen kommun kunde prognosticeras.")

    df = pd.DataFrame(rader).set_index("omrade")
    partikolumner = [p for p in cfg.PARTIER if p in df.columns] + ["ÖVRIGA"]
    df[partikolumner] = df[partikolumner].div(df[partikolumner].sum(axis=1), axis=0) * 100
    return _dela_ut_lokala_partier(df, "kommun", partikolumner)


def _dela_ut_lokala_partier(df: pd.DataFrame, niva: str,
                            partikolumner: list[str]) -> pd.DataFrame:
    """Väger in lokala mätningar där sådana finns.

    Mätningen vägs samman med modellens skattning partivis och normaliseras,
    på samma sätt som partisympatiundersökningen i regionmodellen. Ett lokalt
    parti som ingår i mätningen bryts samtidigt ut ur ÖVRIGA och redovisas med
    namn.

    Bara fullständiga mätningar används, se lokala_partier.matning_for_omrade.
    """
    ut = df.copy()
    ut["lokalt_parti"] = None
    ut["lokalt_stod"] = np.nan
    ut["lokalt_matt"] = False
    ut["lokalt_vikt"] = np.nan
    ut["lokalt_kalla"] = None

    for omrade in ut.index:
        aktuellt = {k: float(ut.at[omrade, k]) for k in partikolumner
                    if k in ut.columns}
        justerat, matning = lokala_partier.blanda_in_matning(
            aktuellt, niva, str(omrade))
        if matning is None or not matning["anvands"]:
            continue

        for parti in partikolumner:
            if parti in justerat:
                ut.at[omrade, parti] = justerat[parti]

        lokalt = matning["lokalt_parti"]
        if lokalt and lokalt in justerat:
            ut.at[omrade, "lokalt_parti"] = lokalt
            ut.at[omrade, "lokalt_stod"] = justerat[lokalt]
            ut.at[omrade, "lokalt_matt"] = True
            ut.at[omrade, "lokalt_vikt"] = matning["vikt"]
            ut.at[omrade, "lokalt_kalla"] = matning["kalla"]

    return ut



def fordela_kommunmandat(stod: dict[str, float], platser: int,
                         sparr: float = SPARR_EN_VALKRETS) -> dict[str, int]:
    """Fördelar fullmäktiges mandat med jämkade uddatalsmetoden.

    Kommunvalet saknar procentspärr. Kommuner som inte är valkretsindelade
    tillämpar i stället en spärr på två procent.
    """
    # ÖVRIGA rymmer flera lokala partier som var för sig måste nå en mandatkvot.
    # I kommunvalet är den kvoten låg, eftersom fullmäktige är litet, men ett
    # samlat stöd på några få procent betyder ändå sällan mandat för alla.
    kvalificerade = {}
    for parti, varde in stod.items():
        grans = OVRIGA_EFFEKTIV_SPARR if parti == "ÖVRIGA" else sparr
        if varde >= grans:
            kvalificerade[parti] = varde
    if not kvalificerade:
        kvalificerade = {p: v for p, v in stod.items() if v > 0}
    if not kvalificerade:
        return {p: 0 for p in stod}

    mandat = {p: 0 for p in stod}
    divisorer = {p: 1.2 for p in kvalificerade}
    for _ in range(platser):
        vinnare = max(kvalificerade, key=lambda p: kvalificerade[p] / divisorer[p])
        mandat[vinnare] += 1
        divisorer[vinnare] = 2 * mandat[vinnare] + 1
    return mandat


def _valkretsresultat() -> pd.DataFrame:
    """Valkretsarnas resultat 2022, från data/kommun_valkretsresultat.csv."""
    from pathlib import Path
    fil = Path(__file__).resolve().parent.parent / "data" / "kommun_valkretsresultat.csv"
    if not fil.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(fil, dtype={"kommunkod": str})
    except Exception:
        return pd.DataFrame()


def prognos_per_valkrets(riksprognos: pd.Series) -> pd.DataFrame:
    """Prognos per valkrets i de kommuner som är valkretsindelade.

    Samma metod som för kommunerna: valkretsens eget resultat 2022 skalat med
    rikstrenden. Skillnaderna mellan valkretsar inom en kommun är ofta stora,
    i Stockholm ligger Moderaterna mellan elva och trettio procent beroende på
    valkrets, så en prognos per valkrets säger något som kommunsiffran döljer.

    Mandaten fördelas däremot inte här. Nio tiondelar av mandaten fördelas visserligen
    inom valkretsarna, men utjämningsmandaten gör slutresultatet proportionellt
    över hela kommunen, så mandatfördelningen görs på kommunnivå.
    """
    resultat = _valkretsresultat()
    if resultat.empty:
        return pd.DataFrame()

    trend = regionmodell._rikstrend(riksprognos)

    rader = []
    for _, rad in resultat.iterrows():
        post = {
            "kommunkod": str(rad["kommunkod"]).zfill(4),
            "kommun": rad["kommun"],
            "valkretskod": rad["valkretskod"],
            "valkretsnamn": rad["valkretsnamn"],
        }
        for parti in cfg.PARTIER:
            bas = rad.get(parti)
            if bas is None or not np.isfinite(bas):
                post[parti] = np.nan
                post[f"forra_{parti}"] = np.nan
                continue
            post[parti] = max(0.05, float(bas) * trend.get(parti, 1.0))
            post[f"forra_{parti}"] = float(bas)

        # Normalisera riksdagspartierna till samma andel som 2022, så att
        # övriga partier behåller sitt utrymme i valkretsen.
        gamla = sum(post[f"forra_{p}"] for p in cfg.PARTIER
                    if np.isfinite(post.get(f"forra_{p}", np.nan)))
        nya = sum(post[p] for p in cfg.PARTIER
                  if np.isfinite(post.get(p, np.nan)))
        if nya > 0 and gamla > 0:
            for parti in cfg.PARTIER:
                if np.isfinite(post.get(parti, np.nan)):
                    post[parti] = post[parti] / nya * gamla
                    post[f"diff_{parti}"] = post[parti] - post[f"forra_{parti}"]
        rader.append(post)

    return pd.DataFrame(rader)


def sammanfatta(prognos: pd.DataFrame, storlekar: dict[str, int] | None = None) -> pd.DataFrame:
    """Fördelar mandat och sammanfattar styret per kommun.

    Fullmäktiges storlek läses ur SCB:s valresultat, eftersom den beslutas av
    varje kommun och varierar från 21 till 101 ledamöter. Utfallet 2022 tas med
    som jämförelsepunkt.
    """
    partikolumner = [p for p in cfg.PARTIER if p in prognos.columns] + ["ÖVRIGA"]
    if storlekar is None:
        try:
            storlekar = scb_data.hamta_fullmaktigestorlek()
        except Exception:
            storlekar = {}
    storlekar = storlekar or {}

    try:
        forra_stod = scb_data.hamta_kommunval(ar=["2022"])
        forra_stod = forra_stod.reset_index().set_index("omrade").drop(columns=["ar"])
    except Exception:
        forra_stod = pd.DataFrame()
    try:
        forra_mandat = scb_data.hamta_kommunval_mandat("2022")
    except Exception:
        forra_mandat = {}

    rader = []
    for omrade, rad in prognos.iterrows():
        platser = storlekar.get(omrade, STANDARD_FULLMAKTIGE)
        stod = {p: float(rad[p]) for p in partikolumner}
        # Ett namngivet lokalt parti prövas mot spärren som eget parti.
        lokalt = rad.get("lokalt_parti")
        if lokalt and np.isfinite(rad.get("lokalt_stod", np.nan)):
            stod[str(lokalt)] = float(rad["lokalt_stod"])
        mandat = fordela_kommunmandat(stod, platser, sparr_for_kommun(omrade))
        # Mandat per parti inklusive ett namngivet lokalt parti, för lägesanalysen.
        stod_mandat = {k: int(v) for k, v in mandat.items()}

        post = {"omrade": omrade, "namn": rad["namn"], "mandat_totalt": platser}
        post.update({f"stod_{p}": stod[p] for p in partikolumner})
        post.update({f"mandat_{p}": mandat[p] for p in partikolumner})
        # Det lokala partiets stöd och mandat får egna fält, så att det kan
        # redovisas med namn utan att blandas in i ÖVRIGA.
        post["lokalt_parti"] = lokalt if lokalt else None
        post["lokalt_stod"] = (float(rad["lokalt_stod"]) if lokalt else None)
        post["lokalt_mandat"] = (mandat.get(str(lokalt), 0) if lokalt else None)
        post["lokalt_matt"] = bool(rad.get("lokalt_matt", False)) if lokalt else False
        post["lokalt_kalla"] = rad.get("lokalt_kalla") if lokalt else None

        vanster = sum(mandat[p] for p in cfg.BLOCK["vanster"] if p in mandat)
        hoger = sum(mandat[p] for p in cfg.BLOCK["hoger"] if p in mandat)
        post["mandat_vanster"] = vanster
        post["mandat_hoger"] = hoger
        post["mandat_ovriga"] = (mandat.get("ÖVRIGA", 0)
                                 + (mandat.get(str(lokalt), 0) if lokalt else 0))
        post["majoritet"] = platser // 2 + 1
        post["vanster_majoritet"] = vanster >= post["majoritet"]
        post["hoger_majoritet"] = hoger >= post["majoritet"]
        post["vagmastare"] = not (post["vanster_majoritet"] or post["hoger_majoritet"])

        # Mandatläget beskrivs utan att gissa vilket styre som bildas, eftersom
        # C lokalt oftare styr med de borgerliga än med vänstern.
        lage_mandat = dict(stod_mandat)
        lage = lokala_koalitioner.beskriv_lage(lage_mandat, platser)
        post["lage"] = lage["lage"]
        post["lage_text"] = lage["text"]
        post["lage_beskrivning"] = lage["beskrivning"]
        post["mandat_vanster_ren"] = lage["vanster"]
        post["mandat_borgerliga"] = lage["borgerliga"]
        post["mandat_c"] = lage["c"]
        post["mandat_sd_ensam"] = lage["sd"]
        post["mandat_utanfor"] = lage["ovriga"]

        # Vilka av de vanligaste lokala koalitionerna når majoritet här. Vänster
        # mot höger är för grovt lokalt: blocköverskridande styren är det
        # enskilt vanligaste mönstret i kommunerna.
        for koalition in lokala_koalitioner.utfall_for_omrade(mandat, platser):
            post[f"koal_{koalition['id']}"] = koalition["mandat"]
            post[f"koal_{koalition['id']}_majoritet"] = koalition["har_majoritet"]

        gamla_mandat = forra_mandat.get(omrade, {})
        for parti in partikolumner:
            tidigare = np.nan
            if (not forra_stod.empty and omrade in forra_stod.index
                    and parti in forra_stod.columns):
                tidigare = forra_stod.at[omrade, parti]
            post[f"forra_{parti}"] = float(tidigare) if np.isfinite(tidigare) else None
            post[f"diff_{parti}"] = (float(stod[parti] - tidigare)
                                     if np.isfinite(tidigare) else None)
            gammalt = gamla_mandat.get(parti)
            post[f"forra_mandat_{parti}"] = gammalt
            post[f"mandatdiff_{parti}"] = (mandat[parti] - gammalt
                                           if gammalt is not None else None)

        if gamla_mandat:
            gv = sum(gamla_mandat.get(p, 0) for p in cfg.BLOCK["vanster"])
            gh = sum(gamla_mandat.get(p, 0) for p in cfg.BLOCK["hoger"])
            post["forra_vanster"] = gv
            post["forra_hoger"] = gh
            post["forra_ovriga"] = gamla_mandat.get("ÖVRIGA", 0)
            post["diff_vanster"] = vanster - gv
            post["diff_hoger"] = hoger - gh
            post["diff_ovriga"] = post["mandat_ovriga"] - gamla_mandat.get("ÖVRIGA", 0)

        rader.append(post)

    return pd.DataFrame(rader).set_index("omrade")
