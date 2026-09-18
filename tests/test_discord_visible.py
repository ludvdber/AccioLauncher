"""Le Discord doit se trouver sans ouvrir les Paramètres.

Ludo, 2026-09-18 : l'exe circule de main en main, et qui l'a reçu d'un ami ne
passe jamais par le site. Le Discord — la communauté, et surtout l'endroit où
demander de l'aide — n'était joignable que par Paramètres → À propos, que
personne n'ouvre. Il est désormais à trois endroits :

- un bouton permanent en haut à droite, à côté des statistiques ;
- l'avertissement « le jeu n'a pas démarré », devenu cliquable ;
- le dialogue de plantage, qui disait « à coller sur le Discord » sans donner
  le lien, et n'offrait qu'une issue GitHub — que la plupart des joueurs ne
  savent pas ouvrir, faute de compte.
"""

import ast
from pathlib import Path

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QPushButton  # noqa: E402

from src.core import liens  # noqa: E402
from src.core.config import Config  # noqa: E402
from src.core.game_data import load_catalog  # noqa: E402


@pytest.fixture
def fenetre(qtbot, tmp_path, monkeypatch):
    """Vraie MainWindow sur une config temporaire, ouverts vers l'extérieur
    interceptés (aucun navigateur ne doit s'ouvrir pendant la suite)."""
    monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
    monkeypatch.setattr("src.ui.main_window.MainWindow._start_update_check",
                        lambda self: None)
    ouverts: list[str] = []
    monkeypatch.setattr("src.ui.main_window.open_url", ouverts.append)
    Config(install_path=tmp_path / "g", cache_path=tmp_path / "g" / "c",
           langue="fr", autoplay_videos=False).save()
    from src.ui.main_window import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)
    win.resize(980, 660)
    win.show()
    qtbot.waitExposed(win)
    win.ouverts = ouverts
    return win


class TestUneSeuleAdresse:
    def test_toutes_en_https(self):
        for url in (liens.SITE_URL, liens.DISCORD_URL, liens.KOFI_URL):
            assert url.startswith("https://"), url

    def test_aucune_copie_ailleurs_dans_le_code(self):
        """Trois copies d'une invitation divergent le jour où elle change.

        Le Ko-fi et le site étaient déjà écrits en double avant ce module. Le
        balayage porte sur les LITTÉRAUX (AST), pas sur le texte brut : un
        commentaire qui cite l'adresse n'est pas une copie.
        """
        adresses = {liens.SITE_URL, liens.DISCORD_URL, liens.KOFI_URL}
        fautifs = []
        for fichier in [*Path("src").rglob("*.py"), Path("main.py")]:
            if fichier.name == "liens.py":
                continue
            arbre = ast.parse(fichier.read_text(encoding="utf-8"))
            for noeud in ast.walk(arbre):
                if isinstance(noeud, ast.Constant) and noeud.value in adresses:
                    fautifs.append(f"{fichier}:{noeud.lineno}")
        assert not fautifs, f"adresse recopiée au lieu d'importer src.core.liens : {fautifs}"


class TestBoutonPermanent:
    def test_present_visible_et_a_gauche_des_statistiques(self, fenetre):
        win = fenetre
        assert win._btn_discord.isVisible()
        stats, discord = win._btn_stats.geometry(), win._btn_discord.geometry()
        assert discord.top() == stats.top(), "pas sur la même rangée"
        assert discord.right() < stats.left(), "doit être à GAUCHE des statistiques"
        assert not discord.intersects(stats)

    def test_le_clic_ouvre_le_discord(self, fenetre, qtbot):
        qtbot.mouseClick(fenetre._btn_discord, Qt.MouseButton.LeftButton)
        assert fenetre.ouverts == [liens.DISCORD_URL]

    def test_l_infobulle_dit_a_quoi_il_sert(self, fenetre):
        """Une silhouette se reconnaît, mais « Discord » seul ne dit pas qu'on
        y trouve de l'aide — et c'est pour ça que le bouton existe."""
        assert "Discord" in fenetre._btn_discord.toolTip()
        assert fenetre._btn_discord.accessibleName() == fenetre._btn_discord.toolTip()

    def test_s_efface_en_mode_cinema(self, fenetre):
        fenetre._on_cinema(True)
        assert not any(b.isVisible() for b in fenetre._commandes)
        fenetre._on_cinema(False)
        assert all(b.isVisible() for b in fenetre._commandes)

    def test_descend_sous_le_bandeau_comme_les_autres(self, fenetre, qtbot):
        """Le placement vaut pour TOUTES les commandes : un bouton oublié dans
        la boucle recouvrirait la croix du bandeau de mise à jour."""
        avant = fenetre._btn_discord.geometry().top()
        fenetre._launcher_update_asked = True       # pas de dialogue modal ici
        fenetre._on_launcher_update(
            "9.9.9", "https://github.com/ludvdber/AccioLauncher/releases",
            "https://github.com/ludvdber/AccioLauncher/releases/download/v9/A.exe", "")
        qtbot.waitUntil(lambda: fenetre._btn_discord.geometry().top() > avant,
                        timeout=2000)
        tops = {b.geometry().top() for b in fenetre._commandes}
        assert len(tops) == 1, f"commandes désalignées : {tops}"


