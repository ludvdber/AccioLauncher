"""La barre lumineuse des manettes PlayStation aux couleurs de la maison.

Aucun test ne touche une vraie manette : conftest._jamais_la_vraie_manette
neutralise l'énumération et le fil d'arrière-plan. Ici, on exerce le rapport
(pur), la lecture de /sys/class/hidraw sur un faux arbre, et `colorer` avec des
manettes et des écritures simulées.
"""
from pathlib import Path

import pytest

from src.core import manette
from src.core.manette import Manette


def test_chaque_maison_a_sa_couleur_et_poudlard_par_defaut():
    for maison in ("gryffondor", "serpentard", "serdaigle", "poufsouffle", "poudlard"):
        assert len(manette.couleur(maison)) == 3
    assert manette.couleur("inconnue") == manette.couleur("poudlard")


class TestRapport:
    def test_dualshock4_usb(self):
        """Relevé sur la manette de Ludo (054C:09CC, rapport de 32 octets), écrit avec succès le 2026-09-27."""
        r = manette.rapport(Manette("x", 0x09CC, 32), (255, 16, 0))
        assert len(r) == 32 and r[0] == 0x05
        assert r[1] == 0x06                      # barre + clignotement (réglé à « fixe »), PAS la vibration
        assert (r[4], r[5]) == (0, 0)            # moteurs arrêtés
        assert (r[6], r[7], r[8]) == (255, 16, 0)
        assert (r[9], r[10]) == (0, 0)           # pas de clignotement

    def test_dualsense_usb(self):
        r = manette.rapport(Manette("x", 0x0CE6, 48), (0, 60, 255))
        assert len(r) == 48 and r[0] == 0x02 and r[2] & 0x04
        assert (r[45], r[46], r[47]) == (0, 60, 255)
        assert (r[3], r[4]) == (0, 0)

    def test_bluetooth_pas_de_rapport_faux(self):
        assert manette.rapport(Manette("x", 0x09CC, 78), (1, 2, 3)) is None
        assert manette.rapport(Manette("x", 0x0CE6, 78), (1, 2, 3)) is None

    def test_valeurs_bornees(self):
        r = manette.rapport(Manette("x", 0x05C4, 32), (300, -5, 12.7))
        assert (r[6], r[7], r[8]) == (255, 0, 12)


class TestIdentifiants:
    def test_chemin_usb(self):
        chemin = r"\\?\hid#vid_054c&pid_09cc&mi_03#8&1f6c134a&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}"
        assert manette._vid_pid(chemin) == (0x054C, 0x09CC)

    def test_chemin_bluetooth(self):
        chemin = r"\\?\hid#{00001124-0000-1000-8000-00805f9b34fb}_vid&0002054c_pid&09cc#9&abc#{4d1e55b2}"
        assert manette._vid_pid(chemin) == (0x054C, 0x09CC)

    def test_chemin_sans_identifiants(self):
        assert manette._vid_pid(r"\\?\hid#acpi#1") is None


class TestLinux:
    def _noeud(self, racine: Path, nom: str, hid_id: str):
        d = racine / nom / "device"
        d.mkdir(parents=True)
        (d / "uevent").write_text(f"DRIVER=playstation\nHID_ID={hid_id}\nHID_NAME=Wireless Controller\n")

    def test_seules_les_manettes_sony_connues(self, tmp_path):
        self._noeud(tmp_path, "hidraw0", "0003:0000054C:000009CC")   # DS4 USB
        self._noeud(tmp_path, "hidraw1", "0003:0000046D:0000C52B")   # souris Logitech
        self._noeud(tmp_path, "hidraw2", "0005:0000054C:00000CE6")   # DualSense Bluetooth
        trouvees = manette._manettes_linux(tmp_path)
        assert trouvees == [Manette("/dev/hidraw0", 0x09CC, 32), Manette("/dev/hidraw2", 0x0CE6, 78)]

    def test_sans_hidraw(self, tmp_path):
        assert manette._manettes_linux(tmp_path / "absent") == []

    def test_ecriture_refusee_sans_erreur(self, tmp_path):
        assert manette._ecrire_linux(Manette(str(tmp_path / "rien" / "hidraw9"), 0x09CC, 32), b"\x05") is False


