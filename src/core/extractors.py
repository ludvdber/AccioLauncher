"""Extracteurs d'archives 7z et zip avec protection Zip Slip.

Indépendant de Qt — l'orchestrateur (Installer) injecte les callbacks de progression
et le check d'annulation.

7z.exe (bundlé avec l'app) est l'unique extracteur 7z : progression fine,
annulation immédiate (kill du process), support natif des archives
multi-volumes (.7z.001) et de tous les filtres (BCJ2…). py7zr a été retiré
le 2026-06-10 : il ne savait ni annuler, ni progresser, ni lire BCJ2.
"""

import logging
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable

log = logging.getLogger(__name__)

# Callbacks injectés depuis l'Installer.
ProgressCb = Callable[[int], None]
CancelledCb = Callable[[], bool]

# Délai max pour lister le contenu d'une archive avant extraction.
_LIST_TIMEOUT_S = 120
# Délai de récupération du process 7z APRÈS la fin de son flux de sortie.
# Ce n'est pas une limite de durée d'extraction : à ce point-là, 7z.exe a
# déjà fini d'écrire.
_REAP_TIMEOUT_S = 30


def check_path_traversal(destination: Path, member_name: str) -> bool:
    """Vérifie qu'un fichier extrait ne sort pas du dossier de destination (Zip Slip)."""
    target = (destination / member_name).resolve()
    return target.is_relative_to(destination.resolve())


def is_unsafe_entry(name: str) -> bool:
    """True si un nom d'entrée d'archive sortirait du dossier de destination.

    Fonction pure (testable sans 7z ni disque). Rejette les chemins absolus,
    les lettres de lecteur, les chemins UNC et toute remontée `..`.
    """
    normalized = name.replace("\\", "/").strip()
    if not normalized:
        return True
    if len(normalized) >= 2 and normalized[1] == ":":
        return True          # C:\... ou C:/...
    if normalized.startswith("/"):
        return True          # /abs, //serveur/partage
    return ".." in PurePosixPath(normalized).parts


def unsafe_archive_entries(names: Iterable[str]) -> list[str]:
    """Liste les entrées d'archive qui tenteraient une évasion. Pure."""
    return [n for n in names if is_unsafe_entry(n)]


