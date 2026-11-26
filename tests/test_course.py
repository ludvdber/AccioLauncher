"""`core/course` (1.5) : code, ligne d'identifiant, empreinte, lecture du journal du correctif, sceaux, verdict,
journal signé. Logique pure, aucun `qtbot`. Les lignes ont la forme de `race::FormatLine` et `race::Write` du
correctif (cinq champs, « \\n », sceau FNV-1a des octets de la séance avant chaque `etat` et `fin`)."""

import json
import os
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

    def test_chaque_categorie_du_catalogue_tient_dans_la_ligne(self):
        """Les six jeux de la course ont leurs catégories (celles de speedrun.com), et chacune s'écrit dans la
        ligne ACCIO ; HP7 n'a pas de course."""
        from src.core.game_data import load_catalog
        jeux = {g.id: g for g in load_catalog().games}
        assert {j for j, g in jeux.items() if g.course is not None} == set(course.JEUX)
        for j in course.JEUX:
            regles = jeux[j].course
            assert regles is not None and regles.categories[0].ident == course.ANY
            for c in regles.categories:
                texte = course.ligne_id("7KQ2-M4XP", date(2026, 11, 18), "a3f9c1d2", j, c.ident)
                assert texte.endswith(f" {j.upper()} {c.ident}") and len(texte) <= course.LONGUEUR_ID
        assert {c.ident for c in jeux["hp4"].course.categories} == {"Any%", "100%", "All Shields"}
        assert all("Glitchless" not in jeux[j].course.idents for j in ("hp3", "hp4", "hp5", "hp6"))
        assert jeux["hp4"].course.temps == course.REEL and jeux["hp2"].course.temps == course.SANS_CHARGEMENTS
        for faux in ("Tout ; ou rien", "Any%\t", " Any%", "x" * 24):
            with pytest.raises(ValueError):
                course.ligne_id("7KQ2-M4XP", date(2026, 11, 18), "a3f9c1d2", "hp2", faux)

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
        # Deux écritures dans le même tic de l'horloge des fichiers ont la même date (un échec sur quatre sous
        # Windows) : la seconde est datée une seconde plus tard, comme deux courses réelles.
        premiere = course.dossier("7KQ2-M4XP") / course.JOURNAL
        t = premiere.stat().st_mtime_ns
        os.utime(chemin, ns=(t + 1_000_000_000, t + 1_000_000_000))
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
            refus: tuple[str, ...] = (), jour: str = "2026-11-20", ecrite: int = 0,
            reel: int | None = None) -> course.Passee:
    return course.Passee(code, "hp2", jour, net, True, refus, ecrite, categorie,
                         tuple(course.Segment(*s) for s in segments), net if reel is None else reel)


