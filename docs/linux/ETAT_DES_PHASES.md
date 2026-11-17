# Accio Launcher sous Linux — état des phases 2, 3 et 4

Sections 7 à 9 de [`docs/LINUX.md`](../LINUX.md), déplacées telles quelles le 2026-11-16 (le fichier dépassait
600 lignes) ; leurs numéros sont gardés, les renvois « § 7 », « § 8 », « § 9 » pointent ici.

## 7. État : phase 2 — le lanceur de compatibilité

Ce qui est en place (voir aussi `docs/claude/ARCHITECTURE_CORE.md`, modules `compat`,
`preparation_wine`, `game_registry`, `system_checks`, `pre_launch`) :

- **Détection** : `umu-run`, puis `wine`/`wine64` ; `ACCIO_COMPAT=umu|wine`
  force une famille. Un GE-Proton installé est passé en `PROTONPATH`, sinon un
  UMU-Proton déjà téléchargé, sinon umu choisit (et télécharge).
- **Lancement** : `umu-run <exe>` ou `wine <exe>`, dans le préfixe partagé,
  avec `WINEDLLOVERRIDES` d'après le champ `dll_overrides` du catalogue. La
  sortie de Wine/Proton va dans `_Launcher/logs/wine-<jeu>.log`, réécrit à
  chaque lancement. Sans lanceur : message « Wine introuvable » qui dit quoi
  installer, et bandeau sur la fiche avant même le téléchargement.
- **Préparation** : au premier lancement, un dialogue propose de créer le
  préfixe et d'y installer les composants (winetricks, depuis Microsoft) ;
  rien ne se fait sans clic. En cas d'échec des composants, « Lancer quand
  même ». Journal : `_Launcher/logs/wine-preparation.log`.
- **Registre** : lecture des `.reg` du préfixe, écriture par `regedit /S` via
  le lanceur, relecture ; prévenance conservée, sans mention d'UAC.
- **Chemins** : Documents/AppData du préfixe pour les fichiers ; chemins
  Windows (`C:\…`, `Z:\…`) pour les valeurs lues par le jeu ; page ANSI du
  préfixe pour les INI.
- **Surveillance** : `/proc`, même grâce de 10 s.
- **Catalogue** : `dll_overrides` depuis le 0.29 ; au 0.43, `winmm` pour hp1 et
  hp2 (correctif 2.x). Embarqué et distant identiques (vérifié le 2026-10-20).

### Vérifié dans l'environnement de travail (Wine 9.0 64 bits, 2026-09-24)

Avec `tools/verifier_wine.py` (préfixe, aller-retour HKCU) et des essais ponctuels
(HKLM 32 bits, processus, surcharge), sur un vrai préfixe :

| Vérification | Résultat |
|---|---|
| Création du préfixe par `wine wineboot --init`, attente de `system.reg` | prêt en 16 s |
| Écriture HKCU par le vrai `_ecrire_par_wine` puis relecture | OK en 3,1 s |
| Cas HP7 : HKLM vue 32 bits, `Install Dir` accentué (`Z:\home\frédéric\…`) | écrit sous `Wow6432Node`, relu à l'identique |
| Deuxième passage avec les mêmes valeurs | aucune écriture, **aucune question** |
| `processus_du_jeu` sur un vrai processus Wine (`ping.exe`) | trouvé ; ignoré pour un autre préfixe |
| Surcharge `d3d9=n,b` | DLL du dossier chargée en `native` (§ 3) |

**Non vérifié ici** : umu-run et Proton (pas de Steam Linux Runtime dans ce
conteneur), winetricks (absent, et Wine sans support 32 bits), un vrai jeu.

### Pour dépanner

- `python3 tools/verifier_wine.py` : relevé (lanceur, préfixe, composants).
  `--preparer` fait la préparation, `--registre` un aller-retour d'essai sous
  `HKCU\Software\AccioLauncher\Verification`.
- `UMU_LOG=1` (umu) ou `PROTON_LOG=1` (Proton) dans l'environnement du
  launcher : journaux détaillés, écrits par umu et Proton eux-mêmes.
