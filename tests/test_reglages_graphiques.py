"""Les réglages graphiques de HP3, écrits en place dans son fichier de configuration.

Le fichier d'essai reprend la forme du vrai (HP3 v1.2, relevé le 2026-10-07) :
clés alignées sur une colonne, CRLF, `ForceVerticalSync` dans `[Glide]` ET
`[DirectX]`, `RTTexturesForceScaleAndMSAA` dans `[DirectXExt]`.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt

from src.core import reglages_graphiques as rg
from src.core.game_data import GameData

CONF = (
    "[General]\r\n"
    "OutputAPI                            = bestavailable\r\n"
    "\r\n"
    "[GeneralExt]\r\n"
    ";               FPSLimit: An integer or rational (fractional) value, 0 = unlimited\r\n"
    "FPSLimit                             = 60\r\n"
    "Environment                          = \r\n"
    "\r\n"
    "[Glide]\r\n"
    "ForceVerticalSync                   = true\r\n"
    "Antialiasing                        = appdriven\r\n"
    "\r\n"
    "[DirectX]\r\n"
    "Filtering                           = 16\r\n"
    "Resolution                          = max\r\n"
    "Antialiasing                        = 8x\r\n"
    "ForceVerticalSync                   = true\r\n"
    "\r\n"
    "[DirectXExt]\r\n"
    "RTTexturesForceScaleAndMSAA         = true\r\n"
    "SmoothedDepthSampling               = true\r\n"
)
R = rg.REGLAGES


@pytest.fixture
def conf(tmp_path):
    chemin = tmp_path / "HP3" / "system" / "dgVoodoo.conf"
    chemin.parent.mkdir(parents=True)
    chemin.write_bytes(CONF.encode("ascii"))
    return chemin


class TestLecture:
    def test_valeurs_livrees(self, conf):
        lu = {i: rg.lire(conf, r).valeur for i, r in R.items()}
        assert lu == {"graph_resolution": "max", "graph_antialiasing": "8x",
                      "graph_textures_rendu": True, "graph_filtrage": "16",
                      "graph_limite": "60", "graph_vsync": True}

    def test_valeur_posee_a_la_main(self, conf):
        conf.write_bytes(CONF.replace("= 8x", "= 16x").encode())
        etat = rg.lire(conf, R["graph_antialiasing"])
        assert etat.valeur == "16x" and etat.personnalise


class TestEcriture:
    def test_seule_la_valeur_change(self, conf):
        rg.ecrire(conf, R["graph_antialiasing"], "4x")
        attendu = CONF.replace("Antialiasing                        = 8x",
                               "Antialiasing                        = 4x")
        assert conf.read_bytes() == attendu.encode()          # alignement et CRLF gardés

    def test_la_synchro_de_directx_pas_celle_de_glide(self, conf):
        rg.ecrire(conf, R["graph_vsync"], False)
        texte = conf.read_bytes().decode()
        glide, directx = texte.split("[DirectX]\r\n", 1)
        assert "ForceVerticalSync                   = true" in glide
        assert "ForceVerticalSync                   = false" in directx

    def test_textures_de_rendu_dans_directxext(self, conf):
        rg.ecrire(conf, R["graph_textures_rendu"], False)
        assert "RTTexturesForceScaleAndMSAA         = false\r\n" in conf.read_bytes().decode()

    @pytest.mark.parametrize("valeur", ["0", "120", "144"])
    def test_jamais_plus_de_60_images(self, conf, valeur):
        """Au-delà de 60, diablotin figé et portraits fermés (notes/HP3.md)."""
        with pytest.raises(ValueError):
            rg.ecrire(conf, R["graph_limite"], valeur)
        assert conf.read_bytes() == CONF.encode()

    def test_aucun_choix_au_dela_de_60(self):
        assert all(int(v) <= 60 for v in R["graph_limite"].choix)

    def test_cle_absente_ajoutee_dans_sa_section(self, conf):
        conf.write_bytes(CONF.replace("Filtering                           = 16\r\n", "").encode())
        rg.ecrire(conf, R["graph_filtrage"], "8")
        texte = conf.read_bytes().decode()
        directx = texte.split("[DirectX]\r\n", 1)[1].split("[DirectXExt]")[0]
        assert "Filtering                            = 8\r\n" in directx

    def test_origine_gardee_puis_remise(self, conf):
        rg.ecrire(conf, R["graph_antialiasing"], "off")
        rg.ecrire(conf, R["graph_resolution"], "max_fhd")
        assert rg.chemin_origine(conf).read_bytes() == CONF.encode()   # avant la 1re retouche
        rg.remettre_origine(conf)
        assert conf.read_bytes() == CONF.encode()


class TestDisponible:
    def test_windows_seulement(self, conf, monkeypatch):
        monkeypatch.setattr(rg.sys, "platform", "linux")
        assert not rg.disponible(conf)
        monkeypatch.setattr(rg.sys, "platform", "win32")
        assert rg.disponible(conf)
        assert not rg.disponible(conf.with_name("absent.conf"))


def test_chaque_texte_est_traduit():
    """Les textes de la table passent par `tr()` dynamiquement : le test
    d'i18n, qui lit les `tr("…")` littéraux, ne les voit pas."""
    textes = set()
    for r in R.values():
        textes |= {r.libelle, r.aide, r.zero} | {n for _v, n in r.noms_choix if n}
    for code in ("en", "es"):
        cles = json.loads(Path(f"src/data/i18n/{code}.json").read_text(encoding="utf-8"))["strings"]
        manquants = sorted(t for t in textes if t and t not in cles and not t[0].isdigit())
        assert not manquants, (code, manquants)


