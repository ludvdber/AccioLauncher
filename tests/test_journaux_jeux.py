"""Les journaux des jeux gardés d'un lancement à l'autre et le « Rapport du jeu » (Ludo, 2026-11-20, après #40)."""
from datetime import datetime, timedelta
from types import SimpleNamespace

from src.core import journaux_jeux as jj
from src.core.game_data import GameData


def _jeu(**extra):
    return GameData.from_dict({
        "id": "hp4", "name": "HP4", "year": 2005, "description": "d", "developer": "d",
        "executable": "HP4/gof_f.exe", "cover_image": "c.jpg", **extra})


def _config(tmp_path):
    return SimpleNamespace(install_path=tmp_path / "jeux", resolution_jeu={})


def _installer(tmp_path, journal=b"[1] Accio Launcher PC fix\n[2] Direct3D: game render target 3840x2160\n"):
    dossier = tmp_path / "jeux" / "HP4"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "gof_f.exe").write_bytes(b"MZ")
    (dossier / "d3d9_accio.log").write_bytes(journal)
    (dossier / "d3d9.ini").write_text(
        "; commentaire\n[Accio.Game]\n; la taille\nWidth=3840\nHeight=2160\n\n[Accio.Graphics]\nSSAAFactor=1\n",
        encoding="utf-8")
    return dossier


def _lancer(jeu, config, racine, quand):
    return jj.au_lancement(jeu, config, (3840, 2160), racine=racine, maintenant=quand)


T0 = datetime(2026, 11, 20, 9, 0, 0)


class TestAuLancement:
    def test_le_premier_lancement_note_ses_reglages(self, tmp_path):
        _installer(tmp_path)
        dossier = _lancer(_jeu(), _config(tmp_path), tmp_path / "r", T0)
        texte = (dossier / jj.PARAMETRES).read_text(encoding="utf-8")
        assert "Résolution écrite : 3840×2160" in texte and "automatique" in texte
        assert "[Accio.Game]\nWidth=3840\nHeight=2160\n[Accio.Graphics]\nSSAAFactor=1" in texte
        assert "commentaire" not in texte and "la taille" not in texte
        assert not list(dossier.glob("*.log")), "les journaux actuels sont ceux d'AVANT ce lancement"

    def test_le_lancement_suivant_range_les_journaux_de_la_partie_precedente(self, tmp_path):
        jeu_dir, config, racine = _installer(tmp_path), _config(tmp_path), tmp_path / "r"
        premier = _lancer(_jeu(), config, racine, T0)
        (jeu_dir / "d3d9_accio.log").write_bytes(b"partie 1\n")      # le jeu a tourné
        _lancer(_jeu(), config, racine, T0 + timedelta(minutes=30))
        assert (premier / "d3d9_accio.log").read_bytes() == b"partie 1\n"
        assert (jeu_dir / "d3d9_accio.log").read_bytes() == b"partie 1\n", "rien n'est retiré du jeu"

    def test_seuls_les_derniers_lancements_restent(self, tmp_path):
        _installer(tmp_path)
        config, racine = _config(tmp_path), tmp_path / "r"
        for i in range(jj.LANCEMENTS + 3):
            _lancer(_jeu(), config, racine, T0 + timedelta(hours=i))
        gardes = jj.lancements("hp4", racine)
        assert len(gardes) == jj.LANCEMENTS
        assert gardes[0].name == (T0 + timedelta(hours=jj.LANCEMENTS + 2)).strftime("%Y-%m-%d_%H-%M-%S")

    def test_deux_lancements_dans_la_meme_seconde(self, tmp_path):
        _installer(tmp_path)
        config, racine = _config(tmp_path), tmp_path / "r"
        a, b = _lancer(_jeu(), config, racine, T0), _lancer(_jeu(), config, racine, T0)
        assert a != b and len(jj.lancements("hp4", racine)) == 2

    def test_un_journal_trop_gros_garde_sa_fin(self, tmp_path, monkeypatch):
        monkeypatch.setattr(jj, "OCTETS_MAX", 100)
        jeu_dir, config, racine = _installer(tmp_path), _config(tmp_path), tmp_path / "r"
        premier = _lancer(_jeu(), config, racine, T0)
        (jeu_dir / "d3d9_accio.log").write_bytes(b"".join(b"ligne %03d\n" % i for i in range(100)))
        _lancer(_jeu(), config, racine, T0 + timedelta(minutes=1))
        garde = (premier / "d3d9_accio.log").read_bytes()
        assert garde.startswith(b"[...]\nligne ") and garde.endswith(b"ligne 099\n") and len(garde) <= 110

    def test_ne_leve_jamais(self, tmp_path):
        _installer(tmp_path)
        bloque = tmp_path / "fichier"
        bloque.write_text("pas un dossier")
        assert jj.au_lancement(_jeu(), _config(tmp_path), None, racine=bloque) is None


