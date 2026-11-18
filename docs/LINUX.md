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

## 2. Audit initial (2026-09) : ce qui supposait Windows

Emplacements relevés sur `main` au 2026-09-24, donnés par fichier et fonction (les
numéros de ligne d'origine dérivaient à chaque modification : remplacés le 2026-10-15 par
la fonction qui les contenait ce jour-là). La colonne
« Aujourd'hui sous Linux » dit ce qui se passait **avant** le portage ; « Phase » dit
quelle pull request le traite. L'état réel est aux §§ 7 et 8 (`docs/linux/ETAT_DES_PHASES.md`).

### 2.1 Lancement d'un jeu — le cœur du portage

| Emplacement | Ce qui suppose Windows | Aujourd'hui sous Linux | Traitement | Phase |
|---|---|---|---|---|
| `src/core/game_manager.py` (`GameManager.launch_game`) | `Popen([exe])` : le `.exe` est exécuté directement | `OSError: Exec format error` — aucun jeu ne démarre | Passer par le lanceur de compatibilité (`umu-run <exe>` / `wine <exe>`) | 2 |
| `src/core/game_manager.py` (`GameManager.launch_game`) | Drapeaux `DETACHED_PROCESS` / `CREATE_NEW_PROCESS_GROUP` | Déjà gardés (`start_new_session`) | Conservé ; sorties du lanceur vers un journal par jeu | 2 |
| `src/core/game_manager.py` (`GameManager.launch_game`) + `src/core/system_checks.py` (`crt_x86_reel`, `_dans_le_prefixe`) | Prérequis VC++ testés dans WinSxS et le registre Windows | Les trois tests rendent `True` : **rien n'est vérifié**, un préfixe sans runtime passe | Tester le **préfixe** ; installer par winetricks | 2 |
| `src/core/system_checks.py` (`_systeme_x86`, `_winsxs`) | `C:\Windows` en repli de `%SystemRoot%` | Chemin inexistant (jamais atteint, les tests sont gardés) | Inchangé (gardé) | — |
| `src/core/system_checks.py` (`check_d3d11_feature_level`) | `check_d3d11_feature_level` crée un device D3D11 par ctypes | Rend `False` : **tout `fallback` d'INI s'activerait**, vers un renderer que HP1/HP2 ne livrent pas (cf. CLAUDE.md) | Rendre `True` hors Windows : sous Wine, D3D11 vient de DXVK / wined3d, pas du pilote | 2 |
| `src/core/pre_launch.py` (niveau du module) | `_INI_ENCODING = "mbcs"` sous Windows, `utf-8` ailleurs | Les INI du moteur sont écrits par le jeu **sous Wine**, donc dans la page ANSI du préfixe, pas en UTF-8 | Lire la page ANSI du préfixe (`Nls\Codepage\ACP` dans `system.reg`) | 2 |
| `src/core/pre_launch.py` (`substitute_vars`) | Les VALEURS d'INI (`SavePath=%DOCUMENTS%\Harry Potter\Save`) deviennent des chemins de l'hôte | Le jeu lirait `SavePath=/home/…/Documents/…` : un chemin Unix dans un INI Windows, qui ne tombe juste que si le lecteur courant est `Z:` | Distinguer le chemin du FICHIER (hôte) de la VALEUR écrite (chemin Windows : `C:\users\steamuser\Documents\…`, `Z:\home\…`) | 2 |
| `src/core/pre_launch.py` (`env_de_lancement`) | `__COMPAT_LAYER=HighDpiAware`, couche de compatibilité Windows | Rend déjà `None` hors Windows | Ignoré proprement sous Wine (aucune notion équivalente) ; l'environnement Wine est composé à part | 2 |
| `src/core/config.py` (`get_documents_dir`) | `SHGetFolderPathW`, puis `~/Documents` hors Windows | Pointe le Documents **de l'hôte** : HP1-HP3 y trouveraient leurs INI patchés… que le jeu, sous Wine, ne lit pas | Documents **du préfixe** (`drive_c/users/<profil>/Documents`) | 2 |
| `src/core/post_install.py` (`allowed_config_roots`) | « Saved Games » sous le dossier personnel | Idem : hors du préfixe | Racines du préfixe | 2 |
| `src/core/post_install.py` (`destination_config`) | `~/Documents/…` du catalogue → Documents de l'hôte | Config livrée copiée au mauvais endroit | Suit `get_documents_dir` (préfixe) | 2 |
| `src/core/sauvegardes.py` (`racines`) | `LOCALAPPDATA` | `None` : HP5-HP7b n'ont **aucune** sauvegarde relevée ; Documents de l'hôte pour HP1-HP3 | Documents et `AppData/Local` du préfixe — le module l'annonçait déjà comme « le SEUL endroit à changer » | 2 |
| `src/core/game_registry.py` (`disponible`) | Registre = `winreg` | `False` : sélecteur de langue éteint, **`Install Dir` jamais écrit** — or HP7a/HP7b ne démarrent pas sans lui | `True` quand un lanceur et un préfixe existent | 2 |
| `src/core/game_registry.py` (`lire_valeurs`) | `winreg.OpenKey` | Rend `{}` | Lire `system.reg` / `user.reg` du préfixe (texte, sans lancer Wine) | 2 |
| `src/core/game_registry.py` (`comparer`) (`_ecrire_direct`, `_ecrire_eleve`) | `winreg` puis `ShellExecuteW("runas", "regedit.exe")` + UAC | Jamais atteint (`ecrire_valeurs` rendait `False`) | `_ecrire_eleve` = import du `.reg` par `regedit /S` **dans le préfixe**, via le lanceur ; pas d'UAC, mais la prévenance reste | 2 |
| `src/core/game_language.py` (`resoudre`, `appliquer`) | Portes `disponible()` | Aucune langue, aucune écriture | Rien à changer : elles s'ouvrent quand `disponible()` dit vrai | 2 |
| `src/ui/process_monitor.py` (`ProcessMonitor.start`) | Nom d'exe pris dans `process.args[0]` | Sous Linux ce serait `umu-run` ou `wine` | Chercher l'argument en `.exe` | 2 |
| `src/ui/process_monitor.py` (`_is_exe_running`) | `tasklist.exe` pour suivre la relance UE1 | Rend `False` : la relance de HP1/HP2 au chargement d'une sauvegarde **terminerait la session** au bout de 10 s | Équivalent `/proc` (processus Wine de même nom, même utilisateur, même préfixe), même grâce de 10 s | 2 |
| `src/core/win_utils.py` (`dossier_systeme`) | `System32`, `C:\Windows` | Gardé | Inchangé | — |
| `src/ui/game_detail_handlers.py` (`confirmer_registre.demander`) | « registre de **Windows** », invite UAC | Jamais affiché | Texte Linux : registre **du préfixe Wine**, sans UAC ; même prévenance | 2 |
| `src/ui/game_detail_handlers.py` (`on_play`) | « Composant **Windows** manquant » → page Microsoft ; « Sécurité Windows » pour Documents | Jamais atteint | Proposer l'installation dans le préfixe ; message Documents propre à Linux | 2 |
| `src/ui/game_detail_handlers.py` (`on_game_settings`) | « autorisation administrateur » | Jamais atteint | Texte Linux | 2 |
| `src/ui/alert_banner.py` (niveau du module, `AlertBanner._message`, `AlertBanner._largeur_utile`) | Bandeau « Visual C++ manquant » → page Microsoft | Jamais affiché (tests à `True`) | Lien « Installer » qui prépare le préfixe ; bandeau « Wine introuvable » | 2 |
| `src/core/game_data.py` | Aucune notion de surcharge de DLL | Wine charge **son** `d3d9` au lieu de celui livré (vérifié, §3) | Champ de catalogue `dll_overrides`, validé au parsing | 2 |

