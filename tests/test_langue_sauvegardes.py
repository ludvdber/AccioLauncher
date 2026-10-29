"""HP7 : la partie et les réglages suivent la langue posée.

Le jeu range `auto.sav` et `config.txt` dans un dossier nommé d'après son titre
TRADUIT. Passé du français à l'anglais, il démarrait sans la partie et en 720p,
l'image dans un coin (VU par Ludo le 2026-10-29). Racines redirigées vers
`tmp_path` par `conftest`.
"""

import json
from fnmatch import fnmatch

import pytest

from src.core import game_language, game_registry, sauvegardes
from src.core.config import GAMES_JSON_PATH, Config
from src.core.game_data import GameData, _parse_language_registry

FR = "Electronic Arts/Harry Potter et les Reliques de la Mort (TM) – Deuxième Partie"
EN = "Electronic Arts/Harry Potter and the Deathly Hallows (TM) – Part 2"


def _jeux() -> dict[str, GameData]:
    data = json.loads(GAMES_JSON_PATH.read_text(encoding="utf-8"))
    return {j["id"]: GameData.from_dict(j) for j in data["games"] if j["id"] in ("hp7a", "hp7b")}


@pytest.fixture
def hp7b(monkeypatch):
    """HP7 partie 2 avec un registre qui dit `Locale`, modifiable par le test."""
    registre = {"Locale": "en"}
    monkeypatch.setattr(game_registry, "disponible", lambda: True)
    monkeypatch.setattr(game_registry, "lire_valeurs",
                        lambda ruche, cle, noms, vue=32: {n: registre[n] for n in noms if n in registre})
    return _jeux()["hp7b"], registre


def _poser(rel, contenu):
    chemin = sauvegardes.racines()["localappdata"] / rel
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(contenu)
    return chemin


class TestCatalogue:
    @pytest.mark.parametrize("jeu", ["hp7a", "hp7b"])
    def test_chaque_langue_nomme_un_dossier_que_le_bloc_saves_reconnait(self, jeu):
        """Un dossier que `saves` ne verrait pas recevrait une partie que la
        fiche, elle, ne trouverait jamais."""
        game = _jeux()[jeu]
        dossiers = [lg.saves_folder for lg in game.language_registry.languages]
        assert len(dossiers) == 7 and len(set(dossiers)) == 7
        for d in dossiers:
            assert any(fnmatch(d, m) for m in game.sauvegardes.dossiers), d

    @pytest.mark.parametrize("dossier", ["../Electronic Arts/x", "Electronic Arts/Harry*", "C:/x", ""])
    def test_un_dossier_douteux_ecarte_le_bloc(self, dossier):
        bloc = {"root": "HKLM", "key": "SOFTWARE\\Electronic Arts\\X",
                "languages": {"fr": {"values": {"Locale": "fr"}, "saves_folder": dossier}}}
        attendu = dossier == ""
        assert (_parse_language_registry(bloc) is not None) is attendu


class TestPorter:
    def test_la_partie_et_les_reglages_suivent_la_langue(self, hp7b):
        game, _ = hp7b
        _poser(f"{FR}/auto.sav", b"partie")
        _poser(f"{FR}/config.txt", b"resolutionidx\t0\n")
        assert game_language.porter_sauvegardes(game, Config()) == ["auto.sav", "config.txt"]
        cible = sauvegardes.racines()["localappdata"] / EN
        assert (cible / "auto.sav").read_bytes() == b"partie"
        assert (cible / "config.txt").read_bytes() == b"resolutionidx\t0\n"
        assert (sauvegardes.racines()["localappdata"] / FR / "auto.sav").read_bytes() == b"partie"

    def test_rien_n_est_jamais_ecrase(self, hp7b):
        """Le cas de la machine de Ludo : le dossier anglais n'a que ses réglages."""
        game, _ = hp7b
        _poser(f"{FR}/auto.sav", b"partie")
        _poser(f"{FR}/config.txt", b"fr")
        _poser(f"{EN}/config.txt", b"en")
        assert game_language.porter_sauvegardes(game, Config()) == ["auto.sav"]
        assert (sauvegardes.racines()["localappdata"] / EN / "config.txt").read_bytes() == b"en"

    def test_deja_dans_le_bon_dossier(self, hp7b):
        game, registre = hp7b
        registre["Locale"] = "fr"
        _poser(f"{FR}/auto.sav", b"partie")
        assert game_language.porter_sauvegardes(game, Config()) == []

    def test_langue_inconnue_ou_sans_partie(self, hp7b):
        game, registre = hp7b
        assert game_language.porter_sauvegardes(game, Config()) == []
        registre["Locale"] = "xx"
        _poser(f"{FR}/auto.sav", b"partie")
        assert game_language.porter_sauvegardes(game, Config()) == []
        assert not (sauvegardes.racines()["localappdata"] / EN).exists()

    def test_sans_registre_rien_ne_bouge(self, hp7b, monkeypatch):
        game, _ = hp7b
        monkeypatch.setattr(game_registry, "disponible", lambda: False)
        _poser(f"{FR}/auto.sav", b"partie")
        assert game_language.porter_sauvegardes(game, Config()) == []
