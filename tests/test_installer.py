"""Tests pour les helpers d'extraction (pas de QThread)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.core.extractors import (
    ArchiveRefusee,
    check_path_traversal,
    extract_7z,
    extract_zip,
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
    assert exe is not None, "7-Zip embarqué manquant dans assets/7z/"

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


def _zip(tmp_path, noms: list[str]):
    """Petite archive zip réelle (l'extracteur zip n'a pas besoin de 7-Zip)."""
    import zipfile
    archive = tmp_path / "archive.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for nom in noms:
            zf.writestr(nom, "contenu")
    return archive


@pytest.mark.skipif(find_7z_exe() is None, reason="7-Zip embarqué introuvable")
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


@pytest.mark.skipif(find_7z_exe() is None, reason="7-Zip embarqué introuvable")
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
            "src.core.extractors._sortie_slt",
            lambda _archive, _exe: "Path = Game/data.txt\nPath = ../../evil.dll\n",
        )
        with pytest.raises(ValueError, match="Archive refusée"):
            extract_7z(archive, dest, lambda _: None, lambda: False)
        assert not (dest / "Game").exists(), "rien ne doit être extrait"


def _archive_7z(tmp_path, racine: Path, *noms: str, liens: bool = False) -> Path:
    """Archive 7z réelle des `noms` (relatifs à `racine`) ; `-snl` garde les liens."""
    archive = tmp_path / "essai.7z"
    cmd = [find_7z_exe(), "a", str(archive), *noms, *(["-snl"] if liens else [])]
    subprocess.run(cmd, cwd=str(racine), capture_output=True, check=True, timeout=60)
    return archive


@pytest.mark.skipif(find_7z_exe() is None, reason="7-Zip embarqué introuvable")
class TestExtractionConfineeAuDossierDuJeu:
    """La destination est le dossier des JEUX : `_Launcher/`, les autres jeux,
    le préfixe Wine. Une archive ne doit écrire QUE dans le dossier de son
    jeu, sans chemin absolu, sans `..`, sans lien (audit du 2026-10-29)."""

    def test_une_entree_hors_du_dossier_du_jeu_est_refusee(self, tmp_path):
        src = tmp_path / "src"
        (src / "HP1").mkdir(parents=True)
        (src / "HP1" / "a.txt").write_text("x", encoding="utf-8")
        (src / "_Launcher").mkdir()
        (src / "_Launcher" / "config.json").write_text("{}", encoding="utf-8")
        archive = _archive_7z(tmp_path, src, "HP1", "_Launcher")
        dest = tmp_path / "jeux"
        dest.mkdir()
        with pytest.raises(ArchiveRefusee):
            extract_7z(archive, dest, lambda _: None, lambda: False, "HP1")
        assert not (dest / "_Launcher").exists()
        assert not (dest / "HP1").exists(), "rien ne doit être extrait"

    def test_le_dossier_du_jeu_se_compare_sans_la_casse(self, tmp_path):
        src = tmp_path / "src"
        (src / "hp1").mkdir(parents=True)
        (src / "hp1" / "a.txt").write_text("x", encoding="utf-8")
        dest = tmp_path / "jeux"
        dest.mkdir()
        extract_7z(_archive_7z(tmp_path, src, "hp1"), dest, lambda _: None, lambda: False, "HP1")
        assert (dest / "hp1" / "a.txt").is_file()

    @pytest.mark.skipif(sys.platform == "win32", reason="lien symbolique : privilège sous Windows")
    def test_un_lien_dans_l_archive_est_refuse(self, tmp_path):
        src = tmp_path / "src"
        (src / "HP1").mkdir(parents=True)
        (src / "HP1" / "evasion").symlink_to(tmp_path / "ailleurs")
        archive = _archive_7z(tmp_path, src, "HP1", liens=True)
        dest = tmp_path / "jeux"
        dest.mkdir()
        with pytest.raises(ArchiveRefusee):
            extract_7z(archive, dest, lambda _: None, lambda: False, "HP1")
        assert not (dest / "HP1").exists()

    @pytest.mark.skipif(sys.platform == "win32", reason="lien symbolique : privilège sous Windows")
    def test_un_lien_deja_present_qui_sort_est_refuse(self, tmp_path):
        """Une réparation extrait PAR-DESSUS : 7-Zip écrit à travers un lien
        existant, donc hors du dossier du jeu."""
        ailleurs = tmp_path / "ailleurs"
        ailleurs.mkdir()
        dest = tmp_path / "jeux"
        (dest / "HP1").mkdir(parents=True)
        (dest / "HP1" / "System").symlink_to(ailleurs, target_is_directory=True)
        src = tmp_path / "src"
        (src / "HP1" / "System").mkdir(parents=True)
        (src / "HP1" / "System" / "Core.dll").write_text("x", encoding="utf-8")
        with pytest.raises(ArchiveRefusee):
            extract_7z(_archive_7z(tmp_path, src, "HP1"), dest,
                       lambda _: None, lambda: False, "HP1")
        assert not (ailleurs / "Core.dll").exists()

    def test_zip_hors_du_dossier_du_jeu_refuse(self, tmp_path):
        dest = tmp_path / "jeux"
        dest.mkdir()
        with pytest.raises(ArchiveRefusee):
            extract_zip(_zip(tmp_path, ["HP1/a.txt", "_Launcher/config.json"]), dest,
                        lambda _: None, lambda: False, "HP1")
        assert not (dest / "_Launcher").exists()

    def test_zip_avec_lien_refuse(self, tmp_path):
        import zipfile
        archive = tmp_path / "lien.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            info = zipfile.ZipInfo("HP1/evasion")
            info.external_attr = (0o120777 << 16)
            zf.writestr(info, "/etc")
        dest = tmp_path / "jeux"
        dest.mkdir()
        with pytest.raises(ArchiveRefusee):
            extract_zip(archive, dest, lambda _: None, lambda: False, "HP1")

    def test_l_installeur_passe_son_dossier_de_jeu(self, tmp_path):
        from src.core.installer import Installer
        dest = tmp_path / "jeux"
        inst = Installer(_zip(tmp_path, ["HP1/a.txt", "HP2/b.txt"]), dest, game_dir="HP1")
        erreurs = []
        inst.error.connect(erreurs.append)
        inst.run()
        assert erreurs, "l'installeur doit refuser une archive qui écrit dans HP2"
        assert not (dest / "HP2").exists()


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

    # Ces deux tests RECOPIAIENT le calcul de `run()` au lieu de l'appeler : ils
    # restaient verts quoi qu'on fasse de `run()` (audit du 2026-10-07, ACT-010).
    # Ils passent maintenant par une vraie extraction.

    def test_premiere_installation(self, tmp_path):
        dest = tmp_path / "jeux"
        inst = self._installer(_zip(tmp_path, ["HP1/System/Core.dll"]), dest)
        inst.run()
        assert inst._created_dirs == [dest / "HP1"]
        assert inst._extracted_dirs == [dest / "HP1"]

    def test_le_dossier_du_jeu_est_debloque_meme_s_il_preexiste(self, tmp_path):
        """Le cœur du correctif : ce qu'on DÉBLOQUE et ce qu'on peut SUPPRIMER
        sont deux questions différentes."""
        dest = tmp_path / "jeux"
        (dest / "HP1" / "System").mkdir(parents=True)
        inst = self._installer(_zip(tmp_path, ["HP1/System/Core.dll"]), dest)
        inst.run()
        assert inst._created_dirs == [], "aucun dossier n'a été créé"
        assert inst._extracted_dirs == [dest / "HP1"], (
            "le dossier du jeu doit être débloqué même s'il préexistait")

    def test_annuler_une_reparation_ne_supprime_que_ce_que_l_extraction_a_cree(self, tmp_path):
        """M-01 : vraie archive, annulation posée depuis la progression. Le jeu
        déjà installé reste intact, le dossier neuf de l'archive disparaît."""
        dest = tmp_path / "jeux"
        jeu = dest / "HP1" / "System"
        jeu.mkdir(parents=True)
        (jeu / "Game.exe").write_text("precieux")
        # « Extras » en tête : l'annulation tombe après la première entrée.
        archive = _zip(tmp_path, ["Extras/lisez-moi.txt", "HP1/System/Core.dll"])
        inst = self._installer(archive, dest)
        inst.progress.connect(lambda _pct: inst.cancel())
        fins = []
        inst.install_finished.connect(fins.append)

        inst.run()

        assert (jeu / "Game.exe").read_text() == "precieux"
        assert not (dest / "Extras").exists(), "le dossier créé par l'extraction devait partir"
        assert fins == [], "une installation annulée ne doit pas s'annoncer finie"

    def test_le_nettoyage_refuse_le_dossier_racine_d_installation(self, tmp_path, caplog):
        """M-02 : même si la liste des dossiers créés venait à contenir la racine."""
        dest = tmp_path / "jeux"
        dest.mkdir()
        (dest / "HP2").mkdir()
        inst = self._installer(tmp_path / "a.7z", dest)
        inst._created_dirs = [dest]
        with caplog.at_level("CRITICAL", logger="src.core.installer"):
            inst._cleanup()
        assert (dest / "HP2").is_dir()
        assert any("REFUS" in r.getMessage() for r in caplog.records)

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


