"""Sökmotoroptimering: metadata, strukturerad data, sitemap och partisidor.

Grundas på tre observationer om vad norrmän faktiskt söker på, lästa ur
konkurrenternas URL-struktur och nyhetsrubrikernas ordval:

  1. **Söken är partispecifik.** "Frp meningsmåling", "Høyre oppslutning".
     politpro.eu har `/norge/partier/fremskrittspartiet` och pollofpolls har
     "Partiprofilen Fremskrittspartiet". Rikssidan möter aldrig den söken.
  2. **Sperregrensen är en egen fråga.** "Klarer KrF sperregrensen",
     "Venstre under sperregrensen". Nyhetsrubrikerna använder de orden
     ordagrant. Vår modell svarar med en sannolikhet, vilket ingen
     nyhetsartikel gör.
  3. **Orden är norska, inte svenska.** meningsmåling, oppslutning,
     partibarometer, mandater, sperregrense. Inte mätning, stöd, mandat.

Observera att detta är sökordsval på observerad evidens, inte på mätt
sökvolym: Google Trends svarade inte och vi har ingen Keyword Planner-åtkomst.
Prioriteringen bygger alltså på att konkurrenter och redaktioner valt orden,
vilket är ett indirekt men rimligt mått.

Metadata följer Googles nuvarande riktlinjer: titel 50 till 60 tecken,
beskrivning 140 till 158. Strukturerad data är JSON-LD, som Google
uttryckligen föredrar. Ingen påhittad data läggs i schemat: Google
nedvärderar strukturerad data som inte motsvarar det synliga innehållet.
"""
from __future__ import annotations

import html as html_mod
import json
from datetime import date, datetime

import config as cfg

# Publiceringsadressen. Sidan ligger som undersida till den svenska.
BAS_URL = "https://erikgranberg1982.github.io/valprognos/norge"

# URL-slug per parti. Fullständigt partinamn, som konkurrenterna använder,
# eftersom söken oftare skrivs ut än förkortas för de mindre partierna.
SLUG = {
    "R": "rodt",
    "SV": "sosialistisk-venstreparti",
    "Ap": "arbeiderpartiet",
    "Sp": "senterpartiet",
    "MDG": "miljopartiet-de-gronne",
    "KrF": "kristelig-folkeparti",
    "V": "venstre",
    "H": "hoyre",
    "FrP": "fremskrittspartiet",
}

# Vanliga kortformer som folk söker på, för att kunna nämnas i texten.
KORTNAMN = {
    "R": "Rødt", "SV": "SV", "Ap": "Ap", "Sp": "Sp", "MDG": "MDG",
    "KrF": "KrF", "V": "Venstre", "H": "Høyre", "FrP": "Frp",
}


def partiurl(parti: str) -> str:
    return f"{BAS_URL}/parti/{SLUG[parti]}/"


def _klipp(text: str, hogst: int) -> str:
    """Kortar en beskrivning vid ordgräns så att den inte klipps i sökresultatet."""
    text = " ".join(text.split())
    if len(text) <= hogst:
        return text
    kort = text[:hogst].rsplit(" ", 1)[0]
    return kort.rstrip(",.;:") + "."


def metataggar(titel: str, beskrivning: str, url: str,
               bildurl: str | None = None) -> str:
    """Bygger head-taggarna: canonical, Open Graph och Twitter-kort.

    Canonical pekar alltid på den egna adressen. Sidan publiceras bara på ett
    ställe, men taggen skyddar mot att en spegling eller en adress med
    frågeparametrar indexeras i stället.
    """
    titel = html_mod.escape(titel, quote=True)
    beskrivning = html_mod.escape(_klipp(beskrivning, 158), quote=True)
    delar = [
        f'<link rel="canonical" href="{url}">',
        '<meta name="robots" content="index,follow,max-image-preview:large">',
        f'<meta name="description" content="{beskrivning}">',
        # Open Graph styr hur länken ser ut när den delas, vilket är den
        # vanligaste spridningsvägen för den här typen av sida.
        '<meta property="og:type" content="website">',
        '<meta property="og:locale" content="nb_NO">',
        '<meta property="og:site_name" content="Lysio Research">',
        f'<meta property="og:title" content="{titel}">',
        f'<meta property="og:description" content="{beskrivning}">',
        f'<meta property="og:url" content="{url}">',
        f'<meta name="twitter:card" content="{"summary_large_image" if bildurl else "summary"}">',
        f'<meta name="twitter:title" content="{titel}">',
        f'<meta name="twitter:description" content="{beskrivning}">',
    ]
    if bildurl:
        delar.append(f'<meta property="og:image" content="{bildurl}">')
        delar.append(f'<meta name="twitter:image" content="{bildurl}">')
    return "\n".join(delar)


