"""La difficulté propre à HP2, réglée depuis le launcher (Ludo, 2026-10-30)."""
import json
from pathlib import Path
from types import SimpleNamespace

from src.core import difficulte_jeu
from src.core.catalogue_blocs import _parse_difficulte
from src.core.game_data import GameData

VALEURS = ["DifficultyEasy", "DifficultyMedium", "DifficultyHard"]
# %INSTALL_DIR% est le dossier du jeu : <install_path>/HP2.
BLOC = {"file": "%INSTALL_DIR%\\User.ini", "section": "Engine.PlayerPawn",
        "key": "Difficulty", "values": VALEURS}
RACINE = Path(__file__).resolve().parent.parent


def _jeu(bloc=BLOC):
    return GameData.from_dict({
        "id": "hp2", "name": "HP2", "year": 2002, "description": "d", "developer": "d",
        "executable": "HP2/system/Game.exe", "cover_image": "c.jpg", "difficulty": bloc})


def _ini(tmp_path, contenu="[Engine.PlayerPawn]\nDifficulty=DifficultyEasy\n"):
    chemin = tmp_path / "HP2" / "User.ini"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="cp1252")
    return chemin


def test_lire_puis_ecrire_dans_le_fichier_du_jeu(tmp_path):
    config = SimpleNamespace(install_path=tmp_path)
    chemin = _ini(tmp_path)
    jeu = _jeu()
    assert difficulte_jeu.lire(jeu, config) == 0
    assert difficulte_jeu.ecrire(jeu, config, 2)
    assert "Difficulty=DifficultyHard" in chemin.read_text(encoding="cp1252")
    assert difficulte_jeu.lire(jeu, config) == 2


def test_cle_absente_ou_inconnue_se_lit_facile_comme_le_moteur(tmp_path):
    config = SimpleNamespace(install_path=tmp_path)
    _ini(tmp_path, "[Engine.PlayerPawn]\nName=Harry\n")
    assert difficulte_jeu.lire(_jeu(), config) == 0
    _ini(tmp_path, "[Engine.PlayerPawn]\nDifficulty=difficultymedium\n")
    assert difficulte_jeu.lire(_jeu(), config) == 1, "la casse est ignorée"


def test_rien_n_est_cree_ni_ecrit_hors_des_crans(tmp_path):
    config = SimpleNamespace(install_path=tmp_path)
    jeu = _jeu()
    assert not difficulte_jeu.ecrire(jeu, config, 1), "fichier absent : c'est le jeu qui l'écrit"
    assert not (tmp_path / "HP2" / "User.ini").exists()
    _ini(tmp_path)
    assert not difficulte_jeu.ecrire(jeu, config, 3)
    assert not difficulte_jeu.ecrire(jeu, config, -1)


def test_un_jeu_sans_bloc_n_a_pas_de_reglage(tmp_path):
    config = SimpleNamespace(install_path=tmp_path)
    jeu = _jeu(None)
    assert jeu.difficulte is None
    assert difficulte_jeu.lire(jeu, config) is None
    assert not difficulte_jeu.ecrire(jeu, config, 1)


def test_le_bloc_douteux_est_ignore_en_entier():
    assert _parse_difficulte(BLOC) is not None
    assert _parse_difficulte({**BLOC, "values": VALEURS[:2]}) is None
    assert _parse_difficulte({**BLOC, "values": [VALEURS[0]] * 3}) is None
    assert _parse_difficulte({**BLOC, "values": [*VALEURS[:2], "Hard\nX=1"]}) is None
    assert _parse_difficulte({**BLOC, "key": "Difficulty]"}) is None
    assert _parse_difficulte({**BLOC, "section": ""}) is None
    assert _parse_difficulte({**BLOC, "values": "DifficultyEasy"}) is None
    assert _parse_difficulte(None) is None


def test_le_catalogue_embarque_declare_la_difficulte_de_hp2():
    embarque = json.loads((RACINE / "src" / "data" / "games.json").read_text(encoding="utf-8"))
    hp2 = next(g for g in embarque["games"] if g["id"] == "hp2")
    bloc = _parse_difficulte(hp2.get("difficulty"))
    assert bloc is not None and bloc.values == tuple(VALEURS)
    assert bloc.file.endswith("\\Harry Potter II\\User.ini") and bloc.section == "Engine.PlayerPawn"


def test_la_liste_de_la_fiche_ecrit_le_cran_choisi(qtbot, tmp_path):
    from PyQt6.QtWidgets import QComboBox

    from src.ui.game_settings_dialog import GameSettingsDialog
    chemin = _ini(tmp_path)
    manager = SimpleNamespace(game_language=lambda g: None, langues_disponibles=lambda g: (),
                              config=SimpleNamespace(install_path=tmp_path, reprise={}))
    dlg = GameSettingsDialog(_jeu(), manager, lambda c: True)
    qtbot.addWidget(dlg)
    listes = [c for c in dlg.findChildren(QComboBox) if c.count() == 3 and c.itemData(2) == 2]
    assert len(listes) == 1
    assert listes[0].currentIndex() == 0
    listes[0].setCurrentIndex(1)
    assert "Difficulty=DifficultyMedium" in chemin.read_text(encoding="cp1252")
