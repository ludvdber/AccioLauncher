"""Utilitaires Qt partagés entre les widgets UI."""

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtWidgets import QLayout, QMessageBox, QScrollArea, QWidget

from src.core.config import ASSETS_DIR
from src.core.i18n import tr
from src.ui.theme import themed

_ICONE = ASSETS_DIR / "accio_launcher.ico"
# Repli hors Windows : le .ico est un format Windows, et le portage Linux est
# un objectif déclaré. Qt sait lire les deux, mais autant ne pas en dépendre.
_ICONE_REPLI = ASSETS_DIR / "accio_launcher.png"


def icone_application() -> QIcon:
    """Icône de l'application — le .ico multi-résolution en priorité.

    Il embarque les tailles 16 à 256 dessinées pour chacune : la barre des
    tâches et la fenêtre y piochent la bonne au lieu de réduire un seul PNG,
    ce qui rend les petites tailles nettement plus nettes. Repli sur le PNG si
    le .ico manque (ou hors Windows).

    Source UNIQUE : `main.py` la pose sur l'application entière, pour que
    l'assistant de premier lancement — ouvert avant la fenêtre principale —
    ne porte plus l'icône générique de Windows.
    """
    return QIcon(str(_ICONE if _ICONE.exists() else _ICONE_REPLI))


def avertir(parent, titre: str, texte: str) -> None:
    """Constat sans question : un message, un bouton pour le congédier.

    Remplace `QMessageBox.warning(...)`, qu'aucun widget ne doit appeler
    directement — même règle que `open_url`, et pour deux raisons mesurées.

    ① Le bouton de `QMessageBox.warning` est un bouton STANDARD de Qt, traduit
    par les fichiers `qtbase_<langue>.qm` que le build écarte : il sortait donc
    en anglais quelle que soit la langue choisie dans les Paramètres. Un
    libellé passé par `tr()` vit dans `src/data/i18n/`, là où un traducteur
    bénévole peut l'atteindre et où `tests/test_i18n.py` le voit.

    ② Il est en `AutoText`, alors que ces messages interpolent des noms de jeu
    et des chemins — Qt bascule en rich text dès que le contenu y ressemble.
    """
    boite = QMessageBox(parent)
    boite.setIcon(QMessageBox.Icon.Warning)
    boite.setWindowTitle(titre)
    boite.setTextFormat(Qt.TextFormat.PlainText)
    boite.setText(texte)
    boite.addButton(tr("Fermer"), QMessageBox.ButtonRole.AcceptRole)
    boite.exec()


def clear_layout(layout: QLayout) -> None:
    """Retire et détruit tous les widgets d'un layout."""
    while layout.count():
        item = layout.takeAt(0)
        if (w := item.widget()) is not None:
            w.hide()
            w.deleteLater()


def open_url(url: str) -> None:
    """Ouvre une URL dans le navigateur par défaut. Helper unique pour tout le projet."""
    QDesktopServices.openUrl(QUrl(url))


def open_local_path(path: str) -> None:
    """Ouvre un dossier local dans l'explorateur."""
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def is_writable_dir(path) -> bool:
    """Crée le dossier si nécessaire et vérifie qu'on peut y écrire."""
    from pathlib import Path

    path = Path(path)
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".accio_write_test"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def zone_defilable(page: QWidget) -> QScrollArea:
    """Rend une page défilable UNIQUEMENT si son contenu ne tient pas.

    Partagée par l'assistant et la fenêtre de réglages d'un jeu : deux
    barres de défilement écrites deux fois finissent par diverger.

    `ScrollBarAsNeeded` ne montre la barre que lorsqu'elle sert, donc les
    écrans courts sont inchangés. Sans ça, le Choixpeau — quatre questions,
    seize réponses — débordait de la fenêtre : le texte se chevauchait, et
    agrandir d'un pixel remettait tout en place d'un coup, parce que c'est
    le redimensionnement qui déclenchait enfin la passe de mise en page
    (Ludo, 2026-09-23, capture à l'appui).

    Le fond doit être rendu transparent sur le `QScrollArea` ET sur son
    viewport : un `QAbstractScrollArea` peint son propre fond, et la page
    serait posée sur un rectangle clair au milieu du bleu nuit. Même raison
    pour la barre : sans style, c'est la barre native de Windows, grise et
    hachurée, qui apparaît au Choixpeau (vu dans l'exe le 2026-09-24). Celle
    de « Mes années à Poudlard » : bleu nuit, or au survol, sans flèches.
    """
    zone = QScrollArea()
    zone.setWidget(page)
    zone.setWidgetResizable(True)
    zone.setFrameShape(QScrollArea.Shape.NoFrame)
    zone.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    zone.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    zone.setStyleSheet(themed(
        "QScrollArea, QScrollArea > QWidget > QWidget"
        " { background: transparent; border: none; }"
        "QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }"
        "QScrollBar::handle:vertical {"
        "  background: #2c3e6b; border-radius: 5px; min-height: 30px; }"
        "QScrollBar::handle:vertical:hover { background: #d6a72c; }"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical"
        " { background: none; }"))
    zone.viewport().setAutoFillBackground(False)
    return zone
