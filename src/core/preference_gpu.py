"""Lancer un jeu sur la carte graphique la plus puissante (Windows, deux cartes ; les huit jeux).

Un portable à deux cartes (Intel + NVIDIA ou AMD) laisse Windows choisir, et un
vieux jeu 32 bits part souvent sur la puce économe : c'est l'une des causes
possibles des 5 images/s de HP1/HP2 relevées le 2026-11-18. Windows range le
choix de « Paramètres > Affichage > Graphiques » dans
`HKCU\\Software\\Microsoft\\DirectX\\UserGpuPreferences`, une valeur par exe
(chemin complet), des paires `nom=valeur;` dont `GpuPreference=2;` (haute
performance). Le launcher n'écrit QUE cette paire, sous HKCU (aucune UAC), au
geste du joueur, garde les autres paires que Windows y met, et la retire quand
on éteint : la valeur disparaît si rien d'autre n'y reste.

Proposé seulement sous Windows et sur une machine à deux cartes au moins ;
sous Linux (Wine), rien : la carte s'y choisit autrement.
"""

import functools
import logging
import sys
from pathlib import Path

from src.core import diagnostic

log = logging.getLogger(__name__)

CLE = r"Software\Microsoft\DirectX\UserGpuPreferences"
_NOM = "GpuPreference"
_PUISSANTE = "2"


def ajouter(donnee: str) -> str:
    """La donnée de la valeur avec `GpuPreference=2;`, les autres paires gardées (pure)."""
    paires = [p for p in donnee.split(";") if p.strip()
              and p.partition("=")[0].strip().casefold() != _NOM.casefold()]
    return "".join(f"{p};" for p in (*paires, f"{_NOM}={_PUISSANTE}"))


def retirer(donnee: str) -> str:
    """La donnée sans `GpuPreference` ; vide s'il ne reste rien (pure)."""
    paires = [p for p in donnee.split(";") if p.strip()
              and p.partition("=")[0].strip().casefold() != _NOM.casefold()]
    return "".join(f"{p};" for p in paires)


def puissante(donnee: str) -> bool:
    """La donnée demande-t-elle la carte la plus puissante ? (pure)"""
    return any(nom.strip().casefold() == _NOM.casefold() and valeur.strip() == _PUISSANTE
               for nom, _, valeur in (p.partition("=") for p in donnee.split(";")))


@functools.cache
def _deux_cartes() -> bool:
    """Lu une fois par session (registre, lecture seule) : les cartes ne changent pas."""
    return diagnostic.plusieurs_cartes()


def proposee(cartes: list[str] | None = None) -> bool:
    """Le réglage a-t-il un sens ici ? Windows, et deux cartes réelles au moins."""
    if sys.platform != "win32":
        return False
    return _deux_cartes() if cartes is None else diagnostic.plusieurs_cartes(cartes)


def _lire(exe: Path) -> str:
    if sys.platform != "win32":
        return ""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE) as cle:
            donnee = winreg.QueryValueEx(cle, str(exe))[0]
    except OSError:
        return ""
    return donnee if isinstance(donnee, str) else ""


def _ecrire(exe: Path, donnee: str) -> None:
    """Pose la donnée, ou supprime la valeur si elle est vide. OSError si refusé."""
    if sys.platform != "win32":
        raise OSError("registre de Windows seulement")
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, CLE, 0, winreg.KEY_SET_VALUE) as cle:
        if donnee:
            winreg.SetValueEx(cle, str(exe), 0, winreg.REG_SZ, donnee)
        else:
            winreg.DeleteValue(cle, str(exe))


def active(exe: Path) -> bool:
    """Windows lance-t-il cet exe sur la carte la plus puissante ?"""
    return puissante(_lire(exe))


def poser(exe: Path, oui: bool, cartes: list[str] | None = None) -> bool:
    """Demande (ou retire) la carte la plus puissante pour `exe`. True si c'est fait.

    Rien n'est écrit sur une machine à une seule carte, ni hors Windows.
    """
    if not proposee(cartes):
        return False
    avant = _lire(exe)
    apres = ajouter(avant) if oui else retirer(avant)
    if apres == avant:
        return True
    try:
        _ecrire(exe, apres)
    except OSError as exc:
        log.warning("Préférence de carte graphique non écrite pour %s : %s", exe, exc)
        return False
    log.info("Préférence de carte graphique %s pour %s", "posée" if oui else "retirée", exe)
    return True
