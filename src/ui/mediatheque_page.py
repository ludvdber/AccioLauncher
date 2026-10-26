"""La page Médiathèque : la Musique et les Cinématiques des jeux, un jeu à la fois.

Maquette « Phonographe d'Accio » validée par Ludo le 2026-10-24 (« c'est
magnifique la page musique »). En haut, le titre, les deux rubriques et les
jeux : un seul choix de jeu pour les deux rubriques (Ludo : « choisir le jeu
en haut, pas retourner dans Musique pour changer »).

Musique : à gauche la platine, compacte (le disque du jeu qui tourne pendant
la lecture, le titre, le crédit du compositeur, les commandes, Enregistrer et
Fond sonore côte à côte, le volume) ; à droite l'avancement (repère à 75 %) et
les morceaux, ouverts avec leur bouton d'écoute ou fermés avec leur seuil.

Cinématiques : la liste et l'écran. Une cinématique qui joue fait taire la
musique (`fond_sonore.CINEMATIQUE`) et la lui rend en s'arrêtant.

**Quitter la page rend le fond sonore** : une écoute lancée ici s'arrête
(Ludo : « en quittant le lecteur, c'est resté la dernière musique et pas le
fond sonore que j'ai mis avant »).

Pas de `setStyleSheet("background: transparent")` nu sur un conteneur : une
règle sans sélecteur vaut pour TOUS ses enfants et l'emportait sur le fond or
du bouton de lecture (invisible, 2026-10-24) et des badges. D'où `#transparent`.

Le modèle est `mediatheque.Mediatheque` : la page ne lit rien elle-même.
"""

import logging
import shutil
from html import escape
from pathlib import Path

from PyQt6.QtCore import QRectF, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QImage, QPainter
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.core import discographie, encyclopedie
from src.core.i18n import tr
from src.ui.composants import ENCRE, ENCRE_DISCRETE, ENCRE_DOUCE, bouton, feuille_de_style, police, surtitre, texte
from src.ui.choix_jeux import espacee, numeros, pastille
from src.ui.disque import Disque
from src.ui.encyclopedie_page import VueEncyclopedie
from src.ui.flow_layout import FlowLayout
from src.ui.fond_sonore import CINEMATIQUE, MULTIMEDIA_DISPONIBLE, QAudioOutput, QMediaPlayer, cle, decouper
from src.ui.fonts import cinzel, cinzel_decorative
from src.ui.icon_button import pixmap_icone
from src.ui.mediatheque import CAPTURES, CINEMATIQUES, MUSIQUE, Mediatheque
from src.ui.theme import accent_qcolor, themed
from src.ui.utils import clear_layout, open_local_path, zone_defilable
from src.ui.video_player import VideoPlayer

log = logging.getLogger(__name__)

_LARGEUR_PLATINE = 340
_DISQUE = 220
_LARGEUR_ECRAN = 560

_STYLE = """
QDialog#mediatheque { background: #070712; }
QWidget#transparent { background: transparent; }
QPushButton#retour {
    background: transparent; border: none; color: #a9a7c4; text-align: left; padding: 4px 2px;
}
QPushButton#retour:hover { color: #f2f2f4; }
QPushButton#rubrique, QPushButton#filtre {
    background: transparent; border: 1px solid rgba(255, 255, 255, 0.14); border-radius: 15px;
    color: #c9c7da; padding: 6px 16px;
}
QPushButton#filtre { border-radius: 13px; padding: 5px 13px; }
QPushButton#rubrique:hover, QPushButton#filtre:hover { color: #f2f2f4; }
QPushButton#rubrique:checked, QPushButton#filtre:checked {
    background: rgba(214, 167, 44, 0.14); border-color: rgba(214, 167, 44, 0.6); color: #f2e6c4;
}
QPushButton#rubrique:focus, QPushButton#filtre:focus { border-color: #d6a72c; }
QFrame#platine { background: #08081a; border: none; border-right: 1px solid rgba(214, 167, 44, 0.12); }
QFrame#carteJeu {
    background: #0d0d1a; border: 1px solid rgba(214, 167, 44, 0.14); border-radius: 10px;
}
QFrame#carteJeu[modele="true"]:hover { border-color: rgba(214, 167, 44, 0.35); }
QFrame#carteJeu[choisie="true"] { border-color: rgba(214, 167, 44, 0.6); }
QFrame#filet { background: rgba(255, 255, 255, 0.06); border: none; }
QFrame#ligne { background: transparent; border: none; border-bottom: 1px solid rgba(255, 255, 255, 0.05); }
QFrame#ligne[courante="true"] { background: rgba(214, 167, 44, 0.10); }
QFrame#ligne:hover { background: rgba(214, 167, 44, 0.05); }
QPushButton#rond {
    background: transparent; border: 1px solid rgba(255, 255, 255, 0.16); border-radius: 19px;
}
QPushButton#rond:hover, QPushButton#rond:focus { border-color: #d6a72c; }
QPushButton#lecture { background: #d6a72c; border: none; border-radius: 25px; }
QPushButton#lecture:hover, QPushButton#lecture:focus { background: #e8bd4a; }
QPushButton#lecture:disabled { background: rgba(214, 167, 44, 0.35); }
QPushButton#petit {
    background: transparent; border: 1px solid rgba(255, 255, 255, 0.14); border-radius: 16px;
}
QPushButton#petit[courante="true"] { border-color: #d6a72c; }
QPushButton#petit:hover, QPushButton#petit:focus { border-color: #d6a72c; }
QPushButton#discret { background: transparent; border: none; border-radius: 16px; }
QPushButton#discret:hover, QPushButton#discret:focus { background: rgba(255, 255, 255, 0.06); }
QPushButton#secondaire:checked {
    color: #f2e6c4; background: rgba(214, 167, 44, 0.14); border-color: rgba(214, 167, 44, 0.6);
}
QPushButton#lien { background: transparent; border: none; color: #d6a72c; text-align: left; padding: 0; }
QPushButton#lien:hover { color: #e8bd4a; }
QLabel#nouveau {
    background: #d6a72c; color: #070712; border-radius: 4px; padding: 1px 7px;
}
QLabel#etiquetteFond {
    color: #d6a72c; border: 1px solid rgba(214, 167, 44, 0.45); border-radius: 4px; padding: 1px 7px;
}
QSlider::groove:horizontal { height: 4px; background: rgba(255, 255, 255, 0.12); border-radius: 2px; }
QSlider::sub-page:horizontal { background: #d6a72c; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; background: #f2e6c4;
}
"""


def _icone(nom: str, taille: int, couleur: QColor | None = None) -> QIcon:
    return QIcon(pixmap_icone(nom, taille, couleur or QColor("#e6e4f0")))


def _transparent(widget: QWidget) -> QWidget:
    widget.setObjectName("transparent")
    return widget


def _filet() -> QFrame:
    f = QFrame()
    f.setObjectName("filet")
    f.setFixedHeight(1)
    return f


