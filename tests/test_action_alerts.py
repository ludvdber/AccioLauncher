"""Tests du bandeau d'avertissement de `src/ui/action_panel.py`.

Règle testée ici : **un état ne s'affiche que lorsqu'il DÉVIE de la normale**.
Pas de ligne « espace disque : 412 Go », pas de pastille « prérequis OK » — la
présence même du bandeau est l'information. Les tests vérifient donc autant son
absence que son contenu.
"""

import pytest

pytest.importorskip("pytestqt")

from src.core.config import Config  # noqa: E402
from src.core.game_manager import GameManager, GameState  # noqa: E402
from src.ui.action_panel import ActionPanel  # noqa: E402


@pytest.fixture
def panel(qtbot, tmp_path, monkeypatch):
    """ActionPanel sur un manager isolé, prérequis système réputés satisfaits."""
    monkeypatch.setattr("src.core.system_checks.check_vcredist_x86", lambda: True)
    cfg = Config(install_path=tmp_path / "games",
                 cache_path=tmp_path / "games" / ".cache", langue="fr")
    manager = GameManager(cfg)
    from src.core.i18n import set_language
    set_language("fr")
    widget = ActionPanel(manager)
    widget.resize(560, 120)
    qtbot.addWidget(widget)
    yield widget, manager
    set_language("fr")


def _disque(monkeypatch, free_mb):
    """Force l'espace libre vu par `GameManager.free_space_mb`.

    On patche `shutil.disk_usage` et non la méthode : `GameManager` utilise
    `__slots__` (l'attribut d'instance est en lecture seule), et surtout le
    vrai chemin de code — conversion octets → Mo comprise — reste exercé.
    """
    from collections import namedtuple
    usage = namedtuple("usage", "total used free")

    def _fake(_path):
        if free_mb is None:
            raise OSError("lecteur indisponible")
        return usage(0, 0, free_mb * 1024 * 1024)

    monkeypatch.setattr("src.core.game_manager.shutil.disk_usage", _fake)


def _jeu_telechargeable(manager):
    """Premier jeu du catalogue dont une archive est réellement publiée."""
    for entry in manager.get_games():
        dl = entry.game.current_download
        if dl is not None and dl.is_available and dl.size_mb > 0:
            return entry.game
    pytest.skip("aucun jeu téléchargeable dans le catalogue embarqué")


def _prepare(panel_fixture, state):
    widget, manager = panel_fixture
    game = _jeu_telechargeable(manager)
    manager.set_game_state(game.id, state)
    widget.set_game(game)
    widget.refresh()
    return widget, manager, game


class TestSilenceQuandToutVaBien:
    def test_aucun_bandeau_avec_de_la_place_et_du_reseau(self, panel, monkeypatch):
        widget, manager = panel
        _disque(monkeypatch, 900_000)
        _prepare(panel, GameState.NOT_INSTALLED)
        assert widget._alert.isHidden()
        assert widget._alert.text() == ""

    def test_espace_inconnu_ne_declenche_rien(self, panel, monkeypatch):
        """`None` veut dire « je ne sais pas » : un lecteur réseau déconnecté ne
        prouve pas qu'il manque de la place."""
        widget, manager = panel
        _disque(monkeypatch, None)
        _prepare(panel, GameState.NOT_INSTALLED)
        assert widget._alert.isHidden()

    def test_rien_sans_jeu(self, panel):
        widget, _ = panel
        widget.set_game(None)
        widget.refresh()
        assert widget._alert.isHidden()


