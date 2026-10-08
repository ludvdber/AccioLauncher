"""Reconnaître, au retour du jeu, une configuration qui l'empêche de s'afficher.

Les journaux sont écrits comme le moteur UE1 les écrit (bloc relevé dans un
vrai `HP.log` le 2026-09-26). Documents est celui du conftest.
"""
import os
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from src.core import config_cassee
from src.core.catalogue_blocs import ConfigFile, PostInstall

RENDEV = (
    "Log: Log file open, 10/03/26 15:00:00\r\n"
    "Init: CPU Features: CMov FPU RDTSC PAE MMX KNI\r\n"
    "Critical: appError called:\r\n"
    "Critical: Assertion failed: RenDev [File:C:\\HPotter\\unreal\\WinDrv\\Src\\WinViewport.cpp] [Line: 351]\r\n"
    "Critical: UWindowsViewport::OpenWindow\r\n"
    "Critical: UGameEngine::Init\r\n"
    "Exit: Executing UObject::StaticShutdownAfterError\r\n"
    "Exit: Exiting.\r\n"
)
# Un fichier du JEU qui manque : remettre la configuration n'y ferait rien.
BITMAP = (
    "Critical: appError called:\r\n"
    "Critical: Assertion failed: Bitmap.LoadFile(Filename) [File:..\\..\\Engine\\Inc\\UnEngineWin.h] [Line: 189]\r\n"
    "Critical: Windows GetLastError: Le fichier spécifié est introuvable. (2)\r\n"
    "Exit: Executing UObject::StaticShutdownAfterError\r\n"
)
SAIN = "Log: Getting modelist...\r\nLog: Done.\r\nExit: Exiting.\r\n"
# Cas réel (HP3, joueur sur Intel UHD, 2026-10-06) : l'arrêt PENDANT le dessin.
HP3_INTEL = (
    "Critical: appError called:\r\n"
    "Critical: SetRenderTarget failed(D3DERR_INVALIDCALL).\r\n"
    "Critical: FD3DRenderInterface::SetRenderTarget <- UShadowBitmapMaterial::Get"
    " <- UGameEngine::Draw <- UWindowsViewport::Repaint <- MainLoop\r\n"
)


@pytest.fixture
def jeu(tmp_path):
    game = SimpleNamespace(
        id="hp2", name="Harry Potter II", executable="HP2/system/Game.exe", sauvegardes=None,
        post_install=PostInstall(config_files=(
            ConfigFile("config/Game.ini", "~/Documents/Harry Potter II/Game.ini"),)))
    dossier = tmp_path / "Documents" / "Harry Potter II"
    dossier.mkdir(parents=True)
    return game, dossier


class TestLecture:
    def test_rendev_est_reconnue_et_la_ligne_rendue(self):
        assert config_cassee.erreur_d_affichage(RENDEV).startswith("Assertion failed: RenDev")

    def test_un_fichier_du_jeu_manquant_n_est_pas_une_affaire_de_configuration(self):
        assert config_cassee.erreur_d_affichage(BITMAP) is None

    def test_un_journal_sans_erreur(self):
        assert config_cassee.erreur_d_affichage(SAIN) is None

    def test_un_arret_pendant_le_dessin_n_est_pas_la_configuration(self):
        """Cas réel HP3 sur Intel UHD : l'affichage s'était ouvert, « viewport »
        n'apparaît que dans l'historique du dessin."""
        assert config_cassee.erreur_d_affichage(HP3_INTEL) is None

    def test_le_mot_hors_d_une_ligne_critique_ne_compte_pas(self):
        assert config_cassee.erreur_d_affichage("Log: Viewport opened, RenDev ok\r\n") is None


class TestArretFatal:
    """Tout arrêt compte, avec son genre (audit du 2026-10-07, P1-001)."""

    def test_trois_genres(self):
        assert config_cassee.arret_fatal(RENDEV).genre == config_cassee.AFFICHAGE
        assert config_cassee.arret_fatal(HP3_INTEL).genre == config_cassee.DESSIN
        assert config_cassee.arret_fatal(BITMAP) == config_cassee.Arret(
            "Assertion failed: Bitmap.LoadFile(Filename) [File:..\\..\\Engine\\Inc\\UnEngineWin.h] [Line: 189]",
            config_cassee.AUTRE)

    def test_la_ligne_est_celle_que_le_joueur_a_vue(self):
        assert config_cassee.arret_fatal(HP3_INTEL).ligne == "SetRenderTarget failed(D3DERR_INVALIDCALL)."

    def test_pas_d_arret(self):
        assert config_cassee.arret_fatal(SAIN) is None
        assert config_cassee.arret_fatal("Critical: appError called:\r\n") is None


