"""La course (1.5) dans l'interface : le dialogue de départ, le fil de l'empreinte, le résultat.

Le chrono, le temps et le verdict sont dans `core/course` ; les réglages tenus et rendus dans
`core/mode_course`. Ici : ce qui se VOIT, et l'orchestration du départ (`partir`), comme
`game_detail_handlers.on_play` qu'il appelle ensuite. Une course part d'une NOUVELLE partie (S7.1), le
temps compté est celui sans les chargements (S7.4), et la phrase sur la vidéo est dite telle que Ludo l'a
tranchée (S7.7) : la signature n'arrête qu'une retouche à la main du fichier.
"""

import json
import logging
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.core import course, mode_course
from src.core import difficulte_presets as dp
from src.core.config import APP_VERSION, Config
from src.core.game_data import GameData
from src.core.thread_utils import liberer_apres_fin
from src.core.i18n import tr, trn
from src.ui.composants import bouton, feuille_de_style, filtre, lien, transparent
from src.ui.entree_focus import entree_suit_le_focus
from src.ui.fenetre_message import message
from src.ui.fonts import body_font, cinzel
from src.ui.theme import themed
from src.ui.toggle_switch import ToggleSwitch
from src.ui.utils import BARRE_DEFILEMENT, open_local_path

if TYPE_CHECKING:
    from src.ui.game_detail import GameDetailView
    from src.ui.main_window import MainWindow

log = logging.getLogger(__name__)

_FENETRE = "QDialog { background: #0d0d1a; border: 1px solid rgba(214,167,44,0.3); }"
_BARRE = ("QProgressBar { background: #141428; border: 1px solid #2a2a48; border-radius: 4px; height: 8px; }"
          "QProgressBar::chunk { background: #d6a72c; border-radius: 3px; }")
_GRIS = "color: #8a8aaa; background: transparent;"
_TEXTE = "color: #e0e0f0; background: transparent;"
_OR = "color: #d6a72c; background: transparent;"
_ROUGE = "color: #e07a6a; background: transparent;"
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
        course.SANS_FIN: tr("La fin de la course n'a pas été vue : partie quittée avant le générique."),
        course.RETOUCHE: tr("Le temps écrit ne correspond pas aux chargements du journal."),
        course.TROP_D_IMAGES: tr("Le jeu a dépassé 60 images par seconde."),
        course.MODE_NON_TENU: tr("Un réglage qui touche au temps du jeu a changé pendant la course."),
        course.INTERDITS: tr("Le correctif a vu un réglage interdit en course."),
        course.SOUS_WINE: tr("Sous Linux, la ligne ACCIO ne s'affiche pas encore à l'écran : le temps n'est pas classé."),
        "sauvegardes": tr("Le dossier des sauvegardes de la course ne s'écrit pas à un endroit que le jeu sait lire."),
        "ini": tr("Les réglages de la course n'ont pas pu être écrits dans le dossier du jeu."),
        "journal_tenu": tr("Le journal d'une course passée est encore ouvert : fermez le jeu."),
    }
    return phrases.get(code, code)


def regle_categorie(categorie: str) -> str:
    """Ce que la catégorie demande, en une phrase. Le launcher ne le vérifie pas : la vidéo le montre."""
    return {
        course.ANY: tr("Finir le jeu le plus vite possible, par tous les moyens."),
        course.CENT: tr("Finir le jeu en ayant tout ramassé, comme le demande le classement du jeu."),
        course.SANS_BUG: tr("Finir le jeu sans exploiter aucun bug : ni traverser un mur, ni sauter une scène par une faille."),
    }.get(categorie, "")


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


def _libelle(texte: str, style: str = _TEXTE, taille: int = 12) -> QLabel:
    """Un libellé en texte BRUT (noms du catalogue, raisons), à la ligne si besoin."""
    lbl = QLabel(texte)
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    lbl.setWordWrap(True)
    lbl.setFont(body_font(taille))
    lbl.setStyleSheet(themed(style))
    return lbl


def _titre(texte: str) -> QLabel:
    lbl = _libelle(texte, _OR)
    lbl.setFont(cinzel(14, bold=True))
    return lbl


def dossiers(game: GameData, install_path: Path) -> tuple[Path, Path]:
    """(dossier du jeu, dossier de l'exe)."""
    exe = Path(game.executable)
    return Path(install_path) / exe.parts[0], (Path(install_path) / exe).parent


