"""Le rendu D3D11 de HP1/HP2 réglé dans le launcher, et la carte graphique la plus puissante.

Constat du 2026-11-18 (1.3.6-beta.1) : HP1 et HP2 à 5 images/s sur un portable, leur rendu
installé au maximum et rien pour le régler dans le launcher. Depuis le 2026-11-19, chaque
réglage utile de `[D3D11Drv.D3D11RenderDevice]` a sa ligne dans la page Image, et les trois
niveaux de la bêta en sont les préréglages.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core import preference_gpu, qualite_rendu, reglages_image, resolution_jeu
from src.core.config import Config
from src.core.game_data import GameData
from src.core.pre_launch import _INI_ENCODING

B = chr(92)
CRLF = "\r\n"
FICHIER = "%DOCUMENTS%" + B + "Harry Potter II" + B + "Game.ini"
R = qualite_rendu.REGLAGES

JEU = {
    "id": "hp2", "name": "HP2", "year": 2002, "description": "d",
    "developer": "dev", "executable": "HP2/system/Game.exe", "cover_image": "c.png",
    "pre_launch": {"ini_patches": [
        {"file": FICHIER, "section": "D3D11Drv.D3D11RenderDevice", "key": "Borderless",
         "value": "True"},
    ]},
}

# La section telle que l'installation la livre (HP2 config/Game.ini, relevé le 2026-11-19 ; HP1 la même),
# avec ce qui ne nous regarde pas autour (profil accentué, une autre section qui porte des clés du même nom).
LIVREE = (
    "Coronas=True", "HighDetailActors=True", "VolumetricLighting=True", "ShinySurfaces=True",
    "DetailTextures=True", "Precache=True", "Antialiasing=8", "Anisotropy=16", "VSync=True",
    "ParallaxOcclusionMapping=True", "LODBias=0", "BumpMapping=True", "HDR=True", "AlphaToCoverage=True",
    "AutoFOV=True", "FPSLimit=100", "UnlimitedViewDistance=True", "ASSAO=True", "ASSAOContrast=0.500000",
    "ASSAOScale=0.400000", "HDRLuminance=0.600000", "HDRAdaptationSpeed=0.200000", "HDRBloom=0.200000",
    "HDRFilmicTonemapping=True", "SSR=True", "SSRIntensity=0.350000", "SSRFresnelAmount=0.300000",
    "ParallaxRange=1.000000", "BumpMappingContrast=0.500000", "SSRNonTransparentWater=True",
    "SSRModelIntensity=0.200000", "OneXBlending=False", "Tesselation=False", "TessDefaultFactor=0.300000",
    "FullMeshLOD=True", "SupportMETextEnabled=False", "FastAltTab=True", "DisableTextureFiltering=False",
    "Borderless=True",
)
INI = (
    "[Engine.Engine]" + CRLF
    + "GameRenderDevice=D3D11Drv.D3D11RenderDevice" + CRLF
    + "[Core.System]" + CRLF
    + "SavePath=C:" + B + "Users" + B + "Frédéric" + B + "Save" + CRLF
    + "[D3D11Drv.D3D11RenderDevice]" + CRLF
    + "".join(ligne + CRLF for ligne in LIVREE)
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


def _magasin(game, config):
    sauvegardes = []
    return qualite_rendu.MagasinRendu(game, config, lambda: sauvegardes.append(1)), sauvegardes


class TestTable:
    def test_la_valeur_accio_est_la_section_livree(self):
        """ACCIO dit ce que porte l'installation, clé par clé, dans l'écriture du moteur."""
        livree = dict(ligne.split("=", 1) for ligne in LIVREE)
        for ident, r in R.items():
            assert qualite_rendu.texte(r, qualite_rendu.ACCIO[ident]) == livree[r.cle], ident

    def test_maximale_est_l_installation(self):
        _i, _n, _t, maximale = next(p for p in qualite_rendu.PREREGLAGES if p[0] == qualite_rendu.MAXIMALE)
        assert all(v == qualite_rendu.ACCIO[i] for i, v in maximale.items())

    def test_chaque_valeur_des_prereglages_est_proposee(self):
        for _i, _n, _t, valeurs in qualite_rendu.PREREGLAGES:
            for ident, v in valeurs.items():
                r = R[ident]
                assert (v in r.choix) if r.choix else isinstance(v, bool), (ident, v)

    def test_chaque_reglage_a_sa_place_dans_la_page(self):
        assert all(reglages_image.place(r) != reglages_image._AILLEURS for r in R.values())

    def test_la_limite_ne_depasse_jamais_l_installation(self):
        """Au-delà de 100 images/s, rien n'a été vu en jeu."""
        assert max(R["rendu_limite"].choix) == 100

    def test_jamais_ce_que_le_catalogue_pose(self):
        """`Borderless` et `FastAltTab` sont posés par le catalogue à chaque lancement."""
        assert not {r.cle for r in R.values()} & {"Borderless", "FastAltTab"}

    def test_chaque_texte_est_traduit(self):
        textes = set()
        for r in R.values():
            textes |= {r.libelle, r.aide, r.zero, r.technique} | {n for _v, n in r.etiquettes}
        textes |= {t for _i, n, tx, _v in qualite_rendu.PREREGLAGES for t in (n, tx)}
        sans_mots = {"100", "HDR", "SSR", "MSAA", "parallax occlusion mapping"}
        for code in ("en", "es"):
            cles = json.loads(Path(f"src/data/i18n/{code}.json").read_text(encoding="utf-8"))["strings"]
            manquants = sorted(t for t in textes if t and t not in cles and t not in sans_mots)
            assert not manquants, (code, manquants)


