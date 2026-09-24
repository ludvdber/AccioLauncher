"""La préparation du préfixe Wine : créer, installer, et le dire.

Aucun Wine n'est lancé : `Popen` est remplacé par un faux processus qui produit
ce qu'aurait produit le vrai (le `system.reg` d'un préfixe créé, la ligne de
`winetricks.log` d'un verbe installé). Le fil est exercé en appelant ses étapes
directement ; l'orchestrateur, lui, fait tourner un vrai `QThread`, qui se
termine de lui-même — jamais par `terminate()` (règle 3 de CLAUDE.md).
"""

import subprocess
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("pytestqt")

from src.core import compat, preparation_wine as prep  # noqa: E402
from src.core.compat import Lanceur  # noqa: E402

UMU = Lanceur("umu", "/nonexistent/umu-run")
WINE = Lanceur("wine", "/nonexistent/wine", winetricks="/nonexistent/winetricks")


class _FauxProc:
    def __init__(self, code=0, dure=0):
        self.pid = 999_999
        self._code = code
        self._reste = dure
        self.tue = False

    def wait(self, timeout=None):
        if self._reste > 0 and not self.tue:
            self._reste -= 1
            raise subprocess.TimeoutExpired("x", timeout)
        return self._code

    def kill(self):
        self.tue = True


def _faux_popen(monkeypatch, effets):
    """`effets(commande, env)` joue ce qu'aurait fait le vrai programme."""
    appels = []

    def faux(commande, **kwargs):
        appels.append((commande, kwargs))
        return effets(commande, kwargs["env"]) or _FauxProc()
    monkeypatch.setattr(prep.subprocess, "Popen", faux)
    return appels


def _cree_le_prefixe(pfx):
    (pfx / "drive_c").mkdir(parents=True, exist_ok=True)
    (pfx / "system.reg").write_text("WINE REGISTRY Version 2\n#arch=win64\n", encoding="utf-8")


def _fil(tmp_path, lanceur=WINE, verbes=("vcrun2005",)):
    pfx = tmp_path / "prefixes" / lanceur.famille
    return prep.PreparationWine(lanceur, pfx, verbes, tmp_path / "logs" / "prep.log"), pfx


class TestLesEtapes:
    def test_creer_puis_installer(self, tmp_path, monkeypatch):
        fil, pfx = _fil(tmp_path)

        def effets(commande, env):
            if "wineboot" in commande:
                _cree_le_prefixe(pfx)
            else:
                (pfx / "winetricks.log").write_text("vcrun2005\n", encoding="utf-8")
        appels = _faux_popen(monkeypatch, effets)
        assert fil._preparer() == (True, "")
        assert [c for c, _ in appels] == [
            [WINE.executable, "wineboot", "--init"],
            [WINE.winetricks, "-q", "vcrun2005"]]

    def test_pas_de_fenetre_mono_ni_gecko_a_la_creation(self, tmp_path, monkeypatch):
        """Wine les propose par des fenêtres que personne n'attend ici."""
        fil, pfx = _fil(tmp_path, verbes=())
        appels = _faux_popen(monkeypatch, lambda c, e: _cree_le_prefixe(pfx))
        fil._preparer()
        assert "mscoree,mshtml=" in appels[0][1]["env"]["WINEDLLOVERRIDES"]

    def test_chaque_processus_dans_sa_session_et_le_prefixe(self, tmp_path, monkeypatch):
        """À l'annulation, c'est tout le groupe qu'on arrête (umu, conteneur,
        winetricks), pas seulement le premier processus."""
        fil, pfx = _fil(tmp_path, verbes=())
        appels = _faux_popen(monkeypatch, lambda c, e: _cree_le_prefixe(pfx))
        fil._preparer()
        kwargs = appels[0][1]
        assert kwargs["start_new_session"] is True
        assert kwargs["env"]["WINEPREFIX"] == str(pfx)
        assert kwargs["stdin"] == subprocess.DEVNULL

    def test_un_prefixe_deja_pret_n_est_pas_recree(self, tmp_path, monkeypatch):
        fil, pfx = _fil(tmp_path, UMU)
        _cree_le_prefixe(pfx)
        def effets(commande, env):
            (pfx / "winetricks.log").write_text("vcrun2005\n", encoding="utf-8")
        appels = _faux_popen(monkeypatch, effets)
        assert fil._preparer() == (True, "")
        assert [c for c, _ in appels] == [[UMU.executable, "winetricks", "vcrun2005"]]

    def test_le_prefixe_qui_n_arrive_jamais(self, tmp_path, monkeypatch):
        monkeypatch.setattr(prep, "_ATTENTE_PREFIXE_S", 0)
        fil, _ = _fil(tmp_path)
        _faux_popen(monkeypatch, lambda c, e: None)
        assert fil._preparer() == (False, prep.PREFIXE)

    def test_wine_sans_winetricks(self, tmp_path, monkeypatch):
        fil, pfx = _fil(tmp_path, Lanceur("wine", "/nonexistent/wine"))
        _cree_le_prefixe(pfx)
        _faux_popen(monkeypatch, lambda c, e: pytest.fail("rien à lancer"))
        assert fil._preparer() == (False, prep.WINETRICKS_ABSENT)

    def test_winetricks_en_echec(self, tmp_path, monkeypatch):
        fil, pfx = _fil(tmp_path)
        _cree_le_prefixe(pfx)
        _faux_popen(monkeypatch, lambda c, e: _FauxProc(code=1))
        assert fil._preparer() == (False, prep.COMPOSANTS)

    def test_un_code_non_nul_mais_le_verbe_est_la(self, tmp_path, monkeypatch):
        """winetricks sort parfois en erreur sur un détail après avoir installé :
        c'est son journal qui fait foi, comme pour la détection."""
        fil, pfx = _fil(tmp_path)
        _cree_le_prefixe(pfx)

        def effets(commande, env):
            (pfx / "winetricks.log").write_text("vcrun2005\n", encoding="utf-8")
            return _FauxProc(code=1)
        _faux_popen(monkeypatch, effets)
        assert fil._preparer() == (True, "")

    def test_sans_verbe_rien_d_autre_que_le_prefixe(self, tmp_path, monkeypatch):
        fil, pfx = _fil(tmp_path, verbes=())
        appels = _faux_popen(monkeypatch, lambda c, e: _cree_le_prefixe(pfx))
        assert fil._preparer() == (True, "")
        assert len(appels) == 1

    def test_le_journal_garde_chaque_commande(self, tmp_path, monkeypatch):
        fil, pfx = _fil(tmp_path)

        def effets(commande, env):
            _cree_le_prefixe(pfx)
            (pfx / "winetricks.log").write_text("vcrun2005\n", encoding="utf-8")
        _faux_popen(monkeypatch, effets)
        fil._preparer()
        journal = (tmp_path / "logs" / "prep.log").read_text(encoding="utf-8")
        assert "wineboot --init" in journal and "vcrun2005" in journal


