"""Vérification des mises à jour du catalogue et du launcher en arrière-plan."""

import json
import logging
import re

from PyQt6.QtCore import QThread, pyqtSignal

from src.core.config import APP_VERSION, LOCAL_CATALOG_PATH
from src.core.game_data import _parse_catalog
from src.core.version_utils import compare_versions, update_disponible

log = logging.getLogger(__name__)

# httpx est importé paresseusement dans les méthodes du thread (~70 ms d'import
# évités au démarrage — partagé avec le Downloader, le premier des deux paie).
_TIMEOUT_KW = {"connect": 5.0, "read": 5.0, "write": 5.0, "pool": 5.0}
_LAUNCHER_API = "https://api.github.com/repos/ludvdber/AccioLauncher/releases/latest"
_GAMES_RELEASES_API = "https://api.github.com/repos/ludvdber/accio-launcher-games/releases?per_page=100"
_LOCAL_CATALOG_PATH = LOCAL_CATALOG_PATH


_SHA256_PREFIX = "sha256:"

# Plafond du catalogue distant. Le catalogue embarqué pèse ~30 Ko ; cette borne
# laisse vingt fois plus de jeux et de langues, tout en empêchant une réponse
# aberrante de saturer la mémoire puis le disque.
_CATALOG_MAX_BYTES = 4 * 1024 * 1024


def _assets_publies(releases: list[dict]):
    """Parcourt les assets exploitables des releases : (url, asset).

    Les trois extracteurs qui suivent (empreintes, tailles, compteurs) lisaient
    la MÊME réponse GitHub avec le MÊME préambule recopié trois fois. Le
    troisième portait même le commentaire « mêmes gardes que ci-dessus » : le
    dédoublement était connu, documenté, et laissé en place — c'est-à-dire une
    règle de sécurité tenue par la vigilance de qui relit.

    Ces gardes ne sont pas décoratives. Sans elles, une release nulle ou un
    asset non-objet levait `AttributeError`, qui n'est PAS dans le tuple
    `except` de l'appelant : l'exception sortait de `QThread.run()` et
    l'utilisateur recevait un rapport de plantage pour une réponse HTTP
    inattendue — portail captif, proxy, page d'erreur.

    L'URL est exigée non vide ET de type `str` : c'est la plus stricte des trois
    variantes d'origine, et elle évite d'indexer un dictionnaire sur un nombre
    le jour où l'API renverrait autre chose.
    """
    for rel in releases:
        if not isinstance(rel, dict):
            continue
        for asset in rel.get("assets", []) or []:
            if not isinstance(asset, dict):
                continue
            url = asset.get("browser_download_url", "")
            if url and isinstance(url, str):
                yield url, asset


def extract_asset_digests(releases: list[dict]) -> dict[str, str]:
    """URL d'asset → empreinte SHA-256 (hex), depuis les releases GitHub.

    GitHub calcule et publie lui-même l'empreinte de chaque asset (champ
    `digest`, format « sha256:<hex> »). La récupérer ici évite de la recopier
    à la main dans games.json à chaque release — une empreinte fausse ou
    oubliée serait pire que pas d'empreinte du tout, puisqu'elle inspirerait
    une confiance qu'elle ne mérite pas.

    Aucune requête supplémentaire : la réponse est déjà téléchargée pour les
    compteurs de téléchargement.

    Les entrées non conformes (algorithme inconnu, longueur inattendue) sont
    ignorées silencieusement — un asset sans empreinte exploitable doit
    dégrader vers « pas de vérification », jamais vers un échec de download.
    """
    digests: dict[str, str] = {}
    for url, asset in _assets_publies(releases):
        raw = asset.get("digest") or ""
        if not isinstance(raw, str) or not raw.startswith(_SHA256_PREFIX):
            continue
        hexa = raw[len(_SHA256_PREFIX):].strip().lower()
        if len(hexa) == 64 and all(c in "0123456789abcdef" for c in hexa):
            digests[url] = hexa
    return digests


