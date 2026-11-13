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

from PyQt6.QtCore import QObject, QRectF, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QImage, QPainter, QTextOption
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
from src.core.i18n import tr, trn
from src.ui import ecran_video_gpu
from src.ui.composants import (
    ENCRE, ENCRE_DISCRETE, ENCRE_DOUCE, bouton, feuille_de_style, filtre, icone_de_bouton, police, rond,
    lien,
    surtitre, texte,
)
from src.ui.choix_jeux import espacee, numeros, pastille
from src.ui.cinema_plein_ecran import PleinEcran
from src.ui.disque import Disque
from src.ui.encyclopedie_page import EtatVide, VueEncyclopedie
from src.ui.flow_layout import FlowLayout
from src.ui.fond_sonore import CINEMATIQUE, MULTIMEDIA_DISPONIBLE, QAudioOutput, QMediaPlayer, cle, decouper
from src.ui.fonts import cinzel, cinzel_decorative
from src.ui.icon_button import pixmap_icone
from src.ui.mediatheque import CAPTURES, CINEMATIQUES, MUSIQUE, Mediatheque
from src.ui.theme import accent_qcolor, themed
from src.ui.utils import apres_le_fil, clear_layout, open_local_path, zone_defilable
from src.ui.video_player import VideoPlayer

log = logging.getLogger(__name__)

_LARGEUR_PLATINE = 340
_DISQUE = 220
_LARGEUR_ECRAN = 560
_PAS_BARRE_MS = 250                # au plus 4 repeintes par seconde de la barre de lecture

_STYLE = """
QDialog#mediatheque { background: #070712; }
QWidget#transparent { background: transparent; }
QFrame#platine { background: #08081a; border: none; border-right: 1px solid rgba(214, 167, 44, 0.12); }
QFrame#carteJeu {
    background: #0d0d1a; border: 1px solid rgba(214, 167, 44, 0.14); border-radius: 10px;
}
QFrame#carteJeu[modele="true"]:hover { border-color: rgba(214, 167, 44, 0.35); }
QFrame#carteJeu[choisie="true"] { border-color: rgba(214, 167, 44, 0.6); }
QFrame#filet { background: rgba(255, 255, 255, 0.06); border: none; }
QFrame#ligne { background: transparent; border: none; border-bottom: 1px solid rgba(255, 255, 255, 0.05); }
QFrame#ligne[courante="true"] { background: rgba(214, 167, 44, 0.10); }
QFrame#ligne[ouverte="true"]:hover { background: rgba(214, 167, 44, 0.05); }
QPushButton#pli {
    background: transparent; border: none; border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}
QPushButton#pli:hover { background: rgba(214, 167, 44, 0.05); }
QPushButton#lecture { background: #d6a72c; border: none; border-radius: 25px; }
QPushButton#lecture:hover { background: #e8bd4a; }
QPushButton#lecture:disabled { background: rgba(214, 167, 44, 0.35); }
QPushButton#petit {
    background: transparent; border: 1px solid rgba(255, 255, 255, 0.14); border-radius: 16px;
}
QPushButton#petit[courante="true"] { border-color: #d6a72c; }
QPushButton#petit:hover { border-color: #d6a72c; }
QPushButton#discret { background: transparent; border: none; border-radius: 16px; }
QPushButton#discret:hover { background: rgba(255, 255, 255, 0.06); }
QPushButton#secondaire:checked {
    color: #f2e6c4; background: rgba(214, 167, 44, 0.14); border-color: rgba(214, 167, 44, 0.6);
}
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
QSlider::handle:horizontal:disabled { background: #5d5b72; }
"""


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
    """Un titre sur une ligne qui s'élide au lieu de se couper (texte entier en bulle).

    Élidé au MILIEU : la fin distingue souvent deux titres (« …Coupe du monde, début » et
    « …, fin » devenaient tous deux « Le camping de la Coupe du mon… » à 980 px)."""

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
        court = self.fontMetrics().elidedText(self._plein, Qt.TextElideMode.ElideMiddle, self.width())
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


def _icone_lire(courante: bool) -> QIcon:
    """Discrète sur chaque ligne : l'or ne désigne que celle qui joue."""
    return icone_de_bouton("play", 14, accent_qcolor() if courante else QColor("#a9a7c4"))


def _bouton_lire(libelle: str, action) -> QPushButton:
    b = QPushButton()
    b.setObjectName("petit")
    b.setFixedSize(32, 32)
    b.setIcon(_icone_lire(False))
    b.setIconSize(QSize(14, 14))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setAccessibleName(libelle)
    b.clicked.connect(action)
    return b


def _ecrire(libelle: QLabel, contenu: str) -> None:
    """Un libellé vide ne garde pas sa hauteur."""
    libelle.setText(contenu)
    libelle.setVisible(bool(contenu))


def _poids_vgmstream() -> str:
    """« 4,3 Mo » : le poids du zip annoncé avant de le télécharger (même unité que les jeux)."""
    from src.core import vgmstream
    from src.core.i18n import decimal_separator
    mo = f"{vgmstream.TAILLE_ZIP / (1024 * 1024):.1f}".replace(".", decimal_separator())
    return f"{mo} {tr('Mo')}"


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


