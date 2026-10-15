"""Les sauvegardes : où elles sont, et quelle partie a nourri laquelle.

Les racines (Documents, AppData) sont redirigées vers `tmp_path` par
`conftest._sauvegardes_hors_du_vrai_disque` : aucun test ne lit les vraies
sauvegardes de la machine.
"""

import os
from datetime import date, datetime

import pytest

from src.core import sauvegardes
from src.core.game_data import GameData, Sauvegardes, _parse_sauvegardes, load_catalog


def _poser(racine, rel, quand: datetime, contenu=b"x"):
    chemin = racine / rel
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(contenu)
    t = quand.timestamp()
    os.utime(chemin, (t, t))
    return chemin


@pytest.fixture
def docs():
    return sauvegardes.racines()["documents"]


HP1 = Sauvegardes(racine="documents", dossiers=("Harry Potter/Save",),
                  fichiers="Save*.usa")
HP3 = Sauvegardes(racine="documents", dossiers=("Harry Potter*Azkaban/Save",),
                  fichiers="Save*.usa", exclure=("Save1??.usa",))
HP2 = Sauvegardes(racine="documents", dossiers=("Harry Potter II/Save",),
                  fichiers="Slot*/Save0.usa", premier=1)


class TestReleve:
    def test_trouve_les_emplacements(self, docs):
        _poser(docs, "Harry Potter/Save/Save0.usa", datetime(2026, 3, 8))
        _poser(docs, "Harry Potter/Save/Save1.usa", datetime(2026, 4, 3))
        _poser(docs, "Harry Potter/Save/GameSaveInfo0", datetime(2026, 4, 3))
        assert set(sauvegardes.releve(HP1)) == {"Save0.usa", "Save1.usa"}

    def test_le_dossier_suit_la_langue_du_jeu(self, docs):
        """Relevé sur une vraie machine : HP3 installé en français range ses
        sauvegardes sous « Harry Potter et le prisonnier d'Azkaban »."""
        _poser(docs, "Harry Potter et le prisonnier d'Azkaban/Save/Save0.usa",
               datetime(2026, 4, 6))
        assert set(sauvegardes.releve(HP3)) == {"Save0.usa"}

    def test_les_miroirs_de_hp3_sont_exclus(self, docs):
        for n in ("Save0", "Save100", "Save101"):
            _poser(docs, f"Harry Potter and the Prisoner of Azkaban/Save/{n}.usa",
                   datetime(2026, 3, 5))
        assert set(sauvegardes.releve(HP3)) == {"Save0.usa"}

    def test_l_emplacement_peut_etre_un_dossier(self, docs):
        _poser(docs, "Harry Potter II/Save/Slot1/Save0.usa", datetime(2026, 3, 28))
        _poser(docs, "Harry Potter II/Save/Slot1/Adv1Willow_pa.usa", datetime(2026, 3, 28))
        assert set(sauvegardes.releve(HP2)) == {"Slot1/Save0.usa"}

    def test_rien_ne_leve(self):
        assert sauvegardes.releve(None) == {}
        assert sauvegardes.releve(HP1) == {}      # dossier absent


HP7B = Sauvegardes(racine="localappdata",
                   dossiers=("Electronic Arts/Harry Potter*Deuxi*me Partie",
                             "Electronic Arts/Harry Potter*Part* 2"),
                   fichiers="auto.sav")


class TestPlusieursLangues:
    """HP7 range ses sauvegardes sous le titre de la langue JOUÉE : qui a joué
    en français puis en espagnol a deux dossiers (cas réel du 2026-09-26)."""

    FR = "Electronic Arts/Harry Potter et les Reliques de la Mort (TM) – Deuxième Partie"
    ES = "Electronic Arts/Harry Potter y las Reliquias de la Muerte (TM) – Parte 2"

    def test_le_dossier_de_la_derniere_partie_l_emporte(self):
        appdata = sauvegardes.racines()["localappdata"]
        _poser(appdata, f"{self.FR}/auto.sav", datetime(2026, 9, 1))
        _poser(appdata, f"{self.ES}/auto.sav", datetime(2026, 9, 20))
        assert sauvegardes.dossier(HP7B) == appdata / self.ES

    def test_un_dossier_sans_sauvegarde_ne_prend_pas_la_place(self):
        """Le cas de la machine relevée : l'espagnol n'a qu'un `config.txt`."""
        appdata = sauvegardes.racines()["localappdata"]
        _poser(appdata, f"{self.FR}/auto.sav", datetime(2026, 9, 1))
        _poser(appdata, f"{self.ES}/config.txt", datetime(2026, 9, 25))
        assert sauvegardes.dossier(HP7B) == appdata / self.FR

    def test_sans_aucune_sauvegarde_l_ordre_du_catalogue_decide(self):
        appdata = sauvegardes.racines()["localappdata"]
        _poser(appdata, f"{self.ES}/config.txt", datetime(2026, 9, 25))
        _poser(appdata, f"{self.FR}/config.txt", datetime(2026, 9, 1))
        assert sauvegardes.dossier(HP7B) == appdata / self.FR


