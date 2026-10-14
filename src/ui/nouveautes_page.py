"""La page « Nouveautés » du launcher (contenu : `src/core/nouveautes.py`).

Maquette validée par Ludo le 2026-10-14 : trois cartes pour ce qui se voit le
plus, puis la liste, chaque ligne marquée de ce qu'elle est (nouveau, amélioré,
corrigé). Ouverte seule au premier lancement d'une version plus récente, et à
la demande depuis le numéro de version d'À propos.

Une PAGE à la place de la bibliothèque (`pages.py`), comme Mes années : pas une
fenêtre posée sur la fiche, qu'on fermerait sans la lire.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from src.core.i18n import tr
from src.core.liens import NOTES_VERSIONS_URL
from src.core.nouveautes import Changement, Nouveautes, PointFort
from src.ui.composants import (
    ENCRE_DOUCE,
    Rangee,
    bouton,
    feuille_de_style,
    police,
    surtitre,
    texte,
)
from src.ui.fonts import cinzel, cinzel_decorative
from src.ui.icon_button import pixmap_icone
from src.ui.theme import accent_qcolor, current as current_theme, themed
from src.ui.utils import open_url, zone_defilable

_MARGES = (64, 30, 64, 28)

_STYLE = """
QDialog#nouveautes { background: #060611; }
QFrame#pointFort {
    background: #0d0d1a; border: 1px solid rgba(214, 167, 44, 0.22); border-radius: 12px;
}
QFrame#filetOr { background: rgba(214, 167, 44, 0.14); border: none; }
QLabel#toutesLesVersions { color: #a9a7c4; }
"""


def _libelle_genre(genre: str) -> tuple[str, str]:
    """(libellé, couleur) de la marque d'une ligne."""
    if genre == "nouveau":
        return tr("Nouveau"), "#9db8ff"
    if genre == "ameliore":
        return tr("Amélioré"), current_theme().accent_light
    return tr("Corrigé"), "#7be0a4"


class _CartePointFort(QFrame):
    def __init__(self, point: PointFort) -> None:
        super().__init__()
        self.setObjectName("pointFort")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(10)
        icone = QLabel()
        icone.setPixmap(pixmap_icone(point.icone, 26, accent_qcolor()))
        icone.setStyleSheet("background: transparent; border: none;")
        lay.addWidget(icone)
        titre = QLabel(point.titre)
        titre.setTextFormat(Qt.TextFormat.PlainText)
        titre.setWordWrap(True)
        titre.setFont(cinzel(12, bold=True))
        titre.setStyleSheet("color: #f2f2f4; background: transparent; border: none;")
        lay.addWidget(titre)
        corps = texte(point.texte, 15, "#c9c7da", retour=True)
        corps.setStyleSheet(corps.styleSheet() + " border: none;")
        lay.addWidget(corps)
        lay.addStretch()


class _LigneChangement(QWidget):
    def __init__(self, changement: Changement) -> None:
        super().__init__()
        self.genre = changement.genre
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)
        libelle, couleur = _libelle_genre(changement.genre)
        marque = QLabel(libelle.upper())
        marque.setTextFormat(Qt.TextFormat.PlainText)
        f = cinzel(8, bold=True)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        marque.setFont(f)
        marque.setStyleSheet(f"color: {couleur}; background: transparent;")
        # Une colonne de marques alignée : la largeur de la plus longue des trois.
        largeur = max(marque.fontMetrics().horizontalAdvance(_libelle_genre(g)[0].upper()) + 8
                      for g in ("nouveau", "ameliore", "corrige"))
        marque.setFixedWidth(largeur)
        marque.setContentsMargins(0, 4, 0, 0)
        h.addWidget(marque, alignment=Qt.AlignmentFlag.AlignTop)
        phrase = texte(changement.texte, 15, "#dcdaea", retour=True)
        # En haut : sa voisine de colonne peut faire deux lignes, et une phrase
        # centrée dans la hauteur commune décrochait de sa marque.
        phrase.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        h.addWidget(phrase, stretch=1)


