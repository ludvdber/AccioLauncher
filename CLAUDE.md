# CLAUDE.md

Guide de travail pour Claude Code sur ce dépôt. **Toute règle ici a été payée une fois** : elle porte sa mesure, pas son récit.

## Project Overview

Launcher PyQt6 pour 8 jeux Harry Potter PC (Windows 10/11). **Interface et commentaires en français.** Python 3.12+ (`build.bat` préfère 3.14, replie sur 3.13 puis 3.12).

**Ne pas passer à Python 3.15** : PyInstaller met des mois à suivre une version majeure, et le gain serait nul ici.

**Linux est un objectif déclaré** : tout appel win32 derrière `sys.platform == "win32"` avec un repli sensé (patron : `self_update.can_self_update`, `win_utils`, `system_checks`, `game_registry.disponible`). Jamais de lettre de lecteur hors code gardé.

**Le registre sous Linux** : il n'y en a pas, mais le jeu tournera sous **Wine, qui a le sien**. Le travail n'est pas à supprimer, il est à rebrancher sur `wine regedit`. Tout passe par `game_registry.disponible()` — un seul point à changer, plus `_ecrire_eleve`.

**Portage Linux : `docs/LINUX.md` fait foi** (audit `fichier:ligne`, contenu RELEVÉ des archives, décisions : umu puis wine, préfixe partagé, chemins du préfixe, surcharges de DLL, AppImage).

## Commands

```bash
pip install -r requirements.txt && python main.py     # lancer depuis les sources
python -m pytest                                      # toute la suite
python -m pytest tests/test_config.py::TestConfig::test_defaults
python -m ruff check .                                # jeu de règles FIGÉ dans pyproject.toml
pip install -r requirements-dev.txt && build.bat      # → dist/AccioLauncher.exe
./build.sh                                            # Linux → dist/AccioLauncher-x86_64.AppImage
```

`build.bat` enchaîne icône → lint → tests → géométrie (vraies polices) → PyInstaller, et **s'ARRÊTE au premier échec** : un exe publié avec une régression coûte plus cher que 20 s d'attente. `build.sh` fait de même sous Linux, plus l'AppImage (6 étapes) ; hors d'un venv il crée `.venv-build` (le Python d'un système atomique ne s'installe pas), et sans session graphique l'audit passe par `xvfb-run` — il PASSE sous Linux avec les vraies polices (xcb, 78 s).

## Où lire le détail (À LIRE AVANT DE TOUCHER AU SUJET)

Le détail vit dans `docs/claude/`, mot pour mot ce que contenait ce fichier :

| Avant de toucher à… | Lire |
|---|---|
| un module de `src/` (rôle, pièges, mesures) | [docs/claude/ARCHITECTURE.md](docs/claude/ARCHITECTURE.md) — chercher le nom du module |
| journal, sortie `os._exit`, CI, release, AppImage | ARCHITECTURE.md § « Journal, sortie et CI » |
| `games.json` (champs, blocs, validation), HP7 `pc`, HP1-HP3 (UE1), logo/icône | [docs/claude/CATALOGUE_ET_JEUX.md](docs/claude/CATALOGUE_ET_JEUX.md) |
| n'importe quoi listé dans l'index ci-dessous | [docs/claude/REGLES.md](docs/claude/REGLES.md), même numéro |
| Linux / Wine | [docs/LINUX.md](docs/LINUX.md) |

