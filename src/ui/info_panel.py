"""Panneau d'informations du jeu — titre, metadata, description, tags, version."""

from html import escape

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from src.core.game_data import GameData
from src.core.game_manager import GameManager
from src.core.i18n import tr
from src.ui.clickable_label import ClickableLabel
from src.ui.flow_layout import FlowLayout
from src.ui.fonts import cinzel, cinzel_decorative, body_font
from src.ui.theme import current as current_theme, themed
from src.ui.utils import clear_layout
from src.core.formatting import format_playtime, format_relative_date, format_size

# Largeurs de CONFORT, toujours rabotées à la place réelle : figées, elles
# débordaient sous ~1100 px de fenêtre.
_TITLE_MAX_W = 600
_DESC_MAX_W = 520
# Crans de réduction du titre (px) et plancher. Un seul cran suffit au pire cas
# (espagnol HP7a à 980×660) ; avec deux, le rattrapage les prenait tous les deux.
_TITRE_CRANS = (0, 6)
_TITRE_MIN_PX = 24
_SCROLLBAR_W = 6
# Sous-estimer de 2 px fait apparaître une barre de défilement pour rien.
_HAUTEUR_SLACK = 8


def _insecable(texte: str) -> str:
    """Rend un segment de la ligne méta insécable : elle ne peut se replier
    qu'au séparateur ◆, jamais au milieu d'une information (règle 64)."""
    return texte.replace(" ", " ")


