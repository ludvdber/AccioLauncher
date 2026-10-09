"""Réglages d'UN jeu : image, commandes, langue, performances, et ses fichiers.

Pourquoi une FENÊTRE et pas le menu qu'il y avait ici d'abord : un menu est un
choix qu'on prend et qui se referme, alors que les réglages d'un jeu
s'étoffent. Une fenêtre a des rubriques, de la place pour expliquer, et sait
montrer ce qui n'est pas encore là (la rubrique « Affichage » verrouillée de
HP1 à HP3).

Refaite le 2026-10-09 d'après la maquette « Réglages du jeu » validée par
Ludo : un rail à gauche (le jeu, ses rubriques, ses fichiers), des cartes à
droite. Ce qu'elle corrige de l'ancienne boîte à onglets :

- une boîte trop haute pour ce qu'elle portait, et un onglet entier pour
  quelques liens : les fichiers vivent au bas du rail ;
- les effets d'image repliés par familles : il fallait déplier pour voir ce
  que fait un préréglage. Tous sont visibles, préréglages à côté ;
- le coût lu comme du texte (« GPU +++ » sur chaque ligne) : trois points de
  couleur se comparent d'un coup d'œil, le détail reste dans le « ? » ;
- les liens entre réglages découverts en voyant des lignes grisées : la
  ligne grisée DIT ce qui l'éteint, et un effet qui dépend d'un autre est
  rangé en retrait sous lui ;
- « Rétablir les réglages d'origine » en lien gris, qu'on croyait
  désactivé, et un bouton Fermer alors que tout s'enregistre au fil des
  clics : un vrai bouton au pied, « Retour à la fiche » en haut du rail.
"""

import html
from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QIcon
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.core import reglages_correctif, reglages_graphiques
from src.core.game_data import GameData
from src.core.game_manager import GameManager
from src.core.i18n import tr
from src.ui.aide_reglage import BoutonAide
from src.ui.composants import (
    ENCRE_DOUCE,
    Carte,
    Rangee,
    feuille_de_style,
    police,
    surtitre,
)
from src.ui.editeur_touches import EditeurTouches
from src.ui.fonts import cinzel, cinzel_decorative
from src.ui.icon_button import pixmap_icone
from src.ui.theme import accent_qcolor, current as current_theme, themed
from src.ui.toggle_switch import ToggleSwitch
from src.ui.utils import zone_defilable
from src.ui.reglages_widgets import (  # noqa: F401  (réexportés)
    _STYLE,
    _CarteEffets,
    _CartePrereglage,
    _Disposition,
    _Jaquette,
    _Ligne,
    _Points,
)
from src.ui.reglages_rubriques import (  # noqa: F401  (réexportés)
    log,
    _ONGLETS,
    _COULEURS_COUT,
    _COULEUR_SE_VOIT,
    _COULEUR_NOTE,
    _LIEN_STYLE,
    _GROUPES_EFFETS,
    _RESSOURCES,
    _NIVEAUX,
    _A_VENIR,
    RubriquesDuJeu,
)

# Le rail : le jeu, ses rubriques, ses fichiers.
_LARGEUR_RAIL = 260
# Taille d'ouverture, celle de la maquette, et le plancher : sous 900 px de
# large, la page Image passe d'elle-même en une colonne.
_TAILLE_VOULUE = QSize(1320, 860)
_TAILLE_MIN = QSize(900, 580)
# Les marges de lecture d'une page.
_MARGES_PAGE = (40, 28, 40, 28)
# La page Image côte à côte au-dessus de ça : la colonne de gauche (affichage,
# préréglages) et la carte des effets.
_SEUIL_IMAGE = 860

