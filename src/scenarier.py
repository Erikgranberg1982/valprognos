"""Scenarier för riksdagsvalet: tänkta utfall och vad de gör med mandaten.

Ett scenario är inte en prognos. Det är en fråga: om det här händer, hur ser
riksdagen ut då? Modellens egen prognos säger vad som är troligt; scenarierna
säger vad som skulle följa av något som ännu inte är det.

Varje scenario definierar en förflyttning av väljarstöd och räknar om mandat
och koalitioner med samma metod som huvudprognosen.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from pathlib import Path

import pandas as pd

import config as cfg
import modell

ROT = Path(__file__).resolve().parent.parent


# Riksdagens 349 mandat fördelas i 29 valkretsar. Örebro län har tolv, vilket
# behövs för scenariot om ett lokalt parti som tar sig in via valkretsspärren.
VALKRETSMANDAT = {"Örebro län": 12}


# Institut med tät och jämn publicering, som gör en trendlinje meningsfull.
TRENDINSTITUT = ["Demoskop", "Novus"]
TRENDSTART = "2026-06-01"

# Tidigare riksdagsval med mätningar under valrörelsen, för scenarierna om
# att valspurten upprepar sig. Wikipedias sidor för 2010 och 2014 har en
# annan tabellstruktur som skraparen inte tolkar, så underlaget är två val.
TIDIGARE_VAL = {
    2018: {
        "valdag": date(2018, 9, 9),
        "fil": "matningar_2018.csv",
        "utfall": {"V": 8.00, "S": 28.26, "MP": 4.41, "C": 8.61,
                   "L": 5.49, "M": 19.84, "KD": 6.32, "SD": 17.53},
    },
    2022: {
        "valdag": date(2022, 9, 11),
        "fil": "matningar_2022.csv",
        "utfall": dict(cfg.VALRESULTAT_2022),
    },
}


@dataclass
class Scenario:
    id: str
    namn: str
    fraga: str
    beskrivning: str
    # Förflyttning i procentenheter per parti. Summan bör vara noll: röster
    # flyttar mellan partier, de uppstår inte.
    forflyttning: dict[str, float] = field(default_factory=dict)
    # Ett parti utanför de åtta som tar mandat via valkretsspärren.
    valkretsparti: dict | None = None
    forbehall: str = ""
    # Räknas ur mätdata i stället för att anges för hand.
    trend: bool = False
    trenddata: dict = field(default_factory=dict)
    valspurt: list[int] | None = None
    spurtdata: dict = field(default_factory=dict)


def spurt_for_val(ar: int, dagar_kvar: int) -> dict:
    """Hur mycket varje parti flyttade sig de sista dagarna i ett tidigare val.

    Jämför sammanvägningen lika många dagar före valdagen med det faktiska
    utfallet. Skillnaden är valspurten.
    """
    import prognos as _prognos

    val = TIDIGARE_VAL[ar]
    fil = ROT / "data" / val["fil"]
    if not fil.exists():
        raise FileNotFoundError(f"data/{val['fil']} saknas.")

    df = _prognos.las_matningar(fil)
    ref = val["valdag"] - timedelta(days=dagar_kvar)
    hist = df[df["datum"] <= pd.Timestamp(ref)]
    if len(hist) < 15:
        raise ValueError(
            f"För få mätningar från {ar} fram till {ref}: {len(hist)}.")

    pop = _prognos.kor_prognos(hist, ref, val["valdag"])["snitt"]
    return {
        "ar": ar,
        "referensdatum": ref.isoformat(),
        "valdag": val["valdag"].isoformat(),
        "antal_matningar": len(hist),
        "pop": {p: float(pop[p]) for p in cfg.PARTIER},
        "utfall": val["utfall"],
        "spurt": {p: val["utfall"][p] - float(pop[p]) for p in cfg.PARTIER},
    }


def valspurt(baslinje, dagar_kvar: int, ar: list[int]) -> tuple[dict, dict]:
    """Lägger tidigare valspurter ovanpå dagens läge.

    Jämförelsedatumet flyttar sig av sig självt när valdagen närmar sig:
    sexton dagar kvar jämförs med sexton dagar kvar i de tidigare valen. Ges
    flera år används genomsnittet av deras spurter.
    """
    val = [spurt_for_val(a, dagar_kvar) for a in ar]
    spurt = {p: sum(v["spurt"][p] for v in val) / len(val) for p in cfg.PARTIER}

    nytt = {p: max(0.0, float(baslinje[p]) + spurt[p]) for p in cfg.PARTIER}
    summa = sum(nytt.values())
    normaliserad = {p: v * 100 / summa for p, v in nytt.items()}

    # Pekar valen åt samma håll? Med bara ett val är frågan inte meningsfull.
    if len(val) > 1:
        ense = [p for p in cfg.PARTIER
                if all(v["spurt"][p] > 0 for v in val)
                or all(v["spurt"][p] < 0 for v in val)]
    else:
        ense = []

    info = {
        "dagar_kvar": dagar_kvar,
        "ar": ar,
        "val": val,
        "spurt": spurt,
        "eniga_partier": ense,
        "obalanserad_summa": summa,
    }
    return normaliserad, info


def trendforflyttning(matningar) -> tuple[dict, dict]:
    """Extrapolerar Demoskop och Novus sommartrend fram till valdagen.

    En rät linje läggs genom varje partis mätvärden från juni och framåt och
    förlängs till valdagen. Linjerna dras oberoende av varandra, så summan
    hamnar sällan på hundra och normaliseras efteråt.
    """
    import numpy as np

    m = matningar[
        matningar["institut"].isin(TRENDINSTITUT)
        & (matningar["datum"] >= pd.Timestamp(TRENDSTART))
    ].copy()
    if len(m) < 4:
        raise ValueError(
            f"För få mätningar för trendlinjen: {len(m)} sedan {TRENDSTART}.")

    start = pd.Timestamp(TRENDSTART)
    t = (m["datum"] - start).dt.days.to_numpy()
    t_val = (pd.Timestamp(cfg.VALDAG) - start).days

    ra = {}
    lutningar = {}
    for parti in cfg.PARTIER:
        lut, intercept = np.polyfit(t, m[parti].to_numpy(), 1)
        ra[parti] = max(0.0, lut * t_val + intercept)
        lutningar[parti] = lut * 30.44   # procentenheter per månad

    summa = sum(ra.values())
    normaliserad = {p: v * 100 / summa for p, v in ra.items()}

    info = {
        "antal": len(m),
        "institut": sorted(m["institut"].unique().tolist()),
        "forsta": m["datum"].min().date().isoformat(),
        "sista": m["datum"].max().date().isoformat(),
        "lutning_per_manad": lutningar,
        "obalanserad_summa": summa,
        "matningar": m.sort_values("datum")[
            ["institut", "datum"] + list(cfg.PARTIER)].to_dict("records"),
    }
    return normaliserad, info


SCENARIER = [
    Scenario(
        id="l_over_sparren",
        namn="Liberalerna klarar spärren",
        fraga="Vad händer om L tar sig över fyra procent på upploppet?",
        beskrivning=(
            "Liberalerna ligger under spärren i prognosen och får noll mandat. "
            "Partiet har historiskt vunnit väljare sent, och en stödröstning "
            "från de borgerliga grannarna skulle kunna lyfta det över gränsen. "
            "Scenariot lägger L strax över fyra procent och tar rösterna "
            "främst från C, men även från KD, M och S."
        ),
        forflyttning={"L": 1.97, "C": -0.90, "KD": -0.45, "M": -0.42, "S": -0.20},
        forbehall=(
            "Att L hamnar precis över spärren är det svåraste utfallet att "
            "prognosticera. Skillnaden mellan 3,9 och 4,1 procent är noll "
            "eller drygt tjugo mandat, och ligger långt inom mätfelet."
        ),
    ),
    Scenario(
        id="orebropartiet_valkrets",
        namn="Örebropartiet in via valkretsen",
        fraga="Vad händer om Örebropartiet får femton procent i Örebro län?",
        beskrivning=(
            "Vallagen har två vägar till riksdagen: fyra procent i hela landet, "
            "eller tolv procent i en enskild valkrets. Den andra vägen har inte "
            "gett mandat sedan 1900-talet. Örebropartiet mäter starkt i "
            "kommunvalet, och scenariot prövar vad som händer om stödet håller "
            "hela vägen upp till riksdagsvalet i Örebro län. Femton procent "
            "ligger klart över valkretsspärren och räcker till mer än ett "
            "mandat."
        ),
        valkretsparti={
            "namn": "Örebropartiet",
            "kod": "ÖP",
            "valkrets": "Örebro län",
            "andel_i_valkrets": 15.0,
            "farg": "#7B3FA0",
        },
        # Örebro län har tolv av 349 mandat, alltså 3,4 procent av riket.
        # Femton procent i länet motsvarar därför cirka 0,52 procentenheter
        # nationellt, tagna från de partier som står starkast i länet.
        forflyttning={"SD": -0.18, "S": -0.15, "M": -0.10, "KD": -0.04,
                      "V": -0.02, "C": -0.02, "MP": -0.01},
        forbehall=(
            "Detta är scenariets mest osäkra antagande. Modellen skattar att "
            "ett lokalt parti behåller knappt en femtedel av sitt kommunstöd i "
            "riksdagsvalet, vilket gör tolv procent i valkretsen mycket "
            "osannolikt. Örebropartiet mätte 18,4 procent i kommunvalet, vilket "
            "motsvarar omkring 3,5 procent i riksdagsvalet i länet. Rösterna "
            "antas komma främst från SD, S och M, och i mindre grad från "
            "övriga partier."
        ),
    ),
    Scenario(
        id="sommartrend",
        namn="Sommartrenden håller i sig",
        fraga="Vad händer om sommarens rörelse fortsätter rakt fram till valdagen?",
        beskrivning=(
            "Demoskop och Novus mäter tätast och jämnast av instituten. "
            "Scenariot lägger en rät linje genom deras mätningar från juni, "
            "juli och augusti och förlänger den till valdagen. Det är ett "
            "mekaniskt antagande: opinionen rör sig sällan linjärt, och de "
            "sista veckorna före ett val brukar vara de mest rörliga. Men det "
            "visar vart sommarens riktning pekar om ingenting bryter den."
        ),
        trend=True,
        forbehall=(
            "En rät linje genom sex mätningar är ett svagt underlag och tar "
            "varken hänsyn till institutens husfaktorer eller till att "
            "opinionen historiskt planar ut nära valdagen. Huvudprognosen "
            "väger alla institut, korrigerar för husfaktorer och simulerar "
            "utfallet, och är därför en bättre gissning om vad som faktiskt "
            "händer. Trenden svarar bara på vad riktningen pekar mot."
        ),
    ),
    Scenario(
        id="samma_valspurt",
        namn="Samma valspurt som 2022",
        fraga="Vad händer om upploppet upprepar sig precis som förra valet?",
        beskrivning=(
            "Opinionsmätningar och valresultat skiljer sig nästan alltid åt, "
            "och skillnaden uppstår till stor del under de sista veckorna. "
            "Scenariot mäter hur långt varje parti flyttade sig mellan "
            "sammanvägningen och det faktiska utfallet 2022, räknat från "
            "exakt lika många dagar före valdagen som i dag, och lägger den "
            "rörelsen ovanpå dagens nivåer. Jämförelsedatumet flyttar sig "
            "därför av sig självt allteftersom valdagen närmar sig."
        ),
        valspurt=[2022],
        forbehall=(
            "Vilar på ett enda val. Jämför med scenariot som väger in 2018: "
            "de två valen pekar åt motsatt håll för sex av åtta partier, och "
            "SD:s spurt var minus fyra procentenheter 2018 mot plus två 2022. "
            "Läs siffran som en storleksordning på hur mycket ett upplopp kan "
            "flytta, inte som en riktningsangivelse."
        ),
    ),
    Scenario(
        id="snitt_valspurt",
        namn="Genomsnittlig valspurt",
        fraga="Vad händer om upploppet liknar de två senaste valen i snitt?",
        beskrivning=(
            "Samma räkning som föregående scenario, men med genomsnittet av "
            "valspurten 2018 och 2022 i stället för bara det senaste valet. "
            "Att jämföra de två scenarierna säger mer än något av dem säger "
            "ensamt: där de pekar åt olika håll finns inget mönster att luta "
            "sig mot."
        ),
        valspurt=[2018, 2022],
        forbehall=(
            "Två val är fortfarande ett tunt underlag, och att ta "
            "genomsnittet av två motsatta rörelser ger ett tal nära noll som "
            "inte betyder att ingenting händer, bara att valen sa olika "
            "saker. Bara Vänsterpartiet och Socialdemokraterna rörde sig åt "
            "samma håll i båda valen. Wikipedias sidor för 2010 och 2014 har "
            "en annan tabellstruktur som modellens skrapare inte tolkar, så "
            "underlaget går inte att utöka utan handpåläggning."
        ),
    ),

]


def _mandat_med_valkretsparti(roster: dict[str, float], vp: dict | None) -> tuple[dict, int]:
    """Fördelar mandat och lyfter ut de mandat ett valkretsparti tar.

    Ett parti som klarar tolv procent i en valkrets deltar i fördelningen av
    den valkretsens fasta mandat, men inte i utjämningen. Mandaten tas därför
    från valkretsen och resten av riket fördelas som vanligt.
    """
    if not vp:
        return modell.fordela_mandat(roster), 0

    platser = VALKRETSMANDAT.get(vp["valkrets"], 12)

    # Inom valkretsen fördelas mandaten mellan riksdagspartierna och det
    # lokala partiet med samma metod som i riket. Det lokala partiets andel
    # tas ur valkretsen, så övriga partier måste skalas ned till det som blir
    # kvar. Utan normaliseringen summerar andelarna till över hundra procent
    # och det lokala partiet får för lite vikt i fördelningen.
    andel = vp["andel_i_valkrets"]
    riks = {p: roster.get(p, 0.0) for p in cfg.PARTIER}
    summa = sum(riks.values())
    skala = (100.0 - andel) / summa if summa else 0.0
    i_valkrets = {p: v * skala for p, v in riks.items()}
    i_valkrets[vp["kod"]] = andel
    lokalt = modell.fordela_mandat(i_valkrets, platser)
    vunna = lokalt.get(vp["kod"], 0)

    ovriga = modell.fordela_mandat(roster, cfg.MANDAT_TOTALT - vunna)
    ovriga[vp["kod"]] = vunna
    return ovriga, vunna


def valkretsrakning(roster: dict[str, float], vp: dict) -> dict:
    """Steg för steg-räkning av mandaten i valkretsen.

    Gör det möjligt att kontrollera varför det lokala partiet får just det
    antal mandat det får, och hur nära nästa mandat det ligger.
    """
    platser = VALKRETSMANDAT.get(vp["valkrets"], 12)
    andel = vp["andel_i_valkrets"]
    riks = {p: roster.get(p, 0.0) for p in cfg.PARTIER}
    summa = sum(riks.values())
    skala = (100.0 - andel) / summa if summa else 0.0
    andelar = {p: v * skala for p, v in riks.items()}
    andelar[vp["kod"]] = andel

    mandat = {p: 0 for p in andelar}
    divisorer = {p: 1.2 for p in andelar}
    steg = []
    for _ in range(platser):
        vinnare = max(andelar, key=lambda p: andelar[p] / divisorer[p])
        kvot = andelar[vinnare] / divisorer[vinnare]
        mandat[vinnare] += 1
        divisorer[vinnare] = 2 * mandat[vinnare] + 1
        steg.append({"parti": vinnare, "kvot": kvot})

    # Vad hade krävts för ett mandat till? Nästa kvot för partiet måste
    # överstiga den sista vinnande kvoten.
    sista = steg[-1]["kvot"]
    nasta_divisor = 2 * mandat[vp["kod"]] + 1
    behovs = sista * nasta_divisor

    return {
        "platser": platser,
        "andelar": andelar,
        "mandat": mandat,
        "steg": steg,
        "vunna": mandat[vp["kod"]],
        "sista_kvot": sista,
        "kvot_for_nasta": andel / nasta_divisor,
        "behovs_for_nasta": behovs,
    }


def kor(scenario: Scenario, baslinje: pd.Series,
        matningar: pd.DataFrame | None = None,
        dagar_kvar: int | None = None) -> dict:
    """Räknar ut ett scenarios utfall från prognosens viktade snitt."""
    bas = {p: float(baslinje[p]) for p in cfg.PARTIER}

    if scenario.trend:
        if matningar is None:
            raise ValueError("Trendscenariot behöver mätningarna.")
        nytt, info = trendforflyttning(matningar)
        scenario.trenddata = info
    elif scenario.valspurt:
        if dagar_kvar is None:
            raise ValueError("Valspurtscenariot behöver antal dagar kvar.")
        nytt, info = valspurt(baslinje, dagar_kvar, scenario.valspurt)
        scenario.spurtdata = info
    else:
        nytt = dict(bas)
        for parti, delta in scenario.forflyttning.items():
            nytt[parti] = max(0.0, nytt.get(parti, 0.0) + delta)

    mandat_bas = modell.fordela_mandat(bas)
    mandat_nytt, vk_mandat = _mandat_med_valkretsparti(nytt, scenario.valkretsparti)

    return {
        "scenario": scenario,
        "roster_bas": bas,
        "roster_nytt": nytt,
        "mandat_bas": mandat_bas,
        "mandat_nytt": mandat_nytt,
        "valkretsmandat": vk_mandat,
        "koalitioner": _koalitioner(mandat_bas, mandat_nytt, bas, nytt),
        "summa_forflyttning": sum(scenario.forflyttning.values()),
    }


def _koalitioner(mandat_bas: dict, mandat_nytt: dict,
                 roster_bas: dict, roster_nytt: dict) -> list[dict]:
    """Jämför varje regeringsalternativs mandat före och efter.

    Ett alternativ kan ha extra villkor utöver 175 mandat, som att C måste
    klara spärren för att kunna ingå. Villkoren prövas mot röstandelarna.
    """
    rader = []
    for alt in cfg.REGERINGSALTERNATIV:
        f = sum(mandat_bas.get(p, 0) for p in alt["partier"])
        e = sum(mandat_nytt.get(p, 0) for p in alt["partier"])

        villkor_f = villkor_e = True
        for parti, grans in (alt.get("krav", {}).get("minst") or {}).items():
            villkor_f &= roster_bas.get(parti, 0.0) >= grans * 100
            villkor_e &= roster_nytt.get(parti, 0.0) >= grans * 100

        rader.append({
            "id": alt["id"],
            "namn": alt["namn"],
            "partier": alt["partier"],
            "fore": f,
            "efter": e,
            "diff": e - f,
            "majoritet_fore": f >= 175 and villkor_f,
            "majoritet_efter": e >= 175 and villkor_e,
        })
    return sorted(rader, key=lambda r: -r["efter"])


def kor_alla(baslinje: pd.Series,
             matningar: pd.DataFrame | None = None,
             dagar_kvar: int | None = None) -> list[dict]:
    ut = []
    for s in SCENARIER:
        if s.trend and matningar is None:
            continue
        if s.valspurt and dagar_kvar is None:
            continue
        try:
            ut.append(kor(s, baslinje, matningar, dagar_kvar))
        except Exception as fel:
            print(f"  Scenariot {s.id} kunde inte räknas: {fel}")
    return ut
