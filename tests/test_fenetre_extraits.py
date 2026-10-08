"""Ce qui est sorti de `main_window` le 2026-09-30, exercé SANS la fenêtre.

C'était la raison de l'extraction : noyées dans une fenêtre de 978 lignes, ces
décisions ne s'exerçaient qu'en construisant tout le launcher, donc presque
jamais une par une. Les tests d'intégration (`test_integration_smoke.py`)
gardent le câblage ; ceux-ci gardent les décisions.
"""

from types import SimpleNamespace

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import QEvent, QObject, QPointF, QRect, Qt, pyqtSignal  # noqa: E402
from PyQt6.QtGui import QKeyEvent, QMouseEvent  # noqa: E402
from PyQt6.QtWidgets import QLineEdit, QPushButton, QWidget  # noqa: E402

from src.core.i18n import set_language  # noqa: E402


@pytest.fixture(autouse=True)
def _francais():
    set_language("fr")


class _Ops:
    def __init__(self, occupe=False):
        self.is_busy = occupe


# ─── Barre de statut ───

class TestBarreDeStatut:
    def _barre(self, qtbot, faits=True, occupe=False):
        from src.ui.barre_de_statut import BarreDeStatut
        barre = BarreDeStatut(SimpleNamespace(faits_du_jour=faits), _Ops(occupe))
        qtbot.addWidget(barre)
        return barre

    def test_au_repos_le_fait_du_jour_et_non_pret(self, qtbot):
        barre = self._barre(qtbot)
        assert barre.currentMessage() == barre.au_repos() != "Prêt"

    def test_sans_fait_du_jour_on_retombe_sur_pret(self, qtbot):
        assert self._barre(qtbot, faits=False).currentMessage() == "Prêt"

    def test_ordre_des_messages_ambiants(self, qtbot):
        barre = self._barre(qtbot)
        barre.ambiance(2, en_ligne=False)
        assert "2 mises à jour" in barre.currentMessage(), "une mise à jour passe avant tout"
        barre.ambiance(0, en_ligne=False)
        assert "Hors ligne" in barre.currentMessage()
        assert "jouables" in barre.currentMessage(), "dire ce qui reste possible"
        barre.ambiance(0, en_ligne=True)
        assert barre.currentMessage() == barre.au_repos()

    def test_un_telechargement_de_jeu_n_est_jamais_ecrase(self, qtbot):
        barre = self._barre(qtbot, occupe=True)
        barre.showMessage("Téléchargement de HP5…")
        barre.ambiance(3, en_ligne=False)
        barre.bandes_annonces(0, 8, 10, 100)
        barre.bandes_annonces_finies(8, 0)
        assert barre.currentMessage() == "Téléchargement de HP5…"

    def test_bandes_annonces_rang_et_pourcentage(self, qtbot):
        barre = self._barre(qtbot)
        barre.bandes_annonces(2, 8, 50, 200)
        assert barre.currentMessage() == "Bandes-annonces : 3/8 (25 %)"
        barre.bandes_annonces(7, 8, 0, 0)     # taille inconnue : pas de division par zéro
        assert barre.currentMessage() == "Bandes-annonces : 8/8 (0 %)"
        barre.bandes_annonces_finies(8, 0)
        assert barre.currentMessage() == barre.au_repos()


# ─── Géométrie d'ouverture ───

class TestGeometrieDOuverture:
    def _g(self, x, y, largeur, hauteur):
        from src.ui.window_chrome import geometrie_d_ouverture
        return geometrie_d_ouverture(QRect(x, y, largeur, hauteur))

    def test_un_portable_1366x768_tient_entier(self):
        """728 px utiles une fois la barre des tâches retirée : l'ancien 1200x800 débordait."""
        g = self._g(0, 0, 1366, 728)
        assert QRect(0, 0, 1366, 728).contains(g)
        assert (g.width(), g.height()) == (980, 660)

    def test_un_grand_ecran_est_plafonne_et_centre(self):
        g = self._g(0, 0, 2560, 1400)
        assert (g.width(), g.height()) == (1320, 880)
        assert g.center().x() in (1279, 1280) and g.center().y() in (699, 700)

    def test_jamais_plus_grand_que_l_ecran(self):
        g = self._g(0, 0, 800, 600)
        assert g.width() <= 800 and g.height() <= 600

    def test_un_second_ecran_decale(self):
        """Écran à droite du principal : la fenêtre s'ouvre SUR lui, pas en 0,0."""
        g = self._g(1920, 0, 1920, 1040)
        assert QRect(1920, 0, 1920, 1040).contains(g)


