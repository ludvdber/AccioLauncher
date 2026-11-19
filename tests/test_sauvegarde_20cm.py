"""C8 (Ludo, 2026-11-17) : la difficulté de HP5 et la Nouvelle partie+ de HP4 écrites dans la sauvegarde du
joueur, à son choix. Les fichiers sont FABRIQUÉS ici, au format lu dans les exe (atelier,
`notes/doc/hp4/SAUVEGARDE.md` et `doc/hp5/SAUVEGARDE.md`) : aucune partie réelle dans ce dépôt public. Le
module a été vérifié à part sur les copies de référence de l'atelier (2026-11-19) : difficulté réécrite
identique à l'octet à `hp5_save.py`, partie neuve de HP4 identique bloc par bloc au fichier VU à l'essai 24b.
"""
import struct
from datetime import datetime
from pathlib import Path

import pytest

from src.core import copies_sauvegardes, sauvegardes
from src.core import sauvegarde_20cm as s20
from src.core.game_data import load_catalog

_JEUX = {g.id: g for g in load_catalog().games}
_RW = 0x1C02002D


# ── Fabriquer des fichiers au format du jeu ──

def _fiche5(pour_cent: int, difficulte: int, jour: int = 16) -> bytes:
    fiche = bytearray(0x178)
    fiche[0x04:0x0C] = b"Hogwarts"
    struct.pack_into("<7I", fiche, 0x44, 2026, 11, 1, jour, 12, 6, 22)
    struct.pack_into("<I", fiche, 0x74, pour_cent)
    struct.pack_into("<I", fiche, 0x78, 3)                      # version du bloc de réglages
    struct.pack_into("<3I", fiche, 0x7C, 2, 1, 1)               # ligne 0
    struct.pack_into("<3I", fiche, 0x88, 3, difficulte, difficulte)
    return bytes(fiche)


def _corps5(difficulte: int, graine: int) -> bytes:
    corps = bytearray(0x400)
    corps[:8] = b"PTOO30.1"
    struct.pack_into("<I", corps, 0x08, 0x178)
    for i in range(0x18, 0x178, 4):
        struct.pack_into("<I", corps, i, (i * 2654435761 + graine) & 0xFFFF)
    struct.pack_into("<I", corps, 0x8C, difficulte)
    struct.pack_into("<I", corps, 0x14, s20._somme_corps5(bytes(corps)))
    return bytes(corps)


def hpootp(*parties: tuple[int, int] | None) -> bytes:
    """HP5 : (pour cent, difficulté) par emplacement, None = libre."""
    fiches = b"".join(_fiche5(*p, jour=10 + k) if p else bytes(0x178) for k, p in enumerate(parties))
    corps = b"".join(_corps5(p[1], k) if p else bytes(0x400) for k, p in enumerate(parties))
    return s20.composer(fiches, corps)


def _bloc(type_: int, charge: bytes) -> bytes:
    return struct.pack("<III", type_, len(charge), _RW) + charge


def _entite(nom: str, enregistrements: list[tuple[int, bytes]]) -> bytes:
    nommee = nom.encode("ascii") + b"\0\x13\x37"                 # le jeu laisse des octets au hasard après le nom
    charge = struct.pack("<II", 0x18, 0x40000000) + bytes(range(16))
    charge += struct.pack("<II", 8 + len(nommee), 0x80000000) + nommee
    for indice, valeur in enregistrements:
        charge += struct.pack("<II", 8 + len(valeur), indice) + valeur
    return _bloc(0x705, charge)


def _histoire(niveau: str) -> bytes:
    return _bloc(0x723, niveau.encode("ascii") + bytes(5))


def _corps4(niveau: str, graine: int, drapeaux: int) -> bytes:
    blocs = [_bloc(0x722, b"evas" + niveau.encode("ascii") + b"\0"),
             _entite("GlobalData", [(i, struct.pack("<I", graine * 100 + i)) for i in range(40)]),
             _entite("SaveFlags", [(i, struct.pack("<I", drapeaux if i in (0, 3) else 0)) for i in range(8)]),
             _entite("MagicMastery", [(i, struct.pack("<f", graine + i / 10)) for i in range(16)])]
    if niveau != s20.PREMIER_NIVEAU:
        blocs += [_histoire(niveau), _histoire("FrontEnd_LevelSelect"), _entite("ShieldGenerator", [(0, b"\1\0\0\0")])]
    blocs += [_histoire(s20.PREMIER_NIVEAU), _histoire("FrontEnd_CharacterSelect")]
    contenu = b"".join(blocs)
    return contenu + bytes(0x2800 - len(contenu))


