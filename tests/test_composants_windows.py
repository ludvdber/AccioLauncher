"""Composants Windows installés d'un clic (ACT-054, audit du 2026-10-07).

Aucun test n'exécute un installeur ni n'ouvre d'invite : `executer_eleve` est
interdit par `conftest`, le réseau et la signature sont bouchonnés ici.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core import composants_windows as cw
from src.core import system_checks
from tests.test_preparation_wine import _boite_espion, _Vue


@pytest.fixture
def jeu_hp7a():
    from src.core.game_data import GameData
    return GameData.from_dict({
        "id": "hp7a", "name": "HP7", "year": 2010, "description": "d", "developer": "EA",
        "executable": "HP7/pc/hp7.exe", "cover_image": "c.jpg",
        "requires": ["vcredist2005_x86"], "versions": []})


class TestPaquets:
    def test_un_installeur_par_famille_dans_l_ordre(self):
        paquets = cw.paquets_pour(["xinput1_3", "vcredist_x86", "d3dx9_43",
                                   "vcredist2005_x86", "d3dcompiler_43", "inconnu"])
        assert [p.cle for p in paquets] == ["vc2005", "vc2022", "directx"]

    def test_tout_prerequis_declarable_a_son_installeur(self):
        """Un identifiant que le catalogue peut déclarer sans installeur ici
        retomberait en silence sur la page : la table doit rester complète."""
        assert set(system_checks.PREREQUIS) == set(cw.PAQUET_DU_PREREQUIS)

    def test_tout_vient_de_chez_microsoft_en_https(self):
        for p in cw.PAQUETS.values():
            assert p.url.startswith(("https://download.microsoft.com/", "https://aka.ms/"))


class TestScript:
    """Audit du 2026-10-29 : les installeurs vérifiés côté utilisateur étaient
    lancés ÉLEVÉS depuis un `mkdtemp` que tout programme du même compte peut
    modifier pendant l'invite UAC, par un `.bat` posé au même endroit."""

    _SOURCE = Path("C:/Users/Frédéric O'Brien/AppData/Local/Temp/accio_composants_x")

    def _script(self, prerequis=("vcredist2005_x86", "xinput1_3")):
        paquets = cw.paquets_pour(prerequis)
        return cw.script_d_installation(paquets, self._SOURCE, {p.cle: p.cle * 8 for p in paquets})

    def test_rien_n_est_lance_depuis_le_dossier_de_l_utilisateur(self):
        corps = self._script()
        lances = [ligne for ligne in corps.splitlines() if "Start-Process" in ligne]
        assert lances and all("-FilePath $cible" in ligne for ligne in lances)
        assert "$d = Join-Path $win ('Temp\\accio_composants_' + [guid]::NewGuid()" in corps
        assert "GetFolderPath('Windows')" in corps and "SystemRoot" not in corps

    def test_la_copie_est_verifiee_avant_d_etre_lancee(self):
        corps = self._script(("vcredist2005_x86",))
        copie = corps.index("Copy-Item")
        empreinte = corps.index("Get-FileHash -LiteralPath $cible")
        signature = corps.index("Get-AuthenticodeSignature -LiteralPath $cible")
        lancement = corps.index("Start-Process")
        assert copie < empreinte < lancement and copie < signature < lancement
        assert "'vc2005vc2005vc2005vc2005vc2005vc2005vc2005vc2005'" in corps

    def test_le_chemin_est_une_chaine_powershell_sure(self):
        """Une apostrophe dans le nom du compte se double, rien ne s'interprète."""
        assert "'C:\\Users\\Frédéric O''Brien" in self._script().replace("/", "\\")

    def test_rien_n_est_ecrit_dans_le_dossier_de_l_utilisateur(self):
        """Le processus élevé écrivait son bilan dans `source` : une jonction ou
        un lien posé là par un programme sans privilège redirige une écriture
        ADMINISTRATEUR vers n'importe quel fichier du système. Le bilan revient
        par le code de sortie de PowerShell."""
        corps = self._script(("vcredist2005_x86", "vcredist_x86"))
        for ecriture in ("Set-Content", "Out-File", "Add-Content", "resultats"):
            assert ecriture not in corps, ecriture
        assert corps.rstrip().endswith(f"exit ($bilan + {cw.MARQUE_BILAN})")
        # Trois bits par paquet, dans l'ordre : vc2005 au rang 0, vc2022 au rang 1.
        assert "$bilan += $n * 1" in corps and "$bilan += $n * 8" in corps

    def test_le_script_voyage_dans_la_ligne_de_commande(self):
        import base64
        programme, parametres = cw.commande_powershell_elevee("Write-Output 1")
        assert programme.lower().endswith("powershell.exe")
        encode = parametres.split("-EncodedCommand ")[1]
        assert base64.b64decode(encode).decode("utf-16-le") == "Write-Output 1"

    @pytest.mark.skipif(sys.platform != "win32", reason="parseur de Windows PowerShell")
    def test_windows_powershell_accepte_la_syntaxe(self):
        """Le script n'est jamais EXÉCUTÉ par la suite (invite UAC) : le parseur
        de PowerShell en vérifie au moins la syntaxe, sur le job Windows."""
        import base64
        import subprocess
        from src.core import game_registry
        for script in (self._script(), game_registry.script_registre_eleve("Windows Registry Editor Version 5.00\r\n")):
            texte = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
            verifie = ("$t = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('" + texte + "')); "
                       "$e = $null; [void][Management.Automation.Language.Parser]::ParseInput($t, [ref]$null, [ref]$e); "
                       "[Console]::Out.Write($e.Count)")
            programme, _ = cw.commande_powershell_elevee("")
            sortie = subprocess.run(  # nosec B603 : test, chemin système absolu
                [programme, "-NoProfile", "-NonInteractive", "-EncodedCommand",
                 base64.b64encode(verifie.encode("utf-16-le")).decode("ascii")],
                capture_output=True, timeout=60,
                # Comme `signature_microsoft` : sans le PSModulePath de PowerShell 7 (la CI).
                env={k: v for k, v in __import__("os").environ.items() if k.upper() != "PSMODULEPATH"})
            assert sortie.stdout.decode("utf-8", "replace").strip() == "0", sortie.stderr

    def test_lire_le_bilan(self):
        paquets = cw.paquets_pour(("vcredist2005_x86", "vcredist_x86"))
        code = cw.MARQUE_BILAN + 1 * 1 + 2 * 8
        assert cw.lire_bilan(code, paquets) == {"vc2005": "réussi", "vc2022": "redémarrage demandé"}
        assert cw.lire_bilan(cw.MARQUE_BILAN + 4 + 5 * 8, paquets) == {
            "vc2005": "copie refusée", "vc2022": "échec"}
        # PowerShell arrêté par une exception : code 1, pas un bilan.
        assert cw.lire_bilan(1, paquets) == {}
        assert cw.lire_bilan(cw.MARQUE_BILAN, paquets) == {
            "vc2005": "non lancé", "vc2022": "non lancé"}