class GameSettingsDialog(RubriquesDuJeu, QDialog):
    """Fenêtre de réglages d'un jeu. Tout choix s'écrit AUSSITÔT.

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
        self._actions = tuple(actions)
        # (oui) -> bool : prévient, écrit, dit si c'est pris. None = pas de rubrique.
        self._appliquer_manette = appliquer_manette
        self._bascule_manette = None
        # La liste des résolutions (HP1, HP2) ; None pour les autres jeux.
        self._choix_resolution: QComboBox | None = None
        self._groupe = QButtonGroup(self)
        self._boutons: dict[str, QRadioButton] = {}
        # Réglages du correctif que le catalogue déclare confirmés pour ce jeu,
        # et son ini (à côté de l'exécutable, là où le correctif le lit).
        self._reglages = reglages_correctif.reglages_du_jeu(game.fix_settings)
        self._ini: Path | None = (
            reglages_correctif.chemin_ini(
                manager.config.install_path / Path(game.executable).parent)
            if self._reglages else None)
        # HP3 : pas de correctif, mais le fichier de son traducteur D3D8 (`reglages_graphiques`).
        conf = reglages_graphiques.chemin(manager.config.install_path / Path(game.executable).parent)
        self._conf_graph: Path | None = (
            conf if not self._reglages and reglages_graphiques.disponible(conf) else None)
        self._controles_graph: dict[str, QWidget] = {}
        self._erreur: QLabel | None = None
        self._compte_captures: QLabel | None = None
        # Le contrôle de chaque réglage du correctif, par identifiant : la remise
        # à l'origine les remet sur ce que porte le fichier, sans rebâtir la page.
        self._controles: dict[str, QWidget] = {}
        # Le « ? » de chaque ligne, par identifiant (par libellé hors correctif).
        self._aides: dict[str, BoutonAide] = {}
        # La ligne entière de chaque réglage : grisée quand un autre réglage,
        # éteint, lui retire tout effet, et elle dit lequel.
        self._blocs: dict[str, _Ligne] = {}
        self._bouton_reset: QPushButton | None = None
        # L'éditeur de touches (HP4) et la note sous la disposition ZQSD, que
        # l'éditeur fait apparaître dès qu'une touche est choisie à l'unité.
        self._editeur: EditeurTouches | None = None
        self._note_preregle: QLabel | None = None
        # « Qualité d'image » : les préréglages de CE jeu et leurs cartes.
        self._prereglages: tuple = ()
        self._boutons_prereglage: dict[str, QPushButton] = {}
        self._carte_des_effets: QWidget | None = None

        self.setWindowTitle(tr("Réglages — {}").format(game.name))
        self.setStyleSheet(themed(_STYLE) + feuille_de_style())
        self._build_ui()
        self._taille_de_depart()

    def _taille_de_depart(self) -> None:
        """Celle de la maquette, bornée par l'écran : la fenêtre se redimensionne
        à la main, et chaque page défile si elle ne tient pas (règle 52)."""
        ecran = self.screen() or QGuiApplication.primaryScreen()
        voulue, mini = QSize(_TAILLE_VOULUE), QSize(_TAILLE_MIN)
        if ecran is not None:
            dispo = ecran.availableGeometry().size()
            voulue = voulue.boundedTo(QSize(int(dispo.width() * 0.92), int(dispo.height() * 0.9)))
            mini = mini.boundedTo(voulue)
        self.setMinimumSize(mini)
        self.resize(voulue)

    # ── Construction ──

    def _build_ui(self) -> None:
        racine = QHBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(0)

        self._defile = QStackedWidget()
        self._defile.setStyleSheet("background: transparent;")
        self._contenus: list[QWidget] = []
        pages = []
        for ident, libelle, icone in _ONGLETS:
            contenu = QWidget()
            contenu.setStyleSheet("background: transparent;")
            page = QVBoxLayout(contenu)
            page.setContentsMargins(*_MARGES_PAGE)
            page.setSpacing(0)
            titre = QLabel(tr(libelle))
            titre.setFont(cinzel_decorative(20))
            titre.setStyleSheet("color: #f4f2f8; background: transparent;")
            page.addWidget(titre)
            page.addSpacing(20)
            corps = QVBoxLayout()
            corps.setContentsMargins(0, 0, 0, 0)
            corps.setSpacing(0)
            page.addLayout(corps)
            if not self._remplir(ident, corps):
                contenu.deleteLater()
                continue
            page.addStretch()
            self._contenus.append(contenu)
            self._defile.addWidget(zone_defilable(contenu))
            pages.append((ident, libelle, icone))

        racine.addWidget(self._rail(pages))
        droite = QVBoxLayout()
        droite.setContentsMargins(0, 0, 0, 0)
        droite.setSpacing(0)
        droite.addWidget(self._defile, stretch=1)
        self._erreur = QLabel("")
        self._erreur.setFont(police(13))
        self._erreur.setWordWrap(True)
        self._erreur.setTextFormat(Qt.TextFormat.PlainText)
        self._erreur.setStyleSheet("color: #e8955a; background: transparent;")
        self._erreur.setContentsMargins(_MARGES_PAGE[0], 8, _MARGES_PAGE[2], 8)
        self._erreur.hide()
        droite.addWidget(self._erreur)
        droite.addWidget(self._pied())
        racine.addLayout(droite, stretch=1)
        if self._onglets:
            next(iter(self._onglets.values())).setChecked(True)

    def _rail(self, pages) -> QFrame:
        rail = QFrame()
        rail.setObjectName("rail")
        rail.setFixedWidth(_LARGEUR_RAIL)
        lay = QVBoxLayout(rail)
        lay.setContentsMargins(18, 22, 18, 20)
        lay.setSpacing(4)

        # Le chemin du retour dit OÙ il mène : la fiche, pas « Fermer ».
        retour = QPushButton(tr("Retour à la fiche"))
        retour.setObjectName("retour")
        retour.setFont(police(13))
        retour.setIcon(QIcon(pixmap_icone("retour", 18, QColor("#a9a7c4"))))
        retour.setIconSize(QSize(18, 18))
        retour.setCursor(Qt.CursorShape.PointingHandCursor)
        retour.setAutoDefault(False)
        retour.clicked.connect(self.accept)
        lay.addWidget(retour, alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addSpacing(14)

        identite = QHBoxLayout()
        identite.setSpacing(14)
        identite.addWidget(_Jaquette(self.game.cover_image), alignment=Qt.AlignmentFlag.AlignTop)
        noms = QVBoxLayout()
        noms.setSpacing(4)
        nom = QLabel(self.game.name)
        nom.setTextFormat(Qt.TextFormat.PlainText)   # le nom vient du CATALOGUE
        nom.setWordWrap(True)
        nom.setFont(cinzel(11, bold=True))
        nom.setStyleSheet("color: #f4f2f8; background: transparent;")
        nom.setMinimumWidth(1)
        noms.addWidget(nom)
        noms.addWidget(surtitre(tr("Réglages du jeu")))
        identite.addLayout(noms, stretch=1)
        lay.addLayout(identite)
        lay.setAlignment(identite, Qt.AlignmentFlag.AlignTop)
        self._titre = nom
        lay.addSpacing(20)

        self._groupe_onglets = QButtonGroup(self)
        self._groupe_onglets.setExclusive(True)
        self._onglets: dict[str, QPushButton] = {}
        normal = QColor("#a9a7c4")
        choisi = QColor(current_theme().accent_light)
        for rang, (ident, libelle, icone) in enumerate(pages):
            pictogramme = QIcon()
            pictogramme.addPixmap(pixmap_icone(icone, 20, normal), QIcon.Mode.Normal, QIcon.State.Off)
            pictogramme.addPixmap(pixmap_icone(icone, 20, choisi), QIcon.Mode.Normal, QIcon.State.On)
            btn = QPushButton(tr(libelle))
            btn.setObjectName("rubrique")
            btn.setCheckable(True)
            btn.setIcon(pictogramme)
            btn.setIconSize(QSize(20, 20))
            btn.setFont(police(14))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setAutoDefault(False)
            btn.toggled.connect(lambda oui, r=rang: oui and self._defile.setCurrentIndex(r))
            self._groupe_onglets.addButton(btn)
            self._onglets[ident] = btn
            lay.addWidget(btn)
        lay.addStretch()

        if self._actions:
            filet = QFrame()
            filet.setObjectName("separateur")
            filet.setFixedHeight(1)
            lay.addWidget(filet)
            lay.addSpacing(14)
            self._actions_du_rail(lay)
        return rail

    def _pied(self) -> QFrame:
        """Ce qui vaut pour toute la fenêtre : quand c'est pris en compte, comment
        revenir, et la remise à l'origine."""
        pied = QFrame()
        pied.setObjectName("pied")
        pied.setMinimumHeight(56)
        h = QHBoxLayout(pied)
        h.setContentsMargins(_MARGES_PAGE[0], 10, _MARGES_PAGE[2], 10)
        h.setSpacing(10)
        info = QLabel()
        info.setPixmap(pixmap_icone("infos", 18, accent_qcolor()))
        info.setStyleSheet("background: transparent;")
        h.addWidget(info)
        morceaux = []
        if self._correctif_actif() or self._conf_graph is not None or self.game.resolution is not None:
            morceaux.append(tr("Pris en compte au prochain lancement du jeu."))
        morceaux.append(tr("Échap pour revenir à la fiche."))
        self._pied_notes = QLabel("  ·  ".join(morceaux))
        self._pied_notes.setTextFormat(Qt.TextFormat.PlainText)
        self._pied_notes.setWordWrap(True)
        self._pied_notes.setFont(police(13))
        self._pied_notes.setStyleSheet(f"color: {ENCRE_DOUCE}; background: transparent;")
        h.addWidget(self._pied_notes, stretch=1)
        if self._bouton_reset is not None:
            h.addWidget(self._bouton_reset)
        return pied

    # ── Les pages ──

    def _correctif_actif(self) -> bool:
        """Le jeu déclare des réglages ET porte le nouveau correctif, qui les lira."""
        ini = self._ini
        return bool(self._reglages) and ini is not None and ini.is_file() \
            and reglages_correctif.est_nouveau_correctif(ini)

    def _remplir(self, onglet: str, corps: QVBoxLayout) -> bool:
        """Pose le contenu d'une page ; False si elle n'a rien à montrer."""
        if onglet == "image":
            if self._section_graphiques(corps, "image"):
                return True
            if not self._reglages:
                self._section_affichage(corps)
                return True
            return self._page_image(corps)
        if onglet == "commandes":
            if not self._correctif_actif():
                # Une seule note pour les touches ET la manette du correctif.
                note = (self._section_correctif(corps, "commandes")
                        or self._section_correctif(corps, "manette"))
                return self._section_manette(corps) or note
            a_des_touches = self._section_disposition(corps)
            if a_des_touches and "touches_zqsd" in self._controles:
                self._section_touches(corps)
            return self._section_manette(corps) or a_des_touches
        if onglet == "jeu":
            rempli = False
            # La langue n'a sa rubrique que si elle se RÈGLE : jeu qui en déclare,
            # et registre atteignable pour ceux qui la lisent là.
            if self.manager.game_language(self.game) is not None:
                self._section_langue(corps)
                rempli = True
            if self._section_correctif(corps, "jeu", titre=tr("Dans le jeu")):
                rempli = True
            return self._section_captures(corps) or rempli
        return (self._section_correctif(corps, "perfs")
                or self._section_graphiques(corps, "perfs"))

    def _page_image(self, corps: QVBoxLayout) -> bool:
        """Affichage et qualité d'image à gauche, chaque effet à droite.

        Les préréglages d'abord (Ludo, 2026-09-30 : « les gens s'y retrouvent
        pas ») ; chaque effet reste réglable, et désormais VISIBLE à côté : on
        voit ce que change un préréglage au moment où on le choisit.
        """
        if not self._correctif_actif():
            # Jeu absent ou ancien correctif : une seule note pour toute la page.
            return (self._section_correctif(corps, "affichage")
                    or self._section_correctif(corps, "image"))
        gauche = QWidget()
        gauche.setStyleSheet("background: transparent;")
        colonne = QVBoxLayout(gauche)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.setSpacing(0)
        self._section_correctif(colonne, "affichage", titre=tr("Affichage"))
        qualite = [r for r in self._reglages if r.onglet == "image"]
        droite = None
        if qualite:
            self._prereglages = reglages_correctif.prereglages_du_jeu(qualite)
            if self._prereglages:
                self._section(colonne, surtitre(tr("Qualité d'image")), self._cartes_prereglages())
            droite = QWidget()
            droite.setStyleSheet("background: transparent;")
            v = QVBoxLayout(droite)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(0)
            carte = self._effets_par_familles(qualite)
            self._section(v, self._entete_effets(tr("Chaque effet")), carte)
            v.addStretch()
            self._carte_des_effets = carte
            self._maj_dependances()
            self._maj_prereglage()
        colonne.addStretch()
        blocs = [b for b, plein in ((gauche, colonne.count() > 1), (droite, droite is not None)) if plein]
        if not blocs:
            return False
        if len(blocs) == 2:
            corps.addWidget(Rangee(blocs, colonnes=2, seuil=_SEUIL_IMAGE, etirements=(4, 5), ecart=36))
        else:
            corps.addWidget(blocs[0])
        self._bouton_origine()
        return True

    def _entete_effets(self, titre: str) -> QWidget:
        """Le surtitre, et la légende des repères au bout de la ligne."""
        entete = QWidget()
        entete.setStyleSheet("background: transparent;")
        h = QHBoxLayout(entete)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        h.addWidget(surtitre(titre))
        h.addStretch()
        oeil = QLabel()
        oeil.setPixmap(pixmap_icone("oeil", 18, QColor(_COULEUR_SE_VOIT)))
        oeil.setStyleSheet("background: transparent;")
        h.addWidget(oeil)
        h.addWidget(self._petit(tr("se voit")))
        h.addSpacing(12)
        for niveau in (1, 2, 3):
            h.addWidget(_Points(niveau))
        h.addWidget(self._petit(tr("exigence")))
        # Le détail des couleurs, au survol de la légende.
        entete.setToolTip(
            tr("Exigence pour la carte graphique (GPU), le processeur (CPU) ou la mémoire (RAM) :")
            + " " + " · ".join((tr("vert faible"), tr("orange moyen"), tr("rouge extrême"))) + ". "
            + tr("Chaque « ? » explique son réglage."))
        return entete

    @staticmethod
    def _petit(contenu: str) -> QLabel:
        lbl = QLabel(contenu)
        lbl.setTextFormat(Qt.TextFormat.PlainText)
        lbl.setFont(police(12))
        lbl.setStyleSheet(f"color: {ENCRE_DOUCE}; background: transparent;")
        return lbl

    def _carte_effets(self) -> _CarteEffets:
        return _CarteEffets()

    def _effets_par_familles(self, qualite) -> _CarteEffets:
        carte = _CarteEffets()
        restants = list(qualite)
        familles = []
        for nom, idents in _GROUPES_EFFETS:
            membres = [r for r in restants if r.ident in idents]
            if membres:
                familles.append((nom, membres))
                restants = [r for r in restants if r not in membres]
        if restants:
            # Un réglage d'image qu'aucune famille ne nomme encore n'est jamais perdu.
            familles.append(("Autres", restants))
        for nom, membres in familles:
            carte.famille(tr(nom))
            presents = {r.ident for r in membres}
            for reglage in membres:
                # Rangé en retrait sous le réglage dont il dépend, s'il est là.
                self._controle(carte, self._ini, reglage, retrait=reglage.depend_de in presents)
        self._egaliser(carte)
        return carte

    def _cartes_prereglages(self) -> QWidget:
        """Légère · Équilibrée · Maximale · Sur mesure, en cartes de deux sur deux."""
        bloc = QWidget()
        bloc.setStyleSheet("background: transparent;")
        grille = QGridLayout(bloc)
        grille.setContentsMargins(0, 0, 0, 0)
        grille.setSpacing(10)
        groupe = QButtonGroup(self)
        groupe.setExclusive(True)
        entrees = [(ident, nom, texte, rang + 1)
                   for rang, (ident, nom, texte, _v) in enumerate(self._prereglages)]
        entrees.append(("", "Sur mesure", "Se choisit tout seul dès qu'un effet change.", 0))
        for rang, (ident, nom, texte, niveau) in enumerate(entrees):
            repere = _Points(min(niveau, 3), largeur_segment=16) if niveau else None
            carte = _CartePrereglage(tr(nom), tr(texte), repere)
            if not ident:
                carte.setProperty("surMesure", True)
            carte.clicked.connect(lambda _c=False, i=ident: self._choisir_prereglage(i))
            groupe.addButton(carte)
            grille.addWidget(carte, rang // 2, rang % 2)
            self._boutons_prereglage[ident] = carte
        return bloc

    def _fiche(self, aide_txt: str, reglage=None) -> str:
        """Ce qu'ouvre le « ? » : la description, puis tout ce qu'on sait du réglage."""
        e = html.escape
        paragraphes = [e(aide_txt)]
        if reglage is not None:
            if reglage.cout:
                paragraphes.append("<br>".join(
                    f'{e(tr(_RESSOURCES.get(r, r)))} : <span style="color:{_COULEURS_COUT[n]}">'
                    f"{e(tr(_NIVEAUX[n]))} ({'+' * n})</span>" for r, n in reglage.cout))
            if reglage.se_voit:
                paragraphes.append(f'<span style="color:{_COULEUR_SE_VOIT}">'
                                   f"{e(tr('Se voit nettement à l’écran.'))}</span>")
            declares = {r.ident for r in self._reglages}

            def deja_dit(autre) -> bool:
                # La description le nomme déjà (« l'allumer éteint les ombres de contact ») :
                # la fiche ne le répète pas.
                return reglages_correctif.textes(autre)[0].lower() in aide_txt.lower()

            parent = reglages_correctif.REGLAGES.get(reglage.depend_de)
            if parent is not None and parent.ident in declares and not deja_dit(parent):
                paragraphes.append(e(tr("Sans effet tant que « {} » est éteint.").format(
                    reglages_correctif.textes(parent)[0])))
            exclu = reglages_correctif.REGLAGES.get(reglage.exclut)
            if exclu is not None and exclu.ident in declares and not deja_dit(exclu):
                paragraphes.append(e(tr("L'allumer éteint « {} », qui ne peut pas agir en même "
                                        "temps.").format(reglages_correctif.textes(exclu)[0])))
        return "".join(f"<p>{p}</p>" for p in paragraphes)

    def _maj_prereglage(self) -> None:
        """La carte cochée suit ce que portent VRAIMENT les contrôles."""
        if not self._prereglages:
            return
        courant = reglages_correctif.prereglage_courant(self._prereglages, self._valeurs_affichees())
        carte = self._boutons_prereglage.get(courant)
        if carte is not None:
            carte.setChecked(True)

    def _choisir_prereglage(self, ident: str) -> None:
        if not ident:
            # « Sur mesure » n'écrit rien : il mène aux effets, qu'on règle un par un.
            zone = self._zone_de(self._carte_des_effets)
            if zone is not None:
                zone.ensureWidgetVisible(self._carte_des_effets, 0, 0)
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

    @staticmethod
    def _zone_de(widget: QWidget | None) -> QScrollArea | None:
        while widget is not None and not isinstance(widget, QScrollArea):
            widget = widget.parentWidget()
        return widget

    def _section_correctif(self, corps: QVBoxLayout, onglet: str, titre: str = "") -> bool:
        """Les réglages du correctif PC (HP4-HP7b) rangés dans CET onglet ; False s'il n'y en a pas.

        Trois cas, et chacun le DIT : jeu absent, ancien correctif (rien ne
        lirait ces clés), nouveau correctif.
        """
        reglages = [r for r in self._reglages if r.onglet == onglet]
        if not reglages:
            return False
        ini = self._ini
        if ini is None or not ini.is_file():
            self._note(corps, tr("Installez le jeu pour régler son correctif."))
            return True
        if not reglages_correctif.est_nouveau_correctif(ini):
            self._note(corps, tr(
                "Ces réglages arrivent avec la prochaine version du correctif "
                "de ce jeu."))
            return True
        carte = Carte()
        for reglage in reglages:
            self._controle(carte, ini, reglage)
        self._egaliser(carte)
        self._section(corps, surtitre(titre) if titre else None, carte)
        self._maj_dependances()
        return True

    def _section_disposition(self, corps: QVBoxLayout) -> bool:
        """« Clavier d'origine » ou ZQSD et souris, en deux cartes (HP4)."""
        reglages = [r for r in self._reglages if r.onglet == "commandes"]
        if not reglages:
            return False
        for reglage in reglages:
            if reglage.ident != "touches_zqsd":
                carte = Carte()
                self._controle(carte, self._ini, reglage)
                self._egaliser(carte)
                self._section(corps, None, carte)
                continue
            try:
                etat = reglages_correctif.lire(self._ini, reglage)
            except OSError:
                log.warning("Correctif : %s illisible", self._ini, exc_info=True)
                continue
            libelle_txt, aide_txt = reglages_correctif.textes(reglage)
            disposition = _Disposition(bool(etat.valeur), libelle_txt, aide_txt)
            disposition.toggled.connect(
                lambda coche, r=reglage, d=disposition: self._on_reglage(r, coche, d))
            # Des touches choisies une par une (ci-dessous, ou à la main dans
            # l'ini) : la disposition les écraserait. On le dit, on n'y touche pas.
            disposition.setEnabled(not etat.personnalise)
            self._controles[reglage.ident] = disposition
            bloc = QWidget()
            bloc.setStyleSheet("background: transparent;")
            v = QVBoxLayout(bloc)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(8)
            v.addWidget(disposition)
            note = QLabel(tr("Touches choisies une par une : la disposition ne les remplace pas. "
                             "« Remettre les touches du jeu » la libère."))
            note.setFont(police(13))
            note.setWordWrap(True)
            note.setTextFormat(Qt.TextFormat.PlainText)
            note.setStyleSheet("color: #e8955a; background: transparent;")
            note.setVisible(etat.personnalise)
            v.addWidget(note)
            self._note_preregle = note
            self._section(corps, surtitre(tr("Disposition")), bloc)
        return True

    def _valeurs_affichees(self) -> dict:
        """identifiant → valeur que montre son contrôle."""
        valeurs = {}
        for ident, widget in self._controles.items():
            valeurs[ident] = (widget.currentData() if isinstance(widget, QComboBox)
                              else widget.isChecked())
        return valeurs

    def _maj_dependances(self) -> None:
        """Grise ce qu'un réglage éteint prive d'effet, et DIT lequel sous son nom.

        Grisé et non caché : la page ne saute pas, et on voit ce qu'il faut
        rallumer. La valeur n'est PAS réécrite — rallumer le parent rend l'effet
        tel qu'il était.
        """
        valeurs = self._valeurs_affichees()
        for ident, bloc in self._blocs.items():
            reglage = reglages_correctif.REGLAGES[ident]
            bloquant = reglages_correctif.bloque_par(reglage, valeurs)
            bloc.setEnabled(bloquant is None)
            effet = bloc.haut.graphicsEffect()
            if bloquant is None:
                if effet is not None:
                    bloc.haut.setGraphicsEffect(None)
                bloc.setToolTip("")
                bloc.note.hide()
            else:
                if effet is None:
                    effet = QGraphicsOpacityEffect(bloc.haut)
                    effet.setOpacity(0.42)
                    bloc.haut.setGraphicsEffect(effet)
                phrase = tr("Sans effet tant que « {} » est éteint.").format(
                    reglages_correctif.textes(bloquant)[0])
                bloc.setToolTip(phrase)
                bloc.note.setText(phrase)
                bloc.note.show()

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

    def _bouton_origine(self) -> None:
        """« Rétablir les réglages d'origine » : ceux de l'ini tel qu'il était avant
        la première retouche du lanceur (demandé par Ludo, 2026-09-28 — surtout
        maintenant que les couleurs se règlent). Au pied : il vaut pour toutes
        les pages, image, commandes et performances.
        """
        if self._ini is None or not self._ini.is_file():
            return
        btn = self._nouveau_bouton_reset()
        btn.setEnabled(reglages_correctif.a_une_origine(self._ini))
        btn.setToolTip(tr("Ceux du jeu tel qu'il a été installé. "
                          "Rien n'a encore été changé depuis le lanceur."))
        if btn.isEnabled():
            btn.setToolTip(tr("Remet image, commandes et performances comme à "
                              "l'installation du jeu."))
        btn.clicked.connect(self._remettre_origine)

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

    def _montrer_erreur(self, texte: str = "") -> None:
        self._erreur.setText(texte or tr(
            "Réglage non enregistré : le fichier d3d9.ini du jeu n'a pas "
            "pu être modifié (jeu en cours, ou fichier en lecture seule)."))
        self._erreur.show()

    def _ligne(self, libelle_txt: str, controle: QWidget, aide_txt: str,
               reglage=None, retrait: bool = False) -> _Ligne:
        """Une ligne par réglage : le nom, son « ? », ses repères, le contrôle
        toujours à DROITE, dans une colonne de même largeur pour toute la carte.

        L'explication vit derrière le « ? », au clic (Ludo : « une
        bonne description au survol de la souris ou un bouton ? ») : une phrase
        sous chaque ligne, c'était le mur de texte qu'on voulait retirer.
        """
        serree = reglage is not None and reglage.onglet == "image"
        ligne = _Ligne(serree, retrait)
        h = ligne.rangee
        libelle = QLabel(libelle_txt)
        libelle.setTextFormat(Qt.TextFormat.PlainText)
        libelle.setWordWrap(True)
        libelle.setMinimumWidth(1)
        libelle.setFont(police(14))
        libelle.setStyleSheet("color: #ecebf3; background: transparent;")
        h.addWidget(libelle, stretch=1)
        aide = BoutonAide(libelle_txt, self._fiche(aide_txt, reglage))
        h.addWidget(aide, alignment=Qt.AlignmentFlag.AlignVCenter)
        self._aides[reglage.ident if reglage is not None else libelle_txt] = aide
        if serree:
            self._reperes(h, reglage)
        if isinstance(controle, ToggleSwitch):
            # Le libellé est à côté, pas dedans : sans nom accessible, un lecteur
            # d'écran n'annoncerait qu'« interrupteur » (règle 15).
            controle.setToolTip(libelle_txt)
        controle.setAccessibleName(libelle_txt)
        controle.setAccessibleDescription(aide_txt)
        case = QWidget()
        case.setObjectName("caseControle")
        case.setStyleSheet("background: transparent;")
        hc = QHBoxLayout(case)
        hc.setContentsMargins(0, 0, 0, 0)
        hc.addStretch()
        hc.addWidget(controle)
        h.addWidget(case)
        return ligne

    def _reperes(self, ligne: QHBoxLayout, reglage) -> None:
        """L'œil s'il se VOIT à l'écran, les trois points de ce qu'il coûte.

        Chacun à sa place même vide : les colonnes tombent l'une sous l'autre
        d'une ligne à la suivante.
        """
        oeil = QLabel()
        oeil.setFixedSize(18, 18)
        oeil.setStyleSheet("background: transparent;")
        if reglage.se_voit:
            oeil.setPixmap(pixmap_icone("oeil", 18, QColor(_COULEUR_SE_VOIT)))
            oeil.setToolTip(tr("Se voit nettement à l’écran."))
        ligne.addWidget(oeil)
        niveau = max((n for _r, n in reglage.cout), default=0)
        points = _Points(niveau)
        if niveau:
            detail = "\n".join(f"{tr(_RESSOURCES.get(r, r))} : {tr(_NIVEAUX[n])}"
                               for r, n in reglage.cout)
            points.setToolTip(detail)
            points.setAccessibleName(detail)
        ligne.addWidget(points)
        ligne.addSpacing(6)

    @staticmethod
    def _egaliser(carte: QWidget) -> None:
        """Une seule largeur pour les listes et la colonne des contrôles d'une carte :
        une liste plus large que les autres, des interrupteurs qui ne tombent pas
        sur le même bord, c'était le désordre de l'ancienne fenêtre."""
        listes = carte.findChildren(QComboBox)
        largeur = max([c.sizeHint().width() for c in listes] + [48])
        largeur = min(largeur, 260)
        for liste in listes:
            liste.setFixedWidth(largeur)
        for case in carte.findChildren(QWidget, "caseControle"):
            case.setFixedWidth(largeur)

    def _controle(self, carte, ini: Path, reglage, retrait: bool = False) -> None:
        try:
            etat = reglages_correctif.lire(ini, reglage)
        except OSError:
            log.warning("Correctif : %s illisible", ini, exc_info=True)
            return
        libelle_txt, aide_txt = reglages_correctif.textes(reglage)
        if reglage.choix:
            choix = self._liste()
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
            controle = choix
        else:
            controle = ToggleSwitch(bool(etat.valeur))
            controle.toggled.connect(
                lambda coche, r=reglage, b=controle: self._on_reglage(r, coche, b))
            self._controles[reglage.ident] = controle
        ligne = self._ligne(libelle_txt, controle, aide_txt, reglage, retrait)
        if not reglage.choix and etat.personnalise:
            # Quelques lignes du panneau allumées à la main : rien n'est
            # perdu à le dire, et l'interrupteur reste libre.
            ligne.note.setText(tr(
                "Réglé en partie à la main dans d3d9.ini : l'activer allume tout le panneau."))
            ligne.note.show()
        self._blocs[reglage.ident] = ligne
        carte.ajouter(ligne)

    # ── Réaction ──

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
            self._bouton_reset.setEnabled(reglages_correctif.a_une_origine(self._ini))
            self._bouton_reset.setToolTip(tr("Remet image, commandes et performances "
                                             "comme à l'installation du jeu."))
        if not self._erreur.isHidden():
            self._erreur.hide()
