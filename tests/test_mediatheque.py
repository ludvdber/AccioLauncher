"""La Médiathèque : cinématiques, crédits, enregistrement d'un morceau, page et barre du bas."""

import json

import pytest

from src.core import cinematiques, discographie, phonographe


# ─── Cœur ───

class TestCinematiques:
    def test_lit_le_fichier_et_ignore_les_entrees_abimees(self, tmp_path):
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({"jeux": {
            "hp3": {"dossier": "Movies", "ext": ".BIK", "clips": [
                {"f": "LupinWolf", "t": "Lupin", "s": 93}, {"f": 3, "t": "x", "s": 0}]},
            "hp7": {"dossier": "pc", "ext": ".vp6", "sans_son": True, "clips": []},
            "casse": {"ext": ".bik", "clips": []},
        }}), encoding="utf-8")
        lu = cinematiques.charger(chemin)
        assert set(lu) == {"hp3", "hp7"}
        assert lu["hp3"].extension == ".bik"
        assert lu["hp3"].clips == (cinematiques.Cinematique("LupinWolf", "Lupin", 93),)
        assert lu["hp7"].sans_son and not lu["hp3"].sans_son

    def test_illisible_rend_vide(self, tmp_path):
        assert cinematiques.charger(tmp_path / "absent.json") == {}

    def test_presentes_casse_ignoree_et_logos_passes(self, tmp_path):
        """« Passer les logos » renomme en `.bik.off` : la cinématique reste là."""
        films = tmp_path / "movies"
        films.mkdir()
        (films / "LUPINWOLF.bik").write_bytes(b"BIKi")
        (films / "KWLogo.bik.off").write_bytes(b"BIKi")
        collection = cinematiques.Collection("Movies", ".bik", False, (
            cinematiques.Cinematique("LupinWolf", "Lupin", 0),
            cinematiques.Cinematique("KWLogo", "Logo", 0),
            cinematiques.Cinematique("Absente", "Rien", 0)))
        trouvees = cinematiques.presentes(collection, tmp_path)
        assert set(trouvees) == {"LupinWolf", "KWLogo"}
        assert cinematiques.presentes(collection, None) == {}

    def test_donnees_embarquees(self):
        """Le fichier livré : HP3 à HP8 (hp7a, hp7b), et rien pour HP1 et HP2 (moteur seul)."""
        lu = cinematiques.charger()
        assert {"hp3", "hp4", "hp5", "hp6", "hp7a", "hp7b"} <= set(lu)
        assert "hp1" not in lu and "hp2" not in lu
        assert lu["hp7a"].sans_son and lu["hp7b"].sans_son and lu["hp4"].voix
        # HP5 et HP6 : la banque compte un nom par flux (12 chacune, relevé sur les jeux).
        for jeu in ("hp5", "hp6"):
            banque = lu[jeu].banque
            assert banque is not None and len(banque.ordre) == 12 and "fr" in banque.fichiers
        assert {"ns01", "ns02", "ns08", "ns09", "ns14", "ns15", "pensieve"} <= set(lu["hp6"].banque.ordre)
        assert all(c.titre for col in lu.values() for c in col.clips)
        # Hors HP3 et HP4 (logos, prénoms), chaque titre a son anglais et son espagnol.
        neutres = {"Bellatrix", "Harry", "Hermione", "Ron"}
        for col in lu.values():
            for c in col.clips:
                if c.titres not in neutres:
                    assert isinstance(c.titres, tuple) and {"fr", "en", "es"} <= dict(c.titres).keys(), c.fichier


class TestCredits:
    def test_un_credit_par_jeu(self):
        credits = discographie.charger_credits()
        assert {j: (c.compositeur, c.annee) for j, c in credits.items()} == {
            "hp1": ("Jeremy Soule", 2001), "hp2": ("Jeremy Soule", 2002),
            "hp3": ("Jeremy Soule", 2004), "hp4": ("Jeremy Soule", 2005),
            "hp5": ("James Hannigan", 2007), "hp6": ("James Hannigan", 2009),
            "hp7a": ("James Hannigan", 2010), "hp7b": ("James Hannigan", 2011)}

    def test_illisible_rend_vide(self, tmp_path):
        assert discographie.charger_credits(tmp_path / "absent.json") == {}


