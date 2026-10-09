"""Les rubriques de la fenêtre de réglages qui ne règlent pas l'image.

Langue, touches, affichage verrouillé, manette, captures et fichiers. Classe
parente de `GameSettingsDialog`, sortie du même fichier le 2026-10-03 (1 228
lignes) : les méthodes sont celles d'origine, elles lisent les attributs posés
par la fenêtre. Les constantes de la fenêtre vivent ici aussi.

Refaites en cartes le 2026-10-09 (maquette « Réglages du jeu ») : chaque
rubrique est un surtitre doré et une carte de lignes, comme les Paramètres.
"""

import logging
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from src.core import captures, manette, reglages_correctif, reglages_graphiques, resolution_jeu
from src.core.i18n import tr
from src.ui.composants import ENCRE_DOUCE, Carte, LigneReglage, bouton, petit_titre, police, surtitre
from src.ui.editeur_touches import EditeurTouches
from src.ui.fonts import body_font
from src.ui.icon_button import pixmap_icone
from src.ui.styles import RADIO_STYLE
from src.ui.theme import current as current_theme, themed
from src.ui.toggle_switch import ToggleSwitch
from src.ui.utils import liste_deroulante, open_local_path

log = logging.getLogger(__name__)

# Les rubriques, dans l'ordre du rail : (identifiant, libellé, pictogramme).
# L'image d'abord : c'est ce qu'on vient régler le plus souvent. Les fichiers
# ne sont plus une rubrique : leurs actions vivent au bas du rail, visibles
# de partout (un onglet entier servait à quelques liens).
_ONGLETS = (
    ("image", "Image", "ecran"),
    ("commandes", "Commandes", "clavier"),
    ("jeu", "Jeu", "drapeau"),
    ("perfs", "Performances", "jauge"),
)

# Repères de coût (Ludo, 2026-09-30) : vert faible, orange moyen, rouge extrême.
# Hors palette de maison, comme le filet des alertes : ce sont des signaux, et
# ils se lisent aussi sans la couleur (un, deux ou trois points allumés).
_COULEURS_COUT = {1: "#6cc58a", 2: "#e8955a", 3: "#ec5f5f"}
_COULEUR_SE_VOIT = "#d6a72c"
# Ce qu'un réglage a perdu d'effet, dit sous son nom : ambre, pas rouge.
_COULEUR_NOTE = "#c9954a"

_LIEN_STYLE = (
    "QPushButton { color: #d6a72c; background: transparent;"
    " border: none; text-align: left; padding: 4px 0px; }"
    "QPushButton:hover { color: #e8c547; text-decoration: underline; }"
    "QPushButton:disabled { color: #55556a; }"
)