def _repolir(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class _Paquets:
    """Bâtit une longue liste par paquets, au fil de la boucle d'événements.

    152 rangées d'un coup figeaient l'ouverture de la page 0,4 s (HP3, mesuré
    le 2026-10-24) : les 30 premières se posent tout de suite, le reste suit
    sans bloquer. Minuteur POSSÉDÉ (règle 102) : un nouveau jeu l'arrête.
    """

    TAILLE = 30

    def __init__(self, parent: QWidget, pile: QVBoxLayout) -> None:
        self._pile = pile
        self._attente: list = []
        self._minuteur = QTimer(parent)
        self._minuteur.setInterval(0)
        self._minuteur.timeout.connect(self._suite)

    def remplir(self, fabriques: list) -> None:
        self._minuteur.stop()
        clear_layout(self._pile)
        self._attente = list(fabriques)
        self._suite()

    def _suite(self) -> None:
        paquet, self._attente = self._attente[:self.TAILLE], self._attente[self.TAILLE:]
        for fabrique in paquet:
            self._pile.addWidget(fabrique())
        if self._attente:
            self._minuteur.start()
        else:
            self._minuteur.stop()
            self._pile.addStretch()


class _Elide(QLabel):
    """Un titre sur une ligne qui s'élide au lieu de se couper (texte entier en bulle)."""

    def __init__(self, contenu: str, px: int, encre: str, italique: bool = False) -> None:
        super().__init__()
        self._plein = contenu
        self.setTextFormat(Qt.TextFormat.PlainText)
        f = police(px)
        f.setItalic(italique)
        self.setFont(f)
        self.setStyleSheet(f"color: {encre}; background: transparent;")
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(40)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().resizeEvent(event)
        court = self.fontMetrics().elidedText(self._plein, Qt.TextElideMode.ElideRight, self.width())
        self.setText(court)
        self.setToolTip(self._plein if court != self._plein else "")


def _texte_seuil(seuil: int) -> str:
    if seuil >= discographie.TOUT_A:
        return tr("S'ouvre à {} %").format(discographie.TOUT_A)
    return tr("S'ouvre vers {} %").format(seuil)


def _nouveaux(n: int) -> str:
    return tr("{} nouveau").format(n) if n == 1 else tr("{} nouveaux").format(n)


def _badge_nouveau() -> QLabel:
    badge = QLabel(tr("Nouveau").upper())
    badge.setObjectName("nouveau")
    badge.setFont(cinzel(7, bold=True))
    return badge


def _cadenas() -> QLabel:
    cadenas = QLabel()
    cadenas.setFixedSize(32, 32)
    cadenas.setAlignment(Qt.AlignmentFlag.AlignCenter)
    cadenas.setPixmap(pixmap_icone("cadenas", 18, QColor("#5d5b72")))
    return cadenas


def _bouton_lire(libelle: str, action) -> QPushButton:
    b = QPushButton()
    b.setObjectName("petit")
    b.setFixedSize(32, 32)
    b.setIcon(_icone("play", 14, accent_qcolor()))
    b.setIconSize(QSize(14, 14))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setAccessibleName(libelle)
    b.clicked.connect(action)
    return b


def _message(contenu: str) -> QLabel:
    return texte(contenu, 15, "#c9c7da", retour=True)


class _Barre(QWidget):
    """L'avancement du jeu, avec le repère des 75 % où tout s'ouvre."""

    def __init__(self) -> None:
        super().__init__()
        self.pct = 0
        self.setFixedHeight(14)

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        y = self.height() / 2 - 3
        p.setBrush(QColor(255, 255, 255, 30))
        p.drawRoundedRect(QRectF(0, y, self.width(), 6), 3, 3)
        p.setBrush(accent_qcolor())
        p.drawRoundedRect(QRectF(0, y, self.width() * self.pct / 100, 6), 3, 3)
        p.setBrush(QColor(242, 238, 226, 150))
        p.drawRect(QRectF(self.width() * discographie.TOUT_A / 100 - 1, 0, 2, self.height()))
        p.end()


class _Jeux(QWidget):
    """Les jeux en pastilles, communs aux deux rubriques ; « 2 nouveaux » sur ceux qui en ont."""

    choisi = pyqtSignal(str)

    def __init__(self, media: Mediatheque) -> None:
        super().__init__()
        _transparent(self)
        self._media = media
        self._boutons: dict[str, QPushButton] = {}
        flux = FlowLayout(self, spacing=8)
        flux.setContentsMargins(0, 0, 0, 0)
        groupe = QButtonGroup(self)
        groupe.setExclusive(True)
        jeux = [g for g in (media.game(j) for j in media.jeux_tous()) if g is not None]
        self._etiquettes = numeros(jeux)
        for game in jeux:
            jeu = game.id
            b = pastille(game, self._etiquettes[jeu])
            b.clicked.connect(lambda _c=False, j=jeu: self.choisi.emit(j))
            groupe.addButton(b)
            flux.addWidget(b)
            self._boutons[jeu] = b
            self.compter(jeu)

    @property
    def ids(self) -> list[str]:
        return list(self._boutons)

    def cocher(self, jeu: str) -> None:
        if jeu in self._boutons:
            self._boutons[jeu].setChecked(True)

    def compter(self, jeu: str) -> None:
        b = self._boutons.get(jeu)
        if b is None:
            return
        n = len(self._media.nouveaux(jeu, MUSIQUE)) + len(self._media.nouveaux(jeu, CINEMATIQUES))
        nom = self._etiquettes.get(jeu, self._media.nom(jeu))
        # Le chiffre seul sur la pastille : « 130 nouveaux » sur chacune faisait
        # passer les jeux sur deux lignes ; le mot est dans l'infobulle.
        b.setText(f"{nom}  ·  {n}" if n else nom)
        infobulle = escape(self._media.nom(jeu))
        b.setToolTip(f"{infobulle} · {escape(_nouveaux(n))}" if n else infobulle)
        b.setAccessibleName(f"{self._media.nom(jeu)}, {_nouveaux(n)}" if n else self._media.nom(jeu))


class _LigneMorceau(QFrame):
    """Un morceau : ouvert (écouter, enregistrer) ou fermé (cadenas et seuil)."""

    def __init__(self, page: _VueMusique, jeu: str, num: int, morceau: discographie.Morceau,
                 ouvert: bool, nouveau: bool) -> None:
        super().__init__()
        self.setObjectName("ligne")
        self.cle = cle(jeu, morceau.fichier)
        self.setMinimumHeight(44)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 3, 8, 3)
        lay.setSpacing(12)
        numero = texte(str(num), 12, ENCRE_DISCRETE)
        numero.setFixedWidth(26)
        numero.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(numero)
        self._ecouter: QPushButton | None = None
        self._fond: QLabel | None = None
        if ouvert:
            self._ecouter = _bouton_lire(tr("Écouter {}").format(morceau.titre),
                                         lambda: page.ecouter(self.cle))
            lay.addWidget(self._ecouter)
            lay.addWidget(_Elide(morceau.titre, 15, ENCRE), stretch=1)
            if nouveau:
                lay.addWidget(_badge_nouveau())
            self._fond = QLabel(tr("Fond sonore"))
            self._fond.setObjectName("etiquetteFond")
            self._fond.setFont(police(12))
            self._fond.hide()
            lay.addWidget(self._fond)
            enregistrer = QPushButton()
            enregistrer.setObjectName("discret")
            enregistrer.setFixedSize(32, 32)
            enregistrer.setIcon(_icone("telechargement", 16, QColor("#a9a7c4")))
            enregistrer.setIconSize(QSize(16, 16))
            enregistrer.setCursor(Qt.CursorShape.PointingHandCursor)
            enregistrer.setToolTip(tr("Enregistrer le morceau"))
            enregistrer.setAccessibleName(tr("Enregistrer {}").format(morceau.titre))
            enregistrer.clicked.connect(lambda: page.enregistrer(self.cle))
            lay.addWidget(enregistrer)
        else:
            lay.addWidget(_cadenas())
            lay.addWidget(_Elide(tr("Morceau à découvrir"), 15, ENCRE_DISCRETE, italique=True), stretch=1)
            lay.addWidget(texte(_texte_seuil(morceau.seuil), 13, ENCRE_DOUCE))

    def marquer(self, courante: bool, fond: bool) -> None:
        if bool(self.property("courante")) != courante:
            self.setProperty("courante", courante)
            _repolir(self)
            if self._ecouter is not None:
                self._ecouter.setProperty("courante", courante)
                _repolir(self._ecouter)
        if self._fond is not None:
            self._fond.setVisible(fond)