class TestSeuil:
    def test_une_sauvegarde_au_seuil_suffit(self):
        assert discographie.ouvert_au_seuil(0, None)
        assert not discographie.ouvert_au_seuil(30, None)
        assert discographie.ouvert_au_seuil(30, 30)
        assert not discographie.ouvert_au_seuil(93, 74)
        assert discographie.ouvert_au_seuil(93, 75)


class TestEnregistrer:
    def test_nom_de_fichier(self):
        assert phonographe.nom_de_fichier('Crabbe: "Goyle"?') == "Crabbe- -Goyle--"
        assert phonographe.nom_de_fichier("  ...  ") == "Morceau"

    def test_copie_sous_le_titre(self, tmp_path):
        source = tmp_path / "Common_Room.mp2"
        source.write_bytes(b"x" * 10)
        cible = phonographe.exporter(source, "Common Room", tmp_path / "Musique" / "HP1")
        assert cible == tmp_path / "Musique" / "HP1" / "Common Room.mp2"
        assert cible.read_bytes() == b"x" * 10

    def test_deja_enregistre_ne_double_pas(self, tmp_path):
        source = tmp_path / "a.ogg"
        source.write_bytes(b"abc")
        dossier = tmp_path / "out"
        premier = phonographe.exporter(source, "A", dossier)
        assert phonographe.exporter(source, "A", dossier) == premier
        assert len(list(dossier.iterdir())) == 1

    def test_n_ecrase_jamais_un_autre_fichier(self, tmp_path):
        dossier = tmp_path / "out"
        dossier.mkdir()
        (dossier / "A.ogg").write_bytes(b"autre chose, plus long")
        source = tmp_path / "a.ogg"
        source.write_bytes(b"abc")
        cible = phonographe.exporter(source, "A", dossier)
        assert cible == dossier / "A (2).ogg"
        assert (dossier / "A.ogg").read_bytes() == b"autre chose, plus long"

    def test_source_absente_rend_none(self, tmp_path):
        assert phonographe.exporter(tmp_path / "absent.ogg", "A", tmp_path / "out") is None


# ─── Le lecteur de fond (sans rien jouer : aucun fichier n'est trouvé) ───

@pytest.fixture
def fond(qtbot, tmp_path):
    from PyQt6.QtWidgets import QWidget
    from src.core.config import Config
    from src.ui.fond_sonore import FondSonore
    fenetre = QWidget()
    qtbot.addWidget(fenetre)
    config = Config(install_path=tmp_path, musique_fond="hp2/Greenhouse")
    return FondSonore(config, lambda _jeu: None, lambda: tmp_path, fenetre)


class TestFondSonore:
    def test_la_platine_montre_le_fond_puis_l_ecoute(self, fond):
        assert fond.morceau == "hp2/Greenhouse"
        fond.ecouter("hp1/Common_Room")
        assert fond.morceau == "hp1/Common_Room"
        fond.arreter_ecoute()
        assert fond.morceau == "hp2/Greenhouse"

    def test_pause_sur_place(self, fond):
        fond.ecouter("hp1/Common_Room")
        fond.basculer_pause()
        assert fond.en_pause and fond._voulu() == ""
        fond.basculer_pause()
        assert not fond.en_pause and fond._voulu() == "hp1/Common_Room"

    def test_une_cinematique_fait_taire_meme_l_ecoute(self, fond):
        from src.ui.fond_sonore import CINEMATIQUE
        fond.ecouter("hp1/Common_Room")
        fond.suspendre(CINEMATIQUE)
        assert fond._voulu() == ""
        fond.reprendre(CINEMATIQUE)
        assert fond._voulu() == "hp1/Common_Room"

    def test_le_volume_ne_s_ecrit_qu_au_lacher(self, fond):
        from src.core import config
        fichier = config.CONFIG_FILE_PATH       # redirigé par la garde de conftest
        fond.regler_volume(60, enregistrer=False)
        assert fond._config.volume_musique == 60 and not fichier.exists()
        fond.regler_volume(150)
        assert fond._config.volume_musique == 100
        assert json.loads(fichier.read_text(encoding="utf-8"))["volume_musique"] == 100


# ─── La page et la barre du bas, dans une vraie fenêtre ───

