"""Composants communs des pages : surtitre, carte, ligne de réglage, boutons.
Toutes les pages s'en servent, pour qu'aucune ne parle une autre langue visuelle.

Les couleurs sont écrites dans la palette Poudlard et passent par `themed()` :
une maison les remplace toutes d'un coup.
"""

import shutil
from html import escape
from pathlib import Path

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from src.ui.fonts import body_font, cinzel
from src.ui.icon_button import pixmap_icone
from src.ui.theme import RAYON_CARTE, RAYON_CONTROLE, current, rayon_pastille, themed

# Encres des pages, du plus lu au plus discret.
ENCRE = "#f2f2f4"
ENCRE_DOUCE = "#8f8db0"
# Remontée le 2026-10-29 (audit, choix de Ludo) : #6f6d8e faisait 3,05 sur
# `bg_card`, sous le seuil AA de 4,5. `test_contraste` tient le seuil.
ENCRE_DISCRETE = "#8c8aa5"
# L'icône d'une commande éteinte, l'encre du cadenas des Collections.
ENCRE_ETEINTE = "#5d5b72"

# Les pastilles cochables ont une hauteur FIXE : leur rayon en est la moitié
# (`theme.rayon_pastille`). Mesurées le 2026-11-12 avec les polices du projet :
# 28 px pour un filtre (police 13), 32 px pour une rubrique en pastille
# (police 14 et pictogramme de 18 px). 36 px pour une pastille à jaquette
# (`choix_jeux.pastille`, jaquette de 24 px) : à 28, la jaquette touchait le
# bord (1 px d'air) ; c'est la hauteur qu'elle avait avant la refonte.
HAUTEUR_FILTRE = 28
HAUTEUR_FILTRE_GRAND = 32
HAUTEUR_FILTRE_JAQUETTE = 36
_TAILLE_ROND = 38
# Le pictogramme du retour et des rubriques d'un rail, au repos.
_ENCRE_RAIL = "#a9a7c4"
# Les liens (audit UI v57, Ludo 2026-11-13) : onze présentations différentes, dont des liens
# or sans soulignement que Ludo ne reconnaissait pas comme des liens (ASTeam, 2026-10-14).
# Un lien est OR et SOULIGNÉ ; une action secondaire (« Désinstaller… ») est un lien gris.
ENCRE_LIEN_DISCRET = "#a9a7c4"

