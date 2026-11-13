"""Les Défis du Carnet : les succès d'un jeu, en médailles (2026-10-26).

Troisième rubrique du Carnet (`carnet_page.py`). Les succès restaient au bas
du folio, en liste de texte ; ici chacun a sa médaille (`medailles.py`), dans
l'ordre du jeu : du bronze à l'or, on lit ce qui vient ensuite. Une médaille
non obtenue montre son emblème en creux, avec ce qu'elle demande.

Ce qui compte est ce que `succes.obtenus` rend : les sauvegardes de TOUT le
jeu, et la première date observée. Une date inconnue ne s'affiche pas.

« Recommencer les défis » (2026-10-27) remet un jeu à zéro (`succes.recommencer`),
ce que Steam ne permet pas ; une partie déjà avancée les redonne dès qu'on y
rejoue, la confirmation le dit.

En vitrine depuis le 2026-11-13 (car7, choix de Ludo) : les médailles en grand,
centrées, nom dessous, ce qu'elles demandent en infobulle et au focus ; le compte
en tête, en chiffre or avec sa jauge. Avant, deux colonnes de cartes de 912 px où
une médaille de 84 px laissait 80 % de vide, et « 2 sur 7 » en petit gris.
« Recommencer » est un lien discret : la confirmation existe, le geste n'a pas à
être le seul bouton plein de la page.
"""

from datetime import datetime

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QScrollArea, QToolTip, QVBoxLayout, QWidget,
)

from src.core import sauvegardes, succes
from src.core.i18n import tr
from src.ui.composants import feuille_de_style, lien
from src.ui.flow_layout import FlowLayout
from src.ui.folio_page import _tuile
from src.ui.fenetre_message import message
from src.ui.medailles import pixmap_medaille
from src.ui.stats_widgets import _DISCRET, _Paragraphe, _texte
from src.ui.succes_widgets import _jour
from src.ui.theme import themed
from src.ui.utils import BARRE_DEFILEMENT

_MEDAILLE = 128
_LARGEUR_DEFI = 176          # la médaille et l'air autour : quatre à sept par rangée

_STYLE = """
QWidget#defis, QWidget#defisCorps { background: transparent; }
QScrollArea { background: transparent; border: none; }
QFrame#defi { background: transparent; border: 1px solid transparent; border-radius: 12px; }
QFrame#defi[obtenu="true"] { background: rgba(214, 167, 44, 0.05); }
QFrame#tuile { background: #0d0d1a; border: 1px solid rgba(214, 167, 44, 0.16); border-radius: 12px; }
QLabel#titreSection { color: #d6a72c; letter-spacing: 2px; }
"""


