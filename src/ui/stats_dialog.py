"""La saga — ce que le launcher a observé de tes parties.

Tout vient pour l'instant de `src/core/stats.py`, donc de parties que le
launcher a RÉELLEMENT chronométrées. **Les sauvegardes des jeux ne sont pas
encore lues — ce n'est pas un refus, c'est une question ouverte** : une lecture
UNIQUE ne dit pas si un `.usa` à 100 % est la partie en cours ou une partie
finie il y a deux ans, ni ce qu'on fait quand un jeu déjà terminé est repris
depuis le début. Afficher un avancement d'après une supposition serait un
chiffre faux qu'on n'a aucun moyen de démentir. Le jour où la question sera
tranchée, l'avancement viendra s'ajouter ici sans rien déplacer.

**Cette page a été un tableau de bord, et c'était une erreur.** Elle alignait
quatre grands chiffres, une barre de progression en huit segments, des jauges
de temps par jeu et un bloc d'habitudes. Au premier jour elle affichait UNE
carte (« 4 min de jeu au total ») étirée sur toute la largeur, six rectangles
vides sur huit, et — bloc le plus gros et le plus coloré de la page — la liste
des six jeux JAMAIS lancés. Tout ce qu'elle mettait en avant était une absence,
et le reste était exact sans rien apprendre à personne.

Deux formes la remplacent, parce qu'elles échouent à des endroits différents :

· **la frise** (les huit jaquettes dans l'ordre de la saga) donne à la page un
  squelette qui NE DÉPEND PAS DES DONNÉES. C'est le vrai diagnostic de l'ancien
  écran : chaque bloc y changeait de taille selon ce qu'il y avait — quatre
  cartes puis une, huit segments dont six vides, six lignes de liste, puis du
  vide. Une page dont la structure varie a l'air cassée bien avant d'avoir
  l'air pauvre. Ici, huit jaquettes, toujours, dès la première seconde d'usage
  comme après trois ans ; seule l'ENCRE varie.
· **le journal** (les parties, la dernière en haut) donne une raison d'y
  revenir, ce qu'une frise seule n'a pas : elle est identique à chaque visite.
  Et il applique la règle « rien de normal ne s'affiche » GRATUITEMENT — un jeu
  auquel on n'a jamais joué n'a simplement aucune ligne, sans seuil, sans
  condition, sans risque de le reprocher à personne.

Ce qui a été retiré, et ne doit pas revenir : la liste des jeux jamais lancés
(un catalogue de ce qu'on n'a pas fait), les segments vides (la même chose en
géométrie), la série de jours (sa seule force est la peur de la rompre — un
nag, sur des jeux qu'on rejoue deux fois par an), le jour et la plage horaire
de prédilection (vrais, prouvés, et inertes ; et devinés tant qu'il n'y a pas
vingt soirées derrière), le nombre de démarrages du launcher et les octets
téléchargés (ça mesure l'outil, pas la partie).

Les jaquettes non jouées ne sont NI grisées NI désaturées : six tuiles ternes
sur huit remplaceraient un paragraphe qui accuse par une image qui accuse.
Toutes à pleine présence, seul le chiffre distingue.
"""

from datetime import date
from html import escape

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFontMetrics, QImageReader, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.core import stats
from src.core.config import ASSETS_DIR
from src.core.formatting import format_duree_compacte
from src.core.game_manager import GameManager
from src.core.i18n import tr
from src.ui.fonts import cinzel
from src.ui.theme import accent_qcolor, themed

_SECONDAIRE = "#b0b0c8"

# La frise : huit jaquettes, largeur partagée, HAUTEUR DÉDUITE de la largeur.
#
# Le rapport est celui d'une affiche (2:3), et il est mesuré, pas choisi : cinq
# jaquettes du catalogue sont en 600 × 900, trois sont carrées (HP2, HP7a,
# HP7b). Aucune case ne peut flatter les deux familles — mais une case à 0,83,
# comme ici avant le 2026-08-28, rognait TOUT LE MONDE : 20 % de hauteur sur
# les affiches et 17 % de largeur sur les carrées, si bien que les trois
# dernières de la rangée avaient l'air zoomées sans qu'on sache pourquoi. En
# 2:3, cinq jaquettes sur huit sont exactes et seules les trois carrées sont
# recadrées — ce sont des affiches centrées, elles le supportent.
#
# La hauteur ne peut PAS être une constante posée à côté de la largeur : c'est
# le défaut du carrousel (`THUMB_H` contre `CAROUSEL_HEIGHT`), payé deux fois.
# `_Frise.resizeEvent` la calcule.
_FRISE_RAPPORT = 2 / 3          # largeur / hauteur d'une case
_FRISE_LEGENDE_H = 24
_FRISE_ECART = 8

