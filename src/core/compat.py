"""Couche de compatibilité Linux : lancer des jeux Windows par umu-run ou wine.

Sous Linux, le launcher est natif mais les huit jeux restent des `.exe` : on
les lance par **umu-run** (Proton hors de Steam, dans le conteneur du Steam
Linux Runtime) de préférence, sinon par le **wine** du système. Tout ce qui
suit en découle, et `docs/LINUX.md` en garde les raisons et les relevés.

Le « Windows » des jeux est un PRÉFIXE Wine : leur Documents, leur AppData,
leur registre et leurs runtimes Visual C++ y vivent, pas dans le `$HOME` de
l'utilisateur. Ce module est le seul à savoir où il est et comment on y parle ;
les autres (`config`, `sauvegardes`, `game_registry`, `system_checks`,
`pre_launch`, `game_manager`) lui posent la question au lieu de la trancher.

**Un préfixe PARTAGÉ par tous les jeux**, un par famille de lanceur
(`_Launcher/prefixes/umu`, `_Launcher/prefixes/wine`). Partagé parce que c'est
le modèle que tout le code suppose déjà — un Documents, un AppData, un
registre, exactement comme sous Windows — et que le socle Visual C++ exigé par
les huit jeux ne s'installe alors qu'une fois. Un par FAMILLE parce que Proton
range le profil sous `steamuser` et Wine sous le nom Unix, et que Proton
« met à niveau » un préfixe Wine en y recopiant le sien : passer de l'un à
l'autre sur le même dossier rendrait les sauvegardes invisibles, sans un mot.

Rien ici n'importe Qt, et rien ne se lance à l'import : tout ce qui touche au
disque ou au système se fait À L'APPEL, avec des chemins résolus depuis
`config.CONFIG_FILE_PATH` — c'est ce que `tests/conftest.py` redirige, et la
garde qui protège la vraie configuration protège donc aussi le vrai préfixe.
"""

import codecs
import functools
import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

FAMILLES = ("umu", "wine")

# Dossier des préfixes, sous `_Launcher/` : la racine d'AccioLauncher
# n'appartient qu'aux jeux (règle d'arborescence de CLAUDE.md).
DOSSIER_PREFIXES = "prefixes"

# Profil Windows des préfixes Proton. umu le crée, avec un lien du nom Unix
# vers lui (relevé dans `umu/umu_run.py`, `setup_pfx`, 2026-09-24).
PROFIL_PROTON = "steamuser"

# Forcer un lanceur, pour le dépannage : `ACCIO_COMPAT=wine` (ou `umu`).
VARIABLE_FORCAGE = "ACCIO_COMPAT"

# Marque qu'écrit Wine à l'octet 0x40 de ses propres DLL. Un préfixe neuf en
# contient déjà dans WinSxS (VC80, VC90), rangées exactement là où le vrai
# redistribuable irait : sans ce test, on croirait Visual C++ installé.
# Vérifié sur un préfixe Wine 9.0 le 2026-09-24 ; « placeholder » est la
# formulation des versions plus anciennes.
_MARQUES_WINE = (b"Wine builtin DLL", b"Wine placeholder DLL")

# Un nom de fichier de journal fait d'un identifiant de jeu, qui vient du
# catalogue DISTANT : même filtre que les noms de bande-annonce.
_NOM_SUR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True, slots=True)
class Lanceur:
    """La couche de compatibilité retenue sur cette machine."""

    famille: str        # « umu » ou « wine »
    executable: str     # chemin ABSOLU de umu-run / wine
    # winetricks du système, pour la famille wine. Vide avec umu : il est
    # livré avec UMU-Proton et GE-Proton, et `umu-run winetricks` le trouve.
    winetricks: str = ""
    # PROTONPATH retenu pour umu. Vide = laisser umu choisir (UMU-Proton, qu'il
    # télécharge et tient à jour lui-même).
    proton: str = ""


# ─── Détection ───