class TestNumeros:
    def test_numerote_a_partir_du_premier_declare(self):
        assert sauvegardes.numero("Save0.usa", HP1, 2) == 1
        assert sauvegardes.numero("Slot1/Save0.usa", HP2, 1) == 1

    def test_une_sauvegarde_unique_n_a_pas_de_numero(self):
        unique = Sauvegardes(racine="localappdata",
                             dossiers=("Electronic Arts/x",), fichiers="auto.sav")
        assert sauvegardes.numero("auto.sav", unique, 1) is None


class TestSauvegardeRapide:
    """F5 dans HP1 écrit `Save9.usa`, hors des emplacements du menu du jeu."""

    def test_hp1_seulement(self):
        assert sauvegardes.est_rapide("hp1", "Save9.usa")
        assert sauvegardes.est_rapide("hp1", "save9.USA")
        assert not sauvegardes.est_rapide("hp1", "Save0.usa")
        assert not sauvegardes.est_rapide("hp3", "Save9.usa"), "relevé sur HP1 seulement"

    def test_ni_numero_ni_emplacement_10(self, docs):
        _poser(docs, "Harry Potter/Save/Save0.usa", datetime(2026, 3, 8))
        _poser(docs, "Harry Potter/Save/Save9.usa", datetime(2026, 3, 9))
        vues = sauvegardes.vues("hp1", HP1, stock={})
        assert [(v.fichier, v.numero, v.rapide) for v in vues] == [
            ("Save0.usa", 1, False), ("Save9.usa", None, True)]


class TestAttribution:
    def test_la_partie_va_a_la_sauvegarde_ecrite(self, docs, tmp_path):
        s0 = _poser(docs, "Harry Potter/Save/Save0.usa", datetime(2026, 3, 8))
        _poser(docs, "Harry Potter/Save/Save1.usa", datetime(2026, 4, 3))
        avant = sauvegardes.releve(HP1)
        t = datetime(2026, 9, 19, 22, 0).timestamp()
        os.utime(s0, (t, t))
        apres = sauvegardes.releve(HP1)
        retenue = sauvegardes.attribuer("hp1", avant, apres,
                                        datetime(2026, 9, 19, 21, 0), 3600)
        assert retenue == "Save0.usa"
        vues = {v.fichier: v for v in sauvegardes.vues("hp1", HP1)}
        assert vues["Save0.usa"].parties == 1 and vues["Save0.usa"].temps == 3600
        assert vues["Save0.usa"].derniere == date(2026, 9, 19)

    def test_une_sauvegarde_jamais_observee_ne_devine_pas_son_temps(self, docs):
        """Elle a des dates — le disque les porte — mais aucune partie vue."""
        _poser(docs, "Harry Potter/Save/Save1.usa", datetime(2026, 4, 3))
        (vue,) = sauvegardes.vues("hp1", HP1)
        assert vue.temps is None and vue.parties == 0
        assert vue.derniere == date(2026, 4, 3)

    def test_une_sauvegarde_creee_pendant_la_partie_commence_avec_elle(self, docs):
        avant = sauvegardes.releve(HP1)
        _poser(docs, "Harry Potter/Save/Save2.usa", datetime(2026, 9, 19, 22, 0))
        sauvegardes.attribuer("hp1", avant, sauvegardes.releve(HP1),
                              datetime(2026, 9, 19, 21, 0), 600)
        (vue,) = sauvegardes.vues("hp1", HP1)
        assert vue.commencee == date(2026, 9, 19)

    def test_sans_sauvegarde_ecrite_la_partie_n_appartient_a_personne(self, docs):
        _poser(docs, "Harry Potter/Save/Save0.usa", datetime(2026, 3, 8))
        etat = sauvegardes.releve(HP1)
        assert sauvegardes.attribuer("hp1", etat, etat, datetime.now(), 600) is None
        # ...mais elle est NOTÉE comme telle, pour que la page puisse le dire.
        assert sauvegardes.temps_sans_sauvegarde("hp1") == 600
        assert [v.fichier for v in sauvegardes.vues("hp1", HP1)] == ["Save0.usa"]

    def test_le_temps_sans_sauvegarde_n_inclut_pas_l_avant_releve(self):
        """Rien d'observé = rien d'affirmé : zéro, pas « tout le temps du jeu »."""
        assert sauvegardes.temps_sans_sauvegarde("hp6") == 0

    def test_plusieurs_changees_la_plus_recente_gagne(self):
        avant = {"a": sauvegardes.Etat(1.0, None), "b": sauvegardes.Etat(1.0, None)}
        apres = {"a": sauvegardes.Etat(5.0, None), "b": sauvegardes.Etat(9.0, None)}
        assert sauvegardes.modifiee(avant, apres) == "b"

    def test_un_fichier_illisible_est_mis_de_cote(self):
        chemin = sauvegardes.chemin_fichier()
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text("{pas du json", encoding="utf-8")
        assert sauvegardes.charger() == {}
        assert chemin.with_suffix(".corrompu").exists()


