"""L'onglet « Difficulté » des réglages d'un jeu : le cadran, les presets, et
tout le détail en dessous (contenu : `src/core/difficulte_presets.py`).

1.4, tranché par Ludo le 2026-10-30 : des presets aux noms clairs (Récit,
Détendu, Normal, Difficile, Hardcore ; puis, à une seule vie, Réaliste et
Impardonnable) et « Sur mesure ». Mise en page de la maquette de l'expert UI/UX,
validée le 2026-10-31 (atelier, `artefact_difficulte/index.html`) : cadran de
défi (`cadran_defi.py`), cartes cliquables EN ENTIER, l'active bordée d'or avec
un sceau « ACTIF », valeurs en or alignées à droite.

UN SEUL ONGLET, plus de page à part (Ludo, 2026-10-31 : « Sur mesure ouvre le
menu Jeu avec la difficulté tout en haut, puis Démarrage, avant de remettre la
difficulté du Quidditch : ça n'a aucun sens ; un seul onglet Difficulté avec
tout dedans »). Ce panneau porte le haut de l'onglet (cadran, presets, en-tête
« Sur mesure ») ; les réglages un par un sont posés juste dessous par la
fenêtre des réglages (`reglages_rubriques._page_difficulte`), et choisir un
preset les remet sur ce que porte le fichier. Choisir écrit aussitôt ; rien
n'est écrit au lancement.
"""

from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from src.core import difficulte_presets as dp
from src.core.config import Config
from src.core.game_data import GameData
from src.core.i18n import tr
from src.ui.cadran_defi import CadranDefi, teinte
from src.ui.composants import Rangee, surtitre, texte
from src.ui.fonts import cinzel
from src.ui.theme import current as current_theme, themed

_DOUX = "#a9a7c4"
_ETEINT = "#6c6a88"
_OR_CLAIR = "#f0d060"

_STYLE = """
QFrame#preset {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #121226, stop:0.6 #0d0d1a);
    border: 1px solid rgba(214, 167, 44, 0.22); border-radius: 14px;
}
QFrame#preset:hover { border-color: rgba(214, 167, 44, 0.5); }
QFrame#preset[actif="true"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #16162c, stop:0.7 #0d0d1a);
    border: 1px solid #d6a72c;
}
QFrame#preset[focusClavier="true"]:focus { border: 2px solid #f0d060; }
QFrame#surMesure {
    background: #0d0d1a; border: 1px solid rgba(214, 167, 44, 0.22); border-radius: 14px;
}
QFrame#surMesure[actif="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(214, 167, 44, 0.08), stop:0.6 #0d0d1a);
    border: 1px solid #d6a72c;
}
QFrame#bientot {
    background: rgba(13, 13, 26, 0.5); border: 1px solid rgba(169, 167, 196, 0.12); border-radius: 14px;
}
QFrame#filetLignes { background: rgba(214, 167, 44, 0.14); border: none; }
QFrame#filetSection {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(214, 167, 44, 0.22), stop:1 rgba(214, 167, 44, 0));
    border: none;
}
"""

# Les jeux UE1 relisent leurs fichiers au lancement ; HP5 et HP6, dans la seconde.
_EN_DIRECT = {"hp5", "hp6"}


def _pastille(contenu: str, encre: str, bord: str) -> QLabel:
    """« BÊTA », « BIENTÔT » : une capitale en Cinzel dans une gélule."""
    lbl = QLabel(contenu.upper())
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    f = cinzel(7, bold=True)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.8)
    lbl.setFont(f)
    lbl.setStyleSheet(themed(f"color: {encre}; background: transparent; border: 1px solid {bord};"
                             " border-radius: 9px; padding: 2px 9px 1px 9px;"))
    lbl.setMinimumHeight(round(QFontMetricsF(f).height()) + 8)
    lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return lbl


def _nom(contenu: str, pt: int, encre: str) -> QLabel:
    lbl = QLabel(contenu)
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    lbl.setFont(cinzel(pt, bold=True))
    lbl.setStyleSheet(f"color: {encre}; background: transparent; border: none;")
    return lbl


def _sans_bord(lbl: QLabel) -> QLabel:
    lbl.setStyleSheet(lbl.styleSheet() + " border: none;")
    return lbl


