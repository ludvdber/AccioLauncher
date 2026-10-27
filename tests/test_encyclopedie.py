"""Personnages et Bestiaire des Collections : les fiches embarquées, les images lues dans le jeu, la page."""

import pytest

from src.core import encyclopedie, textures_ue1


JEUX = ("hp1", "hp2", "hp3", "hp4", "hp5", "hp6")


class TestFiches:
    def test_deux_rubriques_six_jeux(self):
        for rubrique in (encyclopedie.PERSONNAGES, encyclopedie.BESTIAIRE):
            assert encyclopedie.jeux(rubrique) == JEUX

    def test_chaque_texte_dans_chaque_langue(self):
        langues = {"fr", "en", "es"}
        for rubrique in (encyclopedie.PERSONNAGES, encyclopedie.BESTIAIRE):
            for jeu in JEUX:
                for f in encyclopedie.fiches(rubrique, jeu):
                    for texte in (f.nom, f.sous_titre, f.texte):
                        assert not isinstance(texte, str), f.cle
                        assert {k for k, v in texte if v.strip()} >= langues, (jeu, f.cle)

    def test_cles_uniques_par_jeu(self):
        for rubrique in (encyclopedie.PERSONNAGES, encyclopedie.BESTIAIRE):
            for jeu in JEUX:
                cles = [f.cle for f in encyclopedie.fiches(rubrique, jeu)]
                assert len(cles) == len(set(cles)), (rubrique, jeu)

    def test_une_creature_ne_vit_qu_au_bestiaire(self):
        """Touffu en double dans les deux rubriques « n'a pas de sens » (Ludo, 2026-10-27)."""
        for jeu in JEUX:
            personnages = {f.modele or f.cle for f in encyclopedie.fiches(encyclopedie.PERSONNAGES, jeu)}
            betes = {f.modele or f.cle for f in encyclopedie.fiches(encyclopedie.BESTIAIRE, jeu)}
            assert not personnages & betes, jeu
        assert "touffu" not in {f.cle for f in encyclopedie.fiches(encyclopedie.PERSONNAGES, "hp1")}

    def test_pas_d_image_pour_hp5_et_hp6(self):
        """Option 1 : leurs seules images sont des visages photographiés dépliés."""
        for rubrique in (encyclopedie.PERSONNAGES, encyclopedie.BESTIAIRE):
            for jeu in ("hp5", "hp6"):
                assert all(f.image is None for f in encyclopedie.fiches(rubrique, jeu))

    def test_un_fichier_absent_ne_casse_rien(self, tmp_path):
        assert encyclopedie.charger.__wrapped__(tmp_path / "absent.json") == {}


class TestImages:
    def test_sans_le_jeu(self, tmp_path):
        harry = encyclopedie.fiches(encyclopedie.PERSONNAGES, "hp1")[0]
        assert harry.image is not None
        assert encyclopedie.image(tmp_path / "System", harry) is None

    def test_le_fichier_se_trouve_sans_tenir_compte_de_la_casse(self, tmp_path):
        (tmp_path / "HP3" / "Textures").mkdir(parents=True)
        (tmp_path / "HP3" / "Textures" / "hp3_menu.utx").write_bytes(b"")
        image = encyclopedie.ImageJeu("textures/HP3_Menu.utx", "Pixie", 32)
        assert encyclopedie.chemin_image(tmp_path / "HP3" / "system", image) == \
            tmp_path / "HP3" / "Textures" / "hp3_menu.utx"

    def test_palette_en_bvra_et_indice_zero_masque(self):
        tex = textures_ue1.TexturePaletee(2, 1, bytes([0, 1]), ((10, 20, 30, 255), (40, 50, 60, 255)), True)
        assert encyclopedie.bgra_de_palette(tex) == (2, 1, bytes([30, 20, 10, 0, 60, 50, 40, 255]))

    def test_recadrer(self):
        pixels = bytes(range(4 * 4 * 3))          # 4 × 3, un octet différent par canal
        w, h, px = encyclopedie.recadrer((4, 3, pixels), (1, 1, 2, 2))
        assert (w, h) == (2, 2)
        assert px == pixels[20:28] + pixels[36:44]

    def test_recadrage_hors_image(self):
        assert encyclopedie.recadrer((4, 3, bytes(48)), (5, 0, 2, 2)) is None


pytest.importorskip("pytestqt")


class _Media:
    def __init__(self, dossier=None):
        self._dossier = dossier

    def dossier_exe(self, jeu):
        return self._dossier


