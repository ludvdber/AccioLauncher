"""Les journaux des jeux gardés d'un lancement à l'autre, et les réglages de chaque lancement (Ludo, 2026-11-20).

Le correctif réécrit ses `<dll>_accio.log` à chaque démarrage du jeu, et les jeux UE1 leur `.log` : un joueur qui
signalait un souci après avoir relancé le jeu n'avait plus la trace de la partie fautive, et rien ne disait quels
réglages tournaient (#40 : « HP4 en 4K mais l'image est plus basse », sans rien d'autre).

À chaque lancement, AVANT que le jeu ne réécrive ses journaux (`GameManager.launch_game`, tout réglage posé) :

1. les journaux actuels du jeu sont COPIÉS dans le dossier du lancement précédent (ce sont les siens), chacun
   réduit à sa fin au-delà de `OCTETS_MAX` ;
2. un dossier neuf reçoit `parametres.txt` : les sections que le launcher règle, telles qu'elles partent au jeu ;
3. seuls les `LANCEMENTS` derniers dossiers restent.

Rien n'est déplacé ni effacé dans le dossier du jeu. Ne lève jamais : un échec va au journal du launcher.
`rapport` assemble le tout pour le bouton « Rapport du jeu » de la rubrique Fichiers.
"""
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path

from src.core.config import LAUNCHER_DATA_PATH, Config
from src.core.game_data import GameData

log = logging.getLogger(__name__)

DOSSIER = LAUNCHER_DATA_PATH / "journaux_jeux"
LANCEMENTS = 4
OCTETS_MAX = 1_000_000
PARAMETRES = "parametres.txt"
# L'ini du correctif de chaque jeu (`Harry-Potter-PC-Fix/data/HPx/`), à côté de l'exe.
INI_CORRECTIF = ("d3d9.ini", "winmm.ini", "dinput8.ini")
# HP3 : le fichier de ses réglages graphiques, à côté de l'exe ; jamais nommé dans le rapport.
_REGLAGES_GRAPHIQUES = "dgVoodoo.conf"
_FORMAT = "%Y-%m-%d_%H-%M-%S"
_NOM = re.compile(r"^\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d(?:_\d+)?$")


def fichiers_journaux(game: GameData, install_path: Path) -> list[Path]:
    """Les `.log` du jeu : à côté de l'exe (correctif, manette) et dans son dossier de Documents
    (HP1-HP3 : `HP.log`…)."""
    from src.core import sauvegardes
    dossiers = [(install_path / game.executable).parent]
    spec = game.sauvegardes
    if spec is not None and spec.racine == "documents":
        d = sauvegardes.dossier(spec)
        if d is not None:
            dossiers.append(d.parent)
    trouves: list[Path] = []
    for d in dossiers:
        try:
            trouves += sorted(f for f in d.glob("*.log") if f.is_file())
        except OSError:
            continue
    return trouves


def _lire(chemin: Path) -> str:
    """Un ini UE1 peut être en UTF-16 (avec BOM), le correctif écrit de l'UTF-8, le reste du cp1252."""
    brut = chemin.read_bytes()
    if brut.startswith((b"\xff\xfe", b"\xfe\xff")):
        return brut.decode("utf-16", errors="replace")
    try:
        return brut.decode("utf-8-sig")
    except UnicodeDecodeError:
        return brut.decode("cp1252", errors="replace")


def _compacte(texte: str, sections: set[str] | None = None) -> list[str]:
    """Les lignes `[section]` et `clé=valeur` d'un ini, sans commentaires ni lignes vides ;
    `sections` (en minuscules) : seulement celles-là."""
    lignes: list[str] = []
    garde = sections is None
    for brute in texte.splitlines():
        ligne = brute.strip()
        if not ligne or ligne[0] in ";#":
            continue
        if ligne.startswith("["):
            garde = sections is None or ligne.strip("[]").casefold() in sections
        if garde:
            lignes.append(ligne)
    return lignes