@pytest.fixture
def fenetre_avec_jeux(make_window, monkeypatch, tmp_path):
    """HP2 installé avec deux morceaux, HP3 avec deux cinématiques ; aucune partie."""
    from src.core.game_manager import GameManager, GameState
    jeux = tmp_path / "copies"
    (jeux / "hp2" / "Music").mkdir(parents=True)
    morceaux = discographie.charger()["hp2"]
    for m in morceaux[:2]:
        (jeux / "hp2" / "Music" / f"{m.fichier}.ogg").write_bytes(b"OggS")
    (jeux / "hp3" / "Movies").mkdir(parents=True)
    (jeux / "hp3" / "Movies" / "SiriusPhoto.bik").write_bytes(b"BIKi")
    (jeux / "hp3" / "Movies" / "LupinWolf.bik").write_bytes(b"BIKi")
    monkeypatch.setattr(GameManager, "is_installed", lambda self, j: j in {"hp2", "hp3"})
    monkeypatch.setattr(GameManager, "get_state", lambda self, j: GameState.INSTALLED
                        if j in {"hp2", "hp3"} else GameState.NOT_INSTALLED)
    monkeypatch.setattr(GameManager, "get_game_path", lambda self, j: jeux / j)
    monkeypatch.setattr("src.core.discographie.avancement", lambda jeu, spec: None)
    # Collection fabriquée (règle 78) : un clip ouvert d'office, un au seuil de 93 %.
    collection = cinematiques.Collection("Movies", ".bik", False, (
        cinematiques.Cinematique("SiriusPhoto", "La photo de Sirius", 0),
        cinematiques.Cinematique("LupinWolf", "Lupin", 93)))
    monkeypatch.setattr(cinematiques, "charger", lambda chemin=None: {"hp3": collection})
    return make_window()


class TestPage:
    def test_onglet_et_mini_lecteur(self, make_window):
        from src.ui.title_bar import COLLECTIONS
        win = make_window()
        assert win._title_bar.onglet(COLLECTIONS).isVisibleTo(win._title_bar)
        assert win._mediatheque.mini.parent() is not None

    def test_ouverte_sans_jeu_installe(self, make_window):
        from src.ui.mediatheque_page import MediathequePage
        from src.ui.title_bar import COLLECTIONS
        win = make_window()
        win._on_onglet(COLLECTIONS)
        page = win._pages.page
        assert isinstance(page, MediathequePage)
        assert win._title_bar.onglet(COLLECTIONS).isChecked()
        page.accept()
        assert win._pages.page is None

    def test_morceaux_ouverts_fermes_et_nouveaux(self, fenetre_avec_jeux, qtbot):
        from src.ui.mediatheque_page import _LigneMorceau
        from src.ui.title_bar import COLLECTIONS
        win = fenetre_avec_jeux
        onglet = win._title_bar.onglet(COLLECTIONS)
        # Les sauvegardes se lisent juste après l'ouverture de la fenêtre.
        qtbot.waitUntil(lambda: onglet.pastille, timeout=5000)
        win._mediatheque.ouvrir("musique", "hp2")
        page = win._pages.page
        hp2 = discographie.charger()["hp2"]
        # Bâtie par paquets : les premières rangées tout de suite, le reste ensuite.
        assert 0 < len(page.findChildren(_LigneMorceau)) < len(hp2)
        qtbot.waitUntil(lambda: len(page.findChildren(_LigneMorceau)) == len(hp2), timeout=5000)
        lignes = page.findChildren(_LigneMorceau)
        ouvertes = [ligne for ligne in lignes if ligne._ecouter is not None]
        assert len(ouvertes) == sum(m.seuil == 0 for m in hp2)
        # Montrés une fois : vus. Les cinématiques, bâties mais pas regardées, restent nouvelles.
        assert not win._mediatheque.nouveaux("hp2", "musique")
        assert win._mediatheque.nouveaux("hp3", "cinematiques") == {"SiriusPhoto"}
        page.rubrique("cinematiques")
        assert page.jeu == "hp2", "le jeu choisi en haut vaut pour les deux rubriques"
        page.montrer("hp3")
        assert not win._mediatheque.nouveaux("hp3", "cinematiques")
        win._mediatheque.ouvrir("musique", "hp3")
        assert not onglet.pastille, "tout a été vu : le point or s'éteint"

    def test_cinematiques_et_seuils(self, fenetre_avec_jeux, qtbot):
        from src.ui.mediatheque_page import _LigneCine
        win = fenetre_avec_jeux
        win._mediatheque.ouvrir("cinematiques", "hp3")
        page = win._pages.page
        assert page.rubrique_courante == "cinematiques"
        qtbot.waitUntil(lambda: len(page.findChildren(_LigneCine)) == 2, timeout=5000)
        lignes = {ligne.fichier: ligne for ligne in page.findChildren(_LigneCine)}
        assert set(lignes) == {"SiriusPhoto", "LupinWolf"}
        assert lignes["SiriusPhoto"]._voir is not None     # seuil 0
        assert lignes["LupinWolf"]._voir is None           # la fin de l'histoire, sans partie lue

    def test_le_lien_de_la_fiche_ouvre_le_jeu(self, fenetre_avec_jeux):
        win = fenetre_avec_jeux
        win._detail.mediatheque_demandee.emit("hp2")
        page = win._pages.page
        assert page.jeu == "hp2"

    def test_couper_le_son_apres_la_page_ne_plante_pas(self, fenetre_avec_jeux):
        """La page fermée restait branchée au lecteur : couper le son repeignait un disque détruit."""
        import gc
        win = fenetre_avec_jeux
        win._mediatheque.ouvrir("musique", "hp2")
        win._pages.page.accept()
        gc.collect()
        win._mediatheque.mini._son.click()
        win._mediatheque.mini._son.click()

    def test_quitter_la_page_rend_le_fond_sonore(self, fenetre_avec_jeux):
        win = fenetre_avec_jeux
        fond = win._mediatheque.fond
        fond.choisir_fond("hp2/" + discographie.charger()["hp2"][0].fichier)
        win._mediatheque.ouvrir("musique", "hp2")
        fond.ecouter("hp2/" + discographie.charger()["hp2"][1].fichier)
        win._pages.page.accept()
        assert fond.morceau == fond.fond

    def test_le_haut_parleur_coupe_tout(self, fenetre_avec_jeux):
        win = fenetre_avec_jeux
        mini = win._mediatheque.mini
        assert not win.config.son_coupe
        mini._son.click()
        assert win.config.son_coupe and mini._son.property("coupe")
        mini._son.click()
        assert not win.config.son_coupe