class InfoPanel(QWidget):
    """Panneau d'infos du jeu : contenu défilant + zone d'action épinglée.

    La zone d'action vit hors du défilement : dans le flux, le bouton
    principal passait sous la ligne de flottaison vers 1100 px de large.
    """

    versions_clicked = pyqtSignal()
    # Langue du jeu cliquée dans la ligne méta (aiguillage gardé, voir _on_meta_link).
    language_clicked = pyqtSignal()
    # Le contenu a changé de hauteur : le parent doit repositionner le panneau.
    content_changed = pyqtSignal()

    def __init__(self, manager: GameManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._desc_expanded: bool = False
        self._full_desc: str = ""
        # Crans de troncature demandés par le parent quand le panneau déborde
        # alors qu'il ne peut plus grandir.
        self._desc_squeeze: int = 0
        self._title_size: int = 0    # px, posé par _apply_title_size
        # Dernier levier du rattrapage, après la description (cf. squeeze_title).
        self._title_squeeze: int = 0
        self._height_budget: int = 10_000   # posé par GameDetailView

        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(50, 0, 30, 0)
        self._layout.setSpacing(0)
        self._build_widgets()

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setLayout(self._layout)

        self._scroll = QScrollArea(self)
        self._setup_scroll()
        self._scroll.setWidget(container)

        self._action_slot = QVBoxLayout()
        self._action_slot.setContentsMargins(50, 6, 30, 0)
        self._action_slot.setSpacing(0)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._scroll, stretch=1)
        root.addLayout(self._action_slot)

    def set_height_budget(self, pixels: int) -> None:
        """Hauteur maximale que le parent peut accorder au panneau.

        Ne dépend que de la fenêtre, jamais de nos ajustements : pas de boucle.
        """
        if pixels != self._height_budget:
            self._height_budget = pixels
            # Nouvelle taille : repartir du nominal (règle 43).
            self._desc_squeeze = 0
            self._title_squeeze = 0
            if not self._desc_expanded and self._full_desc:
                self._apply_desc_truncation()

    def _desc_budget(self) -> int:
        """Nombre de caractères affichés avant « Lire la suite ».

        Trois paliers selon la hauteur, plus `_desc_squeeze` quand le panneau
        déborde ENCORE à pleine taille (seul cas vu : l'espagnol des deux titres
        les plus longs à 980×660). Un palier fixe plus bas aurait raccourci
        l'accroche de tous les jeux pour deux.
        """
        if self._height_budget >= 430:
            depart = 0
        elif self._height_budget >= 380:
            depart = 1
        else:
            depart = 2
        index = min(depart + self._desc_squeeze, len(self._DESC_PALIERS) - 1)
        return self._DESC_PALIERS[index]

    def squeeze_description(self) -> bool:
        """Descend d'un palier de troncature. False s'il n'y a plus de marge."""
        if self._desc_expanded or not self._full_desc:
            return False
        avant = self._desc_budget()
        self._desc_squeeze += 1
        if self._desc_budget() == avant:
            self._desc_squeeze -= 1
            return False
        self._apply_desc_truncation()
        self._apply_available_width()
        return True

    def _apply_desc_truncation(self) -> None:
        limite = self._desc_budget()
        if len(self._full_desc) > limite:
            self._desc.setText(self._full_desc[:limite].rstrip() + "…")
            self._btn_expand.setText(tr("Lire la suite…"))
            self._btn_expand.setVisible(True)
        else:
            self._desc.setText(self._full_desc)
            self._btn_expand.setVisible(False)

    def natural_height(self) -> int:
        """Hauteur nécessaire pour tout montrer sans défiler (au-delà, la zone
        d'action épinglée creuserait un vide sous la description)."""
        if self._scroll.widget() is None:
            return 0
        # `heightForWidth`, jamais `sizeHint` (règle 39) : celui d'un QLabel
        # en wordWrap surestime (195 px pour 97).
        return (self._layout.heightForWidth(self.available_width())
                + self._hauteur_zone_action()
                + _HAUTEUR_SLACK)

    def _hauteur_zone_action(self) -> int:
        """Hauteur RÉELLE de la zone d'action, sans passer par son `sizeHint`.

        Son `sizeHint` annonçait 134 px pour 68 (la ligne de statistiques en
        wordWrap) : un trou de 66 px entre la description et le bouton, sur
        tout jeu déjà joué. Remède habituel : `heightForWidth` (règle 39).
        """
        marges = self._action_slot.contentsMargins()
        total = marges.top() + marges.bottom()
        largeur = self.available_width()
        premier = True
        for i in range(self._action_slot.count()):
            widget = self._action_slot.itemAt(i).widget()
            # Caché = sans place (statistiques d'un jeu jamais lancé).
            if widget is None or widget.isHidden():
                continue
            if not premier:
                total += self._action_slot.spacing()
            premier = False
            if widget.hasHeightForWidth():
                total += widget.heightForWidth(largeur)
            else:
                total += widget.sizeHint().height()
        return total

    def overflow(self) -> int:
        """Pixels qui manquent pour tout montrer sans défiler, lus APRÈS la mise
        en page : `natural_height` sous-estime dans les cas limites (titre sur
        trois lignes). Zéro quand tout tient."""
        conteneur = self._scroll.widget()
        if conteneur is None:
            return 0
        # Sinon la plage de la barre est encore celle d'avant.
        layout = conteneur.layout()
        if layout is not None:
            layout.activate()
        return max(0, self._scroll.verticalScrollBar().maximum())

    def _setup_scroll(self) -> None:
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._scroll.setStyleSheet(themed(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: transparent; width: 4px; border: none; }"
            "QScrollBar::handle:vertical { background: rgba(214,167,44,0.3); border-radius: 2px; min-height: 20px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
        ))

    def _build_widgets(self) -> None:
        lay = self._layout

        # Titre
        self._title = QLabel()
        self._title.setObjectName("gameTitle")
        # Texte du catalogue : PlainText dès la construction (règle 57).
        self._title.setTextFormat(Qt.TextFormat.PlainText)
        self._title.setFont(cinzel_decorative(36))   # famille ; la TAILLE vient du QSS
        self._title.setWordWrap(True)
        self._title.setMaximumWidth(_TITLE_MAX_W)  # raboté dans _apply_available_width
        # Sélecteur par ID : avec un simple « QLabel », la règle
        # `QLabel#gameTitle` de styles.py gagnait et figeait 36 px.
        self._title.setStyleSheet(
            "QLabel#gameTitle { color: #f2f2f4; background: transparent; }")
        lay.addWidget(self._title)
        lay.addSpacing(10)

        # Tags sous le titre : ensemble, l'identité du jeu.
        self._tags_container = QWidget()
        self._tags_container.setStyleSheet("background: transparent;")
        self._tags_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._tags_layout = FlowLayout(self._tags_container, spacing=8)
        lay.addWidget(self._tags_container)
        lay.addSpacing(10)

        # Ligne méta UNIQUE (année, studio, poids, version + changelog,
        # téléchargements) : un seul libellé qui se replie comme une phrase.
        # En plusieurs widgets, le compteur sautait de place d'un jeu à l'autre.
        self._meta = QLabel()
        self._meta.setObjectName("gameMeta")
        self._meta.setFont(cinzel(14))
        self._meta.setWordWrap(True)
        self._meta.setTextFormat(Qt.TextFormat.RichText)
        self._meta.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        # `#b4b4d0` : à `#8a8aaa`, 44 % des illustrations passaient sous WCAG AA.
        self._meta.setStyleSheet("QLabel { color: #b4b4d0; background: transparent; }")
        self._meta.linkActivated.connect(self._on_meta_link)
        lay.addWidget(self._meta)
        lay.addSpacing(16)

        # Statistiques : créées ici, épinglées sous le bouton (add_bottom_widget).
        self._stats_label = QLabel()
        self._stats_label.setFont(body_font(12))
        self._stats_label.setStyleSheet(themed(
            "QLabel { color: rgba(214, 167, 44, 0.70); background: transparent; }"
        ))
        self._stats_label.setWordWrap(True)
        self._stats_label.setVisible(False)

        # Description
        self._desc = QLabel()
        self._desc.setObjectName("gameDescription")
        # Texte du catalogue : PlainText dès la construction (règle 57).
        self._desc.setTextFormat(Qt.TextFormat.PlainText)
        self._desc.setFont(body_font(15))
        self._desc.setWordWrap(True)
        self._desc.setMaximumWidth(_DESC_MAX_W)  # raboté dans _apply_available_width
        # OPAQUE (règle 65) : à 0,75 d'opacité, 40 % des illustrations sous
        # WCAG AA ; `#b8b8d0` tient aussi l'illustration de HP4 sous un voile à 15 %.
        self._desc.setStyleSheet(
            "QLabel { color: #b8b8d0; background: transparent;"
            " line-height: 1.5; }"
        )
        lay.addWidget(self._desc)

        # Expand/collapse — ClickableLabel : focusable clavier (A11Y)
        self._btn_expand = ClickableLabel()
        self._btn_expand.setFont(body_font(13))
        self._btn_expand.setStyleSheet(themed(
            "QLabel { color: #d6a72c; background: transparent; padding-top: 4px; }"
            "QLabel:hover { color: #e8c547; }"
        ))
        self._btn_expand.setVisible(False)
        self._btn_expand.clicked.connect(self._toggle_desc)
        lay.addWidget(self._btn_expand)
        lay.addSpacing(12)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_available_width()

    def available_width(self) -> int:
        """Largeur offerte au contenu, mesurée sur le PANNEAU : pendant
        `resizeEvent`, le viewport rend encore sa largeur précédente, et le
        titre restait plafonné à 120 px pour de bon."""
        left, _, right, _ = self._layout.getContentsMargins()
        return max(120, self.width() - left - right - _SCROLLBAR_W)

    def _apply_available_width(self) -> None:
        """Rabote les largeurs sur la place réelle : un QLabel en wordWrap ne
        descend pas seul sous son `minimumSizeHint`."""
        self._apply_margins()
        avail = self.available_width()
        self._apply_title_size(avail)
        self._title.setMaximumWidth(min(_TITLE_MAX_W, avail))
        self._desc.setMaximumWidth(min(_DESC_MAX_W, avail))
        self._stats_label.setMaximumWidth(avail)
        self._tags_container.setMaximumWidth(avail)
        self._meta.setMaximumWidth(avail)
        self._fit_height(self._title)
        self._fit_height(self._desc)
        self._fit_height(self._stats_label)
        self._relayout_tags(avail)
        self._fit_height(self._meta)

    def _apply_margins(self) -> None:
        """Marges resserrées sur panneau étroit (80 px sur 550, c'est 15 %)."""
        wide = self.width() >= 620
        left, right = (50, 30) if wide else (32, 22)
        if self._layout.contentsMargins().left() != left:
            self._layout.setContentsMargins(left, 0, right, 0)
            self._action_slot.setContentsMargins(left, 6, right, 0)

    def _apply_title_size(self, avail: int) -> None:
        """Taille du titre selon la largeur de la colonne, moins les crans.

        Par le STYLESHEET, pas `setFont` (règle 14) : la règle applicative de
        styles.py l'emportait, et ces paliers n'ont longtemps rien changé. La
        hauteur manquante, elle, passe par les crans (squeeze_title).
        """
        base = 36 if avail >= 520 else 30 if avail >= 440 else 26
        size = max(_TITRE_MIN_PX,
                   base - _TITRE_CRANS[min(self._title_squeeze, len(_TITRE_CRANS) - 1)])
        if size != self._title_size:
            self._title_size = size
            self._title.setStyleSheet(
                "QLabel#gameTitle { color: #f2f2f4; background: transparent;"
                " font-size: %dpx; }" % size)

    def squeeze_title(self) -> bool:
        """Descend le titre d'un cran (dernier levier : c'est le plus gros
        bloc du panneau). False s'il n'y a plus de marge."""
        avant = self._title_size
        self._title_squeeze += 1
        self._apply_available_width()
        if self._title_size == avant:
            self._title_squeeze -= 1
            return False
        return True

    @staticmethod
    def _fit_height(label: QLabel) -> None:
        """Hauteur que le texte réclame à sa largeur (règle 38) : sinon on
        lisait « Harry Potter à l'École des » sans « Sorciers »."""
        width = label.maximumWidth()
        if width <= 0 or not label.text():
            return
        # `heightForWidth` rend max(minimumHeight, calcul) : remettre le minimum
        # à zéro d'abord, sinon le titre ne rétrécit plus jamais.
        label.setMinimumHeight(0)
        label.setMinimumHeight(label.heightForWidth(width))

    def _relayout_tags(self, avail: int | None = None) -> None:
        """Donne au conteneur de tags la hauteur exacte dont le flow a besoin."""
        self._relayout_flow(self._tags_container, self._tags_layout, avail)

    def _relayout_flow(self, container: QWidget, flow: FlowLayout,
                       avail: int | None = None) -> None:
        """Hauteur exacte d'un conteneur en FlowLayout, sinon sa dernière ligne
        se fait couper — un plafond fixe ne survit pas au rétrécissement."""
        if avail is None:
            avail = self.available_width()
        needed = flow.heightForWidth(avail) if flow.count() else 0
        container.setFixedHeight(max(0, needed))

    # ──────────────────── API publique ────────────────────

    _DESC_TRUNCATE = 160
    # Longueurs d'accroche, du plus généreux au plus serré.
    _DESC_PALIERS = (160, 90, 55, 30)

    def _on_meta_link(self, href: str) -> None:
        """Aiguillage des liens de la ligne méta. Il ne reste que le changelog,
        mais un lambda qui ignore le href renverrait tout futur lien vers lui."""
        if href == "langue":
            self.language_clicked.emit()
        else:
            self.versions_clicked.emit()

    def apply_game(self, game: GameData) -> None:
        """Met à jour tous les labels avec les données du jeu."""
        # Titre PLEIN à chaque jeu (règle 43) : un cran pris par le titre
        # espagnol le plus long restait sinon sur les sept autres.
        self._title_squeeze = 0
        self._title.setText(game.name)

        # Metadata
        gold = current_theme().accent
        sep = f'<span style="color:{gold}; margin: 0 6px;"> ◆ </span>'
        dl = game.current_download
        size_str = format_size(dl.size_mb) if dl else "?"
        installed = self._manager.installed_version(game.id)
        version = installed or game.recommended_version
        lien = (f'<a href="changelog" style="color:{gold}; text-decoration:none;">'
                + _insecable(tr("v{} · changelog").format(version)) + '</a>')
        # `escape` sur tout (règle 58) : en RichText, le balisage d'un nom de
        # studio serait interprété (et un `<img src="file:///…">` lu).
        morceaux = [escape(str(game.year), quote=False),
                    _insecable(escape(game.developer, quote=False)),
                    _insecable(escape(size_str, quote=False)), lien]

        # PAS de langue du jeu ici : « FRANÇAIS » est un état normal (règle 107).
        # Le réglage vit dans l'engrenage (GameSettingsDialog, rubrique « Langue »).

        # Téléchargements cumulés, sans seuil (règle 120). 0 = réponse GitHub
        # absente, pas « personne » : on n'affiche alors rien (règle 108).
        count = self._manager.download_count(game.id)
        if count > 0:
            pretty = f"{count:,}".replace(",", " ")  # espace fine insécable FR
            key = "{} téléchargement" if count == 1 else "{} téléchargements"
            # En doré : la preuve sociale ressort du gris de la ligne.
            morceaux.append(f'<span style="color:{gold};">'
                            + _insecable(tr(key).format(pretty)) + '</span>')
            self._meta.setToolTip(
                tr("Téléchargements cumulés de toutes les versions (GitHub)"))
        else:
            self._meta.setToolTip("")

        self._meta.setText(
            '<span style="text-transform:uppercase; letter-spacing:2px;">'
            + sep.join(morceaux) + '</span>'
        )


        # Stats de jeu — une seule ligne discrète, affichée uniquement si déjà joué
        self._refresh_stats(game)

        # Description
        self._set_desc_text(game.description)

        # Tags
        self._refresh_tags(game)

        # Remesurer : un libellé gardait la hauteur du jeu PRÉCÉDENT (161 px
        # d'une description dépliée pour une courte).
        self._apply_available_width()

    def add_bottom_widget(self, widget: QWidget) -> None:
        """Épingle un widget sous la zone défilante, suivi des statistiques :
        elles commentent l'action (« reprendre ? »)."""
        self._action_slot.addWidget(widget)
        self._action_slot.addWidget(self._stats_label)

    def add_stretch(self) -> None:
        self._layout.addStretch()

    # ──────────────────── Description ────────────────────

    def _set_desc_text(self, text: str) -> None:
        self._full_desc = text
        self._desc_expanded = False
        # Nouveau jeu : le resserrement décidé pour le précédent ne le concerne pas.
        self._desc_squeeze = 0
        self._apply_desc_truncation()

    def _toggle_desc(self) -> None:
        self._desc_expanded = not self._desc_expanded
        if self._desc_expanded:
            self._desc.setText(self._full_desc)
            self._btn_expand.setText(tr("Réduire le texte"))
        else:
            self._apply_desc_truncation()
        # Remesurer puis faire repositionner, sinon le panneau défile au lieu de grandir.
        self._apply_available_width()
        self.content_changed.emit()

    # ──────────────────── Stats de jeu ────────────────────

    def _refresh_stats(self, game: GameData) -> None:
        """Ligne « 14 h de jeu · Dernière session : hier » — cachée si jamais joué."""
        seconds = self._manager.get_playtime(game.id)
        if seconds <= 0:
            self._stats_label.setVisible(False)
            return
        parts = [format_playtime(seconds)]
        last = self._manager.last_played(game.id)
        if last:
            parts.append(tr("Dernière session : {}").format(format_relative_date(last)))
        self._stats_label.setText("  ·  ".join(parts))
        self._stats_label.setVisible(True)

    # ──────────────────── Tags ────────────────────

    def _refresh_tags(self, game: GameData) -> None:
        clear_layout(self._tags_layout)
        for tag in game.tags:
            badge = QLabel(tag.upper())
            badge.setFont(cinzel(10, bold=True))
            badge.setStyleSheet(themed(
                "QLabel { background: rgba(214, 167, 44, 0.05); color: #d6a72c;"
                " border: 1px solid rgba(214, 167, 44, 0.3); border-radius: 12px;"
                " padding: 4px 14px; letter-spacing: 2px; }"
            ))
            self._tags_layout.addWidget(badge)
        self._tags_container.updateGeometry()
        # Sinon la dernière ligne de pastilles reste coupée.
        self._relayout_tags()
