"""Personnages et Bestiaire : les fiches des rubriques des Collections.

Demandés par Ludo le 2026-10-26, option 1 retenue : des fiches de texte (nom,
rôle ou lieu, description), et une image seulement quand le jeu en a une
PROPRE. Les relevés des agents avaient surtout des peaux dépliées et des
visages photographiés (« le bestiaire est horrible ») ; ne restent que les
illustrations du livre de HP1, les icônes d'interface de HP1 à HP3 et les
cartes du folio de HP4. Les autres fiches portent un emblème (côté interface).

`src/data/encyclopedie.json` : les textes sont ceux du launcher, en trois
langues, et les noms les noms officiels. Les images ne sont JAMAIS livrées :
elles se lisent dans la copie du joueur, à l'endroit relevé (paquet Unreal et
nom de texture pour HP1-HP3, position d'une image 0x7B dans un flux de
`data.big` pour HP4). Sans le jeu, la fiche reste du texte.
"""

import json
import logging
import struct
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from src.core import folio_hp4, textures_ue1
from src.core.config import ENCYCLOPEDIE_PATH
from src.core.i18n import TexteTraduit, texte_traduit
from src.core.images_ea import entree_big

log = logging.getLogger(__name__)

PERSONNAGES = "personnages"
BESTIAIRE = "bestiaire"

ImageBgra = tuple[int, int, bytes]       # largeur, hauteur, pixels B V R A


@dataclass(frozen=True)
class ImageJeu:
    fichier: str                          # relatif au dossier du jeu (« Textures/StoryBookTest.utx »)
    nom: str = ""                         # texture d'un paquet Unreal
    bits: int = 8                         # 8 : palette ; 32 : B V R A
    recadrage: tuple[int, int, int, int] | None = None     # x, y, largeur, hauteur
    entree: str = ""                      # entrée de data.big (HP4)
    position: int = 0                     # en-tête de l'image dans cette entrée


@dataclass(frozen=True)
class ModeleJeu:
    fichier: str                          # paquet relatif au dossier du jeu (« System/HarryPotter.u »)
    nom: str                              # le `SkeletalMesh` (« skharryMesh »)


@dataclass(frozen=True)
class Fiche:
    cle: str
    nom: TexteTraduit
    sous_titre: TexteTraduit              # le rôle d'un personnage, le lieu d'une créature
    texte: TexteTraduit
    image: ImageJeu | None
    modele: ModeleJeu | None = None       # son modèle 3D (HP1, HP2)


def _image(brute: object) -> ImageJeu | None:
    if not isinstance(brute, dict) or not isinstance(brute.get("fichier"), str):
        return None
    recadrage = brute.get("recadrage")
    cadre = None
    if isinstance(recadrage, list) and len(recadrage) == 4:
        x, y, w, h = (int(v) for v in recadrage)
        cadre = (x, y, w, h)
    return ImageJeu(brute["fichier"], str(brute.get("nom", "")), int(brute.get("bits", 8)), cadre,
                    str(brute.get("entree", "")), int(brute.get("position", 0)))


def _fiche(brute: dict[str, object], champ: str) -> Fiche | None:
    nom, sous_titre, texte = (texte_traduit(brute.get(k)) for k in ("nom", champ, "texte"))
    if nom is None or sous_titre is None or texte is None or not isinstance(brute.get("cle"), str):
        return None
    modele = brute.get("modele")
    modele_jeu = None
    if isinstance(modele, dict) and isinstance(modele.get("fichier"), str) and isinstance(modele.get("nom"), str):
        modele_jeu = ModeleJeu(modele["fichier"], modele["nom"])
    return Fiche(str(brute["cle"]), nom, sous_titre, texte, _image(brute.get("image")), modele_jeu)


