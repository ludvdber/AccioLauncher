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

import pytest

from src.core.config import GAMES_JSON_PATH


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

    def test_hp7b_n_a_pas_de_format(self, catalogue):
        """Son ini n'a pas d'AspectRatio : rien ne lirait la clé."""
        hp7b = next(j for j in catalogue["games"] if j["id"] == "hp7b")
        assert "format_image" not in hp7b["fix_settings"]


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
