"""Les Courses du Carnet (1.5) : les courses gardées d'un jeu, par catégorie, son record, ses records successifs, sa
course idéale, son meilleur passage sur chaque carte (le classement par niveau de la base, `course.par_carte`),
la comparaison avec la course d'un ami, et le classement Accio.

Quatrième rubrique du Carnet (`carnet_page.py`), sur le jeu choisi en haut comme le Folio et les Défis, et
seulement quand une course a été gardée ou classée : une rubrique toujours vide serait un onglet de plus pour rien.
Ce qui se lit est le `course.json` de chaque course (`course.passees`) : ses deux temps (réel et sans chargements),
celui qui classe le jeu en premier (`course_regles`, le catalogue), s'il est valable, sinon la première raison du
refus ; le dossier s'ouvre, une course s'efface après confirmation (`mode_course.supprimer`, qui refuse une course
dont les réglages ne sont pas encore rendus). Chaque `course.json` est lu UNE fois par visite du Carnet (règle
140) : le Carnet passe sa liste, la page ne relit qu'après une suppression. Les pastilles des catégories ne
paraissent que si le jeu a des courses de plus d'une catégorie, dans l'ordre du catalogue ; changer de catégorie
redessine la page sur la liste déjà lue.

Partager et comparer passent par le `course.json` lui-même : « Partager mon record » en écrit une copie où le
joueur veut (pour un ami, ou le Discord), « Comparer à la course d'un ami » en lit une, la VÉRIFIE (signature,
temps et verdict recalculés depuis ses lignes brutes, `course.lire_externe`) et la met carte par carte en face du
record. Pas de serveur : un fichier qu'on s'envoie.
"""

import shutil
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
from src.ui.page_course import nom_categorie
from src.ui.stats_widgets import _DISCRET, _Paragraphe, _texte
from src.ui.theme import RAYON_CARTE, themed
from src.ui.utils import BARRE_DEFILEMENT, open_local_path, open_url

_LARGEUR_TUILE = 360         # celle des tuiles des Défis et du Folio
_VERT = "#7be0a4"
_ROUGE = "#e07a6a"

_STYLE = f"""
QWidget#courses, QWidget#coursesCorps {{ background: transparent; }}
QScrollArea {{ background: transparent; border: none; }}
QFrame#courseGardee {{ background: #0d0d1a; border: 1px solid rgba(214, 167, 44, 0.12);
                       border-radius: {RAYON_CARTE}px; }}
QFrame#courseGardee[valable="true"] {{ border-color: rgba(214, 167, 44, 0.32); }}
QFrame#parCarte, QFrame#classement, QFrame#records, QFrame#comparaison {{ background: #0d0d1a;
                  border: 1px solid rgba(214, 167, 44, 0.12); border-radius: {RAYON_CARTE}px; }}
"""


def _documents() -> Path:
    dossier = Path.home() / "Documents"
    return dossier if dossier.is_dir() else Path.home()


