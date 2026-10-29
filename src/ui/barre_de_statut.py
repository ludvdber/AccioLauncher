"""La barre de statut : le message ambiant, et ce qui a le droit de le remplacer.

Extrait de `main_window` (plafond de lignes) : ces quatre messages ne lisaient
de la fenêtre que la config, l'état des opérations et l'état réseau — donc
rien qui justifiait de construire toute la fenêtre pour les tester.

Règle commune : un téléchargement de jeu en cours a la priorité. Son statut
n'est jamais écrasé par un message d'ambiance ou de bandes-annonces.
"""

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import QLabel, QSizePolicy, QStatusBar

from src.core import almanach
from src.core.i18n import tr
from src.ui.fonts import body_font


class BarreDeStatut(QStatusBar):
    """Le message est un VRAI libellé, et non le texte que peint QStatusBar.

    Le message natif se peint à 6 px du bord, dans la police de la feuille de
    style globale : à côté du reste, il faisait barre d'état de débogage, et
    sa première lettre touchait le bord de la fenêtre (audit UI, 2026-10-14).
    Le libellé prend la police du launcher, une marge de lecture, et s'élide
    au lieu d'élargir la fenêtre.
    """

    def __init__(self, config, ops, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._ops = ops
        self._message = ""
        self._libelle = QLabel(self)
        self._libelle.setObjectName("messageStatut")
        self._libelle.setTextFormat(Qt.TextFormat.PlainText)
        self._libelle.setFont(body_font(10))
        self._libelle.setStyleSheet(
            "QLabel { color: #8f8db0; background: transparent; padding-left: 14px; }")
        # Ignored : un message long s'élide, il ne pousse pas la fenêtre.
        self._libelle.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.addWidget(self._libelle, 1)
        self._libelle.installEventFilter(self)
        self.showMessage(self.au_repos())

    # L'interface de QStatusBar, sur le libellé.
    def showMessage(self, message: str, timeout: int = 0) -> None:  # noqa: N802
        self._message = message
        self._elider()

    def currentMessage(self) -> str:  # noqa: N802
        return self._message

    def clearMessage(self) -> None:  # noqa: N802
        self.showMessage("")

    def eventFilter(self, obj, event) -> bool:
        # La largeur du LIBELLÉ, connue après la passe de mise en page.
        if obj is self._libelle and event.type() == QEvent.Type.Resize:
            self._elider()
        return False

    def _elider(self) -> None:
        largeur = self._libelle.width() - 14
        texte = self._message
        if largeur > 0:
            texte = self._libelle.fontMetrics().elidedText(
                texte, Qt.TextElideMode.ElideRight, largeur)
        self._libelle.setText(texte)
        self._libelle.setToolTip(self._message if texte != self._message else "")

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
            self.showMessage(tr("1 mise à jour disponible") if mises_a_jour == 1
                             else tr("{} mises à jour disponibles").format(mises_a_jour))
        elif not en_ligne:
            # Dire ce qui change vraiment pour l'utilisateur : sa bibliothèque
            # reste jouable, seuls les nouveaux téléchargements attendent.
            self.showMessage(tr("Hors ligne : les téléchargements attendent la connexion."))
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
