"""Une VRAIE MainWindow : la mise en page de la fiche (troncature, défilement,
bandeau, titre, langues) et le texte du catalogue jamais interprété.

Config temporaire (CONFIG_FILE_PATH patché), `_start_update_check` neutralisé,
autoplay=False. Fixtures `make_window*` dans `conftest.py`.
"""

import pathlib

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import Qt  # noqa: E402

from tests.fenetre_commune import (  # noqa: E402
    _CATALOG,
)


class TestCrossfade:
    def test_old_frame_kept_until_fade_completes(self, make_window):
        win = make_window()
        win.show()
        win.resize(1200, 800)
        bg = win._detail._bg
        bg._ensure_prepared()
        if bg._prepared is None:
            pytest.skip("backgrounds absents du repo de test")
        win._detail.set_game(_CATALOG.games[1])
        assert bg._old_frame is not None  # l'ancien rendu sert de sous-couche
        bg.bg_opacity = 1.0  # fade terminé
        assert bg._old_frame is None  # snapshot libéré


class TestPasDeTroncature:
    """Régressions de mise en page : le texte ne doit jamais être coupé.

    Le panneau d'info est positionné en `setGeometry` à 50 % de la fenêtre.
    Des largeurs figées en pixels (600 / 520) le débordaient dès que la fenêtre
    passait sous ~1100 px.
    """

    TAILLES = ((1200, 800), (980, 660), (1600, 900))

    @staticmethod
    def _jeu_le_plus_charge(win):
        return max((e.game for e in win.manager.get_games()), key=lambda g: len(g.name) + len(g.description))

    def test_titre_et_description_tiennent_dans_le_panneau(self, make_window, qtbot, mise_en_page_stable):
        win = make_window()
        win.show()
        info = win._detail._info
        for w, h in self.TAILLES:
            win.resize(w, h)
            mise_en_page_stable(win)
            win._detail.set_game(self._jeu_le_plus_charge(win))
            mise_en_page_stable(win)
            assert info._title.width() <= info.available_width(), (
                f"titre plus large que le panneau en {w}x{h}")
            assert info._desc.width() <= info.available_width(), (
                f"description plus large que le panneau en {w}x{h}")
            besoin = info._title.heightForWidth(info._title.width())
            assert info._title.height() >= besoin, (
                f"titre amputé en {w}x{h} : {info._title.height()} px pour {besoin} px de texte")


class TestDescriptionEntreJeux:
    """Le libellé de description ne doit pas garder la hauteur du jeu précédent.

    Scénario signalé : déplier la description d'un jeu « bientôt disponible »
    puis revenir sur un autre jeu laissait un grand vide sous un texte court,
    parce que `minimumHeight` gardait la valeur de l'état déplié.
    """

    @staticmethod
    def _besoin(label) -> int:
        # heightForWidth() renvoie max(minimumHeight, calcul) : remettre le
        # minimum à zéro est le seul moyen d'obtenir la hauteur réelle du texte.
        garde = label.minimumHeight()
        label.setMinimumHeight(0)
        besoin = label.heightForWidth(label.width())
        label.setMinimumHeight(garde)
        return besoin

    def test_hauteur_suit_le_texte_apres_changement_de_jeu(self, make_window_jeu_a_venir,
                                                          qtbot, mise_en_page_stable):
        win, soon = make_window_jeu_a_venir()
        win.show()
        info = win._detail._info
        autre = next(e.game for e in win.manager.get_games() if e.game.is_downloadable)

        win._detail.set_game(soon)
        mise_en_page_stable(win)
        info._toggle_desc()               # « Lire la suite »
        mise_en_page_stable(win)
        assert info._desc_expanded is True

        win._detail.set_game(autre)
        mise_en_page_stable(win)
        assert info._desc_expanded is False, "le dépliage ne doit pas survivre au changement"
        ecart = info._desc.height() - self._besoin(info._desc)
        assert abs(ecart) <= 2, f"{ecart} px de vide sous la description"

    def test_bouton_coherent_avec_le_texte(self, make_window, qtbot, mise_en_page_stable):
        """« Lire la suite » ne s'affiche que si du texte est réellement caché."""
        win = make_window()
        win.show()
        info = win._detail._info
        for entry in win.manager.get_games():
            win._detail.set_game(entry.game)
            mise_en_page_stable(win)
            tronque = info._desc.text() != info._full_desc
            assert info._btn_expand.isVisible() == tronque, (
                f"{entry.game.id} : bouton={info._btn_expand.isVisible()} "
                f"alors que tronqué={tronque}")