class _VueMusique(QWidget):
    """La platine à gauche, l'avancement et les morceaux du jeu choisi à droite."""

    def __init__(self, media: Mediatheque) -> None:
        super().__init__()
        self._media = media
        self._fond = media.fond
        self._jeu = ""
        self._affichee = False
        self._lignes: list[_LigneMorceau] = []
        self._dossier_enregistre = None
        racine = QHBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(0)
        cadre = QFrame()
        cadre.setObjectName("platine")
        cadre.setFixedWidth(_LARGEUR_PLATINE)
        c = QVBoxLayout(cadre)
        c.setContentsMargins(0, 0, 0, 0)
        c.addWidget(zone_defilable(self._platine()))
        racine.addWidget(cadre)
        racine.addWidget(self._liste(), stretch=1)
        # Des méthodes, pas des lambdas : le lecteur vit plus longtemps que la page,
        # et un lambda gardait la page morte branchée (plantage en coupant le son
        # après l'avoir quittée, 2026-10-24). `detacher` coupe aussi, à la fermeture.
        self._fond.change.connect(self._rafraichir)
        self._fond.son_coupe_change.connect(self._sur_son_coupe)

    def _sur_son_coupe(self, _coupe: bool) -> None:
        self._rafraichir()

    def detacher(self) -> None:
        for signal, slot in ((self._fond.change, self._rafraichir),
                             (self._fond.son_coupe_change, self._sur_son_coupe)):
            try:
                signal.disconnect(slot)
            except TypeError:
                pass

    # ── Construction ──

    def _platine(self) -> QWidget:
        page = _transparent(QWidget())
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(0)
        lay.addWidget(surtitre(tr("En cours")))
        lay.addSpacing(12)
        self._disque = Disque(_DISQUE)
        lay.addWidget(self._disque, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(12)
        self._titre = QLabel()
        self._titre.setTextFormat(Qt.TextFormat.PlainText)
        self._titre.setWordWrap(True)
        self._titre.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._titre.setFont(cinzel(13, bold=True))
        self._titre.setStyleSheet(f"color: {ENCRE}; background: transparent;")
        lay.addWidget(self._titre)
        lay.addSpacing(2)
        self._sous_titre = texte("", 13, ENCRE_DOUCE, retour=True)
        self._sous_titre.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self._sous_titre)
        self._credit = texte("", 12, ENCRE_DISCRETE, retour=True)
        self._credit.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self._credit)
        lay.addSpacing(10)

        commandes = QHBoxLayout()
        commandes.setSpacing(10)
        commandes.addStretch()
        self._precedent = self._rond("precedent", tr("Morceau précédent"), lambda: self._sauter(-1))
        commandes.addWidget(self._precedent)
        self._lecture = QPushButton()
        self._lecture.setObjectName("lecture")
        self._lecture.setFixedSize(50, 50)
        self._lecture.setIconSize(QSize(20, 20))
        self._lecture.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lecture.clicked.connect(self._fond.basculer_pause)
        commandes.addWidget(self._lecture)
        self._suivant = self._rond("suivant", tr("Morceau suivant"), lambda: self._sauter(1))
        commandes.addWidget(self._suivant)
        commandes.addStretch()
        lay.addLayout(commandes)
        lay.addSpacing(12)

        # Enregistrer et Fond sonore côte à côte : la platine tenait sur deux écrans.
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._enregistrer = bouton(tr("Enregistrer"))
        self._enregistrer.setAutoDefault(False)
        self._enregistrer.setIcon(_icone("telechargement", 16))
        self._enregistrer.setIconSize(QSize(16, 16))
        self._enregistrer.setToolTip(tr("Enregistrer ce morceau"))
        self._enregistrer.clicked.connect(lambda: self.enregistrer(self._fond.morceau))
        actions.addWidget(self._enregistrer, stretch=1)
        self._bouton_fond = bouton(tr("Fond sonore"))
        self._bouton_fond.setCheckable(True)
        self._bouton_fond.setAutoDefault(False)
        self._bouton_fond.setIcon(_icone("musique", 16))
        self._bouton_fond.setIconSize(QSize(16, 16))
        self._bouton_fond.clicked.connect(self._basculer_fond)
        actions.addWidget(self._bouton_fond, stretch=1)
        lay.addLayout(actions)
        self._confirmation = texte("", 12, ENCRE_DOUCE, retour=True)
        self._confirmation.setContentsMargins(0, 6, 0, 0)
        self._confirmation.hide()
        lay.addWidget(self._confirmation)
        self._ouvrir_dossier = QPushButton(tr("Ouvrir le dossier"))
        self._ouvrir_dossier.setObjectName("lien")
        self._ouvrir_dossier.setFont(police(12))
        self._ouvrir_dossier.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ouvrir_dossier.hide()
        self._ouvrir_dossier.clicked.connect(
            lambda: self._dossier_enregistre is not None and open_local_path(self._dossier_enregistre))
        lay.addWidget(self._ouvrir_dossier, alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addSpacing(12)
        lay.addWidget(_filet())
        lay.addSpacing(10)

        self._fond_texte = texte("", 13, ENCRE_DOUCE, retour=True)
        lay.addWidget(self._fond_texte)
        lay.addSpacing(8)
        volume = QHBoxLayout()
        volume.setSpacing(10)
        icone = QLabel()
        icone.setPixmap(pixmap_icone("volume", 18, QColor("#a9a7c4")))
        volume.addWidget(icone)
        self._volume = QSlider(Qt.Orientation.Horizontal)
        self._volume.setRange(0, 100)
        self._volume.setValue(self._media.fond_volume())
        self._volume.setAccessibleName(tr("Volume de la musique"))
        self._volume.valueChanged.connect(
            lambda v: self._fond.regler_volume(v, enregistrer=not self._volume.isSliderDown()))
        self._volume.sliderReleased.connect(lambda: self._fond.regler_volume(self._volume.value()))
        volume.addWidget(self._volume, stretch=1)
        lay.addLayout(volume)
        lay.addStretch()
        return page

    def _rond(self, icone: str, libelle: str, action) -> QPushButton:
        b = QPushButton()
        b.setObjectName("rond")
        b.setFixedSize(38, 38)
        b.setIcon(_icone(icone, 16))
        b.setIconSize(QSize(16, 16))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setToolTip(libelle)
        b.setAccessibleName(libelle)
        b.clicked.connect(action)
        return b

    def _liste(self) -> QWidget:
        colonne = _transparent(QWidget())
        lay = QVBoxLayout(colonne)
        lay.setContentsMargins(32, 18, 40, 0)
        lay.setSpacing(0)
        self._vide = _message("")
        self._vide.hide()
        lay.addWidget(self._vide)

        self._carte = QFrame()
        self._carte.setObjectName("carteJeu")
        c = QVBoxLayout(self._carte)
        c.setContentsMargins(18, 12, 18, 10)
        c.setSpacing(6)
        haut = QHBoxLayout()
        self._nom_jeu = QLabel()
        self._nom_jeu.setTextFormat(Qt.TextFormat.PlainText)
        self._nom_jeu.setFont(cinzel(11, bold=True))
        self._nom_jeu.setStyleSheet(f"color: {ENCRE}; background: transparent;")
        haut.addWidget(self._nom_jeu, stretch=1)
        self._compte = texte("", 13, ENCRE_DOUCE)
        haut.addWidget(self._compte)
        c.addLayout(haut)
        self._barre = _Barre()
        c.addWidget(self._barre)
        self._bas = _transparent(QWidget())
        bas = QHBoxLayout(self._bas)
        bas.setContentsMargins(0, 0, 0, 0)
        self._avance = texte("", 12, ENCRE_DOUCE)
        bas.addWidget(self._avance, stretch=1)
        bas.addWidget(texte(tr("{} % : tout s'ouvre").format(discographie.TOUT_A), 12, ENCRE_DOUCE))
        c.addWidget(self._bas)
        lay.addWidget(self._carte)
        lay.addSpacing(10)

        self._morceaux = _transparent(QWidget())
        self._pile = QVBoxLayout(self._morceaux)
        self._pile.setContentsMargins(0, 0, 0, 12)
        self._pile.setSpacing(0)
        self._paquets = _Paquets(self, self._pile)
        self._zone = zone_defilable(self._morceaux)
        lay.addWidget(self._zone, stretch=1)
        self._credit_jeu = texte("", 12, ENCRE_DISCRETE, retour=True)
        self._credit_jeu.setContentsMargins(0, 8, 0, 14)
        lay.addWidget(self._credit_jeu)
        self._stretch_vide = QWidget()
        lay.addWidget(self._stretch_vide, stretch=1)
        return colonne

    # ── Le jeu montré ──

    def montrer(self, jeu: str) -> None:
        self._jeu = jeu
        media = self._media
        morceaux = media.morceaux(jeu)
        a_de_la_musique = jeu in {g.id for g in media.jeux(MUSIQUE)}
        for w in (self._carte, self._zone, self._credit_jeu):
            w.setVisible(a_de_la_musique)
        self._vide.setVisible(not a_de_la_musique)
        self._stretch_vide.setVisible(not a_de_la_musique)
        self._lignes = []
        if not a_de_la_musique:
            self._paquets.remplir([])
            self._vide.setText(
                tr("La musique de ce jeu n'est pas encore lue par le launcher.") if jeu
                else tr("Installez L'École des sorciers, La Chambre des secrets ou Le Prisonnier "
                        "d'Azkaban pour écouter leur musique ici."))
            self._rafraichir()
            return
        nouveaux = media.nouveaux(jeu, MUSIQUE)
        avance = media.avance(jeu)
        ouverts = sum(media.ouvert(jeu, m.seuil) for m in morceaux)

        def fabrique(i: int, m: discographie.Morceau):
            def faire() -> QWidget:
                ligne = _LigneMorceau(self, jeu, i, m, media.ouvert(jeu, m.seuil), m.fichier in nouveaux)
                ligne.marquer(ligne.cle == self._fond.morceau, ligne.cle == self._fond.fond)
                self._lignes.append(ligne)
                return ligne
            return faire

        self._paquets.remplir([fabrique(i, m) for i, m in enumerate(morceaux, 1)])
        self._nom_jeu.setText(media.nom(jeu))
        self._compte.setText(tr("{n} morceaux sur {total}").format(n=ouverts, total=len(morceaux)))
        self._barre.pct = avance or 0
        self._barre.update()
        # Un jeu dont tout est ouvert d'office (HP4) n'a pas d'avancement à montrer.
        a_des_seuils = any(m.seuil > 0 for m in morceaux)
        self._barre.setVisible(a_des_seuils)
        self._bas.setVisible(a_des_seuils)
        self._avance.setText(tr("Votre sauvegarde la plus avancée : {} %").format(avance)
                             if avance is not None else tr("Aucune partie lue pour l'instant"))
        credit = media.credit(jeu)
        self._credit_jeu.setText(
            (credit + " · " if credit else "")
            + tr("Harry Potter © Warner Bros. Entertainment Inc. Les morceaux enregistrés "
                 "viennent de votre copie du jeu, pour votre usage personnel."))
        self._marquer_vus()
        self._rafraichir()

    def afficher(self, oui: bool) -> None:
        self._affichee = oui
        self._marquer_vus()

    def _marquer_vus(self) -> None:
        """Vus en les MONTRANT : la marque « Nouveau » reste affichée cette fois-ci.
        La page bâtit ses deux rubriques d'un coup ; celle qu'on ne regarde pas
        ne marque rien."""
        if self._affichee and self._jeu:
            self._media.marquer_vus(self._jeu, MUSIQUE)

    # ── Actions ──

    def ecouter(self, cle_morceau: str) -> None:
        self._fond.ecouter(cle_morceau)

    def _sauter(self, pas: int) -> None:
        courant = decouper(self._fond.morceau)
        jeu = courant[0] if courant is not None else self._jeu
        liste = [cle(jeu, m.fichier) for m in self._media.morceaux(jeu) if self._media.ouvert(jeu, m.seuil)]
        if not liste:
            return
        pos = liste.index(self._fond.morceau) if self._fond.morceau in liste else -pas
        self._fond.ecouter(liste[(pos + pas) % len(liste)])

    def _basculer_fond(self) -> None:
        morceau = self._fond.morceau
        if morceau and morceau == self._fond.fond:
            self._fond.choisir_fond("")
        elif morceau:
            self._fond.choisir_fond(morceau)

    def enregistrer(self, cle_morceau: str) -> None:
        if not cle_morceau:
            return
        chemin = self._media.enregistrer(cle_morceau)
        if chemin is None:
            self._confirmation.setText(tr("Le morceau n'a pas pu être enregistré."))
            self._dossier_enregistre = None
        else:
            self._confirmation.setText(tr("Enregistré dans {}").format(chemin.parent))
            self._dossier_enregistre = chemin.parent
        self._confirmation.show()
        self._ouvrir_dossier.setVisible(chemin is not None)

    # ── État ──

    def _rafraichir(self) -> None:
        fond = self._fond
        morceau = fond.morceau
        decoupe = decouper(morceau)
        joue = fond.en_lecture
        if decoupe is not None:
            jeu = decoupe[0]
            self._disque.poser(jeu, self._media.jaquette(jeu))
            self._titre.setText(fond.titre(morceau))
            etat = (tr("Son coupé") if fond.son_coupe and not fond.ecoute
                    else tr("en boucle") if joue else tr("En pause"))
            self._sous_titre.setText(f"{self._media.nom(jeu)} · {etat}")
            self._credit.setText(self._media.credit(jeu))
        else:
            jeu = self._jeu
            self._disque.poser(jeu, self._media.jaquette(jeu) if jeu else None)
            self._titre.setText(tr("Choisissez un morceau"))
            self._sous_titre.setText(tr("Le bouton à côté de chaque titre le fait jouer."))
            self._credit.setText("")
        self._disque.set_tourne(joue)
        self._lecture.setIcon(_icone("pause" if joue else "play", 20, QColor("#070712")))
        self._lecture.setAccessibleName(tr("Pause") if joue else tr("Lecture"))
        self._lecture.setToolTip(self._lecture.accessibleName())
        actif = decoupe is not None
        for b in (self._lecture, self._precedent, self._suivant, self._enregistrer, self._bouton_fond):
            b.setEnabled(actif)
        est_fond = actif and morceau == fond.fond
        self._bouton_fond.setChecked(est_fond)
        self._bouton_fond.setToolTip(tr("Retirer ce morceau du fond sonore") if est_fond
                                     else tr("Mettre ce morceau en fond sonore du launcher"))
        # Sans fond sonore, rien à dire (un état normal ne s'affiche pas).
        self._fond_texte.setVisible(bool(fond.fond))
        if fond.fond:
            self._fond_texte.setText(tr("Fond sonore du launcher : {}").format(
                f"{fond.titre(fond.fond)} · {fond.fond.split('/')[0].upper()}"))
        for ligne in self._lignes:
            ligne.marquer(ligne.cle == morceau, ligne.cle == fond.fond)


class _Ecran(QWidget):
    """L'image de la cinématique, dans son format, sur fond noir."""

    def __init__(self) -> None:
        super().__init__()
        self._image: QImage | None = None
        self.setMinimumSize(320, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QVBoxLayout(self)
        self._invite = texte(tr("Choisissez une cinématique dans la liste."), 14, ENCRE_DOUCE, retour=True)
        self._invite.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._invite)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().resizeEvent(event)
        self.setFixedHeight(self.width() * 9 // 16)

    def poser(self, image: QImage | None) -> None:
        self._image = image
        self._invite.setVisible(image is None)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt)
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#000000"))
        p.drawRoundedRect(QRectF(self.rect()), 8, 8)
        image = self._image
        if image is not None and not image.isNull():
            echelle = min(self.width() / image.width(), self.height() / image.height())
            larg, haut = image.width() * echelle, image.height() * echelle
            p.drawImage(QRectF((self.width() - larg) / 2, (self.height() - haut) / 2, larg, haut), image)
        p.end()


class _LigneCine(QFrame):
    def __init__(self, page: _VueCinematiques, jeu: str, num: int, titre: str, seuil: int,
                 ouvert: bool, nouveau: bool, fichier: str) -> None:
        super().__init__()
        self.setObjectName("ligne")
        self.fichier = fichier
        self.setMinimumHeight(44)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 3, 8, 3)
        lay.setSpacing(12)
        numero = texte(str(num), 12, ENCRE_DISCRETE)
        numero.setFixedWidth(26)
        numero.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(numero)
        self._voir: QPushButton | None = None
        if ouvert:
            self._voir = _bouton_lire(tr("Regarder {}").format(titre),
                                      lambda: page.jouer(jeu, fichier, titre))
            lay.addWidget(self._voir)
            lay.addWidget(_Elide(titre, 15, ENCRE), stretch=1)
            if nouveau:
                lay.addWidget(_badge_nouveau())
        else:
            lay.addWidget(_cadenas())
            lay.addWidget(_Elide(tr("Cinématique à découvrir"), 15, ENCRE_DISCRETE, italique=True),
                          stretch=1)
            lay.addWidget(texte(_texte_seuil(seuil), 13, ENCRE_DOUCE))

    def marquer(self, courante: bool) -> None:
        if bool(self.property("courante")) != courante:
            self.setProperty("courante", courante)
            _repolir(self)
            if self._voir is not None:
                self._voir.setProperty("courante", courante)
                _repolir(self._voir)


