"""Blocs du catalogue et leurs barrières.

Tout ce que `games.json` déclare à côté d'une version de jeu (langues,
manette, sauvegardes, captures, bandes-annonces, contributeurs) et les
validateurs qui le séparent de la machine : le catalogue est DISTANT.
`game_data` les réexporte ; sorti de `game_data` le 2026-10-03 (1 172 lignes).
"""
import logging
import re
from dataclasses import dataclass

from src.core import game_registry as registre
from src.core.i18n import SOURCE_LANGUAGE, get_language

log = logging.getLogger(__name__)


# Noms de périphériques réservés par Windows : ouvrir « CON » ouvre la console,
# pas un fichier — quel que soit le dossier et quelle que soit l'extension.
_PERIPHERIQUES = frozenset(
    ["con", "prn", "aux", "nul"]
    + ["com%d" % i for i in range(1, 10)]
    + ["lpt%d" % i for i in range(1, 10)]
)


def _tags_valides(tags) -> tuple:
    """Tags du catalogue, réduits à une liste de chaînes (un dict affichait
    ses CLÉS en pastilles : mieux vaut pas de tag qu'un tag inventé)."""
    if not isinstance(tags, (list, tuple)):
        return ()
    return tuple(t for t in tags if isinstance(t, str))


def _est_peripherique(nom: str) -> bool:
    """True si `nom` est un nom de périphérique Windows réservé."""
    return nom.split(".")[0].strip().lower() in _PERIPHERIQUES


def _https_ou_rien(url):
    """Écarte au PARSING toute URL de téléchargement non-https.

    Le téléchargeur refuse déjà tout sauf https ; ceci avance le MOMENT du
    refus : une coquille `http` donne « bientôt disponible » au lieu d'une
    erreur technique au clic. Chaîne ou liste de parts ; None si écarté.
    """
    if isinstance(url, str):
        return url if url.startswith("https://") else None
    if isinstance(url, (list, tuple)):
        gardees = [u for u in url if isinstance(u, str) and u.startswith("https://")]
        # Tout ou rien : une liste de parts trouée décalerait les empreintes.
        return list(url) if len(gardees) == len(url) and gardees else None
    return None


def _sha256_valide(value) -> str | None:
    """Empreinte hexadécimale de 64 caractères, ou None (une coquille du
    catalogue faisait planter le comparateur sur `.lower()`)."""
    if not isinstance(value, str):
        return None
    hexa = value.strip().lower()
    if len(hexa) == 64 and all(c in "0123456789abcdef" for c in hexa):
        return hexa
    if value:
        log.warning("Empreinte SHA-256 mal formée dans le catalogue, ignorée : %r", value)
    return None


def _taille_mo(value) -> int:
    """Taille annoncée en Mo, jamais négative : négative, elle passait la
    vérification d'espace et DÉSACTIVAIT le plafond du téléchargeur."""
    try:
        taille = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, taille)


def _loc(data: dict, key: str, default):
    """Valeur du champ `key` dans la langue active, sinon en français.

    Traductions DANS le catalogue (bloc `i18n`, règle 55) : un jeu ajouté
    arrive traduit sans republier l'exe. Résolu au parsing (`set_language()`
    tourne avant `load_catalog()`). Repli par CHAMP.
    """
    lang = get_language()
    if lang != SOURCE_LANGUAGE:
        block = data.get("i18n")
        if isinstance(block, dict):
            translated = block.get(lang)
            if isinstance(translated, dict) and key in translated:
                value = translated[key]
                # Un bloc i18n trafiqué ne doit pas changer le TYPE du champ…
                if isinstance(value, type(default)):
                    # …ni le VIDER (fiche sans titre) : vide = absent → français.
                    if isinstance(value, str) and not value.strip():
                        log.warning("Traduction vide (%s/%s) — repli sur le français", lang, key)
                    else:
                        return value
    return data.get(key, default)


@dataclass(frozen=True, slots=True)
class ConfigFile:
    """Fichier de configuration à copier après installation."""
    source: str       # relatif au dossier du jeu (ex: "config/hppoa.ini")
    destination: str   # chemin avec ~ (ex: "~/Documents/MonJeu/hppoa.ini")

    @classmethod
    def from_dict(cls, data: dict) -> "ConfigFile":
        return cls(source=data["source"], destination=data["destination"])


