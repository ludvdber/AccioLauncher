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

« Une seule vie » (Réaliste, Impardonnable) : deux cartes comme les autres,
sous les réglages, avec ce que fait le jeu à la première mort et l'état de la
vie (`core/une_vie`). Elles ne se montrent que là où le mode est proposé
(`difficulte_presets.une_vie_proposee`).
"""

from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from src.core import difficulte_presets as dp
from src.core import une_vie
from src.core.config import Config
from src.core.game_data import GameData
from src.core.i18n import tr
from src.ui.cadran_defi import CadranDefi, teinte
from src.ui.composants import Rangee, pastille, surtitre, texte, transparent
from src.ui.fonts import cinzel
from src.ui.theme import RAYON_CARTE, current as current_theme, themed

_DOUX = "#a9a7c4"
_OR_CLAIR = "#f0d060"

_STYLE = f"""
QFrame#preset {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #121226, stop:0.6 #0d0d1a);
    border: 1px solid rgba(214, 167, 44, 0.22); border-radius: {RAYON_CARTE}px;
}}
QFrame#preset:hover {{ border-color: rgba(214, 167, 44, 0.5); }}
QFrame#preset[actif="true"] {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #16162c, stop:0.7 #0d0d1a);
    border: 1px solid #d6a72c;
}}
QFrame#surMesure {{
    background: #0d0d1a; border: 1px solid rgba(214, 167, 44, 0.22); border-radius: {RAYON_CARTE}px;
}}
QFrame#surMesure[actif="true"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(214, 167, 44, 0.08), stop:0.6 #0d0d1a);
    border: 1px solid #d6a72c;
}}
QFrame#filetLignes {{ background: rgba(214, 167, 44, 0.14); border: none; }}
QFrame#filetSection {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(214, 167, 44, 0.22), stop:1 rgba(214, 167, 44, 0));
    border: none;
}}
"""


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
            fond.addRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), RAYON_CARTE - 1, RAYON_CARTE - 1)
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


def _titre_section(contenu: str) -> QWidget:
    """Un surtitre doré suivi d'un filet qui s'efface vers la droite."""
    bloc = QWidget()
    transparent(bloc, "titreSection")
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
    """Le haut de l'onglet Difficulté : ce qui ne change pas, le cadran, les
    presets, l'en-tête « Sur mesure ». `choisi` part après l'écriture d'un
    preset (identifiant, réglages qui n'ont PAS pu l'être)."""

    choisi = pyqtSignal(str, list)

    def __init__(self, game: GameData, config: Config, ini: Path | None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        transparent(self, "panneauDifficulte")
        self.setStyleSheet(self.styleSheet() + themed(_STYLE))
        self.game = game
        self.config = config
        self.ini = ini
        self.idents = dp.idents_du_jeu(game, ini)
        self.crans = dp.reperes(game.id, self.idents)
        self.cartes_une_vie: list[_CartePreset] = []
        self.etat_une_vie: QLabel | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        # « Bêta » se pose à côté du titre de la page (la fenêtre le prend) : seul à gauche
        # du cadran, il laissait 660 × 330 px vides et repoussait les préréglages sous le
        # pli (audit UI f44, f68). Le cadran plafonne sa hauteur et se centre.
        self.pastille_beta = pastille(tr("Bêta"), _OR_CLAIR, "rgba(214, 167, 44, 0.5)")
        self.pastille_beta.setToolTip(tr("Bêta : ces réglages sont encore en essai. Ce qui ne va pas "
                                         "se signale sur le Discord du projet."))
        lay.addWidget(self._bloc_cadran())
        lay.addSpacing(22)
        lay.addWidget(_titre_section(tr("Préréglages")))
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
        return dp.courant(self.valeurs(), self.idents, dp.une_vie_active(self.game, self.config))

    # ── Construire ────────────────────────────────────────────────────────
    def _bloc_cadran(self) -> QWidget:
        self.cadran = CadranDefi(self._choisir)
        self.cadran.poser_crans(tuple((p.ident, tr(p.nom), c) for p, c in self.crans))
        return self.cadran

    def _tete_sur_mesure(self) -> QWidget:
        """Le titre de la section des réglages un par un, allumé quand aucun
        preset ne correspond : les réglages eux-mêmes suivent, posés par la fenêtre."""
        bloc = QWidget()
        transparent(bloc, "teteSurMesure")
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
        return bloc

    def bloc_une_seule_vie(self) -> QWidget | None:
        """Réaliste, et Impardonnable là où Hardcore change quelque chose, à poser
        par la fenêtre sous les réglages ; None là où le mode n'est pas proposé."""
        if not dp.une_vie_proposee(self.game, self.config):
            return None
        vies = [p for p in dp.PRESETS if p.une_vie and dp.disponible(p, self.game.id, self.idents)]
        crans = {p.ident: c for p, c in self.crans}
        self.cartes_une_vie = [
            _CartePreset(p, dp.changements(p, self.idents), crans.get(dp.BASE_UNE_VIE[p.ident], 40),
                         self._choisir)
            for p in vies]
        for carte in self.cartes_une_vie:
            carte.voisines = self.cartes_une_vie
        mode = une_vie.MODES[self.game.id]
        bloc = QWidget()
        transparent(bloc, "uneSeuleVie")
        bloc.setStyleSheet(bloc.styleSheet() + themed(_STYLE))
        v = QVBoxLayout(bloc)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(14)
        v.addWidget(_titre_section(tr("Une seule vie")))
        phrases = [tr("La première mort efface la partie : elle se joue dans un dossier à part, et vos "
                      "sauvegardes ne sont ni lues ni écrites."), tr(mode.apres)]
        if mode.note:
            phrases.append(tr(mode.note))
        explication = texte("\n\n".join(phrases), 14, _DOUX, retour=True)
        explication.setObjectName("explicationUneVie")
        v.addWidget(Rangee([explication, *self.cartes_une_vie], 1 + len(self.cartes_une_vie), seuil=640,
                           etirements=(11, *(10,) * len(self.cartes_une_vie)), ecart=12))
        self.etat_une_vie = texte("", 14, _OR_CLAIR, retour=True)
        self.etat_une_vie.setStyleSheet(themed(self.etat_une_vie.styleSheet()))
        self.etat_une_vie.setObjectName("etatUneVie")
        v.addWidget(self.etat_une_vie)
        self._dire_etat()
        return bloc

    def _dire_etat(self) -> None:
        """Où en est la vie, seulement quand le mode est actif : rien à dire sinon."""
        if self.etat_une_vie is None:
            return
        phrase = ""
        if dp.une_vie_active(self.game, self.config):
            etat = une_vie.etat(self.game)
            phrase = (tr("Votre dernière vie s'est terminée : la prochaine partie en commence une nouvelle.")
                      if etat.finie else
                      tr("Une vie est en cours : JOUER la reprend.") if etat.en_cours else
                      tr("La prochaine partie commence votre vie."))
        self.etat_une_vie.setText(phrase)
        self.etat_une_vie.setVisible(bool(phrase))

    # ── Réagir ────────────────────────────────────────────────────────────
    def rafraichir(self, anime: bool = True) -> None:
        """Marques, sceau et aiguille sur ce que portent les fichiers."""
        valeurs = self.valeurs()
        vie = dp.une_vie_active(self.game, self.config)
        courant = dp.courant(valeurs, self.idents, vie)
        for carte in (*self.cartes_presets, *self.cartes_une_vie):
            carte.marquer(carte.ident == courant)
        sur_mesure = courant == dp.SUR_MESURE
        if self.sceau_sur_mesure is not None:
            self.sceau_sur_mesure.setVisible(sur_mesure)
        niveau = dp.niveau(valeurs, self.game.id, self.idents)
        sous = tr("Une seule vie") if vie else ""
        if sur_mesure:
            situe = dp.situer(niveau, self.crans)
            self.cadran.viser(niveau, tr("Sur mesure"), " · ".join(filter(None, (situe, sous))), anime=anime)
        else:
            # Réaliste et Impardonnable allument le cran de Normal ou de Hardcore.
            base = dp.courant(valeurs, self.idents)
            self.cadran.viser(niveau, tr(dp.PAR_IDENT[courant].nom), sous, actif=base, anime=anime)
        self._dire_etat()

    def _choisir(self, ident: str) -> None:
        if ident == self.courant():
            return
        rates = dp.appliquer(dp.PAR_IDENT[ident], self.game, self.config, self.ini, self.idents)
        self.rafraichir()
        self.choisi.emit(ident, rates)