def _organisation() -> dict:
    return {
        "@type": "Organization",
        "name": "Lysio Research",
        "url": "https://lysio.se",
    }


def strukturerad_data_riks(sammanfattning, meta: dict,
                           valdag: date) -> str:
    """JSON-LD för rikssidan: Dataset plus WebPage.

    Dataset är rätt typ: sidan publicerar ett räknat underlag med angivna
    källor, inte en artikel. Fälten speglar det som faktiskt står på sidan,
    ingenting påhittat.
    """
    rader = sammanfattning.to_dict("records")
    variabler = [f"{r['parti']} {r['prognos']:.1f} %" for r in rader]

    dataset = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": f"Valgprognose for stortingsvalget {valdag.year}",
        "description": (
            f"Prognose for stortingsvalget {valdag.year} basert på "
            f"{meta['antal_matningar']} meningsmålinger fra "
            f"{meta['antal_institut']} byråer. Mandatene beregnes i alle 19 "
            f"valgdistrikter etter valgloven, med St. Laguës modifiserte "
            f"metode og sperregrense bare for utjevningsmandatene."),
        "url": f"{BAS_URL}/",
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "creator": _organisation(),
        "dateModified": meta.get("genererad_iso", date.today().isoformat()),
        "temporalCoverage": f"2025-09-08/{valdag.isoformat()}",
        "spatialCoverage": {"@type": "Place", "name": "Norge"},
        "variableMeasured": variabler,
        "isAccessibleForFree": True,
        "citation": [
            "https://www.pollofpolls.no/",
            "https://www.ssb.no/statbank/table/08092",
            "https://lovdata.no/lov/2002-06-28-57",
        ],
    }
    return f'<script type="application/ld+json">{json.dumps(dataset, ensure_ascii=False, separators=(",", ":"))}</script>'


def strukturerad_data_fragor(fragor: list[tuple[str, str]]) -> str:
    """JSON-LD FAQPage.

    Frågorna måste finnas synligt på sidan med samma svar. Ett schema som
    beskriver innehåll som inte syns räknas som vilseledande.
    """
    if not fragor:
        return ""
    data = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": f,
             "acceptedAnswer": {"@type": "Answer", "text": s}}
            for f, s in fragor
        ],
    }
    return f'<script type="application/ld+json">{json.dumps(data, ensure_ascii=False, separators=(",", ":"))}</script>'


def strukturerad_data_brodsmulor(steg: list[tuple[str, str]]) -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": namn, "item": url}
            for i, (namn, url) in enumerate(steg)
        ],
    }
    return f'<script type="application/ld+json">{json.dumps(data, ensure_ascii=False, separators=(",", ":"))}</script>'


# --- Sidtexter ---------------------------------------------------------------

# Titlarna får suffixet " · Lysio Research" i sidmallarna. Det räknas in i
# den längd Google visar, så budgeten för själva titeln är 60 minus suffixet.
SUFFIX_LANGD = len(" · Lysio Research")
TITEL_MAX = 60 - SUFFIX_LANGD


def _valj_titel(kandidater: list[str]) -> str:
    """Väljer den längsta titeln som ryms, annars den kortaste kandidaten.

    Längre är bättre så länge den inte klipps: en titel som utnyttjar
    utrymmet bär fler sökord.
    """
    rymmer = [k for k in kandidater if len(k) <= TITEL_MAX]
    if rymmer:
        return max(rymmer, key=len)
    return min(kandidater, key=len)


def riks_titel(valdag: date, storsta: str, storsta_procent: float) -> str:
    """Titel för rikssidan.

    Bär de tre orden som söks mest: valgprognose, stortingsvalget, året. Det
    största partiets namn läggs till eftersom söken ofta är partispecifik och
    titeln då matchar även en partisök.
    """
    kort = KORTNAMN.get(storsta, storsta)
    return _valj_titel([
        f"Valgprognose stortingsvalget {valdag.year}: {kort} størst",
        f"Valgprognose {valdag.year}: meningsmålinger og mandater",
        f"Valgprognose stortingsvalget {valdag.year}",
    ])


