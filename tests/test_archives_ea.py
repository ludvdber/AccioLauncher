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


    def test_un_flux_a_cheval_sur_deux_pas_de_recherche(self, tmp_path):
        """65 535 octets de remplissage : le « SCHl » suivant commence 2 octets
        avant la fin du premier pas de recherche (64 Kio). Les pas ne se
        recouvraient pas : le morceau disparaissait sans bruit."""
        archive = tmp_path / "music.big"
        mus = _mus(_flux(100), _flux(300), remplissage=(1 << 16) - 1)
        archive.write_bytes(_bigf({"audio/music/x/x_stream.mus": mus}))
        assert len(archives_ea.flux_schl(archive, archives_ea.lister(archive)[0])) == 2

    def test_toutes_les_coupures_possibles(self, tmp_path):
        archive = tmp_path / "music.big"
        for decalage in range(-6, 3):
            mus = _mus(_flux(10), _flux(20), remplissage=(1 << 16) + decalage)
            archive.write_bytes(_bigf({"m.mus": mus}))
            archives_ea._entrees_en_cache.cache_clear()
            entree = archives_ea.lister(archive)[0]
            assert len(archives_ea.flux_schl(archive, entree)) == 2, decalage

    def test_une_archive_tronquee_ne_rend_que_les_flux_entiers(self, tmp_path):
        archive = tmp_path / "music.big"
        mus = _mus(_flux(100), _flux(300))
        archive.write_bytes(_bigf({"m.mus": mus[:-20]}))
        assert len(archives_ea.flux_schl(archive, archives_ea.lister(archive)[0])) == 1

    def test_extraire_d_une_archive_trop_courte_ne_laisse_rien(self, tmp_path):
        archive = tmp_path / "a.big"
        archive.write_bytes(_bigf({"f.vp6": b"0123456789"}))
        e = archives_ea.lister(archive)[0]
        cible = tmp_path / "cache" / "f.vp6"
        assert archives_ea.extraire(archive, e.debut, e.taille + 50, cible) is None
        assert not cible.exists() and not list(cible.parent.glob("*.accio-tmp"))


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


class TestBanqueDeVoix:
    """HP5 : un flux par cinématique dans une banque `_s.sdt`, sans en-tête."""

    def _jeu(self, tmp_path, nombre):
        jeu = tmp_path / "HP5"
        jeu.mkdir()
        banque = b"".join(_flux(100 + 10 * i) for i in range(nombre))
        (jeu / "movies.big").write_bytes(_bigf({"events/ct/fr-fr_s.sdt": banque}))
        return jeu, cinematiques.Collection(
            "movies/neutral", ".vp6", True, (), "movies.big", {},
            cinematiques.Banque("movies.big", {"fr": "events/ct/fr-fr_s.sdt"}, ("aa01", "bb02", "cc03")))

    def test_le_flux_de_la_cinematique(self, tmp_path, monkeypatch):
        from src.core import vgmstream
        jeu, collection = self._jeu(tmp_path, 3)
        source = cinematiques.voix(collection, jeu, "bb02", "es")     # espagnol absent : la banque présente
        assert source is not None and source.convertir
        monkeypatch.setattr(vgmstream, "convertir", lambda src, cible: src)
        extrait = cinematiques.lisible(source, tmp_path / "cache", "hp5")
        assert extrait is not None and extrait.read_bytes()[:4] == b"SCHl"
        assert len(extrait.read_bytes()) == len(_flux(110))
        assert cinematiques.voix(collection, jeu, "zz99", "fr") is None

    def test_un_decalage_ne_donne_aucune_voix(self, tmp_path):
        jeu, collection = self._jeu(tmp_path, 2)
        assert cinematiques.voix(collection, jeu, "aa01", "fr") is None


class TestBanqueChoixDeLangue:
    def _jeu(self, tmp_path):
        jeu = tmp_path / "HP5"
        jeu.mkdir()
        fr = b"".join(_flux(100) for _ in range(2))
        de = b"".join(_flux(200) for _ in range(2))
        (jeu / "movies.big").write_bytes(_bigf({"ct/fr-fr_s.sdt": fr, "ct/de-de_s.sdt": de}))
        return jeu, cinematiques.Collection(
            "movies/neutral", ".vp6", True, (), "movies.big", {},
            cinematiques.Banque("movies.big", {"fr": "ct/fr-fr_s.sdt", "de": "ct/de-de_s.sdt"}, ("a", "b")))

    def test_la_langue_demandee_d_abord(self, tmp_path):
        jeu, collection = self._jeu(tmp_path)
        assert cinematiques.voix(collection, jeu, "B", "de").entree.taille == len(_flux(200))
        assert cinematiques.voix(collection, jeu, "b", "fr").entree.taille == len(_flux(100))

    def test_sans_la_langue_ni_l_anglais_la_premiere_presente(self, tmp_path):
        jeu, collection = self._jeu(tmp_path)
        assert cinematiques.voix(collection, jeu, "a", "it").entree.taille == len(_flux(100))

    def test_une_banque_absente_de_l_archive_passe_a_la_suivante(self, tmp_path):
        jeu = tmp_path / "HP5"
        jeu.mkdir()
        (jeu / "movies.big").write_bytes(_bigf({"ct/de-de_s.sdt": _flux(50) + _flux(60)}))
        collection = cinematiques.Collection(
            "m", ".vp6", True, (), "movies.big", {},
            cinematiques.Banque("movies.big", {"fr": "ct/fr-fr_s.sdt", "de": "ct/de-de_s.sdt"}, ("a", "b")))
        assert cinematiques.voix(collection, jeu, "b", "fr").entree.taille == len(_flux(60))
        assert cinematiques.voix(collection, None, "b", "fr") is None


class TestDonneesLivrees:
    """Les deux fichiers générés que le launcher embarque : une faute de
    génération y passerait sans bruit (une vidéo sans voix, un morceau fantôme)."""

    def test_cinematiques_coherentes(self):
        for jeu, col in cinematiques.charger().items():
            noms = [c.fichier.lower() for c in col.clips]
            assert len(noms) == len(set(noms)), f"{jeu} : cinématique en double"
            assert all(c.titre.strip() for c in col.clips), f"{jeu} : titre vide"
            if col.banque is not None:
                manquants = [o for o in col.banque.ordre if o.lower() not in noms]
                assert not manquants, f"{jeu} : la banque nomme des vidéos absentes {manquants}"
                assert len(set(col.banque.ordre)) == len(col.banque.ordre)

    def test_discographie_coherente(self):
        from src.core import discographie
        for jeu, morceaux in discographie.charger().items():
            noms = [m.fichier.lower() for m in morceaux]
            assert len(noms) == len(set(noms)), f"{jeu} : morceau en double"
            assert all(m.titre.strip() for m in morceaux), f"{jeu} : titre vide"
