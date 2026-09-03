# Datakällor för den norska prognosen

Allt nedan är testat och fungerar per 2026-09-03.

## Val av källa för opinionsmätningar

Två källor är utredda. **Wikipedia används**, av tre skäl:

1. **Urvalsstorlek finns med.** pollofpolls CSV har ingen urvalskolumn alls.
   Modellen viktar mätningar efter urval, så utan den siffran måste varje
   mätning tilldelas institutets typiska urval, vilket är en gissning.
2. **Fältarbetsperiod i stället för publiceringsdatum.** Wikipedia anger
   perioden, till exempel 10 till 16 augusti. Mätningen viktas mot periodens
   mittdatum, vilket är den tidpunkt siffran faktiskt beskriver. pollofpolls
   anger bara ett datum.
3. **Svarsfrekvens finns för en del mätningar.** Används inte i dag men är
   användbart vid kalibrering av institutsvikter.

Wikipedia hänvisar i sin tur till pollofpolls för siffrorna, så källan är
**inte oberoende**. Det är samma underliggande data i bättre struktur. Ett
verkligt oberoende alternativ finns inte: instituten publicerar inte sina
mätningar som data, utan bara som artiklar hos uppdragsgivaren, och
forskningsdata från ISF och Norsk medborgerpanel har år av eftersläpning och
mäter inte partisympati veckovis.

**Verifiering.** De mätningar som finns i båda källorna har jämförts. För
Norstat, Verian, Norfakta och Respons Analyse är siffrorna identiska på
decimalen. `src/hamta_matningar.py` läser pollofpolls och behålls just för att
kunna göra om den jämförelsen när något ser fel ut.

## Wikipedia, den källa som används

`src/scraper.py`. Skrapar wikitext via MediaWikis API, inte renderad HTML:
wikitexten ändras bara när någon redigerar tabellen, medan HTML också ändras
när Wikipedia byter mallar.

```
https://en.wikipedia.org/w/api.php?action=parse&page=2029_Norwegian_parliamentary_election&prop=wikitext&format=json&formatversion=2
```

Sidan har en tabell per år under rubriker som `=== 2026 ===`. Kolumnordningen
är **R, SV, MDG, Ap, Sp, V, KrF, H, FrP**, alltså vänster till höger politiskt
och inte den ordning `config.PARTIER` använder.

Format att hantera, allt implementerat och testat:

- Fältarbetsperioden står i mallen `{{opdrts|10|16|August|2026}}`. Tre
  varianter förekommer och alla måste hanteras:
  - `{{opdrts|10|16|August|2026}}` är ett vanligt intervall.
  - `{{opdrts||2|Mar|2026}}` med tom första dag är en enda dag.
  - `{{opdrts|23|2|Mar|2026}}` spänner över ett månadsskifte och betyder
    23 februari till 2 mars. Månaden i mallen är slutmånaden.
- Månadsnamnen förkortas oftast till tre bokstäver, `Apr` inte `April`.
  Missas det tappas fyra femtedelar av mätningarna, vilket var det första
  felet i implementationen.
- Varje particell är `procent<br />{{font|...|text=mandat}}`. Mandattalet är
  pollofpolls egen fördelning och kastas, vi räknar mandat själva i mandat.py.
- Småpartier ligger gömda i `{{Hide|...}}` inuti Andre-cellen och måste
  strippas innan övrig markup, annars läcker deras siffror in.
- Urvalet skrivs med tusentalskomma, `1,000`.
- Svarsfrekvensen kan vara `{{NA}}`.

Täckning per 2026-09-03: 71 mätningar från 2025-10-01 och framåt, sex
institut. Fyra mätningar saknar urvalsstorlek och får då institutets typiska
urval.

## pollofpolls.no, används för kontroll

`src/hamta_matningar.py`. Öppna CSV-endpoints, ingen HTML-skrapning behövs.
Kräver webbläsar-User-Agent. **Teckenkodningen är latin-1, inte UTF-8.**

```
https://www.pollofpolls.no/lastned.csv?tabell=liste_galluper&type=riks&start=2025-01-01&slutt=2026-09-03&kommuneid=0
```

- Två rader förord före rubrikraden.
- `Måling` innehåller institut och uppdragsgivare separerade med `/`.
- `Dato` är `D/M-ÅÅÅÅ`, dag först och utan inledande nolla.
- Partikolumner är `procent (mandat)` med decimalkomma.

