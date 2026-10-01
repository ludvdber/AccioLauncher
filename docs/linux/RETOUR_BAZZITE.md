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

## Complément (après-midi)

- **C, HP6** : pas reproduit. Nouvelle partie lancée par umu (GE-Proton10-34), son coupé : la cinématique du
  serment joue jusqu'au bout sans toucher au clavier, puis la partie démarre ; Meta pendant le jeu → le correctif
  journalise `another program in front, the game is not told` puis `back in front`, le jeu continue. Dans
  l'ancien journal, en revanche, la cadence tombe à ~3 images/s (images 12062 → 13006 en 313 s) avant la fin :
  c'est là que le gel a eu lieu. Journaux : `~/Accio-essais/hp6-d3d9-ancien.log`, `hp6-d3d9-essai.log`.
  Sauvegardes copiées avant, remises après.
- **D** : trouvé une cause certaine pour le déplacement : sous Wayland `move()` est ignoré, la barre de titre
  ne déplaçait donc pas la fenêtre. `TitleBar.mousePressEvent` passe maintenant par `startSystemMove`
  (repli manuel s'il refuse) ; test `tests/test_title_bar_wayland.py`. L'agrandissement n'a pas été revu.
- AppImage reconstruite (`build.sh`, sortie 0) et copiée dans `~/Téléchargements/` pour le raccourci : pas relancée.

## Deuxième passage (2026-10-01)

Launcher depuis les sources (catalogue embarqué modifié), préfixe copié avant (`~/AccioSauvegardes/prefixe-umu-1001`),
son coupé. Suite : **2313 réussis, 33 sautés**, ruff propre ; AppImage reconstruite (66 Mo).

### `xinput1_3` : défaut confirmé et corrigé

HP6 lancé exactement comme le launcher (`WINEDLLOVERRIDES=d3d9=n,b`, `WINEDEBUG=+loaddll`) :

```
Loaded L"X:\\Games\\AccioLauncher\\HP6\\d3d9.dll" at 7AF50000: native
Loaded L"X:\\Games\\AccioLauncher\\HP6\\XINPUT1_3.dll" at 7AF20000: builtin
```

Aucun `xinput_accio.log`. Avec `d3d9=n,b;xinput1_3=n,b` : `XINPUT1_3.dll … native`, et le journal du correctif
apparaît (`settings: PlayStation=1 Rumble=1 LightBar=set`, `Accio xinput1_3: Xbox pads through xinput1_4.dll`).
→ `"xinput1_3"` ajouté à `dll_overrides` de hp5, hp6, hp7a, hp7b (`src/data/games.json`, embarqué, sans
nouveau numéro), `docs/LINUX.md` § 3, `CLAUDE.md`, et `TestLeCatalogueEmbarqueDeclareLesSurcharges`.
**À reporter dans le catalogue distant.**

### D : fenêtre du launcher sous KWin (Wayland)

Sur la vraie fenêtre, souris pilotée par `ydotool` : glisser la barre de titre **déplace** la fenêtre
(correctif `startSystemMove` du premier passage, vérifié) ; double clic sur la barre **agrandit**. Pendant une
action : pas encore essayé.

### HP2 : premier lancement

| | |
|---|---|
| Bandeau de prérequis | aucun : le préfixe a déjà `d3dx11_43`/`d3dcompiler_43` posés pour HP1. |
| Démarrage | oui, par JOUER ; launcher rangé dans la zone de notification. |
| Écran | la fenêtre de démarrage du jeu « Menu principal » s'affiche **sans fond ni boutons** : seul « Quitter » est dessiné, avec le texte « clique sur Nouvelle partie ou Charger partie ». Survol, Alt+N : rien. **Injouable en l'état.** |
| `Running.ini` | créé par le launcher à 11:17:24 (`Fichier pré-lancement créé : …/Harry Potter II/Running.ini`), **absent** 13 s plus tard ; `Detected.log` montre l'autodétection (`testrendev=D3DDrv.D3DRenderDevice`, `Can't find file for package 'D3DDrv'`). Le jeu retire donc le fichier lui-même : le garde-fou ne joue pas chez HP2 comme chez HP1 (non mesuré sous Windows). `GameRenderDevice` reste `D3D11Drv` après la sortie. |
| Sortie | « Quitter » ferme proprement. |

Piste pour le menu vide : ses boutons sont des images de la fenêtre de démarrage (Window.dll/GDI), pas du
rendu D3D11 ; à comparer avec Windows (le même écran y a-t-il ses quatre boutons ?).

### HP3 : dgVoodoo plante sous Proton, DXVK seul fonctionne

| | |
|---|---|
| Installation | par le launcher, 336 Mo à ~23 Mo/s, barre du bas visible, `État de hp3 → installed`. |
| Lancement avec le catalogue (`d3d8,d3d9,ddraw,msvcr70`) | **plantage au démarrage** : « Critical Error — General protection fault », `History: CreateDevice <- UD3DRenderDevice::SetRes <- UWindowsViewport::TryRenderDevice <- UWindowsViewport::OpenWindow <- UGameEngine::Init <- InitEngine`, carte vue comme « Intel(R) Graphics (ADL GT2) (dgVoodoo DX API Layer) ». Capture : `~/Accio-essais/hp3-critical.png`. |
| Sans surcharge (d3d8/d3d9 de Proton = DXVK) | menu complet, nouvelle partie, emplacement, cinématique du train avec sous-titres : **le jeu tourne**. |
| Catalogue | `dll_overrides` de hp3 ramené à `["msvcr70"]` (embarqué ; test, `docs/LINUX.md`, `CLAUDE.md`). Relancé par JOUER : `surcharges msvcr70`, menu atteint, « Quitter → Oui » sort en code 0. **À reporter dans le catalogue distant.** Cadence ≤ 60 : non mesurée. |

Ce que dgVoodoo apportait sous Windows (cartes modernes) est fait sous Linux par DXVK ; si un réglage de
`dgVoodoo.conf` le rend viable sous Proton, c'est à chercher côté Windows (non essayé ici).

### Reste de ce passage

HP4 en partie (ci-dessus), HP5, HP7a, HP7b (non installés), le correctif de cette nuit
(`gh` absent : artefact `d3d9-win32` à fournir par Ludo), HP6 sur 10 min et ombres ×4, HP1 (charger une partie),
D pendant une action (le double clic simulé par `ydotool` ne tombe pas de façon fiable sur la barre de titre :
à faire avec Ludo), retours 3/Annuler/double clic sur JOUER, AppImage. Suppression de `~/Accio-essais/pfx-*` :
à demander.

### HP4 : invite de sauvegarde automatique, 10 démarrages sur 10 sans plantage

Installé par le launcher (847 Mo, extraction 7zzs en 21 s), lancé par JOUER (`surcharges d3d9,msvcr71`) : choix
de langue, puis « Voulez-vous activer la sauvegarde automatique », « Oui ». L'archive porte déjà le nouveau
correctif (`d3d9_accio.log` écrit). Puis neuf démarrages scriptés (`~/Accio-essais/hp4-boucle.sh`, même
`WINEDLLOVERRIDES`, aucune sauvegarde n'étant écrite avant la fin des logos l'invite revient à chaque fois) :
**10 / 10 vivants 8 s après « Oui »**, captures `hp4-invite*.png` / `hp4-apres*.png`. Le plantage Windows
d'environ 1 sur 10 ne se montre pas sous Wine (sans la DLL de cette nuit, donc sans `AudioStreamGuard`).
Note : le jeu ne reçoit le clavier qu'après un clic dans sa fenêtre (focus). ZQSD en partie : non essayé.

### Après l'audit de 9998e0d

**1. HP3, `max_fps` : le plafond n'est PAS appliqué.** Le launcher journalise bien `surcharges msvcr70, plafond 60 ips`
et le processus reçoit `DXVK_FRAME_RATE=60` (lu dans `/proc/<pid>/environ`), mais **HP3 ne passe pas par DXVK** :
`/proc/<pid>/maps` montre `lib/wine/i386-windows/d3d8.dll` + `wined3d.dll`. Proton ne pose `d3d8=n` (et ne copie le
d3d8 de DXVK dans `syswow64`) que si `PROTON_DXVK_D3D8=1` ; sans lui, le `syswow64/d3d8.dll` du préfixe est celui
de Wine (`Wine builtin`, pas de « dxvk »). Le compteur `DXVK_HUD=fps` n'apparaît d'ailleurs jamais.

Essais pour mettre HP3 sur DXVK, chaque fois DLL de dgVoodoo mises de côté puis remises (`cmp` : identiques) :

| Essai | Résultat |
|---|---|
| `PROTON_DXVK_D3D8=1`, `D3D8.dll` de dgVoodoo écarté seul | le d3d8 de DXVK charge le `D3D9.dll` de dgVoodoo du dossier du jeu → « Please install DirectX 8.1b or later » |
| `PROTON_DXVK_D3D8=1`, les quatre DLL de dgVoodoo écartées | DXVK chargé (`syswow64/d3d8.dll` + `d3d9.dll`, compteur visible) mais **image figée** sur l'introduction (compteur bloqué à 35,8, jeu à ~10 % CPU), > 1 min, Échap/Entrée/clic sans effet |
| dgVoodoo + `Resolution = unforced` (au lieu de `max`) | même « General protection fault » dans `UD3DRenderDevice::SetRes` |
| dgVoodoo + `OutputAPI = d3d11_fl11_0` | idem |

Cadence réelle sous wined3d (`WINEDEBUG=+fps`, menu) : **57-59 images/s**. Contre-épreuve `vblank_mode=0` :
**58 images/s** aussi → **ne prouve rien** : écran à 60 Hz et XWayland/KWin synchronisent de toute façon. Pas
d'écran > 60 Hz disponible. Conclusion : `DXVK_FRAME_RATE` est sans effet sur HP3 tel que lancé ; wined3d n'a
pas de limiteur. Pistes (côté Windows / décision) : faire tourner dgVoodoo sous Proton, ou plafonner par un
autre moyen que DXVK (le moteur, ou un limiteur dans le correctif s'il en existe un pour UE2/HP3).

**3. HP2, `GameRenderDevice` pendant la partie.** `Running.ini` posé, jeu lancé (12:57:48), relevé toutes les 2 s :
`Running.ini` présent jusqu'à ~12 s, **absent à 15 s** ; à 12:58:03 `Detected.ini`, `Detected.log` et `Game.ini`
sont réécrits ensemble (autodétection), mais **`GameRenderDevice` et `WindowedRenderDevice` restent
`D3D11Drv.D3D11RenderDevice`** pendant toute la partie (relevé à 2, 4, …, 25 et 50 s). Seul `RunCount` change
(50 → 52) entre avant et après. Différence avec HP1 : la détection n'y réécrit pas le pilote. Plein écran non
touché. Le menu reste sans fond ni boutons.

**2. HP7a/HP7b et `xinput1_3`** : non fait (non installés).

L'écran s'est verrouillé à 12:59 : essais à l'écran interrompus là. HP2, HP3 et HP4 fermés, `dgVoodoo.conf`
et DLL de HP3 remis, préfixe sauvegardé dans `~/AccioSauvegardes/prefixe-umu-1001`.