class TestSuppressionDeLArchive:
    """M-03 : « supprimer les archives après installation » sur un multi-volumes."""

    @staticmethod
    def _parts(dossier, nom, n):
        for i in range(1, n + 1):
            (dossier / f"{nom}.{i:03d}").write_bytes(b"x")

    def test_toutes_les_parts_sont_supprimees_et_elles_seules(self, tmp_path):
        from src.core.installer import supprimer_archive
        self._parts(tmp_path, "hp1_v1.3.7z", 3)
        self._parts(tmp_path, "hp2_v1.2.7z", 1)
        supprimer_archive(tmp_path / "hp1_v1.3.7z.001")
        assert sorted(p.name for p in tmp_path.iterdir()) == ["hp2_v1.2.7z.001"]

    def test_une_part_verrouillee_ne_fait_pas_echouer(self, tmp_path, monkeypatch, caplog):
        from pathlib import Path

        from src.core.installer import supprimer_archive
        self._parts(tmp_path, "hp1_v1.3.7z", 3)
        vrai_unlink = Path.unlink

        def unlink(self, missing_ok=False):
            if self.name.endswith(".002"):
                raise PermissionError(32, "fichier utilisé par un autre processus")
            return vrai_unlink(self, missing_ok=missing_ok)
        monkeypatch.setattr(Path, "unlink", unlink)

        with caplog.at_level("WARNING", logger="src.core.installer"):
            supprimer_archive(tmp_path / "hp1_v1.3.7z.001")

        assert sorted(p.name for p in tmp_path.iterdir()) == ["hp1_v1.3.7z.002"]
        assert any("verrouillé" in r.getMessage() for r in caplog.records)

    def test_l_installeur_supprime_apres_une_vraie_installation(self, tmp_path):
        from src.core.installer import Installer
        archive = _zip(tmp_path, ["HP1/System/Core.dll"])
        inst = Installer(archive, tmp_path / "jeux", game_dir="HP1", delete_archive=True)
        inst.run()
        assert (tmp_path / "jeux" / "HP1" / "System" / "Core.dll").exists()
        assert not archive.exists()


