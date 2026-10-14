"""L'atelier des artistes, en PAGE : les métiers à gauche, leur liste à droite.

Maquette « L'atelier, tous les métiers » validée par Ludo le 2026-10-14. Elle
remplace l'encadré « Vous dessinez ? » d'À propos, qui ne parlait que des
jaquettes et des fonds, et qu'on ne trouvait qu'en allant au bout des
Paramètres. L'atelier s'ouvre depuis « Contribuer », dans la barre du haut, et
depuis la pastille de la fiche quand l'image du jeu affiché cherche un artiste.

Contenu : `src/core/atelier.py`. Le rail reprend celui des réglages du jeu et
des versions (même style, même retour « Bibliothèque »).
"""

from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QImageReader
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

from src.core import atelier
from src.core.config import ASSETS_DIR
from src.core.i18n import tr
from src.core.liens import DISCORD_URL
from src.ui.composants import ENCRE, ENCRE_DOUCE, Rangee, bouton, feuille_de_style, police, surtitre, texte
from src.ui.fonts import cinzel_decorative
from src.ui.icon_button import pixmap_icone
from src.ui.reglages_widgets import _STYLE as _STYLE_RAIL
from src.ui.theme import current as current_theme, themed
from src.ui.utils import open_url, zone_defilable

_LARGEUR_RAIL = 300
_MARGES_PAGE = (48, 32, 48, 32)

_STYLE = """
QPushButton#metier {
    background: transparent; border: 1px solid transparent; border-radius: 8px;
    min-height: 54px; max-height: 54px;
}
QPushButton#metier:hover { background: rgba(255, 255, 255, 0.04); }
QPushButton#metier:checked {
    background: rgba(214, 167, 44, 0.09); border-color: rgba(214, 167, 44, 0.45);
}
QPushButton#metier[focusClavier="true"]:focus { border: 2px solid #d6a72c; }
QFrame#format {
    background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 13px;
}
QFrame#besoins {
    background: #0d0d1a; border: 1px solid rgba(214, 167, 44, 0.16); border-radius: 12px;
}
QFrame#filetBesoin { background: rgba(255, 255, 255, 0.06); border: none; }
QFrame#etape {
    background: rgba(214, 167, 44, 0.05); border: 1px solid rgba(214, 167, 44, 0.22);
    border-radius: 10px;
}
"""


def _taille(chemin: Path) -> tuple[int, int]:
    """Lue dans l'en-tête du fichier, sans décoder l'image."""
    taille = QImageReader(str(chemin)).size()
    return (taille.width(), taille.height()) if taille.isValid() else (0, 0)


def besoins_mesures(jeux) -> list[atelier.Besoin]:
    """Les jaquettes et fonds du catalogue à refaire, avec leurs mots traduits."""
    tailles = {g.id: (_taille(ASSETS_DIR / "covers" / g.cover_image),
                      _taille(ASSETS_DIR / "backgrounds" / f"{g.id}_bg.jpg")) for g in jeux}
    return atelier.besoins_mesures(tailles, {
        atelier.JAQUETTE: tr("Jaquette"),
        atelier.FOND: tr("Fond d'écran"),
        "carree": tr("Carrée aujourd'hui"),
        "taille": tr("{} × {} aujourd'hui"),
        "priorite": tr("en priorité"),
    })


def libelle_etat(etat: str) -> tuple[str, str, str]:
    """(libellé, encre, fond) de la pastille d'un besoin."""
    if etat == atelier.COURS:
        return tr("En cours"), "#b9ccff", "rgba(157,184,255,0.14)"
    if etat == atelier.FAIT:
        return tr("Fait"), "#7be0a4", "rgba(46,204,113,0.14)"
    return tr("Cherche un artiste"), current_theme().accent_light, "rgba(214,167,44,0.14)"


def _pastille(libelle: str, encre: str, fond: str, px: int = 12) -> QLabel:
    lbl = QLabel(libelle)
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    lbl.setFont(police(px))
    lbl.setStyleSheet(f"color: {encre}; background: {fond}; border-radius: 10px; padding: 3px 9px;")
    lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return lbl


