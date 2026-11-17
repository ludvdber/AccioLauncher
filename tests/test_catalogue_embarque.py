"""Contrats de la copie EMBARQUÉE du catalogue (`src/data/games.json`).

La règle 78 interdit de faire dépendre un test du contenu de `games.json` : le
catalogue DISTANT se met à jour sans release, et un test qui suppose son
contenu casse à chaque livraison de jeu. La copie embarquée, elle, est
versionnée avec le code. Ces tests en affirment des CONTRATS (« HP1 et HP2
déclarent les runtimes que charge leur moteur graphique »), pas des
fragilités. Ils étaient éparpillés dans six fichiers (audit du 2026-10-07,
P2-013) : quand on remplace la copie embarquée en « repartant du RAW », c'est
ici, et seulement ici, qu'un rouge doit apparaître.

Un rouge ici veut donc dire : le catalogue publié a changé un de ces points.
Corriger le catalogue OU ce contrat, en connaissance de cause — jamais
supprimer le test pour faire passer la publication.
"""

import json
import re
from fnmatch import fnmatch

import pytest

from src.core.catalogue_blocs import _parse_difficulte, _parse_language_files
from src.core.config import GAMES_JSON_PATH
from src.core.game_data import GameData, load_catalog


@pytest.fixture(scope="module")
def catalogue() -> dict:
    return json.loads(GAMES_JSON_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def requis(catalogue) -> dict[str, set[str]]:
    return {g["id"]: set(g.get("requires", [])) for g in catalogue["games"]}


class TestRuntimesDeclares:
    def test_ce_que_charge_d3d11drv(self, requis):
        for jeu in ("hp1", "hp2"):
            assert {"d3dx11_43", "d3dcompiler_43", "vcredist2010_x86"} <= requis[jeu], jeu
        # HP5 et HP6 importent msvcr80.dll.
        for jeu in ("hp5", "hp6"):
            assert "vcredist2005_x86" in requis[jeu], jeu

    def test_directx9_ce_que_chaque_jeu_charge(self, requis):
        from src.core.system_checks import DLL_DIRECTX9
        # Les Reliques : hp7.exe importe d3dx9_37 (le runtime de 2010, seul à déclarer) ; plus de d3dx9_43 (ancien
        # wrapper) et leur archive livre SON xinput1_3.dll, comme HP5 et HP6 (relevé des imports le 2026-10-08).
        for jeu in ("hp7a", "hp7b"):
            assert requis[jeu] & set(DLL_DIRECTX9) == {"d3dx9_37"}, jeu
        # HP4 à HP6 portent le nouveau correctif (catalogue 0.33) : plus de D3DX, et leur archive livre SON
        # xinput1_3.dll. Exiger le runtime de 2010 bloquerait le lancement pour une DLL que plus rien ne charge.
        for jeu in ("hp4", "hp5", "hp6"):
            assert not requis[jeu] & set(DLL_DIRECTX9), jeu
        # HP1 à HP3 (Unreal) n'ont besoin d'aucune.
        for jeu in ("hp1", "hp2", "hp3"):
            assert not requis[jeu] & set(DLL_DIRECTX9), jeu

    def test_hp7_ses_deux_visual_cpp(self, requis):
        """HP7 partie 1 réclame Visual C++ 2005, partie 2 Visual C++ 2008 —
        deux runtimes distincts du 2015-2022 vérifié pour tous les jeux."""
        assert "vcredist2005_x86" in requis["hp7a"]
        assert "vcredist2008_x86" in requis["hp7b"]


class TestReglages:
    def test_chaque_reglage_declare_est_connu(self, catalogue):
        """Un identifiant inconnu serait ignoré en silence : au catalogue embarqué, c'est une faute."""
        from src.core import reglages_correctif as rc
        for jeu in catalogue["games"]:
            for ident in jeu.get("fix_settings", ()):
                assert ident in rc.REGLAGES, f"{jeu['id']} : {ident}"

    def test_textures_hd_sur_hp6_seulement(self, catalogue):
        """Catalogue 0.57 (2026-11-12) : le pack de textures HD bêta n'existe que pour HP6 ; ailleurs,
        l'interrupteur promettrait des textures qu'aucun pack ne fournit."""
        porteurs = {j["id"] for j in catalogue["games"] if "textures_hd" in j.get("fix_settings", ())}
        assert porteurs == {"hp6"}

    def test_force_du_halo_sur_hp5_et_hp6(self, catalogue):
        """Catalogue 0.57 (2026-11-12) : `NativeBloomStrength` vu en jeu sur HP5 (livré à 60) et sur HP6
        (essai 74 du 2026-11-13 : une seule cible suivie, flou de profondeur intact ; livré à 100, clé absente)."""
        porteurs = {j["id"] for j in catalogue["games"] if "force_halo" in j.get("fix_settings", ())}
        assert porteurs == {"hp5", "hp6"}

    def test_decor_entier_sur_hp6_seulement(self, catalogue):
        """Catalogue 0.57 (2026-11-13) : `ZoneCulling` n'existe que dans le correctif de HP6 ; l'ini livré porte
        2 (décision de Ludo), le joueur le change dans l'onglet Image."""
        porteurs = {j["id"] for j in catalogue["games"] if "decor_entier" in j.get("fix_settings", ())}
        assert porteurs == {"hp6"}

    def test_egal_au_catalogue_publie_quand_son_depot_est_la(self):
        """Les deux catalogues ensemble : l'embarqué et `accio-launcher-games/games.json` portent le même
        contenu et le même numéro. Sauté quand le dépôt voisin n'est pas cloné (CI)."""
        from pathlib import Path
        voisin = Path(__file__).resolve().parents[2] / "accio-launcher-games" / "games.json"
        if not voisin.is_file():
            pytest.skip("dépôt accio-launcher-games absent")
        assert json.loads(voisin.read_text(encoding="utf-8")) == json.loads(GAMES_JSON_PATH.read_text(encoding="utf-8"))

    def test_hp7b_n_a_pas_de_format(self, catalogue):
        """Son ini n'a pas d'AspectRatio : rien ne lirait la clé."""
        hp7b = next(j for j in catalogue["games"] if j["id"] == "hp7b")
        assert "format_image" not in hp7b["fix_settings"]

    def test_hp7a_n_expose_pas_le_format_tant_que_l_effet_n_est_pas_vu(self, catalogue):
        """Audit du 2026-10-07 (P4-002, ACT-039) : `PatchAspect` y cherche « le premier
        flottant égal à 16/9 » dans l'exécutable, motif jamais vérifié. Un réglage dont
        on n'a pas vu l'effet n'a pas à être proposé (règle 118). À remettre le jour où
        un essai en jeu l'aura vu."""
        hp7a = next(j for j in catalogue["games"] if j["id"] == "hp7a")
        assert "format_image" not in hp7a["fix_settings"]

    def test_hp7_ne_promet_pas_une_image_plus_nette(self, catalogue):
        """Audit du 2026-10-07 (P4-001, ACT-037) : les réglages d'image de HP7a/HP7b sont
        livrés éteints (`FXAA=0`, `Antialiasing=0`, `AnisotropicFiltering=0`…). Le texte de
        version ne peut donc pas dire « image plus nette » (règle 108). À rétablir si
        ACT-038 livre un réglage qu'on a vu."""
        for gid in ("hp7a", "hp7b"):
            jeu = next(j for j in catalogue["games"] if j["id"] == gid)
            for v in jeu["versions"]:
                lignes = [*v["changes"], *(v.get("i18n", {}).get("en", {}).get("changes") or ()),
                          *(v.get("i18n", {}).get("es", {}).get("changes") or ())]
                for ligne in lignes:
                    assert "plus nette" not in ligne and "sharper" not in ligne \
                        and "más nítida" not in ligne, (gid, ligne)


def test_les_sauvegardes_ne_nomment_aucun_chemin_windows(catalogue):
    """Le launcher sera porté sous Linux (le jeu, lui, tournera dans Wine) :
    le bloc `saves` ne nomme qu'une racine abstraite et des motifs relatifs
    en « / ». Seule `sauvegardes.racines()` saura où est la racine."""
    for jeu in catalogue["games"]:
        bloc = jeu.get("saves")
        if not bloc:
            continue
        assert bloc["root"] in ("documents", "localappdata")
        for motif in [*bloc["folders"], bloc["files"]]:
            assert "\\" not in motif and ":" not in motif, (jeu["id"], motif)
            assert not motif.startswith("/"), (jeu["id"], motif)


def test_les_bandes_annonces_se_lisent(catalogue):
    from src.core.game_data import _parse_trailers
    declares = catalogue.get("trailers", {})
    assert declares, "le catalogue embarqué ne déclare aucune bande-annonce"
    assert len(_parse_trailers(declares)) == len(declares)


def _jeu(catalogue: dict, ident: str) -> dict:
    return next(j for j in catalogue["games"] if j["id"] == ident)


def _cles(noeud: object):
    """Toutes les paires (clé, valeur) d'ini_patches, où qu'elles soient."""
    if isinstance(noeud, dict):
        if "key" in noeud and "value" in noeud:
            yield str(noeud["key"]), str(noeud["value"])
        for v in noeud.values():
            yield from _cles(v)
    elif isinstance(noeud, list):
        for v in noeud:
            yield from _cles(v)


class TestCeQuiCasseUnJeuSansBruit:
    """Les six garde-fous de CLAUDE.md (détail : CATALOGUE_ET_JEUX.md).
    Chacun a été payé par un jeu cassé SANS message ; un catalogue repris
    du RAW qui en perdrait un ne ferait rougir aucun autre test."""

    @pytest.mark.parametrize("ident", ["hp1", "hp2"])
    def test_running_ini_reste_cree(self, catalogue, ident):
        fichiers = _jeu(catalogue, ident)["pre_launch"]["create_files"]
        assert any(f.endswith(r"\Running.ini") for f in fichiers), ident

    def test_jamais_startup_fullscreen_true(self, catalogue):
        for jeu in catalogue["games"]:
            for cle, valeur in _cles(jeu):
                assert not (cle.lower() == "startupfullscreen" and valeur.lower() == "true"), jeu["id"]

    @pytest.mark.parametrize("ident", ["hp7a", "hp7b"])
    def test_hp7_dans_son_sous_dossier_pc(self, catalogue, ident):
        assert _jeu(catalogue, ident)["post_install"]["sous_dossier"] == "pc"

    @pytest.mark.parametrize("ident", ["hp1", "hp2", "hp3"])
    def test_le_menu_video_reste_verrouille(self, catalogue, ident):
        """Un `.int` sans sa DLL : le menu vidéo la propose, le jeu ne redémarre plus."""
        assert _jeu(catalogue, ident).get("display_locked") is True, ident

    def test_hp3_jamais_au_dela_de_60_images(self, catalogue):
        assert 0 < _jeu(catalogue, "hp3").get("max_fps", 0) <= 60

    @pytest.mark.parametrize(("ident", "anglais", "francais", "prefixe"), [
        ("hp7a", "en_UK", "fr_FR", "HP7/pc/DH1_"),
        ("hp7b", "en", "fr", "HP8/pc/DH2_"),
    ])
    def test_hp7_et_sa_seconde_partie_n_ont_ni_la_meme_locale_ni_les_memes_fichiers(
            self, catalogue, ident, anglais, francais, prefixe):
        """`requires_file` et les valeurs `Locale` diffèrent entre les deux parties : le bloc de
        l'une recopié sur l'autre ne ferait rougir aucun autre test."""
        langues = _jeu(catalogue, ident)["language_registry"]["languages"]
        assert langues["en"]["values"]["Locale"] == anglais, ident
        assert langues["fr"]["values"]["Locale"] == francais, ident
        assert all(langue["requires_file"].startswith(prefixe) for langue in langues.values()), ident


class TestMediatheque:
    def test_les_jeux_de_la_mediatheque_existent_dans_la_copie_embarquee(self, catalogue):
        """La discographie et les cinématiques sont rangées par id de jeu : un id
        absent du catalogue embarqué ne s'afficherait jamais."""
        from src.core import cinematiques, discographie
        ids = {g["id"] for g in catalogue["games"]}
        assert set(cinematiques.charger()) <= ids
        assert set(discographie.charger()) <= ids


def test_aucune_cinematique_n_est_titree_par_son_fichier():
    """Audit UI f31 : vingt cinématiques de V s'intitulaient « Cinématique « dh03 » », et deux de IV
    « Niveau « dw » » ; chacune a été vue image par image et porte un titre dans les trois langues."""
    from src.core import cinematiques
    for jeu, collection in cinematiques.charger().items():
        for clip in collection.clips:
            titres = dict(clip.titres) if not isinstance(clip.titres, str) else {"fr": clip.titres}
            assert set(titres) >= {"fr", "en", "es"} or isinstance(clip.titres, str), (jeu, clip.fichier)
            for langue, texte in titres.items():
                # Un code de fichier entre guillemets (« dh03 », “dw”) : le titre de secours.
                assert not re.search(r"[«“]\s?[a-z0-9_]+\s?[»”]", texte), (jeu, clip.fichier, langue, texte)


def test_le_titre_espagnol_de_hp7_suit_la_graphie_d_ea():
    """Audit UI f111 : le catalogue écrivait « las reliquias de la Muerte », les nouveautés « Las reliquias
    de la muerte », alors que le jeu et son dossier de sauvegarde écrivent « Reliquias de la Muerte »."""
    donnees = GAMES_JSON_PATH.parent
    vus = 0
    for fichier in ("games.json", "nouveautes.json", "atelier.json", "i18n/es.json"):
        for trouve in re.findall(r"reliquias de la muerte", (donnees / fichier).read_text(encoding="utf-8"),
                                 flags=re.IGNORECASE):
            vus += 1
            assert trouve == "Reliquias de la Muerte", (fichier, trouve)
    assert vus >= 4   # le titre est bien là où on le cherche : sinon le test ne prouverait rien


class TestSurchargesDeDll:
    """Le relevé du 2026-09-24 (docs/LINUX.md § 3) : ce que chaque archive
    LIVRE et que Wine 9.0 fournit aussi. Rien de deviné, rien d'oublié —
    un `d3d9` manquant ici et Wine remplace le wrapper du jeu en silence."""

    ATTENDU = {
        # winmm : la DLL du correctif (FillScreen, SkipSetup, manette, lanceur de HP2 sous Wine),
        # que Wine remplacerait par la sienne. Relevé le 2026-10-15, catalogue 0.43.
        "hp1": ("winmm",), "hp2": ("winmm",),
        # dgVoodoo (d3d8, d3d9, ddraw) plante sous Proton : `UD3DRenderDevice::SetRes`,
        # General protection fault ; DXVK seul rend le jeu (HP3, 2026-10-01).
        "hp3": ("msvcr70",),
        "hp4": ("d3d9", "msvcr71"),
        # xinput1_3 : la DLL manette du correctif, `builtin` sans surcharge (HP6, 2026-10-01).
        "hp5": ("d3d9", "xinput1_3"), "hp6": ("d3d9", "xinput1_3"),
        "hp7a": ("d3d9", "xinput1_3"), "hp7b": ("d3d9", "xinput1_3"),
    }

    def test_releve(self):
        cat = load_catalog(GAMES_JSON_PATH)
        assert {g.id: g.dll_overrides for g in cat.games} == self.ATTENDU

    def test_seul_hp3_porte_un_plafond_d_images_et_il_vaut_60(self):
        """`max_fps` : sous Linux, dgVoodoo n'est plus surchargé, c'est DXVK qui tient les 60
        (`DXVK_FRAME_RATE`) ; aucun autre jeu n'a de plafond déclaré."""
        cat = load_catalog(GAMES_JSON_PATH)
        assert {g.id: g.max_fps for g in cat.games if g.max_fps} == {"hp3": 60}


def test_la_difficulte_native_de_hp2(catalogue):
    """La difficulté propre à HP2 (Ludo, 2026-10-30) : trois crans dans `User.ini`."""
    bloc = _parse_difficulte(_jeu(catalogue, "hp2").get("difficulty"))
    assert bloc is not None and bloc.values == ("DifficultyEasy", "DifficultyMedium", "DifficultyHard")
    assert bloc.file.endswith("\\Harry Potter II\\User.ini") and bloc.section == "Engine.PlayerPawn"


class TestLanguesHp1Hp2:
    """Les langues que la copie embarquée propose pour HP1 et HP2 (2026-11-03) :
    espagnol de l'édition US 2003 de HP1 ; anglais (`usa`) et espagnol (`spa`) du
    disque US de HP2. Chaque langue écrit le Documents ET le `default.ini` du jeu,
    et ne s'affiche que si ses voix sont dans l'archive."""

    @pytest.mark.parametrize(("ident", "attendu"), [
        ("hp1", {"fr": "fre", "en": "int", "es": "spa"}),
        ("hp2", {"fr": "fre", "en": "usa", "es": "spa"}),
    ])
    def test_trois_langues_dans_les_deux_fichiers(self, catalogue, ident, attendu):
        bloc = _jeu(catalogue, ident)["language_files"]["languages"]
        assert {code: {p["value"] for p in lg["ini"]} for code, lg in bloc.items()} == {
            code: {v} for code, v in attendu.items()}
        for lg in bloc.values():
            fichiers = [p["file"] for p in lg["ini"]]
            assert len(fichiers) == 2 and fichiers[0].startswith("%DOCUMENTS%")
            assert fichiers[1].startswith("%INSTALL_DIR%") and lg["requires_file"].startswith(ident.upper() + "/Sounds/")


class TestLanguesHp3:
    """Les onze langues de HP3, réunies depuis quatre éditions européennes du CD
    (2026-11-04), et le dossier de Documents figé (`AppUserDir`, voir
    `test_langue_fichiers.TestHP3Langues`)."""

    ATTENDU = {"fr": "Fre", "en": "int", "es": "Spa", "de": "Ger", "it": "Ita", "pt": "Por",
               "pt-BR": "Bra", "nl": "Dut", "sv": "Swe", "da": "Dan", "no": "Nor"}

    def test_invisible_pour_le_launcher_1_3_2(self, catalogue):
        """La 1.3.2 lit `language_files` et écrit Default.ini sans lui rendre sa date :
        HP3 recréait alors les réglages du joueur, dès l'entrée `fr` (son `AppUserDir`)
        avec HP3 1.6. Les langues de HP3 vivent donc sous `language_files_v2`, que
        seule la 1.3.3 lit (2026-11-05)."""
        jeu = _jeu(catalogue, "hp3")
        assert "language_files" not in jeu and "language_files_v2" in jeu
        assert GameData.from_dict(jeu).language_files is not None

    def test_onze_langues_et_leurs_voix(self, catalogue):
        bloc = _jeu(catalogue, "hp3")["language_files_v2"]["languages"]
        assert {code: lg["ini"][0]["value"] for code, lg in bloc.items()} == self.ATTENDU
        for code, lg in bloc.items():
            valeur = self.ATTENDU[code]
            voix = "alldialog.uax" if valeur == "int" else f"alldialog.{valeur.lower()}_uax"
            assert lg["requires_file"] == f"HP3/sounds/{voix}"

    def test_chaque_langue_garde_le_meme_dossier_de_documents(self, catalogue):
        jeu = _jeu(catalogue, "hp3")
        dossier = "Harry Potter et le prisonnier d'Azkaban"
        # Le dossier figé est celui où le launcher écrit la config et cherche les parties.
        assert all(dossier in p["file"] for p in jeu["pre_launch"]["ini_patches"])
        for lg in jeu["language_files_v2"]["languages"].values():
            par_cle = {(p["file"], p["section"], p["key"]): p["value"] for p in lg["ini"]}
            assert par_cle[("%INSTALL_DIR%\\system\\Default.ini", "Core.System", "AppUserDir")] == dossier
            assert par_cle[("%DOCUMENTS%\\" + dossier + "\\hppoa.ini", "Engine.Engine", "Language")] \
                == par_cle[("%INSTALL_DIR%\\system\\Default.ini", "Engine.Engine", "Language")]

    def test_le_bloc_se_lit(self, catalogue):
        lu = _parse_language_files(_jeu(catalogue, "hp3")["language_files_v2"])
        assert lu is not None and lu.codes == tuple(self.ATTENDU)


@pytest.mark.parametrize("ident", ["hp7a", "hp7b"])
def test_chaque_langue_de_hp7_nomme_un_dossier_que_le_bloc_saves_reconnait(catalogue, ident):
    """Un dossier que `saves` ne verrait pas recevrait une partie que la fiche, elle,
    ne trouverait jamais (`test_langue_sauvegardes.py`)."""
    game = GameData.from_dict(_jeu(catalogue, ident))
    dossiers = [lg.saves_folder for lg in game.language_registry.languages]
    assert len(dossiers) == 7 and len(set(dossiers)) == 7
    for d in dossiers:
        assert any(fnmatch(d, m) for m in game.sauvegardes.dossiers), d
