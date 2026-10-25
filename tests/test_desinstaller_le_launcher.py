"""Désinstaller le launcher : ce qui part, ce qui reste, et le script qui efface.

Aucun test ne lance de script : `programmer` est toujours remplacé.
"""

import pytest

from src.core import desinstallation as d


@pytest.fixture
def poste(tmp_path, monkeypatch):
    """Un dossier de jeux avec son `_Launcher`, deux jeux et des copies de sauvegardes."""
    racine = tmp_path / "Games" / "AccioLauncher"
    donnees = racine / "_Launcher"
    (donnees / "logs").mkdir(parents=True)
    (donnees / "copies_sauvegardes" / "hp4").mkdir(parents=True)
    (donnees / "config.json").write_text("{}", encoding="utf-8")
    for jeu in ("HP1", "HP4"):
        (racine / jeu).mkdir()
    monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", donnees / "config.json")
    return racine


class TestInventaire:
    def test_garder_les_jeux_n_efface_que_le_launcher(self, poste):
        inv = d.inventaire(poste, [poste / "HP1", poste / "HP4"], garder_jeux=True,
                           garder_copies=False)
        assert inv.dossiers == (poste / "_Launcher",)
        assert poste in inv.si_vides, "la racine ne part que vide : les jeux la gardent"

    def test_effacer_les_jeux(self, poste):
        inv = d.inventaire(poste, [poste / "HP1", poste / "HP4"], garder_jeux=False,
                           garder_copies=False)
        assert poste / "HP1" in inv.dossiers and poste / "HP4" in inv.dossiers

    def test_un_dossier_hors_du_dossier_des_jeux_n_est_jamais_efface(self, poste, tmp_path):
        ailleurs = tmp_path / "Documents" / "HP1"
        inv = d.inventaire(poste, [ailleurs], garder_jeux=False, garder_copies=False)
        assert ailleurs not in inv.dossiers

    def test_les_copies_de_sauvegardes_restent(self, poste):
        inv = d.inventaire(poste, [], garder_jeux=True, garder_copies=True)
        donnees = poste / "_Launcher"
        assert donnees not in inv.dossiers, "le dossier entier emporterait les copies"
        assert donnees / "copies_sauvegardes" not in inv.dossiers
        assert donnees / "logs" in inv.dossiers
        assert donnees / "config.json" in inv.fichiers

    def test_rien_n_est_touche_en_listant(self, poste):
        d.inventaire(poste, [poste / "HP1"], garder_jeux=False)
        assert (poste / "HP1").is_dir() and (poste / "_Launcher" / "logs").is_dir()


class TestScriptWindows:
    def test_aucun_chemin_dans_le_corps(self, poste):
        """Règle 79 : cmd.exe relit le .bat en page OEM ; les chemins voyagent par l'environnement."""
        inv = d.inventaire(poste / "Frédéric", [], garder_jeux=True, garder_copies=False,
                           programme=poste / "Accio Launcher.exe")
        corps, variables = d.corps_windows(inv)
        corps.encode("ascii")
        assert str(poste) not in corps
        assert variables["ACCIO_EXE"].endswith("Accio Launcher.exe")
        assert all(ligne.endswith("\r") for ligne in corps.split("\n")[:-1]), "fins de ligne CRLF"

    def test_la_racine_n_est_retiree_que_vide(self, poste):
        inv = d.inventaire(poste, [], garder_jeux=True, garder_copies=False)
        corps, variables = d.corps_windows(inv)
        cle = next(k for k, v in variables.items() if v == str(poste))
        assert f'rmdir "%{cle}%"' in corps and f'rmdir /s /q "%{cle}%"' not in corps



