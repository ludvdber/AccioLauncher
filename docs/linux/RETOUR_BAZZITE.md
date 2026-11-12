# Septième passage (2026-11-11 et 2026-11-12)

Pour : Ludo et la session Windows. Demande : trouver la cause du gel du GPU Intel quand l'incrustation de HP6 se
dessine sous Wine, essayer le launcher 1.3.3 sous Linux, puis `./build.sh` et l'AppImage. Fait en deux fois : le
11 (cause du gel, corrections, build, 6 parties de preuve), puis le 12 au matin (les six jeux par JOUER, les 4
parties de preuve qui manquaient).

## En bref

| Bloc | État | Conclusion |
|---|---|---|
| 1. Gel du GPU | **fait** | Cause : le pilote Intel de Mesa (ANV) donne 132 registres pour 128 au vertex shader « ubershader » de DXVK quand notre texte se dessine. Remède : `d3d9.ffUbershaderVS = False`, posé par le launcher. 10 parties de 10 minutes sans gel. |
| 2. Launcher 1.3.3 | **fait, sauf Lumos** | Les écrans du launcher sont VUS, et HP1 à HP6 sont VUS en jeu par JOUER avec F12, F10, F11, Alt+Tab. Trois défauts corrigés. Restent Lumos dans HP2 et quelques nouveautés (Reprendre, export). |
| 3. Build et AppImage | **fait** | `./build.sh` : code 0 en 2 min 59, AppImage de 71 Mo, fenêtre en moins d'une seconde, HP1 joué par JOUER avec elle. |

## Machine

Bazzite 45 (Kinoite), noyau 7.3.3-ogc1.1.fc45, Mesa 26.2.6 (ANV, Intel Alder Lake GT2, i3-1220P), umu-launcher
1.4.4, GE-Proton10-34, **DXVK v2.7.1-509-g1676dcaf342a9b1** (VU par `DXVK_HUD=version`, capture
`~/Accio-essais/p7/hp6/essai0-a.png`), Python 3.15.0 (`/usr/bin/python3.15`, venv `.venv` refait). Dépôt :
9dcb2fc au début, ca241de à la fin (Ludo a commité mes corrections en route : ab21ec3 et 41f0c90). Catalogue 0.57.
Correctif : dépôt à 350b92e (VERSION 2.4.0). Versions installées, toutes celles que le catalogue recommande :
HP1 1.7, HP2 1.6, HP3 1.7, HP4 1.5, HP5 1.6, HP6 1.3, HP7a 1.3, HP7b 1.3. DLL du correctif en place (relevé par
SHA-256 et chaîne de version) : `winmm.dll` 2.4.0 (HP1, HP2), `dinput8.dll` 2.4.0 (HP3), `d3d9.dll` 2.4.0 (HP4,
HP5), `d3d9.dll` **2.2.0** (HP6, HP7, HP8).

## Tests

| | Réussis | Sautés | Échecs |
|---|---|---|---|
| Avant mes corrections (9dcb2fc) | 4557 | 44 | **1** : `test_le_bouton_jouer_garde_sa_hauteur_d_un_jeu_a_l_autre` (polices de Linux) |
| À la fin (ca241de + les trois retouches de texte de ce rapport) | **4581** | 44 | 0 |

ruff : « All checks passed! ». mypy et `mypy --platform linux` : « no issues found in 94 source files ».
`tools/verifier_wine.py` (sortie complète : `~/Accio-essais/p7/verifier_wine.txt`) : umu trouvé, GE-Proton10-34,
préfixe prêt (`win64`, page ANSI cp1252), winetricks présent, `d3dcompiler_43`, `d3dx11_43`, `vcrun2005`,
`vcrun2008`, `vcrun2022` présents, aucun composant manquant.

## Bloc 1 — le gel du GPU Intel quand l'incrustation de HP6 se dessine

### La cause, en une phrase

**Le pilote Intel de Mesa (ANV).** Le texte de l'incrustation passe par le vertex shader « ubershader » du
pipeline fixe de DXVK ; pour ce dessin-là, ANV donne au shader **132 registres pour une file de 128**, et le GPU
ne finit jamais le dessin. Notre dessin est du Direct3D 9 valide, DXVK n'émet rien de faux : c'est le pilote qui
compile un shader qui déborde. Niveau de preuve : **relevé** dans neuf fichiers d'erreur du GPU sur neuf, et
**vu** par les essais (le même dessin passe dès que l'ubershader n'est plus utilisé).

### Ce que dit le fichier d'erreur (`/sys/class/drm/card1/error`)

Neuf gels, neuf fichiers, copiés en root par un veilleur que Ludo a lancé (`~/Accio-essais/p7/gpu/`). Ils
disent tous la même chose (détail par fichier : `gpu/registres-9-gels.txt`) :