class TestAnnulation:
    def test_le_groupe_est_arrete(self, tmp_path, monkeypatch):
        fil, pfx = _fil(tmp_path)
        proc = _FauxProc(dure=100)
        _faux_popen(monkeypatch, lambda c, e: proc)
        tues = []
        monkeypatch.setattr(prep.os, "killpg", lambda pid, sig: tues.append(sig) or proc.kill(),
                            raising=False)
        # Posé sur l'INSTANCE, jamais sur la classe Qt (règle 12 de CLAUDE.md).
        fil.isInterruptionRequested = lambda: True
        assert fil._preparer() == (False, prep.ANNULEE)
        assert tues, "le groupe de processus n'a pas été arrêté"


class TestLeFilEmet:
    def test_fin_et_etapes(self, tmp_path, monkeypatch, qtbot):
        fil, pfx = _fil(tmp_path)

        def effets(commande, env):
            _cree_le_prefixe(pfx)
            (pfx / "winetricks.log").write_text("vcrun2005\n", encoding="utf-8")
        _faux_popen(monkeypatch, effets)
        etapes, fins = [], []
        fil.etape.connect(lambda e, v: etapes.append((e, v)))
        fil.preparation_terminee.connect(lambda ok, r: fins.append((ok, r)))
        fil.run()                        # dans CE fil : aucun QThread démarré
        assert etapes == [("prefixe", ""), ("composants", "vcrun2005")]
        assert fins == [(True, "")]

    def test_une_erreur_de_systeme_devient_un_echec_propre(self, tmp_path, monkeypatch, qtbot):
        fil, _ = _fil(tmp_path)

        def explose(*a, **k):
            raise OSError("disque plein")
        monkeypatch.setattr(prep.subprocess, "Popen", explose)
        fins = []
        fil.preparation_terminee.connect(lambda ok, r: fins.append((ok, r)))
        fil.run()
        assert fins == [(False, prep.PREFIXE)]


