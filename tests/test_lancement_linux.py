"""Le lancement d'un jeu sous Linux, branché sur la couche de compatibilité.

`sys.platform` est SIMULÉ : ces tests décrivent ce que fait le launcher sous
Linux, et ils tournent aussi sous Windows — un garde-fou qui ne s'arme que là
où le défaut n'existe pas ne garde rien (`test_portabilite_linux.py`). Seuls
ceux qui composent de vrais chemins POSIX sont réservés à Linux.

La machine par défaut est celle de `conftest._linux_pret_a_jouer` : un lanceur
factice (« wine »), un préfixe prêt, les composants Visual C++ en place.
"""

import sys
from pathlib import Path

import pytest

from src.core import compat, game_registry, system_checks
from src.core.config import Config
from src.core.game_data import GameData
from src.core.game_manager import GameManager
from src.core.sauvegardes import racines as _racines_reelles

B = chr(92)
CLE = "SOFTWARE" + B + "Electronic Arts" + B + "Harry Potter and the Deathly Hallows Part 1"

JEU = {
    "id": "hp7a", "name": "HP7", "year": 2010, "description": "d",
    "developer": "EA", "executable": "HP7/pc/hp7.exe", "cover_image": "c.jpg",
    "dll_overrides": ["d3d9"], "dpi_aware": True, "requires": ["vcredist2005_x86"],
    "versions": [],
}


@pytest.fixture
def linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")


def _manager(tmp_path, monkeypatch, jeu=None) -> GameManager:
    from unittest.mock import patch
    from src.core.game_data import Catalog

    game = GameData.from_dict(jeu or JEU)
    exe = tmp_path / "jeux" / game.executable
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"MZ")
    catalogue = Catalog(catalog_version="1", catalog_url="", games=(game,))
    with patch("src.core.game_manager.load_catalog", return_value=catalogue):
        manager = GameManager(Config(install_path=tmp_path / "jeux",
                                     cache_path=tmp_path / "cache"))
    return manager


def _sans_prelancement(monkeypatch, etapes=None):
    for nom in ("unblock_game_dlls", "delete_pre_launch_files", "create_pre_launch_files",
                "restaurer_configs_manquantes", "apply_ini_patches"):
        monkeypatch.setattr("src.core.game_manager." + nom,
                            lambda *a, _nom=nom: etapes.append(_nom) if etapes is not None else None)


def _popen_espion(monkeypatch):
    vus = {}

    def faux(commande, **kwargs):
        vus["commande"] = commande
        vus.update(kwargs)
        return object()
    monkeypatch.setattr("src.core.game_manager.subprocess.Popen", faux)
    return vus


