"""Les invariants du fuzzing, rejoués sur des cas connus.

Atheris ne tourne que sous Linux (workflow `fuzz.yml`) : sans ce fichier, un
invariant devenu faux — ou une barrière qui aurait changé — ne se verrait
qu'en CI, et pas dans `build.bat`. Chaque cas ci-dessous est une attaque déjà
écrite quelque part dans ce projet, ou un défaut que le fuzzing a trouvé.
"""

import copy
import json

import pytest

from fuzz import invariants
from src.core.config import GAMES_JSON_PATH


@pytest.fixture(scope="module")
def vrai_catalogue():
    return json.loads(GAMES_JSON_PATH.read_text(encoding="utf-8"))


class TestCatalogue:
    def test_le_vrai_catalogue(self, vrai_catalogue):
        invariants.catalogue(vrai_catalogue)

    @pytest.mark.parametrize("brut", [None, 42, "x", [], {}, {"games": "x"}, [1, "a", None]])
    def test_racines_absurdes(self, brut):
        invariants.catalogue(brut)

    def test_annee_infinie_ne_plante_pas(self, vrai_catalogue):
        """Trouvé en préparant le fuzzing : `1e999` est du JSON valide, et
        `int(inf)` lève OverflowError, qui traversait `load_catalog`."""
        brut = copy.deepcopy(vrai_catalogue)
        brut["games"][0]["year"] = float("inf")
        invariants.catalogue(brut)

    @pytest.mark.parametrize("champ, valeur", [
        ("executable", "../../evil.exe"),
        ("executable", "..\\..\\evil.exe"),
        ("executable", "C:/Windows/evil.exe"),
        ("warning_url", "javascript:alert(1)"),
        ("post_install", {"sous_dossier": "../pc"}),
        ("versions", [{"version": "1", "download_url": "http://x"}]),
        ("versions", [{"version": "1", "download_parts": ["https://a", "file:///b"]}]),
    ])
    def test_valeurs_hostiles(self, vrai_catalogue, champ, valeur):
        brut = copy.deepcopy(vrai_catalogue)
        brut["games"][0][champ] = valeur
        invariants.catalogue(brut)

    def test_injection_reg_par_le_catalogue(self, vrai_catalogue):
        brut = copy.deepcopy(vrai_catalogue)
        jeu = next(j for j in brut["games"] if "language_registry" in j)
        langue = next(iter(jeu["language_registry"]["languages"].values()))
        langue["values"] = {"Locale": 'fr\r\n[HKEY_LOCAL_MACHINE\\x]\r\n"a"="b"'}
        invariants.catalogue(brut)


class TestRegistre:
    CLE = "Software\\Electronic Arts\\Jeu"

    @pytest.mark.parametrize("valeur", [
        "French\r\n[HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run]\r\n\"x\"=\"evil.exe\"",
        "fr\u0085[HKEY_LOCAL_MACHINE\\x]",      # NEL, un saut de ligne C1
        "fr\u2028x",                             # séparateur de ligne Unicode
        'fr"\\',
        "C:\\Jeux\\HP7\\",
    ])
    def test_valeurs(self, valeur):
        invariants.registre_ecrit("HKLM", self.CLE, {"Locale": valeur}, 32)

    @pytest.mark.parametrize("cle", [
        "Software\\a]\r\n[HKEY_LOCAL_MACHINE\\x",
        "Software\\Microsoft\\Windows\\CurrentVersion\\Run",
        "Software\\..\\..\\System",
        "Software\\Editeur\u2029Jeu",
    ])
    def test_cles(self, cle):
        invariants.registre_ecrit("HKLM", cle, {"Locale": "fr"}, 32)

    def test_les_separateurs_unicode_sont_refuses(self):
        """Durci en préparant le fuzzing : `_controle` ne voyait que le C0 et
        DEL ; NEL et les séparateurs Unicode passaient."""
        from src.core.game_registry import refus_de_valeur
        for c in ("\u0085", "\u2028", "\u2029", "\x9b"):
            assert refus_de_valeur("Locale", "fr" + c) is not None


class TestArchive:
    @pytest.mark.parametrize("nom", [
        "HP1/System/HP.exe", "../evil.dll", "..\\evil.dll", "a/../../x",
        "C:/x", "/etc/passwd", "//serveur/partage", " ../x", ".. /evil.dll",
        "a/.. /.. /x", "... /x", "./ok.txt", " ./x", "a/C:x", "HP.exe:flux",
    ])
    def test_noms(self, tmp_path, nom):
        destination = tmp_path / "jeu"
        destination.mkdir()
        invariants.entree_archive(destination, nom)

    @pytest.mark.parametrize("nom", [".. /evil.dll", "a/.. /.. /x", "... /x", "a/ ./b",
                                     " ./x", "a/C:x", "HP1/System/HP.exe:flux"])
    def test_points_et_espaces_refuses(self, nom):
        """Durci en préparant le fuzzing : Windows retire points et espaces en
        fin de nom, et `check_path_traversal` jugeait « .. /x » HORS du
        dossier quand `is_unsafe_entry` le jugeait sûr. Même désaccord sur un
        deux-points hors de la tête du nom, qui désigne sous NTFS un flux de
        données alternatif."""
        from src.core.extractors import is_unsafe_entry
        assert is_unsafe_entry(nom)
