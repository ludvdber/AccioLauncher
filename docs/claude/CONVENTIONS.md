# Conventions : le détail

Déplacé tel quel depuis `CLAUDE.md` le 2026-10-26 (le fichier, chargé à chaque séance, faisait 23 Ko). `CLAUDE.md` garde la règle en une ligne ; ici vivent la mesure et le pourquoi.

## Syntaxe et typage

- Syntaxe lisible par la 3.14 (voir l'exception du fuzzing), exécutée en 3.15 : `str | Path`, génériques `def f[T: Base]`, f-strings, aucun `from __future__ import annotations` (3.14 diffère les annotations) ; `pathlib.Path` partout. Toute sortie de programme lue en texte nomme son encodage (`tests/test_encodages_explicites.py`).
- **mypy (2026-10-16)** : TOUT `src/core` est vérifié en **strict** par `build.bat`, `build.sh` et la CI ; la liste d'exception `[tool.mypy.overrides]` a été vidée puis retirée : ne pas la recréer, tout module neuf naît strict. Typer aussi ce qu'on touche dans `src/ui` quand c'est simple. Pas de `assert` pour rassurer mypy (retiré par `-O`, signalé par Bandit) : un vrai test (`if x is None: return`) ou un `TypeGuard`. Le typage ne coûte rien à l'exécution.

## Dépendances et ruff

- `pyproject.toml` fait foi pour les dépendances. **`requires-python = ">=3.15"`** : une borne plus basse que ce que la CI teste laisse pip installer le paquet là où il plante (le `>=3.10` d'origine plantait à l'import sur `enum.StrEnum`, 3.11).
- **Le jeu de règles ruff est figé** (`select = ["E4","E7","E9","F","W","UP","B"]`). Sans cette section, « le projet est propre » dépendait du défaut de la version installée : 0.15 → 0.16 a fait apparaître 119 signalements sans qu'une ligne change. **`UP` et `B` adoptés le 2026-10-25** avec Python 3.14 seul (f-strings, génériques PEP 695, `zip(strict=)` explicite) ; plus de `from __future__ import annotations` (3.14 diffère les annotations). `I` écarté (158 déplacements pour rien) ; `SIM`/`C4`/`RET`/`PTH` restent des candidates, à relire au cas par cas : `os.path.abspath` n'est pas `Path.resolve()` (lecteurs réseau, `subst`), et `Path.copy()` recopie l'attribut lecture seule sous Windows, contrairement à `shutil.copyfile`.

## Arborescence utilisateur

`~/Games/AccioLauncher/` ne contient QUE les dossiers de jeux ; tout le reste vit dans `_Launcher/` (`config.json`, `catalog_cache.json`, `sessions.json`, `i18n/`, `trailers/`, `logs/`, `cache/`). Quelqu'un qui ouvre ce dossier veut y voir ses JEUX, et une plomberie visible invite à être supprimée au hasard. **Deux régimes délibérés** : les données du launcher sont à un chemin FIXE (`LAUNCHER_DATA_PATH`) — déplacer ses jeux ne doit pas rendre les journaux introuvables — tandis que le **cache suit `install_path`** (`cache_pour()`), parce qu'une archive de 7 Go doit atterrir sur le même volume que son extraction, sans quoi le rangement devient une copie et la vérification d'espace ment. `migrer_arborescence()` est appelée **avant le logging** (un `RotatingFileHandler` tiendrait le fichier ouvert) **et avant `Config.exists()`** (sinon l'assistant rouvrirait chez quelqu'un qui a huit jeux). Idempotente, n'écrase jamais une destination existante.

## Versions

Versions : `0.0.x` bugfix · `0.x.0` jeu ajouté · `x.0.0` tous les jeux livrés. Le numéro vit à TROIS endroits — `pyproject.toml`, `config.APP_VERSION`, badge README — accord tenu par `tests/test_config.py`. `release.yml` DÉDUIT le tag d'`APP_VERSION` (aucun tag saisi à la main) et refuse une version qui a déjà sa release ou son tag, ou un lancement hors de `main`.

## Ko-fi sans nag

Exactement UN remerciement dans la vie du launcher (`kofi_milestone_thanked`), **à la première mise à jour du launcher installée** (`Config.version_lancee` qui monte ; vide = config d'avant la 1.1.6, donc aussi une mise à jour ; une config neuve porte la version courante). Plus aux heures de jeu (ACT-072, 2026-10-09) : un merci qui dépend du temps passé dans les jeux d'EA et de Warner relie l'argent à leur consommation. Il cède la place au toast des mises à jour de jeux et attend le retour de partie suivant. **La règle « une seule fois » ne bouge pas.**
