"""Les versions d'un jeu, en PAGE : la liste à gauche, le détail à droite.

Refaite le 2026-10-14 d'après la maquette « Versions d'un jeu » validée par
Ludo. L'ancienne boîte de 550 × 500 empilait toutes les versions, chacune avec
son bouton : pour lire ce qu'apporte la 1.3, il fallait faire défiler la 1.0,
et quatre boutons « Revenir à… » se ressemblaient. Ici on choisit une version
dans le rail ; la page dit ce qu'elle change et porte UN bouton, qui dit ce
qui va arriver.

Le rail reprend celui des réglages du jeu (retour « Bibliothèque », jaquette,
nom) : deux pages d'un même jeu se reconnaissent.

Ce que la page promet, elle le tient : changer de version SUPPRIME le dossier
du jeu (`GameOperations.switch_version`), mais les réglages posés à côté de
l'exécutable sont lus avant et reportés dans la nouvelle version
(`reglages_conserves`), et les configs de Documents ne sont plus écrasées.
Les sauvegardes, rangées dans Documents ou AppData, ne bougent pas.
"""

import html
from datetime import date

from PyQt6.QtCore import QDate, QLocale, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.formatting import format_size
from src.core.game_data import GameData, GameVersion
from src.core.game_manager import GameManager
from src.core.i18n import get_language, tr
from src.core.version_utils import compare_versions
from src.ui.composants import (
    ENCRE,
    ENCRE_DOUCE,
    bouton,
    feuille_de_style,
    police,
    surtitre,
    texte,
)
from src.ui.fenetre_message import FenetreMessage
from src.ui.fonts import cinzel, cinzel_decorative
from src.ui.icon_button import pixmap_icone
from src.ui.reglages_widgets import _STYLE as _STYLE_RAIL, _Jaquette
from src.ui.theme import current as current_theme, themed
from src.ui.utils import zone_defilable

_LARGEUR_RAIL = 300
_MARGES_PAGE = (48, 32, 48, 32)
_VERT = "#7be0a4"

_STYLE = """
QPushButton#version {
    background: transparent; border: 1px solid transparent; border-radius: 8px;
    min-height: 58px; max-height: 58px;
}
QPushButton#version:hover { background: rgba(255, 255, 255, 0.04); }
QPushButton#version:checked {
    background: rgba(214, 167, 44, 0.09); border-color: rgba(214, 167, 44, 0.45);
}
QPushButton#version[focusClavier="true"]:focus { border: 2px solid #d6a72c; }
QFrame#filetOr { background: rgba(214, 167, 44, 0.16); border: none; }
"""


def _date_sort_key(date_str: str) -> tuple[int, ...]:
    """Tuple parsable depuis une date 'YYYY-MM-DD' ; tolérant aux formats cassés."""
    try:
        return tuple(int(x) for x in date_str.split("-"))
    except (ValueError, AttributeError):
        return (0,)


def _jour(date_str: str) -> date | None:
    cle = _date_sort_key(date_str)
    try:
        return date(*cle) if len(cle) == 3 else None
    except ValueError:
        return None


# L'ordre du jour, du mois et de l'année, sans le jour de la semaine que
# porte le format long de QLocale. Une langue absente prend « 1 octobre 2026 ».
_FORMATS_LONGS = {
    "fr": "d MMMM yyyy",
    "en": "MMMM d, yyyy",
    "es": "d 'de' MMMM 'de' yyyy",
}


def date_courte(date_str: str) -> str:
    """« 01/10/2026 » ; la chaîne du catalogue telle quelle si elle ne se lit pas."""
    d = _jour(date_str)
    return d.strftime("%d/%m/%Y") if d else date_str


def date_longue(date_str: str) -> str:
    """« 1er octobre 2026 » dans la langue de l'interface."""
    d = _jour(date_str)
    if d is None:
        return date_str
    langue = get_language()
    motif = _FORMATS_LONGS.get(langue, "d MMMM yyyy")
    if langue == "fr" and d.day == 1:
        motif = "d'er' MMMM yyyy"   # QLocale ne connaît pas l'ordinal « 1er »
    return QLocale(langue).toString(QDate(d.year, d.month, d.day), motif)


def _badge(libelle: str, couleur: str, fond: str) -> QLabel:
    lbl = QLabel(libelle)
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    lbl.setFont(police(11))
    lbl.setStyleSheet(f"color: {couleur}; background: {fond}; border-radius: 9px; padding: 2px 8px;")
    lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return lbl


