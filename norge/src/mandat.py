"""Norsk mandatfördelning: distriktsmandat och utjämningsmandat.

Reproducerar stortingsvalen 2021 och 2025 exakt, noll mandats avvikelse för
samtliga partier. Kör `python3 mandat.py` för att verifiera det.

Fördelningen skiljer sig från den svenska på tre punkter som alla spelar roll:

  1. Första divisorn är 1,4, inte 1,2.
  2. Fyraprocentsspärren gäller BARA utjämningsmandaten. Ett parti under
     spärren kan vinna distriktsmandat på egen styrka, vilket Venstre gjorde
     2025 med 3,69 procent och tre mandat.
  3. Varje distrikt har exakt ett utjämningsmandat, och vilket parti som får
     det avgörs av en kvot som väger distriktets röstetal per mandat.

Se forskning/VALSYSTEMET.md för regelverket och källhänvisningar.
"""
from __future__ import annotations

SPARRGRANS = 0.04
FORSTA_DIVISOR = 1.4
UTJAMNINGSMANDAT = 19

# Mandat per valdistrikt, inklusive distriktets enda utjämningsmandat.
# Räknas om av departementet varje val efter invånarantal och areal.
MANDAT_PER_DISTRIKT_2025 = {
    "Østfold": 9, "Akershus": 20, "Oslo": 20, "Hedmark": 7, "Oppland": 6,
    "Buskerud": 8, "Vestfold": 7, "Telemark": 6, "Aust-Agder": 4,
    "Vest-Agder": 6, "Rogaland": 14, "Hordaland": 16, "Sogn og Fjordane": 4,
    "Møre og Romsdal": 8, "Sør-Trøndelag": 10, "Nord-Trøndelag": 5,
    "Nordland": 9, "Troms": 6, "Finnmark": 4,
}

MANDAT_PER_DISTRIKT_2021 = dict(MANDAT_PER_DISTRIKT_2025,
                                **{"Akershus": 19, "Finnmark": 5})

# Restpost i röstdata. Räknas i underlaget men konkurrerar inte om mandat,
# eftersom den är en klump av många småpartier och inget enskilt parti.
RESTPOST = "Andre"


def sainte_lague(roster: dict[str, float], platser: int,
                 forsta: float = FORSTA_DIVISOR) -> dict[str, int]:
    """St. Laguës modifierade metod. Divisorer 1,4 - 3 - 5 - 7 ...

    Ingen spärr tillämpas här. Anropande kod avgör vilka partier som får delta.

    Implementerad med en förberäknad kvotlista i stället för en max-sökning per
    plats. Fördelningen körs miljontals gånger i simuleringen, och att ta de
    `platser` största kvoterna på en gång är märkbart snabbare än att leta
    vinnare om och om igen.
    """
    mandat = {p: 0 for p in roster}
    if platser <= 0:
        return mandat

    # Ett parti kan aldrig få fler än `platser` mandat, så det räcker att
    # räkna ut så många kvoter per parti.
    kvoter = []
    for parti, r in roster.items():
        if r <= 0:
            continue
        for i in range(platser):
            kvoter.append((r / (forsta if i == 0 else 2 * i + 1), parti))

    kvoter.sort(reverse=True)
    for _, parti in kvoter[:platser]:
        mandat[parti] += 1
    return mandat


