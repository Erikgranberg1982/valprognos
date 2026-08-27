# Skapa en token för publicering

## Steg för steg

1. Gå till <https://github.com/settings/personal-access-tokens/new>
   (Settings → Developer settings → Personal access tokens → Fine-grained tokens)

2. Fyll i:

   | Fält | Värde |
   |---|---|
   | **Token name** | `valprognos-publicering` |
   | **Expiration** | 30 dagar räcker |
   | **Repository access** | Only select repositories → `valprognos` |

3. Under **Permissions → Repository permissions**, sätt:

   | Behörighet | Nivå | Varför |
   |---|---|---|
   | **Contents** | Read and write | Krävs för att pusha koden |
   | **Workflows** | Read and write | Krävs eftersom `.github/workflows/` ingår i pushen |

   Lämna allt annat på **No access**. Ge inte `Administration`, och ge inte
   åtkomst till alla repon.

4. **Generate token** och kopiera värdet. Det visas bara en gång.

## Ge den till mig säkert

Klistra **inte** in token i chatten. Den hamnar då i transkriptet och blir
läsbar i efterhand.

Kör i stället detta i din terminal. Det sparar token i macOS nyckelring, som
jag kan använda utan att någonsin se värdet:

```bash
cd "/Users/erikgranberg/Desktop/Python/Election prediction"
git config credential.helper osxkeychain
git push -u origin main
```

Git frågar då:

- **Username:** `Erikgranberg1982`
- **Password:** klistra in token

Pushen går igenom och token sparas. Säg till när det är klart, så tar jag
resten: verifierar att allt kom upp, och guidar dig genom Pages-inställningen.

## Efter publicering

Återkalla token när den inte behövs längre, på
<https://github.com/settings/personal-access-tokens>. Att den går ut efter 30
dagar är ett skydd, men aktiv återkallning är bättre.
