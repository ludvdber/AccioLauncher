"""Tests pour src/ui/carousel.py — focus sur set_games() (CRITICAL #4)."""

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtGui import QImage, QPainter  # noqa: E402

from src.core.game_data import GameData  # noqa: E402
from src.ui.carousel import Carousel  # noqa: E402
from src.ui.carousel_item import CarouselItem  # noqa: E402


_GAME_DICT = {
    "id": "x", "name": "X", "year": 2001, "description": "d",
    "developer": "Dev", "executable": "X/x.exe", "cover_image": "x.jpg",
}


class _FakeManager:
    def is_installed(self, _: str) -> bool: return False
    def has_update(self, _: str) -> bool: return False
    def installed_version(self, _: str) -> str | None: return None
    def is_new(self, _: str) -> bool: return False
    def mark_seen(self, _: str) -> None: pass
    # Reprise d'un téléchargement interrompu : None = rien en attente.
    def reprise(self, _game): return None


def _make_game(game_id: str) -> GameData:
    return GameData.from_dict({**_GAME_DICT, "id": game_id, "name": game_id.upper()})


class TestCarouselSetGames:
    def test_initial_population(self, qtbot):
        c = Carousel([_make_game("a"), _make_game("b")], _FakeManager())
        qtbot.addWidget(c)
        assert len(c._items) == 2
        assert c.current_index == 0

    def test_grow(self, qtbot):
        c = Carousel([_make_game("a")], _FakeManager())
        qtbot.addWidget(c)
        c.set_games([_make_game("a"), _make_game("b"), _make_game("c")])
        assert len(c._items) == 3

    def test_shrink(self, qtbot):
        c = Carousel([_make_game("a"), _make_game("b"), _make_game("c")],
                     _FakeManager())
        qtbot.addWidget(c)
        c.set_games([_make_game("a")])
        assert len(c._items) == 1
        assert c.current_index == 0

    def test_replace_completely(self, qtbot):
        c = Carousel([_make_game("hp1")], _FakeManager())
        qtbot.addWidget(c)
        c.set_games([_make_game("hp7a"), _make_game("hp7b")])
        assert [item.game.id for item in c._items] == ["hp7a", "hp7b"]

    def test_empty_list(self, qtbot):
        c = Carousel([_make_game("a")], _FakeManager())
        qtbot.addWidget(c)
        c.set_games([])
        assert c._items == []

    def test_select_emits_signal(self, qtbot):
        c = Carousel([_make_game("a"), _make_game("b"), _make_game("c")],
                     _FakeManager())
        qtbot.addWidget(c)
        with qtbot.waitSignal(c.game_selected, timeout=500) as sig:
            c.select(2)
        assert sig.args == [2]

    def test_select_no_signal_on_same_index(self, qtbot):
        c = Carousel([_make_game("a"), _make_game("b")], _FakeManager())
        qtbot.addWidget(c)
        with qtbot.assertNotEmitted(c.game_selected):
            c.select(0)  # déjà current

    def test_select_navigation(self, qtbot):
        c = Carousel([_make_game("a"), _make_game("b"), _make_game("c")],
                     _FakeManager())
        qtbot.addWidget(c)
        c.select_next()
        assert c.current_index == 1
        c.select_next()
        assert c.current_index == 2
        c.select_next()  # wrap
        assert c.current_index == 0
        c.select_prev()  # wrap arrière
        assert c.current_index == 2


class TestSelectionPreserveeAuReload:
    """Reconstruire la bande ne doit pas ramener la surbrillance sur l'item 0.

    Cas réel (capture de Ludo, 2026-08-21) : la fiche s'ouvre sur le dernier
    jeu joué (HP6), puis le catalogue distant arrive, `set_games` reconstruit
    la bande et remet l'index à 0. Résultat : HP1 surligné, HP6 affiché
    au-dessus. Le second effet est pire que le premier — `select` sort tôt
    quand l'index ne change pas, donc cliquer sur HP1 ne faisait RIEN et
    l'utilisateur ne pouvait plus revenir au jeu qu'il voyait surligné.
    """

    def test_garde_le_jeu_courant(self, qtbot):
        jeux = [_make_game("hp1"), _make_game("hp2"), _make_game("hp6")]
        c = Carousel(jeux, _FakeManager())
        qtbot.addWidget(c)
        c.select(2)
        c.set_games(jeux)
        assert c.current_index == 2
        assert c.current_game_id() == "hp6"
        assert [item.selected for item in c._items] == [False, False, True]

    def test_id_explicite_prioritaire(self, qtbot):
        """L'appelant décide : c'est lui qui pose la fiche, la bande le suit."""
        jeux = [_make_game("hp1"), _make_game("hp2"), _make_game("hp6")]
        c = Carousel(jeux, _FakeManager())
        qtbot.addWidget(c)
        c.set_games(jeux, selected_id="hp2")
        assert c.current_index == 1
        assert c.current_game_id() == "hp2"

    def test_repli_sur_zero_si_le_jeu_disparait(self, qtbot):
        jeux = [_make_game("hp1"), _make_game("hp2"), _make_game("hp6")]
        c = Carousel(jeux, _FakeManager())
        qtbot.addWidget(c)
        c.select(2)
        c.set_games([_make_game("hp1"), _make_game("hp2")])
        assert c.current_index == 0
        assert c._items[0].selected is True

    def test_reload_reste_muet(self, qtbot):
        """Contrat inchangé : `set_games` n'emet pas, l'appelant pose la fiche."""
        jeux = [_make_game("hp1"), _make_game("hp2"), _make_game("hp6")]
        c = Carousel(jeux, _FakeManager())
        qtbot.addWidget(c)
        c.select(2)
        with qtbot.assertNotEmitted(c.game_selected):
            c.set_games(jeux)

    def test_clic_sur_le_jeu_affiche_apres_reload(self, qtbot):
        """Un clic sur l'item VOISIN doit encore basculer la fiche.

        Garde-fou contre la correction inverse (figer l'index sans bouger la
        surbrillance) : la bande doit rester navigable apres reconstruction.
        """
        jeux = [_make_game("hp1"), _make_game("hp2"), _make_game("hp6")]
        c = Carousel(jeux, _FakeManager())
        qtbot.addWidget(c)
        c.select(2)
        c.set_games(jeux)
        with qtbot.waitSignal(c.game_selected, timeout=500) as sig:
            c.select(0)
        assert sig.args == [0]
        assert c.current_game_id() == "hp1"


