"""La page Médiathèque : la Musique et les Cinématiques des jeux, un jeu à la fois.

Maquette « Phonographe d'Accio » validée par Ludo le 2026-10-24 (« c'est
magnifique la page musique »). À gauche, la platine : le disque du jeu qui
tourne pendant la lecture, le titre, le crédit du compositeur, les commandes,
« Enregistrer ce morceau » et le fond sonore du launcher. À droite, les jeux,
l'avancement (repère à 75 %) et les morceaux : ouverts avec leur bouton
d'écoute, ou fermés avec le seuil qui les ouvre, titre caché.

Les cinématiques ont leur rubrique dans la même page (Ludo : « un menu pour
les deux, on n'a pas assez de place »). Une cinématique qui joue fait taire la
musique (`fond_sonore.CINEMATIQUE`) et la lui rend en s'arrêtant.

Le modèle est `mediatheque.Mediatheque` : la page ne lit rien elle-même.
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QImage, QPainter
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
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

from src.core import discographie
from src.core.i18n import tr
from src.ui.composants import ENCRE, ENCRE_DISCRETE, ENCRE_DOUCE, bouton, feuille_de_style, police, surtitre, texte
from src.ui.disque import Disque
from src.ui.flow_layout import FlowLayout
from src.ui.fond_sonore import CINEMATIQUE, cle, decouper
from src.ui.fonts import cinzel, cinzel_decorative
from src.ui.icon_button import pixmap_icone
from src.ui.mediatheque import CINEMATIQUES, MUSIQUE, Mediatheque
from src.ui.theme import accent_qcolor, themed
from src.ui.utils import open_local_path, zone_defilable
from src.ui.video_player import VideoPlayer

_LARGEUR_PLATINE = 360
_DISQUE = 260
_LARGEUR_ECRAN = 560

_STYLE = """
QDialog#mediatheque { background: #070712; }
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
QFrame#filet { background: rgba(255, 255, 255, 0.06); border: none; }
QFrame#ligne { background: transparent; border: none; border-bottom: 1px solid rgba(255, 255, 255, 0.05); }
QFrame#ligne[courante="true"] { background: rgba(214, 167, 44, 0.10); }
QFrame#ligne:hover { background: rgba(214, 167, 44, 0.05); }
QPushButton#rond {
    background: transparent; border: 1px solid rgba(255, 255, 255, 0.16); border-radius: 21px;
}
QPushButton#rond:hover, QPushButton#rond:focus { border-color: #d6a72c; }
QPushButton#lecture { background: #d6a72c; border: none; border-radius: 28px; }
QPushButton#lecture:hover, QPushButton#lecture:focus { background: #e8bd4a; }
QPushButton#petit {
    background: transparent; border: 1px solid rgba(255, 255, 255, 0.14); border-radius: 16px;
}
QPushButton#petit[courante="true"] { border-color: #d6a72c; }
QPushButton#petit:hover, QPushButton#petit:focus { border-color: #d6a72c; }
QPushButton#discret { background: transparent; border: none; border-radius: 16px; }
QPushButton#discret:hover, QPushButton#discret:focus { background: rgba(255, 255, 255, 0.06); }
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


def _filet() -> QFrame:
    f = QFrame()
    f.setObjectName("filet")
    f.setFixedHeight(1)
    return f


def _repolir(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


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
    """Les jeux d'une rubrique, en pastilles ; « 2 nouveaux » sur ceux qui en ont."""

    choisi = pyqtSignal(str)

    def __init__(self, media: Mediatheque, rubrique: str) -> None:
        super().__init__()
        self._media = media
        self._rubrique = rubrique
        self._boutons: dict[str, QPushButton] = {}
        flux = FlowLayout(self, spacing=8)
        flux.setContentsMargins(0, 0, 0, 0)
        groupe = QButtonGroup(self)
        groupe.setExclusive(True)
        for game in media.jeux(rubrique):
            b = QPushButton()
            b.setObjectName("filtre")
            b.setCheckable(True)
            b.setAutoDefault(False)
            b.setFont(police(13))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, j=game.id: self.choisi.emit(j))
            groupe.addButton(b)
            flux.addWidget(b)
            self._boutons[game.id] = b
            self.compter(game.id)

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
        n = len(self._media.nouveaux(jeu, self._rubrique))
        nom = self._media.nom(jeu)
        b.setText(f"{nom}  ·  {_nouveaux(n)}" if n else nom)