class TestTempsQuiClasse:
    """Le temps qui classe le jeu (réel pour HP4 à HP6, sans chargements ailleurs), les records successifs, la
    course idéale, les passages d'avant, la comparaison de deux courses."""

    def test_le_record_suit_le_temps_du_jeu(self):
        peu_de_chargements = _gardee("AAAA-AAAA", 100, reel=110, ecrite=1)
        beaucoup = _gardee("BBBB-BBBB", 90, reel=130, ecrite=2)
        assert course.meilleure([peu_de_chargements, beaucoup]).code == "BBBB-BBBB"
        assert course.meilleure([peu_de_chargements, beaucoup], None, course.REEL).code == "AAAA-AAAA"
        assert beaucoup.temps(course.REEL) == 130 and beaucoup.temps(course.SANS_CHARGEMENTS) == 90

    def test_les_deux_temps_relus_du_journal(self):
        r = course.analyser(journal(*HP2))
        assert (r.reel, r.net) == (39_000_000, 34_000_000)
        assert r.temps(course.REEL) == 39_000_000 and r.temps(course.SANS_CHARGEMENTS) == 34_000_000

    def test_records_successifs(self):
        suite = [_gardee("AAAA-AAAA", 50, jour="2026-11-01"), _gardee("BBBB-BBBB", 60, jour="2026-11-02"),
                 _gardee("CCCC-CCCC", 40, jour="2026-11-03"), _gardee("DDDD-DDDD", 30, jour="2026-11-04",
                                                                     refus=(course.RETOUCHE,)),
                 _gardee("EEEE-EEEE", 35, jour="2026-11-05"), _gardee("FFFF-FFFF", 1, categorie="100%")]
        assert [c.code for c in course.records(suite, "Any%")] == ["AAAA-AAAA", "CCCC-CCCC", "EEEE-EEEE"]

    def test_course_ideale_et_carte_traversee_deux_fois(self):
        """Le meilleur temps à chaque PLACE du parcours : le hub court de la première traversée ne remplace pas
        la seconde, longue."""
        a = _gardee("AAAA-AAAA", 60, ("Hub", 5, False), ("Donjon", 30, False), ("Hub", 25, False), ecrite=1)
        b = _gardee("BBBB-BBBB", 70, ("Hub", 4, False), ("Donjon", 40, False), ("Hub", 26, False), ecrite=2)
        detour = _gardee("CCCC-CCCC", 65, ("Hub", 1, False), ("Autre", 1, False), ecrite=3)
        ideale = course.ideale([a, b, detour], "Any%")
        assert ideale is not None and (ideale.net_us, ideale.a_gagner_us) == (4 + 30 + 25, 1)
        assert course.ideale([detour], "100%") is None
        seule = course.ideale([a], "Any%")
        assert seule is not None and seule.a_gagner_us == 0

    def test_course_ideale_au_temps_qui_classe(self):
        """En temps réel, l'idéale garde les chargements du record : seul le temps à gagner s'en retire."""
        a = _gardee("AAAA-AAAA", 30, ("PrivetDr", 10, False), ("Adv1Willow", 20, False), reel=40, ecrite=1)
        b = _gardee("BBBB-BBBB", 31, ("PrivetDr", 8, False), ("Adv1Willow", 23, False), reel=41, ecrite=2)
        reel = course.ideale([a, b], "Any%", course.REEL)
        assert reel is not None and (reel.net_us, reel.a_gagner_us, reel.temps_us) == (28, 2, 38)
        net = course.ideale([a, b], "Any%")
        assert net is not None and net.temps_us == net.net_us == 28

    def test_passages_d_avant(self):
        a = _gardee("AAAA-AAAA", 30, ("PrivetDr", 10, False), ("Adv1Willow", 20, False))
        b = _gardee("BBBB-BBBB", 31, ("PrivetDr", 12, False), ("Adv1Willow", 19, False))
        nouvelle = (course.Segment("PrivetDr", 11), course.Segment("Adv1Willow", 18))
        assert course.passages_d_avant([a, b], "CCCC-CCCC", "Any%", nouvelle) == (10, 19)
        assert course.passages_d_avant([a], "AAAA-AAAA", "Any%", a.segments) == (None, None), "pas elle-même"
        assert course.passages_d_avant([a, b], "CCCC-CCCC", "100%", nouvelle) == (None, None)

    def test_format_ecart(self):
        assert course.format_ecart(-3_000_000) == "−3.000" and course.format_ecart(512_000) == "+0.512"
        assert course.format_ecart(0) == "±0.000" and course.format_ecart(62_500_000) == "+1:02.500"
        assert course.format_ecart(-59_999_000) == "−59.999"

    def test_comparer_deux_courses(self):
        moi = _gardee("AAAA-AAAA", 30, ("PrivetDr", 10, False), ("Hub", 5, False), ("Fin", 10, False),
                      ("Hub", 5, False))
        ami = _gardee("BBBB-BBBB", 28, ("PrivetDr", 8, False), ("Raccourci", 4, False), ("Fin", 16, False))
        lignes = {c.carte: (c.a_us, c.b_us, c.ecart_us) for c in course.comparer(moi, ami)}
        assert list(lignes) == ["PrivetDr", "Hub", "Fin", "Raccourci"]
        assert lignes["PrivetDr"] == (10, 8, -2) and lignes["Hub"] == (10, None, None)
        assert lignes["Fin"] == (10, 16, 6) and lignes["Raccourci"] == (None, 4, None)


