"""Les Défis du Carnet : les succès en médailles (2026-10-26)."""

from datetime import datetime
from types import SimpleNamespace

import pytest

from src.core import folio, sauvegardes, succes
from src.ui import medailles

FIN = datetime(2026, 10, 24, 21, 30)


@pytest.fixture
def porte(monkeypatch):
    """Ce que « porte » chaque sauvegarde, sans fichier de jeu."""
    etat: dict[str, set[str] | None] = {}
    monkeypatch.setattr(succes, "evaluer", lambda jeu, spec, rel: etat.get(rel))
    monkeypatch.setattr(succes, "charger", lambda chemin=None: {})
    monkeypatch.setattr(sauvegardes, "vues", lambda jeu, spec: [SimpleNamespace(fichier=r) for r in etat])
    return etat


class TestMedailles:
    def test_chaque_succes_a_sa_medaille_declaree(self):
        """Un succès ajouté sans médaille tomberait sur le bronze des cartes : le dire ici."""
        for jeu in folio.JEUX:
            for s in succes.du_jeu(jeu):
                if not (jeu == "hp5" and s.ident.startswith("complet_")):
                    assert s.ident in medailles.MEDAILLES.get(jeu, {}), (jeu, s.ident)

    def test_les_images_existent(self):
        noms = {e for table in medailles.MEDAILLES.values() for e, _m in table.values()}
        for nom in noms:
            assert (medailles._DOSSIER / f"embleme-{nom}.png").is_file(), nom
        for m in (medailles.BRONZE, medailles.ARGENT, medailles.OR, "verrouillee"):
            assert (medailles._DOSSIER / f"medaille-{m}.png").is_file(), m

    def test_obtenue_et_verrouillee_different(self, qtbot):
        a = medailles.pixmap_medaille("hp1", "cartes_25", True, 64).toImage()
        b = medailles.pixmap_medaille("hp1", "cartes_25", False, 64).toImage()
        assert a.width() == 64 and a != b

    def test_les_lignes_pleines_de_hp5(self):
        assert medailles.medaille("hp5", "complet_3") == ("decouverte", medailles.ARGENT)


class TestPage:
    def test_toutes_les_medailles_dans_l_ordre_du_jeu(self, qtbot, porte):
        from src.ui.defis_page import DefisPage
        porte["Save0.usa"] = {"points_100"}
        page = DefisPage(SimpleNamespace(id="hp1", sauvegardes=None))
        qtbot.addWidget(page)
        assert [d.ident for d in page.defis] == [s.ident for s in succes.du_jeu("hp1")]
        assert [d.ident for d in page.defis if d.obtenu] == ["points_100"]

    def test_recommencer_apres_confirmation_seulement(self, qtbot, porte, monkeypatch):
        from src.ui import defis_page
        porte["Save0.usa"] = {"points_100"}
        page = defis_page.DefisPage(SimpleNamespace(id="hp1", name="HP1", sauvegardes=None))
        qtbot.addWidget(page)
        remis = []
        monkeypatch.setattr(succes, "recommencer", lambda jeu, quand: remis.append(jeu))
        monkeypatch.setattr(defis_page, "message", lambda *a, **k: 1)
        page.bouton_recommencer.click()
        assert remis == [], "Annuler ne touche à rien"
        monkeypatch.setattr(defis_page, "message", lambda *a, **k: 0)
        porte.clear()
        page.bouton_recommencer.click()
        assert remis == ["hp1"]
        assert not any(d.obtenu for d in page.defis), "la page est redessinée"

    def test_un_jeu_sans_defis_le_dit(self, qtbot, porte):
        from PyQt6.QtWidgets import QLabel
        from src.ui.defis_page import DefisPage
        page = DefisPage(SimpleNamespace(id="hp7a", sauvegardes=None))
        qtbot.addWidget(page)
        assert page.defis == []
        assert "Ce jeu n'a pas encore de défis." in [lbl.text() for lbl in page.findChildren(QLabel)]
