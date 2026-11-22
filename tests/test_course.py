"""`core/course` (1.5) : code, ligne d'identifiant, empreinte, lecture du journal du correctif, sceaux, verdict,
journal signé. Logique pure, aucun `qtbot`. Les lignes ont la forme de `race::FormatLine` et `race::Write` du
correctif (cinq champs, « \\n », sceau FNV-1a des octets de la séance avant chaque `etat` et `fin`)."""

import json
from datetime import date
from pathlib import Path

import pytest

from src.core import course


def ligne(us: int, evenement: str, carte: str = "", detail: str = "") -> tuple[int, str, str, str]:
    return us, evenement, carte, detail


def journal(*evenements: tuple[int, str, str, str], heure: str = "2026-11-19T10:00:00") -> str:
    """Le fichier tel que la DLL l'écrit, sceaux compris."""
    texte, sceau = "", course.fnv1a64(b"")
    for us, ev, carte, detail in evenements:
        if ev == "seance":
            sceau = course.fnv1a64(b"")
        elif ev in ("etat", "fin"):
            detail = f"{detail};sceau={sceau:016x}"
        brute = f"{heure}\t{us}\t{ev}\t{carte}\t{detail}\n"
        sceau = course.fnv1a64(brute.encode("utf-8"), sceau)
        texte += brute
    return texte


RACE_ID = "ACCIO 7KQ2-M4XP 2026-11-19 a3f9c1d2 HP2 Any%"
HP2 = (
    ligne(0, "seance", "", f"HP2;fix=2.5.0;RaceId={RACE_ID}"),
    ligne(1, "reglages", "", "FPSLimit=60;QuidditchDifficulty=0;OneLife=0;DeathCounter=0;DamageTaken=1"),
    ligne(2, "reglages", "", "interdits="),
    ligne(1_000_000, "carte", "PrivetDr", ""),
    ligne(1_000_000, "depart", "PrivetDr", "nouvelle"),
    ligne(1_100_000, "charge_debut", "PrivetDr", ""),
    ligne(3_100_000, "charge_fin", "PrivetDr", ""),
    ligne(11_000_000, "etat", "PrivetDr", "fps=59.9;net=8000000"),
    ligne(20_000_000, "carte", "Adv1Willow", ""),
    ligne(20_000_000, "charge_debut", "Adv1Willow", ""),
    ligne(21_000_000, "sauve_debut", "Adv1Willow", ""),
    ligne(22_000_000, "charge_fin", "Adv1Willow", ""),
    ligne(23_000_000, "sauve_fin", "Adv1Willow", ""),
    ligne(40_000_000, "fin", "Credits", "total=39000000;pauses=5000000;net=34000000"),
)


class TestIdentifiant:
    def test_code_alphabet_et_forme(self):
        for _ in range(200):
            code = course.tirer_code()
            assert course.code_valide(code)
            assert not set(code) & set("0O1I")

    def test_codes_refuses(self):
        for faux in ("7KQ2M4XP", "7KQ2-M4X0", "../../x", "7kq2-m4xp", ""):
            assert not course.code_valide(faux)
        with pytest.raises(ValueError):
            course.dossier("../evil")

    def test_ligne_id(self):
        texte = course.ligne_id("7KQ2-M4XP", date(2026, 11, 18), "a3f9c1d2", "hp2", "Any%")
        assert texte == "ACCIO 7KQ2-M4XP 2026-11-18 a3f9c1d2 HP2 Any%"
        assert len(texte) <= course.LONGUEUR_ID

    def test_trois_categories_dans_la_ligne(self):
        assert course.CATEGORIES == ("Any%", "100%", "Glitchless")
        for categorie in course.CATEGORIES:
            texte = course.ligne_id("7KQ2-M4XP", date(2026, 11, 18), "a3f9c1d2", "hp6", categorie)
            assert texte.endswith(f" HP6 {categorie}") and len(texte) <= course.LONGUEUR_ID
        with pytest.raises(ValueError):
            course.ligne_id("7KQ2-M4XP", date(2026, 11, 18), "a3f9c1d2", "hp2", "any%")

    def test_ligne_id_bornee_et_ascii(self):
        with pytest.raises(ValueError):
            course.ligne_id("7KQ2-M4XP", date(2026, 11, 18), "a3f9c1d2", "hp2", "x" * 40)
        with pytest.raises(ValueError):
            course.ligne_id("7KQ2-M4XP", date(2026, 11, 18), "a3f9c1d2", "hp2", "Tout à 100 %")


