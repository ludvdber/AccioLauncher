"""Un fichier = une lecture par session, sauf s'il change (`core/octets_gardes`, 2026-11-16).

Le banc de rapidité comptait la sauvegarde de HP5 ouverte 9 fois sur un parcours, chaque
`GameSaveInfo` de HP1 7 fois, `sauvegardes.json` 10 fois."""

import builtins
import json
from pathlib import Path

import pytest

from src.core import folio, folio_hp4, octets_gardes, sauvegardes


@pytest.fixture
def ouvertures(monkeypatch):
    """Les fichiers ouverts en lecture, par nom."""
    vus: list[str] = []
    vrai = builtins.open

    def compter(fichier, mode="r", *args, **kwargs):
        if "r" in mode and isinstance(fichier, (str, Path)):
            vus.append(Path(fichier).name)
        return vrai(fichier, mode, *args, **kwargs)
    monkeypatch.setattr(builtins, "open", compter)
    octets_gardes.liberer()
    yield vus
    octets_gardes.liberer()


def test_lu_une_fois_tant_qu_il_ne_change_pas(tmp_path, vieillir, ouvertures):
    partie = tmp_path / "HPOOTP"
    partie.write_bytes(b"partie de Ludo")
    vieillir(partie)
    assert octets_gardes.lire(partie) == b"partie de Ludo"
    assert octets_gardes.lire(partie) == b"partie de Ludo"
    assert octets_gardes.lire(partie, 6) == octets_gardes.lire(partie, 6) == b"partie"
    assert ouvertures.count("HPOOTP") == 2, "une fois entier, une fois son en-tête"
    partie.write_bytes(b"partie plus longue")       # le jeu a sauvegardé
    vieillir(partie)
    assert octets_gardes.lire(partie) == b"partie plus longue"
    assert ouvertures.count("HPOOTP") == 3


def test_un_fichier_qui_vient_d_etre_ecrit_se_relit(tmp_path, ouvertures):
    partie = tmp_path / "HPGOF"
    partie.write_bytes(b"a")
    assert octets_gardes.lire(partie) == octets_gardes.lire(partie) == b"a"
    assert ouvertures.count("HPGOF") == 2, "le jeu sauvegarde peut-être encore : rien n'est gardé"


def test_un_gros_fichier_n_est_pas_garde(tmp_path, vieillir, ouvertures):
    gros = tmp_path / "gros.bin"
    gros.write_bytes(bytes(300 * 1024))
    vieillir(gros)
    octets_gardes.lire(gros)
    octets_gardes.lire(gros)
    assert ouvertures.count("gros.bin") == 2


def test_un_jeu_qui_demarre_reprend_tout(tmp_path, vieillir, ouvertures):
    partie = tmp_path / "auto.sav"
    partie.write_bytes(b"a")
    vieillir(partie)
    octets_gardes.lire(partie)
    octets_gardes.liberer()
    octets_gardes.lire(partie)
    assert ouvertures.count("auto.sav") == 2


def test_absent_leve_comme_une_lecture(tmp_path):
    with pytest.raises(OSError):
        octets_gardes.lire(tmp_path / "absent")


def test_les_pages_ne_relisent_pas_la_meme_sauvegarde(tmp_path, vieillir, ouvertures):
    """Le relevé du Carnet lit l'en-tête, le folio le contenu, puis chaque retour sur la page."""
    info = tmp_path / "GameSaveInfo0"
    info.write_bytes(bytes(16) + bytes([5]) + b"lev1\x00" + bytes(8))
    partie = tmp_path / "HPGOF"
    partie.write_bytes(bytes(64))
    vieillir(info, partie)
    for _ in range(4):
        folio.info_hp1(info)
        folio_hp4.releve(partie)
        sauvegardes._entete(partie)
    assert ouvertures.count("GameSaveInfo0") == 1
    assert ouvertures.count("HPGOF") == 2


def test_le_releve_des_sauvegardes_se_lit_une_fois(tmp_path, vieillir, monkeypatch):
    from src.core import json_garde
    chemin = tmp_path / "sauvegardes.json"
    chemin.write_text(json.dumps({"sauvegardes": [{"jeu": "hp1", "fichier": "Save0.usa", "parties": []}]}),
                      encoding="utf-8")
    vieillir(chemin)
    lus = []
    vrai = json_garde._decoder
    monkeypatch.setattr(json_garde, "_decoder", lambda c: lus.append(c) or vrai(c))
    json_garde._garde.cache_clear()
    premier = sauvegardes.charger(chemin)
    assert ("hp1", "Save0.usa") in premier
    assert sauvegardes.charger(chemin) == premier and len(lus) == 1
    premier[("hp1", "Save0.usa")]["parties"].append("x")       # l'appelant modifie SA copie
    assert sauvegardes.charger(chemin)[("hp1", "Save0.usa")]["parties"] == []
    json_garde._garde.cache_clear()
