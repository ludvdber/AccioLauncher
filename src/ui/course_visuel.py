"""Les pièces de dessin des trois écrans de la course (1.5), prises sur la maquette validée par Ludo (canevas
« Accio Launcher 1.5 — pages du mode course », 2026-11-25) : la page Course, le résultat, les Courses du Carnet.

Les mêmes partout, pour que les trois écrans se ressemblent : le panneau sombre bordé, la tuile « libellé gris,
valeur claire », le temps en chiffres alignés, l'alerte rouge avec son geste, le grand bouton or plein de
« Partir », le rond à initiale d'un joueur du classement, la pastille d'une catégorie qui porte son record.

Les chiffres des temps : Gelasio dessine par défaut des chiffres elzéviriens (le « 3 » et le « 9 » descendent
sous la ligne) et de largeurs inégales ; un temps se lit en chiffres ALIGNÉS de même chasse (`lnum`, `tnum`),
comme la police à chasse fixe de la maquette, sans charger une police de plus.
"""

import zlib

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QIcon
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from src.ui.composants import ENCRE, lien, police, transparent
from src.ui.fonts import cinzel
from src.ui.icon_button import pixmap_icone
from src.ui.theme import themed

OR = "#d6a72c"
OR_CLAIR = "#f0d060"
CREME = "#f4ecd0"
GRIS = "#9a9ab8"
GRIS_CLAIR = "#c9c9dc"
VERT = "#7fdcaa"
ROUGE = "#f39a8f"

# Les feuilles des pièces, à poser une fois sur la page (`themed` : l'or suit le thème).
STYLE = themed(f"""
QFrame#panneauCourse {{ background: rgba(13, 13, 26, 0.92); border: 1px solid #1f1f3a; border-radius: 10px; }}
QFrame#panneauOr {{ background: rgba(13, 13, 26, 0.92); border: 1px solid rgba(214, 167, 44, 0.4);
                    border-radius: 8px; }}
QFrame#tuileCourse {{ background: #11111f; border: 1px solid #22223a; border-radius: 6px; }}
QFrame#tuileOr {{ background: rgba(13, 13, 26, 0.92); border: 1px solid rgba(214, 167, 44, 0.4);
                  border-radius: 6px; }}
QFrame#alerteCourse {{ background: rgba(224, 122, 106, 0.10); border: 1px solid rgba(224, 122, 106, 0.45);
                       border-radius: 6px; }}
QFrame#bonneNouvelle {{ background: rgba(63, 191, 127, 0.10); border: 1px solid rgba(63, 191, 127, 0.45);
                        border-radius: 6px; }}
QFrame#placeCourse {{ background: rgba(214, 167, 44, 0.10); border: 1px solid rgba(214, 167, 44, 0.5);
                      border-radius: 8px; }}
QFrame#filetCourse {{ background: #1b1b33; border: none; }}
QFrame#ligneClassee {{ background: transparent; border: none; border-bottom: 1px solid #16162c; }}
QFrame#ligneClassee[vous="true"] {{ background: rgba(214, 167, 44, 0.12); border-radius: 4px; }}
QPushButton#partirCourse {{
    min-height: 48px; max-height: 48px; padding: 0 40px; border-radius: 4px; border: none;
    background: #d6a72c; color: #14110a;
}}
QPushButton#partirCourse:hover {{ background: #e8c547; }}
QPushButton#partirCourse:disabled {{ background: rgba(214, 167, 44, 0.18); color: #6f6d8e; }}
QPushButton#boutonOr {{
    min-height: 38px; max-height: 38px; padding: 0 24px; border-radius: 4px; border: none;
    background: #d6a72c; color: #14110a;
}}
QPushButton#boutonOr:hover {{ background: #e8c547; }}
QPushButton#boutonCadre {{
    min-height: 36px; max-height: 36px; padding: 0 16px; border-radius: 4px;
    background: transparent; border: 1px solid #3a3a58; color: #d4d4e4;
}}
QPushButton#boutonCadre:hover {{ border-color: #d6a72c; color: {ENCRE}; }}
QPushButton#boutonCadreOr {{
    min-height: 36px; max-height: 36px; padding: 0 16px; border-radius: 4px;
    background: transparent; border: 1px solid #d6a72c; color: #f0d060;
}}
QPushButton#boutonCadreOr:hover {{ background: rgba(214, 167, 44, 0.12); }}
""")

# Les fonds des ronds à initiale : ceux de la maquette, choisis par le nom du joueur (toujours le même rond pour
# le même joueur, d'une page à l'autre).
_FONDS_RONDS = ("#5865f2", "#b4508a", "#2f8a6c", "#8a5a2f", "#4a6aa8", "#7a4ab0", "#a8604a")


def chiffres(f: QFont) -> QFont:
    """La police avec des chiffres alignés et de même chasse : un temps qui change ne danse pas."""
    for etiquette in ("lnum", "tnum"):
        f.setFeature(QFont.Tag(etiquette), 1)
    return f


def libelle(contenu: str, px: int = 14, encre: str = ENCRE, *, retour: bool = False,
            gras: bool = False) -> QLabel:
    """Un libellé en texte BRUT (rien n'est interprété : noms du catalogue et du réseau)."""
    lbl = QLabel(contenu)
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    lbl.setFont(police(px, gras=gras))
    lbl.setStyleSheet(f"color: {encre}; background: transparent;")
    if retour:
        lbl.setWordWrap(True)
        lbl.setMinimumWidth(1)
    return lbl


def temps(contenu: str, px: int = 14, encre: str = CREME, *, gras: bool = False) -> QLabel:
    """Un temps, en chiffres alignés."""
    lbl = libelle(contenu, px, encre, gras=gras)
    lbl.setFont(chiffres(lbl.font()))
    return lbl


