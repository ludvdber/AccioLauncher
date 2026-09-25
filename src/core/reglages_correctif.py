"""Réglages du correctif PC de HP4, HP5 et HP6, lus et écrits dans son `d3d9.ini`.

Le correctif (dépôt Harry-Potter-PC-Fix) lit un `d3d9.ini` à côté de l'exécutable
du jeu. Ce module en règle QUELQUES clés depuis le lanceur ; tout le reste du
fichier appartient au joueur et n'est jamais réécrit.

Trois règles :

- **Seulement ce qui a été VU en jeu.** Le catalogue déclare, jeu par jeu, les
  réglages confirmés (`fix_settings`) ; un identifiant inconnu d'une version
  plus ancienne du lanceur est ignoré. Proposer un réglage qu'on n'a jamais
  regardé tourner, c'est déplacer le test chez le joueur.
- **Seulement le NOUVEAU correctif.** Les archives publiées portent encore
  l'ancien wrapper, dont l'ini n'a pas ces clés : on le reconnaît à l'absence
  de `[Accio.Window]`, et l'interface dit alors que les réglages arrivent avec
  la prochaine version, au lieu d'écrire des clés que personne ne lira.
- **Une édition en place.** Commentaires, ordre, fins de ligne (CRLF) et
  encodage restent ceux du fichier : seule la ligne de la clé change.
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from src.core.i18n import tr

log = logging.getLogger(__name__)

NOM_INI = "d3d9.ini"
_MARQUE_V2 = "Accio.Window"   # section qu'a seul le nouveau correctif

# Choix proposés pour la limite d'images. 0 = aucune.
LIMITES_FPS = (0, 60, 100, 120, 144)

# Le préréglage « déplacement à gauche du clavier + sorts à la souris » :
# celui que l'ini livre en commentaire (tools/make_ini.py du correctif). Le
# correctif lit les touches par le nom IMPRIMÉ sur le clavier du joueur
# (keys.cpp) : les mêmes POSITIONS s'appellent ZQSD sur un AZERTY et WASD sur
# un QWERTY. Écrire « Z » pour tout le monde aurait mis « avancer » en bas à
# gauche d'un clavier américain. Les positions sont donc des codes de balayage
# (ceux d'un clavier US : W A S D, puis E et R), traduites en lettres selon la
# disposition active.
_POSITIONS = (("MoveUp", 0x11, "W"), ("MoveLeft", 0x1E, "A"), ("MoveDown", 0x1F, "S"),
              ("MoveRight", 0x20, "D"), ("Accio", 0x12, "E"), ("Extremos", 0x13, "R"))
_SOURIS = (("Charm", "MouseLeft"), ("Jinx", "MouseRight"))


def _lettre(scan: int, repli: str) -> str:
    """La lettre imprimée à cette position sur le clavier actif (Windows).

    Ailleurs, la position US : sous Linux le jeu tourne sous Wine, dont la
    disposition ne se lit pas d'ici, et un QWERTY est le cas le plus répandu.
    """
    if sys.platform != "win32":
        return repli
    try:
        import ctypes
        vk = ctypes.windll.user32.MapVirtualKeyW(scan, 1)   # MAPVK_VSC_TO_VK
    except (AttributeError, OSError):
        return repli
    # Pour une lettre, le code de touche virtuelle EST la majuscule ASCII.
    return chr(vk) if 0x41 <= vk <= 0x5A else repli


def touches_preregle() -> tuple[tuple[str, str], ...]:
    """(action, touche) du préréglage, pour le clavier de CE poste."""
    return tuple((action, _lettre(scan, us)) for action, scan, us in _POSITIONS) + _SOURIS


@dataclass(frozen=True)
class Reglage:
    ident: str
    section: str
    cle: str          # vide pour un réglage composé (les touches)
    libelle: str      # clé tr() ; passer par textes() pour l'afficher
    aide: str         # clé tr()


# L'ordre est celui de l'affichage.
REGLAGES: dict[str, Reglage] = {r.ident: r for r in (
    Reglage("arriere_plan", "Accio.Window", "KeepRunningInBackground",
            "Continuer à tourner après un Alt+Tab",
            "Le jeu ne se fige plus quand une autre fenêtre passe devant, "
            "et reprend le clavier dès qu'on revient."),
    Reglage("limite_fps", "Accio.Window", "FPSLimit",
            "Limite d'images par seconde",
            "Plafonne le nombre d'images calculées : l'ordinateur chauffe "
            "moins et fait moins de bruit."),
    Reglage("touches_zqsd", "Accio.Keys", "",
            "Déplacement {} et sorts à la souris",
            "Se déplacer avec {0}, Charme au clic gauche, Maléfice au clic "
            "droit, Accio sur {1}, Extremos sur {2}. Les touches d'origine "
            "continuent de marcher, sauf {3}, qui fait reculer."),
)}


def textes(reglage: Reglage) -> tuple[str, str]:
    """(libellé, aide) traduits, avec les lettres du clavier de ce poste."""
    if reglage.ident != "touches_zqsd":
        return tr(reglage.libelle), tr(reglage.aide)
    t = dict(touches_preregle())
    deplacement = t["MoveUp"] + t["MoveLeft"] + t["MoveDown"] + t["MoveRight"]
    return (tr(reglage.libelle).format(deplacement),
            tr(reglage.aide).format(deplacement, t["Accio"], t["Extremos"], t["MoveDown"]))

# Réglages du correctif pas encore confirmés en jeu : écrits, pour que celui
# qui les cherche comprenne qu'ils arrivent (même principe que la rubrique
# « Affichage » verrouillée).
A_VENIR = (
    "Résolution",
    "Format d'image",
    "Compteur d'images (FPS) et performances",
    "Effets d'image (lissage, lumière, ombres)",
)


def reglages_du_jeu(idents) -> tuple[Reglage, ...]:
    """Les réglages déclarés par le catalogue, connus de CE lanceur, dans l'ordre d'affichage."""
    voulus = set(idents or ())
    return tuple(r for r in REGLAGES.values() if r.ident in voulus)


def chemin_ini(dossier_exe: Path) -> Path:
    return dossier_exe / NOM_INI


# ── Lecture et écriture de l'ini, en place ──

_SECTION = re.compile(r"^\s*\[([^\]]+)\]\s*$")


def _lire(chemin: Path) -> tuple[list[str], str]:
    """Lignes SANS fin de ligne, et la fin de ligne du fichier."""
    brut = chemin.read_bytes().decode("utf-8", errors="surrogateescape")
    fin = "\r\n" if "\r\n" in brut else "\n"
    return brut.split(fin), fin


def _ecrire(chemin: Path, lignes: list[str], fin: str) -> None:
    texte = fin.join(lignes)
    tmp = chemin.with_name(chemin.name + ".tmp")
    tmp.write_bytes(texte.encode("utf-8", errors="surrogateescape"))
    tmp.replace(chemin)


def _bornes(lignes: list[str], section: str) -> tuple[int, int] | None:
    """(première ligne après l'en-tête, ligne de la section suivante), ou None."""
    debut = None
    for i, ligne in enumerate(lignes):
        m = _SECTION.match(ligne)
        if not m:
            continue
        if debut is not None:
            return debut, i
        if m.group(1).strip().lower() == section.lower():
            debut = i + 1
    return (debut, len(lignes)) if debut is not None else None


def _motif_cle(cle: str, commentee: bool) -> re.Pattern:
    prefixe = r"\s*;\s*" if commentee else r"\s*"
    return re.compile(prefixe + re.escape(cle) + r"\s*=(.*)$", re.IGNORECASE)


def _valeur(lignes: list[str], section: str, cle: str) -> str | None:
    bornes = _bornes(lignes, section)
    if bornes is None:
        return None
    motif = _motif_cle(cle, commentee=False)
    for ligne in lignes[bornes[0]:bornes[1]]:
        m = motif.match(ligne)
        if m:
            # Le correctif lit ses valeurs avec les commentaires de fin de ligne
            # (« 100 // max fps » dans les anciens ini) : ne garder que la valeur.
            return re.split(r"\s*(?://|;)", m.group(1), maxsplit=1)[0].strip()
    return None


def _poser(lignes: list[str], section: str, cle: str, valeur: str | None) -> bool:
    """Pose `cle=valeur` (ou la commente si valeur est None). False si la section manque."""
    bornes = _bornes(lignes, section)
    if bornes is None:
        return False
    debut, fin = bornes
    active, commentee = _motif_cle(cle, False), _motif_cle(cle, True)
    for i in range(debut, fin):
        if active.match(lignes[i]) or commentee.match(lignes[i]):
            lignes[i] = f"{cle}={valeur}" if valeur is not None else f";{cle}={_ancienne(lignes[i])}"
            return True
    if valeur is None:
        return True   # rien à commenter
    # Clé absente : juste après la dernière ligne non vide de la section.
    j = fin
    while j > debut and not lignes[j - 1].strip():
        j -= 1
    lignes.insert(j, f"{cle}={valeur}")
    return True


def _ancienne(ligne: str) -> str:
    return ligne.split("=", 1)[1].strip() if "=" in ligne else ""


# ── Ce que voit l'interface ──

@dataclass(frozen=True)
class Etat:
    """Ce que porte l'ini pour un réglage.

    `valeur` : bool pour un interrupteur, int pour la limite d'images.
    `personnalise` : l'ini porte une valeur que l'interface ne sait pas
    représenter (touches choisies à la main) — on l'affiche, on ne l'écrase pas.
    """
    valeur: object
    personnalise: bool = False


def est_nouveau_correctif(ini: Path) -> bool:
    try:
        lignes, _ = _lire(ini)
    except OSError:
        return False
    return _bornes(lignes, _MARQUE_V2) is not None


def lire(ini: Path, reglage: Reglage) -> Etat:
    lignes, _ = _lire(ini)
    if reglage.ident == "touches_zqsd":
        preregle = touches_preregle()
        actives = {cle: _valeur(lignes, reglage.section, cle) for cle, _ in preregle}
        if all(actives[cle] is not None and actives[cle].lower() == v.lower() for cle, v in preregle):
            return Etat(True)
        return Etat(False, personnalise=any(v is not None for v in actives.values()))
    brut = _valeur(lignes, reglage.section, reglage.cle)
    if reglage.ident == "limite_fps":
        try:
            n = int(brut) if brut is not None else 0
        except ValueError:
            return Etat(0, personnalise=True)
        return Etat(n, personnalise=n not in LIMITES_FPS)
    # Interrupteur : le correctif lit 0 = non, tout autre nombre = oui ; défaut oui.
    if brut is None:
        return Etat(True)
    return Etat(brut.strip() not in ("0", ""))


def ecrire(ini: Path, reglage: Reglage, valeur) -> None:
    """Écrit un réglage. Lève OSError si le fichier ne peut pas être écrit,
    ValueError si la valeur n'est pas de celles que l'interface propose."""
    lignes, fin = _lire(ini)
    if reglage.ident == "touches_zqsd":
        for cle, touche in touches_preregle():
            if not _poser(lignes, reglage.section, cle, touche if valeur else None):
                raise ValueError(f"section [{reglage.section}] absente")
    elif reglage.ident == "limite_fps":
        if valeur not in LIMITES_FPS:
            raise ValueError(f"limite {valeur!r} non proposée")
        if not _poser(lignes, reglage.section, reglage.cle, str(int(valeur))):
            raise ValueError(f"section [{reglage.section}] absente")
    else:
        if not _poser(lignes, reglage.section, reglage.cle, "1" if valeur else "0"):
            raise ValueError(f"section [{reglage.section}] absente")
    _ecrire(ini, lignes, fin)
    log.info("Correctif : %s = %r dans %s", reglage.ident, valeur, ini)
