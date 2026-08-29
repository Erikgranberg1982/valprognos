"""Scenarier för riksdagsvalet: tänkta utfall och vad de gör med mandaten.

Ett scenario är inte en prognos. Det är en fråga: om det här händer, hur ser
riksdagen ut då? Modellens egen prognos säger vad som är troligt; scenarierna
säger vad som skulle följa av något som ännu inte är det.

Varje scenario definierar en förflyttning av väljarstöd och räknar om mandat
och koalitioner med samma metod som huvudprognosen.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

import config as cfg
import modell


# Riksdagens 349 mandat fördelas i 29 valkretsar. Örebro län har tolv, vilket
# behövs för scenariot om ett lokalt parti som tar sig in via valkretsspärren.
VALKRETSMANDAT = {"Örebro län": 12}


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
        fraga="Vad händer om Örebropartiet får tolv procent i Örebro län?",
        beskrivning=(
            "Vallagen har två vägar till riksdagen: fyra procent i hela landet, "
            "eller tolv procent i en enskild valkrets. Den andra vägen har inte "
            "gett mandat sedan 1900-talet. Örebropartiet mäter starkt i "
            "kommunvalet, och scenariot prövar vad som händer om stödet håller "
            "hela vägen upp till riksdagsvalet i Örebro län."
        ),
        valkretsparti={
            "namn": "Örebropartiet",
            "kod": "ÖP",
            "valkrets": "Örebro län",
            "andel_i_valkrets": 12.0,
            "farg": "#7B3FA0",
        },
        # Örebro län har tolv av 349 mandat, alltså 3,4 procent av riket. Tolv
        # procent i länet motsvarar därför cirka 0,41 procentenheter
        # nationellt, tagna från de partier som står starkast i länet.
        forflyttning={"SD": -0.14, "S": -0.12, "M": -0.08, "KD": -0.03,
                      "V": -0.02, "C": -0.01, "MP": -0.01},
        forbehall=(
            "Detta är scenariets mest osäkra antagande. Modellen skattar att "
            "ett lokalt parti behåller knappt en femtedel av sitt kommunstöd i "
            "riksdagsvalet, vilket gör tolv procent i valkretsen mycket "
            "osannolikt. Örebropartiet mätte 18,4 procent i kommunvalet, vilket "
            "motsvarar omkring 3,5 procent i riksdagsvalet i länet. Rösterna "
            "antas komma främst från SD, S och M, och i mindre grad från "
            "övriga partier. Tolv procent ger ett mandat, inte två: för ett "
            "andra mandat hade det krävts omkring fjorton procent i "
            "valkretsen."
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


def kor(scenario: Scenario, baslinje: pd.Series) -> dict:
    """Räknar ut ett scenarios utfall från prognosens viktade snitt."""
    bas = {p: float(baslinje[p]) for p in cfg.PARTIER}
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


def kor_alla(baslinje: pd.Series) -> list[dict]:
    return [kor(s, baslinje) for s in SCENARIER]
