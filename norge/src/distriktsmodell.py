"""Översätter en rikstrend till resultat per valdistrikt.

Nödvändigt i Norge, till skillnad från Sverige. Den svenska modellen kan
approximera riket som en valkrets eftersom utjämningen gör slutresultatet
nära riksproportionellt. Här går det inte: fyraprocentsspärren gäller bara
utjämningsmandaten, så ett parti under spärren får mandat uteslutande genom
distriktsstyrka. Venstres tre mandat 2025 kan inte härledas ur riksandelen
3,69 procent, bara ur var partiet är starkt.

Metoden är en relativ profil per distrikt och parti:

    profil[distrikt][parti] = distriktets andel / rikets andel

Profilen är påfallande stabil mellan val. MDG i Oslo låg på 2,15 gånger
riksnivån 2021 och 2,16 gånger 2025. Senterpartiet i Sogn og Fjordane på 2,10
respektive 2,87.

Validerat ur stickprov: med **2021 års profil** och 2025 års riksandelar som
enda indata blir mandatfördelningen 2025 fel med 6 mandat av 169, och samtliga
spärrnära partier hamnar rätt, inklusive Venstres tre. Med 2025 års egen
profil blir felet noll, vilket är metodens övre gräns.

Kör `python3 distriktsmodell.py` för att se båda testerna.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

import mandat

ROT = Path(__file__).resolve().parent.parent

# Partiernas ordning spelar ingen roll här, men listan avgör vilka partier som
# får en profil. Restposten Andre hanteras separat, se las_valresultat.
PARTIER = ["R", "SV", "Ap", "Sp", "MDG", "KrF", "V", "H", "FrP"]
RESTPOST = "Andre"


@functools.lru_cache(maxsize=8)
def _las_valresultat_cachad(ar: int) -> str:
    """Läser filen en gång per val. Se las_valresultat."""
    fil = ROT / "forskning" / f"roster{ar}_full.json"
    if not fil.exists():
        raise FileNotFoundError(
            f"Saknar {fil.relative_to(ROT)}. Hämtas från SSB tabell 08092, "
            f"se forskning/DATAKALLOR.md.")
    return fil.read_text(encoding="utf-8")


def las_valresultat(ar: int) -> dict[str, dict[str, float]]:
    """Läser röstetal per distrikt och parti från forskning/.

    SSB skriver Finnmark med samiskt tillägg. Namnet kortas så att distrikten
    matchar nycklarna i mandat.MANDAT_PER_DISTRIKT.
    """
    rader = json.loads(_las_valresultat_cachad(ar))
    return {d.split(" - ")[0]: v for d, v in rader.items()}


def riksandelar(roster: dict[str, dict[str, float]]) -> dict[str, float]:
    """Riksandel i procent per parti, räknat på samtliga godkända röster."""
    riks: dict[str, float] = {}
    for distrikt in roster.values():
        for parti, v in distrikt.items():
            riks[parti] = riks.get(parti, 0.0) + v
    totalt = sum(riks.values())
    return {p: riks.get(p, 0.0) / totalt * 100 for p in PARTIER}


def rostetal_per_distrikt(roster: dict[str, dict[str, float]]) -> dict[str, float]:
    return {d: sum(v.values()) for d, v in roster.items()}


@functools.lru_cache(maxsize=8)
def _profil_och_rostetal(ar: int) -> tuple:
    """Profil och röstetal per distrikt, cachat per val.

    Simuleringen anropar prognos() tiotusentals gånger med samma profilår.
    Utan cache byggs profilen om varje gång, vilket dominerade körtiden.
    Returnerar tupler eftersom lru_cache kräver hashbara värden.
    """
    profil = bygg_profil(ar)
    rostetal = rostetal_per_distrikt(las_valresultat(ar))
    return (tuple((d, tuple(sorted(v.items()))) for d, v in profil.items()),
            tuple(sorted(rostetal.items())))


def _uppackad_profil(ar: int) -> tuple[dict, dict]:
    profil_t, rostetal_t = _profil_och_rostetal(ar)
    return ({d: dict(v) for d, v in profil_t}, dict(rostetal_t))


def bygg_profil(ar: int) -> dict[str, dict[str, float]]:
    """Bygger relativa distriktsprofiler ur ett valresultat.

    Ett parti som inte ställt upp i ett distrikt får profilen noll, inte ett,
    så att modellen inte hittar på stöd där partiet saknas.
    """
    roster = las_valresultat(ar)
    riks = riksandelar(roster)

    profil: dict[str, dict[str, float]] = {}
    for distrikt, partiroster in roster.items():
        distriktstotal = sum(partiroster.values())
        profil[distrikt] = {}
        for parti in PARTIER:
            riksandel = riks.get(parti, 0.0)
            if riksandel <= 0 or distriktstotal <= 0:
                profil[distrikt][parti] = 0.0
                continue
            distriktsandel = partiroster.get(parti, 0.0) / distriktstotal * 100
            profil[distrikt][parti] = distriktsandel / riksandel
    return profil


def fordela_till_distrikt(riksandel: dict[str, float],
                          profil: dict[str, dict[str, float]],
                          rostetal: dict[str, float]) -> dict[str, dict[str, float]]:
    """Skalar en rikstrend till röstetal per distrikt och parti.

    `riksandel` är procent per parti och behöver inte summera till hundra:
    restposten ligger utanför de nio partierna. Skillnaden mot hundra bevaras
    som en Andre-post i varje distrikt, eftersom fyraprocentsspärren räknas
    mot samtliga godkända röster. Utan den blir varje partis andel för hög och
    spärrberäkningen fel, vilket är den fälla som gav fyra mandats fel i
    valideringen av mandat.py.
    """
    restandel = max(0.0, 100.0 - sum(riksandel.values()))

    ut: dict[str, dict[str, float]] = {}
    for distrikt, distriktsprofil in profil.items():
        if distrikt not in rostetal:
            continue
        rader = {p: riksandel.get(p, 0.0) * distriktsprofil.get(p, 0.0)
                 for p in PARTIER}
        # Restposten antas följa riket, den saknar egen profil.
        rader[RESTPOST] = restandel
        summa = sum(rader.values())
        if summa <= 0:
            continue
        # Normalisera till distriktets röstetal, så att distrikten väger rätt
        # mot varandra i den nationella spärrberäkningen.
        skala = rostetal[distrikt] / summa
        ut[distrikt] = {p: v * skala for p, v in rader.items()}
    return ut


def prognos(riksandel: dict[str, float], profilar: int = 2025,
            mandat_per_distrikt: dict[str, int] | None = None) -> dict:
    """Räknar mandat från en rikstrend, via distriktsfördelning.

    `profilar` är det val vars distriktsprofil används. Standard är senaste
    valet, alltså 2025.
    """
    if mandat_per_distrikt is None:
        mandat_per_distrikt = mandat.MANDAT_PER_DISTRIKT_2025

    profil, rostetal = _uppackad_profil(profilar)
    roster = fordela_till_distrikt(riksandel, profil, rostetal)
    return mandat.fordela(roster, mandat_per_distrikt)


# --- Verifiering -------------------------------------------------------------

FAKTISKT_MANDAT = {
    2025: {"Ap": 53, "FrP": 47, "H": 24, "SV": 9, "Sp": 9, "R": 9,
           "MDG": 8, "KrF": 7, "V": 3},
    2021: {"Ap": 48, "H": 36, "Sp": 28, "FrP": 21, "SV": 13, "R": 8,
           "V": 8, "MDG": 3, "KrF": 3},
}


def _verifiera() -> int:
    """Testar metoden ur stickprov: gammal profil, nya riksandelar."""
    fall = [
        (2025, 2021, mandat.MANDAT_PER_DISTRIKT_2025,
         "2021 års profil mot 2025 års utfall, ur stickprov"),
        (2025, 2025, mandat.MANDAT_PER_DISTRIKT_2025,
         "2025 års egen profil, metodens övre gräns"),
        (2021, 2025, mandat.MANDAT_PER_DISTRIKT_2021,
         "2025 års profil mot 2021 års utfall, bakåt ur stickprov"),
    ]

    totalt_fel = 0
    for utfallsar, profilar, mandattal, beskrivning in fall:
        roster = las_valresultat(utfallsar)
        riks = riksandelar(roster)
        profil = bygg_profil(profilar)
        rostetal = rostetal_per_distrikt(las_valresultat(profilar))
        res = mandat.fordela(
            fordela_till_distrikt(riks, profil, rostetal), mandattal)

        faktiskt = FAKTISKT_MANDAT[utfallsar]
        fel = sum(abs(res["mandat"].get(p, 0) - faktiskt.get(p, 0))
                  for p in PARTIER)
        if profilar != utfallsar:
            totalt_fel += fel

        print(f"\n{'=' * 62}\n  {beskrivning}\n{'=' * 62}")
        print(f"{'PARTI':<6}{'RIKS':>8}{'MANDAT':>8}{'FAKTISKT':>10}{'DIFF':>7}")
        print("-" * 62)
        for p in sorted(PARTIER, key=lambda x: -res["mandat"].get(x, 0)):
            diff = res["mandat"].get(p, 0) - faktiskt.get(p, 0)
            print(f"{p:<6}{riks[p]:>7.2f}%{res['mandat'].get(p, 0):>8}"
                  f"{faktiskt.get(p, 0):>10}{diff:>+7}"
                  f"{'' if diff == 0 else '  <-'}")
        print("-" * 62)
        print(f"Avvikelse: {fel} mandat av {sum(mandattal.values())}")

    print(f"\n{'=' * 62}")
    print(f"Summa avvikelse ur stickprov: {totalt_fel} mandat")
    # Sex mandats fel per val är metodens observerade nivå. Gränsen sätts med
    # marginal så att testet fångar en verklig regression, inte normalt brus.
    return 0 if totalt_fel <= 16 else 1


if __name__ == "__main__":
    raise SystemExit(_verifiera())
