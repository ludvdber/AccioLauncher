"""Tests pour src/core/game_data.py"""

import pytest

from src.core.i18n import set_language
from src.core.game_data import (
    GameData, GameVersion, IniPatch,
    _parse_catalog,
)


MINIMAL_GAME = {
    "id": "hp_test",
    "name": "HP Test",
    "year": 2001,
    "description": "Test game",
    "developer": "TestDev",
    "executable": "HPTest/Game.exe",
    "cover_image": "test_cover.jpg",
}

FULL_GAME = {
    **MINIMAL_GAME,
    "tags": ["Action", "Aventure"],
    "latest_version": "1.1",
    "recommended_version": "1.1",
    "versions": [
        {
            "version": "1.1",
            "date": "2026-01-01",
            "download_url": "https://example.com/v1.1.7z",
            "download_parts": None,
            "size_mb": 500,
            "changes": ["Fix A", "Fix B"],
        },
        {
            "version": "1.0",
            "date": "2025-01-01",
            "download_url": "https://example.com/v1.0.7z",
            "download_parts": None,
            "size_mb": 480,
            "changes": ["Initial release"],
        },
    ],
    "pre_launch": {
        "create_files": ["%DOCUMENTS%\\Test\\Running.ini"],
        "ini_patches": [
            {
                "file": "%DOCUMENTS%\\Test\\Game.ini",
                "section": "Engine.Engine",
                "key": "GameRenderDevice",
                "value": "D3D11Drv.D3D11RenderDevice",
                "fallback": "D3DDrv.D3DRenderDevice",
            },
        ],
    },
    "post_install": {
        "registry": ["HKCU\\Software\\Test=value"],
        "config_files": [
            {"source": "config/Game.ini", "destination": "~/Documents/Test/Game.ini"},
        ],
    },
}


class TestGameVersion:
    def test_from_dict(self):
        v = GameVersion.from_dict(FULL_GAME["versions"][0])
        assert v.version == "1.1"
        assert v.size_mb == 500
        assert len(v.changes) == 2
        assert v.download_parts is None

    def test_from_dict_defaults(self):
        v = GameVersion.from_dict({})
        assert v.version == "1.0"
        assert v.size_mb == 0
        assert v.changes == ()
        # Empreintes absentes → vérification désactivée (rétro-compat catalogue)
        assert v.sha256 is None
        assert v.sha256_parts == ()

    def test_from_dict_sha256(self):
        v = GameVersion.from_dict({
            "version": "1.2",
            "sha256": "a" * 64,
            "sha256_parts": ["b" * 64, "c" * 64],
        })
        assert v.sha256 == "a" * 64
        assert v.sha256_parts == ("b" * 64, "c" * 64)


class TestIniPatch:
    def test_from_dict_with_fallback(self):
        p = IniPatch.from_dict(FULL_GAME["pre_launch"]["ini_patches"][0])
        assert p.key == "GameRenderDevice"
        assert p.fallback == "D3DDrv.D3DRenderDevice"

    def test_from_dict_without_fallback(self):
        p = IniPatch.from_dict({
            "file": "test.ini", "section": "S", "key": "K", "value": "V",
        })
        assert p.fallback is None


class TestGameData:
    def test_from_dict_minimal(self):
        g = GameData.from_dict(MINIMAL_GAME)
        assert g.id == "hp_test"
        assert g.tags == ()
        assert g.pre_launch is None

    def test_from_dict_full(self):
        g = GameData.from_dict(FULL_GAME)
        assert len(g.versions) == 2
        assert len(g.tags) == 2
        assert g.pre_launch is not None
        assert len(g.pre_launch.ini_patches) == 1
        assert g.pre_launch.ini_patches[0].fallback == "D3DDrv.D3DRenderDevice"
        assert len(g.post_install.config_files) == 1

    def test_missing_fields_raises(self):
        with pytest.raises(ValueError, match="Champs manquants"):
            GameData.from_dict({"id": "x"})

    def test_current_download(self):
        g = GameData.from_dict(FULL_GAME)
        dl = g.current_download
        assert dl is not None
        assert dl.version == "1.1"  # recommended_version

    def test_get_version(self):
        g = GameData.from_dict(FULL_GAME)
        assert g.get_version("1.0") is not None
        assert g.get_version("1.0").size_mb == 480
        assert g.get_version("9.9") is None