@dataclass(frozen=True, slots=True)
class IniPatch:
    """Patch INI à appliquer avant le lancement du jeu."""
    file: str       # chemin avec %DOCUMENTS% comme variable
    section: str    # ex: "FirstRun"
    key: str        # ex: "Reconfig"
    value: str      # ex: "0"
    fallback: str | None = None  # valeur de repli si la valeur principale échoue

    @classmethod
    def from_dict(cls, data: dict) -> "IniPatch":
        return cls(file=data["file"], section=data["section"],
                   key=data["key"], value=data["value"],
                   fallback=data.get("fallback"))


@dataclass(frozen=True, slots=True)
class GameLanguage:
    """Une langue proposée par un jeu, et ce qu'elle écrit dans le registre."""
    code: str                                  # « fr », « en »… (code i18n)
    label: str                                 # écrit DANS sa propre langue
    values: tuple[tuple[str, str | int], ...]  # (nom, valeur) — frozen ⇒ tuple
    # Fichier dont la PRÉSENCE prouve la langue installée (le registre ne fait
    # que sélectionner, règle 73). Relatif au dossier ; vide = toujours proposée.
    requires_file: str = ""

    @property
    def as_dict(self) -> dict:
        return dict(self.values)


@dataclass(frozen=True, slots=True)
class LanguageRegistry:
    """Où un jeu lit sa langue, et ce qu'il faut y écrire pour chacune.

    Au catalogue : valeurs propres à chaque jeu (« French », « fr_FR »,
    DWORD…), corrigeables sans republier l'exe.
    """
    root: str
    key: str
    view: int
    languages: tuple[GameLanguage, ...]
    # Posées AVEC toute langue, même clé, donc une seule invite UAC : HP7 ne
    # démarre pas sans « Install Dir » (écrit d'ordinaire par l'installeur EA).
    # `%INSTALL_DIR%` substitué à l'écriture.
    common: tuple[tuple[str, str | int], ...] = ()

    def get(self, code: str) -> GameLanguage | None:
        return next((lg for lg in self.languages if lg.code == code), None)

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(lg.code for lg in self.languages)


@dataclass(frozen=True, slots=True)
class ManetteRegistre:
    """Où un jeu range « jouer à la manette », et les deux valeurs qui le disent.

    HP5/HP6 ne lisent la manette que choisie dans leur menu, choix rangé sous
    `HKCU\\Software\\Electronic Arts\\<jeu>\\ControllerConfig`,
    `CurrentSelection` : 0 = désactivée, 4 = manette. Au catalogue, comme la langue.
    """
    root: str
    key: str
    view: int
    value: str
    on: int
    off: int


@dataclass(frozen=True, slots=True)
class LangueFichiers:
    """Une langue d'un jeu qui la lit dans ses FICHIERS, pas dans le registre.

    HP1 : `Language=fre|int` dans `HP.ini` ET `System\\Default.ini` (qui
    décide avec `Running.ini`), plus `Help\\splash<langue>.bmp`, sans lequel
    « Assertion failed: Bitmap.LoadFile ».
    """
    code: str
    label: str
    ini: tuple[IniPatch, ...]
    # (source, destination) relatifs au dossier d'installation, comme
    # `requires_file` ; copiés seulement si la destination MANQUE.
    copies: tuple[tuple[str, str], ...] = ()
    requires_file: str = ""


@dataclass(frozen=True, slots=True)
class LanguageFiles:
    """Pendant de `LanguageRegistry` pour les jeux qui lisent leur langue dans
    des fichiers : même surface (`languages`, `get`, `codes`), donc le
    sélecteur et la fiche n'ont pas à savoir d'où vient la langue. Pas de
    registre : ni élévation, ni invite UAC, et ça marche tel quel sous Wine."""
    languages: tuple[LangueFichiers, ...]

    def get(self, code: str) -> LangueFichiers | None:
        return next((lg for lg in self.languages if lg.code == code), None)

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(lg.code for lg in self.languages)


# Un caractère de contrôle ajouterait des lignes à l'ini du jeu ; crochets et
# « = » dans section/clé en changeraient la structure.
_INI_INTERDIT_NOM = re.compile(r"[\x00-\x1f\x7f\[\]=]")
_INI_INTERDIT_VALEUR = re.compile(r"[\x00-\x1f\x7f]")


