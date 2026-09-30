# Retour : essais Linux sur Bazzite (2026-09-30, 12 h – 12 h 45)

Pour : Ludo et la session Windows. Exécution de `docs/linux/MISSION_BAZZITE.md`, interrompue à la
demande de Ludo avant les tâches C, D et F. Rien n'est commité.

Machine : Bazzite, noyau 7.0.9, KDE Wayland, i3-1220P / Intel UHD, umu-launcher 1.4.0,
GE-Proton10-34, Python 3.14.5 (venv `.venv` dans le dépôt), launcher lancé depuis les sources.

## En bref

| Sujet | État |
|---|---|
| A. HP1 « Initializing Direct3D failed » | **Corrigé et vérifié** : il manquait `d3dx11_43` + `d3dcompiler_43` natifs. Le launcher les détecte, les installe par la barre de préparation, HP1 atteint son menu. |
| B. Plus d'une minute avant le jeu | **Cause trouvée et corrigée** : umu retéléchargeait son runtime (195 Mo) avant chaque partie. 17 s → 5,5 s du clic au processus. |
| **Nouveau : plus aucune installation possible une fois Wine préparé** | **Corrigé et vérifié** (HP2 installé ensuite). Défaut bloquant, invisible jusqu'ici. |
| E. `/var~` dans le diagnostic | **Corrigé** (+ le `SavePath` de HP1 qui partait en `Z:\var\home\…`). |
| Retours 1, 2, 3, 7 (corrections de c321e5b) | Vérifiés, voir plus bas. Le sens 2 du retour 3 n'est pas prouvé. |
| C. HP6 figé sur la cinématique | **Non fait.** |
| D. Fenêtre impossible à agrandir | **Non fait** (voir « Ce qui reste »). |
| F. HP3-HP5, HP7a/b, manette | **Non fait.** |

## Tests

- `python -m pytest` : **2220 réussis, 33 sautés** sous Linux (au départ : 2184 / 33). Les 33 sautés sont des
  tests « Windows uniquement » (`.bat`, chemins Windows, `tasklist`, constantes `CREATE_*`, page ANSI Windows)
  et 6 cas `test_fonts.py` (Georgia absente). **Tous les tests réservés à Linux tournent et passent** sur un
  vrai Linux avec Wine.
- `python -m ruff check .` : propre.
- Pas vérifié sous Windows. À surveiller en CI : HP1 et HP2 exigent maintenant `d3dx11_43.dll` et
  `d3dcompiler_43.dll` dans SysWOW64 ; si le runner Windows ne les a pas, un test qui suppose le bandeau
  caché sur HP1/HP2 réel passerait au rouge (aucun vu sous Linux, mais la machine « prête à jouer » de
  `conftest` ne couvre que Linux).

## A. Prérequis de HP1 et HP2

### Preuve

`HP.log` de HP1 (dans `Documents/Harry Potter` du préfixe, pas dans `HP1/System`) avant correction :

```
Log: Initializing Direct3D 11 renderer.
Log: polyflags.fxh:8:1: W4300: Redefinition of PF_Invisible.
Log: Error compiling effects file. Please make sure it resides in the "\system\d3d11drv" directory.
Critical: Init: Initializing Direct3D failed.
```