class TestEmpreinte:
    @staticmethod
    def _jeu(tmp_path: Path) -> tuple[Path, Path]:
        jeu = tmp_path / "HP2"
        system = jeu / "system"
        (jeu / "Maps").mkdir(parents=True)
        system.mkdir()
        (system / "Game.exe").write_bytes(b"exe")
        (system / "Engine.u").write_bytes(b"scripts")
        (system / "winmm.dll").write_bytes(b"correctif")
        (system / "winmm.ini").write_text("[Accio.Game]\nRaceLog=0\n", encoding="utf-8")
        (system / "User.ini").write_text("[x]\n", encoding="utf-8")
        (jeu / "Maps" / "PrivetDr.unr").write_bytes(b"carte")
        return jeu, system

    def test_stable_et_sans_l_ini(self, tmp_path):
        jeu, system = self._jeu(tmp_path)
        a = course.empreinte("hp2", jeu, system)
        (system / "winmm.ini").write_text("[Accio.Game]\nRaceLog=1\n", encoding="utf-8")
        (system / "User.ini").write_text("[y]\n", encoding="utf-8")
        b = course.empreinte("hp2", jeu, system)
        assert a is not None and a == b
        assert [f.chemin for f in a.fichiers] == ["maps/privetdr.unr", "system/engine.u", "system/game.exe",
                                                  "system/winmm.dll"]
        assert a.courte == a.complete[:8]

    def test_sensible_a_un_octet(self, tmp_path):
        jeu, system = self._jeu(tmp_path)
        a = course.empreinte("hp2", jeu, system)
        (jeu / "Maps" / "PrivetDr.unr").write_bytes(b"cartf")
        assert course.empreinte("hp2", jeu, system) != a

    def test_hp4_a_hp6_archives(self, tmp_path):
        jeu = tmp_path / "HP5"
        jeu.mkdir()
        for nom in ("hp.exe", "data.big", "d3d9.dll", "d3d9.ini", "d3d9_accio.log"):
            (jeu / nom).write_bytes(nom.encode())
        emp = course.empreinte("hp5", jeu, jeu)
        assert emp is not None and [f.chemin for f in emp.fichiers] == ["d3d9.dll", "data.big", "hp.exe"]

    def test_cache_et_annulation(self, tmp_path, monkeypatch):
        jeu, system = self._jeu(tmp_path)
        cache: course.Cache = {}
        monkeypatch.setattr(course.signature, "fiable", lambda etat: (etat.st_mtime_ns, etat.st_size))
        a = course.empreinte("hp2", jeu, system, cache)
        assert len(cache) == 4
        lus: list[Path] = []
        vrai = course._sha256
        monkeypatch.setattr(course, "_sha256", lambda p, avance: lus.append(p) or vrai(p, avance))
        assert course.empreinte("hp2", jeu, system, cache) == a and not lus
        assert course.empreinte("hp2", jeu, system, annule=lambda: True) is None

    def test_sans_fichier(self, tmp_path):
        assert course.empreinte("hp2", tmp_path, tmp_path) is None


