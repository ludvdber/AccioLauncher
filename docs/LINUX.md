# Accio Launcher sous Linux — audit et plan

Objectif : un launcher **natif Linux**, utilisable d'abord sur **Bazzite** (Fedora
Atomic, immuable, orienté jeu), publié à chaque release à côté de l'exe Windows.

Ce document est l'audit de la phase 1 : tout ce qui, dans le code du 2026-09-24,
suppose Windows, avec son emplacement, ce que ça donne aujourd'hui sous Linux et
ce qui est prévu. Il restera le document de référence du portage : les phases
suivantes le complètent au lieu d'en ouvrir un autre.

**Règle absolue du portage : le comportement Windows ne change pas.** Tout code
Linux passe derrière `sys.platform` avec un repli sensé, sur le patron déjà en
place (`game_registry.disponible`, `win_utils`, `system_checks`).

---

## 1. Le point clé : le launcher est natif, les jeux restent des `.exe`

Les huit jeux sont des programmes Windows 32 bits de 2001-2011. Sous Linux, le
launcher ne les lance pas lui-même : il passe par une **couche de
compatibilité** — `umu-run` (Proton hors de Steam) de préférence, sinon le
`wine` du système.

Conséquence qui structure tout le reste : **le « Windows » des jeux est un
préfixe Wine.** Leur dossier Documents, leur AppData, leur registre et leurs
runtimes Visual C++ vivent dans ce préfixe, pas dans le `$HOME` de
l'utilisateur. Tout le code qui écrit « chez Windows » pour un jeu (INI de
Documents, sauvegardes, registre, prérequis) doit viser le préfixe.

---

## 2. Audit : ce qui suppose Windows

Emplacements relevés sur `main` au 2026-09-24 (`fichier:ligne`). La colonne
« Aujourd'hui sous Linux » dit ce qui se passe **sans** portage ; « Phase » dit
quelle pull request le traite.

### 2.1 Lancement d'un jeu — le cœur du portage

