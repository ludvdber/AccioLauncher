"""Barre de titre custom pour fenêtre sans cadre."""

from PyQt6.QtCore import Qt, QPoint, QRectF, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QMouseEvent, QPainter, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QLabel, QWidget

from src.core.i18n import tr
from src.ui.fonts import body_font, cinzel
from src.ui import theme
from src.ui.ecu import Ecu, emaux
from src.ui.icon_button import BLURPLE, pixmap_icone

# Débord opaque sous le bord bas, en pixels logiques — même remède que
# `background_widget._DEBORD_PX` pour la couture du carrousel : Qt découpe
# au rect réel, donc peindre au-delà garantit d'atteindre le bord physique
# quelle que soit l'échelle d'affichage.
_DEBORD_PX = 2.0

HAUTEUR = 38

# Les trois onglets, par clé (le libellé est traduit, la clé non).
BIBLIOTHEQUE = "bibliotheque"
ANNEES = "annees"
PARAMETRES = "parametres"

_TAILLE_LOGO = 16
_ECART_LOGO = 8


class _Onglet(QPushButton):
    """Onglet de la barre : capitales Cinzel, trait à l'accent sous l'onglet ouvert.

    Dans l'anneau de focus (règle 15), contrairement aux boutons de fenêtre :
    ce sont les pages du launcher, la manette doit pouvoir les atteindre.
    """

    def __init__(self, libelle: str, palette: theme.Palette, parent: QWidget) -> None:
        super().__init__(libelle.upper(), parent)
        self.setCheckable(True)
        self.setAccessibleName(libelle)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(HAUTEUR)
        police = cinzel(9, bold=True)
        police.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.6)
        self.setFont(police)
        # Bordure haute transparente de même épaisseur : le libellé reste
        # centré quand le trait du bas apparaît.
        self.setStyleSheet(
            "QPushButton { background: transparent; color: #a9a7c4; padding: 0 12px;"
            " border: none; border-top: 2px solid transparent;"
            " border-bottom: 2px solid transparent; }"
            f"QPushButton:hover {{ color: {palette.accent_light}; }}"
            f"QPushButton:checked {{ color: #f2eee2; border-bottom-color: {palette.accent}; }}"
            f"QPushButton:focus {{ color: {palette.accent_light}; }}"
        )


def _logo_espace(couleur: QColor) -> QIcon:
    """Le logo suivi d'un blanc, en un seul pixmap (règle 30, même remède que
    `about_page._icone_espacee`)."""
    pm = pixmap_icone("discord", _TAILLE_LOGO, couleur)
    ratio = pm.devicePixelRatio()
    large = QPixmap(round((_TAILLE_LOGO + _ECART_LOGO) * ratio), round(_TAILLE_LOGO * ratio))
    large.setDevicePixelRatio(ratio)
    large.fill(Qt.GlobalColor.transparent)
    p = QPainter(large)
    p.drawPixmap(0, 0, pm)
    p.end()
    return QIcon(large)


