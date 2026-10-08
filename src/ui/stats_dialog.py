"""La saga — ce que le launcher a observé de vos parties.

**Refondue le 2026-09-19** sur la maquette « l'étagère » choisie par Ludo,
avec le grand histogramme des mois de la maquette « le registre » :

· **l'étagère** — les huit jaquettes dans l'ordre de la saga, toujours huit.
  C'est le squelette de la page, et il ne dépend pas des données : une page
  dont la structure varie a l'air cassée bien avant d'avoir l'air pauvre
  (diagnostic de la version du 2026-08-27, qui reste vrai). On y CHOISIT un
  jeu : seuls ceux qui ont quelque chose à dire se laissent choisir ;
· **la fiche du jeu choisi** — son temps, ses parties, la dernière fois, puis
  ses SAUVEGARDES en cartes : commencée quand, écrite pour la dernière fois
  quand, combien de parties, combien de temps. C'était la demande principale ;
  les chiffres viennent de `src/core/sauvegardes.py`, qui compare les
  sauvegardes avant et après chaque partie ;
· **la colonne de la saga** — le total, l'année, le mois, la plus longue
  partie avec sa date ;
· **les douze derniers mois** en barres. Des heures, pas des pourcentages, et
  des barres, pas un camembert : ce que réclament les joueurs de Steam et de
  GOG Galaxy (audit du 2026-09-19).

Ce qui ne revient pas, pour les raisons écrites dans la version précédente :
la liste des jeux jamais lancés, la série de jours, le jour et la plage
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
from src.ui.fonts import cinzel
from src.ui.theme import themed
from src.ui.stats_widgets import (  # noqa: F401  (réexportés)
    _SECONDAIRE,
    _DISCRET,
    _FRISE_RAPPORT,
    _FRISE_LEGENDE_H,
    _FRISE_ECART,
    _FRISE_LEVEE,
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
    _Etagere,
    _Mois,
    _Jauge,
    _CarteSauvegarde,
    _Scolarite,
)


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
        self.setMinimumWidth(820)
        self._zone: QScrollArea | None = None
        self._contenu: QWidget | None = None
        self._etagere: _Etagere | None = None
        self._fiche_hote: QVBoxLayout | None = None
        self._fiche: QWidget | None = None
        self._ajuste = False
        self.resize(920, 720)
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
        root.setContentsMargins(22, 16, 22, 16)
        root.setSpacing(12)

        titre = QLabel(tr("Mes années à Poudlard"))
        titre.setFont(cinzel(18, bold=True))
        root.addWidget(titre)
        # Le résumé ne s'écrit en tête que lorsque la page n'a RIEN d'autre à
        # dire : dès qu'il y a du temps, la colonne de la saga porte le même
        # total, et le dire deux fois (Ludo, capture du 2026-09-19) fait
        # chercher la différence entre les deux.
        ouverture = self._ouverture()
        if ouverture:
            root.addWidget(_texte(ouverture, 13, _SECONDAIRE))

        possibles = self._selectionnables()
        # L'étagère est HORS de la zone défilante : c'est le squelette de la
        # page, il ne doit jamais partir sous la ligne de flottaison.
        self._etagere = _Etagere(self._entrees, self._legendes(), possibles,
                                 self._choix_initial(possibles))
        self._etagere.choisi.connect(self._montrer_jeu)
        root.addWidget(self._etagere)

        if possibles or stats.temps_total(self._hist):
            contenu = QWidget()
            corps = QVBoxLayout(contenu)
            corps.setContentsMargins(0, 8, 8, 4)
            corps.setSpacing(24)

            # Deux colonnes : à gauche le jeu choisi PUIS les douze mois, à
            # droite la saga. Posés sous la rangée, les mois tombaient sous la
            # ligne de flottaison (mesuré à 920×720 avec les données de Ludo)
            # pendant que la fiche laissait une demi-largeur vide à côté de
            # ses cartes.
            bande = self._bande_scolarite()
            if bande is not None:
                corps.addLayout(bande)

            rangee = QHBoxLayout()
            rangee.setSpacing(24)
            gauche = QVBoxLayout()
            gauche.setSpacing(24)
            self._fiche_hote = QVBoxLayout()
            self._fiche_hote.setContentsMargins(0, 0, 0, 0)
            gauche.addLayout(self._fiche_hote)
            cases = stats.douze_mois(self._hist)
            if any(s for _, _, s in cases):
                bloc = QVBoxLayout()
                bloc.setSpacing(8)
                bloc.addWidget(_titre_section(tr("Les douze derniers mois")))
                bloc.addWidget(_Mois(cases))
                gauche.addLayout(bloc)
            gauche.addStretch(1)
            rangee.addLayout(gauche, 1)
            rangee.addWidget(self._colonne_saga(), 0, Qt.AlignmentFlag.AlignTop)
            corps.addLayout(rangee)
            if self._etagere.choix is not None:
                self._montrer_jeu(self._etagere.choix)
            corps.addStretch(1)

            zone = QScrollArea()
            zone.setWidgetResizable(True)
            zone.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            zone.setWidget(contenu)
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

    def _bande_scolarite(self) -> QVBoxLayout | None:
        """Les sept années — la bande, son titre et sa phrase.

        None tant qu'AUCUNE année n'a commencé : la bande n'apprendrait alors
        rien que la phrase d'ouverture ne dise déjà, et sept cases vides sous
        « aucune partie enregistrée » sont du remplissage. Un état ne s'affiche
        que lorsqu'il dévie.
        """
        liste = scolarite.annees(
            [e.game for e in self._entrees],
            lambda gid: self._etats.get(gid) is GameState.INSTALLED,
            lambda gid: self._temps.get(gid, 0))
        courante = scolarite.annee_courante(liste)
        if courante == 0:
            return None

        bande = _Scolarite(liste, courante, self._selectionnables())
        # Cliquer une année pose son jeu dans la fiche du dessous — le même
        # geste que l'étagère, vers la même cible.
        bande.choisi.connect(self._montrer_jeu)
        bande.choisi.connect(self._etagere.choisir)
        bloc = QVBoxLayout()
        bloc.setSpacing(8)
        bloc.addWidget(_titre_section(tr("Les sept années")))
        bloc.addWidget(bande)
        bloc.addWidget(_Paragraphe(self._phrase_scolarite(liste, courante)))
        return bloc

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

        chiffres = QHBoxLayout()
        chiffres.setSpacing(28)
        temps = self._temps.get(game_id, 0)
        parties = self._parties.get(game_id, 0)
        derniere = self._dernieres.get(game_id)
        faits = []
        if temps:
            faits.append((_duree(temps), tr("de jeu")))
        if parties:
            faits.append((str(parties), tr("parties") if parties > 1 else tr("partie")))
        if derniere:
            faits.append((_date(derniere), tr("dernière fois")))
        for valeur, libelle in faits:
            col = QVBoxLayout()
            col.setSpacing(0)
            col.addWidget(_chiffre(valeur, 16))
            col.addWidget(_texte(libelle, 11, _DISCRET))
            chiffres.addLayout(col)
        if faits:
            chiffres.addStretch(1)
            couche.addLayout(chiffres)

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
