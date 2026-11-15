"""Paramètres, « la salle commune » : un ciel en bandeau, les rubriques en pastilles dessous, des cartes.

Rubriques : Général (dossier et archives, langue, sauvegardes) · Son et image
(maison, Almanach, effets, son et vidéos) · Intégrations (Discord, manette) ·
À propos (numéros et « Vérifier les mises à jour »).

Maquette A « Voûte » pour la page, B « Almanach » pour Son et image (Ludo,
2026-11-15) : le même bandeau que les réglages d'un jeu (`bandeau_jeu`), sur la
Voie lactée de l'ESO au lieu du jeu ; les cartes vont par deux ; ce qui se
choisit se voit (`choix_visuels`) : la langue sur son drapeau, la maison sur son
blason, l'ambiance sur son dessin, les effets sur un aperçu. Chaque réglage reste
une ligne (titre, phrase d'aide, commande à droite) dans une carte.

Le thème et la langue demandent un redémarrage (bouton « Redémarrer
maintenant ») ; la saison des particules s'applique EN DIRECT (signal
`season_changed`).
"""

import logging
from pathlib import Path


from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.config import Config, cache_pour
from src.core.game_manager import GameManager, GameState
from src.core import effets, manette
from src.core import trailers as trailer_store
from src.core.formatting import format_bytes, format_size
from src.core.i18n import available_languages, get_language, tr, trn
from src.ui.bandeau_jeu import BLEU_NUIT, CIEL_PARAMETRES, Bandeau, pastille_rubrique
from src.ui.choix_visuels import (
    ChoixEnTuiles, pastille_langue, tuile_ambiance, tuile_effets, tuile_maison,
)
from src.ui.composants import (
    TAILLE_MINIMALE_PAGE,
    MARGES_PAGE,
    ENCRE_DOUCE, LISTE_HAUTE, Carte, Chemin, LigneReglage, Rangee, bouton, icone_de_bouton,
    espace_du_volume, feuille_de_style, police, surtitre, texte,
    lien,
    transparent,
)
from src.ui.fenetre_message import message
from src.ui import about_page, manette_nav
from src.ui.disk_scan_worker import DiskScanWorker, garer
from src.core.season import (
    SEASON_LABELS, SEASONS,
)
from src.ui.theme import THEMES, accent_qcolor, current as current_theme, themed
from src.ui.toggle_switch import ToggleSwitch
from src.ui.utils import avertir, is_writable_dir, open_local_path, zone_defilable

log = logging.getLogger(__name__)

# Dans l'ordre de `effets.MODES`.
_LIBELLES_EFFETS = {"auto": "Selon ce PC", "oui": "Oui", "non": "Non"}

# (libellé, pictogramme) de chaque rubrique, dans l'ordre des pages.
_RUBRIQUES = (("Général", "dossier"), ("Son et image", "ecran"),
              ("Intégrations", "integrations"), ("À propos", "infos"))
_RANG_A_PROPOS = len(_RUBRIQUES) - 1   # ses messages arrivent de la fenêtre, après un clic
# Le bandeau du ciel : les pastilles en bas, le ciel au-dessus (pas de grand titre : l'onglet PARAMÈTRES,
# souligné, le dit déjà ; audit UI f46).
_HAUTEUR_CIEL = 132
# Les pages de cartes par deux : au-delà, sur un grand écran, une ligne de réglage séparait son titre de
# son interrupteur par un désert. À propos, une colonne, garde sa largeur de lecture.
_LARGEUR_CARTES = 1120
_LARGEUR_LECTURE = 760
# Sous cette largeur, les cartes par deux s'empilent (`Rangee`).
_SEUIL_DEUX_COLONNES = 860

# La liste haute de `composants` (les copies de sauvegarde l'importent d'ici).
_COMBO_STYLE = LISTE_HAUTE


def _texte_disque(path: Path) -> str:
    libre, total = espace_du_volume(path)
    if not total:
        return tr("Espace libre inconnu")
    return tr("{libre} libres sur {total}").format(
        libre=format_bytes(libre), total=format_bytes(total))


class _AnneauDisque(QWidget):
    """Le volume en un anneau : vos jeux en or, le reste du disque en gris, le libre vide ; au centre, le
    poids de vos jeux."""

    _COTE = 84

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(self._COTE, self._COTE)
        self._jeux = 0.0
        self._reste = 0.0
        self._poids = ""

    def regler(self, jeux: int, libre: int, total: int) -> None:
        if total <= 0:
            self._jeux = self._reste = 0.0
        else:
            self._jeux = min(1.0, jeux / total)
            self._reste = max(0.0, min(1.0 - self._jeux, (total - libre - jeux) / total))
        self._poids = format_bytes(jeux) if jeux > 0 else ""
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        epaisseur = 9.0
        r = QRectF(self.rect()).adjusted(epaisseur / 2 + 1, epaisseur / 2 + 1, -epaisseur / 2 - 1, -epaisseur / 2 - 1)
        stylo = QPen(QColor(255, 255, 255, 18), epaisseur)
        stylo.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(stylo)
        p.drawArc(r, 0, 360 * 16)
        # De midi, dans le sens des aiguilles : vos jeux, puis le reste du disque. Un jeu installé reste
        # VISIBLE même s'il pèse 1 % du disque.
        jeux = max(4.0, 360 * self._jeux) if self._jeux > 0 else 0.0
        stylo.setColor(QColor(255, 255, 255, 56))
        p.setPen(stylo)
        p.drawArc(r, round(90 * 16 - jeux * 16), round(-360 * self._reste * 16))
        stylo.setColor(accent_qcolor(255))
        p.setPen(stylo)
        p.drawArc(r, 90 * 16, round(-jeux * 16))
        if self._poids:
            p.setPen(QColor("#f4f2f8"))
            p.setFont(police(13, gras=True))
            p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, self._poids.replace(" ", "\n", 1))
        p.end()


