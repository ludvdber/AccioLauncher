"""Tests du bandeau d'avertissement de `src/ui/action_panel.py`.

Règle testée ici : **un état ne s'affiche que lorsqu'il DÉVIE de la normale**.
Pas de ligne « espace disque : 412 Go », pas de pastille « prérequis OK » — la
présence même du bandeau est l'information. Les tests vérifient donc autant son
absence que son contenu.
"""

import pytest

pytest.importorskip("pytestqt")

from src.core.config import Config  # noqa: E402
from src.core.game_manager import GameManager, GameState  # noqa: E402
from src.ui.action_panel import ActionPanel  # noqa: E402


@pytest.fixture
def panel(qtbot, tmp_path, monkeypatch):
    """ActionPanel sur un manager isolé, prérequis système réputés satisfaits."""
    monkeypatch.setattr("src.core.system_checks.check_vcredist_x86", lambda: True)
    cfg = Config(install_path=tmp_path / "games",
                 cache_path=tmp_path / "games" / ".cache", langue="fr")
    manager = GameManager(cfg)
    from src.core.i18n import set_language
    set_language("fr")
    widget = ActionPanel(manager)
    widget.resize(560, 120)
    qtbot.addWidget(widget)
    yield widget, manager
    set_language("fr")


def _disque(monkeypatch, free_mb):
    """Force l'espace libre vu par `GameManager.free_space_mb`.

    On patche `shutil.disk_usage` et non la méthode : `GameManager` utilise
    `__slots__` (l'attribut d'instance est en lecture seule), et surtout le
    vrai chemin de code — conversion octets → Mo comprise — reste exercé.
    """
    from collections import namedtuple
    usage = namedtuple("usage", "total used free")

    def _fake(_path):
        if free_mb is None:
            raise OSError("lecteur indisponible")
        return usage(0, 0, free_mb * 1024 * 1024)

    monkeypatch.setattr("src.core.game_manager.shutil.disk_usage", _fake)


def _jeu_telechargeable(manager):
    """Premier jeu du catalogue dont une archive est réellement publiée."""
    for entry in manager.get_games():
        dl = entry.game.current_download
        if dl is not None and dl.is_available and dl.size_mb > 0:
            return entry.game
    pytest.skip("aucun jeu téléchargeable dans le catalogue embarqué")


def _prepare(panel_fixture, state):
    widget, manager = panel_fixture
    game = _jeu_telechargeable(manager)
    manager.set_game_state(game.id, state)
    widget.set_game(game)
    widget.refresh()
    return widget, manager, game


class TestSilenceQuandToutVaBien:
    def test_aucun_bandeau_avec_de_la_place_et_du_reseau(self, panel, monkeypatch):
        widget, manager = panel
        _disque(monkeypatch, 900_000)
        _prepare(panel, GameState.NOT_INSTALLED)
        assert widget._alert.isHidden()
        assert widget._alert.text() == ""

    def test_espace_inconnu_ne_declenche_rien(self, panel, monkeypatch):
        """`None` veut dire « je ne sais pas » : un lecteur réseau déconnecté ne
        prouve pas qu'il manque de la place."""
        widget, manager = panel
        _disque(monkeypatch, None)
        _prepare(panel, GameState.NOT_INSTALLED)
        assert widget._alert.isHidden()

    def test_rien_sans_jeu(self, panel):
        widget, _ = panel
        widget.set_game(None)
        widget.refresh()
        assert widget._alert.isHidden()


class TestEspaceDisque:
    def test_bandeau_quand_la_place_manque(self, panel, monkeypatch):
        widget, manager = panel
        _disque(monkeypatch, 50)
        _prepare(panel, GameState.NOT_INSTALLED)
        assert not widget._alert.isHidden()
        assert "Espace insuffisant" in widget._alert.text()

    def test_le_bandeau_propose_de_changer_de_dossier(self, panel, monkeypatch, qtbot):
        widget, manager = panel
        _disque(monkeypatch, 50)
        _prepare(panel, GameState.NOT_INSTALLED)
        assert 'href="settings"' in widget._alert.text()
        with qtbot.waitSignal(widget.settings_requested, timeout=500):
            widget._on_alert_link("settings")

    def test_le_seuil_est_celui_de_la_verification_au_clic(self, panel, monkeypatch):
        """Juste au-dessus du besoin → silence ; juste en dessous → bandeau."""
        from src.core.system_checks import needed_space_mb
        widget, manager = panel
        game = _jeu_telechargeable(manager)
        besoin = needed_space_mb(game.current_download.size_mb)

        _disque(monkeypatch, besoin)
        _prepare(panel, GameState.NOT_INSTALLED)
        assert widget._alert.isHidden()

        _disque(monkeypatch, besoin - 1)
        widget.refresh()
        assert not widget._alert.isHidden()

    def test_pas_de_bandeau_disque_sur_un_jeu_installe(self, panel, monkeypatch):
        """Rien à télécharger : la place libre ne le concerne plus."""
        widget, manager = panel
        _disque(monkeypatch, 1)
        _prepare(panel, GameState.INSTALLED)
        assert widget._alert.isHidden()


