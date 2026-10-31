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

**Téléchargé à la première écoute depuis la 1.3.1** (2026-10-28) : il pesait
4,3 Mo dans l'exe pour les seuls joueurs de HP5 et HP6. La release officielle
(4,5 Mo) est vérifiée par l'empreinte du zip PUIS de chaque fichier, et posée
dans `_Launcher/outils/vgmstream-r2117/` avec sa licence. Depuis les sources,
`assets/vgmstream/` (posé par `build/vgmstream.py`) sert encore.
"""

import hashlib
import io
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

log = logging.getLogger(__name__)

_SANS_FENETRE = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
_DELAI_S = 60

VERSION = "r2117"
URL = f"https://github.com/vgmstream/vgmstream/releases/download/{VERSION}/vgmstream-win64.zip"
EMPREINTE_ZIP = "6c4a8a3813864fefed081bbd337dbc0ad93bf88e0b92f5db98d7ab258b22dc6c"
TAILLE_ZIP = 4_468_180   # octets : le poids annoncé avant de télécharger (4,5 Mo)
# Nom dans le zip → (nom posé, empreinte SHA-256). La licence ISC voyage avec le binaire.
FICHIERS: dict[str, tuple[str, str]] = {
    "avcodec-vgmstream-59.dll": ("avcodec-vgmstream-59.dll",
                                 "4d6cf54e7b3c26ef06e95bdb515a10d1e1bed3ec1ffd87ec3e5c4fbcd2a883f6"),
    "avformat-vgmstream-59.dll": ("avformat-vgmstream-59.dll",
                                  "0dde66ea268cccb67b1aa219c1ce879602b839e561a79a00c8215e2688f1a4b2"),
    "avutil-vgmstream-57.dll": ("avutil-vgmstream-57.dll",
                                "a999856c17cfdce3c22b92b6640a7ada6c4ab4c3c6841a863770b72fa0bc19b4"),
    "libatrac9.dll": ("libatrac9.dll", "fe82f1ae13a798337e03942c35351997c23caadb5eb0c6b7a2dc2a521ed8b02e"),
    "libcelt-0061.dll": ("libcelt-0061.dll", "542254723d9100f91cbf18e41c4aff80287c22a9859e9e545c413d984df440ad"),
    "libcelt-0110.dll": ("libcelt-0110.dll", "bfcc51d865bb3b6a2793381bf535f23ec423feb722b46333fa8556ccdcafa61a"),
    "libg719_decode.dll": ("libg719_decode.dll",
                           "aad61f205ce1f1b61285f6b37b90a331ec8c6ae2f94f361714dc21a12c236960"),
    "libmpg123-0.dll": ("libmpg123-0.dll", "db9eb1d91b8eb9f47b0968201dbf6c51a9627e539a78afd9ad5f59c5d18fe4df"),
    "libspeex-1.dll": ("libspeex-1.dll", "04dbc85fcec6c54671535bf39937a70f2dd040a81ad670a0b84de6ca17b39bff"),
    "libvorbis.dll": ("libvorbis.dll", "5f330a20b19b3c70dc43eedcc95891e65940fca04a77155c573efcdd4c2ca665"),
    "swresample-vgmstream-4.dll": ("swresample-vgmstream-4.dll",
                                   "688a81d31ef98a9a6143e1075b2f4c5b79bdfa51e7a14d50d662a0e916dac739"),
    "vgmstream-cli.exe": ("vgmstream-cli.exe", "29df08c557ada8269c92a6abfe3886ad2f65849b0b26ba78a0819b363bbc5b85"),
    "COPYING": ("License.txt", "fcc26d35c4c4365e31f21734f846e4ee362ff0b57ba696085605a7b4768d8763"),
}
_EXE = "vgmstream-cli.exe"


def _base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent.parent


def dossier_installe() -> Path:
    """Où le launcher pose vgmstream téléchargé (résolu à l'appel : les tests le déplacent)."""
    from src.core import config
    return config.LAUNCHER_DATA_PATH / "outils" / f"vgmstream-{VERSION}"


def executable() -> Path | None:
    """vgmstream-cli : le téléchargé, sinon celui des sources sous Windows ; celui du système sous Linux."""
    if sys.platform == "win32":
        for dossier in (dossier_installe(), _base() / "assets" / "vgmstream"):
            if (dossier / _EXE).is_file():
                return dossier / _EXE
        return None
    trouve = shutil.which("vgmstream-cli")
    return Path(os.path.abspath(trouve)) if trouve else None


def a_telecharger() -> bool:
    """Windows sans vgmstream : la musique de HP5 et HP6 attend son téléchargement."""
    return sys.platform == "win32" and executable() is None


def _empreinte(donnees: bytes) -> str:
    return hashlib.sha256(donnees).hexdigest()


def installer(archive: Path) -> bool:
    """Pose le zip officiel téléchargé, chaque fichier vérifié ; False sans rien poser au moindre écart.

    Écrit d'abord dans un dossier voisin puis le renomme : un dossier à moitié
    posé ne passe jamais pour un vgmstream installé.
    """
    try:
        donnees = archive.read_bytes()
        if _empreinte(donnees) != EMPREINTE_ZIP:
            log.warning("vgmstream : empreinte du zip inattendue, rien n'est posé")
            return False
        with zipfile.ZipFile(io.BytesIO(donnees)) as zf:
            contenus = {pose: zf.read(nom) for nom, (pose, _e) in FICHIERS.items()}
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        log.warning("vgmstream : zip illisible (%s), rien n'est posé", exc)
        return False
    attendues = {pose: e for pose, e in FICHIERS.values()}
    for pose, contenu in contenus.items():
        if _empreinte(contenu) != attendues[pose]:
            log.warning("vgmstream : empreinte de %s inattendue, rien n'est posé", pose)
            return False
    cible = dossier_installe()
    provisoire = cible.with_name(cible.name + ".accio-tmp")
    try:
        shutil.rmtree(provisoire, ignore_errors=True)   # notre propre reste d'un essai interrompu
        provisoire.mkdir(parents=True)
        for pose, contenu in contenus.items():
            (provisoire / pose).write_bytes(contenu)
        if cible.exists():
            shutil.rmtree(cible)
        provisoire.rename(cible)
    except OSError as exc:
        log.warning("vgmstream : pose dans %s échouée : %s", cible, exc)
        shutil.rmtree(provisoire, ignore_errors=True)
        return False
    log.info("vgmstream %s posé dans %s, empreintes vérifiées", VERSION, cible)
    return True


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
        proc = subprocess.run(  # nosec B603  # noqa: S603
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
