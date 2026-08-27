"""Regionvalsprognos byggd på riksdagsprognosen plus historiska differenser.

Det finns inga publicerade opinionsmätningar för regionvalen, så modellen
härleder regionvalsstödet i tre steg:

  1. Riksdagsprognosen ger utgångsläget nationellt.
  2. En regional profil skattas per region från riksdagsvalets utfall där,
     justerad med SCB:s partisympati per landsdel så att profilen följer hur
     opinionen faktiskt har rört sig sedan förra valet.
  3. Differensen mellan regionval och riksdagsval 2018 och 2022 läggs på. Den
     fångar att väljare röstar annorlunda i regionvalet: SD tappar omkring sex
     procentenheter och lokala partier vinner motsvarande.

Lokala partier redovisas av SCB samlat som ÖVRIGA och kan inte prognosticeras
individuellt. De hålls därför på sin historiska nivå per region, vilket är den
ärligaste behandlingen när det saknas mätningar.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config as cfg
import lokala_partier
import scb_data

# Regionfullmäktige har inget lagstadgat mandattal; storleken beslutas av
# regionen själv utifrån antalet röstberättigade. Den läses därför ur SCB:s
# valresultat i stället för att antas, med ett fallvärde om hämtningen fallerar.
STANDARD_REGIONMANDAT = 71


def regionmandat() -> dict[str, int]:
    try:
        mandat = scb_data.hamta_regionmandat()
    except Exception:
        mandat = {}
    return mandat or {}

# Regionval har en spärr på tre procent, lägre än riksdagsvalets fyra.
REGION_SPARR = 0.03

# Hur mycket SCB:s regionala partisympati får väga mot den historiska profilen.
# Kalibrerat mot regionvalet 2022, se regional_profil.
PSU_VIKT = float(cfg._P.get("psu_vikt", 0.25))


# Valet som prognosen utgår från.
FORRA_VALET = "2022"

# ÖVRIGA är inte ett parti utan summan av flera lokala partier. Ett samlat stöd
# strax över spärren betyder oftast att inget enskilt parti klarar den. Tröskeln
# är kalibrerad mot regionvalet 2022, där den sänkte det totala mandatfelet för
# ÖVRIGA från 21 till 5 mandat över alla regioner.
OVRIGA_EFFEKTIV_SPARR = 5.0


def _rikstrend(riksprognos: pd.Series) -> dict[str, float]:
    """Kvoten mellan riksdagsprognosen och riksdagsvalet 2022, per parti.

    Kvoten uttrycker hur mycket ett parti vuxit eller krympt nationellt sedan
    förra valet, och används för att skala områdenas egna resultat.
    """
    ut = {}
    for parti in cfg.PARTIER:
        forra = cfg.VALRESULTAT_2022.get(parti)
        nu = riksprognos.get(parti)
        if forra and nu is not None and forra > 0:
            ut[parti] = float(nu) / float(forra)
        else:
            ut[parti] = 1.0
    return ut



def skatta_differenser(vikt_2022: float = 0.7) -> pd.DataFrame:
    """Skattar differensen mellan regionval och riksdagsval per region och parti.

    Båda valen 2018 och 2022 vägs in, med tyngdpunkt på det senaste eftersom
    partilandskapet ändras över tid. Regioner som saknar data i ett av åren
    faller tillbaka på det år som finns.
    """
    regionval = scb_data.hamta_regionval()
    riksdagsval = scb_data.hamta_riksdagsval_per_region()

    gemensam = regionval.index.intersection(riksdagsval.index)
    diff = (regionval.loc[gemensam] - riksdagsval.loc[gemensam]).reset_index()

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
            if not giltiga.any():
                post[parti] = 0.0
                continue
            post[parti] = float(np.average(varden[giltiga],
                                           weights=grupp["vikt"][giltiga]))
        rader.append(post)

    return pd.DataFrame(rader).set_index("omrade")


def regional_profil(anvand_psu: bool = True) -> pd.DataFrame:
    """Skattar hur varje region avviker från riket i riksdagsval.

    Profilen uttrycks som en multiplikator per parti: 1,3 betyder att partiet
    är 30 procent starkare i regionen än nationellt. Multiplikativ form väljs
    framför additiv eftersom den bevarar rimliga nivåer även för små partier.

    När SCB:s landsdelsdata används vägs den historiska profilen samman med den
    aktuella, så att profilen speglar var opinionen står nu och inte bara var
    den stod 2022.
    """
    riksdagsval = scb_data.hamta_riksdagsval_per_region(ar=["2022"])
    riksdagsval = riksdagsval.reset_index().set_index("omrade").drop(columns=["ar"])

    riket = riksdagsval.mean()  # Ovägt riksgenomsnitt som referens.
    historisk = riksdagsval.div(riket, axis=1)

    if not anvand_psu:
        return historisk

    try:
        psu = scb_data.hamta_psu_landsdel()
    except Exception:
        return historisk

    # Senaste mätmånaden, samt riket som referens. Kolumnen tid måste bort
    # innan divisionen, annars hamnar en textkolumn i beräkningen.
    psu = psu.reset_index()
    senaste = sorted(psu["tid"].unique())[-1]
    aktuell = (psu[psu["tid"] == senaste]
               .drop(columns=["tid"])
               .set_index("landsdel"))
    if "Z01" not in aktuell.index:
        return historisk
    aktuell = aktuell.apply(pd.to_numeric, errors="coerce")

    psu_riket = aktuell.loc["Z01"]
    psu_profil = aktuell.drop(index="Z01").div(psu_riket, axis=1)

    # Översätt landsdelsprofil till regioner. En region som täcks av flera
    # landsdelar får medelvärdet av dem.
    rader = {}
    for landsdel, regioner in scb_data.LANDSDEL_TILL_REGION.items():
        if landsdel not in psu_profil.index:
            continue
        for region in regioner:
            rader.setdefault(region, []).append(psu_profil.loc[landsdel])
    if not rader:
        return historisk

    psu_region = pd.DataFrame({r: pd.concat(v, axis=1).mean(axis=1)
                               for r, v in rader.items()}).T

    # Väg samman: den historiska profilen är finkornig men gammal, PSU är färsk
    # men indelad i tio grova landsdelar. Vikten är kalibrerad mot regionvalet
    # 2022: med 25 procent PSU faller felet från 1,66 till 1,53 procentenheter,
    # medan ren PSU är sämre än ingen PSU alls (1,95) eftersom landsdelarna är
    # för grova för att beskriva en enskild region.
    vikt = PSU_VIKT
    gemensamma_partier = [p for p in historisk.columns if p in psu_region.columns]
    ut = historisk.copy()
    for parti in gemensamma_partier:
        psu_varde = psu_region[parti].reindex(ut.index)
        ut[parti] = np.where(psu_varde.notna(),
                             (1.0 - vikt) * ut[parti] + vikt * psu_varde.fillna(1.0),
                             ut[parti])
    return ut


def prognos_per_region(riksprognos: pd.Series, anvand_psu: bool = True,
                       lokala_konstanta: bool = True) -> pd.DataFrame:
    """Bygger regionvalsprognos per region.

    Utgångspunkten är regionens eget resultat i förra regionvalet, skalat med
    hur mycket partiet gått upp eller ner nationellt sedan dess. Ett parti som
    fått 3,0 procent i regionen och sedan vuxit från 5,3 till 6,5 nationellt
    hamnar på 3,0 x 6,5/5,3, alltså 3,7 procent.

    Metoden valdes efter jämförelse mot regionvalet 2022. Ett tidigare upplägg
    skalade rikstrenden med regionens profil och adderade skillnaden mellan
    region- och riksdagsval. Det gav 1,49 procentenheters medelabsolutfel mot
    1,18 för den nuvarande, och kunde dessutom producera orimliga nivåer när
    profil och skillnad pekade åt samma håll: ett parti med tre gånger rikets
    stöd i en region blåstes upp så att radsumman överskred hundra procent och
    normaliseringen tryckte ner alla andra partier.

    Att utgå från det faktiska lokalvalsresultatet fångar dessutom automatiskt
    det som skillnadstermen försökte modellera, nämligen att väljare röstar
    annorlunda i lokalvalen.

    riksprognos är riksdagsprognosen i procent per parti.
    """
    forra_lokalt = scb_data.hamta_regionval(ar=[FORRA_VALET])
    forra_lokalt = (forra_lokalt.reset_index()
                    .set_index("omrade").drop(columns=["ar"]))
    trend = _rikstrend(riksprognos)

    rader = []
    for omrade in scb_data.REGIONER:
        if omrade not in forra_lokalt.index:
            continue

        post = {"omrade": omrade, "namn": scb_data.REGIONER[omrade]}
        for parti in cfg.PARTIER:
            if parti not in forra_lokalt.columns:
                continue
            bas = forra_lokalt.at[omrade, parti]
            if not np.isfinite(bas):
                bas = 0.05
            post[parti] = max(0.05, float(bas) * trend.get(parti, 1.0))

        # Lokala partier hålls på sin nivå från förra valet, eftersom SCB
        # redovisar dem samlat och de inte kan prognosticeras var för sig.
        ovriga = np.nan
        if lokala_konstanta and "ÖVRIGA" in forra_lokalt.columns:
            ovriga = forra_lokalt.at[omrade, "ÖVRIGA"]
        post["ÖVRIGA"] = float(ovriga) if np.isfinite(ovriga) else 3.0

        rader.append(post)

    df = pd.DataFrame(rader).set_index("omrade")
    partikolumner = [p for p in cfg.PARTIER if p in df.columns] + ["ÖVRIGA"]
    summa = df[partikolumner].sum(axis=1)
    df[partikolumner] = df[partikolumner].div(summa, axis=0) * 100
    return _dela_ut_lokala_partier(df, "region", partikolumner)


def _dela_ut_lokala_partier(df: pd.DataFrame, niva: str,
                            partikolumner: list[str]) -> pd.DataFrame:
    """Lyfter ut namngivna lokala partier ur ÖVRIGA där mätningar finns.

    ÖVRIGA är en samlingspost. För de områden där ett lokalt parti har en egen
    mätning redovisas partiet med namn, och resten blir kvar som ÖVRIGA. Ett
    namngivet parti prövas då mot spärren för sig, vilket ger ett rättvisare
    mandatutfall.

    Anropas efter normaliseringen. Om partiet mäts högre än ÖVRIGA-posten tas
    skillnaden proportionellt från de övriga partierna, eftersom ett växande
    lokalt parti vinner röster från riksdagspartierna och inte bara från andra
    lokala. Summan förblir hundra procent.
    """
    if "ÖVRIGA" not in df.columns:
        return df

    ut = df.copy()
    ut["lokalt_parti"] = None
    ut["lokalt_stod"] = np.nan
    ut["lokalt_matt"] = False
    ut["lokalt_kalla"] = None

    riksdagspartier = [k for k in partikolumner if k != "ÖVRIGA"]

    for omrade in ut.index:
        post = lokala_partier.for_omrade(niva, str(omrade))
        if not post:
            continue

        ovriga = float(ut.at[omrade, "ÖVRIGA"])
        eget, rest = lokala_partier.dela_upp_ovriga(ovriga, post["stod"])

        # Det parti tar utöver den gamla ÖVRIGA-posten måste komma någonstans.
        overskott = max(0.0, eget - ovriga)
        if overskott > 0:
            bas = sum(float(ut.at[omrade, k]) for k in riksdagspartier)
            if bas > overskott:
                for k in riksdagspartier:
                    andel = float(ut.at[omrade, k]) / bas
                    ut.at[omrade, k] = float(ut.at[omrade, k]) - overskott * andel
            else:
                # Orimligt stort överskott; behåll posten oförändrad.
                continue

        ut.at[omrade, "lokalt_parti"] = post["parti"]
        ut.at[omrade, "lokalt_stod"] = eget
        ut.at[omrade, "lokalt_matt"] = post["matt"]
        ut.at[omrade, "lokalt_kalla"] = post.get("kalla")
        ut.at[omrade, "ÖVRIGA"] = rest

    return ut



def fordela_regionmandat(stod: dict[str, float], platser: int) -> dict[str, int]:
    """Fördelar regionfullmäktiges mandat med jämkade uddatalsmetoden.

    Regionval har tre procents spärr i stället för riksdagsvalets fyra. För
    ÖVRIGA används en högre effektiv spärr, eftersom posten rymmer flera
    partier som var för sig måste klara spärren.
    """
    kvalificerade = {}
    for parti, varde in stod.items():
        grans = (OVRIGA_EFFEKTIV_SPARR if parti == "ÖVRIGA"
                 else REGION_SPARR * 100)
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


def _forra_valet() -> tuple[pd.DataFrame, dict[str, dict[str, int]]]:
    """Regionvalets utfall 2022 i procent och mandat, som jämförelsepunkt."""
    try:
        stod = scb_data.hamta_regionval(ar=["2022"])
        stod = stod.reset_index().set_index("omrade").drop(columns=["ar"])
    except Exception:
        stod = pd.DataFrame()

    mandat: dict[str, dict[str, int]] = {}
    try:
        mandat = scb_data.hamta_regionval_mandat("2022")
    except Exception:
        pass
    return stod, mandat


def sammanfatta(prognos: pd.DataFrame) -> pd.DataFrame:
    """Lägger till mandatfördelning, blocksummor och jämförelse med 2022."""
    partikolumner = [p for p in cfg.PARTIER if p in prognos.columns] + ["ÖVRIGA"]
    mandattal = regionmandat()
    forra_stod, forra_mandat = _forra_valet()

    rader = []
    for omrade, rad in prognos.iterrows():
        platser = mandattal.get(omrade, STANDARD_REGIONMANDAT)
        stod = {p: float(rad[p]) for p in partikolumner}
        # Ett namngivet lokalt parti prövas mot spärren som eget parti.
        lokalt = rad.get("lokalt_parti")
        if lokalt and np.isfinite(rad.get("lokalt_stod", np.nan)):
            stod[str(lokalt)] = float(rad["lokalt_stod"])
        mandat = fordela_regionmandat(stod, platser)

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
        # Vem som styr avgörs inte av blocken enbart: lokala partier kan vara
        # vågmästare, vilket är vanligt i regionerna.
        post["vanster_majoritet"] = vanster >= post["majoritet"]
        post["hoger_majoritet"] = hoger >= post["majoritet"]
        post["vagmastare"] = not (post["vanster_majoritet"] or post["hoger_majoritet"])

        # Jämförelse med förra valet, per parti och för blocken.
        gamla_mandat = forra_mandat.get(omrade, {})
        for parti in partikolumner:
            tidigare = np.nan
            if (not forra_stod.empty and omrade in forra_stod.index
                    and parti in forra_stod.columns):
                tidigare = forra_stod.at[omrade, parti]
            post[f"forra_{parti}"] = (float(tidigare) if np.isfinite(tidigare)
                                      else None)
            post[f"diff_{parti}"] = (float(stod[parti] - tidigare)
                                     if np.isfinite(tidigare) else None)
            gammalt = gamla_mandat.get(parti)
            post[f"forra_mandat_{parti}"] = gammalt
            post[f"mandatdiff_{parti}"] = (mandat[parti] - gammalt
                                           if gammalt is not None else None)

        if gamla_mandat:
            gv = sum(gamla_mandat.get(p, 0) for p in cfg.BLOCK["vanster"])
            gh = sum(gamla_mandat.get(p, 0) for p in cfg.BLOCK["hoger"])
            go = gamla_mandat.get("ÖVRIGA", 0)
            post["forra_vanster"] = gv
            post["forra_hoger"] = gh
            post["forra_ovriga"] = go
            post["diff_vanster"] = vanster - gv
            post["diff_hoger"] = hoger - gh
            post["diff_ovriga"] = post["mandat_ovriga"] - go

        rader.append(post)

    return pd.DataFrame(rader).set_index("omrade")


if __name__ == "__main__":
    import prognos as huvudprognos
    from datetime import date

    df = huvudprognos.las_matningar(huvudprognos.ROT / "data" / "matningar.csv")
    referens = df["datum"].max().date()
    res = huvudprognos.kor_prognos(df, referens, date.fromisoformat(cfg.VALDAG))

    reg = prognos_per_region(res["snitt"])
    sam = sammanfatta(reg)

    print(f"Regioner: {len(sam)}")
    print("\nStöd per region, procent:")
    kol = [f"stod_{p}" for p in cfg.PARTIER] + ["stod_ÖVRIGA"]
    visa = sam[["namn"] + kol].copy()
    visa.columns = ["Region"] + cfg.PARTIER + ["ÖVR"]
    print(visa.round(1).to_string(index=False))

    print("\nStyre:")
    for _, r in sam.iterrows():
        styre = ("vänster" if r["vanster_majoritet"]
                 else "höger" if r["hoger_majoritet"] else "vågmästarläge")
        print(f"  {r['namn']:24s} {int(r['mandat_vanster']):3d}-{int(r['mandat_hoger']):3d} "
              f"(+{int(r['mandat_ovriga'])} övr) av {int(r['mandat_totalt'])}  {styre}")
