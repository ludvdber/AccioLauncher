"""Le relevé de scolarité : une ligne par jeu, rangée sous son année.

Remplace l'étagère des huit jaquettes et la bande des sept années (refonte du
2026-10-09, maquette « Mes années » validée par Ludo). Les deux disaient la
même chose en deux endroits ; le relevé le dit une fois, avec les chiffres.

· **Toujours huit lignes**, jouées ou non : la structure ne dépend pas des
  données (une page qui change de forme a l'air cassée bien avant d'avoir l'air
  pauvre). Un jeu jamais lancé dit « Pas encore lancé », sans zéro.
· **L'année VII a deux jeux** : la partie 2 se range sous la partie 1, reliée
  par un trait, sans second chiffre romain. Le rang vient de `annee` dans le
  catalogue, jamais de la position (règle « le SENS d'un jeu, pas son RANG »).
· **Hors des cours** : un jeu sans `annee` (le Quidditch, le jour où il entre au
  catalogue) a sa section, qui ne compte pas dans les sept années. Elle
  n'apparaît que s'il y a un tel jeu : une section vide serait une promesse.
· On CHOISIT une ligne (souris, ↑/↓, Début/Fin) : ses sauvegardes s'affichent
  en dessous. Seuls les jeux qui ont quelque chose à dire se laissent choisir.
"""

from datetime import date
from html import escape

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImageReader, QLinearGradient, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from src.core.config import ASSETS_DIR
from src.core.formatting import format_relative_date
from src.core.i18n import tr
from src.core.scolarite import ANNEES
from src.ui.focus_visible import PROPRIETE as _FOCUS_CLAVIER
from src.ui.fonts import body_font, cinzel
from src.ui.theme import accent_qcolor, current as theme_courant

_ROMAINS = ("I", "II", "III", "IV", "V", "VI", "VII")

# Colonnes, partagées par l'en-tête et chaque ligne : sans largeurs communes,
# les colonnes ne s'alignent pas d'une ligne à l'autre.
_COL_ANNEE = 52
_COL_TEMPS = 210
_COL_PARTIES = 64
_COL_DERNIERE = 136
_BARRE_MAX = 120
_JAQUETTE = (30, 42)
_HAUTEUR_LIGNE = 54
_ECART = 14
_GRIS = "#8f8db0"


def _jaquette(nom_fichier: str) -> QPixmap | None:
    """Réduite par le DÉCODEUR, comme le carrousel : décoder une jaquette de
    1024 px pour l'afficher à 42 coûterait l'ouverture de la page."""
    chemin = ASSETS_DIR / "covers" / nom_fichier
    if not chemin.exists():
        return None
    lecteur = QImageReader(str(chemin))
    source = lecteur.size()
    if source.isValid() and source.height() > 0:
        facteur = 2 * _JAQUETTE[1] / source.height()   # 2× : écrans à 200 %
        if facteur < 1.0:
            lecteur.setScaledSize(source * facteur)
    image = lecteur.read()
    return None if image.isNull() else QPixmap.fromImage(image)


class _Jaquette(QWidget):
    """La vignette, recadrée « par expansion » (les jaquettes carrées aussi)."""

    def __init__(self, pixmap: QPixmap | None, parent=None) -> None:
        super().__init__(parent)
        self._pm = pixmap
        self.setFixedSize(*_JAQUETTE)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        case = QRectF(self.rect())
        if self._pm is None or self._pm.isNull():
            p.fillRect(case, QColor(22, 33, 62))
        else:
            facteur = max(case.width() / self._pm.width(), case.height() / self._pm.height())
            dessine = QRectF(0, 0, self._pm.width() * facteur, self._pm.height() * facteur)
            dessine.moveCenter(case.center())
            p.setClipRect(case)
            p.drawPixmap(dessine, self._pm, QRectF(self._pm.rect()))
        p.end()


class _Barre(QWidget):
    """Le temps du jeu rapporté au jeu le plus joué : une longueur, pas un %."""

    def __init__(self, part: float, parent=None) -> None:
        super().__init__(parent)
        self._part = max(0.0, min(1.0, part))
        self.setFixedSize(_BARRE_MAX, 6)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(accent_qcolor(200))
        largeur = max(3.0, self.width() * self._part)
        p.drawRoundedRect(QRectF(0, 0, largeur, self.height()), 3, 3)
        p.end()


class _Nom(QLabel):
    """Nom du jeu, ÉLIDÉ à la largeur reçue, le nom entier en infobulle.

    PlainText (règle 57) et infobulle échappée : une infobulle est un QLabel
    en AutoText, le seul endroit où du balisage du catalogue serait interprété.
    """

    def __init__(self, nom: str, parent=None) -> None:
        super().__init__(parent)
        self._nom = nom
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setFont(body_font(14))
        self.setToolTip(escape(nom, quote=False))
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(60)
        self.setText(nom)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.setText(self.fontMetrics().elidedText(
            self._nom, Qt.TextElideMode.ElideRight, self.width()))