def parametres(game: GameData, config: Config, taille: tuple[int, int] | None = None) -> str:
    """Ce que le launcher règle pour ce jeu, tel que le jeu va le lire."""
    from src.core.pre_launch import resolve_safe_path
    exe = (config.install_path / game.executable).parent
    lignes = [f"{game.name} ({game.id})"]
    if taille is not None:
        lignes.append(f"Résolution écrite : {taille[0]}×{taille[1]}")
    choix = config.resolution_jeu.get(game.id, "")
    lignes.append(f"Résolution choisie : {choix or 'automatique (écran)'}")
    blocs: list[tuple[str, Path, set[str] | None]] = [
        (f"Correctif · {nom}", exe / nom, None) for nom in INI_CORRECTIF]
    blocs.append(("Réglages graphiques", exe / _REGLAGES_GRAPHIQUES, None))
    # Les sections des fichiers que le catalogue patche (HP1-HP3 : rendu, fenêtre), elles seules.
    voulues: dict[Path, set[str]] = {}
    patches = list(game.pre_launch.ini_patches) if game.pre_launch is not None else []
    for p in patches:
        chemin = resolve_safe_path(p.file, game, config)
        if chemin is not None:
            voulues.setdefault(chemin, set()).add(p.section.casefold())
    blocs += [(f"Jeu · {chemin.name}", chemin, sections) for chemin, sections in voulues.items()]
    for titre, chemin, sections in blocs:
        try:
            contenu = _compacte(_lire(chemin), sections)
        except OSError:
            continue
        lignes += ["", f"── {titre} ──", *contenu]
    return "\n".join(lignes) + "\n"


def _copier_la_fin(source: Path, cible: Path) -> None:
    taille = source.stat().st_size
    if taille <= OCTETS_MAX:
        shutil.copyfile(source, cible)
        return
    with source.open("rb") as f:
        f.seek(taille - OCTETS_MAX)
        fin = f.read()
    cible.write_bytes(b"[...]\n" + fin.split(b"\n", 1)[-1])


def lancements(game_id: str, racine: Path | None = None) -> list[Path]:
    """Les dossiers des lancements gardés, du plus récent au plus ancien."""
    dossier = (racine or DOSSIER) / game_id
    try:
        return sorted((d for d in dossier.iterdir() if d.is_dir() and _NOM.match(d.name)), reverse=True)
    except OSError:
        return []


def au_lancement(game: GameData, config: Config, taille: tuple[int, int] | None = None,
                 racine: Path | None = None, maintenant: datetime | None = None) -> Path | None:
    """Range les journaux de la partie précédente et note les réglages de celle-ci ; rend son dossier."""
    racine = racine or DOSSIER
    try:
        anciens = lancements(game.id, racine)
        if anciens and not any(anciens[0].glob("*.log")):
            for f in fichiers_journaux(game, config.install_path):
                _copier_la_fin(f, anciens[0] / f.name)
        nom = (maintenant or datetime.now()).strftime(_FORMAT)
        dossier = racine / game.id / nom
        n = 1
        while dossier.exists():
            n += 1
            dossier = racine / game.id / f"{nom}_{n}"
        dossier.mkdir(parents=True)
        (dossier / PARAMETRES).write_text(parametres(game, config, taille), encoding="utf-8")
        for vieux in lancements(game.id, racine)[LANCEMENTS:]:
            shutil.rmtree(vieux, ignore_errors=True)
        return dossier
    except OSError:
        log.warning("Journaux de %s non rangés", game.id, exc_info=True)
        return None


def rapport(game: GameData, config: Config, entete: list[str], racine: Path | None = None) -> str:
    """Le rapport d'UN jeu : en-tête, réglages d'aujourd'hui, journaux actuels, puis chaque lancement gardé ;
    chemins personnels cachés."""
    from src.core import diagnostic
    journaux: list[tuple[str, str]] = [("Réglages actuels", parametres(game, config))]
    gardes = lancements(game.id, racine)
    # Le plus récent est celui de la dernière partie : ses journaux sont encore à côté du jeu.
    journaux += [(f"Dernière partie · {f.name}", diagnostic.lire_la_fin(f))
                 for f in fichiers_journaux(game, config.install_path)]
    for rang, dossier in enumerate(gardes):
        quand = dossier.name.replace("_", " ", 1)
        fichiers = sorted(dossier.iterdir()) if rang else [dossier / PARAMETRES]
        for f in fichiers:
            if f.is_file():
                titre = "réglages" if f.name == PARAMETRES else f.name
                journaux.append((f"Lancement du {quand} · {titre}", diagnostic.lire_la_fin(f)))
    return diagnostic.rapport_complet("\n".join(entete), journaux)
