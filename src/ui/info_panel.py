"""Panneau d'informations du jeu — titre, metadata, description, tags, version."""

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

# Largeurs de CONFORT de lecture — jamais dépassées, mais toujours rabotées à la
# place réellement disponible. Le panneau est positionné en setGeometry à 50 %
# de la fenêtre (voir GameDetailView._position_info) : figer 600/520 px faisait
# déborder titre et description dès que la fenêtre passait sous ~1100 px, et le
# texte était coupé net au bord du panneau.
_TITLE_MAX_W = 600
_DESC_MAX_W = 520
# Largeur de la barre de défilement stylée, à retrancher de la place utile.
_SCROLLBAR_W = 6
# Marge sur la hauteur calculée : sous-estimer de deux pixels suffit à faire
# apparaître une barre de défilement pour rien, et ça se voit beaucoup.
_HAUTEUR_SLACK = 8


def _insecable(texte: str) -> str:
    """Rend un segment de la ligne méta insécable.

    La ligne méta passe à la ligne quand elle est trop longue, et c'est voulu.
    Ce qui ne l'est pas, c'est qu'elle coupe À L'INTÉRIEUR d'un segment : on
    lisait « ◆ 16 » en fin de ligne et « téléchargements » tout seul en dessous.
    En remplaçant les espaces par des insécables, le seul endroit où le texte
    peut se replier reste le séparateur ◆ — donc entre deux informations
    entières, jamais au milieu d'une.
    """
    return texte.replace(" ", "\u00a0")


