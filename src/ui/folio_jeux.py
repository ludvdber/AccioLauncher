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
from concurrent.futures import ThreadPoolExecutor
from html import escape
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
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
from src.ui.carte_3d import Carte3D
from src.ui.composants import ENCRE, ENCRE_DOUCE, police, surtitre, texte
from src.ui.flow_layout import FlowLayout
from src.ui.fonts import cinzel
from src.ui.folio_page import (
    _ECART_CASES,
    _IMAGE_FICHE,
    _LARGEUR_RAIL,
    _MARGE_FICHE,
    FolioPage,
    Rangee,
    _CarteSorcier,
    _Jauge,
    _tuile,
    en_tete,
    image_bgra,
    nom_emplacement,
    pixmap_texture,
)
from src.ui.theme import accent_qcolor, bg_qcolor, current as current_theme, themed
from src.ui.utils import zone_defilable

_SERIE_PLEINE = 5     # au-delà, une série prend la rangée entière


def page_folio(game, install_path: Path, parent: QWidget | None = None,
               integree: bool = False) -> FolioPage:
    """La page du folio qui va avec le jeu (`folio.JEUX`)."""
    classe = {"hp2": FolioPageHP2, "hp3": FolioPageHP3, "hp4": FolioPageHP4, "hp5": FolioPageHP5,
              "hp7a": FolioPageHP7, "hp7b": FolioPageHP7,
              "hp6": FolioPageHP6}.get(game.id, FolioPage)
    return classe(game, install_path, parent, integree=integree)


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


_MEDAILLE = 48


def _rond(image: tuple[int, int, bytes] | None, cote: int, dpr: float,
          acquis: bool = True) -> QPixmap | None:
    """Une image de badge de HP6 dans un disque, en gris s'il reste à remporter."""
    pix = image_bgra(image, cote, dpr)
    if pix is None:
        return None
    rond = QPixmap(round(cote * dpr), round(cote * dpr))
    rond.setDevicePixelRatio(dpr)
    rond.fill(Qt.GlobalColor.transparent)
    if not acquis:
        gris = pix.toImage().convertToFormat(QImage.Format.Format_Grayscale8)
        pix = QPixmap.fromImage(gris)
        pix.setDevicePixelRatio(dpr)
    p = QPainter(rond)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    chemin = QPainterPath()
    chemin.addEllipse(QRectF(0.5, 0.5, cote - 1, cote - 1))
    p.setClipPath(chemin)
    p.setOpacity(1.0 if acquis else 0.35)
    p.drawPixmap(0, 0, pix)
    p.end()
    return rond


def _medaille(image: tuple[int, int, bytes], acquis: bool, textes: tuple[str, str] | None,
              dpr: float) -> QLabel:
    """Un badge de HP6 : son image ronde, en gris s'il reste à remporter
    (« Les badges grisés n'ont pas encore été remportés », dit le jeu), et
    son nom avec la façon de l'obtenir au survol."""
    rond = _rond(image, _MEDAILLE, dpr, acquis)
    if rond is None:
        rond = QPixmap(round(_MEDAILLE * dpr), round(_MEDAILLE * dpr))
        rond.setDevicePixelRatio(dpr)
        rond.fill(Qt.GlobalColor.transparent)
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
    rang.setContentsMargins(0, 0, 0, 0)
    rang.addWidget(Rangee(*tuiles))
    return rang


def _page(construire, droite: QWidget | None = None) -> tuple[QWidget, QVBoxLayout]:
    """Le corps d'une page sans grille : une colonne qui défile, et `droite`
    fixe à côté (la carte choisie de HP4, comme la fiche de HP1)."""
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
    if droite is not None:
        h.addWidget(droite)
    return corps, lay


# ── HP3 ──

