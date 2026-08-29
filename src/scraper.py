"""Hämtar opinionsmätningar från Wikipedia och normaliserar dem till en CSV.

Wikipedia lägger varje instituts mätningar i en egen tabell under en rubrik med
institutets namn. Sammanvägningar (poll of polls) ligger i en egen tabell och
exkluderas, eftersom de annars dubbelräknar de underliggande mätningarna.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from config import EXKLUDERA, INSTITUT, PARTIER, STANDARD_URVAL

def wiki_url(valar: int = 2026) -> str:
    return (
        "https://sv.wikipedia.org/wiki/"
        f"Opinionsm%C3%A4tningar_inf%C3%B6r_riksdagsvalet_i_Sverige_{valar}"
    )


WIKI_URL = wiki_url(2026)
HEADERS = {"User-Agent": "svensk-valprediktor/0.1 (analysprojekt)"}

MANADER = {
    "januari": 1, "februari": 2, "mars": 3, "april": 4, "maj": 5, "juni": 6,
    "juli": 7, "augusti": 8, "september": 9, "oktober": 10, "november": 11,
    "december": 12,
}

ROT = Path(__file__).resolve().parent.parent


def _rensa_procent(text) -> float | None:
    """Tolkar '31,0 %', '9+ %', '17+%', '4* %' till ett flyttal.

    Sentio med flera redovisar avrundade heltal med suffix som anger åt vilket
    håll värdet avrundats. '+' betyder strax över, '-' strax under. Vi justerar
    med en tredjedels procentenhet för att inte systematiskt förlora information.
    """
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None
    s = str(text).strip()
    if not s or s in {"-", "–", "—"}:
        return None
    s = s.replace("\xa0", " ").replace("%", "").strip()
    justering = 0.0
    if s.endswith("+"):
        justering, s = 0.33, s[:-1]
    elif s.endswith("-"):
        justering, s = -0.33, s[:-1]
    elif s.endswith("*"):
        s = s[:-1]
    s = s.replace(",", ".").strip()
    # Plocka första talet, ignorera eventuella fotnoter.
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None
    return float(m.group()) + justering


def _tolka_datum(text: str, standardar: int = 2026) -> date | None:
    """Tolkar svenska datumangivelser och returnerar mätperiodens slutdatum.

    Hanterar '27 maj–7 juni 2026', '6–19 juli 2026', '24 oktober 2025',
    'maj 2023'. Slutdatumet används eftersom det bäst representerar när
    opinionen faktiskt mättes.
    """
    if not text or (isinstance(text, float) and pd.isna(text)):
        return None
    s = str(text).replace("\xa0", " ").strip()
    s = re.sub(r"\[\d+\]", "", s)
    # Normalisera alla bindestreckvarianter till ett tecken.
    s = re.sub(r"\s*[–—-]\s*", "–", s)

    ar_m = re.search(r"(19|20)\d{2}", s)
    ar = int(ar_m.group()) if ar_m else standardar

    # Sista delen efter ev. intervall är slutdatumet.
    sista = s.split("–")[-1]

    dag_m = re.search(r"\b(\d{1,2})\b", sista)
    manad_m = re.search(r"\b(" + "|".join(MANADER) + r")\b", sista, re.IGNORECASE)

    if not manad_m:
        # Månaden kan stå i första delen: '27 maj–7 juni' har månad i båda,
        # men '3–7 maj' har den bara sist. Sök i hela strängen som fallback.
        manad_m = re.search(r"\b(" + "|".join(MANADER) + r")\b", s, re.IGNORECASE)
    if not manad_m:
        return None
    manad = MANADER[manad_m.group().lower()]

    if not dag_m:
        # Bara månad angiven, anta månadens mitt.
        dag = 15
    else:
        dag = int(dag_m.group())

    try:
        return date(ar, manad, min(dag, 28) if dag > 31 else dag)
    except ValueError:
        return None


def _tolka_urval(soup_rad) -> int | None:
    """Letar efter urvalsstorlek i radens text, t.ex. '1 542 personer'."""
    txt = soup_rad.get_text(" ", strip=True).replace("\xa0", " ")
    m = re.search(r"\b(\d[\d ]{2,6})\s*(?:personer|intervjuer|svar)\b", txt, re.I)
    if m:
        return int(m.group(1).replace(" ", ""))
    return None


def _las_tabell(html: str):
    """Läser en HTML-tabell till en DataFrame.

    Från pandas 2.1 tolkas en rå HTML-sträng som ett filnamn och måste lindas i
    StringIO. Äldre versioner accepterar strängen direkt. Funktionen hanterar
    båda, så att koden fungerar likadant lokalt och i byggmiljön.
    """
    from io import StringIO

    try:
        tabeller = pd.read_html(StringIO(html))
    except (TypeError, ValueError):
        tabeller = pd.read_html(html)
    return tabeller[0] if tabeller else None


def _platta_kolumner(kolumner) -> list[str]:
    """Plattar ut Wikipedias flernivåheader till partikoder.

    Headern har flera nivåer och partikoderna (V, S, MP, ...) ligger inte alltid
    på den understa. För V och S står i stället 'Diff'/'Källa' underst, vilket
    gör att en naiv reversed()-sökning ger fel kolumnnamn. Vi väljer därför den
    nivå som innehåller flest partikoder och faller tillbaka på övriga nivåer
    för kolumner som saknar värde där.
    """
    if not isinstance(kolumner, pd.MultiIndex):
        return [str(c).strip() for c in kolumner]

    antal_nivaer = kolumner.nlevels
    partiset = set(PARTIER)
    basta, basta_traff = 0, -1
    for niva in range(antal_nivaer):
        traff = sum(1 for c in kolumner if str(c[niva]).strip() in partiset)
        if traff > basta_traff:
            basta, basta_traff = niva, traff

    ut = []
    for c in kolumner:
        namn = str(c[basta]).strip()
        if not namn or "Unnamed" in namn or namn == "nan":
            namn = next(
                (str(n).strip() for n in c
                 if str(n).strip() and "Unnamed" not in str(n) and str(n).strip() != "nan"),
                str(c[0]),
            )
        ut.append(namn)
    return ut


def hamta_html(cache: bool = True, valar: int = 2026) -> str:
    cachefil = ROT / "data" / f"wikipedia_cache_{valar}.html"
    if cache and cachefil.exists():
        alder = (datetime.now().timestamp() - cachefil.stat().st_mtime) / 3600
        if alder < 6:
            return cachefil.read_text(encoding="utf-8")
    svar = requests.get(wiki_url(valar), headers=HEADERS, timeout=30)
    svar.raise_for_status()
    cachefil.parent.mkdir(parents=True, exist_ok=True)
    cachefil.write_text(svar.text, encoding="utf-8")
    return svar.text


def _institut_for_tabell(tabell) -> str | None:
    """Hittar institutnamnet i närmast föregående rubrik."""
    rubrik = tabell.find_previous(["h2", "h3", "h4"])
    if not rubrik:
        return None
    txt = rubrik.get_text(" ", strip=True)
    txt = re.sub(r"\[redigera.*?\]", "", txt).strip()
    # 'Verian (f.d. Kantar Sifo)' -> 'Verian'
    txt = re.split(r"\s*\(", txt)[0].strip()
    return txt or None


def skrapa(valar: int = 2026) -> pd.DataFrame:
    html = hamta_html(valar=valar)
    soup = BeautifulSoup(html, "lxml")

    rader = []
    for tabell in soup.find_all("table"):
        institut = _institut_for_tabell(tabell)
        if not institut:
            continue
        if any(e.lower() in institut.lower() for e in EXKLUDERA):
            continue
        if institut in {"Innehåll", "Trend", "Referenser", "Källor", "Se även",
                        "Medelvärde", "Sammanställning"}:
            continue
        if "vallokalsundersökning" in institut.lower() or "vallokalundersökning" in institut.lower():
            continue

        # Läs tabellen med pandas för robust cellhantering.
        try:
            df = _las_tabell(str(tabell))
        except (ValueError, IndexError):
            continue
        if df is None:
            continue
        if df.shape[1] < 9:
            continue

        df.columns = _platta_kolumner(df.columns)

        if not all(p in df.columns for p in PARTIER):
            continue

        datumkol = next(
            (c for c in df.columns if any(k in c.lower() for k in ("period", "publicerad", "datum"))),
            df.columns[0],
        )

        soup_rader = tabell.find_all("tr")
        for i, (_, rad) in enumerate(df.iterrows()):
            datum = _tolka_datum(rad[datumkol], standardar=valar)
            if datum is None:
                continue
            varden = {p: _rensa_procent(rad[p]) for p in PARTIER}
            if sum(1 for v in varden.values() if v is not None) < 6:
                continue
            summa = sum(v for v in varden.values() if v is not None)
            if not (80 <= summa <= 105):
                continue  # Uppenbart trasig rad.

            urval = None
            if i + 2 < len(soup_rader):
                urval = _tolka_urval(soup_rader[i + 2])

            post = {
                "institut": institut,
                "datum": datum.isoformat(),
                "urval": urval or INSTITUT.get(institut, {}).get("typiskt_urval", STANDARD_URVAL),
                "urval_skattat": urval is None,
            }
            post.update({p: varden[p] for p in PARTIER})
            rader.append(post)

    if not rader:
        raise RuntimeError("Inga mätningar kunde tolkas. Wikipedias tabellstruktur kan ha ändrats.")

    df = pd.DataFrame(rader)
    df = df.drop_duplicates(subset=["institut", "datum"] + PARTIER)
    df = df.sort_values("datum", ascending=False).reset_index(drop=True)
    if valar == 2026:
        df = slask_ihop(df)
    return df


def egna_matningar() -> pd.DataFrame:
    """Läser mätningar som lagts in för hand i data/egna_matningar.csv.

    Wikipedia ligger ibland några dagar efter, och en mätning som bara
    publicerats i en tidning finns inte där alls. Sådana rader skrivs annars
    över nästa gång skrapningen kör, eftersom spara() ersätter hela filen.
    """
    fil = ROT / "data" / "egna_matningar.csv"
    if not fil.exists():
        return pd.DataFrame()
    df = pd.read_csv(fil)
    if df.empty:
        return df

    saknas = [k for k in ["institut", "datum"] + PARTIER if k not in df.columns]
    if saknas:
        raise RuntimeError(
            f"egna_matningar.csv saknar kolumnerna: {', '.join(saknas)}")

    df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
    if df["datum"].isna().any():
        trasiga = df.loc[df["datum"].isna(), "institut"].tolist()
        raise RuntimeError(
            f"egna_matningar.csv har ogiltigt datum för: {', '.join(map(str, trasiga))}. "
            "Skriv datum som ÅÅÅÅ-MM-DD.")
    df["datum"] = df["datum"].dt.date.astype(str)

    for parti in PARTIER:
        df[parti] = pd.to_numeric(df[parti], errors="coerce")
    if df[PARTIER].isna().any().any():
        raise RuntimeError("egna_matningar.csv har tomma eller ogiltiga partisiffror.")

    summa = df[PARTIER].sum(axis=1)
    orimliga = df.loc[(summa < 85) | (summa > 105)]
    if not orimliga.empty:
        rad = orimliga.iloc[0]
        raise RuntimeError(
            f"egna_matningar.csv: {rad['institut']} {rad['datum']} summerar till "
            f"{summa.loc[orimliga.index[0]]:.1f} procent. Kontrollera siffrorna.")

    if "urval" not in df.columns:
        df["urval"] = None
    df["urval_skattat"] = df["urval"].isna()
    df["urval"] = [
        u if pd.notna(u) else INSTITUT.get(i, {}).get("typiskt_urval", STANDARD_URVAL)
        for u, i in zip(df["urval"], df["institut"])
    ]
    return df[["institut", "datum", "urval", "urval_skattat"] + PARTIER]


def slask_ihop(skrapade: pd.DataFrame) -> pd.DataFrame:
    """Lägger egna mätningar ovanpå de skrapade.

    Egna rader vinner vid krock på institut och datum, så att en mätning man
    lagt in för hand inte dubbleras när Wikipedia kommer ikapp.
    """
    egna = egna_matningar()
    if egna.empty:
        return skrapade
    ihop = pd.concat([egna, skrapade], ignore_index=True)
    ihop = ihop.drop_duplicates(subset=["institut", "datum"], keep="first")
    return ihop.sort_values("datum", ascending=False).reset_index(drop=True)


def spara(df: pd.DataFrame, valar: int = 2026) -> Path:
    namn = "matningar.csv" if valar == 2026 else f"matningar_{valar}.csv"
    ut = ROT / "data" / namn
    df.to_csv(ut, index=False, encoding="utf-8")
    return ut


if __name__ == "__main__":
    import sys as _sys
    _ar = int(_sys.argv[1]) if len(_sys.argv) > 1 else 2026
    d = skrapa(_ar)
    fil = spara(d, _ar)
    print(f"Sparade {len(d)} mätningar till {fil}")
    print(d.groupby("institut").size().sort_values(ascending=False).to_string())