| Emplacement | Ce qui suppose Windows | Aujourd'hui sous Linux | Traitement | Phase |
|---|---|---|---|---|
| `src/core/game_manager.py:335` | `Popen([exe])` : le `.exe` est exécuté directement | `OSError: Exec format error` — aucun jeu ne démarre | Passer par le lanceur de compatibilité (`umu-run <exe>` / `wine <exe>`) | 2 |
| `src/core/game_manager.py:321-326` | Drapeaux `DETACHED_PROCESS` / `CREATE_NEW_PROCESS_GROUP` | Déjà gardés (`start_new_session`) | Conservé ; sorties du lanceur vers un journal par jeu | 2 |
| `src/core/game_manager.py:283` + `src/core/system_checks.py:83-97, 139-156` | Prérequis VC++ testés dans WinSxS et le registre Windows | Les trois tests rendent `True` : **rien n'est vérifié**, un préfixe sans runtime passe | Tester le **préfixe** ; installer par winetricks | 2 |
| `src/core/system_checks.py:78-79` | `C:\Windows` en repli de `%SystemRoot%` | Chemin inexistant (jamais atteint, les tests sont gardés) | Inchangé (gardé) | — |
| `src/core/system_checks.py:159-193` | `check_d3d11_feature_level` crée un device D3D11 par ctypes | Rend `False` : **tout `fallback` d'INI s'activerait**, vers un renderer que HP1/HP2 ne livrent pas (cf. CLAUDE.md) | Rendre `True` hors Windows : sous Wine, D3D11 vient de DXVK / wined3d, pas du pilote | 2 |
| `src/core/pre_launch.py:34` | `_INI_ENCODING = "mbcs"` sous Windows, `utf-8` ailleurs | Les INI du moteur sont écrits par le jeu **sous Wine**, donc dans la page ANSI du préfixe, pas en UTF-8 | Lire la page ANSI du préfixe (`Nls\Codepage\ACP` dans `system.reg`) | 2 |
| `src/core/pre_launch.py:94-111` (`substitute_vars`) | Les VALEURS d'INI (`SavePath=%DOCUMENTS%\Harry Potter\Save`) deviennent des chemins de l'hôte | Le jeu lirait `SavePath=/home/…/Documents/…` : un chemin Unix dans un INI Windows, qui ne tombe juste que si le lecteur courant est `Z:` | Distinguer le chemin du FICHIER (hôte) de la VALEUR écrite (chemin Windows : `C:\users\steamuser\Documents\…`, `Z:\home\…`) | 2 |
| `src/core/pre_launch.py:304-330` (`env_de_lancement`) | `__COMPAT_LAYER=HighDpiAware`, couche de compatibilité Windows | Rend déjà `None` hors Windows | Ignoré proprement sous Wine (aucune notion équivalente) ; l'environnement Wine est composé à part | 2 |
| `src/core/config.py:14-32` (`get_documents_dir`) | `SHGetFolderPathW`, puis `~/Documents` hors Windows | Pointe le Documents **de l'hôte** : HP1-HP3 y trouveraient leurs INI patchés… que le jeu, sous Wine, ne lit pas | Documents **du préfixe** (`drive_c/users/<profil>/Documents`) | 2 |
| `src/core/post_install.py:33` | « Saved Games » sous le dossier personnel | Idem : hors du préfixe | Racines du préfixe | 2 |
| `src/core/post_install.py:122-132` (`destination_config`) | `~/Documents/…` du catalogue → Documents de l'hôte | Config livrée copiée au mauvais endroit | Suit `get_documents_dir` (préfixe) | 2 |
| `src/core/sauvegardes.py:77-96` (`racines`) | `LOCALAPPDATA` | `None` : HP5-HP7b n'ont **aucune** sauvegarde relevée ; Documents de l'hôte pour HP1-HP3 | Documents et `AppData/Local` du préfixe — le module l'annonçait déjà comme « le SEUL endroit à changer » | 2 |
| `src/core/game_registry.py:52-65` (`disponible`) | Registre = `winreg` | `False` : sélecteur de langue éteint, **`Install Dir` jamais écrit** — or HP7a/HP7b ne démarrent pas sans lui | `True` quand un lanceur et un préfixe existent | 2 |
| `src/core/game_registry.py:182-206` (`lire_valeurs`) | `winreg.OpenKey` | Rend `{}` | Lire `system.reg` / `user.reg` du préfixe (texte, sans lancer Wine) | 2 |
| `src/core/game_registry.py:239-286` (`_ecrire_direct`, `_ecrire_eleve`) | `winreg` puis `ShellExecuteW("runas", "regedit.exe")` + UAC | Jamais atteint (`ecrire_valeurs:323` rend `False`) | `_ecrire_eleve` = import du `.reg` par `regedit /S` **dans le préfixe**, via le lanceur ; pas d'UAC, mais la prévenance reste | 2 |
| `src/core/game_language.py:105, 182` | Portes `disponible()` | Aucune langue, aucune écriture | Rien à changer : elles s'ouvrent quand `disponible()` dit vrai | 2 |
| `src/ui/process_monitor.py:68` | Nom d'exe pris dans `process.args[0]` | Sous Linux ce serait `umu-run` ou `wine` | Chercher l'argument en `.exe` | 2 |
| `src/ui/process_monitor.py:84-100` (`_is_exe_running`) | `tasklist.exe` pour suivre la relance UE1 | Rend `False` : la relance de HP1/HP2 au chargement d'une sauvegarde **terminerait la session** au bout de 10 s | Équivalent `/proc` (processus Wine de même nom, même utilisateur, même préfixe), même grâce de 10 s | 2 |
| `src/core/win_utils.py:11-24` | `System32`, `C:\Windows` | Gardé | Inchangé | — |
| `src/ui/game_detail_handlers.py:117-130` | « registre de **Windows** », invite UAC | Jamais affiché | Texte Linux : registre **du préfixe Wine**, sans UAC ; même prévenance | 2 |
| `src/ui/game_detail_handlers.py:221-236` | « Composant **Windows** manquant » → page Microsoft ; « Sécurité Windows » pour Documents | Jamais atteint | Proposer l'installation dans le préfixe ; message Documents propre à Linux | 2 |
| `src/ui/game_detail_handlers.py:535-537` | « autorisation administrateur » | Jamais atteint | Texte Linux | 2 |
| `src/ui/alert_banner.py:52-54, 155-162, 310-316` | Bandeau « Visual C++ manquant » → page Microsoft | Jamais affiché (tests à `True`) | Lien « Installer » qui prépare le préfixe ; bandeau « Wine introuvable » | 2 |
| `src/core/game_data.py` | Aucune notion de surcharge de DLL | Wine charge **son** `d3d9` au lieu de celui livré (vérifié, §3) | Champ de catalogue `dll_overrides`, validé au parsing | 2 |