def _minutes(ms: int) -> str:
    """« 1:05 » : une durée de cinématique, en minutes et secondes."""
    minutes, secondes = divmod(max(0, ms) // 1000, 60)
    return f"{minutes}:{secondes:02d}"


def _nom_de_fichier(texte_libre: str) -> str:
    """Un titre de cinématique en nom de fichier sûr partout (Windows et Linux)."""
    nom = "".join("_" if c in '<>:"/\\|?*' or ord(c) < 32 else c for c in texte_libre)
    return nom.strip(" .") or "cinematique"


class _VueCinematiques(QWidget):
    """La liste des cinématiques du jeu choisi à gauche, l'écran à droite.

    Une barre de lecture (Ludo, 2026-10-25 : « comme un vrai lecteur où on peut
    avancer ») : sa longueur est celle du plus long de l'image et de la voix
    (une narration déborde souvent de sa vidéo), et la déplacer déplace les deux.
    """

    def __init__(self, media: Mediatheque) -> None:
        super().__init__()
        self._media = media
        self._jeu = ""
        self._affichee = False
        self._courante = ""
        self._lignes: list[_LigneCine] = []
        self._video = VideoPlayer(self)
        self._video.set_plein_debit(True)
        self._video.video_frame.connect(lambda image: self._ecran.poser(image))
        self._video.playback_ended.connect(self._video_finie)
        self._video.position_changed.connect(self._avancer)
        self._video.duration_changed.connect(self._allonger)
        # La voix de HP4 est un fichier à part : un second lecteur, lancé avec la vidéo.
        self._voix: QMediaPlayer | None = None
        self._voix_sortie: QAudioOutput | None = None
        self._chemin_video: Path | None = None
        self._chemin_voix: Path | None = None
        self._duree_video = 0
        self._duree = 0

        racine = QHBoxLayout(self)
        racine.setContentsMargins(40, 18, 40, 0)
        racine.setSpacing(32)
        colonne = _transparent(QWidget())
        c = QVBoxLayout(colonne)
        c.setContentsMargins(0, 0, 0, 0)
        c.setSpacing(0)
        self._vide = _message("")
        self._vide.hide()
        c.addWidget(self._vide)
        self._liste = _transparent(QWidget())
        self._pile = QVBoxLayout(self._liste)
        self._pile.setContentsMargins(0, 0, 0, 12)
        self._pile.setSpacing(0)
        self._paquets = _Paquets(self, self._pile)
        self._zone = zone_defilable(self._liste)
        c.addWidget(self._zone, stretch=1)
        self._stretch_vide = QWidget()
        c.addWidget(self._stretch_vide, stretch=1)
        racine.addWidget(colonne, stretch=2)

        cote = _transparent(QWidget())
        cote.setMaximumWidth(_LARGEUR_ECRAN)
        d = QVBoxLayout(cote)
        d.setContentsMargins(0, 0, 0, 0)
        d.setSpacing(0)
        self._ecran = _Ecran()
        d.addWidget(self._ecran)
        d.addSpacing(12)
        self._titre = QLabel()
        self._titre.setTextFormat(Qt.TextFormat.PlainText)
        self._titre.setWordWrap(True)
        self._titre.setFont(cinzel(12, bold=True))
        self._titre.setStyleSheet(f"color: {ENCRE}; background: transparent;")
        d.addWidget(self._titre)
        d.addSpacing(4)
        self._note = texte("", 13, ENCRE_DOUCE, retour=True)
        d.addWidget(self._note)
        d.addSpacing(10)
        barre = QHBoxLayout()
        barre.setSpacing(10)
        self._position = QSlider(Qt.Orientation.Horizontal)
        self._position.setRange(0, 0)
        self._position.setAccessibleName(tr("Position dans la cinématique"))
        self._position.setCursor(Qt.CursorShape.PointingHandCursor)
        self._position.sliderMoved.connect(self._montrer_temps)
        self._position.sliderReleased.connect(lambda: self._aller_a(self._position.value()))
        # Un clic ou une flèche (sans glisser) déplace aussi la lecture ; nos
        # propres mises à jour passent signaux bloqués.
        self._position.valueChanged.connect(self._valeur_barre)
        barre.addWidget(self._position, stretch=1)
        self._temps = texte("", 12, ENCRE_DISCRETE)
        self._temps.setMinimumWidth(80)
        self._temps.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        barre.addWidget(self._temps)
        d.addLayout(barre)
        d.addSpacing(10)
        commandes = QHBoxLayout()
        commandes.setSpacing(10)
        self._pause = bouton(tr("Pause"))
        self._pause.setAutoDefault(False)
        self._pause.clicked.connect(self._basculer_pause)
        commandes.addWidget(self._pause)
        self._stop = bouton(tr("Arrêter"))
        self._stop.setAutoDefault(False)
        self._stop.clicked.connect(self.arreter)
        commandes.addWidget(self._stop)
        commandes.addStretch()
        self._enregistrer = bouton(tr("Enregistrer…"))
        self._enregistrer.setAutoDefault(False)
        self._enregistrer.setToolTip(tr("Garder une copie de cette cinématique sur votre ordinateur."))
        self._enregistrer.clicked.connect(self._enregistrer_copie)
        commandes.addWidget(self._enregistrer)
        d.addLayout(commandes)
        d.addStretch()
        racine.addWidget(cote, stretch=3)
        self._etat_commandes()

    def montrer(self, jeu: str) -> None:
        self._jeu = jeu
        media = self._media
        self._lignes = []
        presentes = [c for c in media.cinematiques(jeu) if media.a_la_cinematique(jeu, c.fichier)]
        self._zone.setVisible(bool(presentes))
        self._vide.setVisible(not presentes)
        self._stretch_vide.setVisible(not presentes)
        if not presentes:
            self._paquets.remplir([])
            if not jeu:
                texte_vide = tr("Aucun jeu installé n'a de cinématique à montrer ici pour "
                                "l'instant. Les trois premiers jeux jouent les leurs dans le "
                                "moteur, sans fichier vidéo.")
            elif jeu in ("hp1", "hp2"):
                texte_vide = tr("Ce jeu joue ses cinématiques dans son moteur : il n'a pas de "
                                "fichier vidéo à montrer ici.")
            else:
                texte_vide = tr("Les cinématiques de ce jeu ne sont pas encore lues par le launcher.")
            self._vide.setText(texte_vide)
            return
        nouveaux = media.nouveaux(jeu, CINEMATIQUES)

        def fabrique(num: int, clip):
            def faire() -> QWidget:
                ligne = _LigneCine(self, jeu, num, clip.titre, clip.seuil, media.ouvert(jeu, clip.seuil),
                                   clip.fichier in nouveaux, clip.fichier)
                ligne.marquer(clip.fichier == self._courante)
                self._lignes.append(ligne)
                return ligne
            return faire

        self._paquets.remplir([fabrique(num, clip) for num, clip in enumerate(presentes, 1)])
        self._marquer_vus()

    def afficher(self, oui: bool) -> None:
        self._affichee = oui
        self._marquer_vus()
        if not oui:
            self.arreter()

    def _marquer_vus(self) -> None:
        if self._affichee and self._jeu:
            self._media.marquer_vus(self._jeu, CINEMATIQUES)

    def jouer(self, jeu: str, fichier: str, titre: str) -> None:
        self._arreter_voix()
        chemin = self._media.video(jeu, fichier)
        if chemin is None:
            self._note.setText(tr("Cette cinématique n'a pas pu être lue."))
            return
        # La voix AVANT l'image : celle de HP5 se convertit au premier
        # visionnage, et l'image aurait pris cette avance sur la parole.
        voix = self._media.voix(jeu, fichier)
        fond = self._media.fond
        fond.suspendre(CINEMATIQUE)
        volume = self._media.fond_volume() / 100.0
        self._duree_video = self._duree = 0
        self._position.setRange(0, 0)
        if not self._video.play(str(chemin), muted=fond.son_coupe, volume=volume):
            fond.reprendre(CINEMATIQUE)
            return
        self._chemin_video, self._chemin_voix = chemin, voix
        if voix is not None and MULTIMEDIA_DISPONIBLE:
            self._voix_sortie = QAudioOutput(self)
            self._voix_sortie.setVolume(volume)
            self._voix_sortie.setMuted(fond.son_coupe)
            self._voix = QMediaPlayer(self)
            self._voix.setAudioOutput(self._voix_sortie)
            self._voix.setSource(QUrl.fromLocalFile(str(voix)))
            self._voix.mediaStatusChanged.connect(self._statut_voix)
            self._voix.positionChanged.connect(self._avancer)
            self._voix.durationChanged.connect(self._allonger_voix)
            self._voix.play()
        self._courante = fichier
        self._titre.setText(titre)
        self._note.setText(tr("Le son de cette cinématique est encore en cours de déchiffrement.")
                           if self._media.sans_son(jeu) and voix is None else self._media.nom(jeu))
        for ligne in self._lignes:
            ligne.marquer(ligne.fichier == fichier)
        self._etat_commandes()

    def _basculer_pause(self) -> None:
        if self._video.paused:
            self._video.resume()
            if self._voix is not None:
                self._voix.play()
        else:
            self._video.pause()
            if self._voix is not None:
                self._voix.pause()
        self._etat_commandes()

    # ── Barre de lecture ──

    def _allonger(self, ms: int) -> None:
        self._duree_video = ms
        self._allonger_voix(ms)

    def _allonger_voix(self, ms: int) -> None:
        if ms > self._duree:
            self._duree = ms
            self._position.setRange(0, ms)
            self._position.setPageStep(max(1000, ms // 10))
            self._montrer_temps(self._position.value())

    def _avancer(self, _ms: int) -> None:
        """La plus avancée des deux pistes : quand l'image est finie, la voix continue."""
        if self._position.isSliderDown():
            return
        voix = self._voix.position() if self._voix is not None else 0
        image = self._video.position if self._video.is_playing else 0
        self._position.blockSignals(True)
        self._position.setValue(max(voix, image))
        self._position.blockSignals(False)
        self._montrer_temps(self._position.value())

    def _montrer_temps(self, ms: int) -> None:
        self._temps.setText(f"{_minutes(ms)} / {_minutes(self._duree)}" if self._duree else "")

    def _valeur_barre(self, ms: int) -> None:
        if not self._position.isSliderDown():             # le glisser se pose au relâché
            self._aller_a(ms)

    def _aller_a(self, ms: int) -> None:
        """Les deux pistes à `ms`. Une image déjà finie repart si on revient en arrière."""
        if not self._courante:
            return
        if self._voix is not None:
            self._voix.setPosition(ms)
            if not self._video.paused and self._voix.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self._voix.play()
        if self._video.is_playing:
            if self._duree_video and ms >= self._duree_video:
                self._video.stop()                     # au-delà de l'image : la voix seule
            else:
                self._video.seek(ms)
        elif self._chemin_video is not None and ms < self._duree_video:
            fond = self._media.fond
            pause = self._video.paused
            self._video.play(str(self._chemin_video), muted=fond.son_coupe,
                             volume=self._media.fond_volume() / 100.0, debut_ms=ms)
            if pause:
                self._video.pause()
        self._montrer_temps(ms)

    def _enregistrer_copie(self) -> None:
        """Une copie de la vidéo, et de sa voix quand elle est à part : le même nom,
        deux fichiers côte à côte (la vidéo du jeu n'a pas de piste son)."""
        if self._chemin_video is None or not self._courante:
            return
        base = _nom_de_fichier(f"{self._media.nom(self._jeu)} - {self._titre.text()}")
        dossier = Path.home() / "Videos"
        depart = str((dossier if dossier.is_dir() else Path.home()) / (base + self._chemin_video.suffix))
        cible, _filtre = QFileDialog.getSaveFileName(self, tr("Enregistrer la cinématique"), depart)
        if not cible:
            return
        video = Path(cible)
        if video.suffix.lower() != self._chemin_video.suffix.lower():
            video = video.with_name(video.name + self._chemin_video.suffix)
        copies = [(self._chemin_video, video)]
        if self._chemin_voix is not None:
            copies.append((self._chemin_voix, video.with_suffix(self._chemin_voix.suffix)))
        try:
            for source, arrivee in copies:
                shutil.copyfile(source, arrivee)
        except OSError as exc:
            log.warning("Copie de la cinématique impossible : %s", exc)
            self._note.setText(tr("La cinématique n'a pas pu être enregistrée à cet endroit."))
            return
        if len(copies) == 2:
            self._note.setText(tr("Enregistrée : « {} », et sa voix à côté, « {} ».").format(
                copies[0][1].name, copies[1][1].name))
        else:
            self._note.setText(tr("Enregistrée : « {} ».").format(copies[0][1].name))

    def _video_finie(self) -> None:
        """La narration des transitions de HP5 dure plus que leur image (85 s de
        voix pour 64 s de vidéo sur DL03) : elle finit sa phrase, puis tout s'arrête."""
        if self._voix is not None and self._voix.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            return
        self.arreter()

    def _statut_voix(self, statut) -> None:
        if statut == QMediaPlayer.MediaStatus.EndOfMedia and not self._video.is_playing:
            self.arreter()

    def _arreter_voix(self) -> None:
        if self._voix is not None:
            self._voix.stop()
            self._voix.setSource(QUrl())
            self._voix.deleteLater()
            self._voix = None
        if self._voix_sortie is not None:
            self._voix_sortie.deleteLater()
            self._voix_sortie = None

    def arreter(self) -> None:
        """Fin, bouton Arrêter, rubrique quittée ou page fermée : l'écran se vide, la musique revient."""
        self._video.stop()
        self._arreter_voix()
        self._courante = ""
        self._chemin_video = self._chemin_voix = None
        self._duree_video = self._duree = 0
        self._position.setRange(0, 0)
        self._temps.setText("")
        self._ecran.poser(None)
        self._titre.setText("")
        self._note.setText("")
        for ligne in self._lignes:
            ligne.marquer(False)
        self._media.fond.reprendre(CINEMATIQUE)
        self._etat_commandes()

    def _etat_commandes(self) -> None:
        actif = bool(self._courante)
        self._pause.setEnabled(actif)
        self._stop.setEnabled(actif)
        self._position.setEnabled(actif)
        self._enregistrer.setEnabled(actif)
        self._pause.setText(tr("Reprendre") if actif and self._video.paused else tr("Pause"))


class MediathequePage(QDialog):
    """La Médiathèque, en page : les jeux en haut, Musique et Cinématiques dessous."""

    def __init__(self, media: Mediatheque, rubrique: str = CAPTURES, jeu: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("mediatheque")
        self.setWindowTitle(tr("Collections"))
        self.setMinimumSize(900, 560)
        self.setStyleSheet(themed(_STYLE) + feuille_de_style())
        self._media = media
        racine = QVBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(0)

        entete = _transparent(QWidget())
        e = QVBoxLayout(entete)
        e.setContentsMargins(40, 18, 40, 14)
        e.setSpacing(0)
        retour = QPushButton(tr("Bibliothèque"))
        retour.setObjectName("retour")
        retour.setFont(police(13))
        retour.setIcon(QIcon(pixmap_icone("retour", 16, QColor("#a9a7c4"))))
        retour.setIconSize(QSize(16, 16))
        retour.setCursor(Qt.CursorShape.PointingHandCursor)
        retour.setAutoDefault(False)
        retour.clicked.connect(self.accept)
        e.addWidget(retour, alignment=Qt.AlignmentFlag.AlignLeft)
        e.addSpacing(8)
        e.addWidget(surtitre(tr("Ce que les jeux contiennent")))
        e.addSpacing(4)
        # Les rubriques juste après le titre, comme au Carnet (audit du 2026-10-24).
        ligne = QHBoxLayout()
        ligne.setSpacing(10)
        titre = QLabel(tr("Collections"))
        titre.setFont(cinzel_decorative(22))
        titre.setStyleSheet("color: #f4f2f8; background: transparent;")
        ligne.addWidget(titre, alignment=Qt.AlignmentFlag.AlignVCenter)
        ligne.addSpacing(22)
        self._rubriques: dict[str, QPushButton] = {}
        groupe = QButtonGroup(self)
        groupe.setExclusive(True)
        for cle_rubrique, libelle, icone in ((CAPTURES, tr("Captures"), "appareil"),
                                             (MUSIQUE, tr("Musique"), "musique"),
                                             (CINEMATIQUES, tr("Cinématiques"), "film"),
                                             (encyclopedie.PERSONNAGES, tr("Personnages"), "personnages"),
                                             (encyclopedie.BESTIAIRE, tr("Bestiaire"), "patte")):
            b = QPushButton(libelle)
            b.setObjectName("rubrique")
            b.setCheckable(True)
            b.setAutoDefault(False)
            b.setFont(police(14))
            pictogramme, taille = espacee(pixmap_icone(icone, 18, QColor("#e6e4f0")), QSize(18, 18))
            b.setIcon(pictogramme)
            b.setIconSize(taille)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, r=cle_rubrique: self.rubrique(r))
            groupe.addButton(b)
            ligne.addWidget(b, alignment=Qt.AlignmentFlag.AlignVCenter)
            self._rubriques[cle_rubrique] = b
        ligne.addStretch()
        e.addLayout(ligne)
        e.addSpacing(14)
        self._jeux = _Jeux(media)
        self._jeux.choisi.connect(self.montrer)
        e.addWidget(self._jeux)
        racine.addWidget(entete)
        racine.addWidget(_filet())

        self._pile = QStackedWidget()
        self._musique = _VueMusique(media)
        self._cinematiques = _VueCinematiques(media)
        self._pile.addWidget(self._musique)
        self._pile.addWidget(self._cinematiques)
        # Personnages et Bestiaire (2026-10-26) : bâtis pour le jeu choisi
        # seulement quand on les regarde.
        self._encyclo = {r: VueEncyclopedie(media, r)
                         for r in (encyclopedie.PERSONNAGES, encyclopedie.BESTIAIRE)}
        for vue in self._encyclo.values():
            self._pile.addWidget(vue)
        # Les captures : la Galerie d'avant, bâtie à la première visite (elle
        # décode ses vignettes sur un fil à part).
        self._captures: QDialog | None = None
        racine.addWidget(self._pile, stretch=1)
        if not self._jeux.ids:
            self._musique.montrer("")
            self._cinematiques.montrer("")
        self.rubrique(rubrique if rubrique in self._rubriques else CAPTURES)

        jeux = self._jeux.ids
        if jeu not in jeux:
            courant = decouper(media.fond.morceau)
            premier = next((g.id for g in media.jeux(MUSIQUE if rubrique == CAPTURES else rubrique)), jeux[0] if jeux else "")
            jeu = courant[0] if courant is not None and courant[0] in jeux else premier
        if jeu:
            self.montrer(jeu)

    def montrer(self, jeu: str) -> None:
        self._jeux.cocher(jeu)
        self._musique.montrer(jeu)
        self._cinematiques.montrer(jeu)
        vue = self._encyclo.get(self.rubrique_courante)
        if vue is not None:
            vue.montrer(jeu)
        self._jeux.compter(jeu)

    @property
    def jeu(self) -> str:
        return self._musique._jeu

    def rubrique(self, cle_rubrique: str) -> None:
        self._rubriques[cle_rubrique].setChecked(True)
        musique, captures = cle_rubrique == MUSIQUE, cle_rubrique == CAPTURES
        # La Galerie a ses propres filtres par jeu (« Tous » compris).
        self._jeux.setVisible(not captures)
        if captures:
            self._pile.setCurrentWidget(self._galerie())
        elif cle_rubrique in self._encyclo:
            self._pile.setCurrentWidget(self._encyclo[cle_rubrique])
            if self.jeu:
                self._encyclo[cle_rubrique].montrer(self.jeu)
        else:
            self._pile.setCurrentWidget(self._musique if musique else self._cinematiques)
        self._cinematiques.afficher(cle_rubrique == CINEMATIQUES)
        self._musique.afficher(musique)
        if self.jeu:
            self._jeux.compter(self.jeu)

    def _galerie(self) -> QDialog:
        if self._captures is None:
            from src.ui.galerie_page import GaleriePage
            galerie = GaleriePage(self._media.catalogue(), self, integree=True)
            galerie.setWindowFlags(Qt.WindowType.Widget)
            galerie.setMinimumSize(0, 0)
            galerie.finished.connect(self._galerie_fermee)    # son Échap ferme la page
            self._pile.addWidget(galerie)
            self._captures = galerie
        return self._captures

    def _galerie_fermee(self, resultat: int) -> None:
        self.done(resultat)

    @property
    def rubrique_courante(self) -> str:
        courante = self._pile.currentWidget()
        if courante is self._musique:
            return MUSIQUE
        if isinstance(courante, VueEncyclopedie):
            return courante.rubrique
        return CAPTURES if courante is not None and courante is self._captures else CINEMATIQUES

    def done(self, resultat: int) -> None:
        # La Galerie arrête de décoder ses vignettes (son `done`), sans relancer
        # la fermeture de la page par son signal.
        for vue in self._encyclo.values():
            vue.fermer()
        if self._captures is not None:
            self._captures.finished.disconnect(self._galerie_fermee)
            self._captures.done(resultat)
            self._captures = None
        # La page quittée ne laisse pas une cinématique jouer pour personne, et
        # une écoute lancée ici rend la place au fond sonore choisi.
        self._cinematiques.arreter()
        self._musique.detacher()
        self._media.fond.arreter_ecoute()
        super().done(resultat)
