"""Hämtar norska opinionsmätningar från Wikipedia.

Skrapar wikitexten via MediaWikis API i stället för den renderade HTML-sidan.
Wikitexten är stabilare: den ändras när någon redigerar tabellen, medan
HTML-strukturen också kan ändras när Wikipedia byter mallar eller skin.

Wikipedia har två fördelar mot pollofpolls egna CSV-filer, som är den andra
tänkbara källan:

  1. Urvalsstorlek och svarsfrekvens finns med. pollofpolls CSV har ingen
     urvalskolumn alls, och modellen viktar mätningar efter urval.
  2. Fältarbetsperioden anges som ett intervall, inte bara publiceringsdatum.
     Mätningens mittdatum är rätt tidpunkt att vikta mot.

Notera att Wikipedia i sin tur hänvisar till pollofpolls för siffrorna, så
källan är inte oberoende. Den är däremot bättre strukturerad.

Se forskning/DATAKALLOR.md för formatdetaljer.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent

API = "https://en.wikipedia.org/w/api.php"
UA = "Norsk-valprognos/1.0 (Lysio Research; kontakt via lysio.se)"

# Partikolumnerna i den ordning de står i Wikipedias tabell.
PARTIORDNING = ["R", "SV", "MDG", "Ap", "Sp", "V", "KrF", "H", "FrP"]

MANADER = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
    # Tabellen skrivs på engelska men norska månadsnamn förekommer.
    "januar": 1, "februar": 2, "mars": 3, "mai": 5, "juni": 6, "juli": 7,
    "oktober": 10, "desember": 12,
}
# Wikipedia förkortar månadsnamnen i de flesta rader, "Apr" i stället för
# "April". Trebokstavsformerna läggs till automatiskt så att listan bara
# behöver underhållas på ett ställe.
MANADER.update({namn[:3]: nummer for namn, nummer in list(MANADER.items())})

# Institutnamn normaliseras mot data/institut_vikter.csv.
INSTITUT_NORMALISERING = {
    "Respons": "Respons Analyse",
    "Respons Analyse": "Respons Analyse",
    "Kantar": "Verian", "Kantar TNS": "Verian", "TNS Gallup": "Verian",
    "Verian": "Verian", "Norstat": "Norstat", "Opinion": "Opinion",
    "InFact": "InFact", "Norfakta": "Norfakta", "Sentio": "Sentio",
    "Ipsos": "Ipsos",
}

# Rader som inte är mätningar utan valresultat eller sammanvägningar.
EJ_MATNINGAR = re.compile(
    r"election|valg|result|poll of polls|average|snitt", re.IGNORECASE)


def hamta_wikitext(sida: str) -> str:
    """Hämtar en sidas wikitext via MediaWikis API."""
    fraga = urllib.parse.urlencode({
        "action": "parse", "page": sida, "prop": "wikitext",
        "format": "json", "formatversion": "2",
    })
    begaran = urllib.request.Request(f"{API}?{fraga}", headers={"User-Agent": UA})
    with urllib.request.urlopen(begaran, timeout=60) as svar:
        data = json.load(svar)
    if "error" in data:
        raise ValueError(f"Wikipedia svarade: {data['error'].get('info')}")
    return data["parse"]["wikitext"]


def _rensa(cell: str) -> str:
    """Plockar bort wikimarkup och behåller den synliga texten.

    Ordningen spelar roll: gömda underposter i {{Hide|...}} måste bort innan
    övriga mallar, annars läcker småpartiernas siffror in i cellen.
    """
    cell = re.sub(r"\{\{Hide\|.*?\}\}\s*$", "", cell,
                  flags=re.IGNORECASE | re.DOTALL)
    # Mandattalet står i en font-mall efter <br />. Klipp där.
    cell = re.split(r"<br\s*/?>", cell, maxsplit=1)[0]
    cell = re.sub(r"style\s*=\s*\"[^\"]*\"", "", cell)
    cell = re.sub(r"\{\{[^{}]*\}\}", "", cell)
    cell = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]|]*)\]\]", r"\1", cell)
    cell = re.sub(r"\[https?://\S+\s+([^\]]*)\]", r"\1", cell)
    cell = re.sub(r"<ref.*?(?:/>|</ref>)", "", cell, flags=re.DOTALL)
    cell = re.sub(r"<[^>]+>", "", cell)
    return cell.replace("'''", "").replace("''", "").strip(" |")


def _tolka_datumintervall(cell: str, standardar: int) -> date | None:
    """Tolkar fältarbetsperioden och returnerar dess mittdatum.

    Mätningen bör viktas mot när fältarbetet gjordes, inte när den
    publicerades. Perioden skrivs oftast med mallen {{opdrts|10|16|August|2026}},
    alltså från den tionde till den sextonde augusti.
    """
    mall = re.search(r"\{\{\s*opdrts\s*\|([^}]*)\}\}", cell, re.IGNORECASE)
    if mall:
        delar = [d.strip() for d in mall.group(1).split("|")]
        # Månad och år anges sist. Dagarna är de inledande positionerna, och
        # den första kan vara tom: {{opdrts||2|Mar|2026}} är en enda dag.
        manad = next((MANADER[d.lower()] for d in delar
                      if d.lower() in MANADER), None)
        ar = next((int(d) for d in delar if d.isdigit() and len(d) == 4),
                  standardar)
        dagar = [int(d) for d in delar
                 if d.isdigit() and len(d) <= 2 and 1 <= int(d) <= 31]
        if manad and dagar:
            try:
                sista = date(ar, manad, dagar[-1])
                forsta = date(ar, manad, dagar[0]) if len(dagar) > 1 else sista
                # Perioden kan spänna över ett månadsskifte:
                # {{opdrts|23|2|Mar|2026}} betyder 23 februari till 2 mars.
                # Månaden i mallen är slutmånaden, så starten ligger i den
                # föregående.
                if forsta > sista:
                    foregaende = sista.replace(day=1) - timedelta(days=1)
                    forsta = date(foregaende.year, foregaende.month, dagar[0])
                return forsta + (sista - forsta) / 2
            except ValueError:
                return None

    text = _rensa(cell)
    # Fritext, till exempel "10-16 August 2026" eller "16 August 2026".
    traff = re.search(r"(\d{1,2})\s*(?:[-–]\s*(\d{1,2})\s*)?"
                      r"([A-Za-zÅÄÖåäö]+)\s*(\d{4})?", text)
    if not traff:
        return None
    d1, d2, manadsnamn, ar = traff.groups()
    manad = MANADER.get(manadsnamn.lower())
    if not manad:
        return None
    try:
        forsta = date(int(ar or standardar), manad, int(d1))
        sista = date(int(ar or standardar), manad, int(d2)) if d2 else forsta
        return forsta + (sista - forsta) / 2
    except ValueError:
        return None


def _tolka_tal(cell: str) -> float | None:
    text = _rensa(cell)
    traff = re.match(r"(\d+(?:[.,]\d+)?)", text)
    return float(traff.group(1).replace(",", ".")) if traff else None


def _tolka_urval(cell: str) -> int | None:
    text = _rensa(cell).replace(",", "").replace(" ", "").replace(" ", "")
    traff = re.search(r"(\d{3,7})", text)
    return int(traff.group(1)) if traff else None


def skrapa(sida: str = "2029 Norwegian parliamentary election") -> list[dict]:
    """Skrapar samtliga mätningstabeller på sidan.

    Sidan har en tabell per år under rubriker som "=== 2026 ===". Året i
    rubriken används som standardår när en datumcell saknar årtal.
    """
    wikitext = hamta_wikitext(sida)

    avsnitt = re.split(r"\n=+\s*(\d{4})\s*=+\s*\n", wikitext)
    # split ger [före, år, innehåll, år, innehåll, ...]
    rader: list[dict] = []
    for i in range(1, len(avsnitt) - 1, 2):
        ar = int(avsnitt[i])
        rader.extend(_tolka_tabell(avsnitt[i + 1], ar))

    if not rader:
        raise ValueError(
            "Hittade inga mätningar. Wikipedia har troligen ändrat "
            "tabellstrukturen, kontrollera sidan manuellt.")

    # Samma mätning kan stå i två avsnitt om året skiftar. Behåll en per
    # institut och datum.
    unika: dict[tuple, dict] = {}
    for rad in rader:
        unika[(rad["institut"], rad["datum"])] = rad
    return sorted(unika.values(), key=lambda r: r["datum"], reverse=True)


def _tolka_tabell(text: str, ar: int) -> list[dict]:
    ut = []
    for rad in re.split(r"\n\|-", text):
        celler = re.split(r"\n\s*\|(?!\|)", rad)
        celler = [c for c in celler if c.strip()]
        if len(celler) < 4 + len(PARTIORDNING):
            continue

        institut = _rensa(celler[0])
        if not institut or EJ_MATNINGAR.search(institut):
            continue
        # Rubrikceller börjar med utropstecken i wikitext.
        if celler[0].lstrip().startswith("!"):
            continue

        datum = _tolka_datumintervall(celler[1], ar)
        if datum is None:
            continue

        varden = {}
        for parti, cell in zip(PARTIORDNING, celler[4:4 + len(PARTIORDNING)]):
            tal = _tolka_tal(cell)
            if tal is None:
                break
            varden[parti] = tal
        if len(varden) != len(PARTIORDNING):
            continue

        summa = sum(varden.values())
        # En mätning som inte summerar till rimligt nära hundra är feltolkad.
        # Övriga partier ligger utanför de nio, så summan understiger hundra.
        if not 85.0 <= summa <= 105.0:
            continue

        ut.append({
            "institut": INSTITUT_NORMALISERING.get(institut, institut),
            "datum": datum.isoformat(),
            "urval": _tolka_urval(celler[2]),
            "svarsfrekvens": _tolka_tal(celler[3]),
            **varden,
            "kalla": "Wikipedia",
        })
    return ut


def spara(rader: list[dict], fil: Path | None = None) -> Path:
    if fil is None:
        fil = ROT / "data" / "matningar.csv"
    fil.parent.mkdir(parents=True, exist_ok=True)
    kolumner = (["institut", "datum", "urval", "svarsfrekvens"]
                + PARTIORDNING + ["kalla"])
    with open(fil, "w", encoding="utf-8", newline="") as f:
        skrivare = csv.DictWriter(f, fieldnames=kolumner)
        skrivare.writeheader()
        skrivare.writerows(rader)
    return fil


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Hämtar norska opinionsmätningar från Wikipedia")
    ap.add_argument("--sida", default="2029 Norwegian parliamentary election",
                    help="Wikipediasida att skrapa")
    args = ap.parse_args()

    print(f"Hämtar {args.sida} ...")
    rader = skrapa(args.sida)
    fil = spara(rader)

    institut: dict[str, int] = {}
    utan_urval = 0
    for r in rader:
        institut[r["institut"]] = institut.get(r["institut"], 0) + 1
        if not r["urval"]:
            utan_urval += 1

    print(f"\n{len(rader)} mätningar sparade i {fil.relative_to(ROT)}")
    print(f"Period: {rader[-1]['datum']} till {rader[0]['datum']}")
    if utan_urval:
        print(f"Varning: {utan_urval} mätningar saknar urvalsstorlek.")
    print("\nInstitut:")
    for namn, antal in sorted(institut.items(), key=lambda x: -x[1]):
        print(f"  {namn:20}{antal:5}")


if __name__ == "__main__":
    main()