class _Pastilles(QWidget):
    """Les rubriques en pastilles, sous le ciel, comme celles des réglages d'un jeu (`pastille_rubrique`).

    ←/→ passent d'une pastille à l'autre, la manette aussi, puis descendent vers la page, et A choisit
    (`manette_nav`) ; même interface que la QListWidget d'avant."""

    currentRowChanged = pyqtSignal(int)

    def __init__(self, rubriques) -> None:
        super().__init__()
        transparent(self, "rubriques")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self._groupe = QButtonGroup(self)
        self._groupe.setExclusive(True)
        self.boutons: list[QPushButton] = []
        for rang, (libelle, icone) in enumerate(rubriques):
            btn = pastille_rubrique(tr(libelle), icone)
            btn.toggled.connect(lambda oui, r=rang: oui and self.currentRowChanged.emit(r))
            self._groupe.addButton(btn)
            self.boutons.append(btn)
            lay.addWidget(btn)
        lay.addStretch()

    def count(self) -> int:
        return len(self.boutons)

    def currentRow(self) -> int:  # noqa: N802 (même interface que QListWidget)
        return next((r for r, b in enumerate(self.boutons) if b.isChecked()), -1)

    def setCurrentRow(self, rang: int) -> None:  # noqa: N802
        self.boutons[rang].setChecked(True)


