"""La table des réglages du correctif : les choix proposés, la classe `Reglage`, la table `REGLAGES` (ordre d'affichage) et les `PREREGLAGES`. Pure donnée ; la lecture et l'écriture du `d3d9.ini` restent dans `reglages_correctif`, qui réexporte tout. Sortie le 2026-10-03.
"""
from __future__ import annotations
from dataclasses import dataclass

# Choix proposés pour la limite d'images. 0 = aucune.
LIMITES_FPS = (0, 60, 100, 120, 144)
# Échantillons du MSAA. Le correctif descend de lui-même à ce que la carte sait
# faire ; 16 n'est pas proposé : peu de cartes le font, et l'écart avec 8 ne se
# voit pas.
ECHANTILLONS_MSAA = (0, 2, 4, 8)
# Filtrage anisotrope : 0 = éteint (textures floues de biais), 16 = livré.
FILTRAGES = (0, 2, 4, 8, 16)
# Vivacité et contraste de l'étalonnage : des crans nommés plutôt que des
# nombres, qui ne disent rien à qui ne connaît pas le correctif. Les valeurs
# livrées y sont toutes (HP4/HP6 0.30 et 0.20, HP5 0.60 et 0.30).
VIVACITES = ((0, "Aucune"), (0.15, "Légère"), (0.3, "Moyenne"), (0.45, "Forte"), (0.6, "Très forte"))
CONTRASTES = ((0, "D'origine"), (0.1, "Léger"), (0.2, "Moyen"), (0.3, "Fort"))
# Netteté après le FXAA (livrée à 0.40 partout) et netteté des textures au loin
# (TextureLODBias : négatif = plus net ; HP5 livré à -1.5).
NETTETES = ((0, "Aucune"), (0.2, "Légère"), (0.4, "Moyenne"), (0.6, "Forte"))
NETTETES_LOINTAINES = ((0, "D'origine"), (-0.5, "Un peu plus nettes"), (-1, "Plus nettes"),
                       (-1.5, "Très nettes"))
# Taille de l'image au démarrage, [Accio.Game] Width et Height. Le jeu livré
# démarre en 640×480 : c'est l'« éteint », écrit tel quel s'il est choisi.
RESOLUTIONS = (("640x480", ""), ("1280x720", "1280×720"), ("1600x900", "1600×900"),
               ("1920x1080", "1920×1080"), ("2560x1440", "2560×1440"), ("3840x2160", "3840×2160"))
# WindowStyle du correctif : 1 = sans bordure sur tout l'écran (recommandé).
MODES_FENETRE = ((1, "Plein écran sans bordure"), (2, "Fenêtre"), (3, "Fenêtre redimensionnable"),
                 (4, "Sans bordure, à la taille de l'image"))
# AspectRatio : 0 = format livré. Les rapports sont écrits tels que le correctif les lit.
FORMATS = (("0", ""), ("16:9", "16:9"), ("16:10", "16:10"), ("21:9", "21:9"), ("32:9", "32:9"))
# Langues du menu de démarrage de HP6 (les 16 qu'il propose), écrites dans leur
# propre langue comme dans le menu du jeu : un nom de langue ne se traduit pas
# pour celui qui la cherche. « auto » (le défaut du correctif) est la langue de
# Windows ramenée à la variante que le jeu connaît.
LANGUES_MENU = (
    ("auto", ""), ("en", "English"), ("fr", "Français"), ("es", "Español"), ("de", "Deutsch"),
    ("it", "Italiano"), ("nl", "Nederlands"), ("pt", "Português"), ("pt-br", "Português (Brasil)"),
    ("pl", "Polski"), ("ru", "Русский"), ("sv", "Svenska"), ("da", "Dansk"), ("fi", "Suomi"),
    ("no", "Norsk"), ("cs", "Čeština"), ("hu", "Magyar"),
)

