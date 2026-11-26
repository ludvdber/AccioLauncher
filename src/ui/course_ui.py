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
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QThread, QTimer, Qt, pyqtBoundSignal, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QDialog,
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
from src.ui import filtres_globaux
from src.ui.composants import bouton, feuille_de_style, lien, transparent
from src.ui.entree_focus import entree_suit_le_focus
from src.ui.fenetre_message import message
from src.ui.fonts import body_font, cinzel
from src.ui.theme import themed
from src.ui.utils import BARRE_DEFILEMENT, open_local_path, open_url

if TYPE_CHECKING:
    from src.ui.game_detail import GameDetailView
    from src.ui.main_window import MainWindow
    from src.ui.page_course import Choix

log = logging.getLogger(__name__)

_FENETRE = "QDialog { background: #0d0d1a; border: 1px solid rgba(214,167,44,0.3); }"
_GRIS = "color: #8a8aaa; background: transparent;"
_TEXTE = "color: #e0e0f0; background: transparent;"
_OR = "color: #d6a72c; background: transparent;"
_ROUGE = "color: #e07a6a; background: transparent;"
_VERT = "color: #7be0a4; background: transparent;"
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


def _libelle(texte: str, style: str = _TEXTE, taille: int = 12) -> QLabel:
    """Un libellé en texte BRUT (noms du catalogue, raisons), à la ligne si besoin."""
    lbl = QLabel(texte)
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    lbl.setWordWrap(True)
    lbl.setFont(body_font(taille))
    lbl.setStyleSheet(themed(style))
    return lbl


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
    if choix.fantome != config.course_fantome:
        config.course_fantome = choix.fantome
        config.save()
    fantome = (course.fantome(course.passees(game.id), choix.categorie, game.course.temps)
               if choix.fantome else None)
    native = ""
    if game.difficulte is not None:
        from src.core import difficulte_jeu
        rang = difficulte_jeu.lire(game, config)
        native = f";native={rang}" if rang is not None else ""
    try:
        etat = mode_course.entrer(game, choix.ini, choix.categorie, choix.empreinte, "normal" + native,
                                  fantome=fantome)
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
    """Le temps d'une course qui vient de finir : les deux temps, l'essai, le record et la place au classement,
    puis le découpage par carte avec les meilleurs passages en or et l'écart à chacun, la course idéale."""

    def __init__(self, conclusion: mode_course.Conclusion, nom: str, parent: QWidget | None = None, *,
                 game: GameData | None = None, courses: list[course.Passee] | None = None,
                 classement_: classement.Classement | None = None) -> None:
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
        valable = r.fin and not conclusion.refus
        self.setWindowTitle(tr("Course : {}").format(nom))
        self.setMinimumSize(560, 480)
        self.setStyleSheet(themed(_FENETRE) + feuille_de_style())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(8)
        titre = _libelle(tr("Course terminée : {}").format(nom) if r.fin
                         else tr("Course non terminée : {}").format(nom), _OR)
        titre.setFont(cinzel(14, bold=True))
        layout.addWidget(titre)
        ordre = sorted(du_jeu, key=lambda c: (c.jour, c.ecrite_ns))
        rang_essai = next((i + 1 for i, c in enumerate(ordre) if c.code == conclusion.code), len(ordre) + 1)
        layout.addWidget(_libelle(f"{nom_cat} · " + tr("essai {}").format(rang_essai), _GRIS, 12))

        principal, nom_principal, autre = _deux_temps(game, r)
        temps = QLabel(course.format_temps(principal))
        temps.setObjectName("tempsCourse")
        temps.setFont(cinzel(28, bold=True))
        temps.setStyleSheet(themed(_OR if valable else _TEXTE))
        layout.addWidget(temps)
        infos = [nom_principal, autre,
                 trn(r.chargements, "{} chargement", "{} chargements").format(r.chargements)]
        if r.rechargements:
            infos.append(trn(r.rechargements, "{} partie rechargée", "{} parties rechargées").format(r.rechargements))
        if r.fps_moyen is not None:
            infos.append(tr("{} images/s en moyenne").format(f"{r.fps_moyen:.0f}"))
        layout.addWidget(_libelle(" · ".join(infos), _GRIS, 11))
        layout.addWidget(_libelle(
            tr("Temps valable, à prouver par la vidéo.") if not conclusion.refus else
            "\n".join(raison(c) for c in conclusion.refus), _OR if not conclusion.refus else _ROUGE, 12))
        if r.interdits:
            layout.addWidget(_libelle(tr("Interdits en course : {}").format(", ".join(r.interdits)), _ROUGE, 11))
        if valable:
            self._record(layout, du_jeu, principal, quel, classement_)
        if r.segments:
            layout.addSpacing(4)
            layout.addWidget(_libelle(tr("Par carte"), _OR, 12))
            avant = course.passages_d_avant(du_jeu, conclusion.code, conclusion.categorie, r.segments)
            layout.addWidget(self._segments(r.segments, avant), 1)
            ideale = course.ideale(du_jeu, conclusion.categorie, quel)
            if ideale is not None and ideale.a_gagner_us > 0:
                layout.addWidget(_libelle(tr("Course idéale : {} sans chargements, encore {} à gagner.").format(
                    course.format_temps(ideale.net_us), course.format_temps(ideale.a_gagner_us)), _GRIS, 11))
        layout.addWidget(_libelle(tr(
            "Le journal signé est dans le dossier de la course. Le launcher est libre : sa signature n'arrête "
            "qu'une retouche à la main du fichier. La vidéo reste la preuve."), _GRIS, 10))
        if not conclusion.rendu:
            layout.addWidget(_libelle(tr(
                "Vos réglages n'ont pas pu être rendus : le launcher réessaiera à son prochain démarrage."),
                _ROUGE, 11))
        pied = QHBoxLayout()
        dossier = lien(tr("Ouvrir le dossier de la course"), discret=True)
        dossier.clicked.connect(lambda: open_local_path(str(course.dossier(conclusion.code))))
        pied.addWidget(dossier)
        pied.addStretch()
        copier = bouton(tr("Copier le résumé"))
        copier.clicked.connect(self._copier)
        fermer = bouton(tr("Fermer"), principal=True)
        fermer.clicked.connect(self.accept)
        for b in (copier, fermer):
            b.setAutoDefault(False)
            pied.addWidget(b)
        layout.addLayout(pied)

    def _record(self, layout: QVBoxLayout, du_jeu: list[course.Passee], principal: int, quel: str,
                classement_: classement.Classement | None) -> None:
        """Le record d'avant battu ou non, et la place que ce temps prendrait au classement Accio."""
        avant = course.meilleure([c for c in du_jeu if c.code != self._conclusion.code], None, quel)
        if avant is None:
            phrase, style = tr("Premier temps valable dans cette catégorie."), _VERT
        elif principal < avant.temps(quel):
            phrase = tr("Nouveau record : {} de mieux que le précédent.").format(
                course.format_temps(avant.temps(quel) - principal))
            style = _VERT
        else:
            phrase = tr("Votre record reste {} ({} de plus cette fois).").format(
                course.format_temps(avant.temps(quel)), course.format_temps(principal - avant.temps(quel)))
            style = _TEXTE
        self.phrase_record = _libelle(phrase, style, 12)
        layout.addWidget(self.phrase_record)
        tableau = (classement_ or classement.en_cache()).de(self._conclusion.jeu, self._conclusion.categorie)
        rangee = QHBoxLayout()
        rangee.addWidget(_libelle(tr("Ce temps prendrait la place {} du classement Accio : publiez la vidéo et "
                                     "le course.json sur le Discord pour y entrer.").format(
            classement.rang(tableau, principal)), _TEXTE, 12), 1)
        discord = lien(tr("Ouvrir le Discord"), discret=True)
        discord.clicked.connect(lambda: open_url(DISCORD_URL))
        rangee.addWidget(discord, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(rangee)

    def _segments(self, segments: tuple[course.Segment, ...], avant: tuple[int | None, ...]) -> QScrollArea:
        """Une ligne par carte : son nom (celui du jeu), son temps sans chargements, l'écart au meilleur passage
        d'avant à cette place du parcours ; en or, un meilleur passage."""
        contenu = QWidget()
        transparent(contenu)
        grille = QGridLayout(contenu)
        grille.setContentsMargins(0, 0, 6, 0)
        grille.setHorizontalSpacing(14)
        grille.setVerticalSpacing(2)
        grille.setColumnStretch(0, 1)
        droite = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        self.meilleurs: list[int] = []
        for i, (s, meilleur) in enumerate(zip(segments, avant, strict=True)):
            nom = tr("{} (rechargée)").format(s.carte) if s.depuis_sauvegarde else s.carte or tr("(sans nom)")
            dore = meilleur is not None and s.net_us <= meilleur
            if dore:
                self.meilleurs.append(i)
            grille.addWidget(_libelle(nom, _OR if dore else _TEXTE, 11), i, 0)
            grille.addWidget(_libelle(course.format_temps(s.net_us), _OR if dore else _TEXTE, 11), i, 1, droite)
            if meilleur is not None:
                ecart = _libelle(course.format_ecart(s.net_us - meilleur), _VERT if dore else _GRIS, 11)
                grille.addWidget(ecart, i, 2, droite)
        grille.setRowStretch(len(segments), 1)
        zone = QScrollArea()
        zone.setWidgetResizable(True)
        zone.setWidget(contenu)
        zone.setStyleSheet("QScrollArea { background: transparent; border: none; }" + BARRE_DEFILEMENT)
        return zone

    def _copier(self) -> None:
        QGuiApplication.clipboard().setText(resume(self._conclusion, self._nom, self._game))


def montrer(window: MainWindow, conclusion: mode_course.Conclusion) -> None:
    """Fenêtre modale mais SANS boucle à elle : appelée depuis un minuteur, un `exec` bloquerait tout ce qui
    suit dans la boucle d'évènements."""
    game = window.manager.get_game_by_id(conclusion.jeu)
    dlg = CourseResultat(conclusion, game.name if game is not None else conclusion.jeu, window, game=game)
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
