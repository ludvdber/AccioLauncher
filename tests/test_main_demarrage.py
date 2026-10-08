"""La boîte d'un démarrage raté (M-09 / ACT-005).

Elle était en français en dur, par le raccourci `QMessageBox.critical`
(règle 116), et ne disait pas où trouver le journal — la seule chose dont
l'aide sur le Discord a besoin.
"""

import pytest

pytest.importorskip("pytestqt")

import main  # noqa: E402


class _FausseBoite:
    """Note ce qu'on lui demande ; `exec()` ne bloque pas."""

    def __init__(self):
        self.textes: list[str] = []
        self.boutons: list[str] = []
        self.details = ""
        self.ouverte = False

    def setWindowTitle(self, t):
        self.textes.append(t)

    def setText(self, t):
        self.textes.append(t)

    def setInformativeText(self, t):
        self.textes.append(t)

    def setDetailedText(self, t):
        self.details = t

    def addButton(self, libelle, _role):
        self.boutons.append(libelle)

    def exec(self):
        self.ouverte = True

    def setIcon(self, _i):
        pass

    def setTextFormat(self, _f):
        pass

    def setTextInteractionFlags(self, _f):
        pass


@pytest.fixture
def boite(qapp):
    return _FausseBoite()


def test_la_boite_donne_le_chemin_du_journal(boite):
    assert main.afficher_erreur_fatale(RuntimeError("boum"), fabrique=lambda: boite)
    assert boite.ouverte
    assert any(str(main.LOG_FILE) in t for t in boite.textes)
    assert "RuntimeError: boum" in boite.details


def test_les_textes_passent_par_la_traduction(boite):
    from src.core.i18n import get_language, set_language
    avant = get_language()
    set_language("en")
    try:
        main.afficher_erreur_fatale(RuntimeError("boum"), fabrique=lambda: boite)
    finally:
        set_language(avant)
    assert "Accio Launcher could not start." in boite.textes
    assert boite.boutons == ["Close"]
