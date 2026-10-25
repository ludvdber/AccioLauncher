"""Imports paresseux de Python 3.15 (PEP 810), limités aux modules du launcher.

Une fois `activer()` appelée, un `import` de niveau module visant `src.*` ne
charge plus rien : le module se charge à son premier usage. La fenêtre
principale tirait d'office À propos, la reprise, les captures, le diagnostic de
plantage, les réglages… Mesuré le 2026-10-25 (banc muet, démarrages alternés,
12 par configuration) : 62 modules du launcher de moins à l'ouverture,
démarrage 711 ms au lieu de 761, mémoire privée 51,5 Mo au lieu de 56,2.

Limité à `src.*` : en mode global (`-X lazy_imports=all`), pytest lui-même
tombe sur un `ImportCycleError` dans son propre mécanisme d'import ; les
bibliothèques tierces gardent donc leurs imports tels quels. Rendre paresseux
aussi ce que NOS modules importent (bibliothèque standard) ne gagnait rien de
plus (708 ms).

La syntaxe `lazy import` reste interdite : le fuzzing tourne en 3.14, qui ne
la lit pas. La 3.14 n'a pas `sys.set_lazy_imports` : `activer()` n'y fait que
le préchargement.
"""

import importlib
import sys

# Règle 5 : un module d'extension Qt se crée au démarrage, jamais en pleine
# session. Avec la paresse, le module qui l'importe ne s'exécute plus qu'à son
# premier usage (lecteur vidéo, icône SVG) : on les crée donc ici, d'office.
# `tests/test_imports_qt.py` vérifie que tout module d'extension importé dans
# `src/` figure dans cette liste.
MODULES_QT_A_CHARGER_TOT = ("PyQt6.QtNetwork", "PyQt6.QtSvg", "PyQt6.QtMultimedia")


def seulement_le_launcher(_importeur: str | None, module: str,
                          _noms: tuple[str, ...] | None = None) -> bool:
    """Filtre de `sys.set_lazy_imports_filter` : paresseux pour `src.*` seul."""
    return module.startswith("src.")


def activer() -> bool:
    """Précharge les modules d'extension Qt, puis active la paresse si
    l'interpréteur la connaît. Vrai si elle est active. À appeler avant tout
    objet Qt et avant d'importer la fenêtre principale."""
    for nom in MODULES_QT_A_CHARGER_TOT:
        try:
            importlib.import_module(nom)
        except ImportError:   # QtMultimedia peut manquer sous Linux : video_player dégrade
            pass
    if not hasattr(sys, "set_lazy_imports"):
        return False
    sys.set_lazy_imports("all")
    sys.set_lazy_imports_filter(seulement_le_launcher)
    return True