# Au-delà, « pas relancé depuis… » DÉVIE et mérite une ligne. En deçà, c'est
# l'état normal de quelqu'un qui joue à autre chose cette semaine.
_DELAISSE_JOURS = 90

# Le journal est intégral dans le fichier ; à l'écran on s'arrête, sinon
# construire vingt mille lignes de layout gèlerait l'ouverture de la page.
_JOURNAL_MAX = 100

# Plafond d'ouverture. Au-delà, le journal défile — mais la fenêtre ne s'ouvre
# JAMAIS plus haute que son contenu : c'est ce plafond qui borne, pas un vide.
_HAUTEUR_MAX = 720


def _duree_frise(secondes: int) -> str:
    """Durée pour la LÉGENDE d'une case, où la place se compte en dizaines de px.

    `format_duree_compacte` rend « moins d'une minute » — juste dans le journal,
    où la ligne se lit d'un trait, et deux fois trop long sous une jaquette.
    Une forme propre à ce support vaut mieux qu'une élision, qui rendrait ici
    « moins d'une m… », c'est-à-dire du bruit à la place d'un chiffre.
    """
    return tr("< 1 min") if secondes < 60 else format_duree_compacte(secondes)


def _texte(contenu: str, taille: int = 13, couleur: str = "#ffffff",
           gras: bool = False) -> QLabel:
    """QLabel en PlainText — ces chaînes portent des noms venus du CATALOGUE,
    et `AutoText` bascule en rich text dès que Qt renifle du HTML."""
    lbl = QLabel(contenu)
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    poids = "bold" if gras else "normal"
    lbl.setStyleSheet(
        f"color: {couleur}; font-size: {taille}px; font-weight: {poids};"
        " background: transparent;")
    return lbl


class _Paragraphe(QLabel):
    """Texte long en `wordWrap`, dont la hauteur suit la largeur RÉELLE.

    Un `QLabel` en `wordWrap` posé dans un layout sans hauteur imposée annonce
    un `sizeHint` calculé à une largeur qui n'est pas la sienne : le layout ne
    lui accorde qu'une ligne et le texte se coupe. Le piège a été payé cinq
    fois dans ce projet ; le remède vit ici une fois pour toutes.
    """

    def __init__(self, contenu: str, parent=None) -> None:
        super().__init__(contenu, parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True)
        self.setStyleSheet(
            f"color: {_SECONDAIRE}; font-size: 12px; background: transparent;")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.setMinimumHeight(0)
        self.setMinimumHeight(self.heightForWidth(self.width()))