class TestEspaceDisque:
    def test_bandeau_quand_la_place_manque(self, panel, monkeypatch):
        widget, manager = panel
        _disque(monkeypatch, 50)
        _prepare(panel, GameState.NOT_INSTALLED)
        assert not widget._alert.isHidden()
        assert "Espace insuffisant" in widget._alert.text()

    def test_le_bandeau_propose_de_changer_de_dossier(self, panel, monkeypatch, qtbot):
        widget, manager = panel
        _disque(monkeypatch, 50)
        _prepare(panel, GameState.NOT_INSTALLED)
        assert 'href="settings"' in widget._alert.text()
        with qtbot.waitSignal(widget.settings_requested, timeout=500):
            widget._on_alert_link("settings")

    def test_le_seuil_est_celui_de_la_verification_au_clic(self, panel, monkeypatch):
        """Juste au-dessus du besoin → silence ; juste en dessous → bandeau."""
        from src.core.system_checks import needed_space_mb
        widget, manager = panel
        game = _jeu_telechargeable(manager)
        besoin = needed_space_mb(game.current_download.size_mb)

        _disque(monkeypatch, besoin)
        _prepare(panel, GameState.NOT_INSTALLED)
        assert widget._alert.isHidden()

        _disque(monkeypatch, besoin - 1)
        widget.refresh()
        assert not widget._alert.isHidden()

    def test_pas_de_bandeau_disque_sur_un_jeu_installe(self, panel, monkeypatch):
        """Rien à télécharger : la place libre ne le concerne plus."""
        widget, manager = panel
        _disque(monkeypatch, 1)
        _prepare(panel, GameState.INSTALLED)
        assert widget._alert.isHidden()


class TestHorsLigne:
    def test_bandeau_et_bouton_grise(self, panel, monkeypatch):
        widget, manager = panel
        _disque(monkeypatch, 900_000)
        _prepare(panel, GameState.NOT_INSTALLED)
        widget.set_online(False)
        assert "Hors ligne" in widget._alert.text()
        boutons = [widget._action_layout.itemAt(i).widget()
                   for i in range(widget._action_layout.count())]
        telecharger = [b for b in boutons if b is not None and b.objectName() == "btnDownload"]
        assert telecharger and not telecharger[0].isEnabled()

    def test_le_retour_en_ligne_reactive_tout(self, panel, monkeypatch):
        widget, manager = panel
        _disque(monkeypatch, 900_000)
        _prepare(panel, GameState.NOT_INSTALLED)
        widget.set_online(False)
        widget.set_online(True)
        assert widget._alert.isHidden()
        boutons = [widget._action_layout.itemAt(i).widget()
                   for i in range(widget._action_layout.count())]
        telecharger = [b for b in boutons if b is not None and b.objectName() == "btnDownload"]
        assert telecharger and telecharger[0].isEnabled()

    def test_pas_de_mention_hors_ligne_sur_un_jeu_installe(self, panel, monkeypatch):
        """Il reste parfaitement jouable : le dire serait du bruit."""
        widget, manager = panel
        _disque(monkeypatch, 900_000)
        _prepare(panel, GameState.INSTALLED)
        widget.set_online(False)
        assert widget._alert.isHidden()


class TestPrerequisVCredist:
    def test_bandeau_sur_un_jeu_installe(self, panel, monkeypatch):
        widget, manager = panel
        monkeypatch.setattr("src.core.system_checks.check_vcredist_x86", lambda: False)
        _prepare(panel, GameState.INSTALLED)
        assert "Visual C++" in widget._alert.text()
        assert 'href="vcredist_x86"' in widget._alert.text()

    def test_pas_avant_installation(self, panel, monkeypatch):
        """Rien à lancer encore : l'avertissement viendrait trop tôt."""
        widget, manager = panel
        monkeypatch.setattr("src.core.system_checks.check_vcredist_x86", lambda: False)
        _disque(monkeypatch, 900_000)
        _prepare(panel, GameState.NOT_INSTALLED)
        assert widget._alert.isHidden()

    def test_le_clic_arme_le_re_test_au_retour(self, panel, monkeypatch):
        """Sans re-test, l'avertissement survivrait à l'installation du paquet
        jusqu'au prochain démarrage — le launcher aurait l'air cassé."""
        widget, manager = panel
        ouvert = []
        monkeypatch.setattr("src.ui.action_panel.open_url", ouvert.append)
        monkeypatch.setattr("src.core.system_checks.check_vcredist_x86", lambda: False)
        _prepare(panel, GameState.INSTALLED)

        widget._on_alert_link("vcredist_x86")
        assert ouvert and "vc_redist" in ouvert[0]
        assert widget._awaiting_vcredist is True

        monkeypatch.setattr("src.core.system_checks.check_vcredist_x86", lambda: True)
        widget.recheck_prerequisites()
        assert widget._awaiting_vcredist is False
        assert widget._alert.isHidden()

    def test_recheck_est_muet_sans_demande(self, panel, monkeypatch):
        """Appelé à chaque activation de fenêtre : il ne doit RIEN reconstruire
        tant que l'utilisateur n'est pas parti installer quelque chose."""
        widget, manager = panel
        _disque(monkeypatch, 900_000)
        _prepare(panel, GameState.INSTALLED)
        appels = []
        monkeypatch.setattr(widget, "refresh", lambda: appels.append(1))
        widget.recheck_prerequisites()
        assert appels == []


