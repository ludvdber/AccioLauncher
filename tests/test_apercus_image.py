"""Les aperçus avant/après de la page Image (`core/apercus_image.py`, `ui/comparateur_image.py`)."""

import json

from PIL import Image

from src.core import apercus_image
from src.core.apercus_image import Apercu


def _dossier(tmp_path, index, fichiers=("lissage_accio.jpg", "lissage_autre.jpg")):
    (tmp_path / "hp5").mkdir()
    for nom in fichiers:
        Image.new("RGB", (64, 36), (40, 60, 90)).save(tmp_path / "hp5" / nom)
    (tmp_path / "index.json").write_text(json.dumps(index), encoding="utf-8")
    return tmp_path


class TestApercu:
    def test_un_reglage_qui_a_ses_deux_images(self, tmp_path):
        d = _dossier(tmp_path, {"hp5": {"lissage": {"autre": "Coupé"}}})
        a = apercus_image.apercu("hp5", "lissage", d)
        assert a == Apercu(d / "hp5" / "lissage_accio.jpg", d / "hp5" / "lissage_autre.jpg", "Coupé")

    def test_rien_pour_un_autre_jeu_ou_un_autre_reglage(self, tmp_path):
        d = _dossier(tmp_path, {"hp5": {"lissage": {"autre": "Coupé"}}})
        assert apercus_image.apercu("hp4", "lissage", d) is None
        assert apercus_image.apercu("hp5", "halo", d) is None

    def test_une_image_manquante_ne_montre_rien(self, tmp_path):
        d = _dossier(tmp_path, {"hp5": {"lissage": {"autre": "Coupé"}}}, fichiers=("lissage_accio.jpg",))
        assert apercus_image.apercu("hp5", "lissage", d) is None

    def test_un_index_absent_ou_mal_forme_ne_leve_pas(self, tmp_path):
        assert apercus_image.apercu("hp5", "lissage", tmp_path) is None
        (tmp_path / "index.json").write_text("{pas du json", encoding="utf-8")
        assert apercus_image.apercu("hp5", "lissage", tmp_path) is None
        (tmp_path / "index.json").write_text(json.dumps({"hp5": {"lissage": {"autre": 3}}}), encoding="utf-8")
        assert apercus_image.apercu("hp5", "lissage", tmp_path) is None

    def test_un_libelle_hors_liste_n_est_pas_montre(self, tmp_path):
        """Il ne s'afficherait qu'en français : pas de traduction sans littéral dans le code."""
        d = _dossier(tmp_path, {"hp5": {"lissage": {"autre": "Inventé"}}})
        assert apercus_image.apercu("hp5", "lissage", d) is None

    def test_chaque_libelle_est_traduit(self):
        for langue in ("en", "es"):
            textes = json.loads((apercus_image.ASSETS_DIR.parent / "src" / "data" / "i18n" / f"{langue}.json").read_text(encoding="utf-8"))["strings"]
            assert all(lib in textes for lib in apercus_image.LIBELLES), langue

    def test_les_apercus_livres_ont_tous_leurs_images(self):
        """Chaque entrée de l'index livré a ses deux images, et son libellé est traduit."""
        index = json.loads((apercus_image.DOSSIER / "index.json").read_text(encoding="utf-8"))
        en = json.loads((apercus_image.ASSETS_DIR.parent / "src" / "data" / "i18n" / "en.json").read_text(encoding="utf-8"))["strings"]
        assert index, "aucun aperçu livré"
        for jeu, reglages in index.items():
            for ident, fiche in reglages.items():
                assert apercus_image.apercu(jeu, ident) is not None, (jeu, ident)
                assert fiche["autre"] in en, fiche["autre"]


class TestComparateur:
    def test_cache_sans_apercu_montre_avec(self, qtbot, tmp_path):
        from src.ui.comparateur_image import Comparateur
        d = _dossier(tmp_path, {"hp5": {"lissage": {"autre": "Coupé"}}})
        c = Comparateur(264)
        qtbot.addWidget(c)
        assert c.isHidden()
        c.montrer(apercus_image.apercu("hp5", "lissage", d))
        assert not c.isHidden()
        c.montrer(None)
        assert c.isHidden()

    def test_le_trait_suit_la_souris_et_revient_au_milieu(self, qtbot, tmp_path):
        from PyQt6.QtCore import QPoint, Qt
        from src.ui.comparateur_image import Comparateur
        d = _dossier(tmp_path, {"hp5": {"lissage": {"autre": "Coupé"}}})
        c = Comparateur(264)
        qtbot.addWidget(c)
        c.montrer(apercus_image.apercu("hp5", "lissage", d))
        c.show()
        qtbot.mouseMove(c, QPoint(66, 40))
        qtbot.waitUntil(lambda: abs(c._part - 0.25) < 0.01)
        c.leaveEvent(None)
        assert c._part == 0.5
        assert c.cursor().shape() == Qt.CursorShape.SizeHorCursor

    def test_le_meme_apercu_ne_ramene_pas_le_trait(self, qtbot, tmp_path):
        """La fiche se refait à chaque cran d'un curseur : le trait ne doit pas sauter au milieu."""
        from src.ui.comparateur_image import Comparateur
        d = _dossier(tmp_path, {"hp5": {"lissage": {"autre": "Coupé"}}})
        c = Comparateur(264)
        qtbot.addWidget(c)
        a = apercus_image.apercu("hp5", "lissage", d)
        c.montrer(a)
        c._part = 0.8
        c.montrer(apercus_image.apercu("hp5", "lissage", d))
        assert c._part == 0.8
