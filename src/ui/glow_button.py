"""Boutons entièrement peints — le bouton principal de la fiche.

Deux variantes :
- "filled" : fond plein (JOUER, INSTALLER)
- "outline" : fond à peine teinté + bordure colorée (actions secondaires)

Le nom est historique. Le bouton portait un halo qui pulsait et un reflet qui le
traversait toutes les quelques secondes : retirés le 2026-10-14 à la demande de
Ludo, « le bouton télécharger fait vraiment virus ». Un gros bouton doré qui
scintille, c'est le code visuel des faux boutons de téléchargement des sites
douteux. Le halo, peint HORS du rectangle arrondi mais rogné au rectangle du
widget, laissait aussi un voile carré dans les quatre coins. Plus rien ne bouge
au repos : le survol éclaircit, l'appui assombrit, et c'est tout.
"""

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import (
    QColor, QEnterEvent, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import QPushButton, QWidget

from src.ui import theme


# Marge intérieure réservée au texte d'un GlowButton, en pixels logiques.
# Elle évite que l'élision ne colle le libellé au bord arrondi.
_MARGE_TEXTE = 20
# Écart entre le libellé et son détail (« INSTALLER   4,6 Go »). Un espace, pas
# un tiret cadratin : « TÉLÉCHARGER — 4,6 GO » faisait texte généré.
ECART_DETAIL = 14
# Le détail est lu après le libellé : même couleur, moins appuyée.
_OPACITE_DETAIL = 0.72


class GlowButton(QPushButton):
    """Bouton peint, deux styles : filled / outline.

    Sans `glow_color` / `bg_stops` explicites, l'accent du thème actif est
    utilisé (thèmes maisons). Les couleurs passées explicitement (JOUER vert)
    ne sont pas thématisées.

    `detail` : un complément plus discret à droite du libellé (le poids d'un
    jeu à installer), dans la police du texte courant.
    """

    def __init__(
        self,
        text: str,
        glow_color: str | None = None,
        style: str = "filled",
        bg_stops: tuple[str, str, str] | None = None,
        text_color: str | None = None,
        parent: QWidget | None = None,
        detail: str = "",
        detail_font: QFont | None = None,
    ) -> None:
        super().__init__(text, parent)
        palette = theme.current()
        if glow_color is None:
            glow_color = palette.accent
        self._style = style  # "filled" or "outline"
        self._glow_color = QColor(glow_color)
        self._detail = detail
        self._detail_font = detail_font

        if bg_stops:
            self._bg_top = QColor(bg_stops[0])
            self._bg_bot = QColor(bg_stops[2])
        else:
            self._bg_top = QColor(palette.accent)
            self._bg_bot = QColor(palette.accent_dark)

        if text_color:
            self._text_color = QColor(text_color)
        elif style == "outline":
            self._text_color = QColor(glow_color)
        else:
            self._text_color = QColor("#ffffff")

        self._hovered = False
        self._pressed = False

        self.setStyleSheet("QPushButton { background: transparent; border: none; }")

    def detail(self) -> str:
        return self._detail

    def police_detail(self) -> QFont:
        return self._detail_font if self._detail_font is not None else self.font()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        if not self.isEnabled():
            # INSTALLER hors ligne : plein et doré, il avait l'air cliquable.
            p.setOpacity(0.45)

        w = self.width()
        h = self.height()
        radius = 6.0
        # Tout ce qui est peint reste DANS le rectangle arrondi : rien ne
        # déborde vers les coins du widget.
        btn_rect = QRectF(0.5, 0.5, w - 1, h - 1)
        clip = QPainterPath()
        clip.addRoundedRect(btn_rect, radius, radius)
        p.setClipPath(clip)
        if self._style == "filled":
            self._paint_filled(p, h, btn_rect)
        else:
            self._paint_outline(p, btn_rect)
        p.setClipping(False)

        if self._style == "outline":
            r, g, b = self._glow_color.red(), self._glow_color.green(), self._glow_color.blue()
            p.setPen(QPen(QColor(r, g, b, 180 if self._hovered else 120), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(btn_rect, radius, radius)

        tc = QColor(self._text_color)
        if self._style == "outline" and self._hovered:
            tc = tc.lighter(130)
        self._paint_texte(p, tc, QRectF(0, 0, w, h))
        p.end()

    def _paint_texte(self, p: QPainter, couleur: QColor, rect: QRectF) -> None:
        """Libellé, et détail à sa droite, centrés ensemble.

        Élision — filet de sécurité. `drawText` centré ne coupe RIEN : un
        libellé plus large que le bouton déborde des DEUX côtés, hors du cadre
        dessiné, et le début du mot disparaît (constaté le 2026-08-20 sur le
        bouton de téléchargement, qui portait alors une durée estimée). Les
        appelants dimensionnent le bouton à son contenu (cf. ActionPanel) ;
        ceci garantit qu'aucun GlowButton ne déborde en silence, quelle que
        soit la traduction. Le détail cède sa place en premier.
        """
        dispo = max(0, int(rect.width()) - _MARGE_TEXTE)
        fm = self.fontMetrics()
        fm_detail = QFontMetrics(self.police_detail())
        detail = self._detail
        largeur_detail = fm_detail.horizontalAdvance(detail) if detail else 0
        if detail and fm.horizontalAdvance(self.text()) + ECART_DETAIL + largeur_detail > dispo:
            detail, largeur_detail = "", 0
        texte = fm.elidedText(self.text(), Qt.TextElideMode.ElideRight, dispo)
        if not detail:
            p.setPen(couleur)
            p.setFont(self.font())
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, texte)
            return
        largeur = fm.horizontalAdvance(texte)
        x = rect.x() + (rect.width() - largeur - ECART_DETAIL - largeur_detail) / 2
        p.setPen(couleur)
        p.setFont(self.font())
        p.drawText(QRectF(x, rect.y(), largeur, rect.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                   | Qt.TextFlag.TextDontClip, texte)
        p.save()
        p.setOpacity(p.opacity() * _OPACITE_DETAIL)
        p.setFont(self.police_detail())
        # TextDontClip : la mesure de la police du détail peut différer d'un
        # pixel du rendu (police en points), et un rectangle au pixel près
        # rognait la dernière lettre (« 4,6 Gc »).
        p.drawText(QRectF(x + largeur + ECART_DETAIL, rect.y(), largeur_detail,
                          rect.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                   | Qt.TextFlag.TextDontClip, detail)
        p.restore()

    def _paint_filled(self, p: QPainter, h: int, rect: QRectF) -> None:
        """Fond plein, un dégradé à peine sensible de haut en bas."""
        haut, bas = QColor(self._bg_top), QColor(self._bg_bot)
        if self._pressed:
            haut, bas = bas, bas.darker(115)
        elif self._hovered:
            haut, bas = haut.lighter(110), bas.lighter(110)
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0, haut)
        bg.setColorAt(1, bas)
        p.fillRect(rect, bg)

    def _paint_outline(self, p: QPainter, rect: QRectF) -> None:
        """Fond à peine teinté — pour les actions secondaires."""
        if self._pressed:
            p.fillRect(rect, QColor(255, 255, 255, 12))
        elif self._hovered:
            r, g, b = self._glow_color.red(), self._glow_color.green(), self._glow_color.blue()
            p.fillRect(rect, QColor(r, g, b, 20))
        else:
            p.fillRect(rect, QColor(255, 255, 255, 6))

    def enterEvent(self, event: QEnterEvent) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        self._pressed = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(event)