class _PointNouveau(QWidget):
    """Le point or « du nouveau ici », celui de l'onglet Collections, posé dans
    le coin haut droit d'un bouton. Ludo, 2026-10-31 : « on voit pas où dans
    Collections il y a du nouveau » ; le point de la barre menait à une page
    ouverte sur les Captures, sans rien qui dise quelle rubrique ni quel jeu."""

    _COTE = 8

    def __init__(self, bouton: QWidget) -> None:
        super().__init__(bouton)
        self.setFixedSize(self._COTE, self._COTE)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        bouton.installEventFilter(self)
        self.hide()
        self._placer()

    def _placer(self) -> None:
        bouton = self.parentWidget()
        if bouton is not None:
            self.move(bouton.width() - self._COTE - 5, 4)

    def eventFilter(self, objet, evenement) -> bool:  # noqa: N802 (Qt)
        if evenement.type() == evenement.Type.Resize:
            self._placer()
        return False

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(accent_qcolor())
        p.drawEllipse(QRectF(0.5, 0.5, self._COTE - 1, self._COTE - 1))
        p.end()


class _Jeux(QWidget):
    """Les jeux en pastilles, communs aux rubriques : le point or sur ceux qui ont
    du nouveau dans la rubrique regardée, atténuées si elle n'y a rien."""

    choisi = pyqtSignal(str)

    def __init__(self, media: Mediatheque) -> None:
        super().__init__()
        _transparent(self)
        self._media = media
        self._boutons: dict[str, QPushButton] = {}
        self._points: dict[str, _PointNouveau] = {}
        # Le compte d'un jeu ne parle que de la rubrique ouverte, sinon il
        # annonce ce que la liste ne montre pas. Personnages et Bestiaire n'ont
        # pas de nouveautés : aucun compte (ils gardaient celui de la musique).
        self.rubrique = MUSIQUE
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
            self._points[jeu] = _PointNouveau(b)
            self.compter(jeu)

    @property
    def ids(self) -> list[str]:
        return list(self._boutons)

    def cocher(self, jeu: str) -> None:
        if jeu in self._boutons:
            self._boutons[jeu].setChecked(True)

    def compter_tous(self) -> None:
        for jeu in self._boutons:
            self.compter(jeu)

    def compter(self, jeu: str) -> None:
        b = self._boutons.get(jeu)
        if b is None:
            return
        n = len(self._media.nouveaux(jeu, self.rubrique)) if self.rubrique in (MUSIQUE, CINEMATIQUES) else 0
        self._points[jeu].setVisible(bool(n))
        # Le point or dit qu'il y a du nouveau, l'infobulle combien : un chiffre
        # collé au numéro du jeu se lisait « VII · 2 0 ».
        b.setText(self._etiquettes.get(jeu, self._media.nom(jeu)))
        # <qt> et quote=False, comme la Galerie : « l&#x27;École » s'affichait en clair.
        infobulle = escape(self._media.nom(jeu), quote=False)
        b.setToolTip(f"<qt>{infobulle} · {escape(_nouveaux(n), quote=False)}</qt>" if n
                     else f"<qt>{infobulle}</qt>")
        b.setAccessibleName(f"{self._media.nom(jeu)}, {_nouveaux(n)}" if n else self._media.nom(jeu))
        vide = self._sans_contenu(jeu)
        if b.property("vide") != vide:
            b.setProperty("vide", vide)
            _repolir(b)

    def _sans_contenu(self, jeu: str) -> bool:
        """La rubrique ouverte n'a rien à montrer pour ce jeu."""
        media = self._media
        if self.rubrique == MUSIQUE:
            return not media.morceaux(jeu)
        if self.rubrique == CINEMATIQUES:
            return not any(media.a_la_cinematique(jeu, c.fichier) for c in media.cinematiques(jeu))
        return self.rubrique != CAPTURES and not encyclopedie.fiches(self.rubrique, jeu)


class _LigneMorceau(QFrame):
    """Un morceau : ouvert (écouter, enregistrer) ou fermé (cadenas et seuil)."""

    def __init__(self, page: _VueMusique, jeu: str, num: int, morceau: discographie.Morceau,
                 ouvert: bool, nouveau: bool) -> None:
        super().__init__()
        self.setObjectName("ligne")
        self.cle = cle(jeu, morceau.fichier)
        self.setProperty("ouverte", ouvert)
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
            self.setCursor(Qt.CursorShape.PointingHandCursor)
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
            enregistrer.setIcon(icone_de_bouton("telechargement", 16, QColor("#a9a7c4")))
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

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt)
        """Toute la ligne ouverte s'écoute, comme une fiche se choisit d'un clic."""
        if self._ecouter is not None and event.button() == Qt.MouseButton.LeftButton:
            self._ecouter.click()
            return
        super().mousePressEvent(event)

    def marquer(self, courante: bool, fond: bool) -> None:
        if bool(self.property("courante")) != courante:
            self.setProperty("courante", courante)
            _repolir(self)
            if self._ecouter is not None:
                self._ecouter.setProperty("courante", courante)
                self._ecouter.setIcon(_icone_lire(courante))
                _repolir(self._ecouter)
        if self._fond is not None:
            self._fond.setVisible(fond)


