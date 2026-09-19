"""La saga — ce que le launcher a observé de tes parties.

**Refondue le 2026-09-19** sur la maquette « l'étagère » choisie par Ludo,
avec le grand histogramme des mois de la maquette « le registre » :

· **l'étagère** — les huit jaquettes dans l'ordre de la saga, toujours huit.
  C'est le squelette de la page, et il ne dépend pas des données : une page
  dont la structure varie a l'air cassée bien avant d'avoir l'air pauvre
  (diagnostic de la version du 2026-08-27, qui reste vrai). On y CHOISIT un
  jeu : seuls ceux qui ont quelque chose à dire se laissent choisir ;
· **la fiche du jeu choisi** — son temps, ses parties, la dernière fois, puis
  ses SAUVEGARDES en cartes : commencée quand, écrite pour la dernière fois
  quand, combien de parties, combien de temps. C'était la demande principale ;
  les chiffres viennent de `src/core/sauvegardes.py`, qui compare les
  sauvegardes avant et après chaque partie ;
· **la colonne de la saga** — le total, l'année, le mois, la plus longue
  partie avec sa date ;
· **les douze derniers mois** en barres. Des heures, pas des pourcentages, et
  des barres, pas un camembert : ce que réclament les joueurs de Steam et de
  GOG Galaxy (audit du 2026-09-19).

Ce qui ne revient pas, pour les raisons écrites dans la version précédente :
la liste des jeux jamais lancés, la série de jours, le jour et la plage
horaire de prédilection, les démarrages du launcher et les octets téléchargés.
Et **aucun zéro** : une ligne sans valeur ne s'affiche pas, une sauvegarde
dont on n'a vu aucune partie dit « — » et pourquoi, jamais une estimation.
"""

from datetime import date
from html import escape

from PyQt6.QtCore import QLocale, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QImageReader, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.core import sauvegardes, stats
from src.core.config import ASSETS_DIR
from src.core.formatting import format_duree_compacte
from src.core.game_manager import GameManager
from src.core.i18n import get_language, tr
from src.ui.focus_visible import PROPRIETE as _FOCUS_CLAVIER
from src.ui.fonts import cinzel
from src.ui.theme import accent_qcolor, bg_qcolor, themed

_SECONDAIRE = "#b0b0c8"
_DISCRET = "#8a8aa6"

# L'étagère : huit jaquettes, largeur partagée, HAUTEUR DÉDUITE de la largeur.
# En 2:3, cinq jaquettes sur huit sont exactes et seules les trois carrées
# (HP2, HP7a, HP7b) sont recadrées ; une case à 0,83 les rognait toutes. La
# hauteur n'est JAMAIS une constante posée à côté de la largeur — le défaut
# du carrousel, payé deux fois.
_FRISE_RAPPORT = 2 / 3          # largeur / hauteur d'une case
_FRISE_LEGENDE_H = 24
_FRISE_ECART = 8
_FRISE_LEVEE = 6                # la jaquette choisie se soulève d'autant

_HISTO_H = 130
_COLONNE_SAGA = 250

# Plafond d'ouverture : au-delà, le corps défile. La fenêtre ne s'ouvre
# JAMAIS plus haute que son contenu — c'est ce plafond qui borne, pas un vide.
# Il suit l'ÉCRAN : 720 px fixes coupaient les douze mois sur un 1440p, où il
# restait 400 px libres, et 900 fixes déborderaient d'un portable 1366×768.
_HAUTEUR_MAX = 900
_MARGE_ECRAN = 80


def _hauteur_max(widget: QWidget) -> int:
    ecran = widget.screen()
    if ecran is None:
        return _HAUTEUR_MAX
    return max(400, min(_HAUTEUR_MAX, ecran.availableGeometry().height() - _MARGE_ECRAN))


def _duree_courte(secondes: int) -> str:
    """Durée pour une LÉGENDE, où la place se compte en dizaines de pixels.

    `format_duree_compacte` rend « moins d'une minute » (105 px dans une case
    de 98 : on lisait « oins d'une minu ») et « 12 h 05 min », trop long au
    pied d'une barre.
    """
    if secondes < 60:
        return tr("< 1 min")
    if secondes < 3600:
        # Même arrondi que la colonne de la saga : la barre de septembre et
        # la ligne « En septembre » portaient 38 et 39 min pour 38,5.
        return _duree(secondes)
    return tr("{} h").format(int(secondes / 3600 + 0.5))


