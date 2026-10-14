"""Les réglages du joueur survivent à un changement de version et à une réparation."""

from pathlib import Path

from src.core import reglages_conserves
from src.core.game_data import GameData
from src.core.post_install import apply_config_files

ANCIEN = ("[Accio.Window]\r\nWindowed=1\r\nScreenshotKey=123\r\n\r\n"
          "[Accio.Game]\r\nFOV=1.3\r\nAncienneCle=7\r\n")
NEUF = ("; Correctif v3\r\n[Accio.Window]\r\nWindowed=0\r\nScreenshotKey=123\r\n\r\n"
        "[Accio.Game]\r\nFOV=1.0 // champ de vision\r\nNouvelleCle=1\r\n")


def _jeu() -> GameData:
    return GameData.from_dict({
        "id": "hp4", "name": "HP4", "year": 2005, "description": "d", "developer": "d",
        "executable": "HP4/system/game.exe", "cover_image": "c.jpg"})


class TestFusion:
    def test_la_valeur_du_joueur_dans_le_fichier_neuf(self):
        texte, changees = reglages_conserves.fusionner(NEUF, ANCIEN)
        assert "Windowed=1" in texte and "FOV=1.3" in texte
        assert changees == 2

    def test_les_cles_neuves_restent_et_les_retirees_ne_reviennent_pas(self):
        texte, _ = reglages_conserves.fusionner(NEUF, ANCIEN)
        assert "NouvelleCle=1" in texte and "AncienneCle" not in texte

    def test_mise_en_page_du_neuf(self):
        texte, _ = reglages_conserves.fusionner(NEUF, ANCIEN)
        assert texte.startswith("; Correctif v3\r\n") and "\n" not in texte.replace("\r\n", "")

    def test_meme_cle_autre_section_pas_melangee(self):
        texte, changees = reglages_conserves.fusionner("[B]\nX=1\n", "[A]\nX=9\n")
        assert texte == "[B]\nX=1\n" and changees == 0


class TestChangementDeVersion:
    def test_mis_de_cote_puis_repose_apres_suppression(self, tmp_path):
        jeu = _jeu()
        dossier = tmp_path / "HP4" / "system"
        dossier.mkdir(parents=True)
        (dossier / "d3d9.ini").write_bytes(ANCIEN.encode())
        gardes = reglages_conserves.mettre_de_cote(jeu, tmp_path)
        (dossier / "d3d9.ini").unlink()                    # l'ancienne version part
        (dossier / "d3d9.ini").write_bytes(NEUF.encode())  # la nouvelle arrive
        assert reglages_conserves.reposer(jeu, tmp_path, gardes) == 1
        texte = (dossier / "d3d9.ini").read_text()
        assert "Windowed=1" in texte and "NouvelleCle=1" in texte
        assert (dossier / "d3d9.ini.origine").read_bytes() == NEUF.encode(), \
            "l'origine est celle de la NOUVELLE version"

    def test_un_fichier_que_la_version_neuve_n_a_pas_revient_tel_quel(self, tmp_path):
        jeu = _jeu()
        dossier = tmp_path / "HP4" / "system"
        dossier.mkdir(parents=True)
        (dossier / "dgVoodoo.conf").write_bytes(b"[General]\nScaling=1\n")
        gardes = reglages_conserves.mettre_de_cote(jeu, tmp_path)
        (dossier / "dgVoodoo.conf").unlink()
        reglages_conserves.reposer(jeu, tmp_path, gardes)
        assert (dossier / "dgVoodoo.conf").read_bytes() == b"[General]\nScaling=1\n"

    def test_rien_a_garder(self, tmp_path):
        assert reglages_conserves.mettre_de_cote(_jeu(), tmp_path) == {}


class TestConfigsDeDocuments:
    def _poser(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.core.post_install.get_documents_dir", lambda: tmp_path / "Docs")
        monkeypatch.setattr("src.core.post_install.allowed_config_roots",
                            lambda: [tmp_path / "Docs"])
        modele = tmp_path / "Jeux" / "HP3" / "config" / "User.ini"
        modele.parent.mkdir(parents=True)
        modele.write_text("modele")
        joueur = tmp_path / "Docs" / "HP3" / "User.ini"
        joueur.parent.mkdir(parents=True)
        joueur.write_text("touches du joueur")
        return joueur

    def test_l_installation_garde_la_config_du_joueur(self, tmp_path, monkeypatch):
        joueur = self._poser(tmp_path, monkeypatch)
        apply_config_files(tmp_path / "Jeux", "HP3", [("config/User.ini", "~/Documents/HP3/User.ini")],
                           garder_existants=True)
        assert joueur.read_text() == "touches du joueur"

    def test_la_remise_a_l_origine_ecrase_toujours(self, tmp_path, monkeypatch):
        joueur = self._poser(tmp_path, monkeypatch)
        apply_config_files(tmp_path / "Jeux", "HP3", [("config/User.ini", "~/Documents/HP3/User.ini")])
        assert joueur.read_text() == "modele"


def test_l_installeur_garde_les_configs():
    """Le point de passage de TOUTE installation (neuve, réparation, version)."""
    source = (Path(__file__).resolve().parent.parent / "src" / "core" / "installer.py").read_text(
        encoding="utf-8")
    assert "garder_existants=True" in source
