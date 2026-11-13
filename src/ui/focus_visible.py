"""Anneau de focus réservé au CLAVIER.

Qt ne connaît pas `:focus-visible` : la règle `:focus` du stylesheet global
s'applique aussi bien à un focus donné par le clavier qu'à celui que Qt pose
tout seul sur le premier bouton de la chaîne à l'ouverture de la fenêtre, ou à
celui d'un simple clic. Résultat : le bouton « Réduire » s'ouvrait cerclé d'or
alors que personne n'avait rien fait, et un clic sur JOUER laissait l'anneau
derrière lui — dans les deux cas, l'œil est attiré pour rien.

Supprimer l'anneau n'est pas une option : c'est le seul repère d'un utilisateur
au clavier. On distingue donc les deux cas par la RAISON du focus : le widget
reçoit la propriété `focusClavier`, et UN anneau le suit.

Un seul anneau pour toute l'interface, dessiné ici : un widget transparent à la
souris, enfant de la fenêtre, posé au-dessus du contrôle marqué, 2 px de la
couleur de la maison, à 3 px du bord et arrondi comme le contrôle. Les
feuilles de style en écrivaient sept façons différentes (cadre, couleur du
texte, fond…), la règle `outline` globale ajoutait un rectangle à angles droits
DANS le cadre, et un lien, un curseur ou « Lire la suite… » ne changeaient
d'aucun pixel (audit UI tra5 et tra6, 2026-11-13). Aucune feuille de style ni
aucun widget peint ne dessine donc son propre anneau (`test_focus_visible`).
Le rayon se lit dans la feuille de style du contrôle ; un widget peint dit sa
forme avec `forme()`. Dans une zone qui défile, l'anneau est coupé au bord
visible de la zone.

Le filtre est posé sur QApplication : il couvre aussi les dialogues et
l'assistant de premier lancement, qui vivent avant MainWindow.

Deux autres devoirs du même filtre, parce qu'ils tiennent au même événement :
la fenêtre qui perd la main (Alt+Tab, un menu) GARDE la marque de son widget,
sinon le focus revenait sans anneau et Espace agissait sur un bouton qu'on ne
voyait plus désigné ; et un focus reçu au clavier fait défiler jusqu'à lui
chaque zone qui le contient : Qt ne le fait que pour un Tab parti de la zone
elle-même, et un Maj+Tab venu de la barre du haut laissait le focus 39 px sous
le bas de la fenêtre.

Une raison Tab ne vaut clavier que pendant l'appui d'une touche : un widget qui
se cache en tenant le focus le passe au suivant avec cette raison, et un clic
sur « ← Bibliothèque » allumait l'onglet BIBLIOTHÈQUE comme un Tab.

Tab qui ENTRE dans un groupe exclusif (rail, catégories, segments, cartes du
folio) se pose sur le choix coché, pas sur le premier bouton : le Carnet ouvert
sur les Défis cerclait « Folio », et Espace ouvrait autre chose que ce qu'on
croyait désigné. Dans le groupe, Tab avance comme avant.
"""


import re

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, Qt, QTimer
from PyQt6.QtGui import QPainter, QPen
from PyQt6.QtWidgets import QAbstractButton, QAbstractScrollArea, QApplication, QScrollArea, QWidget

from src.ui.theme import RAYON_CONTROLE, accent_qcolor


PROPRIETE = "focusClavier"

# Tab / Maj+Tab / raccourci mnémonique. Tout le reste (ouverture de la fenêtre,
# clic, popup, retour depuis une autre application) n'est PAS une intention de
# navigation au clavier.
_RAISONS_CLAVIER = frozenset({
    Qt.FocusReason.TabFocusReason,
    Qt.FocusReason.BacktabFocusReason,
    Qt.FocusReason.ShortcutFocusReason,
})
# La fenêtre perd ou reprend la main, un menu s'ouvre ou se ferme : le focus ne
# change pas de widget, sa marque non plus.
_RAISONS_GARDEES = frozenset({
    Qt.FocusReason.ActiveWindowFocusReason,
    Qt.FocusReason.PopupFocusReason,
})
_MARGE_DEFILEMENT = 24

# L'anneau : son épaisseur, et l'écart entre le bord du contrôle et le milieu du trait.
_TRAIT = 2.0
_ECART = 3
_RAYON = "rayonFocus"           # propriétés posées par `forme()`
_RETRAIT = "retraitFocus"
# `#nom … { … border-radius: 13px` : le rayon que la feuille de style donne au contrôle.
_RAYON_FEUILLE = r"#{}\b[^{{}}]*\{{[^}}]*?border-radius:\s*(\d+)px"
_RAYON_NU = re.compile(r"^[^{}]*border-radius:\s*(\d+)px")
PASTILLE = 10_000.0             # `forme(w, PASTILLE)` : rond, ou pastille, à toute hauteur


