"""Réglages graphiques de HP3, lus et écrits dans le fichier de son traducteur D3D8.

Demandé par Ludo le 2026-10-07 : « pourquoi ne pas mettre ce paramètre dans
l'engrenage du jeu », puis « les autres paramètres également ». Le déclencheur :
un joueur sur puce Intel UHD dont HP3 s'arrête à chaque lancement sur
« SetRenderTarget failed » en dessinant l'ombre de Harry (`notes/HP3.md` du
correctif). L'hypothèse est l'antialiasing 8x livré en v1.2, imposé jusqu'aux
textures de rendu : sans réglage, la seule issue était d'éditer ce fichier au
Bloc-notes.

Le correctif d'Accio de HP3 (`dinput8.dll`) ne règle pas l'image : elle passe par un traducteur D3D8 → D3D11 livré avec le jeu,
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

Laissé hors du launcher (inventaire du 2026-11-19, `notes/HP3.md` de l'atelier) : ce qui fait
marcher le jeu (sortie, carte simulée, mémoire vidéo, modes d'écran, profondeur, tramage,
`Mipmapping`, `SmoothedDepthSampling`), ce qui ne doit jamais changer (filigrane, Alt+Entrée,
`FPSLimit` au-delà de 60), et ce qu'aucun essai n'a encore vu (`Brightness`, `Color`, `Contrast`,
`PhongShadingWhenPossible`, `Bilinear2DOperations`, `ScalingMode`). Les clés d'image de
`hppoa.ini` (`[D3DDrv.D3DRenderDevice]`, détails de `[WinDrv.WindowsClient]`) sont livrées au
plus haut, et le traducteur force déjà le filtrage et la synchronisation.
"""

import logging
import re
import shutil
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

from src.core.lecture_ini import differe, lire_lignes
from src.core.reglages_correctif import Etat, Prereglage, _bornes, _ecrire, _lire
from src.core.reglages_table import Reglage, ValeurChoix

log = logging.getLogger(__name__)

NOM = "dgVoodoo.conf"
SUFFIXE_ORIGINE = ".origine"

ANTIALIASING = (("off", ""), ("2x", "×2"), ("4x", "×4"), ("8x", "×8"))
FILTRAGES = (("appdriven", ""), ("4", "×4"), ("8", "×8"), ("16", "×16"))
# `max` : la taille de l'écran ; `max_fhd`/`max_qhd` : la plus grande qui tient
# sous 1080p / 1440p (documentation dans le fichier) ; `unforced` : celle
# que demande le jeu.
RESOLUTIONS = (("unforced", ""), ("max_fhd", "Jusqu'à 1080p"), ("max_qhd", "Jusqu'à 1440p"),
               ("max", "Celle de l'écran"))
LIMITES = (("60", ""), ("30", "30"))