### 2.2 Installation, extraction

| Emplacement | Ce qui suppose Windows | Aujourd'hui sous Linux | Traitement | Phase |
|---|---|---|---|---|
| `src/core/extractors.py:77-102` (`find_7z_exe`) | `7z.exe` embarqué, puis `C:\Program Files\7-Zip` | Repli sur `shutil.which("7z")` : dépend de ce que l'utilisateur a installé ; sur Bazzite, rien de garanti | Embarquer le **7-Zip officiel Linux** (`7zz`), repli `7zz`/`7z` du système (jamais py7zr, règle 92) | 3 |
| `src/core/extractors.py:114-115, 198-199` | `CREATE_NO_WINDOW` | Déjà gardé | Inchangé | — |
| `src/core/post_install.py:101` + `src/core/win_utils.py:48-67` | `Zone.Identifier` (flux NTFS) | No-op, sans objet sous Linux | Inchangé | — |
| `accio_launcher.spec:83-88, 212-236` | Onefile Windows, ressource de version, `.ico`, `7z.exe` embarqué partout | Un build Linux embarquerait 7z.exe/7z.dll pour rien | Spec par plateforme : onedir Linux, sans binaires Windows | 4 |

### 2.3 Mise à jour du launcher

| Emplacement | Ce qui suppose Windows | Aujourd'hui sous Linux | Traitement | Phase |
|---|---|---|---|---|
| `src/core/self_update.py:20-22` (`can_self_update`) | Exe gelé **Windows** | `False` : la mise à jour ouvre la page de release | AppImage : remplacer `$APPIMAGE` | 3 |
| `src/core/self_update.py:57-129` | `.bat` qui attend la mort du processus | — | Script `/bin/sh` détaché, chemins par l'environnement (même principe que les `%ACCIO_*%`) | 3 |
| `src/core/self_update.py:178-185` (`relaunch_after_exit`) | Hors Windows : `Popen([sys.executable, *argv])` **immédiat** | Deux défauts : la nouvelle instance démarre avant la mort de l'ancienne et bute sur l'instance unique ; dans une AppImage, `sys.executable` vit dans un montage qui disparaît avec le processus | Attendre la mort du PID puis relancer `$APPIMAGE` | 3 |
| `src/core/updater.py:485` | Asset de mise à jour = le premier `.exe` | Un launcher Linux téléchargerait l'exe Windows | Choisir l'asset de SA plateforme (`.AppImage`) | 3 |
| `src/ui/update_dispatcher.py:234` | Fichier téléchargé nommé `AccioLauncher_v….exe` | — | Nom selon la plateforme | 3 |
| `src/core/self_update.py:25-41` (`_clean_pyinstaller_env`) | Purge les `_PYI_*` | Sous Linux, le chargeur de PyInstaller **modifie `LD_LIBRARY_PATH`** : tout processus enfant (umu, wine, xdg-open, le navigateur) chargerait les bibliothèques embarquées | Restaurer `LD_LIBRARY_PATH` d'origine au démarrage (mode gelé Linux) | 3 |

### 2.4 Intégrations et confort

