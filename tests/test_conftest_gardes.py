"""Les gardes de `conftest.py` qui tiennent la suite hors des vrais fichiers."""

import json


def test_le_catalogue_en_cache_n_est_pas_celui_du_poste(tmp_path):
    """Audit du 2026-10-29 : `LOCAL_CATALOG_PATH` n'était pas redirigé, et
    `load_catalog()` lisait le cache du launcher installé sur le poste."""
    from src.core import config, updater
    assert config.LOCAL_CATALOG_PATH.is_relative_to(tmp_path)
    assert updater._LOCAL_CATALOG_PATH == config.LOCAL_CATALOG_PATH


def test_un_cache_plus_recent_est_bien_celui_du_test(tmp_path):
    """Le chemin redirigé est celui que `load_catalog` lit vraiment."""
    from src.core import config
    from src.core.game_data import load_catalog
    jeu = {"id": "hp_cache", "name": "Cache", "year": 2001, "description": "d",
           "developer": "dev", "executable": "X/x.exe", "cover_image": "c.png"}
    # Jamais d'écriture tant que la redirection n'est pas prouvée.
    assert config.LOCAL_CATALOG_PATH.is_relative_to(tmp_path)
    config.LOCAL_CATALOG_PATH.write_text(
        json.dumps({"catalog_version": "99999", "games": [jeu]}), encoding="utf-8")
    assert [g.id for g in load_catalog().games] == ["hp_cache"]
