"""Tests sentinelles pour les petits widgets : ClickableLabel, Toast, Ticker."""

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import Qt  # noqa: E402

from src.ui.clickable_label import ClickableLabel  # noqa: E402
# Importé ICI et pas dans le test : voir tests/conftest.py — créer un module
# d'extension Qt en pleine session est une source de plantage aléatoire.
from src.ui.single_instance import SingleInstance  # noqa: E402
from src.ui.ticker import Ticker  # noqa: E402
from src.ui.toast import Toast  # noqa: E402


class TestClickableLabel:
    def test_click_emits(self, qtbot):
        lbl = ClickableLabel("Lire la suite…")
        qtbot.addWidget(lbl)
        with qtbot.waitSignal(lbl.clicked, timeout=1000):
            qtbot.mouseClick(lbl, Qt.MouseButton.LeftButton)

    def test_enter_key_emits(self, qtbot):
        """A11Y : le label doit être activable au clavier."""
        lbl = ClickableLabel("Versions et changelog")
        qtbot.addWidget(lbl)
        with qtbot.waitSignal(lbl.clicked, timeout=1000):
            qtbot.keyClick(lbl, Qt.Key.Key_Return)

    def test_focusable(self, qtbot):
        lbl = ClickableLabel("x")
        qtbot.addWidget(lbl)
        assert lbl.focusPolicy() != Qt.FocusPolicy.NoFocus


class TestToast:
    def test_show_message(self, qtbot):
        from PyQt6.QtWidgets import QWidget
        host = QWidget()
        host.resize(800, 600)
        qtbot.addWidget(host)
        host.show()
        toast = Toast(host)
        toast.show_message("Jeu installé ✓", duration_ms=200)
        assert toast.isVisible()
        assert toast.text() == "Jeu installé ✓"

    def test_message_replaced(self, qtbot):
        from PyQt6.QtWidgets import QWidget
        host = QWidget()
        host.resize(800, 600)
        qtbot.addWidget(host)
        toast = Toast(host)
        toast.show_message("Premier")
        toast.show_message("Second")
        assert toast.text() == "Second"


class TestSingleInstance:
    def test_second_instance_activates_first(self, qtbot):
        import uuid

        key = f"accio-test-{uuid.uuid4().hex}"
        first = SingleInstance(key)
        assert first.try_acquire() is True

        second = SingleInstance(key)
        with qtbot.waitSignal(first.activate_requested, timeout=2000):
            assert second.try_acquire() is False

        first.release()

    @staticmethod
    def _envoyer(qtbot, key, *morceaux):
        """Un client brut qui envoie son message en plusieurs écritures."""
        from PyQt6.QtNetwork import QLocalSocket
        sock = QLocalSocket()
        sock.connectToServer(key)
        assert sock.waitForConnected(2000)
        for morceau in morceaux:
            sock.write(morceau)
            sock.flush()
            sock.waitForBytesWritten(1000)
            qtbot.wait(50)
        return sock

    def test_un_message_en_deux_morceaux_arrive_entier(self, qtbot):
        """Audit du 2026-11-16 : le premier morceau (« jou ») était lu seul, et la
        connexion coupée ; la demande de jeu se perdait."""
        import uuid
        key = f"accio-test-{uuid.uuid4().hex}"
        first = SingleInstance(key)
        assert first.try_acquire() is True
        recus = []
        first.jouer_requested.connect(recus.append)
        sock = self._envoyer(qtbot, key, b"jou", b"er:hp4\n")
        qtbot.waitUntil(lambda: recus == ["hp4"], timeout=3000)
        sock.abort()
        first.release()

    def test_un_identifiant_douteux_n_est_pas_relaye(self, qtbot):
        import uuid
        key = f"accio-test-{uuid.uuid4().hex}"
        first = SingleInstance(key)
        assert first.try_acquire() is True
        recus = []
        first.jouer_requested.connect(recus.append)
        sock = self._envoyer(qtbot, key, b"jouer:../../x\n")
        qtbot.wait(300)
        assert recus == []
        sock.abort()
        first.release()

    def test_la_cle_depend_du_compte(self, monkeypatch):
        """Audit du 2026-11-16 : un nom fixe est commun à tous les comptes d'un
        poste ; le launcher d'un second compte croyait l'instance déjà ouverte."""
        from src.ui import single_instance
        monkeypatch.setattr(single_instance.getpass, "getuser", lambda: "ludo")
        a = single_instance._cle_par_utilisateur()
        monkeypatch.setattr(single_instance.getpass, "getuser", lambda: "invite")
        assert a != single_instance._cle_par_utilisateur()


class TestTicker:
    def test_singleton(self, qtbot):
        assert Ticker.instance() is Ticker.instance()

    def test_tick_fires(self, qtbot):
        ticker = Ticker.instance()
        ticker.resume()
        with qtbot.waitSignal(ticker.tick, timeout=2000):
            pass

    def test_pause_resume(self, qtbot):
        ticker = Ticker.instance()
        abonne = lambda: None  # noqa: E731
        ticker.tick.connect(abonne)
        try:
            ticker.pause()
            assert not ticker._timer.isActive()
            ticker.resume()
            assert ticker._timer.isActive()
        finally:
            Ticker.detach(abonne)

    def test_sans_abonne_l_horloge_se_tait_et_repart_au_premier(self, qtbot):
        """f126 : derrière une page, plus rien ne bouge, et l'horloge réveillait encore le
        launcher 30 fois par seconde."""
        ticker = Ticker.instance()
        abonnes = ticker.receivers(ticker.tick)
        if abonnes:
            pytest.skip(f"{abonnes} abonné(s) laissé(s) par un autre test")
        ticker.resume()
        qtbot.waitUntil(lambda: not ticker._timer.isActive(), timeout=500)
        abonne = lambda: None  # noqa: E731
        ticker.tick.connect(abonne)
        try:
            assert ticker._timer.isActive(), "le premier abonné la relance"
        finally:
            Ticker.detach(abonne)
