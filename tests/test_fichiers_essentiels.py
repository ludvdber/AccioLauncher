"""Les fichiers sans lesquels un jeu ne démarre pas : déclarés, vérifiés, signalés.

Cas d'origine (rapport du 2026-10-09) : `d3d11drv.dll` retiré de HP2 par
l'antivirus après l'installation, et le launcher proposait la configuration.
"""
from types import SimpleNamespace

import pytest

from src.core import fichiers_essentiels
from src.core.catalogue_blocs import _MAX_FICHIERS_ESSENTIELS, _fichiers_essentiels_valides


def _jeu(essentiels=("HP2/system/d3d11drv.dll", "HP2/system/Effects11.dll")):
    return SimpleNamespace(id="hp2", name="Harry Potter II", executable="HP2/system/Game.exe",
                           fichiers_essentiels=tuple(essentiels))


def _installer(racine, *relatifs):
    for r in relatifs:
        f = racine / r
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"MZ")


class TestCatalogue:
    def test_liste_gardee_dans_l_ordre_et_sans_doublon(self):
        assert _fichiers_essentiels_valides(
            ["HP2\\system\\d3d11drv.dll", "HP2/system/Effects11.dll", "HP2/system/d3d11drv.dll"]
        ) == ("HP2/system/d3d11drv.dll", "HP2/system/Effects11.dll")

    def test_absente(self):
        assert _fichiers_essentiels_valides(None) == ()

    @pytest.mark.parametrize("brut", [
        "HP2/system/d3d11drv.dll",                       # pas une liste
        ["HP2/system/d3d11drv.dll", "../../Windows/x.dll"],
        ["HP2/system/d3d11drv.dll", "C:/Windows/x.dll"],
        ["HP2/system/d3d11drv.dll", None],
        ["HP2/system/con.dll"],
        [f"HP2/f{i}.dll" for i in range(_MAX_FICHIERS_ESSENTIELS + 1)],
    ])
    def test_tout_ou_rien(self, brut):
        """Une liste à moitié retenue dirait « tout est là » à tort."""
        assert _fichiers_essentiels_valides(brut) == ()

    def test_lu_par_game_data(self):
        from src.core.game_data import GameData
        jeu = GameData.from_dict({
            "id": "hp2", "name": "HP2", "year": 2002, "description": "", "developer": "KW",
            "executable": "HP2/system/Game.exe", "cover_image": "c.jpg",
            "essential_files": ["HP2/system/d3d11drv.dll"]})
        assert jeu.fichiers_essentiels == ("HP2/system/d3d11drv.dll",)


class TestManquants:
    def test_tout_est_la(self, tmp_path):
        _installer(tmp_path, "HP2/system/Game.exe", "HP2/system/d3d11drv.dll",
                   "HP2/system/Effects11.dll")
        assert fichiers_essentiels.manquants(_jeu(), tmp_path) == []

    def test_le_pilote_retire_par_l_antivirus(self, tmp_path):
        _installer(tmp_path, "HP2/system/Game.exe", "HP2/system/Effects11.dll")
        assert fichiers_essentiels.manquants(_jeu(), tmp_path) == ["HP2/system/d3d11drv.dll"]

    def test_l_executable_d_abord_et_une_seule_fois(self, tmp_path):
        jeu = _jeu(("HP2/system/d3d11drv.dll", "HP2/system/Game.exe"))
        assert fichiers_essentiels.manquants(jeu, tmp_path) == [
            "HP2/system/Game.exe", "HP2/system/d3d11drv.dll"]

    def test_la_casse_ne_compte_pas(self, tmp_path):
        """Sous Linux, `System` au catalogue et `system` sur le disque."""
        _installer(tmp_path, "hp2/SYSTEM/game.EXE", "hp2/system/D3D11DRV.DLL",
                   "HP2/system/effects11.dll")
        assert fichiers_essentiels.manquants(_jeu(), tmp_path) == []

    def test_un_dossier_au_nom_du_fichier_ne_compte_pas(self, tmp_path):
        _installer(tmp_path, "HP2/system/Game.exe", "HP2/system/Effects11.dll")
        (tmp_path / "HP2" / "system" / "d3d11drv.dll").mkdir()
        assert fichiers_essentiels.manquants(_jeu(), tmp_path) == ["HP2/system/d3d11drv.dll"]

    def test_un_fichier_en_plus_n_est_jamais_une_panne(self, tmp_path):
        """Un mod de cartes AJOUTE des fichiers : rien à signaler."""
        _installer(tmp_path, "HP2/system/Game.exe", "HP2/system/d3d11drv.dll",
                   "HP2/system/Effects11.dll", "HP2/Maps/Mod.unr", "HP2/system/Mod.u")
        assert fichiers_essentiels.manquants(_jeu(), tmp_path) == []


