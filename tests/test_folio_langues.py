"""Le texte du folio de HP1 à HP3 dans la langue du launcher : les extensions des jeux UE1.

Audit UI, 2026-11-13 : en espagnol, le folio cherchait `HPmenu.esp`, alors que les jeux nomment
leur espagnol `spa` ; tout retombait sur l'anglais. HP3 écrit `.Ger` et `.Ita`.
"""

import pytest

from src.core import folio, folio_hp3


@pytest.mark.parametrize(("langue", "fichier"), [
    ("es", "HPmenu.spa"), ("fr", "HPmenu.fre"), ("en", "HPMenu.int")])
def test_hp1_et_hp2(tmp_path, langue, fichier):
    for nom in ("HPMenu.int", "HPmenu.fre", "HPmenu.spa"):
        (tmp_path / nom).write_bytes(b"")
    assert folio.fichier_textes(tmp_path, langue) == tmp_path / fichier


@pytest.mark.parametrize(("langue", "fichier"), [
    ("es", "HpMenu.Spa"), ("de", "HpMenu.Ger"), ("it", "HpMenu.Ita"), ("en", "HpMenu.int")])
def test_hp3(tmp_path, langue, fichier):
    for nom in ("HpMenu.int", "HpMenu.Spa", "HpMenu.Ger", "HpMenu.Ita"):
        (tmp_path / nom).write_bytes(b"")
    assert folio_hp3._fichier(tmp_path, "hpmenu", langue) == tmp_path / fichier
