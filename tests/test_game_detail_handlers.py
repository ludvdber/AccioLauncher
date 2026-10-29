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
        assert boites and boites[0][0] == "Rien n'a été importé"
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
        assert boites[-1][0] == "Rien n'a été importé"
        assert "n'a pas été déplacé" in boites[-1][1]
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
        assert vue.status_message.recus == ["Le jeu n'a pas démarré. Le journal du launcher dit pourquoi."]
        assert vue.game_launched.recus == []

    def test_une_erreur_inconnue_est_dite(self, tmp_path, boites):
        vue = self._vue_qui_leve(tmp_path, RuntimeError("autre chose"))
        h.on_play(vue)
        assert vue.status_message.recus == ["Le jeu n'a pas démarré. Le journal du launcher dit pourquoi."]

    def test_documents_inaccessible_explique_la_protection(self, tmp_path, boites, monkeypatch):
        monkeypatch.setattr(h.sys, "platform", "win32")
        vue = self._vue_qui_leve(tmp_path, RuntimeError("documents_inutilisable:C:\\Users\\x\\Documents\\HPX"))
        h.on_play(vue)
        assert boites[0][0] == "Dossier Documents inaccessible"
        assert "Accès contrôlé aux dossiers" in boites[0][1]

    def test_aucun_processus_rendu(self, tmp_path, boites):
        vue = _vue(tmp_path, launch_game=lambda *_a, **_k: None)
        h.on_play(vue)
        assert vue.status_message.recus == ["Le jeu n'a pas démarré. Le journal du launcher dit pourquoi."]

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
        assert vue.notify.recus == ["Dossier introuvable : le jeu a peut-être été déplacé."]


class TestTelechargerRefuse:
    """Les cinq raisons de ne PAS lancer un téléchargement, et ce qui est dit."""

    def _version(self, disponible=True):
        return SimpleNamespace(is_available=disponible, size_mb=900)

    def _vue_dl(self, tmp_path, **ops):
        lances = []
        vue = _vue(tmp_path, _jeu(current_download=self._version()), archive_size_mb=lambda v: 700)
        vue._ops = SimpleNamespace(is_busy=False, active_game=None, check_disk_space=lambda v: None,
                                   download=lambda g, v: lances.append((g.id, v)))
        for nom, valeur in ops.items():
            setattr(vue._ops, nom, valeur)
        return vue, lances

    def test_un_autre_jeu_en_cours_un_toast_qui_le_nomme(self, tmp_path):
        vue, lances = self._vue_dl(tmp_path, is_busy=True, active_game=SimpleNamespace(id="hp2", name="HP2"))
        h.on_download(vue)
        assert not lances and "HP2" in vue.notify.recus[0]

    def test_ce_jeu_deja_en_cours(self, tmp_path):
        vue, lances = self._vue_dl(tmp_path, is_busy=True, active_game=SimpleNamespace(id="hpx", name="HPX"))
        h.on_download(vue)
        assert not lances and vue.status_message.recus and not vue.notify.recus

    def test_sans_version(self, tmp_path):
        vue, lances = self._vue_dl(tmp_path)
        vue.game.current_download = None
        h.on_download(vue)
        assert not lances and vue.status_message.recus

    def test_pas_encore_publie_ne_parle_pas_de_connexion(self, tmp_path):
        vue, lances = self._vue_dl(tmp_path)
        h.on_download(vue, self._version(disponible=False))
        assert not lances
        assert "connexion" not in vue.status_message.recus[0].lower()

    def test_place_insuffisante_dit_les_deux_tailles(self, tmp_path):
        vue, lances = self._vue_dl(tmp_path, check_disk_space=lambda v: 300)
        h.on_download(vue)
        assert not lances
        assert "300" in vue.notify.recus[0]

    def test_tout_va_bien_le_telechargement_part(self, tmp_path):
        vue, lances = self._vue_dl(tmp_path)
        h.on_download(vue)
        assert lances == [("hpx", vue.game.current_download)]

    def test_pendant_la_preparation_de_wine_rien_ne_part(self, tmp_path):
        vue, lances = self._vue_dl(tmp_path)
        vue.preparation_en_cours = True
        h.on_download(vue)
        assert not lances and vue.notify.recus


class TestMiseAJourDuJeu:
    def _vue_maj(self, tmp_path):
        changes = []
        ver = SimpleNamespace(version="1.2", changes=["Textures HD", "Correctif son"])
        jeu = _jeu(recommended_version="1.2", get_version=lambda v: ver if v == "1.2" else None)
        vue = _vue(tmp_path, jeu, installed_version=lambda _id: "1.1")
        vue._ops = SimpleNamespace(is_busy=False, switch_version=lambda g, v: changes.append(v.version))
        return vue, changes

    def test_la_question_dit_ce_qui_change(self, tmp_path, boites):
        vue, changes = self._vue_maj(tmp_path)
        boites.repondre(1)
        h.on_update_clicked(vue)
        titre, texte = boites[0]
        assert "v1.1" in texte and "v1.2" in texte and "• Textures HD" in texte
        assert not changes, "« Plus tard » ne change rien"

    def test_accepter_change_de_version(self, tmp_path, boites):
        vue, changes = self._vue_maj(tmp_path)
        boites.repondre(0)
        h.on_update_clicked(vue)
        assert changes == ["1.2"]

    def test_changer_de_version_seulement_pour_le_jeu_affiche(self, tmp_path):
        vue, changes = self._vue_maj(tmp_path)
        h.on_switch_version(vue, "autre", "1.2")
        h.on_switch_version(vue, "hpx", "9.9")
        assert not changes
        h.on_switch_version(vue, "hpx", "1.2")
        assert changes == ["1.2"]