| Emplacement | Ce qui suppose Windows | Aujourd'hui sous Linux | Traitement | Phase |
|---|---|---|---|---|
| `src/core/discord_presence.py:58-80` (`_open_ipc`) | Tube nommé Windows ; socket Unix dans `$XDG_RUNTIME_DIR` | Discord **Flatpak** (fréquent sur Bazzite) n'est pas trouvé : son socket est sous `$XDG_RUNTIME_DIR/app/com.discordapp.Discord/` | Ajouter les emplacements Flatpak (et Snap) | 3 |
| `main.py:96-101` | `SetCurrentProcessExplicitAppUserModelID` | Gardé | Équivalent Linux : `setDesktopFileName` — sous Wayland, c'est lui qui relie la fenêtre à son icône et à son `.desktop` | 3 |
| `src/ui/main_window.py:524-529` (`_minimize_to_tray`) | Suppose une zone de notification | Sans zone de notification (GNOME sans extension AppIndicator, certains compositeurs Wayland), la fenêtre **disparaît** sans icône pour la rappeler | Réduire au lieu de cacher quand `isSystemTrayAvailable()` est faux | 3 |
| `src/core/win_taskbar.py` | `ITaskbarList3` | No-op | Inchangé (piste : `com.canonical.Unity.LauncherEntry`) | — |
| `src/core/diagnostic.py:48-56` (`systeme`) | `win32_ver` | « Linux 6.x » : ni Bazzite ni sa version | `/etc/os-release` (`PRETTY_NAME`) | 3 |
| `src/core/diagnostic.py:103-183` | Processeur, mémoire, cartes graphiques lus dans le registre / `GlobalMemoryStatusEx` | Mémoire et cartes vides | `/proc/meminfo`, `/sys/class/drm` ; plus une ligne « Compatibilité » (lanceur, Proton, préfixe) | 3 |
| `src/core/i18n.py:163-178` | `GetUserDefaultUILanguage` | Repli sur `LANG` & co. : correct | Inchangé | — |
| `src/ui/utils.py:10-27` | Icône `.ico` | Qt lit le `.ico` sous Linux (greffon `qico`) | Inchangé ; PNG 256 px pour le `.desktop` | 4 |
| `src/ui/fonts.py` | — | Polices embarquées (Gelasio remplace Georgia depuis longtemps) | Inchangé | — |
| `src/ui/single_instance.py` | — | `QLocalServer` : socket Unix, fonctionne | Inchangé | — |

### 2.5 Build, CI, documentation

| Emplacement | Constat | Traitement | Phase |
|---|---|---|---|
| `build.bat` | Windows uniquement (et doit le rester) | `build.sh` équivalent : lint → tests → PyInstaller → AppImage, arrêt au premier échec | 4 |
| `.github/workflows/release.yml` | Un seul job, `windows-latest` | Job Linux en parallèle (`ubuntu-22.04` pour la glibc), même tag, AppImage + SHA-256 + attestation jointes au **même** brouillon | 4 |
| `.github/release-notes.md` | Instructions Windows | Section Linux, après le trait (hors de la boîte de mise à jour) | 4 |
| `.github/workflows/tests.yml` | `linux-smoke` bloquant, offscreen | Inchangé ; la suite Linux couvre désormais le lanceur de compatibilité | — |
| `README.md` | Installation Windows | Section « Linux / Bazzite » | 4 |
| `docs/THIRD-PARTY-NOTICES.md` | Binaires Windows seulement | 7-Zip Linux, runtime AppImage, appimagetool | 3-4 |

### 2.6 Déjà portable (vérifié, rien à faire)

- Les chemins du catalogue écrits à la Windows (`HP1\System\…`, `%DOCUMENTS%\…`)
  sont normalisés AVANT vérification (`game_data._est_relatif_sur`,
  `extractors.check_path_traversal`, `pre_launch.substitute_vars`).
- Les INI gardent leurs fins de ligne CRLF (`pre_launch._INI_NEWLINE`) : le jeu
  tournera sous Wine et relira ses propres fins de ligne.
- `Running.ini` (HP1/HP2) et le sous-dossier `pc` de HP7 sont des comportements
  des JEUX : ils valent tels quels sous Wine.
- `.gitattributes` impose déjà LF/CRLF là où il faut ; un `build.sh` y prendra LF.

---

## 3. Ce que livrent les archives (relevé du 2026-09-24)

**Méthode — rien n'est deviné.** Un `.7z` range son en-tête à la FIN : on a lu,
par requêtes HTTP partielles, les 32 octets de tête de chaque archive publiée
(version recommandée) puis sa queue, reconstitué des fichiers creux de la bonne
taille, et fait lister le contenu par 7-Zip. Pour HP4, HP5 et HP6, le `d3d9.ini`
est le premier fichier du bloc : on en a décompressé le début pour l'identifier.

