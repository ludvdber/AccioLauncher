"""Les sauvegardes d'un jeu : revenir à une version, exporter, importer.

Une liste par sauvegarde, la plus récente en haut, datée par le JEU (le
moment où il a écrit cette version, pas celui de la copie) : c'est ce dont
on se souvient — « hier soir, avant le boss ». Remettre une version demande
une confirmation qui dit ce qui se passe pour l'état actuel : il est copié
d'abord, on peut donc y revenir de la même façon.

En tête de liste, la sauvegarde telle qu'elle est maintenant : c'est celle
qu'on exporte le plus souvent (`partage_sauvegardes`, Ludo 2026-10-26 :
« exportables en .zip et importation zip et sans zip aussi »). Importer
remplace un emplacement après l'avoir copié, ou en remplit un libre.
"""

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QDate, QLocale, Qt, QTime
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core import copies_sauvegardes, partage_sauvegardes, sauvegardes
from src.core.config import APP_VERSION
from src.core.game_data import GameData
from src.core.i18n import get_language, tr
from src.core.phonographe import nom_de_fichier
from src.ui.fonts import body_font, cinzel
from src.ui.settings_panel import _COMBO_STYLE
from src.ui.theme import themed
from src.ui.fenetre_message import message
from src.ui.utils import liste_deroulante, open_local_path

_LISTE_STYLE = (
    "QListWidget { color: #e0e0f0; background: #141428; border: 1px solid #2a2a48;"
    " font-size: 13px; outline: none; }"
    "QListWidget::item { padding: 6px 8px; }"
    "QListWidget::item:selected { color: #0d0d1a; background: #d6a72c; }"
)

# La ligne « telle qu'elle est maintenant », en tête de liste.
_ACTUELLE = "actuelle"


def _taille(octets: int) -> str:
    """Les copies font de 2 Ko (HP5) à 3 Mo (HP3) : le Ko compte ici."""
    if octets >= 1024 * 1024:
        mo = QLocale(get_language()).toString(octets / (1024 * 1024), "f", 1)
        return f"{mo} {tr('Mo')}"
    return f"{max(1, round(octets / 1024))} {tr('Ko')}"


def _quand(moment) -> str:
    """« jeudi 1 octobre 2026, 20:15 » dans la langue de l'interface.

    Date LONGUE et heure COURTE : un `datetime` passé tel quel à `QLocale`
    devient une date sans heure, et deux versions du même soir se confondaient.
    """
    locale = QLocale(get_language())
    return f"{locale.toString(QDate(moment.year, moment.month, moment.day), QLocale.FormatType.LongFormat)}, {locale.toString(QTime(moment.hour, moment.minute), QLocale.FormatType.ShortFormat)}"


def _refus(code: str) -> str:
    """Ce qu'on dit quand un fichier ne s'importe pas (`partage_sauvegardes`)."""
    return {
        partage_sauvegardes.AUTRE_JEU: tr("Cette sauvegarde vient d'un autre jeu."),
        partage_sauvegardes.SANS_SAUVEGARDE: tr("Ce fichier ne contient pas de sauvegarde de ce jeu."),
        partage_sauvegardes.PLUSIEURS: tr("Ce .zip contient plusieurs sauvegardes : gardez-en une seule "
                                          "par fichier."),
        partage_sauvegardes.TROP_GROS: tr("Ce fichier est bien trop gros pour une sauvegarde."),
    }.get(code, tr("Ce fichier n'a pas pu être lu."))


