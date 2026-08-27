"""Page de statistiques — ce que le launcher a observé de lui-même.

Tout ce qui s'affiche ici vient de `src/core/stats.py`, donc de sessions que le
launcher a RÉELLEMENT chronométrées. Rien n'est lu dans les sauvegardes des
jeux : un `.usa` ne dit pas s'il est la partie en cours ou une partie finie il
y a deux ans, et afficher « terminé à 100 % » d'après une supposition est pire
que de ne rien afficher — c'est un chiffre faux qu'on n'a aucun moyen de
démentir. Le jour où un format sera décodé pour de bon, il viendra s'ajouter
ici sans rien déplacer.

Deux règles de la maison s'appliquent en particulier :
  · **rien de normal ne s'affiche** — une série de jours à 0, une plage
    d'heures sans données ou un jeu jamais lancé ne prennent pas de place ;
  · **les jauges sont PEINTES** — un `QLabel` en `wordWrap` posé dans un layout
    sans hauteur imposée annonce un `sizeHint` calculé à une largeur qui n'est
    pas la sienne. Le piège a déjà été payé quatre fois dans ce projet.
"""

from html import escape

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.core import stats
from src.core.formatting import (
    format_bytes,
    format_duree_compacte,
    format_relative_date,
)
from src.core.game_manager import GameManager, GameState
from src.core.i18n import tr
from src.ui.fonts import cinzel
from src.ui.theme import accent_qcolor, themed

_SECONDAIRE = "#b0b0c8"
_HAUTEUR_JAUGE = 8


def _jours_semaine() -> tuple[str, ...]:
    """Écrits en toutes lettres et non tirés de la locale système : la langue de
    l'interface est celle du launcher, pas celle de Windows."""
    return (tr("lundi"), tr("mardi"), tr("mercredi"), tr("jeudi"),
            tr("vendredi"), tr("samedi"), tr("dimanche"))


def _texte(contenu: str, taille: int = 13, couleur: str = "#ffffff",
           gras: bool = False) -> QLabel:
    """QLabel en PlainText — ces chaînes portent des noms venus du CATALOGUE,
    et `AutoText` bascule en rich text dès que Qt renifle du HTML."""
    lbl = QLabel(contenu)
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    poids = "bold" if gras else "normal"
    lbl.setStyleSheet(f"color: {couleur}; font-size: {taille}px; font-weight: {poids};"
                      " background: transparent;")
    return lbl


class _Paragraphe(QLabel):
    """Texte qui revient à la ligne, et dont la hauteur suit la largeur RÉELLE.

    C'est le remède au piège maison le plus récurrent : le `sizeHint` d'un
    `QLabel` en `wordWrap` est calculé à une largeur qui n'est pas la sienne,
    donc le layout ne lui accorde qu'une ligne et le texte est coupé. On mesure
    au moment où la largeur est enfin connue — au `resizeEvent` — et jamais
    avant. Sans ça, la liste des jeux jamais lancés se tronque dès qu'il y en a
    trois, c'est-à-dire chez presque tout le monde au début.
    """

    def __init__(self, contenu: str, parent=None) -> None:
        super().__init__(contenu, parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True)
        self.setStyleSheet(f"color: {_SECONDAIRE}; font-size: 12px; background: transparent;")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.setMinimumHeight(0)
        self.setMinimumHeight(self.heightForWidth(self.width()))