def dossiers_programmes() -> list[Path]:
    """Où chercher un programme que le PATH ne donne pas.

    Le PATH d'une session graphique ne contient pas toujours `~/.local/bin`,
    où s'installent umu (archive « zipapp ») et winetricks à la main.
    """
    return [Path.home() / ".local" / "bin", Path("/usr/local/bin"), Path("/usr/bin")]


def _trouver(nom: str, which=shutil.which, dossiers: list[Path] | None = None) -> str:
    """Chemin ABSOLU d'un programme, ou chaîne vide — jamais le nom seul
    (règle 1 de CLAUDE.md)."""
    trouve = which(nom)
    if trouve:
        return os.path.abspath(trouve)
    for dossier in dossiers_programmes() if dossiers is None else dossiers:
        candidat = dossier / nom
        if candidat.is_file() and os.access(candidat, os.X_OK):
            return str(candidat)
    return ""


def dossiers_proton() -> list[Path]:
    """Où Steam, ProtonUp-Qt et umu rangent les versions de Proton.

    Mêmes emplacements qu'umu (`umu_consts.py` : `STEAM_COMPAT`,
    `UMU_COMPAT`), plus ceux de Steam natif et de Steam en Flatpak.
    """
    maison = Path.home()
    donnees = Path(os.environ.get("XDG_DATA_HOME") or maison / ".local" / "share")
    return [
        donnees / "Steam" / "compatibilitytools.d",
        donnees / "umu" / "compatibilitytools",
        maison / ".steam" / "root" / "compatibilitytools.d",
        maison / ".var" / "app" / "com.valvesoftware.Steam" / "data" / "Steam"
        / "compatibilitytools.d",
        Path("/usr/share/steam/compatibilitytools.d"),
    ]


