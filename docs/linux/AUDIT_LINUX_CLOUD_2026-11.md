# Audit Linux depuis le cloud (2026-11-17)

Pour : Ludo. Fait dans un conteneur Linux, **sans les jeux** : aucun jeu n'a été lancé ici, et rien dans ce
rapport ne prétend le contraire. Ce qui concerne les jeux s'appuie sur tes relevés faits sur Bazzite
(`docs/linux/RETOUR_BAZZITE.md`) et c'est dit à chaque fois. Aucun fichier de code ni de test n'a été modifié :
ce rapport est le seul fichier livré, et les correctifs y sont **proposés**, pas appliqués.

Dépôt audité : `main` à `55345d3` (2026-11-17 18:40), launcher 1.3.5.

---

## Le verdict en trois lignes

- **Ça marche** : sous Linux, toute la suite passe (4995 réussis, 48 sautés, 0 échec), ruff et mypy sont propres,
  `./build.sh` va au bout (code 0, 4 min 26) et l'AppImage obtenue (72 Mo) démarre sur l'assistant de premier
  lancement sans rien écrire hors du dossier personnel. Aucun appel propre à Windows n'est laissé sans garde.
- **Ça casse** : rien de bloquant pour Bazzite. Deux défauts réels mais sans gravité : (1) le build de release
  installe un ruff **non vérifié par empreinte** (0.17.5 au lieu du 0.17.3 verrouillé) ; (2) chaque fichier
  réécrit par le launcher (l'exe patché « 4 Go », les INI des jeux) passe en droits **0600**, et un lien
  symbolique est remplacé par un fichier ordinaire. Pour toi seul sur ta machine, ça ne change rien en pratique.
- **On ne sait pas encore** : le vrai **mode Jeu**, l'icône après intégration par **Gear Lever**, **Discord en
  Flatpak**, la **manette pour naviguer dans le launcher** sous Linux, et HP7a avec le drapeau 4 Go sous Proton.
  Sept essais courts, en fin de rapport.

---

## 1. Ce qui a été mesuré

### Environnement

| Élément | Version |
|---|---|
| Système | Ubuntu 24.04.5 LTS, noyau 6.18.44, x86_64, 4 cœurs (pas Fedora : voir les limites, § 6) |
| Python | 3.15.2 (python-build-standalone, installé par `uv` 0.13.9 ; le `uv` 0.8.17 présent ne connaissait pas la 3.15) |
| Paquets | `pip install --require-hashes -r .github/requirements/tests.txt` : OK. PyQt6 6.11.0 (Qt 6.11.2), pytest 9.2.0, pytest-qt 4.5.0, pytest-xdist 3.8.0, pytest-timeout 2.4.0, ruff 0.17.3, mypy 2.4.1, PyInstaller 6.22.3 |
| Bibliothèques système | celles du job `linux-smoke` (`libegl1 libgl1 libxkbcommon0 libdbus-1-3 libpulse0 libgssapi-krb5-2`), plus `libxrandr2 libsqlite3-0 file xvfb`, les `libxcb-*` de Qt et `fuse3` |

### Tests, lint, types

Commande : `QT_QPA_PLATFORM=offscreen python -m pytest -n auto --dist loadfile`.

| Passe | Réussis | Sautés | Échecs | Durée |
|---|---|---|---|---|
| Utilisateur normal (`useradd ludo`), comme le recommande `docs/claude/ARCHITECTURE.md` | **4995** | **48** | **0** | 89 s |
| Root | 4994 | 49 | 0 | 94 s |
| Dans `./build.sh` (étape 3/6, utilisateur normal) | 4995 | 48 | 0 | 93 s |

- `ruff check .` : « All checks passed! » (ruff 0.17.3).
- `mypy` : « Success: no issues found in 101 source files ».
- `mypy --platform linux` : « Success: no issues found in 101 source files ».

**Le compte tombe juste.** Sous Windows : 5009 + 34 = 5043 tests. Ici : 4995 + 48 = 5043. Même total, et l'écart
s'explique entièrement : 47 tests Windows seulement et 1 test qui attend un autre dépôt sont sautés ici ; les
30 tests Linux seulement et les 4 tests de liens symboliques (sautés sous Windows sans le droit adéquat) passent ici.
5009 − 47 − 1 + 30 + 4 = 4995.

**Les 48 sautés, un par un** (sortie de `pytest -rs`, regroupés par raison) :

| Raison donnée par le test | Nombre | Fichier:ligne | Pourquoi c'est normal |
|---|---|---|---|
| chemins Windows (`C:\…`) | 11 | `tests/test_game_registry.py:177, 183, 190, 202, 215, 223, 353, 375, 399, 412, 422` | conversion de chemins propre au registre Windows |
| `.bat` / constantes `CREATE_NO_WINDOW` de Windows | 7 | `tests/test_self_update.py:54, 101, 128, 149, 386, 389` ; `tests/test_securite.py:116` | mise à jour par script `.bat` : Linux a son `/bin/sh`, testé à part |
| System32 / `C:\Windows` / `tasklist` | 6 | `tests/test_securite.py:80` (×4), `:75`, `:88` | programmes système de Windows |
| lancement, couche et code d'erreur Windows | 4 | `tests/test_game_manager.py:1040, 1063, 1147, 1155` | lancement direct de l'exe ; sous Linux, c'est umu/wine (testé ailleurs) |
| `Install Dir` Windows | 1 | `tests/test_game_manager.py:949` | son pendant Linux est `test_lancement_linux.py::…::test_install_dir_est_un_chemin_z` |
| flux NTFS `Zone.Identifier` | 1 | `tests/test_game_manager.py:353` | n'existe pas sous Linux |
| registre et DWM | 3 | `tests/test_win_utils.py:100, 104, 117` | API Windows |
| liste des processus de Windows | 2 | `tests/test_process_monitor.py:135, 148` | Linux lit `/proc`, testé ailleurs |
| HID par setupapi | 2 | `tests/test_manette.py:390, 395` | Linux passe par hidraw |
| `vgmstream.exe` embarqué seulement sous Windows | 2 | `tests/test_vgmstream.py:39, 46` | voulu |
| Authenticode, PowerShell | 2 | `tests/test_composants_windows.py:92, 140` | installation de VC++ propre à Windows |
| exe signé de Windows | 1 | `tests/test_memoire_4go.py:66` | lit un exe du système Windows |
| page ANSI Windows (`mbcs`) | 1 | `tests/test_pre_launch.py:124` | Linux lit la page du préfixe |
| énumération des modes d'écran | 1 | `tests/test_resolution_jeu.py:368` | API Windows |
| installation Windows (ACT-054) | 1 | `tests/test_action_alerts.py:202` | bandeau propre à Windows |
| diagnostic Windows | 1 | `tests/test_diagnostic.py:43` | `win32_ver` |
| lit le registre Windows | 1 | `tests/test_tools_catalogue.py:74` | outil de poste Windows |
| **dépôt `accio-launcher-games` absent** | **1** | `tests/test_catalogue_embarque.py:99` | **le seul qui n'est pas « Windows seulement »** : il compare le catalogue embarqué à un dépôt voisin, absent du conteneur |
| **Total** | **48** | | |

Le 49e saut en root (`tests/test_post_install_config.py:54`, « root écrit dans un fichier en lecture seule ») est
voulu : root passe outre les droits.

### Build de l'AppImage

`./build.sh` lancé **en utilisateur normal, hors environnement virtuel**, avec `python3.15` dans le PATH : le
chemin qu'il prend sur Bazzite (il crée `.venv-build`).

| Étape | Résultat |
|---|---|
| Dépendances (`pip install -r requirements-dev.txt`) | installées… **dont ruff 0.17.5**, pas le 0.17.3 verrouillé (constat C1) |
| 1/6 icône | 7 tailles, OK |
| 2/6 ruff, mypy, mypy linux | propres |
| 3/6 tests | 4995 réussis, 48 sautés |
| 4/6 géométrie (Xvfb, vraies polices) | 9 « OK » (fr/en/es × nominal, bandeau, charge) |
| 5/6 PyInstaller | 50 bibliothèques laissées à la machine, aucun défaut |
| 6/6 AppImage | appimagetool 1.9.1 téléchargé et vérifié par empreinte ; **aucun outil manquant** |
| Fin | **code 0, 266 s**, `dist/AccioLauncher-x86_64.AppImage` = 75 831 800 octets (**72 Mo**), SHA-256 `8029afca…127a` |

**Outils manquants ?** Aucun pour construire : appimagetool et le runtime sont téléchargés par
`build/linux/appimage.py`. **FUSE manquait pour lancer** : dans le conteneur, `/dev/fuse` est en `crw-------`
(root seulement). En utilisateur normal, l'AppImage refuse de se monter (« open dir error », code 127).
Contournement : `APPIMAGE_EXTRACT_AND_RUN=1`. Ce n'est pas un défaut de l'AppImage : sur Bazzite, tu l'as déjà
lancée montée par FUSE (`RETOUR_BAZZITE.md`, bloc 3).

**Lancement « offscreen » : impossible, et c'est voulu.** Le greffon `offscreen` est retiré de l'AppImage
(`accio_launcher.spec:167`) ; avec `QT_QPA_PLATFORM=offscreen`, elle s'arrête : « Could not find the Qt platform
plugin "offscreen" », code 127. Lancée à la place sous Xvfb (plateforme `xcb`, celle du mode Jeu) :

- fenêtre « Accio Launcher », `WM_CLASS` = `("AccioLauncher" "AccioLauncher")` (`xwininfo -root -tree`) ;
- assistant de premier lancement affiché (choix de langue, capture prise) ;
- journal : `Accio Launcher 1.3.5 (AppImage) · Ubuntu 24.04.5 LTS · … · Python 3.15.2 · Qt 6.11.2`, puis
  « Aucun lanceur de compatibilité (umu-run, wine) trouvé » (normal : il n'y en a pas dans le conteneur).

**Taille et plafond.** Aucun test ne plafonne la **taille** de l'AppImage. Le seul plafond testé est celui de la
**glibc** (`build/linux/glibc_exigee.py`, 2.35 en release) :

| Mesure | Résultat |
|---|---|
| `glibc_exigee.py dist/AccioLauncher-x86_64.AppImage 2.35` | **refusé** : `libsndfile`, `libsystemd`, `libxcb-cursor`, `libxkbcommon` exigent GLIBC_2.38 |
| `… 2.39` | accepté : « 126 fichiers ELF, glibc exigée : 2.38 » |

C'est attendu : un build fait sur Ubuntu 24.04 prend les bibliothèques de 24.04. La release, elle, se construit
dans `ubuntu:22.04` (`release.yml`), et passe le plafond 2.35. Pour Bazzite, sans importance : sa glibc est bien
plus récente.

Tailles relevées au fil du temps : 62 Mo (release, 22.04), 67 Mo (local `uv`, 2026-10-29), 71 Mo (Bazzite,
2026-11-12), **72 Mo** ici. Ça grimpe doucement, sans garde-fou (constat C6).

**Ce que l'AppImage demande à la machine** (fermeture des `NEEDED` de tous les ELF de l'image extraite, moins ce
qu'elle embarque) : `libc`, `libm`, `libdl`, `libpthread`, `librt`, `libresolv`, `libutil`, `ld-linux-x86-64`,
`libstdc++`, `libgcc_s`, `libEGL`, `libGL`, `libdrm`, `libX11`, `libX11-xcb`, `libxcb`, `libwayland-client`,
`libwayland-cursor`, `libwayland-egl`, `libfontconfig`, `libfreetype`, `libz`, `libcom_err`, `libgpg-error`.
Tous existent sous ces noms exacts dans Fedora. `libjpeg.so.8` (nom propre à Ubuntu, Fedora a `.62`) figurait
dans la liste de PyInstaller, mais **plus rien ne la réclame** après l'élagage : pas de piège.

**Rien d'écrit hors du dossier personnel.** Après le lancement, `find / -xdev -user ludo -newer <début>` en
excluant `/home`, `/tmp`, `/proc`, `/sys`, `/dev` et `/run` ne trouve **rien**. Dans le dossier personnel, seul
`~/Games/AccioLauncher/_Launcher/logs/accio_launcher.log` est créé. Le seul ajout dans `/tmp` est l'extraction
du runtime (`appimage_extracted_*`), propre au mode `APPIMAGE_EXTRACT_AND_RUN` ; monté par FUSE, le runtime
monte dans `/tmp` sans y écrire de fichiers.

---

## 2. Tableau des constats, par priorité

Impact : **Moyen** = touche la sécurité ou la reproductibilité de la release ; **Faible** = gêne possible dans un
cas particulier ; **À vérifier** = aucune preuve de défaut, seulement un risque à lever par un essai.
Effort : **minime** (quelques lignes), **petit** (une fonction et son test).

| N° | Constat | Impact | Effort | Où | Preuve |
|---|---|---|---|---|---|
| C1 | La release installe un ruff **non vérifié par empreinte** | Moyen | minime | `build.sh:56`, `build.bat:50`, `requirements-dev.txt:11`, `.github/requirements/tests.txt:638` | `pip install -r requirements-dev.txt --dry-run` sur l'environnement haché : « Would install ruff-0.17.5 » |
| C2 | L'exe patché « 4 Go » et les INI réécrits passent en **0600** ; un lien symbolique devient un fichier | Faible | minime | `src/core/ecriture_atomique.py:37-41`, appelé par `memoire_4go.py:103`, `pre_launch.py:293`, `reglages_correctif.py:320`, `reglages_conserves.py:162`, `texte_ue1.py:563` | essai réel ci-dessous : `0755 → 0600` |
| C3 | Icône dans la barre des tâches après Gear Lever : `StartupWMClass` ≠ `app_id` Wayland | À vérifier | minime | `build/linux/be.acciolauncher.AccioLauncher.desktop:15`, `main.py:17` et `:214` | SUPPOSÉ (voir détail) |
| C4 | Manette dans le launcher sous Linux jamais essayée boutons pressés ; Steam Deck sans Steam : pas de `/dev/input/js*` | À vérifier | — | `src/core/manette_lecture.py:351`, `:378` | `RETOUR_BAZZITE_PASSAGES_1_A_6.md:247` et `:414` « manette non essayée » |
| C5 | La désinstallation du launcher laisserait l'entrée de menu créée par Gear Lever | Faible | petit | `src/core/desinstallation.py:61` (`programme_courant`) | SUPPOSÉ (Gear Lever non installé ici) |
| C6 | Aucun test ne plafonne la taille de l'AppImage | Faible | minime | `build/linux/appimage.py:172` | 62 → 67 → 71 → 72 Mo |
| C7 | `mypy --platform linux` ne vérifie que `src/core` ; `src/ui` et `main.py` échappent à la passe Linux | Faible | — | `pyproject.toml:85-86` | passe ponctuelle sur `src/ui` + `main.py` : 1 seule alerte de plateforme, fausse (voir § 3.6) |

### C1 — La release installe un ruff non vérifié

**En clair** : la release vérifie l'empreinte de chaque paquet installé, puis `build.sh` réinstalle « par-dessus »
depuis une liste sans empreintes. Comme cette liste demande un ruff plus récent que celui qui est verrouillé, pip
va chercher la dernière version sur PyPI. Ruff ne part pas dans l'AppImage (c'est un outil de vérification), donc
**rien de ce qui est publié n'est touché aujourd'hui**. Mais le principe « la release n'embarque que ce que la CI a
testé » ne tient plus que par chance : le jour où un plancher de `requirements.txt` (PyQt6…) dépasse le fichier
verrouillé, c'est un paquet **embarqué** qui viendra de PyPI sans vérification. Et la CI (`tests.yml`, ruff 0.17.3)
ne lint plus avec le même ruff que la release (0.17.5) : une release peut échouer sur un lint que la CI n'a pas vu.

Preuves :

- `pyproject.toml:23` et `requirements-dev.txt:11` : `ruff>=0.17.4` (commit `1adad44`, « update ruff version
  to 0.17.4 in dependencies ») ; `.github/requirements/tests.txt:638` : `ruff==0.17.3` (pas regénéré).
- `build.sh:56` (et `build.bat:50`) exécutent `pip install -r requirements-dev.txt` **sans condition**, même
  avec `ACCIO_PY` posé par `release.yml`.
- Simulation sur l'environnement haché : `pip install -r requirements-dev.txt --dry-run` → « Would install
  ruff-0.17.5 ». `.venv-build` du build réel : `ruff 0.17.5`.
- Le commentaire de `.github/workflows/release.yml:114-115` (« Le `pip install` de build.bat trouve ensuite tout
  déjà satisfait et n'y touche plus ») est donc faux aujourd'hui.

Correctif proposé (non appliqué) :

```diff
--- a/build.sh
+++ b/build.sh
@@
-"$PY" -m pip install -r requirements-dev.txt --quiet || echec "installation des dépendances échouée."
+# En release (ACCIO_PY), les paquets viennent de tests.txt, vérifiés par empreinte : ne rien réinstaller.
+if [ -z "${ACCIO_PY:-}" ]; then
+    "$PY" -m pip install -r requirements-dev.txt --quiet || echec "installation des dépendances échouée."
+fi
```

Même garde dans `build.bat:50` (`if not defined ACCIO_PY …`), puis regénérer `.github/requirements/tests.txt`
(ruff ≥ 0.17.4). Filet suggéré : un test qui vérifie que chaque plancher de `requirements-dev.txt` est satisfait
par la version épinglée dans `tests.txt`.

### C2 — Les fichiers réécrits passent en 0600

**En clair** : pour réécrire un fichier sans risque de le laisser à moitié écrit, le launcher écrit une copie
temporaire puis la met à la place de l'original. Cette copie naît avec des droits « moi seul » (0600), et ces
droits remplacent ceux de l'original. Pour toi, seul utilisateur de ta machine, **aucune conséquence visible** :
Wine et Proton ouvrent l'exe en lecture, ils n'ont pas besoin du droit d'exécution. D'ailleurs le drapeau 4 Go
existe depuis le 2026-10-26, et tu as joué HP1 à HP6 par JOUER le 2026-11-12 : leurs exes étaient donc déjà en
0600 (déduit, pas relevé). Ça gênerait un second compte sur le même PC, une bibliothèque de jeux partagée, ou un
outil de sauvegarde qui préserve les droits.

Essai réel (utilisateur normal, `umask 022`, vrai `memoire_4go.poser` sur un exe PE 32 bits fabriqué) :

```
avant 0o755 drapeau False
poser -> True
apres 0o600 drapeau True
lien encore symlink ? False cible drapeau False
lien dur: orig drapeau False dur True
```

- Un exe installé par 7-Zip naît en `644` (essai : `7zzs x` d'une archive fabriquée, `umask 022`) ; après le
  premier JOUER, il est en `600`.
- Si l'exe est un **lien symbolique** (jeu rangé ailleurs et relié), le lien est remplacé par un fichier
  ordinaire, et la vraie cible n'est **pas** patchée. Un **lien dur** est séparé de son jumeau.
- Même mécanisme pour les INI des jeux (`pre_launch.py:293`), le `d3d9.ini` du correctif
  (`reglages_correctif.py:320`), les réglages conservés et les `.int` regravés de UE1.

Correctif proposé (non appliqué) :

```diff
--- a/src/core/ecriture_atomique.py
+++ b/src/core/ecriture_atomique.py
@@ def ecrire_octets_atomique(chemin: Path, octets: bytes, suffixe: str = ".tmp") -> None:
-    fd, tmp = tempfile.mkstemp(dir=chemin.parent, suffix=suffixe)
+    chemin = Path(os.path.realpath(chemin))   # un lien : écrire sa cible, garder le lien
+    fd, tmp = tempfile.mkstemp(dir=chemin.parent, suffix=suffixe)
     try:
         with os.fdopen(fd, "wb") as f:
             f.write(octets)
+        with contextlib.suppress(OSError):    # mkstemp crée en 0600 : reprendre les droits d'origine
+            os.chmod(tmp, stat.S_IMODE(os.stat(chemin).st_mode))
         os.replace(tmp, chemin)
```

(`import stat` en tête.) Sous Windows, `os.chmod` ne touche que la lecture seule : sans effet sur le comportement
actuel. À garder tel quel pour `ecrire_atomique` (config, statistiques) : 0600 y est plutôt une qualité. Test
sentinelle : un fichier en 0755 reste en 0755 après `memoire_4go.poser`, test gardé `skipif win32`.

### C3 — L'icône après intégration par Gear Lever (SUPPOSÉ)

Sous Wayland, Qt annonce la fenêtre sous l'identifiant `be.acciolauncher.AccioLauncher` (`main.py:17`, `:214`).
Le `.desktop` de l'AppImage porte ce nom, donc tant qu'il garde ce nom, KDE fait le lien. Mais
`StartupWMClass=AccioLauncher` (`.desktop:15`) ne correspond **pas** à cet identifiant : si Gear Lever renomme le
`.desktop` en l'intégrant (SUPPOSÉ : non vérifié ici, Gear Lever n'est pas installable dans le conteneur), KDE
n'a plus rien pour relier la fenêtre à son icône, et affiche une icône générique. `WM_CLASS` mesuré sous X11 :
`AccioLauncher`, ce qui explique la valeur actuelle.

À trancher par l'essai 4 (§ 5). S'il échoue, correctif d'une ligne : `StartupWMClass=be.acciolauncher.AccioLauncher`
(le bureau de Bazzite est en Wayland ; en mode Jeu, Steam ne se sert pas du `.desktop`).

### C4 — La manette dans le launcher (À vérifier)

`manette_lecture.LecteurLinux` lit `/dev/input/js*` (`manette_lecture.py:378`). Deux inconnues :

- la navigation du launcher à la manette n'a jamais été essayée **sous Linux** avec des boutons pressés : en jeu,
  la manette a été « vue par winmm… ; boutons non pressés » (`RETOUR_BAZZITE_PASSAGES_1_A_6.md:144`), et le bloc
  manette est noté « Non fait » / « manette non essayée » (`:247`, `:414`). L'essai DS4 du 2026-10-07 décrit dans
  `ARCHITECTURE_CORE.md` a eu lieu sous Windows (SUPPOSÉ : le texte ne nomme pas le système, mais il parle de la
  barre de titre maison et de winmm) ;
- sur un Steam Deck ou une console portable, les commandes intégrées ne créent un `/dev/input/js*` que lorsque
  Steam tourne (Steam Input) (SUPPOSÉ). Sans Steam ouvert, le launcher ne verrait aucune manette, sans message.

Le code ne plante pas dans ce cas : sans `js*`, `LecteurLinux` ne rend rien. Essai 6 (§ 5).

### C5 — Désinstaller le launcher après Gear Lever (SUPPOSÉ)

`desinstallation.programme_courant()` efface `$APPIMAGE` et `_Launcher/` (préfixes et copies gardés), rien d'autre.
Une AppImage intégrée par Gear Lever laisse un `.desktop` et une icône dans `~/.local/share/` (SUPPOSÉ) : l'entrée
« Accio Launcher » resterait dans le menu, pointant vers un fichier effacé. Pas d'essai demandé (destructif) ;
piste : la boîte de désinstallation pourrait le dire (« retirez aussi l'entrée dans Gear Lever »).

### C6 — Pas de plafond de taille

Proposition, dans `build/linux/appimage.py` juste après l'affichage de la taille (ligne 172) :

```diff
+    if sortie.stat().st_size > 90 * 1024 ** 2:
+        raise SystemExit("AppImage de plus de 90 Mo : une bibliothèque inattendue est embarquée ?")
```

90 Mo laisse la marge d'un build local par `uv` (72 Mo ici) ; la release (62 Mo) est loin dessous.

### C7 — La passe Linux de mypy ne voit pas l'interface

`pyproject.toml:85-86` : `platform = "win32"`, `files = ["src/core"]`. Une passe ponctuelle
(`mypy --platform linux --follow-imports=silent main.py src/ui`, hors réglage strict, 789 erreurs ordinaires de
typage non annoté) ne donne qu'**une** alerte de plateforme : `src/ui/process_monitor.py:39`,
`subprocess.CREATE_NO_WINDOW`… qui est déjà gardé par `if sys.platform == "win32" else 0`. Rien à corriger
aujourd'hui ; c'est la relecture du § 3.6 qui couvre `src/ui`, pas un outil.

---

## 3. Relecture de la voie Linux

### 3.1 Lancement par umu-run, Proton ou Wine

- **Détection** (`src/core/compat.py:146-170`) : `umu-run`, puis `wine`, puis `wine64`, chemin toujours
  **absolu** (`_trouver`, `:87-98`) ; recherche aussi dans `~/.local/bin`, `/usr/local/bin`, `/usr/bin` quand le
  PATH de la session graphique ne les donne pas. `ACCIO_COMPAT=umu|wine` force une famille. `lanceur()` rend
  `None` sous Windows (`:181`). Conforme à `LINUX.md` § 4.1.
- **Proton** (`:100-143`) : GE-Proton puis UMU-Proton, cherchés dans `Steam/compatibilitytools.d` (natif et
  Flatpak), `umu/compatibilitytools`, `~/.steam/root/…` ; tri numérique (`GE-Proton10-15` après `9-27`). Un
  `PROTONPATH` de l'utilisateur est respecté (`:163`).
- **Environnement** (`:747-781`) : `WINEPREFIX`, `ACCIO_LAUNCH=1`, `GAMEID=umu-default`, `WINEDLLOVERRIDES` en
  `n,b` qui respecte une surcharge de l'utilisateur, `DXVK_CONFIG` avec `d3d9.ffUbershaderVS = False` (gel du GPU
  Intel), `UMU_RUNTIME_UPDATE=0` hors vérification hebdomadaire ou hors ligne. `LD_LIBRARY_PATH` de l'AppImage
  retiré pour les enfants (`environnement_hote`, `:701-727`).
- **Surveillance** (`:852-885`) : `/proc`, même utilisateur, même préfixe (comparaison des chemins résolus,
  `pfx → .` d'umu compris).

Rien d'anormal à la lecture. Le lancement réel des jeux n'est vérifiable que chez toi (vu : HP1 à HP6 le
2026-11-12, HP7a/HP7b le 2026-10-20, `ETAT_DES_PHASES.md` § 9).

### 3.2 Préfixes

Un préfixe partagé par famille : `~/Games/AccioLauncher/_Launcher/prefixes/umu|wine` (`compat.py:288-297`).
Profil `steamuser` pour umu, sinon le seul profil présent, sinon le nom Unix (`:316-334`). Chemins hôte → Windows :
`C:\…` dans `drive_c`, puis le lecteur de `dosdevices` le plus proche (le `X:` que Proton relie au dossier
personnel), sinon `Z:\…` ; le cas Bazzite `/home` → `/var/home` est traité par comparaison des chemins résolus
(`:350-404`). La désinstallation du launcher **garde** les préfixes (ils contiennent les sauvegardes,
`desinstallation.py:78-81`).

### 3.3 Registre Wine (`game_registry.disponible()`)

`game_registry.py:65-81` : `True` sous Windows ; sous Linux, seulement si un lanceur **et** un préfixe initialisé
(`system.reg` + `drive_c`) existent. Lecture : texte des `.reg`, sans lancer Wine (`compat.lire_valeurs`) ;
redirection `WOW6432Node` pour HKLM 32 bits sur préfixe `win64`. Écriture : `.reg` UTF-16 déposé dans
`drive_c/windows/temp`, importé par `regedit /S` via le lanceur, sans vérification hebdomadaire du runtime
(`:364-380`). Les caractères de contrôle sont refusés avant d'écrire un `.reg`. Conforme.

### 3.4 Casse des noms de fichiers

`src/core/sans_casse.py` cherche sans tenir compte de la casse, avec un cache invalidé par la date du dossier. Il
sert au folio et à l'encyclopédie (`folio*.py`, `encyclopedie.py:126`). Les autres lectures de fichiers du jeu
sans casse ont leur propre boucle, insensible elle aussi : `fichiers_essentiels.py:40`, `cinematiques.py:202` et
`:241`, `phonographe.py:89`, `config_cassee.py:70`, `sons_cartes_hp4.py:183`, `archives_ea.py:86`. Aucune
recherche sensible à la casse trouvée sur un nom fixé à la main. Les chemins du catalogue (exe, INI) sont pris
tels qu'écrits : ils ont tenu sur Bazzite pour les huit jeux (relevé, `RETOUR_BAZZITE.md`).

### 3.5 Droits des fichiers

Voir C2 : vérifié pour de vrai, `0755 → 0600`. L'auto-mise à jour, elle, remet bien `0755` sur la nouvelle AppImage
(`self_update.py:328`). Le 7-Zip embarqué est en `-rwxr-xr-x` dans le dépôt (`assets/7z/linux/7zzs`) et
`_find_7z_linux` vérifie `os.access(…, X_OK)` avant de s'en servir.

### 3.6 Appels propres à Windows : tous gardés

Recensement (`grep` de `windll`, `WinDLL`, `winreg`, `ShellExecute`, `CREATE_NO_WINDOW`, `DETACHED_PROCESS`,
`os.startfile`, `msvcrt`, `wintypes`) : 21 modules de `src/core`, `src/ui/process_monitor.py`, `main.py`.

- `src/core` : la passe `mypy --platform linux` (stricte) est propre ; elle signalerait un `ctypes.windll` ou un
  `winreg` hors garde (typeshed ne les définit que pour win32).
- `src/ui` : un seul usage, `process_monitor.py:39`, gardé par `if sys.platform == "win32" else 0` ; le repli
  Linux (`/proc`) est en `:135`.
- `main.py:179-182` : `SetCurrentProcessExplicitAppUserModelID` sous `if sys.platform == "win32"` ; le pendant
  Linux est `setDesktopFileName` (`:214`).
- `extractors.find_7z_exe` (`:103-104`) : sous Linux, part directement vers `_find_7z_linux` ; les chemins
  `C:\Program Files\…` ne sont atteints que sous Windows.

Aucun appel win32 sans garde, et chaque garde a un repli Linux qui fait quelque chose d'utile (ou rien, quand il
n'y a rien à faire : `Zone.Identifier`, barre des tâches).

### 3.7 7-Zip Linux embarqué

`assets/7z/linux/7zzs` : ELF 64 bits **statique** (`file`), « 7-Zip (z) 26.00 (x64) ». Choisi avant tout 7-Zip du
système (`extractors.py:125-134`), puis `7zz`, `7z`, `7za` par chemin absolu ; jamais py7zr. Extraction avec
`-snl-` (aucun lien symbolique matérialisé, `:362-364`). Progression découpée sur les retours arrière.

### 3.8 Discord sous Linux et sous Flatpak

`discord_presence.dossiers_ipc` (`:96-123`) : `$XDG_RUNTIME_DIR`, puis `app/com.discordapp.Discord` (Flatpak),
`app/com.discordapp.DiscordCanary`, `.flatpak/dev.vencord.Vesktop/xdg-run`, `snap.discord`, puis `/tmp` (connexion
seulement). Délai de 2 s par tentative, sockets fermés en cas d'échec. Logique correcte ; **jamais essayé avec un
vrai Discord Flatpak** (`LINUX.md:423-424`) → essai 7.

### 3.9 Dossiers utilisateur

`config.py:76-94` : jeux dans `~/Games/AccioLauncher`, tout le reste dans `_Launcher/` à chemin **fixe** (même si
les jeux sont installés ailleurs), sauf le cache qui suit l'emplacement des jeux. Les variables XDG servent là où
elles ont un sens : `XDG_DATA_HOME` pour umu et Proton (`compat.py:107`, `:210`), `XDG_RUNTIME_DIR` pour Discord,
`QStandardPaths` pour Images, Musique, Bureau. La config n'est **pas** sous `~/.config` : choix délibéré (règle
d'arborescence de `CLAUDE.md`), pas un oubli.

### 3.10 Système immuable

Mesuré au § 1 : rien d'écrit hors du dossier personnel. Recensement du code : les seuls chemins absolus hors
`$HOME` sont **lus** (`/proc`, `/sys/class/drm`, `/sys/class/hidraw`, `/dev/input`, `/usr/share/hwdata/pci.ids`)
ou servent à **chercher** des programmes (`/usr/bin`, `/usr/local/bin`,
`/usr/share/steam/compatibilitytools.d`). Les dossiers temporaires du registre sont **dans le préfixe**
(`game_registry.py:371-373`). Rien n'appelle `rpm-ostree`, `sudo` ni `pkexec`. Conforme.

### 3.11 AppImage sur Bazzite : FUSE et intégration au bureau

- **FUSE** : runtime `type2-runtime` 20251108 statique, épinglé par empreinte (`appimage.py:53`) ; pas de
  `libfuse2` requis. Il lui faut `fusermount3`, présent sur Bazzite (tu l'as lancée montée). Rien de neuf ici.
- **Bureau** : `.desktop` valide (`desktop-file-validate` en phase 4), `app_id` Wayland
  `be.acciolauncher.AccioLauncher`. L'AppImage ne s'intègre pas seule au menu : c'est le rôle de Gear Lever, que
  Bazzite **n'installe pas d'office** : sa documentation dit que Gear Lever « you can install in Bazaar »
  (<https://docs.bazzite.gg/Installing_and_Managing_Software/AppImage/>, consultée le 2026-11-17). Voir C3 et C5.
- **Risque à surveiller** : dans le ticket ublue-os/bazzite#2338, un mainteneur répond qu'ils garderont Gear Lever
  « until at which time we can remove all appimage support permanently » et recommande Flatpak et distrobox
  (<https://github.com/ublue-os/bazzite/issues/2338>). Aucun retrait n'est annoncé ; c'est une raison de garder
  la piste Flatpak (`LINUX.md` § 4.8) en vue.

---

## 4. Phrases fausses ou périmées dans les docs

| Où | Ce qui est écrit | Ce qui est vrai | Preuve |
|---|---|---|---|
| `.github/workflows/release.yml:114-115` (commentaire, repris pour le job Linux à `:301`) | « Le `pip install` de build.bat trouve ensuite tout déjà satisfait et n'y touche plus. » | **Faux depuis `1adad44`** : il installe ruff 0.17.5 par-dessus le 0.17.3 haché | C1, `--dry-run` |
| `docs/LINUX.md:423` (§ 10) | « Wayland et manette sont vus depuis sur Bazzite » | **Trop fort pour la manette** : vue par le jeu sans bouton pressé ; la navigation du launcher à la manette sous Linux n'a jamais été essayée | `RETOUR_BAZZITE_PASSAGES_1_A_6.md:144`, `:247`, `:414` |
| `docs/linux/ETAT_DES_PHASES.md` § 9 (« `./build.sh` : icône → lint → tests → … ») | la chaîne des étapes | **Incomplet** : omet l'installation sans empreinte de `requirements-dev.txt` qui précède tout (`build.sh:56`) — c'est elle qui fait C1 | `build.sh:54-56` |
| `docs/linux/ETAT_DES_PHASES.md` § 9 et `build/linux/appimage.py:45` | « appimagetool 1.9.1 » | **Exact mais trompeur** : le binaire de la release 1.9.1 se présente comme « continuous build (git version 8c8c91f), build 296 built on 2025-12-04 ». L'empreinte épinglée, elle, fait foi | sortie de `build.sh` |
| `docs/linux/MISSION_BAZZITE.md:236` | « les ~26 tests sautés sous Windows » | **Périmé** : 34 sautés sous Windows au 2026-11-17 | `CLAUDE.md`, `docs/claude/TESTS.md:7` |
| `docs/linux/MISSION_PORTABLE.md:105` | « sous Windows, 3331 réussis et 30 sautés » | **Périmé** : 5009 réussis, 34 sautés | idem |
| `CLAUDE.md` (Commands) | « `python -m mypy --platform linux` — les branches Linux » | **Incomplet** : seulement celles de `src/core` (`pyproject.toml:86`) | C7 |
| `docs/LINUX.md` § 2.4 (Discord) et `ETAT_DES_PHASES.md` § 8 | « sockets natifs, Flatpak et Snap » | **Incomplet** : le code cherche aussi Discord Canary et Vesktop | `discord_presence.py:114-120` |

Vérifié **juste** (pour éviter de le reverifier) : 7-Zip 26.00 statique (§ 8) ; `LD_LIBRARY_PATH` retiré pour les
enfants (§ 8) ; `strip=True` sous Linux (§ 9, `accio_launcher.spec:313`, `:322`) ; Gear Lever absent de l'image
de Bazzite (§ 4.8, documentation de Bazzite ci-dessus) ; `_Launcher/prefixes/umu|wine` (§ 4.2) ; Xvfb, sinon le
premier affichage de `/tmp/.X11-unix` pour l'audit de géométrie (§ 9, `build.sh`) ; « 30 tests Linux » sautés
sous Windows (cohérent avec le total, § 1).

---

## 5. À essayer sur ta machine Bazzite

Ce qui ne se vérifie qu'avec les jeux, un vrai écran et ton matériel. Chaque essai : le geste exact, puis ce que
tu dois voir. Prends l'AppImage du prochain brouillon de release (ou de `./build.sh`).

1. **Droits de l'exe après JOUER (confirme C2)**
   Geste : lance HP4 par JOUER, quitte-le, puis dans un terminal :
   `find ~/Games/AccioLauncher -iname '*.exe' -mmin -15 -exec stat -c '%a %n' {} +`
   Attendu aujourd'hui : `600` devant l'exe de HP4 (le constat), **et** HP4 a bien démarré. Si tu vois `644` ou
   `755`, C2 est faux chez toi : dis-le.

2. **HP7a avec le drapeau 4 Go sous Proton**
   Geste : JOUER sur HP7 partie 1, aller jusqu'au menu du jeu, quitter. Puis
   `grep "4 Go" ~/Games/AccioLauncher/_Launcher/logs/accio_launcher.log | tail -2`
   Attendu : le jeu démarre comme avant, et une ligne « 4 Go : drapeau posé sur … » (ou rien, si le drapeau était
   déjà posé). Rien de neuf n'a été lancé sous Wine avec ce drapeau depuis tes essais (2026-10-26 : SUPPOSÉ sous
   Windows).

3. **Le compte des tests chez toi**
   Geste : `./build.sh` depuis le dépôt à jour.
   Attendu : `code 0`, et à l'étape 3/6 « 4995 passed, 48 skipped » (ou 4996/47 si le dépôt
   `accio-launcher-games` est à côté). Et dans `.venv-build`, `python -m ruff --version` → **0.17.5** : c'est C1.

4. **Gear Lever et l'icône (tranche C3)**
   Geste : installer Gear Lever depuis Bazaar, ouvrir l'AppImage avec lui, « Déplacer vers le menu des
   applications », lancer « Accio Launcher » depuis le menu, regarder la barre des tâches.
   Attendu : l'icône dorée d'Accio, pas une icône générique. Si elle est générique, envoie la sortie de
   `ls ~/.local/share/applications | grep -i accio` : le correctif d'une ligne est prêt (C3).

5. **Le vrai mode Jeu**
   Geste : en mode Bureau, Steam → « Ajouter un jeu non-Steam » → l'AppImage ; passer en mode Jeu, lancer Accio
   Launcher, puis JOUER sur HP1, quitter HP1.
   Attendu : la fenêtre du launcher s'affiche en plein écran ; la manette déplace le focus ; HP1 démarre ; à sa
   fermeture, le launcher revient au premier plan (pas d'écran noir). Note ce qui se passe à chaque étape.

6. **La manette dans le launcher, en mode Bureau (tranche C4)**
   Geste : brancher la DS4 en USB, Steam **fermé** ; `ls -l /dev/input/js*` ; ouvrir le launcher, appuyer sur
   la croix ← / →, puis sur ✕.
   Attendu : au moins un `/dev/input/js0` lisible par toi ; ← / → changent de jeu dans le carrousel, ✕ ouvre la
   fiche. Puis recommencer **Steam ouvert** : un seul déplacement par appui (pas deux).

7. **Discord en Flatpak**
   Geste : ouvrir Discord (Flatpak) ; `ls $XDG_RUNTIME_DIR/app/com.discordapp.Discord/` ; dans le launcher,
   Paramètres → activer la présence Discord ; JOUER sur un jeu.
   Attendu : `discord-ipc-0` listé ; ton profil Discord affiche « Accio Launcher » et le jeu en cours.

---

## 6. Limites de cet audit

- Conteneur **Ubuntu 24.04**, pas Fedora : les noms de bibliothèques ont été comparés à Fedora par leur nom
  (`soname`), pas chargés sur un vrai Fedora.
- Ni umu, ni Proton, ni Wine, ni GPU, ni manette, ni Discord, ni session Wayland, ni Gear Lever ici : tout ce qui
  en dépend est soit relu dans le code, soit repris de tes relevés (cités), soit marqué SUPPOSÉ.
- FUSE refusé à l'utilisateur normal dans le conteneur : l'AppImage a été lancée par extraction
  (`APPIMAGE_EXTRACT_AND_RUN=1`), sous Xvfb (`xcb`), jusqu'à l'assistant de premier lancement seulement.
- Le build local n'est pas comparable au Mo près à la release (Python de `uv` contre celui de `setup-python`,
  Ubuntu 24.04 contre 22.04).