class _Chiffre(QFrame):
    """Une carte du bandeau : un grand nombre et ce qu'il compte."""

    def __init__(self, valeur: str, libelle: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("carteChiffre")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(2)
        grand = _texte(valeur, 22, "#ffffff", gras=True)
        grand.setFont(cinzel(21, bold=True))
        lay.addWidget(grand)
        lay.addWidget(_texte(libelle, 12, _SECONDAIRE))


class _Jauge(QWidget):
    """Barre de proportion peinte. `part` va de 0 à 1."""

    def __init__(self, part: float, parent=None) -> None:
        super().__init__(parent)
        self._part = max(0.0, min(1.0, part))
        self.setFixedHeight(_HAUTEUR_JAUGE)
        self.setMinimumWidth(60)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        r = _HAUTEUR_JAUGE / 2
        p.setBrush(QColor(255, 255, 255, 22))
        p.drawRoundedRect(QRectF(0, 0, self.width(), _HAUTEUR_JAUGE), r, r)
        if self._part > 0:
            # Plancher à la hauteur de la barre : en dessous, un rectangle
            # arrondi n'a plus de longueur visible et une part réelle mais
            # minuscule disparaîtrait complètement.
            largeur = max(_HAUTEUR_JAUGE, self.width() * self._part)
            p.setBrush(accent_qcolor(230))
            p.drawRoundedRect(QRectF(0, 0, largeur, _HAUTEUR_JAUGE), r, r)
        p.end()


class _Saga(QWidget):
    """Les huit jeux en huit segments : joué, installé, absent.

    C'est la seule statistique proprement « Harry Potter » que le launcher
    puisse produire sans ouvrir une sauvegarde, et c'est celle qui donne envie
    d'aller chercher le suivant.
    """

    def __init__(self, entrees, joues: set[str], parent=None) -> None:
        super().__init__(parent)
        self._entrees = list(entrees)
        self._joues = joues
        self.setFixedHeight(22)
        self.setMouseTracking(True)

    def _segment(self, i: int) -> QRectF:
        n = max(1, len(self._entrees))
        pas = self.width() / n
        return QRectF(i * pas + 2, 5, max(4.0, pas - 4), 12)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i, entree in enumerate(self._entrees):
            rect = self._segment(i)
            if entree.game.id in self._joues:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(accent_qcolor(230))
            elif entree.state == GameState.INSTALLED:
                p.setPen(accent_qcolor(150))
                p.setBrush(Qt.BrushStyle.NoBrush)
            else:
                p.setPen(QColor(255, 255, 255, 45))
                p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, 3, 3)
        p.end()

    def mouseMoveEvent(self, event) -> None:
        """Le nom du jeu sous le curseur — sans ça, huit segments anonymes.

        Le nom est échappé : une infobulle est un `QLabel` laissé en `AutoText`,
        donc le seul endroit de la page où du balisage venu du catalogue serait
        INTERPRÉTÉ — le reste est en `PlainText` par construction.
        """
        x = event.position().x()
        for i, entree in enumerate(self._entrees):
            if self._segment(i).contains(QPointF(x, 11.0)):
                self.setToolTip(escape(entree.game.name, quote=False))
                return
        self.setToolTip("")


class _Heures(QWidget):
    """Histogramme des heures de début de partie (24 cases)."""

    def __init__(self, cases: list[int], parent=None) -> None:
        super().__init__(parent)
        self._cases = cases
        self.setFixedHeight(78)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        haut = max(self._cases) or 1
        zone = self.height() - 18
        pas = self.width() / 24
        # Une ligne de base CONTINUE, et non un moignon de barre par heure
        # vide : les moignons laissaient un trait pointillé, qu'on lit comme un
        # axe cassé plutôt que comme des heures sans partie.
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 26))
        p.drawRect(QRectF(0, zone - 1, self.width(), 1))
        p.setBrush(accent_qcolor(210))
        for h, valeur in enumerate(self._cases):
            hauteur = zone * valeur / haut
            if hauteur >= 2:
                p.drawRoundedRect(
                    QRectF(h * pas + 1.5, zone - hauteur, max(3.0, pas - 3), hauteur),
                    2, 2)
        p.setPen(QColor(150, 150, 175))
        police = p.font()
        police.setPixelSize(10)
        p.setFont(police)
        # Chiffres NUS, sans unité. « {} h » est déjà la clé d'une DURÉE
        # (`format_duree_compacte`) : la réutiliser ici aurait mis un traducteur
        # devant une chaîne à deux sens, dont un seul se voit à la relecture.
        # La phrase juste au-dessus dit déjà qu'on parle d'heures.
        for h in (0, 6, 12, 18):
            p.drawText(QRectF(h * pas, zone + 3, pas * 4, 14),
                       int(Qt.AlignmentFlag.AlignLeft), str(h))
        p.end()