class TestCatalogue:
    def test_le_catalogue_embarque_declare_ses_sauvegardes(self):
        jeux = {g.id: g for g in load_catalog().games}
        assert jeux["hp1"].sauvegardes is not None
        assert jeux["hp3"].sauvegardes.exclure == ("Save1??.usa",)

    @pytest.mark.parametrize("bloc", [
        {"root": "C:/", "folders": ["x"], "files": "a"},
        {"root": "documents", "folders": ["../x"], "files": "a"},
        {"root": "documents", "folders": ["C:/Windows"], "files": "a"},
        {"root": "documents", "folders": ["x"], "files": "**/*.usa"},
        {"root": "documents", "folders": ["x"], "files": "a/b/c"},
        {"root": "documents", "folders": ["x"], "files": "HP.exe:flux"},
        {"root": "documents", "folders": [], "files": "a"},
        {"root": "documents", "folders": ["x"], "files": "a", "first": "0"},
    ])
    def test_un_bloc_douteux_est_ignore_en_entier(self, bloc):
        assert _parse_sauvegardes(bloc) is None

    def test_un_bloc_douteux_n_empeche_pas_le_jeu_de_se_charger(self):
        jeu = GameData.from_dict({
            "id": "x", "name": "X", "year": 2001, "description": "", "developer": "d",
            "executable": "X/x.exe", "cover_image": "x.jpg",
            "saves": {"root": "documents", "folders": ["../../x"], "files": "a"}})
        assert jeu.sauvegardes is None


# Aucun chemin Windows dans les `saves` du catalogue embarqué :
# tests/test_catalogue_embarque.py.


# ─── HP4 : trois emplacements dans un seul fichier ───

HP4 = Sauvegardes(racine="localappdata",
                  dossiers=("Electronic Arts/Harry Potter and the Goblet of Fire/HPGOF",),
                  fichiers="HPGOF", premier=1, emplacements="hp4")


def _hpgof(*emplacements) -> bytes:
    """Un `HPGOF` fabriqué sur la disposition relevée le 2026-09-30 (vraie
    sauvegarde de Ludo : emplacement 1 le 28/09 12:23:58, classement 4 niveau 3 ;
    emplacement 2 le 30/09 18:54:30 ; emplacement 3 vide). `None` : vide."""
    entete = bytearray(b"20CM" + b"\0" * 0x21C) + b"\0" * 0x7000
    for k, quand in enumerate((*emplacements, None, None, None)[:3]):
        base = 0x10 + k * 0xAC
        if quand is None:
            entete[base + 0xAC:base + 0xB4] = b"\xff" * 8
            continue
        entete[base + 0x6C:base + 0x76] = quand.strftime("%d/%m/%Y").encode()
        entete[base + 0x8C:base + 0x94] = quand.strftime("%H:%M:%S").encode()
        entete[base + 0xAC:base + 0xB4] = (4).to_bytes(4, "little") + (3).to_bytes(4, "little")
    return bytes(entete)


@pytest.fixture
def appdata():
    return sauvegardes.racines()["localappdata"]


