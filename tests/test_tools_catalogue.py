"""Les outils de `tools/` qu'aucun test ne touchait (audit du 2026-10-07, ACT-021).

`verifier_i18n_catalogue.py` dit ce qui manque dans les blocs `i18n` du
catalogue, la source des traductions, sans jamais l'écrire (l'ancien
`apply_catalog_i18n.py` le réécrivait depuis des tables qui ne connaissaient
plus que 7 versions sur 38). Le catalogue de test est FABRIQUÉ, jamais lu dans
`games.json` (règle 78).
"""

import importlib
import json
import sys

import pytest

outil = importlib.import_module("tools.verifier_i18n_catalogue")

NOM_FR = "Harry Potter à l'École des Sorciers"


def _catalogue(**jeu) -> dict:
    base = {
        "id": "hp1", "name": NOM_FR, "description": "Texte sans traduction connue.",
        "versions": [{"version": "1.0", "changes": ["Version originale du jeu"]}],
    }
    base.update(jeu)
    return {"catalog_version": "0.0", "games": [base]}


def _ecrire(chemin, catalogue: dict, *, crlf=False, indent=4) -> None:
    texte = json.dumps(catalogue, ensure_ascii=False, indent=indent) + "\n"
    if crlf:
        texte = texte.replace("\n", "\r\n")
    chemin.write_bytes(texte.encode("utf-8"))


_TRADUIT = {"en": {"name": "Philosopher's Stone", "description": "Text."},
            "es": {"name": "La piedra filosofal", "description": "Texto."}}


class TestVerifierI18nCatalogue:
    def test_tout_traduit_rend_zero_et_n_ecrit_rien(self, tmp_path, capsys):
        chemin = tmp_path / "games.json"
        _ecrire(chemin, _catalogue(versions=[], i18n=_TRADUIT), crlf=True)
        avant = chemin.read_bytes()
        assert outil.main(["x", str(chemin)]) == 0
        assert chemin.read_bytes() == avant
        assert "tout est traduit" in capsys.readouterr().out

    def test_une_traduction_absente_est_listee(self, tmp_path, capsys):
        chemin = tmp_path / "games.json"
        _ecrire(chemin, _catalogue())
        assert outil.main(["x", str(chemin)]) == 1
        sortie = capsys.readouterr().out
        assert "en · hp1 · name" in sortie and "es · hp1 v1.0 · changes" in sortie

    def test_un_changelog_incomplet_compte_comme_absent(self):
        version = {"version": "1.1", "changes": ["a", "b"],
                   "i18n": {"en": {"changes": ["a"]}, "es": {"changes": ["a", "b"]}}}
        assert outil.manquants(_catalogue(versions=[version], i18n=_TRADUIT)) == ["en · hp1 v1.1 · changes"]

    def test_le_role_d_un_contributeur_mais_pas_son_nom(self):
        catalogue = _catalogue(versions=[], i18n=_TRADUIT)
        catalogue["contributors"] = [{"name": "Sara", "role": "Tests", "i18n": {"en": {"role": "Testing"}}}]
        assert outil.manquants(catalogue) == ["es · contributeur Sara · role"]


class TestLesAutresOutilsSImportent:
    """Au minimum, qu'un renommage dans `src/` ne les casse pas en silence."""

    def test_verifier_wine(self):
        importlib.import_module("tools.verifier_wine")

    @pytest.mark.skipif(sys.platform != "win32", reason="lit le registre Windows")
    def test_capture_registre(self):
        importlib.import_module("tools.capture_registre")
