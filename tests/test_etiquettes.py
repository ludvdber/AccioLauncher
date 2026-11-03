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


def test_une_issue_modifiee_perd_l_etiquette_de_l_ancien_jeu():
    """Elle gardait les deux étiquettes de jeu (audit du 2026-11-02)."""
    texte = (RACINE / ".github" / "workflows" / "etiquettes.yml").read_text(encoding="utf-8")
    assert "edited" in texte and "--remove-label" in texte


def test_les_etiquettes_sont_valides_pour_github():
    noms = [e["nom"] for e in ETIQUETTES]
    assert len(noms) == len(set(noms))
    for e in ETIQUETTES:
        assert re.fullmatch(r"[0-9a-f]{6}", e["couleur"]), e["nom"]
        assert len(e["nom"]) <= 50 and len(e["description"]) <= 100, e["nom"]


def test_le_modele_de_bug_nomme_le_vrai_bouton_du_rapport():
    """Il demandait « Copier les informations de diagnostic », un bouton qui
    n'existe pas : les issues arrivaient sans rapport (Ludo, 2026-11-03)."""
    modele = (RACINE / ".github" / "ISSUE_TEMPLATE" / "bug.yml").read_text(encoding="utf-8")
    anglais = json.loads((RACINE / "src" / "data" / "i18n" / "en.json").read_text(encoding="utf-8"))["strings"]
    assert "Copier le rapport" in modele and anglais["Copier le rapport"] in modele
    assert "accio_launcher.log" in modele and "Accio Launcher - rapport.txt" in modele
