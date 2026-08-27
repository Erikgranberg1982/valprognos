# Logotyper

Hämtade från lysio.se och skalade till 88 pixlars höjd, sedan sparade som
palett-PNG med 32 färger. Det räcker för en logotyp med få färger och ger
ungefär en femtedel av originalens filstorlek.

| Fil | Källa |
|---|---|
| `lysio-logo-farg.png` | <https://lysio.se/wp-content/uploads/2021/12/cropped-lysio-bred-farg2x.png> |
| `lysio-logo-vit.png` | <https://lysio.se/wp-content/uploads/2022/01/orginal-vit-for-webb.png> |

Färgvarianten är bred, med bubbelmärket till vänster om ordmärket, och används
i ljust läge. Den vita är kvadratisk, med bubblorna ovanför ordmärket, och
används i mörkt läge.

Logotyperna bäddas in i sidan som data-URI:er av `src/dashboard.py`, så att den
publicerade sidan inte hämtar något från lysio.se. Det gör sidan oberoende av
att filerna ligger kvar på samma adresser.
