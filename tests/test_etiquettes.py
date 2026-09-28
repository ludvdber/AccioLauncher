"""Les étiquettes de jeu des issues : les réponses des formulaires et `etiquettes.json` doivent concorder.

Le workflow « étiquettes » compare la réponse « Jeu concerné » MOT POUR MOT : un
titre retouché d'un seul côté ferait cesser l'étiquetage sans rien signaler.
"""
import json
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
ETIQUETTES = json.loads((RACINE / ".github" / "etiquettes.json").read_text(encoding="utf-8"))["etiquettes"]


def _options_jeu(modele: str) -> list[str]:
    texte = (RACINE / ".github" / "ISSUE_TEMPLATE" / modele).read_text(encoding="utf-8")
    bloc = texte.split("id: jeu", 1)[1].split("- type:", 1)[0]
    return re.findall(r"^\s+- (.+)$", bloc.split("options:", 1)[1], re.MULTILINE)


def test_chaque_reponse_du_formulaire_a_son_etiquette():
    jeux = {e["jeu"] for e in ETIQUETTES if "jeu" in e}
    for modele in ("bug.yml", "idee.yml"):
        options = _options_jeu(modele)
        assert len(options) == 9, modele
        assert set(options) == jeux, modele


def test_les_etiquettes_sont_valides_pour_github():
    noms = [e["nom"] for e in ETIQUETTES]
    assert len(noms) == len(set(noms))
    for e in ETIQUETTES:
        assert re.fullmatch(r"[0-9a-f]{6}", e["couleur"]), e["nom"]
        assert len(e["nom"]) <= 50 and len(e["description"]) <= 100, e["nom"]
