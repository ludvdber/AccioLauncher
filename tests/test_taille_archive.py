"""Poids annoncé d'un téléchargement : celui de l'archive, pas du jeu installé.

Mesuré le 2026-08-21 : le `size_mb` du catalogue est la taille du jeu UNE FOIS
INSTALLÉ. Le bouton « TÉLÉCHARGER » l'affichait comme un poids de
téléchargement, soit de 1,77 à 2,30 fois la réalité (HP3 : « 775 Mo » annoncés
pour 337 Mo réels, HP6 : « 4,4 Go » pour 2,1 Go). La barre de progression, elle,
compte les octets reçus : l'interface se contredisait d'un écran à l'autre.

Le vrai chiffre vient de GitHub, dans la MÊME réponse que les compteurs et les
empreintes — aucune requête de plus, aucune saisie à la main. Absent, on retombe
sur le catalogue : un poids approximatif vaut mieux que pas de poids du tout.
"""

import pytest

pytest.importorskip("pytestqt")

from src.core.config import Config  # noqa: E402
from src.core.game_data import GameVersion  # noqa: E402
from src.core.game_manager import GameManager  # noqa: E402
from src.core.system_checks import needed_space_mb  # noqa: E402
from src.core.updater import extract_asset_sizes  # noqa: E402

MO = 1024 * 1024


def _release(*assets):
    return {"assets": [{"browser_download_url": u, "size": t} for u, t in assets]}


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
    cfg = Config(install_path=tmp_path / "games", cache_path=tmp_path / "cache",
                 langue="fr", autoplay_videos=False)
    cfg.save()
    return GameManager(cfg)


class TestExtraction:
    """Partie pure : lire les tailles d'une réponse d'API, sans rien casser."""

    def test_les_tailles_sont_lues(self):
        rel = _release(("https://x.test/hp1.7z", 254_803_968))
        assert extract_asset_sizes([rel]) == {"https://x.test/hp1.7z": 254_803_968}

    def test_une_reponse_aberrante_ne_leve_rien(self):
        """Portail captif, proxy, page d'erreur : dégrader, jamais planter."""
        assert extract_asset_sizes([None, 42, {"assets": None},
                                    {"assets": ["texte"]}]) == {}

    def test_les_tailles_absurdes_sont_ignorees(self):
        rel = {"assets": [
            {"browser_download_url": "https://x.test/a", "size": 0},
            {"browser_download_url": "https://x.test/b", "size": -1},
            {"browser_download_url": "https://x.test/c", "size": "12"},
            {"browser_download_url": "", "size": 99},
        ]}
        assert extract_asset_sizes([rel]) == {}

    def test_un_booleen_n_est_pas_une_taille(self):
        """`True` vaut 1 pour `isinstance(int)` : un octet d'archive, vraiment ?"""
        rel = {"assets": [{"browser_download_url": "https://x.test/a", "size": True}]}
        assert extract_asset_sizes([rel]) == {}


