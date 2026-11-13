"""Tests pour src/ui/theme.py — palette pure, sans Qt."""

import pytest

from src.ui.theme import THEMES, current, set_theme, themed


@pytest.fixture(autouse=True)
def _reset_theme():
    """Chaque test repart de Poudlard et y revient (état module global)."""
    set_theme("poudlard")
    yield
    set_theme("poudlard")


class TestSetTheme:
    def test_default_is_poudlard(self):
        assert current().id == "poudlard"
        assert current().accent == "#d6a72c"

    def test_known_theme(self):
        set_theme("gryffondor")
        assert current().id == "gryffondor"

    def test_unknown_falls_back_to_poudlard(self):
        set_theme("dortoir-des-blaireaux")
        assert current().id == "poudlard"

    def test_five_houses(self):
        assert set(THEMES) == {"poudlard", "gryffondor", "serpentard", "serdaigle", "poufsouffle"}


class TestAccentRgb:
    def test_poudlard_gold(self):
        assert THEMES["poudlard"].accent_rgb == (214, 167, 44)


class TestThemed:
    QSS = ("color: #d6a72c; border: 1px solid #f0d060;"
           " background: rgba(214, 167, 44, 0.3); top: #9a7209;"
           " hover: #e8c547; packed: rgba(214,167,44,0.5);")

    def test_poudlard_passthrough(self):
        assert themed(self.QSS) == self.QSS

    def test_gryffondor_substitutes_everything(self):
        set_theme("gryffondor")
        out = themed(self.QSS)
        p = THEMES["gryffondor"]
        r, g, b = p.accent_rgb
        assert "#d6a72c" not in out and "214, 167, 44" not in out and "214,167,44" not in out
        assert "#f0d060" not in out and "#e8c547" not in out and "#9a7209" not in out
        assert p.accent in out and p.accent_light in out and p.accent_dark in out
        assert f"{r}, {g}, {b}" in out

    def test_non_palette_colors_untouched(self):
        set_theme("serpentard")
        qss = "color: #ffffff; play: #2ecc71; red: #c0392b;"
        assert themed(qss) == qss


class TestThemedSurfaces:
    """v2 : les surfaces bleu nuit sont teintées maison, pas seulement l'accent."""

    QSS = ("background: #060611; dialog: #0d0d1a; card: #0f1528;"
           " control: #16213e; b1: #1a2744; b2: #2c3e6b; veil: rgba(6, 6, 17, 0.92);")

    def test_poudlard_passthrough(self):
        assert themed(self.QSS) == self.QSS

    def test_gryffondor_tints_every_surface(self):
        set_theme("gryffondor")
        out = themed(self.QSS)
        p = THEMES["gryffondor"]
        for navy in ("#060611", "#0d0d1a", "#0f1528", "#16213e",
                     "#1a2744", "#2c3e6b", "6, 6, 17"):
            assert navy not in out
        assert p.bg in out and p.bg_dialog in out and p.bg_card in out
        assert p.bg_control in out and p.border in out and p.border_strong in out
        br, bgc, bb = p.bg_rgb
        assert f"rgba({br}, {bgc}, {bb}, 0.92)" in out

    def test_every_house_has_tinted_surfaces(self):
        base = THEMES["poudlard"]
        for pid, p in THEMES.items():
            if pid == "poudlard":
                continue
            assert p.bg != base.bg, pid
            assert p.bg_control != base.bg_control, pid
            assert p.border_strong != base.border_strong, pid


class TestThemedHorsPalette:
    """Audit du 2026-11-13 : les fonds écrits hors palette (#070712 des Réglages du jeu, du Carnet
    et des Collections, #15152a des listes…) restaient bleu nuit sous un thème de maison."""

    def test_les_fonds_hors_palette_prennent_la_maison(self):
        from src.ui.theme import _VOISINES
        set_theme("gryffondor")
        for h in _VOISINES:
            assert themed(f"background: {h};") != f"background: {h};", h

    def test_meme_ecart_que_la_surface_voisine(self):
        set_theme("gryffondor")
        # #070712 = fond de Poudlard + 1 sur chaque canal ; Gryffondor #1a0709 + 1.
        assert themed("background: #070712;") == "background: #1b080a;"

    def test_l_or_des_survols_suit_la_maison(self):
        set_theme("serpentard")
        out = themed("a: #e8bd4a; b: #f4e2a8;")
        assert out == f"a: {THEMES['serpentard'].accent_light}; b: {THEMES['serpentard'].accent_light};"

    def test_un_seul_passage(self):
        """Une couleur substituée n'est jamais substituée une seconde fois."""
        set_theme("poufsouffle")
        p = THEMES["poufsouffle"]
        assert themed("color: #d6a72c;") == f"color: {p.accent};"

    def test_un_triplet_plus_long_n_est_pas_touche(self):
        set_theme("gryffondor")
        qss = "a: rgba(213, 13, 26, 0.5); b: rgb(6, 6, 170); c: rgba(16, 6, 17, 1);"
        assert themed(qss) == qss

    def test_rgba_du_fond_des_dialogues(self):
        set_theme("serdaigle")
        r, g, b = (int(THEMES["serdaigle"].bg_dialog[i:i + 2], 16) for i in (1, 3, 5))
        assert themed("background: rgba(13, 13, 26, 0.9);") == f"background: rgba({r}, {g}, {b}, 0.9);"

    def test_majuscules(self):
        set_theme("gryffondor")
        assert themed("color: #D6A72C;") == f"color: {THEMES['gryffondor'].accent};"
