"""Réglages du correctif PC de HP4 à HP7 partie 2, lus et écrits dans son `d3d9.ini`.

Le correctif (dépôt Harry-Potter-PC-Fix) lit un `d3d9.ini` à côté de l'exécutable
du jeu. Ce module en règle QUELQUES clés depuis le lanceur ; tout le reste du
fichier appartient au joueur et n'est jamais réécrit.

Trois règles :

- **Seulement ce qui a été VU en jeu.** Le catalogue déclare, jeu par jeu, les
  réglages confirmés (`fix_settings`) ; un identifiant inconnu d'une version
  plus ancienne du lanceur est ignoré. Proposer un réglage qu'on n'a jamais
  regardé tourner, c'est déplacer le test chez le joueur.
- **Seulement le NOUVEAU correctif.** Les archives publiées portent encore
  l'ancien wrapper, dont l'ini n'a pas ces clés : on le reconnaît à l'absence
  de `[Accio.Window]`, et l'interface dit alors que les réglages arrivent avec
  la prochaine version, au lieu d'écrire des clés que personne ne lira.
- **Une édition en place.** Commentaires, ordre, fins de ligne (CRLF) et
  encodage restent ceux du fichier : seule la ligne de la clé change.
"""

from __future__ import annotations

import logging
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from src.core.i18n import decimal_separator, tr

log = logging.getLogger(__name__)

NOM_INI = "d3d9.ini"
# Copie de l'ini tel qu'il était AVANT la première retouche du lanceur : ce que
# « Rétablir les réglages d'origine » remet en place.
SUFFIXE_ORIGINE = ".origine"
_MARQUE_V2 = "Accio.Window"   # section qu'a seul le nouveau correctif

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


def _lettre(scan: int, repli: str) -> str:
    """La lettre imprimée à cette position sur le clavier actif (Windows).

    Ailleurs, la position US : sous Linux le jeu tourne sous Wine, dont la
    disposition ne se lit pas d'ici, et un QWERTY est le cas le plus répandu.
    """
    if sys.platform != "win32":
        return repli
    try:
        import ctypes
        vk = ctypes.windll.user32.MapVirtualKeyW(scan, 1)   # MAPVK_VSC_TO_VK
    except (AttributeError, OSError):
        return repli
    # Pour une lettre, le code de touche virtuelle EST la majuscule ASCII.
    return chr(vk) if 0x41 <= vk <= 0x5A else repli


def touches_preregle() -> tuple[tuple[str, str], ...]:
    """(action, touche) du préréglage, pour le clavier de CE poste."""
    return tuple((action, _lettre(scan, us)) for action, scan, us in _POSITIONS) + _SOURIS


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


def allume(reglage: Reglage, valeur) -> bool:
    """Le réglage agit-il ? Un interrupteur coché, ou un choix autre que le premier (l'« éteint »)."""
    if reglage.choix:
        return valeur != reglage.choix[0]
    return bool(valeur)


def eteint(reglage: Reglage):
    """La valeur qui l'éteint."""
    return reglage.choix[0] if reglage.choix else False


def bloque_par(reglage: Reglage, valeurs: dict) -> Reglage | None:
    """Le réglage ÉTEINT dont dépend celui-ci (directement ou non), ou None s'il agit.

    `valeurs` : identifiant → valeur, pour les réglages présents dans la fenêtre.
    Un parent absent (non déclaré pour ce jeu) ne bloque rien.
    """
    parent = REGLAGES.get(reglage.depend_de)
    while parent is not None and parent.ident in valeurs:
        if not allume(parent, valeurs[parent.ident]):
            return parent
        parent = REGLAGES.get(parent.depend_de)
    return None


def libelle_choix(reglage: Reglage, valeur) -> str:
    """Ce que la liste déroulante affiche pour une valeur."""
    if reglage.noms_choix:
        if valeur == reglage.choix[0]:
            return tr(reglage.zero)
        return dict(reglage.noms_choix).get(valeur, str(valeur))
    if valeur == reglage.choix[0]:
        return tr(reglage.zero)
    if reglage.etiquettes:
        return tr(dict(reglage.etiquettes).get(valeur, _nombre(valeur)))
    return reglage.format_choix.format(_nombre(valeur).replace(".", decimal_separator()))


def _nombre(valeur) -> str:
    """1.5 → « 1.5 », 2.0 → « 2 » : ce que lit le correctif, sans décimale inutile."""
    return f"{valeur:g}" if isinstance(valeur, float) else str(valeur)