def extract_asset_sizes(releases: list[dict]) -> dict[str, int]:
    """URL d'asset → taille RÉELLE en octets, depuis les releases GitHub. Pure.

    Le catalogue déclare un `size_mb` qui s'est révélé être la taille du jeu
    UNE FOIS INSTALLÉ, pas celle de l'archive : mesuré le 2026-08-21, il vaut de
    1,77 à 2,30 fois le téléchargement réel (HP3 annonçait « 775 Mo » pour
    337 Mo). Le bouton promettait donc presque le double de ce que la barre de
    progression comptait ensuite — l'interface se contredisait d'un écran à
    l'autre.

    Plutôt que de demander qu'on recopie la bonne valeur à la main dans
    `games.json` — un chiffre saisi à la main se périme au premier réenrobage —
    on prend celui que GitHub publie, dans la MÊME réponse que les compteurs et
    les empreintes : aucune requête supplémentaire. Absent (API injoignable,
    archive hébergée ailleurs) → l'appelant retombe sur `size_mb`, comme avant.
    """
    tailles: dict[str, int] = {}
    for url, asset in _assets_publies(releases):
        taille = asset.get("size")
        # `not isinstance(taille, bool)` : en Python `True` EST un entier, et
        # `tailles[url] = True` passerait ensuite pour une taille de 1 octet.
        if isinstance(taille, int) and not isinstance(taille, bool) and taille > 0:
            tailles[url] = taille
    return tailles


def aggregate_download_counts(
    releases: list[dict], games_asset_urls: dict[str, list[list[str]]],
) -> dict[str, int]:
    """Compte les téléchargements GitHub par jeu, TOUTES versions confondues.

    `games_asset_urls` : game_id → liste de versions → liste d'URLs d'assets
    (download_url + download_parts). Une version multi-parts compte chaque part
    séparément côté GitHub : on prend le MAX des parts (≈ téléchargements
    complets de cette version), puis on SOMME les versions du jeu.
    """
    url_counts: dict[str, int] = {}
    for url, asset in _assets_publies(releases):
        try:
            url_counts[url] = max(0, int(asset.get("download_count", 0) or 0))
        except (TypeError, ValueError):
            url_counts[url] = 0

    totals: dict[str, int] = {}
    for game_id, versions in games_asset_urls.items():
        total = 0
        for urls in versions:
            counts = [url_counts.get(u, 0) for u in urls if u]
            if counts:
                total += max(counts)
        if total > 0:
            totals[game_id] = total
    return totals


def _releases_api_from_catalog_url(catalog_url: str) -> str:
    """Déduit l'API releases du repo des jeux depuis l'URL raw du catalogue."""
    m = re.search(r"raw\.githubusercontent\.com/([^/]+)/([^/]+)/", catalog_url or "")
    if m:
        return f"https://api.github.com/repos/{m.group(1)}/{m.group(2)}/releases?per_page=100"
    return _GAMES_RELEASES_API