def _reste_a_defiler(qtbot, win, timeout: int = 1000) -> int:
    """Ce qui défile ENCORE une fois la mise en page finie. Une attente fixe
    (20 ms) mesurait au milieu des passes de `_fit_info_height`, qui se
    réarment : chaque étape d'ajustement ajoutée rendait le test faux."""
    from pytestqt.exceptions import TimeoutError as Delai
    barre = win._detail._info._scroll.verticalScrollBar()
    try:
        qtbot.waitUntil(lambda: barre.maximum() == 0, timeout=timeout)
    except Delai:
        pass
    return barre.maximum()

class TestBandeauSansScrollbar:
    """« Pas de scroll si on a pas ouvert la suite d'une description » (Ludo).

    Un bandeau d'avertissement de deux lignes faisait déborder le panneau de
    20 px sur une fenêtre au minimum syndical et ramenait la barre. Le budget
    de description a donc un troisième palier, et le bandeau n'affiche qu'un
    seul message à la fois.
    """

    @staticmethod
    def _disque(monkeypatch, free_mb):
        from collections import namedtuple
        usage = namedtuple("usage", "total used free")
        monkeypatch.setattr("src.core.game_manager.shutil.disk_usage",
                            lambda _p: usage(0, 0, free_mb * 1024 * 1024))

    def _balaye(self, win, qtbot, taille):
        """Toutes les fiches à une taille donnée → liste des débordements."""
        win.resize(*taille)
        qtbot.wait(30)
        deborde = []
        for entry in win.manager.get_games():
            win._detail.set_game(entry.game)
            trop = _reste_a_defiler(qtbot, win)
            if trop > 0:
                deborde.append((entry.game.id, trop))
        return deborde

    @pytest.mark.parametrize("taille", [(980, 660), (1100, 720), (1320, 880)])
    def test_hors_ligne(self, make_window, qtbot, monkeypatch, taille):
        self._disque(monkeypatch, 900_000)
        win = make_window()
        win.show()
        win._on_network_status(False)
        qtbot.wait(30)
        assert self._balaye(win, qtbot, taille) == []

    @pytest.mark.parametrize("taille", [(980, 660), (1100, 720), (1320, 880)])
    def test_disque_plein(self, make_window, qtbot, monkeypatch, taille):
        self._disque(monkeypatch, 40)
        win = make_window()
        win.show()
        assert self._balaye(win, qtbot, taille) == []

    @pytest.mark.parametrize("taille", [(980, 660), (1320, 880)])
    def test_prerequis_manquant_sur_jeux_installes(self, make_window, qtbot,
                                                   monkeypatch, taille):
        from src.core.game_manager import GameState
        self._disque(monkeypatch, 900_000)
        monkeypatch.setattr("src.core.system_checks.check_vcredist_x86", lambda: False)
        win = make_window()
        win.show()
        for entry in win.manager.get_games():
            win.manager.set_game_state(entry.game.id, GameState.INSTALLED)
        assert self._balaye(win, qtbot, taille) == []

    # Texte réaliste, volontairement long : c'est le catalogue qui l'écrit, à
    # distance, et personne ne relancera cette suite avant de le publier.
    _AVERTISSEMENT = (
        "Votre antivirus peut mettre en quarantaine un fichier de ce jeu pendant "
        "l'installation. S'il refuse de démarrer, restaurez ce fichier depuis la "
        "quarantaine de votre antivirus."
    )

    @staticmethod
    def _catalogue_avec_avertissement(monkeypatch, url=""):
        """Colle la mise en garde sur TOUS les jeux — pire cas de mise en page."""
        import dataclasses

        from src.core import game_manager
        vrai_load = game_manager.load_catalog

        def _charge(*a, **k):
            cat = vrai_load(*a, **k)
            return dataclasses.replace(cat, games=tuple(
                dataclasses.replace(
                    g, warning=TestBandeauSansScrollbar._AVERTISSEMENT,
                    warning_url=url)
                for g in cat.games))

        monkeypatch.setattr(game_manager, "load_catalog", _charge)

    @pytest.mark.parametrize("taille", [(980, 660), (1100, 720), (1320, 880)])
    def test_avertissement_du_catalogue_avant_telechargement(
            self, make_window, qtbot, monkeypatch, taille):
        self._disque(monkeypatch, 900_000)
        self._catalogue_avec_avertissement(monkeypatch)
        win = make_window()
        win.show()
        assert self._balaye(win, qtbot, taille) == []

    @pytest.mark.parametrize("taille", [(980, 660), (1320, 880)])
    def test_avertissement_du_catalogue_avec_lien(
            self, make_window, qtbot, monkeypatch, taille):
        """Le « En savoir plus » allonge la dernière ligne — cas le plus large."""
        self._disque(monkeypatch, 900_000)
        self._catalogue_avec_avertissement(
            monkeypatch, url="https://acciolauncher.be/aide/antivirus")
        win = make_window()
        win.show()
        assert self._balaye(win, qtbot, taille) == []

    @pytest.mark.parametrize("taille", [(980, 660), (1320, 880)])
    def test_avertissement_du_catalogue_sur_jeux_installes(
            self, make_window, qtbot, monkeypatch, taille):
        from src.core.game_manager import GameState
        self._disque(monkeypatch, 900_000)
        self._catalogue_avec_avertissement(monkeypatch)
        win = make_window()
        win.show()
        for entry in win.manager.get_games():
            win.manager.set_game_state(entry.game.id, GameState.INSTALLED)
        assert self._balaye(win, qtbot, taille) == []

    def test_le_bandeau_est_bien_la_pendant_le_balayage(
            self, make_window, qtbot, monkeypatch):
        """Garde-fou : sans lui, les trois tests ci-dessus passeraient à vide
        si le mécanisme d'avertissement cessait d'afficher quoi que ce soit."""
        self._disque(monkeypatch, 900_000)
        self._catalogue_avec_avertissement(monkeypatch)
        win = make_window()
        win.show()
        win.resize(980, 660)
        qtbot.wait(30)
        for entry in win.manager.get_games():
            win._detail.set_game(entry.game)
            qtbot.wait(20)
            assert win._detail._action_panel.alert_height() > 0
            assert "quarantaine" in win._detail._action_panel._alert.text()

    def test_le_bandeau_n_affiche_qu_un_message(self, make_window, qtbot, monkeypatch):
        """Hors ligne ET disque plein : le hors-ligne prime, le disque attend
        d'être actionnable (hors ligne, rien ne s'écrit sur le disque)."""
        self._disque(monkeypatch, 40)
        win = make_window()
        win.show()
        win._on_network_status(False)
        qtbot.wait(30)
        texte = win._detail._action_panel._alert.text()
        assert "Hors ligne" in texte
        assert "Espace insuffisant" not in texte


