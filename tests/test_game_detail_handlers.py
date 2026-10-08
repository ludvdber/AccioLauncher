"""Chemins d'erreur des actions de la fiche (M-15 / ACT-020, audit du 2026-10-07).

`game_detail_handlers.py` n'était couvert qu'à 56 %, et ce qui manquait était
justement ce qui tourne mal : un import de jeu refusé ou impossible à déplacer,
un lancement qui échoue, un réglage qui ne s'écrit pas, un registre qui ne
prend pas. Ces chemins disent quelque chose à la personne ; c'est ce qui est
vérifié ici, avec une vue factice et les boîtes remplacées (rien ne s'ouvre).
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.ui import game_detail_handlers as h


class _Signal:
    def __init__(self):
        self.recus = []

    def emit(self, *args):
        self.recus.append(args if len(args) != 1 else args[0])


def _jeu(**kw):
    base = dict(id="hpx", name="HPX", executable="HPX/System/Game.exe", recommended_version="1.0",
                langues=None, langue_par_fichiers=False, sauvegardes=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _vue(tmp_path, jeu=None, **manager):
    m = SimpleNamespace(config=SimpleNamespace(install_path=tmp_path / "jeux"),
                        redetect_state=lambda _id: None, save_installed_version=lambda _id: None)
    for nom, valeur in manager.items():
        setattr(m, nom, valeur)
    return SimpleNamespace(
        game=jeu or _jeu(), manager=m, _ops=SimpleNamespace(is_busy=False),
        notify=_Signal(), status_message=_Signal(), state_changed=_Signal(),
        game_launched=_Signal(), preparation_en_cours=False,
        partie_en_cours=lambda: None, _stop_video=lambda: None, _refresh=lambda: None,
        set_game=lambda _g: None)


class _Boites(list):
    """Les boîtes montrées, (titre, texte), et la réponse qu'elles rendent."""
    reponse = 0

    def repondre(self, reponse: int) -> None:
        self.reponse = reponse

    def __call__(self, _icone, _vue, titre, texte, choix=(), defaut=0):
        self.append((titre, texte))
        return self.reponse


@pytest.fixture
def boites(monkeypatch):
    """Remplace les boîtes : rien ne s'ouvre."""
    faux = _Boites()
    monkeypatch.setattr(h, "_boite", faux)
    return faux


class _FauxDialogue:
    choisi = ""

    @classmethod
    def getExistingDirectory(cls, *_a, **_k):
        return cls.choisi


@pytest.fixture
def dialogue(monkeypatch):
    monkeypatch.setattr(h, "QFileDialog", _FauxDialogue)
    return _FauxDialogue


class TestImportDUnJeuExistant:
    def _source(self, tmp_path):
        source = tmp_path / "ancien" / "HPX"
        (source / "System").mkdir(parents=True)
        (source / "System" / "Game.exe").write_bytes(b"MZ")
        return source

    def test_un_dossier_sans_executable_est_refuse(self, tmp_path, boites, dialogue):
        dialogue.choisi = str(tmp_path / "vide")
        (tmp_path / "vide").mkdir()
        h.on_import_existing(_vue(tmp_path))
        assert boites and boites[0][0] == "Import impossible"
        assert "introuvable" in boites[0][1]

    def test_annuler_ne_deplace_rien(self, tmp_path, boites, dialogue):
        source = self._source(tmp_path)
        dialogue.choisi = str(source)
        boites.repondre(1)
        h.on_import_existing(_vue(tmp_path))
        assert source.is_dir()

    def test_un_deplacement_impossible_est_dit(self, tmp_path, boites, dialogue, monkeypatch):
        source = self._source(tmp_path)
        dialogue.choisi = str(source)

        def refuser(self, _cible):
            raise PermissionError(5, "Accès refusé")
        monkeypatch.setattr(Path, "rename", refuser)
        vue = _vue(tmp_path)
        h.on_import_existing(vue)
        assert boites[-1][0] == "Import impossible"
        assert "Déplacement impossible" in boites[-1][1]
        assert vue.status_message.recus == [], "rien ne doit s'annoncer importé"

    def test_l_import_reussi_deplace_et_l_annonce(self, tmp_path, boites, dialogue):
        source = self._source(tmp_path)
        dialogue.choisi = str(source)
        vue = _vue(tmp_path)
        h.on_import_existing(vue)
        assert (tmp_path / "jeux" / "HPX" / "System" / "Game.exe").exists()
        assert vue.status_message.recus == ["HPX importé avec succès !"]


class TestRemettreLaConfiguration:
    def test_refusee_pendant_une_partie(self, tmp_path, boites):
        vue = _vue(tmp_path)
        vue.partie_en_cours = lambda: "HPX"
        h._remettre_la_configuration(vue, vue.game)
        assert vue.notify.recus == ["Fermez HPX avant de remettre sa configuration."]
        assert boites == []

    def test_les_fichiers_non_remis_sont_nommes(self, tmp_path, boites, monkeypatch):
        monkeypatch.setattr(h.reparation_config, "remettre",
                            lambda _g, _p: SimpleNamespace(echoues=["HP.ini", "User.ini"]))
        vue = _vue(tmp_path)
        h._remettre_la_configuration(vue, vue.game)
        assert boites[0][0] == "Configuration non remise"
        assert "HP.ini\nUser.ini" in boites[0][1]
        assert vue.notify.recus == []

    def test_reussie(self, tmp_path, boites, monkeypatch):
        monkeypatch.setattr(h.reparation_config, "remettre",
                            lambda _g, _p: SimpleNamespace(echoues=[]))
        vue = _vue(tmp_path)
        h._remettre_la_configuration(vue, vue.game)
        assert vue.notify.recus == ["Configuration de HPX remise."]


