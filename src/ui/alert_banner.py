"""Bandeau d'avertissement de la fiche de jeu — rien à l'écran quand tout va bien.

Extrait d'`action_panel.py` le 2026-08-28. Ce n'est pas un découpage à la
ligne : le bandeau est le seul bloc du panneau qui MESURE — il élide sur le vrai
QLabel, réserve sa hauteur, et cette hauteur est lue de l'EXTÉRIEUR par
`GameDetailView._position_info` pour raccourcir la description d'autant. Trois
règles fines (l'ordre de blocage, l'élision à deux lignes, l'échappement du
catalogue) vivaient dispersées au milieu de la construction des boutons, avec
laquelle elles n'ont rien à voir.

La règle du projet — **un état ne s'affiche que lorsqu'il DÉVIE** — est ici tout
entière : rien ne s'affiche tant que rien ne manque.
"""

from html import escape

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import QLabel, QWidget

from src.core.formatting import format_size
from src.core.game_data import GameData
from src.core.game_manager import GameManager, GameState
from src.core.i18n import tr
from src.core.system_checks import (
    PREREQUIS, invalidate_vcredist_cache, needed_space_mb, prerequis_manquants,
)
from src.ui.utils import open_url

# Ambre-orangé : volontairement hors palette de maison. Un avertissement passé
# par `themed()` deviendrait vert chez Serpentard et bleu chez Serdaigle, où il
# ne se distinguerait plus de la décoration.
WARN = "#e8955a"
LIEN = '<a href="{}" style="color:{}; text-decoration: underline;">{}</a>'

# Plafond du bandeau, en lignes. Mesuré sur la plateforme native, vraies
# polices : les bandeaux qui tiennent à 980×660 font 33 px (une ligne) ou 54 px
# (deux) ; un troisième rang en coûte 75 et ramène la barre de défilement — le
# même prix que les deux avertissements empilés que le projet s'interdit déjà.
# Le texte de la mise en garde venant du CATALOGUE, donc de l'extérieur et sans
# repasser par une build, la mise en page ne peut pas dépendre de sa longueur :
# on élide, et « En savoir plus » porte la suite.
_MAX_LIGNES = 2

# Marge horizontale à retrancher pour mesurer : le filet vertical et son
# rembourrage sont peints À L'INTÉRIEUR du label et mangent la place du texte.
_MARGE = 24

# Noms COURTS des prérequis, pour le bandeau : il tient sur une ligne, le
# dialogue de lancement peut se permettre la formulation longue.
_NOMS_COURTS = {
    "vcredist_x86": tr("Visual C++ x86"),
    "vcredist2005_x86": tr("Visual C++ 2005 x86"),
    "vcredist2008_x86": tr("Visual C++ 2008 x86"),
}


