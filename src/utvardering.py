"""Jämför prognosen med valresultatet på alla tre nivåer.

Riksdagen, tjugo regioner och 290 kommuner. Poängen är att se var modellen
höll och var den inte gjorde det: riksprognosen bygger på opinionsmätningar,
medan region och kommun härleds ur områdets eget resultat i förra valet skalat
med rikstrenden. Den skillnaden bör synas i felen.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

import config as cfg

ROT = Path(__file__).resolve().parent.parent


def _las_facit(fil: Path) -> dict:
    if not fil.exists():
        return {}
    ut: dict = defaultdict(dict)
    with open(fil, encoding="utf-8") as f:
        for rad in csv.DictReader(f):
            ut[rad["omrade_kod"]][rad["parti"]] = {
                "procent": float(rad["procent"]),
                "mandat": int(rad["mandat"]),
                "namn": rad.get("omrade_namn", ""),
            }
    return dict(ut)


def _normalisera(kod: str) -> str:
    """Regionkoder skrivs 01L eller 20LG i modellen, 01 hos Valmyndigheten.

    Kommunkoder är fyra siffror och lämnas orörda. Bokstavssuffixen skiljer
    landsting från region och har ingen motsvarighet i valresultatet.
    """
    kod = str(kod).strip()
    siffror = kod.rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    if len(siffror) <= 2:
        return siffror.zfill(2)
    return siffror


def utvardera_niva(prognos: list[dict], facitfil: Path,
                   nyckel: str = "kod") -> dict:
    """Fel per område, plus sammanfattning för nivån."""
    facit = _las_facit(facitfil)
    if not facit:
        return {}

    facit_norm = {_normalisera(k): v for k, v in facit.items()}
    omraden = []
    for post in prognos:
        kod = _normalisera(post.get(nyckel, ""))
        f = facit_norm.get(kod)
        if not f:
            continue
        fel, mandatfel = [], 0
        for parti in cfg.PARTIER:
            if parti not in f:
                continue
            p_stod = post.get("stod", {}).get(parti)
            if p_stod is None:
                continue
            fel.append(abs(float(p_stod) - f[parti]["procent"]))
            p_mandat = post.get("mandat", {}).get(parti)
            if p_mandat is not None:
                mandatfel += abs(int(p_mandat) - f[parti]["mandat"])
        if fel:
            omraden.append({
                "kod": kod,
                "namn": post.get("namn", ""),
                "mae": float(np.mean(fel)),
                "maxfel": float(np.max(fel)),
                "mandatfel": mandatfel,
            })

    if not omraden:
        return {}
    alla = [o["mae"] for o in omraden]
    omraden.sort(key=lambda o: o["mae"])
    return {
        "antal": len(omraden),
        "mae": float(np.mean(alla)),
        "median": float(np.median(alla)),
        "basta": omraden[:5],
        "samsta": omraden[-5:][::-1],
        "mandatfel": sum(o["mandatfel"] for o in omraden),
        "omraden": omraden,
    }


def riksniva(slutprognos: Path, facitfil: Path) -> dict:
    """Riksdagen, parti för parti."""
    facit = {}
    if facitfil.exists():
        with open(facitfil, encoding="utf-8") as f:
            for rad in csv.DictReader(f):
                facit[rad["parti"]] = {"procent": float(rad["procent"]),
                                       "mandat": int(rad["mandat"])}
    fil = slutprognos / "huvudprognos.csv"
    if not fil.exists() or not facit:
        return {}

    rader, fel, mandatfel = [], [], 0
    with open(fil, encoding="utf-8") as f:
        for rad in csv.DictReader(f):
            p = rad["parti"]
            if p not in facit:
                continue
            ds = float(rad["stod"]) - facit[p]["procent"]
            dm = int(rad["mandat"]) - facit[p]["mandat"]
            fel.append(abs(ds))
            mandatfel += abs(dm)
            rader.append({"parti": p, "prognos": float(rad["stod"]),
                          "utfall": facit[p]["procent"], "diff": ds,
                          "prognos_mandat": int(rad["mandat"]),
                          "utfall_mandat": facit[p]["mandat"],
                          "mandatdiff": dm})
    return {"partier": rader, "mae": float(np.mean(fel)),
            "mandatfel": mandatfel}
