"""Les choix des Paramètres en tuiles (`src/ui/choix_visuels.py`) et le ciel du bandeau (maquettes A et B,
Ludo, 2026-11-15)."""

import pytest

pytest.importorskip("pytestqt")

from src.core.config import ASSETS_DIR  # noqa: E402
from src.core.season import SEASON_LABELS, SEASONS  # noqa: E402
from src.ui import choix_visuels as cv  # noqa: E402


def _choix(qtbot, n=3, **kw):
    choix = cv.ChoixEnTuiles(lambda nom, d: cv.tuile_effets(str(d), nom, ""), colonnes=n, **kw)
    qtbot.addWidget(choix)
    for i in range(n):
        choix.addItem(f"Choix {i}", f"d{i}")
    return choix


class TestChoixEnTuiles:
    def test_parle_comme_une_liste_deroulante(self, qtbot):
        choix = _choix(qtbot)
        assert choix.count() == 3 and choix.findData("d2") == 2 and choix.findData("absent") == -1
        assert choix.itemData(1) == "d1" and choix.itemText(1) == "Choix 1"
        with qtbot.waitSignal(choix.currentIndexChanged) as recu:
            choix.setCurrentIndex(2)
        assert recu.args == [2] and choix.currentData() == "d2" and choix.currentText() == "Choix 2"

    def test_un_clic_choisit_une_seule_tuile(self, qtbot):
        choix = _choix(qtbot)
        choix.setCurrentIndex(0)
        recus = []
        choix.currentIndexChanged.connect(recus.append)
        choix.tuiles[1].click()
        assert recus == [1] and [t.isChecked() for t in choix.tuiles] == [False, True, False]
        choix.setCurrentIndex(1)   # déjà choisi : aucun signal de plus
        assert recus == [1]

    def test_la_grille_se_replie_quand_la_place_manque(self, qtbot):
        choix = _choix(qtbot, n=7, largeur_min=118)
        choix.show()
        choix.resize(1100, 200)
        assert choix._n == 7
        choix.resize(300, 200)
        assert choix._n == 2

    def test_chaque_tuile_se_peint(self, qtbot):
        tuiles = [cv.tuile_maison("Gryffondor", "#e0584f", "#6b1a1a"), cv.tuile_effets("non", "Non", "")]
        tuiles += [cv.tuile_ambiance(SEASON_LABELS[s], s) for s in SEASONS]
        for tuile in tuiles:
            qtbot.addWidget(tuile)
            tuile.resize(150, tuile.height())
            tuile.setCheckable(True)
            tuile.setChecked(True)
            assert not tuile.grab().isNull()


class TestAmbiances:
    def test_chaque_ambiance_a_son_dessin(self):
        """La liste vient de `season.SEASONS` : une ambiance ajoutée sans dessin se verrait ici."""
        assert set(SEASONS) <= set(cv._AMBIANCES)

    def test_le_nom_et_la_date(self):
        assert cv.nom_et_date("Halloween (octobre)") == ("Halloween", "octobre")
        assert cv.nom_et_date("Aucune") == ("Aucune", "")

    def test_poudlard_sans_sa_couleur_entre_parentheses(self, qtbot):
        tuile = cv.tuile_maison("Poudlard (Or)", "#e8c547", "#8a6510")
        qtbot.addWidget(tuile)
        assert tuile._nom == "Poudlard"


class TestDrapeaux:
    def test_les_trois_langues_ont_leur_drapeau_et_sa_licence(self, qtbot):
        assert (ASSETS_DIR / "icons" / "drapeaux" / "LICENSE.txt").is_file()
        for code in ("fr", "en", "es"):
            b = cv.pastille_langue("Langue", code)
            qtbot.addWidget(b)
            assert not b.icon().isNull(), code

    def test_une_langue_sans_drapeau_garde_sa_pastille(self, qtbot):
        b = cv.pastille_langue("Deutsch", "de")
        qtbot.addWidget(b)
        assert b.icon().isNull() and b.text() == "Deutsch"


class TestCielDesParametres:
    def test_le_bandeau_est_le_ciel_et_porte_les_rubriques(self, qtbot, tmp_path, monkeypatch):
        from src.core.config import Config
        from src.core.game_manager import GameManager
        from src.ui.bandeau_jeu import CIEL_PARAMETRES, Bandeau
        from src.ui.settings_panel import SettingsDialog
        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "c.json")
        assert CIEL_PARAMETRES.is_file()
        cfg = Config(install_path=tmp_path / "g", cache_path=tmp_path / "g" / "c")
        dlg = SettingsDialog(cfg, GameManager(cfg))
        qtbot.addWidget(dlg)
        ciel = dlg.findChild(Bandeau)
        assert ciel is not None and ciel._couvrir and not ciel._image().isNull()
        assert dlg._nav.parentWidget() is ciel
        dlg.resize(1280, 800)
        assert not ciel.grab().isNull()
        dlg._shutdown_scan()

    def test_couvrir_remplit_toute_la_largeur(self, qtbot):
        """Le ciel couvre le bandeau à toute largeur : pas de bande vide à gauche d'une grande fenêtre."""
        from PyQt6.QtCore import QSize
        from src.ui.bandeau_jeu import CIEL_PARAMETRES, Bandeau
        ciel = Bandeau(CIEL_PARAMETRES, hauteur=132, couvrir=True)
        qtbot.addWidget(ciel)
        for largeur in (900, 2560, 3840):
            ciel.resize(QSize(largeur, 132))
            fond = ciel._fond()
            assert fond is not None and fond.width() >= largeur * fond.devicePixelRatio() - 1