class _LigneMorceau(QFrame):
    """Un morceau : ouvert (écouter, enregistrer) ou fermé (cadenas et seuil)."""

    def __init__(self, page: _VueMusique, jeu: str, num: int, morceau: discographie.Morceau,
                 ouvert: bool, nouveau: bool) -> None:
        super().__init__()
        self.setObjectName("ligne")
        self.cle = cle(jeu, morceau.fichier)
        self.setMinimumHeight(46)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(12)
        numero = texte(str(num), 12, ENCRE_DISCRETE)
        numero.setFixedWidth(26)
        numero.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(numero)
        self._ecouter: QPushButton | None = None
        self._fond: QLabel | None = None
        if ouvert:
            self._ecouter = QPushButton()
            self._ecouter.setObjectName("petit")
            self._ecouter.setFixedSize(32, 32)
            self._ecouter.setIcon(_icone("play", 14, accent_qcolor()))
            self._ecouter.setIconSize(QSize(14, 14))
            self._ecouter.setCursor(Qt.CursorShape.PointingHandCursor)
            self._ecouter.setAccessibleName(tr("Écouter {}").format(morceau.titre))
            self._ecouter.clicked.connect(lambda: page.ecouter(self.cle))
            lay.addWidget(self._ecouter)
            lay.addWidget(_Elide(morceau.titre, 15, ENCRE), stretch=1)
            if nouveau:
                badge = QLabel(tr("Nouveau").upper())
                badge.setObjectName("nouveau")
                badge.setFont(cinzel(7, bold=True))
                lay.addWidget(badge)
            self._fond = QLabel(tr("Fond sonore"))
            self._fond.setObjectName("etiquetteFond")
            self._fond.setFont(police(12))
            lay.addWidget(self._fond)
            enregistrer = QPushButton()
            enregistrer.setObjectName("discret")
            enregistrer.setFixedSize(32, 32)
            enregistrer.setIcon(_icone("telechargement", 16, QColor("#a9a7c4")))
            enregistrer.setIconSize(QSize(16, 16))
            enregistrer.setCursor(Qt.CursorShape.PointingHandCursor)
            nom = tr("Enregistrer {}").format(morceau.titre)
            enregistrer.setToolTip(tr("Enregistrer le morceau"))
            enregistrer.setAccessibleName(nom)
            enregistrer.clicked.connect(lambda: page.enregistrer(self.cle))
            lay.addWidget(enregistrer)
        else:
            cadenas = QLabel()
            cadenas.setFixedSize(32, 32)
            cadenas.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cadenas.setPixmap(pixmap_icone("cadenas", 18, QColor("#5d5b72")))
            lay.addWidget(cadenas)
            lay.addWidget(_Elide(tr("Morceau à découvrir"), 15, ENCRE_DISCRETE, italique=True), stretch=1)
            lay.addWidget(texte(_texte_seuil(morceau.seuil), 13, ENCRE_DOUCE))

    def marquer(self, courante: bool, fond: bool) -> None:
        if self.property("courante") != courante:
            self.setProperty("courante", courante)
            _repolir(self)
            if self._ecouter is not None:
                self._ecouter.setProperty("courante", courante)
                _repolir(self._ecouter)
        if self._fond is not None:
            self._fond.setVisible(fond)


