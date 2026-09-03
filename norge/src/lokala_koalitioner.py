"""Möjliga styren i fylkesting och kommunestyrer.

Vänster mot höger är för grovt på lokal nivå i Norge. Efter valet 2023 styr
Senterpartiet med Høyre och Fremskrittspartiet i Bergen, och lokala listor
sitter i posisjon i ett stort antal kommuner. Ett block som saknar egen
majoritet säger därför lite om vem som faktiskt kan styra.

Modulen räknar ut vilka konstellationer som når egen majoritet i ett område,
och redovisar dem sorterade efter storlek. Den avgör inte vad som är politiskt
troligt: det beror på personer och lokala förhållanden som ingen modell ser.

## Vad som faktiskt gäller i norska kommuner

Grunden för konstellationerna är observerade mönster efter valet 2023:

  - **Borgerlig sida** (H, FrP, KrF, V) hade egen majoritet i 63 kommuner.
  - **Rødgrønn sida** (Ap, SV, Sp, R, MDG) hade egen majoritet i 148.
  - I resten avgör lokala listor eller blocköverskridande lösningar.
  - Fremskrittspartiet ingick i posisjon med Høyre i nio av tio av sina
    koalitioner, men också med Senterpartiet och Arbeiderpartiet i ungefär
    två av tre. Källa: pollofpolls partiprofiler, som täcker 83 registrerade
    kommuner och fylken, alltså långt ifrån alla 357.
  - Senterpartiet är den vanligaste brobyggaren och sitter i posisjon på båda
    sidor.

Därför redovisas både blockstyren och de blocköverskridande alternativ som
är vanliga i verkligheten. **Lokala listor tas med som möjlig partner**,
eftersom de är kingmaker i många kommuner, men aldrig som ensam ledare av ett
styre annat än när de faktiskt har egen majoritet.
"""
from __future__ import annotations

import config as cfg

LOKALT = "LOKALT"

# Konstellationer som prövas, i den ordning de redovisas. Namnen är på norska
# eftersom de visas på sidan.
#
# Urvalet speglar hur norska kommuner faktiskt styrs, inte alla matematiskt
# möjliga kombinationer: nio partier plus lokala listor ger över tusen
# delmängder, och de flesta är politiskt meningslösa.
KONSTELLATIONER = [
    # Blockstyren.
    {"namn": "Borgerlig side", "partier": ["H", "FrP", "KrF", "V"],
     "beskrivning": "Hele borgerlige siden. Hadde eget flertall i 63 "
                    "kommuner etter valget 2023."},
    {"namn": "Rødgrønn side", "partier": ["Ap", "SV", "Sp", "R", "MDG"],
     "beskrivning": "Hele rødgrønne siden. Hadde eget flertall i 148 "
                    "kommuner etter valget 2023."},

    # Vanliga smalare styren.
    {"namn": "H+FrP", "partier": ["H", "FrP"],
     "beskrivning": "De to store på borgerlig side. Frp satt i posisjon med "
                    "Høyre i ni av ti av sine koalisjoner i 2023."},
    {"namn": "Ap+Sp", "partier": ["Ap", "Sp"],
     "beskrivning": "Den klassiske distriktsalliansen."},
    {"namn": "Ap+SV+Sp", "partier": ["Ap", "SV", "Sp"],
     "beskrivning": "Rødgrønt styre uten R og MDG."},
    {"namn": "H+FrP+KrF", "partier": ["H", "FrP", "KrF"],
     "beskrivning": "Borgerlig styre uten Venstre."},

    # Blocköverskridande, som är vanligt lokalt.
    {"namn": "Ap+H", "partier": ["Ap", "H"],
     "beskrivning": "De to tradisjonelle styringspartiene sammen. Uvanlig "
                    "nasjonalt, men forekommer lokalt."},
    {"namn": "H+FrP+Sp", "partier": ["H", "FrP", "Sp"],
     "beskrivning": "Borgerlig side med Senterpartiet. Slik styres Bergen "
                    "etter valget 2023."},
    {"namn": "Ap+Sp+KrF", "partier": ["Ap", "Sp", "KrF"],
     "beskrivning": "Sentrumsstyre over blokkgrensen."},
    {"namn": "Sentrum: Sp+KrF+V", "partier": ["Sp", "KrF", "V"],
     "beskrivning": "Rene sentrumspartier. Krever et uvanlig sterkt "
                    "sentrum."},
]

