"""L'écran où le joueur choisit si, et où, le launcher écrit dans sa sauvegarde (décision C8 de Ludo,
2026-11-17) : la difficulté propre de HP5, la Nouvelle partie+ de HP4. Le contenu et l'écriture sont dans
`core/sauvegarde_20cm`.

Dans l'onglet Difficulté, sous « Une seule vie », une section « Dans votre sauvegarde » et son bouton
(`bloc`), là seulement où le fichier du jeu est présent et lisible. Le bouton ouvre la fenêtre : la partie,
(HP5) la difficulté, puis OÙ écrire : une partie neuve dans un emplacement libre (les siennes ne bougent
pas), ou la sienne réécrite (une copie de sécurité d'abord). « Ne rien écrire » est le troisième choix, et
celui d'Échap. Jamais pendant que le jeu tourne : il réécrirait la partie en sortant.
"""

from collections.abc import Callable
from datetime import datetime

from PyQt6.QtCore import QDate, QLocale, Qt, QTime
from PyQt6.QtWidgets import QDialog, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget

from src.core import sauvegarde_20cm as s20
from src.core.game_data import GameData
from src.core.i18n import get_language, tr
from src.ui.composants import bouton, feuille_de_style, texte, transparent
from src.ui.difficulte_panneau import titre_section
from src.ui.entree_focus import entree_suit_le_focus
from src.ui.fenetre_message import message
from src.ui.fonts import cinzel
from src.ui.settings_panel import _COMBO_STYLE
from src.ui.theme import themed
from src.ui.utils import liste_deroulante

_FENETRE = "QDialog { background: #0d0d1a; border: 1px solid rgba(214,167,44,0.3); }"
_DOUX = "#a9a7c4"
_ENCRE = "#e0e0f0"

# Ce que dit chaque jeu : le titre (de la section et de la fenêtre), ce que fait l'écriture, le bouton.
_TEXTES = {
    "hp5": ("Difficulté de vos parties",
            "Le jeu garde sa difficulté (Facile, Normal, Difficile) dans chaque partie. Le launcher peut "
            "l'y changer : dans une copie de la partie, ou dans la partie elle-même.",
            "Changer la difficulté d'une partie…"),
    "hp4": ("Nouvelle partie+",
            "Repartez du premier niveau en gardant les cartes, les dragées, la maîtrise des sorts, le rang "
            "et les boucliers d'une partie.",
            "Commencer une Nouvelle partie+…"),
}


def _date(moment: datetime | None) -> str:
    if moment is None:
        return ""
    locale = QLocale(get_language())
    jour = locale.toString(QDate(moment.year, moment.month, moment.day), QLocale.FormatType.ShortFormat)
    return f"{jour} {locale.toString(QTime(moment.hour, moment.minute), QLocale.FormatType.ShortFormat)}"


def nom_partie(jeu: str, partie: s20.Partie) -> str:
    """« Partie 1 · 15 % · Difficile · 16/11/2026 12:06 » : ce qu'en montre l'écran des parties du jeu."""
    morceaux = [tr("Partie {}").format(partie.numero)]
    if jeu == "hp5":
        if partie.avancement is not None:
            morceaux.append(f"{partie.avancement} %")
        if partie.difficulte is not None:
            morceaux.append(tr(s20.DIFFICULTES[partie.difficulte]))
    elif partie.rang is not None and partie.boucliers is not None:
        morceaux.append(tr("rang {}, {} boucliers").format(partie.rang, partie.boucliers))
    morceaux.append(_date(partie.ecrite))
    return " · ".join(m for m in morceaux if m)


