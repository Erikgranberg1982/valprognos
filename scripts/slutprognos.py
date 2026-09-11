#!/usr/bin/env python3
"""Fryser prognosen inför valdagen, så att den går att utvärdera efteråt.

Skriver en tidsstämplad mapp under slutprognos/ med huvudprognosen, alla
scenarier och en jämförelsefil som fylls i när resultatet är känt. Poängen är
att låsa siffrorna innan utfallet finns: en prognos som skrivs om i efterhand
går inte att bedöma.

    python3 scripts/slutprognos.py
    python3 scripts/slutprognos.py --utvardera   # efter valet
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROT / "src"))

import config as cfg          # noqa: E402
import modell                 # noqa: E402
import prognos as _prognos    # noqa: E402
import scenarier              # noqa: E402
import pandas as pd           # noqa: E402
import numpy as np            # noqa: E402


def _sannolikhet_over_sparr(sim: dict, parti: str) -> float:
    i = sim["partier"].index(parti)
    return float(np.mean(sim["roster"][:, i] >= cfg.SPARRGRANS * 100))


def bygg() -> Path:
    df = _prognos.las_matningar(ROT / "data" / "matningar.csv")
    rader = pd.read_csv(ROT / "data" / "matningar.csv")
    rader["datum"] = pd.to_datetime(rader["datum"])

    ref = min(df["datum"].max().date(), date.today())
    res = _prognos.kor_prognos(df, ref, date.fromisoformat(cfg.VALDAG),
                               idag=date.today())
    snitt = res["snitt"]
    mandat = modell.fordela_mandat(dict(snitt))
    sm = res["sammanfattning"].set_index("parti")

    katalog = ROT / "slutprognos" / date.today().isoformat()
    katalog.mkdir(parents=True, exist_ok=True)

    # --- Huvudprognosen, ett parti per rad -------------------------------
    huvud = []
    for parti in cfg.PARTIER:
        huvud.append({
            "parti": parti,
            "stod": round(float(snitt[parti]), 2),
            "stod_p10": round(float(sm.at[parti, "p10"]), 2),
            "stod_p90": round(float(sm.at[parti, "p90"]), 2),
            "mandat": mandat[parti],
            "mandat_p10": int(sm.at[parti, "mandat_p10"]),
            "mandat_p90": int(sm.at[parti, "mandat_p90"]),
            "sannolikhet_over_sparr": round(
                _sannolikhet_over_sparr(res["sim"], parti), 4),
            "valresultat_2022": cfg.VALRESULTAT_2022[parti],
            "mandat_2022": cfg.MANDAT_2022[parti],
        })
    _skriv(katalog / "huvudprognos.csv", huvud)

    # --- Scenarierna, ett parti per rad och scenario ----------------------
    scen_rader = []
    for utfall in scenarier.kor_alla(snitt, rader, res["dagar_kvar"]):
        s = utfall["scenario"]
        for parti in cfg.PARTIER:
            scen_rader.append({
                "scenario": s.id,
                "scenario_namn": s.namn,
                "parti": parti,
                "stod": round(utfall["roster_nytt"].get(parti, 0.0), 2),
                "mandat": utfall["mandat_nytt"].get(parti, 0),
                "mandat_huvudprognos": utfall["mandat_bas"].get(parti, 0),
            })
        # Partier utanför de åtta, som Örebropartiet i valkretsscenariot.
        for parti, antal in utfall["mandat_nytt"].items():
            if parti not in cfg.PARTIER and antal:
                scen_rader.append({
                    "scenario": s.id, "scenario_namn": s.namn,
                    "parti": parti, "stod": "", "mandat": antal,
                    "mandat_huvudprognos": 0,
                })
    _skriv(katalog / "scenarier.csv", scen_rader)

    # --- Block och regeringsunderlag --------------------------------------
    block = []
    for namn, partier in (("V+S+MP+C", ["V", "S", "MP", "C"]),
                          ("M+KD+L+SD", ["M", "KD", "L", "SD"])):
        block.append({"underlag": namn,
                      "mandat": sum(mandat[p] for p in partier),
                      "majoritet": sum(mandat[p] for p in partier) >= 175})
    for _, rad in res["regeringar"].iterrows():
        block.append({"underlag": rad["namn"],
                      "mandat": int(rad["mandat_median"]),
                      "majoritet": bool(rad["mandat_median"] >= 175),
                      "sannolikhet": round(float(rad["sannolikhet"]), 4)})
    _skriv(katalog / "regeringsunderlag.csv", block)

    # --- Metadata, så att prognosen går att placera i tiden ---------------
    meta = {
        "genererad": date.today().isoformat(),
        "valdag": cfg.VALDAG,
        "dagar_kvar": res["dagar_kvar"],
        "antal_matningar_i_fonstret": res["antal_matningar"],
        "antal_matningar_totalt": len(rader),
        "senaste_matning": rader["datum"].max().date().isoformat(),
        "halveringstid_dagar": cfg.HALVERINGSTID_DAGAR,
        "antal_simuleringar": cfg.ANTAL_SIMULERINGAR,
    }
    (katalog / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- Mätningarna som ligger till grund --------------------------------
    fonster = rader[rader["datum"] >= rader["datum"].max() - pd.Timedelta(
        days=cfg.MAX_ALDER_DAGAR)]
    fonster.sort_values("datum", ascending=False).to_csv(
        katalog / "matningar.csv", index=False, encoding="utf-8")

    # --- Kandidatprognosen, om den finns ----------------------------------
    kand = ROT / "output" / "kandidatprognos_riksdag.csv"
    if kand.exists():
        (katalog / "kandidatprognos_riksdag.csv").write_text(
            kand.read_text(encoding="utf-8"), encoding="utf-8")

    # --- Tom fil för facit ------------------------------------------------
    facit = [{"parti": p, "valresultat": "", "mandat": ""}
             for p in cfg.PARTIER]
    _skriv(katalog / "facit.csv", facit)

    return katalog


def _skriv(vag: Path, rader: list[dict]) -> None:
    if not rader:
        return
    kolumner = list({k: None for rad in rader for k in rad})
    with open(vag, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=kolumner)
        w.writeheader()
        w.writerows(rader)


def utvardera(katalog: Path) -> None:
    """Jämför prognosen med facit, när facit.csv är ifylld."""
    facitfil = katalog / "facit.csv"
    if not facitfil.exists():
        sys.exit(f"FEL: {facitfil} saknas.")

    facit = {}
    for rad in csv.DictReader(open(facitfil, encoding="utf-8")):
        try:
            facit[rad["parti"]] = {"stod": float(rad["valresultat"]),
                                   "mandat": int(rad["mandat"])}
        except (ValueError, KeyError):
            continue
    if not facit:
        sys.exit("FEL: facit.csv är tom. Fyll i valresultat och mandat.")

    huvud = list(csv.DictReader(open(katalog / "huvudprognos.csv",
                                     encoding="utf-8")))
    fel_stod, fel_mandat = [], []
    print(f"{'parti':6}{'prognos':>9}{'utfall':>8}{'fel':>7}"
          f"{'mandat':>9}{'utfall':>8}{'fel':>6}")
    for rad in huvud:
        p = rad["parti"]
        if p not in facit:
            continue
        ds = float(rad["stod"]) - facit[p]["stod"]
        dm = int(rad["mandat"]) - facit[p]["mandat"]
        fel_stod.append(abs(ds))
        fel_mandat.append(abs(dm))
        print(f"{p:6}{float(rad['stod']):9.2f}{facit[p]['stod']:8.2f}"
              f"{ds:+7.2f}{int(rad['mandat']):9}{facit[p]['mandat']:8}{dm:+6}")
    print(f"\nMedelabsolutfel: {sum(fel_stod)/len(fel_stod):.2f} procentenheter")
    print(f"Felplacerade mandat: {sum(fel_mandat)}")

    # Scenarierna, för att se vilken variant som träffade bäst.
    scen = list(csv.DictReader(open(katalog / "scenarier.csv",
                                    encoding="utf-8")))
    per_scenario: dict[str, list] = {}
    for rad in scen:
        if rad["parti"] not in facit or not rad["stod"]:
            continue
        per_scenario.setdefault(rad["scenario_namn"], []).append(
            abs(float(rad["stod"]) - facit[rad["parti"]]["stod"]))
    if per_scenario:
        print("\nScenarier, medelabsolutfel:")
        for namn, fel in sorted(per_scenario.items(),
                                key=lambda x: sum(x[1]) / len(x[1])):
            print(f"  {namn[:34]:36}{sum(fel)/len(fel):.2f}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Frys prognosen inför valdagen")
    ap.add_argument("--utvardera", action="store_true",
                    help="Jämför med facit.csv i stället för att exportera")
    ap.add_argument("--katalog", help="Vilken slutprognos som ska utvärderas")
    args = ap.parse_args()

    if args.utvardera:
        if args.katalog:
            katalog = Path(args.katalog)
        else:
            mappar = sorted((ROT / "slutprognos").glob("2026-*"))
            if not mappar:
                sys.exit("FEL: ingen slutprognos att utvärdera.")
            katalog = mappar[-1]
        print(f"Utvärderar {katalog.name}\n")
        utvardera(katalog)
        return

    katalog = bygg()
    print(f"Slutprognos sparad: {katalog}")
    for fil in sorted(katalog.iterdir()):
        print(f"  {fil.name:34}{fil.stat().st_size / 1024:7.1f} kB")


if __name__ == "__main__":
    main()