class _LigneMetier(QPushButton):
    """Le nom du métier, où se voit son travail dessous, ce qui attend à droite."""

    def __init__(self, metier: atelier.Metier) -> None:
        super().__init__()
        self.setObjectName("metier")
        self.setCheckable(True)
        self.setAutoDefault(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.metier = metier
        self.setAccessibleName(f"{metier.nom}, {metier.ou}, {metier.ouverts}")
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 7, 12, 7)
        h.setSpacing(10)
        gauche = QVBoxLayout()
        gauche.setSpacing(2)
        nom = texte(metier.nom, 15, ENCRE)
        nom.setFont(police(15, gras=True))
        gauche.addWidget(nom)
        gauche.addWidget(texte(metier.ou, 12, ENCRE_DOUCE))
        h.addLayout(gauche, stretch=1)
        # En Gelasio : le « 1 » de Cinzel se lit « I ».
        compte = texte(str(metier.ouverts), 15, current_theme().accent_light)
        compte.setFont(police(15, gras=True))
        h.addWidget(compte, alignment=Qt.AlignmentFlag.AlignVCenter)
        for enfant in self.findChildren(QLabel):
            enfant.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


class AtelierPage(QDialog):
    """Ce que les artistes peuvent refaire, métier par métier."""

    def __init__(self, jeux, parent: QWidget | None = None, metier: str = "") -> None:
        super().__init__(parent)
        self.setObjectName("atelier")
        self.setWindowTitle(tr("L'atelier"))
        self.setMinimumSize(900, 560)
        self.setStyleSheet(themed(_STYLE_RAIL + _STYLE) + feuille_de_style())
        self.metiers = atelier.charger(besoins_mesures(jeux))
        self._lignes: dict[str, _LigneMetier] = {}
        self._index: dict[str, int] = {}

        racine = QHBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(0)
        racine.addWidget(self._rail())
        self._details = QStackedWidget()
        self._details.setStyleSheet("background: transparent;")
        for m in self.metiers:
            self._index[m.id] = self._details.addWidget(zone_defilable(self._detail(m)))
        racine.addWidget(self._details, stretch=1)
        if self.metiers:
            self.choisir(metier if metier in self._index else self.metiers[0].id)

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
        lay.addSpacing(16)
        lay.addWidget(surtitre(tr("L'atelier")))
        lay.addSpacing(4)
        # Ludo, 2026-10-14 : refaire à l'identique en meilleure qualité est aussi
        # bienvenu que tout réinventer, cinématiques comprises.
        lay.addWidget(texte(tr("Tout ce qui se voit peut être refait : à l'identique en "
                               "meilleure qualité, ou tout autrement. Choisissez votre métier."),
                            14, "#c9c7da", retour=True))
        lay.addSpacing(12)

        self._groupe = QButtonGroup(self)
        self._groupe.setExclusive(True)
        for m in self.metiers:
            ligne = _LigneMetier(m)
            ligne.toggled.connect(lambda oui, c=m.id: oui and self._montrer(c))
            self._groupe.addButton(ligne)
            self._lignes[m.id] = ligne
            lay.addWidget(ligne)
        lay.addStretch()
        lay.addWidget(texte(tr("Chaque contribution entre au générique d'À propos."), 12,
                            ENCRE_DOUCE, retour=True))
        return rail

    def _detail(self, metier: atelier.Metier) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(*_MARGES_PAGE)
        lay.setSpacing(0)

        titre = QLabel(metier.nom)
        titre.setTextFormat(Qt.TextFormat.PlainText)
        titre.setWordWrap(True)
        titre.setFont(cinzel_decorative(22))
        titre.setStyleSheet("color: #f4f2f8; background: transparent;")
        lay.addWidget(titre)
        lay.addSpacing(10)
        lay.addWidget(texte(metier.texte, 16, "#c9c7da", retour=True))
        lay.addSpacing(16)

        if metier.formats:
            formats = QHBoxLayout()
            formats.setSpacing(8)
            for f in metier.formats:
                formats.addWidget(_pastille(f, "#dcdaea", "rgba(255,255,255,0.05)", 13))
            formats.addStretch()
            lay.addLayout(formats)
            lay.addSpacing(8)
        lay.addWidget(texte(tr("Sous licence CC BY 4.0, sans logo de Warner ou d'EA. Les "
                               "personnages des jeux, oui ; les visages des acteurs des films, "
                               "non."), 13, ENCRE_DOUCE, retour=True))
        lay.addSpacing(20)

        cadre = QFrame()
        cadre.setObjectName("besoins")
        liste = QVBoxLayout(cadre)
        liste.setContentsMargins(20, 8, 20, 8)
        liste.setSpacing(0)
        for i, besoin in enumerate(metier.besoins):
            if i:
                filet = QFrame()
                filet.setObjectName("filetBesoin")
                filet.setFixedHeight(1)
                liste.addWidget(filet)
            liste.addWidget(self._ligne_besoin(besoin))
        lay.addWidget(cadre)
        lay.addSpacing(26)
        lay.addWidget(self._etapes())
        lay.addStretch()
        return page

    @staticmethod
    def _ligne_besoin(besoin: atelier.Besoin) -> QWidget:
        ligne = QWidget()
        ligne.setObjectName("besoin")
        h = QHBoxLayout(ligne)
        h.setContentsMargins(0, 12, 0, 12)
        h.setSpacing(16)
        jeu = texte(besoin.jeu, 15, current_theme().accent_light)
        jeu.setFont(police(15, gras=True))
        jeu.setFixedWidth(64)
        h.addWidget(jeu, alignment=Qt.AlignmentFlag.AlignTop)
        quoi = QVBoxLayout()
        quoi.setSpacing(2)
        quoi.addWidget(texte(besoin.quoi, 15, ENCRE, retour=True))
        if besoin.detail:
            quoi.addWidget(texte(besoin.detail, 13, ENCRE_DOUCE, retour=True))
        h.addLayout(quoi, stretch=1)
        h.addWidget(_pastille(*libelle_etat(besoin.etat)), alignment=Qt.AlignmentFlag.AlignVCenter)
        return ligne

    def _etapes(self) -> QWidget:
        """Les trois temps d'une contribution ; le dernier mène au Discord."""
        cartes = []
        for numero, (titre, corps) in enumerate((
                (tr("Réservez"), tr("Dites sur le Discord ce que vous prenez : la ligne passera "
                                    "« en cours » à la mise à jour suivante.")),
                (tr("Au format du jeu"), tr("Gardez le format indiqué plus haut. Les fichiers "
                                            "d'origine se demandent sur le Discord.")),
                (tr("Partagez"), "")), start=1):
            carte = QFrame()
            carte.setObjectName("etape")
            v = QVBoxLayout(carte)
            v.setContentsMargins(16, 14, 16, 16)
            v.setSpacing(6)
            tete = texte(f"{numero}. {titre}", 15, ENCRE)
            tete.setFont(police(15, gras=True))
            v.addWidget(tete)
            if corps:
                v.addWidget(texte(corps, 13, "#c4c2da", retour=True))
            else:
                v.addWidget(texte(tr("Envoyez votre travail sur le Discord, avec le nom "
                                     "à mettre au générique."), 13, "#c4c2da", retour=True))
                discord = bouton(tr("Ouvrir le Discord"), principal=True)
                discord.setAutoDefault(False)
                discord.clicked.connect(lambda: open_url(DISCORD_URL))
                v.addWidget(discord, alignment=Qt.AlignmentFlag.AlignLeft)
            v.addStretch()
            cartes.append(carte)
        rangee = Rangee(cartes, 3, seuil=760, ecart=12)
        # Le ressort de chaque carte la rendait extensible : la rangée mangeait
        # tout le bas de la page au lieu de le laisser au ressort de la page.
        rangee.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        return rangee

    # ── Navigation ──

    def choisir(self, metier: str) -> None:
        ligne = self._lignes.get(metier)
        if ligne is not None:
            ligne.setChecked(True)

    def _montrer(self, metier: str) -> None:
        self._details.setCurrentIndex(self._index[metier])

    @property
    def metier_affiche(self) -> str:
        return next((c for c, i in self._index.items() if i == self._details.currentIndex()), "")

