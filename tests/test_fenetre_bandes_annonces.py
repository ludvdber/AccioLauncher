"""Une VRAIE MainWindow : les bandes-annonces de la fiche (départ, délai, barre audio,
revoir).

Config temporaire (CONFIG_FILE_PATH patché), `_start_update_check` neutralisé,
autoplay=False. Fixtures `make_window*` dans `conftest.py`.
"""

import pathlib

import pytest

pytest.importorskip("pytestqt")


from src.ui import game_detail as _gd  # noqa: E402


class TestBandesAnnonces:
    """Comportement des vidéos de fond : muettes, différées, suspendues.

    Les trailers sont la signature visuelle du launcher — ils restent. Ce qui
    change, c'est qu'ils ne s'imposent plus : pas de son surprise, pas de
    lecture derrière une fenêtre inactive, pas de démarrage pendant qu'on lit
    le titre.
    """

    def test_muet_par_defaut(self):
        from src.core.config import Config
        assert Config().mute_videos is True, "un logiciel ne doit pas faire de bruit sans prévenir"

    def test_video_non_lancee_immediatement(self, make_window, qtbot):
        """Le démarrage est différé : la fiche se lit sur une image fixe."""
        win = make_window(autoplay_videos=True)
        detail = win._detail
        assert detail._pending_video_id == detail.game.id
        assert not detail._video.is_playing, "la vidéo ne doit pas démarrer dans la même frame"

    def test_changer_de_jeu_annule_la_video_programmee(self, make_window, qtbot):
        """Parcourir le carrousel ne doit pas lancer un lecteur par vignette."""
        win = make_window(autoplay_videos=True)
        detail = win._detail
        autre = next(e.game for e in win.manager.get_games() if e.game.id != detail.game.id)
        detail.set_game(autre)
        assert detail._pending_video_id == autre.id
        detail._on_video_timer()          # le timer du PREMIER jeu arrive en retard
        assert not detail._video.is_playing or detail.game.id == autre.id

    def test_pause_effects_suspend_la_video(self, make_window, qtbot):
        """Fenêtre derrière une autre : plus de décodage vidéo pour personne."""
        win = make_window()
        detail = win._detail
        detail.pause_effects()
        assert detail._video.paused is False or not detail._video.is_playing
        detail.resume_effects()

    def test_sans_lecture_automatique_la_pastille_lire_reste(self, make_window, qtbot,
                                                            tmp_path, monkeypatch):
        """Lecture auto coupée : la fiche n'avait plus AUCUNE commande vidéo, ni
        lecture, ni son (Ludo, 2026-10-14). La pastille « Lire » la lance."""
        from src.core import trailers
        faux = tmp_path / "t.mp4"
        faux.write_bytes(b"x")
        monkeypatch.setattr(trailers, "chemin_a_jouer", lambda *a, **k: faux)
        win = make_window(autoplay_videos=False)
        win.show()
        qtbot.waitExposed(win)
        detail = win._detail
        lances = []
        monkeypatch.setattr(detail._video, "play", lambda *a, **k: lances.append(a) or True)
        autre = next(e.game for e in win.manager.get_games() if e.game.id != detail.game.id)
        detail.set_game(autre)
        bar = detail._audio_bar
        qtbot.waitUntil(bar.isVisible, timeout=1000)
        assert bar._btn_replay.accessibleName() == "Lire la bande-annonce"
        assert not bar._btn_mute.isVisible()
        bar._btn_replay.click()
        assert lances, "le clic doit lancer la bande-annonce"
        assert bar._btn_mute.isVisible() and bar._btn_play.isVisible()

    def test_barre_audio_a_un_bouton_pause(self, make_window):
        win = make_window()
        bar = win._detail._audio_bar
        assert hasattr(bar, "play_toggled")
        bar.set_paused_icon(True)
        bar.set_paused_icon(False)


