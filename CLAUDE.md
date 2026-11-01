# CLAUDE.md

Guide de travail pour Claude Code sur ce dépôt. **Toute règle ici a été payée une fois** : elle porte sa mesure, pas son récit. Ce fichier ne garde que ce dont presque toute tâche a besoin ; le détail est dans les fichiers du tableau.

## Project Overview

Launcher PyQt6 pour 8 jeux Harry Potter PC (Windows 10/11). **Interface et commentaires en français.**

- **Python 3.15 seul**, mais le code reste LISIBLE par la 3.14 (`fuzz.yml` et `security.yml` y restent) : pas de syntaxe `lazy import`. Les imports paresseux passent par `ui/imports_paresseux.activer()`.
- **Linux est un objectif déclaré** : tout appel win32 derrière `sys.platform == "win32"` avec un repli sensé ; jamais de lettre de lecteur hors code gardé. Le registre passe par `game_registry.disponible()` (Wine a le sien). [docs/LINUX.md](docs/LINUX.md) fait foi.

## Commands

```bash
pip install -r requirements.txt && python main.py     # lancer depuis les sources
python -m pytest -n auto --dist loadfile              # toute la suite, ~1 min (6 min sans -n)
python -m pytest tests/test_config.py::TestConfig::test_defaults
python -m ruff check .                                # jeu de règles FIGÉ dans pyproject.toml
python -m mypy                                        # src/core en strict, réglé dans pyproject.toml
pip install -r requirements-dev.txt && build.bat      # → dist/AccioLauncher.exe
./build.sh                                            # Linux → dist/AccioLauncher-x86_64.AppImage
```

`build.bat` et `build.sh` enchaînent lint → tests → géométrie → PyInstaller et **s'ARRÊTENT au premier échec**.

## Où lire le détail (À LIRE AVANT DE TOUCHER AU SUJET)

| Avant de toucher à… | Lire |
|---|---|
| un module de `src/core/` (rôle, pièges, mesures) | [docs/claude/ARCHITECTURE_CORE.md](docs/claude/ARCHITECTURE_CORE.md) — chercher le nom du module |
| un module de `src/ui/` | [docs/claude/ARCHITECTURE_UI.md](docs/claude/ARCHITECTURE_UI.md) — chercher le nom du module |
| Python 3.15, build, journal, sortie `os._exit`, CI, release, AppImage ; les découpes de modules | [docs/claude/ARCHITECTURE.md](docs/claude/ARCHITECTURE.md) |
| `games.json` (champs, blocs, validation), HP7 `pc`, HP1-HP3 (UE1), logo/icône | [docs/claude/CATALOGUE_ET_JEUX.md](docs/claude/CATALOGUE_ET_JEUX.md) |
| les tests (compte, tests de fenêtre, polices offscreen, `audit_geometrie`, conftest) | [docs/claude/TESTS.md](docs/claude/TESTS.md) |
| ruff, `requires-python`, l'arborescence utilisateur, les versions, Ko-fi | [docs/claude/CONVENTIONS.md](docs/claude/CONVENTIONS.md) |
| tout sujet de l'index des règles ci-dessous | [docs/claude/REGLES.md](docs/claude/REGLES.md) |
| Linux / Wine | [docs/LINUX.md](docs/LINUX.md) |
| une release (essai en jeu, HP1-HP6, avec le « oui » de Ludo) | [docs/AVANT_RELEASE.md](docs/AVANT_RELEASE.md) |

Un module absent d'ARCHITECTURE_CORE.md ou d'ARCHITECTURE_UI.md n'est pas documenté : l'y ajouter en le créant.

**Ce qui casse un jeu sans bruit** (détail dans CATALOGUE_ET_JEUX.md) : ne jamais retirer `Running.ini` du catalogue (hp1/hp2) ; ne jamais passer `StartupFullscreen=True` ; HP7 ne démarre que dans un sous-dossier `pc` ; un `.int` sans sa DLL casse HP1/HP2 ; HP3 jamais au-delà de 60 images/s ; `requires_file` et les valeurs `Locale` diffèrent entre HP7 parties 1 et 2.

