"""Réglages du correctif PC (HP4-HP6) : lecture, écriture en place, fenêtre de réglages."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core import reglages_correctif as rc
from src.core.game_data import GameData
from src.core.i18n import tr

# Extrait fidèle de l'ini du NOUVEAU correctif (tools/make_ini.py), en CRLF.
INI_V2 = "\r\n".join([
    "; Accio Launcher - PC fix",
    "[Accio.Window]",
    "",
    "; Keeps the game running when it loses focus.",
    "KeepRunningInBackground=1",
    "",
    "; Frame-rate limit (0 = none).",
    "FPSLimit=100",
    "",
    "[Accio.Keys]",
    "",
    "; Example (remove the ; to use it)",
    ";MoveUp=Z",
    ";MoveLeft=Q",
    ";MoveDown=S",
    ";MoveRight=D",
    ";Charm=MouseLeft",
    ";Jinx=MouseRight",
    ";Accio=E",
    ";Extremos=R",
    "",
    "[Accio.Graphics]",
    "FXAA=0",
    "",
    "[Accio.Overlay]",
    "ShowFPS=0",
    "ShowFrameTime=0",
    "ShowGraph=0",
    "ShowCPU=0",
    "ShowGPU=0",
    "ShowVRAM=0",
    "ShowRAM=0",
    "ShowLatency=0",
    "OverlayKey=121",
    "",
])

# L'ancien wrapper, celui que portent encore les archives publiées.
INI_ANCIEN = "[MAIN]\r\nFPSLimit = 100 // max fps\r\n[FORCEWINDOWED]\r\nDoNotNotifyOnTaskSwitch = 0\r\n"

AZERTY = (("MoveUp", "Z"), ("MoveLeft", "Q"), ("MoveDown", "S"), ("MoveRight", "D"),
          ("Accio", "E"), ("Extremos", "R"), ("Charm", "MouseLeft"), ("Jinx", "MouseRight"))


@pytest.fixture
def ini(tmp_path):
    p = tmp_path / "d3d9.ini"
    p.write_bytes(INI_V2.encode("ascii"))
    return p


@pytest.fixture
def azerty(monkeypatch):
    monkeypatch.setattr(rc, "touches_preregle", lambda: AZERTY)


class TestCatalogue:
    def test_seuls_les_reglages_connus_dans_l_ordre_d_affichage(self):
        r = rc.reglages_du_jeu(["touches_zqsd", "inconnu_futur", "arriere_plan"])
        assert [x.ident for x in r] == ["arriere_plan", "touches_zqsd"]

    def test_rien_de_declare_rien_de_propose(self):
        assert rc.reglages_du_jeu(()) == ()
        assert rc.reglages_du_jeu(None) == ()

    def test_le_champ_est_lu_depuis_le_catalogue(self):
        base = {"id": "t", "name": "T", "year": 2005, "description": "d", "developer": "d",
                "executable": "T/t.exe", "cover_image": "c.jpg"}
        assert GameData.from_dict({**base, "fix_settings": ["arriere_plan", "../x", 3]}).fix_settings == ("arriere_plan",)
        # Une chaîne n'est pas une liste : sinon chacune de ses lettres deviendrait un réglage.
        assert GameData.from_dict({**base, "fix_settings": "arriere_plan"}).fix_settings == ()
        assert GameData.from_dict(base).fix_settings == ()


class TestQuelCorrectif:
    def test_nouveau_correctif_reconnu(self, ini):
        assert rc.est_nouveau_correctif(ini)

    def test_ancien_wrapper_refuse(self, tmp_path):
        p = tmp_path / "d3d9.ini"
        p.write_bytes(INI_ANCIEN.encode("ascii"))
        assert not rc.est_nouveau_correctif(p)

    def test_fichier_absent(self, tmp_path):
        assert not rc.est_nouveau_correctif(tmp_path / "d3d9.ini")


class TestEcritureEnPlace:
    def test_seule_la_ligne_de_la_cle_change(self, ini):
        avant = ini.read_bytes().split(b"\r\n")
        rc.ecrire(ini, rc.REGLAGES["arriere_plan"], False)
        apres = ini.read_bytes().split(b"\r\n")
        differences = [(a, b) for a, b in zip(avant, apres) if a != b]
        assert differences == [(b"KeepRunningInBackground=1", b"KeepRunningInBackground=0")]
        assert len(avant) == len(apres)

    def test_les_fins_de_ligne_crlf_restent(self, ini):
        rc.ecrire(ini, rc.REGLAGES["limite_fps"], 60)
        brut = ini.read_bytes()
        assert brut.count(b"\r\n") == brut.count(b"\n")

    def test_aller_retour_interrupteur(self, ini):
        r = rc.REGLAGES["arriere_plan"]
        assert rc.lire(ini, r).valeur is True
        rc.ecrire(ini, r, False)
        assert rc.lire(ini, r).valeur is False

    def test_limite_fps(self, ini):
        r = rc.REGLAGES["limite_fps"]
        assert rc.lire(ini, r) == rc.Etat(100)
        rc.ecrire(ini, r, 0)
        assert rc.lire(ini, r) == rc.Etat(0)

    def test_limite_posee_a_la_main_est_montree_pas_ecrasee(self, ini):
        ini.write_bytes(ini.read_bytes().replace(b"FPSLimit=100", b"FPSLimit=90"))
        assert rc.lire(ini, rc.REGLAGES["limite_fps"]) == rc.Etat(90, personnalise=True)

    def test_une_limite_non_proposee_est_refusee(self, ini):
        with pytest.raises(ValueError):
            rc.ecrire(ini, rc.REGLAGES["limite_fps"], 75)

    def test_cle_absente_ajoutee_dans_sa_section(self, ini):
        ini.write_bytes(ini.read_bytes().replace(b"FPSLimit=100\r\n", b""))
        rc.ecrire(ini, rc.REGLAGES["limite_fps"], 60)
        lignes = ini.read_bytes().decode().split("\r\n")
        assert "FPSLimit=60" in lignes
        assert lignes.index("FPSLimit=60") < lignes.index("[Accio.Keys]")

    def test_section_absente_leve(self, tmp_path):
        p = tmp_path / "d3d9.ini"
        p.write_bytes(INI_ANCIEN.encode("ascii"))
        with pytest.raises(ValueError):
            rc.ecrire(p, rc.REGLAGES["arriere_plan"], True)


class TestPerformances:
    def test_eteints_par_defaut_meme_sans_la_cle(self, ini):
        """Le correctif n'affiche rien tant qu'on ne le demande pas : une clé
        absente vaut 0, pas 1 comme KeepRunningInBackground."""
        ini.write_bytes(ini.read_bytes().replace(b"ShowFPS=0\r\n", b""))
        assert rc.lire(ini, rc.REGLAGES["compteur_fps"]) == rc.Etat(False)
        assert rc.lire(ini, rc.REGLAGES["panneau_perfs"]) == rc.Etat(False)

    def test_compteur_aller_retour(self, ini):
        r = rc.REGLAGES["compteur_fps"]
        rc.ecrire(ini, r, True)
        assert b"ShowFPS=1" in ini.read_bytes()
        assert rc.lire(ini, r) == rc.Etat(True)

    def test_le_panneau_allume_ses_sept_lignes_et_pas_le_compteur(self, ini):
        r = rc.REGLAGES["panneau_perfs"]
        rc.ecrire(ini, r, True)
        lignes = ini.read_bytes().decode().split("\r\n")
        for cle in ("ShowFrameTime", "ShowGraph", "ShowCPU", "ShowGPU", "ShowVRAM", "ShowRAM", "ShowLatency"):
            assert f"{cle}=1" in lignes
        assert "ShowFPS=0" in lignes and "OverlayKey=121" in lignes
        assert rc.lire(ini, r) == rc.Etat(True)
        rc.ecrire(ini, r, False)
        assert rc.lire(ini, r) == rc.Etat(False)

    def test_panneau_regle_en_partie_a_la_main(self, ini):
        ini.write_bytes(ini.read_bytes().replace(b"ShowGPU=0", b"ShowGPU=1"))
        assert rc.lire(ini, rc.REGLAGES["panneau_perfs"]) == rc.Etat(False, personnalise=True)

    def test_lissage_aller_retour(self, ini):
        r = rc.REGLAGES["lissage"]
        assert rc.lire(ini, r) == rc.Etat(False)
        rc.ecrire(ini, r, True)
        assert "FXAA=1" in ini.read_bytes().decode().split("\r\n")
        assert rc.lire(ini, r) == rc.Etat(True)

    def test_retires_de_la_liste_a_venir(self):
        assert not any("FPS" in x for x in rc.A_VENIR)


class TestAnticrenelage:
    """Le MSAA : un réglage à CHOIX, par le même mécanisme que la limite d'images."""

    R = rc.REGLAGES["anticrenelage"]

    def test_eteint_quand_la_cle_manque(self, ini):
        assert rc.lire(ini, self.R) == rc.Etat(0)

    def test_aller_retour(self, ini):
        rc.ecrire(ini, self.R, 8)
        lignes = ini.read_bytes().decode().split("\r\n")
        assert "Antialiasing=8" in lignes
        # Ajoutée dans SA section, pas ailleurs.
        assert lignes.index("[Accio.Graphics]") < lignes.index("Antialiasing=8") < lignes.index("[Accio.Overlay]")
        assert rc.lire(ini, self.R) == rc.Etat(8)
        rc.ecrire(ini, self.R, 0)
        assert rc.lire(ini, self.R) == rc.Etat(0)

    def test_seize_pose_a_la_main_montre_pas_ecrase(self, ini):
        """16 (l'ini de HP5) n'est pas proposé : il se montre tel quel."""
        ini.write_bytes(ini.read_bytes().replace(b"FXAA=0", b"FXAA=0\r\nAntialiasing=16"))
        assert rc.lire(ini, self.R) == rc.Etat(16, personnalise=True)

    def test_une_valeur_non_proposee_est_refusee(self, ini):
        with pytest.raises(ValueError):
            rc.ecrire(ini, self.R, 3)

    def test_chaque_choix_a_son_libelle(self):
        """0 se lit par une clé traduite ; aucun réglage à choix n'oublie ce libellé."""
        for r in rc.REGLAGES.values():
            if r.choix:
                assert r.choix[0] == 0 and r.zero and tr(r.zero)
        assert self.R.format_choix.format(8) == "8×"


