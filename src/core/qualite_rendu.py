"""Le rendu Direct3D 11 de HP1 et HP2 : chaque réglage d'image du rendu, et trois préréglages.

Constat du 2026-11-18 (un joueur sur PC portable) : HP1 et HP2 à 5 images/s en
plein écran, 15 en fenêtré, les autres jeux fluides, rien ne change en baissant
les options du jeu. Leur rendu D3D11 est installé au MAXIMUM dans
`[D3D11Drv.D3D11RenderDevice]` (MSAA 8, occlusion ambiante, réflexions, HDR,
parallaxe, éclairage volumétrique, distance illimitée), et le menu du jeu
n'atteint aucune de ces clés. La 1.3.6-beta.1 en a fait trois niveaux ; la page
Image (`ui/page_image`) règle depuis chaque clé utile, les niveaux devenus ses
préréglages (Légère, Équilibrée, Maximale).

Les choix vivent dans la config du launcher (`Config.rendu_d3d11`, id → {clé →
valeur}) et s'écrivent au LANCEMENT, jeu fermé, dans l'ini du joueur
(`pre_launch.ecrire_cles_ini` : sections et clés sans casse, toute autre ligne
intacte). Le moteur réécrit son ini en quittant, et l'installation le recopie
s'il manque : écrit dans la config, un choix survit aux deux. Une clé jamais
réglée n'est pas écrite : l'ini garde la sienne, et la page la montre.

Laissé hors du launcher (inventaire du 2026-11-19, `notes/HP1.md` de l'atelier) :
`Borderless`, `FastAltTab` (le catalogue les pose), `Precache`, `AutoFOV`,
`FullMeshLOD`, `HighDetailActors`, `DetailTextures` (sans coût sur une carte
récente, rien à gagner à les couper), `SupportMETextEnabled`, `OneXBlending`,
`DisableTextureFiltering` (changent le jeu sans l'alléger), `Tesselation` et
`TessDefaultFactor` (jamais vus), et les dosages des effets
(`ASSAOContrast`, `ASSAOScale`, `HDRLuminance`, `HDRAdaptationSpeed`, `HDRBloom`,
`HDRFilmicTonemapping`, `SSRFresnelAmount`, `SSRModelIntensity`,
`SSRNonTransparentWater`, `ParallaxRange`, `BumpMappingContrast`,
`ShinySurfaces`, `Coronas`) tant qu'un essai en jeu ne les a pas vus.
"""

from collections.abc import Callable, Iterable, Sequence

from src.core.catalogue_blocs import IniPatch
from src.core.config import Config
from src.core.game_data import GameData
from src.core.pre_launch import ecrire_cles_ini, lire_section
from src.core.reglages_correctif import Prereglage, Valeur, arrondir, meme_valeur, sur_le_curseur
from src.core.reglages_table import ECHANTILLONS_MSAA, FILTRAGES, Reglage

SECTION = "D3D11Drv.D3D11RenderDevice"

MAXIMALE = "maximale"
EQUILIBREE = "equilibree"
LEGERE = "legere"

