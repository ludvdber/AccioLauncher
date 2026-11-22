"""`core/mode_course` (1.5) : la table « à tenir » de chaque jeu, les écarts, entrer puis sortir rend l'ini À
L'OCTET, les clés de la course, le dossier neuf, la conclusion et la course interrompue. Logique pure."""

from dataclasses import replace
from pathlib import Path

import pytest

from src.core import course, mode_course
from src.core.game_data import GameData


@pytest.fixture(autouse=True)
def _course_sous_windows(monkeypatch):
    """Ces tests jugent une course « Windows » : sous Linux (CI), une course n'entre pas au classement
    (`course.SOUS_WINE`), ce que `test_sous_linux_la_course_est_refusee` vérifie à part."""
    monkeypatch.setattr(mode_course, "plateforme", lambda: "win32")

INI_HP2 = ("[Accio.Window]\r\nFPSLimit=0\r\nFillScreen=1\r\n\r\n[Accio.Lumos]\r\nLumosFade=1\r\n\r\n"
           "[Accio.Game]\r\nQuidditchDifficulty=2\r\nOneLife=0\r\nDeathCounter=0\r\nOneLifeSaves=\r\nRaceLog=0\r\n\r\n"
           "[Accio.Overlay]\r\nShowFPS=1\r\nRaceId=\r\n\r\n[Accio.Hardcore]\r\nDamageTaken=3\r\nDamageDealt=1\r\n")
INI_HP5 = ("[Accio.Window]\r\nFPSLimit=120\r\n\r\n[Accio.Game]\r\nUnlockFrameRate=1\r\nFrameRateCap=120\r\n"
           "RealFrameTime=1\r\nSimulationStep=0\r\nStepTimers=1\r\nStepPacing=1\r\nWandGate=0\r\n"
           "OneLife=0\r\nDeathCounter=0\r\nOneLifeSaves=\r\nRaceLog=0\r\nRaceSaves=\r\n\r\n"
           "[Accio.Graphics]\r\nSkyMode=0\r\n\r\n[Accio.Shaders]\r\nDump=0\r\n\r\n[Accio.Overlay]\r\nRaceId=\r\n\r\n"
           "[Accio.Hardcore]\r\nDamageTaken=1\r\nDamageDealt=1\r\nPlayerHealth=1\r\nInvincible=0\r\n")


def _jeu(game_id: str, exe: str) -> GameData:
    return GameData(id=game_id, name=game_id.upper(), year=2002, description="", developer="", executable=exe,
                    cover_image="", latest_version="1", recommended_version="1")


def _installer(tmp_path: Path, game_id: str, exe: str, nom_ini: str, texte: str) -> tuple[GameData, Path]:
    chemin = tmp_path / "jeux" / exe
    chemin.parent.mkdir(parents=True, exist_ok=True)
    ini = chemin.parent / nom_ini
    ini.write_bytes(texte.encode("utf-8"))
    return _jeu(game_id, exe), ini


EMPREINTE = course.Empreinte("ab" * 32, "abababab", ())


def test_chaque_jeu_a_sa_table():
    assert set(mode_course.A_TENIR) == set(course.JEUX)
    for jeu, table in mode_course.A_TENIR.items():
        cles = [(t.section, t.cle) for t in table]
        assert len(cles) == len(set(cles)), jeu
        assert ("Accio.Game", "OneLife") in cles and ("Accio.Hardcore", "DamageTaken") in cles
        for t in table:                       # la valeur posée est toujours tenue
            assert t.tenue(t.posee), (jeu, t.cle)


def test_reparations_et_champ_de_vision_gardes():
    """`LumosFade` (HP2), `TextMeasureCache` (HP3), FOV (S7.6) : jamais touchés."""
    toutes = {t.cle for table in mode_course.A_TENIR.values() for t in table}
    assert not toutes & {"LumosFade", "TextMeasureCache", "FOV", "AdaptiveFov", "AspectRatio", "ShowFPS"}


def test_limite_d_images():
    t = next(t for t in mode_course.A_TENIR["hp1"] if t.cle == "FPSLimit")
    assert t.tenue("60") and t.tenue("30") and not t.tenue("0") and not t.tenue("61") and not t.tenue(None)
    sky = next(t for t in mode_course.A_TENIR["hp6"] if t.cle == "SkyMode")
    assert sky.tenue("0") and sky.tenue("1") and not sky.tenue("2") and not sky.tenue("3")


def test_sans_les_cles_de_course_pas_de_course(tmp_path):
    """Les ini livrés de la 1.4 n'ont pas `RaceLog` : rien à proposer."""
    jeu, _ = _installer(tmp_path, "hp2", "HP2/system/Game.exe", "winmm.ini", INI_HP2.replace("RaceLog=0\r\n", ""))
    assert mode_course.ini(jeu, tmp_path / "jeux") is None
    jeu5, _ = _installer(tmp_path, "hp5", "HP5/hp.exe", "d3d9.ini", INI_HP5.replace("RaceSaves=\r\n", ""))
    assert mode_course.ini(jeu5, tmp_path / "jeux") is None
    assert mode_course.ini(_jeu("hp7a", "HP7a/pc/hp7.exe"), tmp_path / "jeux") is None


