"""La course (1.5) dans l'interface : le départ orchestré, le fil de l'empreinte, le résultat.

Le chrono, le temps et le verdict sont dans `core/course` ; les réglages tenus et rendus dans
`core/mode_course` ; les règles de chaque jeu (catégories, temps qui classe) dans le catalogue
(`core/course_regles`). La page de départ est `page_course.CoursePage`. Ici : `partir` (le chrono de la fiche
ouvre la page), `lancer` (la page a dit oui : réglages tenus, clés de la course, lancement, comme
`game_detail_handlers.on_play` qu'il appelle), et la fenêtre du résultat. Une course part d'une NOUVELLE
partie (S7.1) ; le temps qui classe est celui que speedrun.com classe pour ce jeu (réel pour HP4 à HP6, sans
chargements pour HP1 à HP3), l'autre est gardé aussi ; la phrase sur la vidéo est dite telle que Ludo l'a
tranchée (S7.7) : la signature n'arrête qu'une retouche à la main du fichier.
"""

import json
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QThread, QTimer, Qt, pyqtBoundSignal, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.core import classement, course, mode_course
from src.core import difficulte_presets as dp
from src.core.config import APP_VERSION, Config
from src.core.game_data import GameData
from src.core.i18n import tr, trn
from src.core.liens import DISCORD_URL
from src.core.thread_utils import liberer_apres_fin
from src.ui import course_visuel as visuel
from src.ui import filtres_globaux
from src.ui.composants import feuille_de_style, police, surtitre, transparent
from src.ui.entree_focus import entree_suit_le_focus
from src.ui.fenetre_message import message
from src.ui.icon_button import pixmap_icone
from src.ui.theme import themed
from src.ui.utils import BARRE_DEFILEMENT, open_local_path, open_url

if TYPE_CHECKING:
    from src.ui.game_detail import GameDetailView
    from src.ui.main_window import MainWindow
    from src.ui.page_course import Choix

log = logging.getLogger(__name__)

_FENETRE = "QDialog { background: #0d0d1a; border: 1px solid rgba(214,167,44,0.3); }"
# Un fil d'empreinte annulé qui ne répond pas dans le délai : gardé ici jusqu'à sa fin (jamais détruit en
# marche), comme `GameOperations._zombies`.
_ZOMBIES: list[EmpreinteThread] = []
_VERROU = threading.Lock()


def raison(code: str) -> str:
    """La phrase d'un refus de temps (`course.verdict`) ou de départ (`mode_course.CourseRefusee`)."""
    phrases = {
        course.SANS_SEANCE: tr("Le correctif n'a pas ouvert le journal de la course : rien n'a été chronométré."),
        course.RELANCE: tr("Le jeu a été relancé pendant la course."),
        course.AUTRE_ID: tr("L'identifiant du journal n'est pas celui tiré au départ."),
        course.SANS_DEPART: tr("Le départ n'a pas été vu : aucune nouvelle partie n'a commencé."),
        course.DEPART_CHARGE: tr("La course est partie d'une partie chargée, pas d'une nouvelle partie."),
        course.DEPART_CLIC: tr("Le clic de la nouvelle partie n'a pas été vu : le temps part trop tard."),
        course.DEPART_INCONNU: tr("Rien ne dit que la partie était neuve."),
        course.SANS_FIN: tr("La fin de la course n'a pas été vue : partie quittée avant l'arrivée."),
        course.RETOUCHE: tr("Le temps écrit ne correspond pas aux chargements du journal."),
        course.TROP_D_IMAGES: tr("Le jeu a dépassé 65 images par seconde en moyenne sur 10 secondes."),
        course.MODE_NON_TENU: tr("Un réglage qui touche au temps du jeu a changé pendant la course."),
        course.INTERDITS: tr("Le correctif a vu un réglage interdit en course."),
        course.SOUS_WINE: tr("Sous Linux, la ligne ACCIO ne s'affiche pas encore à l'écran : le temps n'est pas classé."),
        "sauvegardes": tr("Le dossier des sauvegardes de la course ne s'écrit pas à un endroit que le jeu sait lire."),
        "ini": tr("Les réglages de la course n'ont pas pu être écrits dans le dossier du jeu."),
        "journal_tenu": tr("Le journal d'une course passée est encore ouvert : fermez le jeu."),
    }
    return phrases.get(code, code)


