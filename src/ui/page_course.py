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

Le dessin suit la maquette (pièces communes dans `course_visuel`) : le panneau sombre, les trois tuiles « Le chrono
part », « Il s'arrête », « Le temps qui compte », les alertes rouges avec leur geste, « Dans le jeu », le grand
bouton or ; à droite les tuiles « Votre record » et « Course idéale », puis le classement avec le joueur à la place
que prendrait son record (« Vous (non envoyé) ») et l'envoi par le Discord. L'affichage dans le jeu (Simple ou
Complet, coin de l'écran) n'y est PAS encore : le correctif ne sait pas le lire, et un réglage que la DLL
ignorerait mentirait (étape 5 du plan de la 1.5).
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
from src.core.liens import DISCORD_URL
from src.ui import course_ui
from src.ui import course_visuel as visuel
from src.ui.bandeau_jeu import bandeau_du_jeu
from src.ui.composants import (
    ENCRE,
    MARGES_PAGE,
    TAILLE_MINIMALE_PAGE,
    bouton_retour,
    colonne_centree,
    feuille_de_style,
    filtre,
    police,
    surtitre,
    transparent,
)
from src.ui.entree_focus import entree_suit_le_focus
from src.ui.theme import themed
from src.ui.toggle_switch import ToggleSwitch
from src.ui.utils import open_url, zone_defilable

_LARGEUR_DROITE = 400
_CLASSES_MONTRES = 6
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
    complet: bool = False
    coin: int = 4


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
        self.complet = config.course_complet
        self.coin = config.course_coin
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
        self.setStyleSheet(themed(_BARRE) + feuille_de_style() + visuel.STYLE)
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
            # La pastille porte le record de la catégorie (maquette) : on voit d'un coup d'œil où l'on en est.
            record = course.meilleure(self._courses, c.ident, self.regles.temps)
            b = filtre(c.nom if record is None else f"{c.nom}   {course.format_temps(record.temps(self.regles.temps))}",
                       grand=True)
            b.setFont(visuel.chiffres(b.font()))
            b.setChecked(c.ident == self.categorie)
            b.setToolTip(c.regle)
            b.setAccessibleName(c.nom)
            b.clicked.connect(lambda _c=False, ident=c.ident: self.choisir(ident))
            groupe.addButton(b)
            self.pastilles[c.ident] = b
            rangee.addWidget(b)
        rangee.addStretch()
        racine.addWidget(bandeau)

        corps = QWidget()
        transparent(corps, "corpsCourse")
        lay = QHBoxLayout(corps)
        lay.setContentsMargins(MARGES_PAGE[0], 20, MARGES_PAGE[2], 24)
        lay.setSpacing(24)
        lay.addWidget(self._panneau(), 1)
        droite = QWidget()
        transparent(droite, "droiteCourse")
        droite.setFixedWidth(_LARGEUR_DROITE)
        self._droite = QVBoxLayout(droite)
        self._droite.setContentsMargins(0, 0, 0, 0)
        self._droite.setSpacing(12)
        lay.addWidget(droite)
        colonne_centree(corps)
        racine.addWidget(zone_defilable(corps), 1)

    def _panneau(self) -> QFrame:
        """Le panneau de gauche : la catégorie, départ, arrivée et temps qui compte, les règles, ce qui bloque,
        ce qui s'affiche dans le jeu, et « Partir »."""
        panneau, gauche = visuel.cadre("panneauCourse", (24, 14, 24, 14), 8)
        tete = QHBoxLayout()
        tete.setSpacing(14)
        self._nom_categorie = visuel.grand_titre("", 26, visuel.OR_CLAIR)
        self._nom_categorie.setWordWrap(False)
        tete.addWidget(self._nom_categorie, alignment=Qt.AlignmentFlag.AlignBottom)
        self._regle = visuel.libelle("", 14, visuel.GRIS_CLAIR, retour=True)
        self._regle.setObjectName("regleCategorie")
        tete.addWidget(self._regle, 1, Qt.AlignmentFlag.AlignBottom)
        gauche.addLayout(tete)
        self._note = visuel.libelle("", 13, visuel.GRIS, retour=True)
        self._note.setObjectName("noteCategorie")
        gauche.addWidget(self._note)

        tuiles = QGridLayout()
        tuiles.setSpacing(10)
        for col, (titre, valeur) in enumerate(((tr("Le chrono part"), self.regles.depart),
                                               (tr("Il s'arrête"), self.regles.arrivee),
                                               (tr("Le temps qui compte"), phrase_du_temps(self.regles)))):
            tuiles.addWidget(visuel.tuile(titre, valeur)[0], 0, col)
            tuiles.setColumnStretch(col, 1)
        gauche.addLayout(tuiles)

        self.bouton_regles = visuel.lien_or(tr("Règles détaillées ›"))
        self.bouton_regles.setCheckable(True)
        self.bouton_regles.toggled.connect(self._deplier_regles)
        gauche.addWidget(self.bouton_regles, alignment=Qt.AlignmentFlag.AlignLeft)
        self.regles_detaillees = QFrame()
        transparent(self.regles_detaillees, "reglesDetaillees")
        detail = QVBoxLayout(self.regles_detaillees)
        detail.setContentsMargins(4, 0, 0, 0)
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
            detail.addWidget(visuel.libelle("•  " + regle, 13, visuel.GRIS_CLAIR, retour=True))
        self.regles_detaillees.hide()
        gauche.addWidget(self.regles_detaillees)

        gauche.addWidget(self._ce_qui_bloque())
        notes = []
        if self.game.id == "hp1":
            notes.append(visuel.libelle(tr(
                "HP1 : une course Accio ne compte pas sur le classement speedrun.com du jeu tant que ses "
                "modérateurs n'ont pas accepté la limite d'images d'Accio."), 13, visuel.GRIS, retour=True))
        if mode_course.plateforme() != "win32":
            notes.append(visuel.libelle(course_ui.raison(course.SOUS_WINE), 13, visuel.GRIS, retour=True))
        if self.ini is not None and (ecarts := mode_course.ecarts(self.game.id, self.ini)):
            note = visuel.libelle(trn(len(ecarts), "{} réglage sera remis le temps de la course, puis rendu.",
                                      "{} réglages seront remis le temps de la course, puis rendus.").format(
                len(ecarts)), 13, visuel.GRIS, retour=True)
            note.setToolTip("\n".join(f"{e.cle} : {e.valeur if e.valeur is not None else '—'} → {e.posee or '—'}"
                                      for e in ecarts))
            notes.append(note)
        for note in notes:
            gauche.addWidget(note)

        gauche.addWidget(visuel.filet())
        dans_le_jeu = QHBoxLayout()
        dans_le_jeu.setSpacing(18)
        jeu = QVBoxLayout()
        jeu.setSpacing(6)
        jeu.addWidget(surtitre(tr("Dans le jeu")))
        details = QHBoxLayout()
        details.setSpacing(8)
        self._groupe_details = QButtonGroup(self)
        self.details: dict[bool, QPushButton] = {}
        for complet, nom, texte_ in ((False, tr("Simple"), tr("une ligne : chrono, écart, images/s")),
                                     (True, tr("Complet"), tr("en plus, les cartes et leurs écarts"))):
            b = visuel.tuile_choix(nom, texte_)
            b.setChecked(complet == self.complet)
            b.toggled.connect(lambda oui, c=complet: oui and self._choisir_detail(c))
            self._groupe_details.addButton(b)
            self.details[complet] = b
            details.addWidget(b)
        details.addStretch()
        jeu.addLayout(details)
        fantome = QHBoxLayout()
        fantome.setSpacing(12)
        self.bascule_fantome = ToggleSwitch(self.fantome)
        self.bascule_fantome.setAccessibleName(tr("Fantôme"))
        self.bascule_fantome.toggled.connect(self._basculer_fantome)
        fantome.addWidget(self.bascule_fantome, alignment=Qt.AlignmentFlag.AlignTop)
        mots = QVBoxLayout()
        mots.setSpacing(2)
        mots.addWidget(visuel.libelle(tr("Fantôme"), 14, ENCRE))
        self._phrase_fantome = visuel.libelle("", 13, visuel.GRIS, retour=True)
        mots.addWidget(self._phrase_fantome)
        fantome.addLayout(mots, 1)
        jeu.addLayout(fantome)
        dans_le_jeu.addLayout(jeu, 1)
        coin = QVBoxLayout()
        coin.setSpacing(6)
        coin.addWidget(surtitre(tr("Coin de l'écran")))
        self.ecran = visuel.EcranCoins(self.coin, self.complet)
        self.ecran.coin_choisi.connect(self._choisir_coin)
        coin.addWidget(self.ecran)
        self._nom_coin = visuel.libelle(visuel.nom_coin(self.coin), 12, visuel.GRIS)
        coin.addWidget(self._nom_coin)
        coin.addStretch()
        dans_le_jeu.addLayout(coin)
        gauche.addLayout(dans_le_jeu)

        gauche.addStretch()
        pied = QHBoxLayout()
        pied.setSpacing(16)
        self._partir = visuel.bouton_partir()
        self._partir.setEnabled(self.ini is not None and not self.bloquants)
        self._partir.clicked.connect(self._calculer)
        pied.addWidget(self._partir)
        attente = QVBoxLayout()
        attente.setSpacing(4)
        self._barre = QProgressBar()
        self._barre.setRange(0, 1000)
        self._barre.setTextVisible(False)
        self._barre.hide()
        attente.addWidget(self._barre)
        self._etat = visuel.libelle("", 13, visuel.GRIS, retour=True)
        self._etat.hide()
        attente.addWidget(self._etat)
        pied.addLayout(attente, 1)
        gauche.addLayout(pied)
        return panneau

    def _ce_qui_bloque(self) -> QWidget:
        """Le correctif trop ancien, ou la difficulté : une alerte chacun, avec le geste qui le règle quand il
        existe."""
        self._bloque = QWidget()
        transparent(self._bloque, "ceQuiBloque")
        lay = QVBoxLayout(self._bloque)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        if self.ini is None:
            minimum = ".".join(map(str, self.regles.correctif_min))
            geste = None
            if self._actions.mettre_a_jour is not None and self._manager.has_update(self.game.id):
                geste = visuel.lien_or(tr("Mettre à jour le jeu"))
                geste.clicked.connect(self._actions.mettre_a_jour)
            lay.addWidget(visuel.alerte(tr("Le correctif installé ne sait pas encore chronométrer ce jeu : la "
                                           "course demande le correctif {} ou plus récent.").format(minimum),
                                        geste))
        for phrase in self.bloquants:
            geste = None
            if self._actions.difficulte is not None:
                geste = visuel.lien_or(tr("Choisir la difficulté"))
                geste.clicked.connect(self._actions.difficulte)
            lay.addWidget(visuel.alerte(phrase, geste))
        self._bloque.setVisible(self.ini is None or bool(self.bloquants))
        return self._bloque

    # ── La colonne de droite : record, idéale, essais, classement ──

    def _remplir_droite(self) -> None:
        while (item := self._droite.takeAt(0)) is not None:
            if (w := item.widget()) is not None:
                w.hide()
                w.deleteLater()
        contenu = QWidget()
        transparent(contenu)
        lay = QVBoxLayout(contenu)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        self._droite.addWidget(contenu)
        temps = self.regles.temps
        du_jeu = [c for c in self._courses if c.categorie == self.categorie]
        record = course.meilleure(du_jeu, self.categorie, temps)
        ideale = course.ideale(du_jeu, self.categorie, temps) if record is not None else None
        tuiles = QGridLayout()
        tuiles.setSpacing(8)
        carte_record, self.temps_record = visuel.tuile(
            tr("Votre record"), course.format_temps(record.temps(temps)) if record is not None else "—",
            valeur_temps=True, valeur_px=19, encre=visuel.OR_CLAIR if record is not None else visuel.GRIS,
            nom="tuileOr")
        self.temps_record.setObjectName("tempsRecord")
        if record is not None:
            carte_record.setToolTip(f"{self._autre_temps(record)} · {record.jour}")
        tuiles.addWidget(carte_record, 0, 0)
        carte_ideale, _v = visuel.tuile(tr("Course idéale"),
                                        course.format_temps(ideale.temps_us) if ideale is not None else "—",
                                        valeur_temps=True, valeur_px=19)
        carte_ideale.setToolTip(tr("Votre record, moins ce que vos meilleurs passages de chaque carte peuvent encore "
                                   "y gagner."))
        tuiles.addWidget(carte_ideale, 0, 1)
        lay.addLayout(tuiles)
        sous_titre = []
        if record is not None:
            sous_titre.append(f"{self._autre_temps(record)} · {record.jour}")
        if du_jeu:
            valables = sum(c.valable for c in du_jeu)
            sous_titre.append(trn(len(du_jeu), "{} essai", "{} essais").format(len(du_jeu)) + " · "
                              + trn(valables, "{} valable", "{} valables").format(valables))
        else:
            sous_titre.append(tr("Aucune course lancée dans cette catégorie."))
        lay.addWidget(visuel.libelle("\n".join(sous_titre), 12, visuel.GRIS, retour=True))
        lay.addWidget(self._tableau(record), 1)

    def _autre_temps(self, record: course.Passee) -> str:
        if self.regles.temps == course.REEL:
            return tr("{} sans chargements").format(course.format_temps(record.net_us))
        return tr("{} en temps réel").format(course.format_temps(record.total_us))

    def _tableau(self, record: course.Passee | None) -> QFrame:
        """Le classement Accio de la catégorie : les premiers, et le joueur à la place que prendrait son record
        s'il n'y est pas encore ; l'envoi passe par le Discord."""
        temps = self.regles.temps
        panneau, lay = visuel.cadre("panneauCourse", (14, 12, 14, 12), 6)
        tete = QHBoxLayout()
        tete.addWidget(surtitre(tr("Classement Accio") + " · " + nom_categorie(self.regles, self.categorie)), 1)
        if self._actions.carnet is not None and (self._courses or self._classement.categories(self.game.id)):
            tout = visuel.lien_or(tr("Tout voir ›"))
            tout.setFont(police(12))
            tout.setToolTip(tr("Toutes vos courses et le classement complet, dans le Carnet."))
            tout.clicked.connect(self._actions.carnet)
            tete.addWidget(tout)
        lay.addLayout(tete)
        self.places = list(self._classement.de(self.game.id, self.categorie))
        self.place_record: int | None = None
        if record is not None and record.code not in {e.code for e in self.places}:
            self.place_record = classement.rang(tuple(self.places), record.temps(temps))
        lignes: list[tuple[int, str, int, bool]] = [(i + 1, e.joueur, e.temps_us, False)
                                                    for i, e in enumerate(self.places)]
        if self.place_record is not None and record is not None:
            lignes.insert(self.place_record - 1, (self.place_record, tr("Vous (non envoyé)"),
                                                  record.temps(temps), True))
            lignes = [(i + 1, j, t, v) for i, (_r, j, t, v) in enumerate(lignes)]
        if not self.places:
            lay.addStretch()
            vide = visuel.libelle(tr("Personne n'est encore classé en {}.").format(
                nom_categorie(self.regles, self.categorie)), 15, visuel.CREME, retour=True)
            vide.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(vide)
            suite = visuel.libelle(tr("La première course valable envoyée prend la place 1."), 13, visuel.GRIS,
                                   retour=True)
            suite.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(suite)
            lay.addStretch()
        else:
            montrees = lignes[:_CLASSES_MONTRES]
            vous = next((ligne for ligne in lignes if ligne[3]), None)
            if vous is not None and vous not in montrees:
                montrees[-1] = vous
            for rang, joueur, us, est_vous in montrees:
                lay.addWidget(visuel.ligne_classee(rang, joueur, course.format_temps(us), vous=est_vous))
            lay.addStretch()
        if self.place_record is not None:
            envoyer = visuel.bouton_nomme(tr("Envoyer mon record sur le Discord"), "boutonCadreOr")
            envoyer.setToolTip(tr("Publiez la vidéo de la course et son course.json sur le Discord : une fois "
                                  "validée, elle entre au classement."))
            envoyer.clicked.connect(lambda: open_url(DISCORD_URL))
            lay.addWidget(envoyer)
        return panneau

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
        self._nom_categorie.setText(c.nom)
        self._regle.setText(c.regle)
        self._note.setText(c.note)
        self._note.setVisible(bool(c.note))
        self._partir.setText(tr("Partir en {}").format(c.nom))
        self._decrire_fantome()
        self._remplir_droite()

    def _deplier_regles(self, ouvert: bool) -> None:
        self.regles_detaillees.setVisible(ouvert)
        self.bouton_regles.setText(tr("Masquer les règles détaillées") if ouvert else tr("Règles détaillées ›"))

    def _choisir_detail(self, complet: bool) -> None:
        self.complet = complet
        self.ecran.montrer_detail(complet)

    def _choisir_coin(self, coin: int) -> None:
        self.coin = coin
        self._nom_coin.setText(visuel.nom_coin(coin))

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
        self._phrase_fantome.setText(phrase)
        self.note_fantome = phrase

    def _figer(self, oui: bool) -> None:
        for b in (*self.pastilles.values(), *self.details.values(), self.bascule_fantome, self.ecran):
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
            self.choix = Choix(self.game.id, self.ini, self.categorie, emp, self.fantome, self.complet, self.coin)
        self.accept()

    def _echec(self, texte_: str) -> None:
        self._lacher_fil(sur_sa_fin=True)
        self._barre.hide()
        self._etat.setText(tr("L'empreinte n'a pas pu être calculée : {}").format(texte_))
        self._figer(False)

    def done(self, code: int) -> None:
        self._lacher_fil()
        super().done(code)