# Trois rayons seulement (`theme`) : commande, carte, pastille. Les rubriques
# d'un rail, le retour et les filtres vivent ICI : chaque page en gardait sa
# copie (`retour` six fois, `rubrique` et `filtre` trois), et elles divergeaient.
_STYLE = f"""
QFrame#carte {{
    background: #0d0d1a;
    border: 1px solid rgba(214, 167, 44, 0.14);
    border-radius: {RAYON_CARTE}px;
}}
QFrame#separateur {{ background: rgba(255, 255, 255, 0.06); border: none; }}
QPushButton#principal, QPushButton#secondaire {{
    min-height: 34px; max-height: 34px; padding: 0 16px; border-radius: {RAYON_CONTROLE}px;
}}
QPushButton#principal {{
    color: #ecdcb0; background: rgba(214, 167, 44, 0.06);
    border: 1px solid rgba(214, 167, 44, 0.35);
}}
QPushButton#secondaire {{
    color: #d9d6e8; background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.14);
}}
QPushButton#principal:hover, QPushButton#secondaire:hover {{
    border-color: #d6a72c;
}}
QPushButton#principal:disabled, QPushButton#secondaire:disabled {{
    color: #6f6d8e; border-color: rgba(255, 255, 255, 0.08);
}}
QPushButton#danger {{
    min-height: 34px; max-height: 34px; padding: 0 16px; border-radius: {RAYON_CONTROLE}px;
    color: #f6d2cd; background: rgba(224, 88, 79, 0.10);
    border: 1px solid rgba(224, 88, 79, 0.60);
}}
QPushButton#danger:hover {{ background: rgba(224, 88, 79, 0.20); border-color: #e0584f; }}
QPushButton#rond {{
    background: transparent; border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: {rayon_pastille(_TAILLE_ROND)}px;
}}
QPushButton#rond:hover {{ border-color: #d6a72c; }}
QPushButton#rond:disabled {{ border-color: rgba(255, 255, 255, 0.06); }}
QPushButton#retour {{
    background: transparent; border: none; color: {_ENCRE_RAIL};
    text-align: left; padding: 4px 2px;
}}
QPushButton#retour:hover {{ color: #f2f2f4; }}
QPushButton#rubrique {{
    color: {_ENCRE_RAIL}; background: transparent; border: none;
    border-left: 2px solid transparent; border-radius: {RAYON_CONTROLE}px;
    text-align: left; padding: 0 14px;
}}
QPushButton#rubrique:hover {{ color: #f2f2f4; background: rgba(255, 255, 255, 0.04); }}
QPushButton#rubrique:checked {{
    color: #f2e6c4; background: rgba(214, 167, 44, 0.10);
    border-left: 2px solid #d6a72c;
}}
QPushButton#filtre {{
    background: transparent; border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: {rayon_pastille(HAUTEUR_FILTRE)}px; color: #c9c7da; padding: 0 13px;
}}
QPushButton#filtre[grand="true"] {{
    border-radius: {rayon_pastille(HAUTEUR_FILTRE_GRAND)}px; padding: 0 16px;
}}
QPushButton#filtre[jaquette="true"] {{ border-radius: {rayon_pastille(HAUTEUR_FILTRE_JAQUETTE)}px; }}
QPushButton#filtre[vide="true"] {{ color: #8c8aa5; border-color: rgba(255, 255, 255, 0.07); }}
QPushButton#filtre:hover {{ color: #f2f2f4; }}
QPushButton#filtre:checked {{
    background: rgba(214, 167, 44, 0.14); border-color: rgba(214, 167, 44, 0.6); color: #f2e6c4;
}}
QPushButton#lien, QPushButton#lienDiscret {{
    background: transparent; border: none; text-decoration: underline; padding: 4px 2px;
    text-align: left;
}}
QPushButton#lien {{ color: #d6a72c; }}
QPushButton#lien:hover {{ color: #e8c547; }}
QPushButton#lienDiscret {{ color: {ENCRE_LIEN_DISCRET}; }}
QPushButton#lienDiscret:hover {{ color: #f2f2f4; }}
QPushButton#lien:disabled, QPushButton#lienDiscret:disabled {{ color: {ENCRE_ETEINTE}; }}
"""

# Les listes déroulantes. `LISTE` : celle des pages (réglages d'un jeu,
# Collections), basse et sobre, alignée en colonne avec les interrupteurs.
# `LISTE_HAUTE` : celle des Paramètres et des copies de sauvegarde.
# Le focus clavier et la ligne choisie d'une liste ouverte, en OR : `outline`
# n'est pas peint sur une QComboBox (la règle globale de styles.py ne s'y
# voyait pas), et la ligne choisie, #2c3e6b sur #16213e, ne se distinguait
# pas des autres. Mesuré sur capture, Ludo à la manette le 2026-10-07 : « tout
# n'est pas mis en évidence, surtout les paramètres graphiques et dropdown ».
# Le cadre passe à 2 px et le remplissage perd 1 px : rien ne bouge.
# `::drop-down` retire le bouton natif : sans lui, sa flèche restait sous le
# chevron que peint `utils._ListeDeroulante` (deux flèches superposées).
# La liste peint ses lignes elle-même : `selection-*` seul n'y changeait rien
# (ligne choisie au clavier, mesurée sans aucune différence de couleur).
_LIGNES_DE_LISTE = (
    "QComboBox::drop-down { border: none; width: 18px; }"
    "QComboBox QAbstractItemView::item { padding: 4px 8px; }"
    "QComboBox QAbstractItemView::item:selected { background: rgba(214, 167, 44, 0.30);"
    " color: #f0d060; }"
)
LISTE = (
    "QComboBox { background: #15152a; color: #e4e2ef; border: 1px solid rgba(255,255,255,0.13);"
    f" border-radius: {RAYON_CONTROLE}px; padding: 3px 10px; min-height: 22px; }}"
    "QComboBox:hover { border-color: rgba(214,167,44,0.55); }"
    "QComboBox:disabled { color: #6f6d8e; }"
    "QComboBox QAbstractItemView { background: #15152a; color: #e4e2ef; outline: none;"
    " selection-background-color: rgba(214, 167, 44, 0.30); selection-color: #f0d060; }"
    + _LIGNES_DE_LISTE
)
LISTE_HAUTE = (
    "QComboBox { background: #16213e; color: #ffffff; border: 1px solid #2c3e6b;"
    f" border-radius: {RAYON_CONTROLE}px; padding: 6px 12px; font-size: 13px; }}"
    "QComboBox QAbstractItemView { background: #16213e; color: #ffffff; outline: none;"
    " selection-background-color: rgba(214, 167, 44, 0.30); selection-color: #f0d060; }"
    + _LIGNES_DE_LISTE
)


