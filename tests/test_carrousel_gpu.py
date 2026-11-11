"""Le carrousel et le disque sur la carte graphique : le double des widgets.

Les autres tests gardent ce chemin éteint (`conftest.py`) ; ceux-ci l'allument.
"""

import os
import subprocess
import sys
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, QRectF, QSize, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QWidget

from src.core.config import ASSETS_DIR
from src.ui import carrousel_gpu, fond_gpu
from src.ui.carousel import Carousel, SCALE_FAR, SCALE_SELECTED
from tests.test_carousel import _FakeManager, _make_game

pytestmark = pytest.mark.skipif(not fond_gpu.QUICK_DISPONIBLE, reason="Qt Quick absent")


@pytest.fixture
def jumeau_allume(monkeypatch):
    monkeypatch.setenv("ACCIO_FOND_GPU", "1")
    monkeypatch.setenv("ACCIO_CARROUSEL_GPU", "1")


def _bande(qtbot, *ids, largeur=900) -> Carousel:
    c = Carousel([_make_game(i) for i in (ids or ("a", "b", "c"))], _FakeManager())
    qtbot.addWidget(c)
    c.resize(largeur, 192)
    c.show()
    qtbot.waitExposed(c)
    return c


def _etats(c: Carousel):
    return c._jumeau._racine.property("etats")


def test_allume_par_defaut_avec_le_fond_sur_la_carte(monkeypatch):
    monkeypatch.setenv("ACCIO_FOND_GPU", "1")
    monkeypatch.delenv("ACCIO_CARROUSEL_GPU", raising=False)
    assert carrousel_gpu.actif()


def test_a_zero_il_s_eteint_meme_avec_le_fond_sur_la_carte(qtbot, monkeypatch):
    monkeypatch.setenv("ACCIO_FOND_GPU", "1")
    monkeypatch.setenv("ACCIO_CARROUSEL_GPU", "0")
    assert not carrousel_gpu.actif()
    c = _bande(qtbot)
    assert c._jumeau is None and isinstance(c._gpu, fond_gpu.EtoilesGPU)
    assert all(item.updatesEnabled() for item in c._items)


def test_sans_le_fond_sur_la_carte_il_reste_eteint(monkeypatch):
    monkeypatch.setenv("ACCIO_FOND_GPU", "0")
    monkeypatch.delenv("ACCIO_CARROUSEL_GPU", raising=False)
    assert not carrousel_gpu.actif()


@pytest.mark.parametrize("absent", ["PyQt6.QtQuickWidgets", "PyQt6.QtQuick"])
def test_un_module_quick_absent_laisse_tout_s_importer_et_eteint(absent):
    """`QtQuickWidgets` manquant seul faisait un `TypeError` à l'import de `disque.py`."""
    code = (
        f"import sys; sys.modules[{absent!r}] = None\n"
        "from PyQt6.QtWidgets import QApplication\n"
        "app = QApplication([])\n"
        "from src.ui import carrousel_gpu, disque, fiche_gpu, fond_gpu\n"
        "assert not fond_gpu.QUICK_DISPONIBLE\n"
        "assert not carrousel_gpu.actif() and not fiche_gpu.actif()\n"
        "d = disque.Disque(18, fond_scene='#060611'); d.show(); app.processEvents()\n"
        "assert d._gpu is None\n"
    )
    env = {**os.environ, "ACCIO_FOND_GPU": "1", "ACCIO_CARROUSEL_GPU": "1", "ACCIO_FICHE_GPU": "1",
           "QT_QPA_PLATFORM": "offscreen"}
    fini = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                          encoding="utf-8", errors="replace", timeout=120, check=False)
    assert fini.returncode == 0, fini.stderr


def test_la_scene_se_charge_et_les_vignettes_ne_se_peignent_plus(qtbot, jumeau_allume):
    c = _bande(qtbot)
    assert isinstance(c._jumeau, carrousel_gpu.CarrouselGPU)
    assert not c._jumeau.errors(), [e.toString() for e in c._jumeau.errors()]
    assert all(not item.updatesEnabled() for item in c._items)
    peints = []
    for item in c._items:
        item.paintEvent = lambda e, i=item: peints.append(i)
    c.select(1)
    c._items[1].update()
    qtbot.wait(30)
    assert not peints, "le widget d'une vignette ne doit plus se peindre"