class TestParseCatalog:
    def test_dict_format(self):
        raw = {
            "catalog_version": "0.7",
            "catalog_url": "https://example.com/games.json",
            "games": [MINIMAL_GAME],
        }
        cat = _parse_catalog(raw)
        assert cat.catalog_version == "0.7"
        assert len(cat.games) == 1

    def test_list_format_legacy(self):
        raw = [MINIMAL_GAME]
        cat = _parse_catalog(raw)
        assert cat.catalog_version == "0"
        assert len(cat.games) == 1

    def test_empty(self):
        cat = _parse_catalog({"games": []})
        assert cat.games == ()

    def test_invalid_game_is_skipped_not_crashing(self):
        """Régression d'audit : un jeu mal typé dans un cache trafiqué est ignoré,
        les jeux valides restent — pas de TypeError qui remonte au boot."""
        raw = {"catalog_version": "9", "games": [
            MINIMAL_GAME,
            42,                                  # entier au lieu d'objet
            {"id": "bad", "name": "B", "year": None, "description": "d",
             "developer": "e", "executable": "b.exe", "cover_image": "c.png"},
        ]}
        cat = _parse_catalog(raw)
        assert len(cat.games) == 1
        assert cat.games[0].id == "hp_test"

    def test_aberrant_root_raises_valueerror(self):
        """Un JSON aberrant lève ValueError (rattrapée par load_catalog), jamais TypeError."""
        with pytest.raises(ValueError):
            _parse_catalog(99)
        with pytest.raises(ValueError):
            _parse_catalog({"games": 42})


class TestVersionAvailability:
    """Un jeu peut figurer au catalogue avant que ses archives soient en ligne.

    Sans ce contrôle, le bouton TÉLÉCHARGER restait actif, le téléchargeur
    échouait sur « Aucune URL de téléchargement » et l'utilisateur recevait
    « Vérifiez votre connexion internet » — accusation injuste : c'est le
    catalogue qui est en avance sur les archives, pas le réseau.
    """

    @staticmethod
    def _version(**kw) -> GameVersion:
        base = {"version": "1.0", "date": "", "download_url": None,
                "download_parts": None, "size_mb": 100, "changes": ()}
        return GameVersion(**{**base, **kw})

    def test_url_simple_disponible(self):
        assert self._version(download_url="https://ex.com/a.7z").is_available is True

    def test_multiparts_disponible(self):
        v = self._version(download_parts=["https://ex.com/a.7z.001"])
        assert v.is_available is True

    def test_sans_source_indisponible(self):
        assert self._version().is_available is False

    def test_parts_vides_indisponible(self):
        """Une liste vide n'est pas une source."""
        assert self._version(download_parts=[]).is_available is False

    def test_chaine_vide_indisponible(self):
        assert self._version(download_url="").is_available is False

    def test_jeu_telechargeable_si_une_version_lest(self):
        game = GameData.from_dict({**FULL_GAME})
        assert game.is_downloadable is True

    def test_jeu_non_telechargeable_si_aucune_source(self):
        """Cas réel du catalogue : hp7a / hp7b annoncés sans archive."""
        data = {
            **MINIMAL_GAME,
            "recommended_version": "1.0",
            "versions": [{"version": "1.0", "date": "2026-04-06",
                          "download_url": None, "download_parts": None,
                          "size_mb": 5000, "changes": ["Version originale"]}],
        }
        game = GameData.from_dict(data)
        assert game.is_downloadable is False
        assert game.current_download is not None, "la version existe, elle n'est juste pas publiée"
        assert game.current_download.is_available is False

    def test_jeu_sans_version_non_telechargeable(self):
        assert GameData.from_dict(MINIMAL_GAME).is_downloadable is False


