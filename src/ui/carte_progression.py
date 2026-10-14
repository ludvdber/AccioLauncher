"""La fiche d'un jeu PENDANT son téléchargement et son installation (2026-10-09).

Avant : une barre de 400 px avec « 42% » écrit en blanc sur l'or, une ligne
grise de tirets (« 42% — 1,2 Go / 2,8 Go — 17,6 Mo/s — ~1 min restantes »)
et un « Annuler » sans cadre, perdu à droite ; à l'installation, le texte de
la barre chevauchait son remplissage. La carte dit les mêmes choses, chacune
à sa place :

- l'étape, combien il en reste (« Étape 1 sur 4 · Téléchargement »), et le
  pourcentage à droite ;
- une barre fine, sans rien écrit dessus ;
- le volume, la vitesse et le temps restant, puis « Annuler » en vrai bouton.

Les chiffres viennent de `morceaux_de_progression`, comme ceux de la barre du
bas : les deux ne peuvent pas se contredire (règle 97).
"""

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.core.formatting import morceaux_de_progression
from src.core.i18n import tr
from src.ui.composants import ENCRE_DOUCE, bouton, feuille_de_style, police, texte
from src.ui.fonts import cinzel
from src.ui.theme import accent_qcolor, themed

# Les phases de `GameOperations`, dans l'ordre du parcours.
ETAPES = ("download", "verify", "install", "finalize")
_SANS_CHIFFRE = ("verify", "finalize")
_LARGEUR = 460


def _libelle(phase: str) -> str:
    return {"download": tr("Téléchargement"), "verify": tr("Vérification"),
            "install": tr("Installation"), "finalize": tr("Finalisation")}[phase]


class _Barre(QWidget):
    """Barre fine, peinte : le remplissage seul, aucun texte dessus.

    Sans chiffre (vérification, finalisation), elle reste pleine et pâle :
    une barre immobile à un pourcentage faux serait pire qu'aucune.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(8)
        self.valeur = 0
        self.sans_chiffre = False

    def regler(self, valeur: int, sans_chiffre: bool = False) -> None:
        self.valeur = max(0, min(100, valeur))
        self.sans_chiffre = sans_chiffre
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        rect = QRectF(self.rect())
        p.setBrush(QColor(255, 255, 255, 22))
        p.drawRoundedRect(rect, 4, 4)
        if self.sans_chiffre:
            p.setBrush(accent_qcolor(70))
            p.drawRoundedRect(rect, 4, 4)
        elif self.valeur:
            p.setBrush(accent_qcolor())
            p.drawRoundedRect(QRectF(0, 0, max(8.0, rect.width() * self.valeur / 100), rect.height()), 4, 4)
        p.end()


class CarteProgression(QWidget):
    """Ce que fait le launcher pour ce jeu, tant qu'il le télécharge ou l'installe."""

    annuler = pyqtSignal()

    def __init__(self, phase: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(themed("QLabel#etape { color: #d6a72c; background: transparent; }")
                           + feuille_de_style())
        self.setMaximumWidth(_LARGEUR)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 8)
        lay.setSpacing(0)

        # Trois lignes, pas plus : la carte prend la place du bouton JOUER, et
        # la fiche ne doit pas se mettre à défiler à la taille minimale.
        tete = QHBoxLayout()
        tete.setSpacing(12)
        self._etape = QLabel()
        self._etape.setObjectName("etape")
        f = cinzel(8, bold=True)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.4)
        self._etape.setFont(f)
        tete.addWidget(self._etape, alignment=Qt.AlignmentFlag.AlignBottom)
        tete.addStretch()
        self.pourcentage = QLabel()
        self.pourcentage.setFont(police(18, gras=True))
        self.pourcentage.setStyleSheet("color: #f4f2f8; background: transparent;")
        tete.addWidget(self.pourcentage, alignment=Qt.AlignmentFlag.AlignBottom)
        lay.addLayout(tete)
        lay.addSpacing(6)
        self._barre = _Barre()
        lay.addWidget(self._barre)
        lay.addSpacing(8)

        pied = QHBoxLayout()
        pied.setSpacing(12)
        self.detail = texte("", 13, ENCRE_DOUCE)
        self.detail.setMinimumWidth(1)
        pied.addWidget(self.detail, stretch=1)
        self.bouton_annuler = bouton(tr("Annuler"))
        self.bouton_annuler.setAccessibleName(tr("Annuler le téléchargement"))
        self.bouton_annuler.clicked.connect(self.annuler)
        pied.addWidget(self.bouton_annuler)
        lay.addLayout(pied)
        self._partie = ""
        self.regler_phase(phase)

    def regler_phase(self, phase: str) -> None:
        if phase not in ETAPES:
            return
        self.phase = phase
        rang = ETAPES.index(phase)
        self._etape.setText(tr("Étape {n} sur {total} · {etape}").format(
            n=rang + 1, total=len(ETAPES), etape=_libelle(phase)).upper())
        # Annuler ne vaut que tant que rien n'est extrait : une installation
        # arrêtée en route laisserait un jeu à moitié posé.
        self.bouton_annuler.setVisible(phase in ("download", "verify"))
        if phase in _SANS_CHIFFRE:
            self.pourcentage.setText("")
            self.detail.setText(tr("Vérification de l'archive…") if phase == "verify"
                                else tr("Finalisation de l'installation…"))
            self._barre.regler(100, sans_chiffre=True)
            return
        self.pourcentage.setText(tr("{} %").format(0))
        self._barre.regler(0)
        if phase == "install":
            self.detail.setText(tr("Extraction des fichiers. Le jeu sera prêt à jouer juste après."))

    def regler_telechargement(self, recu: int, total: int, vitesse: float, reste: float) -> None:
        if total <= 0:
            return
        if self.phase != "download":
            self.regler_phase("download")
        pct, fait, attendu, debit, temps = morceaux_de_progression(recu, total, vitesse, reste)
        self.pourcentage.setText(tr("{} %").format(pct))
        volume = tr("{fait} sur {attendu}").format(fait=fait, attendu=attendu)
        self.detail.setText(" · ".join(m for m in (volume, debit, temps, self._partie) if m))
        self._barre.regler(pct)

    def regler_parties(self, courante: int, total: int) -> None:
        self._partie = tr("partie {n} sur {total}").format(n=courante, total=total) if total > 1 else ""

    def regler_installation(self, pct: int) -> None:
        if self.phase != "install":
            self.phase = "install"
            self.regler_phase("install")
        self.pourcentage.setText(tr("{} %").format(pct))
        self._barre.regler(pct)
