#!/usr/bin/env python3
"""Svensk valprediktor: kör hela kedjan från hämtning till dashboard.

Användning:
    python3 prognos.py              # kör med cachad data om den är färsk
    python3 prognos.py --hamta      # tvinga ny hämtning från Wikipedia
    python3 prognos.py --backtest   # utvärdera modellen mot valet 2022
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import config as cfg
import dashboard
import modell
import scraper

ROT = Path(__file__).resolve().parent.parent

# Institutnamn som bytt namn mellan valcyklerna.
NAMNBYTEN = {"Sifo": "Verian", "Kantar Sifo": "Verian", "Demoskop / Inizio": "Demoskop"}

VALRESULTAT_2022 = {
    "V": 6.75, "S": 30.33, "MP": 5.08, "C": 6.71,
    "L": 4.61, "M": 19.10, "KD": 5.34, "SD": 20.54,
}


def las_matningar(fil: Path) -> pd.DataFrame:
    df = pd.read_csv(fil)
    df["datum"] = pd.to_datetime(df["datum"])
    df["institut"] = df["institut"].replace(NAMNBYTEN)
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


def bygg_lokala_prognoser(res: dict) -> tuple:
    """Bygger region- och kommunprognoser för dashboarden.

    Kräver SCB:s API. Om hämtningen fallerar returneras None så att sidan
    ändå kan byggas med riksdagsprognosen.
    """
    regioner = kommuner = None
    try:
        import regionmodell
        regioner = regionmodell.sammanfatta(
            regionmodell.prognos_per_region(res["snitt"]))
    except Exception as fel:
        print(f"  Kunde inte bygga regionprognos: {fel}")
    try:
        import kommunmodell
        kommuner = kommunmodell.sammanfatta(
            kommunmodell.prognos_per_kommun(res["snitt"]))
    except Exception as fel:
        print(f"  Kunde inte bygga kommunprognos: {fel}")
    return regioner, kommuner


def skriv_terminal(res: dict, df: pd.DataFrame) -> None:
    print("=" * 66)
    print(f"  VALPROGNOS {cfg.VALDAG[:4]}  ·  {res['dagar_kvar']} dagar till valet")
    print("=" * 66)

    print(f"\nUnderlag: {res['antal_matningar']} mätningar, "
          f"{df['institut'].nunique()} institut, "
          f"senaste {df['datum'].max().date()}\n")

    print(f"{'PARTI':<6}{'PROGNOS':>9}{'MOT 2022':>10}{'80%-SPANN':>13}"
          f"{'MANDAT':>8}{'MOT 2022':>10}")
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
        print(f"{b['namn']:<14}{b['mandat_median']:>4} mandat ({andring:>3} mot 2022) "
              f"spann {b['mandat_p10']}–{b['mandat_p90']}   "
              f"majoritet: {b['sannolikhet_majoritet']*100:>5.1f}%")
    print(f"{'Inget block':<14}{'':>4}              "
          f"     ingen majoritet: {res['block']['oavgjort']*100:>5.1f}%")

    print("\n" + "-" * 66)
    print("REGERINGSALTERNATIV  (sannolikhet att nå 175 mandat)")
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


def kor_lokal_prognos(res: dict, niva: str, omrade: str | None = None) -> None:
    """Skriver ut region- eller kommunvalsprognos.

    Båda nivåerna bygger på riksdagsprognosen: den regionala profilen och
    differensen mellan lokalval och riksdagsval översätter rikstrenden till
    lokala förhållanden. Det finns inga opinionsmätningar per region eller
    kommun, så prognosen är osäkrare än riksdagsprognosen.
    """
    if niva == "region":
        import regionmodell as modul
        rubrik = "REGIONVALSPROGNOS"
        prognos_df = modul.prognos_per_region(res["snitt"])
    else:
        import kommunmodell as modul
        rubrik = "KOMMUNVALSPROGNOS"
        prognos_df = modul.prognos_per_kommun(res["snitt"])

    sammanfattning = modul.sammanfatta(prognos_df)

    if omrade:
        trafffilter = sammanfattning["namn"].str.contains(omrade, case=False, na=False)
        if not trafffilter.any():
            print(f"Hittade inget område som matchar {omrade!r}.")
            forslag = ", ".join(sammanfattning["namn"].head(8))
            print(f"Exempel på områden: {forslag} ...")
            return
        sammanfattning = sammanfattning[trafffilter]

    partier = [p for p in cfg.PARTIER] + ["ÖVRIGA"]

    print("=" * 78)
    print(f"  {rubrik}  ·  {res['dagar_kvar']} dagar till valet")
    print("=" * 78)
    print(f"\nBygger på riksdagsprognosen plus historiska differenser mellan "
          f"{niva}val\noch riksdagsval. Lokala partier redovisas samlat som ÖVRIGA "
          f"och hålls\nkonstanta på förra valets nivå.\n")

    if len(sammanfattning) <= 25:
        rubrikrad = "OMRÅDE".ljust(22) + "".join(p.rjust(7) for p in partier)
        print(rubrikrad)
        print("-" * len(rubrikrad))
        for _, rad in sammanfattning.iterrows():
            namn = str(rad["namn"])[:21].ljust(22)
            varden = "".join(f"{rad[f'stod_{p}']:7.1f}" for p in partier)
            rad_text = namn + varden
            if rad.get("lokalt_parti"):
                rad_text += (f"   {rad['lokalt_parti']} "
                             f"{rad['lokalt_stod']:.1f}%"
                             f"{'' if rad.get('lokalt_matt') else ' (skalat)'}")
            print(rad_text)

        print("\n" + "-" * 78)
        print("STYRE  (mandat vänster mot höger, övriga inom parentes)")
        print("-" * 78)
        for _, rad in sammanfattning.iterrows():
            if rad["vanster_majoritet"]:
                styre = "vänstermajoritet"
            elif rad["hoger_majoritet"]:
                styre = "högermajoritet"
            else:
                styre = "vågmästarläge"
            dv = (f"{int(rad['diff_vanster']):+d}"
                  if rad.get("diff_vanster") is not None else "–")
            dh = (f"{int(rad['diff_hoger']):+d}"
                  if rad.get("diff_hoger") is not None else "–")
            print(f"{str(rad['namn'])[:24]:26s}"
                  f"{int(rad['mandat_vanster']):3d} ({dv:>3}) - "
                  f"{int(rad['mandat_hoger']):3d} ({dh:>3})"
                  f"  utanför {int(rad['mandat_ovriga']):2d}"
                  f"  av {int(rad['mandat_totalt']):3d}   {styre}")
    else:
        # För 290 kommuner blir en full tabell oläslig; sammanfatta i stället.
        print(f"{len(sammanfattning)} kommuner prognosticerade.\n")
        print("STYRE")
        print("-" * 40)
        print(f"  Vänstermajoritet {int(sammanfattning['vanster_majoritet'].sum()):4d}")
        print(f"  Högermajoritet   {int(sammanfattning['hoger_majoritet'].sum()):4d}")
        print(f"  Vågmästarläge    {int(sammanfattning['vagmastare'].sum()):4d}")

        print("\nTio kommuner med starkast lokala partier")
        print("-" * 62)
        for _, rad in sammanfattning.nlargest(10, "stod_ÖVRIGA").iterrows():
            print(f"  {str(rad['namn'])[:22]:24s}{rad['stod_ÖVRIGA']:5.1f}%  "
                  f"{int(rad['mandat_ovriga']):2d} av {int(rad['mandat_totalt']):3d} mandat")

        print("\nAnvänd --omrade NAMN för att se en enskild kommun.")

    print()


def backtest() -> None:
    """Utvärderar modellen mot det faktiska valresultatet 2022."""
    fil = ROT / "data" / "matningar_2022.csv"
    if not fil.exists():
        print("Hämtar 2022 års mätningar...")
        scraper.spara(scraper.skrapa(2022), 2022)

    df = las_matningar(fil)
    valdag = date(2022, 9, 11)

    print("=" * 66)
    print("  BACKTEST MOT VALET 2022")
    print("=" * 66)
    print(f"\n{'DAGAR FÖRE':>11}{'MAE':>8}{'MAX FEL':>10}{'BLOCKFEL':>11}{'TÄCKNING':>11}")
    print("-" * 66)

    for dagar in (7, 14, 30, 60, 90, 180, 365):
        ref = valdag - timedelta(days=dagar)
        hist = df[df["datum"] <= pd.Timestamp(ref)]
        if len(hist) < 15:
            continue
        res = kor_prognos(hist, ref, valdag)
        snitt = res["snitt"]

        fel = [abs(snitt[p] - VALRESULTAT_2022[p]) for p in cfg.PARTIER]
        vanster_prognos = sum(snitt[p] for p in cfg.BLOCK["vanster"])
        vanster_utfall = sum(VALRESULTAT_2022[p] for p in cfg.BLOCK["vanster"])

        sm = res["sammanfattning"].set_index("parti")
        inom = sum(1 for p in cfg.PARTIER
                   if sm.loc[p, "p10"] <= VALRESULTAT_2022[p] <= sm.loc[p, "p90"])

        print(f"{dagar:>11}{np.mean(fel):>8.2f}{max(fel):>10.2f}"
              f"{vanster_prognos - vanster_utfall:>+11.2f}{f'{inom}/8':>11}")

    # Detaljerad jämförelse på valdagen.
    ref = valdag - timedelta(days=1)
    res = kor_prognos(df[df["datum"] <= pd.Timestamp(ref)], ref, valdag)
    snitt = res["snitt"]
    mandat_prognos = modell.fordela_mandat(dict(snitt))
    mandat_utfall = modell.fordela_mandat(VALRESULTAT_2022)

    print("\n" + "-" * 66)
    print("SISTA MÄTNINGEN FÖRE VALET")
    print("-" * 66)
    print(f"{'PARTI':<7}{'PROGNOS':>9}{'UTFALL':>9}{'FEL':>8}"
          f"{'MANDAT':>9}{'FAKTISKT':>10}")
    for p in cfg.PARTIER:
        print(f"{p:<7}{snitt[p]:>8.1f}%{VALRESULTAT_2022[p]:>8.1f}%"
              f"{snitt[p] - VALRESULTAT_2022[p]:>+8.2f}"
              f"{mandat_prognos[p]:>9}{mandat_utfall[p]:>10}")

    vp = sum(mandat_prognos[p] for p in cfg.BLOCK["vanster"])
    vu = sum(mandat_utfall[p] for p in cfg.BLOCK["vanster"])
    print(f"\n{'Block V+S+MP+C':<25}{vp:>9} mandat mot faktiska {vu}")
    print(f"{'Medelabsolutfel':<25}"
          f"{np.mean([abs(snitt[p] - VALRESULTAT_2022[p]) for p in cfg.PARTIER]):>9.2f} "
          f"procentenheter\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Svensk valprediktor")
    ap.add_argument("--hamta", action="store_true", help="Tvinga ny hämtning från Wikipedia")
    ap.add_argument("--backtest", action="store_true", help="Utvärdera mot valet 2022")
    ap.add_argument("--ingen-html", action="store_true", help="Hoppa över dashboarden")
    ap.add_argument("--korrigera", action="store_true",
                    help="Aktivera historisk valdagskorrigering (V ned, SD upp)")
    ap.add_argument("--niva", choices=["riksdag", "region", "kommun"],
                    default="riksdag",
                    help="Vilket val som ska prognosticeras (standard: riksdag)")
    ap.add_argument("--omrade", metavar="NAMN",
                    help="Visa bara ett område, t.ex. --omrade Skåne")
    ap.add_argument("--kandidater", nargs="?", const="alla",
                    choices=["alla", "riksdag", "region", "kommun"],
                    help=("Hämta vallistor och skriv kandidatprognos. "
                          "Utan nivå skrivs alla tre valen."))
    ap.add_argument("--tvinga-vallistor", action="store_true",
                    help="Tvinga ny hämtning av kandidaturer från Valmyndigheten")
    args = ap.parse_args()

    if args.backtest:
        backtest()
        return

    fil = ROT / "data" / "matningar.csv"
    if args.hamta or not fil.exists():
        print("Hämtar mätningar från Wikipedia...")
        df_ny = scraper.skrapa(2026)
        scraper.spara(df_ny, 2026)
        print(f"  {len(df_ny)} mätningar sparade.\n")

    df = las_matningar(fil)
    valdag = date.fromisoformat(cfg.VALDAG)
    referensdatum = min(df["datum"].max().date(), date.today())

    korrigera = True if args.korrigera else None
    # Nedräkningen ska följa kalendern, inte senaste mätningens datum.
    res = kor_prognos(df, referensdatum, valdag, korrigera=korrigera,
                      idag=date.today())

    if args.kandidater:
        import vallistor
        vald_niva = None if args.kandidater == "alla" else args.kandidater
        utfiler = vallistor.skriv_kandidatprognoser(
            res, niva=vald_niva, omrade=args.omrade,
            tvinga_vallistor=args.tvinga_vallistor)
        vallistor.skriv_terminal(utfiler)

    if args.niva in ("region", "kommun"):
        kor_lokal_prognos(res, args.niva, args.omrade)
        return

    skriv_terminal(res, df)

    if not args.ingen_html:
        # Grafens högerkant ska visa dagens prognos, inte närmaste
        # rutnätspunkt före senaste mätningen.
        trend = modell.trendserie(res["justerad"], slutdatum=date.today())
        matningar = bygg_matningstabell(df, res, referensdatum)
        try:
            import kommunmodell as _km
            valkretsar = _km.prognos_per_valkrets(res["snitt"])
        except Exception:
            valkretsar = None
        regioner, kommuner = bygg_lokala_prognoser(res)
        meta = {
            "dagar_kvar": res["dagar_kvar"],
            "antal_matningar": res["antal_matningar"],
            "antal_institut": df["institut"].nunique(),
            "senaste_matning": df["datum"].max().date().isoformat(),
            "antal_simuleringar": res["sim"]["n"],
            "genererad": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        html, kommun_json = dashboard.bygg(
            res["sammanfattning"], res["block"], res["regeringar"],
            trend, res["husfaktorer"], matningar, meta,
            regioner=regioner, kommuner=kommuner, valkretsar=valkretsar)
        kandidat_json = None
        try:
            import json as _json
            import kandidater as _kand
            kandidat_json = _json.dumps(
                {"kommun": _kand.per_omrade("kommun"),
                 "region": _kand.per_omrade("region")},
                ensure_ascii=False, separators=(",", ":"))
        except Exception:
            pass
        ut = dashboard.spara(html, kommun_json, kandidat_json)

        # Fristående sidor: lista över ledamöterna och en sida per parti.
        try:
            import ledamotslista
            ledamotslista.skriv(ROT / "output")
        except Exception:
            pass
        try:
            import partisida
            partisida.skriv(ROT / "output", res["sammanfattning"], trend, meta)
        except Exception as fel:
            print(f"  Partisidan kunde inte byggas: {fel}")
        try:
            import scenariosida
            scenariosida.skriv(ROT / "output", res["snitt"], meta, df)
        except Exception as fel:
            print(f"  Scenariosidan kunde inte byggas: {fel}")
        print(f"Dashboard sparad: {ut}\n")


if __name__ == "__main__":
    main()