def feuille_de_style() -> str:
    """À poser une fois sur la fenêtre qui accueille les composants."""
    return themed(_STYLE)


def police(px: int, gras: bool = False) -> QFont:
    """Gelasio à une taille en PIXELS : les maquettes sont cotées en px."""
    f = body_font()
    f.setPixelSize(px)
    if gras:
        f.setWeight(QFont.Weight.DemiBold)
    return f


class Paragraphe(QLabel):
    """Texte en `wordWrap` dont la hauteur suit la largeur RÉELLE (règle 38).

    Un `QLabel` à la ligne annonce un `sizeHint` calculé à une largeur qui n'est
    pas la sienne : le layout ne lui accorde qu'une ligne et le texte se coupe
    (« Désinstaller » : la phrase sur les jeux réduite à sa première ligne, dans
    les trois langues). Sa hauteur minimale se recalcule à chaque largeur reçue
    et à chaque texte posé après coup.
    """

    def __init__(self, contenu: str = "") -> None:
        super().__init__(contenu)
        self.setWordWrap(True)

    def setText(self, contenu: str) -> None:
        super().setText(contenu)
        self._suivre()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._suivre()

    def _suivre(self) -> None:
        self.setMinimumHeight(0)
        self.setMinimumHeight(max(0, self.heightForWidth(self.width())))


def transparent(widget: QWidget, nom: str) -> None:
    """Un conteneur sans fond. La règle porte son NOM : sans sélecteur, elle
    s'applique aussi à TOUS ses enfants et gagne sur la feuille de la fenêtre. Elle
    effaçait le fond des cartes de la Difficulté, le fond doré de « Suivant » dans
    l'assistant, le rail, les cartes des Paramètres, le filet du Journal des
    changements et la pastille des sorts appris du Folio (audit UI, 2026-11-13)."""
    widget.setObjectName(nom)
    widget.setStyleSheet(f"QWidget#{nom} {{ background: transparent; }}")


def survol(p: QPainter, case: QPushButton, rayon: float) -> None:
    """Pour une case PEINTE (règle 15) : le survol l'éclaire. Les cases du folio ne changeaient
    pas au survol (audit UI, 2026-11-13). La case pose `WA_Hover` ; son rayon sert aussi à
    l'anneau du clavier (`focus_visible.forme`)."""
    if case.underMouse():
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 26))
        p.drawRoundedRect(QRectF(case.rect()).adjusted(1, 1, -1, -1), rayon, rayon)


def texte(contenu: str, px: int = 13, encre: str = ENCRE,
          retour: bool = False) -> QLabel:
    """Un libellé en texte BRUT : rien de ce qu'il reçoit n'est interprété."""
    lbl = Paragraphe(contenu) if retour else QLabel(contenu)
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    lbl.setFont(police(px))
    lbl.setStyleSheet(f"color: {encre}; background: transparent;")
    return lbl


