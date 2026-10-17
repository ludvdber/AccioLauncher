"""Le folio de HP2 à HP6, en PAGE, sur le modèle de celui de HP1.

Maquettes du canevas « Folios HP3, HP5, HP6 » (2026-10-15), validées par Ludo
(« pour le moment les maquettes vont bien »). Même rail des parties à gauche
(`FolioPage`), le corps change par jeu ; tout est LU dans les sauvegardes
(`core/folio_hp3.py`, `folio_hp4.py`, `folio_hp5.py`, `folio_hp6.py`) et dans le jeu installé
(noms, descriptions et images des cartes de HP3, noms des sorts et des quêtes de
HP4), rien n'est recopié. La page HP4 n'a pas de maquette validée : elle reprend
les tuiles et les cadres des autres.

HP3 range ses 80 cartes par série, comme le folio du jeu : une série de 15
prend une rangée entière (10 + 5), deux séries de 5 se partagent une rangée,
et toutes les cases restent alignées sur dix colonnes.
"""

import unicodedata
from html import escape
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from src.core import (
    folio,
    folio_hp2,
    folio_hp3,
    folio_hp4,
    folio_hp5,
    folio_hp6,
    folio_hp7,
    sauvegardes,
)
from src.core.i18n import get_language, tr
from src.ui.composants import ENCRE, ENCRE_DOUCE, police, surtitre, texte
from src.ui.flow_layout import FlowLayout
from src.ui.folio_page import (
    _ECART_CASES,
    _IMAGE_FICHE,
    _MARGE_FICHE,
    FolioPage,
    _CarteSorcier,
    nom_emplacement,
    pixmap_texture,
)
from src.ui.theme import accent_qcolor, current as current_theme, themed
from src.ui.utils import zone_defilable

_SERIE_PLEINE = 5     # au-delà, une série prend la rangée entière


def page_folio(game, install_path: Path, parent: QWidget | None = None, revenir=None) -> FolioPage:
    """La page du folio qui va avec le jeu (`folio.JEUX`)."""
    classe = {"hp2": FolioPageHP2, "hp3": FolioPageHP3, "hp4": FolioPageHP4, "hp5": FolioPageHP5,
              "hp7a": FolioPageHP7, "hp7b": FolioPageHP7,
              "hp6": FolioPageHP6}.get(game.id, FolioPage)
    return classe(game, install_path, parent, revenir=revenir)


class _Jauge(QWidget):
    """Une part sur un total, en or sur un rail discret."""

    def __init__(self, part: float) -> None:
        super().__init__()
        self.setFixedHeight(5)
        self._part = max(0.0, min(1.0, part))

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 30))
        p.drawRoundedRect(self.rect().toRectF(), 2.5, 2.5)
        if self._part > 0:
            plein = self.rect().toRectF()
            plein.setWidth(max(5.0, plein.width() * self._part))
            p.setBrush(accent_qcolor())
            p.drawRoundedRect(plein, 2.5, 2.5)
        p.end()


def _tuile(chiffre: str, libelle: str, part: float | None = None,
           icone: QPixmap | None = None) -> QFrame:
    """Le chiffre en or, son libellé, et sa jauge s'il a un total ; à droite,
    l'icône du jeu s'il en a une (HP2 : dragées, étoiles, folio)."""
    tuile = QFrame()
    tuile.setObjectName("tuile")
    tuile.setMinimumWidth(140)
    h = QHBoxLayout(tuile)
    h.setContentsMargins(18, 14, 14, 14)
    h.setSpacing(10)
    v = QVBoxLayout()
    v.setSpacing(4)
    h.addLayout(v, stretch=1)
    if icone is not None:
        image = QLabel()
        image.setStyleSheet("background: transparent;")
        image.setPixmap(icone)
        h.addWidget(image, alignment=Qt.AlignmentFlag.AlignVCenter)
    nombre = texte(chiffre, 26, current_theme().accent_light)
    nombre.setFont(police(26, gras=True))
    v.addWidget(nombre)
    v.addWidget(texte(libelle, 13, ENCRE_DOUCE, retour=True))
    if part is not None:
        v.addSpacing(4)
        v.addWidget(_Jauge(part))
    return tuile


def _pastille(nom: str, glyphe: QPixmap | None, appris: bool) -> QFrame:
    """Un sort : son glyphe (la forme tracée en jeu) et son nom ; en
    pointillés s'il reste à apprendre (même style que les sorts de HP1)."""
    cadre = QFrame()
    cadre.setObjectName("sortAppris" if appris else "sortAVenir")
    cadre.setFixedHeight(34)          # avec ou sans glyphe, la même ligne
    h = QHBoxLayout(cadre)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(6)
    if glyphe is not None and appris:
        image = QLabel()
        image.setStyleSheet("background: transparent; border: none; padding: 0;")
        image.setPixmap(glyphe)
        h.addWidget(image)
    nom_ = texte(nom, 14, "#f2e6c4" if appris else "#7d7b96")
    nom_.setFont(police(14, gras=appris))
    nom_.setStyleSheet(nom_.styleSheet() + " border: none; padding: 0;")
    h.addWidget(nom_)
    cadre.setAccessibleName(nom + ", " + (tr("appris") if appris else tr("pas encore appris")))
    return cadre