### 2.2 Installation, extraction

| Emplacement | Ce qui suppose Windows | Aujourd'hui sous Linux | Traitement | Phase |
|---|---|---|---|---|
| `src/core/extractors.py` (`find_7z_exe`) | `7z.exe` embarqué, puis `C:\Program Files\7-Zip` | Repli sur `shutil.which("7z")` : dépend de ce que l'utilisateur a installé ; sur Bazzite, rien de garanti | Embarquer le **7-Zip officiel Linux** (`7zz`), repli `7zz`/`7z` du système (jamais py7zr, règle 92) | 3 |
| `src/core/extractors.py` (`_find_7z_linux`, `verify_archive_entries`) | `CREATE_NO_WINDOW` | Déjà gardé | Inchangé | — |
| `src/core/post_install.py` (`ranger_dans_sous_dossier`) + `src/core/win_utils.py` (`remove_zone_identifier`) | `Zone.Identifier` (flux NTFS) | No-op, sans objet sous Linux | Inchangé | — |
| `accio_launcher.spec` (ressource de version, choix du 7-Zip par plateforme) | Onefile Windows, ressource de version, `.ico`, `7z.exe` embarqué partout | Un build Linux embarquerait 7z.exe/7z.dll pour rien | Spec par plateforme : onedir Linux, sans binaires Windows | 4 |