class EmpreinteThread(QThread):
    """L'empreinte des fichiers du jeu (gigaoctets pour HP4 à HP6), hors du fil de l'interface."""

    progress = pyqtSignal(int)                 # pour mille
    error = pyqtSignal(str)
    empreinte_prete = pyqtSignal(object)       # course.Empreinte

    def __init__(self, game_id: str, dossier_jeu: Path, dossier_exe: Path) -> None:
        super().__init__()
        self._jeu, self._dossier_jeu, self._dossier_exe = game_id, dossier_jeu, dossier_exe
        self._annule = threading.Event()

    def cancel(self) -> None:
        self._annule.set()

    def run(self) -> None:
        cache_chemin = course.racine() / "empreintes.json"
        try:
            with _VERROU:
                cache = course.lire_cache(cache_chemin)
                emp = course.empreinte(self._jeu, self._dossier_jeu, self._dossier_exe, cache,
                                       lambda fait, total: self.progress.emit(fait * 1000 // max(1, total)),
                                       self._annule.is_set)
                if emp is not None:
                    cache_chemin.parent.mkdir(parents=True, exist_ok=True)
                    from src.core.ecriture_atomique import ecrire_atomique
                    ecrire_atomique(cache_chemin, json.dumps(cache))
        except OSError as exc:
            log.warning("Course : empreinte de %s impossible", self._jeu, exc_info=True)
            self.error.emit(str(exc))
            return
        if emp is None:
            if not self._annule.is_set():
                self.error.emit(tr("Aucun fichier du jeu à empreinter."))
            return
        self.empreinte_prete.emit(emp)


def lacher(fil: EmpreinteThread, *branchements: tuple[pyqtBoundSignal, object], sur_sa_fin: bool) -> None:
    """Déconnecte le fil, puis : depuis un de ses signaux de fin, `liberer_apres_fin` (règle 133) ; sinon (page
    fermée en route), l'annuler, l'attendre 3 s, et le garer s'il ne répond pas."""
    for signal, slot in branchements:
        try:
            signal.disconnect(slot)
        except TypeError:
            pass
    if sur_sa_fin:
        liberer_apres_fin(fil)
    elif fil.isRunning():
        fil.cancel()
        if not fil.wait(3000):
            _ZOMBIES.append(fil)
            fil.finished.connect(lambda: _ZOMBIES.remove(fil) if fil in _ZOMBIES else None)


def dossiers(game: GameData, install_path: Path) -> tuple[Path, Path]:
    """(dossier du jeu, dossier de l'exe)."""
    exe = Path(game.executable)
    return Path(install_path) / exe.parts[0], (Path(install_path) / exe).parent


def bloquants(game: GameData, config: Config) -> list[str]:
    """Ce qui empêche le départ, en phrases : la difficulté doit être Normal (la une seule vie coupée)."""
    sortie = []
    if dp.au_lancement(game, config) != "normal":
        sortie.append(tr("Choisissez la difficulté Normal (une seule vie coupée) : la course se court sur le jeu "
                         "d'origine."))
    return sortie


# ── Le départ ──

def partir(view: GameDetailView) -> None:
    """Le chrono de la fiche : la page Course, à la place de la bibliothèque. Elle ne lance rien elle-même :
    fermée avec un `Choix`, `lancer` prend la suite."""
    from src.ui import game_detail_handlers as handlers
    from src.ui.page_course import Actions, CoursePage
    game = view.game
    if game is None or not mode_course.propose(game):
        return
    if view.partie_en_cours():
        view.notify.emit(tr("{} est en train de démarrer ou déjà lancé.").format(view.partie_en_cours()))
        return
    en_page = bool(view.receivers(view.page_demandee))

    def carnet() -> None:
        from src.ui.carnet_page import COURSES, CarnetPage
        view.page_demandee.emit(filtres_globaux.batie(
            lambda: CarnetPage(view.manager, view.window(), rubrique=COURSES, jeu=game.id)))

    actions = Actions(difficulte=lambda: handlers.on_game_settings(view, onglet="difficulte"),
                      mettre_a_jour=lambda: handlers.on_update_clicked(view),
                      carnet=carnet) if en_page else Actions()
    page = filtres_globaux.batie(lambda: CoursePage(game, view.manager, actions=actions, parent=view))
    page.accepted.connect(lambda: page.choix is not None and lancer(view, page.choix))
    if en_page:
        view.page_demandee.emit(page)
    else:
        page.exec()


def lancer(view: GameDetailView, choix: Choix) -> None:
    """La page a dit oui : réglages tenus et clés de la course, fantôme, puis le jeu. Si le jeu ne part pas,
    les réglages sont rendus aussitôt."""
    from src.ui import game_detail_handlers as handlers
    game, config = view.game, view.manager.config
    if game is None or game.id != choix.jeu or game.course is None or view.partie_en_cours():
        return
    if (choix.fantome, choix.complet, choix.coin) != (config.course_fantome, config.course_complet,
                                                      config.course_coin):
        config.course_fantome, config.course_complet, config.course_coin = choix.fantome, choix.complet, choix.coin
        config.save()
    passees = course.passees(game.id)
    fantome = course.fantome(passees, choix.categorie, game.course.temps) if choix.fantome else None
    record = course.meilleure(passees, choix.categorie, game.course.temps)
    affichage = mode_course.Affichage(choix.complet, choix.coin,
                                      record.temps(game.course.temps) if record is not None else None)
    native = ""
    if game.difficulte is not None:
        from src.core import difficulte_jeu
        rang = difficulte_jeu.lire(game, config)
        native = f";native={rang}" if rang is not None else ""
    try:
        etat = mode_course.entrer(game, choix.ini, choix.categorie, choix.empreinte, "normal" + native,
                                  fantome=fantome, affichage=affichage)
    except (mode_course.CourseRefusee, OSError, ValueError) as exc:
        code = str(exc.args[0]) if isinstance(exc, mode_course.CourseRefusee) and exc.args else "ini"
        message(view, QMessageBox.Icon.Warning, tr("Course"), raison(code))
        return
    handlers.on_play(view)
    if not view.partie_en_cours():
        mode_course.sortir(etat)


# ── Le résultat ──

def _deux_temps(game: GameData | None, r: course.Resultat) -> tuple[int, str, str]:
    """(le temps qui classe, son nom, l'autre dit en clair)."""
    if game is not None and game.course is not None and game.course.temps == course.REEL:
        return r.reel, tr("temps réel"), tr("{} sans chargements").format(course.format_temps(r.net))
    return r.net, tr("sans les chargements"), tr("{} en temps réel").format(course.format_temps(r.reel))


def resume(conclusion: mode_course.Conclusion, nom: str, game: GameData | None = None) -> str:
    """Le résumé à coller avec la vidéo : jeu, catégorie, les deux temps, ligne d'identifiant, versions."""
    r = conclusion.resultat
    lignes = [f"{nom} — {conclusion.categorie}",
              tr("Temps réel : {}").format(course.format_temps(r.reel)),
              tr("Temps sans chargements : {}").format(course.format_temps(r.net)),
              conclusion.ligne_id,
              tr("Launcher {} · correctif {}").format(APP_VERSION, r.version_fix or "?")]
    if game is not None and game.course is not None:
        lignes.insert(1, tr("Temps qui classe : {}").format(
            tr("réel") if game.course.temps == course.REEL else tr("sans chargements")))
    lignes += [raison(code) for code in conclusion.refus]
    return "\n".join(lignes)


class CourseResultat(QDialog):
    """Le temps d'une course qui vient de finir (maquette « Résultat » du canevas de la 1.5) : à gauche le temps qui
    classe en grand et l'autre, le record d'avant battu ou non, le code, l'empreinte et les versions, la place au
    classement Accio ; à droite le découpage par carte (passage, cumul, écart au record, ce qui reste à gagner,
    les meilleurs passages en or), la course idéale, et le Carnet."""

    def __init__(self, conclusion: mode_course.Conclusion, nom: str, parent: QWidget | None = None, *,
                 game: GameData | None = None, courses: list[course.Passee] | None = None,
                 classement_: classement.Classement | None = None,
                 carnet: Callable[[], None] | None = None) -> None:
        super().__init__(parent)
        entree_suit_le_focus(self)
        self._conclusion, self._nom, self._game = conclusion, nom, game
        r = conclusion.resultat
        regles = game.course if game is not None else None
        quel = regles.temps if regles is not None else course.SANS_CHARGEMENTS
        cat = regles.categorie(conclusion.categorie) if regles is not None else None
        nom_cat = cat.nom if cat is not None else conclusion.categorie
        du_jeu = [c for c in (courses if courses is not None else course.passees(conclusion.jeu))
                  if c.categorie == conclusion.categorie]
        self._valable = r.fin and not conclusion.refus
        self.phrase_record: QLabel | None = None
        self.meilleurs: list[int] = []
        self.setWindowTitle(tr("Course : {}").format(nom))
        self.setMinimumSize(980, 600)
        self.setStyleSheet(themed(_FENETRE) + feuille_de_style() + visuel.STYLE)
        racine = QHBoxLayout(self)
        racine.setContentsMargins(32, 28, 32, 24)
        racine.setSpacing(32)
        gauche = QVBoxLayout()
        gauche.setSpacing(14)
        droite = QVBoxLayout()
        droite.setSpacing(10)
        racine.addLayout(gauche, 100)
        racine.addLayout(droite, 115)

        tete = (tr("Course terminée") if r.fin else tr("Course non terminée")) + " · " + nom_cat
        gauche.addWidget(surtitre(tete))
        gauche.addWidget(visuel.grand_titre(nom, 22))
        principal, nom_principal, autre = _deux_temps(game, r)
        temps = visuel.temps(course.format_temps(principal), 48, visuel.OR_CLAIR if self._valable else visuel.CREME)
        temps.setObjectName("tempsCourse")
        bloc_temps = QVBoxLayout()
        bloc_temps.setSpacing(4)
        bloc_temps.addWidget(temps)
        bloc_temps.addWidget(visuel.libelle(tr("{}, la règle de speedrun.com pour ce jeu").format(nom_principal)
                                            if regles is not None else nom_principal, 14, "#b9b9d0", retour=True))
        ordre = sorted(du_jeu, key=lambda c: (c.jour, c.ecrite_ns))
        rang_essai = next((i + 1 for i, c in enumerate(ordre) if c.code == conclusion.code), len(ordre) + 1)
        infos = [autre, trn(r.chargements, "{} chargement", "{} chargements").format(r.chargements)]
        if r.rechargements:
            infos.append(trn(r.rechargements, "{} partie rechargée", "{} parties rechargées").format(r.rechargements))
        if r.fps_moyen is not None:
            infos.append(tr("{} images/s en moyenne").format(f"{r.fps_moyen:.0f}"))
        infos.append(tr("essai {}").format(rang_essai))
        bloc_temps.addWidget(visuel.libelle(" · ".join(infos), 14, "#b9b9d0", retour=True))
        gauche.addLayout(bloc_temps)

        for code in conclusion.refus:
            gauche.addWidget(visuel.alerte(raison(code)))
        if r.interdits:
            gauche.addWidget(visuel.alerte(tr("Interdits en course : {}").format(", ".join(r.interdits))))
        if not conclusion.rendu:
            gauche.addWidget(visuel.alerte(tr(
                "Vos réglages n'ont pas pu être rendus : le launcher réessaiera à son prochain démarrage.")))
        if self._valable:
            self._record(gauche, du_jeu, principal, quel)
        gauche.addLayout(self._fiche(r))
        if self._valable:
            gauche.addWidget(self._place(principal, classement_))
        gauche.addStretch()
        gestes = QHBoxLayout()
        gestes.setSpacing(10)
        dossier = visuel.bouton_nomme(tr("Ouvrir le dossier de la course"), "boutonCadre")
        dossier.clicked.connect(lambda: open_local_path(str(course.dossier(conclusion.code))))
        copier = visuel.bouton_nomme(tr("Copier le résumé"), "boutonCadre")
        copier.setToolTip(tr("Jeu, catégorie, les deux temps, la ligne ACCIO et les versions : à coller avec la "
                             "vidéo."))
        copier.clicked.connect(self._copier)
        gestes.addWidget(dossier)
        gestes.addWidget(copier)
        gestes.addStretch()
        gauche.addLayout(gestes)

        droite.addWidget(surtitre(tr("Par carte")))
        if r.segments:
            avant = course.passages_d_avant(du_jeu, conclusion.code, conclusion.categorie, r.segments)
            record = course.meilleure([c for c in du_jeu if c.code != conclusion.code], None, quel)
            droite.addWidget(self._segments(r.segments, avant, record), 1)
            ideale = course.ideale(du_jeu, conclusion.categorie, quel)
            if ideale is not None:
                somme = QGridLayout()
                somme.setHorizontalSpacing(12)
                somme.setVerticalSpacing(4)
                somme.setColumnStretch(0, 1)
                droite_ = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                somme.addWidget(visuel.libelle(tr("Course idéale (vos meilleurs passages bout à bout)"), 13,
                                               "#b9b9d0"), 0, 0)
                somme.addWidget(visuel.temps(course.format_temps(ideale.temps_us), 13), 0, 1, droite_)
                somme.addWidget(visuel.libelle(tr("Encore à gagner sur votre record"), 13, "#b9b9d0"), 1, 0)
                somme.addWidget(visuel.temps(course.format_temps(ideale.a_gagner_us), 13), 1, 1, droite_)
                droite.addLayout(somme)
            droite.addWidget(visuel.libelle(tr(
                "Passages sans les chargements, pour comparer d'un PC à l'autre. Écart : à votre record au moment "
                "de quitter chaque carte ; vert en avance. Or : nouveau meilleur passage à cette place."), 12,
                visuel.GRIS, retour=True))
        else:
            droite.addWidget(visuel.libelle(tr("Le journal ne découpe pas cette course par carte."), 13,
                                            visuel.GRIS, retour=True))
            droite.addStretch()
        droite.addWidget(visuel.libelle(tr(
            "Le journal signé est dans le dossier de la course. Le launcher est libre : sa signature n'arrête "
            "qu'une retouche à la main du fichier. La vidéo reste la preuve."), 12, visuel.GRIS, retour=True))
        pied = QHBoxLayout()
        pied.addStretch()
        if carnet is not None:
            voir = visuel.bouton_nomme(tr("Voir dans le Carnet"), "boutonOr", 15, cinzel_gras=True)
            voir.clicked.connect(lambda: (self.accept(), carnet()))
            pied.addWidget(voir)
        fermer = visuel.bouton_nomme(tr("Fermer"), "boutonCadre" if carnet is not None else "boutonOr",
                                     15 if carnet is None else 14, cinzel_gras=carnet is None)
        fermer.clicked.connect(self.accept)
        pied.addWidget(fermer)
        droite.addLayout(pied)

    def _record(self, lay: QVBoxLayout, du_jeu: list[course.Passee], principal: int, quel: str) -> None:
        """Le record d'avant battu ou non : en vert s'il tombe (ou si c'est le premier temps valable)."""
        avant = course.meilleure([c for c in du_jeu if c.code != self._conclusion.code], None, quel)
        bon = avant is None or principal < avant.temps(quel)
        if avant is None:
            phrase = tr("Premier temps valable dans cette catégorie.")
        elif principal < avant.temps(quel):
            phrase = tr("Nouveau record : {} de mieux que le précédent.").format(
                course.format_temps(avant.temps(quel) - principal))
        else:
            phrase = tr("Votre record reste {} ({} de plus cette fois).").format(
                course.format_temps(avant.temps(quel)), course.format_temps(principal - avant.temps(quel)))
        cadre, h = visuel.cadre("bonneNouvelle" if bon else "tuileCourse", (12, 10, 12, 10), 10, horizontal=True)
        if bon:
            coche = QLabel()
            transparent(coche)
            coche.setPixmap(pixmap_icone("coche", 18, QColor(visuel.VERT)))
            h.addWidget(coche, alignment=Qt.AlignmentFlag.AlignTop)
        self.phrase_record = visuel.libelle(phrase + " " + tr("Temps valable, à prouver par la vidéo."), 14,
                                            "#c8f0da" if bon else visuel.CREME, retour=True)
        h.addWidget(self.phrase_record, 1)
        lay.addWidget(cadre)

    def _fiche(self, r: course.Resultat) -> QGridLayout:
        """Code, empreinte et versions : ce que la ligne ACCIO montre sur la vidéo."""
        grille = QGridLayout()
        grille.setHorizontalSpacing(14)
        grille.setVerticalSpacing(6)
        grille.setColumnStretch(1, 1)
        morceaux = self._conclusion.ligne_id.split()
        lignes = [(tr("Code"), self._conclusion.code)]
        if len(morceaux) >= 4:
            lignes.append((tr("Empreinte"), morceaux[3]))
        lignes.append((tr("Versions"), tr("Launcher {} · correctif {}").format(APP_VERSION, r.version_fix or "?")))
        for i, (titre, valeur) in enumerate(lignes):
            grille.addWidget(visuel.libelle(titre, 13, visuel.GRIS), i, 0)
            grille.addWidget(visuel.temps(valeur, 13), i, 1)
        return grille

    def _place(self, principal: int, classement_: classement.Classement | None) -> QFrame:
        """La place que ce temps prendrait au classement Accio, l'écart à la place d'au-dessus, et l'envoi."""
        tableau = (classement_ or classement.en_cache()).de(self._conclusion.jeu, self._conclusion.categorie)
        place = classement.rang(tableau, principal)
        cadre, h = visuel.cadre("placeCourse", (14, 12, 14, 12), 12, horizontal=True)
        rond = QLabel(str(place))
        rond.setFixedSize(30, 30)
        rond.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rond.setFont(police(13, gras=True))
        rond.setStyleSheet(f"background: {visuel.OR}; color: #14110a; border-radius: 15px;")
        h.addWidget(rond)
        mots = QVBoxLayout()
        mots.setSpacing(2)
        mots.addWidget(visuel.libelle(tr("Ce temps prendrait la place {} du classement Accio.").format(place), 14,
                                      visuel.CREME, retour=True))
        suite = tr("Envoyez la vidéo et le course.json sur le Discord : la course est vérifiée par une personne.")
        if place > 1:
            dessus = tableau[place - 2].temps_us
            suite = tr("À {} de la place {}.").format(course.format_temps(principal - dessus), place - 1) + " " + suite
        mots.addWidget(visuel.libelle(suite, 12, "#b9b9d0", retour=True))
        h.addLayout(mots, 1)
        envoyer = visuel.bouton_nomme(tr("Ouvrir le Discord"), "boutonOr", 13)
        envoyer.clicked.connect(lambda: open_url(DISCORD_URL))
        h.addWidget(envoyer, alignment=Qt.AlignmentFlag.AlignVCenter)
        return cadre

    def _segments(self, segments: tuple[course.Segment, ...], avant: tuple[int | None, ...],
                  record: course.Passee | None) -> QScrollArea:
        """Une ligne par carte : son nom (celui du jeu), le passage, le cumul, l'écart au record au même point
        (si le record a suivi le même parcours jusque-là), et ce que cette carte peut encore gagner sur le
        meilleur passage d'avant à cette place ; la médaille en or, un nouveau meilleur passage."""
        contenu = QWidget()
        transparent(contenu)
        grille = QGridLayout(contenu)
        grille.setContentsMargins(0, 0, 6, 0)
        grille.setHorizontalSpacing(12)
        grille.setVerticalSpacing(8)
        grille.setColumnStretch(0, 1)
        droite = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        for col, titre in enumerate((tr("Carte"), tr("Passage"), tr("Cumul"), tr("Écart"), tr("À gagner"))):
            entete = visuel.libelle(titre, 13, visuel.GRIS)
            entete.setContentsMargins(0, 0, 0, 6)
            grille.addWidget(entete, 0, col, droite if col else Qt.AlignmentFlag.AlignLeft)
        de_record = record.segments if record is not None else ()
        cumul = cumul_record = 0
        meme_parcours = True
        for i, (s, meilleur) in enumerate(zip(segments, avant, strict=True)):
            ligne = i + 1
            nom = tr("{} (rechargée)").format(s.carte) if s.depuis_sauvegarde else s.carte or tr("(sans nom)")
            dore = meilleur is not None and s.net_us <= meilleur
            if dore:
                self.meilleurs.append(i)
            cumul += s.net_us
            grille.addWidget(visuel.libelle(nom, 13, visuel.OR_CLAIR if dore else "#e0e0f0"), ligne, 0)
            grille.addWidget(visuel.temps(course.format_temps(s.net_us), 13, "#d4d4e4"), ligne, 1, droite)
            grille.addWidget(visuel.temps(course.format_temps(cumul), 13, visuel.GRIS), ligne, 2, droite)
            meme_parcours = meme_parcours and i < len(de_record) and de_record[i].carte == s.carte
            if meme_parcours:
                cumul_record += de_record[i].net_us
                ecart = cumul - cumul_record
                grille.addWidget(visuel.temps(course.format_ecart(ecart), 13,
                                              visuel.VERT if ecart < 0 else visuel.ROUGE if ecart > 0
                                              else visuel.GRIS), ligne, 3, droite)
            if dore:
                medaille = QLabel()
                transparent(medaille)
                medaille.setPixmap(pixmap_icone("medaille", 14, QColor(visuel.OR_CLAIR)))
                medaille.setToolTip(tr("Nouveau meilleur passage à cette place."))
                grille.addWidget(medaille, ligne, 4, droite)
            elif meilleur is not None:
                grille.addWidget(visuel.temps(course.format_temps(s.net_us - meilleur), 13, visuel.GRIS),
                                 ligne, 4, droite)
        grille.setRowStretch(len(segments) + 1, 1)
        zone = QScrollArea()
        zone.setWidgetResizable(True)
        zone.setWidget(contenu)
        zone.setStyleSheet("QScrollArea { background: transparent; border: none; }" + BARRE_DEFILEMENT)
        return zone

    def _copier(self) -> None:
        QGuiApplication.clipboard().setText(resume(self._conclusion, self._nom, self._game))


def montrer(window: MainWindow, conclusion: mode_course.Conclusion) -> None:
    """Fenêtre modale mais SANS boucle à elle : appelée depuis un minuteur, un `exec` bloquerait tout ce qui
    suit dans la boucle d'évènements. « Voir dans le Carnet » ouvre les Courses du jeu à la place de la
    bibliothèque."""
    from src.ui.carnet_page import COURSES, CarnetPage
    game = window.manager.get_game_by_id(conclusion.jeu)

    def carnet() -> None:
        window._pages.batir(lambda: CarnetPage(window.manager, window, COURSES, jeu=conclusion.jeu))

    dlg = CourseResultat(conclusion, game.name if game is not None else conclusion.jeu, window, game=game,
                         carnet=carnet)
    dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dlg.setWindowModality(Qt.WindowModality.WindowModal)
    dlg.show()


def brancher(window: MainWindow) -> None:
    """Le résultat au retour de la partie ; au démarrage, celui d'une course interrompue (launcher tué)."""
    window._session.course_terminee.connect(lambda c: QTimer.singleShot(0, lambda: montrer(window, c)))

    def interrompues() -> None:
        for c in window._session.courses_interrompues():
            montrer(window, c)
    QTimer.singleShot(0, interrompues)