def _objet(nom: str, nombre: int, icone: QPixmap | None) -> QFrame:
    """Un objet de l'inventaire : icône du jeu, nombre, nom."""
    cadre = QFrame()
    cadre.setObjectName("objet")
    h = QHBoxLayout(cadre)
    h.setContentsMargins(12, 8, 16, 8)
    h.setSpacing(10)
    if icone is not None:
        image = QLabel()
        image.setStyleSheet("background: transparent;")
        image.setPixmap(icone)
        h.addWidget(image)
    v = QVBoxLayout()
    v.setSpacing(0)
    chiffre = texte(str(nombre), 18, current_theme().accent_light)
    chiffre.setFont(police(18, gras=True))
    v.addWidget(chiffre)
    v.addWidget(texte(nom, 12, ENCRE_DOUCE))
    h.addLayout(v)
    return cadre


def image_bgra(image: tuple[int, int, bytes] | None, cote: int, dpr: float) -> QPixmap | None:
    """Une image du jeu en B V R A (HP4) à `cote` px logiques, ou None."""
    if image is None:
        return None
    largeur, hauteur, pixels = image
    brute = QImage(pixels, largeur, hauteur, largeur * 4, QImage.Format.Format_ARGB32)
    physique = max(1, round(cote * dpr))
    pix = QPixmap.fromImage(brute.scaled(physique, physique, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation))
    pix.setDevicePixelRatio(dpr)
    return pix


_MEDAILLE = 48


def _medaille(image: tuple[int, int, bytes], acquis: bool, textes: tuple[str, str] | None,
              dpr: float) -> QLabel:
    """Un badge de HP6 : son image ronde, en gris s'il reste à remporter
    (« Les badges grisés n'ont pas encore été remportés », dit le jeu), et
    son nom avec la façon de l'obtenir au survol."""
    pix = image_bgra(image, _MEDAILLE, dpr)
    rond = QPixmap(round(_MEDAILLE * dpr), round(_MEDAILLE * dpr))
    rond.setDevicePixelRatio(dpr)
    rond.fill(Qt.GlobalColor.transparent)
    if pix is not None:
        if not acquis:
            gris = pix.toImage().convertToFormat(QImage.Format.Format_Grayscale8)
            pix = QPixmap.fromImage(gris)
            pix.setDevicePixelRatio(dpr)
        p = QPainter(rond)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        chemin = QPainterPath()
        chemin.addEllipse(QRectF(0.5, 0.5, _MEDAILLE - 1, _MEDAILLE - 1))
        p.setClipPath(chemin)
        p.setOpacity(1.0 if acquis else 0.35)
        p.drawPixmap(0, 0, pix)
        p.end()
    medaille = QLabel()
    medaille.setFixedSize(_MEDAILLE, _MEDAILLE)
    medaille.setStyleSheet("background: transparent;")
    medaille.setPixmap(rond)
    etat = tr("remporté") if acquis else tr("pas encore remporté")
    if textes is not None:
        nom, comment = textes
        medaille.setToolTip(f"<b>{escape(nom)}</b><br>{escape(comment)}<br><i>{escape(etat)}</i>")
        medaille.setAccessibleName(f"{nom}, {etat}")
    else:
        medaille.setAccessibleName(etat)
    return medaille


def _rangee(*tuiles: QFrame) -> QHBoxLayout:
    rang = QHBoxLayout()
    rang.setSpacing(12)
    for t in tuiles:
        rang.addWidget(t, stretch=1)
    return rang


def _page(construire) -> tuple[QWidget, QVBoxLayout]:
    """Le corps d'une page sans grille : une colonne qui défile."""
    corps = QWidget()
    h = QHBoxLayout(corps)
    h.setContentsMargins(0, 0, 0, 0)
    page = QWidget()
    page.setStyleSheet("background: transparent;")
    lay = QVBoxLayout(page)
    lay.setContentsMargins(36, 30, 36, 28)
    lay.setSpacing(0)
    construire(lay)
    lay.addStretch()
    h.addWidget(zone_defilable(page), stretch=1)
    return corps, lay


# ── HP3 ──