class TestColorer:
    def test_colore_chaque_manette_qui_sait(self, monkeypatch):
        ecrits = []
        monkeypatch.setattr(manette, "manettes", lambda: [Manette("a", 0x09CC, 32), Manette("b", 0x09CC, 78)])
        monkeypatch.setattr(manette, "_ecrire_windows", lambda m, d: ecrits.append((m.chemin, d)) or True)
        monkeypatch.setattr(manette, "_ecrire_linux", lambda m, d: ecrits.append((m.chemin, d)) or True)
        assert manette.colorer("serpentard") == 1           # la Bluetooth est sautée
        (chemin, donnees), = ecrits
        assert chemin == "a" and tuple(donnees[6:9]) == manette.couleur("serpentard")

    def test_une_ecriture_qui_echoue_ne_leve_pas(self, monkeypatch):
        def refus(m, d):
            raise OSError("occupée")
        monkeypatch.setattr(manette, "manettes", lambda: [Manette("a", 0x09CC, 32)])
        monkeypatch.setattr(manette, "_ecrire_windows", refus)
        monkeypatch.setattr(manette, "_ecrire_linux", refus)
        assert manette.colorer("gryffondor") == 0

    def test_sans_manette_rien(self):
        assert manette.colorer("gryffondor") == 0            # conftest : aucune manette


class TestEteindre:
    """La barre s'éteint à la fermeture du launcher (2026-10-01)."""

    def test_noir_sur_chaque_manette_et_ecrit_avant_le_retour(self, monkeypatch):
        ecrits = []
        monkeypatch.setattr(manette, "manettes", lambda: [Manette("a", 0x09CC, 32)])
        monkeypatch.setattr(manette, "_ecrire_windows", lambda m, d: ecrits.append(d) or True)
        monkeypatch.setattr(manette, "_ecrire_linux", lambda m, d: ecrits.append(d) or True)
        manette.eteindre()
        # Attendu, pas lancé en fond : `os._exit` suit la fermeture.
        (donnees,) = ecrits
        assert tuple(donnees[6:9]) == (0, 0, 0)

    def test_sans_manette_ne_leve_pas(self):
        manette.eteindre()                                   # conftest : aucune manette


_INI_HP5 = (
    "[Accio.Window]\r\nWindowed=1\r\n\r\n"
    "[Accio.Controller]\r\n"
    "; Light bar of a PlayStation controller (USB only), as red,green,blue\r\n"
    "PlayStation=1\r\nRumble=1\r\nLightBar=\r\n\r\n"
    "[Accio.Graphics]\r\nFXAA=1\r\n"
)


class TestPreparer:
    """Au lancement, la couleur de la maison part dans le d3d9.ini que lit le
    xinput1_3.dll du correctif (HP5, HP6, les Reliques)."""

    def _ini(self, tmp_path, texte=_INI_HP5):
        (tmp_path / "d3d9.ini").write_bytes(texte.encode("ascii"))
        return tmp_path / "d3d9.ini"

    def test_la_couleur_de_la_maison(self, tmp_path):
        ini = self._ini(tmp_path)
        assert manette.preparer(tmp_path, "serpentard") is True
        texte = ini.read_bytes().decode("ascii")
        assert "LightBar=0,190,40\r\n" in texte
        assert texte.replace("LightBar=0,190,40", "LightBar=") == _INI_HP5, "seule la ligne change"

    def test_reglage_eteint_le_correctif_n_y_touche_pas(self, tmp_path):
        ini = self._ini(tmp_path, _INI_HP5.replace("LightBar=", "LightBar=255,16,0"))
        assert manette.preparer(tmp_path, None) is True
        assert "LightBar=\r\n" in ini.read_bytes().decode("ascii")

    def test_pas_de_reecriture_a_chaque_lancement(self, tmp_path):
        self._ini(tmp_path)
        assert manette.preparer(tmp_path, "poudlard") is True
        assert manette.preparer(tmp_path, "poudlard") is False

    def test_sans_section_manette_rien(self, tmp_path):
        """HP4 (DirectInput) et l'ancien correctif : pas de section, pas d'erreur."""
        texte = "[Accio.Window]\r\nWindowed=1\r\n"
        ini = self._ini(tmp_path, texte)
        assert manette.preparer(tmp_path, "gryffondor") is False
        assert ini.read_bytes().decode("ascii") == texte

    def test_sans_ini_rien(self, tmp_path):
        assert manette.preparer(tmp_path, "gryffondor") is False
        assert not (tmp_path / "d3d9.ini").exists()

    def test_theme_inconnu_couleur_de_poudlard(self):
        assert manette.texte_couleur("inconnu") == "255,110,0"
        assert manette.texte_couleur(None) == ""


