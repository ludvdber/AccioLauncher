"""Les rubriques Personnages et Bestiaire des Collections.

Des fiches de texte d'abord (nom,
rôle ou lieu, description), une image seulement quand le jeu en a une propre,
un emblème sinon (`core/encyclopedie.py` dit lesquelles). Le choix du jeu est
celui de la page, en haut, commun à toutes les rubriques.

Les images se lisent dans la copie du joueur, et une fiche sans image reçoit
le rendu de son modèle : ces vignettes ne se fabriquent qu'UNE fois, gardées
sur le disque et chargées au lancement (`vignettes_fiches`). La vue les pose
telles quelles à l'ouverture ; celles qui manquent encore arrivent par
`Vignettes.changees`.

Les fiches de HP1 à HP3, HP5 et HP6 ont aussi leur modèle 3D (`maillages_ue1`,
`maillages_ue2`, `maillages_fpm`) : la fiche choisie s'affiche dans une colonne
FIXE à droite, dans une visionneuse qu'on fait tourner (`modele_3d`). Seul SON
modèle est lu, sur un fil, en pleine taille (120 ms au plus pour HP5-HP6,
280 ms pour HP3 depuis le décodeur DXT du 2026-11-16) : lire les modèles de
toute la liste à chaque ouverture prenait 2 à 3 s.

Les fiches s'ouvrent avec l'histoire, comme la musique :
une fiche fermée garde sa place, sans nom ni image ni modèle, avec le
pourcentage qui l'ouvre ; à 75 % tout le jeu est ouvert.
"""

from concurrent.futures import Future, ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

from PyQt6.QtCore import QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.core import encyclopedie, maillages_ue1, mouvements
from src.core.i18n import dans_la_langue, get_language, tr, trn
from src.ui.composants import ENCRE, ENCRE_DOUCE, LISTE, icone_de_bouton, police, rond, texte, transparent
from src.ui.carte_avancement import CarteAvancement, texte_seuil
from src.ui.flow_layout import FlowLayout
from src.ui.fonts import cinzel
from src.ui.icon_button import pixmap_icone
from src.ui.modele_3d import Modele3D, mouvement_de_repos
from src.ui.theme import accent_qcolor, current as current_theme, themed
from src.ui.utils import clear_layout, liste_deroulante, zone_defilable
from src.ui.vignettes_fiches import ModeleLu, images

_LARGEUR_FICHE = 400
_IMAGE = QSize(96, 120)          # une carte de HP4 est deux fois plus haute que large
_IMAGE_COMPACTE = QSize(52, 64)  # la carte réduite, quand la visionneuse montre le texte
_ICONE = {encyclopedie.PERSONNAGES: "personnages", encyclopedie.BESTIAIRE: "patte"}
_SCENE_MIN = QSize(320, 320)
_MARGE_SCENE = 32
_LARGEUR_MOUVEMENTS = 320        # « Respirer » sur 1273 px ne disait rien de plus
_EMBLEME_VIDE = QSize(96, 96)
# Avec une visionneuse, la liste tient sur UNE colonne à gauche et le modèle
# prend toute la place qui reste (Ludo, 2026-10-27 : « plus agréable pour
# zoomer et apprécier le modèle »).
_LARGEUR_LISTE = _LARGEUR_FICHE + 80 + 8

# La liste des mouvements sous le modèle : la même que les listes des réglages
# (`composants.LISTE` : fond bleu nuit, filet clair, or au survol).
_LISTE_STYLE = LISTE


def embleme(rubrique: str, taille: QSize, dpr: float, icone_nom: str = "") -> QPixmap:
    """Le cercle doré et le pictogramme de la rubrique (ou `icone_nom`), pour
    une fiche sans image. Peint une fois par aspect : chaque fiche repeignait le même."""
    return _embleme(rubrique, taille.width(), taille.height(), dpr, icone_nom, accent_qcolor().rgb())


@lru_cache(maxsize=16)
def _embleme(rubrique: str, largeur: int, hauteur: int, dpr: float, icone_nom: str, _accent: int) -> QPixmap:
    taille = QSize(largeur, hauteur)
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