def _fiche4(niveau: str, rang: int, boucliers: int) -> bytes:
    return (s20._champ(niveau, 0x60) + s20._champ("28/09/2026", 0x20) + s20._champ("12:23:58", 0x20)
            + struct.pack("<iii", rang, boucliers, 0))


_VIDE4 = bytes(0xA0) + struct.pack("<iii", -1, -1, 0)


def hpgof(*parties: tuple[str, int, int] | None) -> bytes:
    """HP4 : (niveau, rang, boucliers) par emplacement, None = libre."""
    fiches = b"".join(_fiche4(*p) if p else _VIDE4 for p in parties)
    corps = b"".join(_corps4(p[0], k + 1, 0x84020602) if p else bytes(0x2800) for k, p in enumerate(parties))
    return s20.composer(fiches, corps)


# ── Le conteneur ──

class TestConteneur:
    def test_aller_retour_a_l_octet(self):
        octets = hpootp((15, 2), (6, 2), (4, 2))
        assert s20.composer(*s20.ouvrir(octets)) == octets

    def test_la_somme_du_jeu_n_est_pas_le_crc32_bzip2(self):
        """Valeur de référence calculée avec `sauve_20cm.crc` de l'atelier (forme non augmentée)."""
        assert s20.crc(b"123456789") == 0x74527081
        assert s20.crc(b"123456789") != 0xFC891918, "le CRC-32/BZIP2 de la même chaîne"

    @pytest.mark.parametrize("ou", [0x02, 0x14, 0x30, 0x500])
    def test_un_octet_change_rend_le_fichier_illisible(self, ou):
        octets = bytearray(hpootp((15, 2), None, None))
        octets[ou] ^= 0x40
        with pytest.raises(s20.Illisible):
            s20.ouvrir(bytes(octets))


# ── HP5 ──

class TestDifficulteHP5:
    def test_lire_les_parties(self):
        parties = s20.parties("hp5", hpootp((15, 2), None, (4, 0)))
        assert parties[1] is None
        assert (parties[0].numero, parties[0].avancement, parties[0].difficulte) == (1, 15, 2)
        assert parties[0].ecrite == datetime(2026, 11, 10, 12, 6, 22)
        assert parties[2].difficulte == 0

    def test_reecrire_change_les_trois_endroits_et_rien_d_autre(self):
        avant = hpootp((15, 2), (6, 2), (4, 2))
        apres = s20.difficulte_hp5(avant, 2, 0, 2)
        assert [p.difficulte for p in s20.parties("hp5", apres)] == [2, 0, 2]
        ecarts = {i for i, (a, b) in enumerate(zip(avant, apres, strict=True)) if a != b}
        fiche, corps = 0x1C + 0x178, 0x1C + 3 * 0x178 + 0x400
        permis = set(range(0x10, 0x1C)) | set(range(fiche + 0x8C, fiche + 0x94)) \
            | set(range(corps + 0x14, corps + 0x18)) | set(range(corps + 0x8C, corps + 0x90))
        assert ecarts and ecarts <= permis, "CRC, fiche (gardée, courante), corps (valeur, somme)"

    def test_une_partie_neuve_dans_l_emplacement_libre(self):
        avant = hpootp((15, 2), None, (4, 1))
        apres = s20.difficulte_hp5(avant, 1, 0, 2)
        p1, p2 = s20.ouvrir(apres)
        a1, a2 = s20.ouvrir(avant)
        assert [p.difficulte if p else None for p in s20.parties("hp5", apres)] == [2, 0, 1]
        assert p1[:0x178] == a1[:0x178] and p2[:0x400] == a2[:0x400], "la partie d'origine ne bouge pas"
        assert p1[0x178 * 2:] == a1[0x178 * 2:] and p2[0x800:] == a2[0x800:]
        assert s20.parties("hp5", apres)[1].avancement == 15

    def test_jamais_par_dessus_une_autre_partie(self):
        with pytest.raises(ValueError):
            s20.difficulte_hp5(hpootp((15, 2), (6, 2), None), 1, 0, 2)
        with pytest.raises(ValueError):
            s20.difficulte_hp5(hpootp(None, (6, 2), None), 1, 0, 3)

    def test_un_corps_qui_ne_concorde_pas_n_est_pas_ecrit(self):
        """Fiche et corps en désaccord : pas le format lu (essai 24 : le corps fait foi)."""
        p1, p2 = s20.ouvrir(hpootp((15, 2), None, None))
        fiche = bytearray(p1)
        struct.pack_into("<I", fiche, 0x8C, 1)
        with pytest.raises(s20.Illisible):
            s20.parties("hp5", s20.composer(bytes(fiche), p2))


