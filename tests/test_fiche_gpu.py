"""La fiche sur la carte graphique (`fiche_gpu`) : le jumeau visuel, derrière son interrupteur.

Rien ici ne juge des pixels de la scène (voir la comparaison par grab dans le
paragraphe `fiche_gpu` d'ARCHITECTURE_UI.md) : ces tests tiennent le câblage, à savoir
que les vrais widgets ne peignent plus et que leur double suit chaque changement.
"""

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QPointF, QRectF
from PyQt6.QtGui import QEnterEvent
from PyQt6.QtWidgets import QWidget

from src.ui import fiche_gpu, fond_gpu

pytestmark = pytest.mark.skipif(not fond_gpu.QUICK_DISPONIBLE, reason="Qt Quick absent")


class _ComptePeintures(QObject):
    def __init__(self):
        super().__init__()
        self.n = 0

    def eventFilter(self, _o, e):
        if e.type() == QEvent.Type.Paint:
            self.n += 1
        return False


def _allumer(monkeypatch):
    monkeypatch.setenv("ACCIO_FOND_GPU", "1")
    monkeypatch.setenv("ACCIO_FICHE_GPU", "1")


def _detail_allume(make_window, monkeypatch, qtbot):
    _allumer(monkeypatch)
    win = make_window()
    detail = win._detail
    win.show()
    qtbot.wait(30)
    return win, detail, detail._jumeau


def _attendre(jumeau, qtbot):
    """Le passage différé du minuteur, puis ce que la scène a reçu."""
    qtbot.waitUntil(lambda: not jumeau._minuteur.isActive(), timeout=1000)
    qtbot.wait(5)


def _noeud(jumeau, w):
    n = jumeau.noeud_de(w)
    assert n is not None
    return n


# ── L'interrupteur ──


def test_allume_par_defaut_avec_le_fond_sur_la_carte(monkeypatch):
    monkeypatch.delenv("ACCIO_FICHE_GPU", raising=False)
    monkeypatch.setenv("ACCIO_FOND_GPU", "1")
    assert fiche_gpu.actif()


def test_a_zero_il_s_eteint_meme_avec_le_fond_sur_la_carte(monkeypatch):
    monkeypatch.setenv("ACCIO_FICHE_GPU", "0")
    monkeypatch.setenv("ACCIO_FOND_GPU", "1")
    assert not fiche_gpu.actif()


def test_sans_le_fond_sur_la_carte_il_reste_eteint(monkeypatch):
    monkeypatch.delenv("ACCIO_FICHE_GPU", raising=False)
    monkeypatch.setenv("ACCIO_FOND_GPU", "0")
    assert not fiche_gpu.actif()


def test_eteint_garde_l_effet_d_opacite_et_aucun_jumeau(make_window, monkeypatch):
    monkeypatch.setenv("ACCIO_FICHE_GPU", "0")
    win = make_window()
    assert win._detail._jumeau is None
    assert win._detail._info.graphicsEffect() is win._detail._info_opacity
    assert win._detail._info.updatesEnabled()


def test_scene_cassee_retombe_sur_les_widgets(make_window, monkeypatch, tmp_path):
    casse = tmp_path / "FicheJumeau.qml"
    casse.write_text("ceci n'est pas du QML", encoding="utf-8")
    monkeypatch.setattr(fiche_gpu, "_QML", casse)
    _allumer(monkeypatch)
    win = make_window()
    assert win._detail._jumeau is None
    assert win._detail._info.graphicsEffect() is win._detail._info_opacity


def test_le_qml_du_jumeau_n_importe_que_qt_quick():
    source = fiche_gpu._QML.read_text(encoding="utf-8")
    assert source.startswith("import QtQuick\n") and "QtQuick.Controls" not in source


# ── Le jumeau ──


def test_les_widgets_ne_se_peignent_plus_mais_gardent_leurs_geometries(make_window, monkeypatch, qtbot):
    win, detail, jumeau = _detail_allume(make_window, monkeypatch, qtbot)
    assert jumeau is not None
    assert detail._info.graphicsEffect() is None
    assert not detail._info.updatesEnabled() and not detail._audio_bar.updatesEnabled()
    titre = detail._info._title
    compte = _ComptePeintures()
    titre.installEventFilter(compte)
    detail.update()
    win.repaint()
    qtbot.wait(30)
    assert compte.n == 0
    # La géométrie des enfants, elle, continue de bouger.
    avant = titre.geometry()
    detail._info.setGeometry(0, 40, 400, 300)
    qtbot.waitUntil(lambda: titre.geometry() != avant or titre.width() < 700, timeout=2000)
    assert titre.width() <= 400


