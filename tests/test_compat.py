"""La couche de compatibilité Linux (`src/core/compat.py`).

Tout ce qui est testé ici est PUR ou ne lit que des fichiers posés par le test :
aucun Wine n'est lancé, aucun `/proc` réel n'est consulté, et la détection du
lanceur reçoit un `which` factice — la suite ne doit pas dépendre de ce qui est
installé sur la machine qui la joue. Ces tests tournent donc aussi sous Windows.

Les échantillons de registre sont RELEVÉS sur un vrai préfixe Wine 9.0
(2026-09-24), pas inventés : c'est leur format exact qu'on doit savoir lire.
"""

import os
import sys
from pathlib import Path

import pytest

from src.core import compat
from src.core.compat import Lanceur

# `lanceur` d'origine, capturé à l'import : la garde de conftest le remplace
# pendant chaque test, et c'est la vraie fonction qu'on veut éprouver ici.
_LANCEUR_REEL = compat.lanceur

B = chr(92)


def _which(disponibles: dict):
    return lambda nom: disponibles.get(nom)


class TestDetection:
    def test_umu_passe_avant_wine(self):
        trouve = compat.detecter({}, _which({"umu-run": "/usr/bin/umu-run",
                                             "wine": "/usr/bin/wine"}),
                                 programmes=[], protons=[])
        assert trouve == Lanceur("umu", "/usr/bin/umu-run")

    def test_wine_ensuite_avec_son_winetricks(self):
        trouve = compat.detecter({}, _which({"wine": "/usr/bin/wine",
                                             "winetricks": "/usr/bin/winetricks"}),
                                 programmes=[], protons=[])
        assert trouve == Lanceur("wine", "/usr/bin/wine", winetricks="/usr/bin/winetricks")

    def test_wine64_seul_suffit(self):
        trouve = compat.detecter({}, _which({"wine64": "/usr/bin/wine64"}),
                                 programmes=[], protons=[])
        assert trouve.famille == "wine" and trouve.executable == "/usr/bin/wine64"
        assert trouve.winetricks == ""

    def test_rien_trouve(self):
        assert compat.detecter({}, _which({}), programmes=[], protons=[]) is None

    def test_accio_compat_force_une_famille(self):
        which = _which({"umu-run": "/usr/bin/umu-run", "wine": "/usr/bin/wine"})
        trouve = compat.detecter({"ACCIO_COMPAT": "wine"}, which, programmes=[], protons=[])
        assert trouve.famille == "wine"

    def test_forcer_une_famille_absente_ne_rabat_pas_sur_l_autre(self):
        """Le forçage sert au dépannage : retomber en silence sur umu ferait
        croire qu'on teste wine."""
        which = _which({"umu-run": "/usr/bin/umu-run"})
        assert compat.detecter({"ACCIO_COMPAT": "wine"}, which,
                               programmes=[], protons=[]) is None

    def test_jamais_le_nom_seul(self, tmp_path):
        """`which` peut rendre un chemin relatif si le PATH en contient un."""
        which = _which({"umu-run": "bin/umu-run"})
        assert os.path.isabs(compat.detecter({}, which, programmes=[], protons=[]).executable)

    def test_local_bin_hors_du_path(self, tmp_path):
        """Une session graphique n'a pas toujours `~/.local/bin` dans son PATH,
        et c'est là que s'installe l'archive « zipapp » d'umu."""
        umu = tmp_path / "umu-run"
        umu.write_text("#!/bin/sh\n", encoding="utf-8")
        umu.chmod(0o755)
        trouve = compat.detecter({}, _which({}), programmes=[tmp_path], protons=[])
        if sys.platform != "win32":      # le bit exécutable n'existe pas sous Windows
            assert trouve.executable == str(umu)

    def test_un_protonpath_de_l_utilisateur_est_respecte(self, tmp_path):
        _proton(tmp_path, "GE-Proton10-3")
        trouve = compat.detecter({"PROTONPATH": "/mon/proton"},
                                 _which({"umu-run": "/usr/bin/umu-run"}),
                                 programmes=[], protons=[tmp_path])
        assert trouve.proton == ""      # on ne le remplace pas : umu le lit lui-même


