"""Effets animés coupés selon le PC ou le joueur (`src/core/effets.py`, audit UI f116).

Chaque effet est vérifié dans les DEUX sens : coupé quand `animes()` dit non,
présent quand il dit oui. Sans l'autre moitié, un effet jamais lancé passerait.
"""

import pytest

from src.core import diagnostic, effets

_BASIQUE = "Microsoft Microsoft Basic Display Adapter — pilote 10.0.26100.1"
_NVIDIA = "NVIDIA NVIDIA GeForce RTX 4070 — pilote 32.0.15.6094"


# ─── La règle ───

@pytest.mark.parametrize(("mode", "animations", "pilote_absent", "attendu"), [
    ("auto", True, False, True),
    ("auto", False, False, False),     # Windows a coupé ses animations
    ("auto", True, True, False),       # tout est dessiné par le processeur
    ("oui", False, True, True),        # le joueur force
    ("non", True, False, False),
    ("inconnu", True, False, True),    # config écrite à la main : comme « Selon ce PC »
])
def test_la_regle(mode, animations, pilote_absent, attendu):
    assert effets.choisir(mode, animations, pilote_absent) is attendu


def test_sans_pilote_seul_l_adaptateur_de_base():
    assert diagnostic.sans_pilote_graphique([_BASIQUE])
    assert not diagnostic.sans_pilote_graphique([_BASIQUE, _NVIDIA])   # la vraie carte compte
    assert not diagnostic.sans_pilote_graphique([_NVIDIA])
    assert not diagnostic.sans_pilote_graphique([])                    # sans savoir, on ne retire rien


def test_hors_windows_les_animations_comptent_comme_allumees(monkeypatch):
    monkeypatch.setattr(effets.sys, "platform", "linux")
    assert effets.animations_windows()


def test_decider_pose_la_session(monkeypatch):
    monkeypatch.setattr(effets, "animations_windows", lambda: False)
    assert effets.decider("auto") is False and effets.animes() is False
    assert effets.decider("oui") is True and effets.animes() is True


def test_sans_pilote_le_fond_reste_au_processeur(monkeypatch):
    from src.ui import fond_gpu
    if not fond_gpu.QUICK_DISPONIBLE or not fond_gpu._QML.exists():
        pytest.skip("Qt Quick absent")
    monkeypatch.delenv("ACCIO_FOND_GPU", raising=False)
    monkeypatch.setattr(fond_gpu.sys, "platform", "win32")
    assert fond_gpu.actif()
    monkeypatch.setattr(effets, "sans_pilote", lambda: True)
    assert not fond_gpu.actif()


# ─── Les widgets ───

pytest.importorskip("pytestqt")


@pytest.mark.parametrize("animes", [True, False])
def test_fenetre_zoom_parallaxe_particules_etoiles(make_window, monkeypatch, animes):
    from PyQt6.QtCore import QPointF
    monkeypatch.setattr(effets, "animations_windows", lambda: animes)
    win = make_window(season="halloween")   # une saison fixe : « auto » peut tomber sur « aucune »
    assert effets.animes() is animes
    assert (win._particles._season == "halloween") is animes
    detail, fond = win._detail, win._detail._bg
    fond._set_zoom_ticking(False)
    detail._apply_game(detail.game)
    assert fond._zoom_ticking is animes
    fond._set_parallax_ticking(False)
    detail.handle_mouse_move(QPointF(10, 10))
    assert fond._parallax_ticking is animes
    win._carousel.pause()
    win._carousel.resume()
    assert win._carousel._ticking is animes


@pytest.mark.parametrize("animes", [True, False])
def test_le_modele_s_arrete_au_repos_quand_les_effets_sont_coupes(qtbot, monkeypatch, animes):
    from src.core import maillages_ue1 as mu
    from src.ui import modele_3d
    monkeypatch.setattr(effets, "_animes", animes)
    monkeypatch.setattr(modele_3d, "_application_active", lambda: True)   # règle 12 : dans le module
    points = ((0.0, -10.0, 0.0), (0.0, 10.0, 0.0), (0.0, 10.0, 20.0))
    carre = mu.Maillage(points, (mu.Face((0, 1, 2), ((0.0, 1.0), (1.0, 1.0), (1.0, 0.0)), 0),),
                        (mu.Materiau("rouge", mu.PF_DEUX_FACES),))
    v = modele_3d.Modele3D()
    qtbot.addWidget(v)
    v.show()
    v.poser(carre)
    v._repos = modele_3d._ATTENTE_REPOS
    avant = v.lacet
    v._avancer()
    assert v._minuteur.isActive() is animes
    assert (v.lacet != avant) is animes
    v.mouseReleaseEvent(None)   # le lâcher d'un geste remet le minuteur en route
    assert v._minuteur.isActive()


@pytest.mark.parametrize("animes", [True, False])
def test_parametres_effets_animes(qtbot, tmp_path, monkeypatch, animes):
    from src.core.config import Config
    from src.core.game_manager import GameManager
    from src.ui.settings_panel import SettingsDialog
    monkeypatch.setattr(effets, "animations_windows", lambda: animes)
    effets.decider("auto")   # la session telle que ce PC la donne
    monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
    cfg = Config(install_path=tmp_path / "jeux", cache_path=tmp_path / "cache", langue="fr")
    dlg = SettingsDialog(cfg, GameManager(cfg))
    qtbot.addWidget(dlg)
    dlg.construire_rubrique(1)   # Son et image
    combo = dlg._effets_combo
    assert [combo.itemData(i) for i in range(combo.count())] == list(effets.MODES)
    assert combo.currentData() == "auto"
    particules = dlg._season_combo.parentWidget()
    while particules is not None and type(particules).__name__ != "LigneReglage":
        particules = particules.parentWidget()
    assert particules is not None and particules.isEnabled() is animes
    assert dlg._effets_hint.isHidden()
    # Le choix qui changerait l'état de la session demande de redémarrer ; revenir n'en demande plus.
    combo.setCurrentIndex(effets.MODES.index("non" if animes else "oui"))
    assert cfg.effets_animes == ("non" if animes else "oui")
    assert not dlg._effets_hint.isHidden()
    combo.setCurrentIndex(0)
    assert dlg._effets_hint.isHidden()
    # Changer d'ambiance en direct ne rallume pas les particules quand les effets sont coupés.
    with qtbot.waitSignal(dlg.season_changed) as recu:
        dlg._season_combo.setCurrentIndex(dlg._season_combo.findData("halloween"))
    assert recu.args == ["halloween" if animes else "aucune"]
    dlg._shutdown_scan()


def test_la_config_garde_le_choix(tmp_path, monkeypatch):
    from src.core import config
    monkeypatch.setattr(config, "CONFIG_FILE_PATH", tmp_path / "config.json")
    cfg = config.Config(install_path=tmp_path / "jeux", effets_animes="non")
    cfg.save()
    assert config.Config.load().effets_animes == "non"