def forme(widget: QWidget, rayon: float, retrait: int = 0) -> None:
    """La forme d'un contrôle PEINT pour l'anneau : son rayon, et la marge transparente
    qui entoure ce qu'il dessine (l'interrupteur en garde une)."""
    widget.setProperty(_RAYON, float(rayon))
    widget.setProperty(_RETRAIT, retrait)


def _rayon(widget: QWidget, hauteur: int) -> float:
    """Le rayon du contrôle : posé par `forme()`, sinon lu dans la feuille de style la plus
    proche qui le nomme. Un rayon de pastille (au moins 40 % de la hauteur) suit la hauteur
    réelle : `#filtre[grand="true"]` est plus haut que la règle `#filtre` qu'on lit."""
    pose = widget.property(_RAYON)
    rayon = float(pose) if pose is not None else None
    nom = widget.objectName()
    motif = re.compile(_RAYON_FEUILLE.format(re.escape(nom))) if nom else None
    porteur: QWidget | None = widget
    while rayon is None and porteur is not None:
        feuille = porteur.styleSheet()
        trouve = (_RAYON_NU.search(feuille) if porteur is widget else None) or (
            motif.search(feuille) if motif is not None and feuille else None)
        if trouve:
            rayon = float(trouve.group(1))
        porteur = porteur.parentWidget()
    if rayon is None:
        return float(RAYON_CONTROLE)
    return hauteur / 2 if rayon >= 0.4 * hauteur else rayon


class _Anneau(QWidget):
    """L'anneau du contrôle marqué, au-dessus de tout dans sa fenêtre."""

    def __init__(self, fenetre: QWidget) -> None:
        super().__init__(fenetre)
        self.setObjectName("anneauFocus")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hide()
        self._cible: QWidget | None = None
        self._suivis: list[QWidget] = []
        self._coupe = QRect()           # la partie visible, dans le repère de l'anneau
        self._rayon = 0.0
        self._en_attente = False

    def suivre(self, cible: QWidget) -> None:
        if cible is not self._cible:
            self.lacher()
            self._cible = cible
            cible.destroyed.connect(self._detruite)
            porteur: QWidget | None = cible
            while porteur is not None and porteur is not self.parentWidget():
                porteur.installEventFilter(self)
                self._suivis.append(porteur)
                porteur = porteur.parentWidget()
        self._placer()

    def lacher(self, cible: QWidget | None = None) -> None:
        if cible is not None and cible is not self._cible:
            return
        if self._cible is not None:
            try:
                self._cible.destroyed.disconnect(self._detruite)
            except (TypeError, RuntimeError):
                pass
        for porteur in self._suivis:
            try:
                porteur.removeEventFilter(self)
            except RuntimeError:            # déjà détruit
                pass
        self._suivis.clear()
        self._cible = None
        self.hide()

    def _detruite(self) -> None:
        self._suivis.clear()
        self._cible = None
        self.hide()

    def eventFilter(self, obj, event) -> bool:
        if event.type() in (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.Show,
                            QEvent.Type.Hide) and not self._en_attente:
            # Une mise en page bouge vingt widgets d'un coup : un seul placement après.
            self._en_attente = True
            QTimer.singleShot(0, self._replacer)
        return False

    def _replacer(self) -> None:
        self._en_attente = False
        if self._cible is not None:
            self._placer()

    def _placer(self) -> None:
        cible, fenetre = self._cible, self.parentWidget()
        if cible is None or fenetre is None or not cible.isVisible():
            self.hide()
            return
        retrait = int(cible.property(_RETRAIT) or 0)
        contour = QRect(cible.mapTo(fenetre, QPoint(0, 0)), cible.size()).adjusted(
            retrait, retrait, -retrait, -retrait)
        self._rayon = _rayon(cible, contour.height()) + _ECART
        deborde = _ECART + int(_TRAIT)
        zone = contour.adjusted(-deborde, -deborde, deborde, deborde)
        visible = fenetre.rect()
        porteur = cible.parentWidget()
        while porteur is not None and porteur is not fenetre:
            if isinstance(porteur, QAbstractScrollArea) and porteur.viewport() is not None:
                vue = porteur.viewport()
                visible = visible.intersected(QRect(vue.mapTo(fenetre, QPoint(0, 0)), vue.size()))
            porteur = porteur.parentWidget()
        coupe = zone.intersected(visible)
        if coupe.isEmpty():
            self.hide()
            return
        self.setGeometry(zone)
        self._coupe = coupe.translated(-zone.topLeft())
        self.raise_()
        self.show()
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setClipRect(self._coupe)
        p.setPen(QPen(accent_qcolor(), _TRAIT))
        p.setBrush(Qt.BrushStyle.NoBrush)
        moitie = _TRAIT / 2
        p.drawRoundedRect(QRectF(self.rect()).adjusted(moitie, moitie, -moitie, -moitie),
                          self._rayon, self._rayon)
        p.end()