Historik: enskilda mätningar finns minst från 2013, alltså fyra valcykler
(2013, 2017, 2021, 2025). **Detta är källan för backtest**, eftersom
Wikipedias 2029-sida bara täcker innevarande cykel. Motsvarande
Wikipediasidor finns per valår om urvalsstorlekar behövs även bakåt.

### Övriga endpoints

| Tabell | Innehåll |
|---|---|
| `liste_galluper` | Enskilda mätningar. Huvudkällan för backtest |
| `gallupsnitttabell` | Månadssnitt, `int=m`, från 2000 |
| `valgresultater_historisk` | Valresultat 1945 och framåt, riks eller `type=fylke&kommuneid=NN` |
| `storting_utjevning_siste_galluper` | Utjämningsmandat per fylke enligt senaste mätningar |

### Institut som mäter, sett i data 2025-2026

| Institut | Antal | Uppdragsgivare |
|---|---:|---|
| Opinion | 35 | Dagsavisen, FriFagbevegelse, ANB, ABC, Altinget |
| Verian | 30 | TV 2 |
| Respons Analyse | 22 | VG, Aftenposten |
| InFact | 22 | Nettavisen |
| Norstat | 20 | NRK, Vårt Land, Dagbladet |
| Norfakta | 20 | Nationen, Klassekampen |

Sentio och Ipsos finns i `data/institut_vikter.csv` men har inga mätningar i
perioden. Vikterna i filen är gissningar och behöver kalibreras mot husfaktorer
skattade ur den historiska serien.

Namnen förkortas i båda källorna, `Respons` inte `Respons Analyse`. Mappning
sker i `INSTITUT_NORMALISERING` i respektive modul.

## Valresultat per distrikt: SSB

Tabell 08092, `Stortingsvalet. Godkjende røyster, etter parti/valliste`.

```
POST https://data.ssb.no/api/v0/no/table/08092
{"query":[
  {"code":"Region","selection":{"filter":"item","values":["v01","v02", ... ,"v20"]}},
  {"code":"PolitParti","selection":{"filter":"all","values":["*"]}},
  {"code":"ContentsCode","selection":{"filter":"item","values":["Godkjente1"]}},
  {"code":"Tid","selection":{"filter":"item","values":["2025"]}}],
 "response":{"format":"json-stat2"}}
```

- Valdistrikten har regionkoder `v01` till `v20`. **`v13` är Bergen och
  historisk**, upphörde 1972. De 19 aktuella distrikten är alltså v01-v12 och
  v14-v20.
- `ContentsCode` ska vara `Godkjente1` för röstetal, `GodkjenteProsent` för
  andelar. Andra koder ger HTTP 400.
- Använd `filter":"all"` på parti. Hämtas bara de nio stora partierna blir
  röstsumman för låg och spärrberäkningen fel.
- Data finns för 1945 till 2025, vart fjärde år.

Verifierat: summorna reproducerar de officiella nationella andelarna exakt,
till exempel 2025 Ap 28,02, FrP 23,85, Venstre 3,69.

Sparade råfiler: `forskning/roster2021_full.json` och
`forskning/roster2025_full.json`, röstetal per distrikt och parti.

## Lokala partier måste hanteras

Restposten `Andre` kan inte behandlas som ett parti. Två fel uppstår annars:

1. Slås alla småpartier ihop till ett kan klumpen klara fyraprocentsspärren
   och tilldelas utjämningsmandat. Det gav sju mandats fel i 2025-testet.
2. Ett enskilt lokalt parti kan vinna ett distriktsmandat. Pasientfokus fick
   12,70 procent i Finnmark 2021 och ett mandat. Utan det blir 2021 fel.

`Andre` ska alltså räknas i röstunderlaget, men bara partier som redovisas
separat får konkurrera om mandat. Distrikt med ovanligt stor `Andre`-post
behöver särskild uppmärksamhet, Finnmark särskilt.

## Vad som inte är utrett

- **Distriktsprofiler.** Modellen behöver översätta rikstrend till 19
  distriktsresultat. Underlaget finns i SSB 08092 över flera val, men metoden
  är inte byggd.
- **Mandat per distrikt för 2029.** Räknas om av departementet före valet, på
  befolkning och areal. Fram till dess får 2025 års fördelning användas.
- **Fylkesvisa mätningar.** pollofpolls har `type=fylke&kommuneid=NN`. Kan ge
  direkt underlag per distrikt, men täckningen är ojämn och outredd.
- **Kandidater och vallistor.** Ingen källa undersökt.
