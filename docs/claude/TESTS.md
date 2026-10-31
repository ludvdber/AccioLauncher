# Tests : le détail

Déplacé tel quel depuis `CLAUDE.md` le 2026-10-26 (le fichier, chargé à chaque séance, faisait 23 Ko). `CLAUDE.md` garde la règle courte ; ici vivent la mesure et le pourquoi.

## Compte et tests sautés

**Compte au dernier point (2026-10-31, Windows, Python 3.15.1, pytest-qt 4.5.0) : 4110 réussis, 34 sautés** (en 1 min avec `-n auto --dist loadfile`, pytest-xdist ; 6 min sans) (30 exigent Linux, 4 le droit de créer un lien symbolique sous Windows : `test_installer` ×2, `test_compat`, `.DirIcon`) (la CI exige 83 % et coupe un test à 60 s) (**3325 réussis + 38 sautés sous Linux**, portable Bazzite, Python 3.14.7, 2026-10-20 ; **3838 + 39** dans un conteneur Ubuntu 24.04, Python 3.15.2, utilisateur normal, 2026-10-29 : les 39 sont Windows seulement, et les 29 « Linux seulement » y passent tous). Les 30 tests Linux exigent le système (chemins POSIX du préfixe, chemins de l'hôte, liens symboliques, bit exécutable, sockets Unix, `/bin/sh`, 7-Zip Linux, objdump, script de désinstallation du launcher) : le job Linux de la CI les exécute. Les 6 de `tests/test_fonts.py` (Gelasio contre Georgia) se sautaient PARTOUT et ont été retirés le 2026-10-25. Un `s` n'est jamais un échec ; ce qui doit alerter, c'est leur NOMBRE qui grimpe. Tout nouveau module → au moins un test sentinelle.

## Tests de bout en bout

`tests/test_integration_smoke.py` (démarrage, clavier, pages, fermeture) et `test_fenetre_operations.py`, `test_fenetre_mise_en_page.py`, `test_fenetre_bandes_annonces.py`, `test_fenetre_engrenage.py` (découpés le 2026-10-14) pilotent une vraie MainWindow offscreen — c'est là qu'on teste le câblage bout-en-bout. Fixtures `make_window*` dans `conftest.py`. **`tests/test_parcours.py` suit un joueur d'un bout à l'autre** (archive locale → vrai extracteur → JOUER → vrai moniteur de processus → retour → désinstallation, plus la barre du bas pendant la préparation de Wine) sur un jeu FABRIQUÉ : seuls le réseau et le processus du jeu sont simulés. Son premier passage a trouvé la règle 134, invisible à tous les tests d'étape. `tests/test_downloader_stream.py` injecte un faux `httpx` dans `sys.modules`.

## Polices sous offscreen

`QFontDatabase.families()` y rend **zéro famille** (revérifié le 2026-10-25, Qt 6.11). Le piège était Georgia, police du système, que Qt remplaçait par Cinzel (+24 % de largeur, +6 à +12 % d'interligne selon la taille) : la suite mesurait une autre police que l'utilisateur. **Résolu depuis que les trois polices sont embarquées** (Gelasio pour le corps, `fonts.py`, gardé par `test_aucune_famille_ne_depend_du_systeme`) : offscreen mesure les vraies. Ne JAMAIS appeler une police par son nom système (règle 89), sinon le piège revient. Le rendu natif (DPI, lissage) reste propre à chaque plateforme, d'où **`tools/audit_geometrie.py`**, lancé par `build.bat` sur la plateforme native avec `WA_DontShowOnScreen` : 8 jeux × 4 états × 4 tailles × **3 scénarios** (`nominal`, `bandeau`, `charge`) × toutes les langues. Le scénario `bandeau` a été ajouté parce que l'outil écartait le bandeau d'alerte — exactement là où vivait un débordement de 20 px en espagnol.

## La machine par défaut est « prête à jouer »

Sous Linux aussi : `conftest._linux_pret_a_jouer` pose un lanceur FACTICE (chemin inexistant : un `Popen` oublié échoue franchement au lieu de lancer Wine) et un préfixe prêt, composants compris, dans un `_Launcher/` temporaire À PART (dans `tmp_path`, il se mêlait à ce que d'autres tests y listent). Sans elle, le runner (sans Wine) affichait « Wine introuvable » partout et un poste qui a Wine l'aurait lancé. **`sans_lanceur`** pour le cas contraire ; `lanceur_factice` rend le faux. Les tests Linux SIMULENT `sys.platform` et tournent aussi sous Windows.

## Le vrai Documents

**Aucun test n'écrit dans le vrai Documents** : `conftest._documents_hors_du_vrai_dossier` redirige `get_documents_dir` de `post_install` et `pre_launch`, sur le même dossier que la garde des sauvegardes. Les tests de lancement neutralisaient les étapes UNE PAR UNE, par leur nom : une étape ajoutée sans compléter la liste aurait écrit chez la personne qui lance la suite.
