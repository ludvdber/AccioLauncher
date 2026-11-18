"""Qualité du rendu D3D11 de HP1/HP2 et carte graphique la plus puissante (1.3.6-beta.1).

Constat du 2026-11-18 : HP1 et HP2 à 5 images/s sur un portable, leur rendu
installé au maximum et rien pour le régler dans le launcher.
"""

import sys
from types import SimpleNamespace

import pytest

from src.core import preference_gpu, qualite_rendu
from src.core.config import Config
from src.core.game_data import GameData
from src.core.pre_launch import _INI_ENCODING

B = chr(92)
CRLF = "\r\n"
FICHIER = "%DOCUMENTS%" + B + "Harry Potter II" + B + "Game.ini"

JEU = {
    "id": "hp2", "name": "HP2", "year": 2002, "description": "d",
    "developer": "dev", "executable": "HP2/system/Game.exe", "cover_image": "c.png",
    "pre_launch": {"ini_patches": [
        {"file": FICHIER, "section": "D3D11Drv.D3D11RenderDevice", "key": "Borderless",
         "value": "True"},
    ]},
}

# Tel que l'installation le livre, avec ce qui ne nous regarde pas autour (profil
# accentué, une autre section qui porte des clés du même nom).
INI = (
    "[Engine.Engine]" + CRLF
    + "GameRenderDevice=D3D11Drv.D3D11RenderDevice" + CRLF
    + "[Core.System]" + CRLF
    + "SavePath=C:" + B + "Users" + B + "Frédéric" + B + "Save" + CRLF
    + "[D3D11Drv.D3D11RenderDevice]" + CRLF
    + "Coronas=True" + CRLF
    + "VolumetricLighting=True" + CRLF
    + "Antialiasing=8" + CRLF
    + "Anisotropy=16" + CRLF
    + "ParallaxOcclusionMapping=True" + CRLF
    + "HDR=True" + CRLF
    + "UnlimitedViewDistance=True" + CRLF
    + "ASSAO=True" + CRLF
    + "SSR=True" + CRLF
    + "Borderless=True" + CRLF
    + CRLF
    + "[D3DDrv.D3DRenderDevice]" + CRLF
    + "Antialiasing=8" + CRLF
    + "HDR=True" + CRLF
)


@pytest.fixture
def hp2(tmp_path, monkeypatch):
    docs = tmp_path / "Documents"
    ini = docs / "Harry Potter II" / "Game.ini"
    ini.parent.mkdir(parents=True)
    ini.write_bytes(INI.encode(_INI_ENCODING))
    monkeypatch.setattr("src.core.pre_launch.get_documents_dir", lambda: docs.resolve())
    return GameData.from_dict(JEU), Config(install_path=tmp_path / "Jeux"), ini


def _section(ini, nom="[D3D11Drv.D3D11RenderDevice]"):
    lignes = ini.read_bytes().decode(_INI_ENCODING).split(CRLF)
    debut = lignes.index(nom)
    fin = next((i for i in range(debut + 1, len(lignes)) if lignes[i].startswith("[")), len(lignes))
    return dict(ligne.split("=", 1) for ligne in lignes[debut + 1:fin] if "=" in ligne)