class TestEcriture:
    def test_rien_n_est_ecrit_sans_reglage(self, hp2):
        game, config, ini = hp2
        origine = ini.read_bytes()
        assert not qualite_rendu.appliquer(game, config)
        assert ini.read_bytes() == origine

    def test_seules_les_cles_reglees_sont_ecrites(self, hp2):
        game, config, ini = hp2
        magasin, _s = _magasin(game, config)
        magasin.ecrire(R["rendu_anticrenelage"], 2)
        magasin.ecrire(R["rendu_reflets_force"], 0.5)
        assert config.rendu_d3d11 == {"hp2": {"Antialiasing": "2", "SSRIntensity": "0.500000"}}
        assert qualite_rendu.appliquer(game, config)
        section = _section(ini)
        assert section["Antialiasing"] == "2" and section["SSRIntensity"] == "0.500000"
        assert section["ASSAO"] == "True"

    def test_les_autres_lignes_restent_intactes_a_l_octet(self, hp2):
        """Seules les lignes des clés réglées changent ; l'autre section qui porte
        `Antialiasing` et `HDR`, le profil accentué, l'ordre, les CRLF restent."""
        game, config, ini = hp2
        avant = ini.read_bytes().split(CRLF.encode("ascii"))
        magasin, _s = _magasin(game, config)
        for ident, v in next(p for p in qualite_rendu.PREREGLAGES if p[0] == qualite_rendu.LEGERE)[3].items():
            magasin.ecrire(R[ident], v)
        qualite_rendu.appliquer(game, config)
        apres = ini.read_bytes().split(CRLF.encode("ascii"))
        assert len(apres) == len(avant)
        touchees = {cle.encode("ascii") for cle in config.rendu_d3d11["hp2"]}
        debut = avant.index(b"[D3D11Drv.D3D11RenderDevice]")
        fin = avant.index(b"[D3DDrv.D3DRenderDevice]")
        for i, (a, b) in enumerate(zip(avant, apres, strict=True)):
            if debut < i < fin and a.partition(b"=")[0] in touchees:
                continue
            assert a == b, (i, a, b)
        assert _section(ini, "[D3DDrv.D3DRenderDevice]") == {"Antialiasing": "8", "HDR": "True"}

    def test_remettre_rend_l_installation_a_l_octet(self, hp2):
        game, config, ini = hp2
        origine = ini.read_bytes()
        magasin, _s = _magasin(game, config)
        magasin.ecrire(R["rendu_anticrenelage"], 0)
        magasin.ecrire(R["rendu_vsync"], False)
        qualite_rendu.appliquer(game, config)
        assert ini.read_bytes() != origine
        assert magasin.a_change()
        magasin.remettre()
        qualite_rendu.appliquer(game, config)
        assert ini.read_bytes() == origine
        assert not qualite_rendu.MagasinRendu(game, config, lambda: None).a_change()

    def test_section_et_cles_sans_casse(self, hp2):
        """Le moteur lit sans casse : réécrire « [d3d11drv.d3d11renderdevice] » en ajoutant
        une seconde section laisserait l'ancienne valeur lue."""
        game, config, ini = hp2
        ini.write_bytes(INI.replace("[D3D11Drv.D3D11RenderDevice]", "[d3d11drv.d3d11renderdevice]")
                        .replace("Antialiasing=8" + CRLF + "Anisotropy", "antialiasing=8" + CRLF
                                 + "Anisotropy").encode(_INI_ENCODING))
        config.rendu_d3d11["hp2"] = {"Antialiasing": "0"}
        qualite_rendu.appliquer(game, config)
        texte = ini.read_bytes().decode(_INI_ENCODING)
        assert texte.casefold().count("[d3d11drv.d3d11renderdevice]") == 1
        assert _section(ini, "[d3d11drv.d3d11renderdevice]")["Antialiasing"] == "0"

    def test_une_seule_ecriture_pour_toutes_les_cles(self, hp2, monkeypatch):
        """Règle 140 : un fichier, une ouverture."""
        from src.core import pre_launch
        game, config, _ini = hp2
        ecritures = []
        vraie = pre_launch.ecrire_octets_atomique
        monkeypatch.setattr(pre_launch, "ecrire_octets_atomique",
                            lambda chemin, octets: (ecritures.append(chemin), vraie(chemin, octets)))
        config.rendu_d3d11["hp2"] = {"Antialiasing": "0", "SSR": "False", "HDR": "False"}
        qualite_rendu.appliquer(game, config)
        assert len(ecritures) == 1

    def test_l_ini_absent_n_est_pas_cree(self, hp2):
        game, config, ini = hp2
        ini.unlink()
        config.rendu_d3d11["hp2"] = {"Antialiasing": "0"}
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
        config.rendu_d3d11["hp1"] = {"Antialiasing": "4"}
        config.save()
        assert Config.load().rendu_d3d11 == {"hp1": {"Antialiasing": "4"}}


