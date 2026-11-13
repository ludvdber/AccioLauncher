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

    def test_le_haut_parleur_coupe_aussi_l_ecoute(self, fond):
        """Ludo, 2026-11-02 : un bug. L'écoute de la Médiathèque continuait,
        bouton « coupé » affiché (grand audit)."""
        fond.ecouter("hp1/Common_Room")
        fond.basculer_son()
        assert fond._voulu() == ""
        fond.basculer_son()
        assert fond._voulu() == "hp1/Common_Room"

    def test_le_fichier_du_morceau_se_prepare_sur_un_autre_fil(self, fond, qtbot, monkeypatch, tmp_path):
        """Grand audit du 2026-11-02 : lister `music.big` et convertir par
        vgmstream figeait la fenêtre 0,3 à 0,5 s à la première écoute."""
        import threading

        from src.ui.fond_sonore import MULTIMEDIA_DISPONIBLE
        if not MULTIMEDIA_DISPONIBLE:
            pytest.skip("PyQt6-Multimedia absent")
        fond._config.son_coupe = False
        piste = tmp_path / "morceau.ogg"
        piste.write_bytes(b"OggS")
        fils = []
        monkeypatch.setattr(fond, "fichier", lambda c: (fils.append((threading.current_thread(), c)),
                                                        piste)[1])
        fond.demarrer()
        assert fond._courant == "" and fond._en_preparation == "hp2/Greenhouse"
        fond.ecouter("hp1/Common_Room")      # demandé pendant la préparation : il gagne
        qtbot.waitUntil(lambda: fond._courant == "hp1/Common_Room", timeout=5000)
        assert fils and all(f is not threading.main_thread() for f, _c in fils)
        fond.arreter()

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

    def test_sans_morceau_la_note_seule_au_gabarit_du_haut_parleur(self, make_window):
        """Le mot « Musique » doublait la note ; le clic ouvre les Collections."""
        win = make_window()
        mini = win._mediatheque.mini
        win._mediatheque.fond._config.musique_fond = ""
        mini.actualiser()
        assert mini._titre.isHidden() and not mini._note.isHidden()
        assert mini._bouton.width() == mini._son.width()
        assert mini._bouton.toolTip() == "Collections"
        assert mini._bouton.accessibleName() == "Ouvrir les Collections"

    def test_avec_un_morceau_son_titre_et_son_disque(self, make_window):
        win = make_window()
        mini = win._mediatheque.mini
        win._mediatheque.fond._config.musique_fond = "hp1/piste"
        mini.actualiser()
        assert not mini._titre.isHidden() and mini._titre.text()
        assert mini._note.isHidden()
        assert mini._bouton.width() > mini._son.width()
        win._mediatheque.fond._config.musique_fond = ""

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
        a_ecouter = sum(m.seuil == 0 for m in hp2)
        # Les ouverts (moins d'un paquet) tout de suite ; les fermés restent sous le pli.
        lignes = page.findChildren(_LigneMorceau)
        assert len(lignes) == a_ecouter and all(ligne._ecouter is not None for ligne in lignes)
        # Le pli, lui, se bâtit par paquets : les premières rangées tout de suite, le reste ensuite.
        from src.ui.mediatheque_page import _PliFermes
        qtbot.waitUntil(lambda: bool(page.findChildren(_PliFermes)), timeout=5000)
        page.findChildren(_PliFermes)[0].bouton.click()
        assert a_ecouter < len(page.findChildren(_LigneMorceau)) < len(hp2)
        lignes = _deplier(page, qtbot, len(hp2))
        ouvertes = [ligne for ligne in lignes if ligne._ecouter is not None]
        assert len(ouvertes) == a_ecouter
        # Montrés une fois : vus. Les cinématiques, bâties mais pas regardées, restent nouvelles.
        assert not win._mediatheque.nouveaux("hp2", "musique")
        assert win._mediatheque.nouveaux("hp3", "cinematiques") == {"SiriusPhoto"}
        page.rubrique("cinematiques")
        assert page.jeu == "hp2", "le jeu choisi en haut vaut pour les deux rubriques"
        page.montrer("hp3")
        assert not win._mediatheque.nouveaux("hp3", "cinematiques")
        win._mediatheque.ouvrir("musique", "hp3")
        assert not onglet.pastille, "tout a été vu : le point or s'éteint"

    def test_le_point_or_dit_quelle_rubrique_et_quel_jeu(self, fenetre_avec_jeux, qtbot):
        """Ludo, 2026-10-31 : « on voit pas où dans Collections il y a du nouveau »."""
        from src.ui.title_bar import COLLECTIONS
        win = fenetre_avec_jeux
        qtbot.waitUntil(lambda: win._title_bar.onglet(COLLECTIONS).pastille, timeout=5000)
        win._on_onglet(COLLECTIONS)
        page = win._pages.page
        assert page.rubrique_courante == "captures"
        points = page._points
        assert points["musique"].isVisibleTo(page) and points["cinematiques"].isVisibleTo(page)
        page.rubrique("cinematiques")
        jeux = page._jeux._points
        # HP2 vient d'être montré, mais rien de neuf en cinématiques : seul HP3 a son point.
        assert jeux["hp3"].isVisibleTo(page) and not jeux["hp2"].isVisibleTo(page)
        page.montrer("hp3")
        assert not jeux["hp3"].isVisibleTo(page) and not points["cinematiques"].isVisibleTo(page)
        page.rubrique("musique")
        assert jeux["hp2"].isVisibleTo(page), "la musique de HP2 n'a pas encore été montrée"
        page.montrer("hp2")
        assert not points["musique"].isVisibleTo(page), "montrée, elle est vue"
        page.accept()

    def test_personnages_et_bestiaire_sans_compte_de_nouveautes(self, fenetre_avec_jeux, qtbot):
        """Les pastilles des jeux y gardaient le compte de la rubrique d'avant
        (audit du 2026-11-02)."""
        from src.core import encyclopedie as _encyclo
        from src.ui.title_bar import COLLECTIONS
        win = fenetre_avec_jeux
        qtbot.waitUntil(lambda: win._title_bar.onglet(COLLECTIONS).pastille, timeout=5000)
        win._on_onglet(COLLECTIONS)
        page = win._pages.page
        page.rubrique("cinematiques")
        assert page._jeux._points["hp3"].isVisibleTo(page)
        for rubrique in (_encyclo.PERSONNAGES, _encyclo.BESTIAIRE):
            page.rubrique(rubrique)
            assert not any(p.isVisibleTo(page) for p in page._jeux._points.values()), rubrique
            assert "·" not in page._jeux._boutons["hp3"].text()
        page.accept()

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

    def test_la_voix_s_arrete_sans_stop(self, vue, monkeypatch):
        """Règle 135 : `stop()` garde le GIL, `setSource(QUrl())` arrête et le relâche."""
        from src.ui.fond_sonore import MULTIMEDIA_DISPONIBLE, QMediaPlayer
        if not MULTIMEDIA_DISPONIBLE:
            pytest.skip("QtMultimedia absent de cette machine")
        _win, page, _ordre = vue
        voix = QMediaPlayer(page)
        appels = []
        monkeypatch.setattr(voix, "stop", lambda: appels.append(True))
        page._voix = voix
        page._arreter_voix()
        assert not appels and page._voix is None

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

    def test_une_pause_en_fin_de_narration_tient_apres_un_saut(self, vue, monkeypatch):
        """L'image est finie, seule la voix est en pause : le saut ne relance rien."""
        from PyQt6.QtMultimedia import QMediaPlayer

        _win, page, _ordre = vue
        page.jouer("hp3", "SiriusPhoto", "x")
        page._allonger(20_000)
        lancees, pauses = [], []

        class Voix:
            def setPosition(self, _ms): pass
            def playbackState(self): return QMediaPlayer.PlaybackState.PausedState
            def play(self): lancees.append(1)
            def setSource(self, _u): pass
            def deleteLater(self): pass
            def stop(self): pass

        page._voix = Voix()
        monkeypatch.setattr(page._video, "play", lambda chemin, muted, volume, debut_ms=0: True)
        monkeypatch.setattr(page._video, "pause", lambda: pauses.append(1))
        page._aller_a(5_000)
        assert not lancees, "la voix reste en pause"
        assert pauses, "l'image relancée se remet en pause"

    def test_sans_voix_un_saut_au_bout_termine_la_cinematique(self, vue, monkeypatch):
        _win, page, _ordre = vue
        page.jouer("hp3", "SiriusPhoto", "x")
        page._allonger(20_000)
        monkeypatch.setattr(page._video, "_attente", 1)   # `is_playing` : une ouverture en cours
        fins = []
        monkeypatch.setattr(page, "arreter", lambda: fins.append(1))
        page._aller_a(20_000)
        assert fins == [1]

    def test_enregistrer_copie_la_video_et_sa_voix(self, vue, monkeypatch, tmp_path, qtbot):
        """La copie se fait sur un fil à part (grand audit du 2026-11-02 : jusqu'à
        329 Mo pour HP8, la fenêtre figée jusqu'au bout)."""
        import shutil
        import threading

        from PyQt6.QtWidgets import QFileDialog
        win, page, _ordre = vue
        fils, vraie = [], shutil.copyfile
        monkeypatch.setattr(shutil, "copyfile", lambda s, d: (fils.append(threading.current_thread()),
                                                              vraie(s, d))[1])
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
        assert not page._enregistrer.isEnabled(), "pas de seconde copie par-dessus"
        qtbot.waitUntil(lambda: "Sirius.wav" in page._note.text(), timeout=5000)
        assert fils and all(f is not threading.main_thread() for f in fils)
        assert page._enregistrer.isEnabled()
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

    def test_au_repos_rien_ne_dit_en_cours_et_le_grand_bouton_lance_le_premier(self, vue):
        _win, page, fond, cles = vue
        page.montrer("hp2")
        assert fond.morceau == ""
        for libelle in (page._surtitre, page._titre, page._sous_titre):
            assert libelle.isHidden()
        assert page._lecture.isEnabled() and not page._suivant.isEnabled()
        page._lecture.click()
        assert fond.morceau == cles[0]
        assert not page._surtitre.isHidden() and not page._titre.isHidden()
        page._lecture.click()
        assert fond.en_pause and fond.morceau == cles[0], "ensuite, il met en pause"

    def test_sans_morceau_ouvert_le_grand_bouton_s_eteint(self, vue, monkeypatch):
        win, page, _fond, _cles = vue
        monkeypatch.setattr(win._mediatheque, "ouvert", lambda jeu, seuil: False)
        page.montrer("hp2")
        assert not page._lecture.isEnabled()

    def test_le_grand_bouton_n_offre_pas_une_musique_illisible(self, vue, monkeypatch):
        win, page, _fond, _cles = vue
        monkeypatch.setattr(win._mediatheque, "attend_vgmstream", lambda jeu: True)
        page.montrer("hp2")
        assert not page._lecture.isEnabled()

    def test_sans_vgmstream_du_systeme_la_page_le_dit_au_lieu_de_lister(self, vue, monkeypatch):
        """Sous Linux la liste s'affichait, Lecture ne jouait rien, sans un mot (Bazzite, 2026-11-11)."""
        win, page, _fond, _cles = vue
        monkeypatch.setattr(win._mediatheque, "manque_vgmstream", lambda jeu: True)
        page.montrer("hp2")
        assert "vgmstream-cli" in page._vide.text()
        assert not page._vide.isHidden() and page._zone.isHidden()
        assert page._bouton_lecteur.isHidden(), "rien à télécharger d'ici"
        assert not page._lecture.isEnabled()

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


