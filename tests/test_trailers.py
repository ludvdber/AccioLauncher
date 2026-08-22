"""Bandes-annonces : catalogue, stockage sur disque, ménage, téléchargement.

Elles ont quitté l'exécutable (74 → 160 Mo pour DEUX d'entre elles). Ce fichier
garde les trois choses qui, si elles cassaient, casseraient en silence : le nom
de fichier PORTE la version, le ménage ne touche QUE nos fichiers, et une
version venue du catalogue distant ne peut pas écrire hors du dossier.
"""

import json
from unittest.mock import patch

import pytest

from src.core import trailers as store
from src.core.game_data import Trailer, _parse_trailers


def _t(game_id="hp1", version="1.0", size_mb=10):
    return Trailer(game_id=game_id, version=version,
                   url=f"https://example.org/{game_id}_video.mp4", size_mb=size_mb)


@pytest.fixture
def dossier(tmp_path):
    """Redirige le dossier des bandes-annonces vers un tmp_path."""
    with patch.object(store, "TRAILERS_DIR", tmp_path):
        yield tmp_path


def _poser(dossier, nom, octets=b"x"):
    f = dossier / nom
    f.write_bytes(octets)
    return f


# ────────────────────────── Catalogue ──────────────────────────

class TestParsing:
    def test_entree_minimale(self):
        t = _parse_trailers({"hp1": {"version": "1.0",
                                     "url": "https://x/hp1_video.mp4"}})
        assert len(t) == 1
        assert t[0].game_id == "hp1"
        assert t[0].version == "1.0"
        assert t[0].size_mb == 0

    def test_http_refuse(self):
        """Même barrière que les archives : non-https écarté AU PARSING."""
        assert _parse_trailers({"hp1": {"version": "1.0",
                                        "url": "http://x/a.mp4"}}) == ()

    @pytest.mark.parametrize("version", [
        "../../evil", "..", "a/b", "a\\b", "", "1.0 ", ".hidden",
    ])
    def test_version_impropre_a_un_nom_de_fichier(self, version):
        """La version vient du catalogue DISTANT et finit dans un nom de fichier.

        Sans ce filtre, `"version": "../../../evil"` ferait écrire hors du
        dossier des bandes-annonces — même risque que les chemins `executable`.
        """
        assert _parse_trailers({"hp1": {"version": version,
                                        "url": "https://x/a.mp4"}}) == ()

    @pytest.mark.parametrize("game_id", ["../hp1", "hp1/../..", "", "a\\b"])
    def test_identifiant_impropre(self, game_id):
        assert _parse_trailers({game_id: {"version": "1.0",
                                          "url": "https://x/a.mp4"}}) == ()

    def test_entree_cassee_ignoree_pas_levee(self):
        """Un ornement ne doit jamais priver quelqu'un de sa bibliothèque."""
        t = _parse_trailers({
            "hp1": "pas un dict",
            "hp2": {"version": 3, "url": "https://x/a.mp4"},
            "hp3": {"version": "1.0", "url": "https://x/hp3_video.mp4"},
        })
        assert [x.game_id for x in t] == ["hp3"]

    def test_bloc_absent_ou_aberrant(self):
        assert _parse_trailers(None) == ()
        assert _parse_trailers([1, 2, 3]) == ()

    def test_taille_negative_ramenee_a_zero(self):
        t = _parse_trailers({"hp1": {"version": "1.0", "url": "https://x/a.mp4",
                                     "size_mb": -500}})
        assert t[0].size_mb == 0

    def test_catalogue_reel_parse_ses_trailers(self):
        """Le `games.json` embarqué déclare bien ses bandes-annonces."""
        from src.core.config import GAMES_JSON_PATH
        brut = json.loads(GAMES_JSON_PATH.read_text(encoding="utf-8"))
        declares = brut.get("trailers", {})
        assert declares, "le catalogue embarqué ne déclare aucune bande-annonce"
        assert len(_parse_trailers(declares)) == len(declares)


class TestNomDeFichier:
    def test_le_nom_porte_la_version(self):
        """Sans la version dans le nom, améliorer une bande-annonce ne
        remplacerait jamais l'ancienne : le nom de l'ASSET, lui, ne change pas.

        C'est exactement le défaut déjà payé sur les parts d'archive de HP5.
        """
        assert _t(version="1.0").filename == "hp1_video_v1.0.mp4"
        assert _t(version="2.0").filename == "hp1_video_v2.0.mp4"
        assert _t(version="1.0").filename != _t(version="2.0").filename


# ────────────────────────── Disque ──────────────────────────

