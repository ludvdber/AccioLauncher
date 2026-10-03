"""Les rubriques de la fenêtre de réglages qui ne règlent pas l'image.

Langue, touches, affichage verrouillé, manette, captures et fichiers. Classe
parente de `GameSettingsDialog`, sortie du même fichier le 2026-10-03 (1 228
lignes) : les méthodes sont celles d'origine, elles lisent les attributs posés
par la fenêtre. Les constantes de la fenêtre vivent ici aussi.
"""

import logging
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from src.core import captures, manette, reglages_correctif
from src.core.i18n import tr
from src.ui.editeur_touches import EditeurTouches
from src.ui.fonts import body_font, cinzel
from src.ui.styles import RADIO_STYLE
from src.ui.theme import themed
from src.ui.toggle_switch import ToggleSwitch
from src.ui.utils import open_local_path

log = logging.getLogger(__name__)

# Les mesures du cadre : `_ajuster_hauteur` les additionne, la construction les pose.
_LARGEUR = 590        # cinq onglets, et une ligne de réglage avec son « ? », ses pastilles et sa liste
_MARGES_H = 22 + 22   # contentsMargins gauche et droite de la fenêtre
_MARGE_HAUT, _MARGE_BAS = 20, 16
_ESPACE_TITRE = 14
_HAUTEUR_ONGLETS = 34
_ESPACE_ONGLETS = 16
_ESPACE_PIED = 8
_HAUTEUR_PIED = 32    # le bouton « Fermer »
# Part de l'écran que la fenêtre prend d'elle-même au plus : au-delà, elle
# défile (Ludo, 2026-10-01 : « pas évident quand elle prend tout l'écran »).
_PART_ECRAN = 0.8
_HAUTEUR_MIN_PAGE = 120

# (identifiant, libellé) dans l'ordre des onglets. L'image d'abord : c'est ce
# qu'on vient régler le plus souvent.
_ONGLETS = (
    ("image", "Image"),
    ("commandes", "Commandes"),
    ("jeu", "Jeu"),
    ("perfs", "Performances"),
    ("fichiers", "Fichiers"),
)

_ONGLET_STYLE = (
    "QPushButton { color: #8a8aaa; background: transparent; border: none;"
    " border-bottom: 2px solid rgba(255,255,255,0.06); padding: 6px 10px; }"
    "QPushButton:hover { color: #e8c547; }"
    "QPushButton:checked { color: #d6a72c; border-bottom: 2px solid #d6a72c; }"
)

# Repères de coût (Ludo, 2026-09-30) : vert faible, orange moyen, rouge extrême.
# Hors palette de maison, comme le filet des alertes : ce sont des signaux, et
# ils se lisent aussi sans la couleur (+, ++, +++).
_COULEURS_COUT = {1: "#6cc58a", 2: "#e8955a", 3: "#ec5f5f"}
_COULEUR_SE_VOIT = "#d6a72c"

_LIEN_STYLE = (
    "QPushButton { color: #d6a72c; background: transparent;"
    " border: none; text-align: left; padding: 4px 0px; }"
    "QPushButton:hover { color: #e8c547; text-decoration: underline; }"
    "QPushButton:disabled { color: #55556a; }"
)

# Les familles d'effets de « Qualité d'image », dans l'ordre d'affichage.
_GROUPES_EFFETS = (
    ("Contours", ("lissage", "nettete", "anticrenelage", "anticrenelage_transparence",
                  "surechantillonnage")),
    ("Textures", ("filtrage", "textures_lointaines", "feuillage_lointain")),
    ("Lumière et ombres", ("occlusion", "ombres_nettes", "halo", "rayons", "brouillard")),
    ("Couleurs", ("couleurs", "vivacite", "contraste")),
)
_RESSOURCES = {"GPU": "Carte graphique (GPU)", "CPU": "Processeur (CPU)", "RAM": "Mémoire (RAM)"}
_NIVEAUX = {1: "faible", 2: "moyenne", 3: "extrême"}

_GROUPE_STYLE = (
    "QPushButton { color: #d0d0e0; background: #141428; border: 1px solid #2a2a48;"
    " border-radius: 6px; padding: 7px 10px; text-align: left; }"
    "QPushButton:hover { border-color: #d6a72c; color: #e8c547; }"
    "QPushButton:checked { border-color: rgba(214,167,44,0.55); }"
)

_PREREGLAGE_STYLE = (
    "QPushButton { color: #b0b0c8; background: #141428; border: 1px solid #2a2a48;"
    " padding: 5px 8px; }"
    "QPushButton:hover { color: #e8c547; }"
    "QPushButton:checked { color: #0d0d1a; background: #d6a72c; border-color: #d6a72c; }"
)

