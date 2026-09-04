"""Metadata för sökmotorer och delning: canonical, Open Graph, JSON-LD.

Sidorna publiceras på två adresser, GitHub Pages och app.lysio.se. Utan en
canonical-tagg riskerar de att räknas som dubbletter av varandra, och den
adress som råkar indexeras först vinner. Taggen pekar därför alltid på
Lysio-adressen, som är den avsedda.

Beskrivningarna byggs ur prognosen i stället för att vara fasta, så att en
delad länk visar aktuellt läge och inte en text från i somras. Google klipper
beskrivningar vid omkring 158 tecken och titlar vid omkring 60, vilket
_klipp respekterar.

Strukturerad data är JSON-LD, som Google uttryckligen föredrar. Bara sådant
som faktiskt syns på sidan läggs i schemat: strukturerad data som inte
motsvarar innehållet nedvärderas.
"""
from __future__ import annotations

import html as _html
import json
from datetime import date

import config as cfg

# Den kanoniska adressen. GitHub Pages fungerar som spegling.
BAS_URL = "https://app.lysio.se/valprognos"

SIDNAMN = {
    "index.html": "",
    "partier_2026.html": "partier_2026.html",
    "ledamoter_2026.html": "ledamoter_2026.html",
    "scenarier_2026.html": "scenarier_2026.html",
}


def url_for(fil: str) -> str:
    del_ = SIDNAMN.get(fil, fil)
    return f"{BAS_URL}/{del_}" if del_ else f"{BAS_URL}/"


def _klipp(text: str, hogst: int) -> str:
    """Kortar vid ordgräns, så att beskrivningen inte bryts mitt i ett ord."""
    text = " ".join(str(text).split())
    if len(text) <= hogst:
        return text
    kort = text[:hogst].rsplit(" ", 1)[0]
    return kort.rstrip(",.;:") + "…"


def metataggar(titel: str, beskrivning: str, fil: str,
               bildurl: str | None = None) -> str:
    """head-taggarna för en sida."""
    url = url_for(fil)
    titel = _html.escape(_klipp(titel, 60), quote=True)
    beskrivning = _html.escape(_klipp(beskrivning, 158), quote=True)
    delar = [
        f'<link rel="canonical" href="{url}">',
        '<meta name="robots" content="index,follow,max-image-preview:large">',
        f'<meta name="description" content="{beskrivning}">',
        '<meta property="og:type" content="website">',
        '<meta property="og:locale" content="sv_SE">',
        '<meta property="og:site_name" content="Lysio Research">',
        f'<meta property="og:title" content="{titel}">',
        f'<meta property="og:description" content="{beskrivning}">',
        f'<meta property="og:url" content="{url}">',
        f'<meta name="twitter:card" content='
        f'"{"summary_large_image" if bildurl else "summary"}">',
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
        "url": "https://www.lysio.se/",
    }


def strukturerad_data(titel: str, beskrivning: str, fil: str,
                      meta: dict) -> str:
    """JSON-LD: WebPage plus Dataset för prognosen.

    Dataset används eftersom sidan i grunden publicerar en beräkning på ett
    underlag, vilket är vad schemat beskriver.
    """
    url = url_for(fil)
    genererad = str(meta.get("genererad") or "")[:10] or date.today().isoformat()
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebPage",
                "@id": url,
                "url": url,
                "name": _klipp(titel, 110),
                "description": _klipp(beskrivning, 300),
                "inLanguage": "sv-SE",
                "isPartOf": {"@type": "WebSite", "url": f"{BAS_URL}/",
                             "name": "Valprognos 2026"},
                "publisher": _organisation(),
                "dateModified": genererad,
            },
            {
                "@type": "Dataset",
                "name": "Valprognos för riksdagsvalet 2026",
                "description": (
                    f"Sammanvägning av {meta.get('antal_matningar', 0)} "
                    f"opinionsmätningar från {meta.get('antal_institut', 0)} "
                    "institut, justerad för husfaktorer och simulerad till "
                    "mandatfördelning."),
                "license": "https://creativecommons.org/licenses/by/4.0/",
                "creator": _organisation(),
                "dateModified": genererad,
                "temporalCoverage": f"../{cfg.VALDAG}",
                "spatialCoverage": {"@type": "Country", "name": "Sverige"},
            },
        ],
    }
    return ('<script type="application/ld+json">'
            + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            + "</script>")


def riks_beskrivning(sammanfattning, meta: dict, block: dict) -> str:
    """Beskrivning för startsidan, byggd ur aktuell prognos."""
    sm = sammanfattning.set_index("parti")
    kol = "prognos" if "prognos" in sm.columns else "stod_medel"
    topp = sorted(((p, float(sm.at[p, kol])) for p in cfg.PARTIER),
                  key=lambda x: -x[1])[:3]
    lista = ", ".join(f"{p} {v:.1f}%" for p, v in topp)
    dagar = meta.get("dagar_kvar")
    nar = f"{dagar} dagar kvar" if dagar is not None else "inför valet"
    return (f"Prognos för riksdagsvalet 13 september 2026, {nar}. {lista}. "
            f"Bygger på {meta.get('antal_matningar', 0)} mätningar från "
            f"{meta.get('antal_institut', 0)} institut. Även region och kommun.")


def sitemap(filer: list[str], genererad: str | None = None) -> str:
    dag = (genererad or date.today().isoformat())[:10]
    rader = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for fil in filer:
        rader.append(f"  <url><loc>{url_for(fil)}</loc>"
                     f"<lastmod>{dag}</lastmod>"
                     f"<changefreq>daily</changefreq></url>")
    rader.append("</urlset>")
    return "\n".join(rader)


def robots() -> str:
    return ("User-agent: *\n"
            "Allow: /\n\n"
            f"Sitemap: {BAS_URL}/sitemap.xml\n")
