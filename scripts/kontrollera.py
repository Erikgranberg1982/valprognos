#!/usr/bin/env python3
"""Kontrollerar att ett bygge gav rimligt resultat innan det publiceras.

Scrapern bygger på Wikipedias tabellstruktur, som kan ändras utan förvarning.
Utan den här kontrollen skulle ett trasigt bygge publiceras tyst. Skriptet
avslutar med felkod om något ser fel ut, vilket stoppar publiceringen.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROT = Path(__file__).resolve().parent.parent
PARTIER = ["V", "S", "MP", "C", "L", "M", "KD", "SD"]

# Rimlighetsintervall per parti, satta brett så att verkliga opinionssvängningar
# släpps igenom men uppenbara parsningsfel fångas.
RIMLIGT = {
    "V": (2.0, 20.0), "S": (15.0, 50.0), "MP": (1.0, 20.0), "C": (1.0, 20.0),
    "L": (0.5, 15.0), "M": (8.0, 35.0), "KD": (1.0, 20.0), "SD": (8.0, 35.0),
}

MINSTA_ANTAL_MATNINGAR = 20
MINSTA_ANTAL_INSTITUT = 3


def fel(text: str) -> None:
    print(f"FEL: {text}")
    sys.exit(1)


def main() -> None:
    matningar = ROT / "data" / "matningar.csv"
    sida = ROT / "output" / "prognos.html"
    kommuner = ROT / "output" / "kommuner.json"

    if not matningar.exists():
        fel("data/matningar.csv saknas, scrapern har inte körts.")
    if not sida.exists():
        fel("output/prognos.html saknas, dashboarden byggdes inte.")

    df = pd.read_csv(matningar)
    df["datum"] = pd.to_datetime(df["datum"])

    if len(df) < MINSTA_ANTAL_MATNINGAR:
        fel(f"Bara {len(df)} mätningar, förväntade minst {MINSTA_ANTAL_MATNINGAR}. "
            "Wikipedias tabellstruktur kan ha ändrats.")

    institut = df["institut"].nunique()
    if institut < MINSTA_ANTAL_INSTITUT:
        fel(f"Bara {institut} institut, förväntade minst {MINSTA_ANTAL_INSTITUT}.")

    saknade = [p for p in PARTIER if p not in df.columns]
    if saknade:
        fel(f"Kolumner saknas för: {', '.join(saknade)}")

    # Summan av partierna ska ligga nära hundra procent. Övriga partier ligger
    # utanför, så drygt nittiofem procent är normalt.
    summa = df[PARTIER].sum(axis=1)
    if summa.median() < 90 or summa.median() > 102:
        fel(f"Partisummans median är {summa.median():.1f}, vilket är orimligt.")

    # Senaste mätningen får inte vara för gammal, annars har hämtningen
    # tystnat utan att fela.
    alder = (pd.Timestamp.now() - df["datum"].max()).days
    if alder > 120:
        fel(f"Senaste mätningen är {alder} dagar gammal. Hämtningen kan ha slutat "
            "fungera.")

    # Prognosens nivåer ska vara rimliga.
    sys.path.insert(0, str(ROT / "src"))
    import config as cfg
    import prognos as huvud

    referens = min(df["datum"].max().date(), pd.Timestamp.now().date())
    from datetime import date
    res = huvud.kor_prognos(huvud.las_matningar(matningar), referens,
                            date.fromisoformat(cfg.VALDAG))
    snitt = res["snitt"]

    for parti, (lag, hog) in RIMLIGT.items():
        if parti not in snitt.index:
            fel(f"{parti} saknas i prognosen.")
        if not (lag <= snitt[parti] <= hog):
            fel(f"{parti} prognosticeras till {snitt[parti]:.1f} procent, "
                f"utanför det rimliga intervallet {lag}-{hog}.")

    total = snitt.sum()
    if abs(total - 100) > 0.5:
        fel(f"Prognosen summerar till {total:.2f} procent i stället för 100.")

    storlek_kb = sida.stat().st_size / 1024
    if storlek_kb < 40:
        fel(f"Sidan är bara {storlek_kb:.0f} kB, vilket antyder ett trasigt bygge.")

    # Kommundata ligger komprimerad i sidan. Saknas den fungerar kommunvyn inte.
    html = sida.read_text(encoding="utf-8")
    if "kommun_gz" not in html:
        fel("Kommundata saknas i sidan, kommunvyn skulle bli tom.")
    if "Så beräknas region och kommun" not in html:
        fel("Metodavsnittet för region och kommun saknas i sidan.")

    print(f"Kontroll godkänd: {len(df)} mätningar från {institut} institut, "
          f"senaste {df['datum'].max().date()}.")
    print(f"  Prognos: " + ", ".join(f"{p} {snitt[p]:.1f}" for p in PARTIER))
    print(f"  Sida {storlek_kb:.0f} kB" +
          (f", kommundata {kommuner.stat().st_size / 1024:.0f} kB"
           if kommuner.exists() else ", ingen kommundata"))


if __name__ == "__main__":
    main()