class FolioPageHP3(FolioPage):
    """Cartes par série, friandises, défis de sortilège."""

    _colonnes = 10
    _case_min = 30     # dix colonnes : à 980 px, 56 puis 32 px par case débordaient

    def _charger(self) -> None:
        self.releves = folio_hp3.emplacements(sauvegardes.fichiers(self.game.sauvegardes))
        self._cat = folio_hp3.catalogue(self._system, get_language())
        lus = [r for r in self.releves if r.lu]
        self._plus = (max(lus, key=lambda r: (len(r.cartes), r.dragees))
                      if len(self.releves) > 1 and lus else None)

    def _entree(self, releve) -> tuple[str, datetime | None, str]:
        return nom_emplacement(releve), releve.modifie, ""

    def _icone(self, nom: str, cote: int = 40) -> QPixmap | None:
        """Une image de `HP3_Menu.utx`, rognée à sa partie visible."""
        return image_bgra(folio_hp3.image_menu(self._system, nom), cote,
                          self.devicePixelRatioF(), rogner=True)

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
                   len(releve.cartes) / total, self._icone(folio_hp3.ICONES["cartes"])),
            _tuile(str(releve.dragees), tr("Dragées surprises"), None,
                   self._icone(folio_hp3.ICONES["dragees"])),
            _tuile(str(releve.pasties), tr("Patacitrouilles"), None,
                   self._icone(folio_hp3.ICONES["pasties"])),
            _tuile(str(releve.gateaux), tr("Fondants du chaudron"), None,
                   self._icone(folio_hp3.ICONES["gateaux"]))))
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
        g.addWidget(surtitre(tr("Défis de sortilège")), 0, 0, 1, 3)
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
            g.addWidget(texte(d.nom, 14, ENCRE, retour=True), rang, 1)
            # Les deux comptes l'un sous l'autre : sur une ligne, le cadre
            # imposait 528 px à une fenêtre de 980 (2026-10-17).
            comptes = QVBoxLayout()
            comptes.setSpacing(2)
            comptes.addWidget(texte(tr("Boucliers {} / {}").format(d.boucliers, d.boucliers_total),
                                    13, or_clair))
            if d.secrets_total:
                comptes.addWidget(texte(
                    tr("Zones secrètes {} / {}").format(d.secrets, d.secrets_total), 13, or_clair))
            g.addLayout(comptes, rang, 2)
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
            # Le pentagone de la série, celui des onglets du folio du jeu.
            bloc.addLayout(en_tete(serie.titre, self._icone(f"Card{serie.code}", 24),
                                   f"{trouvees} / {len(serie.cartes)}"))
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
            cote = min(_IMAGE_FICHE, self._fiche.width() - 2 * _MARGE_FICHE - 1)   # 1 : le liseré
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
                                         "un marchand."))
        self.carte_montree = numero


# ── HP2 ──

class FolioPageHP2(FolioPage):
    """Les 101 cartes par catégorie (bronze, argent, or), les dragées, la Coupe
    des quatre maisons de HP1 ; le niveau nommé dans la langue du jeu."""

    _colonnes = 10
    _case_min = 30

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
            lay.addLayout(en_tete(titres[categorie], self._icone(categorie, 26),
                                  f"{trouvees} / {len(cartes)}"))
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
            cote = min(_IMAGE_FICHE, self._fiche.width() - 2 * _MARGE_FICHE - 1)   # 1 : le liseré
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
                else tr("Elle se cache quelque part dans le château, ou chez un marchand."))
        self.carte_montree = numero


# ── HP4 ──

_VIGNETTE_HP4 = 30                      # hauteur d'une case ; une carte de personnage est deux fois plus large
_GRANDE_CARTE = QSize(420, 230)         # la carte de personnage fait 512 × 256 : jamais agrandie
_PETITE_CARTE = 260                     # largeur de la carte choisie sur une fenêtre étroite


def _illustration(system: Path, jeu: folio_hp4.JeuCartes, rang: int,
                  taille: QSize | None) -> QImage | None:
    """L'illustration d'une carte, réduite à `taille` (px physiques) ou entière.
    Appelée sur le fil de décodage : une QImage, jamais une QPixmap."""
    image = folio_hp4.image_carte(system, jeu, rang)
    if image is None:
        return None
    largeur, hauteur, pixels = image
    brute = QImage(pixels, largeur, hauteur, largeur * 4, QImage.Format.Format_ARGB32)
    if taille is None:
        return brute.copy()          # la copie garde ses pixels : `pixels` peut s'en aller
    return brute.scaled(taille, Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)