class TestProgressionDu7ZipLinux:
    """Le 7-Zip officiel pour Linux recule avec des `\\b` au lieu de passer à la
    ligne : lu ligne à ligne, toute l'extraction était UNE ligne, et la barre
    restait à 0 % jusqu'au bout."""

    # Relevé sur 7zzs 26.00 (2026-09-24), extraction avec -bsp1 dans un tube.
    RELEVE = (b"\n  0%\x08\x08\x08\x08    \x08\x08\x08\x08 29% 1 - src/f1.bin"
              b"\x08\x08\x08\x08\x08\x08\x08\x08\x08\x08\x08\x08\x08\x08\x08\x08\x08\x08\x08"
              b"                   \x08\x08\x08 59% 2 - src/f2.bin\x08\x08\rEverything is Ok\n")

    def test_decoupage_aux_retours_arriere(self):
        from src.core.extractors import _segments_de_progression
        lecture, ecriture = os.pipe()
        os.write(ecriture, self.RELEVE)
        os.close(ecriture)
        with os.fdopen(lecture, "rb") as flux:
            segments = [s.strip() for s in _segments_de_progression(flux)]
        assert "29% 1 - src/f1.bin" in segments
        assert "59% 2 - src/f2.bin" in segments
        assert segments[-1] == "Everything is Ok"

    @pytest.mark.skipif(sys.platform == "win32", reason="7-Zip pour Linux, lu par descripteur")
    def test_le_releve_passe_par_le_vrai_chemin(self, tmp_path, monkeypatch):
        """Le RELEVÉ rejoué par un faux 7-Zip, à travers `extract_7z` lui-même :
        `Popen`, lecture du descripteur, analyse. Lu ligne à ligne, ce flux ne
        donnait QUE le 100 % final.

        Pourquoi un faux et pas le vrai 7zzs : 7-Zip ne publie un pourcentage
        qu'environ toutes les 200 ms (mesuré : 39 valeurs en 8 s). Une vraie
        extraction assez courte pour un test finit parfois AVANT le premier —
        la version précédente de ce test échouait une fois sur quelques-unes
        sous charge, ce qui la rendait pire qu'une absence de test."""
        from src.core import extractors
        faux = tmp_path / "7zz"
        faux.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = l ]; then printf "Path = Game/f1.bin\\n"; exit 0; fi\n'
            "printf '\\n  0%%\\b\\b\\b\\b    \\b\\b\\b\\b 29%% 1 - Game/f1.bin'\n"
            "sleep 0.2\n"
            "printf '\\b\\b\\b\\b\\b\\b\\b\\b\\b\\b\\b\\b\\b\\b\\b\\b\\b\\b\\b"
            "                   \\b\\b\\b 59%% 2 - Game/f2.bin\\b\\b'\n"
            "sleep 0.2\n"
            "printf '\\rEverything is Ok\\n'\n",
            encoding="utf-8")
        faux.chmod(0o755)
        monkeypatch.setattr(extractors, "find_7z_exe", lambda: str(faux))
        valeurs: list[int] = []
        extract_7z(tmp_path / "a.7z", tmp_path, valeurs.append, lambda: False)
        assert valeurs == [29, 59, 100]

    @pytest.mark.skipif(sys.platform == "win32" or find_7z_exe() is None,
                        reason="7-Zip officiel pour Linux")
    def test_une_vraie_extraction(self, tmp_path):
        """Le 7-Zip EMBARQUÉ accepte nos options (`-bsp1`, `-snl-`, la liste
        `-slt` de la vérification) et rend les fichiers intacts. La
        progression intermédiaire est prouvée ci-dessus, pas ici."""
        src = tmp_path / "src" / "Game"
        src.mkdir(parents=True)
        for i in range(2):
            (src / f"f{i}.bin").write_bytes(os.urandom(1_000_000))
        archive = tmp_path / "a.7z"
        subprocess.run([find_7z_exe(), "a", "-mx1", str(archive), "Game"],
                       cwd=str(tmp_path / "src"), capture_output=True, check=True, timeout=120)
        valeurs: list[int] = []
        dest = tmp_path / "out"
        dest.mkdir()
        extract_7z(archive, dest, valeurs.append, lambda: False)
        assert (dest / "Game" / "f1.bin").read_bytes() == (src / "f1.bin").read_bytes()
        assert valeurs[-1] == 100


