"""Les vignettes des Personnages et du Bestiaire, gardées sur le disque.

Ouvrir les Personnages relisait et redessinait tout à CHAQUE ouverture : le
modèle 3D de chaque fiche lu dans les archives du jeu (2,2 s de travail pour
les 23 de HP5, 2,7 s pour les 21 de HP6, 3,4 s pour les 12 de HP3), puis une
vignette rendue par modèle, posées une à une pendant que la fenêtre peinait
(Ludo, 2026-11-16 : « plus d'une seconde d'attente c'est trop long […] je
préfère un démarrage long du launcher mais tout le reste fluide »).

Une vignette ne dépend que des fichiers du jeu : elle se fabrique UNE fois et
se garde. `cache/fiches/<jeu>_<rubrique>.png` est une planche, toutes les
vignettes d'une vue dans un seul fichier (une ouverture, pas trente) ; son
texte PNG porte l'empreinte dont elle dépend (`encyclopedie.empreinte` : les
fiches, la date et la taille des fichiers du jeu qu'elles lisent ; plus la
couleur de la maison, que porte le disque de sol) et la case de chaque fiche.
Une empreinte qui a changé jette la planche.

`Vignettes` (un seul objet, tenu par la Médiathèque) :

- au lancement, charge en mémoire les planches de chaque jeu installé et
  fabrique ce qui manque (`preparer`), sur un fil pour la lecture et dans le fil
  de l'interface pour le rendu (la carte graphique), une vignette par tour de
  minuteur. Sans carte graphique (rendu QPainter, des centaines de millisecondes
  par modèle), rien ne se fabrique en fond : seulement pour la vue à l'écran ;
- la page demande `gardees(jeu, rubrique)` : la mémoire, sans disque ; ce qui
  arrive ensuite s'annonce par `changees` ; `preparer(d_abord=True)` fait passer
  la vue ouverte devant le reste ;
- un jeu qui démarre reprend la mémoire (`liberer`), le retour de partie la
  recharge.
"""

import json
import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from PyQt6.QtCore import QBuffer, QIODevice, QObject, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPainter

from src.core import encyclopedie, maillages_ue1
from src.core.ecriture_atomique import ecrire_octets_atomique
from src.ui.modele_3d import Modele3D
from src.ui.theme import accent_qcolor

log = logging.getLogger(__name__)

_VERSION = 1                     # à monter quand le rendu d'une vignette change
# Un modèle se rend à la taille de la carte réduite de la liste, pour un écran à 200 %.
_RENDU, _DPR = QSize(52, 64), 2.0
_IMAGE_MAX = QSize(192, 240)     # une image du jeu : la grande carte, à 200 %
_COTE_TEXTURE = 128              # les textures d'un modèle rendu sur 104 pixels de large
_COLONNES = 8
_TEXTE = "accio"

ModeleLu = tuple[maillages_ue1.Maillage, dict[str, QImage], maillages_ue1.Animation | None]
_ModeleBrut = tuple[maillages_ue1.Maillage, dict[str, encyclopedie.ImageBgra], maillages_ue1.Animation | None]
_Matiere = tuple[encyclopedie.ImageBgra | None, _ModeleBrut | None]


def images(textures: dict[str, encyclopedie.ImageBgra]) -> dict[str, QImage]:
    """Les textures lues par un fil (des octets B V R A) en QImage, dans le fil de l'interface."""
    return {nom: QImage(px, w, h, 4 * w, QImage.Format.Format_ARGB32).copy()
            for nom, (w, h, px) in textures.items()}


def chemin(cache: Path, jeu: str, rubrique: str) -> Path:
    return cache / "fiches" / f"{jeu}_{rubrique}.png"


def lire(planche_png: Path, empreinte: str) -> dict[str, QImage]:
    """Les vignettes de la planche, par clé de fiche ; aucune si elle manque, ne se lit pas ou
    porte une autre empreinte."""
    planche = QImage(str(planche_png))
    if planche.isNull():
        return {}
    try:
        index = json.loads(planche.text(_TEXTE))
    except ValueError:
        return {}
    if not isinstance(index, dict) or index.get("empreinte") != empreinte or not isinstance(index.get("cases"), dict):
        return {}
    sortie: dict[str, QImage] = {}
    for cle, case in index["cases"].items():
        if isinstance(case, list) and len(case) == 4 and all(isinstance(v, int) for v in case):
            cadre = QRect(*case)
            if not cadre.isEmpty() and planche.rect().contains(cadre):
                sortie[cle] = planche.copy(cadre)
    return sortie