def test_la_selection_pose_la_taille_finale_sans_animer_les_widgets(qtbot, jumeau_allume):
    c = _bande(qtbot)
    c.select(2)
    item = c._items[2]
    assert item._anim_scale == SCALE_SELECTED
    assert c._items[0]._anim_scale == SCALE_FAR
    # Pas d'animation de propriété : aucune mise en page pendant les 400 ms.
    assert item._scale_anim.state().name == "Stopped"
    assert item.width() == int(item._thumb_w * SCALE_SELECTED) + 10
    # Le double est demandé, et avec animation, à la géométrie finale.
    etats = _etats(c)
    assert etats[2]["choisi"] and not etats[0]["choisi"]
    assert etats[2]["cw"] == int(item._thumb_w * SCALE_SELECTED)
    assert etats[2]["x"] == item.x() and etats[2]["y"] == item.y()
    assert c._jumeau._racine.property("animer") is True


def test_une_geometrie_qui_change_sans_selection_suit_sans_animation(qtbot, jumeau_allume):
    c = _bande(qtbot)
    c.select(1)
    c.resize(1200, 192)
    qtbot.waitUntil(lambda: _etats(c)[1]["x"] == c._items[1].x(), timeout=2000)
    assert c._jumeau._racine.property("animer") is False


def test_le_survol_laisse_tourner_l_animation_en_cours(qtbot, jumeau_allume):
    c = _bande(qtbot)
    c.select(1)
    qtbot.wait(20)                       # la géométrie de la sélection est partie
    assert c._jumeau._racine.property("animer") is True
    c._items[0].enterEvent(None)
    c._pousser_jumeau()
    assert _etats(c)[0]["survol"]
    assert c._jumeau._racine.property("animer") is True, "un survol n'annule pas l'animation"
    c._items[0].leaveEvent(None)
    c._pousser_jumeau()
    assert not _etats(c)[0]["survol"]


def test_reconstruire_la_bande_garde_le_double_aligne(qtbot, jumeau_allume):
    c = _bande(qtbot, "a", "b")
    c.set_games([_make_game("x"), _make_game("y"), _make_game("z")], selected_id="z")
    qtbot.wait(20)
    etats = _etats(c)
    assert len(etats) == 3 and etats[2]["choisi"]
    assert c._items[0].updatesEnabled() is False, "les vignettes neuves aussi"


def test_le_fournisseur_sert_les_images_des_vignettes(qtbot, jumeau_allume):
    c = _bande(qtbot)
    url = _etats(c)[0]["image"]
    assert url.startswith("image://accio/")
    image, taille = c._jumeau._fournisseur.requestImage(url.removeprefix("image://accio/"), QSize())
    assert not image.isNull() and taille.width() > 0


def test_la_scene_dessine_le_filet_de_la_vignette_choisie(qtbot, jumeau_allume):
    c = _bande(qtbot, "a", "b")
    c.select(1)
    qtbot.wait(450)
    item = c._items[1]
    x, y = item.x() + item.width() // 2, item.y() + 5
    def _filet():
        rendu = c._jumeau.grabFramebuffer()
        couleur = rendu.pixelColor(x, y + 1)
        return couleur.red() > 90 and couleur.green() > 70      # le filet doré, pas le fond
    qtbot.waitUntil(_filet, timeout=4000)


def test_sans_scene_valide_les_vignettes_se_peignent(qtbot, monkeypatch, jumeau_allume):
    monkeypatch.setattr(carrousel_gpu.CarrouselGPU, "valide", lambda self: False)
    c = _bande(qtbot)
    assert c._jumeau is None
    assert all(item.updatesEnabled() for item in c._items)


