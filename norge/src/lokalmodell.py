"""Prognos för fylkestings- och kommunestyrevalget 2027.

Metoden är den som Erik angav, och samma som den svenska modellen använder
efter jämförelse mot regionvalet 2022: **utgå från områdets eget resultat i
förra lokalvalet och skala med rikstrendens förändring**. Ett parti som fick
12,0 procent i en kommun 2023 och sedan gått från 14,6 till 15,6 nationellt
hamnar på 12,0 x 15,6/14,6, alltså 12,8 procent.

**Lokala partier hålls konstanta** på sin nivå från 2023. De kan inte
prognosticeras: det finns inga mätningar per kommun, och ett lokalt parti
beror på personer och sakfrågor som inte syns i rikstrenden.

Skalningen sker mot **stortingsvalets** rikstrend, eftersom det är den enda
opinionen som mäts löpande. Det är modellens svagaste led: väljarna röstar
bevisligen annorrunda i lokalval, och den skillnaden fångas bara i den mån
den låg i 2023 års resultat och är oförändrad sedan dess.

## Vad som skiljer mot stortingsmodellen

Fylkes- och kommunevalget har en helt annan mandatfördelning:

  1. **Ingen fyraprocentsspärr.** Spärren hör till stortingsvalets
     utjämningsmandat och finns inte här.
  2. **Inga utjämningsmandat.** Varje område fördelar sina egna mandat.
  3. Kvar blir alltså ren St. Laguë med första divisor 1,4, per område.

Den effektiva spärren blir i stället en funktion av församlingens storlek.
I ett kommunestyre med 27 platser krävs ungefär 2 procent för ett mandat, i
ett med 101 platser knappt en halv.

## Osäkerhet

Prognosen är väsentligt osäkrare än stortingsprognosen, av tre skäl som alla
är strukturella och inte går att räkna bort:

  1. Inga mätningar finns per kommun eller fylke.
  2. Rikstrenden gäller stortingsval, inte lokalval.
  3. Lokala partier hålls konstanta, och de var 9,5 procent av rösterna i
     kommunevalget 2023.

Backtestet i `_verifiera` mäter hur stort felet faktiskt blir: 2019 års
resultat skalat med den faktiska rikstrendsförändringen till 2023, jämfört med
utfallet 2023.
"""
from __future__ import annotations

from pathlib import Path

import config as cfg
import ssb_lokalval as ssb

ROT = Path(__file__).resolve().parent.parent

FORSTA_DIVISOR = 1.4
LOKALT = ssb.LOKALT

# Senaste lokalvalet. Nästa hålls 13 september 2027.
FORRA_LOKALVALET = "2023"
VALDAG_2027 = "2027-09-13"

# Riksopinionen vid respektive lokalvalsdag, alltså det tidsviktade snittet
# av stortingssympatimätningarna de fyra månaderna före valet. Detta är
# referenspunkten för rikstrenden, INTE närmaste stortingsval.
#
# Skillnaden är avgörande. Lokalvalen hålls två år efter stortingsvalen, och
# opinionen hinner röra sig långt på två år. Mätt mot stortingsvalen 2017 och
# 2021 gick fem av nio partier åt fel håll jämfört med lokalvalens faktiska
# förändring 2019 till 2023: Høyre föll 0,81 nationellt men steg 1,29 i
# kommunevalget, och Senterpartiet steg 1,31 nationellt men kollapsade till
# 0,57 lokalt. Mätt mot opinionen vid valdagen pekar sju av nio rätt.
#
# Framräknade med opinion_vid() nedan, ur data/matningar_historik.csv, och
# hårdkodade så att prognosen kan byggas utan den historiska serien. Kör
# `python3 lokalmodell.py --referens 2023` för att räkna om dem.
OPINION_VID_LOKALVAL = {
    "2019": {"R": 4.9, "SV": 7.3, "Ap": 25.0, "Sp": 16.0, "MDG": 6.2,
             "KrF": 3.8, "V": 3.1, "H": 22.7, "FrP": 11.0},
    "2023": {"R": 5.4, "SV": 9.2, "Ap": 20.3, "Sp": 6.6, "MDG": 4.2,
             "KrF": 3.9, "V": 5.3, "H": 31.0, "FrP": 13.9},
}


