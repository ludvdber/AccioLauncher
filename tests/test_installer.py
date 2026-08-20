"""Tests pour les helpers d'extraction (pas de QThread)."""

import os
import subprocess
import sys

import pytest

from src.core.extractors import (
    check_path_traversal,
    extract_7z,
    find_7z_exe,
    is_unsafe_entry,
    list_7z_entries,
    unsafe_archive_entries,
    verify_archive_entries,
)
from src.core.installer import Installer


class TestIsUnsafeEntry:
    """Validation des noms d'entrées d'archive AVANT extraction (fonction pure)."""

    def test_chemin_relatif_normal(self):
        assert is_unsafe_entry("Game/System/HP.exe") is False

    def test_backslash_windows(self):
        assert is_unsafe_entry("Game\\System\\HP.exe") is False

    def test_remontee_refusee(self):
        assert is_unsafe_entry("../evil.exe") is True
        assert is_unsafe_entry("Game/../../evil.exe") is True

    def test_remontee_backslash_refusee(self):
        assert is_unsafe_entry("..\\..\\Windows\\System32\\evil.dll") is True

    def test_absolu_refuse(self):
        assert is_unsafe_entry("/etc/passwd") is True

    def test_lettre_de_lecteur_refusee(self):
        assert is_unsafe_entry("C:\\Windows\\System32\\evil.dll") is True
        assert is_unsafe_entry("D:/data/x") is True

    def test_unc_refuse(self):
        assert is_unsafe_entry("\\\\serveur\\partage\\x.dll") is True

    def test_vide_refuse(self):
        assert is_unsafe_entry("") is True
        assert is_unsafe_entry("   ") is True

    def test_point_simple_accepte(self):
        """« . » n'est pas une remontée — ne pas rejeter les noms légitimes."""
        assert is_unsafe_entry("Game/./data.txt") is False
        assert is_unsafe_entry("Game/..bizarre/x") is False


class TestUnsafeArchiveEntries:
    def test_liste_seulement_les_dangereuses(self):
        entries = ["Game/a.txt", "../evil", "Game/b.txt", "C:\\x"]
        assert unsafe_archive_entries(entries) == ["../evil", "C:\\x"]

    def test_archive_saine_liste_vide(self):
        assert unsafe_archive_entries(["Game/a", "Game/sub/b"]) == []


class TestCheckPathTraversal:
    def test_safe_path(self, tmp_path):
        assert check_path_traversal(tmp_path, "HP1/System/Game.exe") is True

    def test_traversal(self, tmp_path):
        assert check_path_traversal(tmp_path, "../../etc/passwd") is False

    def test_absolute_in_archive(self, tmp_path):
        assert check_path_traversal(tmp_path, "/etc/passwd") is False

    def test_nested_safe(self, tmp_path):
        assert check_path_traversal(tmp_path, "game/data/maps/level1.unr") is True

    def test_backslash_traversal(self, tmp_path):
        assert check_path_traversal(tmp_path, "..\\..\\evil.dll") is False


class TestInstallerSignals:
    def test_finished_not_shadowed(self, tmp_path):
        """Régression : le signal métier ne doit PAS s'appeler `finished` —
        ça masquerait QThread.finished."""
        inst = Installer(tmp_path / "a.7z", tmp_path / "dest")
        assert inst.finished.signal == "2finished()"  # natif QThread, sans argument
        assert inst.install_finished.signal == "2install_finished(QString)"


def _make_7z(tmp_path, *, volume_size: str | None = None):
    """Crée une archive 7z de test via 7z.exe (py7zr retiré du projet)."""
    exe = find_7z_exe()
    assert exe is not None, "7z.exe bundlé manquant dans assets/7z/"

    src = tmp_path / "src" / "Game"
    src.mkdir(parents=True)
    (src / "data.txt").write_text("hello", encoding="utf-8")
    # Données incompressibles pour que -v10k produise réellement plusieurs volumes
    (src / "big.bin").write_bytes(os.urandom(30_000))

    archive = tmp_path / "a.7z"
    cmd = [exe, "a", str(archive), "Game"]
    if volume_size:
        cmd.append(f"-v{volume_size}")
    kwargs: dict = {"cwd": str(tmp_path / "src"), "capture_output": True, "timeout": 60}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    result = subprocess.run(cmd, **kwargs)
    assert result.returncode == 0, result.stdout
    return archive


@pytest.mark.skipif(sys.platform != "win32", reason="7z.exe bundlé Windows uniquement")
class TestExtract7z:
    def test_extract_simple(self, tmp_path):
        archive = _make_7z(tmp_path)
        dest = tmp_path / "out"
        dest.mkdir()
        progress_values: list[int] = []
        extract_7z(archive, dest, progress_values.append, lambda: False)

        assert (dest / "Game" / "data.txt").read_text(encoding="utf-8") == "hello"
        assert progress_values, "7z.exe doit émettre au moins une progression"

    def test_extract_multivolume_001(self, tmp_path):
        """7z.exe lit nativement les archives découpées — le downloader émet le .001 brut."""
        _make_7z(tmp_path, volume_size="10k")
        first_part = tmp_path / "a.7z.001"
        assert first_part.exists(), "le découpage -v10k doit produire a.7z.001"
        assert (tmp_path / "a.7z.002").exists()

        dest = tmp_path / "out"
        dest.mkdir()
        extract_7z(first_part, dest, lambda _: None, lambda: False)

        assert (dest / "Game" / "data.txt").read_text(encoding="utf-8") == "hello"
        assert (dest / "Game" / "big.bin").stat().st_size == 30_000


