"""La saga — ce que le launcher a observé de vos parties.

**Refondue le 2026-10-09** sur la maquette « Mes années » validée par Ludo
(relevé de scolarité), après la version « l'étagère » du 2026-09-19 :

· **le relevé** (`stats_releve.py`) — une ligne par jeu sous son année, l'année
  VII en deux lignes reliées, une section « hors des cours » pour un jeu sans
  année. Toujours huit lignes : c'est le squelette, il ne dépend pas des
  données. On y CHOISIT un jeu ;
· **les sauvegardes du jeu choisi** en cartes : commencée quand, écrite pour la
  dernière fois quand, combien de parties, combien de temps. Les chiffres
  viennent de `src/core/sauvegardes.py` ;
· **la colonne de la saga** — le total, l'année, le mois, la plus longue
  partie avec sa date — et **les douze derniers mois** en barres.

Ce qui ne revient pas, pour les raisons écrites dans la version précédente :
la série de jours, le jour et la plage
horaire de prédilection, les démarrages du launcher et les octets téléchargés.
Et **aucun zéro** : une ligne sans valeur ne s'affiche pas, une sauvegarde
dont on n'a vu aucune partie dit « — » et pourquoi, jamais une estimation.
"""

from datetime import date

from PyQt6.QtCore import QLocale, Qt
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

from src.core import sauvegardes, scolarite, stats
from src.core.game_manager import GameManager, GameState
from src.core.i18n import tr
from src.ui.ecu import emaux
from src.ui.stats_releve import _Releve
from src.ui.fonts import cinzel
from src.ui.theme import current as theme_courant, themed
from src.ui.stats_widgets import (  # noqa: F401  (réexportés)
    _SECONDAIRE,
    _DISCRET,
    _HISTO_H,
    _COLONNE_SAGA,
    _HAUTEUR_MAX,
    _MARGE_ECRAN,
    _hauteur_max,
    _duree_courte,
    _minutes,
    _duree,
    _date,
    _locale,
    _texte,
    _chiffre,
    _titre_section,
    _Paragraphe,
    _Mois,
    _Jauge,
    _CarteSauvegarde,
)


# Colonne de droite (saga, douze mois) : à 250 px, les noms des mois
# s'élidaient en « n… d… j… ».
_COLONNE_DROITE = 310


