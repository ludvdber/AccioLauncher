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
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from src.core import captures, manette, reglages_correctif, reglages_graphiques, resolution_jeu
from src.core.i18n import tr
from src.ui.editeur_touches import EditeurTouches
from src.ui.fonts import body_font, cinzel
from src.ui.settings_panel import _COMBO_STYLE
from src.ui.styles import RADIO_STYLE
from src.ui.theme import themed
from src.ui.toggle_switch import ToggleSwitch
from src.ui.utils import liste_deroulante, open_local_path

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
        """Jeu sans réglage de correctif : la résolution si le catalogue dit où
        l'écrire (HP1, HP2), et ce qui vient, verrouillé."""
        reglable = self.game.resolution is not None
        layout.addWidget(self._titre_rubrique(tr("Affichage"), verrouille=not reglable))
        layout.addSpacing(8 if not reglable else 2)
        if reglable:
            self._ligne_resolution(layout)
        # Sous une rubrique active, des choix grisés sans « BIENTÔT » auraient
        # l'air de réglages cassés (règle 119) : on ne les annonce plus ici.
        for nom in (() if reglable else _A_VENIR):
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
                "Ces réglages viendront ici.") if not reglable else tr(
                "Réglez la résolution ici, pas dans le menu du jeu : ses options "
                "vidéo peuvent l'empêcher de redémarrer."))
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

    def _ligne_resolution(self, layout: QVBoxLayout) -> None:
        """La taille de l'image du jeu : la plus grande que l'écran permet, par défaut.

        Enregistrée dans la config du launcher, ÉCRITE dans l'ini au lancement
        (`resolution_jeu`) : le jeu, son menu vidéo ou un Alt+Entrée peuvent la
        changer, le lancement suivant remet celle-ci.
        """
        place = resolution_jeu.place_pour(self.game, self.manager.config)
        choix = liste_deroulante()
        choix.setStyleSheet(themed(_COMBO_STYLE))
        choix.setMinimumWidth(130)
        if place is not None:
            choix.addItem(tr("Remplir l'écran ({} × {})").format(*place), "")
        else:
            choix.addItem(tr("Remplir l'écran"), "")
        for taille in resolution_jeu.proposees(place):
            choix.addItem("{} × {}".format(*taille), resolution_jeu.ecrire(taille))
        courant = self.manager.config.resolution_jeu.get(self.game.id, "")
        if courant and choix.findData(courant) < 0:
            taille = resolution_jeu.lire(courant)
            if taille is not None:
                # Choisie sur un autre écran, plus grand : la montrer telle quelle,
                # le lancement repliera sur la place disponible tant qu'elle ne tient pas.
                choix.addItem(tr("{} × {} (plus grande que cet écran)").format(*taille), courant)
        choix.setCurrentIndex(max(0, choix.findData(courant)))
        choix.currentIndexChanged.connect(lambda _i, c=choix: self._on_resolution(c.currentData()))
        self._choix_resolution = choix
        self._ligne(layout, tr("Résolution"), choix, tr(
            "La taille de l'image du jeu. Par défaut, la plus grande dont la fenêtre tient à "
            "l'écran, barre de titre comprise, sans passer sous la barre des tâches. Une taille "
            "plus petite allège le travail de la carte graphique. Appliquée à chaque lancement, "
            "même si le menu du jeu ou Alt+Entrée l'a changée entre-temps."))

    def _on_resolution(self, valeur: str) -> None:
        resolutions = self.manager.config.resolution_jeu
        if valeur:
            resolutions[self.game.id] = valeur
        else:
            resolutions.pop(self.game.id, None)
        self.manager.config.save()

    def _section_graphiques(self, layout: QVBoxLayout, onglet: str) -> bool:
        """HP3 : les réglages graphiques rangés dans CET onglet (`reglages_graphiques`).

        Même présentation que le correctif (ligne, « ? », pastilles), écrite
        aussitôt dans `dgVoodoo.conf`. False si ce jeu n'en a pas.
        """
        conf = self._conf_graph
        reglages = reglages_graphiques.du_onglet(onglet)
        if conf is None or not reglages:
            return False
        if onglet == "image":
            layout.addWidget(self._titre_rubrique(tr("Image")))
            layout.addSpacing(4)
        for reglage in reglages:
            self._controle_graph(layout, conf, reglage)
        if onglet == "image":
            self._bouton_origine_graph(layout)
        return True

    def _controle_graph(self, layout: QVBoxLayout, conf: Path, reglage) -> None:
        try:
            etat = reglages_graphiques.lire(conf, reglage)
        except OSError:
            log.warning("Réglages graphiques : %s illisible", conf, exc_info=True)
            return
        libelle_txt, aide_txt = tr(reglage.libelle), tr(reglage.aide)
        if reglage.choix:
            controle = liste_deroulante()
            controle.setStyleSheet(themed(_COMBO_STYLE))
            controle.setMinimumWidth(130)
            noms = dict(reglage.noms_choix)
            for valeur in reglage.choix:
                controle.addItem(tr(reglage.zero) if valeur == reglage.choix[0]
                                 else tr(noms[valeur]), valeur)
            if etat.personnalise:
                controle.addItem(tr("{} (réglé à la main)").format(etat.valeur), etat.valeur)
            controle.setCurrentIndex(max(0, controle.findData(etat.valeur)))
            controle.currentIndexChanged.connect(
                lambda _i, c=controle, r=reglage: self._on_graph(r, c.currentData(), c))
        else:
            controle = ToggleSwitch(bool(etat.valeur))
            controle.toggled.connect(
                lambda coche, r=reglage, b=controle: self._on_graph(r, coche, b))
        self._controles_graph[reglage.ident] = controle
        self._ligne(layout, libelle_txt, controle, aide_txt, reglage)

    def _remettre_controle_graph(self, controle: QWidget, reglage) -> None:
        """Remet un contrôle sur ce que porte VRAIMENT le fichier."""
        try:
            etat = reglages_graphiques.lire(self._conf_graph, reglage)
        except OSError:
            return
        controle.blockSignals(True)
        if isinstance(controle, QComboBox):
            index = controle.findData(etat.valeur)
            if index < 0:
                controle.addItem(tr("{} (réglé à la main)").format(etat.valeur), etat.valeur)
                index = controle.count() - 1
            controle.setCurrentIndex(index)
        else:
            controle.setChecked(bool(etat.valeur))
        controle.blockSignals(False)

    def _on_graph(self, reglage, valeur, controle: QWidget) -> None:
        """Écrit AUSSITÔT, comme les réglages du correctif."""
        if reglage.choix and valeur not in reglage.choix:
            return   # l'entrée « réglé à la main » : c'est déjà ce que porte le fichier
        try:
            reglages_graphiques.ecrire(self._conf_graph, reglage, valeur)
        except (OSError, ValueError):
            log.warning("Réglages graphiques : %s non écrit", reglage.ident, exc_info=True)
            self._remettre_controle_graph(controle, reglage)
            self._montrer_erreur(tr(
                "Réglage non enregistré : le fichier des réglages graphiques du jeu "
                "n'a pas pu être modifié (jeu en cours, ou fichier en lecture seule)."))
            return
        if self._bouton_reset is not None:
            self._bouton_reset.setEnabled(reglages_graphiques.a_une_origine(self._conf_graph))
        if not self._erreur.isHidden():
            self._erreur.hide()
            self._ajuster_hauteur()

    def _bouton_origine_graph(self, layout: QVBoxLayout) -> None:
        """« Rétablir les réglages d'origine » : ceux du fichier tel qu'installé."""
        bouton = QPushButton(tr("Rétablir les réglages d'origine"))
        bouton.setFont(body_font(12))
        bouton.setStyleSheet(themed(_LIEN_STYLE))
        bouton.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton.setEnabled(reglages_graphiques.a_une_origine(self._conf_graph))
        bouton.setToolTip(tr("Remet image et performances comme à l'installation du jeu."))
        bouton.clicked.connect(self._remettre_origine_graph)
        self._bouton_reset = bouton
        layout.addSpacing(8)
        ligne = QHBoxLayout()
        ligne.addWidget(bouton)
        ligne.addStretch()
        layout.addLayout(ligne)

    def _remettre_origine_graph(self) -> None:
        try:
            reglages_graphiques.remettre_origine(self._conf_graph)
        except OSError:
            log.warning("Réglages graphiques : remise à l'origine impossible", exc_info=True)
            self._montrer_erreur(tr(
                "Réglage non enregistré : le fichier des réglages graphiques du jeu "
                "n'a pas pu être modifié (jeu en cours, ou fichier en lecture seule)."))
            return
        for ident, controle in self._controles_graph.items():
            self._remettre_controle_graph(controle, reglages_graphiques.REGLAGES[ident])

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