def _parse_language_files(data) -> "LanguageFiles | None":
    """Lit le bloc `language_files`, ou None s'il est absent ou douteux.

    Tout ou rien, comme `language_registry` : une langue à moitié posée donne
    un jeu à moitié traduit — ou qui ne démarre pas (le splash de HP1).
    """
    if not isinstance(data, dict):
        return None
    brut = data.get("languages")
    if not isinstance(brut, dict) or not brut:
        return None
    langues: list[LangueFichiers] = []
    for code, entree in brut.items():
        if not isinstance(code, str) or not _JETON_SUR.match(code) or not isinstance(entree, dict):
            return None
        patches = entree.get("ini")
        if not isinstance(patches, list) or not patches:
            return None
        ini: list[IniPatch] = []
        for p in patches:
            if not isinstance(p, dict):
                return None
            champs = [p.get(k) for k in ("file", "section", "key", "value")]
            if not all(isinstance(c, str) and c for c in champs):
                return None
            fichier, section, cle, valeur = champs
            if not fichier.startswith(("%DOCUMENTS%", "%INSTALL_DIR%")) \
                    or ".." in fichier.replace("\\", "/").split("/") \
                    or _INI_INTERDIT_VALEUR.search(fichier) \
                    or _INI_INTERDIT_NOM.search(section) or _INI_INTERDIT_NOM.search(cle) \
                    or _INI_INTERDIT_VALEUR.search(valeur):
                log.warning("Bloc language_files ignoré (patch INI douteux) : %r", p)
                return None
            ini.append(IniPatch(file=fichier, section=section, key=cle, value=valeur))
        copies: list[tuple[str, str]] = []
        brut_copies = entree.get("copy", [])
        if not isinstance(brut_copies, list):
            return None
        for c in brut_copies:
            if not isinstance(c, dict):
                return None
            src, dst = c.get("from"), c.get("to")
            if not (isinstance(src, str) and isinstance(dst, str)
                    and _est_relatif_sur(src) and _est_relatif_sur(dst)):
                log.warning("Bloc language_files ignoré (copie douteuse) : %r", c)
                return None
            copies.append((src, dst))
        temoin = entree.get("requires_file", "")
        if not isinstance(temoin, str) or (temoin and not _est_relatif_sur(temoin)):
            return None
        label = entree.get("label")
        if not isinstance(label, str) or not label.strip():
            label = code
        langues.append(LangueFichiers(code=code, label=label, ini=tuple(ini),
                                      copies=tuple(copies), requires_file=temoin))
    return LanguageFiles(languages=tuple(langues))


def _est_relatif_sur(chemin: str) -> bool:
    r"""True si ce chemin de catalogue peut être joint au dossier d'un jeu.

    Mêmes refus que pour `executable` : pas de remontée, pas de racine, pas de
    lettre de lecteur, pas d'octet nul. Normaliser AVANT de vérifier — sous
    POSIX « \ » n'est pas un séparateur, et le garde-fou serait inopérant.
    """
    if not chemin or "\x00" in chemin or len(chemin) > 260:
        return False
    norm = chemin.replace("\\", "/")
    if norm.startswith("/") or (len(norm) >= 2 and norm[1] == ":"):
        return False
    return ".." not in norm.split("/")


def _parse_manette_registre(data) -> "ManetteRegistre | None":
    """Lit le bloc `controller_registry`, ou None s'il est absent ou douteux.

    Mêmes barrières que `language_registry` (clé et valeur passent par
    `refus_de_cle` / `refus_de_valeur`), plus : deux entiers distincts. Les
    booléens sont refusés explicitement — `True` EST un `int`.
    """
    if not isinstance(data, dict):
        return None
    root = data.get("root", "HKCU")
    cle = data.get("key", "")
    try:
        view = int(data.get("view", 32))
    except (TypeError, ValueError):
        return None
    if view not in (32, 64):
        return None
    raison = registre.refus_de_cle(root, cle)
    if raison is not None:
        log.warning("Bloc controller_registry ignoré (%s) : %r", raison, cle)
        return None
    nom, on, off = data.get("value"), data.get("on"), data.get("off")
    if any(isinstance(v, bool) or not isinstance(v, int) for v in (on, off)) or on == off:
        return None
    for v in (on, off):
        raison = registre.refus_de_valeur(nom, v)
        if raison is not None:
            log.warning("Bloc controller_registry ignoré (%s) : %r", raison, nom)
            return None
    return ManetteRegistre(root=root, key=cle, view=view, value=nom, on=on, off=off)