- Les préfixes se suppriment sans risque pour les jeux eux-mêmes — mais les
  **sauvegardes de HP1 à HP7b sont dedans** (Documents et AppData du préfixe).

## 8. État : phase 3 — le reste du portage

- **7-Zip** : le 7-Zip officiel pour Linux (`assets/7z/linux/7zzs`, 26.00,
  variante statique) est embarqué et passe avant tout 7-Zip du système ;
  chaque build n'embarque que le sien. Sa progression s'efface par retours
  arrière (`\x08`) sans jamais de `\r` : elle est découpée dessus, sinon la
  barre restait à 0 % jusqu'à la fin.
- **Mise à jour du launcher** : dans une AppImage, le fichier désigné par
  `$APPIMAGE` est remplacé atomiquement (copie à côté, `chmod 755`,
  `os.replace`), puis un `/bin/sh` détaché attend la fin du processus et
  relance. Un dossier en lecture seule, ou un lancement depuis les sources,
  retombe sur la page de release. Le vérificateur choisit l'asset `.AppImage`
  (et son empreinte), plus jamais l'`.exe`.
- **« Redémarrer maintenant »** attend désormais la fin du processus avant de
  relancer (la relance immédiate butait sur l'instance unique).
- **Discord** : sockets natifs, **Flatpak** (`app/com.discordapp.Discord`) et
  Snap.
- **Environnement** : l'AppImage retire ses propres bibliothèques de
  `LD_LIBRARY_PATH` pour tout ce qu'elle lance (Wine, umu, `xdg-open`, le
  navigateur).
- **Bureau** : `app_id` Wayland `be.acciolauncher.AccioLauncher` (le nom du
  `.desktop` de la phase 4) ; sans zone de notification, la fenêtre est
  RÉDUITE pendant une partie au lieu d'être cachée sans moyen de la rappeler.
- **Diagnostic** : distribution, noyau, session (`KDE · Wayland`,
  `Gamescope`), processeur, mémoire, cartes graphiques (`/sys/class/drm`,
  `pci.ids`, version NVIDIA), et une ligne « Compatibilité » (lanceur, Proton,
  préfixe, composants), aussi écrite en tête du journal. Le nom Unix du profil
  Wine est masqué comme le dossier personnel.

### Vérifié dans l'environnement de travail (Ubuntu 24.04, sans affichage)

| Vérification | Résultat |
|---|---|
| Extraction réelle par `7zzs` : 48 Mo (suite de tests), puis 120 Mo en quatre volumes `.7z.001` par le vrai `extract_7z` | fichiers identiques, progression intermédiaire reçue (56 %, 84 %, 100 %) |
| Relance par le vrai `/bin/sh` : attend la fin du processus, puis lance | test de bout en bout dans la suite |
| Remplacement d'un fichier « AppImage » factice ; dossier en lecture seule (simulé : le conteneur tourne en root, qui écrit partout) | remplacé / renvoi à la page de release |
| Socket Discord factice sous `app/com.discordapp.Discord` | trouvé, préféré aux emplacements absents |