class _VueMusique(QWidget):
    """La platine à gauche, les jeux et leurs morceaux à droite."""

    def __init__(self, media: Mediatheque, jeu: str) -> None:
        super().__init__()
        self._media = media
        self._fond = media.fond
        self._jeu = ""
        self._affichee = False
        self._lignes: list[_LigneMorceau] = []
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
        self._fond.change.connect(self._rafraichir)
        self._fond.son_coupe_change.connect(lambda _c: self._rafraichir())
        jeux = self._pastilles.ids
        depart = decouper(self._fond.morceau)
        if jeu not in jeux:
            jeu = depart[0] if depart is not None and depart[0] in jeux else (jeux[0] if jeux else "")
        if jeu:
            self.montrer(jeu)
        self._rafraichir()

    # ── Construction ──

    def _platine(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(0)
        lay.addWidget(surtitre(tr("En cours")))
        lay.addSpacing(16)
        self._disque = Disque(_DISQUE)
        lay.addWidget(self._disque, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(18)
        self._titre = QLabel()
        self._titre.setTextFormat(Qt.TextFormat.PlainText)
        self._titre.setWordWrap(True)
        self._titre.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._titre.setFont(cinzel(13, bold=True))
        self._titre.setStyleSheet(f"color: {ENCRE}; background: transparent;")
        lay.addWidget(self._titre)
        lay.addSpacing(4)
        self._sous_titre = texte("", 13, ENCRE_DOUCE, retour=True)
        self._sous_titre.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self._sous_titre)
        lay.addSpacing(2)
        self._credit = texte("", 12, ENCRE_DISCRETE, retour=True)
        self._credit.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self._credit)
        lay.addSpacing(16)

        commandes = QHBoxLayout()
        commandes.setSpacing(14)
        commandes.addStretch()
        self._precedent = self._rond("precedent", tr("Morceau précédent"), lambda: self._sauter(-1))
        commandes.addWidget(self._precedent)
        self._lecture = QPushButton()
        self._lecture.setObjectName("lecture")
        self._lecture.setFixedSize(56, 56)
        self._lecture.setIconSize(QSize(22, 22))
        self._lecture.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lecture.clicked.connect(self._fond.basculer_pause)
        commandes.addWidget(self._lecture)
        self._suivant = self._rond("suivant", tr("Morceau suivant"), lambda: self._sauter(1))
        commandes.addWidget(self._suivant)
        commandes.addStretch()
        lay.addLayout(commandes)
        lay.addSpacing(16)

        self._enregistrer = bouton(tr("Enregistrer ce morceau"))
        self._enregistrer.setAutoDefault(False)
        self._enregistrer.setIcon(_icone("telechargement", 16))
        self._enregistrer.setIconSize(QSize(16, 16))
        self._enregistrer.clicked.connect(lambda: self.enregistrer(self._fond.morceau))
        lay.addWidget(self._enregistrer)
        lay.addSpacing(6)
        self._confirmation = texte("", 12, ENCRE_DOUCE, retour=True)
        self._confirmation.hide()
        lay.addWidget(self._confirmation)
        self._ouvrir_dossier = QPushButton(tr("Ouvrir le dossier"))
        self._ouvrir_dossier.setObjectName("lien")
        self._ouvrir_dossier.setFont(police(12))
        self._ouvrir_dossier.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ouvrir_dossier.hide()
        lay.addWidget(self._ouvrir_dossier, alignment=Qt.AlignmentFlag.AlignLeft)
        self._dossier_enregistre = None
        self._ouvrir_dossier.clicked.connect(
            lambda: self._dossier_enregistre is not None and open_local_path(self._dossier_enregistre))
        lay.addSpacing(18)
        lay.addWidget(_filet())
        lay.addSpacing(16)

        lay.addWidget(surtitre(tr("Fond sonore du launcher")))
        lay.addSpacing(6)
        self._fond_texte = texte("", 14, ENCRE, retour=True)
        lay.addWidget(self._fond_texte)
        lay.addSpacing(10)
        self._bouton_fond = bouton("", principal=True)
        self._bouton_fond.setAutoDefault(False)
        self._bouton_fond.clicked.connect(self._basculer_fond)
        lay.addWidget(self._bouton_fond)
        lay.addSpacing(18)

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
        b.setFixedSize(42, 42)
        b.setIcon(_icone(icone, 18))
        b.setIconSize(QSize(18, 18))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setToolTip(libelle)
        b.setAccessibleName(libelle)
        b.clicked.connect(action)
        return b

    def _liste(self) -> QWidget:
        colonne = QWidget()
        colonne.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(colonne)
        lay.setContentsMargins(32, 24, 40, 0)
        lay.setSpacing(0)
        self._pastilles = _Jeux(self._media, MUSIQUE)
        self._pastilles.choisi.connect(self.montrer)
        lay.addWidget(self._pastilles)
        lay.addSpacing(16)
        if not self._pastilles.ids:
            lay.addWidget(texte(tr("Installez L'École des sorciers, La Chambre des secrets ou "
                                   "Le Prisonnier d'Azkaban pour écouter leur musique ici."),
                                15, "#c9c7da", retour=True))
            lay.addStretch()
            return colonne

        carte = QFrame()
        carte.setObjectName("carteJeu")
        c = QVBoxLayout(carte)
        c.setContentsMargins(18, 14, 18, 12)
        c.setSpacing(8)
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
        bas = QHBoxLayout()
        self._avance = texte("", 12, ENCRE_DOUCE)
        bas.addWidget(self._avance, stretch=1)
        bas.addWidget(texte(tr("{} % : tout s'ouvre").format(discographie.TOUT_A), 12, ENCRE_DOUCE))
        c.addLayout(bas)
        lay.addWidget(carte)
        lay.addSpacing(12)

        self._morceaux = QWidget()
        self._morceaux.setStyleSheet("background: transparent;")
        self._pile = QVBoxLayout(self._morceaux)
        self._pile.setContentsMargins(0, 0, 0, 12)
        self._pile.setSpacing(0)
        lay.addWidget(zone_defilable(self._morceaux), stretch=1)
        self._credit_jeu = texte("", 12, ENCRE_DISCRETE, retour=True)
        self._credit_jeu.setContentsMargins(0, 8, 0, 14)
        lay.addWidget(self._credit_jeu)
        return colonne

    # ── Le jeu montré ──

    def montrer(self, jeu: str) -> None:
        self._jeu = jeu
        self._pastilles.cocher(jeu)
        media = self._media
        morceaux = media.morceaux(jeu)
        nouveaux = media.nouveaux(jeu, MUSIQUE)
        avance = media.avance(jeu)
        while self._pile.count():
            item = self._pile.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._lignes = []
        ouverts = 0
        for i, m in enumerate(morceaux, 1):
            ouvert = media.ouvert(jeu, m.seuil)
            ouverts += ouvert
            ligne = _LigneMorceau(self, jeu, i, m, ouvert, m.fichier in nouveaux)
            self._pile.addWidget(ligne)
            self._lignes.append(ligne)
        self._pile.addStretch()
        game_nom = media.nom(jeu)
        self._nom_jeu.setText(game_nom)
        self._compte.setText(tr("{n} morceaux sur {total}").format(n=ouverts, total=len(morceaux)))
        self._barre.pct = avance or 0
        self._barre.update()
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
            self._pastilles.compter(self._jeu)

    # ── Actions ──

    def ecouter(self, cle_morceau: str) -> None:
        self._fond.ecouter(cle_morceau)

    def _ouverts_du_jeu(self, jeu: str) -> list[str]:
        return [cle(jeu, m.fichier) for m in self._media.morceaux(jeu) if self._media.ouvert(jeu, m.seuil)]

    def _sauter(self, pas: int) -> None:
        courant = decouper(self._fond.morceau)
        jeu = courant[0] if courant is not None else self._jeu
        liste = self._ouverts_du_jeu(jeu)
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
        if decoupe is not None:
            jeu = decoupe[0]
            self._disque.poser(jeu, self._media.jaquette(jeu))
            self._titre.setText(fond.titre(morceau))
            etat = (tr("Son coupé") if fond.son_coupe and not fond.ecoute
                    else tr("En pause") if fond.en_pause or not fond.en_lecture else tr("en boucle"))
            self._sous_titre.setText(f"{self._media.nom(jeu)} · {etat}")
            self._credit.setText(self._media.credit(jeu))
        else:
            jeu = self._jeu
            self._disque.poser(jeu, self._media.jaquette(jeu) if jeu else None)
            self._titre.setText(tr("Choisissez un morceau"))
            self._sous_titre.setText(tr("Le bouton à côté de chaque titre le fait jouer."))
            self._credit.setText("")
        self._disque.set_tourne(fond.en_lecture)
        joue = fond.en_lecture
        self._lecture.setIcon(_icone("pause" if joue else "play", 22, QColor("#070712")))
        self._lecture.setAccessibleName(tr("Pause") if joue else tr("Lecture"))
        self._lecture.setToolTip(self._lecture.accessibleName())
        actif = decoupe is not None
        for b in (self._lecture, self._precedent, self._suivant, self._enregistrer, self._bouton_fond):
            b.setEnabled(actif)
        est_fond = actif and morceau == fond.fond
        self._fond_texte.setText(
            f"{fond.titre(fond.fond)} · {fond.fond.split('/')[0].upper()}" if fond.fond else tr("Aucun"))
        self._bouton_fond.setText(tr("Retirer du fond") if est_fond else tr("Mettre en fond sonore"))
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
        self.setMinimumHeight(46)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(12)
        numero = texte(str(num), 12, ENCRE_DISCRETE)
        numero.setFixedWidth(26)
        numero.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(numero)
        self._voir: QPushButton | None = None
        if ouvert:
            self._voir = QPushButton()
            self._voir.setObjectName("petit")
            self._voir.setFixedSize(32, 32)
            self._voir.setIcon(_icone("play", 14, accent_qcolor()))
            self._voir.setIconSize(QSize(14, 14))
            self._voir.setCursor(Qt.CursorShape.PointingHandCursor)
            self._voir.setAccessibleName(tr("Regarder {}").format(titre))
            self._voir.clicked.connect(lambda: page.jouer(jeu, fichier, titre))
            lay.addWidget(self._voir)
            lay.addWidget(_Elide(titre, 15, ENCRE), stretch=1)
            if nouveau:
                badge = QLabel(tr("Nouveau").upper())
                badge.setObjectName("nouveau")
                badge.setFont(cinzel(7, bold=True))
                lay.addWidget(badge)
        else:
            cadenas = QLabel()
            cadenas.setFixedSize(32, 32)
            cadenas.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cadenas.setPixmap(pixmap_icone("cadenas", 18, QColor("#5d5b72")))
            lay.addWidget(cadenas)
            lay.addWidget(_Elide(tr("Cinématique à découvrir"), 15, ENCRE_DISCRETE, italique=True),
                          stretch=1)
            lay.addWidget(texte(_texte_seuil(seuil), 13, ENCRE_DOUCE))

    def marquer(self, courante: bool) -> None:
        if self.property("courante") != courante:
            self.setProperty("courante", courante)
            _repolir(self)
            if self._voir is not None:
                self._voir.setProperty("courante", courante)
                _repolir(self._voir)