def test_les_scenes_n_importent_que_qt_quick():
    """Le tri du paquet PyInstaller (`_qml_utile`) n'embarque pas QtQuick.Controls."""
    for nom in ("CarrouselAccueil.qml", "DisqueScene.qml"):
        imports = [ligne.strip() for ligne in (ASSETS_DIR / "qml" / nom).read_text(encoding="utf-8").splitlines()
                   if ligne.startswith("import ")]
        assert imports == ["import QtQuick"], nom


def test_dans_une_vraie_fenetre_et_sans_rejouer_les_animations_des_widgets(make_window, qtbot, monkeypatch):
    monkeypatch.setenv("ACCIO_FOND_GPU", "1")
    monkeypatch.setenv("ACCIO_CARROUSEL_GPU", "1")
    win = make_window()
    win.show()
    qtbot.waitExposed(win)
    c = win._carousel
    assert isinstance(c._jumeau, carrousel_gpu.CarrouselGPU)
    tailles = []
    for item in c._items:
        original = item._update_size
        monkeypatch.setattr(item, "_update_size",
                            lambda o=original, i=item: (tailles.append(i), o())[1])
    c.select_next()
    qtbot.wait(450)
    assert len(tailles) == len(c._items), "une seule mise en page par vignette, plus 25 par animation"