class _PliFermes(QWidget):
    """Les morceaux encore fermés, repliés sous les ouverts.

    126 lignes « Morceau à découvrir » sur 152 noyaient les 26 qu'on peut
    écouter (HP3, constat accepté par Ludo le 2026-11-12) : un seul pli dit
    combien il en reste, et déroule les lignes, avec leurs seuils, pour qui
    veut les voir. Elles se bâtissent à la première ouverture, par paquets.
    """

    def __init__(self, fabriques: list) -> None:
        super().__init__()
        _transparent(self)
        self._fabriques = fabriques
        self._bati = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        libelle = tr("{} à découvrir").format(len(fabriques))
        self.bouton = QPushButton()
        self.bouton.setObjectName("pli")
        self.bouton.setCheckable(True)
        self.bouton.setMinimumHeight(44)
        self.bouton.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bouton.setAccessibleName(libelle)
        rangee = QHBoxLayout(self.bouton)
        rangee.setContentsMargins(8, 3, 8, 3)
        rangee.setSpacing(12)
        rangee.addSpacing(26)               # sous la colonne des numéros
        rangee.addWidget(_cadenas())
        self.libelle = texte(libelle, 15, ENCRE_DOUCE)
        rangee.addWidget(self.libelle, stretch=1)
        self._chevron = QLabel()
        self._chevron.setFixedSize(32, 32)
        self._chevron.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rangee.addWidget(self._chevron)
        for enfant in (self.libelle, self._chevron):
            enfant.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.bouton.toggled.connect(self._basculer)
        lay.addWidget(self.bouton)
        self.corps = _transparent(QWidget())
        pile = QVBoxLayout(self.corps)
        pile.setContentsMargins(0, 0, 0, 0)
        pile.setSpacing(0)
        self._paquets = _Paquets(self, pile)
        self.corps.hide()
        lay.addWidget(self.corps)
        self._poser_chevron(False)

    def _poser_chevron(self, ouvert: bool) -> None:
        self._chevron.setPixmap(pixmap_icone("replier" if ouvert else "deplier", 14, QColor("#a9a7c4")))

    def _basculer(self, ouvert: bool) -> None:
        if ouvert and not self._bati:
            self._bati = True
            self._paquets.remplir(self._fabriques)
        self.corps.setVisible(ouvert)
        self._poser_chevron(ouvert)