class TestNiveauDeLaBeta:
    """La 1.3.6-beta.1 gardait un niveau par jeu : il devient ses clés, une fois."""

    def test_legere_eteint_tout(self, hp2):
        game, config, ini = hp2
        config.qualite_rendu["hp2"] = qualite_rendu.LEGERE
        assert qualite_rendu.appliquer(game, config)
        section = _section(ini)
        assert section["Antialiasing"] == "0"
        for cle in ("ASSAO", "SSR", "HDR", "ParallaxOcclusionMapping", "VolumetricLighting",
                    "UnlimitedViewDistance"):
            assert section[cle] == "False", cle
        assert config.qualite_rendu == {}

    def test_equilibree(self, hp2):
        game, config, ini = hp2
        config.qualite_rendu["hp2"] = qualite_rendu.EQUILIBREE
        qualite_rendu.appliquer(game, config)
        section = _section(ini)
        assert section["Antialiasing"] == "4"
        assert section["SSR"] == section["ParallaxOcclusionMapping"] == "False"
        assert section["UnlimitedViewDistance"] == "False"
        assert section["ASSAO"] == section["HDR"] == section["VolumetricLighting"] == "True"

    def test_un_reglage_deja_fait_l_emporte(self, hp2):
        game, config, _ini = hp2
        config.rendu_d3d11["hp2"] = {"Antialiasing": "2"}
        config.qualite_rendu["hp2"] = qualite_rendu.LEGERE
        qualite_rendu.appliquer(game, config)
        assert config.rendu_d3d11 == {"hp2": {"Antialiasing": "2"}} and config.qualite_rendu == {}

    def test_un_niveau_inconnu_n_ecrit_rien(self, hp2):
        game, config, ini = hp2
        origine = ini.read_bytes()
        config.qualite_rendu["hp2"] = "inconnu"
        assert not qualite_rendu.appliquer(game, config)
        assert ini.read_bytes() == origine


