"""Polices embarquées — surtout la police de CORPS.

`body_font()` appelait Georgia par son nom : une police Microsoft, présente
sous Windows, **absente sous Linux** (objectif déclaré du projet) et garantie
nulle part. Elle est remplacée par Gelasio, embarquée sous licence OFL et
métriquement compatible avec Georgia.

Ces tests gardent les trois choses qui rendent ce remplacement acceptable :
le fichier est bien là, il est bien chargé, et sa licence accompagne le binaire.
"""

from pathlib import Path

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtGui import QFontDatabase  # noqa: E402

from src.core.config import ASSETS_DIR  # noqa: E402
from src.ui.fonts import body_font, cinzel, cinzel_decorative, load_fonts  # noqa: E402

RACINE = Path(__file__).resolve().parent.parent
POLICES = ASSETS_DIR / "fonts"


class TestFichiersEmbarques:
    def test_la_police_de_corps_est_embarquee(self):
        f = POLICES / "Gelasio-Variable.ttf"
        assert f.exists(), (
            f"{f} absent — l'interface retomberait sur Georgia, qui n'existe "
            "pas sous Linux")
        assert f.stat().st_size > 50_000

    def test_la_licence_accompagne_la_police(self):
        """L'OFL exige que sa licence voyage avec la police redistribuée."""
        licence = POLICES / "Gelasio-OFL.txt"
        assert licence.exists(), f"{licence} absent — redistribution non conforme"
        texte = licence.read_text(encoding="utf-8", errors="replace")
        assert "SIL OPEN FONT LICENSE" in texte.upper()

    def test_la_police_est_declaree_dans_les_notices(self):
        notices = (RACINE / "docs" / "THIRD-PARTY-NOTICES.md").read_text(
            encoding="utf-8")
        assert "Gelasio" in notices
        assert "Open Font License" in notices


class TestChargement:
    def test_la_police_de_corps_est_chargee(self, qtbot):
        load_fonts()
        famille = body_font(14).family()
        assert famille == "Gelasio", (
            f"body_font() rend « {famille} » : la police embarquée n'a pas été "
            "chargée, l'interface dépend encore du système")

    def test_toutes_les_familles_sont_disponibles(self, qtbot):
        load_fonts()
        for police in (cinzel(12), cinzel_decorative(20), body_font(14)):
            assert police.family() in QFontDatabase.families(), (
                f"« {police.family()} » absente de la base de polices Qt")

    def test_aucune_famille_ne_depend_du_systeme(self, qtbot):
        """Sous offscreen il n'y a AUCUNE police système : si l'une des trois
        familles était encore un nom Windows, elle serait substituée en silence.
        """
        load_fonts()
        for police in (cinzel(12), cinzel_decorative(20), body_font(14)):
            assert police.family() not in ("Georgia", "Segoe UI", "Times New Roman")
