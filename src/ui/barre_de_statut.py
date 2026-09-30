"""La barre de statut : le message ambiant, et ce qui a le droit de le remplacer.

Extrait de `main_window` (plafond de lignes) : ces quatre messages ne lisaient
de la fenêtre que la config, l'état des opérations et l'état réseau — donc
rien qui justifiait de construire toute la fenêtre pour les tester.

Règle commune : un téléchargement de jeu en cours a la priorité. Son statut
n'est jamais écrasé par un message d'ambiance ou de bandes-annonces.
"""

from PyQt6.QtWidgets import QStatusBar

from src.core import almanach
from src.core.i18n import tr


class BarreDeStatut(QStatusBar):
    def __init__(self, config, ops, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._ops = ops
        self.showMessage(self.au_repos())

    def au_repos(self) -> str:
        """Ce que dit la barre quand il n'y a RIEN à signaler.

        « Prêt » est un état normal, et le projet s'interdit d'en afficher
        partout ailleurs : ça n'apprenait rien à personne tout en occupant
        cette ligne en permanence. Le fait du jour prend donc sa place — il
        n'ajoute aucun pixel, et il s'efface de lui-même dès qu'un vrai
        message arrive, puisque ce message le remplace. C'est ce qui le rend
        non intrusif : il n'interrompt jamais rien, il occupe un silence.

        Désactivable (`config.faits_du_jour`) ; on retombe alors sur « Prêt ».
        """
        if self._config.faits_du_jour:
            fait = almanach.fait_du_jour()
            if fait:
                return tr(fait)
        return tr("Prêt")

    def ambiance(self, mises_a_jour: int, en_ligne: bool) -> None:
        """Message ambiant : mises à jour, hors ligne, ou le repos."""
        if self._ops.is_busy:
            return  # ne pas écraser le statut d'un téléchargement en cours
        if mises_a_jour > 0:
            self.showMessage(tr("{} mise(s) à jour disponible(s)").format(mises_a_jour))
        elif not en_ligne:
            # Dire ce qui change vraiment pour l'utilisateur : sa bibliothèque
            # reste jouable, seuls les nouveaux téléchargements attendent.
            self.showMessage(tr("Hors ligne — les jeux installés restent jouables."))
        else:
            self.showMessage(self.au_repos())

    def bandes_annonces(self, faites: int, total: int, octets: int, total_octets: int) -> None:
        """Bandes-annonces : le dire ici, pas dans la barre de téléchargement (le
        parcours « 1/4 → 4/4 » ne veut rien dire pour un fichier qui ne
        s'installe pas). N'en laisser la trace que dans les Paramètres revenait
        à tirer des centaines de Mo sans le dire (Ludo, 2026-09-23)."""
        if self._ops.is_busy:
            return
        pct = round(octets * 100 / total_octets) if total_octets > 0 else 0
        self.showMessage(tr("Bandes-annonces : {n}/{total} ({pct} %)").format(
            n=min(faites + 1, total), total=total, pct=pct))

    def bandes_annonces_finies(self, *_args) -> None:
        if not self._ops.is_busy:
            self.showMessage(self.au_repos())