def surtitre(contenu: str, *, a_la_ligne: bool = False) -> QLabel:
    """Le petit titre doré en capitales espacées qui annonce une carte.

    `a_la_ligne` : dans un rail étroit, « JOURNAL DES CHANGEMENTS » se coupait en
    « JOURNAL DES CHANGEM » (2026-11-01) ; il passe à la ligne comme le nom du jeu."""
    lbl = QLabel(contenu.upper())
    if a_la_ligne:
        lbl.setWordWrap(True)
        lbl.setMinimumWidth(1)
    f = cinzel(8, bold=True)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.5)
    lbl.setFont(f)
    lbl.setStyleSheet(themed("color: #d6a72c; background: transparent;"))
    lbl.setContentsMargins(2, 0, 0, 0)
    return lbl


def petit_titre(contenu: str) -> QLabel:
    """Le titre gris DANS une carte (« SE DÉPLACER », « CONTOURS »).

    8 pt et 1,8 px d'espacement (2026-11-12, constat tra16) : à 7 pt (9,3 px à
    100 %) et 2,2 px, les capitales espacées se lisaient mal."""
    lbl = QLabel(contenu.upper())
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    f = cinzel(8, bold=True)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.8)
    lbl.setFont(f)
    lbl.setStyleSheet(f"color: {ENCRE_DOUCE}; background: transparent; border: none;")
    return lbl


