"""Les vignettes des Personnages et du Bestiaire gardées sur le disque (`ui/vignettes_fiches`).

Ludo, 2026-11-16 : toute vue s'ouvre en 0,5 s. Les modèles de toute la liste se relisaient et
se redessinaient à chaque ouverture (2 à 3 s pour HP3, HP5, HP6)."""

import pytest

from src.core import encyclopedie, maillages_ue1

pytest.importorskip("pytestqt")

from PyQt6.QtGui import QColor, QImage  # noqa: E402

from src.ui import vignettes_fiches  # noqa: E402
from src.ui.vignettes_fiches import Vignettes  # noqa: E402

TRIANGLE = maillages_ue1.Maillage(((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
                                  (maillages_ue1.Face((0, 1, 2), ((0, 0), (1, 0), (0, 1)), 0),),
                                  (maillages_ue1.Materiau("", 0),))


def _unie(couleur: str, largeur: int = 8, hauteur: int = 6) -> QImage:
    image = QImage(largeur, hauteur, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(couleur))
    return image


class TestPlanche:
    def test_aller_retour_chaque_vignette_a_sa_taille(self, qapp, tmp_path):
        planche = tmp_path / "fiches" / "hp5_personnages.png"
        vignettes_fiches.ecrire(planche, "e1", {"harry": _unie("#ff0000"), "ron": _unie("#00ff00", 12, 10)})
        lues = vignettes_fiches.lire(planche, "e1")
        assert set(lues) == {"harry", "ron"}
        assert (lues["harry"].width(), lues["harry"].height()) == (8, 6)
        assert (lues["ron"].width(), lues["ron"].height()) == (12, 10)
        assert lues["harry"].pixelColor(4, 3) == QColor("#ff0000")
        assert lues["ron"].pixelColor(11, 9) == QColor("#00ff00")
        assert [p.name for p in planche.parent.iterdir()] == ["hp5_personnages.png"], "aucun temporaire laissé"

    def test_une_autre_empreinte_jette_la_planche(self, qapp, tmp_path):
        planche = tmp_path / "p.png"
        vignettes_fiches.ecrire(planche, "e1", {"harry": _unie("#ff0000")})
        assert vignettes_fiches.lire(planche, "e2") == {}

    def test_absente_ou_abimee_aucune_vignette(self, qapp, tmp_path):
        assert vignettes_fiches.lire(tmp_path / "absente.png", "e1") == {}
        abimee = tmp_path / "abimee.png"
        abimee.write_bytes(b"pas un PNG")
        assert vignettes_fiches.lire(abimee, "e1") == {}
        sans_index = tmp_path / "sans_index.png"
        _unie("#ffffff").save(str(sans_index), "PNG")
        assert vignettes_fiches.lire(sans_index, "e1") == {}


class TestEmpreinte:
    FICHE = encyclopedie.Fiche("harry", "A", "b", "c", None, encyclopedie.ModeleJeu("data2.big", "body_harry"))

    def test_elle_suit_le_fichier_du_jeu(self, tmp_path, vieillir):
        archive = tmp_path / "data2.big"
        archive.write_bytes(b"BIGF" + bytes(60))
        vieillir(archive)
        avant = encyclopedie.empreinte(tmp_path, (self.FICHE,))
        assert avant is not None and avant == encyclopedie.empreinte(tmp_path, (self.FICHE,))
        archive.write_bytes(b"BIGF" + bytes(90))
        vieillir(archive)
        assert encyclopedie.empreinte(tmp_path, (self.FICHE,)) not in (None, avant)

    def test_un_fichier_qui_vient_de_changer_ne_garde_rien(self, tmp_path):
        (tmp_path / "data2.big").write_bytes(b"BIGF")
        assert encyclopedie.empreinte(tmp_path, (self.FICHE,)) is None

    def test_elle_suit_ce_que_la_fiche_releve(self, tmp_path):
        autre = encyclopedie.Fiche("harry", "A", "b", "c", None, encyclopedie.ModeleJeu("data2.big", "body_ron"))
        assert encyclopedie.empreinte(tmp_path, (self.FICHE,)) != encyclopedie.empreinte(tmp_path, (autre,))


class TestVignettes:
    """Une vignette se fabrique UNE fois : ensuite la mémoire, puis le disque d'une session à l'autre."""

    @pytest.fixture
    def lus(self, monkeypatch):
        lus: list[tuple[str, int]] = []

        def lire(dossier, fiche, cote=512):
            lus.append((fiche.cle, cote))
            return TRIANGLE, {}, None
        monkeypatch.setattr(maillages_ue1, "de_la_fiche", lire)
        return lus

    @staticmethod
    def _preparer(qtbot, jeu_dossier, cache, jeu="hp5"):
        vignettes = Vignettes(lambda _jeu: jeu_dossier, lambda: cache)
        vignettes.preparer(jeu, encyclopedie.PERSONNAGES, d_abord=True)
        qtbot.waitUntil(lambda: not vignettes.en_cours(jeu, encyclopedie.PERSONNAGES), timeout=10000)
        return vignettes

    def test_fabriquees_une_fois_puis_lues_sur_le_disque(self, qtbot, tmp_path, lus, vieillir):
        archive = tmp_path / "data2.big"
        archive.write_bytes(b"BIGF" + bytes(60))
        vieillir(archive)
        avec_modele = sorted(f.cle for f in encyclopedie.fiches(encyclopedie.PERSONNAGES, "hp5") if f.modele)
        premiere = self._preparer(qtbot, tmp_path, tmp_path / "cache")
        assert sorted(lus) == [(cle, 128) for cle in avec_modele]
        assert sorted(premiere.gardees("hp5", encyclopedie.PERSONNAGES)) == avec_modele
        planche = vignettes_fiches.chemin(tmp_path / "cache", "hp5", encyclopedie.PERSONNAGES)
        qtbot.waitUntil(planche.is_file, timeout=5000)
        # Redemander la même vue dans la session : rien n'est relu ni refait.
        lus.clear()
        premiere.preparer("hp5", encyclopedie.PERSONNAGES, d_abord=True)
        qtbot.waitUntil(lambda: not premiere.en_cours("hp5", encyclopedie.PERSONNAGES), timeout=5000)
        assert lus == []
        # Une autre session : la planche du disque suffit, aucun modèle n'est lu.
        seconde = self._preparer(qtbot, tmp_path, tmp_path / "cache")
        assert lus == [] and sorted(seconde.gardees("hp5", encyclopedie.PERSONNAGES)) == avec_modele
        vignette = seconde.gardees("hp5", encyclopedie.PERSONNAGES)["harry"]
        assert (vignette.width(), vignette.height()) == (104, 128)

    def test_le_fichier_du_jeu_change_les_vignettes_se_refont(self, qtbot, tmp_path, lus, vieillir):
        archive = tmp_path / "data2.big"
        archive.write_bytes(b"BIGF" + bytes(60))
        vieillir(archive)
        self._preparer(qtbot, tmp_path, tmp_path / "cache")
        planche = vignettes_fiches.chemin(tmp_path / "cache", "hp5", encyclopedie.PERSONNAGES)
        qtbot.waitUntil(planche.is_file, timeout=5000)
        archive.write_bytes(b"BIGF" + bytes(90))        # une mise à jour du jeu
        vieillir(archive)
        lus.clear()
        self._preparer(qtbot, tmp_path, tmp_path / "cache")
        assert lus, "la planche d'avant la mise à jour ne vaut plus"

    def test_un_jeu_qui_demarre_reprend_la_memoire(self, qtbot, tmp_path, lus, vieillir):
        archive = tmp_path / "data2.big"
        archive.write_bytes(b"BIGF" + bytes(60))
        vieillir(archive)
        vignettes = self._preparer(qtbot, tmp_path, tmp_path / "cache")
        planche = vignettes_fiches.chemin(tmp_path / "cache", "hp5", encyclopedie.PERSONNAGES)
        qtbot.waitUntil(planche.is_file, timeout=5000)
        vignettes.liberer()
        assert vignettes.gardees("hp5", encyclopedie.PERSONNAGES) == {}
        lus.clear()
        vignettes.preparer("hp5", encyclopedie.PERSONNAGES)       # le retour de partie : le disque suffit
        qtbot.waitUntil(lambda: not vignettes.en_cours("hp5", encyclopedie.PERSONNAGES), timeout=5000)
        assert vignettes.gardees("hp5", encyclopedie.PERSONNAGES) and lus == []

    def test_sans_carte_graphique_rien_ne_se_fabrique_en_fond(self, qtbot, tmp_path, lus):
        """Hors écran, le rendu est celui de QPainter (des centaines de millisecondes par modèle de
        HP5-HP6) : au lancement, seules les planches du disque se chargent."""
        vignettes = Vignettes(lambda _jeu: tmp_path, lambda: tmp_path / "cache")
        vignettes.preparer("hp5", encyclopedie.PERSONNAGES)
        qtbot.waitUntil(lambda: not vignettes.en_cours("hp5", encyclopedie.PERSONNAGES), timeout=5000)
        assert lus == [] and vignettes.gardees("hp5", encyclopedie.PERSONNAGES) == {}

    def test_la_vue_a_l_ecran_passe_devant(self, qtbot, tmp_path, lus):
        vignettes = Vignettes(lambda _jeu: tmp_path, lambda: tmp_path / "cache")
        vignettes.preparer("hp5", encyclopedie.PERSONNAGES, d_abord=True)
        vignettes.preparer("hp6", encyclopedie.PERSONNAGES, d_abord=True)
        qtbot.waitUntil(lambda: not vignettes.en_cours("hp6", encyclopedie.PERSONNAGES), timeout=10000)
        assert vignettes.en_cours("hp5", encyclopedie.PERSONNAGES), "HP6, demandé à l'écran, a fini le premier"
        qtbot.waitUntil(lambda: not vignettes.en_cours("hp5", encyclopedie.PERSONNAGES), timeout=10000)
        assert vignettes.gardees("hp5", encyclopedie.PERSONNAGES), "HP5, suspendu, a repris ensuite"
        attendues = sum(f.modele is not None for jeu in ("hp5", "hp6")
                        for f in encyclopedie.fiches(encyclopedie.PERSONNAGES, jeu))
        assert len(lus) == attendues, "aucune vignette faite deux fois"

    def test_sans_le_jeu_rien_a_preparer(self, qtbot, tmp_path, lus):
        vignettes = Vignettes(lambda _jeu: None, lambda: tmp_path / "cache")
        vignettes.preparer("hp5", encyclopedie.PERSONNAGES)
        qtbot.waitUntil(lambda: not vignettes.en_cours("hp5", encyclopedie.PERSONNAGES), timeout=5000)
        assert lus == [] and not (tmp_path / "cache").exists()

    def test_a_la_fermeture_plus_rien_ne_se_fabrique(self, qtbot, tmp_path, lus):
        vignettes = Vignettes(lambda _jeu: tmp_path, lambda: tmp_path / "cache")
        vignettes.preparer("hp6", encyclopedie.PERSONNAGES, d_abord=True)
        vignettes.arreter()
        qtbot.wait(150)
        assert len(lus) <= 1 and vignettes.gardees("hp6", encyclopedie.PERSONNAGES) == {}