class _ChoixEmplacement(QDialog):
    """Où poser la partie importée : un emplacement libre d'abord."""

    def __init__(self, noms: list[tuple[str, str, bool]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Importer dans quel emplacement ?"))
        self.setStyleSheet(themed(
            "QDialog { background: #0d0d1a; border: 1px solid rgba(214,167,44,0.3); }"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(10)
        texte = QLabel(tr("Choisissez l'emplacement où la partie apparaîtra dans le menu du jeu."))
        texte.setFont(body_font(11))
        texte.setWordWrap(True)
        texte.setStyleSheet("color: #e0e0f0; background: transparent;")
        layout.addWidget(texte)
        self.choix = liste_deroulante()
        self.choix.setStyleSheet(themed(_COMBO_STYLE))
        for rel, nom, pris in noms:
            self.choix.addItem(tr("{} (remplacer la partie)").format(nom) if pris
                               else tr("{} (libre)").format(nom), rel)
        libres = [i for i, (_r, _n, pris) in enumerate(noms) if not pris]
        self.choix.setCurrentIndex(libres[0] if libres else 0)
        layout.addWidget(self.choix)
        pied = QHBoxLayout()
        pied.addStretch()
        ok = QPushButton(tr("Importer"))
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.clicked.connect(self.accept)
        annuler = QPushButton(tr("Annuler"))
        annuler.setCursor(Qt.CursorShape.PointingHandCursor)
        annuler.clicked.connect(self.reject)
        pied.addWidget(ok)
        pied.addWidget(annuler)
        layout.addLayout(pied)


class CopiesDialog(QDialog):
    """Les sauvegardes d'un jeu : versions, « Remettre cette version », export, import."""

    def __init__(self, game: GameData, partie_en_cours=lambda: "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.game = game
        # () -> str : le nom du jeu qui tourne, vide sinon. Remettre une
        # sauvegarde sous un jeu ouvert : il la réécrirait en quittant.
        self._partie_en_cours = partie_en_cours
        self._versions: dict[str, list[copies_sauvegardes.Version]] = {}
        self._presents: dict[str, Path] = {}
        self.setWindowTitle(tr("Sauvegardes : {}").format(game.name))
        self.setMinimumSize(560, 460)
        self.setStyleSheet(themed(
            "QDialog { background: #0d0d1a; border: 1px solid rgba(214,167,44,0.3); }"))
        self._build_ui()
        self._recharger()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(10)
        titre = QLabel(tr("Sauvegardes : {}").format(self.game.name))
        titre.setFont(cinzel(14, bold=True))
        titre.setTextFormat(Qt.TextFormat.PlainText)      # nom du CATALOGUE
        titre.setWordWrap(True)
        titre.setStyleSheet(themed("color: #d6a72c; background: transparent;"))
        layout.addWidget(titre)
        note = QLabel(tr(
            "Avant chaque partie, le lanceur garde une copie de chaque sauvegarde qui a changé. "
            "Les dates sont celles où le jeu a écrit chaque version. Une sauvegarde s'exporte en .zip "
            "pour la garder ou la partager, et s'importe depuis un .zip ou le fichier seul."))
        note.setFont(body_font(11))
        note.setWordWrap(True)
        note.setStyleSheet("color: #8a8aaa; background: transparent;")
        layout.addWidget(note)

        self._choix = liste_deroulante()
        self._choix.setStyleSheet(themed(_COMBO_STYLE))
        self._choix.currentIndexChanged.connect(self._montrer)
        layout.addWidget(self._choix)
        self._liste = QListWidget()
        self._liste.setStyleSheet(themed(_LISTE_STYLE))
        self._liste.currentRowChanged.connect(self._maj_bouton)
        self._liste.itemActivated.connect(lambda _i: self._remettre())
        layout.addWidget(self._liste, 1)
        self._total = QLabel("")
        self._total.setFont(body_font(10))
        self._total.setStyleSheet("color: #8a8aaa; background: transparent;")
        # Le dossier des copies sur la ligne du total, en lien : cinq boutons au
        # pied ne tenaient pas à 640 px (aperçu du 2026-10-26).
        ligne = QHBoxLayout()
        ligne.addWidget(self._total)
        ligne.addStretch()
        dossier = QPushButton(tr("Ouvrir le dossier des copies"))
        dossier.setFlat(True)
        dossier.setFont(body_font(10))
        dossier.setStyleSheet(themed("QPushButton { color: #d6a72c; background: transparent; border: none;"
                                     " text-decoration: underline; padding: 0; }"))
        dossier.setCursor(Qt.CursorShape.PointingHandCursor)
        dossier.clicked.connect(self._ouvrir_dossier)
        ligne.addWidget(dossier)
        layout.addLayout(ligne)

        pied = QHBoxLayout()
        self._importer_bouton = QPushButton(tr("Importer…"))
        self._importer_bouton.setCursor(Qt.CursorShape.PointingHandCursor)
        self._importer_bouton.clicked.connect(self._importer)
        pied.addWidget(self._importer_bouton)
        pied.addStretch()
        self._exporter_bouton = QPushButton(tr("Exporter en .zip…"))
        self._exporter_bouton.setCursor(Qt.CursorShape.PointingHandCursor)
        self._exporter_bouton.clicked.connect(self._exporter)
        pied.addWidget(self._exporter_bouton)
        self._bouton = QPushButton(tr("Remettre cette version"))
        self._bouton.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bouton.clicked.connect(self._remettre)
        pied.addWidget(self._bouton)
        fermer = QPushButton(tr("Fermer"))
        fermer.setCursor(Qt.CursorShape.PointingHandCursor)
        fermer.clicked.connect(self.accept)
        pied.addWidget(fermer)
        layout.addLayout(pied)

    # ── Contenu ──

    def _nom(self, rel: str, presents: set[str]) -> str:
        """« Emplacement 2 », ou le nom du fichier ; « (effacée) » si elle n'existe plus."""
        nom = self._nom_emplacement(rel, max(len(self._versions), len(presents)))
        if rel not in presents:
            nom = tr("{} (effacée)").format(nom)
        return nom

    def _nom_emplacement(self, rel: str, nb: int) -> str:
        spec = self.game.sauvegardes
        n = sauvegardes.numero(rel, spec, nb) if spec is not None else None
        if sauvegardes.est_rapide(self.game.id, rel):
            return tr("Sauvegarde rapide")
        return tr("Emplacement {}").format(n) if n else rel.rsplit("/", 1)[-1]

    def _recharger(self) -> None:
        garde = self._choix.currentData()
        self._versions = copies_sauvegardes.versions(self.game.id)
        self._presents = sauvegardes.fichiers(self.game.sauvegardes)
        presents = set(self._presents)
        self._choix.blockSignals(True)
        self._choix.clear()
        for rel in sorted(set(self._versions) | presents):
            self._choix.addItem(self._nom(rel, presents), rel)
        self._choix.setCurrentIndex(max(0, self._choix.findData(garde)))
        self._choix.blockSignals(False)
        # Une seule sauvegarde (HP5 à HP7) : la liste suffit.
        self._choix.setVisible(self._choix.count() > 1)
        total = sum(v.taille for liste in self._versions.values() for v in liste)
        nb = sum(len(liste) for liste in self._versions.values())
        self._total.setText(tr("{} copie(s), {} en tout.").format(nb, _taille(total)))
        self._importer_bouton.setEnabled(self.game.sauvegardes is not None)
        self._montrer()

    def _montrer(self) -> None:
        self._liste.clear()
        rel = self._choix.currentData()
        chemin = self._presents.get(rel) if rel else None
        if chemin is not None:
            try:
                st = chemin.stat()
                texte = tr("Telle qu'elle est maintenant, écrite le {} ({})").format(
                    _quand(datetime.fromtimestamp(st.st_mtime)), _taille(st.st_size))
                item = QListWidgetItem(texte)
                item.setData(Qt.ItemDataRole.UserRole, _ACTUELLE)
                self._liste.addItem(item)
            except OSError:
                pass
        for rang, v in enumerate(self._versions.get(rel, [])):
            texte = f"{_quand(v.quand)} · {_taille(v.taille)}"
            if rang == 0:
                texte = tr("{} (la plus récente)").format(texte)
            item = QListWidgetItem(texte)
            item.setData(Qt.ItemDataRole.UserRole, v)
            self._liste.addItem(item)
        if self._liste.count():
            self._liste.setCurrentRow(0)
        self._maj_bouton()

    def _maj_bouton(self) -> None:
        item = self._liste.currentItem()
        donnee = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        self._bouton.setEnabled(isinstance(donnee, copies_sauvegardes.Version))
        self._exporter_bouton.setEnabled(donnee is not None)

    def _ouvrir_dossier(self) -> None:
        dossier = copies_sauvegardes.dossier_du_jeu(self.game.id)
        if dossier.is_dir():
            open_local_path(str(dossier))

    # ── Revenir ──

    def _boite(self, icone, titre: str, texte: str, choix=(), conserve: str = "") -> int:
        """Texte brut, boutons nommés : mêmes raisons que `game_detail_handlers._boite`."""
        # Le défaut est le RETRAIT : remettre une sauvegarde ne se fait pas d'un Entrée distrait.
        return message(self, icone, titre, texte, choix, defaut=max(0, len(choix) - 1), conserve=conserve)

    def _nom_courant(self) -> str:
        """Le nom à écrire dans les questions : l'emplacement, ou « la sauvegarde »
        pour un jeu qui n'en a qu'une (HP5 à HP7 : leur nom de fichier ne dit rien)."""
        spec = self.game.sauvegardes
        rel = self._choix.currentData() or ""
        if self._choix.count() > 1 or (spec is not None and sauvegardes.numero(rel, spec, 1)):
            return self._choix.currentText()
        return tr("La sauvegarde")

    def _jeu_ouvert(self) -> bool:
        en_cours = self._partie_en_cours()
        if en_cours:
            self._boite(QMessageBox.Icon.Information, tr("Partie en cours"),
                        tr("Fermez {} avant de remettre une sauvegarde : il la réécrirait "
                           "en quittant.").format(en_cours))
        return bool(en_cours)

    def _remettre(self) -> None:
        item = self._liste.currentItem()
        spec = self.game.sauvegardes
        if item is None or spec is None:
            return
        version = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(version, copies_sauvegardes.Version) or self._jeu_ouvert():
            return
        quand = _quand(version.quand)
        choix = self._boite(QMessageBox.Icon.Question, tr("Remettre cette version"),
                            tr("« {} » va revenir à sa version du {}.\n\n"
                               "Son état actuel est copié d'abord : vous pourrez y revenir "
                               "de la même façon.").format(self._nom_courant(), quand),
                            (tr("Remettre cette version"), tr("Annuler")))
        if choix != 0:
            return
        if copies_sauvegardes.revenir(self.game.id, spec, version):
            self._boite(QMessageBox.Icon.Information, tr("Sauvegarde remise"),
                        tr("« {} » est revenue à sa version du {}.").format(
                            self._nom_courant(), quand))
        else:
            self._boite(QMessageBox.Icon.Warning, tr("Sauvegarde non remise"),
                        tr("Rien n'a été remplacé. Le journal du launcher en dit la raison."))
        self._recharger()

    # ── Exporter ──

    def _exporter(self) -> None:
        item = self._liste.currentItem()
        spec = self.game.sauvegardes
        rel = self._choix.currentData()
        if item is None or spec is None or not rel:
            return
        donnee = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(donnee, copies_sauvegardes.Version):
            quand = donnee.quand
        else:
            try:
                quand = datetime.fromtimestamp(self._presents[rel].stat().st_mtime)
            except (KeyError, OSError):
                return
        nom = nom_de_fichier(f"{self.game.name} - {self._nom_courant()} - {quand:%Y-%m-%d %H%M}") + ".zip"
        dossier = Path.home() / "Documents"
        depart = str((dossier if dossier.is_dir() else Path.home()) / nom)
        cible, _filtre = QFileDialog.getSaveFileName(self, tr("Exporter la sauvegarde"), depart,
                                                     tr("Archive zip (*.zip)"))
        if not cible:
            return
        destination = Path(cible)
        if destination.suffix.lower() != ".zip":
            destination = destination.with_name(destination.name + ".zip")
        if isinstance(donnee, copies_sauvegardes.Version):
            fait = partage_sauvegardes.exporter_version(self.game.id, donnee, destination, APP_VERSION)
        else:
            fait = partage_sauvegardes.exporter(self.game.id, spec, rel, destination, APP_VERSION)
        if not fait:
            self._boite(QMessageBox.Icon.Warning, tr("Sauvegarde non exportée"),
                        tr("Le fichier n'a pas pu être écrit. Le journal du launcher en dit la raison."))
            return
        choix = self._boite(QMessageBox.Icon.Information, tr("Sauvegarde exportée"),
                            tr("« {} » s'importe dans Accio Launcher, sur ce PC ou sur un autre : "
                               "{} › Sauvegardes › Importer.").format(destination.name, self.game.name),
                            (tr("Ouvrir le dossier"), tr("Fermer")))
        if choix == 0:
            open_local_path(str(destination.parent))

    # ── Importer ──

    def _importer(self) -> None:
        spec = self.game.sauvegardes
        if spec is None or self._jeu_ouvert():
            return
        dossier = Path.home() / "Downloads"
        depart = str(dossier if dossier.is_dir() else Path.home())
        source, _filtre = QFileDialog.getOpenFileName(
            self, tr("Importer une sauvegarde"), depart,
            tr("Sauvegardes (*.zip *.usa);;Tous les fichiers (*)"))
        if not source:
            return
        paquet = partage_sauvegardes.lire(Path(source), spec)
        if isinstance(paquet, partage_sauvegardes.Paquet) and paquet.jeu not in (None, self.game.id):
            paquet = partage_sauvegardes.AUTRE_JEU
        if not isinstance(paquet, partage_sauvegardes.Paquet):
            self._boite(QMessageBox.Icon.Warning, tr("Sauvegarde non importée"), _refus(paquet))
            return
        places = partage_sauvegardes.emplacements(self.game.id, spec)
        if len(places) == 1:
            rel, pris = places[0]
        else:
            noms = [(r, self._nom_emplacement(r, len(places)), p) for r, p in places]
            choix = _ChoixEmplacement(noms, self)
            if choix.exec() != QDialog.DialogCode.Accepted:
                return
            rel = choix.choix.currentData()
            pris = dict(places)[rel]
        nom = self._nom_emplacement(rel, len(places)) if len(places) > 1 else tr("La sauvegarde")
        if pris:
            texte = (tr("« {} » va être remplacée par la partie importée.").format(nom) if len(places) > 1
                     else tr("Votre progression actuelle va être remplacée par la partie importée."))
            if self._boite(QMessageBox.Icon.Question, tr("Importer une sauvegarde"), texte,
                           (tr("Importer"), tr("Annuler")),
                           conserve=tr("La partie remplacée est copiée d'abord : elle reste dans "
                                       "cette liste, et revient en un clic.")) != 0:
                return
        if partage_sauvegardes.importer(self.game.id, spec, paquet, rel):
            self._boite(QMessageBox.Icon.Information, tr("Sauvegarde importée"),
                        tr("La partie est dans « {} ». Elle apparaît au prochain lancement du jeu.").format(nom))
        else:
            self._boite(QMessageBox.Icon.Warning, tr("Sauvegarde non importée"),
                        tr("Rien n'a été remplacé. Le journal du launcher en dit la raison."))
        self._recharger()
        index = self._choix.findData(rel)
        if index >= 0:
            self._choix.setCurrentIndex(index)