def _parse_language_registry(data) -> "LanguageRegistry | None":
    """Lit le bloc `language_registry`, ou None s'il est absent ou douteux.

    TOUT ou RIEN : jamais la moitié des valeurs dans le registre de quelqu'un.
    """
    if not isinstance(data, dict):
        return None
    root = data.get("root", "HKCU")
    cle = data.get("key", "")
    try:
        view = int(data.get("view", 32))
    except (TypeError, ValueError):
        return None
    if view not in (32, 64):
        return None
    raison = registre.refus_de_cle(root, cle)
    if raison is not None:
        log.warning("Bloc language_registry ignoré (%s) : %r", raison, cle)
        return None

    brut = data.get("languages")
    if not isinstance(brut, dict) or not brut:
        return None
    langues: list[GameLanguage] = []
    for code, entree in brut.items():
        if not isinstance(code, str) or not isinstance(entree, dict):
            return None
        valeurs = entree.get("values")
        if not isinstance(valeurs, dict) or not valeurs:
            return None
        paires: list[tuple[str, str | int]] = []
        for nom, valeur in valeurs.items():
            raison = registre.refus_de_valeur(nom, valeur)
            if raison is not None:
                log.warning("Valeur de langue refusée (%s) : %r", raison, nom)
                return None
            paires.append((nom, valeur))
        label = entree.get("label")
        if not isinstance(label, str) or not label.strip():
            label = code
        fichier = entree.get("requires_file", "")
        if not isinstance(fichier, str):
            return None
        # Même validation que `executable`.
        if fichier and not _est_relatif_sur(fichier):
            log.warning("requires_file non sûr, bloc de langue ignoré : %r", fichier)
            return None
        langues.append(GameLanguage(code=code, label=label, values=tuple(paires),
                                    requires_file=fichier))

    # Valeurs communes, tout ou rien. Contrôle du GABARIT ici ; le vrai
    # garde-fou est `ecrire_valeurs`, qui revalide après substitution.
    communes: list[tuple[str, str | int]] = []
    brut_communes = data.get("values", {})
    if not isinstance(brut_communes, dict):
        return None
    for nom, valeur in brut_communes.items():
        raison = registre.refus_de_valeur(nom, valeur)
        if raison is not None:
            log.warning("Valeur commune refusée (%s) : %r", raison, nom)
            return None
        communes.append((nom, valeur))

    return LanguageRegistry(root=root, key=cle, view=view, languages=tuple(langues),
                            common=tuple(communes))


@dataclass(frozen=True, slots=True)
class Resolution:
    """Où le jeu lit la taille de sa fenêtre : deux clés d'un `.ini`.

    HP1 et HP2 (UE1, 2026-10-03) : `[WinDrv.WindowsClient] WindowedViewportX/Y`,
    VU en jeu le 2026-10-01 — le moteur ouvre sa fenêtre sans bordure à cette
    taille. Le launcher y écrit celle de l'écran à chaque lancement, ou celle que
    la personne a choisie (`resolution_jeu`).
    """
    file: str       # chemin avec %DOCUMENTS% / %INSTALL_DIR%, un `.ini`
    section: str
    width: str      # clé de la largeur
    height: str     # clé de la hauteur


def _parse_resolution(data) -> "Resolution | None":
    """Lit le bloc `resolution`, ou None s'il est absent ou douteux.

    Mêmes barrières que les patchs de `language_files` : rien qui puisse
    ajouter une ligne ou une section à l'ini. Le chemin, lui, est encore
    contrôlé à l'écriture (`resolve_safe_path` : un `.ini`, dans Documents ou
    le dossier des jeux).
    """
    if not isinstance(data, dict):
        return None
    champs = [data.get(k) for k in ("file", "section", "width", "height")]
    if not all(isinstance(c, str) and c.strip() for c in champs):
        return None
    fichier, section, largeur, hauteur = champs
    if _INI_INTERDIT_VALEUR.search(fichier) or largeur == hauteur or any(
            _INI_INTERDIT_NOM.search(c) for c in (section, largeur, hauteur)):
        log.warning("Bloc resolution ignoré (douteux) : %r", data)
        return None
    return Resolution(file=fichier, section=section, width=largeur, height=hauteur)