class TestSignature:
    SUJET = "CN=Microsoft Corporation, O=Microsoft Corporation, L=Redmond, S=Washington, C=US"

    def test_valide_et_microsoft(self):
        assert cw.est_signe_par_microsoft("Valid", self.SUJET)

    @pytest.mark.parametrize("statut, sujet", [
        ("HashMismatch", SUJET),     # le fichier a bougé après la signature
        ("NotSigned", ""),
        ("Valid", "CN=Microsoft Corporation Fake, O=Quelqu'un, C=US"),
        ("Valid", "CN=Autre, O=Microsoft Corporation"),
    ])
    def test_tout_le_reste_est_refuse(self, statut, sujet):
        assert not cw.est_signe_par_microsoft(statut, sujet)

    @pytest.mark.skipif(sys.platform != "win32", reason="Authenticode : Windows seulement")
    def test_la_vraie_lecture_par_powershell(self, monkeypatch, tmp_path):
        """Le script encodé, le fichier passé par l'environnement, la sortie
        « statut|sujet » : jamais exécutés pour de vrai avant le 2026-10-24.
        Lecture seule, aucune invite. explorer.exe est signé par catalogue au nom
        de « Microsoft Windows » : lu Valid, puis refusé (un installeur Visual C++
        est signé « Microsoft Corporation »)."""
        import os
        from pathlib import Path
        lus = []
        vraie = cw.est_signe_par_microsoft
        monkeypatch.setattr(cw, "est_signe_par_microsoft",
                            lambda statut, sujet: lus.append((statut, sujet)) or vraie(statut, sujet))
        explorer = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "explorer.exe")
        assert not cw.signature_microsoft(Path(explorer))
        assert lus[-1][0] == "Valid" and "O=Microsoft Corporation" in lus[-1][1]
        nu = tmp_path / "nu.exe"
        nu.write_bytes(b"MZ" + b"\0" * 64)
        assert not cw.signature_microsoft(nu)
        assert lus[-1][0] in ("NotSigned", "UnknownError")


    def test_powershell_7_ne_lui_passe_pas_ses_modules(self, monkeypatch, tmp_path):
        """Hérité d'un terminal PowerShell 7, PSModulePath fait échouer Windows
        PowerShell sans un mot : la CI était rouge, et un joueur lancé depuis ce
        terminal se voyait refuser les installeurs Microsoft."""
        import subprocess
        monkeypatch.setattr(cw.sys, "platform", "win32")
        monkeypatch.setattr("src.core.win_utils.dossier_systeme", lambda: r"C:\Windows\System32")
        monkeypatch.setenv("PSModulePath", r"C:\Program Files\PowerShell\7\Modules")
        vus = {}

        def run(args, **k):
            vus.update(k["env"])
            return subprocess.CompletedProcess(args, 0, b"Valid|" + self.SUJET.encode(), b"")
        monkeypatch.setattr(cw.subprocess, "run", run)
        assert cw.signature_microsoft(tmp_path / "vc.exe")
        assert not any(c.upper() == "PSMODULEPATH" for c in vus)
        assert vus["ACCIO_FICHIER"] == str(tmp_path / "vc.exe")