def grand_titre(contenu: str, px: int, encre: str = CREME) -> QLabel:
    """Un titre en Cinzel gras (nom de la catégorie, du jeu)."""
    lbl = libelle(contenu, px, encre, retour=True)
    f = cinzel(10, bold=True)
    f.setPixelSize(px)
    lbl.setFont(f)
    return lbl


def cadre(nom: str, marges: tuple[int, int, int, int] = (12, 10, 12, 10), espace: int = 4,
          horizontal: bool = False) -> tuple[QFrame, QVBoxLayout | QHBoxLayout]:
    """Un QFrame nommé (son style est dans `STYLE`) et sa mise en page."""
    f = QFrame()
    f.setObjectName(nom)
    lay: QVBoxLayout | QHBoxLayout = QHBoxLayout(f) if horizontal else QVBoxLayout(f)
    lay.setContentsMargins(*marges)
    lay.setSpacing(espace)
    return f, lay


def tuile(titre: str, valeur: str, *, valeur_temps: bool = False, valeur_px: int = 14, encre: str = CREME,
          nom: str = "tuileCourse") -> tuple[QFrame, QLabel]:
    """Libellé gris en haut, valeur claire dessous ; (la tuile, le libellé de la valeur)."""
    f, lay = cadre(nom, espace=2 if valeur_temps else 4)
    lay.addWidget(libelle(titre, 12, GRIS))
    v = temps(valeur, valeur_px, encre) if valeur_temps else libelle(valeur, valeur_px, encre, retour=True)
    lay.addWidget(v)
    lay.addStretch()
    return f, v


def alerte(phrase: str, geste: QPushButton | None = None) -> QFrame:
    """Ce qui empêche de partir : le triangle, la phrase, et le geste qui le règle quand il existe."""
    f, lay = cadre("alerteCourse", (12, 10, 12, 10), 12, horizontal=True)
    icone = QLabel()
    transparent(icone)
    icone.setPixmap(pixmap_icone("attention", 18, QColor("#e8968a")))
    lay.addWidget(icone, alignment=Qt.AlignmentFlag.AlignTop)
    lay.addWidget(libelle(phrase, 14, "#f2c4bc", retour=True), 1)
    if geste is not None:
        lay.addWidget(geste, alignment=Qt.AlignmentFlag.AlignVCenter)
    return f


def lien_or(contenu: str) -> QPushButton:
    """Le lien du launcher (`composants.lien` : or ET souligné, la seule présentation d'un lien, test_liens) à la
    taille des écrans de course. La maquette les dessinait sans soulignement : Ludo ne reconnaissait pas un lien
    or sans soulignement (2026-10-14), la règle du launcher l'emporte."""
    b = lien(contenu)
    b.setFont(police(14))
    b.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return b


def bouton_nomme(contenu: str, nom: str, px: int = 14, *, cinzel_gras: bool = False) -> QPushButton:
    """Un bouton dont le style est dans `STYLE` : `boutonOr`, `boutonCadre`, `boutonCadreOr`, `partirCourse`."""
    b = QPushButton(contenu)
    b.setObjectName(nom)
    if cinzel_gras:
        f = cinzel(10, bold=True)
        f.setPixelSize(px)
        b.setFont(f)
    else:
        b.setFont(police(px))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setAutoDefault(False)
    return b


def bouton_partir() -> QPushButton:
    """Le grand bouton or plein de la page Course, avec le chrono."""
    b = bouton_nomme("", "partirCourse", 17, cinzel_gras=True)
    # Le chrono, sombre sur l'or, et éteint quand le bouton l'est.
    icone = QIcon(pixmap_icone("chrono", 18, QColor("#14110a")))
    icone.addPixmap(pixmap_icone("chrono", 18, QColor("#6f6d8e")), QIcon.Mode.Disabled)
    b.setIcon(icone)
    return b


def rond(joueur: str, *, vous: bool = False, taille: int = 26) -> QLabel:
    """Le rond à initiale d'un joueur du classement (le classement ne porte pas encore les avatars du
    Discord) ; or pour le joueur lui-même."""
    initiale = next((c for c in joueur if c.isalnum()), "?").upper()
    fond = OR if vous else _FONDS_RONDS[zlib.crc32(joueur.encode("utf-8")) % len(_FONDS_RONDS)]
    lbl = QLabel(initiale)
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    lbl.setFixedSize(taille, taille)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setFont(police(11, gras=True))
    lbl.setStyleSheet(f"background: {fond}; color: {'#14110a' if vous else '#ffffff'};"
                      f" border-radius: {taille // 2}px;")
    return lbl


def ligne_classee(rang: int, joueur: str, contenu_temps: str, *, vous: bool = False,
                  apres: QWidget | None = None) -> QFrame:
    """Une ligne du classement : rang en or, rond, joueur (texte BRUT : il vient du réseau), temps."""
    f, lay = cadre("ligneClassee", (4, 7, 4, 7), 10, horizontal=True)
    f.setProperty("vous", vous)
    r = libelle(str(rang), 14, OR)
    r.setFont(cinzel(10, bold=True))
    r.setFixedWidth(24)
    lay.addWidget(r)
    lay.addWidget(rond(joueur, vous=vous))
    nom = libelle(joueur, 14, ENCRE)
    nom.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    lay.addWidget(nom, 1)
    lay.addWidget(temps(contenu_temps, 13, CREME))
    if apres is not None:
        lay.addWidget(apres)
    return f


def filet() -> QFrame:
    f = QFrame()
    f.setObjectName("filetCourse")
    f.setFixedHeight(1)
    return f
