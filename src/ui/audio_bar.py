"""Barre audio (mute + volume) du lecteur vidéo de la vue détail."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QSlider, QWidget

from src.ui.icon_button import IconButton
from src.ui.theme import themed

# Aucun pictogramme n'est plus écrit en caractères ici : ils sont PEINTS
# (`src/ui/icon_button.py`). Le haut-parleur était un emoji (U+1F50A), rendu
# en couleur par Windows et insensible au thème, et trois glyphes servis par
# trois polices différentes ne faisaient pas une famille.

# La largeur de la barre est CALCULÉE à partir de ses éléments, et non posée
# à côté d'eux : elle sert à coller la barre au bord droit de la fiche, et
# deux nombres qu'aucun calcul ne relie finissent toujours par se contredire
# — la barre débordait de 18 px HORS de la fenêtre, donc la poignée de volume
# disparaissait au maximum (Ludo, 2026-08-23).
_BOUTON = 26
_ESPACE = 6
_MARGE = 8
_SLIDER = 80
_HAUTEUR = 32
# Le filet compte DEUX fois dans la largeur : il est peint à l'intérieur du
# widget, donc il mange la place du layout. L'oublier serrait le curseur de
# volume de 2 px — invisible, jusqu'au jour où il ne le serait plus.
_BORDURE = 1
_LARGEUR = 2 * (_BORDURE + _MARGE) + 3 * _BOUTON + 3 * _ESPACE + _SLIDER
# Fin de lecture : une pastille RONDE (largeur = hauteur), pas un galet
# rétréci — un rectangle aux bouts arrondis qui ne contient qu'une seule
# icône a l'air d'une barre à qui il manque des boutons.
_MARGE_FIN = 2
_LARGEUR_FIN = 2 * (_BORDURE + _MARGE_FIN) + _BOUTON


class AudioBar(QWidget):
    """Mini-barre flottante avec bouton mute et slider de volume.

    Émet `mute_toggled` (bool) et `volume_changed` (int 0-100). Le contrôleur
    est responsable de propager au lecteur média et de mettre à jour l'icône.
    """

    mute_toggled = pyqtSignal()
    volume_changed = pyqtSignal(int)
    play_toggled = pyqtSignal()
    replay_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Sans `WA_StyledBackground`, un QWidget nu N'APPLIQUE PAS le fond ni
        # la bordure de sa feuille de style : le galet sombre était écrit
        # depuis toujours et n'a jamais été peint, si bien que les icônes
        # flottaient à même la bande-annonce — illisibles sur une image
        # claire, ce qui est précisément le cas d'un plan de jour.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Galet : rayon = moitié de la hauteur (un « presque arrondi » se
        # remarque), plus un filet doré d'un pixel comme les cartes de la
        # fiche — sans lui la barre flotte sans appartenir à rien.
        self.setStyleSheet(themed(
            "AudioBar { background: rgba(6,6,17,0.72);"
            " border: %dpx solid rgba(214,167,44,0.22);" % _BORDURE +
            " border-radius: %dpx; }" % (_HAUTEUR // 2)))
        self.setFixedSize(_LARGEUR, _HAUTEUR)
        self.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(_MARGE, 0, _MARGE, 0)
        layout.setSpacing(_ESPACE)

        # Revoir : une bande-annonce qui se terminait ne laissait AUCUN
        # moyen de la revoir — il fallait changer de jeu et revenir, en
        # espérant que le délai reparte. Ce bouton reste donc affiché
        # après la fin, seul, dans une pastille réduite.
        self._btn_replay = IconButton("replay", _BOUTON, self)
        self._btn_replay.setAccessibleName("Revoir la bande-annonce")
        layout.addWidget(self._btn_replay)
        self._btn_replay.clicked.connect(self.replay_clicked.emit)

        # Pause de la bande-annonce : un contrôle explicite, à côté du son.
        self._btn_play = IconButton("pause", _BOUTON, self)
        self._btn_play.setAccessibleName("Mettre la bande-annonce en pause")
        self._btn_play.clicked.connect(self.play_toggled.emit)
        layout.addWidget(self._btn_play)

        self._btn_mute = IconButton("volume", _BOUTON, self)
        self._btn_mute.setAccessibleName("Couper le son de la vidéo")
        self._btn_mute.clicked.connect(self.mute_toggled.emit)
        layout.addWidget(self._btn_mute)

        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setFixedWidth(_SLIDER)   # la largeur du calcul ci-dessus
        self._volume_slider.setValue(25)
        self._volume_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self._volume_slider.setAccessibleName("Volume de la vidéo")
        self._volume_slider.setStyleSheet(themed(
            "QSlider::groove:horizontal { background: rgba(255,255,255,0.14);"
            " height: 3px; border-radius: 1px; }"
            "QSlider::handle:horizontal { background: #d6a72c; width: 10px;"
            " height: 10px; margin: -4px 0; border-radius: 5px; }"
            "QSlider::handle:horizontal:hover { background: #e8c547; }"
            "QSlider::sub-page:horizontal { background: rgba(214,167,44,0.55);"
            " border-radius: 1px; }"
        ))
        self._volume_slider.valueChanged.connect(self.volume_changed.emit)
        layout.addWidget(self._volume_slider)

    def set_mode_fin(self, fin: bool) -> None:
        """Bascule entre la barre complète et la pastille « revoir ».

        À la fin d'une bande-annonce il n'y a plus rien à mettre en pause
        ni à régler : ne garder que le bouton utile, et se rétrécir pour ne
        pas laisser une barre de commandes inertes au-dessus du carrousel.
        """
        self._btn_play.setVisible(not fin)
        self._btn_mute.setVisible(not fin)
        self._volume_slider.setVisible(not fin)
        marge = _MARGE_FIN if fin else _MARGE
        self.layout().setContentsMargins(marge, 0, marge, 0)
        self.setFixedSize(_LARGEUR_FIN if fin else _LARGEUR, _HAUTEUR)

    def set_muted_icon(self, muted: bool) -> None:
        self._btn_mute.set_icone("muet" if muted else "volume")

    def set_paused_icon(self, paused: bool) -> None:
        self._btn_play.set_icone("play" if paused else "pause")

    def volume(self) -> int:
        return self._volume_slider.value()