def test_un_bouton_recree_par_un_refresh_ne_se_peint_pas(make_window, monkeypatch, qtbot):
    win, detail, jumeau = _detail_allume(make_window, monkeypatch, qtbot)
    _attendre(jumeau, qtbot)
    panneau = detail._action_panel
    vieux = panneau.findChild(QWidget, "btnDownload") or panneau.findChild(QWidget, "btnPlay")
    assert vieux is not None
    panneau.refresh()
    _attendre(jumeau, qtbot)
    neuf = panneau.findChild(QWidget, "btnDownload") or panneau.findChild(QWidget, "btnPlay")
    assert neuf is not None and neuf is not vieux
    assert not neuf.updatesEnabled()
    compte = _ComptePeintures()
    neuf.installEventFilter(compte)
    detail.update()
    win.repaint()
    qtbot.wait(30)
    assert compte.n == 0, "le bouton neuf ne se peint pas"
    assert _noeud(jumeau, neuf).pose["source"], "c'est son double qui le montre"


def test_le_texte_d_un_libelle_part_dans_son_double(make_window, monkeypatch, qtbot):
    _, detail, jumeau = _detail_allume(make_window, monkeypatch, qtbot)
    titre = detail._info._title
    _attendre(jumeau, qtbot)
    n = _noeud(jumeau, titre)
    version = n.version
    source = n.pose["source"]
    titre.setText("Un autre titre")
    _attendre(jumeau, qtbot)
    assert n.version > version
    assert n.pose["source"] != source and "image://jumeau/" in n.pose["source"]


def test_la_visibilite_et_la_geometrie_suivent(make_window, monkeypatch, qtbot):
    _, detail, jumeau = _detail_allume(make_window, monkeypatch, qtbot)
    titre = detail._info._title
    _attendre(jumeau, qtbot)
    n = _noeud(jumeau, titre)
    assert n.pose["visible"] is True
    titre.hide()
    _attendre(jumeau, qtbot)
    assert n.pose["visible"] is False
    titre.show()
    _attendre(jumeau, qtbot)
    assert n.pose["visible"] is True
    # Un déplacement seul (ni taille, ni affichage) : c'est `Move` qui doit le signaler.
    # Le titre est dans la zone défilante : c'est son rognage qui part avec la fiche.
    zone = jumeau._racine.property("zoneDefilante")
    assert n.groupe == "contenu" and zone.width() > 0
    detail._info.move(detail._info.x() + 7, detail._info.y() + 11)
    _attendre(jumeau, qtbot)
    assert jumeau._racine.property("zoneDefilante") == zone.translated(7, 11)


def test_le_double_suit_le_defilement(make_window, monkeypatch, qtbot):
    _, detail, jumeau = _detail_allume(make_window, monkeypatch, qtbot)
    _attendre(jumeau, qtbot)
    contenu = jumeau._contenu
    assert contenu is not None
    n = next(x for x in jumeau._noeuds.values() if x.groupe == "contenu" and x.pose.get("visible"))
    x, y = n.pose["x"], n.pose["y"]
    contenu.move(contenu.x(), contenu.y() - 17)
    _attendre(jumeau, qtbot)
    assert (n.pose["x"], n.pose["y"]) == (x, y - 17)


def test_le_survol_d_un_bouton_refait_son_image_sans_toucher_le_reste(make_window, monkeypatch, qtbot):
    _, detail, jumeau = _detail_allume(make_window, monkeypatch, qtbot)
    _attendre(jumeau, qtbot)
    bouton = detail._action_panel.findChild(QWidget, "btnDownload")
    if bouton is None:      # selon l'état du catalogue de test : le bouton de jeu installé
        bouton = detail._action_panel.findChild(QWidget, "btnPlay")
    assert bouton is not None
    n = _noeud(jumeau, bouton)
    versions = {cle: x.version for cle, x in jumeau._noeuds.items()}
    QCoreApplication.sendEvent(bouton, QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5)))
    _attendre(jumeau, qtbot)
    assert n.version > versions[n.cle]
    autres_changes = [c for c, x in jumeau._noeuds.items()
                      if c != n.cle and x.version != versions[c]]
    assert not autres_changes


