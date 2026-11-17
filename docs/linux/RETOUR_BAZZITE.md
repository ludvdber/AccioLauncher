Passages 1 à 6 (2026-09-30 au 2026-10-23) : [`RETOUR_BAZZITE_PASSAGES_1_A_6.md`](RETOUR_BAZZITE_PASSAGES_1_A_6.md).
Un nouveau passage s'écrit ici, en haut.

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
