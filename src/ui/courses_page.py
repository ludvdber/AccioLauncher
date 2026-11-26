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

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
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
    QVBoxLayout,
    QWidget,
)

from src.core import classement, course, mode_course
from src.core.ecriture_atomique import ecrire_atomique
from src.core.formatting import format_duree_compacte
from src.core.game_data import GameData
from src.core.i18n import tr, trn
from src.core.liens import DISCORD_URL
from src.core.phonographe import nom_de_fichier
from src.ui import course_visuel as visuel
from src.ui.composants import feuille_de_style, filtre, lien, police, surtitre
from src.ui.course_ui import raison
from src.ui.fenetre_message import message
from src.ui.page_course import nom_categorie
from src.ui.theme import themed
from src.ui.utils import BARRE_DEFILEMENT, open_local_path, open_url

_STYLE = """
QWidget#courses, QWidget#coursesCorps { background: transparent; }
QScrollArea { background: transparent; border: none; }
QFrame#courseGardee { background: #0d0d1a; border: 1px solid #1b1b33; border-radius: 6px; }
QFrame#listeCourse { background: #0d0d1a; border: 1px solid #1b1b33; border-radius: 8px; }
QFrame#ligneListe { background: transparent; border: none; border-bottom: 1px solid #16162c; }
"""


def _documents() -> Path:
    dossier = Path.home() / "Documents"
    return dossier if dossier.is_dir() else Path.home()


class _Ligne(QFrame):
    """Une course : le temps qui classe et le jour, son statut, « Ouvrir le dossier », « Supprimer »."""

    def __init__(self, passee: course.Passee, page: CoursesPage, *, record: bool) -> None:
        super().__init__()
        self.setObjectName("courseGardee")
        self.code = passee.code
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(4)
        haut = QHBoxLayout()
        principal = visuel.temps(course.format_temps(passee.temps(page.temps)), 17, visuel.CREME)
        principal.setObjectName("tempsGarde")
        principal.setToolTip(page.autre_temps(passee))
        haut.addWidget(principal)
        haut.addStretch()
        jour = visuel.libelle(f"{passee.jour} · {passee.code}", 13, visuel.GRIS)
        haut.addWidget(jour)
        v.addLayout(haut)
        if passee.valable:
            statut = tr("Temps valable · record") if record else tr("Temps valable")
        else:
            statut = raison(passee.refus[0]) if passee.refus else raison(course.SANS_FIN)
        self.statut = visuel.libelle(statut, 13, visuel.VERT if passee.valable else visuel.ROUGE, retour=True)
        v.addWidget(self.statut)
        gestes = QHBoxLayout()
        gestes.setSpacing(16)
        dossier = visuel.lien_or(tr("Ouvrir le dossier"))
        dossier.setFont(police(13))
        dossier.clicked.connect(lambda: open_local_path(str(course.dossier(passee.code))))
        gestes.addWidget(dossier)
        self.bouton_supprimer = lien(tr("Supprimer"), discret=True)
        self.bouton_supprimer.clicked.connect(lambda: page.supprimer(passee))
        gestes.addWidget(self.bouton_supprimer)
        gestes.addStretch()
        v.addLayout(gestes)


class _Records(QWidget):
    """La courbe des records successifs : le premier en haut à gauche, le dernier en bas à droite (plus bas =
    plus rapide), un point or sur le record actuel."""

    def __init__(self, temps_us: list[int]) -> None:
        super().__init__()
        self._temps = temps_us
        self.setFixedHeight(54)
        self.setMinimumWidth(120)

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt)
        if len(self._temps) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        haut, bas = 8.0, float(self.height() - 8)
        gauche, droite = 6.0, float(self.width() - 6)
        lent, vite = max(self._temps), min(self._temps)
        etendue = max(1, lent - vite)
        pas = (droite - gauche) / (len(self._temps) - 1)
        points = [QPointF(gauche + i * pas, haut + (lent - t) / etendue * (bas - haut))
                  for i, t in enumerate(self._temps)]
        p.setPen(QPen(QColor(visuel.OR), 2))
        p.drawPolyline(points)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(visuel.OR_CLAIR))
        p.drawEllipse(points[-1], 4, 4)
        p.end()


