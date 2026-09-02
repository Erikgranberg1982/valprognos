#!/usr/bin/env python3
"""Laddar upp den byggda sidan till app.lysio.se med SFTP.

GitHub Pages uppdateras av sig självt varje natt. Den egna servern gör det
inte, utan kräver en uppladdning. Skriptet skickar de sex filer sidan behöver
och lämnar övrigt i katalogen orört.

    python3 scripts/publicera_server.py            # ladda upp från output/
    python3 scripts/publicera_server.py --torrkor  # visa vad som skulle göras

Inloggningsuppgifterna läses ur .env i projektroten och skrivs aldrig ut.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent
FJARRKATALOG = "/var/www/html/valprognos"
VARD = "46.246.49.209"

# Bara dessa filer behövs för att sidan ska fungera. CSV-filerna i
# publicering/ är källdata för granskning och läses inte av någon sida.
FILER = [
    "index.html",
    "partier_2026.html",
    "ledamoter_2026.html",
    "scenarier_2026.html",
    "kandidater.json",
    "kommuner.json",
]


def las_uppgifter() -> tuple[str, str]:
    """Hämtar användarnamn och lösenord ur .env."""
    fil = ROT / ".env"
    if not fil.exists():
        sys.exit("FEL: .env saknas i projektroten.")
    text = fil.read_text(encoding="utf-8")
    anv = re.search(r"hugouser:\s*(\S+)", text)
    los = re.search(r"hugopass:\s*(\S+)", text)
    if not anv or not los:
        sys.exit("FEL: .env saknar hugouser eller hugopass.")
    return anv.group(1), los.group(1)


def summa(vag: Path) -> str:
    return hashlib.sha256(vag.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description="Publicera till app.lysio.se")
    ap.add_argument("--torrkor", action="store_true",
                    help="Visa vad som skulle laddas upp utan att göra det")
    ap.add_argument("--katalog", default=str(ROT / "output"),
                    help="Katalog att ladda upp från (standard: output)")
    args = ap.parse_args()

    kalla = Path(args.katalog)
    saknas = [f for f in FILER if not (kalla / f).exists()]
    if saknas:
        sys.exit(f"FEL: dessa filer saknas i {kalla}: {', '.join(saknas)}")

    try:
        import paramiko
    except ImportError:
        sys.exit("FEL: paramiko saknas. Kör: pip install paramiko")

    anv, los = las_uppgifter()
    klient = paramiko.SSHClient()
    klient.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    klient.connect(VARD, username=anv, password=los, timeout=30,
                   look_for_keys=False, allow_agent=False)
    sftp = klient.open_sftp()

    try:
        sftp.stat(FJARRKATALOG)
    except FileNotFoundError:
        sys.exit(f"FEL: {FJARRKATALOG} finns inte på servern.")

    andrade, oforandrade = [], []
    for namn in FILER:
        lokal = kalla / namn
        fjarr = f"{FJARRKATALOG}/{namn}"
        try:
            samma = sftp.stat(fjarr).st_size == lokal.stat().st_size
        except FileNotFoundError:
            samma = False
        (oforandrade if samma else andrade).append(namn)

    if args.torrkor:
        print(f"Torrkörning mot {VARD}:{FJARRKATALOG}")
        for n in andrade:
            print(f"  skulle laddas upp: {n} "
                  f"({(kalla / n).stat().st_size / 1024:.0f} kB)")
        for n in oforandrade:
            print(f"  oförändrad storlek: {n}")
        sftp.close()
        klient.close()
        return

    # Ladda upp allt, även det som ser oförändrat ut: lika filstorlek betyder
    # inte lika innehåll, och sex filer är snabbt gjort.
    for namn in FILER:
        lokal = kalla / namn
        fjarr = f"{FJARRKATALOG}/{namn}"
        tillfallig = f"{fjarr}.ny"
        sftp.put(str(lokal), tillfallig)
        # Byt in filen när den är helt uppladdad, så att en besökare aldrig
        # hämtar en halv sida.
        try:
            sftp.posix_rename(tillfallig, fjarr)
        except (AttributeError, IOError):
            try:
                sftp.remove(fjarr)
            except FileNotFoundError:
                pass
            sftp.rename(tillfallig, fjarr)
        print(f"  {namn:22}{lokal.stat().st_size / 1024:8.0f} kB")

    sftp.close()
    klient.close()
    print(f"\nKlart. {len(FILER)} filer uppladdade till "
          f"https://app.lysio.se/valprognos/")


if __name__ == "__main__":
    main()