# Le préréglage « déplacement à gauche du clavier + sorts à la souris » :
# celui que l'ini livre en commentaire (tools/make_ini.py du correctif). Le
# correctif lit les touches par le nom IMPRIMÉ sur le clavier du joueur
# (keys.cpp) : les mêmes POSITIONS s'appellent ZQSD sur un AZERTY et WASD sur
# un QWERTY. Écrire « Z » pour tout le monde aurait mis « avancer » en bas à
# gauche d'un clavier américain. Les positions sont donc des codes de balayage
# (ceux d'un clavier US : W A S D, puis E et R), traduites en lettres selon la
# disposition active.
_POSITIONS = (("MoveUp", 0x11, "W"), ("MoveLeft", 0x1E, "A"), ("MoveDown", 0x1F, "S"),
              ("MoveRight", 0x20, "D"), ("Accio", 0x12, "E"), ("Extremos", 0x13, "R"))
_SOURIS = (("Charm", "MouseLeft"), ("Jinx", "MouseRight"))

# Le panneau de performances : tout ce que l'overlay sait afficher en plus du
# compteur d'images, réglé d'un seul geste (le détail reste dans l'ini).
_PANNEAU = ("ShowFrameTime", "ShowGraph", "ShowCPU", "ShowGPU", "ShowVRAM", "ShowRAM", "ShowLatency")
# La résolution : deux clés, un seul choix (« 1920x1080 »).
_RESOLUTION = ("Width", "Height")


@dataclass(frozen=True)
class Reglage:
    ident: str
    section: str
    cle: str          # vide pour un réglage composé (touches, panneau)
    libelle: str      # clé tr() ; passer par textes() pour l'afficher
    aide: str         # clé tr()
    defaut: bool = True   # interrupteur : ce que fait le correctif quand la clé manque
    # Réglage à CHOIX (liste déroulante) : les valeurs proposées, dans l'ordre.
    # La PREMIÈRE (0 d'ordinaire ; 1 pour un facteur) s'affiche `zero` (clé
    # tr()) et vaut aussi pour une clé absente ; les autres s'affichent avec
    # `format_choix`. Vide : un interrupteur.
    # Des choix TEXTUELS (une langue) portent leur libellé : `noms_choix`,
    # (valeur, libellé) ; le premier vaut pour une clé absente et s'affiche
    # `zero`.
    choix: tuple = ()
    zero: str = ""
    format_choix: str = "{}"
    noms_choix: tuple[tuple[str, str], ...] = ()
    # L'onglet de la fenêtre de réglages : quelqu'un qui cherche son clavier ne
    # doit pas traverser l'anticrénelage (Ludo, 2026-09-28).
    onglet: str = "jeu"
    # Ce que le réglage demande à la machine, au plus fort de ses choix :
    # (ressource, niveau 1 à 3) — « GPU », « CPU », « RAM ». Affiché en repère,
    # pour diriger vers ce qui coûte avant qu'un PC modeste ne rame.
    cout: tuple[tuple[str, int], ...] = ()
    # Change-t-il VRAIMENT l'image ? Beaucoup d'effets sont discrets ; ceux-là se voient.
    se_voit: bool = False
    # Libellés de choix NUMÉRIQUES (clés tr()) : (valeur, libellé). Le premier
    # s'affiche quand même `zero`. Vide : `format_choix`.
    etiquettes: tuple[tuple[object, str], ...] = ()
    # Ce que le correctif fait VRAIMENT de ces clés (Ludo, 2026-09-28 : « si un
    # paramètre désactive d'autres paramètres, il faut que ça se voie dans le
    # launcher ») :
    # `depend_de` — sans CE réglage allumé, celui-ci n'a aucun effet (grisé) ;
    # `exclut` — l'allumer éteint l'autre, dans l'ini comme à l'écran.
    depend_de: str = ""
    exclut: str = ""


