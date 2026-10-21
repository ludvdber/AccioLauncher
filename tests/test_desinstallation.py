"""Ce que la désinstallation dit des sauvegardes (ACT-059, audit du 2026-10-07).

Le message « conservées » ne venait que des jeux qui déclarent des fichiers de
configuration, donc HP1 à HP3, alors qu'aucun des huit jeux ne range ses
sauvegardes dans son dossier. Il suit maintenant le bloc `saves` déclaré ;
sans bloc, on ne sait pas, et on se tait (règle 108).
"""
from types import SimpleNamespace

import pytest

from src.ui import game_detail_handlers as h


def _vue(sauvegardes, config_files):
    notes, desinstalles = [], []
    game = SimpleNamespace(id="hpx", name="HPX", sauvegardes=sauvegardes,
                           post_install=SimpleNamespace(config_files=config_files))
    vue = SimpleNamespace(
        game=game, manager=SimpleNamespace(uninstall_game=desinstalles.append),
        _refresh=lambda: None, state_changed=SimpleNamespace(emit=lambda: None),
        notify=SimpleNamespace(emit=notes.append), status_message=SimpleNamespace(emit=lambda _m: None))
    return vue, notes, desinstalles


@pytest.mark.parametrize("sauvegardes, config, attendu", [
    (object(), ("HP.ini",), "Vos sauvegardes et la configuration du jeu sont conservées"),
    (object(), (), "Vos sauvegardes sont conservées"),
    (None, ("HP.ini",), "La configuration du jeu dans Mes Documents est conservée."),
])
def test_ce_qui_reste_est_dit_avant_le_clic(monkeypatch, sauvegardes, config, attendu):
    """Dans la question, pas dans un toast d'après qui s'efface (Bazzite,
    2026-10-20) : c'est avant le clic que la peur de tout perdre fait hésiter."""
    questions = []
    monkeypatch.setattr(h, "_boite", lambda *a, **k: questions.append(a[3]) or 0)
    vue, notes, desinstalles = _vue(sauvegardes, config)
    h.on_uninstall(vue)
    assert desinstalles == ["hpx"] and notes == []
    assert questions[0].split("\n\n")[1].startswith(attendu)


def test_sans_rien_de_declare_on_n_affirme_rien(monkeypatch):
    questions = []
    monkeypatch.setattr(h, "_boite", lambda *a, **k: questions.append(a[3]) or 0)
    vue, notes, desinstalles = _vue(None, ())
    h.on_uninstall(vue)
    assert desinstalles == ["hpx"] and notes == []
    assert "\n\n" not in questions[0]


def test_annuler_ne_desinstalle_rien(monkeypatch):
    monkeypatch.setattr(h, "_boite", lambda *a, **k: 1)
    vue, notes, desinstalles = _vue(object(), ())
    h.on_uninstall(vue)
    assert desinstalles == [] and notes == []
