"""`--verifier-exe <rapport>` : l'exe CONSTRUIT se vérifie lui-même, puis quitte.

La suite tourne depuis les sources : un module, une police ou un fichier de données
oublié par la recette PyInstaller (`accio_launcher.spec`) ne se voyait qu'au lancement
chez un joueur (audit des tests, 2026-11-15). La CI lance ce mode sur l'exe et
l'AppImage juste construits. Il n'écrit rien chez l'utilisateur : ni config, ni journal,
seulement le rapport demandé.

Contrôles : chaque module de `src.core` et `src.ui` s'importe ; le catalogue embarqué
se lit et nomme au moins un jeu ; chaque langue embarquée traduit ; les polices
embarquées se chargent ; 7-Zip et les ressources dont les jeux ont besoin sont là.
"""

import importlib
import pkgutil
import sys
from pathlib import Path

DRAPEAU = "--verifier-exe"

# Importables seulement sur leur système : ils ne comptent pas comme manquants ailleurs.
_SEULEMENT_WINDOWS = frozenset({"src.core.composants_windows", "src.core.liste_saut"})


def demande(argv: list[str]) -> Path | None:
    """Le chemin du rapport si `argv` demande la vérification, sinon None."""
    if DRAPEAU not in argv:
        return None
    k = argv.index(DRAPEAU)
    return Path(argv[k + 1]) if k + 1 < len(argv) else Path("verification_exe.txt")


def _modules() -> list[str]:
    import src.core
    import src.ui
    noms = []
    for paquet in (src.core, src.ui):
        noms += [f"{paquet.__name__}.{m.name}" for m in pkgutil.iter_modules(paquet.__path__)]
    return sorted(noms)


def verifier() -> list[str]:
    """Les lignes du rapport ; celles qui commencent par « ÉCHEC » sont les défauts."""
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([sys.argv[0]])
    lignes: list[str] = []

    noms = _modules()
    if len(noms) < 100:
        lignes.append(f"ÉCHEC modules : {len(noms)} trouvés seulement (le paquet est-il complet ?)")
    for nom in noms:
        if sys.platform != "win32" and nom in _SEULEMENT_WINDOWS:
            continue
        try:
            importlib.import_module(nom)
        except Exception as exc:  # noqa: BLE001 — TOUT défaut d'import est le sujet du rapport
            lignes.append(f"ÉCHEC import {nom} : {exc.__class__.__name__}: {exc}")
    lignes.append(f"modules : {len(noms)} importés")

    from src.core.config import ASSETS_DIR, GAMES_JSON_PATH
    from src.core.game_data import load_catalog
    try:
        jeux = load_catalog(GAMES_JSON_PATH).games
        lignes.append(f"catalogue : {len(jeux)} jeux" if jeux else "ÉCHEC catalogue : aucun jeu")
    except Exception as exc:  # noqa: BLE001
        lignes.append(f"ÉCHEC catalogue : {exc}")

    from src.core import i18n
    for info in i18n.available_languages():
        if info.code == i18n.SOURCE_LANGUAGE:
            continue
        i18n.set_language(info.code)
        if i18n.tr("Fermer") == "Fermer":
            lignes.append(f"ÉCHEC langue {info.code} : rien n'est traduit")
    i18n.set_language(i18n.SOURCE_LANGUAGE)
    lignes.append(f"langues : {', '.join(i.code for i in i18n.available_languages())}")

    from PyQt6.QtGui import QFontDatabase
    from src.ui.fonts import load_fonts
    load_fonts()
    familles = set(QFontDatabase.families())
    for famille in ("Cinzel", "Cinzel Decorative", "Gelasio"):
        if not any(f.startswith(famille) for f in familles):
            lignes.append(f"ÉCHEC police {famille} : non chargée")

    sept = ASSETS_DIR / "7z" / ("7z.exe" if sys.platform == "win32" else "linux")
    for chemin in (sept, ASSETS_DIR / "backgrounds", ASSETS_DIR / "covers", ASSETS_DIR / "fonts"):
        if not chemin.exists():
            lignes.append(f"ÉCHEC ressource absente : {chemin.relative_to(ASSETS_DIR.parent)}")
    return lignes


def executer(rapport: Path) -> int:
    """Écrit le rapport (l'exe fenêtré n'a pas de console) ; 0 si tout va, 1 sinon."""
    try:
        lignes = verifier()
    except Exception as exc:  # noqa: BLE001 — le rapport doit exister même si la vérification casse
        lignes = [f"ÉCHEC vérification interrompue : {exc.__class__.__name__}: {exc}"]
    echecs = [ligne for ligne in lignes if ligne.startswith("ÉCHEC")]
    lignes.append(f"== {'OK' if not echecs else f'{len(echecs)} ÉCHEC(S)'}")
    rapport.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return 1 if echecs else 0