def _cle_version(nom: str) -> list:
    """« GE-Proton10-15 » après « GE-Proton9-27 » : ordre NUMÉRIQUE. Pure."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", nom)]


def proton_installe(dossiers: list[Path] | None = None) -> str:
    """Le Proton à donner à umu, ou chaîne vide pour le laisser choisir.

    GE-Proton d'abord (ProtonUp-Qt l'installe, et c'est ce qu'on attend sur
    une machine de jeu), puis un UMU-Proton déjà téléchargé. Donner un chemin
    ABSOLU a un second intérêt : umu ne contacte plus GitHub pour vérifier
    qu'une version plus récente existe (`umu_proton.get_umu_proton`) — ce qui,
    sur une écriture de registre faite pendant que la fenêtre attend, pourrait
    déclencher le téléchargement de plusieurs centaines de Mo.
    """
    candidats: dict[str, list[Path]] = {"GE-Proton": [], "UMU-Proton": []}
    for dossier in dossiers if dossiers is not None else dossiers_proton():
        try:
            entrees = list(dossier.iterdir())
        except OSError:
            continue
        for entree in entrees:
            for prefixe_nom, liste in candidats.items():
                if entree.name.startswith(prefixe_nom) and (entree / "proton").is_file():
                    liste.append(entree)
    for liste in candidats.values():
        if liste:
            return str(max(liste, key=lambda p: _cle_version(p.name)))
    return ""


def detecter(env=None, which=shutil.which, programmes: list[Path] | None = None,
             protons: list[Path] | None = None) -> Lanceur | None:
    """umu-run d'abord, wine ensuite ; None si aucun des deux n'est là.

    `ACCIO_COMPAT` restreint la recherche à une famille. Un `PROTONPATH` déjà
    posé par l'utilisateur est respecté : on ne le remplace pas. `which`,
    `programmes` et `protons` sont injectables : un test ne doit pas dépendre
    de ce qui est installé sur la machine qui le joue.
    """
    env = os.environ if env is None else env
    force = env.get(VARIABLE_FORCAGE, "").strip().lower()
    familles = (force,) if force in FAMILLES else FAMILLES
    for famille in familles:
        if famille == "umu":
            umu = _trouver("umu-run", which, programmes)
            if umu:
                proton = "" if env.get("PROTONPATH") else proton_installe(protons)
                return Lanceur("umu", umu, proton=proton)
        else:
            wine = _trouver("wine", which, programmes) or _trouver("wine64", which, programmes)
            if wine:
                return Lanceur("wine", wine,
                               winetricks=_trouver("winetricks", which, programmes))
    return None


@functools.cache
def lanceur() -> Lanceur | None:
    """Le lanceur de CETTE machine, cherché une fois par session.

    Toujours None sous Windows : les jeux s'y lancent tels quels. Oublié par
    `oublier()`, appelé au retour dans la fenêtre — quelqu'un qui vient
    d'installer umu n'a pas à redémarrer le launcher.
    """
    if sys.platform == "win32":
        return None
    trouve = detecter()
    if trouve is None:
        log.warning("Aucun lanceur de compatibilité (umu-run, wine) trouvé")
    else:
        log.info("Lanceur de compatibilité : %s (%s)%s", trouve.famille,
                 trouve.executable, f", Proton {trouve.proton}" if trouve.proton else "")
    return trouve


def oublier() -> None:
    """Refait la détection au prochain appel.

    `cache_clear` cherché plutôt qu'appelé d'autorité, comme dans
    `system_checks.invalidate_vcredist_cache` : un test qui remplace
    `lanceur` ne doit pas faire casser le retour dans la fenêtre.
    """
    vider = getattr(lanceur, "cache_clear", None)
    if vider is not None:
        vider()


# ─── Le préfixe et ses dossiers ───

def _donnees_launcher() -> Path:
    """`_Launcher/`, résolu À L'APPEL (cf. l'en-tête du module)."""
    from src.core import config
    return config.CONFIG_FILE_PATH.parent


def dossier_journaux() -> Path:
    return _donnees_launcher() / "logs"


def prefixe(famille: str | None = None) -> Path:
    """Le préfixe de la famille donnée, sinon de celle du lanceur trouvé.

    Sans lanceur, celui d'umu : c'est le recommandé, et un jeu installé avant
    qu'umu le soit doit déposer sa configuration là où umu la lira.
    """
    if famille not in FAMILLES:
        trouve = lanceur()
        famille = trouve.famille if trouve is not None else "umu"
    return _donnees_launcher() / DOSSIER_PREFIXES / famille


def pret(pfx: Path | None = None) -> bool:
    """True si le préfixe est initialisé (registre écrit, `drive_c` créé)."""
    pfx = pfx if pfx is not None else prefixe()
    return (pfx / "system.reg").is_file() and (pfx / "drive_c").is_dir()


def _nom_unix() -> str:
    """Le nom que Wine donne au profil : celui de l'utilisateur Unix."""
    try:
        import pwd
        return pwd.getpwuid(os.getuid()).pw_name
    except (ImportError, KeyError, AttributeError):
        return os.environ.get("USER") or "user"


def profil(pfx: Path | None = None) -> Path:
    """`drive_c/users/<profil>` du préfixe.

    Proton : `steamuser`. Wine : le nom Unix — ou, si le préfixe existe déjà,
    le seul profil qu'il contient (un `USER` différent de la base des mots de
    passe ne doit pas faire chercher un dossier qui n'existe pas).
    """
    pfx = pfx if pfx is not None else prefixe()
    utilisateurs = pfx / "drive_c" / "users"
    if pfx.name == "umu" or (utilisateurs / PROFIL_PROTON).is_dir():
        return utilisateurs / PROFIL_PROTON
    try:
        existants = [d for d in utilisateurs.iterdir()
                     if d.is_dir() and d.name.lower() != "public"]
    except OSError:
        existants = []
    if len(existants) == 1:
        return existants[0]
    return utilisateurs / _nom_unix()


def documents(pfx: Path | None = None) -> Path:
    return profil(pfx) / "Documents"


def appdata_local(pfx: Path | None = None) -> Path:
    """AppData\\Local ; les très vieux Wine l'appelaient autrement."""
    base = profil(pfx)
    ancien = base / "Local Settings" / "Application Data"
    if not (base / "AppData").exists() and ancien.is_dir():
        return ancien
    return base / "AppData" / "Local"


def saved_games(pfx: Path | None = None) -> Path:
    return profil(pfx) / "Saved Games"


