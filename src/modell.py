"""Prognosmodell: viktat medelvärde, husfaktorer och Monte Carlo-simulering."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

import config as cfg

ROT = Path(__file__).resolve().parent.parent


# --- Vikter ------------------------------------------------------------------

def tidsvikt(alder_dagar: np.ndarray) -> np.ndarray:
    """Exponentiell avklingning: nyare mätningar väger tyngre.

    Halveringstiden styrs av data/modellparametrar.csv. Med 30 dagar väger en
    månad gammal mätning hälften så mycket som en dagsfärsk.
    """
    return 0.5 ** (np.asarray(alder_dagar, dtype=float) / cfg.HALVERINGSTID_DAGAR)


def urvalsvikt(urval: np.ndarray) -> np.ndarray:
    """Vikt efter urvalsstorlek, normaliserad mot ett typiskt urval om 1500.

    Precisionen växer med kvadratroten ur urvalet, inte linjärt, så ett
    SCB-urval på 9000 väger cirka 2,4 gånger en mätning på 1500 - inte 6.
    """
    return np.sqrt(np.asarray(urval, dtype=float) / 1500.0)


def institutsvikt(institut: pd.Series) -> np.ndarray:
    return institut.map(
        lambda i: cfg.INSTITUT.get(i, {}).get("vikt", cfg.STANDARD_VIKT)
    ).to_numpy(dtype=float)


def berakna_vikter(df: pd.DataFrame, referensdatum: date) -> pd.Series:
    """Total vikt = kvalitet x urval x färskhet."""
    alder = (pd.Timestamp(referensdatum) - df["datum"]).dt.days.to_numpy()
    v = institutsvikt(df["institut"]) * urvalsvikt(df["urval"]) * tidsvikt(alder)
    return pd.Series(v, index=df.index)


# --- Husfaktorer -------------------------------------------------------------

def skatta_husfaktorer(df: pd.DataFrame, referensdatum: date) -> pd.DataFrame:
    """Skattar varje instituts systematiska avvikelse från konsensus.

    För varje mätning jämförs institutets siffra med ett tidsviktat konsensus
    från övriga institut vid samma tidpunkt. Genomsnittet av dessa avvikelser
    är institutets husfaktor. Metoden är iterativ i den meningen att konsensus
    beräknas exklusive institutet självt, så ett institut inte kan definiera
    sin egen referenspunkt.
    """
    fonster = df[
        (pd.Timestamp(referensdatum) - df["datum"]).dt.days <= cfg.HUSFAKTOR_FONSTER_DAGAR
    ].copy()

    rader = []
    for institut, grupp in fonster.groupby("institut"):
        if len(grupp) < cfg.MIN_MATNINGAR_HUSFAKTOR:
            continue
        avvikelser = {p: [] for p in cfg.PARTIER}
        vikter = []
        for _, matning in grupp.iterrows():
            # Övriga instituts mätningar, viktade mot denna mätnings datum.
            andra = fonster[
                (fonster["institut"] != institut)
                & ((fonster["datum"] - matning["datum"]).dt.days.abs() <= 45)
            ]
            if len(andra) < 3:
                continue
            dagar = (andra["datum"] - matning["datum"]).dt.days.abs().to_numpy()
            w = institutsvikt(andra["institut"]) * tidsvikt(dagar)
            if w.sum() <= 0:
                continue
            for p in cfg.PARTIER:
                konsensus = np.average(andra[p].to_numpy(dtype=float), weights=w)
                avvikelser[p].append(float(matning[p]) - konsensus)
            vikter.append(1.0)

        if not vikter:
            continue
        post = {"institut": institut, "antal_matningar": len(vikter)}
        for p in cfg.PARTIER:
            post[p] = float(np.mean(avvikelser[p])) if avvikelser[p] else 0.0
        rader.append(post)

    if not rader:
        return pd.DataFrame(columns=["institut", "antal_matningar"] + cfg.PARTIER)

    hf = pd.DataFrame(rader)
    # Centrera så att husfaktorerna summerar till noll över instituten. Annars
    # skulle en generell nivåförskjutning felaktigt tolkas som partistöd.
    for p in cfg.PARTIER:
        hf[p] = hf[p] - hf[p].mean()
    return hf


def justera_for_husfaktor(df: pd.DataFrame, husfaktorer: pd.DataFrame) -> pd.DataFrame:
    """Drar bort en dämpad andel av varje instituts husfaktor."""
    ut = df.copy()
    if husfaktorer.empty:
        return ut
    hf = husfaktorer.set_index("institut")
    for p in cfg.PARTIER:
        korr = ut["institut"].map(hf[p]).fillna(0.0).to_numpy(dtype=float)
        ut[p] = ut[p].to_numpy(dtype=float) - cfg.HUSFAKTOR_DAMPNING * korr
    return ut


def tillampa_valdagskorrigering(snitt: pd.Series, aktivera: bool | None = None) -> pd.Series:
    """Justerar snittet för historiskt observerad skevhet per parti.

    Backtestet mot 2022 visar att V konsekvent överskattades och SD
    underskattades i mätningarna. Korrigeringen är avstängd som standard
    eftersom den vilar på en enda valcykel.
    """
    if aktivera is None:
        aktivera = cfg.ANVAND_VALDAGSKORRIGERING
    if not aktivera or not cfg.VALDAGSKORRIGERING:
        return snitt
    ut = snitt.copy()
    for parti, delta in cfg.VALDAGSKORRIGERING.items():
        if parti in ut.index:
            ut[parti] = max(0.05, ut[parti] + delta)
    return ut / ut.sum() * 100.0


# --- Trend -------------------------------------------------------------------

def viktat_snitt(df: pd.DataFrame, referensdatum: date) -> pd.Series:
    vikter = berakna_vikter(df, referensdatum)
    if vikter.sum() <= 0:
        raise ValueError("Alla vikter är noll, kontrollera datum och parametrar.")
    snitt = {p: float(np.average(df[p].to_numpy(dtype=float), weights=vikter)) for p in cfg.PARTIER}
    s = pd.Series(snitt)
    return s / s.sum() * 100.0  # Normalisera bort 'Andra'.


def trendserie(df: pd.DataFrame, steg_dagar: int = 7) -> pd.DataFrame:
    """Rullande tidsviktat snitt för hela perioden, för grafen."""
    start, slut = df["datum"].min(), df["datum"].max()
    punkter = pd.date_range(start + pd.Timedelta(days=30), slut, freq=f"{steg_dagar}D")
    rader = []
    for punkt in punkter:
        histor = df[df["datum"] <= punkt]
        if len(histor) < 4:
            continue
        try:
            s = viktat_snitt(histor, punkt.date())
        except ValueError:
            continue
        rader.append({"datum": punkt, **s.to_dict()})
    return pd.DataFrame(rader)


# --- Mandatfördelning --------------------------------------------------------

def fordela_mandat(roster: dict[str, float], platser: int = cfg.MANDAT_TOTALT) -> dict[str, int]:
    """Jämkade uddatalsmetoden med 4-procentsspärr.

    Riksdagens 349 mandat fördelas med första divisor 1,2 (jämkningen) och
    därefter 3, 5, 7 ... Partier under spärren får inga mandat. Modellen
    approximerar hela riket som en valkrets, vilket är en förenkling: i
    verkligheten fördelas 310 fasta mandat i 29 valkretsar och 39
    utjämningsmandat korrigerar för avvikelser. Utjämningen gör dock
    slutresultatet mycket nära en riksproportionell fördelning.
    """
    kvalificerade = {p: v for p, v in roster.items() if v >= cfg.SPARRGRANS * 100}
    if not kvalificerade:
        # Inget parti klarar spärren. Utfallet är konstitutionellt omöjligt men kan
        # uppstå i enstaka simuleringar; riksdagen måste fyllas, så spärren faller
        # och mandaten fördelas bland samtliga partier. Samma regel gäller i den
        # vektoriserade varianten, så de två alltid ger identiska resultat.
        kvalificerade = {p: v for p, v in roster.items() if v > 0}
    if not kvalificerade:
        return {p: 0 for p in roster}

    mandat = {p: 0 for p in roster}
    divisorer = {p: 1.2 for p in kvalificerade}
    for _ in range(platser):
        vinnare = max(kvalificerade, key=lambda p: kvalificerade[p] / divisorer[p])
        mandat[vinnare] += 1
        divisorer[vinnare] = 2 * mandat[vinnare] + 1
    return mandat


def _fordela_mandat_vektor(roster: np.ndarray) -> np.ndarray:
    """Vektoriserad mandatfördelning för många simuleringar samtidigt."""
    n_sim, n_partier = roster.shape
    kvalificerad = roster >= cfg.SPARRGRANS * 100
    # Rader där inget parti klarar spärren: låt spärren falla, se fordela_mandat.
    ingen_kvalificerad = ~kvalificerad.any(axis=1)
    if ingen_kvalificerad.any():
        kvalificerad = kvalificerad.copy()
        kvalificerad[ingen_kvalificerad] = roster[ingen_kvalificerad] > 0
    effektiva = np.where(kvalificerad, roster, 0.0)

    mandat = np.zeros((n_sim, n_partier), dtype=np.int32)
    divisorer = np.full((n_sim, n_partier), 1.2)
    for _ in range(cfg.MANDAT_TOTALT):
        kvoter = np.where(effektiva > 0, effektiva / divisorer, -1.0)
        vinnare = np.argmax(kvoter, axis=1)
        rad = np.arange(n_sim)
        mandat[rad, vinnare] += 1
        divisorer[rad, vinnare] = 2 * mandat[rad, vinnare] + 1
    return mandat


# --- Kammargeometri ----------------------------------------------------------

def kammarplatser(totalt: int = cfg.MANDAT_TOTALT, rader: int = 11,
                  r_inner: float = 1.0, r_yttre: float = 2.05) -> list[dict]:
    """Beräknar koordinater för riksdagskammarens platser i en halvcirkel.

    Platserna fördelas på rader där antalet per rad är proportionellt mot
    radiens båglängd, vilket ger jämn täthet. Resultatet sorteras från vänster
    till höger så att partierna kan placeras i politisk ordning.
    """
    import math

    radier = [r_inner + (r_yttre - r_inner) * i / (rader - 1) for i in range(rader)]
    langd = sum(radier)
    antal = [max(1, round(totalt * r / langd)) for r in radier]
    while sum(antal) > totalt:
        antal[antal.index(max(antal))] -= 1
    while sum(antal) < totalt:
        antal[antal.index(min(antal))] += 1

    platser = []
    for r, n in zip(radier, antal):
        for j in range(n):
            t = 0.5 if n == 1 else j / (n - 1)
            vinkel = math.pi * (1 - t)
            platser.append({
                "x": round(r * math.cos(vinkel), 4),
                "y": round(-r * math.sin(vinkel), 4),
                "vinkel": vinkel,
                "r": r,
            })
    platser.sort(key=lambda p: (-p["vinkel"], p["r"]))
    return platser


# --- Simulering --------------------------------------------------------------

def simulera(snitt: pd.Series, dagar_kvar: int, n: int | None = None,
             fro: int = 20260913) -> dict:
    """Monte Carlo med korrelerat nationellt fel och partispecifikt brus.

    Tre osäkerhetskällor läggs på:
      1. Ett nationellt fel som slår åt samma håll för hela block (korrelerat),
         vilket speglar att opinionsmätningar tenderar att missa systematiskt.
      2. Ett partispecifikt oberoende fel.
      3. En driftterm som växer med tiden kvar till valdagen.
    """
    if n is None:
        n = cfg.ANTAL_SIMULERINGAR
    rng = np.random.default_rng(fro)
    partier = list(cfg.PARTIER)
    bas = snitt[partier].to_numpy(dtype=float)

    manader_kvar = max(dagar_kvar, 0) / 30.44
    drift_sd = cfg.TREND_DRIFT_SD_PER_MANAD * np.sqrt(manader_kvar) * 100
    parti_sd = cfg.PARTIFEL_SD * 100
    nat_sd = cfg.NATIONELLT_FEL_SD * 100

    # Nationellt fel: ett gemensamt blockskift som flyttar röster mellan blocken.
    blockskift = rng.normal(0, nat_sd, size=n)
    tecken = np.array([1.0 if p in cfg.BLOCK["vanster"] else -1.0 for p in partier])

    # Partifel skalas med partiets storlek: stora partier har större absolut fel.
    skala = np.sqrt(np.maximum(bas, 1.0) / 20.0)
    partifel = rng.normal(0, parti_sd, size=(n, len(partier))) * skala
    driftfel = rng.normal(0, drift_sd, size=(n, len(partier))) * skala

    roster = bas + blockskift[:, None] * tecken[None, :] + partifel + driftfel
    roster = np.clip(roster, 0.05, None)
    roster = roster / roster.sum(axis=1, keepdims=True) * 100.0

    mandat = _fordela_mandat_vektor(roster)

    return {
        "partier": partier,
        "roster": roster,
        "mandat": mandat,
        "n": n,
    }


def sammanfatta(sim: dict) -> pd.DataFrame:
    partier, roster, mandat = sim["partier"], sim["roster"], sim["mandat"]
    rader = []
    for i, p in enumerate(partier):
        r, m = roster[:, i], mandat[:, i]
        prognos = float(np.mean(r))
        mandat_median = int(np.median(m))
        forra_stod = cfg.VALRESULTAT_2022.get(p)
        forra_mandat = cfg.MANDAT_2022.get(p)
        rader.append({
            "parti": p,
            "namn": cfg.PARTINAMN[p],
            "prognos": prognos,
            "p10": float(np.percentile(r, 10)),
            "p90": float(np.percentile(r, 90)),
            "mandat_median": mandat_median,
            "mandat_p10": int(np.percentile(m, 10)),
            "mandat_p90": int(np.percentile(m, 90)),
            "sannolikhet_over_sparr": float(np.mean(r >= cfg.SPARRGRANS * 100)),
            # Jämförelse mot valet 2022, så att förändringen går att läsa direkt.
            "forra_stod": forra_stod,
            "forandring": (prognos - forra_stod) if forra_stod is not None else None,
            "forra_mandat": forra_mandat,
            "mandatforandring": ((mandat_median - forra_mandat)
                                 if forra_mandat is not None else None),
        })
    return pd.DataFrame(rader).sort_values("prognos", ascending=False).reset_index(drop=True)


def blockutfall(sim: dict) -> dict:
    partier, mandat, roster = sim["partier"], sim["mandat"], sim["roster"]
    idx = {p: i for i, p in enumerate(partier)}
    ut = {}
    for block, medlemmar in cfg.BLOCK.items():
        kol = [idx[p] for p in medlemmar]
        m = mandat[:, kol].sum(axis=1)
        r = roster[:, kol].sum(axis=1)
        forra_roster = sum(cfg.VALRESULTAT_2022.get(p, 0.0) for p in medlemmar)
        forra_mandat = sum(cfg.MANDAT_2022.get(p, 0) for p in medlemmar)
        mandat_median = int(np.median(m))
        ut[block] = {
            "namn": cfg.BLOCKNAMN[block],
            "mandat_median": mandat_median,
            "mandat_p10": int(np.percentile(m, 10)),
            "mandat_p90": int(np.percentile(m, 90)),
            "roster": float(np.mean(r)),
            "sannolikhet_majoritet": float(np.mean(m >= 175)),
            "forra_roster": forra_roster,
            "forandring": float(np.mean(r)) - forra_roster,
            "forra_mandat": forra_mandat,
            "mandatforandring": mandat_median - forra_mandat,
        }
    v = mandat[:, [idx[p] for p in cfg.BLOCK["vanster"]]].sum(axis=1)
    h = mandat[:, [idx[p] for p in cfg.BLOCK["hoger"]]].sum(axis=1)
    ut["oavgjort"] = float(np.mean((v < 175) & (h < 175)))
    return ut


def regeringsutfall(sim: dict) -> pd.DataFrame:
    """Sannolikhet att varje regeringsalternativ når egen majoritet."""
    partier, mandat, roster = sim["partier"], sim["mandat"], sim["roster"]
    idx = {p: i for i, p in enumerate(partier)}
    rader = []
    for alt in cfg.REGERINGSALTERNATIV:
        kol = [idx[p] for p in alt["partier"] if p in idx]
        m = mandat[:, kol].sum(axis=1)
        giltig = m >= 175
        # Extra villkor, t.ex. att C måste klara spärren för att ingå.
        for parti, grans in (alt.get("krav", {}).get("minst") or {}).items():
            if parti in idx:
                giltig &= roster[:, idx[parti]] >= grans * 100
        rader.append({
            "id": alt["id"],
            "namn": alt["namn"],
            "beskrivning": alt["beskrivning"],
            "partier": "+".join(alt["partier"]),
            "sannolikhet": float(np.mean(giltig)),
            "mandat_median": int(np.median(m)),
            "mandat_p10": int(np.percentile(m, 10)),
            "mandat_p90": int(np.percentile(m, 90)),
        })
    return pd.DataFrame(rader).sort_values("sannolikhet", ascending=False).reset_index(drop=True)