### 2.3 Mise à jour du launcher

| Emplacement | Ce qui suppose Windows | Aujourd'hui sous Linux | Traitement | Phase |
|---|---|---|---|---|
| `src/core/self_update.py` (`can_self_update`) | Exe gelé **Windows** | `False` : la mise à jour ouvre la page de release | AppImage : remplacer `$APPIMAGE` | 3 |
| `src/core/self_update.py` (`nom_du_telechargement`) | `.bat` qui attend la mort du processus | — | Script `/bin/sh` détaché, chemins par l'environnement (même principe que les `%ACCIO_*%`) | 3 |
| `src/core/self_update.py` (`relaunch_after_exit`) | Hors Windows : `Popen([sys.executable, *argv])` **immédiat** | Deux défauts : la nouvelle instance démarre avant la mort de l'ancienne et bute sur l'instance unique ; dans une AppImage, `sys.executable` vit dans un montage qui disparaît avec le processus | Attendre la mort du PID puis relancer `$APPIMAGE` | 3 |
| `src/core/updater.py` (`UpdateChecker._check_launcher`, `asset_de_la_plateforme`) | Asset de mise à jour = le premier `.exe` | Un launcher Linux téléchargerait l'exe Windows | Choisir l'asset de SA plateforme (`.AppImage`) | 3 |
| `src/ui/update_dispatcher.py` (`UpdateDispatcher.download`) | Fichier téléchargé nommé `AccioLauncher_v….exe` | — | Nom selon la plateforme | 3 |
| `src/core/self_update.py` (`_clean_pyinstaller_env`) | Purge les `_PYI_*` | Sous Linux, le chargeur de PyInstaller **modifie `LD_LIBRARY_PATH`** : tout processus enfant (umu, wine, xdg-open, le navigateur) chargerait les bibliothèques embarquées | Restaurer `LD_LIBRARY_PATH` d'origine au démarrage (mode gelé Linux) | 3 |

### 2.4 Intégrations et confort