class TestPoidsReel:
    def test_fichier_unique(self, manager):
        v = GameVersion(version="1.0", date="", download_url="https://x.test/hp1.7z",
                        download_parts=None, size_mb=431, changes=())
        manager.set_asset_sizes({"https://x.test/hp1.7z": 243 * MO})
        assert manager.archive_size_mb(v) == 243

    def test_sans_reponse_de_l_api_on_ne_ment_pas_par_defaut(self, manager):
        """0 = « je ne sais pas » ; l'appelant retombe alors sur le catalogue."""
        v = GameVersion(version="1.0", date="", download_url="https://x.test/hp1.7z",
                        download_parts=None, size_mb=431, changes=())
        assert manager.archive_size_mb(v) == 0

    def test_multi_parts_additionne(self, manager):
        v = GameVersion(version="1.1", date="", download_url=None,
                        download_parts=("https://x.test/hp5.7z.001",
                                        "https://x.test/hp5.7z.002"),
                        size_mb=4600, changes=())
        manager.set_asset_sizes({"https://x.test/hp5.7z.001": 2000 * MO,
                                 "https://x.test/hp5.7z.002": 490 * MO})
        assert manager.archive_size_mb(v) == 2490

    def test_multi_parts_c_est_tout_ou_rien(self, manager):
        """Une somme partielle annoncerait moins que la réalité — pire que rien.

        Le garde-fou de taille du téléchargeur (×1,5) couperait alors un
        téléchargement parfaitement sain.
        """
        v = GameVersion(version="1.1", date="", download_url=None,
                        download_parts=("https://x.test/hp5.7z.001",
                                        "https://x.test/hp5.7z.002"),
                        size_mb=4600, changes=())
        manager.set_asset_sizes({"https://x.test/hp5.7z.001": 2000 * MO})
        assert manager.archive_size_mb(v) == 0

    def test_la_casse_de_l_asset_n_empeche_pas_la_correspondance(self, manager):
        """Cas réel : le catalogue écrit « hp5.7z.001 », l'asset « HP5.7z.001 »."""
        v = GameVersion(version="1.0", date="", download_url=None,
                        download_parts=("https://x.test/hp5-v1.0/hp5.7z.001",), size_mb=4600,
                        changes=())
        manager.set_asset_sizes({"https://x.test/hp5-v1.0/HP5.7z.001": 2490 * MO})
        assert manager.archive_size_mb(v) == 2490

    def test_une_ambiguite_de_casse_est_ecartee(self, manager):
        """Deux tailles pour la même URL à la casse près : ne pas deviner."""
        v = GameVersion(version="1.0", date="", download_url="https://x.test/HP5.7z",
                        download_parts=None, size_mb=4600, changes=())
        manager.set_asset_sizes({"https://x.test/hp5.7z": 100 * MO,
                                 "https://x.test/Hp5.7z": 200 * MO})
        assert manager.archive_size_mb(v) == 0


class TestEspaceDisque:
    def test_le_pic_est_la_somme_archive_plus_installe(self):
        """HP5 : 2 490 Mo d'archive cohabitent avec les fichiers extraits."""
        assert needed_space_mb(4600, 2490) == 7444

    def test_l_exigence_couvre_le_pic_REELLEMENT_mesure(self):
        """Le seul chiffre qui compte : ce que HP5 occupe vraiment au pic.

        2 490 Mo d'archive + 4 709 Mo mesurés sur disque le 2026-08-21. Le
        catalogue en annonce 4 600 : sans marge, l'exigence tombait SOUS le
        pic et l'extraction aurait manqué de place après coup.
        """
        assert needed_space_mb(4600, 2490) >= 2490 + 4709

    def test_sans_taille_reelle_on_garde_le_double(self):
        assert needed_space_mb(4600) == 9200

    def test_l_ancienne_regle_reclamait_deux_giga_de_trop(self):
        """Le chiffre qui justifie ce correctif, gardé sous test."""
        ancien, nouveau = needed_space_mb(4600), needed_space_mb(4600, 2490)
        assert ancien - nouveau == 1756


class TestBouton:
    """Ce que l'utilisateur lit réellement sur le bouton principal."""

    def _libelle(self, panel):
        for i in range(panel._action_layout.count()):
            w = panel._action_layout.itemAt(i).widget()
            texte = w.text() if w is not None and hasattr(w, "text") else ""
            if texte and "CHARGER" in texte:
                return texte
        return ""

    def test_le_poids_reel_remplace_celui_du_catalogue(self, manager, qtbot):
        from src.core.i18n import set_language
        from src.ui.action_panel import ActionPanel
        set_language("fr")

        jeu = next(e.game for e in manager.get_games()
                   if e.game.id == "hp3" and e.game.current_download.is_available)
        panel = ActionPanel(manager)
        qtbot.addWidget(panel)

        panel.set_game(jeu)
        panel.refresh()
        assert "775 Mo" in self._libelle(panel), "repli attendu sur le catalogue"

        manager.set_asset_sizes({jeu.current_download.download_url: 337 * MO})
        panel.refresh()
        libelle = self._libelle(panel)
        assert "337 Mo" in libelle
        assert "775 Mo" not in libelle
