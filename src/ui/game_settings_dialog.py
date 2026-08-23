"""Réglages d'UN jeu : langue aujourd'hui, affichage plus tard.

Pourquoi une FENÊTRE et pas le menu qu'il y avait ici d'abord : un menu est un
choix qu'on prend et qui se referme, alors que les réglages d'un jeu vont
s'étoffer — résolution, qualité, mode fenêtré. Un menu qui grandit devient une
liste à dérouler ; une fenêtre, elle, a des rubriques, de la place pour
expliquer, et sait montrer ce qui n'est pas encore là.

La rubrique « Affichage » est justement là, verrouillée. Annoncer ce qui vient
n'est pas une promesse en l'air : c'est la moitié de la réponse à « pourquoi le
lanceur ne me laisse pas régler la résolution ».
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from src.core.game_data import GameData
from src.core.game_manager import GameManager
from src.core.i18n import tr
from src.ui.fonts import body_font, cinzel
from src.ui.theme import themed

# Réglages annoncés mais pas encore livrés. Ils sont ÉCRITS, pas résumés en
# « bientôt » : quelqu'un qui cherche la résolution doit reconnaître ce qu'il
# cherche, et comprendre que ce n'est pas lui qui n'a pas trouvé.
_A_VENIR = (
    "Résolution",
    "Qualité graphique",
    "Mode fenêtré / plein écran",
)


class GameSettingsDialog(QDialog):
    """Fenêtre de réglages d'un jeu. Le choix de langue s'applique AUSSITÔT.

    Pas de bouton « Appliquer » : l'écriture registre peut demander une
    élévation, et une invite UAC se comprend juste après un clic délibéré sur
    une langue, beaucoup moins après un « Appliquer » qui regrouperait trois
    réglages sans dire lequel la déclenche.
    """

    def __init__(self, game: GameData, manager: GameManager,
                 appliquer_langue, actions=(),
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.game = game
        self.manager = manager
        # Rappel fourni par l'appelant : c'est lui qui sait prévenir, élever et
        # rafraîchir la fiche (cf. `game_detail_handlers._appliquer_langue`).
        self._appliquer_langue = appliquer_langue
        # (libellé, rappel) — composées par l'appelant. La fenêtre reste
        # bête : elle affiche et referme, elle ne sait pas réparer un jeu.
        # Ajouter une entrée demain ne la touchera pas.
        self._actions = tuple(actions)
        self._groupe = QButtonGroup(self)
        self._boutons: dict[str, QRadioButton] = {}

        self.setWindowTitle(tr("Réglages — {}").format(game.name))
        self.setStyleSheet(themed(
            "QDialog { background: #0d0d1a; border: 1px solid rgba(214,167,44,0.3); }"
        ))
        self._build_ui()
        # Pas de taille fixe : le nombre de langues varie de 1 à 7 selon ce que
        # l'installation porte réellement. Une hauteur figée couperait les
        # dernières ou laisserait un grand vide.
        self.setFixedWidth(430)
        self.adjustSize()

    # ── Construction ──

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 16)
        layout.setSpacing(0)

        titre = QLabel(tr("Réglages — {}").format(self.game.name))
        titre.setFont(cinzel(14, bold=True))
        titre.setTextFormat(Qt.TextFormat.PlainText)   # le nom vient du CATALOGUE
        titre.setWordWrap(True)
        titre.setStyleSheet(themed("color: #d6a72c; background: transparent;"))
        layout.addWidget(titre)
        layout.addSpacing(18)

        self._section_langue(layout)
        layout.addSpacing(20)
        self._section_affichage(layout)
        layout.addSpacing(18)
        self._section_fichiers(layout)
        layout.addSpacing(16)

        pied = QHBoxLayout()
        pied.addStretch()
        fermer = QPushButton(tr("Fermer"))
        fermer.setFont(body_font(12))
        fermer.setCursor(Qt.CursorShape.PointingHandCursor)
        fermer.setFixedSize(110, 32)
        fermer.clicked.connect(self.accept)
        pied.addWidget(fermer)
        layout.addLayout(pied)

    def _titre_rubrique(self, texte: str, verrouille: bool = False) -> QWidget:
        ligne = QWidget()
        ligne.setStyleSheet("background: transparent;")
        h = QHBoxLayout(ligne)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        lbl = QLabel(texte)
        lbl.setFont(cinzel(11, bold=True))
        lbl.setStyleSheet(themed(
            "color: %s; background: transparent;" % ("#6a6a80" if verrouille else "#d6a72c")))
        h.addWidget(lbl)
        if verrouille:
            badge = QLabel(tr("BIENTÔT"))
            badge.setFont(body_font(9))
            badge.setStyleSheet(
                "color: #8a8aaa; background: rgba(138,138,170,0.12);"
                " border-radius: 3px; padding: 2px 7px;")
            h.addWidget(badge)
        h.addStretch()
        return ligne

    def _section_langue(self, layout: QVBoxLayout) -> None:
        layout.addWidget(self._titre_rubrique(tr("Langue du jeu")))
        layout.addSpacing(8)

        lr = self.game.language_registry
        courant = self.manager.game_language(self.game)
        proposables = self.manager.langues_disponibles(self.game) if lr else ()

        if len(proposables) < 2:
            # Une seule langue sur le disque : le DIRE. Un choix unique déjà
            # coché laisse croire à un réglage cassé — le registre ne fait que
            # sélectionner, les fichiers viennent du disque d'origine.
            note = QLabel(tr(
                "Ce jeu n'est installé que dans une seule langue.\n"
                "Le lanceur ne peut que sélectionner une langue déjà présente "
                "sur le disque, pas la télécharger."))
            note.setFont(body_font(11))
            note.setWordWrap(True)
            note.setStyleSheet("color: #8a8aaa; background: transparent;")
            layout.addWidget(note)
            return

        for langue in proposables:
            radio = QRadioButton(langue.label)
            radio.setFont(body_font(12))
            radio.setCursor(Qt.CursorShape.PointingHandCursor)
            radio.setStyleSheet(themed(
                "QRadioButton { color: #e8e8f0; background: transparent;"
                " padding: 3px 0px; }"
                "QRadioButton:hover { color: #d6a72c; }"
            ))
            radio.setChecked(langue.code == courant)
            radio.toggled.connect(
                lambda coche, code=langue.code: self._on_langue(coche, code))
            self._groupe.addButton(radio)
            self._boutons[langue.code] = radio
            layout.addWidget(radio)

    def _section_affichage(self, layout: QVBoxLayout) -> None:
        layout.addWidget(self._titre_rubrique(tr("Affichage"), verrouille=True))
        layout.addSpacing(8)
        for nom in _A_VENIR:
            item = QRadioButton(tr(nom))
            item.setFont(body_font(12))
            item.setEnabled(False)
            item.setStyleSheet(
                "QRadioButton { color: #55556a; background: transparent;"
                " padding: 2px 0px; }")
            layout.addWidget(item)
        trait = QFrame()
        trait.setFrameShape(QFrame.Shape.HLine)
        trait.setStyleSheet("color: rgba(255,255,255,0.06);")
        layout.addSpacing(6)
        layout.addWidget(trait)

    def _section_fichiers(self, layout: QVBoxLayout) -> None:
        """Actions qui n'étaient atteignables qu'au CLIC DROIT.

        « Gérer les versions » et « Vérifier / réparer » existaient déjà, mais
        seulement dans le menu contextuel — exactement le défaut qu'on vient de
        corriger pour la langue : une fonction qu'il faut deviner n'existe pas.
        Elles referment la fenêtre avant d'agir, sinon leur propre dialogue
        s'empilerait par-dessus celui-ci.
        """
        if not self._actions:
            return
        layout.addWidget(self._titre_rubrique(tr("Fichiers du jeu")))
        layout.addSpacing(8)
        for libelle, rappel in self._actions:
            btn = QPushButton(libelle)
            btn.setFont(body_font(12))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(themed(
                "QPushButton { color: #d6a72c; background: transparent;"
                " border: none; text-align: left; padding: 4px 0px; }"
                "QPushButton:hover { color: #e8c547; text-decoration: underline; }"
            ))
            btn.clicked.connect(lambda _c=False, r=rappel: self._lancer(r))
            layout.addWidget(btn)

    def _lancer(self, rappel) -> None:
        self.accept()
        rappel()

    # ── Réaction ──

    def _on_langue(self, coche: bool, code: str) -> None:
        """Un bouton radio vient d'être coché.

        `toggled` part AUSSI pour celui qui se décoche : sans le test, un
        changement déclencherait deux écritures registre, donc deux invites UAC
        à la suite — le meilleur moyen de faire refuser la seconde.
        """
        if not coche or code == self.manager.game_language(self.game):
            return
        if not self._appliquer_langue(code):
            # Refus ou échec : remettre le bouton sur ce que porte VRAIMENT le
            # registre. Laisser la sélection sur un choix qui n'a pas pris
            # afficherait une langue que le jeu n'a pas.
            self._resynchroniser()

    def _resynchroniser(self) -> None:
        courant = self.manager.game_language(self.game)
        for code, bouton in self._boutons.items():
            bouton.blockSignals(True)
            bouton.setChecked(code == courant)
            bouton.blockSignals(False)
