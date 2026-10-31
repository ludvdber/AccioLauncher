"""La page « Difficulté » d'un jeu (contenu : `src/core/difficulte_presets.py`).

1.4, tranché par Ludo le 2026-10-30 : des presets aux noms clairs (Récit,
Détendu, Normal, Difficile, Hardcore ; puis, à une seule vie, Réaliste et
Impardonnable), « Sur mesure » à part, qui ouvre le détail de chaque réglage.
Une PAGE à la place de la fiche (`pages.py`), comme les réglages du jeu, ouverte
par le bouton à jauge de la fiche.

Mise en page de la maquette de l'expert UI/UX, validée par Ludo le 2026-10-31
(atelier, `artefact_difficulte/index.html`) : le cadran de défi en tête
(`cadran_defi.py`), des cartes qui se cliquent EN ENTIER (plus de bouton
« Choisir » répété), l'active bordée d'or avec un sceau « ACTIF », les valeurs
en or alignées à droite ; « Sur mesure » juste sous les presets, allumé quand
il est actif ; « Une seule vie » en bas, allégée tant qu'elle reste « bientôt ».

Chaque carte dit ce que le preset change dans CE jeu, calculé depuis les
réglages ; un preset qui n'y change rien ne s'y montre pas. Choisir écrit
aussitôt (comme l'engrenage) ; rien n'est écrit au lancement.
"""

from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)

from src.core import difficulte_presets as dp
from src.core import reglages_correctif
from src.core.game_data import GameData
from src.core.game_manager import GameManager
from src.core.i18n import tr
from src.ui.cadran_defi import CadranDefi, teinte
from src.ui.composants import Rangee, bouton, feuille_de_style, surtitre, texte
from src.ui.fonts import cinzel, cinzel_decorative
from src.ui.theme import current as current_theme, themed
from src.ui.utils import zone_defilable

_MARGES = (64, 30, 64, 28)
_DOUX = "#a9a7c4"
_ETEINT = "#6c6a88"
_OR_CLAIR = "#f0d060"