REGLAGES: dict[str, Reglage] = {r.ident: r for r in (
    # L'œil (`se_voit`) sur la résolution et l'anticrénelage seulement : posé sur les quatre
    # réglages d'image, il ne distinguait rien (audit UI f118).
    Reglage("graph_resolution", "DirectX", "Resolution",
            "Résolution de rendu",
            "La taille à laquelle l'image est calculée, quelle que soit celle que choisit le "
            "jeu. « Celle de l'écran » donne l'image la plus nette ; « Jusqu'à 1080p » "
            "soulage une carte graphique modeste sur un grand écran.",
            choix=tuple(v for v, _ in RESOLUTIONS), zero="Celle du jeu", noms_choix=RESOLUTIONS,
            onglet="image", cout=(("GPU", 2),), se_voit=True),
    Reglage("graph_antialiasing", "DirectX", "Antialiasing",
            "Anticrénelage",
            "Lisse les bords en escalier des objets. ×8 est livré ; ×4 se voit à peine moins "
            "et coûte moins. Si le jeu s'arrête dès son lancement (« SetRenderTarget "
            "failed »), essayez ×4, puis « Aucun » : certaines puces graphiques, Intel "
            "notamment, refusent le ×8.",
            choix=tuple(v for v, _ in ANTIALIASING), zero="Aucun", noms_choix=ANTIALIASING,
            onglet="image", cout=(("GPU", 3),), se_voit=True),
    Reglage("graph_textures_rendu", "DirectXExt", "RTTexturesForceScaleAndMSAA",
            "Lisser aussi les ombres et reflets",
            "Applique la résolution et l'anticrénelage choisis aux images que le jeu calcule "
            "à part, comme l'ombre de Harry : elles restent fines au lieu de pixeliser. "
            "Éteint, elles gardent leur taille d'origine. À éteindre si le jeu s'arrête "
            "dès son lancement et que baisser l'anticrénelage n'a pas suffi.",
            defaut=True, onglet="image", cout=(("GPU", 1),)),
    Reglage("graph_filtrage", "DirectX", "Filtering",
            "Netteté des sols et des murs",
            "Garde nettes les textures vues de biais, comme le sol au loin. ×16 est livré "
            "et ne coûte presque rien.",
            choix=tuple(v for v, _ in FILTRAGES), zero="Celui du jeu", noms_choix=FILTRAGES,
            onglet="image", cout=(("GPU", 1),)),
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


# Le jeu de 2004, sans traducteur : la taille et le filtrage qu'il demandait, sans anticrénelage, ses
# ombres à leur taille. Sa limite d'images et sa synchronisation dépendaient de la carte.
DU_JEU: dict[str, ValeurChoix | bool] = {
    "graph_resolution": "unforced", "graph_antialiasing": "off", "graph_textures_rendu": False,
    "graph_filtrage": "appdriven",
}

# Les préréglages de la page Image. Maximale = l'installation. Légère : la carte d'un PC portable, et
# les ombres et reflets à leur taille, ce qui a fait cesser l'arrêt au lancement sur une puce Intel UHD
# (2026-10-15, `repli_apres_echec`).
PREREGLAGES: tuple[Prereglage, ...] = (
    ("legere", "Légère",
     "Pour un PC portable ou une puce graphique modeste : image jusqu'à 1080p, contours non lissés.",
     {"graph_resolution": "max_fhd", "graph_antialiasing": "off", "graph_textures_rendu": False,
      "graph_filtrage": "16"}),
    ("equilibree", "Équilibrée",
     "Image à la taille de l'écran, contours lissés un peu moins fort.",
     {"graph_resolution": "max", "graph_antialiasing": "4x", "graph_textures_rendu": True,
      "graph_filtrage": "16"}),
    ("maximale", "Maximale",
     "Tous les effets, tels qu'installés, pour une carte graphique récente.",
     {"graph_resolution": "max", "graph_antialiasing": "8x", "graph_textures_rendu": True,
      "graph_filtrage": "16"}),
)


class MagasinGraphique:
    """Où la page Image lit et écrit ces réglages (`reglages_image.Magasin`)."""

    def __init__(self, conf: Path) -> None:
        self.conf = conf
        # Les lignes que la page vient de lire ou d'écrire, avec (date en ns, taille) du fichier : la
        # question « y a-t-il à remettre ? » qui suit aussitôt ne le relit pas tant qu'il n'a pas bougé.
        # `lecture_ini` ne garde pas un fichier de moins de 2 s, et ce bouton le relisait à l'ouverture
        # de la page et après chaque choix (banc du 2026-11-19).
        self._vu: tuple[tuple[int, int], list[str], str] | None = None
        self._accio: dict[str, object] | None = None

    def _signature(self) -> tuple[int, int]:
        etat = self.conf.stat()
        return etat.st_mtime_ns, etat.st_size

    def lire(self, reglage: Reglage) -> object:
        return lire(self.conf, reglage).valeur

    def lire_tout(self, reglages: Iterable[Reglage]) -> dict[str, object]:
        """Le fichier lu UNE fois : tout juste écrit, il l'était autant de fois que de réglages (sept)."""
        signature = self._signature()       # avant la lecture : un changement entre les deux se verra
        lignes, fin = _lire(self.conf)
        self._vu = (signature, lignes, fin)
        return {r.ident: _etat(lignes, r).valeur for r in reglages}

    def ecrire(self, reglage: Reglage, valeur: object) -> None:
        self.ecrire_tout([(reglage, valeur)])

    def ecrire_tout(self, valeurs: Sequence[tuple[Reglage, object]]) -> dict[str, object]:
        propres: list[tuple[Reglage, str | bool]] = []
        for reglage, valeur in valeurs:
            if not isinstance(valeur, (str, bool)):
                raise ValueError(f"{reglage.ident} : {valeur!r} non proposé")
            propres.append((reglage, valeur))
        self._vu = None
        lignes, fin = _ecrire_lot(self.conf, propres)
        try:
            self._vu = (self._signature(), lignes, fin)
        except OSError:
            pass
        return {r.ident: _etat(lignes, r).valeur for r, _v in propres}

    def accio(self, reglage: Reglage) -> object:
        """Ce que porte le fichier tel qu'installé (sa copie d'origine), sinon le fichier : lu une fois pour
        tous les réglages (sans copie d'origine, l'ouverture de la page relisait le fichier six fois). La
        copie d'origine, posée avant la première retouche, porte ce que portait alors le fichier."""
        if self._accio is None:
            self._accio = {}
            for fichier in (chemin_origine(self.conf), self.conf):
                try:
                    lignes, _ = _lire(fichier)
                except OSError:
                    continue
                self._accio = {r.ident: _etat(lignes, r).valeur for r in REGLAGES.values()}
                break
        return self._accio.get(reglage.ident)

    def jeu(self, reglage: Reglage) -> object:
        return DU_JEU.get(reglage.ident)

    def a_change(self) -> bool:
        if (vu := self._vu) is not None:
            try:
                if self._signature() == vu[0]:
                    origine = chemin_origine(self.conf)
                    return origine.is_file() and lire_lignes(origine) != (vu[1], vu[2])
            except OSError:
                pass
            self._vu = None
        return a_une_origine(self.conf)

    def remettre(self) -> None:
        self._vu = None
        remettre_origine(self.conf)


def chemin(dossier_exe: Path) -> Path:
    return dossier_exe / NOM


def disponible(conf: Path | None) -> bool:
    """Un `dgVoodoo.conf` à régler, et un système où le traducteur le lira."""
    return sys.platform == "win32" and conf is not None and conf.is_file()


def _motif(cle: str) -> re.Pattern[str]:
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
    return _etat(lignes, reglage)


def _etat(lignes: list[str], reglage: Reglage) -> Etat:
    brut = _valeur(lignes, reglage.section, reglage.cle)
    if not reglage.choix:
        if brut is None:
            return Etat(reglage.defaut)
        return Etat(brut.strip().lower() == "true")
    v = (brut or str(reglage.choix[0])).strip().lower()
    return Etat(v, personnalise=v not in reglage.choix)


def chemin_origine(conf: Path) -> Path:
    return conf.with_name(conf.name + SUFFIXE_ORIGINE)


def a_une_origine(conf: Path) -> bool:
    """Une copie d'origine qui diffère du fichier : il y a quelque chose à remettre.

    Depuis le 2026-11-13 l'installation pose la copie d'origine (`reglages_conserves`) :
    sa seule présence ne dit plus que le joueur a changé quelque chose.
    """
    origine = chemin_origine(conf)
    try:
        return differe(conf, origine)
    except OSError:
        return origine.is_file()


def ecrire(conf: Path, reglage: Reglage, valeur: str | bool) -> None:
    """Écrit un réglage. OSError si le fichier ne peut pas l'être, ValueError
    si la valeur n'est pas proposée (jamais plus de 60 images/s, par exemple)."""
    ecrire_tout(conf, [(reglage, valeur)])


def ecrire_tout(conf: Path, valeurs: Sequence[tuple[Reglage, str | bool]]) -> dict[str, object]:
    """Plusieurs réglages en UNE lecture et UNE écriture du fichier, et ce qu'il porte ensuite, par
    identifiant. Un préréglage en écrit quatre : le fichier, tout juste écrit, était relu neuf fois
    (`lecture_ini` ne garde pas un fichier de moins de 2 s ; banc du 2026-11-19). OSError ou
    ValueError (valeur non proposée, section absente) : rien n'est écrit."""
    lignes, _fin = _ecrire_lot(conf, valeurs)
    return {r.ident: _etat(lignes, r).valeur for r, _v in valeurs}


def _ecrire_lot(conf: Path, valeurs: Sequence[tuple[Reglage, str | bool]]) -> tuple[list[str], str]:
    """`ecrire_tout`, qui rend les lignes écrites et leur fin de ligne."""
    lignes, fin = _lire(conf)
    for reglage, valeur in valeurs:
        if reglage.choix and valeur not in reglage.choix:
            raise ValueError(f"{reglage.ident} : {valeur!r} non proposé")
        _poser(lignes, reglage.section, reglage.cle,
               str(valeur) if reglage.choix else ("true" if valeur else "false"))
    copie = chemin_origine(conf)
    if not copie.exists():
        try:
            shutil.copy2(conf, copie)
        except OSError:
            log.warning("Réglages graphiques : copie d'origine de %s impossible", conf, exc_info=True)
    _ecrire(conf, lignes, fin)
    log.info("Réglages graphiques : %s dans %s",
             ", ".join(f"{r.cle} = {v}" for r, v in valeurs), conf)
    return lignes, fin


# Après un arrêt PENDANT le dessin d'une image (`config_cassee.DESSIN`), un cran
# à la fois : l'anticrénelage d'abord (8x → 4x → aucun, ce que l'aide du réglage
# conseille déjà), puis ses effets sur les ombres et reflets. Un cran, et non
# tout d'un coup : le joueur garde la plus belle image que sa puce accepte.
_ANTIALIASING_PLUS_BAS = {"8x": "4x", "4x": "off", "2x": "off"}


def repli_apres_echec(conf: Path, intel: bool = False) -> tuple[Reglage, object, object] | None:
    """Le prochain cran à descendre : (réglage, valeur actuelle, valeur proposée).

    None quand il n'y a plus rien à baisser, ou que le fichier est illisible :
    proposer de réessayer sans rien changer serait promettre pour rien (règle 108).

    `intel` : une puce Intel est présente. Les ombres et reflets passent alors
    EN PREMIER : sur Intel UHD, c'est ce réglage qui a fait cesser le plantage
    au lancement, pas l'anticrénelage (cas signalé, Ludo, 2026-10-15).
    """
    aa = REGLAGES["graph_antialiasing"]
    rendu = REGLAGES["graph_textures_rendu"]
    try:
        if intel and lire(conf, rendu).valeur:
            return rendu, True, False
        actuel = lire(conf, aa).valeur
        if actuel in _ANTIALIASING_PLUS_BAS:
            return aa, actuel, _ANTIALIASING_PLUS_BAS[actuel]
        # Une valeur posée à la main (16x…) : le premier cran proposé.
        if actuel not in ("off", "appdriven"):
            return aa, actuel, "4x"
        if lire(conf, rendu).valeur:
            return rendu, True, False
    except OSError:
        log.warning("Réglages graphiques : %s illisible pour un repli", conf, exc_info=True)
    return None


def remettre_origine(conf: Path) -> None:
    """Remet les clés réglables telles que les portait le fichier d'origine.

    Lève OSError si un des deux fichiers ne peut pas être lu ou écrit, rien
    d'autre : une section retirée du fichier courant est laissée telle quelle
    (`_poser` levait ValueError, qui sortait du slot sans message).
    """
    origine, _ = _lire(chemin_origine(conf))
    lignes, fin = _lire(conf)
    for reglage in REGLAGES.values():
        valeur = _valeur(origine, reglage.section, reglage.cle)
        if valeur is None:
            continue
        try:
            _poser(lignes, reglage.section, reglage.cle, valeur)
        except ValueError:
            log.warning("Réglages graphiques : [%s] absente de %s, %s non remis",
                        reglage.section, conf, reglage.cle)
    _ecrire(conf, lignes, fin)
    log.info("Réglages graphiques : réglages d'origine remis dans %s", conf)