def fordela(roster_per_distrikt: dict[str, dict[str, float]],
            mandat_per_distrikt: dict[str, int] | None = None,
            restpost: str = RESTPOST) -> dict:
    """Fördelar samtliga 169 mandat från röstetal per distrikt och parti.

    `roster_per_distrikt` är {distrikt: {parti: röster}}. Röstetalen kan vara
    absoluta tal eller procent, så länge de är jämförbara mellan distrikt, men
    absoluta röstetal krävs för att distriktens vikt mot varandra ska bli rätt.

    Returnerar en dict med totalt antal mandat per parti, uppdelningen i
    distrikts- och utjämningsmandat, samt vilket parti som tog varje distrikts
    utjämningsmandat.
    """
    if mandat_per_distrikt is None:
        mandat_per_distrikt = MANDAT_PER_DISTRIKT_2025

    saknade = set(roster_per_distrikt) - set(mandat_per_distrikt)
    if saknade:
        raise ValueError(f"Distrikt utan mandattal: {sorted(saknade)}")

    partier = sorted({p for d in roster_per_distrikt.values() for p in d}
                     - {restpost})
    platser_totalt = sum(mandat_per_distrikt.values())

    # --- Steg 1: distriktsmandat. Alla utom ett per distrikt, ingen spärr. ---
    distrikt = {
        d: sainte_lague({p: v for p, v in roster.items() if p != restpost},
                        mandat_per_distrikt[d] - 1)
        for d, roster in roster_per_distrikt.items()
    }
    vunna = {p: sum(distrikt[d].get(p, 0) for d in distrikt) for p in partier}

    # --- Steg 2: nationell kvot, bara för partier över spärren. -------------
    riks = {p: sum(roster_per_distrikt[d].get(p, 0)
                   for d in roster_per_distrikt) for p in partier}
    # Spärren räknas mot SAMTLIGA godkända röster, alltså inklusive restposten.
    # Räknas nämnaren bara på de redovisade partierna blir varje andel för hög:
    # MDG hade 2021 fått fyra procent i stället för 3,94 och felaktigt klarat
    # spärren, vilket ger fyra mandats fel.
    giltiga = sum(sum(d.values()) for d in roster_per_distrikt.values())
    if giltiga <= 0:
        raise ValueError("Röstunderlaget är noll.")

    over = {p: v for p, v in riks.items() if v / giltiga >= SPARRGRANS}
    if not over:
        # Inget parti klarar spärren. Konstitutionellt omöjligt men kan uppstå
        # i enstaka simuleringar. Utjämningen faller då bort och alla 169
        # mandat blir i praktiken distriktsmandat.
        over = dict(riks)

    # Partier under spärren behåller sina distriktsmandat. Dessa dras av innan
    # resten fördelas nationellt.
    laste = sum(vunna[p] for p in partier if p not in over)

    # Överfördelning: ett parti kan vinna fler distriktsmandat än sin
    # nationella kvot. Mandaten kan inte tas ifrån det, så partiet låses på
    # sitt distriktsresultat och resten fördelas om utan det. 2021 krävdes två
    # varv: först Senterpartiet med 28 distriktsmandat mot kvoten 25, sedan
    # Arbeiderpartiet. Utan detta blir summan 170 mandat i stället för 169.
    kvarvarande = dict(over)
    while True:
        nationellt = sainte_lague(kvarvarande, platser_totalt - laste)
        overskott = [p for p in kvarvarande if vunna[p] > nationellt[p]]
        if not overskott or len(overskott) == len(kvarvarande):
            break
        for p in overskott:
            laste += vunna[p]
            del kvarvarande[p]

    utjamning = {p: max(0, nationellt.get(p, 0) - vunna[p]) if p in kvarvarande
                 else 0 for p in partier}

    # --- Steg 3: vilket distrikt varje utjämningsmandat tas från. -----------
    # Valgloven § 11-6 tredje ledet: partiets röster i distriktet divideras med
    # 2 * vunna distriktsmandat + 1, och därefter med distriktets genomsnittliga
    # röstetal per distriktsmandat.
    kvoter = []
    for d, roster in roster_per_distrikt.items():
        distriktsmandat = mandat_per_distrikt[d] - 1
        if distriktsmandat <= 0:
            continue
        snitt = sum(roster.values()) / distriktsmandat
        if snitt <= 0:
            continue
        for p, r in roster.items():
            if p == restpost or utjamning.get(p, 0) <= 0:
                continue
            kvoter.append((r / (2 * distrikt[d].get(p, 0) + 1) / snitt, d, p))
    kvoter.sort(reverse=True)

    kvar = dict(utjamning)
    tagna: set[str] = set()
    tilldelat: dict[str, str] = {}
    for _, d, p in kvoter:
        if d in tagna or kvar.get(p, 0) <= 0:
            continue
        tagna.add(d)
        kvar[p] -= 1
        tilldelat[d] = p

    return {
        "mandat": {p: vunna[p] + utjamning.get(p, 0) for p in partier},
        "distriktsmandat": vunna,
        "utjamningsmandat": utjamning,
        "utjamning_per_distrikt": tilldelat,
        "over_sparren": sorted(kvarvarande),
        "andel": {p: riks[p] / giltiga * 100 for p in partier},
    }


