"""Archives EA (BIGF) et flux SCHl, sur des archives FABRIQUÉES (règle 78)."""

import struct

from src.core import archives_ea, cinematiques, phonographe


def _bigf(fichiers: dict[str, bytes]) -> bytes:
    """Une archive BIGF : en-tête, table (début et taille gros-boutistes, nom), contenus."""
    table = b"".join(struct.pack(">II", 0, 0) + nom.encode("latin-1") + b"\0" for nom in fichiers)
    taille_tete = 16 + len(table)
    pos, entrees, corps = taille_tete, b"", b""
    for nom, contenu in fichiers.items():
        entrees += struct.pack(">II", pos, len(contenu)) + nom.encode("latin-1") + b"\0"
        corps += contenu
        pos += len(contenu)
    tete = b"BIGF" + struct.pack("<I", taille_tete + len(corps)) + struct.pack(">II", len(fichiers), taille_tete)
    return tete + entrees + corps


def _bloc(etiquette: bytes, charge: bytes) -> bytes:
    return etiquette + struct.pack("<I", 8 + len(charge)) + charge


def _flux(octets_de_son: int) -> bytes:
    return (_bloc(b"SCHl", b"GSTR" + b"\0" * 28) + _bloc(b"SCCl", b"\1\0\0\0")
            + _bloc(b"SCDl", b"\x55" * octets_de_son) + _bloc(b"SCEl", b""))


def _mus(*flux: bytes, remplissage: int = 0) -> bytes:
    return b"\x12\x34\x56\x78" + b"\0" * 252 + (b"\0" * remplissage).join(flux)


class TestBigf:
    def test_liste_les_entrees(self, tmp_path):
        archive = tmp_path / "movies.big"
        archive.write_bytes(_bigf({"Movies/English/A.vp6": b"MVhd1234", "Movies/French/A.asf": b"SCHl"}))
        entrees = archives_ea.lister(archive)
        assert [e.nom for e in entrees] == ["Movies/English/A.vp6", "Movies/French/A.asf"]
        e = archives_ea.trouver(archive, "movies/english/a.VP6")
        assert e is not None and archive.read_bytes()[e.debut:e.debut + e.taille] == b"MVhd1234"

    def test_illisible_rend_vide(self, tmp_path):
        (tmp_path / "x.big").write_bytes(b"pas une archive")
        assert archives_ea.lister(tmp_path / "x.big") == ()
        assert archives_ea.lister(tmp_path / "absente.big") == ()

    def test_extraire_puis_reutiliser(self, tmp_path):
        archive = tmp_path / "a.big"
        archive.write_bytes(_bigf({"f.vp6": b"0123456789"}))
        e = archives_ea.lister(archive)[0]
        cible = tmp_path / "cache" / "f.vp6"
        assert archives_ea.extraire(archive, e.debut, e.taille, cible) == cible
        assert cible.read_bytes() == b"0123456789"
        assert archives_ea.extraire(archive, e.debut, e.taille, cible) == cible


class TestFlux:
    def test_flux_bout_a_bout_et_remplissage(self, tmp_path):
        archive = tmp_path / "music.big"
        mus = _mus(_flux(100), _flux(300), _flux(50), remplissage=37)
        archive.write_bytes(_bigf({"audio/music/x/x_stream.mus": mus}))
        flux = archives_ea.flux_schl(archive, archives_ea.lister(archive)[0])
        assert len(flux) == 3
        donnees = archive.read_bytes()
        for debut, taille in flux:
            assert donnees[debut:debut + 4] == b"SCHl"
            assert donnees[debut + taille - 8:debut + taille - 4] == b"SCEl"


class TestPhonographeHp4:
    def test_les_longs_flux_sont_des_morceaux_les_ambiances_non(self, tmp_path, monkeypatch):
        monkeypatch.setattr(phonographe, "SEUIL_MORCEAU", 200)
        jeu = tmp_path / "HP4"
        jeu.mkdir()
        (jeu / "music.big").write_bytes(_bigf({
            "audio/music/camp/camp_stream.mus": _mus(_flux(500), _flux(20), _flux(400)),
            "audio/music/camp_sfx/campsite_sfx_stream.mus": _mus(_flux(900)),
            "audio/music/camp/camp_mem0.mus": b"BNKl",
        }))
        pistes = phonographe.pistes("hp4", jeu)
        assert [p.identifiant for p in pistes] == ["camp_stream-1", "camp_stream-2"]
        lu = phonographe.fichier_lisible(pistes[1], tmp_path / "cache")
        assert lu is not None and lu.suffix == ".asf" and lu.read_bytes()[:4] == b"SCHl"


class TestCinematiquesArchive:
    def test_video_de_la_langue_puis_anglaise_et_voix(self, tmp_path):
        jeu = tmp_path / "HP4"
        jeu.mkdir()
        (jeu / "movies.big").write_bytes(_bigf({
            "Movies/English/AVcamp.vp6": b"MVhd-en",
            "Movies/French/AVlogo.vp6": b"MVhd-fr",
            "Movies/French/AVcamp.asf": b"SCHl-fr",
            "Movies/English/AVcamp.asf": b"SCHl-en",
        }))
        collection = cinematiques.Collection(
            "Movies/English", ".vp6", False,
            (cinematiques.Cinematique("AVcamp", "Camp", 0), cinematiques.Cinematique("AVlogo", "Logo", 0),
             cinematiques.Cinematique("AVabsente", "Rien", 0)),
            "movies.big", {"fr": "Movies/French", "en": "Movies/English"})
        sources = cinematiques.presentes(collection, jeu, "fr")
        assert set(sources) == {"AVcamp", "AVlogo"}
        video = cinematiques.lisible(sources["AVcamp"], tmp_path / "cache", "hp4")
        assert video is not None and video.read_bytes() == b"MVhd-en"
        voix_fr = cinematiques.voix(collection, jeu, "AVcamp", "fr")
        assert voix_fr is not None
        assert cinematiques.lisible(voix_fr, tmp_path / "cache", "hp4").read_bytes() == b"SCHl-fr"
        voix_es = cinematiques.voix(collection, jeu, "AVcamp", "es")
        assert cinematiques.lisible(voix_es, tmp_path / "cache", "hp4").read_bytes() == b"SCHl-en"