class TestLectureCinematique:
    """Le parcours d'une cinématique dans la vraie page : la musique se tait,
    la voix est prête AVANT l'image, la narration finit sa phrase, la musique revient."""

    @pytest.fixture
    def vue(self, fenetre_avec_jeux, qtbot, monkeypatch, tmp_path):
        win = fenetre_avec_jeux
        win._mediatheque.ouvrir("cinematiques", "hp3")
        vue = win._pages.page._cinematiques
        ordre = []
        video = tmp_path / "v.bik"
        video.write_bytes(b"BIKi")
        monkeypatch.setattr(win._mediatheque, "video", lambda j, f: ordre.append("video") or video)
        monkeypatch.setattr(win._mediatheque, "voix",
                            lambda j, f: ordre.append("voix") or None)
        monkeypatch.setattr(vue._video, "play",
                            lambda chemin, muted, volume: ordre.append("play") or True)
        return win, vue, ordre

    def test_la_voix_est_prete_avant_l_image(self, vue):
        win, page, ordre = vue
        page.jouer("hp3", "SiriusPhoto", "La photo de Sirius")
        assert ordre.index("voix") < ordre.index("play")
        assert "cinematique" in win._mediatheque.fond._raisons, "la musique se tait"
        assert page._courante == "SiriusPhoto" and page._stop.isEnabled()

    def test_une_cinematique_rend_le_son_et_suit_le_haut_parleur(self, vue):
        """Le son coupé du launcher rendait la cinématique muette (Ludo, 2026-10-27)."""
        win, page, _ordre = vue
        win._mediatheque.fond.basculer_son()
        assert win.config.son_coupe
        page.jouer("hp3", "SiriusPhoto", "La photo de Sirius")
        assert not win.config.son_coupe
        win._mediatheque.mini._son.click()
        assert page._video.muted, "couper pendant la lecture coupe la cinématique"
        win._mediatheque.mini._son.click()
        assert not page._video.muted

    def test_arreter_rend_la_musique(self, vue):
        win, page, _ordre = vue
        page.jouer("hp3", "SiriusPhoto", "La photo de Sirius")
        page.arreter()
        assert "cinematique" not in win._mediatheque.fond._raisons
        assert not page._courante and not page._stop.isEnabled()

    def test_une_video_illisible_le_dit_et_ne_coupe_rien(self, vue, monkeypatch):
        win, page, _ordre = vue
        monkeypatch.setattr(win._mediatheque, "video", lambda j, f: None)
        page.jouer("hp3", "SiriusPhoto", "x")
        assert "n'a pas pu être lue" in page._note.text()
        assert "cinematique" not in win._mediatheque.fond._raisons

    def test_un_lecteur_qui_refuse_rend_la_musique(self, vue, monkeypatch):
        win, page, _ordre = vue
        monkeypatch.setattr(page._video, "play", lambda chemin, muted, volume: False)
        page.jouer("hp3", "SiriusPhoto", "x")
        assert "cinematique" not in win._mediatheque.fond._raisons
        assert not page._courante

    def test_la_narration_finit_sa_phrase(self, vue, monkeypatch):
        """DL03 : 85 s de voix pour 64 s d'image. La fin de l'image n'arrête pas la voix."""
        from src.ui.fond_sonore import MULTIMEDIA_DISPONIBLE, QMediaPlayer
        if not MULTIMEDIA_DISPONIBLE:
            # Runner Ubuntu sans libpulse : QtMultimedia ne se charge pas, la page
            # ne crée alors aucune voix, il n'y a rien à attendre.
            pytest.skip("QtMultimedia absent de cette machine")
        win, page, _ordre = vue
        page.jouer("hp3", "SiriusPhoto", "x")

        class VoixQuiParle:
            def playbackState(self):
                return QMediaPlayer.PlaybackState.PlayingState

            def stop(self):
                pass

            def setSource(self, _s):
                pass

            def deleteLater(self):
                pass
        page._voix = VoixQuiParle()
        page._video_finie()
        assert page._courante == "SiriusPhoto", "la voix parle encore : on attend"
        # L'image est finie : `is_playing` lit `_player`. Posé sur l'INSTANCE, jamais
        # une property sur la classe d'un QObject (règle 12).
        monkeypatch.setattr(page._video, "_player", None)
        page._statut_voix(QMediaPlayer.MediaStatus.EndOfMedia)
        assert not page._courante
        assert "cinematique" not in win._mediatheque.fond._raisons

    def test_quitter_la_rubrique_arrete_tout(self, vue):
        win, page, _ordre = vue
        page.jouer("hp3", "SiriusPhoto", "x")
        win._pages.page.rubrique("musique")
        assert not page._courante
        assert "cinematique" not in win._mediatheque.fond._raisons

    def test_le_plein_ecran_suit_le_lecteur_et_se_ferme_a_la_fin(self, vue, qtbot, monkeypatch):
        """Demandé par Ludo le 2026-10-27 : la même lecture sur tout l'écran,
        Espace pour la pause, Échap pour revenir, refermé quand tout s'arrête."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QImage

        from src.ui import cinema_plein_ecran
        from src.ui.cinema_plein_ecran import SAUT_MS
        _win, page, _ordre = vue
        assert not page._plein.isEnabled(), "rien à montrer sans cinématique"
        page.jouer("hp3", "SiriusPhoto", "x")
        assert page._plein.isEnabled()
        # Pas de vrai plein écran dans un test : une fenêtre ordinaire suffit.
        monkeypatch.setattr(cinema_plein_ecran.PleinEcran, "ouvrir", lambda self, voisin: self.show())
        page._plein.click()
        plein = page._plein_ecran
        assert plein is not None
        image = QImage(32, 18, QImage.Format.Format_RGB32)
        page._video.video_frame.emit(image)
        assert plein._image is image, "les images du lecteur arrivent au plein écran"
        pauses, sauts = [], []
        monkeypatch.setattr(page, "_aller_a", sauts.append)
        plein.pause_demandee.disconnect()
        plein.pause_demandee.connect(lambda: pauses.append(1))
        qtbot.keyClick(plein, Qt.Key.Key_Space)
        qtbot.keyClick(plein, Qt.Key.Key_Right)
        assert pauses == [1] and sauts == [SAUT_MS]
        qtbot.keyClick(plein, Qt.Key.Key_Escape)
        assert page._plein_ecran is None
        page._plein.click()
        assert page._plein_ecran is not None
        page.arreter()
        assert page._plein_ecran is None, "la fin de la cinématique ramène à la page"

    def test_la_barre_prend_la_plus_longue_des_deux_pistes(self, vue):
        _win, page, _ordre = vue
        page.jouer("hp3", "SiriusPhoto", "x")
        assert not page._position.maximum()
        page._allonger(26_490)                     # l'image de ns11
        page._allonger_voix(33_000)                # sa voix, plus longue
        page._allonger(26_490)
        assert page._position.maximum() == 33_000
        assert page._temps.text() == "0:00 / 0:33"
        page.arreter()
        assert not page._position.maximum() and not page._temps.text()
        assert not page._position.isEnabled()

    def test_revenir_en_arriere_relance_l_image_finie(self, vue, monkeypatch):
        _win, page, ordre = vue
        page.jouer("hp3", "SiriusPhoto", "x")
        page._allonger(20_000)
        relances = []
        monkeypatch.setattr(page._video, "play",
                            lambda chemin, muted, volume, debut_ms=0: relances.append(debut_ms) or True)
        page._aller_a(5_000)                       # l'image n'est plus là (`_player` vide)
        assert relances == [5_000]
        page._aller_a(25_000)                      # au-delà de l'image : rien à relancer
        assert relances == [5_000]

    def test_enregistrer_copie_la_video_et_sa_voix(self, vue, monkeypatch, tmp_path):
        from PyQt6.QtWidgets import QFileDialog
        win, page, _ordre = vue
        voix = tmp_path / "voix.wav"
        voix.write_bytes(b"RIFF")
        monkeypatch.setattr(win._mediatheque, "voix", lambda j, f: voix)
        page.jouer("hp3", "SiriusPhoto", "La photo : Sirius ?")
        sortie = tmp_path / "sortie"
        sortie.mkdir()
        demande = []
        monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(
            lambda _p, _t, depart: demande.append(depart) or (str(sortie / "Sirius"), "")))
        page._enregistrer_copie()
        assert ":" not in demande[0].split("\\")[-1].split("/")[-1].replace("Sirius ?", "")
        assert (sortie / "Sirius.bik").read_bytes() == b"BIKi"
        assert (sortie / "Sirius.wav").read_bytes() == b"RIFF"
        assert "Sirius.wav" in page._note.text()

    def test_enregistrer_annule_ne_copie_rien(self, vue, monkeypatch, tmp_path):
        from PyQt6.QtWidgets import QFileDialog
        _win, page, _ordre = vue
        page.jouer("hp3", "SiriusPhoto", "x")
        monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *_a: ("", "")))
        page._enregistrer_copie()
        assert page._note.text() != "" and "Enregistrée" not in page._note.text()


class TestAidesDuLecteur:
    def test_minutes(self):
        from src.ui.mediatheque_page import _minutes
        assert _minutes(0) == "0:00"
        assert _minutes(65_400) == "1:05"
        assert _minutes(-5) == "0:00"

    def test_nom_de_fichier_sur(self):
        from src.ui.mediatheque_page import _nom_de_fichier
        assert _nom_de_fichier('HP6 - Le vrai souvenir : les Horcruxes?') == "HP6 - Le vrai souvenir _ les Horcruxes_"
        assert _nom_de_fichier(" ... ") == "cinematique"


class TestCommandesMusique:
    @pytest.fixture
    def vue(self, fenetre_avec_jeux, monkeypatch):
        win = fenetre_avec_jeux
        win._mediatheque.ouvrir("musique", "hp2")
        monkeypatch.setattr(win._mediatheque, "ouvert", lambda jeu, seuil: True)
        cles = [f"hp2/{m.fichier}" for m in discographie.charger()["hp2"]]
        return win, win._pages.page._musique, win._mediatheque.fond, cles

    def test_suivant_et_precedent_font_le_tour(self, vue):
        _win, page, fond, cles = vue
        page._sauter(1)
        assert fond.morceau == cles[0], "rien en cours : suivant = le premier"
        page._sauter(-1)
        assert fond.morceau == cles[-1], "précédent depuis le premier : le dernier"
        page._sauter(1)
        assert fond.morceau == cles[0]

    def test_le_bouton_fond_pose_puis_retire(self, vue):
        _win, page, fond, cles = vue
        page._basculer_fond()
        assert fond.fond == "", "rien en cours : rien à poser"
        fond.ecouter(cles[1])
        page._basculer_fond()
        assert fond.fond == cles[1]
        page._basculer_fond()
        assert fond.fond == ""

    def test_enregistrer_dit_ou_ou_dit_l_echec(self, vue, monkeypatch, tmp_path):
        win, page, _fond, cles = vue
        monkeypatch.setattr(win._mediatheque, "enregistrer", lambda c: tmp_path / "HP2" / "a.ogg")
        page.enregistrer(cles[0])
        assert str(tmp_path / "HP2") in page._confirmation.text()
        assert page._ouvrir_dossier.isVisibleTo(page)
        monkeypatch.setattr(win._mediatheque, "enregistrer", lambda c: None)
        page.enregistrer(cles[0])
        assert "n'a pas pu" in page._confirmation.text()
        assert not page._ouvrir_dossier.isVisibleTo(page)


class TestVgmstreamALaDemande:
    """1.3.1 : HP5 et HP6 sans vgmstream montrent son poids et un bouton, pas une liste muette."""

    def test_le_bouton_dit_le_poids_puis_la_liste_revient(self, fenetre_avec_jeux, monkeypatch):
        from src.core.i18n import tr
        win = fenetre_avec_jeux
        win._mediatheque.ouvrir("musique", "hp2")
        page = win._pages.page._musique
        attend = {"oui": True}
        monkeypatch.setattr(win._mediatheque, "attend_vgmstream", lambda jeu: attend["oui"])
        lances = []
        monkeypatch.setattr(win._mediatheque.vgmstream, "lancer", lambda: lances.append(1))
        page.montrer("hp2")
        assert page._bouton_lecteur.isVisibleTo(page) and not page._carte.isVisibleTo(page)
        assert page._bouton_lecteur.text() == tr("Télécharger ({})").format("4,3 " + tr("Mo"))
        page._bouton_lecteur.click()
        assert lances == [1] and not page._bouton_lecteur.isEnabled()
        win._mediatheque.vgmstream.progression.emit(42)
        assert "42" in page._bouton_lecteur.text()
        win._mediatheque.vgmstream.termine.emit(False)
        assert page._bouton_lecteur.isEnabled() and "connexion" in page._vide.text()
        attend["oui"] = False
        win._mediatheque.vgmstream.termine.emit(True)
        assert not page._bouton_lecteur.isVisibleTo(page) and page._carte.isVisibleTo(page)


class TestChangerDeJeuViteNeMelangeRien:
    def test_les_rangees_du_jeu_precedent_ne_restent_pas_peintes(self, fenetre_avec_jeux, qtbot):
        """Vu à l'audit du 2026-10-24 : les listes de trois jeux peintes les
        unes sur les autres, les anciennes rangées encore visibles en attendant
        leur destruction différée."""
        from src.ui.mediatheque_page import _LigneMorceau
        win = fenetre_avec_jeux
        win.show()
        qtbot.waitExposed(win)
        win._mediatheque.ouvrir("musique", "hp2")
        page = win._pages.page
        anciennes = page.findChildren(_LigneMorceau)
        assert anciennes
        page.montrer("hp3")
        assert all(not ligne.isVisible() for ligne in anciennes)


class TestBoutonCollectionsDeLaFiche:
    """Les deux pictogrammes à côté de l'engrenage (Ludo, 2026-10-27 : « plus
    petit, une icône musique et images »), sur tout jeu installé qui a des médias."""

    def _montrer(self, win, jeu):
        from src.ui.icon_button import IconButton
        game = next(e.game for e in win.manager.get_games() if e.game.id == jeu)
        win._detail.set_game(game)
        return win._detail._action_panel.findChild(IconButton, "boutonMedias")

    def test_a_cote_de_l_engrenage_en_pictogrammes(self, fenetre_avec_jeux):
        win = fenetre_avec_jeux
        bouton = self._montrer(win, "hp3")
        assert bouton is not None and bouton.isVisibleTo(win._detail)
        assert bouton.icone() == "musique" and bouton.width() > bouton.height()
        rangee = win._detail._action_panel._action_layout
        assert rangee.indexOf(bouton) == rangee.indexOf(win._detail._action_panel._btn_reglages) + 1

    def test_ouvre_la_rubrique_des_nouveautes(self, fenetre_avec_jeux, qtbot):
        win = fenetre_avec_jeux
        qtbot.waitUntil(lambda: win._title_bar.onglet("collections").pastille, timeout=5000)
        media = win._mediatheque
        media.marquer_vus("hp3", "musique")
        assert media.nouveaux("hp3", "cinematiques")
        assert media.rubrique_pour("hp3") == "cinematiques", "la musique déjà vue : les cinématiques"
        self._montrer(win, "hp3").click()
        assert win._pages.page.rubrique_courante == "cinematiques" and win._pages.page.jeu == "hp3"
        win._pages.page.accept()
        media.marquer_vus("hp3", "cinematiques")
        assert media.rubrique_pour("hp3") == "musique", "rien de neuf : sa musique"
        self._montrer(win, "hp3").click()
        assert win._pages.page.rubrique_courante == "musique"


def test_la_page_des_collections_a_les_deux_rubriques(fenetre_avec_jeux):
    from src.core import encyclopedie as _encyclo
    win = fenetre_avec_jeux
    win._mediatheque.ouvrir(_encyclo.BESTIAIRE, "hp2")
    page = win._pages.page
    assert page.rubrique_courante == _encyclo.BESTIAIRE
    vue = page._encyclo[_encyclo.BESTIAIRE]
    assert [f.fiche.cle for f in vue.fiches][:2] == ["gnome", "lutin_de_cornouailles"]
    page.rubrique(_encyclo.PERSONNAGES)
    assert page._encyclo[_encyclo.PERSONNAGES].fiches


class TestUnSeulSonCoupe:
    """Le haut-parleur de la bande-annonce, celui de la barre du bas et les
    Paramètres disent la même chose (Ludo, 2026-10-27 : « Même le son coupé
    n'est pas dans les paramètres »)."""

    def test_rallumer_la_bande_annonce_rend_le_son_du_launcher(self, fenetre_avec_jeux):
        win = fenetre_avec_jeux
        fond, detail = win._mediatheque.fond, win._detail
        fond.basculer_son()
        assert detail._video.muted
        detail._on_mute_clicked()
        assert not win.config.son_coupe, "la barre du bas ne dit plus « coupé »"
        assert not win._mediatheque.mini._son.property("coupe")
        assert not detail._video.muted

    def test_le_haut_parleur_du_bas_coupe_quand_meme(self, fenetre_avec_jeux):
        win = fenetre_avec_jeux
        detail = win._detail
        win.config.mute_videos = True
        detail.apply_audio_config()
        assert detail._video.muted
        detail._on_mute_clicked()
        assert not detail._video.muted, "le geste vaut malgré « Couper le son des vidéos »"
        win._mediatheque.mini._son.click()
        assert detail._video.muted
        win._mediatheque.mini._son.click()
        assert not detail._video.muted, "le choix de la session revient"

    def test_le_reglage_change_reprend_la_main(self, fenetre_avec_jeux):
        win = fenetre_avec_jeux
        detail = win._detail
        win.config.mute_videos = True
        detail.apply_audio_config()
        assert detail._video.muted
        detail._on_mute_clicked()
        win.config.mute_videos = False
        detail.apply_audio_config()
        win.config.mute_videos = True
        detail.apply_audio_config()
        assert detail._video.muted

    def test_l_interrupteur_des_parametres_suit_le_haut_parleur(self, fenetre_avec_jeux, qtbot):
        from src.ui.settings_panel import SettingsDialog
        win = fenetre_avec_jeux
        fond = win._mediatheque.fond
        dlg = SettingsDialog(win.config, win.manager, win, fond=fond)
        qtbot.addWidget(dlg)
        dlg.construire_rubrique(1)
        assert not dlg._tgl_son.isChecked()
        dlg._tgl_son._basculer()
        assert win.config.son_coupe and win._mediatheque.mini._son.property("coupe")
        win._mediatheque.mini._son.click()
        assert not dlg._tgl_son.isChecked()
        dlg.reject()
        win._mediatheque.mini._son.click()   # le dialogue fermé n'écoute plus
        assert win.config.son_coupe