class TestPriorite:
    """UN SEUL message. Empiler « hors ligne » et « espace insuffisant » coûtait
    80 px et ramenait la barre de défilement sur une fenêtre de 980×660 — pour
    un conseil qui n'est même pas actionnable : hors ligne, rien ne s'écrit."""

    def test_le_hors_ligne_prime_sur_le_disque(self, panel, monkeypatch):
        widget, manager = panel
        _disque(monkeypatch, 50)
        _prepare(panel, GameState.NOT_INSTALLED)
        widget.set_online(False)
        texte = widget._alert.text()
        assert "Hors ligne" in texte
        assert "Espace insuffisant" not in texte

    def test_le_disque_reapparait_une_fois_en_ligne(self, panel, monkeypatch):
        widget, manager = panel
        _disque(monkeypatch, 50)
        _prepare(panel, GameState.NOT_INSTALLED)
        widget.set_online(False)
        widget.set_online(True)
        assert "Espace insuffisant" in widget._alert.text()

    def test_jamais_deux_lignes(self, panel, monkeypatch):
        widget, manager = panel
        _disque(monkeypatch, 50)
        _prepare(panel, GameState.NOT_INSTALLED)
        widget.set_online(False)
        assert "<br>" not in widget._alert.text()

    def test_hauteur_nulle_quand_il_n_y_a_rien_a_dire(self, panel, monkeypatch):
        """`alert_height()` pilote le budget du panneau d'info : il DOIT valoir
        0 dans le cas nominal, sinon on raccourcit la description pour rien."""
        widget, manager = panel
        _disque(monkeypatch, 900_000)
        _prepare(panel, GameState.NOT_INSTALLED)
        assert widget.alert_height() == 0
        widget.set_online(False)
        assert widget.alert_height() > 0