# ── HP4 ──

class TestNouvellePartiePlusHP4:
    MAINTENANT = datetime(2026, 11, 19, 20, 5, 7)

    @staticmethod
    def _blocs(octets: bytes, k: int) -> list[tuple[int, str, bytes]]:
        _p1, p2 = s20.ouvrir(octets)
        return [(t, s20._nom(t, b), b) for t, b in s20._blocs(p2[(k - 1) * 0x2800:k * 0x2800])]

    def test_lire_les_parties(self):
        parties = s20.parties("hp4", hpgof(("lvl_003_DragonWoods", 4, 3), None, None))
        assert (parties[0].rang, parties[0].boucliers, parties[1]) == (4, 3, None)
        assert parties[0].ecrite == datetime(2026, 9, 28, 12, 23, 58)

    def test_la_partie_neuve_est_une_partie_tout_juste_commencee(self):
        avant = hpgof(("lvl_003_DragonWoods", 4, 3), None, None)
        apres = s20.nouvelle_partie_plus_hp4(avant, 1, 2, self.MAINTENANT)
        neuve = s20.parties("hp4", apres)[1]
        assert (neuve.rang, neuve.boucliers, neuve.ecrite) == (4, 3, datetime(2026, 11, 19, 20, 5, 7))
        p1, _ = s20.ouvrir(apres)
        assert p1[0xAC:0xAC + 0x60].rstrip(b"\0") == b"lvl_001_CampsiteWoods"
        source = {n: b for _t, n, b in self._blocs(avant, 1)}
        blocs = self._blocs(apres, 2)
        assert [(hex(t), n) for t, n, _b in blocs] == [
            ("0x722", ""), ("0x705", "GlobalData"), ("0x705", "SaveFlags"), ("0x705", "MagicMastery"),
            ("0x723", "lvl_001_CampsiteWoods"), ("0x723", "FrontEnd_CharacterSelect")], "l'ordre du jeu"
        assert blocs[0][2][12:] == b"evaslvl_001_CampsiteWoods\0"
        assert blocs[1][2] == source["GlobalData"] and blocs[3][2] == source["MagicMastery"]
        drapeaux = s20._enregistrements(blocs[2][2])
        assert all(blocs[2][2][d + 8:d + 12] == bytes(4) for d, _l, i in drapeaux if i < 8)
        assert blocs[2][2][:60] == source["SaveFlags"][:60], "le reste de SaveFlags est repris tel quel"

    def test_la_partie_d_origine_ne_bouge_pas(self):
        avant = hpgof(("lvl_003_DragonWoods", 4, 3), None, ("lvl_002_DADA", 1, 0))
        apres = s20.nouvelle_partie_plus_hp4(avant, 1, 2, self.MAINTENANT)
        (a1, a2), (n1, n2) = s20.ouvrir(avant), s20.ouvrir(apres)
        for k in (0, 2):
            assert n1[k * 0xAC:(k + 1) * 0xAC] == a1[k * 0xAC:(k + 1) * 0xAC]
            assert n2[k * 0x2800:(k + 1) * 0x2800] == a2[k * 0x2800:(k + 1) * 0x2800]

    def test_reecrire_la_sienne(self):
        avant = hpgof(("lvl_003_DragonWoods", 4, 3), None, None)
        apres = s20.nouvelle_partie_plus_hp4(avant, 1, 1, self.MAINTENANT)
        assert [n for _t, n, _b in self._blocs(apres, 1)][-2:] == ["lvl_001_CampsiteWoods",
                                                                   "FrontEnd_CharacterSelect"]
        assert "ShieldGenerator" not in [n for _t, n, _b in self._blocs(apres, 1)]
        assert s20.parties("hp4", apres)[1] is None

    def test_jamais_par_dessus_une_autre_partie(self):
        with pytest.raises(ValueError):
            s20.nouvelle_partie_plus_hp4(hpgof(("lvl_003_DragonWoods", 4, 3), ("lvl_002_DADA", 1, 0), None),
                                         1, 2, self.MAINTENANT)

    def test_une_partie_sans_les_blocs_d_une_partie_neuve_n_est_pas_ecrite(self):
        """Pas d'historique du premier niveau : on ne devine rien."""
        p1, p2 = s20.ouvrir(hpgof(("lvl_003_DragonWoods", 4, 3), None, None))
        blocs = [b for t, b in s20._blocs(p2[:0x2800]) if s20._nom(t, b) != "FrontEnd_CharacterSelect"]
        corps = b"".join(blocs)
        octets = s20.composer(p1, corps + bytes(0x2800 - len(corps)) + p2[0x2800:])
        with pytest.raises(s20.Illisible):
            s20.nouvelle_partie_plus_hp4(octets, 1, 2, self.MAINTENANT)