class _VueMusique(QWidget):
    """La platine à gauche, l'avancement et les morceaux du jeu choisi à droite."""

    def __init__(self, media: Mediatheque) -> None:
        super().__init__()
        self._media = media
        self._fond = media.fond
        self._jeu = ""
        self._lisible = False          # le jeu affiché a des morceaux qu'on peut lancer
        self._affichee = False
        self._lignes: list[_LigneMorceau] = []
        # Un pli ouvert bâtit ses lignes sur SON minuteur, que `remplir` n'arrête
        # pas : sans ce tour, un jeu remontré pendant ce temps recevait dans
        # `_lignes` des lignes promises à `deleteLater` (`marquer` levait ensuite).
        self._tour = 0
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
        media.vgmstream.progression.connect(self._sur_progression_lecteur)
        media.vgmstream.termine.connect(self._sur_lecteur_pose)

    def _sur_son_coupe(self, _coupe: bool) -> None:
        self._rafraichir()

    # ── vgmstream, téléchargé à la première écoute de HP5 ou HP6 ──

    def _telecharger_lecteur(self) -> None:
        self._bouton_lecteur.setEnabled(False)
        self._media.vgmstream.lancer()

    def _sur_progression_lecteur(self, pct: int) -> None:
        self._bouton_lecteur.setEnabled(False)
        self._bouton_lecteur.setText(tr("Téléchargement… {} %").format(pct))

    def _sur_lecteur_pose(self, ok: bool) -> None:
        if ok:
            self.montrer(self._jeu)
            return
        # Le jeu affiché n'attend pas vgmstream (HP7, HP8) : son texte reste le
        # sien, il n'a pas de bouton pour réessayer (audit du 2026-11-02).
        if self._bouton_lecteur.isHidden():
            return
        self._bouton_lecteur.setEnabled(True)
        self._bouton_lecteur.setText(tr("Réessayer ({})").format(_poids_vgmstream()))
        self._vide.setText(tr("Le téléchargement n'a pas abouti. Vérifiez votre connexion, "
                              "puis réessayez."))

    def detacher(self) -> None:
        for signal, slot in ((self._fond.change, self._rafraichir),
                             (self._fond.son_coupe_change, self._sur_son_coupe),
                             (self._media.vgmstream.progression, self._sur_progression_lecteur),
                             (self._media.vgmstream.termine, self._sur_lecteur_pose)):
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
        self._surtitre = surtitre(tr("En cours"))
        lay.addWidget(self._surtitre)
        lay.addSpacing(12)
        self._disque = Disque(_DISQUE, fond_scene=themed("#08081a"))      # le fond du cadre `#platine`
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
        self._precedent = rond("precedent", tr("Morceau précédent"), lambda: self._sauter(-1))
        commandes.addWidget(self._precedent)
        self._lecture = QPushButton()
        self._lecture.setObjectName("lecture")
        self._lecture.setFixedSize(50, 50)
        self._lecture.setIconSize(QSize(20, 20))
        self._lecture.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lecture.clicked.connect(self._lire)
        commandes.addWidget(self._lecture)
        self._suivant = rond("suivant", tr("Morceau suivant"), lambda: self._sauter(1))
        commandes.addWidget(self._suivant)
        commandes.addStretch()
        lay.addLayout(commandes)
        lay.addSpacing(12)

        # Enregistrer et Fond sonore côte à côte : la platine tenait sur deux écrans.
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._enregistrer = rond("telechargement", tr("Enregistrer ce morceau"),
                                  lambda: self.enregistrer(self._fond.morceau))
        actions.addWidget(self._enregistrer)
        self._bouton_fond = bouton(tr("Fond sonore"))
        self._bouton_fond.setCheckable(True)
        self._bouton_fond.setAutoDefault(False)
        self._bouton_fond.setIcon(icone_de_bouton("musique", 16))
        self._bouton_fond.setIconSize(QSize(16, 16))
        self._bouton_fond.clicked.connect(self._basculer_fond)
        actions.addWidget(self._bouton_fond, stretch=1)
        lay.addLayout(actions)
        self._confirmation = texte("", 12, ENCRE_DOUCE, retour=True)
        self._confirmation.setContentsMargins(0, 6, 0, 0)
        self._confirmation.hide()
        lay.addWidget(self._confirmation)
        self._ouvrir_dossier = lien(tr("Ouvrir le dossier"))
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

    def _liste(self) -> QWidget:
        colonne = _transparent(QWidget())
        lay = QVBoxLayout(colonne)
        lay.setContentsMargins(32, 18, 40, 0)
        lay.setSpacing(0)
        self._bouton_lecteur = bouton("", principal=True)
        self._bouton_lecteur.clicked.connect(self._telecharger_lecteur)
        self._vide = EtatVide("musique", action=self._bouton_lecteur)
        self._bouton_lecteur.hide()
        self._vide.hide()
        lay.addWidget(self._vide, stretch=1)

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
        return colonne

    # ── Le jeu montré ──

    def montrer(self, jeu: str) -> None:
        if jeu != self._jeu:
            self._zone.verticalScrollBar().setValue(0)     # un autre jeu s'ouvre en tête
        self._jeu = jeu
        media = self._media
        morceaux = media.morceaux(jeu)
        a_de_la_musique = jeu in {g.id for g in media.jeux(MUSIQUE)}
        attend = a_de_la_musique and media.attend_vgmstream(jeu)
        # Linux sans `vgmstream-cli` : la liste s'affichait, Lecture ne jouait rien
        # et rien ne disait pourquoi (Bazzite, 2026-11-11).
        manque = a_de_la_musique and media.manque_vgmstream(jeu)
        self._lisible = a_de_la_musique and not attend and not manque
        for w in (self._carte, self._zone, self._credit_jeu):
            w.setVisible(self._lisible)
        self._vide.setVisible(not self._lisible)
        self._bouton_lecteur.setVisible(attend)
        self._lignes = []
        self._tour += 1
        if attend:
            # Un téléchargement à la demande dit son poids (règle du « coché d'avance ») ;
            # celui déjà en cours, ouvert depuis une autre page, garde son bouton éteint.
            self._paquets.remplir([])
            self._vide.setText(tr("La musique de {} se lit avec vgmstream, un petit outil libre "
                                  "à télécharger une seule fois.").format(media.nom(jeu)))
            en_cours = media.vgmstream.en_cours
            self._bouton_lecteur.setEnabled(not en_cours)
            self._bouton_lecteur.setText(tr("Téléchargement…") if en_cours else
                                         tr("Télécharger ({})").format(_poids_vgmstream()))
            self._rafraichir()
            return
        if manque:
            self._paquets.remplir([])
            self._vide.setText(tr("La musique de {} se lit avec vgmstream, un petit outil libre. "
                                  "Installez « vgmstream-cli » sur ce système pour l'écouter.")
                               .format(media.nom(jeu)))
            self._rafraichir()
            return
        if not a_de_la_musique:
            self._paquets.remplir([])
            self._vide.setText(
                tr("Pas encore de musique pour ce jeu.") if jeu
                else tr("Installez l'un des six premiers jeux pour écouter sa musique ici."))
            self._rafraichir()
            return
        nouveaux = media.nouveaux(jeu, MUSIQUE)
        avance = media.avance(jeu)
        ouverts = sum(media.ouvert(jeu, m.seuil) for m in morceaux)

        tour = self._tour

        def fabrique(i: int, m: discographie.Morceau, ouvert: bool):
            def faire() -> QWidget:
                ligne = _LigneMorceau(self, jeu, i, m, ouvert, m.fichier in nouveaux)
                ligne.marquer(ligne.cle == self._fond.morceau, ligne.cle == self._fond.fond)
                if tour == self._tour:
                    self._lignes.append(ligne)
                return ligne
            return faire

        # Les ouverts d'abord, dans leur ordre ; les fermés sous un seul pli. Le
        # numéro suit l'ordre affiché.
        a_ecouter = [m for m in morceaux if media.ouvert(jeu, m.seuil)]
        fermes = [m for m in morceaux if not media.ouvert(jeu, m.seuil)]
        fabriques: list = [fabrique(i, m, True) for i, m in enumerate(a_ecouter, 1)]
        if fermes:
            sous_le_pli = [fabrique(i, m, False) for i, m in enumerate(fermes, len(a_ecouter) + 1)]
            fabriques.append(lambda: _PliFermes(sous_le_pli))
        self._paquets.remplir(fabriques)
        self._nom_jeu.setText(media.nom(jeu))
        self._compte.setText(trn(ouverts, "{n} morceau sur {total}", "{n} morceaux sur {total}")
                             .format(n=ouverts, total=len(morceaux)))
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

    def _lire(self) -> None:
        """Pause ou reprise ; au repos, le premier morceau ouvert du jeu affiché."""
        if decouper(self._fond.morceau) is None:
            self._sauter(1)
        else:
            self._fond.basculer_pause()

    def _ouverts(self, jeu: str) -> list[str]:
        return [cle(jeu, m.fichier) for m in self._media.morceaux(jeu) if self._media.ouvert(jeu, m.seuil)]

    def _sauter(self, pas: int) -> None:
        courant = decouper(self._fond.morceau)
        liste = self._ouverts(courant[0] if courant is not None else self._jeu)
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
            self._credit.setText("")
        self._disque.set_tourne(joue)
        self._lecture.setIcon(icone_de_bouton("pause" if joue else "play", 20, QColor(themed("#070712"))))
        self._lecture.setAccessibleName(tr("Pause") if joue else tr("Lecture"))
        self._lecture.setToolTip(self._lecture.accessibleName())
        actif = decoupe is not None
        # Au repos, le disque suffit : ni « En cours », ni titre.
        for w in (self._surtitre, self._titre, self._sous_titre):
            w.setVisible(actif)
        self._credit.setVisible(bool(self._credit.text()))
        for b in (self._precedent, self._suivant, self._enregistrer, self._bouton_fond):
            b.setEnabled(actif)
        self._lecture.setEnabled(actif or (self._lisible and bool(self._ouverts(self._jeu))))
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
    """L'image de la cinématique, dans son format, sur fond noir. Un
    double-clic la passe en plein écran."""

    double_clic = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._image: QImage | None = None
        # La scène sur la carte graphique, créée à la première cinématique (une
        # `QQuickWidget` compte, et beaucoup de visites n'en lancent aucune).
        self._gpu: ecran_video_gpu.EcranVideoGPU | None = None
        self._gpu_tente = False
        self._sur_gpu = False
        self.setMinimumSize(320, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # Peinte et non posée dans un layout : le `setFixedHeight` de `resizeEvent`
        # ne relançait pas sa disposition, et elle restait 68 px trop haut.
        self._invite = tr("Choisissez une cinématique dans la liste.")

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().resizeEvent(event)
        self.setFixedHeight(self.width() * 9 // 16)
        if self._gpu is not None:
            self._gpu.setGeometry(self.rect())

    def sortie_gpu(self) -> QObject | None:
        """Le `VideoOutput` de l'écran, ou None : le chemin QPainter."""
        if not self._gpu_tente:
            self._gpu_tente = True
            # Les coins arrondis sur la couleur de la page (`QDialog#mediatheque`).
            self._gpu = ecran_video_gpu.creer(self, coin=8, fond=QColor(themed("#070712")))
            if self._gpu is not None:
                self._gpu.setGeometry(self.rect())
                self._gpu.hide()
        return self._gpu.sortie_video() if self._gpu is not None else None

    def debut_gpu(self) -> None:
        """Une lecture part vers la scène : `poser` ne sera plus appelé pour ses images."""
        if self._gpu is not None:
            self._sur_gpu = True
            self._gpu.show()

    @property
    def sur_gpu(self) -> bool:
        return self._sur_gpu

    @property
    def invite_visible(self) -> bool:
        return self._image is None and not self._sur_gpu

    def poser(self, image: QImage | None) -> None:
        self._image = image
        if image is None and self._gpu is not None:
            self._sur_gpu = False
            self._gpu.vider()
            self._gpu.hide()
        self.update()

    @property
    def image(self) -> QImage | None:
        return self._image

    def mouseDoubleClickEvent(self, _event) -> None:  # noqa: N802 (Qt)
        if self._image is not None or self._sur_gpu:
            self.double_clic.emit()

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
        if self.invite_visible:
            p.setFont(police(14))
            p.setPen(QColor(ENCRE_DOUCE))
            option = QTextOption(Qt.AlignmentFlag.AlignCenter)
            option.setWrapMode(QTextOption.WrapMode.WordWrap)
            p.drawText(QRectF(self.rect()).adjusted(24, 0, -24, 0), self._invite, option)
        p.end()


class _LigneCine(QFrame):
    def __init__(self, page: _VueCinematiques, jeu: str, num: int, titre: str, seuil: int,
                 ouvert: bool, nouveau: bool, fichier: str) -> None:
        super().__init__()
        self.setObjectName("ligne")
        self.fichier = fichier
        self.setProperty("ouverte", ouvert)
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
            self.setCursor(Qt.CursorShape.PointingHandCursor)
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

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt)
        if self._voir is not None and event.button() == Qt.MouseButton.LeftButton:
            self._voir.click()
            return
        super().mousePressEvent(event)

    def marquer(self, courante: bool) -> None:
        if bool(self.property("courante")) != courante:
            self.setProperty("courante", courante)
            _repolir(self)
            if self._voir is not None:
                self._voir.setProperty("courante", courante)
                self._voir.setIcon(_icone_lire(courante))
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
        self._copie_en_cours = False
        self._jeu = ""
        self._jeu_video = ""        # le jeu de la cinématique lancée (on peut changer de jeu pendant)
        self._affichee = False
        self._courante = ""
        self._lignes: list[_LigneCine] = []
        self._video = VideoPlayer(self)
        self._video.set_plein_debit(True)
        self._video.set_garder_image(True)           # `_Ecran.poser(None)` la retire
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
        self._plein_ecran: PleinEcran | None = None
        # Mise en pause par la fenêtre réduite, pas par l'utilisateur : seule celle-là
        # reprend d'elle-même au retour (voir `set_reduite`).
        self._fenetre_reduite = False
        self._pause_reduite = False
        # Le haut-parleur de la barre du bas vaut aussi pendant la lecture.
        media.fond.son_coupe_change.connect(self._sur_son_coupe)

        racine = QHBoxLayout(self)
        racine.setContentsMargins(40, 18, 40, 0)
        racine.setSpacing(32)
        colonne = _transparent(QWidget())
        c = QVBoxLayout(colonne)
        c.setContentsMargins(0, 0, 0, 0)
        c.setSpacing(0)
        self._vide = EtatVide("film")
        self._vide.hide()
        c.addWidget(self._vide, stretch=1)
        self._liste = _transparent(QWidget())
        self._pile = QVBoxLayout(self._liste)
        self._pile.setContentsMargins(0, 0, 0, 12)
        self._pile.setSpacing(0)
        self._paquets = _Paquets(self, self._pile)
        self._zone = zone_defilable(self._liste)
        c.addWidget(self._zone, stretch=1)
        racine.addWidget(colonne, stretch=2)

        cote = self._cote = _transparent(QWidget())
        cote.setMaximumWidth(_LARGEUR_ECRAN)
        d = QVBoxLayout(cote)
        d.setContentsMargins(0, 0, 0, 0)
        d.setSpacing(0)
        self._ecran = _Ecran()
        self._ecran.double_clic.connect(self.plein_ecran)
        d.addWidget(self._ecran)
        d.addSpacing(12)
        self._titre = QLabel()
        self._titre.setTextFormat(Qt.TextFormat.PlainText)
        self._titre.setWordWrap(True)
        self._titre.setFont(cinzel(12, bold=True))
        self._titre.setStyleSheet(f"color: {ENCRE}; background: transparent;")
        d.addWidget(self._titre)
        self._titre.hide()
        self._note = texte("", 13, ENCRE_DOUCE, retour=True)
        self._note.setContentsMargins(0, 4, 0, 0)
        d.addWidget(self._note)
        self._note.hide()
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
        self._temps.hide()
        d.addSpacing(10)
        commandes = QHBoxLayout()
        commandes.setSpacing(10)
        self._pause = rond("pause", tr("Pause"), self._basculer_pause)
        commandes.addWidget(self._pause)
        self._stop = rond("arret", tr("Arrêter"), self.arreter)
        commandes.addWidget(self._stop)
        self._plein = rond("plein_ecran", tr("Plein écran"), self.plein_ecran,
                            bulle=f'{tr("Plein écran")} · {tr("Échap pour revenir")}')
        commandes.addWidget(self._plein)
        commandes.addStretch()
        self._enregistrer = rond("telechargement", tr("Enregistrer la cinématique"), self._enregistrer_copie,
                                  bulle=tr("Garder une copie de cette cinématique sur votre ordinateur."))
        commandes.addWidget(self._enregistrer)
        d.addLayout(commandes)
        d.addStretch()
        racine.addWidget(cote, stretch=3)
        self._etat_commandes()

    def montrer(self, jeu: str) -> None:
        if jeu != self._jeu:
            self._zone.verticalScrollBar().setValue(0)     # un autre jeu s'ouvre en tête
        self._jeu = jeu
        media = self._media
        self._lignes = []
        presentes = [c for c in media.cinematiques(jeu) if media.a_la_cinematique(jeu, c.fichier)]
        self._zone.setVisible(bool(presentes))
        self._vide.setVisible(not presentes)
        self._cote.setVisible(bool(presentes))
        if not presentes:
            self._paquets.remplir([])
            if self._courante:                 # l'écran se cache : pas de voix sans image
                self.arreter()
            if not jeu:
                texte_vide = tr("Aucun jeu installé n'a de cinématique à montrer ici pour "
                                "l'instant. Les deux premiers jeux jouent les leurs dans le "
                                "moteur, sans fichier vidéo.")
            elif jeu in ("hp1", "hp2"):
                texte_vide = tr("Ce jeu joue ses cinématiques dans son moteur : il n'a pas de "
                                "fichier vidéo à montrer ici.")
            else:
                texte_vide = tr("Pas encore de cinématique pour ce jeu.")
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
            _ecrire(self._note, tr("Cette cinématique n'a pas pu être lue."))
            return
        self._jeu_video = jeu
        # La voix AVANT l'image : celle de HP5 se convertit au premier
        # visionnage, et l'image aurait pris cette avance sur la parole.
        voix = self._media.voix(jeu, fichier)
        fond = self._media.fond
        # Lancer une cinématique demande le son, comme une écoute : le son coupé
        # du launcher la rendait muette (Ludo, 2026-10-27).
        fond.suspendre(CINEMATIQUE)
        fond.rendre_le_son()
        volume = self._media.fond_volume() / 100.0
        self._duree_video = self._duree = 0
        self._position.setRange(0, 0)
        self._pause_reduite = False
        # La fenêtre plein écran reste ouverte si on revient choisir ici (Alt+Tab) :
        # les images continuent d'y aller.
        if self._plein_ecran is None:
            self._video.set_sortie(self._ecran.sortie_gpu())
        if not self._video.play(str(chemin), muted=fond.son_coupe, volume=volume):
            fond.reprendre(CINEMATIQUE)
            return
        self._ecran.debut_gpu()
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
        _ecrire(self._titre, titre)
        if voix is None and self._media.attend_vgmstream(jeu):
            # HP5, HP6 : le son est là, c'est vgmstream qui manque (1.3.1).
            note = tr("Le son de cette cinématique se lit avec vgmstream : téléchargez-le une fois "
                      "depuis la Musique de ce jeu.")
        elif voix is None and self._media.manque_vgmstream(jeu):
            note = tr("Le son de cette cinématique se lit avec vgmstream : installez "
                      "« vgmstream-cli » sur ce système.")
        elif voix is None and self._media.sans_son(jeu):
            note = tr("Le son de cette cinématique est encore en cours de déchiffrement.")
        else:
            note = self._media.nom(jeu)
        _ecrire(self._note, note)
        for ligne in self._lignes:
            ligne.marquer(ligne.fichier == fichier)
        self._etat_commandes()

    def _sur_son_coupe(self, coupe: bool) -> None:
        self._video.set_muted(coupe)
        if self._voix_sortie is not None:
            self._voix_sortie.setMuted(coupe)

    def detacher(self) -> None:
        try:
            self._media.fond.son_coupe_change.disconnect(self._sur_son_coupe)
        except TypeError:
            pass

    def plein_ecran(self) -> None:
        """La cinématique en cours sur tout l'écran ; le lecteur reste celui-ci."""
        if not self._courante or self._plein_ecran is not None:
            return
        plein = PleinEcran(self._ecran.image, gpu=self._ecran.sur_gpu)
        self._video.video_frame.connect(plein.poser)
        if self._ecran.sur_gpu:
            sortie = plein.sortie_video()
            if sortie is None:                 # la scène a refusé : ses images, peintes
                plein.poser(self._video.image_courante())
            self._video.set_sortie(sortie)
        plein.pause_demandee.connect(self._basculer_pause)
        plein.saut_demande.connect(lambda ms: self._aller_a(max(0, self._position.value() + ms)))
        plein.fermee.connect(self._plein_ecran_ferme)
        self._plein_ecran = plein
        plein.ouvrir(self.window())

    def _plein_ecran_ferme(self) -> None:
        plein, self._plein_ecran = self._plein_ecran, None
        if plein is not None:
            try:
                self._video.video_frame.disconnect(plein.poser)
            except TypeError:
                pass
        if self._ecran.sur_gpu:
            self._video.set_sortie(self._ecran.sortie_gpu())
        fenetre = self.window()
        if fenetre is not None:
            fenetre.activateWindow()
        self._suivre_reduction()

    def set_reduite(self, oui: bool) -> None:
        """Fenêtre réduite ou cachée : rien ne se voit, inutile de décoder (la fiche
        fait de même). La pause porte sur les deux pistes, et ne reprend au retour
        que si c'est elle qui l'a posée. Sans effet tant que le plein écran montre
        la cinématique : c'est une autre fenêtre."""
        self._fenetre_reduite = oui
        self._suivre_reduction()

    def _suivre_reduction(self) -> None:
        cachee = self._fenetre_reduite and self._plein_ecran is None
        if cachee and self._courante and not self._en_pause():
            self._basculer_pause()
            self._pause_reduite = True
        elif not cachee and self._pause_reduite:
            self._pause_reduite = False
            if self._en_pause():
                self._basculer_pause()

    def _en_pause(self) -> bool:
        """L'image finie, le lecteur vidéo est libéré : c'est la voix qui dit
        l'état. Sans elle, la reprise ne revenait jamais (grand audit du 2026-11-02)."""
        if self._video.is_playing or self._voix is None:
            return self._video.paused
        return self._voix.playbackState() == QMediaPlayer.PlaybackState.PausedState

    def _basculer_pause(self) -> None:
        if self._en_pause():
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
        valeur = max(voix, image)
        # Au plus 4 repeintes par seconde au lieu d'une par `positionChanged` des deux
        # pistes. Un pas se mesure en temps DE LA VIDÉO, donc un saut (dix secondes en
        # plein écran) passe tout de suite. Pas saccadé : sur la barre de 560 px au
        # plus, une cinématique de 2 min avance de 1,2 px par quart de seconde ;
        # au-delà, le pas suit la durée d'un pixel, jamais plus d'une seconde (le temps
        # affiché).
        pas = min(1000, max(_PAS_BARRE_MS, self._duree // max(1, self._position.width())))
        if abs(valeur - self._position.value()) < pas:
            return
        self._position.blockSignals(True)
        self._position.setValue(valeur)
        self._position.blockSignals(False)
        self._montrer_temps(self._position.value())

    def _montrer_temps(self, ms: int) -> None:
        _ecrire(self._temps, f"{_minutes(ms)} / {_minutes(self._duree)}" if self._duree else "")

    def _valeur_barre(self, ms: int) -> None:
        if not self._position.isSliderDown():             # le glisser se pose au relâché
            self._aller_a(ms)

    def _aller_a(self, ms: int) -> None:
        """Les deux pistes à `ms`. Une image déjà finie repart si on revient en arrière."""
        if not self._courante:
            return
        en_pause = self._en_pause()   # image finie, seule la voix sait qu'on est en pause
        if self._voix is not None:
            self._voix.setPosition(ms)
            if not en_pause and self._voix.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self._voix.play()
        if self._video.is_playing:
            if self._duree_video and ms >= self._duree_video:
                if self._voix is None:                 # rien ne finirait : ni image, ni voix pour prendre le relais
                    self.arreter()
                    return
                self._video.stop()                     # au-delà de l'image : la voix seule
            else:
                self._video.seek(ms)
        elif self._chemin_video is not None and ms < self._duree_video:
            fond = self._media.fond
            pause = en_pause
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
        base = _nom_de_fichier(f"{self._media.nom(self._jeu_video)} - {self._titre.text()}")
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
        # Sur un fil à part : une cinématique de HP8 pèse jusqu'à 329 Mo, et la
        # copie figeait la fenêtre jusqu'au bout (grand audit du 2026-11-02).
        self._copie_en_cours = True
        self._etat_commandes()
        _ecrire(self._note, tr("Enregistrement de la cinématique…"))

        def copier() -> list[str] | None:
            try:
                for source, arrivee in copies:
                    shutil.copyfile(source, arrivee)
            except OSError as exc:
                log.warning("Copie de la cinématique impossible : %s", exc)
                return None
            return [arrivee.name for _source, arrivee in copies]
        apres_le_fil(self, copier, self._poser_copie, "cinematique-copie")

    def _poser_copie(self, noms: object) -> None:
        self._copie_en_cours = False
        self._etat_commandes()
        if not isinstance(noms, list):
            _ecrire(self._note, tr("La cinématique n'a pas pu être enregistrée à cet endroit."))
        elif len(noms) == 2:
            _ecrire(self._note, tr("Enregistrée : « {} », et sa voix à côté, « {} ».").format(*noms))
        else:
            _ecrire(self._note, tr("Enregistrée : « {} ».").format(noms[0]))

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
            self._voix.setSource(QUrl())                  # arrête aussi (règle 135)
            self._voix.deleteLater()
            self._voix = None
        if self._voix_sortie is not None:
            self._voix_sortie.deleteLater()
            self._voix_sortie = None

    def arreter(self) -> None:
        """Fin, bouton Arrêter, rubrique quittée ou page fermée : l'écran se vide, la musique revient."""
        if self._plein_ecran is not None:
            self._plein_ecran.close()
        self._pause_reduite = False
        self._video.stop()
        self._arreter_voix()
        self._courante = ""
        self._chemin_video = self._chemin_voix = None
        self._duree_video = self._duree = 0
        self._position.setRange(0, 0)
        _ecrire(self._temps, "")
        self._ecran.poser(None)
        _ecrire(self._titre, "")
        _ecrire(self._note, "")
        for ligne in self._lignes:
            ligne.marquer(False)
        self._media.fond.reprendre(CINEMATIQUE)
        self._etat_commandes()

    def _etat_commandes(self) -> None:
        actif = bool(self._courante)
        self._pause.setEnabled(actif)
        self._stop.setEnabled(actif)
        self._plein.setEnabled(actif)
        self._position.setEnabled(actif)
        self._enregistrer.setEnabled(actif and not self._copie_en_cours)
        en_pause = actif and self._en_pause()
        libelle = tr("Reprendre") if en_pause else tr("Pause")
        self._pause.setIcon(icone_de_bouton("play" if en_pause else "pause", 16))
        self._pause.setToolTip(libelle)
        self._pause.setAccessibleName(libelle)


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
        # Pas de « ← Bibliothèque » : l'onglet du haut le dit déjà, et Échap
        # ferme la page (Ludo, 2026-10-27 : « retire le bibliothèque répété »).
        e.addWidget(surtitre(tr("Ce que les jeux contiennent")))
        e.addSpacing(4)
        # Les rubriques juste après le titre, comme au Carnet (audit du 2026-10-24).
        ligne = QHBoxLayout()
        ligne.setSpacing(10)
        titre = QLabel(tr("Collections"))
        titre.setFont(cinzel_decorative(22))
        titre.setStyleSheet("color: #f4f2f8; background: transparent;")
        # Le titre garde sa largeur, les rubriques passent à la ligne : sous 1 040 px, on lisait
        # « COLLECTIO », coupé net contre « Captures » (audit UI, 2026-11-13).
        titre.setMinimumWidth(titre.sizeHint().width())
        ligne.addWidget(titre, alignment=Qt.AlignmentFlag.AlignVCenter)
        ligne.addSpacing(22)
        rubriques = _transparent(QWidget())
        flux_rubriques = FlowLayout(rubriques, spacing=10)
        self._rubriques: dict[str, QPushButton] = {}
        groupe = QButtonGroup(self)
        groupe.setExclusive(True)
        for cle_rubrique, libelle, icone in ((CAPTURES, tr("Captures"), "appareil"),
                                             (MUSIQUE, tr("Musique"), "musique"),
                                             (CINEMATIQUES, tr("Cinématiques"), "film"),
                                             (encyclopedie.PERSONNAGES, tr("Personnages"), "personnages"),
                                             (encyclopedie.BESTIAIRE, tr("Bestiaire"), "patte")):
            b = filtre(libelle, grand=True)
            pictogramme, taille = espacee(pixmap_icone(icone, 18, QColor("#e6e4f0")), QSize(18, 18))
            b.setIcon(pictogramme)
            b.setIconSize(taille)
            b.clicked.connect(lambda _c=False, r=cle_rubrique: self.rubrique(r))
            groupe.addButton(b)
            flux_rubriques.addWidget(b)
            self._rubriques[cle_rubrique] = b
        self._points = {r: _PointNouveau(self._rubriques[r]) for r in (MUSIQUE, CINEMATIQUES)}
        ligne.addWidget(rubriques, stretch=1)
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
            # Toutes les rubriques disent qu'il faut un jeu : Personnages et Bestiaire
            # restaient des pages noires (audit UI, 2026-11-13).
            self._musique.montrer("")
            self._cinematiques.montrer("")
            for vue in self._encyclo.values():
                vue.montrer("")
        self.rubrique(rubrique if rubrique in self._rubriques else CAPTURES)

        jeux = self._jeux.ids
        if jeu not in jeux:
            courant = decouper(media.fond.morceau)
            premier = next((g.id for g in media.jeux(MUSIQUE if rubrique == CAPTURES else rubrique)), jeux[0] if jeux else "")
            jeu = courant[0] if courant is not None and courant[0] in jeux else premier
        if jeu:
            self.montrer(jeu)
        media.vus_changes.connect(self._rafraichir_points)
        self._rafraichir_points()

    def _rafraichir_points(self) -> None:
        """Le point or sur chaque rubrique qui a du nouveau, tous jeux confondus,
        et sur chaque jeu qui en a dans la rubrique ouverte."""
        for rubrique, point in self._points.items():
            point.setVisible(self._media.a_des_nouveautes((rubrique,)))
        self._jeux.compter_tous()

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

    def set_reduite(self, oui: bool) -> None:
        self._cinematiques.set_reduite(oui)

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
        self._jeux.rubrique = cle_rubrique
        self._cinematiques.afficher(cle_rubrique == CINEMATIQUES)
        self._musique.afficher(musique)
        self._jeux.compter_tous()

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
        self._cinematiques.detacher()
        self._musique.detacher()
        self._media.fond.arreter_ecoute()
        super().done(resultat)