class TestScriptLinux:
    def test_les_cibles_dans_l_ordre_et_le_si_vide_marque(self, poste, monkeypatch):
        """Les chemins arrivent en arguments, jamais dans le script ; « V: »
        marque ce qui ne part que vide."""
        import sys
        lances = []
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(d.subprocess, "Popen", lambda args, **k: lances.append((args, k)))
        inv = d.Inventaire((poste / "_Launcher",), poste / "Accio.AppImage", (poste,),
                           (poste / "_Launcher" / "config.json",))
        assert d.programmer(inv)
        args, options = lances[0]
        assert args[:4] == ["/bin/sh", "-c", d._SCRIPT_SH, "accio-desinstallation"]
        assert args[4:] == [str(poste / "_Launcher"), str(poste / "_Launcher" / "config.json"),
                            str(poste / "Accio.AppImage"), f"V:{poste}"]
        assert str(poste) not in d._SCRIPT_SH
        assert options["env"]["ACCIO_PID"]

    def test_un_echec_au_lancement_ne_promet_rien(self, poste, monkeypatch):
        import sys
        monkeypatch.setattr(sys, "platform", "linux")

        def refuse(*_a, **_k):
            raise OSError("pas de /bin/sh")
        monkeypatch.setattr(d.subprocess, "Popen", refuse)
        assert not d.programmer(d.Inventaire((poste / "_Launcher",), None))

    @pytest.mark.skipif(not __import__("sys").platform.startswith("linux"), reason="/bin/sh : Linux")
    def test_bout_en_bout_efface_apres_la_fin_et_garde_un_dossier_non_vide(self, tmp_path):
        """Le vrai script, sur des dossiers jetables : il attend la mort du
        processus, efface les cibles, et ne retire « V: » que vide."""
        import subprocess
        cible = tmp_path / "_Launcher"
        (cible / "logs").mkdir(parents=True)
        vide, plein = tmp_path / "vide", tmp_path / "plein"
        vide.mkdir()
        (plein / "HP1").mkdir(parents=True)
        dormeur = subprocess.Popen(["sleep", "1"])
        subprocess.run(["/bin/sh", "-c", d._SCRIPT_SH, "test", str(cible), f"V:{vide}", f"V:{plein}"],
                       env={"ACCIO_PID": str(dormeur.pid), "PATH": "/usr/bin:/bin"}, timeout=30)
        dormeur.wait()
        assert not cible.exists() and not vide.exists()
        assert (plein / "HP1").is_dir(), "un dossier qui contient un jeu reste"


def test_programmer_passe_par_le_script_detache(poste, monkeypatch):
    import sys
    appels = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("src.core.self_update.executer_apres_la_fin",
                        lambda corps, prefixe, variables: appels.append(prefixe) or True)
    assert d.programmer(d.inventaire(poste, [], garder_jeux=True))
    assert appels == ["accio_desinstallation_"]


class TestLaFenetre:
    def test_tout_est_garde_par_defaut(self, qtbot, tmp_path):
        from src.ui.desinstallation_dialog import DesinstallationDialog
        dlg = DesinstallationDialog(tmp_path, 3 * 1024 ** 3, True)
        qtbot.addWidget(dlg)
        assert dlg.garder_jeux and dlg.garder_copies

    def test_effacer_les_jeux_le_dit_en_clair(self, qtbot, tmp_path):
        from src.ui.desinstallation_dialog import DesinstallationDialog
        dlg = DesinstallationDialog(tmp_path, 3 * 1024 ** 3, True)
        qtbot.addWidget(dlg)
        dlg.tgl_jeux._basculer()          # comme un clic
        assert not dlg.garder_jeux
        assert "effacés" in dlg._ligne_jeux.description.text()

    def test_sans_jeu_la_question_ne_se_pose_pas(self, qtbot, tmp_path):
        from src.ui.desinstallation_dialog import DesinstallationDialog
        dlg = DesinstallationDialog(tmp_path, 0, False)
        qtbot.addWidget(dlg)
        dlg.tgl_jeux.setChecked(False)
        assert dlg.garder_jeux, "une question cachée ne peut pas avoir reçu de réponse"


class _Session:
    def __init__(self, nom):
        self.nom_en_cours = nom


class _FausseFenetre:
    def __init__(self, nom_en_cours="", tmp_path=None):
        from src.core.config import Config
        self._session = _Session(nom_en_cours)
        self.config = Config(install_path=tmp_path)
        self.manager = type("M", (), {"get_games": lambda _s: [], "get_game_path": lambda _s, _i: None})()
        self.fermee = False

    def _confirmer_fermeture(self):
        return True

    def _fermer_sans_demander(self):
        self.fermee = True


def test_une_partie_en_cours_bloque(monkeypatch, tmp_path):
    from src.ui import desinstallation_dialog as module
    messages = []
    monkeypatch.setattr(module, "avertir", lambda *a: messages.append(a[1]))
    monkeypatch.setattr(module.desinstallation, "programmer", lambda _inv: pytest.fail("lancé"))
    fenetre = _FausseFenetre("HP4", tmp_path)
    assert not module.desinstaller(fenetre, None, True, True)
    assert messages and not fenetre.fermee


def test_programme_puis_ferme(monkeypatch, tmp_path):
    from src.ui import desinstallation_dialog as module
    monkeypatch.setattr(module.desinstallation, "programmer", lambda _inv: True)
    fenetre = _FausseFenetre("", tmp_path)
    assert module.desinstaller(fenetre, None, True, True)
    assert fenetre.fermee