class _Sceau(QWidget):
    """« ✓ ACTIF » en or, peint : la coche n'existe pas dans Cinzel (règle 59)."""

    def __init__(self) -> None:
        super().__init__()
        self._texte = tr("Actif").upper()
        self._police = cinzel(7, bold=True)
        self._police.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt)
        m = QFontMetricsF(self._police)
        return QSize(round(17 + m.horizontalAdvance(self._texte)) + 2, round(m.height()) + 2)

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        encre = QColor(current_theme().accent_light)
        milieu = self.height() / 2
        coche = QPainterPath(QPointF(1.5, milieu + 0.5))
        coche.lineTo(4.5, milieu + 3)
        coche.lineTo(10, milieu - 3.5)
        stylo = QPen(encre, 1.8)
        stylo.setCapStyle(Qt.PenCapStyle.RoundCap)
        stylo.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(stylo)
        p.drawPath(coche)
        p.setFont(self._police)
        m = QFontMetricsF(self._police)
        p.drawText(QPointF(17, milieu + (m.ascent() - m.descent()) / 2), self._texte)
        p.end()


class _CartePreset(QFrame):
    """Un preset : toute la carte se clique (Espace, Entrée ; ←/→ passe à la voisine)."""

    def __init__(self, preset: dp.Preset, lignes: tuple[tuple[str, str], ...], cran: float,
                 choisir: Callable[[str], None]) -> None:
        super().__init__()
        self.setObjectName("preset")
        self.ident = preset.ident
        self._choisir = choisir
        self.voisines: list[_CartePreset] = []
        self._teinte = teinte(max(cran, 4))
        self.setProperty("actif", "false")
        self.setProperty("bientot", "false")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(tr(preset.nom))
        self.setAccessibleDescription(tr(preset.phrase))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 22, 20, 20)
        lay.setSpacing(10)
        tete = QHBoxLayout()
        tete.setSpacing(10)
        tete.addWidget(_nom(tr(preset.nom), 15, "#f2f2f4"), stretch=1)
        self.sceau = _Sceau()
        politique = self.sceau.sizePolicy()
        politique.setRetainSizeWhenHidden(True)
        self.sceau.setSizePolicy(politique)
        self.sceau.setVisible(False)
        tete.addWidget(self.sceau, alignment=Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(tete)
        lay.addWidget(_sans_bord(texte(tr(preset.phrase), 14, _DOUX, retour=True)))
        if lignes:
            filet = QFrame()
            filet.setObjectName("filetLignes")
            filet.setFixedHeight(1)
            lay.addSpacing(2)
            lay.addWidget(filet)
            lay.addSpacing(2)
            grille = QGridLayout()
            grille.setHorizontalSpacing(12)
            grille.setVerticalSpacing(7)
            grille.setColumnStretch(0, 1)
            for rang, (libelle, valeur) in enumerate(lignes):
                lib = _sans_bord(texte(libelle, 14, _OR_CLAIR if not valeur else "#d9d8e6", retour=True))
                lib.setStyleSheet(themed(lib.styleSheet()))
                lib.setObjectName("changement")
                if not valeur:
                    grille.addWidget(lib, rang, 0, 1, 2)
                    continue
                val = _sans_bord(texte(valeur, 14, _OR_CLAIR, retour=True))
                val.setStyleSheet(themed(val.styleSheet()))
                val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
                grille.addWidget(lib, rang, 0, Qt.AlignmentFlag.AlignTop)
                grille.addWidget(val, rang, 1, Qt.AlignmentFlag.AlignTop)
            lay.addLayout(grille)
        lay.addStretch()

    def marquer(self, actif: bool) -> None:
        if self.property("actif") == ("true" if actif else "false"):
            return
        self.setProperty("actif", "true" if actif else "false")
        self.sceau.setVisible(actif)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    # ── Choisir ───────────────────────────────────────────────────────────
    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt)
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self._choisir(self.ident)
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt)
        touche = event.key()
        if touche in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._choisir(self.ident)
            return
        if self in self.voisines:
            rang = self.voisines.index(self)
            cible = {Qt.Key.Key_Right: rang + 1, Qt.Key.Key_Down: rang + 1, Qt.Key.Key_Left: rang - 1,
                     Qt.Key.Key_Up: rang - 1, Qt.Key.Key_Home: 0,
                     Qt.Key.Key_End: len(self.voisines) - 1}.get(Qt.Key(touche))
            if cible is not None:
                voisine = self.voisines[max(0, min(cible, len(self.voisines) - 1))]
                voisine.setFocus(Qt.FocusReason.TabFocusReason)
                voisine._choisir(voisine.ident)
                return
        super().keyPressEvent(event)

    # ── Le liseré du haut, à la couleur du cran ───────────────────────────
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().paintEvent(event)
        actif = self.property("actif") == "true"
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if actif:
            # Une lueur à la couleur du cran, qui descend du liseré.
            lueur = QRadialGradient(QPointF(self.width() / 2, 0), self.width() * 0.6)
            couleur = QColor(self._teinte)
            couleur.setAlpha(40)
            lueur.setColorAt(0, couleur)
            couleur.setAlpha(0)
            lueur.setColorAt(1, couleur)
            fond = QPainterPath()
            fond.addRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 13, 13)
            p.fillPath(fond, lueur)
        couleur = QColor(self._teinte)
        couleur.setAlphaF(1.0 if actif else 0.7 if self.underMouse() else 0.35)
        if actif:
            halo = QColor(self._teinte)
            halo.setAlpha(70)
            p.setPen(self._stylo(halo, 6))
            p.drawLine(QPointF(20, 1), QPointF(self.width() - 20, 1))
        p.setPen(self._stylo(couleur, 2))
        p.drawLine(QPointF(19, 1), QPointF(self.width() - 19, 1))
        p.end()

    @staticmethod
    def _stylo(couleur: QColor, epaisseur: float) -> QPen:
        stylo = QPen(couleur, epaisseur)
        stylo.setCapStyle(Qt.PenCapStyle.RoundCap)
        return stylo