class EtatVide(QWidget):
    """Rien à montrer : le cercle doré de la rubrique et une phrase, au milieu de la
    place. Le même partout dans les Collections ; `action`, un bouton sous la phrase."""

    def __init__(self, icone: str, phrase: str = "", action: QWidget | None = None) -> None:
        super().__init__()
        self.setObjectName("transparent")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(14)
        lay.addStretch()
        image = QLabel()
        transparent(image)
        image.setPixmap(embleme("", _EMBLEME_VIDE, self.devicePixelRatioF(), icone))
        lay.addWidget(image, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._phrase = texte(phrase, 15, "#c9c7da", retour=True)
        self._phrase.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self._phrase)
        if action is not None:
            lay.addWidget(action, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch()

    def text(self) -> str:
        return self._phrase.text()

    def setText(self, phrase: str) -> None:  # noqa: N802 (comme un QLabel)
        self._phrase.setText(phrase)


class _Fiche(QFrame):
    """Une fiche : l'image (ou l'emblème) à gauche, le texte à droite. Avec un
    modèle 3D, un clic la montre en grand.

    `compacte` (la visionneuse est là) : l'image et le nom seulement. Le nom, le sous-titre et
    la description étaient posés mot pour mot dans la carte ET sous le modèle, et des cartes de
    150 px n'en laissaient voir que 5 sur 26 (audit UI col3, 2026-11-13)."""

    choisie = pyqtSignal(object)

    def __init__(self, rubrique: str, fiche: encyclopedie.Fiche, ouverte: bool = True,
                 compacte: bool = False) -> None:
        super().__init__()
        self.setObjectName("carteJeu")      # le cadre des cartes de la page (`mediatheque_page._STYLE`)
        self.fiche = fiche
        self.ouverte = ouverte
        self.setProperty("modele", ouverte and fiche.modele is not None)
        # Une fiche qui se choisit au clic se choisit aussi au clavier et à la
        # manette (règles 15 et 119) : 26 fiches et aucun widget focalisable
        # dans la vue, ni choix ni défilement possibles sans souris (audit du
        # 2026-10-29). L'anneau est celui de `focus_visible`. Toute fiche
        # ouverte prend le focus, même sans modèle : sans elle, aucune fiche de HP4 ne
        # s'atteignait, et le bas de la liste restait hors de vue au clavier (audit UI,
        # 2026-11-13) ; le focus fait défiler la zone (`focus_visible`).
        if ouverte:
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedWidth(_LARGEUR_FICHE)
        self.taille_image = _IMAGE_COMPACTE if compacte else _IMAGE
        h = QHBoxLayout(self)
        h.setContentsMargins(*((12, 8, 14, 8) if compacte else (14, 14, 16, 14)))
        h.setSpacing(14)
        self._image = QLabel()
        self._image.setFixedSize(self.taille_image)
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        transparent(self._image)
        self._image.setPixmap(embleme(rubrique, self.taille_image, self.devicePixelRatioF(),
                                      "" if ouverte else "cadenas"))
        h.addWidget(self._image, alignment=Qt.AlignmentFlag.AlignVCenter if compacte else Qt.AlignmentFlag.AlignTop)
        v = QVBoxLayout()
        v.setSpacing(3)
        if not ouverte:
            nom = texte(tr("À découvrir"), 15, ENCRE_DOUCE, retour=True)
            nom.setFont(cinzel(12, bold=True))
            v.addWidget(nom)
            v.addWidget(texte(texte_seuil(fiche.seuil), 12, ENCRE_DOUCE, retour=True))
            v.addStretch()
            h.addLayout(v, stretch=1)
            self.setAccessibleName(tr("À découvrir"))
            return
        nom = texte(dans_la_langue(fiche.nom), 15, ENCRE, retour=True)
        nom.setFont(cinzel(12, bold=True))
        v.addWidget(nom)
        if not compacte:
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

    def poser_image(self, brute: QImage) -> None:
        dpr = self.devicePixelRatioF()
        pix = QPixmap.fromImage(brute.scaled(
            round(self.taille_image.width() * dpr), round(self.taille_image.height() * dpr),
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        pix.setDevicePixelRatio(dpr)
        self._image.setPixmap(pix)
        self.a_une_vignette = True

    a_une_vignette = False      # l'image du jeu ou le rendu de son modèle, à la place de l'emblème


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
        # Les mouvements du jeu, centrés sous le modèle : un choix dans la liste le
        # lance, le rond l'arrête (Ludo, 2026-10-27 : « un bouton pour animer les modèles »).
        self._commandes = QWidget()
        self._commandes.setObjectName("transparent")
        rang = QHBoxLayout(self._commandes)
        rang.setContentsMargins(0, 6, 0, 0)
        rang.setSpacing(10)
        self.mouvements = liste_deroulante()
        self.mouvements.setMaximumWidth(_LARGEUR_MOUVEMENTS)
        self.mouvements.setFont(police(13))
        self.mouvements.setStyleSheet(themed(_LISTE_STYLE))
        self.mouvements.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mouvements.setToolTip(tr("Un mouvement du jeu ; au survol d'une ligne, son nom dans les fichiers"))
        self.mouvements.currentIndexChanged.connect(self._mouvement_choisi)
        # `activated` aussi : rechoisir « Respirer », déjà affiché, ne change pas l'index.
        self.mouvements.activated.connect(self._mouvement_choisi)
        self.bouton_animer = rond("play", tr("Animer"), self.basculer_animation)
        rang.addStretch(1)
        rang.addWidget(self.mouvements, stretch=4)
        rang.addWidget(self.bouton_animer)
        rang.addStretch(1)
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
        # L'aide ne vit que jusqu'au premier geste (constat col15) : ensuite elle
        # s'efface en gardant sa place, et le modèle ne change pas de taille.
        self.aide = texte(tr("Glisser pour tourner · molette pour zoomer · double-clic pour revenir"),
                          12, ENCRE_DOUCE, retour=True)
        politique = self.aide.sizePolicy()
        politique.setRetainSizeWhenHidden(True)
        self.aide.setSizePolicy(politique)
        v.addWidget(self.aide)
        self.modele.manipule.connect(self.aide.hide)

    def montrer(self, fiche: encyclopedie.Fiche, modele: ModeleLu | None) -> None:
        self._nom.setText(dans_la_langue(fiche.nom))
        self._sous_titre.setText(dans_la_langue(fiche.sous_titre))
        self._texte.setText(dans_la_langue(fiche.texte))
        if modele is None:
            self.modele.poser(None)
        else:
            self.modele.poser(*modele)
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
        self._suivre_animation()
        self._commandes.setVisible(self.mouvements.count() > 0)

    def basculer_animation(self) -> None:
        """Lance le mouvement choisi, ou rend la pose de référence."""
        if self.modele.mouvement is not None:
            self.modele.animer(None)
        else:
            self.modele.animer(self.mouvements.currentData())
        self._suivre_animation()

    def _mouvement_choisi(self, _index: int) -> None:
        nom = self.mouvements.currentData()
        if nom and nom != self.modele.mouvement:
            self.modele.animer(nom)
            self._suivre_animation()

    def _suivre_animation(self) -> None:
        anime = self.modele.mouvement is not None
        libelle = tr("Figer") if anime else tr("Animer")
        self.bouton_animer.setIcon(icone_de_bouton("pause" if anime else "play", 16))
        self.bouton_animer.setToolTip(libelle)
        self.bouton_animer.setAccessibleName(libelle)


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
        self._dossier: Path | None = None
        # Le modèle de la SEULE fiche montrée : un modèle de HP6 pèse ~8 Mo de textures, et
        # les garder tous s'additionnait au fil des clics.
        self._modele: tuple[str, ModeleLu] | None = None
        self._attendu: tuple[_Fiche, Future] | None = None
        # À l'ouverture, la première fiche dont le modèle se lit ouvre la visionneuse.
        self._candidates: list[_Fiche] = []
        self._vignettes_branchees = False
        self._choisie: _Fiche | None = None
        self.scene: _Scene | None = None
        self._chargeur = QTimer(self)
        self._chargeur.setInterval(15)
        self._chargeur.timeout.connect(self._poser_modele)

    def montrer(self, jeu: str) -> None:
        if jeu == self._jeu and self.fiches:
            return
        self._jeu = jeu
        self._oublier_modele()
        self._candidates = []
        self._choisie = None
        self._dossier = None
        if self.scene is not None:
            self.scene.modele.poser(None)
            self.scene.hide()
            self.scene.deleteLater()
        self.scene = None
        self._liste_etroite(False)
        self.fiches = []
        clear_layout(self._lay)
        # Un autre jeu s'ouvre en tête : il gardait la hauteur du précédent, et la fiche
        # montrée en grand (Harry) était hors de la vue (audit UI, 2026-11-13).
        self._liste.verticalScrollBar().setValue(0)
        fiches = encyclopedie.fiches(self.rubrique, jeu) if jeu else []
        if not fiches:
            if jeu:
                phrase = tr("Pas encore de fiche pour ce jeu.")
            elif self.rubrique == encyclopedie.PERSONNAGES:
                phrase = tr("Installez un jeu pour voir ses personnages ici.")
            else:
                phrase = tr("Installez un jeu pour voir ses créatures ici.")
            self._lay.addWidget(EtatVide(_ICONE[self.rubrique], phrase), stretch=1)
            return
        # Les fiches OUVERTES sur le total : « 26 personnages » comptait aussi les fermées.
        ouvertes = sum(self._media.ouvert(jeu, f.seuil) for f in fiches)
        compte = trn(ouvertes, "{n} personnage sur {total}", "{n} personnages sur {total}") \
            if self.rubrique == encyclopedie.PERSONNAGES else \
            trn(ouvertes, "{n} créature sur {total}", "{n} créatures sur {total}")
        dossier = self._dossier = self._media.dossier_exe(jeu)
        if dossier is not None and any(f.modele is not None and self._media.ouvert(jeu, f.seuil)
                                       for f in fiches):
            self.scene = _Scene()
            self.scene.hide()               # jusqu'au premier modèle lu
            self._racine.addWidget(self.scene, stretch=1)
            # Étroite tout de suite : les fiches se peignaient sur deux colonnes, puis sautaient sur
            # une à l'arrivée du premier modèle (audit UI f37).
            self._liste_etroite(True)
        carte = CarteAvancement()
        carte.poser(self._media.nom(jeu), compte.format(n=ouvertes, total=len(fiches)),
                    self._media.avance(jeu), any(f.seuil > 0 for f in fiches))
        self._lay.addWidget(carte)
        flux = FlowLayout(spacing=14)
        for fiche in fiches:
            vue = _Fiche(self.rubrique, fiche, self._media.ouvert(jeu, fiche.seuil),
                         compacte=self.scene is not None)
            vue.choisie.connect(self.choisir)
            flux.addWidget(vue)
            self.fiches.append(vue)
        self._lay.addLayout(flux)
        self._lay.addStretch()
        if self.scene is not None and self.fiches:
            # Créée avant les fiches, la visionneuse passait avant elles au clavier (f32).
            QWidget.setTabOrder(self.fiches[-1], self.scene.mouvements)
            QWidget.setTabOrder(self.scene.mouvements, self.scene.bouton_animer)
        if dossier is None:
            return
        vignettes = self._media.vignettes
        if not self._vignettes_branchees:
            self._vignettes_branchees = True
            vignettes.changees.connect(self._poser_vignettes)
        self._poser_vignettes(jeu, self.rubrique)
        vignettes.preparer(jeu, self.rubrique, d_abord=True)
        self._candidates = [v for v in self.fiches if v.property("modele")]
        self._essayer_la_suivante()

    def en_attente(self) -> bool:
        """Reste-t-il une vignette à recevoir ou le modèle montré à lire ? (banc de rapidité)"""
        return self._attendu is not None or (
            self._dossier is not None and self._media.vignettes.en_cours(self._jeu, self.rubrique))

    def _poser_vignettes(self, jeu: str, rubrique: str) -> None:
        if (jeu, rubrique) != (self._jeu, self.rubrique):
            return
        gardees = self._media.vignettes.gardees(jeu, rubrique)
        for vue in self.fiches:
            vignette = gardees.get(vue.fiche.cle) if vue.ouverte and not vue.a_une_vignette else None
            if vignette is not None:
                vue.poser_image(vignette)

    def _liste_etroite(self, oui: bool) -> None:
        """Une colonne quand la visionneuse est là, toute la largeur sinon."""
        if oui:
            self._liste.setFixedWidth(_LARGEUR_LISTE)
        else:
            self._liste.setMinimumWidth(0)
            self._liste.setMaximumWidth(16777215)

    def choisir(self, vue: _Fiche) -> None:
        """Montre la fiche en grand ; son modèle la rejoint dès qu'il est lu."""
        if self.scene is None:
            return
        self._candidates = []
        self._liste_etroite(True)
        if self._choisie is not None:
            self._choisie.marquer(False)
        self._choisie = vue
        vue.marquer(True)
        lu = self._modele[1] if self._modele is not None and self._modele[0] == vue.fiche.cle else None
        self.scene.montrer(vue.fiche, lu)
        self.scene.show()
        if lu is None and vue.fiche.modele is not None:
            self._lire_modele(vue)

    def _essayer_la_suivante(self) -> None:
        if self._candidates:
            self._lire_modele(self._candidates.pop(0))

    def _lire_modele(self, vue: _Fiche) -> None:
        self._oublier_modele()
        if self._dossier is not None:
            self._attendu = (vue, self._fil.submit(maillages_ue1.de_la_fiche, self._dossier, vue.fiche))
            self._chargeur.start()

    def _oublier_modele(self) -> None:
        if self._attendu is not None:
            self._attendu[1].cancel()
        self._attendu, self._modele = None, None
        self._chargeur.stop()

    def _poser_modele(self) -> None:
        if self._attendu is None or not self._attendu[1].done():
            return
        vue, futur = self._attendu
        self._attendu = None
        self._chargeur.stop()
        lu = futur.result() if futur.exception() is None else None
        if lu is None:
            if self._choisie is None:       # à l'ouverture : la fiche suivante qui a un modèle
                self._essayer_la_suivante()
            return
        maillage, textures, animation = lu
        self._modele = (vue.fiche.cle, (maillage, images(textures), animation))
        if self._choisie is None:
            self.choisir(vue)
        elif self._choisie is vue and self.scene is not None:
            self.scene.montrer(vue.fiche, self._modele[1])

    def fermer(self) -> None:
        """La page se ferme : plus rien à décoder."""
        self._chargeur.stop()
        self._fil.shutdown(wait=False, cancel_futures=True)
        if self._vignettes_branchees:
            self._vignettes_branchees = False
            try:
                self._media.vignettes.changees.disconnect(self._poser_vignettes)
            except TypeError:
                pass
        if self.scene is not None:
            self.scene.modele.poser(None)