Essais sur des **copies** du préfixe (le vrai est resté intact pour l'essai par le launcher), un verbe à la fois :

| Préfixe | Résultat |
|---|---|
| tel quel (`vcrun2022`) | « Error compiling effects file » |
| `+ d3dcompiler_43` seul | « Error compiling effects file » |
| `+ d3dx11_43` seul | « Error compiling effects file » |
| `+ d3dx11_43 + d3dcompiler_43` | **menu du jeu** |

`vcrun2010` n'est **pas** nécessaire sous Wine : le processus de HP1 charge `msvcr100.dll`/`msvcp100.dll`
depuis `GE-Proton10-34/files/lib/wine/i386-windows/` (relevé dans `/proc/<pid>/maps`), et atteint le menu.

Remarque : une surcharge `WINEDLLOVERRIDES=d3dx11_43=b` n'a pas pris (la DLL native restait chargée) ; seules
les copies de préfixe ont été probantes.

### Verbes winetricks prouvés, jeu par jeu

| Jeu | Verbes nécessaires sous Wine | Preuve |
|---|---|---|
| HP1 | `d3dx11_43`, `d3dcompiler_43` | ci-dessus, puis par le launcher |
| HP2 | les mêmes (même `d3d11drv.dll`) | **non lancé** faute de temps : installé seulement |
| HP5, HP6 | `vcrun2005` déclaré (import `msvcr80`, audit Windows) | **pas prouvé nécessaire sous Wine** : HP6 tournait sans (retour de Ludo) |

### Code

- `src/core/system_checks.py` : `DLL_COMPILATEUR = ("d3dx11_43", "d3dcompiler_43")`, `check_dll_native`
  (Windows : SysWOW64 ; Linux : verbe au `winetricks.log`, ou DLL non-Wine dans `syswow64` **et** surcharge
  `native` dans `HKCU\Software\Wine\DllOverrides`, par `dll_native_dans_le_prefixe`) ; `vcredist2010_x86`
  (`check_vcredist_2010_x86` : `msvcr100` et `msvcp100` dans SysWOW64 ; « présent » sous Linux, prouvé ci-dessus ;
  page `VCREDIST_2010_URL` = download id 26999, VC++ 2010 SP1 MFC) ; verbes `d3dx11_43`, `d3dcompiler_43`,
  `vcrun2010` ; `invalidate_vcredist_cache` vide les nouveaux caches.
- Libellés : bandeau « DirectX (d3dx11_43.dll) », dialogue « Le runtime DirectX de Microsoft (…) »,
  barre « DirectX (d3dx11_43) », « Visual C++ 2010 ». Le texte du dialogue de préparation dit maintenant
  « Les composants (Visual C++, DirectX) sont téléchargés… ». en/es complétés.
- `src/data/games.json` : `requires` sur hp1/hp2 (`d3dx11_43`, `d3dcompiler_43`, `vcredist2010_x86`) et hp5/hp6
  (`vcredist2005_x86`), **`catalog_version` 0.35**. Le publié était identique à l'embarqué (0.34) au moment de
  la modification. **À faire par Ludo après la release du launcher** : recopier l'embarqué dans
  `accio-launcher-games`. Un launcher 1.1.2 ignore sans danger les identifiants qu'il ne connaît pas.
- Tests : `tests/test_prerequis_compilateur.py` (nouveau, 18 tests, Windows et Linux simulés) ; `conftest`
  ajoute les deux verbes à la machine « prête à jouer ».

### Vérifié en conditions réelles (launcher depuis les sources, vrai préfixe)

1. Fiche HP1 : « DirectX (d3dx11_43.dll) manquant dans Wine — requis pour lancer ce jeu. Installer ».
2. Dialogue : « y installer DirectX (d3dx11_43), DirectX (d3dcompiler_43) » → Préparer.
3. Barre du bas : étape, chrono, dernière ligne d'umu (« Downloading steamrt3 (latest)… », « SHA256 is OK »…),
   bouton Annuler. Fin en 75 s (`Préparation de Wine : réussie`), statut « Wine est prêt. ».
4. JOUER : « Démarrage de … Wine peut mettre jusqu'à une minute à ouvrir le jeu. », fenêtre du jeu à 6,8 s,
   launcher rangé à +6,9 s, **menu de HP1 affiché**, retour propre (« Jeu terminé … 98 s »).

HP1 affiche à **chaque** lancement l'assistant « première configuration » (liste de cartes vide,
« Commencer ! » passe) : c'est l'effet documenté de `Running.ini`, que le launcher pose exprès. Non modifié.

## Défaut bloquant trouvé : aucune installation après la préparation de Wine

En installant HP2 :

```
ValueError: Path traversal détecté après extraction : ~/Games/AccioLauncher/_Launcher/prefixes/umu/dosdevices/z:
```

puis la boîte « L'installation a échoué. L'archive est peut-être corrompue. » `verify_extracted_paths` parcourait
**tout** le dossier des jeux, préfixe Wine compris, où `dosdevices/z:` est un lien légitime vers `/`. HP1 et HP6
s'étaient installés avant la création du préfixe, d'où l'absence de symptôme. Effet secondaire : l'extraction
avait eu lieu, HP2 apparaissait « installé » mais sans ses étapes post-installation (configs non copiées).