class TestCoutureCarrousel:
    """« Il y a une ligne de pixel bizarre juste au dessus de la liste de jeu ».

    Le carrousel est un widget FRÈRE : il ne montre pas l'illustration, donc là
    où son dégradé est transparent on voit le fond plat du conteneur. Le bas de
    la fiche, lui, était assombri sous cette couleur par la vignette radiale
    (rgb(3,3,8) contre rgb(6,6,17)) — un trait clair sur toute la largeur, de
    valeur IDENTIQUE sur les 8 jeux, ce qui a permis de l'imputer au rendu et
    non aux images.
    """

    def _ecart(self, win, stable):
        """Somme |dRGB| max entre la dernière ligne de la fiche et la première
        du carrousel, échantillonnée sur toute la largeur.

        TOUTE la décoration animée est neutralisée avant de mesurer, parce
        qu'elle traverse la frontière sans être ce qu'on teste :
        - les particules, qui passent au-dessus des deux widgets ;
        - les étoiles scintillantes du carrousel, tirées à des positions
          ALÉATOIRES à la construction. Quand l'une tombe sur la première ligne
          du carrousel, elle éclaircit 2 à 4 colonnes sur 1000 (pic mesuré :
          95/765) et le test échoue pour la mauvaise raison.

        Ne masquer que les particules laissait le test instable : 14 échecs sur
        30 en reproduction directe. Le pixel du HAUT, lui, valait toujours
        exactement bg_qcolor(255) — le raccord n'a jamais fauté, seule la
        mesure était contaminée.
        """
        win._particles.hide()
        win._carousel._stars.clear()   # décor aléatoire : fausserait la mesure
        win._carousel.update()
        stable(win)
        img = win.grab().toImage()
        haut = win._carousel.mapTo(win, win._carousel.rect().topLeft()).y()
        pire = 0
        for x in range(4, win.width() - 4, 11):
            a = img.pixelColor(x, haut - 1)
            b = img.pixelColor(x, haut)
            pire = max(pire, abs(a.red() - b.red()) + abs(a.green() - b.green())
                       + abs(a.blue() - b.blue()))
        return pire

    def test_aucune_marche_sur_aucun_jeu(self, make_window, mise_en_page_stable):
        win = make_window()
        win.resize(1320, 880)
        win.show()
        mise_en_page_stable(win)
        for entry in win.manager.get_games():
            win._detail.set_game(entry.game)
            ecart = self._ecart(win, mise_en_page_stable)
            assert ecart == 0, (
                f"{entry.game.id} : marche de {ecart}/765 au-dessus du carrousel")

    def test_tient_aussi_en_carrousel_compact(self, make_window, mise_en_page_stable):
        """Sous 780 px de haut le carrousel se compacte : le raccord suit."""
        win = make_window()
        win.resize(1000, 700)
        win.show()
        mise_en_page_stable(win)
        assert self._ecart(win, mise_en_page_stable) == 0


