"""La Médiathèque : la musique et les cinématiques des jeux, et leur câblage.

Demandée par Ludo le 2026-10-24 : une page pour les musiques et les vidéos,
triées par jeu, un morceau comme fond sonore du launcher, un bouton qui coupe
tout « sans devoir toucher à 15 menus », les morceaux qui s'ouvrent au fil de
la partie, et une marque pour ce qui vient de s'ouvrir. Puis : un seul onglet
pour les deux (« on n'a pas assez de place ») et des raccourcis ailleurs.

Ici vit tout ce que la fenêtre aurait dû porter (plafond de `main_window`) :
- `Mediatheque` : le lecteur de fond, l'avancement lu dans les sauvegardes,
  les nouveautés, l'enregistrement d'un morceau, l'ouverture de la page ;
- `MiniLecteur` : le petit disque et le haut-parleur de la barre du bas,
  visibles de partout. Un clic sur le disque ouvre la page.

Les raccourcis : l'onglet du haut (pastille or quand quelque chose s'est
ouvert), le mini-lecteur, et le lien « Musique » de la fiche d'un jeu.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from PyQt6.QtCore import QObject, QSize, QStandardPaths, Qt, QTimer
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QWidget

from src.core import cinematiques, discographie, phonographe
from src.core.config import ASSETS_DIR, cache_pour
from src.core.i18n import get_language, tr
from src.ui.disque import Disque
from src.ui.fond_sonore import JEU, FondSonore, decouper
from src.ui.fonts import body_font
from src.ui.icon_button import pixmap_icone
from src.ui.theme import accent_qcolor, themed
from src.ui.title_bar import MEDIATHEQUE

log = logging.getLogger(__name__)

MUSIQUE = "musique"
CINEMATIQUES = "cinematiques"
_LARGEUR_TITRE_MINI = 220


@lru_cache(maxsize=1)
def _jeux_avec_medias() -> frozenset[str]:
    return frozenset(discographie.charger()) | frozenset(cinematiques.charger())


def a_des_medias(jeu: str) -> bool:
    """Ce jeu a-t-il des morceaux ou des cinématiques ? (le lien de la fiche)"""
    return jeu in _jeux_avec_medias()


def _cle_vus(jeu: str, rubrique: str) -> str:
    # Les cinématiques vues se rangent à côté des morceaux, sous leur propre clé.
    return jeu if rubrique == MUSIQUE else f"{jeu}:{CINEMATIQUES}"


class Mediatheque(QObject):
    """Le modèle de la page et de la barre du bas ; les widgets ne font que l'appeler."""

    def __init__(self, fenetre: QWidget, manager, pages, detail, barre_statut, session,
                 barre_titre) -> None:
        super().__init__(fenetre)
        self._manager = manager
        self._pages = pages
        self._barre_titre = barre_titre
        config = manager.config
        self.fond = FondSonore(config, manager.get_game_path,
                               lambda: cache_pour(config.install_path), fenetre)
        self._morceaux = discographie.charger()
        self._credits = discographie.charger_credits()
        self._cines = cinematiques.charger()
        self._avances: dict[str, int | None] = {}
        self._vus = discographie.charger_vus()
        self._presentes: dict[str, dict[str, cinematiques.Source]] = {}

        self.mini = MiniLecteur(self)
        barre_statut.addPermanentWidget(self.mini)
        # La bande-annonce qui s'entend fait taire la musique ; le son coupé de
        # la barre du bas fait taire la bande-annonce.
        detail.son_bande_annonce.connect(self.fond.bande_annonce_sonore)
        self.fond.son_coupe_change.connect(lambda _coupe: detail.apply_audio_config())
        detail.mediatheque_demandee.connect(lambda jeu: self.ouvrir(MUSIQUE, jeu))
        session.demarree.connect(lambda _nom: self.fond.suspendre(JEU))
        session.terminee.connect(self._retour_de_partie)
        QApplication.instance().aboutToQuit.connect(self.fond.arreter)
        # Lire les sauvegardes des trois premiers jeux coûtait 0,3 s au lancement
        # (mesuré le 2026-10-24) : c'est fait juste après l'ouverture de la fenêtre,
        # par un minuteur POSSÉDÉ (règle 102). Une page ouverte avant relit d'elle-même.
        self._lecture = QTimer(self)
        self._lecture.setSingleShot(True)
        self._lecture.timeout.connect(self.actualiser)
        self._lecture.start(1200)
        self.mini.actualiser()
        self.fond.demarrer()

    # ── Ouverture ──

    def ouvrir(self, rubrique: str = MUSIQUE, jeu: str = "") -> None:
        from src.ui.mediatheque_page import MediathequePage
        if self._lecture.isActive():
            self._lecture.stop()
            self.actualiser()
        self._pages.ouvrir(MediathequePage(self, rubrique, jeu), MEDIATHEQUE)

    def _retour_de_partie(self, *_args) -> None:
        """Une partie finie a pu ouvrir des morceaux : on relit, puis la musique reprend."""
        self.actualiser()
        self.fond.reprendre(JEU)

    def actualiser(self) -> None:
        """Relit l'avancement des jeux installés et pose la pastille de l'onglet."""
        for jeu in set(self._morceaux) | set(self._cines):
            game = self._manager.get_game_by_id(jeu)
            installe = game is not None and self._manager.is_installed(jeu)
            self._avances[jeu] = (discographie.avancement(jeu, game.sauvegardes)
                                  if installe else None)
            collection = self._cines.get(jeu)
            self._presentes[jeu] = (cinematiques.presentes(collection, self._manager.get_game_path(jeu),
                                                           get_language())
                                    if installe and collection is not None else {})
        self._barre_titre.set_pastille(MEDIATHEQUE, self.a_des_nouveautes())
        self.mini.actualiser()

    # ── Jeux ──

    def jeux(self, rubrique: str) -> list:
        """Les jeux installés qui ont quelque chose à montrer dans cette rubrique."""
        if rubrique == MUSIQUE:
            return [e.game for e in self._manager.get_games()
                    if e.game.id in self._morceaux and self._manager.is_installed(e.game.id)]
        return [e.game for e in self._manager.get_games() if self._presentes.get(e.game.id)]

    def jeux_tous(self) -> list[str]:
        """Les jeux qui ont de la musique OU des cinématiques, dans l'ordre du catalogue."""
        avec = {g.id for r in (MUSIQUE, CINEMATIQUES) for g in self.jeux(r)}
        return [e.game.id for e in self._manager.get_games() if e.game.id in avec]

    def nom(self, jeu: str) -> str:
        from src.ui.galerie_page import nom_court
        game = self._manager.get_game_by_id(jeu)
        return nom_court(game.name) if game is not None else jeu.upper()

    def jaquette(self, jeu: str) -> Path | None:
        game = self._manager.get_game_by_id(jeu)
        if game is None or not game.cover_image:
            return None
        chemin = ASSETS_DIR / "covers" / game.cover_image
        return chemin if chemin.is_file() else None

    def fond_volume(self) -> int:
        return self._manager.config.volume_musique

    def avance(self, jeu: str) -> int | None:
        return self._avances.get(jeu)

    def credit(self, jeu: str) -> str:
        """« Musique de Jeremy Soule · © 2001 Electronic Arts Inc. », vide sans crédit."""
        c = self._credits.get(jeu)
        if c is None:
            return ""
        return tr("Musique de {compositeur} · © {annee} {editeur}").format(
            compositeur=c.compositeur, annee=c.annee, editeur=c.editeur)

    # ── Morceaux ──

    def morceaux(self, jeu: str) -> tuple[discographie.Morceau, ...]:
        return self._morceaux.get(jeu, ())

    def ouvert(self, jeu: str, seuil: int) -> bool:
        return discographie.ouvert_au_seuil(seuil, self._avances.get(jeu))

    def _ouverts(self, jeu: str, rubrique: str) -> set[str]:
        if rubrique == MUSIQUE:
            return {m.fichier for m in self.morceaux(jeu) if self.ouvert(jeu, m.seuil)}
        presentes = self._presentes.get(jeu, {})
        return {c.fichier for c in self.cinematiques(jeu)
                if c.fichier in presentes and self.ouvert(jeu, c.seuil)}

    def nouveaux(self, jeu: str, rubrique: str) -> set[str]:
        return discographie.nouveaux(_cle_vus(jeu, rubrique), self._ouverts(jeu, rubrique), self._vus)

    def marquer_vus(self, jeu: str, rubrique: str) -> None:
        cle_vus, ouverts = _cle_vus(jeu, rubrique), self._ouverts(jeu, rubrique)
        if ouverts <= self._vus.get(cle_vus, set()):
            return
        discographie.marquer_vus(cle_vus, ouverts)
        self._vus.setdefault(cle_vus, set()).update(ouverts)
        self._barre_titre.set_pastille(MEDIATHEQUE, self.a_des_nouveautes())

    def a_des_nouveautes(self) -> bool:
        return any(discographie.nouveaux(_cle_vus(g.id, r), self._ouverts(g.id, r), self._vus)
                   for r in (MUSIQUE, CINEMATIQUES) for g in self.jeux(r))

    def enregistrer(self, cle_morceau: str) -> Path | None:
        """Copie le morceau dans Musique › Accio › HPx ; le chemin, ou None."""
        morceau = decouper(cle_morceau)
        source = self.fond.fichier(cle_morceau)
        if morceau is None or source is None:
            return None
        racine = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MusicLocation)
        if not racine:
            return None
        dossier = Path(racine) / "Accio" / morceau[0].upper()
        return phonographe.exporter(source, self.fond.titre(cle_morceau) or morceau[1], dossier)

    # ── Cinématiques ──

    def cinematiques(self, jeu: str) -> tuple[cinematiques.Cinematique, ...]:
        collection = self._cines.get(jeu)
        return collection.clips if collection is not None else ()

    def a_la_cinematique(self, jeu: str, fichier: str) -> bool:
        return fichier in self._presentes.get(jeu, {})

    def _cache(self) -> Path:
        return cache_pour(self._manager.config.install_path)

    def video(self, jeu: str, fichier: str) -> Path | None:
        """Le fichier de la vidéo, recopié depuis l'archive du jeu au premier visionnage."""
        source = self._presentes.get(jeu, {}).get(fichier)
        return cinematiques.lisible(source, self._cache(), jeu) if source is not None else None

    def voix(self, jeu: str, fichier: str) -> Path | None:
        """La voix séparée de la cinématique (HP4), dans la langue du launcher sinon en anglais."""
        collection = self._cines.get(jeu)
        if collection is None:
            return None
        source = cinematiques.voix(collection, self._manager.get_game_path(jeu), fichier, get_language())
        return cinematiques.lisible(source, self._cache(), jeu) if source is not None else None

    def sans_son(self, jeu: str) -> bool:
        collection = self._cines.get(jeu)
        return collection is not None and collection.sans_son


