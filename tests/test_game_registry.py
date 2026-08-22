"""Tests de `src/core/game_registry.py`.

Ce module est la seule barrière entre un catalogue qui se met à jour À DISTANCE
et le registre système de l'utilisateur. Les parties qui décident — quoi
accepter, quoi refuser, quoi écrire — sont donc PURES et testées ici sans
registre, sans Windows et sans élévation.
"""

import sys

import pytest

from src.core.game_registry import (
    construire_reg, deja_a_jour, ecrire_valeurs, lire_valeurs,
    refus_de_cle, refus_de_valeur,
)

BS = chr(92)
CLE_JEU = BS.join(["SOFTWARE", "Electronic Arts",
                   "Harry Potter and the Deathly Hallows Part 1"])
CLE_RUN = BS.join(["Software", "Microsoft", "Windows", "CurrentVersion", "Run"])


class TestRefusDeCle:
    """La clé relevée sur une vraie installation doit passer ; les chemins de
    persistance au démarrage, jamais."""

    def test_la_vraie_cle_de_hp7_est_acceptee(self):
        assert refus_de_cle("HKLM", CLE_JEU) is None

    def test_hkcu_accepte(self):
        assert refus_de_cle("HKCU", BS.join(["Software", "Editeur", "Jeu"])) is None

    def test_run_refuse(self):
        """L'ancienne whitelist de `post_install` (« commence par Software »)
        acceptait exactement ce chemin : persistance à chaque ouverture de
        session, écrite par un catalogue distant."""
        assert refus_de_cle("HKCU", CLE_RUN) is not None

    @pytest.mark.parametrize("cle", [
        BS.join(["Software", "Microsoft", "Quoi"]),
        BS.join(["Software", "Policies", "X"]),
        BS.join(["Software", "Classes", "X"]),
        BS.join(["Software", "Editeur", "Image File Execution Options"]),
    ])
    def test_segments_interdits(self, cle):
        assert refus_de_cle("HKLM", cle) is not None

    @pytest.mark.parametrize("ruche", ["HKCR", "HKEY_USERS", "", None, 5])
    def test_ruches_refusees(self, ruche):
        assert refus_de_cle(ruche, CLE_JEU) is not None

    @pytest.mark.parametrize("cle", [
        "",
        "   ",
        "Software",                                   # trop court
        BS.join(["Windows", "X", "Y"]),               # hors Software
        BS.join(["Software", "..", "X"]),             # remontée
        "Software" + BS + "X\x00Y",                   # octet nul
        None,
        42,
    ])
    def test_chemins_refuses(self, cle):
        assert refus_de_cle("HKLM", cle) is not None

    def test_le_slash_compte_comme_separateur(self):
        """Sous POSIX « \\ » n'est pas un séparateur : normaliser AVANT de
        vérifier, sinon le garde-fou est inopérant hors Windows."""
        assert refus_de_cle("HKCU", "Software/Microsoft/Windows") is not None


class TestRefusDeValeur:
    def test_chaine_et_entier_acceptes(self):
        assert refus_de_valeur("Language", "French") is None
        assert refus_de_valeur("Language", 2) is None

    def test_la_valeur_par_defaut_est_refusee(self):
        """C'est précisément ce que l'ancien stub écrivait, et c'est ce qui
        créait une SOUS-CLÉ « Install Dir » au lieu de la valeur nommée."""
        assert refus_de_valeur("", "x") is not None

    @pytest.mark.parametrize("nom", ["AppInit_DLLs", "Userinit", "Shell", "appinit_dlls"])
    def test_noms_interdits(self, nom):
        assert refus_de_valeur(nom, "x.dll") is not None

    @pytest.mark.parametrize("valeur", [True, False, 1.5, None, [], {}, b"x"])
    def test_types_refuses(self, valeur):
        """`bool` est un `int` en Python : sans test explicite il passerait en
        REG_DWORD 0/1, ce que personne n'a demandé."""
        assert refus_de_valeur("N", valeur) is not None

    @pytest.mark.parametrize("valeur", [-1, 0x1_0000_0000])
    def test_entiers_hors_bornes(self, valeur):
        assert refus_de_valeur("N", valeur) is not None

    def test_octet_nul(self):
        assert refus_de_valeur("N", "a\x00b") is not None