class _VueCinematiques(QWidget):
    """La liste des cinématiques à gauche, l'écran à droite."""

    def __init__(self, media: Mediatheque, jeu: str) -> None:
        super().__init__()
        self._media = media
        self._jeu = ""
        self._affichee = False
        self._courante = ""
        self._lignes: list[_LigneCine] = []
        self._video = VideoPlayer(self)
        self._video.set_plein_debit(True)
        self._video.video_frame.connect(lambda image: self._ecran.poser(image))
        self._video.playback_ended.connect(self.arreter)

        racine = QHBoxLayout(self)
        racine.setContentsMargins(40, 0, 40, 0)
        racine.setSpacing(32)
        colonne = QWidget()
        colonne.setStyleSheet("background: transparent;")
        c = QVBoxLayout(colonne)
        c.setContentsMargins(0, 0, 0, 0)
        c.setSpacing(0)
        self._pastilles = _Jeux(media, CINEMATIQUES)
        self._pastilles.choisi.connect(self.montrer)
        c.addWidget(self._pastilles)
        c.addSpacing(14)
        self._liste = QWidget()
        self._liste.setStyleSheet("background: transparent;")
        self._pile = QVBoxLayout(self._liste)
        self._pile.setContentsMargins(0, 0, 0, 12)
        self._pile.setSpacing(0)
        if self._pastilles.ids:
            c.addWidget(zone_defilable(self._liste), stretch=1)
        else:
            c.addWidget(texte(tr("Aucun jeu installé n'a de cinématique à montrer ici pour "
                                 "l'instant. Les trois premiers jeux jouent les leurs dans le "
                                 "moteur, sans fichier vidéo."), 15, "#c9c7da", retour=True))
            c.addStretch()
        racine.addWidget(colonne, stretch=2)

        cote = QWidget()
        cote.setStyleSheet("background: transparent;")
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
        d.addSpacing(12)
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
        d.addLayout(commandes)
        d.addStretch()
        racine.addWidget(cote, stretch=3)
        self._etat_commandes()

        jeux = self._pastilles.ids
        if jeu not in jeux:
            jeu = jeux[0] if jeux else ""
        if jeu:
            self.montrer(jeu)

    def montrer(self, jeu: str) -> None:
        self._jeu = jeu
        self._pastilles.cocher(jeu)
        media = self._media
        nouveaux = media.nouveaux(jeu, CINEMATIQUES)
        while self._pile.count():
            item = self._pile.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._lignes = []
        num = 0
        for clip in media.cinematiques(jeu):
            if media.chemin_cinematique(jeu, clip.fichier) is None:
                continue
            num += 1
            ligne = _LigneCine(self, jeu, num, clip.titre, clip.seuil, media.ouvert(jeu, clip.seuil),
                               clip.fichier in nouveaux, clip.fichier)
            ligne.marquer(clip.fichier == self._courante)
            self._pile.addWidget(ligne)
            self._lignes.append(ligne)
        self._pile.addStretch()
        self._marquer_vus()

    def afficher(self, oui: bool) -> None:
        self._affichee = oui
        self._marquer_vus()
        if not oui:
            self.arreter()

    def _marquer_vus(self) -> None:
        if self._affichee and self._jeu:
            self._media.marquer_vus(self._jeu, CINEMATIQUES)
            self._pastilles.compter(self._jeu)

    def jouer(self, jeu: str, fichier: str, titre: str) -> None:
        chemin = self._media.chemin_cinematique(jeu, fichier)
        if chemin is None:
            return
        fond = self._media.fond
        fond.suspendre(CINEMATIQUE)
        config_coupe = fond.son_coupe
        if not self._video.play(str(chemin), muted=config_coupe,
                                volume=self._media.fond_volume() / 100.0):
            fond.reprendre(CINEMATIQUE)
            return
        self._courante = fichier
        self._titre.setText(titre)
        self._note.setText(tr("Sans le son pour l'instant : il est rangé ailleurs dans le jeu.")
                           if self._media.sans_son(jeu) else self._media.nom(jeu))
        for ligne in self._lignes:
            ligne.marquer(ligne.fichier == fichier)
        self._etat_commandes()

    def _basculer_pause(self) -> None:
        if self._video.paused:
            self._video.resume()
        else:
            self._video.pause()
        self._etat_commandes()

    def arreter(self) -> None:
        """Fin, bouton Arrêter ou page quittée : l'écran se vide, la musique revient."""
        self._video.stop()
        self._courante = ""
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
        self._pause.setText(tr("Reprendre") if actif and self._video.paused else tr("Pause"))