@pytest.mark.usefixtures("linux")
class TestLancementSousWine:
    def test_sans_lanceur_on_le_dit_avant_d_ecrire_quoi_que_ce_soit(
            self, tmp_path, monkeypatch, sans_lanceur):
        m = _manager(tmp_path, monkeypatch)
        etapes = []
        _sans_prelancement(monkeypatch, etapes)
        vus = _popen_espion(monkeypatch)
        with pytest.raises(RuntimeError, match="compat_absent"):
            m.launch_game("hp7a")
        assert not etapes, "rien ne doit être écrit dans un préfixe que personne ne lira"
        assert not vus

    def test_un_lanceur_installe_depuis_est_trouve_sans_redemarrer(self, tmp_path, monkeypatch):
        m = _manager(tmp_path, monkeypatch)
        _sans_prelancement(monkeypatch)
        vus = _popen_espion(monkeypatch)
        faux = compat.Lanceur("wine", "/nonexistent/accio-test/wine")
        reponses = [None]
        monkeypatch.setattr(compat, "lanceur", lambda: reponses[0])
        monkeypatch.setattr(compat, "oublier", lambda: reponses.__setitem__(0, faux))
        assert m.launch_game("hp7a") is not None
        assert vus["commande"][0] == faux.executable

    def test_la_commande_passe_par_le_lanceur(self, tmp_path, monkeypatch, lanceur_factice):
        m = _manager(tmp_path, monkeypatch)
        _sans_prelancement(monkeypatch)
        vus = _popen_espion(monkeypatch)
        m.launch_game("hp7a")
        exe = tmp_path / "jeux" / "HP7" / "pc" / "hp7.exe"
        assert vus["commande"] == [lanceur_factice.executable, str(exe)]
        assert vus["cwd"] == str(exe.parent)
        assert vus["start_new_session"] is True
        assert "creationflags" not in vus

    def test_l_environnement_est_celui_du_prefixe(self, tmp_path, monkeypatch):
        m = _manager(tmp_path, monkeypatch)
        _sans_prelancement(monkeypatch)
        vus = _popen_espion(monkeypatch)
        m.launch_game("hp7a")
        env = vus["env"]
        assert env["WINEPREFIX"] == str(compat.prefixe("wine"))
        assert "d3d9=n,b" in env["WINEDLLOVERRIDES"].split(";")

    def test_dpi_aware_est_ignore_sous_wine(self, tmp_path, monkeypatch):
        """`__COMPAT_LAYER` est une couche de Windows : sans objet sous Wine."""
        # Le processus qui lance la suite peut l'avoir hérité (`RunAsInvoker` : vu en session).
        monkeypatch.delenv("__COMPAT_LAYER", raising=False)
        m = _manager(tmp_path, monkeypatch)
        _sans_prelancement(monkeypatch)
        vus = _popen_espion(monkeypatch)
        m.launch_game("hp7a")
        assert "__COMPAT_LAYER" not in vus["env"]

    def test_la_sortie_de_wine_va_au_journal_du_jeu(self, tmp_path, monkeypatch):
        m = _manager(tmp_path, monkeypatch)
        _sans_prelancement(monkeypatch)
        vus = _popen_espion(monkeypatch)
        m.launch_game("hp7a")
        assert Path(vus["stdout"].name) == compat.journal_du_jeu("hp7a")
        assert vus["stdout"].closed, "notre copie du descripteur doit être fermée"
        assert compat.journal_du_jeu("hp7a").exists()

    def test_un_composant_manquant_bloque_le_lancement(self, tmp_path, monkeypatch):
        (compat.prefixe("wine") / "winetricks.log").write_text("vcrun2022\n", encoding="utf-8")
        system_checks.invalidate_vcredist_cache()
        m = _manager(tmp_path, monkeypatch)
        _sans_prelancement(monkeypatch)
        _popen_espion(monkeypatch)
        with pytest.raises(RuntimeError, match="prerequis_manquant:vcredist2005_x86"):
            m.launch_game("hp7a")

    def test_lancer_quand_meme(self, tmp_path, monkeypatch):
        """Après un échec de winetricks, les composants intégrés à Wine
        suffisent parfois : c'est à l'utilisateur d'essayer."""
        (compat.prefixe("wine") / "winetricks.log").write_text("", encoding="utf-8")
        system_checks.invalidate_vcredist_cache()
        m = _manager(tmp_path, monkeypatch)
        _sans_prelancement(monkeypatch)
        vus = _popen_espion(monkeypatch)
        assert m.launch_game("hp7a", ignorer_prerequis=True) is not None
        assert vus["commande"]

    def test_l_ordre_du_pre_lancement_ne_change_pas(self, tmp_path, monkeypatch):
        m = _manager(tmp_path, monkeypatch)
        etapes = []
        _sans_prelancement(monkeypatch, etapes)
        _popen_espion(monkeypatch)
        m.launch_game("hp7a")
        assert etapes == ["unblock_game_dlls", "delete_pre_launch_files",
                          "create_pre_launch_files", "restaurer_configs_manquantes",
                          "apply_ini_patches"]


def _ecrire_system_reg(texte: str) -> Path:
    pfx = compat.prefixe("wine")
    (pfx / "system.reg").write_text("WINE REGISTRY Version 2\n\n#arch=win64\n\n" + texte,
                                    encoding="utf-8")
    return pfx