def chemin_windows(chemin: Path, pfx: Path | None = None) -> str:
    r"""Le chemin tel que le JEU le lit, sous Wine.

    Ce que Python écrit est un chemin de l'hôte ; ce que le jeu lit dans son
    INI ou dans son registre doit être un chemin WINDOWS. Un `SavePath=/home/…`
    ne tombait juste que si le lecteur courant du jeu était `Z:` — par
    accident. Dans `drive_c` : `C:\…` ; ailleurs : `Z:\…`, que Wine et Proton
    relient à `/`.

    La comparaison est LEXICALE, sans résoudre les liens : Documents peut être
    un lien vers `~/Documents` (Wine le fait), et c'est `C:\users\…` que le jeu
    connaît.
    """
    chemin = Path(os.path.abspath(chemin))
    pfx = pfx if pfx is not None else prefixe()
    lecteur_c = Path(os.path.abspath(pfx / "drive_c"))
    try:
        relatif = chemin.relative_to(lecteur_c)
    except ValueError:
        return "Z:" + str(chemin).replace("/", "\\")
    return "C:\\" + "\\".join(relatif.parts)


# ─── Registre du préfixe (fichiers texte de Wine) ───

_HEXA = "0123456789abcdefABCDEF"
_ECHAPPEMENTS = {"a": "\a", "b": "\b", "e": "\x1b", "f": "\f", "n": "\n",
                 "r": "\r", "t": "\t", "v": "\v"}


def desechapper(texte: str) -> str:
    r"""Chaîne d'un `.reg` de Wine → texte. Pure.

    Relevé sur un préfixe Wine 9.0 : « frédéric » y est écrit
    `fr\x00e9d\xe9ric`. Wine note tout caractère hors ASCII en `\x` suivi de
    UN à QUATRE chiffres hexadécimaux, et en met quatre dès que le caractère
    suivant pourrait être pris pour un chiffre de plus. Lire jusqu'à quatre
    chiffres est donc exact dans tous les cas — c'est ce que fait Wine
    lui-même (`parse_strW`). Les caractères de contrôle sortent en
    `\n`-style ou en octal.
    """
    sortie: list[str] = []
    i, n = 0, len(texte)
    while i < n:
        c = texte[i]
        if c != "\\" or i + 1 >= n:
            sortie.append(c)
            i += 1
            continue
        s = texte[i + 1]
        if s == "x":
            j = i + 2
            while j < n and j - (i + 2) < 4 and texte[j] in _HEXA:
                j += 1
            if j > i + 2:
                sortie.append(chr(int(texte[i + 2:j], 16)))
            else:
                sortie.append("x")
            i = j
        elif s in "01234567":
            j = i + 1
            while j < n and j - (i + 1) < 3 and texte[j] in "01234567":
                j += 1
            sortie.append(chr(int(texte[i + 1:j], 8)))
            i = j
        else:
            sortie.append(_ECHAPPEMENTS.get(s, s))
            i += 2
    return "".join(sortie)


def _chaine_entre_guillemets(texte: str, debut: int) -> tuple[str, int] | None:
    """(contenu brut, index après le guillemet fermant) ; `debut` pointe le « " »."""
    i = debut + 1
    while i < len(texte):
        if texte[i] == "\\":
            i += 2
            continue
        if texte[i] == '"':
            return texte[debut + 1:i], i + 1
        i += 1
    return None


def _valeur(brute: str):
    """Valeur d'une ligne de `.reg` de Wine : chaîne, DWORD, ou None (ignorée)."""
    if brute.startswith('"'):
        lu = _chaine_entre_guillemets(brute, 0)
        return desechapper(lu[0]) if lu else None
    if brute.startswith("str(2):") or brute.startswith("str(1):"):
        return _valeur(brute[7:])
    if brute.startswith("dword:"):
        try:
            return int(brute[6:14], 16)
        except ValueError:
            return None
    return None      # hex(…), listes : rien dont le launcher ait besoin