# L'ordre est celui de l'affichage dans leur groupe (`reglages_image._PLACES`).
REGLAGES: dict[str, Reglage] = {r.ident: r for r in (
    Reglage("rendu_anticrenelage", SECTION, "Antialiasing",
            "Anticrénelage",
            "Lisse les contours des personnages et du décor en calculant plusieurs points par pixel. ×8 est "
            "installé ; ×4 se voit à peine moins et coûte nettement moins. Le réglage qui pèse le plus sur un "
            "PC portable.",
            choix=ECHANTILLONS_MSAA, zero="Éteint", format_choix="×{}", technique="MSAA",
            onglet="image", cout=(("GPU", 3),), se_voit=True),
    Reglage("rendu_feuillage", SECTION, "AlphaToCoverage",
            "Feuillage et grilles lissés",
            "Avec l'anticrénelage, lisse aussi le bord découpé des feuilles, des herbes et des grilles, en "
            "escalier sans lui.",
            onglet="image", cout=(("GPU", 1),), depend_de="rendu_anticrenelage"),
    Reglage("rendu_filtrage", SECTION, "Anisotropy",
            "Netteté des sols et des murs",
            "Sols, murs et chemins vus en biais restent nets au lieu de devenir flous. Presque gratuit sur une "
            "carte récente.",
            choix=FILTRAGES, zero="Éteint", format_choix="×{}", technique="filtrage anisotrope",
            onglet="image", cout=(("GPU", 1),), se_voit=True),
    Reglage("rendu_textures_lointaines", SECTION, "LODBias",
            "Textures lointaines",
            "Garde les textures nettes plus loin : dalles, pavés et boiseries restent détaillés au lieu de "
            "flouter avec la distance. Peut faire scintiller certaines surfaces.",
            choix=(0, -1), zero="D'origine", etiquettes=((-1, "Plus nettes"),),
            onglet="image", cout=(("GPU", 1),), beta=True),
    Reglage("rendu_relief", SECTION, "BumpMapping",
            "Relief des surfaces",
            "Pierres, briques et boiseries accrochent la lumière comme si elles avaient du relief. Éteint : "
            "des murs plats, comme dans le jeu d'origine.",
            onglet="image", cout=(("GPU", 1),), se_voit=True),
    Reglage("rendu_parallaxe", SECTION, "ParallaxOcclusionMapping",
            "Relief profond",
            "Creuse vraiment les joints des pierres et des pavés, qui gardent leur profondeur quand la caméra "
            "tourne.",
            technique="parallax occlusion mapping", onglet="image", cout=(("GPU", 2),), se_voit=True),
    Reglage("rendu_occlusion", SECTION, "ASSAO",
            "Ombres de contact",
            "Assombrit les recoins, le pied des murs et le contact des objets : le décor gagne en relief.",
            technique="occlusion ambiante", onglet="image", cout=(("GPU", 2),), se_voit=True),
    Reglage("rendu_hdr", SECTION, "HDR",
            "Lumière à haute dynamique",
            "Les lumières vives éclairent et débordent comme à l'œil : torches, fenêtres et sorts brillent, "
            "l'ombre garde ses détails. Éteint : une lumière plus plate.",
            technique="HDR", onglet="image", cout=(("GPU", 1),), se_voit=True),
    Reglage("rendu_volumetrique", SECTION, "VolumetricLighting",
            "Brume lumineuse",
            "La lumière des lampes et des fenêtres se voit dans l'air, comme dans une pièce poussiéreuse.",
            technique="éclairage volumétrique", onglet="image", cout=(("GPU", 2),)),
    Reglage("rendu_reflets", SECTION, "SSR",
            "Reflets sur les sols",
            "Dalles, parquets et eau reflètent le décor et les personnages. Les herbes, la terre et les tapis "
            "ne reflètent rien.",
            technique="SSR", onglet="image", cout=(("GPU", 2),), se_voit=True),
    Reglage("rendu_reflets_force", SECTION, "SSRIntensity",
            "Force des reflets",
            "La part du reflet sur les sols : « Discrets » laisse surtout voir la pierre, « Forts » fait des "
            "sols presque miroirs.",
            choix=(0.2, 0.35, 0.5), zero="Discrets", etiquettes=((0.35, "Moyens"), (0.5, "Forts")),
            chiffre=True, onglet="image", depend_de="rendu_reflets"),
    Reglage("rendu_distance", SECTION, "UnlimitedViewDistance",
            "Décor lointain entier",
            "Dessine le décor jusqu'au bout de la vue, au lieu de le couper dans le brouillard à distance "
            "normale.",
            onglet="image", cout=(("GPU", 2),), se_voit=True),
    # Plafonnée à 100, la valeur installée : au-delà, rien n'a été vu en jeu.
    Reglage("rendu_limite", SECTION, "FPSLimit",
            "Limite d'images par seconde",
            "Plafonne le nombre d'images calculées : l'ordinateur chauffe moins et fait moins de bruit. 60 "
            "suffit sur un écran à 60 Hz.",
            choix=(100, 60, 30), zero="100", onglet="perfs"),
    Reglage("rendu_vsync", SECTION, "VSync",
            "Synchronisation verticale",
            "Cale les images sur la fréquence de l'écran : plus de déchirure horizontale quand la caméra "
            "tourne, contre un peu plus de délai entre la souris et l'image.",
            onglet="perfs"),
)}

