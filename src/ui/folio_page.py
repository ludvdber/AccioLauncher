"""Le folio d'un jeu, en PAGE : les emplacements à gauche, ce que dit la sauvegarde à droite.

Maquette « Folio HP1, quatre maisons » validée par Ludo le 2026-10-14 : les
cartes trouvées, les dragées, et la Coupe des quatre maisons en sabliers (les
points de chaque maison sont dans la sauvegarde, pas seulement ceux de
Gryffondor : la course se voit).

Ouverte depuis la fiche du jeu dans Mes années, ou depuis le bouton Folio de
la bibliothèque ; son retour ramène d'où l'on vient. Lecture seule :
`src/core/folio.py` ne fait que lire la sauvegarde, les textes du jeu et les
images des cartes (`textures_ue1.py`), toutes dans la copie installée.

La carte choisie s'affiche dans une colonne FIXE à droite (Ludo, 2026-10-14) :
sous la grille, sa fiche tombait hors de l'écran et l'on cliquait sans rien voir.
"""

from pathlib import Path

from PyQt6.QtCore import QEvent, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QImage, QLinearGradient, QPainter, QPen, QPixmap, qRgba
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.core import folio, sauvegardes
from src.core.i18n import get_language, tr
from src.ui.composants import ENCRE, ENCRE_DOUCE, feuille_de_style, police, surtitre, texte
from src.ui.fonts import cinzel, cinzel_decorative
from src.ui.galerie_page import nom_court
from src.ui.icon_button import pixmap_icone
from src.ui.reglages_widgets import _STYLE as _STYLE_RAIL
from src.ui.theme import current as current_theme, themed
from src.ui.utils import zone_defilable

_LARGEUR_RAIL = 280
_LARGEUR_FICHE = (236, 420)   # suit la fenêtre : 30 % de ce qui reste après le rail
_MARGE_FICHE = 24
_IMAGE_FICHE = 220        # la carte du jeu fait 256 : jamais agrandie
_COLONNES = 5             # 25 cartes : cinq rangées de cinq
_ECART_CASES = 8
# Plafonds relevés le 2026-10-14 (108 et 290 px) : en plein écran, la grille
# restait minuscule à gauche d'un grand vide (capture de Ludo, 2552 px).
_CASE_MIN, _CASE_MAX = 56, 160

# Les couleurs des maisons (maquette) : le haut du sablier, puis le bas.
_COULEURS = {
    folio.GRYFFONDOR: ("#e0473f", "#ae0001"),
    folio.SERPENTARD: ("#3f9a5c", "#1a472a"),
    folio.SERDAIGLE: ("#5b7bd6", "#222f5b"),
    folio.POUFSOUFFLE: ("#ecb939", "#b8860b"),
}

_STYLE = """
QPushButton#emplacement {
    background: transparent; border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 8px;
}
QPushButton#emplacement:hover { background: rgba(255, 255, 255, 0.04); }
QPushButton#emplacement:checked {
    background: rgba(214, 167, 44, 0.09); border-color: rgba(214, 167, 44, 0.45);
}
QPushButton#emplacement[focusClavier="true"]:focus { border: 2px solid #d6a72c; }
QFrame#tuile, QFrame#coupe {
    background: #0d0d1a; border: 1px solid rgba(214, 167, 44, 0.16); border-radius: 12px;
}
QFrame#fiche {
    background: #0a0a16; border: none; border-left: 1px solid rgba(214, 167, 44, 0.16);
}
"""


def nom_maison(maison: str) -> str:
    return {folio.GRYFFONDOR: tr("Gryffondor"), folio.SERPENTARD: tr("Serpentard"),
            folio.SERDAIGLE: tr("Serdaigle"), folio.POUFSOUFFLE: tr("Poufsouffle")}[maison]