class TestRecuperationDuVideDuHaut:
    """Avant de rogner du TEXTE, la fiche récupère du VIDE.

    Le retrait au-dessus du panneau vaut 10 % de la fiche (49 px à 980×660) et
    ne porte aucune information : remonter le panneau ne coûte rien à
    l'utilisateur, là où un cran d'accroche en moins lui coûte deux lignes.

    Le cas qui l'a imposé existait AVANT le bandeau du catalogue : en espagnol,
    à 980×660, l'avertissement d'espace disque faisait déjà défiler la fiche de
    HP7 de 20 px. Il ne se reproduit pas ici — la suite tourne en `offscreen`,
    où Qt substitue une autre police — donc on teste le MÉCANISME, et la mesure
    en vraies polices est faite par `tools/audit_geometrie.py` (scénario
    « bandeau », qui échoue si ce correctif disparaît).
    """

    @staticmethod
    def _force_debordement(win, pixels):
        """Fait croire au panneau qu'il déborde, sans toucher à la classe Qt.

        Attribut d'INSTANCE : remplacer `InfoPanel.overflow` au niveau de la
        classe laisserait un descripteur sip posé pour toute la session, et le
        processus meurt plusieurs fichiers de tests plus loin.
        """
        win._detail._info.overflow = lambda: pixels

    def test_le_panneau_remonte_au_lieu_de_rogner(self, make_window, qtbot, mise_en_page_stable):
        win = make_window()
        win.show()
        win.resize(980, 660)
        mise_en_page_stable(win)
        nominal = win._detail._info.y()
        assert nominal > 0

        self._force_debordement(win, 30)
        win._detail._position_info()
        # `waitUntil` et non un `wait` fixe : la remontée se fait par une
        # chaîne de `singleShot(0)` qui se réarme, donc en plusieurs tours de
        # boucle d'évènements. 80 ms suffisent à vide et pas toujours sous la
        # charge de la suite complète — un test qui échoue une fois sur dix
        # arrête `build.bat` au hasard, ce qui est pire qu'une absence de test.
        qtbot.waitUntil(lambda: win._detail._info.y() < nominal, timeout=3000)

    def test_jamais_sous_le_plancher(self, make_window, qtbot, mise_en_page_stable):
        """Un débordement énorme ne doit pas coller le titre à la barre."""
        from src.ui.game_detail import _INFO_TOP_MIN
        win = make_window()
        win.show()
        win.resize(980, 660)
        mise_en_page_stable(win)
        self._force_debordement(win, 10_000)
        win._detail._position_info()
        qtbot.waitUntil(lambda: win._detail._info.y() <= _INFO_TOP_MIN, timeout=3000)
        assert win._detail._info.y() >= _INFO_TOP_MIN

    def test_le_retrait_nominal_revient_au_redimensionnement(self, make_window, qtbot, mise_en_page_stable):
        """`_position_info` repart du retrait nominal : un resserrement décidé
        pour une petite fenêtre ne doit pas survivre à son agrandissement."""
        win = make_window()
        win.show()
        win.resize(980, 660)
        mise_en_page_stable(win)
        nominal = win._detail._info.y()
        self._force_debordement(win, 30)
        win._detail._position_info()
        qtbot.waitUntil(lambda: win._detail._info.y() < nominal, timeout=3000)
        remonte = win._detail._info.y()

        del win._detail._info.overflow      # le panneau ne déborde plus
        win.resize(1320, 880)
        qtbot.waitUntil(lambda: win._detail._info.y() > remonte, timeout=3000)