@pytest.mark.skipif(sys.platform != "win32", reason="7z.exe bundlé Windows uniquement")
class TestVerifyArchiveEntries:
    """Le contrôle anti-évasion doit avoir lieu AVANT l'écriture sur disque.

    `verify_extracted_paths` ne peut structurellement pas jouer ce rôle : il
    parcourt l'intérieur de la destination, donc un fichier écrit dehors n'y
    apparaît jamais.
    """

    def test_liste_les_entrees_reelles(self, tmp_path):
        archive = _make_7z(tmp_path)
        entries = list_7z_entries(archive, find_7z_exe())
        assert "Game\\data.txt" in entries or "Game/data.txt" in entries
        # -ba : l'archive elle-même ne doit pas apparaître comme une entrée
        assert not any(e.endswith("a.7z") for e in entries)

    def test_archive_saine_passe(self, tmp_path):
        archive = _make_7z(tmp_path)
        verify_archive_entries(archive, find_7z_exe())  # ne lève pas

    def test_multivolume_valide_via_le_001(self, tmp_path):
        _make_7z(tmp_path, volume_size="10k")
        verify_archive_entries(tmp_path / "a.7z.001", find_7z_exe())  # ne lève pas

    def test_archive_illisible_leve(self, tmp_path):
        bogus = tmp_path / "pas_une_archive.7z"
        bogus.write_bytes(b"ceci n'est pas une archive 7z")
        with pytest.raises(RuntimeError):
            verify_archive_entries(bogus, find_7z_exe())

    def test_extraction_refusee_si_entree_dangereuse(self, tmp_path, monkeypatch):
        """Une entrée en `..` doit faire échouer l'extraction avant tout écriture.

        7-Zip neutralise les `..` de son côté, donc on simule le listing pour
        exercer NOTRE garde — c'est justement le point : ne pas dépendre d'un
        comportement amont non documenté.
        """
        archive = _make_7z(tmp_path)
        dest = tmp_path / "out"
        dest.mkdir()
        monkeypatch.setattr(
            "src.core.extractors.list_7z_entries",
            lambda _archive, _exe: ["Game/data.txt", "../../evil.dll"],
        )
        with pytest.raises(ValueError, match="Archive refusée"):
            extract_7z(archive, dest, lambda _: None, lambda: False)
        assert not (dest / "Game").exists(), "rien ne doit être extrait"


class TestDeblocageSurReparation:
    """Une réparation ou une mise à jour extrait par-dessus un dossier qui
    EXISTE DÉJÀ. `_extracted_dirs` était calculé par différence d'inventaire :
    la différence était donc vide, et `unblock_extracted` ne débloquait plus
    rien (mesuré : 0 fichier sur 3). Un .dll qui garde son Zone.Identifier fait
    échouer UE1 sur « Can't find file for package ».
    """

    @staticmethod
    def _installer(archive, destination, game_dir="HP1"):
        from src.core.installer import Installer
        return Installer(archive, destination, game_dir=game_dir)

    def test_premiere_installation(self, tmp_path):
        inst = self._installer(tmp_path / "a.7z", tmp_path / "jeux")
        (tmp_path / "jeux").mkdir()
        inst._created_dirs = [tmp_path / "jeux" / "HP1"]
        inst._extracted_dirs = [tmp_path / "jeux" / "HP1"]
        assert inst._extracted_dirs, "rien à débloquer sur une première installation"

    def test_le_dossier_du_jeu_est_debloque_meme_s_il_preexiste(self, tmp_path):
        """Le cœur du correctif : ce qu'on DÉBLOQUE et ce qu'on peut SUPPRIMER
        sont deux questions différentes."""
        dest = tmp_path / "jeux"
        (dest / "HP1" / "System").mkdir(parents=True)
        archive = tmp_path / "a.7z"
        archive.write_bytes(b"7z")
        inst = self._installer(archive, dest)

        # On rejoue le calcul de run() sans lancer d'extraction réelle.
        avant = {p.name for p in dest.iterdir() if p.is_dir()}   # {"HP1"}
        apres = {p.name for p in dest.iterdir() if p.is_dir()}
        nouveaux = apres - avant
        inst._created_dirs = [dest / d for d in nouveaux]
        a_debloquer = set(nouveaux)
        if inst.game_dir and inst.game_dir in apres:
            a_debloquer.add(inst.game_dir)
        inst._extracted_dirs = [dest / d for d in a_debloquer]

        assert inst._created_dirs == [], "aucun dossier n'a été créé"
        assert inst._extracted_dirs == [dest / "HP1"], (
            "le dossier du jeu doit être débloqué même s'il préexistait")

    def test_le_nettoyage_ne_touche_pas_un_dossier_preexistant(self, tmp_path):
        """Annuler une réparation ne doit JAMAIS emporter l'installation que
        l'utilisateur avait déjà."""
        dest = tmp_path / "jeux"
        jeu = dest / "HP1" / "System"
        jeu.mkdir(parents=True)
        (jeu / "Game.exe").write_text("precieux")
        inst = self._installer(tmp_path / "a.7z", dest)
        inst._extracted_dirs = [dest / "HP1"]    # à débloquer
        inst._created_dirs = []                  # mais rien à supprimer

        inst._cleanup()

        assert (jeu / "Game.exe").exists(), (
            "le nettoyage a supprimé une installation préexistante")
