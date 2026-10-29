"""Le toast du retour de partie, et la date en toutes lettres des Défis.

La section « Succès » au bas du folio a vécu ici du 2026-10-24 au 2026-10-27 :
les Défis du Carnet (`defis_page.py`) la montraient déjà, en médailles.
"""

from collections.abc import Callable
from datetime import datetime

from src.core import succes
from src.core.i18n import tr, trn
from src.ui.toast import Toast


def annonce_succes(nom_du_jeu: str, obtenus: list[succes.Succes]) -> str:
    """Le texte du toast au retour de partie (`MainWindow._on_game_exited`). Le
    toast ne passe pas à la ligne seul : deux lignes, trois titres au plus."""
    if len(obtenus) == 1:
        return (tr("Succès dans {} : {}").format(nom_du_jeu, tr(obtenus[0].titre))
                + "\n" + tr(obtenus[0].description))
    titres = ", ".join(tr(s.titre) for s in obtenus[:3])
    if len(obtenus) > 3:
        titres += " " + trn(len(obtenus) - 3, "et {} autre", "et {} autres").format(len(obtenus) - 3)
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
