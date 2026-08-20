"""Sentinelles des deux modules extraits de `main_window.py` le 2026-08-20.

`NotificationBar` (le ruban doré) et `UpdateDispatcher` (les `UpdateChecker` et
le téléchargement de l'exe de mise à jour) sont sortis de la fenêtre, qui passe
de 1015 à 805 lignes.

Le piège trouvé PENDANT la découpe est testé ici en premier : brancher un signal
Qt directement sur une méthode liée du `GameManager` lève `SystemError`.
"""

import pytest

pytest.importorskip("pytestqt")

from src.core.config import Config  # noqa: E402
from src.core.game_manager import GameManager  # noqa: E402
from src.ui.notification_bar import NotificationBar  # noqa: E402
from src.ui.update_dispatcher import UpdateDispatcher  # noqa: E402


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
    cfg = Config(install_path=tmp_path / "games", cache_path=tmp_path / "cache",
                 langue="fr", autoplay_videos=False)
    cfg.save()
    return GameManager(cfg)


class TestReferenceFaible:
    """`GameManager` n'est pas référençable faiblement — donc pas connectable.

    PyQt garde une référence FAIBLE vers le receveur d'une méthode liée. Or
    `GameManager` déclare `__slots__` sans `__weakref__` : la connexion lève
    `SystemError: … returned a result with an exception set`, **à la connexion
    seulement**, jamais à l'import. Le dispatcher passe donc par ses propres
    slots, et ce test dit pourquoi on ne « simplifiera » pas ce détour.
    """

    def test_le_manager_n_est_pas_referencable_faiblement(self, manager):
        import weakref
        with pytest.raises(TypeError):
            weakref.ref(manager)

    def test_les_empreintes_arrivent_quand_meme_au_manager(self, qtbot, manager):
        dispatcher = UpdateDispatcher(manager)
        empreintes = {"https://exemple/hp1.7z": "ab" * 32}
        dispatcher._on_asset_digests(empreintes)
        assert manager._asset_digests == empreintes

    def test_les_compteurs_servent_le_manager_ET_la_fenetre(self, qtbot, manager):
        dispatcher = UpdateDispatcher(manager)
        with qtbot.waitSignal(dispatcher.download_counts, timeout=1000):
            dispatcher._on_download_counts({"hp1": 42})
        assert manager.download_count("hp1") == 42


class TestDispatcher:
    def test_sans_asset_pas_d_installation_automatique(self, qtbot, manager):
        dispatcher = UpdateDispatcher(manager)
        dispatcher.remember("9.9.9", "https://exemple/release", "", "")
        assert not dispatcher.can_install_itself

    def test_la_re_tentative_s_arme_hors_ligne_et_s_arrete_en_ligne(self, qtbot, manager):
        dispatcher = UpdateDispatcher(manager)
        dispatcher.schedule_retry(False)
        assert dispatcher._offline_retry.isActive()
        dispatcher.schedule_retry(True)
        assert not dispatcher._offline_retry.isActive()

    def test_shutdown_sans_rien_en_cours_ne_leve_pas(self, qtbot, manager):
        dispatcher = UpdateDispatcher(manager)
        dispatcher.shutdown()
        dispatcher.shutdown()      # idempotent : appelé aussi par closeEvent

    def test_un_checker_force_est_suivi_puis_oublie(self, qtbot, manager, monkeypatch):
        from src.core.updater import UpdateChecker
        monkeypatch.setattr(UpdateChecker, "start", lambda self: None)
        dispatcher = UpdateDispatcher(manager)
        checker = dispatcher.forced_checker()
        assert checker in dispatcher._extra_checkers
        dispatcher._forget(checker)
        assert checker not in dispatcher._extra_checkers

    def test_le_checker_force_demande_bien_un_fetch(self, qtbot, manager, monkeypatch):
        """Version « 0 » : le catalogue distant est retéléchargé quoi qu'on ait."""
        from src.core.updater import UpdateChecker
        monkeypatch.setattr(UpdateChecker, "start", lambda self: None)
        dispatcher = UpdateDispatcher(manager)
        assert dispatcher.forced_checker()._current_version == "0"


class TestBandeau:
    def test_cache_a_la_construction(self, qtbot):
        barre = NotificationBar()
        qtbot.addWidget(barre)
        assert not barre.isVisible()

    def test_annoncer_montre_et_nomme_la_version(self, qtbot):
        barre = NotificationBar()
        qtbot.addWidget(barre)
        barre.show()
        barre.announce("9.9.9", auto=True)
        assert "9.9.9" in barre.message()
        assert barre.isVisible()

    def test_le_libelle_du_bouton_dit_ce_qui_va_arriver(self, qtbot):
        """« Mettre à jour » installe ; « Télécharger » ouvre le navigateur."""
        barre = NotificationBar()
        qtbot.addWidget(barre)
        barre.announce("9.9.9", auto=True)
        auto = barre._btn.text()
        barre.announce("9.9.9", auto=False)
        assert auto != barre._btn.text()

    def test_la_croix_previent_et_se_cache(self, qtbot):
        barre = NotificationBar()
        qtbot.addWidget(barre)
        barre.show()
        barre.announce("9.9.9", auto=False)
        with qtbot.waitSignal(barre.dismissed, timeout=1000):
            barre._on_close()
        assert not barre.isVisible()

    def test_occupe_grise_le_bouton(self, qtbot):
        barre = NotificationBar()
        qtbot.addWidget(barre)
        barre.announce("9.9.9", auto=True)
        barre.set_busy(True)
        assert not barre._btn.isEnabled()
        barre.set_busy(False)
        assert barre._btn.isEnabled()


class TestFenetreAllegee:
    """La fenêtre ne doit pas récupérer en douce ce qu'on vient d'en sortir."""

    def test_plus_de_construction_de_bandeau_ni_de_checker(self):
        import inspect

        import src.ui.main_window as mw
        source = inspect.getsource(mw)
        for interdit in ("_build_notif_bar", "_launcher_dl", "_shutdown_checker",
                         "_games_asset_urls", "SpeedTracker"):
            assert interdit not in source, (
                f"« {interdit} » est reparti dans main_window.py")

    def test_la_fenetre_reste_sous_le_seuil(self):
        from pathlib import Path
        lignes = len(Path("src/ui/main_window.py").read_text(
            encoding="utf-8").splitlines())
        assert lignes <= 830, f"main_window.py a regrossi : {lignes} lignes"