class TestLeJeuQuiNeDemarrePas:
    def _nom_le_plus_long(self) -> str:
        return max((g.name for g in load_catalog().games), key=len)

    def test_le_toast_mene_au_discord(self, fenetre, qtbot):
        fenetre._on_game_exited("HP1", partie=False)
        assert fenetre._toast.isVisible()
        assert "Discord" in fenetre._toast.text()
        qtbot.mouseClick(fenetre._toast, Qt.MouseButton.LeftButton)
        assert fenetre.ouverts == [liens.DISCORD_URL]

    def test_une_partie_normale_ne_propose_pas_d_aide(self, fenetre):
        """Rien ne s'affiche quand tout va bien — la règle du projet."""
        fenetre._on_game_exited("HP1", partie=True)
        assert "Discord" not in fenetre._toast.text()

    def test_tient_dans_la_plus_petite_fenetre(self, fenetre):
        """Le toast n'a ni retour à la ligne ni largeur maximale : sur une
        seule ligne, le nom le plus long du catalogue l'aurait fait dépasser
        d'une fenêtre de 980 px. D'où l'aide sur une seconde ligne. La police
        substituée hors écran est ~22 % plus large que Gelasio : la mesure
        est prudente."""
        fenetre._on_game_exited(self._nom_le_plus_long(), partie=False)
        toast = fenetre._toast
        assert toast.text().count("\n") == 1
        assert toast.geometry().left() >= 0
        assert toast.geometry().right() <= fenetre.width()

    def test_le_nom_du_jeu_n_est_jamais_interprete(self, fenetre):
        """Le toast affiche du texte du catalogue DISTANT (noms de jeux)."""
        assert fenetre._toast.textFormat() == Qt.TextFormat.PlainText


class TestDialogueDePlantage:
    @pytest.fixture
    def dialogue(self, qtbot, monkeypatch):
        ouverts: list[str] = []
        monkeypatch.setattr("src.ui.utils.open_url", ouverts.append)
        from src.ui.crash_dialog import construire_dialogue

        dlg = construire_dialogue("Traceback (most recent call last): …")
        qtbot.addWidget(dlg)
        dlg.show()
        qtbot.waitExposed(dlg)
        dlg.ouverts = ouverts
        return dlg

    def _bouton(self, dlg, nom: str) -> QPushButton:
        return dlg.findChild(QPushButton, nom)

    def test_un_bouton_ouvre_le_discord(self, dialogue, qtbot):
        bouton = self._bouton(dialogue, "crashDiscord")
        assert bouton is not None and bouton.isVisible()
        qtbot.mouseClick(bouton, Qt.MouseButton.LeftButton)
        assert dialogue.ouverts == [liens.DISCORD_URL]

    def test_aide_et_launcher_sur_deux_rangees(self, dialogue):
        """Obtenir de l'aide d'un côté, décider du launcher de l'autre."""
        boutons = {b.text(): b.geometry().top()
                   for b in dialogue.findChildren(QPushButton)}
        rangees = sorted(set(boutons.values()))
        assert len(rangees) == 2, boutons
        discord = self._bouton(dialogue, "crashDiscord").geometry().top()
        assert discord == rangees[0], "l'aide doit venir en premier"

    def test_ne_deborde_pas_de_sa_largeur_minimale(self, dialogue):
        """Cinq boutons sur une rangée l'élargissaient bien au-delà de 560 px."""
        assert dialogue.sizeHint().width() <= dialogue.minimumWidth() + 40, (
            f"dialogue élargi à {dialogue.sizeHint().width()} px")