def _deplier(page, qtbot, total):
    """Ouvre le pli des morceaux fermés et attend toutes les lignes, dans l'ordre affiché."""
    from src.ui.mediatheque_page import _LigneMorceau, _PliFermes
    qtbot.waitUntil(lambda: bool(page.findChildren(_PliFermes)), timeout=5000)
    pli = page.findChildren(_PliFermes)[0]
    if not pli.bouton.isChecked():
        pli.bouton.click()
    qtbot.waitUntil(lambda: len(page.findChildren(_LigneMorceau)) == total, timeout=5000)
    return list(page._musique._lignes)          # dans l'ordre où elles se posent


class TestLesFermesSousUnPli:
    """Constat accepté par Ludo le 2026-11-12 : 26 morceaux ouverts dispersés dans
    152 lignes, dont 126 « Morceau à découvrir ». Les ouverts d'abord, les fermés
    sous un seul pli qui dit leur nombre."""

    def _page(self, win, qtbot, jeu):
        from src.ui.mediatheque_page import _LigneMorceau
        win._mediatheque.ouvrir("musique", jeu)
        page = win._pages.page
        qtbot.waitUntil(lambda: bool(page.findChildren(_LigneMorceau)), timeout=5000)
        return page

    def test_les_ouverts_d_abord_dans_leur_ordre_puis_un_seul_pli(self, fenetre_avec_jeux, qtbot):
        from PyQt6.QtWidgets import QLabel
        from src.ui.mediatheque_page import _LigneMorceau, _PliFermes
        win = fenetre_avec_jeux
        page = self._page(win, qtbot, "hp2")
        media = win._mediatheque
        hp2 = discographie.charger()["hp2"]
        ouverts = [m for m in hp2 if media.ouvert("hp2", m.seuil)]
        fermes = [m for m in hp2 if not media.ouvert("hp2", m.seuil)]
        assert ouverts and fermes, "le jeu d'essai a des deux"
        qtbot.waitUntil(lambda: len(page.findChildren(_PliFermes)) == 1, timeout=5000)
        pli = page.findChildren(_PliFermes)[0]
        assert pli.libelle.text() == f"{len(fermes)} à découvrir"
        assert pli.bouton.accessibleName() == pli.libelle.text()
        assert not pli.bouton.isChecked() and pli.corps.isHidden()
        lignes = page.findChildren(_LigneMorceau)
        assert [ligne.cle for ligne in lignes] == [f"hp2/{m.fichier}" for m in ouverts]
        assert [ligne.findChildren(QLabel)[0].text() for ligne in lignes] == [
            str(i) for i in range(1, len(ouverts) + 1)]
        # Le pli suit la dernière ligne ouverte.
        pile = page._musique._pile
        index = [pile.itemAt(i).widget() for i in range(pile.count())]
        assert index.index(pli) == len(ouverts)

    def test_le_pli_deroule_les_fermes_numerotes_a_la_suite(self, fenetre_avec_jeux, qtbot):
        from PyQt6.QtWidgets import QLabel
        from src.ui.mediatheque_page import _LigneMorceau, _PliFermes
        win = fenetre_avec_jeux
        page = self._page(win, qtbot, "hp2")
        media = win._mediatheque
        hp2 = discographie.charger()["hp2"]
        ouverts = [m for m in hp2 if media.ouvert("hp2", m.seuil)]
        fermes = [m for m in hp2 if not media.ouvert("hp2", m.seuil)]
        _deplier(page, qtbot, len(hp2))
        pli = page.findChildren(_PliFermes)[0]
        assert pli.bouton.isChecked() and not pli.corps.isHidden()
        sous = pli.corps.findChildren(_LigneMorceau)
        assert [ligne.cle for ligne in sous] == [f"hp2/{m.fichier}" for m in fermes]
        assert all(ligne._ecouter is None and not ligne.property("ouverte") for ligne in sous)
        assert [ligne.findChildren(QLabel)[0].text() for ligne in sous] == [
            str(i) for i in range(len(ouverts) + 1, len(hp2) + 1)]
        textes = {lbl.text() for lbl in sous[0].findChildren(QLabel)}
        assert any(t.startswith("S'ouvre") for t in textes), "le seuil reste lisible"
        pli.bouton.click()
        assert pli.corps.isHidden()
        pli.bouton.click()
        assert len(page.findChildren(_LigneMorceau)) == len(hp2), "rebâties une seule fois"

    def test_un_jeu_remontre_pendant_le_depliage_ne_garde_pas_de_lignes_mortes(
            self, fenetre_avec_jeux, qtbot):
        """Retour de partie (`actualiser`) pendant que le pli bâtit ses paquets : son
        minuteur à lui court encore, ses lignes vont à `deleteLater`."""
        from PyQt6 import sip
        from src.ui.mediatheque_page import _PliFermes
        win = fenetre_avec_jeux
        page = self._page(win, qtbot, "hp2")
        vue = page._musique
        qtbot.waitUntil(lambda: bool(page.findChildren(_PliFermes)), timeout=5000)
        ancien = page.findChildren(_PliFermes)[0]
        ancien.bouton.click()
        vue.montrer("hp2")
        # Son minuteur peut tomber avant le `deleteLater` : on l'y force.
        ancien._paquets._suite()
        qtbot.wait(200)
        hp2 = discographie.charger()["hp2"]
        assert all(not sip.isdeleted(ligne) for ligne in vue._lignes)
        assert len(vue._lignes) == sum(win._mediatheque.ouvert("hp2", m.seuil) for m in hp2)
        vue._rafraichir()                # `marquer` sur chaque ligne : ne lève plus

    def test_sans_ferme_pas_de_pli(self, fenetre_avec_jeux, qtbot, monkeypatch):
        from src.ui.mediatheque_page import _LigneMorceau, _PliFermes
        win = fenetre_avec_jeux
        monkeypatch.setattr(win._mediatheque, "ouvert", lambda _jeu, _seuil: True)
        page = self._page(win, qtbot, "hp2")
        hp2 = discographie.charger()["hp2"]
        qtbot.waitUntil(lambda: len(page.findChildren(_LigneMorceau)) == len(hp2), timeout=5000)
        assert not page.findChildren(_PliFermes)