class UpdateChecker(QThread):
    """Vérifie les mises à jour du catalogue et du launcher en arrière-plan."""

    catalog_updated = pyqtSignal(object)        # Catalog
    launcher_update = pyqtSignal(str, str, str, str)  # (version, url_release, url_asset_exe, sha256 hex)
    update_counts = pyqtSignal(int)             # nombre de jeux avec mise à jour dispo
    download_counts = pyqtSignal(object)        # dict game_id → téléchargements GitHub cumulés
    asset_digests = pyqtSignal(object)          # dict url_asset → sha256 hex (publié par GitHub)
    asset_sizes = pyqtSignal(object)            # dict url_asset → taille réelle en octets
    network_status = pyqtSignal(bool)           # False = aucun serveur joignable (hors ligne)

    def __init__(self, catalog_url: str, current_catalog_version: str,
                 installed_versions: dict[str, str],
                 games_asset_urls: dict[str, list[list[str]]] | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self._catalog_url = catalog_url
        self._current_version = current_catalog_version
        self._installed_versions = dict(installed_versions)  # snapshot thread-safe
        self._games_asset_urls = games_asset_urls or {}      # snapshot (compteur ⬇)
        # Diagnostic réseau. `_contact` passe à True dès qu'un serveur RÉPOND,
        # même par une erreur HTTP : un 403 (rate limit) ou un 404 prouvent que
        # la connexion fonctionne. Seules les erreurs de transport (DNS, connexion
        # refusée, timeout) comptent comme « injoignable ».
        self._contact = False
        self._transport_errors = 0

    def run(self) -> None:
        """Trois étapes réseau séquentielles, interruptibles entre chacune.

        `requestInterruption()` ne peut pas avorter une requête HTTP en cours
        (httpx n'expose pas d'annulation), mais tester le drapeau entre les
        étapes ramène le pire cas d'une trentaine de secondes (3 requêtes) à
        une dizaine (1 requête en vol) — la fenêtre pendant laquelle une
        fermeture de fenêtre peut détruire un thread encore actif.
        """
        self._contact = False
        self._transport_errors = 0
        self._check_catalog()
        if self.isInterruptionRequested():
            log.info("Vérification des mises à jour interrompue (après catalogue)")
            return
        self._check_launcher()
        if self.isInterruptionRequested():
            log.info("Vérification des mises à jour interrompue (après launcher)")
            return
        self._check_download_counts()
        self.network_status.emit(self.is_online)

    @property
    def is_online(self) -> bool:
        """False seulement si AUCUN serveur n'a répondu ET qu'au moins une
        tentative a échoué au transport.

        Deux garde-fous volontaires : sans tentative du tout (aucune URL à
        vérifier), on ne déclare pas l'utilisateur hors ligne ; et une seule
        réponse, fût-elle une erreur HTTP, suffit à prouver qu'il est en ligne.
        Un faux « hors ligne » désactiverait le bouton de téléchargement d'un
        utilisateur parfaitement connecté — c'est le seul échec inacceptable ici.
        """
        return self._contact or self._transport_errors == 0

    def _note_transport_error(self, exc: Exception) -> None:
        """Distingue « serveur injoignable » de « serveur qui répond mal »."""
        import httpx  # import différé (thread) — voir en-tête de module

        if isinstance(exc, httpx.TransportError):
            self._transport_errors += 1

    def _check_download_counts(self) -> None:
        """Lit les releases du repo des jeux : compteurs ⬇ ET empreintes SHA-256.

        Une seule requête sert les deux usages — voir `extract_asset_digests`.
        """
        import httpx  # import différé (thread) — voir en-tête de module

        if not self._games_asset_urls:
            return
        try:
            with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(**_TIMEOUT_KW)) as client:
                resp = client.get(_releases_api_from_catalog_url(self._catalog_url))
                self._contact = True
                if resp.status_code == 403:
                    log.warning("GitHub API rate limit atteint (compteurs ⬇)")
                    return
                resp.raise_for_status()
                releases = resp.json()
            if not isinstance(releases, list):
                return
            totals = aggregate_download_counts(releases, self._games_asset_urls)
            if totals:
                log.info("Compteurs de téléchargement : %s", totals)
                self.download_counts.emit(totals)
            # Même réponse, zéro requête de plus : les empreintes publiées par
            # GitHub servent à vérifier l'intégrité des archives téléchargées.
            digests = extract_asset_digests(releases)
            if digests:
                log.info("Empreintes SHA-256 récupérées pour %d asset(s)", len(digests))
                self.asset_digests.emit(digests)
            # Toujours la même réponse : la taille réelle des archives, que le
            # catalogue ne sait pas donner (son `size_mb` est la taille une fois
            # installé). Voir `extract_asset_sizes`.
            tailles = extract_asset_sizes(releases)
            if tailles:
                log.info("Tailles réelles récupérées pour %d asset(s)", len(tailles))
                self.asset_sizes.emit(tailles)
        except (httpx.HTTPError, json.JSONDecodeError, ValueError,
                AttributeError, TypeError) as exc:
            self._note_transport_error(exc)
            log.warning("Impossible de récupérer les compteurs de téléchargement : %s", exc)

    def _check_catalog(self) -> None:
        """Télécharge et valide le catalogue distant."""
        import httpx  # import différé (thread) — voir en-tête de module

        if not self._catalog_url or not self._catalog_url.startswith("https://"):
            return
        try:
            with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(**_TIMEOUT_KW)) as client:
                # En streaming, avec un plafond : le téléchargeur d'archives en
                # a un (SIZE_OVERHEAD_FACTOR), la récupération du catalogue n'en
                # avait aucun. `client.get()` charge en mémoire tout ce que le
                # serveur envoie, puis on l'écrivait sur disque. Le catalogue
                # réel pèse ~30 Ko ; 4 Mo laissent de la marge pour vingt fois
                # plus de jeux et vingt langues.
                with client.stream("GET", self._catalog_url) as resp:
                    self._contact = True
                    resp.raise_for_status()
                    morceaux: list[bytes] = []
                    recus = 0
                    for bloc in resp.iter_bytes(64 * 1024):
                        recus += len(bloc)
                        if recus > _CATALOG_MAX_BYTES:
                            raise ValueError(
                                f"catalogue distant trop volumineux "
                                f"(> {_CATALOG_MAX_BYTES} octets), ignoré")
                        morceaux.append(bloc)
                brut = b"".join(morceaux)
            raw = json.loads(brut.decode("utf-8"))

            catalog = _parse_catalog(raw)
            if not catalog.games:
                log.warning("Catalogue distant vide, ignoré")
                return

            if compare_versions(catalog.catalog_version, self._current_version) > 0:
                # Sauvegarder localement
                try:
                    _LOCAL_CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
                    _LOCAL_CATALOG_PATH.write_text(
                        json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                except OSError as exc:
                    log.warning("Impossible de sauvegarder le catalogue local : %s", exc)

                log.info("Catalogue mis à jour : v%s → v%s",
                         self._current_version, catalog.catalog_version)
                self.catalog_updated.emit(catalog)

                # Compter les mises à jour disponibles
                # Même règle que `GameManager.has_update` — elle vit dans
                # version_utils pour ne pas pouvoir diverger d'un site à l'autre.
                count = 0
                for game in catalog.games:
                    if update_disponible(self._installed_versions.get(game.id),
                                         game.recommended_version):
                        count += 1
                if count > 0:
                    self.update_counts.emit(count)
            else:
                log.info("Catalogue à jour (v%s)", self._current_version)

        except (httpx.HTTPError, json.JSONDecodeError, ValueError, KeyError,
                AttributeError, TypeError) as exc:
            self._note_transport_error(exc)
            log.warning("Impossible de vérifier le catalogue distant : %s", exc)

    def _check_launcher(self) -> None:
        """Vérifie si une nouvelle version du launcher est disponible."""
        import httpx  # import différé (thread) — voir en-tête de module

        try:
            with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(**_TIMEOUT_KW)) as client:
                resp = client.get(_LAUNCHER_API)
                self._contact = True
                if resp.status_code == 403:
                    log.warning("GitHub API rate limit atteint")
                    return
                resp.raise_for_status()
                data = resp.json()

            # `resp.json()` peut rendre une liste (page d'erreur, proxy) : sans
            # ce garde, `data.get` levait `AttributeError`, hors du tuple
            # `except` ci-dessous, donc hors de `QThread.run()` — rapport de
            # plantage affiché à l'utilisateur. Voir aussi la note dans
            # `aggregate_download_counts`.
            if not isinstance(data, dict):
                log.warning("Réponse de release inattendue (%s), ignorée",
                            type(data).__name__)
                return

            tag = data.get("tag_name", "")
            if not tag or not isinstance(tag, str):
                return

            if compare_versions(tag, APP_VERSION) > 0:
                html_url = data.get("html_url", "https://github.com/ludvdber/AccioLauncher/releases/latest")
                if not isinstance(html_url, str) or not html_url.startswith("https://github.com/"):
                    log.warning("URL de release suspecte ignorée : %s", html_url)
                    html_url = "https://github.com/ludvdber/AccioLauncher/releases/latest"
                # Asset .exe pour l'auto-update (vide si introuvable → fallback page release)
                asset_url = ""
                asset_sha256 = ""
                for asset in data.get("assets", []) or []:
                    if not isinstance(asset, dict):
                        continue
                    url = asset.get("browser_download_url", "")
                    nom = asset.get("name", "")
                    if not isinstance(url, str) or not isinstance(nom, str):
                        continue
                    if nom.lower().endswith(".exe") and url.startswith("https://"):
                        asset_url = url
                        # GitHub publie l'empreinte de l'asset : elle évite d'avoir
                        # à la recopier à la main dans le code à chaque release,
                        # et sans elle l'auto-update installait un exe non vérifié.
                        asset_sha256 = extract_asset_digests([data]).get(url, "")
                        break
                log.info("Nouvelle version du launcher disponible : %s (actuelle: %s)", tag, APP_VERSION)
                if asset_url and not asset_sha256:
                    log.warning("Aucune empreinte publiée pour %s — mise à jour non vérifiée", asset_url)
                self.launcher_update.emit(tag.lstrip("v"), html_url, asset_url, asset_sha256)
            else:
                log.info("Launcher à jour (v%s)", APP_VERSION)

        except (httpx.HTTPError, json.JSONDecodeError, ValueError,
                AttributeError, TypeError) as exc:
            self._note_transport_error(exc)
            log.warning("Impossible de vérifier la version du launcher : %s", exc)
