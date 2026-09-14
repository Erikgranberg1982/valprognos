# Utvärdering av slutprognosen 2026

Prognosen frystes den 11 september, två dagar före valet. Facit är det
preliminära resultatet med 94 procent av valdistrikten räknade, hämtat den
14 september. Siffrorna kan ändras något i den slutliga rösträkningen.

## Huvudprognosen

| Parti | Prognos | Utfall | Fel | Mandat | Utfall | Fel |
|---|---|---|---|---|---|---|
| V | 8,12 | 8,20 | −0,08 | 30 | 29 | +1 |
| S | 28,98 | 28,10 | +0,88 | 105 | 100 | +5 |
| MP | 7,53 | 6,10 | +1,43 | 27 | 22 | +5 |
| C | 7,71 | 7,10 | +0,61 | 28 | 25 | +3 |
| **L** | **3,84** | **5,40** | **−1,56** | **0** | **19** | **−19** |
| M | 17,52 | 19,90 | −2,38 | 64 | 70 | −6 |
| KD | 6,63 | 6,20 | +0,43 | 24 | 22 | +2 |
| SD | 19,66 | 17,60 | +2,06 | 71 | 62 | +9 |

**Medelabsolutfel 1,18 procentenheter. 50 felplacerade mandat.**

Till jämförelse: mot 2022 låg felet på 0,73 procentenheter nära valdagen,
och kalibreringen byggde på det valet. 1,18 ligger närmare den validering mot
2018 som gav 1,7, vilket stärker slutsatsen att osäkerheten var för snävt satt.

## Vad som gick fel

Tre fel dominerar, och de hänger ihop.

**Liberalerna.** Modellen gav 3,84 procent och noll mandat. Utfallet blev 5,40
och nitton mandat. Sannolikheten att L skulle klara spärren skattades till 41
procent, så utfallet låg inom det modellen ansåg möjligt, men punktskattningen
missade helt.

**Sverigedemokraterna och Moderaterna.** SD överskattades med 2,06
procentenheter och M underskattades med 2,38. Novus noterade under
slutveckan att L vann väljare främst från SD och M, vilket stämmer med
utfallet: den rörelsen fortsatte efter att mätningarna slutat.

Gemensamt för alla tre är att de var delar av samma sena förskjutning, och att
tjugoen dagars halveringstid vägde in augustimätningar som hann bli inaktuella.

## Scenarierna

Rangordnat på medelabsolutfel i procent, inte på mandat. Ett parti nära
spärren ger nitton mandats utslag oavsett hur nära procenttalet låg, vilket
skulle låta Liberalerna ensamt avgöra hela rangordningen.

| Variant | MAE | Mandat i fel parti |
|---|---|---|
| **Bara den senaste veckan** | **0,96** | 26 |
| Liberalerna klarar spärren | 0,97 | 24 |
| Örebropartiet in via valkretsen | 1,14 | 50 |
| Huvudprognosen | 1,18 | 50 |
| Sommartrenden håller i sig | 1,26 | 36 |
| Samma valspurt som 2022 | 1,41 | 52 |
| Genomsnittlig valspurt | 1,43 | 54 |

Två scenarier slog huvudprognosen tydligt, och båda byggde på samma insikt:
att de färskaste mätningarna vägde för lite.

Scenariot med enbart den senaste veckans mätningar halverade mandatfelet, från
femtio till tjugosex. Det är värt att notera mot backtestet som gjordes före
valet: mot 2018 och 2022 gav kortare tidsfönster **högre** fel, vilket var
skälet att behålla tjugoen dagar. I valet 2026 gällde motsatsen, eftersom
slutveckan innehöll en ovanligt snabb rörelse.

## Region och kommun

| Nivå | Medelfel | Median | Områden |
|---|---|---|---|
| Riksdagen | 1,18 | – | 1 |
| Regionfullmäktige | 1,32 | 1,29 | 20 |
| Kommunfullmäktige | 2,15 | 1,91 | 290 |

Felen växer nedåt som väntat. Riksprognosen bygger på opinionsmätningar,
medan region och kommun härleds ur områdets eget resultat i förra valet skalat
med rikstrenden. Kalibreringen före valet gav 1,49 för region och 1,95 för
kommun, så utfallet ligger nära det modellen själv angav.

Spridningen mellan kommuner är stor. Arboga landade på 0,36 procentenheter,
medan Sorsele hamnade 9,59 fel. De sämsta är genomgående små kommuner, där ett
lokalt parti eller en enskild kandidat kan flytta flera procentenheter utan att
synas i rikstrenden.

## Blocken

| | V+S+MP+C | M+KD+L+SD |
|---|---|---|
| **Facit** | **176** | **173** |
| Huvudprognosen | 190 | 159 |
| Liberalerna klarar spärren | 178 | 171 |

Huvudprognosen missade blockskillnaden med trettioett mandat, medan
L-scenariot missade med fem. Ingen sida nådde egen majoritet, och
Centerpartiets tjugofem mandat avgör regeringsbildningen.

## Inför 2030

Modellen som togs fram för 2026 ligger i taggen `val-2026`. Tre frågor att
pröva innan nästa val:

1. **Halveringstiden.** Tjugoen dagar var kalibrerat mot 2018 och 2022 men
   fungerade sämre 2026. En tid som krymper de sista veckorna vore värd att
   testa mot alla tre valen.
2. **Spärren.** Ett parti nära fyra procent bör redovisas som två utfall, inte
   som en punktskattning. Skillnaden mellan 3,84 och 5,40 procent är nitton
   mandat.
3. **Kalibreringen.** Osäkerheten byggde på ett enda val. Med 2026 finns nu
   tre valcykler att kalibrera mot.
