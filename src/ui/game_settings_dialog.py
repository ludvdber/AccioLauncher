"""Réglages d'UN jeu : image, commandes, langue, performances, et ses fichiers.

Pourquoi une FENÊTRE et pas le menu qu'il y avait ici d'abord : un menu est un
choix qu'on prend et qui se referme, alors que les réglages d'un jeu
s'étoffent. Une fenêtre a des rubriques, de la place pour expliquer, et sait
montrer ce qui n'est pas encore là (une rubrique verrouillée et nommée pour un
jeu qui n'aurait encore aucun réglage).

Refaite le 2026-10-09 d'après la maquette « Réglages du jeu » validée par
Ludo, puis mise en disposition B le 2026-11-15 : en haut le bandeau du jeu,
dessous les rubriques en pastilles (Langue, Image, Jeu, Difficulté, Fichiers),
une page en cartes pour chacune ; plus de rail à gauche. Ce qu'elle corrige de
l'ancienne boîte à onglets :

- une boîte trop haute pour ce qu'elle portait, et un onglet entier pour
  quelques liens : les actions sur les fichiers ont leur page, en cartes
  expliquées ;
- les effets d'image repliés par familles : il fallait déplier pour voir ce
  que fait un préréglage. Tous sont visibles, préréglages à côté ;
- le coût lu comme du texte (« GPU +++ » sur chaque ligne) : trois points de
  couleur se comparent d'un coup d'œil, le détail reste dans le « ? » ;
- les liens entre réglages découverts en voyant des lignes grisées : la
  ligne grisée DIT ce qui l'éteint, et un effet qui dépend d'un autre est
  rangé en retrait sous lui ;
- « Revenir à l'installation » en lien gris, qu'on croyait
  désactivé, et un bouton Fermer alors que tout s'enregistre au fil des
  clics : un vrai bouton, « Bibliothèque » dans le bandeau.
"""

import html
from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QGraphicsOpacityEffect,
    QLabel,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.core import (preference_gpu, qualite_rendu, reglages_correctif, reglages_graphiques, resolution_jeu,
                      texte_ue1)
from src.core.game_data import GameData
from src.core.game_manager import GameManager
from src.core.i18n import tr
from src.ui.composants import (
    TAILLE_MINIMALE_PAGE,
    transparent,
    colonne_centree,
    MARGES_PAGE,
    Carte,
    bouton_retour,
    feuille_de_style,
    police,
    surtitre,
)
from src.ui.bandeau_jeu import badge_dans_la_pastille, bandeau_du_jeu, pastille_rubrique
from src.ui.editeur_touches import EditeurTouches
from src.ui.entree_focus import entree_suit_le_focus
from src.core.reglages_image import Magasin, MagasinCorrectif
from src.core.reglages_table import Reglage
from src.ui.page_image import LARGEUR_LISTE, LigneLibre, PageAvecFiche, PageImage, _LigneImage
from src.ui.theme import themed
from src.ui.theme import current as theme_courant
from src.ui.toggle_switch import ToggleSwitch
from src.ui.utils import zone_defilable
from src.ui.reglages_widgets import (  # réexportés
    _STYLE,
    _Disposition,
    _texte_beta,
)
from src.ui.reglages_rubriques import (  # noqa: F401  (réexportés)
    log,
    _ONGLETS,
    _COULEURS_COUT,
    _COULEUR_NOTE,
    _RESSOURCES,
    _NIVEAUX,
    _A_VENIR,
    RubriquesDuJeu,
)

# Le rail : le jeu, ses rubriques, ses fichiers. 270 : à 260, quand le rail défile (fenêtre de
# 660 à 700 px de haut), sa barre de 10 px coupait « RÉGLAGES DU / JEU » (audit UI f65).
# Taille d'ouverture, celle de la maquette, quand la page s'ouvre seule (sans fenêtre pour
# l'accueillir) ; le plancher est celui de toutes les pages (`TAILLE_MINIMALE_PAGE`).
_TAILLE_VOULUE = QSize(1320, 860)
# Une hauteur commune aux en-têtes de cartes voisines : la légende de « Chaque
# effet » (œil et points de 18 px) décalait sa carte de 3 px par rapport à la
# colonne de gauche.
_HAUTEUR_ENTETE = 18

