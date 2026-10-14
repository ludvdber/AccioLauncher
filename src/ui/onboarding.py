"""Assistant de premier lancement, refait le 2026-10-09 sur la maquette validée.

Un écran de langue, plein cadre, puis quatre étapes dans une fenêtre à rail :

1. Langue. Volontairement en PREMIER et seule : c'est ce qui fait naître la
   suite déjà traduite, alors qu'aucune config n'existe encore. Elle est
   pré-choisie sur la langue du système (`detect_system_language`), anglais en
   repli, et l'écran se retraduit dès qu'on en touche une autre.
2. Dossier : où ranger les jeux, la place qu'il faut, et ce qu'il contient déjà.
3. Vos jeux. Ceux qui sont DÉJÀ dans le dossier sont repris d'office : une
   config effacée ou un launcher réinstallé ne fait plus repartir de zéro
   (Ludo, 2026-10-09). D'autres se montrent depuis un autre dossier et y sont
   déplacés (même disque : instantané).
4. Le Choixpeau, une question à la fois, puis son verdict : l'assistant prend
   aussitôt les couleurs de la maison.
5. Dernières touches : couleurs du launcher, bandes-annonces.

**Rattrapage** (`run_rattrapage`) : à quelqu'un qui avait le launcher avant le
Choixpeau et les bandes-annonces, seules les étapes jamais vues, une fois
(`src/core/assistant.py`).

Les étapes ne sont construites qu'à la sortie de l'écran de langue, une fois
`set_language()` appelé : les `tr()` sont évalués à la construction.
"""

import logging
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QStackedWidget, QVBoxLayout, QWidget,
)

from src.core import manette
from src.core.assistant import CHOIXPEAU, ETAPES_RATTRAPABLES, TOUCHES, etapes_a_rattraper
from src.core.choixpeau import QUESTIONS, question, reponses, repartir, verdict
from src.core.config import ASSETS_DIR, DEFAULT_INSTALL_PATH, Config, cache_pour
from src.core.formatting import format_bytes, format_size
from src.core.game_data import GameData, load_catalog
from src.core.i18n import available_languages, detect_system_language, set_language, tr
from src.ui.assistant_widgets import (
    STYLE, BarreDisque, CarteCouleur, CarteLangue, CarteReponse, LigneJeu, Progression,
    RailEtapes, bouton_suivant, lien, surtitre_etape, titre_etape,
)
from src.ui.composants import (
    ENCRE_DISCRETE, ENCRE_DOUCE, Carte, Chemin, LigneReglage, Pastille, bouton,
    espace_du_volume, feuille_de_style, police, texte,
)
from src.ui.ecu import Ecu
from src.ui.fonts import cinzel, cinzel_decorative
from src.ui.icon_button import pixmap_icone
from src.ui.theme import THEMES, accent_qcolor, current as theme_courant, set_theme, themed
from src.ui.toggle_switch import ToggleSwitch
from src.ui.utils import avertir, is_writable_dir, zone_defilable

log = logging.getLogger(__name__)

# Les écrans de la fenêtre à rail. Le verdict n'est pas une étape : il clôt
# celle du Choixpeau, et le rail reste dessus.
DOSSIER, JEUX, CHOIXPEAU_Q, VERDICT, DERNIERES = "dossier", "jeux", "choixpeau", "verdict", "touches"
_ETAPE_DU_RAIL = {DOSSIER: DOSSIER, JEUX: JEUX, CHOIXPEAU_Q: CHOIXPEAU_Q,
                  VERDICT: CHOIXPEAU_Q, DERNIERES: DERNIERES}
_NOMS_DU_RAIL = {DOSSIER: "Dossier", JEUX: "Vos jeux", CHOIXPEAU_Q: "Le Choixpeau",
                 DERNIERES: "Dernières touches"}
_VERT = "#5fbf86"
_ORANGE = "#e0a05a"
_LARGEUR_LECTURE = 720


class OnboardingAnnule(Exception):
    """L'assistant a été fermé sans être terminé.

    Levée au lieu de rendre une `Config` de défaut : écrire une config ICI
    démarrait le launcher comme si l'assistant avait abouti, ET rendait
    `Config.exists()` vrai, si bien que l'assistant ne revenait JAMAIS —
    fermer la fenêtre ne reportait donc pas l'installation, elle la sautait
    définitivement (Ludo, 2026-09-23). Ne rien écrire est la seule façon de
    tenir la promesse implicite de la croix : « pas maintenant ».
    """


def detect_installed_games(parent: Path, games: list[GameData]) -> list[tuple[GameData, Path]]:
    """Détecte les installations existantes sous `parent` (fonction pure).

    Un jeu est détecté si le dossier attendu (1er segment de `executable`)
    existe et contient l'exécutable relatif. Retourne [(jeu, dossier_source)].
    """
    found: list[tuple[GameData, Path]] = []
    for game in games:
        parts = Path(game.executable).parts
        if len(parts) < 2:
            continue
        candidate = parent / parts[0]
        if (candidate / Path(*parts[1:])).exists():
            found.append((game, candidate))
    return found


