"""Koalitioner som faktiskt styr i kommuner och regioner.

Vänster mot höger är för grovt på lokal nivå. Efter valet 2022 hade 99 av 290
kommuner ett blocköverskridande styre, vilket är det enskilt vanligaste
mönstret, och SCB räknar 84 olika partikonstellationer bland kommunerna.

Modulen läser de vanligaste koalitionerna från data/lokala_koalitioner.csv och
räknar ut om var och en når egen majoritet i ett område. Antalet kommuner och
regioner där koalitionen faktiskt styr 2022 till 2026 tas med, så att det går
att se hur vanlig konstellationen är i verkligheten.

Källa för styrena: SCB:s tabeller ME0002KnP01 och ME0002LanP01.
"""
from __future__ import annotations

import csv
from pathlib import Path

import config as cfg

ROT = Path(__file__).resolve().parent.parent
FIL = ROT / "data" / "lokala_koalitioner.csv"


def las() -> list[dict]:
    """Läser koalitionstabellen.

    Partierna anges som M+KD+L+C i CSV-filen och delas upp här. Partier som
    inte finns i konfigurationen ignoreras, så att filen tål stavfel utan att
    hela prognosen faller.
    """
    if not FIL.exists():
        return []

    ut = []
    with open(FIL, encoding="utf-8") as f:
        for rad in csv.DictReader(f):
            namn = (rad.get("namn") or "").strip()
            partitext = (rad.get("partier") or "").strip()
            if not namn or not partitext:
                continue

            partier = [p.strip() for p in partitext.split("+") if p.strip()]
            giltiga = [p for p in partier if p in cfg.PARTIER]
            if not giltiga:
                continue

            def heltal(nyckel):
                try:
                    return int((rad.get(nyckel) or "0").strip())
                except ValueError:
                    return 0

            ut.append({
                "id": (rad.get("id") or namn.lower()).strip(),
                "namn": namn,
                "partier": giltiga,
                "kommuner_2022": heltal("kommuner_2022"),
                "regioner_2022": heltal("regioner_2022"),
                "kommentar": (rad.get("kommentar") or "").strip(),
            })
    return ut


# Grupper som används för att beskriva mandatläget lokalt. C hålls utanför båda,
# eftersom partiet lokalt oftare styr med de borgerliga än med vänstern: efter
# valet 2022 ingick C i 135 kommunstyren, varav 55 med borgerliga, 48 med båda
# sidorna och bara 32 med vänstern. Att räkna C till något block ger därför en
# missvisande bild.
VANSTER = ["V", "S", "MP"]
BORGERLIGA = ["M", "KD", "L"]


