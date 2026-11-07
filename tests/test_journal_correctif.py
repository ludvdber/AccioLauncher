"""Le journal du correctif relu au retour d'une partie (`journal_correctif`), son signal et son toast."""
import os
from datetime import datetime, timedelta
from types import SimpleNamespace

from src.core import journal_correctif as jc
from src.ui import toast_correctif

DEMARRAGE = "[100] Accio Launcher PC fix 2.4.0 (d3d9.dll), C:\\Jeux\\HP6\\hp6.exe\n"
SAIN = DEMARRAGE + "[120] Game: 30 fps limit lifted, set\n[130] Overlay: ShowFPS=0\n"
PANNE = (DEMARRAGE
         + "[120] Game: 30 fps wait code not found, left unchanged\n"
         + "[121] Direct3D: refused with MSAA (0x8876086C), again without\n"
         + "[122] Shaders: ps replacement refused (0x1), the game's own used\n"
         + "[130] Game: far plane NOT set: unexpected code (other hp6.exe build?)\n"
         + "[131] Game: 30 fps wait code not found, left unchanged\n")


class TestLignes:
    def test_un_journal_sain_ne_dit_rien(self):
        assert jc.lignes_en_echec(SAIN) == ()

    def test_les_echecs_sans_horodatage_ni_doublon_dans_l_ordre(self):
        assert jc.lignes_en_echec(PANNE) == (
            "Game: 30 fps wait code not found, left unchanged",
            "Game: far plane NOT set: unexpected code (other hp6.exe build?)")

    def test_un_repli_prevu_par_la_dll_n_est_pas_un_echec(self):
        """La DLL a réessayé sans l'option et le jeu tourne : le dire serait alarmer pour rien."""
        assert not any("again without" in ligne or "own used" in ligne for ligne in jc.lignes_en_echec(PANNE))

    def test_seul_le_dernier_demarrage_compte(self):
        """Une DLL qui AJOUTE à son journal : la panne d'hier, corrigée depuis, ne se redit pas."""
        assert jc.lignes_en_echec(PANNE + SAIN) == ()

    def test_un_exe_inconnu_ne_noie_pas_le_toast(self):
        texte = DEMARRAGE + "".join(f"[1] Réglage {i}: NOT set\n" for i in range(30))
        assert len(jc.lignes_en_echec(texte)) == jc.LIGNES_MAX

    def test_un_journal_sans_ligne_de_demarrage_se_lit_en_entier(self):
        assert jc.lignes_en_echec("Menu: hook refused (error 5)\n") == ("Menu: hook refused (error 5)",)


class TestFichiers:
    def test_journaux_de_toutes_les_dll(self, tmp_path):
        (tmp_path / "d3d9_accio.log").write_text(PANNE, encoding="utf-8")
        (tmp_path / "xinput_accio.log").write_text("Game: registry functions not found, PlayStation controllers "
                                                   "not added\n", encoding="utf-8")
        trouves = jc.echecs(tmp_path)
        assert [e.journal for e in trouves] == ["d3d9_accio.log", "d3d9_accio.log", "xinput_accio.log"]

    def test_journal_d_une_partie_precedente_ignore(self, tmp_path):
        journal = tmp_path / "winmm_accio.log"
        journal.write_text(PANNE, encoding="utf-8")
        vieux = (datetime.now() - timedelta(hours=1)).timestamp()
        os.utime(journal, (vieux, vieux))
        assert jc.echecs(tmp_path, datetime.now() - timedelta(seconds=30)) == ()
        assert jc.echecs(tmp_path) != ()          # le rapport, lui, lit le dernier lancement quel qu'il soit

    def test_dossier_absent(self, tmp_path):
        assert jc.echecs(tmp_path / "nulle_part", datetime.now()) == ()

    def test_utf8_abime_ne_coute_pas_la_lecture(self, tmp_path):
        (tmp_path / "dinput8_accio.log").write_bytes(b"\xff\xfe" + PANNE.encode("utf-8"))
        assert len(jc.echecs(tmp_path)) == 2

    def test_signature_stable_et_vide_sans_panne(self, tmp_path):
        (tmp_path / "d3d9_accio.log").write_text(PANNE, encoding="utf-8")
        a, b = jc.echecs(tmp_path), jc.echecs(tmp_path)
        assert jc.signature(a) == jc.signature(b) != ""
        assert jc.signature(()) == ""