class FolioPageHP3(FolioPage):
    """Cartes par série, friandises, défis de sortilège."""

    _colonnes = 10
    _case_min = 32     # dix colonnes : à 980 px, 56 px par case débordaient

    def _charger(self) -> None:
        self.releves = folio_hp3.emplacements(sauvegardes.fichiers(self.game.sauvegardes))
        self._cat = folio_hp3.catalogue(self._system, get_language())
        lus = [r for r in self.releves if r.lu]
        self._plus = (max(lus, key=lambda r: (len(r.cartes), r.dragees))
                      if len(self.releves) > 1 and lus else None)

    def _entree(self, releve) -> tuple[str, datetime | None, str]:
        return nom_emplacement(releve), releve.modifie, ""

    def _construire(self, releve) -> QWidget:
        if releve is None or not releve.lu:
            return super()._construire(releve)
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
        self._zone.viewport().installEventFilter(self)
        h.addWidget(self._zone, stretch=1)
        self._cases = []

        total = len(self._cat.cartes) or releve.total_cartes or folio_hp3.CARTES
        lay.addLayout(_rangee(
            _tuile(f"{len(releve.cartes)} / {total}", tr("Cartes trouvées"),
                   len(releve.cartes) / total),
            _tuile(str(releve.dragees), tr("Dragées surprises")),
            _tuile(str(releve.pasties), tr("Patacitrouilles")),
            _tuile(str(releve.gateaux), tr("Fondants du chaudron"))))
        defis = folio_hp3.defis(releve, self._cat.defis)
        if defis:
            lay.addSpacing(12)
            lay.addWidget(self._defis(defis))
        lay.addSpacing(26)

        if not self._cat.cartes:
            lay.addWidget(texte(tr("Les noms et les images des cartes se lisent dans le jeu "
                                   "installé."), 14, "#c9c7da", retour=True))
            lay.addStretch()
            return corps
        lay.addWidget(texte(tr("Pointillés : pas encore trouvée"), 12, ENCRE_DOUCE))
        lay.addSpacing(10)
        self._groupe_cartes = QButtonGroup(corps)
        self._groupe_cartes.setExclusive(True)
        lay.addLayout(self._series(releve))
        lay.addStretch()
        h.addWidget(self._colonne_fiche())
        trouvees = [i for i, c in enumerate(self._cat.cartes, 1) if c.classe in releve.cartes]
        self._cases[(trouvees[0] if trouvees else 1) - 1].setChecked(True)
        self._ajuster_cases()
        return corps

    def _defis(self, defis: list[folio_hp3.Defi]) -> QFrame:
        cadre = QFrame()
        cadre.setObjectName("coupe")
        g = QGridLayout(cadre)
        g.setContentsMargins(20, 14, 20, 16)
        g.setHorizontalSpacing(24)
        g.setVerticalSpacing(8)
        g.addWidget(surtitre(tr("Défis de sortilège")), 0, 0, 1, 4)
        or_clair = current_theme().accent_light
        for rang, d in enumerate(defis, 1):
            # Le bouclier du défi, tel que le menu du jeu le dessine.
            bouclier = image_bgra(folio_hp3.image_bouclier(self._system, d.ident), 40,
                                  self.devicePixelRatioF())
            if bouclier is not None:
                image = QLabel()
                image.setStyleSheet("background: transparent;")
                image.setPixmap(bouclier)
                g.addWidget(image, rang, 0)
            g.addWidget(texte(d.nom, 14, ENCRE), rang, 1)
            g.addWidget(texte(tr("Boucliers {} / {}").format(d.boucliers, d.boucliers_total),
                              13, or_clair), rang, 2)
            if d.secrets_total:
                g.addWidget(texte(tr("Zones secrètes {} / {}").format(d.secrets, d.secrets_total),
                                  13, or_clair), rang, 3)
        g.setColumnStretch(1, 1)
        return cadre

    def _series(self, releve) -> QGridLayout:
        """Les séries sur une grille de dix colonnes : 15 cartes = une rangée
        pleine, deux séries de 5 côte à côte."""
        grille = QGridLayout()
        grille.setHorizontalSpacing(_ECART_CASES)
        grille.setVerticalSpacing(18)
        numeros = {c.code or c.classe: i for i, c in enumerate(self._cat.cartes, 1)}
        rang, colonne = 0, 0
        for serie in self._cat.series:
            pleine = len(serie.cartes) > _SERIE_PLEINE
            if pleine and colonne:
                rang, colonne = rang + 1, 0
            bloc = QVBoxLayout()
            bloc.setSpacing(8)
            trouvees = sum(1 for c in serie.cartes if c.classe in releve.cartes)
            entete = QHBoxLayout()
            entete.addWidget(surtitre(serie.titre))
            entete.addStretch()
            entete.addWidget(texte(f"{trouvees} / {len(serie.cartes)}", 12, ENCRE_DOUCE))
            bloc.addLayout(entete)
            cases = QGridLayout()
            cases.setSpacing(_ECART_CASES)
            largeur = 10 if pleine else _SERIE_PLEINE
            for k, carte in enumerate(serie.cartes):
                numero = numeros[carte.code or carte.classe]
                trouvee = carte.classe in releve.cartes
                vignette = (folio_hp3.image_carte(self._system, carte.code, grande=False)
                            if trouvee else None)
                case = _CarteSorcier(numero, carte, trouvee, vignette)
                case.toggled.connect(lambda oui, n=numero: oui and self._montrer_carte(n))
                self._groupe_cartes.addButton(case)
                cases.addWidget(case, k // largeur, k % largeur)
                self._cases.append(case)
            cases.setColumnStretch(largeur, 1)
            bloc.addLayout(cases)
            grille.addLayout(bloc, rang, colonne, 1, 2 if pleine else 1)
            if pleine or colonne:
                rang, colonne = rang + 1, 0
            else:
                colonne = 1
        grille.setColumnStretch(2, 1)
        # L'ordre des cases suit le catalogue : `_cases[numero - 1]`.
        self._cases.sort(key=lambda c: c.numero)
        return grille

    def _montrer_carte(self, numero: int) -> None:
        carte = self._cat.cartes[numero - 1]
        trouvee = self.releve is not None and carte.classe in self.releve.cartes
        # Une carte pas trouvée ne montre pas son image : ce serait la dévoiler.
        image = folio_hp3.image_carte(self._system, carte.code) if trouvee else None
        self._fiche_image.setVisible(image is not None)
        if image is not None:
            cote = min(_IMAGE_FICHE, self._fiche.width() - 2 * _MARGE_FICHE)
            self._fiche_image.setFixedHeight(cote)
            self._fiche_image.setPixmap(pixmap_texture(image, cote, self.devicePixelRatioF()))
        if trouvee:
            self._fiche_nom.setText(carte.nom)
            self._fiche_dates.setText(carte.dates)
            self._fiche_texte.setText(carte.texte)
        else:
            self._fiche_nom.setText(tr("Pas encore trouvée"))
            self._fiche_dates.setText("")
            self._fiche_texte.setText(tr("Elle se cache quelque part dans le château, ou chez "
                                         "un marchand. Le folio ne dit pas où, pour ne rien "
                                         "gâcher."))
        self.carte_montree = numero


# ── HP2 ──

class FolioPageHP2(FolioPage):
    """Les 101 cartes par catégorie (bronze, argent, or), les dragées, la Coupe
    des quatre maisons de HP1 ; le niveau nommé dans la langue du jeu."""

    _colonnes = 10
    _case_min = 32

    def _charger(self) -> None:
        self.releves = folio_hp2.emplacements(self.game.sauvegardes)
        self._cat = folio_hp2.catalogue(self._system, get_language())
        self._plus = folio.le_plus_avance(self.releves)
        self._blasons = {m: folio_hp2.image_menu(self._system, nom)
                         for m, nom in folio_hp2.BLASONS.items()}

    def _icone(self, cle: str, cote: int = 40, paquet: str = "hp2_menu.utx") -> QPixmap | None:
        """Une icône du jeu : une clé de `ICONES`, ou un nom de texture."""
        tex = folio_hp2.image_menu(self._system, folio_hp2.ICONES.get(cle, cle), paquet)
        return (pixmap_texture(tex, cote, self.devicePixelRatioF(), rogner=True)
                if tex is not None else None)

    def _sorts_et_objets(self, lay: QVBoxLayout, releve) -> None:
        """Les sorts du livre (glyphes du jeu), puis la potion et les ingrédients
        que la sauvegarde suit, avec leurs noms dans la langue du launcher."""
        lay.addWidget(surtitre(tr("Sorts appris")))
        lay.addSpacing(10)
        ligne = FlowLayout(spacing=8)
        for classes, nom, glyphe in folio_hp2.SORTS:
            appris = any(c in releve.sorts for c in classes)
            ligne.addWidget(_pastille(nom, self._icone(glyphe, 22, "spellshapes.utx") if appris
                                      else None, appris))
        lay.addLayout(ligne)
        lay.addSpacing(26)
        if not releve.objets:
            return
        noms = folio_hp2.noms_objets(self._system, get_language())
        lay.addWidget(surtitre(tr("Potion et ingrédients")))
        lay.addSpacing(10)
        ligne = FlowLayout(spacing=8)
        for item, _cle, repli, icone in folio_hp2.OBJETS:
            if item in releve.objets:
                ligne.addWidget(_objet(noms.get(item) or tr(repli), releve.objets[item],
                                       self._icone(icone, 32)))
        lay.addLayout(ligne)
        lay.addSpacing(26)

    def _entree(self, releve) -> tuple[str, datetime | None, str]:
        return (nom_emplacement(releve), releve.modifie,
                folio_hp2.lieu(self._system, get_language(), releve.titre))

    def _image(self, releve) -> Path | None:
        return folio_hp2.image_sauvegarde(releve.chemin)

    def _construire(self, releve) -> QWidget:
        if releve is None or not releve.lu:
            return super()._construire(releve)
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
        self._zone.viewport().installEventFilter(self)
        h.addWidget(self._zone, stretch=1)
        self._cases = []

        tuiles = [_tuile(f"{len(releve.cartes)} / {folio_hp2.CARTES}", tr("Cartes trouvées"),
                         len(releve.cartes) / folio_hp2.CARTES, self._icone("cartes")),
                  _tuile(str(releve.dragees), tr("Dragées surprises"), None,
                         self._icone("dragees"))]
        if releve.etoiles is not None:
            tuiles.append(_tuile(str(releve.etoiles), tr("Étoiles des défis"), None,
                                 self._icone("etoiles")))
        if releve.defis is not None:
            haut, plafond = releve.defis
            # Le plafond dans le libellé : « 300 / 500 » ne tenait pas dans une
            # tuile sur quatre à 1400 px.
            tuiles.append(_tuile(str(haut), tr("Points aux défis, sur {}").format(plafond),
                                 haut / plafond, self._icone("defis")))
        if releve.duel:
            tuiles.append(_tuile(str(releve.duel), tr("Rang au club de duel"), None,
                                 self._icone("duel")))
        lay.addLayout(_rangee(*tuiles))
        lay.addSpacing(12)
        lay.addWidget(self._coupe(releve))
        lay.addSpacing(26)
        self._sorts_et_objets(lay, releve)

        if not self._cat:
            lay.addWidget(texte(tr("Les noms et les images des cartes se lisent dans le jeu "
                                   "installé."), 14, "#c9c7da", retour=True))
            lay.addStretch()
            return corps
        lay.addWidget(texte(tr("Pointillés : pas encore trouvée"), 12, ENCRE_DOUCE))
        lay.addSpacing(10)
        self._groupe_cartes = QButtonGroup(corps)
        self._groupe_cartes.setExclusive(True)
        titres = {folio_hp2.BRONZE: tr("Cartes de bronze"),
                  folio_hp2.ARGENT: tr("Cartes d'argent"),
                  folio_hp2.OR: tr("Cartes d'or")}
        for categorie in folio_hp2.CATEGORIES:
            cartes = sorted((c for c in self._cat.values() if c.categorie == categorie),
                            key=lambda c: c.numero)
            trouvees = sum(1 for c in cartes if c.numero in releve.cartes)
            entete = QHBoxLayout()
            entete.setSpacing(8)
            pochette = self._icone(categorie, 26)
            if pochette is not None:
                image = QLabel()
                image.setStyleSheet("background: transparent;")
                image.setPixmap(pochette)
                entete.addWidget(image)
            entete.addWidget(surtitre(titres[categorie]))
            entete.addStretch()
            entete.addWidget(texte(f"{trouvees} / {len(cartes)}", 12, ENCRE_DOUCE))
            lay.addLayout(entete)
            lay.addSpacing(8)
            grille = QGridLayout()
            grille.setSpacing(_ECART_CASES)
            for k, carte in enumerate(cartes):
                trouvee = carte.numero in releve.cartes
                vignette = folio_hp2.image_carte(self._system, carte) if trouvee else None
                case = _CarteSorcier(carte.numero, carte, trouvee, vignette)
                case.toggled.connect(lambda oui, n=carte.numero: oui and self._montrer_carte(n))
                self._groupe_cartes.addButton(case)
                grille.addWidget(case, k // self._colonnes, k % self._colonnes)
                self._cases.append(case)
            grille.setColumnStretch(self._colonnes, 1)
            lay.addLayout(grille)
            lay.addSpacing(20)
        lay.addStretch()
        h.addWidget(self._colonne_fiche())
        par_numero = {c.numero: c for c in self._cases}
        premiere = min((n for n in releve.cartes if n in par_numero), default=min(par_numero))
        par_numero[premiere].setChecked(True)
        self._ajuster_cases()
        return corps

    def _montrer_carte(self, numero: int) -> None:
        carte = self._cat.get(numero)
        trouvee = self.releve is not None and numero in self.releve.cartes
        # Une carte pas trouvée ne montre pas son image : ce serait la dévoiler.
        image = folio_hp2.image_carte(self._system, carte) if trouvee and carte else None
        self._fiche_image.setVisible(image is not None)
        if image is not None:
            cote = min(_IMAGE_FICHE, self._fiche.width() - 2 * _MARGE_FICHE)
            self._fiche_image.setFixedHeight(cote)
            self._fiche_image.setPixmap(pixmap_texture(image, cote, self.devicePixelRatioF()))
        if trouvee and carte is not None:
            self._fiche_nom.setText(carte.nom)
            self._fiche_dates.setText(carte.dates)
            self._fiche_texte.setText(carte.texte)
        else:
            self._fiche_nom.setText(tr("Pas encore trouvée"))
            self._fiche_dates.setText("")
            en_vente = self.releve is not None and numero in self.releve.marchands
            self._fiche_texte.setText(
                tr("Un marchand la propose : elle s'achète avec des dragées.") if en_vente
                else tr("Elle se cache quelque part dans le château, ou chez un marchand. "
                        "Le folio ne dit pas où, pour ne rien gâcher."))
        self.carte_montree = numero


# ── HP4 ──

class FolioPageHP4(FolioPage):
    """Les trois emplacements de `HPGOF` : rang, boucliers, maîtrise, quêtes.

    Les mêmes écrans que la pensine (touche I) ; les noms viennent du jeu
    installé dans la langue du launcher, sinon du français par `tr()`."""

    def _charger(self) -> None:
        self.releves = [p for chemin in sauvegardes.fichiers(self.game.sauvegardes).values()
                        for p in folio_hp4.releve(chemin)]
        self._table = folio_hp4.textes(self._system, get_language())
        self._table_jeu = folio_hp4.textes_jeu(self._system, get_language())
        self._dragee = image_bgra(folio_hp4.image_dragee(self._system), 36,
                                  self.devicePixelRatioF())

    def _nom(self, ref: folio_hp4.Nom) -> str:
        return folio_hp4.nom(self._table, ref) or tr(ref[1])

    def _nom_jeu(self, ref: folio_hp4.Nom) -> str:
        return folio_hp4.nom(self._table_jeu, ref) or tr(ref[1])

    def _entree(self, partie) -> tuple[str, datetime | None, str]:
        rang = partie.nom_rang
        return (tr("Emplacement {}").format(partie.emplacement), partie.ecrite,
                self._nom(rang) if rang else "")

    def _depart(self):
        return max(self.releves, key=lambda p: p.ecrite or datetime.min, default=None)

    def _construire(self, partie) -> QWidget:
        if partie is None:
            return super()._construire(None)

        def contenu(lay: QVBoxLayout) -> None:
            rang = partie.nom_rang
            tuiles = [_tuile(f"{partie.boucliers} / {folio_hp4.BOUCLIERS}",
                             self._nom(folio_hp4.TITRES["boucliers"]),
                             partie.boucliers / folio_hp4.BOUCLIERS)]
            if rang:
                tuiles.insert(0, _tuile(self._nom(rang), self._nom(folio_hp4.TITRES["classement"])))
            tuiles.append(_tuile(str(partie.dragees), tr("Dragées surprises"), None,
                                 self._dragee))
            lay.addLayout(_rangee(*tuiles))
            if partie.maitrise:
                lay.addSpacing(12)
                lay.addLayout(_rangee(
                    self._jauges(folio_hp4.TITRES["sortileges"], folio_hp4.SORTILEGES, partie),
                    self._jauges(folio_hp4.TITRES["sorts"], folio_hp4.SORTS, partie)))
            if partie.quetes:
                lay.addSpacing(12)
                lay.addWidget(self._quetes(partie.quetes))
            lay.addSpacing(12)
            lay.addWidget(self._cartes(partie.cartes))

        return _page(contenu)[0]

    def _cartes(self, cartes: frozenset[int]) -> QFrame:
        """Le Folio Universitas : les cartes possédées par personnage, par famille."""
        cadre = QFrame()
        cadre.setObjectName("coupe")
        g = QGridLayout(cadre)
        g.setContentsMargins(20, 14, 20, 16)
        g.setHorizontalSpacing(16)
        g.setVerticalSpacing(10)
        g.addWidget(surtitre(self._nom_jeu(folio_hp4.TITRES_CARTES["folio"])), 0, 0, 1, 3)
        or_clair = current_theme().accent_light
        for rang, (perso, plage, familles) in enumerate(folio_hp4.PERSONNAGES, 1):
            n = folio_hp4.compte(cartes, plage)
            g.addWidget(texte(perso, 14, ENCRE if n else ENCRE_DOUCE), rang, 0)
            g.addWidget(texte((tr("{} carte") if n == 1 else tr("{} cartes")).format(n), 13,
                              or_clair if n else ENCRE_DOUCE), rang, 1)
            detail = [f"{self._nom_jeu(folio_hp4.FAMILLES[f])} {k}"
                      for f, p in familles.items() if (k := folio_hp4.compte(cartes, p))]
            g.addWidget(texte(" · ".join(detail), 13, ENCRE_DOUCE, retour=True), rang, 2)
        debut, fin = folio_hp4.CREATURES
        n = folio_hp4.compte(cartes, folio_hp4.CREATURES)
        rang = len(folio_hp4.PERSONNAGES) + 1
        g.addWidget(texte(self._nom_jeu(folio_hp4.TITRES_CARTES["creatures"]), 14,
                          ENCRE if n else ENCRE_DOUCE), rang, 0)
        g.addWidget(texte(f"{n} / {fin - debut + 1}", 13,
                          or_clair if n == fin - debut + 1 else ENCRE if n else ENCRE_DOUCE),
                    rang, 1)
        g.setColumnStretch(2, 1)
        return cadre

    def _jauges(self, titre: folio_hp4.Nom, jauges, partie) -> QFrame:
        """Une jauge par sort, comme la page de la pensine."""
        cadre = QFrame()
        cadre.setObjectName("coupe")
        g = QGridLayout(cadre)
        g.setContentsMargins(20, 14, 20, 16)
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(8)
        g.addWidget(surtitre(self._nom(titre)), 0, 0, 1, 2)
        for rang, (indice, ref, maximum) in enumerate(jauges, 1):
            part = folio_hp4.part(partie, indice, maximum)
            g.addWidget(texte(self._nom(ref), 13, ENCRE if part else ENCRE_DOUCE), rang, 0)
            g.addWidget(_Jauge(part), rang, 1, Qt.AlignmentFlag.AlignVCenter)
        g.setColumnStretch(1, 1)
        g.setRowStretch(len(jauges) + 1, 1)   # deux cadres côte à côte : le court reste en haut
        return cadre

    def _quetes(self, quetes: tuple[folio_hp4.Quete, ...]) -> QFrame:
        """Les objets à trouver, toutes les quêtes d'une même sorte additionnées."""
        cadre = QFrame()
        cadre.setObjectName("coupe")
        g = QGridLayout(cadre)
        g.setContentsMargins(20, 14, 20, 16)
        g.setHorizontalSpacing(16)
        g.setVerticalSpacing(8)
        g.addWidget(surtitre(self._nom(folio_hp4.TITRES["quetes"])), 0, 0, 1, 5)
        or_clair = current_theme().accent_light
        moitie = (len(quetes) + 1) // 2
        for k, q in enumerate(quetes):
            rang, col = 1 + k % moitie, 3 * (k // moitie)
            couleur = ENCRE if q.trouves else ENCRE_DOUCE
            g.addWidget(texte(self._nom(q.nom), 13, couleur, retour=True), rang, col)
            g.addWidget(texte(f"{q.trouves} / {q.total}", 13,
                              or_clair if q.trouves == q.total else couleur),
                        rang, col + 1, Qt.AlignmentFlag.AlignRight)
        g.setColumnStretch(0, 1)
        g.setColumnStretch(3, 1)
        g.setColumnMinimumWidth(2, 24)
        return cadre


# ── HP5 ──

class FolioPageHP5(FolioPage):
    """Les trois parties du fichier `HPOOTP` : avancement et points de découverte."""

    def _charger(self) -> None:
        self.releves = [p for chemin in sauvegardes.fichiers(self.game.sauvegardes).values()
                        for p in folio_hp5.releve(chemin)]

    def _entree(self, partie) -> tuple[str, datetime | None, str]:
        lieu = tr("{} % terminé").format(partie.pourcentage) if partie.pourcentage is not None else ""
        return tr("Partie {}").format(partie.emplacement), partie.ecrite, lieu

    def _depart(self):
        return max(self.releves, key=lambda p: p.ecrite or datetime.min, default=None)

    def _image(self, partie) -> QImage | None:
        """La vignette du chapitre, celle de l'écran « Continuer aventure »."""
        image = folio_hp5.image_chapitre(self._system, partie.chapitre)
        if image is None:
            return None
        largeur, hauteur, pixels = image
        return QImage(pixels, largeur, hauteur, largeur * 4, QImage.Format.Format_ARGB32).copy()

    def _construire(self, partie) -> QWidget:
        if partie is None:
            return super()._construire(None)

        def contenu(lay: QVBoxLayout) -> None:
            tuiles = []
            if partie.pourcentage is not None:
                tuiles.append(_tuile(f"{partie.pourcentage} %", tr("de l'histoire terminée"),
                                     partie.pourcentage / 100))
            if partie.decouverte is not None:
                tuiles.append(_tuile(
                    f"{partie.decouverte} / {folio_hp5.DECOUVERTE_MAX:,}".replace(",", " "),
                    tr("Points de découverte"), partie.decouverte / folio_hp5.DECOUVERTE_MAX))
            lay.addLayout(_rangee(*tuiles))
            if partie.compteurs is not None:
                lay.addSpacing(12)
                lay.addWidget(self._informations(partie.compteurs))

        return _page(contenu)[0]

    @staticmethod
    def _informations(compteurs: tuple[int, ...]) -> QFrame:
        """L'écran « Informations sur le jeu », en deux colonnes."""
        cadre = QFrame()
        cadre.setObjectName("coupe")
        g = QGridLayout(cadre)
        g.setContentsMargins(20, 14, 20, 16)
        g.setHorizontalSpacing(16)
        g.setVerticalSpacing(8)
        g.addWidget(surtitre(tr("Informations sur le jeu")), 0, 0, 1, 5)
        or_clair = current_theme().accent_light
        moitie = (len(compteurs) + 1) // 2
        for k, (c, n) in enumerate(zip(folio_hp5.COMPTEURS, compteurs, strict=True)):
            rang, col = 1 + k % moitie, 3 * (k // moitie)
            valeur = (f"{n * 100 // c.total} %" if c.en_pourcentage else f"{n} / {c.total}")
            g.addWidget(texte(tr(c.libelle), 13, ENCRE if n else ENCRE_DOUCE, retour=True),
                        rang, col)
            g.addWidget(texte(valeur, 13, or_clair if n else ENCRE_DOUCE), rang, col + 1,
                        Qt.AlignmentFlag.AlignRight)
        g.setColumnStretch(0, 1)
        g.setColumnStretch(3, 1)
        g.setColumnMinimumWidth(2, 24)
        return cadre


# ── HP6 ──

# Les sorts comme les livres les nomment, dans la langue du launcher.
_SORTS_HP6 = {"Expelliarmus": "Expelliarmus", "Stupefy": "Stupéfix", "Lumos": "Lumos",
              "Reparo": "Reparo", "Leviosa": "Wingardium Leviosa", "Accio": "Accio",
              "Incendio": "Incendio", "Protego": "Protego", "Petrificus": "Petrificus Totalus",
              "LeviCorpus": "Levicorpus", "Depulso": "Depulso"}


class FolioPageHP6(FolioPage):
    """Écussons, mini-écussons, chapitre, sorts et badges de l'unique partie."""

    def _charger(self) -> None:
        self.releves = []
        for chemin in sauvegardes.fichiers(self.game.sauvegardes).values():
            partie = folio_hp6.releve(chemin)
            if partie is not None:
                self.releves.append(partie)

    def _entree(self, partie) -> tuple[str, datetime | None, str]:
        lieu = tr("Chapitre {}").format(partie.chapitre) if partie.chapitre else ""
        return tr("Partie"), partie.ecrite, lieu

    def _depart(self):
        return self.releves[0] if self.releves else None

    def _construire(self, partie) -> QWidget:
        if partie is None:
            return super()._construire(None)

        def contenu(lay: QVBoxLayout) -> None:
            # Le « 3 / 25 (372) » du menu de pause ; la jauge va du palier
            # atteint au suivant, comme celle du jeu.
            atteints, vers_suivant = folio_hp6.palier(partie.mini_ecussons)
            if atteints < len(folio_hp6.PALIERS):
                detail = tr("{} ramassés, prochain palier à {}").format(
                    partie.mini_ecussons, folio_hp6.PALIERS[atteints])
            else:
                detail = tr("{} ramassés").format(partie.mini_ecussons)
            tuiles = [
                _tuile(f"{partie.ecussons} / {folio_hp6.ECUSSONS}", tr("Écussons de Poudlard"),
                       partie.ecussons / folio_hp6.ECUSSONS),
                _tuile(f"{atteints} / {len(folio_hp6.PALIERS)}",
                       tr("Paliers de mini-écussons") + "\n" + detail, vers_suivant)]
            if partie.badges_total:
                tuiles.append(_tuile(f"{partie.badges} / {partie.badges_total}", tr("Badges")))
            lay.addLayout(_rangee(*tuiles))
            if partie.sorts:
                lay.addSpacing(26)
                lay.addWidget(surtitre(tr("Sorts appris")))
                lay.addSpacing(10)
                # Quatre par rangée, chacune à la largeur de son nom (une grille
                # les étirait toutes à celle de « Wingardium Leviosa »).
                for debut in range(0, len(partie.sorts), 4):
                    rang = QHBoxLayout()
                    rang.setSpacing(8)
                    for sort in partie.sorts[debut:debut + 4]:
                        puce = texte(tr(_SORTS_HP6[sort]), 14, ENCRE)
                        puce.setStyleSheet(themed(_PUCE))
                        rang.addWidget(puce)
                    rang.addStretch()
                    lay.addLayout(rang)
                    lay.addSpacing(8)
            self._badges(lay, partie)
            lay.addSpacing(18)
            lay.addWidget(self._lieux(folio_hp6.par_lieu(partie.trouves)))

        return _page(contenu)[0]

    def _badges(self, lay: QVBoxLayout, partie) -> None:
        """Les trente badges en trois séries, comme l'écran « Badges » du jeu,
        avec ses images, ses noms et ses explications ; rien sans le jeu."""
        images = folio_hp6.images_badges(self._system)
        if not images:
            return
        textes = folio_hp6.textes_badges(self._system, get_language())
        dpr = self.devicePixelRatioF()
        lay.addSpacing(26)
        lay.addWidget(surtitre(tr("Badges")))
        for prefixe, serie in folio_hp6.SERIES:
            cles = [cle for cle, _, _ in folio_hp6.BADGES if cle.startswith(prefixe)]
            lay.addSpacing(10)
            gagnes = sum(1 for cle in cles if cle in partie.acquis)
            lay.addWidget(texte(f"{tr(serie)}  ·  {gagnes} / {len(cles)}", 13, ENCRE_DOUCE))
            lay.addSpacing(6)
            ligne = FlowLayout(spacing=6)
            for cle in cles:
                if cle in images:
                    ligne.addWidget(_medaille(images[cle], cle in partie.acquis,
                                              textes.get(cle), dpr))
            lay.addLayout(ligne)

    @staticmethod
    def _lieux(lieux: list[folio_hp6.Lieu]) -> QFrame:
        """Les écussons lieu par lieu, en deux colonnes : où chercher encore."""
        cadre = QFrame()
        cadre.setObjectName("coupe")
        g = QGridLayout(cadre)
        g.setContentsMargins(20, 14, 20, 16)
        g.setHorizontalSpacing(16)
        g.setVerticalSpacing(6)
        g.addWidget(surtitre(tr("Écussons par lieu")), 0, 0, 1, 5)
        or_clair = current_theme().accent_light
        # Par ordre alphabétique dans la langue affichée, accents ignorés
        # (« Écussons » ne doit pas tomber après « Volière »).
        noms = sorted(((tr(lieu.libelle), lieu) for lieu in lieux),
                      key=lambda paire: unicodedata.normalize("NFKD", paire[0]).casefold())
        moitie = (len(noms) + 1) // 2
        for k, (nom, lieu) in enumerate(noms):
            rang, col = 1 + k % moitie, 3 * (k // moitie)
            couleur = ENCRE if lieu.trouves else ENCRE_DOUCE
            g.addWidget(texte(nom, 13, couleur, retour=True), rang, col)
            g.addWidget(texte(f"{lieu.trouves} / {lieu.total}", 13,
                              or_clair if lieu.trouves == lieu.total else couleur),
                        rang, col + 1, Qt.AlignmentFlag.AlignRight)
        g.setColumnStretch(0, 1)
        g.setColumnStretch(3, 1)
        g.setColumnMinimumWidth(2, 24)
        return cadre


_PUCE = """QLabel { color: #f2f2f4; background: rgba(214, 167, 44, 0.08);
    border: 1px solid rgba(214, 167, 44, 0.45); border-radius: 12px; padding: 5px 14px; }"""


# ── HP7 et HP8 ──

class FolioPageHP7(FolioPage):
    """`auto.sav` des deux Reliques de la Mort : missions annexes, niveau et,
    pour la partie 1, les combats."""

    def _charger(self) -> None:
        self.releves = [p for p in (folio_hp7.releve(c) for c in
                                    sauvegardes.fichiers(self.game.sauvegardes).values())
                        if p is not None]

    def _entree(self, partie) -> tuple[str, datetime | None, str]:
        return tr("Partie"), partie.ecrite, ""

    def _depart(self):
        return max(self.releves, key=lambda p: p.ecrite or datetime.min, default=None)

    def _construire(self, partie) -> QWidget:
        if partie is None or not partie.lu:
            # Sans table de noms : le message « rien à lire encore » de HP1.
            return super()._construire(partie)

        def contenu(lay: QVBoxLayout) -> None:
            tuiles = []
            if partie.missions:
                total = len(partie.missions)
                tuiles.append(_tuile(f"{partie.missions_terminees} / {total}",
                                     tr("Missions annexes terminées"),
                                     partie.missions_terminees / total))
            niveau = partie.entier("PlayerLevel")
            if niveau:
                tuiles.append(_tuile(str(niveau), tr("Niveau")))
            if tuiles:
                lay.addLayout(_rangee(*tuiles))
            combats = [(libelle, partie.entier(nom)) for nom, libelle in folio_hp7.COMBATS
                       if partie.entier(nom) is not None]
            if combats:
                lay.addSpacing(12)
                lay.addWidget(self._combats(combats))

        return _page(contenu)[0]

    @staticmethod
    def _combats(combats: list[tuple[str, int | None]]) -> QFrame:
        cadre = QFrame()
        cadre.setObjectName("coupe")
        g = QGridLayout(cadre)
        g.setContentsMargins(20, 14, 20, 16)
        g.setHorizontalSpacing(16)
        g.setVerticalSpacing(8)
        g.addWidget(surtitre(tr("Combats")), 0, 0, 1, 2)
        or_clair = current_theme().accent_light
        for rang, (libelle, n) in enumerate(combats, 1):
            g.addWidget(texte(tr(libelle), 13, ENCRE if n else ENCRE_DOUCE, retour=True), rang, 0)
            g.addWidget(texte(str(n or 0), 13, or_clair if n else ENCRE_DOUCE), rang, 1,
                        Qt.AlignmentFlag.AlignRight)
        g.setColumnStretch(0, 1)
        return cadre