class TestCatalogueTraduit:
    """Blocs `i18n` du catalogue — résolus au parsing (voir game_data._loc).

    Les traductions du catalogue voyagent DANS le catalogue et non dans le
    dictionnaire du launcher : le catalogue se met à jour à distance, donc un
    jeu ajouté doit pouvoir arriver déjà traduit sans republier l'exécutable.
    """

    GAME = {
        **MINIMAL_GAME,
        "tags": ["Aventure", "Énigmes"],
        "recommended_version": "1.0",
        "versions": [{
            "version": "1.0", "date": "2026-01-01",
            "download_url": "https://example.org/a.7z", "size_mb": 10,
            "changes": ["Version originale du jeu"],
            "i18n": {"en": {"changes": ["Original game release"]}},
        }],
        "i18n": {
            "en": {"name": "HP Test EN", "description": "Test game EN",
                   "tags": ["Adventure", "Puzzles"]},
        },
    }

    @staticmethod
    def _parse(lang: str) -> GameData:
        set_language(lang)
        try:
            return GameData.from_dict({**TestCatalogueTraduit.GAME})
        finally:
            set_language("fr")

    def test_francais_est_la_source(self):
        game = self._parse("fr")
        assert game.name == "HP Test"
        assert game.tags == ("Aventure", "Énigmes")
        assert game.versions[0].changes == ("Version originale du jeu",)

    def test_anglais_resolu_au_parsing(self):
        game = self._parse("en")
        assert game.name == "HP Test EN"
        assert game.description == "Test game EN"
        assert game.tags == ("Adventure", "Puzzles")
        assert game.versions[0].changes == ("Original game release",)

    def test_langue_absente_retombe_sur_le_francais(self):
        """L'espagnol n'est pas fourni pour ce jeu : le français doit rester."""
        game = self._parse("es")
        assert game.name == "HP Test"
        assert game.tags == ("Aventure", "Énigmes")

    def test_repli_par_champ(self):
        """Un bloc partiel (nom traduit, tags non) reste utilisable tel quel."""
        data = {**MINIMAL_GAME, "tags": ["Aventure"],
                "i18n": {"en": {"name": "Partial EN"}}}
        set_language("en")
        try:
            game = GameData.from_dict(data)
        finally:
            set_language("fr")
        assert game.name == "Partial EN"
        assert game.tags == ("Aventure",), "le champ non traduit garde le français"

    def test_bloc_i18n_mal_type_est_ignore(self):
        """Un catalogue distant trafiqué ne doit pas changer le TYPE d'un champ.

        `tags` doit rester une liste : une chaîne ici ferait exploser le
        `tuple()` en caractères isolés, et l'InfoPanel afficherait 8 pastilles.
        """
        data = {**MINIMAL_GAME, "tags": ["Aventure"],
                "i18n": {"en": {"name": 42, "tags": "Adventure"}}}
        set_language("en")
        try:
            game = GameData.from_dict(data)
        finally:
            set_language("fr")
        assert game.name == "HP Test"
        assert game.tags == ("Aventure",)

    def test_i18n_non_dict_est_ignore(self):
        data = {**MINIMAL_GAME, "i18n": "n'importe quoi"}
        set_language("en")
        try:
            game = GameData.from_dict(data)
        finally:
            set_language("fr")
        assert game.name == "HP Test"


class TestAvertissementDuCatalogue:
    """Champs `warning` / `warning_url` : une mise en garde par jeu.

    Le texte voyage DANS le catalogue (donc traduisible par son bloc `i18n` et
    modifiable à distance, sans republier l'exécutable). L'URL, elle, est la
    seule chaîne du catalogue qui finisse dans le navigateur de l'utilisateur :
    elle est filtrée au parsing, et un refus dégrade le lien sans emporter
    l'avertissement lui-même.
    """

    def test_absent_par_defaut(self):
        game = GameData.from_dict(MINIMAL_GAME)
        assert game.warning == ""
        assert game.warning_url == ""

    def test_texte_conserve(self):
        game = GameData.from_dict({**MINIMAL_GAME, "warning": "Une DLL est mise en quarantaine."})
        assert game.warning == "Une DLL est mise en quarantaine."

    def test_texte_traduit_par_le_bloc_i18n(self):
        data = {**MINIMAL_GAME,
                "warning": "Une DLL est mise en quarantaine.",
                "i18n": {"en": {"warning": "A DLL gets quarantined."}}}
        set_language("en")
        try:
            game = GameData.from_dict(data)
        finally:
            set_language("fr")
        assert game.warning == "A DLL gets quarantined."

    def test_url_https_acceptee(self):
        game = GameData.from_dict({**MINIMAL_GAME, "warning_url": "https://acciolauncher.be/aide"})
        assert game.warning_url == "https://acciolauncher.be/aide"

    @pytest.mark.parametrize("url", [
        "http://acciolauncher.be/aide",      # clair
        "javascript:alert(1)",               # exécution
        "file:///C:/Windows/System32",       # disque local
        "HTTPS:/acciolauncher.be",           # https mal formé
        "https://",                          # vide derrière le schéma
        "   ",                               # blancs
        123,                                 # pas une chaîne
        None,
    ])
    def test_url_refusee(self, url):
        game = GameData.from_dict({**MINIMAL_GAME, "warning_url": url})
        assert game.warning_url == ""

    def test_une_url_refusee_n_emporte_pas_l_avertissement(self):
        """Le message est l'information ; le lien n'est qu'un confort."""
        game = GameData.from_dict({**MINIMAL_GAME,
                                   "warning": "Une DLL est mise en quarantaine.",
                                   "warning_url": "javascript:alert(1)"})
        assert game.warning == "Une DLL est mise en quarantaine."
        assert game.warning_url == ""

    def test_un_bloc_i18n_ne_peut_pas_changer_le_type(self):
        data = {**MINIMAL_GAME, "warning": "texte", "i18n": {"en": {"warning": ["liste"]}}}
        set_language("en")
        try:
            game = GameData.from_dict(data)
        finally:
            set_language("fr")
        assert game.warning == "texte"


