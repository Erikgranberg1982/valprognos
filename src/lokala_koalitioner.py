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