# ─── Touches globales ───

class _Carrousel:
    def __init__(self):
        self.pas = []

    def select_prev(self):
        self.pas.append(-1)

    def select_next(self):
        self.pas.append(+1)


class _Fiche:
    def __init__(self, cinema=False):
        self._cinema = cinema

    def cinema(self):
        return self._cinema

    def set_cinema(self, oui):
        self._cinema = oui


def _touche(cle):
    return QKeyEvent(QEvent.Type.KeyPress, cle, Qt.KeyboardModifier.NoModifier)


class TestToucheGlobale:
    def _jouer(self, cle, fiche=None, active=True):
        from src.ui.clavier_global import touche_globale
        carrousel = _Carrousel()
        pris = touche_globale(_touche(cle), carrousel, fiche or _Fiche(), active)
        return pris, carrousel.pas

    def test_les_fleches_naviguent(self):
        assert self._jouer(Qt.Key.Key_Right) == (True, [+1])
        assert self._jouer(Qt.Key.Key_Left) == (True, [-1])

    def test_fenetre_inactive_rien(self):
        assert self._jouer(Qt.Key.Key_Right, active=False) == (False, [])

    def test_les_autres_touches_passent(self):
        assert self._jouer(Qt.Key.Key_Space) == (False, [])

    def test_echap_ne_sort_que_du_plein_ecran(self):
        fiche = _Fiche(cinema=True)
        assert self._jouer(Qt.Key.Key_Escape, fiche)[0] is True
        assert fiche.cinema() is False
        assert self._jouer(Qt.Key.Key_Escape, fiche)[0] is False, (
            "rien à quitter : la touche reste aux widgets, la fenêtre ne se ferme pas")

    def test_un_champ_texte_garde_ses_fleches(self, qtbot):
        champ = QLineEdit()
        qtbot.addWidget(champ)
        champ.show()
        champ.activateWindow()
        champ.setFocus()
        qtbot.waitUntil(champ.hasFocus, timeout=2000)
        assert self._jouer(Qt.Key.Key_Left) == (False, [])

    def test_un_bouton_ne_les_garde_pas(self, qtbot):
        """Le cas qui a motivé le filtre : après un clic, le bouton a le focus."""
        bouton = QPushButton("JOUER")
        qtbot.addWidget(bouton)
        bouton.show()
        bouton.activateWindow()
        bouton.setFocus()
        qtbot.waitUntil(bouton.hasFocus, timeout=2000)
        assert self._jouer(Qt.Key.Key_Right) == (True, [+1])


# ─── Bords de la fenêtre sans cadre ───

class _Poignee:
    def __init__(self):
        self.bords = []

    def startSystemResize(self, bords):
        self.bords.append(bords)
        return True


class _Fenetre(QWidget):
    """Une vraie fenêtre de 400x300 dont on règle l'état agrandi / actif."""

    def __init__(self, agrandie=False, active=True):
        super().__init__()
        self.resize(400, 300)
        self._agrandie, self._active = agrandie, active
        self.poignee = _Poignee()

    def isMaximized(self):
        return self._agrandie

    def isActiveWindow(self):
        return self._active

    def windowHandle(self):
        return self.poignee

    def mapFromGlobal(self, point):     # repère global = repère de la fenêtre
        return point


def _clic(x, y, bouton=Qt.MouseButton.LeftButton):
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(x, y), QPointF(x, y),
                       bouton, bouton, Qt.KeyboardModifier.NoModifier)