def _encre(icone, cote, mode):
    """La couleur la plus couverte d'un pictogramme, dans ce mode."""
    from PyQt6.QtGui import QColor, QIcon
    image = icone.pixmap(cote, cote, mode, QIcon.State.Off).toImage()
    pixels = (image.pixelColor(x, y) for x in range(image.width()) for y in range(image.height()))
    meilleur = max(pixels, key=lambda c: c.alpha())
    assert meilleur.alpha() > 200
    return QColor(meilleur.red(), meilleur.green(), meilleur.blue())


class TestLignesEtPastilles:
    """Revue de l'interface, Collections : la ligne se clique, l'or désigne celle qui
    joue, un chiffre ne se colle plus au numéro du jeu."""

    def _lignes(self, win, qtbot, classe):
        page = win._pages.page
        qtbot.waitUntil(lambda: bool(page.findChildren(classe)), timeout=5000)
        return page

    def test_un_clic_sur_la_ligne_ouverte_ecoute(self, fenetre_avec_jeux, qtbot):
        from PyQt6.QtCore import Qt
        from src.ui.mediatheque_page import _LigneMorceau
        win = fenetre_avec_jeux
        win._mediatheque.ouvrir("musique", "hp2")
        hp2 = discographie.charger()["hp2"]
        page = self._lignes(win, qtbot, _LigneMorceau)
        lignes = _deplier(page, qtbot, len(hp2))
        ouverte = next(ligne for ligne in lignes if ligne._ecouter is not None)
        fermee = next(ligne for ligne in lignes if ligne._ecouter is None)
        fond = win._mediatheque.fond
        assert fermee.cursor().shape() != Qt.CursorShape.PointingHandCursor and not fermee.property("ouverte")
        qtbot.mouseClick(fermee, Qt.MouseButton.LeftButton)
        assert fond.morceau == "", "une ligne fermée ne promet rien"
        assert ouverte.cursor().shape() == Qt.CursorShape.PointingHandCursor and ouverte.property("ouverte")
        qtbot.mouseClick(ouverte, Qt.MouseButton.LeftButton)
        assert fond.morceau == ouverte.cle

    def test_l_or_ne_reste_que_sur_la_ligne_en_cours(self, fenetre_avec_jeux, qtbot):
        from PyQt6.QtGui import QIcon
        from src.ui.mediatheque_page import _LigneMorceau
        from src.ui.theme import accent_qcolor
        win = fenetre_avec_jeux
        win._mediatheque.ouvrir("musique", "hp2")
        page = self._lignes(win, qtbot, _LigneMorceau)
        ligne = next(x for x in page.findChildren(_LigneMorceau) if x._ecouter is not None)
        or_ = accent_qcolor().rgb()
        assert _encre(ligne._ecouter.icon(), 14, QIcon.Mode.Normal).rgb() != or_
        ligne.marquer(True, False)
        assert _encre(ligne._ecouter.icon(), 14, QIcon.Mode.Normal).rgb() == or_
        ligne.marquer(False, False)
        assert _encre(ligne._ecouter.icon(), 14, QIcon.Mode.Normal).rgb() != or_

    def test_un_clic_sur_la_ligne_de_cinematique_la_joue(self, fenetre_avec_jeux, qtbot, monkeypatch):
        from PyQt6.QtCore import Qt
        from src.ui.mediatheque_page import _LigneCine
        win = fenetre_avec_jeux
        win._mediatheque.ouvrir("cinematiques", "hp3")
        page = win._pages.page
        qtbot.waitUntil(lambda: len(page.findChildren(_LigneCine)) == 2, timeout=5000)
        jouees = []
        monkeypatch.setattr(page._cinematiques, "jouer", lambda j, f, t: jouees.append(f))
        lignes = {ligne.fichier: ligne for ligne in page.findChildren(_LigneCine)}
        qtbot.mouseClick(lignes["LupinWolf"], Qt.MouseButton.LeftButton)
        assert jouees == []
        qtbot.mouseClick(lignes["SiriusPhoto"], Qt.MouseButton.LeftButton)
        assert jouees == ["SiriusPhoto"]

    def test_le_nouveau_se_dit_par_le_point_sans_chiffre(self, fenetre_avec_jeux, qtbot):
        from src.ui.title_bar import COLLECTIONS
        win = fenetre_avec_jeux
        qtbot.waitUntil(lambda: win._title_bar.onglet(COLLECTIONS).pastille, timeout=5000)
        win._on_onglet(COLLECTIONS)
        page = win._pages.page
        page.rubrique("cinematiques")
        hp3 = page._jeux._boutons["hp3"]
        assert page._jeux._points["hp3"].isVisibleTo(page)
        assert not any(c.isdigit() for c in hp3.text()), "le compte reste dans l'infobulle"
        assert "1 nouveau" in hp3.toolTip()
        page.accept()

    def test_les_pastilles_sans_contenu_s_attenuent(self, fenetre_avec_jeux):
        from src.core import encyclopedie as _encyclo
        win = fenetre_avec_jeux
        win._mediatheque.ouvrir("cinematiques", "hp3")
        page = win._pages.page
        boutons = page._jeux._boutons
        assert boutons["hp2"].property("vide") is True and boutons["hp3"].property("vide") is False
        page.rubrique("musique")
        assert boutons["hp2"].property("vide") is False
        page.rubrique(_encyclo.BESTIAIRE)
        assert boutons["hp2"].property("vide") is False
        page.accept()


