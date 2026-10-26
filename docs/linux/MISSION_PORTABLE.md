# Mission : le portable Bazzite, quatrième passage

Pour : Claude Code sur le portable Linux de Ludo (Bazzite, KDE Wayland, i3-1220P, Intel UHD).
Rédigé le 2026-10-20 par la session Windows. **Ce fichier se suffit à lui-même** : il remplace le
« Troisième passage » de `MISSION_BAZZITE.md`, qui n'a jamais été fait et qui est repris ici (bloc 1).

Tu travailles **seul et longtemps** : Ludo laisse le portable tourner et reviendra lire ton rapport.
Avance bloc par bloc, dans l'ordre. Un bloc bloqué ne bloque pas les suivants : note où tu t'es arrêté,
pourquoi, avec les journaux, et passe au suivant.

Réponds à Ludo **en français**, phrases simples, sans tirets cadratins, sans formules creuses.

---

## 0. À lire avant de commencer

Dans cet ordre, en entier :

1. `CLAUDE.md` du dépôt : toutes les règles du projet. Les pièges « Ce qui casse un jeu sans bruit » valent ici.
2. `docs/LINUX.md` : le portage (umu puis wine, préfixe partagé, chemins, surcharges de DLL, AppImage).
3. `docs/linux/RETOUR_BAZZITE.md` : ce que les deux premiers passages ont trouvé, et où ils se sont arrêtés.
4. Avant de toucher à un jeu : sa fiche `notes/HPx.md` dans le dépôt `Harry-Potter-PC-Fix`. Clone-le à côté
   s'il n'est pas sur le portable : `git clone https://github.com/ludvdber/Harry-Potter-PC-Fix.git`
   (dépôt public, lecture seule pour toi). Tout fait nouveau sur un jeu s'écrit dans SA fiche, en fin de
   section, avec la mention `(VU sous Bazzite le AAAA-MM-JJ)`.

## 1. Ce qui a changé depuis le deuxième passage (2026-10-01)

- **Launcher 1.2.2** publié (2026-10-17). Nouveautés qui touchent Linux et n'ont **jamais** été vues sous Linux :
  - le **folio** des huit jeux : il lit les sauvegardes dans le préfixe (`drive_c/users/steamuser/Documents/…`)
    et des images dans les paquets des jeux installés (`HPMenu.u`, `HP3_Menu.utx`, `data.big`, `.str`…) ;
  - **Mes années** : cartes des sauvegardes, statistiques par partie, « Sauvegardes » ;
  - la **galerie** des captures (F12 en jeu, HP4 à HP7b), rangées dans `Images › Accio Launcher` ;
  - les **versions** d'un jeu (changer de version garde sauvegardes et réglages) ;
  - le liseré et les coins de fenêtre (Windows 11 seulement, rien à voir sous Linux sauf l'absence d'erreur).
- **Catalogue 0.43 en ligne** (embarqué et distant identiques) : `"dll_overrides": ["winmm"]` ajouté à hp1 et hp2,
  `slots: "hp5"` pour les emplacements de HP5. **Personne n'a vérifié la surcharge `winmm` sous Wine** : c'est
  ta première priorité, les joueurs Linux l'ont déjà.
