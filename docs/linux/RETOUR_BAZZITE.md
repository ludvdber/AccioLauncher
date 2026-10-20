# Quatrième passage (2026-10-20) — en cours (rapport d'étape mis à jour à 17 h 15, après la reprise)

Portable Bazzite, launcher **depuis les sources** (commit `4f758f9`, catalogue 0.43), jeux lancés par JOUER sauf mention « manuel ». Les essais à l'écran se font dans un **gamescope headless** (`--backend headless`, Xwayland `:1`, captures `gamescopectl screenshot`, entrées `xdotool`) : le verrouillage d'écran de KDE a coupé les deux passages précédents et Ludo n'était pas là pour le désactiver. Captures, journaux et notes par jeu : `~/Accio-essais/` (`notes-HP1.md` … `notes-HP6.md`, `notes-bloc3.md`).

## En bref

| Bloc | État | Conclusion |
|---|---|---|
| 0. Mise en place | fait | venv recréé, contrôles verts (ci-dessous), préfixe et config copiés avant tout jeu. Tous les jeux **mis à jour ou installés** par le launcher (HP1 1.3, HP2 1.2, HP3 1.3, HP4 1.2, HP5 1.3, HP6 1.2, HP7b 1.2 ; **HP7a 1.1 installé seulement à la reprise**, 16:11 : il manquait). |
| 1. `winmm` HP1/HP2 (0.43) | **fait** | **La surcharge prend** : `surcharges winmm` au journal, `HP2\system\WINMM.dll : native`, `winmm_accio.log` écrit, pour HP1 comme HP2, avec la DLL de l'archive (2.0.1) comme avec la 2.1.0. **Mais le lanceur de HP2 reste noir avec la 2.1.0** : la paire retirée par `WineLauncherFix` n'est pas celle qui s'exécute (détail et proposition plus bas). HP1 : assistant sauté, Alt+Entrée ×2 et fenêtre devant sans dégât, `GameRenderDevice` conservé. |
| 2. Six jeux avec la 1.2.2 | en partie | HP1, HP2, HP3, HP4, HP5 lancés (tableaux plus bas). **HP5 démarre sans `vcrun2005`**. **HP6 fait : 10 min sans effondrement (31,8 à 45,4 images/s), ombres ×4 = −16 % (35,5 contre 42,3) sur la même scène.** Mais **l'incrustation du correctif (F10/F11) fait planter le GPU Intel** et fige le jeu pour toujours (détail plus bas). |
| 3. Folio, Mes années, galerie, versions | en partie | Audit de géométrie : **OK, 0 défaut** (sur la session réelle, `xvfb-run` n'existe pas sur Bazzite). Galerie : F12 dans HP4 écrit directement dans `~/Images/Accio Launcher/<jeu>/`. Folio : **s'ouvre pour les 8 jeux, sauvegardes trouvées dans le préfixe** (HP1 « Hall d'entrée de Poudlard » avec l'image, HP6 écussons/badges/chapitre). Mes années : cartes et statistiques OK. Restauration sur copie, galerie (affichage), versions, tailles : pas encore. |
| 4. HP3 à 60 images/s | fait (constat) | Inchangé : HP3 tourne sur le `d3d8` de wined3d (maps), `DXVK_FRAME_RATE=60` sans effet, dgVoodoo écarté. Rien de nouveau prouvé. |
| 5. Launcher sous Linux | en partie | Retour en zone de notification et retour à la fin de partie : vu 5 fois. Préparation de Wine : `vcrun2005` posé par le bandeau « Installer » en **12 s**, JOUER débloqué. Annuler (à faire sur `vcrun2008`, HP7b), double clic JOUER, fenêtre KWin, désinstallation, AppImage : à faire. |
| 6. HP7a/HP7b | en partie | Installés par le launcher : HP7b « 104 élément(s) rangé(s) dans pc/ », HP7a « 134 élément(s) rangé(s) dans pc/ » (16:11:33). `Install Dir`/`Locale` pas encore dans `system.reg` (écrits au lancement). Lancement : accordé par Ludo (« fais également hp7 et 8 que tu testeras à la fin »), pas encore fait. |

## Machine

Bazzite, noyau `7.2.7-ogc1.1.fc44.x86_64`, KDE Wayland (essais dans gamescope headless 1920×1080), umu-launcher 1.4.4, **GE-Proton10-34** (`~/.local/share/Steam/compatibilitytools.d`), Python 3.14.7 (venv du dépôt), dépôt AccioLauncher `4f758f9` (2026-10-20), dépôt Harry-Potter-PC-Fix `259ec54` (v2.1.0). Manette **DualShock 4 USB** (`054c:09cc`, `/dev/hidraw1` accessible, `js0`) branchée par Ludo à 11:20. Son coupé à 11:45 (`wpctl` : 0.40 [MUTED], à remettre : `wpctl set-mute @DEFAULT_AUDIO_SINK@ 0`).

## Tests et contrôles (avant toute modification ; aucune modification de code depuis)

- `pytest -q` : **3323 réussis, 38 sautés, 0 échec** (7 min 15). Les 38 sautés = 32 réservés à Windows + 6 `test_fonts.py` (Georgia).
- `ruff check .` : propre. `mypy` : propre (68 fichiers).
- `tools/verifier_wine.py` : famille umu, `/usr/bin/umu-run`, Proton GE-Proton10-34 ; préfixe `_Launcher/prefixes/umu` prêt, win64, ANSI cp1252, Documents `drive_c/users/steamuser/Documents` (`C:\users\steamuser\Documents`) ; winetricks : `d3dcompiler_43, d3dx11_43, vcrun2022` ; composants : `vcredist_x86` présent, **`vcredist2005_x86` MANQUANT, `vcredist2008_x86` MANQUANT**, `vcredist2010_x86`/`d3dx9_43`/`d3dx9_37`/`xinput1_3`/`d3dx11_43`/`d3dcompiler_43` présents ; registre disponible.
- Correctif 2.1.0 : les 12 fichiers de la release téléchargés dans `~/Accio-essais/correctif-2.1.0/`, **SHA-256 tous conformes** au tableau de la release (`sha256sum -c`).

## Bloc 1 — `winmm` (HP2 puis HP1)

**Ce qu'installent les archives** (relevé après mise à jour par le launcher) : HP1 1.3 et HP2 1.2 livrent `winmm.dll` **2.0.1** (sha `ce7f2576…` HP1, `cdc62e04…` HP2), pas la 2.1.0 (`b56e0ab3…`). Le `winmm.ini` de HP1 est identique à celui de la release ; celui de HP2 **n'a pas la clé `WineLauncherFix`** (6 lignes de moins). HP3 1.3 livre `dinput8.dll` 2.0.1 ; HP4/HP5/HP6/HP7b livrent un `d3d9.dll` sans numéro (`bf74b6bd…`, antérieur à 2.1.0, mais qui lit déjà `TextureDetail`, `FitToScreen`, `AudioStreamGuard`).

| HP2 | A : archive (2.0.1) | B : release 2.1.0 |
|---|---|---|
| sha256 `winmm.dll` | `cdc62e04…` | `b56e0ab3…` |
| ligne `Lancement sous …` | `surcharges winmm, plafond aucun` | idem |
| `winmm.dll` chargée (maps + `+loaddll`) | `HP2\system\WINMM.dll : native` + `winmm.dll` de Proton (chargée par le proxy, `179 of 193 functions`, 14 exports absents chez Wine) | idem |
| `winmm_accio.log` | `Accio Launcher PC fix 2.0.1 (winmm.dll)` ; `Settings: … BlockAltEnter=1 FillScreen=1 SkipSetup=0` ; pas de `Launcher:` | `… 2.1.0 (winmm.dll)` ; `Settings: … WineLauncherFix=1` ; **`Launcher: two SetWindowPos taken out at 10902583 (WineLauncherFix, under Wine)`** |
| lanceur « Menu principal » | **noir, seul « Quitter »** | **noir, seul « Quitter »** (Tab, Alt+N, clics aux positions des boutons : rien) |
| fenêtre | 480×556, cadre Wine | idem |
| Alt+Entrée, manette | injouable derrière le lanceur | idem |
| sortie | Quitter → code 0 | Quitter → code 0 |

**Pourquoi le lanceur reste noir avec la 2.1.0** (`WINEDEBUG=+win,+dialog` puis relais `user32.SetWindowPos` ; journaux `~/Accio-essais/hp2-B-windebug.log`, `hp2-B-relay.log`) :
- Le dialogue « Menu principal » (0x200d2, 480×556 à 720,262) contient un cadre `Static` 1061 (479×410) ; la **page** « MainMenu » (gabarit DIALOGEX 320×265, `WS_CHILD|WS_VISIBLE`) est un dialogue **enfant de ce cadre**, avec `&New Game` 3021, `&Load Game` 3020, `&Options` 3019 et le titre 1150. Créée à (0,0), `GetWindowRect` = (720,262)-(1200,693) : à sa place.
- Puis Game.exe appelle `SetWindowPos(page, HWND_TOPMOST, 717, 257, 486, 566, SWP_FRAMECHANGED)` (retour `0x10913023`) et `SetWindowPos(page, HWND_NOTOPMOST, 0,0,0,0, NOSIZE|NOMOVE)` (retour `0x1091303c`). 717,257 = centrage ÉCRAN d'une fenêtre 486×566 ; appliqué à une fenêtre **enfant**, c'est relatif au cadre : la page part en (1437,519)-(1923,1085), hors du dialogue, donc fond et trois boutons coupés (« Quitter » est un bouton du dialogue parent, pas de la page).
- La paire que retire `launcher.h` est à **`0x1090258C`/`0x109025A5`** (poignée globale `[0x109807a4]`) : ce n'est pas celle-ci. Celle qui s'exécute est la **seconde paire** que le commentaire de `launcher.h` écarte volontairement, à **`0x1091301D`/`0x10913036`** (même slot IAT `0x1099007C`), poignée lue par `mov edx,[ebp-14h] ; mov eax,[edx+4] ; push eax` : `6A FF 8B 55 EC 8B 42 04 50 FF 15 7C 00 99 10` puis `6A 03 6A 00 6A 00 6A 00 6A 00 6A FE 8B 4D EC 8B 51 04 52 FF 15 7C 00 99 10`.

| HP1 | A : archive (2.0.1) | B : release 2.1.0 |
|---|---|---|
| sha256 | `ce7f2576…` | `b56e0ab3…` |
| `surcharges` | `winmm` | `winmm` |
| chargée | `HP1\System\WINMM.dll : native` | idem |
| `winmm_accio.log` | `2.0.1 (winmm.dll)`, `Settings: … BlockAltEnter=0 FillScreen=1 SkipSetup=1`, **`Setup: skipped at 1090C8D4 (SkipSetup): no wizard, no renderer test`**, `Fill the screen: watched`, **`Pad 0: 054C:09CC "Wine joystick driver", 14 buttons, 6 axes, caps 0x3F -> PlayStation layout`** | idem avec `2.1.0` et `WineLauncherFix=0`, pas de `Launcher:` (attendu) |
| assistant « première configuration » | **ne s'ouvre pas** ; `HP.log` : `Bound to D3D11Drv.dll`, pas de `Detecting D3DDrv` ; `Running.ini` présent en partie, **effacé par le jeu à la sortie propre** | idem |
| fenêtre | 1904×1041 (viewport du HP.ini), image 4:3 centrée ; FillScreen sans effet (image plus petite que l'écran : documenté) | idem |
| Alt+Entrée ×2 (A) | **le jeu continue** ; fenêtre → 1920×1080, `winmm_accio.log` : `Window 1920x1080: frame taken off, now on the screen at 0,0 (FillScreen)` ; `HP.ini` : `WindowedViewportX/Y=1920/1080`, **`GameRenderDevice=D3D11Drv.D3D11RenderDevice` conservé** (relevé avant, après chaque Alt+Entrée, après la fenêtre devant, après la sortie : seuls `Reconfig` et `RunCount` changent) | non refait |
| fenêtre devant 8 s puis retour | le jeu continue | — |
| manette | vue par winmm (ligne `Pad 0`) et par le moteur (`Detected joysticks: 16`, `Joy1 … AltFire`) ; boutons non pressés (personne devant la manette) | — |
| partie | nouvelle partie, livre d'introduction, hall de Poudlard (`Lev_Tut1.unr`), **`Save0.usa` créé** ; Quitter partie → Oui → Quitter → Oui : code 0, 4362 s | menu, Quitter → Oui : code 0 |

**Phrase du bloc** : le lanceur de HP2 **n'est pas réparé sous Linux** par la 2.1.0 (la surcharge et la DLL marchent, le motif retiré n'est pas le bon). Fichiers d'origine (2.0.1) **remis** dans HP1/System et HP2/system à la fin du bloc.

## Bloc 2 — jeu par jeu

| | HP1 | HP2 | HP3 | HP4 | HP5 (manuel) |
|---|---|---|---|---|---|
| démarre | oui, 4 s (menu ~30 s) | oui, 6 s (lanceur noir) | oui, 4 s (menu ~30 s) | oui, 27 s (device D3D) | oui, 4 s |
| `surcharges` | `winmm` | `winmm` | `msvcr70, plafond 60 ips` | `d3d9,msvcr71` | manuel : `d3d9=n,b;xinput1_3=n,b` |
| DLL du correctif chargées | `winmm.dll` native | `winmm.dll` native | **`dinput8.dll` native SANS surcharge** (Wine ne la préfère pas interne, contrairement à d3d8/d3d9/winmm/xinput1_3) ; `d3d8.dll` de dgVoodoo **écarté** (builtin) | `d3d9.dll`, `MSVCR71.DLL` natives ; `syswow64/d3d9.dll` = DXVK | `d3d9.dll`, `xinput1_3.dll`, `hpexhdlr.dll` natives ; `MSVCR80/MSVCP80` **de Wine (winsxs builtin)** |
| journal du correctif | `winmm_accio.log` (ci-dessus) | idem | `dinput8_accio.log` : `5 of 6 functions` (`GetdfDIJoystick` absent chez Wine), `CreateDevice: watched`, `GetDeviceState: watched`, **`Pad: 054C:09CC "Wireless Controller", 14 buttons, 6 axes, 1 hats -> PlayStation layout`, dead zone 15 %** | `d3d9_accio.log` : `Game: Goblet of Fire`, `sound stream guard set`, `PlayStation controllers offered` ; F12 → `Screenshot saved: Z:\home\…\Images\Accio Launcher\Harry Potter et la Coupe de Feu\2026-10-20_12-04-42.png` | `d3d9_accio.log` : `DPI awareness: on`, **`Game: detail level 2 when the game has none saved set`**, `MSAA 16` ; **`xinput_accio.log` : `pad 09CC: opened, input 64 bytes, output 32 bytes`, `first reports: 1 pad(s) heard in 2 ms`, `slot 0: PlayStation pad 09CC given to the game`** |
| en jeu | nouvelle partie, hall, déplacement, Alt+Entrée ×2, fenêtre devant : OK | injouable (lanceur) | sauvegarde 1 chargée (train), déplacement OK ; Échap n'interrompt pas la cinématique | langue, invite sauvegarde auto « Oui » **1/1 sans plantage** (10/10 au 2e passage), personnage (touche Sort = X), camp des Weasley, déplacements, F12, fenêtre devant 8 s (`another program in front … back in front, the pointer shown while away is hidden again`), menu pause | langues → vidéo → titre → Nouvelle aventure → emplacement 1 → **Paramètres vidéo : « Niveau de détail : Haut »** (TextureDetail=2 d'une installation neuve : VU) ; « Appliquer » → `device Reset hr=0x0`, DLL survit |
| sortie | menu → Quitter → Oui : code 0 | Quitter : code 0 | pas d'entrée « Quitter » trouvée dans le menu Échap (parchemin) ; `pkill` pour la pause | menu principal → Quitter → Oui : code 0 (2 fois) | clavier perdu après le Reset (non élucidé) ; `pkill` |
| ce qui casse | — | lanceur noir (bloc 1) | plafond 60 sans effet (wined3d) | DirectInput sous Wine **rate une touche tapée** (xdotool `key`) : il faut la maintenir (0,15–1 s) ; ZQSD non représentatif (gamescope expose xkb `us`, l'hôte est `fr-nodeadkeys`) | — |
| verbes winetricks prouvés | d3dx11_43, d3dcompiler_43 (2e passage) | idem | aucun | aucun | **aucun : vcrun2005 PAS nécessaire** (Wine 10 fournit msvcr80/msvcp80) |

**HP6 (reprise, 16 h – 17 h)** : `vcrun2005` posé par le launcher (12 s), puis JOUER, partie neuve (cinématique, Quidditch au Terrier), puis reprises sur la sauvegarde automatique (`HPHBP0`).

- **Blocage : l'incrustation du correctif fait planter le GPU.** Dès que F10 (compteur) ou F11 (mesure) dessine l'incrustation (`Overlay: first drawn (2880 x 1620, own scene 1)`, dernière ligne du journal), le noyau écrit `i915 0000:00:02.0: [drm] GPU HANG: ecode 12:1:85dffdff, in hp6.exe` puis `context reset due to GPU hang` ; l'image reste figée, le fil principal attend pour toujours dans DXVK (CPU ~0), il faut tuer le jeu. **4 fois sur 4** (16:16:23, 16:30:23, 16:32:59, 16:36:21), avec la DLL de l'archive (`bf74b6bd…`) comme avec la 2.1.0 (`1f1f67c1…`), avec `Bloom=1` comme `Bloom=0`. Piles `winedbg` (attaché à chaud, `bt all`) : `~/Accio-essais/hp6-blocage-*-bt.txt` ; la première fois l'attente part d'`AnalyzeBright` (`effects.cpp`, `LockRect(…, D3DLOCK_READONLY)` après `GetRenderTargetData`, RVA `0x147c4` dans l'archive, `0x14ea4` dans la 2.1.0), sans `Bloom` elle part directement du jeu : c'est la conséquence (le GPU ne rend plus rien), pas la cause. Machine : Intel Alder Lake UHD (i3-1220P), Mesa 26.2.2 (ANV), GE-Proton10-34. L'état d'erreur du GPU (`/sys/class/drm/card1/error`) est lisible en root seulement : pas relevé.
- **Contre-épreuve** : le compteur de DXVK (`DXVK_HUD=fps,frametimes`, hérité du launcher relancé avec cette variable) s'affiche sans aucun blocage. Ce qui plante est donc le dessin de l'incrustation du correctif (`overlay.cpp`, `Draw` : `DrawPrimitiveUP` en `XYZRHW` sans tampon de profondeur, puis le texte avec la texture de police `D3DPOOL_MANAGED`), pas DXVK seul.
- **10 minutes de jeu** (16:40:42 → 16:50:43, touches maintenues en boucle, relevé du compteur DXVK toutes les 30 s) : 37,2 37,6 34,2 31,8 35,2 41,3 39,9 43,7 43,3 40,3 43,6 40,9 41,5 41,5 45,4 43,9 40,8 39,9 43,9 41,7. **Pas d'effondrement** (l'ancien gel tombait à ~3 images/s). Planche : `~/Accio-essais/planche-10min.png`.
- **Ombres, même scène** (arrivée de la sauvegarde au Terrier, Harry immobile, « Déplace Harry avec ZQSD », 6 relevés à 5 s) : `ShadowMapScale=1` → 43,8 43,5 41,1 43,8 40,9 40,4 (**moy. 42,3**) ; `ShadowMapScale=4` → 35,6 35,9 35,1 35,6 35,4 35,1 (**moy. 35,5**, −16 %). Le journal confirme `shadow targets drawn 4x larger` et écarte le tampon de flou 2048 (`is a blur buffer, not a shadow map`). **Aucune différence visible** sur cette scène (paire `~/Accio-essais/ombres-x1-x4.png`). Menu principal en ×1 : 44,2 à 44,8. Réglages remis (`ShadowMapScale=1`, `Bloom=1`, DLL de l'archive : ini identique à avant, sha vérifié).
- Le repère `(frame N)` du journal ne s'écrit que quand le nombre de mipmaps change (`direct3d.cpp`) : `fps_from_log.py` ne vaut que pour les premières minutes.

HP6 au 2e passage : voir plus bas. Cadence : un outil `~/Accio-essais/fps_from_log.py` déduit les images/s des paires `[ms] … (frame N)` du `d3d9_accio.log` (HP4 : 46 images/s de moyenne sur 327 s, 29-38 en jeu, Intel UHD, SSAA 1,5).

## Blocs 3 à 6 (état)

- **3.6 Audit de géométrie** : `tools/audit_geometrie.py` sur le Xwayland de gamescope (vraies polices, 3 langues × 8 jeux × 4 états × 4 tailles × 3 scénarios) : « Aucune troncature, aucun débordement, aucune barre de défilement », exit 0. `xvfb-run` n'est pas installé sur Bazzite : la mission et `build.sh` le supposent.
- **3.4 Galerie** : F12 dans HP4 écrit **directement** dans `~/Images/Accio Launcher/Harry Potter et la Coupe de Feu/` (`ScreenshotFolder=Z:\home\…` posé par le launcher dans `d3d9.ini`, accents intacts) ; rien dans `HP4/screenshots/`. L'affichage dans la galerie n'a pas encore été regardé.
- **3.1 Folio** (VU, depuis « Mes années » → « Ouvrir le folio ») : HP1 « Emplacement 1 · 20 octobre 2026 · Hall d'entrée de Poudlard » avec l'image du menu de chargement, « Partie tout juste commencée : pas encore de carte ni de points » ; HP2 et HP4 « Aucune sauvegarde trouvée pour ce jeu » (exact : HP4 « Dont 29 min jouées sans sauvegarder ») ; HP3 deux emplacements datés du 1er octobre, « partie tout juste commencée » ; HP6 la page complète (écussons 0/125, paliers 0/25, badges 1/30, Quidditch 1/10, écussons par lieu, « Chapitre 1 »). HP5, HP7a, HP7b : lignes « Pas encore lancé », pas de folio à ouvrir (HP5 n'a été lancé qu'à la main).
- **3.2 « Dernière partie »** : non vérifiable ici, et c'est le comportement voulu : la sauvegarde HP1 est au tutoriel (`Lev_Tut1`, Harry n'a encore rien écrit : `lire_harry_hp1` et `lire_bloc_hp1` rendent None), celles de HP3 n'ont ni niveau ni objet. La fiche garde donc la description (`folio.resume_hp1`, « tant qu'on a rien on laisse la description »).
- **3.3 Mes années** : tableau, statistiques, graphe des douze mois, « Élève de Serdaigle » : OK. Écart relevé : HP1 **1 h 27 min** ici, **1 h 15 min** sur sa fiche. Cause : deux sessions du 30 septembre (600 s et 120 s) dans `sessions.json` mais pas dans `playtime_seconds` ; ce jour-là le 1er passage avait remis `config.json` depuis une copie. Reste d'essai (supposé), pas un défaut du launcher. Restauration sur copie : pas encore.
- **Fiche, jeu ouvert au démarrage** : relancé à 16:38, le launcher s'ouvre sur **HP1** alors que HP6 est le dernier joué. `GameManager.last_played_game_id` compare des DATES (`last_played` au jour près) : à égalité, c'est l'ordre du dictionnaire qui gagne. Proposition : prendre le `debut` le plus récent de `sessions.json`. Non codé.
- **Outil de clic** : dans gamescope, la fenêtre est mise à l'échelle SANS déformation (bandes noires) ; mon `vclic2.sh` supposait un étirement, d'où des clics « sans effet » sur les liens et tuiles plus tôt dans ce passage. Corrigé à 17:10 : liens, boutons et lignes répondent. Pas un défaut du launcher.
- **5.4** zone de notification : le launcher s'y range à chaque lancement et revient à la fin (« Retour de … partie terminée », temps de jeu mis à jour) : vu sur HP1, HP2, HP3, HP4.
- **5.1/5.2/5.3/5.5/5.6/5.7** : à faire. 5.5 : la barre lumineuse n'a pas été observée (pas d'yeux sur la manette) ; `xinput_accio.log` de HP5 dit `LightBar=left alone` en lancement manuel (le launcher pose `LightBar=255,110,0` dans le `d3d9.ini` de HP6).
- **5.1** : bandeau « Visual C++ 2005 x86 manquant dans Wine — requis pour lancer ce jeu. Installer » sur HP6 → boîte « Préparer Wine » (une seule ligne : Visual C++ 2005) → barre du bas « Installation de Visual C++ 2005 » avec Annuler → « Wine est prêt. » en 12 s (installeur déjà dans le cache de winetricks), aucun processus restant. HP7a ne montre plus de bandeau ensuite ; HP7b demande Visual C++ 2008 : Annuler s'y testera.
- **6** : HP7a installé à la reprise (16:09 → 16:11:33, 31 Mo/s, 3 parties, « 134 élément(s) rangé(s) dans pc/ ») ; lancement à faire en dernier (accord écrit de Ludo dans la conversation).