class _PastilleDiscord(QPushButton):
    """« Discord » en pastille : logo officiel blanc, Blurple au survol."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__("Discord", parent)
        libelle = tr("Discord : aide et communauté")
        self.setToolTip(libelle)
        self.setAccessibleName(libelle)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(body_font(10))
        self.setFixedHeight(26)
        self.setIconSize(QSize(_TAILLE_LOGO + _ECART_LOGO, _TAILLE_LOGO))
        self._blanc = _logo_espace(QColor("#ffffff"))
        self._survol = _logo_espace(BLURPLE)
        self.setIcon(self._blanc)
        self.setStyleSheet(
            "QPushButton { background: transparent; color: #d9d6e8; padding: 0 12px 0 10px;"
            " border: 1px solid rgba(255,255,255,0.12); border-radius: 13px; }"
            "QPushButton:hover, QPushButton:focus { border-color: rgba(88,101,242,0.6);"
            " background: rgba(88,101,242,0.12); }"
        )

    def enterEvent(self, event) -> None:
        self.setIcon(self._survol)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.setIcon(self._blanc)
        super().leaveEvent(event)


class TitleBar(QWidget):
    """Barre du haut : nom, écu, onglets, Discord et boutons de fenêtre."""

    onglet_demande = pyqtSignal(str)
    discord_demande = pyqtSignal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._window = parent
        self._drag_pos: QPoint | None = None
        self.setFixedHeight(HAUTEUR)
        self.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 4, 0)
        layout.setSpacing(0)

        # Titre — Cinzel Decorative, doré. Sans pictogramme : le ⚡ (U+26A1)
        # est à présentation emoji par défaut, donc Windows le rendait en
        # couleur à côté d'un titre or — en permanence, sur l'élément de marque.
        self._title = QLabel("Accio Launcher")
        self._title.setFont(cinzel(13, bold=True))
        self._title.setStyleSheet(f"color: {theme.current().accent}; background: transparent;")
        layout.addWidget(self._title)

        # L'écu, seulement avec un thème de maison (voir src/ui/ecu.py). La
        # phrase « Élève de … » vivait à côté : avec les onglets, elle ne tenait
        # plus à 980 px en espagnol. Elle passe dans l'infobulle de l'écu.
        # L'écu laisse passer la souris (glisser la fenêtre par-dessus) : c'est
        # son support, un QWidget nu qui ignore aussi le clic, qui porte la bulle.
        self._ecu = None
        palette = theme.current()
        if emaux(palette.id) is not None:
            layout.addSpacing(14)
            support = QWidget(self)
            support.setToolTip(tr("Élève de {}").format(tr(palette.nom)))
            boite = QHBoxLayout(support)
            boite.setContentsMargins(0, 0, 0, 0)
            self._ecu = Ecu(palette.id, support)
            boite.addWidget(self._ecu)
            layout.addWidget(support, alignment=Qt.AlignmentFlag.AlignVCenter)
            self._support_ecu = support

        layout.addSpacing(18)
        self._onglets: dict[str, QPushButton] = {}
        for cle, libelle in ((BIBLIOTHEQUE, tr("Bibliothèque")),
                             (ANNEES, tr("Mes années")),
                             (PARAMETRES, tr("Paramètres"))):
            onglet = _Onglet(libelle, palette, self)
            onglet.clicked.connect(lambda _=False, c=cle: self.onglet_demande.emit(c))
            layout.addWidget(onglet)
            self._onglets[cle] = onglet
        self.set_onglet(BIBLIOTHEQUE)

        layout.addStretch()

        # Discord : le logo officiel, blanc au repos et Blurple au survol, dans
        # TOUS les thèmes (une marque ne prend pas la couleur de la maison).
        self._discord = _PastilleDiscord(self)
        self._discord.clicked.connect(self.discord_demande)
        layout.addWidget(self._discord, alignment=Qt.AlignmentFlag.AlignVCenter)
        filet = QWidget(self)
        filet.setFixedSize(1, 18)
        filet.setStyleSheet("background: rgba(255,255,255,0.10);")
        layout.addSpacing(14)
        layout.addWidget(filet, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addSpacing(6)

        # Boutons minimalistes
        for text, slot, hover_bg, label in (
            ("\u2500", self._on_minimize, "rgba(255,255,255,0.08)", tr("Réduire")),
            ("\u25a1", self._on_maximize, "rgba(255,255,255,0.08)", tr("Agrandir")),
            ("\u2715", self._on_close, "#c0392b", tr("Fermer")),
        ):
            btn = QPushButton(text)
            btn.setAccessibleName(label)
            btn.setToolTip(label)
            btn.setFixedSize(44, 38)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            # Hors de l'anneau de focus, comme les boutons d'une vraie barre de
            # titre Windows (le clavier a Alt+F4 et Win+↓). Ils étaient les
            # PREMIERS de l'anneau : la croix de la manette, au démarrage,
            # RÉDUISAIT le launcher, et deux appuis vers le bas plus loin elle
            # l'aurait FERMÉ (Ludo, 2026-10-07 : « HP1 ne s'ouvre pas et le
            # launcher ne revient pas »).
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: #8a8aaa; border: none;"
                f" font-size: 13px; }}"
                f"QPushButton:hover {{ background: {hover_bg}; color: #eaeaea; }}"
            )
            btn.clicked.connect(slot)
            layout.addWidget(btn)

    def set_onglet(self, cle: str) -> None:
        """Souligne l'onglet ouvert. Mes années et Paramètres sont des fenêtres
        modales : la fenêtre principale remet Bibliothèque à leur fermeture."""
        for c, onglet in self._onglets.items():
            onglet.setChecked(c == cle)

    def onglet(self, cle: str) -> QPushButton:
        return self._onglets[cle]

    @property
    def discord(self) -> QPushButton:
        return self._discord

    def _on_minimize(self) -> None:
        self._window.showMinimized()

    def _on_maximize(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def _on_close(self) -> None:
        self._window.close()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), theme.bg_qcolor(217))  # rgba(6,6,17,0.85)
        # Séparateur à l'accent du thème (la ligne au-dessus le fait déjà pour
        # le fond ; l'or était codé en dur trois lignes plus bas).
        #
        # Peint en fillRect DÉBORDANT sous le bord, et non en drawLine à
        # `height() - 1`. Cette coordonnée est LOGIQUE : à une échelle
        # d'affichage fractionnaire, le bord bas du widget ne tombe pas sur un
        # pixel physique entier (38 px logiques × 1,25 = 47,5), et le filet se
        # posait une rangée physique au-dessus du vrai bord, laissant une bande
        # de fond nu entre lui et la fiche de jeu. Mesuré : présent à 1,25 et
        # 1,5 sur les 8 jeux et les 4 tailles, absent à 1,0. Même famille que
        # la couture du carrousel (pitfall #32) ; Qt découpe le débord au rect
        # réel du widget, donc la ligne atteint toujours le bord.
        p.fillRect(QRectF(0.0, self.height() - 1.0,
                          float(self.width()), 1.0 + _DEBORD_PX),
                   theme.accent_qcolor(25))
        p.end()

    # ── Drag de la fenêtre ──

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self._window.isMaximized():
                # Restore first, reposition window so cursor stays on the title bar
                from PyQt6.QtGui import QGuiApplication
                global_pt = event.globalPosition().toPoint()
                self._window.showNormal()
                geo = self._window.frameGeometry()
                new_x = int(global_pt.x() - geo.width() * 0.5)
                # Borner aux limites de l'écran sous le curseur (multi-monitor safe)
                screen = QGuiApplication.screenAt(global_pt)
                if screen is not None:
                    sg = screen.availableGeometry()
                    new_x = max(sg.x(), min(new_x, sg.x() + sg.width() - geo.width()))
                self._window.move(new_x, 0)
                self._drag_pos = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            else:
                self._drag_pos = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not (self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton):
            return
        # Sous Wayland, `move()` est ignoré : seul le compositeur déplace une
        # fenêtre. `startSystemMove` lui passe la main (X11 et Windows
        # l'acceptent aussi) ; repli manuel s'il refuse. Au premier MOUVEMENT
        # et non à l'appui : sous Windows, la boucle modale de déplacement
        # ouverte à l'appui avale le second clic, donc le double-clic qui
        # agrandit la fenêtre.
        poignee = self._window.windowHandle()
        if poignee is not None and poignee.startSystemMove():
            self._drag_pos = None
            return
        self._window.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self._on_maximize()
