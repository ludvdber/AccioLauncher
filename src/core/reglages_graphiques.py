"""Réglages graphiques de HP3, lus et écrits dans le fichier de son traducteur D3D8.

Demandé par Ludo le 2026-10-07 : « pourquoi ne pas mettre ce paramètre dans
l'engrenage du jeu », puis « les autres paramètres également ». Le déclencheur :
un joueur sur puce Intel UHD dont HP3 s'arrête à chaque lancement sur
« SetRenderTarget failed » en dessinant l'ombre de Harry (`notes/HP3.md` du
correctif). L'hypothèse est l'antialiasing 8x livré en v1.2, imposé jusqu'aux
textures de rendu : sans réglage, la seule issue était d'éditer ce fichier au
Bloc-notes.

HP3 n'a pas le correctif d'Accio : son image passe par un traducteur D3D8 → D3D11 livré avec le jeu,
dont la qualité se règle dans `system\\dgVoodoo.conf`, à côté de l'exe. Ce n'est
pas le `d3d9.ini` de `reglages_correctif` : clés alignées (« Clé = valeur »),
booléens `true`/`false`, et une même clé dans plusieurs sections
(`ForceVerticalSync` est dans `[Glide]` ET `[DirectX]`) — d'où une édition
toujours bornée à SA section. La présentation, elle, est la même (`Reglage`).

Mêmes règles que pour le correctif : une édition EN PLACE (seule la valeur de
la ligne change, alignement, commentaires et fins de ligne gardés), une copie
d'origine avant la première retouche, et jamais plus de 60 images/s (au-delà,
diablotin figé et portraits qui ne s'ouvrent plus : `notes/HP3.md`).

Windows seulement : sous Linux, Proton rend HP3 sans ce traducteur (2026-10-01),
et ces clés ne seraient lues par personne.
"""

from __future__ import annotations

import logging
import re
import shutil
import sys
from pathlib import Path

from src.core.reglages_correctif import Etat, _bornes, _ecrire, _lire
from src.core.reglages_table import Reglage

log = logging.getLogger(__name__)

NOM = "dgVoodoo.conf"
SUFFIXE_ORIGINE = ".origine"

ANTIALIASING = (("off", ""), ("2x", "2x"), ("4x", "4x"), ("8x", "8x"))
FILTRAGES = (("appdriven", ""), ("4", "4x"), ("8", "8x"), ("16", "16x"))
# `max` : la taille de l'écran ; `max_fhd`/`max_qhd` : la plus grande qui tient
# sous 1080p / 1440p (documentation dans le fichier) ; `unforced` : celle
# que demande le jeu.
RESOLUTIONS = (("unforced", ""), ("max_fhd", "Jusqu'à 1080p"), ("max_qhd", "Jusqu'à 1440p"),
               ("max", "Celle de l'écran"))
LIMITES = (("60", ""), ("30", "30"))

REGLAGES: dict[str, Reglage] = {r.ident: r for r in (
    Reglage("graph_resolution", "DirectX", "Resolution",
            "Résolution de rendu",
            "La taille à laquelle l'image est calculée, quelle que soit celle que choisit le "
            "jeu. « Celle de l'écran » donne l'image la plus nette ; « Jusqu'à 1080p » "
            "soulage une carte graphique modeste sur un grand écran.",
            choix=tuple(v for v, _ in RESOLUTIONS), zero="Celle du jeu", noms_choix=RESOLUTIONS,
            onglet="image", cout=(("GPU", 2),), se_voit=True),
    Reglage("graph_antialiasing", "DirectX", "Antialiasing",
            "Anticrénelage",
            "Lisse les bords en escalier des objets. 8x est livré ; 4x se voit à peine moins "
            "et coûte moins. Si le jeu s'arrête dès son lancement (« SetRenderTarget "
            "failed »), essayez 4x, puis « Aucun » : certaines puces graphiques, Intel "
            "notamment, refusent le 8x.",
            choix=tuple(v for v, _ in ANTIALIASING), zero="Aucun", noms_choix=ANTIALIASING,
            onglet="image", cout=(("GPU", 3),), se_voit=True),
    Reglage("graph_textures_rendu", "DirectXExt", "RTTexturesForceScaleAndMSAA",
            "Lisser aussi les ombres et reflets",
            "Applique la résolution et l'anticrénelage choisis aux images que le jeu calcule "
            "à part, comme l'ombre de Harry : elles restent fines au lieu de pixeliser. "
            "Éteint, elles gardent leur taille d'origine. À éteindre si le jeu s'arrête "
            "dès son lancement et que baisser l'anticrénelage n'a pas suffi.",
            defaut=True, onglet="image", cout=(("GPU", 1),), se_voit=True),
    Reglage("graph_filtrage", "DirectX", "Filtering",
            "Filtrage des textures",
            "Garde nettes les textures vues de biais, comme le sol au loin. 16x est livré "
            "et ne coûte presque rien.",
            choix=tuple(v for v, _ in FILTRAGES), zero="Celui du jeu", noms_choix=FILTRAGES,
            onglet="image", cout=(("GPU", 1),), se_voit=True),
    Reglage("graph_limite", "GeneralExt", "FPSLimit",
            "Limite d'images par seconde",
            "Ce jeu ne doit pas dépasser 60 images par seconde : au-delà, le diablotin se fige "
            "et certains portraits ne s'ouvrent plus. 30 fait moins chauffer l'ordinateur.",
            choix=tuple(v for v, _ in LIMITES), zero="60 (vitesse normale)", noms_choix=LIMITES,
            onglet="perfs"),
    Reglage("graph_vsync", "DirectX", "ForceVerticalSync",
            "Synchronisation verticale",
            "Cale les images sur la fréquence de l'écran : plus de déchirure horizontale "
            "quand la caméra tourne, contre un peu plus de délai entre la souris et l'image.",
            defaut=True, onglet="perfs"),
)}