@lru_cache(maxsize=1)
def charger(chemin: Path | None = None) -> dict[str, dict[str, tuple[Fiche, ...]]]:
    """{rubrique: {jeu: fiches}} ; vide si le fichier manque ou ne se lit pas."""
    chemin = chemin or ENCYCLOPEDIE_PATH
    try:
        brut = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("Encyclopédie illisible : %s", chemin, exc_info=True)
        return {}
    sortie: dict[str, dict[str, tuple[Fiche, ...]]] = {}
    for rubrique, champ in ((PERSONNAGES, "role"), (BESTIAIRE, "lieu")):
        par_jeu = brut.get(rubrique) if isinstance(brut, dict) else None
        if not isinstance(par_jeu, dict):
            continue
        sortie[rubrique] = {
            jeu: tuple(f for f in (_fiche(b, champ) for b in fiches if isinstance(b, dict)) if f)
            for jeu, fiches in par_jeu.items() if isinstance(fiches, list)}
    return sortie


def fiches(rubrique: str, jeu: str) -> tuple[Fiche, ...]:
    return charger().get(rubrique, {}).get(jeu, ())


def jeux(rubrique: str) -> tuple[str, ...]:
    return tuple(j for j, f in charger().get(rubrique, {}).items() if f)


# ── Les images, lues dans le jeu installé ──

def _trouver(dossier: Path, relatif: str) -> Path | None:
    """`relatif` sous `dossier`, sans tenir compte de la casse (HP3 écrit
    « textures », HP1 « Textures », et Linux ne pardonne pas)."""
    courant = dossier
    for partie in relatif.split("/"):
        try:
            courant = next(p for p in courant.iterdir() if p.name.lower() == partie.lower())
        except (OSError, StopIteration):
            return None
    return courant


def chemin_image(dossier_exe: Path, image: ImageJeu | ModeleJeu) -> Path | None:
    """Le fichier qui porte l'image ou le modèle : à côté de l'exe (HP4), ou
    depuis la racine du jeu, dossier parent de `System` (HP1-HP3)."""
    return _trouver(dossier_exe, image.fichier) or _trouver(dossier_exe.parent, image.fichier)


def image(dossier_exe: Path, fiche: Fiche) -> ImageBgra | None:
    """L'image de la fiche lue dans le jeu installé (B V R A), recadrée ; None
    sans image, sans le jeu, ou si elle n'est plus là où elle a été relevée."""
    if fiche.image is None:
        return None
    chemin = chemin_image(dossier_exe, fiche.image)
    if chemin is None:
        return None
    try:
        lue = _lire(chemin, fiche.image)
    except (OSError, ValueError, IndexError, struct.error):
        log.warning("Encyclopédie : image de %s illisible", fiche.cle, exc_info=True)
        return None
    if lue is None or fiche.image.recadrage is None:
        return lue
    return recadrer(lue, fiche.image.recadrage)


def _lire(chemin: Path, image_jeu: ImageJeu) -> ImageBgra | None:
    if image_jeu.entree:
        flux = _flux(str(chemin), image_jeu.entree)
        return folio_hp4.image_7b(flux, image_jeu.position) if flux else None
    if image_jeu.bits == 32:
        return textures_ue1.texture_32(chemin, image_jeu.nom)
    tex = textures_ue1.texture(chemin, image_jeu.nom)
    return bgra_de_palette(tex) if tex is not None else None


@lru_cache(maxsize=1)
def _flux(big: str, entree: str) -> bytes:
    return entree_big(Path(big), entree)


def bgra_de_palette(tex: textures_ue1.TexturePaletee) -> ImageBgra:
    """Une texture de 256 couleurs en B V R A ; l'indice 0 transparent si masquée."""
    couleurs = [bytes((b, v, r, 0 if tex.masquee and i == 0 else 255))
                for i, (r, v, b, _a) in enumerate(tex.palette)]
    couleurs += [bytes(4)] * (256 - len(couleurs))
    return tex.largeur, tex.hauteur, b"".join(couleurs[i] for i in tex.indices)


def recadrer(img: ImageBgra, cadre: tuple[int, int, int, int]) -> ImageBgra | None:
    largeur, hauteur, pixels = img
    x, y, w, h = cadre
    w, h = min(w, largeur - x), min(h, hauteur - y)
    if x < 0 or y < 0 or w <= 0 or h <= 0:
        return None
    lignes = (pixels[4 * ((y + k) * largeur + x):4 * ((y + k) * largeur + x + w)] for k in range(h))
    return w, h, b"".join(lignes)