@pytest.mark.usefixtures("registre_atteignable")
class TestSelecteurDeLangue:
    """La langue du jeu N'EST PLUS dans la ligne méta (Ludo, 2026-08-26).

    Elle y a vécu du 2026-08-21 au 2026-08-26, en segment doré cliquable. Le
    grief est simple et il est de fond : ce segment affichait « FRANÇAIS »,
    c'est-à-dire un ÉTAT NORMAL — la chose même que le projet s'interdit
    partout ailleurs (« espace libre : 412 Go », « en ligne », « prérequis
    OK »). Un état ne s'affiche que lorsqu'il DÉVIE ; celui-ci ne dévie
    jamais. Il occupait donc en permanence la ligne la plus contrainte de la
    fiche pour n'apprendre rien à personne.

    Rien n'est perdu : l'engrenage s'affiche sous EXACTEMENT la même condition
    (cf. `TestEngrenageReglagesDuJeu`) et nomme le réglage au lieu de le faire
    deviner. Ces tests-ci gardent donc l'ABSENCE, et le comportement d'écriture
    reste vérifié plus bas.
    """

    def test_la_ligne_meta_ne_porte_plus_la_langue(self, make_window_multilingue):
        win, jeu = make_window_multilingue()
        win._detail.set_game(jeu)
        meta = win._detail._info._meta.text()
        assert 'href="langue"' not in meta
        # Et pas davantage en clair : retirer le lien en laissant le mot aurait
        # gardé le bruit tout en supprimant le raccourci.
        assert "Fran" not in meta

    def test_absent_sur_les_autres_jeux(self, make_window_multilingue):
        """Sept jeux sur huit n'ont pas de bloc : un réglage sans choix
        possible est du bruit."""
        win, _ = make_window_multilingue()
        autre = win.manager.get_games()[1].game
        win._detail.set_game(autre)
        assert 'href="langue"' not in win._detail._info._meta.text()

    def test_la_version_a_quitte_la_fiche(self, make_window_multilingue):
        """L'AIGUILLAGE lui-même est testé sur un panneau isolé
        (`TestAiguillageLigneMeta`) : sur une vraie fenêtre, `versions_clicked`
        est câblé au dialogue des versions, dont le `exec()` bloque la suite de
        tests indéfiniment."""
        win, jeu = make_window_multilingue()
        win._detail.set_game(jeu)
        # La ligne méta n'a AUCUN lien ; la version est partie dans l'engrenage
        # (« Gérer les versions », maquette « Plan du launcher v2 », 2026-10-26).
        assert "href=" not in win._detail._info._meta.text()
        indices = win._detail._info._indices.text()
        assert 'href="changelog"' not in indices and "VERSION" not in indices.upper()

    def test_le_choix_est_bien_retenu(self, make_window_multilingue):
        """Le réglage vit toujours — il ne s'AFFICHE simplement plus sur la fiche."""
        win, jeu = make_window_multilingue()
        win._detail.set_game(jeu)
        win.manager.set_game_language(jeu.id, "de")
        assert win.manager.game_language(jeu) == "de"
        assert "Deutsch" not in win._detail._info._meta.text()

    def test_le_clic_ecrit_le_registre(self, make_window_multilingue,
                                       monkeypatch, qtbot):
        win, jeu = make_window_multilingue()
        win._detail.set_game(jeu)
        ecrits = []
        monkeypatch.setattr("src.core.game_language.registre.ecrire_valeurs",
                            lambda *a, **k: ecrits.append(a) or True)
        from src.ui import game_detail_handlers as handlers
        handlers._appliquer_langue(win._detail, "en")
        qtbot.wait(20)
        assert win.manager.game_language(jeu) == "en"
        assert ecrits and ecrits[0][2] == {"Language": "English", "Locale": "en_US"}

    def test_un_echec_de_registre_previent_par_un_modal(self, make_window_multilingue,
                                                        monkeypatch):
        """UAC refusé : le choix est enregistré mais SANS effet. Un toast qui
        s'efface laisserait croire que c'est fait — donc un modal."""
        win, jeu = make_window_multilingue()
        win._detail.set_game(jeu)
        monkeypatch.setattr("src.core.game_language.registre.ecrire_valeurs",
                            lambda *a, **k: False)
        vus = []
        monkeypatch.setattr("src.ui.game_detail_handlers._boite",
                            lambda *a, **k: vus.append(a))
        from src.ui import game_detail_handlers as handlers
        avant = win.manager.game_language(jeu)
        handlers._appliquer_langue(win._detail, "en")
        assert len(vus) == 1
        # ET le choix ne doit PAS être enregistré : sinon la fiche annoncerait
        # une langue que le jeu n'a pas, et chaque lancement redemanderait
        # l'élévation pour un écart que l'utilisateur a déjà refusé de corriger.
        assert jeu.id not in win.manager.config.game_language
        assert win.manager.game_language(jeu) == avant

    def test_choisir_la_langue_deja_active_ne_fait_rien(self, make_window_multilingue,
                                                        monkeypatch):
        win, jeu = make_window_multilingue()
        win._detail.set_game(jeu)
        ecrits = []
        monkeypatch.setattr("src.core.game_language.registre.ecrire_valeurs",
                            lambda *a, **k: ecrits.append(a) or True)
        from src.ui import game_detail_handlers as handlers
        handlers._appliquer_langue(win._detail, win.manager.game_language(jeu))
        assert ecrits == []


