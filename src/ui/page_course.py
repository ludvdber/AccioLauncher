"""La page Course (1.5) : tout ce qu'il faut voir avant de partir, sur une page du jeu et non plus dans une boîte.

Maquette « Page Course » du canevas de la 1.5 (Ludo, 2026-11-25 : « pour le speedrun ça me semble ok ») : le
bandeau du jeu en haut, comme ses réglages et son journal, ses catégories en pastilles dans le bandeau (celles de
speedrun.com pour CE jeu, `course_regles`) ; à gauche ce que la catégorie demande, le départ, l'arrivée et le
temps qui classe dits en clair, les règles détaillées repliées (un débutant lit une phrase, un habitué déplie),
le fantôme, ce qui bloque et « Partir » ; à droite le record du joueur, sa course idéale, ses essais, et le
classement Accio de la catégorie, visible sans clic de plus.

« Partir » calcule l'empreinte des fichiers du jeu dans un fil (`course_ui.EmpreinteThread`), puis ferme la page
avec un `Choix` : le départ lui-même est l'affaire de `course_ui.lancer`. Fermer la page autrement (retour,
Échap, une autre page ouverte par-dessus) ne lance rien : `choix` reste None.

L'affichage dans le jeu (Simple ou Complet, coin de l'écran) n'est PAS ici : le correctif ne sait pas encore le
lire, et un réglage que la DLL ignorerait mentirait (étape 5 du plan de la 1.5).
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core import classement, course, mode_course
from src.core.course_regles import Categorie, Regles
from src.core.game_data import GameData
from src.core.game_manager import GameManager
from src.core.i18n import tr, trn
from src.ui import course_ui
from src.ui.bandeau_jeu import bandeau_du_jeu
from src.ui.composants import (
    ENCRE,
    ENCRE_DOUCE,
    MARGES_PAGE,
    TAILLE_MINIMALE_PAGE,
    Carte,
    LigneReglage,
    bouton,
    bouton_retour,
    colonne_centree,
    feuille_de_style,
    filtre,
    lien,
    surtitre,
    texte,
    transparent,
)
from src.ui.entree_focus import entree_suit_le_focus
from src.ui.fonts import cinzel
from src.ui.theme import themed
from src.ui.toggle_switch import ToggleSwitch
from src.ui.utils import zone_defilable

_OR = "#d6a72c"
_ROUGE = "#e07a6a"
_LARGEUR_DROITE = 380
_CLASSES_MONTRES = 5
_BARRE = ("QProgressBar { background: #141428; border: 1px solid #2a2a48; border-radius: 4px; height: 8px; }"
          "QProgressBar::chunk { background: #d6a72c; border-radius: 3px; }")


@dataclass(frozen=True)
class Choix:
    """Ce que la page a décidé : la course part avec ça."""
    jeu: str
    ini: Path
    categorie: str
    empreinte: course.Empreinte
    fantome: bool


@dataclass(frozen=True)
class Actions:
    """Ce que la page peut ouvrir ailleurs ; None : pas proposé (fiche seule, dans un test)."""
    difficulte: Callable[[], None] | None = None
    mettre_a_jour: Callable[[], None] | None = None
    carnet: Callable[[], None] | None = None


def phrase_du_temps(regles: Regles) -> str:
    """Le temps qui classe le jeu, et l'autre, gardé aussi."""
    if regles.temps == course.REEL:
        return tr("Temps réel, chargements compris : celui que speedrun.com classe pour ce jeu. Le temps sans "
                  "chargements est gardé aussi.")
    return tr("Temps sans les chargements : celui que speedrun.com classe pour ce jeu. Le temps réel est gardé "
              "aussi.")


def nom_categorie(regles: Regles | None, ident: str) -> str:
    """Le nom montré d'une catégorie (« Tous les boucliers ») ; son identifiant si le catalogue ne la connaît pas."""
    c = regles.categorie(ident) if regles is not None else None
    return c.nom if c is not None else ident


def _gris(contenu: str, px: int = 13) -> QLabel:
    return texte(contenu, px, ENCRE_DOUCE, retour=True)