class TestJournal:
    def test_fnv_comme_le_correctif(self):
        assert course.fnv1a64(b"a") == 0xAF63DC4C8601EC8C   # race_test.cpp, « FNV-1a, 64 bits »

    def test_une_course_entiere(self):
        r = course.analyser(journal(*HP2))
        assert r.seances == 1 and r.jeu_dll == "HP2" and r.version_fix == "2.5.0" and r.race_id == RACE_ID
        assert r.depart == "nouvelle" and r.fin
        assert (r.total_us, r.pauses_us, r.net_us) == (39_000_000, 5_000_000, 34_000_000)
        # Deux pauses : 2 s, puis la sauvegarde ouverte pendant le chargement (20 s à 23 s, une seule pause).
        assert (r.total_calcule_us, r.pauses_calcule_us, r.net_calcule_us) == (39_000_000, 5_000_000, 34_000_000)
        assert r.chargements == 2 and r.fps_moyen == pytest.approx(59.9)
        assert r.sceaux == 2 and r.sceaux_intacts is True
        assert r.interdits == () and dict(r.reglages)["FPSLimit"] == "60"
        assert course.verdict(r, course.Attendu(RACE_ID, True)) == ()

    def test_decoupage_par_carte(self):
        r = course.analyser(journal(*HP2))
        assert [s.carte for s in r.segments] == ["PrivetDr", "Adv1Willow"]
        assert [s.net_us for s in r.segments] == [17_000_000, 17_000_000]
        assert sum(s.net_us for s in r.segments) == r.net_us

    def test_hp4_a_hp6_depart_au_debut_du_chargement(self):
        # `StartFromLastLoad` : la ligne `depart` est écrite APRÈS le chargement, datée de son début.
        r = course.analyser(journal(
            ligne(0, "seance", "", "HP5;fix=2.5.0;RaceId=X"),
            ligne(5_000_000, "charge_debut"), ligne(9_000_000, "charge_fin"),
            ligne(5_000_000, "depart", "", "nouvelle"),
            ligne(9_100_000, "carte", "LW"),
            ligne(15_000_000, "fin", "LW", "total=10000000;pauses=4000000;net=6000000")))
        assert (r.total_calcule_us, r.pauses_calcule_us, r.net_calcule_us) == (10_000_000, 4_000_000, 6_000_000)
        assert [s.carte for s in r.segments] == ["LW"] and r.segments[0].net_us == 6_000_000

    def test_seule_la_derniere_seance(self):
        texte = journal(*HP2[:5]) + journal(*HP2)
        r = course.analyser(texte)
        assert r.seances == 2 and r.fin
        assert course.RELANCE in course.verdict(r, course.Attendu(RACE_ID, True))

    def test_sans_fin(self):
        r = course.analyser(journal(*HP2[:-1]))
        assert not r.fin and r.net == r.net_calcule_us == 23_000_000 - 1_000_000 - 5_000_000
        assert course.SANS_FIN in course.verdict(r, course.Attendu(RACE_ID, True))

    def test_net_retouche(self):
        """Le sceau de `fin` porte sur les lignes d'AVANT elle : la ligne `fin` seule retouchée garde des sceaux
        intacts, et c'est le recalcul des pauses qui la voit."""
        texte = journal(*HP2).replace("net=34000000;", "net=30000000;")
        r = course.analyser(texte)
        assert r.sceaux_intacts is True
        assert course.RETOUCHE in course.verdict(r, course.Attendu(RACE_ID, True))

    def test_pause_retouchee_et_net_refait(self):
        """Une pause allongée ET un `net` refait pour aller avec : le recalcul concorde, le sceau non."""
        texte = journal(*HP2).replace("\t3100000\tcharge_fin", "\t9100000\tcharge_fin").replace(
            "pauses=5000000;net=34000000", "pauses=11000000;net=28000000")
        r = course.analyser(texte)
        assert r.net_calcule_us == r.net_us == 28_000_000
        assert r.sceaux_intacts is False and course.RETOUCHE in course.verdict(r, course.Attendu(RACE_ID, True))

    def test_ligne_ajoutee_casse_le_sceau(self):
        lignes_ = journal(*HP2).split("\n")
        lignes_.insert(6, "2026-11-19T10:00:00\t3200000\tcharge_fin\tPrivetDr\t")
        assert course.analyser("\n".join(lignes_)).sceaux_intacts is False

    def test_interdits(self):
        evts = list(HP2)
        evts[2] = ligne(2, "reglages", "", "interdits=FPSLimit,RealFrameTime")
        r = course.analyser(journal(*evts))
        assert r.interdits == ("FPSLimit", "RealFrameTime")
        assert course.INTERDITS in course.verdict(r, course.Attendu(RACE_ID, True))

    def test_lignes_mal_formees_sautees(self):
        texte = "pas une ligne\n" + journal(*HP2) + "2026-11-19T10:00:00\tcoupé"
        assert course.analyser(texte).fin

    @pytest.mark.parametrize(("depart", "code"), [
        ("sauvegarde", course.DEPART_CHARGE), ("nouvelle;clic=non", course.DEPART_CLIC),
        ("inconnu", course.DEPART_INCONNU)])
    def test_departs_refuses(self, depart, code):
        evts = list(HP2)
        evts[4] = ligne(1_000_000, "depart", "PrivetDr", depart)
        assert code in course.verdict(course.analyser(journal(*evts)), course.Attendu(RACE_ID, True))

    def test_autres_refus(self):
        r = course.analyser(journal(*HP2))
        assert course.verdict(r, course.Attendu("autre", True)) == (course.AUTRE_ID,)
        assert course.verdict(r, course.Attendu(RACE_ID, False)) == (course.MODE_NON_TENU,)
        assert course.verdict(r, course.Attendu(RACE_ID, True, sous_wine=True)) == (course.SOUS_WINE,)
        assert course.verdict(course.analyser(""), course.Attendu(RACE_ID, True)) == (course.SANS_SEANCE,)
        evts = list(HP2)
        evts[7] = ligne(11_000_000, "etat", "PrivetDr", "fps=75.0;net=8000000")
        assert course.TROP_D_IMAGES in course.verdict(course.analyser(journal(*evts)), course.Attendu(RACE_ID, True))

    def test_lire_et_retirer(self, tmp_path):
        assert course.lire(tmp_path) == ""
        (tmp_path / course.FICHIER).write_text(journal(*HP2), encoding="utf-8")
        assert course.analyser(course.lire(tmp_path)).fin
        assert course.retirer(tmp_path) and not (tmp_path / course.FICHIER).exists()

    def test_format_temps(self):
        assert course.format_temps(34_000_000) == "0:34.000"
        assert course.format_temps(3_723_456_789) == "1:02:03.456"
        assert course.format_temps(-5) == "0:00.000"


