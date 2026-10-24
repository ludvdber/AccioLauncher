"""La visite guidée du launcher : un élément éclairé à la fois, une phrase, « Suivant ».

Idée de Ludo (2026-10-24) : l'assistant règle la langue, le dossier et la
maison, puis laisse les gens seuls devant la bibliothèque. Beaucoup ne trouvent
jamais le folio, Mes années ou les réglages graphiques derrière l'engrenage :
« le launcher propose bien plus qu'ils ne le pensent ».

La fenêtre s'assombrit, l'élément de l'étape reste éclairé et cerclé d'or, et
une carte dit en une phrase à quoi il sert. Montrée une fois (`Config.visite_vue`),
après l'assistant comme après une mise à jour ; Paramètres › Général la relance.

Une étape dont l'élément n'est pas à l'écran (jeu pas installé : ni folio ni
engrenage) est sautée plutôt que de cercler un vide. Le calque couvre toute la
fenêtre et reçoit tous les clics : rien ne se lance pendant la visite.
"""

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from src.core.config import Config
from src.core.i18n import tr
from src.ui.composants import ENCRE, bouton, feuille_de_style, police, surtitre, texte
from src.ui.theme import accent_qcolor, bg_qcolor, themed

# Écart entre l'élément et le bord de sa découpe, puis entre la découpe et la carte.
_MARGE_DECOUPE = 8
_ECART_CARTE = 16
# Bord de fenêtre que la carte ne franchit jamais.
_GOUTTIERE = 16
_LARGEUR_CARTE = 380
_RAYON = 12
# Voile : assez sombre pour que l'élément éclairé soit le seul qu'on lise.
_ALPHA_VOILE = 205
# Après l'ouverture : laisser le fondu finir et la fiche se poser.
DELAI_MS = 1500

_STYLE_CARTE = """
QFrame#carteVisite {
    background: #0d0d1a;
    border: 1px solid rgba(214, 167, 44, 0.45);
    border-radius: 12px;
}
"""


@dataclass(frozen=True)
class Etape:
    titre: str
    phrase: str
    # L'élément à éclairer, cherché au moment de l'étape (la fiche se reconstruit
    # à chaque jeu) ; None ou invisible : l'étape est sautée.
    cible: Callable[[], QWidget | None]


def _visible(widget: QWidget | None) -> QWidget | None:
    return widget if widget is not None and widget.isVisible() else None


def etapes_launcher(carrousel: QWidget, fiche: QWidget, barre: QWidget,
                    onglet: Callable[[str], QWidget], contribuer: QWidget) -> list[Etape]:
    """Les étapes, dans l'ordre où l'œil parcourt la fenêtre : bas, centre, haut."""
    from src.ui.resume_partie import BlocFolio
    from src.ui.title_bar import ANNEES, GALERIE, PARAMETRES

    return [
        Etape(tr("Vos huit jeux"),
              tr("Choisissez un jeu ici, à la souris, avec les flèches du clavier ou à la manette."),
              lambda: carrousel),
        Etape(tr("Jouer"),
              tr("Le bouton principal installe le jeu, puis le lance. Pour les trois premiers jeux, "
                 "il rouvre directement votre dernière partie."),
              # Un nouveau venu n'a souvent rien d'installé : TÉLÉCHARGER est son bouton principal.
              lambda: _visible(fiche.findChild(QWidget, "btnPlay"))
              or fiche.findChild(QWidget, "btnDownload")),
        Etape(tr("Les réglages du jeu"),
              tr("Image, réglages graphiques, touches, manette, langue : tout ce qui concerne "
                 "ce jeu est derrière l'engrenage."),
              lambda: fiche.findChild(QWidget, "btnGameSettings")),
        Etape(tr("Votre partie"),
              tr("Votre avancement, lu dans vos sauvegardes. Un clic ouvre le folio : cartes, "
                 "dragées, points de maison."),
              lambda: fiche.findChild(BlocFolio)),
        Etape(tr("Mes années à Poudlard"),
              tr("Votre temps de jeu, votre scolarité année par année et vos succès."),
              lambda: onglet(ANNEES)),
        Etape(tr("La galerie"),
              tr("En jeu, F12 prend une capture. Elles sont toutes ici, rangées par jeu, "
                 "prêtes à partager."),
              lambda: onglet(GALERIE)),
        Etape(tr("Contribuer"),
              tr("Vous dessinez, traduisez ou modélisez ? L'atelier dit comment aider le projet."),
              lambda: contribuer),
        Etape(tr("Paramètres"),
              tr("Langue, dossier des jeux, ambiances, copies de vos sauvegardes. "
                 "Cette visite s'y relance, dans Général."),
              lambda: onglet(PARAMETRES)),
    ]