def bloc(game: GameData, partie_en_cours: Callable[[], str], parent: QWidget | None = None) -> QWidget | None:
    """La section de l'onglet Difficulté, ou None (jeu sans cette écriture, aucune partie lisible)."""
    if game.id not in _TEXTES:
        return None
    lu = s20.lire(game)
    if lu is None or not lu.occupees:
        return None
    titre, phrase, libelle = _TEXTES[game.id]
    section = QWidget(parent)
    transparent(section, "dansLaSauvegarde")
    v = QVBoxLayout(section)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(14)
    v.addWidget(titre_section(tr(titre)))
    ligne = QHBoxLayout()
    ligne.setSpacing(18)
    explication = texte(tr(phrase), 14, _DOUX, retour=True)
    ligne.addWidget(explication, stretch=1)
    ouvrir = bouton(tr(libelle))
    ouvrir.setObjectName("ouvrirChoixSauvegarde")
    ouvrir.clicked.connect(lambda: ChoixSauvegarde(game, partie_en_cours, section).exec())
    ligne.addWidget(ouvrir, alignment=Qt.AlignmentFlag.AlignVCenter)
    v.addLayout(ligne)
    return section


class ChoixSauvegarde(QDialog):
    """La partie, (HP5) la difficulté, et où écrire. Relit le fichier à l'ouverture."""

    def __init__(self, game: GameData, partie_en_cours: Callable[[], str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        entree_suit_le_focus(self)
        self.game = game
        self._partie_en_cours = partie_en_cours
        self._lu = s20.lire(game)
        titre, phrase, _libelle = _TEXTES[game.id]
        self.setWindowTitle(tr(titre))
        self.setMinimumWidth(560)
        self.setStyleSheet(themed(_FENETRE) + feuille_de_style())
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 16)
        lay.setSpacing(12)
        tete = QLabel(tr(titre))
        tete.setTextFormat(Qt.TextFormat.PlainText)
        tete.setFont(cinzel(14, bold=True))
        tete.setStyleSheet(themed("color: #d6a72c; background: transparent;"))
        lay.addWidget(tete)
        lay.addWidget(texte(tr(phrase), 13, _DOUX, retour=True))

        grille = QGridLayout()
        grille.setHorizontalSpacing(14)
        grille.setVerticalSpacing(10)
        self.partie = liste_deroulante()
        self.difficulte = liste_deroulante() if game.id == "hp5" else None
        self.ou = liste_deroulante()
        lignes = [(tr("Partie"), self.partie), (tr("Écrire"), self.ou)]
        if self.difficulte is not None:
            lignes.insert(1, (tr("Difficulté"), self.difficulte))
        for rang, (nom, liste) in enumerate(lignes):
            liste.setStyleSheet(themed(_COMBO_STYLE))
            etiquette = texte(nom, 13, _ENCRE)
            etiquette.setBuddy(liste)
            grille.addWidget(etiquette, rang, 0)
            grille.addWidget(liste, rang, 1)
        grille.setColumnStretch(1, 1)
        lay.addLayout(grille)
        self.note = texte("", 12, _DOUX, retour=True)
        self.note.setObjectName("noteChoixSauvegarde")
        lay.addWidget(self.note)

        pied = QHBoxLayout()
        pied.addStretch()
        # Du plus neutre au plus engageant : celui qui agit finit à droite.
        self.rien = bouton(tr("Ne rien écrire"))
        self.rien.clicked.connect(self.reject)
        self.ecrire = bouton(tr("Écrire"), principal=True)
        self.ecrire.clicked.connect(self._ecrire)
        for b in (self.rien, self.ecrire):
            b.setAutoDefault(False)
            pied.addWidget(b)
        lay.addLayout(pied)

        for p in self._lu.occupees if self._lu is not None else ():
            self.partie.addItem(nom_partie(game.id, p), p.numero)
        if self.difficulte is not None:
            for nom in s20.DIFFICULTES:
                self.difficulte.addItem(tr(nom))
            self.difficulte.currentIndexChanged.connect(self._maj)
        self.partie.currentIndexChanged.connect(self._sur_partie)
        self.ou.currentIndexChanged.connect(self._maj)
        self._sur_partie()

    # ── Ce qui est choisi ──

    def _choisie(self) -> s20.Partie | None:
        numero = self.partie.currentData()
        if self._lu is None or not isinstance(numero, int):
            return None
        return self._lu.parties[numero - 1]

    def _vers(self) -> int | None:
        vers = self.ou.currentData()
        return vers if isinstance(vers, int) else None

    def _sur_partie(self) -> None:
        """Une autre partie : les deux destinations, et (HP5) sa difficulté actuelle présélectionnée."""
        partie = self._choisie()
        self.ou.blockSignals(True)
        self.ou.clear()
        if partie is not None and self._lu is not None:
            libre = self._lu.libre
            if libre is not None:
                self.ou.addItem(tr("Une nouvelle partie, dans l'emplacement {}").format(libre), libre)
            self.ou.addItem(tr("Cette partie, réécrite"), partie.numero)
        self.ou.blockSignals(False)
        if self.difficulte is not None and partie is not None and partie.difficulte is not None:
            self.difficulte.blockSignals(True)
            self.difficulte.setCurrentIndex(partie.difficulte)
            self.difficulte.blockSignals(False)
        self._maj()

    def _maj(self) -> None:
        """Ce que fera l'écriture, en une phrase ; « Écrire » grisé quand il n'y a rien à faire."""
        partie, vers = self._choisie(), self._vers()
        utile = partie is not None and vers is not None
        if partie is None or vers is None or self._lu is None:
            phrase = ""
        elif self.difficulte is not None and vers == partie.numero \
                and self.difficulte.currentIndex() == partie.difficulte:
            phrase = tr("Cette partie est déjà à cette difficulté.")
            utile = False
        elif vers != partie.numero:
            phrase = tr("Vos parties ne changent pas.") if self._lu.libre is not None else ""
        elif self.game.id == "hp4":
            phrase = tr("Son niveau et les niveaux traversés repartent du début. Une copie de sécurité est "
                        "faite d'abord : « Sauvegardes », dans la rubrique Fichiers, sait la remettre.")
        else:
            phrase = tr("Rien d'autre ne change dans la partie. Une copie de sécurité est faite d'abord : "
                        "« Sauvegardes », dans la rubrique Fichiers, sait la remettre.")
        self.note.setText(phrase)
        self.note.setVisible(bool(phrase))
        self.ecrire.setEnabled(utile)

    # ── Écrire ──

    def _boite(self, icone: QMessageBox.Icon, titre: str, contenu: str) -> None:
        message(self, icone, titre, contenu)

    def _ecrire(self) -> None:
        partie, vers, lu = self._choisie(), self._vers(), self._lu
        if partie is None or vers is None or lu is None:
            return
        en_cours = self._partie_en_cours()
        if en_cours:
            self._boite(QMessageBox.Icon.Information, tr("Partie en cours"),
                        tr("Fermez {} avant d'écrire dans la sauvegarde : il la réécrirait en "
                           "quittant.").format(en_cours))
            return
        try:
            if self.difficulte is not None:
                neufs = s20.difficulte_hp5(lu.octets, partie.numero, self.difficulte.currentIndex(), vers)
            else:
                neufs = s20.nouvelle_partie_plus_hp4(lu.octets, partie.numero, vers, datetime.now())
        except ValueError:     # Illisible compris : rien n'est écrit
            raison = "format"
        else:
            raison = s20.ecrire(self.game, lu, neufs)
        if raison:
            self._boite(QMessageBox.Icon.Warning, tr("Rien n'a été écrit"), {
                "change": tr("La sauvegarde a changé depuis l'ouverture de cette fenêtre : rouvrez-la."),
                "copie": tr("La copie de sécurité n'a pas pu être faite : la sauvegarde n'a pas été "
                            "touchée."),
            }.get(raison, tr("La sauvegarde n'a pas pu être écrite. Le journal du launcher en dit la "
                             "raison.")))
            return
        self._boite(QMessageBox.Icon.Information, tr("C'est écrit"),
                    tr("La partie {} vous attend dans le menu du jeu.").format(vers))
        self.accept()