def test_le_fond_du_mini_disque_est_celui_de_la_barre_de_statut(make_window, qtbot):
    """Le fond (`fond_scene`) doit être la couleur que la barre peint vraiment autour."""
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QColor
    from src.ui.theme import themed
    win = make_window(theme="serpentard")
    win.show()
    qtbot.waitExposed(win)
    barre = win._status_bar
    couleur = barre.grab().toImage().pixelColor(QPoint(3, barre.height() // 2))
    assert couleur.name() == QColor(themed("#060611")).name()


# ── Le clic vise ce qui est vu ──


class _Horloge:
    def __init__(self):
        self.t = 0

    def elapsed(self):
        return self.t


def _glissement():
    g = carrousel_gpu.Glissement()
    g._horloge = _Horloge()
    return g


def test_le_glissement_suit_la_courbe_de_la_scene():
    g = _glissement()
    g.poser([(0.0, 0.0, 10.0, 10.0)], False)
    assert not g.en_cours()
    g.poser([(100.0, 0.0, 10.0, 10.0)], True)
    assert g.en_cours() and g.rects_vus()[0].x() == 0.0
    g._horloge.t = 100
    assert g.rects_vus()[0].x() == pytest.approx(12.5)      # InOutQuad à un quart
    g._horloge.t = 200
    assert g.rects_vus()[0].x() == pytest.approx(50.0)
    g._horloge.t = 400
    assert g.rects_vus()[0].x() == 100.0 and not g.en_cours()


def test_une_course_interrompue_repart_de_ce_qui_se_voit():
    g = _glissement()
    g.poser([(0.0, 0.0, 10.0, 10.0)], False)
    g.poser([(100.0, 0.0, 10.0, 10.0)], True)
    g._horloge.t = 200                                      # vue à 50
    g.poser([(0.0, 0.0, 10.0, 10.0)], True)
    assert g.rects_vus()[0].x() == pytest.approx(50.0)
    g._horloge.t = 400
    assert g.rects_vus()[0].x() == pytest.approx(25.0), "400 ms pleines depuis l'interruption"


def test_une_valeur_inchangee_continue_sa_course_comme_un_behavior():
    g = _glissement()
    g.poser([(0.0, 0.0, 10.0, 10.0)], False)
    g.poser([(100.0, 100.0, 10.0, 10.0)], True)
    g._horloge.t = 200
    g.poser([(0.0, 100.0, 10.0, 10.0)], True)               # seul x repart
    g._horloge.t = 400
    assert g.rects_vus()[0].y() == 100.0, "y arrive à l'heure de sa propre course"


def test_sans_animation_la_valeur_saute():
    g = _glissement()
    g.poser([(0.0, 0.0, 10.0, 10.0)], False)
    g.poser([(100.0, 0.0, 10.0, 10.0)], True)
    g._horloge.t = 100
    g.poser([(300.0, 0.0, 10.0, 10.0)], False)
    assert g.rects_vus()[0].x() == 300.0 and not g.en_cours()


def test_la_course_de_python_est_celle_de_la_scene(qtbot, jumeau_allume):
    c = _bande(qtbot)
    assert c._jumeau._racine.property("duree") == carrousel_gpu.Glissement.DUREE_MS
    source = (ASSETS_DIR / "qml" / "CarrouselAccueil.qml").read_text(encoding="utf-8")
    assert source.count("easing.type: Easing.InOutQuad") == 5
    assert "easing.type: Easing." not in source.replace("easing.type: Easing.InOutQuad", "")


def _huit_vignettes_a_l_arret(qtbot):
    """Une bande dont l'animation est FIGÉE à son départ : l'horloge ne bouge plus."""
    c = _bande(qtbot, *"abcdefgh", largeur=1200)
    c._pousser_jumeau()
    horloge = _Horloge()
    horloge.t = 1_000_000
    c._jumeau._glissement._horloge = horloge
    return c, horloge


def _cliquer(c, x, y):
    """Le clic que Qt livrerait : au widget réellement sous le point."""
    cible = c.childAt(QPoint(x, y)) or c
    QTest.mouseClick(cible, Qt.MouseButton.LeftButton, pos=cible.mapFrom(c, QPoint(x, y)))


def _sur(rects, x, y):
    return next((i for i in reversed(range(len(rects))) if rects[i].contains(QPointF(x, y))), None)


def _points_de_desaccord(c, avant, y):
    """Pour chaque x : (ce qui se voit, le widget réellement là), s'ils diffèrent."""
    finals = [QRectF(item.geometry()) for item in c._items]
    return [(x, _sur(avant, x, y), _sur(finals, x, y)) for x in range(c.width())
            if _sur(avant, x, y) != _sur(finals, x, y)]


def test_au_debut_de_l_animation_le_clic_vise_la_vignette_vue_pas_la_voisine(qtbot, jumeau_allume):
    c, _ = _huit_vignettes_a_l_arret(qtbot)
    avant = [QRectF(item.geometry()) for item in c._items]
    y = c._items[3].y() + 40
    c.select(7)
    x, vu, reel = next(p for p in _points_de_desaccord(c, avant, y)
                       if p[1] not in (None, 7) and p[2] is not None)
    _cliquer(c, x, y)
    assert c.current_index == vu != reel


def test_une_vignette_vue_la_ou_il_n_y_a_plus_de_widget_se_clique(qtbot, jumeau_allume):
    c, _ = _huit_vignettes_a_l_arret(qtbot)
    avant = [QRectF(item.geometry()) for item in c._items]
    y = c._items[3].y() + 40
    c.select(7)
    x, vu, _reel = next(p for p in _points_de_desaccord(c, avant, y)
                        if p[1] not in (None, 7) and p[2] is None)
    assert c.childAt(QPoint(x, y)) is None, "un trou de la bande : ni widget, ni scène"
    _cliquer(c, x, y)
    assert c.current_index == vu


def test_un_clic_sur_un_widget_ou_rien_ne_se_voit_ne_choisit_rien(qtbot, jumeau_allume):
    c, _ = _huit_vignettes_a_l_arret(qtbot)
    avant = [QRectF(item.geometry()) for item in c._items]
    y = c._items[3].y() + 40
    c.select(7)
    x, _vu, _reel = next(p for p in _points_de_desaccord(c, avant, y)
                         if p[1] is None and p[2] is not None)
    _cliquer(c, x, y)
    assert c.current_index == 7


def test_a_mi_course_le_clic_suit_la_position_interpolee(qtbot, jumeau_allume):
    c, horloge = _huit_vignettes_a_l_arret(qtbot)
    avant = [QRectF(item.geometry()) for item in c._items]
    y = c._items[3].y() + 40
    c.select(7)
    finals = [QRectF(item.geometry()) for item in c._items]
    horloge.t += 200
    milieu = [QRectF((a.x() + f.x()) / 2, (a.y() + f.y()) / 2,
                     (a.width() + f.width()) / 2, (a.height() + f.height()) / 2)
              for a, f in zip(avant, finals, strict=True)]
    x = next(x for x in range(c.width())
             if _sur(milieu, x, y) not in (None, 7) and _sur(finals, x, y) != _sur(milieu, x, y))
    vu = _sur(milieu, x, y)
    _cliquer(c, x, y)
    assert c.current_index == vu


def test_l_animation_finie_le_clic_revient_au_vrai_widget(qtbot, jumeau_allume):
    c, horloge = _huit_vignettes_a_l_arret(qtbot)
    avant = [QRectF(item.geometry()) for item in c._items]
    y = c._items[3].y() + 40
    c.select(7)
    x, _vu, reel = next(p for p in _points_de_desaccord(c, avant, y)
                        if p[2] not in (None, 7) and p[1] is not None)
    horloge.t += 400
    assert not c._jumeau.glisse()
    _cliquer(c, x, y)
    assert c.current_index == reel


def test_eteint_le_clic_ne_passe_pas_par_la_position_vue(qtbot, monkeypatch):
    monkeypatch.setenv("ACCIO_FOND_GPU", "1")
    monkeypatch.setenv("ACCIO_CARROUSEL_GPU", "0")
    c = _bande(qtbot)
    c.select(2)
    assert c._items[1]._clic_vu is None
    QTest.mouseClick(c._items[1], Qt.MouseButton.LeftButton)
    assert c.current_index == 1


# ── L'échelle de l'écran ──


def test_un_changement_d_echelle_refait_les_images_du_carrousel(qtbot, jumeau_allume, monkeypatch):
    c = _bande(qtbot)
    item = c._items[0]
    item._cached_is_new, item._cached_installed = True, False
    item._signaler_jumeau()
    qtbot.waitUntil(lambda: not c._jumeau_a_pousser.isActive(), timeout=1000)
    qtbot.wait(5)
    j = c._jumeau
    avant = _etats(c)[0]
    assert j._racine.property("dpr") == 1.0 and avant["marques"]
    monkeypatch.setattr(j, "devicePixelRatioF", lambda: 1.5)
    QCoreApplication.sendEvent(c, QEvent(QEvent.Type.DevicePixelRatioChange))
    qtbot.waitUntil(lambda: j._racine.property("dpr") == 1.5, timeout=1000)
    apres = _etats(c)[0]
    assert apres["marques"] != avant["marques"]
    for cle in ("marques", "image", "chiffre"):
        if apres[cle] and not apres["jaquette"]:
            assert apres[cle] != avant[cle], cle
    image, _ = j._fournisseur.requestImage(apres["marques"].removeprefix("image://accio/"), QSize())
    assert image.width() == round(apres["cw"] * 1.5)


# ── Le focus ──


def test_les_scenes_du_carrousel_ne_sont_pas_des_arrets_tab(qtbot, jumeau_allume, monkeypatch):
    c = _bande(qtbot)
    assert c._jumeau.focusPolicy() == Qt.FocusPolicy.NoFocus
    monkeypatch.setenv("ACCIO_CARROUSEL_GPU", "0")
    c2 = _bande(qtbot)
    assert c2._gpu is not c2._jumeau and c2._gpu.focusPolicy() == Qt.FocusPolicy.NoFocus


def _arrets_tab(win):
    """La chaîne de Tab telle que la parcourent le clavier et la manette."""
    arrets, w = [], win.nextInFocusChain()
    while w is not win:
        if w.focusPolicy() & Qt.FocusPolicy.TabFocus and w.isVisibleTo(win) and w.isEnabled():
            arrets.append((type(w).__name__, w.objectName()))
        w = w.nextInFocusChain()
    return arrets


def test_la_navigation_est_celle_du_chemin_reel(make_window, qtbot, monkeypatch):
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtQuickWidgets import QQuickWidget
    monkeypatch.setenv("ACCIO_FOND_GPU", "1")
    for nom in ("ACCIO_CARROUSEL_GPU", "ACCIO_FICHE_GPU"):
        monkeypatch.setenv(nom, "0")
    eteinte = make_window()
    eteinte.show()
    qtbot.wait(30)
    attendus = _arrets_tab(eteinte)
    for nom in ("ACCIO_CARROUSEL_GPU", "ACCIO_FICHE_GPU"):
        monkeypatch.setenv(nom, "1")
    win = make_window()
    win.show()
    qtbot.wait(30)
    assert win._carousel._jumeau is not None and win._detail._jumeau is not None
    assert attendus, "des arrêts à comparer"
    assert _arrets_tab(win) == attendus
    scenes = win.findChildren(QQuickWidget)
    assert scenes and all(s.focusPolicy() == Qt.FocusPolicy.NoFocus for s in scenes)
    depart = win._carousel.current_index
    droite = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
    assert win.eventFilter(win, droite) is True
    assert win._carousel.current_index == depart + 1


class TestLeDisque:
    @staticmethod
    def _disque(qtbot, cote=18, reflet=False, fond_scene="#060611"):
        from src.ui.disque import Disque
        parent = QWidget()
        qtbot.addWidget(parent)
        d = Disque(cote, reflet=reflet, parent=parent, fond_scene=fond_scene)
        parent.resize(cote + 4, cote + 4)
        parent.show()
        qtbot.waitExposed(parent)
        return d

    def test_la_rotation_passe_a_la_scene_sans_repeindre(self, qtbot, jumeau_allume, monkeypatch):
        d = self._disque(qtbot)
        assert d._gpu is not None and d._gpu.valide() and not d._gpu.errors()
        repeint = []
        monkeypatch.setattr(d, "update", lambda *a: repeint.append(a))
        monkeypatch.setattr(d, "_horloge", SimpleNamespace(restart=lambda: 110))
        d._angle = 10.0
        d._battement()
        attendu = 10.0 + 360.0 * 0.11 / 5.5
        assert d._angle == pytest.approx(attendu)
        assert d._gpu._racine.property("angle") == pytest.approx(attendu), "le battement envoie l'angle"
        assert not repeint, "Python ne pousse que l'angle"

    def test_les_clics_traversent_la_scene(self, qtbot, jumeau_allume):
        from PyQt6.QtCore import Qt
        d = self._disque(qtbot)
        assert d._gpu.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def test_la_platine_met_le_reflet_et_l_ombre(self, qtbot, jumeau_allume):
        d = self._disque(qtbot, cote=100, reflet=True, fond_scene="#08081a")
        racine = d._gpu._racine
        assert racine.property("ombre") and racine.property("lumiere")

    def test_un_changement_d_echelle_refait_ombre_lumiere_et_image(self, qtbot, jumeau_allume, monkeypatch):
        d = self._disque(qtbot, cote=100, reflet=True, fond_scene="#08081a")
        racine = d._gpu._racine
        avant = {nom: racine.property(nom) for nom in ("ombre", "lumiere", "disque")}
        assert all(avant.values())
        monkeypatch.setattr(d, "devicePixelRatioF", lambda: 1.5)
        monkeypatch.setattr(d._gpu, "devicePixelRatioF", lambda: 1.5)
        QCoreApplication.sendEvent(d, QEvent(QEvent.Type.DevicePixelRatioChange))
        for nom, url in avant.items():
            neuve = racine.property(nom)
            assert neuve != url, nom
            image, _ = d._gpu._fournisseur.requestImage(neuve.removeprefix("image://accio/"), QSize())
            assert image.width() == 150, nom

    def test_la_scene_du_disque_n_est_pas_un_arret_tab(self, qtbot, jumeau_allume):
        from PyQt6.QtCore import Qt
        d = self._disque(qtbot)
        assert d._gpu.focusPolicy() == Qt.FocusPolicy.NoFocus

    def test_eteint_le_disque_se_peint_lui_meme(self, qtbot, monkeypatch):
        monkeypatch.setenv("ACCIO_FOND_GPU", "1")
        monkeypatch.setenv("ACCIO_CARROUSEL_GPU", "0")
        d = self._disque(qtbot)
        assert d._gpu is None

    def test_sans_couleur_de_fond_pas_de_scene(self, qtbot, jumeau_allume):
        d = self._disque(qtbot, fond_scene=None)
        assert d._gpu is None