class TestApresLaPartie:
    def test_journal_de_cette_partie(self, jeu):
        game, dossier = jeu
        (dossier / "Game.log").write_bytes(RENDEV.encode("cp1252"))
        debut = datetime.now() - timedelta(seconds=30)
        assert "RenDev" in config_cassee.apres_la_partie(game, debut).ligne

    def test_journal_d_une_partie_precedente_ignore(self, jeu):
        """Le moteur réécrit son journal à chaque démarrage : un vieux journal
        dit ce qui s'est passé AVANT, pas ce qui vient d'arriver."""
        game, dossier = jeu
        log = dossier / "Game.log"
        log.write_bytes(RENDEV.encode("cp1252"))
        vieux = (datetime.now() - timedelta(hours=2)).timestamp()
        os.utime(log, (vieux, vieux))
        assert config_cassee.apres_la_partie(game, datetime.now() - timedelta(minutes=1)) is None

    def test_nom_du_journal_sans_egard_a_la_casse(self, jeu):
        game, dossier = jeu
        (dossier / "GAME.LOG").write_bytes(RENDEV.encode("cp1252"))
        assert config_cassee.apres_la_partie(game, datetime.now() - timedelta(seconds=5))

    def test_utf16_long_lu_par_la_fin_sans_couper_les_caracteres(self, jeu, monkeypatch):
        """UE1 peut écrire en UTF-16 : lire la FIN d'un gros journal ne doit pas
        décaler les caractères d'un octet (le BOM est au début seulement)."""
        game, dossier = jeu
        monkeypatch.setattr(config_cassee, "_FIN", 1001)       # impair exprès
        texte = "Log: é\r\n" * 2000 + RENDEV
        (dossier / "Game.log").write_bytes(b"\xff\xfe" + texte.encode("utf-16-le"))
        assert "RenDev" in config_cassee.apres_la_partie(game, datetime.now() - timedelta(seconds=5)).ligne

    def test_sans_journal_ni_debut(self, jeu):
        game, _ = jeu
        assert config_cassee.apres_la_partie(game, datetime.now()) is None
        assert config_cassee.apres_la_partie(game, None) is None

    def test_jeu_sans_configuration_declaree(self):
        sans = SimpleNamespace(id="hp5", executable="HP5/hp5.exe", post_install=PostInstall())
        assert config_cassee.journal(sans) is None


class TestProposition:
    """Au retour, la question se pose — et la réponse remet vraiment la configuration."""

    @pytest.fixture
    def handlers(self):
        from src.ui import game_detail_handlers as h
        return h

    def _vue(self, install):
        notes = []
        return SimpleNamespace(
            manager=SimpleNamespace(config=SimpleNamespace(install_path=install)),
            partie_en_cours=lambda: "", notify=SimpleNamespace(emit=notes.append)), notes

    @pytest.mark.parametrize("choix, remise", [(0, True), (1, False), (-1, False)])
    def test_remettre_ou_plus_tard(self, handlers, monkeypatch, jeu, tmp_path, choix, remise):
        game, dossier = jeu
        install = tmp_path / "Jeux"
        (install / "HP2" / "config").mkdir(parents=True)
        (install / "HP2" / "config" / "Game.ini").write_bytes(b"[Engine.Engine]\r\n")
        (dossier / "Game.ini").write_bytes(b"[Engine.Engine]\r\nGameRenderDevice=SoftDrv\r\n")
        questions = []
        monkeypatch.setattr(handlers, "_boite",
                            lambda *a, **k: questions.append((a[3], a[4])) or choix)
        vue, notes = self._vue(install)
        handlers.proposer_apres_plantage(vue, game, "Assertion failed: RenDev")
        texte, boutons = questions[0]
        assert "« Assertion failed: RenDev »" in texte          # la ligne telle quelle
        assert boutons == ("Remettre la configuration", "Plus tard")
        assert ((dossier / "Game.ini").read_bytes() == b"[Engine.Engine]\r\n") is remise
        assert bool(notes) is remise