def lire_cle(texte: str, cle: str) -> dict:
    """Valeurs nommées d'une clé dans le TEXTE d'un `system.reg` / `user.reg`.

    Pure. `cle` est relative à la racine du fichier (« Software\\…  »), comparée
    sans tenir compte de la casse, comme le fait Windows. Une clé absente rend
    `{}` : ce n'est pas une erreur, c'est « rien à comparer ».
    """
    cible = cle.replace("/", "\\").strip("\\").lower()
    trouve: dict = {}
    dedans = False
    for ligne in texte.splitlines():
        if ligne.startswith("["):
            fin = ligne.rfind("]")
            if dedans:
                break
            dedans = fin > 0 and desechapper(ligne[1:fin]).lower() == cible
            continue
        if not dedans or not ligne.startswith('"'):
            continue
        lu = _chaine_entre_guillemets(ligne, 0)
        if lu is None or ligne[lu[1]:lu[1] + 1] != "=":
            continue
        valeur = _valeur(ligne[lu[1] + 1:])
        if valeur is not None:
            trouve[desechapper(lu[0])] = valeur
    return trouve


def _lire(fichier: Path) -> str:
    try:
        return fichier.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def architecture(pfx: Path) -> str:
    """« win64 » ou « win32 », lu dans l'en-tête de `system.reg`."""
    for ligne in _lire(pfx / "system.reg").splitlines()[:8]:
        if ligne.startswith("#arch="):
            return ligne[6:].strip()
    return "win64"


def cle_effective(pfx: Path, ruche: str, cle: str, vue: int) -> str:
    r"""Où se trouve RÉELLEMENT une clé 32 bits dans le préfixe.

    Même règle que `game_registry.construire_reg` : la vue 32 bits s'écrit
    `Software\WOW6432Node\…`. Deux exceptions que Windows fait aussi : un
    préfixe 32 bits n'a pas de redirection, et `HKCU\Software` est PARTAGÉ
    entre les deux vues depuis Windows 7.
    """
    segments = [s for s in cle.replace("/", "\\").split("\\") if s]
    if (vue == 32 and ruche == "HKLM" and architecture(pfx) == "win64"
            and segments and not any(s.lower() == "wow6432node" for s in segments)):
        segments = [segments[0], "WOW6432Node", *segments[1:]]
    return "\\".join(segments)


def vue_effective(pfx: Path, ruche: str, vue: int) -> int:
    """La vue à donner à `construire_reg` pour écrire là où `cle_effective` lit."""
    if vue == 32 and ruche == "HKLM" and architecture(pfx) == "win64":
        return 32
    return 64


def lire_valeurs(pfx: Path, ruche: str, cle: str, noms, vue: int = 32) -> dict:
    """Valeurs nommées en place dans le registre du préfixe. Aucun processus lancé.

    Les noms de valeur ne tiennent pas compte de la casse (Windows non plus) ;
    le dictionnaire rendu est indexé par les noms DEMANDÉS.
    """
    fichier = pfx / ("system.reg" if ruche == "HKLM" else "user.reg")
    trouve = lire_cle(_lire(fichier), cle_effective(pfx, ruche, cle, vue))
    par_nom = {nom.lower(): valeur for nom, valeur in trouve.items()}
    return {nom: par_nom[nom.lower()] for nom in noms if nom.lower() in par_nom}


def encodage_ansi(pfx: Path | None = None, defaut: str = "cp1252") -> str:
    """Page de codes ANSI du préfixe — celle dans laquelle UE1 écrit ses INI.

    Sous Windows c'est `mbcs`. Sous Wine, elle dépend de la langue de la
    session qui a créé le préfixe, et Wine la note dans son registre
    (`HKLM\\System\\CurrentControlSet\\Control\\Nls\\Codepage`, valeur `ACP` —
    `1252` relevé sur un préfixe neuf).
    """
    pfx = pfx if pfx is not None else prefixe()
    acp = lire_valeurs(pfx, "HKLM", r"System\CurrentControlSet\Control\Nls\Codepage",
                       ["ACP"], vue=64).get("ACP")
    if isinstance(acp, str) and acp.isdigit():
        try:
            return codecs.lookup(f"cp{acp}").name
        except LookupError:
            log.info("Page de codes %s inconnue de Python — repli %s", acp, defaut)
    return defaut