# L'ordre est celui de l'affichage. L'aide est une description COMPLÈTE : elle
# ne s'affiche plus sous la ligne mais dans la fiche du « ? » (Ludo, 2026-09-30),
# qui y ajoute d'elle-même le coût, « se voit » et les dépendances.
REGLAGES: dict[str, Reglage] = {r.ident: r for r in (
    # ── Affichage (onglet Image, au-dessus de la qualité) ──
    # Clés lues par le nouveau correctif (tools/make_ini.py du dépôt du
    # correctif), ouvertes au lanceur le 2026-09-30 à la demande de Ludo : À VOIR
    # EN JEU avant de publier le catalogue qui les déclare.
    Reglage("resolution", "Accio.Game", "",
            "Résolution",
            "La taille de l'image au démarrage du jeu, livré en 640×480. Choisissez celle de "
            "votre écran pour l'image la plus nette ; elle se change aussi dans les options "
            "du jeu.",
            choix=tuple(v for v, _ in RESOLUTIONS), zero="D'origine (640×480)",
            noms_choix=RESOLUTIONS, onglet="affichage"),
    Reglage("mode_fenetre", "Accio.Window", "WindowStyle",
            "Mode d'affichage",
            "Plein écran sans bordure : le jeu couvre tout l'écran, et Alt+Tab passe à une "
            "autre fenêtre sans le figer (recommandé). Fenêtre : une fenêtre ordinaire, "
            "redimensionnable ou non. Sans bordure à la taille de l'image : ni cadre ni "
            "étirement.",
            choix=tuple(v for v, _ in MODES_FENETRE), zero="Plein écran sans bordure",
            etiquettes=MODES_FENETRE, onglet="affichage"),
    Reglage("format_image", "Accio.Game", "AspectRatio",
            "Format d'image",
            "Le format de l'image. « D'origine » garde celui que prévoit le jeu ; choisissez "
            "celui de votre écran (16:10, 21:9, 32:9) pour que l'image le remplisse sans être"
            " étirée.",
            choix=tuple(v for v, _ in FORMATS), zero="D'origine", noms_choix=FORMATS,
            onglet="affichage"),
    Reglage("champ_vision", "Accio.Game", "FOV",
            "Champ de vision",
            "Élargit l'angle de vue de la caméra : on voit davantage autour du personnage, "
            "surtout utile sur un écran large. « D'origine » garde la vue du jeu.",
            choix=(0, 1.15, 1.25, 1.4), zero="D'origine", format_choix="×{}",
            onglet="affichage"),
    Reglage("ecran_principal", "Accio.Window", "UsePrimaryMonitor",
            "Toujours sur l'écran principal",
            "Avec plusieurs écrans, ouvre toujours le jeu sur l'écran principal de Windows. "
            "Éteint, il s'ouvre sur l'écran où il démarre.",
            defaut=False, onglet="affichage"),
    Reglage("premier_plan", "Accio.Window", "AlwaysOnTop",
            "Toujours au premier plan",
            "En mode fenêtre, garde le jeu devant toutes les autres fenêtres, même quand vous"
            " cliquez ailleurs.",
            defaut=False, onglet="affichage"),
    # ── Jeu, commandes, performances ──
    Reglage("arriere_plan", "Accio.Window", "KeepRunningInBackground",
            "Continuer à tourner après un Alt+Tab",
            "Le jeu ne se fige plus quand une autre fenêtre passe devant, et reprend le "
            "clavier dès qu'on revient."),
    Reglage("limite_fps", "Accio.Window", "FPSLimit",
            "Limite d'images par seconde",
            "Plafonne le nombre d'images calculées : l'ordinateur chauffe moins et fait moins"
            " de bruit.",
            choix=LIMITES_FPS, zero="Aucune", onglet="perfs"),
    # HP7 partie 1 : au-delà de 60 images/s, ses cinématiques passent en accéléré
    # (Ludo, 2026-10-01). Même clé, choix bornés ; le correctif tient aussi
    # `FPSCeiling=60` au cas où l'ini dirait plus.
    Reglage("limite_fps_60", "Accio.Window", "FPSLimit",
            "Limite d'images par seconde",
            "Ce jeu ne doit pas dépasser 60 images par seconde : au-delà, ses cinématiques "
            "passent en accéléré. 30 fait moins chauffer l'ordinateur.",
            choix=(60, 30), zero="60 (vitesse normale)", onglet="perfs"),
    Reglage("synchro_verticale", "Accio.Graphics", "VSync",
            "Synchronisation verticale",
            "Cale les images sur la fréquence de l'écran : plus de déchirure horizontale "
            "quand la caméra tourne. En contrepartie, un peu plus de délai entre la souris et"
            " l'image. Avec une limite d'images qui ne divise pas la fréquence de l'écran, le"
            " jeu peut retomber à la moitié de celle-ci (144 sur un écran à 180 Hz donne 90"
            " images) : choisissez alors une autre limite.",
            defaut=False, onglet="perfs"),
    Reglage("touches_zqsd", "Accio.Keys", "",
            "Déplacement {} et sorts à la souris",
            "Se déplacer avec {0}, Charme au clic gauche, Maléfice au clic droit, Accio sur "
            "{1}, Extremos sur {2}. Les touches d'origine continuent de marcher, sauf {3}, "
            "qui fait reculer.", onglet="commandes"),
    # [Accio.Controller] est lu par le xinput1_3.dll du correctif (HP5-HP7b) ;
    # HP4 n'a pas cette DLL, son correctif lit sa propre clé dans [Accio.Game].
    Reglage("manette_playstation", "Accio.Controller", "PlayStation",
            "Manette PlayStation reconnue",
            "Une manette PlayStation 4 ou 5 branchée est vue comme une manette Xbox, que le "
            "jeu connaît. Éteignez-le si Steam Input ou DS4Windows la convertissent déjà : le"
            " jeu la verrait deux fois.", onglet="manette"),
    Reglage("manette_playstation_hp4", "Accio.Game", "PlayStationController",
            "Manette PlayStation reconnue",
            "Une manette PlayStation 4 ou 5 branchée est vue comme une manette Xbox, que le "
            "jeu connaît. Éteignez-le si Steam Input ou DS4Windows la convertissent déjà : le"
            " jeu la verrait deux fois.", onglet="manette"),
    Reglage("vibrations", "Accio.Controller", "Rumble",
            "Vibrations de la manette PlayStation",
            "Les vibrations d'une manette PlayStation branchée en USB. Sans effet en "
            "Bluetooth.", onglet="manette"),
    # ── Qualité d'image (préréglages, puis le détail) ──
    # HP4 seulement : dans le correctif, le FXAA porte aussi l'étalonnage, le
    # SSAO, le bloom et les rayons ; sur HP5 (réglages d'image de Ludo, tous
    # allumés) l'éteindre les éteindrait tous.
    Reglage("lissage", "Accio.Graphics", "FXAA",
            "Lissage des contours (FXAA)",
            "Adoucit les escaliers au bord des personnages et du décor (cheveux, vêtements, "
            "toiles de tente), avec un léger renforcement de la netteté. Il porte aussi les "
            "effets ci-dessous : l'éteindre éteint ombres de contact, halo, rayons et "
            "couleurs.",
            defaut=False, onglet="image", cout=(("GPU", 1),), se_voit=True),
    Reglage("nettete", "Accio.Graphics", "Sharpness",
            "Netteté",
            "Rend du piqué à l'image que le lissage (FXAA) adoucit : contours et textures "
            "plus nets. Trop fort, un liseré clair apparaît autour des contours.",
            choix=tuple(v for v, _ in NETTETES), zero="Aucune", etiquettes=NETTETES,
            onglet="image", cout=(("GPU", 1),), depend_de="lissage"),
    # HP4 et HP6, vu en jeu le 2026-09-25 (contours lissés, 99 FPS tenus sur
    # HP4) avec le correctif qui multi-échantillonne la cible de scène du jeu
    # et garde l'anticrénelage que le jeu éteint. Pas HP5 : avec son SSAO, le
    # MSAA n'atteint pas la scène (la profondeur lue ne se multi-échantillonne
    # pas en Direct3D 9).
    Reglage("anticrenelage", "Accio.Graphics", "Antialiasing",
            "Anticrénelage (MSAA)",
            "Lisse les contours des personnages et du décor en calculant plusieurs points par"
            " pixel. Plus le nombre est grand, plus c'est lisse, et plus la carte graphique "
            "travaille. L'allumer éteint les ombres de contact, qui l'empêchent d'atteindre "
            "le décor.",
            choix=ECHANTILLONS_MSAA, zero="Désactivé", format_choix="{}×",
            onglet="image", cout=(("GPU", 2),), se_voit=True, exclut="occlusion"),
    # HP4 et HP6, vu en jeu le 2026-09-26 : sous le seul MSAA, les bords
    # découpés (cheveux, feuilles, herbe) restent en escalier ; le correctif
    # les suréchantillonne sur carte NVIDIA (mèches de Harry et Ron au choix du
    # personnage de HP4, pins de HP6). Coût : 1 % low 101 → 76 sur HP6 en
    # 2560×1440, 94 → 84 sur HP4 (RTX 2060 SUPER). Sans effet sans MSAA.
    Reglage("anticrenelage_transparence", "Accio.Graphics", "TransparencyAntialiasing",
            "Cheveux et feuillage lissés",
            "Avec l'anticrénelage, lisse aussi les pointes des cheveux, les feuilles et "
            "l'herbe. Cartes NVIDIA seulement ; demande plus à la carte graphique là où il y "
            "a beaucoup de feuillage.", defaut=False,
            onglet="image", cout=(("GPU", 2),), depend_de="anticrenelage"),
    # HP5, vu en jeu le 2026-09-26 : son occlusion ambiante lit la profondeur
    # comme une texture, ce qui ferme le MSAA à la scène ; le suréchantillonnage
    # (image calculée en ×2 puis réduite) lisse quand même, et affine textures
    # et contours lointains (tapisseries, vitraux, échiquier). Coût mesuré en
    # 2560×1440, RTX 2060 SUPER : moyenne 120 → 84, 1 % low 82 → 39. La première
    # valeur (1) est l'« éteint » du correctif. ×1,5 (un peu plus de deux fois
    # les pixels) : HP4 et HP6 le prennent eux aussi, joués ainsi par Ludo le
    # 2026-09-27/28 (forêt interdite, menus de HP6 qui cliquent juste) ; c'est
    # leur défaut depuis, parce qu'il veut « le moins de pixelisation possible ».
    Reglage("surechantillonnage", "Accio.Graphics", "SSAAFactor",
            "Suréchantillonnage",
            "Calcule l'image en plus grand puis la réduit : contours, cheveux, feuillages et "
            "détails lointains nettement plus fins. Le réglage qui se voit le plus, et le "
            "plus exigeant : ×2 est pour les PC puissants.",
            choix=(1, 1.5, 2), zero="Désactivé", format_choix="×{}",
            onglet="image", cout=(("GPU", 3),), se_voit=True),
    # Les effets du correctif (HP4-HP6), tous allumés dans les ini livrés et
    # joués ainsi ; F8 (CompareKey) les montre éteints. Ouverts au lanceur à la
    # demande de Ludo (2026-09-28) : « beaucoup d'options dans l'ini, quasiment
    # aucune modifiable depuis le launcher ». Tous passent par le FXAA.
    Reglage("filtrage", "Accio.Graphics", "AnisotropicFiltering",
            "Netteté des textures de biais",
            "Sols, murs et chemins vus en biais restent nets au lieu de devenir flous "
            "(filtrage anisotrope). Presque gratuit sur une carte récente.",
            choix=FILTRAGES, zero="Désactivé", format_choix="×{}",
            onglet="image", cout=(("GPU", 1),), se_voit=True),
    Reglage("textures_lointaines", "Accio.Graphics", "TextureLODBias",
            "Textures lointaines",
            "Garde les textures nettes plus loin : sols, murs et chemins restent détaillés au"
            " lieu de flouter avec la distance. Un réglage fort peut faire scintiller "
            "certaines surfaces.",
            choix=tuple(v for v, _ in NETTETES_LOINTAINES), zero="D'origine",
            etiquettes=NETTETES_LOINTAINES, onglet="image", cout=(("GPU", 1),)),
    Reglage("feuillage_lointain", "Accio.Graphics", "MipmapCoverage",
            "Feuillage dense au loin",
            "Feuilles, cheveux et grilles gardent leur densité au loin, au lieu de "
            "s'éclaircir puis de disparaître. Surtout visible dans les forêts.",
            defaut=False, onglet="image", cout=(("GPU", 1),)),
    Reglage("occlusion", "Accio.Graphics", "SSAO",
            "Ombres de contact",
            "Assombrit les recoins, le pied des murs et le contact des objets : le décor "
            "gagne en relief (occlusion ambiante). Les allumer éteint l'anticrénelage (MSAA).",
            defaut=False, onglet="image", cout=(("GPU", 2),), se_voit=True,
            depend_de="lissage", exclut="anticrenelage"),
    # « Expérimental » dans l'ini livré : agrandit aussi les reflets.
    Reglage("ombres_nettes", "Accio.Graphics", "ShadowMapScale",
            "Ombres plus nettes",
            "Calcule les ombres portées en plus fin : des bords nets au lieu de flous et "
            "crénelés. Expérimental : agrandit aussi les reflets, et demande plus de mémoire "
            "vidéo. À vos risques : sur Le Prince de Sang-Mêlé, ×4 laisse des taches sombres "
            "sur les personnages dehors quand la caméra tourne.",
            choix=(1, 2, 4), zero="D'origine", format_choix="×{}",
            onglet="image", cout=(("GPU", 2), ("RAM", 1))),
    Reglage("halo", "Accio.Graphics", "Bloom",
            "Halo lumineux",
            "Les lumières vives (fenêtres, torches, sorts) débordent doucement autour "
            "d'elles.",
            defaut=False, onglet="image", cout=(("GPU", 1),), depend_de="lissage"),
    Reglage("rayons", "Accio.Graphics", "GodRays",
            "Rayons de lumière",
            "Des rayons partent des sources de lumière fortes, comme le soleil à travers les "
            "arbres.",
            defaut=False, onglet="image", cout=(("GPU", 1),), depend_de="lissage"),
    Reglage("couleurs", "Accio.Graphics", "ColorGrading",
            "Couleurs retravaillées",
            "Active la vivacité et le contraste ci-dessous, en épargnant les visages. Éteint "
            ": les couleurs d'origine du jeu.",
            defaut=False, onglet="image", se_voit=True, depend_de="lissage"),
    Reglage("vivacite", "Accio.Graphics", "Vibrance",
            "Vivacité des couleurs",
            "Ravive les couleurs ternes sans saturer celles qui le sont déjà. Seulement avec "
            "« Couleurs retravaillées ».",
            choix=tuple(v for v, _ in VIVACITES), zero="Aucune", etiquettes=VIVACITES,
            onglet="image", se_voit=True, depend_de="couleurs"),
    Reglage("contraste", "Accio.Graphics", "Contrast",
            "Contraste",
            "Creuse l'écart entre zones claires et sombres. Seulement avec « Couleurs "
            "retravaillées ».",
            choix=tuple(v for v, _ in CONTRASTES), zero="D'origine", etiquettes=CONTRASTES,
            onglet="image", se_voit=True, depend_de="couleurs"),
    # HP6, vu en jeu le 2026-09-26 : le voile vert du décor lointain (ce que
    # Ludo trouvait « très flou au loin, comme un brouillard »). Éteint, les
    # collines du parc sont nettes (contraste du tiers lointain 21-27 → 25-31).
    # Un choix d'artiste du jeu : allumé par défaut, comme livré.
    Reglage("brouillard", "Accio.Game", "DistanceFog",
            "Brouillard lointain",
            "Le voile vert dans lequel le jeu noie le décor au loin. Éteint : collines et "
            "paysages nets et contrastés, la scène un peu plus sombre.",
            onglet="image", se_voit=True),
    Reglage("compteur_fps", "Accio.Overlay", "ShowFPS",
            "Compteur d'images (FPS)",
            "Affiche les images par seconde en haut à gauche. En jeu, F10 le masque ou le "
            "remet.",
            defaut=False, onglet="perfs"),
    Reglage("panneau_perfs", "Accio.Overlay", "",
            "Panneau de performances",
            "Temps par image et son graphe, processeur, carte graphique, mémoire vidéo et "
            "vive, latence. En jeu, F11 lance un benchmark et F11 à nouveau l'arrête ; il est"
            " enregistré dans le dossier « benchmarks » du jeu.",
            defaut=False, onglet="perfs", cout=(("CPU", 1),)),
    # HP6, vu en jeu le 2026-09-26 : son menu de langue s'ouvre sur la langue
    # de Windows, mais le jeu ne connaît qu'une variante de chaque langue — un
    # Windows en français de Belgique le faisait partir en ANGLAIS (le menu se
    # valide seul au bout de 15 s). « auto » : menu sur Français ; « es » :
    # sur Español. HP4 et HP5 ne demandent rien à Windows : pas pour eux.
    Reglage("langue_menu", "Accio.Game", "Language",
            "Langue au démarrage",
            "La langue sur laquelle s'ouvre le menu du jeu, qui la prend tout seul après "
            "quelques secondes. « Celle de Windows » corrige un défaut du jeu : un Windows en"
            " français de Belgique, de Suisse ou du Canada, ou en espagnol, le faisait "
            "démarrer en anglais.",
            choix=tuple(v for v, _ in LANGUES_MENU), zero="Celle de Windows",
            noms_choix=LANGUES_MENU),
)}