class TestEtatsVides:
    def test_sans_cinematique_ni_ecran_ni_commandes(self, fenetre_avec_jeux):
        win = fenetre_avec_jeux
        win._mediatheque.ouvrir("cinematiques", "hp3")
        vue = win._pages.page._cinematiques
        assert vue._vide.isHidden() and not vue._cote.isHidden()
        vue.montrer("hp2")
        assert not vue._vide.isHidden() and vue._cote.isHidden()
        assert "moteur" in vue._vide.text()
        vue.montrer("hp3")
        assert vue._vide.isHidden() and not vue._cote.isHidden()

    def test_l_ecran_cache_une_cinematique_en_cours_s_arrete(self, fenetre_avec_jeux, monkeypatch, tmp_path):
        win = fenetre_avec_jeux
        win._mediatheque.ouvrir("cinematiques", "hp3")
        vue = win._pages.page._cinematiques
        video = tmp_path / "v.bik"
        video.write_bytes(b"BIKi")
        monkeypatch.setattr(win._mediatheque, "video", lambda j, f: video)
        monkeypatch.setattr(win._mediatheque, "voix", lambda j, f: None)
        monkeypatch.setattr(vue._video, "play", lambda chemin, muted, volume: True)
        vue.jouer("hp3", "SiriusPhoto", "x")
        vue.montrer("hp2")
        assert not vue._courante, "pas de voix sans image"
        assert "cinematique" not in win._mediatheque.fond._raisons

    def test_un_jeu_sans_musique_a_son_etat_vide(self, fenetre_avec_jeux):
        from src.ui.encyclopedie_page import EtatVide
        win = fenetre_avec_jeux
        win._mediatheque.ouvrir("musique", "hp3")
        vue = win._pages.page._musique
        assert isinstance(vue._vide, EtatVide)
        vue.montrer("hp_inconnu")
        assert not vue._vide.isHidden() and vue._vide.text() == "Pas encore de musique pour ce jeu."
        assert not vue._lecture.isEnabled()