class TestTailleDuTitre:
    """`_apply_title_size` était DU CODE MORT, et personne ne l'a vu.

    `styles.py` pose une règle applicative `QLabel#gameTitle { font-size: 36px }`,
    et en Qt une feuille de style l'emporte sur la police posée par `setFont` :
    les trois paliers de la fonction ne changeaient donc rien (mesuré le
    2026-08-21 : hauteur du titre identique AU PIXEL de 36 à 26, interligne
    bloqué à 48).

    Ces tests passent par une VRAIE MainWindow, et c'est le point : sur un
    `InfoPanel` construit tout seul, la feuille applicative n'est pas là, le
    `setFont` fonctionne, et le défaut ne se reproduit pas. C'est exactement
    l'angle mort qui l'a laissé vivre.
    """

    @staticmethod
    def _titre(win):
        return win._detail._info._title

    def test_la_taille_passe_par_le_stylesheet(self, make_window, qtbot):
        win = make_window()
        win.show()
        qtbot.wait(40)
        assert "font-size" in self._titre(win).styleSheet()

    def test_le_squeeze_reduit_vraiment_la_hauteur(self, make_window, qtbot):
        """LE test qui manquait : avec `setFont`, la hauteur ne bougeait pas."""
        win = make_window()
        win.show()
        win.resize(980, 660)
        qtbot.wait(60)
        info = win._detail._info
        titre = self._titre(win)
        largeur = titre.maximumWidth()
        titre.setMinimumHeight(0)
        avant = titre.heightForWidth(largeur)

        assert info.squeeze_title() is True
        titre.setMinimumHeight(0)
        apres = titre.heightForWidth(largeur)
        assert apres < avant, "le titre doit RÉTRÉCIR (régression du code mort)"

    def test_le_squeeze_est_borne(self, make_window, qtbot):
        win = make_window()
        win.show()
        qtbot.wait(40)
        info = win._detail._info
        crans = 0
        while info.squeeze_title():
            crans += 1
            assert crans < 10, "squeeze_title ne s'arrête jamais"
        assert crans >= 1

    def test_pas_de_fuite_d_un_jeu_a_l_autre(self, make_window, qtbot):
        """Un cran arraché par le titre le plus long ne doit pas rapetisser le
        titre des sept autres jeux — même fuite d'état que la sélection du
        carrousel, corrigée le même jour."""
        win = make_window()
        win.show()
        win.resize(980, 660)
        qtbot.wait(60)
        info = win._detail._info
        jeux = [e.game for e in win.manager.get_games()]

        win._detail.set_game(jeux[0])
        qtbot.wait(40)
        nominal = info._title_size

        info.squeeze_title()
        assert info._title_size < nominal

        win._detail.set_game(jeux[1])
        qtbot.wait(40)
        assert info._title_size == nominal


