# Uppdatera prognosen

## Det korta svaret

**Oftast gör du ingenting.** GitHub Actions hämtar nya mätningar från Wikipedia
och bygger om sidan varje natt 05:10 UTC, alltså 07:10 svensk sommartid. En
mätning som publiceras på morgonen syns normalt på sidan dagen efter.

Du behöver bara ingripa i tre fall, beskrivna nedan.

---

## Fall 1: Du vill inte vänta till natten

Gå till **Actions → Bygg och publicera valprognos → Run workflow**. Bygget tar
några minuter och publicerar direkt.

Vill du köra lokalt i stället:

```bash
cd "/Users/erikgranberg/Desktop/Python/Election prediction/src"
python3 prognos.py --hamta
```

`--hamta` tvingar ny hämtning i stället för att använda cachen.

---

## Fall 2: En mätning finns inte på Wikipedia

Wikipedia ligger ibland några dagar efter, och en mätning som bara publicerats
i en tidning kommer kanske aldrig dit. Lägg då in den för hand i
`data/egna_matningar.csv`:

```csv
institut,datum,urval,V,S,MP,C,L,M,KD,SD,kalla,kommentar
Novus,2026-09-02,2400,8.1,31.0,7.0,6.8,2.2,18.2,6.5,19.7,https://novus.se/...,Publicerad i SVT
```

Reglerna:

- **institut** måste stavas som i `data/institut_vikter.csv`, annars får
  mätningen standardvikt i stället för institutets egen.
- **datum** som ÅÅÅÅ-MM-DD. Använd publiceringsdatum.
- **urval** kan lämnas tomt. Då används institutets typiska urval, och
  mätningen får något lägre vikt eftersom siffran är en gissning.
- **kalla** och **kommentar** används inte i räkningen men gör det möjligt att
  kontrollera raden i efterhand.

Filen läses efter varje hämtning, så raden **överlever** att Wikipedia skrapas
om. Kommer Wikipedia ikapp och publicerar samma mätning vinner din egen rad,
och den dubbleras inte.

Ta bort raden när du vill, till exempel när Wikipedia fått in den. Prognosen
blir densamma.

Om något är fel i filen stoppas bygget med ett tydligt meddelande i stället för
att räkna på skräp: fel datumformat, tomma partisiffror, eller siffror som inte
summerar till ungefär hundra.

---

## Fall 3: En lokal mätning för en kommun eller region

Lägg till en rad i `data/lokala_matningar.csv`. Kolumnerna är fler eftersom
lokala mätningar behöver veta vilket område de gäller:

```csv
id,niva,omrade_kod,omrade_namn,institut,uppdragsgivare,urval,datum,V,S,MP,C,L,M,KD,SD,lokalt_parti,lokalt_stod,kalla,kommentar
```

- **id** är en fri etikett, till exempel `malmo_kommun_novus_202609`. Den ska
  vara unik.
- **omrade_kod** är kommunkoden eller regionkoden, fyra respektive två siffror.
  Örebro är `1880`, Göteborg `1480`.
- **lokalt_parti** och **lokalt_stod** används när ett lokalt parti mäts
  separat, som Örebropartiet eller Demokraterna. Lämna tomma annars.

**Viktigt:** alla åtta riksdagspartier måste ha en siffra. Saknas något parti
används mätningen inte alls, eftersom en ofullständig mätning inte går att
vikta mot rikstrenden på ett rimligt sätt.

---

## Justera modellen

Alla parametrar ligger i CSV-filer och kräver ingen kodändring:

| Fil | Vad den styr |
|---|---|
| `data/institut_vikter.csv` | Hur tungt varje institut väger, och deras typiska urval |
| `data/modellparametrar.csv` | Halveringstid, osäkerhet, antal simuleringar |
| `data/lokala_matningar.csv` | Lokala mätningar |
| `data/egna_matningar.csv` | Riksmätningar som saknas på Wikipedia |

Efter en ändring: kör om bygget, eller pusha så bygger Actions om automatiskt.

---

## Kontrollera innan du publicerar

```bash
python3 scripts/kontrollera.py
```

Skriptet stoppar bygget om något ser fel ut: för få mätningar, orimliga
partisummor, trasig JavaScript, eller att senaste mätningen blivit för gammal.
Gränsen för det sista är tjugoen dagar de sista tre månaderna före valet och
etthundratjugo dagar dessförinnan, eftersom mätningarna kommer tätare i
valrörelsen.

Samma kontroll körs i Actions. **Faller den publiceras ingenting, och sidan som
redan ligger uppe påverkas inte.**

---

## Publicera till app.lysio.se

GitHub Pages uppdateras av sig självt. Din egen server gör det inte.

```bash
cd "/Users/erikgranberg/Desktop/Python/Election prediction/src"
python3 prognos.py --hamta
cp ../output/index.html ../output/partier_2026.html \
   ../output/ledamoter_2026.html ../output/*.json ../output/*.csv ../publicering/
```

Ladda sedan upp innehållet i `publicering/` till `/valprognos/` på servern.
Alla filer måste ligga i samma mapp, eftersom sidorna länkar till varandra med
relativa sökvägar.

---

## Vanliga fel

**Bygget faller på kontrollsteget.** Oftast har Wikipedia ändrat sin
tabellstruktur. Loggen under Actions säger vad som avvek. Den publicerade sidan
påverkas inte.

**En ny mätning syns inte.** Kontrollera att institutets namn stavas som i
`institut_vikter.csv`. Ett okänt namn ger mätningen standardvikt men den
används fortfarande. Kontrollera också att mätningen ligger inom
tidsfönstret på `max_alder_dagar` i `modellparametrar.csv`.

**Prognosen rör sig knappt trots en ny mätning.** Det är väntat. En enskild
mätning väger mot alla andra inom tidsfönstret. Vikten halveras var
tjugoförsta dag, så en månadsgammal mätning väger ungefär en tredjedel av en
färsk. Först när flera institut visar samma sak flyttar sig prognosen tydligt.

**Ett institut som inte finns i `institut_vikter.csv`** får vikt 0,80 mot
exempelvis Novus 1,20. Mätningen används alltså, men väger mindre. Lägg till
institutet i filen om du vill styra det.
