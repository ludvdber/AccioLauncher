"""Filets UI de l'audit du 2026-08-20 : arité des slots, peinture, DPI."""

import pytest

pytest.importorskip("pytestqt")

import inspect  # noqa: E402

from PyQt6.QtCore import QPoint  # noqa: E402
from PyQt6.QtGui import QRegion  # noqa: E402

import src.ui.main_window as mw  # noqa: E402
from src.core.updater import UpdateChecker  # noqa: E402


class TestAriteDesSlots:
    """PyQt tronque SILENCIEUSEMENT les arguments qu'un slot ne déclare pas.

    `launcher_update` porte quatre arguments ; le slot du chemin « Vérifier les
    mises à jour » n'en déclarait que trois. L'empreinte SHA-256 publiée par
    GitHub — le 4ᵉ — était donc jetée, et l'exe d'auto-update installé SANS
    être vérifié, alors que la vérification au démarrage, elle, le vérifiait.
    """

    @staticmethod
    def _arite_du_signal(signal_bound) -> int:
        """Nombre d'arguments déclarés par un signal, lu sur sa signature."""
        signature = signal_bound.signal            # ex. "2launcher_update(QString,QString,QString,QString)"
        args = signature[signature.index("(") + 1:-1]
        return len([a for a in args.split(",") if a])

    def test_launcher_update_porte_bien_quatre_arguments(self):
        checker = UpdateChecker("", "0", {})
        assert self._arite_du_signal(checker.launcher_update) == 4

    def test_le_slot_du_check_force_les_declare_tous(self):
        """Sans ça, l'empreinte est jetée sans le moindre message."""
        src = inspect.getsource(mw.MainWindow._force_update_check)
        ligne = [x for x in src.splitlines() if "def on_launcher" in x]
        assert ligne, "slot on_launcher introuvable"
        params = ligne[0][ligne[0].index("(") + 1:ligne[0].rindex(")")]
        assert len([p for p in params.split(",") if p.strip()]) == 4, (
            f"on_launcher doit déclarer 4 paramètres, vu : {ligne[0].strip()}")

    def test_l_empreinte_arrive_jusqu_au_champ(self, qtbot, tmp_path, monkeypatch):
        """Bout en bout : le signal émis avec une empreinte doit la faire
        atterrir dans `_updates.asset_sha256`."""
        import src.core.config as cfgmod
        from src.core.config import Config

        cfg = tmp_path / "config.json"
        monkeypatch.setattr(cfgmod, "CONFIG_FILE_PATH", cfg)
        Config(install_path=tmp_path / "jeux", cache_path=tmp_path / "cache",
               langue="fr", autoplay_videos=False).save()
        monkeypatch.setattr(mw.MainWindow, "_start_update_check", lambda self: None)

        fenetre = mw.MainWindow()
        qtbot.addWidget(fenetre)
        fenetre._launcher_update_asked = True      # pas de dialogue modal

        empreinte = "b7" * 32
        captures = {}
        monkeypatch.setattr(UpdateChecker, "start",
                            lambda self: captures.setdefault("checker", self))

        class FauxDialogue:
            class _Destroyed:
                @staticmethod
                def connect(*a):
                    pass
            destroyed = _Destroyed()

            def isVisible(self):
                return False

            def show_update_status(self, *a):
                pass

            def update_catalog_version(self, *a):
                pass

        fenetre._force_update_check(FauxDialogue(), catalog_only=False)
        captures["checker"].launcher_update.emit(
            "9.9.9", "https://github.com/ludvdber/AccioLauncher/releases",
            "https://github.com/x/AccioLauncher.exe", empreinte)

        assert fenetre._updates.asset_sha256 == empreinte, (
            "l'auto-update serait téléchargé sans vérification d'intégrité")


