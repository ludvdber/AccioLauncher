import hashlib
import logging
import re
import threading
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from PyQt6.QtCore import QThread, pyqtSignal

log = logging.getLogger(__name__)

# httpx est importé paresseusement dans les méthodes du thread (~70 ms d'import
# évités au démarrage du launcher — il ne sert qu'une fois un téléchargement lancé).

MAX_RETRIES = 3
BACKOFF_BASE = 1  # secondes
CHUNK_SIZE = 256 * 1024  # 256 Ko
SIZE_OVERHEAD_FACTOR = 1.5  # tolérance vs size_mb du catalog avant abandon

_ALLOWED_SCHEMES = {"https"}
_TIMEOUT_KW = {"connect": 15.0, "read": 120.0, "write": 30.0, "pool": 10.0}

# Suffixe de volume d'une archive multi-parts : « .001 », « .002 »…
_MOTIF_VOLUME = re.compile(r"\.\d{3}")


def _numero_volume(url: str, index: int) -> str:
    """Suffixe de volume à donner à la part `index`, d'après son URL. Pure.

    On reprend le numéro que porte l'asset (« .002 ») plutôt que de compter
    nous-mêmes : c'est lui que 7z.exe lira, et un catalogue qui listerait ses
    parts dans le désordre ne doit pas se retrouver renuméroté en silence. Le
    repli sur le rang ne sert qu'aux URLs sans numéro exploitable, où il faut
    bien produire QUELQUE chose de séquentiel.
    """
    suffixe = Path(url.rsplit("/", 1)[-1]).suffix
    return suffixe if _MOTIF_VOLUME.fullmatch(suffixe) else f".{index + 1:03d}"


def _validate_url(url: str) -> None:
    """Vérifie que l'URL utilise un protocole autorisé."""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"Protocole non autorisé : {parsed.scheme!r} (attendu https)")
    if not parsed.hostname:
        raise ValueError(f"URL invalide (pas de hostname) : {url!r}")


def _ensure_response_https(response) -> None:
    """Rejette une réponse dont l'URL FINALE n'est pas https.

    `follow_redirects=True` suit un 3xx https→http silencieusement (attaque de
    rétrogradation) ; on ne valide qu'au départ, donc on re-vérifie l'arrivée.
    """
    scheme = getattr(getattr(response, "url", None), "scheme", "https")
    if scheme not in _ALLOWED_SCHEMES:
        raise OSError(f"Redirection vers un protocole non sûr : {scheme!r} (attendu https)")