**Pourquoi c'est nécessaire — vérifié dans Wine 9.0**, avec un `d3d9.dll` natif
posé à côté d'un exécutable :

```
sans surcharge              → Loaded "…\testdll\d3d9.dll" : builtin
WINEDLLOVERRIDES=d3d9=n,b   → Loaded "…\testdll\d3d9.dll" : native
nom sans équivalent Wine    → Loaded "…\testdll\openal32.dll" : native
```

Sans surcharge, **Wine remplace silencieusement la DLL livrée par la sienne**
dès qu'il en a une du même nom. Le jeu démarre, mais sans le wrapper qui force le
fenêtré sans bordure, bride les FPS et corrige le champ de vision — le défaut
invisible par excellence. Une DLL dont Wine n'a pas d'équivalent est chargée
d'office : rien à surcharger.

La surcharge à déclarer est donc l'**intersection** entre ce que l'archive
livre et ce que Wine fournit en interne (liste relevée dans le
`x86_64-windows/` de Wine 9.0) :

| Jeu | DLL livrées (hors DLL propres au moteur) | En collision avec Wine 9.0 | `dll_overrides` proposé |
|---|---|---|---|
| hp1 | `d3d11drv.dll` (renderer UE1 de Kentie), `Effects11.dll` | aucune | — |
| hp2 | `d3d11drv.dll`, `Effects11.dll`, `OpenAL32.dll`, `ogg`/`vorbis*` | aucune (`openal32` absent de Wine 9.0) | — |
| hp3 | dgVoodoo 2 : `D3D8.dll`, `D3D9.dll`, `DDraw.dll`, `D3DImm.dll` + `dgVoodoo.conf` ; `msvcr70.dll`, `binkw32.dll` | `d3d8`, `d3d9`, `ddraw`, `msvcr70` | `["d3d8", "d3d9", "ddraw", "msvcr70"]` |
| hp4 | `d3d9.dll` (wrapper ThirteenAG : FPS, fenêtré forcé, FOV) + `d3d9.ini`, `MSVCR71.DLL`, `GofInput.dll` | `d3d9`, `msvcr71` | `["d3d9", "msvcr71"]` |
| hp5 | `d3d9.dll` (wrapper étendu : FXAA, SSAO, DPIAware…) chaîné à `d3d9_original.dll`, `fps.dll`, `hpexhdlr.dll` | `d3d9` | `["d3d9"]` |
| hp6 | `d3d9.dll` (wrapper) + `d3d9.ini`, `fps.dll` | `d3d9` | `["d3d9"]` |
| hp7a | `d3d9.dll` (wrapper) + `d3d9.ini` | `d3d9` | `["d3d9"]` |
| hp7b | `d3d9.dll` (wrapper) + `d3d9.ini`, `paul.dll` | `d3d9` | `["d3d9"]` |

Remarques :

- **`n,b` et jamais `n`** : si la DLL livrée manque (quarantaine d'antivirus
  pour `paul.dll`, fichier supprimé), le jeu retombe sur celle de Wine au lieu
  de ne plus démarrer.
- Les wrappers `d3d9` chargent ensuite le « vrai » `d3d9` depuis
  `system32` : sous Proton c'est celui de **DXVK**, sous Wine celui de wined3d.
  C'est la chaîne voulue.
- Le champ est **par jeu et vient du catalogue**, comme `dpi_aware` : un jeu
  ajouté déclare le sien sans republier le launcher. Il est ignoré sous Windows,
  où la DLL du dossier du jeu est chargée d'office.
- `openal32` : présent dans d'anciennes versions de Wine, absent de la 9.0. Non
  déclaré, puisque non vérifié ailleurs ; à ajouter pour hp2 si un Wine plus
  ancien pose problème.

---

## 4. Décisions de conception

### 4.1 Détection : `umu-run`, puis `wine`

Dans cet ordre, comme demandé. `umu-run` fait tourner **Proton** hors de Steam,
dans le conteneur du Steam Linux Runtime : DXVK, correctifs et bibliothèques
32 bits inclus — c'est ce qui se rapproche le plus de « ça marche comme sur
Steam Deck ». `wine` système en second : il marche, mais sans DXVK (rendu
wined3d/OpenGL) et selon ce que la distribution a installé.