RANGEE = "Electronic Arts/Harry Potter and the Goblet of Fire/HPGOF/HPGOF"


class TestEmplacementsDansUnFichier:
    """HP4 range ses trois parties dans `HPGOF` (vu à l'écran « Sélectionnez un
    emplacement ») : ses dates de fichier ne disent pas laquelle a bougé."""

    def test_les_emplacements_occupes_seulement(self):
        lus = sauvegardes.emplacements_hp4(
            _hpgof(datetime(2026, 9, 28, 12, 23, 58), datetime(2026, 9, 30, 18, 54, 30), None))
        assert lus == [(1, datetime(2026, 9, 28, 12, 23, 58).timestamp(), None),
                       (2, datetime(2026, 9, 30, 18, 54, 30).timestamp(), None)]

    def test_un_fichier_etranger_ne_rend_rien(self):
        assert sauvegardes.emplacements_hp4(b"PK\x03\x04" + b"\0" * 0x300) == []
        assert sauvegardes.emplacements_hp4(b"20CM") == []

    def test_une_date_illisible_garde_l_emplacement(self):
        entete = bytearray(_hpgof(datetime(2026, 9, 28, 12, 0, 0)))
        entete[0x7C:0x86] = b"31/31/2026"
        assert sauvegardes.emplacements_hp4(bytes(entete)) == [(1, None, None)]

    def test_le_releve_en_fait_des_sauvegardes_distinctes(self, appdata):
        _poser(appdata, RANGEE, datetime(2026, 9, 30, 18, 54, 30),
               _hpgof(datetime(2026, 9, 28, 12, 23, 58), datetime(2026, 9, 30, 18, 54, 30), None))
        etats = sauvegardes.releve(HP4)
        assert set(etats) == {"HPGOF#1", "HPGOF#2"}
        assert etats["HPGOF#1"].modifie == datetime(2026, 9, 28, 12, 23, 58).timestamp()

    def test_la_partie_va_a_l_emplacement_reecrit(self, appdata, tmp_path):
        """Le fichier entier est réécrit ; seul l'en-tête de l'emplacement joué change."""
        avant_1, avant_2 = datetime(2026, 9, 28, 12, 23, 58), datetime(2026, 9, 29, 20, 0, 0)
        _poser(appdata, RANGEE, avant_2, _hpgof(avant_1, avant_2, None))
        avant = sauvegardes.releve(HP4)
        _poser(appdata, RANGEE, datetime(2026, 9, 30, 21, 0, 0),
               _hpgof(datetime(2026, 9, 30, 21, 0, 0), avant_2, None))
        retenu = sauvegardes.attribuer("hp4", avant, sauvegardes.releve(HP4),
                                       datetime(2026, 9, 30, 20, 0, 0), 3600,
                                       chemin=tmp_path / "s.json")
        assert retenu == "HPGOF#1"

    def test_chaque_carte_porte_son_emplacement(self, appdata):
        """Même seul, « Emplacement 2 » est vrai : le jeu en montre toujours trois."""
        _poser(appdata, RANGEE, datetime(2026, 9, 30),
               _hpgof(None, datetime(2026, 9, 30, 18, 54, 30), None))
        vues = sauvegardes.vues("hp4", HP4, stock={})
        assert [(v.fichier, v.numero) for v in vues] == [("HPGOF#2", 2)]
        assert vues[0].derniere == date(2026, 9, 30)

    def test_le_catalogue_declare_le_format(self):
        assert _parse_sauvegardes({"root": "localappdata", "folders": ["X/HPOOTP"],
                                   "files": "HPOOTP", "slots": "hp5"}).emplacements == "hp5"

    def test_le_format_de_hp4_seul(self):
        bloc = {"root": "localappdata", "folders": ["Electronic Arts/X/HPGOF"],
                "files": "HPGOF", "slots": "hp4"}
        assert _parse_sauvegardes(bloc).emplacements == "hp4"
        # Un format que ce launcher ne connaît pas : le fichier reste UNE sauvegarde.
        assert _parse_sauvegardes({**bloc, "slots": "hp9"}).emplacements == ""

HP5 = Sauvegardes(racine="localappdata",
                  dossiers=("Electronic Arts/Harry Potter*Ph*nix/HPOOTP",),
                  fichiers="HPOOTP", premier=1, emplacements="hp5")
HPOOTP = "Electronic Arts/Harry Potter and the Order of the Phoenix/HPOOTP/HPOOTP"


