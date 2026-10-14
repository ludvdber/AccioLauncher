"""« Vous dessinez ? » : l'appel aux artistes, dans À propos (2026-10-09).

Les illustrations d'Accio viennent d'où elles ont pu, et certaines ne sont pas
faites pour lui : des fonds trop petits pour un grand écran, des jaquettes
carrées dans un carrousel en portrait. L'appel dit LESQUELLES, d'après leurs
dimensions (`src/core/images_a_refaire.py`) : il se raccourcit tout seul à
mesure que les images arrivent, et disparaît quand il n'y a plus rien à faire.

Les conditions sont celles du cahier des charges : sous licence CC BY 4.0,
sans logo de Warner ou d'EA ni visage d'acteur. Les artistes retenus entrent
au générique, juste au-dessus.
"""

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImageReader
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from src.core.config import ASSETS_DIR
from src.core.images_a_refaire import FOND, JAQUETTE, a_refaire
from src.core.i18n import tr
from src.core.liens import DISCORD_URL
from src.ui.composants import ENCRE, ENCRE_DOUCE, bouton, feuille_de_style, police, texte
from src.ui.icon_button import pixmap_icone
from src.ui.theme import accent_qcolor, themed
from src.ui.utils import open_url


def _taille(chemin: Path) -> tuple[int, int]:
    """Lue dans l'en-tête du fichier, sans décoder l'image."""
    taille = QImageReader(str(chemin)).size()
    return (taille.width(), taille.height()) if taille.isValid() else (0, 0)


def besoins(jeux) -> list[tuple[str, str]]:
    """[(nom du jeu, « jaquette » | « fond »)] pour les jeux du catalogue."""
    noms = {g.id: g.name for g in jeux}
    tailles = {g.id: (_taille(ASSETS_DIR / "covers" / g.cover_image),
                      _taille(ASSETS_DIR / "backgrounds" / f"{g.id}_bg.jpg")) for g in jeux}
    return [(noms[jeu], quoi) for jeu, quoi in a_refaire(tailles)]


def construire(jeux) -> QFrame | None:
    """Le cadre de l'appel ; None quand toutes les images sont à la hauteur."""
    manques = besoins(jeux)
    if not manques:
        return None
    cadre = QFrame()
    cadre.setObjectName("appelArtistes")
    cadre.setStyleSheet(themed(
        "QFrame#appelArtistes { background: rgba(214, 167, 44, 0.05);"
        " border: 1px solid rgba(214, 167, 44, 0.30); border-radius: 10px; }"
        " QFrame#appelArtistes QLabel { border: none; }") + feuille_de_style())
    lay = QVBoxLayout(cadre)
    lay.setContentsMargins(20, 16, 20, 18)
    lay.setSpacing(8)

    tete = QHBoxLayout()
    tete.setSpacing(12)
    icone = QLabel()
    icone.setStyleSheet("background: transparent;")
    icone.setPixmap(pixmap_icone("infos", 20, accent_qcolor()))
    tete.addWidget(icone, alignment=Qt.AlignmentFlag.AlignTop)
    titre = texte(tr("Vous dessinez ?"), 16, ENCRE)
    titre.setFont(police(16, gras=True))
    tete.addWidget(titre, stretch=1)
    lay.addLayout(tete)
    lay.addWidget(texte(tr(
        "Certaines images d'Accio ne sont pas à la hauteur des jeux : trop petites "
        "pour un grand écran, ou carrées dans un carrousel en portrait. Une illustration "
        "faite pour le launcher les remplacerait, et son auteur entrerait au générique."),
        13, "#c4c2da", retour=True))

    lay.addSpacing(4)
    for nom, quoi in manques:
        ligne = QHBoxLayout()
        ligne.setSpacing(8)
        genre = texte(tr("Jaquette") if quoi == "jaquette" else tr("Fond d'écran"), 13,
                      QColor(accent_qcolor()).name())
        genre.setFixedWidth(110)
        ligne.addWidget(genre)
        ligne.addWidget(texte(nom, 13, ENCRE), stretch=1)
        lay.addLayout(ligne)
    lay.addSpacing(4)

    pied = QHBoxLayout()
    pied.setSpacing(14)
    pied.addWidget(texte(tr(
        "Jaquette : {jl} × {jh} px. Fond : {fl} × {fh} px. Sous licence CC BY 4.0, "
        "sans logo de Warner ou d'EA ni visage d'acteur.").format(
            jl=JAQUETTE[0], jh=JAQUETTE[1], fl=FOND[0], fh=FOND[1]),
        12, ENCRE_DOUCE, retour=True), stretch=1)
    proposer = bouton(tr("En parler sur le Discord"), principal=True)
    proposer.clicked.connect(lambda: open_url(DISCORD_URL))
    pied.addWidget(proposer, alignment=Qt.AlignmentFlag.AlignBottom)
    lay.addLayout(pied)
    return cadre