def test_ecarts(tmp_path):
    jeu, ini = _installer(tmp_path, "hp2", "HP2/system/Game.exe", "winmm.ini", INI_HP2)
    assert mode_course.ini(jeu, tmp_path / "jeux") == ini
    assert {(e.cle, e.valeur, e.posee) for e in mode_course.ecarts("hp2", ini)} == {
        ("FPSLimit", "0", "60"), ("QuidditchDifficulty", "2", "0"), ("DamageTaken", "3", "1")}


def test_entrer_puis_sortir_rend_l_ini_a_l_octet(tmp_path):
    jeu, ini = _installer(tmp_path, "hp2", "HP2/system/Game.exe", "winmm.ini", INI_HP2)
    avant = ini.read_bytes()
    (ini.parent / course.FICHIER).write_text("vieux journal", encoding="utf-8")
    etat = mode_course.entrer(jeu, ini, "Any%", EMPREINTE, "normal")
    assert mode_course.actif(ini) and mode_course.ecarts("hp2", ini) == []
    texte = ini.read_text(encoding="utf-8")
    assert f"RaceId={etat.ligne_id}" in texte and "RaceLog=1" in texte and "RaceSaves" not in texte
    assert etat.ligne_id.startswith(f"ACCIO {etat.code} ") and etat.ligne_id.endswith(" abababab HP2 Any%")
    assert not (ini.parent / course.FICHIER).exists()
    assert mode_course.arguments(jeu, tmp_path / "jeux") == ("PrivetDr.unr", "-SAVESLOT=7")
    assert [e.code for e in mode_course.en_cours("hp2")] == [etat.code]
    assert mode_course.sortir(etat)
    assert ini.read_bytes() == avant
    assert mode_course.en_cours() == [] and mode_course.arguments(jeu, tmp_path / "jeux") is None
    ou = course.dossier(etat.code)
    assert not (ou / course.AVANT).exists() and (ou / course.AVANT_RENDU).is_file()


def test_hp4_a_hp6_dossier_de_sauvegardes_neuf(tmp_path):
    jeu, ini = _installer(tmp_path, "hp5", "HP5/hp.exe", "d3d9.ini", INI_HP5.replace("Dump=0\r\n", ""))
    avant = ini.read_bytes()
    etat = mode_course.entrer(jeu, ini, "Any%", EMPREINTE, "normal")
    saves = course.dossier(etat.code) / course.SAUVEGARDES
    assert saves.is_dir() and not any(saves.iterdir())
    lu = {e.cle for e in mode_course.ecarts("hp5", ini)}
    assert lu == set()
    from src.core import reglages_correctif as rc
    assert rc.valeur_posee(ini, "Accio.Game", "RaceSaves") == etat.sauvegardes
    assert rc.valeur_posee(ini, "Accio.Game", "StepTimers") == "0"
    assert rc.valeur_posee(ini, "Accio.Window", "FPSLimit") == "60"
    assert mode_course.arguments(jeu, tmp_path / "jeux") == ()
    assert mode_course.sortir(etat) and ini.read_bytes() == avant


def test_cle_ajoutee_puis_retiree(tmp_path):
    """FrameRateCap absent sur HP5 : posé pour la course, retiré après (l'ini revient à l'octet)."""
    jeu, ini = _installer(tmp_path, "hp5", "HP5/hp.exe", "d3d9.ini", INI_HP5.replace("FrameRateCap=120\r\n", ""))
    avant = ini.read_bytes()
    etat = mode_course.entrer(jeu, ini, "Any%", EMPREINTE, "normal")
    assert "FrameRateCap=60" in ini.read_text(encoding="utf-8")
    assert mode_course.sortir(etat) and ini.read_bytes() == avant


def test_ini_sans_section_refuse_et_rend(tmp_path):
    jeu, ini = _installer(tmp_path, "hp2", "HP2/system/Game.exe", "winmm.ini",
                          INI_HP2.replace("[Accio.Overlay]\r\nShowFPS=1\r\nRaceId=\r\n\r\n", ""))
    avant = ini.read_bytes()
    with pytest.raises(mode_course.CourseRefusee):
        mode_course.entrer(jeu, ini, "Any%", EMPREINTE, "normal")
    assert ini.read_bytes() == avant and mode_course.en_cours() == []


