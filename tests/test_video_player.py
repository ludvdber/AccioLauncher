"""Le lecteur vidéo (`src/ui/video_player.py`) sur une VRAIE vidéo.

`tests/data/rouge_06s.mp4` : 0,6 s d'image rouge en 64 × 36, piste son muette
(2,5 Ko, fabriquée par ffmpeg le 2026-10-24). Le lecteur des cinématiques et
des bandes-annonces n'était exercé que sur des objets simulés : ici l'image
arrive, la fin est signalée, les ressources sont rendues.
"""

from pathlib import Path

import pytest

from src.ui.video_player import MULTIMEDIA_DISPONIBLE, VideoPlayer

VIDEO = Path(__file__).parent / "data" / "rouge_06s.mp4"

pytestmark = pytest.mark.skipif(not MULTIMEDIA_DISPONIBLE, reason="PyQt6-Multimedia absent")


@pytest.fixture
def lecteur(qtbot):
    from PyQt6.QtWidgets import QWidget
    hote = QWidget()
    qtbot.addWidget(hote)
    lecteur = VideoPlayer(hote)
    lecteur.set_plein_debit(True)
    yield lecteur
    lecteur.stop()


class TestVraieLecture:
    def test_l_image_arrive_puis_la_fin_est_signalee(self, lecteur, qtbot):
        images = []
        lecteur.video_frame.connect(images.append)
        with qtbot.waitSignal(lecteur.playback_ended, timeout=10000):
            assert lecteur.play(str(VIDEO), muted=True)
            assert lecteur.is_playing
        assert images, "aucune image décodée"
        couleur = images[0].pixelColor(32, 18)
        assert couleur.red() > 180 and couleur.green() < 80, couleur.name()
        assert not lecteur.is_playing, "la fin rend les ressources"

    def test_la_duree_et_la_position_pour_la_barre_de_lecture(self, lecteur, qtbot):
        durees = []
        lecteur.duration_changed.connect(durees.append)
        with qtbot.waitSignal(lecteur.position_changed, timeout=10000):
            assert lecteur.play(str(VIDEO), muted=True)
        qtbot.waitUntil(lambda: any(d > 0 for d in durees), timeout=10000)
        assert 400 <= max(durees) <= 800              # 0,6 s
        lecteur.pause()
        lecteur.seek(300)
        qtbot.waitUntil(lambda: lecteur.position >= 250, timeout=5000)
        assert lecteur.duration == max(durees)

    def test_relancer_remplace_la_lecture_en_cours(self, lecteur, qtbot):
        assert lecteur.play(str(VIDEO), muted=True)
        premier = lecteur._player
        assert lecteur.play(str(VIDEO), muted=True)
        assert lecteur._player is not premier

    def test_pause_et_reprise_sans_perdre_la_source(self, lecteur, qtbot):
        assert lecteur.play(str(VIDEO), muted=True)
        lecteur.pause()
        assert lecteur.paused and lecteur.is_playing
        lecteur.resume()
        assert not lecteur.paused

    def test_fenetre_reduite_puis_rendue(self, lecteur):
        assert lecteur.play(str(VIDEO), muted=True)
        lecteur.set_reduite(True)
        assert lecteur.paused
        lecteur.set_reduite(False)
        assert not lecteur.paused
        lecteur.pause()
        lecteur.set_reduite(True)
        lecteur.set_reduite(False)
        assert lecteur.paused, "une pause voulue ne reprend pas d'elle-même"


class TestSon:
    def test_sans_lecture_couper_ne_fait_rien(self, lecteur):
        assert lecteur.toggle_mute() is False
        lecteur.set_volume(50)
        lecteur.set_muted(True)
        assert lecteur.muted

    def test_monter_le_volume_rend_le_son(self, lecteur):
        assert lecteur.play(str(VIDEO), muted=True)
        assert lecteur.muted and lecteur._audio.isMuted()
        lecteur.set_volume(40)
        assert not lecteur.muted and not lecteur._audio.isMuted()
        assert lecteur._audio.volume() == pytest.approx(0.4)
        assert lecteur.toggle_mute() is True and lecteur._audio.isMuted()


def test_la_copie_d_un_saut_n_est_plus_dans_le_tmp_partage(tmp_path):
    """Audit du 2026-10-29 : `/tmp/accio_cinematique_{0,1}.vp6`, nom fixe dans
    un dossier partagé. Les copies vivent désormais dans les données du
    launcher (redirigées vers `tmp_path` par conftest)."""
    import tempfile

    from src.ui.video_player import dossier_des_copies
    dossier = dossier_des_copies()
    assert dossier.is_relative_to(tmp_path)
    assert dossier.parent != Path(tempfile.gettempdir())