# ─── Prérequis ───

def est_dll_interne_wine(chemin: Path) -> bool:
    """True si ce fichier est une DLL de Wine lui-même, et non la vraie."""
    try:
        with open(chemin, "rb") as f:
            entete = f.read(0x40 + 32)
    except OSError:
        return False
    return entete[0x40:].startswith(_MARQUES_WINE)


def verbes_installes(pfx: Path | None = None) -> set[str]:
    """Verbes que winetricks a menés à bien dans ce préfixe (`winetricks.log`).

    C'est le registre que tient winetricks lui-même (`winetricks
    list-installed` le lit) ; `umu-run winetricks` écrit le même fichier.
    """
    pfx = pfx if pfx is not None else prefixe()
    return {ligne.strip().lower() for ligne in _lire(pfx / "winetricks.log").splitlines()
            if ligne.strip()}


# ─── Surcharges de DLL ───

def composer_surcharges(existant: str, noms) -> str:
    """`WINEDLLOVERRIDES` complété par nos DLL, en `n,b` (native d'abord).

    Pure. Une DLL que l'utilisateur surcharge déjà n'est pas touchée : son
    réglage est délibéré, le nôtre est un défaut raisonnable. `n,b` et jamais
    `n` : si la DLL livrée manque (quarantaine d'antivirus, fichier supprimé),
    le jeu retombe sur celle de Wine au lieu de ne plus démarrer.
    """
    deja: set[str] = set()
    for entree in (existant or "").split(";"):
        dlls = entree.split("=", 1)[0]
        deja.update(d.strip().lower() for d in dlls.split(",") if d.strip())
    ajouts = [f"{nom}=n,b" for nom in noms if nom.lower() not in deja]
    morceaux = [m for m in ((existant or "").strip(";"), *ajouts) if m]
    return ";".join(morceaux)


# ─── Environnement et commandes ───

def environnement_hote(base=None, gele: bool | None = None) -> dict[str, str]:
    """L'environnement d'origine, débarrassé de ce que PyInstaller y a mis.

    Le chargeur d'un exécutable PyInstaller Linux ajoute son dossier en tête de
    `LD_LIBRARY_PATH` (l'ancienne valeur est gardée dans
    `LD_LIBRARY_PATH_ORIG`). Hérité, il ferait charger nos bibliothèques
    embarquées par wine, par umu et par le navigateur qu'ouvre `xdg-open` —
    des plantages qui n'auraient aucun rapport apparent avec le launcher. Les
    `_PYI_*` sont purgés pour la même raison que dans `self_update`.
    """
    env = dict(os.environ if base is None else base)
    gele = bool(getattr(sys, "frozen", False)) if gele is None else gele
    for cle in [k for k in env if k.startswith("_PYI_") or k == "_MEIPASS2"]:
        del env[cle]
    if gele:
        origine = env.pop("LD_LIBRARY_PATH_ORIG", None)
        if origine:
            env["LD_LIBRARY_PATH"] = origine
        else:
            env.pop("LD_LIBRARY_PATH", None)
    return env


def environnement(trouve: Lanceur, pfx: Path, surcharges=(), base=None) -> dict[str, str]:
    """Environnement d'un processus lancé dans le préfixe."""
    env = environnement_hote(base)
    env["WINEPREFIX"] = str(pfx)
    if trouve.famille == "umu":
        # umu met `umu-default` de lui-même ; le poser le rend visible au
        # journal, et une valeur de l'utilisateur reste la sienne.
        env.setdefault("GAMEID", "umu-default")
        if trouve.proton and not env.get("PROTONPATH"):
            env["PROTONPATH"] = trouve.proton
    else:
        env.setdefault("WINEDEBUG", "-all")
        if trouve.winetricks:
            env.setdefault("WINE", trouve.executable)
    dlls = composer_surcharges(env.get("WINEDLLOVERRIDES", ""), surcharges)
    if dlls:
        env["WINEDLLOVERRIDES"] = dlls
    return env


def commande_jeu(trouve: Lanceur, exe: Path) -> list[str]:
    return [trouve.executable, str(exe)]