# ── Le fichier du joueur ──

def _poser(jeu: str, octets: bytes) -> Path:
    dossier = {"hp4": "Electronic Arts/Harry Potter and the Goblet of Fire/HPGOF",
               "hp5": "Electronic Arts/Harry Potter et l'Ordre du Phénix/HPOOTP"}[jeu]
    chemin = sauvegardes.racines()["localappdata"] / dossier / ("HPGOF" if jeu == "hp4" else "HPOOTP")
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(octets)
    return chemin


class TestEcrire:
    def test_lire_le_fichier_du_joueur(self):
        assert s20.lire(_JEUX["hp5"]) is None, "pas de sauvegarde : rien à proposer"
        _poser("hp5", hpootp((15, 2), None, (4, 2)))
        lu = s20.lire(_JEUX["hp5"])
        assert lu is not None and lu.libre == 2 and [p.numero for p in lu.occupees] == [1, 3]
        assert s20.lire(_JEUX["hp6"]) is None

    def test_un_fichier_d_un_autre_format_ne_se_propose_pas(self):
        _poser("hp5", b"20CM" + bytes(100))
        assert s20.lire(_JEUX["hp5"]) is None

    def test_copie_de_securite_puis_ecriture(self):
        chemin = _poser("hp5", hpootp((15, 2), None, None))
        lu = s20.lire(_JEUX["hp5"])
        neufs = s20.difficulte_hp5(lu.octets, 1, 0, 1)
        assert s20.ecrire(_JEUX["hp5"], lu, neufs) == ""
        assert chemin.read_bytes() == neufs
        versions = copies_sauvegardes.versions("hp5")
        assert len(versions["HPOOTP"]) == 1, "l'état d'avant est à l'abri"

    def test_rien_si_le_jeu_a_reecrit_le_fichier_entre_temps(self):
        chemin = _poser("hp5", hpootp((15, 2), None, None))
        lu = s20.lire(_JEUX["hp5"])
        chemin.write_bytes(hpootp((16, 2), None, None))
        assert s20.ecrire(_JEUX["hp5"], lu, s20.difficulte_hp5(lu.octets, 1, 0, 1)) == "change"
        assert s20.parties("hp5", chemin.read_bytes())[0].avancement == 16

    def test_rien_sans_copie_de_securite(self, monkeypatch):
        chemin = _poser("hp4", hpgof(("lvl_003_DragonWoods", 4, 3), None, None))
        lu = s20.lire(_JEUX["hp4"])
        monkeypatch.setattr(copies_sauvegardes, "mettre_a_l_abri", lambda *a: False)
        neufs = s20.nouvelle_partie_plus_hp4(lu.octets, 1, 2, datetime(2026, 11, 19))
        assert s20.ecrire(_JEUX["hp4"], lu, neufs) == "copie"
        assert chemin.read_bytes() == lu.octets

    def test_jamais_un_fichier_que_le_jeu_refuserait(self):
        _poser("hp5", hpootp((15, 2), None, None))
        lu = s20.lire(_JEUX["hp5"])
        with pytest.raises(s20.Illisible):
            s20.ecrire(_JEUX["hp5"], lu, lu.octets[:-1])


# ── L'écran ──

pytest.importorskip("pytestqt")