class TestUneVraieArchiveAbimee:
    """Audit du 2026-10-29 : le code d'échec de 7-Zip n'était exercé qu'à
    travers des faux. Une vraie archive dont 100 octets sont altérés doit
    lever `ExtractionEchouee` avec la sortie de 7-Zip, que `echecs` lit pour
    dire « archive abîmée »."""

    @pytest.mark.skipif(sys.platform == "win32" or find_7z_exe() is None,
                        reason="7-Zip officiel pour Linux")
    def test_le_code_d_echec_remonte_avec_sa_sortie(self, tmp_path):
        from src.core import echecs
        from src.core.extractors import ExtractionEchouee
        src = tmp_path / "src" / "Game"
        src.mkdir(parents=True)
        (src / "f.bin").write_bytes(os.urandom(300_000))
        archive = tmp_path / "a.7z"
        subprocess.run([find_7z_exe(), "a", "-mx1", str(archive), "Game"],
                       cwd=str(tmp_path / "src"), capture_output=True, check=True, timeout=120)
        brut = bytearray(archive.read_bytes())
        milieu = len(brut) // 2
        brut[milieu:milieu + 100] = bytes(100)
        archive.write_bytes(bytes(brut))
        dest = tmp_path / "out"
        dest.mkdir()
        with pytest.raises(ExtractionEchouee) as exc:
            extract_7z(archive, dest, lambda _v: None, lambda: False)
        assert exc.value.sortie, "la sortie de 7-Zip est gardée pour la boîte d'échec"
        assert echecs.cause_installation(exc.value, 10 ** 12) == "archive"


