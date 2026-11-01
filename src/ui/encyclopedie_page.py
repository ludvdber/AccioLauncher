"""Les rubriques Personnages et Bestiaire des Collections.

Option 1 retenue par Ludo le 2026-10-26 : des fiches de texte d'abord (nom,
rôle ou lieu, description), une image seulement quand le jeu en a une propre,
un emblème sinon (`core/encyclopedie.py` dit lesquelles). Le choix du jeu est
celui de la page, en haut, commun à toutes les rubriques.

Les images se lisent dans la copie du joueur : une texture de 256 couleurs ou
une carte de HP4 se décode en quelques dizaines de millisecondes, d'où un fil
à part et un minuteur qui les pose au fil de l'eau, comme la Galerie. Le fil
ne rend que des octets B V R A : la QImage se fait ici, dans le fil de
l'interface.

Les fiches de HP1 et HP2 ont aussi leur modèle 3D (`maillages_ue1`) : la fiche
choisie s'affiche dans une colonne FIXE à droite, dans une visionneuse qu'on
fait tourner (`modele_3d`), et une fiche sans image reçoit le rendu de son
modèle en vignette, une par tour de minuteur pour ne pas figer la page. En
haut de la liste jusqu'au 2026-10-27 : il fallait descendre choisir une fiche
puis remonter la voir (Ludo, comme le Folio Universitas).

Les fiches s'ouvrent avec l'histoire, comme la musique (Ludo, 2026-10-27) :
une fiche fermée garde sa place, sans nom ni image ni modèle, avec le
pourcentage qui l'ouvre ; à 75 % tout le jeu est ouvert.
"""

from concurrent.futures import Future, ThreadPoolExecutor

from PyQt6.QtCore import QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.core import discographie, encyclopedie, maillages_ue1, mouvements
from src.core.i18n import dans_la_langue, get_language, tr
from src.ui.composants import ENCRE, ENCRE_DOUCE, bouton, police, texte
from src.ui.flow_layout import FlowLayout
from src.ui.fonts import cinzel
from src.ui.icon_button import pixmap_icone
from src.ui.modele_3d import Modele3D, mouvement_de_repos
from src.ui.theme import accent_qcolor, current as current_theme, themed
from src.ui.utils import clear_layout, liste_deroulante, zone_defilable

_LARGEUR_FICHE = 400
_IMAGE = QSize(96, 120)          # une carte de HP4 est deux fois plus haute que large
_ICONE = {encyclopedie.PERSONNAGES: "personnages", encyclopedie.BESTIAIRE: "patte"}
_SCENE_MIN = QSize(320, 320)
_MARGE_SCENE = 32
# Avec une visionneuse, la liste tient sur UNE colonne à gauche et le modèle
# prend toute la place qui reste (Ludo, 2026-10-27 : « plus agréable pour
# zoomer et apprécier le modèle »).
_LARGEUR_LISTE = _LARGEUR_FICHE + 80 + 8
# Les modèles de HP5-HP6 se lisent d'abord avec des textures de 128 pixels
# (vignettes, premier affichage), puis en pleine taille pour la fiche choisie
# seulement (Ludo, 2026-10-31 : passer à HP6 était « ultra lent »).
_COTE_VIGNETTE = 128

ModeleLu = tuple[maillages_ue1.Maillage, dict[str, QImage], maillages_ue1.Animation | None]

# La liste des mouvements sous le modèle : la même que les listes des réglages,
# en plus discret (fond bleu nuit, filet clair, or au survol).
_LISTE_STYLE = (
    "QComboBox { background: #15152a; color: #e4e2ef; border: 1px solid rgba(255,255,255,0.13);"
    " border-radius: 6px; padding: 3px 10px; min-height: 22px; }"
    "QComboBox:hover { border-color: rgba(214,167,44,0.55); }"
    "QComboBox[focusClavier=\"true\"]:focus { border: 2px solid #d6a72c; padding: 2px 9px; }"
    "QComboBox::drop-down { border: none; width: 18px; }"
    "QComboBox QAbstractItemView { background: #15152a; color: #e4e2ef; outline: none;"
    " selection-background-color: rgba(214, 167, 44, 0.30); selection-color: #f0d060; }"
)


def _images(textures: dict[str, encyclopedie.ImageBgra]) -> dict[str, QImage]:
    return {nom: QImage(px, w, h, 4 * w, QImage.Format.Format_ARGB32).copy()
            for nom, (w, h, px) in textures.items()}