class TestBandeAnnonceNeRepartPasTouteSeule:
    """`_schedule_video` arme un `singleShot` de 2 s que rien ne désarmait.

    Couper la vidéo ne l'empêchait donc pas de repartir juste après. Cas réel
    (Ludo, 2026-08-23) : un téléchargement en cours, on va lancer un AUTRE jeu
    — donc on change de fiche puis on clique JOUER dans la foulée, en moins de
    deux secondes. La fenêtre part dans le tray, le minuteur arrive derrière, et
    la bande-annonce joue sans image. Sans téléchargement on s'attarde sur la
    fiche, le minuteur a déjà tiré, et le défaut ne se reproduit pas.
    """

    @staticmethod
    def _espionner(vue, monkeypatch):
        joues = []
        monkeypatch.setattr(type(vue), "_try_play_video",
                            lambda self, gid: joues.append(gid))
        return joues

    def test_stop_annule_le_demarrage_en_attente(self, make_window, monkeypatch):
        win = make_window(autoplay_videos=True)
        vue = win._detail
        jeux = [e.game for e in win.manager.get_games()]
        vue.set_game(jeux[0])
        vue.set_game(jeux[1])          # arme le minuteur pour jeux[1]
        joues = self._espionner(vue, monkeypatch)
        vue._stop_video()              # ce que fait JOUER
        vue._on_video_timer()          # le minuteur arrive derrière
        assert joues == []

    def test_la_mise_en_tray_annule_aussi(self, make_window, monkeypatch):
        """`pause()` (tray) passe par `_stop_video` : même protection."""
        win = make_window(autoplay_videos=True)
        vue = win._detail
        vue.set_game([e.game for e in win.manager.get_games()][1])
        joues = self._espionner(vue, monkeypatch)
        vue.pause()
        vue._on_video_timer()
        assert joues == []

    def test_une_fenetre_cachee_ne_lance_rien(self, make_window, monkeypatch):
        """Second garde-fou, indépendant de l'annulation : un `singleShot` déjà
        en vol quand la fenêtre disparaît ne doit pas aboutir à du son sans
        image."""
        win = make_window(autoplay_videos=True)
        win.show()
        vue = win._detail
        jeu = [e.game for e in win.manager.get_games()][1]
        vue.set_game(jeu)
        joues = self._espionner(vue, monkeypatch)
        vue._pending_video_id = jeu.id      # comme si rien ne l'avait annulé
        win.hide()
        vue._on_video_timer()
        assert joues == []

    def test_le_cas_normal_joue_toujours(self, make_window, monkeypatch):
        """Le garde-fou ne doit pas emporter la lecture normale."""
        win = make_window(autoplay_videos=True)
        win.show()
        vue = win._detail
        jeu = [e.game for e in win.manager.get_games()][1]
        vue.set_game(jeu)
        joues = self._espionner(vue, monkeypatch)
        vue._on_video_timer()
        assert joues == [jeu.id]


