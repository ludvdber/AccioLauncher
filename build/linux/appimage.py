"""Range le dossier gelé (`dist/AccioLauncher`) dans une AppImage.

Étape 6/6 de `build.sh`. Sortie : `dist/AccioLauncher-x86_64.AppImage`.

Pourquoi une AppImage (et pas d'abord un Flatpak) : un seul fichier, qui se
télécharge depuis la même release que l'exe Windows, s'exécute sans
installation et SE MET À JOUR TOUT SEUL par le mécanisme du launcher
(`self_update` remplace `$APPIMAGE`). Un Flatpak passerait par Flathub — une
revue, un manifeste à tenir, et un bac à sable où lancer Wine, umu et les
jeux demanderait des autorisations larges. Voir docs/LINUX.md § 4.8.

Le nom ne porte PAS la version : l'auto-mise à jour remplace le fichier sur
place, et un « AccioLauncher-1.0.7 » qui contiendrait la 1.0.9 mentirait.

Les deux outils d'AppImage sont ÉPINGLÉS par version et par empreinte, comme
les actions de la CI : un build ne doit pas changer parce qu'un « continuous »
a bougé en amont.
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import ssl
import subprocess
import sys
import urllib.request
from pathlib import Path

ICI = Path(__file__).resolve().parent
RACINE = ICI.parent.parent
sys.path.insert(0, str(ICI))

from dependances import verifier_dossier  # noqa: E402

# Identifiant de bureau : le MÊME que `main.DESKTOP_ID` (tenu par un test) —
# c'est lui qui relie la fenêtre, sous Wayland, à ce fichier et à son icône.
IDENTIFIANT = "be.acciolauncher.AccioLauncher"
SORTIE = "AccioLauncher-x86_64.AppImage"

# (url, SHA-256) relevés le 2026-09-24.
APPIMAGETOOL = (
    "https://github.com/AppImage/appimagetool/releases/download/1.9.1/"
    "appimagetool-x86_64.AppImage",
    "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0",
)
# Le runtime est la partie exécutable de TOUTE AppImage : il monte l'image et
# lance AppRun. Celui-ci est lié statiquement (libfuse 3 comprise) : la machine
# n'a plus besoin de libfuse2, absente de Fedora et donc de Bazzite.
RUNTIME = (
    "https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64",
    "2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d",
)


# Voyagent dans l'AppImage (`usr/share/doc/accio-launcher/`).
DOCUMENTS = ("LICENSE", "ADDITIONAL-TERMS.md", "TRADEMARKS.md", "docs/THIRD-PARTY-NOTICES.md")


def empreinte(chemin: Path) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def outil(url: str, sha256: str, cache: Path) -> Path:
    """Le fichier épinglé, depuis le cache ou téléchargé ; refusé s'il diffère."""
    cible = cache / url.rsplit("/", 2)[-2] / url.rsplit("/", 1)[-1]
    if not (cible.is_file() and empreinte(cible) == sha256):
        cible.parent.mkdir(parents=True, exist_ok=True)
        print(f"  téléchargement : {url}")
        temporaire = cible.with_suffix(".part")
        # URL https constante ci-dessus ; son contenu est vérifié juste après.
        with urllib.request.urlopen(url, context=ssl.create_default_context(),  # nosec B310
                                    timeout=120) as reponse, open(temporaire, "wb") as f:
            shutil.copyfileobj(reponse, f)
        trouvee = empreinte(temporaire)
        if trouvee != sha256:
            temporaire.unlink()
            raise SystemExit(f"Empreinte inattendue pour {url} :\n  {trouvee}\n  attendue {sha256}")
        temporaire.replace(cible)
    cible.chmod(0o755)
    return cible


