"""Les Courses du Carnet (1.5) : les courses gardées d'un jeu, par catégorie, son meilleur temps valable et
son meilleur passage sur chaque carte (le classement par niveau de la base, `course.par_carte`).

Quatrième rubrique du Carnet (`carnet_page.py`), sur le jeu choisi en haut comme le Folio et les Défis, et
seulement quand une course a été gardée : une rubrique toujours vide serait un onglet de plus pour rien.
Ce qui se lit est le `course.json` de chaque course (`course.passees`) : son temps sans chargements (S7.4),
s'il est valable, sinon la première raison du refus ; le dossier s'ouvre, une course s'efface après
confirmation (`mode_course.supprimer`, qui refuse une course dont les réglages ne sont pas encore rendus).
Aucune course n'est lue en entier ici : ses lignes brutes restent dans son dossier. Chaque `course.json` est lu
UNE fois par visite du Carnet (règle 140) : le Carnet passe sa liste, la page ne relit qu'après une suppression.
Les pastilles des catégories ne paraissent que si le jeu a des courses de plus d'une catégorie ; changer de
catégorie redessine la page sur la liste déjà lue.

Sous ses courses, le classement Accio de la catégorie (`classement.py`, le cache que le Carnet passe) :
rang, joueur, temps, jour, vidéo ; la place que prendrait le record du joueur ; comment y entrer.
"""

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.core import classement, course, mode_course
from src.core.ecriture_atomique import ecrire_atomique
from src.core.game_data import GameData
from src.core.i18n import tr, trn
from src.core.liens import DISCORD_URL
from src.core.phonographe import nom_de_fichier
from src.ui.composants import feuille_de_style, filtre, lien
from src.ui.course_ui import raison
from src.ui.fenetre_message import message
from src.ui.folio_page import _tuile
from src.ui.stats_widgets import _DISCRET, _Paragraphe, _texte
from src.ui.theme import RAYON_CARTE, themed
from src.ui.utils import BARRE_DEFILEMENT, open_local_path, open_url

_LARGEUR_TUILE = 360         # celle des tuiles des Défis et du Folio

_STYLE = f"""
QWidget#courses, QWidget#coursesCorps {{ background: transparent; }}
QScrollArea {{ background: transparent; border: none; }}
QFrame#courseGardee {{ background: #0d0d1a; border: 1px solid rgba(214, 167, 44, 0.12);
                       border-radius: {RAYON_CARTE}px; }}
QFrame#courseGardee[valable="true"] {{ border-color: rgba(214, 167, 44, 0.32); }}
QFrame#parCarte, QFrame#classement {{ background: #0d0d1a; border: 1px solid rgba(214, 167, 44, 0.12);
                  border-radius: {RAYON_CARTE}px; }}
"""