class TestAvertissementDuCatalogue:
    """Mise en garde attachée à UN jeu par le catalogue.

    Cas réel : une DLL de HP7 partie 2 est mise en quarantaine par les
    antivirus. L'installation réussit, puis le jeu refuse de démarrer, et rien
    à l'écran ne relie les deux. Le message doit donc se voir AVANT le
    téléchargement (la demande de Ludo) **et** rester visible une fois le jeu
    installé, qui est le moment où l'utilisateur en a réellement besoin.

    Il reste au DERNIER rang : tout ce qui précède est bloquant ici et
    maintenant, lui ne l'est pas.
    """

    _TEXTE = ("Votre antivirus peut mettre en quarantaine un fichier de ce jeu "
              "pendant l'installation. S'il refuse de démarrer, restaurez ce "
              "fichier depuis la quarantaine de votre antivirus.")

    @staticmethod
    def _prepare(panel_fixture, state, **champs):
        import dataclasses
        widget, manager = panel_fixture
        game = dataclasses.replace(_jeu_telechargeable(manager), **champs)
        manager.set_game_state(game.id, state)
        widget.set_game(game)
        widget.refresh()
        return widget

    def test_visible_avant_telechargement(self, panel, monkeypatch):
        _disque(monkeypatch, 900_000)
        widget = self._prepare(panel, GameState.NOT_INSTALLED, warning=self._TEXTE)
        assert "quarantaine" in widget._alert.text()
        assert widget.alert_height() > 0

    def test_visible_une_fois_installe(self, panel, monkeypatch):
        """Le moment qui compte : le jeu est là et ne démarre pas."""
        _disque(monkeypatch, 900_000)
        widget = self._prepare(panel, GameState.INSTALLED, warning=self._TEXTE)
        assert "quarantaine" in widget._alert.text()

    def test_rien_sans_avertissement_au_catalogue(self, panel, monkeypatch):
        """Les sept autres jeux ne doivent rien afficher du tout."""
        _disque(monkeypatch, 900_000)
        widget = self._prepare(panel, GameState.NOT_INSTALLED)
        assert widget._alert.isHidden()
        assert widget.alert_height() == 0

    def test_muet_pendant_le_telechargement(self, panel, monkeypatch):
        """Prévenir pendant l'opération n'aide plus : c'est trop tard, et la
        zone d'action est déjà occupée par la barre et le stepper."""
        _disque(monkeypatch, 900_000)
        widget = self._prepare(panel, GameState.DOWNLOADING, warning=self._TEXTE)
        assert widget._alert.isHidden()

    def test_cede_le_pas_au_hors_ligne(self, panel, monkeypatch):
        _disque(monkeypatch, 900_000)
        widget = self._prepare(panel, GameState.NOT_INSTALLED, warning=self._TEXTE)
        widget.set_online(False)
        texte = widget._alert.text()
        assert "Hors ligne" in texte
        assert "quarantaine" not in texte

    def test_cede_le_pas_a_l_espace_disque(self, panel, monkeypatch):
        _disque(monkeypatch, 50)
        widget = self._prepare(panel, GameState.NOT_INSTALLED, warning=self._TEXTE)
        texte = widget._alert.text()
        assert "Espace insuffisant" in texte
        assert "quarantaine" not in texte

    def test_cede_le_pas_au_prerequis_manquant(self, panel, monkeypatch):
        monkeypatch.setattr("src.core.system_checks.check_vcredist_x86", lambda: False)
        from src.core.system_checks import invalidate_vcredist_cache
        invalidate_vcredist_cache()
        _disque(monkeypatch, 900_000)
        widget = self._prepare(panel, GameState.INSTALLED, warning=self._TEXTE)
        texte = widget._alert.text()
        assert "manquant" in texte
        assert "quarantaine" not in texte
        invalidate_vcredist_cache()

    def test_toujours_une_seule_ligne_de_message(self, panel, monkeypatch):
        _disque(monkeypatch, 50)
        widget = self._prepare(panel, GameState.NOT_INSTALLED, warning=self._TEXTE)
        assert "<br>" not in widget._alert.text()

    def test_lien_seulement_si_le_catalogue_donne_une_url(self, panel, monkeypatch):
        _disque(monkeypatch, 900_000)
        widget = self._prepare(panel, GameState.NOT_INSTALLED, warning=self._TEXTE)
        assert "En savoir plus" not in widget._alert.text()
        widget = self._prepare(panel, GameState.NOT_INSTALLED, warning=self._TEXTE,
                               warning_url="https://acciolauncher.be/aide/antivirus")
        assert "En savoir plus" in widget._alert.text()

    def test_le_lien_ouvre_l_url_du_catalogue(self, panel, monkeypatch):
        ouvertes = []
        monkeypatch.setattr("src.ui.action_panel.open_url", ouvertes.append)
        _disque(monkeypatch, 900_000)
        widget = self._prepare(panel, GameState.NOT_INSTALLED, warning=self._TEXTE,
                               warning_url="https://acciolauncher.be/aide/antivirus")
        widget._on_alert_link("avertissement")
        assert ouvertes == ["https://acciolauncher.be/aide/antivirus"]

    def test_pas_de_lien_mort_si_l_url_a_ete_refusee(self, panel, monkeypatch):
        """Une URL non-https est vidée au parsing : le texte doit rester, mais
        sans lien, et un clic ne doit rien ouvrir."""
        ouvertes = []
        monkeypatch.setattr("src.ui.action_panel.open_url", ouvertes.append)
        _disque(monkeypatch, 900_000)
        widget = self._prepare(panel, GameState.NOT_INSTALLED, warning=self._TEXTE,
                               warning_url="")
        assert "En savoir plus" not in widget._alert.text()
        widget._on_alert_link("avertissement")
        assert ouvertes == []