def chemin(dossier_exe: Path) -> Path:
    return dossier_exe / NOM


def disponible(conf: Path | None) -> bool:
    """Un `dgVoodoo.conf` à régler, et un système où le traducteur le lira."""
    return sys.platform == "win32" and conf is not None and conf.is_file()


def du_onglet(onglet: str) -> tuple[Reglage, ...]:
    return tuple(r for r in REGLAGES.values() if r.onglet == onglet)


def _motif(cle: str) -> re.Pattern:
    # Le préfixe (clé, alignement, « = » et l'espace qui suit) est gardé tel quel.
    return re.compile(r"^(\s*" + re.escape(cle) + r"\s*=[ \t]*)(.*?)\s*$", re.IGNORECASE)


def _valeur(lignes: list[str], section: str, cle: str) -> str | None:
    bornes = _bornes(lignes, section)
    if bornes is None:
        return None
    motif = _motif(cle)
    for ligne in lignes[bornes[0]:bornes[1]]:
        m = motif.match(ligne)
        if m:
            return m.group(2)
    return None


def _poser(lignes: list[str], section: str, cle: str, valeur: str) -> None:
    bornes = _bornes(lignes, section)
    if bornes is None:
        raise ValueError(f"section [{section}] absente")
    debut, fin = bornes
    motif = _motif(cle)
    for i in range(debut, fin):
        m = motif.match(lignes[i])
        if m:
            lignes[i] = m.group(1) + valeur
            return
    # Clé absente : après la dernière ligne non vide de la section, alignée
    # comme le fichier aligne les siennes.
    j = fin
    while j > debut and not lignes[j - 1].strip():
        j -= 1
    lignes.insert(j, f"{cle:<37}= {valeur}")


def lire(conf: Path, reglage: Reglage) -> Etat:
    """Ce que porte le fichier. Lève OSError s'il est illisible."""
    lignes, _ = _lire(conf)
    brut = _valeur(lignes, reglage.section, reglage.cle)
    if not reglage.choix:
        if brut is None:
            return Etat(reglage.defaut)
        return Etat(brut.strip().lower() == "true")
    v = (brut or reglage.choix[0]).strip().lower()
    return Etat(v, personnalise=v not in reglage.choix)


def chemin_origine(conf: Path) -> Path:
    return conf.with_name(conf.name + SUFFIXE_ORIGINE)


def a_une_origine(conf: Path) -> bool:
    return chemin_origine(conf).is_file()


def ecrire(conf: Path, reglage: Reglage, valeur) -> None:
    """Écrit un réglage. OSError si le fichier ne peut pas l'être, ValueError
    si la valeur n'est pas proposée (jamais plus de 60 images/s, par exemple)."""
    if reglage.choix and valeur not in reglage.choix:
        raise ValueError(f"{reglage.ident} : {valeur!r} non proposé")
    lignes, fin = _lire(conf)
    texte = valeur if reglage.choix else ("true" if valeur else "false")
    _poser(lignes, reglage.section, reglage.cle, texte)
    copie = chemin_origine(conf)
    if not copie.exists():
        try:
            shutil.copy2(conf, copie)
        except OSError:
            log.warning("Réglages graphiques : copie d'origine de %s impossible", conf, exc_info=True)
    _ecrire(conf, lignes, fin)
    log.info("Réglages graphiques : %s = %s dans %s", reglage.cle, texte, conf)


def remettre_origine(conf: Path) -> None:
    """Remet les clés réglables telles que les portait le fichier d'origine."""
    origine, _ = _lire(chemin_origine(conf))
    lignes, fin = _lire(conf)
    for reglage in REGLAGES.values():
        valeur = _valeur(origine, reglage.section, reglage.cle)
        if valeur is not None:
            _poser(lignes, reglage.section, reglage.cle, valeur)
    _ecrire(conf, lignes, fin)
    log.info("Réglages graphiques : réglages d'origine remis dans %s", conf)
