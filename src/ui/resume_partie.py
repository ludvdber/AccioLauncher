"""Où en est la partie, sur la fiche d'un jeu dont on sait lire les sauvegardes.

La description cède sa place dès qu'il y a mieux à montrer (Ludo, 2026-10-15) :
qui a déjà joué l'a lue, et veut savoir où il en était. Un jeu dont on ne lit
rien garde sa description (`folio.FICHES` : les cartes de HP1 à HP3, et
depuis le 2026-10-26 les boucliers de HP4, la découverte de HP5, les
écussons de HP6, chacun avec l'icône que le jeu lui donne).

Maquette H du canevas « fiche » : la ligne « Dernière partie » sous le titre,
puis le bouton, puis ce bloc (éventail des cartes, compte, barre, maisons et
temps de jeu). Le bloc entier ouvre le folio.
"""

from datetime import date, datetime
from html import escape
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.core import folio, folio_hp2, folio_hp3, folio_hp4, folio_hp5, folio_hp6
from src.core.formatting import format_relative_date
from src.core.i18n import get_language, tr, trn
from src.ui.fonts import body_font
from src.ui.theme import accent_qcolor, themed

# Au-delà, le bloc s'étirerait sur toute la colonne pour trois lignes courtes.
LARGEUR_MAX = 380
_CARTE_H = 34          # hauteur d'une carte de l'éventail, px logiques
_EVENTAIL = ((0, 4, -10.0), (14, 1, -1.0), (28, 3, 9.0))   # x, y, angle

_STYLE = """
QFrame#blocFolio {
    background: rgba(255, 255, 255, 0.04); border: 1px solid transparent; border-radius: 8px;
}
QFrame#blocFolio:hover { background: rgba(255, 255, 255, 0.07); }
QFrame#blocFolio[focusClavier="true"]:focus { border-color: #d6a72c; }
"""


def phrase_derniere_partie(modifie: datetime, lieu: str, today: date | None = None) -> str:
    """« Dernière partie hier · Parc de Poudlard », en RichText échappé.

    La date est celle que le JEU a écrite (la sauvegarde), pas la dernière
    session du launcher : elle va avec le lieu, et une partie lancée hors du
    launcher compte aussi. Un point plutôt que « au » : le lieu vient du jeu,
    dans sa langue, et « au Bibliothèque » se lirait mal.
    """
    today = today or date.today()
    if (today - modifie.date()).days > 30:
        # En toutes lettres et dans la langue de l'interface, comme au Folio :
        # « 20/09/2026 » imposait l'ordre français même en anglais.
        from src.ui.versions_dialog import date_longue
        debut = tr("Dernière partie le {}").format(date_longue(modifie.strftime("%Y-%m-%d")))
    else:
        debut = tr("Dernière partie {}").format(
            format_relative_date(modifie.isoformat(), today))
    texte = f'<span style="color:#b4b4d0;">{escape(debut, quote=False)}</span>'
    if lieu:
        texte += ('<span style="color:#b4b4d0;">&nbsp;·&nbsp;</span>'
                  + escape(lieu, quote=False))
    return texte


def maison_en_tete(releve: folio.Releve) -> str:
    """« Serpentard mène », « À égalité », ou rien sans points."""
    from src.ui.folio_page import nom_maison
    tete = releve.en_tete()
    if tete is None:
        return tr("À égalité") if releve.lu and any(releve.points.values()) else ""
    return tr("{} mène").format(nom_maison(tete[0]))


def phrase_cartes(trouvees: int, total: int = folio.CARTES_HP1) -> str:
    cle = "{} carte sur {}" if trouvees == 1 else "{} cartes sur {}"
    return tr(cle).format(trouvees, total)


def _nombre(n: int) -> str:
    """« 4 360 » : l'espace fine insécable des milliers, comme l'écran du jeu."""
    return f"{n:,}".replace(",", "\u202f")


# (singulier, pluriel) de la phrase du bloc, par ce qu'on compte.
_PHRASES = {
    "boucliers": ("{} bouclier sur {}", "{} boucliers sur {}"),
    "ecussons": ("{} écusson sur {}", "{} écussons sur {}"),
}


def phrase_resume(resume: folio.Resume) -> str:
    """« 9 cartes sur 25 », « 12 boucliers sur 38 », « 4 % terminé »."""
    if resume.unite == "pourcent":
        return tr("{} % terminé").format(resume.trouvees)
    formes = _PHRASES.get(resume.unite)
    if formes is None:
        return phrase_cartes(resume.trouvees, resume.total)
    cle = formes[0] if resume.trouvees == 1 else formes[1]
    return tr(cle).format(_nombre(resume.trouvees), _nombre(resume.total))