def _meme_dossier(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def _meme_disque(a: Path, b: Path) -> bool:
    try:
        return a.resolve().drive.lower() == b.resolve().drive.lower()
    except OSError:
        return False


def poids_installe(game: GameData) -> int:
    """Ce que pèse le jeu installé, en octets (version recommandée)."""
    for version in game.versions:
        if version.version == game.recommended_version:
            return version.size_mb * 1024 * 1024
    return 0


class OnboardingDialog(QDialog):
    """L'assistant, modal, affiché avant la construction de MainWindow.

    `config` et `rattrapage` : la version courte, pour une config existante.
    """

    def __init__(self, config: Config | None = None, rattrapage: tuple[str, ...] = ()) -> None:
        super().__init__()
        self.setObjectName("assistant")
        self.setWindowTitle(tr("Bienvenue dans Accio Launcher") if config else "Accio Launcher")
        self.setMinimumSize(860, 600)
        self.resize(960, 640)
        self._rattrapage = tuple(e for e in ETAPES_RATTRAPABLES if e in rattrapage)

        # Résultats lus par run_onboarding() / run_rattrapage() après accept().
        base = config or Config()
        self.install_path: Path = base.install_path if config else DEFAULT_INSTALL_PATH
        self.langue = base.langue if config else detect_system_language()
        self._theme_initial = base.theme if config else "poudlard"
        self.theme = self._theme_initial
        self.autoplay = base.autoplay_videos
        # Muet par défaut : c'est le réglage de `Config.mute_videos`, et
        # l'assistant ne fait que le rendre visible.
        self.mute_videos = base.mute_videos
        self.trailers_optin = True
        self._reponses = [-1] * len(QUESTIONS)
        self._question = 0
        self._maison = ""
        self._en_place: list[tuple[GameData, Path]] = []
        self._ailleurs: list[tuple[GameData, Path]] = []
        self._dossier_cherche: Path | None = None
        self._coches: dict[str, bool] = {}
        self._lignes: dict[str, LigneJeu] = {}
        self._icones: list[tuple[QLabel, str, int]] = []
        self._catalogue = load_catalog()
        self._games = list(self._catalogue.games)
        self._etapes: QWidget | None = None
        self._ecran = ""
        self._ecrans: list[str] = []

        racine = QVBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        self._racine = QStackedWidget()
        racine.addWidget(self._racine)
        if config is None:
            set_language(self.langue)
            self._racine.addWidget(self._page_langue())
        else:
            set_theme(self.theme)
            self._construire_etapes()
        self._appliquer_style()

    # ── Style et couleurs ──

    def _appliquer_style(self) -> None:
        self.setStyleSheet(themed(STYLE) + feuille_de_style())
        for lbl, nom, taille in self._icones:
            lbl.setPixmap(pixmap_icone(nom, taille, accent_qcolor()))

    def _appliquer_theme(self, theme_id: str) -> None:
        """Les couleurs d'une maison, tout de suite : rien n'est reconstruit."""
        if theme_courant().id == theme_id:
            return
        set_theme(theme_id)
        self._appliquer_style()

    def _icone(self, nom: str, taille: int = 22, couleur: str = "") -> QLabel:
        """Un pictogramme posé dans un libellé ; doré, il suit la maison."""
        lbl = QLabel()
        lbl.setFixedSize(taille, taille)
        lbl.setStyleSheet("background: transparent;")
        if couleur:
            lbl.setPixmap(pixmap_icone(nom, taille, QColor(couleur)))
        else:
            lbl.setPixmap(pixmap_icone(nom, taille, accent_qcolor()))
            self._icones.append((lbl, nom, taille))
        return lbl

    # ── Écran de langue ──

    def _page_langue(self) -> QWidget:
        """Plein cadre, neutre : chaque carte est écrite dans sa propre langue."""
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(40, 30, 40, 30)
        lay.setSpacing(0)
        lay.addStretch(3)

        logo = QLabel()
        logo.setStyleSheet("background: transparent;")
        ecran = QGuiApplication.primaryScreen()
        ratio = ecran.devicePixelRatio() if ecran is not None else 1.0
        pm = QPixmap(str(ASSETS_DIR / "accio_logo_horizontal.png"))
        if not pm.isNull():
            pm = pm.scaledToWidth(round(300 * ratio), Qt.TransformationMode.SmoothTransformation)
            pm.setDevicePixelRatio(ratio)
            logo.setPixmap(pm)
        lay.addWidget(logo, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(30)

        langues = QLabel("Langue · Language · Idioma")
        f = cinzel(10, bold=True)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 4)
        langues.setFont(f)
        langues.setStyleSheet("color: #a9a7c4; background: transparent;")
        lay.addWidget(langues, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(22)

        rangee = QHBoxLayout()
        rangee.setSpacing(16)
        rangee.addStretch()
        self._groupe_langue = QButtonGroup(page)
        self._cartes_langue: list[CarteLangue] = []
        for info in available_languages():
            carte = CarteLangue(info.code, info.name)
            self._groupe_langue.addButton(carte)
            self._cartes_langue.append(carte)
            rangee.addWidget(carte)
            if info.code == self.langue:
                carte.setChecked(True)
        rangee.addStretch()
        lay.addLayout(rangee)
        self._groupe_langue.buttonClicked.connect(self._sur_langue)
        lay.addSpacing(22)

        self._aide_langue = texte("", 13, ENCRE_DOUCE, retour=True)
        self._aide_langue.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self._aide_langue)
        lay.addSpacing(30)
        self._continuer = bouton_suivant("")
        self._continuer.clicked.connect(self._quitter_la_langue)
        lay.addWidget(self._continuer, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(4)
        self._traduire_la_langue()
        return page

    def _traduire_la_langue(self) -> None:
        self._aide_langue.setText(tr("Choisie d'après votre système. "
                                     "Elle se change plus tard dans les Paramètres."))
        self._continuer.setText(tr("Suivant"))

    def langue_choisie(self) -> str:
        carte = self._groupe_langue.checkedButton()
        return carte.code if isinstance(carte, CarteLangue) else self.langue

    def choisir_langue(self, code: str) -> None:
        for carte in self._cartes_langue:
            if carte.code == code:
                carte.setChecked(True)
                self._sur_langue(carte)

    def _sur_langue(self, carte) -> None:
        """L'écran se retraduit au clic : on voit tout de suite ce qu'on choisit."""
        set_language(carte.code)
        self._traduire_la_langue()

    def _quitter_la_langue(self) -> None:
        choisie = self.langue_choisie()
        # Déjà passé par ici dans une AUTRE langue : les étapes existent,
        # figées dans celle d'avant (`tr()` est évalué à la construction).
        if self._etapes is not None and choisie != self.langue:
            self._oublier_les_etapes()
        self.langue = choisie
        set_language(self.langue)
        # Le catalogue résout ses traductions AU PARSING : relu une fois la
        # langue connue, sinon les noms de jeux resteraient en français.
        self._catalogue = load_catalog()
        self._games = list(self._catalogue.games)
        self.setWindowTitle(tr("Bienvenue dans Accio Launcher"))
        if self._etapes is None:
            self._construire_etapes()
        self._racine.setCurrentWidget(self._etapes)
        self._afficher(self._ecrans[0])

    def _oublier_les_etapes(self) -> None:
        """Jette les étapes pour les rebâtir dans une autre langue.

        Les réponses déjà données (dossier, jeux cochés, Choixpeau) vivent dans
        des attributs, pas dans les widgets : elles survivent au rebâti.
        """
        self._racine.removeWidget(self._etapes)
        self._etapes.deleteLater()
        self._etapes = None
        # Les pictogrammes dorés partent avec les étapes ; l'écran de langue n'en a pas.
        self._icones = []
        self._lignes = {}

    # ── Fenêtre à rail ──

    def _construire_etapes(self) -> None:
        plein = not self._rattrapage
        if plein:
            self._ecrans = [DOSSIER, JEUX, CHOIXPEAU_Q, VERDICT, DERNIERES]
        else:
            self._ecrans = ([CHOIXPEAU_Q, VERDICT] if CHOIXPEAU in self._rattrapage else []) \
                + ([DERNIERES] if TOUCHES in self._rattrapage else [])
        self._rail_noms = [e for e in self._ecrans if e != VERDICT]

        self._etapes = QWidget()
        self._etapes.setStyleSheet("background: transparent;")
        h = QHBoxLayout(self._etapes)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        rail = QFrame()
        rail.setObjectName("railAssistant")
        rail.setFixedWidth(232)
        v = QVBoxLayout(rail)
        v.setContentsMargins(24, 30, 24, 24)
        v.setSpacing(0)
        marque = QLabel("Accio Launcher")
        marque.setObjectName("marque")
        marque.setFont(cinzel(12, bold=True))
        v.addWidget(marque)
        v.addSpacing(26)
        self._rail = RailEtapes([tr(_NOMS_DU_RAIL[e]) for e in self._rail_noms],
                                premiere_faite=tr("Langue") if plein else "")
        v.addWidget(self._rail)
        v.addStretch()
        note = tr("Tout se change plus tard, dans les Paramètres.") if plein else tr(
            "Ce que le launcher ne vous avait encore jamais montré. "
            "Tout se change plus tard, dans les Paramètres.")
        v.addWidget(texte(note, 12, "#5f5d80", retour=True))
        h.addWidget(rail)

        droite = QVBoxLayout()
        droite.setContentsMargins(0, 0, 0, 0)
        droite.setSpacing(0)
        self._pile = QStackedWidget()
        self._zones: dict[str, QWidget] = {}
        for ecran in self._ecrans:
            zone = zone_defilable(self._construire(ecran))
            self._zones[ecran] = zone
            self._pile.addWidget(zone)
        droite.addWidget(self._pile, stretch=1)
        droite.addWidget(self._pied())
        h.addLayout(droite, stretch=1)
        self._racine.addWidget(self._etapes)
        self._racine.setCurrentWidget(self._etapes)
        if not plein:
            self._afficher(self._ecrans[0])

    def _pied(self) -> QFrame:
        pied = QFrame()
        pied.setObjectName("piedAssistant")
        pied.setFixedHeight(72)
        lay = QHBoxLayout(pied)
        lay.setContentsMargins(44, 0, 44, 0)
        lay.setSpacing(12)
        self._btn_retour = bouton(tr("Retour"))
        self._btn_retour.setAutoDefault(False)
        self._btn_retour.clicked.connect(self._retour)
        lay.addWidget(self._btn_retour)
        lay.addStretch()
        self._fin = texte(tr("C'est tout. Bon retour à Poudlard."), 13, ENCRE_DOUCE)
        lay.addWidget(self._fin)
        self._lien = lien("")
        self._lien.clicked.connect(self._sur_lien)
        lay.addWidget(self._lien)
        self._btn_suivant = bouton_suivant("")
        self._btn_suivant.clicked.connect(self._suivant)
        lay.addWidget(self._btn_suivant)
        return pied

    def _construire(self, ecran: str) -> QWidget:
        return {DOSSIER: self._page_dossier, JEUX: self._page_jeux,
                CHOIXPEAU_Q: self._page_choixpeau, VERDICT: self._page_verdict,
                DERNIERES: self._page_dernieres}[ecran]()

    def _squelette(self, ecran: str, titre: str = "", lede: str = "") -> tuple[QWidget, QVBoxLayout]:
        """Surtitre, titre, phrase d'entrée : le haut commun des étapes."""
        cadre = QWidget()
        cadre.setStyleSheet("background: transparent;")
        h = QHBoxLayout(cadre)
        h.setContentsMargins(44, 36, 44, 24)
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        page.setMaximumWidth(_LARGEUR_LECTURE)
        h.addWidget(page, stretch=1)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(surtitre_etape(self._surtitre(ecran)))
        if titre:
            lay.addSpacing(6)
            lay.addWidget(titre_etape(titre))
        if lede:
            lay.addSpacing(10)
            phrase = texte(lede, 15, "#a9a7c4", retour=True)
            phrase.setMaximumWidth(580)
            lay.addWidget(phrase)
        return cadre, lay

    def _surtitre(self, ecran: str) -> str:
        if ecran == VERDICT:
            return tr("Le Choixpeau a parlé")
        rang = self._rail_noms.index(_ETAPE_DU_RAIL[ecran])
        if self._rattrapage:
            return tr("Nouveau · étape {n} sur {total}").format(n=rang + 1, total=len(self._rail_noms))
        return tr("Étape {n} sur {total}").format(n=rang + 2, total=len(self._rail_noms) + 1)

    # ── Étape : dossier ──

    def _page_dossier(self) -> QWidget:
        page, lay = self._squelette(DOSSIER, tr("Où ranger les jeux ?"), tr(
            "Les jeux seront installés ici. Les fichiers du launcher tiennent dans un seul "
            "sous-dossier, _Launcher : le reste, ce sont vos jeux."))
        lay.addSpacing(26)
        carte = Carte()
        self._chemin = Chemin(str(self.install_path))
        changer = bouton(tr("Changer…"))
        changer.clicked.connect(self._changer_dossier)
        self._ligne_dossier = LigneReglage(self._chemin, "", changer, icone=self._icone("dossier"))
        carte.ajouter(self._ligne_dossier)

        disque = QWidget()
        disque.setStyleSheet("background: transparent;")
        v = QVBoxLayout(disque)
        v.setContentsMargins(20, 16, 20, 18)
        v.setSpacing(10)
        self._barre = BarreDisque()
        v.addWidget(self._barre)
        legende = QHBoxLayout()
        legende.setSpacing(7)
        legende.addWidget(Pastille(QColor(255, 255, 255, 56)))
        legende.addWidget(texte(tr("Déjà occupé"), 12, ENCRE_DOUCE))
        legende.addSpacing(14)
        self._pastille_saga = Pastille(accent_qcolor())
        legende.addWidget(self._pastille_saga)
        self._legende_saga = texte("", 12, ENCRE_DOUCE)
        legende.addWidget(self._legende_saga)
        legende.addStretch()
        self._libre = texte("", 12, "#d9d6e8")
        legende.addWidget(self._libre)
        v.addLayout(legende)
        carte.ajouter(disque)

        avis = QWidget()
        avis.setStyleSheet("background: transparent;")
        a = QHBoxLayout(avis)
        a.setContentsMargins(20, 12, 20, 14)
        a.setSpacing(12)
        self._picto_place = QLabel()
        self._picto_place.setFixedSize(18, 18)
        a.addWidget(self._picto_place, alignment=Qt.AlignmentFlag.AlignTop)
        self._texte_place = texte("", 13, "#b9d8c4", retour=True)
        a.addWidget(self._texte_place, stretch=1)
        carte.ajouter(avis)
        lay.addWidget(carte)
        lay.addStretch()
        lay.addSpacing(18)
        # Dit une fois, avant le premier téléchargement : c'est le seul écran
        # que tout le monde voit.
        lay.addWidget(texte(tr(
            "Les jeux restent la propriété de Warner Bros. et d'Electronic Arts : "
            "pour y jouer légalement, il faut en posséder une copie originale "
            "(CD, DVD ou achat numérique)."), 12, ENCRE_DISCRETE, retour=True))
        self._regler_dossier()
        return page

    def _regler_dossier(self) -> None:
        self._en_place = (detect_installed_games(self.install_path, self._games)
                          if self.install_path.is_dir() else [])
        presents = {g.id for g, _ in self._en_place}
        saga = sum(poids_installe(g) for g in self._games if g.id not in presents)
        libre, total = espace_du_volume(self.install_path)
        self._chemin.definir(str(self.install_path))
        self._ligne_dossier.decrire(
            tr("Dossier proposé. Un dossier à vous, hors de Program Files.")
            if self.install_path == DEFAULT_INSTALL_PATH else tr("Dossier choisi."))
        self._barre.regler(total - libre, saga, total)
        self._legende_saga.setText(
            (tr("Les jeux qui manquent · {}") if presents else tr("Toute la saga · {}"))
            .format(format_bytes(saga)))
        self._pastille_saga.setVisible(saga > 0)
        self._legende_saga.setVisible(saga > 0)
        self._libre.setText(tr("{libre} libres sur {total}").format(
            libre=format_bytes(libre), total=format_bytes(total)) if total else tr("Espace libre inconnu"))

        phrases = []
        n = len(presents)
        if n == 1:
            phrases.append(tr("Ce dossier contient déjà un jeu : il sera repris tel quel."))
        elif n > 1:
            phrases.append(tr("Ce dossier contient déjà {} jeux : ils seront repris tels quels.").format(n))
        assez = not total or libre >= saga
        if saga and total:
            if not assez:
                phrases.append(tr("Il manque {} pour toute la saga. Chaque jeu se télécharge à part : "
                                  "vous pourrez en installer une partie.").format(format_bytes(saga - libre)))
            elif presents:
                phrases.append(tr("Assez de place pour ceux qui manquent."))
            else:
                phrases.append(tr("Assez de place pour toute la saga. "
                                  "Chaque jeu se télécharge quand vous le choisissez."))
        couleur = _VERT if assez else _ORANGE
        self._picto_place.setPixmap(pixmap_icone("coche" if assez else "attention", 18, QColor(couleur)))
        self._texte_place.setStyleSheet(
            f"color: {'#b9d8c4' if assez else '#ecc896'}; background: transparent;")
        self._texte_place.setText(" ".join(phrases))
        self._picto_place.parentWidget().setVisible(bool(phrases))

    def _changer_dossier(self) -> None:
        choisi = QFileDialog.getExistingDirectory(
            self, tr("Dossier d'installation des jeux"), str(self.install_path))
        if not choisi:
            return
        self.install_path = Path(choisi)
        if self._dossier_cherche is not None and _meme_dossier(self._dossier_cherche, self.install_path):
            self._dossier_cherche = None
        self._regler_dossier()
        self._regler_jeux()

    # ── Étape : vos jeux ──

    def _page_jeux(self) -> QWidget:
        page, lay = self._squelette(JEUX, tr("Vous avez déjà des jeux ?"), tr(
            "Ceux qui sont déjà dans le dossier du launcher sont repris tels quels. "
            "D'autres ailleurs ? Montrez le dossier qui les contient."))
        lay.addSpacing(22)
        self._hote_jeux = QVBoxLayout()
        self._hote_jeux.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(self._hote_jeux)
        lay.addSpacing(14)
        self._note_jeux = texte(tr(
            "Les jeux cochés sont déplacés dans le dossier du launcher, pas copiés : "
            "sur un même disque, c'est instantané."), 13, ENCRE_DOUCE, retour=True)
        lay.addWidget(self._note_jeux)
        lay.addStretch()
        self._carte_jeux: Carte | None = None
        self._regler_jeux()
        return page

    def _regler_jeux(self) -> None:
        """Rebâtit la carte des jeux : ceux du dossier, puis ceux trouvés ailleurs."""
        if self._carte_jeux is not None:
            self._hote_jeux.removeWidget(self._carte_jeux)
            self._carte_jeux.deleteLater()
        presents = {g.id for g, _ in self._en_place}
        self._ailleurs = []
        if self._dossier_cherche is not None:
            self._ailleurs = [(g, src) for g, src in detect_installed_games(self._dossier_cherche, self._games)
                              if g.id not in presents]
        carte = Carte()
        if self._dossier_cherche is not None:
            n = len(self._ailleurs)
            etat = (tr("1 jeu reconnu") if n == 1 else tr("{} jeux reconnus").format(n)) if n \
                else tr("Aucun jeu reconnu dans ce dossier.")
            tete = LigneReglage(Chemin(str(self._dossier_cherche)), etat, self._bouton_chercher(tr("Autre dossier…")),
                                icone=self._icone("dossier"))
        elif self._en_place:
            n = len(self._en_place)
            etat = tr("1 jeu déjà dans le dossier du launcher") if n == 1 \
                else tr("{} jeux déjà dans le dossier du launcher").format(n)
            tete = LigneReglage(Chemin(str(self.install_path)), etat,
                                self._bouton_chercher(tr("Chercher ailleurs…")), icone=self._icone("dossier"))
        else:
            tete = LigneReglage(tr("Aucun jeu dans le dossier du launcher pour l'instant."),
                                tr("Si vous en avez installé ailleurs, montrez le dossier qui les contient."),
                                self._bouton_chercher(tr("Chercher dans un dossier…")), icone=self._icone("dossier"))
        if self._dossier_cherche is not None or self._en_place:
            tete.description.setStyleSheet(themed("color: #e8c547; background: transparent;"))
        carte.ajouter(tete)

        self._lignes = {}
        for game, src in self._en_place:
            carte.ajouter(LigneJeu(game.name, game.cover_image, str(src), tr("Déjà en place")))
        for game, src in self._ailleurs:
            if _meme_disque(src, self.install_path):
                ligne = LigneJeu(game.name, game.cover_image, str(src))
                ligne.setChecked(self._coches.get(game.id, True))
                ligne.toggled.connect(lambda coche, gid=game.id: self._cocher(gid, coche))
                self._lignes[game.id] = ligne
            else:
                ligne = LigneJeu(game.name, game.cover_image, str(src),
                                 tr("Autre disque : à déplacer à la main"), "#ecc896")
            carte.ajouter(ligne)
        self._carte_jeux = carte
        self._hote_jeux.addWidget(carte)
        self._note_jeux.setVisible(bool(self._lignes))
        if self._ecran == JEUX:
            self._regler_pied()

    def _bouton_chercher(self, libelle: str):
        btn = bouton(libelle)
        btn.clicked.connect(self._chercher_ailleurs)
        return btn

    def _chercher_ailleurs(self) -> None:
        choisi = QFileDialog.getExistingDirectory(
            self, tr("Dossier contenant vos jeux"), str(Path.home()))
        if not choisi:
            return
        dossier = Path(choisi)
        # Montrer le dossier du launcher lui-même : ses jeux sont déjà repris.
        self._dossier_cherche = None if _meme_dossier(dossier, self.install_path) else dossier
        self._regler_jeux()

    def _cocher(self, game_id: str, coche: bool) -> None:
        self._coches[game_id] = coche
        self._regler_pied()

    def _a_deplacer(self) -> int:
        return sum(1 for ligne in self._lignes.values() if ligne.isChecked())

    def checked_imports(self) -> list[tuple[GameData, Path]]:
        """Les jeux déjà en place (à inscrire) et ceux cochés ailleurs (à déplacer)."""
        coches = [(g, src) for g, src in self._ailleurs
                  if g.id in self._lignes and self._lignes[g.id].isChecked()]
        return list(self._en_place) + coches

    # ── Étape : le Choixpeau ──

    def _page_choixpeau(self) -> QWidget:
        page, lay = self._squelette(CHOIXPEAU_Q, tr("Le Choixpeau"), tr(
            "« Voyons voir… où vais-je bien pouvoir vous mettre ? » "
            "Quatre questions, et votre maison donnera ses couleurs au launcher."))
        lay.addSpacing(24)
        rang = QHBoxLayout()
        rang.setSpacing(12)
        self._progression = Progression(len(QUESTIONS))
        rang.addWidget(self._progression, alignment=Qt.AlignmentFlag.AlignVCenter)
        self._compte = texte("", 12, ENCRE_DOUCE)
        rang.addWidget(self._compte)
        rang.addStretch()
        lay.addLayout(rang)
        lay.addSpacing(14)
        self._intitule = QLabel()
        self._intitule.setTextFormat(Qt.TextFormat.PlainText)
        self._intitule.setWordWrap(True)
        f = police(21)
        f.setItalic(True)
        self._intitule.setFont(f)
        self._intitule.setStyleSheet("color: #f4f2f8; background: transparent;")
        lay.addWidget(self._intitule)
        lay.addSpacing(18)
        grille = QGridLayout()
        grille.setSpacing(12)
        self._groupe_reponses = QButtonGroup(self)
        self._cartes_reponse: list[CarteReponse] = []
        for i in range(4):
            carte = CarteReponse()
            self._groupe_reponses.addButton(carte, i)
            self._cartes_reponse.append(carte)
            grille.addWidget(carte, i // 2, i % 2)
        grille.setColumnStretch(0, 1)
        grille.setColumnStretch(1, 1)
        self._groupe_reponses.idClicked.connect(self._sur_reponse)
        lay.addLayout(grille)
        lay.addStretch()
        self._regler_question()
        return page

    def _regler_question(self) -> None:
        q = self._question
        self._progression.regler(q)
        self._compte.setText(tr("Question {n} sur {total}").format(n=q + 1, total=len(QUESTIONS)))
        self._intitule.setText(question(q))
        self._groupe_reponses.setExclusive(False)
        for i, (carte, contenu) in enumerate(zip(self._cartes_reponse, reponses(q))):
            carte.dire(contenu)
            carte.setChecked(self._reponses[q] == i)
        self._groupe_reponses.setExclusive(True)

    def _sur_reponse(self, rang: int) -> None:
        self._reponses[self._question] = rang
        self._regler_pied()

    def _repartir(self) -> None:
        """Dépouille les réponses : la maison, ou rien si personne n'a répondu."""
        self._maison = repartir(self._reponses)
        if self._maison:
            self.theme = self._maison
            # Le Choixpeau a parlé : la manette, si elle est là, le sait aussitôt.
            manette.colorer_en_fond(self._maison)

    def _oublier_le_choixpeau(self) -> None:
        self._reponses = [-1] * len(QUESTIONS)
        self._question = 0
        self._maison = ""
        self.theme = self._theme_initial
        self._regler_question()

    # ── Le verdict ──

    def _page_verdict(self) -> QWidget:
        # Pas de titre : c'est le cri de la maison, en grand sous l'écu.
        page, lay = self._squelette(VERDICT)
        lay.addStretch()
        self._hote_ecu = QHBoxLayout()
        self._hote_ecu.addStretch()
        self._ecu: QWidget | None = None
        self._hote_ecu.addStretch()
        lay.addLayout(self._hote_ecu)
        lay.addSpacing(26)
        self._devise = QLabel()
        self._devise.setTextFormat(Qt.TextFormat.PlainText)
        self._devise.setWordWrap(True)
        self._devise.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        f = police(21)
        f.setItalic(True)
        self._devise.setFont(f)
        self._devise.setStyleSheet("color: #e9e6f2; background: transparent;")
        lay.addWidget(self._devise)
        lay.addSpacing(12)
        self._cri = QLabel()
        self._cri.setObjectName("marque")
        self._cri.setTextFormat(Qt.TextFormat.PlainText)
        self._cri.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._cri.setFont(cinzel_decorative(28, QFont.Weight.Bold))
        lay.addWidget(self._cri)
        lay.addSpacing(18)
        self._note_verdict = texte("", 13, ENCRE_DOUCE, retour=True)
        self._note_verdict.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self._note_verdict)
        lay.addStretch()
        return page

    def _regler_verdict(self) -> None:
        if self._ecu is not None:
            self._hote_ecu.removeWidget(self._ecu)
            self._ecu.deleteLater()
        self._ecu = Ecu(self._maison, hauteur=132)
        self._hote_ecu.insertWidget(1, self._ecu)
        devise, cri = verdict(self._maison)
        self._devise.setText(tr("« {} »").format(devise))
        self._cri.setText(cri)
        self._note_verdict.setText(tr(
            "Le launcher prend déjà les couleurs de {maison}. "
            "Vous pourrez en choisir d'autres à l'étape suivante.").format(maison=tr(THEMES[self._maison].nom)))

    # ── Étape : dernières touches ──

    def _page_dernieres(self) -> QWidget:
        page, lay = self._squelette(DERNIERES, tr("Dernières touches"), tr(
            "Trois questions de goût, et la bibliothèque s'ouvre."))
        lay.addSpacing(24)
        lay.addWidget(surtitre_etape(tr("Couleurs du launcher")))
        lay.addSpacing(10)
        rangee = QHBoxLayout()
        rangee.setSpacing(10)
        self._groupe_couleurs = QButtonGroup(self)
        self._cartes_couleur: dict[str, CarteCouleur] = {}
        for palette in THEMES.values():
            nom = tr("Poudlard") if palette.id == "poudlard" else tr(palette.nom)
            carte = CarteCouleur(palette.id, nom)
            self._groupe_couleurs.addButton(carte)
            self._cartes_couleur[palette.id] = carte
            rangee.addWidget(carte, stretch=1)
        self._groupe_couleurs.buttonClicked.connect(lambda c: self._choisir_couleur(c.theme_id))
        lay.addLayout(rangee)

        lay.addSpacing(24)
        lay.addWidget(surtitre_etape(tr("Bandes-annonces")))
        lay.addSpacing(10)
        carte = Carte()
        # Les bandes-annonces ne sont PAS dans l'exécutable : elles pèsent des
        # centaines de Mo pour un ornement, et tout le monde n'en veut pas. On
        # demande donc, en annonçant le poids.
        poids = sum(t.size_mb for t in self._catalogue.trailers)
        self._tgl_trailers: ToggleSwitch | None = None
        if poids:
            ligne, self._tgl_trailers = self._interrupteur(
                tr("Télécharger les bandes-annonces"), True,
                tr("Une vidéo par jeu, {taille} en tout. Elles se suppriment d'un clic "
                   "dans les Paramètres.").format(taille=format_size(poids)))
            carte.ajouter(ligne)
        ligne, self._tgl_autoplay = self._interrupteur(
            tr("Les lire automatiquement sur la fiche"), self.autoplay)
        carte.ajouter(ligne)
        # Le son, DÉCOCHÉ par défaut : une bande-annonce se lance toute seule
        # dès la première fiche, et du son qui part sans prévenir fait
        # sursauter. Le poser ici le rend découvrable sans l'imposer.
        ligne, self._tgl_son = self._interrupteur(
            tr("Avec le son"), not self.mute_videos,
            tr("Coupé par défaut : rien ne part fort à l'ouverture."))
        carte.ajouter(ligne)
        lay.addWidget(carte)
        lay.addStretch()
        return page

    @staticmethod
    def _interrupteur(titre: str, coche: bool, phrase: str = "") -> tuple[LigneReglage, ToggleSwitch]:
        bascule = ToggleSwitch(coche)
        bascule.setAccessibleName(titre)
        return LigneReglage(titre, phrase, bascule), bascule

    def _regler_dernieres(self) -> None:
        for theme_id, carte in self._cartes_couleur.items():
            carte.annoter(tr("Choisie par le Choixpeau") if theme_id == self._maison else "")
            carte.setChecked(theme_id == self.theme)

    def _choisir_couleur(self, theme_id: str) -> None:
        self.theme = theme_id
        self._appliquer_theme(theme_id)

    # ── Navigation ──

    def _afficher(self, ecran: str) -> None:
        self._ecran = ecran
        # Chaque écran porte ses couleurs : celles d'avant le Choixpeau,
        # la maison au verdict, la couleur choisie aux dernières touches.
        if ecran == VERDICT:
            self._regler_verdict()
            self._appliquer_theme(self._maison)
        elif ecran == DERNIERES:
            self._regler_dernieres()
            self._appliquer_theme(self.theme)
        else:
            self._appliquer_theme(self._theme_initial)
        if ecran == CHOIXPEAU_Q:
            self._regler_question()
        self._pile.setCurrentWidget(self._zones[ecran])
        self._rail.regler(self._rail_noms.index(_ETAPE_DU_RAIL[ecran]))
        self._regler_pied()

    def _regler_pied(self) -> None:
        ecran = self._ecran
        # Le rattrapage n'a rien avant sa première question : pas de retour.
        premier = bool(self._rattrapage) and ecran == self._ecrans[0] and self._question == 0
        self._btn_retour.setVisible(not premier)
        self._btn_retour.setText(tr("Refaire le test") if ecran == VERDICT else tr("Retour"))
        self._fin.setVisible(ecran == DERNIERES)
        lien_txt = ""
        suivant, actif = tr("Suivant"), True
        if ecran == JEUX:
            n = self._a_deplacer()
            if n:
                suivant = tr("Importer 1 jeu") if n == 1 else tr("Importer {} jeux").format(n)
                lien_txt = tr("Passer sans importer")
        elif ecran == CHOIXPEAU_Q:
            derniere = self._question == len(QUESTIONS) - 1
            suivant = tr("Voir le verdict") if derniere else tr("Question suivante")
            actif = self._reponses[self._question] >= 0
            lien_txt = tr("Garder le thème de Poudlard") if self._theme_initial == "poudlard" \
                else tr("Garder mes couleurs")
        elif ecran == DERNIERES:
            suivant = tr("Ouvrir la bibliothèque") if not self._rattrapage else tr("Terminer")
        self._lien.setText(lien_txt)
        self._lien.setVisible(bool(lien_txt))
        self._btn_suivant.setText(suivant)
        self._btn_suivant.setEnabled(actif)

    def _suivant(self) -> None:
        ecran = self._ecran
        if ecran == DOSSIER:
            if not is_writable_dir(self.install_path):
                avertir(self, tr("Dossier non inscriptible"),
                        tr("Impossible d'écrire dans :\n{}").format(self.install_path))
                return
            self._afficher(JEUX)
        elif ecran == JEUX:
            self._afficher(CHOIXPEAU_Q)
        elif ecran == CHOIXPEAU_Q:
            if self._reponses[self._question] < 0:
                return
            if self._question < len(QUESTIONS) - 1:
                self._question += 1
                self._regler_question()
                self._regler_pied()
                return
            self._repartir()
            self._afficher_ou_finir(VERDICT if self._maison else self._apres_choixpeau())
        elif ecran == VERDICT:
            self._afficher_ou_finir(self._apres_choixpeau())
        elif ecran == DERNIERES:
            self._terminer()

    def _apres_choixpeau(self) -> str:
        return DERNIERES if DERNIERES in self._ecrans else ""

    def _afficher_ou_finir(self, ecran: str) -> None:
        if ecran:
            self._afficher(ecran)
        else:
            self._terminer()

    def _retour(self) -> None:
        ecran = self._ecran
        if ecran == DOSSIER:
            self._racine.setCurrentIndex(0)
            self._appliquer_theme(self._theme_initial)
        elif ecran == JEUX:
            self._afficher(DOSSIER)
        elif ecran == CHOIXPEAU_Q:
            if self._question > 0:
                self._question -= 1
                self._regler_question()
                self._regler_pied()
            elif JEUX in self._ecrans:
                self._afficher(JEUX)
        elif ecran == VERDICT:
            self._oublier_le_choixpeau()
            self._afficher(CHOIXPEAU_Q)
        elif ecran == DERNIERES:
            if self._maison:
                self._afficher(VERDICT)
            elif CHOIXPEAU_Q in self._ecrans:
                self._afficher(CHOIXPEAU_Q)

    def _sur_lien(self) -> None:
        if self._ecran == JEUX:
            for ligne in self._lignes.values():
                ligne.setChecked(False)
            self._afficher(CHOIXPEAU_Q)
        elif self._ecran == CHOIXPEAU_Q:
            # Rien n'est obligatoire : sans maison, les couleurs d'avant restent.
            self._oublier_le_choixpeau()
            self._afficher_ou_finir(self._apres_choixpeau())

    def _terminer(self) -> None:
        if self._ecran == DERNIERES:
            self.autoplay = self._tgl_autoplay.isChecked()
            self.mute_videos = not self._tgl_son.isChecked()
            # Catalogue sans bandes-annonces : rien n'a été proposé, donc rien
            # n'a été accepté. Répondre « oui » à une question qu'on n'a pas
            # posée ferait télécharger sans mandat le jour où il en déclarera.
            self.trailers_optin = self._tgl_trailers.isChecked() if self._tgl_trailers else False
        self.accept()

    def perform_imports(self, config: Config) -> None:
        """Inscrit les jeux déjà en place et déplace les jeux cochés (config déjà créée)."""
        from src.ui.game_detail_handlers import find_import_error

        done: list[str] = []
        errors: list[str] = []
        for game, src in self.checked_imports():
            if src.parent.resolve() == config.install_path.resolve():
                done.append(game.name)  # déjà au bon endroit, rien à déplacer
                config.installed_versions[game.id] = game.recommended_version
                continue
            error = find_import_error(game, src, config.install_path)
            if error is not None:
                errors.append(f"{game.name} : {error.splitlines()[0]}")
                continue
            dest = config.install_path / Path(game.executable).parts[0]
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                src.rename(dest)  # même disque (validé) → instantané
            except OSError as exc:
                errors.append(f"{game.name} : {exc}")
                continue
            config.installed_versions[game.id] = game.recommended_version
            done.append(game.name)
            log.info("Onboarding : %s importé (%s → %s)", game.id, src, dest)
        if done or errors:
            config.save()
        if errors:
            avertir(
                self, tr("Import partiel"),
                tr("Certains jeux n'ont pas pu être importés :\n\n{}").format(
                    "\n".join(errors)))


def run_onboarding() -> Config:
    """Affiche l'assistant et retourne la Config créée.

    Lève `OnboardingAnnule` si l'assistant n'a pas abouti — la croix, Échap,
    ou un dossier devenu inaccessible entre-temps. **Aucune config n'est
    alors écrite** : c'est ce qui permet à l'assistant de revenir au
    lancement suivant. Il écrivait auparavant des défauts, ce qui démarrait
    le launcher ET sautait l'installation pour de bon.
    """
    dlg = OnboardingDialog()
    if dlg.exec() != QDialog.DialogCode.Accepted:
        log.info("Assistant de premier lancement fermé sans être terminé")
        raise OnboardingAnnule
    if not is_writable_dir(dlg.install_path):
        # L'étape du dossier le refuse déjà : on n'arrive ici que si le dossier
        # a disparu entre-temps. Abandonner vaut mieux qu'écrire une config
        # qui désigne un dossier où rien ne pourra jamais s'installer.
        log.warning("Dossier d'installation inaccessible : %s", dlg.install_path)
        raise OnboardingAnnule
    config = Config(
        install_path=dlg.install_path,
        cache_path=cache_pour(dlg.install_path),
        langue=dlg.langue,
        theme=dlg.theme,
        autoplay_videos=dlg.autoplay,
        mute_videos=dlg.mute_videos,
        trailers_optin=dlg.trailers_optin,
    )
    config.save()
    dlg.perform_imports(config)
    return config


def run_rattrapage(config: Config, etapes: tuple[str, ...]) -> None:
    """Les étapes jamais vues, une fois, puis la bibliothèque.

    Fermer la fenêtre ne repose pas la question au lancement suivant : un
    écran qui revient tant qu'on ne l'a pas rempli, c'est une relance, et le
    launcher s'interdit d'insister. Rien de ce qui n'a pas été répondu n'est
    changé ; les étapes sont seulement notées comme vues.
    """
    dlg = OnboardingDialog(config, etapes)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        config.theme = dlg.theme
        if TOUCHES in etapes:
            config.autoplay_videos = dlg.autoplay
            config.mute_videos = dlg.mute_videos
            config.trailers_optin = dlg.trailers_optin
        log.info("Rattrapage de l'assistant terminé (%s)", ", ".join(etapes))
    else:
        log.info("Rattrapage de l'assistant fermé (%s)", ", ".join(etapes))
    for etape in etapes:
        if etape not in config.etapes_assistant:
            config.etapes_assistant.append(etape)
    config.save()


def charger_ou_accueillir() -> Config:
    """La config du launcher, après l'assistant s'il y a lieu.

    Aucune config : l'assistant complet (`run_onboarding`). Une config d'avant
    le Choixpeau ou les bandes-annonces : ces étapes-là seulement, une fois.
    """
    if not Config.exists():
        return run_onboarding()
    config = Config.load()
    etapes = etapes_a_rattraper(config.etapes_assistant, config.theme, config.trailers_optin)
    if etapes:
        set_language(config.langue)
        run_rattrapage(config, etapes)
    return config