class TestVerificationApresExtraction:
    """La destination est le dossier des jeux : il contient aussi `_Launcher/`,
    et sous Linux le préfixe Wine, dont `dosdevices/z:` pointe LÉGITIMEMENT
    vers `/`. Tout parcourir refusait toute installation une fois Wine préparé
    (HP2 sur Bazzite, 2026-09-30)."""

    def test_premiers_niveaux(self):
        from src.core.extractors import premiers_niveaux
        assert premiers_niveaux(["HP2/system/Game.exe", "HP2", "HP2\\Maps\\a.unr",
                                 "lisez-moi.txt", "./x", ""]) == {"HP2", "lisez-moi.txt", "x"}

    @pytest.mark.skipif(sys.platform == "win32", reason="liens symboliques POSIX")
    def test_le_prefixe_wine_voisin_n_est_pas_une_evasion(self, tmp_path):
        from src.core.extractors import verify_extracted_paths
        dosdevices = tmp_path / "_Launcher" / "prefixes" / "umu" / "dosdevices"
        dosdevices.mkdir(parents=True)
        (dosdevices / "z:").symlink_to("/")
        (tmp_path / "HP2" / "system").mkdir(parents=True)
        verify_extracted_paths(tmp_path, {"HP2"})               # ne lève pas
        with pytest.raises(ValueError):
            verify_extracted_paths(tmp_path)                    # l'ancien parcours

    @pytest.mark.skipif(sys.platform == "win32", reason="liens symboliques POSIX")
    def test_un_lien_hors_destination_dans_le_jeu_reste_refuse(self, tmp_path):
        from src.core.extractors import verify_extracted_paths
        (tmp_path / "HP2" / "system").mkdir(parents=True)
        (tmp_path / "HP2" / "system" / "evasion").symlink_to("/etc")
        with pytest.raises(ValueError):
            verify_extracted_paths(tmp_path, {"HP2"})

    @pytest.mark.skipif(sys.platform == "win32", reason="liens symboliques POSIX")
    def test_un_premier_niveau_qui_est_lui_meme_un_lien(self, tmp_path):
        from src.core.extractors import verify_extracted_paths
        (tmp_path / "HP2").symlink_to("/etc")
        with pytest.raises(ValueError):
            verify_extracted_paths(tmp_path, {"HP2"})
