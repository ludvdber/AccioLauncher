"""Panneau d'informations du jeu — titre, metadata, description, version."""

from datetime import datetime
from html import escape
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QScrollArea, QSpacerItem, QVBoxLayout, QWidget,
)

from src.core import folio, folio_hp2, folio_hp3, folio_hp4, folio_hp5, folio_hp6, sauvegardes
from src.core.game_data import GameData
from src.core.game_manager import GameManager
from src.core.i18n import get_language, tr
from src.ui.clickable_label import ClickableLabel
from src.ui.composants import police
from src.ui.fonts import cinzel, cinzel_decorative, body_font
from src.ui.icon_button import pixmap_icone
from src.ui.resume_partie import BlocFolio, cartes_eventail, lieu_resume, phrase_derniere_partie
from src.ui.theme import current as current_theme, themed
from src.core.formatting import format_size

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
# Écart entre le bouton principal et la ligne « JOUABLE À LA MANETTE · VERSION 1.3 ».
_ECART_INDICES = 12
_HAUTEUR_ECART_PLEIN = 760


def _insecable(texte: str) -> str:
    """Rend un segment de la ligne méta insécable : elle ne peut se replier
    qu'au séparateur ◆, jamais au milieu d'une information (règle 64)."""
    return texte.replace(" ", " ")


def _manette(game: GameData) -> str:
    """Dite seulement si le jeu a été essayé (`controller` vide : rien, règle 108)."""
    return {"yes": tr("Jouable à la manette"), "partial": tr("Manette en partie"),
            "no": tr("Sans manette")}.get(game.controller, "")


_PICTO = 18     # px logiques : au-dessous, le pictogramme ne se lit plus (règle 51)
_pictos: dict[tuple[str, float], str] = {}


