"""Miniature d'un jeu dans le carrousel — reflet, profondeur, badges."""

import re

from PyQt6.QtCore import (
    Qt, pyqtSignal, QRect, QRectF, QPropertyAnimation, QEasingCurve, pyqtProperty,
)
from PyQt6.QtGui import (
    QColor, QFont, QFontMetrics, QImageReader, QLinearGradient, QPainter,
    QPainterPath, QPen, QPixmap, QTransform,
)
from PyQt6.QtWidgets import QWidget

from src.core.config import ASSETS_DIR
from src.core.game_data import GameData
from src.core.game_manager import GameManager
from src.core.i18n import tr
from src.ui.fonts import cinzel
from src.ui.theme import accent_qcolor
from src.ui import theme

THUMB_W = 90
THUMB_H = 125
REFLECTION_RATIO = 0.20
REFLECTION_OPACITY = 0.06

# Marges verticales de l'item, en dur dans `_update_size` : 6 px sous le reflet
# et 10 px de respiration.
_MARGE_V = 16
# Rapport largeur/hauteur de la jaquette, à tenir quelle que soit la bande.
_RAPPORT = THUMB_W / THUMB_H


def vignette_pour(dispo: int, echelle_max: float) -> tuple[int, int]:
    """Taille de vignette qui TIENT dans `dispo` pixels de hauteur d'item.

    `dispo` est la place réellement offerte à l'item, marges du layout du
    carrousel DÉDUITES — pas la hauteur de la bande.

    `THUMB_H` était une constante, et la hauteur de la bande une autre : deux
    nombres voisins qu'aucun calcul ne reliait. Ils ne concordaient que pour
    l'item le plus LOIN de la sélection (150 px pour 160) ; le sélectionné, lui,
    réclame 180 px et était rogné de 27 px — visible en permanence, sur la
    vignette que l'œil regarde en premier. En bande compacte (124 px), les huit
    l'étaient, de 33 à 63 px.

    On inverse donc le calcul : la bande est la contrainte, la vignette s'y
    plie. `echelle_max` est le plus grand facteur de profondeur appliqué
    (`SCALE_SELECTED`) — c'est LUI qui décide, puisque c'est le plus grand item
    qui doit tenir.
    """
    # hauteur_item(h) = h + int(h * RATIO) + _MARGE_V, avec h = THUMB_H * échelle
    budget = max(1, dispo - _MARGE_V)
    h_max = int(budget / (1.0 + REFLECTION_RATIO))
    hauteur = max(1, int(h_max / echelle_max))
    return max(1, int(hauteur * _RAPPORT)), hauteur

# Corps des pastilles « NOUVEAU » / « BIENTÔT », du plus lisible au plus petit.
# La vignette ne fait que 90 px : « PRÓXIMAMENTE » réclame 98 px à 8 pt. Plutôt
# que de parier sur la brièveté des traductions, on réduit le corps jusqu'à ce
# que la pastille tienne — un badge un peu plus petit vaut mieux qu'un badge
# coupé, et le traducteur n'a aucune contrainte à respecter.
_BADGE_SIZES = (9, 8, 7, 6)
_BADGE_PADDING = 10


def _badge_font(text: str, max_w: int) -> QFont:
    """Plus grand corps auquel la pastille de `text` tient dans `max_w`.

    Cinzel, EMBARQUÉE, et non « Segoe UI » appelée par son nom : cette police
    n'existe pas sous Linux, n'est garantie nulle part, et sous `offscreen` Qt
    la remplace en silence par une police 22 % plus large — la boucle
    ci-dessous mesurait donc autre chose que ce que l'utilisateur voit. Le
    changement de police ne peut rien casser ici : c'est précisément le rôle de
    cette boucle que de réduire le corps jusqu'à ce que ça tienne.
    """
    for size in _BADGE_SIZES:
        f = cinzel(size, bold=True)
        if QFontMetrics(f).horizontalAdvance(text) + _BADGE_PADDING <= max_w:
            return f
    return cinzel(_BADGE_SIZES[-1], bold=True)


