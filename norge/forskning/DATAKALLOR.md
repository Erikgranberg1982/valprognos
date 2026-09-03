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

- ~~Distriktsprofiler.~~ **Byggt.** `src/distriktsmodell.py` skalar
  rikstrenden till 19 distrikt med historiska profiler. Validerad ur
  stickprov: sex mandats fel av 169.
- **Mandat per distrikt för 2029.** Räknas om av departementet före valet, på
  befolkning och areal. Fram till dess får 2025 års fördelning användas.
- ~~Fylkesvisa mätningar.~~ **Utrett, och de finns i praktiken inte.**
  `type=fylke` ger tomma tabeller för 2024 till 2026. Mätningar per fylke
  görs bara under lokalvalsår och mäter då fylkestingsvalg, inte
  stortingsvalg. Se avsnittet om andra valnivåer nedan.
- **Kandidater och vallistor.** Ingen källa undersökt.

## Andra valnivåer: vad som krävs

Frågan är vad som behövs för att göra prognoser för fler nivåer än
stortingsvalet. Svaret skiljer sig kraftigt mellan nivåerna.

### Distriktsprognos för stortingsvalet: möjlig i dag

Modellen räknar redan mandat i alla 19 valdistrikt, så siffrorna finns.
Det som saknas är bara att publicera dem: en sida per valdistrikt med
mandatfördelning och vilket parti som tar distriktets utjämningsmandat.

**Osäkerheten är dock större än rikssiffrans.** Distriktsresultatet
härleds ur rikstrenden via historisk profil, inte ur mätningar i
distriktet. Det bör framgå tydligt om det publiceras.

**Det finns nästan inga distriktsmätningar att förbättra med.**
pollofpolls `type=fylke` ger tomma tabeller för 2024 till 2026. Mätningar
per fylke görs i praktiken bara under lokalvalsår, och de mäter då
*fylkestingsvalg*, inte stortingsvalg. Exempel: Rogaland hade två
Respons-mätningar 2023, båda om fylkestinget.

### Fylkestings- och kommunevalg 2027: byggt

Valdagen är **13 september 2027**, alltså före stortingsvalet 2029.
Implementerat i `src/lokalmodell.py` och `src/lokalsida.py`.

Datakällor, alla verifierade:

| Tabell | Innehåll |
|---|---|
| **01180** | Kommunestyrevalget, godkända röster per parti, 1945 till 2023 |
| **01181** | Fylkestingsvalget, godkända röster per parti, 1975 till 2023 |
| **04813** | Kommunestyremedlemmer, ger församlingens faktiska storlek |
| Klass **131** | Kommunklassifikation, för kommun till fylke |

Fällor som visade sig:

- **01181 saknar fylkesrader.** Fylkestingsrösterna redovisas per kommun, så
  summeringen till fylke måste göras själv. Kommunkodens två första siffror
  är fylkeskoden.
- **`Hele landet` ligger bland områdena.** Behandlas den som ett område får
  man ett kommunestyre med 9 115 platser. Se `AGGREGAT` i ssb_lokalval.py.
- **Områdesnamn bär giltighetssuffix.** 2019-data skriver "Alta (2020-2023)"
  medan 2023-data skriver "Alta". Utan normalisering tappades 114 av 357
  kommuner i backtestet. Fylkessuffix som "Våler (Innlandet)" måste däremot
  behållas, det särskiljer två olika kommuner.
- **Tvåspråkiga namn stämmer inte mellan tabeller.** Valtabellen skriver
  "Kárásjohka - Karasjok", klassifikationen "Kárášjohka" med š. Alla
  namnvarianter måste provas.
- **04813 använder ContentsCode `Medlemmer`**, inte `Godkjente1`. Fel kod ger
  HTTP 400.
- **Oslo har inget fylkesting.** Kommunestyret fyller rollen, så Oslo finns
  bara på kommunnivå. 14 fylkesting, inte 15.

