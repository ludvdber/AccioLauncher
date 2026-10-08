"""Tests pour le helper de tri date utilisé par versions_dialog.

Le helper est gardé hors classe pour rester testable sans Qt.
"""

from src.ui.versions_dialog import _date_sort_key


class TestDateSortKey:
    def test_iso_format(self):
        assert _date_sort_key("2026-04-29") == (2026, 4, 29)

    def test_zero_padded(self):
        # Les deux formats donnent la même clé sémantique (4 < 12 quel que soit le pad)
        a = _date_sort_key("2026-3-08")
        b = _date_sort_key("2026-03-08")
        assert a == b == (2026, 3, 8)

    def test_invalid_returns_zero_tuple(self):
        # Ne crash pas, retourne un tuple bas pour pousser l'entrée en bas du tri.
        assert _date_sort_key("not-a-date") == (0,)
        assert _date_sort_key("") == (0,)
        assert _date_sort_key(None) == (0,)  # type: ignore[arg-type]

    def test_sort_stability(self):
        dates = ["2026-04-29", "2025-12-31", "2026-01-01", "2026-04-29"]
        sorted_dates = sorted(dates, key=_date_sort_key, reverse=True)
        assert sorted_dates[0] == "2026-04-29"
        assert sorted_dates[1] == "2026-04-29"
        assert sorted_dates[-1] == "2025-12-31"


# ─── La fenêtre elle-même (M-15 / ACT-020 : 12 % couverte) ──────────────────

import pytest  # noqa: E402

pytest.importorskip("pytestqt")

from types import SimpleNamespace  # noqa: E402

from PyQt6.QtWidgets import QLabel, QMessageBox, QPushButton  # noqa: E402

from src.core.game_data import GameData  # noqa: E402

JEU = {
    "id": "hpx", "name": "HPX", "year": 2001, "description": "d", "developer": "dev",
    "executable": "HPX/System/Game.exe", "cover_image": "c.png",
    "latest_version": "1.2", "recommended_version": "1.2",
    "versions": [
        {"version": "1.0", "date": "2026-01-01", "size_mb": 10, "download_url": "https://x/1.0.7z",
         "changes": ["Version <b>originale</b>"]},
        {"version": "1.1", "date": "2026-02-01", "size_mb": 10, "download_url": "https://x/1.1.7z"},
        {"version": "1.2", "date": "2026-03-01", "size_mb": 10, "download_url": "https://x/1.2.7z"},
        {"version": "1.3", "date": "2026-04-01", "size_mb": 10},
    ],
}


def _dialogue(qtbot, installee):
    from src.ui.versions_dialog import VersionsDialog
    manager = SimpleNamespace(installed_version=lambda _id: installee)
    dlg = VersionsDialog(GameData.from_dict(JEU), manager)
    qtbot.addWidget(dlg)
    return dlg


def _boutons(dlg):
    return [b.text() for b in dlg.findChildren(QPushButton) if b.text() != "Fermer"]


class _FausseConfirmation:
    """QMessageBox remplacée au niveau du MODULE (règle 12) ; `exec()` ne bloque pas."""
    Icon = QMessageBox.Icon
    ButtonRole = QMessageBox.ButtonRole
    accepter = True

    def __init__(self, _parent=None):
        self._boutons = []
        self.texte = ""

    def addButton(self, libelle, _role):
        self._boutons.append(libelle)
        return libelle

    def setText(self, t):
        self.texte = t

    def clickedButton(self):
        return self._boutons[0] if _FausseConfirmation.accepter else self._boutons[1]

    def __getattr__(self, _nom):       # setIcon, setWindowTitle, exec…
        return lambda *a, **k: None


class TestFenetreDesVersions:
    def test_les_boutons_disent_ce_qui_va_arriver(self, qtbot):
        dlg = _dialogue(qtbot, "1.1")
        # 1.1 installée : rien pour elle ; 1.3 sans archive : « Pas encore en ligne ».
        assert sorted(_boutons(dlg)) == ["Mettre à jour vers v1.2", "Revenir à v1.0"]
        assert any(lbl.text() == "Pas encore en ligne" for lbl in dlg.findChildren(QLabel))

    def test_sans_version_installee_on_propose_d_installer(self, qtbot):
        dlg = _dialogue(qtbot, None)
        assert sorted(_boutons(dlg)) == ["Installer v1.0", "Installer v1.1", "Installer v1.2"]

    def test_un_changelog_venu_du_catalogue_est_echappe(self, qtbot):
        dlg = _dialogue(qtbot, None)
        textes = [lbl.text() for lbl in dlg.findChildren(QLabel)]
        assert any("Version &lt;b&gt;originale&lt;/b&gt;" in t for t in textes)

    @pytest.mark.parametrize("accepter, attendu", [(True, [("hpx", "1.0")]), (False, [])])
    def test_la_confirmation_decide_du_changement(self, qtbot, monkeypatch, accepter, attendu):
        monkeypatch.setattr("src.ui.versions_dialog.QMessageBox", _FausseConfirmation)
        monkeypatch.setattr(_FausseConfirmation, "accepter", accepter)
        dlg = _dialogue(qtbot, "1.1")
        demandes = []
        dlg.switch_to_version.connect(lambda jeu, v: demandes.append((jeu, v)))
        dlg._on_install_version("1.0")
        assert demandes == attendu