class TestSession:
    """Le signal part du retour de jeu, après `terminee`, et seulement s'il y a de quoi."""

    def test_signal_apres_un_arret_sur_rendev(self, qtbot, monkeypatch, jeu, tmp_path):
        from src.ui import game_session as gs
        game, dossier = jeu
        manager = SimpleNamespace(
            config=SimpleNamespace(install_path=tmp_path / "Jeux", discord_presence=False),
            add_playtime=lambda *a: False, get_game_by_id=lambda _i: game,
            get_game_path=lambda _i: tmp_path / "Jeux" / "HP2")
        session = gs.GameSession(manager)
        monkeypatch.setattr(gs.reparation_config, "disponible", lambda *_a: True)
        monkeypatch.setattr(gs.captures, "ramasser", lambda *_a: None)
        monkeypatch.setattr(gs.stats, "fermer_session", lambda: None)
        session._game_id, session._debut = "hp2", datetime.now() - timedelta(seconds=20)
        (dossier / "Game.log").write_bytes(RENDEV.encode("cp1252"))
        ordre = []
        session.terminee.connect(lambda *_a: ordre.append("terminee"))
        session.configuration_cassee.connect(lambda gid, ligne: ordre.append((gid, ligne[:24])))
        session._on_game_exited("Harry Potter II", 1, 20.0)
        assert ordre == ["terminee", ("hp2", "Assertion failed: RenDev")]

    def test_pas_de_signal_pour_un_journal_sain(self, qtbot, monkeypatch, jeu, tmp_path):
        from src.ui import game_session as gs
        game, dossier = jeu
        manager = SimpleNamespace(
            config=SimpleNamespace(install_path=tmp_path / "Jeux", discord_presence=False),
            add_playtime=lambda *a: True, get_game_by_id=lambda _i: game,
            get_game_path=lambda _i: tmp_path / "Jeux" / "HP2")
        session = gs.GameSession(manager)
        monkeypatch.setattr(gs.reparation_config, "disponible", lambda *_a: True)
        monkeypatch.setattr(gs.captures, "ramasser", lambda *_a: None)
        monkeypatch.setattr(gs.stats, "fermer_session", lambda: None)
        monkeypatch.setattr(gs.sauvegardes, "attribuer", lambda *_a: None)
        session._game_id, session._debut = "hp2", datetime.now() - timedelta(seconds=20)
        (dossier / "Game.log").write_bytes(SAIN.encode("cp1252"))
        recus = []
        session.configuration_cassee.connect(lambda *a: recus.append(a))
        session._on_game_exited("Harry Potter II", 0, 600.0)
        assert recus == []

    def _session(self, monkeypatch, jeu, tmp_path, remise_possible: bool):
        from src.ui import game_session as gs
        game, _ = jeu
        comptes = []
        manager = SimpleNamespace(
            config=SimpleNamespace(install_path=tmp_path / "Jeux", discord_presence=False),
            add_playtime=lambda *a: comptes.append(a) or False, get_game_by_id=lambda _i: game,
            get_game_path=lambda _i: tmp_path / "Jeux" / "HP2")
        session = gs.GameSession(manager)
        monkeypatch.setattr(gs.reparation_config, "disponible", lambda *_a: remise_possible)
        monkeypatch.setattr(gs.captures, "ramasser", lambda *_a: None)
        monkeypatch.setattr(gs.stats, "fermer_session", lambda: None)
        # Le journal du jeu a déjà dit la cause : Windows n'est pas interrogé.
        monkeypatch.setattr(gs.diagnostic_plantage, "apres_la_partie",
                            lambda *_a: pytest.fail("diagnostic lancé en plus de la boîte"))
        session._game_id, session._debut = "hp2", datetime.now() - timedelta(seconds=200)
        ordre = []
        session.terminee.connect(lambda nom, partie, arret: ordre.append(("terminee", partie, arret)))
        session.configuration_cassee.connect(lambda gid, ligne: ordre.append(("remise", gid)))
        session.arret_fatal.connect(lambda gid, arret: ordre.append(("arret", gid, arret.genre)))
        return session, ordre, comptes

    def test_un_arret_hors_affichage_est_annonce_et_pas_compte(self, qtbot, monkeypatch, jeu, tmp_path):
        """M-04 de l'audit : la boîte « Critical Error » regardée 2 min ne fait
        pas une partie, et l'arrêt reçoit sa boîte au lieu du silence."""
        session, ordre, comptes = self._session(monkeypatch, jeu, tmp_path, True)
        (jeu[1] / "Game.log").write_bytes(BITMAP.encode("cp1252"))
        session._on_game_exited("Harry Potter II", 0, 120.0)
        assert ordre == [("terminee", False, True), ("arret", "hp2", config_cassee.AUTRE)]
        assert comptes[0][4] is True             # add_playtime informé de l'arrêt

    def test_une_erreur_d_affichage_sans_remise_possible_recoit_la_boite_generale(
            self, qtbot, monkeypatch, jeu, tmp_path):
        session, ordre, _ = self._session(monkeypatch, jeu, tmp_path, False)
        (jeu[1] / "Game.log").write_bytes(RENDEV.encode("cp1252"))
        session._on_game_exited("Harry Potter II", 0, 120.0)
        assert ordre == [("terminee", False, True), ("arret", "hp2", config_cassee.AFFICHAGE)]


