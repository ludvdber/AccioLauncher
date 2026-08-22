"""Fuites win32 attrapées par le job `linux-smoke`, resté rouge depuis sa création.

Ce job tourne sur `ubuntu-latest` en `continue-on-error` : il ne bloque rien,
et personne ne le regardait. Il échouait à CHAQUE run depuis au moins le
2026-06-12. Reproduit le 2026-08-21 dans un conteneur Linux (`python:3.14-slim`
+ les bibliothèques Qt du workflow) : 4 échecs, 608 passés en 47 s, quand la CI
en met 45 — le même run.

Les quatre venaient de trois suppositions Windows :

1. `subprocess.CREATE_NEW_PROCESS_GROUP` n'existe QUE sous Windows, et il était
   nommé dans l'appel : `AttributeError` avant même d'atteindre `Popen`, donc y
   compris dans un test qui remplace `Popen`.
2. « \\ » n'est pas un séparateur sous POSIX. Le garde-fou anti-Zip-Slip laissait
   donc passer « ..\\..\\evil.dll », et les chemins du catalogue (écrits à la
   Windows) devenaient un seul nom de fichier, si bien qu'AUCUN patch INI ne
   s'appliquait.
3. `write_text` traduit le saut de ligne en `os.linesep` : CRLF sous Windows par
   coïncidence de plateforme, LF sous Linux. Le patcheur réécrivait donc tout le
   fichier du moteur, alors qu'il promet un aller-retour exact.

Les tests ci-dessous tournent sur LES DEUX plateformes — c'est tout l'intérêt :
un garde-fou qui ne s'arme que là où le défaut n'existe pas ne garde rien.
"""

import ast
import inspect
from pathlib import Path

import pytest

from src.core import pre_launch, self_update
from src.core.config import Config
from src.core.extractors import check_path_traversal
from src.core.game_data import GameData

_JEU = {
    "id": "hp1", "name": "HP1", "year": 2001, "developer": "KnowWonder",
    "description": "Le premier.",
    "executable": "HP1/System/HP.exe", "cover_image": "hp1.jpg",
    "versions": [], "pre_launch": {},
}


class TestZipSlipHorsWindows:
    """La normalisation doit précéder la vérification, pas dépendre de l'OS."""

    def test_une_remontee_en_antislash_est_refusee(self, tmp_path):
        assert check_path_traversal(tmp_path, r"..\..\evil.dll") is False

    def test_une_remontee_en_slash_reste_refusee(self, tmp_path):
        assert check_path_traversal(tmp_path, "../../evil.dll") is False

    def test_un_chemin_sage_reste_accepte(self, tmp_path):
        assert check_path_traversal(tmp_path, r"System\HP.exe") is True


class TestCheminsDuCatalogue:
    """Le catalogue écrit à la Windows et se met à jour à distance : on subit."""

    def test_les_separateurs_sont_normalises_hors_windows(self, tmp_path, monkeypatch):
        """`sys.platform` est simulé, sinon ce test ne s'armerait que sur la CI Linux."""
        monkeypatch.setattr(pre_launch.sys, "platform", "linux")
        monkeypatch.setattr(pre_launch, "get_documents_dir", lambda: tmp_path / "Documents")
        resolu = pre_launch.substitute_vars(
            r"%DOCUMENTS%\Harry Potter\HP.ini",
            GameData.from_dict(_JEU), Config(install_path=tmp_path / "jeux"))
        assert "Harry Potter/HP.ini" in resolu
        assert "\\" not in resolu.split("Documents", 1)[1]

    def test_windows_garde_ses_antislashs(self, tmp_path, monkeypatch):
        """La substitution ne doit rien toucher là où « \\ » est le séparateur."""
        monkeypatch.setattr(pre_launch.sys, "platform", "win32")
        monkeypatch.setattr(pre_launch, "get_documents_dir", lambda: tmp_path / "Documents")
        resolu = pre_launch.substitute_vars(
            r"%DOCUMENTS%\Harry Potter\HP.ini",
            GameData.from_dict(_JEU), Config(install_path=tmp_path / "jeux"))
        assert r"Harry Potter\HP.ini" in resolu