class StatsDialog(QDialog):
    """Tout ce que le launcher sait de tes parties."""

    def __init__(self, manager: GameManager, parent=None) -> None:
        super().__init__(parent)
        self.manager = manager
        self._hist = stats.charger()
        # Les trois dérivées dont vit toute la page, calculées UNE fois. Les
        # sections se les repassaient : `temps_par_jeu` était parcouru trois
        # fois et le dictionnaire des noms reconstruit à l'identique dans deux
        # méthodes — deux copies à corriger le jour où le nom d'un jeu se
        # résoudra autrement. La page grandira, ces lignes ne bougeront pas.
        self._entrees = manager.get_games()
        self._noms = {e.game.id: e.game.name for e in self._entrees}
        self._temps = stats.temps_par_jeu(self._hist)
        self.setWindowTitle(tr("Statistiques"))
        self.setMinimumSize(720, 560)
        # Le minimum est ce qui TIENT, pas ce qu'il faut montrer : à
        # 560 px les habitudes tombaient sous la ligne de flottaison.
        self.resize(840, 720)
        self.setStyleSheet(themed(self._style()))
        self._build()

    def _style(self) -> str:
        return """
        QDialog { background-color: #0d0d1a; color: #ffffff; }
        QLabel { color: #ffffff; background: transparent; }
        QLabel#titreSection {
            font-size: 12px; font-weight: bold; color: #d6a72c;
            letter-spacing: 1px;
        }
        QFrame#carteChiffre {
            background-color: #16213e;
            border: 1px solid #2c3e6b;
            border-radius: 8px;
        }
        QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }
        QScrollBar:vertical {
            background: transparent; width: 10px; margin: 0;
        }
        QScrollBar::handle:vertical {
            background: #2c3e6b; border-radius: 5px; min-height: 30px;
        }
        QScrollBar::handle:vertical:hover { background: #d6a72c; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
        QPushButton#btnClose {
            background-color: #d6a72c; color: #000000; font-weight: bold;
            border: none; border-radius: 6px; padding: 10px 24px; font-size: 14px;
        }
        QPushButton#btnClose:hover { background-color: #e6b422; }
        """

    # ──────────────────── Construction ────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        titre = QLabel(tr("Statistiques"))
        titre.setFont(cinzel(18, bold=True))
        root.addWidget(titre)

        sous_titre = self._ligne_de_couverture()
        if sous_titre:
            root.addWidget(_texte(sous_titre, 12, _SECONDAIRE))

        zone = QScrollArea()
        zone.setWidgetResizable(True)
        zone.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        contenu = QWidget()
        self._corps = QVBoxLayout(contenu)
        self._corps.setContentsMargins(0, 4, 8, 4)
        self._corps.setSpacing(14)
        zone.setWidget(contenu)
        root.addWidget(zone, 1)

        if self._hist.vide:
            self._etat_vide()
        else:
            self._bandeau()
            self._saga()
            self._par_jeu()
            self._habitudes()
        self._corps.addStretch(1)

        bas = QHBoxLayout()
        bas.addStretch(1)
        fermer = QPushButton(tr("Fermer"))
        fermer.setObjectName("btnClose")
        fermer.setCursor(Qt.CursorShape.PointingHandCursor)
        fermer.clicked.connect(self.accept)
        bas.addWidget(fermer)
        root.addLayout(bas)

    def _ligne_de_couverture(self) -> str:
        """Depuis quand le journal couvre, et combien de fois le launcher a servi."""
        morceaux = []
        premiere = stats.premiere_session(self._hist)
        if premiere is not None:
            morceaux.append(tr("Depuis le {}").format(premiere.strftime("%d/%m/%Y")))
        if self._hist.demarrages > 1:
            morceaux.append(tr("{} démarrages du launcher").format(self._hist.demarrages))
        if self._hist.octets_telecharges > 0:
            morceaux.append(tr("{} téléchargés").format(
                format_bytes(self._hist.octets_telecharges)))
        return "  ·  ".join(morceaux)

    def _titre_section(self, texte: str) -> None:
        lbl = QLabel(texte.upper())
        lbl.setObjectName("titreSection")
        self._corps.addWidget(lbl)

    def _etat_vide(self) -> None:
        """Le premier jour, cette page ne doit pas avoir l'air cassée."""
        msg = _texte(tr("Lance une partie : cette page se remplit toute seule."),
                     14, _SECONDAIRE)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Centré, et non posé en haut : une page vide qui commence en haut se
        # lit comme un contenu qui n'a pas fini de charger.
        self._corps.addStretch(1)
        self._corps.addWidget(msg)

    # ──────────────────── Sections ────────────────────

    def _bandeau(self) -> None:
        total = sum(self._temps.values())
        parties = len(self._hist.sessions)
        grille = QGridLayout()
        grille.setSpacing(10)
        cartes = [(format_duree_compacte(total), tr("de jeu au total"))]
        # Les trois suivantes se déduisent des SESSIONS : sans session
        # enregistrée elles vaudraient toutes zéro, ce qui n'est pas une
        # information mais trois cases vides.
        if parties:
            cartes.append((str(parties), tr("parties lancées")))
            cartes.append((format_duree_compacte(stats.duree_moyenne(self._hist)),
                           tr("par session en moyenne")))
            cartes.append((str(len(stats.jours_joues(self._hist))), tr("jours de jeu")))
        for i, (valeur, libelle) in enumerate(cartes):
            grille.addWidget(_Chiffre(valeur, libelle), 0, i)
        self._corps.addLayout(grille)

    def _saga(self) -> None:
        entrees = self._entrees
        if not entrees:
            return
        joues = {gid for gid, secondes in self._temps.items() if secondes > 0}
        installes = sum(1 for e in entrees if e.state == GameState.INSTALLED)
        self._titre_section(tr("Progression dans la saga"))
        self._corps.addWidget(_Saga(entrees, joues))
        detail = tr("{} des {} jeux joués").format(
            len([e for e in entrees if e.game.id in joues]), len(entrees))
        if installes:
            detail += "  ·  " + tr("{} installés").format(installes)
        self._corps.addWidget(_texte(detail, 12, _SECONDAIRE))

    def _par_jeu(self) -> None:
        temps = self._temps
        if not temps:
            return
        parties = stats.parties_par_jeu(self._hist)
        derniere = stats.derniere_par_jeu(self._hist)
        noms = self._noms
        plus_haut = max(temps.values())

        self._titre_section(tr("Temps par jeu"))
        grille = QGridLayout()
        grille.setHorizontalSpacing(12)
        grille.setVerticalSpacing(8)
        grille.setColumnStretch(1, 1)
        for ligne, (gid, secondes) in enumerate(
                sorted(temps.items(), key=lambda kv: -kv[1])):
            grille.addWidget(_texte(noms.get(gid, gid), 13), ligne, 0)
            grille.addWidget(_Jauge(secondes / plus_haut), ligne, 1)
            grille.addWidget(_texte(format_duree_compacte(secondes), 13, gras=True),
                             ligne, 2)
            n = parties.get(gid, 0)
            # Un jeu dont tout le temps est antérieur au journal n'a pas de
            # compte de parties : mieux vaut ne rien dire qu'annoncer « 0 partie »
            # à côté de six heures de jeu.
            grille.addWidget(_texte(tr("{} parties").format(n) if n else "",
                                    12, _SECONDAIRE), ligne, 3)
            jour = derniere.get(gid)
            grille.addWidget(_texte(format_relative_date(jour.isoformat()) if jour else "",
                                    12, _SECONDAIRE), ligne, 4)
        self._corps.addLayout(grille)

        jamais = [e.game.name for e in self._entrees if e.game.id not in temps]
        if jamais:
            self._corps.addWidget(_Paragraphe(
                tr("Jamais lancés : {}").format(" · ".join(jamais))))

    def _habitudes(self) -> None:
        if not self._hist.sessions:
            return
        self._titre_section(tr("Habitudes"))
        grille = QGridLayout()
        grille.setHorizontalSpacing(14)
        grille.setVerticalSpacing(6)
        grille.setColumnStretch(1, 1)

        def ajouter(ligne: int, etiquette: str, valeur: str) -> None:
            grille.addWidget(_texte(etiquette, 12, _SECONDAIRE), ligne, 0)
            grille.addWidget(_texte(valeur, 13), ligne, 1)

        ligne = 0
        serie = stats.serie_actuelle(self._hist)
        if serie > 1:
            record = stats.meilleure_serie(self._hist)
            valeur = tr("{} jours d'affilée").format(serie)
            if record > serie:
                valeur += "  ·  " + tr("record : {} jours").format(record)
            ajouter(ligne, tr("Série en cours"), valeur)
            ligne += 1

        longue = stats.plus_longue(self._hist)
        if longue is not None:
            ajouter(ligne, tr("Plus longue partie"),
                    tr("{} — {}, le {}").format(
                        self._noms.get(longue.jeu, longue.jeu),
                        format_duree_compacte(longue.duree),
                        longue.debut.strftime("%d/%m/%Y")))
            ligne += 1

        jour = stats.jour_prefere(self._hist)
        if jour is not None:
            ajouter(ligne, tr("Jour de prédilection"), _jours_semaine()[jour])
            ligne += 1
        self._corps.addLayout(grille)

        plage = stats.plage_de_predilection(self._hist)
        if plage is not None:
            debut, fin = plage
            self._corps.addWidget(_texte(
                tr("Tu lances surtout une partie entre {} h et {} h").format(debut, fin),
                12, _SECONDAIRE))
            self._corps.addWidget(_Heures(stats.par_heure(self._hist)))