class TestConstruireReg:
    """Le .reg est écrit à la main : son format est donc à prouver."""

    def test_entete_et_chemin(self):
        texte = construire_reg("HKLM", CLE_JEU, {"Language": "French"}, vue=32)
        assert texte.startswith("Windows Registry Editor Version 5.00")
        assert "[HKEY_LOCAL_MACHINE" + BS + "SOFTWARE" + BS + "WOW6432Node" + BS in texte

    def test_la_vue_32_passe_par_le_chemin(self):
        """Un .reg n'a pas de drapeau de vue : WOW6432Node s'écrit DANS le
        chemin, sinon on pose la valeur là où le jeu 32 bits ne la lit pas."""
        assert "WOW6432Node" in construire_reg("HKLM", CLE_JEU, {"A": "b"}, vue=32)
        assert "WOW6432Node" not in construire_reg("HKLM", CLE_JEU, {"A": "b"}, vue=64)

    def test_chaine_et_dword(self):
        texte = construire_reg("HKCU", BS.join(["Software", "E", "J"]),
                               {"Language": "French", "Num": 2})
        assert '"Language"="French"' in texte
        assert '"Num"=dword:00000002' in texte

    def test_antislash_et_guillemet_echappes(self):
        texte = construire_reg("HKCU", BS.join(["Software", "E", "J"]),
                               {"Dir": "C:" + BS + "Jeux" + BS, "Q": 'a"b'})
        assert '"Dir"="C:' + BS + BS + "Jeux" + BS + BS + '"' in texte
        assert '"Q"="a' + BS + '"b"' in texte

    def test_crlf(self):
        """regedit lit un fichier de commandes Windows : LF ne suffit pas."""
        texte = construire_reg("HKCU", BS.join(["Software", "E", "J"]), {"A": "b"})
        assert BS + "r" not in texte  # pas d'échappement littéral
        assert texte.count("\r\n") >= 3
        assert "\n" not in texte.replace("\r\n", "")

    def test_encodable_en_utf16(self):
        """C'est l'encodage exigé par regedit, et le seul qui tienne un chemin
        accentué — cf. le piège des .bat en page de codes OEM."""
        texte = construire_reg("HKLM", CLE_JEU, {"Dir": "C:" + BS + "Frédéric" + BS + "日本"})
        assert texte.encode("utf-16").startswith(b"\xff\xfe")


class TestHorsWindows:
    """Objectif Linux : rien ne doit lever, tout doit dégrader."""

    def test_lecture_vide_hors_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        assert lire_valeurs("HKLM", CLE_JEU, ["Language"]) == {}

    def test_ecriture_refusee_hors_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        assert ecrire_valeurs("HKLM", CLE_JEU, {"Language": "French"}) is False

    def test_deja_a_jour_est_faux_hors_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        assert deja_a_jour("HKLM", CLE_JEU, {"Language": "French"}) is False


