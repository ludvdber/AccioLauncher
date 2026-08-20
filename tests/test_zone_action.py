"""Le bouton principal ne doit pas descendre loin sous la description.

Signalé par Ludo le 2026-08-20 : « pourquoi le bouton téléchargement est si bas
pour HP2 ». Un trou de 87 px s'ouvrait entre la fin de la description et le
bouton, sur ce jeu-là seulement.

Cause mesurée : `InfoPanel.natural_height()` additionnait
`_action_slot.sizeHint()`, qui annonçait 134 px pour une zone en occupant 68.
L'écart vient de la ligne de statistiques de jeu — un QLabel en `wordWrap`,
dont le `sizeHint` vaut 80 px pour une ligne qui en fait 20. La zone défilante
prenant tout l'excédent (`stretch=1`), ces 66 px devenaient un vide.

**Pourquoi HP2 et lui seul** : la ligne de statistiques est cachée tant qu'on
n'a jamais joué. Sur le poste de Ludo, HP2 était le seul jeu avec du temps de
jeu enregistré — le défaut touchait donc n'importe quel jeu déjà lancé, mais un
seul était dans cet état.

Quatrième occurrence du même piège dans ce projet (titre, bandeau d'alerte,
note « bientôt disponible ») : le `sizeHint` d'un QLabel en `wordWrap` est
calculé à une largeur qui n'est pas la sienne. Le remède reste `heightForWidth`.
"""

import datetime

import pytest

pytest.importorskip("pytestqt")

from src.core.game_data import load_catalog  # noqa: E402

_CATALOG = load_catalog()
_HP2 = next(g for g in _CATALOG.games if g.id == "hp2")


@pytest.fixture
def fenetre(qtbot, tmp_path, monkeypatch):
    """MainWindow sur une config temporaire, à la taille de la capture de Ludo.

    1250×822 logiques = les 1562×1028 physiques de sa capture à l'échelle 125 %.
    """
    def _make(*, temps_de_jeu: int = 0, installe: bool = False):
        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
        monkeypatch.setattr("src.ui.main_window.MainWindow._start_update_check",
                            lambda self: None)
        from src.core.config import Config
        cfg = Config(install_path=tmp_path / "games",
                     cache_path=tmp_path / "games" / ".cache",
                     langue="fr", autoplay_videos=False)
        if temps_de_jeu:
            cfg.playtime_seconds[_HP2.id] = temps_de_jeu
            cfg.last_played[_HP2.id] = datetime.datetime.now().isoformat()
        if installe:
            cfg.installed_versions[_HP2.id] = _HP2.latest_version
            # `_detect_state` regarde le disque : poser vraiment l'exécutable est
            # le seul moyen d'obtenir l'état INSTALLÉ comme en production, donc
            # la zone d'action complète (JOUER + rangée secondaire).
            exe = cfg.install_path / _HP2.executable
            exe.parent.mkdir(parents=True, exist_ok=True)
            exe.write_bytes(b"MZ")
        cfg.save()
        from src.ui.main_window import MainWindow
        win = MainWindow()
        qtbot.addWidget(win)
        win.resize(1250, 822)
        win.show()
        qtbot.waitExposed(win)
        win._detail.set_game(_HP2)
        _stabiliser(qtbot, win)
        return win
    yield _make
    from src.core.i18n import set_language
    set_language("fr")


def _stabiliser(qtbot, win) -> None:
    """Laisse passer les `singleShot(0)` de `_fit_info_height`."""
    for _ in range(4):
        qtbot.wait(10)


def _trou(win) -> int:
    """Pixels vides entre le bas du contenu et le haut de la zone d'action."""
    info = win._detail._info
    lay = info._scroll.widget().layout()
    lay.activate()
    bas = 0
    for i in range(lay.count()):
        w = lay.itemAt(i).widget()
        if w is not None and w.isVisible():
            bas = max(bas, w.mapTo(info, w.rect().bottomLeft()).y())
    haut = info.height()
    for i in range(info._action_slot.count()):
        w = info._action_slot.itemAt(i).widget()
        if w is not None and w.isVisible():
            haut = min(haut, w.mapTo(info, w.rect().topLeft()).y())
    return haut - bas


# Marge de respiration nominale entre la description et le bouton, mesurée sur
# un jeu jamais joué. Le défaut la portait à 87.
_TROU_MAX = 40