class _TuileBientot(QFrame):
    """Un preset à une seule vie, pas encore possible : ni bouton ni clic."""

    def __init__(self, preset: dp.Preset) -> None:
        super().__init__()
        self.setObjectName("bientot")
        self.ident = preset.ident
        self.setProperty("actif", "false")
        self.setProperty("bientot", "true")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(4)
        tete = QHBoxLayout()
        tete.addWidget(_nom(tr(preset.nom), 12, "#8f8daa"), stretch=1)
        tete.addWidget(_pastille(tr("Bientôt"), _DOUX, "rgba(169, 167, 196, 0.25)"),
                       alignment=Qt.AlignmentFlag.AlignTop)
        lay.addLayout(tete)
        lay.addWidget(_sans_bord(texte(tr(preset.phrase), 13, _ETEINT, retour=True)))
        lay.addStretch()


def _transparent(widget: QWidget, nom: str) -> None:
    """Un conteneur sans fond. La règle porte son NOM : sans sélecteur, elle
    s'appliquait aussi à ses enfants, et effaçait le fond des cartes et des filets."""
    widget.setObjectName(nom)
    widget.setStyleSheet(f"QWidget#{nom} {{ background: transparent; }}")


def _titre_section(contenu: str) -> QWidget:
    """Un surtitre doré suivi d'un filet qui s'efface vers la droite."""
    bloc = QWidget()
    _transparent(bloc, "titreSection")
    h = QHBoxLayout(bloc)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(14)
    h.addWidget(surtitre(contenu))
    filet = QFrame()
    filet.setObjectName("filetSection")
    filet.setFixedHeight(1)
    h.addWidget(filet, stretch=1)
    return bloc