def rikstrend(riksprognos: dict[str, float],
              referens: dict[str, float] | None = None) -> dict[str, float]:
    """Förändringskvot per parti: dagens riksopinion delat med referensens.

    Referensen är riksopinionen vid det senaste lokalvalet, inte resultatet i
    närmaste stortingsval. Se OPINION_VID_LOKALVAL för varför: valet av
    referens är den enskilt viktigaste metodfrågan i modellen och avgör om
    skalningen förbättrar eller försämrar prognosen.

    Kvoten kapas i båda ändar. Ett parti som fyrdubblats nationellt har inte
    fyrdubblats i varje kommun: lokalvalsstödet är trögare, och en okapad kvot
    ger orimliga nivåer i kommuner där partiet redan var starkt.
    """
    if referens is None:
        referens = OPINION_VID_LOKALVAL[FORRA_LOKALVALET]
    ut = {}
    for parti in cfg.PARTIER:
        nu = riksprognos.get(parti)
        da = referens.get(parti)
        if not nu or not da or da <= 0:
            ut[parti] = 1.0
            continue
        ut[parti] = max(0.35, min(2.8, float(nu) / float(da)))
    return ut


def opinion_vid(valdag: str, fonster_dagar: int = 120) -> dict[str, float]:
    """Räknar riksopinionen vid ett datum ur den historiska mätningsserien.

    Används för att ta fram OPINION_VID_LOKALVAL och för att kontrollera att
    de hårdkodade värdena stämmer. Kräver data/matningar_historik.csv, som
    hämtas med `python3 hamta_matningar.py --fran 2012-01-01`.
    """
    from datetime import date as _date

    import pandas as pd

    import modell
    import prognos as _prognos

    fil = ROT / "data" / "matningar_historik.csv"
    if not fil.exists():
        raise FileNotFoundError(
            f"Saknar {fil.relative_to(ROT)}. Hämta med "
            f"`python3 hamta_matningar.py --fran 2012-01-01`.")

    df = _prognos.las_matningar(fil)
    slut = _date.fromisoformat(valdag)
    fonster = df[(df["datum"] <= pd.Timestamp(slut))
                 & ((pd.Timestamp(slut) - df["datum"]).dt.days <= fonster_dagar)]
    if len(fonster) < 5:
        raise ValueError(f"Bara {len(fonster)} mätningar inom {fonster_dagar} "
                         f"dagar före {valdag}.")
    snitt = modell.viktat_snitt(fonster, slut)
    return {p: round(float(snitt[p]), 1) for p in cfg.PARTIER}


def sainte_lague(roster: dict[str, float], platser: int,
                 forsta: float = FORSTA_DIVISOR) -> dict[str, int]:
    """St. Laguës modifierade metod, utan spärr.

    Samma metod som i stortingsvalet, men här finns ingen fyraprocentsspärr
    och inga utjämningsmandat. Den effektiva spärren följer i stället av
    församlingens storlek.
    """
    mandat = {p: 0 for p in roster}
    if platser <= 0:
        return mandat
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


def skala_omrade(forra: dict[str, float], trend: dict[str, float],
                 lokala_konstanta: bool = True) -> dict[str, float]:
    """Skalar ett områdes resultat med rikstrenden.

    Returnerar andelar i procent som summerar till hundra. Lokala partier
    behåller sin andel av utgångsläget, och normaliseringen fördelar
    skillnaden på de partier som faktiskt rör sig.
    """
    total = sum(forra.values())
    if total <= 0:
        return {}

    andelar = {p: v / total * 100 for p, v in forra.items()}
    skalat = {}
    for parti, andel in andelar.items():
        if parti == LOKALT:
            # Hålls konstant, se modulens dokumentation.
            skalat[parti] = andel if lokala_konstanta else andel
        else:
            skalat[parti] = andel * trend.get(parti, 1.0)

    summa = sum(skalat.values())
    if summa <= 0:
        return {}
    return {p: v / summa * 100 for p, v in skalat.items()}


