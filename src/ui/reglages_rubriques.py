"""Les rubriques de `GameSettingsDialog` (classe parente) et les constantes de
la fenêtre ; les méthodes lisent les attributs posés par la fenêtre. Chaque
rubrique est un surtitre doré et une carte de lignes, comme les Paramètres.
"""

import logging
from collections.abc import Callable, Iterable
from functools import cached_property
from pathlib import Path
from typing import NamedTuple

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QColor
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

from src.core import (captures, difficulte_jeu, manette, preference_gpu, reglages_correctif, reprise,
                      resolution_jeu, texte_ue1, videos_lancement)
from src.core import difficulte_presets as dp
from src.core.i18n import tr
from src.core.reglages_table import Reglage
from src.ui import choix_sauvegarde
from src.ui.choix_jeux import espacee
from src.ui.difficulte_panneau import PanneauDifficulte
from src.ui.composants import (
    transparent,
    MARGES_PAGE,
    ENCRE_DISCRETE, ENCRE_DOUCE, LISTE, Carte, LigneReglage, bouton, police, surtitre,
)
from src.ui.editeur_touches import EditeurTouches
from src.ui.fenetre_message import FenetreMessage
from src.ui.fonts import body_font
from src.ui.icon_button import pixmap_icone
from src.ui.styles import RADIO_STYLE
from src.ui.theme import accent_qcolor, current as current_theme, themed
from src.ui.toggle_switch import ToggleSwitch
from src.ui.utils import liste_deroulante, open_local_path

log = logging.getLogger(__name__)

# Les rubriques, dans l'ordre du rail : (identifiant, libellé, pictogramme).
# L'image d'abord : c'est ce qu'on vient régler le plus souvent. Le rail ne porte
# que des pages : les actions sur les fichiers ont la leur, en dernier (audit UI
# reg24 : une entrée sur deux lançait une action, « Désinstaller » à un clic d'un curseur).
_ONGLETS = (
    # En PREMIER, et à part (Ludo, 2026-11-03) : les joueurs qui ne parlent pas
    # français ne trouvaient pas la langue, rangée dans « Jeu ».
    ("langue", "Langue", "site"),
    # Performances y entre, en « Fluidité » (audit UI reg21 : six rubriques dont trois de deux à
    # quatre lignes, pendant que « Qualité » en avait quinze).
    ("image", "Image", "ecran"),
    # Démarrage, arrière-plan, manette ou touches, captures : la page Commandes n'avait que deux
    # lignes (reg21). « Jeu » : des curseurs, le drapeau n'évoquait rien de tout ça (tra15).
    ("jeu", "Jeu", "curseurs"),
    # Tout ce qui règle la difficulté, presets et détail (Ludo, 2026-10-31).
    ("difficulte", "Difficulté", "epee"),
    ("fichiers", "Fichiers", "dossier"),
)


class ActionFichier(NamedTuple):
    """Une action de la rubrique Fichiers. Elle referme la fenêtre avant d'agir,
    sinon son dialogue s'empilerait sur celui-ci."""
    libelle: str
    rappel: Callable[[], None]
    explication: str
    commande: str           # le libellé du bouton
    risquee: bool = False   # à part, en dernier, bouton rouge

# Repères de coût (Ludo, 2026-09-30) : vert faible, orange moyen, rouge extrême.
# Hors palette de maison, comme le filet des alertes : ce sont des signaux, et
# ils se lisent aussi sans la couleur (un, deux ou trois points allumés).
_COULEURS_COUT = {1: "#6cc58a", 2: "#e8955a", 3: "#ec5f5f"}
# Ce qu'un réglage a perdu d'effet, dit sous son nom : ambre, pas rouge.
_COULEUR_NOTE = "#c9954a"

# Une liste de la page : plus basse et plus sobre que celle des Paramètres,
# elle s'aligne en colonne avec les interrupteurs (`composants.LISTE`).
_LISTE_STYLE = LISTE

_RESSOURCES = {"GPU": "Carte graphique (GPU)", "CPU": "Processeur (CPU)", "RAM": "Mémoire (RAM)"}
_NIVEAUX = {1: "faible", 2: "moyenne", 3: "extrême"}
# Les marges de lecture d'une page.
# Le temps que reste au pied la confirmation d'une remise à l'origine.
_DUREE_ANNONCE_PIED = 4000
# La page qui montre un réglage, quand son `onglet` n'est pas celui du rail.
_PAGE_DE = {"affichage": "image", "perfs": "image", "commandes": "jeu", "manette": "jeu",
            "demarrage": "jeu"}