| Emplacement | Ce qui suppose Windows | Aujourd'hui sous Linux | Traitement | Phase |
|---|---|---|---|---|
| `src/core/discord_presence.py` (`_open_ipc`) | Tube nommé Windows ; socket Unix dans `$XDG_RUNTIME_DIR` | Discord **Flatpak** (fréquent sur Bazzite) n'est pas trouvé : son socket est sous `$XDG_RUNTIME_DIR/app/com.discordapp.Discord/` | Ajouter les emplacements Flatpak (et Snap) ; fait : Discord, Discord Canary, Vesktop en Flatpak, Snap (`dossiers_ipc`) | 3 |
| `main.py` (`main`, AppUserModelID) | `SetCurrentProcessExplicitAppUserModelID` | Gardé | Équivalent Linux : `setDesktopFileName` — sous Wayland, c'est lui qui relie la fenêtre à son icône et à son `.desktop` | 3 |
| `src/ui/main_window.py` (`_minimize_to_tray`) | Suppose une zone de notification | Sans zone de notification (GNOME sans extension AppIndicator, certains compositeurs Wayland), la fenêtre **disparaît** sans icône pour la rappeler | Réduire au lieu de cacher quand `isSystemTrayAvailable()` est faux | 3 |
| `src/core/win_taskbar.py` | `ITaskbarList3` | No-op | Inchangé (piste : `com.canonical.Unity.LauncherEntry`) | — |
| `src/ui/fond_gpu.py` (`actif`) | Fond animé dessiné par la carte graphique (QtQuick) ; les cinématiques (`ecran_video_gpu`) le suivent | **Éteint** hors Windows (`sys.platform == "win32"`) : le fond passe par QPainter | À essayer sous Wine et dans l'AppImage avec `ACCIO_FOND_GPU=1` | — |
| `src/ui/fiche_gpu.py`, `src/ui/carrousel_gpu.py` (`actif`) | Jumeau visuel de la fiche, du carrousel et du disque (QtQuick) | **Éteints** avec le fond : ils suivent `fond_gpu.actif()` | Suivent l'essai du fond | — |
| `src/core/diagnostic.py` (`systeme`) | `win32_ver` | « Linux 6.x » : ni Bazzite ni sa version | `/etc/os-release` (`PRETTY_NAME`) | 3 |
| `src/core/diagnostic.py` (`identite`) | Processeur, mémoire, cartes graphiques lus dans le registre / `GlobalMemoryStatusEx` | Mémoire et cartes vides | `/proc/meminfo`, `/sys/class/drm` ; plus une ligne « Compatibilité » (lanceur, Proton, préfixe) | 3 |
| `src/core/i18n.py` (`detect_system_language`) | `GetUserDefaultUILanguage` | Repli sur `LANG` & co. : correct | Inchangé | — |
| `src/ui/utils.py` (niveau du module) | Icône `.ico` | Qt lit le `.ico` sous Linux (greffon `qico`) | Inchangé ; PNG 256 px pour le `.desktop` | 4 |
| `src/ui/fonts.py` | — | Polices embarquées (Gelasio remplace Georgia depuis longtemps) | Inchangé | — |
| `src/ui/single_instance.py` | — | `QLocalServer` : socket Unix, fonctionne | Inchangé | — |

### 2.5 Build, CI, documentation

| Emplacement | Constat | Traitement | Phase |
|---|---|---|---|
| `build.bat` | Windows uniquement (et doit le rester) | `build.sh` équivalent : lint → tests → PyInstaller → AppImage, arrêt au premier échec | 4 |
| `.github/workflows/release.yml` | Un seul job, `windows-latest` | Job Linux en parallèle (runner `ubuntu-latest`, build dans un conteneur `ubuntu:22.04` pour la glibc 2.35, prouvée par `glibc_exigee.py`), même tag, AppImage + SHA-256 + attestation jointes au **même** brouillon | 4 |
| `.github/release-notes.md` | Instructions Windows | Section Linux, après le trait (hors de la boîte de mise à jour) | 4 |
| `.github/workflows/tests.yml` | `linux-smoke` bloquant, offscreen | Inchangé ; la suite Linux couvre désormais le lanceur de compatibilité | — |
| `README.md` | Installation Windows | Section « Linux / Bazzite » | 4 |
| `docs/THIRD-PARTY-NOTICES.md` | Binaires Windows seulement | 7-Zip Linux, runtime AppImage, appimagetool | 3-4 |

### 2.6 Déjà portable (vérifié, rien à faire)

