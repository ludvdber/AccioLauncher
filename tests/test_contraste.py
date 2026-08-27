"""Le texte de la fiche reste-t-il LISIBLE par-dessus ce qui bouge derrière ?

Le projet vérifiait exhaustivement la GÉOMÉTRIE (`tools/audit_geometrie.py` :
troncatures, débordements, barres de défilement) et **rien du contraste**. Trois
défauts y ont vécu jusqu'au 2026-08-26, tous mesurés sur 195 images extraites
des huit bandes-annonces et sur les huit illustrations, sous les glyphes
eux-mêmes :

- le voile d'assombrissement n'était posé que sur l'illustration, jamais sur la
  bande-annonce (titre 27 % des plans sous le seuil AA, description 25 %) ;
- la description était semi-transparente, donc elle se MÉLANGEAIT au fond :
  40 % des illustrations sous le seuil, pire cas 3,41 ;
- la ligne méta, en `#8a8aaa`, échouait sur 44 % des illustrations — et c'est
  elle qui porte le compteur de téléchargements.

Ces tests ferment les trois. Ils mesurent le rendu RÉEL du `BackgroundWidget`
sous le masque d'encre de chaque libellé, pas une couleur théorique sur un fond
supposé : c'est précisément l'écart entre les deux qui avait laissé passer les
défauts.

Note offscreen : les couleurs, elles, ne sont pas affectées par l'absence de
base de polices. La police substituée change la FORME des glyphes, donc le
masque — mais un masque plus large est plus sévère, pas plus laxiste.
"""

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import QPoint  # noqa: E402
from PyQt6.QtGui import QColor, QImage, QRegion  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402


@pytest.fixture
def fenetre(qtbot, tmp_path, monkeypatch):
    """MainWindow sur une config temporaire — même recette que le smoke test.

    Dupliquée plutôt qu'importée : `make_window` vit dans
    `test_integration_smoke.py`, et importer une fixture d'un module de tests à
    l'autre crée une dépendance qu'aucun des deux ne déclare.
    """
    monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
    monkeypatch.setattr("src.ui.main_window.MainWindow._start_update_check",
                        lambda self: None)
    from src.core.config import Config
    Config(install_path=tmp_path / "games", cache_path=tmp_path / "games" / ".cache",
           langue="fr", autoplay_videos=False).save()
    from src.ui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    win.resize(1200, 800)
    yield win
    from src.core.i18n import set_language
    from src.ui.theme import set_theme
    set_language("fr")
    set_theme("poudlard")

# Seuil WCAG 2.1 niveau AA pour du texte de taille courante.
AA = 4.5


def _luminance(r: int, g: int, b: int) -> float:
    def canal(c: float) -> float:
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)


def _contraste(c1, c2) -> float:
    a, b = _luminance(*c1), _luminance(*c2)
    if a < b:
        a, b = b, a
    return (a + 0.05) / (b + 0.05)