def textes(reglage: Reglage) -> tuple[str, str]:
    """(libellé, aide) traduits, avec les lettres du clavier de ce poste."""
    if reglage.ident != "touches_zqsd":
        return tr(reglage.libelle), tr(reglage.aide)
    t = dict(touches_preregle())
    deplacement = t["MoveUp"] + t["MoveLeft"] + t["MoveDown"] + t["MoveRight"]
    return (tr(reglage.libelle).format(deplacement),
            tr(reglage.aide).format(deplacement, t["Accio"], t["Extremos"], t["MoveDown"]))

def reglages_du_jeu(idents) -> tuple[Reglage, ...]:
    """Les réglages déclarés par le catalogue, connus de CE lanceur, dans l'ordre d'affichage."""
    voulus = set(idents or ())
    return tuple(r for r in REGLAGES.values() if r.ident in voulus)


def prereglages_du_jeu(reglages) -> tuple[tuple[str, str, str, dict], ...]:
    """Les préréglages réduits aux réglages que CE jeu déclare ; () s'il y en a trop peu.

    Moins de trois réglages en commun, un préréglage ne résumerait rien : le
    détail suffit.
    """
    presents = {r.ident for r in reglages}
    reduits = tuple((ident, nom, texte, {k: v for k, v in valeurs.items() if k in presents})
                    for ident, nom, texte, valeurs in PREREGLAGES)
    return reduits if len(reduits[0][3]) >= 3 else ()


def prereglage_courant(prereglages, valeurs: dict) -> str:
    """L'identifiant du préréglage que portent `valeurs` (identifiant → valeur), "" sinon."""
    for ident, _nom, _texte, voulues in prereglages:
        if all(k in valeurs and valeurs[k] == v for k, v in voulues.items()):
            return ident
    return ""


def chemin_ini(dossier_exe: Path) -> Path:
    return dossier_exe / NOM_INI


# ── Lecture et écriture de l'ini, en place ──

_SECTION = re.compile(r"^\s*\[([^\]]+)\]\s*$")


def _lire(chemin: Path) -> tuple[list[str], str]:
    """Lignes SANS fin de ligne, et la fin de ligne du fichier."""
    brut = chemin.read_bytes().decode("utf-8", errors="surrogateescape")
    fin = "\r\n" if "\r\n" in brut else "\n"
    return brut.split(fin), fin


def _ecrire(chemin: Path, lignes: list[str], fin: str) -> None:
    texte = fin.join(lignes)
    tmp = chemin.with_name(chemin.name + ".tmp")
    tmp.write_bytes(texte.encode("utf-8", errors="surrogateescape"))
    tmp.replace(chemin)


def _bornes(lignes: list[str], section: str) -> tuple[int, int] | None:
    """(première ligne après l'en-tête, ligne de la section suivante), ou None."""
    debut = None
    for i, ligne in enumerate(lignes):
        m = _SECTION.match(ligne)
        if not m:
            continue
        if debut is not None:
            return debut, i
        if m.group(1).strip().lower() == section.lower():
            debut = i + 1
    return (debut, len(lignes)) if debut is not None else None


def _motif_cle(cle: str, commentee: bool) -> re.Pattern:
    prefixe = r"\s*;\s*" if commentee else r"\s*"
    return re.compile(prefixe + re.escape(cle) + r"\s*=(.*)$", re.IGNORECASE)


def _valeur(lignes: list[str], section: str, cle: str) -> str | None:
    bornes = _bornes(lignes, section)
    if bornes is None:
        return None
    motif = _motif_cle(cle, commentee=False)
    for ligne in lignes[bornes[0]:bornes[1]]:
        m = motif.match(ligne)
        if m:
            # Le correctif lit ses valeurs avec les commentaires de fin de ligne
            # (« 100 // max fps » dans les anciens ini) : ne garder que la valeur.
            return re.split(r"\s*(?://|;)", m.group(1), maxsplit=1)[0].strip()
    return None


def _poser(lignes: list[str], section: str, cle: str, valeur: str | None) -> bool:
    """Pose `cle=valeur` (ou la commente si valeur est None). False si la section manque."""
    bornes = _bornes(lignes, section)
    if bornes is None:
        return False
    debut, fin = bornes
    active, commentee = _motif_cle(cle, False), _motif_cle(cle, True)
    for i in range(debut, fin):
        if active.match(lignes[i]) or commentee.match(lignes[i]):
            lignes[i] = f"{cle}={valeur}" if valeur is not None else f";{cle}={_ancienne(lignes[i])}"
            return True
    if valeur is None:
        return True   # rien à commenter
    # Clé absente : juste après la dernière ligne non vide de la section.
    j = fin
    while j > debut and not lignes[j - 1].strip():
        j -= 1
    lignes.insert(j, f"{cle}={valeur}")
    return True