Modules documentés (et `catalogue_blocs.py`, `stats_widgets.py`, `reglages_rubriques.py`, `reglages_table.py`, découpés le 2026-10-03 : voir le haut d'ARCHITECTURE.md) — `src/core/` : `config.py`, `game_data.py`, `game_manager.py`, `compat.py`, `preparation_wine.py`, `game_registry.py`, `reglages_correctif.py`, `touches_correctif.py`, `game_language.py`, `pre_launch.py`, `downloader.py`, `self_update.py`, `installer.py`, `extractors.py`, `post_install.py`, `trailers.py`, `thread_utils.py`, `stats.py`, `choixpeau.py`, `captures.py`, `manette.py`, `manette_lecture.py`, `reparation_config.py`, `sauvegardes.py`, `season.py`, `almanach.py`, `scolarite.py`, `updater.py`, `echecs.py`, `diagnostic.py`, `single_instance.py`, `discord_presence.py`, `system_checks.py`.
`src/ui/` : `main_window.py`, `window_chrome.py`, `game_session.py`, `update_dispatcher.py`, `notification_bar.py`, `game_detail.py`, `game_operations.py`, `action_panel.py`, `alert_banner.py`, `info_panel.py`, `flow_layout.py`, `carousel.py`, `carousel_item.py`, `video_player.py`, `background_widget.py`, `download_bar.py`, `trailer_store.py`, `stats_dialog.py`, `settings_panel.py`, `about_page.py`, `onboarding.py`, `theme.py`, `splash.py`, `icon_button.py`, `ticker.py`, `focus_visible.py`, `toggle_switch.py`, `tray_manager.py`, `fonts.py`, `utils.py`, `game_detail_handlers.py`, `crash_dialog.py`, `clickable_label.py`, `styles.py`, `manette_nav.py`.

**Ce qui casse un jeu sans bruit** (détail dans CATALOGUE_ET_JEUX.md) : ne jamais retirer `Running.ini` du catalogue (hp1/hp2) ; ne jamais passer `StartupFullscreen=True` ; HP7 ne démarre que dans un sous-dossier `pc` ; un `.int` sans sa DLL casse HP1/HP2 ; HP3 jamais au-delà de 60 images/s ; `requires_file` et les valeurs `Locale` diffèrent entre HP7 parties 1 et 2.

## Testing

- `pytest-qt>=4.5` ; `qtbot` est la façon standard de tester un widget. `tests/conftest.py` force `QT_QPA_PLATFORM=offscreen`.
- La logique pure (tout `src/core/` sauf les QThread) se teste sans fixture Qt.
- **Compte au dernier point (2026-10-01) : 2313 sous Linux au passage du portable (+33 sautés : Windows uniquement et Georgia) ; 2359 sous Windows (+30 sautés).** 25 sont des tests Linux qui exigent le système (chemins POSIX du préfixe, liens symboliques, bit exécutable, sockets Unix, `/bin/sh`, 7-Zip Linux) ; le dernier est `tests/test_fonts.py`, qui compare Gelasio à **Georgia**, absente sous offscreen — rien à comparer, pas de défaut. Un `s` n'est jamais un échec ; ce qui doit alerter, c'est leur NOMBRE qui grimpe. Tout nouveau module → au moins un test sentinelle.
- `tests/test_integration_smoke.py` pilote une vraie MainWindow offscreen — c'est là qu'on teste le câblage bout-en-bout. **`tests/test_parcours.py` suit un joueur d'un bout à l'autre** (archive locale → vrai extracteur → JOUER → vrai moniteur de processus → retour → désinstallation, plus la barre du bas pendant la préparation de Wine) sur un jeu FABRIQUÉ : seuls le réseau et le processus du jeu sont simulés. Son premier passage a trouvé la règle 134, invisible à tous les tests d'étape. `tests/test_downloader_stream.py` injecte un faux `httpx` dans `sys.modules`.
- **Piège polices** : sous offscreen, `QFontDatabase.families()` rend **zéro famille** et Qt substitue Cinzel, **22 % plus large et 16 % plus haute d'interligne** (421 px contre 344 sur la même phrase). Toutes les mesures de mise en page portent donc sur une autre police que celle de l'utilisateur — conservateur pour la troncature horizontale, **faux dès qu'un empilement de hauteurs entre en jeu**. D'où **`tools/audit_geometrie.py`**, lancé par `build.bat` sur la plateforme native avec `WA_DontShowOnScreen` : 8 jeux × 4 états × 4 tailles × **2 scénarios** (`nominal`, `bandeau`) × toutes les langues. Le scénario `bandeau` a été ajouté parce que l'outil écartait le bandeau d'alerte — exactement là où vivait un débordement de 20 px en espagnol.
- **La machine par défaut des tests est « prête à jouer », sous Linux aussi** : `conftest._linux_pret_a_jouer` pose un lanceur FACTICE (chemin inexistant : un `Popen` oublié échoue franchement au lieu de lancer Wine) et un préfixe prêt, composants compris, dans un `_Launcher/` temporaire À PART (dans `tmp_path`, il se mêlait à ce que d'autres tests y listent). Sans elle, le runner (sans Wine) affichait « Wine introuvable » partout et un poste qui a Wine l'aurait lancé. **`sans_lanceur`** pour le cas contraire ; `lanceur_factice` rend le faux. Les tests Linux SIMULENT `sys.platform` et tournent aussi sous Windows.
- **Aucun test n'écrit dans le vrai Documents** : `conftest._documents_hors_du_vrai_dossier` redirige `get_documents_dir` de `post_install` et `pre_launch`, sur le même dossier que la garde des sauvegardes. Les tests de lancement neutralisaient les étapes UNE PAR UNE, par leur nom : une étape ajoutée sans compléter la liste aurait écrit chez la personne qui lance la suite.
- **Piège env** : si pytest-qt n'est pas dans le Python actif, les fichiers de tests widgets sont silencieusement skippés et le compte chute (~110). Vérifier `python -m pip show pytest-qt`.

## Key Conventions

- Type hints 3.10+ (`str | Path`) ; `pathlib.Path` partout.
- Le travail threadé utilise des `QThread` avec `progress` / `error` + **un signal de fin NOMMÉ** (`download_finished`, `install_finished`, `result`) — jamais `finished`, qui masquerait le natif. Déconnecter symétriquement (try/except `TypeError`) avant de mettre à None.
- Annuler un `QThread` : `cancel()` puis `wait(3000)` avant de relâcher la référence ; au timeout, le garer dans `GameOperations._zombies` et le récolter via `finished`. **Ne jamais laisser un nouveau téléchargement rouvrir un `.part` qu'un vieux thread tient encore** (verrou Windows).
- Tous les callbacks qui mutent l'état vivent sur l'orchestrateur ; les widgets sont des consommateurs bêtes.
- Un slot qui parle à un `QDialog` après sa fermeture possible doit vérifier sa vivacité (patron `_force_update_check` : drapeau + `dlg.destroyed.connect`).
- **Arborescence utilisateur** : `~/Games/AccioLauncher/` ne contient QUE les dossiers de jeux ; tout le reste vit dans `_Launcher/` (`config.json`, `catalog_cache.json`, `sessions.json`, `i18n/`, `trailers/`, `logs/`, `cache/`). Quelqu'un qui ouvre ce dossier veut y voir ses JEUX, et une plomberie visible invite à être supprimée au hasard. **Deux régimes délibérés** : les données du launcher sont à un chemin FIXE (`LAUNCHER_DATA_PATH`) — déplacer ses jeux ne doit pas rendre les journaux introuvables — tandis que le **cache suit `install_path`** (`cache_pour()`), parce qu'une archive de 7 Go doit atterrir sur le même volume que son extraction, sans quoi le rangement devient une copie et la vérification d'espace ment. `migrer_arborescence()` est appelée **avant le logging** (un `RotatingFileHandler` tiendrait le fichier ouvert) **et avant `Config.exists()`** (sinon l'assistant rouvrirait chez quelqu'un qui a huit jeux). Idempotente, n'écrase jamais une destination existante.
- Versions : `0.0.x` bugfix · `0.x.0` jeu ajouté · `x.0.0` tous les jeux livrés. Le numéro vit à TROIS endroits — `pyproject.toml`, `config.APP_VERSION`, badge README — accord tenu par `tests/test_config.py`, et `release.yml` refuse un tag qui ne porte pas `APP_VERSION`.
- `pyproject.toml` fait foi pour les dépendances. **`requires-python = ">=3.12"`** et surtout pas `>=3.10` : `enum.StrEnum` exige 3.11, donc l'ancienne borne laissait pip installer le paquet sur un interpréteur où il plante à l'import.
- **Le jeu de règles ruff est figé** (`select = ["E4","E7","E9","F","W"]`). Sans cette section, « le projet est propre » dépendait du défaut de la version installée : 0.15 → 0.16 a fait apparaître 119 signalements sans qu'une ligne change. `I`/`UP`/`B`/`SIM`/`C4`/`RET` sont des adoptions candidates, à traiter en une passe dédiée.
- Thème sombre (`#060611`, or `#d6a72c`). Tout nouveau stylesheet contenant un hex or OU une surface bleu nuit doit passer par `theme.themed(...)` ; tout `QColor` or dans un paintEvent par `accent_qcolor(alpha)`, tout voile sombre par `bg_qcolor(alpha)`.
- **Ko-fi sans nag** : exactement UN remerciement dans la vie du launcher (`kofi_milestone_thanked`, cap **2 h**, `_KOFI_CAP_SECONDES`). Le cap était à 10 h : le remerciement n'existant qu'une fois, le placer si loin revenait à ne l'adresser à presque personne. **La règle « une seule fois » ne bouge pas.**
- Hero dynamique : la vue ouvre sur `manager.last_played_game_id()` via `carousel.select(idx)` — ne pas appeler `set_game` directement pour un index ≠ 0.
- Nav clavier : ←/→ routés par `MainWindow._handle_global_key` ; ne pas ajouter de `keyPressEvent` aux widgets pour ça. Les widgets d'édition gardent leurs flèches.

## Index des règles à ne pas réintroduire

134 règles, chacune payée une fois, détaillées avec leur mesure dans [docs/claude/REGLES.md](docs/claude/REGLES.md). Ouvrir la règle avant de toucher au sujet qu'elle nomme.

**Processus, threads, sortie**
1. Lancer un programme par son seul nom
2. Faire taire Bandit sans relire
3. `terminate()` sur un QThread Python DANS le processus de pytest
4. Jeter le résultat d'un `wait()` sur un `QThread` à la fermeture
5. Importer un module d'extension Qt (`QtNetwork`, `QtMultimedia`, `QtSql`…) depuis une FONCTION
6. Nommer une constante `subprocess.CREATE_*` ailleurs qu'à l'import, sous garde
7. `finished = pyqtSignal(...)` sur un QThread
8. Brancher un signal Qt directement sur une méthode de `GameManager`
9. Ajouter un argument à un signal sans mettre à jour TOUS ses slots
10. Appeler une `@property` comme une méthode
11. Un objet Qt durable créé sans parent
12. Monkeypatcher un attribut de CLASSE Qt dans un test
133. Détruire un `QThread` depuis le slot de son PROPRE signal de fin nommé

**Qt : peinture, focus, widgets**
13. Compter sur la feuille de style pour peindre le fond d'un `QWidget` nu
14. Croire qu'un `setFont()` l'emporte sur un stylesheet
15. Un widget PEINT qui se laisse cliquer sans se laisser atteindre au clavier
16. Un sélecteur `:focus` non conditionné
17. `Ticker.instance().tick.disconnect(...)`
18. Un `QTimer` dédié par animation décorative
19. Une animation décorative sur une `QPropertyAnimation`
20. Un zoom (ou toute animation) qui repeint le fond EN BOUCLE
21. `update()` nu sur un overlay translucide plein écran
22. Laisser un `paintEvent` grossir en mur
23. `label.mousePressEvent = lambda …`
24. `MainWindow.mouseMoveEvent`
25. Appeler `QDesktopServices.openUrl(QUrl(url))` directement
26. `hasattr` / `getattr` sur des attributs de widget
27. Un slot qui touche un `QDialog` après `exec()` sans vérifier sa vivacité
28. Un `QMenu` positionné sur `QCursor.pos()` seul
29. Poser un widget en absolu dans `MainWindow` sans tenir compte du bandeau
30. Un `QPushButton` qui porte pictogramme ET libellé sans écart
31. Une icône de zone de notification qui n'écoute que `DoubleClick`
32. Transporter une taille en octets dans un `pyqtSignal(int)`
33. Cacher explicitement (`hide()`) un widget qu'on va reposer dans une page
34. Poser l'icône sur une fenêtre plutôt que sur l'application

**Mise en page et mesure**
35. Dimensionner une vignette de carrousel par une constante, indépendamment de la bande
36. Positionner un widget flottant d'après un nombre écrit à la main
37. Un libellé posé à côté d'un bouton à largeur FIXE
38. Un `QLabel` en `wordWrap` dans un layout sans hauteur imposée
39. Additionner le `sizeHint` d'un layout contenant un `QLabel` `wordWrap`
40. Reconstruire le panneau d'actions sans repositionner le panneau d'infos
41. Rogner du TEXTE avant d'avoir récupéré le VIDE
42. Laisser une passe de `_fit_info_height` ne pas se réarmer
43. Laisser un état de mise en page décidé pour UN contenu survivre au suivant
44. Terminer le fond de la fiche sur autre chose que `bg_qcolor(255)`
45. Terminer une couche opaque PILE sur le bord logique d'un widget
46. Un `p.scale(ratio, ratio)` sur un `QPainter` ouvert sur un `QPixmap` à `devicePixelRatio`
47. Mesurer avec `mapTo` sur un widget qui n'est pas un ANCÊTRE
48. Mesurer une hauteur pilotée par `resizeEvent` sur un widget non AFFICHÉ
49. Un `min-width` de feuille de style sur un bouton dont le libellé peut grandir
50. `drawText` centré pour un libellé qui peut grandir
51. Servir un pictogramme sous ~18 px, ou passer à une graisse plus fine
52. Poser une page qui peut déborder sans zone défilante

**Texte, i18n, contenu distant**
53. Peindre du texte au `drawText` sans passer par `tr()`
54. Remettre des traductions dans du Python
55. Traduire le catalogue via `tr()`
56. Écrire un JSON de langue ou de catalogue avec `ensure_ascii=True`
57. Laisser un widget en `AutoText` afficher du texte de catalogue
58. Insérer du texte de catalogue dans un QLabel `RichText` sans l'échapper
59. Un pictogramme Unicode dans un libellé
60. Croire qu'`Emoji_Presentation=No` garantit un rendu monochrome
61. Retracer à la main un pictogramme, et surtout une marque
62. Trois boutons de lien qui ne se distinguent que par leur libellé
63. Écrire une adresse du projet ailleurs que dans `src/core/liens.py`
64. Laisser la ligne méta se couper au milieu d'une information
65. Un texte semi-transparent par-dessus une image
66. Croire qu'un voile uniforme protège le texte
67. Construire une page traduite UNE fois et la garder quand la langue change

**Catalogue, registre, sécurité**
68. Injecter dans un `.reg` ce qui vient du catalogue
69. Modifier le registre de quelqu'un sans le prévenir
70. Écrire un fichier destiné à une exécution ÉLEVÉE sous un nom prévisible
71. Un test qui peut faire apparaître une invite UAC
72. Recopier les valeurs de registre d'un jeu vers sa suite
73. Croire qu'une clé de registre suffit à changer la langue d'un jeu
74. Ré-écrire une plomberie `registry` dans le catalogue
75. Recopier une empreinte SHA-256 à la main dans `games.json`
76. Croire que la vérification protège d'un dépôt compromis
77. Supposer que « \ » est un séparateur de chemin
78. Faire dépendre un test du CONTENU de `games.json`

**Fichiers, encodage, build**
79. Écrire un chemin dans le corps d'un `.bat`
80. Laisser un `.bat` prendre des fins de ligne LF
81. Lire un fichier écrit par un AUTRE programme dans notre encodage
82. Laisser `write_text` choisir les fins de ligne d'un fichier qui ne nous appartient pas
83. Nommer un fichier de cache d'après l'URL dont il vient
84. Déduire d'une différence d'inventaire ce qu'il faut débloquer
85. Comparer des versions comme des CHAÎNES
86. Prendre `size_mb` pour la taille d'une archive
87. Régénérer `assets/accio_launcher.ico` depuis un PNG
88. Ignorer `assets/accio_launcher.ico` dans `.gitignore`
89. Appeler une police par son nom système
90. Réembarquer une bande-annonce dans l'exécutable
91. Nommer une bande-annonce locale d'après son asset
92. Re-ajouter py7zr
93. Mélanger les jeux et la plomberie dans le dossier utilisateur
94. Laisser PyInstaller embarquer tout ce que Qt livre

**Orchestration et états**
95. Changer `install_path` sans `manager.refresh_states()`
96. Désinstaller avant que le téléchargement de remplacement ne finisse
97. Ré-implémenter les lignes de progression
98. Recopier le seuil ou le calcul de reprise
99. Ajouter un champ à `Config` sans toucher à `save()` ET `load()`
100. Double-firing des items du `Carousel` via `set_games` sans réémettre `game_selected`
101. Reconstruire le carrousel sans lui redire QUEL jeu est affiché
102. Armer un `QTimer.singleShot` pour un démarrage différé
103. `apply_pre_launch_patches` à l'installation
104. Lancer un jeu sans lui donner la couche de compatibilité DPI
105. Écrire une config quand l'assistant de premier lancement n'aboutit pas
106. Croire qu'une configuration posée à l'installation est encore là au lancement
134. Émettre un signal d'état AVANT que l'état existe

**Ce que l'interface a le droit de dire**
107. Afficher un état NORMAL
108. Affirmer un résultat qu'on n'a pas obtenu
109. Déclarer « hors ligne » sur une erreur HTTP
110. Laisser l'état hors-ligne sans re-tentative
111. Une boîte d'échec qui accuse la connexion sans le savoir
112. Annoncer un échec de téléchargement sans dire ce qui est CONSERVÉ
113. Proposer une mise à jour du launcher sans dire ce qu'elle CONTIENT
114. Effacer tout seul une notification qui demande une action
115. Transformer un modal de QUESTION ou d'ERREUR en toast
116. `QMessageBox.StandardButton.Yes` / `.No`, et les raccourcis `question()` / `warning()` / `information()`
117. Empiler plusieurs avertissements dans le bandeau
118. Poser un réglage sans rien qui dise qu'il en est un
119. Un bloc qui a l'air d'un bouton et ne répond pas
120. Un seuil d'affichage sur le compteur de téléchargements
121. Remettre une durée estimée sur le bouton TÉLÉCHARGER
122. Confondre une DURÉE et un TEMPS RESTANT
123. Figer le statut du démarrage dans une image
124. Revenir à `QSplashScreen`
125. Traiter le choix « je veux les bandes-annonces » comme une réponse jetable
126. Télécharger en arrière-plan sans que rien à l'écran ne le dise

**Produit : ce qui a été tranché**
127. Poser un DESSIN dans un coin de la fiche
128. Une ambiance de l'Almanach qui ne dure qu'un JOUR
129. Dire qu'une année « attend » alors qu'elle est DERRIÈRE

**Linux et AppImage**
130. Embarquer dans l'AppImage ce que la machine fournit
131. Laisser un greffon tirer une pile entière
132. Construire l'AppImage sur une machine qui n'a pas les dépendances des greffons
- Déduire le SENS d'un jeu de son RANG dans le catalogue
- Laisser un bloc grossir dans un fichier hôte parce qu'il « va avec »

**Pièges de test récurrents**
- Un test de mise en page avec un `qtbot.wait(n)` fixe
- Un test qui n'appelle que `pixmap_icone` sans demander `qtbot`
- Émettre un signal d'UI sur une VRAIE fenêtre sans regarder où il est câblé
- Attendre un fichier écrit par un autre processus en testant son existence