class CourseDialog(QDialog):
    """Catégorie, règles, fantôme, ce qui bloque, ce qui sera remis ; « Partir » calcule l'empreinte puis
    rend la main (`empreinte` posée, dialogue accepté). Le départ lui-même est l'affaire de `partir`."""

    def __init__(self, game: GameData, install_path: Path, bloquants: list[str],
                 ecarts: list[mode_course.Ecart], parent: QWidget | None = None, *, fantome: bool = True) -> None:
        super().__init__(parent)
        entree_suit_le_focus(self)
        self.game = game
        self.empreinte: course.Empreinte | None = None
        self.categorie = course.ANY
        self.fantome = fantome
        self._courses = course.passees(game.id)
        self._install_path = Path(install_path)
        self._fil: EmpreinteThread | None = None
        self.setWindowTitle(tr("Course : {}").format(game.name))
        self.setMinimumWidth(560)
        self.setStyleSheet(themed(_FENETRE) + feuille_de_style())
        self._construire(bloquants, ecarts)

    def _construire(self, bloquants: list[str], ecarts: list[mode_course.Ecart]) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 16)
        layout.setSpacing(10)
        layout.addWidget(_titre(tr("Course : {}").format(self.game.name)))
        layout.addLayout(self._choix_categorie())
        self._regle = _libelle(regle_categorie(self.categorie), _OR, 12)
        layout.addWidget(self._regle)
        for regle in (
                tr("Le chrono part d'une nouvelle partie et compte le temps sans les chargements."),
                tr("60 images par seconde au plus ; ce qui touche au temps du jeu est remis le temps de la course,"
                   " puis vos réglages vous sont rendus."),
                tr("Une ligne ACCIO reste en bas de l'image toute la course, avec le chrono sans chargements"
                   " et les images par seconde : elle doit se lire sur votre vidéo, entière. C'est la vidéo,"
                   " jugée par une personne, qui prouve la course.")):
            layout.addWidget(_libelle("• " + regle))
        layout.addLayout(self._choix_fantome())
        if self.game.id == "hp1":
            layout.addWidget(_libelle(tr(
                "HP1 : une course Accio ne compte pas sur le classement speedrun.com du jeu tant que ses "
                "modérateurs n'ont pas accepté la limite d'images d'Accio."), _GRIS, 11))
        if sys.platform != "win32":
            layout.addWidget(_libelle(raison(course.SOUS_WINE), _GRIS, 11))
        if ecarts:
            note = _libelle(trn(len(ecarts),
                                       "{} réglage sera remis le temps de la course, puis rendu.",
                                       "{} réglages seront remis le temps de la course, puis rendus.")
                                   .format(len(ecarts)), _GRIS, 11)
            note.setToolTip("\n".join(f"{e.cle} : {e.valeur if e.valeur is not None else '—'} → {e.posee or '—'}"
                                      for e in ecarts))
            layout.addWidget(note)
        self._bloque = _libelle("\n".join(bloquants), _ROUGE, 12)
        self._bloque.setVisible(bool(bloquants))
        layout.addWidget(self._bloque)
        self._barre = QProgressBar()
        self._barre.setRange(0, 1000)
        self._barre.setTextVisible(False)
        self._barre.setStyleSheet(themed(_BARRE))
        self._barre.hide()
        layout.addWidget(self._barre)
        self._etat = _libelle("", _GRIS, 11)
        self._etat.hide()
        layout.addWidget(self._etat)
        pied = QHBoxLayout()
        pied.addStretch()
        self._partir = bouton(tr("Partir"), principal=True)
        self._partir.setEnabled(not bloquants)
        self._partir.clicked.connect(self._calculer)
        fermer = bouton(tr("Fermer"))
        fermer.clicked.connect(self.reject)
        for b in (self._partir, fermer):
            b.setAutoDefault(False)
            pied.addWidget(b)
        layout.addLayout(pied)

    def _choix_categorie(self) -> QHBoxLayout:
        """Une pastille par catégorie, Any% cochée ; la règle de la catégorie dessous."""
        rangee = QHBoxLayout()
        rangee.setSpacing(8)
        rangee.addWidget(_libelle(tr("Catégorie"), _GRIS, 12))
        self.pastilles: dict[str, QPushButton] = {}
        self._groupe = QButtonGroup(self)
        self._groupe.setExclusive(True)
        for nom in course.CATEGORIES:
            b = filtre(nom)
            b.setChecked(nom == self.categorie)
            b.toggled.connect(lambda coche, n=nom: coche and self._choisir(n))
            self._groupe.addButton(b)
            self.pastilles[nom] = b
            rangee.addWidget(b)
        rangee.addStretch()
        return rangee

    def _choix_fantome(self) -> QHBoxLayout:
        """« Fantôme » : voir ou non l'écart à son record de la catégorie ; la phrase dit ce record."""
        rangee = QHBoxLayout()
        rangee.setSpacing(12)
        colonne = QVBoxLayout()
        colonne.setSpacing(2)
        colonne.addWidget(_libelle(tr("Fantôme"), _TEXTE, 12))
        self._note_fantome = _libelle("", _GRIS, 11)
        colonne.addWidget(self._note_fantome)
        rangee.addLayout(colonne, 1)
        self.bascule_fantome = ToggleSwitch(self.fantome)
        self.bascule_fantome.setAccessibleName(tr("Fantôme"))
        self.bascule_fantome.toggled.connect(self._basculer_fantome)
        rangee.addWidget(self.bascule_fantome, alignment=Qt.AlignmentFlag.AlignVCenter)
        self._decrire_fantome()
        return rangee

    def _basculer_fantome(self, coche: bool) -> None:
        self.fantome = coche
        self._decrire_fantome()

    def _decrire_fantome(self) -> None:
        record = course.meilleure(self._courses, self.categorie)
        if not self.fantome:
            texte = tr("Seuls le chrono et les images par seconde sont montrés.")
        elif record is None:
            texte = tr("Pas encore de record valable en {} : l'écart viendra avec le premier.").format(self.categorie)
        else:
            texte = tr("L'écart à votre record en {} ({}) suit le chrono à chaque carte quittée.").format(
                self.categorie, course.format_temps(record.net_us))
        self._note_fantome.setText(texte)

    def _choisir(self, categorie: str) -> None:
        self.categorie = categorie
        self._regle.setText(regle_categorie(categorie))
        self._decrire_fantome()

    def _calculer(self) -> None:
        for b in (*self.pastilles.values(), self.bascule_fantome):
            b.setEnabled(False)
        self._partir.setEnabled(False)
        self._barre.show()
        self._etat.setText(tr("Empreinte des fichiers du jeu…"))
        self._etat.show()
        jeu, exe = dossiers(self.game, self._install_path)
        fil = EmpreinteThread(self.game.id, jeu, exe)
        fil.progress.connect(self._barre.setValue)
        fil.error.connect(self._echec)
        fil.empreinte_prete.connect(self._prete)
        self._fil = fil
        fil.start()

    def _lacher_fil(self, sur_sa_fin: bool = False) -> None:
        """Déconnecte le fil, puis : depuis un de ses signaux de fin, `liberer_apres_fin` (règle 133) ;
        sinon (fenêtre fermée en route), l'annuler, l'attendre 3 s, et le garer s'il ne répond pas."""
        fil, self._fil = self._fil, None
        if fil is None:
            return
        for signal, slot in ((fil.progress, self._barre.setValue), (fil.error, self._echec),
                             (fil.empreinte_prete, self._prete)):
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

    def _prete(self, emp: course.Empreinte) -> None:
        self._lacher_fil(sur_sa_fin=True)
        self.empreinte = emp
        self.accept()

    def _echec(self, texte: str) -> None:
        self._lacher_fil(sur_sa_fin=True)
        self._barre.hide()
        self._etat.setText(tr("L'empreinte n'a pas pu être calculée : {}").format(texte))
        self._partir.setEnabled(True)
        for b in (*self.pastilles.values(), self.bascule_fantome):
            b.setEnabled(True)

    def done(self, code: int) -> None:
        self._lacher_fil()
        super().done(code)