# Une liste de la page : plus basse et plus sobre que celle des Paramètres,
# elle s'aligne en colonne avec les interrupteurs.
_LISTE_STYLE = (
    "QComboBox { background: #15152a; color: #e4e2ef; border: 1px solid rgba(255,255,255,0.13);"
    " border-radius: 6px; padding: 3px 10px; min-height: 22px; }"
    "QComboBox:hover { border-color: rgba(214,167,44,0.55); }"
    "QComboBox:disabled { color: #6f6d8e; }"
    "QComboBox[focusClavier=\"true\"]:focus { border: 2px solid #d6a72c; padding: 2px 9px; }"
    "QComboBox::drop-down { border: none; width: 18px; }"
    "QComboBox QAbstractItemView { background: #15152a; color: #e4e2ef; outline: none;"
    " selection-background-color: rgba(214, 167, 44, 0.30); selection-color: #f0d060; }"
    "QComboBox QAbstractItemView::item { padding: 4px 8px; }"
    "QComboBox QAbstractItemView::item:selected { background: rgba(214, 167, 44, 0.30);"
    " color: #f0d060; }"
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
        """Le surtitre doré d'une rubrique ; « BIENTÔT » à côté si elle est verrouillée."""
        ligne = QWidget()
        ligne.setStyleSheet("background: transparent;")
        h = QHBoxLayout(ligne)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        lbl = surtitre(texte)
        if verrouille:
            lbl.setStyleSheet("color: #6a6a80; background: transparent;")
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

    @staticmethod
    def _section(corps: QVBoxLayout, entete: QWidget | None, contenu: QWidget) -> None:
        """Un surtitre puis son contenu ; 26 px d'air avec la rubrique d'avant."""
        if corps.count():
            corps.addSpacing(26)
        if entete is not None:
            corps.addWidget(entete)
            corps.addSpacing(10)
        corps.addWidget(contenu)

    def _section_langue(self, corps: QVBoxLayout) -> None:
        lr = self.game.langues
        courant = self.manager.game_language(self.game)
        proposables = self.manager.langues_disponibles(self.game) if lr else ()
        carte = Carte()
        if len(proposables) < 2:
            # Une seule langue sur le disque : le DIRE. Un choix unique déjà
            # coché laisse croire à un réglage cassé — le registre ne fait que
            # sélectionner, les fichiers viennent du disque d'origine.
            carte.ajouter(LigneReglage(
                tr("Ce jeu n'est installé que dans une seule langue."),
                tr("Le lanceur ne peut que sélectionner une langue déjà présente "
                   "sur le disque, pas la télécharger.")))
            self._section(corps, self._titre_rubrique(tr("Langue du jeu")), carte)
            return
        for langue in proposables:
            radio = QRadioButton(langue.label)
            radio.setFont(police(14))
            radio.setCursor(Qt.CursorShape.PointingHandCursor)
            radio.setStyleSheet(themed(RADIO_STYLE))
            radio.setChecked(langue.code == courant)
            radio.toggled.connect(
                lambda coche, code=langue.code: self._on_langue(coche, code))
            self._groupe.addButton(radio)
            self._boutons[langue.code] = radio
            ligne = QWidget()
            ligne.setStyleSheet("background: transparent;")
            h = QHBoxLayout(ligne)
            h.setContentsMargins(20, 11, 20, 11)
            h.addWidget(radio)
            carte.ajouter(ligne)
        self._section(corps, self._titre_rubrique(tr("Langue du jeu")), carte)

    def _section_touches(self, corps: QVBoxLayout) -> None:
        """Chaque action de HP4 et sa touche, réglables une par une.

        Sous la disposition : elle couvre le cas le plus courant en un geste,
        l'éditeur tout le reste (gaucher, pavé numérique, souris à boutons).
        """
        self._editeur = EditeurTouches(self._ini)
        self._editeur.modifie.connect(self._touches_modifiees)
        self._editeur.echec.connect(self._montrer_erreur)
        entete = QWidget()
        entete.setStyleSheet("background: transparent;")
        h = QHBoxLayout(entete)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(surtitre(tr("Touches une par une")))
        h.addStretch()
        h.addWidget(self._editeur.tout)
        bloc = QWidget()
        bloc.setStyleSheet("background: transparent;")
        v = QVBoxLayout(bloc)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        aide = QLabel(tr("Cliquez sur la touche d'une action, puis appuyez sur celle que vous "
                         "voulez, ou recliquez-la avec le bouton de souris voulu. Échap ou un "
                         "clic ailleurs annule."))
        aide.setTextFormat(Qt.TextFormat.PlainText)
        aide.setWordWrap(True)
        aide.setFont(police(13))
        aide.setStyleSheet(f"color: {ENCRE_DOUCE}; background: transparent;")
        v.addWidget(aide)
        v.addWidget(self._editeur)
        self._section(corps, entete, bloc)

    def _touches_modifiees(self) -> None:
        self._maj_preregle()
        self._apres_ecriture()

    def _maj_preregle(self) -> None:
        """La disposition suit le fichier : libre tant qu'aucune touche n'est
        choisie à l'unité, verrouillée (et la note le dit) sinon — elle les écraserait."""
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

    def _section_affichage(self, corps: QVBoxLayout) -> None:
        """Jeu sans réglage de correctif : la résolution si le catalogue dit où
        l'écrire (HP1, HP2), et ce qui vient, verrouillé."""
        reglable = self.game.resolution is not None
        carte = Carte()
        if reglable:
            self._ligne_resolution(carte)
        # Sous une rubrique active, des choix grisés sans « BIENTÔT » auraient
        # l'air de réglages cassés (règle 119) : on ne les annonce plus ici.
        for nom in (() if reglable else _A_VENIR):
            item = QRadioButton(tr(nom))
            item.setFont(police(14))
            item.setEnabled(False)
            item.setStyleSheet(
                "QRadioButton { color: #55556a; background: transparent; }")
            ligne = QWidget()
            ligne.setStyleSheet("background: transparent;")
            h = QHBoxLayout(ligne)
            h.setContentsMargins(20, 11, 20, 11)
            h.addWidget(item)
            carte.ajouter(ligne)
        self._egaliser(carte)
        self._section(corps, self._titre_rubrique(tr("Affichage"), verrouille=not reglable), carte)
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
            note.setFont(police(13))
            note.setWordWrap(True)
            note.setTextFormat(Qt.TextFormat.PlainText)
            note.setStyleSheet("color: #e8955a; background: transparent;")
            corps.addSpacing(10)
            corps.addWidget(note)

    def _ligne_resolution(self, carte: Carte) -> None:
        """La taille de l'image du jeu : la plus grande que l'écran permet, par défaut.

        Enregistrée dans la config du launcher, ÉCRITE dans l'ini au lancement
        (`resolution_jeu`) : le jeu, son menu vidéo ou un Alt+Entrée peuvent la
        changer, le lancement suivant remet celle-ci.
        """
        place = resolution_jeu.place_pour(self.game, self.manager.config)
        choix = self._liste()
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
        carte.ajouter(self._ligne(tr("Résolution"), choix, tr(
            "La taille de l'image du jeu. Par défaut, la plus grande dont la fenêtre tient à "
            "l'écran, barre de titre comprise, sans passer sous la barre des tâches. Une taille "
            "plus petite allège le travail de la carte graphique. Appliquée à chaque lancement, "
            "même si le menu du jeu ou Alt+Entrée l'a changée entre-temps.")))

    def _on_resolution(self, valeur: str) -> None:
        resolutions = self.manager.config.resolution_jeu
        if valeur:
            resolutions[self.game.id] = valeur
        else:
            resolutions.pop(self.game.id, None)
        self.manager.config.save()

    def _liste(self) -> QComboBox:
        choix = liste_deroulante()
        choix.setFont(police(13))
        choix.setCursor(Qt.CursorShape.PointingHandCursor)
        choix.setStyleSheet(themed(_LISTE_STYLE))
        return choix

    def _section_graphiques(self, corps: QVBoxLayout, onglet: str) -> bool:
        """HP3 : les réglages graphiques rangés dans CET onglet (`reglages_graphiques`).

        Même présentation que le correctif (ligne, « ? », repères), écrite
        aussitôt dans le fichier de son traducteur. False si ce jeu n'en a pas.
        """
        conf = self._conf_graph
        reglages = reglages_graphiques.du_onglet(onglet)
        if conf is None or not reglages:
            return False
        carte = self._carte_effets() if onglet == "image" else Carte()
        for reglage in reglages:
            self._controle_graph(carte, conf, reglage)
        self._egaliser(carte)
        if onglet == "image":
            self._section(corps, self._entete_effets(tr("Qualité d'image")), carte)
            self._bouton_origine_graph()
        else:
            self._section(corps, None, carte)
        return True

    def _controle_graph(self, carte, conf: Path, reglage) -> None:
        try:
            etat = reglages_graphiques.lire(conf, reglage)
        except OSError:
            log.warning("Réglages graphiques : %s illisible", conf, exc_info=True)
            return
        libelle_txt, aide_txt = tr(reglage.libelle), tr(reglage.aide)
        if reglage.choix:
            controle = self._liste()
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
        carte.ajouter(self._ligne(libelle_txt, controle, aide_txt, reglage))

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

    def _bouton_origine_graph(self) -> None:
        """« Rétablir les réglages d'origine » : ceux du fichier tel qu'installé."""
        btn = self._nouveau_bouton_reset()
        btn.setEnabled(reglages_graphiques.a_une_origine(self._conf_graph))
        btn.setToolTip(tr("Remet image et performances comme à l'installation du jeu."))
        btn.clicked.connect(self._remettre_origine_graph)

    def _nouveau_bouton_reset(self) -> QPushButton:
        """Le bouton du pied de page : bordé comme un vrai bouton, jamais un lien
        gris qu'on croirait désactivé (critique de la maquette)."""
        btn = bouton(tr("Rétablir les réglages d'origine"))
        btn.setIcon(QIcon(pixmap_icone("replay", 18, QColor(current_theme().accent))))
        btn.setAutoDefault(False)
        self._bouton_reset = btn
        return btn

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

    def _note(self, corps: QVBoxLayout, texte: str, entete: QWidget | None = None) -> None:
        """Une phrase seule dans une carte : ce que la rubrique ne peut pas encore faire."""
        carte = Carte()
        lbl = QLabel(texte)
        lbl.setFont(police(13))
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.TextFormat.PlainText)
        lbl.setStyleSheet(f"color: {ENCRE_DOUCE}; background: transparent;")
        lbl.setContentsMargins(20, 14, 20, 14)
        carte.ajouter(lbl)
        self._section(corps, entete, carte)

    def _section_manette(self, corps: QVBoxLayout) -> bool:
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
        carte = Carte()
        if etat is not None:
            bascule = ToggleSwitch(etat)
            self._bascule_manette = bascule
            bascule.toggled.connect(self._on_manette)
            # HP5 et HP6 (lu dans leurs exe, 2026-09-30) : au démarrage, un choix
            # « manette » sans manette vue retombe au clavier ET s'écrit ainsi.
            carte.ajouter(self._ligne(tr("Jouer à la manette"), bascule, tr(
                "Le jeu garde ce choix dans le registre de Windows : le lanceur vous "
                "prévient avant de le modifier. Il se règle aussi dans les options du jeu. "
                "Branchez la manette avant de lancer le jeu : s'il ne la trouve pas au "
                "démarrage, il repasse au clavier.")))
        for reglage in du_correctif:
            self._controle(carte, self._ini, reglage)
        self._egaliser(carte)
        self._section(corps, self._titre_rubrique(tr("Manette")), carte)
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

    def _section_captures(self, corps: QVBoxLayout) -> bool:
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
        entete = self._titre_rubrique(tr("Captures d'écran"))
        if not touche and not n:
            # Rien à ouvrir : un bouton vers un dossier vide ne servirait à rien.
            self._note(corps, tr(
                "La touche de capture arrive avec la prochaine version du correctif "
                "de ce jeu."), entete)
            return True
        ouvrir = bouton(tr("Ouvrir le dossier des captures"))
        ouvrir.setAutoDefault(False)
        ouvrir.clicked.connect(self._ouvrir_captures)
        self._compte_captures = QLabel("")
        self._compte_captures.setFont(police(13))
        self._compte_captures.setStyleSheet(f"color: {ENCRE_DOUCE}; background: transparent;")
        description = tr(
            "Touche {} en jeu. Les captures sont rangées hors du dossier du jeu : "
            "le désinstaller ne les efface pas.").format(touche) if touche else ""
        carte = Carte()
        carte.ajouter(LigneReglage(tr("Captures d'écran"), description,
                                   self._compte_captures, ouvrir))
        self._section(corps, entete, carte)
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

    def _actions_du_rail(self, colonne: QVBoxLayout) -> None:
        """Actions qui n'étaient atteignables qu'au CLIC DROIT, au bas du rail.

        « Gérer les versions » et « Vérifier / réparer » existaient déjà, mais
        seulement dans le menu contextuel — exactement le défaut qu'on vient de
        corriger pour la langue : une fonction qu'il faut deviner n'existe pas.
        Elles referment la fenêtre avant d'agir, sinon leur propre dialogue
        s'empilerait par-dessus celui-ci.
        """
        if not self._actions:
            return
        colonne.addWidget(petit_titre(tr("Fichiers du jeu")))
        colonne.addSpacing(6)
        for libelle, rappel in self._actions:
            btn = QPushButton(libelle)
            btn.setFont(police(13))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(themed(
                "QPushButton { color: #c8c6dc; background: transparent;"
                " border: none; text-align: left; padding: 6px 0px; }"
                "QPushButton:hover { color: #e8c547; }"
                "QPushButton[focusClavier=\"true\"]:focus { color: #e8c547; }"
            ))
            btn.setAutoDefault(False)
            btn.clicked.connect(lambda _c=False, r=rappel: self._lancer(r))
            colonne.addWidget(btn)

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
        for code, bouton_ in self._boutons.items():
            bouton_.blockSignals(True)
            bouton_.setChecked(code == courant)
            bouton_.blockSignals(False)