class TestOrchestrateur:
    def _jeu(self):
        return SimpleNamespace(id="hp7a", name="HP7")

    def test_un_vrai_fil_qui_se_termine_seul(self, qtbot, monkeypatch):
        from src.ui.preparateur_wine import PreparateurWine
        monkeypatch.setattr(prep.PreparationWine, "_preparer", lambda self: (True, ""))
        orch = PreparateurWine()
        with qtbot.waitSignal(orch.terminee, timeout=5000) as signal:
            assert orch.demarrer(self._jeu(), ["vcrun2005"], puis_jouer=True) is True
        assert signal.args == ["hp7a", True, "", True]
        assert not orch.en_cours

    def test_une_seule_a_la_fois(self, qtbot, monkeypatch):
        from src.ui.preparateur_wine import PreparateurWine
        attente = {"fin": False}

        def lente(self):
            while not attente["fin"] and not self.isInterruptionRequested():
                self.msleep(10)
            return True, ""
        monkeypatch.setattr(prep.PreparationWine, "_preparer", lente)
        orch = PreparateurWine()
        assert orch.demarrer(self._jeu(), [], puis_jouer=False)
        assert orch.demarrer(self._jeu(), [], puis_jouer=False) is False
        with qtbot.waitSignal(orch.terminee, timeout=5000):
            attente["fin"] = True

    def test_terminee_n_est_emis_qu_une_fois_le_fil_arrete(self, qtbot, monkeypatch):
        """CI Linux, 2026-09-24 : le fil annonçait sa fin puis tournait encore ;
        détruit à ce moment-là avec son parent, Qt abandonnait le processus
        (code 134), une exécution sur deux. On élargit ici la fenêtre à 300 ms
        pour que l'ancien code échoue à tous les coups."""
        from src.ui.preparateur_wine import PreparateurWine

        def annonce_puis_traine(self):
            self.preparation_terminee.emit(True, "")
            self.msleep(300)
        monkeypatch.setattr(prep.PreparationWine, "run", annonce_puis_traine)
        orch = PreparateurWine()
        assert orch.demarrer(self._jeu(), [], puis_jouer=False)
        fil = orch._fil
        encore_en_marche = []
        orch.terminee.connect(lambda *_: encore_en_marche.append(fil.isRunning()))
        with qtbot.waitSignal(orch.terminee, timeout=5000):
            pass
        assert encore_en_marche == [False]

    def test_la_fermeture_arrete_le_fil(self, qtbot, monkeypatch):
        """Sans `terminate()` : le fil honore l'interruption à son sondage."""
        from src.ui.preparateur_wine import PreparateurWine

        def jusqu_a_l_interruption(self):
            while not self.isInterruptionRequested():
                self.msleep(10)
            return False, prep.ANNULEE
        monkeypatch.setattr(prep.PreparationWine, "_preparer", jusqu_a_l_interruption)
        orch = PreparateurWine()
        orch.demarrer(self._jeu(), [], puis_jouer=False)
        fil = orch._fil
        orch.shutdown()
        assert not fil.isRunning()
        assert not orch.en_cours

    def test_sans_lanceur_rien_ne_demarre(self, qtbot, sans_lanceur):
        from src.ui.preparateur_wine import PreparateurWine
        assert PreparateurWine().demarrer(self._jeu(), [], puis_jouer=False) is False

    def test_les_messages_de_la_barre_de_statut(self, qtbot, monkeypatch):
        from src.core.i18n import set_language
        from src.ui.preparateur_wine import PreparateurWine
        set_language("fr")
        orch = PreparateurWine()
        vus = []
        orch.message.connect(vus.append)
        orch._famille = "umu"
        orch._on_etape("prefixe", "")
        orch._on_etape("composants", "vcrun2022 vcrun2005")
        assert "Proton" in vus[0], "umu peut télécharger Proton : le dire"
        assert vus[1] == ("Préparation de Wine : installation de "
                          "Visual C++ 2015-2022, Visual C++ 2005…")


class _Vue:
    """Juste ce que les handlers lisent d'une fiche de jeu."""

    def __init__(self, jeu, en_cours=False):
        self.game = jeu
        self.preparation_en_cours = en_cours
        self.journal_preparation = "/tmp/accio/wine-preparation.log"
        self.notes: list[str] = []
        self.notify = SimpleNamespace(emit=self.notes.append)
        self.preparations: list = []
        self.manager = SimpleNamespace(get_game_by_id=lambda gid: jeu if gid == jeu.id else None)

    def preparer_wine(self, jeu, verbes, puis_jouer):
        self.preparations.append((jeu.id, list(verbes), puis_jouer))


def _boite_espion(monkeypatch, reponse):
    from src.ui import game_detail_handlers as gdh
    vus = []

    def boite(icone, vue, titre, texte, choix=(), defaut=0):
        vus.append((titre, texte, choix))
        return reponse
    monkeypatch.setattr(gdh, "_boite", boite)
    return vus


@pytest.fixture
def jeu_hp7a():
    from src.core.game_data import GameData
    return GameData.from_dict({
        "id": "hp7a", "name": "HP7", "year": 2010, "description": "d", "developer": "EA",
        "executable": "HP7/pc/hp7.exe", "cover_image": "c.jpg",
        "requires": ["vcredist2005_x86"], "versions": []})