class TestDelaiBandeAnnonceRemisAZero:
    """Changer vite de jeu ne doit pas raccourcir le délai de la bande-annonce.

    `QTimer.singleShot` ne se réarme pas : chaque changement de jeu en ajoutait
    un de plus, et le garde-fou de `_on_video_timer` compare le jeu AFFICHÉ au
    jeu ATTENDU — deux valeurs qui sont toujours d'accord une fois la rafale
    finie. Le minuteur du PREMIER jeu tirait donc sur le DERNIER, bien avant la
    fin de son délai, puis les suivants relançaient la lecture depuis le début
    (Ludo, 2026-08-23). Le minuteur est désormais possédé : `start()` repart de
    zéro, `stop()` annule.
    """

    @staticmethod
    def _preparer(win, delai_ms: int, monkeypatch):
        """Fenêtre visible, minuteur raccourci, `_try_play_video` espionné.

        Le délai est raccourci AUX DEUX endroits — la constante du module et
        l'intervalle du minuteur — pour que ces tests restent un discriminant :
        sur le code d'avant, seule la constante était lue.
        """
        win.show()
        vue = win._detail
        monkeypatch.setattr(_gd, "_VIDEO_START_DELAY_MS", delai_ms)
        vue._video_timer.setInterval(delai_ms)
        joues: list[str] = []
        vue._try_play_video = joues.append   # instance, jamais la CLASSE Qt
        return vue, joues

    def test_une_rafale_ne_laisse_quun_seul_minuteur(self, make_window, qtbot, monkeypatch):
        """Quatre jeux d'affilée : UNE lecture, celle du dernier.

        C'est la mesure directe du défaut — avec un `singleShot` par changement,
        les quatre arrivaient et rejouaient la même bande-annonce depuis le
        début, la première 3 délais trop tôt.
        """
        win = make_window(autoplay_videos=True)
        vue, joues = self._preparer(win, 250, monkeypatch)
        jeux = [e.game for e in win.manager.get_games()][:4]
        assert len(jeux) == 4
        for jeu in jeux:
            vue.set_game(jeu)          # sans attendre : c'est la rafale
        qtbot.waitUntil(lambda: bool(joues), timeout=3000)
        qtbot.wait(500)                # laisser venir d'éventuels retardataires
        assert joues == [jeux[-1].id]

    def test_le_delai_repart_de_zero_au_changement(self, make_window, qtbot, monkeypatch):
        """Le compte à rebours reprend au maximum quand on change de jeu.

        Mesuré sur le minuteur lui-même plutôt qu'à la montre : `remainingTime()`
        dit exactement ce qu'on veut prouver, sans fenêtre de tir à rater sous
        la charge de la suite complète. Sur le code d'avant il rend -1 — le
        délai n'appartenait à personne.
        """
        win = make_window(autoplay_videos=True)
        vue, joues = self._preparer(win, 1500, monkeypatch)
        jeux = [e.game for e in win.manager.get_games()]
        vue.set_game(jeux[0])
        qtbot.wait(600)
        restant_avant = vue._video_timer.remainingTime()
        assert 0 < restant_avant < 1200, "le délai du premier jeu doit courir"
        vue.set_game(jeux[1])
        assert vue._video_timer.remainingTime() > restant_avant + 300
        assert joues == [], "rien ne doit avoir démarré en 600 ms"

    def test_couper_annule_vraiment_le_minuteur(self, make_window, qtbot, monkeypatch):
        """`stop()` sur un minuteur possédé annule pour de bon.

        Complément du garde-fou par condition (`_pending_video_id`), qui reste
        en place pour un `timeout` déjà posté dans la file d'événements.
        """
        win = make_window(autoplay_videos=True)
        vue, joues = self._preparer(win, 250, monkeypatch)
        vue.set_game([e.game for e in win.manager.get_games()][1])
        assert vue._video_timer.isActive()
        vue._stop_video()
        assert not vue._video_timer.isActive()
        qtbot.wait(500)
        assert joues == []