class TestEcriture:
    def test_legere_eteint_tout(self, hp2):
        game, config, ini = hp2
        config.qualite_rendu["hp2"] = qualite_rendu.LEGERE
        assert qualite_rendu.appliquer(game, config)
        section = _section(ini)
        assert section["Antialiasing"] == "0"
        for cle in ("ASSAO", "SSR", "HDR", "ParallaxOcclusionMapping", "VolumetricLighting",
                    "UnlimitedViewDistance"):
            assert section[cle] == "False", cle

    def test_equilibree(self, hp2):
        game, config, ini = hp2
        config.qualite_rendu["hp2"] = qualite_rendu.EQUILIBREE
        qualite_rendu.appliquer(game, config)
        section = _section(ini)
        assert section["Antialiasing"] == "4"
        assert section["SSR"] == section["ParallaxOcclusionMapping"] == "False"
        assert section["UnlimitedViewDistance"] == "False"
        assert section["ASSAO"] == section["HDR"] == section["VolumetricLighting"] == "True"

    def test_les_autres_lignes_restent_intactes_a_l_octet(self, hp2):
        """Seules les lignes des clés du niveau changent ; l'autre section qui porte
        `Antialiasing` et `HDR`, le profil accentué, l'ordre, les CRLF restent."""
        game, config, ini = hp2
        avant = ini.read_bytes().split(CRLF.encode("ascii"))
        config.qualite_rendu["hp2"] = qualite_rendu.LEGERE
        qualite_rendu.appliquer(game, config)
        apres = ini.read_bytes().split(CRLF.encode("ascii"))
        assert len(apres) == len(avant)
        touchees = {cle.encode("ascii") for cle in qualite_rendu.valeurs(qualite_rendu.LEGERE)}
        debut = avant.index(b"[D3D11Drv.D3D11RenderDevice]")
        fin = avant.index(b"[D3DDrv.D3DRenderDevice]")
        for i, (a, b) in enumerate(zip(avant, apres, strict=True)):
            if debut < i < fin and a.partition(b"=")[0] in touchees:
                continue
            assert a == b, (i, a, b)
        assert _section(ini, "[D3DDrv.D3DRenderDevice]") == {"Antialiasing": "8", "HDR": "True"}

    def test_maximale_remet_l_installation(self, hp2):
        game, config, ini = hp2
        origine = ini.read_bytes()
        config.qualite_rendu["hp2"] = qualite_rendu.LEGERE
        qualite_rendu.appliquer(game, config)
        config.qualite_rendu["hp2"] = qualite_rendu.MAXIMALE
        qualite_rendu.appliquer(game, config)
        assert ini.read_bytes() == origine

    def test_sans_choix_rien_n_est_ecrit(self, hp2):
        game, config, ini = hp2
        origine = ini.read_bytes()
        assert not qualite_rendu.appliquer(game, config)
        config.qualite_rendu["hp2"] = "inconnu"
        assert not qualite_rendu.appliquer(game, config)
        assert ini.read_bytes() == origine

    def test_section_et_cles_sans_casse(self, hp2):
        """Le moteur lit sans casse : réécrire « [d3d11drv.d3d11renderdevice] » en ajoutant
        une seconde section laisserait l'ancienne valeur lue."""
        game, config, ini = hp2
        ini.write_bytes(INI.replace("[D3D11Drv.D3D11RenderDevice]", "[d3d11drv.d3d11renderdevice]")
                        .replace("Antialiasing=8" + CRLF + "Anisotropy", "antialiasing=8" + CRLF
                                 + "Anisotropy").encode(_INI_ENCODING))
        config.qualite_rendu["hp2"] = qualite_rendu.LEGERE
        qualite_rendu.appliquer(game, config)
        texte = ini.read_bytes().decode(_INI_ENCODING)
        assert texte.casefold().count("[d3d11drv.d3d11renderdevice]") == 1
        assert _section(ini, "[d3d11drv.d3d11renderdevice]")["Antialiasing"] == "0"

    def test_une_seule_ecriture_pour_toutes_les_cles(self, hp2, monkeypatch):
        """Règle 140 : un fichier, une ouverture (sept écritures avant le regroupement)."""
        from src.core import pre_launch
        game, config, _ini = hp2
        ecritures = []
        vraie = pre_launch.ecrire_octets_atomique
        monkeypatch.setattr(pre_launch, "ecrire_octets_atomique",
                            lambda chemin, octets: (ecritures.append(chemin), vraie(chemin, octets)))
        config.qualite_rendu["hp2"] = qualite_rendu.LEGERE
        qualite_rendu.appliquer(game, config)
        assert len(ecritures) == 1

    def test_l_ini_absent_n_est_pas_cree(self, hp2):
        game, config, ini = hp2
        ini.unlink()
        config.qualite_rendu["hp2"] = qualite_rendu.LEGERE
        assert not qualite_rendu.appliquer(game, config)
        assert not ini.exists()

    def test_seuls_les_jeux_en_d3d11_sont_concernes(self, hp2):
        game, _config, _ini = hp2
        assert qualite_rendu.gere(game)
        autre = dict(JEU, id="hp3", pre_launch={"ini_patches": [
            {"file": FICHIER, "section": "FirstRun", "key": "Reconfig", "value": "0"}]})
        assert not qualite_rendu.gere(GameData.from_dict(autre))

    def test_le_choix_survit_a_la_fermeture(self, tmp_path, monkeypatch):
        """Règle 99 : un champ de Config sans save()/load() disparaît à la fermeture."""
        chemin = tmp_path / "config.json"
        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", chemin)
        config = Config(install_path=tmp_path)
        config.qualite_rendu["hp1"] = qualite_rendu.EQUILIBREE
        config.save()
        assert Config.load().qualite_rendu == {"hp1": qualite_rendu.EQUILIBREE}


class TestDonneeDeWindows:
    """Les paires `nom=valeur;` que Windows range pour un exe (pures, testées partout)."""

    def test_ajouter_garde_les_autres_paires(self):
        assert preference_gpu.ajouter("") == "GpuPreference=2;"
        assert preference_gpu.ajouter("VRROptimizeEnable=0;GpuPreference=1;") == \
            "VRROptimizeEnable=0;GpuPreference=2;"

    def test_retirer_rend_ce_qu_il_y_avait(self):
        assert preference_gpu.retirer("GpuPreference=2;") == ""
        assert preference_gpu.retirer("VRROptimizeEnable=0;GpuPreference=2;") == "VRROptimizeEnable=0;"

    def test_puissante(self):
        assert preference_gpu.puissante("SwapEffectUpgradeEnable=1;GpuPreference=2;")
        assert not preference_gpu.puissante("GpuPreference=1;")
        assert not preference_gpu.puissante("")


INTEL = "Intel(R) UHD Graphics 620 · pilote 31.0 · du 2025-01-01"
NVIDIA = "NVIDIA GeForce MX150 · pilote 566.03 · du 2025-01-01 · 2 Go"
PARSEC = "Parsec Virtual Display Adapter · pilote 0.45 · virtuel"
BASIQUE = "Microsoft Basic Display Adapter · pilote 10.0"