def icones(ico: Path, appdir: Path) -> None:
    """Chaque taille DESSINÉE de l'icône Windows, telle quelle, en PNG.

    Aucune n'est recalculée : l'.ico porte sept tailles ajustées une à une,
    et réduire la plus grande rendait les petites molles (règle 87).
    """
    from PIL import Image

    with Image.open(ico) as image:
        tailles = sorted(image.ico.sizes())
        for largeur, hauteur in tailles:
            dossier = appdir / "usr/share/icons/hicolor" / f"{largeur}x{hauteur}" / "apps"
            dossier.mkdir(parents=True, exist_ok=True)
            image.ico.getimage((largeur, hauteur)).save(dossier / f"{IDENTIFIANT}.png")
    plus_grande = tailles[-1][0]
    source = appdir / "usr/share/icons/hicolor" / f"{plus_grande}x{plus_grande}" / "apps"
    shutil.copyfile(source / f"{IDENTIFIANT}.png", appdir / f"{IDENTIFIANT}.png")
    (appdir / ".DirIcon").symlink_to(f"{IDENTIFIANT}.png")


def assembler(gele: Path, appdir: Path) -> None:
    """Construit l'AppDir : AppRun, .desktop, icônes, dossier gelé."""
    if appdir.exists():
        shutil.rmtree(appdir)
    (appdir / "usr/lib").mkdir(parents=True)
    shutil.copytree(gele, appdir / "usr/lib/AccioLauncher", symlinks=True)
    shutil.copyfile(ICI / "AppRun", appdir / "AppRun")
    (appdir / "AppRun").chmod(0o755)
    bureau = ICI / f"{IDENTIFIANT}.desktop"
    shutil.copyfile(bureau, appdir / bureau.name)
    (appdir / "usr/share/applications").mkdir(parents=True)
    shutil.copyfile(bureau, appdir / "usr/share/applications" / bureau.name)
    icones(RACINE / "assets" / "accio_launcher.ico", appdir)
    # La licence et les avis tiers voyagent AVEC le binaire : les licences des
    # composants embarqués (7-Zip, LGPL de Qt et du runtime…) l'exigent.
    doc = appdir / "usr/share/doc/accio-launcher"
    doc.mkdir(parents=True)
    for nom in DOCUMENTS:
        shutil.copyfile(RACINE / nom, doc / Path(nom).name)


def main() -> int:
    if platform.machine() != "x86_64":
        print(f"ERREUR : seul x86_64 est pris en charge (7-Zip et runtime embarqués), "
              f"pas {platform.machine()}.")
        return 1
    gele = RACINE / "dist" / "AccioLauncher"
    if not (gele / "AccioLauncher").is_file():
        print("ERREUR : dist/AccioLauncher introuvable — PyInstaller n'a pas tourné.")
        return 1

    # Avant d'emballer : une dépendance manquante ici, c'est un launcher qui
    # ne démarre pas chez quelqu'un d'autre, sans message lisible.
    defauts = verifier_dossier(gele)
    if defauts:
        print("ERREUR : dossier gelé incomplet ou trop complet :")
        print("\n".join(f"  - {d}" for d in defauts))
        return 1

    cache = RACINE / "build" / "linux" / "outils"
    outil_appimage = outil(*APPIMAGETOOL, cache)
    runtime = outil(*RUNTIME, cache)

    appdir = RACINE / "build" / "appimage" / "AccioLauncher.AppDir"
    assembler(gele, appdir)

    sortie = RACINE / "dist" / SORTIE
    sortie.unlink(missing_ok=True)
    env = dict(os.environ, ARCH="x86_64",
               # appimagetool est lui-même une AppImage : s'extraire plutôt que
               # se monter, les runners de CI n'ayant pas FUSE.
               APPIMAGE_EXTRACT_AND_RUN="1")
    env.pop("VERSION", None)          # sinon appimagetool l'ajoute au nom
    # Outil épinglé ci-dessus (chemin absolu, empreinte vérifiée) ; aucun shell.
    code = subprocess.run(  # nosec B603
        [str(outil_appimage), "--no-appstream", "--runtime-file", str(runtime),
         str(appdir), str(sortie)], env=env, check=False).returncode
    if code != 0 or not sortie.is_file():
        print(f"ERREUR : appimagetool a échoué (code {code}).")
        return 1
    sortie.chmod(0o755)
    print(f"AppImage : {sortie.relative_to(RACINE)} "
          f"({sortie.stat().st_size / 1024 ** 2:.0f} Mo)")
    print(f"SHA-256  : {empreinte(sortie)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