def riks_beskrivning(sammanfattning, meta: dict, block: dict,
                     valdag: date) -> str:
    """Beskrivning för rikssidan, 140 till 158 tecken.

    Innehåller en konkret siffra, eftersom en beskrivning med ett faktiskt tal
    får fler klick än en allmän formulering.
    """
    storsta = sammanfattning.iloc[0]
    kort = KORTNAMN.get(storsta["parti"], storsta["parti"])
    procent = f"{storsta['prognos']:.1f}".replace(".", ",")
    return _klipp(
        f"{kort} størst med {procent} % og {int(storsta['mandat_median'])} "
        f"mandater. Oppdatert prognose for stortingsvalget {valdag.year} fra "
        f"{meta['antal_matningar']} meningsmålinger, med mandater beregnet i "
        f"alle 19 valgdistrikter.", 158)


def parti_titel(parti: str, prognos: float) -> str:
    """Titel för en partisida.

    Formen "<Parti> meningsmåling 2029" matchar den vanligaste söken direkt.
    """
    kort = KORTNAMN.get(parti, parti)
    namn = cfg.PARTINAMN[parti]
    ar = date.fromisoformat(cfg.VALDAG).year

    # Både fullnamn och kortform ska med när de ryms, eftersom söken sker på
    # båda: "Arbeiderpartiet meningsmåling" och "Ap meningsmåling". Att välja
    # bort fullnamnet för att få plats med utfyllnadsord vore fel prioritering,
    # fullnamnet är det starkare sökordet.
    kandidater = []
    if kort.lower() != namn.lower():
        kandidater.append(f"{namn} ({kort}) meningsmåling {ar}")
    kandidater += [
        f"{namn} meningsmåling {ar}",
        f"{kort} meningsmåling og oppslutning {ar}",
        f"{kort} meningsmåling {ar}",
    ]
    return _valj_titel(kandidater)


def parti_beskrivning(parti: str, rad, valdag: date) -> str:
    kort = KORTNAMN.get(parti, parti)
    procent = f"{rad['prognos']:.1f}".replace(".", ",")
    over = rad["sannolikhet_over_sparr"]
    if over >= 0.98:
        sparr = "trygt over sperregrensen"
    elif over <= 0.02:
        sparr = "under sperregrensen"
    else:
        sparr = (f"{cfg.formatera_sannolikhet(over)} sjanse for å klare "
                 f"sperregrensen")
    return _klipp(
        f"{kort} ligger på {procent} % og {int(rad['mandat_median'])} mandater "
        f"i prognosen for stortingsvalget {valdag.year}, {sparr}. Oppdatert "
        f"snitt av meningsmålingene.", 158)


def parti_fragor(parti: str, rad, valdag: date) -> list[tuple[str, str]]:
    """Frågor och svar som besvarar de faktiska sökfrågorna.

    Formuleringarna följer hur frågan ställs i söken och i nyhetsrubrikerna:
    "klarer X sperregrensen", "hvor mange mandater får X".
    """
    kort = KORTNAMN.get(parti, parti)
    namn = cfg.PARTINAMN[parti]
    procent = f"{rad['prognos']:.1f}".replace(".", ",")
    p10 = f"{rad['p10']:.1f}".replace(".", ",")
    p90 = f"{rad['p90']:.1f}".replace(".", ",")
    over = rad["sannolikhet_over_sparr"]
    forra = cfg.VALRESULTAT_2025.get(parti)
    forra_txt = f"{forra:.2f}".replace(".", ",") if forra else "–"

    fragor = [
        (f"Hva viser meningsmålingene for {namn} nå?",
         f"{kort} ligger på {procent} prosent i det vektede snittet av "
         f"meningsmålingene. Intervallet som dekker fire av fem utfall i "
         f"simuleringen går fra {p10} til {p90} prosent. Ved stortingsvalget "
         f"2025 fikk partiet {forra_txt} prosent."),
        (f"Hvor mange mandater får {kort} ved stortingsvalget {valdag.year}?",
         f"Prognosen gir {kort} {int(rad['mandat_median'])} mandater, med et "
         f"intervall fra {int(rad['mandat_p10'])} til "
         f"{int(rad['mandat_p90'])}. Mandatene beregnes i alle 19 "
         f"valgdistrikter etter valgloven, ikke ut fra landsandelen alene."),
    ]

    # Sperregrensefrågan är bara meningsfull för partier den kan avgöra för.
    if over < 0.98:
        if over <= 0.02:
            svar = (f"Prognosen gir {kort} under fire prosent. Partiet mister "
                    f"da utjevningsmandatene, men beholder de "
                    f"distriktsmandatene det vinner på egen styrke. ")
        else:
            svar = (f"Sannsynligheten for at {kort} kommer over fire prosent "
                    f"er {cfg.formatera_sannolikhet(over)} i simuleringen. ")
        svar += ("Sperregrensen gjelder bare utjevningsmandatene. Et parti "
                 "under grensen kan fortsatt vinne distriktsmandater: Venstre "
                 "fikk tre mandater i 2025 med 3,69 prosent.")
        fragor.insert(1, (f"Klarer {kort} sperregrensen?", svar))

    return fragor