## Pour la session Windows

1. **HP2, `WineLauncherFix` (correctif)** : neutraliser aussi la seconde paire `SetWindowPos` (`0x1091301D`/`0x10913036`, motif ci-dessus, même `add esp,1Ch` + nops), ou, plus robuste, dérouter le slot IAT `0x1099007C` vers un relais qui ignore un `SetWindowPos` sur une fenêtre `WS_CHILD` dont (x,y,cx,cy) centre à l'écran. Vérifier sous Windows ce que reçoit `[ebp-14h]+4` dans ce chemin (sans doute une fenêtre de premier niveau, d'où aucun dégât là-bas). Tant que ce n'est pas fait, HP2 est injouable par le launcher sous Linux.
2. **Archives** : HP1 1.3, HP2 1.2, HP3 1.3 portent le correctif 2.0.1 ; HP2 n'a pas `WineLauncherFix` dans son ini. À republier avec la 2.1.0 quand 1. est corrigé.
3. **README du correctif / `xinput.cpp`** : « none of this runs on Linux » est faux depuis le catalogue 0.35 : sous Wine la DLL native lit la DS4 par hidraw (`pad 09CC: opened … given to the game`). Corriger le texte.
4. **Catalogue distant** : rien à modifier d'après ce passage. (`dinput8` se charge natif sans surcharge sous GE-Proton10-34 ; l'ajouter en `n,b` serait sans danger mais non prouvé nécessaire.)
5. **`requires` `vcredist2005_x86` (hp5, hp6, hp7a) et `vcredist2008_x86` (hp7b)** : sous Linux le launcher **refuse JOUER** tant que winetricks n'a pas posé `vcrun2005`/`vcrun2008`, alors que HP5 (ce passage) et HP6 (2e passage) tournent avec les DLL de Wine. Proposition : hors Windows, répondre « présent » pour ces deux-là comme pour `vcredist2010_x86` (ou n'exiger le verbe que si le jeu échoue), ce qui épargne aux joueurs Linux un téléchargement Microsoft de plusieurs minutes. À décider par Ludo ; non codé.
6. **Incrustation du correctif sous Linux (HP4 à HP7, `overlay.cpp`)** : F10/F11 plantent le GPU Intel (Mesa ANV) et figent le jeu, 4 fois sur 4, archive comme 2.1.0 (détail au bloc 2). À chercher sous Windows avec le code : quel appel du dessin fait planter (essayer sans le texte, puis sans le panneau ; un `D3DRS_*` laissé à une valeur que DXVK traduit mal ; `BeginScene` propre « own scene 1 » juste avant `Present`). En attendant, sous Wine, ne pas dessiner l'incrustation (ou la désactiver par défaut et le dire dans l'ini), puisqu'un joueur qui presse F10 perd sa partie.
7. **`docs/LINUX.md` § 3** : « `n,b` et jamais `n` » n'est vrai que pour la famille wine : sous Proton, `d3d9=n` est ajouté APRÈS la chaîne du launcher et Wine garde le dernier réglage (sans dégât, DXVK est natif). § 4.5 et § 7 à rafraîchir (verbes prouvés, catalogue 0.43). Non modifié ici.