class TestJournalSigne:
    @staticmethod
    def _ecrire(code: str, categorie: str = "Any%") -> Path:
        r = course.analyser(journal(*HP2))
        emp = course.Empreinte("ab" * 32, "abababab", (course.Fichier("system/game.exe", 3, "cd" * 32),))
        course.creer_dossier(code)
        donnees = course.contenu(
            game_id="hp2", categorie=categorie, code=code, jour=date(2026, 11, 19), ligne=RACE_ID, empreinte_jeu=emp,
            launcher="1.5.0", ini="[Accio.Game]\nRaceLog=1\n", ecarts=[], resultat=r,
            refus=course.verdict(r, course.Attendu(RACE_ID, True)), plateforme="win32", difficulte="normal")
        return course.ecrire_journal(code, donnees)

    def test_signe_puis_verifie(self):
        chemin = self._ecrire("7KQ2-M4XP")
        v = course.verifier_journal(chemin)
        assert v.lisible and v.signature and v.concorde and v.refus == () and v.net_us == 34_000_000
        texte, code = course.rapport_verification(chemin)
        assert code == 0 and "intacte" in texte and "0:34.000" in texte

    def test_un_octet_change(self):
        chemin = self._ecrire("7KQ2-M4XP")
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
        donnees["resultat"]["net_us"] = 1
        chemin.write_text(json.dumps(donnees), encoding="utf-8")
        assert not course.verifier_journal(chemin).signature
        assert course.rapport_verification(chemin)[1] == 1

    def test_journal_brut_retouche_avec_signature_refaite(self):
        """Quelqu'un qui recompile signe ce qu'il veut (S7.7) ; le recalcul des pauses, lui, voit le `net` changé."""
        chemin = self._ecrire("7KQ2-M4XP")
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
        donnees["journal"] = [li.replace("net=34000000", "net=3400000") for li in donnees["journal"]]
        donnees["signature"] = course.signer(donnees)
        chemin.write_text(json.dumps(donnees), encoding="utf-8")
        v = course.verifier_journal(chemin)
        assert v.signature and course.RETOUCHE in v.refus and not v.concorde

    def test_dossier_neuf_jamais_reutilise(self):
        course.creer_dossier("7KQ2-M4XP")
        assert (course.dossier("7KQ2-M4XP") / course.SAUVEGARDES).is_dir()
        with pytest.raises(FileExistsError):
            course.creer_dossier("7KQ2-M4XP")

    def test_courses_gardees_et_meilleur_temps(self):
        self._ecrire("7KQ2-M4XP")
        chemin = self._ecrire("AAAA-BBBB")
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
        donnees["refus"] = [course.DEPART_CHARGE]
        donnees["resultat"]["net_us"] = 1_000_000            # plus rapide, mais refusée
        chemin.write_text(json.dumps(donnees), encoding="utf-8")
        gardees = course.passees("hp2")
        assert [c.code for c in gardees] == ["AAAA-BBBB", "7KQ2-M4XP"], "la plus récente d'abord"
        assert not gardees[0].valable and gardees[1].valable
        meilleure = course.meilleure(gardees)
        assert meilleure is not None and meilleure.code == "7KQ2-M4XP" and meilleure.net_us == 34_000_000
        assert course.passees("hp5") == [] and course.meilleure([]) is None
        assert len(course.passees()) == 2

    def test_categorie_et_segments_relus(self):
        self._ecrire("7KQ2-M4XP", "Glitchless")
        (gardee,) = course.passees("hp2")
        assert gardee.categorie == "Glitchless"
        assert [(s.carte, s.net_us) for s in gardee.segments] == [("PrivetDr", 17_000_000),
                                                                 ("Adv1Willow", 17_000_000)]
        assert course.meilleure([gardee], "Any%") is None and course.meilleure([gardee], "Glitchless") == gardee

    def test_segments_mal_formes_sautes(self):
        assert course._segments_lus([["A", 5, False], ["B", "5", False], ["C", True, False], "D", None]) == (
            course.Segment("A", 5, False),)
        assert course._segments_lus("pas une liste") == ()

    def test_demande_de_verification(self):
        assert course.demande_de_verification(["main.py"]) is None
        assert course.demande_de_verification(["main.py", "--verifier-course", "x.json"]) == Path("x.json")
        assert not course.verifier_journal(Path("absent.json")).lisible