def _cellule(texte: str, largeur: int, *, droite: bool = False,
             couleur: str = "#f2f2f4", italique: bool = False) -> QLabel:
    lbl = QLabel(texte)
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    lbl.setFont(body_font(13))
    style = f"color: {couleur}; background: transparent;"
    if italique:
        style += " font-style: italic;"
    lbl.setStyleSheet(style)
    lbl.setFixedWidth(largeur)
    if droite:
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return lbl


def _quand(jour: date) -> str:
    texte = format_relative_date(jour.isoformat())
    return texte[:1].upper() + texte[1:]


class _Ligne(QWidget):
    """Une ligne du relevé. Peinte : le fond de la ligne choisie et le trait
    qui relie la partie 2 de l'année VII à la partie 1."""

    def __init__(self, releve: "_Releve", game_id: str, *, rattachee: bool) -> None:
        super().__init__(releve)
        self._releve = releve
        self.game_id = game_id
        self._rattachee = rattachee
        self.setFixedHeight(_HAUTEUR_LIGNE)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._releve.choisir(self.game_id)
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        if self.game_id == self._releve.choix:
            fond = QLinearGradient(r.topLeft(), r.topRight())
            fond.setColorAt(0.0, accent_qcolor(28))
            fond.setColorAt(1.0, accent_qcolor(0))
            p.fillRect(r, fond)
            p.fillRect(QRectF(0, 0, 2, r.height()), accent_qcolor())
            if self._releve.hasFocus() and self._releve.property(_FOCUS_CLAVIER):
                p.setPen(QPen(accent_qcolor(170), 1, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(r.adjusted(0.5, 0.5, -0.5, -0.5))
        if self._rattachee:
            # Le coude de la partie 2 vers la partie 1, dans la colonne des années.
            p.setPen(QPen(accent_qcolor(110), 1))
            x = 22.5
            p.drawLine(int(x), -1, int(x), int(r.height() / 2))
            p.drawLine(int(x), int(r.height() / 2), int(x) + 12, int(r.height() / 2))
        p.setPen(QPen(QColor(255, 255, 255, 14), 1))
        p.drawLine(0, int(r.height()) - 1, int(r.width()), int(r.height()) - 1)
        p.end()


class _Releve(QWidget):
    """Les jeux, rangés par année de scolarité, dont on choisit un."""

    choisi = pyqtSignal(str)

    def __init__(self, entrees, temps: dict[str, int], parties: dict[str, int],
                 dernieres: dict[str, date], legendes: dict[str, str],
                 selectionnables: set[str], choix: str | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self._entrees = list(entrees)
        self._legendes = legendes
        self._selectionnables = selectionnables
        self._choix = choix if choix in selectionnables else None
        self._lignes: list[_Ligne] = []
        if selectionnables:
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.setAccessibleName(tr("Relevé de scolarité"))

        couche = QVBoxLayout(self)
        couche.setContentsMargins(0, 0, 0, 0)
        couche.setSpacing(0)
        couche.addWidget(self._entete())

        temps_max = max(temps.values(), default=0)
        scolaires = sorted((e for e in self._entrees if 1 <= e.game.annee <= ANNEES),
                           key=lambda e: e.game.annee)
        hors = [e for e in self._entrees if not 1 <= e.game.annee <= ANNEES]
        annee_vue = 0
        for e in scolaires:
            rattachee = e.game.annee == annee_vue
            annee_vue = e.game.annee
            couche.addWidget(self._ligne(e.game, temps, parties, dernieres, temps_max,
                                         annee=None if rattachee else e.game.annee,
                                         rattachee=rattachee))
        if hors:
            couche.addSpacing(18)
            couche.addWidget(self._titre_hors_des_cours())
            for e in hors:
                couche.addWidget(self._ligne(e.game, temps, parties, dernieres,
                                             temps_max, annee=None, rattachee=False))

    # ──────────────────── Construction ────────────────────

    @staticmethod
    def _entete() -> QWidget:
        entete = QWidget()
        rang = QHBoxLayout(entete)
        rang.setContentsMargins(0, 0, 0, 8)
        rang.setSpacing(_ECART)
        style = f"color: {_GRIS}; letter-spacing: 2px; background: transparent;"
        for texte, largeur, droite in ((tr("Année"), _COL_ANNEE, False),
                                       (tr("Jeu"), 0, False),
                                       (tr("Temps de jeu"), _COL_TEMPS, False),
                                       (tr("Parties"), _COL_PARTIES, True),
                                       (tr("Dernière session"), _COL_DERNIERE, True)):
            lbl = QLabel(texte.upper())
            lbl.setTextFormat(Qt.TextFormat.PlainText)
            lbl.setFont(cinzel(8, bold=True))
            lbl.setStyleSheet(style)
            if largeur:
                lbl.setFixedWidth(largeur)
            if droite:
                lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            rang.addWidget(lbl, 0 if largeur else 1)
        return entete

    @staticmethod
    def _titre_hors_des_cours() -> QWidget:
        bloc = QWidget()
        rang = QHBoxLayout(bloc)
        rang.setContentsMargins(0, 0, 0, 4)
        rang.setSpacing(14)
        titre = QLabel(tr("Hors des cours").upper())
        titre.setFont(cinzel(8, bold=True))
        titre.setStyleSheet(f"color: {_GRIS}; letter-spacing: 2px;")
        rang.addWidget(titre)
        filet = QWidget()
        filet.setFixedHeight(1)
        filet.setStyleSheet("background: rgba(255,255,255,0.08);")
        rang.addWidget(filet, 1)
        note = QLabel(tr("ne compte pas dans les sept années"))
        note.setFont(body_font(12))
        note.setStyleSheet("color: #6f6d8e; font-style: italic;")
        rang.addWidget(note)
        return bloc

    def _ligne(self, game, temps, parties, dernieres, temps_max, *,
               annee: int | None, rattachee: bool) -> _Ligne:
        gid = game.id
        ligne = _Ligne(self, gid, rattachee=rattachee)
        if gid in self._selectionnables:
            ligne.setCursor(Qt.CursorShape.PointingHandCursor)
        rang = QHBoxLayout(ligne)
        rang.setContentsMargins(0, 0, 0, 0)
        rang.setSpacing(_ECART)

        romain = QLabel(_ROMAINS[annee - 1] if annee else "")
        romain.setFont(cinzel(13, bold=True))
        romain.setFixedWidth(_COL_ANNEE)
        romain.setContentsMargins(12, 0, 0, 0)
        romain.setStyleSheet(f"color: {theme_courant().accent}; background: transparent;")
        rang.addWidget(romain)

        jeu = QWidget()
        jeu_rang = QHBoxLayout(jeu)
        jeu_rang.setContentsMargins(0, 0, 0, 0)
        jeu_rang.setSpacing(12)
        jeu_rang.addWidget(_Jaquette(_jaquette(game.cover_image)))
        jeu_rang.addWidget(_Nom(game.name), 1)
        rang.addWidget(jeu, 1)

        secondes = temps.get(gid, 0)
        if secondes:
            from src.ui.stats_widgets import _duree
            bloc = QWidget()
            bloc.setFixedWidth(_COL_TEMPS)
            bloc_rang = QHBoxLayout(bloc)
            bloc_rang.setContentsMargins(0, 0, 0, 0)
            bloc_rang.setSpacing(12)
            bloc_rang.addWidget(_Barre(secondes / temps_max if temps_max else 0))
            valeur = QLabel(_duree(secondes))
            valeur.setFont(body_font(13))
            valeur.setStyleSheet("color: #f2f2f4;")
            bloc_rang.addWidget(valeur, 1)
            rang.addWidget(bloc)
        elif self._legendes.get(gid):
            # Des sauvegardes, aucun temps chronométré : la même convention que
            # le reste de la page, un tiret, jamais une estimation.
            rang.addWidget(_cellule(self._legendes[gid], _COL_TEMPS, couleur=_GRIS))
        else:
            rang.addWidget(_cellule(tr("Pas encore lancé"), _COL_TEMPS,
                                    couleur=_GRIS, italique=True))

        n = parties.get(gid, 0)
        rang.addWidget(_cellule(str(n) if n else "", _COL_PARTIES, droite=True))
        jour = dernieres.get(gid)
        rang.addWidget(_cellule(_quand(jour) if jour else "", _COL_DERNIERE, droite=True,
                                couleur="#a9a7c4"))
        self._lignes.append(ligne)
        return ligne

    # ──────────────────── Choix ────────────────────

    @property
    def choix(self) -> str | None:
        return self._choix

    def choisir(self, game_id: str) -> None:
        if game_id in self._selectionnables and game_id != self._choix:
            self._choix = game_id
            for ligne in self._lignes:
                ligne.update()
            self.choisi.emit(game_id)

    def _ordre(self) -> list[str]:
        """L'ordre d'AFFICHAGE (par année), pas celui du catalogue."""
        return [ligne.game_id for ligne in self._lignes
                if ligne.game_id in self._selectionnables]

    def keyPressEvent(self, event) -> None:
        ordre = self._ordre()
        if not ordre:
            super().keyPressEvent(event)
            return
        pos = ordre.index(self._choix) if self._choix in ordre else -1
        touche = event.key()
        if touche in (Qt.Key.Key_Down, Qt.Key.Key_Right):
            cible = ordre[min(pos + 1, len(ordre) - 1)]
        elif touche in (Qt.Key.Key_Up, Qt.Key.Key_Left):
            cible = ordre[max(pos - 1, 0)]
        elif touche == Qt.Key.Key_Home:
            cible = ordre[0]
        elif touche == Qt.Key.Key_End:
            cible = ordre[-1]
        else:
            super().keyPressEvent(event)
            return
        self.choisir(cible)

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        for ligne in self._lignes:
            ligne.update()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        for ligne in self._lignes:
            ligne.update()