class TestPlafondDuBandeau:
    """Le texte vient du CATALOGUE, donc de l'extérieur et sans passer par une
    build : la mise en page ne peut pas dépendre de sa longueur.

    Mesuré sur la plateforme native : un bandeau d'une ligne fait 33 px, deux
    lignes 54, trois 75 — et 75 px ramènent la barre de défilement à 980×660,
    exactement le prix des deux avertissements empilés que le projet s'interdit
    déjà. On élide donc à deux lignes, et « En savoir plus » porte la suite.
    """

    _LONG = ("Votre antivirus peut mettre en quarantaine un fichier de ce jeu pendant "
             "l'installation, ce qui empêche le jeu de démarrer ensuite. Si cela vous "
             "arrive, restaurez ce fichier depuis la quarantaine de votre antivirus, "
             "puis relancez le jeu depuis le launcher comme d'habitude.")

    @staticmethod
    def _pose(panel_fixture, texte, url=""):
        import dataclasses
        widget, manager = panel_fixture
        game = dataclasses.replace(_jeu_telechargeable(manager),
                                   warning=texte, warning_url=url)
        manager.set_game_state(game.id, GameState.NOT_INSTALLED)
        widget.set_game(game)
        widget.refresh()
        return widget

    @staticmethod
    def _lignes(widget):
        from PyQt6.QtGui import QFontMetrics
        fm = QFontMetrics(widget._alert.font())
        return round(widget._alert.minimumHeight() / fm.lineSpacing())

    def test_un_texte_court_n_est_pas_touche(self, panel, monkeypatch):
        _disque(monkeypatch, 900_000)
        widget = self._pose(panel, "Une DLL peut être bloquée par votre antivirus.")
        assert "…" not in widget._alert.text()

    def test_un_texte_long_est_elide(self, panel, monkeypatch):
        _disque(monkeypatch, 900_000)
        widget = self._pose(panel, self._LONG)
        assert widget._alert.text().endswith("…")
        assert self._lignes(widget) <= 2

    def test_elide_aussi_avec_le_lien(self, panel, monkeypatch):
        """Le « En savoir plus » s'ajoute à la DERNIÈRE ligne : c'est lui qui la
        fait déborder, il doit donc entrer dans la mesure."""
        _disque(monkeypatch, 900_000)
        widget = self._pose(panel, self._LONG, url="https://acciolauncher.be/aide")
        assert "En savoir plus" in widget._alert.text()
        assert self._lignes(widget) <= 2

    def test_le_debut_du_message_survit(self, panel, monkeypatch):
        """Élider n'est utile que si l'essentiel tient dans ce qui reste."""
        _disque(monkeypatch, 900_000)
        widget = self._pose(panel, self._LONG)
        assert widget._alert.text().startswith("Votre antivirus peut mettre en quarantaine")

    def test_un_pave_ne_fait_pas_grandir_le_bandeau(self, panel, monkeypatch):
        """Pire cas : un catalogue qui envoie un mur de texte."""
        _disque(monkeypatch, 900_000)
        court = self._pose(panel, "Court.")
        h_court = court.alert_height()
        pave = self._pose(panel, "Blabla très long. " * 80)
        assert pave.alert_height() <= max(h_court * 2, 60)
        assert self._lignes(pave) <= 2


class TestAiguillageLigneMeta:
    """La ligne méta porte deux liens : changelog et langue du jeu.

    Testé sur un InfoPanel ISOLÉ, jamais sur une vraie fenêtre : là-bas
    `versions_clicked` est câblé au dialogue des versions, dont le `exec()`
    bloquerait la suite de tests pour toujours (constaté).
    """

    def test_chaque_href_va_au_bon_signal(self, qtbot, tmp_path, monkeypatch):
        from src.core.config import Config
        from src.core.game_manager import GameManager
        from src.ui.info_panel import InfoPanel

        cfg = Config(install_path=tmp_path / "g", cache_path=tmp_path / "g" / ".cache")
        panel = InfoPanel(GameManager(cfg))
        qtbot.addWidget(panel)
        recus = []
        panel.versions_clicked.connect(lambda: recus.append("versions"))
        panel.language_clicked.connect(lambda: recus.append("langue"))

        panel._on_meta_link("changelog")
        panel._on_meta_link("langue")
        assert recus == ["versions", "langue"]

    def test_un_href_inconnu_ne_declenche_pas_la_langue(self, qtbot, tmp_path):
        """Repli sur le changelog, jamais sur une écriture registre."""
        from src.core.config import Config
        from src.core.game_manager import GameManager
        from src.ui.info_panel import InfoPanel

        cfg = Config(install_path=tmp_path / "g", cache_path=tmp_path / "g" / ".cache")
        panel = InfoPanel(GameManager(cfg))
        qtbot.addWidget(panel)
        recus = []
        panel.versions_clicked.connect(lambda: recus.append("versions"))
        panel.language_clicked.connect(lambda: recus.append("langue"))
        panel._on_meta_link("nimportequoi")
        assert recus == ["versions"]