class TestVue:
    def test_une_fiche_par_personnage_et_un_emblème_sans_le_jeu(self, qtbot):
        from src.ui.encyclopedie_page import VueEncyclopedie
        vue = VueEncyclopedie(_Media(), encyclopedie.PERSONNAGES)
        qtbot.addWidget(vue)
        vue.montrer("hp5")
        assert len(vue.fiches) == len(encyclopedie.fiches(encyclopedie.PERSONNAGES, "hp5"))
        assert vue._attendues == [] and not any(f.a_une_image for f in vue.fiches)
        vue.fermer()

    def test_un_jeu_sans_fiche_le_dit(self, qtbot):
        from PyQt6.QtWidgets import QLabel

        from src.ui.encyclopedie_page import VueEncyclopedie
        vue = VueEncyclopedie(_Media(), encyclopedie.BESTIAIRE)
        qtbot.addWidget(vue)
        vue.montrer("hp7a")
        assert vue.fiches == []
        assert "Aucune fiche pour ce jeu." in {lab.text() for lab in vue.findChildren(QLabel)}
        vue.fermer()

    def test_changer_de_jeu_ne_laisse_aucune_ancienne_fiche(self, qtbot):
        """Les fiches de HP6 restaient à l'écran sous « Aucune fiche » de HP7
        (Ludo, 2026-10-27) : le flux retiré gardait ses widgets."""
        from PyQt6.QtWidgets import QFrame

        from src.ui.encyclopedie_page import VueEncyclopedie
        vue = VueEncyclopedie(_Media(), encyclopedie.BESTIAIRE)
        qtbot.addWidget(vue)
        vue.show()

        def montrees():
            # Par le nom d'objet : une fiche dont l'enveloppe Python est
            # perdue revient en QFrame, `findChildren(_Fiche)` ne la voit plus.
            return [f for f in vue.findChildren(QFrame, "carteJeu") if f.isVisible()]
        vue.montrer("hp6")
        vue.montrer("hp7b")
        assert montrees() == []
        vue.montrer("hp1")
        qtbot.waitUntil(lambda: len(montrees()) == len(vue.fiches), timeout=2000)
        vue.fermer()

    def test_le_texte_replie_tient_dans_la_fiche(self, qtbot):
        """La hauteur souhaitée suit le texte replié : une longue description
        n'est plus coupée par le `FlowLayout` (rendu du 2026-10-26)."""
        from src.ui.encyclopedie_page import _Fiche
        courte = encyclopedie.Fiche("a", "A", "b", "c", None)
        longue = encyclopedie.Fiche("a", "A", "b", "mot " * 120, None)
        f1, f2 = _Fiche(encyclopedie.BESTIAIRE, courte), _Fiche(encyclopedie.BESTIAIRE, longue)
        qtbot.addWidget(f1)
        qtbot.addWidget(f2)
        assert f2.sizeHint().height() > f1.sizeHint().height() + 60


class TestModeles:
    def test_hp1_et_hp2_ont_un_modele_par_fiche(self):
        for rubrique in (encyclopedie.PERSONNAGES, encyclopedie.BESTIAIRE):
            for jeu in ("hp1", "hp2"):
                for f in encyclopedie.fiches(rubrique, jeu):
                    assert f.modele is not None, (rubrique, jeu, f.cle)
                    assert f.modele.fichier.startswith("System/")
            for jeu in ("hp3", "hp4", "hp5", "hp6"):
                assert all(f.modele is None for f in encyclopedie.fiches(rubrique, jeu))

    def test_la_fiche_choisie_montre_son_modele(self, qtbot, tmp_path, monkeypatch):
        from src.core import maillages_ue1
        from src.ui.encyclopedie_page import VueEncyclopedie
        triangle = maillages_ue1.Maillage(((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
                                          (maillages_ue1.Face((0, 1, 2), ((0, 0), (1, 0), (0, 1)), 0),),
                                          (maillages_ue1.Materiau("", 0),))
        monkeypatch.setattr(maillages_ue1, "de_la_fiche", lambda dossier, fiche: (triangle, {}))
        monkeypatch.setattr(encyclopedie, "image", lambda dossier, fiche: None)
        vue = VueEncyclopedie(_Media(tmp_path), encyclopedie.PERSONNAGES)
        qtbot.addWidget(vue)
        vue.montrer("hp1")
        qtbot.waitUntil(lambda: not vue._chargeur.isActive(), timeout=5000)
        assert vue.scene is not None and vue.scene.modele.modele is triangle
        assert vue.fiches[0].property("choisie") is True
        # Une fiche sans image a reçu la vignette de son modèle.
        assert all(f.a_une_vignette for f in vue.fiches)
        vue.choisir(vue.fiches[3])
        assert vue.fiches[3].property("choisie") and not vue.fiches[0].property("choisie")
        vue.fermer()