class MediathequePage(QDialog):
    """La Médiathèque, en page : Musique et Cinématiques."""

    def __init__(self, media: Mediatheque, rubrique: str = MUSIQUE, jeu: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("mediatheque")
        self.setWindowTitle(tr("Médiathèque"))
        self.setMinimumSize(900, 560)
        self.setStyleSheet(themed(_STYLE) + feuille_de_style())
        self._media = media
        racine = QVBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(0)

        entete = QWidget()
        entete.setStyleSheet("background: transparent;")
        e = QVBoxLayout(entete)
        e.setContentsMargins(40, 22, 40, 16)
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
        e.addSpacing(12)
        ligne = QHBoxLayout()
        ligne.setSpacing(24)
        titres = QVBoxLayout()
        titres.setSpacing(4)
        titres.addWidget(surtitre(tr("La musique et les cinématiques des jeux")))
        titre = QLabel(tr("Médiathèque"))
        titre.setFont(cinzel_decorative(22))
        titre.setStyleSheet("color: #f4f2f8; background: transparent;")
        titres.addWidget(titre)
        ligne.addLayout(titres)
        ligne.addStretch()
        self._rubriques: dict[str, QPushButton] = {}
        groupe = QButtonGroup(self)
        groupe.setExclusive(True)
        for cle_rubrique, libelle, icone in ((MUSIQUE, tr("Musique"), "musique"),
                                             (CINEMATIQUES, tr("Cinématiques"), "film")):
            b = QPushButton(libelle)
            b.setObjectName("rubrique")
            b.setCheckable(True)
            b.setAutoDefault(False)
            b.setFont(police(14))
            b.setIcon(_icone(icone, 18))
            b.setIconSize(QSize(18, 18))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, r=cle_rubrique: self.rubrique(r))
            groupe.addButton(b)
            ligne.addWidget(b, alignment=Qt.AlignmentFlag.AlignBottom)
            self._rubriques[cle_rubrique] = b
        e.addLayout(ligne)
        racine.addWidget(entete)
        racine.addWidget(_filet())

        self._pile = QStackedWidget()
        self._musique = _VueMusique(media, jeu)
        self._cinematiques = _VueCinematiques(media, jeu)
        self._pile.addWidget(self._musique)
        self._pile.addWidget(self._cinematiques)
        racine.addWidget(self._pile, stretch=1)
        self.rubrique(rubrique if rubrique in self._rubriques else MUSIQUE)

    def rubrique(self, cle_rubrique: str) -> None:
        self._rubriques[cle_rubrique].setChecked(True)
        musique = cle_rubrique == MUSIQUE
        self._pile.setCurrentWidget(self._musique if musique else self._cinematiques)
        self._cinematiques.afficher(not musique)
        self._musique.afficher(musique)

    @property
    def rubrique_courante(self) -> str:
        return MUSIQUE if self._pile.currentWidget() is self._musique else CINEMATIQUES

    def done(self, resultat: int) -> None:
        # La page quittée ne laisse pas une cinématique jouer pour personne.
        self._cinematiques.arreter()
        super().done(resultat)