def _anneau(fenetre: QWidget, creer: bool) -> _Anneau | None:
    """L'anneau de la fenêtre, créé au premier besoin si `creer`."""
    anneau = fenetre.findChild(_Anneau, "anneauFocus", Qt.FindChildOption.FindDirectChildrenOnly)
    return _Anneau(fenetre) if anneau is None and creer else anneau


def _marque(widget: QWidget, actif: bool) -> None:
    """Pose la propriété, et l'anneau de la fenêtre suit le widget marqué ou le quitte."""
    if isinstance(widget, _Anneau):
        return
    if widget.property(PROPRIETE) != actif:
        widget.setProperty(PROPRIETE, actif)
        widget.update()        # le Relevé peint sa ligne choisie au clavier
    fenetre = widget.window()
    if fenetre is widget:      # une fenêtre seule n'a pas où poser d'anneau
        return
    anneau = _anneau(fenetre, actif)
    if anneau is None:
        return
    if actif:
        anneau.suivre(widget)
    else:
        anneau.lacher(widget)


def marquer(widget: QWidget | None) -> None:
    """Allume l'anneau du widget qui a DÉJÀ le focus (la manette, `manette_nav`).

    Une fenêtre qui s'ouvre donne le focus à son premier contrôle sans raison
    clavier : pas d'anneau, et à la manette on ne savait pas où l'on était.
    Tout appui de la manette est une intention de navigation : il l'allume.
    """
    if widget is not None and widget.hasFocus():
        _marque(widget, True)


def montrer(widget: QWidget) -> None:
    """Fait défiler chaque zone qui contient `widget` jusqu'à lui, de la plus proche à la plus large."""
    enfant, parent = widget, widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QScrollArea) and parent.widget() is not None:
            parent.ensureWidgetVisible(enfant, 0, _MARGE_DEFILEMENT)
            enfant = parent
        parent = parent.parentWidget()


def _choix_du_groupe(widget: QWidget, avant: QWidget | None) -> QAbstractButton | None:
    """Le bouton coché du groupe exclusif où `widget` entre depuis l'extérieur, s'il n'est pas lui."""
    groupe = widget.group() if isinstance(widget, QAbstractButton) else None
    if groupe is None or not groupe.exclusive():
        return None
    coche = groupe.checkedButton()
    if coche is None or coche is widget or not coche.isVisible() or not coche.isEnabled():
        return None
    try:
        dedans = isinstance(avant, QAbstractButton) and avant.group() is groupe
    except RuntimeError:            # le widget d'avant est déjà détruit
        dedans = False
    return None if dedans else coche


class _FiltreFocus(QObject):
    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self._touche = False          # une touche est en cours de traitement
        self._avant: QWidget | None = None     # qui avait le focus juste avant

    def _relacher(self) -> None:
        self._touche = False

    def eventFilter(self, obj, event) -> bool:
        type_ = event.type()
        if type_ == QEvent.Type.KeyPress and not self._touche:
            self._touche = True
            QTimer.singleShot(0, self._relacher)
        elif type_ in (QEvent.Type.FocusIn, QEvent.Type.FocusOut) and isinstance(obj, QWidget):
            raison = event.reason()
            if raison in _RAISONS_GARDEES:
                return False
            if type_ == QEvent.Type.FocusOut:
                self._avant = obj
            elif raison in (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason):
                coche = _choix_du_groupe(obj, self._avant)
                if coche is not None:
                    coche.setFocus(raison)
                    return False
            clavier = type_ == QEvent.Type.FocusIn and raison in _RAISONS_CLAVIER and self._touche
            _marque(obj, clavier)
            if clavier:
                montrer(obj)
        return False       # ne jamais consommer l'événement


_filtre: _FiltreFocus | None = None


def install(app: QApplication) -> None:
    """À appeler une fois, juste après la création de QApplication."""
    global _filtre
    if _filtre is not None:
        return
    _filtre = _FiltreFocus(app)
    app.installEventFilter(_filtre)