def _proton(dossier: Path, nom: str) -> Path:
    chemin = dossier / nom
    chemin.mkdir(parents=True)
    (chemin / "proton").write_text("", encoding="utf-8")
    return chemin


class TestChoixDeProton:
    def test_le_plus_recent_en_ordre_numerique(self, tmp_path):
        _proton(tmp_path, "GE-Proton9-27")
        attendu = _proton(tmp_path, "GE-Proton10-3")
        assert compat.proton_installe([tmp_path]) == str(attendu)

    def test_ge_avant_umu(self, tmp_path):
        _proton(tmp_path, "UMU-Proton-9.0-4e")
        attendu = _proton(tmp_path, "GE-Proton9-4")
        assert compat.proton_installe([tmp_path]) == str(attendu)

    def test_umu_proton_deja_telecharge(self, tmp_path):
        attendu = _proton(tmp_path, "UMU-Proton-9.0-4e")
        assert compat.proton_installe([tmp_path]) == str(attendu)

    def test_un_dossier_sans_script_proton_est_ignore(self, tmp_path):
        (tmp_path / "GE-Proton10-9").mkdir()
        assert compat.proton_installe([tmp_path]) == ""

    def test_dossiers_absents(self, tmp_path):
        assert compat.proton_installe([tmp_path / "rien"]) == ""


class TestLanceurDeLaMachine:
    def test_toujours_none_sous_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        _LANCEUR_REEL.cache_clear()
        try:
            assert _LANCEUR_REEL() is None
        finally:
            _LANCEUR_REEL.cache_clear()

    def test_oublier_ne_casse_pas_si_lanceur_est_remplace(self):
        compat.oublier()      # conftest a remplacé `lanceur` par un lambda


class TestPrefixe:
    def test_sous_launcher_et_par_famille(self, monkeypatch, tmp_path):
        monkeypatch.setattr(compat, "_donnees_launcher", lambda: tmp_path)
        assert compat.prefixe("umu") == tmp_path / "prefixes" / "umu"
        assert compat.prefixe("wine") == tmp_path / "prefixes" / "wine"

    def test_sans_lanceur_celui_d_umu(self, monkeypatch, tmp_path, sans_lanceur):
        """Un jeu installé avant umu dépose sa configuration là où umu la lira."""
        monkeypatch.setattr(compat, "_donnees_launcher", lambda: tmp_path)
        assert compat.prefixe().name == "umu"

    def test_la_garde_de_test_donne_un_prefixe_pret(self):
        assert compat.pret(compat.prefixe())

    def test_pret_exige_registre_et_drive_c(self, tmp_path):
        assert not compat.pret(tmp_path)
        (tmp_path / "drive_c").mkdir()
        assert not compat.pret(tmp_path)
        (tmp_path / "system.reg").write_text("", encoding="utf-8")
        assert compat.pret(tmp_path)


class TestProfil:
    def test_proton_range_sous_steamuser(self, tmp_path):
        pfx = tmp_path / "umu"
        assert compat.profil(pfx) == pfx / "drive_c" / "users" / "steamuser"
        assert compat.documents(pfx) == compat.profil(pfx) / "Documents"
        assert compat.appdata_local(pfx) == compat.profil(pfx) / "AppData" / "Local"

    def test_wine_reprend_le_profil_existant(self, tmp_path):
        """Le nom vient de la base des mots de passe : un `USER` différent ne
        doit pas faire chercher un dossier qui n'existe pas."""
        pfx = tmp_path / "wine"
        (pfx / "drive_c" / "users" / "Public").mkdir(parents=True)
        (pfx / "drive_c" / "users" / "frédéric").mkdir()
        assert compat.profil(pfx).name == "frédéric"

    def test_wine_sans_prefixe_prend_le_nom_unix(self, tmp_path, monkeypatch):
        monkeypatch.setattr(compat, "_nom_unix", lambda: "ludo")
        assert compat.profil(tmp_path / "wine").name == "ludo"

    def test_un_vieux_wine_et_son_appdata(self, tmp_path):
        pfx = tmp_path / "wine"
        ancien = pfx / "drive_c" / "users" / "ludo" / "Local Settings" / "Application Data"
        ancien.mkdir(parents=True)
        assert compat.appdata_local(pfx) == ancien