def lire_resume(game, system: Path, langue: str) -> folio.Resume | None:
    """Où en est la dernière partie d'un jeu de `folio.FICHES`, lu dans ses sauvegardes.

    Partagé par la fiche et la carte Discord (`GameSession`). Pur : se lit
    aussi hors du fil de l'interface.
    """
    from src.core import sauvegardes
    if game.id == "hp4":
        return folio_hp4.resume(sauvegardes.fichiers(game.sauvegardes), system, langue)
    if game.id == "hp5":
        return folio_hp5.resume(sauvegardes.fichiers(game.sauvegardes))
    if game.id == "hp6":
        return folio_hp6.resume(sauvegardes.fichiers(game.sauvegardes))
    if game.id == "hp2":
        # HP2 numérote ses emplacements par dossier (`Slot1/Save0.usa`).
        return folio_hp2.resume(game.sauvegardes, system, langue)
    if game.id in ("hp1", "hp3"):
        lire = folio_hp3.resume if game.id == "hp3" else folio.resume_hp1
        return lire(sauvegardes.fichiers(game.sauvegardes), system, langue)
    return None


def ligne_discord(resume: folio.Resume) -> str:
    """« Parc de Poudlard · 9 cartes sur 25 » : la partie, sur la carte Discord."""
    return " · ".join(p for p in (lieu_resume(resume), phrase_resume(resume)) if p)


def lieu_resume(resume: folio.Resume) -> str:
    """Ce qui suit « Dernière partie… » : le lieu que le jeu nomme, ou pour
    HP6 son chapitre (l'avancement de HP5 est déjà dans le bloc)."""
    if resume.lieu:
        return resume.lieu
    partie = resume.releve
    if isinstance(partie, folio_hp6.Partie) and partie.chapitre:
        return tr("Chapitre {}").format(partie.chapitre)
    return ""


class _Eventail(QWidget):
    """Trois cartes trouvées, en éventail, telles que le jeu les dessine."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(58, 42)
        self._cartes: list[QPixmap] = []

    def regler(self, cartes: list[QPixmap]) -> None:
        self._cartes = cartes[:len(_EVENTAIL)]
        self.setVisible(bool(self._cartes))
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if len(self._cartes) == 1:
            # Une icône seule (HP4 à HP6) : droite et centrée, pas penchée en carte.
            pix = self._cartes[0]
            ratio = pix.devicePixelRatio() or 1.0
            larg, haut = pix.width() / ratio, pix.height() / ratio
            p.drawPixmap(QRectF((self.width() - larg) / 2, (self.height() - haut) / 2, larg, haut),
                         pix, QRectF(pix.rect()))
            p.end()
            return
        for pix, (x, y, angle) in zip(self._cartes, _EVENTAIL, strict=False):
            ratio = pix.devicePixelRatio() or 1.0
            larg, haut = pix.width() / ratio, pix.height() / ratio
            p.save()
            p.translate(x + larg / 2, y + haut / 2)
            p.rotate(angle)
            p.drawPixmap(QRectF(-larg / 2, -haut / 2, larg, haut), pix, QRectF(pix.rect()))
            p.restore()
        p.end()


class _Barre(QWidget):
    """Cartes trouvées sur le total, en or sur un rail discret."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(3)
        self._part = 0.0

    def regler(self, part: float) -> None:
        self._part = max(0.0, min(1.0, part))
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        rail = QRectF(self.rect())
        p.setBrush(QColor(255, 255, 255, 26))
        p.drawRoundedRect(rail, 1.5, 1.5)
        if self._part > 0:
            p.setBrush(accent_qcolor())
            p.drawRoundedRect(QRectF(0, 0, max(3.0, rail.width() * self._part),
                                     rail.height()), 1.5, 1.5)
        p.end()