class TestMagasin:
    def test_un_lot_n_enregistre_la_config_qu_une_fois(self, hp2):
        """Un préréglage enregistrait la config sept fois, une par réglage (banc du 2026-11-19)."""
        game, config, _ini = hp2
        magasin, sauvegardes = _magasin(game, config)
        valeurs = magasin.ecrire_tout([(R["rendu_anticrenelage"], 0), (R["rendu_vsync"], False)])
        assert valeurs == {"rendu_anticrenelage": 0, "rendu_vsync": False}
        assert sauvegardes == [1]
        assert config.rendu_d3d11["hp2"]["Antialiasing"] == "0"

    def test_un_lot_refuse_ne_change_rien(self, hp2):
        game, config, _ini = hp2
        magasin, sauvegardes = _magasin(game, config)
        with pytest.raises(ValueError):
            magasin.ecrire_tout([(R["rendu_anticrenelage"], 0), (R["rendu_limite"], 144)])
        assert sauvegardes == [] and config.rendu_d3d11 == {}

    def test_sans_reglage_la_page_montre_l_ini(self, hp2):
        """Une valeur posée à la main dans l'ini se montre telle quelle ; rien n'est écrit pour autant."""
        game, config, ini = hp2
        ini.write_bytes(INI.replace("Antialiasing=8" + CRLF + "Anisotropy",
                                    "Antialiasing=2" + CRLF + "Anisotropy").encode(_INI_ENCODING))
        magasin, _s = _magasin(game, config)
        assert magasin.lire(R["rendu_anticrenelage"]) == 2
        assert magasin.lire(R["rendu_reflets_force"]) == pytest.approx(0.35)
        assert magasin.lire(R["rendu_hdr"]) is True
        assert config.rendu_d3d11 == {}

    def test_l_ini_illisible_montre_l_installation(self, hp2):
        game, config, ini = hp2
        ini.unlink()
        magasin, _s = _magasin(game, config)
        assert all(magasin.lire(r) == qualite_rendu.ACCIO[i] for i, r in R.items())

    def test_ecrire_enregistre_la_config(self, hp2):
        game, config, _ini = hp2
        magasin, sauvegardes = _magasin(game, config)
        magasin.ecrire(R["rendu_reflets"], False)
        assert magasin.lire(R["rendu_reflets"]) is False
        assert sauvegardes == [1]

    def test_une_valeur_non_proposee_est_refusee(self, hp2):
        game, config, _ini = hp2
        magasin, sauvegardes = _magasin(game, config)
        with pytest.raises(ValueError):
            magasin.ecrire(R["rendu_limite"], 144)
        with pytest.raises(ValueError):
            magasin.ecrire(R["rendu_anticrenelage"], 16)
        assert config.rendu_d3d11 == {} and not sauvegardes

    def test_le_curseur_des_reflets_arrondit_au_pas(self, hp2):
        game, config, _ini = hp2
        magasin, _s = _magasin(game, config)
        magasin.ecrire(R["rendu_reflets_force"], 0.30000000000000004)
        assert config.rendu_d3d11["hp2"]["SSRIntensity"] == "0.300000"

    def test_accio_et_jeu(self, hp2):
        game, config, _ini = hp2
        magasin, _s = _magasin(game, config)
        assert magasin.accio(R["rendu_anticrenelage"]) == 8
        assert magasin.jeu(R["rendu_anticrenelage"]) == 0
        assert magasin.jeu(R["rendu_limite"]) is None, "le jeu de 2002 n'avait pas de limite connue"


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
    """La page Image de HP1/HP2 : la résolution et ce que règle le launcher dans « Écran », les
    réglages du rendu dans leurs catégories, les trois niveaux de la bêta en préréglages."""

    def _dialogue(self, qtbot, game, config, monkeypatch, deux_cartes):
        from src.ui import game_settings_dialog as gsd
        monkeypatch.setattr(resolution_jeu, "place_disponible", lambda: (1920, 1080))
        monkeypatch.setattr(preference_gpu, "proposee", lambda: deux_cartes)
        monkeypatch.setattr(preference_gpu, "active", lambda _exe: False)
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

    def test_tous_les_reglages_du_rendu_sont_dans_la_page(self, qtbot, hp2, monkeypatch):
        _game, config, _ini = hp2
        page = self._dialogue(qtbot, self._jeu(), config, monkeypatch, deux_cartes=False)._page_img
        assert page is not None and set(page.reglages) == set(R)
        assert [c.ident for c in page.categories] == ["ecran", "qualite", "lumiere", "distance", "fluidite"]
        assert page.ligne("resolution_ecran").controle is page.liste_resolution

    def test_un_prereglage_s_ecrit_dans_la_config(self, qtbot, hp2, monkeypatch):
        _game, config, _ini = hp2
        page = self._dialogue(qtbot, self._jeu(), config, monkeypatch, deux_cartes=False)._page_img
        assert page.onglet_prereglages is not None
        assert not page.sur_mesure.isVisibleTo(page) or page._cartes_prereglage[qualite_rendu.MAXIMALE].isChecked()
        page.choisir_prereglage(qualite_rendu.LEGERE)
        assert config.rendu_d3d11["hp2"]["Antialiasing"] == "0"
        assert config.rendu_d3d11["hp2"]["SSR"] == "False"
        assert page._cartes_prereglage[qualite_rendu.LEGERE].isChecked()

    def test_un_reglage_seul_et_sa_dependance(self, qtbot, hp2, monkeypatch):
        """Sans anticrénelage, « Feuillage et grilles lissés » n'a pas d'effet : il se replie."""
        _game, config, _ini = hp2
        dlg = self._dialogue(qtbot, self._jeu(), config, monkeypatch, deux_cartes=False)
        page = dlg._page_img
        ligne = page.ligne("rendu_feuillage")
        assert not ligne.isHidden()
        page.regler("rendu_anticrenelage", 0)
        assert ligne.isHidden()
        assert config.rendu_d3d11["hp2"] == {"Antialiasing": "0"}
        assert dlg._bouton_reset.isEnabled()

    def test_revenir_a_l_installation(self, qtbot, hp2, monkeypatch):
        _game, config, _ini = hp2
        dlg = self._dialogue(qtbot, self._jeu(), config, monkeypatch, deux_cartes=False)
        page = dlg._page_img
        assert not dlg._bouton_reset.isEnabled()
        page.regler("rendu_reflets", False)
        dlg._confirmer_origine = lambda _pages: True
        dlg._bouton_reset.click()
        assert page.valeur("rendu_reflets") is True
        assert config.rendu_d3d11["hp2"]["SSR"] == "True"
        assert not dlg._bouton_reset.isEnabled()

    def test_la_carte_puissante_seulement_avec_deux_cartes(self, qtbot, hp2, monkeypatch):
        _game, config, _ini = hp2
        page = self._dialogue(qtbot, self._jeu(), config, monkeypatch, False)._page_img
        assert "carte_puissante" not in page._libres
        page = self._dialogue(qtbot, self._jeu(), config, monkeypatch, True)._page_img
        assert page.ligne("carte_puissante").controle is page._libres["carte_puissante"].controle

    def test_la_carte_puissante_aussi_hors_de_hp1_hp2(self, qtbot, hp2, monkeypatch):
        """Les huit jeux (Ludo, 2026-11-19) : la ligne ne dépend plus de la qualité du rendu de HP1/HP2."""
        _game, config, _ini = hp2
        monkeypatch.setattr(qualite_rendu, "gere", lambda _g: False)
        page = self._dialogue(qtbot, self._jeu(), config, monkeypatch, True)._page_img
        assert page is not None and "carte_puissante" in page._libres
        page = self._dialogue(qtbot, self._jeu(), config, monkeypatch, False)._page_img
        assert page is None or "carte_puissante" not in page._libres

    def test_plein_ecran_sans_bordure_dans_ecran(self, qtbot, hp2, monkeypatch, tmp_path):
        """Issue #39 : `FillScreen` du `winmm.ini` de HP1/HP2 a sa ligne dans « Écran », allumée comme le
        correctif la livre ; l'éteindre écrit 0 (une fenêtre à barre de titre)."""
        _game, config, _ini = hp2
        winmm = tmp_path / "Jeux" / "HP2" / "system" / "winmm.ini"
        winmm.parent.mkdir(parents=True)
        winmm.write_bytes(b"[Accio.Window]\r\nFillScreen=1\r\nMuteInBackground=0\r\n")
        jeu = GameData.from_dict(dict(JEU, display_locked=True, fix_settings=["plein_ecran"],
                                      resolution={"file": FICHIER, "section": "WinDrv.WindowsClient",
                                                  "width": "WindowedViewportX", "height": "WindowedViewportY"}))
        page = self._dialogue(qtbot, jeu, config, monkeypatch, deux_cartes=False)._page_img
        assert reglages_image.place(page.reglages["plein_ecran"]) == ("ecran", "Affichage")
        assert page.valeur("plein_ecran") is True
        page.regler("plein_ecran", False)
        assert winmm.read_bytes() == b"[Accio.Window]\r\nFillScreen=0\r\nMuteInBackground=0\r\n"

    def test_la_mise_en_garde_du_menu_du_jeu_reste(self, qtbot, hp2, monkeypatch):
        """Celui qui cherche la résolution ne doit pas aller la changer dans le menu du jeu."""
        from PyQt6.QtWidgets import QLabel
        _game, config, _ini = hp2
        page = self._dialogue(qtbot, self._jeu(), config, monkeypatch, False)._page_img
        page.montrer(0)
        notes = [n for n in page.findChildren(QLabel, "noteEcran") if "menu du jeu" in n.text()]
        assert notes
