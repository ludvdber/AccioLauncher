"""Étapes post-extraction : fichiers de config, rangement, déblocage NTFS."""

import logging
import shutil
from pathlib import Path

from src.core.config import get_documents_dir
from src.core.win_utils import remove_zone_identifier

log = logging.getLogger(__name__)

# Extensions interdites en destination d'un config_file : aucun fichier de
# configuration légitime n'en a besoin, et elles ouvrent toutes une voie
# d'exécution (raccourci, script, DLL chargée par un jeu…).
_FORBIDDEN_DEST_SUFFIXES = frozenset({
    ".exe", ".com", ".scr", ".pif", ".msi", ".bat", ".cmd",
    ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
    ".lnk", ".url", ".dll", ".reg", ".hta",
})


def allowed_config_roots() -> list[Path]:
    """Dossiers dans lesquels un `config_file` du catalogue peut écrire.

    Volontairement PLUS étroit que le home : `~/AppData/Roaming/Microsoft/
    Windows/Start Menu/Programs/Startup` est sous le home, et une entrée de
    catalogue empoisonnée y déposerait un fichier exécuté à chaque ouverture de
    session — qui survivrait à la désinstallation du jeu. Tous les jeux du
    catalogue écrivent dans `~/Documents/<jeu>/` ; « Saved Games » est ajouté
    parce que c'est l'autre emplacement standard des sauvegardes Windows.
    """
    return [get_documents_dir(), Path.home() / "Saved Games"]


def config_dest_error(dest: Path, roots: list[Path]) -> str | None:
    """Raison du refus d'une destination de config, ou None si elle est valide.

    Fonction pure (testable sans disque ni catalogue).
    """
    if dest.suffix.lower() in _FORBIDDEN_DEST_SUFFIXES:
        return f"extension exécutable refusée ({dest.suffix})"
    try:
        resolved = dest.resolve()
    except OSError as exc:
        return f"chemin invalide ({exc})"
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return None
        except (ValueError, OSError):
            continue
    return "hors des dossiers autorisés (Documents, Saved Games)"


def ranger_dans_sous_dossier(dossier_jeu: Path, nom: str) -> int:
    """Déplace le contenu de `dossier_jeu` dans `dossier_jeu/nom`. Rend le compte.

    HP7 partie 1 et 2 ne démarrent QUE si leurs fichiers vivent dans un
    sous-dossier `pc` sous la clé `Install Dir` du registre — relevé dans les
    binaires (`Install Dir` suivi de `pc`) puis vérifié en lançant le jeu : à
    plat il sort en 0,5 s avec le code 0, sans un mot, par le chemin
    « insérez le disque ». Le NOM compte : `zz` échoue comme `à plat`.

    Les archives publiées, elles, posent les fichiers à plat. Plutôt que de
    republier 12 Go, on range après extraction — un renommage sur le même
    volume, donc instantané quelle que soit la taille du jeu.

    Idempotent : rejoué (réparation, mise à jour), il ne fait que redescendre
    ce que la nouvelle extraction a reposé à plat, en écrasant l'ancien.
    """
    if not nom or not dossier_jeu.is_dir():
        return 0
    cible = dossier_jeu / nom
    cible.mkdir(parents=True, exist_ok=True)
    deplaces = 0
    for entree in list(dossier_jeu.iterdir()):
        if entree == cible:
            continue
        destination = cible / entree.name
        try:
            if destination.exists():
                # Réparation : l'archive vient de reposer un fichier à plat
                # par-dessus une installation déjà rangée. `os.replace` écrase
                # en une opération ; sans ça le déplacement échouerait et on
                # garderait l'ANCIEN fichier tout en croyant l'avoir remplacé.
                if destination.is_dir():
                    shutil.rmtree(destination)
                else:
                    destination.unlink()
            entree.replace(destination)
            deplaces += 1
        except OSError as exc:
            log.warning("Impossible de ranger %s dans %s/ : %s",
                        entree.name, nom, exc)
    if deplaces:
        log.info("%d élément(s) rangé(s) dans %s/", deplaces, nom)
    return deplaces


def unblock_extracted(extracted_dirs: list[Path]) -> int:
    """Supprime le flag NTFS Zone.Identifier des fichiers extraits."""
    return sum(remove_zone_identifier(d) for d in extracted_dirs)


def apply_config_files(
    destination: Path, game_dir: str | None,
    config_files: list[tuple[str, str]],
) -> None:
    """Copie les fichiers de configuration vers Documents (avec backup .bak)."""
    if not config_files:
        return

    for source_rel, dest_tilde in config_files:
        try:
            base = destination / game_dir if game_dir else destination
            src = (base / source_rel).resolve()
            if not src.is_relative_to(destination.resolve()):
                log.warning("Config source hors du dossier d'installation : %s", source_rel)
                continue
            if not src.exists():
                log.warning("Fichier de config source introuvable : %s", src)
                continue

            docs_dir = get_documents_dir()
            dest_str = dest_tilde.replace("~/Documents", str(docs_dir)).replace("~", str(Path.home()))
            dest = Path(dest_str)
            reason = config_dest_error(dest, allowed_config_roots())
            if reason is not None:
                log.warning("Config destination refusée (%s) : %s", reason, dest_tilde)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)

            if dest.exists():
                bak = dest.with_suffix(dest.suffix + ".bak")
                shutil.copy2(dest, bak)
                log.info("Backup de la config existante : %s → %s", dest, bak)

            shutil.copy2(src, dest)
            log.info("Config copiée : %s → %s", src, dest)
        except OSError as exc:
            log.warning("Impossible de copier le fichier de config %s : %s", source_rel, exc)