class TestLesDialogues:
    """Une QUESTION avant de télécharger, une explication après un échec."""

    def test_proposer_dit_ce_qui_va_se_passer(self, monkeypatch, jeu_hp7a):
        from src.core import system_checks
        from src.ui import game_detail_handlers as gdh
        monkeypatch.setattr(sys, "platform", "linux")
        (compat.prefixe("wine") / "winetricks.log").write_text("vcrun2022\n", encoding="utf-8")
        system_checks.invalidate_vcredist_cache()
        vus = _boite_espion(monkeypatch, 0)
        vue = _Vue(jeu_hp7a)
        gdh.proposer_preparation(vue, jeu_hp7a, puis_jouer=True)
        titre, texte, choix = vus[0]
        assert "Microsoft" in texte and "Visual C++ 2005" in texte
        assert vue.preparations == [("hp7a", ["vcrun2005"], True)]

    def test_rien_a_preparer_rien_a_demander(self, monkeypatch, jeu_hp7a):
        from src.ui import game_detail_handlers as gdh
        vus = _boite_espion(monkeypatch, 0)
        gdh.proposer_preparation(_Vue(jeu_hp7a), jeu_hp7a, puis_jouer=True)
        assert not vus

    def test_plus_tard_ne_prepare_rien(self, monkeypatch, jeu_hp7a):
        from src.core import system_checks
        from src.ui import game_detail_handlers as gdh
        monkeypatch.setattr(sys, "platform", "linux")
        (compat.prefixe("wine") / "winetricks.log").write_text("", encoding="utf-8")
        system_checks.invalidate_vcredist_cache()
        _boite_espion(monkeypatch, 1)
        vue = _Vue(jeu_hp7a)
        gdh.proposer_preparation(vue, jeu_hp7a, puis_jouer=True)
        assert vue.preparations == []

    def test_reussite_puis_jouer(self, monkeypatch, jeu_hp7a):
        from src.ui import game_detail_handlers as gdh
        joues = []
        monkeypatch.setattr(gdh, "on_play", lambda vue, **k: joues.append(k))
        gdh.apres_preparation(_Vue(jeu_hp7a), "hp7a", True, "", True)
        assert joues == [{}]

    def test_reussite_sans_jouer_previent(self, monkeypatch, jeu_hp7a):
        from src.ui import game_detail_handlers as gdh
        monkeypatch.setattr(gdh, "on_play", lambda *a, **k: pytest.fail("pas demandé"))
        vue = _Vue(jeu_hp7a)
        gdh.apres_preparation(vue, "hp7a", True, "", False)
        assert len(vue.notes) == 1

    def test_echec_des_composants_propose_de_lancer_quand_meme(self, monkeypatch, jeu_hp7a):
        from src.ui import game_detail_handlers as gdh
        vus = _boite_espion(monkeypatch, 0)
        joues = []
        monkeypatch.setattr(gdh, "on_play", lambda vue, **k: joues.append(k))
        gdh.apres_preparation(_Vue(jeu_hp7a), "hp7a", False, prep.COMPOSANTS, True)
        assert "wine-preparation.log" in vus[0][1]
        assert joues == [{"ignorer_prerequis": True}]

    def test_sans_prefixe_pas_de_lancement_possible(self, monkeypatch, jeu_hp7a):
        from src.ui import game_detail_handlers as gdh
        vus = _boite_espion(monkeypatch, 0)
        monkeypatch.setattr(gdh, "on_play", lambda *a, **k: pytest.fail("rien ne peut démarrer"))
        gdh.apres_preparation(_Vue(jeu_hp7a), "hp7a", False, prep.PREFIXE, True)
        assert vus[0][2] == ()

    def test_une_annulation_n_a_rien_a_dire(self, monkeypatch, jeu_hp7a):
        from src.ui import game_detail_handlers as gdh
        vus = _boite_espion(monkeypatch, 0)
        vue = _Vue(jeu_hp7a)
        gdh.apres_preparation(vue, "hp7a", False, prep.ANNULEE, True)
        assert not vus and not vue.notes

    def test_wine_introuvable_mene_au_guide(self, monkeypatch, jeu_hp7a):
        from src.core.liens import GUIDE_LINUX_URL
        from src.ui import game_detail_handlers as gdh
        vus = _boite_espion(monkeypatch, 0)
        ouverts = []
        monkeypatch.setattr(gdh, "open_url", ouverts.append)
        gdh.signaler_compat_absent(_Vue(jeu_hp7a))
        assert "Bazzite" in vus[0][1] and "umu-launcher" in vus[0][1]
        assert ouverts == [GUIDE_LINUX_URL]

    def test_jouer_pendant_une_preparation(self, monkeypatch, jeu_hp7a):
        from src.ui import game_detail_handlers as gdh
        vue = _Vue(jeu_hp7a, en_cours=True)
        vue.manager.launch_game = lambda *a, **k: pytest.fail("lancé pendant winetricks")
        gdh.on_play(vue)
        assert len(vue.notes) == 1