class TestEcritureNeComprometPas:
    """`ecrire_valeurs` ne doit JAMAIS atteindre le registre sur une entrée
    refusée — c'est tout ou rien, pas une écriture à moitié."""

    @staticmethod
    def _piege(monkeypatch):
        appels = []
        monkeypatch.setattr("src.core.game_registry._ecrire_direct",
                            lambda *a: appels.append(a) or True)
        monkeypatch.setattr("src.core.game_registry._ecrire_eleve",
                            lambda *a: appels.append(a) or True)
        monkeypatch.setattr("src.core.game_registry.deja_a_jour", lambda *a, **k: False)
        return appels

    @pytest.mark.skipif(sys.platform != "win32", reason="chemin Windows")
    def test_cle_refusee_n_ecrit_rien(self, monkeypatch):
        appels = self._piege(monkeypatch)
        assert ecrire_valeurs("HKCU", CLE_RUN, {"X": "y"}) is False
        assert appels == []

    @pytest.mark.skipif(sys.platform != "win32", reason="chemin Windows")
    def test_une_seule_valeur_refusee_annule_tout(self, monkeypatch):
        appels = self._piege(monkeypatch)
        assert ecrire_valeurs("HKLM", CLE_JEU,
                              {"Language": "French", "AppInit_DLLs": "x"}) is False
        assert appels == []

    @pytest.mark.skipif(sys.platform != "win32", reason="chemin Windows")
    def test_rien_a_faire_si_deja_a_jour(self, monkeypatch):
        """Le point entier du dispositif : pas d'invite UAC pour rien."""
        appels = []
        monkeypatch.setattr("src.core.game_registry.deja_a_jour", lambda *a, **k: True)
        monkeypatch.setattr("src.core.game_registry._ecrire_direct",
                            lambda *a: appels.append(a) or True)
        monkeypatch.setattr("src.core.game_registry._ecrire_eleve",
                            lambda *a: appels.append(a) or True)
        assert ecrire_valeurs("HKLM", CLE_JEU, {"Language": "French"}) is True
        assert appels == []

    @pytest.mark.skipif(sys.platform != "win32", reason="chemin Windows")
    def test_l_elevation_prend_le_relais_si_l_ecriture_directe_echoue(self, monkeypatch):
        etapes = []
        monkeypatch.setattr("src.core.game_registry.deja_a_jour",
                            lambda *a, **k: bool(etapes))
        monkeypatch.setattr("src.core.game_registry._ecrire_direct",
                            lambda *a: False)
        monkeypatch.setattr("src.core.game_registry._ecrire_eleve",
                            lambda *a: etapes.append("eleve") or True)
        assert ecrire_valeurs("HKLM", CLE_JEU, {"Language": "French"}) is True
        assert etapes == ["eleve"]

    @pytest.mark.skipif(sys.platform != "win32", reason="chemin Windows")
    def test_uac_refuse_rend_false(self, monkeypatch):
        monkeypatch.setattr("src.core.game_registry.deja_a_jour", lambda *a, **k: False)
        monkeypatch.setattr("src.core.game_registry._ecrire_direct", lambda *a: False)
        monkeypatch.setattr("src.core.game_registry._ecrire_eleve", lambda *a: False)
        assert ecrire_valeurs("HKLM", CLE_JEU, {"Language": "French"}) is False

    @pytest.mark.skipif(sys.platform != "win32", reason="chemin Windows")
    def test_une_ecriture_qui_ne_prend_pas_rend_false(self, monkeypatch):
        """regedit /s est MUET, y compris en échec : c'est la relecture qui
        fait foi, jamais son code de retour."""
        monkeypatch.setattr("src.core.game_registry.deja_a_jour", lambda *a, **k: False)
        monkeypatch.setattr("src.core.game_registry._ecrire_direct", lambda *a: False)
        monkeypatch.setattr("src.core.game_registry._ecrire_eleve", lambda *a: True)
        assert ecrire_valeurs("HKLM", CLE_JEU, {"Language": "French"},
                              attente_s=0.3) is False


_CRLF = chr(13) + chr(10)
_CONTROLES = [chr(10), chr(13), chr(9), chr(0), chr(27), chr(127)]


class TestInjectionDansLeReg:
    """Le catalogue est DISTANT, et le .reg est importe par un regedit ELEVE.

    Un .reg est un format ligne a ligne : une valeur portant un saut de ligne
    referme la chaine, et la suite est relue comme des instructions. Demontre
    le 2026-08-21 — le doublement des antislashs limitait les degats, mais par
    ACCIDENT, pas par conception. On refuse les caracteres de controle.
    """

    _CHARGE = ("French" + _CRLF
               + "[HKEY_LOCAL_MACHINE" + BS + "SOFTWARE" + BS + "Microsoft" + BS
               + "Windows" + BS + "CurrentVersion" + BS + "Run]" + _CRLF
               + chr(34) + "x" + chr(34) + "=" + chr(34) + "evil.exe" + chr(34))

    def test_la_charge_est_refusee(self):
        assert refus_de_valeur("Language", self._CHARGE) is not None

    @pytest.mark.parametrize("c", _CONTROLES)
    def test_tous_les_caracteres_de_controle(self, c):
        assert refus_de_valeur("N", "a" + c + "b") is not None
        assert refus_de_valeur("a" + c + "b", "v") is not None

    def test_un_chemin_avec_saut_de_ligne_est_refuse(self):
        assert refus_de_cle("HKLM", "Software" + BS + "E" + chr(10) + "vil" + BS + "J") is not None

    @pytest.mark.parametrize("crochet", ["[", "]"])
    def test_crochets_refuses_dans_le_chemin(self, crochet):
        """Ce sont les delimiteurs de section d'un .reg."""
        assert refus_de_cle("HKLM", "Software" + BS + "E" + crochet + "vil" + BS + "J") is not None

    def test_construire_reg_refuse_bruyamment(self):
        """Une fonction qui fabrique un fichier importe en administrateur ne
        doit pas produire une injection en silence parce qu'un appelant a
        oublie de valider."""
        with pytest.raises(ValueError):
            construire_reg("HKLM", CLE_JEU, {"Language": self._CHARGE})
        with pytest.raises(ValueError):
            construire_reg("HKCU", CLE_RUN, {"Language": "French"})

    def test_aucune_ligne_parasite_dans_un_reg_valide(self):
        """Controle de forme : en-tete + [cle] + une ligne par valeur."""
        texte = construire_reg("HKLM", CLE_JEU, {"A": "b", "C": 1})
        lignes = [ligne for ligne in texte.split(_CRLF) if ligne]
        assert len(lignes) == 4
        assert sum(1 for ligne in lignes if ligne.startswith("[")) == 1