class TestFenetre:
    @pytest.fixture
    def dlg(self, qtbot, conf, tmp_path, monkeypatch):
        from src.ui.game_settings_dialog import GameSettingsDialog
        monkeypatch.setattr(rg.sys, "platform", "win32")
        jeu = GameData.from_dict({
            "id": "hp3", "name": "HP3", "year": 2004, "description": "d", "developer": "d",
            "executable": "HP3/system/hppoa.exe", "cover_image": "c.jpg"})
        manager = SimpleNamespace(game_language=lambda g: None, langues_disponibles=lambda g: (),
                                  config=SimpleNamespace(install_path=tmp_path, resolution_jeu={}))
        d = GameSettingsDialog(jeu, manager, lambda code: True)
        qtbot.addWidget(d)
        return d

    def test_onglets_image_et_performances(self, dlg):
        assert {"image", "perfs"} <= set(dlg._onglets)
        assert set(dlg._controles_graph) == set(R)

    def test_choisir_ecrit_aussitot(self, dlg, conf):
        liste = dlg._controles_graph["graph_antialiasing"]
        assert liste.currentData() == "8x"
        liste.setCurrentIndex(liste.findData("4x"))
        assert "Antialiasing                        = 4x" in conf.read_bytes().decode()
        assert dlg._bouton_reset.isEnabled()

    def test_retablir_l_origine(self, qtbot, dlg, conf):
        qtbot.mouseClick(dlg._controles_graph["graph_vsync"], Qt.MouseButton.LeftButton)
        assert "ForceVerticalSync                   = false" in conf.read_bytes().decode()
        dlg._bouton_reset.click()
        assert conf.read_bytes() == CONF.encode()
        assert dlg._controles_graph["graph_vsync"].isChecked()

    def test_fichier_en_lecture_seule(self, dlg, conf, monkeypatch):
        def refus(*_a):
            raise OSError("verrouillé")
        monkeypatch.setattr(rg, "_ecrire", refus)
        liste = dlg._controles_graph["graph_limite"]
        liste.setCurrentIndex(liste.findData("30"))
        assert liste.currentData() == "60"                    # remis sur le fichier
        assert "réglages graphiques" in dlg._erreur.text()
        assert "voodoo" not in dlg._erreur.text().lower()