_STYLE = """
QDialog#difficulte { background: #060611; }
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
QFrame#filetOr { background: rgba(214, 167, 44, 0.14); border: none; }
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


class DifficultePage(QDialog):
    """Les presets de difficulté d'un jeu installé."""

    def __init__(self, game: GameData, manager: GameManager,
                 ouvrir_detail: Callable[[], None] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("difficulte")
        self.game = game
        self.manager = manager
        self._ouvrir_detail = ouvrir_detail
        self.setWindowTitle(tr("Difficulté"))
        self.setStyleSheet(themed(_STYLE) + feuille_de_style())
        declares = reglages_correctif.reglages_du_jeu(game.fix_settings)
        self.ini: Path | None = (reglages_correctif.ini_du_correctif(
            manager.config.install_path / Path(game.executable).parent) if declares else None)
        self.idents = dp.idents_du_jeu(game, self.ini)
        self.crans = dp.reperes(game.id, self.idents)
        self.erreur = ""
        racine = QVBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(0)
        racine.addWidget(zone_defilable(self._contenu()), stretch=1)
        racine.addWidget(self._pied())
        self._rafraichir(anime=False)

    def valeurs(self) -> dict[str, object]:
        return dp.lire(self.game, self.manager.config, self.ini, self.idents)

    def courant(self) -> str:
        return dp.courant(self.valeurs(), self.idents)

    def _contenu(self) -> QWidget:
        page = QWidget()
        _transparent(page, "contenuDifficulte")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(_MARGES[0], _MARGES[1], _MARGES[2], 0)
        lay.setSpacing(0)
        lay.addWidget(Rangee([self._entete(), self._bloc_cadran()], 2, seuil=860,
                             etirements=(1, 1), ecart=40))
        lay.addSpacing(28)
        lay.addWidget(_titre_section(tr("Presets")))
        lay.addSpacing(14)
        presets = [p for p in dp.PRESETS if not p.une_vie and dp.disponible(p, self.game.id, self.idents)]
        crans = {p.ident: c for p, c in self.crans}
        self.cartes_presets = [
            _CartePreset(p, dp.changements(p, self.idents), crans.get(p.ident, 40), self._choisir)
            for p in presets]
        for carte in self.cartes_presets:
            carte.voisines = self.cartes_presets
        colonnes = len(self.cartes_presets)
        # Sous 210 px par carte, elles s'écrasaient (cinq cartes à 1000 px) : on empile.
        lay.addWidget(Rangee(list(self.cartes_presets), colonnes, seuil=colonnes * 210, ecart=14))
        lay.addSpacing(14)
        lay.addWidget(self._sur_mesure())
        self.tuiles = self._une_seule_vie(lay)
        self.cartes: list[QFrame] = [*self.cartes_presets, *self.tuiles]
        self.ligne_erreur = texte("", 14, "#ff9a8a", retour=True)
        self.ligne_erreur.setVisible(False)
        lay.addSpacing(14)
        lay.addWidget(self.ligne_erreur)
        lay.addStretch()
        lay.addSpacing(24)
        return page

    def _entete(self) -> QWidget:
        bloc = QWidget()
        _transparent(bloc, "enteteDifficulte")
        v = QVBoxLayout(bloc)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addStretch()
        v.addWidget(surtitre(tr("Difficulté")))
        v.addSpacing(10)
        titre = QLabel(self.game.name)
        titre.setTextFormat(Qt.TextFormat.PlainText)
        titre.setFont(cinzel_decorative(24))
        titre.setWordWrap(True)
        titre.setStyleSheet("color: #f4f2f8; background: transparent;")
        v.addWidget(titre)
        v.addSpacing(14)
        quand = (tr("Change à tout moment, partie en cours comprise.") if self.game.id in _EN_DIRECT
                 else tr("Compte au prochain lancement du jeu."))
        v.addWidget(texte(quand + " " + tr("Vos sauvegardes ne changent pas."), 16, _DOUX, retour=True))
        v.addSpacing(10)
        beta = _pastille(tr("Bêta"), _OR_CLAIR, "rgba(214, 167, 44, 0.5)")
        v.addWidget(beta, alignment=Qt.AlignmentFlag.AlignLeft)
        v.addStretch()
        return bloc

    def _bloc_cadran(self) -> QWidget:
        self.cadran = CadranDefi(self._choisir)
        self.cadran.poser_crans(tuple((p.ident, tr(p.nom), c) for p, c in self.crans))
        return self.cadran

    def _sur_mesure(self) -> QFrame:
        self.cadre_sur_mesure = QFrame()
        self.cadre_sur_mesure.setObjectName("surMesure")
        self.cadre_sur_mesure.setProperty("actif", "false")
        h = QHBoxLayout(self.cadre_sur_mesure)
        h.setContentsMargins(20, 18, 20, 18)
        h.setSpacing(24)
        gauche = QVBoxLayout()
        gauche.setSpacing(4)
        tete = QHBoxLayout()
        tete.setSpacing(12)
        tete.addWidget(_nom(tr("Sur mesure"), 14, "#f2f2f4"))
        self.sceau_sur_mesure = _Sceau()
        self.sceau_sur_mesure.setVisible(False)
        tete.addWidget(self.sceau_sur_mesure, alignment=Qt.AlignmentFlag.AlignVCenter)
        tete.addStretch()
        gauche.addLayout(tete)
        gauche.addWidget(_sans_bord(texte(tr("Chaque réglage à votre goût, un par un."), 14, _DOUX,
                                          retour=True)))
        h.addLayout(gauche, stretch=1)
        if self._ouvrir_detail is not None:
            detail = bouton(tr("Régler chaque paramètre"), principal=True)
            detail.setAutoDefault(False)
            detail.clicked.connect(self._ouvrir_detail)
            h.addWidget(detail, alignment=Qt.AlignmentFlag.AlignVCenter)
        return self.cadre_sur_mesure

    def _une_seule_vie(self, lay: QVBoxLayout) -> list[_TuileBientot]:
        """Réaliste, et Impardonnable là où Hardcore change quelque chose."""
        hardcore = dp.disponible(dp.PAR_IDENT["hardcore"], self.game.id, self.idents)
        tuiles = [_TuileBientot(p) for p in dp.PRESETS
                  if p.une_vie and (p.ident == "realiste" or hardcore)]
        if not tuiles:
            return []
        lay.addSpacing(34)
        lay.addWidget(_titre_section(tr("Une seule vie")))
        lay.addSpacing(14)
        explication = texte(tr("La première mort termine la partie : pas de retour à la dernière "
                               "sauvegarde."), 14, _DOUX, retour=True)
        explication.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(Rangee([explication, *tuiles], 1 + len(tuiles), seuil=720,
                             etirements=(11, *(10,) * len(tuiles)), ecart=14))
        return tuiles

    def _pied(self) -> QWidget:
        pied = QWidget()
        _transparent(pied, "piedDifficulte")
        v = QVBoxLayout(pied)
        v.setContentsMargins(_MARGES[0], 0, _MARGES[2], _MARGES[3])
        v.setSpacing(18)
        filet = QFrame()
        filet.setObjectName("filetOr")
        filet.setFixedHeight(1)
        v.addWidget(filet)
        h = QHBoxLayout()
        h.addStretch()
        retour = bouton(tr("Retour à la fiche"), principal=True)
        retour.setAutoDefault(False)
        retour.clicked.connect(self.accept)
        h.addWidget(retour)
        v.addLayout(h)
        return pied

    @classmethod
    def depuis_la_fiche(cls, view) -> None:
        """Ouvre la page depuis le bouton à jauge de la fiche (`GameDetailView`).
        « Régler chaque paramètre » ouvre les réglages du jeu sur l'onglet Jeu."""
        from src.ui import game_detail_handlers as handlers
        if view.game is None:
            return
        dlg = cls(view.game, view.manager, parent=view,
                  ouvrir_detail=lambda: handlers.on_game_settings(view, onglet="jeu"))
        if view.receivers(view.page_demandee):
            view.page_demandee.emit(dlg)
        else:
            dlg.exec()

    def showEvent(self, event) -> None:  # noqa: N802 (Qt)
        # Au retour des réglages du jeu (« Régler chaque paramètre »), le choix
        # a pu changer : l'aiguille suit.
        super().showEvent(event)
        self._rafraichir()

    def _rafraichir(self, anime: bool = True) -> None:
        valeurs = self.valeurs()
        courant = dp.courant(valeurs, self.idents)
        for carte in self.cartes_presets:
            carte.marquer(carte.ident == courant)
        sur_mesure = courant == dp.SUR_MESURE
        if self.cadre_sur_mesure.property("actif") != ("true" if sur_mesure else "false"):
            self.cadre_sur_mesure.setProperty("actif", "true" if sur_mesure else "false")
            self.cadre_sur_mesure.style().unpolish(self.cadre_sur_mesure)
            self.cadre_sur_mesure.style().polish(self.cadre_sur_mesure)
        self.sceau_sur_mesure.setVisible(sur_mesure)
        niveau = dp.niveau(valeurs, self.game.id, self.idents)
        if sur_mesure:
            self.cadran.viser(niveau, tr("Sur mesure"), dp.situer(niveau, self.crans), anime=anime)
        else:
            self.cadran.viser(niveau, tr(dp.PAR_IDENT[courant].nom), actif=courant, anime=anime)
        self.ligne_erreur.setText(self.erreur)
        self.ligne_erreur.setVisible(bool(self.erreur))

    def _choisir(self, ident: str) -> None:
        if ident == self.courant():
            return
        rates = dp.appliquer(dp.PAR_IDENT[ident], self.game, self.manager.config, self.ini, self.idents)
        self.erreur = (tr("Certains réglages n'ont pas pu être écrits (fichier absent ou en lecture "
                          "seule) : le jeu garde les précédents.") if rates else "")
        self._rafraichir()