# --- Verifiering -------------------------------------------------------------

FAKTISKT = {
    2025: {"Ap": 53, "FrP": 47, "H": 24, "SV": 9, "Sp": 9, "R": 9,
           "MDG": 8, "KrF": 7, "V": 3},
    2021: {"Ap": 48, "H": 36, "Sp": 28, "FrP": 21, "SV": 13, "R": 8,
           "V": 8, "MDG": 3, "KrF": 3, "PF": 1},
}


def _verifiera() -> int:
    """Kör fördelningen mot 2021 och 2025 och rapporterar avvikelsen."""
    import json
    from pathlib import Path

    rot = Path(__file__).resolve().parent.parent
    totalt_fel = 0

    for ar, mandattal in ((2021, MANDAT_PER_DISTRIKT_2021),
                          (2025, MANDAT_PER_DISTRIKT_2025)):
        fil = rot / "forskning" / f"roster{ar}_full.json"
        if not fil.exists():
            print(f"{ar}: saknar {fil.relative_to(rot)}, hoppas över.")
            continue
        roster = json.loads(fil.read_text(encoding="utf-8"))
        # SSB skriver Finnmark med samiskt namn.
        roster = {d.split(" - ")[0]: v for d, v in roster.items()}
        # Pasientfokus redovisas inte separat av SSB men vann ett
        # distriktsmandat i Finnmark 2021 med 12,70 procent i distriktet.
        if ar == 2021:
            roster["Finnmark"]["PF"] = 4950
            roster["Finnmark"]["Andre"] -= 4950

        res = fordela(roster, mandattal)
        faktiskt = FAKTISKT[ar]
        fel = sum(abs(res["mandat"].get(p, 0) - f) for p, f in faktiskt.items())
        totalt_fel += fel

        print(f"\n{'=' * 58}\n  STORTINGSVALET {ar}\n{'=' * 58}")
        print(f"{'PARTI':<6}{'ANDEL':>8}{'DISTR':>7}{'UTJÄMN':>8}"
              f"{'TOTALT':>8}{'FAKTISKT':>10}{'DIFF':>7}")
        print("-" * 58)
        for p in sorted(res["mandat"], key=lambda x: -res["mandat"][x]):
            diff = res["mandat"][p] - faktiskt.get(p, 0)
            flagga = "" if diff == 0 else "  <-"
            print(f"{p:<6}{res['andel'][p]:>7.2f}%{res['distriktsmandat'][p]:>7}"
                  f"{res['utjamningsmandat'][p]:>8}{res['mandat'][p]:>8}"
                  f"{faktiskt.get(p, 0):>10}{diff:>+7}{flagga}")
        print("-" * 58)
        print(f"Summa {sum(res['mandat'].values())} mandat "
              f"(distrikt {sum(res['distriktsmandat'].values())}, "
              f"utjämning {sum(res['utjamningsmandat'].values())})")
        print(f"Över spärren: {', '.join(res['over_sparren'])}")
        print(f"Avvikelse mot faktiskt utfall: {fel} mandat")

    print(f"\n{'=' * 58}")
    print(f"Total avvikelse över båda valen: {totalt_fel} mandat")
    return 0 if totalt_fel == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_verifiera())
