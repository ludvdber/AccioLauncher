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
                manquants = [o for o in col.banque.ordre
                             if o.lower() not in noms and o not in col.banque.sans_video]
                assert not manquants, f"{jeu} : la banque nomme des vidéos absentes {manquants}"
                assert len(set(col.banque.ordre)) == len(col.banque.ordre)
                for chapitre in col.banque.chapitres:
                    absents = [n for n in chapitre.flux if n not in noms]
                    assert not absents, f"{jeu} : un chapitre nomme des vidéos absentes {absents}"
                    assert not set(chapitre.flux) & {o.lower() for o in col.banque.ordre}

    def test_hp5_et_hp6_relies_aux_chapitres(self):
        """Relevé le 2026-10-25 : les 20 vidéos de HP6 ont un son, 31 des 55 de HP5."""
        collections = cinematiques.charger()
        for jeu, attendu in (("hp6", 20), ("hp5", 31)):
            banque = collections[jeu].banque
            assert banque is not None
            relies = {o.lower() for o in banque.ordre} - set(banque.sans_video)
            relies |= {n for c in banque.chapitres for n in c.flux}
            assert len(relies) == attendu, jeu


def _index_langue(entrees: list[tuple[int, int, int]]) -> bytes:
    """Un index de langue HP6 : un bloc ATAD qui finit par (compte, positions, durées, hachages)."""
    tableau = struct.pack("<I", len(entrees)) + b"".join(struct.pack("<III", *e) for e in entrees)
    atad = _bloc(b"ATAD", b"\0" * 12 + tableau)
    return _bloc(b"MRTS", _bloc(b"PRGA", b"autre chose") + atad)


def _son_de_chapitre(octets_de_son: int, sous_titres: bytes = b"") -> bytes:
    """Un son de banque de chapitre : en-tête ADAT (sous-titres), zéros, puis le flux."""
    tete = b"ADAT" + struct.pack("<II", 2, 16 + len(sous_titres)) + b"SUB3" + sous_titres
    return tete + b"\0" * (0x40 - len(tete) % 0x40) + _flux(octets_de_son)


class TestBanqueDeChapitre:
    """HP6 : le son d'une cinématique dans la banque d'un chapitre, trouvé par son hachage."""

    def test_positions_lues_dans_l_index(self):
        brut = _index_langue([(0, 1000, 0xAAAA), (0x200, 2000, 0x19CD6F76)])
        assert cinematiques.positions_index(brut) == {0xAAAA: 0, 0x19CD6F76: 0x200}
        assert cinematiques.positions_index(b"ATAD\xff\xff\xff\xff") == {}
        assert cinematiques.positions_index(b"") == {}

    def test_flux_a_saute_l_en_tete_adat(self, tmp_path):
        premier = _son_de_chapitre(100, "Comme vous le savez".encode("utf-16-le"))
        archive = tmp_path / "d.big"
        archive.write_bytes(_bigf({"b_s.sdt": premier + _son_de_chapitre(300)}))
        e = archives_ea.lister(archive)[0]
        debut, taille = archives_ea.flux_a(archive, e, len(premier))
        assert taille == len(_flux(300))
        assert archive.read_bytes()[debut:debut + 4] == b"SCHl"
        assert archives_ea.flux_a(archive, e, 3) is None          # pas un début de son
        assert archives_ea.flux_a(archive, e, e.taille + 5) is None

    def _jeu(self, tmp_path):
        jeu = tmp_path / "HP6"
        jeu.mkdir()
        sons = [_son_de_chapitre(100), _son_de_chapitre(200), _son_de_chapitre(300)]
        positions = [0, len(sons[0]), len(sons[0]) + len(sons[1])]
        en = [_son_de_chapitre(111), _son_de_chapitre(222)]
        # La langue et sa banque ne sont pas dans la même archive, comme dans HP6.
        (jeu / "data.big").write_bytes(_bigf({
            "chapters/hogwarts/fr-fr.str": _index_langue(
                [(positions[0], 1, 0x1), (positions[2], 3, 0x19CD6F76), (positions[1], 2, 0x2)]),
            "chapters/hogwarts/en-gb.str": _index_langue([(0, 1, 0x1), (len(en[0]), 2, 0x19CD6F76)])}))
        (jeu / "data2.big").write_bytes(_bigf({
            "chapters/hogwarts/fr-fr_s.sdt": b"".join(sons),
            "chapters/hogwarts/en-gb_s.sdt": b"".join(en)}))
        chapitre = cinematiques.Chapitre(("data.big", "data2.big"), "chapters/hogwarts/{code}.str",
                                         "chapters/hogwarts/{code}_s.sdt", {"ns03": 0x19CD6F76})
        banque = cinematiques.Banque("movies.big", {"fr": "ct/fr-fr_s.sdt", "en": "ct/en-gb_s.sdt"},
                                     ("ns01",), chapitres=(chapitre,))
        return jeu, cinematiques.Collection("movies/neutral", ".vp6", True, (), "movies.big", {}, banque)

    def test_le_son_de_la_cinematique_dans_sa_langue(self, tmp_path):
        jeu, collection = self._jeu(tmp_path)
        fr = cinematiques.voix(collection, jeu, "NS03", "fr")
        assert fr is not None and fr.convertir and fr.entree.taille == len(_flux(300))
        assert fr.entree.nom == "chapters/hogwarts/fr-fr_s_ns03.asf"
        en = cinematiques.voix(collection, jeu, "ns03", "en")
        assert en is not None and en.entree.taille == len(_flux(222))
        assert cinematiques.voix(collection, jeu, "ns04", "fr") is None

    def test_le_bloc_du_fichier(self):
        bloc = {"archive": "movies.big", "fichiers": {"fr": "x/fr-fr_s.sdt"}, "ordre": ["a"],
                "chapitres": [{"archives": ["data.big"], "index": "c/{code}.str",
                               "banque": "c/{code}_s.sdt", "flux": {"NS03": "19CD6F76", "x": "pas hexa"}},
                              {"archives": "data.big"}]}
        banque = cinematiques._banque(bloc)
        assert banque is not None and len(banque.chapitres) == 1
        assert banque.chapitres[0].flux == {"ns03": 0x19CD6F76}

    def test_discographie_coherente(self):
        from src.core import discographie
        for jeu, morceaux in discographie.charger().items():
            noms = [m.fichier.lower() for m in morceaux]
            assert len(noms) == len(set(noms)), f"{jeu} : morceau en double"
            assert all(m.titre.strip() for m in morceaux), f"{jeu} : titre vide"
