# Slutprognos

Prognosen som den såg ut innan valresultatet fanns, fryst för att gå att
utvärdera efteråt. En prognos som skrivs om i efterhand går inte att bedöma.

## Mapparna

Varje mapp är namngiven efter dagen den skapades. `2026-09-11` är
slutprognosen inför valet den 13 september.

| Fil | Innehåll |
|---|---|
| `huvudprognos.csv` | Stöd, mandat och spann per parti, plus sannolikhet över spärren |
| `scenarier.csv` | Samtliga sex scenarier, ett parti per rad |
| `regeringsunderlag.csv` | Block och regeringsalternativ med sannolikheter |
| `matningar.csv` | De mätningar som ligger till grund |
| `kandidatprognos_riksdag.csv` | Vilka personer som tar de 349 mandaten |
| `metadata.json` | Datum, antal mätningar, modellparametrar |
| `facit.csv` | Tom mall att fylla i när resultatet är känt |

## Efter valet

Fyll i `facit.csv` med valresultat och mandat per parti, och kör sedan:

```bash
python3 scripts/slutprognos.py --utvardera
```

Skriptet skriver ut felet per parti, medelabsolutfelet, antalet felplacerade
mandat och en rangordning av hur väl varje scenario träffade. Det sista är
det intressanta: huvudprognosen väger alla mätningar med tjugoen dagars
halveringstid, medan scenarierna prövar andra antaganden.

## Att göra en ny frysning

```bash
python3 scripts/slutprognos.py
```

Skapar en ny mapp med dagens datum. Kör den innan vallokalerna stänger,
annars är det ingen prognos längre.