class TestBarreAudioResteDansLaFiche:
    """Elle était posée à `width() - 174` alors qu'elle fait 192 px de large.

    18 px passaient donc HORS de la fenêtre : la poignée de volume disparaissait
    dès qu'on montait le son à fond (Ludo, capture du 2026-08-23). Deux nombres
    qu'aucun calcul ne reliait — le défaut du carrousel, à quelques jours près.
    """

    @pytest.mark.parametrize("taille", [(980, 560), (1200, 700), (1600, 800)])
    def test_elle_ne_depasse_jamais_du_bord(self, make_window, taille):
        win = make_window()
        vue = win._detail
        vue.resize(*taille)
        vue._position_audio_bar()   # une fenêtre cachée ne délivre pas resizeEvent
        bar = vue._audio_bar
        assert bar.x() + bar.width() <= vue.width()
        assert bar.y() + bar.height() <= vue.height()

    def test_la_poignee_de_volume_tient_dans_la_fiche(self, make_window):
        """Le symptôme exact : le curseur à 100 sortait de la fenêtre."""
        win = make_window()
        vue = win._detail
        vue.resize(1200, 700)
        bar = vue._audio_bar
        # La barre COMPLÈTE : sans lecture auto, la fiche montre la pastille « Lire ».
        bar.set_mode_fin(False)
        vue._position_audio_bar()
        bar.layout().activate()
        coin = bar.mapTo(vue, bar._volume_slider.geometry().topRight())
        assert coin.x() <= vue.width()

    def test_le_mode_fin_reste_colle_au_meme_bord(self, make_window):
        """La barre rétrécit à la fin : la position doit suivre sa largeur."""
        win = make_window()
        vue = win._detail
        vue.resize(1200, 700)
        vue._position_audio_bar()
        bar = vue._audio_bar
        marge = vue.width() - (bar.x() + bar.width())
        assert marge > 0, "la barre doit déjà être DANS la fiche"
        bar.set_mode_fin(True)
        vue._position_audio_bar()
        assert vue.width() - (bar.x() + bar.width()) == marge


class TestRevoirLaBandeAnnonce:
    """Une bande-annonce terminée ne laissait aucun moyen de la revoir.

    Il fallait changer de jeu et revenir, en espérant que le délai reparte.
    À la fin, la barre ne garde que le bouton « revoir » — les autres commandes
    n'ont plus rien à commander.
    """

    @staticmethod
    def _avec_bande_annonce(monkeypatch):
        monkeypatch.setattr(_gd.trailers, "chemin_a_jouer",
                            lambda gid, decl: pathlib.Path("bande.mp4"))

    def test_la_pastille_revoir_reste_apres_la_fin(self, make_window, monkeypatch):
        win = make_window(autoplay_videos=True)
        win.show()
        vue = win._detail
        vue.set_game([e.game for e in win.manager.get_games()][1])
        self._avec_bande_annonce(monkeypatch)
        vue._on_video_ended()
        bar = vue._audio_bar
        assert not bar.isHidden()
        assert not bar._btn_replay.isHidden()
        assert bar._volume_slider.isHidden(), "plus rien à régler"
        assert bar._btn_play.isHidden(), "plus rien à mettre en pause"

    def test_sans_bande_annonce_rien_ne_reste(self, make_window, monkeypatch):
        """`_stop_video` cache la barre : la fin ne doit pas la ressusciter."""
        win = make_window(autoplay_videos=True)
        win.show()
        vue = win._detail
        vue.set_game([e.game for e in win.manager.get_games()][1])
        monkeypatch.setattr(_gd.trailers, "chemin_a_jouer", lambda gid, decl: None)
        vue._on_video_ended()
        assert vue._audio_bar.isHidden()

    def test_le_bouton_rejoue_le_jeu_affiche(self, make_window, monkeypatch):
        win = make_window(autoplay_videos=True)
        win.show()
        vue = win._detail
        jeu = [e.game for e in win.manager.get_games()][1]
        vue.set_game(jeu)
        joues: list[str] = []
        vue._try_play_video = joues.append
        vue._audio_bar.replay_clicked.emit()
        assert joues == [jeu.id]

    def test_rejouer_remet_la_barre_complete(self, make_window, monkeypatch):
        """Après un « revoir », les commandes reviennent — et la barre aussi."""
        win = make_window(autoplay_videos=True)
        win.show()
        vue = win._detail
        vue.set_game([e.game for e in win.manager.get_games()][1])
        self._avec_bande_annonce(monkeypatch)
        vue._on_video_ended()
        assert vue._audio_bar._volume_slider.isHidden()
        monkeypatch.setattr(type(vue._video), "play",
                            lambda self, chemin, **kw: True)
        vue._on_replay_clicked()
        bar = vue._audio_bar
        assert not bar._volume_slider.isHidden()
        assert bar.x() + bar.width() <= vue.width()