class TestBoite:
    @pytest.fixture
    def h(self):
        from src.ui import game_detail_handlers as h
        return h

    def _vue(self, install, game, occupe=False):
        appels = []
        vue = SimpleNamespace(
            game=game, preparation_en_cours=False,
            manager=SimpleNamespace(config=SimpleNamespace(install_path=install)),
            notify=SimpleNamespace(emit=appels.append),
            _ops=SimpleNamespace(is_busy=occupe, repair=lambda g: appels.append(("repair", g.id))),
            _refresh=lambda: None)
        return vue, appels

    def _repondre(self, monkeypatch, h, choix):
        boites = []
        monkeypatch.setattr(h, "_boite", lambda *a, **k: boites.append((a[2], a[3], a[4])) or choix)
        return boites

    def test_rien_ne_manque_rien_ne_s_affiche(self, h, monkeypatch, tmp_path):
        _installer(tmp_path, "HP2/system/Game.exe", "HP2/system/d3d11drv.dll",
                   "HP2/system/Effects11.dll")
        boites = self._repondre(monkeypatch, h, 0)
        vue, _ = self._vue(tmp_path, _jeu())
        assert h.signaler_fichiers_manquants(vue, vue.game) is False and boites == []

    @pytest.mark.parametrize("choix, attendu", [
        (0, [("repair", "hp2")]), (1, ["ouvert"]), (2, []), (-1, [])])
    def test_la_boite_nomme_le_fichier_et_propose_le_remede(self, h, monkeypatch, tmp_path,
                                                           choix, attendu):
        _installer(tmp_path, "HP2/system/Game.exe", "HP2/system/Effects11.dll")
        boites = self._repondre(monkeypatch, h, choix)
        vue, appels = self._vue(tmp_path, _jeu())
        from src.ui import fichiers_manquants
        monkeypatch.setattr(fichiers_manquants, "ouvrir_dossier_du_jeu",
                            lambda *_a: appels.append("ouvert"))
        assert h.signaler_fichiers_manquants(vue, vue.game) is True
        titre, texte, boutons = boites[0]
        assert titre == "Il manque des fichiers à Harry Potter II"
        assert "• d3d11drv.dll" in texte and "antivirus" in texte and "HP2/" not in texte
        assert boutons == ("Retélécharger le jeu", "Ouvrir le dossier du jeu", "Fermer")
        assert appels == attendu

    def test_pas_de_retelechargement_par_dessus_une_operation(self, h, monkeypatch, tmp_path):
        self._repondre(monkeypatch, h, 0)
        vue, appels = self._vue(tmp_path, _jeu(), occupe=True)
        h.signaler_fichiers_manquants(vue, vue.game)
        assert appels == []

    def test_au_dela_de_huit_le_nombre_dit_le_reste(self, h, monkeypatch, tmp_path):
        jeu = _jeu([f"HP2/system/f{i}.dll" for i in range(11)])
        _installer(tmp_path, "HP2/system/Game.exe")
        boites = self._repondre(monkeypatch, h, -1)
        vue, _ = self._vue(tmp_path, jeu)
        h.signaler_fichiers_manquants(vue, jeu)
        texte = boites[0][1]
        assert "• f7.dll" in texte and "f8.dll" not in texte and "… et 3 autres" in texte

    def test_apres_rendev_le_fichier_manquant_passe_avant_la_configuration(
            self, h, monkeypatch, tmp_path):
        """Le cas du rapport : plus de « Remettre la configuration » pour rien."""
        _installer(tmp_path, "HP2/system/Game.exe", "HP2/system/Effects11.dll")
        boites = self._repondre(monkeypatch, h, -1)
        vue, _ = self._vue(tmp_path, _jeu())
        h.proposer_apres_plantage(vue, vue.game, "Assertion failed: RenDev")
        assert len(boites) == 1 and boites[0][2][0] == "Retélécharger le jeu"

    def test_apres_un_arret_fatal_aussi(self, h, monkeypatch, tmp_path):
        from src.core import config_cassee
        _installer(tmp_path, "HP2/system/Game.exe", "HP2/system/Effects11.dll")
        boites = self._repondre(monkeypatch, h, -1)
        vue, _ = self._vue(tmp_path, _jeu())
        h.signaler_arret(vue, vue.game, config_cassee.arret_fatal(
            "Critical: appError called:\r\nCritical: Assertion failed: RenDev\r\n"))
        assert len(boites) == 1 and boites[0][2][0] == "Retélécharger le jeu"

    def test_le_bouton_verifier_dit_que_tout_est_la(self, h, monkeypatch, tmp_path):
        _installer(tmp_path, "HP2/system/Game.exe", "HP2/system/d3d11drv.dll",
                   "HP2/system/Effects11.dll")
        monkeypatch.setattr(h.reparation_config, "disponible", lambda *_a: False)
        boites = self._repondre(monkeypatch, h, 1)
        vue, _ = self._vue(tmp_path, _jeu())
        h.on_repair(vue)
        assert boites[0][1].startswith("Les fichiers essentiels de Harry Potter II sont tous là.")

    def test_sans_liste_au_catalogue_il_ne_promet_rien(self, h, monkeypatch, tmp_path):
        """Seul l'exécutable a été regardé : « tout est là » mentirait."""
        _installer(tmp_path, "HP2/system/Game.exe")
        monkeypatch.setattr(h.reparation_config, "disponible", lambda *_a: False)
        boites = self._repondre(monkeypatch, h, 1)
        vue, _ = self._vue(tmp_path, _jeu(()))
        h.on_repair(vue)
        assert "sont tous là" not in boites[0][1]

    def test_le_bouton_verifier_signale_avant_de_proposer_la_configuration(
            self, h, monkeypatch, tmp_path):
        _installer(tmp_path, "HP2/system/Game.exe", "HP2/system/Effects11.dll")
        monkeypatch.setattr(h.reparation_config, "disponible", lambda *_a: True)
        boites = self._repondre(monkeypatch, h, -1)
        vue, _ = self._vue(tmp_path, _jeu())
        h.on_repair(vue)
        assert len(boites) == 1 and "• d3d11drv.dll" in boites[0][1]