def embleme(rubrique: str, taille: QSize, dpr: float, icone_nom: str = "") -> QPixmap:
    """Le cercle doré et le pictogramme de la rubrique (ou `icone_nom`), pour
    une fiche sans image."""
    pix = QPixmap(round(taille.width() * dpr), round(taille.height() * dpr))
    pix.setDevicePixelRatio(dpr)
    pix.fill(Qt.GlobalColor.transparent)
    cote = min(taille.width(), taille.height()) - 16
    cercle = QRectF((taille.width() - cote) / 2, (taille.height() - cote) / 2, cote, cote)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(accent_qcolor(110), 1.5))
    p.setBrush(accent_qcolor(18))
    p.drawEllipse(cercle)
    icone = round(cote * 0.45)
    p.drawPixmap(round(cercle.center().x() - icone / 2), round(cercle.center().y() - icone / 2),
                 pixmap_icone(icone_nom or _ICONE[rubrique], icone, accent_qcolor(200)))
    p.end()
    return pix


def _texte_seuil(seuil: int) -> str:
    if seuil >= discographie.TOUT_A:
        return tr("S'ouvre à {} % de l'histoire").format(discographie.TOUT_A)
    return tr("S'ouvre vers {} % de l'histoire").format(seuil)


class _Fiche(QFrame):
    """Une fiche : l'image (ou l'emblème) à gauche, le texte à droite. Avec un
    modèle 3D, un clic la montre en grand."""

    choisie = pyqtSignal(object)

    def __init__(self, rubrique: str, fiche: encyclopedie.Fiche, ouverte: bool = True) -> None:
        super().__init__()
        self.setObjectName("carteJeu")      # le cadre des cartes de la page (`mediatheque_page._STYLE`)
        self.fiche = fiche
        self.ouverte = ouverte
        self.setProperty("modele", ouverte and fiche.modele is not None)
        # Une fiche qui se choisit au clic se choisit aussi au clavier et à la
        # manette (règles 15 et 119) : 26 fiches et aucun widget focalisable
        # dans la vue, ni choix ni défilement possibles sans souris (audit du
        # 2026-10-29). L'anneau est dessiné par `mediatheque_page._STYLE`.
        if self.property("modele"):
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedWidth(_LARGEUR_FICHE)
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 14, 16, 14)
        h.setSpacing(14)
        self._image = QLabel()
        self._image.setFixedSize(_IMAGE)
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image.setStyleSheet("background: transparent;")
        self._image.setPixmap(embleme(rubrique, _IMAGE, self.devicePixelRatioF(),
                                      "" if ouverte else "cadenas"))
        h.addWidget(self._image, alignment=Qt.AlignmentFlag.AlignTop)
        v = QVBoxLayout()
        v.setSpacing(3)
        if not ouverte:
            nom = texte(tr("À découvrir"), 15, ENCRE_DOUCE, retour=True)
            nom.setFont(cinzel(12, bold=True))
            v.addWidget(nom)
            v.addWidget(texte(_texte_seuil(fiche.seuil), 12, ENCRE_DOUCE, retour=True))
            v.addStretch()
            h.addLayout(v, stretch=1)
            self.setAccessibleName(tr("À découvrir"))
            return
        nom = texte(dans_la_langue(fiche.nom), 15, ENCRE, retour=True)
        nom.setFont(cinzel(12, bold=True))
        v.addWidget(nom)
        v.addWidget(texte(dans_la_langue(fiche.sous_titre), 12, current_theme().accent_light,
                          retour=True))
        v.addSpacing(4)
        v.addWidget(texte(dans_la_langue(fiche.texte), 13, "#c9c7da", retour=True))
        v.addStretch()
        h.addLayout(v, stretch=1)
        self.setAccessibleName(dans_la_langue(fiche.nom))

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if self.property("modele") and event is not None and event.button() == Qt.MouseButton.LeftButton:
            self.choisie.emit(self)

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        if (self.property("modele") and event is not None
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space)):
            self.choisie.emit(self)
            return
        super().keyPressEvent(event)

    def marquer(self, choisie: bool) -> None:
        self.setProperty("choisie", choisie)
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)

    def sizeHint(self) -> QSize:
        # La hauteur du texte REPLIÉ à la largeur de la fiche : le `FlowLayout`
        # prend la taille souhaitée telle quelle, et celle d'un QLabel qui se
        # replie compte une seule ligne (descriptions coupées, rendu du 2026-10-26).
        lay = self.layout()
        hauteur = lay.heightForWidth(_LARGEUR_FICHE) if lay is not None else -1
        return QSize(_LARGEUR_FICHE, max(hauteur, super().sizeHint().height()))

    def poser(self, image: encyclopedie.ImageBgra) -> None:
        largeur, hauteur, pixels = image
        self.poser_image(QImage(pixels, largeur, hauteur, largeur * 4, QImage.Format.Format_ARGB32))
        self.a_une_image = True

    def poser_image(self, brute: QImage) -> None:
        dpr = self.devicePixelRatioF()
        pix = QPixmap.fromImage(brute.scaled(
            round(_IMAGE.width() * dpr), round(_IMAGE.height() * dpr),
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        pix.setDevicePixelRatio(dpr)
        self._image.setPixmap(pix)

    a_une_image = False
    a_une_vignette = False      # le rendu de son modèle, faute d'image


class _Scene(QFrame):
    """La fiche choisie en grand, dans toute la place à droite de la liste :
    son modèle qu'on fait tourner, son texte dessous."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("sceneFiche")
        self.setStyleSheet(themed(
            "QFrame#sceneFiche { background: transparent; border: none;"
            " border-left: 1px solid rgba(214, 167, 44, 0.16); }"))
        v = QVBoxLayout(self)
        v.setContentsMargins(_MARGE_SCENE, 22, _MARGE_SCENE, 24)
        v.setSpacing(6)
        self.modele = Modele3D()
        self.modele.setMinimumSize(_SCENE_MIN)
        v.addWidget(self.modele, stretch=1)
        # Les mouvements du jeu : la liste et le bouton qui les lance ou les arrête
        # (Ludo, 2026-10-27 : « un bouton pour animer les modèles »).
        self._commandes = QWidget()
        self._commandes.setObjectName("transparent")
        rang = QHBoxLayout(self._commandes)
        rang.setContentsMargins(0, 6, 0, 0)
        rang.setSpacing(10)
        self.mouvements = liste_deroulante()
        self.mouvements.setFont(police(13))
        self.mouvements.setStyleSheet(themed(_LISTE_STYLE))
        self.mouvements.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mouvements.setToolTip(tr("Un mouvement du jeu ; au survol d'une ligne, son nom dans les fichiers"))
        self.mouvements.currentIndexChanged.connect(self._mouvement_choisi)
        self.bouton_animer = bouton(tr("Animer"))
        self.bouton_animer.clicked.connect(self.basculer_animation)
        rang.addWidget(self.mouvements, stretch=1)
        rang.addWidget(self.bouton_animer)
        self._commandes.hide()
        v.addWidget(self._commandes)
        v.addSpacing(8)
        self._nom = texte("", 18, ENCRE, retour=True)
        self._nom.setFont(cinzel(17, bold=True))
        self._sous_titre = texte("", 13, current_theme().accent_light, retour=True)
        self._texte = texte("", 14, "#c9c7da", retour=True)
        v.addWidget(self._nom)
        v.addWidget(self._sous_titre)
        v.addSpacing(6)
        v.addWidget(self._texte)
        v.addSpacing(14)
        v.addWidget(texte(tr("Glisser pour tourner · molette pour zoomer · double-clic pour revenir"),
                          12, ENCRE_DOUCE, retour=True))

    def montrer(self, fiche: encyclopedie.Fiche, modele: ModeleLu | None, garder_vue: bool = False) -> None:
        self._nom.setText(dans_la_langue(fiche.nom))
        self._sous_titre.setText(dans_la_langue(fiche.sous_titre))
        self._texte.setText(dans_la_langue(fiche.texte))
        if modele is None:
            self.modele.poser(None)
        else:
            self.modele.poser(*modele, garder_vue=garder_vue)
        # Le nom du jeu (« TalkLeft2 ») reste la donnée ; la ligne montre sa
        # traduction (`core/mouvements.py`) et, au survol, le nom d'origine.
        langue = get_language()
        self.mouvements.blockSignals(True)
        self.mouvements.clear()
        for nom in self.modele.mouvements():
            libelle = mouvements.libelle(nom, langue)
            if libelle is not None:
                self.mouvements.addItem(libelle, nom)
                self.mouvements.setItemData(self.mouvements.count() - 1, nom, Qt.ItemDataRole.ToolTipRole)
        if modele is not None and modele[2] is not None:
            repos = mouvement_de_repos(modele[2])
            if repos is not None and self.mouvements.findData(repos) >= 0:
                self.mouvements.setCurrentIndex(self.mouvements.findData(repos))
        self.mouvements.blockSignals(False)
        self.bouton_animer.setText(tr("Animer"))
        self._commandes.setVisible(self.mouvements.count() > 0)

    def basculer_animation(self) -> None:
        """Lance le mouvement choisi, ou rend la pose de référence."""
        if self.modele.mouvement is not None:
            self.modele.animer(None)
            self.bouton_animer.setText(tr("Animer"))
        elif self.modele.animer(self.mouvements.currentData()):
            self.bouton_animer.setText(tr("Figer"))

    def _mouvement_choisi(self, _index: int) -> None:
        nom = self.mouvements.currentData()
        if self.modele.mouvement is not None and nom:
            self.modele.animer(nom)


class VueEncyclopedie(QWidget):
    """Les fiches d'une rubrique pour le jeu choisi en haut de la page."""

    def __init__(self, media, rubrique: str) -> None:
        super().__init__()
        self.setObjectName("transparent")
        self._media = media
        self.rubrique = rubrique
        self._jeu = ""
        self.fiches: list[_Fiche] = []
        page = QWidget()
        page.setObjectName("transparent")
        self._lay = QVBoxLayout(page)
        self._lay.setContentsMargins(40, 22, 40, 28)
        self._lay.setSpacing(14)
        # La liste défile à gauche, la fiche choisie reste à droite.
        self._racine = QHBoxLayout(self)
        self._racine.setContentsMargins(0, 0, 0, 0)
        self._racine.setSpacing(0)
        self._liste = zone_defilable(page)
        self._racine.addWidget(self._liste, stretch=1)
        self._fil = ThreadPoolExecutor(max_workers=1, thread_name_prefix="encyclopedie")
        # La fiche choisie en pleine taille : un fil à elle, sinon elle attendrait
        # derrière toutes les vignettes.
        self._fil_choix = ThreadPoolExecutor(max_workers=1, thread_name_prefix="encyclopedie-choix")
        self._complete: tuple[_Fiche, Future] | None = None
        # La pleine taille de la SEULE fiche montrée : un modèle de HP6 en 512
        # pèse ~8 Mo de textures, et les garder toutes s'additionnait au fil des clics.
        self._grand: tuple[str, ModeleLu] | None = None
        self._dossier = None
        self._attendues: list[tuple[_Fiche, Future]] = []
        self._modeles_attendus: list[tuple[_Fiche, Future]] = []
        self._modeles: dict[str, ModeleLu] = {}
        self._vignettes: list[_Fiche] = []
        self._choisie: _Fiche | None = None
        self.scene: _Scene | None = None
        # Rend les vignettes des fiches sans image ; jamais montré.
        self._peintre = Modele3D()
        self._chargeur = QTimer(self)
        self._chargeur.setInterval(30)
        self._chargeur.timeout.connect(self._poser_pretes)

    def montrer(self, jeu: str) -> None:
        if jeu == self._jeu and self.fiches:
            return
        self._jeu = jeu
        for _fiche, futur in self._attendues + self._modeles_attendus:
            futur.cancel()
        if self._complete is not None:
            self._complete[1].cancel()
        self._complete, self._grand = None, None
        self._attendues, self._modeles_attendus, self._vignettes = [], [], []
        self._modeles = {}
        self._choisie = None
        if self.scene is not None:
            self.scene.modele.poser(None)
            self.scene.hide()
            self.scene.deleteLater()
        self.scene = None
        self._liste_etroite(False)
        self.fiches = []
        clear_layout(self._lay)
        fiches = encyclopedie.fiches(self.rubrique, jeu)
        if not fiches:
            self._lay.addWidget(texte(tr("Aucune fiche pour ce jeu."), 14, ENCRE_DOUCE))
            self._lay.addStretch()
            return
        compte = (tr("{} personnage") if len(fiches) == 1 else tr("{} personnages")) \
            if self.rubrique == encyclopedie.PERSONNAGES else \
            (tr("{} créature") if len(fiches) == 1 else tr("{} créatures"))
        dossier = self._dossier = self._media.dossier_exe(jeu)
        if dossier is not None and any(f.modele is not None and self._media.ouvert(jeu, f.seuil)
                                       for f in fiches):
            self.scene = _Scene()
            self.scene.hide()               # jusqu'au premier modèle lu
            self._racine.addWidget(self.scene, stretch=1)
        self._lay.addWidget(texte(compte.format(len(fiches)), 13, ENCRE_DOUCE))
        flux = FlowLayout(spacing=14)
        for fiche in fiches:
            vue = _Fiche(self.rubrique, fiche, self._media.ouvert(jeu, fiche.seuil))
            vue.choisie.connect(self.choisir)
            flux.addWidget(vue)
            self.fiches.append(vue)
            if dossier is None or not vue.ouverte:
                continue
            if fiche.image is not None:
                self._attendues.append((vue, self._fil.submit(encyclopedie.image, dossier, fiche)))
            if fiche.modele is not None:
                self._modeles_attendus.append(
                    (vue, self._fil.submit(maillages_ue1.de_la_fiche, dossier, fiche, _COTE_VIGNETTE)))
        self._lay.addLayout(flux)
        self._lay.addStretch()
        if self._attendues or self._modeles_attendus:
            self._chargeur.start()

    def _liste_etroite(self, oui: bool) -> None:
        """Une colonne quand la visionneuse est là, toute la largeur sinon."""
        if oui:
            self._liste.setFixedWidth(_LARGEUR_LISTE)
        else:
            self._liste.setMinimumWidth(0)
            self._liste.setMaximumWidth(16777215)

    def choisir(self, vue: _Fiche) -> None:
        """Montre la fiche en grand, avec son modèle s'il est déjà lu."""
        if self.scene is None:
            return
        self._liste_etroite(True)
        if self._choisie is not None:
            self._choisie.marquer(False)
        self._choisie = vue
        vue.marquer(True)
        self.scene.montrer(vue.fiche, self._modele_montre(vue))
        self.scene.show()
        self._completer(vue)

    def _modele_montre(self, vue: _Fiche) -> ModeleLu | None:
        if self._grand is not None and self._grand[0] == vue.fiche.cle:
            return self._grand[1]
        return self._modeles.get(vue.fiche.cle)

    def _completer(self, vue: _Fiche) -> None:
        """Relit en pleine taille le modèle de HP5-HP6 de la fiche choisie."""
        modele = vue.fiche.modele
        if (modele is None or not modele.fichier.lower().endswith(".big") or self._dossier is None
                or (self._grand is not None and self._grand[0] == vue.fiche.cle)):
            return
        if self._complete is not None:
            if self._complete[0] is vue:
                return
            self._complete[1].cancel()
        self._complete = (vue, self._fil_choix.submit(maillages_ue1.de_la_fiche, self._dossier, vue.fiche))
        self._chargeur.start()

    def _poser_pretes(self) -> None:
        restantes = []
        for vue, futur in self._attendues:
            if not futur.done():
                restantes.append((vue, futur))
            elif not futur.cancelled() and futur.exception() is None and futur.result() is not None:
                vue.poser(futur.result())
        self._attendues = restantes
        modeles = []
        for vue, futur in self._modeles_attendus:
            if not futur.done():
                modeles.append((vue, futur))
            elif not futur.cancelled() and futur.exception() is None and futur.result() is not None:
                maillage, textures, animation = futur.result()
                self._modeles[vue.fiche.cle] = (maillage, _images(textures), animation)
                self._vignettes.append(vue)
                # La fiche choisie avant que son modèle soit lu le reçoit ; une
                # fiche déjà montrée (en grand) n'est pas remise de face.
                if self._choisie is None or (self._choisie is vue and self.scene is not None
                                             and self.scene.modele.modele is None):
                    self.choisir(vue)
        self._modeles_attendus = modeles
        if self._complete is not None and self._complete[1].done():
            vue, futur = self._complete
            self._complete = None
            if not futur.cancelled() and futur.exception() is None and futur.result() is not None:
                maillage, textures, animation = futur.result()
                self._grand = (vue.fiche.cle, (maillage, _images(textures), animation))
                if self._choisie is vue and self.scene is not None:
                    self.scene.montrer(vue.fiche, self._grand[1], garder_vue=True)
        # Une vignette par tour : une trentaine de millisecondes chacune.
        while self._vignettes:
            vue = self._vignettes.pop(0)
            if not vue.a_une_image and not vue.a_une_vignette:
                self._peintre.poser(*self._modeles[vue.fiche.cle])
                vue.poser_image(self._peintre.rendu(_IMAGE, vue.devicePixelRatioF()))
                vue.a_une_vignette = True
                break
        if not restantes and not modeles and not self._vignettes and self._complete is None:
            self._chargeur.stop()

    def fermer(self) -> None:
        """La page se ferme : plus rien à décoder."""
        self._chargeur.stop()
        self._fil.shutdown(wait=False, cancel_futures=True)
        self._fil_choix.shutdown(wait=False, cancel_futures=True)
        if self.scene is not None:
            self.scene.modele.poser(None)
