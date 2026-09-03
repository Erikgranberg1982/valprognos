# Norsk valprognos

Prognos för stortingsvalet 2029. Publiceras som undersida till den svenska
prognosen: <https://erikgranberg1982.github.io/valprognos/norge/>

Byggd på den svenska valprediktorn, men mandatfördelningen är skriven från
grunden. Det norska valsystemet skiljer sig så mycket att den svenska
förenklingen inte fungerar.

## Vad som är verifierat

**Mandatfördelningen återger stortingsvalen 2021 och 2025 exakt**, noll
mandats avvikelse för samtliga partier. Kör `cd src && python3 mandat.py`.

**Distriktsmodellen träffar inom sex mandat av 169** när den prövas ur
stickprov, alltså med föregående vals distriktsprofil och bara riksandelar
som indata. Kör `cd src && python3 distriktsmodell.py`.

**Osäkerheten är kalibrerad mot fyra val**, 2013 till 2025. I backtestet föll
utfallet inom 80-procentsintervallet i 75 till 81 procent av fallen på alla
avstånd från en vecka till tre år. Medelabsolutfelet är 0,71 procentenheter
en vecka före valet. Kör `cd src && python3 prognos.py --backtest`.

## Det som skiljer mot Sverige

Tre saker, som alla påverkar modellen:

1. **Första divisorn är 1,4**, inte 1,2.
2. **Fyraprocentsspärren gäller bara utjämningsmandaten.** Ett parti under
   spärren kan vinna distriktsmandat på egen styrka. Venstre fick tre mandat
   2025 med 3,69 procent, MDG och KrF tre var 2021 under spärren.
3. **Riket kan inte behandlas som en valkrets.** Den svenska modellen gör så,
   och det fungerar där eftersom utjämningen ger ett nära riksproportionellt
   resultat. I Norge får ett parti under spärren mandat uteslutande genom
   distriktsstyrka, så modellen måste fördela mandat i alla 19 valdistrikt.

Tre fällor visade sig under valideringen, alla dokumenterade i
`forskning/VALSYSTEMET.md`:

- **Spärrens nämnare** är samtliga godkända röster. Räknas den bara på de
  redovisade partierna får MDG 2021 fyra procent i stället för 3,94 och
  klarar spärren felaktigt. Fyra mandats fel.
- **Överfördelning kräver en loop.** Senterpartiet vann 28 distriktsmandat
  2021 mot en nationell kvot på 25. Mandaten kan inte tas ifrån partiet, så
  det låses och resten fördelas om. Två iterationer krävdes. Utan detta blir
  summan 170 mandat.
- **Restposten Andre är inget parti.** Som klump klarar den spärren och tar
  sju mandat felaktigt. Samtidigt kan ett enskilt lokalt parti vinna ett
  distriktsmandat, som Pasientfokus i Finnmark 2021 med 12,70 procent.

## Köra lokalt

```bash
pip install -r requirements.txt
cd src

python3 prognos.py                 # hela kedjan, bygger sidan
python3 prognos.py --hamta         # tvinga ny hämtning
python3 prognos.py --backtest      # utvärdera mot 2013 till 2025
python3 mandat.py                  # verifiera mandatfördelningen
python3 distriktsmodell.py         # verifiera distriktsmodellen
```

Sidan hamnar i `output/norge/index.html`. Miljövariabeln `NORSK_OUTPUT`
pekar om katalogen, vilket arbetsflödet använder.

## Datakällor

Opinionsmätningar från Wikipedias sammanställning, som har urvalsstorlek och
fältarbetsperiod. Valresultat per valdistrikt från SSB tabell 08092.
Mandatregler enligt valgloven. Se `forskning/DATAKALLOR.md` för endpoints,
format och varför Wikipedia valdes framför pollofpolls egna CSV-filer.

## Vad som inte finns

Kandidat- och ledamotsprognos är medvetet utelämnad. Fylkes- och
kommunvalsprognos likaså: valordningen skiljer sig från riksvalet och
underlaget är inte utrett.

Mandatfördelningen per distrikt för 2029 räknas om av departementet före
valet, på befolkning och areal. Fram till dess används 2025 års fördelning.