def phrase_coupe(releve: folio.Releve) -> str:
    """« Serpentard mène de 18 points », « Gryffondor mène », « À égalité »."""
    tete = releve.en_tete()
    if tete is None:
        return tr("À égalité") if releve.lu and any(releve.points.values()) else ""
    maison, ecart = tete
    if maison == folio.GRYFFONDOR:
        return tr("Gryffondor mène")
    return tr("{} mène de {} points").format(nom_maison(maison), ecart)


class _Sablier(QWidget):
    """Une colonne de sable aux couleurs de la maison, haute de ses points."""

    def __init__(self, maison: str, part: float) -> None:
        super().__init__()
        self._maison = maison
        self._part = max(0.0, min(1.0, part))
        self.setFixedSize(46, 120)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        verre = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.setBrush(QColor(255, 255, 255, 8))
        p.drawRoundedRect(verre, 8, 8)
        if self._part > 0:
            haut = max(4.0, (verre.height() - 6) * self._part)
            sable = QRectF(verre.x() + 3, verre.bottom() - 3 - haut, verre.width() - 6, haut)
            clair, fonce = _COULEURS[self._maison]
            degrade = QLinearGradient(sable.topLeft(), sable.bottomLeft())
            degrade.setColorAt(0.0, QColor(clair))
            degrade.setColorAt(1.0, QColor(fonce))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(degrade)
            p.drawRoundedRect(sable, 5, 5)
        p.end()