class TestEcran:
    @staticmethod
    def _fenetre(qtbot, jeu, en_cours=""):
        from src.ui.choix_sauvegarde import ChoixSauvegarde
        dlg = ChoixSauvegarde(_JEUX[jeu], lambda: en_cours)
        qtbot.addWidget(dlg)
        return dlg

    @pytest.fixture
    def boites(self, monkeypatch):
        vues: list[str] = []
        monkeypatch.setattr("src.ui.choix_sauvegarde.message", lambda _p, _i, titre, *a, **k: vues.append(titre))
        return vues

    def test_pas_de_section_sans_sauvegarde(self, qtbot):
        from src.ui.choix_sauvegarde import bloc
        assert bloc(_JEUX["hp5"], lambda: "") is None
        assert bloc(_JEUX["hp6"], lambda: "") is None
        _poser("hp4", hpgof(("lvl_003_DragonWoods", 4, 3), None, None))
        section = bloc(_JEUX["hp4"], lambda: "")
        qtbot.addWidget(section)
        assert section is not None

    def test_hp5_une_partie_neuve_a_la_difficulte_choisie(self, qtbot, boites):
        chemin = _poser("hp5", hpootp((15, 2), None, (4, 2)))
        dlg = self._fenetre(qtbot, "hp5")
        assert [dlg.partie.itemText(i) for i in range(dlg.partie.count())][0].startswith("Partie 1 · 15 % · Difficile")
        assert dlg.difficulte.currentIndex() == 2, "la difficulté actuelle de la partie"
        assert dlg.ou.itemData(0) == 2 and dlg.ou.itemData(1) == 1, "neuve d'abord, puis la sienne"
        dlg.difficulte.setCurrentIndex(0)
        dlg.ecrire.click()
        assert [p.difficulte if p else None for p in s20.parties("hp5", chemin.read_bytes())] == [2, 0, 2]
        assert boites == ["C'est écrit"]

    def test_la_meme_difficulte_sur_la_meme_partie_ne_s_ecrit_pas(self, qtbot):
        _poser("hp5", hpootp((15, 2), (6, 1), (4, 2)))
        dlg = self._fenetre(qtbot, "hp5")
        assert dlg.ou.count() == 1, "aucun emplacement libre : seulement la réécrire"
        assert not dlg.ecrire.isEnabled()
        dlg.difficulte.setCurrentIndex(1)
        assert dlg.ecrire.isEnabled() and "copie de sécurité" in dlg.note.text()

    def test_ne_rien_ecrire(self, qtbot):
        chemin = _poser("hp4", hpgof(("lvl_003_DragonWoods", 4, 3), None, None))
        avant = chemin.read_bytes()
        dlg = self._fenetre(qtbot, "hp4")
        dlg.rien.click()
        assert chemin.read_bytes() == avant and dlg.result() == 0

    def test_jamais_pendant_que_le_jeu_tourne(self, qtbot, boites):
        chemin = _poser("hp4", hpgof(("lvl_003_DragonWoods", 4, 3), None, None))
        avant = chemin.read_bytes()
        dlg = self._fenetre(qtbot, "hp4", en_cours="Harry Potter et la Coupe de Feu")
        dlg.ecrire.click()
        assert chemin.read_bytes() == avant and boites == ["Partie en cours"]

    def test_hp4_reecrire_la_sienne_dit_ce_qui_repart(self, qtbot, boites):
        chemin = _poser("hp4", hpgof(("lvl_003_DragonWoods", 4, 3), None, None))
        dlg = self._fenetre(qtbot, "hp4")
        dlg.ou.setCurrentIndex(1)
        assert "repartent du début" in dlg.note.text()
        dlg.ecrire.click()
        assert s20.parties("hp4", chemin.read_bytes())[1] is None
        assert boites == ["C'est écrit"]

    def test_dans_l_onglet_difficulte_de_hp5(self, qtbot, tmp_path):
        """De bout en bout : la fenêtre des réglages pose la section sous les préréglages."""
        from dataclasses import replace
        from types import SimpleNamespace

        from src.ui.game_settings_dialog import GameSettingsDialog
        _poser("hp5", hpootp((15, 2), None, None))
        # Ses réglages de difficulté seulement : la page Image demanderait une vraie configuration.
        game = replace(_JEUX["hp5"], fix_settings=("degats_recus", "degats_infliges", "vie_joueur", "invincible"),
                       resolution=None)
        dossier = tmp_path / Path(game.executable).parent
        dossier.mkdir(parents=True)
        (dossier / "d3d9.ini").write_bytes(b"; Accio Launcher - PC fix\r\n[Accio.Window]\r\nWindowStyle=1\r\n"
                                           b"[Accio.Hardcore]\r\nDamageTaken=1\r\nDamageDealt=1\r\n"
                                           b"PlayerHealth=1\r\nInvincible=0\r\n")
        manager = SimpleNamespace(config=SimpleNamespace(install_path=tmp_path, reprise={}),
                                  game_language=lambda g: None, langues_disponibles=lambda g: ())
        dlg = GameSettingsDialog(game, manager, lambda c: True)
        qtbot.addWidget(dlg)
        dlg.ouvrir_onglet("difficulte")
        from PyQt6.QtWidgets import QPushButton
        assert dlg.findChild(QPushButton, "ouvrirChoixSauvegarde") is not None
