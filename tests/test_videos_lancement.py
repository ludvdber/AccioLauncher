"""Passer les vidéos de lancement de HP3 (VU dans l'atelier le 2026-10-21)."""
from src.core import videos_lancement as v
from src.core.catalogue_blocs import _videos_de_lancement_valides

VIDEOS = ("HP3/Movies/eag_1920.bik", "HP3/Movies/wb_1920.bik", "HP3/Movies/KWLogo.bik")


def _jeu(tmp_path, noms=VIDEOS):
    for rel in noms:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(rel.encode())
    (tmp_path / "HP3/Movies/LoadLevel.bik").write_bytes(b"jeu")
    return tmp_path


def test_passer_puis_remettre_rend_les_fichiers_a_l_octet(tmp_path):
    d = _jeu(tmp_path)
    assert v.passees(d, VIDEOS) is False
    assert v.passer(d, VIDEOS, True) and v.passees(d, VIDEOS) is True
    assert not (d / VIDEOS[0]).exists() and (d / (VIDEOS[0] + ".off")).exists()
    assert (d / "HP3/Movies/LoadLevel.bik").read_bytes() == b"jeu", "une vidéo non déclarée"
    assert v.passer(d, VIDEOS, False) and v.passees(d, VIDEOS) is False
    assert all((d / rel).read_bytes() == rel.encode() for rel in VIDEOS)
    assert not list(d.rglob("*.off"))


def test_une_video_revenue_par_la_reparation_compte_comme_jouee(tmp_path):
    d = _jeu(tmp_path)
    v.passer(d, VIDEOS, True)
    (d / VIDEOS[2]).write_bytes(b"remise")          # « Vérifier / réparer »
    assert v.passees(d, VIDEOS) is False
    assert v.passer(d, VIDEOS, False)
    assert (d / VIDEOS[2]).read_bytes() == b"remise" and not list(d.rglob("*.off"))


def test_jeu_absent_pas_de_rubrique(tmp_path):
    assert v.passees(tmp_path, VIDEOS) is None


def test_le_catalogue_ne_peut_nommer_que_des_videos():
    assert _videos_de_lancement_valides(list(VIDEOS)) == VIDEOS
    assert _videos_de_lancement_valides(["HP3/system/Engine.dll"]) == ()
    assert _videos_de_lancement_valides(["../Documents/x.bik"]) == ()
    assert _videos_de_lancement_valides(None) == ()


def test_l_interrupteur_de_la_fiche_renomme_les_videos(qtbot, tmp_path):
    from types import SimpleNamespace

    from src.core.game_data import GameData
    from src.ui.game_settings_dialog import GameSettingsDialog
    from src.ui.toggle_switch import ToggleSwitch
    d = _jeu(tmp_path)
    jeu = GameData.from_dict({
        "id": "hp3", "name": "HP3", "year": 2004, "description": "d", "developer": "d",
        "executable": "HP3/system/hppoa.exe", "cover_image": "c.jpg", "launch_videos": list(VIDEOS)})
    manager = SimpleNamespace(game_language=lambda g: None, langues_disponibles=lambda g: (),
                              config=SimpleNamespace(install_path=d))
    dlg = GameSettingsDialog(jeu, manager, lambda c: True)
    qtbot.addWidget(dlg)
    bascules = [b for b in dlg.findChildren(ToggleSwitch) if not b.isChecked()]
    assert len(bascules) == 1
    bascules[0].toggled.emit(True)
    assert v.passees(d, VIDEOS) is True