class TestConfig:
    def test_la_panne_signalee_survit_au_redemarrage(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
        from src.core.config import Config
        cfg = Config(install_path=tmp_path)
        cfg.correctif_signale["hp6"] = "abc"
        cfg.save()
        assert Config.load().correctif_signale == {"hp6": "abc"}


def _session(monkeypatch, tmp_path, partie: bool):
    from src.ui import game_session as gs
    game = SimpleNamespace(id="hp6", name="Harry Potter VI", executable="HP6/hp6.exe", sauvegardes=None,
                           post_install=None)
    dossier = tmp_path / "Jeux" / "HP6"
    dossier.mkdir(parents=True)
    manager = SimpleNamespace(
        config=SimpleNamespace(install_path=tmp_path / "Jeux", discord_presence=False),
        add_playtime=lambda *a: partie, get_game_by_id=lambda _i: game,
        get_game_path=lambda _i: dossier)
    session = gs.GameSession(manager)
    monkeypatch.setattr(gs.config_cassee, "apres_la_partie", lambda *_a: None)
    monkeypatch.setattr(gs.captures, "ramasser", lambda *_a: None)
    monkeypatch.setattr(gs.stats, "fermer_session", lambda: None)
    monkeypatch.setattr(gs.diagnostic_plantage, "apres_la_partie", lambda *_a: None)
    session._game_id, session._debut = "hp6", datetime.now() - timedelta(seconds=20)
    return session, dossier


class TestSession:
    def test_signal_apres_terminee_quand_le_correctif_a_echoue(self, qtbot, monkeypatch, tmp_path):
        session, dossier = _session(monkeypatch, tmp_path, partie=True)
        (dossier / "d3d9_accio.log").write_text(PANNE, encoding="utf-8")
        ordre = []
        session.terminee.connect(lambda *_a: ordre.append("terminee"))
        session.correctif_en_echec.connect(lambda gid, e: ordre.append((gid, len(e))))
        session._on_game_exited("Harry Potter VI", 0, 600.0)
        assert ordre == ["terminee", ("hp6", 2)]

    def test_le_diagnostic_de_plantage_part_quand_meme(self, qtbot, monkeypatch, tmp_path):
        """Revue du 2026-11-07 : un échec du correctif qui revient à chaque lancement taisait la
        boîte d'un vrai plantage (le toast, lui, ne se redit pas pour la même panne)."""
        from src.ui import game_session as gs
        session, dossier = _session(monkeypatch, tmp_path, partie=True)
        (dossier / "d3d9_accio.log").write_text(PANNE, encoding="utf-8")
        lus = []
        monkeypatch.setattr(gs.diagnostic_plantage, "apres_la_partie", lambda *a: lus.append(a))
        recus = []
        session.correctif_en_echec.connect(lambda *a: recus.append(a))
        session._on_game_exited("Harry Potter VI", 0xC0000005, 600.0)
        qtbot.waitUntil(lambda: bool(lus), timeout=3000)
        assert len(recus) == 1

    def test_rien_pour_un_journal_sain(self, qtbot, monkeypatch, tmp_path):
        session, dossier = _session(monkeypatch, tmp_path, partie=True)
        (dossier / "d3d9_accio.log").write_text(SAIN, encoding="utf-8")
        recus = []
        session.correctif_en_echec.connect(lambda *a: recus.append(a))
        session._on_game_exited("Harry Potter VI", 0, 600.0)
        assert recus == []

    def test_rien_si_le_jeu_n_a_pas_demarre(self, qtbot, monkeypatch, tmp_path):
        """Un jeu fermé aussitôt a déjà son toast d'aide : pas deux toasts."""
        session, dossier = _session(monkeypatch, tmp_path, partie=False)
        (dossier / "d3d9_accio.log").write_text(PANNE, encoding="utf-8")
        recus = []
        session.correctif_en_echec.connect(lambda *a: recus.append(a))
        session._on_game_exited("Harry Potter VI", 1, 2.0)
        assert recus == []


class TestToast:
    """Le toast vit dans `ui/toast_correctif`, branché par la fenêtre sur sa session."""

    def _echecs(self):
        return (jc.Echec("d3d9_accio.log", "Game: far plane NOT set"),)

    def test_dit_une_fois_par_panne(self, make_window, monkeypatch):
        win = make_window()
        jeu = win.manager.catalog.games[0]
        messages = []
        monkeypatch.setattr(win._toast, "show_message", lambda texte, **_k: messages.append(texte))
        monkeypatch.setattr(win._toast, "isVisible", lambda: False)
        toast_correctif.signaler(win, jeu.id, self._echecs())
        toast_correctif.signaler(win, jeu.id, self._echecs())
        assert len(messages) == 1 and "un réglage du correctif n'a pas pu s'appliquer" in messages[0]
        assert win.config.correctif_signale[jeu.id] == jc.signature(self._echecs())

    def test_une_autre_panne_se_dit(self, make_window, monkeypatch):
        win = make_window()
        jeu = win.manager.catalog.games[0]
        messages = []
        monkeypatch.setattr(win._toast, "show_message", lambda texte, **_k: messages.append(texte))
        monkeypatch.setattr(win._toast, "isVisible", lambda: False)
        toast_correctif.signaler(win, jeu.id, self._echecs())
        toast_correctif.signaler(win, jeu.id, (jc.Echec("d3d9_accio.log", "Menu: hook refused (error 5)"),))
        assert len(messages) == 2

    def test_un_toast_deja_affiche_passe_d_abord(self, make_window, monkeypatch):
        """Un succès annoncé garde sa place ; la panne n'est pas marquée dite, elle reviendra."""
        win = make_window()
        jeu = win.manager.catalog.games[0]
        messages = []
        monkeypatch.setattr(win._toast, "show_message", lambda texte, **_k: messages.append(texte))
        monkeypatch.setattr(win._toast, "isVisible", lambda: True)
        toast_correctif.signaler(win, jeu.id, self._echecs())
        assert messages == [] and jeu.id not in win.config.correctif_signale


class TestRapport:
    def test_le_resume_porte_la_panne_du_dernier_lancement(self, tmp_path):
        from src.core import diagnostic
        from tests.test_diagnostic import _faux_manager
        dossier = tmp_path / "HP1" / "System"
        dossier.mkdir(parents=True)
        (dossier / "winmm_accio.log").write_text(PANNE, encoding="utf-8")
        texte = diagnostic.rapport(_faux_manager(tmp_path), tentatives=(), prerequis={}, machine=[],
                                   documents="D", compatibilite="")
        assert "Correctif, réglages non appliqués au dernier lancement :" in texte
        assert "hp1 · winmm_accio.log : Game: far plane NOT set" in texte

    def test_rien_quand_le_correctif_n_a_rien_dit(self, tmp_path):
        from src.core import diagnostic
        from tests.test_diagnostic import _faux_manager
        texte = diagnostic.rapport(_faux_manager(tmp_path), tentatives=(), prerequis={}, machine=[],
                                   documents="D", compatibilite="")
        assert "Correctif, réglages" not in texte

    def test_la_fenetre_branche_le_toast(self, make_window, monkeypatch):
        win = make_window()
        jeu = win.manager.catalog.games[0]
        messages = []
        monkeypatch.setattr(win._toast, "show_message", lambda texte, **_k: messages.append(texte))
        monkeypatch.setattr(win._toast, "isVisible", lambda: False)
        win._session.correctif_en_echec.emit(jeu.id, (jc.Echec("d3d9_accio.log", "Menu: hook refused"),))
        assert len(messages) == 1