- Les chemins du catalogue écrits à la Windows (`HP1\System\…`, `%DOCUMENTS%\…`)
  sont normalisés AVANT vérification (`chemins.refus_de_chemin`,
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
| hp1 | `d3d11drv.dll` (renderer UE1 de Kentie), `Effects11.dll` ; `winmm.dll` (correctif, depuis le 2026-10-07) | `winmm` | `["winmm"]` (catalogue 0.43) |
| hp2 | `d3d11drv.dll`, `Effects11.dll`, `OpenAL32.dll`, `ogg`/`vorbis*` ; `winmm.dll` (correctif) | `winmm` (`openal32` absent de Wine 9.0) | `["winmm"]` (catalogue 0.43) |
| hp3 | dgVoodoo 2 : `D3D8.dll`, `D3D9.dll`, `DDraw.dll`, `D3DImm.dll` + `dgVoodoo.conf` ; `msvcr70.dll`, `binkw32.dll` | `d3d8`, `d3d9`, `ddraw`, `msvcr70` | `["msvcr70"]` — **dgVoodoo laissé de côté** : sous Proton il plante au démarrage (`UD3DRenderDevice::SetRes`, General protection fault), alors que le d3d8/d3d9 de Proton (DXVK) rend le jeu (menu, nouvelle partie, cinématique : vu le 2026-10-01). Le plafond de 60 images/s que tenait dgVoodoo devait passer par `"max_fps": 60` → `DXVK_FRAME_RATE=60` : **sans effet** (Bazzite, 2026-10-01 puis 10-20) — HP3 rend par le `d3d8` de wined3d, pas par DXVK ; le plafond reste à trouver |
| hp4 | `d3d9.dll` (wrapper ThirteenAG : FPS, fenêtré forcé, FOV) + `d3d9.ini`, `MSVCR71.DLL`, `GofInput.dll` | `d3d9`, `msvcr71` | `["d3d9", "msvcr71"]` |
| hp5 | `d3d9.dll` (wrapper étendu : FXAA, SSAO, DPIAware…) chaîné à `d3d9_original.dll`, `fps.dll`, `hpexhdlr.dll`, `xinput1_3.dll` (correctif) | `d3d9`, `xinput1_3` | `["d3d9", "xinput1_3"]` |
| hp6 | `d3d9.dll` (wrapper) + `d3d9.ini`, `fps.dll`, `xinput1_3.dll` | `d3d9`, `xinput1_3` | `["d3d9", "xinput1_3"]` |
| hp7a | `d3d9.dll` (wrapper) + `d3d9.ini` ; `xinput1_3.dll` seulement avec le nouveau correctif (absent des archives installées au 2026-10-01 : la surcharge retombe alors sans dommage sur celle de Wine) | `d3d9`, `xinput1_3` | `["d3d9", "xinput1_3"]` |
| hp7b | `d3d9.dll` (wrapper) + `d3d9.ini`, `paul.dll` ; `xinput1_3.dll` : comme hp7a | `d3d9`, `xinput1_3` | `["d3d9", "xinput1_3"]` |

Remarques :

- **`n,b` et jamais `n`** : si la DLL livrée manque (quarantaine d'antivirus
  pour `paul.dll`, fichier supprimé), le jeu retombe sur celle de Wine au lieu
  de ne plus démarrer. Vrai pour la famille wine ; sous Proton, `d3d9=n` est
  ajouté APRÈS la chaîne du launcher et Wine garde le dernier réglage (sans
  dégât : DXVK est natif). Vérifié sur Bazzite pour `winmm` (HP1, HP2),
  `d3d9` et `xinput1_3` (HP4 à HP7b) : DLL du dossier chargée en `native`.
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
  `drive_c`, et pour le reste **le lecteur que Wine donne lui-même au chemin**
  (`dosdevices`, la racine la plus profonde gagne), sinon `Z:\…` (relié à `/`).
  Proton relie aussi `x:` au dossier personnel : l'exe lancé par son chemin
  Unix tourne en `X:\Games\AccioLauncher\HP7\pc\hp7.exe`. HP7 compare son
  dossier à `Install Dir` et quitte en silence (code 0, 3 s) si la valeur dit
  `Z:\home\…` : défaut trouvé et corrigé sur Bazzite le 2026-10-20.
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
| `vcredist2005_x86` (HP5, HP6, HP7a) | `vcrun2005` | **toujours présent** : les DLL VC80 de Wine suffisent (HP5 et HP6 tournent sans, Bazzite, 2026-10-20 ; HP7a non essayé) |
| `vcredist2008_x86` (HP7b) | `vcrun2008` | assembly `x86_microsoft.vc90.crt_…` **réelle**, ou `winetricks.log` |

Piège vérifié : **un préfixe Wine neuf contient déjà des dossiers WinSxS VC80 et
VC90** (`…_none_deadbeef`), remplis des DLL internes de Wine, marquées
`Wine builtin DLL` à l'octet 0x40. Le test Windows (`crt_x86_present`) y verrait
un Visual C++ installé. La détection Linux écarte ces DLL par leur marque.

L'installation passe par `umu-run winetricks …` (winetricks est livré avec
UMU-Proton et GE-Proton : sur Bazzite, c'est `GE-Proton10-34/protonfixes/winetricks -q`
qui tourne ; `vcrun2005` posé en 12 s, `vcrun2008` en 10 s, installeurs déjà en cache) ou par le `winetricks` du système avec `wine`. Elle
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
  dans un conteneur `ubuntu:22.04` (glibc 2.35 : Mint 21, Debian 12, Bazzite,
  Steam Deck), sur un runner `ubuntu-latest`.