def _ancienne(ligne: str) -> str:
    return ligne.split("=", 1)[1].strip() if "=" in ligne else ""


# ── Ce que voit l'interface ──

@dataclass(frozen=True)
class Etat:
    """Ce que porte l'ini pour un réglage.

    `valeur` : bool pour un interrupteur, int pour un réglage à choix.
    `personnalise` : l'ini porte une valeur que l'interface ne sait pas
    représenter (touches choisies à la main) — on l'affiche, on ne l'écrase pas.
    """
    valeur: object
    personnalise: bool = False


def est_nouveau_correctif(ini: Path) -> bool:
    try:
        lignes, _ = _lire(ini)
    except OSError:
        return False
    return _bornes(lignes, _MARQUE_V2) is not None


def lire(ini: Path, reglage: Reglage) -> Etat:
    lignes, _ = _lire(ini)
    if reglage.ident == "touches_zqsd":
        preregle = touches_preregle()
        actives = {cle: _valeur(lignes, reglage.section, cle) for cle, _ in preregle}
        if all(actives[cle] is not None and actives[cle].lower() == v.lower() for cle, v in preregle):
            return Etat(True)
        return Etat(False, personnalise=any(v is not None for v in actives.values()))
    if reglage.ident == "panneau_perfs":
        # Un mélange (quelques lignes à la main) se montre éteint et se signale.
        allumees = [_valeur(lignes, reglage.section, cle) not in (None, "0", "") for cle in _PANNEAU]
        return Etat(all(allumees), personnalise=any(allumees) and not all(allumees))
    if reglage.ident == "resolution":
        largeur, hauteur = (_valeur(lignes, reglage.section, cle) for cle in _RESOLUTION)
        if largeur is None and hauteur is None:
            return Etat(reglage.choix[0])
        v = f"{(largeur or '').strip()}x{(hauteur or '').strip()}"
        return Etat(v, personnalise=v not in reglage.choix)
    brut = _valeur(lignes, reglage.section, reglage.cle)
    if reglage.noms_choix:
        # Le correctif compare sans tenir compte de la casse.
        v = brut.lower() if brut else reglage.choix[0]
        return Etat(v, personnalise=v not in reglage.choix)
    if reglage.choix:
        # Un facteur peut être décimal (SSAAFactor=1.5) ; un entier reste un int.
        try:
            n = float(brut) if brut is not None else reglage.choix[0]
        except ValueError:
            return Etat(0, personnalise=True)
        if isinstance(n, float) and n.is_integer():
            n = int(n)
        return Etat(n, personnalise=n not in reglage.choix)
    # Interrupteur : le correctif lit 0 = non, tout autre nombre = oui.
    if brut is None:
        return Etat(reglage.defaut)
    return Etat(brut.strip() not in ("0", ""))


def touche_capture(ini: Path) -> str:
    """La touche de capture que lira le correctif, telle qu'on la montre (« F12 »), ou "".

    Lue dans l'ini plutôt que déclarée : seul le NOUVEAU correctif en a une, et
    un joueur a pu la changer (`ScreenshotKey`, code de touche Windows, 0 = aucune).
    """
    if not est_nouveau_correctif(ini):
        return ""
    try:
        lignes, _ = _lire(ini)
    except OSError:
        return ""
    brut = _valeur(lignes, _MARQUE_V2, "ScreenshotKey")
    try:
        code = int(brut) if brut is not None else 0x7B   # défaut du correctif : F12
    except ValueError:
        return ""
    if 0x70 <= code <= 0x87:
        return f"F{code - 0x6F}"
    if code == 0x2C:
        return tr("Impr. écran")
    if 0x30 <= code <= 0x5A:
        return chr(code)
    return ""


def poser_valeur(ini: Path, section: str, cle: str, valeur: str) -> bool:
    """Pose une clé que le LANCEUR tient à jour (pas un réglage de l'interface).

    N'écrit que si la valeur change : le fichier n'est pas réécrit à chaque
    lancement pour rien. Rend True s'il a été écrit. Lève OSError si le fichier
    ne peut pas l'être, ValueError si la section manque ou si la valeur ferait
    une seconde ligne.
    """
    if any(c in valeur for c in "\r\n\x00"):
        raise ValueError(f"{cle} : valeur sur plusieurs lignes")
    lignes, fin = _lire(ini)
    if _valeur(lignes, section, cle) == valeur:
        return False
    if not _poser(lignes, section, cle, valeur):
        raise ValueError(f"section [{section}] absente")
    _ecrire(ini, lignes, fin)
    return True


def chemin_origine(ini: Path) -> Path:
    return ini.with_name(ini.name + SUFFIXE_ORIGINE)