def pixmap_texture(tex, cote: int, dpr: float) -> QPixmap:
    """Une texture du jeu (256 couleurs) en pixmap de `cote` px logiques."""
    image = QImage(tex.indices, tex.largeur, tex.hauteur, tex.largeur,
                   QImage.Format.Format_Indexed8)
    image.setColorTable([qRgba(r, v, b, 0 if tex.masquee and i == 0 else 255)
                         for i, (r, v, b, _a) in enumerate(tex.palette)])
    physique = max(1, round(cote * dpr))
    pix = QPixmap.fromImage(
        image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied).scaled(
            physique, physique, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
    pix.setDevicePixelRatio(dpr)
    return pix


class _CarteSorcier(QPushButton):
    """Une case du folio : la carte trouvée telle que le jeu la dessine, son
    numéro si le jeu n'est plus installé, des pointillés si elle reste à trouver."""

    def __init__(self, numero: int, carte: folio.Carte | None, trouvee: bool,
                 vignette=None) -> None:
        super().__init__()
        self.numero = numero
        self.trouvee = trouvee
        self.vignette = vignette if trouvee else None   # textures_ue1.TexturePaletee
        self._pix: QPixmap | None = None
        self.setCheckable(True)
        self.setAutoDefault(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(_CASE_MIN, _CASE_MIN)
        nom = carte.nom if carte else tr("Carte {}").format(numero)
        self.setAccessibleName(nom if trouvee else tr("Carte pas encore trouvée"))

    def resizeEvent(self, event) -> None:
        self._pix = None
        super().resizeEvent(event)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cadre = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        choisie = self.isChecked()
        if self.trouvee:
            p.setBrush(QColor("#2a1f10") if choisie else QColor("#1a1508"))
            p.setPen(QPen(QColor("#e8c547") if choisie else QColor(214, 167, 44, 90),
                          2 if choisie else 1))
        else:
            p.setBrush(Qt.BrushStyle.NoBrush)
            stylo = QPen(QColor("#e8c547") if choisie else QColor(255, 255, 255, 46),
                         2 if choisie else 1)
            stylo.setStyle(Qt.PenStyle.DashLine)
            p.setPen(stylo)
        p.drawRoundedRect(cadre, 6, 6)
        if self.vignette is not None:
            if self._pix is None:
                self._pix = pixmap_texture(self.vignette, self.width() - 6,
                                           self.devicePixelRatioF())
            p.drawPixmap(3, 3, self._pix)
        elif self.trouvee:
            p.setPen(QColor("#f2e6c4") if choisie else QColor("#d9cfae"))
            p.setFont(cinzel(10, bold=True))
            p.drawText(cadre, Qt.AlignmentFlag.AlignCenter, str(self.numero))
        p.end()


class _LigneEmplacement(QPushButton):
    def __init__(self, releve: folio.Releve, lieu: str, plus_avance: bool) -> None:
        super().__init__()
        self.setObjectName("emplacement")
        self.setCheckable(True)
        self.setAutoDefault(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.releve = releve
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 9, 12, 9)
        v.setSpacing(3)
        haut = QHBoxLayout()
        haut.setSpacing(8)
        nom = (tr("Sauvegarde rapide") if releve.rapide
               else tr("Emplacement {}").format(releve.emplacement))
        titre = texte(nom, 15, ENCRE)
        titre.setFont(police(15, gras=True))
        haut.addWidget(titre)
        haut.addStretch()
        from src.ui.versions_dialog import date_longue
        haut.addWidget(texte(date_longue(releve.modifie.strftime("%Y-%m-%d")), 12, ENCRE_DOUCE))
        v.addLayout(haut)
        if lieu:
            v.addWidget(texte(lieu, 13, "#c9c7da"))
        if plus_avance:
            v.addWidget(texte(tr("La plus avancée"), 12, current_theme().accent_light))
        etats = [nom, lieu,
                 tr("La plus avancée") if plus_avance else ""]
        self.setAccessibleName(", ".join(e for e in etats if e))
        for enfant in self.findChildren(QLabel):
            enfant.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # La hauteur de son CONTENU : un QPushButton ne la tire pas de son layout.
        self.setMinimumHeight(v.sizeHint().height())


class FolioPage(QDialog):
    """Ce que les sauvegardes de HP1 disent de la partie."""

    def __init__(self, game, install_path: Path, parent: QWidget | None = None,
                 revenir=None) -> None:
        super().__init__(parent)
        self.setObjectName("folio")
        self.game = game
        self._revenir = revenir
        self.setWindowTitle(tr("Folio"))
        self.setMinimumSize(900, 560)
        self.setStyleSheet(themed(_STYLE_RAIL + _STYLE) + feuille_de_style())
        self.releves = folio.emplacements_hp1(sauvegardes.fichiers(game.sauvegardes))
        system = install_path / Path(game.executable).parent
        self.cartes, self._titres = folio.textes_hp1(folio.fichier_textes(system, get_language()))
        self._paquet = folio.paquet_menu(system) if system.is_dir() else None
        self._cases: list[_CarteSorcier] = []
        self._plus = folio.le_plus_avance(self.releves)
        self.releve: folio.Releve | None = None
        self._lignes: dict[int, _LigneEmplacement] = {}

        racine = QHBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(0)
        racine.addWidget(self._rail())
        self._hote = QVBoxLayout()
        self._hote.setContentsMargins(0, 0, 0, 0)
        corps = QWidget()
        corps.setLayout(self._hote)
        racine.addWidget(corps, stretch=1)
        self._corps: QWidget | None = None
        depart = folio.la_derniere_jouee(self.releves)
        if depart is not None:
            self.choisir(depart.emplacement)
        else:
            self._afficher(None)

    # ── Rail ──

    def _rail(self) -> QFrame:
        rail = QFrame()
        rail.setObjectName("rail")
        rail.setFixedWidth(_LARGEUR_RAIL)
        lay = QVBoxLayout(rail)
        lay.setContentsMargins(18, 22, 18, 20)
        lay.setSpacing(6)
        retour = QPushButton(tr("Mes années") if self._revenir else tr("Bibliothèque"))
        retour.setObjectName("retour")
        retour.setFont(police(13))
        retour.setIcon(QIcon(pixmap_icone("retour", 16, QColor("#a9a7c4"))))
        retour.setIconSize(QSize(16, 16))
        retour.setCursor(Qt.CursorShape.PointingHandCursor)
        retour.setAutoDefault(False)
        retour.clicked.connect(self._retour)
        lay.addWidget(retour, alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addSpacing(16)
        lay.addWidget(surtitre(tr("Folio")))
        nom = QLabel(nom_court(self.game.name))
        nom.setTextFormat(Qt.TextFormat.PlainText)   # le nom vient du CATALOGUE
        nom.setWordWrap(True)
        nom.setFont(cinzel(13, bold=True))
        nom.setStyleSheet(f"color: {ENCRE}; background: transparent;")
        lay.addWidget(nom)
        lay.addSpacing(16)
        if self.releves:
            lay.addWidget(surtitre(tr("Sauvegarde lue")))
            lay.addSpacing(4)
        self._groupe = QButtonGroup(self)
        self._groupe.setExclusive(True)
        for r in self.releves:
            ligne = _LigneEmplacement(r, folio.lieu(self._titres, r.niveau), r is self._plus)
            ligne.toggled.connect(lambda oui, rel=r: oui and self._afficher(rel))
            self._groupe.addButton(ligne)
            self._lignes[r.emplacement] = ligne
            lay.addWidget(ligne)
        lay.addStretch()
        lay.addWidget(texte(tr("Lue sans être modifiée. Les autres années arriveront jeu par jeu."),
                            12, ENCRE_DOUCE, retour=True))
        return rail

    def _retour(self) -> None:
        self.accept()
        if self._revenir is not None:
            self._revenir()

    def choisir(self, emplacement: int) -> None:
        ligne = self._lignes.get(emplacement)
        if ligne is not None:
            ligne.setChecked(True)

    # ── Corps ──

    def _afficher(self, releve: folio.Releve | None) -> None:
        self.releve = releve
        if self._corps is not None:
            self._corps.hide()
            self._corps.deleteLater()
        self._corps = self._construire(releve)
        self._hote.addWidget(self._corps)

    def _construire(self, releve: folio.Releve | None) -> QWidget:
        corps = QWidget()
        h = QHBoxLayout(corps)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(36, 30, 36, 28)
        lay.setSpacing(0)
        self._zone = zone_defilable(page)
        # La largeur utile est celle du VIEWPORT, connue après la mise en page
        # de la zone, pas au redimensionnement de la page (cases trop petites).
        self._zone.viewport().installEventFilter(self)
        h.addWidget(self._zone, stretch=1)
        self._cases = []

        if releve is None or not releve.lu:
            message = (tr("Aucune sauvegarde trouvée pour ce jeu.") if releve is None else
                       tr("Rien à lire encore dans cette sauvegarde : elle date du tout début "
                          "du jeu, avant la première carte et les premiers points."))
            titre = QLabel(tr("Folio"))
            titre.setFont(cinzel_decorative(22))
            titre.setStyleSheet("color: #f4f2f8; background: transparent;")
            lay.addWidget(titre)
            lay.addSpacing(12)
            lay.addWidget(texte(message, 16, "#c9c7da", retour=True))
            lay.addStretch()
            return corps

        # Tout dans UNE colonne : à 980 px, rail, coupe et fiche côte à côte ne
        # laissaient que 380 px aux sabliers et aux cartes.
        tuiles = QHBoxLayout()
        tuiles.setSpacing(12)
        tuiles.addWidget(self._tuile(f"{len(releve.cartes)} / {folio.CARTES_HP1}",
                                     tr("Cartes trouvées")), stretch=1)
        tuiles.addWidget(self._tuile(str(releve.dragees), tr("Dragées surprises")), stretch=1)
        lay.addLayout(tuiles)
        lay.addSpacing(12)
        lay.addWidget(self._coupe(releve))
        lay.addSpacing(26)

        # L'un SOUS l'autre : côte à côte, ils imposaient 470 px à la colonne
        # et la faisaient déborder sous la fiche de la carte à 980 px.
        lay.addWidget(surtitre(tr("Cartes des sorcières et sorciers célèbres")))
        lay.addSpacing(4)
        lay.addWidget(texte(tr("Pointillés : pas encore trouvée"), 12, ENCRE_DOUCE))
        lay.addSpacing(12)
        grille = QGridLayout()
        grille.setHorizontalSpacing(_ECART_CASES)
        grille.setVerticalSpacing(_ECART_CASES)
        self._groupe_cartes = QButtonGroup(corps)
        self._groupe_cartes.setExclusive(True)
        for numero in range(1, folio.CARTES_HP1 + 1):
            trouvee = numero in releve.cartes
            vignette = folio.image_carte_hp1(self._paquet, numero) if trouvee else None
            case = _CarteSorcier(numero, self.cartes.get(numero), trouvee, vignette)
            case.toggled.connect(lambda oui, n=numero: oui and self._montrer_carte(n))
            self._groupe_cartes.addButton(case)
            grille.addWidget(case, (numero - 1) // _COLONNES, (numero - 1) % _COLONNES)
            self._cases.append(case)
        grille.setColumnStretch(_COLONNES, 1)
        lay.addLayout(grille)
        lay.addStretch()
        h.addWidget(self._colonne_fiche())
        premiere = min(releve.cartes) if releve.cartes else 1
        self._cases[premiere - 1].setChecked(True)
        self._ajuster_cases()
        return corps

    def _colonne_fiche(self) -> QFrame:
        """La carte choisie, toujours visible à droite de la grille."""
        self._fiche = QFrame()
        self._fiche.setObjectName("fiche")
        self._fiche.setFixedWidth(self._largeur_fiche())
        contenu = QWidget()
        contenu.setStyleSheet("background: transparent;")
        f = QVBoxLayout(contenu)
        f.setContentsMargins(_MARGE_FICHE, 30, _MARGE_FICHE, 24)
        f.setSpacing(6)
        self._fiche_image = QLabel()
        self._fiche_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fiche_image.setStyleSheet("background: transparent;")
        f.addWidget(self._fiche_image)
        f.addSpacing(10)
        self._fiche_nom = texte("", 18, ENCRE, retour=True)
        self._fiche_nom.setFont(cinzel(13, bold=True))
        self._fiche_dates = texte("", 13, current_theme().accent_light, retour=True)
        self._fiche_texte = texte("", 14, "#c9c7da", retour=True)
        f.addWidget(self._fiche_nom)
        f.addWidget(self._fiche_dates)
        f.addSpacing(8)
        f.addWidget(self._fiche_texte)
        f.addStretch()
        v = QVBoxLayout(self._fiche)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(zone_defilable(contenu))
        return self._fiche

    def _largeur_fiche(self) -> int:
        mini, maxi = _LARGEUR_FICHE
        return max(mini, min(maxi, int((self.width() - _LARGEUR_RAIL) * 0.3)))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._cases and self._fiche.width() != self._largeur_fiche():
            self._fiche.setFixedWidth(self._largeur_fiche())
            self._montrer_carte(self.carte_montree)

    def eventFilter(self, objet, event) -> bool:
        if event.type() == QEvent.Type.Resize and self._cases and objet is self._zone.viewport():
            self._ajuster_cases()
        return super().eventFilter(objet, event)

    def _ajuster_cases(self) -> None:
        """Les cases suivent la place : cinq par rangée, entre 56 et 160 px
        (la grande texture, 256 px : la petite serait floue à cette taille)."""
        if not self._cases:
            return
        marges = self._zone.widget().layout().contentsMargins()
        dispo = self._zone.viewport().width() - marges.left() - marges.right()
        cote = (dispo - (_COLONNES - 1) * _ECART_CASES) // _COLONNES
        cote = max(_CASE_MIN, min(_CASE_MAX, cote))
        for case in self._cases:
            if case.width() != cote:
                case.setFixedSize(cote, cote)

    def _tuile(self, chiffre: str, libelle: str) -> QFrame:
        tuile = QFrame()
        tuile.setObjectName("tuile")
        tuile.setMinimumWidth(150)
        v = QVBoxLayout(tuile)
        v.setContentsMargins(18, 14, 18, 14)
        v.setSpacing(2)
        nombre = texte(chiffre, 28, current_theme().accent_light)
        nombre.setFont(police(28, gras=True))
        v.addWidget(nombre)
        v.addWidget(texte(libelle, 13, ENCRE_DOUCE))
        return tuile

    def _coupe(self, releve: folio.Releve) -> QFrame:
        coupe = QFrame()
        coupe.setObjectName("coupe")
        v = QVBoxLayout(coupe)
        v.setContentsMargins(20, 14, 20, 16)
        v.setSpacing(12)
        # La phrase SOUS le titre : côte à côte, ils faisaient déborder la colonne à 980 px.
        entete = QVBoxLayout()
        entete.setSpacing(4)
        entete.addWidget(surtitre(tr("La Coupe des quatre maisons")))
        self.phrase_coupe = texte(phrase_coupe(releve), 13, current_theme().accent_light)
        entete.addWidget(self.phrase_coupe)
        v.addLayout(entete)
        rangee = QHBoxLayout()
        rangee.setSpacing(10)
        plus_haut = max(1, *releve.points.values())
        tete = releve.en_tete()
        for maison in folio.MAISONS:
            points = releve.points.get(maison, 0)
            col = QVBoxLayout()
            col.setSpacing(6)
            chiffre = texte(str(points), 15, ENCRE)
            chiffre.setFont(police(15, gras=True))
            col.addWidget(chiffre, alignment=Qt.AlignmentFlag.AlignHCenter)
            col.addWidget(_Sablier(maison, points / plus_haut), alignment=Qt.AlignmentFlag.AlignHCenter)
            col.addWidget(texte(nom_maison(maison), 13, "#dcdaea"), alignment=Qt.AlignmentFlag.AlignHCenter)
            note = (tr("En tête") if tete and tete[0] == maison
                    else tr("Votre maison") if maison == folio.GRYFFONDOR else "")
            etiquette = texte(note, 11, current_theme().accent_light if note == tr("En tête")
                              else ENCRE_DOUCE)
            etiquette.setMinimumHeight(16)
            col.addWidget(etiquette, alignment=Qt.AlignmentFlag.AlignHCenter)
            rangee.addLayout(col, stretch=1)
        v.addLayout(rangee)
        coupe.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        return coupe

    def _montrer_carte(self, numero: int) -> None:
        carte = self.cartes.get(numero)
        trouvee = self.releve is not None and numero in self.releve.cartes
        # Une carte pas trouvée ne montre pas son image : ce serait la dévoiler.
        image = folio.image_carte_hp1(self._paquet, numero) if trouvee else None
        self._fiche_image.setVisible(image is not None)
        if image is not None:
            cote = min(_IMAGE_FICHE, self._fiche.width() - 2 * _MARGE_FICHE)
            self._fiche_image.setFixedHeight(cote)
            self._fiche_image.setPixmap(pixmap_texture(image, cote, self.devicePixelRatioF()))
        if trouvee:
            self._fiche_nom.setText(carte.nom if carte else tr("Carte {}").format(numero))
            self._fiche_dates.setText(carte.dates if carte else "")
            self._fiche_texte.setText(carte.texte if carte else
                                      tr("Le texte de la carte se lit dans le jeu installé."))
        else:
            self._fiche_nom.setText(tr("Pas encore trouvée"))
            self._fiche_dates.setText("")
            self._fiche_texte.setText(tr("Elle se cache quelque part dans le château. Le folio "
                                         "ne dit pas où, pour ne rien gâcher."))
        self.carte_montree = numero