- **Flatpak, piste future** : le bac à sable complique précisément ce dont le
  launcher a besoin — lancer Wine/Proton (il faudrait `flatpak-spawn --host`,
  donc la permission `org.freedesktop.Flatpak`, qui annule l'intérêt du bac à
  sable, ou embarquer un runtime Wine comme le font Bottles et Lutris), et
  écrire dans `~/Games` (permission de système de fichiers à demander). À
  reconsidérer une fois le portage éprouvé.

### 4.9 DXVK : le gel du GPU Intel, et l'incrustation du correctif

Relevé sur Bazzite le 2026-11-11 (i3-1220P, Intel UHD « ADL GT2 », Mesa 26.2.6,
GE-Proton10-34 dont le DXVK est `v2.7.1-509-g1676dcaf`, c'est-à-dire la branche
qui deviendra la 3.0). Détail : `docs/linux/RETOUR_BAZZITE.md`, septième passage.

- **Le défaut.** Ce DXVK rend le pipeline fixe de Direct3D 9 par un vertex
  shader unique, l'« ubershader ». Pour un sommet position + couleur + texture
  (17 éléments de sommet), le pilote Intel de Mesa (ANV) donne à ce shader
  2 + 58 registres de constantes + 72 d'attributs = **132 registres pour une
  file de 128**. Le GPU ne finit jamais le dessin : `i915 … GPU HANG` au journal
  du noyau, image figée, il faut tuer le jeu. Mesa connaît le défaut (ticket
  15795, correctif MR 42665 de juillet 2026, présent dans la 26.2.6) mais son
  correctif ne suffit pas à ce cas ; DXVK 3.0.1 le contourne de son côté en
  activant les « descriptor buffers » sur ces GPU.
- **Qui le déclenche.** Le texte de l'incrustation du correctif (F10, F11) de
  HP4 à HP7b : 9 gels sur 9, d'où son `DrawUnderWine=0`. N'importe quel dessin
  à pipeline fixe du même genre le ferait.
- **Le remède, côté lanceur.** `compat.environnement` pose
  `DXVK_CONFIG=d3d9.ffUbershaderVS = False` à chaque lancement : DXVK compile
  alors un shader par cas, comme avant la 3.0. Un réglage de l'utilisateur sur
  cette option, ou sur `dxvk.enableDescriptorBuffer` (l'autre remède, vérifié
  aussi), reste le sien. Avec le remède, HP6 tient 42 images/s au Terrier (sans lui : non mesuré).
- **L'incrustation.** `incrustation_wine.suivre` écrit `DrawUnderWine=1` dans
  le `d3d9.ini` quand l'environnement du lancement porte le remède, `0` sinon.
  Un ini sans la clé n'est pas touché.
- **wined3d** (`PROTON_USE_WINED3D=1`) : pas de gel, le défaut est propre au
  couple DXVK + ANV.

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

## 6. Si aucun lanceur n'est trouvé (texte affiché)