class TestEcranAuRepos:
    def test_l_invite_est_au_milieu_de_l_ecran(self, qtbot):
        from src.ui.mediatheque_page import _Ecran
        ecran = _Ecran()
        qtbot.addWidget(ecran)
        ecran.setFixedSize(560, 315)
        assert ecran.invite_visible
        image = ecran.grab().toImage()
        marge = 16
        allumes = [y for y in range(marge, image.height() - marge) for x in range(marge, image.width() - marge)
                   if image.pixelColor(x, y).value() > 60]
        assert allumes, "l'invite est peinte"
        assert abs((min(allumes) + max(allumes)) / 2 - image.height() / 2) <= 6

    def test_rien_ne_garde_de_hauteur_entre_l_ecran_et_la_barre(self, fenetre_avec_jeux, monkeypatch, tmp_path):
        win = fenetre_avec_jeux
        win._mediatheque.ouvrir("cinematiques", "hp3")
        vue = win._pages.page._cinematiques
        assert vue._titre.isHidden() and vue._note.isHidden() and vue._temps.isHidden()
        video = tmp_path / "v.bik"
        video.write_bytes(b"BIKi")
        monkeypatch.setattr(win._mediatheque, "video", lambda j, f: video)
        monkeypatch.setattr(win._mediatheque, "voix", lambda j, f: None)
        monkeypatch.setattr(vue._video, "play", lambda chemin, muted, volume: True)
        vue.jouer("hp3", "SiriusPhoto", "La photo")
        vue._allonger(20_000)
        assert not vue._titre.isHidden() and not vue._note.isHidden() and not vue._temps.isHidden()
        vue.arreter()
        assert vue._titre.isHidden() and vue._note.isHidden() and vue._temps.isHidden()

    def test_les_commandes_eteintes_se_voient_eteintes(self, fenetre_avec_jeux):
        from PyQt6.QtGui import QColor, QIcon
        from src.ui import composants
        from src.ui.mediatheque_page import _STYLE
        win = fenetre_avec_jeux
        win._mediatheque.ouvrir("cinematiques", "hp3")
        vue = win._pages.page._cinematiques
        assert not vue._stop.isEnabled()
        eteinte = QColor(composants.ENCRE_ETEINTE).rgb()
        assert _encre(vue._stop.icon(), 16, QIcon.Mode.Disabled).rgb() == eteinte
        assert _encre(vue._stop.icon(), 16, QIcon.Mode.Normal).rgb() != eteinte
        assert "QPushButton#rond:disabled" in composants.feuille_de_style()
        assert "QSlider::handle:horizontal:disabled" in _STYLE


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

    def test_un_echec_ne_reecrit_pas_un_jeu_qui_ne_l_attend_pas(self, fenetre_avec_jeux, monkeypatch):
        """Sur HP7 ou HP8, « pas encore lu » devenait « Le téléchargement n'a pas
        abouti… », sans bouton (audit du 2026-11-02)."""
        win = fenetre_avec_jeux
        win._mediatheque.ouvrir("musique", "hp2")
        page = win._pages.page._musique
        monkeypatch.setattr(win._mediatheque, "attend_vgmstream", lambda jeu: False)
        page.montrer("hp2")
        avant = page._vide.text()
        win._mediatheque.vgmstream.termine.emit(False)
        assert page._vide.text() == avant and page._bouton_lecteur.isHidden()


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