@pytest.mark.skipif(sys.platform == "win32", reason="chemins de l'hôte Linux")
class TestCheminWindows:
    def test_dans_drive_c(self, tmp_path):
        pfx = tmp_path / "umu"
        docs = pfx / "drive_c" / "users" / "steamuser" / "Documents" / "Harry Potter"
        assert compat.chemin_windows(docs, pfx) == (
            "C:" + B + B.join(["users", "steamuser", "Documents", "Harry Potter"]))

    def test_hors_du_prefixe_par_z(self, tmp_path):
        pfx = tmp_path / "umu"
        chemin = Path("/home/ludo/Games/AccioLauncher/HP7")
        assert compat.chemin_windows(chemin, pfx) == (
            "Z:" + B + B.join(["home", "ludo", "Games", "AccioLauncher", "HP7"]))

    def test_comparaison_lexicale_sans_suivre_les_liens(self, tmp_path):
        """Wine fait parfois de Documents un lien vers `~/Documents` : le jeu,
        lui, connaît `C:\\users\\…`, et c'est ça qu'il doit lire."""
        pfx = tmp_path / "wine"
        profil = pfx / "drive_c" / "users" / "ludo"
        profil.mkdir(parents=True)
        (tmp_path / "vrais-documents").mkdir()
        (profil / "Documents").symlink_to(tmp_path / "vrais-documents")
        assert compat.chemin_windows(profil / "Documents", pfx).startswith("C:" + B)


# Échantillon RELEVÉ dans le system.reg d'un préfixe Wine 9.0, après import par
# `regedit /S` d'un .reg construit par `construire_reg` (2026-09-24).
SYSTEM_REG = (
    "WINE REGISTRY Version 2\n"
    ";; All keys relative to \\\\Machine\n"
    "\n"
    "#arch=win64\n"
    "\n"
    "[Software\\\\Wow6432Node\\\\Electronic Arts\\\\Harry Potter and the Deathly "
    "Hallows Part 1] 1790275107\n"
    "#time=1dd4c53e357a546\n"
    '"Guillemet"="a\\"b"\n'
    '"Install Dir"="Z:\\\\home\\\\fr\\x00e9d\\xe9ric\\\\Games\\\\HP7\\\\"\n'
    '"Locale"="fr_FR"\n'
    '"Nombre"=dword:00000007\n'
    "\n"
    "[System\\\\CurrentControlSet\\\\Control\\\\Nls\\\\Codepage] 1790274555\n"
    '"1252"="c_1252.nls"\n'
    '"ACP"="1252"\n'
    "\n"
    "[Software\\\\Wow6432Node\\\\Microsoft\\\\VisualStudio\\\\14.0\\\\VC\\\\Runtimes\\\\x86]"
    " 1790275999\n"
    '"Installed"=dword:00000001\n'
    '"Version"="v14.40.33810.00"\n'
)
CLE_HP7 = "SOFTWARE" + B + "Electronic Arts" + B + "Harry Potter and the Deathly Hallows Part 1"