# Les préréglages de « Qualité d'image » : (identifiant, nom, ce qu'il fait,
# valeurs). Seulement ce qui COÛTE : le goût (couleurs, brouillard, netteté) et
# l'expérimental (ombres) ne bougent pas quand on choisit un préréglage. Le MSAA
# reste éteint partout : il exclut les ombres de contact, que les trois gardent
# ou éteignent ensemble.
PREREGLAGES = (
    ("legere", "Légère",
     "Pour un PC modeste ou un portable : effets de lumière éteints, contours lissés.",
     {"lissage": True, "anticrenelage": 0, "anticrenelage_transparence": False,
      "surechantillonnage": 1, "filtrage": 4, "occlusion": False, "halo": False,
      "rayons": False, "feuillage_lointain": False}),
    ("equilibree", "Équilibrée",
     "Tous les effets de lumière, sans suréchantillonnage.",
     {"lissage": True, "anticrenelage": 0, "anticrenelage_transparence": False,
      "surechantillonnage": 1, "filtrage": 16, "occlusion": True, "halo": True,
      "rayons": True, "feuillage_lointain": False}),
    ("maximale", "Maximale",
     "Tous les effets et l'image la plus fine (suréchantillonnage ×1,5), pour une "
     "carte graphique récente.",
     {"lissage": True, "anticrenelage": 0, "anticrenelage_transparence": False,
      "surechantillonnage": 1.5, "filtrage": 16, "occlusion": True, "halo": True,
      "rayons": True, "feuillage_lointain": True}),
)