def riks_fragor(sammanfattning, block: dict, meta: dict,
                valdag: date) -> list[tuple[str, str]]:
    """Frågor för rikssidan. Besvarar de breda söken om valet som helhet."""
    storsta = sammanfattning.iloc[0]
    kort = KORTNAMN.get(storsta["parti"], storsta["parti"])
    v, h = block["vanster"], block["hoger"]
    ledande = v if v["mandat_median"] >= h["mandat_median"] else h

    nara = [r for _, r in sammanfattning.iterrows()
            if 0.02 < r["sannolikhet_over_sparr"] < 0.98]
    nara_txt = ", ".join(
        f"{KORTNAMN.get(r['parti'], r['parti'])} "
        f"({cfg.formatera_sannolikhet(r['sannolikhet_over_sparr'])})"
        for r in nara) or "ingen partier"

    return [
        (f"Hvilket parti er størst på meningsmålingene?",
         f"{kort} er størst med {f'{storsta.prognos:.1f}'.replace('.', ',')} "
         f"prosent i det vektede snittet av {meta['antal_matningar']} "
         f"meningsmålinger fra {meta['antal_institut']} byråer."),
        ("Hvem får flertall ved stortingsvalget?",
         f"{ledande['namn']} ligger nå an til {ledande['mandat_median']} "
         f"mandater, og får flertall i "
         f"{cfg.formatera_sannolikhet(ledande['sannolikhet_majoritet'])} av "
         f"simuleringene. Det trengs {cfg.MAJORITET} av 169 mandater for "
         f"flertall."),
        ("Hvilke partier ligger nær sperregrensen?",
         f"Sperregrensen er uavgjort for {nara_txt}. Grensen på fire prosent "
         f"gjelder bare utjevningsmandatene, så et parti under grensen kan "
         f"likevel vinne distriktsmandater."),
        ("Hvordan beregnes mandatene?",
         "Landstrenden skaleres til alle 19 valgdistrikter med hvert "
         "distrikts historiske profil. Deretter fordeles 150 "
         "distriktsmandater med St. Laguës modifiserte metode og første "
         "delingstall 1,4, uten sperregrense, og 19 utjevningsmandater bare "
         "mellom partier over fire prosent. Metoden gjengir stortingsvalgene "
         "2021 og 2025 eksakt."),
    ]


# --- Sitemap och robots -----------------------------------------------------

def sitemap(sidor: list[tuple[str, str]]) -> str:
    """Bygger sitemap.xml. `sidor` är par av adress och lastmod-datum.

    Bara indexerbara kanoniska adresser tas med, vilket är hela poängen med
    filen: den ska inte ge motstridiga signaler mot robots.txt.
    """
    rader = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url, lastmod in sidor:
        rader.append(f"  <url><loc>{url}</loc>"
                     f"<lastmod>{lastmod}</lastmod></url>")
    rader.append("</urlset>")
    return "\n".join(rader) + "\n"


def robots() -> str:
    """robots.txt. Blockerar ingenting: sidan har inget som inte ska indexeras.

    Sitemap-adressen anges här, eftersom det är den plats sökmotorerna letar
    på först.
    """
    return ("User-agent: *\n"
            "Allow: /\n"
            f"\nSitemap: {BAS_URL}/sitemap.xml\n")
