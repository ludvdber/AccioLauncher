# Accio Launcher en Flatpak

Pour : Ludo. Fait le 2026-11-18 dans un conteneur Linux (Ubuntu 24.04, Flatpak 1.14.6, flatpak-builder 1.4.2,
runtime `org.freedesktop.Platform` 25.08), **sans les jeux, sans GPU, sans umu ni Proton réels**. Chaque point dit
s'il est **PROUVÉ** (essayé ici, sortie à l'appui) ou **SUPPOSÉ** (lu dans le code ou la documentation, à
vérifier sur Bazzite). Aucune ligne de `src/` n'a été modifiée : tout passe par deux petits scripts du Flatpak.

Pourquoi : un mainteneur de Bazzite a écrit qu'ils retireraient un jour le support des AppImage et recommandent
Flatpak (ublue-os/bazzite#2338, relevé dans `docs/linux/AUDIT_LINUX_CLOUD_2026-11.md`, PR #36).

---

## En bref

**Verdict : presque prêt.** Le Flatpak se construit, s'installe, démarre jusqu'à l'assistant de premier lancement,
et le vrai launcher y trouve umu et GE-Proton **sur l'hôte**. Ce qui manque :

1. **Trois petits changements dans `src/`** (proposés plus bas, pas appliqués) : le diagnostic annonce la
   distribution du runtime au lieu de Bazzite ; la mise à jour enverrait vers la page de l'AppImage ; la
   surveillance de HP1/HP2 quand ils se relancent ne voit pas les processus de l'hôte.
2. **Les essais sur ton Bazzite** (liste en fin de document) : préparer Wine, jouer, manette, Discord, mode Jeu.
3. **Pour Flathub** : une exception pour `flatpak-spawn --host` (Lutris en a une) et la preuve que le domaine
   `acciolauncher.be` est à toi. Rien de cela n'est nécessaire pour l'installer chez toi.

Ce qui change pour toi par rapport à l'AppImage : le launcher s'installe et se met à jour comme toutes tes autres
applications (Discover / Bazaar), sans Gear Lever. Ce qui ne change pas : tes jeux, tes préfixes et tes
sauvegardes restent dans `~/Games/AccioLauncher`, et le Flatpak les reprend tels quels.

---

## 1. Ce qui a été construit

| Fichier | Rôle |
|---|---|
| `build/flatpak/be.acciolauncher.AccioLauncher.json` | le manifeste (JSON : testable sans PyYAML) |
| `build/flatpak/preparer.py` | l'archive source : le dossier gelé de PyInstaller (le MÊME que l'AppImage), le `.desktop`, les icônes des sept tailles de l'`.ico`, les licences, le metainfo avec la version de `pyproject.toml` |
| `build/flatpak/accio-launcher` | le point d'entrée : pose les relais vers l'hôte, rend le `XDG_DATA_HOME` de l'hôte, lance le launcher |
| `build/flatpak/accio-hote` | le relais : `umu-run`, `wine`, `wine64`, `winetricks` exécutés sur l'hôte par `flatpak-spawn --host` |
| `build/flatpak/be.acciolauncher.AccioLauncher.metainfo.xml` | la fiche AppStream (Discover, Flathub), version posée à l'emballage |
| `build/flatpak/construire.sh` | archive → flatpak-builder → `dist/AccioLauncher.flatpak` |
| `tests/test_flatpak.py` | 13 tests : identifiant, permissions exactes, relais (faux `flatpak-spawn`), archive reproductible |

Construire (après `python -m PyInstaller accio_launcher.spec --noconfirm`) :

```sh
flatpak install flathub org.freedesktop.Platform//25.08 org.freedesktop.Sdk//25.08
sh build/flatpak/construire.sh
flatpak install --user dist/AccioLauncher.flatpak
flatpak run be.acciolauncher.AccioLauncher
```

### Mesures (PROUVÉ)

