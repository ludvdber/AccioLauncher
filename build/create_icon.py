"""Vérifie l'icône Windows du launcher — elle n'est PLUS générée.

`assets/accio_launcher.ico` est désormais un **asset de marque** livré par le
pack (`accio-launcher-site/assets/AccioLogo/accio-launcher.ico`) : sept tailles
dessinées, 16 à 256, chacune ajustée pour rester lisible. La regénérer à partir
d'un PNG en réduisant au LANCZOS donnait un résultat nettement plus mou en 16 et
24 px — précisément les tailles que l'utilisateur voit le plus, dans la barre
des tâches et l'explorateur.

Ce script ne fabrique donc plus rien : il vérifie que l'icône est présente et
saine, et il explique où la reprendre si elle manque. `build.bat` l'appelle
avant PyInstaller, qui a besoin du fichier pour la ressource de l'exécutable.
"""

import sys
from pathlib import Path

RACINE = Path(__file__).parent.parent
ICONE = RACINE / "assets" / "accio_launcher.ico"
SOURCE = "accio-launcher-site/assets/AccioLogo/accio-launcher.ico"
TAILLES_ATTENDUES = {16, 24, 32, 48, 64, 128, 256}


def main() -> int:
    if not ICONE.exists():
        print(f"ERREUR : {ICONE} est absente.")
        print(f"         Reprendre le fichier depuis {SOURCE}.")
        return 1

    try:
        from PIL import Image
    except ImportError:
        print(f"Icone presente ({ICONE.stat().st_size} octets) — "
              "Pillow absent, contenu non verifie.")
        return 0

    with Image.open(ICONE) as im:
        tailles = {w for w, _ in im.info.get("sizes", [])}
    manquantes = TAILLES_ATTENDUES - tailles
    print("Icone : %s (%d octets), tailles %s"
          % (ICONE.name, ICONE.stat().st_size,
             ", ".join(str(t) for t in sorted(tailles))))
    if manquantes:
        print("ATTENTION : tailles manquantes %s — l'icone sera floue a ces"
              " dimensions." % ", ".join(str(t) for t in sorted(manquantes)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
