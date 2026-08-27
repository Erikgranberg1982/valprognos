# Svensk valprediktor

Prognosmodell för riksdagsvalet 13 september 2026, byggd i samma anda som
FiveThirtyEight: opinionsmätningar viktas efter kvalitet, urval och färskhet,
justeras för institutens husfaktorer och körs genom en Monte Carlo-simulering
som ger sannolikheter för block och regeringsalternativ.

## Kom igång

```bash
cd src
python3 prognos.py                      # riksdagsprognos och dashboard
python3 prognos.py --niva region        # regionvalsprognos
python3 prognos.py --niva kommun        # kommunvalsprognos
python3 prognos.py --niva region --omrade Skåne
python3 prognos.py --hamta              # tvinga ny hämtning från Wikipedia
python3 prognos.py --backtest           # utvärdera mot valet 2022
python3 prognos.py --korrigera          # historisk valdagskorrigering
```

Resultatet skrivs till terminalen och till `output/prognos.html`.

Beroenden: `pandas`, `numpy`, `requests`, `beautifulsoup4`, `lxml`.

## Dashboarden

Sidan är byggd i Lysio Researchs grafiska profil (korall `#EF7466`, mörkblå
`#003D63`, Work Sans) och fungerar i både ljust och mörkt läge. Den innehåller:

- **Riksdagskammaren** som halvcirkel med en punkt per mandat, partierna i
  politisk ordning. Två markörer: majoritetsgränsen vid 175 mandat och den
  punkt där det ledande blockets mandat tar slut.
- **Blockkort** med mandatspann och sannolikhet för egen majoritet.
- **Partitabell** med prognos, 80-procentsspann och mandatfördelning.
- **Trendgraf** över hela perioden, med etiketter som skjuts isär så att
  partier med snarlikt stöd går att läsa.
- **Regeringsalternativ** rangordnade efter sannolikhet.
- **Institutsöversikt** där varje kort visar institutets faktiska genomslag i
  prognosen. Klicka på ett institut för att se alla dess mätningar med vikt
  per mätning.
- **De femton senaste mätningarna** med instituten egna siffror, blocksummor
  och varje mätnings vikt.
- **Husfaktorer** per institut och parti.

### Varför ett institut kan väga lite

Viktandelen på institutskorten visar det faktiska genomslaget, som ofta
förvånar. SCB har högsta kvalitetsvikt och nio tusen svarande, men gör bara två
mätningar per år. Med en halveringstid på 30 dagar väger en mätning som är 88
dagar gammal bara omkring 13 procent av en dagsfärsk, så SCB landar på cirka 4
procent av totalvikten. Skop, som senast mätte 2024, faller helt utanför
tidsfönstret och markeras som exkluderat.

## Så fungerar modellen

**1. Datainsamling.** `scraper.py` hämtar mätningar från Wikipedias
sammanställning, där varje institut har en egen tabell. Sammanvägningar
("poll of polls") exkluderas eftersom de annars dubbelräknar underliggande
mätningar. Parsern hanterar svenska datumintervall (`27 maj–7 juni 2026`) och
institut som redovisar avrundade heltal med riktningssuffix (`9+ %`, `32- %`).

**2. Viktning.** Varje mätnings vikt är produkten av tre faktorer:

| Faktor | Beräkning |
|---|---|
| Institutets kvalitet | Från `data/institut_vikter.csv` |
| Urvalsstorlek | `sqrt(urval / 1500)`, eftersom precision växer med kvadratroten |
| Färskhet | `0.5 ^ (ålder / halveringstid)`, standard 21 dagar |

### Institutsvikter och urval

Urvalsstorlekarna är verifierade mot instituten egna publiceringar i augusti
2026, inte uppskattade:

| Institut | Urval | Rekrytering | Vikt |
|---|---|---|---|
| SCB | 4 500 svarande av 9 000 utskick | Slumpmässigt ur befolkningsregistret | 1,35 |
| Verian | 3 043 | Slumpmässigt urval | 1,20 |
| Novus | 1 900–2 700, median 2 330 | Flerkanal: telefon, SMS, e-post, post | 1,15 |
| Indikator | 2 000–3 000 | Postenkät med slumpmässigt urval | 1,00 |
| Demoskop | 2 016 | Självrekryterad webbpanel | 0,95 |
| Ipsos | ~1 800 | Webbpanel med visst slumpurval | 0,95 |
| Sentio | ~1 000 | Självrekryterad webbpanel | 0,50 |
| Skop | ~1 200 | Telefon och post | 0,50 |

