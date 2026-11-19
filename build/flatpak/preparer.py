"""Prépare l'archive que le manifeste Flatpak emballe : AccioLauncher-linux-x86_64.tar.gz.

Contenu : le dossier gelé de PyInstaller (`dist/AccioLauncher`, le MÊME que celui
de l'AppImage, élagué par le spec), le `.desktop` de l'AppImage et les icônes
extraites telles quelles des sept tailles de l'`.ico`, plus la licence et les
avis tiers. Archive REPRODUCTIBLE : entrées triées, date, propriétaire et
droits de groupe fixés, gzip sans date — deux passes sur le même dossier
donnent la même empreinte (c'est elle que le manifeste de Flathub épinglera).

Usage : python build/flatpak/preparer.py   (après PyInstaller)
"""

import gzip
import hashlib
import io
import subprocess
import sys
import tarfile
import tomllib
from datetime import UTC, datetime
from pathlib import Path

ICI = Path(__file__).resolve().parent
RACINE = ICI.parent.parent
IDENTIFIANT = "be.acciolauncher.AccioLauncher"
SORTIE = ICI / "AccioLauncher-linux-x86_64.tar.gz"
DOCUMENTS = ("LICENSE", "ADDITIONAL-TERMS.md", "TRADEMARKS.md", "docs/THIRD-PARTY-NOTICES.md")
DATE_FIXE = 1_700_000_000


def icones(ico: Path) -> dict[str, bytes]:
    """Chemin dans l'archive → PNG, une entrée par taille de l'`.ico`."""
    from PIL import Image
    image = Image.open(ico)
    sortie = {}
    for largeur, hauteur in sorted(image.ico.sizes()):
        tampon = io.BytesIO()
        image.ico.getimage((largeur, hauteur)).save(tampon, format="PNG")
        sortie[f"share/icons/hicolor/{largeur}x{hauteur}/apps/{IDENTIFIANT}.png"] = tampon.getvalue()
    return sortie


def metainfo(version: str, date: str) -> bytes:
    """Le metainfo AppStream, version et date posées : le numéro de version ne
    vit PAS une cinquième fois dans le dépôt (pyproject.toml fait foi)."""
    modele = (ICI / f"{IDENTIFIANT}.metainfo.xml").read_text(encoding="utf-8")
    return modele.replace("@VERSION@", version).replace("@DATE@", date).encode("utf-8")


def version_et_date() -> tuple[str, str]:
    """Version de pyproject.toml ; date du dernier commit (stable d'un build à
    l'autre : l'archive reste reproductible), sinon celle du jour."""
    projet = tomllib.loads((RACINE / "pyproject.toml").read_text(encoding="utf-8"))
    try:
        # Programme fixe, arguments en liste, aucun shell.
        brut = subprocess.run(["git", "log", "-1", "--format=%ct"], cwd=RACINE,  # noqa: S607
                              capture_output=True, text=True, encoding="utf-8",
                              check=True).stdout.strip()
        instant = datetime.fromtimestamp(int(brut), UTC)
    except (OSError, ValueError, subprocess.CalledProcessError):
        instant = datetime.now(UTC)
    return projet["project"]["version"], instant.strftime("%Y-%m-%d")


def _info(nom: str, taille: int = 0, mode: int = 0o644,
          genre: bytes = tarfile.REGTYPE, lien: str = "") -> tarfile.TarInfo:
    info = tarfile.TarInfo(nom)
    info.size, info.mode, info.type, info.linkname = taille, mode, genre, lien
    info.mtime, info.uid, info.gid, info.uname, info.gname = DATE_FIXE, 0, 0, "", ""
    return info


def entrees(gele: Path) -> list[tuple[tarfile.TarInfo, bytes | None]]:
    """Toutes les entrées de l'archive, triées. Pure (hors lecture des fichiers)."""
    resultat: list[tuple[tarfile.TarInfo, bytes | None]] = []
    for chemin in sorted(gele.rglob("*")):
        nom = "AccioLauncher/" + chemin.relative_to(gele).as_posix()
        if chemin.is_symlink():
            resultat.append((_info(nom, genre=tarfile.SYMTYPE, mode=0o777,
                                   lien=str(chemin.readlink())), None))
        elif chemin.is_dir():
            resultat.append((_info(nom, genre=tarfile.DIRTYPE, mode=0o755), None))
        else:
            mode = 0o755 if chemin.stat().st_mode & 0o100 else 0o644
            donnees = chemin.read_bytes()
            resultat.append((_info(nom, len(donnees), mode), donnees))
    ajouts = icones(RACINE / "assets" / "accio_launcher.ico")
    bureau = RACINE / "build" / "linux" / f"{IDENTIFIANT}.desktop"
    ajouts[f"share/applications/{IDENTIFIANT}.desktop"] = bureau.read_bytes()
    ajouts[f"share/metainfo/{IDENTIFIANT}.metainfo.xml"] = metainfo(*version_et_date())
    for doc in DOCUMENTS:
        ajouts[f"share/doc/accio-launcher/{Path(doc).name}"] = (RACINE / doc).read_bytes()
    for nom in sorted(ajouts):
        resultat.append((_info(nom, len(ajouts[nom])), ajouts[nom]))
    return resultat


def ecrire(gele: Path, sortie: Path) -> str:
    """Écrit l'archive ; rend son SHA-256."""
    brut = io.BytesIO()
    with tarfile.TarFile(fileobj=brut, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for info, donnees in entrees(gele):
            tar.addfile(info, io.BytesIO(donnees) if donnees is not None else None)
    tampon = io.BytesIO()
    with gzip.GzipFile(fileobj=tampon, mode="wb", mtime=0, compresslevel=9, filename="") as gz:
        gz.write(brut.getvalue())
    sortie.write_bytes(tampon.getvalue())
    return hashlib.sha256(tampon.getvalue()).hexdigest()


def main() -> int:
    gele = RACINE / "dist" / "AccioLauncher"
    if not (gele / "AccioLauncher").is_file():
        print("ERREUR : dist/AccioLauncher introuvable — lancer PyInstaller d'abord "
              "(python -m PyInstaller accio_launcher.spec --noconfirm).")
        return 1
    empreinte = ecrire(gele, SORTIE)
    print(f"Archive : {SORTIE.relative_to(RACINE)} ({SORTIE.stat().st_size / 1024 ** 2:.0f} Mo)")
    print(f"SHA-256 : {empreinte}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
