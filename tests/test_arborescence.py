"""Le dossier utilisateur ne melange plus les jeux et la plomberie.

Avant le 2026-08-26, `~/Games/AccioLauncher` contenait cote a cote les dossiers
de jeux (HP2, HP7, HP8...) et `.cache`, `trailers`, `accio_launcher.log`,
`catalog_cache.json`, `config.json`. Quelqu'un qui ouvre ce dossier veut y voir
ses JEUX ; le reste invite surtout a etre supprime au hasard.

La migration doit etre SANS RISQUE : elle tourne a chaque demarrage, chez des
gens qui ont deja des jeux installes, et une erreur y coute une reinstallation
de plusieurs gigaoctets.
"""

import json

from src.core.config import (
    LAUNCHER_DIR_NAME, cache_pour, migrer_arborescence,
)


def _ancienne_arborescence(racine):
    """Reproduit exactement ce que montrait l'explorateur de Ludo."""
    racine.mkdir(parents=True, exist_ok=True)
    for jeu in ("HP2", "HP7", "HP8"):
        (racine / jeu).mkdir()
        (racine / jeu / "jeu.exe").write_text("binaire", encoding="utf-8")
    (racine / ".cache").mkdir()
    (racine / ".cache" / "hp2_v1.0.7z.part").write_text("x" * 100, encoding="utf-8")
    (racine / "trailers").mkdir()
    (racine / "trailers" / "hp1_video_v1.0.mp4").write_text("video", encoding="utf-8")
    (racine / "i18n").mkdir()
    (racine / "i18n" / "de.json").write_text("{}", encoding="utf-8")
    (racine / "accio_launcher.log").write_text("journal", encoding="utf-8")
    (racine / "catalog_cache.json").write_text('{"catalog_version": "0.23"}',
                                               encoding="utf-8")
    (racine / "config.json").write_text(json.dumps({
        "install_path": str(racine),
        "cache_path": str(racine / ".cache"),
        "langue": "fr",
    }), encoding="utf-8")


class TestMigration:
    def test_range_tout_sauf_les_jeux(self, tmp_path):
        racine = tmp_path / "AccioLauncher"
        _ancienne_arborescence(racine)

        deplaces = migrer_arborescence(racine)
        assert deplaces, "rien n'a bouge alors que tout etait a l'ancien endroit"

        # Les JEUX n'ont pas bouge d'un pouce — c'est tout l'enjeu.
        for jeu in ("HP2", "HP7", "HP8"):
            assert (racine / jeu / "jeu.exe").read_text(encoding="utf-8") == "binaire"

        # A la racine il ne reste que les jeux et le dossier du launcher.
        restants = sorted(p.name for p in racine.iterdir())
        assert restants == ["HP2", "HP7", "HP8", LAUNCHER_DIR_NAME]

        donnees = racine / LAUNCHER_DIR_NAME
        assert (donnees / "config.json").exists()
        assert (donnees / "catalog_cache.json").exists()
        assert (donnees / "i18n" / "de.json").exists()
        assert (donnees / "trailers" / "hp1_video_v1.0.mp4").exists()
        assert (donnees / "logs" / "accio_launcher.log").exists()
        assert (donnees / "cache" / "hp2_v1.0.7z.part").exists()

    def test_le_cache_path_persiste_est_corrige(self, tmp_path):
        """Sans ca, le premier telechargement recreerait `.cache` a la racine
        et l'operation n'aurait servi a rien — le chemin est PERSISTE."""
        racine = tmp_path / "AccioLauncher"
        _ancienne_arborescence(racine)
        migrer_arborescence(racine)
        data = json.loads(
            (racine / LAUNCHER_DIR_NAME / "config.json").read_text(encoding="utf-8"))
        assert data["cache_path"] == str(cache_pour(racine))

    def test_idempotente(self, tmp_path):
        """Elle tourne a CHAQUE demarrage : le deuxieme passage ne fait rien."""
        racine = tmp_path / "AccioLauncher"
        _ancienne_arborescence(racine)
        migrer_arborescence(racine)
        assert migrer_arborescence(racine) == []
        assert (racine / LAUNCHER_DIR_NAME / "config.json").exists()

    def test_n_ecrase_jamais_ce_qui_existe_deja(self, tmp_path):
        """Un doublon a l'ancien endroit est moins grave qu'une perte.

        Cas reel possible : une version rangee a deja tourne, puis quelqu'un
        rejoue un vieil exe qui recree un `config.json` a la racine.
        """
        racine = tmp_path / "AccioLauncher"
        _ancienne_arborescence(racine)
        donnees = racine / LAUNCHER_DIR_NAME
        donnees.mkdir()
        (donnees / "config.json").write_text('{"langue": "es"}', encoding="utf-8")

        migrer_arborescence(racine)
        assert json.loads((donnees / "config.json").read_text(encoding="utf-8")) \
            == {"langue": "es"}
        assert (racine / "config.json").exists(), "l'ancien a ete detruit"

    def test_ne_fait_rien_sur_un_dossier_absent(self, tmp_path):
        assert migrer_arborescence(tmp_path / "jamais-cree") == []

    def test_une_installation_neuve_ne_declenche_rien(self, tmp_path):
        racine = tmp_path / "AccioLauncher"
        (racine / "HP1").mkdir(parents=True)
        assert migrer_arborescence(racine) == []