def _image_en_ligne(couleur: str, ratio: float) -> str:
    """Le pictogramme de la manette en `data:` pour la ligne méta (RichText) :
    rendu à la taille PHYSIQUE, posé à la taille logique, net à 125 %."""
    cle = (couleur, ratio)
    if cle not in _pictos:
        import base64
        from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
        pix = pixmap_icone("manette", _PICTO, QColor(couleur))
        octets = QByteArray()
        tampon = QBuffer(octets)
        tampon.open(QIODevice.OpenModeFlag.WriteOnly)
        pix.save(tampon, "PNG")
        _pictos[cle] = base64.b64encode(bytes(octets)).decode("ascii")
    return (f'<img src="data:image/png;base64,{_pictos[cle]}" width="{_PICTO}" '
            f'height="{_PICTO}" style="vertical-align: middle;">')


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
    # « Folio » de la ligne d'indices, pour un jeu installé dont il sait lire
    # les sauvegardes. Bouton près de l'engrenage jusqu'au 2026-10-14 : il
    # faisait passer le temps de jeu sous la rangée (Ludo).
    folio_clicked = pyqtSignal()
    # « Musique » de la ligne méta : la Médiathèque ouverte sur ce jeu.
    mediatheque_clicked = pyqtSignal()

    def __init__(self, manager: GameManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._desc_expanded: bool = False
        self._full_desc: str = ""
        # Crans de troncature demandés par le parent quand le panneau déborde
        # alors qu'il ne peut plus grandir.
        self._desc_squeeze: int = 0
        # Retiré par `squeeze_medias` quand la fiche manque de place (seul sur
        # sa rangée) ; rendu à chaque jeu et à chaque taille (règle 43).
        self._medias_retire = False
        self._title_size: int = 0    # px, posé par _apply_title_size
        # Dernier levier du rattrapage, après la description (cf. squeeze_title).
        self._title_squeeze: int = 0
        self._height_budget: int = 10_000   # posé par GameDetailView
        # La partie en cours, quand on sait la lire : elle remplace la
        # description (resume_partie.py). `_a_propos` : la personne a demandé
        # à relire la description malgré tout.
        self._game: GameData | None = None
        self._resume: folio.Resume | None = None
        self._a_propos = False
        # Sans folio, l'avancement que le jeu écrit (HP5 : « 14 % ») : une
        # ligne au-dessus de la description, qui reste (Ludo, 2026-10-15).
        self._avancee: sauvegardes.Etat | None = None

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
            self._medias_retire = False
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
        if self._desc_expanded or not self._full_desc or not self.description_montree():
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
            self._btn_expand.setVisible(self.description_montree())
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
            item = self._action_slot.itemAt(i)
            if item.spacerItem() is not None:
                # L'écart sous le bouton : le layout le pose toujours.
                total += item.spacerItem().sizeHint().height()
                continue
            widget = item.widget()
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

        # Ligne méta UNIQUE (année, studio, poids, téléchargements) : un seul
        # libellé qui se replie comme une phrase. La version et ses nouveautés
        # sont descendues sous le bouton (piste A, 2026-10-09).
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

        # « Dernière partie hier · Parc de Poudlard », à la place de la
        # description quand une sauvegarde se lit. Le lieu vient du jeu :
        # RichText échappé (règle 58).
        self._derniere = QLabel()
        self._derniere.setObjectName("derniere_partie")
        self._derniere.setFont(body_font(15))
        self._derniere.setWordWrap(True)
        self._derniere.setTextFormat(Qt.TextFormat.RichText)
        self._derniere.setStyleSheet("QLabel { color: #f2f2f4; background: transparent; }")
        self._derniere.hide()
        lay.addWidget(self._derniere)

        # Le bloc du folio, épinglé sous le bouton (add_bottom_widget).
        self._bloc = BlocFolio()
        self._bloc.clicked.connect(self.folio_clicked)
        self._bloc_hote = QWidget()
        hote = QHBoxLayout(self._bloc_hote)
        hote.setContentsMargins(0, 12, 0, 0)
        hote.setSpacing(10)
        hote.addWidget(self._bloc, 0, Qt.AlignmentFlag.AlignVCenter)
        # La musique et les cinématiques du jeu : un galet à côté du folio
        # (Ludo, 2026-10-24 : un lien dans la ligne méta « fait trop long »).
        # Avec son NOM depuis l'audit du 2026-10-24 : la note seule, ronde, ne
        # disait pas ce qu'elle ouvrait (Ludo : « les nouveautés sont pas très
        # visibles »). Largeur au contenu, hauteur fixe (règles 37 et 49).
        self._medias = QPushButton()
        self._medias.setObjectName("boutonMedias")
        self._medias.setFixedHeight(40)
        self._medias.setFont(police(14))
        self._medias.setCursor(Qt.CursorShape.PointingHandCursor)
        self._medias.setToolTip(tr("La musique, les cinématiques et les captures du jeu"))
        self._medias.setAccessibleName(tr("Collections : la musique, les cinématiques et les "
                                          "captures du jeu"))
        self._medias.setText(tr("Collections"))
        from src.ui.choix_jeux import espacee
        icone, taille = espacee(pixmap_icone("images", 18, QColor("#e6e4f0")), QSize(18, 18))
        self._medias.setIcon(icone)
        self._medias.setIconSize(taille)
        self._medias.setStyleSheet(themed(
            "QPushButton#boutonMedias { background: rgba(255, 255, 255, 0.03); color: #e6e4f0;"
            " border: 1px solid rgba(255, 255, 255, 0.14); border-radius: 20px; padding: 0 16px; }"
            "QPushButton#boutonMedias:hover, QPushButton#boutonMedias:focus {"
            " border-color: #d6a72c; background: rgba(214, 167, 44, 0.08); }"))
        self._medias.clicked.connect(self.mediatheque_clicked)
        self._medias.hide()
        hote.addWidget(self._medias, 0, Qt.AlignmentFlag.AlignVCenter)
        hote.addStretch()
        self._bloc_hote.hide()

        # Ligne d'indices, épinglée sous le bouton (add_bottom_widget) :
        # « Jouable à la manette · Version 1.3 · Nouveautés ». La manette
        # était une pastille parmi les genres, la version un lien dans la
        # ligne méta ; ici, ce sont des faits sur CE qu'on lance.
        self._indices = QLabel()
        self._indices.setObjectName("indicesJeu")
        self._ecart_indices = QSpacerItem(0, _ECART_INDICES)
        # En petites capitales espacées, comme « TEMPS DE JEU » à côté du
        # bouton d'un jeu installé : des faits sur le jeu, pas une phrase.
        police_indices = cinzel(8, bold=True)
        police_indices.setPixelSize(12)
        police_indices.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.6)
        self._indices.setFont(police_indices)
        self._indices.setWordWrap(True)
        self._indices.setTextFormat(Qt.TextFormat.RichText)
        self._indices.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        self._indices.setStyleSheet(
            "QLabel { color: #8f8db0; background: transparent; }")
        self._indices.linkActivated.connect(self._on_meta_link)

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
        self._indices.setMaximumWidth(avail)
        self._meta.setMaximumWidth(avail)
        self._derniere.setMaximumWidth(min(_DESC_MAX_W, avail))
        self._fit_height(self._title)
        self._fit_height(self._desc)
        self._fit_height(self._derniere)
        self._fit_height(self._indices)
        self._fit_height(self._meta)

    def _apply_margins(self) -> None:
        """Marges resserrées sur panneau étroit (80 px sur 550, c'est 15 %)."""
        # L'écart sous le bouton rend sa place sur une fenêtre basse : à
        # 980×660, en espagnol, les 12 px faisaient défiler HP7 de 7 px
        # (audit de géométrie, 2026-10-14).
        ecart = _ECART_INDICES if self.window().height() >= _HAUTEUR_ECART_PLEIN else 4
        if self._ecart_indices.sizeHint().height() != ecart:
            self._ecart_indices.changeSize(0, ecart)
            self._action_slot.invalidate()
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
                f" font-size: {size}px; }}")

    def squeeze_medias(self) -> bool:
        """Retire le galet « Collections » quand il occupe SEUL une rangée
        (HP4 à HP8, sans bloc du folio). L'onglet Collections reste en haut ;
        un titre rogné se verrait davantage. False s'il n'y a rien à gagner."""
        if self._medias_retire or not self._medias.isVisibleTo(self) or self._bloc.isVisibleTo(self):
            return False
        self._medias_retire = True
        self._medias.hide()
        self._bloc_hote.hide()
        return True

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

    # ──────────────────── API publique ────────────────────

    _DESC_TRUNCATE = 160
    # Longueurs d'accroche, du plus généreux au plus serré.
    _DESC_PALIERS = (160, 90, 55, 30)

    def _on_meta_link(self, href: str) -> None:
        """Aiguillage des liens de la ligne méta. Il ne reste que le changelog,
        mais un lambda qui ignore le href renverrait tout futur lien vers lui."""
        if href == "langue":
            self.language_clicked.emit()
        elif href == "folio":
            self.folio_clicked.emit()
        elif href == "a-propos":
            self._basculer_a_propos()
        else:
            self.versions_clicked.emit()

    def apply_game(self, game: GameData) -> None:
        """Met à jour tous les labels avec les données du jeu."""
        # Titre PLEIN à chaque jeu (règle 43) : un cran pris par le titre
        # espagnol le plus long restait sinon sur les sept autres.
        self._title_squeeze = 0
        self._medias_retire = False
        self._title.setText(game.name)
        # La partie se relit dans `rafraichir_indices`, que le parent appelle
        # juste après : la lire ici aussi coûterait deux lectures par jeu.
        nouveau = self._game is None or self._game.id != game.id
        self._game = game
        if nouveau:
            self._resume = None
            self._avancee = None
            self._a_propos = False
            self._appliquer_partie()

        # Metadata
        gold = current_theme().accent
        sep = f'<span style="color:{gold}; margin: 0 6px;"> ◆ </span>'
        dl = game.current_download
        size_str = format_size(dl.size_mb) if dl else "?"
        # `escape` sur tout (règle 58) : en RichText, le balisage d'un nom de
        # studio serait interprété (et un `<img src="file:///…">` lu).
        morceaux = [escape(str(game.year), quote=False),
                    _insecable(escape(game.developer, quote=False)),
                    _insecable(escape(size_str, quote=False))]

        # La manette, fait sur le jeu, rejoint ses faits (maquette « Plan du
        # launcher v2 », 2026-10-26) ; sa nuance passe en infobulle.
        manette = _manette(game)
        if manette:
            morceaux.append(self._fait_manette(game))

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
            bulles = [tr("Téléchargements cumulés de toutes les versions (GitHub)")]
        else:
            bulles = []
        if manette:
            bulles.insert(0, manette + (f" : {game.controller_note}" if game.controller_note else ""))
        self._meta.setToolTip("\n".join(bulles))

        self._meta.setText(
            '<span style="text-transform:uppercase; letter-spacing:2px;">'
            + sep.join(morceaux) + '</span>'
        )

        self._refresh_indices(game)

        # Description
        self._set_desc_text(game.description)

        # Remesurer : un libellé gardait la hauteur du jeu PRÉCÉDENT (161 px
        # d'une description dépliée pour une courte).
        self._apply_available_width()

    def add_bottom_widget(self, widget: QWidget) -> None:
        """Épingle un widget sous la zone défilante, suivi de la ligne
        d'indices : elle parle de ce que le bouton lance."""
        self._action_slot.addWidget(widget)
        self._action_slot.addWidget(self._bloc_hote)
        # De l'air sous le bouton : collée à lui, la ligne avait l'air d'en
        # faire partie (Ludo, 2026-10-14).
        self._action_slot.addSpacerItem(self._ecart_indices)
        self._action_slot.addWidget(self._indices)

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

    # ──────────────────── Indices ────────────────────

    def rafraichir_indices(self, game: GameData | None) -> None:
        """Après un changement d'état du jeu (installé, désinstallé, retour
        de partie) : la partie en cours se relit, puis la ligne d'indices."""
        if game is not None:
            self._game = game
            self._resume = self._lire_partie(game)
            self._avancee = None if self._resume is not None else self._lire_avancee(game)
            self._appliquer_partie()
            self._refresh_indices(game)

    # ──────────────────── Partie en cours ────────────────────

    def partie_affichee(self) -> bool:
        """Vrai quand la fiche montre la partie plutôt que la description :
        le panneau d'actions range alors ses statistiques dans le bloc."""
        return self._resume is not None

    def description_montree(self) -> bool:
        return self._resume is None or self._a_propos

    def _lire_partie(self, game: GameData) -> folio.Resume | None:
        """Seulement un jeu INSTALLÉ que le folio sait lire : désinstallé, la
        fiche redevient une invitation, la description revient."""
        if game.id not in folio.FICHES or not self._manager.is_installed(game.id):
            return None
        system = self._manager.config.install_path / Path(game.executable).parent
        if game.id == "hp4":
            return folio_hp4.resume(sauvegardes.fichiers(game.sauvegardes), system, get_language())
        if game.id == "hp5":
            return folio_hp5.resume(sauvegardes.fichiers(game.sauvegardes))
        if game.id == "hp6":
            return folio_hp6.resume(sauvegardes.fichiers(game.sauvegardes))
        if game.id == "hp2":
            # HP2 numérote ses emplacements par dossier (`Slot1/Save0.usa`).
            return folio_hp2.resume(game.sauvegardes, system, get_language())
        lire = folio_hp3.resume if game.id == "hp3" else folio.resume_hp1
        return lire(sauvegardes.fichiers(game.sauvegardes), system, get_language())

    def _lire_avancee(self, game: GameData) -> sauvegardes.Etat | None:
        if not self._manager.is_installed(game.id):
            return None
        return sauvegardes.derniere_avancee(game.sauvegardes)

    def _appliquer_partie(self) -> None:
        resume, game = self._resume, self._game
        description = self.description_montree()
        self._desc.setVisible(description)
        if self._desc_expanded:
            self._btn_expand.setVisible(description)
        else:
            self._apply_desc_truncation()
        avancee = self._avancee
        self._derniere.setVisible((resume is not None and not self._a_propos)
                                  or (resume is None and avancee is not None))
        from src.ui.mediatheque import a_des_medias
        medias = game is not None and a_des_medias(game.id)
        # « Collections », comme l'onglet : « Musique » ne disait pas les
        # cinématiques ni les captures (Ludo, 2026-10-24). Le galet vivait dans
        # l'hôte du bloc du folio, montré seulement avec un « Reprendre » : de
        # HP4 à HP8, il n'apparaissait jamais.
        self._bloc.setVisible(resume is not None)
        medias = medias and (resume is not None or not self._medias_retire)
        self._medias.setVisible(medias)
        self._bloc_hote.setVisible(resume is not None or medias)
        if resume is None and avancee is not None and avancee.avancement is not None:
            self._derniere.setText(phrase_derniere_partie(
                datetime.fromtimestamp(avancee.modifie),
                tr("{} % terminé").format(avancee.avancement)))
        if resume is not None and game is not None:
            self._derniere.setText(phrase_derniere_partie(resume.quand or datetime.now(),
                                                          lieu_resume(resume)))
            system = self._manager.config.install_path / Path(game.executable).parent
            self._bloc.montrer(resume, cartes_eventail(game.id, system, resume.releve,
                                                       self.devicePixelRatioF()),
                               self._manager.get_playtime(game.id))
        self._apply_available_width()

    def _basculer_a_propos(self) -> None:
        """« À propos du jeu » remet la description, « Ma partie » la retire."""
        self._a_propos = not self._a_propos
        self._appliquer_partie()
        if self._game is not None:
            self._refresh_indices(self._game)
        self._apply_available_width()
        self.content_changed.emit()

    def _fait_manette(self, game: GameData) -> str:
        """La manette en pictogramme (maquette « Plan du launcher v2 », Ludo
        2026-10-26 : « parfait ») ; « en partie » s'écrit à côté, « sans
        manette » en toutes lettres. Le libellé complet est en infobulle."""
        if game.controller == "no":
            return _insecable(escape(tr("Sans manette"), quote=False))
        image = _image_en_ligne("#b4b4d0", self.devicePixelRatioF())
        if game.controller == "partial":
            return image + "&nbsp;" + _insecable(escape(tr("en partie"), quote=False))
        return image

    def _refresh_indices(self, game: GameData) -> None:
        """Sous le bouton, le seul lien vers la partie : « À propos du jeu »
        quand le bloc du folio cache la description, sinon « Folio ».

        Maquette « Plan du launcher v2 » (Ludo, 2026-10-26) : la manette est
        montée dans la ligne méta, la version est partie dans l'engrenage
        (« Gérer les versions ») ; une ligne qui mêlait une information, une
        action de dépannage et un lien ne se lisait pas.
        """
        gold = current_theme().accent
        morceaux = []
        if self._resume is not None:
            # Le bloc porte déjà « Folio › » : ici, la description rangée.
            libelle = tr("Ma partie") if self._a_propos else tr("À propos du jeu")
            morceaux.append(f'<a href="a-propos" style="color:{gold}; text-decoration:none;">'
                            + _insecable(escape(libelle.upper(), quote=False)) + '</a>')
        elif game.id in folio.JEUX and self._manager.is_installed(game.id):
            morceaux.append(f'<a href="folio" style="color:{gold}; text-decoration:none;">'
                            + _insecable(escape(tr("Folio").upper(), quote=False)) + '</a>')
        point ='<span style="color:#4c4a68;">&nbsp;&nbsp;·&nbsp;&nbsp;</span>'
        self._indices.setText(point.join(morceaux))
        self._indices.setVisible(bool(morceaux))