- **Correctif v2.1.0 publié** (2026-10-16) : https://github.com/ludvdber/Harry-Potter-PC-Fix/releases/tag/v2.1.0
  - `winmm.dll` pour HP1 et HP2 : plein écran sans cadre (`FillScreen`), assistant de HP1 sauté (`SkipSetup`),
    manette (Options → Échap, Share → Tab), Alt+Entrée avalé dans HP2, et **sous Wine seulement** pour HP2
    (`WineLauncherFix=1` dans son `winmm.ini`) : retrait en mémoire des deux `SetWindowPos` qui rendent le
    lanceur de HP2 **noir avec seulement « Quitter »**. C'est le « menu vide » vu au deuxième passage.
  - `dinput8.dll` pour HP3 (manette).
  - `d3d9.dll` HP4 à HP7b : `FitToScreen`, `MouseFrameRate`, plafond de cadence des cinématiques,
    `SSAAMaxHeight`, `TextureDetail`, couleurs, ombres, retour au premier plan, `AudioStreamGuard`.
  - Empreintes SHA-256 de la release : `winmm.dll` `b56e0ab3ca2e5f280630a2ba89adcee32786e4fd2b9344aef0dfba041c50ba2b`,
    `d3d9.dll` `1f1f67c1525e9e6f9e3d1ad33e19304696872e322ed039f04039dfbdc81bf030`,
    `dinput8.dll` `d99a42624685aa83e17e03926a6369ddefcfa7fcf6b2f9a8b3743474ac6e8963`,
    `xinput1_3.dll` `eca0f98dad52a021217154a14e8ec8fca08196edae752652c55c0b04a850d026`.
  - **Les archives des jeux ne sont peut-être PAS à jour** : Ludo ne refait une archive de jeu que par lots.
    Ce qu'un joueur Linux reçoit aujourd'hui, c'est le correctif de l'archive. Compare toujours
    (`sha256sum`) la DLL installée avec celle de la release, et note laquelle tu essaies.

## 2. Ce que tu as le droit de faire, et pas

