#!/usr/bin/env python3
"""Kontrollerar att det norska bygget gav ett rimligt resultat.

Körs i arbetsflödet efter bygget. Faller kontrollen publiceras ingenting, och
sidan som redan ligger uppe påverkas inte. Det är avsiktligt: en trasig sida
är sämre än en gammal.

Kör lokalt med `python3 kontrollera.py`.
"""
from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path

ROT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROT / "src"))

import config as cfg  # noqa: E402

FEL: list[str] = []
VARNING: list[str] = []


def kontrollera_matningar() -> None:
    fil = ROT / "data" / "matningar.csv"
    if not fil.exists():
        FEL.append("data/matningar.csv saknas, hämtningen har inte körts.")
        return

    import csv
    with open(fil, encoding="utf-8") as f:
        rader = list(csv.DictReader(f))

    if len(rader) < 10:
        FEL.append(f"Bara {len(rader)} mätningar, väntade minst 10. "
                   f"Wikipedia har troligen ändrat tabellstrukturen.")
        return

    senaste = max(date.fromisoformat(r["datum"]) for r in rader)
    alder = (date.today() - senaste).days
    valdag = date.fromisoformat(cfg.VALDAG)
    # Mätningarna kommer tätare i valrörelsen, så gränsen skärps nära valet.
    gräns = 21 if (valdag - date.today()).days < 90 else 120
    if alder > gräns:
        FEL.append(f"Senaste mätningen är {alder} dagar gammal, gränsen är "
                   f"{gräns}. Hämtningen kan ha slutat fungera.")

    for r in rader:
        summa = sum(float(r[p]) for p in cfg.PARTIER)
        if not 85.0 <= summa <= 102.0:
            FEL.append(f"Mätningen {r['institut']} {r['datum']} summerar till "
                       f"{summa:.1f}, vilket inte är rimligt.")
            break

    utan_urval = sum(1 for r in rader if not r.get("urval"))
    if utan_urval > len(rader) / 3:
        VARNING.append(f"{utan_urval} av {len(rader)} mätningar saknar "
                       f"urvalsstorlek och får institutets typiska urval.")

    print(f"  {len(rader)} mätningar, senaste {senaste} "
          f"({alder} dagar gammal)")


def kontrollera_mandatfordelning() -> None:
    """Kör mandatfördelningen mot de faktiska valen 2021 och 2025.

    Detta är den viktigaste kontrollen: fördelningen ska återge båda valen
    exakt. En avvikelse betyder att något i regeltolkningen gått sönder.
    """
    import mandat

    for ar, mandattal in ((2021, mandat.MANDAT_PER_DISTRIKT_2021),
                          (2025, mandat.MANDAT_PER_DISTRIKT_2025)):
        fil = ROT / "forskning" / f"roster{ar}_full.json"
        if not fil.exists():
            VARNING.append(f"Saknar {fil.name}, kan inte verifiera {ar}.")
            continue
        import json
        roster = {d.split(" - ")[0]: v
                  for d, v in json.loads(fil.read_text(encoding="utf-8")).items()}
        if ar == 2021:
            roster["Finnmark"]["PF"] = 4950
            roster["Finnmark"]["Andre"] -= 4950

        res = mandat.fordela(roster, mandattal)
        faktiskt = mandat.FAKTISKT[ar]
        avvikelse = sum(abs(res["mandat"].get(p, 0) - f)
                        for p, f in faktiskt.items())
        if avvikelse:
            FEL.append(f"Mandatfördelningen avviker {avvikelse} mandat från "
                       f"valet {ar}. Den ska återge det exakt.")
        if sum(res["mandat"].values()) != cfg.MANDAT_TOTALT:
            FEL.append(f"Fördelningen gav {sum(res['mandat'].values())} mandat "
                       f"{ar}, inte {cfg.MANDAT_TOTALT}.")
        print(f"  Mandatfördelning {ar}: {avvikelse} mandats avvikelse")


def kontrollera_sidan() -> None:
    katalog = Path(os_environ_output() or (ROT.parent / "output" / "norge"))
    fil = katalog / "index.html"
    if not fil.exists():
        FEL.append(f"{fil} saknas, sidan byggdes inte.")
        return

    html = fil.read_text(encoding="utf-8")
    if len(html) < 15_000:
        FEL.append(f"Sidan är bara {len(html)} tecken, väntade minst 15 000.")

    for tagg in ("div", "table", "svg", "tbody"):
        if html.count(f"<{tagg}") != html.count(f"</{tagg}>"):
            FEL.append(f"Obalanserade <{tagg}>-taggar i sidan.")

    if "nan" in html.lower().replace("finnmark", ""):
        träffar = [m.start() for m in re.finditer(r"\bnan\b", html, re.I)][:1]
        if träffar:
            FEL.append("Sidan innehåller NaN, någon siffra räknades inte fram.")

    # Sidan ska vara på norska. Ett par svenska ord som annars lätt smiter med.
    for ord_ in ("mätning", "röster", "spärren", "riksdag"):
        if ord_ in html.lower():
            FEL.append(f"Sidan innehåller det svenska ordet {ord_!r}.")

    print(f"  Sidan är {len(html) / 1024:.0f} kB")


def os_environ_output() -> str | None:
    from os import environ
    return environ.get("NORSK_OUTPUT")


def main() -> int:
    print(f"Kontrollerar bygget, {datetime.now():%Y-%m-%d %H:%M}")
    kontrollera_matningar()
    kontrollera_mandatfordelning()
    kontrollera_sidan()

    for v in VARNING:
        print(f"  Varning: {v}")
    if FEL:
        print("\nKontrollen föll:")
        for f in FEL:
            print(f"  - {f}")
        print("\nInget publiceras. Sidan som ligger uppe påverkas inte.")
        return 1
    print("\nAllt ser rimligt ut.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
