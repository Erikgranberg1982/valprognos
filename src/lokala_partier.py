"""Namngivna lokala partier med egna mätningar.

SCB redovisar alla lokala partier samlat som ÖVRIGA, vilket gör att ett enskilt
parti inte kan följas. För de partier där det finns en publicerad mätning kan
posten i stället delas upp, så att partiet syns med namn och sitt aktuella stöd.

Källan är data/lokala_partier.csv. Ett parti kan ha mätning på en nivå men inte
på en annan. Då skalas stödet mellan nivåerna med samma förhållande som partiet
hade mellan nivåerna i förra valet, vilket är den bästa tillgängliga
uppskattningen när mätningar saknas.

Riksdagsvalet är ett särfall. Ett parti kommer in i riksdagen antingen med fyra
procent i hela landet eller med tolv procent i en enskild valkrets. Den andra
vägen är i praktiken den enda möjliga för ett lokalt parti, och den redovisas
därför separat.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import numpy as np
import pandas as pd

import config as cfg

ROT = Path(__file__).resolve().parent.parent


# Valkretsens spärr för att nå riksdagen utan att klara fyraprocentsspärren.
VALKRETS_SPARR = cfg.VALKRETS_SPARR * 100

# Hur mycket av sitt kommunvalsstöd ett lokalt parti behåller på andra nivåer.
# Skattat från samtliga kommuner med minst tre procent ÖVRIGA i kommunvalet
# 2018 och 2022. Väljare som röstar lokalt i kommunvalet röstar oftast på ett
# riksdagsparti när de väljer riksdag, vilket gör tappet dramatiskt. Används i
# metodbeskrivningen på sidan.
NIVAKVOT = {
    "kommun": 1.00,
    "region": 0.66,
    "riksdagsvalkrets": 0.19,
}


def las_matningar() -> pd.DataFrame:
    """Läser lokala mätningar med samtliga publicerade partisiffror.

    En lokal mätning mäter hela partifältet i sitt område, inte bara det lokala
    partiet. Alla partier som redovisats i mätningen ska därför vägas mot
    modellens skattning, inte bara det namngivna lokala partiet.

    Partier som inte publicerats lämnas tomma i CSV-filen och behåller
    modellens egen skattning.
    """
    fil = ROT / "data" / "lokala_matningar.csv"
    if not fil.exists():
        return pd.DataFrame()

    rader = []
    with open(fil, encoding="utf-8") as f:
        for rad in csv.DictReader(f):
            niva = (rad.get("niva") or "").strip()
            kod = (rad.get("omrade_kod") or "").strip()
            if not niva or not kod:
                continue

            def tal(nyckel):
                text = (rad.get(nyckel) or "").strip().replace(",", ".")
                try:
                    return float(text)
                except ValueError:
                    return np.nan

            post = {
                "id": (rad.get("id") or "").strip(),
                "niva": niva,
                "omrade_kod": kod,
                "omrade_namn": (rad.get("omrade_namn") or "").strip(),
                "institut": (rad.get("institut") or "").strip(),
                "uppdragsgivare": (rad.get("uppdragsgivare") or "").strip(),
                "urval": int(tal("urval")) if np.isfinite(tal("urval")) else None,
                "datum": (rad.get("datum") or "").strip(),
                "lokalt_parti": (rad.get("lokalt_parti") or "").strip() or None,
                "lokalt_stod": tal("lokalt_stod"),
                "kalla": (rad.get("kalla") or "").strip(),
                "kommentar": (rad.get("kommentar") or "").strip(),
            }
            for parti in cfg.PARTIER:
                post[parti] = tal(parti)
            rader.append(post)

    return pd.DataFrame(rader)


def matning_for_omrade(niva: str, omrade_kod: str) -> dict | None:
    """Den lokala mätning som gäller ett område, om den är fullständig.

    En mätning används bara om samtliga riksdagspartier har en publicerad
    siffra. En ofullständig mätning kan inte vägas in konsekvent: att justera
    några partier mot mätningen och låta resten stå kvar på modellens skattning
    ger en fördelning som varken speglar mätningen eller modellen, och
    normaliseringen flyttar då felet till de partier som inte mättes.

    Mätningar som saknar partier läses in ändå, med anvands satt till False, så
    att de kan redovisas på sidan tillsammans med skälet.
    """
    tabell = las_matningar()
    if tabell.empty:
        return None

    traff = tabell[(tabell["niva"] == niva) &
                   (tabell["omrade_kod"].astype(str).str.upper()
                    == str(omrade_kod).upper())]
    if traff.empty:
        return None

    # Nyaste mätningen gäller. Filordningen är inte kronologisk, och ett område
    # kan ha mätts flera gånger: Göteborg har både Indikator i april och Novus
    # i september.
    if "datum" in traff.columns:
        traff = traff.sort_values("datum", ascending=False)
    rad = traff.iloc[0]
    return beskriv_matning(rad)


def beskriv_matning(rad) -> dict:
    """Beskriver en enskild mätningsrad.

    Ett område kan ha mätts flera gånger. Sidan redovisar alla mätningar,
    medan prognosen bara använder den nyaste, så tolkningen av en rad måste gå
    att göra oberoende av vilken som gäller.
    """
    partier = {p: float(rad[p]) for p in cfg.PARTIER if np.isfinite(rad[p])}
    saknade = [p for p in cfg.PARTIER if p not in partier]
    fullstandig = not saknade

    return {
        "id": rad["id"],
        "niva": rad["niva"],
        "omrade_kod": rad["omrade_kod"],
        "omrade_namn": rad["omrade_namn"],
        "institut": rad["institut"],
        "uppdragsgivare": rad["uppdragsgivare"],
        "urval": rad["urval"],
        "datum": rad["datum"],
        "vikt": vikt_for_matning(rad["datum"], rad["urval"]),
        "partier": partier,
        "saknade": saknade,
        "fullstandig": fullstandig,
        "anvands": fullstandig,
        "lokalt_parti": rad["lokalt_parti"],
        "lokalt_stod": (float(rad["lokalt_stod"])
                        if np.isfinite(rad["lokalt_stod"]) else None),
        "kalla": rad["kalla"],
        "kommentar": rad["kommentar"],
    }


def vikt_for_matning(datum_text: str | None, urval: int | None = None) -> float:
    """Hur tungt en lokal mätning ska väga mot modellens egen skattning.

    Riksmätningar tappar halva sin vikt var tjugoförsta dag, eftersom det alltid
    finns en färskare mätning av samma sak. För en lokal mätning är alternativet
    inte en nyare mätning utan en extrapolering från rikstrenden, som inte vet
    något om just det området. En äldre lokal mätning är därför fortfarande
    bättre underlag än ingen alls, och avklingningen är satt till 120 dagar.

    Vikten toppar vid LOKAL_MATNING_MAXVIKT, under ett, eftersom även en färsk
    mätning har urvalsosäkerhet och modellens skattning bär information om vad
    som hänt nationellt sedan mätningen gjordes.

    Urvalsstorleken justerar vikten på samma sätt som för riksmätningar, med
    kvadratroten mot ett referensurval på tusen svarande, vilket är typiskt för
    en lokal mätning.
    """
    from datetime import date

    vikt = cfg.LOKAL_MATNING_MAXVIKT

    if datum_text:
        try:
            matdatum = date.fromisoformat(str(datum_text).strip()[:10])
            alder = max(0, (date.today() - matdatum).days)
            vikt *= 0.5 ** (alder / cfg.LOKAL_MATNING_HALVERINGSTID)
        except ValueError:
            pass

    if urval and urval > 0:
        # Dämpad urvalsjustering: en dubbelt så stor mätning väger cirka
        # fyrtio procent mer, inte dubbelt.
        vikt *= min(1.3, (urval / 1000.0) ** 0.5)

    return max(0.0, min(1.0, vikt))


def blanda_in_matning(stod: dict[str, float], niva: str,
                      omrade_kod: str) -> tuple[dict[str, float], dict | None]:
    """Väger in en lokal mätning i ett områdes prognos.

    Metoden följer samma princip som SCB:s partisympatiundersökning i
    regionmodellen: mätningen och modellens skattning vägs samman partivis och
    resultatet normaliseras, i stället för att enskilda partier skrivs över.
    Skillnaden är vikten, som är betydligt högre här eftersom en lokal mätning
    gäller exakt det område den används på, medan partisympatiundersökningen är
    indelad i tio grova landsdelar.

    Mätningen används bara om den är fullständig, se matning_for_omrade.
    Returnerar det justerade stödet och mätningen, eller ursprungligt stöd och
    None om ingen användbar mätning finns.
    """
    matning = matning_for_omrade(niva, omrade_kod)
    if matning is None or not matning["anvands"]:
        return stod, matning

    vikt = matning["vikt"]
    ut = dict(stod)

    # Riksdagspartierna vägs mot sina uppmätta värden.
    for parti, matt in matning["partier"].items():
        if parti in ut:
            ut[parti] = (1.0 - vikt) * ut[parti] + vikt * matt

    # Det lokala partiet vägs mot ÖVRIGA, som är modellens skattning för det.
    lokalt = matning["lokalt_parti"]
    if lokalt and matning["lokalt_stod"] is not None:
        bas = ut.get("ÖVRIGA", 0.0)
        vagt = (1.0 - vikt) * bas + vikt * matning["lokalt_stod"]
        ut[lokalt] = vagt
        ut["ÖVRIGA"] = max(0.0, bas - vagt)

    # Normalisera till hundra procent.
    summa = sum(v for v in ut.values() if v > 0)
    if summa > 0:
        ut = {k: max(0.0, v) / summa * 100.0 for k, v in ut.items()}

    return ut, matning


if __name__ == "__main__":
    tabell = las_matningar()
    print(f"{len(tabell)} lokala mätningar i data/lokala_matningar.csv\n")
    for _, rad in tabell.iterrows():
        m = matning_for_omrade(rad["niva"], rad["omrade_kod"])
        if not m:
            continue
        status = (f"används, vikt {m['vikt']*100:.0f} procent" if m["anvands"]
                  else f"används inte, saknar {', '.join(m['saknade'])}")
        print(f"  {m['institut']} för {m['uppdragsgivare']}, "
              f"{rad['omrade_namn']} ({rad['niva']}): {status}")
        if m["partier"]:
            print("    " + "  ".join(f"{p} {v:.1f}"
                                     for p, v in m["partier"].items()))
        if m["lokalt_parti"]:
            print(f"    {m['lokalt_parti']} {m['lokalt_stod']:.1f}")
