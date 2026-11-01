"""Utilitaires Qt partagés entre les widgets UI."""

from PyQt6.QtCore import QEvent, QObject, QPointF, Qt, QUrl
from PyQt6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import (
    QAbstractScrollArea, QApplication, QComboBox, QLayout, QListView, QMessageBox, QScrollArea,
    QWidget,
)

from src.core.config import ASSETS_DIR
from src.ui.theme import accent_qcolor, themed

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


def avertir(parent, titre: str, texte: str, conserve: str = "") -> None:
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
    # Ici et pas en tête : `fenetre_message` passe par `composants`, qui
    # n'a pas à charger tout `utils` pour exister.
    from src.ui.fenetre_message import message
    message(parent, QMessageBox.Icon.Warning, titre, texte, conserve=conserve)


def clear_layout(layout: QLayout) -> None:
    """Retire et détruit tous les widgets d'un layout, ceux de ses sous-layouts
    compris : retirer un sous-layout laissait ses widgets à l'écran, enfants de
    la page, à leur dernière place (fiches d'un autre jeu au Bestiaire, Ludo,
    2026-10-27)."""
    while layout.count():
        item = layout.takeAt(0)
        if (w := item.widget()) is not None:
            w.hide()
            w.deleteLater()
        elif (sous := item.layout()) is not None:
            clear_layout(sous)


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


def liste_deroulante() -> QComboBox:
    """Une QComboBox dont la liste ouverte obéit à la feuille de style.

    La vue par défaut d'une QComboBox peint ses lignes par un délégué qui ignore
    `::item:selected` : la ligne choisie au clavier ou à la manette restait du
    même bleu que les autres (mesuré sur capture, 2026-10-07 : « tout n'est pas
    mis en évidence pour la manette, surtout les dropdown »). Une QListView posée
    explicitement prend le délégué standard, qui lit la feuille de style.
    """
    liste = _ListeDeroulante()
    liste.setView(QListView(liste))
    liste.installEventFilter(_SansMolette(liste))
    return liste


class _ListeDeroulante(QComboBox):
    """Un chevron à droite : une liste se reconnaît comme telle.

    Avec une feuille de style, `::drop-down` sans `::down-arrow` ne dessine
    AUCUNE flèche : les listes des réglages et des mouvements 3D se lisaient
    comme des champs de saisie (revue des écrans, 2026-11-01). Peint ici plutôt
    qu'en `image: url()` : la feuille de style ne connaît pas l'échelle
    d'affichage ni la couleur du thème."""

    def paintEvent(self, event: QPaintEvent | None) -> None:
        super().paintEvent(event)
        if not self.isEnabled():
            couleur = QColor(111, 109, 142)
        elif self.underMouse() or self.view().isVisible():
            couleur = accent_qcolor()
        else:
            couleur = QColor(228, 226, 239, 150)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        stylo = QPen(couleur, 1.6)
        stylo.setCapStyle(Qt.PenCapStyle.RoundCap)
        stylo.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(stylo)
        cx, cy = self.width() - 14.0, self.height() / 2 + 1
        p.drawPolyline([QPointF(cx - 4, cy - 2), QPointF(cx, cy + 2), QPointF(cx + 4, cy - 2)])
        p.end()


class _SansMolette(QObject):
    """La molette fait défiler la PAGE, jamais le réglage sous le curseur.

    Une liste fermée changeait de valeur, et l'écrivait aussitôt, quand on
    faisait défiler les réglages graphiques et que le curseur passait dessus
    (Ludo, 2026-10-14 : « un scroll sans faire exprès peut tout ruiner »).
    L'événement est passé à la zone défilante qui la contient, s'il y en a une.
    """

    def eventFilter(self, objet, event) -> bool:
        if event.type() != QEvent.Type.Wheel:
            return False
        zone = objet.parentWidget()
        while zone is not None and not isinstance(zone, QAbstractScrollArea):
            zone = zone.parentWidget()
        if zone is not None:
            QApplication.sendEvent(zone.viewport(), event)
        return True


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
    # Pas un arrêt de Tab : la zone prenait le focus sans rien montrer, et à la
    # manette un appui sur ↓ semblait ne rien faire (capture du 2026-10-07).
    # Ce qu'elle contient s'atteint toujours, et la zone défile jusqu'au widget
    # qui reçoit le focus ; le stick droit et la molette la font défiler.
    zone.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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
