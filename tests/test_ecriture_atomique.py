"""L'écriture atomique commune à la config, aux stats, aux succès, aux sauvegardes et à la discographie."""

import pytest

from src.core import ecriture_atomique as ea


def test_remplace_le_fichier_et_ne_laisse_rien(tmp_path):
    cible = tmp_path / "config.json"
    cible.write_text("ancien", encoding="utf-8")
    ea.ecrire_atomique(cible, '{"langue": "français"}')
    assert cible.read_text(encoding="utf-8") == '{"langue": "français"}'
    assert [p.name for p in tmp_path.iterdir()] == ["config.json"]


def test_un_echec_garde_l_ancien_et_efface_le_temporaire(tmp_path, monkeypatch):
    cible = tmp_path / "stats.json"
    cible.write_text("ancien", encoding="utf-8")

    def refuse(_src, _dst):
        raise PermissionError("fichier verrouillé")
    monkeypatch.setattr(ea.os, "replace", refuse)
    with pytest.raises(PermissionError):
        ea.ecrire_atomique(cible, "neuf")
    assert cible.read_text(encoding="utf-8") == "ancien"
    assert [p.name for p in tmp_path.iterdir()] == ["stats.json"]


def test_une_interruption_ne_laisse_pas_de_temporaire(tmp_path, monkeypatch):
    """Ctrl+C ou fermeture forcée en pleine écriture : les anciennes copies ne
    nettoyaient que sur `OSError`."""
    def coupe(_src, _dst):
        raise KeyboardInterrupt
    monkeypatch.setattr(ea.os, "replace", coupe)
    with pytest.raises(KeyboardInterrupt):
        ea.ecrire_atomique(tmp_path / "succes.json", "neuf", ".accio-tmp")
    assert list(tmp_path.iterdir()) == []