def _garder_origine(ini: Path) -> None:
    """Copie l'ini AVANT la première retouche d'un réglage, une fois pour toutes.

    Un échec n'empêche pas le réglage : il ne coûte que la remise à l'origine.
    """
    copie = chemin_origine(ini)
    if copie.exists():
        return
    try:
        shutil.copy2(ini, copie)
    except OSError:
        log.warning("Correctif : copie d'origine de %s impossible", ini, exc_info=True)


def _cles(reglage: Reglage) -> tuple[str, ...]:
    if reglage.ident == "touches_zqsd":
        # Toutes les actions, pas seulement celles du préréglage : l'éditeur de
        # touches (touches_correctif, qui importe ce module) règle aussi Pause,
        # Valider et Retour.
        from src.core.touches_correctif import ACTIONS
        return tuple(a.cle for a in ACTIONS)
    if reglage.ident == "panneau_perfs":
        return _PANNEAU
    if reglage.ident == "resolution":
        return _RESOLUTION
    return (reglage.cle,)


# Le plafond que le correctif tient DANS le jeu (HP4-HP6 : 120). Au-dessous de
# la limite choisie, c'est lui qui l'emporte : « 144 » donnait 120 images, même
# sans synchro (Ludo, 2026-10-01). Il suit donc la limite vers le HAUT ; jamais
# vers le bas (un plafond livré n'est pas une préférence qu'on retire).
_PLAFOND = ("Accio.Game", "FrameRateCap")


def _relever_plafond(lignes: list[str], limite) -> None:
    actuel = _valeur(lignes, *_PLAFOND)
    if actuel is None or not limite:
        return
    try:
        plafond = int(float(actuel))
    except ValueError:
        return
    if 0 < plafond < int(limite):
        _poser(lignes, *_PLAFOND, str(int(limite)))


def a_une_origine(ini: Path) -> bool:
    return chemin_origine(ini).is_file()


def remettre_origine(ini: Path, reglages) -> None:
    """Remet les clés de CES réglages telles que les portait l'ini d'origine.

    Seulement les clés que le lanceur règle : le reste du fichier (touches
    posées à la main, dossier des captures) ne bouge pas. Une clé absente de
    l'origine est commentée, donc rendue au défaut du correctif. Lève OSError
    si un des deux fichiers ne peut pas être lu ou écrit.
    """
    origine, _ = _lire(chemin_origine(ini))
    lignes, fin = _lire(ini)
    for reglage in reglages:
        for cle in _cles(reglage):
            _poser(lignes, reglage.section, cle, _valeur(origine, reglage.section, cle))
        if reglage.cle == "FPSLimit" and _valeur(lignes, *_PLAFOND) is not None:
            _poser(lignes, *_PLAFOND, _valeur(origine, *_PLAFOND))
    _ecrire(ini, lignes, fin)
    log.info("Correctif : réglages d'origine remis dans %s", ini)


def ecrire(ini: Path, reglage: Reglage, valeur) -> None:
    """Écrit un réglage. Lève OSError si le fichier ne peut pas être écrit,
    ValueError si la valeur n'est pas de celles que l'interface propose."""
    lignes, fin = _lire(ini)
    _garder_origine(ini)
    if reglage.ident == "touches_zqsd":
        for cle, touche in touches_preregle():
            if not _poser(lignes, reglage.section, cle, touche if valeur else None):
                raise ValueError(f"section [{reglage.section}] absente")
    elif reglage.ident == "panneau_perfs":
        for cle in _PANNEAU:
            if not _poser(lignes, reglage.section, cle, "1" if valeur else "0"):
                raise ValueError(f"section [{reglage.section}] absente")
    elif reglage.ident == "resolution":
        if valeur not in reglage.choix:
            raise ValueError(f"{reglage.ident} : {valeur!r} non proposé")
        for cle, nombre in zip(_RESOLUTION, valeur.split("x")):
            if not _poser(lignes, reglage.section, cle, nombre):
                raise ValueError(f"section [{reglage.section}] absente")
    elif reglage.choix:
        if valeur not in reglage.choix:
            raise ValueError(f"{reglage.ident} : {valeur!r} non proposé")
        texte = str(valeur) if reglage.noms_choix else _nombre(valeur)
        if not _poser(lignes, reglage.section, reglage.cle, texte):
            raise ValueError(f"section [{reglage.section}] absente")
        if reglage.cle == "FPSLimit":
            _relever_plafond(lignes, valeur)
    else:
        if not _poser(lignes, reglage.section, reglage.cle, "1" if valeur else "0"):
            raise ValueError(f"section [{reglage.section}] absente")
    _ecrire(ini, lignes, fin)
    log.info("Correctif : %s = %r dans %s", reglage.ident, valeur, ini)