class _VignetteHP4(QPushButton):
    """Une carte d'un jeu de la boutique : son illustration si elle est
    possédée, une carte vide bordée d'or si le jeu ne l'illustre pas, des
    pointillés si elle reste à obtenir (la montrer serait la dévoiler)."""

    def __init__(self, jeu: folio_hp4.JeuCartes, rang: int, possedee: bool, taille: QSize,
                 titre_jeu: str) -> None:
        super().__init__()
        self.jeu, self.rang, self.possedee, self.titre_jeu = jeu, rang, possedee, titre_jeu
        self._image: QImage | None = None
        self._pix: QPixmap | None = None
        self.setCheckable(True)
        self.setAutoDefault(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(taille)
        self.setAccessibleName(f"{titre_jeu}, " + (tr("Obtenue") if possedee
                                                   else tr("Pas encore obtenue")))

    def poser(self, image: QImage | None) -> None:
        self._image, self._pix = image, None
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cadre = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        choisie = self.isChecked()
        or_vif = accent_qcolor(255)
        if self._image is not None:
            if self._pix is None:
                self._pix = QPixmap.fromImage(self._image)
                self._pix.setDevicePixelRatio(self.devicePixelRatioF())
            chemin = QPainterPath()
            chemin.addRoundedRect(cadre, 3, 3)
            p.setClipPath(chemin)
            p.drawPixmap(cadre, self._pix, QRectF(self._pix.rect()))
            p.setClipping(False)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(or_vif, 2) if choisie else Qt.PenStyle.NoPen)
        elif self.possedee:
            p.setBrush(bg_qcolor(255))
            p.setPen(QPen(or_vif if choisie else accent_qcolor(150), 2 if choisie else 1))
        else:
            p.setBrush(Qt.BrushStyle.NoBrush)
            stylo = QPen(or_vif if choisie else QColor(255, 255, 255, 46), 2 if choisie else 1)
            stylo.setStyle(Qt.PenStyle.DashLine)
            p.setPen(stylo)
        p.drawRoundedRect(cadre, 3, 3)
        p.end()


