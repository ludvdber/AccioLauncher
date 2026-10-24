"""Le phonographe (`src/core/phonographe.py`) : pistes d'un jeu, flux sorti d'un paquet UE1."""

from src.core import phonographe
from src.core.phonographe import Piste, fichier_lisible, flux_umx, pistes, titre


def _compact(v: int) -> bytes:
    """Index compact UE1, pour fabriquer un paquet (valeurs positives)."""
    octets = bytearray([v & 0x3F])
    v >>= 6
    if v:
        octets[0] |= 0x40
    while v:
        octets.append((v & 0x7F) | (0x80 if v >> 7 else 0))
        v >>= 7
    return bytes(octets)


def _paquet(flux: bytes, fmt: str = "mp2", proprietes_vides: bool = True) -> bytes:
    """Un .umx minimal, même disposition que ceux de HP1 (version 75)."""
    noms = ["None", fmt, "Music", "Piste"]
    table = b"".join(_compact(len(n) + 1) + n.encode() + b"\0" + b"\0" * 4 for n in noms)
    objet = (_compact(0 if proprietes_vides else 3) + _compact(1) + b"\0" * 4
             + _compact(len(flux)) + flux)
    debut_noms = 64
    debut_objet = debut_noms + len(table)
    debut_exports = debut_objet + len(objet)
    export = (_compact(2) + _compact(0) + b"\0" * 4 + _compact(3) + b"\0" * 4
              + _compact(len(objet)) + _compact(debut_objet))
    entete = bytearray(64)
    entete[0:4] = (0x9E2A83C1).to_bytes(4, "little")
    entete[4:6] = (75).to_bytes(2, "little")
    entete[12:16] = len(noms).to_bytes(4, "little")
    entete[16:20] = debut_noms.to_bytes(4, "little")
    entete[20:24] = (1).to_bytes(4, "little")
    entete[24:28] = debut_exports.to_bytes(4, "little")
    return bytes(entete) + table + objet + export


class TestFluxUmx:
    def test_le_flux_et_son_format_sortent_intacts(self):
        flux = bytes(range(256)) * 600          # plus long qu'un index compact d'un octet
        assert flux_umx(_paquet(flux)) == ("mp2", flux)

    def test_un_fichier_qui_n_est_pas_un_paquet(self):
        assert flux_umx(b"OggS" + b"\0" * 100) is None

    def test_un_paquet_tronque_ne_leve_pas(self):
        assert flux_umx(_paquet(b"x" * 5000)[:200]) is None

    def test_un_objet_avec_proprietes_est_saute(self):
        assert flux_umx(_paquet(b"abc", proprietes_vides=False)) is None


class TestPistes:
    def test_hp2_lit_ses_ogg_quelle_que_soit_la_casse_du_dossier(self, tmp_path):
        (tmp_path / "music").mkdir()
        (tmp_path / "music" / "Adv4Greenhouse_Music_edit.ogg").write_bytes(b"OggS")
        (tmp_path / "music" / "notes.txt").write_text("x")
        trouvees = pistes("hp2", tmp_path)
        assert [p.titre for p in trouvees] == ["Adv4Greenhouse"]
        assert not trouvees[0].empaquetee

    def test_un_jeu_sans_source_ou_pas_installe(self, tmp_path):
        assert pistes("hp6", tmp_path) == []
        assert pistes("hp1", None) == []
        assert pistes("hp1", tmp_path) == []

    def test_les_jeux_couverts(self):
        assert phonographe.jeux_couverts() == ("hp1", "hp2", "hp3")


class TestTitre:
    def test_les_suffixes_de_travail_partent(self):
        assert titre("Common_Room") == "Common Room"
        assert titre("Fluffy_Flute_2_v4") == "Fluffy Flute 2 v4"
        assert titre("Cue29_withloop") == "Cue29"

    def test_un_nom_fait_seulement_d_un_suffixe_reste(self):
        assert titre("edit") == "edit"


class TestFichierLisible:
    def test_hp1_extrait_une_fois_puis_resert(self, tmp_path):
        source = tmp_path / "HP1" / "Music" / "Common_Room.umx"
        source.parent.mkdir(parents=True)
        source.write_bytes(_paquet(b"\xff\xf5" + b"m" * 3000))
        piste = pistes("hp1", tmp_path / "HP1")[0]
        assert piste.empaquetee
        cache = tmp_path / "cache"
        sortie = fichier_lisible(piste, cache)
        assert sortie == cache / "phonographe" / "hp1" / "Common_Room.mp2"
        assert sortie.read_bytes() == b"\xff\xf5" + b"m" * 3000
        source.unlink()                          # la copie extraite suffit ensuite
        assert fichier_lisible(piste, cache) == sortie
        assert not list((cache / "phonographe" / "hp1").glob("*.accio-tmp"))

    def test_un_format_que_le_lecteur_ne_sait_pas_ouvrir(self, tmp_path):
        source = tmp_path / "x.umx"
        source.write_bytes(_paquet(b"IMPM" * 10, fmt="it"))
        assert fichier_lisible(Piste("hp1", "x", source, True), tmp_path / "cache") is None

    def test_un_ogg_se_lit_tel_quel(self, tmp_path):
        source = tmp_path / "a.ogg"
        source.write_bytes(b"OggS")
        assert fichier_lisible(Piste("hp2", "a", source, False), tmp_path) == source