# Réglages annoncés mais pas encore livrés. Ils sont ÉCRITS, pas résumés en
# « bientôt » : quelqu'un qui cherche la résolution doit reconnaître ce qu'il
# cherche, et comprendre que ce n'est pas lui qui n'a pas trouvé.
_A_VENIR = (
    "Résolution",
    "Qualité graphique",
    "Mode fenêtré / plein écran",
)



def _ligne_alignee(titre: str, description: str = "", *commandes: QWidget) -> LigneReglage:
    """Une `LigneReglage` aux marges des lignes de réglage (`page_image._LigneImage`, 14 et
    6 px) : ses 20 et 14 px des Paramètres décalaient le nom de la carte Captures sous ceux de
    Démarrage (audit UI f43)."""
    ligne = LigneReglage(titre, description, *commandes)
    ligne.layout().setContentsMargins(14, 6, 12, 6)
    return ligne

class RubriquesDuJeu:
    """Rubriques simples de `GameSettingsDialog` (voir le module)."""

    def _titre_rubrique(self, texte: str, verrouille: bool = False) -> QWidget:
        """Le surtitre doré d'une rubrique ; « BIENTÔT » à côté si elle est verrouillée."""
        ligne = QWidget()
        transparent(ligne)
        h = QHBoxLayout(ligne)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        lbl = surtitre(texte)
        if verrouille:
            lbl.setStyleSheet(f"color: {ENCRE_DISCRETE}; background: transparent;")
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
    def _ajouter_a_la_main(liste: QComboBox, reglage, valeur) -> int:
        """La valeur posée à la main dans l'ini, rangée entre les crans qui l'encadrent."""
        # Une ancienne valeur à la main ne reste pas dans la liste à côté de la nouvelle.
        for i in reversed(range(liste.count())):
            if liste.itemData(i) not in reglage.choix:
                liste.removeItem(i)
        rang = reglages_correctif.rang_a_la_main(reglage, valeur)
        liste.insertItem(rang, tr("{} (réglé à la main)").format(
            reglages_correctif.texte_valeur(valeur)), valeur)
        return rang

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
            carte.ajouter(_ligne_alignee(
                tr("Ce jeu n'est installé que dans une seule langue."),
                tr("Le launcher ne peut que sélectionner une langue déjà présente "
                   "sur le disque, pas la télécharger.")))
            self._section(corps, None, carte)
            self._note_langues(corps)
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
            transparent(ligne)
            h = QHBoxLayout(ligne)
            h.setContentsMargins(20, 11, 20, 11)
            h.addWidget(radio)
            carte.ajouter(ligne)
        self._section(corps, None, carte)
        self._note_langues(corps)

    def _note_langues(self, corps: QVBoxLayout) -> None:
        """Prévenir que la liste n'est pas celle du launcher (Ludo, 2026-11-03) :
        un jeu peut avoir d'autres langues, et plus nombreuses."""
        self._note(corps, tr(
            "Ce jeu a ses propres langues, parfois plus nombreuses que celles du launcher. "
            "Par défaut, il suit celle du launcher quand il l'a."))

    def _section_touches(self, corps: QVBoxLayout) -> None:
        """Chaque action de HP4 et sa touche, réglables une par une.

        Sous la disposition : elle couvre le cas le plus courant en un geste,
        l'éditeur tout le reste (gaucher, pavé numérique, souris à boutons).
        """
        self._editeur = EditeurTouches(self._ini)
        self._editeur.modifie.connect(self._touches_modifiees)
        self._editeur.echec.connect(self._montrer_erreur)
        entete = QWidget()
        transparent(entete)
        h = QHBoxLayout(entete)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(surtitre(tr("Touches une par une")))
        h.addStretch()
        h.addWidget(self._editeur.tout)
        bloc = QWidget()
        transparent(bloc)
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
        """Jeu sans aucun réglage d'image : ce qui vient, verrouillé (HP1 à HP3 ont leur page Image)."""
        carte = Carte()
        # Sous une rubrique active, des choix grisés sans « BIENTÔT » auraient
        # l'air de réglages cassés (règle 119) : seulement sous la rubrique verrouillée.
        for nom in _A_VENIR:
            item = QRadioButton(tr(nom))
            item.setFont(police(14))
            item.setEnabled(False)
            item.setStyleSheet(
                "QRadioButton { color: #55556a; background: transparent; }")
            ligne = QWidget()
            transparent(ligne)
            h = QHBoxLayout(ligne)
            h.setContentsMargins(20, 11, 20, 11)
            h.addWidget(item)
            carte.ajouter(ligne)
        self._egaliser(carte)
        self._section(corps, self._titre_rubrique(tr("Affichage"), verrouille=True), carte)
        if self.game.display_locked:
            # Cette rubrique est exactement l'endroit où va celui qui cherche la
            # résolution — donc celui qui, ne la trouvant pas ici, ira la
            # chercher dans le menu du jeu et cassera son installation.
            note = QLabel(tr(
                "Ne touchez pas aux options vidéo DANS le jeu : l'affichage "
                "est déjà réglé au mieux par le launcher, et le modifier ici "
                "peut empêcher le jeu de redémarrer.\n"
                "Ces réglages viendront ici."))
            note.setFont(police(13))
            note.setWordWrap(True)
            note.setTextFormat(Qt.TextFormat.PlainText)
            note.setStyleSheet("color: #e8955a; background: transparent;")
            corps.addSpacing(10)
            corps.addWidget(note)

    def _controle_texte(self) -> QComboBox:
        """La taille du texte de HP1/HP2 : automatique, ou plus petite ou plus grande (ligne d'« Écran »).

        Une liste et non un curseur : à la manette, ← → réglaient le curseur
        sans pouvoir en sortir (`manette_nav`). Posée au lancement (`texte_ue1`).
        """
        choix = self._liste()
        place = resolution_jeu.place_pour(self.game, self.manager.config)
        taille = resolution_jeu.voulue(self.manager.config.resolution_jeu.get(self.game.id, ""), place)
        auto = texte_ue1.facteur(taille[1], "") if taille is not None else None
        choix.addItem(tr("Automatique (×{})").format(reglages_correctif.texte_valeur(auto))
                      if auto else tr("Automatique"), "")
        for cle, libelle in (("petit", tr("Plus petit")), ("grand", tr("Plus grand")),
                             ("tres_grand", tr("Très grand")),
                             (texte_ue1.ORIGINE, tr("D'origine (texte de {})").format(self.game.year))):
            choix.addItem(libelle, cle)
        courant = self.manager.config.taille_texte.get(self.game.id, "")
        choix.setCurrentIndex(max(0, choix.findData(courant)))
        choix.currentIndexChanged.connect(lambda _i, c=choix: self._on_taille_texte(c.currentData()))
        return choix

    def _aide_texte(self) -> str:
        return tr(
            "Le jeu agrandit ses menus avec l'écran, mais garde le texte de {annee}, minuscule en "
            "haute définition. Le launcher redessine ses lettres à la taille de l'image : "
            "automatique, le texte retrouve sa place d'origine dans les cadres. Plus grand peut "
            "déborder de certains cadres.").format(annee=self.game.year)

    def _on_taille_texte(self, valeur: str) -> None:
        tailles = self.manager.config.taille_texte
        if valeur:
            tailles[self.game.id] = valeur
        else:
            tailles.pop(self.game.id, None)
        self.manager.config.save()

    def _controle_carte_puissante(self) -> ToggleSwitch:
        """Deux cartes graphiques (Windows) : demander la plus puissante pour l'exe du jeu."""
        exe = self.manager.config.install_path / self.game.executable
        bascule = ToggleSwitch(preference_gpu.active(exe))
        bascule.toggled.connect(lambda oui: self._on_carte_puissante(bascule, exe, oui))
        return bascule

    @staticmethod
    def _aide_carte_puissante() -> str:
        return tr(
            "Ce PC a deux cartes graphiques, et Windows lance souvent ce jeu sur la plus "
            "économe. Allumé, le launcher le note dans les réglages graphiques de Windows "
            "(Paramètres > Affichage > Graphiques), pour ce jeu seulement ; éteint, il le retire.")

    def _on_carte_puissante(self, bascule: ToggleSwitch, exe: Path, oui: bool) -> None:
        preference_gpu.poser(exe, oui)
        # L'interrupteur dit ce que porte VRAIMENT le registre (règle 118).
        vrai = preference_gpu.active(exe)
        if vrai != oui:
            bascule.blockSignals(True)
            bascule.setChecked(vrai)
            bascule.blockSignals(False)

    def _liste(self) -> QComboBox:
        choix = liste_deroulante()
        choix.setFont(police(13))
        choix.setCursor(Qt.CursorShape.PointingHandCursor)
        choix.setStyleSheet(themed(_LISTE_STYLE))
        return choix

    def _nouveau_bouton_reset(self) -> QPushButton:
        """Le bouton du pied de page : bordé comme un vrai bouton, jamais un lien
        gris qu'on croirait désactivé (critique de la maquette)."""
        btn = bouton(tr("Revenir à l'installation"))
        icone, taille = espacee(pixmap_icone("replay", 18, QColor(current_theme().accent)), QSize(18, 18))
        btn.setIcon(icone)
        btn.setIconSize(taille)
        btn.setAutoDefault(False)
        self._bouton_reset = btn
        return btn

    @staticmethod
    def _pages_remises(onglets: Iterable[str]) -> str:
        """Les pages que touche une remise à l'origine, dans l'ordre du rail."""
        pages = {_PAGE_DE.get(o, o) for o in onglets}
        return " · ".join(tr(libelle) for ident, libelle, _icone in _ONGLETS if ident in pages)

    def _confirmer_origine(self, pages: str) -> bool:
        """La remise vaut pour toutes ces pages, même celles qu'on ne regarde pas,
        et ne s'annule pas : on demande, et Annuler est le choix par défaut."""
        boite = FenetreMessage(self)
        boite.setWindowTitle(tr("Remettre ce jeu comme à l'installation ?"))
        boite.setText(tr("Pages remises comme à l'installation : {}.").format(pages))
        retablir = boite.addButton(tr("Rétablir"), FenetreMessage.ButtonRole.DestructiveRole)
        annuler = boite.addButton(tr("Annuler"), FenetreMessage.ButtonRole.RejectRole)
        boite.setDefaultButton(annuler)
        boite.exec()
        return boite.clickedButton() is retablir

    def _annoncer_remise(self) -> None:
        """Le pied le dit quatre secondes, puis reprend ce qu'il disait."""
        self._poser_pied(tr("Réglages de l'installation remis."))
        self._minuteur_pied.start()

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
        etat = self._etat_manette
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
                "Branchez la manette avant de lancer le jeu : sans elle, il repasse au "
                "clavier. Se règle aussi dans les options du jeu.")))
        for reglage in du_correctif:
            self._controle(carte, self._ini, reglage)
        self._egaliser(carte)
        self._section(corps, self._titre_rubrique(tr("Manette")), carte)
        return True

    @cached_property
    def _etat_manette(self) -> bool | None:
        """Le choix manette du jeu (registre), None sans interrupteur : lu une fois pour la rubrique et sa page."""
        return manette.activee(self.game) if self._appliquer_manette is not None else None

    @cached_property
    def _quoi_demarrage(self) -> tuple[bool | None, bool, list]:
        """(logos passés, « Reprendre » proposé, réglages du correctif) : lus une fois pour la rubrique et sa page."""
        videos = self.game.videos_lancement
        etat = videos_lancement.passees(self.manager.config.install_path, videos) if videos else None
        du_correctif = [r for r in self._reglages if r.onglet == "demarrage"] if self._correctif_actif() else []
        return etat, self.game.id in reprise.JEUX, du_correctif

    @cached_property
    def _quoi_captures(self) -> tuple[int, str]:
        """(captures déjà prises, touche du correctif ou du catalogue) : lus une fois pour la rubrique et sa page."""
        # La touche du correctif se lit dans SON ini (seul le nouveau en a une) ;
        # celle d'un autre moteur, le catalogue la déclare.
        ini = reglages_correctif.ini_du_correctif(
            self.manager.config.install_path / Path(self.game.executable).parent)
        return captures.nombre(self.game), reglages_correctif.touche_capture(ini) or self.game.touche_capture

    def _difficulte_proposee(self) -> bool:
        """Un réglage de difficulté ou « Une seule vie » : sans eux (HP7, hors 1.4), pas de rubrique."""
        return bool(dp.idents_du_jeu(self.game, self._ini)) or dp.une_vie_proposee(self.game, self.manager.config)

    def _section_demarrage(self, corps: QVBoxLayout) -> bool:
        """« Démarrage » : passer les logos (HP3, les logos que le catalogue
        nomme) et « Reprendre » qui ouvre la dernière partie (HP1 à HP3, CE jeu
        seulement : Ludo, 2026-10-31, il était dans les Paramètres du launcher,
        où personne ne le cherchait)."""
        etat, reprend, du_correctif = self._quoi_demarrage
        if etat is None and not reprend and not du_correctif:
            return False
        carte = Carte()
        if reprend:
            bascule_reprise = ToggleSwitch(self.manager.config.reprise.get(self.game.id, False))
            bascule_reprise.toggled.connect(self._on_reprise)
            carte.ajouter(self._ligne(tr("Reprendre ouvre la dernière partie"), bascule_reprise, tr(
                "« Reprendre » ouvre directement votre dernière partie, sans passer par le menu du "
                "jeu. Éteint, le menu revient : pour charger une autre sauvegarde ou commencer une "
                "nouvelle partie.")))
        if etat is not None:
            bascule = ToggleSwitch(etat)
            bascule.toggled.connect(lambda oui: self._on_videos(bascule, oui))
            carte.ajouter(self._ligne(tr("Passer les logos"), bascule, tr(
                "Le jeu s'ouvre directement sur son menu, sans les logos des studios. "
                "Les vidéos sont gardées : il suffit de rallumer pour les revoir.")))
        for reglage in du_correctif:
            self._controle(carte, self._ini, reglage)
        self._egaliser(carte)
        self._section(corps, self._titre_rubrique(tr("Démarrage")), carte)
        return True

    def _on_reprise(self, oui: bool) -> None:
        # Choisi ici : la question d'après la première partie n'a plus lieu d'être.
        config = self.manager.config
        config.reprise[self.game.id] = oui
        config.save()

    def _on_videos(self, bascule: ToggleSwitch, oui: bool) -> None:
        dossier = self.manager.config.install_path
        videos_lancement.passer(dossier, self.game.videos_lancement, oui)
        # L'interrupteur dit ce que portent VRAIMENT les fichiers (règle 118).
        vrai = bool(videos_lancement.passees(dossier, self.game.videos_lancement))
        if vrai != oui:
            bascule.blockSignals(True)
            bascule.setChecked(vrai)
            bascule.blockSignals(False)

    def _page_difficulte(self, corps: QVBoxLayout) -> bool:
        """L'onglet Difficulté (Ludo, 2026-10-31 : « un seul onglet Difficulté avec
        tout dedans et pas une autre page ») : le cadran et les presets en haut
        (`PanneauDifficulte`), puis chaque réglage, puis « Une seule vie ».
        Choisir un preset remet chaque contrôle sur le fichier ; changer un
        réglage déplace l'aiguille (`_maj_dependances`)."""
        if not self._difficulte_proposee():
            return False
        # Bâtis DANS la page, déjà posée (règle 143) : rattachés après, panneau et carte repassaient
        # entiers sous la feuille de style (26 ms du premier clic sur la Difficulté de HP5).
        panneau = PanneauDifficulte(self.game, self.manager.config, self._ini, parent=corps.parentWidget())
        self._panneau = panneau
        corps.addWidget(panneau)
        choix_jeu, reglages = None, []
        # HP1 : le Quidditch seul, que les presets règlent déjà cran par cran.
        if panneau.sur_mesure:
            corps.addSpacing(14)
            carte = Carte()
            corps.addWidget(carte)
            choix_jeu = self._ligne_difficulte_jeu(carte)
            if self._correctif_actif():
                reglages = [r for r in self._reglages if r.onglet == "difficulte"]
            for reglage in reglages:
                self._controle(carte, self._ini, reglage)
            self._egaliser(carte)
        if (une_vie := panneau.bloc_une_seule_vie()) is not None:
            corps.addSpacing(34)
            corps.addWidget(une_vie)
        # HP5 et HP4 : écrire dans la sauvegarde du joueur, à son choix seulement (C8).
        if (dans_la_sauvegarde := choix_sauvegarde.bloc(self.game, self._partie_en_cours)) is not None:
            corps.addSpacing(34)
            corps.addWidget(dans_la_sauvegarde)
        panneau.choisi.connect(lambda _ident, rates: self._sur_preset(reglages, choix_jeu, rates))
        return True

    def _pied(self) -> QFrame:
        """Ce qui vaut pour toute la fenêtre : quand c'est pris en compte, et la
        remise à l'origine. Rien à dire et pas de bouton : pas de pied."""
        pied = QFrame()
        pied.setObjectName("pied")
        pied.setMinimumHeight(56)
        h = QHBoxLayout(pied)
        h.setContentsMargins(MARGES_PAGE[0], 10, MARGES_PAGE[2], 10)
        h.setSpacing(10)
        self._pied_info = QLabel()
        self._pied_info.setPixmap(pixmap_icone("infos", 18, accent_qcolor()))
        transparent(self._pied_info)
        h.addWidget(self._pied_info)
        self._pied_notes = QLabel("")
        self._pied_notes.setTextFormat(Qt.TextFormat.PlainText)
        self._pied_notes.setWordWrap(True)
        self._pied_notes.setFont(police(13))
        self._pied_notes.setStyleSheet(f"color: {ENCRE_DOUCE}; background: transparent;")
        h.addWidget(self._pied_notes, stretch=1)
        h.addStretch()   # le bouton reste à droite quand la note disparaît
        if self._bouton_reset is not None:
            h.addWidget(self._bouton_reset)
        self._cadre_pied = pied
        self._minuteur_pied = QTimer(self)
        self._minuteur_pied.setSingleShot(True)
        self._minuteur_pied.setInterval(_DUREE_ANNONCE_PIED)
        self._minuteur_pied.timeout.connect(lambda: self._noter_pied(self._onglet_pied))
        self._noter_pied("")
        return pied

    def _noter_pied(self, onglet: str) -> None:
        """Le pied dit QUAND c'est pris en compte pour l'onglet affiché : HP5 et
        HP6 relisent leur difficulté dans la seconde, HP4 ses dégâts (ses créatures
        au niveau suivant), le ciel de HP6 aussi, le reste au prochain lancement."""
        self._onglet_pied = onglet
        self._minuteur_pied.stop()
        if onglet == "difficulte" and self.game.id in ("hp5", "hp6"):
            contenu = tr("Change à tout moment, partie en cours comprise.")
        elif onglet == "difficulte" and self.game.id == "hp4":
            # Le correctif relit les dégâts dans la seconde, la jauge des créatures au chargement d'un niveau.
            contenu = tr("Les dégâts changent à tout moment, partie en cours comprise ; la résistance des "
                         "créatures, au prochain niveau.")
        elif not (self._correctif_actif() or self._conf_graph is not None
                  or self.game.resolution is not None):
            contenu = ""
        elif onglet == "image" and any(r.ident == "ciel" for r in self._reglages):
            contenu = tr("Pris en compte au prochain lancement du jeu, sauf le ciel, "
                         "qui change à tout moment.")
        else:
            contenu = tr("Pris en compte au prochain lancement du jeu.")
        self._poser_pied(contenu)

    def _poser_pied(self, contenu: str) -> None:
        self._pied_notes.setText(contenu)
        self._pied_notes.setVisible(bool(contenu))
        self._pied_info.setVisible(bool(contenu))
        montrer = bool(contenu) or self._bouton_reset is not None
        # Sans parent, un widget rendu visible devient une fenêtre : le pied est construit avant d'être posé.
        if self._cadre_pied.parentWidget() is not None or not montrer:
            self._cadre_pied.setVisible(montrer)

    def _sur_preset(self, reglages: list, choix_jeu: QComboBox | None, rates: list) -> None:
        """Un preset vient d'être écrit : chaque contrôle reprend ce que porte le fichier."""
        for reglage in reglages:
            if (widget := self._controles.get(reglage.ident)) is not None:
                self._remettre_controle(widget, reglage)
        if choix_jeu is not None:
            choix_jeu.blockSignals(True)
            choix_jeu.setCurrentIndex(difficulte_jeu.lire(self.game, self.manager.config) or 0)
            choix_jeu.blockSignals(False)
        self._maj_dependances()
        if rates:
            self._montrer_erreur(tr("Certains réglages n'ont pas pu être écrits (fichier absent ou en "
                                    "lecture seule) : le jeu garde les précédents."))
        else:
            self._apres_ecriture()

    def _ligne_difficulte_jeu(self, carte: Carte) -> QComboBox | None:
        """La difficulté propre au jeu (HP2), lue et écrite dans SON fichier
        (`difficulte_jeu`) : le menu du jeu et cette liste disent la même chose."""
        rang = difficulte_jeu.lire(self.game, self.manager.config)
        if rang is None:
            return None
        choix = self._liste()
        for valeur, nom in enumerate(difficulte_jeu.NIVEAUX):
            # Le rang 0, c'est Normal : « Facile » y promettait un jeu allégé.
            choix.addItem(tr("D'origine") if valeur == 0 else tr(nom), valeur)
        choix.setCurrentIndex(rang)
        choix.currentIndexChanged.connect(lambda _i, c=choix: self._on_difficulte(c))
        aide = tr(
            "La difficulté du jeu lui-même, qu'aucun de ses menus ne montre. Plus elle "
            "monte, plus Harry perd de vie à chaque coup (×1,2 d'origine, ×2 en Moyen, ×3 en "
            "Difficile) et plus les sorts ennemis vont vite ; le Basilic résiste davantage. "
            "À régler jeu fermé ; compte au prochain lancement.")
        carte.ajouter(self._ligne(tr("Difficulté du jeu"), choix, aide, reglage=Reglage(
            "difficulte_jeu", "", "", "Difficulté du jeu", aide, onglet="difficulte", beta=True)))
        return choix

    def _on_difficulte(self, choix: QComboBox) -> None:
        if difficulte_jeu.ecrire(self.game, self.manager.config, choix.currentData()):
            self._maj_dependances()
            return
        # Pas écrit : la liste revient sur ce que porte VRAIMENT le fichier (règle 118).
        choix.blockSignals(True)
        choix.setCurrentIndex(difficulte_jeu.lire(self.game, self.manager.config) or 0)
        choix.blockSignals(False)
        self._montrer_erreur(tr(
            "Difficulté non enregistrée : le fichier de réglages du jeu n'a pas pu être "
            "modifié (fichier absent ou en lecture seule)."))

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
        n, touche = self._quoi_captures
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
        ouvrir = bouton(tr("Ouvrir le dossier"))
        icone, taille = espacee(pixmap_icone("dossier", 18, QColor(current_theme().accent)), QSize(18, 18))
        ouvrir.setIcon(icone)
        ouvrir.setIconSize(taille)
        ouvrir.setAutoDefault(False)
        ouvrir.clicked.connect(self._ouvrir_captures)
        self._compte_captures = QLabel("")
        self._compte_captures.setFont(police(13))
        self._compte_captures.setStyleSheet(f"color: {ENCRE_DOUCE}; background: transparent;")
        rangees = tr("Dans Images › Accio Launcher.")
        titre, description = (tr("Touche {} en jeu").format(touche), rangees) if touche else (rangees, "")
        carte = Carte()
        carte.ajouter(_ligne_alignee(titre, description, self._compte_captures, ouvrir))
        self._section(corps, entete, carte)
        self._afficher_compte(n)
        return True

    def _afficher_compte(self, n: int) -> None:
        # Rien quand il n'y en a pas : « 0 » ne dit rien d'utile. Le nombre seul :
        # la rubrique et sa ligne nomment déjà les captures.
        if self._compte_captures is None:
            return
        self._compte_captures.setText(str(n) if n else "")

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

    def _page_fichiers(self, corps: QVBoxLayout) -> bool:
        """Les actions sur les fichiers du jeu, chacune avec ce qu'elle fait ; celle
        qui ne se défait pas (« Désinstaller ») à part et en dernier (audit UI reg24)."""
        if not self._actions:
            return False
        sures = Carte()
        risquees = Carte()
        for action in self._actions:
            btn = bouton(action.commande)
            if action.risquee:
                btn.setObjectName("danger")
            btn.setAutoDefault(False)
            btn.clicked.connect(lambda _c=False, r=action.rappel: self._lancer(r))
            (risquees if action.risquee else sures).ajouter(
                _ligne_alignee(action.libelle, action.explication, btn))
        for rang, carte in enumerate(c for c in (sures, risquees) if c.findChildren(LigneReglage)):
            if rang:
                corps.addSpacing(28)
            corps.addWidget(carte)
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
        for code, bouton_ in self._boutons.items():
            bouton_.blockSignals(True)
            bouton_.setChecked(code == courant)
            bouton_.blockSignals(False)