def beskriv_lage(mandat: dict[str, int], totalt: int) -> dict:
    """Beskriver mandatläget i ett område utan att gissa vilket styre som bildas.

    Den tidigare etiketten sa vänster- eller högermajoritet utifrån
    riksdagsvalets blockindelning, där C räknas som vänster. Lokalt blev det
    missvisande: modellen angav vänstermajoritet i 57 procent av kommunerna
    medan faktiskt vänsterstyre efter valet 2022 var 20 procent. Etiketten mätte
    aritmetik men lästes som en förutsägelse om styret.

    I stället beskrivs vad som faktiskt går att säga: om en sida når majoritet på
    egen hand, om den behöver C, eller om ingen kombination räcker. Vilket styre
    som sedan bildas avgörs av förhandlingar som ingen modell kan förutse.
    """
    if totalt <= 0:
        return {"lage": "okant", "text": "Okänt", "beskrivning": ""}

    majoritet = totalt // 2 + 1
    v = sum(int(mandat.get(p, 0)) for p in VANSTER)
    b = sum(int(mandat.get(p, 0)) for p in BORGERLIGA)
    c = int(mandat.get("C", 0))
    sd = int(mandat.get("SD", 0))
    ovriga = totalt - v - b - c - sd

    if v >= majoritet:
        lage, text = "vanster", "V+S+MP i majoritet"
        beskrivning = "Vänsterpartierna når majoritet utan C."
    elif b + sd >= majoritet and b + c >= majoritet:
        lage, text = "hoger_flera", "Högern har flera vägar"
        beskrivning = ("De borgerliga når majoritet både med C och med SD, "
                       "och kan välja.")
    elif b + c >= majoritet:
        lage, text = "borgerlig_c", "Borgerliga med C"
        beskrivning = "M, KD och L når majoritet om C ingår."
    elif b + sd >= majoritet:
        lage, text = "hoger_sd", "Borgerliga med SD"
        beskrivning = "M, KD och L når majoritet med stöd av SD."
    elif v + c >= majoritet:
        lage, text = "vanster_c", "Vänstern med C"
        beskrivning = "V, S och MP når majoritet om C ingår."
    elif ovriga > 0 and max(v, b) + ovriga >= majoritet:
        lage, text = "lokala_vagmastare", "Lokala partier avgör"
        beskrivning = ("Ingen sida når majoritet utan stöd av lokala partier, "
                       f"som har {ovriga} mandat.")
    else:
        lage, text = "oklart", "Oklart läge"
        beskrivning = ("Ingen av de vanliga kombinationerna når majoritet. "
                       "Styret kräver en bredare lösning.")

    return {
        "lage": lage,
        "text": text,
        "beskrivning": beskrivning,
        "vanster": v,
        "borgerliga": b,
        "c": c,
        "sd": sd,
        "ovriga": ovriga,
        "majoritet": majoritet,
    }


def utfall_for_omrade(mandat: dict[str, int], totalt: int,
                      koalitioner: list[dict] | None = None) -> list[dict]:
    """Räknar ut vilka koalitioner som når majoritet i ett område.

    mandat är antal mandat per parti, totalt är fullmäktiges storlek. Resultatet
    sorteras med de koalitioner som når majoritet först, och därefter efter hur
    nära de ligger.
    """
    if koalitioner is None:
        koalitioner = las()
    if not koalitioner or totalt <= 0:
        return []

    majoritet = totalt // 2 + 1

    ut = []
    for koalition in koalitioner:
        summa = sum(int(mandat.get(p, 0)) for p in koalition["partier"])
        ut.append({
            "id": koalition["id"],
            "namn": koalition["namn"],
            "partier": "+".join(koalition["partier"]),
            "mandat": summa,
            "majoritet": majoritet,
            "har_majoritet": summa >= majoritet,
            "avstand": summa - majoritet,
            "kommuner_2022": koalition["kommuner_2022"],
            "regioner_2022": koalition["regioner_2022"],
            "kommentar": koalition["kommentar"],
        })

    ut.sort(key=lambda x: (-x["har_majoritet"], -x["avstand"]))
    return ut


if __name__ == "__main__":
    koalitioner = las()
    print(f"{len(koalitioner)} koalitioner i data/lokala_koalitioner.csv\n")
    for k in koalitioner:
        print(f"  {k['namn']:16s} {'+'.join(k['partier']):14s} "
              f"{k['kommuner_2022']:3d} kommuner, {k['regioner_2022']:2d} regioner")

    # Exempel: Örebro kommun 2026 enligt prognosen.
    import prognos as hp
    import kommunmodell as km
    from datetime import date

    df = hp.las_matningar(hp.ROT / "data" / "matningar.csv")
    res = hp.kor_prognos(df, df["datum"].max().date(),
                         date.fromisoformat(cfg.VALDAG))
    sammanfattning = km.sammanfatta(km.prognos_per_kommun(res["snitt"]))
    rad = sammanfattning.loc["1880"]

    mandat = {p: int(rad[f"mandat_{p}"]) for p in cfg.PARTIER}
    print(f"\nÖrebro, {int(rad['mandat_totalt'])} mandat:")
    for post in utfall_for_omrade(mandat, int(rad["mandat_totalt"])):
        marke = "JA " if post["har_majoritet"] else "nej"
        print(f"  {marke} {post['namn']:16s} {post['mandat']:3d} mandat "
              f"({post['avstand']:+d} mot majoritet)")