Mandatfördelningen är ren St. Laguë med första divisor 1,4, **utan spärr och
utan utjämningsmandat**. Den effektiva tröskeln följer i stället av
församlingens storlek. Summan stämmer: 9 115 mandat i 357 kommunestyrer och
654 i 14 fylkesting.

#### Referenspunkten är den viktigaste metodfrågan

Metoden är att skala områdets 2023-resultat med riksopinionens förändring.
Frågan är vad man skalar *från*, och svaret avgör om modellen fungerar alls.

**Närmaste stortingsval som referens fungerar inte.** Mätt mot stortingsvalen
2017 och 2021 gick fem av nio partier åt fel håll jämfört med lokalvalens
faktiska förändring 2019 till 2023: Høyre föll 0,81 nationellt men steg 1,29 i
kommunevalget, Senterpartiet steg 1,31 nationellt men kollapsade till 0,57
lokalt. Skalningen blev då **sämre än att inte göra något**: 4,80 mot 3,87
procentenheters fel.

**Riksopinionen vid lokalvalsdagen fungerar.** Lokalvalen hålls två år efter
stortingsvalen, och opinionen hinner röra sig långt. Mätt mot opinionen i
september 2019 respektive 2023 pekar sju av nio partier rätt.

Backtest, 2019 skalat till 2023 med respektive referens:

| Referens | Fylke | Kommun |
|---|---:|---:|
| Ingen skalning, 2019 rakt av | 3,18 | 3,87 |
| Närmaste stortingsval | 4,44 | 4,80 |
| Riksopinionen vid valdagen, full skalning | 1,61 | 3,61 |
| **Riksopinionen med dämpning 0,65** | **1,53** | **3,32** |

Procentenheters medelabsolutfel per parti. Fylkesnivån halveras, kommunnivån
förbättras måttligt: där dominerar lokala listor och personer som rikstrenden
inte fångar.

#### Rikstrenden måste dämpas

Lokalvalsstödet följer inte riksopinionen fullt ut. Mätt på lokalvalen 2019
till 2023 slår ungefär **0,65** av opinionsrörelsen igenom lokalt, räknat som
exponent på förändringskvoten. Backtestet bekräftar nivån:

| Dämpning | Fylke | Kommun |
|---|---:|---:|
| 0,00 (ingen skalning) | 3,18 | 3,87 |
| 0,50 | 1,79 | 3,31 |
| **0,65** | **1,53** | **3,32** |
| 0,80 | 1,44 | 3,41 |
| 1,00 (full skalning) | 1,61 | 3,61 |

Fylkesnivån är marginellt bättre vid 0,80 och kommunnivån vid 0,50, men 0,65
ligger nära optimum för båda och sammanfaller med det observerade värdet.

Utan dämpning blir enskilda partier orimliga. Fremskrittspartiet har gått
från 13,9 till 31,0 procent i riksopinionen sedan lokalvalet 2023, en kvot på
2,23. Full skalning gav partiet 19,6 procent i snitt över kommunerna och 68
procent i den mest extrema, trots att FrP aldrig fått mer än 11,4 procent i
ett kommunval. Med dämpning blir kvoten 1,68 och riksnivån 19,1 procent,
vilket fortfarande är partiets bästa kommunval någonsin men följer av
opinionsläget snarare än av ett modellfel.

Referensvärdena ligger hårdkodade i `OPINION_VID_LOKALVAL` och kan räknas om
med `python3 lokalmodell.py --referens 2023`.

### Sametingsvalget

Hålls samtidigt som stortingsvalet, med sju valkretsar och egen
valordning. Inga opinionsmätningar publiceras. Går inte att prognosticera
på mätningar.

### Kvar att göra

Distriktssidor för stortingsvalet, alltså en sida per valdistrikt. Siffrorna
räknas redan i distriktsmodellen, så det är bara att publicera dem.