class _Frise(QWidget):
    """Les huit jeux dans l'ordre de la saga, jaquette à l'appui.

    C'est ce qui remplace la barre en huit segments : l'ordre des huit existe
    dans le monde, le launcher ne le fabrique pas — et il se lit sans légende,
    ce qu'aucun de nos autres graphiques ne faisait.

    **Pas de pourcentage de complétion.** Une barre « 2/8 » posée sur des jeux
    qu'on possède déjà est une liste de tâches qu'on n'a pas écrite, et elle
    fait passer un cinquième replay de HP3 pour une stagnation. La frise montre
    ce qui a été vécu ; elle ne note pas.

    Les jaquettes sont peintes à la main plutôt que posées en `QLabel` : la
    largeur d'une case se déduit de celle du widget, donc la frise tient à
    toutes les tailles de fenêtre sans qu'aucun nombre ne soit écrit à côté
    d'un autre — c'est le défaut du carrousel, payé deux fois.
    """

    def __init__(self, entrees, temps: dict[str, int], parent=None) -> None:
        super().__init__(parent)
        self._entrees = list(entrees)
        self._temps = temps
        self._jaquettes: dict[str, QPixmap] = {}
        self.setMouseTracking(True)
        for e in self._entrees:
            pm = self._charger(e.game.cover_image)
            if pm is not None:
                self._jaquettes[e.game.id] = pm

    @staticmethod
    def _charger(nom_fichier: str) -> QPixmap | None:
        """Réduction demandée AU DÉCODEUR, comme le carrousel : décoder un
        JPEG 1024×1024 en pleine résolution pour l'afficher à 150 px coûte huit
        fois le temps de l'ouverture de la page.

        Le plafond est en HAUTEUR de case × 2 (écrans à forte densité). Il est
        généreux à dessein : la case grandit avec la fenêtre, et re-décoder à
        chaque redimensionnement coûterait bien plus que les quelques pixels
        économisés ici.
        """
        chemin = ASSETS_DIR / "covers" / nom_fichier
        if not chemin.exists():
            return None
        lecteur = QImageReader(str(chemin))
        source = lecteur.size()
        if source.isValid() and source.height() > 0:
            facteur = 400 / source.height()
            if facteur < 1.0:
                lecteur.setScaledSize(source * facteur)
        image = lecteur.read()
        return None if image.isNull() else QPixmap.fromImage(image)

    def _hauteur_case(self) -> float:
        n = max(1, len(self._entrees))
        largeur = (self.width() - _FRISE_ECART * (n - 1)) / n
        return largeur / _FRISE_RAPPORT

    def resizeEvent(self, event) -> None:
        """La hauteur se DÉDUIT de la largeur reçue — jamais l'inverse.

        Le layout vertical donne la largeur et lit la hauteur : la boucle est
        donc impossible, et la garde `!=` évite un aller-retour inutile.
        """
        super().resizeEvent(event)
        voulue = round(self._hauteur_case()) + _FRISE_LEGENDE_H
        if voulue != self.height():
            self.setFixedHeight(voulue)

    def _case(self, i: int) -> QRectF:
        n = max(1, len(self._entrees))
        largeur = (self.width() - _FRISE_ECART * (n - 1)) / n
        return QRectF(i * (largeur + _FRISE_ECART), 0.0,
                      largeur, self._hauteur_case())

    def mouseMoveEvent(self, event) -> None:
        """Le nom du jeu sous le curseur — sans ça, huit jaquettes muettes.

        Le nom est échappé : une infobulle est un `QLabel` laissé en `AutoText`,
        donc le seul endroit de la page où du balisage venu du catalogue serait
        INTERPRÉTÉ — tout le reste est en `PlainText` par construction.
        """
        x = event.position().x()
        for i, entree in enumerate(self._entrees):
            case = self._case(i)
            if case.left() <= x <= case.right():
                self.setToolTip(escape(entree.game.name, quote=False))
                return
        self.setToolTip("")

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        police = p.font()
        police.setPointSize(9)
        for i, entree in enumerate(self._entrees):
            case = self._case(i)
            pm = self._jaquettes.get(entree.game.id)
            if pm is not None:
                p.save()
                p.setClipRect(case)
                # « Par expansion » : on couvre la case sans bande vide, les
                # jaquettes du catalogue n'ayant pas toutes le même rapport.
                facteur = max(case.width() / pm.width(), case.height() / pm.height())
                dessine = QRectF(0, 0, pm.width() * facteur, pm.height() * facteur)
                dessine.moveCenter(case.center())
                p.drawPixmap(dessine, pm, QRectF(pm.rect()))
                p.restore()
            else:
                p.fillRect(case, QColor(22, 33, 62))

            secondes = self._temps.get(entree.game.id, 0)
            if not secondes:
                continue        # rien à dire : l'absence ne prend pas d'encre
            p.setFont(police)
            p.setPen(accent_qcolor())
            # ÉLIDER, toujours : un `drawText` centré ne coupe rien et déborde
            # des DEUX côtés. « moins d'une minute » réclamait 105 px dans une
            # case de 98 et sortait à l'écran en « oins d'une minu » — le
            # défaut documenté du bouton principal, repayé ici.
            texte = QFontMetrics(police).elidedText(
                _duree_frise(secondes), Qt.TextElideMode.ElideRight,
                int(case.width()))
            p.drawText(QRectF(case.left(), case.bottom() + 4.0,
                              case.width(), _FRISE_LEGENDE_H - 4.0),
                       int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                       texte)
        p.end()