class BlocFolio(QFrame):
    """Le bloc cliquable : il a l'air d'un bouton, il en est un (règle 119)."""

    clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("blocFolio")
        self.setStyleSheet(themed(_STYLE))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Atteint au clavier ET à la manette (règle 15).
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(tr("Ouvrir le folio"))
        self.setMaximumWidth(LARGEUR_MAX)

        rang = QHBoxLayout(self)
        rang.setContentsMargins(8, 8, 12, 8)
        rang.setSpacing(12)
        self._eventail = _Eventail()
        rang.addWidget(self._eventail, 0, Qt.AlignmentFlag.AlignVCenter)

        colonne = QVBoxLayout()
        colonne.setSpacing(6)
        haut = QHBoxLayout()
        haut.setSpacing(10)
        self._compte = QLabel()
        self._compte.setFont(body_font(14))
        self._compte.setStyleSheet("color: #f2f2f4; background: transparent;")
        lien = QLabel(tr("Folio") + " ›")
        lien.setFont(body_font(12))
        lien.setStyleSheet(themed("color: #d6a72c; background: transparent;"))
        haut.addWidget(self._compte)
        haut.addStretch(1)
        haut.addWidget(lien)
        colonne.addLayout(haut)
        self._barre = _Barre()
        colonne.addWidget(self._barre)
        self._detail = QLabel()
        self._detail.setFont(body_font(12))
        # Opaque (règle 65), même gris que la ligne méta.
        self._detail.setStyleSheet("color: #b4b4d0; background: transparent;")
        # Une seule ligne, courte (« Serpentard mène ») : en deux, la hauteur
        # du bloc ne suivait pas et la seconde était coupée. L'écart de points
        # est dans le folio ; le temps de jeu, à droite de l'engrenage.
        colonne.addWidget(self._detail)
        rang.addLayout(colonne, 1)

    def montrer(self, resume: folio.Resume, cartes: list[QPixmap]) -> None:
        self._compte.setText(phrase_resume(resume))
        self._barre.regler(resume.trouvees / resume.total if resume.total else 0.0)
        self._eventail.regler(cartes)
        # Les maisons : HP1 seulement (HP3 n'écrit pas leurs points).
        maisons = (maison_en_tete(resume.releve)
                   if isinstance(resume.releve, folio.Releve) else "")
        if isinstance(resume.releve, folio_hp5.Partie) and resume.releve.decouverte:
            maisons = trn(resume.releve.decouverte, "{} point de découverte",
                          "{} points de découverte").format(_nombre(resume.releve.decouverte))
        self._detail.setText(maisons)
        self._detail.setVisible(bool(maisons))

    def heightForWidth(self, largeur: int) -> int:
        # Le panneau demande à SA largeur ; le bloc s'arrête à LARGEUR_MAX.
        return super().heightForWidth(min(largeur, self.maximumWidth()))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self.clicked.emit()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
        else:
            super().keyPressEvent(event)

    def texte_detail(self) -> str:
        return self._detail.text() if self._detail.isVisibleTo(self) else ""

    def texte_compte(self) -> str:
        return self._compte.text()


# L'icône du bloc quand le jeu ne compte pas des cartes (les mêmes qu'au folio).
# HP5 : la vignette du chapitre, celle de l'écran « Continuer aventure ».
_ICONES = {
    "hp4": lambda system, _partie: folio_hp4.image_menu(system, "boucliers"),
    "hp5": lambda system, partie: folio_hp5.image_chapitre(system, partie.chapitre),
    "hp6": lambda system, _partie: folio_hp6.image_menu(system, "ecussons"),
}


# Éventails déjà peints, par jeu, dossier, cartes, échelle et langue. Les paquets
# du jeu sont trop gros pour rester en mémoire (`textures_ue1._ouvrir` en garde
# deux : 25 Mo pour HP2), et passer de HP1 à HP3 les relisait tous : 70 ms
# d'analyse à chaque fiche (mesuré le 2026-11-01). Trois petites images, elles, se gardent.
_EVENTAILS: dict[tuple, list[QPixmap]] = {}
_EVENTAILS_MAX = 16


def cartes_eventail(game_id: str, system: Path, releve, dpr: float) -> list[QPixmap]:
    """Les trois premières cartes trouvées, en petit ; vide sans le jeu installé."""
    if game_id not in ("hp1", "hp2", "hp3"):
        return _cartes_eventail(game_id, system, releve, dpr)
    cle = (game_id, str(system), tuple(sorted(releve.cartes)), dpr, get_language())
    if cle not in _EVENTAILS:
        cartes = _cartes_eventail(game_id, system, releve, dpr)
        if not cartes:
            return cartes   # jeu absent ou paquet illisible : redemander la prochaine fois
        if len(_EVENTAILS) >= _EVENTAILS_MAX:
            _EVENTAILS.pop(next(iter(_EVENTAILS)))
        _EVENTAILS[cle] = cartes
    return _EVENTAILS[cle]


def _cartes_eventail(game_id: str, system: Path, releve, dpr: float) -> list[QPixmap]:
    from src.ui.folio_page import pixmap_texture
    if not system.is_dir():
        return []
    textures = []
    if game_id == "hp1":
        paquet = folio.paquet_menu(system)
        if paquet is None:
            return []
        textures = [folio.image_carte_hp1(paquet, n, grande=False)
                    for n in sorted(releve.cartes)[:len(_EVENTAIL)]]
    elif game_id == "hp2":
        cat2 = folio_hp2.catalogue(system, get_language())
        textures = [folio_hp2.image_carte(system, cat2[n])
                    for n in sorted(releve.cartes)[:len(_EVENTAIL)] if n in cat2]
    elif game_id == "hp3":
        cat = folio_hp3.catalogue(system, get_language())
        trouvees = [c for c in cat.cartes if c.classe in releve.cartes][:len(_EVENTAIL)]
        textures = [folio_hp3.image_carte(system, c.code, grande=False) for c in trouvees]
    elif game_id in _ICONES:
        # Pas de cartes : l'icône que le jeu donne à ce qu'on compte, seule.
        from src.ui.folio_page import image_bgra
        icone = image_bgra(_ICONES[game_id](system, releve), _CARTE_H + 4, dpr, rogner=True,
                           colonnes=(0.27, 0.73) if game_id == "hp4" else (0.0, 1.0))
        return [icone] if icone is not None else []
    return [pixmap_texture(t, _CARTE_H, dpr) for t in textures if t is not None]