def file_sha256(path: Path, cancelled: Callable[[], bool] | None = None) -> str:
    """Empreinte SHA-256 d'un fichier (lecture par blocs de 1 Mio).

    Retourne "" si annulé en cours de calcul.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            if cancelled is not None and cancelled():
                return ""
            h.update(chunk)
    return h.hexdigest()


class Downloader(QThread):
    """Télécharge une archive (simple ou multi-parts) en arrière-plan."""

    progress = pyqtSignal(int, int)   # (octets_téléchargés, octets_total)
    # NB : pas `finished` — ça masquerait le signal natif QThread.finished
    # (utilisé par GameOperations pour le nettoyage différé des threads annulés).
    download_finished = pyqtSignal(str)  # chemin du fichier téléchargé
    error = pyqtSignal(str)              # message d'erreur
    part_info = pyqtSignal(int, int)     # (part_courante, total_parts) — multi-parts uniquement
    verifying = pyqtSignal()             # vérification SHA-256 d'un fichier complet en cours

    def __init__(
        self,
        url: str | None,
        destination: Path,
        parts: list[str] | None = None,
        expected_size_mb: int = 0,
        expected_sha256: str | None = None,
        expected_sha256_parts: list[str] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.url = url
        self.destination = destination
        self.parts = parts
        self.expected_sha256 = expected_sha256
        self.expected_sha256_parts = expected_sha256_parts or []
        # Cap = expected_size_mb * SIZE_OVERHEAD_FACTOR. 0 = pas de cap (rétro-compat).
        self._max_total_bytes = (
            int(expected_size_mb * SIZE_OVERHEAD_FACTOR * 1024 * 1024)
            if expected_size_mb > 0 else 0
        )
        self._cancel_event = threading.Event()
        self._last_emit = 0.0

    def _verify_sha256(self, path: Path, expected: str | None) -> bool:
        """Vérifie l'empreinte d'un fichier complet (relecture intégrale).

        Ne sert plus qu'aux parts déjà en cache — les téléchargements frais sont
        hachés incrémentalement pendant le stream (aucune pause à 100 %).
        """
        if not expected:
            return True
        self.verifying.emit()
        log.info("Vérification SHA-256 de %s…", path.name)
        actual = file_sha256(path, cancelled=lambda: self._cancelled)
        if self._cancelled:
            return False
        if actual.lower() != expected.lower():
            log.error("SHA-256 invalide pour %s : attendu %s, obtenu %s", path, expected, actual)
            return False
        log.info("SHA-256 conforme : %s", path.name)
        return True

    @property
    def _cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def cancel(self) -> None:
        self._cancel_event.set()
        log.info("Annulation du téléchargement demandée")

    def run(self) -> None:
        try:
            if self.parts:
                self._run_multipart()
            elif self.url:
                self._run_single()
            else:
                self.error.emit("Aucune URL de téléchargement.")
        except Exception as exc:
            log.exception("Erreur inattendue dans le downloader")
            self.error.emit(f"Erreur : {exc}")

    # ─── Téléchargement simple (fichier unique) ───

    def _run_single(self) -> None:
        import httpx  # import différé (thread) — voir en-tête de module

        try:
            _validate_url(self.url)
        except ValueError as exc:
            self.error.emit(str(exc))
            return

        part_path = self.destination.with_suffix(self.destination.suffix + ".part")
        part_path.parent.mkdir(parents=True, exist_ok=True)

        for attempt in range(1, MAX_RETRIES + 1):
            if self._cancelled:
                return
            try:
                digest = self._download_stream(
                    self.url, part_path, global_offset=0, global_total=0,
                    compute_sha256=bool(self.expected_sha256),
                )
                if self._cancelled:
                    return
                if self.expected_sha256 and (digest or "").lower() != self.expected_sha256.lower():
                    # Fichier corrompu : repartir de zéro (OSError → boucle de retry)
                    log.error("SHA-256 invalide pour %s : attendu %s, obtenu %s",
                              part_path, self.expected_sha256, digest)
                    part_path.unlink(missing_ok=True)
                    raise OSError("empreinte SHA-256 invalide (fichier corrompu)")
                part_path.replace(self.destination)
                log.info("Téléchargement terminé : %s", self.destination)
                self.download_finished.emit(str(self.destination))
                return
            except (httpx.HTTPError, OSError) as exc:
                log.warning("Tentative %d/%d échouée : %s", attempt, MAX_RETRIES, exc)
                if attempt < MAX_RETRIES:
                    wait = BACKOFF_BASE * (2 ** (attempt - 1))
                    time.sleep(wait)

        self.error.emit("Échec du téléchargement après plusieurs tentatives.")

    # ─── Téléchargement multi-parts ───

    def _migrer_part_heritee(self, url: str, part_dest: Path, index: int) -> None:
        """Traite une part restée sous son ANCIEN nom, tiré de l'URL.

        Jusqu'au 2026-08-21, une part était rangée sous le nom de son asset
        (« hp5.7z.001 »), qui ne porte pas la version : les deux versions de HP5
        publient des assets de même nom, si bien qu'une part de la v1.0 laissée
        dans le cache était reprise telle quelle pour la v1.1 — et l'ancien jeu
        s'installait sous le numéro du nouveau, sans un mot. Les parts portent
        désormais le nom de la destination, qui porte la version.

        Reste le fichier hérité. Sa provenance est justement ce qu'on ne sait
        pas : le RÉUTILISER serait rejouer le défaut. Deux issues seulement —
        on l'adopte si son empreinte prouve qu'il appartient bien à la version
        demandée (et on épargne alors jusqu'à 2 Go de téléchargement), sinon on
        le supprime, parce qu'un fichier dont personne ne peut dire à quoi il
        correspond n'a rien à faire dans un cache.
        """
        heritee = part_dest.parent / Path(url.rsplit("/", 1)[-1]).name
        if heritee == part_dest or part_dest.exists() or not heritee.exists():
            return
        attendu = (self.expected_sha256_parts[index]
                   if index < len(self.expected_sha256_parts) else None)
        if attendu and self._verify_sha256(heritee, attendu):
            log.info("Part héritée adoptée (empreinte conforme) : %s → %s",
                     heritee.name, part_dest.name)
            heritee.replace(part_dest)
            return
        if self._cancelled:
            return
        log.info("Part héritée de provenance inconnue, supprimée : %s", heritee.name)
        try:
            heritee.unlink(missing_ok=True)
        except OSError as exc:
            log.warning("Impossible de supprimer %s : %s", heritee, exc)

    def _run_multipart(self) -> None:
        import httpx  # import différé (thread) — voir en-tête de module

        for url in self.parts:
            try:
                _validate_url(url)
            except ValueError as exc:
                self.error.emit(str(exc))
                return

        total_parts = len(self.parts)
        part_paths: list[Path] = []
        cache_dir = self.destination.parent
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Étape 1 : télécharger chaque part
        for i, url in enumerate(self.parts):
            if self._cancelled:
                return

            part_dest = cache_dir / (self.destination.name + _numero_volume(url, i))
            self._migrer_part_heritee(url, part_dest, i)
            part_paths.append(part_dest)
            part_tmp = part_dest.with_suffix(part_dest.suffix + ".part")

            self.part_info.emit(i + 1, total_parts)

            expected_part_hash = (
                self.expected_sha256_parts[i]
                if i < len(self.expected_sha256_parts) else None
            )

            for attempt in range(1, MAX_RETRIES + 1):
                if self._cancelled:
                    return
                # Si la part est déjà téléchargée complètement (et conforme), skip
                if part_dest.exists():
                    if self._verify_sha256(part_dest, expected_part_hash):
                        log.info("Part déjà présente : %s", part_dest)
                        break
                    if self._cancelled:
                        return
                    log.warning("Part en cache corrompue, re-téléchargement : %s", part_dest)
                    part_dest.unlink(missing_ok=True)
                try:
                    digest = self._download_stream(
                        url, part_tmp,
                        global_offset=i, global_total=total_parts,
                        compute_sha256=bool(expected_part_hash),
                    )
                    if self._cancelled:
                        return
                    if expected_part_hash and (digest or "").lower() != expected_part_hash.lower():
                        log.error("SHA-256 invalide pour %s : attendu %s, obtenu %s",
                                  part_tmp, expected_part_hash, digest)
                        part_tmp.unlink(missing_ok=True)
                        raise OSError("empreinte SHA-256 invalide (part corrompue)")
                    part_tmp.replace(part_dest)
                    log.info("Part %d/%d terminée : %s", i + 1, total_parts, part_dest)
                    break
                except (httpx.HTTPError, OSError) as exc:
                    log.warning("Part %d tentative %d/%d échouée : %s", i + 1, attempt, MAX_RETRIES, exc)
                    if attempt < MAX_RETRIES:
                        wait = BACKOFF_BASE * (2 ** (attempt - 1))
                        time.sleep(wait)
            else:
                # Nettoyer le fichier .part temporaire de la part échouée
                part_tmp.unlink(missing_ok=True)
                self.error.emit(f"Échec du téléchargement de la partie {i + 1}/{total_parts}.")
                return

        if self._cancelled:
            return

        # 7z.exe lit nativement les archives multi-volumes : on émet directement
        # la première part (.001) — pas de concaténation (gain disque + temps).
        # L'intégrité est couverte par les hash par part (sha256_parts).
        if self.expected_sha256 and not self.expected_sha256_parts:
            log.warning("sha256 global ignoré pour un téléchargement multi-parts — "
                        "utiliser sha256_parts dans le catalogue")
        first_part = part_paths[0]
        log.info("Téléchargement multi-parts terminé : %s (%d parts)", first_part, total_parts)
        self.download_finished.emit(str(first_part))

    # ─── Streaming avec reprise ───

    def _hash_existing(self, part_path: Path, size: int) -> "hashlib._Hash | None":
        """Hache le préfixe déjà téléchargé avant une reprise (lecture disque rapide).

        Retourne None si annulé en cours de lecture.
        """
        h = hashlib.sha256()
        with open(part_path, "rb") as f:
            remaining = size
            while remaining > 0:
                chunk = f.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                if self._cancelled:
                    return None
                h.update(chunk)
                remaining -= len(chunk)
        return h

    def _download_stream(
        self, url: str, part_path: Path,
        global_offset: int = 0, global_total: int = 0,
        compute_sha256: bool = False,
    ) -> str | None:
        """Télécharge en streaming avec reprise via HTTP Range.

        `compute_sha256=True` → hache les octets AU FIL du stream (préfixe repris
        inclus) et retourne l'empreinte hex — plus de relecture intégrale (et donc
        plus d'UI figée à 100 %) après le téléchargement. Retourne None si le
        hash n'est pas demandé ou en cas d'annulation.
        """
        import httpx  # import différé (thread) — voir en-tête de module

        timeout = httpx.Timeout(**_TIMEOUT_KW)
        downloaded = part_path.stat().st_size if part_path.exists() else 0
        headers: dict[str, str] = {}
        hasher = None
        if downloaded > 0:
            headers["Range"] = f"bytes={downloaded}-"
            log.info("Reprise du téléchargement à %d octets", downloaded)
            if compute_sha256:
                hasher = self._hash_existing(part_path, downloaded)
                if hasher is None:  # annulé pendant le hachage du préfixe
                    return None
        elif compute_sha256:
            hasher = hashlib.sha256()

        needs_retry = False
        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            with client.stream("GET", url, headers=headers) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 416 and downloaded > 0:
                        log.warning("HTTP 416 : fichier .part corrompu, suppression et reprise")
                        part_path.unlink(missing_ok=True)
                        needs_retry = True
                    else:
                        raise

                if not needs_retry:
                    _ensure_response_https(response)
                    raw_length = response.headers.get("content-length", "")
                    try:
                        content_length = int(raw_length)
                    except (ValueError, TypeError):
                        content_length = 0

                    if response.status_code == 206:
                        total = downloaded + content_length
                    else:
                        # Le serveur a ignoré le Range → contenu complet, repartir de zéro
                        total = content_length
                        downloaded = 0
                        if compute_sha256:
                            hasher = hashlib.sha256()

                    # Cap : refuser si le serveur annonce > expected * 1.5
                    if self._max_total_bytes and total > self._max_total_bytes:
                        raise OSError(
                            f"Taille annoncée ({total} octets) dépasse la limite "
                            f"({self._max_total_bytes} octets)"
                        )

                    mode = "ab" if response.status_code == 206 else "wb"
                    with open(part_path, mode) as f:
                        for chunk in response.iter_bytes(CHUNK_SIZE):
                            if self._cancelled:
                                return None
                            f.write(chunk)
                            if hasher is not None:
                                hasher.update(chunk)
                            downloaded += len(chunk)
                            # Cap en cours de stream (Content-Length manquant ou menteur)
                            if self._max_total_bytes and downloaded > self._max_total_bytes:
                                raise OSError(
                                    f"Téléchargement dépasse la limite ({downloaded} > "
                                    f"{self._max_total_bytes} octets)"
                                )
                            now = time.monotonic()
                            if now - self._last_emit >= 0.1:
                                self.progress.emit(downloaded, total)
                                self._last_emit = now
                    self.progress.emit(downloaded, total)  # final
                    return hasher.hexdigest() if hasher is not None else None

        if not needs_retry:
            return None

        # Retry une seule fois après HTTP 416 (sans Range)
        hasher = hashlib.sha256() if compute_sha256 else None
        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                _ensure_response_https(response)
                raw_length = response.headers.get("content-length", "")
                try:
                    total = int(raw_length)
                except (ValueError, TypeError):
                    total = 0
                # Même cap que le chemin nominal : un retry 416 ne doit pas être
                # une porte dérobée pour un fichier surdimensionné.
                if self._max_total_bytes and total > self._max_total_bytes:
                    raise OSError(
                        f"Taille annoncée ({total} octets) dépasse la limite "
                        f"({self._max_total_bytes} octets)"
                    )
                with open(part_path, "wb") as f:
                    downloaded = 0
                    for chunk in response.iter_bytes(CHUNK_SIZE):
                        if self._cancelled:
                            return None
                        f.write(chunk)
                        if hasher is not None:
                            hasher.update(chunk)
                        downloaded += len(chunk)
                        if self._max_total_bytes and downloaded > self._max_total_bytes:
                            raise OSError(
                                f"Téléchargement dépasse la limite ({downloaded} > "
                                f"{self._max_total_bytes} octets)"
                            )
                        now = time.monotonic()
                        if now - self._last_emit >= 0.1:
                            self.progress.emit(downloaded, total)
                            self._last_emit = now
                self.progress.emit(downloaded, total)  # final
        return hasher.hexdigest() if hasher is not None else None
