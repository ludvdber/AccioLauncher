# Mission : essais Linux sur Bazzite

Pour : Claude Code sur le portable Linux de Ludo (Bazzite, KDE Wayland, i3-1220P, Intel UHD).
Rédigé le 2026-09-30 par la session Windows. Tu travailles **seul, en autonomie** ; Ludo reviendra
lire ton rapport puis le rapportera à la session Windows.

Réponds à Ludo **en français**. Lis d'abord `CLAUDE.md` (toutes les règles du projet) et
`docs/LINUX.md` (portage : umu puis wine, préfixe partagé, surcharges de DLL).

## Deuxième passage (2026-10-01) : chaque jeu, un par un

Le premier passage (tâches A à F, plus bas) est fait : lis `docs/linux/RETOUR_BAZZITE.md` pour savoir
où il s'est arrêté. Ludo demande maintenant d'essayer **chaque jeu** sous Linux. Ajoute tes résultats dans
`RETOUR_BAZZITE.md`, sous un titre « Deuxième passage (2026-10-01) », sans effacer le premier.

**Ce qui change dans les autorisations** : HP7a et HP7b peuvent maintenant être lancés (« chaque jeu »).
Sous Windows, HP8 s'est déjà figé à 100 % sur tous les cœurs (2026-09-25) : surveille-le (`top`) et, s'il
ne répond plus pendant 30 s, arrête-le (`pkill -f hp8.exe`, puis `wineserver -k` avec le `WINEPREFIX` du
launcher) et note-le. Tout le reste de « Ce que tu as le droit de faire » reste valable : son coupé,
sauvegarde du préfixe d'abord, pas de commit, rien d'installé sur le système.

### Le correctif de cette nuit (DLL Windows, à récupérer)

Le correctif `Harry-Potter-PC-Fix` a changé cette nuit, côté Windows. Les archives publiées ne le portent
pas encore. Pour l'essayer :

1. Le build GitHub du dépôt `ludvdber/Harry-Potter-PC-Fix` publie l'artefact **`d3d9-win32`** (un seul
   `d3d9.dll` et un seul `xinput1_3.dll` pour tous les jeux). Prends celui du dernier commit **vert** :
   `gh run download --repo ludvdber/Harry-Potter-PC-Fix -n d3d9-win32` si `gh` est connecté. Sinon,
   demande à Ludo de le télécharger depuis la page Actions du dépôt.
2. Les `d3d9.ini` viennent du même commit : `data/<jeu>/d3d9.ini` du dépôt (clone-le à côté s'il n'y est pas).
3. Avant de remplacer quoi que ce soit dans `~/Games/AccioLauncher/<jeu>/`, copie `d3d9.dll`, `d3d9.ini`
   et `xinput1_3.dll` d'origine dans `~/AccioSauvegardes/`, et remets-les à la fin. Une « Vérification /
   réparation » du launcher les remet aussi.
4. Essaie chaque jeu **d'abord avec ce que l'archive installe**, puis avec la nouvelle DLL. Les deux
   résultats comptent : les joueurs Linux ont aujourd'hui la version de l'archive.

Nouveautés à regarder sous Wine (sous Windows, toutes ont été vues en jeu) :