class FolioPageHP4(FolioPage):
    """Les trois emplacements de `HPGOF` : rang, boucliers, maîtrise, quêtes.

    Les mêmes écrans que la pensine (touche I) ; les noms viennent du jeu
    installé dans la langue du launcher, sinon du français par `tr()`."""

    def _charger(self) -> None:
        self.releves = [p for chemin in sauvegardes.fichiers(self.game.sauvegardes).values()
                        for p in folio_hp4.releve(chemin)]
        self._table = folio_hp4.textes(self._system, get_language())
        self._table_jeu = folio_hp4.textes_jeu(self._system, get_language())
        self._index_jeu = folio_hp4.index_jeu(self._system, get_language()) if self._table_jeu else {}
        dpr = self.devicePixelRatioF()
        self._dragee = image_bgra(folio_hp4.image_dragee(self._system), 36, dpr, rogner=True)
        # Les objets de la pensine sans leurs volutes : la bande du milieu.
        self._bouclier = image_bgra(folio_hp4.image_menu(self._system, "boucliers"), 40, dpr,
                                    rogner=True, colonnes=(0.27, 0.73))
        self._carte = image_bgra(folio_hp4.image_menu(self._system, "cartes"), 30, dpr,
                                 rogner=True, colonnes=(0.27, 0.73))
        # Les illustrations des cartes, 0,08 s chacune : décodées sur un fil à
        # part et posées au fil de l'eau, comme les vignettes de la galerie.
        self._fil = ThreadPoolExecutor(max_workers=1, thread_name_prefix="folio_hp4")
        self._attendues: list = []
        self._grande_attendue = None
        self._carte_montree_hp4 = None
        self._chargeur = QTimer(self)
        self._chargeur.setInterval(30)
        self._chargeur.timeout.connect(self._poser_pretes)

    def _chemin(self, partie) -> Path | None:
        return None      # un fichier, plusieurs emplacements : pas de temps par partie

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

        # La carte choisie, FIXE à droite : sous la grille, il fallait
        # descendre la choisir puis remonter la voir (Ludo, 2026-10-27).
        colonne = self._colonne_carte()

        def contenu(lay: QVBoxLayout) -> None:
            rang = partie.nom_rang
            tuiles = [_tuile(f"{partie.boucliers} / {folio_hp4.BOUCLIERS}",
                             self._nom(folio_hp4.TITRES["boucliers"]),
                             partie.boucliers / folio_hp4.BOUCLIERS, self._bouclier)]
            if rang:
                tuiles.insert(0, _tuile(self._nom(rang), self._nom(folio_hp4.TITRES["classement"])))
            tuiles.append(_tuile(str(partie.dragees), tr("Dragées surprises"), None,
                                 self._dragee))
            lay.addLayout(_rangee(*tuiles))
            if partie.maitrise:
                lay.addSpacing(12)
                rangee = QHBoxLayout()
                rangee.setSpacing(12)
                rangee.addWidget(self._jauges(folio_hp4.TITRES["sortileges"],
                                              folio_hp4.SORTILEGES, partie), stretch=1)
                rangee.addWidget(self._jauges(folio_hp4.TITRES["sorts"], folio_hp4.SORTS,
                                              partie, colonnes=2), stretch=2)
                lay.addLayout(rangee)
            if partie.quetes:
                lay.addSpacing(12)
                lay.addWidget(self._quetes(partie.quetes))
            lay.addSpacing(12)
            lay.addWidget(self._cartes(partie.cartes))

        return _page(contenu, colonne)[0]

    def _largeur_colonne(self) -> int:
        return max(_PETITE_CARTE, min(_GRANDE_CARTE.width(),
                                      int((self.width() - _LARGEUR_RAIL) * 0.36))) + 2 * _MARGE_FICHE

    def _taille_carte(self, colonne: int) -> QSize:
        largeur = colonne - 2 * _MARGE_FICHE
        # Presque carrée : une carte de créature est en hauteur, celle d'un
        # personnage deux fois plus large que haute ; les deux y tiennent.
        return QSize(largeur, round(largeur * 0.85))

    def _colonne_carte(self) -> QFrame:
        """La carte choisie en grand, qui s'incline sous la souris comme dans
        le jeu, et ce qu'on en sait dessous."""
        self._colonne_hp4 = QFrame()
        self._colonne_hp4.setObjectName("fiche")
        largeur = self._largeur_colonne()
        self._colonne_hp4.setFixedWidth(largeur)
        contenu = QWidget()
        contenu.setStyleSheet("background: transparent;")
        fiche = QVBoxLayout(contenu)
        fiche.setContentsMargins(_MARGE_FICHE, 30, _MARGE_FICHE, 24)
        fiche.setSpacing(4)
        self._grande = Carte3D()
        self._grande.setFixedSize(self._taille_carte(largeur))
        fiche.addWidget(self._grande)
        fiche.addSpacing(10)
        self._carte_jeu = surtitre("")
        self._carte_nom = texte("", 18, ENCRE, retour=True)
        self._carte_nom.setFont(cinzel(13, bold=True))
        self._carte_texte = texte("", 14, "#c9c7da", retour=True)
        self._carte_etat = texte("", 13, current_theme().accent_light, retour=True)
        fiche.addWidget(self._carte_jeu)
        fiche.addSpacing(4)
        fiche.addWidget(self._carte_nom)
        fiche.addWidget(self._carte_texte)
        fiche.addSpacing(6)
        fiche.addWidget(self._carte_etat)
        fiche.addStretch()
        v = QVBoxLayout(self._colonne_hp4)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(zone_defilable(contenu))
        return self._colonne_hp4

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        colonne = getattr(self, "_colonne_hp4", None)
        try:
            if colonne is not None and colonne.width() != self._largeur_colonne():
                colonne.setFixedWidth(self._largeur_colonne())
                self._grande.setFixedSize(self._taille_carte(self._largeur_colonne()))
        except RuntimeError:            # colonne d'une autre partie, déjà détruite
            self._colonne_hp4 = None

    def _cartes(self, cartes: frozenset[int]) -> QFrame:
        """Le Folio Universitas : les jeux de la boutique, chaque carte possédée
        avec son illustration ; la carte choisie est dans la colonne de droite."""
        self._attendues = []           # les vignettes d'une autre partie ne se posent plus
        cadre = QFrame()
        cadre.setObjectName("coupe")
        lay = QVBoxLayout(cadre)
        lay.setContentsMargins(20, 14, 20, 18)
        lay.setSpacing(10)
        jeux = [j for _, groupe in folio_hp4.GROUPES_CARTES for j in groupe]
        total = sum(1 for j in jeux for c in j.cartes if c in cartes)
        lay.addLayout(en_tete(self._nom_jeu(folio_hp4.TITRES_CARTES["folio"]), self._carte,
                              (tr("{} carte") if total == 1 else tr("{} cartes")).format(total)))

        self._groupe_cartes = QButtonGroup(cadre)
        self._groupe_cartes.setExclusive(True)
        self._vignettes: list[_VignetteHP4] = []
        or_clair = current_theme().accent_light
        dpr = self.devicePixelRatioF()
        for titre, groupe in folio_hp4.GROUPES_CARTES:
            nom_groupe = titre if isinstance(titre, str) else self._nom_jeu(titre)
            dans = sum(1 for j in groupe for c in j.cartes if c in cartes)
            sur = sum(len(j.cartes) for j in groupe)
            lay.addSpacing(8)
            ligne = QHBoxLayout()
            ligne.setSpacing(10)
            ligne.addWidget(texte(nom_groupe, 15, ENCRE if dans else ENCRE_DOUCE))
            ligne.addWidget(texte(f"{dans} / {sur}", 13,
                                  or_clair if dans == sur else ENCRE if dans else ENCRE_DOUCE))
            ligne.addStretch()
            lay.addLayout(ligne)
            jeux_du_groupe = FlowLayout(spacing=16)
            for k, jeu in enumerate(groupe, 1):
                jeux_du_groupe.addWidget(self._jeu(nom_groupe, jeu, k, cartes, dpr))
            lay.addLayout(jeux_du_groupe)

        possedees = [v for v in self._vignettes if v.possedee and v.rang < v.jeu.images]
        (possedees or self._vignettes)[0].setChecked(True)
        if self._attendues:
            self._chargeur.start()
        return cadre

    def _jeu(self, nom_groupe: str, jeu: folio_hp4.JeuCartes, numero: int,
             cartes: frozenset[int], dpr: float) -> QWidget:
        """Un jeu de la boutique : son titre, son compte, ses cartes en ligne."""
        bloc = QWidget()
        bloc.setStyleSheet("background: transparent;")
        v = QVBoxLayout(bloc)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        titre = self._nom_jeu(jeu.titre).format(numero)
        dans = sum(1 for c in jeu.cartes if c in cartes)
        v.addWidget(texte(f"{titre} · {dans} / {len(jeu.cartes)}", 12, ENCRE_DOUCE))
        rangee = QHBoxLayout()
        rangee.setSpacing(4)
        paysage = jeu.image.startswith(("wc_hry", "wc_ron", "wc_hermione"))
        taille = QSize(_VIGNETTE_HP4 * (2 if paysage else 1), _VIGNETTE_HP4)
        for rang, carte in enumerate(jeu.cartes):
            vignette = _VignetteHP4(jeu, rang, carte in cartes, taille, f"{nom_groupe} · {titre}")
            vignette.toggled.connect(lambda oui, vi=vignette: oui and self._montrer_carte_hp4(vi))
            self._groupe_cartes.addButton(vignette)
            self._vignettes.append(vignette)
            rangee.addWidget(vignette)
            if vignette.possedee and rang < jeu.images:
                physique = QSize(round(taille.width() * dpr), round(taille.height() * dpr))
                self._attendues.append((vignette, self._fil.submit(
                    _illustration, self._system, jeu, rang, physique)))
        rangee.addStretch()
        v.addLayout(rangee)
        return bloc

    def _montrer_carte_hp4(self, vignette: _VignetteHP4) -> None:
        """La carte choisie en grand, décodée hors du fil de l'interface."""
        self._carte_montree_hp4 = vignette
        self._carte_jeu.setText(vignette.titre_jeu.upper())
        # Nom et description : la boutique du jeu les montre avant l'achat ;
        # l'illustration, elle, reste réservée aux cartes obtenues.
        nom_carte, description = folio_hp4.texte_carte(self._table_jeu,
                                                        vignette.jeu.cartes[vignette.rang],
                                                        self._index_jeu)
        self._carte_nom.setText(nom_carte)
        self._carte_nom.setVisible(bool(nom_carte))
        self._carte_texte.setText(description)
        self._carte_texte.setVisible(bool(description))
        illustree = vignette.rang < vignette.jeu.images
        if not vignette.possedee:
            etat = tr("Pas encore obtenue")
        elif illustree:
            etat = tr("Obtenue")
        else:
            etat = tr("Obtenue, sans illustration dans le jeu")
        self._carte_etat.setText(etat)
        self._grande.poser(None)
        self._grande_attendue = None
        if vignette.possedee and illustree:
            self._grande_attendue = (vignette, self._fil.submit(
                _illustration, self._system, vignette.jeu, vignette.rang, None))
            self._chargeur.start()

    def _poser_pretes(self) -> None:
        restantes = []
        for vignette, futur in self._attendues:
            if not futur.done():
                restantes.append((vignette, futur))
            elif not futur.cancelled() and futur.exception() is None:
                vignette.poser(futur.result())
        self._attendues = restantes
        if self._grande_attendue is not None and self._grande_attendue[1].done():
            vignette, futur = self._grande_attendue
            self._grande_attendue = None
            if (vignette is self._carte_montree_hp4 and not futur.cancelled()
                    and futur.exception() is None):
                self._grande.poser(futur.result())
        if not self._attendues and self._grande_attendue is None:
            self._chargeur.stop()

    def done(self, resultat: int) -> None:
        """La page se ferme : plus rien à décoder pour elle."""
        self._chargeur.stop()
        self._fil.shutdown(wait=False, cancel_futures=True)
        super().done(resultat)

    def _jauges(self, titre: folio_hp4.Nom, jauges, partie, colonnes: int = 1) -> QFrame:
        """Une jauge par sort, comme la page de la pensine ; les dix sorts sur
        deux colonnes, à côté des quatre sortilèges (une seule laissait un
        cadre de sortilèges à moitié vide)."""
        cadre = QFrame()
        cadre.setObjectName("coupe")
        g = QGridLayout(cadre)
        g.setContentsMargins(20, 14, 20, 16)
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(8)
        g.addWidget(surtitre(self._nom(titre)), 0, 0, 1, 3 * colonnes - 1)
        hauteur = -(-len(jauges) // colonnes)
        for k, (indice, ref, maximum) in enumerate(jauges):
            rang, col = 1 + k % hauteur, 3 * (k // hauteur)
            part = folio_hp4.part(partie, indice, maximum)
            g.addWidget(texte(self._nom(ref), 13, ENCRE if part else ENCRE_DOUCE), rang, col)
            g.addWidget(_Jauge(part), rang, col + 1, Qt.AlignmentFlag.AlignVCenter)
            g.setColumnStretch(col + 1, 1)
        for c in range(1, colonnes):
            g.setColumnMinimumWidth(3 * c - 1, 12)
        # Deux cadres côte à côte : le court reste en haut. Pas d'étirement de
        # rangée : il rendait la grille extensible, et les deux cadres prenaient
        # tout le bas de la page.
        g.setAlignment(Qt.AlignmentFlag.AlignTop)
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

    def _chemin(self, partie) -> Path | None:
        return None      # les trois parties de `HPOOTP` partagent un fichier

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
                    tr("Points de découverte"), partie.decouverte / folio_hp5.DECOUVERTE_MAX,
                    image_bgra(folio_hp5.image_decouverte(self._system), 36,
                               self.devicePixelRatioF())))
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
        # Une partie par fichier, mais la partie ne porte pas son chemin.
        self._chemins: dict[int, Path] = {}
        for chemin in sauvegardes.fichiers(self.game.sauvegardes).values():
            partie = folio_hp6.releve(chemin)
            if partie is not None:
                self.releves.append(partie)
                self._chemins[id(partie)] = chemin

    def _chemin(self, partie) -> Path | None:
        return self._chemins.get(id(partie))

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
            dpr = self.devicePixelRatioF()
            tuiles = [
                _tuile(f"{partie.ecussons} / {folio_hp6.ECUSSONS}", tr("Écussons de Poudlard"),
                       partie.ecussons / folio_hp6.ECUSSONS,
                       image_bgra(folio_hp6.image_menu(self._system, "ecussons"), 44, dpr)),
                _tuile(f"{atteints} / {len(folio_hp6.PALIERS)}",
                       tr("Paliers de mini-écussons") + "\n" + detail, vers_suivant,
                       image_bgra(folio_hp6.image_menu(self._system, "mini"), 44, dpr))]
            if partie.badges_total:
                # Le dernier badge remporté, dans l'ordre de l'écran du jeu.
                gagne = next((cle for cle, _, _ in reversed(folio_hp6.BADGES)
                              if cle in partie.acquis), None)
                images = folio_hp6.images_badges(self._system) if gagne else {}
                tuiles.append(_tuile(f"{partie.badges} / {partie.badges_total}", tr("Badges"),
                                     partie.badges / partie.badges_total,
                                     _rond(images.get(gagne), 40, dpr) if gagne else None))
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