# Ce que livre l'installation (HP.ini de HP1, Game.ini de HP2, les mêmes valeurs) : la valeur Accio.
ACCIO: dict[str, Valeur] = {
    "rendu_anticrenelage": 8, "rendu_feuillage": True, "rendu_filtrage": 16, "rendu_textures_lointaines": 0,
    "rendu_relief": True, "rendu_parallaxe": True, "rendu_occlusion": True, "rendu_hdr": True,
    "rendu_volumetrique": True, "rendu_reflets": True, "rendu_reflets_force": 0.35, "rendu_distance": True,
    "rendu_limite": 100, "rendu_vsync": True,
}

# Le jeu de 2001-2002 et son rendu d'alors n'avaient aucun de ces effets ; le filtrage, l'éclairage
# volumétrique, la limite et la synchronisation y dépendaient de la carte : pas de valeur connue.
DU_JEU: dict[str, Valeur] = {
    "rendu_anticrenelage": 0, "rendu_feuillage": False, "rendu_textures_lointaines": 0, "rendu_relief": False,
    "rendu_parallaxe": False, "rendu_occlusion": False, "rendu_hdr": False, "rendu_reflets": False,
    "rendu_distance": False,
}

# Les trois niveaux de la 1.3.6-beta.1, devenus les préréglages de la page Image. Maximale = l'installation.
PREREGLAGES: tuple[Prereglage, ...] = (
    (LEGERE, "Légère",
     "Pour un PC portable ou un jeu qui saccade : contours, reflets et effets de lumière éteints.",
     {"rendu_anticrenelage": 0, "rendu_occlusion": False, "rendu_reflets": False, "rendu_hdr": False,
      "rendu_parallaxe": False, "rendu_volumetrique": False, "rendu_distance": False}),
    (EQUILIBREE, "Équilibrée",
     "Contours lissés, ombres et lumière gardées, sans reflets ni relief profond.",
     {"rendu_anticrenelage": 4, "rendu_occlusion": True, "rendu_reflets": False, "rendu_hdr": True,
      "rendu_parallaxe": False, "rendu_volumetrique": True, "rendu_distance": False}),
    (MAXIMALE, "Maximale",
     "Tous les effets, tels qu'installés, pour une carte graphique récente.",
     {"rendu_anticrenelage": 8, "rendu_occlusion": True, "rendu_reflets": True, "rendu_hdr": True,
      "rendu_parallaxe": True, "rendu_volumetrique": True, "rendu_distance": True}),
)


def _patch_d3d11(game: GameData) -> IniPatch | None:
    """Le patch du catalogue qui règle le rendu D3D11 du jeu : il dit QUEL fichier
    porte la section. Aucun : le jeu ne rend pas par D3D11Drv (HP3 à HP8)."""
    if game.pre_launch is None:
        return None
    return next((p for p in game.pre_launch.ini_patches
                 if p.section.casefold() == SECTION.casefold()), None)


def gere(game: GameData) -> bool:
    return _patch_d3d11(game) is not None


def texte(reglage: Reglage, valeur: object) -> str:
    """La valeur telle que le moteur l'écrit : True/False, un entier, un réel à six décimales."""
    if not reglage.choix:
        return "True" if valeur else "False"
    if isinstance(valeur, (int, float)) and float(valeur).is_integer():
        return str(int(valeur))
    return f"{float(str(valeur)):.6f}"


def valeur(reglage: Reglage, brut: str) -> Valeur | None:
    """La valeur d'un texte de l'ini ; None s'il ne se lit pas."""
    if not reglage.choix:
        return brut.strip().casefold() in ("true", "1")
    try:
        n = float(brut)
    except ValueError:
        return None
    return int(n) if n.is_integer() else n