def _badge_texte(text: str, max_w: int) -> tuple[QFont, str]:
    """Police et texte d'une pastille garantis tenir dans `max_w`.

    On réduit d'abord le corps ; si même le plus petit ne suffit pas — une
    traduction franchement longue —, on abrège. Sans ce dernier recours la
    pastille dépassait la vignette et se faisait couper par le bord du widget,
    ce qui est pire qu'un mot abrégé.
    """
    police = _badge_font(text, max_w)
    fm = QFontMetrics(police)
    if fm.horizontalAdvance(text) + _BADGE_PADDING <= max_w:
        return police, text
    return police, fm.elidedText(text, Qt.TextElideMode.ElideRight,
                                 max_w - _BADGE_PADDING)


_ARABIC_TO_ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI",
                     7: "VII", 8: "VIII", 9: "IX", 10: "X"}


def _game_roman(game_id: str) -> str:
    """Extrait le chiffre romain depuis l'id du jeu (ex: 'hp3' → 'III')."""
    m = re.search(r"(\d+)$", game_id)
    if m:
        n = int(m.group(1))
        return _ARABIC_TO_ROMAN.get(n, str(n))
    return game_id.upper()


class CarouselItem(QWidget):
    """Miniature d'un jeu dans le carrousel avec reflet, profondeur et transitions."""

    clicked = pyqtSignal()

    def __init__(self, game: GameData, manager: GameManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.game = game
        self.manager = manager
        self._selected = False
        self._hovered = False
        self._pixmap: QPixmap | None = None
        self._anim_scale = 0.9
        self._anim_opacity = 0.45
        # Taille de base de la jaquette. Ce n'est plus la constante du module :
        # c'est le carrousel qui l'impose d'après la hauteur de sa bande (cf.
        # `vignette_pour`), sinon l'item déborde et se fait rogner.
        self._thumb_w = THUMB_W
        self._thumb_h = THUMB_H

        self._reflection_cache: QPixmap | None = None
        self._reflection_cache_size: tuple[int, int] = (0, 0)
        self._cached_installed: bool = False
        self._cached_has_update: bool = False
        self._cached_version: str = ""
        self._cached_is_new: bool = False
        self._cached_coming_soon: bool = False
        self._cached_reprise: float = 0.0   # part déjà reçue, 0 = rien en attente

        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._scale_anim = QPropertyAnimation(self, b"anim_scale")
        self._scale_anim.setDuration(400)
        self._scale_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self._opacity_anim = QPropertyAnimation(self, b"anim_opacity")
        self._opacity_anim.setDuration(400)
        self._opacity_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self._update_size()
        self._load_cover()

    def _get_anim_scale(self) -> float:
        return self._anim_scale

    def _set_anim_scale(self, v: float) -> None:
        self._anim_scale = v
        self._update_size()
        self.update()

    anim_scale = pyqtProperty(float, _get_anim_scale, _set_anim_scale)

    def _get_anim_opacity(self) -> float:
        return self._anim_opacity

    def _set_anim_opacity(self, v: float) -> None:
        self._anim_opacity = v
        self.update()

    anim_opacity = pyqtProperty(float, _get_anim_opacity, _set_anim_opacity)

    def refresh_state(self) -> None:
        """Recharge les indicateurs (installé, update, version, nouveau) depuis le manager."""
        self._cached_installed = self.manager.is_installed(self.game.id)
        self._cached_has_update = self.manager.has_update(self.game.id)
        self._cached_version = self.manager.installed_version(self.game.id) or ""
        self._cached_is_new = self.manager.is_new(self.game.id)
        # Jeu annoncé dont aucune archive n'est publiée : signalé dans la
        # vignette pour que l'utilisateur le sache AVANT de cliquer.
        self._cached_coming_soon = not self.game.is_downloadable
        # Téléchargement INTERROMPU qui attend dans le cache. Le calcul (et son
        # seuil) vit dans `GameManager.reprise` : le bouton de la fiche
        # l'affiche aussi, et deux règles jumelles finissent par diverger.
        reprise = self.manager.reprise(self.game)
        self._cached_reprise = reprise[0] if reprise is not None else 0.0
        self.update()

    def _load_cover(self) -> None:
        """Charge la jaquette en demandant la réduction AU DÉCODEUR.

        `QPixmap(chemin).scaled(...)` décodait le JPEG en pleine résolution
        (600×900, et 1024×1024 pour trois jeux) avant de le réduire à 180×250 :
        61 ms pour les huit vignettes, soit 40 % du constructeur de MainWindow.
        `QImageReader.setScaledSize` laisse libjpeg sous-échantillonner pendant
        le décodage — même cadrage, 29 ms au lieu de 85.
        """
        cover_path = ASSETS_DIR / "covers" / self.game.cover_image
        if not cover_path.exists():
            return
        cible_w, cible_h = THUMB_W * 2, THUMB_H * 2
        reader = QImageReader(str(cover_path))
        source = reader.size()
        if source.isValid() and source.width() > 0 and source.height() > 0:
            # « KeepAspectRatioByExpanding » : le plus grand des deux rapports,
            # pour couvrir la vignette sans bande vide.
            facteur = max(cible_w / source.width(), cible_h / source.height())
            if facteur < 1.0:
                reader.setScaledSize(source * facteur)
        image = reader.read()
        if image.isNull():
            return
        self._pixmap = QPixmap.fromImage(image)

    def set_taille_vignette(self, largeur: int, hauteur: int) -> None:
        """Impose la taille de base de la jaquette (décidée par le carrousel)."""
        if (largeur, hauteur) == (self._thumb_w, self._thumb_h):
            return
        self._thumb_w, self._thumb_h = largeur, hauteur
        # Le reflet est mis en cache à une taille : la changer sans l'invalider
        # laisserait l'ancien, à l'échelle d'avant.
        self._reflection_cache = None
        self._reflection_cache_size = (0, 0)
        self._update_size()
        self.update()

    def _update_size(self) -> None:
        w = int(self._thumb_w * self._anim_scale)
        h = int(self._thumb_h * self._anim_scale)
        ref_h = int(h * REFLECTION_RATIO) + 6
        self.setFixedSize(w + 10, h + ref_h + 10)

    def set_depth(self, scale: float, opacity: float) -> None:
        self._scale_anim.stop()
        self._scale_anim.setStartValue(self._anim_scale)
        self._scale_anim.setEndValue(scale)
        self._scale_anim.start()

        self._opacity_anim.stop()
        self._opacity_anim.setStartValue(self._anim_opacity)
        self._opacity_anim.setEndValue(opacity)
        self._opacity_anim.start()

    @property
    def selected(self) -> bool:
        return self._selected

    @selected.setter
    def selected(self, value: bool) -> None:
        self._selected = value
        self.update()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        scale = self._anim_scale
        w = int(self._thumb_w * scale)
        h = int(self._thumb_h * scale)
        x_off = (self.width() - w) // 2
        y_off = 5
        radius = 6.0

        eff_opacity = self._anim_opacity
        if self._hovered and not self._selected:
            eff_opacity = min(eff_opacity + 0.2, 1.0)

        p.setOpacity(eff_opacity)

        if self._selected:
            p.save()
            p.setOpacity(0.4)
            for i in range(4):
                spread = (i + 1) * 3
                alpha = 60 - i * 12
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(0, 0, 0, max(alpha, 5)))
                p.drawRoundedRect(
                    x_off - spread, y_off - spread + 4,
                    w + spread * 2, h + spread * 2,
                    radius + spread, radius + spread,
                )
            p.restore()
            p.setOpacity(eff_opacity)

        clip = QPainterPath()
        clip.addRoundedRect(float(x_off), float(y_off), float(w), float(h), radius, radius)

        if self._pixmap:
            p.setClipPath(clip)
            p.drawPixmap(x_off, y_off, w, h, self._pixmap)
            p.setClipping(False)
        else:
            # Vignette de repli (jaquette absente) : dégradé teinté par le thème
            # — un bleu nuit codé en dur restait bleu au milieu d'une interface
            # verte chez Serpentard.
            grad = QLinearGradient(x_off, y_off, x_off, y_off + h)
            grad.setColorAt(0, QColor(theme.current().bg_card))
            grad.setColorAt(1, theme.bg_qcolor(255))
            p.setBrush(grad)
            p.setPen(QPen(accent_qcolor(60), 1.0))
            p.drawRoundedRect(x_off, y_off, w, h, radius, radius)

            # Le chiffre romain SEUL, centré. Il portait au-dessus un ⚡ demandé
            # en « Segoe UI Emoji » : U+26A1 est à présentation emoji par défaut,
            # donc Windows le rendait en couleur, hors palette et insensible au
            # `setPen` — le piège du bouton pause bleu, en plus discret.
            p.setOpacity(1.0)
            roman = _game_roman(self.game.id)
            p.setPen(accent_qcolor(160))
            p.setFont(cinzel(20, bold=True))
            p.drawText(QRect(x_off, y_off, w, h), Qt.AlignmentFlag.AlignCenter, roman)
            p.setOpacity(eff_opacity)

        if self._selected:
            p.setOpacity(1.0)
            for i in range(3):
                glow = accent_qcolor(25 - i * 7)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(glow)
                off = (i + 1) * 3
                p.drawRoundedRect(x_off - off, y_off - off, w + off * 2, h + off * 2, radius + off, radius + off)

            pen = QPen(accent_qcolor(), 2.0)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(x_off + 1, y_off + 1, w - 2, h - 2, radius, radius)

        if self._pixmap:
            ref_h = int(h * REFLECTION_RATIO)
            ref_y = y_off + h + 4
            if self._reflection_cache is None or self._reflection_cache_size != (w, h):
                self._reflection_cache = self._pixmap.scaled(
                    w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                ).transformed(QTransform().scale(1, -1))
                self._reflection_cache_size = (w, h)
            flipped = self._reflection_cache

            p.setOpacity(eff_opacity * REFLECTION_OPACITY)
            ref_clip = QPainterPath()
            ref_clip.addRoundedRect(float(x_off), float(ref_y), float(w), float(ref_h), 3, 3)
            p.setClipPath(ref_clip)
            p.drawPixmap(x_off, ref_y, w, h, flipped)
            p.setClipping(False)

            p.setOpacity(1.0)
            fade = QLinearGradient(0, ref_y, 0, ref_y + ref_h)
            fade.setColorAt(0, theme.bg_qcolor(80))
            fade.setColorAt(1, theme.bg_qcolor(255))
            p.fillRect(x_off, ref_y, w, ref_h, fade)

        if self._cached_installed:
            p.setOpacity(1.0)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#2ecc71"))
            p.drawEllipse(x_off + w - 14, y_off + h - 14, 10, 10)

            ver_text = f"v{self._cached_version}" if self._cached_version else ""
            if ver_text:
                p.setFont(cinzel(9))
                fm = p.fontMetrics()
                tw = fm.horizontalAdvance(ver_text)
                th = fm.height()
                pad_x, pad_y = 4, 2
                bx = x_off + 3
                by = y_off + h - th - pad_y * 2 - 3
                p.setBrush(QColor(0, 0, 0, 153))
                p.drawRoundedRect(QRectF(bx, by, tw + pad_x * 2, th + pad_y * 2), 3, 3)
                p.setPen(QColor(220, 220, 240, 200))
                p.drawText(QRectF(bx + pad_x, by + pad_y, tw, th), Qt.AlignmentFlag.AlignCenter, ver_text)

        if self._cached_has_update:
            p.setOpacity(1.0)
            badge_size = 18
            bx = x_off + w - badge_size - 2
            by = y_off + 2
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(accent_qcolor(220))
            p.drawRoundedRect(QRectF(bx, by, badge_size, badge_size), 4, 4)
            p.setPen(QColor(255, 255, 255, 240))
            p.setFont(cinzel(10, bold=True))
            p.drawText(QRectF(bx, by, badge_size, badge_size), Qt.AlignmentFlag.AlignCenter, "↑")

        if self._cached_is_new and not self._cached_installed:
            # Ruban « NOUVEAU » en haut à gauche (jeu apparu via update du catalogue)
            p.setOpacity(1.0)
            police, text = _badge_texte(tr("NOUVEAU"), w - 6)
            p.setFont(police)
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(text)
            bx, by = x_off + 3, y_off + 3
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(accent_qcolor(235))
            p.drawRoundedRect(QRectF(bx, by, tw + _BADGE_PADDING, fm.height() + 3), 3, 3)
            p.setPen(theme.bg_qcolor(255))
            p.drawText(QRectF(bx, by, tw + _BADGE_PADDING, fm.height() + 3),
                       Qt.AlignmentFlag.AlignCenter, text)

        if self._cached_coming_soon:
            # Voile sombre + mention discrète : la vignette reste lisible et
            # attractive (c'est un jeu à venir, pas une erreur), mais on ne
            # laisse pas croire qu'elle est jouable.
            p.setOpacity(1.0)
            p.fillRect(x_off, y_off, w, h, theme.bg_qcolor(120))
            police, text = _badge_texte(tr("BIENTÔT"), w - 6)
            p.setFont(police)
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(text)
            bw, bh = tw + _BADGE_PADDING, fm.height() + 3
            bx = x_off + (w - bw) // 2
            by = y_off + (h - bh) // 2
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.bg_qcolor(200))
            p.drawRoundedRect(QRectF(bx, by, bw, bh), 3, 3)
            p.setPen(QColor(200, 200, 220, 230))
            p.drawText(QRectF(bx, by, bw, bh), Qt.AlignmentFlag.AlignCenter, text)

        if self._cached_reprise > 0:
            # Téléchargement interrompu : un filet au bas de la jaquette,
            # rempli à hauteur de ce qui est déjà reçu.
            #
            # Le téléchargeur reprend depuis toujours (`.part` + `Range`), et
            # jusqu'ici RIEN ne le disait avant d'avoir navigué sur la fiche du
            # bon jeu, parmi huit : mesuré le 2026-08-29, à la réouverture
            # aucun des 16 textes visibles n'en soufflait mot, et le launcher
            # ouvre sur le dernier jeu JOUÉ, jamais sur celui qu'on
            # téléchargeait. Sur 4,6 Go, c'est quelqu'un qui a déjà attendu et
            # qui croit avoir tout perdu.
            #
            # Un filet et non une pastille chiffrée : la vignette fait 100 px
            # de large au repos, un pourcentage y serait illisible — et la
            # question n'est pas « combien » mais « il y a quelque chose ici ».
            # Aucun pictogramme non plus : Cinzel n'a pas de glyphe de pause,
            # Windows partirait en repli couleur (cf. `icon_button.py`).
            p.setOpacity(1.0)
            ep = max(2.0, h * 0.022)
            y_filet = y_off + h - ep
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.bg_qcolor(190))
            p.drawRect(QRectF(x_off, y_filet, w, ep))
            p.setBrush(accent_qcolor(235))
            p.drawRect(QRectF(x_off, y_filet, w * self._cached_reprise, ep))

        p.end()