class TestFinsDeLigneDuMoteur:
    """Un .ini d'UE1 est en CRLF, sur toutes les plateformes."""

    def test_le_fichier_reste_en_crlf(self, tmp_path, monkeypatch):
        docs = tmp_path / "Documents" / "Harry Potter"
        docs.mkdir(parents=True)
        ini = docs / "HP.ini"
        ini.write_bytes(b"[FirstRun]\r\nReconfig=1\r\n")
        monkeypatch.setattr(pre_launch, "get_documents_dir",
                            lambda: (tmp_path / "Documents").resolve())

        jeu = dict(_JEU)
        jeu["pre_launch"] = {"ini_patches": [
            {"file": r"%DOCUMENTS%\Harry Potter\HP.ini",
             "section": "FirstRun", "key": "Reconfig", "value": "0"},
        ]}
        pre_launch.apply_ini_patches(GameData.from_dict(jeu),
                                     Config(install_path=tmp_path / "jeux"))

        octets = ini.read_bytes()
        assert b"Reconfig=0" in octets, "le patch ne s'est pas appliqué"
        assert octets.count(b"\r\n") == octets.count(b"\n"), (
            "un saut de ligne isolé : le fichier a été réécrit en LF, "
            "alors que le moteur l'a écrit en CRLF")


class TestConstantesWindows:
    """Un module doit rester IMPORTABLE et APPELABLE hors Windows."""

    def test_les_drapeaux_de_detachement_existent_partout(self):
        assert isinstance(self_update._DRAPEAUX_DETACHE, int)

    def test_aucune_constante_windows_dans_le_corps_de_la_fonction(self):
        """Elles ne doivent être touchées qu'une fois, sous garde, à l'import.

        Les nommer dans le corps rend la fonction intestable hors Windows :
        l'`AttributeError` tombe avant `Popen`, donc avant tout point où un
        test pourrait intervenir.
        """
        arbre = ast.parse(inspect.getsource(self_update._spawn_after_exit_bat))
        noms = {n.attr for n in ast.walk(arbre) if isinstance(n, ast.Attribute)}
        fautives = {n for n in noms if n.startswith("CREATE_")}
        assert not fautives, f"constantes Windows nommées dans le corps : {fautives}"


class TestWorkflowCI:
    """Le job Linux existe pour attraper ces fuites — encore faut-il qu'il tourne."""

    def test_le_smoke_linux_est_toujours_declare(self):
        workflow = Path(".github/workflows/tests.yml").read_text(encoding="utf-8")
        assert "linux-smoke:" in workflow
        assert "ubuntu-latest" in workflow


@pytest.mark.parametrize("nom", ["libegl1", "libgl1", "libxkbcommon0", "libdbus-1-3"])
def test_les_bibliotheques_qt_restent_installees_par_la_ci(nom):
    """Retirer l'une d'elles casse la collecte entière, pas un test isolé."""
    workflow = Path(".github/workflows/tests.yml").read_text(encoding="utf-8")
    assert nom in workflow


class TestRegistreHorsWindows:
    """`game_registry` touche a winreg et ctypes.windll : ni l'un ni l'autre
    n'existe sous Linux. Meme piege que les constantes `CREATE_*`."""

    def test_aucun_import_windows_au_niveau_module(self):
        """`import winreg` en tete de fichier casserait l'import sous Linux —
        et `game_data` importe `game_registry`, donc TOUT le catalogue."""
        from src.core import game_registry

        arbre = ast.parse(Path(game_registry.__file__).read_text(encoding="utf-8"))
        au_module = set()
        for noeud in arbre.body:            # NIVEAU MODULE uniquement
            if isinstance(noeud, ast.Import):
                au_module.update(a.name.split(".")[0] for a in noeud.names)
            elif isinstance(noeud, ast.ImportFrom) and noeud.module:
                au_module.add(noeud.module.split(".")[0])
        assert "winreg" not in au_module
        assert "ctypes" not in au_module

    def test_windll_reste_dans_la_branche_elevee(self):
        """`ctypes.windll` n'existe pas sous Linux : le nommer ailleurs que
        dans `_ecrire_eleve` rendrait la fonction appelante intestable."""
        from src.core import game_registry

        source = Path(game_registry.__file__).read_text(encoding="utf-8")
        arbre = ast.parse(source)
        fautifs = []
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.FunctionDef) or noeud.name == "_ecrire_eleve":
                continue
            for sous in ast.walk(noeud):
                if isinstance(sous, ast.Attribute) and sous.attr == "windll":
                    fautifs.append(noeud.name)
        assert not fautifs, "windll nomme hors de _ecrire_eleve : %s" % fautifs

    def test_le_module_s_importe_et_degrade(self, monkeypatch):
        from src.core import game_registry

        monkeypatch.setattr("sys.platform", "linux")
        cle = chr(92).join(["Software", "Editeur", "Jeu"])
        assert game_registry.lire_valeurs("HKLM", cle, ["A"]) == {}
        assert game_registry.ecrire_valeurs("HKLM", cle, {"A": "b"}) is False
        # Les fonctions PURES, elles, doivent marcher partout : ce sont elles
        # qui gardent le registre, et le catalogue est parse sur les deux OS.
        assert game_registry.refus_de_cle("HKLM", cle) is None
        assert "WOW6432Node" in game_registry.construire_reg("HKLM", cle, {"A": "b"})