## Sauvegardes et remise en état

- Copie avant le premier jeu : `~/AccioSauvegardes/2026-10-20_1115/` (préfixe entier 723 Mo, `config.json`, `sessions.json`, plus `HP1-archive-1.3/`, `HP2-archive-1.2/`, `HP3-archive-1.3/` = DLL et ini du correctif tels que livrés).
- `diff -r` préfixe (Documents) copie ↔ actuel : seuls diffèrent `HP.ini`/`User.ini`/`HP.log`/`Game.ini`/`Game.log` (réécrits par les moteurs à chaque partie), `Running.ini` (effacé par la sortie propre de HP1) et `Harry Potter/Save/` (nouveau : `Save0.usa` + `GameSaveInfo0` de la partie HP1). HP3 `Save0/Save1.usa` inchangés ; AppData : aucune différence.
- Remis à l'identique : `winmm.dll`/`winmm.ini` 2.0.1 de HP1 et HP2 (sha vérifiés). Rien d'autre n'a été remplacé. Son : encore coupé (à remettre à 0.40). HP6 : copie `~/AccioSauvegardes/2026-10-20_1600-HP6/` (dossiers EA, vides avant la partie) et `~/AccioSauvegardes/2026-10-20_1115/HP6-archive-1.2/` (DLL et ini livrés) ; tout est remis, ini identique, sha `bf74b6bd…`.
- Dépôt : `git status` ne contient que ce fichier (et `CLAUDE.md` pour le compte de tests Linux). **Aucune modification de code ni de catalogue embarqué** à ce stade.

## Restes (dans l'ordre prévu à la reprise)

Bloc 5.1 (Annuler sur `vcrun2008` de HP7b, préparer pendant un téléchargement), bloc 3 (restauration sur copie, galerie, versions, tailles 980×660 / plein écran), 5.2/5.6/5.7 (double clic JOUER, désinstallation HP3, AppImage), HP7a (vérifier `rangé(s) dans pc/` et `Install Dir`/`Locale` dans `system.reg`) puis HP7a/HP7b en jeu avec surveillance CPU, relecture de `docs/LINUX.md`. Suppression des copies `~/Accio-essais/pfx-*` : en attente de l'accord de Ludo. 5.3 (fenêtre KWin) : avec Ludo.

---

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