class StatsDialog(QDialog):
    """La saga : l'étagère, la fiche du jeu choisi, la saga, les mois."""

    def __init__(self, manager: GameManager, parent=None) -> None:
        super().__init__(parent)
        self.manager = manager
        self._hist = stats.charger()
        # Les dérivées dont vit toute la page, calculées UNE fois.
        self._entrees = manager.get_games()
        self._noms = {e.game.id: e.game.name for e in self._entrees}
        self._etats = {e.game.id: e.state for e in self._entrees}
        self._temps = stats.temps_par_jeu(self._hist)
        self._parties = stats.parties_par_jeu(self._hist)
        self._dernieres = stats.derniere_par_jeu(self._hist)
        stock = sauvegardes.charger()
        self._sans_sauvegarde = {e.game.id: sauvegardes.temps_sans_sauvegarde(e.game.id, stock)
                                 for e in self._entrees}
        self._vues = {e.game.id: sauvegardes.vues(e.game.id, e.game.sauvegardes, stock)
                      for e in self._entrees}
        self.setWindowTitle(tr("Mes années à Poudlard"))
        # Assez LARGE pour que huit jaquettes restent des images et non des
        # timbres. Pas de plancher en HAUTEUR : la page se rétrécit à son
        # contenu.
        self.setMinimumWidth(1080)
        self._zone: QScrollArea | None = None
        self._contenu: QWidget | None = None
        self._releve: _Releve | None = None
        self._fiche_hote: QVBoxLayout | None = None
        self._fiche: QWidget | None = None
        self._ajuste = False
        self.resize(1200, 760)
        self.setStyleSheet(themed(self._style()))
        self._build()

    def _style(self) -> str:
        return """
        QDialog { background-color: #0d0d1a; color: #ffffff; }
        QLabel { color: #ffffff; background: transparent; }
        QLabel#titreSection {
            font-size: 11px; font-weight: bold; color: #d6a72c;
            letter-spacing: 1px;
        }
        QFrame#carteSave {
            background-color: #16213e; border: 1px solid #2c3e6b;
            border-radius: 8px;
        }
        QFrame#colonneSaga { border: none; border-left: 1px solid #2c3e6b; }
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

    # ──────────────────── Données ────────────────────

    def _selectionnables(self) -> set[str]:
        """Un jeu se choisit s'il a quelque chose à dire : du temps, ou des
        sauvegardes sur le disque."""
        return {gid for gid in self._noms
                if self._temps.get(gid) or self._vues.get(gid)}

    def _choix_initial(self, possibles: set[str]) -> str | None:
        """Le dernier jeu JOUÉ, sinon le plus joué, sinon le premier qui a des
        sauvegardes — l'ordre de ce qu'on a envie de revoir en ouvrant."""
        if self._dernieres:
            return max(self._dernieres, key=self._dernieres.get)
        if self._temps:
            return max(self._temps, key=self._temps.get)
        for e in self._entrees:
            if e.game.id in possibles:
                return e.game.id
        return None

    def _legendes(self) -> dict[str, str]:
        legendes = {}
        for gid in self._noms:
            if self._temps.get(gid):
                legendes[gid] = _duree_courte(self._temps[gid])
            elif self._vues.get(gid):
                # Des sauvegardes, mais aucune partie chronométrée : le temps
                # n'est pas connu, et on ne l'invente pas. Le tiret est la
                # même convention que partout ailleurs sur la page.
                legendes[gid] = "—"
        return legendes

    # ──────────────────── Construction ────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 18, 26, 16)
        root.setSpacing(12)

        tete = QVBoxLayout()
        tete.setSpacing(6)
        surtitre = QLabel(tr("Relevé de scolarité").upper())
        surtitre.setFont(cinzel(8, bold=True))
        surtitre.setStyleSheet(f"color: {theme_courant().accent}; letter-spacing: 4px;")
        tete.addWidget(surtitre)
        titre = QLabel(tr("Mes années à Poudlard"))
        titre.setFont(cinzel(18, bold=True))
        tete.addWidget(titre)
        # Sous le titre : la maison et l'avancée (refonte du 2026-10-09). La
        # phrase vivait dans la barre du haut, où elle ne tenait plus à côté
        # des onglets ; ici, c'est la page de la scolarité.
        liste = self._annees()
        entete = self._phrase_entete(theme_courant(), liste)
        if entete:
            tete.addWidget(_texte(entete, 13, theme_courant().accent))
        root.addLayout(tete)
        # Le résumé ne s'écrit en tête que lorsque la page n'a RIEN d'autre à
        # dire : dès qu'il y a du temps, la colonne de la saga porte le même
        # total, et le dire deux fois (Ludo, capture du 2026-09-19) fait
        # chercher la différence entre les deux.
        ouverture = self._ouverture()
        if ouverture:
            root.addWidget(_texte(ouverture, 13, _SECONDAIRE))

        possibles = self._selectionnables()
        # Le relevé est HORS de la zone défilante : c'est le squelette de la
        # page, il ne doit jamais partir sous la ligne de flottaison.
        self._releve = _Releve(self._entrees, self._temps, self._parties, self._dernieres,
                               self._legendes(), possibles, self._choix_initial(possibles))
        self._releve.choisi.connect(self._montrer_jeu)
        haut = QHBoxLayout()
        haut.setSpacing(28)
        gauche = QVBoxLayout()
        gauche.setSpacing(10)
        gauche.addWidget(self._releve)
        courante = scolarite.annee_courante(liste)
        if courante:
            gauche.addWidget(_Paragraphe(self._phrase_scolarite(liste, courante)))
        gauche.addStretch(1)
        haut.addLayout(gauche, 1)

        # À droite, ce qui parle de TOUTE la saga : le total et les mois.
        if stats.temps_total(self._hist):
            droite = QVBoxLayout()
            droite.setSpacing(22)
            saga = self._colonne_saga()
            saga.setFixedWidth(_COLONNE_DROITE)
            droite.addWidget(saga)
            cases = stats.douze_mois(self._hist)
            if any(s for _, _, s in cases):
                bloc = QVBoxLayout()
                bloc.setSpacing(8)
                bloc.addWidget(_titre_section(tr("Les douze derniers mois")))
                mois = _Mois(cases)
                mois.setFixedWidth(_COLONNE_DROITE)
                bloc.addWidget(mois)
                droite.addLayout(bloc)
            droite.addStretch(1)
            haut.addLayout(droite)
        root.addLayout(haut)

        if possibles:
            # Dessous, les sauvegardes du jeu choisi : seule partie qui défile.
            contenu = QWidget()
            corps = QVBoxLayout(contenu)
            corps.setContentsMargins(0, 4, 8, 4)
            corps.setSpacing(12)
            self._fiche_hote = QVBoxLayout()
            self._fiche_hote.setContentsMargins(0, 0, 0, 0)
            corps.addLayout(self._fiche_hote)
            if self._releve.choix is not None:
                self._montrer_jeu(self._releve.choix)
            corps.addStretch(1)

            zone = QScrollArea()
            zone.setWidgetResizable(True)
            zone.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            zone.setWidget(contenu)
            # Sous son `minimumSizeHint` (~70 px), la zone ne descendait pas :
            # une fiche courte laissait 15 px de vide au bas de la page. Un
            # minimum EXPLICITE le remplace ; la hauteur vient d'_ajuster_hauteur.
            zone.setMinimumHeight(1)
            root.addWidget(zone, 1)
            self._zone, self._contenu = zone, contenu

        bas = QHBoxLayout()
        bas.addStretch(1)
        fermer = QPushButton(tr("Fermer"))
        fermer.setObjectName("btnClose")
        fermer.setCursor(Qt.CursorShape.PointingHandCursor)
        fermer.clicked.connect(self.accept)
        bas.addWidget(fermer)
        root.addLayout(bas)

    def _ouverture(self) -> str:
        """La phrase d'en-tête des pages VIDES ; chaîne vide dès qu'il y a du
        temps, que la colonne de la saga dit mieux."""
        if sum(self._temps.values()):
            return ""
        if any(self._vues.values()):
            return tr("Vos sauvegardes sont là ; le temps de jeu se comptera "
                      "à partir de votre prochaine partie.")
        return tr("Aucune partie enregistrée pour l'instant — "
                  "lancez un jeu, cette page se remplira toute seule.")

    def _annees(self):
        return scolarite.annees(
            [e.game for e in self._entrees],
            lambda gid: self._etats.get(gid) is GameState.INSTALLED,
            lambda gid: self._temps.get(gid, 0))

    @staticmethod
    def _phrase_entete(palette, liste) -> str:
        """« Élève de Serdaigle · 5 années commencées sur 7 ».

        Chaque moitié n'apparaît que si elle dit quelque chose : pas de maison
        sous le thème Poudlard, pas de compte tant qu'aucune année n'a commencé
        (« 0 année commencée » serait un état normal affiché, règle 107).
        """
        morceaux = []
        if emaux(palette.id) is not None:
            morceaux.append(tr("Élève de {}").format(tr(palette.nom)))
        commencees = sum(1 for a in liste if a.statut is scolarite.Statut.COMMENCEE)
        if commencees == 1:
            morceaux.append(tr("1 année commencée sur {}").format(scolarite.ANNEES))
        elif commencees > 1:
            morceaux.append(tr("{} années commencées sur {}").format(
                commencees, scolarite.ANNEES))
        return "  ·  ".join(morceaux)

    @staticmethod
    def _phrase_scolarite(liste, courante: int) -> str:
        """« Vous êtes en 5ᵉ année. La 6ᵉ année vous attend. »

        Deux suites possibles, et une seule à la fois. **Ce qui ATTEND est
        devant** : la première année non commencée au-delà de celle où l'on
        est. Quand il n'y a plus rien devant mais qu'on a sauté des années en
        chemin, on ne dit pas qu'elles « attendent » — on dit combien il en
        reste, et la bande juste au-dessus montre lesquelles. « Tu es en 7ᵉ
        année. La 4ᵉ année t'attend. » était la première version, et Ludo l'a
        justement trouvée ridicule.

        L'ordinal ne se fabrique PAS en collant un suffixe au nombre : le
        français écrit « 1ʳᵉ » et non « 1ᵉ », et l'anglais comme l'espagnol
        construisent la phrase autrement. Chaque forme est donc une clé, et
        c'est le traducteur qui décide de sa langue.
        """
        phrase = (tr("Vous êtes en 1ʳᵉ année.") if courante == 1
                  else tr("Vous êtes en {}ᵉ année.").format(courante))
        suivante = scolarite.prochaine_annee(liste)
        if suivante is not None:
            phrase += " " + (
                tr("La 1ʳᵉ année vous attend.") if suivante.numero == 1
                else tr("La {}ᵉ année vous attend.").format(suivante.numero))
            return phrase
        reste = len(scolarite.restantes(liste))
        if reste == 1:
            phrase += " " + tr("Il vous reste une année à découvrir.")
        elif reste > 1:
            phrase += " " + tr("Il vous reste {} années à découvrir.").format(reste)
        return phrase

    def _colonne_saga(self) -> QWidget:
        """Toute la saga : total, année, mois, plus longue partie.

        Une ligne à zéro ne s'écrit pas : « En septembre : 0 » est une case
        vide qui apprend à ne plus lire la colonne.
        """
        cadre = QFrame()
        cadre.setObjectName("colonneSaga")
        cadre.setFixedWidth(_COLONNE_SAGA)
        couche = QVBoxLayout(cadre)
        couche.setContentsMargins(22, 0, 0, 0)
        couche.setSpacing(6)
        couche.addWidget(_titre_section(tr("Toute la saga")))

        aujourdhui = date.today()
        annee = stats.temps_annee(self._hist, aujourdhui.year)
        herite = sum(self._hist.herite.values())
        # Le total AFFICHÉ est la somme des parties AFFICHÉES, chacune arrondie
        # à la minute. Arrondir chaque ligne de son côté donnait, sur les
        # données de Ludo, « 46 min au total, dont 43 cette année et 4
        # d'avant » : 46,5 → 46, 42,9 → 43, 3,6 → 4, et 43 + 4 = 47. Un seul
        # compte qui ne tombe pas juste suffit à faire douter de toute la page.
        autres = stats.temps_total(self._hist) - annee - herite
        total = 60 * sum(_minutes(x) for x in (annee, autres, herite))
        lignes = [(tr("Au total"), total, 17)]
        mois = stats.par_mois(self._hist).get((aujourdhui.year, aujourdhui.month), 0)
        lignes.append((tr("En {}").format(aujourdhui.year), annee, 13))
        lignes.append((tr("En {}").format(_locale().standaloneMonthName(
            aujourdhui.month, QLocale.FormatType.LongFormat)), mois, 13))
        for libelle, secondes, taille in lignes:
            if not secondes:
                continue
            ligne = QHBoxLayout()
            ligne.addWidget(_texte(libelle, 12, _SECONDAIRE))
            ligne.addStretch(1)
            ligne.addWidget(_chiffre(_duree(secondes), taille,
                                     "#d6a72c" if taille > 13 else "#ffffff"))
            couche.addLayout(ligne)

        if herite:
            # Sans cette ligne, l'année et le mois ne se raccordent pas au
            # total, et quelqu'un qui le remarque cesse de croire la page.
            couche.addWidget(_Paragraphe(
                tr("Dont {} jouées avant la mise en service du journal, sans "
                   "date.").format(_duree(herite)),
                taille=11))

        longue = stats.plus_longue(self._hist)
        if longue is not None:
            couche.addSpacing(10)
            couche.addWidget(_titre_section(tr("Plus longue partie")))
            couche.addWidget(_chiffre(_duree(longue.duree), 14))
            # Jamais un record sans sa date : daté, c'est un souvenir.
            couche.addWidget(_Paragraphe(tr("{}, le {}").format(
                self._noms.get(longue.jeu, longue.jeu),
                longue.debut.strftime("%d/%m/%Y"))))
        return cadre

    def _montrer_jeu(self, game_id: str) -> None:
        """Remplace la fiche. La fenêtre ne change PAS de taille : une fenêtre
        qui saute à chaque clic sur une jaquette se lit comme un défaut ; le
        corps défile."""
        if self._fiche_hote is None:
            return
        if self._fiche is not None:
            self._fiche.hide()
            self._fiche.deleteLater()
        self._fiche = self._construire_fiche(game_id)
        self._fiche_hote.addWidget(self._fiche)

    def _construire_fiche(self, game_id: str) -> QWidget:
        fiche = QWidget()
        couche = QVBoxLayout(fiche)
        couche.setContentsMargins(0, 0, 0, 0)
        couche.setSpacing(12)
        nom = QLabel(self._noms.get(game_id, game_id))
        nom.setTextFormat(Qt.TextFormat.PlainText)
        nom.setFont(cinzel(14, bold=True))
        nom.setWordWrap(True)
        couche.addWidget(nom)

        # Temps, parties et dernière fois sont sur la ligne du relevé : la
        # fiche ne garde que ce que le relevé ne peut pas montrer.
        vues = self._vues.get(game_id) or []
        if vues:
            couche.addSpacing(4)
            couche.addWidget(_titre_section(tr("Sauvegardes")))
            if any(v.temps is None for v in vues):
                # On ne DEVINE pas le temps d'une sauvegarde née avant le
                # relevé : on dit pourquoi il manque et quand il viendra — une
                # fois pour la section, pas une fois par carte.
                couche.addWidget(_Paragraphe(
                    tr("Le temps par sauvegarde se compte à partir de votre "
                       "prochaine partie."), taille=11))
            grille = QGridLayout()
            grille.setSpacing(12)
            temps_max = max((v.temps or 0 for v in vues), default=0)
            recente = (max(vues, key=lambda v: v.modifie).fichier
                       if len(vues) > 1 else None)
            for i, vue in enumerate(vues):
                grille.addWidget(_CarteSauvegarde(vue, temps_max, vue.fichier == recente),
                                 i // 2, i % 2)
            grille.setColumnStretch(0, 1)
            grille.setColumnStretch(1, 1)
            couche.addLayout(grille)
        sans = self._sans_sauvegarde.get(game_id, 0)
        if sans >= 60:
            # Sans cette ligne, la somme des cartes est inférieure au temps du
            # jeu et rien ne dit pourquoi. Seules les parties OBSERVÉES sans
            # écriture y entrent — jamais celles d'avant le relevé.
            couche.addWidget(_Paragraphe(
                tr("Dont {} jouées sans sauvegarder.").format(
                    _duree(sans)), taille=11))
        couche.addStretch(1)
        return fiche

    # ──────────────────── Hauteur ────────────────────

    def showEvent(self, event) -> None:
        """La hauteur ne se mesure qu'une fois la page RÉELLEMENT mise en page :
        l'étagère et les paragraphes déduisent leur hauteur de la largeur
        reçue, qu'ils n'ont pas avant d'être montrés."""
        super().showEvent(event)
        if not self._ajuste:
            self._ajuste = True
            self._ajuster_hauteur()

    def _ajuster_hauteur(self) -> None:
        """La fenêtre s'arrête où le contenu s'arrête, plafonnée par l'écran.

        L'écart est mesuré sur ce qui est POSÉ, jamais sur le `sizeHint` d'une
        `QScrollArea`, qui ne porte pas la hauteur de son contenu.
        """
        self.setMinimumHeight(0)
        self.layout().activate()
        if self._zone is not None and self._contenu is not None:
            ecart = (self._contenu.sizeHint().height()
                     - self._zone.viewport().height())
        else:
            ecart = self.sizeHint().height() - self.height()
        self.resize(self.width(), min(self.height() + ecart, _hauteur_max(self)))