Vikten följer två principer. **Rekryteringsmetod:** ett slumpmässigt urval ur
befolkningsregistret ger bättre representativitet än en självrekryterad panel,
oavsett storlek. **Metodtransparens:** institut som publicerar urvalsstorlek,
viktningsvariabler och svarsfrekvens per mätning väger tyngre än de som inte
gör det, eftersom redovisningen går att granska.

Två noteringar. SCB har högst vikt men litet genomslag, cirka 3 procent, eftersom
de bara mäter en gång per år sedan 2023 och tidsvikten då tar över. Skop har inte
publicerat sedan juni 2024 och ligger utanför modellens tidsfönster.

**3. Husfaktorer.** Varje instituts systematiska avvikelse skattas genom att
jämföra dess mätningar med ett tidsviktat konsensus från *övriga* institut, så
inget institut definierar sin egen referenspunkt. Faktorerna centreras till att
summera till noll, så att en generell nivåförskjutning inte misstas för
partistöd. Modellen korrigerar bort 75 procent av den skattade avvikelsen.

**4. Simulering.** 40 000 dragningar med tre osäkerhetskällor: ett korrelerat
blockfel, ett partispecifikt fel som skalas med partiets storlek, och en
driftterm som växer med kvadratroten ur tiden kvar till valdagen. Mandaten
fördelas med jämkade uddatalsmetoden och fyraprocentsspärren.

## Kalibrering och validering

Osäkerhetsparametrarna är kalibrerade mot valet 2022 så att 80-procents-
intervallen faktiskt täcker utfallet i ungefär 80 procent av fallen.

Modellens träffsäkerhet mot det faktiska resultatet 2022:

| Dagar före valet | Medelabsolutfel | Täckning i 80%-intervall |
|---|---|---|
| 7 | 0,64 pe | 7/8 |
| 14 | 0,62 pe | 7/8 |
| 30 | 1,13 pe | 6/8 |
| 90 | 1,62 pe | 6/8 |
| 365 | 2,16 pe | 7/8 |

Dagen före valet 2022 gav modellen vänsterblocket 174 mandat mot faktiska 173.

## Region- och kommunval

Dashboarden och CLI:t hanterar alla tre valnivåer. Region- och kommunval växlas
direkt i dashboardens sektion **Region och kommun**, med sökfält för enskilda
områden.

### Hur de beräknas

Det finns inga publicerade opinionsmätningar för region- eller kommunval, så
modellen härleder stödet i tre steg:

1. **Rikstrenden** kommer från riksdagsprognosen.
2. **En områdesprofil** anger hur mycket starkare eller svagare varje parti är
   där jämfört med riket, uttryckt som en multiplikator. Profilen bygger på
   områdets eget riksdagsvalsresultat 2022, vägt samman med SCB:s
   partisympatiundersökning per landsdel så att den följer hur opinionen rört
   sig sedan dess.
3. **Differensen mellan lokalval och riksdagsval** läggs på, skattad från 2018
   och 2022 med tyngdpunkt på det senare.

Steg 3 gör den största skillnaden. Väljare röstar systematiskt annorlunda i
lokalvalen:

| Parti | Regionval minus riksdagsval | Korrelation mellan 2018 och 2022 |
|---|---|---|
| SD | −6,4 pe | 0,81 |
| Lokala partier (ÖVRIGA) | +4,0 pe | 0,61 |
| V | +1,5 pe | 0,61 |
| KD | +1,1 pe | 0,85 |
| C | +0,4 pe | 0,86 |

Den höga korrelationen mellan valen visar att mönstren är stabila per område
och därför går att extrapolera, inte att de är slumpmässigt brus.

### SCB:s regionala opinion