class TestVignettesTiennentDansLaBande:
    """Les jaquettes ne doivent jamais être rognées par le bord de la bande.

    La taille de l'item et la hauteur du carrousel étaient deux constantes
    indépendantes, qui ne concordaient que pour l'item le plus ÉLOIGNÉ de la
    sélection (150 px pour 160). La vignette sélectionnée, elle, réclamait
    180 px et se faisait couper de 27 px — en permanence, sur celle que l'œil
    regarde en premier. En bande compacte (fenêtre < 780 px), les huit étaient
    coupées, de 33 à 63 px.
    """

    @staticmethod
    def _debordements(c):
        """Items dont la géométrie sort de la bande.

        `activate()` force la passe de layout : redimensionner un enfant ne
        replace pas les autres tout de suite, et sans ça on mesure des
        positions d'avant le changement de bande — un test qui échoue pour une
        raison qui n'est pas celle qu'il surveille.
        """
        c._items_layout.activate()
        return [(i, item.geometry().height(), item.geometry().bottom() - c.height())
                for i, item in enumerate(c._items)
                if item.geometry().bottom() > c.height() or item.geometry().top() < 0]

    def _carousel(self, qtbot, compact):
        jeux = [_make_game("hp%d" % n) for n in range(1, 9)]
        c = Carousel(jeux, _FakeManager())
        qtbot.addWidget(c)
        c.set_compact(compact)
        c.resize(1200, c.height())
        c.show()
        c.select(6)
        # L'échelle est animée : attendre qu'elle se pose, sinon on mesure
        # l'état de départ et le test passe pour de mauvaises raisons.
        qtbot.waitUntil(lambda: c._items[6]._anim_scale > 1.05, timeout=3000)
        return c

    def test_bande_normale(self, qtbot):
        c = self._carousel(qtbot, compact=False)
        assert self._debordements(c) == []

    def test_bande_compacte(self, qtbot):
        """Le cas signalé : redimensionner sous 780 px cassait la bande."""
        c = self._carousel(qtbot, compact=True)
        assert self._debordements(c) == []

    def test_le_passage_en_compact_redimensionne_les_vignettes(self, qtbot):
        """`set_compact` ne changeait QUE la hauteur de la bande."""
        c = self._carousel(qtbot, compact=False)
        avant = c._items[0]._thumb_h
        c.set_compact(True)
        assert c._items[0]._thumb_h < avant
        assert self._debordements(c) == []

    def test_retour_en_normal(self, qtbot):
        """Aller-retour : les vignettes doivent reprendre leur taille."""
        c = self._carousel(qtbot, compact=False)
        depart = c._items[0]._thumb_h
        c.set_compact(True)
        c.set_compact(False)
        assert c._items[0]._thumb_h == depart
        assert self._debordements(c) == []