class TestAuLancement:
    def _lancer(self, tmp_path, monkeypatch, **reglages):
        from tests.test_game_manager import GAME_DICT, _make_manager
        m = _make_manager(tmp_path)
        for cle, valeur in reglages.items():
            setattr(m.config, cle, valeur)
        exe = tmp_path / "HPTest" / "System" / "Game.exe"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_bytes(b"")
        (exe.parent / "d3d9.ini").write_bytes(_INI_HP5.encode("ascii"))
        monkeypatch.setattr("src.core.game_manager.prerequis_manquants", lambda _r: [])
        for nom in ("unblock_game_dlls", "delete_pre_launch_files",
                    "create_pre_launch_files", "apply_ini_patches"):
            monkeypatch.setattr("src.core.game_manager." + nom, lambda *a: None)
        monkeypatch.setattr("src.core.game_manager.subprocess.Popen", lambda *a, **k: object())
        assert m.launch_game(GAME_DICT["id"]) is not None
        return (exe.parent / "d3d9.ini").read_bytes().decode("ascii")

    def test_le_lancement_pose_la_couleur(self, tmp_path, monkeypatch):
        assert "LightBar=0,60,255\r\n" in self._lancer(tmp_path, monkeypatch, theme="serdaigle")

    def test_reglage_eteint_au_lancement(self, tmp_path, monkeypatch):
        texte = self._lancer(tmp_path, monkeypatch, theme="serdaigle", couleur_manette=False)
        assert "LightBar=\r\n" in texte


@pytest.fixture
def fenetre(qtbot, tmp_path, monkeypatch):
    """Une MainWindow sur une config isolée (comme `make_window` de test_integration_smoke)."""
    def _make(**overrides):
        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
        monkeypatch.setattr("src.ui.main_window.MainWindow._start_update_check", lambda self: None)
        from src.core.config import Config
        Config(install_path=tmp_path / "games", cache_path=tmp_path / "games" / ".cache", langue="fr",
               autoplay_videos=False, **overrides).save()
        from src.ui.main_window import MainWindow
        win = MainWindow()
        qtbot.addWidget(win)
        return win
    yield _make
    from src.ui.theme import set_theme
    set_theme("poudlard")


class TestBranchements:
    def test_la_fenetre_colore_a_l_ouverture(self, fenetre):
        fenetre(theme="serdaigle")
        assert manette.appels == ["serdaigle"]

    def test_reglage_eteint_rien(self, fenetre):
        fenetre(couleur_manette=False)
        assert manette.appels == []

    @staticmethod
    def _fermer(win, monkeypatch) -> list:
        eteintes = []
        monkeypatch.setattr(manette, "eteindre", lambda *a: eteintes.append(True))
        win.close()
        return eteintes

    def test_la_fermeture_eteint_la_barre_qu_elle_a_allumee(self, fenetre, monkeypatch):
        assert self._fermer(fenetre(), monkeypatch) == [True]

    def test_reglage_coupe_la_fermeture_n_y_touche_pas(self, fenetre, monkeypatch):
        assert self._fermer(fenetre(couleur_manette=False), monkeypatch) == []

    def test_une_partie_en_cours_garde_sa_barre(self, fenetre, monkeypatch):
        win = fenetre()
        # Sur l'INSTANCE (règle 12 : jamais une propriété de classe Qt).
        monkeypatch.setattr(win._session._monitor, "_game_name", "HP6")
        assert self._fermer(win, monkeypatch) == []

    def test_le_choixpeau_colore_la_manette(self, qtbot):
        from src.ui.onboarding import OnboardingDialog
        dlg = OnboardingDialog()
        qtbot.addWidget(dlg)
        dlg._build_rest()
        for groupe in dlg._groupes_maison:
            groupe.buttons()[0].click()
        dlg._repartir()
        assert manette.appels and manette.appels[-1] == dlg._maison