class MiniLecteur(QWidget):
    """Le petit disque et le titre (ouvre la page), puis le haut-parleur qui coupe tout."""

    def __init__(self, media: Mediatheque) -> None:
        super().__init__()
        self._media = media
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 10, 2)
        lay.setSpacing(6)

        self._bouton = QPushButton()
        self._bouton.setObjectName("miniLecteur")
        self._bouton.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bouton.setFixedHeight(28)
        self._bouton.setStyleSheet(themed(
            "QPushButton#miniLecteur { background: transparent; border: 1px solid rgba(255, 255, 255, 0.10);"
            " border-radius: 14px; }"
            "QPushButton#miniLecteur:hover, QPushButton#miniLecteur:focus {"
            " border-color: rgba(214, 167, 44, 0.55); }"))
        dedans = QHBoxLayout(self._bouton)
        dedans.setContentsMargins(5, 0, 12, 0)
        dedans.setSpacing(8)
        self._disque = Disque(18, reflet=False)
        self._disque.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._note = QLabel()
        self._note.setPixmap(pixmap_icone("musique", 18, QColor("#c9c7da")))
        self._note.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._titre = QLabel()
        self._titre.setTextFormat(Qt.TextFormat.PlainText)
        self._titre.setFont(body_font(10))
        self._titre.setStyleSheet("color: #d9d6e8; background: transparent;")
        self._titre.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        dedans.addWidget(self._disque)
        dedans.addWidget(self._note)
        dedans.addWidget(self._titre)
        self._bouton.clicked.connect(lambda: media.ouvrir(MUSIQUE))
        lay.addWidget(self._bouton)

        self._son = QPushButton()
        self._son.setObjectName("sonLauncher")
        self._son.setCursor(Qt.CursorShape.PointingHandCursor)
        self._son.setFixedSize(28, 28)
        self._son.setIconSize(QSize(18, 18))
        self._son.setStyleSheet(themed(
            "QPushButton#sonLauncher { background: transparent; border: 1px solid rgba(255, 255, 255, 0.10);"
            " border-radius: 14px; }"
            "QPushButton#sonLauncher[coupe=\"true\"] { background: rgba(214, 167, 44, 0.16);"
            " border-color: rgba(214, 167, 44, 0.55); }"
            "QPushButton#sonLauncher:hover, QPushButton#sonLauncher:focus {"
            " border-color: rgba(214, 167, 44, 0.55); }"))
        self._son.clicked.connect(media.fond.basculer_son)
        lay.addWidget(self._son)
        media.fond.change.connect(self.actualiser)
        media.fond.son_coupe_change.connect(lambda _c: self.actualiser())

    def actualiser(self) -> None:
        fond = self._media.fond
        morceau = decouper(fond.morceau)
        if morceau is not None:
            jeu = morceau[0]
            self._disque.poser(jeu, self._media.jaquette(jeu))
            texte = f"{fond.titre(fond.morceau)} · {jeu.upper()}"
            libelle = tr("Médiathèque, morceau : {}").format(texte)
        else:
            texte = tr("Musique")
            libelle = tr("Ouvrir la Médiathèque")
        self._disque.setVisible(morceau is not None)
        self._note.setVisible(morceau is None)
        self._disque.set_tourne(fond.en_lecture)
        metriques = self._titre.fontMetrics()
        court = metriques.elidedText(texte, Qt.TextElideMode.ElideRight, _LARGEUR_TITRE_MINI)
        self._titre.setText(court)
        self._bouton.setToolTip(texte if court != texte else "")
        self._bouton.setAccessibleName(libelle)
        coupe = fond.son_coupe
        self._son.setIcon(QIcon(pixmap_icone("muet" if coupe else "volume", 18,
                                             accent_qcolor() if coupe else QColor("#d9d6e8"))))
        texte_son = tr("Remettre le son du launcher") if coupe else tr("Couper le son du launcher")
        self._son.setToolTip(texte_son)
        self._son.setAccessibleName(texte_son)
        self._bouton.setFixedWidth(self._bouton.layout().sizeHint().width())
        self._son.setProperty("coupe", coupe)
        self._son.style().unpolish(self._son)
        self._son.style().polish(self._son)
