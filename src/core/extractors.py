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
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

# Callbacks injectés depuis l'Installer.
ProgressCb = Callable[[int], None]
CancelledCb = Callable[[], bool]


def check_path_traversal(destination: Path, member_name: str) -> bool:
    """Vérifie qu'un fichier extrait ne sort pas du dossier de destination (Zip Slip)."""
    target = (destination / member_name).resolve()
    return target.is_relative_to(destination.resolve())


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


def verify_extracted_paths(destination: Path) -> None:
    """Vérifie post-extraction que tous les fichiers sont sous destination."""
    dest_resolved = destination.resolve()
    for item in destination.rglob("*"):
        if not item.resolve().is_relative_to(dest_resolved):
            log.critical("Path traversal détecté post-extraction : %s", item)
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

    log.info("Extraction via 7z.exe : %s → %s", archive, destination)
    cmd = [exe, "x", str(archive), f"-o{destination}", "-y", "-bsp1"]
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
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

        ret = proc.wait(timeout=300)
        if ret != 0:
            raise RuntimeError(f"7z.exe a échoué (code {ret})")
        progress(100)
        verify_extracted_paths(destination)
        log.info("Extraction 7z.exe terminée")
    except subprocess.TimeoutExpired:
        log.error("7z.exe n'a pas terminé dans le délai imparti, kill du processus")
        proc.kill()
        proc.wait(timeout=10)
        raise RuntimeError("7z.exe a dépassé le temps d'extraction maximum (5 min)")
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

        for i, member in enumerate(members, 1):
            if cancelled():
                return
            if not check_path_traversal(destination, member.filename):
                log.warning("Zip Slip détecté, entrée ignorée : %s", member.filename)
                continue
            zf.extract(member, destination)
            progress(i * 100 // total)