def bloquants(game: GameData, config: Config) -> list[str]:
    """Ce qui empêche le départ, en phrases : la difficulté doit être Normal (la une seule vie coupée)."""
    sortie = []
    if dp.au_lancement(game, config) != "normal":
        sortie.append(tr("Choisissez la difficulté Normal (une seule vie coupée) : la course se court sur le jeu "
                         "d'origine."))
    return sortie


def partir(view: GameDetailView) -> None:
    """Le bouton « Course » de la fiche : dialogue, empreinte, réglages tenus et clés de la course, lancement.
    Si le jeu ne part pas, les réglages sont rendus aussitôt."""
    from src.ui import game_detail_handlers as handlers
    game, config = view.game, view.manager.config
    if game is None:
        return
    if view.partie_en_cours():
        view.notify.emit(tr("{} est en train de démarrer ou déjà lancé.").format(view.partie_en_cours()))
        return
    ini = mode_course.ini(game, config.install_path)
    if ini is None:
        return
    dlg = CourseDialog(game, config.install_path, bloquants(game, config),
                       mode_course.ecarts(game.id, ini), view, fantome=config.course_fantome)
    if dlg.exec() != QDialog.DialogCode.Accepted or dlg.empreinte is None:
        return
    if dlg.fantome != config.course_fantome:
        config.course_fantome = dlg.fantome
        config.save()
    fantome = course.fantome(course.passees(game.id), dlg.categorie) if dlg.fantome else None
    native = ""
    if game.difficulte is not None:
        from src.core import difficulte_jeu
        rang = difficulte_jeu.lire(game, config)
        native = f";native={rang}" if rang is not None else ""
    try:
        etat = mode_course.entrer(game, ini, dlg.categorie, dlg.empreinte, "normal" + native, fantome=fantome)
    except (mode_course.CourseRefusee, OSError, ValueError) as exc:
        code = str(exc.args[0]) if isinstance(exc, mode_course.CourseRefusee) and exc.args else "ini"
        message(view, QMessageBox.Icon.Warning, tr("Course"), raison(code))
        return
    handlers.on_play(view)
    if not view.partie_en_cours():
        mode_course.sortir(etat)