# Réglages annoncés mais pas encore livrés. Ils sont ÉCRITS, pas résumés en
# « bientôt » : quelqu'un qui cherche la résolution doit reconnaître ce qu'il
# cherche, et comprendre que ce n'est pas lui qui n'a pas trouvé.
_A_VENIR = (
    "Résolution",
    "Qualité graphique",
    "Mode fenêtré / plein écran",
)



class RubriquesDuJeu:
    """Rubriques simples de `GameSettingsDialog` (voir le module)."""

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

        lr = self.game.langues
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

        for rang, langue in enumerate(proposables):
            radio = QRadioButton(langue.label)
            radio.setFont(body_font(12))
            radio.setCursor(Qt.CursorShape.PointingHandCursor)
            radio.setStyleSheet(themed(RADIO_STYLE))
            radio.setChecked(langue.code == courant)
            radio.toggled.connect(
                lambda coche, code=langue.code: self._on_langue(coche, code))
            self._groupe.addButton(radio)
            self._boutons[langue.code] = radio
            if rang:
                layout.addSpacing(6)
            layout.addWidget(radio)

    def _section_touches(self, layout: QVBoxLayout) -> None:
        """Chaque action de HP4 et sa touche, réglables une par une.

        Sous le préréglage : il couvre le cas le plus courant en un geste,
        l'éditeur tout le reste (gaucher, pavé numérique, souris à boutons).
        """
        layout.addWidget(self._titre_rubrique(tr("Touches une par une")))
        layout.addSpacing(4)
        self._note(layout, tr("Cliquez sur la touche d'une action, puis appuyez sur celle que vous "
                              "voulez, ou recliquez-la avec le bouton de souris voulu. Échap ou un "
                              "clic ailleurs annule."))
        layout.addSpacing(6)
        self._editeur = EditeurTouches(self._ini)
        self._editeur.modifie.connect(self._touches_modifiees)
        self._editeur.echec.connect(self._montrer_erreur)
        layout.addWidget(self._editeur)

    def _touches_modifiees(self) -> None:
        self._maj_preregle()
        self._apres_ecriture()

    def _maj_preregle(self) -> None:
        """L'interrupteur ZQSD suit le fichier : libre tant qu'aucune touche n'est
        choisie à l'unité, verrouillé (et la note le dit) sinon — il les écraserait."""
        bascule = self._controles.get("touches_zqsd")
        if bascule is None:
            return
        try:
            etat = reglages_correctif.lire(self._ini, reglages_correctif.REGLAGES["touches_zqsd"])
        except OSError:
            return
        bascule.blockSignals(True)
        bascule.setChecked(bool(etat.valeur))
        bascule.blockSignals(False)
        bascule.setEnabled(not etat.personnalise)
        if self._note_preregle is not None:
            self._note_preregle.setVisible(etat.personnalise)

    def _section_affichage(self, layout: QVBoxLayout) -> None:
        """Jeu sans réglage de correctif : la rubrique verrouillée, qui dit ce qui vient."""
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

    def _note(self, layout: QVBoxLayout, texte: str) -> None:
        note = QLabel(texte)
        note.setFont(body_font(11))
        note.setWordWrap(True)
        note.setTextFormat(Qt.TextFormat.PlainText)
        note.setStyleSheet("color: #8a8aaa; background: transparent;")
        layout.addWidget(note)

    def _section_manette(self, layout: QVBoxLayout) -> bool:
        """« Jouer à la manette » (HP5, HP6) : le choix que le jeu garde dans le registre.

        Deux voies, toutes deux voulues par Ludo (2026-09-27) : le menu du jeu, ou
        cet interrupteur — qui PRÉVIENT avant d'écrire (le rappel de l'appelant).
        """
        etat = manette.activee(self.game) if self._appliquer_manette is not None else None
        # Ce que le correctif règle de la manette (PlayStation, vibrations), sous
        # le même titre : quelqu'un qui cherche sa manette ne la cherche qu'une fois.
        du_correctif = [r for r in self._reglages if r.onglet == "manette"] \
            if self._correctif_actif() else []
        if etat is None and not du_correctif:
            return False
        layout.addWidget(self._titre_rubrique(tr("Manette")))
        layout.addSpacing(4)
        if etat is not None:
            bascule = ToggleSwitch(etat)
            self._bascule_manette = bascule
            bascule.toggled.connect(self._on_manette)
            # HP5 et HP6 (lu dans leurs exe, 2026-09-30) : au démarrage, un choix
            # « manette » sans manette vue retombe au clavier ET s'écrit ainsi.
            self._ligne(layout, tr("Jouer à la manette"), bascule, tr(
                "Le jeu garde ce choix dans le registre de Windows : le lanceur vous "
                "prévient avant de le modifier. Il se règle aussi dans les options du jeu. "
                "Branchez la manette avant de lancer le jeu : s'il ne la trouve pas au "
                "démarrage, il repasse au clavier."))
        for reglage in du_correctif:
            self._controle(layout, self._ini, reglage)
        return True

    def _on_manette(self, oui: bool) -> None:
        if self._appliquer_manette(oui):
            return
        # Refusé ou pas pris : l'interrupteur revient sur ce que porte VRAIMENT
        # le registre, comme la langue (règle 118).
        vrai = bool(manette.activee(self.game))
        self._bascule_manette.blockSignals(True)
        self._bascule_manette.setChecked(vrai)
        self._bascule_manette.blockSignals(False)

    def _section_captures(self, layout: QVBoxLayout) -> bool:
        """Le dossier des captures de CE jeu, hors de son dossier d'installation.

        Affichée si le jeu sait en prendre (touche déclarée au catalogue) ou si
        le dossier en contient déjà — un jeu désinstallé garde ses captures, et
        c'est justement là qu'on vient les chercher.
        """
        n = captures.nombre(self.game)
        # La touche du correctif se lit dans SON ini (seul le nouveau en a une) ;
        # celle d'un autre moteur, le catalogue la déclare.
        ini = reglages_correctif.chemin_ini(
            self.manager.config.install_path / Path(self.game.executable).parent)
        touche = reglages_correctif.touche_capture(ini) or self.game.touche_capture
        # Un jeu dont le catalogue déclare les captures a sa rubrique même sans
        # touche connue : sous l'ancien correctif, elle disparaissait sans un
        # mot, et Ludo cherchait le bouton annoncé (2026-09-27).
        if not (touche or n or self.game.captures):
            return False
        layout.addWidget(self._titre_rubrique(tr("Captures d'écran")))
        layout.addSpacing(8)
        if touche:
            self._note(layout, tr(
                "Touche {} en jeu. Les captures sont rangées hors du dossier du jeu : "
                "le désinstaller ne les efface pas.").format(touche))
            layout.addSpacing(4)
        elif not n:
            # Rien à ouvrir : un bouton vers un dossier vide ne servirait à rien.
            self._note(layout, tr(
                "La touche de capture arrive avec la prochaine version du correctif "
                "de ce jeu."))
            return True
        ligne = QWidget()
        ligne.setStyleSheet("background: transparent;")
        h = QHBoxLayout(ligne)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)
        ouvrir = QPushButton(tr("Ouvrir le dossier des captures"))
        ouvrir.setFont(body_font(12))
        ouvrir.setCursor(Qt.CursorShape.PointingHandCursor)
        ouvrir.setStyleSheet(themed(
            "QPushButton { color: #d6a72c; background: transparent;"
            " border: none; text-align: left; padding: 4px 0px; }"
            "QPushButton:hover { color: #e8c547; text-decoration: underline; }"
        ))
        ouvrir.clicked.connect(self._ouvrir_captures)
        h.addWidget(ouvrir)
        h.addStretch()
        self._compte_captures = QLabel("")
        self._compte_captures.setFont(body_font(11))
        self._compte_captures.setStyleSheet("color: #8a8aaa; background: transparent;")
        h.addWidget(self._compte_captures)
        layout.addWidget(ligne)
        self._afficher_compte(n)
        return True

    def _afficher_compte(self, n: int) -> None:
        # Rien quand il n'y en a pas : « 0 capture » ne dit rien d'utile.
        if self._compte_captures is None:
            return
        self._compte_captures.setText(
            "" if not n else tr("1 capture") if n == 1 else tr("{} captures").format(n))

    def _ouvrir_captures(self) -> None:
        """Range d'abord ce que le jeu a laissé chez lui, puis ouvre le dossier."""
        install = self.manager.config.install_path
        captures.ramasser(self.game, install)
        dossier = captures.dossier(self.game)
        try:
            dossier.mkdir(parents=True, exist_ok=True)
        except OSError:
            log.warning("Captures : %s impossible à créer", dossier, exc_info=True)
            return
        self._afficher_compte(len(captures.images(dossier)))
        open_local_path(str(dossier))

    def _section_fichiers(self, layout: QVBoxLayout) -> bool:
        """Actions qui n'étaient atteignables qu'au CLIC DROIT.

        « Gérer les versions » et « Vérifier / réparer » existaient déjà, mais
        seulement dans le menu contextuel — exactement le défaut qu'on vient de
        corriger pour la langue : une fonction qu'il faut deviner n'existe pas.
        Elles referment la fenêtre avant d'agir, sinon leur propre dialogue
        s'empilerait par-dessus celui-ci.
        """
        if not self._actions:
            return False
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
        return True

    def _lancer(self, rappel) -> None:
        self.accept()
        rappel()

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
