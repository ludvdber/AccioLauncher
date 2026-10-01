"""Rapport de dépannage complet et case « administrateur » (2026-10-01).

Deux retours du même rapport Discord : HP2 refusé par Windows (`WinError 740`)
sans explication, et des journaux qu'il faut aller chercher dans des dossiers
dont la personne ne se souvient plus.
"""

from pathlib import Path
from types import SimpleNamespace

from src.core import diagnostic, win_utils
from src.core.game_manager import GameState


class TestCaseAdministrateur:
    def test_seules_les_ruches_qui_portent_runasadmin(self):
        couches = {"HKCU": ["RUNASADMIN", "WINXPSP3"], "HKLM": ["HIGHDPIAWARE"]}
        assert win_utils.exige_l_administrateur(couches) == ["HKCU"]

    def test_rien_de_pose_rien_d_exige(self):
        assert win_utils.exige_l_administrateur({}) == []

    def test_hors_windows_aucune_lecture(self, monkeypatch):
        monkeypatch.setattr(win_utils.sys, "platform", "linux")
        assert win_utils.couches_de_compatibilite(Path("/jeux/Game.exe")) == {}


class TestBoiteAdministrateur:
    def _ouvrir(self, monkeypatch, couches, reponse=1):
        from src.ui import game_detail_handlers as gdh
        vus, ouverts = [], []
        monkeypatch.setattr(gdh, "_boite", lambda icone, vue, titre, texte, choix=(), defaut=0:
                            vus.append((titre, texte, choix)) or reponse)
        monkeypatch.setattr(gdh, "open_local_path", ouverts.append)
        monkeypatch.setattr("src.core.win_utils.couches_de_compatibilite", lambda exe: couches)
        exe = Path("C:/Jeux/HP2/system/Game.exe")
        gdh.signaler_elevation(SimpleNamespace(game=SimpleNamespace(name="HP2")), exe)
        return vus, ouverts, exe

    def test_nomme_le_fichier_et_la_case(self, monkeypatch):
        vus, _, exe = self._ouvrir(monkeypatch, {"HKCU": ["RUNASADMIN"]})
        texte = vus[0][1]
        assert str(exe) in texte and "administrateur" in texte
        assert "tous les utilisateurs" not in texte

    def test_cochee_pour_tous_le_dit(self, monkeypatch):
        vus, _, _ = self._ouvrir(monkeypatch, {"HKLM": ["RUNASADMIN"]})
        assert "cochée pour tous les utilisateurs" in vus[0][1]

    def test_non_vue_renvoie_aussi_vers_tous_les_utilisateurs(self, monkeypatch):
        vus, _, _ = self._ouvrir(monkeypatch, {})
        assert "Si elle n'est pas cochée" in vus[0][1]

    def test_le_bouton_ouvre_le_dossier_du_jeu(self, monkeypatch):
        _, ouverts, exe = self._ouvrir(monkeypatch, {}, reponse=0)
        assert ouverts == [str(exe.parent)]


class TestLireLaFin:
    def test_utf16_du_moteur_ue1(self, tmp_path):
        f = tmp_path / "HP.log"
        f.write_bytes("Log: Démarrage\r\n".encode("utf-16"))
        assert "Démarrage" in diagnostic.lire_la_fin(f)

    def test_ansi_ne_coute_pas_le_reste(self, tmp_path):
        f = tmp_path / "Game.log"
        f.write_bytes("Frédéric\n".encode("cp1252"))
        assert "Frédéric" in diagnostic.lire_la_fin(f)

    def test_garde_la_fin_sur_une_ligne_entiere(self, tmp_path):
        f = tmp_path / "d3d9_accio.log"
        f.write_text("".join(f"ligne {i}\n" for i in range(1000)), encoding="utf-8")
        texte = diagnostic.lire_la_fin(f, n=100)
        assert texte.startswith("[…]\nligne ") and texte.rstrip().endswith("ligne 999")

    def test_absent_est_dit(self, tmp_path):
        assert "illisible" in diagnostic.lire_la_fin(tmp_path / "rien.log")


class TestJournauxDesJeux:
    def test_seuls_les_jeux_installes(self, tmp_path):
        for dossier in ("HP4", "HP5"):
            (tmp_path / dossier).mkdir()
            (tmp_path / dossier / "d3d9_accio.log").write_text("x", encoding="utf-8")
        jeux = [SimpleNamespace(id="hp4", executable="HP4/gof_f.exe", sauvegardes=None),
                SimpleNamespace(id="hp5", executable="HP5/hp.exe", sauvegardes=None)]
        etats = {"hp4": GameState.INSTALLED, "hp5": GameState.NOT_INSTALLED}
        manager = SimpleNamespace(
            catalog=SimpleNamespace(games=jeux), get_state=etats.get,
            config=SimpleNamespace(install_path=tmp_path))
        assert [nom for nom, _ in diagnostic.journaux_des_jeux(manager)] == [
            "hp4 · d3d9_accio.log"]


class TestRapportComplet:
    def test_chaque_journal_sous_son_titre_et_chemins_caches(self):
        maison = str(Path.home())
        texte = diagnostic.rapport_complet(
            "Accio Launcher 1.1.3", [("hp6 · xinput_accio.log", f"{maison}\\Games\\x\n")])
        assert "══ hp6 · xinput_accio.log ══" in texte
        assert maison not in texte


class TestBoutonDiagnostic:
    def test_le_fichier_et_le_resume_partent_ensemble(self, qtbot, tmp_path):
        from src.ui import about_page
        fichier = tmp_path / about_page.NOM_RAPPORT
        donnees = about_page.presse_papiers("résumé", fichier)
        assert donnees.text() == "résumé"
        assert [u.toLocalFile() for u in donnees.urls()] == [fichier.as_posix()]

    def test_le_rapport_est_ecrit_avec_les_journaux(self, qtbot, tmp_path, monkeypatch):
        from src.ui import about_page
        logs = tmp_path / "logs"
        logs.mkdir()
        (logs / "accio_launcher.log").write_text("ERROR: panne", encoding="utf-8")
        monkeypatch.setattr(about_page, "LOG_DIR", logs)
        monkeypatch.setattr(about_page, "dossier_du_rapport", lambda: tmp_path)
        monkeypatch.setattr(about_page.diagnostic, "journaux_des_jeux", lambda m: [])
        chemin = about_page.enregistrer_rapport(None, "résumé")
        texte = chemin.read_text(encoding="utf-8")
        assert texte.startswith("résumé") and "ERROR: panne" in texte

    def test_un_bureau_en_lecture_seule_ne_casse_rien(self, qtbot, tmp_path, monkeypatch):
        from src.ui import about_page
        monkeypatch.setattr(about_page, "LOG_DIR", tmp_path)
        monkeypatch.setattr(about_page, "dossier_du_rapport", lambda: tmp_path / "absent")
        monkeypatch.setattr(about_page.diagnostic, "journaux_des_jeux", lambda m: [])
        assert about_page.enregistrer_rapport(None, "résumé") is None