# Konstellationer som prövas med lokala listor som partner. Lokala listor är
# kingmaker i många kommuner, så de alternativen är ofta de enda som når
# majoritet.
MED_LOKALA = [
    ("Borgerlig side", ["H", "FrP", "KrF", "V"]),
    ("Rødgrønn side", ["Ap", "SV", "Sp", "R", "MDG"]),
    ("H+FrP", ["H", "FrP"]),
    ("Ap+Sp", ["Ap", "Sp"]),
]


def _mandat(mandat: dict[str, int], partier: list[str]) -> int:
    return sum(mandat.get(p, 0) for p in partier)


def mojliga_styren(mandat: dict[str, int], platser: int,
                   hogst: int = 6) -> list[dict]:
    """Konstellationer som når egen majoritet, störst marginal först.

    Returnerar högst `hogst` alternativ. Ett alternativ som är en delmängd av
    ett redan redovisat och ger samma partier utesluts, eftersom det inte
    tillför något: H+FrP och H+FrP+KrF är olika bara om KrF har mandat.
    """
    behovs = platser // 2 + 1
    ut = []
    sedda: set[frozenset] = set()

    kandidater = [(k["namn"], k["partier"], k.get("beskrivning", ""), False)
                  for k in KONSTELLATIONER]
    # Beskrivningen sätts först när alternativet visas, så att den kan säga
    # hur många mandat de lokala listorna faktiskt bidrar med. Samma text på
    # varje rad vore bara brus.
    kandidater += [(f"{namn} + lokale lister", partier + [LOKALT], None, True)
                   for namn, partier in MED_LOKALA]

    for namn, partier, beskrivning, med_lokala in kandidater:
        # Bara partier som faktiskt har mandat räknas, så att namnet stämmer
        # med vilka som ingår.
        ingar = [p for p in partier if mandat.get(p, 0) > 0]
        if not ingar:
            continue
        nyckel = frozenset(ingar)
        if nyckel in sedda:
            continue
        summa = _mandat(mandat, ingar)
        if summa < behovs:
            continue
        sedda.add(nyckel)
        if beskrivning is None:
            bidrag = mandat.get(LOKALT, 0)
            beskrivning = (
                f"Lokale lister bidrar med {bidrag} "
                f"{'mandat' if bidrag == 1 else 'mandater'} og er nødvendige "
                f"for flertallet.")
        ut.append({
            "namn": namn,
            "partier": ingar,
            "beskrivning": beskrivning,
            "mandat": summa,
            "marginal": summa - behovs,
            "behovs": behovs,
            "med_lokala": med_lokala,
        })

    ut.sort(key=lambda a: (-a["mandat"], len(a["partier"])))
    return ut[:hogst]


def storsta_parti(mandat: dict[str, int]) -> str | None:
    if not mandat:
        return None
    return max(mandat, key=lambda p: mandat.get(p, 0))


def sammanfatta(mandat: dict[str, int], platser: int) -> dict:
    """Beskriver mandatläget: block, lokala listor och möjliga styren."""
    behovs = platser // 2 + 1
    vanster = _mandat(mandat, cfg.BLOCK["vanster"])
    hoger = _mandat(mandat, cfg.BLOCK["hoger"])
    lokalt = mandat.get(LOKALT, 0)

    if vanster >= behovs:
        lage, forklaring = "Rødgrønt flertall", (
            f"Rødgrønn side får {vanster} av {platser} mandater og flertall "
            f"på egen hånd.")
    elif hoger >= behovs:
        lage, forklaring = "Borgerlig flertall", (
            f"Borgerlig side får {hoger} av {platser} mandater og flertall "
            f"på egen hånd.")
    elif lokalt >= behovs:
        lage, forklaring = "Lokale lister i flertall", (
            f"Lokale lister får {lokalt} av {platser} mandater og flertall "
            f"på egen hånd.")
    else:
        storst = ("Rødgrønn" if vanster > hoger
                  else "Borgerlig" if hoger > vanster else "Ingen")
        forklaring = (
            f"Ingen side får {behovs} mandater alene. {storst} side er størst "
            f"med {max(vanster, hoger)} mot {min(vanster, hoger)}")
        if lokalt:
            forklaring += (f", og lokale lister har {lokalt} mandater som kan "
                           f"avgjøre")
        lage = "Vippeposisjon"
        forklaring += "."

    return {
        "lage": lage,
        "forklaring": forklaring,
        "behovs": behovs,
        "vanster": vanster,
        "hoger": hoger,
        "lokalt": lokalt,
        "styren": mojliga_styren(mandat, platser),
    }
