"""La galerie des captures, en PAGE : les vignettes par mois, la capture choisie à droite.

Maquette « Galerie, Discord et vitrine » validée par Ludo le 2026-10-14, avec
deux notes de sa part : dire que F12 ne marche pas encore dans les trois
premiers jeux (pour éviter des signalements inutiles), et que les plus belles
images partagées pourront aller sur le site et servir à présenter le launcher.

« Partager sur Discord » ne publie rien : le launcher n'a aucun compte relié.
Il copie l'image dans le presse-papiers et ouvre le salon #accio-medias
(`DISCORD_MEDIAS_URL`, 2026-10-22 : l'invitation seule laissait chercher le
salon) ; c'est le joueur qui la colle. La page le dit, pour qu'on ne cherche
pas où elle est partie.

Contenu : `src/core/galerie.py`. Les vignettes se décodent sur un fil à part
après l'ouverture et se rangent dans `_Launcher/cache/vignettes`
(`_poser_pretes`) : décoder d'un coup cent PNG de 2560 px figeait la page
plusieurs secondes. Seule la capture choisie est lue en grand.
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtCore import QDate, QLocale, QRectF, QSize, Qt, QTime, QTimer
from PyQt6.QtGui import QColor, QGuiApplication, QIcon, QImage, QImageReader, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.core import galerie
from src.core.i18n import get_language, tr
from src.core.liens import DISCORD_MEDIAS_URL
from src.ui.composants import ENCRE, ENCRE_DOUCE, bouton, feuille_de_style, police, surtitre, texte
from src.ui.flow_layout import FlowLayout
from src.ui.fonts import cinzel, cinzel_decorative
from src.ui.icon_button import pixmap_icone
from src.ui.theme import current as current_theme, themed
from src.ui.utils import open_local_path, open_url, zone_defilable

log = logging.getLogger(__name__)

_LARGEUR_COTE = 380
# En plein écran, la colonne et les vignettes grandissent (Ludo, 2026-10-14 :
# « mettre en plein écran n'adapte pas trop les sections »). La vignette en
# cache fait 416 px de large : au-delà de 330, elle s'agrandirait floue.
_LARGEUR_COTE_MAX = 600
_VIGNETTE_MAX = 330
_VIGNETTE = QSize(208, 117)   # 16:9
_APERCU_LARGEUR = _LARGEUR_COTE - 2 * 24

_STYLE = """
QDialog#galerie { background: #070712; }
QFrame#cote {
    background: #08081a; border: none; border-left: 1px solid rgba(214, 167, 44, 0.12);
}
QPushButton#retour {
    background: transparent; border: none; color: #a9a7c4; text-align: left; padding: 4px 2px;
}
QPushButton#retour:hover { color: #f2f2f4; }
QPushButton#filtre {
    background: transparent; border: 1px solid rgba(255, 255, 255, 0.14); border-radius: 12px;
    color: #a9a7c4; padding: 5px 12px;
}
QPushButton#filtre[vide="true"] { color: #5d5b72; }
QPushButton#filtre:hover { color: #f2f2f4; }
QPushButton#filtre:checked {
    background: rgba(214, 167, 44, 0.14); border-color: rgba(214, 167, 44, 0.6); color: #f2e6c4;
}
QPushButton#filtre[focusClavier="true"]:focus { border: 2px solid #d6a72c; }
QFrame#note {
    background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 10px;
}
QFrame#vitrine {
    background: rgba(214, 167, 44, 0.05); border: 1px solid rgba(214, 167, 44, 0.25);
    border-radius: 10px;
}
"""


def nom_court(nom: str) -> str:
    """« Harry Potter et la Coupe de Feu » → « La Coupe de Feu » (fr, en, es)."""
    court = re.sub(r"^Harry Potter(\s+(et|and|y))?\s*[:\-–]?\s*", "", nom).strip()
    return (court[:1].upper() + court[1:]) if court else nom


def mois(annee: int, numero: int) -> str:
    """« OCTOBRE 2026 » dans la langue de l'interface."""
    return QLocale(get_language()).toString(QDate(annee, numero, 1), "MMMM yyyy").upper()