class NouveautesPage(QDialog):
    """Ce qu'apporte la version installée du launcher."""

    def __init__(self, nouveautes: Nouveautes, apres_mise_a_jour: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("nouveautes")
        self.nouveautes = nouveautes
        self.setWindowTitle(tr("Nouveautés"))
        self.setStyleSheet(themed(_STYLE) + feuille_de_style())
        racine = QVBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(0)
        racine.addWidget(zone_defilable(self._contenu(apres_mise_a_jour)), stretch=1)
        racine.addWidget(self._pied())

    def _contenu(self, apres_mise_a_jour: bool) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(_MARGES[0], _MARGES[1], _MARGES[2], 0)
        lay.setSpacing(0)

        tete = QHBoxLayout()
        tete.setSpacing(24)
        gauche = QVBoxLayout()
        gauche.setSpacing(8)
        gauche.addWidget(surtitre(tr("Mise à jour installée") if apres_mise_a_jour
                                  else tr("Nouveautés")))
        titre = QLabel(tr("Accio Launcher {}").format(self.nouveautes.version))
        titre.setTextFormat(Qt.TextFormat.PlainText)
        titre.setFont(cinzel_decorative(24))
        titre.setStyleSheet("color: #f4f2f8; background: transparent;")
        gauche.addWidget(titre)
        if self.nouveautes.nom:
            nom = QLabel(self.nouveautes.nom)
            nom.setObjectName("nomVersion")
            nom.setTextFormat(Qt.TextFormat.PlainText)
            nom.setFont(cinzel(15, bold=True))
            nom.setStyleSheet(f"color: {current_theme().accent}; background: transparent;")
            gauche.addWidget(nom)
        phrases = []
        if self.nouveautes.depuis:
            phrases.append(tr("Ce qui change depuis la {}.").format(self.nouveautes.depuis))
        if apres_mise_a_jour:
            phrases.append(tr("Rien à faire de votre côté : vos jeux et vos réglages sont là."))
        if phrases:
            gauche.addWidget(texte(" ".join(phrases), 15, "#a9a7c4", retour=True))
        tete.addLayout(gauche, stretch=1)
        lien = QLabel(f'<a href="{NOTES_VERSIONS_URL}" style="color:#a9a7c4;">'
                      f'{tr("Toutes les versions")}</a>')
        lien.setObjectName("toutesLesVersions")
        lien.setTextFormat(Qt.TextFormat.RichText)
        lien.setFont(police(14))
        lien.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse
                                     | Qt.TextInteractionFlag.LinksAccessibleByKeyboard)
        lien.linkActivated.connect(open_url)
        tete.addWidget(lien, alignment=Qt.AlignmentFlag.AlignBottom)
        lay.addLayout(tete)

        if self.nouveautes.points_forts:
            lay.addSpacing(24)
            cartes = [_CartePointFort(p) for p in self.nouveautes.points_forts]
            lay.addWidget(Rangee(cartes, len(cartes), seuil=720, ecart=18))
        if self.nouveautes.changements:
            lay.addSpacing(26)
            lignes = [_LigneChangement(c) for c in self.nouveautes.changements]
            liste = Rangee(lignes, 2, seuil=760, ecart=12)
            liste.layout().setHorizontalSpacing(48)
            lay.addWidget(liste)
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
        h.setSpacing(24)
        h.addWidget(texte(tr("Cette page revient dans Paramètres › À propos, en cliquant "
                             "sur le numéro de version."), 14, ENCRE_DOUCE, retour=True),
                    stretch=1)
        aller = bouton(tr("Aller à la bibliothèque"), principal=True)
        aller.setAutoDefault(False)
        aller.clicked.connect(self.accept)
        h.addWidget(aller)
        v.addLayout(h)
        return pied
