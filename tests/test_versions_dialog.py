"""Page des versions d'un jeu : tri, dates, et ce que chaque version propose.

Les helpers de date sont gardés hors classe pour rester testables sans Qt.
"""

import pytest

from src.ui.versions_dialog import _date_sort_key, date_courte


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


class TestDates:
    def test_date_courte(self):
        assert date_courte("2026-10-01") == "01/10/2026"

    def test_une_date_illisible_reste_telle_quelle(self):
        assert date_courte("bientôt") == "bientôt"
        assert date_courte("2026-02-30") == "2026-02-30"

    def test_date_longue_en_francais(self, qtbot):
        from src.core.i18n import set_language
        from src.ui.versions_dialog import date_longue
        set_language("fr")
        assert date_longue("2026-10-01") == "1er octobre 2026"
        assert date_longue("2026-09-28") == "28 septembre 2026"

    @pytest.mark.parametrize("langue, attendu", [("en", "October 1, 2026"),
                                                 ("es", "1 de octubre de 2026")])
    def test_date_longue_dans_l_ordre_de_chaque_langue(self, qtbot, langue, attendu):
        from src.core.i18n import set_language
        from src.ui.versions_dialog import date_longue
        set_language(langue)
        try:
            assert date_longue("2026-10-01") == attendu
        finally:
            set_language("fr")


# ─── La fenêtre elle-même (M-15 / ACT-020 : 12 % couverte) ──────────────────



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


def _actions(dlg):
    """Le bouton de chaque page de version, par numéro ; None s'il n'y en a pas."""
    return {v.version: (b.text() if (b := dlg.action(v.version)) else None)
            for v in dlg.game.versions}


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


class TestPageDesVersions:
    def test_les_boutons_disent_ce_qui_va_arriver(self, qtbot):
        dlg = _dialogue(qtbot, "1.1")
        # 1.1 installée : rien pour elle ; 1.3 sans archive : « Pas encore en ligne ».
        assert _actions(dlg) == {"1.0": "Revenir à v1.0", "1.1": None,
                                 "1.2": "Mettre à jour vers v1.2", "1.3": None}
        assert any(lbl.text() == "Pas encore en ligne" for lbl in dlg.findChildren(QLabel))
        assert any(lbl.text() == "C'est la version installée" for lbl in dlg.findChildren(QLabel))

    def test_sans_version_installee_on_propose_d_installer(self, qtbot):
        dlg = _dialogue(qtbot, None)
        assert _actions(dlg) == {"1.0": "Installer v1.0", "1.1": "Installer v1.1",
                                 "1.2": "Installer v1.2", "1.3": None}
        assert not any(lbl.text() == "Vos sauvegardes restent." for lbl in dlg.findChildren(QLabel)), \
            "rien à garder quand rien n'est installé"

    def test_s_ouvre_sur_la_version_installee(self, qtbot):
        dlg = _dialogue(qtbot, "1.1")
        assert dlg._lignes["1.1"].isChecked()
        assert dlg._details.currentIndex() == dlg._index["1.1"]

    def test_sans_installation_s_ouvre_sur_la_recommandee(self, qtbot):
        dlg = _dialogue(qtbot, None)
        assert dlg._lignes["1.2"].isChecked()

    def test_choisir_une_version_montre_sa_page(self, qtbot):
        dlg = _dialogue(qtbot, "1.1")
        dlg._lignes["1.0"].click()
        assert dlg._details.currentIndex() == dlg._index["1.0"]
        assert not dlg._lignes["1.1"].isChecked()

    def test_les_plus_recentes_en_haut_du_rail(self, qtbot):
        dlg = _dialogue(qtbot, "1.1")
        assert list(dlg._lignes) == ["1.3", "1.2", "1.1", "1.0"]

    def test_le_rail_dit_installee_et_recommandee(self, qtbot):
        dlg = _dialogue(qtbot, "1.1")
        assert "Installée" in dlg._lignes["1.1"].accessibleName()
        assert "Recommandée" in dlg._lignes["1.2"].accessibleName()
        assert "Installée" not in dlg._lignes["1.0"].accessibleName()

    def test_ne_promet_pas_les_reglages(self, qtbot):
        """Changer de version supprime le dossier du jeu, et l'ini du correctif avec."""
        dlg = _dialogue(qtbot, "1.1")
        textes = " ".join(lbl.text() for lbl in dlg.findChildren(QLabel))
        assert "sauvegardes" in textes
        assert "réglages" not in textes

    def test_le_retour_ferme_la_page(self, qtbot):
        dlg = _dialogue(qtbot, "1.1")
        fermee = []
        dlg.finished.connect(fermee.append)
        next(b for b in dlg.findChildren(QPushButton) if b.text() == "Bibliothèque").click()
        assert fermee

    def test_un_changelog_venu_du_catalogue_est_echappe(self, qtbot):
        dlg = _dialogue(qtbot, None)
        textes = [lbl.text() for lbl in dlg.findChildren(QLabel)]
        assert any("Version &lt;b&gt;originale&lt;/b&gt;" in t for t in textes)

    @pytest.mark.parametrize("accepter, attendu", [(True, [("hpx", "1.0")]), (False, [])])
    def test_la_confirmation_decide_du_changement(self, qtbot, monkeypatch, accepter, attendu):
        monkeypatch.setattr("src.ui.versions_dialog.FenetreMessage", _FausseConfirmation)
        monkeypatch.setattr(_FausseConfirmation, "accepter", accepter)
        dlg = _dialogue(qtbot, "1.1")
        demandes = []
        dlg.switch_to_version.connect(lambda jeu, v: demandes.append((jeu, v)))
        dlg._on_install_version("1.0")
        assert demandes == attendu