class TestChemins:
    def test_le_cache_suit_les_jeux(self, tmp_path):
        """Une archive de 7 Go doit atterrir sur le meme volume que son
        extraction : sinon le rangement final devient une COPIE, et la
        verification d'espace disque ment."""
        assert cache_pour(tmp_path).parent.parent == tmp_path

    def test_les_donnees_ne_suivent_pas_les_jeux(self):
        """Deplacer ses jeux ne doit pas rendre les journaux introuvables.

        `CONFIG_FILE_PATH` n'est pas verifie ici : `conftest.py` le redirige
        vers un dossier temporaire pour TOUS les tests, precisement pour qu'un
        test n'ecrive jamais dans la vraie configuration.
        """
        from src.core.config import (
            DEFAULT_INSTALL_PATH, LAUNCHER_DATA_PATH, LOG_DIR, USER_I18N_DIR,
        )
        from src.core.trailers import TRAILERS_DIR

        assert LAUNCHER_DATA_PATH == DEFAULT_INSTALL_PATH / LAUNCHER_DIR_NAME
        for chemin in (LOG_DIR, USER_I18N_DIR, TRAILERS_DIR):
            assert chemin.parent == LAUNCHER_DATA_PATH, chemin


class TestContributeurs:
    """Les remerciements vivent dans le CATALOGUE, donc a distance.

    Remercier quelqu'un ne doit pas attendre une release : une traduction
    rendue un mardi doit pouvoir etre creditee le mardi. Sinon la personne voit
    passer trois versions sans son nom, et n'en propose pas une deuxieme.
    """

    @staticmethod
    def _parse(brut):
        from src.core.game_data import _parse_contributors
        return _parse_contributors(brut)

    def test_nom_role_et_lien(self):
        (c,) = self._parse([{"name": "Ludovic", "role": "Creation",
                             "url": "https://github.com/ludvdber"}])
        assert (c.name, c.role, c.url) == ("Ludovic", "Creation",
                                           "https://github.com/ludvdber")

    def test_le_lien_est_facultatif(self):
        """Quelqu'un peut ne rien vouloir de public."""
        (c,) = self._parse([{"name": "Anon"}])
        assert c.url == "" and c.role == ""

    def test_seul_https_atteint_le_navigateur(self):
        """Meme regle que `warning_url` : c'est du catalogue DISTANT, et ca
        finit dans `QDesktopServices.openUrl`."""
        for mauvaise in ("javascript:alert(1)", "http://exemple.fr",
                         "file:///C:/Windows", 42):
            (c,) = self._parse([{"name": "X", "url": mauvaise}])
            assert c.url == "", mauvaise

    def test_une_entree_fautive_ne_perd_pas_les_autres(self):
        contribs = self._parse([
            "pas un dict", {"role": "sans nom"}, {"name": "   "},
            {"name": "Valide"},
        ])
        assert [c.name for c in contribs] == ["Valide"]

    def test_bloc_absent_ou_mal_type(self):
        assert self._parse(None) == ()
        assert self._parse({"name": "pas une liste"}) == ()

    def test_le_role_est_traduisible_par_le_catalogue(self):
        from src.core.i18n import set_language
        entree = {"name": "Ludovic", "role": "Creation",
                  "i18n": {"en": {"role": "Creator"}}}
        try:
            set_language("en")
            (c,) = self._parse([entree])
            assert c.role == "Creator"
        finally:
            set_language("fr")

    def test_le_catalogue_embarque_en_declare(self):
        """Sentinelle : si le bloc disparait, l'A propos redevient muet."""
        from src.core.game_data import load_catalog
        assert load_catalog().contributors, "plus aucun contributeur au catalogue"

    def test_le_balisage_d_un_nom_n_est_jamais_interprete(self, qtbot, tmp_path,
                                                          monkeypatch):
        """L'A propos est du RichText, et ces noms viennent du catalogue.

        Un `<img src="http://...">` dans un nom ferait partir une requete a
        l'ouverture des Parametres — donc « qui utilise le launcher » chez
        l'hebergeur de l'image.
        """
        import dataclasses

        from src.core.config import Config
        from src.core.game_data import Contributor
        from src.core.game_manager import GameManager
        from src.ui.settings_panel import SettingsDialog

        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "c.json")
        cfg = Config(install_path=tmp_path / "g", cache_path=tmp_path / "g" / "c")
        manager = GameManager(cfg)
        piege = Contributor(name='<img src="http://pisteur/x.png">', role="<b>x</b>")
        # `catalog` est une property en lecture seule : on remplace l'objet
        # qu'elle expose, pas la property.
        manager._catalog = dataclasses.replace(manager.catalog,
                                               contributors=(piege,))

        dlg = SettingsDialog(cfg, manager)
        qtbot.addWidget(dlg)
        from PyQt6.QtWidgets import QLabel
        rendu = "".join(lbl.text() for lbl in dlg.findChildren(QLabel))
        assert "<img" not in rendu
        assert "&lt;img" in rendu