def test_conclure(tmp_path):
    from tests.test_course import HP2, journal
    jeu, ini = _installer(tmp_path, "hp2", "HP2/system/Game.exe", "winmm.ini", INI_HP2)
    avant = ini.read_bytes()
    etat = mode_course.entrer(jeu, ini, "Any%", EMPREINTE, "normal")
    evts = list(HP2)
    evts[0] = (0, "seance", "", f"HP2;fix=2.5.0;RaceId={etat.ligne_id}")
    (ini.parent / course.FICHIER).write_text(journal(*evts), encoding="utf-8", newline="\n")
    fin = mode_course.conclure(etat, "1.5.0")
    assert fin.rendu and fin.refus == () and fin.resultat.net == 34_000_000
    assert fin.journal is not None and course.verifier_journal(fin.journal).signature
    assert (course.dossier(etat.code) / course.FICHIER).is_file()
    donnees = course.lire_journal(fin.journal)
    assert donnees is not None and f"RaceId={etat.ligne_id}" in donnees["ini"]   # l'ini tel que posé
    assert ini.read_bytes() == avant and mode_course.en_cours() == []


def test_sous_linux_la_course_est_refusee(tmp_path, monkeypatch):
    """Hors Windows (Wine), la course est gardée mais refusée au classement, et le journal le dit."""
    from tests.test_course import HP2, journal
    monkeypatch.setattr(mode_course, "plateforme", lambda: "linux")
    jeu, ini = _installer(tmp_path, "hp2", "HP2/system/Game.exe", "winmm.ini", INI_HP2)
    etat = mode_course.entrer(jeu, ini, "Any%", EMPREINTE, "normal")
    evts = list(HP2)
    evts[0] = (0, "seance", "", f"HP2;fix=2.5.0;RaceId={etat.ligne_id}")
    (ini.parent / course.FICHIER).write_text(journal(*evts), encoding="utf-8", newline="\n")
    fin = mode_course.conclure(etat, "1.5.0")
    assert fin.rendu and fin.refus == (course.SOUS_WINE,)
    assert fin.journal is not None and course.verifier_journal(fin.journal).refus == (course.SOUS_WINE,)


def test_conclure_sans_journal(tmp_path):
    """Le correctif n'a rien écrit (DLL plus ancienne) : course refusée, réglages rendus quand même."""
    jeu, ini = _installer(tmp_path, "hp2", "HP2/system/Game.exe", "winmm.ini", INI_HP2)
    etat = mode_course.entrer(jeu, ini, "Any%", EMPREINTE, "normal")
    fin = mode_course.conclure(etat, "1.5.0")
    assert fin.refus == (course.SANS_SEANCE,) and fin.rendu


def test_ini_rendu_impossible_reste_a_rendre(tmp_path, monkeypatch):
    jeu, ini = _installer(tmp_path, "hp2", "HP2/system/Game.exe", "winmm.ini", INI_HP2)
    etat = mode_course.entrer(jeu, ini, "Any%", EMPREINTE, "normal")
    monkeypatch.setattr(mode_course.rc, "poser_valeur", lambda *a: (_ for _ in ()).throw(OSError("tenu")))
    assert not mode_course.sortir(etat)
    assert [e.code for e in mode_course.en_cours()] == [etat.code]


def test_avant_json_relu(tmp_path):
    jeu, ini = _installer(tmp_path, "hp2", "HP2/system/Game.exe", "winmm.ini", INI_HP2)
    etat = mode_course.entrer(jeu, ini, "Any%", replace(EMPREINTE, fichiers=(course.Fichier("a", 1, "b"),)), "normal")
    (relu,) = mode_course.en_cours("hp2")
    assert relu == etat


def test_supprimer_une_course_gardee(tmp_path):
    jeu, ini = _installer(tmp_path, "hp5", "HP5/hp.exe", "d3d9.ini", INI_HP5)
    etat = mode_course.entrer(jeu, ini, "Any%", EMPREINTE, "normal")
    assert not mode_course.supprimer(etat.code), "réglages pas encore rendus : avant.json les rend"
    assert course.dossier(etat.code).is_dir()
    mode_course.conclure(etat, "1.5.0")
    assert mode_course.supprimer(etat.code) and not course.dossier(etat.code).exists()
    with pytest.raises(ValueError):
        mode_course.supprimer("../../x")


def test_fantome_pose_au_depart_retire_a_la_sortie(tmp_path):
    jeu, ini = _installer(tmp_path, "hp2", "HP2/system/Game.exe", "winmm.ini", INI_HP2)
    avant = ini.read_bytes()
    etat = mode_course.entrer(jeu, ini, "Any%", EMPREINTE, "normal", fantome="PrivetDr\t10\n")
    assert (ini.parent / course.FANTOME).read_text(encoding="utf-8") == "PrivetDr\t10\n"
    assert mode_course.sortir(etat) and ini.read_bytes() == avant
    assert not (ini.parent / course.FANTOME).exists(), "le fantôme ne survit pas à la course"
    (ini.parent / course.FANTOME).write_text("vieux\t1\n", encoding="utf-8")
    etat = mode_course.entrer(jeu, ini, "Any%", EMPREINTE, "normal")
    assert not (ini.parent / course.FANTOME).exists(), "sans fantôme voulu, celui d'une course passée est retiré"
    mode_course.sortir(etat)