@pytest.mark.usefixtures("linux")
class TestRegistreDuPrefixe:
    def test_disponible_quand_lanceur_et_prefixe_existent(self):
        assert game_registry.disponible() is True

    def test_pas_sans_lanceur(self, sans_lanceur):
        assert game_registry.disponible() is False

    def test_pas_avant_la_preparation(self):
        """Écrire lancerait umu pendant que la fenêtre attend — et umu peut
        alors télécharger Proton."""
        (compat.prefixe("wine") / "system.reg").unlink()
        assert game_registry.disponible() is False
        assert game_registry.lire_valeurs("HKLM", CLE, ["Locale"]) == {}

    def test_la_lecture_ne_lance_rien(self, monkeypatch):
        _ecrire_system_reg("[Software\\\\Wow6432Node\\\\Electronic Arts\\\\Harry Potter and "
                           'the Deathly Hallows Part 1] 1\n"Locale"="fr_FR"\n')
        monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("processus lancé"))
        assert game_registry.lire_valeurs("HKLM", CLE, ["Locale"]) == {"Locale": "fr_FR"}

    def test_prevenir_puis_ecrire_puis_relire(self, monkeypatch):
        """Tout le parcours d'`ecrire_valeurs` sous Wine : la prévenance voit
        ce qu'on remplace, l'écriture passe par `_ecrire_eleve`, et c'est la
        RELECTURE du fichier qui dit si ça a pris."""
        entete = ("[Software\\\\Wow6432Node\\\\Electronic Arts\\\\Harry Potter and "
                  "the Deathly Hallows Part 1] 1\n")
        _ecrire_system_reg(entete + '"Locale"="fr_FR"\n')
        vus = {}

        def confirmer(ruche, cle, valeurs, ecarts):
            vus["ecarts"] = ecarts
            return True

        def faux_eleve(ruche, cle, valeurs, vue):
            # Ce que fera le wineserver en s'arrêtant : réécrire system.reg.
            _ecrire_system_reg(entete + '"Locale"="fr"\n')
            return True
        monkeypatch.setattr(game_registry, "_ecrire_eleve", faux_eleve)
        assert game_registry.ecrire_valeurs("HKLM", CLE, {"Locale": "fr"}, attente_s=2,
                                            confirmer=confirmer) is True
        assert vus["ecarts"] == {"Locale": ("fr_FR", "fr")}

    def test_un_refus_n_ecrit_rien(self, monkeypatch):
        _ecrire_system_reg("")
        monkeypatch.setattr(game_registry, "_ecrire_eleve",
                            lambda *a: pytest.fail("écriture malgré le refus"))
        assert game_registry.ecrire_valeurs("HKLM", CLE, {"Locale": "fr"},
                                            confirmer=lambda *a: False) is False


@pytest.mark.skipif(sys.platform == "win32", reason="chemins POSIX du préfixe")
@pytest.mark.usefixtures("linux")
class TestImportParRegedit:
    """`_ecrire_par_wine` : le .reg part dans le préfixe, par le lanceur."""

    def _espion(self, monkeypatch):
        vus = {}

        def faux_run(commande, **kwargs):
            vus["commande"] = commande
            vus["env"] = kwargs["env"]
            fichier = Path(compat.prefixe("wine") / "drive_c" / "windows" / "temp")
            vus["reg"] = [p.read_text(encoding="utf-16") for p in fichier.glob("accio_reg_*/langue.reg")]
            return None
        monkeypatch.setattr(game_registry.subprocess, "run", faux_run)
        return vus

    def test_le_reg_est_pose_dans_le_prefixe_et_importe_en_silence(self, monkeypatch):
        vus = self._espion(monkeypatch)
        assert game_registry._ecrire_par_wine("HKLM", CLE, {"Locale": "fr"}, 32) is True
        commande = vus["commande"]
        assert commande[0] == compat.lanceur().executable
        assert commande[1:3] == ["regedit", "/S"]
        assert commande[3].startswith("C:" + B + "windows" + B + "temp" + B + "accio_reg_")
        assert commande[3].endswith(B + "langue.reg")
        assert len(vus["reg"]) == 1 and "WOW6432Node" in vus["reg"][0]
        assert '"Locale"="fr"' in vus["reg"][0]

    def test_pas_de_mise_a_jour_d_umu_pendant_que_la_fenetre_attend(self, monkeypatch):
        vus = self._espion(monkeypatch)
        game_registry._ecrire_par_wine("HKLM", CLE, {"Locale": "fr"}, 32)
        assert vus["env"]["UMU_RUNTIME_UPDATE"] == "0"
        assert vus["env"]["WINEPREFIX"] == str(compat.prefixe("wine"))

    def test_la_barriere_anti_injection_reste_la_meme(self, monkeypatch):
        """`construire_reg` refuse bruyamment : rien n'est importé."""
        vus = self._espion(monkeypatch)
        assert game_registry._ecrire_par_wine(
            "HKLM", CLE, {"Locale": "fr\r\n[HKLM\\x]"}, 32) is False
        assert "commande" not in vus

    def test_sans_lanceur_rien(self, monkeypatch, sans_lanceur):
        vus = self._espion(monkeypatch)
        assert game_registry._ecrire_par_wine("HKLM", CLE, {"Locale": "fr"}, 32) is False
        assert not vus

    def test_les_dossiers_temporaires_sont_retires(self, monkeypatch):
        self._espion(monkeypatch)
        game_registry._ecrire_par_wine("HKLM", CLE, {"Locale": "fr"}, 32)
        game_registry._nettoyer_reg()
        temp = compat.prefixe("wine") / "drive_c" / "windows" / "temp"
        assert not list(temp.glob("accio_reg_*"))