class StatsDialog(QDialog):
    """La saga : la frise de ce qui a été joué, puis le journal des parties."""

    def __init__(self, manager: GameManager, parent=None) -> None:
        super().__init__(parent)
        self.manager = manager
        self._hist = stats.charger()
        # Les dérivées dont vit toute la page, calculées UNE fois.
        self._entrees = manager.get_games()
        self._noms = {e.game.id: e.game.name for e in self._entrees}
        self._temps = stats.temps_par_jeu(self._hist)
        self.setWindowTitle(tr("La saga"))
        # Assez LARGE pour que huit jaquettes restent des images et non des
        # timbres : sous ~700 px utiles, la frise ne se lit plus. Pas de
        # plancher en HAUTEUR, en revanche : il valait 520 px et empêchait la
        # page sans journal de se rétrécir à son contenu — la garde même qu'on
        # avait écrite contre le vide était donc bloquée par cette ligne.
        self.setMinimumWidth(760)
        self._zone: QScrollArea | None = None
        self._contenu: QWidget | None = None
        self._ajuste = False
        self.resize(880, _HAUTEUR_MAX)
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
        root.setSpacing(12)

        titre = QLabel(tr("La saga"))
        titre.setFont(cinzel(18, bold=True))
        root.addWidget(titre)
        root.addWidget(_texte(self._ouverture(), 13, _SECONDAIRE))

        # La frise est HORS de la zone défilante : c'est le squelette de la
        # page, il ne doit jamais partir sous la ligne de flottaison.
        root.addWidget(_Frise(self._entrees, self._temps))

        for ligne in self._faits_marquants():
            root.addWidget(_Paragraphe(ligne))

        # Le journal se construit AVANT d'être posé : on ne sait qu'après s'il a
        # quelque chose à dire, et la zone défilante ne doit pas exister s'il
        # n'en a pas. La créer puis la retirer ne suffit pas — `deleteLater`
        # laisse le widget dans le layout le temps d'un tour de boucle, donc le
        # vide se déplace au lieu de disparaître (essayé, mesuré à l'image).
        contenu = QWidget()
        self._corps = QVBoxLayout(contenu)
        self._corps.setContentsMargins(0, 4, 8, 4)
        self._corps.setSpacing(12)
        rempli = self._journal()

        zone: QScrollArea | None = None
        if rempli:
            self._corps.addStretch(1)
            zone = QScrollArea()
            zone.setWidgetResizable(True)
            zone.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            zone.setWidget(contenu)
            root.addWidget(zone, 1)
        else:
            # **Une page ne se termine jamais par du vide.** Sans journal, la
            # zone défilante étirait 450 px de rien sous la frise, et une page
            # qui commence en haut puis s'arrête au milieu se lit comme un
            # chargement inachevé — c'est-à-dire comme une panne. On ne remplit
            # pas : la fenêtre s'arrête où le contenu s'arrête.
            contenu.deleteLater()
            # Le temps d'avant le journal se dit quand même, sans le titre de
            # section : un titre « JOURNAL DES PARTIES » au-dessus de zéro
            # partie annonce une liste qui n'existe pas. Sans cette phrase, en
            # revanche, le total de l'en-tête ne se raccorde à rien.
            herite = sum(self._hist.herite.values())
            if herite:
                root.addWidget(_Paragraphe(
                    tr("Avant la mise en service du journal : {}, sans le "
                       "détail des parties.").format(
                           format_duree_compacte(herite))))

        bas = QHBoxLayout()
        bas.addStretch(1)
        fermer = QPushButton(tr("Fermer"))
        fermer.setObjectName("btnClose")
        fermer.setCursor(Qt.CursorShape.PointingHandCursor)
        fermer.clicked.connect(self.accept)
        bas.addWidget(fermer)
        root.addLayout(bas)
        self._zone = zone
        self._contenu = contenu if rempli else None

    def showEvent(self, event) -> None:
        """La hauteur ne se mesure qu'une fois la page RÉELLEMENT mise en page.

        Elle était ajustée à la fin de `_build`, c'est-à-dire avant que le
        moindre widget ait une largeur : `_Frise` et `_Paragraphe` calculent
        tous deux leur hauteur d'après la largeur reçue, donc à ce moment-là
        aucun des deux n'a la sienne et la somme est fausse. C'est le piège
        déjà écrit dans CLAUDE.md pour les tests (« mesurer une hauteur pilotée
        par resizeEvent sur un widget qu'on n'a pas affiché ») — il vaut pour
        le code autant que pour ce qui le vérifie.
        """
        super().showEvent(event)
        if not self._ajuste:
            self._ajuste = True
            self._ajuster_hauteur()

    def _ajuster_hauteur(self) -> None:
        """La fenêtre s'arrête où le contenu s'arrête, plafonnée à `_HAUTEUR_MAX`.

        **La règle vaut dans les DEUX états, et c'était l'erreur** : elle n'était
        appliquée qu'à la page sans journal. Avec quatre parties au journal, la
        fenêtre s'ouvrait quand même à 700 px et la zone défilante — qui prend
        tout l'excédent — étirait 250 px de vide sous la dernière ligne. Une
        page qui commence en haut et s'arrête au milieu se lit comme un
        chargement inachevé, que la cause soit un journal absent ou un journal
        court.

        L'écart est mesuré sur ce qui est POSÉ, jamais sur un `sizeHint` de
        `QScrollArea` : celui-ci ne porte pas la hauteur de son contenu, c'est
        même toute sa raison d'être.
        """
        self.setMinimumHeight(0)
        self.layout().activate()
        if self._zone is not None and self._contenu is not None:
            ecart = (self._contenu.sizeHint().height()
                     - self._zone.viewport().height())
        else:
            ecart = self.sizeHint().height() - self.height()
        self.resize(self.width(), min(self.height() + ecart, _HAUTEUR_MAX))

    def _ouverture(self) -> str:
        """Une PHRASE, et non une rangée de cartes.

        Une rangée a un nombre fixe de membres : elle est cassée dès qu'il en
        manque un, et une carte solitaire étirée sur 800 px en était la preuve
        à l'écran. Une phrase se raccourcit sans se déformer — c'est la seule
        forme qui encaisse une donnée comme quatre.
        """
        total = sum(self._temps.values())
        if not total:
            return tr("Aucune partie enregistrée pour l'instant — "
                      "lance un jeu, cette page se remplira toute seule.")
        joues = len([e for e in self._entrees if self._temps.get(e.game.id)])
        if joues >= len(self._entrees) > 0:
            return tr("{} de jeu, sur les {} jeux de la saga.").format(
                format_duree_compacte(total), len(self._entrees))
        return tr("{} de jeu, sur {} des {} jeux de la saga.").format(
            format_duree_compacte(total), joues, len(self._entrees))

    def _faits_marquants(self) -> list[str]:
        """Des faits DATÉS, jamais des moyennes.

        Un événement unique est vrai dès la première fois ; une moyenne ment
        jusqu'à ce qu'elle ait de quoi. C'est la ligne de partage que l'ancienne
        page ne faisait pas — elle annonçait une « plage horaire de
        prédilection » sur deux soirées, ce qui est de l'horoscope, et le prix
        d'un horoscope est qu'on cesse de croire le reste de la page.

        Et jamais un record sans sa date : daté, c'est un souvenir ; sans date,
        c'est un chiffre.
        """
        lignes = []
        longue = stats.plus_longue(self._hist)
        if longue is not None:
            lignes.append(tr("Plus longue partie : {} sur {}, le {}.").format(
                format_duree_compacte(longue.duree),
                self._noms.get(longue.jeu, longue.jeu),
                longue.debut.strftime("%d/%m/%Y")))

        delaisse = self._delaisse()
        if delaisse is not None:
            gid, jours = delaisse
            lignes.append(tr("{} : pas relancé depuis {} jours.").format(
                self._noms.get(gid, gid), jours))
        return lignes

    def _delaisse(self) -> tuple[str, int] | None:
        """Le jeu qu'on a vraiment joué et qu'on ne lance plus.

        C'est la donnée qui compte pour des jeux de NOSTALGIE : le cumul par
        jeu n'apprend rien à quelqu'un qui sait déjà avoir beaucoup joué à HP2,
        alors que l'écart lui rappelle ce qu'il avait oublié. Un rappel, pas un
        reproche — d'où le seuil, « depuis trois jours » n'étant pas une
        information.

        `derniere_par_jeu` ne voit QUE les sessions : un jeu dont tout le temps
        est antérieur au journal n'a pas de date, et serait annoncé comme
        délaissé alors qu'on n'en sait rien. La garde est structurelle.
        """
        derniere = stats.derniere_par_jeu(self._hist)
        if not derniere:
            return None
        aujourd_hui = date.today()
        candidats = [(gid, (aujourd_hui - jour).days) for gid, jour in derniere.items()]
        candidats = [(gid, j) for gid, j in candidats if j >= _DELAISSE_JOURS]
        if not candidats:
            return None
        # Le plus joué d'entre eux : c'est celui dont l'absence pèse.
        return max(candidats, key=lambda c: self._temps.get(c[0], 0))

    def _journal(self) -> bool:
        """Les parties, la dernière en haut. Rend False s'il n'y a rien à dire.

        Un agrégat n'est intéressant qu'après des mois ; une entrée de journal
        l'est dès la première, parce que l'entrée EST le contenu. C'est aussi
        la seule forme qui applique « rien de normal ne s'affiche » toute seule
        — un jeu jamais lancé n'a pas de ligne, sans qu'aucune condition n'ait
        eu à être écrite.
        """
        sessions = sorted(self._hist.sessions, key=lambda s: s.debut, reverse=True)
        if not sessions:
            # **Le temps hérité ne fait PAS un journal.** Il rendait True ici,
            # donc la zone défilante existait pour porter une seule phrase et
            # étirait 388 px de vide sous la frise (mesuré le 2026-08-28 sur la
            # capture de Ludo). C'est l'état de TOUS les utilisateurs actuels :
            # du temps de jeu d'avant le journal, et pas encore une partie
            # enregistrée. Mon test de l'état vide ne couvrait que le premier
            # lancement — un état vide plus rare que celui-ci.
            return False

        self._titre_section(tr("Journal des parties"))
        grille = QGridLayout()
        grille.setHorizontalSpacing(16)
        grille.setVerticalSpacing(6)
        grille.setColumnStretch(1, 1)
        for ligne, s in enumerate(sessions[:_JOURNAL_MAX]):
            grille.addWidget(_texte(s.debut.strftime("%d/%m/%Y  %H:%M"),
                                    12, _SECONDAIRE), ligne, 0)
            grille.addWidget(_texte(self._noms.get(s.jeu, s.jeu), 13), ligne, 1)
            valeur = _texte(format_duree_compacte(s.duree), 13, gras=True)
            valeur.setAlignment(Qt.AlignmentFlag.AlignRight
                                | Qt.AlignmentFlag.AlignVCenter)
            grille.addWidget(valeur, ligne, 2)
        self._corps.addLayout(grille)

        if len(sessions) > _JOURNAL_MAX:
            self._corps.addWidget(_Paragraphe(
                tr("… et {} parties plus anciennes, conservées dans le journal.")
                .format(len(sessions) - _JOURNAL_MAX)))

        herite = sum(self._hist.herite.values())
        if herite:
            # Sans cette ligne, la somme du journal ne colle pas avec le total
            # de l'en-tête, et quelqu'un qui le remarque cesse de faire
            # confiance à toute la page. On le dit donc, avec ce qu'on ignore.
            self._corps.addWidget(_Paragraphe(
                tr("Avant la mise en service du journal : {}, sans le détail "
                   "des parties.").format(format_duree_compacte(herite))))
        return True

    def _titre_section(self, texte: str) -> None:
        lbl = QLabel(texte.upper())
        lbl.setObjectName("titreSection")
        lbl.setTextFormat(Qt.TextFormat.PlainText)
        self._corps.addWidget(lbl)
