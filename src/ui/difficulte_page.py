"""La page « Difficulté » d'un jeu (contenu : `src/core/difficulte_presets.py`).

1.4, tranché par Ludo le 2026-10-30 : des presets aux noms clairs (Normal,
Détendu, Hardcore ; puis, à une seule vie, Réaliste et Impardonnable), « Sur
mesure » à part, qui ouvre le détail de chaque réglage. Une PAGE à la place de
la fiche (`pages.py`), comme les réglages du jeu, ouverte par le bouton à jauge
de la fiche.

Chaque carte dit ce que le preset change dans CE jeu, calculé depuis les
réglages ; un preset qui n'y change rien ne s'y montre pas, et une seule vie se
montre « bientôt » tant que son mécanisme n'existe pas. Choisir écrit aussitôt
(comme l'engrenage) ; rien n'est écrit au lancement.
"""

from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.core import difficulte_presets as dp
from src.core import reglages_correctif
from src.core.game_data import GameData
from src.core.game_manager import GameManager
from src.core.i18n import tr
from src.ui.composants import ENCRE_DOUCE, Rangee, bouton, feuille_de_style, surtitre, texte
from src.ui.fonts import cinzel, cinzel_decorative
from src.ui.theme import current as current_theme, themed
from src.ui.utils import zone_defilable

_MARGES = (64, 30, 64, 28)

_STYLE = """
QDialog#difficulte { background: #060611; }
QFrame#preset { background: #0d0d1a; border: 1px solid rgba(214, 167, 44, 0.22); border-radius: 12px; }
QFrame#preset[actif="true"] { background: rgba(214, 167, 44, 0.08); border: 2px solid rgba(214, 167, 44, 0.75); }
QFrame#preset[bientot="true"] { background: #0a0a14; border: 1px dashed rgba(169, 167, 196, 0.25); }
QFrame#filetOr { background: rgba(214, 167, 44, 0.14); border: none; }
"""

# Les jeux UE1 relisent leurs fichiers au lancement ; HP5 et HP6, dans la seconde.
_EN_DIRECT = {"hp5", "hp6"}


class _CartePreset(QFrame):
    def __init__(self, preset: dp.Preset, lignes: tuple[tuple[str, str], ...], actif: bool,
                 bientot: bool, choisir: Callable[[str], None]) -> None:
        super().__init__()
        self.setObjectName("preset")
        self.ident = preset.ident
        self.setProperty("actif", "true" if actif else "false")
        self.setProperty("bientot", "true" if bientot else "false")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)
        nom = QLabel(tr(preset.nom))
        nom.setTextFormat(Qt.TextFormat.PlainText)
        nom.setFont(cinzel(14, bold=True))
        couleur = "#7d7b94" if bientot else "#f2f2f4"
        nom.setStyleSheet(f"color: {couleur}; background: transparent; border: none;")
        lay.addWidget(nom)
        phrase = texte(tr(preset.phrase), 14, "#a9a7c4" if not bientot else "#6f6d86", retour=True)
        phrase.setStyleSheet(phrase.styleSheet() + " border: none;")
        lay.addWidget(phrase)
        for libelle, valeur in lignes:
            ligne = texte(f"{libelle} : {valeur}" if valeur else libelle, 13, "#dcdaea", retour=True)
            ligne.setObjectName("changement")
            ligne.setStyleSheet(ligne.styleSheet() + " border: none;")
            lay.addWidget(ligne)
        lay.addStretch()
        if bientot:
            etat = texte(tr("Bientôt"), 13, "#7d7b94")
            etat.setStyleSheet(etat.styleSheet() + " border: none;")
            lay.addWidget(etat)
            self.bouton = None
            return
        self.bouton = bouton(tr("Choisi") if actif else tr("Choisir"), principal=not actif)
        self.bouton.setAutoDefault(False)
        self.bouton.setEnabled(not actif)
        self.bouton.setAccessibleName(tr("Choisir {}").format(tr(preset.nom)))
        self.bouton.clicked.connect(lambda: choisir(preset.ident))
        lay.addWidget(self.bouton, alignment=Qt.AlignmentFlag.AlignLeft)


def _cases_vides(n: int) -> list[QWidget]:
    """Des cases invisibles qui GARDENT leur place : une colonne vide de la grille
    perdait son écart, et les cartes du dessous ne s'alignaient plus."""
    cases = []
    for _ in range(n):
        case = QWidget()
        politique = case.sizePolicy()
        politique.setRetainSizeWhenHidden(True)
        case.setSizePolicy(politique)
        case.hide()
        cases.append(case)
    return cases