def test_l_arret_efface_les_copies_des_sauts(lecteur):
    """Grand audit du 2026-11-02 : les deux copies d'une cinématique de HP8
    (jusqu'à 329 Mo chacune) restaient dans le cache fixe après la lecture."""
    from src.ui.video_player import dossier_des_copies
    dossier = dossier_des_copies()
    dossier.mkdir(parents=True, exist_ok=True)
    for n in (0, 1):
        (dossier / f"saut_{n}.vp6").write_bytes(b"MVhd")
    lecteur._copies = 2
    lecteur.stop()
    assert not list(dossier.glob("saut_*.vp6"))


def _clip(tmp_path):
    """Une cinématique d'EA de 10 images à 10 images/s, complètes en 0, 4 et 9."""
    import struct

    def bloc(nom, contenu):
        return nom + struct.pack("<I", 8 + len(contenu)) + contenu
    images = "KFFFKFFFFK"
    entete = bloc(b"MVhd", b"vp60" + struct.pack("<HHIIII", 64, 64, len(images), 99, 10, 1))
    chemin = tmp_path / "clip.vp6"
    chemin.write_bytes(entete + b"".join(bloc(b"MV0K" if c == "K" else b"MV0F", b"\0" * 4)
                                         for c in images))
    return chemin


@pytest.fixture
def sans_vrai_media(lecteur, monkeypatch):
    """`_ouvrir` remplacé : un faux lecteur, et la liste des fichiers ouverts."""
    from unittest.mock import MagicMock
    ouverts = []

    def ouvrir(chemin, _muet, _volume):
        ouverts.append(chemin)
        lecteur._player, lecteur._sink, lecteur._audio = MagicMock(), MagicMock(), MagicMock()
        lecteur._paused = False
    monkeypatch.setattr(lecteur, "_ouvrir", ouvrir)
    return ouverts


class TestSautDansUneCinematique:
    """Grand audit du 2026-11-02 : l'index et la copie d'un saut figeaient le
    fil de l'interface (0,45 s puis 0,2 s par saut pour une cinématique de HP8)."""

    def test_le_saut_se_prepare_sur_un_autre_fil(self, lecteur, sans_vrai_media, qtbot,
                                                  tmp_path, monkeypatch):
        import threading

        from src.core import vp6_ea
        from src.ui.video_player import dossier_des_copies
        fils, vrai = [], vp6_ea.indexer
        monkeypatch.setattr(vp6_ea, "indexer", lambda c: (fils.append(threading.current_thread()),
                                                           vrai(c))[1])
        assert lecteur.play(str(_clip(tmp_path)), debut_ms=750)
        assert lecteur.is_playing and lecteur.position == 750 and sans_vrai_media == []
        assert lecteur.duration == 1000, "la durée vient de l'en-tête, tout de suite"
        qtbot.waitUntil(lambda: len(sans_vrai_media) == 1, timeout=5000)
        assert fils and fils[0] is not threading.main_thread()
        assert Path(sans_vrai_media[0]).parent == dossier_des_copies()
        assert lecteur._decalage == 400 and lecteur._cible == 750

    def test_un_saut_depasse_est_jete(self, lecteur, sans_vrai_media, qtbot, tmp_path):
        from src.ui.video_player import dossier_des_copies
        clip = _clip(tmp_path)
        assert lecteur.play(str(clip))
        lecteur.seek(950)
        lecteur.seek(500)
        qtbot.waitUntil(lambda: len(sans_vrai_media) == 2, timeout=5000)
        qtbot.waitUntil(lambda: len(list(dossier_des_copies().glob("saut_*.vp6"))) == 1, timeout=5000)
        assert sans_vrai_media[0] == str(clip)
        assert [Path(c).name for c in dossier_des_copies().glob("saut_*.vp6")] == \
            [Path(sans_vrai_media[1]).name]
        assert lecteur._decalage == 400

    def test_avant_la_deuxieme_image_complete_le_fichier_lui_meme(self, lecteur, sans_vrai_media,
                                                                  qtbot, tmp_path):
        clip = _clip(tmp_path)
        assert lecteur.play(str(clip))
        lecteur.pause()
        lecteur.seek(300)
        qtbot.waitUntil(lambda: len(sans_vrai_media) == 2, timeout=5000)
        assert sans_vrai_media == [str(clip), str(clip)]
        assert lecteur._decalage == 0 and lecteur._cible == 300 and lecteur._pause_apres_saut

    def test_une_pause_pendant_l_avance_rapide_attend_le_point_voulu(
            self, lecteur, sans_vrai_media, qtbot, tmp_path):
        """Posée tout de suite, elle figeait l'image d'avant le saut (audit du 2026-11-02)."""
        from unittest.mock import MagicMock
        assert lecteur.play(str(_clip(tmp_path)), debut_ms=750)
        qtbot.waitUntil(lambda: len(sans_vrai_media) == 1, timeout=5000)
        assert lecteur._cible == 750
        lecteur.pause()
        assert lecteur._paused
        lecteur._player.pause.assert_not_called()
        image = MagicMock()
        image.isValid.return_value = True
        image.startTime.return_value = (750 - lecteur._decalage) * 1000
        lecteur._on_frame(image)
        lecteur._player.pause.assert_called_once()
        assert lecteur._paused and lecteur._cible == -1