## Testing

- `pytest-qt>=4.5` ; `qtbot` est la façon standard de tester un widget. `tests/conftest.py` force `QT_QPA_PLATFORM=offscreen`. La logique pure (tout `src/core/` sauf les QThread) se teste sans fixture Qt.
- **Compte au dernier point (2026-11-02, Windows, Python 3.15.2, 553e130) : 4193 réussis, 34 sautés** (30 tests Linux qui exigent le système, 4 qui exigent le droit de créer un lien symbolique sous Windows). Un `s` n'est jamais un échec ; ce qui doit alerter, c'est leur NOMBRE qui grimpe. **Dans le Bash de Claude, `python` est la 3.14** : lancer `py -3.15 -m pytest`.- Tout nouveau module → au moins un test sentinelle. Le câblage de bout en bout se teste sur une vraie MainWindow (`make_window*`, `test_fenetre_*.py`, `test_parcours.py`).
- Ne JAMAIS appeler une police par son nom système (règle 89) : offscreen mesurerait une autre police.
- Aucun test n'écrit dans le vrai Documents (`conftest._documents_hors_du_vrai_dossier`).
- **Piège env** : si pytest-qt n'est pas dans le Python actif, les tests widgets sont sautés en silence et le compte chute (~110). Vérifier `python -m pip show pytest-qt`.

## Key Conventions

- Syntaxe 3.14 : `str | Path`, génériques `def f[T: Base]`, aucun `from __future__ import annotations` ; `pathlib.Path` partout. Toute sortie de programme lue en texte nomme son encodage.
- **mypy strict sur TOUT `src/core`**, sans liste d'exception : tout module neuf naît strict. Pas de `assert` pour rassurer mypy : un vrai test ou un `TypeGuard`.
- `QThread` : `progress` / `error` + **un signal de fin NOMMÉ** (`download_finished`, `install_finished`, `result`), jamais `finished`. Déconnecter symétriquement (try/except `TypeError`) avant de mettre à None.
- Annuler un `QThread` : `cancel()` puis `wait(3000)` ; au timeout, le garer dans `GameOperations._zombies`. **Jamais un nouveau téléchargement sur un `.part` qu'un vieux thread tient encore.**
- Tous les callbacks qui mutent l'état vivent sur l'orchestrateur ; les widgets sont des consommateurs bêtes.
- Un slot qui parle à un `QDialog` après sa fermeture possible vérifie sa vivacité (patron `_force_update_check`).
- `~/Games/AccioLauncher/` ne contient QUE les jeux ; tout le reste dans `_Launcher/` (chemin fixe), sauf le cache qui suit `install_path` (`cache_pour()`).
- Le numéro de version vit à TROIS endroits (`pyproject.toml`, `config.APP_VERSION`, badge README) ; `pyproject.toml` fait foi pour les dépendances ; le jeu de règles ruff est figé.
- Thème : tout stylesheet avec un hex or ou une surface bleu nuit passe par `theme.themed(...)` ; dans un paintEvent, `accent_qcolor(alpha)` et `bg_qcolor(alpha)`.
- Ko-fi : exactement UN remerciement dans la vie du launcher, à la première mise à jour installée. Jamais lié aux heures de jeu.
- Hero : la vue ouvre via `carousel.select(idx)`, jamais `set_game` directement pour un index ≠ 0.
- Nav clavier : ←/→ routés par `MainWindow._handle_global_key` ; pas de `keyPressEvent` aux widgets pour ça.

## Index des règles à ne pas réintroduire

135 règles, numérotées et classées dans [docs/claude/REGLES.md](docs/claude/REGLES.md), chacune avec sa mesure. **Ouvrir la règle avant de toucher au sujet qu'elle nomme.** Catégories : processus, threads, sortie · Qt : peinture, focus, widgets · mise en page et mesure · texte, i18n, contenu distant · catalogue, registre, sécurité · fichiers, encodage, build · orchestration et états · ce que l'interface a le droit de dire · produit : ce qui a été tranché · Linux et AppImage · pièges de test récurrents.