@pytest.mark.parametrize("cle", ["couleur_manette"])
def test_reglage_persiste(tmp_path, monkeypatch, cle):
    from src.core import config as cfg
    monkeypatch.setattr(cfg, "CONFIG_FILE_PATH", tmp_path / "config.json")
    c = cfg.Config(install_path=tmp_path, cache_path=tmp_path / "c")
    setattr(c, cle, False)
    c.save()
    assert getattr(cfg.Config.load(), cle) is False


# ── « Jouer à la manette » dans le registre du jeu (HP5, HP6) ──

_BLOC = {"root": "HKCU", "key": r"Software\Electronic Arts\Harry Potter and the Half Blood Prince\ControllerConfig",
         "value": "CurrentSelection", "on": 4, "off": 0}


def _jeu(bloc=_BLOC, **extra):
    from src.core.game_data import GameData
    base = {"id": "hp6", "name": "HP6", "year": 2009, "description": "d", "developer": "d",
            "executable": "HP6/hp6.exe", "cover_image": "c.jpg", "controller_registry": bloc}
    base.update(extra)
    return GameData.from_dict(base)


class TestBlocDuCatalogue:
    def test_hp5_et_hp6_le_declarent(self):
        """Relevé en jeu (L6/L7, 2026-09-27) : 0 = désactivée, 4 = manette."""
        from src.core.game_data import load_catalog
        jeux = {g.id: g for g in load_catalog().games}
        for gid in ("hp5", "hp6"):
            r = jeux[gid].manette_registre
            assert r is not None and (r.root, r.value, r.on, r.off) == ("HKCU", "CurrentSelection", 4, 0)
            assert r.key.endswith(r"\ControllerConfig")
        assert all(g.manette_registre is None for g in jeux.values() if g.id not in ("hp5", "hp6"))

    @pytest.mark.parametrize("change", [
        {"on": True}, {"off": False}, {"on": 0}, {"on": "4"}, {"value": ""}, {"value": "a\nb"},
        {"key": r"System\CurrentControlSet"}, {"key": r"Software\..\x"}, {"root": "HKCR"}, {"view": 16},
        {"on": -1}, {"off": 2 ** 32},
    ])
    def test_un_bloc_douteux_est_ignore(self, change):
        assert _jeu({**_BLOC, **change}).manette_registre is None

    def test_absent_ou_mal_forme(self):
        assert _jeu(None).manette_registre is None
        assert _jeu(["x"]).manette_registre is None