def _minutes(secondes: int) -> int:
    """Arrondi à la minute la plus proche, demi-minute vers le haut.

    `round()` arrondit au PAIR (46,5 → 46) : juste pour une moyenne, faux pour
    un compteur qu'on additionne à la main.
    """
    return int(secondes / 60 + 0.5) if secondes > 0 else 0


def _duree(secondes: int) -> str:
    """Toute durée de la page passe par ici : même arrondi partout.

    `format_duree_compacte` arrondit au PAIR (`round`), `_minutes` à la
    demi-minute supérieure : mélangés, 38,5 min s'écrivaient 38 sur la barre
    et 39 dans la colonne.
    """
    return format_duree_compacte(60 * _minutes(secondes) if secondes >= 60 else secondes)


def _date(jour: date | None) -> str:
    return jour.strftime("%d/%m/%Y") if jour else ""


def _locale() -> QLocale:
    """Les noms de mois dans la langue de l'INTERFACE, par Qt : vingt-quatre
    chaînes de moins à faire traduire à des bénévoles."""
    return QLocale(get_language())


def _texte(contenu: str, taille: int = 13, couleur: str = "#ffffff",
           gras: bool = False) -> QLabel:
    """QLabel en PlainText — ces chaînes portent des noms venus du CATALOGUE,
    et `AutoText` bascule en rich text dès que Qt renifle du HTML."""
    lbl = QLabel(contenu)
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    poids = "bold" if gras else "normal"
    lbl.setStyleSheet(
        f"color: {couleur}; font-size: {taille}px; font-weight: {poids};"
        " background: transparent;")
    return lbl


def _chiffre(valeur: str, taille: int = 20, couleur: str = "#ffffff") -> QLabel:
    lbl = QLabel(valeur)
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    lbl.setFont(cinzel(taille, bold=True))
    lbl.setStyleSheet(f"color: {couleur}; background: transparent;")
    return lbl


def _titre_section(texte: str) -> QLabel:
    lbl = QLabel(texte.upper())
    lbl.setObjectName("titreSection")
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    return lbl


class _Paragraphe(QLabel):
    """Texte long en `wordWrap`, dont la hauteur suit la largeur RÉELLE.

    Un `QLabel` en `wordWrap` posé dans un layout sans hauteur imposée annonce
    un `sizeHint` calculé à une largeur qui n'est pas la sienne : le layout ne
    lui accorde qu'une ligne et le texte se coupe. Le piège a été payé cinq
    fois dans ce projet ; le remède vit ici une fois pour toutes.
    """

    def __init__(self, contenu: str, parent=None, taille: int = 12) -> None:
        super().__init__(contenu, parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True)
        self.setStyleSheet(
            f"color: {_SECONDAIRE}; font-size: {taille}px; background: transparent;")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.setMinimumHeight(0)
        self.setMinimumHeight(self.heightForWidth(self.width()))