class TestBlocDeLangue:
    """`language_registry` : TOUT ou RIEN.

    Une déclaration à moitié valide est rejetée en entier plutôt que d'écrire
    la moitié des valeurs dans le registre d'un utilisateur. Le catalogue se met
    à jour à distance : il n'a pas droit à l'à-peu-près ici.
    """

    _BS = chr(92)
    _CLE = chr(92).join(["SOFTWARE", "Electronic Arts", "Jeu"])

    def _bloc(self, **surcharges):
        base = {
            "root": "HKLM", "view": 32, "key": self._CLE,
            "languages": {
                "fr": {"label": "Français",
                       "values": {"Language": "French", "Locale": "fr_FR"}},
                "en": {"label": "English",
                       "values": {"Language": "English", "Num": 3}},
            },
        }
        base.update(surcharges)
        return GameData.from_dict({**MINIMAL_GAME, "language_registry": base})

    def test_absent_par_defaut(self):
        assert GameData.from_dict(MINIMAL_GAME).language_registry is None

    def test_lecture_complete(self):
        lr = self._bloc().language_registry
        assert lr is not None
        assert (lr.root, lr.view, lr.key) == ("HKLM", 32, self._CLE)
        assert lr.codes == ("fr", "en")
        assert lr.get("fr").label == "Français"
        assert lr.get("fr").as_dict == {"Language": "French", "Locale": "fr_FR"}
        assert lr.get("en").as_dict == {"Language": "English", "Num": 3}
        assert lr.get("ja") is None

    def test_ordre_du_catalogue_preserve(self):
        """C'est l'ordre du sélecteur : il appartient au catalogue, pas au tri
        alphabétique de Python."""
        assert self._bloc().language_registry.codes == ("fr", "en")

    def test_cle_dangereuse_rejette_tout_le_bloc(self):
        cle = self._BS.join(["Software", "Microsoft", "Windows",
                             "CurrentVersion", "Run"])
        assert self._bloc(key=cle).language_registry is None

    def test_ruche_inconnue_rejetee(self):
        assert self._bloc(root="HKCR").language_registry is None

    @pytest.mark.parametrize("vue", [16, 0, "trente-deux", None])
    def test_vue_invalide_rejetee(self, vue):
        assert self._bloc(view=vue).language_registry is None

    def test_une_seule_valeur_interdite_rejette_tout_le_bloc(self):
        """Le français resterait valide : on le jette quand même, sinon le
        sélecteur proposerait une langue sur deux sans rien dire."""
        langues = {
            "fr": {"values": {"Language": "French"}},
            "en": {"values": {"AppInit_DLLs": "x.dll"}},
        }
        assert self._bloc(languages=langues).language_registry is None

    @pytest.mark.parametrize("langues", [
        {},                                       # vide
        {"fr": {}},                               # pas de values
        {"fr": {"values": {}}},                   # values vide
        {"fr": {"values": "French"}},             # values pas un dict
        {"fr": "French"},                         # entrée pas un dict
        "français",                               # pas un dict du tout
        None,
    ])
    def test_langues_invalides_rejetees(self, langues):
        assert self._bloc(languages=langues).language_registry is None

    def test_label_manquant_retombe_sur_le_code(self):
        langues = {"fr": {"values": {"Language": "French"}}}
        lr = self._bloc(languages=langues).language_registry
        assert lr.get("fr").label == "fr"

    def test_un_bloc_absent_ou_mal_type_ne_leve_pas(self):
        for valeur in (None, "oui", 42, []):
            g = GameData.from_dict({**MINIMAL_GAME, "language_registry": valeur})
            assert g.language_registry is None

    def test_le_jeu_reste_utilisable_si_le_bloc_est_rejete(self):
        """Un bloc douteux ne doit pas faire disparaître le jeu du catalogue."""
        g = self._bloc(root="HKCR")
        assert g.id == MINIMAL_GAME["id"]
        assert g.language_registry is None