class TestCourseDUnAmi:
    """Un `course.json` partagé : relu, vérifié, son temps RECALCULÉ depuis ses lignes brutes."""

    @staticmethod
    def _signee(tmp_path: Path, retoucher=None) -> Path:
        r = course.analyser(journal(*HP2))
        donnees = course.contenu(
            game_id="hp2", categorie="Any%", code="7KQ2-M4XP", jour=date(2026, 11, 19), ligne=RACE_ID,
            empreinte_jeu=course.Empreinte("ab" * 32, "abababab", ()), launcher="1.5.0", ini="", ecarts=[],
            resultat=r, refus=course.verdict(r, course.Attendu(RACE_ID, True)), plateforme="win32",
            difficulte="normal")
        signe = dict(donnees)
        signe["signature"] = course.signer(signe)
        if retoucher is not None:
            retoucher(signe)
        chemin = tmp_path / "ami.json"
        chemin.write_text(json.dumps(signe), encoding="utf-8")
        return chemin

    def test_en_regle(self, tmp_path):
        ami = course.lire_externe(self._signee(tmp_path))
        assert ami is not None and ami.en_regle and ami.passee.code == "7KQ2-M4XP"
        assert (ami.passee.net_us, ami.passee.total_us) == (34_000_000, 39_000_000)
        assert [s.carte for s in ami.passee.segments] == ["PrivetDr", "Adv1Willow"]

    def test_temps_retouche_sans_refaire_la_signature(self, tmp_path):
        def plus_rapide(d):
            d["resultat"]["net_us"] = 1_000
        ami = course.lire_externe(self._signee(tmp_path, plus_rapide))
        assert ami is not None and not ami.en_regle and not ami.verification.signature
        assert ami.passee.net_us == 34_000_000, "le temps recalculé, pas celui écrit"

    def test_illisible(self, tmp_path):
        (tmp_path / "rien.json").write_text("{}", encoding="utf-8")
        assert course.lire_externe(tmp_path / "rien.json") is None
        assert course.lire_externe(tmp_path / "absent.json") is None


class TestReglesDuCatalogue:
    """Le bloc `race` d'un jeu (`course_regles`) : le catalogue est distant, tout y est contrôlé."""

    @staticmethod
    def _bloc(**change) -> dict:
        bloc = {"fix_min": "2.5.0", "timing": "real", "start": "Départ.", "end": "Arrivée.",
                "categories": [{"id": "Any%", "rule": "Vite."}, {"id": "All Shields", "name": "Tous les boucliers",
                                                                 "rule": "Les 38.", "note": "Écart."}],
                "i18n": {"en": {"start": "Start.", "end": "End."}}}
        bloc.update(change)
        return bloc

    def test_lu(self):
        from src.core import course_regles
        r = course_regles.lire(self._bloc())
        assert r is not None and r.correctif_min == (2, 5, 0) and r.temps == course.REEL
        assert r.idents == ("Any%", "All Shields") and r.categorie("All Shields").nom == "Tous les boucliers"
        assert r.categorie("Any%").nom == "Any%" and r.categorie("All Shields").note == "Écart."
        assert course_regles.lire(self._bloc(timing="loadless")).temps == course.SANS_CHARGEMENTS

    def test_traduit(self, monkeypatch):
        from src.core import course_regles, i18n
        monkeypatch.setattr(i18n, "_lang", "en")
        r = course_regles.lire(self._bloc())
        assert r is not None and (r.depart, r.arrivee) == ("Start.", "End.")

    @pytest.mark.parametrize("change", [
        {"fix_min": "2.x"}, {"fix_min": None}, {"timing": "rta"}, {"timing": 1}, {"start": ""},
        {"end": "x" * 401}, {"categories": []}, {"categories": "Any%"},
        {"categories": [{"id": "Any%"}, {"id": "Tout ; rien", "rule": "x"}, {"id": 5, "rule": "x"}]},
    ])
    def test_refuse(self, change):
        from src.core import course_regles
        assert course_regles.lire(self._bloc(**change)) is None
        assert course_regles.lire(None) is None and course_regles.lire([]) is None

    def test_doublon_et_categories_mal_formees_sautees(self):
        from src.core import course_regles
        r = course_regles.lire(self._bloc(categories=[{"id": "Any%", "rule": "a"}, {"id": "Any%", "rule": "b"},
                                                      {"id": "x" * 30, "rule": "c"}, {"id": "100%", "rule": "d"}]))
        assert r is not None and r.idents == ("Any%", "100%") and r.categorie("Any%").regle == "a"

    @pytest.mark.parametrize(("page", "lue"), [("hp1pc", "hp1pc"), (None, ""), ("../hp4", ""), ("HP4", ""),
                                               (4, ""), ("a" * 41, "")])
    def test_page_speedrun(self, page, lue):
        """L'identifiant finit dans une adresse : mal formé, pas de lien, mais la course reste."""
        from src.core import course_regles
        r = course_regles.lire(self._bloc(speedrun=page))
        assert r is not None and r.speedrun == lue

    def test_page_speedrun_de_chaque_jeu(self):
        from src.core.game_data import load_catalog
        pages = {g.id: g.course.speedrun for g in load_catalog().games if g.course is not None}
        assert pages == {"hp1": "hp1pc", "hp2": "hp2pc", "hp3": "hp3pc", "hp4": "hp4", "hp5": "hp5", "hp6": "hp6"}


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


