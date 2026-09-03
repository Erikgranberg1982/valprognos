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

# Skriptet ligger i norge/ i publiceringsrepot men i scripts/ i
# utvecklingsträdet. Roten är den katalog som har src/ i sig.
_HAR = Path(__file__).resolve().parent
ROT = _HAR if (_HAR / "src").is_dir() else _HAR.parent
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
    # I publiceringsrepot skrivs sidan till repotets gemensamma output/norge/,
    # alltså en nivå ovanför norge/. Lokalt ligger den i projektets egen
    # output/norge/. NORSK_OUTPUT vinner alltid när den är satt.
    if os_environ_output():
        katalog = Path(os_environ_output())
    else:
        egen = ROT / "output" / "norge"
        katalog = egen if egen.is_dir() else ROT.parent / "output" / "norge"
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
    kontrollera_seo(katalog, html)


def kontrollera_seo(katalog: Path, riks_html: str) -> None:
    """Kontrollerar metadata, strukturerad data, partisidor och sitemap.

    Titel- och beskrivningslängd kontrolleras eftersom Google klipper dem, och
    en klippt titel tappar just de ord som står sist. JSON-LD kontrolleras för
    att den ska gå att tolka: ett syntaxfel gör hela blocket värdelöst.
    """
    import json as _json
    sys.path.insert(0, str(ROT / "src"))
    import seo

    for tagg, namn in (('rel="canonical"', "canonical"),
                       ('property="og:title"', "og:title"),
                       ('name="description"', "description")):
        if tagg not in riks_html:
            FEL.append(f"Rikssidan saknar {namn}.")

    titel = re.search(r"<title>(.*?)</title>", riks_html, re.S)
    if titel and len(titel.group(1)) > 60:
        VARNING.append(f"Titeln är {len(titel.group(1))} tecken och klipps "
                       f"troligen i sökresultatet: {titel.group(1)!r}")
    beskrivning = re.search(r'name="description" content="(.*?)"', riks_html, re.S)
    if beskrivning:
        n = len(beskrivning.group(1))
        if not 100 <= n <= 158:
            VARNING.append(f"Beskrivningen är {n} tecken, målet är 140 till 158.")

    # Strukturerad data ska gå att tolka på varje sida som har den.
    antal_partisidor = 0
    for fil in sorted(katalog.glob("parti/*/index.html")):
        antal_partisidor += 1
        sidhtml = fil.read_text(encoding="utf-8")
        for block in re.findall(
                r'<script type="application/ld\+json">(.*?)</script>',
                sidhtml, re.S):
            try:
                _json.loads(block)
            except ValueError as fel:
                FEL.append(f"Trasig JSON-LD i {fil.parent.name}: {fel}")
        t = re.search(r"<title>(.*?)</title>", sidhtml, re.S)
        if t and len(t.group(1)) > 60:
            VARNING.append(f"Titeln på {fil.parent.name} är "
                           f"{len(t.group(1))} tecken.")
        if "sperregrense" not in sidhtml.lower():
            VARNING.append(f"{fil.parent.name} nämner inte sperregrensen.")

    vantat = len(cfg.PARTIER)
    if antal_partisidor != vantat:
        FEL.append(f"{antal_partisidor} partisidor byggda, väntade {vantat}.")

    # Lokalvalssidorna: 14 fylken och 357 kommuner plus en översikt. Antalen
    # kan ändras vid en kommunreform, så avvikelse är en varning och inte ett
    # fel. Att de saknas helt är däremot ett fel.
    fylkessidor = len(list(katalog.glob("lokalvalg/fylke/*/index.html")))
    kommunsidor = len(list(katalog.glob("lokalvalg/kommune/*/index.html")))
    if not (katalog / "lokalvalg" / "index.html").exists():
        FEL.append("lokalvalg/index.html saknas.")
    if fylkessidor == 0 or kommunsidor == 0:
        FEL.append(f"Lokalvalssidor saknas: {fylkessidor} fylken, "
                   f"{kommunsidor} kommuner.")
    else:
        if fylkessidor != 14:
            VARNING.append(f"{fylkessidor} fylkessidor, väntade 14.")
        if kommunsidor != 357:
            VARNING.append(f"{kommunsidor} kommunsidor, väntade 357.")
        # Mandatsumman per område ska stämma, annars är fördelningen trasig.
        prov = katalog / "lokalvalg" / "kommune" / "bergen" / "index.html"
        if prov.exists() and "kommunestyret" not in prov.read_text(encoding="utf-8"):
            FEL.append("Kommunsidan för Bergen ser inte ut som väntat.")
        print(f"  lokalvalet: {fylkessidor} fylken, {kommunsidor} kommuner")

    lokalsidor = fylkessidor + kommunsidor + (
        1 if (katalog / "lokalvalg" / "index.html").exists() else 0)
    sitemapfil = katalog / "sitemap.xml"
    if not sitemapfil.exists():
        FEL.append("sitemap.xml saknas.")
    else:
        adresser = re.findall(r"<loc>(.*?)</loc>", sitemapfil.read_text(encoding="utf-8"))
        forvantat = vantat + 1 + lokalsidor
        if len(adresser) != forvantat:
            FEL.append(f"sitemap.xml har {len(adresser)} adresser, "
                       f"väntade {forvantat}.")
        for adress in adresser:
            if not adress.startswith(seo.BAS_URL):
                FEL.append(f"sitemap.xml har en adress utanför webbplatsen: "
                           f"{adress}")
    if not (katalog / "robots.txt").exists():
        FEL.append("robots.txt saknas.")

    print(f"  {antal_partisidor} partisidor, sitemap och robots.txt")


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