def resume(conclusion: mode_course.Conclusion, nom: str) -> str:
    """Le résumé à coller avec la vidéo : jeu, catégorie, temps, ligne d'identifiant, versions."""
    r = conclusion.resultat
    lignes = [f"{nom} — {conclusion.categorie}",
              tr("Temps (sans chargements) : {}").format(course.format_temps(r.net)),
              tr("Temps total : {}").format(course.format_temps(r.total_us if r.fin else r.total_calcule_us)),
              conclusion.ligne_id,
              tr("Launcher {} · correctif {}").format(APP_VERSION, r.version_fix or "?")]
    lignes += [raison(code) for code in conclusion.refus]
    return "\n".join(lignes)


class CourseResultat(QDialog):
    """Le temps d'une course qui vient de finir : temps sans chargements, découpage par carte, refus."""

    def __init__(self, conclusion: mode_course.Conclusion, nom: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        entree_suit_le_focus(self)
        self._conclusion, self._nom = conclusion, nom
        r = conclusion.resultat
        self.setWindowTitle(tr("Course : {}").format(nom))
        self.setMinimumSize(520, 420)
        self.setStyleSheet(themed(_FENETRE) + feuille_de_style())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 16)
        layout.setSpacing(8)
        layout.addWidget(_titre(tr("Course terminée : {}").format(nom) if r.fin
                                else tr("Course non terminée : {}").format(nom)))
        layout.addWidget(_libelle(conclusion.categorie, _GRIS, 12))
        temps = QLabel(course.format_temps(r.net))
        temps.setObjectName("tempsCourse")
        temps.setFont(cinzel(26, bold=True))
        temps.setStyleSheet(themed(_OR if not conclusion.refus else _TEXTE))
        layout.addWidget(temps)
        infos = [tr("sans les chargements"),
                 tr("{} au total").format(course.format_temps(r.total_us if r.fin else r.total_calcule_us)),
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
        if r.segments:
            layout.addWidget(_libelle(tr("Par carte"), _OR, 12))
            layout.addWidget(self._segments(r.segments), 1)
        layout.addWidget(_libelle(tr(
            "Le journal signé est dans le dossier de la course. Le launcher est libre : sa signature n'arrête "
            "qu'une retouche à la main du fichier. La vidéo reste la preuve."), _GRIS, 10))
        if not conclusion.rendu:
            layout.addWidget(_libelle(tr(
                "Vos réglages n'ont pas pu être rendus : le launcher réessaiera à son prochain démarrage."),
                _ROUGE, 11))
        pied = QHBoxLayout()
        dossier = lien(tr("Ouvrir le dossier de la course"))
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

    def _segments(self, segments: tuple[course.Segment, ...]) -> QScrollArea:
        """Une ligne par carte : son nom (celui du jeu), son temps sans chargements."""
        contenu = QWidget()
        transparent(contenu)
        grille = QVBoxLayout(contenu)
        grille.setContentsMargins(0, 0, 6, 0)
        grille.setSpacing(2)
        for s in segments:
            rangee = QHBoxLayout()
            nom = _libelle(s.carte or tr("(sans nom)"), _TEXTE, 11)
            if s.depuis_sauvegarde:
                nom.setText(tr("{} (rechargée)").format(s.carte))
            rangee.addWidget(nom, 1)
            rangee.addWidget(_libelle(course.format_temps(s.net_us), _TEXTE, 11))
            grille.addLayout(rangee)
        grille.addStretch()
        zone = QScrollArea()
        zone.setWidgetResizable(True)
        zone.setWidget(contenu)
        zone.setStyleSheet("QScrollArea { background: transparent; border: none; }" + BARRE_DEFILEMENT)
        return zone

    def _copier(self) -> None:
        QGuiApplication.clipboard().setText(resume(self._conclusion, self._nom))


def montrer(window: MainWindow, conclusion: mode_course.Conclusion) -> None:
    """Fenêtre modale mais SANS boucle à elle : appelée depuis un minuteur, un `exec` bloquerait tout ce qui
    suit dans la boucle d'évènements."""
    game = window.manager.get_game_by_id(conclusion.jeu)
    dlg = CourseResultat(conclusion, game.name if game is not None else conclusion.jeu, window)
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