class SettingsDialog(QDialog):
    """Panneau de paramètres Accio Launcher."""

    config_changed = pyqtSignal()
    # « Vérifier les mises à jour » : launcher, catalogue et jeux en un geste.
    verification_demandee = pyqtSignal()
    season_changed = pyqtSignal(str)       # saison RÉSOLUE, appliquée en direct
    restart_requested = pyqtSignal()       # « Redémarrer maintenant » (thème/langue)
    # « Désinstaller et fermer » : (garder les jeux, garder les copies).
    desinstallation_demandee = pyqtSignal(bool, bool)
    nouveautes_demandees = pyqtSignal()   # le numéro de version d'À propos
    visite_demandee = pyqtSignal()        # « Revoir la visite » (`visite_guidee.py`)

    def __init__(self, config: Config, manager: GameManager, parent=None,
                 store=None, fond=None) -> None:
        super().__init__(parent)
        self.config = config
        self.manager = manager
        # Le son du launcher (src.ui.fond_sonore.FondSonore) : l'interrupteur
        # « Couper tout le son » est le haut-parleur de la barre du bas.
        self._fond = fond
        self._tgl_son = None
        # Magasin de bandes-annonces (src.ui.trailer_store.TrailerStore).
        # Optionnel : les tests ouvrent le dialogue sans, et la ligne se cache.
        self._store = store
        self._lbl_trailers = None
        self._btn_trailers = None
        # Bâtis avec leur rubrique, à sa première visite (`construire_rubrique`).
        self._theme_hint = None
        self._effets_hint: LigneReglage | None = None
        self._update_status = None
        self._versions_label = None
        self._btn_verifier = None
        self._scan_worker: DiskScanWorker | None = None
        # Une vérification à la fois : trois clics en lançaient trois, et un catalogue
        # neuf rebâtissait la bibliothèque trois fois (audit UI f19). Pas de bouton
        # grisé : il perdrait le focus du clavier au milieu du geste.
        self._verification_en_cours = False
        # (interrupteur, champ de Config) : l'enregistrement ne relit que ceux
        # des rubriques déjà construites.
        self._interrupteurs: list[tuple[ToggleSwitch, str]] = []
        self.setWindowTitle(tr("Paramètres"))
        self.setMinimumSize(*TAILLE_MINIMALE_PAGE)
        self.resize(1000, 680)
        self.setStyleSheet(themed(self._style()) + feuille_de_style())
        self._build_ui()

    def _style(self) -> str:
        return """
        QDialog { background-color: #060611; }
        """

    # ──────────────────── Construction ────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._ciel())

        # Chaque page DÉFILE au besoin (règle 52) : changer de thème ou de langue
        # fait apparaître « Redémarrer maintenant » et une ligne d'aide, et la page
        # Affichage ne tenait plus — Qt écrasait les lignes sous leur hauteur,
        # textes rognés par le bas (capture de Ludo, 2026-09-27).
        # Seule la rubrique Général se construit à l'ouverture ; les autres à
        # leur PREMIÈRE visite, une place vide gardant leur rang dans la pile.
        # Les poser toutes dans leur zone défilante coûtait 0,39 s à froid sur
        # les 0,82 de l'ouverture (mise en forme de quatre pages dont une seule
        # se voit), mesuré le 2026-10-14 sur Windows avec les vraies polices.
        # La rubrique visitée ensuite ne paie que sa propre mise en forme.
        self._pages = QStackedWidget()
        self._pages.addWidget(zone_defilable(self._marges(self._page_general(), _LARGEUR_CARTES)))
        for _ in _RUBRIQUES[1:]:
            self._pages.addWidget(QWidget())
        self._construites = {0}
        self._nav.currentRowChanged.connect(self.construire_rubrique)
        root.addWidget(self._pages, stretch=1)

        self._nav.currentRowChanged.connect(self._pages.setCurrentIndex)
        self._nav.setCurrentRow(0)
        # Rouverte après un changement pas encore appliqué : la ligne le redit.
        self._regler_redemarrage()

    def construire_rubrique(self, rang: int) -> None:
        """Bâtit la rubrique `rang` si ce n'est pas déjà fait (idempotent)."""
        if rang in self._construites or not 0 <= rang < len(_RUBRIQUES):
            return
        self._construites.add(rang)
        largeur = _LARGEUR_CARTES
        if rang == _RANG_A_PROPOS:
            contenu = about_page.construire(
                self.manager.catalog.contributors, manager=self.manager,
                ouvrir_nouveautes=self.nouveautes_demandees.emit,
                mises_a_jour=self._bloc_mises_a_jour())
            self._versions_label = contenu.findChild(QLabel, "versions")
            largeur = _LARGEUR_LECTURE
        else:
            contenu = (None, self._page_display, self._page_integrations)[rang]()
        courante = self._pages.currentIndex()
        vide = self._pages.widget(rang)
        self._pages.insertWidget(rang, zone_defilable(self._marges(contenu, largeur)))
        self._pages.removeWidget(vide)
        vide.deleteLater()
        self._pages.setCurrentIndex(courante)
        self._regler_redemarrage()

    def _ciel(self) -> Bandeau:
        """Le bandeau : la Voie lactée, et les rubriques en pastilles posées en bas.

        Ni « ← Bibliothèque » ni grand « PARAMÈTRES » : l'onglet souligné du haut dit déjà où l'on est,
        et Échap ferme la page (Ludo, 2026-10-27 ; audit UI f46, comme le Carnet et les Collections, col11).
        Pas de version non plus : À propos la porte, cliquable (une seule fois, Ludo, 2026-10-14)."""
        ciel = Bandeau(CIEL_PARAMETRES, hauteur=_HAUTEUR_CIEL, couvrir=True, bords=BLEU_NUIT)
        lay = QVBoxLayout(ciel)
        lay.setContentsMargins(MARGES_PAGE[0], 0, MARGES_PAGE[2], 18)
        lay.addStretch()
        self._nav = _Pastilles(_RUBRIQUES)
        lay.addWidget(self._nav)
        return ciel

    @staticmethod
    def _marges(page: QWidget, largeur: int) -> QWidget:
        """Les marges autour d'une page, alignée sur les pastilles du bandeau, et une largeur bornée."""
        cadre = QWidget()
        transparent(cadre, "margesPage")
        lay = QHBoxLayout(cadre)
        lay.setContentsMargins(MARGES_PAGE[0], 24, MARGES_PAGE[2], 24)
        page.setMaximumWidth(largeur)
        # Le reste de la largeur va au ressort, à DROITE : un alignement à gauche aurait réduit la page à sa
        # largeur conseillée, pas à sa largeur bornée.
        lay.addWidget(page, stretch=1)
        lay.addStretch(0)
        return cadre

    @staticmethod
    def _bloc(titre: str, *contenus: QWidget, etirer: bool = True) -> QWidget:
        """Un surtitre doré et ce qu'il annonce, qui prend la hauteur que la rangée lui donne."""
        bloc = QWidget()
        transparent(bloc)
        lay = QVBoxLayout(bloc)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        if titre:
            lay.addWidget(surtitre(titre))
        # Le dernier contenu (la carte) prend la hauteur de la rangée : deux cartes voisines finissent au
        # même pixel. Sans carte à étirer (`etirer=False`), le bloc reste en haut de la rangée.
        for rang, contenu in enumerate(contenus):
            etire = etirer and rang == len(contenus) - 1
            if etire and isinstance(contenu, Carte):
                contenu.etirable()
            lay.addWidget(contenu, stretch=1 if etire else 0)
        if not etirer:
            lay.addStretch()
        return bloc

    @staticmethod
    def _par_deux(gauche: QWidget, droite: QWidget) -> Rangee:
        """Deux blocs côte à côte, empilés quand la fenêtre est étroite."""
        return Rangee([gauche, droite], 2, _SEUIL_DEUX_COLONNES, ecart=18)

    @staticmethod
    def _page(*sections: QWidget) -> QWidget:
        """Une page de blocs, de haut en bas (une rangée de deux compte pour un)."""
        page = QWidget()
        transparent(page, "pageCartes")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(24)
        for section in sections:
            # Jamais plus haute que son contenu : une carte étirable (`Carte.etirable`) rend sa rangée
            # « extensible » aux yeux de la page, qui lui donnait alors le bas de la fenêtre.
            section.setSizePolicy(section.sizePolicy().horizontalPolicy(), QSizePolicy.Policy.Maximum)
            lay.addWidget(section)
        lay.addStretch()
        return page

    @staticmethod
    def _interrupteur(titre: str, coche: bool, description: str = "") -> tuple[LigneReglage, ToggleSwitch]:
        """Ligne de réglage dont la commande est un interrupteur."""
        bascule = ToggleSwitch(coche)
        # Le libellé est à CÔTÉ, pas dedans : sans nom accessible, une aide
        # technique n'annonce qu'« interrupteur », sans dire de quoi.
        bascule.setAccessibleName(titre)
        return LigneReglage(titre, description, bascule), bascule

    def _reglage(self, titre: str, champ: str,
                 description: str = "") -> tuple[LigneReglage, ToggleSwitch]:
        """Un interrupteur relié au champ `champ` de la config, enregistré au basculement."""
        ligne, bascule = self._interrupteur(titre, getattr(self.config, champ), description)
        self._interrupteurs.append((bascule, champ))
        bascule.toggled.connect(self._on_setting_changed)
        return ligne, bascule

    def _restart_button(self) -> QPushButton:
        btn = bouton(tr("Redémarrer maintenant"), principal=True)
        btn.clicked.connect(self.restart_requested)
        return btn

    def _ligne_redemarrage(self, phrase: str) -> tuple[LigneReglage, QPushButton]:
        """« Redémarrez le launcher pour appliquer… » + le bouton, cachée tant
        que rien n'a changé (montrée au premier changement de langue ou de thème)."""
        btn = self._restart_button()
        ligne = LigneReglage(phrase, "", btn)
        ligne.titre.setStyleSheet(themed("color: #e8c547; background: transparent;"))
        ligne.titre.setWordWrap(True)
        ligne.hide()
        return ligne, btn

    # ── Page Général ──

    def _page_general(self) -> QWidget:
        # Vos jeux : l'anneau du disque, puis ce qu'il contient, où, et ce qui reste libre.
        dossier = Carte()
        haut = QWidget()
        transparent(haut)
        lay_haut = QHBoxLayout(haut)
        lay_haut.setContentsMargins(20, 18, 20, 18)
        lay_haut.setSpacing(18)
        self._disque = _AnneauDisque()
        lay_haut.addWidget(self._disque, alignment=Qt.AlignmentFlag.AlignTop)
        colonne = QVBoxLayout()
        colonne.setSpacing(4)
        self._installed_label = texte(tr("Calcul de l'espace utilisé…"), 17, "#ffffff")
        self._installed_label.setFont(police(17, gras=True))
        self._installed_label.setWordWrap(True)
        colonne.addWidget(self._installed_label)
        # Le chemin, coupé au milieu, entier en infobulle.
        self._path_label = Chemin(str(self.config.install_path), 13, ENCRE_DOUCE)
        colonne.addWidget(self._path_label)
        self._free_label = texte(_texte_disque(self.config.install_path), 13, ENCRE_DOUCE)
        colonne.addWidget(self._free_label)
        colonne.addSpacing(10)
        boutons = QHBoxLayout()
        boutons.setSpacing(10)
        btn_open = bouton(tr("Ouvrir"))
        btn_open.setIcon(icone_de_bouton("dossier", 16, accent_qcolor(255)))
        btn_open.clicked.connect(self._on_open_install_folder)
        boutons.addWidget(btn_open)
        # Pas l'action mise en avant : le dossier ne se change pas à la légère.
        btn_change = bouton(tr("Changer…"))
        btn_change.clicked.connect(self._on_change_path)
        boutons.addWidget(btn_change)
        boutons.addStretch()
        colonne.addLayout(boutons)
        lay_haut.addLayout(colonne, stretch=1)
        dossier.ajouter(haut)
        self._octets_jeux = 0
        self._regler_disque()

        self._lancer_scan()

        # La langue sur son drapeau : déposer un src/data/i18n/<code>.json suffit à en ajouter une, sans
        # toucher à ce fichier (src/core/i18n.available_languages) ; sans drapeau connu, la pastille reste nue.
        langue = Carte()
        interieur = QWidget()
        transparent(interieur)
        lay_langue = QVBoxLayout(interieur)
        lay_langue.setContentsMargins(20, 18, 20, 18)
        lay_langue.setSpacing(12)
        langues = available_languages()
        self._choix_langue = ChoixEnTuiles(pastille_langue, colonnes=max(1, len(langues)), largeur_min=110)
        for info in langues:
            self._choix_langue.addItem(info.name, info.code)
        self._choix_langue.setCurrentIndex(max(0, self._choix_langue.findData(self.config.langue)))
        self._choix_langue.currentIndexChanged.connect(self._on_language_changed)
        lay_langue.addWidget(self._choix_langue)
        lay_langue.addWidget(texte(
            tr("Les jeux ont leurs propres langues, parfois plus nombreuses que celles du launcher : "
               "chacun a la sienne dans ses réglages, rubrique Langue."), 13, ENCRE_DOUCE, retour=True))
        # Dans la même case que les drapeaux : en ligne à part, son filet restait visible, ligne cachée.
        self._lang_hint, self._lang_restart = self._ligne_redemarrage(
            tr("Redémarrez le launcher pour appliquer la langue."))
        self._lang_hint.layout().setContentsMargins(0, 0, 0, 0)
        lay_langue.addWidget(self._lang_hint)
        langue.ajouter(interieur)

        sauvegardes = Carte()
        ligne, self._tgl_copies = self._reglage(
            tr("Copier les sauvegardes avant chaque partie"), "copies_sauvegardes",
            tr("Une copie de chaque sauvegarde qui a changé, à restaurer depuis les réglages du jeu."))
        sauvegardes.ajouter(ligne)

        # Les archives vivent à côté des jeux : c'est la place du disque qu'il règle.
        archives = Carte()
        ligne, self._tgl_archives = self._reglage(
            tr("Supprimer les archives après installation"), "delete_archives")
        archives.ajouter(ligne)

        fin = Carte()
        revoir = bouton(tr("Revoir la visite"))
        revoir.clicked.connect(self.visite_demandee.emit)
        fin.ajouter(LigneReglage(
            tr("Visite guidée"),
            tr("Où trouver le Carnet, les Collections et les réglages de chaque jeu."),
            revoir))
        # Un lien discret : ce geste n'a pas à peser autant que « Revoir la visite ».
        desinstaller = lien(tr("Désinstaller…"), discret=True)
        desinstaller.clicked.connect(self._on_desinstaller)
        fin.ajouter(LigneReglage(
            "Accio Launcher",
            tr("Vos jeux peuvent rester : un launcher réinstallé les retrouve tout seul."),
            desinstaller))

        return self._page(
            self._par_deux(self._bloc(tr("Dossier des jeux"), dossier),
                           self._bloc(tr("Langue du launcher"), langue)),
            self._par_deux(self._bloc("", sauvegardes), self._bloc("", archives)),
            fin)

    def _on_desinstaller(self) -> None:
        from src.ui.desinstallation_dialog import DesinstallationDialog
        a_des_jeux = any(e.state == GameState.INSTALLED for e in self.manager.get_games())
        dlg = DesinstallationDialog(self.config.install_path, self._octets_jeux, a_des_jeux, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.desinstallation_demandee.emit(dlg.garder_jeux, dlg.garder_copies)

    def _regler_disque(self) -> None:
        libre, total = espace_du_volume(self.config.install_path)
        self._disque.regler(self._octets_jeux, libre, total)
        self._free_label.setText(_texte_disque(self.config.install_path))

    def _lancer_scan(self) -> None:
        """Mesure les jeux installés, en arrière-plan."""
        # Snapshot des chemins sur le thread principal (thread-safe)
        game_paths = [
            self.manager.get_game_path(entry.game.id)
            for entry in self.manager.get_games()
            if entry.state == GameState.INSTALLED
        ]
        game_paths = [p for p in game_paths if p is not None]
        self._scan_worker = DiskScanWorker(game_paths, parent=self)
        self._scan_worker.result.connect(self._on_scan_done)
        self._scan_worker.start()

    # ── Page Son et image ──

    def _page_display(self) -> QWidget:
        videos = Carte()
        if self._fond is not None:
            ligne, self._tgl_son = self._interrupteur(
                tr("Couper tout le son"), self._fond.son_coupe,
                tr("Musique, bandes-annonces et cinématiques."))
            self._tgl_son.toggled.connect(self._sur_interrupteur_son)
            self._fond.son_coupe_change.connect(self._sur_son_coupe)
            videos.ajouter(ligne)
        ligne, self._tgl_autoplay = self._reglage(
            tr("Lecture automatique des vidéos"), "autoplay_videos")
        videos.ajouter(ligne)
        self._ligne_mute, self._tgl_mute = self._reglage(
            tr("Couper le son des vidéos"), "mute_videos")
        videos.ajouter(self._ligne_mute)
        if self._tgl_son is not None:
            self._griser(self._ligne_mute, not self._tgl_son.isChecked())

        self._btn_trailers = bouton("", principal=True)
        self._btn_trailers.clicked.connect(self._on_trailers_clicked)
        self._ligne_trailers = LigneReglage(tr("Bandes-annonces"), " ", self._btn_trailers)
        self._lbl_trailers = self._ligne_trailers.description
        videos.ajouter(self._ligne_trailers)
        if self._store is not None:
            self._store.state_changed.connect(self._refresh_trailers)
            self._store.progress.connect(self._on_trailer_progress)
            self._store.job_finished.connect(self._on_trailer_job_finished)
        self._refresh_trailers()

        # La maison sur son blason (les couleurs de chaque thème, l'initiale de son nom).
        self._choix_maison = ChoixEnTuiles(
            lambda nom, ident: tuile_maison(nom, THEMES[ident].accent_light, THEMES[ident].accent_dark),
            colonnes=len(THEMES), largeur_min=150)
        for palette in THEMES.values():
            self._choix_maison.addItem(tr(palette.nom), palette.id)
        self._choix_maison.setCurrentIndex(max(0, self._choix_maison.findData(self.config.theme)))
        self._choix_maison.currentIndexChanged.connect(self._on_theme_changed)
        self._theme_hint, self._theme_restart = self._ligne_redemarrage(
            tr("Redémarrez le launcher pour changer ses couleurs."))

        # L'ambiance du mois sur son dessin. La LISTE vient de `season.SEASONS`, jamais d'une copie locale :
        # deux listes qu'aucun calcul ne relie finissent par diverger — ajouter une ambiance l'aurait laissée
        # invisible dans les Paramètres, sans que rien ne le signale.
        self._choix_ambiance = ChoixEnTuiles(tuile_ambiance, colonnes=len(SEASONS), largeur_min=118)
        for value in SEASONS:
            self._choix_ambiance.addItem(tr(SEASON_LABELS[value]), value)
        self._choix_ambiance.setCurrentIndex(max(0, self._choix_ambiance.findData(self.config.season)))
        self._choix_ambiance.currentIndexChanged.connect(self._on_season_changed)
        self._griser(self._choix_ambiance, effets.animes())   # effets coupés : la saison attend, intacte
        almanach = Carte()
        ligne, _ = self._reglage(tr("Fait du jour dans la barre de statut"), "faits_du_jour")
        almanach.ajouter(ligne)

        # Les effets animés sur un aperçu ; « Selon ce PC » dit ce que ce PC a choisi.
        sous = {"auto": tr("Ici : animés") if effets.selon("auto") else tr("Ici : coupés")}
        self._choix_effets = ChoixEnTuiles(
            lambda nom, mode: tuile_effets(str(mode), nom, sous.get(str(mode), "")), colonnes=len(effets.MODES),
            largeur_min=110)
        for mode in effets.MODES:
            self._choix_effets.addItem(tr(_LIBELLES_EFFETS[mode]), mode)
        self._choix_effets.setCurrentIndex(max(0, self._choix_effets.findData(self.config.effets_animes)))
        self._choix_effets.currentIndexChanged.connect(self._on_effets_changed)
        self._effets_hint, _ = self._ligne_redemarrage(tr("Redémarrez le launcher pour appliquer ce choix."))

        return self._page(
            self._bloc(tr("Couleurs du launcher"), self._choix_maison, self._theme_hint),
            self._bloc(tr("Almanach"), self._choix_ambiance, almanach),
            self._par_deux(
                self._bloc(tr("Effets animés"), self._choix_effets, texte(
                    tr("Particules, zoom du fond, étoiles et personnages qui tournent seuls."),
                    13, ENCRE_DOUCE, retour=True), self._effets_hint, etirer=False),
                self._bloc(tr("Son et vidéos"), videos)))

    # ── Bandes-annonces ──

    def _trailers(self) -> tuple:
        """Bandes-annonces déclarées par le catalogue."""
        return self.manager.trailers()

    def _refresh_trailers(self) -> None:
        """Met la ligne à jour : ce qu'on a, ce qu'il manque, et quoi faire.

        Cachée quand le catalogue n'en déclare aucune : proposer de télécharger
        ce qui n'existe pas serait une promesse en l'air, et un launcher plus
        ancien que son catalogue doit rester silencieux, pas cassé.
        """
        if self._lbl_trailers is None or self._btn_trailers is None:
            return
        liste = self._trailers()
        self._ligne_trailers.setVisible(bool(liste))
        if not liste:
            return

        if self._store is not None and self._store.is_busy:
            self._btn_trailers.setText(tr("Annuler"))
            return

        presentes = trailer_store.nombre_present(liste)
        octets = trailer_store.poids_disque()
        if presentes == len(liste):
            self._lbl_trailers.setText(
                tr("{n} sur le disque ({taille})").format(
                    n=presentes, taille=format_bytes(octets)))
            self._btn_trailers.setText(tr("Supprimer"))
            self._nature_bouton_trailers("secondaire")
        else:
            manque = trailer_store.poids_a_telecharger(liste)
            self._lbl_trailers.setText(
                tr("{faites} sur {total}").format(faites=presentes, total=len(liste)))
            self._btn_trailers.setText(
                tr("Télécharger ({taille})").format(taille=format_size(manque)))
            self._nature_bouton_trailers("principal")

    def _nature_bouton_trailers(self, nature: str) -> None:
        """L'or désigne l'action de la ligne : pas un geste qui efface."""
        bouton_ = self._btn_trailers
        if bouton_.objectName() != nature:
            bouton_.setObjectName(nature)
            bouton_.style().unpolish(bouton_)
            bouton_.style().polish(bouton_)

    def _on_trailer_progress(self, faites: int, total: int, octets: int, sur: int) -> None:
        if self._lbl_trailers is None:
            return
        pct = round(octets * 100 / sur) if sur else 0
        self._lbl_trailers.setText(
            tr("Téléchargement des bandes-annonces… {faites}/{total} · {pct} %").format(
                faites=faites + 1, total=total, pct=pct))

    def _on_trailer_job_finished(self, _ok: int, _echecs: int) -> None:
        self._refresh_trailers()

    def _on_trailers_clicked(self) -> None:
        """Télécharger, annuler ou supprimer — selon ce que dit le bouton."""
        if self._store is None:
            return
        if self._store.is_busy:
            self._store.cancel()
            self._refresh_trailers()
            return
        liste = self._trailers()
        if trailer_store.nombre_present(liste) == len(liste):
            choix = message(
                self, QMessageBox.Icon.Question, tr("Supprimer les bandes-annonces"),
                tr("Les bandes-annonces ({taille}) quittent le disque.").format(
                    taille=format_bytes(trailer_store.poids_disque())),
                choix=(tr("Supprimer"), tr("Annuler")), defaut=1, danger=True)
            if choix != 0:
                return
            # Supprimer, c'est aussi dire non : sans ça le rattrapage du
            # prochain démarrage les re-téléchargerait aussitôt.
            self.config.trailers_optin = False
            self.config.save()
            self._store.supprimer_tout()
            self._refresh_trailers()
            return
        self.config.trailers_optin = True
        self.config.save()
        self._store.start(liste)
        self._refresh_trailers()

    # ── Mises à jour (rubrique À propos) ──

    def _bloc_mises_a_jour(self) -> QWidget:
        """Le bouton sous les numéros d'À propos, et son résultat dessous.

        UN bouton : « Actualiser le catalogue » lançait le même vérificateur
        que lui, le launcher en moins (`verification_forcee`)."""
        bloc = QWidget()
        transparent(bloc)
        lay = QVBoxLayout(bloc)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self._btn_verifier = bouton(tr("Vérifier les mises à jour"))
        self._btn_verifier.clicked.connect(self._on_verifier)
        lay.addWidget(self._btn_verifier, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._update_status = texte("", 13, ENCRE_DOUCE, retour=True)
        self._update_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_status.hide()
        lay.addWidget(self._update_status)
        return bloc

    # ── Page Intégrations ──

    def _page_integrations(self) -> QWidget:
        discord = Carte()
        ligne, self._tgl_discord = self._reglage(
            tr("Afficher le jeu en cours sur Discord"), "discord_presence")
        discord.ajouter(ligne)
        self._ligne_discord_partie, self._tgl_discord_partie = self._reglage(
            tr("Montrer où en est votre partie"), "discord_partie",
            tr("Lieu et avancement s'affichent sur votre carte Discord. "
               "Éteint : seuls le jeu, votre maison et votre année."))
        discord.ajouter(self._ligne_discord_partie)
        self._tgl_discord.toggled.connect(self._griser_discord_partie)
        self._griser_discord_partie(self._tgl_discord.isChecked())

        manette_carte = Carte()
        ligne, self._tgl_nav_manette = self._reglage(
            tr("Naviguer dans le launcher à la manette"), "navigation_manette",
            tr("Flèches de la manette : changer de jeu et de bouton. ✕ ou A : valider. "
               "Rond ou B : retour. Stick droit : faire défiler."))
        self._tgl_nav_manette.toggled.connect(self._on_navigation_manette)
        manette_carte.ajouter(ligne)
        ligne, self._tgl_manette = self._reglage(
            tr("Barre lumineuse de la manette aux couleurs de votre maison"), "couleur_manette")
        self._tgl_manette.toggled.connect(self._on_couleur_manette)
        manette_carte.ajouter(ligne)
        return self._page(self._par_deux(self._bloc(tr("Discord"), discord),
                                         self._bloc(tr("Manette"), manette_carte)))

    # ── Page À propos ──

    # ──────────────────── Slots ────────────────────

    def _on_scan_done(self, count: int, total_bytes: int) -> None:
        """Callback quand le scan disque en arrière-plan est terminé."""
        # Une clé par nombre : « (x) » ne se traduit pas, et l'anglais met
        # 0 au pluriel quand le français le met au singulier.
        if count == 0:
            phrase = tr("Aucun jeu installé")
        elif count == 1:
            phrase = tr("1 jeu installé, {}").format(format_bytes(total_bytes))
        else:
            phrase = tr("{} jeux installés, {}").format(count, format_bytes(total_bytes))
        self._installed_label.setText(phrase)
        self._octets_jeux = total_bytes
        self._regler_disque()
        log.info("Total installé : %d jeu(x), %s", count, format_bytes(total_bytes))

    def _on_change_path(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, tr("Changer le dossier d'installation"), str(self.config.install_path)
        )
        if chosen:
            # MÊME garde que l'assistant de premier lancement, qui la posait
            # depuis toujours — pas ici. Or c'est par ce chemin qu'on choisit un
            # dossier APRÈS coup, donc celui par lequel arrivent « Program
            # Files », la racine d'un disque et les lecteurs réseau montés en
            # lecture seule. Sans elle, le réglage était accepté, sauvegardé, et
            # l'échec ne se manifestait qu'au téléchargement suivant, sous la
            # forme d'une erreur qui n'accusait pas le dossier.
            if not is_writable_dir(Path(chosen)):
                avertir(
                    self, tr("Dossier non inscriptible"),
                    tr("Ce dossier refuse l'écriture. Choisissez-en un autre :\n{}").format(chosen))
                return
            self.changer_dossier(Path(chosen))

    def changer_dossier(self, nouveau: Path) -> None:
        """Pose le nouveau dossier, après avoir dit ce que deviennent les jeux.

        Rien n'est déplacé : ceux qui sont installés restent dans l'ancien
        dossier, et sans prévenir la bibliothèque se vidait d'un coup."""
        if nouveau == self.config.install_path:
            return
        installes = sum(1 for e in self.manager.get_games() if e.state == GameState.INSTALLED)
        if installes:
            choix = message(
                self, QMessageBox.Icon.Warning, tr("Changer le dossier d'installation"),
                trn(installes, "Votre jeu ({taille}) reste dans :\n{dossier}\n\nLe launcher ne le verra plus.",
                    "Vos {n} jeux ({taille}) restent dans :\n{dossier}\n\nLe launcher ne les verra plus.").format(
                        n=installes, taille=format_bytes(self._octets_jeux),
                        dossier=self.config.install_path),
                choix=(tr("Changer"), tr("Annuler")), defaut=1)
            if choix != 0:
                return
        self.config.install_path = nouveau
        self.config.cache_path = cache_pour(nouveau)
        self._path_label.definir(str(nouveau))
        # La carte redit ce que contient le NOUVEAU dossier : l'enregistrement
        # re-détecte les jeux d'abord, le scan lit donc les bons.
        self._installed_label.setText(tr("Calcul de l'espace utilisé…"))
        self._octets_jeux = 0
        self._regler_disque()
        self._save()
        self._shutdown_scan()
        self._lancer_scan()

    def _on_setting_changed(self) -> None:
        for bascule, champ in self._interrupteurs:
            setattr(self.config, champ, bascule.isChecked())
        self._save()

    def _griser_discord_partie(self, presence: bool) -> None:
        """Sans présence Discord, la carte n'existe pas."""
        self._griser(self._ligne_discord_partie, presence)

    @staticmethod
    def _griser(ligne: QWidget, actif: bool) -> None:
        """Un réglage qu'un autre éteint reste visible, grisé, sa valeur intacte."""
        ligne.setEnabled(actif)
        if actif:
            ligne.setGraphicsEffect(None)
        elif ligne.graphicsEffect() is None:
            effet = QGraphicsOpacityEffect(ligne)
            effet.setOpacity(0.42)
            ligne.setGraphicsEffect(effet)

    @staticmethod
    def _on_navigation_manette(coche: bool) -> None:
        # Tout de suite : c'est en essayant qu'on voit si ça marche.
        navigation = manette_nav.navigation()
        if navigation is not None:
            navigation.set_actif(coche)

    def _on_couleur_manette(self, coche: bool) -> None:
        # Allumé : la manette prend la couleur tout de suite, c'est ce qui dit que ça marche.
        if coche:
            manette.colorer_en_fond(self.config.theme)
        else:
            # Décochée, elle restait allumée, même launcher fermé (grand audit du 2026-11-02).
            manette.eteindre_en_fond()

    def _on_language_changed(self) -> None:
        """Change la langue (effective au prochain démarrage — chaînes posées à la construction)."""
        self.config.langue = self._choix_langue.currentData()
        self._regler_redemarrage()
        self._save()

    def _regler_redemarrage(self) -> None:
        """« Redémarrer » seulement si la config diffère de ce qui TOURNE : revenir
        à la langue (ou au thème) de départ n'a rien à appliquer."""
        self._lang_hint.setVisible(self.config.langue != get_language())
        if self._theme_hint is not None:
            self._theme_hint.setVisible(self.config.theme != current_theme().id)
        if self._effets_hint is not None:
            self._effets_hint.setVisible(effets.selon(self.config.effets_animes) != effets.animes())

    def _on_theme_changed(self) -> None:
        """Change le thème (effectif au prochain démarrage — couleurs posées à la construction)."""
        self.config.theme = self._choix_maison.currentData()
        # La fenêtre attend un redémarrage ; la manette, elle, change tout de suite.
        if self.config.couleur_manette:
            manette.colorer_en_fond(self.config.theme)
        self._regler_redemarrage()
        self._save()

    def _on_effets_changed(self) -> None:
        """Effets animés : effectif au prochain démarrage, comme le thème (`src/core/effets.py`)."""
        self.config.effets_animes = self._choix_effets.currentData()
        self._regler_redemarrage()
        self._save()

    def _on_season_changed(self) -> None:
        """Change la saison des particules — appliqué EN DIRECT (pas de redémarrage)."""
        self.config.season = self._choix_ambiance.currentData()
        self._save()
        self.season_changed.emit(effets.saison_des_particules(self.config.season))

    def _sur_interrupteur_son(self, coupe: bool) -> None:
        if coupe != self._fond.son_coupe:
            self._fond.basculer_son()
        self._griser(self._ligne_mute, not coupe)   # tout coupé : il ne changerait rien

    def _sur_son_coupe(self, coupe: bool) -> None:
        """Le haut-parleur de la barre du bas, ou une écoute qui rend le son."""
        if self._tgl_son is not None:
            self._tgl_son.setChecked(coupe)   # n'émet pas `toggled`
            self._griser(self._ligne_mute, not coupe)

    def done(self, result: int) -> None:
        """Arrête le scan disque sur TOUS les chemins de fermeture.

        reject() (Échap) et la fermeture par les onglets (`Pages`) ne passent
        PAS par closeEvent : seul done() est commun aux sorties (vérifié). Sans ça, le QThread de scan serait détruit avec le
        dialog alors qu'il tourne encore → crash.
        """
        self._shutdown_scan()
        if self._fond is not None:
            try:
                self._fond.son_coupe_change.disconnect(self._sur_son_coupe)
            except TypeError:
                pass
        super().done(result)

    def _shutdown_scan(self) -> None:
        """Interrompt et attend le DiskScanWorker (idempotent : la référence est
        lâchée, un fil garé puis libéré n'est plus jamais touché)."""
        fil, self._scan_worker = self._scan_worker, None
        if fil is None:
            return
        fil.blockSignals(True)
        try:
            fil.result.disconnect(self._on_scan_done)
        except TypeError:
            pass
        if fil.isRunning():
            # L'interruption est lue à chaque entrée de dossier ; un disque qui ne
            # répond plus (partage réseau en veille) bloque pourtant DANS l'appel
            # système : 5,7 s de fenêtre figée avec un disque simulé à 6 s (audit UI
            # f18). Au-delà de 3 s, le fil est garé jusqu'à sa vraie fin.
            fil.requestInterruption()
            if not fil.wait(3000):
                garer(fil)

    def _on_open_install_folder(self) -> None:
        open_local_path(str(self.config.install_path))

    def _on_verifier(self) -> None:
        if self._verification_en_cours:
            return
        self._verification_en_cours = True
        self._update_status.setText(tr("Vérification des mises à jour…"))
        self._update_status.setStyleSheet(themed("color: #d6a72c;"))
        self._update_status.show()
        self.verification_demandee.emit()

    def update_catalog_version(self, version: str) -> None:
        """Redit le numéro du catalogue d'À propos après une vérification ; le
        résultat, lui, arrive en une fois à la fin (`show_update_status`)."""
        self.construire_rubrique(_RANG_A_PROPOS)
        about_page.regler_catalogue(self._versions_label, version)

    def show_update_status(self, message: str, success: bool = True) -> None:
        """Affiche le résultat sous « Vérifier les mises à jour »."""
        self._verification_en_cours = False
        self.construire_rubrique(_RANG_A_PROPOS)
        color = "#2ecc71" if success else "#8a8aaa"
        self._update_status.setText(message)
        self._update_status.setStyleSheet(f"color: {color};")
        self._update_status.show()

    def jeux_a_mettre_a_jour(self) -> int:
        """Les jeux installés dont une mise à jour attend déjà : sans eux, une
        vérification qui n'apporte rien dirait « Tout est à jour » (règle 108)."""
        return sum(self.manager.has_update(e.game.id) for e in self.manager.get_games())

    def _save(self) -> None:
        self.config.save()
        self.config_changed.emit()