class TestPresence:
    def test_absent(self, dossier):
        assert store.present(_t()) is False

    def test_present(self, dossier):
        _poser(dossier, "hp1_video_v1.0.mp4", b"0123456789")
        assert store.present(_t()) is True

    def test_fichier_vide_compte_comme_absent(self, dossier):
        """Résidu d'un téléchargement coupé : le compter présent afficherait
        une vidéo qui ne démarre jamais, sans rien pour l'expliquer."""
        _poser(dossier, "hp1_video_v1.0.mp4", b"")
        assert store.present(_t()) is False

    def test_dossier_inexistant(self, tmp_path):
        with patch.object(store, "TRAILERS_DIR", tmp_path / "jamais_cree"):
            assert store.present(_t()) is False
            assert store.poids_disque() == 0
            assert store.fichiers_perimes([_t()]) == []

    def test_une_autre_version_ne_compte_pas(self, dossier):
        _poser(dossier, "hp1_video_v1.0.mp4", b"xx")
        assert store.present(_t(version="2.0")) is False


class TestManquantes:
    def test_ordre_du_catalogue_preserve(self, dossier):
        liste = [_t("hp1"), _t("hp2"), _t("hp3")]
        _poser(dossier, "hp2_video_v1.0.mp4", b"xx")
        assert [t.game_id for t in store.manquantes(liste)] == ["hp1", "hp3"]

    def test_poids_ne_compte_que_le_manquant(self, dossier):
        liste = [_t("hp1", size_mb=80), _t("hp2", size_mb=20)]
        _poser(dossier, "hp1_video_v1.0.mp4", b"xx")
        assert store.poids_a_telecharger(liste) == 20

    def test_nombre_present(self, dossier):
        liste = [_t("hp1"), _t("hp2")]
        _poser(dossier, "hp1_video_v1.0.mp4", b"xx")
        assert store.nombre_present(liste) == 1


class TestMenage:
    def test_ancienne_version_est_perimee(self, dossier):
        _poser(dossier, "hp1_video_v1.0.mp4", b"xx")
        perimes = store.fichiers_perimes([_t(version="2.0")])
        assert [f.name for f in perimes] == ["hp1_video_v1.0.mp4"]

    def test_jeu_disparu_du_catalogue_est_perime(self, dossier):
        _poser(dossier, "hp9_video_v1.0.mp4", b"xx")
        assert [f.name for f in store.fichiers_perimes([_t()])] == \
            ["hp9_video_v1.0.mp4"]

    def test_version_attendue_non_perimee(self, dossier):
        _poser(dossier, "hp1_video_v1.0.mp4", b"xx")
        assert store.fichiers_perimes([_t(version="1.0")]) == []

    def test_un_fichier_etranger_n_est_jamais_touche(self, dossier):
        """Le dossier appartient à l'utilisateur : on n'y jette que nos fichiers."""
        intrus = _poser(dossier, "mes_notes.txt", b"important")
        autre = _poser(dossier, "hp1_video.mp4", b"depose a la main")
        _poser(dossier, "hp1_video_v1.0.mp4", b"xx")
        store.supprimer_tout()
        assert intrus.exists()
        assert autre.exists()
        assert not (dossier / "hp1_video_v1.0.mp4").exists()

    def test_supprimer_tout_rend_le_compte(self, dossier):
        _poser(dossier, "hp1_video_v1.0.mp4", b"0123456789")
        _poser(dossier, "hp2_video_v1.0.mp4", b"01234")
        n, octets = store.supprimer_tout()
        assert (n, octets) == (2, 15)

    def test_poids_disque(self, dossier):
        _poser(dossier, "hp1_video_v1.0.mp4", b"0123456789")
        _poser(dossier, "pas_le_notre.mp4", b"0123456789")
        assert store.poids_disque() == 10


class TestChemenAJouer:
    def test_telechargee_prioritaire(self, dossier):
        t = _t()
        _poser(dossier, t.filename, b"xx")
        assert store.chemin_a_jouer("hp1", [t]) == dossier / t.filename

    def test_repli_sur_l_ancien_emplacement_embarque(self, dossier, tmp_path):
        """`assets/videos` n'est plus livré, mais reste consulté : les fichiers
        sont là en développement, et quelqu'un peut déposer les siens."""
        assets = tmp_path / "assets"
        (assets / "videos").mkdir(parents=True)
        (assets / "videos" / "hp1_video.mp4").write_bytes(b"xx")
        with patch.object(store, "ASSETS_DIR", assets):
            assert store.chemin_a_jouer("hp1", []) == assets / "videos" / "hp1_video.mp4"

    def test_rien_nulle_part(self, dossier, tmp_path):
        with patch.object(store, "ASSETS_DIR", tmp_path / "vide"):
            assert store.chemin_a_jouer("hp1", [_t()]) is None

    def test_declaree_mais_pas_telechargee(self, dossier, tmp_path):
        """Déclarée au catalogue mais absente du disque : pas de vidéo, et
        surtout pas le fichier d'une AUTRE version."""
        _poser(dossier, "hp1_video_v1.0.mp4", b"xx")
        with patch.object(store, "ASSETS_DIR", tmp_path / "vide"):
            assert store.chemin_a_jouer("hp1", [_t(version="2.0")]) is None