class TestDeuxCartes:
    def test_une_vraie_carte_ne_suffit_pas(self):
        from src.core import diagnostic
        assert not diagnostic.plusieurs_cartes([NVIDIA])
        assert not diagnostic.plusieurs_cartes([NVIDIA, PARSEC, BASIQUE])
        assert diagnostic.plusieurs_cartes([INTEL, NVIDIA])

    @pytest.fixture
    def registre(self, monkeypatch):
        """Un faux registre : aucun test n'écrit dans celui de la machine."""
        valeurs: dict[str, str] = {}
        monkeypatch.setattr(preference_gpu, "_lire", lambda exe: valeurs.get(str(exe), ""))

        def ecrire(exe, donnee):
            if donnee:
                valeurs[str(exe)] = donnee
            else:
                valeurs.pop(str(exe), None)
        monkeypatch.setattr(preference_gpu, "_ecrire", ecrire)
        return valeurs

    def test_rien_n_est_ecrit_sur_une_machine_a_une_carte(self, registre, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        assert not preference_gpu.poser(tmp_path / "Game.exe", True, cartes=[NVIDIA, PARSEC])
        assert registre == {}

    def test_rien_n_est_ecrit_hors_windows(self, registre, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        assert not preference_gpu.proposee([INTEL, NVIDIA])
        assert not preference_gpu.poser(tmp_path / "Game.exe", True, cartes=[INTEL, NVIDIA])
        assert registre == {}

    def test_deux_cartes_pose_puis_retire(self, registre, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        exe = tmp_path / "Game.exe"
        registre[str(exe)] = "VRROptimizeEnable=0;"
        assert preference_gpu.poser(exe, True, cartes=[INTEL, NVIDIA])
        assert registre[str(exe)] == "VRROptimizeEnable=0;GpuPreference=2;"
        assert preference_gpu.active(exe)
        assert preference_gpu.poser(exe, False, cartes=[INTEL, NVIDIA])
        assert registre[str(exe)] == "VRROptimizeEnable=0;"
        registre.clear()
        preference_gpu.poser(exe, True, cartes=[INTEL, NVIDIA])
        preference_gpu.poser(exe, False, cartes=[INTEL, NVIDIA])
        assert registre == {}, "la valeur disparaît quand il n'y reste rien"


class TestFenetre:
    """Les deux lignes dans la carte « Affichage » de HP1/HP2."""

    def _dialogue(self, qtbot, game, config, monkeypatch, deux_cartes):
        from src.ui import game_settings_dialog as gsd
        from src.ui import reglages_rubriques as rr
        monkeypatch.setattr(rr.resolution_jeu, "place_disponible", lambda: (1920, 1080))
        monkeypatch.setattr(rr.preference_gpu, "proposee", lambda: deux_cartes)
        monkeypatch.setattr(rr.preference_gpu, "active", lambda _exe: False)
        manager = SimpleNamespace(config=config, game_language=lambda _g: None)
        dlg = gsd.GameSettingsDialog(game, manager, appliquer_langue=lambda _c: True)
        qtbot.addWidget(dlg)
        return dlg

    @staticmethod
    def _jeu():
        bloc = {"file": FICHIER, "section": "WinDrv.WindowsClient",
                "width": "WindowedViewportX", "height": "WindowedViewportY"}
        jeu = GameData.from_dict(dict(JEU, display_locked=True, resolution=bloc))
        assert jeu.resolution is not None, "sans résolution, la rubrique Affichage est verrouillée"
        return jeu

    @staticmethod
    def _liste_qualite(dlg):
        from PyQt6.QtWidgets import QComboBox
        return next((c for c in dlg.findChildren(QComboBox)
                     if c.count() and c.itemData(0) == qualite_rendu.MAXIMALE), None)

    @staticmethod
    def _bascule_gpu(dlg):
        from src.ui.toggle_switch import ToggleSwitch
        return next((b for b in dlg.findChildren(ToggleSwitch)
                     if "deux cartes graphiques" in b.accessibleDescription()), None)

    def test_la_qualite_se_choisit_et_s_enregistre(self, qtbot, hp2, monkeypatch):
        _game, config, _ini = hp2
        dlg = self._dialogue(qtbot, self._jeu(), config, monkeypatch, deux_cartes=False)
        liste = self._liste_qualite(dlg)
        assert liste is not None and liste.currentData() == qualite_rendu.MAXIMALE
        liste.setCurrentIndex(liste.findData(qualite_rendu.LEGERE))
        assert config.qualite_rendu == {"hp2": qualite_rendu.LEGERE}

    def test_la_carte_puissante_seulement_avec_deux_cartes(self, qtbot, hp2, monkeypatch):
        _game, config, _ini = hp2
        assert self._bascule_gpu(self._dialogue(qtbot, self._jeu(), config, monkeypatch, False)) is None
        dlg = self._dialogue(qtbot, self._jeu(), config, monkeypatch, True)
        assert self._bascule_gpu(dlg) is not None