class TestVignettePour:
    """La formule, sans Qt : un item à l'échelle maximale doit tenir."""

    def test_le_plus_grand_item_tient(self):
        from src.ui.carousel import SCALE_SELECTED
        from src.ui.carousel_item import REFLECTION_RATIO, _MARGE_V, vignette_pour

        for dispo in (148, 112, 90, 200, 60):
            _, h = vignette_pour(dispo, SCALE_SELECTED)
            haut = int(h * SCALE_SELECTED)
            total = haut + int(haut * REFLECTION_RATIO) + _MARGE_V
            assert total <= dispo, "dispo=%d -> item de %d px" % (dispo, total)

    def test_le_rapport_de_la_jaquette_est_tenu(self):
        from src.ui.carousel import SCALE_SELECTED
        from src.ui.carousel_item import THUMB_H, THUMB_W, vignette_pour

        w, h = vignette_pour(148, SCALE_SELECTED)
        assert abs(w / h - THUMB_W / THUMB_H) < 0.02

    def test_une_bande_absurde_ne_leve_pas(self):
        """Une hauteur nulle ou négative ne doit pas produire une taille nulle
        (division par zéro plus loin) ni faire lever."""
        from src.ui.carousel import SCALE_SELECTED
        from src.ui.carousel_item import vignette_pour

        for dispo in (0, -50, 1):
            w, h = vignette_pour(dispo, SCALE_SELECTED)
            assert w >= 1 and h >= 1


class TestFiletDeReprise:
    """Un téléchargement interrompu doit se voir SANS naviguer.

    Mesuré le 2026-08-29 : 12 Mo de HP3 en cache, le launcher rouvre sur HP7
    partie 2 (dernier jeu JOUÉ, jamais celui qu'on téléchargeait) et **aucun
    des 16 textes visibles** ne mentionne l'attente. Il fallait deviner, puis
    trouver la bonne fiche parmi huit, pour lire « REPRENDRE — 763 Mo
    restants ». Le téléchargeur reprend pourtant depuis toujours.

    Sur 4,6 Go, c'est quelqu'un qui a déjà attendu vingt minutes et qui croit
    avoir tout perdu — la marche la plus chère de l'entonnoir.
    """

    def _vignette(self, qtbot, fraction):
        class _M(_FakeManager):
            def reprise(self, _game):
                return (fraction, 100.0) if fraction else None

        it = CarouselItem(_make_game("hp3"), _M())
        qtbot.addWidget(it)
        it.refresh_state()
        it.resize(160, 220)
        img = QImage(it.size(), QImage.Format.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        it.render(p)
        p.end()
        return it, img

    def test_le_filet_apparait_quand_il_y_a_de_quoi_reprendre(self, qtbot):
        _, avec = self._vignette(qtbot, 0.6)
        _, sans = self._vignette(qtbot, 0.0)
        differents = sum(
            1 for y in range(avec.height()) for x in range(avec.width())
            if avec.pixelColor(x, y) != sans.pixelColor(x, y))
        assert differents > 30, (
            f"seulement {differents} pixel(s) changent : aucun filet peint")

    def test_rien_ne_se_voit_quand_il_n_y_a_rien_en_attente(self, qtbot):
        """« Un état ne s'affiche que lorsqu'il DÉVIE » : sans reprise en
        cours, la vignette doit être RIGOUREUSEMENT celle d'avant."""
        it = CarouselItem(_make_game("hp3"), _FakeManager())
        qtbot.addWidget(it)
        it.refresh_state()
        assert it._cached_reprise == 0.0

    def test_le_filet_grandit_avec_la_part_telechargee(self, qtbot):
        """Sinon il ne serait qu'un voyant : c'est l'avancement qui décide de
        relancer maintenant ou plus tard.

        On compte l'encre DORÉE, pas les pixels qui changent : la piste sombre
        occupe toute la largeur dès qu'il y a une reprise, donc un écart mesuré
        sur la différence avec la vignette nue vaut la même chose à 25 % et à
        75 % — le test passait alors sans rien prouver.
        """
        def or_du_filet(img):
            # Toute l'image : le filet est au bas de la JAQUETTE, au-dessus du
            # reflet — pas au bas du widget.
            n = 0
            for y in range(img.height()):
                for x in range(img.width()):
                    c = img.pixelColor(x, y)
                    if c.alpha() > 100 and c.red() > 120 and c.red() > c.blue() + 40:
                        n += 1
            return n

        petit = or_du_filet(self._vignette(qtbot, 0.25)[1])
        grand = or_du_filet(self._vignette(qtbot, 0.75)[1])
        assert petit > 0, "aucune encre dorée : le filet n'est pas rempli"
        assert grand > petit * 1.5, (
            f"le remplissage ne suit pas la progression : {petit} px à 25 %, "
            f"{grand} px à 75 %")

    def test_le_seuil_et_le_calcul_ne_vivent_qu_a_UN_endroit(self):
        """Le bouton de la fiche et la vignette affichent la même chose : deux
        seuils recopiés divergent tôt ou tard (le défaut du carrousel, déjà
        payé avec THUMB_H et CAROUSEL_HEIGHT)."""
        import pathlib
        panel = pathlib.Path("src/ui/action_panel.py").read_text(encoding="utf-8")
        item = pathlib.Path("src/ui/carousel_item.py").read_text(encoding="utf-8")
        assert "0.99" not in panel, "seuil de reprise recopié dans action_panel"
        assert "0.99" not in item, "seuil de reprise recopié dans carousel_item"
        assert "manager.reprise(" in item or ".reprise(" in item