class TestLectureEcriture:
    def test_etat_lu_dans_le_registre(self, monkeypatch, registre_atteignable):
        monkeypatch.setattr("src.core.game_registry.lire_valeurs", lambda *a, **k: {"CurrentSelection": 4})
        assert manette.activee(_jeu()) is True
        monkeypatch.setattr("src.core.game_registry.lire_valeurs", lambda *a, **k: {"CurrentSelection": 0})
        assert manette.activee(_jeu()) is False
        monkeypatch.setattr("src.core.game_registry.lire_valeurs", lambda *a, **k: {})
        assert manette.activee(_jeu()) is False

    def test_sous_wine_lu_dans_le_user_reg_du_prefixe(self, monkeypatch):
        """Linux : le choix vit dans le `user.reg` du préfixe, lu comme du texte, sans lancer Wine.

        `HKCU\\Software` n'est pas redirigé en vue 32 bits : la clé s'y lit telle que le catalogue l'écrit.
        """
        import sys
        from src.core import compat
        monkeypatch.setattr(sys, "platform", "linux")
        cle = _BLOC["key"].replace("\\", "\\\\")
        user_reg = compat.prefixe() / "user.reg"
        user_reg.write_text(f'WINE REGISTRY Version 2\n\n[{cle}] 1727000000\n"CurrentSelection"=dword:00000004\n',
                            encoding="utf-8")
        assert manette.activee(_jeu()) is True
        user_reg.write_text(user_reg.read_text(encoding="utf-8").replace("00000004", "00000000"), encoding="utf-8")
        assert manette.activee(_jeu()) is False

    def test_rien_sans_bloc_ni_registre(self, monkeypatch):
        assert manette.activee(_jeu(None)) is None
        monkeypatch.setattr("src.core.game_registry.disponible", lambda: False)
        assert manette.activee(_jeu()) is None

    def test_ecrit_la_bonne_valeur_et_passe_le_rappel(self, monkeypatch):
        vus = []
        monkeypatch.setattr("src.core.game_registry.ecrire_valeurs",
                            lambda ruche, cle, valeurs, vue, confirmer=None: vus.append((ruche, valeurs, confirmer)) or True)
        rappel = object()
        assert manette.activer(_jeu(), True, confirmer=rappel)
        assert manette.activer(_jeu(), False)
        assert vus[0] == ("HKCU", {"CurrentSelection": 4}, rappel)
        assert vus[1][1] == {"CurrentSelection": 0}

    def test_la_barriere_du_registre_s_applique(self, monkeypatch, registre_atteignable):
        """Le vrai `ecrire_valeurs` : compare d'abord, prévient seulement s'il y a un écart, écrit en direct."""
        from src.core import game_registry
        etat = {"CurrentSelection": 0}
        monkeypatch.setattr(game_registry, "lire_valeurs", lambda r, c, noms, v=32: dict(etat))
        monkeypatch.setattr(game_registry, "_ecrire_direct", lambda r, c, valeurs, v: etat.update(valeurs) or True)
        demandes = []
        assert manette.activer(_jeu(), True, confirmer=lambda *a: demandes.append(a) or True)
        assert etat == {"CurrentSelection": 4} and len(demandes) == 1
        assert demandes[0][3] == {"CurrentSelection": (0, 4)}          # « remplace : 0 » affiché
        assert manette.activer(_jeu(), True, confirmer=lambda *a: demandes.append(a) or True)
        assert len(demandes) == 1                                        # déjà à 4 : personne n'est dérangé
        assert not manette.activer(_jeu(), False, confirmer=lambda *a: False)
        assert etat == {"CurrentSelection": 4}                           # refus : rien écrit


class TestFenetreDeReglages:
    def _dialogue(self, qtbot, monkeypatch, tmp_path, lu, appliquer):
        from types import SimpleNamespace

        from src.ui.game_settings_dialog import GameSettingsDialog
        monkeypatch.setattr("src.core.game_registry.disponible", lambda: True)
        monkeypatch.setattr("src.core.game_registry.lire_valeurs", lambda *a, **k: dict(lu))
        mgr = SimpleNamespace(game_language=lambda g: None, langues_disponibles=lambda g: (),
                              config=SimpleNamespace(install_path=tmp_path))
        dlg = GameSettingsDialog(_jeu(), mgr, lambda c: True, appliquer_manette=appliquer)
        qtbot.addWidget(dlg)
        return dlg

    def test_l_interrupteur_montre_le_registre(self, qtbot, monkeypatch, tmp_path):
        dlg = self._dialogue(qtbot, monkeypatch, tmp_path, {"CurrentSelection": 4}, lambda oui: True)
        assert dlg._bascule_manette is not None and dlg._bascule_manette.isChecked()

    def test_un_refus_remet_l_interrupteur_sur_le_vrai(self, qtbot, monkeypatch, tmp_path):
        demandes = []
        dlg = self._dialogue(qtbot, monkeypatch, tmp_path, {"CurrentSelection": 0},
                             lambda oui: demandes.append(oui) or False)
        dlg._bascule_manette._basculer()        # un clic (setChecked n'émet rien)
        assert demandes == [True]
        assert not dlg._bascule_manette.isChecked()

    def test_pas_de_rubrique_sans_rappel_ni_bloc(self, qtbot, monkeypatch, tmp_path):
        dlg = self._dialogue(qtbot, monkeypatch, tmp_path, {"CurrentSelection": 4}, None)
        assert dlg._bascule_manette is None
