"""Le client HTTPS du launcher : redirections suivies, certificats vérifiés par le SYSTÈME.

La vérification passe par truststore : le magasin de certificats de Windows
(CryptoAPI, tenu à jour par Windows Update), et sous Linux le paquet de
certificats de la distribution, mis à jour avec elle. Avant, c'était la liste
de certifi figée dans l'exe : une autorité retirée en urgence (emSign, Python
3.14.9 sorti exprès le 2026-10-21) restait acceptée jusqu'à la version
suivante du launcher. Essayé le 2026-10-25 : GitHub accepté, certificats
expiré, auto-signé et au mauvais nom refusés (badssl.com).

httpx et truststore s'importent ICI, au premier appel, jamais au chargement du
module : ~70 ms de démarrage (voir l'en-tête de `updater`).
"""

import functools
import logging
import ssl
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

log = logging.getLogger(__name__)


@functools.cache
def contexte_tls() -> ssl.SSLContext | bool:
    """Le contexte TLS du système ; à défaut, `True` (vérification par certifi).

    Le repli garde une vérification complète : il ne désactive jamais rien.
    """
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception as exc:          # magasin illisible, système non pris en charge
        log.warning("Certificats du système inutilisables, liste intégrée à la place : %s", exc)
        return True


def client(timeout: httpx.Timeout | float) -> httpx.Client:
    """Un `httpx.Client` à ouvrir dans un `with`."""
    import httpx
    return httpx.Client(follow_redirects=True, timeout=timeout, verify=contexte_tls())
