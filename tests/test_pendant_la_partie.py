"""Pendant une partie, le launcher se fait oublier (audit du 2026-11-13).

- la question « Mise à jour disponible » ne s'ouvre plus par-dessus le jeu : elle revient au retour ;
- les fonds préchargés (≈ 106 Mo) sont rendus au jeu, et reviennent au retour ;
- les paquets des jeux lus par le Carnet et les Collections sont rendus au lancement.
Contre-épreuve : ces tests échouent sur l'ancien code.
"""

from src.core import textures_ue1
from src.ui import dialogues_fenetre
from src.ui.game_session import GameSession


class _PartieFactice:
    """Un jeu qui tourne : `poll()` ne rend rien (comme dans test_parcours)."""
    pid = 4242
    args = ["Game.exe"]

    def poll(self):
        return None


def test_la_mise_a_jour_attend_la_fin_de_la_partie(make_window, monkeypatch):
    win = make_window()
    questions = []
    monkeypatch.setattr(dialogues_fenetre, "proposer_mise_a_jour",
                        lambda *a, **k: questions.append(a) or False)
    win._updates.version = "9.9.9"
    monkeypatch.setattr(GameSession, "nom_en_cours", property(lambda self: "HP3"))
    win._propose_launcher_update()
    assert questions == [], "posée par-dessus le jeu"
    monkeypatch.setattr(GameSession, "nom_en_cours", property(lambda self: ""))
    win._propose_launcher_update()
    assert len(questions) == 1


def test_les_fonds_precharges_sont_rendus_pendant_la_partie(make_window, monkeypatch):
    win = make_window()
    poses = []
    monkeypatch.setattr(win._detail._bg, "precharger", lambda chemins: poses.append(list(chemins)))
    win._session.demarree.emit("HP3")
    assert poses and poses[-1] == [], "les fonds restaient décodés pendant la partie"
    win._session.terminee.emit("HP3", True, False)
    assert poses[-1], "les fonds ne reviennent pas au retour"


def test_les_fonds_reviennent_des_qu_on_rouvre_le_launcher(make_window, monkeypatch, qtbot):
    """Ludo, 2026-11-15 : « libérer au lancement et reprendre dès qu'on ouvre le launcher »,
    sans attendre la fin de la partie ; et une seule relecture, pas une de plus au retour."""
    win = make_window()
    win.show()
    qtbot.waitExposed(win)
    poses = []
    monkeypatch.setattr(win._detail._bg, "precharger", lambda chemins: poses.append(list(chemins)))
    win._session.demarree.emit("HP3")
    assert poses == [[]]
    from PyQt6.QtCore import QEvent
    from PyQt6.QtWidgets import QApplication
    win.activateWindow()
    qtbot.waitUntil(win.isActiveWindow, timeout=1000)
    # L'événement est envoyé à la main : hors écran sous Linux, la fenêtre était déjà active
    # avant la partie, et `activateWindow` n'en produit aucun nouveau (CI du 2026-11-15).
    QApplication.sendEvent(win, QEvent(QEvent.Type.ActivationChange))
    assert len(poses) == 2
    assert poses[-1], "rouvert pendant la partie, le launcher restait sans ses fonds"
    win._session.terminee.emit("HP3", True, False)
    assert len(poses) == 2, "relus une seconde fois au retour"


def test_la_question_est_reposee_au_retour_sauf_apres_un_arret_fatal(make_window, monkeypatch, qtbot):
    win = make_window()
    reposees = []
    monkeypatch.setattr(win, "_propose_launcher_update", lambda: reposees.append(True))
    win._updates.version = "9.9.9"
    win._session.terminee.emit("HP3", True, True)
    qtbot.wait(10)
    assert reposees == [], "reposée par-dessus la boîte de l'arrêt fatal"
    win._session.terminee.emit("HP3", True, False)
    qtbot.waitUntil(lambda: reposees == [True], timeout=1000)


def test_les_paquets_sont_rendus_au_lancement(make_window, monkeypatch):
    win = make_window()
    rendus = []
    monkeypatch.setattr(textures_ue1, "liberer", lambda: rendus.append(True))
    try:
        win._session.demarrer(_PartieFactice(), "HP3", "hp3")
        assert rendus == [True]
    finally:
        win._session.shutdown()


def test_tous_les_caches_des_pages_sont_rendus_au_lancement(make_window, monkeypatch):
    """f113 : seuls les paquets entiers étaient rendus ; folios, jaquettes et fonds décodés
    restaient (205 Mo pendant la partie au lieu de 144)."""
    from collections import OrderedDict
    from PyQt6.QtGui import QPixmap
    from src.core import folio_hp3, folio_hp6
    from src.ui import background_widget, stats_releve
    win = make_window()
    pleins = (folio_hp3._valeurs, folio_hp3._catalogue, folio_hp3._image_menu, folio_hp6._textes_badges,
              folio_hp6._images_badges, folio_hp6._images_menu, stats_releve._jaquette_decodee)
    vides = []
    for f in pleins:
        monkeypatch.setattr(f, "cache_clear", lambda f=f: vides.append(f))
    fonds = OrderedDict((c, QPixmap()) for c in ("hp1", "hp2", "hp3"))
    monkeypatch.setattr(background_widget, "_FONDS_DECODES", fonds)
    try:
        win._session.demarrer(_PartieFactice(), "HP3", "hp3")
        assert set(map(id, vides)) == set(map(id, pleins))
        assert list(fonds) == ["hp3"], "le fond affiché reste"
    finally:
        win._session.shutdown()