class TestReessayerPlusBas:
    REGLAGE = SimpleNamespace(cle="MSAA", ident="graph_antialiasing")

    def test_un_fichier_non_ecrit_ne_relance_pas_le_jeu(self, tmp_path, boites, monkeypatch):
        def echec(*_a):
            raise OSError("verrouillé")
        monkeypatch.setattr(h.reglages_graphiques, "ecrire", echec)
        lances = []
        monkeypatch.setattr(h, "on_play", lances.append)
        vue = _vue(tmp_path)
        h._reessayer_plus_bas(vue, vue.game, tmp_path / "x.conf", self.REGLAGE, "4x")
        assert boites[0][0] == "Réglage non changé"
        assert lances == []

    def test_un_autre_jeu_affiche_recoit_un_toast(self, tmp_path, boites, monkeypatch):
        monkeypatch.setattr(h.reglages_graphiques, "ecrire", lambda *_a: None)
        lances = []
        monkeypatch.setattr(h, "on_play", lances.append)
        vue = _vue(tmp_path, jeu=_jeu(id="autre"))
        h._reessayer_plus_bas(vue, _jeu(), tmp_path / "x.conf", self.REGLAGE, "4x")
        assert lances == []
        assert vue.notify.recus == ["Réglage changé : relancez HPX."]


class TestLancementQuiEchoue:
    def _vue_qui_leve(self, tmp_path, exc):
        def lancer(*_a, **_k):
            raise exc
        return _vue(tmp_path, launch_game=lancer)

    def test_une_erreur_systeme_est_dite(self, tmp_path, boites):
        vue = self._vue_qui_leve(tmp_path, OSError("exe introuvable"))
        h.on_play(vue)
        assert vue.status_message.recus == ["Impossible de lancer le jeu."]
        assert vue.game_launched.recus == []

    def test_une_erreur_inconnue_est_dite(self, tmp_path, boites):
        vue = self._vue_qui_leve(tmp_path, RuntimeError("autre chose"))
        h.on_play(vue)
        assert vue.status_message.recus == ["Impossible de lancer le jeu."]

    def test_documents_inaccessible_explique_la_protection(self, tmp_path, boites, monkeypatch):
        monkeypatch.setattr(h.sys, "platform", "win32")
        vue = self._vue_qui_leve(tmp_path, RuntimeError("documents_inutilisable:C:\\Users\\x\\Documents\\HPX"))
        h.on_play(vue)
        assert boites[0][0] == "Dossier Documents inaccessible"
        assert "Accès contrôlé aux dossiers" in boites[0][1]

    def test_aucun_processus_rendu(self, tmp_path, boites):
        vue = _vue(tmp_path, launch_game=lambda *_a, **_k: None)
        h.on_play(vue)
        assert vue.status_message.recus == ["Impossible de lancer le jeu."]

    def test_une_partie_deja_en_cours_ne_relance_rien(self, tmp_path, boites):
        appels = []
        vue = _vue(tmp_path, launch_game=lambda *a, **k: appels.append(a))
        vue.partie_en_cours = lambda: "HPX"
        h.on_play(vue)
        assert appels == []
        assert vue.notify.recus == ["HPX est en train de démarrer ou déjà lancé."]


class TestRegistreQuiNePrendPas:
    def test_manette_echec_reel_dit_quoi_faire(self, tmp_path, boites, monkeypatch):
        monkeypatch.setattr(h.manette, "activer", lambda *_a, **_k: False)
        vue = _vue(tmp_path)
        assert h._appliquer_manette(vue, vue.game, True) is False
        assert vue.notify.recus == ["Le registre n'a pas pu être modifié : réglez la manette "
                                    "dans les options du jeu."]

    def test_manette_refusee_ne_reproche_rien(self, tmp_path, boites, monkeypatch):
        def activer(_g, _oui, confirmer):
            confirmer("HKCU", "Software\\HPX", {"Joystick": 1})
            return False
        monkeypatch.setattr(h.manette, "activer", activer)
        boites.repondre(1)            # « Annuler »
        vue = _vue(tmp_path)
        h._appliquer_manette(vue, vue.game, True)
        assert vue.notify.recus == []

    def test_langue_non_ecrite_est_une_boite(self, tmp_path, boites, monkeypatch, qapp):
        monkeypatch.setattr(h.sys, "platform", "win32")
        jeu = _jeu(langues={"en": SimpleNamespace(label="English")})
        enregistres = []
        vue = _vue(tmp_path, jeu=jeu, game_language=lambda _g: "fr",
                   apply_game_language=lambda *_a, **_k: False,
                   set_game_language=lambda *a: enregistres.append(a))
        assert h._appliquer_langue(vue, "en") is False
        assert boites[0][0] == "Langue du jeu"
        assert "autorisation administrateur" in boites[0][1]
        assert enregistres == [], "un choix que le registre n'a pas pris ne s'enregistre pas"

    def test_dossier_du_jeu_introuvable(self, tmp_path):
        vue = _vue(tmp_path)
        h._ouvrir_dossier_du_jeu(vue, vue.game)
        assert vue.notify.recus == ["Dossier introuvable — le jeu a peut-être été déplacé."]
