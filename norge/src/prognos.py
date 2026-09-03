#!/usr/bin/env python3
"""Norsk valprediktor: kör hela kedjan från hämtning till publicerad sida.

Användning:
    python3 prognos.py              # kör med cachad data om den är färsk
    python3 prognos.py --hamta      # tvinga ny hämtning från Wikipedia
    python3 prognos.py --backtest   # utvärdera mot valen 2013 till 2025
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import config as cfg
import norsk_dashboard
import modell
import scraper

ROT = Path(__file__).resolve().parent.parent

# Institutnamn som bytt namn mellan valcyklerna. Kantar TNS blev Verian 2023.
NAMNBYTEN = {"Kantar": "Verian", "Kantar TNS": "Verian",
             "TNS Gallup": "Verian", "Respons": "Respons Analyse"}

# Faktiska valresultat, för backtest. Andelar i procent av godkända röster.
VALRESULTAT = {
    2013: {"Ap": 30.8, "H": 26.8, "FrP": 16.3, "SV": 4.1, "Sp": 5.5,
           "KrF": 5.6, "V": 5.2, "MDG": 2.8, "R": 1.1},
    2017: {"Ap": 27.4, "H": 25.0, "FrP": 15.2, "SV": 6.0, "Sp": 10.3,
           "KrF": 4.2, "V": 4.4, "MDG": 3.2, "R": 2.4},
    2021: {"Ap": 26.3, "H": 20.4, "FrP": 11.6, "SV": 7.6, "Sp": 13.5,
           "KrF": 3.8, "V": 4.6, "MDG": 3.9, "R": 4.7},
    2025: {"Ap": 28.0, "H": 14.6, "FrP": 23.8, "SV": 5.6, "Sp": 5.6,
           "KrF": 4.2, "V": 3.7, "MDG": 4.7, "R": 5.3},
}

VALDAGAR = {2013: date(2013, 9, 9), 2017: date(2017, 9, 11),
            2021: date(2021, 9, 13), 2025: date(2025, 9, 8)}


def las_matningar(fil: Path) -> pd.DataFrame:
    df = pd.read_csv(fil)
    df["datum"] = pd.to_datetime(df["datum"])
    df["institut"] = df["institut"].replace(NAMNBYTEN)

    # Urvalet saknas för en del mätningar hos källan. Utan ifyllnad blir
    # urvalsvikten NaN och sprider sig genom hela det viktade snittet, så att
    # varje partisiffra blir NaN. Institutets typiska urval används i stället,
    # och saknas även det STANDARD_URVAL.
    if "urval" not in df.columns:
        df["urval"] = float("nan")
    typiskt = df["institut"].map(
        lambda i: cfg.INSTITUT.get(i, {}).get("typiskt_urval",
                                              cfg.STANDARD_URVAL))
    df["urval_gissat"] = df["urval"].isna()
    df["urval"] = pd.to_numeric(df["urval"], errors="coerce").fillna(typiskt)

    saknade = df[cfg.PARTIER].isna().any(axis=1)
    if saknade.any():
        raise ValueError(
            f"{int(saknade.sum())} mätningar saknar partisiffror, "
            f"första {df.loc[saknade, 'datum'].min().date()}. "
            f"En ofullständig mätning kan inte viktas mot rikstrenden.")
    return df


def kor_prognos(df: pd.DataFrame, referensdatum: date, valdag: date,
                korrigera: bool | None = None,
                idag: date | None = None) -> dict:
    """Kör hela modellkedjan och returnerar alla delresultat.

    `referensdatum` styr viktningen av mätningar och kan ligga i det förflutna,
    till exempel i ett backtest. Nedräkningen till valdagen och simuleringens
    drift utgår i stället från `idag`, som annars fryser på senaste mätningens
    datum: den 2 september med senaste mätning den 30 augusti visade sidan
    fjorton dagar kvar i stället för elva.
    """
    if idag is None:
        idag = referensdatum
    husfaktorer = modell.skatta_husfaktorer(df, referensdatum)
    justerad = modell.justera_for_husfaktor(df, husfaktorer)

    aktuell = justerad[
        (pd.Timestamp(referensdatum) - justerad["datum"]).dt.days <= cfg.MAX_ALDER_DAGAR
    ]
    snitt = modell.viktat_snitt(aktuell, referensdatum)
    snitt = modell.tillampa_valdagskorrigering(snitt, korrigera)

    dagar_kvar = max((valdag - idag).days, 0)
    sim = modell.simulera(snitt, dagar_kvar)

    return {
        "snitt": snitt,
        "husfaktorer": husfaktorer,
        "justerad": justerad,
        "sim": sim,
        "sammanfattning": modell.sammanfatta(sim),
        "block": modell.blockutfall(sim),
        "regeringar": modell.regeringsutfall(sim),
        "dagar_kvar": dagar_kvar,
        "antal_matningar": len(aktuell),
    }


def bygg_matningstabell(df: pd.DataFrame, res: dict, referensdatum: date) -> pd.DataFrame:
    """Bygger tabellen över enskilda mätningar med varje mätnings faktiska vikt.

    Vikterna visas som andel av den totala vikten inom modellens tidsfönster, så
    att det går att se hur mycket en enskild mätning faktiskt påverkar prognosen.
    Mätningar utanför fönstret får vikt noll och markeras som exkluderade.
    """
    ut = df.copy()
    alder = (pd.Timestamp(referensdatum) - ut["datum"]).dt.days
    ut["alder_dagar"] = alder
    ut["inom_fonster"] = alder <= cfg.MAX_ALDER_DAGAR

    vikter = modell.berakna_vikter(ut, referensdatum)
    ut["vikt"] = vikter.where(ut["inom_fonster"], 0.0)
    total = ut["vikt"].sum()
    ut["viktandel"] = (ut["vikt"] / total * 100) if total > 0 else 0.0

    # Blocksummor per mätning, för snabb avläsning.
    ut["block_v"] = ut[cfg.BLOCK["vanster"]].sum(axis=1)
    ut["block_h"] = ut[cfg.BLOCK["hoger"]].sum(axis=1)

    return ut.sort_values("datum", ascending=False).reset_index(drop=True)


def skriv_terminal(res: dict, df: pd.DataFrame) -> None:
    print("=" * 66)
    print(f"  VALPROGNOS {cfg.VALDAG[:4]}  ·  {res['dagar_kvar']} dagar till valet")
    print("=" * 66)

    print(f"\nUnderlag: {res['antal_matningar']} mätningar, "
          f"{df['institut'].nunique()} institut, "
          f"senaste {df['datum'].max().date()}\n")

    print(f"{'PARTI':<6}{'PROGNOS':>9}{'MOT 2025':>10}{'80%-SPANN':>13}"
          f"{'MANDAT':>8}{'MOT 2025':>10}")
    print("-" * 72)
    for _, r in res["sammanfattning"].iterrows():
        spann = f"{r['p10']:.1f}–{r['p90']:.1f}"
        andring = (f"{r['forandring']:+.1f}" if r.get("forandring") is not None
                   else "–")
        mandring = (f"{r['mandatforandring']:+d}"
                    if r.get("mandatforandring") is not None else "–")
        varning = ""
        if r["sannolikhet_over_sparr"] < 0.98:
            varning = (f"  ({cfg.formatera_sannolikhet(r['sannolikhet_over_sparr'])} "
                       f"över spärren)")
        print(f"{r['parti']:<6}{r['prognos']:>8.1f}%{andring:>10}{spann:>13}"
              f"{r['mandat_median']:>8}{mandring:>10}{varning}")

    print("\n" + "-" * 66)
    print("BLOCK")
    print("-" * 66)
    for nyckel in ("vanster", "hoger"):
        b = res["block"][nyckel]
        andring = (f"{b['mandatforandring']:+d}" if "mandatforandring" in b else "–")
        print(f"{b['namn']:<14}{b['mandat_median']:>4} mandat ({andring:>3} mot 2025) "
              f"spann {b['mandat_p10']}–{b['mandat_p90']}   "
              f"majoritet: {b['sannolikhet_majoritet']*100:>5.1f}%")
    # Blocken delar samtliga 169 mandat och talet är udda, så en av dem når
    # alltid 85. Raden "ingen majoritet" vore alltid noll och skrivs inte ut.

    print("\n" + "-" * 66)
    print(f"REGERINGSALTERNATIV  (sannolikhet att nå {cfg.MAJORITET} mandat)")
    print("-" * 66)
    for _, r in res["regeringar"].iterrows():
        stapel = "█" * int(round(r["sannolikhet"] * 24))
        print(f"{r['sannolikhet']*100:>5.1f}%  {stapel:<24} {r['namn']}")
        print(f"        {r['partier']}  ·  {r['mandat_median']} mandat "
              f"({r['mandat_p10']}–{r['mandat_p90']})")

    if not res["husfaktorer"].empty:
        print("\n" + "-" * 66)
        print("HUSFAKTORER (procentenheters avvikelse från övriga institut)")
        print("-" * 66)
        hf = res["husfaktorer"].set_index("institut")[cfg.PARTIER].round(2)
        print(hf.to_string())
    print()


def backtest(historikfil: Path | None = None) -> None:
    """Utvärderar modellen mot de fyra stortingsvalen 2013 till 2025.

    Kräver den långa mätningsserien från pollofpolls, eftersom Wikipedias
    2029-sida bara täcker innevarande valcykel. Hämtas med
    `python3 hamta_matningar.py --fran 2012-01-01`.

    Två saker mäts: träffsäkerheten i punktprognosen, och om
    80-procentsintervallen faktiskt täcker utfallet i fyra fall av fem.
    Det senare är det som avgör om osäkerheten är rätt kalibrerad.
    """
    if historikfil is None:
        historikfil = ROT / "data" / "matningar_historik.csv"
    if not historikfil.exists():
        raise SystemExit(
            f"Saknar {historikfil.relative_to(ROT)}. Hämta den med:\n"
            f"  python3 hamta_matningar.py --fran 2012-01-01")

    df = las_matningar(historikfil)

    print("=" * 70)
    print("  BACKTEST MOT STORTINGSVALEN 2013, 2017, 2021 OCH 2025")
    print("=" * 70)
    print(f"\nUnderlag: {len(df)} mätningar "
          f"{df['datum'].min().date()} till {df['datum'].max().date()}\n")

    print(f"{'DAGAR FÖRE':>11}{'VAL':>5}{'MAE':>8}{'RMSE':>8}"
          f"{'MAXFEL':>9}{'TÄCKNING':>11}")
    print("-" * 70)

    for dagar in (7, 30, 90, 180, 365, 545, 730, 1095):
        fel: list[float] = []
        inom = totalt = antal_val = 0
        for ar, utfall in VALRESULTAT.items():
            valdag = VALDAGAR[ar]
            ref = valdag - timedelta(days=dagar)
            hist = df[df["datum"] <= pd.Timestamp(ref)]
            hist = hist[(pd.Timestamp(ref) - hist["datum"]).dt.days
                        <= cfg.MAX_ALDER_DAGAR]
            if len(hist) < 15:
                continue
            antal_val += 1
            res = kor_prognos(hist, ref, valdag)
            snitt = res["snitt"]
            sm = res["sammanfattning"].set_index("parti")
            for parti in cfg.PARTIER:
                fel.append(snitt[parti] - utfall[parti])
                totalt += 1
                if sm.loc[parti, "p10"] <= utfall[parti] <= sm.loc[parti, "p90"]:
                    inom += 1
        if not fel:
            continue
        felv = np.array(fel)
        tackning = f"{inom / totalt * 100:.0f}%" if totalt else "–"
        print(f"{dagar:>11}{antal_val:>5}{np.abs(felv).mean():>8.2f}"
              f"{np.sqrt((felv ** 2).mean()):>8.2f}"
              f"{np.abs(felv).max():>9.2f}{tackning:>11}")

    print("-" * 70)
    print("MAE och RMSE i procentenheter, snitt över alla partier och val.")
    print("Täckning är andelen utfall som föll inom 80-procentsintervallet,")
    print("och bör därför ligga nära 80 procent om osäkerheten är rätt satt.")

    # Mandatfördelningen mot det senaste valet, som kontroll av hela kedjan.
    print("\n" + "-" * 70)
    print("MANDAT UR FAKTISKT VALRESULTAT 2025")
    print("-" * 70)
    mandat = modell.fordela_mandat(VALRESULTAT[2025])
    avvikelse = sum(abs(mandat[p] - cfg.MANDAT_2025[p]) for p in cfg.PARTIER)
    print(f"{'PARTI':<7}{'MODELL':>8}{'FAKTISKT':>10}{'DIFF':>7}")
    for parti in sorted(cfg.PARTIER, key=lambda p: -mandat[p]):
        diff = mandat[parti] - cfg.MANDAT_2025[parti]
        print(f"{parti:<7}{mandat[parti]:>8}{cfg.MANDAT_2025[parti]:>10}{diff:>+7}")
    print(f"\nTotal avvikelse: {avvikelse} mandat. Noll betyder att "
          f"fördelningen återger valet exakt.\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Svensk valprediktor")
    ap.add_argument("--hamta", action="store_true", help="Tvinga ny hämtning från Wikipedia")
    ap.add_argument("--backtest", action="store_true",
                    help="Utvärdera mot valen 2013 till 2025")
    ap.add_argument("--ingen-html", action="store_true", help="Hoppa över dashboarden")
    ap.add_argument("--korrigera", action="store_true",
                    help="Aktivera historisk valdagskorrigering (V ned, SD upp)")
    args = ap.parse_args()

    if args.backtest:
        backtest()
        return

    fil = ROT / "data" / "matningar.csv"
    if args.hamta or not fil.exists():
        print("Hämtar mätningar från Wikipedia...")
        # skrapa tar sidans titel, inte ett årtal som den svenska versionen.
        df_ny = scraper.skrapa()
        scraper.spara(df_ny, fil)
        print(f"  {len(df_ny)} mätningar sparade.\n")

    df = las_matningar(fil)
    valdag = date.fromisoformat(cfg.VALDAG)
    referensdatum = min(df["datum"].max().date(), date.today())

    korrigera = True if args.korrigera else None
    # Nedräkningen ska följa kalendern, inte senaste mätningens datum.
    res = kor_prognos(df, referensdatum, valdag, korrigera=korrigera,
                      idag=date.today())

    skriv_terminal(res, df)

    if not args.ingen_html:
        # Grafens högerkant ska visa dagens prognos, inte närmaste
        # rutnätspunkt före senaste mätningen.
        trend = modell.trendserie(res["justerad"], slutdatum=date.today())
        matningar = bygg_matningstabell(df, res, referensdatum)
        meta = {
            "dagar_kvar": res["dagar_kvar"],
            "antal_matningar": res["antal_matningar"],
            "antal_institut": df["institut"].nunique(),
            "senaste_matning": df["datum"].max().date().isoformat(),
            "antal_simuleringar": res["sim"]["n"],
            "genererad": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        meta["genererad_iso"] = datetime.now().date().isoformat()
        html = norsk_dashboard.bygg(
            res["sammanfattning"], res["block"], res["regeringar"],
            trend, matningar, meta, res["husfaktorer"])
        ut = norsk_dashboard.spara(html)
        katalog = ut.parent
        print(f"Sidan sparad: {ut}")

        # En sida per parti. Söken efter opinionsdata är partispecifik, så
        # rikssidan ensam möter aldrig den vanligaste frågan.
        import partisida_no
        import seo
        partisidor = partisida_no.skriv_alla(
            res["sammanfattning"], trend, matningar, meta, katalog)
        print(f"  {len(partisidor)} partisidor")

        # Lokalvalet 2027: fylkesting och kommunestyrer. Bygger på förra
        # lokalvalets resultat skalat med riksopinionens förändring, med
        # lokala listor konstanta. Osäkrare än stortingsprognosen, se
        # lokalmodell.py.
        lokala = None
        try:
            import lokalsida
            lokala = lokalsida.skriv_alla(dict(res["snitt"]), katalog)
            print(f"  lokalvalet 2027: {lokala['fylken']} fylken, "
                  f"{lokala['kommuner']} kommuner")
        except Exception as fel:
            print(f"  Lokalvalssidorna kunde inte byggas: {fel}")

        # sitemap.xml och robots.txt. Bara kanoniska adresser tas med.
        idag = date.today().isoformat()
        sidor = [(seo.BAS_URL + "/", idag)]
        sidor += [(seo.partiurl(p), idag) for p in cfg.PARTIER
                  if p in res["sammanfattning"]["parti"].values]
        if lokala:
            sidor += [(a, idag) for a in lokala["adresser"]]
        (katalog / "sitemap.xml").write_text(seo.sitemap(sidor),
                                             encoding="utf-8")
        (katalog / "robots.txt").write_text(seo.robots(), encoding="utf-8")
        print(f"  sitemap.xml med {len(sidor)} adresser, robots.txt\n")


if __name__ == "__main__":
    main()