class TestLectureDuRegistreDeWine:
    def test_desechapper_les_accents_de_wine(self):
        """`\\x00e9` quand le caractère suivant pourrait passer pour un chiffre,
        `\\xe9` sinon : les deux formes, dans la même valeur."""
        assert compat.desechapper("fr\\x00e9d\\xe9ric") == "frédéric"

    def test_desechapper_antislash_et_guillemet(self):
        assert compat.desechapper('Z:\\\\home\\\\a\\"b') == 'Z:' + B + "home" + B + 'a"b'

    def test_desechapper_octal_et_controle(self):
        assert compat.desechapper("a\\tb\\012c") == "a\tb\nc"

    def test_lire_une_cle(self):
        cle = "Software" + B + "Wow6432Node" + B + CLE_HP7.split(B, 1)[1]
        valeurs = compat.lire_cle(SYSTEM_REG, cle)
        assert valeurs == {
            "Guillemet": 'a"b',
            "Install Dir": "Z:" + B + B.join(["home", "frédéric", "Games", "HP7"]) + B,
            "Locale": "fr_FR",
            "Nombre": 7,
        }

    def test_la_casse_de_la_cle_ne_compte_pas(self):
        cle = "SOFTWARE" + B + "WOW6432NODE" + B + CLE_HP7.split(B, 1)[1]
        assert compat.lire_cle(SYSTEM_REG, cle)["Locale"] == "fr_FR"

    def test_cle_absente(self):
        assert compat.lire_cle(SYSTEM_REG, "Software" + B + "Rien") == {}

    def test_types_ignores(self):
        texte = '[A] 1\n"h"=hex:01,02\n"e"=str(2):"%WINDIR%"\n'
        assert compat.lire_cle(texte, "A") == {"e": "%WINDIR%"}

    def test_lire_valeurs_dans_la_vue_32_bits(self, tmp_path):
        """Le jeu est 32 bits : sa clé HKLM est sous `Wow6432Node`."""
        (tmp_path / "system.reg").write_text(SYSTEM_REG, encoding="utf-8")
        assert compat.lire_valeurs(tmp_path, "HKLM", CLE_HP7, ["Locale", "absente"]) == {
            "Locale": "fr_FR"}

    def test_les_noms_de_valeur_ignorent_la_casse(self, tmp_path):
        (tmp_path / "system.reg").write_text(SYSTEM_REG, encoding="utf-8")
        assert compat.lire_valeurs(tmp_path, "HKLM", CLE_HP7, ["locale"]) == {"locale": "fr_FR"}

    def test_prefixe_32_bits_sans_redirection(self, tmp_path):
        texte = SYSTEM_REG.replace("#arch=win64", "#arch=win32").replace(
            "Wow6432Node\\\\Electronic", "Electronic")
        (tmp_path / "system.reg").write_text(texte, encoding="utf-8")
        assert compat.lire_valeurs(tmp_path, "HKLM", CLE_HP7, ["Locale"]) == {"Locale": "fr_FR"}

    def test_hkcu_n_est_pas_redirige(self, tmp_path):
        """`HKCU\\Software` est partagé entre les vues depuis Windows 7."""
        (tmp_path / "system.reg").write_text(SYSTEM_REG, encoding="utf-8")
        (tmp_path / "user.reg").write_text('[Software\\\\Ed\\\\Jeu] 1\n"L"="fr"\n',
                                           encoding="utf-8")
        assert compat.lire_valeurs(tmp_path, "HKCU", "Software" + B + "Ed" + B + "Jeu",
                                   ["L"]) == {"L": "fr"}
        assert compat.vue_effective(tmp_path, "HKCU", 32) == 64
        assert compat.vue_effective(tmp_path, "HKLM", 32) == 32

    def test_fichier_absent(self, tmp_path):
        assert compat.lire_valeurs(tmp_path, "HKLM", CLE_HP7, ["Locale"]) == {}


class TestPageDeCodes:
    def test_lue_dans_le_registre_du_prefixe(self, tmp_path):
        (tmp_path / "system.reg").write_text(
            SYSTEM_REG.replace('"ACP"="1252"', '"ACP"="1251"'), encoding="utf-8")
        assert compat.encodage_ansi(tmp_path) == "cp1251"

    def test_repli(self, tmp_path):
        assert compat.encodage_ansi(tmp_path) == "cp1252"

    def test_page_inconnue_de_python(self, tmp_path):
        (tmp_path / "system.reg").write_text(
            SYSTEM_REG.replace('"ACP"="1252"', '"ACP"="99999"'), encoding="utf-8")
        assert compat.encodage_ansi(tmp_path, defaut="cp1252") == "cp1252"


