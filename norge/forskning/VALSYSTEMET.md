# Det norska valsystemet, verifierat mot 2021 och 2025

Det här dokumentet beskriver mandatfördelningen så som den faktiskt räknas,
och är verifierat: algoritmen nedan reproducerar både stortingsvalet 2025 och
2021 med **noll mandats avvikelse** för samtliga partier.

Källor: [valgloven § 11-4 och § 11-6](https://lovdata.no/lov/2002-06-28-57/%C2%A711-11),
[SNL om utjevningsmandat](https://snl.no/utjevningsmandat), röstdata från
[SSB tabell 08092](https://data.ssb.no/api/v0/no/table/08092).

## Grundstruktur

169 mandat i 19 valdistrikt. Varje distrikt har ett bestämt antal mandat,
varav **exakt ett är utjämningsmandat**. Alltså 150 distriktsmandat och 19
utjämningsmandat.

Mandat per distrikt räknas om varje val efter både invånarantal och areal
(areal viktas, vilket gynnar Finnmark och Sogn og Fjordane).

| Distrikt | 2025 | 2021 |
|---|---:|---:|
| Akershus | 20 | 19 |
| Oslo | 20 | 20 |
| Hordaland | 16 | 16 |
| Rogaland | 14 | 14 |
| Sør-Trøndelag | 10 | 10 |
| Nordland | 9 | 9 |
| Østfold | 9 | 9 |
| Buskerud | 8 | 8 |
| Møre og Romsdal | 8 | 8 |
| Hedmark | 7 | 7 |
| Vestfold | 7 | 7 |
| Oppland | 6 | 6 |
| Telemark | 6 | 6 |
| Troms | 6 | 6 |
| Vest-Agder | 6 | 6 |
| Nord-Trøndelag | 5 | 5 |
| Aust-Agder | 4 | 4 |
| Sogn og Fjordane | 4 | 4 |
| Finnmark | 4 | 5 |
| **Summa** | **169** | **169** |

Talen ovan är totaler **inklusive** distriktets utjämningsmandat. Antalet
distriktsmandat är alltså talet minus ett.

## Steg 1: distriktsmandat, utan spärr

I varje distrikt fördelas `mandat - 1` platser med **St. Laguës modifierade
metod**: divisorer 1,4 - 3 - 5 - 7 - 9 ...

Första divisorn är **1,4**, inte svenska 1,2.

**Ingen spärr gäller här.** Detta är den viktigaste skillnaden mot Sverige.
Ett parti under fyra procent kan vinna distriktsmandat på egen styrka:

- Venstre 2025: 3,69 procent nationellt, men **3 distriktsmandat**
- MDG 2021: 3,94 procent, **3 distriktsmandat**
- KrF 2021: 3,80 procent, **3 distriktsmandat**
- Pasientfokus 2021: rent lokalt parti, 12,70 procent i Finnmark, **1 mandat**

Divisorn 1,4 fungerar i praktiken som en mjuk tröskel i små distrikt, men
ingen formell spärr finns.

## Steg 2: utjämningsmandat, spärren gäller bara här

Fyraprocentsspärren avgör **bara** rätten till utjämningsmandat.

1. Räkna nationell röstandel. **Nämnaren är samtliga godkända röster**,
   inklusive alla småpartier. Detta är lätt att göra fel: räknas nämnaren
   bara på de nio stora partierna får MDG 2021 fyra procent i stället för
   3,94 och klarar spärren felaktigt, vilket ger fyra mandats fel.
2. Partier under fyra procent behåller sina distriktsmandat men får inga
   utjämningsmandat. Deras mandat dras av från de 169 innan resten fördelas.
3. De återstående mandaten fördelas nationellt mellan spärrklarande partier,
   också med St. Laguë 1,4.
4. Partiets utjämningsmandat = nationell kvot minus redan vunna
   distriktsmandat.

### Överfördelning

Ett parti kan vinna fler distriktsmandat än sin nationella kvot. Mandaten kan
inte tas ifrån det. Partiet låses då på sitt distriktsresultat och resten
fördelas om utan det. Detta upprepas till dess ingen har överskott.

2021 krävdes två iterationer: först låstes Senterpartiet (28 distriktsmandat
mot kvoten 25), sedan Arbeiderpartiet. Utan detta steg blir summan 170 mandat
i stället för 169.

## Steg 3: vilket distrikt varje utjämningsmandat tas från

Enligt § 11-6 tredje ledet. För varje kombination av distrikt och
utjämningsberättigat parti beräknas en kvot:

```
kvot = (partiets röster i distriktet / (2 * vunna distriktsmandat + 1))
       / (distriktets röster / distriktets antal distriktsmandat)
```

Alla kvoter sorteras fallande. Mandat nummer 1 går till den högsta kvoten.
Sedan gäller två uteslutningsregler:

- När ett distrikt tilldelats sitt utjämningsmandat utgår det ur fortsatt
  beräkning. Varje distrikt får precis ett.
- När ett parti fått sitt antal utjämningsmandat utgår partiet.

Detta gör att ett litet parti kan få sitt utjämningsmandat från ett distrikt
där det står svagt, helt enkelt eftersom de starka distrikten redan är tagna.

## Konsekvenser för modellen

Den svenska `modell.fordela_mandat` nollar alla partier under spärren och
approximerar riket som en valkrets. Båda är fel för Norge:

1. Spärren får inte tillämpas på distriktsmandaten.
2. Riket kan inte behandlas som en valkrets. Distriktsstrukturen avgör hur
   många mandat ett litet parti får under spärren, och den kan inte
   approximeras bort. Modellen **måste** simulera per distrikt.

Punkt 2 betyder att prognosen behöver en fördelningsnyckel från rikstrend till
distriktsresultat, byggd på historiska distriktsprofiler. Det är mer arbete än
den svenska modellen kräver, men utan det går spärrdramatiken, som är själva
kärnan i norsk valanalys, inte att modellera.