class InfoPanel(QWidget):
    """Panneau d'infos du jeu : contenu défilant + zone d'action épinglée.

    La zone d'action vit VOLONTAIREMENT hors du défilement. Quand elle était
    dans le flux, le bouton principal passait sous la ligne de flottaison dès
    que la fenêtre descendait vers 1100 px de large : l'action principale du
    launcher devenait invisible, sans même une barre de défilement visible pour
    le signaler.
    """

    versions_clicked = pyqtSignal()
    # Le contenu a changé de hauteur (dépliage de la description) : le panneau
    # doit être repositionné, sinon il défile au lieu de grandir.
    content_changed = pyqtSignal()

    def __init__(self, manager: GameManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._manager = manager
        # _desc_expanded et _full_desc sont initialisés par _set_desc_text au premier apply_game
        self._desc_expanded: bool = False
        self._full_desc: str = ""
        # Crans de troncature supplémentaires demandés par le parent quand le
        # panneau déborde alors qu'il ne peut plus grandir.
        self._desc_squeeze: int = 0
        self._title_size: int = 36  # suivi par _apply_title_size
        # Hauteur que le parent peut nous accorder (posée par GameDetailView).
        self._height_budget: int = 10_000

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

        Sert à raccourcir la description quand la fenêtre est petite : mieux
        vaut trois lignes et « Lire la suite » qu'une barre de défilement qui
        rogne le texte. La valeur ne dépend que de la fenêtre, jamais de nos
        propres ajustements — pas de boucle possible.
        """
        if pixels != self._height_budget:
            self._height_budget = pixels
            # Nouvelle taille de fenêtre : on repart du palier nominal, sinon un
            # resserrement décidé pour une petite fenêtre survivrait à son
            # agrandissement et l'accroche resterait courte pour rien.
            self._desc_squeeze = 0
            if not self._desc_expanded and self._full_desc:
                self._apply_desc_truncation()

    def _desc_budget(self) -> int:
        """Nombre de caractères affichés avant « Lire la suite ».

        Trois paliers et non deux : sur une fenêtre au minimum syndical
        (980×660), un bandeau d'avertissement de deux lignes suffisait à faire
        déborder le panneau de 20 px, donc à ramener la barre de défilement.
        Mieux vaut une accroche plus courte suivie de « Lire la suite » qu'un
        texte complet qu'il faut faire défiler pour atteindre le bouton JOUER.

        `_desc_squeeze` descend d'un cran de plus quand le panneau déborde
        ENCORE alors qu'il occupe déjà toute la place disponible (cf.
        `GameDetailView._fit_info_height`) : le seul cas où c'est arrivé est
        l'espagnol sur les deux titres les plus longs du catalogue, à 980×660.
        Un palier fixe plus bas aurait raccourci l'accroche de TOUS les jeux
        pour régler le cas de deux.
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
        """Hauteur nécessaire pour tout montrer sans défiler.

        Sert à ne PAS étirer le panneau au-delà de son contenu : la zone
        d'action étant épinglée en bas, un panneau plus haut que nécessaire
        creusait un vide entre la description et le bouton.
        """
        if self._scroll.widget() is None:
            return 0
        # `layout.heightForWidth()` est la seule mesure fiable ici. Le `sizeHint`
        # d'un QLabel en `wordWrap` est calculé à une largeur arbitraire et
        # surestime (195 px annoncés pour un titre qui en occupe 97) ; la
        # géométrie réelle, elle, est encore périmée quand on la lit juste après
        # un changement de jeu, et la description se retrouvait hors panneau.
        return (self._layout.heightForWidth(self.available_width())
                + self._hauteur_zone_action()
                + _HAUTEUR_SLACK)

    def _hauteur_zone_action(self) -> int:
        """Hauteur RÉELLE de la zone d'action, sans passer par son `sizeHint`.

        `_action_slot.sizeHint()` annonçait 134 px pour une zone qui en occupe
        68 (mesuré sur hp2, fenêtre 1250×822) : la ligne de statistiques est un
        QLabel en `wordWrap`, dont le `sizeHint` vaut 80 px pour une ligne qui
        en fait 20. La zone défilante prenant tout l'excédent (`stretch=1`), ces
        66 px s'ouvraient en TROU entre la description et le bouton — d'autant
        plus visible que le bouton principal descendait d'autant.

        Le symptôme n'apparaissait que sur un jeu DÉJÀ JOUÉ, puisque la ligne de
        statistiques est cachée tant qu'on n'a pas joué : un seul jeu du
        catalogue de Ludo était concerné, ce qui donnait « pourquoi le bouton
        est-il si bas pour HP2 ? ».

        Quatrième occurrence du même piège (titre, bandeau d'alerte, note
        « bientôt disponible », puis celle-ci) : le remède est toujours
        `heightForWidth`, jamais `sizeHint`.
        """
        marges = self._action_slot.contentsMargins()
        total = marges.top() + marges.bottom()
        largeur = self.available_width()
        premier = True
        for i in range(self._action_slot.count()):
            widget = self._action_slot.itemAt(i).widget()
            # Un widget caché ne prend pas de place — c'est le cas de la ligne
            # de statistiques tant que le jeu n'a jamais été lancé.
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
        """Pixels qui manquent au panneau pour tout montrer sans défiler.

        `natural_height()` s'appuie sur `layout.heightForWidth()`, qui
        sous-estime dans les cas limites — un titre qui passe sur trois lignes,
        une note d'avertissement sur deux. La marge fixe `_HAUTEUR_SLACK`
        absorbe l'ordinaire mais pas ces cas-là, et la retoucher au jugé ne
        ferait que déplacer le seuil.

        On lit donc ce qui déborde RÉELLEMENT, après la mise en page, pour que
        l'appelant rallonge d'exactement ce qu'il faut. Zéro quand tout tient.
        """
        conteneur = self._scroll.widget()
        if conteneur is None:
            return 0
        # La géométrie vient d'être posée : forcer l'activation du layout,
        # sinon la plage de la barre de défilement est encore celle d'avant.
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
        self._title.setFont(cinzel_decorative(36))
        self._title.setWordWrap(True)
        self._title.setMaximumWidth(_TITLE_MAX_W)  # raboté dans _apply_available_width
        self._title.setStyleSheet("QLabel { color: #eaeaea; background: transparent; }")
        lay.addWidget(self._title)
        lay.addSpacing(10)

        # Tags — juste sous le titre : ensemble ils forment l'IDENTITÉ du jeu.
        # Ils précèdent donc les métadonnées, qui répondent à « combien ça coûte »
        # et non à « qu'est-ce que c'est ».
        self._tags_container = QWidget()
        self._tags_container.setStyleSheet("background: transparent;")
        self._tags_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._tags_layout = FlowLayout(self._tags_container, spacing=8)
        lay.addWidget(self._tags_container)
        lay.addSpacing(10)

        # Bande méta UNIQUE : année, studio, poids, version + changelog, et la
        # pastille de téléchargements. Trois lignes dorées se suivaient avant,
        # avec le même poids visuel — l'œil les lisait comme du bruit. Le flow
        # les fait passer à la ligne au lieu de déborder du panneau (la pastille
        # se faisait couper au bord à la taille minimale de la fenêtre).
        # UN SEUL libellé, qui s'enchaîne et passe à la ligne comme une phrase.
        # En FlowLayout de plusieurs widgets, le compteur de téléchargements
        # sautait à la ligne ou non selon la longueur du nom du studio : sa
        # position changeait d'un jeu à l'autre, ce qui est déroutant. Le
        # changelog reste cliquable via un vrai lien (accessible au clavier).
        self._meta = QLabel()
        self._meta.setObjectName("gameMeta")
        self._meta.setFont(cinzel(14))
        self._meta.setWordWrap(True)
        self._meta.setTextFormat(Qt.TextFormat.RichText)
        self._meta.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        self._meta.setStyleSheet("QLabel { color: #8a8aaa; background: transparent; }")
        self._meta.linkActivated.connect(lambda _: self.versions_clicked.emit())
        lay.addWidget(self._meta)
        lay.addSpacing(16)

        # Stats de jeu — ÉPINGLÉES sous le bouton d'action (voir add_bottom_widget),
        # parce qu'elles répondent à « est-ce que je reprends ? » et non à
        # « qu'est-ce que ce jeu ? ». Créées ici, posées là-bas.
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
        self._desc.setFont(body_font(15))
        self._desc.setWordWrap(True)
        self._desc.setMaximumWidth(_DESC_MAX_W)  # raboté dans _apply_available_width
        self._desc.setStyleSheet(
            "QLabel { color: rgba(176, 176, 200, 0.75); background: transparent;"
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
        """Largeur réellement offerte au contenu, marges déduites.

        On mesure sur la largeur du PANNEAU, jamais sur celle du viewport du
        QScrollArea : pendant `resizeEvent`, l'enfant n'a pas encore été
        redimensionné et renvoie sa largeur précédente. Au tout premier
        affichage cette valeur est minuscule, le titre se retrouvait plafonné à
        120 px pour de bon, et plus aucun redimensionnement ne venait le
        corriger.
        """
        left, _, right, _ = self._layout.getContentsMargins()
        return max(120, self.width() - left - right - _SCROLLBAR_W)

    def _apply_available_width(self) -> None:
        """Rabote les largeurs sur la place réellement disponible.

        Les QLabel en `wordWrap` ne descendent pas d'eux-mêmes sous leur
        `minimumSizeHint`, donc un maximum figé en pixels finit par dépasser le
        panneau et le texte est coupé au bord.
        """
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
        """Marges resserrées sur panneau étroit — 80 px de marge sur 550 px de
        panneau, c'est 15 % de la largeur perdue là où elle manque le plus."""
        wide = self.width() >= 620
        left, right = (50, 30) if wide else (32, 22)
        if self._layout.contentsMargins().left() != left:
            self._layout.setContentsMargins(left, 0, right, 0)
            self._action_slot.setContentsMargins(left, 6, right, 0)

    def _apply_title_size(self, avail: int) -> None:
        """Taille de titre proportionnée à la colonne.

        36 px dans une colonne de 466 px, c'est trois lignes de titre qui
        poussent la description hors de l'écran. Le corps suit donc la largeur
        réelle, ce qui garde le titre dominant sans qu'il dévore le panneau.
        """
        size = 36 if avail >= 520 else 30 if avail >= 440 else 26
        if size != self._title_size:
            self._title_size = size
            self._title.setFont(cinzel_decorative(size))

    @staticmethod
    def _fit_height(label: QLabel) -> None:
        """Donne au libellé la hauteur que son texte réclame à sa largeur.

        Un QLabel en `wordWrap` placé dans un QVBoxLayout reçoit la hauteur de
        son `sizeHint`, calculée à une largeur qui n'est pas la sienne : le
        titre du jeu réclamait 146 px et n'en obtenait que 97, si bien qu'on
        lisait « Harry Potter à l'École des » sans « Sorciers ».
        """
        width = label.maximumWidth()
        if width <= 0 or not label.text():
            return
        # `QLabel.heightForWidth()` renvoie max(minimumHeight, hauteur calculée) :
        # mesurer sans remettre le minimum à zéro fait cliqueter la valeur vers le
        # haut à chaque redimensionnement, et le titre ne rétrécit plus jamais.
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
    _DL_COUNT_MIN = 1  # seuil d'affichage de la pastille téléchargements (passer à ~100 plus tard)

    def apply_game(self, game: GameData) -> None:
        """Met à jour tous les labels avec les données du jeu."""
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
        morceaux = [str(game.year), _insecable(game.developer),
                    _insecable(size_str), lien]

        # Compteur de téléchargements (GitHub, toutes versions cumulées). Il vit
        # DANS la ligne méta et non dans une pastille séparée : en pastille, le
        # FlowLayout le renvoyait à la ligne ou non selon la longueur du nom du
        # studio, et sa position sautait d'un jeu à l'autre. Caché tant
        # qu'inconnu ou sous le seuil.
        count = self._manager.download_count(game.id)
        if count >= self._DL_COUNT_MIN:
            pretty = f"{count:,}".replace(",", "\u202f")  # espace fine insécable FR
            key = "{} téléchargement" if count == 1 else "{} téléchargements"
            # En doré comme avant : c'est de la preuve sociale, elle mérite de
            # ressortir du reste de la ligne méta, qui est en gris sourdine.
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

        # Les textes viennent tous de changer : remesurer les hauteurs. Sans ça,
        # un libellé garde la hauteur réservée pour le jeu PRÉCÉDENT — après un
        # « Lire la suite » suivi d'un changement de jeu, la description courte
        # conservait les 161 px de la version dépliée et laissait un grand vide.
        self._apply_available_width()

    def add_bottom_widget(self, widget: QWidget) -> None:
        """Épingle un widget sous la zone défilante — il reste toujours visible.

        Les statistiques de jeu suivent immédiatement : elles commentent
        l'action (« reprendre ? »), donc elles vivent avec elle.
        """
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
        # Le texte a changé de hauteur : remesurer, puis demander au parent de
        # repositionner le panneau. Sans ça, déplier fait apparaître une barre
        # de défilement au lieu d'agrandir le panneau.
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
        # Les tags viennent de changer : recalculer la hauteur du flow,
        # sinon la dernière ligne de pastilles reste coupée.
        self._relayout_tags()