def _surcharges(game: GameData, config: Config) -> dict[str, str]:
    """Les clés réglées dans le launcher pour ce jeu. Un niveau de la 1.3.6-beta.1 devient ses clés."""
    ancien = config.qualite_rendu.pop(game.id, None)
    niveau = next((v for i, _n, _t, v in PREREGLAGES if i == ancien), None)
    if niveau is not None and game.id not in config.rendu_d3d11:
        config.rendu_d3d11[game.id] = {REGLAGES[i].cle: texte(REGLAGES[i], v) for i, v in niveau.items()}
    return config.rendu_d3d11.get(game.id, {})


def appliquer(game: GameData, config: Config) -> bool:
    """Écrit dans l'ini du jeu les clés réglées dans le launcher. True si quelque chose a été écrit."""
    patch = _patch_d3d11(game)
    cles = _surcharges(game, config) if patch is not None else {}
    if patch is None or not cles:
        return False
    return ecrire_cles_ini(patch.file, SECTION, cles, game, config)


def _proposee(reglage: Reglage, v: object) -> object:
    """La valeur telle qu'elle s'écrit (un cran du curseur arrondi) ; ValueError si la page ne la propose pas."""
    if reglage.choix and v not in reglage.choix:
        if not sur_le_curseur(reglage, v):
            raise ValueError(f"{reglage.ident} : {v!r} non proposé")
        return arrondir(reglage, float(str(v)))
    return v


class MagasinRendu:
    """Où la page Image lit et écrit ces réglages (`reglages_image.Magasin`) : la config du launcher,
    sinon ce que porte l'ini du jeu (lu UNE fois, à l'ouverture), sinon l'installation."""

    def __init__(self, game: GameData, config: Config, enregistrer: Callable[[], None]) -> None:
        self.game, self.config, self._enregistrer = game, config, enregistrer
        patch = _patch_d3d11(game)
        self._ini = (lire_section(patch.file, SECTION, game, config) if patch is not None else None) or {}

    def lire(self, reglage: Reglage) -> object:
        brut = _surcharges(self.game, self.config).get(reglage.cle)
        if brut is None:
            brut = self._ini.get(reglage.cle.casefold())
        lue = valeur(reglage, brut) if brut is not None else None
        return ACCIO.get(reglage.ident) if lue is None else lue

    def lire_tout(self, reglages: Iterable[Reglage]) -> dict[str, object]:
        return {r.ident: self.lire(r) for r in reglages}

    def ecrire(self, reglage: Reglage, v: object) -> None:
        """ValueError pour une valeur que la page ne propose pas ; OSError si la config ne s'écrit pas."""
        self.ecrire_tout([(reglage, v)])

    def ecrire_tout(self, valeurs: Sequence[tuple[Reglage, object]]) -> dict[str, object]:
        """Tout d'un coup, la config enregistrée UNE fois : un préréglage l'enregistrait sept fois
        (banc du 2026-11-19). Une valeur non proposée : rien ne change."""
        textes = [(r, texte(r, _proposee(r, v))) for r, v in valeurs]
        _surcharges(self.game, self.config)
        posees = self.config.rendu_d3d11.setdefault(self.game.id, {})
        for r, t in textes:
            posees[r.cle] = t
        self._enregistrer()
        return {r.ident: self.lire(r) for r, _t in textes}

    def accio(self, reglage: Reglage) -> object:
        return ACCIO.get(reglage.ident)

    def jeu(self, reglage: Reglage) -> object:
        return DU_JEU.get(reglage.ident)

    def a_change(self) -> bool:
        return any(not meme_valeur(self.lire(r), ACCIO[r.ident]) for r in REGLAGES.values())

    def remettre(self) -> None:
        """Les valeurs de l'installation, écrites au prochain lancement (une clé oubliée garderait celle de
        l'ini, peut-être réglée plus bas)."""
        _surcharges(self.game, self.config)
        self.config.rendu_d3d11[self.game.id] = {r.cle: texte(r, ACCIO[r.ident]) for r in REGLAGES.values()}
        self._enregistrer()
