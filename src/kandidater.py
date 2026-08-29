"""Kandidatprognos: vilka personer som väntas ta mandaten i varje område.

Underlaget kommer från Valmyndighetens kandidaturer och de listor partierna
registrerat. Kandidaterna hämtas i listordning: ett parti som får fem mandat
väntas fylla dem med listans fem första namn.

Två saker gör prognosen osäker och redovisas därför öppet:

Personröster kan flytta namn förbi varandra i ordningen. Prognosen tar inte
hänsyn till dem, eftersom de inte går att förutse.

Ett parti kan ha flera listor i samma område. Vilken lista väljarna faktiskt
använder är okänt före valet, så modellen väljer den med flest tryckta
valsedlar. Det är en indikation på var partiet lägger sin kampanj, inte en
mätning av väljarnas beteende. På regional nivå bygger 57 procent av raderna
på ett sådant val.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROT = Path(__file__).resolve().parent.parent

# Metodens tillförlitlighet, från säkrast till osäkrast.
METODTEXT = {
    "exakt_en_lista": "Partiet har en enda lista i området, så ordningen är entydig.",
    "proxy_identisk_topplista": "Flera listor delar högsta valsedelsantal, men de "
                                "namn som behövs står i samma ordning på alla.",
    "proxy_flest_valsedlar": "Partiet har flera listor. Den med flest tryckta "
                             "valsedlar används, vilket är en indikation snarare "
                             "än en mätning.",
}
METODNIVA = {
    "exakt_en_lista": "sakert",
    "proxy_identisk_topplista": "sakert",
    "proxy_flest_valsedlar": "osakert",
}


def _las_csv(namn: str) -> pd.DataFrame:
    """Läser en kandidatfil från data/kandidater.

    Filerna ligger gzip-komprimerade och versionshanterade, eftersom de behövs
    när sidan byggs i CI. Tidigare låg de i output, som inte versionshanteras,
    vilket gjorde att bygget skrev en tom kandidatfil.

    Okomprimerad fil accepteras också, så att en nyare export kan läggas in
    utan att först komprimeras.
    """
    katalog = ROT / "data" / "kandidater"
    for fil in (katalog / f"{namn}.csv.gz", katalog / f"{namn}.csv",
                ROT / "output" / f"{namn}.csv"):
        if fil.exists():
            try:
                return pd.read_csv(fil, dtype=str)
            except Exception:
                continue
    return pd.DataFrame()


def _las(niva: str) -> pd.DataFrame:
    return _las_csv(f"kandidatprognos_{niva}")


def las_utelamnade() -> pd.DataFrame:
    """Områden och partier där ingen kandidatprognos kunde göras."""
    return _las_csv("kandidatprognos_utelamnade")


def _omradeskod(niva: str, kod: str) -> str:
    """Normaliserar områdeskoden till samma form som prognosen använder.

    Kandidatfilen anger regioner som "01" medan modellen använder SCB:s
    "01L", och Dalarna heter "20LG". Kommuner anges som fyrsiffrig kod.
    """
    kod = str(kod).strip()
    if niva == "kommun":
        return kod.zfill(4)
    kod = kod.zfill(2)
    return "20LG" if kod == "20" else f"{kod}L"


def per_omrade(niva: str) -> dict:
    """Kandidaterna grupperade på område och parti.

    Returnerar en struktur som kan bäddas in i sidan: för varje område en lista
    med partier, deras mandat och de kandidater som väntas ta dem.
    """
    df = _las(niva)
    if df.empty:
        return {}

    utelamnade = las_utelamnade()
    if not utelamnade.empty:
        utelamnade = utelamnade[utelamnade["niva"] == niva]

    ut: dict[str, dict] = {}
    for (kod, parti), grupp in df.groupby(["omrade_kod", "parti"], sort=False):
        kod = _omradeskod(niva, kod)
        omrade = ut.setdefault(kod, {"namn": grupp["omrade_namn"].iloc[0],
                                     "partier": [], "saknas": []})

        grupp = grupp.copy()
        grupp["ordning_tal"] = pd.to_numeric(grupp["ordning"], errors="coerce")
        grupp = grupp.sort_values("ordning_tal")

        metod = str(grupp["listval_metod"].iloc[0])
        varning = grupp["listval_varning"].dropna()

        # Kandidaterna lagras som "Namn|ålder|ort" i stället för objekt, vilket
        # tar bort fältnamn som annars upprepas för varje av tolvtusen rader.
        # Orten utelämnas när den är samma som områdets, vilket den oftast är.
        namn = []
        for _, rad in grupp.iterrows():
            alder = rad.get("alder_pa_valdagen")
            alderstext = str(int(float(alder))) if pd.notna(alder) else ""
            ort = str(rad.get("folkbokforingskommun") or "")
            if ort == str(grupp["omrade_namn"].iloc[0]):
                ort = ""
            namn.append(f"{rad['namn']}|{alderstext}|{ort}".rstrip("|"))

        try:
            mandat = int(float(grupp["prognosmandat_parti"].iloc[0]))
        except (ValueError, TypeError):
            mandat = len(namn)

        omrade["partier"].append({
            "p": str(parti),
            "m": mandat,
            "k": namn,
            "niva": METODNIVA.get(metod, "osakert"),
            "v": str(varning.iloc[0]) if len(varning) else None,
        })

    # Partier utan prognos redovisas med skälet.
    for _, rad in utelamnade.iterrows():
        kod = _omradeskod(niva, rad["omrade_kod"])
        omrade = ut.setdefault(kod, {"namn": str(rad["omrade_namn"]),
                                     "partier": [], "saknas": []})
        try:
            mandat = int(float(rad["mandat"]))
        except (ValueError, TypeError):
            mandat = 0
        omrade["saknas"].append({
            "p": str(rad["parti"]),
            "m": mandat,
            "skal": str(rad.get("skäl") or "okänt skäl"),
        })

    for omrade in ut.values():
        omrade["partier"].sort(key=lambda x: -x["m"])
    return ut


if __name__ == "__main__":
    for niva in ("kommun", "region"):
        data = per_omrade(niva)
        kandidater = sum(len(p["k"]) for o in data.values() for p in o["partier"])
        osakra = sum(1 for o in data.values() for p in o["partier"]
                     if p["niva"] == "osakert")
        saknas = sum(len(o["saknas"]) for o in data.values())
        print(f"{niva}: {len(data)} områden, {kandidater} kandidater, "
              f"{osakra} partier med osäker lista, {saknas} utan prognos")