class TestPrerequisDuPrefixe:
    def test_marque_des_dll_de_wine(self, tmp_path):
        """Relevé sur Wine 9.0 : `Wine builtin DLL` à l'octet 0x40."""
        interne = tmp_path / "interne.dll"
        interne.write_bytes(b"MZ" + bytes(0x3E) + b"Wine builtin DLL" + bytes(16))
        vraie = tmp_path / "vraie.dll"
        vraie.write_bytes(b"MZ" + bytes(0x3E) + b"This program cannot be run" + bytes(8))
        assert compat.est_dll_interne_wine(interne) is True
        assert compat.est_dll_interne_wine(vraie) is False
        assert compat.est_dll_interne_wine(tmp_path / "absente.dll") is False

    def test_verbes_de_winetricks(self, tmp_path):
        (tmp_path / "winetricks.log").write_text("vcrun2005\n\nVCRUN2022\n", encoding="utf-8")
        assert compat.verbes_installes(tmp_path) == {"vcrun2005", "vcrun2022"}
        assert compat.verbes_installes(tmp_path / "rien") == set()


class TestSurchargesDeDll:
    def test_native_d_abord(self):
        assert compat.composer_surcharges("", ["d3d9", "msvcr71"]) == "d3d9=n,b;msvcr71=n,b"

    def test_rien_a_ajouter(self):
        assert compat.composer_surcharges("", []) == ""

    def test_un_reglage_de_l_utilisateur_est_garde(self):
        """Une DLL déjà surchargée : son réglage est délibéré, le nôtre un défaut."""
        existant = "d3d9=b;dxgi,d3d11=n"
        resultat = compat.composer_surcharges(existant, ["D3D9", "ddraw"])
        assert resultat == "d3d9=b;dxgi,d3d11=n;ddraw=n,b"


class TestEnvironnement:
    def test_hote_sans_trace_de_pyinstaller(self):
        base = {"PATH": "/usr/bin", "_PYI_APPLICATION_HOME_DIR": "/tmp/x",
                "LD_LIBRARY_PATH": "/tmp/_MEI/lib:/opt/lib",
                "LD_LIBRARY_PATH_ORIG": "/opt/lib"}
        env = compat.environnement_hote(base, gele=True)
        assert env == {"PATH": "/usr/bin", "LD_LIBRARY_PATH": "/opt/lib"}

    def test_hote_gele_sans_ld_library_path_d_origine(self):
        """Le chargeur l'a CRÉÉ : l'hériter ferait charger nos bibliothèques
        embarquées par wine, umu et le navigateur."""
        env = compat.environnement_hote({"LD_LIBRARY_PATH": "/tmp/_MEI"}, gele=True,
                                        embarque="/tmp/_MEI")
        assert "LD_LIBRARY_PATH" not in env

    def test_hote_gele_garde_ce_que_l_utilisateur_avait_pose(self):
        """Sans `LD_LIBRARY_PATH_ORIG`, seules NOS entrées partent."""
        base = {"LD_LIBRARY_PATH": "/tmp/_MEI:/tmp/_MEI/lib:/opt/mes-libs:/tmp/_MEIxyz"}
        env = compat.environnement_hote(base, gele=True, embarque="/tmp/_MEI/")
        assert env["LD_LIBRARY_PATH"] == "/opt/mes-libs:/tmp/_MEIxyz"

    def test_hote_gele_origine_vide(self):
        """`LD_LIBRARY_PATH_ORIG` vide : il n'y avait rien avant nous."""
        base = {"LD_LIBRARY_PATH": "/tmp/_MEI", "LD_LIBRARY_PATH_ORIG": ""}
        env = compat.environnement_hote(base, gele=True, embarque="/tmp/_MEI")
        assert "LD_LIBRARY_PATH" not in env and "LD_LIBRARY_PATH_ORIG" not in env

    def test_depuis_les_sources_rien_ne_change(self):
        base = {"LD_LIBRARY_PATH": "/opt/lib"}
        assert compat.environnement_hote(base, gele=False) == base

    def test_umu(self, tmp_path):
        umu = Lanceur("umu", "/usr/bin/umu-run", proton="/p/GE-Proton10-3")
        env = compat.environnement(umu, tmp_path, ["d3d9"], base={"PATH": "/usr/bin"})
        assert env["WINEPREFIX"] == str(tmp_path)
        assert env["GAMEID"] == "umu-default"
        assert env["PROTONPATH"] == "/p/GE-Proton10-3"
        assert env["WINEDLLOVERRIDES"] == "d3d9=n,b"
        assert "__COMPAT_LAYER" not in env

    def test_umu_respecte_les_reglages_de_l_utilisateur(self, tmp_path):
        umu = Lanceur("umu", "/usr/bin/umu-run", proton="/p/GE")
        env = compat.environnement(umu, tmp_path, base={"GAMEID": "umu-12", "PROTONPATH": "/x"})
        assert env["GAMEID"] == "umu-12" and env["PROTONPATH"] == "/x"

    def test_wine(self, tmp_path):
        wine = Lanceur("wine", "/usr/bin/wine", winetricks="/usr/bin/winetricks")
        env = compat.environnement(wine, tmp_path, base={})
        assert env["WINEDEBUG"] == "-all"
        assert env["WINE"] == "/usr/bin/wine"     # le winetricks du système l'utilise
        assert "WINEDLLOVERRIDES" not in env