def _masque(widget: QWidget) -> QImage:
    """Le libellé SEUL : fond transparent, encre opaque.

    Sans `DrawWindowBackground`, `render` n'inscrit que les glyphes. C'est ce
    qui permet de ne relire le fond QUE là où il y a de l'encre — mesurer tout
    le rectangle d'un QLabel en wordWrap échantillonne surtout du vide, à un
    endroit où le voile gauche est déjà affaibli, et surestime le problème.
    """
    img = QImage(widget.size(), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    widget.render(img, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    return img


def _origine(widget: QWidget, vue: QWidget, bg: QWidget) -> QPoint:
    """Coin haut-gauche de `widget` dans le repère du fond.

    `mapTo(bg, ...)` serait FAUX : `_bg` et `_info` sont FRÈRES, tous deux
    enfants de la vue, et `mapTo` exige un ancêtre — Qt le signale à chaque
    appel (« parent must be in parent hierarchy ») et rend une valeur qui ne
    veut rien dire. On passe donc par le parent commun, ce qui est exact parce
    que le fond est posé en `setGeometry(self.rect())`, donc à l'origine de la
    vue. L'assertion le vérifie plutôt que de le supposer.
    """
    assert bg.pos() == QPoint(0, 0), "le fond n'est plus à l'origine de la vue"
    return widget.mapTo(vue, widget.rect().topLeft())


def _pire_fond(rendu: QImage, masque: QImage, org: QPoint):
    """Le fond le plus CLAIR réellement situé sous une lettre.

    C'est lui qui décide si un mot devient illisible ; une moyenne de
    paragraphe ne dirait rien du mot qui tombe sur le ciel. 98e centile plutôt
    que le maximum : un pixel isolé n'est pas un problème de lisibilité.
    """
    fonds = []
    for y in range(masque.height()):
        for x in range(masque.width()):
            if masque.pixelColor(x, y).alpha() < 160:
                continue
            px, py = org.x() + x, org.y() + y
            if 0 <= px < rendu.width() and 0 <= py < rendu.height():
                c = rendu.pixelColor(px, py)
                fonds.append((c.red(), c.green(), c.blue()))
    if not fonds:
        return None
    fonds.sort(key=_luminance_tuple)
    return fonds[int(len(fonds) * 0.98)]


def _luminance_tuple(c) -> float:
    return _luminance(*c)


def _couleur_peinte(widget: QWidget) -> tuple[int, int, int]:
    """Couleur RÉELLEMENT peinte par le libellé, alpha compris.

    On la relit sur un rendu par-dessus du noir plutôt que de la déduire de la
    feuille de style : c'est justement l'alpha oublié dans un `rgba()` qui
    faisait échouer la description, et une valeur lue dans le CSS ne l'aurait
    pas montré.
    """
    img = QImage(widget.size(), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    widget.render(img, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    meilleur, sommet = (0, 0, 0), -1.0
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() < 250:
                continue
            lum = _luminance(c.red(), c.green(), c.blue())
            if lum > sommet:
                sommet, meilleur = lum, (c.red(), c.green(), c.blue())
    return meilleur


def _composite(couleur, alpha: float, fond):
    return tuple(round(alpha * couleur[i] + (1 - alpha) * fond[i]) for i in range(3))


class TestVoileSurLesDeuxChemins:
    """Le voile était dans la branche `else` : la vidéo ne le recevait pas.

    L'invariant vérifié ici n'est pas « le voile vaut 77 » mais « une
    bande-annonce et une illustration sont traitées PAREIL ». Il survit donc à
    un ajustement de la valeur, et il échoue dès qu'un des deux chemins
    reprend un traitement que l'autre n'a pas.
    """

    @staticmethod
    def _blanc(tmp_path):
        img = QImage(400, 300, QImage.Format.Format_RGB32)
        img.fill(QColor(255, 255, 255))
        chemin = tmp_path / "blanc.png"
        img.save(str(chemin))
        return chemin, img

    def test_video_et_illustration_sont_assombries_pareil(self, qtbot, tmp_path):
        from src.ui.background_widget import BackgroundWidget

        chemin, img = self._blanc(tmp_path)
        bg = BackgroundWidget()
        qtbot.addWidget(bg)
        bg.resize(600, 400)
        bg.set_image(chemin)
        bg.bg_opacity = 1.0
        statique = bg.grab().toImage()

        bg.set_video_frame(img)
        video = bg.grab().toImage()

        assert video == statique, (
            "le chemin vidéo et le chemin illustration ne reçoivent pas le "
            "même traitement — c'est exactement le défaut du voile manquant")

    def test_le_blanc_pur_ressort_assombri(self, qtbot, tmp_path):
        """Contrôle grossier : sans voile, le centre resterait quasi blanc."""
        from src.ui.background_widget import _VOILE_ALPHA, BackgroundWidget

        _, img = self._blanc(tmp_path)
        bg = BackgroundWidget()
        qtbot.addWidget(bg)
        bg.resize(600, 400)
        bg.set_video_frame(img)
        bg.bg_opacity = 1.0
        centre = bg.grab().toImage().pixelColor(300, 120)
        plafond = 255 * (1 - _VOILE_ALPHA / 255) + 1
        assert centre.red() <= plafond, (
            f"blanc rendu à {centre.red()} : le voile n'est pas appliqué")


class TestContrasteSurLesIllustrations:
    """Titre, description et ligne méta au-dessus des VRAIES illustrations.

    Le chemin statique est le plus dur des deux : les jaquettes sont des images
    de promotion, donc claires et contrastées, là où un plan de bande-annonce
    est souvent sombre. C'est d'ailleurs lui qui échouait le plus (78 % pour la
    ligne méta) alors que la plainte d'origine portait sur les bandes-annonces.
    """

    ZONES = ("titre", "description", "meta")

    @staticmethod
    def _mesure(win, jeu):
        vue, bg, info = win._detail, win._detail._bg, win._detail._info
        vue.set_game(jeu)
        for _ in range(6):
            QApplication.processEvents()
        bg.bg_opacity = 1.0
        rendu = bg.grab().toImage()
        out = {}
        for nom, w in (("titre", info._title), ("description", info._desc),
                       ("meta", info._meta)):
            if not w.isVisible():
                continue
            fond = _pire_fond(rendu, _masque(w), _origine(w, vue, bg))
            if fond is None:
                continue
            out[nom] = _contraste(_couleur_peinte(w), fond)
        return out

    def test_les_trois_libelles_tiennent_le_seuil_aa(self, fenetre, qtbot):
        win = fenetre
        win.show()
        qtbot.waitExposed(win)
        fautes = []
        for entree in win.manager.get_games():
            for zone, c in self._mesure(win, entree.game).items():
                if c < AA:
                    fautes.append(f"{entree.game.id}/{zone} : {c:.2f}")
        assert not fautes, (
            "sous le seuil WCAG AA (4.5) sur l'illustration : " + ", ".join(fautes))

    def test_les_anciennes_couleurs_echouaient(self, fenetre, qtbot):
        """Le test ci-dessus ne vaut que s'il pouvait échouer.

        Sans cette contre-épreuve, un seuil trop indulgent ou un masque vide
        passerait au vert sans rien vérifier. On rejoue donc les couleurs
        d'AVANT sur les mêmes fonds : elles doivent tomber.
        """
        anciennes = {"description": ((176, 176, 200), 0.75),   # l'alpha oublié
                     "meta": ((138, 138, 170), 1.0)}           # #8a8aaa
        win = fenetre
        win.show()
        qtbot.waitExposed(win)
        vue, bg, info = win._detail, win._detail._bg, win._detail._info
        widgets = {"description": info._desc, "meta": info._meta}

        echecs = 0
        for entree in win.manager.get_games():
            vue.set_game(entree.game)
            for _ in range(6):
                QApplication.processEvents()
            bg.bg_opacity = 1.0
            rendu = bg.grab().toImage()
            for zone, (couleur, alpha) in anciennes.items():
                w = widgets[zone]
                if not w.isVisible():
                    continue
                fond = _pire_fond(rendu, _masque(w), _origine(w, vue, bg))
                if fond is None:
                    continue
                if _contraste(_composite(couleur, alpha, fond), fond) < AA:
                    echecs += 1
        assert echecs > 0, (
            "les anciennes couleurs passent le seuil : la mesure ne prouve "
            "plus rien, vérifier le masque d'encre avant de croire le test vert")


class _FauxMedia:
    """Le strict necessaire pour que `VideoPlayer` se croie en lecture.

    Tient lieu de `_player`, de `_sink` et de `_audio` a la fois : `stop()` les
    manipule tous les trois, et un stub incomplet ferait echouer le test pour
    une raison sans rapport avec ce qu'il mesure.
    """

    class _Signal:
        def disconnect(self, *_a) -> None:
            pass

    def __init__(self) -> None:
        self.mediaStatusChanged = self._Signal()
        self.videoFrameChanged = self._Signal()

    def stop(self) -> None:
        pass

    def setSource(self, *_a) -> None:
        pass

    def deleteLater(self) -> None:
        pass


class TestModeCinema:
    """La bande-annonce seule : ni voile, ni degrades, ni texte.

    C'est la contrepartie du voile qu'on vient de poser sur le chemin video.
    Le voile existe pour rendre le TEXTE lisible ; quand la vue retire le
    texte, garder le voile reviendrait a ternir l'image pour proteger quelque
    chose qui n'est plus la.

    Ces tests exercent le chemin `set_cinema(True)`, qui n'etait couvert par
    RIEN : `_stop_video` n'appelle que `set_cinema(False)`, et le `and`
    court-circuite la garde. Un `is_playing()` appele comme une methode alors
    que c'est une property y a survecu jusqu'a un rendu manuel.
    """

    @staticmethod
    def _jouer(vue, monkeypatch):
        """Fait croire a la vue qu'une bande-annonce tourne.

        Sur l'INSTANCE, jamais sur la classe. `VideoPlayer` est un `QObject`,
        donc `setattr(type(vue._video), "is_playing", ...)` posait une property
        Python sur un type sip ; monkeypatch la « restaurait » ensuite, et le
        processus mourait sur une violation d'acces DEUX FICHIERS plus loin,
        dans le `paintEvent` d'un widget qui n'y etait pour rien (reproduit le
        2026-08-26 : `test_contraste.py` + `test_integration_smoke.py`, 2 fois
        sur 2 ; chacun des deux fichiers passe SEUL). C'est le piege que
        CLAUDE.md decrit deja pour `ParticleOverlay.update`.

        `is_playing` ne fait que rendre `self._player is not None` : il suffit
        donc de poser un faux lecteur, qui doit aussi savoir s'arreter puisque
        `_stop_video` passe par `VideoPlayer.stop()`.
        """
        faux = _FauxMedia()
        for attribut in ("_player", "_sink", "_audio"):
            monkeypatch.setattr(vue._video, attribut, faux)

    def test_refuse_sans_bande_annonce(self, fenetre):
        """Agrandir une image fixe deja plein ecran ne fait que vider l'ecran."""
        vue = fenetre._detail
        vue.set_cinema(True)
        assert vue.cinema() is False
        assert fenetre._carousel.isVisible() or not fenetre.isVisible()

    def test_bascule_et_escamote_le_reste(self, fenetre, monkeypatch, qtbot):
        win = fenetre
        win.show()
        qtbot.waitExposed(win)
        vue = win._detail
        self._jouer(vue, monkeypatch)

        vue.set_cinema(True)
        assert vue.cinema() is True
        assert not vue._info.isVisible()
        assert not win._carousel.isVisible()
        assert not win._btn_settings.isVisible()
        assert vue._bg.cinema() is True

        vue.set_cinema(False)
        assert vue._info.isVisible()
        assert win._carousel.isVisible()
        assert win._btn_settings.isVisible()

    def test_echap_en_sort(self, fenetre, monkeypatch, qtbot):
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtGui import QKeyEvent

        win = fenetre
        win.show()
        qtbot.waitExposed(win)
        win.activateWindow()
        qtbot.waitUntil(win.isActiveWindow, timeout=2000)
        self._jouer(win._detail, monkeypatch)
        win._detail.set_cinema(True)

        ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                       Qt.KeyboardModifier.NoModifier)
        assert win._handle_global_key(ev) is True
        assert win._detail.cinema() is False
        # Hors plein ecran, Echap ne doit RIEN consommer : la fenetre est sans
        # cadre, la fermer sur une touche pressee par reflexe serait brutal.
        assert win._handle_global_key(ev) is False

    def test_arreter_la_video_en_sort(self, fenetre, monkeypatch, qtbot):
        """Sinon une bande-annonce qui se termine laisse une fenetre vide."""
        win = fenetre
        win.show()
        qtbot.waitExposed(win)
        vue = win._detail
        self._jouer(vue, monkeypatch)
        vue.set_cinema(True)
        vue._stop_video()
        assert vue.cinema() is False
        assert win._carousel.isVisible()

    def test_le_fond_n_est_plus_voile(self, qtbot, tmp_path):
        from src.ui.background_widget import BackgroundWidget

        img = QImage(400, 300, QImage.Format.Format_RGB32)
        img.fill(QColor(255, 255, 255))
        bg = BackgroundWidget()
        qtbot.addWidget(bg)
        bg.resize(600, 400)
        bg.set_video_frame(img)
        bg.bg_opacity = 1.0
        voile = bg.grab().toImage().pixelColor(300, 120).red()
        bg.set_cinema(True)
        nu = bg.grab().toImage().pixelColor(300, 120).red()
        assert nu == 255, f"le mode cinema assombrit encore ({nu})"
        assert nu > voile
