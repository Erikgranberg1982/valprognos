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
FIL = ROT / "data" / "lokala_partier.csv"

# Valkretsens spärr för att nå riksdagen utan att klara fyraprocentsspärren.
VALKRETS_SPARR = cfg.VALKRETS_SPARR * 100


def las() -> pd.DataFrame:
    """Läser tabellen över lokala partier.

    Tomma värden i stod och forra_valet tolkas som saknade, inte som nollor.
    """
    if not FIL.exists():
        return pd.DataFrame(columns=["parti", "niva", "omrade_kod", "omrade_namn",
                                     "stod", "forra_valet", "kalla", "datum",
                                     "kommentar"])
    rader = []
    with open(FIL, encoding="utf-8") as f:
        for rad in csv.DictReader(f):
            parti = (rad.get("parti") or "").strip()
            niva = (rad.get("niva") or "").strip()
            if not parti or not niva:
                continue

            def tal(nyckel):
                text = (rad.get(nyckel) or "").strip().replace(",", ".")
                try:
                    return float(text)
                except ValueError:
                    return np.nan

            rader.append({
                "parti": parti,
                "niva": niva,
                "omrade_kod": (rad.get("omrade_kod") or "").strip(),
                "omrade_namn": (rad.get("omrade_namn") or "").strip(),
                "stod": tal("stod"),
                "forra_valet": tal("forra_valet"),
                "kalla": (rad.get("kalla") or "").strip(),
                "datum": (rad.get("datum") or "").strip(),
                "kommentar": (rad.get("kommentar") or "").strip(),
            })
    return pd.DataFrame(rader)


# Hur mycket av sitt kommunvalsstöd ett lokalt parti behåller på andra nivåer.
# Skattat från samtliga kommuner med minst tre procent ÖVRIGA i kommunvalet
# 2018 och 2022. Väljare som röstar lokalt i kommunvalet röstar oftast på ett
# riksdagsparti när de väljer riksdag, vilket gör tappet dramatiskt.
NIVAKVOT = {
    "kommun": 1.00,
    "region": 0.66,      # Regionvalet ligger nära kommunvalet.
    "riksdagsvalkrets": 0.19,  # Medianen är 0,156 och medelvärdet 0,194.
}


def _kallrad(tabell: pd.DataFrame, parti: str):
    """Raden med den faktiska mätningen för ett parti, om någon finns."""
    egna = tabell[(tabell["parti"] == parti) & tabell["stod"].notna()]
    return egna.iloc[0] if not egna.empty else None


def _urval(kalltext: str | None) -> int | None:
    """Plockar ut antalet svarande ur källtexten, t.ex. "(1000 svarande)"."""
    if not kalltext:
        return None
    m = re.search(r"(\d[\d\s]{2,6})\s*(?:svarande|intervjuer|personer)",
                  str(kalltext), re.IGNORECASE)
    if not m:
        return None
    try:
        return int(m.group(1).replace(" ", ""))
    except ValueError:
        return None


def _skala_mellan_nivaer(tabell: pd.DataFrame, parti: str, niva: str,
                         ovriga_kvot: float | None = None) -> float | None:
    """Skattar stödet på en nivå utifrån en mätning på en annan.

    Om partiet har en mätning på nivån används den. Annars skalas stödet från
    den nivå som har en mätning, i första hand med partiets eget förhållande
    mellan nivåerna i förra valet, i andra hand med den empiriska nivåkvoten.

    Skalningen till riksdagsvalet är den mest osäkra: ett lokalt parti behåller
    typiskt bara en femtedel av sitt kommunvalsstöd när samma väljare röstar
    till riksdagen.
    """
    egna = tabell[tabell["parti"] == parti]
    mal = egna[egna["niva"] == niva]
    if not mal.empty and np.isfinite(mal.iloc[0]["stod"]):
        return float(mal.iloc[0]["stod"])

    # Hitta en nivå med mätning att skala från.
    kalla = egna[egna["stod"].notna() & np.isfinite(egna["stod"])]
    if kalla.empty:
        return None
    kallrad = kalla.iloc[0]

    forra_kalla = kallrad["forra_valet"]
    forra_mal = mal.iloc[0]["forra_valet"] if not mal.empty else np.nan

    if np.isfinite(forra_kalla) and np.isfinite(forra_mal) and forra_kalla > 0:
        # Partiet växer eller krymper proportionellt på båda nivåerna.
        return float(kallrad["stod"] * forra_mal / forra_kalla)

    if ovriga_kvot is not None and np.isfinite(ovriga_kvot):
        return float(kallrad["stod"] * ovriga_kvot)

    # Fall tillbaka på den empiriska nivåkvoten, relativt källnivån.
    kvot_mal = NIVAKVOT.get(niva)
    kvot_kalla = NIVAKVOT.get(kallrad["niva"])
    if kvot_mal is not None and kvot_kalla:
        return float(kallrad["stod"] * kvot_mal / kvot_kalla)

    return None


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