class GameSettingsDialog(RubriquesDuJeu, QDialog):
    """Fenêtre de réglages d'un jeu. Tout choix s'écrit AUSSITÔT.

    Pas de bouton « Appliquer » : l'écriture registre peut demander une
    élévation, et une invite UAC se comprend juste après un clic délibéré sur
    une langue, beaucoup moins après un « Appliquer » qui regrouperait trois
    réglages sans dire lequel la déclenche.
    """

    def __init__(self, game: GameData, manager: GameManager,
                 appliquer_langue, actions=(),
                 parent: QWidget | None = None, appliquer_manette=None, onglet: str = "") -> None:
        super().__init__(parent)
        # Entrée choisit la carte, le segment ou l'onglet au focus, comme Espace et
        # comme les cartes de Difficulté (audit UI f56).
        entree_suit_le_focus(self)
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
        self._groupe = QButtonGroup(self)
        self._boutons: dict[str, QRadioButton] = {}
        # Réglages du correctif que le catalogue déclare confirmés pour ce jeu,
        # et son ini (à côté de l'exécutable, là où le correctif le lit).
        declares = reglages_correctif.reglages_du_jeu(game.fix_settings)
        self._ini: Path | None = (reglages_correctif.ini_du_correctif(
            manager.config.install_path / Path(game.executable).parent) if declares else None)
        self._reglages = reglages_correctif.portes_par(self._ini, declares)
        # HP3 : l'image passe par son traducteur D3D8 (`reglages_graphiques`), le
        # reste par son correctif (dinput8.ini) ; les deux cohabitent depuis le
        # 2026-10-28 (déclarer `son_arriere_plan` masquait toute la page Image).
        conf = reglages_graphiques.chemin(manager.config.install_path / Path(game.executable).parent)
        self._conf_graph: Path | None = conf if reglages_graphiques.disponible(conf) else None
        # Les réglages d'image qui ne vivent pas dans l'ini du correctif (rendu D3D11 de HP1/HP2,
        # réglages graphiques de HP3), avec leur magasin : « Revenir à l'installation » les remet aussi.
        self._magasins_image: list[tuple[qualite_rendu.MagasinRendu | reglages_graphiques.MagasinGraphique,
                                         tuple[Reglage, ...]]] = []
        self._erreur: QLabel | None = None
        self._compte_captures: QLabel | None = None
        # Le contrôle de chaque réglage du correctif, par identifiant : la remise
        # à l'origine les remet sur ce que porte le fichier, sans rebâtir la page.
        self._controles: dict[str, QWidget] = {}
        self._panneau = None   # le haut de l'onglet Difficulté
        # La fiche de chaque ligne (son texte riche), par identifiant (par libellé hors correctif).
        self._aides: dict[str, str] = {}
        # Les lignes de la page en construction, que sa fiche suivra : (ligne, titre, fiche).
        self._lignes_de_page: list[tuple[_LigneImage, str, str]] = []
        # La ligne entière de chaque réglage : grisée quand un autre réglage,
        # éteint, lui retire tout effet, et elle dit lequel.
        self._blocs: dict[str, _LigneImage] = {}
        self._bouton_reset: QPushButton | None = None
        # L'éditeur de touches (HP4) et la note sous la disposition ZQSD, que
        # l'éditeur fait apparaître dès qu'une touche est choisie à l'unité.
        self._editeur: EditeurTouches | None = None
        self._note_preregle: QLabel | None = None
        # L'onglet Image des jeux à correctif (`page_image`), None ailleurs.
        self._page_img: PageImage | None = None

        self.setWindowTitle(tr("Réglages de {}").format(game.name))
        self.setStyleSheet(themed(_STYLE) + feuille_de_style())
        self._build_ui()
        self.ouvrir_onglet(onglet)   # la page Difficulté ouvre « jeu » ; "" : la première
        self._taille_de_depart()

    def _taille_de_depart(self) -> None:
        """Celle de la maquette, bornée par l'écran : la fenêtre se redimensionne
        à la main, et chaque page défile si elle ne tient pas (règle 52)."""
        ecran = self.screen() or QGuiApplication.primaryScreen()
        voulue, mini = QSize(_TAILLE_VOULUE), QSize(*TAILLE_MINIMALE_PAGE)
        if ecran is not None:
            dispo = ecran.availableGeometry().size()
            voulue = voulue.boundedTo(QSize(int(dispo.width() * 0.92), int(dispo.height() * 0.9)))
            mini = mini.boundedTo(voulue)
        self.setMinimumSize(mini)
        self.resize(voulue)

    # ── Construction ──

    def _build_ui(self) -> None:
        # Maquette B « L'En-tête » (Ludo, 2026-11-13) : le bandeau du jeu en haut, ses rubriques en
        # pastilles, la page sur toute la largeur. Le rail de gauche (270 px) n'existe plus.
        racine = QVBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(0)

        # Du haut vers le bas : la pile est rattachée à la fenêtre AVANT de recevoir ses pages.
        # Rattachée après, toute la feuille de style repassait sur chaque page à chaque étage
        # (pile, colonne, fenêtre) : 350 des 1 270 ms de l'ouverture pour HP6 (2026-11-16).
        colonne = QWidget()
        transparent(colonne, "corpsReglages")
        colonne_centree(colonne)
        droite = QVBoxLayout(colonne)
        droite.setContentsMargins(0, 0, 0, 0)
        droite.setSpacing(0)
        racine.addWidget(colonne, stretch=1)
        self._defile = QStackedWidget()
        transparent(self._defile)
        droite.addWidget(self._defile, stretch=1)
        self._contenus: list[QWidget] = []
        self._beta: dict[str, QWidget] = {}
        pages = []
        for ident, libelle, icone in _ONGLETS:
            contenu = QWidget()
            transparent(contenu)
            page = QVBoxLayout(contenu)
            # Le nom de la rubrique est dans sa pastille, cochée : la page n'a plus de grand titre.
            page.setContentsMargins(MARGES_PAGE[0], 24, MARGES_PAGE[2], MARGES_PAGE[3])
            page.setSpacing(0)
            corps = QVBoxLayout()
            corps.setContentsMargins(0, 0, 0, 0)
            corps.setSpacing(0)
            page.addLayout(corps)
            self._lignes_de_page = []
            if not self._remplir(ident, corps):
                contenu.deleteLater()
                continue
            if ident == "difficulte" and self._panneau is not None:
                self._beta[ident] = self._panneau.pastille_beta
            self._contenus.append(contenu)
            if ident == "image" and self._page_img is not None:
                # La page Image défile en dedans : ses onglets, sa recherche et sa fiche restent en place.
                corps.setStretch(0, 1)
                page.setStretch(page.count() - 1, 1)
                self._defile.addWidget(contenu)
            else:
                page.addStretch()
                if ident != "difficulte":
                    # Une colonne de lignes : à 1 920 px, le nom partait à 1 500 px de son
                    # contrôle (audit UI reg11). La Difficulté garde sa largeur, pour le cadran.
                    contenu.setMaximumWidth(LARGEUR_LISTE + MARGES_PAGE[0] + MARGES_PAGE[2])
                # La fiche à droite, comme la page Image (audit UI reg20) ; une page sans ligne
                # de réglage (Langue, Fichiers) n'en a pas.
                self._defile.addWidget(PageAvecFiche(contenu, self._lignes_de_page)
                                       if self._lignes_de_page else zone_defilable(contenu))
            pages.append((ident, libelle, icone))

        # Le bandeau sur toute la largeur, au-dessus de la colonne centrée (audit plein écran).
        racine.insertWidget(0, self._bandeau(pages))
        self._erreur = QLabel("")
        self._erreur.setFont(police(13))
        self._erreur.setWordWrap(True)
        self._erreur.setTextFormat(Qt.TextFormat.PlainText)
        self._erreur.setStyleSheet("color: #e8955a; background: transparent;")
        self._erreur.setContentsMargins(MARGES_PAGE[0], 8, MARGES_PAGE[2], 8)
        self._erreur.hide()
        droite.addWidget(self._erreur)
        droite.addWidget(self._pied())
        if self._onglets:
            next(iter(self._onglets.values())).setChecked(True)

    def _bandeau(self, pages) -> QWidget:
        """Le bandeau du jeu : retour, nom, rubriques en pastilles (celles du Carnet et des Collections)."""
        # Le chemin du retour dit OÙ il mène, avec le même mot que Paramètres et
        # Mes années : la fiche vit dans la bibliothèque (audit UI, 2026-10-14).
        retour = bouton_retour(tr("Bibliothèque"), self.accept)
        retour.setToolTip(tr("Échap pour revenir"))
        bandeau, self._titre, rangee = bandeau_du_jeu(self.game, retour)

        self._groupe_onglets = QButtonGroup(self)
        self._groupe_onglets.setExclusive(True)
        self._onglets: dict[str, QPushButton] = {}
        for rang, (ident, libelle, icone) in enumerate(pages):
            btn = pastille_rubrique(tr(libelle), icone)
            btn.toggled.connect(lambda oui, r=rang: oui and self._defile.setCurrentIndex(r))
            btn.toggled.connect(lambda oui, i=ident: oui and self._noter_pied(i))
            self._groupe_onglets.addButton(btn)
            self._onglets[ident] = btn
            if (beta := self._beta.get(ident)) is not None:
                badge_dans_la_pastille(btn, beta)
            rangee.addWidget(btn)
        rangee.addStretch()
        self._zone_rail = bandeau
        return bandeau

    # ── Les pages ──

    def ouvrir_onglet(self, ident: str) -> None:
        """Ouvre la rubrique `ident` (« jeu » depuis la page Difficulté) ; absente, rien ne change."""
        if (btn := self._onglets.get(ident)) is not None:
            btn.click()

    def _correctif_actif(self) -> bool:
        """Le jeu déclare des réglages ET porte le nouveau correctif, qui les lira."""
        ini = self._ini
        return bool(self._reglages) and ini is not None and ini.is_file() \
            and reglages_correctif.est_nouveau_correctif(ini)

    def _remplir(self, onglet: str, corps: QVBoxLayout) -> bool:
        """Pose le contenu d'une page ; False si elle n'a rien à montrer."""
        if onglet == "image":
            return self._page_image_et_fluidite(corps)
        if onglet == "langue":
            # La langue n'a sa rubrique que si elle se RÈGLE : jeu qui en déclare,
            # et registre atteignable pour ceux qui la lisent là.
            if self.manager.game_language(self.game) is None:
                return False
            self._section_langue(corps)
            return True
        if onglet == "jeu":
            rempli = self._section_demarrage(corps)
            if self._section_correctif(corps, "jeu", titre=tr("En arrière-plan")):
                rempli = True
            if self._section_commandes(corps):
                rempli = True
            return self._section_captures(corps) or rempli
        if onglet == "difficulte":
            return self._page_difficulte(corps)
        return self._page_fichiers(corps)

    def _page_image_et_fluidite(self, corps: QVBoxLayout) -> bool:
        """L'image, la fluidité comprise (audit UI reg21), dans la page Image (`page_image`).

        HP1 et HP2 (rendu D3D11, résolution du launcher) et HP3 (réglages graphiques) l'ont même sans
        le nouveau correctif : leurs réglages d'image n'en dépendent pas, ceux du correctif s'y
        ajoutent quand il est là."""
        resolution = self.game.resolution
        du_launcher = resolution is not None and not resolution_jeu.du_correctif(resolution)
        if qualite_rendu.gere(self.game) or self._conf_graph is not None or du_launcher:
            return self._page_image(corps)
        if not self._reglages:
            self._section_affichage(corps)
            return True
        if not self._correctif_actif():
            # Jeu absent ou ancien correctif : une seule note pour toute la page.
            return any(self._section_correctif(corps, o) for o in ("affichage", "image", "perfs"))
        return self._page_image(corps)

    def _section_commandes(self, corps: QVBoxLayout) -> bool:
        """Manette ou touches, dans la page Jeu (audit UI reg21 : la page Commandes avait deux lignes)."""
        if not self._correctif_actif():
            # Une seule note pour les touches ET la manette du correctif.
            note = (self._section_correctif(corps, "commandes")
                    or self._section_correctif(corps, "manette"))
            return self._section_manette(corps) or note
        a_des_touches = self._section_disposition(corps)
        if a_des_touches and "touches_zqsd" in self._controles:
            self._section_touches(corps)
        return self._section_manette(corps) or a_des_touches

    def _page_image(self, corps: QVBoxLayout) -> bool:
        """Affichage et qualité d'image à gauche, chaque effet à droite.

        Les préréglages d'abord (Ludo, 2026-09-30 : « les gens s'y retrouvent
        pas ») ; chaque effet reste réglable, et désormais VISIBLE à côté : on
        voit ce que change un préréglage au moment où on le choisit.
        """
        config = self.manager.config
        magasins: list[tuple[Magasin, tuple[Reglage, ...]]] = []
        if self._ini is not None and self._correctif_actif():
            portes = tuple(r for r in self._reglages if r.onglet in ("affichage", "image", "perfs"))
            if portes:
                magasins.append((MagasinCorrectif(self._ini), portes))
        prereglages = None
        if qualite_rendu.gere(self.game):
            self._magasins_image.append((qualite_rendu.MagasinRendu(self.game, config, config.save),
                                         tuple(qualite_rendu.REGLAGES.values())))
            prereglages = qualite_rendu.PREREGLAGES
        elif self._conf_graph is not None:
            self._magasins_image.append((reglages_graphiques.MagasinGraphique(self._conf_graph),
                                         tuple(reglages_graphiques.REGLAGES.values())))
            prereglages = reglages_graphiques.PREREGLAGES
        magasins += self._magasins_image
        libres = self._lignes_libres()
        if not magasins and self.game.resolution is None and not libres:
            return False
        note = (tr("Réglez la résolution ici, pas dans le menu du jeu : ses options vidéo peuvent "
                   "l'empêcher de redémarrer.")
                if self.game.display_locked and self.game.resolution is not None else "")
        self._page_img = PageImage(self.game, config, magasins, self._erreur_image, self._apres_ecriture,
                                   prereglages=prereglages, libres=libres, note_ecran=note)
        corps.addWidget(self._page_img, stretch=1)
        self._bouton_origine()
        return True

    def _lignes_libres(self) -> tuple[LigneLibre, ...]:
        """Ce que le launcher règle lui-même dans « Écran » : la taille du texte de HP1/HP2 et, sur un PC
        à deux cartes graphiques, la plus puissante pour leur rendu D3D11."""
        libres = []
        if texte_ue1.gere(self.game.id) and self.game.resolution is not None:
            libres.append(LigneLibre("taille_texte", tr("Taille du texte"), self._aide_texte(),
                                     self._controle_texte()))
        if qualite_rendu.gere(self.game) and preference_gpu.proposee():
            libres.append(LigneLibre("carte_puissante", tr("Lancer sur la carte graphique la plus puissante"),
                                     self._aide_carte_puissante(), self._controle_carte_puissante()))
        return tuple(libres)

    @staticmethod
    def _surtitre_cale(titre: str) -> QLabel:
        """Un surtitre de la hauteur de l'en-tête à légende : leurs cartes voisines
        commencent à la même ligne."""
        entete = surtitre(titre)
        entete.setMinimumHeight(_HAUTEUR_ENTETE)
        return entete

    def _fiche(self, aide_txt: str, reglage=None) -> str:
        """Ce qu'ouvre le « ? » : la description, puis tout ce qu'on sait du réglage."""
        e = html.escape
        paragraphes = [e(aide_txt)]
        if reglage is not None:
            if reglage.cout:
                paragraphes.append("<br>".join(
                    # « {} : {} » traduit : l'espace avant les deux-points est française (f119) ;
                    # les points, comme sur la ligne et dans la fiche de la page Image.
                    tr("{} : {}").format(e(tr(_RESSOURCES.get(r, r))),
                                         f'<span style="color:{_COULEURS_COUT[n]}">'
                                         f"{e(tr(_NIVEAUX[n]))} {'●' * n}</span>") for r, n in reglage.cout))
            if reglage.se_voit:
                paragraphes.append(f'<span style="color:{theme_courant().accent}">'
                                   f"{e(tr('Se voit nettement à l’écran.'))}</span>")
            # L'onglet Difficulté le dit une fois, en tête : pas à chaque fiche.
            paragraphes += [e(_texte_beta())] if reglage.beta and reglage.onglet != "difficulte" else []
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
        self._section(corps, self._surtitre_cale(titre) if titre else None, carte)
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
            transparent(bloc)
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
        if self._panneau is not None:
            self._panneau.rafraichir()
        valeurs = self._valeurs_affichees()
        for ident, bloc in self._blocs.items():
            reglage = reglages_correctif.REGLAGES[ident]
            bloquant = reglages_correctif.bloque_par(reglage, valeurs)
            bloc.setEnabled(bloquant is None)
            effet = bloc.haut.graphicsEffect()
            if bloquant is None:
                if effet is not None:
                    bloc.haut.setGraphicsEffect(None)
                bloc.note.hide()
            else:
                if effet is None:
                    effet = QGraphicsOpacityEffect(bloc.haut)
                    effet.setOpacity(0.42)
                    bloc.haut.setGraphicsEffect(effet)
                phrase = reglages_correctif.phrase_blocage(reglage, bloquant)
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
        """« Revenir à l'installation » : ceux de l'ini tel qu'il était avant
        la première retouche du lanceur (demandé par Ludo, 2026-09-28 — surtout
        maintenant que les couleurs se règlent). Au pied : il vaut pour toutes
        les pages qui portent un réglage du correctif, d'où la confirmation.
        """
        if not self._ini_present() and not self._magasins_image:
            return
        btn = self._nouveau_bouton_reset()
        btn.clicked.connect(self._remettre_origine)
        self._maj_bouton_origine()

    def _ini_present(self) -> bool:
        return self._ini is not None and self._ini.is_file()

    def _a_remettre(self) -> bool:
        """Quelque chose a changé depuis l'installation : l'ini du correctif, le rendu, les réglages graphiques."""
        ini = self._ini
        return (ini is not None and self._ini_present() and reglages_correctif.a_une_origine(ini)) \
            or any(m.a_change() for m, _r in self._magasins_image)

    def _maj_bouton_origine(self) -> None:
        btn = self._bouton_reset
        if btn is None:
            return
        btn.setEnabled(self._a_remettre())
        btn.setToolTip(self._infobulle_origine() if btn.isEnabled() else tr(
            "Ceux du jeu tel qu'il a été installé. Rien n'a encore été changé depuis le launcher."))

    def _onglets_remis(self) -> list[str]:
        onglets = [r.onglet for r in self._reglages] if self._ini_present() else []
        return onglets + [r.onglet for _m, portes in self._magasins_image for r in portes]

    def _infobulle_origine(self) -> str:
        return tr("Pages remises comme à l'installation : {}.").format(self._pages_remises(self._onglets_remis()))

    def _remettre_origine(self) -> None:
        if not self._confirmer_origine(self._pages_remises(self._onglets_remis())):
            return
        try:
            if self._ini is not None and self._ini_present() and self._reglages:
                reglages_correctif.remettre_origine(self._ini, self._reglages)
        except OSError:
            log.warning("Correctif : remise à l'origine impossible", exc_info=True)
            self._montrer_erreur()
            return
        for magasin, portes in self._magasins_image:
            try:
                magasin.remettre()
            except OSError:
                log.warning("Image : remise à l'origine impossible", exc_info=True)
                self._erreur_image(portes[0])
                return
        for reglage in self._reglages:
            widget = self._controles.get(reglage.ident)
            if widget is not None:
                self._remettre_controle(widget, reglage)
        if self._page_img is not None:
            self._page_img.rafraichir()
        if self._editeur is not None:
            self._editeur.rafraichir()
        self._maj_preregle()
        self._maj_dependances()
        self._maj_bouton_origine()
        self._erreur.hide()
        self._annoncer_remise()

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
                index = self._ajouter_a_la_main(widget, reglage, etat.valeur)
            widget.setCurrentIndex(index)
        else:
            widget.setChecked(bool(etat.valeur))
        widget.blockSignals(False)

    def _erreur_image(self, reglage: Reglage) -> None:
        """Un réglage de la page Image non écrit : le message nomme le fichier où il vit."""
        if reglage.ident in reglages_graphiques.REGLAGES:
            self._montrer_erreur(tr(
                "Réglage non enregistré : le fichier des réglages graphiques du jeu "
                "n'a pas pu être modifié (jeu en cours, ou fichier en lecture seule)."))
        else:
            self._montrer_erreur()

    def _montrer_erreur(self, texte: str = "") -> None:
        # Le nom du VRAI fichier : HP1 à HP3 n'ont pas de d3d9.ini (winmm.ini,
        # dinput8.ini ; grand audit du 2026-11-02).
        nom = self._ini.name if self._ini is not None else "d3d9.ini"
        self._erreur.setText(texte or tr(
            "Réglage non enregistré : le fichier {} du jeu n'a pas "
            "pu être modifié (jeu en cours, ou fichier en lecture seule).").format(nom))
        self._erreur.show()

    def _ligne(self, libelle_txt: str, controle: QWidget, aide_txt: str,
               reglage=None, retrait: bool = False) -> _LigneImage:
        """La ligne de la page Image, pour toutes les pages (audit UI reg20 : trois façons de montrer
        un réglage dans la même fenêtre) : le nom, « Bêta », le coût s'il pèse, le contrôle dans sa
        colonne à côté du nom. Plus de « ? » : la fiche de la page le dit, à droite, ou l'infobulle
        quand la fenêtre est trop étroite (`PageAvecFiche`)."""
        ident = reglage.ident if reglage is not None else libelle_txt
        ligne = _LigneImage(ident, libelle_txt, reglage, controle, retrait)
        # Le libellé est à côté, pas dedans : sans nom accessible, un lecteur d'écran n'annoncerait
        # qu'« interrupteur » (règle 15) ; `_LigneImage` le pose.
        controle.setAccessibleDescription(aide_txt)
        fiche = self._fiche(aide_txt, reglage)
        self._aides[ident] = fiche
        self._lignes_de_page.append((ligne, libelle_txt, fiche))
        return ligne

    @staticmethod
    def _egaliser(carte: QWidget) -> None:
        """Une seule largeur pour les listes d'une carte : une liste plus large que les autres,
        c'était le désordre de l'ancienne fenêtre. La colonne des contrôles, elle, est celle de
        toutes les lignes (`_LigneImage`)."""
        listes = carte.findChildren(QComboBox)
        largeur = min(max([c.sizeHint().width() for c in listes] + [48]), 260)
        for liste in listes:
            liste.setFixedWidth(largeur)

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
                self._ajouter_a_la_main(choix, reglage, etat.valeur)
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
            return
        self._apres_ecriture()   # avant l'exclusion, dont l'erreur était aussitôt effacée
        self._appliquer_exclusion(reglage, valeur)
        self._maj_dependances()
        if reglage.ident == "touches_zqsd" and self._editeur is not None:
            self._editeur.rafraichir()

    def _apres_ecriture(self) -> None:
        """Ce que change toute écriture réussie : le bouton de remise à l'origine
        (la première retouche vient de garder l'ini d'origine), et l'erreur passée."""
        self._maj_bouton_origine()
        self._erreur.hide()
