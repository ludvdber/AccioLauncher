"""Le folio de HP3, HP5 et HP6, en PAGE, sur le modèle de celui de HP1.

Maquettes du canevas « Folios HP3, HP5, HP6 » (2026-10-15), validées par Ludo
(« pour le moment les maquettes vont bien »). Même rail des parties à gauche
(`FolioPage`), le corps change par jeu ; tout est LU dans les sauvegardes
(`core/folio_hp3.py`, `folio_hp5.py`, `folio_hp6.py`) et dans le jeu installé
(noms, descriptions et images des cartes de HP3), rien n'est recopié.

HP3 range ses 80 cartes par série, comme le folio du jeu : une série de 15
prend une rangée entière (10 + 5), deux séries de 5 se partagent une rangée,
et toutes les cases restent alignées sur dix colonnes.
"""

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from src.core import folio_hp3, folio_hp5, folio_hp6, sauvegardes
from src.core.i18n import get_language, tr
from src.ui.composants import ENCRE, ENCRE_DOUCE, police, surtitre, texte
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
    classe = {"hp3": FolioPageHP3, "hp5": FolioPageHP5, "hp6": FolioPageHP6}.get(game.id, FolioPage)
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


def _tuile(chiffre: str, libelle: str, part: float | None = None) -> QFrame:
    """Le chiffre en or, son libellé, et sa jauge s'il a un total."""
    tuile = QFrame()
    tuile.setObjectName("tuile")
    tuile.setMinimumWidth(140)
    v = QVBoxLayout(tuile)
    v.setContentsMargins(18, 14, 18, 14)
    v.setSpacing(4)
    nombre = texte(chiffre, 26, current_theme().accent_light)
    nombre.setFont(police(26, gras=True))
    v.addWidget(nombre)
    v.addWidget(texte(libelle, 13, ENCRE_DOUCE, retour=True))
    if part is not None:
        v.addSpacing(4)
        v.addWidget(_Jauge(part))
    return tuile


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
        g.addWidget(surtitre(tr("Défis de sortilège")), 0, 0, 1, 3)
        or_clair = current_theme().accent_light
        for rang, d in enumerate(defis, 1):
            g.addWidget(texte(d.nom, 14, ENCRE), rang, 0)
            g.addWidget(texte(tr("Boucliers {} / {}").format(d.boucliers, d.boucliers_total),
                              13, or_clair), rang, 1)
            if d.secrets_total:
                g.addWidget(texte(tr("Zones secrètes {} / {}").format(d.secrets, d.secrets_total),
                                  13, or_clair), rang, 2)
        g.setColumnStretch(0, 1)
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

        return _page(contenu)[0]


_PUCE = """QLabel { color: #f2f2f4; background: rgba(214, 167, 44, 0.08);
    border: 1px solid rgba(214, 167, 44, 0.45); border-radius: 12px; padding: 5px 14px; }"""