def _gardee(code: str, net: int, *segments: tuple[str, int, bool], categorie: str = "Any%",
            refus: tuple[str, ...] = (), jour: str = "2026-11-20", ecrite: int = 0) -> course.Passee:
    return course.Passee(code, "hp2", jour, net, True, refus, ecrite, categorie,
                         tuple(course.Segment(*s) for s in segments))


class TestParCarte:
    """Le classement par niveau de la base de la 1.5 : le passage le plus court de chaque carte."""

    def test_meilleur_passage_de_chaque_carte(self):
        a = _gardee("AAAA-AAAA", 30, ("PrivetDr", 10, False), ("Adv1Willow", 20, False), ecrite=1)
        b = _gardee("BBBB-BBBB", 28, ("PrivetDr", 12, False), ("Adv1Willow", 16, False), ecrite=2)
        passages = course.par_carte([a, b], "Any%")
        assert [(p.carte, p.net_us, p.code) for p in passages] == [("PrivetDr", 10, "AAAA-AAAA"),
                                                                   ("Adv1Willow", 16, "BBBB-BBBB")]

    def test_ne_comptent_pas(self):
        valable = _gardee("AAAA-AAAA", 30, ("PrivetDr", 10, False), ("", 1, False), ("Adv1Willow", 20, False))
        rechargee = _gardee("BBBB-BBBB", 20, ("PrivetDr", 9, False), ("Adv1Willow", 1, True))
        refusee = _gardee("CCCC-CCCC", 5, ("PrivetDr", 2, False), refus=(course.DEPART_CHARGE,))
        autre = _gardee("DDDD-DDDD", 5, ("PrivetDr", 3, False), categorie="100%")
        passages = {p.carte: (p.net_us, p.code) for p in course.par_carte([valable, rechargee, refusee, autre],
                                                                          "Any%")}
        assert passages == {"PrivetDr": (9, "BBBB-BBBB"), "Adv1Willow": (20, "AAAA-AAAA")}
        assert course.par_carte([autre], "Glitchless") == ()

    def test_ordre_de_la_meilleure_course_et_egalite(self):
        lente = _gardee("AAAA-AAAA", 40, ("Hub", 5, False), ("Fin", 10, False), ecrite=1)
        rapide = _gardee("BBBB-BBBB", 30, ("Debut", 7, False), ("Hub", 5, False), ecrite=2)
        passages = course.par_carte([rapide, lente], "Any%")
        assert [p.carte for p in passages] == ["Debut", "Hub", "Fin"], "l'ordre de la meilleure course d'abord"
        assert next(p for p in passages if p.carte == "Hub").code == "AAAA-AAAA", "à égalité, la plus ancienne"