class _LigneVersion(QPushButton):
    """« v1.3 », sa date dessous, et ce qu'elle est pour ce joueur à droite."""

    def __init__(self, ver: GameVersion, installee: bool, recommandee: bool) -> None:
        super().__init__()
        self.setObjectName("version")
        self.setCheckable(True)
        self.setAutoDefault(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.version = ver.version
        etats = []
        if installee:
            etats.append(tr("Installée"))
        if recommandee:
            etats.append(tr("Recommandée"))
        self.setAccessibleName(", ".join([f"v{ver.version}", date_courte(ver.date), *etats]))

        h = QHBoxLayout(self)
        h.setContentsMargins(14, 8, 12, 8)
        h.setSpacing(8)
        gauche = QVBoxLayout()
        gauche.setSpacing(2)
        numero = QLabel(f"v{ver.version}")
        numero.setTextFormat(Qt.TextFormat.PlainText)   # le numéro vient du CATALOGUE
        numero.setFont(cinzel(12, bold=True))
        numero.setStyleSheet(f"color: {ENCRE}; background: transparent;")
        gauche.addWidget(numero)
        gauche.addWidget(texte(date_courte(ver.date), 12, ENCRE_DOUCE))
        h.addLayout(gauche)
        h.addStretch()
        centre = Qt.AlignmentFlag.AlignVCenter
        if installee:
            h.addWidget(_badge(tr("Installée"), _VERT, "rgba(46,204,113,0.14)"), alignment=centre)
        if recommandee:
            h.addWidget(_badge(tr("Recommandée"), current_theme().accent_light,
                               "rgba(214,167,44,0.14)"), alignment=centre)
        # Le bouton reçoit les clics : ses libellés ne sont que de la peinture.
        for enfant in self.findChildren(QLabel):
            enfant.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


class VersionsDialog(QDialog):
    """Versions et changelog d'un jeu — permet upgrade et downgrade."""

    # Émis pour demander un swap de version (uninstall current → install target).
    switch_to_version = pyqtSignal(str, str)  # (game_id, version)

    def __init__(self, game: GameData, manager: GameManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.game = game
        self.manager = manager
        self._installed_version = manager.installed_version(game.id)
        # Les plus récentes d'abord (parsing tolérant aux dates cassées).
        self._versions = sorted(game.versions, key=lambda v: _date_sort_key(v.date), reverse=True)
        self._lignes: dict[str, _LigneVersion] = {}
        self._actions: dict[str, QPushButton] = {}

        self.setWindowTitle(tr("Versions — {}").format(game.name))
        self.setMinimumSize(900, 560)
        self.setStyleSheet(themed(_STYLE_RAIL + _STYLE) + feuille_de_style())
        self._build_ui()
        if self._versions:
            self.choisir(self._version_de_depart())

    def _version_de_depart(self) -> str:
        """Celle qu'on a sous la main : l'installée, sinon la recommandée."""
        connues = {v.version for v in self._versions}
        for candidate in (self._installed_version, self.game.recommended_version):
            if candidate in connues:
                return candidate
        return self._versions[0].version

    # ── Construction ──

    def _build_ui(self) -> None:
        racine = QHBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(0)
        racine.addWidget(self._rail())
        self._details = QStackedWidget()
        self._details.setStyleSheet("background: transparent;")
        self._index: dict[str, int] = {}
        for ver in self._versions:
            self._index[ver.version] = self._details.addWidget(zone_defilable(self._detail(ver)))
        racine.addWidget(self._details, stretch=1)

    def _rail(self) -> QFrame:
        rail = QFrame()
        rail.setObjectName("rail")
        rail.setFixedWidth(_LARGEUR_RAIL)
        lay = QVBoxLayout(rail)
        lay.setContentsMargins(18, 22, 18, 20)
        lay.setSpacing(6)

        retour = QPushButton(tr("Bibliothèque"))
        retour.setObjectName("retour")
        retour.setFont(police(13))
        retour.setIcon(QIcon(pixmap_icone("retour", 16, QColor("#a9a7c4"))))
        retour.setIconSize(QSize(16, 16))
        retour.setCursor(Qt.CursorShape.PointingHandCursor)
        retour.setAutoDefault(False)
        retour.clicked.connect(self.accept)
        lay.addWidget(retour, alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addSpacing(14)

        identite = QHBoxLayout()
        identite.setSpacing(14)
        identite.addWidget(_Jaquette(self.game.cover_image), alignment=Qt.AlignmentFlag.AlignTop)
        noms = QVBoxLayout()
        noms.setSpacing(4)
        nom = QLabel(self.game.name)
        nom.setTextFormat(Qt.TextFormat.PlainText)   # le nom vient du CATALOGUE
        nom.setWordWrap(True)
        nom.setFont(cinzel(11, bold=True))
        nom.setStyleSheet("color: #f4f2f8; background: transparent;")
        nom.setMinimumWidth(1)
        noms.addWidget(nom)
        noms.addWidget(surtitre(tr("Versions")))
        identite.addLayout(noms, stretch=1)
        lay.addLayout(identite)
        lay.addSpacing(18)

        self._groupe = QButtonGroup(self)
        self._groupe.setExclusive(True)
        for ver in self._versions:
            ligne = _LigneVersion(ver, ver.version == self._installed_version,
                                  ver.version == self.game.recommended_version)
            ligne.toggled.connect(lambda oui, v=ver.version: oui and self._montrer(v))
            self._groupe.addButton(ligne)
            self._lignes[ver.version] = ligne
            lay.addWidget(ligne)
        lay.addStretch()
        return rail

    def _detail(self, ver: GameVersion) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(*_MARGES_PAGE)
        lay.setSpacing(0)

        tete = QHBoxLayout()
        tete.setSpacing(24)
        gauche = QVBoxLayout()
        gauche.setSpacing(6)
        titre = QLabel(tr("Version {}").format(ver.version))
        titre.setTextFormat(Qt.TextFormat.PlainText)
        titre.setFont(cinzel_decorative(22))
        titre.setStyleSheet("color: #f4f2f8; background: transparent;")
        gauche.addWidget(titre)
        gauche.addWidget(texte(f"{date_longue(ver.date)} · {format_size(ver.size_mb)}",
                               15, "#a9a7c4"))
        tete.addLayout(gauche, stretch=1)
        tete.addLayout(self._etat(ver))
        lay.addLayout(tete)

        lay.addSpacing(22)
        filet = QFrame()
        filet.setObjectName("filetOr")
        filet.setFixedHeight(1)
        lay.addWidget(filet)
        lay.addSpacing(22)

        if ver.changes:
            lay.addWidget(surtitre(tr("Ce qui change")))
            lay.addSpacing(12)
            puce = current_theme().accent
            for change in ver.changes:
                # Texte du catalogue DISTANT : échappé avant d'entrer en RichText.
                ligne = QLabel(f'<span style="color:{puce};">•</span>&nbsp;&nbsp;'
                               f'{html.escape(change, quote=False)}')
                ligne.setTextFormat(Qt.TextFormat.RichText)
                ligne.setWordWrap(True)
                ligne.setFont(police(16))
                ligne.setStyleSheet("color: #e4e2ef; background: transparent;")
                lay.addWidget(ligne)
                lay.addSpacing(8)
        lay.addStretch()
        return page

    def _etat(self, ver: GameVersion) -> QVBoxLayout:
        """Ce que cette version est pour le joueur, ou le bouton qui y mène."""
        col = QVBoxLayout()
        col.setSpacing(8)
        col.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        if ver.version == self._installed_version:
            ligne = QHBoxLayout()
            ligne.setSpacing(8)
            coche = QLabel()
            coche.setPixmap(pixmap_icone("coche", 18, QColor(_VERT)))
            coche.setStyleSheet("background: transparent;")
            ligne.addWidget(coche)
            ligne.addWidget(texte(tr("C'est la version installée"), 15, _VERT))
            col.addLayout(ligne)
            return col
        if not ver.is_available:
            col.addWidget(texte(tr("Pas encore en ligne"), 14, ENCRE_DOUCE),
                          alignment=Qt.AlignmentFlag.AlignRight)
            return col
        if self._installed_version is None:
            libelle = tr("Installer v{}").format(ver.version)
        elif compare_versions(ver.version, self._installed_version) > 0:
            libelle = tr("Mettre à jour vers v{}").format(ver.version)
        else:
            libelle = tr("Revenir à v{}").format(ver.version)
        btn = bouton(libelle, principal=True)
        btn.setAutoDefault(False)
        btn.clicked.connect(lambda _c=False, v=ver.version: self._on_install_version(v))
        self._actions[ver.version] = btn
        col.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)
        if self._installed_version is not None:
            col.addWidget(texte(tr("Vos sauvegardes et vos réglages restent."), 13, _VERT),
                          alignment=Qt.AlignmentFlag.AlignRight)
        return col

    # ── Navigation ──

    def choisir(self, version: str) -> None:
        ligne = self._lignes.get(version)
        if ligne is not None:
            ligne.setChecked(True)

    def _montrer(self, version: str) -> None:
        self._details.setCurrentIndex(self._index[version])

    def action(self, version: str) -> QPushButton | None:
        """Le bouton de la page de `version` ; None si elle est installée ou pas en ligne."""
        return self._actions.get(version)

    def _on_install_version(self, version: str) -> None:
        action = tr("installer")
        if self._installed_version is not None:
            action = tr("supprimer la version actuelle et installer")

        # Pas de `QMessageBox.question` : ses boutons Yes/No sont traduits par
        # les fichiers `qtbase_<langue>.qm` de Qt, que le build écarte — d'où
        # un « Yes » anglais dans un launcher réglé en français. Et son texte
        # reste en `AutoText` alors qu'il interpole un numéro de version venu
        # du catalogue DISTANT, donc de l'extérieur.
        boite = FenetreMessage(self)
        boite.setIcon(FenetreMessage.Icon.Question)
        boite.setWindowTitle(tr("Confirmer"))
        boite.setText(
            tr("Ceci va {} la version {}.\nContinuer ?").format(action, version))
        installer = boite.addButton(tr("Installer cette version"),
                                    FenetreMessage.ButtonRole.AcceptRole)
        annuler = boite.addButton(tr("Annuler"),
                                  FenetreMessage.ButtonRole.RejectRole)
        boite.setDefaultButton(annuler)
        boite.exec()
        if boite.clickedButton() is installer:
            self.switch_to_version.emit(self.game.id, version)
            self.accept()
