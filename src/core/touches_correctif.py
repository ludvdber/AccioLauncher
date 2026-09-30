"""Les touches de HP4, une par une, dans `[Accio.Keys]` du `d3d9.ini` de son correctif.

Le correctif (keys.cpp) donne à chaque action du jeu les touches que le joueur
nomme, telles qu'IMPRIMÉES sur son clavier (« Z » sur un AZERTY est la touche
marquée Z). Trois choses qu'il fait, et que l'éditeur doit montrer :

- une touche donnée à une action PERD son rôle d'origine : poser « S » sur
  Reculer retire Extremos (S d'origine) à qui ne lui en donne pas une autre ;
- une action sans ligne garde la touche d'origine du jeu ;
- plusieurs touches pour une action (`Charm=MouseLeft,J`) : l'éditeur les
  montre, et en remplace la liste entière quand on en choisit une.

Pas de Qt ici : la traduction d'un appui en nom de touche vit dans l'interface
(`ui/editeur_touches.py`), le reste se teste sans fenêtre.
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from src.core import reglages_correctif as rc
from src.core.i18n import tr

log = logging.getLogger(__name__)

SECTION = "Accio.Keys"


@dataclass(frozen=True)
class Action:
    cle: str         # nom lu par le correctif (kActionsHp4)
    libelle: str     # clé tr(), ou nom propre si `traduire` est faux
    position: int    # la touche d'origine du jeu : code DirectInput (position US)
    traduire: bool = True


# Dans l'ordre du jeu. Les sorts gardent leur nom : ce sont ceux qu'affiche HP4.
ACTIONS = (
    Action("MoveUp", "Avancer", 0xC8),
    Action("MoveDown", "Reculer", 0xD0),
    Action("MoveLeft", "Aller à gauche", 0xCB),
    Action("MoveRight", "Aller à droite", 0xCD),
    Action("Charm", "Charme", 0x2E),
    Action("Jinx", "Maléfice", 0x2D),
    Action("Accio", "Accio", 0x2C, traduire=False),
    Action("Extremos", "Extremos", 0x1F, traduire=False),
    Action("Pause", "Pause", 0x01),
    Action("Confirm", "Valider", 0x1C),
    Action("Back", "Retour", 0x0E),
)
PAR_CLE = {a.cle: a for a in ACTIONS}

# Les touches nommées par ce qu'elles sont (kNamedKeys du correctif) : leur code
# DirectInput, et ce qu'on en affiche (clé tr(), ou tel quel si None).
_NOMMEES: dict[str, tuple[int, str | None]] = {
    "Escape": (0x01, "Échap"), "Tab": (0x0F, "Tabulation"), "Enter": (0x1C, "Entrée"),
    "Space": (0x39, "Espace"), "Backspace": (0x0E, "Retour arrière"), "CapsLock": (0x3A, "Verr. maj"),
    "LShift": (0x2A, "Maj gauche"), "RShift": (0x36, "Maj droite"),
    "LCtrl": (0x1D, "Ctrl gauche"), "RCtrl": (0x9D, "Ctrl droite"),
    "LAlt": (0x38, "Alt gauche"), "RAlt": (0xB8, "Alt droite"),
    "Up": (0xC8, "Flèche haut"), "Down": (0xD0, "Flèche bas"),
    "Left": (0xCB, "Flèche gauche"), "Right": (0xCD, "Flèche droite"),
    "Insert": (0xD2, "Inser"), "Delete": (0xD3, "Suppr"), "Home": (0xC7, "Début"), "End": (0xCF, "Fin"),
    "PageUp": (0xC9, "Page précédente"), "PageDown": (0xD1, "Page suivante"),
    "NumEnter": (0x9C, "Entrée du pavé"),
    **{f"F{n}": (c, None) for n, c in zip(range(1, 13), (*range(0x3B, 0x45), 0x57, 0x58))},
    **{f"Num{n}": (c, None) for n, c in zip(
        range(10), (0x52, 0x4F, 0x50, 0x51, 0x4B, 0x4C, 0x4D, 0x47, 0x48, 0x49))},
}
# « Return » est un alias de « Enter » pour le correctif.
_ALIAS = {"return": "Enter"}
_SOURIS = {"MouseLeft": "Clic gauche", "MouseRight": "Clic droit", "MouseMiddle": "Clic molette",
           "Mouse4": "Bouton 4 de la souris", "Mouse5": "Bouton 5 de la souris"}
# Positions US des lettres et chiffres, pour savoir quelle action une lettre prend
# hors Windows (sous Linux la disposition de Wine ne se lit pas d'ici : QWERTY).
_US = {**{c: 0x10 + i for i, c in enumerate("QWERTYUIOP")},
       **{c: 0x1E + i for i, c in enumerate("ASDFGHJKL")},
       **{c: 0x2C + i for i, c in enumerate("ZXCVBNM")},
       **{str(n): 0x02 + (n - 1) % 10 for n in range(10)}}


def _canonique(nom: str) -> str | None:
    """Le nom tel que l'écrit l'éditeur, ou None si le correctif ne le lirait pas."""
    nom = nom.strip()
    if nom.lower() in _ALIAS:
        return _ALIAS[nom.lower()]
    for connu in (*_NOMMEES, *_SOURIS):
        if connu.lower() == nom.lower():
            return connu
    # Un caractère imprimé : ASCII visible, sauf les deux séparateurs de la ligne.
    if len(nom) == 1 and 0x21 <= ord(nom) <= 0x7E and nom not in ",;":
        return nom.upper()
    return None


def nom_valide(nom: str) -> bool:
    return _canonique(nom) is not None


def texte_touche(nom: str) -> str:
    """Ce qu'on montre d'une touche (« Clic gauche », « Flèche haut », « Z »)."""
    canon = _canonique(nom)
    if canon is None:
        return nom
    if canon in _SOURIS:
        return tr(_SOURIS[canon])
    if canon in _NOMMEES:
        affiche = _NOMMEES[canon][1]
        if affiche is not None:
            return tr(affiche)
        if canon.startswith("Num"):
            return tr("Pavé {}").format(canon[3:])
        return canon
    return canon


def libelle(action: Action) -> str:
    return tr(action.libelle) if action.traduire else action.libelle


def _lettre_a(position: int) -> str | None:
    """Le caractère imprimé à cette position du clavier actif (Windows), sinon None."""
    if sys.platform != "win32":
        return next((c for c, p in _US.items() if p == position), None)
    try:
        import ctypes
        vk = ctypes.windll.user32.MapVirtualKeyW(position, 1)   # MAPVK_VSC_TO_VK
        car = ctypes.windll.user32.MapVirtualKeyW(vk, 2)         # MAPVK_VK_TO_CHAR
    except (AttributeError, OSError):
        return None
    car &= 0x7FFF   # le bit haut marque une touche morte
    return chr(car).upper() if 0x21 <= car <= 0x7E else None


def touche_d_origine(action: Action) -> str:
    """La touche du jeu pour cette action, telle qu'imprimée sur CE clavier."""
    for nom, (code, _) in _NOMMEES.items():
        if code == action.position:
            return texte_touche(nom)
    return _lettre_a(action.position) or "?"