Vérifié dans les sources d'umu (`umu/umu_run.py`, 2026-09) :

- `GAMEID` vaut `umu-default` s'il n'est pas posé ; `PROTONPATH` absent →
  UMU-Proton, téléchargé et tenu à jour par umu ;
- `umu-run ""` crée un préfixe ; `umu-run winetricks <verbes>` exécute
  winetricks **avec `-q`** (non interactif) ;
- umu crée dans le préfixe un lien `pfx → .` et le profil `steamuser`, avec un
  lien du nom Unix vers lui : le Documents du jeu est
  `drive_c/users/steamuser/Documents`.

Un GE-Proton déjà installé (ProtonUp-Qt, `compatibilitytools.d` de Steam natif
ou Flatpak) est préféré via `PROTONPATH` ; un `PROTONPATH` posé par
l'utilisateur est respecté. `ACCIO_COMPAT=wine` (ou `umu`) force un lanceur,
pour le dépannage.

**Bazzite embarque `umu-launcher` et `winetricks` dans son image** (relevé
dans le `Containerfile` de `ublue-os/bazzite`, étape de base commune à toutes
les variantes, le 2026-09-24), ainsi que `p7zip`. Sur Bazzite, le cas « aucun
lanceur » ne devrait donc arriver que sur une image ancienne ou modifiée.

Si rien n'est trouvé : **message clair**, jamais un échec muet — voir §6.

### 4.2 Un préfixe PARTAGÉ par tous les jeux (un par famille de lanceur)

`~/Games/AccioLauncher/_Launcher/prefixes/umu/` ou `…/prefixes/wine/`. Choix
motivé :

1. **C'est le modèle que le code suppose déjà.** Sous Windows, les huit jeux
   partagent UN Documents, UN AppData et UN registre ; `sauvegardes.racines()`,
   `get_documents_dir()` et `game_registry` sont écrits pour une racine unique.
   Un préfixe par jeu aurait obligé à passer le jeu partout où ces fonctions
   sont appelées, pour reproduire une isolation que Windows n'offre pas.
2. **Le socle `vcredist_x86` est exigé par les huit jeux.** Avec un préfixe par
   jeu, on installerait Visual C++ 2015-2022 huit fois (téléchargement et
   installation à chaque premier lancement), et on créerait huit préfixes
   Proton de plusieurs centaines de Mo. Partagé : une fois.
3. Les runtimes propres à HP7a (VC++ 2005) et HP7b (VC++ 2008) cohabitent sans
   conflit, exactement comme sur Windows.
4. Rien d'autre n'est modifié dans le préfixe : les surcharges de DLL passent
   par **l'environnement du lancement** (`WINEDLLOVERRIDES`), pas par le
   registre. Un jeu ne peut donc pas imposer ses réglages aux autres — le
   principal argument de l'isolation tombe.

Le risque accepté : un préfixe abîmé touche tous les jeux. Il se recrée (les
sauvegardes de HP1-HP3 sont dedans : la recréation ne l'efface jamais sans le
dire).

**Pourquoi un préfixe par FAMILLE de lanceur** : Proton range le profil sous
`steamuser`, Wine sous le nom Unix ; Proton « met à niveau » un préfixe Wine en
y recopiant le sien. Passer d'un lanceur à l'autre sur le même préfixe rendrait
les sauvegardes invisibles, sans rien dire. Deux dossiers distincts : aucune
corruption possible, et l'ordre de détection étant fixe, un utilisateur reste
sur le même.

### 4.3 Chemins : l'hôte pour les FICHIERS, Windows pour les VALEURS