class TestHorsLigne:
    def test_bandeau_et_bouton_grise(self, panel, monkeypatch):
        widget, manager = panel
        _disque(monkeypatch, 900_000)
        _prepare(panel, GameState.NOT_INSTALLED)
        widget.set_online(False)
        assert "Hors ligne" in widget._alert.text()
        boutons = [widget._action_layout.itemAt(i).widget()
                   for i in range(widget._action_layout.count())]
        telecharger = [b for b in boutons if b is not None and b.objectName() == "btnDownload"]
        assert telecharger and not telecharger[0].isEnabled()

    def test_le_retour_en_ligne_reactive_tout(self, panel, monkeypatch):
        widget, manager = panel
        _disque(monkeypatch, 900_000)
        _prepare(panel, GameState.NOT_INSTALLED)
        widget.set_online(False)
        widget.set_online(True)
        assert widget._alert.isHidden()
        boutons = [widget._action_layout.itemAt(i).widget()
                   for i in range(widget._action_layout.count())]
        telecharger = [b for b in boutons if b is not None and b.objectName() == "btnDownload"]
        assert telecharger and telecharger[0].isEnabled()

    def test_pas_de_mention_hors_ligne_sur_un_jeu_installe(self, panel, monkeypatch):
        """Il reste parfaitement jouable : le dire serait du bruit."""
        widget, manager = panel
        _disque(monkeypatch, 900_000)
        _prepare(panel, GameState.INSTALLED)
        widget.set_online(False)
        assert widget._alert.isHidden()


class TestPrerequisVCredist:
    def test_bandeau_sur_un_jeu_installe(self, panel, monkeypatch):
        widget, manager = panel
        monkeypatch.setattr("src.core.system_checks.check_vcredist_x86", lambda: False)
        _prepare(panel, GameState.INSTALLED)
        assert "Visual C++" in widget._alert.text()
        assert 'href="vcredist_x86"' in widget._alert.text()

    def test_pas_avant_installation(self, panel, monkeypatch):
        """Rien à lancer encore : l'avertissement viendrait trop tôt."""
        widget, manager = panel
        monkeypatch.setattr("src.core.system_checks.check_vcredist_x86", lambda: False)
        _disque(monkeypatch, 900_000)
        _prepare(panel, GameState.NOT_INSTALLED)
        assert widget._alert.isHidden()

    def test_le_clic_arme_le_re_test_au_retour(self, panel, monkeypatch):
        """Sans re-test, l'avertissement survivrait à l'installation du paquet
        jusqu'au prochain démarrage — le launcher aurait l'air cassé."""
        widget, manager = panel
        ouvert = []
        monkeypatch.setattr("src.ui.action_panel.open_url", ouvert.append)
        monkeypatch.setattr("src.core.system_checks.check_vcredist_x86", lambda: False)
        _prepare(panel, GameState.INSTALLED)

        widget._on_alert_link("vcredist_x86")
        assert ouvert and "vc_redist" in ouvert[0]
        assert widget._awaiting_vcredist is True

        monkeypatch.setattr("src.core.system_checks.check_vcredist_x86", lambda: True)
        widget.recheck_prerequisites()
        assert widget._awaiting_vcredist is False
        assert widget._alert.isHidden()

    def test_recheck_est_muet_sans_demande(self, panel, monkeypatch):
        """Appelé à chaque activation de fenêtre : il ne doit RIEN reconstruire
        tant que l'utilisateur n'est pas parti installer quelque chose."""
        widget, manager = panel
        _disque(monkeypatch, 900_000)
        _prepare(panel, GameState.INSTALLED)
        appels = []
        monkeypatch.setattr(widget, "refresh", lambda: appels.append(1))
        widget.recheck_prerequisites()
        assert appels == []


class TestPriorite:
    """UN SEUL message. Empiler « hors ligne » et « espace insuffisant » coûtait
    80 px et ramenait la barre de défilement sur une fenêtre de 980×660 — pour
    un conseil qui n'est même pas actionnable : hors ligne, rien ne s'écrit."""

    def test_le_hors_ligne_prime_sur_le_disque(self, panel, monkeypatch):
        widget, manager = panel
        _disque(monkeypatch, 50)
        _prepare(panel, GameState.NOT_INSTALLED)
        widget.set_online(False)
        texte = widget._alert.text()
        assert "Hors ligne" in texte
        assert "Espace insuffisant" not in texte

    def test_le_disque_reapparait_une_fois_en_ligne(self, panel, monkeypatch):
        widget, manager = panel
        _disque(monkeypatch, 50)
        _prepare(panel, GameState.NOT_INSTALLED)
        widget.set_online(False)
        widget.set_online(True)
        assert "Espace insuffisant" in widget._alert.text()

    def test_jamais_deux_lignes(self, panel, monkeypatch):
        widget, manager = panel
        _disque(monkeypatch, 50)
        _prepare(panel, GameState.NOT_INSTALLED)
        widget.set_online(False)
        assert "<br>" not in widget._alert.text()

    def test_hauteur_nulle_quand_il_n_y_a_rien_a_dire(self, panel, monkeypatch):
        """`alert_height()` pilote le budget du panneau d'info : il DOIT valoir
        0 dans le cas nominal, sinon on raccourcit la description pour rien."""
        widget, manager = panel
        _disque(monkeypatch, 900_000)
        _prepare(panel, GameState.NOT_INSTALLED)
        assert widget.alert_height() == 0
        widget.set_online(False)
        assert widget.alert_height() > 0
