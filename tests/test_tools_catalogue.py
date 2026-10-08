"""Les outils de `tools/` qu'aucun test ne touchait (audit du 2026-10-07, ACT-021).

`apply_catalog_i18n.py` réécrit le catalogue PUBLIÉ : une passe qui doublerait
un bloc, échapperait les accents (règle 56) ou effacerait une langue qu'il ne
connaît pas partirait chez tous les joueurs à la publication suivante. Le
catalogue de test est FABRIQUÉ, jamais lu dans `games.json` (règle 78).
"""

import importlib
import json
import sys

import pytest

outil = importlib.import_module("tools.apply_catalog_i18n")

NOM_FR = "Harry Potter à l'École des Sorciers"


def _catalogue(**jeu) -> dict:
    base = {
        "id": "hp1", "name": NOM_FR, "description": "Texte sans traduction connue.",
        "tags": ["Aventure", "Énigmes"],
        "versions": [{"version": "1.0", "changes": ["Version originale du jeu"]}],
    }
    base.update(jeu)
    return {"catalog_version": "0.0", "games": [base]}


def _ecrire(chemin, catalogue: dict, *, crlf=False, indent=4) -> None:
    texte = json.dumps(catalogue, ensure_ascii=False, indent=indent) + "\n"
    if crlf:
        texte = texte.replace("\n", "\r\n")
    chemin.write_bytes(texte.encode("utf-8"))


class TestApplyCatalogI18n:
    def test_deux_passes_donnent_le_meme_fichier(self, tmp_path):
        chemin = tmp_path / "games.json"
        _ecrire(chemin, _catalogue())
        outil.main(["x", str(chemin)])
        premiere = chemin.read_bytes()
        outil.main(["x", str(chemin)])
        assert chemin.read_bytes() == premiere
        jeu = json.loads(premiere)["games"][0]
        assert set(jeu["i18n"]) == {"en", "es"}
        assert jeu["i18n"]["en"]["name"] == "Harry Potter and the Philosopher's Stone"

    def test_les_accents_restent_lisibles(self, tmp_path):
        chemin = tmp_path / "games.json"
        _ecrire(chemin, _catalogue())
        outil.main(["x", str(chemin)])
        texte = chemin.read_text(encoding="utf-8")
        assert "\\u00" not in texte
        assert "Énigmes" in texte and "Exploración" not in texte  # rien d'inventé
        assert "Puzles" in texte

    def test_une_langue_inconnue_de_l_outil_est_conservee(self, tmp_path):
        chemin = tmp_path / "games.json"
        _ecrire(chemin, _catalogue(i18n={"de": {"name": "Harry Potter und der Stein der Weisen"}}))
        outil.main(["x", str(chemin)])
        jeu = json.loads(chemin.read_text(encoding="utf-8"))["games"][0]
        assert jeu["i18n"]["de"] == {"name": "Harry Potter und der Stein der Weisen"}
        assert "en" in jeu["i18n"]

    def test_la_mise_en_forme_du_fichier_est_gardee(self, tmp_path):
        """Le dépôt du catalogue est en CRLF à 4 espaces : le reformater noierait
        les vraies modifications dans un diff de 400 lignes."""
        chemin = tmp_path / "games.json"
        _ecrire(chemin, _catalogue(), crlf=True, indent=4)
        outil.main(["x", str(chemin)])
        brut = chemin.read_bytes()
        assert brut.count(b"\n") == brut.count(b"\r\n")
        assert b'\r\n    "games"' in brut

    def test_les_chaines_sans_traduction_sont_listees(self, tmp_path, capsys):
        chemin = tmp_path / "games.json"
        _ecrire(chemin, _catalogue())
        assert outil.main(["x", str(chemin)]) == 1
        assert "Texte sans traduction connue." in capsys.readouterr().out

    def test_tout_traduit_rend_zero(self, tmp_path):
        chemin = tmp_path / "games.json"
        _ecrire(chemin, _catalogue(description=next(iter(outil.DESCRIPTIONS))))
        assert outil.main(["x", str(chemin)]) == 0


class TestLesAutresOutilsSImportent:
    """Au minimum, qu'un renommage dans `src/` ne les casse pas en silence."""

    def test_verifier_wine(self):
        importlib.import_module("tools.verifier_wine")

    @pytest.mark.skipif(sys.platform != "win32", reason="lit le registre Windows")
    def test_capture_registre(self):
        importlib.import_module("tools.capture_registre")