class _Fil(cw.InstallationComposants):
    """Le vrai fil, réseau et signature bouchonnés."""

    def __init__(self, prerequis, signe=True, code=0):
        super().__init__(prerequis)
        self.telecharges = []
        self._signe = signe
        self._code = code

    def _telecharger(self, paquet, fichier):
        fichier.write_bytes(b"MZ")
        self.telecharges.append(paquet.cle)
        return True


class TestLeFil:
    def _executer(self, monkeypatch, fil, code, restants=()):
        lances = []
        monkeypatch.setattr(cw, "signature_microsoft", lambda _f: fil._signe)

        def eleve(script, _abandon=None):
            lances.append(script)
            return code
        monkeypatch.setattr(cw, "executer_eleve", eleve)
        monkeypatch.setattr(system_checks, "prerequis_manquants", lambda _r: list(restants))
        fins = []
        fil.installation_terminee.connect(lambda ok, raison: fins.append((ok, raison)))
        fil.run()
        return fins[0], lances

    def test_tout_est_installe(self, monkeypatch):
        fil = _Fil(["vcredist2005_x86", "xinput1_3"])
        fin, lances = self._executer(monkeypatch, fil, 0)
        assert fin == (True, "")
        assert fil.telecharges == ["vc2005", "directx"]
        assert len(lances) == 1, "une seule invite pour tous les composants"

    def test_une_signature_refusee_n_execute_rien(self, monkeypatch):
        fil = _Fil(["vcredist2005_x86"], signe=False)
        fin, lances = self._executer(monkeypatch, fil, 0)
        assert fin == (False, cw.SIGNATURE) and lances == []

    def test_invite_refusee(self, monkeypatch):
        fin, _ = self._executer(monkeypatch, _Fil(["vcredist_x86"]), None)
        assert fin == (False, cw.REFUSEE)

    def test_la_relecture_fait_foi(self, monkeypatch):
        """Code 0 partout, mais la DLL n'est toujours pas là : c'est un échec."""
        fin, _ = self._executer(monkeypatch, _Fil(["vcredist_x86"]), 0, ["vcredist_x86"])
        assert fin == (False, cw.COMPOSANTS)

    def test_le_dossier_temporaire_ne_reste_pas(self, monkeypatch, tmp_path):
        crees = []
        vrai = cw.tempfile.mkdtemp

        def mkdtemp(**k):
            crees.append(vrai(dir=tmp_path, **k))
            return crees[-1]
        monkeypatch.setattr(cw.tempfile, "mkdtemp", mkdtemp)
        self._executer(monkeypatch, _Fil(["vcredist_x86"]), 0)
        assert crees and not any(tmp_path.iterdir())


