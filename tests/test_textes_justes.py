"""Ce que l'écran dit doit être vrai (lot 3 du grand audit du 2026-11-02).

Chaque test échoue sur le code d'avant : « désinstallé » sur un échec,
« d3d9.ini » pour HP1-HP3, « Windows » sous Linux, dates ambiguës en anglais,
message de HP1 sur HP7.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core import echecs
from src.core.i18n import set_language


@pytest.fixture
def anglais():
    set_language("en")
    yield
    set_language("fr")


class _Signal:
    def __init__(self):
        self.recus = []

    def emit(self, *args):
        self.recus.append(args)


def test_une_desinstallation_ratee_ne_dit_pas_desinstalle(monkeypatch):
    from src.ui import game_detail_handlers as h
    monkeypatch.setattr(h, "_boite", lambda *a, **k: 0)          # « Désinstaller »
    monkeypatch.setattr(h, "_ce_qui_reste", lambda game: "")
    statut = _Signal()
    vue = SimpleNamespace(game=SimpleNamespace(id="hp1", name="HP1"),
                          manager=SimpleNamespace(uninstall_game=lambda gid: False),
                          _refresh=lambda: None, state_changed=_Signal(), status_message=statut)
    h.on_uninstall(vue)
    (message,), = statut.recus
    assert "désinstallé." not in message and "n'a pas abouti" in message


def test_le_message_d_erreur_nomme_le_vrai_fichier():
    from src.ui.game_settings_dialog import GameSettingsDialog
    textes = []
    faux = SimpleNamespace(_ini=Path("HP1/System/winmm.ini"),
                           _erreur=SimpleNamespace(setText=textes.append, show=lambda: None))
    GameSettingsDialog._montrer_erreur(faux)
    assert "winmm.ini" in textes[0] and "d3d9.ini" not in textes[0]


@pytest.mark.parametrize("cause", ["acces_refuse"])
def test_les_echecs_ne_nomment_pas_windows(cause):
    assert "Windows" not in echecs.explication(echecs.Echec(cause=cause))
    for c in ("acces_refuse", "chemin_long"):
        assert "Windows" not in echecs.explication_installation(c)


def test_date_courte_sans_ambiguite_en_anglais(anglais):
    from src.ui.versions_dialog import date_courte
    assert date_courte("2026-10-01") == "2026-10-01"


def test_date_courte_en_francais():
    from src.ui.versions_dialog import date_courte
    assert date_courte("2026-10-01") == "01/10/2026"


def test_hp7_a_son_propre_message_de_debut():
    from src.ui.folio_jeux import FolioPageHP7
    from src.ui.folio_page import FolioPage
    assert "carte" not in FolioPageHP7._message_debut(None)
    assert "carte" in FolioPage._message_debut(None)