@dataclass(frozen=True, slots=True)
class PreLaunch:
    """Données de pré-lancement d'un jeu."""
    ini_patches: tuple[IniPatch, ...] = ()
    delete_files: tuple[str, ...] = ()
    create_files: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PostInstall:
    """Données de post-installation d'un jeu."""
    config_files: tuple[ConfigFile, ...] = ()
    # Sous-dossier dans lequel ranger le jeu après extraction (« pc » pour HP7).
    # Vide = on ne range rien, ce qui est le cas des sept autres jeux.
    sous_dossier: str = ""


def _annee_valide(brut) -> int:
    """Année de scolarité déclarée par le catalogue : 1 à 7, sinon 0 (« hors
    programme », légitime). Booléens refusés : `True` vaudrait « 1ʳᵉ année »."""
    if isinstance(brut, bool) or not isinstance(brut, int):
        return 0
    return brut if 1 <= brut <= 7 else 0


def _ips_max_valide(brut) -> int:
    """Plafond d'images/s déclaré par le catalogue : 1 à 1000, sinon 0 (aucun).

    Booléens refusés comme pour `annee` : `true` vaudrait « 1 image/s ».
    """
    if isinstance(brut, bool) or not isinstance(brut, int):
        return 0
    return brut if 1 <= brut <= 1000 else 0


def _url_aide_valide(brut) -> str:
    """URL d'aide du catalogue, ou chaîne vide si elle n'est pas acceptable.

    HTTPS seul, jamais d'exception : cette chaîne finit dans `openUrl`. Mal
    formée, on perd le lien, pas l'avertissement.
    """
    if not isinstance(brut, str):
        return ""
    url = brut.strip()
    if not url.lower().startswith("https://") or len(url) <= len("https://"):
        if url:
            log.warning("URL d'aide refusée (https attendu) : %r", url)
        return ""
    # « httPs:// » EST du https : rendu sous forme canonique (écart trouvé
    # par le fuzzing avec le contrôle des téléchargements).
    return "https://" + url[len("https://"):]


def _sous_dossier_valide(brut) -> str:
    """Nom du sous-dossier de rangement, ou chaîne vide s'il n'est pas sûr.

    On y DÉPLACE tout un jeu : un seul composant, jamais un chemin
    (`_JETON_SUR` refuse `..`, `/`, `\\` et `:`).
    """
    if not isinstance(brut, str) or not brut:
        return ""
    nom = brut.strip()
    if not _JETON_SUR.match(nom) or nom in (".", ".."):
        log.warning("Sous-dossier de rangement refusé : %r", brut)
        return ""
    return nom


# Au-delà, un bloc `dll_overrides` n'a rien d'un relevé : les jeux du catalogue
# en déclarent un à quatre (docs/LINUX.md, § 3).
_MAX_SURCHARGES_DLL = 16


def _surcharges_dll_valides(brut) -> tuple[str, ...]:
    """DLL livrées avec le jeu que Wine doit charger AVANT les siennes.

    Finissent dans `WINEDLLOVERRIDES`, où `=`, `,` et `;` réécriraient le
    réglage d'une autre DLL : `_JETON_SUR` les refuse. `.dll` retiré,
    doublons fusionnés. Tout ou rien : sinon les DLL de Wine.
    """
    if brut is None:
        return ()
    if not isinstance(brut, list) or len(brut) > _MAX_SURCHARGES_DLL:
        log.warning("Bloc dll_overrides ignoré : %r", brut)
        return ()
    noms: list[str] = []
    for nom in brut:
        if not isinstance(nom, str):
            log.warning("Bloc dll_overrides ignoré (entrée %r)", nom)
            return ()
        propre = nom.strip()
        if propre.lower().endswith(".dll"):
            propre = propre[:-4]
        if not _JETON_SUR.match(propre) or len(propre) > 64:
            log.warning("Bloc dll_overrides ignoré (nom %r)", nom)
            return ()
        if propre.lower() not in noms:
            noms.append(propre.lower())
    return tuple(noms)


# Où un jeu range ses sauvegardes. Les racines sont une LISTE FERMÉE : le
# catalogue distant choisit parmi elles, il n'écrit jamais un chemin absolu.
RACINES_SAUVEGARDES = ("documents", "localappdata")