class _Ligne(QFrame):
    """Une course : jour et code, statut ; le temps qui classe et l'autre ; « Ouvrir le dossier », « Supprimer »."""

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
        self.statut = _texte(statut, 12, "#d6a72c" if passee.valable else _ROUGE)
        self.statut.setWordWrap(True)
        gauche.addWidget(self.statut)
        h.addLayout(gauche, 1)
        temps = QVBoxLayout()
        temps.setSpacing(0)
        principal = _texte(course.format_temps(passee.temps(page.temps)), 18,
                           "#ffffff" if passee.valable else "#c9c7da")
        principal.setObjectName("tempsGarde")
        temps.addWidget(principal, alignment=Qt.AlignmentFlag.AlignRight)
        temps.addWidget(_texte(page.autre_temps(passee), 11, _DISCRET), alignment=Qt.AlignmentFlag.AlignRight)
        h.addLayout(temps)
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
        self.regles = game.course
        self.temps = self.regles.temps if self.regles is not None else course.SANS_CHARGEMENTS
        self._ordre = self.regles.idents if self.regles is not None else ()
        self.lignes: list[_Ligne] = []
        self.pastilles: dict[str, QPushButton] = {}
        self.passages: list[course.Passage] = []
        self.records: tuple[course.Passee, ...] = ()
        self.comparaison: tuple[course.Comparaison, ...] = ()
        self.bouton_livesplit: QPushButton | None = None
        self.bouton_partager: QPushButton | None = None
        self.bouton_comparer: QPushButton | None = None
        self.note_comparaison: QLabel | None = None
        self._ami: course.Externe | None = None
        self.classement = classement_
        self.places: list[classement.Entree] = []
        self.note_place: QLabel | None = None
        du_jeu = [c for c in gardees if c.jeu == game.id]
        # La page s'ouvre sur la catégorie de la course la plus récente (`passees` : la plus récente d'abord),
        # sans course sur la première du classement, sans classement sur la première du catalogue.
        classees = classement_.categories(game.id, self._ordre)
        self.categorie = (du_jeu[0].categorie if du_jeu else classees[0] if classees
                          else self._ordre[0] if self._ordre else course.ANY)
        self._passees: list[course.Passee] = []
        # Une course effacée : le Carnet relit sa liste quand il retire la page.
        self.modifiee = False
        self._racine = QVBoxLayout(self)
        self._racine.setContentsMargins(0, 0, 0, 0)
        self._remplir(du_jeu)

    def autre_temps(self, c: course.Passee) -> str:
        """Le temps qui ne classe pas le jeu, dit avec son nom."""
        if self.temps == course.REEL:
            return tr("{} sans chargements").format(course.format_temps(c.net_us))
        return tr("{} en temps réel").format(course.format_temps(c.total_us))

    def _presentes(self, passees: list[course.Passee]) -> list[str]:
        """Les catégories qui ont une course ou un classé, dans l'ordre du catalogue, puis les autres."""
        noms = set(self.classement.categories(self.game.id, self._ordre)) | {p.categorie for p in passees}
        return sorted(noms, key=lambda c: (self._ordre.index(c) if c in self._ordre else len(self._ordre), c))

    def _remplir(self, passees: list[course.Passee]) -> None:
        self._passees = passees
        presentes = self._presentes(passees)
        if self.categorie not in presentes and presentes:
            # la catégorie choisie n'a plus de course (suppression)
            self.categorie = passees[0].categorie if passees else presentes[0]
        passees = [p for p in passees if p.categorie == self.categorie]
        self.lignes, self.pastilles, self.passages, self.places = [], {}, [], []
        self.records, self.comparaison = (), ()
        self.note_place = self.note_comparaison = None
        self.bouton_livesplit = self.bouton_partager = self.bouton_comparer = None
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
        record = course.meilleure(passees, self.categorie, self.temps)
        if passees:
            self._mes_courses(lay, passees, record)
        else:
            lay.addWidget(_texte(tr("Aucune course gardée en {}.").format(self._nom(self.categorie)), 14, _DISCRET))
        self._classement(lay, record)
        lay.addStretch()

    def _nom(self, ident: str) -> str:
        return nom_categorie(self.regles, ident)

    def _mes_courses(self, lay: QVBoxLayout, passees: list[course.Passee], record: course.Passee | None) -> None:
        """Le record et ses gestes, la course idéale, les records successifs, les courses gardées, le meilleur
        passage par carte, la comparaison avec un ami."""
        haut = QHBoxLayout()
        tuile = _tuile(course.format_temps(record.temps(self.temps)) if record is not None else "—",
                       (tr("Meilleur temps valable") if record is not None else tr("Aucun temps valable"))
                       + " · " + self._nom(self.categorie))
        tuile.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        tuile.setMaximumWidth(_LARGEUR_TUILE)
        haut.addWidget(tuile)
        gestes = QVBoxLayout()
        gestes.setSpacing(4)
        if record is not None:
            self.bouton_partager = lien(tr("Partager mon record"), discret=True)
            self.bouton_partager.setToolTip(tr("Une copie de son journal signé (course.json), pour un ami ou le "
                                               "Discord."))
            self.bouton_partager.clicked.connect(lambda: self.partager(record))
            gestes.addWidget(self.bouton_partager)
            if record.segments:
                self.bouton_livesplit = lien(tr("Exporter pour LiveSplit"), discret=True)
                self.bouton_livesplit.setToolTip(tr("Le meilleur temps de la catégorie, découpé par carte, en "
                                                    "fichier de découpage LiveSplit (.lss)."))
                self.bouton_livesplit.clicked.connect(self.exporter_livesplit)
                gestes.addWidget(self.bouton_livesplit)
                self.bouton_comparer = lien(tr("Comparer à la course d'un ami"), discret=True)
                self.bouton_comparer.setToolTip(tr("Ouvrez le course.json qu'il vous a envoyé : il est vérifié, "
                                                   "puis mis carte par carte en face de votre record."))
                self.bouton_comparer.clicked.connect(lambda: self.comparer(record))
                gestes.addWidget(self.bouton_comparer)
        haut.addSpacing(18)
        haut.addLayout(gestes)
        haut.addStretch()
        lay.addLayout(haut)
        if record is not None:
            lay.addWidget(_texte(self.autre_temps(record) + " · " + record.jour, 12, _DISCRET))
            ideale = course.ideale(passees, self.categorie, self.temps)
            if ideale is not None and ideale.a_gagner_us > 0:
                lay.addWidget(_texte(tr("Course idéale : {} sans chargements, encore {} à gagner.").format(
                    course.format_temps(ideale.net_us), course.format_temps(ideale.a_gagner_us)), 12, _DISCRET))
        if self._ami is not None and record is not None:
            self._comparaison(lay, record, self._ami)
        self.records = course.records(passees, self.categorie, self.temps)
        if len(self.records) > 1:
            lay.addSpacing(14)
            lay.addWidget(_texte(tr("Records successifs"), 14, "#d6a72c"))
            lay.addWidget(self._records(self.records))
        lay.addSpacing(10)
        valables = sum(p.valable for p in passees)
        lay.addWidget(_texte(trn(len(passees), "{} essai", "{} essais").format(len(passees)) + " · "
                             + trn(valables, "{} valable", "{} valables").format(valables), 12, _DISCRET))
        lay.addSpacing(6)
        for passee in passees:
            ligne = _Ligne(passee, self)
            lay.addWidget(ligne)
            self.lignes.append(ligne)
        self.passages = list(course.par_carte(passees, self.categorie, self.temps))
        if self.passages:
            lay.addSpacing(18)
            lay.addWidget(_texte(tr("Meilleur passage par carte"), 14, "#d6a72c"))
            lay.addWidget(_texte(tr("Pris dans les courses valables, sans les chargements ; une carte rechargée ne "
                                    "compte pas."), 12, _DISCRET))
            lay.addWidget(self._par_carte(self.passages))

    def _records(self, suite: tuple[course.Passee, ...]) -> QFrame:
        """Chaque record battu, du premier au dernier : le jour, le temps, ce qu'il a gagné sur le précédent."""
        cadre = QFrame()
        cadre.setObjectName("records")
        grille = QGridLayout(cadre)
        grille.setContentsMargins(16, 10, 16, 10)
        grille.setHorizontalSpacing(14)
        grille.setVerticalSpacing(4)
        grille.setColumnStretch(0, 1)
        droite = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        for i, c in enumerate(suite):
            grille.addWidget(_texte(f"{c.jour} · {c.code}", 12, "#e0e0f0"), i, 0)
            grille.addWidget(_texte(course.format_temps(c.temps(self.temps)), 12, "#ffffff"), i, 1, droite)
            if i:
                gain = c.temps(self.temps) - suite[i - 1].temps(self.temps)
                grille.addWidget(_texte(course.format_ecart(gain), 12, _VERT), i, 2, droite)
        return cadre

    def _comparaison(self, lay: QVBoxLayout, record: course.Passee, ami: course.Externe) -> None:
        """La course de l'ami en face du record : ses deux temps, ce que vaut son fichier, carte par carte."""
        lay.addSpacing(14)
        a = ami.passee
        lay.addWidget(_texte(tr("Comparaison avec la course {} du {}").format(a.code, a.jour), 14, "#d6a72c"))
        ecart = a.temps(self.temps) - record.temps(self.temps)
        phrase = tr("Son temps : {} ({} par rapport au vôtre).").format(course.format_temps(a.temps(self.temps)),
                                                                        course.format_ecart(ecart))
        valeur = (tr("Fichier signé, temps recalculé valable.") if ami.en_regle
                  else tr("Attention : fichier non signé, retouché, ou temps refusé."))
        self.note_comparaison = _texte(phrase + " " + valeur, 12, "#e0e0f0" if ami.en_regle else _ROUGE)
        self.note_comparaison.setWordWrap(True)
        lay.addWidget(self.note_comparaison)
        self.comparaison = course.comparer(record, a)
        if not self.comparaison:
            return
        cadre = QFrame()
        cadre.setObjectName("comparaison")
        grille = QGridLayout(cadre)
        grille.setContentsMargins(16, 10, 16, 10)
        grille.setHorizontalSpacing(14)
        grille.setVerticalSpacing(4)
        grille.setColumnStretch(0, 1)
        droite = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        for col, titre in enumerate((tr("Carte"), tr("Vous"), tr("Votre ami"), tr("Écart"))):
            grille.addWidget(_texte(titre, 11, _DISCRET), 0, col, droite if col else Qt.AlignmentFlag.AlignLeft)
        for i, c in enumerate(self.comparaison, start=1):
            grille.addWidget(_texte(c.carte, 12, "#e0e0f0"), i, 0)
            for col, us in ((1, c.a_us), (2, c.b_us)):
                grille.addWidget(_texte(course.format_temps(us) if us is not None else "—", 12, "#ffffff"),
                                 i, col, droite)
            if (e := c.ecart_us) is not None:
                encre = _VERT if e > 0 else _ROUGE if e < 0 else _DISCRET
                grille.addWidget(_texte(course.format_ecart(e), 12, encre), i, 3, droite)
        lay.addWidget(cadre)

    def _classement(self, lay: QVBoxLayout, record: course.Passee | None) -> None:
        """Le classement Accio de la catégorie, la place qu'y prendrait le record, comment y entrer."""
        self.places = list(self.classement.de(self.game.id, self.categorie))
        lay.addSpacing(18)
        lay.addWidget(_texte(tr("Classement Accio") + " · " + self._nom(self.categorie), 14, "#d6a72c"))
        if self.places:
            lay.addWidget(self._grille(self.places))
        else:
            lay.addWidget(_texte(tr("Personne n'y est encore classé."), 12, _DISCRET))
        if record is not None and record.code not in {e.code for e in self.places}:
            place = classement.rang(tuple(self.places), record.temps(self.temps))
            self.note_place = _texte(tr("Votre record ({}) y prendrait la place {}.").format(
                course.format_temps(record.temps(self.temps)), place), 12, "#e0e0f0")
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
            grille.addWidget(_texte(course.format_temps(e.temps_us), 12, "#ffffff"), i, 3, droite)
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
        for ident in presentes:
            b = filtre(self._nom(ident))
            b.setChecked(ident == self.categorie)
            b.clicked.connect(lambda _c=False, n=ident: self.montrer_categorie(n))
            groupe.addButton(b)
            self.pastilles[ident] = b
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

    # ── Gestes ──

    def _ou_ecrire(self, titre: str, nom: str, motif: str, extension: str) -> Path | None:
        cible, _filtre = QFileDialog.getSaveFileName(self, titre, str(_documents() / nom), motif)
        if not cible:
            return None
        destination = Path(cible)
        return destination if destination.suffix.lower() == extension else destination.with_name(
            destination.name + extension)

    def exporter_livesplit(self) -> None:
        """Le .lss de la catégorie (`course.livesplit`), là où le joueur le veut (Documents d'abord)."""
        texte = course.livesplit(self.game.name, self.categorie, self._passees, self.temps)
        if texte is None:
            return
        destination = self._ou_ecrire(tr("Exporter pour LiveSplit"),
                                      nom_de_fichier(f"{self.game.name} - {self.categorie}") + ".lss",
                                      tr("Découpage LiveSplit (*.lss)"), ".lss")
        if destination is None:
            return
        try:
            ecrire_atomique(destination, texte)
        except OSError:
            message(self, QMessageBox.Icon.Warning, tr("Exporter pour LiveSplit"),
                    tr("Le fichier n'a pas pu être écrit à cet endroit."))

    def partager(self, record: course.Passee) -> None:
        """Une copie du `course.json` du record, telle quelle (sa signature reste bonne), là où le joueur veut."""
        destination = self._ou_ecrire(
            tr("Partager mon record"),
            nom_de_fichier(f"{self.game.name} - {self.categorie} - {record.code}") + ".json",
            tr("Journal de course (*.json)"), ".json")
        if destination is None:
            return
        try:
            shutil.copyfile(course.dossier(record.code) / course.JOURNAL, destination)
        except OSError:
            message(self, QMessageBox.Icon.Warning, tr("Partager mon record"),
                    tr("Le fichier n'a pas pu être écrit à cet endroit."))

    def comparer(self, record: course.Passee) -> None:
        """Lit le `course.json` d'un ami, le vérifie, et le met en face du record (même jeu, même catégorie)."""
        chemin, _filtre = QFileDialog.getOpenFileName(self, tr("Comparer à la course d'un ami"), str(_documents()),
                                                      tr("Journal de course (*.json)"))
        if not chemin:
            return
        ami = course.lire_externe(Path(chemin))
        if ami is None:
            refus = tr("Ce fichier n'est pas le journal d'une course Accio.")
        elif ami.passee.jeu != self.game.id or ami.passee.categorie != self.categorie:
            refus = tr("Cette course n'est pas une course de {} en {}.").format(self.game.name,
                                                                              self._nom(self.categorie))
        else:
            refus = ""
        if refus:
            message(self, QMessageBox.Icon.Warning, tr("Comparer à la course d'un ami"), refus)
            return
        self._ami = ami
        self._rebatir(self._passees)

    def montrer_categorie(self, categorie: str) -> None:
        """Redessine la page sur la catégorie choisie, sans relire les courses."""
        if categorie != self.categorie:
            self.categorie = categorie
            self._ami = None
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
                passee.code, passee.jour, course.format_temps(passee.temps(self.temps))) + "\n\n"
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