- `get_documents_dir()` et `sauvegardes.racines()` rendent les dossiers **du
  préfixe** (chemins hôte : c'est là que Python lit et écrit).
- Ce que le JEU lit (valeur d'INI, `Install Dir` du registre) est converti en
  chemin **Windows** : `C:\users\steamuser\Documents\…` pour ce qui est dans
  `drive_c`, `Z:\home\…\Games\AccioLauncher\HP7\` pour le reste (Wine et Proton
  relient `Z:` à `/`).
- Les INI sont lus et réécrits dans la **page de codes ANSI du préfixe**
  (`HKLM\System\CurrentControlSet\Control\Nls\Codepage`, valeur `ACP`, lue dans
  `system.reg` — `1252` vérifié sur un préfixe neuf). Même contrat qu'`mbcs`
  sous Windows.

### 4.4 Registre : lire les fichiers, écrire par `regedit /S`, prévenir quand même

Vérifié sur un préfixe Wine 9.0 :

- le registre du préfixe est du **texte** (`system.reg` pour HKLM, `user.reg`
  pour HKCU). On le **lit directement**, sans lancer Wine (un `umu-run` coûte
  plusieurs secondes de conteneur) ;
- `wine regedit /S C:\windows\temp\…\langue.reg` importe le `.reg` que
  construit déjà `construire_reg` (même barrière anti-injection, même
  `WOW6432Node` pour la vue 32 bits) en 0,5 s ;
- **`system.reg` n'est réécrit qu'à l'arrêt du wineserver** (≈ 2-3 s après) :
  la relecture de vérification attend donc, comme sous Windows où `regedit /s`
  rend la main avant d'avoir fini ;
- échappements de Wine relevés : `\\`, `\"`, et `\xHHHH` pour tout caractère
  hors ASCII (`fr\x00e9d\xe9ric` pour « frédéric »).

`disponible()` devient vrai quand un lanceur existe **et** que le préfixe est
initialisé. `_ecrire_eleve` reste le seul point d'écriture « hors du
processus » : la garde de `conftest.py` qui l'interdit aux tests couvre donc
Linux sans rien ajouter.

Pas d'UAC sous Wine, mais **le principe « prévenir avant d'écrire » ne bouge
pas** : le rappel de `ecrire_valeurs(…, confirmer=…)` part toujours juste avant
l'écriture, avec ce qu'on remplace. Seul le texte change (registre du préfixe,
pas d'autorisation administrateur).

### 4.5 Prérequis : winetricks dans le préfixe

| Identifiant catalogue | Verbe winetricks | Détection dans le préfixe |
|---|---|---|
| `vcredist_x86` (socle, tous les jeux) | `vcrun2022` | clé `Software\Wow6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x86`, `Installed=1`, ou verbe dans `winetricks.log` |
| `vcredist2005_x86` (HP7a) | `vcrun2005` | assembly `x86_microsoft.vc80.crt_1fc8b3b9a1e18e3b_*` **réelle**, ou `winetricks.log` |
| `vcredist2008_x86` (HP7b) | `vcrun2008` | assembly `x86_microsoft.vc90.crt_…` **réelle**, ou `winetricks.log` |

Piège vérifié : **un préfixe Wine neuf contient déjà des dossiers WinSxS VC80 et
VC90** (`…_none_deadbeef`), remplis des DLL internes de Wine, marquées
`Wine builtin DLL` à l'octet 0x40. Le test Windows (`crt_x86_present`) y verrait
un Visual C++ installé. La détection Linux écarte ces DLL par leur marque.

L'installation passe par `umu-run winetricks …` (winetricks est livré avec
UMU-Proton et GE-Proton) ou par le `winetricks` du système avec `wine`. Elle
télécharge les installeurs **depuis Microsoft** : on le dit avant, et on ne le
fait que sur un clic.

### 4.6 `dpi_aware`, D3D11, `Zone.Identifier`

- `dpi_aware` (HP7a/HP7b) : `__COMPAT_LAYER` est une couche Windows ; sous Wine,
  sans objet. Ignoré, sans avertissement.
- `check_d3d11_feature_level` rend `True` hors Windows : le niveau 11_0 vient
  de DXVK/wined3d, et le repli qu'il déclencherait vise un renderer absent.
- `Zone.Identifier` : flux NTFS, sans objet.

### 4.7 Surveillance du processus

Le processus lancé est `umu-run` (ou `wine`), qui rend la main à la fin du jeu.
Le repli par nom (`tasklist` sous Windows) devient une lecture de `/proc` :
processus du même utilisateur dont le nom (`comm`, que Wine pose au nom de
l'exe Windows) ou le premier argument correspond à l'exe du jeu, et — quand
l'environnement est lisible — dont le `WINEPREFIX` est le nôtre. Même grâce de
10 s (relance UE1).

### 4.8 Emballage : AppImage plutôt que Flatpak

- **AppImage** : un seul fichier, double-clic, intégré au menu par **Gear
  Lever** (Flathub ; absent de la liste préinstallée de Bazzite au 2026-09-24). Surtout : **pas de bac à sable**, donc le
  launcher peut lancer `umu-run` / `wine` de l'hôte et écrire dans
  `~/Games`. Construite par PyInstaller (mode `onedir`) puis `appimagetool`,
  sur `ubuntu-22.04` pour une glibc assez ancienne.
- **Flatpak, piste future** : le bac à sable complique précisément ce dont le
  launcher a besoin — lancer Wine/Proton (il faudrait `flatpak-spawn --host`,
  donc la permission `org.freedesktop.Flatpak`, qui annule l'intérêt du bac à
  sable, ou embarquer un runtime Wine comme le font Bottles et Lutris), et
  écrire dans `~/Games` (permission de système de fichiers à demander). À
  reconsidérer une fois le portage éprouvé.

---

## 5. Plan des phases (une pull request chacune)

1. **Audit** — ce document. Aucun changement de code.
2. **Lanceur de compatibilité** — module `src/core/compat.py` (détection
   umu/wine, préfixe, chemins du préfixe, environnement de lancement,
   conversions de chemins, lecture des `.reg`), branchement de
   `get_documents_dir`, `sauvegardes.racines`, `game_registry`,
   `system_checks`, `pre_launch`, `launch_game` et `ProcessMonitor` ; champ
   `dll_overrides` ; préparation du préfixe et des prérequis en arrière-plan ;
   textes Linux (FR/EN/ES) ; tests.
3. **Reste du portage** — 7-Zip Linux, auto-mise à jour AppImage, choix de
   l'asset par plateforme, Discord Flatpak, `LD_LIBRARY_PATH`, zone de
   notification absente, `setDesktopFileName`, diagnostic ; tests.
4. **Emballage** — spec PyInstaller Linux, AppImage, `.desktop`, `build.sh`,
   job Linux dans `release.yml` (même brouillon, SHA-256, attestation), notes de
   release, README « Linux / Bazzite », avis tiers.

---

## 6. Si aucun lanceur n'est trouvé (texte prévu)

> Accio Launcher lance ces jeux Windows avec **umu-launcher** (recommandé) ou
> **Wine**. Aucun des deux n'est installé.
>
> Sur Bazzite, umu-launcher fait partie du système : mettez Bazzite à jour
> (`ujust update`, puis redémarrez). Sur une autre distribution, installez le
> paquet `umu-launcher` (ou Wine avec le support 32 bits), puis relancez
> Accio Launcher.

Le bouton du message ouvre la section « Linux / Bazzite » du README, qui
détaille aussi l'installation manuelle d'umu (archive « zipapp » dans
`~/.local/bin`).

---

## 7. Limites de cette phase

Vérifié dans l'environnement de travail (Ubuntu 24.04, Wine 9.0 64 bits, sans
affichage) : contenu des archives, ordre de chargement des DLL sous Wine,
format du registre d'un préfixe, écriture par `regedit /S`, marque des DLL
internes de Wine, code d'umu.

**Non vérifié, donc à ne pas tenir pour acquis** : un vrai jeu lancé sous Wine
ou Proton, le comportement réel sur Bazzite (umu préinstallé ou non, Gear
Lever, Discord Flatpak), l'affichage Wayland, les manettes.

## À tester sur Bazzite par Ludo (phase 1)

Rien à exécuter côté launcher pour cette phase. Trois relevés aideront les
suivantes :

1. `umu-run --version` et `winetricks --version` dans un terminal : les deux
   devraient répondre (ils font partie de l'image Bazzite).
2. `ls ~/.local/share/Steam/compatibilitytools.d ~/.steam/root/compatibilitytools.d`
   : un GE-Proton est-il installé ?
3. `flatpak list | grep -i -E "discord|vesktop"` : quelle version de Discord ?
