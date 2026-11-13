"""Anneau de focus réservé au CLAVIER.

Qt ne connaît pas `:focus-visible` : la règle `:focus` du stylesheet global
s'applique aussi bien à un focus donné par le clavier qu'à celui que Qt pose
tout seul sur le premier bouton de la chaîne à l'ouverture de la fenêtre, ou à
celui d'un simple clic. Résultat : le bouton « Réduire » s'ouvrait cerclé d'or
alors que personne n'avait rien fait, et un clic sur JOUER laissait l'anneau
derrière lui — dans les deux cas, l'œil est attiré pour rien.

Supprimer l'anneau n'est pas une option : c'est le seul repère d'un utilisateur
au clavier. On distingue donc les deux cas par la RAISON du focus, et le
stylesheet ne cercle que les widgets marqués. Un widget jamais marqué n'a pas
la propriété, donc le sélecteur ne l'atteint pas : le défaut est « pas
d'anneau », ce qu'on veut.

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


from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtWidgets import QAbstractButton, QApplication, QScrollArea, QWidget


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


def _marque(widget: QWidget, actif: bool) -> None:
    """Pose la propriété et redemande le style — seulement si ça change."""
    if widget.property(PROPRIETE) == actif:
        return
    widget.setProperty(PROPRIETE, actif)
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()


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