| Mesure | Résultat |
|---|---|
| `construire.sh`, utilisateur normal | code 0, 131 s (archive, flatpak-builder, bundle) |
| Archive source | 77 Mo ; **reproductible** : deux passes, même SHA-256 (`092ef41a…10dc7`, build final) |
| Bundle `dist/AccioLauncher.flatpak` | 59 Mo (61 909 968 octets) |
| Installé | 189,8 Mo (le runtime 25.08, partagé avec d'autres applications, en plus) |
| `flatpak run` sous Xvfb | fenêtre « Accio Launcher », assistant de premier lancement (capture `flatpak_assistant.png`) |
| `.desktop` exporté | `Exec=/usr/bin/flatpak run … --command=accio-launcher be.acciolauncher.AccioLauncher`, icônes 16 à 256 px, metainfo |
| `appstreamcli validate` (metainfo) | « Validation was successful: pedantic: 1 » |
| Deux lancements | une seule fenêtre ; journal : « Instance déjà ouverte — demande d'activation envoyée » |
| `flatpak-builder-lint repo` | voir § 5 (Flathub) |

---

## 2. Le choix : repackager le dossier PyInstaller

Trois voies possibles :

| | A. Python + PyQt6 par pip dans le manifeste | **B. Dossier PyInstaller en archive (retenu)** | C. Le même en `extra-data` |
|---|---|---|---|
| Python | le runtime 25.08 a **Python 3.13.18** (relevé) ; le projet exige **3.15** : il faut compiler CPython 3.15 dans le manifeste | celui du dossier gelé (3.15.2) | idem B |
| Qt | roue `PyQt6-Qt6` 6.11.2 = **82 Mo de Qt précompilé** (mesuré) : un binaire, comme B, mais en plus gros à vérifier | celui du dossier gelé (6.11.2) | idem B |
| Build | compilation de CPython (de longues minutes), pip hors ligne avec empreintes : faisable | **131 s** | rien à construire : téléchargé à l'installation chez l'utilisateur |
| Ce qui tourne | une **troisième** combinaison, jamais testée par la suite | **exactement les binaires de l'AppImage**, que la suite (5000 tests), l'audit de géométrie et tes essais Bazzite ont validés | idem B |
| Mises à jour | au rythme du manifeste | au rythme des releases (une archive de plus par release) | idem B |
| Reproductibilité | bonne (empreintes pip) | **archive reproductible prouvée** (même SHA-256 sur deux passes) ; le dossier gelé, lui, l'est autant que le build de release | idem B |
| Flathub | les roues binaires de PyQt sont mal vues ; la base officielle `com.riverbankcomputing.PyQt.BaseApp` est construite pour le Python **du runtime**, pas pour 3.15 | accepté pour un logiciel libre dont l'amont publie ses binaires (archive `url` + `sha256`) ; c'est le cas de nombreuses applications | réservé à ce qui **ne peut pas** être redistribué (logiciels propriétaires) : pas notre cas, ce serait refusé |

**B**, parce qu'il emballe ce qui est déjà testé, sans troisième pile à maintenir. Son défaut, le même que
l'AppImage : Qt et Python ne sont pas mis à jour par le runtime, seulement par une release d'Accio.

Pour Flathub, la source passera de `"path"` à `"url"` + `"sha256"` : l'archive de `preparer.py` sera publiée à
chaque release, à côté de l'AppImage. Ce n'est pas fait ici : `release.yml` est touché par la PR #36, et ajouter
l'étape maintenant créerait un conflit (diff proposé au § 4, D4).

---

## 3. Ce que le bac à sable casse, et comment c'est résolu

### 3.1 Lancer umu-run, Proton ou Wine (hors du Flatpak)

**Le problème.** Dans le bac à sable, `/usr` est celui du runtime : pas d'umu, pas de Wine.
`compat.detecter` ne trouvait rien (« Aucun lanceur de compatibilité », PROUVÉ au premier lancement).

**Comment font les autres** (manifestes Flathub relevés le 2026-11-18) :

- **Lutris** : `--talk-name=org.freedesktop.Flatpak`, donc `flatpak-spawn --host` (exécuter sur l'hôte) ;
- **Heroic** et **Bottles** : umu tourne **dans** le bac à sable (`--filesystem=xdg-data/umu:create`,
  `--allow=multiarch`, `--allow=devel`, `--allow=per-app-dev-shm`), avec les runtimes Proton qu'ils téléchargent
  eux-mêmes.

**Le choix : l'hôte, comme Lutris.** Bazzite livre umu-launcher dans son image et tu y as déjà GE-Proton : les
réutiliser donne **exactement** le comportement de l'AppImage, que tu as vérifié jeu par jeu. Faire tourner umu
dans le bac à sable (Heroic, Bottles) exigerait d'y embarquer umu, de télécharger un deuxième Proton, d'ouvrir
`multiarch`/`devel`, et de tout revérifier jeu par jeu (DXVK, le gel Intel, les surcharges de DLL).

**Le prix**, à dire franchement : `org.freedesktop.Flatpak` permet de lancer **n'importe quoi** sur l'hôte. Le
bac à sable ne protège donc plus le système d'Accio lui-même ; il garde son intérêt pour l'installation, les
mises à jour et le rangement. Le linter de Flathub le signale (`finish-args-flatpak-spawn-access`) : il faut
demander une exception, comme Lutris.

**Comment, sans toucher à `src/`** : au démarrage, `accio-launcher` demande à l'hôte, en un seul aller-retour,
lesquels de `umu-run`, `wine`, `wine64`, `winetricks` existent, et crée pour chacun un lien vers le relais
`accio-hote` dans `$XDG_RUNTIME_DIR/accio-hote`, placé en tête du PATH. `compat.detecter` les trouve par
`shutil.which` comme des programmes ordinaires ; si l'hôte n'a rien, il n'y a aucun lien, et le bandeau
« Wine introuvable » reste juste. Le relais transmet le dossier courant et seulement les variables des jeux
(`WINE*`, `PROTON*`, `PROTONPATH`, `GAMEID`, `STORE`, `UMU_*`, `DXVK_*`, `VKD3D_*`, `MANGOHUD*`, `ACCIO_LAUNCH`).

PROUVÉ (faux `umu-run` installé sur l'hôte, qui note ce qu'il reçoit) :

| Essai | Résultat |
|---|---|
| Le vrai launcher dans le Flatpak | journal : « Lanceur de compatibilité : umu (/run/user/1001/accio-hote/umu-run), Proton …/GE-Proton10-34 » ; « Compatibilité : umu-run (…) · GE-Proton10-34 · préfixe … PAS ENCORE CRÉÉ » |
| Où tourne le programme | sur l'hôte : `/.flatpak-info` absent, PATH de l'hôte |
| Dossier courant, arguments | `cwd=…/HP1/System`, `args=…/HP.exe -arg avec espace` (l'espace est gardé) |
| Variables | `WINEPREFIX`, `GAMEID`, `ACCIO_LAUNCH`, `WINEDLLOVERRIDES`, `UMU_RUNTIME_UPDATE`, `DXVK_CONFIG=d3d9.ffUbershaderVS = False` (espaces gardés) passent ; `LD_LIBRARY_PATH` et une variable étrangère ne passent pas |
| Code de retour, sortie | `code=7` du faux umu relayé ; sa sortie arrive dans le fichier du launcher |
| **Défaut trouvé et corrigé** | avec le `LD_LIBRARY_PATH` du dossier gelé, `flatpak-spawn` chargeait la GLib de PyInstaller : « undefined symbol: g_sort_array », code 127. Le relais le retire désormais (le launcher le retire déjà pour ses enfants, `compat.environnement_hote`) |
| Fermer le launcher pendant une partie | sans `--watch-bus`, le jeu **survit** (comme l'AppImage, `game_manager.py:387`, `start_new_session`) ; avec, il mourait. Option retirée |

SUPPOSÉ : la vraie préparation de Wine (`umu-run ""`, winetricks), l'écriture du registre (`regedit /S`) et un
vrai jeu. Les chemins sont les mêmes des deux côtés (le Flatpak voit `~/Games/AccioLauncher` à son vrai chemin,
y compris `/var/home/…` sur Bazzite) : rien ne devrait changer, mais seul l'essai le dira.

Limite : les relais sont posés **au démarrage**. Quelqu'un qui installe umu pendant que le launcher tourne doit le
relancer (l'AppImage, elle, le retrouve au retour dans la fenêtre).

### 3.2 `~/Games/AccioLauncher`, les préfixes, les sauvegardes, Proton

| Permission | Pourquoi | Preuve |
|---|---|---|
| `--filesystem=~/Games/AccioLauncher:create` | jeux, `_Launcher/` (config, journaux, **préfixes Wine, donc les sauvegardes**) | PROUVÉ : écriture OK ; `~/Documents` invisible |
| `--filesystem=xdg-data/Steam/compatibilitytools.d:ro` | trouver GE-Proton (`compat.proton_installe`) | PROUVÉ : visible, écriture refusée |
| `--filesystem=xdg-data/umu:ro` | savoir si le runtime d'umu est installé (vérification hebdomadaire) | PROUVÉ : visible |

Flatpak redirige `XDG_DATA_HOME` vers `~/.var/app/be.acciolauncher.AccioLauncher/data` (relevé) ; le launcher y
cherchait GE-Proton et umu sans les trouver. `accio-launcher` lui rend celui de l'hôte (`HOST_XDG_DATA_HOME`, sinon
`~/.local/share`). PROUVÉ par le journal ci-dessus (GE-Proton10-34 trouvé). Le launcher n'écrit rien d'autre dans
`XDG_DATA_HOME`.

Pas `--filesystem=home` ni `~/Games` entier (Lutris et Heroic ouvrent bien plus).

Limite : des jeux installés **ailleurs** que sous `~/Games/AccioLauncher` (un second disque) seraient invisibles.
Il faudrait ajouter le dossier choisi (`flatpak override --user --filesystem=/run/media/… be.acciolauncher.AccioLauncher`).

### 3.3 Manette : `/dev/input` et hidraw

`--device=all` : c'est la seule permission qui ouvre à la fois `/dev/input/js*` (navigation,
`manette_lecture.LecteurLinux`) et `/dev/hidraw*` (barre lumineuse de la DS4/DualSense, `manette.py`).
`--device=input` (Flatpak ≥ 1.15.6) n'ouvre pas hidraw. Lutris, Heroic, Bottles et Steam ont tous `--device=all`.

PROUVÉ : avec `--device=all`, le bac à sable voit les 108 entrées du `/dev` de l'hôte ; avec `--nodevice=all`, 14.
`/sys/class/hidraw` et `/sys/class/input` sont visibles. SUPPOSÉ : une vraie manette (le conteneur n'a pas de
`/dev/input`).

### 3.4 Discord

| Permission | Pour |
|---|---|
| `--filesystem=xdg-run/discord-ipc-0` | Discord installé en paquet (natif) |
| `--filesystem=xdg-run/app/com.discordapp.Discord:create` | Discord en Flatpak (le même réglage que Steam et Heroic sur Flathub) |

PROUVÉ (deux faux serveurs Discord sur l'hôte, sous `/run/user/1001`) : depuis le bac à sable, connexion à
`discord-ipc-0` → « natif », à `app/com.discordapp.Discord/discord-ipc-0` → « flatpak ». **Contre-épreuve** : sans la
permission, le socket natif n'est plus qu'un fichier vide en lecture seule (« Permission denied »), et le socket
Flatpak est absent ; deux témoins posés dans `/run/user/1001` restent invisibles (rien d'autre ne fuit).

Non couverts : Discord Canary et Vesktop (le code les cherche, `discord_presence.dossiers_ipc`) ; il faudrait une
permission chacun. Laissés de côté pour rester étroit.

### 3.5 La surveillance des processus des jeux (`/proc`)

PROUVÉ : un « jeu » lancé par le relais tourne sur l'hôte (pid 8013, nommé `hp1.exe`) ; le `/proc` du bac à sable
n'en montre **aucun** (il ne contient que `bwrap`, `sh`, `flatpak-spawn`).

Conséquences :

- **Le suivi principal marche** : le launcher suit le processus qu'il a lancé, et ce processus est le
  `flatpak-spawn` du relais, qui vit tant que le programme de l'hôte tourne et rend son code de retour (PROUVÉ,
  code 7 relayé).
- **Le repli `compat.processus_du_jeu` ne voit rien** : c'est lui qui retient la session pendant la relance
  d'HP1/HP2 au chargement d'une sauvegarde (10 s de grâce). Avec **umu**, c'est probablement sans effet :
  `umu-run` ne rend la main qu'à la fin de tout ce qui tourne dans le préfixe (SUPPOSÉ : le mode
  `waitforexitandrun` de Proton). Avec **wine** seul, la session se terminerait au bout de 10 s.
  Correctif proposé : D3 (§ 4), dont le principe est PROUVÉ : `flatpak-spawn --host ps -u <uid> -o pid=,comm=,args=`
  trouve `hp1.exe` (pid 8013) depuis le bac à sable.

### 3.6 L'auto-mise à jour

PROUVÉ : `$APPIMAGE` est vide dans le Flatpak et `/app` est en lecture seule (écriture refusée). Le code
(`self_update.can_self_update`, `self_update.py:37-38`) rend donc faux, et le launcher **ne remplace jamais son
propre fichier**. Mais `update_dispatcher.download` (`update_dispatcher.py:264-270`) ouvre alors la page de release,
qui propose… l'AppImage. Correctif proposé : D2 (§ 4) — dans un Flatpak, dire « la mise à jour arrivera par
Discover / Bazaar » au lieu d'ouvrir la page.

### 3.7 Le 7-Zip embarqué

PROUVÉ : `/app/lib/AccioLauncher/_internal/assets/7z/linux/7zzs` garde son droit d'exécution dans l'archive
(`preparer.py` le préserve, testé) et extrait une archive dans `~/Games/AccioLauncher` depuis le bac à sable.

### 3.8 Le reste

| Sujet | État |
|---|---|
| Captures (`Images/Accio Launcher`) | `--filesystem=xdg-pictures/Accio Launcher:create`. PROUVÉ : le fichier arrive sur l'hôte. Flatpak recopie le `user-dirs.dirs` de l'hôte : avec `XDG_PICTURES_DIR="$HOME/Images"` (Bazzite en français), la cible est bien `~/Images/Accio Launcher` (relevé). Lecture par `QStandardPaths` : SUPPOSÉ conforme |
| Musiques exportées (`Musique/Accio`) | `--filesystem=xdg-music/Accio:create`. PROUVÉ (fichier arrivé sur l'hôte) |
| Rapport de diagnostic (Bureau) | pas de permission : le Bureau est invisible, `about_page.dossier_du_rapport` retombe sur `_Launcher/logs` (code lu) |
| Liens web, « Ouvrir le dossier » | par le portail `OpenURI` du bureau (Qt le fait seul dans un Flatpak). SUPPOSÉ : le conteneur n'a pas de portail |
| Zone de notification | `--talk-name=org.kde.StatusNotifierWatcher`. SUPPOSÉ (pas de KDE ici) |
| Instance unique | PROUVÉ d'un bac à sable à l'autre |
| Diagnostic | PROUVÉ défaut : le journal dit « Freedesktop SDK 25.08 (Flatpak runtime) » et « (exe) ». `/run/host/os-release` donne la vraie distribution (PROUVÉ). Correctif D1 |
| Désinstallation du launcher (Paramètres) | efface `_Launcher/` (préfixes gardés), `programme_courant()` rend None (pas d'AppImage). Le Flatpak lui-même se retire par Discover : SUPPOSÉ cohérent, à dire dans la boîte (D2 peut le couvrir) |

---

## 4. Chaque fonction du launcher, dans le Flatpak

| Fonction | État | Condition / preuve |
|---|---|---|
| Démarrage, assistant, interface, polices, vidéos | **marche** | PROUVÉ jusqu'à l'assistant (Xvfb) |
| Télécharger un jeu | **marche avec** `--share=network` | SUPPOSÉ (même code que l'AppImage ; le proxy du conteneur bloque GitHub) |
| Installer (7-Zip) | **marche avec** `~/Games/AccioLauncher:create` | PROUVÉ (extraction réelle) |
| Trouver umu / wine / GE-Proton | **marche avec** `org.freedesktop.Flatpak` + `xdg-data/…:ro` + relais | PROUVÉ (journal du vrai launcher) |
| Préparer Wine (préfixe, winetricks) | **marche avec** le relais | SUPPOSÉ (relais prouvé, umu réel absent) |
| JOUER (lancer, suivre, temps de jeu) | **marche avec** le relais | relais PROUVÉ (cwd, variables, code, sortie) ; vrai jeu SUPPOSÉ |
| Relance UE1 de HP1/HP2 (grâce de 10 s) | **à changer dans le code** pour wine seul (D3) ; probablement sans objet avec umu | PROUVÉ : `/proc` aveugle ; `ps` de l'hôte voit le jeu |
| Fermer le launcher pendant une partie | **marche** (le jeu continue) | PROUVÉ |
| Registre Wine (langue, `Install Dir` de HP7) | **marche avec** le relais (lecture des `.reg` dans `~/Games`) | SUPPOSÉ |
| Sauvegardes, Folio, copies | **marche** (dans le préfixe, sous `~/Games`) | SUPPOSÉ (chemins identiques) |
| Captures, musiques exportées | **marche avec** `xdg-pictures/…`, `xdg-music/…` | PROUVÉ |
| Discord (natif, Flatpak) | **marche avec** les deux `xdg-run` | PROUVÉ (faux serveurs) |
| Discord Canary, Vesktop | **ne marche pas** | permission non demandée (choix) |
| Manette (navigation, barre lumineuse) | **marche avec** `--device=all` | SUPPOSÉ (pas de manette ici) |
| Zone de notification | **marche avec** `StatusNotifierWatcher` | SUPPOSÉ |
| Liens web, ouvrir un dossier | **marche** par le portail | SUPPOSÉ |
| Auto-mise à jour | **à changer dans le code** (D2) | PROUVÉ : ne remplace rien, mais ouvre la page de l'AppImage |
| Diagnostic (distribution, forme) | **à changer dans le code** (D1) | PROUVÉ : annonce le runtime |
| Jeux sur un autre disque | **ne marche pas** sans `flatpak override` | par construction |

### Diffs proposés pour `src/` (NON appliqués : une autre session corrige `src/core`)

**D1 — le diagnostic dit la vraie distribution, et « Flatpak »** (`src/core/diagnostic.py`) :

```diff
@@ def systeme() -> str:
-        try:
-            os_release = platform.freedesktop_os_release()
-        except OSError:
-            os_release = {}
+        try:
+            # Dans un Flatpak, /etc/os-release est celui du RUNTIME (« Freedesktop
+            # SDK 25.08 ») ; Flatpak expose celui de l'hôte (relevé le 2026-11-18).
+            hote = Path("/run/host/os-release")
+            os_release = (_lire_os_release(hote) if sous_flatpak() and hote.is_file()
+                          else platform.freedesktop_os_release())
+        except OSError:
+            os_release = {}
@@ def identite() -> str:
     if forme == "exe" and sys.platform != "win32" and os.environ.get("APPIMAGE"):
         forme = "AppImage"
+    elif forme == "exe" and sous_flatpak():
+        forme = "Flatpak"
+
+def sous_flatpak() -> bool:
+    return sys.platform.startswith("linux") and Path("/.flatpak-info").is_file()
```

(`_lire_os_release` : les lignes `CLE=valeur`, guillemets retirés, comme `platform` le fait.)

**D2 — pas de page de l'AppImage dans un Flatpak** (`src/ui/update_dispatcher.py`, `download`) :

```diff
     def download(self) -> None:
         if self._download is not None:
             return
+        if diagnostic.sous_flatpak():
+            # Le Flatpak se met à jour par le gestionnaire de logiciels : la page
+            # de release proposerait l'AppImage, un second launcher à côté.
+            self.launcher_message.emit(tr("La mise à jour arrivera par Discover ou Bazaar."))
+            return
         if not self.can_install_itself:
```

**D3 — voir les processus de l'hôte** (`src/core/compat.py`, `processus_du_jeu`) :

```diff
 def processus_du_jeu(exe: str, pfx: Path | None = None, proc: Path = Path("/proc")) -> bool:
     cible = (exe or "").lower()
     if not cible:
         return False
+    if proc == Path("/proc") and Path("/.flatpak-info").is_file():
+        return _processus_hote(cible)
@@
+def _processus_hote(cible: str) -> bool:
+    """Dans un Flatpak, /proc ne montre que le bac à sable : on demande à l'hôte
+    (`ps` par flatpak-spawn, PROUVÉ le 2026-11-18). Sans le contrôle du préfixe."""
+    try:
+        sortie = subprocess.run(
+            ["flatpak-spawn", "--host", "ps", "-u", str(os.getuid()), "-o", "comm=,args="],
+            capture_output=True, text=True, encoding="utf-8", timeout=5, check=False).stdout
+    except (OSError, subprocess.TimeoutExpired):
+        return False
+    for ligne in sortie.splitlines():
+        comm, _, args = ligne.strip().partition(" ")
+        nom = args.strip().split(" ", 1)[0].replace("\\", "/").rsplit("/", 1)[-1]
+        if comm.lower() == cible[:15] or nom.lower() == cible:
+            return True
+    return False
```

**D4 — publier l'archive à chaque release** (`.github/workflows/release.yml`, job Linux, après `./build.sh` ; non
fait ici : la PR #36 touche ce fichier) : `python build/flatpak/preparer.py`, puis joindre
`build/flatpak/AccioLauncher-linux-x86_64.tar.gz` et son empreinte au brouillon. Le manifeste de Flathub pointera
dessus (`"url"`, `"sha256"`).

---

## 5. Flathub

`flatpak-builder-lint` (outil officiel, `org.flatpak.Builder`), sur le manifeste puis sur le dépôt construit :

| Message | Nature | Suite |
|---|---|---|
| `finish-args-flatpak-spawn-access` (avertissement) | réel : c'est le choix du § 3.1 | demander l'exception à Flathub, en citant Lutris |
| `appid-url-not-reachable` | artefact du conteneur (« self-signed certificate in certificate chain » : le proxy) ; Flathub vérifiera aussi que `acciolauncher.be` t'appartient (l'identifiant `be.acciolauncher.*` l'exige) | fichier de vérification sur le site |
| `appstream-external-screenshot-url`, `appstream-screenshots-not-mirrored-in-ostree` | normal en build local : c'est le build de Flathub qui recopie les captures | rien |
| `metainfo-missing-screenshots`, `releases-info-missing` | **corrigés** (captures du README, version posée par `preparer.py`) | — |

---

## 6. À essayer sur ton Bazzite

Prépare-le une fois : `./build.sh` (ou seulement `python -m PyInstaller accio_launcher.spec --noconfirm`), puis
`sh build/flatpak/construire.sh` et `flatpak install --user dist/AccioLauncher.flatpak`. **Ferme l'AppImage
avant** : les deux partagent `~/Games/AccioLauncher` et l'instance unique.

1. **Démarrer** — Geste : `flatpak run be.acciolauncher.AccioLauncher`, ou « Accio Launcher » dans le menu.
   Attendu : ta bibliothèque telle que tu la connais (mêmes jeux installés), et en tête de
   `~/Games/AccioLauncher/_Launcher/logs/accio_launcher.log` : « Lanceur de compatibilité : umu
   (/run/user/1000/accio-hote/umu-run), Proton …/GE-Proton10-34 ».
2. **Jouer** — Geste : JOUER sur HP1, jouer une minute, quitter. Attendu : le jeu démarre comme avec l'AppImage, le
   launcher revient à la fin, le temps est compté ; `_Launcher/logs/wine-hp1.log` est rempli.
3. **Relance de HP1** — Geste : dans HP1, charger une sauvegarde (le jeu se relance). Attendu : le launcher ne
   revient PAS pendant la relance. S'il revient au bout de 10 s, c'est le cas du § 3.5 : D3 est nécessaire.
4. **HP7 et le registre** — Geste : changer la langue de HP7 partie 2 dans ses réglages, puis JOUER. Attendu : la
   prévenance « registre de Wine », puis le jeu dans la nouvelle langue.
5. **Manette** — Geste : DS4 branchée, dans le launcher : croix ← / →, puis ✕. Attendu : le carrousel change de
   jeu, ✕ ouvre la fiche ; en jeu, la barre lumineuse prend la couleur du jeu (HP6).
6. **Discord Flatpak** — Geste : Discord ouvert, présence activée dans les Paramètres, JOUER. Attendu : ton profil
   affiche « Accio Launcher » et le jeu.
7. **Mode Jeu** — Geste : en mode Bureau, Steam → « Ajouter un jeu non-Steam » → « Accio Launcher » (il est dans la
   liste, comme toute application Flatpak) ; en mode Jeu, le lancer, puis JOUER sur HP1. Attendu : la fenêtre
   s'affiche, la manette la pilote, HP1 démarre et le launcher revient à la fin.
8. **Fermer pendant une partie** — Geste : pendant HP1, quitter le launcher par sa zone de notification. Attendu :
   HP1 continue (comme avec l'AppImage).