| Clé de l'ini | Jeux | Ce qu'elle fait | Quoi vérifier sous Linux |
|---|---|---|---|
| `MouseFrameRate=30` | HP7a, HP7b | La caméra tournait selon « mouvement de la souris × durée de l'image » ; elle répond maintenant comme à 30 images/s quelle que soit la cadence. | Le journal dit `Input: mouse scaled to 30 frames per second`. La caméra suit la souris sans à-coups ni inversion. |
| `FitToScreen=1` | tous (HP4-HP7b) | Une fenêtre à bordure plus grande que la place libre de l'écran est réduite dedans, même si le jeu la redimensionne. | Avec `WindowStyle=2` : la fenêtre ne passe pas sous le panneau de KDE ; ligne `too big for the screen's free area` au journal. Wayland/XWayland peut répondre autrement que Windows : note ce qui se passe. |
| `DPIAware=1` | HP5, HP6 | Sous Windows à 125 %, HP6 en fenêtre était agrandi du facteur d'échelle. | Rien à voir à 100 %. Si KDE est réglé à plus de 100 %, la fenêtre a la taille demandée. |
| `ShadowMapScale=4` | HP6 | Ombres ×4, choisies par Ludo dehors. | **Coût sur l'Intel UHD** : images/s (`ShowFPS=1` ou le panneau F11) avec 4 puis 1, même scène. Si c'est injouable, dis-le avec les chiffres. |
| `GreenRestraint=1.00` | HP6 | Retire la teinte menthe des collines et du ciel. | Juste que l'image s'affiche ; le goût a été jugé sous Windows. |
| `AudioStreamGuard` | HP4 | Sous Windows, environ un démarrage sur dix plantait 2 s après le « Oui » de l'invite de sauvegarde automatique. | Une dizaine de démarrages jusqu'à l'invite, « Oui » : combien de plantages. |
| `TextureDetail=2` | HP5, HP6 | Démarre en « Qualité » quand le registre n'a pas encore d'`OptionLOD`. | **Jamais vu en jeu, même sous Windows** : Options → Vidéo d'une installation neuve dit « Qualité ». |

### Un défaut probable à confirmer en premier : `xinput1_3` sans surcharge

Les archives de HP5 à HP7b livrent un **`xinput1_3.dll`** du correctif (manette PlayStation, barre lumineuse,
manette reconnue dès le démarrage). Le catalogue ne déclare pour eux que `"dll_overrides": ["d3d9"]`. Or Wine
remplace en silence une DLL livrée par la sienne quand il en a une du même nom (vu pour `d3d9`, voir
`docs/LINUX.md` § 3). Sous Linux, la DLL manette du correctif ne serait donc **jamais chargée**.

1. Lance HP5 (ou HP6) par le launcher, manette branchée si possible. Regarde si `HP5/xinput_accio.log`
   est écrit ou mis à jour, et cherche `xinput1_3` dans `_Launcher/logs/wine-hp5.log` (avec
   `WINEDEBUG=+loaddll` si besoin : `native` ou `builtin`).
2. Si c'est `builtin` : ajoute `"xinput1_3"` à `dll_overrides` de **hp5, hp6, hp7a, hp7b** dans
   `src/data/games.json` (l'embarqué : le catalogue 0.35 n'est pas encore publié, pas de nouveau numéro),
   relance, et vérifie que le journal du correctif apparaît. Mets à jour `docs/LINUX.md` § 3 et la ligne
   `dll_overrides` de `CLAUDE.md`. Tests verts.

### Jeu par jeu

| Jeu | Déjà fait | À faire |
|---|---|---|
| HP1 | Menu atteint par le launcher (d3dx11_43 + d3dcompiler_43). | Charger une partie, jouer une minute, Alt+Tab aller-retour, quitter par le menu. `HP.ini` reste en `D3D11Drv` après la sortie. |
| HP2 | Installé, jamais lancé. | Premier lancement par le launcher : le bandeau demande-t-il les mêmes composants que HP1 (déjà dans le préfixe) ? Menu, nouvelle partie, Alt+Tab. |
| HP3 | Rien. | Installer par le launcher, lancer (dgVoodoo : surcharges `d3d8 d3d9 ddraw msvcr70`). Menu, une partie, cadence ≤ 60. Note ce que dit `wine-hp3.log` sur les DLL chargées. |
| HP4 | Rien. | Lancer ; les touches ZQSD du préréglage sur le clavier du portable (la disposition se lit par `VkKeyScan`, sous Wine elle peut différer) ; l'invite de sauvegarde (voir `AudioStreamGuard`). |
| HP5 | Rien. | Lancer, puis `xinput1_3` (ci-dessus) ; `TextureDetail` ; Alt+Tab, le pointeur reste visible au-dessus du jeu. |
| HP6 | Cinématique jouée sans gel ; Meta géré. | Le gel ancien (cadence tombée à ~3 images/s) : surveiller les images/s sur 10 min de partie. Puis la nouvelle DLL (ombres ×4, coût). `vcrun2005` : le launcher le demande-t-il, et le jeu en a-t-il besoin (essai sur une copie du préfixe, comme pour HP1) ? |
| HP7a | Rien. | Installer par le launcher : le rangement dans `HP7/pc/`, l'écriture de `Locale` + `Install Dir` par `regedit` dans le préfixe (la boîte de prévenance s'affiche, pas d'UAC), `d3dx9_37`, VC++ 2005. Le jeu démarre (s'il quitte en 0,5 s sans rien dire, c'est le piège du dossier `pc` : voir `CLAUDE.md`). Puis `MouseFrameRate` et `FitToScreen`. |
| HP7b | Rien. | Comme HP7a (`Locale=fr`, VC++ 2008). Surveillance du gel (voir plus haut). |

Si un jeu ne démarre pas, la cause passe avant le reste : journaux, verbes winetricks essayés **sur une copie
du préfixe**, un à la fois, et ne déclarer que ce qui est prouvé (`requires` dans l'embarqué, comme HP1).

### Après l'audit Windows de ton commit 9998e0d (à faire en premier)

L'audit valide `xinput1_3` et le retrait de dgVoodoo. Il a trouvé un défaut, corrigé côté Windows :

1. **HP3 : le plafond de 60 images/s était parti avec dgVoodoo.** Sous Windows, c'est son `dgVoodoo.conf`
   (`FPSLimit = 60`) qui le tient, et HP3 ne doit **jamais** dépasser 60. Le catalogue porte maintenant
   `"max_fps": 60` pour hp3, que le launcher passe en `DXVK_FRAME_RATE=60` (journal du launcher :
   `plafond 60 ips`). **À vérifier** : lance HP3 par JOUER avec `DXVK_HUD=fps` exporté avant de démarrer le
   launcher depuis les sources. Le compteur doit rester ≤ 60, y compris si tu peux brancher un écran à plus de
   60 Hz. Fais-en une contre-épreuve avec `DXVK_FRAME_RATE=0` (sans plafond) : si le compteur ne dépasse pas
   60 non plus, c'est la synchro de l'écran qui limite, et le test ne prouve rien. Dis-le alors.
2. **HP7a/HP7b et `xinput1_3`** : les archives installées sous Windows n'ont **pas** de `xinput1_3.dll`
   (seuls HP5 et HP6 en livrent un). La surcharge `n,b` retombe alors sur la DLL de Wine : sans danger. Vérifie
   juste, à l'installation de HP7a, que la manette (ou le clavier) marche.
3. **HP2, menu vide** : tu notes que le jeu efface lui-même `Running.ini` 13 s après le lancement, et que
   l'autodétection tourne. Chez HP1, c'est exactement le cas où le moteur réécrit `GameRenderDevice` et plante
   au rechargement du rendu. Relève `System/HP2.ini` (ou l'ini utilisateur dans le préfixe) **pendant** que le
   jeu tourne, pas seulement après : `GameRenderDevice` vaut-il `D3DDrv` à ce moment-là ? Ne force pas le plein
   écran (ni `StartupFullscreen`, ni Alt+Entrée) : chez HP1, c'est ce geste qui plante sans `Running.ini`.
   La comparaison avec Windows sera faite ici.

### Restes du premier passage

- Préparer Wine **pendant** un téléchargement (retour 3, sens 2), le bouton Annuler de la préparation, et le
  double clic sur JOUER.
- D : agrandir la fenêtre du launcher sous KWin (pas dans gamescope : en session KDE normale, Ludo présent).
- L'AppImage (`./build.sh`) : refaire HP1 et un jeu à correctif avec elle.
- Supprimer les copies `~/Accio-essais/pfx-*` (≈ 700 Mo chacune) **après avoir demandé à Ludo**.

### Rapport de ce passage

Dans `RETOUR_BAZZITE.md`, un tableau par jeu : démarre ou non, ce qui a été essayé, ce qui casse (lignes de
journal), verbes winetricks prouvés. Puis la conclusion sur `xinput1_3`, et les mesures d'images/s de HP6
(ombres ×1 / ×4). Tout ce qui demande de toucher à la DLL du correctif : décris, la session Windows corrige.

---

## Premier passage (2026-09-30) : fait, gardé pour mémoire

## Ce que tu as le droit de faire, et pas

**Autorisé pour cette mission** (Ludo l'a demandé explicitement) :
- lancer **HP1 à HP6**, autant de fois qu'il faut, par le launcher ou à la main (`umu-run`) ;
- installer des verbes winetricks **dans le préfixe du launcher**, après l'avoir sauvegardé ;
- créer un venv Python dans le dépôt, modifier le code du launcher, ajouter des tests.

**Interdit :**
- ~~HP7a et HP7b (hp7 / hp8) : ne jamais les lancer.~~ Levé au deuxième passage (voir plus haut).
- Supprimer une sauvegarde de jeu. Sauvegarder AVANT tout essai (voir plus bas), restaurer à l'identique.
- Commit ou push : **Ludo commit lui-même.** Jamais de trailer `Co-Authored-By`.
- Installer quoi que ce soit sur le système (`rpm-ostree`, flatpak, toolbox, paquets) : demander à Ludo.
  Un venv dans le dépôt et les verbes winetricks dans le préfixe Accio ne comptent pas.
- Toucher au catalogue distant (`accio-launcher-games`) ou publier quoi que ce soit.
- Télécharger des mods. Les runtimes Microsoft par winetricks sont permis : c'est ce que fait le launcher.
- **HP1/HP2** : jamais `StartupFullscreen=True`, jamais retirer `Running.ini` (voir `CLAUDE.md`, quirks UE1).
  **HP3** : jamais au-delà de 60 ips.
- Écrire des scripts par l'entrée standard (`python3 - <<EOF`) : écris un fichier `.py`, puis exécute-le.

**Son coupé pendant les essais** : `wpctl get-volume @DEFAULT_AUDIO_SINK@` pour noter l'état,
`wpctl set-mute @DEFAULT_AUDIO_SINK@ 1` pendant les essais, puis remets l'état noté.
Si Ludo utilise le portable pendant que tu travailles, demande-lui avant de faire apparaître un jeu à l'écran.

## Mise en place

1. Ferme l'AppImage 1.1.2 si elle tourne : instance unique, et elle partage la configuration.
2. Depuis le dépôt : `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt`
3. `.venv/bin/python -m pytest` doit être vert. Sous Linux, les ~26 tests sautés sous Windows tournent :
   c'est la première fois qu'ils tournent sur un vrai Linux avec Wine. Signale tout échec.
4. `.venv/bin/python main.py` lance le launcher depuis les sources, sur les mêmes données
   (`~/Games/AccioLauncher`, `_Launcher/config.json`). Pour le détail du journal : `ACCIO_JOURNAL=debug`.
5. Pour la vérification finale, construis l'AppImage (`./build.sh`) et refais les essais clés avec elle.

**Sauvegarde, avant le premier lancement de jeu et avant tout winetricks :**

```sh
d=~/AccioSauvegardes/$(date +%F_%H%M) && mkdir -p "$d"
cp -a ~/Games/AccioLauncher/_Launcher/prefixes "$d"/
```

Le préfixe (`_Launcher/prefixes/umu`) contient les sauvegardes des jeux
(`drive_c/users/steamuser/Documents`) et leur registre (`user.reg`, `system.reg`).
Vérifie d'abord la place libre (`df -h ~`).

**Journaux utiles** (`~/Games/AccioLauncher/…`) :
- `_Launcher/logs/accio_launcher.log` : le launcher ;
- `_Launcher/logs/wine-<jeu>.log` : ce que Proton a dit au dernier lancement ;
- `_Launcher/logs/wine-preparation.log` : la création du préfixe et winetricks ;
- `HP1/System/HP.log` : le moteur de HP1 ;
- `HP6/d3d9_accio.log` : le correctif de HP6.

## Contexte : les retours de Ludo sur l'AppImage 1.1.2

Ludo a testé l'AppImage 1.1.2, **hors ligne** (DNS en échec). Le launcher a trouvé tout seul umu
(`/usr/bin/umu-run`) et GE-Proton10-34. Le préfixe avait `vcrun2022` ; Visual C++ 2005 et 2008 manquaient.
HP1 v1.2 et HP6 v1.1 étaient installés.

1. Bandes-annonces : le son et les boutons marchent, mais l'image reste celle du jeu, sans vidéo.
2. La préparation de Wine et de Visual C++ ne montrait pas d'avancement. La barre de statut disait
   encore « installation de Visual C++ » alors que le jeu était déjà ouvert.
3. Pendant la préparation, Ludo a pu lancer l'installation de HP1 (et son Visual C++).
4. La fenêtre du launcher refusait de s'agrandir pendant une action en cours.
5. **HP1 plante au démarrage** : « Critical Error: Init: Initializing Direct3D failed.
   History: UWindowsViewport::TryRenderDevice <- UWindowsViewport::OpenWindow <- UGameEngine::Init <- InitEngine ».
6. **HP6 s'est figé sur la cinématique d'une nouvelle partie** : le son continuait, l'image non.
   Ludo avait peut-être appuyé sur la touche Meta.
7. Plus d'**une minute** entre le clic sur JOUER et l'ouverture du jeu, pour HP1 comme pour HP6.
8. Le diagnostic affichait `Documents : /var~/Games/…` : `scrub_user_paths` ne connaît pas `/var/home`.

## Déjà corrigé côté Windows (commit c321e5b), à VÉRIFIER ici

Rien de tout ceci n'a pu être vérifié sous Linux :

| Retour | Correction | Quoi vérifier |
|---|---|---|
| 1 | `main.py` pose `QT_FFMPEG_DECODING_HW_DEVICE_TYPES=""` sous Linux : le décodage matériel VAAPI donnait un `QVideoFrame.toImage()` vide. `video_player` journalise une fois une image non convertible. | La vidéo s'affiche en fond. Aucun avertissement « image » au journal. Coût CPU raisonnable (`top`). |
| 2 | La préparation s'affiche dans la barre du bas (`DownloadBar.show_preparation`) : étape, chrono, dernière ligne de winetricks (`preparation_wine.derniere_ligne`) et un bouton Annuler. À la fin : « Wine est prêt. » ou un échec. | Progression visible et vivante. Statut final juste. Annuler arrête bien winetricks : plus aucun processus `winetricks`/`wine` du préfixe. |
| 3 | Téléchargement refusé pendant la préparation (`on_download`), et préparation refusée pendant une opération (`preparer_wine`). | Essayer les deux sens. |
| 7 | La fenêtre reste avec « Démarrage de … » et se range quand le jeu prend la main, au plus tard après 120 s (`ui/retrait_differe.py`). Second clic sur JOUER refusé. Hors ligne, `UMU_RUNTIME_UPDATE=0` (`compat.signaler_reseau`). | Le comportement de la fenêtre. Un double clic ne lance pas deux jeux. |

Pour tester la barre de préparation, il faut un composant manquant. La tâche A ci-dessous en crée
naturellement un : HP1 réclamera `d3dx11_43`.

## Tâches, par ordre de priorité

### A. Prérequis non déclarés (probable cause du plantage de HP1)

Audit des imports des exécutables, fait sous Windows le 2026-09-30 :

- **HP1 et HP2** : `d3d11drv.dll` importe `d3dx11_43.dll` et `d3dcompiler_43.dll` (DirectX de juin 2010),
  ainsi que `msvcr100.dll`/`msvcp100.dll` (Visual C++ 2010). Au démarrage, il compile `System/d3d11drv/ASSAO.fx`
  via `D3DX11CompileFromMemory`. `HP.log` dit « Error creating device » ou « Error compiling effects file ».
- **HP5 et HP6** : importent `msvcr80.dll` (Visual C++ 2005). Seul HP7a le déclare aujourd'hui.

Sous Windows, ce manque ne se voit pas chez Ludo (tout est installé). Sous Wine, la compilation de
l'effet par les DLL internes de Wine est le suspect n° 1.

1. **Confirmer d'abord.** Lance HP1 et lis `HP1/System/HP.log` et `wine-hp1.log`. Puis, préfixe sauvegardé :
   `umu-run winetricks d3dx11_43 d3dcompiler_43`, avec les variables d'environnement que pose `compat.environnement`
   (`WINEPREFIX`, `PROTONPATH`, `GAMEID`…) ; relance. Si ça ne suffit pas, ajoute `vcrun2010`.
   Note précisément quel verbe fait démarrer le jeu : ne déclare que ce qui est prouvé.
2. **`src/core/system_checks.py`** : ajoute les identifiants `d3dx11_43`, `d3dcompiler_43` et `vcredist2010_x86`,
   dans `PREREQUIS` et `VERBES_WINETRICKS` (`d3dx11_43`, `d3dcompiler_43`, `vcrun2010`).
   - Windows : les deux DLL DirectX se cherchent dans SysWOW64, comme `check_directx9`, même page `DIRECTX9_URL`.
     VC++ 2010 ne passe PAS par WinSxS : `msvcr100.dll` et `msvcp100.dll` sont dans SysWOW64. Il faut une page
     d'aide Microsoft pour le VC++ 2010 x86.
   - Linux : `check_directx9` répond « présent », parce que Wine a ses DLL. Pour ces deux DLL, c'est faux : il faut
     la DLL **native** dans le préfixe (`drive_c/windows/syswow64/`, écarter `compat.est_dll_interne_wine`),
     ou le verbe dans `winetricks.log` (`_dans_le_prefixe`). Vérifie aussi la surcharge `native` que pose
     winetricks : Wine charge sinon sa propre DLL.
   - `invalidate_vcredist_cache` doit vider les nouveaux caches.
   - Tests à écrire, en simulant `sys.platform` comme les tests existants, pour qu'ils tournent aussi sous Windows.
3. **Catalogue** : dans `src/data/games.json` (l'exemplaire embarqué), ajoute `requires` à hp1 et hp2
   (`d3dx11_43`, `d3dcompiler_43`, `vcredist2010_x86`, selon ce qui est prouvé à l'étape 1) et à hp5 et hp6
   (`vcredist2005_x86`). Monte `catalog_version` à 0.35 **seulement après avoir lu le catalogue publié** :
   son adresse est le champ `catalog_url` en tête de `src/data/games.json` (`curl -s <adresse>`).
   Si le publié est en avance sur l'embarqué, pars du publié.
   Ne touche pas au dépôt distant : le launcher doit être publié avant le catalogue.
4. Vérifie en conditions réelles : sur HP1, le bandeau signale le manque, puis la préparation installe le verbe,
   avec la barre de la tâche du tableau plus haut. Ensuite HP1 démarre. Refais-le avec HP2 s'il est installé,
   ou installe-le par le launcher.

### B. Lenteur au lancement (plus d'une minute)

Mesure au lieu de deviner. Relève les temps entre le clic et la première image :
- premier et deuxième lancement du même jeu ;
- en ligne et hors ligne (coupe le Wi-Fi : `nmcli radio wifi off`, puis remets-le) ;
- `UMU_LOG=debug` pour voir où umu passe son temps (mise à jour de steamrt, `pressure-vessel`,
  mise à niveau du préfixe après un changement de version de Proton, wineserver).

Si une étape évitable domine, corrige-la dans `compat.py` (environnement, `PROTONPATH` absolu…),
avec un test. Si c'est incompressible, dis-le avec les chiffres.

### C. HP6 figé sur la cinématique

Lis d'abord `notes/HP6.md` du dépôt `Harry-Potter-PC-Fix` s'il est cloné sur le portable.
Refais une nouvelle partie (sauvegardes copiées d'abord), d'abord sans toucher au clavier, puis en appuyant
sur Meta pendant la cinématique. Lis `HP6/d3d9_accio.log` et `wine-hp6.log`. Cherche si le gel vient
du lecteur vidéo du jeu sous Wine, de la perte de focus (Meta ouvre le menu de KDE), ou du correctif.
**Le correctif (`d3d9.dll`) se compile uniquement sous Windows** : n'y touche pas. Décris ce que tu observes
avec les lignes de journal ; la session Windows fera la correction.

### D. Fenêtre impossible à agrandir pendant une action

Reproduis pendant une préparation de Wine et pendant un téléchargement : agrandir, bords, double clic
sur la barre de titre. Si la fenêtre est figée (le fil UI est bloqué), trouve l'appel bloquant
(`py-spy dump` depuis le venv, ou `faulthandler`) et déplace-le hors du fil UI.
Si c'est un défaut de redimensionnement sans cadre sous Wayland (`startSystemResize`), note-le.

### E. `scrub_user_paths` et `/var/home`

Sur Bazzite (Silverblue), `$HOME` vaut `/var/home/<nom>`, alors que `Path.home()` peut donner `/home/<nom>`
(lien symbolique). Le remplacement laisse `/var~`. Corrige dans `src/core/diagnostic.py`, en couvrant
les deux formes et le chemin résolu. Ajoute un test.

### F. Si tout le reste est fait

- Les autres jeux déjà installés (HP2 à HP5) : lancement, menu, chargement d'une partie, Alt+Tab.
  Note tout ce qui manque ou casse, avec les journaux.
- La barre lumineuse d'une manette PlayStation (`manette.py`, `/dev/hidrawN`), si une manette est branchée.

## Règles de travail

- **Tout doit rester vert** avant de rendre la main : `.venv/bin/python -m pytest` et `.venv/bin/python -m ruff check .`
- Tout code win32 derrière `sys.platform == "win32"`. Chaque chaîne visible passe par `tr()` et existe dans
  `src/data/i18n/en.json` et `es.json` (indentation 2, `ensure_ascii=False`).
- `src/ui/main_window.py` a un plafond de lignes testé : extrais plutôt que d'ajouter.
- Mets à jour `CLAUDE.md` pour tout module ou comportement nouveau, et le compte de tests.
- Aucun chemin personnel dans ce qui sera commité : le dépôt est public. Écris `~` au lieu de `/var/home/<nom>`.
- Captures d'écran éventuelles dans `~/Accio-essais/`, jamais dans le dépôt. Une capture de comparaison est
  une PAIRE avant/après, même scène.

## Rapport

Écris `docs/linux/RETOUR_BAZZITE.md` (Ludo le commitera, et la session Windows le lira). Mets-y :
- ce qui a été vérifié et marche, avec la preuve (ligne de journal, mesure) ;
- ce qui a été corrigé : fichiers, tests ajoutés, compte final de tests ;
- les mesures de temps de lancement (tableau) ;
- ce qui reste, avec les extraits de journaux utiles, surtout pour HP6 et tout ce qui touche au correctif ;
- les verbes winetricks PROUVÉS nécessaires, jeu par jeu ;
- l'état des sauvegardes : où est la copie, et la confirmation que les sauvegardes des jeux sont intactes
  (comparaison `diff -r` avec la copie, hors fichiers que les parties ont légitimement modifiés).

À la fin, dis à Ludo en quelques lignes ce qui marche, ce qui reste, et qu'il peut commiter.