class TestBordsDeLaFenetre:
    def _chrome(self, qtbot, **etat):
        from src.ui.window_chrome import WindowChrome
        fen = _Fenetre(**etat)
        qtbot.addWidget(fen)
        return fen, WindowChrome(fen)

    def test_un_clic_sur_le_bord_redimensionne(self, qtbot):
        fen, chrome = self._chrome(qtbot)
        assert chrome.evenement(fen, _clic(398, 150)) is True
        assert fen.poignee.bords == [Qt.Edge.RightEdge]

    def test_un_clic_au_milieu_reste_un_clic(self, qtbot):
        fen, chrome = self._chrome(qtbot)
        assert chrome.evenement(fen, _clic(200, 150)) is False
        assert fen.poignee.bords == []

    def test_agrandie_aucun_bord(self, qtbot):
        fen, chrome = self._chrome(qtbot, agrandie=True)
        assert chrome.evenement(fen, _clic(0, 0)) is False

    def test_le_clic_droit_ne_redimensionne_pas(self, qtbot):
        fen, chrome = self._chrome(qtbot)
        assert chrome.evenement(fen, _clic(398, 150, Qt.MouseButton.RightButton)) is False

    def test_seulement_pour_nos_widgets(self, qtbot):
        """Le filtre est posé sur TOUTE l'application : un dialogue ouvert au bord
        de la fenêtre ne doit pas se mettre à la redimensionner."""
        fen, chrome = self._chrome(qtbot)
        autre = QWidget()
        qtbot.addWidget(autre)
        assert chrome.evenement(autre, _clic(398, 150)) is False

    def test_le_curseur_est_relache_en_sortant(self, qtbot):
        fen, chrome = self._chrome(qtbot)
        survol = QMouseEvent(QEvent.Type.MouseMove, QPointF(398, 150), QPointF(398, 150),
                             Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                             Qt.KeyboardModifier.NoModifier)
        chrome.evenement(fen, survol)
        assert chrome.curseur_pose
        chrome.evenement(fen, QEvent(QEvent.Type.Leave))
        assert not chrome.curseur_pose, "curseur de redimensionnement collé à l'application"


# ─── Vérification forcée ───

class _Checker(QObject):
    catalog_updated = pyqtSignal(object)
    launcher_update = pyqtSignal(str, str, str, str, str)
    finished = pyqtSignal()

    def __init__(self, catalogue=None, launcher=None):
        super().__init__()
        self._catalogue, self._launcher = catalogue, launcher

    def start(self):
        if self._catalogue is not None:
            self.catalog_updated.emit(self._catalogue)
        if self._launcher is not None:
            self.launcher_update.emit(*self._launcher)
        self.finished.emit()


class _Dialogue(QObject):
    """Ce que la vérification dit au dialogue des Paramètres."""

    def __init__(self):
        super().__init__()
        self.statuts, self.versions = [], []

    def isVisible(self):      # la sonde de vivacité : lève RuntimeError sur un objet détruit
        return True

    def show_update_status(self, message, success=True):
        self.statuts.append((message, success))

    def update_catalog_version(self, version):
        self.versions.append(version)


class TestVerificationForcee:
    def _verifier(self, checker, *, en_ligne=True, catalog_only=True, url=""):
        from src.ui import verification_forcee
        dlg, recus = _Dialogue(), {"catalogue": [], "launcher": []}
        verification_forcee.verifier(
            checker, dlg, catalog_only=catalog_only,
            sur_catalogue=recus["catalogue"].append,
            sur_launcher=lambda *a: recus["launcher"].append(a),
            en_ligne=lambda: en_ligne, url_launcher=lambda: url)
        return dlg, recus

    def test_hors_ligne_c_est_un_echec_et_il_le_dit(self):
        dlg, _ = self._verifier(_Checker(), en_ligne=False)
        assert dlg.statuts == [("Hors ligne — vérification impossible.", False)]

    def test_rien_de_neuf_en_ligne(self):
        dlg, _ = self._verifier(_Checker())
        assert dlg.statuts == [("Catalogue déjà à jour", True)]

    def test_un_nouveau_catalogue_arrive_a_la_fenetre_et_au_dialogue(self):
        catalogue = SimpleNamespace(catalog_version="0.36")
        dlg, recus = self._verifier(_Checker(catalogue=catalogue))
        assert recus["catalogue"] == [catalogue]
        assert dlg.versions == ["0.36"]
        assert not any("déjà à jour" in m for m, _ in dlg.statuts), "il vient de changer"

    def test_l_empreinte_du_launcher_arrive_entiere(self):
        """Les CINQ arguments : l'empreinte SHA-256 est le quatrième (règle 9)."""
        annonce = ("9.9.9", "https://x", "https://x/a.exe", "ab" * 32, "notes")
        dlg, recus = self._verifier(_Checker(launcher=annonce), catalog_only=False,
                                    url="https://x")
        assert recus["launcher"] == [annonce]
        assert ("Launcher v9.9.9 disponible !", True) in dlg.statuts

    def test_le_catalogue_seul_n_ecoute_pas_le_launcher(self):
        annonce = ("9.9.9", "https://x", "", "", "")
        _, recus = self._verifier(_Checker(launcher=annonce), catalog_only=True)
        assert recus["launcher"] == []

    def test_un_dialogue_ferme_n_est_plus_touche(self):
        """Le checker peut finir après la fermeture des Paramètres."""
        from src.ui import verification_forcee
        checker, dlg = _Checker(), _Dialogue()
        checker.start = lambda: None         # la réponse arrivera plus tard
        verification_forcee.verifier(
            checker, dlg, catalog_only=True, sur_catalogue=lambda c: None,
            sur_launcher=lambda *a: None, en_ligne=lambda: True, url_launcher=lambda: "")
        dlg.destroyed.emit()
        checker.finished.emit()
        assert dlg.statuts == []