> Accio Launcher lance ces jeux Windows avec **umu-launcher** (recommandé) ou
> **Wine**. Aucun des deux n'est installé.
>
> Sur Bazzite, umu-launcher fait partie du système : mettez Bazzite à jour
> (`ujust update`, puis redémarrez). Sur une autre distribution, installez le
> paquet `umu-launcher` (ou Wine avec le support 32 bits), puis cliquez à
> nouveau sur JOUER : le launcher les cherchera de nouveau.

Le bouton du message ouvre la section « Linux / Bazzite » du README.

---

## 7 à 9. État des phases 2, 3 et 4

Le lanceur de compatibilité (§ 7), le reste du portage (§ 8), l'AppImage et la release commune (§ 9) :
[`docs/linux/ETAT_DES_PHASES.md`](linux/ETAT_DES_PHASES.md).

## 10. Limites de l'audit (phase 1)

Vérifié dans l'environnement de travail (Ubuntu 24.04, Wine 9.0 64 bits, sans
affichage) : contenu des archives, ordre de chargement des DLL sous Wine,
format du registre d'un préfixe, écriture par `regedit /S`, marque des DLL
internes de Wine, code d'umu.

**Non vérifié par cet audit (2026-09-24)** : vrais jeux sous Proton, umu
préinstallé et Wayland sont vus depuis sur Bazzite (RETOUR_BAZZITE.md). La
manette n'y est vue que **par le jeu**, sans bouton pressé
(`RETOUR_BAZZITE_PASSAGES_1_A_6.md`, « manette non essayée ») : la navigation
du launcher à la manette (`/dev/input/js*`) reste à essayer sous Linux, comme
Gear Lever, Discord Flatpak et le mode Jeu (audit du 2026-11-17).

## À tester sur Bazzite par Ludo (phase 1)

Rien à exécuter côté launcher pour cette phase. umu-launcher 1.4.4, winetricks
et GE-Proton10-34 (`~/.local/share/Steam/compatibilitytools.d`) sont relevés
(RETOUR_BAZZITE.md). Reste :

3. `flatpak list | grep -i -E "discord|vesktop"` : quelle version de Discord ?

## À tester sur Bazzite par Ludo (phase 2)

Depuis les sources de la branche de la phase 2 (Bazzite 45 fournit Python 3.15, `/usr/bin/python3.15`) :

```sh
uv venv --python 3.15 ~/accio-venv && uv pip install --python ~/accio-venv/bin/python -r requirements.txt
~/accio-venv/bin/python main.py
```

Vus sur Bazzite (RETOUR_BAZZITE.md) : `verifier_wine`, préparation de Wine
et HP1 par JOUER, sauvegardes au Folio, prévenance du registre de Wine de HP7,
surcharge `+loaddll` de HP5. Restent l'Annuler de la préparation, et :

4. Dans HP1, **charger une sauvegarde** (UE1 relance son processus) : le
   launcher ne doit PAS revenir au bout de 10 s. Quitter le jeu : le launcher
   revient, le temps de jeu est compté.
7. Changer la langue de HP7 partie 2 dans ses réglages : même prévenance, et la
   langue doit suivre en jeu.
