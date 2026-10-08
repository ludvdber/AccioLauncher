"""Composants Windows installés d'un clic (ACT-054, audit du 2026-10-07).

Aucun test n'exécute un installeur ni n'ouvre d'invite : `executer_eleve` est
interdit par `conftest`, le réseau et la signature sont bouchonnés ici.
"""
import sys
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
    def test_aucun_chemin_dans_le_corps_et_fins_crlf(self):
        """Règles 79 et 80 : relu en page OEM, un chemin accentué casserait ;
        sans CRLF, cmd se repositionne au mauvais octet."""
        corps = cw.script_d_installation(cw.paquets_pour(["vcredist2005_x86", "xinput1_3"]))
        corps.encode("ascii")
        assert ":\\" not in corps and "Users" not in corps
        assert corps.count("\r\n") == corps.count("\n")
        assert 'start "" /wait "%~dp0vc2005.exe" /q' in corps
        assert 'start "" /wait "%~dp0directx.exe" /Q' in corps

    def test_le_code_est_note_redirection_en_tete(self):
        """`echo x 0>>f` redirigerait le flux 0 : le code 0 ne serait jamais écrit."""
        corps = cw.script_d_installation(cw.paquets_pour(["vcredist_x86"]))
        assert '>>"%~dp0resultats.txt" echo vc2022 %errorlevel%' in corps

    def test_lire_les_resultats(self):
        assert cw.lire_resultats("vc2005 0\r\nvc2022 3010\r\nbruit\r\nvc2008 x\r\n") == {
            "vc2005": 0, "vc2022": 3010}


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
            lances.append(script.read_bytes())
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
