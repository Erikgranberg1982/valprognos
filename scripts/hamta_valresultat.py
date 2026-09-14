#!/usr/bin/env python3
"""Hämtar valresultatet 2026 från Valmyndigheten.

Resultatsajten läser JSON-filer under resultat.val.se/data/resultat/, en per
valtyp och område. Adresserna följer mönstret RD_P för riksdagen, RF_{län}_P
för regionfullmäktige och KF_{län}_{kommun}_P för kommunfullmäktige, där P
står för preliminärt och S för slutligt resultat.

    python3 scripts/hamta_valresultat.py
    python3 scripts/hamta_valresultat.py --slutligt
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import requests

ROT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROT / "src"))
import config as cfg  # noqa: E402

BAS = "https://resultat.val.se/data/resultat/val2026"
HEADERS = {"User-Agent": "svensk-valprediktor/0.1 (analysprojekt)"}

# Valmyndighetens partiförkortningar mot modellens.
PARTI = {"V": "V", "S": "S", "MP": "MP", "C": "C", "L": "L",
         "M": "M", "KD": "KD", "SD": "SD"}


def hamta(sokvag: str, forsok: int = 3) -> dict | None:
    for i in range(forsok):
        try:
            svar = requests.get(f"{BAS}/{sokvag}.json", headers=HEADERS,
                                timeout=30)
            if svar.status_code == 404:
                return None
            svar.raise_for_status()
            return svar.json()
        except requests.exceptions.RequestException:
            if i < forsok - 1:
                time.sleep(2 * (i + 1))
    return None


def _partirader(data: dict) -> tuple[dict, dict]:
    """Procent och mandat per parti ur en resultatfil."""
    procent, mandat = {}, {}
    for post in data.get("partiMandat", []):
        kod = PARTI.get(str(post.get("partiforkortning") or "").strip())
        if kod:
            mandat[kod] = int(post.get("antalMandat") or 0)
    # Röstandelarna ligger under partiroster i två grupper: partier som
    # deltar i mandatfördelningen och de som missat spärren.
    for grupp in ("rosterPaverkaMandat", "rosterEjPaverkaMandat"):
        block = data.get(grupp) or {}
        for post in block.get("partiroster", []):
            kod = PARTI.get(str(post.get("partiforkortning") or "").strip())
            if kod:
                try:
                    procent[kod] = float(post.get("andelRoster") or 0)
                except (TypeError, ValueError):
                    pass
    return procent, mandat


def main() -> None:
    ap = argparse.ArgumentParser(description="Hämta valresultat 2026")
    ap.add_argument("--slutligt", action="store_true",
                    help="Hämta slutligt resultat i stället för preliminärt")
    args = ap.parse_args()
    suffix = "S" if args.slutligt else "P"

    # --- Riksdagen -------------------------------------------------------
    rd = hamta(f"RD_{suffix}")
    if rd is None:
        sys.exit(f"FEL: riksdagsresultatet ({suffix}) finns inte än.")
    procent, mandat = _partirader(rd)
    status = (f"{'slutligt' if args.slutligt else 'preliminärt'}, "
              f"{rd.get('antalValdistriktRaknade')} av "
              f"{rd.get('antalValdistriktSomSkaRaknas')} valdistrikt")

    rader = [{"parti": p, "procent": procent.get(p, 0.0),
              "mandat": mandat.get(p, 0), "kalla": "Valmyndigheten",
              "status": status} for p in cfg.PARTIER]
    _skriv(ROT / "data" / "valresultat_2026.csv", rader)
    print(f"Riksdagen: {sum(r['mandat'] for r in rader)} mandat, {status}")

    # --- Regioner och kommuner -------------------------------------------
    lan = _lanskoder()
    reg, kom = [], []
    for lanskod, kommunkoder in sorted(lan.items()):
        data = hamta(f"RF_{lanskod}_{suffix}")
        if data:
            pr, ma = _partirader(data)
            for p in cfg.PARTIER:
                reg.append({"omrade_kod": lanskod,
                            "omrade_namn": data.get("namn", ""),
                            "parti": p, "procent": pr.get(p, 0.0),
                            "mandat": ma.get(p, 0)})
        for kkod in kommunkoder:
            kdata = hamta(f"KF_{lanskod}_{kkod}_{suffix}")
            if not kdata:
                continue
            pr, ma = _partirader(kdata)
            for p in cfg.PARTIER:
                kom.append({"omrade_kod": kkod,
                            "omrade_namn": kdata.get("namn", ""),
                            "parti": p, "procent": pr.get(p, 0.0),
                            "mandat": ma.get(p, 0)})
        print(f"  län {lanskod}: {len(kommunkoder)} kommuner", end="\r")

    _skriv(ROT / "data" / "valresultat_region_2026.csv", reg)
    _skriv(ROT / "data" / "valresultat_kommun_2026.csv", kom)
    print(f"\nRegioner: {len({r['omrade_kod'] for r in reg})}")
    print(f"Kommuner: {len({r['omrade_kod'] for r in kom})}")


def _lanskoder() -> dict[str, list[str]]:
    """Län och deras kommuner, ur kommunkoderna i kommundatan."""
    fil = ROT / "data" / "kommunstyren_2022.csv"
    ut: dict[str, list[str]] = {}
    with open(fil, encoding="utf-8") as f:
        for rad in csv.DictReader(f):
            kod = rad["kommunkod"].zfill(4)
            ut.setdefault(kod[:2], []).append(kod)
    return ut


def _skriv(vag: Path, rader: list[dict]) -> None:
    if not rader:
        return
    with open(vag, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rader[0]))
        w.writeheader()
        w.writerows(rader)


if __name__ == "__main__":
    main()