@dataclass(frozen=True, slots=True)
class Sauvegardes:
    """Emplacement des sauvegardes d'un jeu, tel que le déclare le catalogue.

    Au catalogue : le nom du dossier dépend de la LANGUE d'installation
    (« …prisonnier d'Azkaban », « …Reliques de la Mort (TM) – Première Partie »).

    `dossiers` : motifs glob relatifs à la racine (le premier qui existe) ;
    `fichiers` : motif relatif au dossier, un niveau au plus (« Slot*/Save0.usa »
    pour HP2) ; `exclure` : noms écartés (miroirs `Save100.usa` de HP3) ;
    `premier` : numéro du premier emplacement (0 « Save0.usa », 1 « Slot1 »).
    """

    racine: str
    dossiers: tuple[str, ...]
    fichiers: str
    exclure: tuple[str, ...] = ()
    premier: int = 0
    # Les emplacements rangés DANS un seul fichier (« slots » au catalogue) :
    # HP4 garde ses trois parties dans `HPGOF`. Vide : un fichier = une sauvegarde.
    emplacements: str = ""


# Formats d'emplacements que ce launcher sait lire (`sauvegardes._EMPLACEMENTS`).
# Un format inconnu est ignoré, pas le bloc : un launcher plus ancien que son
# catalogue voit alors le fichier comme une seule sauvegarde, ce qui reste vrai.
FORMATS_EMPLACEMENTS = ("hp4",)


def _motif_sur(motif) -> bool:
    """Un motif de catalogue ne sert qu'à LIRE des dates de fichier, mais il
    compose un chemin sur le disque de l'utilisateur : mêmes refus que
    `executable`, plus le « : » (flux NTFS, lettre de lecteur) et « ** » (un
    motif récursif parcourrait tout Documents à chaque partie)."""
    return (isinstance(motif, str) and _est_relatif_sur(motif)
            and ":" not in motif and "**" not in motif)


def _tous_les_noms(data: dict) -> tuple[str, ...]:
    """Le nom du jeu dans chaque langue du catalogue, français d'abord, sans doublon."""
    noms = [data.get("name")]
    bloc = data.get("i18n")
    if isinstance(bloc, dict):
        noms += [t.get("name") for t in bloc.values() if isinstance(t, dict)]
    vus: list[str] = []
    for nom in noms:
        if isinstance(nom, str) and nom.strip() and nom.strip() not in vus:
            vus.append(nom.strip())
    return tuple(vus)


def _touche_capture(data) -> str:
    """Nom de touche affiché tel quel (« F12 », « Impr. écran ») : court, sur une ligne."""
    touche = data.get("key") if isinstance(data, dict) else None
    if not isinstance(touche, str) or not 0 < len(touche.strip()) <= 24 \
            or any(ord(c) < 32 or c in "<>&" for c in touche):
        return ""
    return touche.strip()


def _motifs_captures(data) -> tuple[str, ...]:
    """Motifs `screenshots.collect` : tout ou rien, au plus 8, chacun sous un dossier de jeu.

    Un motif sans « / » viserait la RACINE des jeux ; ce qu'il attraperait
    serait DÉPLACÉ, pas seulement lu : un motif douteux n'a pas de seconde chance.
    """
    data = data.get("collect") if isinstance(data, dict) else None
    if not isinstance(data, list) or not data or len(data) > 8:
        return ()
    if not all(_motif_sur(m) and "/" in m.replace("\\", "/").strip("/") for m in data):
        log.warning("Bloc screenshots ignoré : %r", data)
        return ()
    return tuple(m.replace("\\", "/") for m in data)