9. Cas sans Wine : `ACCIO_COMPAT=wine ~/accio-venv/bin/python main.py` (Bazzite
   n'a pas `wine`) → bandeau « Wine introuvable » sur les fiches, et au JOUER le
   message qui dit quoi installer.

## À tester sur Bazzite par Ludo (phase 3)

Depuis les sources de la branche de la phase 3 (même venv que la phase 2).
L'auto-mise à jour AppImage ne se teste qu'avec l'AppImage de la phase 4.

1. **Extraction** : désinstaller puis réinstaller **HP1** ; la barre
   « Installation » doit AVANCER (pas rester à 0 % puis sauter à 100 %). Le
   journal `~/Games/AccioLauncher/_Launcher/logs/accio_launcher.log` doit
   mentionner `assets/7z/linux/7zzs`.
2. **Journal** : ses deux premières lignes doivent porter
   `Bazzite … · noyau … (x86_64) · KDE · Wayland` (ou `Gamescope` en mode Jeu),
   puis `Compatibilité : umu-run (…) · GE-Proton… · préfixe … prêt`.
3. **Diagnostic** : Paramètres → À propos → « Copier le rapport », coller dans un éditeur : la carte graphique doit être nommée
   (`AMD · Navi …` ou `NVIDIA · … · pilote nvidia 5xx.xx`), et aucune ligne ne
   doit contenir ton nom d'utilisateur.
4. **Discord Flatpak** : Discord ouvert, activer la présence dans les
   Paramètres, lancer un jeu : l'activité « Accio Launcher » doit apparaître
   sur ton profil (vu depuis un autre compte, pour les boutons).
5. **Zone de notification** : lancer un jeu. Sous KDE, le launcher doit se
   ranger dans la zone (icône près de l'horloge) et revenir à la fin de la
   partie. En mode Jeu (Gamescope), noter ce qui se passe : réduit, ou caché ?
6. **Icône Wayland** : la fenêtre du launcher doit porter son icône dans la
   barre des tâches (depuis les sources, sans `.desktop` installé, une icône
   générique est ATTENDUE ; c'est l'AppImage de la phase 4 qui la fournira).
7. **Redémarrer maintenant** : changer la langue dans les Paramètres, cliquer
   « Redémarrer maintenant » : le launcher doit se fermer PUIS se rouvrir
   (une seule fenêtre).
8. **Liens** : « Ouvrir le dossier » d'un jeu et un lien web (Ko-fi, Discord)
   doivent ouvrir Dolphin et le navigateur normalement.

## À tester sur Bazzite par Ludo (phase 4)

Avec l'AppImage d'un build d'essai (Actions → release → Run workflow, case
décochée → artefact « AccioLauncher-linux-essai », un zip qui la contient) ou
d'un brouillon de release (AppImage épurée, `strip=True`, § 9 de `docs/linux/ETAT_DES_PHASES.md` : 71 Mo au build
du 2026-11-11, RETOUR_BAZZITE.md).

1. **Lancer sans rien installer** : ranger le fichier dans `~/AppImages`,
   clic droit → Propriétés → « Exécutable », double-clic. Le launcher s'ouvre ;
   `~/Games/AccioLauncher/_Launcher/logs/accio_launcher.log` commence par
   `Accio Launcher … (AppImage) · Bazzite …`.
2. **Empreinte** : `sha256sum AccioLauncher-x86_64.AppImage` doit donner celle
   du résumé du run (ou des notes du brouillon).
3. **Gear Lever** : ouvrir l'AppImage avec Gear Lever, « Déplacer vers le
   menu des applications ». « Accio Launcher » apparaît dans le menu avec son
   icône ; lancé depuis le menu, la barre des tâches montre l'icône du
   launcher (et non une icône générique Wayland).
4. **Jouer depuis l'AppImage** : installer HP1, JOUER (préparation de Wine
   comme en phase 2), quitter le jeu : le launcher revient.
5. **Liens** : un lien web (Ko-fi) et « Ouvrir le dossier » d'un jeu. Le
   navigateur et Dolphin doivent s'ouvrir normalement — une erreur de
   bibliothèque ici désignerait `LD_LIBRARY_PATH`.
6. **Mode Jeu** : en mode Bureau, Steam → « Ajouter un jeu non-Steam » →
   l'AppImage ; passer en mode Jeu et lancer. Noter : la fenêtre s'affiche-t-
   elle, la souris/manette pilote-t-elle le launcher, un jeu se lance-t-il ?
7. **Brouillon de release** (à la prochaine version) : vérifier qu'il porte
   quatre fichiers — `AccioLauncher.exe`, `AccioLauncher-x86_64.AppImage` et
   leurs `.sigstore.json` — et que les notes affichent les deux empreintes.
8. **Auto-mise à jour** : faite sur Bazzite (1.2.3 → 1.3.3, « AppImage
   remplacée », relance 1 s après : RETOUR_BAZZITE.md) ; reste à voir le
   fichier rangé par Gear Lever.