class TestPasDeScrollDansLeCasNominal:
    """Le garde-fou anti-scrollbar visait à côté.

    `TestBandeauSansScrollbar` balaye bien les 8 fiches à 3 tailles, mais ses
    trois scénarios activent TOUS un bandeau d'avertissement — or un bandeau
    raccourcit la description (3ᵉ palier du budget). Le cas d'un utilisateur
    ordinaire, sans avertissement, n'était jamais testé, et les états
    transitoires non plus : c'est ce qui a laissé passer une barre de
    défilement présente pendant TOUT le téléchargement, sur les 8 jeux et à
    toutes les tailles.
    """

    @staticmethod
    def _disque_large(monkeypatch):
        from collections import namedtuple
        usage = namedtuple("usage", "total used free")
        monkeypatch.setattr("src.core.game_manager.shutil.disk_usage",
                            lambda _p: usage(0, 0, 900_000 * 1024 * 1024))

    @staticmethod
    def _deborde(win, qtbot):
        """Jeux dont le panneau d'infos défile, à la taille courante."""
        trop = []
        for entry in win.manager.get_games():
            win._detail.set_game(entry.game)
            reste = _reste_a_defiler(qtbot, win)
            if reste > 0:
                trop.append((entry.game.id, reste))
        return trop

    @pytest.mark.parametrize("taille", [(980, 660), (1100, 720), (1320, 880), (1500, 950)])
    def test_aucun_avertissement(self, make_window, qtbot, monkeypatch, taille):
        """Cas nominal : réseau OK, disque large, aucun bandeau."""
        self._disque_large(monkeypatch)
        win = make_window()
        win.show()
        win.resize(*taille)
        qtbot.wait(40)
        assert self._deborde(win, qtbot) == []

    @pytest.mark.parametrize("taille", [(980, 660), (1320, 880), (1500, 950)])
    def test_pendant_le_telechargement(self, make_window, qtbot, monkeypatch, taille):
        """Le chemin RÉEL : l'orchestrateur change l'état et émet state_changed.

        Passer en téléchargement ajoute une barre de progression, un stepper et
        une ligne de vitesse à la zone d'action — ~50 px. Sans repositionnement
        du panneau, la fiche se met à défiler jusqu'à la fin de l'installation,
        puis se répare toute seule : introuvable sur demande.
        """
        self._disque_large(monkeypatch)
        win = make_window()
        win.show()
        win.resize(*taille)
        qtbot.wait(40)
        from src.core.game_manager import GameState
        trop = []
        for entry in win.manager.get_games():
            win._detail.set_game(entry.game)
            qtbot.wait(20)
            win.manager.set_game_state(entry.game.id, GameState.DOWNLOADING)
            win._detail.ops.state_changed.emit()
            reste = _reste_a_defiler(qtbot, win)
            if reste > 0:
                trop.append((entry.game.id, reste))
            win.manager.set_game_state(entry.game.id, GameState.NOT_INSTALLED)
            win._detail.ops.state_changed.emit()
            qtbot.wait(10)
        assert trop == []


class TestZoomSurLeTickerPartage:
    """Le zoom du fond était la seule animation décorative hors du Ticker.

    Porté par une QPropertyAnimation, il tournait à la cadence de l'horloge
    d'animation de Qt (~60 Hz) et repeignait la fenêtre entière à chaque frame :
    premier poste de peinture au repos, 88 ms/s à 1200×800. Sur le Ticker
    partagé (30 Hz), le total tombe de 212 à 117 ms/s.
    """

    def test_le_zoom_sabonne_et_se_desabonne(self, make_window, qtbot):
        win = make_window()
        win.show()
        qtbot.wait(60)
        bg = win._detail._bg
        assert bg._zoom_ticking, "le zoom devrait être abonné au Ticker"
        bg.pause()
        assert not bg._zoom_ticking, "pause() doit désabonner le zoom"
        bg.resume()
        assert bg._zoom_ticking, "resume() doit ré-abonner le zoom"

    def test_aucun_timer_hors_ticker(self, make_window, qtbot):
        """Aucune animation décorative ne doit avoir son horloge à elle."""
        from PyQt6.QtCore import QAbstractAnimation
        win = make_window()
        win.show()
        qtbot.wait(80)
        bg = win._detail._bg
        assert not hasattr(bg, "_zoom_anim"), (
            "le zoom ne doit plus passer par une QPropertyAnimation")
        # Un seul aller : au bout, le zoom est posé à 1.05 et se désabonne.
        for _ in range(400):
            bg._advance_zoom()
        assert bg._zoom == 1.05 and bg._zoom_phase == 1.0
        assert not bg._zoom_ticking, "le zoom doit s'arrêter après un aller"
        bg.resume()
        assert not bg._zoom_ticking, "revenir au premier plan ne relance pas le zoom"
        bg.start_zoom_loop()
        assert bg._zoom_ticking and bg._zoom == 1.0, "un nouveau jeu le relance"
        assert QAbstractAnimation is not None  # import utilisé, garde-fou lisible


