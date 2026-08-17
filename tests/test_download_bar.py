"""Tests pour src/ui/download_bar.py — couvre les fixes hide_bar reset + cover scaling."""

import pytest

pytest.importorskip("pytestqt")

from src.core.game_data import GameData  # noqa: E402
from src.core.game_manager import GameState  # noqa: E402
from src.ui.download_bar import DownloadBar  # noqa: E402


_GAME = GameData.from_dict({
    "id": "hp1", "name": "Harry Potter 1", "year": 2001, "description": "d",
    "developer": "Dev", "executable": "HP1/hp.exe", "cover_image": "hp1_cover.jpg",
})


class TestDownloadBarLifecycle:
    def test_hidden_at_construction(self, qtbot):
        bar = DownloadBar()
        qtbot.addWidget(bar)
        assert not bar.isVisible()
        assert bar.current_game is None

    def test_show_for_game_sets_state(self, qtbot):
        bar = DownloadBar()
        qtbot.addWidget(bar)
        bar.show_for_game(_GAME, GameState.DOWNLOADING)
        assert bar.current_game is _GAME
        assert bar._title.text() == "Harry Potter 1"
        assert bar._progress.value() == 0

    def test_install_state_hides_cancel(self, qtbot):
        bar = DownloadBar()
        qtbot.addWidget(bar)
        bar.show_for_game(_GAME, GameState.INSTALLING)
        assert not bar._btn_cancel.isVisible() or bar._btn_cancel.isHidden()

    def test_stepper_phases(self, qtbot):
        """set_phase pilote le stepper ; verify et finalize passent en indéterminé."""
        bar = DownloadBar()
        qtbot.addWidget(bar)
        bar.show_for_game(_GAME, GameState.DOWNLOADING)
        assert bar._phase_label.text().startswith("1/4")

        bar.set_phase("verify")
        assert bar._phase_label.text().startswith("2/4")
        assert bar._progress.maximum() == 0  # indéterminé pendant le hash

        # La progression qui reprend re-borne la barre (part suivante)
        bar.update_download_progress(10, 100, 0.0, -1.0)
        assert bar._progress.maximum() == 100

        bar.set_phase("install")
        assert bar._phase_label.text().startswith("3/4")

        bar.set_phase("inconnu")  # ignoré sans crash
        assert bar._phase_label.text().startswith("3/4"), "phase inconnue = pas de changement"

        bar.hide_bar()
        assert bar._phase_label.text() == ""
        assert bar._progress.maximum() == 100

    def test_phase_finalisation_indeterminee(self, qtbot):
        """Après l'extraction, la barre ne doit PAS rester bloquée à 100 %.

        Sur un jeu de plusieurs Go, le déblocage NTFS et la copie des configs
        durent des dizaines de secondes : sans cette phase, l'utilisateur voyait
        100 % figé et concluait à un plantage.
        """
        bar = DownloadBar()
        qtbot.addWidget(bar)
        bar.show_for_game(_GAME, GameState.INSTALLING)
        bar.update_install_progress(100)
        assert bar._progress.value() == 100

        bar.set_phase("finalize")
        assert bar._phase_label.text().startswith("4/4")
        assert bar._progress.maximum() == 0, "barre indéterminée pendant la finalisation"
        assert bar._status.text() != ""

    def test_hide_bar_resets_everything(self, qtbot):
        """Régression : hide_bar doit reset titre/status/progress sinon flash au prochain show."""
        bar = DownloadBar()
        qtbot.addWidget(bar)
        bar.show_for_game(_GAME, GameState.DOWNLOADING)
        bar.update_download_progress(50, 100, 1024 * 1024.0, 5.0)
        assert bar._progress.value() == 50
        assert bar._status.text() != ""

        bar.hide_bar()

        assert bar.current_game is None
        assert bar._progress.value() == 0
        assert bar._title.text() == ""
        assert bar._status.text() == ""

    def test_update_progress_sets_value(self, qtbot):
        bar = DownloadBar()
        qtbot.addWidget(bar)
        bar.show_for_game(_GAME, GameState.DOWNLOADING)
        bar.update_download_progress(75, 100, 0.0, -1.0)
        assert bar._progress.value() == 75

    def test_update_progress_ignores_zero_total(self, qtbot):
        bar = DownloadBar()
        qtbot.addWidget(bar)
        bar.show_for_game(_GAME, GameState.DOWNLOADING)
        bar.update_download_progress(0, 0, 0.0, -1.0)
        assert bar._progress.value() == 0

    def test_part_info_appended(self, qtbot):
        bar = DownloadBar()
        qtbot.addWidget(bar)
        bar.show_for_game(_GAME, GameState.DOWNLOADING)
        bar.update_download_progress(50, 100, 0.0, -1.0)
        bar.update_part_info(2, 3)
        assert "partie 2/3" in bar._status.text()

    def test_cancel_signal(self, qtbot):
        bar = DownloadBar()
        qtbot.addWidget(bar)
        with qtbot.waitSignal(bar.cancel_clicked, timeout=500):
            bar._btn_cancel.click()
