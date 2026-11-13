"""Le journal des changements d'un jeu, en PAGE : les versions à gauche, ce
que chacune a changé à droite.

Refaite le 2026-10-14 d'après la maquette « Versions d'un jeu » validée par
Ludo. L'ancienne boîte de 550 × 500 empilait toutes les versions, chacune avec
son bouton : pour lire ce qu'apporte la 1.3, il fallait faire défiler la 1.0,
et quatre boutons « Revenir à… » se ressemblaient. Ici on choisit une version
dans le rail ; la page dit ce qu'elle change et porte UN bouton, qui dit ce
qui va arriver.

Le rail reprend celui des réglages du jeu (retour « Bibliothèque », jaquette,
nom) : deux pages d'un même jeu se reconnaissent.

Lecture seule depuis le 2026-10-30 (Ludo) : une seule archive par jeu à
partir du correctif 2.3.0, puisque nos ajouts s'activent dans les réglages.
Revenir à une ancienne version n'est plus proposé ; le catalogue garde ses
versions passées pour ce journal, et la fiche met à jour vers la
recommandée (`GameOperations.mettre_a_jour`).
"""

import html
from collections.abc import Callable
from datetime import date

from PyQt6.QtCore import QDate, QLocale, Qt
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
from src.ui.composants import (
    bouton_retour,
    ENCRE,
    ENCRE_DOUCE,
    feuille_de_style,
    police,
    surtitre,
    texte,
    transparent,
)
from src.ui.entree_focus import entree_suit_le_focus
from src.ui.fonts import cinzel, cinzel_decorative
from src.ui.reglages_widgets import _STYLE as _STYLE_RAIL, _Jaquette
from src.ui.theme import RAYON_CONTROLE, current as current_theme, themed
from src.ui.utils import zone_defilable

_LARGEUR_RAIL = 300
_MARGES_PAGE = (48, 32, 48, 32)
_VERT = "#7be0a4"

_STYLE = f"""
QPushButton#version {{
    background: transparent; border: 1px solid transparent; border-radius: {RAYON_CONTROLE}px;
    min-height: 58px; max-height: 58px;
}}
QPushButton#version:hover {{ background: rgba(255, 255, 255, 0.04); }}
QPushButton#version:checked {{
    background: rgba(214, 167, 44, 0.09); border-color: rgba(214, 167, 44, 0.45);
}}
QPushButton#version[focusClavier="true"]:focus {{ border: 2px solid #d6a72c; }}
QFrame#filetOr {{ background: rgba(214, 167, 44, 0.16); border: none; }}
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
    """« 01/10/2026 » ; « 2026-10-01 » en anglais, où « 01/10 » se lit 10 janvier
    (grand audit du 2026-11-02) ; la chaîne du catalogue telle quelle si elle ne se lit pas."""
    d = _jour(date_str)
    if d is None:
        return date_str
    return d.isoformat() if get_language() == "en" else d.strftime("%d/%m/%Y")


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
        # Installée ET recommandée, c'est le cas normal (règle 107) ; à côté de
        # « Installée », « Recommandée » était rogné dans sa pastille (rail de 300 px).
        recommandee = recommandee and not installee
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
    """Le journal des changements d'un jeu, version par version. Rien ne s'y
    installe : on ne revient plus à une ancienne archive (2026-10-30)."""

    def __init__(self, game: GameData, manager: GameManager, parent: QWidget | None = None,
                 retour: tuple[str, Callable[[], None]] | None = None) -> None:
        """`retour` : (libellé, rappel) quand la page ne ramène pas à la bibliothèque."""
        super().__init__(parent)
        entree_suit_le_focus(self)
        self.game = game
        self.manager = manager
        self._libelle_retour, self._au_retour = retour or (tr("Bibliothèque"), None)
        self._installed_version = manager.installed_version(game.id)
        # Les plus récentes d'abord (parsing tolérant aux dates cassées).
        self._versions = sorted(game.versions, key=lambda v: _date_sort_key(v.date), reverse=True)
        self._lignes: dict[str, _LigneVersion] = {}

        self.setWindowTitle(tr("Journal des changements de {}").format(game.name))
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
        transparent(self._details, "details")
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

        retour = bouton_retour(self._libelle_retour, self.reject)
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
        noms.addWidget(surtitre(tr("Journal des changements"), a_la_ligne=True))
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
        transparent(page, "pageVersion")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(*_MARGES_PAGE)
        lay.setSpacing(0)

        gauche = QVBoxLayout()
        gauche.setSpacing(6)
        titre = QLabel(tr("Version {}").format(ver.version))
        titre.setTextFormat(Qt.TextFormat.PlainText)
        titre.setFont(cinzel_decorative(22))
        titre.setStyleSheet("color: #f4f2f8; background: transparent;")
        gauche.addWidget(titre)
        gauche.addWidget(texte(f"{date_longue(ver.date)} · {format_size(ver.size_mb)}",
                               15, "#a9a7c4"))
        lay.addLayout(gauche)

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

    # ── Navigation ──

    def reject(self) -> None:
        """Le bouton de retour et Échap : d'abord fermer, puis rouvrir d'où l'on
        vient, sinon la page rouverte se poserait sur celle-ci."""
        super().reject()
        rappel, self._au_retour = self._au_retour, None
        if rappel is not None:
            rappel()

    def choisir(self, version: str) -> None:
        ligne = self._lignes.get(version)
        if ligne is not None:
            ligne.setChecked(True)

    def _montrer(self, version: str) -> None:
        self._details.setCurrentIndex(self._index[version])