def commande_creation(trouve: Lanceur) -> list[str]:
    """Crée (ou met à niveau) le préfixe. `umu-run ""` : documenté par umu."""
    if trouve.famille == "umu":
        return [trouve.executable, ""]
    return [trouve.executable, "wineboot", "--init"]


def commande_winetricks(trouve: Lanceur, verbes) -> list[str] | None:
    """Installe des verbes winetricks ; None si winetricks est introuvable.

    `umu-run winetricks` ajoute lui-même `-q` (non interactif) ; le winetricks
    du système le reçoit ici.
    """
    if trouve.famille == "umu":
        return [trouve.executable, "winetricks", *verbes]
    if not trouve.winetricks:
        return None
    return [trouve.winetricks, "-q", *verbes]


def commande_regedit(trouve: Lanceur, pfx: Path, fichier_windows: str) -> list[str]:
    """Importe un `.reg` dans le préfixe, en silence (`/S`).

    Avec umu, le chemin ABSOLU de `regedit.exe` quand il existe : umu exige un
    exécutable qu'il trouve sur le disque, et ne fait que supposer, avec un
    avertissement, qu'un nom nu se résoudra dans le préfixe.
    """
    if trouve.famille == "umu":
        regedit = pfx / "drive_c" / "windows" / "regedit.exe"
        return [trouve.executable, str(regedit) if regedit.is_file() else "regedit",
                "/S", fichier_windows]
    return [trouve.executable, "regedit", "/S", fichier_windows]


def journal_du_jeu(game_id: str) -> Path:
    """`_Launcher/logs/wine-<jeu>.log` : ce que Wine ou Proton ont dit au dernier lancement."""
    nom = game_id if _NOM_SUR.match(game_id or "") else "jeu"
    return dossier_journaux() / f"wine-{nom}.log"


# ─── Processus ───

def _meme_prefixe(declare: str, pfx: Path) -> bool:
    """Proton pose `WINEPREFIX=<préfixe>/pfx/`, et umu fait de `pfx` un lien
    vers le préfixe lui-même : on compare les chemins RÉSOLUS."""
    try:
        return os.path.realpath(declare) == os.path.realpath(pfx)
    except (OSError, ValueError):
        return False


def _wineprefix_de(dossier: Path) -> str | None:
    try:
        brut = (dossier / "environ").read_bytes()
    except OSError:
        return None
    for entree in brut.split(b"\0"):
        if entree.startswith(b"WINEPREFIX="):
            return entree[len(b"WINEPREFIX="):].decode("utf-8", "replace")
    return None


def processus_du_jeu(exe: str, pfx: Path | None = None, proc: Path = Path("/proc")) -> bool:
    """Un processus du jeu tourne-t-il, sous Wine ? Équivalent de `tasklist`.

    Wine nomme le processus (`comm`, tronqué à 15 caractères par le noyau)
    d'après l'exe WINDOWS, et met son chemin en premier argument. On ne
    regarde que les processus de l'utilisateur courant, et — quand leur
    environnement est lisible — ceux de NOTRE préfixe : un autre jeu du même
    nom lancé par Lutris ne doit pas prolonger une session.
    """
    cible = (exe or "").lower()
    if not cible:
        return False
    uid = os.getuid() if hasattr(os, "getuid") else None
    try:
        dossiers = list(proc.iterdir())
    except OSError:
        return False
    for dossier in dossiers:
        if not dossier.name.isdigit():
            continue
        try:
            if uid is not None and dossier.stat().st_uid != uid:
                continue
            comm = (dossier / "comm").read_text(encoding="utf-8", errors="replace").strip()
            arg0 = (dossier / "cmdline").read_bytes().split(b"\0")[0]
        except OSError:
            continue
        nom = arg0.decode("utf-8", "replace").replace("\\", "/").rsplit("/", 1)[-1]
        if comm.lower() != cible[:15] and nom.lower() != cible:
            continue
        if pfx is not None:
            declare = _wineprefix_de(dossier)
            if declare is not None and not _meme_prefixe(declare, pfx):
                continue
        return True
    return False