Partisympatiundersökningen mäter partisympati i tio landsdelar, med data till
maj 2026. Den ger genuin regional signal: SD ligger på 5,6 procent i Stockholm
mot 26,8 i Sydsverige.

Vikten är kalibrerad mot regionvalet 2022:

| Vikt på SCB-data | Medelabsolutfel |
|---|---|
| 0 % (bara historik) | 1,66 pe |
| **25 % (används)** | **1,53 pe** |
| 50 % | 1,56 pe |
| 100 % | 1,95 pe |

Undersökningen mäter riksdagssympati, inte regionvalsavsikt, och landsdelarna
är grova: en enda landsdel kan rymma fyra regioner. Därför förbättrar den
prognosen som komplement men försämrar den om den får dominera. Vikten ändras
med `psu_vikt` i `data/modellparametrar.csv`.

### Lokala partier

SCB redovisar alla lokala partier samlat som ÖVRIGA, så de kan inte
prognosticeras var för sig. De hålls därför konstanta på sin nivå från förra
valet, vilket är den ärligaste behandlingen när mätningar saknas. Nivån är hög
i vissa kommuner: Hagfors 41 procent, Perstorp 37 procent.

### Träffsäkerhet och begränsningar

Ett out-of-sample-test, där bara 2018 års differens används för att förutsäga
regionvalet 2022, ger ett medelabsolutfel på **1,51 procentenheter**. Det är
dubbelt så mycket som riksdagsprognosens 0,62 nära valet, vilket är väntat när
underlaget är historik snarare än mätningar.

- Mandatfördelningen använder regionvalens tre procents spärr och kommunvalens
  praktiska två procent, mot riksdagsvalets fyra.
- Fullmäktiges storlek läses ur SCB:s valresultat, eftersom varje kommun och
  region beslutar sin egen storlek: kommunerna varierar från 21 till 101
  ledamöter.
- Vågmästarläge redovisas explicit, eftersom lokala partier ofta gör att inget
  block når egen majoritet.
- Gotland saknar regionval och ingår därför inte i regionprognosen.
- Lokala förhållanden som ett avhopp eller en lokal stridsfråga kan flytta
  stora väljarandelar och fångas inte alls av modellen.

## Jämförelse med förra valet

Alla nivåer visar förändringen mot valet 2022, både i procentenheter och mandat.
Riksdagsvalets utfall ligger i `src/config.py`; region- och kommunvalens hämtas
från SCB.

## Lokala partier med egna mätningar

SCB redovisar lokala partier samlat som ÖVRIGA, vilket gör att ett enskilt parti
inte kan följas. `data/lokala_partier.csv` bryter ut de partier där det finns en
publicerad mätning, så att de syns med namn och prövas mot spärren för sig.

Formatet är en rad per parti och nivå:

```csv
parti,niva,omrade_kod,omrade_namn,stod,forra_valet,kalla,datum,kommentar
Örebropartiet,kommun,1880,Örebro,18.4,7.9,Novus för Nerikes Allehanda,2026-05-29,
```

Saknas mätning på en nivå skalas stödet från den nivå som har en, i första hand
med partiets eget förhållande mellan nivåerna i förra valet.

När ett parti mäts högre än den gamla ÖVRIGA-posten tas skillnaden
proportionellt från de övriga partierna, eftersom ett växande lokalt parti
vinner röster från riksdagspartierna och inte bara från andra lokala.

### Riksdagen via valkretsspärren

Vallagen har två vägar till riksdagen: fyra procent i hela landet, eller tolv
procent i en enskild valkrets. Den andra vägen är i praktiken den enda möjliga
för ett lokalt parti.

Modellen räknar på den, men resultatet är nedslående för lokala partier. Ett
lokalt parti behåller bara omkring en femtedel av sitt kommunvalsstöd när samma
väljare röstar till riksdagen, skattat från samtliga kommuner med minst tre
procent ÖVRIGA i valen 2018 och 2022:

| Kvot riksdagsval mot kommunval | Värde |
|---|---|
| Median | 0,156 |
| Medelvärde | 0,194 |
| 90:e percentilen | 0,355 |

