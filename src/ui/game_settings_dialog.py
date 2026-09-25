"""Réglages d'UN jeu : langue, et pour HP4-HP6 les réglages confirmés de leur correctif PC.

Pourquoi une FENÊTRE et pas le menu qu'il y avait ici d'abord : un menu est un
choix qu'on prend et qui se referme, alors que les réglages d'un jeu vont
s'étoffer — résolution, qualité, mode fenêtré. Un menu qui grandit devient une
liste à dérouler ; une fenêtre, elle, a des rubriques, de la place pour
expliquer, et sait montrer ce qui n'est pas encore là.

La rubrique « Affichage » est justement là, verrouillée. Annoncer ce qui vient
n'est pas une promesse en l'air : c'est la moitié de la réponse à « pourquoi le
lanceur ne me laisse pas régler la résolution ».
"""

import logging
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from src.core import reglages_correctif
from src.core.game_data import GameData
from src.core.game_manager import GameManager
from src.core.i18n import tr
from src.ui.fonts import body_font, cinzel
from src.ui.settings_panel import _COMBO_STYLE
from src.ui.theme import themed
from src.ui.toggle_switch import toggle_row
from src.ui.utils import zone_defilable

log = logging.getLogger(__name__)

# Les mesures du cadre : `_ajuster_hauteur` les additionne, la construction les pose.
_LARGEUR = 430
_MARGES_H = 22 + 22   # contentsMargins gauche et droite de la fenêtre
_MARGE_HAUT, _MARGE_BAS = 20, 16
_ESPACE_TITRE = 18
_ESPACE_PIED = 8
_HAUTEUR_PIED = 32    # le bouton « Fermer »

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
        # Réglages du correctif que le catalogue déclare confirmés pour ce jeu,
        # et son ini (à côté de l'exécutable, là où le correctif le lit).
        self._reglages = reglages_correctif.reglages_du_jeu(game.fix_settings)
        self._ini: Path | None = (
            reglages_correctif.chemin_ini(
                manager.config.install_path / Path(game.executable).parent)
            if self._reglages else None)
        self._erreur: QLabel | None = None

        self.setWindowTitle(tr("Réglages — {}").format(game.name))
        self.setStyleSheet(themed(
            "QDialog { background: #0d0d1a; border: 1px solid rgba(214,167,44,0.3); }"
        ))
        self._build_ui()
        # La hauteur suit le contenu (de 1 à 7 langues, de 0 à 7 réglages), et
        # l'écran la plafonne : au-delà, les rubriques défilent.
        self.setFixedWidth(_LARGEUR)
        self._ajuster_hauteur()

    def _ajuster_hauteur(self) -> None:
        """Hauteur calculée, pas demandée à `adjustSize`.

        Chaque bloc qui passe à la ligne est mesuré par `heightForWidth` à la
        largeur RÉELLE : le layout, lui, comptait le titre (deux lignes pour « La
        Coupe de Feu ») sur une seule, et « Fermer » chevauchait les rubriques
        (règles 38 et 39).
        """
        largeur = _LARGEUR - _MARGES_H
        corps = self._contenu.layout()
        corps.activate()
        voulu = corps.totalHeightForWidth(largeur) if corps.hasHeightForWidth() else corps.sizeHint().height()
        cadre = _MARGE_HAUT + self._titre.heightForWidth(largeur) + _ESPACE_TITRE + _ESPACE_PIED + _HAUTEUR_PIED + _MARGE_BAS
        ecran = self.screen() or QGuiApplication.primaryScreen()
        # La barre de titre de Windows et un peu d'air au-dessus de la barre des tâches.
        plafond = ecran.availableGeometry().height() - cadre - 60 if ecran is not None else voulu
        if voulu > plafond:
            # La barre de défilement prend sa place à droite : le texte s'en écarte.
            corps.setContentsMargins(0, 0, 18, 0)
        hauteur = max(120, min(voulu, plafond))
        self._defile.setFixedHeight(hauteur)
        self.setFixedHeight(cadre + hauteur)

    # ── Construction ──

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(_MARGES_H // 2, _MARGE_HAUT, _MARGES_H // 2, _MARGE_BAS)
        layout.setSpacing(0)

        titre = QLabel(tr("Réglages — {}").format(self.game.name))
        titre.setFont(cinzel(14, bold=True))
        titre.setTextFormat(Qt.TextFormat.PlainText)   # le nom vient du CATALOGUE
        titre.setWordWrap(True)
        titre.setStyleSheet(themed("color: #d6a72c; background: transparent;"))
        layout.addWidget(titre)
        layout.addSpacing(_ESPACE_TITRE)
        self._titre = titre

        # Les rubriques défilent, le titre et « Fermer » restent : avec les sept
        # réglages de HP4 et les fichiers du jeu, la fenêtre dépasse 718 px, plus
        # que ce qu'offre un écran de 768 px une fois la barre des tâches ôtée
        # (règle 52 : une page qui peut déborder doit pouvoir défiler).
        self._contenu = QWidget()
        self._contenu.setStyleSheet("background: transparent;")
        corps = QVBoxLayout(self._contenu)
        corps.setContentsMargins(0, 0, 0, 0)
        corps.setSpacing(0)
        self._section_langue(corps)
        corps.addSpacing(20)
        self._section_affichage(corps)
        corps.addSpacing(18)
        self._section_fichiers(corps)
        corps.addSpacing(16)
        self._defile = zone_defilable(self._contenu)
        layout.addWidget(self._defile)
        layout.addSpacing(_ESPACE_PIED)

        pied = QHBoxLayout()
        pied.addStretch()
        fermer = QPushButton(tr("Fermer"))
        fermer.setFont(body_font(12))
        fermer.setCursor(Qt.CursorShape.PointingHandCursor)
        fermer.setFixedSize(110, _HAUTEUR_PIED)
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
        if self._reglages:
            self._section_correctif(layout)
            return
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
        if self.game.display_locked:
            # Cette rubrique est exactement l'endroit où va celui qui cherche la
            # résolution — donc celui qui, ne la trouvant pas ici, ira la
            # chercher dans le menu du jeu et cassera son installation.
            note = QLabel(tr(
                "Ne touchez pas aux options vidéo DANS le jeu : l'affichage "
                "est déjà réglé au mieux par le lanceur, et le modifier ici "
                "peut empêcher le jeu de redémarrer.\n"
                "Ces réglages viendront ici."))
            note.setFont(body_font(11))
            note.setWordWrap(True)
            note.setTextFormat(Qt.TextFormat.PlainText)
            note.setStyleSheet("color: #e8955a; background: transparent;")
            layout.addSpacing(6)
            layout.addWidget(note)
        trait = QFrame()
        trait.setFrameShape(QFrame.Shape.HLine)
        trait.setStyleSheet("color: rgba(255,255,255,0.06);")
        layout.addSpacing(6)
        layout.addWidget(trait)

    def _section_correctif(self, layout: QVBoxLayout) -> None:
        """Réglages du correctif PC (HP4-HP6), ceux que le catalogue déclare confirmés.

        Trois cas, et chacun le DIT : jeu absent, ancien correctif (les archives
        publiées le portent encore : rien ne lirait ces clés), nouveau correctif.
        """
        layout.addWidget(self._titre_rubrique(tr("Affichage et jeu")))
        layout.addSpacing(8)
        ini = self._ini
        if ini is None or not ini.is_file():
            self._note(layout, tr("Installez le jeu pour régler son correctif."))
        elif not reglages_correctif.est_nouveau_correctif(ini):
            self._note(layout, tr(
                "Ces réglages arrivent avec la prochaine version du correctif "
                "de ce jeu."))
        else:
            for reglage in self._reglages:
                self._controle(layout, ini, reglage)
            self._erreur = QLabel("")
            self._erreur.setFont(body_font(11))
            self._erreur.setWordWrap(True)
            self._erreur.setTextFormat(Qt.TextFormat.PlainText)
            self._erreur.setStyleSheet("color: #e8955a; background: transparent;")
            self._erreur.hide()
            layout.addWidget(self._erreur)
            self._note(layout, tr("Pris en compte au prochain lancement du jeu."))
        layout.addSpacing(10)
        layout.addWidget(self._titre_rubrique(tr("Plus tard"), verrouille=True))
        layout.addSpacing(4)
        # Une ligne et non une liste de boutons grisés : trois réglages actifs
        # et leurs explications occupent déjà la hauteur d'un petit écran.
        bientot = QLabel(" · ".join(tr(nom) for nom in reglages_correctif.A_VENIR))
        bientot.setFont(body_font(11))
        bientot.setWordWrap(True)
        bientot.setTextFormat(Qt.TextFormat.PlainText)
        bientot.setStyleSheet("color: #6a6a80; background: transparent;")
        layout.addWidget(bientot)
        trait = QFrame()
        trait.setFrameShape(QFrame.Shape.HLine)
        trait.setStyleSheet("color: rgba(255,255,255,0.06);")
        layout.addSpacing(6)
        layout.addWidget(trait)

    def _note(self, layout: QVBoxLayout, texte: str) -> None:
        note = QLabel(texte)
        note.setFont(body_font(11))
        note.setWordWrap(True)
        note.setTextFormat(Qt.TextFormat.PlainText)
        note.setStyleSheet("color: #8a8aaa; background: transparent;")
        layout.addWidget(note)

    def _controle(self, layout: QVBoxLayout, ini: Path, reglage) -> None:
        try:
            etat = reglages_correctif.lire(ini, reglage)
        except OSError:
            log.warning("Correctif : %s illisible", ini, exc_info=True)
            return
        libelle_txt, aide_txt = reglages_correctif.textes(reglage)
        if reglage.choix:
            ligne = QWidget()
            ligne.setStyleSheet("background: transparent;")
            h = QHBoxLayout(ligne)
            h.setContentsMargins(0, 4, 0, 4)
            h.setSpacing(12)
            libelle = QLabel(libelle_txt)
            libelle.setStyleSheet("color: #ffffff; font-size: 13px; background: transparent;")
            h.addWidget(libelle, stretch=1)
            choix = QComboBox()
            choix.setStyleSheet(themed(_COMBO_STYLE))
            choix.setAccessibleName(libelle_txt)
            for n in reglage.choix:
                choix.addItem(tr(reglage.zero) if n == 0 else reglage.format_choix.format(n), n)
            if etat.personnalise:
                # Une valeur posée à la main dans l'ini : la montrer telle
                # quelle plutôt que d'afficher un choix qui n'est pas le sien.
                choix.addItem(tr("{} (réglé à la main)").format(etat.valeur), etat.valeur)
            choix.setCurrentIndex(max(0, choix.findData(etat.valeur)))
            choix.currentIndexChanged.connect(
                lambda _i, c=choix, r=reglage: self._on_reglage(r, c.currentData(), c))
            h.addWidget(choix)
            layout.addWidget(ligne)
        else:
            ligne, bascule = toggle_row(libelle_txt, bool(etat.valeur))
            layout.addWidget(ligne)
            if etat.personnalise and reglage.ident == "touches_zqsd":
                # Des touches choisies à la main dans l'ini : le préréglage les
                # écraserait. On le dit, on n'y touche pas.
                bascule.setEnabled(False)
                self._note(layout, tr(
                    "Touches personnalisées dans d3d9.ini : le lanceur n'y touche pas."))
            elif etat.personnalise:
                # Quelques lignes du panneau allumées à la main : rien n'est
                # perdu à le dire, et l'interrupteur reste libre.
                self._note(layout, tr(
                    "Réglé en partie à la main dans d3d9.ini : l'activer allume tout le panneau."))
            bascule.toggled.connect(
                lambda coche, r=reglage, b=bascule: self._on_reglage(r, coche, b))
        aide = QLabel(aide_txt)
        aide.setFont(body_font(10))
        aide.setWordWrap(True)
        aide.setTextFormat(Qt.TextFormat.PlainText)
        aide.setStyleSheet("color: #8a8aaa; background: transparent; padding-bottom: 4px;")
        layout.addWidget(aide)

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

    def _on_reglage(self, reglage, valeur, widget) -> None:
        """Écrit AUSSITÔT, comme la langue : pas de bouton « Appliquer »."""
        if reglage.choix and valeur not in reglage.choix:
            return   # l'entrée « réglé à la main » : c'est déjà ce que porte le fichier
        try:
            reglages_correctif.ecrire(self._ini, reglage, valeur)
        except (OSError, ValueError):
            log.warning("Correctif : %s non écrit", reglage.ident, exc_info=True)
            # Remettre le contrôle sur ce que porte VRAIMENT le fichier.
            try:
                etat = reglages_correctif.lire(self._ini, reglage)
            except OSError:
                etat = None
            widget.blockSignals(True)
            if isinstance(widget, QComboBox):
                if etat is not None:
                    widget.setCurrentIndex(max(0, widget.findData(etat.valeur)))
            elif etat is not None:
                widget.setChecked(bool(etat.valeur))
            widget.blockSignals(False)
            if self._erreur is not None:
                self._erreur.setText(tr(
                    "Réglage non enregistré : le fichier d3d9.ini du jeu n'a pas "
                    "pu être modifié (jeu en cours, ou fichier en lecture seule)."))
                self._erreur.show()
            return
        if self._erreur is not None:
            self._erreur.hide()

    def _resynchroniser(self) -> None:
        courant = self.manager.game_language(self.game)
        for code, bouton in self._boutons.items():
            bouton.blockSignals(True)
            bouton.setChecked(code == courant)
            bouton.blockSignals(False)