class VisiteGuidee(QWidget):
    """Le calque de la visite, posé sur toute la fenêtre qui le porte."""

    terminee = pyqtSignal()

    def __init__(self, etapes: list[Etape], parent: QWidget) -> None:
        super().__init__(parent)
        self._etapes = etapes
        self._rang = -1
        self._finie = False
        self._cible = QRect()
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(tr("Visite guidée du launcher"))
        self._construire_carte()
        self.setGeometry(parent.rect())

    # ── Carte ──

    def _construire_carte(self) -> None:
        self._carte = QFrame(self)
        self._carte.setObjectName("carteVisite")
        self._carte.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)   # règle 13
        self._carte.setStyleSheet(themed(_STYLE_CARTE) + feuille_de_style())
        self._carte.setFixedWidth(_LARGEUR_CARTE)
        lay = QVBoxLayout(self._carte)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(8)
        self._compteur = surtitre("")
        lay.addWidget(self._compteur)
        self._titre = QLabel()
        self._titre.setTextFormat(Qt.TextFormat.PlainText)
        self._titre.setFont(police(19, gras=True))
        self._titre.setStyleSheet(f"color: {ENCRE}; background: transparent;")
        self._titre.setWordWrap(True)
        lay.addWidget(self._titre)
        self._phrase = texte("", 14, "#d9d6e8", retour=True)
        lay.addWidget(self._phrase)
        lay.addSpacing(6)
        boutons = QHBoxLayout()
        boutons.setSpacing(8)
        self._btn_passer = bouton(tr("Passer la visite"))
        self._btn_passer.clicked.connect(self.terminer)
        boutons.addWidget(self._btn_passer)
        boutons.addStretch()
        self._btn_precedent = bouton(tr("Précédent"))
        self._btn_precedent.clicked.connect(self.precedent)
        boutons.addWidget(self._btn_precedent)
        self._btn_suivant: QPushButton = bouton(tr("Suivant"), principal=True)
        self._btn_suivant.clicked.connect(self.suivant)
        boutons.addWidget(self._btn_suivant)
        lay.addLayout(boutons)

    # ── Parcours ──

    @property
    def rang(self) -> int:
        return self._rang

    def demarrer(self) -> bool:
        """Première étape visible ; False s'il n'y en a aucune (rien n'est montré)."""
        if not self._aller(0, +1):
            return False
        self.show()
        self.raise_()
        return True

    def suivant(self) -> None:
        if not self._aller(self._rang + 1, +1):
            self.terminer()

    def precedent(self) -> None:
        self._aller(self._rang - 1, -1)

    def terminer(self) -> None:
        if self._finie:   # Échap puis un clic avant la destruction : une seule fin
            return
        self._finie = True
        self.hide()
        self.terminee.emit()
        self.deleteLater()

    def _visible(self, rang: int) -> QWidget | None:
        widget = _visible(self._etapes[rang].cible())
        return widget if widget is not None and widget.width() > 0 else None

    def _rang_visible(self, depart: int, pas: int) -> int:
        rang = depart
        while 0 <= rang < len(self._etapes):
            if self._visible(rang) is not None:
                return rang
            rang += pas
        return -1

    def _aller(self, depart: int, pas: int) -> bool:
        rang = self._rang_visible(depart, pas)
        if rang < 0:
            return False
        self._rang = rang
        etape = self._etapes[rang]
        visibles = [r for r in range(len(self._etapes)) if self._visible(r) is not None]
        self._compteur.setText(tr("Étape {} sur {}").format(visibles.index(rang) + 1,
                                                             len(visibles)).upper())
        self._titre.setText(etape.titre)
        self._phrase.setText(etape.phrase)
        self._btn_precedent.setVisible(self._rang_visible(rang - 1, -1) >= 0)
        dernier = self._rang_visible(rang + 1, +1) < 0
        self._btn_suivant.setText(tr("Terminer") if dernier else tr("Suivant"))
        # « Terminer » fait la même chose : deux boutons pour une sortie, c'est un de trop.
        self._btn_passer.setVisible(not dernier)
        for btn in (self._btn_passer, self._btn_precedent, self._btn_suivant):
            # Un libellé plus long (espagnol) élargit la carte au lieu d'être rogné.
            btn.setMinimumWidth(btn.sizeHint().width())
        self._poser()
        self._btn_suivant.setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    # ── Géométrie ──

    def _poser(self) -> None:
        """Découpe autour de l'élément, carte dessous, sinon dessus, sinon au centre."""
        widget = self._visible(self._rang) if self._rang >= 0 else None
        parent = self.parentWidget()
        if widget is None or parent is None:
            return
        # `parent` est un ANCÊTRE de l'élément : mapTo est juste (règle 47).
        coin = widget.mapTo(parent, QPoint(0, 0))
        # Rognée au bord : un onglet collé en haut garderait sinon un cadre ouvert.
        self._cible = QRect(coin, widget.size()).adjusted(
            -_MARGE_DECOUPE, -_MARGE_DECOUPE, _MARGE_DECOUPE, _MARGE_DECOUPE
        ).intersected(self.rect().adjusted(1, 1, -1, -1))
        largeur = max(_LARGEUR_CARTE, self._carte.layout().minimumSize().width())
        self._carte.setFixedWidth(largeur)
        hauteur = self._carte.layout().totalHeightForWidth(largeur)
        self._carte.setFixedHeight(hauteur)
        x = self._cible.center().x() - largeur // 2
        x = max(_GOUTTIERE, min(x, self.width() - _GOUTTIERE - largeur))
        dessous = self._cible.bottom() + _ECART_CARTE
        dessus = self._cible.top() - _ECART_CARTE - hauteur
        if dessous + hauteur <= self.height() - _GOUTTIERE:
            y = dessous
        elif dessus >= _GOUTTIERE:
            y = dessus
        else:   # élément plus haut que la fenêtre ne laisse de place : au centre
            y = (self.height() - hauteur) // 2
        self._carte.move(x, max(_GOUTTIERE, y))
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._poser()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        voile = QPainterPath()
        voile.addRect(QRectF(self.rect()))
        trou = QPainterPath()
        trou.addRoundedRect(QRectF(self._cible), _RAYON, _RAYON)
        p.fillPath(voile.subtracted(trou), bg_qcolor(_ALPHA_VOILE))
        if not self._cible.isEmpty():
            p.setPen(QPen(accent_qcolor(235), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(self._cible), _RAYON, _RAYON)
        p.end()

    # ── Clavier ──

    def touche(self, event: QKeyEvent) -> bool:
        """Appelée par la fenêtre AVANT ses raccourcis : True = consommée.

        Entrée et → avancent, ← recule, Échap passe la visite. Le reste (Tab,
        Espace sur le bouton qui a le focus) suit son cours normal.
        """
        match event.key():
            case Qt.Key.Key_Return | Qt.Key.Key_Enter | Qt.Key.Key_Right:
                self.suivant()
            case Qt.Key.Key_Left:
                self.precedent()
            case Qt.Key.Key_Escape:
                self.terminer()
            case _:
                return False
        return True

    def mousePressEvent(self, event) -> None:
        event.accept()   # rien ne passe sous le voile


class PiloteVisite(QObject):
    """Quand la visite se montre : la fenêtre ne garde que le câblage.

    Une fois (`Config.visite_vue`), 1,5 s après l'affichage, par un minuteur
    POSSÉDÉ (règle 102) ; pas en jeu, pas au tray ; une page ouverte (les
    nouveautés après une mise à jour) la fait attendre le retour à la
    bibliothèque. Notée vue à la FIN, finie ou passée : une fenêtre fermée au
    milieu la remontre au démarrage suivant.

    Il écoute lui-même l'affichage et le redimensionnement de la fenêtre :
    `main_window.py` a un plafond de lignes, et ce n'est que de la plomberie.
    """

    def __init__(self, fenetre: QWidget, config: Config, pages, carrousel: QWidget,
                 fiche: QWidget, barre, en_jeu: Callable[[], bool]) -> None:
        super().__init__(fenetre)
        self._fenetre = fenetre
        self._config = config
        self._pages = pages
        self._etapes = lambda: etapes_launcher(carrousel, fiche, barre, barre.onglet,
                                               barre.contribuer)
        self._en_jeu = en_jeu
        self._fiche = fiche
        self.calque: VisiteGuidee | None = None
        self._attend_page = False
        self.minuteur = QTimer(self)
        self.minuteur.setSingleShot(True)
        self.minuteur.setInterval(DELAI_MS)
        self.minuteur.timeout.connect(self.proposer)
        pages.fermee.connect(self._apres_page)
        fenetre.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.Show:
            self.armer()
        elif event.type() == QEvent.Type.Resize:
            self.reposer()
        return False

    def armer(self) -> None:
        """La fenêtre vient de s'afficher."""
        if not self._config.visite_vue and self.calque is None:
            self.minuteur.start()

    def proposer(self) -> None:
        if self._config.visite_vue or self.calque is not None:
            return
        if not self._fenetre.isVisible() or self._en_jeu():
            return
        if self._pages.page is not None:
            self._attend_page = True
            return
        self.lancer()

    def _apres_page(self) -> None:
        if self._attend_page:
            self._attend_page = False
            self.minuteur.start()

    def revoir(self) -> None:
        """« Revoir la visite » des Paramètres : retour à la bibliothèque d'abord."""
        self._attend_page = False
        self._pages.fermer()
        self.lancer()

    def lancer(self) -> None:
        if self.calque is not None:
            return
        calque = VisiteGuidee(self._etapes(), self._fenetre)
        calque.terminee.connect(self._fin)
        self.calque = calque
        if not calque.demarrer():
            self.calque = None
            calque.deleteLater()

    def _fin(self) -> None:
        self.calque = None
        if not self._config.visite_vue:
            self._config.visite_vue = True
            self._config.save()
        self._fiche.setFocus(Qt.FocusReason.OtherFocusReason)

    @property
    def active(self) -> bool:
        return self.calque is not None

    def touche(self, event: QKeyEvent) -> bool:
        """À appeler AVANT les raccourcis de la fenêtre, visite à l'écran : Entrée
        lançait sinon le jeu caché sous le voile, et les flèches tournaient le carrousel."""
        return self.calque is not None and self.calque.touche(event)

    def reposer(self) -> None:
        """Fenêtre redimensionnée : le calque la recouvre toujours, au-dessus de tout."""
        if self.calque is not None:
            self.calque.setGeometry(self._fenetre.rect())
            self.calque.raise_()