def _parse_sauvegardes(data) -> "Sauvegardes | None":
    """Tout ou rien, comme `language_registry` : un bloc douteux est ignoré en
    entier, et le jeu n'a simplement pas de sauvegardes affichées."""
    if not isinstance(data, dict):
        return None
    racine = data.get("root")
    dossiers = data.get("folders")
    fichiers = data.get("files")
    exclure = data.get("exclude", [])
    premier = data.get("first", 0)
    if racine not in RACINES_SAUVEGARDES:
        return None
    if isinstance(dossiers, str):
        dossiers = [dossiers]
    if (not isinstance(dossiers, list) or not dossiers or len(dossiers) > 8
            or not all(_motif_sur(d) for d in dossiers)):
        log.warning("Bloc saves ignoré (dossiers) : %r", dossiers)
        return None
    if not _motif_sur(fichiers) or fichiers.replace("\\", "/").count("/") > 1:
        log.warning("Bloc saves ignoré (fichiers) : %r", fichiers)
        return None
    if not isinstance(exclure, list) or not all(isinstance(e, str) for e in exclure):
        return None
    if not isinstance(premier, int) or isinstance(premier, bool) or not 0 <= premier <= 9:
        return None
    emplacements = data.get("slots", "")
    if emplacements not in FORMATS_EMPLACEMENTS:
        emplacements = ""
    return Sauvegardes(racine=racine,
                       dossiers=tuple(d.replace("\\", "/") for d in dossiers),
                       fichiers=fichiers.replace("\\", "/"),
                       exclure=tuple(exclure), premier=premier,
                       emplacements=emplacements)


# Pour tout ce qui finit dans un NOM DE FICHIER (identifiant, version) :
# « ../../../evil » écrirait hors du dossier.
_JETON_SUR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True, slots=True)
class Trailer:
    """Bande-annonce d'un jeu, hébergée HORS de l'exécutable (règle 90)."""

    game_id: str
    version: str
    url: str
    size_mb: int = 0
    sha256: str | None = None

    @property
    def filename(self) -> str:
        """Nom du fichier LOCAL, qui porte la VERSION (règle 91) : l'asset
        ne la porte pas, et l'ancienne vidéo rejouerait pour toujours."""
        return f"{self.game_id}_video_v{self.version}.mp4"


def _parse_trailers(raw) -> tuple[Trailer, ...]:
    """Lit le bloc `trailers` du catalogue. Une entrée douteuse est IGNORÉE.

    Jamais d'exception : une bande-annonce est un ornement, et un catalogue
    trafiqué ne doit pas priver quelqu'un de sa bibliothèque de jeux.
    """
    if not isinstance(raw, dict):
        return ()
    trailers = []
    for game_id, entree in raw.items():
        if not isinstance(entree, dict):
            log.warning("Bande-annonce ignorée (%s) : entrée de type %s",
                        game_id, type(entree).__name__)
            continue
        version = entree.get("version")
        url = _https_ou_rien(entree.get("url"))
        if not isinstance(version, str) or url is None:
            log.warning("Bande-annonce ignorée (%s) : version ou url absente/non-https", game_id)
            continue
        if not _JETON_SUR.match(str(game_id)) or not _JETON_SUR.match(version):
            log.warning("Bande-annonce refusée (%s v%s) : identifiant ou version "
                        "impropre à un nom de fichier", game_id, version)
            continue
        taille = entree.get("size_mb", 0)
        trailers.append(Trailer(
            game_id=str(game_id),
            version=version,
            url=url,
            size_mb=taille if isinstance(taille, int) and taille >= 0 else 0,
            sha256=_sha256_valide(entree.get("sha256")),
        ))
    return tuple(trailers)


@dataclass(frozen=True, slots=True)
class Contributor:
    """Quelqu'un à remercier dans l'À propos.

    Au catalogue : remercier ne doit pas attendre une release. `role`
    traduisible (`i18n`) ; `url` facultative, validée https comme `warning_url`.
    """
    name: str
    role: str = ""
    url: str = ""


def _parse_contributors(raw) -> tuple[Contributor, ...]:
    """Bloc `contributors` du catalogue. Tolérant : une entrée fautive est sautée."""
    if not isinstance(raw, list):
        if raw is not None:
            log.warning("'contributors' de type %s, ignoré", type(raw).__name__)
        return ()
    sortie: list[Contributor] = []
    for entree in raw:
        if not isinstance(entree, dict):
            log.warning("Contributeur ignoré (type %s)", type(entree).__name__)
            continue
        nom = _loc(entree, "name", "")
        if not isinstance(nom, str) or not nom.strip():
            log.warning("Contributeur sans nom, ignoré")
            continue
        role = _loc(entree, "role", "")
        sortie.append(Contributor(
            name=nom.strip(),
            role=role.strip() if isinstance(role, str) else "",
            url=_url_aide_valide(entree.get("url", "")),
        ))
    return tuple(sortie)