def test_la_barre_de_progression_change_par_son_update(make_window, monkeypatch, qtbot):
    win, detail, jumeau = _detail_allume(make_window, monkeypatch, qtbot)
    from src.core.game_manager import GameManager, GameState
    monkeypatch.setattr(GameManager, "get_state", lambda self, gid: GameState.DOWNLOADING)
    detail._action_panel.refresh()
    detail._position_info()
    _attendre(jumeau, qtbot)
    carte = detail._action_panel._carte
    assert carte is not None
    n = _noeud(jumeau, carte._barre)
    version = n.version
    carte.regler_telechargement(50 * 1024 * 1024, 100 * 1024 * 1024, 1e6, 10)
    _attendre(jumeau, qtbot)
    assert n.version > version
    assert jumeau._racine is not None


def test_un_refresh_oublie_les_vieux_boutons_et_montre_les_nouveaux(make_window, monkeypatch, qtbot):
    _, detail, jumeau = _detail_allume(make_window, monkeypatch, qtbot)
    _attendre(jumeau, qtbot)
    vieux = detail._action_panel.findChild(QWidget, "btnDownload") or detail._action_panel.findChild(QWidget, "btnPlay")
    assert vieux is not None
    cle = _noeud(jumeau, vieux).cle
    detail._action_panel.refresh()
    qtbot.wait(50)
    assert cle not in jumeau._noeuds
    neuf = detail._action_panel.findChild(QWidget, "btnDownload") or detail._action_panel.findChild(QWidget, "btnPlay")
    assert neuf is not None
    assert _noeud(jumeau, neuf).pose["visible"] is True


def test_le_mode_cinema_masque_la_fiche_et_garde_la_barre(make_window, monkeypatch, qtbot):
    from src.ui.video_player import VideoPlayer
    monkeypatch.setattr(VideoPlayer, "is_playing", True)
    _, detail, jumeau = _detail_allume(make_window, monkeypatch, qtbot)
    detail._audio_bar.set_mode_fin(False)
    detail._position_audio_bar()
    detail._audio_bar.show()
    _attendre(jumeau, qtbot)
    titre, barre = detail._info._title, detail._audio_bar
    detail.set_cinema(True)
    _attendre(jumeau, qtbot)
    assert _noeud(jumeau, titre).pose["visible"] is False
    assert _noeud(jumeau, barre).pose["visible"] is True
    detail.set_cinema(False)


def test_le_changement_de_jeu_change_le_double_du_titre(make_window, monkeypatch, qtbot):
    win, detail, jumeau = _detail_allume(make_window, monkeypatch, qtbot)
    titre = detail._info._title
    _attendre(jumeau, qtbot)
    n = _noeud(jumeau, titre)
    texte, source, image = titre.text(), n.pose["source"], n.image
    # Même taille : seul le texte peut dire que l'image est périmée.
    titre.setFixedSize(titre.size())
    win._carousel.select_next()
    qtbot.waitUntil(lambda: titre.text() != texte, timeout=2000)
    _attendre(jumeau, qtbot)
    assert n.image.size() == image.size()
    assert n.pose["source"] != source and n.image != image, "le double montre le nouveau titre"
    assert jumeau._images.images[n.cle] is n.image
    assert detail._info.graphicsEffect() is None


def test_le_fondu_de_la_fiche_est_une_animation_de_la_scene(make_window, monkeypatch, qtbot):
    win, detail, jumeau = _detail_allume(make_window, monkeypatch, qtbot)
    fondu = jumeau._racine.findChild(QObject, "ficheFondu")
    assert fondu is not None
    win._carousel.select_next()
    assert fondu.property("opacity") < 0.5   # la fiche repart de zéro
    qtbot.waitUntil(lambda: fondu.property("opacity") > 0.99, timeout=2000)


def test_le_fournisseur_d_images_repond_meme_pour_un_widget_parti(qtbot):
    fournisseur = fiche_gpu._Images()
    image, taille = fournisseur.requestImage("9999/1", QRectF(0, 0, 1, 1).size().toSize())
    assert not image.isNull() and taille.width() == 1
