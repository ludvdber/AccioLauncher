"""La section « Succès » au bas du folio (`folio_page.py`), et le toast du retour de partie.

Une rangée de médailles (`medailles.py`) : celles qu'on a obtenues d'abord,
dans l'ordre du jeu, puis celles qui restent, en creux. Le nom, ce qu'elle
demande et la date de la partie où elle est tombée passent en bulle ; une date
inconnue (déjà là au premier regard, `succes.py`) ne s'affiche pas : rien
n'est deviné. Le détail vit dans les Défis du Carnet (`defis_page.py`).
"""

from collections.abc import Callable
from datetime import datetime

from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from src.core import succes
from src.core.catalogue_blocs import Sauvegardes
from src.core.i18n import tr
from src.ui.stats_widgets import _Paragraphe, _titre_section
from src.ui.toast import Toast

_PETITE = 44


def annonce_succes(nom_du_jeu: str, obtenus: list[succes.Succes]) -> str:
    """Le texte du toast au retour de partie (`MainWindow._on_game_exited`). Le
    toast ne passe pas à la ligne seul : deux lignes, trois titres au plus."""
    if len(obtenus) == 1:
        return (tr("Succès dans {} : {}").format(nom_du_jeu, tr(obtenus[0].titre))
                + "\n" + tr(obtenus[0].description))
    titres = ", ".join(tr(s.titre) for s in obtenus[:3])
    if len(obtenus) > 3:
        titres += " " + tr("et {} autres").format(len(obtenus) - 3)
    return tr("{} succès dans {} :").format(len(obtenus), nom_du_jeu) + "\n" + titres


def annoncer_succes(toast: Toast, nom_du_jeu: str, obtenus: list[succes.Succes] | bool,
                    ouvrir: Callable[[], None]) -> bool:
    """Le toast des succès de la partie qui vient de finir ; vrai s'il y en avait.
    Un clic ouvre le Folio du Carnet sur le dernier jeu joué : celui-ci. La
    fenêtre passe `partie and succes_obtenus` : faux quand le jeu n'a pas démarré."""
    if not obtenus or obtenus is True:
        return False
    toast.show_message(annonce_succes(nom_du_jeu, obtenus), duration_ms=9000, on_click=ouvrir)
    return True


def _jour(quand: datetime | None) -> str:
    """En toutes lettres, dans la langue de l'interface (« 24/10/2026 »
    imposait l'ordre français)."""
    if quand is None:
        return ""
    from src.ui.versions_dialog import date_longue
    return date_longue(quand.strftime("%Y-%m-%d"))


class SectionSucces(QWidget):
    """Titre, compte, puis une rangée de médailles : obtenues d'abord.

    Le détail (ce que chacune demande) vit dans la rubrique Défis du Carnet
    (`defis_page.py`, 2026-10-26) ; ici, le nom et la date passent en bulle.
    """

    def __init__(self, jeu: str, sauvegardes: list[str], spec: Sauvegardes | None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from src.ui.flow_layout import FlowLayout
        from src.ui.medailles import pixmap_medaille
        definitions = succes.du_jeu(jeu)
        self.obtenus = succes.obtenus(jeu, sauvegardes, spec)
        couche = QVBoxLayout(self)
        couche.setContentsMargins(0, 0, 0, 0)
        couche.setSpacing(8)
        couche.addWidget(_titre_section(tr("Succès")))
        couche.addWidget(_Paragraphe(
            tr("{} sur {}").format(len(self.obtenus), len(definitions)), taille=13))
        rangee = QWidget()
        flux = FlowLayout(rangee, spacing=6)
        flux.setContentsMargins(0, 4, 0, 0)
        ordre = ([s for s in definitions if s.ident in self.obtenus]
                 + [s for s in definitions if s.ident not in self.obtenus])
        self.lignes: list[str] = []
        self.bulles: list[str] = []
        for s in ordre:
            obtenu = self.obtenus.get(s.ident)
            image = QLabel()
            image.setFixedSize(_PETITE, _PETITE)
            image.setPixmap(pixmap_medaille(jeu, s.ident, obtenu is not None, _PETITE,
                                            self.devicePixelRatioF()))
            bulle = tr(s.titre) + "\n" + tr(s.description)
            quand = _jour(obtenu.date) if obtenu is not None else ""
            if quand:
                bulle += "\n" + quand
            image.setToolTip(bulle)
            flux.addWidget(image)
            self.lignes.append(s.ident)
            self.bulles.append(bulle)
        couche.addWidget(rangee)
