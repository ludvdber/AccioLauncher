"""Informations de diagnostic — ce qu'il faut pour dépanner quelqu'un à distance.

Né de l'audit du 2026-09-18. Le launcher circule de main en main et l'aide
passe par le Discord : la première question y est toujours la même (« quelle
version, quel Windows, quel jeu ? ») et la personne ne sait pas y répondre.
Deux défauts le rendaient pénible :

- le JOURNAL ne portait ni la version du launcher ni celle de Windows — hors
  ligne, la version n'y apparaissait jamais, puisqu'elle n'était écrite que par
  la vérification des mises à jour ;
- rien ne permettait de COPIER ces informations : il fallait les dicter.

Ce module est pur (aucun widget) : il lit la plateforme, le catalogue, les
stats et le journal, et rend du texte. L'interface se contente de le copier.

Rien de personnel n'en sort : le dossier personnel est remplacé par « ~ »
(`scrub_user_paths`), qui cachait déjà le nom d'utilisateur dans le rapport de
plantage.
"""

from __future__ import annotations

import platform
import shutil
import sys
from pathlib import Path

from src.core.config import APP_VERSION

# Lignes du journal reprises dans le diagnostic : les AVERTISSEMENTS et les
# ERREURS seulement. Le reste raconte le fonctionnement normal, et un
# diagnostic de plus de 2 000 caractères devient une pièce jointe sur Discord.
_LIGNES_NOTABLES = 12
_TENTATIVES = 5


def scrub_user_paths(text: str) -> str:
    """Remplace le dossier personnel par ~ (ne pas exposer le nom d'utilisateur)."""
    home = str(Path.home())
    for variant in (home, home.replace("\\", "/"), home.replace("\\", "\\\\")):
        text = text.replace(variant, "~")
    return text


def systeme() -> str:
    """« Windows 11 Professional 10.0.26200 (AMD64) », ou l'équivalent ailleurs."""
    if sys.platform == "win32":
        release, version, _, _ = platform.win32_ver()
        edition = platform.win32_edition() or ""
        nom = " ".join(x for x in ("Windows", release, edition, version) if x)
    else:
        nom = f"{platform.system()} {platform.release()}"
    return f"{nom} ({platform.machine()})"


def identite() -> str:
    """Une ligne : version, forme (exe ou sources), système, Python, Qt."""
    try:
        from PyQt6.QtCore import qVersion
        qt = f" · Qt {qVersion()}"
    except ImportError:
        qt = ""
    forme = "exe" if getattr(sys, "frozen", False) else "sources"
    return (f"Accio Launcher {APP_VERSION} ({forme}) · {systeme()}"
            f" · Python {platform.python_version()}{qt}")


def ecran(largeur: int, hauteur: int, echelle: float) -> str:
    """« 2560×1440 à 125 % » — en pixels PHYSIQUES : Qt donne des pixels
    logiques (2048×1152 pour le même écran), qu'on ne reconnaît pas."""
    return f"{round(largeur * echelle)}×{round(hauteur * echelle)} à {round(echelle * 100)} %"


def lignes_notables(journal: str, n: int = _LIGNES_NOTABLES) -> list[str]:
    """Les `n` derniers avertissements et erreurs d'un journal."""
    marques = ("WARNING:", "ERROR:", "CRITICAL:")
    return [ligne for ligne in journal.splitlines()
            if any(m in ligne for m in marques)][-n:]


def _espace_libre(dossier: Path) -> str:
    chemin = dossier
    while not chemin.exists() and chemin != chemin.parent:
        chemin = chemin.parent
    try:
        return f"{shutil.disk_usage(chemin).free / 1024 ** 3:.0f} Go libres"
    except OSError:
        return "espace libre inconnu"


def rapport(manager, ecrans: list[str] | None = None, journal: str = "",
            tentatives=None, prerequis: dict[str, bool] | None = None) -> str:
    """Le bloc à coller sur le Discord.

    `tentatives` et `prerequis` sont injectables pour les tests ; par défaut ils
    sont lus (journal des sessions, contrôles système mis en cache).
    """
    config = manager.config
    lignes = [identite()]
    langue = getattr(config, "langue", "?")
    lignes.append(f"Interface : {langue} · thème {getattr(config, 'theme', '?')}"
                  f" · catalogue v{manager.catalog.catalog_version}")
    if ecrans:
        lignes.append("Écrans : " + " ; ".join(ecrans))
    lignes.append(f"Dossier des jeux : {config.install_path} — "
                  f"{_espace_libre(Path(config.install_path))}")

    if prerequis is None:
        from src.core.system_checks import PREREQUIS, check_d3d11_feature_level
        prerequis = {nom: bool(test()) for nom, (test, _) in PREREQUIS.items()}
        prerequis["directx11"] = bool(check_d3d11_feature_level())
    lignes.append("Prérequis : " + ", ".join(
        f"{nom} {'OK' if ok else 'MANQUANT'}" for nom, ok in prerequis.items()))

    from src.core.game_manager import GameState

    installes = []
    for g in manager.catalog.games:
        etat = manager.get_state(g.id)
        if etat == GameState.NOT_INSTALLED:
            continue
        version = manager.installed_version(g.id) or "?"
        minutes = manager.get_playtime(g.id) // 60
        installes.append(f"  {g.id} v{version} — {etat} — {minutes} min de jeu")
    lignes.append("Jeux installés :" if installes else "Jeux installés : aucun")
    lignes += installes

    if tentatives is None:
        try:
            from src.core import stats
            tentatives = stats.charger().tentatives
        except Exception:  # un journal illisible ne doit pas priver du reste
            tentatives = ()
    recentes = sorted(tentatives, key=lambda t: t.debut)[-_TENTATIVES:]
    if recentes:
        lignes.append("Lancements qui n'ont pas démarré :")
        lignes += [f"  {t.jeu} le {t.debut:%Y-%m-%d %H:%M} — {t.duree} s, code {t.code}"
                   for t in recentes]

    notables = lignes_notables(journal)
    if notables:
        lignes.append(f"── Journal : {len(notables)} derniers avertissements ──")
        lignes += notables
    return scrub_user_paths("\n".join(lignes))