class TestDesinstaller:
    def test_ce_qui_reste_est_dit_avant_le_clic(self, tmp_path, boites):
        retires = []
        jeu = _jeu(sauvegardes=object(), post_install=SimpleNamespace(config_files=["a.ini"]))
        vue = _vue(tmp_path, jeu, uninstall_game=retires.append)
        boites.repondre(1)
        h.on_uninstall(vue)
        assert "sauvegardes et la configuration" in boites[0][1]
        assert not retires
        boites.repondre(0)
        h.on_uninstall(vue)
        assert retires == ["hpx"] and vue.status_message.recus

    @pytest.mark.parametrize("sauv, conf, attendu", [
        (True, False, "sauvegardes sont conservées"),
        (False, True, "configuration du jeu dans Mes Documents"),
        (False, False, ""),
    ])
    def test_chaque_cas(self, sauv, conf, attendu):
        jeu = _jeu(sauvegardes=object() if sauv else None,
                   post_install=SimpleNamespace(config_files=["a"] if conf else []))
        reste = h._ce_qui_reste(jeu)
        assert (attendu in reste) if attendu else reste == ""


class TestApresPreparationWine:
    """Linux : ce qui suit la préparation de Wine, sans composants Windows."""

    @pytest.fixture
    def linux(self, monkeypatch):
        from src.core import composants_windows
        monkeypatch.setattr(composants_windows, "disponible", lambda: False)

    def _vue_wine(self, tmp_path, joues):
        jeu = _jeu()
        vue = _vue(tmp_path, jeu, get_game_by_id=lambda i: jeu if i == "hpx" else None)
        vue.journal_preparation = tmp_path / "wine.log"
        return vue

    def test_reussie_puis_jouer(self, tmp_path, linux, monkeypatch):
        joues = []
        monkeypatch.setattr(h, "on_play", lambda vue, **k: joues.append(k))
        h.apres_preparation(self._vue_wine(tmp_path, joues), "hpx", True, "", puis_jouer=True)
        assert joues == [{}]

    def test_reussie_sans_jouer_un_toast(self, tmp_path, linux):
        vue = self._vue_wine(tmp_path, [])
        h.apres_preparation(vue, "hpx", True, "", puis_jouer=False)
        assert "Wine est prêt" in vue.notify.recus[0]

    def test_prefixe_impossible_donne_le_journal(self, tmp_path, linux, boites):
        from src.core import preparation_wine
        vue = self._vue_wine(tmp_path, [])
        h.apres_preparation(vue, "hpx", False, preparation_wine.PREFIXE, puis_jouer=True)
        assert str(tmp_path / "wine.log") in boites[0][1]

    def test_winetricks_absent_propose_de_lancer_quand_meme(self, tmp_path, linux, boites, monkeypatch):
        from src.core import preparation_wine
        joues = []
        monkeypatch.setattr(h, "on_play", lambda vue, **k: joues.append(k))
        boites.repondre(0)
        h.apres_preparation(self._vue_wine(tmp_path, joues), "hpx", False,
                            preparation_wine.WINETRICKS_ABSENT, puis_jouer=True)
        assert "winetricks" in boites[0][1]
        assert joues == [{"ignorer_prerequis": True}]

    def test_annulee_ne_dit_rien(self, tmp_path, linux, boites):
        from src.core import preparation_wine
        vue = self._vue_wine(tmp_path, [])
        h.apres_preparation(vue, "hpx", False, preparation_wine.ANNULEE, puis_jouer=True)
        assert not boites and not vue.notify.recus


class TestLangueEtActionPrincipale:
    def test_langue_posee_est_enregistree_et_annoncee(self, tmp_path, boites, qapp):
        jeu = _jeu(langues={"en": SimpleNamespace(label="English")})
        enregistres = []
        vue = _vue(tmp_path, jeu=jeu, game_language=lambda _g: "fr",
                   apply_game_language=lambda *_a, **_k: True,
                   set_game_language=lambda *a: enregistres.append(a))
        assert h._appliquer_langue(vue, "en") is True
        assert enregistres == [("hpx", "en")]
        assert vue.notify.recus == ["Langue du jeu : English"] and not boites

    def test_meme_langue_rien(self, tmp_path, qapp):
        jeu = _jeu(langues={"fr": SimpleNamespace(label="Français")})
        vue = _vue(tmp_path, jeu=jeu, game_language=lambda _g: "fr")
        assert h._appliquer_langue(vue, "fr") is False

    def test_une_seule_langue_installee_pas_de_menu(self, tmp_path):
        jeu = _jeu(langues={"fr": SimpleNamespace(label="Français", code="fr")})
        vue = _vue(tmp_path, jeu=jeu, game_language=lambda _g: "fr",
                   langues_disponibles=lambda _g: [jeu.langues["fr"]])
        h.on_language_clicked(vue)
        assert "une seule langue" in vue.notify.recus[0]

    @pytest.mark.parametrize("etat, attendu", [("NOT_INSTALLED", "download"), ("INSTALLED", "play")])
    def test_entree_fait_l_action_du_bouton(self, tmp_path, monkeypatch, etat, attendu):
        from src.core.game_manager import GameState
        faits = []
        monkeypatch.setattr(h, "on_download", lambda v: faits.append("download"))
        monkeypatch.setattr(h, "on_play", lambda v: faits.append("play"))
        vue = _vue(tmp_path, get_state=lambda _id: GameState[etat])
        h.trigger_primary_action(vue)
        assert faits == [attendu]
