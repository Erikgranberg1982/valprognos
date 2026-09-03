"""Hämtar norska opinionsmätningar från pollofpolls.no.

Sajten har öppna CSV-endpoints, så ingen HTML-skrapning behövs. Det är
väsentligt stabilare än den svenska Wikipedia-skrapningen: strukturen är ett
publicerat filformat i stället för en wikitabell som kan skrivas om.

Kör direkt för att hämta och spara:

    python3 hamta_matningar.py --fran 2013-01-01

Se forskning/DATAKALLOR.md för endpoints och format.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import urllib.request
from datetime import date
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent

BAS = "https://www.pollofpolls.no/lastned.csv"
# Sajten avvisar anrop utan webbläsar-User-Agent.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Kolumnnamnen i CSV:n mot partikoderna i config.
KOLUMN_TILL_PARTI = {
    "Ap": "Ap", "Høyre": "H", "Frp": "FrP", "SV": "SV", "Sp": "Sp",
    "KrF": "KrF", "Venstre": "V", "MDG": "MDG", "Rødt": "R",
}

# Instituten förkortas i CSV:n. Mappas till namnen i institut_vikter.csv.
INSTITUT_NORMALISERING = {
    "Respons": "Respons Analyse",
    "Norstat": "Norstat",
    "Opinion": "Opinion",
    "Verian": "Verian",
    "InFact": "InFact",
    "Norfakta": "Norfakta",
    "Sentio": "Sentio",
    "Ipsos": "Ipsos",
    "Kantar": "Verian",      # Kantar TNS bytte namn till Verian 2023.
    "Kantar TNS": "Verian",
    "TNS Gallup": "Verian",
}


def _hamta(parametrar: dict[str, str]) -> str:
    """Hämtar en CSV och avkodar den. Sajten skickar latin-1, inte UTF-8."""
    fraga = urllib.parse.urlencode(parametrar)
    begaran = urllib.request.Request(f"{BAS}?{fraga}", headers={"User-Agent": UA})
    with urllib.request.urlopen(begaran, timeout=60) as svar:
        return svar.read().decode("latin-1")


def _tolka_datum(text: str) -> date | None:
    """Tolkar pollofpolls datumformat D/M-ÅÅÅÅ, alltså dag först."""
    traff = re.match(r"\s*(\d{1,2})/(\d{1,2})-(\d{4})\s*$", text)
    if not traff:
        return None
    dag, manad, ar = (int(g) for g in traff.groups())
    try:
        return date(ar, manad, dag)
    except ValueError:
        return None


def _tolka_tal(text: str) -> float | None:
    """Plockar procenttalet ur en cell som "26,8 (48)".

    Mandattalet i parentesen är pollofpolls egen fördelning och kastas: vi
    räknar mandat själva i mandat.py.
    """
    traff = re.match(r"\s*(-?[\d]+(?:,\d+)?)", text)
    if not traff:
        return None
    return float(traff.group(1).replace(",", "."))


def _dela_institut(text: str) -> tuple[str, str]:
    """Delar "Norstat/NRK / VL / Dagbl." i institut och uppdragsgivare."""
    delar = text.split("/", 1)
    ravt = delar[0].strip()
    uppdragsgivare = delar[1].strip() if len(delar) > 1 else ""
    return INSTITUT_NORMALISERING.get(ravt, ravt), uppdragsgivare


def hamta_matningar(fran: date, till: date | None = None) -> list[dict]:
    """Hämtar enskilda riksmätningar i perioden.

    Anropet delas per år: sajten tystnar på för långa intervall och ett
    misslyckat år ska inte ta hela serien med sig.
    """
    if till is None:
        till = date.today()

    rader: list[dict] = []
    for ar in range(fran.year, till.year + 1):
        start = max(fran, date(ar, 1, 1))
        slut = min(till, date(ar, 12, 31))
        try:
            text = _hamta({
                "tabell": "liste_galluper", "type": "riks", "kommuneid": "0",
                "start": start.isoformat(), "slutt": slut.isoformat(),
            })
        except Exception as fel:
            print(f"  {ar}: hämtningen misslyckades, {fel}")
            continue
        nya = _tolka_csv(text)
        print(f"  {ar}: {len(nya)} mätningar")
        rader.extend(nya)

    # Samma mätning kan förekomma i två årsanrop om perioderna överlappar.
    unika: dict[tuple, dict] = {}
    for rad in rader:
        unika[(rad["institut"], rad["datum"])] = rad
    return sorted(unika.values(), key=lambda r: r["datum"], reverse=True)


def _tolka_csv(text: str) -> list[dict]:
    """Tolkar en liste_galluper-CSV.

    Filen inleds med ett par förklarande rader före rubrikraden, så inläsningen
    letar upp rubriken i stället för att hoppa över ett fast antal rader.
    """
    rader = list(csv.reader(io.StringIO(text), delimiter=";"))
    rubrikindex = next(
        (i for i, r in enumerate(rader) if r and r[0].strip() == "Måling"), None)
    if rubrikindex is None:
        return []

    rubrik = [c.strip() for c in rader[rubrikindex]]
    kolumnpos = {rubrik[i]: i for i in range(len(rubrik))}
    saknade = [k for k in KOLUMN_TILL_PARTI if k not in kolumnpos]
    if saknade:
        raise ValueError(
            f"pollofpolls har ändrat kolumner, saknar {saknade}. "
            f"Fick: {rubrik}")

    ut = []
    for rad in rader[rubrikindex + 1:]:
        if len(rad) < len(rubrik) or not rad[0].strip():
            continue
        datum = _tolka_datum(rad[kolumnpos["Dato"]])
        if datum is None:
            continue
        institut, uppdragsgivare = _dela_institut(rad[0])

        varden = {}
        trasig = False
        for kolumn, parti in KOLUMN_TILL_PARTI.items():
            tal = _tolka_tal(rad[kolumnpos[kolumn]])
            if tal is None:
                trasig = True
                break
            varden[parti] = tal
        if trasig:
            continue

        andra = _tolka_tal(rad[kolumnpos["Andre"]]) if "Andre" in kolumnpos else None
        summa = sum(varden.values()) + (andra or 0.0)
        # En mätning som inte summerar till ungefär hundra är feltolkad.
        if not 95.0 <= summa <= 105.0:
            print(f"  Hoppar över {institut} {datum}: summan är {summa:.1f}")
            continue

        ut.append({
            "institut": institut,
            "uppdragsgivare": uppdragsgivare,
            "datum": datum.isoformat(),
            **varden,
            "Andra": andra,
            "kalla": "pollofpolls.no",
        })
    return ut


def spara(rader: list[dict], fil: Path | None = None) -> Path:
    if fil is None:
        fil = ROT / "data" / "matningar.csv"
    fil.parent.mkdir(parents=True, exist_ok=True)
    partier = list(KOLUMN_TILL_PARTI.values())
    kolumner = (["institut", "uppdragsgivare", "datum"] + partier
                + ["Andra", "kalla"])
    with open(fil, "w", encoding="utf-8", newline="") as f:
        skrivare = csv.DictWriter(f, fieldnames=kolumner)
        skrivare.writeheader()
        skrivare.writerows(rader)
    return fil


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Hämtar norska opinionsmätningar från pollofpolls.no")
    ap.add_argument("--fran", default="2013-01-01",
                    help="Startdatum ÅÅÅÅ-MM-DD. Enskilda mätningar finns "
                         "från 2013, alltså tre valcykler bakåt.")
    ap.add_argument("--till", help="Slutdatum ÅÅÅÅ-MM-DD. Standard: idag.")
    args = ap.parse_args()

    fran = date.fromisoformat(args.fran)
    till = date.fromisoformat(args.till) if args.till else None

    print(f"Hämtar mätningar från {fran} ...")
    rader = hamta_matningar(fran, till)
    if not rader:
        raise SystemExit("Inga mätningar hämtade.")

    fil = spara(rader)
    institut: dict[str, int] = {}
    for r in rader:
        institut[r["institut"]] = institut.get(r["institut"], 0) + 1

    print(f"\n{len(rader)} mätningar sparade i {fil.relative_to(ROT)}")
    print(f"Period: {rader[-1]['datum']} till {rader[0]['datum']}")
    print("\nInstitut:")
    for namn, antal in sorted(institut.items(), key=lambda x: -x[1]):
        print(f"  {namn:20}{antal:5}")


if __name__ == "__main__":
    main()