- `GPU HANG: ecode 12:1:85dffdff, in hp6.exe`, plateforme `ALDERLAKE_P`, moteur `rcs0`.
- **L'instruction sur laquelle le GPU attend** : `IPEHR 0x7a000204`, un `PIPE_CONTROL` de vidage (`Command
  Streamer Stall`, `Depth Stall`, `Render Target Cache Flush`) placé juste après le dernier `3DPRIMITIVE` du lot.
  Il attend que le dessin précédent soit fini, et il ne finit jamais.
- **Ce qui n'est pas fini** : `INSTDONE 0xffdffffb`, donc les bits « VS Done » et « CS Done » à zéro : l'étage
  des **sommets** (vertex shader) tourne encore. `ROW_INSTDONE` montre 8 à 10 unités d'exécution occupées,
  jamais les mêmes d'un gel à l'autre. Les échantillonneurs (`SAMPLER_INSTDONE 0xffffffff`) et l'étage des pixels
  ont fini. Aucune faute de page (`FAULT_REG 0`).
- **Le dessin fautif** : le dernier `3DPRIMITIVE` du lot, **252 sommets** en liste de triangles. C'est notre
  texte : 252 = 21 caractères × 2 passes (ombre puis face) × 6 sommets (le contenu exact des 21 caractères est supposé)
  chacun. Le dessin d'avant, 6 sommets, est notre panneau.
- **L'état qui fige** (lu dans `3DSTATE_VS`, `3DSTATE_CONSTANT_VS`, `3DSTATE_VERTEX_ELEMENTS` du lot) :

| Dessin | Éléments de sommet | Attributs (`Vertex URB Entry Read Length`) | Constantes poussées | Total | |
|---|---|---|---|---|---|
| dessins de 4 sommets, position + texture (supposé : les effets du correctif) | 15 | 8, soit 64 registres | 19+4+4+2 = 29 | 2 + 29 + 64 = **95** | passe |
| panneau (6 sommets, position + couleur) | 9 | 5, soit 40 registres | 19+33+4+2 = 58 | 2 + 58 + 40 = **100** | passe |
| **texte (252 sommets, position + couleur + texture)** | **17** | **9, soit 72 registres** | 19+33+4+2 = **58** | 2 + 58 + 72 = **132** | **gèle** |

  Une unité d'exécution de cette génération (Gen12) a 128 registres. 132 n'y tiennent pas.
- **Le shader** : noyau de 1 745 instructions à `Instruction Base + 0x58680` (premier fichier), gardé dans
  `gpu/e1-bin/13_user_000300000000.bin`. C'est le vertex shader à pipeline fixe de DXVK
  (`d3d9_fixed_function_vert.vert`, relu au commit `1676dcaf` : une seule vraie boucle, celle du mélange de sommets,
  retrouvée dans le noyau avec ses quatre lectures de matrice).

**Mesa connaît ce défaut** (relevé en ligne le 2026-11-11, copies dans `~/Accio-essais/p7/dxvk-src/`) :
ticket Mesa 15795 et correctif MR 42665, « anv/brw: limit push constant promotion in vertex shaders — The uber
shaders in DXVK are hitting the register limit from the amount of payload data », fusionné le 2026-07-07. **Ce
correctif est dans Mesa 26.2.6** (vérifié dans `anv_nir_compute_push_layout.c` à l'étiquette `mesa-26.2.6`), et
pourtant le portable gèle encore : son estimation (2 registres + 4 par entrée lue) laisse passer 58 registres de
constantes ici. **Supposé** : elle ne compte pas les éléments que le pilote ajoute pour le numéro de sommet et
les paramètres de dessin (`3DSTATE_VF_SGVS`, éléments 0x11 et 0x12), ce qui fait les 4 registres de trop. Les notes
de **DXVK 3.0.1** (2026-07-05) citent le même défaut et le contournent en activant les « descriptor buffers » sur
ces GPU. Le DXVK de GE-Proton10-34 est plus ancien (`v2.7.1-509-g1676dcaf`, 2026-03-22) : il a déjà l'ubershader,
pas encore le contournement.

**Pourquoi seulement au premier dessin, et pas nos effets** (supposé, d'après les notes de DXVK 3.0) : DXVK
compile en tâche de fond une variante optimisée par cas ; nos effets, dessinés à chaque image depuis le début,
ont la leur (29 registres de constantes). L'incrustation apparaît d'un coup : sa première image passe par
l'ubershader complet (58 registres), et le GPU ne rend jamais la main.

### Les essais, un par un

Machine : noyau 7.3.3-ogc1.1.fc45, Mesa 26.2.6 (ANV), umu-launcher 1.4.4, GE-Proton10-34, **DXVK
v2.7.1-509-g1676dcaf342a9b1** (vu par `DXVK_HUD=version`, capture `hp6/essai0-a.png`). HP6 1.3 du catalogue 0.57,
`d3d9.dll` **2.2.0** de l'archive (`1015e2ec…`). La release v2.3.0 du correctif n'est pas téléchargeable d'ici
(dépôt privé, pas de `gh`) ; `overlay.cpp` est identique entre v2.2.0, v2.3.0 et le dépôt (`git diff` vide), et les
six clés `[Accio.Overlay]` sont dans la 2.2.0. Lancement comme le launcher (umu, préfixe partagé, `d3d9` et
`xinput1_3` en `n,b`, `ACCIO_LAUNCH=1`), gamescope sans écran, son coupé. Ini de l'archive + les clés
indiquées, F10, 10 secondes, deux captures (identiques = figé), journal du noyau, puis `pkill`.

**Une erreur de ma part, corrigée en route** : dans les essais 1 à 11, ma deuxième « Entrée » ne passait pas et
HP6 est resté sur la **vidéo d'accueil de son menu principal**, pas au Terrier. Je m'en suis aperçu aux captures.
Le dessin de l'incrustation est le même partout, et le témoin refait en partie gèle pareil (essais T1 et T2) ;
les essais longs, eux, sont tous faits en vraie partie (navigation vérifiée par l'image, capture à l'appui).

| N° | Réglage | Résultat | Fichier d'erreur |
|---|---|---|---|
| 0 | `DXVK_HUD=version`, ini livré | DXVK v2.7.1-509-g1676dcaf ; pas de gel (rien de nous n'est dessiné) | — |
| 1 | témoin : `DrawUnderWine=1` | **gel** (15:43:09) | `gpu-error-…_154310.txt` |
| 2 | `Pipeline=1` | **gel** (15:45:48) : le shader de pixels n'y est pour rien | `…_154549.txt` |
| 3 | `DrawText=0` (panneau seul) | **pas de gel**, panneau affiché | — |
| 4 | `DrawPanel=0` (texte seul) | **gel** (15:51:01) : c'est le texte | `…_155102.txt` |
| 5 | `OwnScene=0` | **gel** (15:53:42) | `…_155344.txt` |
| 6 | `UnbindDepth=0` | **gel** (15:56:07) | `…_155608.txt` |
| 7 | `dxvk.conf` : `dxvk.enableDescriptorBuffer = True` | **pas de gel**, panneau et texte affichés | — |
| 7b (ajouté) | `dxvk.conf` : `d3d9.ffUbershaderVS = False` | **pas de gel**, panneau et texte affichés | — |
| 7c (ajouté) | `dxvk.conf` : `d3d9.ffUbershaderFS = False` | **gel** (16:10:31) : c'est bien le shader de sommets | `…_161033.txt` |
| 8 | `PROTON_USE_WINED3D=1` | **pas de gel**, panneau et texte affichés (pas de HUD DXVK à l'image : c'est bien wined3d) | — |
| 9 | `SSAAFactor=1` (image 1920×1080) | **gel** (16:05:43) : la taille n'y est pour rien | `…_160544.txt` |
| 10 | couche de validation Vulkan | **non fait** : la machine n'a que la couche 64 bits de Steam, HP6 est en 32 bits, et il aurait fallu installer. La cause a été trouvée autrement. | — |
| 11 (ajouté) | `DrawText=0` + `ShowGraph=1` (panneau et graphe, environ 1 500 sommets, sans texture) | **pas de gel** : le nombre de sommets n'y est pour rien | — |
| T1, T2 | témoin refait, T2 **vérifié en partie au Terrier** | **gel** (17:33:48, 17:37:00) | `…_173348.txt`, `…_173700.txt` |

Lecture : seuls les essais qui retirent le **texte** (3, 11) ou l'**ubershader de sommets** (7b), ou qui changent
la façon dont DXVK passe ses constantes au pilote (7), ou qui retirent DXVK (8), évitent le gel. Tout ce qui touche
à notre façon de dessiner (2, 5, 6, 9) n'y change rien.

### La preuve longue : 10 parties de 10 minutes

Remède essayé : `DXVK_CONFIG=d3d9.ffUbershaderVS=False` dans l'environnement (ce que pose le launcher),
`DrawUnderWine=1`, F10 en partie au Terrier, 600 s, comparaison de deux captures à la fin (écart non nul = l'image
bouge), journal du noyau.

| Essai | Début | Menu vu, partie chargée | Écart d'image à 600 s | `GPU HANG` |
|---|---|---|---|---|
| t3 | 17:38 | oui (capture : Harry au Terrier, panneau « 40 FPS ») | non nul | aucun |
| série A-1 | 17:50:36 | oui | 26,25 | aucun |
| série A-2 | 18:03:37 | oui | 27,41 | aucun |
| série A-3 | 18:16:32 | oui | 23,56 | aucun |
| série A-4 | 18:29:26 | oui | 32,33 | aucun |
| série A-5 | 18:42:19 | oui | 24,24 | aucun |
| HP6 par JOUER (launcher) | 12-11, 11:42 | oui (capture) | 31,90 | aucun |
| série B-1 | 12-11, 12:09:30 | oui | 27,44 | aucun |
| série B-2 | 12-11, 12:22:23 | oui | 25,04 | aucun |
| série B-3 | 12-11, 12:35:15 | oui | 29,69 | aucun |

`journalctl -k` : 0 ligne « GPU HANG » pendant ces dix parties. Sans le remède : 9 gels sur 9, chacun en moins
de 10 secondes après F10. **La preuve demandée est faite : 10 parties de 10 minutes sans gel** (9 avec la
variable posée à la main, 1 lancée par le launcher), en deux fois : 6 le 2026-11-11, 4 le 2026-11-12.

**Cadence en partie avec le remède** (F11 du correctif, 32 s au Terrier, panneau dessiné) : 42 images/s en
moyenne, 1 % bas à 15. La même mesure SANS le remède n'est pas faite (ma mesure du 11 tournait sur la vidéo du
menu, elle ne vaut rien) : je ne sais pas ce que le remède coûte ou rapporte. **Non fait** : la série avec
`dxvk.enableDescriptorBuffer = True` (un seul essai court, sans gel) ; l'essai 10.

### Ce que le launcher fait maintenant (commité par Ludo, 41f0c90)

- `compat.environnement()` ajoute `d3d9.ffUbershaderVS = False` à `DXVK_CONFIG` à chaque lancement sous Linux. Un
  réglage du joueur sur cette option ou sur `dxvk.enableDescriptorBuffer` est gardé.
- `incrustation_wine.suivre()` écrit `DrawUnderWine=1` dans le `d3d9.ini` quand le remède est dans l'environnement,
  `0` sinon. Un ini sans la clé n'est pas touché.
- **Niveau de preuve : VU en jeu par JOUER le 2026-11-12** pour HP4, HP5 et HP6 (voir le bloc 2) : ligne
  « Incrustation du correctif sous Wine » au journal, `DXVK_CONFIG` dans l'environnement du jeu, panneau F10
  dessiné, pas de gel ; HP6 a tenu 10 minutes ainsi.

## Bloc 2 — le launcher 1.3.3 sous Linux

**VU dans le gamescope sans écran** (captures dans `~/Accio-essais/p7/l/`) : page Nouveautés après la mise à jour ;
Bibliothèque avec la bande-annonce en fond ; Carnet (Folio de HP6, Défis 1/7, Relevé avec le **graphique des douze
mois**, étiquettes « 14 min » et « 3 h » lisibles) ; Collections (Captures, 7 images ; Musique de HP1 ; Cinématiques
de HP6 lues avec avance ; Personnages de HP1 en 3D ; Bestiaire de HP3 en 3D, « Modèles 3D sur la carte graphique :
Mesa Intel ») ; réglages de HP6 (Image et Ambiance, Performances, cadran de Difficulté) ; **boîte de
désinstallation** (« Vos sauvegardes sont conservées : elles ne sont pas rangées dans le dossier du jeu. », annulée)
; Paramètres ; visite guidée (étape 1 sur 7). **Relevé** au journal de Ludo : l'auto-mise à jour de l'AppImage
1.2.3 → 1.3.3 a marché (15:07:11 « AppImage remplacée », relance 1 s après).

**Corrigé** (dans `src/`, avec test) :

| Défaut | Correction | Test |
|---|---|---|
| Le bouton JOUER sautait de 15 px d'un jeu à l'autre (polices de Linux : une description plus courte que la référence faisait remonter le panneau) | `ui/game_detail.py` : écart signé (ab21ec3). VU : JOUER à y 455–498 sur les 8 fiches | `test_une_description_courte_ne_fait_pas_remonter_le_bouton`, contre-épreuve faite |
| Musique de HP5/HP6 sans `vgmstream-cli` : la page listait les morceaux et ne jouait rien, sans rien dire | `phonographe.manque_vgmstream`, message dans `mediatheque_page` (fr/en/es) (41f0c90). VU | `test_vgmstream.py`, `test_mediatheque.py` |
| Gel du GPU Intel | voir bloc 1 | `test_incrustation_wine.py`, `TestIncrustationDuCorrectif` |

**Observé, pas corrigé** :
- `version_lancee` n'est relevée que s'il n'y a pas de toast de mise à jour de jeu : la page Nouveautés peut se
  rouvrir à chaque démarrage tant qu'un jeu a une mise à jour en attente (supposé d'après le code, vu une fois).
- Sous Linux, le launcher ne télécharge pas vgmstream (il dit seulement de l'installer). Proposition : télécharger
  le binaire Linux officiel comme sous Windows, avec son empreinte. Je ne l'ai pas fait : c'est exécuter un binaire
  téléchargé, à décider par Ludo.
- Deux jeux ne tournent pas en même temps dans le préfixe (`waitforexitandrun`) : un HP1 lancé pendant qu'HP6
  tournait a attendu, puis a été annulé, et le launcher a compté environ 2 minutes de jeu (HP1 : 1 h 16 → 1 h 18).

### Les six jeux par JOUER (2026-11-12, avec l'AppImage du bloc 3)

Chaque jeu : JOUER dans le launcher, jusqu'au jeu, DLL lues dans `/proc/<pid>/maps`, F12, F10, F11 pendant 30 s,
Alt+Tab aller-retour. Relevés complets : `~/Accio-essais/p7/l/hp*-touches.txt`, captures à côté.

| Jeu | En jeu | DLL du correctif chargée, version au journal | F12 | F10 | F11 | Alt+Tab |
|---|---|---|---|---|---|---|
| HP1 1.7 | **VU** : menu, partie 1 chargée, Dumbledore dans le hall, sous-titres français | `HP1/System/winmm.dll`, **2.4.0** ; rendu wined3d | **VU** : rangée dans `Images/Accio Launcher/<titre>` | **VU** : panneau « 26 FPS, 38 ms, 1% low 20 » | **VU** : « avg 27 FPS, 1% low 20 », CSV | vivant, image revenue |
| HP2 1.6 | **VU** : lanceur avec fond et boutons, Nouvelle partie, emplacement 1, Dobby à Privet Drive | `HP2/system/winmm.dll`, **2.4.0**, « WineLauncherFix, under Wine » ; wined3d | **VU** | **VU** au journal (« first drawn 1904 x 1041 ») | « avg 29 FPS, 1% low 21 », CSV | vivant |
| HP3 1.7 | **VU** : menu sur **tout l'écran** 1920×1080 (nouveauté 1.3.3), nouvelle partie à l'emplacement 3, cinématique du train | `HP3/system/dinput8.dll`, **2.4.0**, et `msvcr70.dll` du jeu ; `d3d8` puis wined3d | **VU** | pas dessiné, voulu : « Overlay: not drawn under Wine » | « avg 56 FPS, 1% low 49 » : le plafond de 60 tient (journal du launcher : « plafond 60 ips ») | vivant |
| HP4 1.5 | **VU** : écran de langue, puis la Grande Salle en 3D | `HP4/d3d9.dll`, **2.4.0** ; DXVK (`syswow64/d3d9.dll`) | **VU** | **dessiné, pas de gel** : « first drawn (2880 x 1620 … text 1) » | « avg 34 FPS, 1% low 14 », CSV | vivant |
| HP5 1.6 | **VU** : vidéo d'ouverture (cour de Poudlard) ; pas allé jusqu'à une partie | `HP5/d3d9.dll` **2.4.0** et `xinput1_3.dll` du jeu ; DXVK | **VU** | **dessiné, pas de gel** : « first drawn (1920 x 1080 … text 1) » | « avg 60 FPS, 1% low 42 », CSV | vivant |
| HP6 1.3 | **VU** : menu, Continuer, Harry au Terrier | `HP6/d3d9.dll` **2.2.0** et `xinput1_3.dll` du jeu ; DXVK | **VU** | **VU à l'écran** : panneau « 42 FPS, 23,8 ms, 1% low 16 », pas de gel, **10 minutes tenues** | « avg 42 FPS, 1% low 15 », CSV | vivant |

- **Le remède posé par le launcher est VU.** Journal : « Incrustation du correctif sous Wine : DrawUnderWine=1 dans
  …/HP6/d3d9.ini » (pareil pour HP4 et HP5) ; environnement de `hp6.exe` lu dans `/proc` :
  `DXVK_CONFIG=d3d9.ffUbershaderVS = False`. `journalctl -k` : 0 « GPU HANG » pour les trois jeux.
- **HP5 s'est fermé seul une fois** : premier lancement, « Jeu terminé (code 5, 26 s observées) », sans touche de ma
  part, rien au journal du noyau, dernière ligne du correctif « Mipmaps: 155 chains made (frame 1200) ». Relancé
  aussitôt : il tourne. Cause non trouvée, non reproduit (un seul essai de plus).
- **HP4 s'ouvre sur un écran de choix de langue, « English » proposé**, alors que le launcher est en français.
  Je n'ai pas cherché si c'est l'état de la partie de Ludo ou le suivi de langue de la 1.3.3 : à regarder.
- **Alt+F4 ne ferme ni HP1 ni HP6 ici** (envoyé par `xdotool` dans le gamescope sans écran ; supposé : la touche
  n'arrive pas comme une vraie, à revoir au clavier). HP1 est quitté par son menu, les autres par `kill`.
- **Le lanceur de HP2 est étiré sur tout l'écran par gamescope** : les clics se donnent alors en coordonnées de
  sa fenêtre 480×556. C'est le gamescope d'essai, pas le launcher.

**Non fait** : Lumos à l'écran dans HP2, HP5 jusqu'à une partie, la fermeture de HP3 par le launcher, Reprendre
en un clic, l'export d'une sauvegarde. HP7a, HP7b et HP8 : jamais lancés.

## Bloc 3 — build et AppImage

`./build.sh` complet (`ACCIO_PY` sur le venv, journal `~/Accio-essais/p7/build-sh.log`) : **code 0 en 2 min 59**,
4581 tests, géométrie « Aucune troncature », 49 bibliothèques laissées à la machine, **AppImage de 71 Mo**
(74 373 624 octets, SHA-256 `700a02dac047d357685e…`). Lancée dans le gamescope : **fenêtre visible en 0,97 s**
(0,97 s puis 0,75 s), journal « 1.3.3 (AppImage) … Python 3.15.0 ». **HP1 par JOUER avec elle : VU** le
2026-11-12 (tout le bloc 2 ci-dessus est fait avec cette AppImage) ; le launcher se range au lancement et revient
à la fin (« Retour de … : partie terminée »).

## Pour la session Windows

### Correctif (rien de compilé ni touché ici)

1. **Rien d'urgent : la garde tient.** `DrawUnderWine=0` reste le bon défaut de l'ini livré. Le launcher
   (ce passage) pose le remède DXVK au lancement et écrit lui-même `DrawUnderWine=1` quand le remède est là ;
   un joueur qui lance l'exe sans le launcher garde la coupure.
2. **La vraie correction, dans `overlay.cpp`** (à compiler et voir sous Windows, puis à revoir ici) : ne plus
   passer par le pipeline fixe pour les SOMMETS. Aujourd'hui `Pipeline=1` ne remplace que le shader de pixels,
   et c'est le shader de sommets qui gèle (essai 2). Proposition, sous une valeur `Pipeline=2` :
   - une déclaration de sommets à nous (`D3DDECLUSAGE_POSITION` float4, `COLOR0`, `TEXCOORD0`) à la place de
     `SetFVF(D3DFVF_XYZRHW | …)` : avec `POSITIONT`, Direct3D 9 n'exécute aucun vertex shader, donc DXVK
     reprend son pipeline fixe ; il faut une position NON transformée ;
   - un `vs_3_0` de trois lignes, compilé avec la DLL comme les autres : `o.pos = float4((i.pos.x - 0.5) *
     2 / largeur - 1, 1 - (i.pos.y - 0.5) * 2 / hauteur, 0, 1); o.col = i.col; o.uv = i.uv;` (largeur et
     hauteur de la cible en constante `c0` ; le demi-pixel est celui de Direct3D 9) ;
   - les deux `ps_3_0` existants (`overlay_flat`, `overlay_text`) tels quels.
   Trois entrées de sommet au lieu de dix-sept : 2 + quelques registres, très loin des 128, quel que soit le
   DXVK ou le Mesa du joueur. Quand c'est vu ici sur 10 essais, `DrawUnderWine` peut passer à 1 par défaut avec
   `Pipeline=2` sous Wine, et le launcher n'a plus besoin d'écrire la clé.
3. **Les effets du correctif passent au même endroit** (`effects.cpp` : `SetVertexShader(nullptr)` +
   `D3DFVF_XYZRHW | D3DFVF_TEX1`, donc le même ubershader). Supposé : ce sont les dessins de 4 sommets relevés à 95 registres (29 de
   constantes) ; avec les 58 de la première image ils seraient à 2 + 58 + 64 = 124, sous la limite de 4
   registres seulement. Le même `vs_3_0` les mettrait à l'abri.
4. **`dxvk.conf` dans les archives** (HP4 à HP7b, à côté de l'exe) : une ligne, `d3d9.ffUbershaderVS = False`.
   Sans effet sous Windows (pas de DXVK), il protège un joueur Linux qui a un launcher d'avant ce passage ou
   qui lance l'exe à la main. Facultatif depuis que le launcher pose `DXVK_CONFIG`.
5. **Le commentaire de l'ini** (`make_ini.py`, clé `DrawUnderWine`) peut dire la cause : « the text of the panel
   goes through DXVK's fixed-function vertex shader, which Mesa's Intel driver compiles with more registers
   than the chip has ».
6. **HP3 (`dinput8.dll`, panneau en pipeline fixe Direct3D 8)** : il ne dessine pas sous Wine non plus. HP3
   tourne sur wined3d ici (pas de DXVK), où l'essai 8 ne gèle pas : à essayer avec `DrawUnderWine=1` à un
   prochain passage, pas fait dans celui-ci.

## Sauvegardes

Copie faite avant tout lancement : `~/AccioSauvegardes/2026-11-11_p7/` (préfixes, `config.json`, `sessions.json`,
`sauvegardes.json`, `catalog_cache.json`, copies de sauvegardes du launcher, `HP6-archive-1.3/` avec `d3d9.ini`,
`d3d9.dll`, `xinput1_3.dll` ; `HP1-save` ajouté à 18 h 35, avant toute partie de HP1).

- **HP6** : la sauvegarde est remise depuis la copie après chaque essai (`diff -r` identique, écrit dans chaque
  `hp6/*.txt`). `d3d9.ini` identique à celui de l'archive (`cmp`), aucun `dxvk.conf`.
- **Parties du 2026-11-12 (HP1 à HP6 par JOUER)** : seconde copie avant, `~/AccioSauvegardes/2026-11-12_p7/`
  (Documents de HP1, HP2, HP3, dossiers EA de HP4, HP5, HP6, `HP1/save`, les six ini du correctif). Remise par
  `~/Accio-essais/p7/remise.sh` : `diff -r` **identique** pour les sept dossiers, `cmp` identique pour les six ini
  (le launcher y avait écrit `DrawUnderWine=1` ; il le réécrira au prochain lancement). L'état d'après les
  parties (nouvelle partie de HP2 à l'emplacement 1, de HP3 à l'emplacement 3, `Running.ini`, CSV de F11) est
  gardé dans `cree-par-essai/`. Les six captures F12 restent dans `~/Images/Accio Launcher/`, pour la galerie.
- **Temps de jeu comptés par ces essais** (dans `sessions.json`, non retirés) : HP1 +434 s (et +76 s la veille),
  HP2 +169 s, HP3 +180 s, HP4 +151 s, HP5 +25 s et +126 s, HP6 +791 s.
- **Son** : il était à `0.00 [MUTED]` au début, laissé tel quel.
- Le veilleur root ne tourne plus (dernier signe de vie le 11 à 19 h 00) ; mes gamescopes et le launcher d'essai sont arrêtés. `~/Accio-essais/p7/` garde les
  fichiers d'erreur du GPU, les captures et les scripts (rien dans le dépôt).

---

# Sixième passage : archives du 2026-10-22 (2026-10-23, 19 h 38 – 19 h 58)

Pour : Ludo. Demande : vérifier vite en jeu les nouvelles archives (catalogue 0.45 : HP1 1.4, HP2 1.3, HP3 1.4,
HP5 1.4), HP5 en dernier (il se téléchargeait, installé par le launcher à 19 h 38).

**Comment** : le launcher de Ludo (AppImage) était ouvert, l'instance unique empêchait d'en lancer un second.
Les jeux ont donc été lancés **à la main comme le launcher les lance** (umu, GE-Proton10-34, préfixe partagé, mêmes
surcharges que le catalogue : `winmm` pour HP1/HP2, `msvcr70` pour HP3, `d3d9` et `xinput1_3` pour HP5), dans le
gamescope headless, son coupé. Avant chaque jeu, le dossier des captures a été posé par **le code du launcher**
(`captures.preparer`), et le réglage des vidéos de HP3 par `videos_lancement.passer` : ce sont les fonctions
qu'appellent le lancement et la case des réglages. Tous les correctifs se déclarent **2.1.1** dans leur journal.

| Jeu | En jeu | F12 (capture) | F10 (compteur) | F11 (mesure) | Nouveauté de l'archive |
|---|---|---|---|---|---|
| HP1 1.4 | **VU** : menu, partie chargée, arrivée à Poudlard | **VU** : rangée dans `Images/Accio Launcher/Harry Potter à l'École des Sorciers` (accents corrects) | **VU** : images/s, ms, 1 % bas | **VU** : « avg 47 FPS, 1% low 30 » à l'écran, CSV écrit | — |
| HP2 1.3 | **VU** : le lanceur s'affiche (fond, 3 boutons), Nouvelle partie → emplacement 1 → Privet Drive | **VU** | **VU** | **VU** : « avg 29 FPS » | **Le lanceur noir sous Wine est réglé par l'archive elle-même** (`WineLauncherFix=1`, les deux lignes attendues au journal). Lumos : branché (`DrawComplexSurface goes through the fix`), pas vu à l'écran (pas de passage caché cherché) |
| HP3 1.4 | **VU** : partie chargée, cinématique du train, sous-titres français | **VU** | non affiché, **voulu** : « Overlay: not drawn under Wine » | **VU** : « avg 60 FPS, 1% low 55 » (le plafond de 60 tient) | **Vidéos passées VU** : aucun logo, fond du menu à 8 s, boutons à 20 s ; remises ensuite (empreintes identiques). Texte français : sous-titres d'environ 19 px de haut en 1080p, **pas de capture d'avant pour comparer** |
| HP5 1.4 | **VU** : menu, nouvelle aventure, emplacement 1, cinématique de Dudley | **VU** | non affiché, voulu (`DrawUnderWine=0`) ; donc pas de risque de plantage du GPU Intel | non essayé | **Ombres plus nettes VU au journal** : `shadow textures 512 pixels a side (128 as shipped)`. Démarre sans Visual C++ 2005 |

**Le correctif de HP3 (`dinput8.dll`) se charge sans surcharge** : le catalogue ne surcharge que `msvcr70`, mais
`dinput8_accio.log` est écrit et le correctif se trouve en place. Rien à ajouter au catalogue.

**Un piège dans HP5, sans lien avec l'archive** : appuyer sur Échap pendant que le journal arrive (entre l'écran
titre et le menu) bloque le jeu. Le journal reste vide, sans texte, et rien ne répond, ni Entrée ni les flèches
(image identique pendant 2 min). Relancé sans toucher à rien, le menu s'affiche normalement. Je ne sais pas si la
version 1.3 faisait pareil.

**Remise en état** : les Documents de HP1, HP2 et HP3, `HP1/save` et les sauvegardes de HP5 sont remis depuis
`~/AccioSauvegardes/2026-10-23_HP1-3/` et `2026-10-23_HP5/` (`diff -r` identique ; l'état après les essais est
dans `cree-par-essai/`). `winmm.ini` ×2, `dinput8.ini` et `d3d9.ini` sont remis (`cmp` identique) : le launcher
y réécrira `ScreenshotFolder` au prochain lancement. Les dossiers `benchmarks` créés par F11 sont déplacés dans
la sauvegarde. Les captures restent dans `Images/Accio Launcher` (2 pour HP1, 1 pour HP2, 2 pour HP3, 1 pour HP5),
pour la galerie. Le son est resté coupé (0.00, comme Ludo l'avait laissé).

**Pas fait (Ludo voulait éteindre)** : les écrans du launcher 1.2.3 (boîte de désinstallation, graphique des
douze mois), Lumos à l'écran, HP4, HP6 et HP7 (archives inchangées).

---

# Cinquième passage : HP2 relais (2026-10-20, 17 h 50 – 17 h 56)

Pour : Ludo et la session Windows. Demande : essayer sous Wine la `winmm.dll` du relais (`transfert/HP2_relais/` de
l'atelier, SHA-256 commençant par `8AEB017689C5C324`) avec le `winmm.ini` de HP2, puis la release dès qu'elle sort.

**L'atelier n'a pas pu être récupéré** : `Atelier-acciolauncher` n'est pas cloné sur ce portable et GitHub demande
une identification (dépôt privé, aucun identifiant ici ; mes premiers essais ont pu ouvrir une fenêtre de mot de
passe `ksshaskpass` sur l'écran de Ludo). Aucune DLL en `8AEB0176…` sur la machine. J'ai donc surveillé les
releases, et **la v2.1.1 est sortie à 17 h 46** : essai fait avec elle. Sa `winmm.dll` n'est PAS celle du relais
(SHA-256 `6d8b4309aa25ead7…`, version « 2.1.1 », compilée par GitHub Actions depuis `a039c1f`) ; elle porte les
messages attendus. Empreintes de la release vérifiées (`sha256sum -c`) ; `winmm.ini` du zip HP2 : `7fa7bf0e…`,
`WineLauncherFix=1`.

**Mise en place** : `winmm.dll` et `winmm.ini` d'origine de `HP2/system` (2.0.1 des archives, `cdc62e04…` et
`39ff0467…`) copiés dans `~/AccioSauvegardes/2026-10-20_HP2-relais/`, remplacés par ceux de la 2.1.1. Lancement
par JOUER, son coupé, surcharge inchangée (journal : `surcharges winmm`).

| À vérifier | Résultat |
|---|---|
| Au chargement : « Launcher: the exe's SetWindowPos calls go through the fix » | **oui** : `Launcher: the exe's SetWindowPos calls go through the fix (WineLauncherFix, under Wine)` |
| À l'ouverture du lanceur : « SetWindowPos 717,257 486x566 centring a child window on the screen ignored » | **oui**, mot pour mot, suivi de `(WineLauncherFix)` |
| L'ancienne ligne « two SetWindowPos taken out » | **absente** |
| Le lanceur avec son fond et ses trois boutons | **VU** : logo, fond nuit, « Nouvelle partie », « Charger partie », « Options », plus « Quitter » et le texte d'aide (fenêtre « Menu principal » 480×556) |
| « Nouvelle partie » et « Charger partie » réagissent au clic | **VU** : « Charger partie » ouvre les six emplacements (tous « Vide ») ; « <Retour » revient ; « Nouvelle partie » ouvre les six emplacements de création |
| Une partie se lance jusqu'au jeu | **VU** : emplacement 1 → `Game.exe PrivetDr.unr -SAVESLOT=1`, introduction de Privet Drive (« Harry Potter vivait au 4, Privet Drive… »), environ 32 images/s. Le launcher suit la relance de `Game.exe` et compte la partie (+95 s) |

Le contournement `Game.exe -LOADGAME=0 -SAVESLOT=1` n'a pas servi. Journal complet du correctif :
`~/Accio-essais/hp2-relais-2.1.1-winmm_accio.log`.

**Remise en état** : `winmm.dll` et `winmm.ini` 2.0.1 remis (`cmp` identique) ; Documents de HP2 remis depuis la
copie (`diff -r` identique ; l'état après la partie, avec `Save/Slot1/cache` et `Running.ini`, est gardé dans
`cree-par-essai/`).

**Conclusion** : avec la 2.1.1, **HP2 se joue par le launcher sous Linux**. Il reste à republier l'archive de HP2
avec ce correctif (elle porte toujours la 2.0.1, dont le lanceur est noir sous Wine). La DLL du relais
(`8AEB0176…`) n'a pas été essayée ; si elle diffère de la release, c'est la release qui est validée ici.

---

# Quatrième passage (2026-10-20) — terminé à 18 h 05

Portable Bazzite, launcher **depuis les sources** (commit `4f758f9`, catalogue 0.43), jeux lancés par JOUER sauf mention « manuel ». Les essais à l'écran se font dans un **gamescope headless** (`--backend headless`, Xwayland `:1`, captures `gamescopectl screenshot`, entrées `xdotool`) : le verrouillage d'écran de KDE a coupé les deux passages précédents et Ludo n'était pas là pour le désactiver. Captures, journaux et notes par jeu : `~/Accio-essais/` (`notes-HP1.md` … `notes-HP6.md`, `notes-bloc3.md`).

## En bref

| Bloc | État | Conclusion |
|---|---|---|
| 0. Mise en place | fait | venv recréé, contrôles verts (ci-dessous), préfixe et config copiés avant tout jeu. Tous les jeux **mis à jour ou installés** par le launcher (HP1 1.3, HP2 1.2, HP3 1.3, HP4 1.2, HP5 1.3, HP6 1.2, HP7b 1.2 ; **HP7a 1.1 installé seulement à la reprise**, 16:11 : il manquait). |
| 1. `winmm` HP1/HP2 (0.43) | **fait** | **La surcharge prend** : `surcharges winmm` au journal, `HP2\system\WINMM.dll : native`, `winmm_accio.log` écrit, pour HP1 comme HP2, avec la DLL de l'archive (2.0.1) comme avec la 2.1.0. **Mais le lanceur de HP2 reste noir avec la 2.1.0** : la paire retirée par `WineLauncherFix` n'est pas celle qui s'exécute (détail et proposition plus bas). HP1 : assistant sauté, Alt+Entrée ×2 et fenêtre devant sans dégât, `GameRenderDevice` conservé. |
| 2. Six jeux avec la 1.2.2 | en partie | HP1, HP2, HP3, HP4, HP5 lancés (tableaux plus bas). **HP5 démarre sans `vcrun2005`**. **HP6 fait : 10 min sans effondrement (31,8 à 45,4 images/s), ombres ×4 = −16 % (35,5 contre 42,3) sur la même scène.** Mais **l'incrustation du correctif (F10/F11) fait planter le GPU Intel** et fige le jeu pour toujours (détail plus bas). |
| 3. Folio, Mes années, galerie, versions | **fait** | Audit de géométrie OK (session réelle, puis dans `build.sh`). Folio : s'ouvre pour les 8 jeux. **Restauration sur copie VU** (HP6, version de 16:15 remise, le jeu la charge, original remis, `diff -r` identique). **Galerie VU** (capture F12 de HP4, 2880×1620). **Versions VU** (HP1 1.3 → 1.2 → 1.3, dossier identique fichier par fichier, sauvegardes et réglages intacts). Tailles 980×660 et 1920×1080 : rien de coupé dans les folios. Trois petits défauts d'affichage (plus bas). |
| 4. HP3 à 60 images/s | fait (constat) | Inchangé : HP3 tourne sur le `d3d8` de wined3d (maps), `DXVK_FRAME_RATE=60` sans effet, dgVoodoo écarté. Rien de nouveau prouvé. |
| 5. Launcher sous Linux | fait, sauf 5.3/5.5 | Zone de notification : vu à chaque partie. `vcrun2005` 12 s, `vcrun2008` 10 s. **Annuler et les refus croisés : pas testables à la main** (préparation et installations plus rapides que les clics). **Double clic JOUER : un seul lancement (VU).** **Désinstaller/réinstaller HP3 : sauvegardes et `_Launcher/` intacts (VU).** **AppImage : `build.sh` vert en 3 min 00, 64 Mo, fenêtre en moins d'une seconde, HP1 joué avec elle (VU).** 5.3 (KWin) et 5.5 (barre lumineuse) : il faut Ludo. |
| 6. HP7a/HP7b | **fait, défaut trouvé et corrigé** | **Sous umu, HP7a et HP7b quittaient en 3 s (code 0)** : le launcher écrivait `Install Dir=Z:\home\…` alors que Proton lance l'exe en `X:\Games\…` (`x:` = dossier personnel). **Corrigé dans `compat.chemin_windows`** (test ajouté). Ensuite : HP7a en jeu, 59,9 images/s, 35 à 87 % d'UN cœur ; HP7b en jeu, 27,9 à 29,9 images/s, 0,5 à 2 cœurs. **Aucun gel, jamais tous les cœurs.** |

## Machine

Bazzite, noyau `7.2.7-ogc1.1.fc44.x86_64`, KDE Wayland (essais dans gamescope headless 1920×1080), umu-launcher 1.4.4, **GE-Proton10-34** (`~/.local/share/Steam/compatibilitytools.d`), Python 3.14.7 (venv du dépôt), dépôt AccioLauncher `4f758f9` (2026-10-20), dépôt Harry-Potter-PC-Fix `259ec54` (v2.1.0). Manette **DualShock 4 USB** (`054c:09cc`, `/dev/hidraw1` accessible, `js0`) branchée par Ludo à 11:20. Son coupé à 11:45 (`wpctl` : 0.40 [MUTED], à remettre : `wpctl set-mute @DEFAULT_AUDIO_SINK@ 0`).

## Tests et contrôles

- **Après la correction de `compat.chemin_windows` (18 h)** : `pytest -q` **3325 réussis, 38 sautés, 0 échec** (2 tests neufs) ; `ruff check .` propre ; `mypy` propre (68 fichiers). `./build.sh` complet vert juste avant (3323 tests, audit de géométrie OK).

Avant toute modification :

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
- **5.5** : la barre lumineuse n'a pas été observée (pas d'yeux sur la manette) ; `xinput_accio.log` de HP5 dit `LightBar=left alone` en lancement manuel (le launcher pose `LightBar=255,110,0` dans le `d3d9.ini` de HP6). Le launcher, lui, journalise « Manette : barre lumineuse aux couleurs de « serdaigle » ».
- **5.1** : bandeau « Visual C++ 2005 x86 manquant dans Wine — requis pour lancer ce jeu. Installer » sur HP6 → boîte « Préparer Wine » (une seule ligne : Visual C++ 2005) → barre du bas « Installation de Visual C++ 2005 » avec Annuler → « Wine est prêt. » en 12 s (installeur déjà dans le cache de winetricks), aucun processus restant. HP7a ne montre plus de bandeau ensuite ; HP7b demande Visual C++ 2008 : Annuler s'y testera.
- **6** : HP7a installé à la reprise (16:09 → 16:11:33, 31 Mo/s, 3 parties, « 134 élément(s) rangé(s) dans pc/ ») ; lancement à faire en dernier (accord écrit de Ludo dans la conversation).

**Reprise de 17 h 15 à 18 h 05**

- **3.1 Restaurer une sauvegarde (VU)** : HP6, réglages du jeu → « Restaurer une sauvegarde » → « Versions des sauvegardes » (16:43 la plus récente, 16:15) → « Remettre cette version » → confirmation qui dit que l'état actuel est copié d'abord → « Sauvegarde remise ». Le fichier `HPHBP0` est alors celui de la copie de 16:15 (empreinte identique), le jeu propose « Continuer » et reprend au Terrier. Original remis depuis `~/AccioSauvegardes/2026-10-20_restauration-HP6/` : `diff -r` identique, copies du launcher identiques. **Petit écart** : le fichier remis a les droits `rw-------` au lieu de `rw-r--r--` (fichier temporaire renommé) ; sans effet pour Wine, à aligner si l'on veut un retour à l'octet près.
- **3.4 Galerie (VU)** : la capture F12 de HP4 s'affiche (« 20 octobre 2026, 12:04 · 2880 × 1620 », boutons Discord, ouvrir, copier, dossier).
- **3.5 Versions (VU)** : HP1 « Gérer les versions » liste 1.3 (installée), 1.2, 1.1, 1.0 ; « Revenir à v1.2 » → « Ceci va supprimer la version actuelle » → 1.2 installée en 6 s ; retour par « Mise à jour disponible : v1.2 → v1.3 ». Après l'aller-retour, le dossier HP1 est **identique fichier par fichier** (365 fichiers, hors journaux), Documents et `config.json` aussi. Le journal dit « Config du joueur gardée » pour `HP.ini` et `User.ini`.
- **3.6 Tailles** : 980×660 puis 1920×1080 (forcée par `xdotool` : le gamescope sans écran n'agrandit pas) sur les folios HP1, HP3, HP6 et sur Mes années : rien de coupé à droite, les noms longs de HP6 passent sur deux lignes, comptes alignés. **Trois petits défauts d'affichage**, non corrigés : (1) dans le graphe des douze mois, l'étiquette de septembre s'affiche « 14… » à TOUTES les tailles (`stats_widgets` coupe la valeur à la largeur d'une barre, ≈ 20 px ; proposition : laisser déborder sur les colonnes voisines vides, ou écrire « 14′ ») ; (2) « Sang-Mêlé » perd son circonflexe dans les titres en Cinzel des petites capitales (titre du dialogue des versions, colonne des réglages, folio, Mes années), l'aigu de « Melé » reste : à regarder sous Windows avec la vraie police ; (3) la boîte de désinstallation ne dit pas que les sauvegardes restent (un toast le dit ensuite, en s'effaçant).
- **5.1 Annuler et refus croisés** : pas prouvés. `vcrun2008` s'est posé en 10 s ; et deux fois, l'installation en cours (HP1 1.2 puis 1.3, 6 s chacune) s'est terminée avant que le clic « préparer » n'arrive : le journal montre `Installation terminée` 2 s AVANT `Préparation de Wine`. Il faudrait un composant lent ou un réseau bridé.
- **5.2 Double clic JOUER (VU)** : deux clics à 120 ms sur « Reprendre » de HP1 → une seule ligne `Lancement de`, un seul `HP.exe`.
- **5.6 Désinstaller puis réinstaller HP3 (VU)** : 774 Mo retirés, parties de HP3 (Documents du préfixe) et copies du launcher intactes ; réinstallé en 15 s (336 Mo à 43 Mo/s). `_Launcher/` hors préfixe et journaux : seuls `config.json` (même contenu, ordre des clés) et `sessions.json` (compteur d'octets, deux sessions d'essai) bougent.
- **5.7 AppImage (VU)** : `./build.sh` complet en 3 min 00 (lint, 3323 tests, audit de géométrie, PyInstaller, 48 bibliothèques laissées à la machine), `dist/AccioLauncher-x86_64.AppImage` de **64 Mo** (66 812 408 octets, sha `99da5646…`). Lancée en X11 sur l'affichage d'essai : fenêtre en **moins d'une seconde**, journal `Accio Launcher 1.2.2 (AppImage)`, HP1 lancé avec `surcharges winmm`, launcher revenu à la fin (+23 s comptées). **Piège d'essai** : lancée sans `WAYLAND_DISPLAY`, l'AppImage s'est ouverte sur le VRAI bureau de Ludo (Qt prend `wayland-0` par défaut) ; fermée aussitôt. Et j'avais d'abord passé `QT_QPA_PLATFORM=xcb` à `build.sh` : `conftest.py` ne fait qu'un `setdefault`, la suite ouvrait ses fenêtres ; arrêtée et relancée sans.
- **6. HP7a/HP7b** : premier JOUER sur HP7a → prévenance correcte (« registre de Wine », `Install Dir`, `Locale = fr_FR`, pas d'administrateur), registre écrit sous `Wow6432Node`, puis **sortie code 0 en 3 s**, sans fenêtre de jeu ; le launcher le range en « lancement sans partie ». Même chose sans le `d3d9.dll` du correctif. Trace `+loaddll,+process` : `hp7.exe` charge tout (correctif, DXVK, `d3dx9_37`, `MSVCR80`, `winex11`) puis `NtTerminateProcess(0)`, aucune exception : le chemin « insérez le disque » de `CATALOGUE_ET_JEUX.md`. Cause : `dosdevices` a `x: → ~` (dossier personnel) (créé par Proton), l'exe tourne donc en `X:\Games\AccioLauncher\HP7\pc\`, alors que `Install Dir` dit `Z:\home\<nom>\…`. Preuve : lancé par `Z:\…\pc\hp7.exe`, le jeu ne quitte plus. **Correction** (`src/core/compat.py`, `_lecteur_le_plus_proche`) : `chemin_windows` prend le lecteur que Wine donne au chemin (racine la plus profonde de `dosdevices`), `Z:` sinon. Test `test_le_lecteur_que_wine_donne_au_dossier_personnel` (échoue sans la correction). Au JOUER suivant, la prévenance montre « `X:\Games\AccioLauncher\HP7\` remplace `Z:\home\…` », et **HP7a démarre** : écran des sauvegardes automatiques, titre, menu en français, nouvelle partie « Facile », cinématique puis première scène jouable (« Appuie sur Bouton souris gauche »), **59,9 images/s**, 35 à 47 % d'un cœur au menu, 82 à 95 % en jeu. **HP7b** : prévenance `X:\…\HP8\` + `Locale = fr`, titre, menu « Mode Histoire », chargement puis scène du tombeau, **27,9 à 29,9 images/s** (bridé à 30, normal), 2 cœurs au chargement, 0,5 en jeu. Chien de garde (`~/Accio-essais/garde-hp7.sh`, tue au-delà de 900 % pendant 30 s) jamais déclenché. Journaux : `garde-hp7.exe.log`, `garde-hp8.exe.log`, `hp7a-trace.log`. Sauvegardes neuves créées par ces parties (`auto.sav` des deux jeux) déplacées dans `~/AccioSauvegardes/2026-10-20_HP7/cree-par-essai/` : le dossier EA est identique à avant (`diff -r`). Les clés de registre restent (le launcher les réécrirait).
- **Écran blanc par le chemin `Z:`** (curiosité, pas un défaut du launcher) : lancé à la main par `Z:\…\hp7.exe`, HP7a restait sur une fenêtre blanche sans aucune image pendant 4 min, alors que par le launcher corrigé il affiche tout de suite. Proton dit dans ce cas « Executable is inside wine prefix, launching normally » au lieu de « /unix » : lancement différent, non creusé.

## Pour la session Windows

1. **HP2, `WineLauncherFix` (correctif)** : **réglé par la 2.1.1** (cinquième passage, en tête de ce fichier) : lanceur avec fond et boutons, partie lancée. Ancienne analyse (2.1.0, paire `0x1091301D`/`0x10913036`) gardée dans le bloc 1 pour mémoire.
2. **Archives** : HP1 1.3, HP2 1.2, HP3 1.3 portent le correctif 2.0.1 ; HP2 n'a pas `WineLauncherFix` dans son ini. **À republier avec la 2.1.1** : tant que l'archive de HP2 porte la 2.0.1, son lanceur reste noir sous Linux.
3. **README du correctif / `xinput.cpp`** : « none of this runs on Linux » est faux depuis le catalogue 0.35 : sous Wine la DLL native lit la DS4 par hidraw (`pad 09CC: opened … given to the game`). Corriger le texte.
4. **Catalogue distant** : rien à modifier d'après ce passage. (`dinput8` se charge natif sans surcharge sous GE-Proton10-34 ; l'ajouter en `n,b` serait sans danger mais non prouvé nécessaire.)
5. **`requires` `vcredist2005_x86` (hp5, hp6, hp7a) et `vcredist2008_x86` (hp7b)** : sous Linux le launcher **refuse JOUER** tant que winetricks n'a pas posé `vcrun2005`/`vcrun2008`, alors que HP5 (ce passage) et HP6 (2e passage) tournent avec les DLL de Wine. Proposition : hors Windows, répondre « présent » pour ces deux-là comme pour `vcredist2010_x86` (ou n'exiger le verbe que si le jeu échoue), ce qui épargne aux joueurs Linux un téléchargement Microsoft de plusieurs minutes. À décider par Ludo ; non codé.
6. **Incrustation du correctif sous Linux (HP4 à HP7, `overlay.cpp`)** : F10/F11 plantent le GPU Intel (Mesa ANV) et figent le jeu, 4 fois sur 4, archive comme 2.1.0 (détail au bloc 2). À chercher sous Windows avec le code : quel appel du dessin fait planter (essayer sans le texte, puis sans le panneau ; un `D3DRS_*` laissé à une valeur que DXVK traduit mal ; `BeginScene` propre « own scene 1 » juste avant `Present`). En attendant, sous Wine, ne pas dessiner l'incrustation (ou la désactiver par défaut et le dire dans l'ini), puisqu'un joueur qui presse F10 perd sa partie.
7. **`docs/LINUX.md`** : corrigé dans ce passage (§ 3 HP3 et `n,b`, § 4.3 lecteur, § 4.5 winetricks, § 7 catalogue, § 9 `build.sh` sur Bazzite et tableau « Vérifié sur Bazzite »).
8. **`compat.chemin_windows` (launcher, NOUVEAU)** : la correction du lecteur (bloc 6) ne touche que Linux (`chemin_windows` n'est appelé que sous Wine) ; à relire. Effet de bord voulu : `ScreenshotFolder` et les `%INSTALL_DIR%` des INI passent aussi en `X:\…` quand le jeu est sous le dossier personnel (même dossier pour Wine). Un jeu installé sur un disque externe prendrait le lecteur `v:` (`/run/media`), comme Wine.
9. **HP5 par JOUER** : `vcrun2005` est maintenant posé, HP5 n'a été lancé qu'à la main dans ce passage. À refaire par le launcher au prochain essai.

## Sauvegardes et remise en état

- Copie avant le premier jeu : `~/AccioSauvegardes/2026-10-20_1115/` (préfixe entier 723 Mo, `config.json`, `sessions.json`, plus `HP1-archive-1.3/`, `HP2-archive-1.2/`, `HP3-archive-1.3/` = DLL et ini du correctif tels que livrés).
- `diff -r` préfixe (Documents) copie ↔ actuel : seuls diffèrent `HP.ini`/`User.ini`/`HP.log`/`Game.ini`/`Game.log` (réécrits par les moteurs à chaque partie), `Running.ini` (effacé par la sortie propre de HP1) et `Harry Potter/Save/` (nouveau : `Save0.usa` + `GameSaveInfo0` de la partie HP1). HP3 `Save0/Save1.usa` inchangés ; AppData : aucune différence.
- Remis à l'identique : `winmm.dll`/`winmm.ini` 2.0.1 de HP1 et HP2 (sha vérifiés). Rien d'autre n'a été remplacé. Son : encore coupé (à remettre à 0.40). HP6 : copie `~/AccioSauvegardes/2026-10-20_1600-HP6/` (dossiers EA, vides avant la partie) et `~/AccioSauvegardes/2026-10-20_1115/HP6-archive-1.2/` (DLL et ini livrés) ; tout est remis, ini identique, sha `bf74b6bd…`.
- Copies de la reprise : `~/AccioSauvegardes/2026-10-20_restauration-HP6/`, `…_versions-HP1/` (Documents, `config`, `save`, `System/*.ini`, `config.json`, manifestes avant/après), `…_desinstall-HP3/`, `…_HP7/` (`system.reg`, `user.reg`, dossier EA avant, `cree-par-essai/` = les deux `auto.sav` de HP7), `…_HP2-relais/` (`winmm.dll`/`winmm.ini` 2.0.1 d'origine, Documents de HP2, et `cree-par-essai/` = l'état après la partie). Tout est remis et prouvé par `diff -r` ou `cmp`.
- Dépôt : `src/core/compat.py`, `tests/test_compat.py`, `docs/LINUX.md`, `docs/claude/ARCHITECTURE_CORE.md`, `docs/claude/CATALOGUE_ET_JEUX.md` et ce fichier.

## Restes (dans l'ordre prévu à la reprise)

- 5.3 (fenêtre du launcher sous KWin) et 5.5 (barre lumineuse) : avec Ludo devant l'écran et la manette.
- 5.1 « Annuler » et les refus croisés : il faut une opération plus lente que le clic.
- HP5 par JOUER (maintenant que `vcrun2005` est posé).
- Suppression des copies `~/Accio-essais/pfx-*` (≈ 700 Mo chacune) : en attente de l'accord de Ludo.

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