def _position(nom: str) -> int | None:
    """Le code DirectInput que le correctif associe à ce nom (None : souris, ou inconnu)."""
    canon = _canonique(nom)
    if canon is None or canon in _SOURIS:
        return None
    if canon in _NOMMEES:
        return _NOMMEES[canon][0]
    if sys.platform != "win32":
        return _US.get(canon)
    try:
        import ctypes
        vk = ctypes.windll.user32.VkKeyScanW(ord(canon))
        if vk == -1 or vk == 0xFFFF:
            return None
        scan = ctypes.windll.user32.MapVirtualKeyW(vk & 0xFF, 0)   # MAPVK_VK_TO_VSC
    except (AttributeError, OSError):
        return None
    return scan if 0 < scan < 0x80 else None


# ── Lecture et écriture ──

def touches(ini: Path) -> dict[str, tuple[str, ...]]:
    """action → touches choisies (vide : la touche d'origine du jeu). Lève OSError."""
    lignes, _ = rc._lire(ini)
    choisies = {}
    for action in ACTIONS:
        brut = rc._valeur(lignes, SECTION, action.cle)
        noms = tuple(n.strip() for n in re.split(r"[,;]", brut or "") if n.strip())
        choisies[action.cle] = noms
    return choisies


def sans_touche(choisies: dict[str, tuple[str, ...]]) -> dict[str, str]:
    """Les actions restées sans aucune touche : action → l'action qui a pris la sienne.

    Une action sans ligne compte sur sa touche d'origine ; si une AUTRE action
    s'est vu donner cette touche, le correctif la lui retire (g_consumed).
    """
    prises: dict[int, str] = {}
    for cle, noms in choisies.items():
        for nom in noms:
            p = _position(nom)
            if p is not None and p != PAR_CLE[cle].position:
                prises.setdefault(p, cle)
    return {a.cle: prises[a.position] for a in ACTIONS
            if not choisies.get(a.cle) and a.position in prises}


def attribuer(ini: Path, action: str, nom: str) -> tuple[str, ...]:
    """Donne CETTE touche (seule) à l'action ; la retire aux autres actions qui l'avaient.

    Rend les actions qui l'ont perdue. Lève ValueError pour un nom que le
    correctif ne lirait pas ou une section absente, OSError si le fichier ne
    peut pas être écrit.
    """
    canon = _canonique(nom)
    if canon is None or action not in PAR_CLE:
        raise ValueError(f"touche {nom!r} pour {action!r}")
    lignes, fin = rc._lire(ini)
    avant = touches(ini)
    rc._garder_origine(ini)
    perdues = []
    for autre, noms in avant.items():
        if autre == action or not any(_canonique(n) == canon for n in noms):
            continue
        reste = [n for n in noms if _canonique(n) != canon]
        rc._poser(lignes, SECTION, autre, ",".join(reste) if reste else None)
        perdues.append(autre)
    if not rc._poser(lignes, SECTION, action, canon):
        raise ValueError(f"section [{SECTION}] absente")
    rc._ecrire(ini, lignes, fin)
    log.info("Correctif : %s = %s dans %s%s", action, canon, ini,
             f" (retirée de {', '.join(perdues)})" if perdues else "")
    return tuple(perdues)


def rendre(ini: Path, actions=None) -> None:
    """Rend à ces actions (toutes par défaut) la touche d'origine du jeu : lignes commentées."""
    lignes, fin = rc._lire(ini)
    rc._garder_origine(ini)
    for cle in actions if actions is not None else PAR_CLE:
        rc._poser(lignes, SECTION, cle, None)
    rc._ecrire(ini, lignes, fin)
    log.info("Correctif : touches d'origine rendues (%s) dans %s",
             "toutes" if actions is None else ", ".join(actions), ini)
