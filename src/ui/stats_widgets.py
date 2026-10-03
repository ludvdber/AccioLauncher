"""Les pièces de « Mes années à Poudlard » : l'étagère, les mois, la scolarité, les cartes de sauvegarde et leurs petites fonctions de mise en forme. Sorti de `stats_dialog` le 2026-10-03 (1 062 lignes) ; la fenêtre les assemble.
"""
from datetime import date
from html import escape
from PyQt6.QtCore import QLocale, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QImageReader, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from src.core import sauvegardes, scolarite
from src.core.config import ASSETS_DIR
from src.core.formatting import format_duree_compacte
from src.core.i18n import get_language, tr
from src.ui.focus_visible import PROPRIETE as _FOCUS_CLAVIER
from src.ui.fonts import cinzel
from src.ui.theme import accent_qcolor, bg_qcolor

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


def _cible_au_clavier(touche, ordre: list, pos: int):
    """←/→/Début/Fin dans `ordre` depuis `pos` (-1 : rien de choisi) ; None pour une autre touche."""
    if touche == Qt.Key.Key_Right:
        return ordre[min(pos + 1, len(ordre) - 1)]
    if touche == Qt.Key.Key_Left:
        return ordre[max(pos - 1, 0)]
    if touche == Qt.Key.Key_Home:
        return ordre[0]
    if touche == Qt.Key.Key_End:
        return ordre[-1]
    return None


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
        cible = _cible_au_clavier(event.key(), ordre, pos)
        if cible is None:
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


class _Scolarite(QWidget):
    """Les sept années en une bande — où l'on en est dans la scolarité.

    Toujours SEPT cases, même vides : une année que personne n'a commencée est
    une information (« elle t'attend »), pas une absence à masquer. C'est le
    même principe que l'étagère au-dessus, qui montre toujours huit jaquettes.

    Rien n'est collecté pour ça : l'année vient du catalogue, le statut du
    temps de jeu et de l'état d'installation, tous deux déjà mesurés. C'est une
    LECTURE du catalogue, pas un mécanisme de plus.
    """

    _HAUTEUR = 42
    _ECART = 6

    # Une année se CHOISIT : elle porte le jeu de cette année dans la fiche du
    # dessous. Un bloc qui a l'air d'un bouton et ne répond pas est pire qu'un
    # bloc inerte — c'est le premier reproche de Ludo à cette bande.
    choisi = pyqtSignal(str)              # identifiant du jeu de l'année

    def __init__(self, annees: list[scolarite.Annee], courante: int,
                 selectionnables: set[str] | None = None, parent=None) -> None:
        super().__init__(parent)
        self._annees = annees
        self._courante = courante
        self._selectionnables = selectionnables or set()
        self._survol: int | None = None
        self.setFixedHeight(self._HAUTEUR)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        if self._jouables():
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.setAccessibleName(tr("Les sept années"))

    def _jouables(self) -> list[int]:
        """Les index des années dont un jeu a quelque chose à montrer."""
        return [i for i, a in enumerate(self._annees)
                if any(j.id in self._selectionnables for j in a.jeux)]

    def _jeu_de(self, i: int) -> str | None:
        for jeu in self._annees[i].jeux:
            if jeu.id in self._selectionnables:
                return jeu.id
        return None

    def _case(self, i: int) -> QRectF:
        largeur = (self.width() - self._ECART * (len(self._annees) - 1)) \
            / max(len(self._annees), 1)
        return QRectF(i * (largeur + self._ECART), 0.0,
                      largeur, float(self._HAUTEUR))

    def _index_sous(self, x: float) -> int | None:
        for i in range(len(self._annees)):
            if self._case(i).contains(x, self._HAUTEUR / 2):
                return i
        return None

    def mouseMoveEvent(self, event) -> None:
        i = self._index_sous(event.position().x())
        survol = i if i is not None and self._jeu_de(i) else None
        if survol != self._survol:
            self._survol = survol
            self.update()
        if survol is None:
            self.unsetCursor()
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def leaveEvent(self, event) -> None:
        if self._survol is not None:
            self._survol = None
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            i = self._index_sous(event.position().x())
            if i is not None:
                self._choisir(i)
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        """←/→/Début/Fin, comme l'étagère : un contrôle peint qui se clique
        doit s'atteindre au clavier (règle du projet, payée sur `ToggleSwitch`)."""
        ordre = self._jouables()
        if not ordre:
            super().keyPressEvent(event)
            return
        pos = ordre.index(self._survol) if self._survol in ordre else -1
        touche = event.key()
        cible = _cible_au_clavier(touche, ordre, pos)
        if cible is None and touche in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if pos >= 0:
                self._choisir(ordre[pos])
            return
        if cible is None:
            super().keyPressEvent(event)
            return
        self._survol = cible
        self.update()
        self._choisir(cible)

    def _choisir(self, i: int) -> None:
        gid = self._jeu_de(i)
        if gid is not None:
            self.choisi.emit(gid)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(cinzel(13, bold=True))
        clavier = self.property(_FOCUS_CLAVIER) and self.hasFocus()
        for i, annee in enumerate(self._annees):
            case = self._case(i).adjusted(0.5, 0.5, -0.5, -0.5)
            actuelle = annee.numero == self._courante
            if annee.statut is scolarite.Statut.COMMENCEE:
                p.setBrush(accent_qcolor(38))
                bord, encre = accent_qcolor(165), QColor("#f2f2f4")
            elif annee.statut is scolarite.Statut.EN_ATTENTE:
                p.setBrush(Qt.BrushStyle.NoBrush)
                bord, encre = QColor(255, 255, 255, 52), QColor(_SECONDAIRE)
            else:
                p.setBrush(Qt.BrushStyle.NoBrush)
                bord, encre = QColor(255, 255, 255, 22), QColor("#6a6a82")
            if i == self._survol:
                p.setBrush(accent_qcolor(60))
                bord, encre = accent_qcolor(200), QColor("#f2f2f4")
            # L'année EN COURS se distingue par l'épaisseur du trait et non par
            # une couleur de plus : la page en compte déjà assez, et un trait
            # plus franc se lit sans qu'on ait à apprendre un code.
            p.setPen(QPen(accent_qcolor(230) if actuelle else bord,
                          2.0 if actuelle else 1.0))
            p.drawRoundedRect(case, 5.0, 5.0)
            p.setPen(encre)
            p.drawText(case, int(Qt.AlignmentFlag.AlignCenter), str(annee.numero))
            # Anneau de focus DESSINÉ : un widget peint n'est jamais atteint
            # par la règle `:focus` de la feuille de style.
            if clavier and i == self._survol:
                p.setPen(QPen(accent_qcolor(255), 2.0))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(case.adjusted(-2, -2, 2, 2), 7.0, 7.0)
        p.end()