class AlertBanner(QLabel):
    """Un seul message à la fois, par ordre de blocage, et rien sinon."""

    settings_requested = pyqtSignal()   # « Changer de dossier »

    def __init__(self, manager: GameManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._manager = manager
        # Jeu dont le bandeau parle en ce moment — le lien « En savoir plus »
        # en a besoin, et le prendre au clic plutôt qu'à l'affichage ouvrirait
        # l'URL d'un autre jeu après un changement de fiche.
        self._game: GameData | None = None
        # L'utilisateur est-il parti installer un prérequis ? Sert à ne
        # re-tester qu'à ce retour-là, et pas à chaque alt-tab.
        self._attend_prerequis = False

        self.setObjectName("actionAlert")
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        self.setStyleSheet(
            # Pas de fond plein : la bande s'étirait sur toute la largeur du
            # panneau et laissait un grand rectangle ambre vide à droite du
            # texte. Le filet vertical suffit à marquer l'avertissement.
            f"QLabel {{ color: {WARN}; background: transparent;"
            f" border-left: 3px solid {WARN};"
            " padding: 2px 0px 2px 11px; }"
        )
        self.linkActivated.connect(self._on_lien)
        self.hide()

    # ──────────────────── État lu par le panneau ────────────────────

    @property
    def prerequis_attendu(self) -> bool:
        """L'utilisateur est parti installer un paquet — re-tester à son retour."""
        return self._attend_prerequis

    def oublier_attente(self) -> None:
        """Consomme le drapeau et vide le cache de détection des runtimes."""
        self._attend_prerequis = False
        invalidate_vcredist_cache()

    def hauteur_reservee(self) -> int:
        """Hauteur occupée, 0 quand il n'y a rien à signaler.

        Le panneau d'info s'en sert pour raccourcir la description d'autant :
        cette place-là est prise, et l'ignorer ferait revenir la barre de
        défilement.
        """
        return 0 if self.isHidden() or not self.text() else self.minimumHeight()

    # ──────────────────── Choix du message ────────────────────

    def mettre_a_jour(self, game: GameData | None, state: GameState, *,
                      online: bool) -> None:
        """Recompose le bandeau. Le cache si rien ne dévie.

        UN SEUL message à la fois, par ordre de blocage. Empiler « hors ligne »
        et « espace insuffisant » coûtait 80 px sur une fenêtre de 980×660 et
        ramenait la barre de défilement que le panneau vient tout juste de
        perdre — pour un second conseil qui n'est même pas actionnable : hors
        ligne, il n'y a rien à écrire sur le disque.
        """
        self._game = game
        message = "" if game is None else self._message(game, state, online)
        if not message:
            self.hide()
            self.clear()
            return
        # Aucun pictogramme. Cinzel n'a pas de glyphe pour U+26A0 (rendu en
        # carré vide au test) : Windows part alors en repli de police, et c'est
        # exactement ce repli qui avait donné le bouton pause bleu vif. Le filet
        # ambre et la couleur du texte disent « attention » sans dépendre de la
        # police installée.
        self.setText(message)
        self.show()
        self.ajuster_hauteur()

    def _message(self, game: GameData, state: GameState, online: bool) -> str:
        """Le premier avertissement qui s'applique, du plus bloquant au moins."""
        if state == GameState.NOT_INSTALLED:
            dl = game.current_download
            if dl is not None and dl.is_available:
                if not online:
                    return tr("Hors ligne — connexion requise pour télécharger.")
                manque = self._disque(dl)
                if manque:
                    return manque
        elif state == GameState.INSTALLED:
            # Socle commun + ce que le catalogue déclare pour CE jeu. HP7 exige
            # Visual C++ 2005, un runtime distinct du 2015-2022 : annoncer le
            # mauvais aurait envoyé l'utilisateur installer un paquet qu'il a
            # peut-être déjà, sans que le jeu démarre pour autant.
            manquants = prerequis_manquants(("vcredist_x86", *game.requires))
            if manquants:
                return (
                    tr("{} manquant — requis pour lancer ce jeu.").format(
                        _NOMS_COURTS.get(manquants[0], tr("Composant Windows")))
                    + " " + LIEN.format(manquants[0], WARN, tr("Installer"))
                )
        # Dernier rang : la mise en garde que le CATALOGUE attache à ce jeu.
        # Elle cède le pas à tout ce qui précède, qui est bloquant ici et
        # maintenant, mais elle survit aux deux états qui comptent — avant le
        # téléchargement (prévenir) et une fois installé (expliquer un jeu qui
        # refuse de démarrer). Le texte vient du catalogue et non d'un `tr()` :
        # il se met à jour à distance, sans republier l'exécutable, et voyage
        # déjà traduit dans le bloc `i18n` du jeu.
        if state in (GameState.NOT_INSTALLED, GameState.INSTALLED):
            return self._catalogue(game)
        return ""

    def _disque(self, version) -> str:
        """Avertissement d'espace disque, vide si la place suffit ou est inconnue.

        Prend la VERSION et non un nombre de Mo : le besoin réel est la somme de
        l'archive et du jeu installé, et seule la version permet de retrouver le
        poids réel de l'archive. Ce chiffre doit rester identique à celui de
        `GameOperations.check_disk_space`, sinon le bandeau prévient d'un
        blocage qui n'arrive pas.
        """
        libre = self._manager.free_space_mb()
        besoin = needed_space_mb(version.size_mb,
                                 self._manager.archive_size_mb(version))
        if libre is None or libre >= besoin:
            return ""
        return (
            tr("Espace insuffisant : {} libres, il en faut environ {}.").format(
                format_size(libre), format_size(besoin))
            + " " + LIEN.format("settings", WARN, tr("Changer de dossier"))
        )

    def _catalogue(self, game: GameData) -> str:
        """Mise en garde déclarée par le catalogue pour ce jeu (vide sinon).

        Cas réel : une DLL de HP7 partie 2 est mise en quarantaine par les
        antivirus. L'installation réussit, puis le jeu ne démarre pas — et rien
        à l'écran ne relie les deux. Le dire AVANT le téléchargement était la
        demande de Ludo ; le redire une fois installé est ce qui rend le message
        utile au moment où l'utilisateur en a besoin.
        """
        texte = game.warning.strip()
        if not texte:
            return ""
        lien = ""
        if game.warning_url:
            lien = " " + LIEN.format("avertissement", WARN, tr("En savoir plus"))
        return self._elider(texte, lien)

    # ──────────────────── Mesure ────────────────────

    def _elider(self, brut: str, lien: str) -> str:
        """Ramène le bandeau à `_MAX_LIGNES` lignes (élision par la fin).

        Le texte est ÉCHAPPÉ en HTML avant d'entrer dans le bandeau. Celui-ci
        est un QLabel en `RichText` et le texte vient du CATALOGUE, c'est-à-dire
        de l'extérieur : sans échappement, n'importe quel balisage défait la
        mise en page qu'on vient de border, et un `<img src="file:///…">` lit
        un fichier LOCAL. (La justification longtemps écrite ici — « une image
        distante déclenche une requête réseau » — est FAUSSE : mesuré le
        2026-08-27 contre un serveur local, un QLabel n'a pas de gestionnaire
        réseau et n'en émet aucune. La règle ne bouge pas, son motif si.)

        L'élision porte sur le texte BRUT et l'échappement vient après : couper
        une chaîne déjà échappée trancherait une entité en deux (`&amp;` → `&am`).

        `quote=False` : guillemets et apostrophes n'ont besoin d'être échappés
        que DANS un attribut. Ici c'est du contenu d'élément — les échapper
        remplissait le bandeau de `&#x27;` (rendus correctement par Qt, vérifié,
        mais illisibles en journal comme en test).

        La mesure passe par le VRAI QLabel et non par `QFontMetrics` : le
        bandeau est en `RichText`, donc mis en page par un QTextDocument, dont
        le retour à la ligne ne suit pas celui d'un `boundingRect` en texte
        brut. Mesuré à côté : le texte élidé « tenait » en deux lignes selon
        `QFontMetrics` et s'en affichait trois. On interroge donc exactement la
        fonction qui décide de la hauteur finale, à la largeur qu'utilise
        `ajuster_hauteur` — les deux ne peuvent plus diverger.

        Le lien entre dans la mesure : il s'ajoute à la dernière ligne et c'est
        lui qui la fait déborder.
        """
        def rendu(n: int | None = None) -> str:
            morceau = brut if n is None else brut[:n].rstrip() + "…"
            return escape(morceau, quote=False) + lien

        largeur = self._largeur_utile()
        if largeur <= 40 or not brut:
            return rendu()
        avant = self.text()
        plafond = _MAX_LIGNES * QFontMetrics(self.font()).lineSpacing() + 8

        def hauteur(essai: str) -> int:
            self.setMinimumHeight(0)   # sinon heightForWidth fait cliquet
            self.setText(essai)
            return self.heightForWidth(largeur)

        try:
            if hauteur(rendu()) <= plafond:
                return rendu()
            bas, haut = 0, len(brut)
            while bas < haut:
                milieu = (bas + haut + 1) // 2
                if hauteur(rendu(milieu)) <= plafond:
                    bas = milieu
                else:
                    haut = milieu - 1
            return rendu(bas if bas else 1)
        finally:
            self.setMinimumHeight(0)
            self.setText(avant)

    def _largeur_utile(self) -> int:
        """Largeur de texte réelle — celle du PARENT, moins le filet.

        Le bandeau est étiré par son layout : sa propre largeur n'est juste
        qu'après une passe de mise en page, celle du panneau l'est tout de
        suite. On mesure donc contre le conteneur, comme le faisait le code
        d'origine.
        """
        parent = self.parentWidget()
        return (parent.width() if parent is not None else self.width()) - _MARGE

    def ajuster_hauteur(self) -> None:
        """Réserve la hauteur RÉELLE du bandeau (wordWrap ⇒ plusieurs lignes).

        `sizeHint()` d'un QLabel wordWrap est calculé à une largeur arbitraire ;
        sans hauteur minimale explicite, le panneau d'info sous-estime la place
        nécessaire et rogne le bandeau. `setMinimumHeight(0)` d'abord, sinon
        `heightForWidth` renvoie `max(minimumHeight, calculé)` et la hauteur ne
        redescend jamais (effet cliquet).
        """
        largeur = self._largeur_utile()
        if largeur <= 0 or not self.text():
            return
        self.setMinimumHeight(0)
        self.setMinimumHeight(self.heightForWidth(largeur))

    # ──────────────────── Liens ────────────────────

    def _on_lien(self, href: str) -> None:
        if href == "settings":
            self.settings_requested.emit()
        elif href == "avertissement":
            # L'URL a été validée au PARSING (https uniquement) : le catalogue
            # est distant, c'est la seule de ses chaînes qui atteigne le
            # navigateur, et elle ne doit pas pouvoir être autre chose.
            if self._game is not None and self._game.warning_url:
                open_url(self._game.warning_url)
        elif href in PREREQUIS:
            # L'utilisateur part installer le paquet : on note qu'il faudra
            # re-tester à son retour (cf. `prerequis_attendu`). Le lien porte
            # l'IDENTIFIANT du prérequis manquant, donc on ouvre la bonne page
            # même quand il y en a plusieurs possibles.
            self._attend_prerequis = True
            open_url(PREREQUIS[href][1])