def vagt_stod(matt_varde: float, modellens_skattning: float,
              vikt: float) -> float:
    """Väger samman en lokal mätning med modellens egen skattning."""
    v = max(0.0, min(1.0, vikt))
    return v * matt_varde + (1.0 - v) * modellens_skattning


def dela_upp_ovriga(stod_ovriga: float, parti_stod: float | None) -> tuple[float, float]:
    """Delar ÖVRIGA i det namngivna partiet och resterande lokala partier.

    Returnerar partiets stöd och det som blir kvar för övriga. Om partiet mäts
    högre än den ursprungliga ÖVRIGA-posten växer totalen, vilket är rimligt:
    partiet tar då röster från riksdagspartierna, inte bara från andra lokala.
    """
    if parti_stod is None or not np.isfinite(parti_stod):
        return 0.0, stod_ovriga
    rest = max(0.0, stod_ovriga - parti_stod)
    return parti_stod, rest


def for_omrade(niva: str, omrade_kod: str,
               ovriga_kvot: float | None = None) -> dict | None:
    """Returnerar det lokala partiet för ett område, om något finns.

    Resultatet innehåller partiets namn, skattat stöd, källa och om stödet är
    mätt eller skalat från en annan nivå.
    """
    tabell = las()
    if tabell.empty:
        return None

    trafffilter = ((tabell["niva"] == niva) &
                   (tabell["omrade_kod"].str.upper() == str(omrade_kod).upper()))
    rader = tabell[trafffilter]
    if rader.empty:
        return None

    rad = rader.iloc[0]
    parti = rad["parti"]
    matt = bool(np.isfinite(rad["stod"]))
    stod = (float(rad["stod"]) if matt
            else _skala_mellan_nivaer(tabell, parti, niva, ovriga_kvot))
    if stod is None:
        return None

    # Vikten gäller bara en mätt siffra. Ett skalat värde är redan härlett ur
    # en mätning på annan nivå och ärver den mätningens vikt.
    kallrad = rad if matt else _kallrad(tabell, parti)
    vikt = vikt_for_matning(
        (kallrad["datum"] if kallrad is not None else None),
        _urval(kallrad["kalla"] if kallrad is not None else None))

    return {
        "parti": parti,
        "stod": stod,
        "matt": matt,
        "vikt": vikt,
        "kalla": rad["kalla"] or None,
        "datum": rad["datum"] or None,
        "forra_valet": (float(rad["forra_valet"])
                        if np.isfinite(rad["forra_valet"]) else None),
        "kommentar": rad["kommentar"] or None,
    }


def riksdagschans(valkrets: str, stod_i_valkrets: float,
                  osakerhet: float = 2.5) -> dict | None:
    """Sannolikheten att ett lokalt parti når riksdagen via valkretsspärren.

    Ett parti som får tolv procent i en valkrets tar mandat där även utan att
    klara fyraprocentsspärren nationellt.

    Sannolikheten skattas med en normalfördelning kring det härledda stödet.
    Osäkerheten är satt brett eftersom kedjan är svag: det finns inga mätningar
    av riksdagsvalet i en enskild valkrets, så stödet härleds från en
    kommunmätning via en nivåkvot som varierar kraftigt mellan kommuner. Talet
    ska läsas som en storleksordning, inte som en precis sannolikhet.
    """
    from math import erf, sqrt

    if stod_i_valkrets is None or not np.isfinite(stod_i_valkrets):
        return None

    z = (stod_i_valkrets - VALKRETS_SPARR) / osakerhet
    sannolikhet = 0.5 * (1.0 + erf(z / sqrt(2.0)))

    return {
        "valkrets": valkrets,
        "stod": stod_i_valkrets,
        "sparr": VALKRETS_SPARR,
        "osakerhet": osakerhet,
        "sannolikhet": float(sannolikhet),
    }


if __name__ == "__main__":
    tabell = las()
    print(f"{len(tabell)} rader i data/lokala_partier.csv")
    if not tabell.empty:
        print(tabell[["parti", "niva", "omrade_namn", "stod", "forra_valet"]]
              .to_string(index=False))

    for niva, kod in [("kommun", "1880"), ("region", "18L")]:
        post = for_omrade(niva, kod)
        if post:
            hur = "mätt" if post["matt"] else "skalat från annan nivå"
            print(f"\n{niva} {kod}: {post['parti']} {post['stod']:.1f} % ({hur})")

    krets = for_omrade("riksdagsvalkrets", "VR22")
    if krets:
        chans = riksdagschans("Örebro läns valkrets", krets["stod"])
        if chans:
            print(f"\nRiksdagen via valkretsspärren: {krets['stod']:.1f} % mot "
                  f"{chans['sparr']:.0f} % krävs, sannolikhet "
                  f"{chans['sannolikhet']*100:.1f} %")
