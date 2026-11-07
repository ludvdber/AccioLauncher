"""`.github/tableau_publie.py` et son workflow : les cartes « Prêt » de la prochaine mise à jour passent en
« Publié » à la release du launcher, et rien d'autre."""
import importlib.util
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("tableau_publie", RACINE / ".github" / "tableau_publie.py")
assert _spec is not None and _spec.loader is not None
tp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tp)


def _carte(titre, statut, version):
    valeurs = [{"name": statut, "field": {"name": "Status"}}, {"name": version, "field": {"name": "Version"}}, {}]
    return {"id": titre, "content": {"title": titre}, "fieldValues": {"nodes": valeurs}}


def test_seules_les_cartes_pretes_de_la_prochaine_mise_a_jour():
    items = [_carte("a", "Prêt", tp.PROCHAINE), _carte("b", "Test en jeu", tp.PROCHAINE),
             _carte("c", "Prêt", "1.4 Difficulté · Difficulty"), _carte("d", "Publié", tp.PROCHAINE)]
    assert [i["id"] for i in tp.cartes_a_publier(items)] == ["a"]


def test_sans_jeton_rien_ne_se_fait_et_le_run_reussit(monkeypatch, capsys):
    monkeypatch.delenv("PROJET_TOKEN", raising=False)
    monkeypatch.setenv("VERSION", "1.3.4")
    monkeypatch.setattr(tp, "gql", lambda *_a, **_k: pytest.fail("aucun appel sans jeton"))
    assert tp.main() == 0
    assert "PROJET_TOKEN absent" in capsys.readouterr().out


def test_le_workflow_ne_donne_aucun_droit_au_depot_et_epingle_ses_actions():
    texte = (RACINE / ".github" / "workflows" / "tableau.yml").read_text(encoding="utf-8")
    assert "permissions: {}" in texte and "contents: read" in texte and "write" not in texte
    assert "secrets.PROJET_TOKEN" in texte
    for ligne in texte.splitlines():
        if "uses:" in ligne:
            assert "@" in ligne and len(ligne.split("@")[1].split()[0]) == 40, ligne


def _champs(avec_etape=True):
    noeuds = [{"id": "S", "name": "Status", "options": [{"id": "P", "name": tp.PUBLIE}]}]
    if avec_etape:
        noeuds.append({"id": "E", "name": tp.ETAPE})
    return {"user": {"projectV2": {"id": "PR", "fields": {"nodes": noeuds}}}}


def test_toutes_les_pages_sont_lues(monkeypatch, capsys):
    """Revue du 2026-11-07 : au-delà de 100 cartes, les suivantes étaient ignorées sans un mot."""
    pages = [{"node": {"items": {"pageInfo": {"hasNextPage": True, "endCursor": "c1"},
                                 "nodes": [_carte("a", "Prêt", tp.PROCHAINE)]}}},
             {"node": {"items": {"pageInfo": {"hasNextPage": False, "endCursor": None},
                                 "nodes": [_carte("b", "Prêt", tp.PROCHAINE)]}}}]
    appels = []

    def faux(_jeton, requete, **v):
        appels.append(v)
        if "fields(first" in requete:
            return _champs()
        if "mutation" in requete:
            return {}
        return pages[0 if v.get("a") is None else 1]

    monkeypatch.setenv("PROJET_TOKEN", "x")
    monkeypatch.setenv("VERSION", "1.3.4")
    monkeypatch.setattr(tp, "gql", faux)
    assert tp.main() == 0
    assert "2 carte(s)" in capsys.readouterr().out
    assert any(v.get("a") == "c1" for v in appels)


def test_champ_d_etape_absent_rien_n_est_ecrit(monkeypatch):
    def faux(_jeton, requete, **_v):
        if "mutation" in requete:
            pytest.fail("aucune écriture sans le champ d'étape")
        return _champs(avec_etape=False)

    monkeypatch.setenv("PROJET_TOKEN", "x")
    monkeypatch.setenv("VERSION", "1.3.4")
    monkeypatch.setattr(tp, "gql", faux)
    assert tp.main() == 1