class PanneauDifficulte(QWidget):
    """Le haut de l'onglet Difficulté : à quand ça compte, le cadran, les
    presets, l'en-tête « Sur mesure ». `choisi` part après l'écriture d'un
    preset (identifiant, réglages qui n'ont PAS pu l'être)."""

    choisi = pyqtSignal(str, list)

    def __init__(self, game: GameData, config: Config, ini: Path | None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        _transparent(self, "panneauDifficulte")
        self.setStyleSheet(self.styleSheet() + themed(_STYLE))
        self.game = game
        self.config = config
        self.ini = ini
        self.idents = dp.idents_du_jeu(game, ini)
        self.crans = dp.reperes(game.id, self.idents)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(Rangee([self._entete(), self._bloc_cadran()], 2, seuil=640,
                             etirements=(1, 1), ecart=28))
        lay.addSpacing(22)
        lay.addWidget(_titre_section(tr("Presets")))
        lay.addSpacing(14)
        crans = {p.ident: c for p, c in self.crans}
        presets = [p for p in dp.PRESETS if not p.une_vie and dp.disponible(p, game.id, self.idents)]
        self.cartes_presets = [_CartePreset(p, dp.changements(p, self.idents), crans.get(p.ident, 40),
                                            self._choisir) for p in presets]
        for carte in self.cartes_presets:
            carte.voisines = self.cartes_presets
        colonnes = len(self.cartes_presets)
        # Sous 190 px par carte, elles s'écrasaient : on empile.
        lay.addWidget(Rangee(list(self.cartes_presets), colonnes, seuil=colonnes * 190, ecart=12))
        # Là où les presets font déjà chaque combinaison (HP1), ni l'en-tête ni
        # les réglages un par un : la fenêtre lit `sur_mesure`.
        self.sur_mesure = dp.sur_mesure_utile(self.idents)
        self.sceau_sur_mesure: _Sceau | None = None
        if self.sur_mesure:
            lay.addSpacing(30)
            lay.addWidget(self._tete_sur_mesure())
        self.rafraichir(anime=False)

    # ── Lire ──────────────────────────────────────────────────────────────
    def valeurs(self) -> dict[str, object]:
        return dp.lire(self.game, self.config, self.ini, self.idents)

    def courant(self) -> str:
        return dp.courant(self.valeurs(), self.idents)

    # ── Construire ────────────────────────────────────────────────────────
    def _entete(self) -> QWidget:
        bloc = QWidget()
        _transparent(bloc, "enteteDifficulte")
        v = QVBoxLayout(bloc)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        v.addStretch()
        quand = (tr("Change à tout moment, partie en cours comprise.") if self.game.id in _EN_DIRECT
                 else tr("Compte au prochain lancement du jeu."))
        v.addWidget(texte(quand + " " + tr("Vos sauvegardes ne changent pas."), 15, _DOUX, retour=True))
        v.addWidget(_pastille(tr("Bêta"), _OR_CLAIR, "rgba(214, 167, 44, 0.5)"),
                    alignment=Qt.AlignmentFlag.AlignLeft)
        v.addStretch()
        return bloc

    def _bloc_cadran(self) -> QWidget:
        self.cadran = CadranDefi(self._choisir)
        self.cadran.poser_crans(tuple((p.ident, tr(p.nom), c) for p, c in self.crans))
        return self.cadran

    def _tete_sur_mesure(self) -> QWidget:
        """Le titre de la section des réglages un par un, allumé quand aucun
        preset ne correspond : les réglages eux-mêmes suivent, posés par la fenêtre."""
        bloc = QWidget()
        _transparent(bloc, "teteSurMesure")
        v = QVBoxLayout(bloc)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        tete = QHBoxLayout()
        tete.setSpacing(14)
        tete.addWidget(surtitre(tr("Sur mesure")))
        self.sceau_sur_mesure = _Sceau()
        politique = self.sceau_sur_mesure.sizePolicy()
        politique.setRetainSizeWhenHidden(True)
        self.sceau_sur_mesure.setSizePolicy(politique)
        self.sceau_sur_mesure.setVisible(False)
        tete.addWidget(self.sceau_sur_mesure, alignment=Qt.AlignmentFlag.AlignVCenter)
        filet = QFrame()
        filet.setObjectName("filetSection")
        filet.setFixedHeight(1)
        tete.addWidget(filet, stretch=1)
        v.addLayout(tete)
        v.addWidget(texte(tr("Chaque réglage à votre goût, un par un : un preset les règle tous d'un geste."),
                          14, _DOUX, retour=True))
        return bloc

    def bloc_une_seule_vie(self) -> QWidget | None:
        """Réaliste, et Impardonnable là où Hardcore change quelque chose, en
        tuiles « Bientôt » : à poser par la fenêtre, sous les réglages."""
        hardcore = dp.disponible(dp.PAR_IDENT["hardcore"], self.game.id, self.idents)
        self.tuiles = [_TuileBientot(p) for p in dp.PRESETS
                       if p.une_vie and (p.ident == "realiste" or hardcore)]
        if not self.tuiles:
            return None
        bloc = QWidget()
        _transparent(bloc, "uneSeuleVie")
        bloc.setStyleSheet(bloc.styleSheet() + themed(_STYLE))
        v = QVBoxLayout(bloc)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(14)
        v.addWidget(_titre_section(tr("Une seule vie")))
        explication = texte(tr("La première mort termine la partie : pas de retour à la dernière "
                               "sauvegarde."), 14, _DOUX, retour=True)
        v.addWidget(Rangee([explication, *self.tuiles], 1 + len(self.tuiles), seuil=640,
                           etirements=(11, *(10,) * len(self.tuiles)), ecart=12))
        return bloc

    # ── Réagir ────────────────────────────────────────────────────────────
    def rafraichir(self, anime: bool = True) -> None:
        """Marques, sceau et aiguille sur ce que portent les fichiers."""
        valeurs = self.valeurs()
        courant = dp.courant(valeurs, self.idents)
        for carte in self.cartes_presets:
            carte.marquer(carte.ident == courant)
        sur_mesure = courant == dp.SUR_MESURE
        if self.sceau_sur_mesure is not None:
            self.sceau_sur_mesure.setVisible(sur_mesure)
        niveau = dp.niveau(valeurs, self.game.id, self.idents)
        if sur_mesure:
            self.cadran.viser(niveau, tr("Sur mesure"), dp.situer(niveau, self.crans), anime=anime)
        else:
            self.cadran.viser(niveau, tr(dp.PAR_IDENT[courant].nom), actif=courant, anime=anime)

    def _choisir(self, ident: str) -> None:
        if ident == self.courant():
            return
        rates = dp.appliquer(dp.PAR_IDENT[ident], self.game, self.config, self.ini, self.idents)
        self.rafraichir()
        self.choisi.emit(ident, rates)