För Örebro var kvoten 0,186 år 2022: 9,5 procent i kommunvalet blev 1,8 procent
i riksdagsvalet. Örebropartiets 18,4 procent i kommunmätningen motsvarar därför
omkring 3,5 procent i riksdagsvalet i valkretsen, långt under tolvprocentskravet.
Sannolikheten att nå riksdagen den vägen är under en procent.

Talet ska läsas som en storleksordning. Det finns inga mätningar av
riksdagsvalet i en enskild valkrets, så stödet härleds via en kvot som varierar
kraftigt mellan kommuner.

## Koalitioner på lokal nivå

Vänster mot höger räcker inte för kommuner och regioner. Efter valet 2022 har
99 av 290 kommuner ett blocköverskridande styre, vilket är det enskilt
vanligaste mönstret, och SCB räknar 84 olika partikonstellationer.

Modellen räknar därför ut om de vanligaste koalitionerna når majoritet i varje
område. Listan ligger i `data/lokala_koalitioner.csv` och bygger på SCB:s
statistik över faktiska styren (tabellerna `ME0002KnP01` och `ME0002LanP01`):

| Koalition | Styr 2022, kommuner | Regioner |
|---|---|---|
| Alliansen (M+KD+L+C) | 33 | 2 |
| S+M | 17 | 1 |
| S+C | 14 | 0 |
| V+S | 12 | 0 |
| Höger med SD (M+KD+L+SD) | 9 | 1 |
| V+S+MP+C | 6 | 1 |

Fördelningen av styrestyper 2022:

| Typ | Kommuner | Regioner |
|---|---|---|
| Blocköverskridande | 99 (34 %) | 5 (25 %) |
| Borgerligt med C | 50 (17 %) | 3 (15 %) |
| Höger med SD | 34 (12 %) | 1 (5 %) |
| Vänster med C | 32 (11 %) | 4 (20 %) |
| Vänster | 28 (10 %) | 2 (10 %) |

Notera skillnaden mellan vad som är aritmetiskt möjligt och vad som faktiskt
sker. S+M kan nå majoritet i 134 kommuner enligt prognosen men styr bara i 17:
de flesta väljer andra lösningar när alternativ finns. Kolumnen "Styr nu" i
dashboarden visar det faktiska antalet, så att möjligheten inte förväxlas med
sannolikheten.

Lägg till egna koalitioner genom att fylla på CSV-filen. Partierna anges som
`M+KD+L+C`.

### Sortering

Alla kolumner i region- och kommuntabellen går att sortera genom att klicka på
rubriken. Ett andra klick vänder ordningen. Tal börjar fallande och text
stigande, eftersom man nästan alltid vill se var ett parti är starkast först.

Det är användbart för att hitta mönster i 290 kommuner. Sorterat på KD hamnar
Markaryd först med 42 procent, följt av Sävsjö och Lycksele. Sorteringen
fungerar tillsammans med sökfältet.

### Mandatläge i stället för blockmajoritet

Tabellen visade tidigare vänster- eller högermajoritet enligt riksdagsvalets
blockindelning, där C räknas till vänsterblocket. Lokalt blev det missvisande:
modellen angav vänstermajoritet i 57 procent av kommunerna, medan faktiskt
vänsterstyre efter valet 2022 var 20 procent.

Orsaken är att C lokalt oftare styr med de borgerliga. Av de 135 kommunstyren
partiet ingick i efter valet 2022 var 55 med de borgerliga, 48 med båda sidorna
och 32 med vänstern.

C räknas därför inte till något block. I stället beskrivs vad som faktiskt går
att läsa ur mandaten:

| Läge | Betyder |
|---|---|
| V+S+MP i majoritet | Vänsterpartierna når majoritet utan C |
| Vänstern med C | V, S och MP behöver C |
| Borgerliga med C | M, KD och L behöver C |
| Borgerliga med SD | M, KD och L når majoritet med SD |
| Högern har flera vägar | Borgerliga kan välja mellan C och SD |
| Lokala partier avgör | Ingen sida når majoritet utan lokala partier |
| Oklart läge | Ingen vanlig kombination räcker |

Mandatläget säger vem som **kan** nå majoritet, inte vem som kommer att styra.
Det avgörs av förhandlingar som ingen modell kan förutse.