def _winsxs_vc80(pfx: Path, marque: bytes) -> None:
    dossier = (pfx / "drive_c" / "windows" / "winsxs"
               / "x86_microsoft.vc80.crt_1fc8b3b9a1e18e3b_8.0.50727.6195_none_deadbeef")
    dossier.mkdir(parents=True)
    (dossier / "msvcr80.dll").write_bytes(b"MZ" + bytes(0x3E) + marque + bytes(16))


@pytest.mark.usefixtures("linux")
class TestPrerequisDansLePrefixe:
    @pytest.fixture(autouse=True)
    def _caches_vides(self):
        system_checks.invalidate_vcredist_cache()
        yield
        system_checks.invalidate_vcredist_cache()

    def _vider_winetricks(self):
        (compat.prefixe("wine") / "winetricks.log").write_text("", encoding="utf-8")

    def test_le_journal_de_winetricks_suffit(self):
        assert system_checks.prerequis_manquants(
            ("vcredist_x86", "vcredist2005_x86", "vcredist2008_x86")) == []

    def test_sans_rien_dans_le_prefixe(self):
        self._vider_winetricks()
        assert system_checks.prerequis_manquants(
            ("vcredist_x86", "vcredist2005_x86", "vcredist2008_x86")) == [
            "vcredist_x86", "vcredist2005_x86", "vcredist2008_x86"]

    def test_un_prefixe_pas_encore_cree_n_a_rien(self):
        (compat.prefixe("wine") / "system.reg").unlink()
        assert system_checks.check_vcredist_x86() is False

    def test_sans_lanceur_l_absence_de_wine_est_signalee_ailleurs(self, sans_lanceur):
        assert system_checks.check_vcredist_2005_x86() is True

    def test_les_dll_internes_de_wine_ne_comptent_pas(self):
        """Un préfixe NEUF a déjà un WinSxS VC80 rempli des DLL de Wine."""
        self._vider_winetricks()
        _winsxs_vc80(compat.prefixe("wine"), b"Wine builtin DLL")
        assert system_checks.check_vcredist_2005_x86() is False

    def test_le_vrai_redistribuable_installe_a_la_main(self):
        self._vider_winetricks()
        _winsxs_vc80(compat.prefixe("wine"), b"This program cannot be run")
        assert system_checks.check_vcredist_2005_x86() is True

    def test_vc14_par_sa_cle_de_registre(self):
        self._vider_winetricks()
        _ecrire_system_reg("[Software\\\\Wow6432Node\\\\Microsoft\\\\VisualStudio\\\\14.0"
                           "\\\\VC\\\\Runtimes\\\\x86] 1\n\"Installed\"=dword:00000001\n")
        assert system_checks.check_vcredist_x86() is True

    def test_un_vcrun_plus_ancien_de_la_meme_famille_suffit(self):
        (compat.prefixe("wine") / "winetricks.log").write_text("vcrun2019\n", encoding="utf-8")
        assert system_checks.check_vcredist_x86() is True

    def test_chaque_identifiant_a_son_verbe(self):
        assert set(system_checks.VERBES_WINETRICKS) == set(system_checks.PREREQUIS)