class TestOutilDeSynchronisation:
    """`tools/sync_trailers.py` écrit le bloc `trailers` à partir d'une release.

    Il existe pour qu'aucune URL ni aucune taille ne soit recopiée à la main :
    une URL fautive donne un 404 silencieux, et un `size_mb` sous-estimé fait
    avorter un téléchargement parfaitement sain (plafond ×1,5).
    """

    ASSETS = [
        {"name": "hp1_video.mp4", "size": 85_715_815,
         "browser_download_url": "https://github.com/x/y/releases/download/trailers-v1/hp1_video.mp4"},
        {"name": "notes.txt", "size": 12, "browser_download_url": "https://x/notes.txt"},
    ]

    def _outil(self):
        import importlib
        return importlib.import_module("tools.sync_trailers")

    def test_taille_arrondie_au_superieur(self):
        """`size_mb` est un PLAFOND : arrondi vers le bas, il coupe le
        téléchargement qu'il devait protéger. 81,74 Mo doit donner 82."""
        bloc, ignores = self._outil().bloc_trailers(self.ASSETS, {}, None)
        assert bloc["hp1"]["size_mb"] == 82
        assert ignores == ["notes.txt"]

    def test_version_existante_conservee(self):
        """Ajouter une bande-annonce ne doit pas re-versionner les autres :
        chaque changement de version force un re-téléchargement complet."""
        anciens = {"hp1": {"version": "3.0"}}
        bloc, _ = self._outil().bloc_trailers(self.ASSETS, anciens, None)
        assert bloc["hp1"]["version"] == "3.0"
        force, _ = self._outil().bloc_trailers(self.ASSETS, anciens, "4.0")
        assert force["hp1"]["version"] == "4.0"

    def test_le_bloc_produit_est_relu_par_le_catalogue(self):
        """Le contrat de bout en bout : ce que l'outil écrit, `_parse_trailers`
        doit le rendre — sinon on publie un catalogue muet."""
        bloc, _ = self._outil().bloc_trailers(self.ASSETS, {}, None)
        relus = _parse_trailers(bloc)
        assert [t.game_id for t in relus] == ["hp1"]
        assert relus[0].filename == "hp1_video_v1.0.mp4"

    def test_ecriture_idempotente_et_mise_en_forme_preservee(self, tmp_path):
        """Le catalogue distant est en CRLF indenté à 4 espaces : le reformater
        noierait la vraie modification dans un diff de 400 lignes."""
        outil = self._outil()
        crlf = chr(13) + chr(10)
        cible = tmp_path / 'games.json'
        cible.write_bytes(crlf.join([
            '{', '    "catalog_version": "0.5",', '    "games": [],',
            '    "trailers": {}', '}', '']).encode('utf-8'))
        bloc, _ = outil.bloc_trailers(self.ASSETS, {}, None)
        assert outil.ecrire(cible, bloc, False) is True
        brut = cible.read_bytes()
        assert brut.count(crlf.encode()) > 0
        assert brut.count(chr(10).encode()) == brut.count(crlf.encode()), (
            'des LF isolés se sont glissés dans un fichier CRLF')
        assert outil.ecrire(cible, bloc, False) is False, (
            "l'outil n'est pas idempotent")

    def test_bump_du_catalogue(self, tmp_path):
        """Un distant inférieur ou égal à l'embarqué ne serait jamais adopté :
        `update_disponible` exige STRICTEMENT supérieur."""
        outil = self._outil()
        cible = tmp_path / "games.json"
        cible.write_text(json.dumps({"catalog_version": "0.21", "games": [],
                                     "trailers": {}}), encoding="utf-8")
        bloc, _ = outil.bloc_trailers(self.ASSETS, {}, None)
        outil.ecrire(cible, bloc, True)
        assert json.loads(cible.read_text(encoding="utf-8"))["catalog_version"] == "0.22"