class TestBalisageDuCatalogue:
    """Le bandeau est un QLabel en RichText et son texte vient du CATALOGUE.

    Sans echappement, un `<img src="http://...">` declenchait une requete reseau
    a l'affichage de la fiche — donc « qui regarde quel jeu » partait chez
    l'hebergeur de l'image — et n'importe quel balisage pouvait defaire la mise
    en page qu'on venait de border.
    """

    @staticmethod
    def _pose(panel_fixture, texte, url=""):
        import dataclasses
        widget, manager = panel_fixture
        game = dataclasses.replace(_jeu_telechargeable(manager),
                                   warning=texte, warning_url=url)
        manager.set_game_state(game.id, GameState.NOT_INSTALLED)
        widget.set_game(game)
        widget.refresh()
        return widget

    def test_une_balise_est_neutralisee(self, panel, monkeypatch):
        _disque(monkeypatch, 900_000)
        widget = self._pose(panel, "Attention <b>gros</b> souci")
        rendu = widget._alert.text()
        assert "<b>" not in rendu
        assert "&lt;b&gt;" in rendu

    def test_pas_d_image_distante(self, panel, monkeypatch):
        """Le cas qui fuite vraiment : une image chargee depuis un serveur."""
        _disque(monkeypatch, 900_000)
        widget = self._pose(panel, 'Souci <img src="http://pisteur.example/x.png"> ici')
        assert "<img" not in widget._alert.text()

    def test_pas_de_lien_injecte(self, panel, monkeypatch):
        _disque(monkeypatch, 900_000)
        widget = self._pose(panel, 'Cliquez <a href="file:///C:/">ici</a>')
        rendu = widget._alert.text()
        assert rendu.count("<a ") == 0        # aucun lien : pas de warning_url

    def test_notre_lien_reste_un_vrai_lien(self, panel, monkeypatch):
        """L'echappement ne doit pas neutraliser le lien qu'on ajoute NOUS."""
        _disque(monkeypatch, 900_000)
        widget = self._pose(panel, "Souci", url="https://acciolauncher.be/aide")
        assert '<a href="avertissement"' in widget._alert.text()

    def test_les_esperluettes_survivent_a_l_elision(self, panel, monkeypatch):
        """L'elision porte sur le texte BRUT : couper une chaine deja echappee
        trancherait une entite en deux (`&amp;` -> `&am`)."""
        _disque(monkeypatch, 900_000)
        widget = self._pose(panel, "Ron & Hermione " * 40)
        rendu = widget._alert.text()
        assert "&am" not in rendu.replace("&amp;", "")
        assert rendu.endswith(chr(8230))      # ellipse

    def test_le_libelle_de_langue_est_echappe(self, qtbot, tmp_path):
        """Meme exposition dans la ligne meta, qui est aussi du RichText."""
        import dataclasses

        from src.core.config import Config
        from src.core.game_data import _parse_language_registry
        from src.core.game_manager import GameManager
        from src.ui.info_panel import InfoPanel

        cfg = Config(install_path=tmp_path / "g", cache_path=tmp_path / "g" / ".cache")
        manager = GameManager(cfg)
        bloc = _parse_language_registry({
            "root": "HKCU", "view": 32,
            "key": chr(92).join(["Software", "Editeur", "Jeu"]),
            "languages": {"fr": {"label": "<b>Francais</b>",
                                 "values": {"Language": "French"}}},
        })
        assert bloc is not None
        panel = InfoPanel(manager)
        qtbot.addWidget(panel)
        jeu = dataclasses.replace(manager.get_games()[0].game, language_registry=bloc)
        panel.apply_game(jeu)
        assert "<b>" not in panel._meta.text()
        assert "&lt;b&gt;" in panel._meta.text()
