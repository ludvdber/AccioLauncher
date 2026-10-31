"""Journal des changements d'un jeu (ex-page des versions) : tri, dates, lecture seule.

Les helpers de date sont gardés hors classe pour rester testables sans Qt.
"""

from pathlib import Path

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

from PyQt6.QtWidgets import QLabel, QPushButton  # noqa: E402

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


class TestPageDesVersions:
    def test_le_journal_n_installe_rien(self, qtbot):
        """Une seule archive par jeu (Ludo, 2026-10-30, correctif 2.3.0) : la page
        ne propose plus de revenir à une version, ni d'en installer une."""
        from src.ui.versions_dialog import VersionsDialog
        assert not hasattr(VersionsDialog, "switch_to_version")
        for installee in ("1.1", None):
            dlg = _dialogue(qtbot, installee)
            boutons = [b.text() for b in dlg.findChildren(QPushButton)
                       if b.objectName() != "version"]
            assert boutons == ["Bibliothèque"], boutons

    def test_la_version_installee_se_dit(self, qtbot):
        dlg = _dialogue(qtbot, "1.1")
        textes = [lbl.text() for lbl in dlg.findChildren(QLabel)]
        assert textes.count("C'est la version installée") == 1

    def test_le_journal_de_chaque_version_reste_lisible(self, qtbot):
        dlg = _dialogue(qtbot, None)
        assert dlg.windowTitle() == "Journal des changements de HPX"
        dlg._lignes["1.0"].click()
        page = dlg._details.currentWidget()
        assert any("originale" in lbl.text() for lbl in page.findChildren(QLabel))

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

    def test_la_mise_a_jour_garde_toujours_les_reglages(self):
        """La mise à jour supprime toujours le dossier du jeu : les réglages
        posés à côté de l'exécutable restent lus avant et reportés."""
        from src.ui import game_operations
        assert "reglages_conserves.mettre_de_cote" in Path(game_operations.__file__).read_text(
            encoding="utf-8")

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