@pytest.mark.skipif(sys.platform == "win32", reason="chemins POSIX du préfixe")
@pytest.mark.usefixtures("linux")
class TestCheminsDuJeu:
    """Ce que Python ouvre est un chemin de l'hôte ; ce que le JEU lit, un
    chemin Windows."""

    def test_documents_et_appdata_sont_ceux_du_prefixe(self):
        from src.core.config import get_documents_dir
        profil = compat.profil(compat.prefixe("wine"))
        assert get_documents_dir() == (profil / "Documents").resolve()
        assert _racines_reelles() == {"documents": (profil / "Documents").resolve(),
                                      "localappdata": profil / "AppData" / "Local"}

    def test_une_valeur_d_ini_est_un_chemin_windows(self, tmp_path, monkeypatch):
        from src.core import pre_launch
        docs = compat.documents(compat.prefixe("wine"))
        monkeypatch.setattr(pre_launch, "get_documents_dir", lambda: docs)
        jeu = GameData.from_dict({**JEU, "executable": "HP1/System/HP.exe"})
        valeur = pre_launch.substituer_pour_le_jeu(
            "%DOCUMENTS%" + B + "Harry Potter" + B + "Save", jeu, Config(install_path=tmp_path))
        profil = compat.profil(compat.prefixe("wine")).name
        assert valeur == B.join(["C:", "users", profil, "Documents", "Harry Potter", "Save"])

    def test_install_dir_est_un_chemin_z(self, tmp_path, monkeypatch):
        """Le test que `test_game_manager.test_install_dir_est_substitue`
        annonçait « pour le jour du portage » : sous Wine, `Install Dir` est
        un chemin `Z:\\…`, pas un chemin POSIX."""
        m = _manager(tmp_path, monkeypatch, {**JEU, "language_registry": {
            "root": "HKLM", "key": CLE, "values": {"Install Dir": "%INSTALL_DIR%" + B},
            "languages": {"fr": {"label": "Français", "values": {"Locale": "fr_FR"}}}}})
        valeurs = m.valeurs_registre(m.get_game_by_id("hp7a"), "fr")
        attendu = "Z:" + str(tmp_path / "jeux" / "HP7").replace("/", B) + B
        assert valeurs["Install Dir"] == attendu

    def test_le_patch_d_ini_suit_la_page_de_codes_du_prefixe(self, tmp_path, monkeypatch):
        """Un profil Wine en cyrillique, un préfixe en 1251 : le moteur relit
        ses INI dans SA page de codes."""
        from src.core import pre_launch
        pfx = _ecrire_system_reg("[System\\\\CurrentControlSet\\\\Control\\\\Nls\\\\Codepage] 1\n"
                                 '"ACP"="1251"\n')
        profil = pfx / "drive_c" / "users" / "дмитрий"
        docs = profil / "Documents"
        (docs / "Harry Potter").mkdir(parents=True)
        ini = docs / "Harry Potter" / "HP.ini"
        ini.write_bytes(b"[Core.System]\r\nSavePath=x\r\n")
        monkeypatch.setattr(pre_launch, "get_documents_dir", lambda: docs)
        jeu = GameData.from_dict({**JEU, "executable": "HP1/System/HP.exe", "pre_launch": {
            "ini_patches": [{"file": "%DOCUMENTS%" + B + "Harry Potter" + B + "HP.ini",
                             "section": "Core.System", "key": "SavePath",
                             "value": "%DOCUMENTS%" + B + "Harry Potter" + B + "Save"}]}})
        pre_launch.apply_ini_patches(jeu, Config(install_path=tmp_path))
        attendu = "SavePath=C:" + B + B.join(["users", "дмитрий", "Documents",
                                              "Harry Potter", "Save"])
        assert attendu.encode("cp1251") + b"\r\n" in ini.read_bytes()

    def test_la_config_livree_va_dans_le_prefixe(self):
        from src.core import post_install
        racines = post_install.allowed_config_roots()
        profil = compat.profil(compat.prefixe("wine"))
        assert profil / "Saved Games" in racines
        assert not any(r == Path.home() for r in racines)


class TestSurveillanceSousWine:
    def test_l_exe_du_jeu_et_non_le_lanceur(self):
        from src.ui.process_monitor import ProcessMonitor
        assert ProcessMonitor._nom_de_l_exe(
            ["/usr/bin/umu-run", "/home/l/Games/HP1/System/HP.exe"]) == "hp.exe"
        assert ProcessMonitor._nom_de_l_exe(["C:" + B + "Jeux" + B + "hp8.exe"]) == "hp8.exe"
        assert ProcessMonitor._nom_de_l_exe([]) == ""

    def test_le_repli_cherche_dans_notre_prefixe(self, monkeypatch, linux):
        from src.ui.process_monitor import ProcessMonitor
        vus = []
        monkeypatch.setattr(compat, "processus_du_jeu",
                            lambda exe, pfx: vus.append((exe, pfx)) or True)
        assert ProcessMonitor._is_exe_running("hp.exe") is True
        assert vus == [("hp.exe", compat.prefixe("wine"))]

    def test_sans_lanceur_aucun_jeu_n_a_pu_partir(self, monkeypatch, linux, sans_lanceur):
        from src.ui.process_monitor import ProcessMonitor
        monkeypatch.setattr(compat, "processus_du_jeu", lambda *a: pytest.fail("appelé"))
        assert ProcessMonitor._is_exe_running("hp.exe") is False