class _Defi(QFrame):
    """Une médaille en vitrine : elle, son nom dessous, le jour où elle est tombée ; ce
    qu'elle demande en infobulle, et au focus du clavier (une médaille ne se presse pas)."""

    def __init__(self, jeu: str, defi: succes.Succes, obtenu: succes.Obtenu | None) -> None:
        super().__init__()
        self.setObjectName("defi")
        self.setProperty("obtenu", obtenu is not None)
        self.ident = defi.ident
        self.obtenu = obtenu is not None
        self.demande = tr(defi.description)
        self.setFixedWidth(_LARGEUR_DEFI)
        self.setToolTip(self.demande)
        self.setAccessibleName(tr(defi.titre))
        self.setAccessibleDescription(self.demande)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 14, 10, 12)
        v.setSpacing(6)
        image = QLabel()
        image.setFixedSize(_MEDAILLE, _MEDAILLE)
        image.setPixmap(pixmap_medaille(jeu, defi.ident, self.obtenu, _MEDAILLE, self.devicePixelRatioF()))
        v.addWidget(image, alignment=Qt.AlignmentFlag.AlignHCenter)
        nom = _Paragraphe(tr(defi.titre), taille=14)
        nom.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        nom.setStyleSheet(f"color: {'#ffffff' if obtenu else '#c9c7da'}; font-size: 14px;"
                          f" font-weight: {600 if obtenu else 400}; background: transparent;")
        v.addWidget(nom)
        quand = _jour(obtenu.date) if obtenu is not None else ""
        if quand:
            v.addWidget(_texte(quand, 12, _DISCRET), alignment=Qt.AlignmentFlag.AlignHCenter)
        v.addStretch()

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        QToolTip.showText(self.mapToGlobal(QPoint(self.width() // 2, self.height())), self.demande, self)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        QToolTip.hideText()


class DefisPage(QWidget):
    """Les médailles d'un jeu du folio ; un mot quand le jeu n'en a pas."""

    def __init__(self, game, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("defis")
        self.setStyleSheet(themed(_STYLE) + feuille_de_style())
        self.game = game
        self.defis: list[_Defi] = []
        self._racine = QVBoxLayout(self)
        self._racine.setContentsMargins(0, 0, 0, 0)
        self._remplir()

    def _remplir(self) -> None:
        game = self.game
        definitions = succes.du_jeu(game.id)
        presentes = [v.fichier for v in sauvegardes.vues(game.id, game.sauvegardes)] if definitions else []
        obtenus = succes.obtenus(game.id, presentes, game.sauvegardes) if definitions else {}
        self.defis = []

        racine = self._racine
        zone = QScrollArea()
        zone.setWidgetResizable(True)
        zone.setFrameShape(QFrame.Shape.NoFrame)
        # Sans médailles, la zone est le seul arrêt de Tab de la rubrique : sans
        # anneau, le focus y était invisible (règle 15, audit du 2026-10-29).
        zone.setObjectName("zoneDefis")
        # La barre du launcher, comme le Folio et le Relevé : sans elle, celle du système.
        zone.setStyleSheet(themed(BARRE_DEFILEMENT))
        corps = QWidget()
        corps.setObjectName("defisCorps")
        lay = QVBoxLayout(corps)
        lay.setContentsMargins(40, 26, 40, 30)
        lay.setSpacing(8)
        zone.setWidget(corps)
        racine.addWidget(zone)
        # Les médailles sont les arrêts de Tab ; la zone ne l'est plus que sans elles.
        if definitions:
            zone.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Pas de titre « Défis » : la rubrique choisie en haut le dit déjà.
        if not definitions:
            lay.addWidget(_Paragraphe(tr("Ce jeu n'a pas encore de défis."), taille=14))
            lay.addStretch()
            return
        compte = QHBoxLayout()
        compte.addWidget(_tuile(f"{len(obtenus)} / {len(definitions)}", tr("Défis réussis"),
                                len(obtenus) / len(definitions)))
        compte.addStretch()
        lay.addLayout(compte)
        lay.addSpacing(18)
        vitrine = QWidget()
        vitrine.setObjectName("vitrine")
        vitrine.setStyleSheet("QWidget#vitrine { background: transparent; }")
        flux = FlowLayout(vitrine, spacing=16)
        for defi in definitions:
            carte = _Defi(game.id, defi, obtenus.get(defi.ident))
            flux.addWidget(carte)
            self.defis.append(carte)
        lay.addWidget(vitrine)
        lay.addStretch()
        if obtenus:
            pied = QHBoxLayout()
            pied.addStretch()
            self.bouton_recommencer = lien(tr("Recommencer les défis"), discret=True)
            self.bouton_recommencer.clicked.connect(self.recommencer)
            pied.addWidget(self.bouton_recommencer)
            lay.addSpacing(18)
            lay.addLayout(pied)

    def recommencer(self) -> None:
        """Après confirmation, remet les défis du jeu à zéro et redessine la page."""
        choix = message(
            self, QMessageBox.Icon.Question, tr("Recommencer les défis"),
            tr("Les défis de {} repartent de zéro.").format(self.game.name) + "\n\n"
            + tr("Vos parties déjà avancées les redonnent dès que vous y rejouez : pour repartir "
                 "vraiment de zéro, commencez une nouvelle partie ou supprimez les anciennes "
                 "dans le jeu."),
            choix=(tr("Recommencer"), tr("Annuler")), defaut=1, danger=True)
        if choix != 0:
            return
        succes.recommencer(self.game.id, datetime.now())
        ancienne = self._racine.takeAt(0)
        if ancienne is not None and (w := ancienne.widget()) is not None:
            w.hide()
            w.deleteLater()
        self._remplir()
