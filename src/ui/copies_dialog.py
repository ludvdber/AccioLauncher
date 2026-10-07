"""Revenir à une version précédente d'une sauvegarde (`copies_sauvegardes`).

Une liste par sauvegarde, la plus récente en haut, datée par le JEU (le
moment où il a écrit cette version, pas celui de la copie) : c'est ce dont
on se souvient — « hier soir, avant le boss ». Remettre une version demande
une confirmation qui dit ce qui se passe pour l'état actuel : il est copié
d'abord, on peut donc y revenir de la même façon.
"""

from __future__ import annotations

from PyQt6.QtCore import QDate, QLocale, Qt, QTime
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core import copies_sauvegardes, sauvegardes
from src.core.game_data import GameData
from src.core.i18n import get_language, tr
from src.ui.fonts import body_font, cinzel
from src.ui.settings_panel import _COMBO_STYLE
from src.ui.theme import themed
from src.ui.utils import liste_deroulante, open_local_path

_LISTE_STYLE = (
    "QListWidget { color: #e0e0f0; background: #141428; border: 1px solid #2a2a48;"
    " font-size: 13px; outline: none; }"
    "QListWidget::item { padding: 6px 8px; }"
    "QListWidget::item:selected { color: #0d0d1a; background: #d6a72c; }"
)


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
    return "{}, {}".format(
        locale.toString(QDate(moment.year, moment.month, moment.day), QLocale.FormatType.LongFormat),
        locale.toString(QTime(moment.hour, moment.minute), QLocale.FormatType.ShortFormat))


class CopiesDialog(QDialog):
    """Les copies d'un jeu ; « Remettre cette version » pour revenir en arrière."""

    def __init__(self, game: GameData, partie_en_cours=lambda: "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.game = game
        # () -> str : le nom du jeu qui tourne, vide sinon. Remettre une
        # sauvegarde sous un jeu ouvert : il la réécrirait en quittant.
        self._partie_en_cours = partie_en_cours
        self._versions: dict[str, list[copies_sauvegardes.Version]] = {}
        self.setWindowTitle(tr("Versions des sauvegardes — {}").format(game.name))
        self.setMinimumSize(520, 440)
        self.setStyleSheet(themed(
            "QDialog { background: #0d0d1a; border: 1px solid rgba(214,167,44,0.3); }"))
        self._build_ui()
        self._recharger()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(10)
        titre = QLabel(tr("Versions des sauvegardes — {}").format(self.game.name))
        titre.setFont(cinzel(14, bold=True))
        titre.setTextFormat(Qt.TextFormat.PlainText)      # nom du CATALOGUE
        titre.setWordWrap(True)
        titre.setStyleSheet(themed("color: #d6a72c; background: transparent;"))
        layout.addWidget(titre)
        note = QLabel(tr(
            "Avant chaque partie, le lanceur garde une copie de chaque sauvegarde qui a changé. "
            "Les dates sont celles où le jeu a écrit chaque version."))
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
        layout.addWidget(self._total)

        pied = QHBoxLayout()
        dossier = QPushButton(tr("Ouvrir le dossier des copies"))
        dossier.setCursor(Qt.CursorShape.PointingHandCursor)
        dossier.clicked.connect(self._ouvrir_dossier)
        pied.addWidget(dossier)
        pied.addStretch()
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
        spec = self.game.sauvegardes
        n = sauvegardes.numero(rel, spec, len(self._versions)) if spec is not None else None
        nom = tr("Emplacement {}").format(n) if n else rel.rsplit("/", 1)[-1]
        if rel not in presents:
            nom = tr("{} (effacée)").format(nom)
        return nom

    def _recharger(self) -> None:
        garde = self._choix.currentData()
        self._versions = copies_sauvegardes.versions(self.game.id)
        presents = set(sauvegardes.fichiers(self.game.sauvegardes))
        self._choix.blockSignals(True)
        self._choix.clear()
        for rel in sorted(self._versions):
            self._choix.addItem(self._nom(rel, presents), rel)
        self._choix.setCurrentIndex(max(0, self._choix.findData(garde)))
        self._choix.blockSignals(False)
        # Une seule sauvegarde (HP5 à HP7) : la liste suffit.
        self._choix.setVisible(len(self._versions) > 1)
        total = sum(v.taille for liste in self._versions.values() for v in liste)
        nb = sum(len(liste) for liste in self._versions.values())
        self._total.setText(tr("{} copie(s), {} en tout.").format(nb, _taille(total)))
        self._montrer()

    def _montrer(self) -> None:
        self._liste.clear()
        for rang, v in enumerate(self._versions.get(self._choix.currentData(), [])):
            texte = f"{_quand(v.quand)} — {_taille(v.taille)}"
            if rang == 0:
                texte = tr("{} (la plus récente)").format(texte)
            item = QListWidgetItem(texte)
            item.setData(Qt.ItemDataRole.UserRole, v)
            self._liste.addItem(item)
        if self._liste.count():
            self._liste.setCurrentRow(0)
        self._maj_bouton()

    def _maj_bouton(self) -> None:
        self._bouton.setEnabled(self._liste.currentItem() is not None)

    def _ouvrir_dossier(self) -> None:
        dossier = copies_sauvegardes.dossier_du_jeu(self.game.id)
        if dossier.is_dir():
            open_local_path(str(dossier))

    # ── Revenir ──

    def _boite(self, icone, titre: str, texte: str, choix=()) -> int:
        """Texte brut, boutons nommés : mêmes raisons que `game_detail_handlers._boite`."""
        boite = QMessageBox(self)
        boite.setIcon(icone)
        boite.setWindowTitle(titre)
        boite.setTextFormat(Qt.TextFormat.PlainText)
        boite.setText(texte)
        boutons = [boite.addButton(c, QMessageBox.ButtonRole.AcceptRole if i == 0
                                   else QMessageBox.ButtonRole.RejectRole)
                   for i, c in enumerate(choix or (tr("Fermer"),))]
        boite.setDefaultButton(boutons[-1])
        boite.setEscapeButton(boutons[-1])
        boite.exec()
        clique = boite.clickedButton()
        return boutons.index(clique) if clique in boutons else -1

    def _nom_courant(self) -> str:
        """Le nom à écrire dans les questions : l'emplacement, ou « la sauvegarde »
        pour un jeu qui n'en a qu'une (HP5 à HP7 : leur nom de fichier ne dit rien)."""
        spec = self.game.sauvegardes
        rel = self._choix.currentData() or ""
        if len(self._versions) > 1 or (spec is not None and sauvegardes.numero(rel, spec, 1)):
            return self._choix.currentText()
        return tr("La sauvegarde")

    def _remettre(self) -> None:
        item = self._liste.currentItem()
        spec = self.game.sauvegardes
        if item is None or spec is None:
            return
        version: copies_sauvegardes.Version = item.data(Qt.ItemDataRole.UserRole)
        en_cours = self._partie_en_cours()
        if en_cours:
            self._boite(QMessageBox.Icon.Information, tr("Partie en cours"),
                        tr("Fermez {} avant de remettre une sauvegarde : il la réécrirait "
                           "en quittant.").format(en_cours))
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