class CoursesPage(QWidget):
    """Les courses gardées d'un jeu et son classement Accio, en trois colonnes (maquette « Carnet, rubrique
    Courses ») : le record et les courses ; le meilleur passage par carte ; le classement."""

    def __init__(self, game: GameData, gardees: list[course.Passee],
                 classement_: classement.Classement = classement.VIDE, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("courses")
        self.setStyleSheet(themed(_STYLE) + feuille_de_style() + visuel.STYLE)
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
        """Les catégories du catalogue, puis celles qui ont une course ou un classé sans y être."""
        noms = set(self._ordre) | set(self.classement.categories(self.game.id, self._ordre)) | {
            p.categorie for p in passees}
        return sorted(noms, key=lambda c: (self._ordre.index(c) if c in self._ordre else len(self._ordre), c))

    def _remplir(self, passees: list[course.Passee]) -> None:
        self._passees = passees
        presentes = self._presentes(passees)
        if self.categorie not in presentes and presentes:
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
        zone.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        corps = QWidget()
        corps.setObjectName("coursesCorps")
        colonnes = QHBoxLayout(corps)
        colonnes.setContentsMargins(40, 28, 40, 40)
        colonnes.setSpacing(28)
        zone.setWidget(corps)
        self._racine.addWidget(zone)
        record = course.meilleure(passees, self.categorie, self.temps)
        une, deux, trois = (QVBoxLayout() for _ in range(3))
        for col, part in ((une, 105), (deux, 100), (trois, 100)):
            col.setSpacing(12)
            colonnes.addLayout(col, part)
        une.addWidget(visuel.grand_titre(self.game.name, 22))
        if len(presentes) > 1:
            une.addLayout(self._choix(presentes))
        if passees:
            self._mes_courses(une, passees, record)
            self._par_carte_et_ami(deux, passees, record)
        else:
            une.addWidget(visuel.libelle(tr("Aucune course gardée en {}.").format(self._nom(self.categorie)), 14,
                                         visuel.GRIS, retour=True))
        self._classement(trois, record)
        for col in (une, deux, trois):
            col.addStretch()

    def _nom(self, ident: str) -> str:
        return nom_categorie(self.regles, ident)

    def _surtitre(self, lay: QVBoxLayout, contenu: str) -> None:
        lay.addSpacing(6)
        lay.addWidget(surtitre(contenu))

    def _mes_courses(self, lay: QVBoxLayout, passees: list[course.Passee], record: course.Passee | None) -> None:
        """Le record dans son cadre or (l'autre temps, la course idéale, les essais, le temps passé en course,
        la courbe des records successifs, les gestes), puis chaque course gardée."""
        cadre, v = visuel.cadre("panneauOr", (20, 18, 20, 18), 8)
        if record is not None:
            entete = tr("Meilleur temps valable")
            place = self._place_du_record(record)
            if place is not None:
                entete += " · " + tr("place {} du classement Accio").format(place)
            v.addWidget(visuel.libelle(entete, 14, "#b9b9d0"))
            v.addWidget(visuel.temps(course.format_temps(record.temps(self.temps)), 36, visuel.OR_CLAIR))
            v.addWidget(visuel.libelle(f"{record.jour} · {self.autre_temps(record)}", 13, visuel.GRIS))
        else:
            v.addWidget(visuel.libelle(tr("Aucun temps valable"), 14, "#b9b9d0"))
            v.addWidget(visuel.temps("—", 36, visuel.GRIS))
        ideale = course.ideale(passees, self.categorie, self.temps)
        finis = sum(p.fin for p in passees)
        chiffres = QGridLayout()
        chiffres.setHorizontalSpacing(8)
        for col, (titre, valeur, est_temps) in enumerate((
                (tr("Course idéale"), course.format_temps(ideale.temps_us) if ideale is not None else "—", True),
                (tr("Essais"), trn(len(passees), "{} essai", "{} essais").format(len(passees)) + " · "
                 + trn(finis, "{} finie", "{} finies").format(finis), False),
                (tr("Temps passé en course"),
                 format_duree_compacte(sum(p.total_us for p in passees) // 1_000_000), False))):
            chiffres.addWidget(visuel.libelle(titre, 12, visuel.GRIS), 0, col)
            chiffres.addWidget(visuel.temps(valeur, 15) if est_temps else visuel.libelle(valeur, 15, visuel.CREME),
                               1, col)
            chiffres.setColumnStretch(col, 1)
        v.addSpacing(4)
        v.addLayout(chiffres)
        self.records = course.records(passees, self.categorie, self.temps)
        if len(self.records) > 1:
            suite = [c.temps(self.temps) for c in self.records]
            courbe = _Records(suite)
            phrase = tr("Records successifs : de {} à {} en {} records.").format(
                course.format_temps(suite[0]), course.format_temps(suite[-1]), len(suite))
            courbe.setAccessibleName(phrase)
            courbe.setToolTip("\n".join(f"{c.jour} · {course.format_temps(c.temps(self.temps))}"
                                        for c in self.records))
            v.addSpacing(4)
            v.addWidget(courbe)
            v.addWidget(visuel.libelle(phrase, 12, visuel.GRIS, retour=True))
        if record is not None:
            gestes = QHBoxLayout()
            gestes.setSpacing(16)
            self.bouton_partager = visuel.lien_or(tr("Partager mon record"))
            self.bouton_partager.setToolTip(tr("Une copie de son journal signé (course.json), pour un ami ou le "
                                               "Discord."))
            self.bouton_partager.clicked.connect(lambda: self.partager(record))
            gestes.addWidget(self.bouton_partager)
            if record.segments:
                self.bouton_livesplit = visuel.lien_or(tr("Exporter pour LiveSplit"))
                self.bouton_livesplit.setToolTip(tr("Le meilleur temps de la catégorie, découpé par carte, en "
                                                    "fichier de découpage LiveSplit (.lss)."))
                self.bouton_livesplit.clicked.connect(self.exporter_livesplit)
                gestes.addWidget(self.bouton_livesplit)
                self.bouton_comparer = visuel.lien_or(tr("Comparer à la course d'un ami"))
                self.bouton_comparer.setToolTip(tr("Ouvrez le course.json qu'il vous a envoyé : il est vérifié, "
                                                   "puis mis carte par carte en face de votre record."))
                self.bouton_comparer.clicked.connect(lambda: self.comparer(record))
                gestes.addWidget(self.bouton_comparer)
            gestes.addStretch()
            v.addSpacing(4)
            v.addLayout(gestes)
        lay.addWidget(cadre)
        self._surtitre(lay, tr("Vos courses"))
        for passee in passees:
            ligne = _Ligne(passee, self, record=record is not None and passee.code == record.code)
            lay.addWidget(ligne)
            self.lignes.append(ligne)

    def _par_carte_et_ami(self, lay: QVBoxLayout, passees: list[course.Passee],
                          record: course.Passee | None) -> None:
        """Le meilleur passage par carte et leur somme ; la comparaison avec un ami, quand il y en a une."""
        self.passages = list(course.par_carte(passees, self.categorie, self.temps))
        if self.passages:
            self._surtitre(lay, tr("Meilleur passage par carte"))
            lay.addWidget(visuel.libelle(tr("Pris dans les courses valables, sans les chargements ; une carte "
                                            "rechargée ne compte pas."), 13, visuel.GRIS, retour=True))
            liste, v = visuel.cadre("listeCourse", (16, 6, 16, 6), 0)
            for s in self.passages:
                ligne = self._ligne_liste(s.carte, course.format_temps(s.net_us))
                ligne.setToolTip(f"{s.jour} · {s.code}")
                v.addWidget(ligne)
            ideale = course.ideale(passees, self.categorie, self.temps)
            if ideale is not None:
                v.addWidget(self._ligne_liste(tr("Course idéale (vos meilleurs passages bout à bout)"),
                                              course.format_temps(ideale.net_us), or_=True))
            lay.addWidget(liste)
        if self._ami is not None and record is not None:
            self._comparaison(lay, record, self._ami)

    @staticmethod
    def _ligne_liste(gauche: str, droite: str, *, or_: bool = False) -> QFrame:
        ligne, h = visuel.cadre("ligneListe" if not or_ else "ligneFin", (0, 9, 0, 9), 12, horizontal=True)
        h.addWidget(visuel.libelle(gauche, 14, "#b9b9d0" if or_ else "#e0e0f0", retour=True), 1)
        h.addWidget(visuel.temps(droite, 14, visuel.OR_CLAIR if or_ else visuel.CREME))
        return ligne

    def _comparaison(self, lay: QVBoxLayout, record: course.Passee, ami: course.Externe) -> None:
        """La course de l'ami en face du record : ses deux temps, ce que vaut son fichier, carte par carte."""
        a = ami.passee
        self._surtitre(lay, tr("Comparaison avec la course {} du {}").format(a.code, a.jour))
        ecart = a.temps(self.temps) - record.temps(self.temps)
        phrase = tr("Son temps : {} ({} par rapport au vôtre).").format(course.format_temps(a.temps(self.temps)),
                                                                        course.format_ecart(ecart))
        valeur = (tr("Fichier signé, temps recalculé valable.") if ami.en_regle
                  else tr("Attention : fichier non signé, retouché, ou temps refusé."))
        self.note_comparaison = visuel.libelle(phrase + " " + valeur, 13,
                                               "#e0e0f0" if ami.en_regle else visuel.ROUGE, retour=True)
        lay.addWidget(self.note_comparaison)
        self.comparaison = course.comparer(record, a)
        if not self.comparaison:
            return
        cadre, _v = visuel.cadre("listeCourse", (16, 10, 16, 10), 0)
        grille = QGridLayout()
        _v.addLayout(grille)
        grille.setHorizontalSpacing(14)
        grille.setVerticalSpacing(6)
        grille.setColumnStretch(0, 1)
        droite = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        for col, titre in enumerate((tr("Carte"), tr("Vous"), tr("Votre ami"), tr("Écart"))):
            grille.addWidget(visuel.libelle(titre, 12, visuel.GRIS), 0, col,
                             droite if col else Qt.AlignmentFlag.AlignLeft)
        for i, c in enumerate(self.comparaison, start=1):
            grille.addWidget(visuel.libelle(c.carte, 13, "#e0e0f0"), i, 0)
            for col, us in ((1, c.a_us), (2, c.b_us)):
                grille.addWidget(visuel.temps(course.format_temps(us) if us is not None else "—", 13), i, col,
                                 droite)
            if (e := c.ecart_us) is not None:
                encre = visuel.VERT if e > 0 else visuel.ROUGE if e < 0 else visuel.GRIS
                grille.addWidget(visuel.temps(course.format_ecart(e), 13, encre), i, 3, droite)
        lay.addWidget(cadre)

    def _place_du_record(self, record: course.Passee) -> int | None:
        """La place du record au classement : la sienne s'il y est, celle qu'il prendrait sinon."""
        places = list(self.classement.de(self.game.id, self.categorie))
        if not places:
            return None
        codes = [e.code for e in places]
        if record.code in codes:
            return codes.index(record.code) + 1
        return classement.rang(tuple(places), record.temps(self.temps))

    def _classement(self, lay: QVBoxLayout, record: course.Passee | None) -> None:
        """Le classement Accio de la catégorie, la place qu'y prendrait le record, comment y entrer."""
        self.places = list(self.classement.de(self.game.id, self.categorie))
        lay.addSpacing(36)
        lay.addWidget(surtitre(tr("Classement Accio") + " · " + self._nom(self.categorie)))
        if self.places:
            liste, v = visuel.cadre("listeCourse", (16, 6, 16, 6), 0)
            for i, e in enumerate(self.places):
                video = None
                if e.video:
                    video = visuel.lien_or(tr("Vidéo"))
                    video.setFont(police(13))
                    video.setToolTip(e.video)
                    video.clicked.connect(lambda _c=False, u=e.video: open_url(u))
                ligne = visuel.ligne_classee(i + 1, e.joueur, course.format_temps(e.temps_us), apres=video)
                ligne.setToolTip(" · ".join(x for x in (e.jour, e.code) if x))
                v.addWidget(ligne)
            lay.addWidget(liste)
        else:
            lay.addWidget(visuel.libelle(tr("Personne n'est encore classé en {}.").format(self._nom(self.categorie)),
                                         14, visuel.CREME, retour=True))
        boite, v = visuel.cadre("placeCourse", (16, 14, 16, 14), 8)
        if record is not None and record.code not in {e.code for e in self.places}:
            temps = record.temps(self.temps)
            place = classement.rang(tuple(self.places), temps)
            self.note_place = visuel.libelle(tr("Votre record ({}) y prendrait la place {}.").format(
                course.format_temps(temps), place), 14, visuel.CREME, retour=True)
            v.addWidget(self.note_place)
            if place > 1:
                v.addWidget(visuel.libelle(tr("À {} de la place {}.").format(
                    course.format_temps(temps - self.places[place - 2].temps_us), place - 1), 13, "#b9b9d0"))
        v.addWidget(visuel.libelle(tr("Pour y entrer, publiez la vidéo de la course et son course.json sur le "
                                      "Discord : une fois validée, elle apparaît ici."), 13, "#b9b9d0", retour=True))
        discord = visuel.lien_or(tr("Ouvrir le Discord"))
        discord.clicked.connect(lambda: open_url(DISCORD_URL))
        v.addWidget(discord)
        lay.addWidget(boite)
        if self.regles is not None and self.regles.speedrun:
            source = visuel.lien_or(tr("Les records du jeu d'origine sur speedrun.com ›"))
            source.setFont(police(13))
            adresse = f"https://www.speedrun.com/{self.regles.speedrun}"
            source.setToolTip(adresse)
            source.clicked.connect(lambda: open_url(adresse))
            lay.addWidget(source)

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