class TestBalisageDuCatalogueJamaisInterprete:
    """Aucun texte du catalogue ne doit etre INTERPRETE comme du balisage.

    Le catalogue se met a jour A DISTANCE. `QLabel` et `QMessageBox` sont en
    `AutoText` par defaut : Qt renifle le contenu et bascule en rich text des
    qu'il ressemble a du HTML. Un `<img src="http://...">` dans un nom de jeu
    declenchait donc une requete reseau a l'affichage de la fiche — « qui
    regarde quel jeu » partait chez l'hebergeur de l'image.

    Ce test BALAYE tous les labels d'une vraie fenetre : il attrapera aussi le
    prochain qu'on ajoutera sans y penser.
    """

    _MARQUEUR = "<b>INJECTE</b>"

    @pytest.fixture
    def fenetre_injectee(self, make_window, monkeypatch):
        import dataclasses

        from src.core import game_manager
        vrai_load = game_manager.load_catalog
        marque = self._MARQUEUR

        def _charge(*a, **k):
            cat = vrai_load(*a, **k)
            jeux = list(cat.games)
            jeux[0] = dataclasses.replace(
                jeux[0],
                name="Jeu " + marque,
                description="Description " + marque + " et la suite du texte.",
                developer="Studio " + marque,
                warning="Avertissement " + marque,
                controller="yes",
                controller_note="Note " + marque,
            )
            return dataclasses.replace(cat, games=tuple(jeux))

        monkeypatch.setattr(game_manager, "load_catalog", _charge)
        win = make_window()
        win.show()
        return win, win.manager.get_games()[0].game

    @staticmethod
    def _labels_dangereux(win):
        """Labels dont le texte serait rendu comme du HTML."""
        from PyQt6.QtWidgets import QLabel

        marque = TestBalisageDuCatalogueJamaisInterprete._MARQUEUR
        dangereux = []
        for lab in win.findChildren(QLabel):
            texte = lab.text()
            if marque not in texte:
                continue
            fmt = lab.textFormat()
            if fmt == Qt.TextFormat.RichText or (
                    fmt == Qt.TextFormat.AutoText and Qt.mightBeRichText(texte)):
                dangereux.append((lab.objectName() or type(lab).__name__, fmt.name))
        return dangereux

    def test_aucun_label_n_interprete_le_catalogue(self, fenetre_injectee, qtbot):
        win, jeu = fenetre_injectee
        win.resize(1200, 800)
        win._detail.set_game(jeu)
        qtbot.wait(60)
        assert self._labels_dangereux(win) == []

    def test_aucune_infobulle_n_interprete_le_catalogue(self, fenetre_injectee, qtbot):
        """Une infobulle est un `QLabel` en AutoText : elle échappe au balayage
        des labels. La note « manette » du catalogue y passait brute (audit du
        2026-10-29, règle 57)."""
        from PyQt6.QtWidgets import QWidget

        win, jeu = fenetre_injectee
        win._detail.set_game(jeu)
        qtbot.wait(40)
        porteurs = [w for w in win.findChildren(QWidget) if "INJECTE" in w.toolTip()]
        assert porteurs, "la note du catalogue n'atteint aucune infobulle"
        assert [w.objectName() or type(w).__name__ for w in porteurs
                if self._MARQUEUR in w.toolTip()] == []

    def test_le_marqueur_atteint_bien_l_ecran(self, fenetre_injectee, qtbot):
        """Garde-fou : sans lui, le test ci-dessus passerait a vide si le texte
        du catalogue cessait d'etre affiche."""
        from PyQt6.QtWidgets import QLabel

        win, jeu = fenetre_injectee
        win.resize(1200, 800)
        win._detail.set_game(jeu)
        qtbot.wait(60)
        porteurs = [lab for lab in win.findChildren(QLabel)
                    if self._MARQUEUR in lab.text()]
        assert porteurs, "aucun label ne porte le texte du catalogue"

    def test_le_titre_et_la_description_sont_en_texte_brut(self, fenetre_injectee, qtbot):
        """Les deux qui restent affiches en permanence : c'est la que la
        requete reseau d'une balise partirait a chaque ouverture de fiche."""
        win, jeu = fenetre_injectee
        win._detail.set_game(jeu)
        qtbot.wait(40)
        info = win._detail._info
        assert info._title.textFormat() == Qt.TextFormat.PlainText
        assert info._desc.textFormat() == Qt.TextFormat.PlainText
        assert self._MARQUEUR in info._title.text()

    def test_les_dialogues_passent_par_le_helper_en_texte_brut(self):
        """Un `QMessageBox.question(...)` direct reviendrait a l'AutoText."""
        import ast

        from src.ui import game_detail_handlers as handlers

        source = pathlib.Path(handlers.__file__).read_text(encoding="utf-8")
        arbre = ast.parse(source)
        fautifs = []
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Call):
                continue
            fonc = noeud.func
            if (isinstance(fonc, ast.Attribute)
                    and isinstance(fonc.value, ast.Name)
                    and fonc.value.id == "QMessageBox"
                    and fonc.attr in {"question", "warning", "information", "critical"}):
                fautifs.append(fonc.attr)
        assert not fautifs, f"appels statiques a QMessageBox (AutoText) : {fautifs}"