class TestParametres:
    def test_seules_les_sections_patchees_du_fichier_du_jeu(self, tmp_path):
        dossier = _installer(tmp_path)
        (dossier / "Game.ini").write_text("[WinDrv.WindowsClient]\nWindowedViewportX=3840\n"
                                          "[Engine.Engine]\nGameRenderDevice=X\n", encoding="utf-8")
        jeu = _jeu(pre_launch={"ini_patches": [{"file": "%INSTALL_DIR%\\Game.ini",
                                                "section": "WinDrv.WindowsClient",
                                                "key": "WindowedViewportX", "value": "1"}]})
        texte = jj.parametres(jeu, _config(tmp_path))
        assert "── Jeu · Game.ini ──\n[WinDrv.WindowsClient]\nWindowedViewportX=3840" in texte
        assert "GameRenderDevice" not in texte

    def test_les_reglages_graphiques_de_hp3_sans_nommer_le_fichier(self, tmp_path):
        dossier = _installer(tmp_path)
        (dossier / "dgVoodoo.conf").write_text("[DirectX]\nResolution=max\n", encoding="utf-8")
        texte = jj.parametres(_jeu(), _config(tmp_path))
        assert "── Réglages graphiques ──\n[DirectX]\nResolution=max" in texte
        assert "dgVoodoo" not in texte

    def test_un_ini_ue1_en_utf16(self, tmp_path):
        dossier = _installer(tmp_path)
        (dossier / "winmm.ini").write_bytes("[Accio.Hardcore]\nDamageTaken=3\n".encode("utf-16"))
        assert "DamageTaken=3" in jj.parametres(_jeu(), _config(tmp_path))

    def test_le_choix_de_resolution_du_joueur(self, tmp_path):
        _installer(tmp_path)
        config = _config(tmp_path)
        config.resolution_jeu["hp4"] = "2560x1440"
        assert "Résolution choisie : 2560x1440" in jj.parametres(_jeu(), config)


class TestRapport:
    def test_reglages_derniere_partie_puis_lancements_gardes(self, tmp_path):
        jeu_dir, config, racine = _installer(tmp_path), _config(tmp_path), tmp_path / "r"
        _lancer(_jeu(), config, racine, T0)
        (jeu_dir / "d3d9_accio.log").write_bytes(b"partie 1\n")
        _lancer(_jeu(), config, racine, T0 + timedelta(minutes=30))
        (jeu_dir / "d3d9_accio.log").write_bytes(b"partie 2\n")
        texte = jj.rapport(_jeu(), config, ["EN-TETE"], racine=racine)
        ordre = [texte.index(m) for m in ("EN-TETE", "══ Réglages actuels ══",
                                          "══ Dernière partie · d3d9_accio.log ══\npartie 2",
                                          "══ Lancement du 2026-11-20 09-30-00 · réglages ══",
                                          "══ Lancement du 2026-11-20 09-00-00 · d3d9_accio.log ══\npartie 1")]
        assert ordre == sorted(ordre)

    def test_sans_lancement_garde(self, tmp_path):
        _installer(tmp_path)
        texte = jj.rapport(_jeu(), _config(tmp_path), ["X"], racine=tmp_path / "vide")
        assert "Réglages actuels" in texte and "game render target 3840x2160" in texte


class TestBouton:
    def test_copier_ecrit_le_rapport_et_le_met_dans_le_presse_papiers(self, qapp, tmp_path, monkeypatch):
        from PyQt6.QtGui import QGuiApplication

        from src.ui import about_page, rapport_jeu
        _installer(tmp_path)
        monkeypatch.setattr(about_page, "dossier_du_rapport", lambda: tmp_path)
        recus: list[str] = []
        vue = SimpleNamespace(manager=SimpleNamespace(installed_version=lambda _id: "1.7",
                                                      config=_config(tmp_path)),
                              notify=SimpleNamespace(emit=recus.append))
        rapport_jeu.copier(vue, _jeu())
        fichier = tmp_path / "Accio Launcher - hp4 - rapport.txt"
        texte = fichier.read_text(encoding="utf-8")
        assert texte.startswith("Rapport de HP4 (hp4) · version du jeu 1.7")
        assert "Réglages actuels" in texte and "game render target 3840x2160" in texte
        urls = QGuiApplication.clipboard().mimeData().urls()
        assert [u.toLocalFile() for u in urls] == [str(fichier).replace("\\", "/")]
        assert recus and "HP4" in recus[0]

    def test_dans_la_rubrique_fichiers_d_un_jeu_installe(self, tmp_path):
        from src.core.game_manager import GameState
        from src.ui import game_detail_handlers as h
        vue = SimpleNamespace(manager=SimpleNamespace(get_state=lambda _id: GameState.INSTALLED))
        libelles = [a.libelle for a in h._actions_fichiers(vue, _jeu())]
        assert "Rapport du jeu" in libelles