def quand(capture: galerie.Capture) -> str:
    """« 14 octobre 2026, 21:03 »."""
    from src.ui.versions_dialog import date_longue
    d = capture.quand
    heure = QLocale(get_language()).toString(QTime(d.hour, d.minute), QLocale.FormatType.ShortFormat)
    return f"{date_longue(d.strftime('%Y-%m-%d'))}, {heure}"


def _recadree(image: QImage, taille: QSize) -> QPixmap:
    """L'image couvrant `taille`, centrée, sans déformation."""
    pix = QPixmap(taille)
    pix.fill(QColor("#16172c"))
    if image.isNull():
        return pix
    echelle = max(taille.width() / image.width(), taille.height() / image.height())
    larg, haut = image.width() * echelle, image.height() * echelle
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.drawImage(QRectF((taille.width() - larg) / 2, (taille.height() - haut) / 2, larg, haut), image)
    p.end()
    return pix


def _lire(chemin, largeur: int) -> QImage:
    """Décodée directement à la taille utile quand le format le permet (JPEG)."""
    lecteur = QImageReader(str(chemin))
    lecteur.setAutoTransform(True)
    taille = lecteur.size()
    if taille.isValid() and taille.width() > largeur:
        lecteur.setScaledSize(QSize(largeur, max(1, taille.height() * largeur // taille.width())))
    image = lecteur.read()
    if image.isNull():
        log.warning("Galerie : %s illisible (%s)", chemin, lecteur.errorString())
    return image


def _vignette(chemin) -> QImage:
    """La petite image d'une capture : depuis le cache, sinon décodée puis rangée.

    Appelée HORS du fil de l'interface (un QImage s'y décode sans risque ; le
    QPixmap, lui, se fabrique dans le fil de l'interface, `_Vignette.poser`).
    """
    cache = galerie.chemin_vignette(chemin)
    if cache is not None and cache.is_file():
        image = QImage(str(cache))
        if not image.isNull():
            return image
    image = _lire(chemin, _VIGNETTE.width() * 2)
    if cache is not None and not image.isNull():
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            provisoire = cache.with_suffix(".tmp")
            if image.save(str(provisoire), "JPG", 90):
                provisoire.replace(cache)
        except OSError:
            log.debug("Galerie : vignette de %s non gardée", chemin, exc_info=True)
    return image


class _Vignette(QPushButton):
    """Une capture : son image recadrée, un filet d'or quand elle est choisie."""

    def __init__(self, capture: galerie.Capture, nom_jeu: str) -> None:
        super().__init__()
        self.capture = capture
        self.setCheckable(True)
        self.setAutoDefault(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(_VIGNETTE)
        self.setAccessibleName(f"{nom_jeu}, {quand(capture)}")
        self._pix: QPixmap | None = None
        self._image: QImage | None = None

    def poser(self, image: QImage) -> None:
        self._image = image
        self.recadrer()

    def recadrer(self) -> None:
        """À la taille du bouton, en pixels réels (nette à 125 %)."""
        if self._image is None:
            return
        echelle = self.devicePixelRatioF()
        self._pix = _recadree(self._image, self.size() * echelle)
        self._pix.setDevicePixelRatio(echelle)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cadre = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self._pix is not None:
            p.drawPixmap(self.rect(), self._pix)
        else:
            p.fillRect(self.rect(), QColor("#16172c"))
        choisie = self.isChecked() or (self.hasFocus() and self.property("focusClavier"))
        p.setPen(QColor(current_theme().accent) if choisie else QColor(255, 255, 255, 22))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if choisie:
            pen = p.pen()
            pen.setWidthF(2.0)
            p.setPen(pen)
        p.drawRoundedRect(cadre, 6, 6)
        p.end()


class GaleriePage(QDialog):
    """Les captures de tous les jeux ; à droite, la choisie et ce qu'on peut en faire."""

    def __init__(self, jeux, parent: QWidget | None = None, jeu: str = "") -> None:
        super().__init__(parent)
        self.setObjectName("galerie")
        self.setWindowTitle(tr("Galerie"))
        self.setMinimumSize(900, 560)
        self.setStyleSheet(themed(_STYLE) + feuille_de_style())
        self._jeux = list(jeux)
        self._noms = {g.id: nom_court(g.name) for g in self._jeux}
        self.captures = galerie.lister(self._jeux)
        self._vignettes: list[_Vignette] = []
        self._mois: list[tuple[QWidget, list[_Vignette]]] = []
        self._filtres: dict[str, QPushButton] = {}
        self.choisie: galerie.Capture | None = None
        self._apercu_image: QImage | None = None

        racine = QHBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(0)
        racine.addWidget(zone_defilable(self._contenu()), stretch=1)
        racine.addWidget(self._cote())

        # Décodées sur un fil à part, les plus récentes d'abord, posées ici au
        # fil de l'eau : chaque PNG de 10 Mo coûtait 155 ms au fil de
        # l'interface (Ludo, 2026-10-14 : « ça met déjà du temps à charger avec
        # 6 images »). Le cache des vignettes rend les ouvertures suivantes
        # quasi immédiates.
        self._fil = ThreadPoolExecutor(max_workers=1, thread_name_prefix="galerie")
        self._attendues = [(v, self._fil.submit(_vignette, v.capture.chemin))
                           for v in self._vignettes]
        self._chargeur = QTimer(self)
        self._chargeur.setInterval(30)
        self._chargeur.timeout.connect(self._poser_pretes)
        self._fil_apercu: ThreadPoolExecutor | None = None
        self._apercu_attendu = None
        self._attente_apercu = QTimer(self)
        self._attente_apercu.setInterval(30)
        self._attente_apercu.timeout.connect(self._apercu_pret)
        if self._attendues:
            self._chargeur.start()
        else:
            self._fil.shutdown(wait=False)
        self.filtrer(jeu if jeu in self._filtres else "")
        if self.choisie is None:
            self._montrer(None)

    # ── Construction ──

    def _contenu(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(40, 22, 40, 28)
        lay.setSpacing(0)

        retour = QPushButton(tr("Bibliothèque"))
        retour.setObjectName("retour")
        retour.setFont(police(13))
        retour.setIcon(QIcon(pixmap_icone("retour", 16, QColor("#a9a7c4"))))
        retour.setIconSize(QSize(16, 16))
        retour.setCursor(Qt.CursorShape.PointingHandCursor)
        retour.setAutoDefault(False)
        retour.clicked.connect(self.accept)
        lay.addWidget(retour, alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addSpacing(16)
        lay.addWidget(surtitre(tr("Vos captures")))
        lay.addSpacing(4)
        titre = QLabel(tr("Galerie"))
        titre.setFont(cinzel_decorative(22))
        titre.setStyleSheet("color: #f4f2f8; background: transparent;")
        lay.addWidget(titre)
        lay.addSpacing(16)

        compte = galerie.compte_par_jeu(self.captures)
        filtres = QWidget()
        flux = FlowLayout(filtres, spacing=8)
        flux.setContentsMargins(0, 0, 0, 0)
        self._groupe_filtres = QButtonGroup(self)
        self._groupe_filtres.setExclusive(True)
        for cle, nom, n in (("", tr("Tous"), len(self.captures)),
                            *((g.id, self._noms[g.id], compte.get(g.id, 0)) for g in self._jeux)):
            filtre = QPushButton(f"{nom}  {n}")
            filtre.setObjectName("filtre")
            filtre.setProperty("vide", n == 0)
            filtre.setCheckable(True)
            filtre.setAutoDefault(False)
            filtre.setFont(police(13))
            filtre.setCursor(Qt.CursorShape.PointingHandCursor)
            filtre.clicked.connect(lambda _c=False, c=cle: self.filtrer(c))
            self._groupe_filtres.addButton(filtre)
            self._filtres[cle] = filtre
            flux.addWidget(filtre)
        lay.addWidget(filtres)
        lay.addSpacing(20)

        self._groupe = QButtonGroup(self)
        self._groupe.setExclusive(True)
        for (annee, numero), liste in galerie.par_mois(self.captures):
            bloc = QWidget()
            v = QVBoxLayout(bloc)
            v.setContentsMargins(0, 0, 0, 18)
            v.setSpacing(10)
            entete = QLabel(mois(annee, numero))
            entete.setFont(cinzel(9, bold=True))
            entete.setStyleSheet(f"color: {ENCRE_DOUCE}; background: transparent;")
            v.addWidget(entete)
            grille = QWidget()
            flux_mois = FlowLayout(grille, spacing=10)
            flux_mois.setContentsMargins(0, 0, 0, 0)
            vignettes = []
            for capture in liste:
                vignette = _Vignette(capture, self._noms.get(capture.jeu, capture.jeu))
                vignette.toggled.connect(lambda oui, c=capture: oui and self._montrer(c))
                self._groupe.addButton(vignette)
                flux_mois.addWidget(vignette)
                vignettes.append(vignette)
            self._vignettes += vignettes
            v.addWidget(grille)
            lay.addWidget(bloc)
            self._mois.append((bloc, vignettes))

        if not self.captures:
            lay.addWidget(texte(tr("Pas encore de capture. Elles apparaîtront ici dès la "
                                   "première."), 16, "#c9c7da", retour=True))
            lay.addSpacing(18)

        lay.addStretch()
        note = QFrame()
        note.setObjectName("note")
        n = QVBoxLayout(note)
        n.setContentsMargins(16, 12, 16, 12)
        n.setSpacing(6)
        n.addWidget(texte(tr("F12 en jeu, de La Coupe de Feu aux Reliques de la Mort. Rangées "
                             "dans Images › Accio Launcher, jamais effacées avec un jeu."),
                          13, "#c4c2da", retour=True))
        n.addWidget(texte(tr("Les trois premiers jeux ne savent pas encore prendre de capture : "
                             "F12 n'y fait rien pour l'instant. C'est connu, inutile de le "
                             "signaler."), 13, ENCRE_DOUCE, retour=True))
        lay.addWidget(note)
        return page

    def _cote(self) -> QFrame:
        cote = QFrame()
        cote.setObjectName("cote")
        cote.setFixedWidth(_LARGEUR_COTE)
        self._cote_cadre = cote
        lay = QVBoxLayout(cote)
        lay.setContentsMargins(24, 28, 24, 22)
        lay.setSpacing(0)

        self._apercu = QLabel()
        self._apercu.setFixedSize(_APERCU_LARGEUR, _APERCU_LARGEUR * 9 // 16)
        self._apercu.setStyleSheet("background: #16172c; border-radius: 8px;")
        self._apercu.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._apercu)
        lay.addSpacing(14)
        self._titre_jeu = QLabel("")
        self._titre_jeu.setTextFormat(Qt.TextFormat.PlainText)
        self._titre_jeu.setWordWrap(True)
        self._titre_jeu.setFont(cinzel(12, bold=True))
        self._titre_jeu.setStyleSheet(f"color: {ENCRE}; background: transparent;")
        lay.addWidget(self._titre_jeu)
        lay.addSpacing(4)
        self._details = texte("", 13, ENCRE_DOUCE, retour=True)
        lay.addWidget(self._details)
        lay.addSpacing(18)

        self._partager = bouton(tr("Partager sur Discord"), principal=True)
        self._partager.setAutoDefault(False)
        self._partager.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._partager.clicked.connect(self.partager)
        lay.addWidget(self._partager)
        lay.addSpacing(8)
        self._confirmation = texte("", 13, "#7be0a4", retour=True)
        self._confirmation.hide()
        lay.addWidget(self._confirmation)
        lay.addSpacing(8)
        # L'image en grand, dans la visionneuse du système : il manquait un
        # moyen de la REGARDER autrement qu'en vignette (Ludo, 2026-10-14).
        self._ouvrir = bouton(tr("Ouvrir l'image"))
        self._ouvrir.setAutoDefault(False)
        self._ouvrir.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._ouvrir.clicked.connect(self.ouvrir_image)
        lay.addWidget(self._ouvrir)
        lay.addSpacing(8)
        ligne = QHBoxLayout()
        ligne.setSpacing(8)
        self._copier = bouton(tr("Copier l'image"))
        self._copier.setAutoDefault(False)
        self._copier.clicked.connect(self.copier)
        ligne.addWidget(self._copier)
        self._dossier = bouton(tr("Ouvrir le dossier"))
        self._dossier.setAutoDefault(False)
        self._dossier.clicked.connect(self._ouvrir_dossier)
        ligne.addWidget(self._dossier)
        lay.addLayout(ligne)

        lay.addStretch()
        lay.addSpacing(18)
        vitrine = QFrame()
        vitrine.setObjectName("vitrine")
        v = QVBoxLayout(vitrine)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(6)
        v.addWidget(surtitre(tr("Vitrine")))
        v.addWidget(texte(tr("Les plus belles images partagées sur le Discord pourront être "
                             "choisies pour le site acciolauncher.be et pour présenter le "
                             "launcher, avec votre pseudo en crédit."), 13, "#c4c2da", retour=True))
        lay.addWidget(vitrine)
        return cote

    # ── Chargement des vignettes ──

    def _poser_pretes(self) -> None:
        restantes = []
        for vignette, futur in self._attendues:
            if not futur.done():
                restantes.append((vignette, futur))
            elif not futur.cancelled() and futur.exception() is None:
                vignette.poser(futur.result())
            elif not futur.cancelled():
                log.warning("Galerie : vignette de %s impossible", vignette.capture.chemin,
                            exc_info=futur.exception())
        self._attendues = restantes
        if not restantes:
            self._chargeur.stop()
            self._fil.shutdown(wait=False)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._adapter()

    def _adapter(self) -> None:
        """La colonne de droite, l'aperçu et les vignettes suivent la largeur."""
        cote = max(_LARGEUR_COTE, min(_LARGEUR_COTE_MAX, self.width() * 24 // 100))
        if cote != self._cote_cadre.width():
            self._cote_cadre.setFixedWidth(cote)
            apercu = cote - 2 * 24
            self._apercu.setFixedSize(apercu, apercu * 9 // 16)
            if self._apercu_image is not None:
                self._poser_apercu(self._apercu_image)
        # Marges de la page (2 × 40) et place d'une barre de défilement.
        place = self.width() - cote - 2 * 40 - 14
        # Assez de colonnes pour ne pas dépasser `_VIGNETTE_MAX`, pas plus.
        colonnes = max(1, -(-(place + 10) // (_VIGNETTE_MAX + 10)))
        largeur = max(_VIGNETTE.width(),
                      min(_VIGNETTE_MAX, (place - (colonnes - 1) * 10) // colonnes))
        taille = QSize(largeur, largeur * 9 // 16)
        for vignette in self._vignettes:
            if vignette.size() != taille:
                vignette.setFixedSize(taille)
                vignette.recadrer()

    def _poser_apercu(self, image: QImage) -> None:
        self._apercu_image = image
        pix = _recadree(image, self._apercu.size() * self.devicePixelRatioF())
        pix.setDevicePixelRatio(self.devicePixelRatioF())
        self._apercu.setPixmap(pix)

    def _apercu_pret(self) -> None:
        if self._apercu_attendu is None:
            self._attente_apercu.stop()
            return
        capture, futur = self._apercu_attendu
        if not futur.done():
            return
        self._attente_apercu.stop()
        self._apercu_attendu = None
        # Un autre choix a pu passer entre-temps : on ne pose que le bon.
        if capture == self.choisie and not futur.cancelled() and futur.exception() is None:
            self._poser_apercu(futur.result())

    def done(self, resultat: int) -> None:
        """La page se ferme : plus rien à décoder pour elle."""
        self._chargeur.stop()
        self._attente_apercu.stop()
        self._fil.shutdown(wait=False, cancel_futures=True)
        if self._fil_apercu is not None:
            self._fil_apercu.shutdown(wait=False, cancel_futures=True)
        super().done(resultat)

    # ── Filtre et choix ──

    def filtrer(self, jeu: str) -> None:
        """Ne garde que les captures de `jeu` ("" : toutes)."""
        self._filtres[jeu if jeu in self._filtres else ""].setChecked(True)
        for bloc, vignettes in self._mois:
            visibles = 0
            for vignette in vignettes:
                garder = not jeu or vignette.capture.jeu == jeu
                vignette.setVisible(garder)
                visibles += garder
            bloc.setVisible(visibles > 0)
        visible = self.choisie_visible()
        if visible is not None and visible != self.choisie:
            next(v for v in self._vignettes if v.capture == visible).setChecked(True)

    def choisie_visible(self) -> galerie.Capture | None:
        """La capture choisie si elle est visible, sinon la première visible."""
        visibles = [v.capture for v in self._vignettes if not v.isHidden()]
        if self.choisie in visibles:
            return self.choisie
        return visibles[0] if visibles else None

    def _montrer(self, capture: galerie.Capture | None) -> None:
        self.choisie = capture
        self._confirmation.hide()
        for b in (self._partager, self._ouvrir, self._copier, self._dossier):
            b.setEnabled(capture is not None)
        if capture is None:
            self._apercu.clear()
            self._titre_jeu.setText("")
            self._details.setText("")
            return
        # La vignette en cache tout de suite, la capture en grand dès qu'elle
        # est décodée (155 ms pour un PNG de 10 Mo, hors du fil de l'interface).
        cache = galerie.chemin_vignette(capture.chemin)
        if cache is not None and cache.is_file():
            self._poser_apercu(QImage(str(cache)))
        else:
            self._apercu.clear()
        if self._fil_apercu is None:
            self._fil_apercu = ThreadPoolExecutor(max_workers=1, thread_name_prefix="apercu")
        self._apercu_attendu = (capture, self._fil_apercu.submit(
            _lire, capture.chemin, self._apercu.width() * 2))
        self._attente_apercu.start()
        lecteur = QImageReader(str(capture.chemin))
        taille = lecteur.size()
        nom = next((g.name for g in self._jeux if g.id == capture.jeu), capture.jeu)
        self._titre_jeu.setText(nom)
        details = quand(capture)
        if taille.isValid():
            details += f" · {taille.width()} × {taille.height()}"
        self._details.setText(details)

    # ── Actions ──

    def copier(self) -> bool:
        """L'image dans le presse-papiers ; True si elle y est vraiment (règle 108)."""
        if self.choisie is None:
            return False
        image = QImage(str(self.choisie.chemin))
        presse = QGuiApplication.clipboard()
        if image.isNull() or presse is None:
            self._dire(tr("Cette image ne se lit pas : ouvrez le dossier pour la copier."), False)
            return False
        presse.setImage(image)
        if presse.image().isNull():
            self._dire(tr("La copie n'a pas pris : ouvrez le dossier pour la copier."), False)
            return False
        self._dire(tr("Image copiée."), True)
        return True

    def partager(self) -> None:
        """Copie, puis ouvre le salon des captures : c'est le joueur qui colle l'image."""
        if self.copier():
            self._dire(tr("Image copiée, le salon #accio-medias s'ouvre : collez-la avec Ctrl+V. "
                          "Pas encore sur le serveur ? Le bouton Discord en haut de la fenêtre "
                          "vous y invite."), True)
            open_url(DISCORD_MEDIAS_URL)

    def _dire(self, phrase: str, reussi: bool) -> None:
        self._confirmation.setText(phrase)
        self._confirmation.setStyleSheet(
            f"color: {'#7be0a4' if reussi else '#f0b46a'}; background: transparent;")
        self._confirmation.show()

    def ouvrir_image(self) -> None:
        if self.choisie is not None:
            open_local_path(str(self.choisie.chemin))

    def _ouvrir_dossier(self) -> None:
        if self.choisie is not None:
            open_local_path(str(self.choisie.chemin.parent))