class _Ligne(QFrame):
    """Une course : jour et code, temps, statut ; « Ouvrir le dossier », « Supprimer »."""

    def __init__(self, passee: course.Passee, page: CoursesPage) -> None:
        super().__init__()
        self.setObjectName("courseGardee")
        self.setProperty("valable", passee.valable)
        self.code = passee.code
        h = QHBoxLayout(self)
        h.setContentsMargins(16, 10, 16, 10)
        h.setSpacing(14)
        gauche = QVBoxLayout()
        gauche.setSpacing(2)
        gauche.addWidget(_texte(f"{passee.jour} · {passee.code}", 12, _DISCRET))
        statut = (tr("Temps valable") if passee.valable
                  else raison(passee.refus[0]) if passee.refus else raison(course.SANS_FIN))
        self.statut = _texte(statut, 12, "#d6a72c" if passee.valable else "#e07a6a")
        self.statut.setWordWrap(True)
        gauche.addWidget(self.statut)
        h.addLayout(gauche, 1)
        temps = _texte(course.format_temps(passee.net_us), 18, "#ffffff" if passee.valable else "#c9c7da")
        temps.setObjectName("tempsGarde")
        h.addWidget(temps, alignment=Qt.AlignmentFlag.AlignVCenter)
        dossier = lien(tr("Ouvrir le dossier"), discret=True)
        dossier.clicked.connect(lambda: open_local_path(str(course.dossier(passee.code))))
        h.addWidget(dossier, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.bouton_supprimer = lien(tr("Supprimer"), discret=True)
        self.bouton_supprimer.clicked.connect(lambda: page.supprimer(passee))
        h.addWidget(self.bouton_supprimer, alignment=Qt.AlignmentFlag.AlignVCenter)


class CoursesPage(QWidget):
    """Les courses gardées d'un jeu et son classement Accio ; un mot quand il n'en a pas."""

    def __init__(self, game: GameData, gardees: list[course.Passee],
                 classement_: classement.Classement = classement.VIDE, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("courses")
        self.setStyleSheet(themed(_STYLE) + feuille_de_style())
        self.game = game
        self.lignes: list[_Ligne] = []
        self.pastilles: dict[str, QPushButton] = {}
        self.passages: list[course.Passage] = []
        self.bouton_livesplit: QPushButton | None = None
        self.classement = classement_
        self.places: list[classement.Entree] = []
        self.note_place: QLabel | None = None
        du_jeu = [c for c in gardees if c.jeu == game.id]
        # La page s'ouvre sur la catégorie de la course la plus récente (`passees` : la plus récente d'abord),
        # sans course sur la première du classement.
        classees = classement_.categories(game.id)
        self.categorie = du_jeu[0].categorie if du_jeu else classees[0] if classees else course.ANY
        self._passees: list[course.Passee] = []
        # Une course effacée : le Carnet relit sa liste quand il retire la page.
        self.modifiee = False
        self._racine = QVBoxLayout(self)
        self._racine.setContentsMargins(0, 0, 0, 0)
        self._remplir(du_jeu)

    def _remplir(self, passees: list[course.Passee]) -> None:
        self._passees = passees
        classees = self.classement.categories(self.game.id)
        presentes = [c for c in course.CATEGORIES if c in classees or any(p.categorie == c for p in passees)]
        if self.categorie not in presentes and presentes:
            # la catégorie choisie n'a plus de course (suppression)
            self.categorie = passees[0].categorie if passees else presentes[0]
        passees = [p for p in passees if p.categorie == self.categorie]
        self.lignes, self.pastilles, self.passages, self.places = [], {}, [], []
        self.note_place = None
        self.bouton_livesplit = None
        zone = QScrollArea()
        zone.setWidgetResizable(True)
        zone.setFrameShape(QFrame.Shape.NoFrame)
        zone.setObjectName("zoneCourses")
        zone.setStyleSheet(themed(BARRE_DEFILEMENT))
        corps = QWidget()
        corps.setObjectName("coursesCorps")
        lay = QVBoxLayout(corps)
        lay.setContentsMargins(40, 26, 40, 30)
        lay.setSpacing(8)
        zone.setWidget(corps)
        self._racine.addWidget(zone)
        if not presentes:
            lay.addWidget(_Paragraphe(tr("Aucune course de ce jeu n'est gardée."), taille=16))
            lay.addStretch()
            return
        zone.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if len(presentes) > 1:
            lay.addLayout(self._choix(presentes))
            lay.addSpacing(10)
        if passees:
            self._mes_courses(lay, passees)
        else:
            lay.addWidget(_texte(tr("Aucune course gardée en {}.").format(self.categorie), 14, _DISCRET))
        self._classement(lay, course.meilleure(passees, self.categorie))
        lay.addStretch()

    def _mes_courses(self, lay: QVBoxLayout, passees: list[course.Passee]) -> None:
        """Le meilleur temps, l'export LiveSplit, les courses gardées, le meilleur passage par carte."""
        haut = QHBoxLayout()
        record = course.meilleure(passees, self.categorie)
        tuile = _tuile(course.format_temps(record.net_us) if record is not None else "—",
                       (tr("Meilleur temps valable") if record is not None else tr("Aucun temps valable"))
                       + " · " + self.categorie)
        tuile.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        tuile.setMaximumWidth(_LARGEUR_TUILE)
        haut.addWidget(tuile)
        if record is not None and record.segments:
            self.bouton_livesplit = lien(tr("Exporter pour LiveSplit"), discret=True)
            self.bouton_livesplit.setToolTip(tr("Le meilleur temps de la catégorie, découpé par carte, en fichier "
                                                "de découpage LiveSplit (.lss)."))
            self.bouton_livesplit.clicked.connect(self.exporter_livesplit)
            haut.addSpacing(18)
            haut.addWidget(self.bouton_livesplit, alignment=Qt.AlignmentFlag.AlignVCenter)
        haut.addStretch()
        lay.addLayout(haut)
        lay.addSpacing(6)
        lay.addWidget(_texte(trn(len(passees), "{} course gardée", "{} courses gardées").format(len(passees))
                             + " · " + tr("sans les chargements"), 12, _DISCRET))
        lay.addSpacing(8)
        for passee in passees:
            ligne = _Ligne(passee, self)
            lay.addWidget(ligne)
            self.lignes.append(ligne)
        self.passages = list(course.par_carte(passees, self.categorie))
        if self.passages:
            lay.addSpacing(18)
            lay.addWidget(_texte(tr("Meilleur passage par carte"), 14, "#d6a72c"))
            lay.addWidget(_texte(tr("Pris dans les courses valables ; une carte rechargée ne compte pas."),
                                 12, _DISCRET))
            lay.addWidget(self._par_carte(self.passages))

    def _classement(self, lay: QVBoxLayout, record: course.Passee | None) -> None:
        """Le classement Accio de la catégorie, la place qu'y prendrait le record, comment y entrer."""
        self.places = list(self.classement.de(self.game.id, self.categorie))
        lay.addSpacing(18)
        lay.addWidget(_texte(tr("Classement Accio") + " · " + self.categorie, 14, "#d6a72c"))
        if self.places:
            lay.addWidget(self._grille(self.places))
        else:
            lay.addWidget(_texte(tr("Personne n'y est encore classé."), 12, _DISCRET))
        if record is not None and record.code not in {e.code for e in self.places}:
            place = classement.rang(tuple(self.places), record.net_us)
            self.note_place = _texte(tr("Votre record ({}) y prendrait la place {}.").format(
                course.format_temps(record.net_us), place), 12, "#e0e0f0")
            lay.addWidget(self.note_place)
        entrer = QHBoxLayout()
        entrer.addWidget(_texte(tr("Pour y entrer, publiez la vidéo de la course et son course.json sur le "
                                   "Discord : une fois validée, elle apparaît ici."), 12, _DISCRET))
        discord = lien(tr("Ouvrir le Discord"), discret=True)
        discord.clicked.connect(lambda: open_url(DISCORD_URL))
        entrer.addSpacing(10)
        entrer.addWidget(discord, alignment=Qt.AlignmentFlag.AlignVCenter)
        entrer.addStretch()
        lay.addLayout(entrer)

    @staticmethod
    def _grille(entrees: list[classement.Entree]) -> QFrame:
        """Une ligne par course classée : rang, joueur, jour et code, temps, vidéo. Les noms viennent du
        réseau : `_texte` les montre en texte brut."""
        cadre = QFrame()
        cadre.setObjectName("classement")
        grille = QGridLayout(cadre)
        grille.setContentsMargins(16, 10, 16, 10)
        grille.setHorizontalSpacing(14)
        grille.setVerticalSpacing(4)
        grille.setColumnStretch(1, 1)
        droite = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        for i, e in enumerate(entrees):
            grille.addWidget(_texte(str(i + 1), 12, "#d6a72c" if i < 3 else _DISCRET), i, 0, droite)
            grille.addWidget(_texte(e.joueur, 12, "#e0e0f0"), i, 1)
            grille.addWidget(_texte(" · ".join(x for x in (e.jour, e.code) if x), 11, _DISCRET), i, 2, droite)
            grille.addWidget(_texte(course.format_temps(e.net_us), 12, "#ffffff"), i, 3, droite)
            if e.video:
                video = lien(tr("Vidéo"), discret=True)
                video.setToolTip(e.video)
                video.clicked.connect(lambda _c=False, u=e.video: open_url(u))
                grille.addWidget(video, i, 4, droite)
        return cadre

    def _choix(self, presentes: list[str]) -> QHBoxLayout:
        rangee = QHBoxLayout()
        rangee.setSpacing(8)
        groupe = QButtonGroup(self)
        groupe.setExclusive(True)
        for nom in presentes:
            b = filtre(nom)
            b.setChecked(nom == self.categorie)
            b.clicked.connect(lambda _c=False, n=nom: self.montrer_categorie(n))
            groupe.addButton(b)
            self.pastilles[nom] = b
            rangee.addWidget(b)
        rangee.addStretch()
        return rangee

    @staticmethod
    def _par_carte(passages: list[course.Passage]) -> QFrame:
        """Une ligne par carte : son nom (celui du jeu), le temps, la course qui l'a fait."""
        cadre = QFrame()
        cadre.setObjectName("parCarte")
        grille = QGridLayout(cadre)              # une grille : les temps restent alignés en colonne
        grille.setContentsMargins(16, 10, 16, 10)
        grille.setHorizontalSpacing(14)
        grille.setVerticalSpacing(4)
        grille.setColumnStretch(0, 1)
        droite = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        for rang, s in enumerate(passages):
            grille.addWidget(_texte(s.carte, 12, "#e0e0f0"), rang, 0)
            grille.addWidget(_texte(f"{s.jour} · {s.code}", 11, _DISCRET), rang, 1, droite)
            grille.addWidget(_texte(course.format_temps(s.net_us), 12, "#ffffff"), rang, 2, droite)
        return cadre

    def exporter_livesplit(self) -> None:
        """Le .lss de la catégorie (`course.livesplit`), là où le joueur le veut (Documents d'abord)."""
        texte = course.livesplit(self.game.name, self.categorie, self._passees)
        if texte is None:
            return
        dossier = Path.home() / "Documents"
        nom = nom_de_fichier(f"{self.game.name} - {self.categorie}") + ".lss"
        cible, _filtre = QFileDialog.getSaveFileName(
            self, tr("Exporter pour LiveSplit"), str((dossier if dossier.is_dir() else Path.home()) / nom),
            tr("Découpage LiveSplit (*.lss)"))
        if not cible:
            return
        destination = Path(cible)
        if destination.suffix.lower() != ".lss":
            destination = destination.with_name(destination.name + ".lss")
        try:
            ecrire_atomique(destination, texte)
        except OSError:
            message(self, QMessageBox.Icon.Warning, tr("Exporter pour LiveSplit"),
                    tr("Le fichier n'a pas pu être écrit à cet endroit."))

    def montrer_categorie(self, categorie: str) -> None:
        """Redessine la page sur la catégorie choisie, sans relire les courses."""
        if categorie != self.categorie:
            self.categorie = categorie
            self._rebatir(self._passees)

    def _rebatir(self, passees: list[course.Passee]) -> None:
        ancienne = self._racine.takeAt(0)
        if ancienne is not None and (w := ancienne.widget()) is not None:
            w.hide()
            w.deleteLater()
        self._remplir(passees)

    def supprimer(self, passee: course.Passee) -> None:
        """Après confirmation, efface la course et redessine la page."""
        choix = message(
            self, QMessageBox.Icon.Question, tr("Supprimer la course"),
            tr("La course {} du {} ({}) est effacée : son journal signé et ses sauvegardes.").format(
                passee.code, passee.jour, course.format_temps(passee.net_us)) + "\n\n"
            + tr("Gardez une copie de son dossier si vous voulez encore la présenter."),
            choix=(tr("Supprimer"), tr("Annuler")), defaut=1, danger=True)
        if choix != 0:
            return
        if not mode_course.supprimer(passee.code):
            message(self, QMessageBox.Icon.Warning, tr("Supprimer la course"),
                    tr("Cette course n'a pas pu être effacée : ses réglages ne sont pas encore rendus, ou son "
                       "dossier est ouvert ailleurs."))
            return
        self.modifiee = True
        self._rebatir(course.passees(self.game.id))