class _Etagere(QWidget):
    """Les huit jeux dans l'ordre de la saga, dont on choisit un.

    Peinte à la main plutôt que posée en `QLabel` : la largeur d'une case se
    déduit de celle du widget, donc l'étagère tient à toutes les tailles de
    fenêtre sans qu'aucun nombre ne soit écrit à côté d'un autre.

    **Pas de pourcentage de complétion**, et les jaquettes non jouées ne sont
    ni grisées ni désaturées : seul le voile de SÉLECTION les distingue, et il
    tombe sur toutes sauf la choisie — il désigne un choix, pas une absence.

    Atteignable au clavier (←/→, Début/Fin) avec un anneau DESSINÉ : un widget
    peint n'est pas atteint par la règle `:focus` du stylesheet.
    """

    choisi = pyqtSignal(str)

    def __init__(self, entrees, legendes: dict[str, str],
                 selectionnables: set[str], choix: str | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self._entrees = list(entrees)
        self._legendes = legendes
        self._selectionnables = selectionnables
        self._choix = choix if choix in selectionnables else None
        self._jaquettes: dict[str, QPixmap] = {}
        self.setMouseTracking(True)
        if selectionnables:
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.setAccessibleName(tr("Jeux de la saga"))
        for e in self._entrees:
            pm = self._charger(e.game.cover_image)
            if pm is not None:
                self._jaquettes[e.game.id] = pm

    @property
    def choix(self) -> str | None:
        return self._choix

    @staticmethod
    def _charger(nom_fichier: str) -> QPixmap | None:
        """Réduction demandée AU DÉCODEUR, comme le carrousel : décoder un
        JPEG 1024×1024 en pleine résolution pour l'afficher à 150 px coûte huit
        fois le temps de l'ouverture de la page."""
        chemin = ASSETS_DIR / "covers" / nom_fichier
        if not chemin.exists():
            return None
        lecteur = QImageReader(str(chemin))
        source = lecteur.size()
        if source.isValid() and source.height() > 0:
            facteur = 400 / source.height()
            if facteur < 1.0:
                lecteur.setScaledSize(source * facteur)
        image = lecteur.read()
        return None if image.isNull() else QPixmap.fromImage(image)

    def _largeur_case(self) -> float:
        n = max(1, len(self._entrees))
        return (self.width() - _FRISE_ECART * (n - 1)) / n

    def resizeEvent(self, event) -> None:
        """La hauteur se DÉDUIT de la largeur reçue — jamais l'inverse."""
        super().resizeEvent(event)
        voulue = (round(self._largeur_case() / _FRISE_RAPPORT)
                  + _FRISE_LEVEE + _FRISE_LEGENDE_H)
        if voulue != self.height():
            self.setFixedHeight(voulue)

    def _case(self, i: int) -> QRectF:
        largeur = self._largeur_case()
        leve = 0.0 if self._entrees[i].game.id == self._choix else _FRISE_LEVEE
        return QRectF(i * (largeur + _FRISE_ECART), leve,
                      largeur, largeur / _FRISE_RAPPORT)

    def _index_sous(self, x: float) -> int | None:
        for i in range(len(self._entrees)):
            case = self._case(i)
            if case.left() <= x <= case.right():
                return i
        return None

    def choisir(self, game_id: str) -> None:
        if game_id in self._selectionnables and game_id != self._choix:
            self._choix = game_id
            self.update()
            self.choisi.emit(game_id)

    def mouseMoveEvent(self, event) -> None:
        """Le nom du jeu sous le curseur — sans ça, huit jaquettes muettes.

        Le nom est échappé : une infobulle est un `QLabel` laissé en `AutoText`,
        donc le seul endroit de la page où du balisage venu du catalogue serait
        INTERPRÉTÉ — tout le reste est en `PlainText` par construction.
        """
        i = self._index_sous(event.position().x())
        if i is None:
            self.setToolTip("")
            self.unsetCursor()
            return
        gid = self._entrees[i].game.id
        self.setToolTip(escape(self._entrees[i].game.name, quote=False))
        if gid in self._selectionnables:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.unsetCursor()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            i = self._index_sous(event.position().x())
            if i is not None:
                self.choisir(self._entrees[i].game.id)
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        ordre = [e.game.id for e in self._entrees if e.game.id in self._selectionnables]
        if not ordre:
            super().keyPressEvent(event)
            return
        pos = ordre.index(self._choix) if self._choix in ordre else -1
        touche = event.key()
        if touche == Qt.Key.Key_Right:
            cible = ordre[min(pos + 1, len(ordre) - 1)]
        elif touche == Qt.Key.Key_Left:
            cible = ordre[max(pos - 1, 0)]
        elif touche == Qt.Key.Key_Home:
            cible = ordre[0]
        elif touche == Qt.Key.Key_End:
            cible = ordre[-1]
        else:
            super().keyPressEvent(event)
            return
        self.choisir(cible)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        police = p.font()
        police.setPointSize(9)
        for i, entree in enumerate(self._entrees):
            gid = entree.game.id
            case = self._case(i)
            pm = self._jaquettes.get(gid)
            if pm is not None:
                p.save()
                p.setClipRect(case)
                # « Par expansion » : on couvre la case sans bande vide.
                facteur = max(case.width() / pm.width(), case.height() / pm.height())
                dessine = QRectF(0, 0, pm.width() * facteur, pm.height() * facteur)
                dessine.moveCenter(case.center())
                p.drawPixmap(dessine, pm, QRectF(pm.rect()))
                p.restore()
            else:
                p.fillRect(case, QColor(22, 33, 62))
            choisie = gid == self._choix
            if self._choix is not None and not choisie:
                p.fillRect(case, bg_qcolor(150))
            if choisie:
                p.setPen(QPen(accent_qcolor(), 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(case.adjusted(1, 1, -1, -1))
                if self.hasFocus() and self.property(_FOCUS_CLAVIER):
                    p.setPen(QPen(accent_qcolor(160), 1, Qt.PenStyle.DashLine))
                    p.drawRect(case.adjusted(-3, -3, 3, 3))

            legende = self._legendes.get(gid, "")
            if not legende:
                continue        # rien à dire : l'absence ne prend pas d'encre
            p.setFont(police)
            p.setPen(accent_qcolor() if choisie else QColor(_SECONDAIRE))
            # ÉLIDER, toujours : un `drawText` centré ne coupe rien et déborde
            # des DEUX côtés — le défaut documenté du bouton principal.
            texte = QFontMetrics(police).elidedText(
                legende, Qt.TextElideMode.ElideRight, int(case.width()))
            bas = _FRISE_LEVEE + case.height()
            p.drawText(QRectF(case.left(), bas + 4.0, case.width(),
                              _FRISE_LEGENDE_H - 4.0),
                       int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                       texte)
        p.end()


class _Mois(QWidget):
    """Les douze derniers mois en barres, le mois en cours en or vif.

    Toujours douze colonnes : c'est l'AXE. Un mois sans partie garde un trait
    au ras du sol et ne porte pas de chiffre — aucun « 0 » n'est écrit.
    """

    def __init__(self, cases: list[tuple[int, int, int]], parent=None) -> None:
        super().__init__(parent)
        self._cases = cases
        self.setFixedHeight(_HISTO_H)
        self.setMouseTracking(True)

    def _colonne(self, i: int) -> QRectF:
        n = len(self._cases)
        ecart = 6.0
        largeur = (self.width() - ecart * (n - 1)) / n
        return QRectF(i * (largeur + ecart), 0.0, largeur, float(self.height()))

    def mouseMoveEvent(self, event) -> None:
        x = event.position().x()
        for i, (annee, mois, secondes) in enumerate(self._cases):
            col = self._colonne(i)
            if col.left() <= x <= col.right():
                nom = _locale().standaloneMonthName(mois, QLocale.FormatType.LongFormat)
                valeur = _duree(secondes) if secondes else tr("aucune partie")
                self.setToolTip(f"{nom} {annee} : {valeur}")
                return
        self.setToolTip("")

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        police = p.font()
        police.setPointSize(8)
        p.setFont(police)
        fm = QFontMetrics(police)
        haut_texte = fm.height() + 4
        maxi = max((s for _, _, s in self._cases), default=0) or 1
        zone_h = self.height() - 2 * haut_texte
        loc = _locale()
        for i, (annee, mois, secondes) in enumerate(self._cases):
            col = self._colonne(i)
            actuel = i == len(self._cases) - 1
            sol = haut_texte + zone_h
            if secondes:
                h = max(4.0, zone_h * secondes / maxi)
                barre = QRectF(col.left(), sol - h, col.width(), h)
                p.fillRect(barre, accent_qcolor(255 if actuel else 175))
                p.setPen(QColor("#ffffff") if actuel else QColor(_SECONDAIRE))
                valeur = fm.elidedText(_duree_courte(secondes),
                                       Qt.TextElideMode.ElideRight, int(col.width()))
                p.drawText(QRectF(col.left(), barre.top() - haut_texte,
                                  col.width(), haut_texte),
                           int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom),
                           valeur)
            else:
                p.fillRect(QRectF(col.left(), sol - 2, col.width(), 2),
                           QColor(44, 62, 107, 140))
            nom = loc.standaloneMonthName(mois, QLocale.FormatType.ShortFormat)
            if mois == 1:
                nom = f"{nom} {annee % 100:02d}"
            p.setPen(accent_qcolor() if actuel else QColor(_DISCRET))
            p.drawText(QRectF(col.left(), sol + 3, col.width(), haut_texte),
                       int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                       fm.elidedText(nom, Qt.TextElideMode.ElideRight, int(col.width())))
        p.end()


class _Jauge(QWidget):
    """La part d'une sauvegarde dans le temps de son jeu : un filet, pas un
    pourcentage écrit."""

    def __init__(self, part: float, parent=None) -> None:
        super().__init__(parent)
        self._part = max(0.0, min(1.0, part))
        self.setFixedHeight(3)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(44, 62, 107, 140))
        if self._part:
            p.fillRect(QRectF(0, 0, self.width() * self._part, self.height()),
                       accent_qcolor())
        p.end()


class _CarteSauvegarde(QFrame):
    """Une sauvegarde : son nom, son temps, et ce que le disque sait d'elle."""

    def __init__(self, vue: sauvegardes.Vue, temps_max: int,
                 recente: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("carteSave")
        couche = QVBoxLayout(self)
        couche.setContentsMargins(14, 12, 14, 12)
        couche.setSpacing(8)

        haut = QHBoxLayout()
        nom = (tr("Emplacement {}").format(vue.numero) if vue.numero is not None
               else tr("Sauvegarde"))
        lbl_nom = QLabel(nom)
        lbl_nom.setFont(cinzel(11, bold=True))
        lbl_nom.setStyleSheet("background: transparent;")
        haut.addWidget(lbl_nom)
        if recente:
            # Celle qu'on reprendra : c'est la question qu'on se pose en
            # ouvrant un jeu à quatre emplacements, et les dates seules
            # obligent à les comparer de tête.
            haut.addWidget(_texte(tr("dernière jouée"), 11, "#d6a72c"))
        haut.addStretch(1)
        if vue.temps:
            haut.addWidget(_chiffre(_duree(vue.temps), 14, "#d6a72c"))
        couche.addLayout(haut)
        if vue.temps:
            # Une jauge vide sur quatre cartes n'est pas une information, c'est
            # quatre fois la même absence : elle n'apparaît qu'avec un temps.
            couche.addWidget(_Jauge(vue.temps / temps_max if temps_max else 0.0))

        grille = QGridLayout()
        grille.setHorizontalSpacing(12)
        grille.setVerticalSpacing(2)
        grille.setColumnStretch(1, 1)
        if vue.commencee == vue.derniere:
            # « Commencée le 4, dernière fois le 4 » : une date, dite une fois.
            lignes = [(tr("Jouée le"), _date(vue.derniere))]
        else:
            lignes = [(tr("Commencée"), _date(vue.commencee)),
                      (tr("Dernière fois"), _date(vue.derniere))]
        lignes.append((tr("Parties"), str(vue.parties) if vue.parties else ""))
        rang = 0
        for libelle, valeur in lignes:
            if not valeur:
                continue            # aucun zéro, aucune case vide
            grille.addWidget(_texte(libelle, 12, _DISCRET), rang, 0)
            v = _texte(valeur, 12, _SECONDAIRE)
            v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grille.addWidget(v, rang, 1)
            rang += 1
        couche.addLayout(grille)


class StatsDialog(QDialog):
    """La saga : l'étagère, la fiche du jeu choisi, la saga, les mois."""

    def __init__(self, manager: GameManager, parent=None) -> None:
        super().__init__(parent)
        self.manager = manager
        self._hist = stats.charger()
        # Les dérivées dont vit toute la page, calculées UNE fois.
        self._entrees = manager.get_games()
        self._noms = {e.game.id: e.game.name for e in self._entrees}
        self._temps = stats.temps_par_jeu(self._hist)
        self._parties = stats.parties_par_jeu(self._hist)
        self._dernieres = stats.derniere_par_jeu(self._hist)
        stock = sauvegardes.charger()
        self._sans_sauvegarde = {e.game.id: sauvegardes.temps_sans_sauvegarde(e.game.id, stock)
                                 for e in self._entrees}
        self._vues = {e.game.id: sauvegardes.vues(e.game.id, e.game.sauvegardes, stock)
                      for e in self._entrees}
        self.setWindowTitle(tr("Mes années à Poudlard"))
        # Assez LARGE pour que huit jaquettes restent des images et non des
        # timbres. Pas de plancher en HAUTEUR : la page se rétrécit à son
        # contenu.
        self.setMinimumWidth(820)
        self._zone: QScrollArea | None = None
        self._contenu: QWidget | None = None
        self._etagere: _Etagere | None = None
        self._fiche_hote: QVBoxLayout | None = None
        self._fiche: QWidget | None = None
        self._ajuste = False
        self.resize(920, 720)
        self.setStyleSheet(themed(self._style()))
        self._build()

    def _style(self) -> str:
        return """
        QDialog { background-color: #0d0d1a; color: #ffffff; }
        QLabel { color: #ffffff; background: transparent; }
        QLabel#titreSection {
            font-size: 11px; font-weight: bold; color: #d6a72c;
            letter-spacing: 1px;
        }
        QFrame#carteSave {
            background-color: #16213e; border: 1px solid #2c3e6b;
            border-radius: 8px;
        }
        QFrame#colonneSaga { border: none; border-left: 1px solid #2c3e6b; }
        QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }
        QScrollBar:vertical {
            background: transparent; width: 10px; margin: 0;
        }
        QScrollBar::handle:vertical {
            background: #2c3e6b; border-radius: 5px; min-height: 30px;
        }
        QScrollBar::handle:vertical:hover { background: #d6a72c; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
        QPushButton#btnClose {
            background-color: #d6a72c; color: #000000; font-weight: bold;
            border: none; border-radius: 6px; padding: 10px 24px; font-size: 14px;
        }
        QPushButton#btnClose:hover { background-color: #e6b422; }
        """

    # ──────────────────── Données ────────────────────

    def _selectionnables(self) -> set[str]:
        """Un jeu se choisit s'il a quelque chose à dire : du temps, ou des
        sauvegardes sur le disque."""
        return {gid for gid in self._noms
                if self._temps.get(gid) or self._vues.get(gid)}

    def _choix_initial(self, possibles: set[str]) -> str | None:
        """Le dernier jeu JOUÉ, sinon le plus joué, sinon le premier qui a des
        sauvegardes — l'ordre de ce qu'on a envie de revoir en ouvrant."""
        if self._dernieres:
            return max(self._dernieres, key=self._dernieres.get)
        if self._temps:
            return max(self._temps, key=self._temps.get)
        for e in self._entrees:
            if e.game.id in possibles:
                return e.game.id
        return None

    def _legendes(self) -> dict[str, str]:
        legendes = {}
        for gid in self._noms:
            if self._temps.get(gid):
                legendes[gid] = _duree_courte(self._temps[gid])
            elif self._vues.get(gid):
                # Des sauvegardes, mais aucune partie chronométrée : le temps
                # n'est pas connu, et on ne l'invente pas. Le tiret est la
                # même convention que partout ailleurs sur la page.
                legendes[gid] = "—"
        return legendes

    # ──────────────────── Construction ────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 16, 22, 16)
        root.setSpacing(12)

        titre = QLabel(tr("Mes années à Poudlard"))
        titre.setFont(cinzel(18, bold=True))
        root.addWidget(titre)
        # Le résumé ne s'écrit en tête que lorsque la page n'a RIEN d'autre à
        # dire : dès qu'il y a du temps, la colonne de la saga porte le même
        # total, et le dire deux fois (Ludo, capture du 2026-09-19) fait
        # chercher la différence entre les deux.
        ouverture = self._ouverture()
        if ouverture:
            root.addWidget(_texte(ouverture, 13, _SECONDAIRE))

        possibles = self._selectionnables()
        # L'étagère est HORS de la zone défilante : c'est le squelette de la
        # page, il ne doit jamais partir sous la ligne de flottaison.
        self._etagere = _Etagere(self._entrees, self._legendes(), possibles,
                                 self._choix_initial(possibles))
        self._etagere.choisi.connect(self._montrer_jeu)
        root.addWidget(self._etagere)

        if possibles or stats.temps_total(self._hist):
            contenu = QWidget()
            corps = QVBoxLayout(contenu)
            corps.setContentsMargins(0, 8, 8, 4)
            corps.setSpacing(24)

            # Deux colonnes : à gauche le jeu choisi PUIS les douze mois, à
            # droite la saga. Posés sous la rangée, les mois tombaient sous la
            # ligne de flottaison (mesuré à 920×720 avec les données de Ludo)
            # pendant que la fiche laissait une demi-largeur vide à côté de
            # ses cartes.
            rangee = QHBoxLayout()
            rangee.setSpacing(24)
            gauche = QVBoxLayout()
            gauche.setSpacing(24)
            self._fiche_hote = QVBoxLayout()
            self._fiche_hote.setContentsMargins(0, 0, 0, 0)
            gauche.addLayout(self._fiche_hote)
            cases = stats.douze_mois(self._hist)
            if any(s for _, _, s in cases):
                bloc = QVBoxLayout()
                bloc.setSpacing(8)
                bloc.addWidget(_titre_section(tr("Les douze derniers mois")))
                bloc.addWidget(_Mois(cases))
                gauche.addLayout(bloc)
            gauche.addStretch(1)
            rangee.addLayout(gauche, 1)
            rangee.addWidget(self._colonne_saga(), 0, Qt.AlignmentFlag.AlignTop)
            corps.addLayout(rangee)
            if self._etagere.choix is not None:
                self._montrer_jeu(self._etagere.choix)
            corps.addStretch(1)

            zone = QScrollArea()
            zone.setWidgetResizable(True)
            zone.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            zone.setWidget(contenu)
            root.addWidget(zone, 1)
            self._zone, self._contenu = zone, contenu

        bas = QHBoxLayout()
        bas.addStretch(1)
        fermer = QPushButton(tr("Fermer"))
        fermer.setObjectName("btnClose")
        fermer.setCursor(Qt.CursorShape.PointingHandCursor)
        fermer.clicked.connect(self.accept)
        bas.addWidget(fermer)
        root.addLayout(bas)

    def _ouverture(self) -> str:
        """La phrase d'en-tête des pages VIDES ; chaîne vide dès qu'il y a du
        temps, que la colonne de la saga dit mieux."""
        if sum(self._temps.values()):
            return ""
        if any(self._vues.values()):
            return tr("Tes sauvegardes sont là ; le temps de jeu se comptera "
                      "à partir de ta prochaine partie.")
        return tr("Aucune partie enregistrée pour l'instant — "
                  "lance un jeu, cette page se remplira toute seule.")

    def _colonne_saga(self) -> QWidget:
        """Toute la saga : total, année, mois, plus longue partie.

        Une ligne à zéro ne s'écrit pas : « En septembre : 0 » est une case
        vide qui apprend à ne plus lire la colonne.
        """
        cadre = QFrame()
        cadre.setObjectName("colonneSaga")
        cadre.setFixedWidth(_COLONNE_SAGA)
        couche = QVBoxLayout(cadre)
        couche.setContentsMargins(22, 0, 0, 0)
        couche.setSpacing(6)
        couche.addWidget(_titre_section(tr("Toute la saga")))

        aujourdhui = date.today()
        annee = stats.temps_annee(self._hist, aujourdhui.year)
        herite = sum(self._hist.herite.values())
        # Le total AFFICHÉ est la somme des parties AFFICHÉES, chacune arrondie
        # à la minute. Arrondir chaque ligne de son côté donnait, sur les
        # données de Ludo, « 46 min au total, dont 43 cette année et 4
        # d'avant » : 46,5 → 46, 42,9 → 43, 3,6 → 4, et 43 + 4 = 47. Un seul
        # compte qui ne tombe pas juste suffit à faire douter de toute la page.
        autres = stats.temps_total(self._hist) - annee - herite
        total = 60 * sum(_minutes(x) for x in (annee, autres, herite))
        lignes = [(tr("Au total"), total, 17)]
        mois = stats.par_mois(self._hist).get((aujourdhui.year, aujourdhui.month), 0)
        lignes.append((tr("En {}").format(aujourdhui.year), annee, 13))
        lignes.append((tr("En {}").format(_locale().standaloneMonthName(
            aujourdhui.month, QLocale.FormatType.LongFormat)), mois, 13))
        for libelle, secondes, taille in lignes:
            if not secondes:
                continue
            ligne = QHBoxLayout()
            ligne.addWidget(_texte(libelle, 12, _SECONDAIRE))
            ligne.addStretch(1)
            ligne.addWidget(_chiffre(_duree(secondes), taille,
                                     "#d6a72c" if taille > 13 else "#ffffff"))
            couche.addLayout(ligne)

        if herite:
            # Sans cette ligne, l'année et le mois ne se raccordent pas au
            # total, et quelqu'un qui le remarque cesse de croire la page.
            couche.addWidget(_Paragraphe(
                tr("Dont {} jouées avant la mise en service du journal, sans "
                   "date.").format(_duree(herite)),
                taille=11))

        longue = stats.plus_longue(self._hist)
        if longue is not None:
            couche.addSpacing(10)
            couche.addWidget(_titre_section(tr("Plus longue partie")))
            couche.addWidget(_chiffre(_duree(longue.duree), 14))
            # Jamais un record sans sa date : daté, c'est un souvenir.
            couche.addWidget(_Paragraphe(tr("{}, le {}").format(
                self._noms.get(longue.jeu, longue.jeu),
                longue.debut.strftime("%d/%m/%Y"))))
        return cadre

    def _montrer_jeu(self, game_id: str) -> None:
        """Remplace la fiche. La fenêtre ne change PAS de taille : une fenêtre
        qui saute à chaque clic sur une jaquette se lit comme un défaut ; le
        corps défile."""
        if self._fiche_hote is None:
            return
        if self._fiche is not None:
            self._fiche.hide()
            self._fiche.deleteLater()
        self._fiche = self._construire_fiche(game_id)
        self._fiche_hote.addWidget(self._fiche)

    def _construire_fiche(self, game_id: str) -> QWidget:
        fiche = QWidget()
        couche = QVBoxLayout(fiche)
        couche.setContentsMargins(0, 0, 0, 0)
        couche.setSpacing(12)
        nom = QLabel(self._noms.get(game_id, game_id))
        nom.setTextFormat(Qt.TextFormat.PlainText)
        nom.setFont(cinzel(14, bold=True))
        nom.setWordWrap(True)
        couche.addWidget(nom)

        chiffres = QHBoxLayout()
        chiffres.setSpacing(28)
        temps = self._temps.get(game_id, 0)
        parties = self._parties.get(game_id, 0)
        derniere = self._dernieres.get(game_id)
        faits = []
        if temps:
            faits.append((_duree(temps), tr("de jeu")))
        if parties:
            faits.append((str(parties), tr("parties") if parties > 1 else tr("partie")))
        if derniere:
            faits.append((_date(derniere), tr("dernière fois")))
        for valeur, libelle in faits:
            col = QVBoxLayout()
            col.setSpacing(0)
            col.addWidget(_chiffre(valeur, 16))
            col.addWidget(_texte(libelle, 11, _DISCRET))
            chiffres.addLayout(col)
        if faits:
            chiffres.addStretch(1)
            couche.addLayout(chiffres)

        vues = self._vues.get(game_id) or []
        if vues:
            couche.addSpacing(4)
            couche.addWidget(_titre_section(tr("Sauvegardes")))
            if any(v.temps is None for v in vues):
                # On ne DEVINE pas le temps d'une sauvegarde née avant le
                # relevé : on dit pourquoi il manque et quand il viendra — une
                # fois pour la section, pas une fois par carte.
                couche.addWidget(_Paragraphe(
                    tr("Le temps par sauvegarde se compte à partir de ta "
                       "prochaine partie."), taille=11))
            grille = QGridLayout()
            grille.setSpacing(12)
            temps_max = max((v.temps or 0 for v in vues), default=0)
            recente = (max(vues, key=lambda v: v.modifie).fichier
                       if len(vues) > 1 else None)
            for i, vue in enumerate(vues):
                grille.addWidget(_CarteSauvegarde(vue, temps_max, vue.fichier == recente),
                                 i // 2, i % 2)
            grille.setColumnStretch(0, 1)
            grille.setColumnStretch(1, 1)
            couche.addLayout(grille)
        sans = self._sans_sauvegarde.get(game_id, 0)
        if sans >= 60:
            # Sans cette ligne, la somme des cartes est inférieure au temps du
            # jeu et rien ne dit pourquoi. Seules les parties OBSERVÉES sans
            # écriture y entrent — jamais celles d'avant le relevé.
            couche.addWidget(_Paragraphe(
                tr("Dont {} jouées sans sauvegarder.").format(
                    _duree(sans)), taille=11))
        couche.addStretch(1)
        return fiche

    # ──────────────────── Hauteur ────────────────────

    def showEvent(self, event) -> None:
        """La hauteur ne se mesure qu'une fois la page RÉELLEMENT mise en page :
        l'étagère et les paragraphes déduisent leur hauteur de la largeur
        reçue, qu'ils n'ont pas avant d'être montrés."""
        super().showEvent(event)
        if not self._ajuste:
            self._ajuste = True
            self._ajuster_hauteur()

    def _ajuster_hauteur(self) -> None:
        """La fenêtre s'arrête où le contenu s'arrête, plafonnée par l'écran.

        L'écart est mesuré sur ce qui est POSÉ, jamais sur le `sizeHint` d'une
        `QScrollArea`, qui ne porte pas la hauteur de son contenu.
        """
        self.setMinimumHeight(0)
        self.layout().activate()
        if self._zone is not None and self._contenu is not None:
            ecart = (self._contenu.sizeHint().height()
                     - self._zone.viewport().height())
        else:
            ecart = self.sizeHint().height() - self.height()
        self.resize(self.width(), min(self.height() + ecart, _hauteur_max(self)))