class Rangee(QWidget):
    """Des blocs côte à côte, empilés quand la place manque.

    `seuil` est la largeur sous laquelle tout passe en une colonne : trois
    cartes de touches de 200 px ne tiennent pas dans une fenêtre réduite, et
    les écraser couperait leurs libellés. `etirements` donne la part de chaque
    colonne quand elles sont côte à côte.
    """

    def __init__(self, blocs: list[QWidget], colonnes: int, seuil: int,
                 etirements: tuple[int, ...] = (), ecart: int = 16) -> None:
        super().__init__()
        self.setStyleSheet("background: transparent;")
        self._blocs = list(blocs)
        self._colonnes = colonnes
        self._seuil = seuil
        self._etirements = etirements or (1,) * colonnes
        self._grille = QGridLayout(self)
        self._grille.setContentsMargins(0, 0, 0, 0)
        self._grille.setHorizontalSpacing(ecart)
        self._grille.setVerticalSpacing(ecart)
        self._n = 0
        self._poser(colonnes)

    def colonnes(self) -> int:
        return self._n

    def _poser(self, n: int) -> None:
        if n == self._n:
            return
        self._n = n
        for bloc in self._blocs:
            self._grille.removeWidget(bloc)
        for c in range(self._colonnes):
            self._grille.setColumnStretch(c, self._etirements[c] if n > 1 else (1 if c == 0 else 0))
        for rang, bloc in enumerate(self._blocs):
            ligne, col = divmod(rang, n)
            self._grille.addWidget(bloc, ligne, col, Qt.AlignmentFlag.AlignTop if n == 1 else
                                   Qt.AlignmentFlag(0))

    def _largeur_cote_a_cote(self) -> int:
        """Ce que demandent VRAIMENT les blocs côte à côte : jamais moins que le seuil."""
        mini = sum(b.minimumSizeHint().width() for b in self._blocs[:self._colonnes])
        return max(self._seuil, mini + self._grille.horizontalSpacing() * (self._colonnes - 1))

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt)
        """Le minimum d'UNE colonne : annoncer celui des blocs côte à côte
        bloquerait la zone défilante à cette largeur, et la rangée ne
        s'empilerait plus jamais."""
        largeur = max((b.minimumSizeHint().width() for b in self._blocs), default=0)
        return QSize(largeur, super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().resizeEvent(event)
        large = event.size().width() >= self._largeur_cote_a_cote()
        self._poser(self._colonnes if large else 1)


def bouton(libelle: str, principal: bool = False) -> QPushButton:
    """Bouton de page : bordé d'or s'il fait l'action de la ligne, gris sinon."""
    btn = QPushButton(libelle)
    btn.setObjectName("principal" if principal else "secondaire")
    btn.setFont(police(13, gras=True))
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


def icone_de_bouton(nom: str, taille: int, couleur: QColor | None = None) -> QIcon:
    """Le pictogramme d'un bouton, avec sa version éteinte : celle que Qt fabrique
    sortait aussi claire que l'allumée, (237, 237, 237) sur capture."""
    icone = QIcon(pixmap_icone(nom, taille, couleur or QColor("#e6e4f0")))
    icone.addPixmap(pixmap_icone(nom, taille, QColor(ENCRE_ETEINTE)), QIcon.Mode.Disabled)
    return icone


def rond(icone: str, libelle: str, action, bulle: str = "") -> QPushButton:
    """Un bouton rond à icône seule, comme la barre des bandes-annonces (Ludo, 2026-11-08)."""
    b = QPushButton()
    b.setObjectName("rond")
    b.setFixedSize(38, 38)
    b.setIcon(icone_de_bouton(icone, 16))
    b.setIconSize(QSize(16, 16))
    b.setAutoDefault(False)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setToolTip(bulle or libelle)
    b.setAccessibleName(libelle)
    b.clicked.connect(action)
    return b


def lien(libelle: str, *, discret: bool = False) -> QPushButton:
    """Le lien du launcher : or et souligné, ou gris s'il est `discret`. Feuille : `feuille_de_style`."""
    btn = QPushButton(libelle)
    btn.setObjectName("lienDiscret" if discret else "lien")
    btn.setFont(police(13))
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setAutoDefault(False)
    return btn


def html_lien(cible: str, contenu: str, *, discret: bool = False) -> str:
    """Le même lien dans un texte riche. `contenu` est du HTML déjà échappé ; `cible` l'est ici."""
    encre = ENCRE_LIEN_DISCRET if discret else current().accent
    return (f'<a href="{escape(cible)}" style="color:{encre}; text-decoration:underline;">'
            f"{contenu}</a>")


def bouton_retour(libelle: str, action) -> QPushButton:
    """« ← Bibliothèque » en tête d'une page : un lien gris, pas un bouton bordé."""
    b = QPushButton(libelle)
    b.setObjectName("retour")
    b.setFont(police(13))
    b.setIcon(QIcon(pixmap_icone("retour", 16, QColor(_ENCRE_RAIL))))
    b.setIconSize(QSize(16, 16))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setAutoDefault(False)
    b.clicked.connect(action)
    return b


def bouton_rubrique(libelle: str, icone: str, taille_icone: int = 20,
                    hauteur: int = 44) -> QPushButton:
    """Une rubrique d'un rail vertical (Paramètres, réglages d'un jeu) : cochable,
    son pictogramme gris au repos, dans l'accent du thème une fois choisie."""
    pictogramme = QIcon()
    pictogramme.addPixmap(pixmap_icone(icone, taille_icone, QColor(_ENCRE_RAIL)),
                          QIcon.Mode.Normal, QIcon.State.Off)
    pictogramme.addPixmap(pixmap_icone(icone, taille_icone, QColor(current().accent_light)),
                          QIcon.Mode.Normal, QIcon.State.On)
    b = QPushButton(libelle)
    b.setObjectName("rubrique")
    b.setCheckable(True)
    b.setIcon(pictogramme)
    b.setIconSize(QSize(taille_icone, taille_icone))
    b.setFont(police(14))
    b.setFixedHeight(hauteur)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setAutoDefault(False)
    return b


def filtre(libelle: str, grand: bool = False) -> QPushButton:
    """Une pastille cochable : un filtre (« Tous », un jeu), ou, `grand`, une
    rubrique posée en ligne en tête d'une page (Carnet, Collections)."""
    b = QPushButton(libelle)
    b.setObjectName("filtre")
    b.setProperty("grand", grand)
    b.setCheckable(True)
    b.setAutoDefault(False)
    b.setFont(police(14 if grand else 13))
    b.setFixedHeight(HAUTEUR_FILTRE_GRAND if grand else HAUTEUR_FILTRE)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


class Carte(QFrame):
    """Un bloc bordé qui empile des lignes, un filet entre chacune."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("carte")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)

    def ajouter(self, widget: QWidget) -> QWidget:
        if self._lay.count():
            filet = QFrame()
            filet.setObjectName("separateur")
            filet.setFixedHeight(1)
            self._lay.addWidget(filet)
        self._lay.addWidget(widget)
        return widget


class LigneReglage(QWidget):
    """Titre, phrase d'aide facultative, et les commandes à droite.

    La phrase reste accessible (`description`) : certaines lignes la changent
    selon l'état (espace occupé, bandes-annonces présentes). Le titre peut être
    un widget déjà construit (le chemin coupé au milieu des Paramètres).
    """

    def __init__(self, titre: str | QWidget, description: str = "", *commandes: QWidget,
                 icone: QWidget | None = None) -> None:
        super().__init__()
        self.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 14, 20, 14)
        lay.setSpacing(18)
        if icone is not None:
            lay.addWidget(icone, alignment=Qt.AlignmentFlag.AlignVCenter)
        colonne = QVBoxLayout()
        colonne.setSpacing(3)
        self.titre = titre if isinstance(titre, QWidget) else texte(titre, 14)
        self.titre.setMinimumWidth(1)
        colonne.addWidget(self.titre)
        self.description = texte(description, 13, ENCRE_DOUCE, retour=True)
        colonne.addWidget(self.description)
        lay.addLayout(colonne, stretch=1)
        # APRÈS l'avoir rattachée : un widget sans parent rendu visible devient
        # une FENÊTRE (huit petites fenêtres et 0,5 s à l'ouverture des Paramètres).
        self.description.setVisible(bool(description))
        for commande in commandes:
            lay.addWidget(commande, alignment=Qt.AlignmentFlag.AlignVCenter)

    def decrire(self, contenu: str) -> None:
        self.description.setText(contenu)
        self.description.setVisible(bool(contenu))


def espace_du_volume(path: Path) -> tuple[int, int]:
    """(octets libres, octets au total) du volume ; (0, 0) si illisible.

    Le dossier n'existe pas forcément encore (rien d'installé) : c'est son
    plus proche parent existant qui dit sur quel volume il tombera.
    """
    while not path.exists() and path.parent != path:
        path = path.parent
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return 0, 0
    return usage.free, usage.total


class Pastille(QWidget):
    """Le petit carré de couleur d'une légende."""

    def __init__(self, couleur: QColor) -> None:
        super().__init__()
        self._couleur = couleur
        self.setFixedSize(9, 9)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._couleur)
        p.drawRoundedRect(QRectF(self.rect()), 2, 2)
        p.end()


class Chemin(QLabel):
    """Le chemin du dossier, coupé AU MILIEU s'il ne tient pas.

    Il se cassait juste après « C: » en retour à la ligne (maquette « avant »).
    Coupé au milieu, on garde le lecteur ET le nom du dossier ; le chemin
    complet reste dans l'infobulle.
    """

    def __init__(self, chemin: str, px: int = 14, encre: str = ENCRE) -> None:
        super().__init__()
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setFont(police(px))
        self.setStyleSheet(f"color: {encre}; background: transparent;")
        self.setMinimumWidth(1)
        self.definir(chemin)

    def definir(self, chemin: str) -> None:
        self._chemin = chemin
        self.setToolTip(chemin)
        self._couper()

    def text(self) -> str:  # le chemin ENTIER, pas sa forme coupée
        return self._chemin

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._couper()

    def _couper(self) -> None:
        super().setText(self.fontMetrics().elidedText(
            self._chemin, Qt.TextElideMode.ElideMiddle, max(1, self.width())))

    def sizeHint(self) -> QSize:
        return QSize(self.fontMetrics().horizontalAdvance(self._chemin),
                     super().sizeHint().height())