class TestTouches:
    def test_desactive_par_defaut(self, ini, azerty):
        assert rc.lire(ini, rc.REGLAGES["touches_zqsd"]) == rc.Etat(False)

    def test_activer_decommente_les_huit_lignes(self, ini, azerty):
        r = rc.REGLAGES["touches_zqsd"]
        rc.ecrire(ini, r, True)
        lignes = ini.read_bytes().decode().split("\r\n")
        for action, touche in AZERTY:
            assert f"{action}={touche}" in lignes
        assert rc.lire(ini, r) == rc.Etat(True)
        rc.ecrire(ini, r, False)
        assert rc.lire(ini, r) == rc.Etat(False)
        assert ";MoveUp=Z" in ini.read_bytes().decode().split("\r\n")

    def test_touches_choisies_a_la_main_signalees(self, ini, azerty):
        ini.write_bytes(ini.read_bytes().replace(b";MoveUp=Z", b"MoveUp=I"))
        assert rc.lire(ini, rc.REGLAGES["touches_zqsd"]) == rc.Etat(False, personnalise=True)

    def test_hors_windows_les_positions_us(self, monkeypatch):
        """Sous Linux la disposition de Wine ne se lit pas d'ici : WASD."""
        monkeypatch.setattr(sys, "platform", "linux")
        assert dict(rc.touches_preregle())["MoveUp"] == "W"
        assert dict(rc.touches_preregle())["MoveLeft"] == "A"

    def test_le_texte_porte_les_lettres_du_clavier(self, azerty):
        libelle, aide = rc.textes(rc.REGLAGES["touches_zqsd"])
        assert "ZQSD" in libelle
        assert "ZQSD" in aide and "{" not in aide