class TestAssainirLeProcessus:
    """`assainir_environnement` retouche `os.environ` du launcher lui-même,
    pour ce que Qt lance sans nous (`xdg-open`, le navigateur qui suit)."""

    def test_exe_gele_sous_linux(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", "/tmp/_MEI42", raising=False)
        monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEI42:/opt/lib")
        monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/opt/lib")
        compat.assainir_environnement()
        assert os.environ["LD_LIBRARY_PATH"] == "/opt/lib"
        assert "LD_LIBRARY_PATH_ORIG" not in os.environ

    def test_rien_a_garder(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", "/tmp/_MEI42", raising=False)
        monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEI42")
        monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
        compat.assainir_environnement()
        assert "LD_LIBRARY_PATH" not in os.environ

    @pytest.mark.parametrize("plateforme, gele", [("win32", True), ("linux", False)])
    def test_ailleurs_rien_ne_bouge(self, monkeypatch, plateforme, gele):
        """Windows et les sources : l'environnement est celui qu'on a reçu."""
        monkeypatch.setattr(sys, "platform", plateforme)
        monkeypatch.setattr(sys, "frozen", gele, raising=False)
        monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEI42:/opt/lib")
        compat.assainir_environnement()
        assert os.environ["LD_LIBRARY_PATH"] == "/tmp/_MEI42:/opt/lib"


class TestCommandes:
    UMU = Lanceur("umu", "/usr/bin/umu-run")
    WINE = Lanceur("wine", "/usr/bin/wine", winetricks="/usr/bin/winetricks")

    def test_jeu(self, tmp_path):
        exe = tmp_path / "HP1" / "System" / "HP.exe"
        assert compat.commande_jeu(self.UMU, exe) == ["/usr/bin/umu-run", str(exe)]

    def test_creation_du_prefixe(self):
        """`umu-run ""` : documenté par umu (« Create a umu WINE prefix »)."""
        assert compat.commande_creation(self.UMU) == ["/usr/bin/umu-run", ""]
        assert compat.commande_creation(self.WINE) == ["/usr/bin/wine", "wineboot", "--init"]

    def test_winetricks(self):
        """umu ajoute `-q` lui-même (umu_run.py) ; le winetricks du système le reçoit."""
        assert compat.commande_winetricks(self.UMU, ["vcrun2005"]) == [
            "/usr/bin/umu-run", "winetricks", "vcrun2005"]
        assert compat.commande_winetricks(self.WINE, ["vcrun2005"]) == [
            "/usr/bin/winetricks", "-q", "vcrun2005"]
        assert compat.commande_winetricks(Lanceur("wine", "/usr/bin/wine"), ["x"]) is None

    def test_regedit_par_umu_vise_l_exe_du_prefixe(self, tmp_path):
        """umu exige un exécutable qu'il trouve ; un nom nu n'est que « supposé »."""
        regedit = tmp_path / "drive_c" / "windows" / "regedit.exe"
        assert compat.commande_regedit(self.UMU, tmp_path, "C:" + B + "x.reg")[1] == "regedit"
        regedit.parent.mkdir(parents=True)
        regedit.write_bytes(b"MZ")
        assert compat.commande_regedit(self.UMU, tmp_path, "C:" + B + "x.reg") == [
            "/usr/bin/umu-run", str(regedit), "/S", "C:" + B + "x.reg"]
        assert compat.commande_regedit(self.WINE, tmp_path, "f") == [
            "/usr/bin/wine", "regedit", "/S", "f"]

    def test_journal_d_un_identifiant_douteux(self):
        """L'identifiant vient du catalogue DISTANT et finit dans un nom de fichier."""
        assert compat.journal_du_jeu("hp7a").name == "wine-hp7a.log"
        assert compat.journal_du_jeu("../../evil").name == "wine-jeu.log"


def _processus(proc: Path, pid: int, comm: str, arg0: str, prefixe: str | None = None) -> None:
    dossier = proc / str(pid)
    dossier.mkdir(parents=True)
    (dossier / "comm").write_text(comm + "\n", encoding="utf-8")
    (dossier / "cmdline").write_bytes(arg0.encode("utf-8") + b"\0--flag\0")
    environ = b"PATH=/usr/bin\0" + (f"WINEPREFIX={prefixe}".encode() + b"\0" if prefixe else b"")
    (dossier / "environ").write_bytes(environ)


class TestProcessusDuJeu:
    """L'équivalent de `tasklist`, sur un faux `/proc` posé par le test —
    joué aussi sous Windows : la lecture est la même, seul le vrai `/proc`
    manque."""

    def test_par_le_nom_que_wine_donne_au_processus(self, tmp_path):
        _processus(tmp_path / "proc", 4242, "HP.exe", "C:" + B + "Jeux" + B + "HP.exe")
        assert compat.processus_du_jeu("hp.exe", proc=tmp_path / "proc")

    def test_par_le_premier_argument(self, tmp_path):
        _processus(tmp_path / "proc", 4243, "wine-preloader", "Z:" + B + "g" + B + "Game.exe")
        assert compat.processus_du_jeu("game.exe", proc=tmp_path / "proc")

    def test_le_lanceur_lui_meme_ne_compte_pas(self, tmp_path):
        """`umu-run /…/HP.exe` a l'exe en SECOND argument : ce n'est pas le jeu."""
        _processus(tmp_path / "proc", 4244, "umu-run", "/usr/bin/umu-run")
        assert not compat.processus_du_jeu("hp.exe", proc=tmp_path / "proc")

    def test_un_autre_prefixe_ne_prolonge_pas_la_session(self, tmp_path):
        """Le même jeu lancé par Lutris, dans son préfixe à lui."""
        _processus(tmp_path / "proc", 4245, "HP.exe", "HP.exe", prefixe="/ailleurs")
        assert not compat.processus_du_jeu("hp.exe", tmp_path / "pfx", proc=tmp_path / "proc")

    @pytest.mark.skipif(sys.platform == "win32", reason="lien symbolique : droits admin sous Windows")
    def test_le_lien_pfx_de_proton_est_le_meme_prefixe(self, tmp_path):
        """Proton pose `WINEPREFIX=<préfixe>/pfx/`, et umu fait de `pfx` un
        lien vers le préfixe lui-même."""
        pfx = tmp_path / "pfx-umu"
        pfx.mkdir()
        (pfx / "pfx").symlink_to(".")
        _processus(tmp_path / "proc", 4246, "hp8.exe", "hp8.exe", prefixe=f"{pfx}/pfx/")
        assert compat.processus_du_jeu("hp8.exe", pfx, proc=tmp_path / "proc")

    def test_nom_tronque_par_le_noyau(self, tmp_path):
        """`comm` s'arrête à 15 caractères."""
        _processus(tmp_path / "proc", 4247, "harrypotter_ext", "x")
        assert compat.processus_du_jeu("harrypotter_extra.exe", proc=tmp_path / "proc")

    def test_proc_absent(self, tmp_path):
        assert not compat.processus_du_jeu("hp.exe", proc=tmp_path / "rien")
        assert not compat.processus_du_jeu("", proc=tmp_path)