class TestLiveSplit:
    """Le .lss de la catégorie : le record découpé par carte, en temps de jeu ; les meilleurs segments pris parmi
    les courses du même parcours."""

    @staticmethod
    def _lire(texte: str):
        import xml.etree.ElementTree as ET
        return ET.fromstring(texte.encode("utf-8"))

    def test_record_et_meilleurs_segments(self):
        record = _gardee("AAAA-AAAA", 30_000_000, ("PrivetDr", 10_000_000, False), ("Burrow", 20_000_000, False), ecrite=1)
        meme = _gardee("BBBB-BBBB", 31_000_000, ("PrivetDr", 9_500_000, False), ("Burrow", 21_500_000, False), ecrite=2)
        autre = _gardee("CCCC-CCCC", 40_000_000, ("PrivetDr", 1_000_000, False), ("Hub", 39_000_000, False), ecrite=3)
        refusee = _gardee("DDDD-DDDD", 5, ("PrivetDr", 1, False), ("Burrow", 4, False), refus=(course.DEPART_CHARGE,))
        run = self._lire(course.livesplit("Harry Potter <2> & co", "Any%", [record, meme, autre, refusee]))
        assert run.findtext("GameName") == "Harry Potter <2> & co" and run.findtext("CategoryName") == "Any%"
        assert run.findtext("AttemptCount") == "4"
        segs = run.findall("Segments/Segment")
        assert [s.findtext("Name") for s in segs] == ["PrivetDr", "Burrow"]
        assert [s.findtext("SplitTimes/SplitTime/GameTime") for s in segs] == ["00:00:10.0000000", "00:00:30.0000000"]
        assert [s.findtext("BestSegmentTime/GameTime") for s in segs] == ["00:00:09.5000000", "00:00:20.0000000"], (
            "le meilleur de chaque segment parmi le même parcours ; l'autre parcours et la refusée ne comptent pas")

    def test_rechargee_heures_et_rien_a_exporter(self):
        long = _gardee("AAAA-AAAA", 3_723_456_789, ("PrivetDr", 3_600_000_000, False),
                       ("Burrow", 123_456_789, True), categorie="Glitchless")
        segs = self._lire(course.livesplit("HP2", "Glitchless", [long])).findall("Segments/Segment")
        assert segs[1].findtext("Name") == "Burrow (rechargée)"
        assert segs[1].findtext("SplitTimes/SplitTime/GameTime") == "01:02:03.4567890"
        assert course.livesplit("HP2", "Any%", [long]) is None, "aucun temps valable dans la catégorie"
        assert course.livesplit("HP2", "Any%", [_gardee("AAAA-AAAA", 5)]) is None, "un record sans segment"