# ── La fenêtre ──

def _jeu(tmp_path, fix_settings):
    return GameData.from_dict({
        "id": "hp4", "name": "HP4", "year": 2005, "description": "d", "developer": "d",
        "executable": "HP4/gof_f.exe", "cover_image": "c.jpg", "fix_settings": list(fix_settings)})


def _manager(tmp_path):
    return SimpleNamespace(game_language=lambda g: None, langues_disponibles=lambda g: (),
                           config=SimpleNamespace(install_path=tmp_path))


def _dialogue(qtbot, jeu, manager):
    from src.ui.game_settings_dialog import GameSettingsDialog
    dlg = GameSettingsDialog(jeu, manager, lambda code: True)
    qtbot.addWidget(dlg)
    return dlg


def _textes(dlg):
    from PyQt6.QtWidgets import QLabel
    return " ".join(lb.text() for lb in dlg.findChildren(QLabel))


class TestFenetre:
    def test_jeu_absent(self, qtbot, tmp_path):
        dlg = _dialogue(qtbot, _jeu(tmp_path, ["arriere_plan"]), _manager(tmp_path))
        assert tr("Installez le jeu pour régler son correctif.") in _textes(dlg)

    def test_ancien_correctif_dit_que_ca_arrive(self, qtbot, tmp_path):
        (tmp_path / "HP4").mkdir()
        (tmp_path / "HP4" / "d3d9.ini").write_bytes(INI_ANCIEN.encode("ascii"))
        dlg = _dialogue(qtbot, _jeu(tmp_path, ["arriere_plan"]), _manager(tmp_path))
        assert tr("Ces réglages arrivent avec la prochaine version du correctif "
                  "de ce jeu.") in _textes(dlg)

    def test_un_interrupteur_ecrit_aussitot(self, qtbot, tmp_path):
        from src.ui.toggle_switch import ToggleSwitch
        (tmp_path / "HP4").mkdir()
        ini = tmp_path / "HP4" / "d3d9.ini"
        ini.write_bytes(INI_V2.encode("ascii"))
        dlg = _dialogue(qtbot, _jeu(tmp_path, ["arriere_plan"]), _manager(tmp_path))
        bascules = dlg.findChildren(ToggleSwitch)
        assert len(bascules) == 1 and bascules[0].isChecked()
        bascules[0]._basculer()
        assert b"KeepRunningInBackground=0" in ini.read_bytes()

    def test_la_limite_d_images_ecrit_aussitot(self, qtbot, tmp_path):
        from PyQt6.QtWidgets import QComboBox
        (tmp_path / "HP4").mkdir()
        ini = tmp_path / "HP4" / "d3d9.ini"
        ini.write_bytes(INI_V2.encode("ascii"))
        dlg = _dialogue(qtbot, _jeu(tmp_path, ["limite_fps"]), _manager(tmp_path))
        (choix,) = dlg.findChildren(QComboBox)
        assert choix.currentData() == 100
        choix.setCurrentIndex(choix.findData(60))
        assert b"FPSLimit=60" in ini.read_bytes()

    def test_l_anticrenelage_ecrit_aussitot(self, qtbot, tmp_path):
        from PyQt6.QtWidgets import QComboBox
        (tmp_path / "HP4").mkdir()
        ini = tmp_path / "HP4" / "d3d9.ini"
        ini.write_bytes(INI_V2.encode("ascii"))
        dlg = _dialogue(qtbot, _jeu(tmp_path, ["anticrenelage"]), _manager(tmp_path))
        (choix,) = dlg.findChildren(QComboBox)
        assert choix.currentData() == 0 and choix.currentText() == tr("Désactivé")
        assert [choix.itemText(i) for i in range(1, choix.count())] == ["2×", "4×", "8×"]
        choix.setCurrentIndex(choix.findData(4))
        assert b"Antialiasing=4" in ini.read_bytes()

    def test_tout_hp4_tient_dans_l_ecran_et_fermer_ne_chevauche_rien(self, qtbot, tmp_path):
        """Les sept réglages de HP4 et le titre sur deux lignes : la fenêtre ne
        dépasse pas l'écran (les rubriques défilent), et « Fermer » est SOUS la
        zone qui défile. Le layout seul comptait le titre sur une ligne, et le
        bouton recouvrait les rubriques."""
        from PyQt6.QtWidgets import QPushButton
        (tmp_path / "HP4").mkdir()
        (tmp_path / "HP4" / "d3d9.ini").write_bytes(INI_V2.encode("ascii"))
        tous = ["arriere_plan", "limite_fps", "touches_zqsd", "lissage", "anticrenelage",
                "compteur_fps", "panneau_perfs"]
        jeu = GameData.from_dict({
            "id": "hp4", "name": "Harry Potter et la Coupe de Feu", "year": 2005, "description": "d",
            "developer": "d", "executable": "HP4/gof_f.exe", "cover_image": "c.jpg", "fix_settings": tous})
        dlg = _dialogue(qtbot, jeu, _manager(tmp_path))
        dlg.show()
        qtbot.waitExposed(dlg)
        assert dlg.height() <= dlg.screen().availableGeometry().height()
        (fermer,) = [b for b in dlg.findChildren(QPushButton) if b.text() == tr("Fermer")]
        bas_zone = dlg._defile.geometry().bottom()
        assert fermer.geometry().top() > bas_zone
        assert fermer.geometry().bottom() < dlg.height()

    def test_echec_d_ecriture_remet_le_controle_et_le_dit(self, qtbot, tmp_path, monkeypatch):
        from src.ui.toggle_switch import ToggleSwitch
        (tmp_path / "HP4").mkdir()
        (tmp_path / "HP4" / "d3d9.ini").write_bytes(INI_V2.encode("ascii"))
        dlg = _dialogue(qtbot, _jeu(tmp_path, ["arriere_plan"]), _manager(tmp_path))

        def refus(*_a):
            raise PermissionError("lecture seule")
        monkeypatch.setattr(rc, "_ecrire", refus)
        (bascule,) = dlg.findChildren(ToggleSwitch)
        bascule._basculer()
        assert bascule.isChecked()   # remis sur ce que porte le fichier
        assert not dlg._erreur.isHidden()

    def test_sans_reglage_declare_la_rubrique_reste_verrouillee(self, qtbot, tmp_path):
        dlg = _dialogue(qtbot, _jeu(tmp_path, []), _manager(tmp_path))
        assert tr("BIENTÔT") in _textes(dlg)
        assert tr("Installez le jeu pour régler son correctif.") not in _textes(dlg)


def test_le_module_ne_depend_pas_de_qt():
    source = Path(rc.__file__).read_text(encoding="utf-8")
    assert "PyQt6" not in source
