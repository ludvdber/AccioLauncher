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

import html
import logging
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
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
from src.ui.editeur_touches import EditeurTouches
from src.ui.fonts import body_font, cinzel
from src.ui.settings_panel import _COMBO_STYLE
from src.ui.styles import RADIO_STYLE
from src.ui.theme import themed
from src.ui.toggle_switch import ToggleSwitch
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
        # Le contrôle de chaque réglage du correctif, par identifiant : la remise
        # à l'origine les remet sur ce que porte le fichier, sans rebâtir la page.
        self._controles: dict[str, QWidget] = {}
        # Le bloc entier de chaque réglage (ligne, pastilles, aide) : grisé quand
        # un autre réglage, éteint, lui retire tout effet.
        self._blocs: dict[str, QWidget] = {}
        self._bouton_reset: QPushButton | None = None
        # L'éditeur de touches (HP4) et la note sous le préréglage ZQSD, que
        # l'éditeur fait apparaître dès qu'une touche est choisie à l'unité.
        self._editeur: EditeurTouches | None = None
        self._note_preregle: QLabel | None = None
        # « Qualité d'image » : les préréglages de CE jeu, leurs boutons, la
        # phrase qui dit ce que fait celui qui est choisi, et le détail replié.
        self._prereglages: tuple = ()
        self._boutons_prereglage: dict[str, QPushButton] = {}
        self._texte_prereglage: QLabel | None = None
        self._detail: QWidget | None = None
        self._lien_detail: QPushButton | None = None

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
            # La barre de défilement prend sa place à droite : le texte s'en écarte.
            # Remis à zéro quand elle part (le détail de la qualité se replie).
            contenu.layout().setContentsMargins(0, 0, 18 if v > plafond else 0, 0)
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
            return self._onglet_image(corps)
        if onglet == "commandes":
            if not self._correctif_actif():
                # Une seule note pour les touches ET la manette du correctif.
                note = (self._section_correctif(corps, "commandes")
                        or self._section_correctif(corps, "manette"))
                if note:
                    corps.addSpacing(18)
                return self._section_manette(corps) or note
            a_des_touches = self._section_correctif(corps, "commandes")
            if a_des_touches and "touches_zqsd" in self._controles:
                corps.addSpacing(14)
                self._section_touches(corps)
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

    def _onglet_image(self, corps: QVBoxLayout) -> bool:
        """Affichage, puis « Qualité d'image » : des préréglages, le détail replié.

        Variante B choisie par Ludo le 2026-09-30 (« les gens s'y retrouvent
        pas, beaucoup de texte ») : on choisit d'abord une qualité en un clic ;
        chaque effet reste réglable, derrière un lien, avec ce qu'il coûte.
        """
        if not self._correctif_actif():
            # Jeu absent ou ancien correctif : une seule note pour tout l'onglet.
            return (self._section_correctif(corps, "affichage")
                    or self._section_correctif(corps, "image"))
        rempli = False
        if self._section_correctif(corps, "affichage", titre=tr("Affichage")):
            rempli = True
        qualite = [r for r in self._reglages if r.onglet == "image"]
        if qualite:
            if rempli:
                corps.addSpacing(18)
            corps.addWidget(self._titre_rubrique(tr("Qualité d'image")))
            corps.addSpacing(8)
            self._prereglages = reglages_correctif.prereglages_du_jeu(qualite)
            if self._prereglages:
                self._barre_prereglages(corps)
            self._detail = QWidget()
            self._detail.setStyleSheet("background: transparent;")
            detail = QVBoxLayout(self._detail)
            detail.setContentsMargins(0, 0, 0, 0)
            detail.setSpacing(0)
            self._legende(detail)
            for reglage in qualite:
                self._controle(detail, self._ini, reglage)
            if self._prereglages:
                self._lien_detail = QPushButton()
                self._lien_detail.setFont(body_font(12))
                self._lien_detail.setCursor(Qt.CursorShape.PointingHandCursor)
                self._lien_detail.setStyleSheet(themed(_LIEN_STYLE))
                self._lien_detail.clicked.connect(lambda: self._deplier(self._detail.isHidden()))
                corps.addSpacing(4)
                ligne = QHBoxLayout()
                ligne.addWidget(self._lien_detail)
                ligne.addStretch()
                corps.addLayout(ligne)
                self._detail.hide()
                self._maj_lien_detail()
            corps.addWidget(self._detail)
            self._maj_dependances()
            self._maj_prereglage()
            rempli = True
        if rempli:
            self._bouton_origine(corps)
        return rempli

    def _barre_prereglages(self, layout: QVBoxLayout) -> None:
        """Légère · Équilibrée · Maximale · Sur mesure, et ce que fait le choix."""
        barre = QHBoxLayout()
        barre.setSpacing(0)
        groupe = QButtonGroup(self)
        groupe.setExclusive(True)
        entrees = [(ident, nom) for ident, nom, _t, _v in self._prereglages] + [("", "Sur mesure")]
        for rang, (ident, nom) in enumerate(entrees):
            bouton = QPushButton(tr(nom))
            bouton.setCheckable(True)
            bouton.setFont(body_font(12))
            bouton.setCursor(Qt.CursorShape.PointingHandCursor)
            bouton.setMinimumHeight(32)
            coins = ("border-top-left-radius: 6px; border-bottom-left-radius: 6px;" if rang == 0
                     else "border-top-right-radius: 6px; border-bottom-right-radius: 6px;"
                     if rang == len(entrees) - 1 else "")
            bouton.setStyleSheet(themed(_PREREGLAGE_STYLE.replace(
                "padding: 5px 8px; }", f"padding: 5px 8px; {coins} }}", 1)))
            bouton.clicked.connect(lambda _c=False, i=ident: self._choisir_prereglage(i))
            groupe.addButton(bouton)
            barre.addWidget(bouton, stretch=1)
            self._boutons_prereglage[ident] = bouton
        layout.addLayout(barre)
        layout.addSpacing(6)
        self._texte_prereglage = QLabel("")
        self._texte_prereglage.setFont(body_font(10))
        self._texte_prereglage.setWordWrap(True)
        self._texte_prereglage.setTextFormat(Qt.TextFormat.PlainText)
        self._texte_prereglage.setStyleSheet("color: #8a8aaa; background: transparent;")
        layout.addWidget(self._texte_prereglage)

    def _legende(self, layout: QVBoxLayout) -> None:
        """Ce que disent les pastilles, en une ligne, avec leurs propres couleurs."""
        morceaux = [
            f'<span style="color:{_COULEURS_COUT[1]}">{html.escape(tr("vert faible"))}</span>',
            f'<span style="color:{_COULEURS_COUT[2]}">{html.escape(tr("orange moyen"))}</span>',
            f'<span style="color:{_COULEURS_COUT[3]}">{html.escape(tr("rouge extrême"))}</span>',
        ]
        texte = (html.escape(tr("Exigence pour la carte graphique (GPU), le processeur (CPU) "
                                "ou la mémoire (RAM) :"))
                 + " " + " · ".join(morceaux) + ". "
                 + html.escape(tr("Un réglage exigeant peut faire ramer un PC modeste.")))
        legende = QLabel(texte)
        legende.setTextFormat(Qt.TextFormat.RichText)
        legende.setFont(body_font(10))
        legende.setWordWrap(True)
        legende.setStyleSheet("color: #8a8aaa; background: transparent; padding: 8px 0px 6px 0px;")
        layout.addWidget(legende)

    def _deplier(self, oui: bool) -> None:
        if self._detail is None:
            return
        self._detail.setVisible(oui)
        self._maj_lien_detail()
        self._ajuster_hauteur()

    def _maj_lien_detail(self) -> None:
        if self._lien_detail is None:
            return
        n = sum(1 for r in self._reglages if r.onglet == "image")
        self._lien_detail.setText(tr("Masquer le détail") if not self._detail.isHidden()
                                  else tr("Régler chaque effet ({})").format(n))

    def _maj_prereglage(self) -> None:
        """Le bouton coché et la phrase suivent ce que portent VRAIMENT les contrôles."""
        if not self._prereglages:
            return
        courant = reglages_correctif.prereglage_courant(self._prereglages, self._valeurs_affichees())
        bouton = self._boutons_prereglage.get(courant)
        if bouton is not None:
            bouton.setChecked(True)
        textes = {ident: texte for ident, _n, texte, _v in self._prereglages}
        self._texte_prereglage.setText(
            tr(textes[courant]) if courant else tr("Vos propres réglages, effet par effet."))

    def _choisir_prereglage(self, ident: str) -> None:
        if not ident:
            # « Sur mesure » n'écrit rien : il ouvre le détail.
            self._deplier(True)
            self._maj_prereglage()
            return
        voulues = next(v for i, _n, _t, v in self._prereglages if i == ident)
        try:
            for cle, valeur in voulues.items():
                reglages_correctif.ecrire(self._ini, reglages_correctif.REGLAGES[cle], valeur)
        except (OSError, ValueError):
            log.warning("Correctif : préréglage %s non écrit", ident, exc_info=True)
            self._montrer_erreur()
        # Les contrôles reprennent ce que porte le fichier, écrit en entier ou non.
        for cle in voulues:
            widget = self._controles.get(cle)
            if widget is not None:
                self._remettre_controle(widget, reglages_correctif.REGLAGES[cle])
        self._maj_dependances()
        self._maj_prereglage()
        if self._erreur.isHidden():
            self._apres_ecriture()

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

    def _section_correctif(self, layout: QVBoxLayout, onglet: str, titre: str = "") -> bool:
        """Les réglages du correctif PC (HP4-HP7b) rangés dans CET onglet ; False s'il n'y en a pas.

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
        if titre:
            layout.addWidget(self._titre_rubrique(titre))
            layout.addSpacing(4)
        for reglage in reglages:
            self._controle(layout, ini, reglage)
        self._maj_dependances()
        return True

    def _valeurs_affichees(self) -> dict:
        """identifiant → valeur que montre son contrôle."""
        valeurs = {}
        for ident, widget in self._controles.items():
            valeurs[ident] = (widget.currentData() if isinstance(widget, QComboBox)
                              else widget.isChecked())
        return valeurs

    def _maj_dependances(self) -> None:
        """Grise ce qu'un réglage éteint prive d'effet, et dit lequel.

        Grisé et non caché : la page ne saute pas, et on voit ce qu'il faut
        rallumer. La valeur n'est PAS réécrite — rallumer le parent rend l'effet
        tel qu'il était.
        """
        valeurs = self._valeurs_affichees()
        for ident, bloc in self._blocs.items():
            reglage = reglages_correctif.REGLAGES[ident]
            bloquant = reglages_correctif.bloque_par(reglage, valeurs)
            bloc.setEnabled(bloquant is None)
            effet = bloc.graphicsEffect()
            if bloquant is None:
                if effet is not None:
                    bloc.setGraphicsEffect(None)
                bloc.setToolTip("")
            else:
                if effet is None:
                    effet = QGraphicsOpacityEffect(bloc)
                    effet.setOpacity(0.4)
                    bloc.setGraphicsEffect(effet)
                bloc.setToolTip(tr("Sans effet tant que « {} » est éteint.").format(
                    reglages_correctif.textes(bloquant)[0]))

    def _appliquer_exclusion(self, reglage, valeur) -> None:
        """Allumer un réglage éteint celui qu'il exclut (MSAA ↔ ombres de contact)."""
        autre = reglages_correctif.REGLAGES.get(reglage.exclut)
        widget = self._controles.get(reglage.exclut)
        if autre is None or widget is None or not reglages_correctif.allume(reglage, valeur):
            return
        if not reglages_correctif.allume(autre, self._valeurs_affichees()[autre.ident]):
            return
        try:
            reglages_correctif.ecrire(self._ini, autre, reglages_correctif.eteint(autre))
        except (OSError, ValueError):
            log.warning("Correctif : %s non éteint", autre.ident, exc_info=True)
            self._montrer_erreur()
        self._remettre_controle(widget, autre)

    def _bouton_origine(self, layout: QVBoxLayout) -> None:
        """« Rétablir les réglages d'origine » : ceux de l'ini tel qu'il était avant
        la première retouche du lanceur (demandé par Ludo, 2026-09-28 — surtout
        maintenant que les couleurs se règlent).
        """
        if self._ini is None or not self._ini.is_file():
            return
        bouton = QPushButton(tr("Rétablir les réglages d'origine"))
        bouton.setFont(body_font(12))
        # Même lien doré que les actions de « Fichiers » ; grisé tant qu'il n'y a
        # rien à rétablir.
        bouton.setStyleSheet(themed(
            "QPushButton { color: #d6a72c; background: transparent;"
            " border: none; text-align: left; padding: 4px 0px; }"
            "QPushButton:hover { color: #e8c547; text-decoration: underline; }"
            "QPushButton:disabled { color: #55556a; }"))
        bouton.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton.setEnabled(reglages_correctif.a_une_origine(self._ini))
        bouton.setToolTip(tr("Ceux du jeu tel qu'il a été installé. "
                             "Rien n'a encore été changé depuis le lanceur."))
        if bouton.isEnabled():
            bouton.setToolTip(tr("Remet image, commandes et performances comme à "
                                 "l'installation du jeu."))
        bouton.clicked.connect(self._remettre_origine)
        self._bouton_reset = bouton
        layout.addSpacing(8)
        ligne = QHBoxLayout()
        ligne.addWidget(bouton)
        ligne.addStretch()
        layout.addLayout(ligne)

    def _remettre_origine(self) -> None:
        try:
            reglages_correctif.remettre_origine(self._ini, self._reglages)
        except OSError:
            log.warning("Correctif : remise à l'origine impossible", exc_info=True)
            self._montrer_erreur()
            return
        for reglage in self._reglages:
            widget = self._controles.get(reglage.ident)
            if widget is not None:
                self._remettre_controle(widget, reglage)
        if self._editeur is not None:
            self._editeur.rafraichir()
        self._maj_preregle()
        self._maj_dependances()
        self._maj_prereglage()

    def _remettre_controle(self, widget, reglage) -> None:
        """Remet un contrôle sur ce que porte VRAIMENT le fichier."""
        try:
            etat = reglages_correctif.lire(self._ini, reglage)
        except OSError:
            return
        widget.blockSignals(True)
        if isinstance(widget, QComboBox):
            index = widget.findData(etat.valeur)
            if index < 0:
                widget.addItem(tr("{} (réglé à la main)").format(etat.valeur), etat.valeur)
                index = widget.count() - 1
            widget.setCurrentIndex(index)
        else:
            widget.setChecked(bool(etat.valeur))
        widget.blockSignals(False)

    def _montrer_erreur(self) -> None:
        self._erreur.setText(tr(
            "Réglage non enregistré : le fichier d3d9.ini du jeu n'a pas "
            "pu être modifié (jeu en cours, ou fichier en lecture seule)."))
        if self._erreur.isHidden():
            self._erreur.show()
            self._ajuster_hauteur()   # le message ne doit rien recouvrir

    def _note(self, layout: QVBoxLayout, texte: str) -> None:
        note = QLabel(texte)
        note.setFont(body_font(11))
        note.setWordWrap(True)
        note.setTextFormat(Qt.TextFormat.PlainText)
        note.setStyleSheet("color: #8a8aaa; background: transparent;")
        layout.addWidget(note)

    def _ligne(self, layout: QVBoxLayout, libelle_txt: str, controle: QWidget, aide_txt: str,
               reglage=None) -> None:
        """Une ligne par réglage : le nom, ce qu'il coûte, le contrôle toujours à
        DROITE (maquette B, 2026-09-30) ; la phrase qui dit ce qu'il fait, dessous."""
        ligne = QWidget()
        ligne.setStyleSheet("background: transparent;")
        h = QHBoxLayout(ligne)
        h.setContentsMargins(0, 6, 0, 0)
        h.setSpacing(8)
        libelle = QLabel(libelle_txt)
        libelle.setTextFormat(Qt.TextFormat.PlainText)
        libelle.setStyleSheet("color: #ffffff; font-size: 13px; background: transparent;")
        h.addWidget(libelle)
        if reglage is not None:
            self._reperes(h, reglage)
        h.addStretch(1)
        if isinstance(controle, ToggleSwitch):
            # Le libellé est à côté, pas dedans : sans nom accessible, un lecteur
            # d'écran n'annoncerait qu'« interrupteur » (règle 15).
            controle.setToolTip(libelle_txt)
        controle.setAccessibleName(libelle_txt)
        h.addWidget(controle)
        layout.addWidget(ligne)
        aide = QLabel(aide_txt)
        aide.setFont(body_font(10))
        aide.setWordWrap(True)
        aide.setTextFormat(Qt.TextFormat.PlainText)
        aide.setStyleSheet("color: #8a8aaa; background: transparent; padding-bottom: 4px;")
        layout.addWidget(aide)

    def _controle(self, parent: QVBoxLayout, ini: Path, reglage) -> None:
        try:
            etat = reglages_correctif.lire(ini, reglage)
        except OSError:
            log.warning("Correctif : %s illisible", ini, exc_info=True)
            return
        bloc = QWidget()
        bloc.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(bloc)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        parent.addWidget(bloc)
        self._blocs[reglage.ident] = bloc
        libelle_txt, aide_txt = reglages_correctif.textes(reglage)
        if reglage.choix:
            choix = QComboBox()
            choix.setStyleSheet(themed(_COMBO_STYLE))
            # Une largeur commune : les listes s'alignent en colonne à droite.
            choix.setMinimumWidth(150)
            for n in reglage.choix:
                choix.addItem(reglages_correctif.libelle_choix(reglage, n), n)
            if etat.personnalise:
                # Une valeur posée à la main dans l'ini : la montrer telle
                # quelle plutôt que d'afficher un choix qui n'est pas le sien.
                choix.addItem(tr("{} (réglé à la main)").format(etat.valeur), etat.valeur)
            choix.setCurrentIndex(max(0, choix.findData(etat.valeur)))
            choix.currentIndexChanged.connect(
                lambda _i, c=choix, r=reglage: self._on_reglage(r, c.currentData(), c))
            self._controles[reglage.ident] = choix
            self._ligne(layout, libelle_txt, choix, aide_txt, reglage)
        else:
            bascule = ToggleSwitch(bool(etat.valeur))
            bascule.toggled.connect(
                lambda coche, r=reglage, b=bascule: self._on_reglage(r, coche, b))
            self._controles[reglage.ident] = bascule
            self._ligne(layout, libelle_txt, bascule, aide_txt, reglage)
            if reglage.ident == "touches_zqsd":
                # Des touches choisies une par une (ci-dessous, ou à la main dans
                # l'ini) : le préréglage les écraserait. On le dit sous son aide,
                # on n'y touche pas ; la note suit l'éditeur (_maj_preregle).
                bascule.setEnabled(not etat.personnalise)
            elif etat.personnalise:
                # Quelques lignes du panneau allumées à la main : rien n'est
                # perdu à le dire, et l'interrupteur reste libre.
                self._note(layout, tr(
                    "Réglé en partie à la main dans d3d9.ini : l'activer allume tout le panneau."))
        if reglage.ident == "touches_zqsd":
            note = QLabel(tr("Touches choisies une par une : le préréglage ne les remplace pas. "
                             "« Remettre toutes les touches du jeu » le libère."))
            note.setFont(body_font(10))
            note.setWordWrap(True)
            note.setTextFormat(Qt.TextFormat.PlainText)
            note.setStyleSheet("color: #e8955a; background: transparent; padding-bottom: 4px;")
            note.setVisible(etat.personnalise)
            layout.addWidget(note)
            self._note_preregle = note

    def _reperes(self, ligne: QHBoxLayout, reglage) -> None:
        """Pastilles À CÔTÉ du nom : ce qu'il coûte (« GPU +++ ») et s'il se voit.

        Du TEXTE, pas des pictogrammes : Cinzel n'a pas les symboles, et Windows
        les rendrait en emoji couleur (règles 59 et 60). La couleur double le
        nombre de + (vert, orange, rouge), elle ne le remplace pas.
        """
        pastilles = [(f"{ressource} {'+' * niveau}", _COULEURS_COUT.get(niveau, "#8a8aaa"))
                     for ressource, niveau in reglage.cout]
        if reglage.se_voit:
            pastilles.append((tr("Se voit"), _COULEUR_SE_VOIT))
        for texte, couleur in pastilles:
            pastille = QLabel(texte)
            pastille.setFont(body_font(9))
            pastille.setTextFormat(Qt.TextFormat.PlainText)
            pastille.setStyleSheet(themed(
                f"color: {couleur}; background: transparent; border: 1px solid {couleur};"
                " border-radius: 3px; padding: 0px 5px;"))
            # Centrée, à sa hauteur : sinon elle s'étire à celle de la liste voisine.
            ligne.addWidget(pastille, alignment=Qt.AlignmentFlag.AlignVCenter)

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
                "Branchez-la avant de lancer le jeu. Ce choix vit dans le registre de "
                "Windows : le lanceur prévient avant d'y écrire."))
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
            self._remettre_controle(widget, reglage)
            self._montrer_erreur()
            self._maj_dependances()
            self._maj_prereglage()
            return
        self._appliquer_exclusion(reglage, valeur)
        self._maj_dependances()
        self._maj_prereglage()
        if reglage.ident == "touches_zqsd" and self._editeur is not None:
            self._editeur.rafraichir()
        self._apres_ecriture()

    def _apres_ecriture(self) -> None:
        """Ce que change toute écriture réussie : le bouton de remise à l'origine
        (la première retouche vient de garder l'ini d'origine), et l'erreur passée."""
        if self._bouton_reset is not None and not self._bouton_reset.isEnabled():
            # La première retouche vient de garder l'ini d'origine.
            self._bouton_reset.setEnabled(reglages_correctif.a_une_origine(self._ini))
            self._bouton_reset.setToolTip(tr("Remet image, commandes et performances "
                                             "comme à l'installation du jeu."))
        if not self._erreur.isHidden():
            self._erreur.hide()
            self._ajuster_hauteur()

    def _resynchroniser(self) -> None:
        courant = self.manager.game_language(self.game)
        for code, bouton in self._boutons.items():
            bouton.blockSignals(True)
            bouton.setChecked(code == courant)
            bouton.blockSignals(False)