def _hpootp(*parties: tuple[str, datetime, int] | None) -> bytes:
    """L'en-tête de `HPOOTP`, FABRIQUÉ sur le relevé du 2026-10-15 : `20CM`,
    trois fiches de 0x178 octets à partir de 0x20 (lieu, puis à +0x40 année,
    mois, jour de la semaine, jour, heure, minute, seconde ; pourcentage à +0x70)."""
    d = bytearray(0x1084)
    d[0:4] = b"20CM"
    for k, partie in enumerate(parties):
        if partie is None:
            continue
        lieu, quand, pourcent = partie
        base = 0x20 + k * 0x178
        d[base:base + len(lieu)] = lieu.encode()
        champs = (quand.year, quand.month, (quand.weekday() + 1) % 7, quand.day,
                  quand.hour, quand.minute, quand.second)
        for i, v in enumerate(champs):
            d[base + 0x40 + 4 * i:base + 0x44 + 4 * i] = v.to_bytes(4, "little")
        d[base + 0x70:base + 0x74] = pourcent.to_bytes(4, "little")
    return bytes(d)


class TestTroisPartiesDeHP5:
    """HP5 range trois parties dans `HPOOTP`, avec le pourcentage que montre
    l'écran « Continuer aventure » (VU le 2026-10-15 : 14 %, 6 %, 1 %)."""

    LUDO = (("Frontend", datetime(2026, 10, 1, 16, 8, 24), 14),
            ("Hogwarts", datetime(2026, 5, 3, 15, 59, 52), 6),
            ("GrimmauldPlace", datetime(2026, 4, 29, 21, 5, 13), 1))

    def test_les_trois_parties_comme_l_ecran(self):
        lus = sauvegardes.emplacements_hp5(_hpootp(*self.LUDO)[:0x500])
        assert lus == [(k + 1, quand.timestamp(), pourcent)
                       for k, (_, quand, pourcent) in enumerate(self.LUDO)]

    def test_une_fiche_vide_est_sautee(self):
        lus = sauvegardes.emplacements_hp5(_hpootp(None, self.LUDO[1], None)[:0x500])
        assert [n for n, _, _ in lus] == [2]

    def test_une_date_impossible_n_est_pas_une_partie(self):
        lus = sauvegardes.emplacements_hp5(
            _hpootp(("Hogwarts", datetime(2026, 5, 3), 6))[:0x500].replace(
                (2026).to_bytes(4, "little"), (1).to_bytes(4, "little"), 1))
        assert lus == []

    def test_un_pourcentage_absurde_n_est_pas_affiche(self):
        (lu,) = sauvegardes.emplacements_hp5(
            _hpootp(("Hogwarts", datetime(2026, 5, 3), 250))[:0x500])
        assert lu[2] is None, "la partie reste, sans pourcentage inventé"

    @pytest.mark.parametrize("brut", [b"", b"20CM", b"PK\x03\x04" + bytes(0x500)])
    def test_un_fichier_etranger_ne_rend_rien(self, brut):
        assert sauvegardes.emplacements_hp5(brut) == []

    def test_les_cartes_portent_leur_avancement(self, appdata):
        _poser(appdata, HPOOTP, datetime(2026, 10, 1, 16, 8, 24), _hpootp(*self.LUDO))
        vues = sauvegardes.vues("hp5", HP5, stock={})
        assert [(v.fichier, v.numero, v.avancement) for v in vues] == [
            ("HPOOTP#1", 1, 14), ("HPOOTP#2", 2, 6), ("HPOOTP#3", 3, 1)]
        assert vues[1].derniere == date(2026, 5, 3), "la date écrite par le jeu, pas celle du fichier"

    def test_la_carte_dit_l_avancement(self, appdata, qtbot):
        pytest.importorskip("pytestqt")
        from PyQt6.QtWidgets import QLabel
        from src.core.i18n import set_language
        from src.ui.stats_widgets import _CarteSauvegarde
        set_language("fr")
        _poser(appdata, HPOOTP, datetime(2026, 10, 1, 16, 8, 24), _hpootp(*self.LUDO))
        vue = sauvegardes.vues("hp5", HP5, stock={})[0]
        carte = _CarteSauvegarde(vue, 0)
        qtbot.addWidget(carte)
        textes = [lbl.text() for lbl in carte.findChildren(QLabel)]
        assert "Avancement" in textes and "14 %" in textes, textes
