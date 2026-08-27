# Publicera prognosen

Allt lokalt är klart: repot är initierat, två commits finns på grenen `main`,
och git-identiteten är satt. Det som återstår är ett GitHub-konto och tre steg.

## 1. Skapa konto

Registrera dig på <https://github.com/signup>. Gratis räcker för detta, även
för privat repo och GitHub Actions i publika repon.

Kontot binds till den e-post du anger. Dina commits använder redan
`erik.granberg@lysio.se`.

## 2. Skapa ett tomt repo

Gå till <https://github.com/new> och fyll i:

- **Repository name:** `valprognos-2026`
- **Public** (krävs för gratis GitHub Pages)
- **Lämna alla kryssrutor tomma.** Ingen README, ingen .gitignore, ingen licens.
  De filerna finns redan lokalt, och GitHub skapar annars ett commit som
  krockar med ditt.

## 3. Koppla och skicka upp

Byt `DITT-ANVÄNDARNAMN` mot ditt riktiga:

```bash
cd "/Users/erikgranberg/Desktop/Python/Election prediction"
git remote add origin https://github.com/DITT-ANVÄNDARNAMN/valprognos-2026.git
git push -u origin main
```

Git frågar efter användarnamn och lösenord. **Lösenordet fungerar inte här** –
GitHub kräver en personlig access token i stället:

1. Gå till <https://github.com/settings/tokens>
2. **Generate new token → Fine-grained token**
3. Sätt **Repository access** till ditt nya repo
4. Under **Permissions → Repository permissions** ge `Contents: Read and write`
5. Kopiera token och klistra in den som lösenord vid `git push`

Spara token i nyckelringen så du slipper klistra in den varje gång:

```bash
git config --global credential.helper osxkeychain
```

### Alternativ: SSH i stället för token

Du har redan en nyckel i `~/.ssh/id_ed25519.pub` men den är inte registrerad
hos GitHub. Vill du använda SSH:

```bash
cat ~/.ssh/id_ed25519.pub | pbcopy   # kopierar nyckeln
```

Klistra in den på <https://github.com/settings/keys> under **New SSH key**.
Använd sedan SSH-adressen i stället:

```bash
git remote add origin git@github.com:DITT-ANVÄNDARNAMN/valprognos-2026.git
```

## 4. Slå på GitHub Pages

I repot på GitHub:

**Settings → Pages → Build and deployment → Source:** välj **GitHub Actions**.

Det är allt. Arbetsflödet i `.github/workflows/publicera.yml` tar över:

- Bygger sidan vid varje push till `main`
- Bygger om varje dag klockan 05:10 UTC med nya mätningar
- Kan köras manuellt från **Actions**-fliken
- Stoppar publicering om `scripts/kontrollera.py` inte godkänner bygget

Sidan hamnar på:

```
https://DITT-ANVÄNDARNAMN.github.io/valprognos-2026/
```

Första bygget tar några minuter. Följ det under **Actions**-fliken.

## Aktivera Pages: en fallgrop

Att ge token `Pages`-behörighet räcker inte. Pages måste slås på i repots
inställningar, och GitHub tillåter inte att en fine-grained token gör det.

Symptomet är att bygget lyckas men `deploy-pages` faller med:

```
Failed to create deployment (status: 404)
Ensure GitHub Pages has been enabled
```

Fixen är ett klick under **Settings → Pages → Source: GitHub Actions**.
Kontrollera efteråt att `has_pages` blivit sant:

```bash
curl -s https://api.github.com/repos/Erikgranberg1982/valprognos | grep has_pages
```

## Om något går fel

**`git push` avvisas med "rejected"** betyder att repot inte var tomt. Kör
`git pull --rebase origin main` och försök igen.

**Actions-jobbet faller på kontrollsteget** betyder att bygget inte klarade
rimlighetskontrollen, oftast för att Wikipedias tabellstruktur ändrats. Loggen
under Actions säger vad som avvek. Sidan som redan ligger publicerad påverkas
inte.

**Pages visar 404** betyder oftast att källan inte är satt till GitHub Actions,
eller att första bygget inte hunnit klart.

## Innan du publicerar

Sidan bär Lysio Researchs logotyp och färger, och prognosen går ut publikt
under en valrörelse. Även med repot på ett personligt konto läses den rimligen
som ett utspel från Lysio. Värt att förankra internt först.