class TestPeintureDesParticules:
    """L'overlay est TRANSLUCIDE et couvre toute la fenêtre : un `update()` nu
    oblige Qt à repeindre tout ce qui est dessous, trente fois par seconde,
    pour 35 points de 1,5 à 4 px. Mesuré à 1270×844 : 265 ms/s et 768
    peintures/s avant, 156 ms/s et 563 après — −41 % de CPU, rendu identique.
    """

    @staticmethod
    def _overlay(qtbot, largeur=1270, hauteur=844):
        """Overlay espion, via une SOUS-CLASSE.

        Surtout pas un monkeypatch de `ParticleOverlay.update` : remplacer puis
        « restaurer » cet attribut de CLASSE y laisse le descripteur sip de
        `QWidget.update` posé en attribut Python, et le process finit par
        mourir sur une violation d'accès plusieurs fichiers de tests plus loin.
        """
        from src.ui.particles import ParticleOverlay

        class OverlayEspion(ParticleOverlay):
            def __init__(self):
                super().__init__()
                self.zones = []

            def update(self, *a):
                if a and isinstance(a[0], QRegion):
                    self.zones.append(QRegion(a[0]))
                return super().update(*a)

        overlay = OverlayEspion()
        qtbot.addWidget(overlay)
        overlay.resize(largeur, hauteur)
        overlay.show()
        qtbot.waitExposed(overlay)
        # Chaque test se désabonne du Ticker partagé dans son `finally` : un
        # overlay détruit alors qu'il est encore abonné laisse une connexion
        # morte sur une horloge qui, elle, survit à tout le fichier de tests.
        return overlay

    def test_la_zone_sale_est_bien_plus_petite_que_le_widget(self, qtbot):
        overlay = self._overlay(qtbot)
        try:
            overlay._advance()

            assert overlay.zones, "`_advance` doit déclarer une RÉGION"
            region = overlay.zones[0]
            # PyQt6 n'expose ni `rects()` ni l'itération d'une QRegion : on
            # mesure la fraction sale par échantillonnage d'une grille, ce qui
            # teste directement ce qui compte — « on ne repeint pas tout ».
            pas = 10
            points = [(x, y)
                      for x in range(0, overlay.width(), pas)
                      for y in range(0, overlay.height(), pas)]
            fraction = sum(1 for x, y in points
                           if region.contains(QPoint(x, y))) / len(points)
            assert fraction < 0.35, (
                f"{fraction:.0%} de la fenêtre déclarée sale — la région ne sert à rien")
            assert region != QRegion(overlay.rect())
        finally:
            overlay.pause()

    def test_chaque_particule_est_couverte_avec_sa_marge(self, qtbot):
        """La zone doit englober l'ancienne ET la nouvelle position, glow
        compris — sinon une trainée reste à l'écran."""
        from src.ui.particles import _MARGE_ZONE

        overlay = self._overlay(qtbot, 800, 600)
        try:
            overlay._ensure_particles()
            assert overlay._particles, "aucune particule à vérifier"
            for particule in overlay._particles:
                zone = overlay._zone(particule)
                rayon = max(particule.size, particule.glow_size)
                assert zone.contains(int(particule.x), int(particule.y))
                assert zone.width() >= 2 * (rayon + _MARGE_ZONE)
        finally:
            overlay.pause()


class TestSeparateurDeBarreDeTitre:
    """À une échelle fractionnaire, `drawLine(height() - 1)` en coordonnées
    LOGIQUES tombait une rangée physique au-dessus du vrai bord (38 × 1,25 =
    47,5), laissant une bande de fond nu sous le filet. Même famille que la
    couture du carrousel : on peint au-delà du bord, Qt découpe.
    """

    @staticmethod
    def _code_sans_commentaires(fonction) -> str:
        """Le code seul. Chercher un motif dans la source BRUTE se fait piéger
        par le commentaire qui explique justement pourquoi on ne l'utilise plus."""
        lignes = []
        for ligne in inspect.getsource(fonction).splitlines():
            nu = ligne.split("#", 1)[0]
            if nu.strip():
                lignes.append(nu)
        return chr(10).join(lignes)

    def test_le_filet_deborde_volontairement_sous_le_bord(self):
        from src.ui.title_bar import _DEBORD_PX, TitleBar
        code = self._code_sans_commentaires(TitleBar.paintEvent)
        assert "drawLine" not in code, (
            "drawLine à une coordonnée logique rate le bord physique aux "
            "échelles fractionnaires")
        assert "_DEBORD_PX" in code
        assert _DEBORD_PX >= 1.0