def prognos(riksprognos: dict[str, float], niva: str = "kommun",
            ar: str = FORRA_LOKALVALET,
            referens: dict[str, float] | None = None) -> dict[str, dict]:
    """Bygger prognos per område för angiven nivå.

    `niva` är "kommun" eller "fylke". Returnerar en dict per område med
    andelar, mandat och församlingens storlek.
    """
    trend = rikstrend(riksprognos, referens)

    if niva == "fylke":
        roster = ssb.aggregera_till_fylke(ssb.hamta_fylkesval(ar))
        storlekar = fylkesting_storlek()
    elif niva == "kommun":
        roster = ssb.hamta_kommunval(ar)
        # Faktiskt antal platser, inte en skattning: se
        # ssb.hamta_kommunestyre_storlek.
        try:
            storlekar = ssb.hamta_kommunestyre_storlek(ar)
        except Exception as fel:
            print(f"  Kunde inte hämta kommunestyrestorlekar ({fel}), "
                  f"skattar dem i stället.")
            storlekar = {}
    else:
        raise ValueError(f"Okänd nivå {niva!r}, välj kommun eller fylke.")

    ut = {}
    for omrade, forra in roster.items():
        andelar = skala_omrade(forra, trend)
        if not andelar:
            continue
        platser = (storlekar.get(omrade)
                   or storlekar.get(ssb.normalisera(omrade))
                   or kommunestyre_storlek(sum(forra.values())))
        mandat = sainte_lague(andelar, platser)
        ut[omrade] = {
            "andelar": andelar,
            "mandat": mandat,
            "platser": platser,
            "forra_andelar": {p: v / sum(forra.values()) * 100
                              for p, v in forra.items()},
            "roster_forra": sum(forra.values()),
        }
    return ut


# Kommunestyrets minsta storlek enligt kommuneloven § 5-5, efter
# invånarantal. Kommunen får välja fler platser, och många gör det, så detta
# är ett golv och inte det faktiska antalet.
#
# Röstetalet används som ombud för invånarantalet, eftersom det finns i samma
# datakälla. Ungefär tre av fyra röstberättigade röstar, och ungefär tre av
# fyra invånare är röstberättigade, så röstetalet är grovt räknat halva
# invånarantalet.
LAGSTA_PLATSER = [
    (5_000, 11),
    (10_000, 19),
    (50_000, 27),
    (100_000, 35),
    (float("inf"), 43),
]


def kommunestyre_storlek(roster: float) -> int:
    """Skattar kommunestyrets storlek ur röstetalet.

    Reservlösning. Det faktiska antalet hämtas från SSB tabell 04813, se
    ssb.hamta_kommunestyre_storlek, och används när det finns. Skattningen
    här träffade i genomsnitt 4,3 platser fel mot de faktiska siffrorna, med
    en systematisk underskattning på 3,6 platser, så den används bara när
    hämtningen fallerar.
    """
    invanare = roster * 2
    for grans, platser in LAGSTA_PLATSER:
        if invanare < grans:
            # Påslag på lagens golv: medianen bland norska kommuner ligger
            # några platser över minimum.
            return platser + 4
    return 43


def fylkesting_storlek() -> dict[str, int]:
    """Antal platser per fylkesting efter valet 2023.

    Källa: fylkeskommunernas egna uppgifter. Siffrorna gäller mandatperioden
    2023 till 2027 och kan ändras inför 2027, eftersom fylkestinget självt
    beslutar sin storlek inom lagens ram.
    """
    return {
        "Akershus": 45, "Buskerud": 43, "Østfold": 41, "Innlandet": 57,
        "Vestfold": 39, "Telemark": 41, "Agder": 49, "Rogaland": 47,
        "Vestland": 65, "Møre og Romsdal": 47, "Trøndelag": 59,
        "Nordland": 45, "Troms": 41, "Finnmark": 35,
    }


# --- Verifiering -------------------------------------------------------------