class TestFantome:
    """Le fichier du fantôme que lit `race::ReadGhost` : le record carte par carte, cumulé, sa dernière ligne
    portant son temps."""

    def test_record_carte_par_carte(self):
        record = _gardee("AAAA-AAAA", 31, ("PrivetDr", 10, False), ("Burrow", 5, False), ("Burrow", 6, True),
                         ("Hub", 9, False), ecrite=1)
        plus_lent = _gardee("BBBB-BBBB", 40, ("PrivetDr", 1, False), ("Hub", 39, False), ecrite=2)
        autre = _gardee("CCCC-CCCC", 5, ("PrivetDr", 5, False), categorie="Glitchless")
        assert course.fantome([record, plus_lent, autre], "Any%") == "PrivetDr\t10\nBurrow\t21\nHub\t31\n", (
            "la carte rechargée compte une fois, à sa seconde sortie ; le temps du record en dernier")
        assert course.fantome([record], "Glitchless") is None, "pas de record dans la catégorie"
        assert course.fantome([_gardee("AAAA-AAAA", 5)], "Any%") is None, "un record sans segment"

    def test_noms_qui_casseraient_la_ligne_et_temps_final(self):
        record = _gardee("AAAA-AAAA", 50, ("", 10, False), ("A\tB", 10, False), ("Fin", 10, False))
        assert course.fantome([record], "Any%") == "?\t20\nFin\t50\n", (
            "un nom vide ou à tabulation devient « ? » ; la dernière ligne porte le temps officiel s'il est plus long")

    def test_trop_de_cartes(self):
        trop = _gardee("AAAA-AAAA", 600, *((f"M{i}", 1, False) for i in range(513)))
        assert course.fantome([trop], "Any%") is None, "le correctif refuserait le fichier entier"

    def test_poser_puis_retirer(self, tmp_path):
        course.poser_fantome(tmp_path, "PrivetDr\t10\n")
        assert (tmp_path / course.FANTOME).read_text(encoding="utf-8") == "PrivetDr\t10\n"
        course.poser_fantome(tmp_path, None)
        assert not (tmp_path / course.FANTOME).exists()
        course.poser_fantome(tmp_path, None)                       # rien à retirer : rien ne casse
        course.poser_fantome(tmp_path / "absent", "x\t1\n")       # dossier absent : noté, la course part