**Non vérifié ici** : une vraie AppImage (construite en phase 4), un vrai
Discord, une vraie session Wayland ou GNOME sans zone de notification, une
vraie carte graphique (le conteneur n'a ni `/sys/class/drm` ni `pci.ids`).

## 9. État : phase 4 — l'AppImage et la release commune

- **`./build.sh`** : icône → lint → tests → géométrie (vraies polices, Xvfb
  sans session graphique) → PyInstaller (dossier) → AppImage, arrêt au premier
  échec. Hors d'un environnement virtuel, il crée `.venv-build`. Bazzite n'a
  pas Xvfb : l'audit passe par la session (`DISPLAY`), ou à défaut par le premier
  affichage de `/tmp/.X11-unix` (le Xwayland de gamescope). **Ne pas exporter
  `QT_QPA_PLATFORM`** en l'appelant : `conftest.py` ne fait qu'un `setdefault`,
  et la suite ouvrirait alors ses fenêtres sur l'affichage.
- **`build/linux/appimage.py`** assemble l'AppDir (`AppRun`, `.desktop`
  `be.acciolauncher.AccioLauncher`, icônes extraites des sept tailles de
  l'`.ico`, licence et avis tiers) et appelle appimagetool 1.9.1 avec le
  runtime `type2-runtime` 20251108, **épinglés par empreinte**. Le runtime est
  statique : pas de libfuse2 à installer.
- **`build/linux/dependances.py`** : ce que la machine fournit n'est pas
  embarqué (liste d'exclusion AppImage), ce que plus rien n'atteint est
  élagué (la pile GTK du greffon `libqgtk3`, 23 bibliothèques), et un dossier
  dont une dépendance manquerait est REFUSÉ avant emballage.
- **`release.yml`** : job `version` (tag déduit une fois), builds Windows et
  Linux (conteneur `ubuntu:22.04` sur `ubuntu-latest`) en parallèle, puis UN brouillon portant l'exe,
  l'AppImage et leurs deux attestations — seulement si les deux builds ont
  réussi. Rien n'est publié automatiquement ; case décochée, les deux
  fichiers sont joints au run (7 jours).
- **Notes de release** : section Linux après le trait (hors de la boîte de
  mise à jour du launcher), empreinte `{SHA256_LINUX}` posée par le workflow.

### Vérifié dans l'environnement de travail (Ubuntu 24.04, Xvfb)

| Vérification | Résultat |
|---|---|
| `./build.sh` de bout en bout | 1814 tests, audit de géométrie OK (xcb, 27 familles, 78 s), AppImage de 62 Mo, en 3 min 19 |
| Dossier gelé : dépendances | 0 défaut ; 47 bibliothèques laissées à la machine ; 195 → 168 Mo |
| L'AppImage lancée sous Xvfb (plateforme `xcb`) | démarre, affiche l'assistant, journal « (AppImage) », `WM_CLASS` = `AccioLauncher` |
| Chargeur PyInstaller (onedir) et `LD_LIBRARY_PATH` | `_internal` placé en tête ; un enfant du launcher gelé reçoit la valeur d'ORIGINE (absente, ou `/opt/x`) |
| `.desktop` | `desktop-file-validate` sans remarque |

### Vérifié sur Bazzite (portable, 2026-10-20)

Bazzite, noyau 7.2.7, KDE Wayland, umu-launcher 1.4.4, GE-Proton10-34, Intel UHD
(Mesa 26.2.2). Détail : `docs/linux/RETOUR_BAZZITE.md`.

| Vérification | Résultat |
|---|---|
| `./build.sh` de bout en bout (Python 3.14.7, audit sur la session) | 3323 tests, audit OK, 48 bibliothèques laissées à la machine, AppImage de 64 Mo, en 3 min 00 |
| L'AppImage lancée (xcb) | fenêtre en moins d'une seconde, journal « (AppImage) », HP1 lancé, launcher revenu à la fin |
| Les jeux par JOUER (umu, préfixe partagé) | HP1, HP3, HP4, HP6 jouables ; HP7a/HP7b depuis la correction du lecteur (§ 4.3) ; HP2 jusqu'à la partie avec le correctif 2.1.1 (lanceur noir avec le 2.0.1 des archives) ; HP5 lancé à la main seulement |
| Préparation de Wine depuis le bandeau | `vcrun2005` 12 s, `vcrun2008` 10 s ; « Annuler » non testable à la main (trop rapide) |
| Registre de HP7a/HP7b | `Install Dir` et `Locale` sous `Wow6432Node`, prévenance « registre de Wine » sans mention d'administrateur |
| Zone de notification | le launcher s'y range au lancement et revient à la fin de partie (grâce de 10 s pour UE1) |

**Revérifié le 2026-11-12** (noyau 7.3.3, Mesa 26.2.6, Python 3.15.0, launcher 1.3.3, catalogue 0.57) : `./build.sh` code 0 en 2 min 59 (4581 tests), AppImage de 71 Mo, fenêtre en moins d'une seconde ; HP1 à HP6 joués par JOUER avec elle (F12, F10, F11, Alt+Tab), correctif 2.4.0 chargé (2.2.0 pour HP6) ; incrustation dessinée sans gel dans HP4, HP5, HP6 (§ 4.9).

**Piège d'essai** : sans `WAYLAND_DISPLAY`, Qt (plateforme `wayland`) se connecte
quand même à `wayland-0`. Pour un essai sur un autre affichage, passer
`QT_QPA_PLATFORM=xcb` et `DISPLAY` au launcher lui-même.

### Build d'essai du workflow (`ubuntu-22.04`, run 36058062239)

Lancé par Ludo, case décochée : les deux jobs verts. Côté Linux, 1878 tests,
audit de géométrie OK (xcb, 22 familles), 48 bibliothèques laissées à la
machine, 0 dépendance manquante — mais une AppImage de **77 Mo au lieu de
62**. Cause relevée en rejouant le build avec le MÊME Python (setup-python
3.14.7 pour 22.04) : sa `libpython3.14.so` fait 33 Mo, **avec ses symboles de
débogage**, comme ses modules natifs ; celle d'Ubuntu est déjà épurée. Le
spec passe donc `strip=True` sous Linux (l'exe Windows ne change pas) :
dossier 209 → 163 Mo, AppImage 78 → 62 Mo, `7zzs` intact (c'est une donnée,
pas un binaire pour PyInstaller). L'AppImage épurée a été relancée sous Xvfb
jusqu'à la fenêtre principale : illustrations, icônes SVG, polices,
particules, et une poignée de main TLS menée jusqu'à la vérification du
certificat (refusé ici par le proxy du conteneur, pas par le launcher).

**Non vérifié ici** : une session Wayland, le montage FUSE par un utilisateur non root (`fusermount3`),
Gear Lever, le mode Jeu. L'auto-mise à jour de l'AppImage est relevée au
journal sur Bazzite (1.2.3 → 1.3.3, RETOUR_BAZZITE.md, septième passage).

### Revérifié dans un conteneur Ubuntu 24.04 (audit du 2026-10-29)

Python 3.15.2 (python-build-standalone, installé par `uv`), paquets de
`.github/requirements/tests.txt`, bibliothèques Qt du job `linux-smoke`, Xvfb,
Wine 9.0 **avec le support 32 bits** (`wine32:i386`) et winetricks 20240105.
Suite lancée sous un utilisateur NORMAL (`useradd`), comme le recommande
`docs/claude/ARCHITECTURE.md`.

| Vérification | Résultat |
|---|---|
| `pytest -n 4 --dist loadfile`, utilisateur normal | **3838 réussis, 39 sautés** (tous Windows seulement), 78 s |
| La même suite en root | 3837 réussis, 1 échec attendu (`test_l_attribut_de_l_archive_est_conserve` : root écrit dans un fichier en lecture seule) |
| Les 29 tests sautés sous Windows | TOUS joués ici : chemins POSIX du préfixe (10), chemins de l'hôte (7), liens symboliques (3 + 1), 7-Zip Linux (2), `/bin/sh` (2), socket Unix, droits POSIX, bit exécutable, `.DirIcon` |
| ruff, mypy (plateforme `win32` fixée) | propres |
| `./build.sh` de bout en bout (`ACCIO_PY`, `PYTEST_ADDOPTS` de la release) | code 0 : audit de géométrie OK (fr/en/es × 3 scénarios), 50 bibliothèques laissées à la machine, **AppImage de 67 Mo** |
| L'AppImage sous Xvfb, `APPIMAGE_EXTRACT_AND_RUN=1` | assistant de premier lancement, puis fenêtre principale avec une config posée ; journal « (AppImage) », `WM_CLASS` = `AccioLauncher` |
| L'AppImage montée par FUSE (sans extraction) | en root : montée et lancée, sans libfuse2 (runtime statique). Utilisateur normal : refusé, `/dev/fuse` du conteneur est en `crw-------` (limite du conteneur, pas de l'AppImage) |
| Préfixe par `tools/verifier_wine.py --preparer` | préfixe `win64` créé en ~18 s, page ANSI cp1252, Documents `C:\users\<nom>\Documents` |
| Composants par winetricks | échec : le proxy du conteneur refuse `aka.ms` (réseau, pas le launcher). VC++ 2005/2010, `d3dx9_43`, `d3dx9_37`, `xinput1_3` répondent « présent » d'office, comme prévu |
| `--registre` (le vrai `_ecrire_par_wine`) | HKCU écrit puis relu, OK en 3,0 s |

**Taille de l'AppImage** : 67 Mo ici contre 62 sur la machine de build d'Ubuntu
22.04. Écart venu du PYTHON, pas du code : la `libpython3.15.so` de
python-build-standalone pèse 21 Mo une fois épurée (dépendances liées en
statique), celle d'`actions/setup-python` 7 Mo. Le build de release reste la
référence ; un build local fait par `uv` n'est pas comparable au Mo près.

`libQt6Quick` et `libQt6Qml` (14 Mo) restent nécessaires : c'est le greffon
FFmpeg de QtMultimedia (`libffmpegmediaplugin.so`) qui les réclame.

### Build d'essai dans le conteneur `ubuntu:22.04` (2026-10-29)

`release.yml` passe le job Linux sur `runs-on: ubuntu-latest` avec
`container: ubuntu:22.04`. Le déclenchement du workflow depuis la session
d'audit étant refusé (403), le job a été REJOUÉ dans l'image officielle
`ubuntu:22.04`, avec le Python 3.15.2 que `setup-python` installe pour 22.04
(même archive `python-versions`), les paquets du workflow et `./build.sh`.

Le conteneur nu manquait de trois choses que l'image de runner fournissait,
toutes ajoutées au workflow et tenues par `test_build_linux` :

| Manque | Symptôme |
|---|---|
| `libsqlite3-0` | mypy (étape 2/6) : « INTERNAL ERROR » sur `import sqlite3` |
| `libxrandr2` | greffon FFmpeg de QtMultimedia non chargé : aucune vidéo, 2 tests de lecture en échec |
| `file` | appimagetool refuse de tourner |

| Vérification | Résultat |
|---|---|
| Tests (root, `-n 4`) | 3981 réussis, 41 sautés, 66 s |
| Audit de géométrie (Xvfb, vraies polices) | OK |
| AppImage | 64 Mo, `verifier_dossier` sans défaut |
| `glibc_exigee.py … 2.35` | 165 fichiers ELF, glibc exigée **2.35** : accepté |
| Contre-épreuve `… 2.34` | refusé : `libpython3.15.so.1.0` exige GLIBC_2.35 |
| `objdump -T` brut sur l'image extraite | versions les plus hautes : 2.33, 2.34, **2.35** |

**Gel intermittent** : une passe sur trois a gelé à 98 % des tests (le
symptôme de la release #22), sans que `PYTEST_TIMEOUT` ne se déclenche : le
blocage est dans du code C, où le signal de la méthode par défaut n'arrive
pas. La release passe donc `--timeout-method=thread` : le fil de garde vide
les piles au journal et arrête le build en 60 s. La passe suivante, identique,
était verte.

### Release 1.3.1 : le Python du runner dans le conteneur (2026-10-31)

Le job Linux est mort au premier `python` : « version GLIBC_2.38 not
found ». L'image `ubuntu-latest` porte désormais un Python 3.15.1 construit
pour 24.04 dans son cache d'outils, monté dans le conteneur (`/__t`), et
`setup-python` prend un Python déjà en cache avant d'en télécharger un. Le
job lui donne donc un cache vide, propre au conteneur (`RUNNER_TOOL_CACHE`
et `AGENT_TOOLSDIRECTORY` sur l'étape), ce qui le force à télécharger le
build 22.04 ; l'étape « Python adapté au conteneur » affiche la glibc et la
version retenue, et s'arrête en clair si elles ne vont pas ensemble.