def test_la_croix_de_la_manette_met_le_plein_ecran_en_pause(qtbot):
    """Audit du 2026-10-29 : sans bouton au focus, la manette envoie Entrée,
    que le plein écran ignorait ; seule Espace mettait en pause."""
    from PyQt6.QtCore import Qt

    from src.ui.cinema_plein_ecran import PleinEcran
    plein = PleinEcran()
    qtbot.addWidget(plein)
    pauses = []
    plein.pause_demandee.connect(lambda: pauses.append(1))
    qtbot.keyClick(plein, Qt.Key.Key_Return)
    assert pauses == [1]


def test_la_voix_seule_se_met_en_pause_et_reprend():
    """Grand audit du 2026-11-02 : l'image finie, le lecteur vidéo est libéré et
    `paused` restait faux ; la voix se mettait en pause mais ne reprenait plus."""
    from types import SimpleNamespace
    from src.ui.fond_sonore import QMediaPlayer
    from src.ui.mediatheque_page import _VueCinematiques

    class Voix:
        etat = QMediaPlayer.PlaybackState.PlayingState

        def playbackState(self):
            return self.etat

        def pause(self):
            self.etat = QMediaPlayer.PlaybackState.PausedState

        def play(self):
            self.etat = QMediaPlayer.PlaybackState.PlayingState

    voix = Voix()
    video = SimpleNamespace(is_playing=False, paused=False, pause=lambda: None, resume=lambda: None)
    vue = SimpleNamespace(_video=video, _voix=voix, _etat_commandes=lambda: None)
    vue._en_pause = lambda: _VueCinematiques._en_pause(vue)
    _VueCinematiques._basculer_pause(vue)
    assert voix.etat == QMediaPlayer.PlaybackState.PausedState
    _VueCinematiques._basculer_pause(vue)
    assert voix.etat == QMediaPlayer.PlaybackState.PlayingState, "la reprise ne revenait jamais"


class TestLectureDesParties:
    """Grand audit du 2026-11-02 : la lecture des sauvegardes (~0,3 s) figeait
    la fenêtre au démarrage et à chaque retour de partie."""

    def test_le_retour_de_partie_lit_sur_un_autre_fil(self, fenetre_avec_jeux, qtbot, monkeypatch):
        import threading
        media = fenetre_avec_jeux._mediatheque
        media._lecture.stop()
        fils = []

        def avancement(jeu, spec):
            fils.append(threading.current_thread())
            return 100
        monkeypatch.setattr("src.core.discographie.avancement", avancement)
        media._retour_de_partie()
        qtbot.waitUntil(lambda: media._avances.get("hp2") == 100, timeout=5000)
        assert fils and all(f is not threading.main_thread() for f in fils)
        assert not media._en_vol

    def test_une_lecture_depassee_est_jetee(self, fenetre_avec_jeux, qtbot, monkeypatch):
        media = fenetre_avec_jeux._mediatheque
        media._lecture.stop()
        monkeypatch.setattr("src.core.discographie.avancement", lambda jeu, spec: None)
        media.actualiser_en_fond()
        ancien = media._numero
        monkeypatch.setattr("src.core.discographie.avancement", lambda jeu, spec: 80)
        media.actualiser()               # la page ouverte relit tout de suite
        assert media._avances["hp2"] == 80
        media._poser_lecture(ancien, ({"hp2": 10}, {}))
        assert media._avances["hp2"] == 80, "la lecture plus ancienne n'écrase rien"


