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

import logging
import platform
import shutil
import sys
from pathlib import Path

from src.core.config import APP_VERSION

log = logging.getLogger(__name__)

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


# Classe des adaptateurs d'affichage dans le registre (GUID fixe de Windows).
_CLE_AFFICHAGE = (r"SYSTEM\CurrentControlSet\Control\Class"
                  r"\{4d36e968-e325-11ce-bfc1-08002be10318}")


def version_pilote_publique(fournisseur: str, version: str, radeon: str = "") -> str:
    """Le numéro que l'utilisateur RECONNAÎT, pas celui de Windows.

    Windows range « 32.0.16.1074 » là où NVIDIA affiche « 610.74 » : ce sont
    les cinq derniers chiffres des deux derniers blocs. AMD range son numéro
    public (« 25.8.1 ») dans une valeur à part. Intel affiche le numéro Windows
    tel quel. Demander « quelle version de pilote ? » à quelqu'un qui lit
    610.74 dans son panneau NVIDIA et voir 32.0.16.1074 ici, c'est deux
    réponses qu'on ne sait pas raccorder.
    """
    fournisseur = fournisseur.lower()
    if "nvidia" in fournisseur:
        blocs = version.split(".")
        if len(blocs) == 4 and all(b.isdigit() for b in blocs[2:]):
            chiffres = (blocs[2] + blocs[3].zfill(4))[-5:]
            return f"{chiffres[:3]}.{chiffres[3:]}"
    if radeon and ("amd" in fournisseur or "ati" in fournisseur):
        return radeon
    return version


def _processeur() -> str:
    """Nom commercial du processeur et nombre de cœurs logiques."""
    import os
    nom = ""
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as cle:
                nom = str(winreg.QueryValueEx(cle, "ProcessorNameString")[0])
        except OSError:
            pass
    nom = " ".join((nom or platform.processor() or "inconnu").split())
    return f"{nom} ({os.cpu_count() or '?'} threads)"


def _memoire() -> str:
    """Mémoire vive totale, en Go ; vide si le système ne la dit pas."""
    if sys.platform != "win32":
        return ""
    import ctypes

    class _Etat(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    etat = _Etat()
    etat.dwLength = ctypes.sizeof(_Etat)
    try:
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(etat)):
            return ""
    except (AttributeError, OSError):
        return ""
    return f"{etat.ullTotalPhys / 1024 ** 3:.0f} Go"


def _cartes_graphiques() -> list[str]:
    """Une ligne par adaptateur d'affichage : nom, pilote, date, mémoire.

    Lu dans le REGISTRE, en lecture seule, et non par `wmic` (retiré de
    Windows 11 24H2) ni PowerShell (une seconde de démarrage pour trois
    valeurs). Les adaptateurs virtuels (Parsec, écran distant…) sont gardés et
    signalés : ils sont justement une cause classique de plein écran raté.
    """
    if sys.platform != "win32":
        return []
    import winreg
    cartes = []
    try:
        classe = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _CLE_AFFICHAGE)
    except OSError:
        return []
    with classe:
        i = 0
        while i < 32:
            try:
                sous = winreg.EnumKey(classe, i)
            except OSError:
                break
            i += 1
            if not sous.isdigit():
                continue
            valeurs = {}
            try:
                with winreg.OpenKey(classe, sous) as cle:
                    for nom in ("DriverDesc", "DriverVersion", "DriverDate", "ProviderName",
                                "RadeonSoftwareVersion", "MatchingDeviceId",
                                "HardwareInformation.qwMemorySize"):
                        try:
                            valeurs[nom] = winreg.QueryValueEx(cle, nom)[0]
                        except OSError:
                            pass
            except OSError:
                continue
            if not valeurs.get("DriverDesc"):
                continue
            cartes.append(carte_graphique(valeurs))
    return cartes


def carte_graphique(v: dict) -> str:
    """Met en forme une entrée du registre (pure, testable hors Windows)."""
    fournisseur = f"{v.get('ProviderName', '')} {v.get('DriverDesc', '')}"
    version = version_pilote_publique(fournisseur, str(v.get("DriverVersion", "?")),
                                      str(v.get("RadeonSoftwareVersion", "") or ""))
    morceaux = [str(v["DriverDesc"]).strip(), f"pilote {version}"]
    if v.get("DriverDate"):
        # Windows l'écrit à l'américaine (« 7-2-2026 » = 2 juillet) : lu en
        # Europe, c'est le 7 février. ISO, que personne ne lit de travers.
        m, _, reste = str(v["DriverDate"]).partition("-")
        j, _, a = reste.partition("-")
        date = (f"{a}-{int(m):02d}-{int(j):02d}"
                if m.isdigit() and j.isdigit() and a.isdigit() else str(v["DriverDate"]))
        morceaux.append(f"du {date}")
    memoire = v.get("HardwareInformation.qwMemorySize")
    if isinstance(memoire, int) and memoire > 0:
        morceaux.append(f"{memoire / 1024 ** 3:.0f} Go")
    if not str(v.get("MatchingDeviceId", "")).lower().startswith("pci"):
        morceaux.append("virtuel")
    return " · ".join(morceaux)


def materiel() -> list[str]:
    """Processeur, mémoire et cartes graphiques : ce qu'on demande d'abord
    devant un écran noir ou un jeu qui ne passe pas en plein écran."""
    lignes = []
    memoire = _memoire()
    lignes.append(f"Processeur : {_processeur()}" + (f" · {memoire} de mémoire" if memoire else ""))
    cartes = _cartes_graphiques()
    if cartes:
        lignes.append("Carte graphique : " + cartes[0] if len(cartes) == 1
                      else "Cartes graphiques :")
        if len(cartes) > 1:
            lignes += [f"  {c}" for c in cartes]
    return lignes


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
            tentatives=None, prerequis: dict[str, bool] | None = None,
            machine: list[str] | None = None) -> str:
    """Le bloc à coller sur le Discord.

    `tentatives`, `prerequis` et `machine` sont injectables pour les tests ;
    par défaut ils sont lus (journal des sessions, contrôles système mis en
    cache, registre en lecture seule).
    """
    config = manager.config
    lignes = [identite()]
    langue = getattr(config, "langue", "?")
    lignes.append(f"Interface : {langue} · thème {getattr(config, 'theme', '?')}"
                  f" · catalogue v{manager.catalog.catalog_version}")
    try:
        lignes += materiel() if machine is None else machine
    except Exception as exc:  # un registre inattendu ne doit pas priver du reste
        log.warning("Matériel illisible pour le diagnostic : %s", exc)
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