Correction (`src/core/extractors.py`) : `verify_archive_entries` rend les entrées, `premiers_niveaux()` en tire les
dossiers de premier niveau, et la vérification ne parcourt qu'eux (un premier niveau qui est lui-même un lien
est vérifié). Tests : `TestVerificationApresExtraction` dans `tests/test_installer.py` (l'ancien parcours doit lever
sur le même dossier). **Vérifié** : « Vérifier / réparer » de HP2 → `Config copiée : …/HP2/config/Game.ini`,
`Installation terminée`, `État de hp2 → installed`.

**À signaler dans les notes de la prochaine version** : sous Linux avec la 1.1.2, tout jeu installé après la
préparation de Wine échoue ; ceux qui ont vu l'échec ont un jeu à moitié installé, à réparer.

## B. Temps de lancement

### Mesures (clic ou commande → processus `HP.exe` → première fenêtre), HP1

| Cas | Processus | Fenêtre |
|---|---|---|
| En ligne, umu par défaut, essai 1 (juste après winetricks) | 59 s | — |
| En ligne, umu par défaut, essais 2 et 3 | 17,1 s / 16,4 s | 18,1 s / 17,4 s |
| En ligne, `UMU_RUNTIME_UPDATE=0`, deux essais | 4,5 s / 4,4 s | 6,4 s / 5,4 s |
| Hors ligne (Wi-Fi coupé), umu par défaut, deux essais | 4,5 s / 4,5 s | 5,5 s / 5,5 s |
| Hors ligne, `UMU_RUNTIME_UPDATE=0` | 4,4 s | 6,5 s |
| **Par le launcher corrigé**, en ligne | **5,5 s** | **6,8 s** |

Premier et deuxième lancement ne diffèrent pas sensiblement une fois le runtime écarté.

### Cause

À chaque lancement en ligne, umu interroge `repo.steampowered.com/steamrt3/images/latest-public-beta/VERSION.txt`.
Le CDN de Valve répond selon le nœud `3.0.20260805.254768` ou `3.0.20260928.262393`, jamais la version installée
(`3.0.20260914.260626`). umu ne la trouve pas dans `VERSIONS.txt`, donc **retélécharge l'archive entière**
(`SteamLinuxRuntime_sniper.tar.xz`, 194 750 968 octets), la décompresse, la revérifie (`mtree is OK`), puis écrit
« steamrt3 is up to date ». Parfois la reprise échoue (`ERROR: Digest mismatched`) et le jeu part quand même :
c'est ce qu'on lit dans le `wine-hp1.log` de Ludo. Hors ligne (Wi-Fi coupé), umu échoue tout de suite : pas de
lenteur. Le retour « hors ligne, plus d'une minute » de Ludo tombait en fait **après** le retour du réseau
(journal : en ligne à 11:09:22, la minute a suivi).

### Corrections

- `src/core/compat.py` : `mise_a_jour_runtime_permise()` — une fois le runtime installé
  (`runtime_umu_installe`, `$XDG_DATA_HOME/umu`), umu n'est autorisé à le vérifier qu'une fois par semaine
  (marque `_Launcher/umu-runtime-verifie`) ; sinon `UMU_RUNTIME_UPDATE=0`. Une valeur posée par l'utilisateur reste
  la sienne ; une date dans le futur ne gèle pas. Tests : `TestRuntimeUmuUneFoisParSemaine`.
- Patchs INI : chacun prenait ~190 ms (1,3 s pour HP1) parce qu'`encodage_ansi` relisait le `system.reg` de 4 Mo.
  Mémoïsé sur date + taille : **2 ms par patch** au lancement suivant. Test dans `TestPageDeCodes`.
- `chemin_windows` : `get_documents_dir()` rend un chemin résolu (`/var/home/…`), le préfixe non (`/home/…`) ;
  la comparaison lexicale échouait et le `SavePath` de HP1 valait `Z:\var\home\…\drive_c\users\steamuser\…`.
  Retente en chemins résolus : maintenant `SavePath=C:\users\steamuser\Documents\Harry Potter\Save`.

Le reste (≈ 4,5 s : pressure-vessel, wineserver, démarrage de Proton) est incompressible de notre côté.

## E. `scrub_user_paths`

`src/core/diagnostic.py` : `formes_du_dossier_personnel()` couvre `/home/<nom>` et `/var/home/<nom>`, le chemin
résolu, et les formes Windows que donne Wine (`Z:\var\home\<nom>`, simples et doublées), la plus longue d'abord.
Tests : `TestDossierPersonnelSousSilverblue`.

