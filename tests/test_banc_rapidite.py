"""Sentinelle du banc de rapidité (`tools/banc_rapidite.py`) : son rendu, sans lancer Qt.

Le banc lui-même ne tourne pas dans la suite (il lance le vrai démarrage dans
des processus à part, une minute au moins) ; ce qui doit tenir ici, c'est le
tableau qu'il rend à partir de ses mesures : une ligne par budget, la cible à
côté, l'avertissement du mode hors écran en tête.
"""

import importlib.util
from pathlib import Path

_CHEMIN = Path(__file__).resolve().parents[1] / "tools" / "banc_rapidite.py"


def _banc():
    spec = importlib.util.spec_from_file_location("banc_rapidite", _CHEMIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_FACTICE = {
    "meta": {"etiquette": "essai", "profil": "ludo", "mode": "hors-ecran", "date": "2026-11-13 12:00",
             "commit": "abc1234", "python": "3.15.2", "qt": "6.11.0"},
    "demarrage": {"froid": False, "tours": [{}, {}], "mediane_premier_paint_ms": 900.0,
                  "mediane_utilisable_ms": 950.0},
    "actions": [
        {"nom": "Changer de jeu → hp2", "categorie": "jeu", "reponse_ms": 30.0, "appel_ms": 12.0},
        {"nom": "Paramètres : Son et image", "categorie": "rubrique", "reponse_ms": 177.0, "appel_ms": 168.0},
        {"nom": "Ouvrir Carnet", "categorie": "clic", "reponse_ms": 80.0, "appel_ms": 70.0},
    ],
    "blocages": [{"etape": "Paramètres : Son et image", "duree_ms": 173.7,
                  "cause": "src/ui/settings_panel.py:302 _marges", "appel": "src/ui/settings_panel.py:257",
                  "pile": ["src/ui/settings_panel.py:302 _marges"]}],
    "animations": {"changement de jeu": {"images": 40, "ecart_p95_ms": 35.0, "ecart_max_ms": 60.0,
                                         "peinture_p95_ms": 2.0, "lentes_33ms": 3}},
    "memoire": {"pic_mo": 300.0, "repos_mo": 260.0, "mesure": "octets privés",
                "pages": [{"page": "Carnet", "avant_mo": 280.0, "pic_mo": 300.0, "ouverte_mo": 290.0,
                           "apres_mo": 285.0, "garde_mo": 5.0}]},
    "disque": {"fichiers": 3, "lectures": 5, "modules": 10, "octets_processus": 1e6,
               "relus": [{"fichier": "C:/a/config.json", "lectures": 3, "taille": 1900, "origine": "python",
                          "phases": ["démarrage"]}]},
    "processeur": [{"situation": "repos", "part_coeur_pct": 3.0, "duree_s": 10.0},
                   {"situation": "bande-annonce", "part_coeur_pct": 31.0, "duree_s": 10.0}],
}


def test_une_ligne_par_budget_avec_sa_cible():
    banc = _banc()
    lignes = banc.lignes_tableau(_FACTICE)
    budgets = [ligne["budget"] for ligne in lignes]
    assert budgets[0].startswith("Démarrage à chaud")
    assert lignes[0]["ok"] is True and lignes[0]["cible"] == "< 1000 ms"
    rapides = next(ligne for ligne in lignes if "changement de jeu, rubrique" in ligne["budget"])
    assert rapides["ok"] is False and "Son et image" in rapides["detail"]
    clics = next(ligne for ligne in lignes if "tout autre clic" in ligne["budget"])
    assert clics["ok"] is True
    assert any(ligne["budget"].startswith("Blocages") and ligne["ok"] is False for ligne in lignes)
    assert any(ligne["budget"] == "Images : changement de jeu" and ligne["ok"] is False for ligne in lignes)
    repos = next(ligne for ligne in lignes if ligne["budget"] == "Processeur : repos")
    assert repos["ok"] is True and "%" in repos["valeur"]
    assert all(ligne["cible"] for ligne in lignes), "chaque budget porte sa cible"


def test_le_markdown_dit_le_mode_hors_ecran_en_tete():
    banc = _banc()
    md = banc.rendre_markdown(_FACTICE)
    assert md.index("HORS ÉCRAN") < md.index("| Budget |")
    assert "| Paramètres : Son et image | rubrique | 177.0 ms | < 50 |" in md
    assert "settings_panel.py:302 _marges" in md
    assert "config.json" in md
    vraie = dict(_FACTICE, meta=dict(_FACTICE["meta"], mode="vraie-fenetre"))
    assert "HORS ÉCRAN" not in banc.rendre_markdown(vraie)


def test_statistiques_des_images():
    banc = _banc()
    st = banc.stats_images([[0.0, 0.002], [0.033, 0.034], [0.100, 0.101]])
    assert st["images"] == 3
    assert abs(st["ecart_max_ms"] - 67.0) < 1e-6
    assert st["lentes_33ms"] == 1
