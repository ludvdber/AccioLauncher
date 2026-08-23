"""Tests pour src/core/post_install.py — validation des destinations de config (pur)."""

from pathlib import Path

from src.core.post_install import (
    _FORBIDDEN_DEST_SUFFIXES,
    allowed_config_roots,
    config_dest_error,
    ranger_dans_sous_dossier,
)


def _roots(tmp_path: Path) -> list[Path]:
    return [tmp_path / "Documents", tmp_path / "Saved Games"]


class TestConfigDestError:
    def test_documents_accepte(self, tmp_path):
        dest = tmp_path / "Documents" / "Harry Potter" / "HP.ini"
        assert config_dest_error(dest, _roots(tmp_path)) is None

    def test_saved_games_accepte(self, tmp_path):
        dest = tmp_path / "Saved Games" / "HP3" / "save.dat"
        assert config_dest_error(dest, _roots(tmp_path)) is None

    def test_hors_racines_refuse(self, tmp_path):
        """Le home entier n'est PAS une destination valide — seulement Documents."""
        dest = tmp_path / "AppData" / "Roaming" / "quelquechose.ini"
        assert config_dest_error(dest, _roots(tmp_path)) is not None

    def test_dossier_demarrage_refuse(self, tmp_path):
        """Régression sécurité : le dossier Démarrage est sous le home mais hors
        Documents — un catalogue empoisonné ne doit pas pouvoir y déposer un fichier."""
        dest = (tmp_path / "AppData" / "Roaming" / "Microsoft" / "Windows"
                / "Start Menu" / "Programs" / "Startup" / "evil.bat")
        assert config_dest_error(dest, _roots(tmp_path)) is not None

    def test_traversal_depuis_documents_refuse(self, tmp_path):
        dest = tmp_path / "Documents" / ".." / "AppData" / "x.ini"
        assert config_dest_error(dest, _roots(tmp_path)) is not None

    def test_extension_executable_refusee(self, tmp_path):
        """Même DANS Documents, une extension exécutable est refusée."""
        for suffix in (".exe", ".bat", ".lnk", ".dll", ".ps1"):
            dest = tmp_path / "Documents" / "Harry Potter" / f"payload{suffix}"
            reason = config_dest_error(dest, _roots(tmp_path))
            assert reason is not None, f"{suffix} aurait dû être refusé"
            assert "exécutable" in reason

    def test_extension_insensible_a_la_casse(self, tmp_path):
        dest = tmp_path / "Documents" / "HP" / "payload.ExE"
        assert config_dest_error(dest, _roots(tmp_path)) is not None

    def test_ini_reste_accepte(self, tmp_path):
        dest = tmp_path / "Documents" / "HP" / "User.ini"
        assert config_dest_error(dest, _roots(tmp_path)) is None


class TestAllowedConfigRoots:
    def test_documents_en_premier(self):
        roots = allowed_config_roots()
        assert len(roots) == 2
        assert roots[0].name.lower() in ("documents", "mes documents")

    def test_home_nu_pas_dans_les_racines(self):
        """Le home lui-même ne doit jamais être une racine autorisée."""
        assert Path.home().resolve() not in [r.resolve() for r in allowed_config_roots()]


class TestForbiddenSuffixes:
    def test_couvre_les_vecteurs_classiques(self):
        for suffix in (".exe", ".bat", ".cmd", ".ps1", ".vbs", ".lnk", ".dll", ".reg"):
            assert suffix in _FORBIDDEN_DEST_SUFFIXES

    def test_ini_non_interdit(self):
        assert ".ini" not in _FORBIDDEN_DEST_SUFFIXES


class TestRangerDansSousDossier:
    """HP7 ne démarre QUE si ses fichiers sont dans un sous-dossier `pc`.

    Relevé dans `hp7.exe` / `hp8.exe` (la chaîne `Install Dir` est suivie de
    `pc`), puis vérifié en lançant le jeu : à plat il sort en 0,5 s avec le
    code 0, sans un mot, par le chemin « insérez le disque ». Le nom compte —
    `zz` échoue comme à plat. Les archives publiées posant les fichiers à plat,
    le launcher range après extraction plutôt que de republier 12 Go.
    """

    def _jeu(self, tmp_path, fichiers=("hp7.exe", "DH1_French.pck")):
        d = tmp_path / "HP7"
        d.mkdir()
        for f in fichiers:
            (d / f).write_bytes(b"x")
        return d

    def test_le_contenu_descend_dans_le_sous_dossier(self, tmp_path):
        d = self._jeu(tmp_path)
        assert ranger_dans_sous_dossier(d, "pc") == 2
        assert (d / "pc" / "hp7.exe").is_file()
        assert (d / "pc" / "DH1_French.pck").is_file()
        assert not (d / "hp7.exe").exists()

    def test_les_sous_dossiers_descendent_aussi(self, tmp_path):
        d = self._jeu(tmp_path, ())
        (d / "movies").mkdir()
        (d / "movies" / "intro.vp6").write_bytes(b"v")
        assert ranger_dans_sous_dossier(d, "pc") == 1
        assert (d / "pc" / "movies" / "intro.vp6").is_file()

    def test_idempotent(self, tmp_path):
        """Rejoué sans nouvelle extraction, il n'a plus rien à descendre."""
        d = self._jeu(tmp_path)
        ranger_dans_sous_dossier(d, "pc")
        assert ranger_dans_sous_dossier(d, "pc") == 0
        assert (d / "pc" / "hp7.exe").is_file()

    def test_reparation_ecrase_l_ancien(self, tmp_path):
        """Cas réel : l'archive vient de reposer un fichier À PLAT par-dessus
        une installation déjà rangée. Sans écrasement, le déplacement échoue et
        on garde l'ANCIEN en croyant l'avoir remplacé."""
        d = self._jeu(tmp_path, ("hp7.exe",))
        ranger_dans_sous_dossier(d, "pc")
        (d / "hp7.exe").write_bytes(b"NEUF")          # nouvelle extraction
        assert ranger_dans_sous_dossier(d, "pc") == 1
        assert (d / "pc" / "hp7.exe").read_bytes() == b"NEUF"
        assert not (d / "hp7.exe").exists()

    def test_reparation_ecrase_un_dossier(self, tmp_path):
        d = self._jeu(tmp_path, ())
        (d / "movies").mkdir()
        (d / "movies" / "vieux.vp6").write_bytes(b"v")
        ranger_dans_sous_dossier(d, "pc")
        (d / "movies").mkdir()
        (d / "movies" / "neuf.vp6").write_bytes(b"n")
        ranger_dans_sous_dossier(d, "pc")
        assert (d / "pc" / "movies" / "neuf.vp6").is_file()
        assert not (d / "pc" / "movies" / "vieux.vp6").exists()

    def test_sans_nom_on_ne_touche_a_rien(self, tmp_path):
        """Les sept autres jeux n'ont pas ce champ : rien ne doit bouger."""
        d = self._jeu(tmp_path)
        assert ranger_dans_sous_dossier(d, "") == 0
        assert (d / "hp7.exe").is_file()
        assert not (d / "pc").exists()

    def test_dossier_absent_ne_leve_pas(self, tmp_path):
        assert ranger_dans_sous_dossier(tmp_path / "nexistepas", "pc") == 0
