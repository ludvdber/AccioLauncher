"""Ce que l'utilisateur LIT avant qu'on touche à son registre.

`game_registry` décide quoi écrire ; ce fichier vérifie ce qui est ANNONCÉ.
La distinction compte : sous HKLM, l'écriture enchaîne sur une invite UAC, et
une autorisation Windows qui surgit sans raison connue se refuse — après quoi
le jeu ne démarre pas et personne ne sait pourquoi.

Le cas qui a motivé l'affichage du remplacement : sur une machine où HP7 a été
installé par EA, `Locale` et `Install Dir` existent DÉJÀ et pointent ailleurs.
Dire « le launcher va écrire Locale = fr » sans dire qu'un `fr_FR` est en place
laisse autoriser sans savoir ce qu'on perd.
"""

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtWidgets import QMessageBox  # noqa: E402

from src.ui import game_detail_handlers as gdh  # noqa: E402

CLE = chr(92).join(["SOFTWARE", "Electronic Arts",
                    "Harry Potter and the Deathly Hallows Part 2"])


@pytest.fixture
def dialogue(monkeypatch):
    """Rend (demander, textes) : le rappel réel, et ce qu'il a affiché.

    `_boite` est bouchonné parce qu'il appelle `exec()`, qui BLOQUE la suite
    de tests jusqu'à ce qu'un humain clique.
    """
    textes = []

    def faux_boite(icone, parent, titre, texte, boutons=None, defaut=None):
        textes.append(texte)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(gdh, "_boite", faux_boite)
    return gdh.confirmer_registre(None, "Reliques de la Mort — partie 2"), textes


class TestCeQuiEstAnnonce:

    def test_les_valeurs_a_ecrire_sont_nommees(self, dialogue):
        demander, textes = dialogue
        assert demander("HKLM", CLE, {"Locale": "fr"}, {}) is True
        assert "Locale = fr" in textes[0]
        assert CLE in textes[0]

    def test_le_remplacement_est_annonce(self, dialogue):
        """Le cœur du sujet : on dit par quoi on remplace quoi."""
        demander, textes = dialogue
        demander("HKLM", CLE, {"Locale": "fr"}, {"Locale": ("fr_FR", "fr")})
        assert "Locale = fr" in textes[0]
        assert "fr_FR" in textes[0]

    def test_rien_n_est_annonce_quand_il_n_y_a_rien_a_ecraser(self, dialogue):
        """Une valeur ABSENTE (`None`) ne remplace rien : annoncer un
        remplacement serait faux, et « remplace : (rien) » est du bruit."""
        demander, textes = dialogue
        demander("HKLM", CLE, {"Locale": "fr"}, {"Locale": (None, "fr")})
        assert "Locale = fr" in textes[0]
        assert "remplace" not in textes[0].lower()

    def test_seule_la_valeur_ecrasee_porte_la_mention(self, dialogue):
        demander, textes = dialogue
        demander("HKLM", CLE,
                 {"Locale": "fr", "Install Dir": "D:" + chr(92)},
                 {"Locale": ("fr_FR", "fr"),
                  "Install Dir": (None, "D:" + chr(92))})
        assert textes[0].count("fr_FR") == 1
        assert textes[0].lower().count("remplace") == 1

    def test_l_elevation_est_annoncee_sous_hklm(self, dialogue):
        """Voir Windows demander une autorisation sans savoir pourquoi, c'est
        la refuser."""
        demander, textes = dialogue
        demander("HKLM", CLE, {"Locale": "fr"}, {})
        assert "administrateur" in textes[0].lower()

    def test_pas_d_annonce_d_elevation_sous_hkcu(self, dialogue):
        """HKCU n'élève pas : promettre une invite qui ne viendra pas est un
        mensonge de plus, pas une précaution."""
        demander, textes = dialogue
        demander("HKCU", CLE, {"Locale": "fr"}, {})
        assert "administrateur" not in textes[0].lower()


class TestReponse:

    def test_oui_autorise(self, dialogue):
        demander, _ = dialogue
        assert demander("HKLM", CLE, {"Locale": "fr"}, {}) is True

    def test_non_refuse(self, monkeypatch):
        monkeypatch.setattr(gdh, "_boite",
                            lambda *a, **k: QMessageBox.StandardButton.No)
        demander = gdh.confirmer_registre(None, "Jeu")
        assert demander("HKLM", CLE, {"Locale": "fr"}, {}) is False

    def test_les_ecarts_sont_facultatifs(self, dialogue):
        """Un appelant qui ne les passe pas ne doit pas faire lever le rappel
        — c'est le chemin par lequel passe tout code plus ancien."""
        demander, textes = dialogue
        assert demander("HKLM", CLE, {"Locale": "fr"}) is True
        assert "Locale = fr" in textes[0]
