"""Réglages d'UN jeu : langue, et pour HP4-HP6 les réglages confirmés de leur correctif PC.

Pourquoi une FENÊTRE et pas le menu qu'il y avait ici d'abord : un menu est un
choix qu'on prend et qui se referme, alors que les réglages d'un jeu vont
s'étoffer — résolution, qualité, mode fenêtré. Un menu qui grandit devient une
liste à dérouler ; une fenêtre, elle, a des rubriques, de la place pour
expliquer, et sait montrer ce qui n'est pas encore là.

La rubrique « Affichage » est justement là, verrouillée. Annoncer ce qui vient
n'est pas une promesse en l'air : c'est la moitié de la réponse à « pourquoi le
lanceur ne me laisse pas régler la résolution ».

Des ONGLETS depuis le 2026-09-28 : une seule colonne était « hyper grande et
confuse » (Ludo) — qui voulait l'image traversait la réinstallation, qui voulait
son clavier traversait l'anticrénelage. Chaque réglage du correctif porte son
onglet (`Reglage.onglet`) ; un onglet sans rien à montrer n'apparaît pas.
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
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.core import captures, manette, reglages_correctif
from src.core.game_data import GameData
from src.core.game_manager import GameManager
from src.core.i18n import tr
from src.ui.fonts import body_font, cinzel
from src.ui.settings_panel import _COMBO_STYLE
from src.ui.styles import RADIO_STYLE
from src.ui.theme import themed
from src.ui.toggle_switch import toggle_row
from src.ui.utils import open_local_path, zone_defilable

log = logging.getLogger(__name__)

# Les mesures du cadre : `_ajuster_hauteur` les additionne, la construction les pose.
_LARGEUR = 540        # cinq onglets côte à côte, « Performances » compris
_MARGES_H = 22 + 22   # contentsMargins gauche et droite de la fenêtre
_MARGE_HAUT, _MARGE_BAS = 20, 16
_ESPACE_TITRE = 14
_HAUTEUR_ONGLETS = 34
_ESPACE_ONGLETS = 16
_ESPACE_PIED = 8
_HAUTEUR_PIED = 32    # le bouton « Fermer »

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

# Repères de coût : plus le niveau monte, plus la pastille chauffe. Hors palette
# de maison, comme le filet des alertes : ce sont des avertissements.
_COULEURS_COUT = {1: "#8a8aaa", 2: "#d9b45a", 3: "#e8955a"}

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
                 parent: QWidget | None = None, appliquer_manette=None) -> None:
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
        # (oui) -> bool : prévient, écrit, dit si c'est pris. None = pas de rubrique.
        self._appliquer_manette = appliquer_manette
        self._bascule_manette = None
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
        self._compte_captures: QLabel | None = None

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
        # La page la plus haute fixe la hauteur : changer d'onglet ne fait pas
        # sauter la fenêtre.
        voulus = []
        for contenu in self._contenus:
            corps = contenu.layout()
            corps.activate()
            voulus.append(corps.totalHeightForWidth(largeur) if corps.hasHeightForWidth()
                          else corps.sizeHint().height())
        voulu = max(voulus, default=120)
        pied = sum(lbl.heightForWidth(largeur) for lbl in (self._pied_notes, self._erreur)
                   if not lbl.isHidden())
        cadre = (_MARGE_HAUT + self._titre.heightForWidth(largeur) + _ESPACE_TITRE
                 + (_HAUTEUR_ONGLETS + _ESPACE_ONGLETS if not self._barre_onglets.isHidden() else 0)
                 + pied + _ESPACE_PIED + _HAUTEUR_PIED + _MARGE_BAS)
        ecran = self.screen() or QGuiApplication.primaryScreen()
        # La barre de titre de Windows et un peu d'air au-dessus de la barre des tâches.
        plafond = ecran.availableGeometry().height() - cadre - 60 if ecran is not None else voulu
        for contenu, v in zip(self._contenus, voulus):
            if v > plafond:
                # La barre de défilement prend sa place à droite : le texte s'en écarte.
                contenu.layout().setContentsMargins(0, 0, 18, 0)
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

        # Une rangée d'onglets, puis leurs pages. Chaque page défile seule, le
        # titre, les onglets et « Fermer » restent (règle 52 : une page qui peut
        # déborder doit pouvoir défiler — les huit réglages de HP4 dépassaient
        # un écran de 768 px).
        self._barre_onglets = QWidget()
        self._barre_onglets.setStyleSheet("background: transparent;")
        barre = QHBoxLayout(self._barre_onglets)
        barre.setContentsMargins(0, 0, 0, 0)
        barre.setSpacing(2)
        self._groupe_onglets = QButtonGroup(self)
        self._groupe_onglets.setExclusive(True)
        self._defile = QStackedWidget()
        self._defile.setStyleSheet("background: transparent;")
        self._contenus: list[QWidget] = []
        self._onglets: dict[str, QPushButton] = {}
        for ident, libelle in _ONGLETS:
            contenu = QWidget()
            contenu.setStyleSheet("background: transparent;")
            corps = QVBoxLayout(contenu)
            corps.setContentsMargins(0, 0, 0, 0)
            corps.setSpacing(0)
            if not self._remplir(ident, corps):
                contenu.deleteLater()
                continue
            corps.addStretch()
            bouton = QPushButton(tr(libelle))
            bouton.setCheckable(True)
            bouton.setFont(cinzel(10, bold=True))
            bouton.setCursor(Qt.CursorShape.PointingHandCursor)
            bouton.setStyleSheet(themed(_ONGLET_STYLE))
            rang = len(self._contenus)
            bouton.clicked.connect(lambda _c=False, r=rang: self._defile.setCurrentIndex(r))
            self._groupe_onglets.addButton(bouton)
            barre.addWidget(bouton)
            self._onglets[ident] = bouton
            self._contenus.append(contenu)
            self._defile.addWidget(zone_defilable(contenu))
        barre.addStretch()
        if self._onglets:
            next(iter(self._onglets.values())).setChecked(True)
        # Un seul onglet : la rangée ne dirait rien.
        self._barre_onglets.setVisible(len(self._onglets) > 1)
        layout.addWidget(self._barre_onglets)
        layout.addSpacing(_ESPACE_ONGLETS if len(self._onglets) > 1 else 0)
        layout.addWidget(self._defile)

        # Sous les pages, visibles quel que soit l'onglet : l'échec d'écriture
        # et le rappel que tout vaut au prochain lancement.
        self._pied_notes = QLabel("")
        self._pied_notes.setFont(body_font(10))
        self._pied_notes.setWordWrap(True)
        self._pied_notes.setTextFormat(Qt.TextFormat.PlainText)
        self._pied_notes.setStyleSheet("color: #8a8aaa; background: transparent; padding-top: 6px;")
        if self._correctif_actif():
            self._pied_notes.setText(tr("Pris en compte au prochain lancement du jeu."))
        else:
            self._pied_notes.hide()
        layout.addWidget(self._pied_notes)
        self._erreur = QLabel("")
        self._erreur.setFont(body_font(11))
        self._erreur.setWordWrap(True)
        self._erreur.setTextFormat(Qt.TextFormat.PlainText)
        self._erreur.setStyleSheet("color: #e8955a; background: transparent;")
        self._erreur.hide()
        layout.addWidget(self._erreur)
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

    # ── Les onglets ──

    def _correctif_actif(self) -> bool:
        """Le jeu déclare des réglages ET porte le nouveau correctif, qui les lira."""
        ini = self._ini
        return bool(self._reglages) and ini is not None and ini.is_file() \
            and reglages_correctif.est_nouveau_correctif(ini)

    def _remplir(self, onglet: str, corps: QVBoxLayout) -> bool:
        """Pose le contenu d'un onglet ; False s'il n'a rien à montrer."""
        if onglet == "image":
            if not self._reglages:
                self._section_affichage(corps)
                return True
            self._section_correctif(corps, "image", avertir=True)
            corps.addSpacing(10)
            corps.addWidget(self._titre_rubrique(tr("Plus tard"), verrouille=True))
            corps.addSpacing(4)
            # Une ligne et non une liste de boutons grisés : ce qui vient se lit,
            # sans prendre la hauteur des réglages actifs.
            bientot = QLabel(" · ".join(tr(nom) for nom in reglages_correctif.A_VENIR))
            bientot.setFont(body_font(11))
            bientot.setWordWrap(True)
            bientot.setTextFormat(Qt.TextFormat.PlainText)
            bientot.setStyleSheet("color: #6a6a80; background: transparent;")
            corps.addWidget(bientot)
            return True
        if onglet == "commandes":
            a_des_touches = self._section_correctif(corps, "commandes")
            if a_des_touches:
                corps.addSpacing(18)
            return self._section_manette(corps) or a_des_touches
        if onglet == "jeu":
            rempli = False
            # La langue n'a sa rubrique que si elle se RÈGLE : jeu qui en déclare,
            # et registre atteignable pour ceux qui la lisent là.
            if self.manager.game_language(self.game) is not None:
                self._section_langue(corps)
                corps.addSpacing(20)
                rempli = True
            if self._section_correctif(corps, "jeu"):
                corps.addSpacing(18)
                rempli = True
            return self._section_captures(corps) or rempli
        if onglet == "perfs":
            return self._section_correctif(corps, "perfs")
        return self._section_fichiers(corps)

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

    def _section_correctif(self, layout: QVBoxLayout, onglet: str, avertir: bool = False) -> bool:
        """Les réglages du correctif PC (HP4-HP6) rangés dans CET onglet ; False s'il n'y en a pas.

        Trois cas, et chacun le DIT : jeu absent, ancien correctif (rien ne
        lirait ces clés), nouveau correctif.
        """
        reglages = [r for r in self._reglages if r.onglet == onglet]
        if not reglages:
            return False
        ini = self._ini
        if ini is None or not ini.is_file():
            self._note(layout, tr("Installez le jeu pour régler son correctif."))
            return True
        if not reglages_correctif.est_nouveau_correctif(ini):
            self._note(layout, tr(
                "Ces réglages arrivent avec la prochaine version du correctif "
                "de ce jeu."))
            return True
        if avertir:
            # Demandé par Ludo (2026-09-28) : dire que tout se règle, mais à ses
            # risques, et DIRIGER — ce qui coûte, et ce qui se voit vraiment.
            avis = QLabel(tr(
                "Réglables à vos risques : un réglage exigeant peut faire ramer ou "
                "chauffer un PC modeste. GPU, CPU et RAM disent ce qu'il demande à la "
                "carte graphique, au processeur ou à la mémoire (+ un peu, +++ "
                "beaucoup) ; « Se voit » marque ce qui change vraiment l'image."))
            avis.setFont(body_font(10))
            avis.setWordWrap(True)
            avis.setTextFormat(Qt.TextFormat.PlainText)
            avis.setStyleSheet("color: #e8955a; background: transparent; padding-bottom: 8px;")
            layout.addWidget(avis)
        for reglage in reglages:
            self._controle(layout, ini, reglage)
        return True

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
                choix.addItem(reglages_correctif.libelle_choix(reglage, n), n)
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
        self._reperes(layout, reglage)
        aide = QLabel(aide_txt)
        aide.setFont(body_font(10))
        aide.setWordWrap(True)
        aide.setTextFormat(Qt.TextFormat.PlainText)
        aide.setStyleSheet("color: #8a8aaa; background: transparent; padding-bottom: 4px;")
        layout.addWidget(aide)

    def _reperes(self, layout: QVBoxLayout, reglage) -> None:
        """Pastilles sous le réglage : ce qu'il coûte (« GPU +++ ») et s'il se voit.

        Du TEXTE, pas des pictogrammes : Cinzel n'a pas les symboles, et Windows
        les rendrait en emoji couleur (règles 59 et 60).
        """
        pastilles = [(f"{ressource} {'+' * niveau}", _COULEURS_COUT.get(niveau, "#8a8aaa"))
                     for ressource, niveau in reglage.cout]
        if reglage.se_voit:
            pastilles.append((tr("Se voit"), "#d6a72c"))
        if not pastilles:
            return
        ligne = QWidget()
        ligne.setStyleSheet("background: transparent;")
        h = QHBoxLayout(ligne)
        h.setContentsMargins(0, 0, 0, 2)
        h.setSpacing(6)
        for texte, couleur in pastilles:
            pastille = QLabel(texte)
            pastille.setFont(body_font(9))
            pastille.setTextFormat(Qt.TextFormat.PlainText)
            pastille.setStyleSheet(themed(
                f"color: {couleur}; background: transparent; border: 1px solid {couleur};"
                " border-radius: 3px; padding: 0px 6px;"))
            h.addWidget(pastille)
        h.addStretch()
        layout.addWidget(ligne)

    def _section_manette(self, layout: QVBoxLayout) -> bool:
        """« Jouer à la manette » (HP5, HP6) : le choix que le jeu garde dans le registre.

        Deux voies, toutes deux voulues par Ludo (2026-09-27) : le menu du jeu, ou
        cet interrupteur — qui PRÉVIENT avant d'écrire (le rappel de l'appelant).
        """
        etat = manette.activee(self.game)
        if etat is None or self._appliquer_manette is None:
            return False
        layout.addWidget(self._titre_rubrique(tr("Manette")))
        layout.addSpacing(8)
        ligne, bascule = toggle_row(tr("Jouer à la manette"), etat)
        layout.addWidget(ligne)
        self._bascule_manette = bascule
        bascule.toggled.connect(self._on_manette)
        self._note(layout, tr(
            "Le jeu garde ce choix dans le registre de Windows : le lanceur vous "
            "prévient avant de le modifier. Il se règle aussi dans les options du jeu."))
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
            self._erreur.setText(tr(
                "Réglage non enregistré : le fichier d3d9.ini du jeu n'a pas "
                "pu être modifié (jeu en cours, ou fichier en lecture seule)."))
            if self._erreur.isHidden():
                self._erreur.show()
                self._ajuster_hauteur()   # le message ne doit rien recouvrir
            return
        if not self._erreur.isHidden():
            self._erreur.hide()
            self._ajuster_hauteur()

    def _resynchroniser(self) -> None:
        courant = self.manager.game_language(self.game)
        for code, bouton in self._boutons.items():
            bouton.blockSignals(True)
            bouton.setChecked(code == courant)
            bouton.blockSignals(False)