def find_7z_exe() -> str | None:
    """Cherche 7z.exe : d'abord bundlé avec l'app, puis sur le système."""
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent.parent.parent
    bundled = base / "assets" / "7z" / "7z.exe"
    if bundled.exists():
        return str(bundled)

    candidates = [
        Path(r"C:\Program Files\7-Zip\7z.exe"),
        Path(r"C:\Program Files (x86)\7-Zip\7z.exe"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    try:
        subprocess.run(
            ["7z"], capture_output=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return "7z"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def list_7z_entries(archive: Path, exe: str) -> list[str]:
    """Noms des entrées d'une archive 7z, via `7z l -slt`.

    `-ba` supprime l'en-tête (sinon l'archive elle-même apparaît comme entrée),
    `-p` fournit un mot de passe vide : sans lui, une archive à en-têtes
    chiffrés ferait attendre 7z.exe sur une invite invisible, et le thread
    d'installation resterait bloqué pour toujours.
    """
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    proc = subprocess.run(
        [exe, "l", "-slt", "-ba", "-p", str(archive)],
        capture_output=True, text=True, errors="replace",
        timeout=_LIST_TIMEOUT_S, **kwargs,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Impossible de lire le contenu de l'archive (7z.exe code {proc.returncode})"
        )
    return [
        line[len("Path = "):].strip()
        for line in proc.stdout.splitlines()
        if line.startswith("Path = ")
    ]


def verify_archive_entries(archive: Path, exe: str) -> None:
    """Refuse une archive dont une entrée sortirait du dossier de destination.

    Contrôle AVANT extraction : c'est le seul moment où l'on peut encore
    empêcher l'écriture. `verify_extracted_paths` ne peut pas jouer ce rôle —
    il parcourt l'intérieur de la destination, donc un fichier écrit dehors
    n'y apparaît par construction jamais. 7-Zip neutralise les `..` de son
    côté, mais c'est un comportement non documenté ici et hors de notre
    contrôle : on le vérifie explicitement.
    """
    entries = list_7z_entries(archive, exe)
    unsafe = unsafe_archive_entries(entries)
    if unsafe:
        log.critical("Archive refusée — %d entrée(s) hors destination : %s",
                     len(unsafe), unsafe[:5])
        raise ValueError(
            f"Archive refusée : {len(unsafe)} entrée(s) tentent de sortir du "
            f"dossier d'installation (première : {unsafe[0]!r})"
        )
    log.info("Contenu de l'archive validé : %d entrées, aucune évasion", len(entries))


def verify_extracted_paths(destination: Path) -> None:
    """Vérifie post-extraction qu'aucun lien ne pointe hors de destination.

    Complément de `verify_archive_entries` : le parcours n'énumère que
    l'intérieur de la destination, il ne peut donc PAS détecter un fichier
    écrit dehors — mais `resolve()` suit les liens, ce qui attrape un lien
    symbolique ou une jonction extraits qui pointeraient ailleurs.

    Ne résout QUE les liens : un `resolve()` par fichier faisait des dizaines de
    milliers d'appels système sur un jeu de plusieurs Go, barre figée à 100 %.
    Un `is_symlink()` est un simple lstat, et un fichier ordinaire ne peut pas
    sortir de la destination puisqu'il y a été écrit.
    """
    dest_resolved = destination.resolve()
    for item in destination.rglob("*"):
        if not item.is_symlink():
            continue
        if not item.resolve().is_relative_to(dest_resolved):
            log.critical("Lien hors destination détecté post-extraction : %s", item)
            raise ValueError(f"Path traversal détecté après extraction : {item}")


def extract_7z_subprocess(
    archive: Path, destination: Path,
    progress: ProgressCb, cancelled: CancelledCb,
) -> None:
    """Extraction via 7z.exe — progression parsée sur stdout (-bsp1), kill sur annulation."""
    exe = find_7z_exe()
    if exe is None:
        raise RuntimeError(
            "7z.exe introuvable — l'extraction de cette archive a échoué.\n"
            "Réinstallez Accio Launcher ou installez 7-Zip depuis https://7-zip.org."
        )

    # Valider le contenu AVANT d'écrire quoi que ce soit sur le disque.
    verify_archive_entries(archive, exe)

    log.info("Extraction via 7z.exe : %s → %s", archive, destination)
    # -snl- : ne jamais matérialiser de lien symbolique (un lien extrait pourrait
    # pointer hors du dossier d'installation et servir de relais d'écriture).
    cmd = [exe, "x", str(archive), f"-o{destination}", "-y", "-bsp1", "-snl-"]
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        # stdin fermé, pour la même raison que le `-p` de `list_7z_entries` :
        # 7z.exe peut demander un mot de passe (archive à contenu chiffré) ou
        # une confirmation que `-y` ne couvre pas. Avec un stdin hérité d'un
        # terminal, il attendrait une saisie que personne ne peut lui donner —
        # la boucle de lecture ci-dessous bloque sur une invite sans retour à
        # la ligne, donc `cancelled()` n'est plus jamais testé. Vérifié : avec
        # DEVNULL, 7z rend la main immédiatement (code 255) au lieu d'attendre.
        stdin=subprocess.DEVNULL,
        text=True, **kwargs,
    )

    try:
        last_pct = 0
        for line in proc.stdout:
            if cancelled():
                proc.kill()
                return
            line = line.strip()
            if line.endswith("%") or "%" in line:
                try:
                    pct_str = line.split("%")[0].strip().split()[-1]
                    pct = int(pct_str)
                    if pct != last_pct:
                        progress(pct)
                        last_pct = pct
                except (ValueError, IndexError):
                    pass

        # NB : ce délai ne borne PAS la durée d'extraction — on n'arrive ici
        # qu'une fois stdout épuisé, donc une fois 7z.exe terminé. Il ne couvre
        # que le temps de reap du processus. C'est le bon comportement (un jeu
        # de 8 Go doit pouvoir prendre le temps qu'il faut) ; c'est le message
        # d'erreur qui prétendait le contraire.
        ret = proc.wait(timeout=_REAP_TIMEOUT_S)
        if ret != 0:
            raise RuntimeError(f"7z.exe a échoué (code {ret})")
        progress(100)
        verify_extracted_paths(destination)
        log.info("Extraction 7z.exe terminée")
    except subprocess.TimeoutExpired:
        log.error("7z.exe ne rend pas la main après la fin de son flux, kill du processus")
        proc.kill()
        proc.wait(timeout=10)
        raise RuntimeError("7z.exe ne s'est pas terminé après la fin de l'extraction")
    finally:
        if proc.stdout:
            proc.stdout.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)


def extract_7z(archive: Path, destination: Path,
               progress: ProgressCb, cancelled: CancelledCb) -> None:
    """Extrait une archive .7z (ou multi-volumes .7z.001) via 7z.exe."""
    extract_7z_subprocess(archive, destination, progress, cancelled)


def extract_zip(archive: Path, destination: Path,
                progress: ProgressCb, cancelled: CancelledCb) -> None:
    """Extrait une archive .zip avec progression et protection Zip Slip."""
    with zipfile.ZipFile(archive, "r") as zf:
        members = zf.infolist()
        total = len(members)
        if total == 0:
            return

        # Valider TOUTES les entrées avant d'en écrire une seule — même contrat
        # que verify_archive_entries côté 7z.
        unsafe = [m.filename for m in members if is_unsafe_entry(m.filename)
                  or not check_path_traversal(destination, m.filename)]
        if unsafe:
            log.critical("Archive zip refusée — %d entrée(s) hors destination : %s",
                         len(unsafe), unsafe[:5])
            raise ValueError(
                f"Archive refusée : {len(unsafe)} entrée(s) tentent de sortir du "
                f"dossier d'installation (première : {unsafe[0]!r})"
            )

        for i, member in enumerate(members, 1):
            if cancelled():
                return
            zf.extract(member, destination)
            progress(i * 100 // total)