**Autorisé** (Ludo l'a demandé pour cette mission) :
- lancer **HP1 à HP6**, autant de fois qu'il faut, par le launcher ou à la main (`umu-run`) ;
- installer un jeu par le launcher, le désinstaller, le réinstaller ;
- remplacer, pour un essai, une DLL ou un `.ini` du correctif dans le dossier d'un jeu, **après en avoir copié
  l'original**, et le remettre à la fin ;
- télécharger les zips de la release v2.1.0 du correctif (adresse ci-dessus), et vérifier leur SHA-256 ;
- installer des verbes winetricks **dans le préfixe du launcher**, après l'avoir sauvegardé ; préférer une
  **copie** du préfixe pour toute expérience (voir 3) ;
- créer un venv dans le dépôt, modifier le code du **launcher**, ajouter des tests, modifier le catalogue
  **embarqué** (`src/data/games.json`) si un essai le prouve nécessaire.

**Interdit :**
- **HP7a et HP7b** (`hp7`, `hp8`) : ne pas les lancer. Les installer pour vérifier le rangement dans `HP7/pc/`
  est permis ; les lancer, seulement si Ludo te le dit **par écrit dans cette conversation**. Raison : HP8 s'est
  figé à 100 % sur tous les cœurs sous Windows.
- Supprimer ou écraser une sauvegarde de jeu. Sauvegarder AVANT, restaurer à l'identique, prouver par `diff -r`.
- Commit ou push. **Ludo commite lui-même**, par l'interface de GitHub. Jamais de ligne `Co-Authored-By`.
- Installer quoi que ce soit sur le système (`rpm-ostree`, flatpak, toolbox, paquets). Demander à Ludo.
  Le venv dans le dépôt et les verbes winetricks dans le préfixe Accio ne comptent pas.
- Toucher au dépôt `accio-launcher-games` (catalogue distant) ou publier quoi que ce soit.
- Modifier les sources du correctif (`Harry-Potter-PC-Fix/source`) : il se compile **sous Windows seulement**.
  Tu décris (octets, adresses, lignes de journal, proposition de code dans ton rapport), la session Windows corrige.
- Toucher aux réglages du système (registre de l'hôte, KDE, verrouillage d'écran) sans demander.
- **HP1/HP2** : jamais `StartupFullscreen=True`, jamais retirer `Running.ini` du catalogue.
  **HP3** : jamais au-delà de 60 images/s volontairement.
- Écrire un script par l'entrée standard (`python3 - <<EOF`) : écris un fichier `.py`, puis exécute-le.
- Écrire « dgVoodoo » dans un texte affiché à l'écran ou un nom de fichier du dépôt : on dit « réglages graphiques ».
  Dans ton rapport et les journaux, le nom technique est permis.

**Son coupé** pendant les essais : `wpctl get-volume @DEFAULT_AUDIO_SINK@` pour noter l'état,
`wpctl set-mute @DEFAULT_AUDIO_SINK@ 1`, puis remets l'état noté à la fin.

**L'écran** : demande d'abord à Ludo s'il accepte de couper le verrouillage automatique pendant la mission
(c'est lui qui le fait). Sinon, fais comme au premier passage : `gamescope --backend headless`, captures par
`gamescopectl screenshot`, entrées par xdotool sur son XWayland. Si Ludo utilise le portable pendant que tu
travailles, demande avant de faire apparaître un jeu à l'écran.

## 3. Mise en place

1. Ludo a mis le dépôt à jour. Vérifie : `git log -1 --format='%h %cs %s'` doit être au moins du 2026-10-17
   (`3946929` ou plus récent), et `grep -m1 catalog_version src/data/games.json` doit dire `0.43`.
2. Ferme toute AppImage du launcher qui tourne (instance unique, même configuration).
3. Venv : `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt`
   (recrée-le s'il existe mais date d'avant le 2026-10-15).
4. Contrôles, à recopier dans le rapport :
   - `.venv/bin/python -m pytest -q` : sous Windows, 3331 réussis et 30 sautés. Sous Linux, le compte diffère
     (les tests Windows sautent, les tests Linux tournent). **Tout échec est un résultat** : relève-le, cherche
     la cause, corrige si c'est un défaut du launcher sous Linux.
   - `.venv/bin/python -m ruff check .` et `.venv/bin/python -m mypy` : propres.
   - `python3 tools/verifier_wine.py` (relevé seul, n'écrit rien) : recopie la sortie.
5. **Sauvegarde, avant le premier lancement de jeu** (vérifie d'abord `df -h ~`) :

   ```sh
   d=~/AccioSauvegardes/$(date +%F_%H%M) && mkdir -p "$d"
   cp -a ~/Games/AccioLauncher/_Launcher/prefixes "$d"/
   cp -a ~/Games/AccioLauncher/_Launcher/config.json ~/Games/AccioLauncher/_Launcher/sessions.json "$d"/
   ```

   Le préfixe contient les sauvegardes des jeux (`drive_c/users/steamuser/Documents`) et leur registre.
   Pour chaque jeu dont tu remplaces un fichier : copie à part ses `.ini`, `.dll` du correctif et `.log`.
6. Lance le launcher depuis les sources : `ACCIO_JOURNAL=debug .venv/bin/python main.py`.

**Journaux utiles** (`~/Games/AccioLauncher/…`) :
- `_Launcher/logs/accio_launcher.log` : le launcher (ligne `Lancement sous … surcharges …` à chaque JOUER) ;
- `_Launcher/logs/wine-<jeu>.log` : ce que Proton a dit au dernier lancement ;
- `_Launcher/logs/wine-preparation.log` : création du préfixe et winetricks ;
- correctif : `winmm_accio.log` (HP1/HP2, dans `System`/`system`), `dinput8_accio.log` (HP3),
  `d3d9_accio.log` (HP4 à HP7b), `xinput_accio.log` (HP5 à HP7b) ; leur première ligne porte la version ;
- moteurs Unreal : `HP.log` (HP1) et le journal de HP2, dans le dossier Documents du préfixe.

**Savoir quelle DLL est chargée** (jeu en cours) :
`grep -i -E 'winmm|d3d9|dinput8|xinput' /proc/$(pgrep -f -i '<exe>' | head -1)/maps`.
Un chemin dans le dossier du jeu = celle du correctif ; un chemin dans les fichiers de Proton = celle de Wine.
Si besoin : `WINEDEBUG=+loaddll` (dit `native` ou `builtin`).

---

## Bloc 1. HP1 et HP2 : la surcharge `winmm` du catalogue 0.43 (PRIORITÉ ABSOLUE)

Les joueurs Linux ont le catalogue 0.43 depuis plusieurs jours. Il faut savoir s'il marche.

**Préparation.** Si HP1 ou HP2 n'est pas installé, installe-le par le launcher. S'il l'a été avant le
2026-10-07, son dossier n'a peut-être pas de `winmm.dll` : « Vérifier / réparer » le remet. Relève pour chacun
`sha256sum` de `HP1/System/winmm.dll` et `HP2/system/winmm.dll`, et compare avec la release (`b56e0ab3…`).
Télécharge `HP1-Philosophers-Stone.zip` et `HP2-Chamber-of-Secrets.zip` de la release v2.1.0 dans
`~/Accio-essais/correctif-2.1.0/`, vérifie leurs SHA-256 (tableau de la release), décompresse.

**Essai A : ce qu'installe l'archive** (ce qu'ont les joueurs). Pour HP2, puis HP1 :
1. JOUER. Recopie la ligne `Lancement sous … surcharges …` : elle doit contenir `winmm`.
2. Jeu en cours : quelle `winmm.dll` est chargée (voir 3). Recopie les premières lignes de `winmm_accio.log`
   s'il existe (il n'existe QUE si celle du correctif s'est chargée).
3. Note : le lanceur de HP2 (fond et quatre boutons, ou noir avec seulement « Quitter ») ; la fenêtre (cadre
   ou non, plein écran ou non) ; pour HP1, l'assistant « première configuration » s'ouvre-t-il ?
4. Quitte par le menu du jeu.

**Essai B : la `winmm.dll` et le `winmm.ini` de la release 2.1.0** (originaux copiés d'abord). Ne lance pas
« Vérifier / réparer » après les avoir posés : il remettrait ceux de l'archive. Refais 1 à 4.
- HP2 : `winmm_accio.log` doit montrer `WineLauncherFix=1` puis une ligne `Launcher:` (attendu :
  `Launcher: two SetWindowPos taken out at …`). Recopie-la, quelle qu'elle soit. Le lanceur doit montrer son
  fond et ses quatre boutons. Va jusqu'en jeu par « Nouvelle partie » (une partie neuve dans un emplacement
  libre : relève d'abord la liste des sauvegardes) ou « Charger partie », joue une minute, quitte.
- HP1 : pas de ligne `Launcher:` (la correction n'est active que pour HP2). Rien ne doit changer par rapport à A,
  sauf si l'archive avait une DLL plus ancienne : dis ce qui change.

**Essai C, si la DLL du correctif se charge** :
- HP1 : Alt+Entrée deux fois, puis Alt+Tab aller-retour ; le jeu doit continuer. Relève `GameRenderDevice`
  dans `HP.ini` avant et après : il doit rester `D3D11Drv.D3D11RenderDevice`.
- HP2 : Alt+Entrée doit être sans effet (avalé), le menu ne doit pas se casser.
- Manette PlayStation si Ludo en a branché une : Options → menu (Échap), Share → Tab dans HP2.

**Si le lanceur de HP2 reste noir avec la DLL 2.1.0** : relève `winmm_accio.log` en entier,
`wine-hp2.log` (80 dernières lignes), le journal du moteur, et `WINEDEBUG=+loaddll`. La cause probable est alors
que la DLL du correctif n'est pas chargée dans le processus du lanceur, ou que le motif d'octets n'est pas
trouvé (la ligne `Launcher:` le dit). Ne cherche pas à modifier `Game.exe`.

**Si la surcharge ne prend pas** (Wine charge sa `winmm`) : c'est un défaut du launcher ou du catalogue.
Cherche pourquoi dans `src/core/compat.py` (construction de `WINEDLLOVERRIDES`), corrige, ajoute un test.

**À la fin du bloc** : remets les DLL et `.ini` d'origine, vérifie les sauvegardes (`diff -r` avec la copie).

## Bloc 2. Les six jeux avec la 1.2.2 : installer, lancer, quitter

Pour HP1 à HP6, chacun : installation par le launcher s'il manque, JOUER, menu atteint, une minute en jeu
(charger une partie existante si possible, sinon nouvelle partie), Alt+Tab aller-retour, quitter par le menu.
Relève : la ligne `surcharges`, le temps du clic à la fenêtre, les DLL du correctif chargées, ce qui casse.

Points précis par jeu :

| Jeu | Ce qu'il faut regarder en plus |
|---|---|
| HP1 | Après Alt+Tab, `HP.ini` reste en `D3D11Drv`. Les dragées (`Dragées surprises`) du folio après la partie. |
| HP2 | Le lanceur (bloc 1). En jeu : le menu de pause, les sorts. |
| HP3 | Voir bloc 4 (cadence). La manette par `dinput8.dll` du correctif si une est branchée : `dinput8_accio.log`, et Wine charge-t-il `dinput8` natif ? Le catalogue de hp3 déclare `["msvcr70"]` seulement : si `dinput8` du correctif n'est pas chargé, c'est un défaut à corriger dans l'embarqué (même raisonnement que `xinput1_3` au 2e passage). |
| HP4 | `d3d9_accio.log` : version de la DLL. L'invite de sauvegarde automatique (10 sur 10 sans plantage au 2e passage). ZQSD en partie (disposition lue par `VkKeyScan`). |
| HP5 | **Jamais lancé sous Linux.** `xinput1_3` natif chargé. Options → Vidéo d'une installation neuve : « Qualité » (`TextureDetail`). Le pointeur après Alt+Tab. `vcrun2005` : nécessaire ou non (essai sur une **copie** du préfixe sans lui). |
| HP6 | 10 minutes de partie : la cadence ne doit pas s'effondrer (le gel ancien : ~3 images/s). Ombres (`ShadowMapScale` 4 puis 1, même scène) : images/s sur l'Intel UHD, chiffres à l'appui. |

Si un jeu ne démarre pas, la cause passe avant le reste : journaux, puis verbes winetricks **sur une copie du
préfixe**, un à la fois. Ne déclare au catalogue embarqué (`requires`) que ce qui est prouvé.

## Bloc 3. Folio, Mes années, galerie, versions sous Linux

Rien de tout ceci n'a jamais tourné sous Linux. Avec les jeux installés et au moins une sauvegarde par jeu
(les parties du bloc 2 en créent) :

1. **Folio** de chaque jeu installé (bouton du folio sur la fiche du jeu) : la page s'ouvre, les sauvegardes
   sont trouvées dans le préfixe, les chiffres correspondent à ce que le jeu montre, les images s'affichent
   (cartes, icônes des tuiles, pentagones des séries HP3, boucliers HP4, écussons HP6). Une page qui reste vide
   ou un chiffre faux : relève le chemin cherché (journal en `debug`) et le contenu réel du dossier.
2. **Fiche du jeu** : pour HP1 et HP3 avec une sauvegarde, le bloc « Dernière partie … » remplace la description.
3. **Mes années** : les cartes des sauvegardes (images HP1 et HP2 comprises), les statistiques, et
   « Sauvegardes » sur une **copie** : restaure une copie, vérifie que le jeu la charge, puis remets
   l'état d'origine depuis ta sauvegarde.
4. **Galerie** : F12 dans HP4, HP5 ou HP6 ; la capture apparaît-elle dans la galerie ? Où le jeu l'écrit-il
   dans le préfixe, et où le launcher la range-t-il sur l'hôte (`~/Images/Accio Launcher` ou `~/Pictures/…`) ?
5. **Versions** d'un jeu (fenêtre des versions) : changer de version sur HP1 (s'il en a plusieurs), puis
   revenir ; sauvegardes et réglages conservés (`diff -r`).
6. **Mise en page** sous les vraies polices du portable : redimensionne la fenêtre du launcher à sa taille
   minimale (980 × 660) puis plein écran, sur chaque folio : rien ne doit être coupé à droite (chiffres,
   comptes « 1 / 15 »), les tuiles passent sur deux lignes quand elles manquent de place.
   Puis `xvfb-run -a .venv/bin/python tools/audit_geometrie.py` (ou sur la session réelle si elle est libre) :
   recopie la conclusion.

Tout défaut du launcher : corrige-le dans `src/`, avec un test qui simule `sys.platform` (les tests Linux
tournent aussi sous Windows), sans casser Windows.

## Bloc 4. HP3 : le plafond de 60 images/s sous Linux (recherche)

État au 2e passage : `DXVK_FRAME_RATE=60` est posé mais **sans effet**, parce que HP3 tourne sous wined3d
(`d3d8.dll` de Wine), pas sous DXVK ; les réglages graphiques de Windows (les DLL `d3d8/d3d9/ddraw` qui
plafonnent sous Windows) plantent sous Proton (« General protection fault » dans `UD3DRenderDevice::SetRes`).
Sur l'écran 60 Hz du portable, la synchro limite de toute façon : le défaut ne se voit qu'au-delà de 60 Hz.

À chercher, sans rien casser :
1. Proton récent : `PROTON_DXVK_D3D8=1` avec les DLL des réglages graphiques **écartées** donnait une image
   figée sur l'introduction. Réessaie avec le GE-Proton installé aujourd'hui (note sa version), et avec
   `dinput8.dll` du correctif en place ou non : le figement venait-il d'une entrée, du son, de la vidéo ?
2. Un limiteur hors DXVK : `WINE_FPS_LIMIT` ou équivalent selon la version de Proton/wined3d, ou une option du
   moteur (cherche dans `HP3/system/*.ini` une clé de cadence ; la fiche `notes/HP3.md` en parle peut-être).
3. Mesure toujours avec une contre-épreuve (`vblank_mode=0`, ou un compteur indépendant de la synchro :
   `WINEDEBUG=+fps`). Si rien ne prouve le plafond au-delà de 60 Hz, dis-le : c'est une réponse.

Ne change le catalogue embarqué que si une solution est **prouvée**. Sinon, rapport seulement.

## Bloc 5. Le launcher lui-même sous Linux

1. **Préparation de Wine** : le bouton Annuler (plus aucun processus `winetricks`/`wine` du préfixe ensuite),
   préparer pendant un téléchargement (doit être refusé avec un message), télécharger pendant une préparation
   (refusé, toast).
2. **Double clic sur JOUER** : un seul jeu lancé.
3. **Fenêtre** sous KWin : agrandir, restaurer, bords, double clic sur la barre de titre, **pendant** un
   téléchargement et une préparation. Ce point a besoin de vrais clics : fais-le avec Ludo s'il est là,
   sinon note-le comme restant.
4. **Zone de notification** : le launcher s'y range au lancement d'un jeu et revient à la fin.
5. **Manette PlayStation** (si branchée) : la barre lumineuse (`manette.py`, `/dev/hidrawN`).
6. **Désinstallation** d'un jeu (prends HP3 ou HP4, réinstalle-le ensuite) : le dossier du jeu part, les
   sauvegardes du préfixe restent, rien d'autre n'est touché dans `_Launcher/`.
7. **AppImage** : `./build.sh` (6 étapes, l'audit de géométrie passe par `xvfb-run`). Lance l'AppImage produite,
   refais HP1 (bloc 2) avec elle. Relève sa taille et le temps de démarrage du launcher.

## Bloc 6. Si tout le reste est fait

- HP7a / HP7b : installation seulement (rangement dans `HP7/pc/`, écriture de `Locale` et `Install Dir` dans le
  registre du préfixe par `regedit`, la boîte de prévenance s'affiche, pas d'UAC). **Pas de lancement** sans
  l'accord écrit de Ludo.
- Les copies d'essai `~/Accio-essais/pfx-*` des passages précédents (≈ 700 Mo chacune) : demande à Ludo avant de
  les supprimer.
- Relis `docs/LINUX.md` et corrige ce que tes essais contredisent (sans numéros de ligne : par fonction).

---

## Règles de travail

- **Tout reste vert** avant de rendre la main : `pytest`, `ruff check .`, `mypy`.
- Tout code win32 derrière `sys.platform == "win32"`, avec un repli sensé. Jamais de lettre de lecteur hors code gardé.
- Chaque texte visible passe par `tr()` et existe dans `src/data/i18n/en.json` et `es.json`
  (indentation 2, `ensure_ascii=False`). N'affiche jamais un état normal (« rien n'a été modifié », « Prêt ») :
  seul un changement ou un problème se dit. N'explique pas à l'écran COMMENT une information est obtenue.
- `src/core` est typé en **strict** (mypy) : tout code neuf aussi. Pas de `assert` pour rassurer mypy.
- `src/ui/main_window.py` a un plafond de lignes testé : extrais plutôt que d'ajouter.
- Module ou comportement nouveau : mets à jour `docs/claude/ARCHITECTURE_CORE.md` ou `ARCHITECTURE_UI.md`,
  et le compte de tests dans `CLAUDE.md` (en précisant « sous Linux »).
- Deux catalogues : si tu modifies l'embarqué, écris dans le rapport la modification exacte à reporter dans
  `accio-launcher-games` (Ludo le fera, en partant du catalogue publié). Pas de nouveau numéro de catalogue.
- Aucun chemin personnel dans ce qui sera commité (dépôt public) : `~` au lieu de `/var/home/<nom>`.
- Captures dans `~/Accio-essais/`, jamais dans le dépôt. Une comparaison est une PAIRE avant/après, même scène.
- Ne déclare jamais un résultat que tu n'as pas vu : « VU » (avec la preuve), « relevé » (dans un fichier),
  ou « supposé » (et pourquoi).

## Rapport

Dans `docs/linux/RETOUR_BAZZITE.md`, **en haut du fichier**, sous le titre
« Quatrième passage (AAAA-MM-JJ) », sans effacer le reste :

1. **En bref** : un tableau, une ligne par bloc : fait / en partie / non fait, et la conclusion en une phrase.
2. **Machine** : noyau, umu, version de GE-Proton, Python, commit du dépôt.
3. **Tests** : comptes pytest sous Linux (réussis / sautés / échecs, avant et après tes corrections), ruff, mypy,
   sortie de `verifier_wine.py`.
4. **Bloc 1** : pour HP2 puis HP1, un tableau A (archive) / B (release 2.1.0) : SHA-256 de la DLL, ligne
   `surcharges`, chemin de la `winmm.dll` chargée, ligne `Launcher:`, lanceur, fenêtre, assistant (HP1),
   Alt+Entrée, manette. Puis la phrase : « le lanceur de HP2 est réparé sous Linux » ou non, et ce qui reste.
5. **Bloc 2** : un tableau par jeu (démarre, temps, DLL chargées, ce qui casse avec les lignes de journal,
   verbes winetricks prouvés). Les images/s de HP6 (ombres ×1 / ×4).
6. **Blocs 3 à 6** : ce qui marche (avec la preuve), ce qui a été corrigé (fichiers, tests ajoutés), ce qui reste.
7. **Pour la session Windows** : tout ce qui demande de toucher au correctif ou au catalogue distant, décrit
   précisément (jeu, clé, octets, journal, proposition).
8. **Sauvegardes** : où est la copie, et la preuve que les sauvegardes des jeux sont intactes (`diff -r`, hors
   fichiers que les parties ont légitimement modifiés). Ce qui a été remis à l'identique (DLL, `.ini`, son).

À la fin, dis à Ludo en quelques lignes : ce qui marche, ce qui reste, et la liste des fichiers à commiter
(dépôt AccioLauncher, et notes du dépôt Harry-Potter-PC-Fix s'il y en a). `git status` ne doit contenir que ça.