def ecrire(planche_png: Path, empreinte: str, vignettes: dict[str, QImage]) -> None:
    """Range les vignettes en une planche, posée d'un seul coup (jamais un PNG à moitié écrit)."""
    if not vignettes:
        return
    largeur = max(v.width() for v in vignettes.values())
    hauteur = max(v.height() for v in vignettes.values())
    colonnes = min(_COLONNES, len(vignettes))
    planche = QImage(colonnes * largeur, -(-len(vignettes) // colonnes) * hauteur,
                     QImage.Format.Format_ARGB32_Premultiplied)
    planche.fill(Qt.GlobalColor.transparent)
    cases: dict[str, list[int]] = {}
    p = QPainter(planche)
    for rang, (cle, vignette) in enumerate(vignettes.items()):
        x, y = (rang % colonnes) * largeur, (rang // colonnes) * hauteur
        p.drawImage(x, y, vignette)
        cases[cle] = [x, y, vignette.width(), vignette.height()]
    p.end()
    planche.setText(_TEXTE, json.dumps({"empreinte": empreinte, "cases": cases}))
    tampon = QBuffer()
    tampon.open(QIODevice.OpenModeFlag.WriteOnly)
    if not planche.save(tampon, "PNG"):
        return
    try:
        planche_png.parent.mkdir(parents=True, exist_ok=True)
        ecrire_octets_atomique(planche_png, bytes(tampon.data()))
    except OSError:
        log.warning("Vignettes des fiches : %s ne s'écrit pas", planche_png, exc_info=True)


def _ouvrir(dossier: Path, fiches: tuple[encyclopedie.Fiche, ...], planche_png: Path, prefixe: str,
            connue: str | None) -> tuple[str, dict[str, QImage] | None] | None:
    """Sur le fil : l'empreinte du moment et, si la mémoire ne la porte pas déjà, la planche lue."""
    relevee = encyclopedie.empreinte(dossier, fiches)
    if relevee is None:
        return None
    empreinte = prefixe + relevee
    return empreinte, None if empreinte == connue else lire(planche_png, empreinte)


def _matiere(dossier: Path, fiche: encyclopedie.Fiche) -> _Matiere:
    """Sur le fil : de quoi faire la vignette d'une fiche, son image si elle en a une qui se lit,
    sinon son modèle."""
    lue = encyclopedie.image(dossier, fiche)
    if lue is not None:
        return lue, None
    return None, maillages_ue1.de_la_fiche(dossier, fiche, _COTE_TEXTURE)


class Vignettes(QObject):
    """Les vignettes de chaque vue (jeu, rubrique) : en mémoire, sur le disque, ou à fabriquer."""

    changees = pyqtSignal(str, str)         # jeu, rubrique : `gardees` a du nouveau

    def __init__(self, dossier_exe: Callable[[str], Path | None], cache: Callable[[], Path],
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._dossier_exe, self._cache = dossier_exe, cache
        self._gardees: dict[tuple[str, str], dict[str, QImage]] = {}
        self._empreintes: dict[tuple[str, str], str] = {}
        self._ratees: set[tuple[str, str, str]] = set()     # ni image ni modèle lisibles : pas deux essais
        self._a_ecrire: set[tuple[str, str]] = set()
        self._file: list[tuple[str, str]] = []
        self._a_l_ecran: set[tuple[str, str]] = set()       # demandées par une page ouverte
        # La vue en tête de file : sa planche en cours de lecture, puis ses fiches en fabrication.
        self._ouverture: Future[tuple[str, dict[str, QImage] | None] | None] | None = None
        self._travail: tuple[Path, tuple[encyclopedie.Fiche, ...]] | None = None
        self._attendues: list[tuple[str, Future[_Matiere]]] = []
        self._peintre: Modele3D | None = None
        self._fil = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vignettes")
        self._minuteur = QTimer(self)
        self._minuteur.setInterval(15)
        self._minuteur.timeout.connect(self._avancer)

    def gardees(self, jeu: str, rubrique: str) -> dict[str, QImage]:
        """Les vignettes en mémoire de cette vue, par clé de fiche."""
        return self._gardees.get((jeu, rubrique), {})

    def en_cours(self, jeu: str, rubrique: str) -> bool:
        return (jeu, rubrique) in self._file

    def preparer(self, jeu: str, rubrique: str, d_abord: bool = False) -> None:
        """Charge la planche de cette vue et fabrique ce qui lui manque. `d_abord` : la vue est à
        l'écran, elle passe devant celle qui se préparait (qui reprendra où elle en était)."""
        vue = (jeu, rubrique)
        if vue in self._file:
            if not d_abord or self._file[0] == vue:
                return
            self._file.remove(vue)
        if d_abord:
            self._suspendre()
            self._file.insert(0, vue)
            self._a_l_ecran.add(vue)
        else:
            self._file.append(vue)
        self._minuteur.start()

    def liberer(self) -> None:
        """Un jeu démarre : la mémoire lui revient. Ce qui n'était pas écrit se refera."""
        self._suspendre()
        self._file.clear()
        self._minuteur.stop()
        self._gardees.clear()
        self._empreintes.clear()
        self._a_ecrire.clear()
        self._a_l_ecran.clear()
        if self._peintre is not None:
            self._peintre.deleteLater()
            self._peintre = None

    def arreter(self) -> None:
        """Le launcher se ferme : plus rien à lire ni à fabriquer."""
        self._minuteur.stop()
        self._fil.shutdown(wait=False, cancel_futures=True)

    def _suspendre(self) -> None:
        if self._ouverture is not None:
            self._ouverture.cancel()
        for _cle, futur in self._attendues:
            futur.cancel()
        self._ouverture, self._travail, self._attendues = None, None, []

    def _avancer(self) -> None:
        if not self._file:
            self._minuteur.stop()
            return
        jeu, rubrique = vue = self._file[0]
        if self._travail is None:
            self._commencer(vue)
        elif self._ouverture is not None:
            if self._ouverture.done():
                self._trier(vue, self._travail)
        elif self._attendues[0][1].done():
            # Une vignette par tour : le rendu d'un modèle prend une dizaine de millisecondes.
            cle, futur = self._attendues.pop(0)
            vignette = self._vignette(futur)
            if vignette is None:
                self._ratees.add((jeu, rubrique, cle))
            else:
                self._gardees.setdefault(vue, {})[cle] = vignette
                self._a_ecrire.add(vue)
                self.changees.emit(jeu, rubrique)
            if not self._attendues:
                self._finir(vue)

    def _commencer(self, vue: tuple[str, str]) -> None:
        jeu, rubrique = vue
        dossier = self._dossier_exe(jeu)
        fiches = tuple(f for f in encyclopedie.fiches(rubrique, jeu) if f.image is not None or f.modele is not None)
        if dossier is None or not fiches:
            self._finir(vue)
            return
        self._travail = (dossier, fiches)
        prefixe = f"{_VERSION}-{accent_qcolor().rgb():08x}-"
        self._ouverture = self._fil.submit(_ouvrir, dossier, fiches, chemin(self._cache(), jeu, rubrique), prefixe,
                                           self._empreintes.get(vue))

    def _trier(self, vue: tuple[str, str], travail: tuple[Path, tuple[encyclopedie.Fiche, ...]]) -> None:
        """La planche est lue : ce qu'elle porte passe en mémoire, le reste part en fabrication."""
        jeu, rubrique = vue
        futur, self._ouverture = self._ouverture, None
        lu = futur.result() if futur is not None and futur.exception() is None else None
        if lu is None:                      # un fichier du jeu vient de changer : une autre fois
            self._finir(vue)
            return
        empreinte, lues = lu
        if lues is not None:
            self._empreintes[vue] = empreinte
            self._gardees[vue] = lues
            self.changees.emit(jeu, rubrique)
        dossier, fiches = travail
        gardees = self._gardees.get(vue, {})
        manquantes = [f for f in fiches if f.cle not in gardees and (jeu, rubrique, f.cle) not in self._ratees]
        if not manquantes or (vue not in self._a_l_ecran and not self._peintre_pret().rendu_par_la_carte()):
            self._finir(vue)
            return
        self._attendues = [(f.cle, self._fil.submit(_matiere, dossier, f)) for f in manquantes]

    def _vignette(self, futur: Future[_Matiere]) -> QImage | None:
        if futur.exception() is not None:
            log.warning("Vignette d'une fiche illisible", exc_info=futur.exception())
            return None
        lue, modele = futur.result()
        if lue is not None:
            largeur, hauteur, pixels = lue
            vignette = QImage(pixels, largeur, hauteur, 4 * largeur, QImage.Format.Format_ARGB32)
            if largeur > _IMAGE_MAX.width() or hauteur > _IMAGE_MAX.height():
                return vignette.scaled(_IMAGE_MAX, Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
            return vignette.copy()
        if modele is None:
            return None
        peintre = self._peintre_pret()
        maillage, textures, animation = modele
        peintre.poser(maillage, images(textures), animation)
        vignette = peintre.rendu(_RENDU, _DPR)
        peintre.poser(None)
        vignette.setDevicePixelRatio(1.0)   # des pixels, rangés tels quels dans la planche
        return vignette

    def _peintre_pret(self) -> Modele3D:
        if self._peintre is None:
            self._peintre = Modele3D()      # jamais montré : il ne fait que rendre
        return self._peintre

    def _finir(self, vue: tuple[str, str]) -> None:
        self._file.remove(vue)
        self._travail = None
        if vue in self._a_ecrire:
            self._a_ecrire.discard(vue)
            self._fil.submit(ecrire, chemin(self._cache(), *vue), self._empreintes[vue], dict(self._gardees[vue]))
        # Une vue sans rien à montrer se dit finie aussi : la page cesse d'attendre.
        self.changees.emit(*vue)
