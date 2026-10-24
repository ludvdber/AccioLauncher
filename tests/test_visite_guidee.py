"""La visite guidée du launcher (idée de Ludo, 2026-10-24) : `src/ui/visite_guidee.py`."""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

pytest.importorskip("pytestqt")

from src.core.config import Config  # noqa: E402
from src.ui.visite_guidee import Etape, VisiteGuidee  # noqa: E402


@pytest.fixture
def scene(qtbot):
    """Une fenêtre nue et trois éléments, dont un caché."""
    hote = QWidget()
    hote.resize(900, 600)
    qtbot.addWidget(hote)
    a, b, c = (QWidget(hote) for _ in range(3))
    for w, x in ((a, 40), (b, 300), (c, 600)):
        w.setGeometry(x, 400, 120, 40)
    hote.show()
    qtbot.waitExposed(hote)
    b.hide()
    etapes = [Etape("A", "phrase a", lambda: a), Etape("B", "phrase b", lambda: b),
              Etape("Absent", "rien", lambda: None), Etape("C", "phrase c", lambda: c)]
    return hote, etapes


class TestParcours:
    def test_les_etapes_sans_element_visible_sont_sautees(self, scene):
        hote, etapes = scene
        visite = VisiteGuidee(etapes, hote)
        assert visite.demarrer()
        assert visite.rang == 0
        visite.suivant()
        assert visite.rang == 3, "B (caché) et l'étape sans élément ne se montrent pas"

    def test_le_compteur_ne_compte_que_les_etapes_montrees(self, scene):
        hote, etapes = scene
        visite = VisiteGuidee(etapes, hote)
        visite.demarrer()
        visite.suivant()
        assert visite._compteur.text() == "ÉTAPE 2 SUR 2"

    def test_la_derniere_etape_dit_terminer_et_la_premiere_n_a_pas_de_retour(self, scene):
        hote, etapes = scene
        visite = VisiteGuidee(etapes, hote)
        visite.demarrer()
        assert visite._btn_precedent.isHidden()
        assert visite._btn_suivant.text() == "Suivant"
        visite.suivant()
        assert visite._btn_suivant.text() == "Terminer"
        visite.precedent()
        assert visite.rang == 0

    def test_suivant_sur_la_derniere_termine_une_seule_fois(self, scene, qtbot):
        hote, etapes = scene
        visite = VisiteGuidee(etapes, hote)
        fins = []
        visite.terminee.connect(lambda: fins.append(1))
        visite.demarrer()
        visite.suivant()
        visite.suivant()
        visite.terminer()   # Échap juste après : pas de seconde fin
        assert fins == [1]

    def test_rien_a_montrer_rien_ne_s_affiche(self, scene):
        hote, _ = scene
        visite = VisiteGuidee([Etape("X", "x", lambda: None)], hote)
        assert not visite.demarrer()
        assert not visite.isVisible()


class TestGeometrie:
    def test_la_carte_reste_dans_la_fenetre_et_hors_de_la_decoupe(self, scene):
        hote, etapes = scene
        visite = VisiteGuidee(etapes, hote)
        visite.demarrer()
        for _ in range(2):
            carte = visite._carte.geometry()
            assert visite.rect().contains(carte), carte
            assert not carte.intersects(visite._cible), "la carte cache l'élément éclairé"
            visite.suivant()

    def test_la_decoupe_suit_un_redimensionnement(self, scene):
        hote, etapes = scene
        visite = VisiteGuidee(etapes, hote)
        visite.demarrer()
        etapes[0].cible().move(500, 100)
        visite.resize(hote.size())
        visite._poser()
        assert visite._cible.contains(etapes[0].cible().geometry())


class TestDansLaFenetre:
    def test_une_config_neuve_ne_l_a_pas_vue(self):
        assert Config().visite_vue is False

    def test_elle_se_lance_et_passer_la_note_vue(self, make_window, qtbot):
        win = make_window(visite_vue=False)
        win.show()
        qtbot.waitExposed(win)
        win._visite.proposer()
        assert win._visite.calque is not None and win._visite.calque.isVisible()
        qtbot.keyClick(win._visite.calque._btn_suivant, Qt.Key.Key_Escape)
        assert win._visite.calque is None
        assert win.config.visite_vue
        assert Config.load().visite_vue, "vue en mémoire mais pas enregistrée"

    def test_deja_vue_elle_ne_revient_pas(self, make_window, qtbot):
        win = make_window(visite_vue=True)
        win.show()
        qtbot.waitExposed(win)
        win._visite.proposer()
        assert win._visite.calque is None
        assert not win._visite.minuteur.isActive()

    def test_entree_avance_la_visite_sans_lancer_le_jeu(self, make_window, qtbot):
        win = make_window(visite_vue=False)
        win.show()
        qtbot.waitExposed(win)
        actions = []
        win._detail.trigger_primary_action = lambda: actions.append(1)   # sur l'INSTANCE (règle 12)
        win._visite.proposer()
        depart = win._visite.calque.rang
        qtbot.keyClick(win._visite.calque._btn_suivant, Qt.Key.Key_Return)
        assert win._visite.calque.rang > depart
        assert actions == [], "Entrée a lancé l'action de la fiche cachée sous le voile"

    def test_sans_jeu_installe_le_bouton_principal_est_telecharger(self, make_window, qtbot):
        win = make_window(visite_vue=False)   # dossier de jeux vide
        win.show()
        qtbot.waitExposed(win)
        win._visite.proposer()
        win._visite.calque.suivant()
        assert win._visite.calque.rang == 1, "l'étape du bouton principal a été sautée"
        assert win._visite.calque._etapes[1].cible().objectName() == "btnDownload"

    def test_une_page_ouverte_la_fait_attendre_la_bibliotheque(self, make_window, qtbot):
        win = make_window(visite_vue=False)
        win.show()
        qtbot.waitExposed(win)
        win._on_settings()
        win._visite.proposer()
        assert win._visite.calque is None
        win._pages.fermer()
        assert win._visite.minuteur.isActive(), "le retour à la bibliothèque doit la relancer"

    def test_revoir_depuis_les_parametres(self, make_window, qtbot):
        win = make_window(visite_vue=True)
        win.show()
        qtbot.waitExposed(win)
        win._on_settings()
        win._pages.page.visite_demandee.emit()
        assert win._pages.page is None
        assert win._visite.calque is not None and win._visite.calque.isVisible()