class TestCinematiqueSurLaCarteGraphique:
    """Le parcours de `ecran_video_gpu` dans la vraie page, et ce qui ne dépend pas
    de la scène : la barre de lecture, la fenêtre réduite."""

    @pytest.fixture
    def page_seule(self, fenetre_avec_jeux, monkeypatch, tmp_path):
        from unittest.mock import MagicMock
        win = fenetre_avec_jeux
        win._mediatheque.ouvrir("cinematiques", "hp3")
        page = win._pages.page._cinematiques
        video = tmp_path / "v.bik"
        video.write_bytes(b"BIKi")
        monkeypatch.setattr(win._mediatheque, "video", lambda j, f: video)
        monkeypatch.setattr(win._mediatheque, "voix", lambda j, f: None)
        lecteur = page._video

        def play(_chemin, muted=False, volume=0.25, debut_ms=0):
            lecteur._player, lecteur._sink, lecteur._audio = MagicMock(), MagicMock(), MagicMock()
            lecteur._player.position.return_value = 0
            lecteur._relais = lecteur._recepteur(lecteur._sortie)
            lecteur._paused = False
            return True
        monkeypatch.setattr(lecteur, "play", play)
        return win, page

    @pytest.fixture
    def page_gpu(self, page_seule, monkeypatch):
        from src.ui import fond_gpu
        if not fond_gpu.QUICK_DISPONIBLE:
            pytest.skip("Qt Quick absent")
        # Allumée APRÈS la fenêtre : seules les scènes des cinématiques nous intéressent.
        monkeypatch.setenv("ACCIO_FOND_GPU", "1")
        monkeypatch.setenv("ACCIO_MEDIA_GPU", "1")
        return page_seule

    @pytest.fixture
    def sans_vrai_plein_ecran(self, monkeypatch):
        from src.ui import cinema_plein_ecran
        monkeypatch.setattr(cinema_plein_ecran.PleinEcran, "ouvrir", lambda self, voisin: self.show())

    def test_la_lecture_part_vers_la_scene(self, page_gpu):
        _win, page = page_gpu
        page.jouer("hp3", "SiriusPhoto", "x")
        ecran = page._ecran
        assert ecran.sur_gpu and page._video._garder_image
        assert page._video._sortie is ecran._gpu.sortie_video()
        assert ecran._gpu.isVisibleTo(ecran) and not ecran.invite_visible
        assert page._video._relais is not None, "le lecteur relaie, sans toImage"

    def test_la_scene_couvre_son_ecran_et_le_plein_ecran(self, page_gpu, sans_vrai_plein_ecran):
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QResizeEvent
        from PyQt6.QtWidgets import QApplication
        _win, page = page_gpu
        page.jouer("hp3", "SiriusPhoto", "x")
        ecran = page._ecran
        ecran.resize(480, 270)
        # La fenêtre du test n'est pas montrée : Qt garde l'événement pour l'affichage.
        QApplication.sendEvent(ecran, QResizeEvent(ecran.size(), QSize()))
        assert ecran._gpu.geometry() == ecran.rect()
        page.plein_ecran()
        plein = page._plein_ecran
        plein.resize(640, 360)
        assert plein._gpu.geometry() == plein.rect()

    def test_arreter_retire_la_scene(self, page_gpu, monkeypatch):
        _win, page = page_gpu
        page.jouer("hp3", "SiriusPhoto", "x")
        ecran = page._ecran
        vidages = []
        monkeypatch.setattr(ecran._gpu, "vider", lambda: vidages.append(1))
        page.arreter()
        assert vidages == [1], "la lecture suivante ne commence pas sur cette image"
        assert not ecran.sur_gpu and not ecran._gpu.isVisibleTo(ecran)
        assert ecran.invite_visible

    def test_double_clic_clavier_et_retour_du_plein_ecran(self, page_gpu, qtbot, sans_vrai_plein_ecran):
        from PyQt6.QtCore import Qt
        _win, page = page_gpu
        page.jouer("hp3", "SiriusPhoto", "x")
        ecran = page._ecran
        qtbot.mouseDClick(ecran, Qt.MouseButton.LeftButton)
        plein = page._plein_ecran
        assert plein is not None, "le double-clic ouvre le plein écran sans image QPainter"
        assert plein._gpu.focusPolicy() == Qt.FocusPolicy.NoFocus
        assert page._video._sortie is plein.sortie_video()
        assert page._video._relais is plein.sortie_video().property("videoSink")
        qtbot.keyClick(plein, Qt.Key.Key_Space)
        assert page._video.paused, "Espace reste à la fenêtre"
        qtbot.keyClick(plein, Qt.Key.Key_Space)
        assert not page._video.paused
        qtbot.keyClick(plein, Qt.Key.Key_Escape)
        assert page._plein_ecran is None
        assert page._video._sortie is ecran._gpu.sortie_video(), "les images reviennent à la page"

    def test_scene_refusee_le_chemin_qpainter_tel_quel(self, page_seule, monkeypatch):
        from PyQt6.QtGui import QImage

        from src.ui import ecran_video_gpu
        monkeypatch.setattr(ecran_video_gpu, "creer", lambda *a, **k: None)
        _win, page = page_seule
        page.jouer("hp3", "SiriusPhoto", "x")
        assert page._video._sortie is None and not page._ecran.sur_gpu
        image = QImage(32, 18, QImage.Format.Format_RGB32)
        page._video.video_frame.emit(image)
        assert page._ecran.image is image

    def test_plein_ecran_sans_scene_alors_que_la_page_en_a_une(self, page_gpu, monkeypatch,
                                                               sans_vrai_plein_ecran):
        from PyQt6.QtGui import QImage

        from src.ui import ecran_video_gpu
        _win, page = page_gpu
        page.jouer("hp3", "SiriusPhoto", "x")
        image = QImage(32, 18, QImage.Format.Format_RGB32)
        monkeypatch.setattr(page._video, "image_courante", lambda: image)
        monkeypatch.setattr(ecran_video_gpu, "creer", lambda *a, **k: None)
        page.plein_ecran()
        plein = page._plein_ecran
        assert plein.sortie_video() is None and plein._image is image
        assert page._video._sortie is None and page._video._relais is None

    def test_choisir_une_autre_cinematique_garde_le_plein_ecran(self, page_gpu, sans_vrai_plein_ecran):
        """Alt+Tab vers la page derrière, un clic sur une autre ligne : les images
        restent à la fenêtre qui les montre."""
        _win, page = page_gpu
        page.jouer("hp3", "SiriusPhoto", "x")
        page.plein_ecran()
        plein = page._plein_ecran
        page.jouer("hp3", "LupinWolf", "y")
        assert page._video._sortie is plein.sortie_video()

    def test_la_barre_ne_repeint_que_quatre_fois_par_seconde(self, page_seule, monkeypatch):
        _win, page = page_seule
        page.jouer("hp3", "SiriusPhoto", "x")
        page._allonger(120_000)
        page._position.resize(500, 20)
        valeurs = []
        vrai = page._position.setValue
        monkeypatch.setattr(page._position, "setValue", lambda v: (valeurs.append(v), vrai(v)))
        temps = [0]

        class Voix:
            def position(self):
                return temps[0]
        page._voix = Voix()
        try:
            for ms in range(20, 3_001, 20):            # une position toutes les 20 ms
                temps[0] = ms
                page._avancer(ms)
            assert 11 <= len(valeurs) <= 12, valeurs   # 3 s à 4 par seconde
            assert all(b - a >= 250 for a, b in zip(valeurs, valeurs[1:], strict=False))
            temps[0] = 13_000                          # un saut de dix secondes
            page._avancer(13_000)
            assert valeurs[-1] == 13_000, "un saut se montre tout de suite"
        finally:
            page._voix = None

    def test_la_barre_d_un_long_film_suit_ses_pixels(self, page_seule, monkeypatch):
        from unittest.mock import PropertyMock

        from src.ui.video_player import VideoPlayer
        _win, page = page_seule
        page.jouer("hp3", "SiriusPhoto", "x")
        page._allonger(600_000)                        # 1,2 s par pixel : le pas vise la seconde
        page._position.resize(500, 20)
        valeurs = []
        vrai = page._position.setValue
        monkeypatch.setattr(page._position, "setValue", lambda v: (valeurs.append(v), vrai(v)))
        position = PropertyMock(return_value=900)
        monkeypatch.setattr(VideoPlayer, "position", position)
        page._avancer(900)
        assert valeurs == [], "moins d'une seconde, moins d'un pixel"
        position.return_value = 1_000
        page._avancer(1_000)
        assert valeurs == [1_000]

    def test_reduite_suspend_les_deux_pistes_et_reprend(self, page_seule):
        from unittest.mock import MagicMock
        _win, page = page_seule
        page.jouer("hp3", "SiriusPhoto", "x")
        page._voix = MagicMock()
        page._voix_sortie = MagicMock()
        page.set_reduite(True)
        assert page._video.paused
        page._voix.pause.assert_called_once()
        assert page._pause.accessibleName() == "Reprendre" and not page._pause.text(), "une icône, pas un mot"
        page.set_reduite(False)
        assert not page._video.paused
        page._voix.play.assert_called()
        page._voix = page._voix_sortie = None

    def test_une_pause_voulue_ne_reprend_pas_au_retour(self, page_seule):
        _win, page = page_seule
        page.jouer("hp3", "SiriusPhoto", "x")
        page._basculer_pause()
        page.set_reduite(True)
        page.set_reduite(False)
        assert page._video.paused, "l'utilisateur l'avait mise en pause"

    def test_le_plein_ecran_ouvert_ne_suspend_rien(self, page_seule, sans_vrai_plein_ecran):
        _win, page = page_seule
        page.jouer("hp3", "SiriusPhoto", "x")
        page.plein_ecran()
        page.set_reduite(True)
        assert not page._video.paused, "la cinématique se voit dans l'autre fenêtre"
        page._plein_ecran.close()
        assert page._video.paused, "réduite et plus de plein écran : plus rien ne se voit"
        page.set_reduite(False)
        assert not page._video.paused

    def test_arreter_oublie_la_pause_de_reduction(self, page_seule):
        _win, page = page_seule
        page.jouer("hp3", "SiriusPhoto", "x")
        page.set_reduite(True)
        page.arreter()
        assert not page._pause_reduite

    def test_la_vraie_fenetre_previent_la_page(self, page_seule, monkeypatch):
        from PyQt6.QtCore import QEvent
        from PyQt6.QtWidgets import QApplication
        win, page = page_seule
        win.show()
        page.jouer("hp3", "SiriusPhoto", "x")
        monkeypatch.setattr(win, "isMinimized", lambda: True)
        QApplication.sendEvent(win, QEvent(QEvent.Type.WindowStateChange))
        assert page._video.paused, "l'état de la fenêtre arrive à la page"
        monkeypatch.setattr(win, "isMinimized", lambda: False)
        QApplication.sendEvent(win, QEvent(QEvent.Type.WindowStateChange))
        assert not page._video.paused
        win.hide()                                     # le geste de `_minimize_to_tray`
        assert page._video.paused, "cachée dans la zone de notification aussi"
        win.show()
        assert not page._video.paused


