"""Le client HTTPS commun : certificats du système (truststore), repli sur certifi."""

import ast
import ssl
import sys
from pathlib import Path

from src.core import reseau

RACINE = Path(__file__).resolve().parent.parent


def test_le_contexte_vient_du_systeme():
    reseau.contexte_tls.cache_clear()
    try:
        ctx = reseau.contexte_tls()
        assert isinstance(ctx, ssl.SSLContext)
        assert type(ctx).__module__.startswith("truststore")
        assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
    finally:
        reseau.contexte_tls.cache_clear()


def test_sans_truststore_la_verification_reste_entiere(monkeypatch):
    """Le repli rend `True` (certifi), jamais `False`."""
    monkeypatch.setitem(sys.modules, "truststore", None)    # import → ImportError
    reseau.contexte_tls.cache_clear()
    try:
        assert reseau.contexte_tls() is True
    finally:
        reseau.contexte_tls.cache_clear()


def test_le_client_porte_le_contexte_et_suit_les_redirections(monkeypatch):
    vus = {}

    class FauxHttpx:
        @staticmethod
        def Client(**kw):  # noqa: N802
            vus.update(kw)
            return "client"
    monkeypatch.setitem(sys.modules, "httpx", FauxHttpx)
    monkeypatch.setattr(reseau, "contexte_tls", lambda: "ctx")
    assert reseau.client(12.0) == "client"
    assert vus == {"follow_redirects": True, "timeout": 12.0, "verify": "ctx"}


def test_aucun_client_httpx_cree_hors_de_reseau():
    """Un `httpx.Client(...)` écrit ailleurs reprendrait la liste figée de certifi."""
    fautifs = []
    for fichier in RACINE.joinpath("src").rglob("*.py"):
        if fichier.name == "reseau.py":
            continue
        for n in ast.walk(ast.parse(fichier.read_text(encoding="utf-8"))):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr in {"Client", "AsyncClient", "get", "post", "stream", "head"}
                    and isinstance(n.func.value, ast.Name) and n.func.value.id == "httpx"):
                fautifs.append(f"{fichier.relative_to(RACINE)}:{n.lineno}")
    assert fautifs == [], fautifs