class DifficultePage(QDialog):
    """Les presets de difficulté d'un jeu installé."""

    def __init__(self, game: GameData, manager: GameManager,
                 ouvrir_detail: Callable[[], None] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("difficulte")
        self.game = game
        self.manager = manager
        self._ouvrir_detail = ouvrir_detail
        self.setWindowTitle(tr("Difficulté"))
        self.setStyleSheet(themed(_STYLE) + feuille_de_style())
        declares = reglages_correctif.reglages_du_jeu(game.fix_settings)
        self.ini: Path | None = (reglages_correctif.ini_du_correctif(
            manager.config.install_path / Path(game.executable).parent) if declares else None)
        self.idents = dp.idents_du_jeu(game, self.ini)
        self._racine = QVBoxLayout(self)
        self._racine.setContentsMargins(0, 0, 0, 0)
        self._racine.setSpacing(0)
        self.erreur = ""
        self._construire()

    def courant(self) -> str:
        return dp.courant(dp.lire(self.game, self.manager.config, self.ini, self.idents), self.idents)

    def _construire(self) -> None:
        while self._racine.count():
            item = self._racine.takeAt(0)
            if item is not None and (w := item.widget()) is not None:
                # Hors de la page TOUT DE SUITE : `deleteLater` seul la laissait
                # peinte sous la nouvelle jusqu'au prochain tour de boucle.
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self._racine.addWidget(zone_defilable(self._contenu()), stretch=1)
        self._racine.addWidget(self._pied())

    def _contenu(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(_MARGES[0], _MARGES[1], _MARGES[2], 0)
        lay.setSpacing(0)
        lay.addWidget(surtitre(tr("Difficulté")))
        lay.addSpacing(8)
        titre = QLabel(self.game.name)
        titre.setTextFormat(Qt.TextFormat.PlainText)
        titre.setFont(cinzel_decorative(24))
        titre.setStyleSheet("color: #f4f2f8; background: transparent;")
        lay.addWidget(titre)
        lay.addSpacing(8)
        quand = (tr("Change à tout moment, partie en cours comprise.") if self.game.id in _EN_DIRECT
                 else tr("Compte au prochain lancement du jeu."))
        lay.addWidget(texte(quand + " " + tr("Vos sauvegardes ne changent pas. En bêta."),
                            15, "#a9a7c4", retour=True))
        courant = self.courant()
        hardcore = dp.disponible(dp.PAR_IDENT["hardcore"], self.game.id, self.idents)
        rangees: dict[bool, list[_CartePreset]] = {False: [], True: []}
        for preset in dp.PRESETS:
            disponible = dp.disponible(preset, self.game.id, self.idents)
            # Une seule vie se montre « bientôt » tant que son mécanisme manque ;
            # Impardonnable, seulement là où Hardcore change quelque chose.
            visible = disponible or (preset.une_vie and (preset.ident == "realiste" or hardcore))
            if not visible:
                continue   # ne change rien ici : pas de carte
            lignes = dp.changements(preset, self.idents) if disponible else ()
            rangees[preset.une_vie].append(_CartePreset(
                preset, lignes, preset.ident == courant, not disponible, self._choisir))
        self.cartes = rangees[False] + rangees[True]
        # Même nombre de colonnes aux deux rangées : les cartes s'alignent.
        colonnes = max(len(rangees[False]), len(rangees[True]))
        # Sous 210 px par carte, elles s'écrasaient (cinq cartes à 1000 px de
        # large) et « Impardonnable » élargissait sa colonne : on empile.
        seuil = colonnes * 210
        lay.addSpacing(24)
        lay.addWidget(Rangee(rangees[False], colonnes, seuil=seuil, ecart=18))
        lay.addSpacing(30)
        lay.addWidget(surtitre(tr("Une seule vie")))
        lay.addSpacing(6)
        lay.addWidget(texte(tr("La première mort termine la partie : pas de retour à la dernière "
                               "sauvegarde."), 14, ENCRE_DOUCE, retour=True))
        lay.addSpacing(14)
        lay.addWidget(Rangee(rangees[True] + _cases_vides(colonnes - len(rangees[True])),
                             colonnes, seuil=seuil, ecart=18))
        lay.addSpacing(22)
        sur_mesure = QHBoxLayout()
        sur_mesure.setSpacing(18)
        phrase = (tr("Vos réglages ne correspondent à aucun preset : c'est du sur mesure.")
                  if courant == dp.SUR_MESURE else
                  tr("Sur mesure : chaque réglage à votre goût, un par un."))
        self.ligne_sur_mesure = texte(phrase, 14, ENCRE_DOUCE if courant != dp.SUR_MESURE
                                      else current_theme().accent_light, retour=True)
        sur_mesure.addWidget(self.ligne_sur_mesure, stretch=1)
        if self._ouvrir_detail is not None:
            detail = bouton(tr("Régler chaque paramètre"))
            detail.setAutoDefault(False)
            detail.clicked.connect(self._ouvrir_detail)
            sur_mesure.addWidget(detail)
        lay.addLayout(sur_mesure)
        if self.erreur:
            lay.addSpacing(14)
            lay.addWidget(texte(self.erreur, 14, "#ff9a8a", retour=True))
        lay.addStretch()
        lay.addSpacing(24)
        return page

    def _pied(self) -> QWidget:
        pied = QWidget()
        pied.setStyleSheet("background: transparent;")
        v = QVBoxLayout(pied)
        v.setContentsMargins(_MARGES[0], 0, _MARGES[2], _MARGES[3])
        v.setSpacing(18)
        filet = QFrame()
        filet.setObjectName("filetOr")
        filet.setFixedHeight(1)
        v.addWidget(filet)
        h = QHBoxLayout()
        h.addStretch()
        retour = bouton(tr("Retour à la fiche"), principal=True)
        retour.setAutoDefault(False)
        retour.clicked.connect(self.accept)
        h.addWidget(retour)
        v.addLayout(h)
        return pied

    @classmethod
    def depuis_la_fiche(cls, view) -> None:
        """Ouvre la page depuis le bouton à jauge de la fiche (`GameDetailView`).
        « Régler chaque paramètre » ouvre les réglages du jeu sur l'onglet Jeu."""
        from src.ui import game_detail_handlers as handlers
        if view.game is None:
            return
        dlg = cls(view.game, view.manager, parent=view,
                  ouvrir_detail=lambda: handlers.on_game_settings(view, onglet="jeu"))
        if view.receivers(view.page_demandee):
            view.page_demandee.emit(dlg)
        else:
            dlg.exec()

    def _choisir(self, ident: str) -> None:
        rates = dp.appliquer(dp.PAR_IDENT[ident], self.game, self.manager.config, self.ini, self.idents)
        self.erreur = (tr("Certains réglages n'ont pas pu être écrits (fichier absent ou en lecture "
                          "seule) : le jeu garde les précédents.") if rates else "")
        self._construire()