## Justera modellen

Alla parametrar ligger i CSV-filer och kan ändras utan kodändring:

- **`data/institut_vikter.csv`** — kvalitetsvikt och typiskt urval per institut.
- **`data/modellparametrar.csv`** — halveringstid, osäkerhetsnivåer,
  antal simuleringar. Sänk `halveringstid_dagar` för att låta nya mätningar
  väga tyngre.
- **`data/valdagskorrigering.csv`** — historisk skevhet per parti.

## Regeringsalternativ

Sannolikheterna anger om partierna tillsammans når 175 mandat, inte om de vill
regera ihop. Alternativen överlappar och summerar därför inte till 100 procent.
Redigera listan i `src/config.py` (`REGERINGSALTERNATIV`); ett alternativ kan
ges extra villkor, som att C måste klara spärren.

## Publicering

Sidan byggs som statiska filer i `output/` och kan publiceras var som helst.
Uppsättningen i repot använder GitHub Pages med GitHub Actions:

1. Skapa ett repo på GitHub och lägg upp koden.
2. Slå på Pages under **Settings → Pages** med källa **GitHub Actions**.
3. Arbetsflödet i `.github/workflows/publicera.yml` bygger sidan varje dag
   klockan 05:10 UTC, och går även att köra manuellt från Actions-fliken.

Före publicering kör `scripts/kontrollera.py` en rimlighetskontroll: antal
mätningar och institut, att partisummorna ser vettiga ut, att senaste mätningen
inte är för gammal, och att prognosen ligger inom rimliga intervall. Ett bygge
som inte klarar kontrollen publiceras inte. Det skyddar mot att en ändring i
Wikipedias tabellstruktur tyst ger en trasig sida.

Filerna som publiceras:

| Fil | Innehåll |
|---|---|
| `index.html` | Hela sidan, alla tre valnivåer |
| `kommuner.json` | Kommundata som fristående fil, för egen analys |
| `.nojekyll` | Säger till Pages att inte köra Jekyll |

Kommundata är omkring 137 kB som rå JSON men bäddas in gzip-komprimerad och
base64-kodad, vilket blir cirka 29 kB. Den packas upp i webbläsaren först när
någon växlar till kommunvalet.

Sidan är därmed helt självförsörjande och fungerar likadant om du öppnar
`index.html` direkt från Finder som när den ligger publicerad. En tidigare
version hämtade kommundata med `fetch`, vilket gjorde kommunvyn tom vid lokal
öppning eftersom webbläsaren blockerar `fetch` mot `file://`.

## Kända begränsningar

- **Urvalsstorlekar saknas** i Wikipedias tabeller, så institutets typiska
  urval används för samtliga mätningar.
- **Kalibreringen bygger på ett enda val.** Felmönstren från 2022 är inte
  nödvändigtvis allmängiltiga. Därför är valdagskorrigeringen avstängd som
  standard: den är kalibrerad på samma val den utvärderas mot, vilket gör
  förbättringen delvis cirkulär.
- **Mandatfördelningen approximerar riket som en valkrets.** I verkligheten
  fördelas 310 fasta mandat i 29 valkretsar plus 39 utjämningsmandat.
  Utjämningen gör slutresultatet nära riksproportionellt, men enskilda partier
  kan avvika med ett mandat eller två.
- **Blockindelningen följer Wikipedias kolumner** (V+S+MP+C mot L+M+KD+SD) och
  speglar inte nödvändigtvis dagsaktuella samarbetsviljor.

## Filer

```
assets/             Lysios logotyper, hämtade från lysio.se. Se assets/KALLA.md
src/config.py       Partier, block, regeringsalternativ, parameterinläsning
src/scraper.py      Hämtning och normalisering av mätningar
src/modell.py       Viktning, husfaktorer, mandatfördelning, simulering
src/scb_data.py     SCB:s API: valresultat och regional partisympati
src/regionmodell.py Regionvalsprognos
src/kommunmodell.py Kommunvalsprognos
src/dashboard.py    HTML-generering
src/prognos.py      Huvudprogram, nivåväxling och backtest
```