# ─── Les deux questions ───

class _FausseBoite:
    """Relève ce qu'affiche la boîte ; répond par le bouton `reponse`."""
    reponse = ""
    vues: list = []

    def __init__(self, parent=None):
        self.textes = {}
        self.boutons = []
        _FausseBoite.vues.append(self)

    def setWindowTitle(self, t): self.textes["titre"] = t
    def setIcon(self, *a): pass
    def setTextFormat(self, f): self.textes["format"] = f
    def setText(self, t): self.textes["texte"] = t
    def setInformativeText(self, t): self.textes["detail"] = t
    def setDefaultButton(self, b): self.textes["defaut"] = b.texte

    def addButton(self, texte, role):
        # Un OBJET par bouton : le code compare le bouton cliqué par identité.
        bouton = SimpleNamespace(texte=texte)
        self.boutons.append(bouton)
        return bouton

    def exec(self): return 0

    def clickedButton(self):
        return next((b for b in self.boutons if b.texte == _FausseBoite.reponse), None)


@pytest.fixture
def boite(monkeypatch):
    """Faux posé sur le MODULE, jamais sur la classe Qt (règle 12)."""
    from src.ui import dialogues_fenetre
    _FausseBoite.vues = []
    _FausseBoite.Icon = dialogues_fenetre.QMessageBox.Icon
    _FausseBoite.ButtonRole = dialogues_fenetre.QMessageBox.ButtonRole
    monkeypatch.setattr(dialogues_fenetre, "QMessageBox", _FausseBoite)
    return _FausseBoite


class TestLesDeuxQuestions:
    def test_les_notes_passent_avant_la_mecanique(self, boite):
        from src.ui.dialogues_fenetre import proposer_mise_a_jour
        boite.reponse = "Plus tard"
        assert proposer_mise_a_jour(None, "9.9", "## Corrections\n- HP6", auto=True) is False
        detail = boite.vues[0].textes["detail"]
        assert detail.index("Corrections") < detail.index("automatiquement")
        assert boite.vues[0].textes["format"] == Qt.TextFormat.PlainText, (
            "les notes viennent de GitHub : jamais interprétées")

    def test_sans_notes_on_n_invente_rien(self, boite):
        from src.ui.dialogues_fenetre import proposer_mise_a_jour
        boite.reponse = "Mettre à jour maintenant"
        assert proposer_mise_a_jour(None, "9.9", "  ", auto=False) is True
        assert boite.vues[0].textes["detail"].startswith("La page de téléchargement")
        assert boite.vues[0].textes["defaut"] == "Mettre à jour maintenant"

    def test_fermer_pendant_un_telechargement(self, boite):
        from src.ui.dialogues_fenetre import confirmer_fermeture
        boite.reponse = "Continuer"
        assert confirmer_fermeture(None, "HP5", "download") is False
        assert "reprendra" in boite.vues[0].textes["detail"]
        assert boite.vues[0].textes["defaut"] == "Continuer", "le choix sûr par défaut"

    def test_fermer_pendant_une_installation(self, boite):
        from src.ui.dialogues_fenetre import confirmer_fermeture
        boite.reponse = "Quitter quand même"
        assert confirmer_fermeture(None, None, "install") is True
        assert "« un jeu » est en cours." == boite.vues[0].textes["texte"]
        assert "refaite" in boite.vues[0].textes["detail"]