class TestBoiteDArret:
    """La boîte qui suit un arrêt : le rapport à copier, et pour HP3 un cran plus bas."""

    @pytest.fixture
    def handlers(self):
        from src.ui import game_detail_handlers as h
        return h

    def _vue(self, install, jeu_affiche):
        notes = []
        return SimpleNamespace(
            game=jeu_affiche, manager=SimpleNamespace(config=SimpleNamespace(install_path=install)),
            notify=SimpleNamespace(emit=notes.append)), notes

    def _repondre(self, monkeypatch, handlers, choix):
        boites = []
        monkeypatch.setattr(handlers, "_boite",
                            lambda *a, **k: boites.append((a[3], a[4])) or choix)
        return boites

    @pytest.mark.parametrize("choix, copie", [(0, True), (1, False), (-1, False)])
    def test_copier_le_rapport(self, handlers, monkeypatch, jeu, tmp_path, choix, copie):
        game, _ = jeu
        boites = self._repondre(monkeypatch, handlers, choix)
        copies = []
        monkeypatch.setattr(handlers, "copier_le_rapport", copies.append)
        vue, _ = self._vue(tmp_path, game)
        handlers.signaler_arret(vue, game, config_cassee.arret_fatal(BITMAP))
        texte, boutons = boites[0]
        assert "« Assertion failed: Bitmap.LoadFile" in texte
        assert boutons == ("Copier le rapport", "Fermer")
        assert bool(copies) is copie

    @pytest.fixture
    def hp3(self, tmp_path, monkeypatch, handlers):
        game = SimpleNamespace(id="hp3", name="HP3", executable="HP3/system/hppoa.exe")
        conf = tmp_path / "Jeux" / "HP3" / "system" / "dgVoodoo.conf"
        conf.parent.mkdir(parents=True)
        conf.write_bytes(b"[DirectX]\r\nAntialiasing                        = 8x\r\n"
                         b"\r\n[DirectXExt]\r\nRTTexturesForceScaleAndMSAA         = true\r\n")
        # Hors Windows aussi : c'est la boîte qu'on vérifie, pas la plateforme.
        monkeypatch.setattr(handlers.reglages_graphiques, "disponible", lambda c: c.is_file())
        return game, conf

    def test_hp3_reessaie_un_cran_plus_bas(self, handlers, monkeypatch, hp3, tmp_path):
        game, conf = hp3
        boites = self._repondre(monkeypatch, handlers, 0)
        lances = []
        monkeypatch.setattr(handlers, "on_play", lances.append)
        vue, _ = self._vue(tmp_path / "Jeux", game)
        handlers.signaler_arret(vue, game, config_cassee.arret_fatal(HP3_INTEL))
        assert boites[0][1] == ("Réessayer en 4x", "Copier le rapport", "Fermer")
        assert b"= 4x" in conf.read_bytes()
        assert lances == [vue]

    def test_hp3_copier_ne_change_rien(self, handlers, monkeypatch, hp3, tmp_path):
        game, conf = hp3
        self._repondre(monkeypatch, handlers, 1)
        copies = []
        monkeypatch.setattr(handlers, "copier_le_rapport", copies.append)
        avant = conf.read_bytes()
        vue, _ = self._vue(tmp_path / "Jeux", game)
        handlers.signaler_arret(vue, game, config_cassee.arret_fatal(HP3_INTEL))
        assert copies and conf.read_bytes() == avant

    def test_un_autre_jeu_affiche_n_est_pas_lance(self, handlers, monkeypatch, hp3, tmp_path):
        game, conf = hp3
        self._repondre(monkeypatch, handlers, 0)
        monkeypatch.setattr(handlers, "on_play", lambda _v: pytest.fail("mauvais jeu lancé"))
        vue, notes = self._vue(tmp_path / "Jeux", SimpleNamespace(id="hp1"))
        handlers.signaler_arret(vue, game, config_cassee.arret_fatal(HP3_INTEL))
        assert b"= 4x" in conf.read_bytes() and notes == ["Réglage changé : relancez HP3."]

    def test_plus_rien_a_baisser(self, handlers, monkeypatch, hp3, tmp_path):
        game, conf = hp3
        conf.write_bytes(b"[DirectX]\r\nAntialiasing = off\r\n\r\n"
                         b"[DirectXExt]\r\nRTTexturesForceScaleAndMSAA = false\r\n")
        boites = self._repondre(monkeypatch, handlers, -1)
        vue, _ = self._vue(tmp_path / "Jeux", game)
        handlers.signaler_arret(vue, game, config_cassee.arret_fatal(HP3_INTEL))
        assert boites[0][1] == ("Copier le rapport", "Fermer")
