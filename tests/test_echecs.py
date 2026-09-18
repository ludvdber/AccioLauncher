"""Un échec de téléchargement dit sa VRAIE cause (audit du 2026-09-18).

La boîte affichait « Vérifiez votre connexion internet » quelle que soit la
cause, disque plein et antivirus compris.
"""

import errno

import httpx
import pytest

from src.core.echecs import (
    Echec, EmpreinteInvalide, TailleDepassee, cause_de, explication,
)


def _statut(code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://example.org/x")
    return httpx.HTTPStatusError("x", request=req, response=httpx.Response(code, request=req))


def _winerror(code: int) -> OSError:
    e = OSError(0, "x")
    e.winerror = code
    return e


class TestCause:
    @pytest.mark.parametrize("exc, attendu", [
        (None, ("inconnu", 0)),
        (EmpreinteInvalide("sha"), ("empreinte", 0)),
        (TailleDepassee("trop"), ("inattendu", 0)),
        (OSError(errno.ENOSPC, "plein"), ("disque_plein", 0)),
        (_winerror(112), ("disque_plein", 0)),
        (_winerror(225), ("antivirus", 0)),
        (_winerror(32), ("acces_refuse", 0)),
        (PermissionError(errno.EACCES, "non"), ("acces_refuse", 0)),
        (OSError("autre"), ("inconnu", 0)),
        (_statut(404), ("introuvable", 404)),
        (_statut(403), ("limite", 403)),
        (_statut(503), ("serveur", 503)),
        (httpx.ConnectError("coupé"), ("connexion", 0)),
        (httpx.ReadTimeout("lent"), ("connexion", 0)),
        (ValueError("?"), ("inconnu", 0)),
    ])
    def test_classement(self, exc, attendu):
        assert cause_de(exc) == attendu

    def test_les_erreurs_typees_restent_des_oserror(self):
        """La boucle de reprise du téléchargeur attrape `OSError` : les nouvelles
        exceptions doivent y tomber, sinon une empreinte fausse sortirait du
        thread au lieu d'être retentée."""
        assert issubclass(EmpreinteInvalide, OSError)
        assert issubclass(TailleDepassee, OSError)


class TestExplication:
    def test_seule_la_connexion_accuse_la_connexion(self, langue_fr):
        for cause in ("disque_plein", "antivirus", "acces_refuse", "empreinte",
                      "inattendu", "introuvable", "limite", "serveur", "inconnu"):
            assert "connexion internet" not in explication(Echec(cause)), cause
        assert "connexion internet" in explication(Echec("connexion"))

    def test_le_code_http_est_cite(self, langue_fr):
        assert "404" in explication(Echec("introuvable", code_http=404))

    def test_les_octets_conserves_sont_annonces(self, langue_fr):
        texte = explication(Echec("disque_plein", conserves=5 * 1024 * 1024))
        assert "Le disque est plein" in texte and "conservés" in texte

    def test_rien_d_annonce_sans_octets(self, langue_fr):
        assert "conservés" not in explication(Echec("connexion"))


@pytest.fixture
def langue_fr():
    from src.core.i18n import get_language, set_language
    avant = get_language()
    set_language("fr")
    yield
    set_language(avant)


class TestBoiteDEchec:
    """Bout en bout : le signal du téléchargeur jusqu'au texte de la boîte."""

    def test_la_boite_dit_disque_plein(self, qtbot, langue_fr):
        from unittest.mock import MagicMock

        from src.ui.game_operations import GameOperations

        ops = GameOperations(MagicMock())
        recu = []
        ops.operation_error.connect(lambda t, m: recu.append(m))
        ops._on_download_error("Échec", Echec("disque_plein", conserves=2048))
        assert recu and "Le disque est plein" in recu[0]
        assert "connexion internet" not in recu[0]