def _verifiera() -> int:
    """Backtest: 2019 skalat med faktisk rikstrend, jämfört med utfall 2023.

    Rikstrenden mellan lokalvalen 2019 och 2023 tas från stortingsvalen 2017
    och 2021, alltså de val som låg närmast före respektive lokalval. Det
    speglar hur modellen faktiskt används: rikstrenden är känd, lokalvalets
    utfall är det som ska förutsägas.
    """
    import statistics

    print("=" * 66)
    print("  BACKTEST: LOKALVALET 2019 SKALAT TILL 2023")
    print("=" * 66)
    print("\nRikstrenden är riksopinionen vid valdagen 2023 delad med den vid")
    print("valdagen 2019, alltså den information som fanns då.\n")

    trend = rikstrend(OPINION_VID_LOKALVAL["2023"],
                      OPINION_VID_LOKALVAL["2019"])
    print("Rikstrend, opinion 2019 till 2023:")
    print("  " + "  ".join(f"{p} {trend[p]:.2f}" for p in cfg.PARTIER))

    totalt_fel = 0
    for niva, hamta in (("fylke", None), ("kommun", None)):
        if niva == "fylke":
            forra = ssb.aggregera_till_fylke(ssb.hamta_fylkesval("2019"))
            utfall = ssb.aggregera_till_fylke(ssb.hamta_fylkesval("2023"))
        else:
            forra = ssb.hamta_kommunval("2019")
            utfall = ssb.hamta_kommunval("2023")

        # Områdena matchas på normaliserat namn: 2019-data bär suffix som
        # "(2020-2023)" som inte finns i 2023-data.
        forra = {ssb.normalisera(k): v for k, v in forra.items()}
        utfall = {ssb.normalisera(k): v for k, v in utfall.items()}

        fel_per_omrade = []
        for omrade, bas in forra.items():
            if omrade not in utfall:
                continue
            prognosen = skala_omrade(bas, trend)
            faktiskt_total = sum(utfall[omrade].values())
            if faktiskt_total <= 0 or not prognosen:
                continue
            faktiskt = {p: v / faktiskt_total * 100
                        for p, v in utfall[omrade].items()}
            fel = [abs(prognosen.get(p, 0.0) - faktiskt.get(p, 0.0))
                   for p in set(prognosen) | set(faktiskt)]
            fel_per_omrade.append(statistics.mean(fel))

        if not fel_per_omrade:
            continue
        mae = statistics.mean(fel_per_omrade)
        totalt_fel += mae
        print(f"\n{niva.upper()}: {len(fel_per_omrade)} områden")
        print(f"  Medelabsolutfel per parti: {mae:.2f} procentenheter")
        print(f"  Median: {statistics.median(fel_per_omrade):.2f}, "
              f"värsta område: {max(fel_per_omrade):.2f}")

        # Jämförelse: hur bra hade man klarat sig med att bara behålla 2019?
        naiv = []
        for omrade, bas in forra.items():
            if omrade not in utfall:
                continue
            bas_total, faktiskt_total = sum(bas.values()), sum(utfall[omrade].values())
            if bas_total <= 0 or faktiskt_total <= 0:
                continue
            b = {p: v / bas_total * 100 for p, v in bas.items()}
            f = {p: v / faktiskt_total * 100 for p, v in utfall[omrade].items()}
            naiv.append(statistics.mean(
                [abs(b.get(p, 0.0) - f.get(p, 0.0)) for p in set(b) | set(f)]))
        print(f"  Utan skalning, bara 2019 rakt av: "
              f"{statistics.mean(naiv):.2f} procentenheter")
        if statistics.mean(naiv) < mae:
            print("  VARNING: skalningen försämrar mot att inte göra något.")

    print()
    return 0


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Prognos för fylkestings- och kommunestyrevalget 2027")
    ap.add_argument("--referens", metavar="ÅÅÅÅ",
                    help="Räkna om riksopinionen vid ett lokalvalsår, "
                         "t.ex. --referens 2023")
    args = ap.parse_args()

    if args.referens:
        valdagar = {"2019": "2019-09-09", "2023": "2023-09-11"}
        valdag = valdagar.get(args.referens)
        if not valdag:
            raise SystemExit(f"Okänt lokalvalsår {args.referens!r}, "
                             f"välj {' eller '.join(valdagar)}.")
        raknat = opinion_vid(valdag)
        lagrat = OPINION_VID_LOKALVAL.get(args.referens, {})
        print(f"Riksopinion vid {valdag}:")
        for parti in cfg.PARTIER:
            gammalt = lagrat.get(parti)
            avvikelse = ("" if gammalt is None
                         else f"   lagrat {gammalt}"
                              f"{'' if abs(gammalt - raknat[parti]) < 0.05 else '  AVVIKER'}")
            print(f"  {parti:5}{raknat[parti]:6.1f}{avvikelse}")
        return 0

    return _verifiera()


if __name__ == "__main__":
    raise SystemExit(main())
