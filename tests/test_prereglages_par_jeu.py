"""Ce que chaque préréglage de la 1.4 écrit, jeu par jeu, comparé à la table tranchée (atelier,
`notes/DIFFICULTE_1.4.md` § 2 et § 8 bis ; demande de Ludo du 2026-11-19).

Chaque jeu est installé pour de vrai dans un dossier de test, avec la section `[Accio.Hardcore]` et les clés
de la une seule vie de son ini livré (correctif, `data/<jeu>/`), et le catalogue EMBARQUÉ : un réglage que le
catalogue oublierait de déclarer manquerait ici. Puis chaque préréglage est choisi comme le fait l'onglet
Difficulté (`difficulte_presets.appliquer`), et l'ini relu clé par clé.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core import difficulte_presets as dp
from src.core import reglages_correctif as rc
from src.core import une_vie
from src.core.game_data import load_catalog

# Les clés de [Accio.Hardcore] que livre l'ini de chaque jeu (correctif, data/<jeu>/, 2026-11-18).
_LIVREES = {
    "hp1": ("DamageTaken", "DamageDealt"),
    "hp2": ("DamageTaken", "DamageDealt"),
    "hp3": ("DamageTaken", "DamageDealt"),
    "hp4": ("DamageTaken", "DamageDealt", "EnemyHits", "EnemyRecovery"),
    "hp5": ("DamageTaken", "DamageDealt", "PlayerHealth", "Invincible"),
    "hp6": ("DamageTaken", "DamageDealt", "EnemyReaction", "RemovedSpells", "PlayerHealth", "PlayerRegen",
            "Invincible"),
}
_NOM_INI = {"hp1": "winmm.ini", "hp2": "winmm.ini", "hp3": "dinput8.ini"}

# LA TABLE (Ludo, 2026-11-19) : la section [Accio.Hardcore] entière après le préréglage. HP4 et HP1-HP3
# n'ont pas `Invincible` : pas de Récit. HP5 n'a pas de régénération (C7). HP6 porte ses clés du correctif
# tant que Lua n'est pas livré (`difficulte_lua`) ; vie et régénération n'y sont pas déclarées.
_UE = {"detendu": {"DamageTaken": 0.5, "DamageDealt": 1.5},
       "normal": {"DamageTaken": 1, "DamageDealt": 1},
       "difficile": {"DamageTaken": 1.5, "DamageDealt": 0.75},
       "hardcore": {"DamageTaken": 3, "DamageDealt": 0.5}}
TABLE: dict[str, dict[str, dict[str, float]]] = {
    "hp1": _UE, "hp2": _UE, "hp3": _UE,
    "hp4": {
        "detendu": {"DamageTaken": 0.5, "DamageDealt": 1.5, "EnemyHits": 0.6, "EnemyRecovery": 1.5},
        "normal": {"DamageTaken": 1, "DamageDealt": 1, "EnemyHits": 1, "EnemyRecovery": 1},
        "difficile": {"DamageTaken": 1.5, "DamageDealt": 0.75, "EnemyHits": 1.5, "EnemyRecovery": 0.7},
        "hardcore": {"DamageTaken": 3, "DamageDealt": 0.5, "EnemyHits": 2, "EnemyRecovery": 0.5},
    },
    "hp5": {
        "recit": {"DamageTaken": 1, "DamageDealt": 1.5, "PlayerHealth": 1, "Invincible": 1},
        "detendu": {"DamageTaken": 0.5, "DamageDealt": 1.5, "PlayerHealth": 1.5, "Invincible": 0},
        "normal": {"DamageTaken": 1, "DamageDealt": 1, "PlayerHealth": 1, "Invincible": 0},
        "difficile": {"DamageTaken": 1.5, "DamageDealt": 0.75, "PlayerHealth": 1, "Invincible": 0},
        "hardcore": {"DamageTaken": 3, "DamageDealt": 0.5, "PlayerHealth": 1, "Invincible": 0},
    },
    "hp6": {
        "detendu": {"DamageTaken": 0.5, "DamageDealt": 1.5, "EnemyReaction": 1},
        "normal": {"DamageTaken": 1, "DamageDealt": 1, "EnemyReaction": 1},
        "difficile": {"DamageTaken": 1.5, "DamageDealt": 0.75, "EnemyReaction": 1.5},
        "hardcore": {"DamageTaken": 3, "DamageDealt": 0.5, "EnemyReaction": 5},
    },
}
# Le Quidditch de HP1 et HP2 (`QuidditchDifficulty`, [Accio.Game]) et la difficulté propre de HP2 (User.ini).
QUIDDITCH = {"recit": 0, "detendu": 0, "normal": 0, "difficile": 1, "hardcore": 2}
# Ludo 2026-11-19 : là où DamageTaken s'applique, la difficulté propre de HP2 reste Facile (les deux se multipliaient).
NATIVE_HP2 = {"detendu": "DifficultyEasy", "normal": "DifficultyEasy", "difficile": "DifficultyEasy",
              "hardcore": "DifficultyEasy"}
# Une seule vie : Réaliste = Normal, Impardonnable = Hardcore, plus les trois clés du mode.
UNE_VIE = {"realiste": "normal", "impardonnable": "hardcore"}
ONE_LIFE = {"hp1": "1", "hp2": "1", "hp3": "1", "hp4": "1", "hp5": "2", "hp6": "1"}
JEUX = tuple(TABLE)


def _ini_livre(jeu: str) -> str:
    """Ce que porte l'ini livré pour ce qui nous regarde, aux valeurs livrées (le jeu tel qu'il est sorti)."""
    lignes = ["; Accio Launcher - PC fix", "[Accio.Window]", "WindowStyle=1", "",
              "[Accio.Game]", "OneLife=0", "DeathCounter=0", "OneLifeSaves="]
    if jeu in ("hp1", "hp2"):
        lignes.append("QuidditchDifficulty=0")
    lignes += ["", "[Accio.Hardcore]"]
    lignes += [f"{cle}=" if cle == "RemovedSpells" else f"{cle}={0 if cle == 'Invincible' else 1}"
               for cle in _LIVREES[jeu]]
    return "\r\n".join(lignes) + "\r\n"


@pytest.fixture
def installe(tmp_path):
    """(jeu, config, ini) : le jeu du catalogue embarqué installé sous tmp_path, son ini livré posé."""
    jeux = {g.id: g for g in load_catalog().games}

    def poser(jeu: str):
        game = jeux[jeu]
        racine = tmp_path / "Games"
        dossier = racine / Path(game.executable).parent
        dossier.mkdir(parents=True, exist_ok=True)
        ini = dossier / _NOM_INI.get(jeu, "d3d9.ini")
        ini.write_bytes(_ini_livre(jeu).encode("ascii"))
        if jeu == "hp2":
            user = tmp_path / "Documents" / "Harry Potter II" / "User.ini"
            user.parent.mkdir(parents=True, exist_ok=True)
            user.write_text("[Engine.PlayerPawn]\r\nDifficulty=DifficultyEasy\r\n", encoding="ascii")
        config = SimpleNamespace(install_path=racine)
        assert rc.ini_du_correctif(dossier) == ini
        return game, config, ini
    return poser


def _section(ini: Path, section: str) -> dict[str, str]:
    lignes, _ = rc._lire(ini)
    bornes = rc._bornes(lignes, section)
    assert bornes is not None, section
    debut, fin = bornes
    paires = (ligne.split("=", 1) for ligne in lignes[debut:fin] if "=" in ligne and not ligne.startswith(";"))
    return {cle.strip(): valeur.strip() for cle, valeur in paires}


def _cas():
    for jeu in JEUX:
        for preset in dp.PRESETS:
            base = UNE_VIE.get(preset.ident, preset.ident)
            if base in TABLE[jeu]:
                yield jeu, preset.ident


@pytest.mark.parametrize(("jeu", "ident"), list(_cas()))
def test_chaque_prereglage_ecrit_la_table(installe, tmp_path, jeu, ident):
    game, config, ini = installe(jeu)
    idents = dp.idents_du_jeu(game, ini)
    preset = dp.PAR_IDENT[ident]
    assert preset in dp.proposes(game, config, idents), f"{ident} doit être proposé dans {jeu}"
    assert dp.appliquer(preset, game, config, ini, idents) == [], "tout doit s'écrire"

    base = UNE_VIE.get(ident, ident)
    ecrit = _section(ini, "Accio.Hardcore")
    attendu = {cle: 1.0 for cle in _LIVREES[jeu] if cle != "RemovedSpells"}
    attendu.update({cle: 0.0 for cle in _LIVREES[jeu] if cle == "Invincible"})
    attendu.update(TABLE[jeu][base])
    assert {c: float(v) for c, v in ecrit.items() if c != "RemovedSpells"} == attendu, (jeu, ident)
    assert ecrit.get("RemovedSpells", "") == "", "aucun préréglage ne retire de sort"
    assert "PlayerRegen" not in ecrit or jeu == "hp6", "pas de régénération hors HP6 (C7)"

    jeu_ = _section(ini, "Accio.Game")
    if jeu in ("hp1", "hp2"):
        assert jeu_["QuidditchDifficulty"] == str(QUIDDITCH[base])
    if jeu == "hp2":
        user = (tmp_path / "Documents" / "Harry Potter II" / "User.ini").read_text(encoding="ascii")
        assert f"Difficulty={NATIVE_HP2[base]}" in user
    if ident in UNE_VIE:
        assert jeu_["OneLife"] == ONE_LIFE[jeu]
        assert jeu_["DeathCounter"] == "1"
        assert une_vie.NOM in jeu_["OneLifeSaves"]
    else:
        assert (jeu_["OneLife"], jeu_["DeathCounter"], jeu_["OneLifeSaves"]) == ("0", "0", "")
    # Et la page le relit comme le préréglage choisi.
    assert dp.courant(dp.lire(game, config, ini, idents), idents, dp.une_vie_active(game, config)) == ident


@pytest.mark.parametrize("jeu", JEUX)
def test_les_six_prereglages_ou_cinq_sans_recit(installe, jeu):
    """Récit là où Harry peut être invincible (HP5) ; ailleurs les cinq autres et Normal."""
    game, config, ini = installe(jeu)
    proposes = [p.ident for p in dp.proposes(game, config, dp.idents_du_jeu(game, ini))]
    autres = ["detendu", "normal", "difficile", "hardcore", "realiste", "impardonnable"]
    assert proposes == (["recit", *autres] if jeu == "hp5" else autres)


@pytest.mark.parametrize("jeu", JEUX)
def test_revenir_a_normal_rend_tout(installe, jeu):
    game, config, ini = installe(jeu)
    idents = dp.idents_du_jeu(game, ini)
    livre = ini.read_bytes()
    assert dp.appliquer(dp.PAR_IDENT["impardonnable"], game, config, ini, idents) == []
    assert dp.appliquer(dp.PAR_IDENT["normal"], game, config, ini, idents) == []
    assert ini.read_bytes() == livre, "Normal rend l'ini livré à l'octet"


def test_la_table_suit_les_valeurs_du_preset_py():
    """C2 : « celle du preset py ». Si un jour l'un change sans l'autre, ce test le dit."""
    cles = {"DamageTaken": "degats_recus", "DamageDealt": "degats_infliges", "EnemyHits": "sorts_par_creature",
            "EnemyRecovery": "jauge_creature", "PlayerHealth": "vie_joueur", "EnemyReaction": "reaction_ennemis",
            "Invincible": "invincible"}
    for jeu, presets in TABLE.items():
        for ident, valeurs in presets.items():
            for cle, valeur in valeurs.items():
                assert float(dp.PAR_IDENT[ident].valeurs[cles[cle]]) == valeur, (jeu, ident, cle)