class TestPasDeDoubleWow6432Node:
    """Doubler la redirection creerait une cle fantome que le jeu ne lira
    jamais — et l'echec serait SILENCIEUX."""

    def test_pas_de_doublon_si_le_catalogue_l_a_deja_ecrit(self):
        cle = BS.join(["SOFTWARE", "WOW6432Node", "Electronic Arts", "Jeu"])
        section = construire_reg("HKLM", cle, {"A": "b"}, vue=32).splitlines()[2]
        assert section.lower().count("wow6432node") == 1

    def test_insere_quand_il_manque(self):
        section = construire_reg("HKLM", CLE_JEU, {"A": "b"}, vue=32).splitlines()[2]
        assert section.lower().count("wow6432node") == 1


class TestPrevenanceAvantEcriture:
    """On ne modifie pas le registre de quelqu'un sans le lui dire — mais on ne
    le dérange pas non plus pour rien : le rappel n'est appelé que lorsqu'il y a
    réellement une écriture à faire, jamais quand tout est déjà en place."""

    @pytest.mark.skipif(sys.platform != "win32", reason="chemin Windows")
    def test_le_rappel_est_consulte_avant_toute_ecriture(self, monkeypatch):
        vus = []
        ecrites = []
        monkeypatch.setattr("src.core.game_registry.deja_a_jour",
                            lambda *a, **k: bool(ecrites))
        monkeypatch.setattr("src.core.game_registry._ecrire_direct",
                            lambda *a: ecrites.append(a) or True)

        def confirmer(ruche, cle, valeurs):
            # Le rappel doit voir CE qui sera écrit : c'est ce qu'il affiche.
            vus.append((ruche, cle, dict(valeurs)))
            return True

        assert ecrire_valeurs("HKLM", CLE_JEU, {"Locale": "fr_FR"},
                              confirmer=confirmer) is True
        assert vus == [("HKLM", CLE_JEU, {"Locale": "fr_FR"})]
        assert len(ecrites) == 1

    @pytest.mark.skipif(sys.platform != "win32", reason="chemin Windows")
    def test_un_refus_n_ecrit_rien(self, monkeypatch):
        appels = []
        monkeypatch.setattr("src.core.game_registry.deja_a_jour", lambda *a, **k: False)
        monkeypatch.setattr("src.core.game_registry._ecrire_direct",
                            lambda *a: appels.append(a) or True)
        monkeypatch.setattr("src.core.game_registry._ecrire_eleve",
                            lambda *a: appels.append(a) or True)
        assert ecrire_valeurs("HKLM", CLE_JEU, {"Locale": "fr_FR"},
                              confirmer=lambda *a: False) is False
        assert appels == []

    @pytest.mark.skipif(sys.platform != "win32", reason="chemin Windows")
    def test_pas_de_rappel_quand_il_n_y_a_rien_a_ecrire(self, monkeypatch):
        """Sinon on redemanderait à CHAQUE lancement, et prévenir deviendrait
        un harcèlement qu'on apprend à cliquer sans lire."""
        monkeypatch.setattr("src.core.game_registry.deja_a_jour", lambda *a, **k: True)
        appels = []
        assert ecrire_valeurs("HKLM", CLE_JEU, {"Locale": "fr_FR"},
                              confirmer=lambda *a: appels.append(a) or True) is True
        assert appels == []

    @pytest.mark.skipif(sys.platform != "win32", reason="chemin Windows")
    def test_pas_de_rappel_sur_une_cle_refusee(self, monkeypatch):
        """La validation passe AVANT : inutile de faire valider à l'utilisateur
        une écriture qu'on refusera de toute façon."""
        monkeypatch.setattr("src.core.game_registry.deja_a_jour", lambda *a, **k: False)
        appels = []
        assert ecrire_valeurs("HKCU", CLE_RUN, {"X": "y"},
                              confirmer=lambda *a: appels.append(a) or True) is False
        assert appels == []