def test_les_captures_suivent_le_jeu_choisi_et_gardent_tous(fenetre_avec_jeux, qtbot):
    """Audit UI col12 : HP3 en Cinématiques donnait « Tous » en Captures, le filtre posé en
    Captures se perdait au retour, et les pastilles passaient dans la zone qui défile."""
    from src.ui.mediatheque import CAPTURES, CINEMATIQUES
    win = fenetre_avec_jeux
    win._mediatheque.ouvrir(CINEMATIQUES, "hp3")
    page = win._pages.page
    page.rubrique(CAPTURES)
    galerie = page._galerie()
    assert galerie._filtres == {}, "intégrée, la Galerie prend les pastilles des Collections"
    assert page._jeux.isVisibleTo(page) and page._jeux._boutons["hp3"].isChecked()
    assert page._jeux._tous.isVisibleTo(page)
    page._jeux._tous.click()
    assert page._jeux._tous.isChecked() and page.jeu == "hp3", "« Tous » ne change pas le jeu des autres rubriques"
    page.rubrique(CINEMATIQUES)
    assert page._jeux._boutons["hp3"].isChecked() and not page._jeux._tous.isVisibleTo(page)
    page.rubrique(CAPTURES)
    assert page._jeux._tous.isChecked(), "le filtre posé en Captures est repris au retour"