## Corrections de c321e5b : ce qui a été vérifié

| Retour | Constat |
|---|---|
| 1. Bandes-annonces | **La vidéo s'affiche en fond** (captures successives : l'image change). Aucun avertissement « image » au journal ; ffmpeg dit « No HW decoder found », attendu. Coût CPU non mesuré. |
| 2. Barre de préparation | **Vérifié** (voir A). Le bouton Annuler n'a pas été essayé. |
| 3. Sens 1 : télécharger pendant une préparation | **Refusé**, toast « Préparation de Wine en cours — patientez un instant. » |
| 3. Sens 2 : préparer pendant une opération | **Pas prouvé** : la boîte d'erreur de HP2 est tombée par-dessus le dialogue au moment du clic. |
| 7. Fenêtre au lancement | « Démarrage de … » affiché, fenêtre rangée quand le jeu prend la main (+6,9 s). Le double clic sur JOUER n'a pas été essayé. |

Pendant la préparation, le fil UI n'était pas bloqué (changement de fiche et toast instantanés). py-spy ne sait
pas lire Python 3.14, pas de pile relevée.

## Ce qui reste

1. **C (HP6 figé sur la cinématique)** : pas commencé.
2. **D (agrandir pendant une action)** : pas reproduit. Les essais se sont faits dans gamescope (voir plus bas),
   qui n'a pas de gestionnaire de fenêtres : l'agrandissement Wayland/KWin (`startSystemResize`) n'y est pas
   testable. Le fil UI, lui, restait réactif pendant la préparation : piste KWin/sans cadre plutôt qu'un blocage.
3. **F** : HP3-HP5, HP7a/b non installés ni lancés ; HP2 installé mais pas lancé ; manette non essayée.
4. Retour 3 sens 2, Annuler de la préparation, double clic sur JOUER : à refaire.
5. `vcrun2005` pour HP5/HP6 : déclaré d'après l'audit Windows, non prouvé nécessaire sous Wine (le launcher le
   fera installer sous Linux au prochain JOUER de HP6 : ~1 min, sans danger).
6. `build.sh` et essais avec l'AppImage : non faits.
7. Proposition (non codée) : sous Linux, que l'AppImage installe au premier lancement son `.desktop` et son icône
   dans `~/.local/share` (et offre un raccourci de bureau), comme l'a fait la main ci-dessous.

## Conditions d'essai, sauvegardes, raccourci

- **Copie du préfixe** avant tout essai : `~/AccioSauvegardes/2026-09-30_1201/` (préfixe, `config.json`,
  `sessions.json`). `diff -r` du dossier Documents du préfixe : seuls `HP.ini`, `HP.log`, `Detected.log` de HP1
  diffèrent (patchs et journaux du jeu), plus `Harry Potter II/` créé par l'installation de HP2. **Il n'y avait
  aucune sauvegarde de partie** dans le préfixe ; rien n'a été supprimé.
- Le vrai préfixe a reçu `d3dx11_43` et `d3dcompiler_43` **par le launcher** (c'était l'essai). Copies d'essai du
  préfixe laissées dans `~/Accio-essais/pfx-*` (≈ 700 Mo chacune, à supprimer), captures dans `~/Accio-essais/`.
- Les parties lancées par le launcher ont ajouté ~98 s de temps de jeu HP1 aux statistiques.
- Son : déjà coupé au départ (`0.00 [MUTED]`), laissé tel quel.
- L'écran s'est verrouillé à 12 h 29. Pour ne rien envoyer à l'écran de verrouillage, les essais suivants ont tourné
  dans un gamescope sans écran (`gamescope --backend headless`, captures par `gamescopectl screenshot`, clics par
  xdotool sur son Xwayland). Une demande KDE « Télécommande / contrôle des entrées » ouverte par xdotool plus tôt
  n'a pas été acceptée.
- **Raccourci AppImage** (fait sur ce portable, hors dépôt) : `~/.local/share/applications/be.acciolauncher.AccioLauncher.desktop`
  (menu des applications) et sa copie sur le Bureau, icône 256 px extraite de `assets/accio_launcher.ico` dans
  `~/.local/share/icons/hicolor/256x256/apps/`, `StartupWMClass=AccioLauncher`. Il vise
  `~/Downloads/AccioLauncher-x86_64.appimage` : si l'AppImage est déplacée, corriger la ligne `Exec`.