class CoursePage(QDialog):
    """La page de départ d'une course. `choix` est posé quand l'empreinte est prête, juste avant `accept`."""

    def __init__(self, game: GameData, manager: GameManager, *, actions: Actions | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        entree_suit_le_focus(self)
        regles = game.course
        if regles is None:
            raise ValueError(f"{game.id} n'a pas de course")
        self.game = game
        self.regles: Regles = regles
        self._manager = manager
        self._actions = actions or Actions()
        config = manager.config
        self._install_path = Path(config.install_path)
        self.ini = mode_course.ini(game, self._install_path)
        self.fantome = config.course_fantome
        self.choix: Choix | None = None
        self.empreinte: course.Empreinte | None = None
        self._fil: course_ui.EmpreinteThread | None = None
        self._courses = course.passees(game.id)
        self._classement = classement.en_cache()
        recente = next((c.categorie for c in self._courses if self.regles.categorie(c.categorie)), None)
        self.categorie = recente or self.regles.categories[0].ident
        self.bloquants = course_ui.bloquants(game, config) if self.ini is not None else []
        self.setWindowTitle(tr("Course : {}").format(game.name))
        self.setMinimumSize(*TAILLE_MINIMALE_PAGE)
        self.setStyleSheet(themed(_BARRE) + feuille_de_style())
        self._construire()
        self._montrer_categorie()

    # ── Construction ──

    def _construire(self) -> None:
        racine = QVBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(0)
        bandeau, _nom, rangee = bandeau_du_jeu(self.game, bouton_retour(tr("Bibliothèque"), self.reject))
        rangee.addWidget(surtitre(tr("Course")))
        rangee.addSpacing(8)
        self.pastilles: dict[str, QPushButton] = {}
        groupe = QButtonGroup(self)
        groupe.setExclusive(True)
        for c in self.regles.categories:
            b = filtre(c.nom, grand=True)
            b.setChecked(c.ident == self.categorie)
            b.setToolTip(c.regle)
            b.clicked.connect(lambda _c=False, ident=c.ident: self.choisir(ident))
            groupe.addButton(b)
            self.pastilles[c.ident] = b
            rangee.addWidget(b)
        rangee.addStretch()
        racine.addWidget(bandeau)

        corps = QWidget()
        transparent(corps, "corpsCourse")
        lay = QHBoxLayout(corps)
        lay.setContentsMargins(*MARGES_PAGE)
        lay.setSpacing(36)
        lay.addLayout(self._gauche(), 1)
        droite = QWidget()
        transparent(droite, "droiteCourse")
        droite.setFixedWidth(_LARGEUR_DROITE)
        self._droite = QVBoxLayout(droite)
        self._droite.setContentsMargins(0, 0, 0, 0)
        self._droite.setSpacing(8)
        lay.addWidget(droite, alignment=Qt.AlignmentFlag.AlignTop)
        colonne_centree(corps)
        racine.addWidget(zone_defilable(corps), 1)

    def _gauche(self) -> QVBoxLayout:
        gauche = QVBoxLayout()
        gauche.setSpacing(10)
        self._regle = texte("", 16, ENCRE, retour=True)
        self._regle.setObjectName("regleCategorie")
        gauche.addWidget(self._regle)
        self._note = _gris("")
        self._note.setObjectName("noteCategorie")
        gauche.addWidget(self._note)
        gauche.addSpacing(6)
        carte = Carte()
        carte.ajouter(LigneReglage(tr("Départ du chrono"), self.regles.depart))
        carte.ajouter(LigneReglage(tr("Arrivée"), self.regles.arrivee))
        carte.ajouter(LigneReglage(tr("Temps qui classe"), phrase_du_temps(self.regles)))
        gauche.addWidget(carte)

        self.bouton_regles = lien(tr("Règles détaillées"), discret=True)
        self.bouton_regles.setCheckable(True)
        self.bouton_regles.toggled.connect(self._deplier_regles)
        gauche.addWidget(self.bouton_regles, alignment=Qt.AlignmentFlag.AlignLeft)
        self.regles_detaillees = QFrame()
        transparent(self.regles_detaillees, "reglesDetaillees")
        detail = QVBoxLayout(self.regles_detaillees)
        detail.setContentsMargins(4, 0, 0, 4)
        detail.setSpacing(4)
        for regle in (
                tr("Une course se fait d'une traite : le jeu ne doit être ni fermé ni relancé avant l'arrivée."),
                tr("Elle part d'une nouvelle partie, jamais d'une sauvegarde. Mourir et recharger en route est "
                   "permis."),
                tr("Les cinématiques comptent dans le temps ; les passer est permis."),
                tr("60 images par seconde au plus ; ce qui touche au temps du jeu est remis le temps de la course,"
                   " puis vos réglages vous sont rendus."),
                tr("Le temps est refusé si le jeu dépasse 65 images par seconde en moyenne sur 10 secondes : un "
                   "compteur qui montre 61 un instant ne compte pas."),
                tr("Une ligne ACCIO reste en bas de l'image toute la course, avec le chrono sans chargements"
                   " et les images par seconde : elle doit se lire sur votre vidéo, entière. C'est la vidéo,"
                   " jugée par une personne, qui prouve la course.")):
            detail.addWidget(_gris("•  " + regle))
        self.regles_detaillees.hide()
        gauche.addWidget(self.regles_detaillees)

        fantome = Carte()
        self.bascule_fantome = ToggleSwitch(self.fantome)
        self.bascule_fantome.setAccessibleName(tr("Fantôme"))
        self.bascule_fantome.toggled.connect(self._basculer_fantome)
        self._ligne_fantome = LigneReglage(tr("Fantôme"), "", self.bascule_fantome)
        fantome.ajouter(self._ligne_fantome)
        gauche.addWidget(fantome)

        if self.game.id == "hp1":
            gauche.addWidget(_gris(tr(
                "HP1 : une course Accio ne compte pas sur le classement speedrun.com du jeu tant que ses "
                "modérateurs n'ont pas accepté la limite d'images d'Accio.")))
        if mode_course.plateforme() != "win32":
            gauche.addWidget(_gris(course_ui.raison(course.SOUS_WINE)))
        if self.ini is not None and (ecarts := mode_course.ecarts(self.game.id, self.ini)):
            note = _gris(trn(len(ecarts), "{} réglage sera remis le temps de la course, puis rendu.",
                             "{} réglages seront remis le temps de la course, puis rendus.").format(len(ecarts)))
            note.setToolTip("\n".join(f"{e.cle} : {e.valeur if e.valeur is not None else '—'} → {e.posee or '—'}"
                                      for e in ecarts))
            gauche.addWidget(note)
        gauche.addLayout(self._ce_qui_bloque())

        gauche.addSpacing(6)
        pied = QHBoxLayout()
        self._partir = bouton("", principal=True)
        self._partir.setEnabled(self.ini is not None and not self.bloquants)
        self._partir.clicked.connect(self._calculer)
        self._partir.setAutoDefault(False)
        pied.addWidget(self._partir)
        pied.addStretch()
        gauche.addLayout(pied)
        self._barre = QProgressBar()
        self._barre.setRange(0, 1000)
        self._barre.setTextVisible(False)
        self._barre.hide()
        gauche.addWidget(self._barre)
        self._etat = _gris("", 12)
        self._etat.hide()
        gauche.addWidget(self._etat)
        gauche.addStretch()
        return gauche

    def _ce_qui_bloque(self) -> QVBoxLayout:
        """Le correctif trop ancien, ou la difficulté : la phrase, et le geste qui le règle quand il existe."""
        bloc = QVBoxLayout()
        bloc.setSpacing(4)
        self._bloque = QWidget()
        transparent(self._bloque, "ceQuiBloque")
        lay = QVBoxLayout(self._bloque)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(4)
        if self.ini is None:
            minimum = ".".join(map(str, self.regles.correctif_min))
            lay.addWidget(texte(tr("Le correctif installé ne sait pas encore chronométrer ce jeu : la course "
                                   "demande le correctif {} ou plus récent.").format(minimum),
                                13, _ROUGE, retour=True))
            if self._actions.mettre_a_jour is not None and self._manager.has_update(self.game.id):
                geste = lien(tr("Mettre à jour le jeu"))
                geste.clicked.connect(self._actions.mettre_a_jour)
                lay.addWidget(geste, alignment=Qt.AlignmentFlag.AlignLeft)
        for phrase in self.bloquants:
            lay.addWidget(texte(phrase, 13, _ROUGE, retour=True))
            if self._actions.difficulte is not None:
                geste = lien(tr("Choisir la difficulté"))
                geste.clicked.connect(self._actions.difficulte)
                lay.addWidget(geste, alignment=Qt.AlignmentFlag.AlignLeft)
        self._bloque.setVisible(self.ini is None or bool(self.bloquants))
        bloc.addWidget(self._bloque)
        return bloc

    # ── La colonne de droite : record, idéale, essais, classement ──

    def _remplir_droite(self) -> None:
        while (item := self._droite.takeAt(0)) is not None:
            if (w := item.widget()) is not None:
                w.hide()
                w.deleteLater()
        lay = self._droite
        temps = self.regles.temps
        du_jeu = [c for c in self._courses if c.categorie == self.categorie]
        record = course.meilleure(du_jeu, self.categorie, temps)
        lay.addWidget(surtitre(tr("Votre record")))
        self.temps_record = QLabel(course.format_temps(record.temps(temps)) if record is not None else "—")
        self.temps_record.setObjectName("tempsRecord")
        self.temps_record.setFont(cinzel(24, bold=True))
        self.temps_record.setStyleSheet(themed(f"color: {_OR if record is not None else ENCRE_DOUCE};"
                                               " background: transparent;"))
        lay.addWidget(self.temps_record)
        if record is None:
            lay.addWidget(_gris(tr("Pas encore de temps valable dans cette catégorie.")))
        else:
            autre = (tr("{} sans chargements").format(course.format_temps(record.net_us)) if temps == course.REEL
                     else tr("{} en temps réel").format(course.format_temps(record.total_us)))
            lay.addWidget(_gris(f"{autre} · {record.jour}"))
            ideale = course.ideale(du_jeu, self.categorie, temps)
            if ideale is not None and ideale.a_gagner_us > 0:
                lay.addWidget(_gris(tr("Course idéale : {} sans chargements, encore {} à gagner.").format(
                    course.format_temps(ideale.net_us), course.format_temps(ideale.a_gagner_us))))
        if du_jeu:
            valables = sum(c.valable for c in du_jeu)
            lay.addWidget(_gris(trn(len(du_jeu), "{} essai", "{} essais").format(len(du_jeu)) + " · "
                                + trn(valables, "{} valable", "{} valables").format(valables)))
        lay.addSpacing(18)
        lay.addWidget(surtitre(tr("Classement Accio")))
        self.places = list(self._classement.de(self.game.id, self.categorie))
        if self.places:
            lay.addWidget(self._grille(self.places[:_CLASSES_MONTRES]))
        else:
            lay.addWidget(_gris(tr("Personne n'y est encore classé.")))
        self.note_place: QLabel | None = None
        if record is not None and record.code not in {e.code for e in self.places}:
            place = classement.rang(tuple(self.places), record.temps(temps))
            self.note_place = texte(tr("Votre record y prendrait la place {}.").format(place), 13, ENCRE,
                                    retour=True)
            lay.addWidget(self.note_place)
        if self._actions.carnet is not None and (self._courses or self._classement.categories(self.game.id)):
            carnet = lien(tr("Toutes vos courses et le classement complet"), discret=True)
            carnet.clicked.connect(self._actions.carnet)
            lay.addWidget(carnet, alignment=Qt.AlignmentFlag.AlignLeft)

    @staticmethod
    def _grille(entrees: list[classement.Entree]) -> QFrame:
        """Les premiers du classement : rang, joueur (texte BRUT : il vient du réseau), temps."""
        cadre = QFrame()
        cadre.setObjectName("carte")
        grille = QGridLayout(cadre)
        grille.setContentsMargins(16, 10, 16, 10)
        grille.setHorizontalSpacing(12)
        grille.setVerticalSpacing(4)
        grille.setColumnStretch(1, 1)
        droite = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        for i, e in enumerate(entrees):
            rang = QLabel(str(i + 1))
            rang.setFont(cinzel(11, bold=True))
            rang.setStyleSheet(themed(f"color: {_OR if i < 3 else ENCRE_DOUCE}; background: transparent;"))
            grille.addWidget(rang, i, 0, droite)
            grille.addWidget(texte(e.joueur, 13, ENCRE), i, 1)
            grille.addWidget(texte(course.format_temps(e.temps_us), 13, ENCRE), i, 2, droite)
        return cadre

    # ── Gestes ──

    def choisir(self, ident: str) -> None:
        if ident != self.categorie and self.regles.categorie(ident) is not None:
            self.categorie = ident
            self._montrer_categorie()

    def _montrer_categorie(self) -> None:
        c: Categorie | None = self.regles.categorie(self.categorie)
        if c is None:
            return
        if not self.pastilles[c.ident].isChecked():
            self.pastilles[c.ident].setChecked(True)
        self._regle.setText(c.regle)
        self._note.setText(c.note)
        self._note.setVisible(bool(c.note))
        self._partir.setText(tr("Partir en {}").format(c.nom))
        self._decrire_fantome()
        self._remplir_droite()

    def _deplier_regles(self, ouvert: bool) -> None:
        self.regles_detaillees.setVisible(ouvert)
        self.bouton_regles.setText(tr("Masquer les règles détaillées") if ouvert else tr("Règles détaillées"))

    def _basculer_fantome(self, coche: bool) -> None:
        self.fantome = coche
        self._decrire_fantome()

    def _decrire_fantome(self) -> None:
        nom = nom_categorie(self.regles, self.categorie)
        record = course.meilleure(self._courses, self.categorie, self.regles.temps)
        if not self.fantome:
            phrase = tr("Seuls le chrono et les images par seconde sont montrés.")
        elif record is None:
            phrase = tr("Pas encore de record valable en {} : l'écart viendra avec le premier.").format(nom)
        else:
            # Le correctif découpe le chrono SANS chargements : c'est ce temps du record qu'il compare, même pour
            # un jeu qui se classe au temps réel.
            phrase = tr("L'écart à votre record en {} ({} sans chargements) suit le chrono à chaque carte "
                        "quittée.").format(nom, course.format_temps(record.net_us))
        self._ligne_fantome.decrire(phrase)
        self.note_fantome = phrase

    def _figer(self, oui: bool) -> None:
        for b in (*self.pastilles.values(), self.bascule_fantome):
            b.setEnabled(not oui)
        self._partir.setEnabled(not oui and self.ini is not None and not self.bloquants)

    def _calculer(self) -> None:
        if self.ini is None or self.bloquants:
            return
        self._figer(True)
        self._barre.show()
        self._etat.setText(tr("Empreinte des fichiers du jeu…"))
        self._etat.show()
        jeu, exe = course_ui.dossiers(self.game, self._install_path)
        fil = course_ui.EmpreinteThread(self.game.id, jeu, exe)
        fil.progress.connect(self._barre.setValue)
        fil.error.connect(self._echec)
        fil.empreinte_prete.connect(self._prete)
        self._fil = fil
        fil.start()

    def _lacher_fil(self, sur_sa_fin: bool = False) -> None:
        fil, self._fil = self._fil, None
        if fil is not None:
            course_ui.lacher(fil, (fil.progress, self._barre.setValue), (fil.error, self._echec),
                             (fil.empreinte_prete, self._prete), sur_sa_fin=sur_sa_fin)

    def _prete(self, emp: course.Empreinte) -> None:
        self._lacher_fil(sur_sa_fin=True)
        self.empreinte = emp
        if self.ini is not None:
            self.choix = Choix(self.game.id, self.ini, self.categorie, emp, self.fantome)
        self.accept()

    def _echec(self, texte_: str) -> None:
        self._lacher_fil(sur_sa_fin=True)
        self._barre.hide()
        self._etat.setText(tr("L'empreinte n'a pas pu être calculée : {}").format(texte_))
        self._figer(False)

    def done(self, code: int) -> None:
        self._lacher_fil()
        super().done(code)