@pytest.fixture
def windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")


class TestLesBoites:
    def test_la_question_nomme_tout_annonce_l_invite_et_le_poids(self, monkeypatch, windows,
                                                                  jeu_hp7a):
        from src.ui import game_detail_handlers as gdh
        monkeypatch.setattr(gdh, "prerequis_manquants",
                            lambda _r: ["vcredist2005_x86", "xinput1_3"])
        vus = _boite_espion(monkeypatch, 0)
        vue = _Vue(jeu_hp7a)
        gdh.proposer_preparation(vue, jeu_hp7a, puis_jouer=True)
        titre, texte, choix = vus[0]
        assert "Visual C++ 2005" in texte and "DirectX" in texte
        assert "administrateur" in texte and "Mo" in texte
        assert choix == ("Tout installer et lancer", "Ouvrir la page Microsoft", "Plus tard")
        assert vue.preparations == [("hp7a", ["vcredist2005_x86", "xinput1_3"], True)]

    def test_plus_tard_n_installe_rien(self, monkeypatch, windows, jeu_hp7a):
        from src.ui import game_detail_handlers as gdh
        monkeypatch.setattr(gdh, "prerequis_manquants", lambda _r: ["vcredist2005_x86"])
        _boite_espion(monkeypatch, 2)
        vue = _Vue(jeu_hp7a)
        gdh.proposer_preparation(vue, jeu_hp7a, puis_jouer=True)
        assert vue.preparations == []

    def test_un_refus_de_l_invite_n_ouvre_pas_de_boite(self, monkeypatch, windows, jeu_hp7a):
        """Règle 69 : un refus n'est pas une erreur."""
        from src.ui import game_detail_handlers as gdh
        vus = _boite_espion(monkeypatch, 0)
        vue = _Vue(jeu_hp7a)
        gdh.apres_preparation(vue, "hp7a", False, cw.REFUSEE, True)
        assert not vus and len(vue.notes) == 1

    def test_une_signature_refusee_le_dit_et_offre_la_page(self, monkeypatch, windows, jeu_hp7a):
        from src.ui import game_detail_handlers as gdh
        ouverts = []
        monkeypatch.setattr(gdh, "open_url", ouverts.append)
        monkeypatch.setattr(gdh, "prerequis_manquants", lambda _r: ["vcredist2005_x86"])
        vus = _boite_espion(monkeypatch, 0)
        gdh.apres_preparation(_Vue(jeu_hp7a), "hp7a", False, cw.SIGNATURE, True)
        assert "pas signé par Microsoft" in vus[0][1]
        assert ouverts == [system_checks.VCREDIST_2005_URL]

    def test_reussite_puis_jouer(self, monkeypatch, windows, jeu_hp7a):
        from src.ui import game_detail_handlers as gdh
        joues = []
        monkeypatch.setattr(gdh, "on_play", lambda vue, **k: joues.append(k))
        gdh.apres_preparation(_Vue(jeu_hp7a), "hp7a", True, "", True)
        assert joues == [{}]


def test_l_installateur_a_le_contrat_du_preparateur_wine():
    """La fiche et la barre du bas parlent à l'un ou à l'autre sans savoir lequel."""
    from src.ui.installateur_composants import InstallateurComposants
    from src.ui.preparateur_wine import PreparateurWine
    for nom in ("message", "commencee", "progression", "terminee", "en_cours", "journal",
                "demarrer", "annuler", "shutdown"):
        assert nom in dir(InstallateurComposants) and nom in dir(PreparateurWine), nom


def test_rien_a_installer_ne_demarre_rien(qtbot):
    from src.ui.installateur_composants import InstallateurComposants
    inst = InstallateurComposants()
    assert not inst.demarrer(SimpleNamespace(id="hpx"), ["inconnu"], False)
    assert not inst.en_cours
