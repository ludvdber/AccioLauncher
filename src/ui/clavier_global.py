"""Les touches que la fenêtre principale intercepte avant ses widgets.

Extrait de `main_window` (plafond de lignes) : la décision ne lit que la
touche, le focus, le carrousel et la fiche — pas la fenêtre.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractSpinBox, QApplication, QComboBox, QLineEdit, QSlider,
)

# Le focus sur l'un de ces widgets garde ses flèches : elles y ont un sens.
_EDITION = (QLineEdit, QComboBox, QSlider, QAbstractSpinBox)


def touche_globale(event, carrousel, fiche, fenetre_active: bool) -> bool:
    """←/→ naviguent le carrousel même quand un bouton a le focus (A11Y).
    Échap sort du plein écran de la bande-annonce, et seulement de ça.
    True = la touche est consommée.

    Sans ce filtre, le premier clic sur un bouton lui donnait le focus et les
    flèches devenaient muettes (Qt les consomme pour déplacer le focus).
    Jamais actif quand un dialogue modal est ouvert ni quand le focus est sur
    un widget d'édition (slider de volume, combo, champ texte).
    """
    if event.key() not in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Escape):
        return False
    if QApplication.activeModalWidget() is not None or not fenetre_active:
        return False
    if event.key() == Qt.Key.Key_Escape:
        # Échap ne sort QUE du plein écran : la fenêtre est sans cadre, et la
        # fermer sur une touche pressée par réflexe serait une mauvaise
        # surprise. False quand il n'y a rien à quitter, pour ne pas manger la
        # touche que les widgets pourraient vouloir.
        if not fiche.cinema():
            return False
        fiche.set_cinema(False)
        return True
    if isinstance(QApplication.focusWidget(), _EDITION):
        return False
    if event.key() == Qt.Key.Key_Left:
        carrousel.select_prev()
    else:
        carrousel.select_next()
    return True
