"""vgmstream : les sons d'EA que FFmpeg ne lit pas.

HP5 et HP6 encodent leur musique en EALayer3, HP7 et HP8 leurs sons en Wwise
Vorbis : le lecteur Qt (FFmpeg) n'ouvre ni l'un ni l'autre. vgmstream
(r2117, licence ISC, `assets/vgmstream/License.txt`) les convertit en WAV,
relu ensuite comme n'importe quel fichier. Exécution autorisée par Ludo le
2026-10-24, binaire officiel vérifié par son empreinte SHA-256.

Mesures (2026-10-24) : une minute de HP5 en 0,18 s, huit minutes de HP7 en
1,4 s (90 Mo de WAV). Toutes les DLL livrées sont liées à l'exécutable : il
refuse de démarrer sans `libspeex-1.dll` même pour de l'EALayer3.

Sous Linux, rien n'est embarqué : le `vgmstream-cli` du système s'il existe.
Aucune fonction ne lève : sans vgmstream ou sur un échec, None.
"""

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

_SANS_FENETRE = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
_DELAI_S = 60


def _base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent.parent


def executable() -> Path | None:
    """vgmstream-cli : l'embarqué sous Windows, celui du système sous Linux (chemin ABSOLU)."""
    if sys.platform == "win32":
        embarque = _base() / "assets" / "vgmstream" / "vgmstream-cli.exe"
        return embarque if embarque.is_file() else None
    trouve = shutil.which("vgmstream-cli")
    return Path(os.path.abspath(trouve)) if trouve else None


def disponible() -> bool:
    return executable() is not None


def convertir(source: Path, cible: Path) -> Path | None:
    """Convertit `source` en WAV à `cible` (écriture atomique) ; une conversion déjà faite resservira.

    Une cible plus récente que la source est gardée telle quelle.
    """
    try:
        if cible.is_file() and cible.stat().st_mtime >= source.stat().st_mtime:
            return cible
    except OSError:
        return None
    exe = executable()
    if exe is None:
        return None
    tmp: str | None = None
    try:
        cible.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=cible.parent, suffix=".accio-tmp.wav")
        os.close(fd)
        # Chemin absolu de l'exécutable, liste d'arguments, aucun shell.
        proc = subprocess.run(  # nosec B603
            [str(exe), "-o", tmp, str(source)],
            capture_output=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
            timeout=_DELAI_S, creationflags=_SANS_FENETRE,
        )
        if proc.returncode != 0 or os.path.getsize(tmp) <= 44:
            log.warning("vgmstream, %s non converti (code %s) : %s", source.name, proc.returncode,
                        proc.stderr.strip()[-300:])
            return None
        os.replace(tmp, cible)
        tmp = None
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("vgmstream, conversion de %s échouée : %s", source, exc)
        return None
    finally:
        if tmp is not None:
            try:
                os.remove(tmp)               # notre propre fichier temporaire
            except OSError:
                pass
    return cible