class TestHauteurZoneAction:
    def test_une_ligne_de_stats_ne_compte_pas_pour_quatre(self, fenetre, qtbot):
        """La mesure retenue doit être celle de la place RÉELLEMENT occupée."""
        win = fenetre(temps_de_jeu=70)
        info = win._detail._info
        assert info._stats_label.isVisible(), "la ligne de stats doit être là"

        annonce = info._action_slot.sizeHint().height()
        calcul = info._hauteur_zone_action()
        # Place réellement occupée, marges du slot comprises — elles font partie
        # de la zone, même si aucun widget ne les dessine.
        marges = info._action_slot.contentsMargins()
        premier_widget = min(
            info._action_slot.itemAt(i).widget().mapTo(
                info, info._action_slot.itemAt(i).widget().rect().topLeft()).y()
            for i in range(info._action_slot.count())
            if info._action_slot.itemAt(i).widget() is not None
        )
        reel = info.height() - premier_widget + marges.top() + marges.bottom()

        assert abs(calcul - reel) <= 4, (
            f"la hauteur calculée ({calcul}) doit coller à la réalité ({reel})")
        assert calcul < annonce, (
            f"le sizeHint du slot ({annonce}) surestime, il ne doit plus servir")

    def test_un_widget_cache_ne_prend_pas_de_place(self, fenetre, qtbot):
        """Jamais joué : la ligne de stats est cachée, elle ne compte pas."""
        win = fenetre()
        info = win._detail._info
        assert not info._stats_label.isVisible()
        bouton_seul = info._action_slot.itemAt(0).widget().sizeHint().height()
        marges = info._action_slot.contentsMargins()
        assert info._hauteur_zone_action() == (
            bouton_seul + marges.top() + marges.bottom())


class TestTrouSousLaDescription:
    def test_jamais_joue(self, fenetre):
        assert _trou(fenetre()) <= _TROU_MAX

    def test_deja_joue_ne_creuse_pas_le_trou(self, fenetre):
        """Le cas de la capture : c'est le temps de jeu qui révélait le défaut."""
        assert _trou(fenetre(temps_de_jeu=70)) <= _TROU_MAX

    def test_apres_une_desinstallation(self, fenetre, qtbot):
        """L'état exact de la capture : installé, joué, puis désinstallé."""
        win = fenetre(temps_de_jeu=70, installe=True)
        assert _trou(win) <= _TROU_MAX, "déjà creusé avant même la désinstallation"

        (win.manager.config.install_path / _HP2.executable).unlink()
        win.manager.uninstall_game(_HP2.id)
        win._detail._refresh()
        _stabiliser(qtbot, win)

        assert _trou(win) <= _TROU_MAX

    def test_le_temps_de_jeu_ne_change_pas_la_position_du_bouton(self, fenetre):
        """Une ligne de 20 px ne doit pas déplacer le bouton de 60."""
        sans = _trou(fenetre())
        avec = _trou(fenetre(temps_de_jeu=70))
        assert abs(avec - sans) <= 6, (
            f"trou de {sans} px sans temps de jeu, {avec} px avec")


class TestLibelleDuBouton:
    """La durée estimée a été retirée du bouton (demande de Ludo, 2026-08-20).

    Elle allongeait le libellé jusqu'au débordement et promettait un temps
    calculé sur la vitesse du dernier téléchargement — sans raison de valoir
    encore.
    """

    def test_le_bouton_ne_porte_que_le_poids(self, fenetre):
        win = fenetre()
        layout = win._detail._action_panel._action_layout
        libelles = [layout.itemAt(i).widget().text()
                    for i in range(layout.count())
                    if layout.itemAt(i).widget() is not None
                    and hasattr(layout.itemAt(i).widget(), "text")]
        bouton = [x for x in libelles if "TÉLÉCHARGER" in x]
        assert bouton, f"bouton de téléchargement introuvable dans {libelles}"
        assert "≈" not in bouton[0], f"durée estimée encore présente : {bouton[0]!r}"
        assert "Mo" in bouton[0] or "Go" in bouton[0], bouton[0]

    def test_plus_aucune_estimation_de_duree_dans_le_code(self):
        """Les deux helpers ont été retirés : pas de code mort qui traîne."""
        import src.core.formatting as f
        assert not hasattr(f, "estimate_duration")
        assert not hasattr(f, "format_duree")
