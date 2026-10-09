"""« Que faire ? » : protéger le dossier des jeux de l'antivirus.

Ouverte par le lien du bandeau quand le catalogue nomme l'aide `antivirus`
(HP7 partie 2, dont Paul.dll part en quarantaine). L'ancienne mise en garde
disait « restaurez ce fichier depuis la quarantaine » : un remède après coup,
à refaire après chaque réinstallation. Une exclusion du dossier des jeux règle
la question une fois pour toutes, et pour les huit jeux (refonte du 2026-10-09,
maquette « piste A, HP8 »).

Les étapes nomment les menus de Sécurité Windows. Sous Linux, pas de bouton
« Ouvrir Sécurité Windows » : la phrase générale suffit.
"""

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from src.core.i18n import tr
from src.core.liens import SECURITE_WINDOWS_URL
from src.ui.alert_banner import WARN
from src.ui.fonts import body_font, cinzel
from src.ui.utils import open_url


def _etape(numero: int, texte: str) -> QWidget:
    ligne = QWidget()
    boite = QHBoxLayout(ligne)
    boite.setContentsMargins(0, 0, 0, 0)
    boite.setSpacing(10)
    pastille = QLabel(str(numero))
    pastille.setObjectName("pastilleEtape")
    pastille.setFixedSize(22, 22)
    pastille.setAlignment(Qt.AlignmentFlag.AlignCenter)
    pastille.setFont(cinzel(9, bold=True))
    boite.addWidget(pastille, 0, Qt.AlignmentFlag.AlignTop)
    corps = QLabel(texte)
    corps.setTextFormat(Qt.TextFormat.RichText)
    corps.setWordWrap(True)
    corps.setFont(body_font(13))
    boite.addWidget(corps, 1)
    return ligne


class AideAntivirus(QDialog):
    """Trois étapes, le chemin à copier, et le bouton qui ouvre le bon écran."""

    def __init__(self, dossier: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Protéger le dossier des jeux"))
        self.setMinimumWidth(460)
        self.setStyleSheet(
            "QDialog { background: #11111f; }"
            "QLabel { color: #d4d1e3; background: transparent; }"
            f"QLabel#pastilleEtape {{ color: {WARN}; background: rgba(232,149,90,0.16);"
            " border-radius: 11px; }"
            "QLabel#chemin { color: #e4e2ef; background: #0a0a16;"
            " border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; padding: 6px 10px; }"
            "QPushButton { color: #ecdcb0; background: rgba(255,255,255,0.05);"
            " border: 1px solid rgba(255,255,255,0.18); border-radius: 6px; padding: 6px 12px; }"
            "QPushButton:hover, QPushButton:focus { border-color: #ecdcb0; }"
            f"QPushButton#ouvrirSecurite {{ color: #1a1206; background: {WARN}; border: none;"
            " font-weight: bold; padding: 8px 16px; }"
            "QPushButton#ouvrirSecurite:hover, QPushButton#ouvrirSecurite:focus"
            " { background: #f0ad7a; }"
        )
        self._dossier = str(dossier)

        racine = QVBoxLayout(self)
        racine.setContentsMargins(22, 20, 22, 18)
        racine.setSpacing(14)

        titre = QLabel(tr("Protéger le dossier des jeux"))
        titre.setFont(cinzel(12, bold=True))
        titre.setStyleSheet("color: #f2e6c4;")
        racine.addWidget(titre)

        intro = QLabel(tr(
            "Certains antivirus mettent Paul.dll en quarantaine : l'installation "
            "se termine, puis le jeu ne démarre pas. Une exclusion pour le dossier "
            "des jeux règle la question une fois pour toutes, et vaut aussi pour "
            "les autres jeux."))
        intro.setWordWrap(True)
        intro.setFont(body_font(13))
        racine.addWidget(intro)

        gras = '<b style="color:#f2f2f4">{}</b>'
        racine.addWidget(_etape(1, tr("Ouvrez Sécurité Windows, puis {}.").format(
            gras.format(tr("Protection contre les virus et menaces")))))
        racine.addWidget(_etape(2, tr("{}, puis {}, {}, {}.").format(
            gras.format(tr("Gérer les paramètres")), gras.format(tr("Exclusions")),
            gras.format(tr("Ajouter une exclusion")), gras.format(tr("Dossier")))))
        racine.addWidget(_etape(3, tr("Choisissez le dossier des jeux :")))

        ligne_chemin = QHBoxLayout()
        ligne_chemin.setContentsMargins(32, 0, 0, 0)
        ligne_chemin.setSpacing(10)
        self._chemin = QLabel(self._dossier)
        self._chemin.setObjectName("chemin")
        self._chemin.setTextFormat(Qt.TextFormat.PlainText)
        self._chemin.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._chemin.setFont(body_font(12))
        self._chemin.setWordWrap(True)
        ligne_chemin.addWidget(self._chemin, 1)
        self._copier = QPushButton(tr("Copier"))
        self._copier.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copier.clicked.connect(self._copier_chemin)
        ligne_chemin.addWidget(self._copier)
        racine.addLayout(ligne_chemin)

        bas = QHBoxLayout()
        bas.setSpacing(14)
        self._ouvrir = None
        if sys.platform == "win32":
            self._ouvrir = QPushButton(tr("Ouvrir Sécurité Windows"))
            self._ouvrir.setObjectName("ouvrirSecurite")
            self._ouvrir.setCursor(Qt.CursorShape.PointingHandCursor)
            self._ouvrir.clicked.connect(lambda: open_url(SECURITE_WINDOWS_URL))
            bas.addWidget(self._ouvrir)
        autre = QLabel(tr("Un autre antivirus ? Même idée : une exclusion pour ce dossier."))
        autre.setWordWrap(True)
        autre.setFont(body_font(12))
        autre.setStyleSheet("color: #8f8db0;")
        bas.addWidget(autre, 1)
        racine.addLayout(bas)

        fermer = QPushButton(tr("Fermer"))
        fermer.setCursor(Qt.CursorShape.PointingHandCursor)
        fermer.clicked.connect(self.accept)
        racine.addWidget(fermer, 0, Qt.AlignmentFlag.AlignRight)

    def _copier_chemin(self) -> None:
        QGuiApplication.clipboard().setText(self._dossier)
        # Sans coche : U+2713 part en repli de police (règle 59).
        self._copier.setText(tr("Copié"))
