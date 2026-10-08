"""Dire pourquoi un jeu s'est arrêté, d'après ce que Windows a noté.

Les événements sont écrits comme `wevtutil qe … /f:xml /uni:true` les rend ;
leurs valeurs sont celles relevées sur le poste de Ludo le 2026-10-03
(`hp8.exe` c0000409 à +2 s dans un AUTRE processus, `d3d9.dll` 1.2.0.0 du
correctif, `paul.dll` mis en quarantaine dans `HP8\\pc`).
"""
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core import diagnostic_plantage as dp

C0000005 = 0xC0000005
C0000409 = 0xC0000409


def _evenement(temps: str, **champs) -> str:
    donnees = "".join(f"<Data Name='{k}'>{v}</Data>" for k, v in champs.items())
    return ("<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'><System>"
            f"<EventID>1000</EventID><TimeCreated SystemTime='{temps}'/></System>"
            f"<EventData>{donnees}</EventData></Event>")


def _sortie(*evenements: str) -> bytes:
    return b"\xff\xfe" + "".join(evenements).encode("utf-16-le")


BRUIT = dict(AppName="hp8.exe", ModuleName="hp8.exe", ModuleVersion="1.0.0.0",
             ExceptionCode="c0000409", FaultingOffset="006e5dfd", ProcessId="0x3d08",
             ModulePath=r"C:\Jeux\HP8\pc\hp8.exe")
WRAPPER = dict(AppName="hp8.exe", ModuleName="d3d9.dll", ModuleVersion="1.2.0.0",
               ExceptionCode="c0000005", FaultingOffset="00149ba8", ProcessId="0x31e8",
               ModulePath=r"C:\Jeux\HP8\pc\d3d9.dll")


class TestLecture:
    def test_xml_utf16_avec_accents(self):
        brut = _sortie(_evenement("2026-10-01T17:18:19.1Z", AppName="hp8.exe",
                                  AppPath=r"C:\EA\Deuxième Partie\pc\hp8.exe"))
        ev = dp.lire_evenements(brut)
        assert ev == [{"AppName": "hp8.exe", "AppPath": r"C:\EA\Deuxième Partie\pc\hp8.exe",
                       "_temps": "2026-10-01T17:18:19.1Z"}]

    def test_sortie_illisible_ne_leve_pas(self):
        assert dp.lire_evenements(b"\xff\xfe<Ev\x00") == []
        assert dp.lire_evenements(b"") == []

    @pytest.mark.parametrize("code, attendu", [
        (0, None), (1, None), (None, None), (True, None),
        (3221225477, C0000005),                 # Popen sous Windows : non signé
        (-1073741819, C0000005),                # même code, signé
    ])
    def test_code_de_plantage(self, code, attendu):
        assert dp.code_de_plantage(code) == attendu


class TestNotreProcessus:
    """L'événement retenu est celui de NOTRE processus, jamais le bruit."""

    def test_le_bruit_de_hp8_est_ecarte_par_le_pid(self):
        evs = [dict(BRUIT), dict(BRUIT, ProcessId="0x4108")]
        assert dp.choisir_evenement(evs, "hp8.exe", 0x4108, C0000409)["ProcessId"] == "0x4108"
        assert dp.choisir_evenement(evs[:1], "hp8.exe", 0x4108, C0000409) is None

    def test_le_code_doit_etre_celui_de_la_sortie(self):
        assert dp.choisir_evenement([dict(WRAPPER)], "hp8.exe", 0x31e8, C0000409) is None
        assert dp.choisir_evenement([dict(WRAPPER)], "HP8.EXE", 0x31e8, C0000005) is not None

    def test_un_autre_jeu_n_est_pas_le_notre(self):
        assert dp.choisir_evenement([dict(WRAPPER)], "hp7.exe", 0x31e8, C0000005) is None

    def test_le_premier_plantage_et_pas_sa_suite(self):
        """Relevé réel : même pid, `d3d9.dll` puis `ntdll.dll` une seconde après.
        La liste arrive du plus récent au plus ancien."""
        suite = dict(WRAPPER, ModuleName="ntdll.dll", ModulePath=r"C:\Windows\SysWOW64\ntdll.dll")
        ev = dp.choisir_evenement([suite, dict(WRAPPER)], "hp8.exe", 0x31e8, C0000005)
        assert ev["ModuleName"] == "d3d9.dll"

    def test_requete_bornee_au_debut_de_la_partie(self, monkeypatch):
        vu = []
        monkeypatch.setattr(dp, "_evenements", lambda canal, q, n: vu.append((canal, q)) or [])
        debut = datetime(2026, 10, 1, 19, 18, 17).astimezone()
        p = dp.plantage("hp8.exe", 1, C0000005, debut)
        assert p == dp.Plantage(C0000005)
        canal, q = vu[0]
        assert canal == "Application" and "EventID=1000" in q
        utc = (debut - timedelta(seconds=5)).astimezone(dp.timezone.utc)
        assert utc.strftime("@SystemTime>='%Y-%m-%dT%H:%M:%S.000Z'") in q


class TestQuarantaine:
    def test_fichier_retire_qui_manque_encore(self, tmp_path):
        jeu = tmp_path / "HP8"
        (jeu / "pc").mkdir(parents=True)
        dets = [{"Path": f"file:_{jeu}\\PC\\Paul.dll"},              # casse différente
                {"Path": f"file:_{jeu}\\pc\\paul.dll"},              # doublon
                {"Path": r"file:_D:\HP8\paul.dll"},                  # ailleurs : pas ce jeu
                {"Path": f"process:_pid:12;file:_{jeu}\\pc\\fps.dll"}]
        assert dp.fichiers_en_quarantaine(dets, jeu) == [r"PC\Paul.dll", r"pc\fps.dll"]

    def test_un_fichier_restaure_n_est_plus_une_cause(self, tmp_path):
        jeu = tmp_path / "HP8"
        (jeu / "pc").mkdir(parents=True)
        (jeu / "pc" / "paul.dll").write_bytes(b"MZ")
        assert dp.fichiers_en_quarantaine([{"Path": f"file:_{jeu}\\pc\\paul.dll"}], jeu) == []

    def test_le_dossier_lui_meme_n_est_pas_un_fichier_du_jeu(self, tmp_path):
        assert dp.fichiers_en_quarantaine([{"Path": f"file:_{tmp_path}"}], tmp_path) == []


class TestExplication:
    JEU = Path(r"C:\Jeux\HP8")

    @pytest.mark.parametrize("plantage, mot", [
        (dp.Plantage(dp.DLL_INTROUVABLE), "Vérifier / réparer"),
        (dp.Plantage(dp.DLL_INVALIDE), "abîmé"),
        (dp.Plantage(C0000005), "n'a pas noté"),
        (dp.Plantage(C0000409, "hp8.exe", r"C:\Jeux\HP8\pc\hp8.exe"), "le jeu lui-même"),
        (dp.Plantage(C0000005, "d3d9.dll", r"C:\Jeux\HP8\pc\d3d9.dll"), "installé avec le jeu"),
        (dp.Plantage(C0000005, "nvd3dumx.dll", r"C:\Windows\System32\DriverStore\nvd3dumx.dll"),
         "pilote de la carte graphique"),
        (dp.Plantage(C0000005, "KERNEL32.DLL", r"C:\Windows\SysWOW64\KERNEL32.DLL"),
         "composant de Windows"),
        (dp.Plantage(C0000005, "RTSSHooks.dll", r"C:\Program Files (x86)\RTSS\RTSSHooks.dll"),
         "extérieur au jeu"),
    ])
    def test_chaque_cas_a_sa_phrase(self, plantage, mot):
        assert mot in dp.expliquer(plantage, self.JEU, "hp8.exe")

    def test_detail_a_coller(self):
        p = dp.Plantage(C0000005, "d3d9.dll", "", "1.2.0.0", "00149ba8")
        assert dp.detail(p, "hp8.exe") == "hp8.exe · 0xc0000005 · d3d9.dll 1.2.0.0 · +0x00149ba8"
        assert dp.detail(dp.Plantage(C0000005), "hp8.exe") == "hp8.exe · 0xc0000005"


class TestApresLaPartie:
    @pytest.fixture
    def windows(self, monkeypatch, tmp_path):
        monkeypatch.setattr(dp.sys, "platform", "win32")
        jeu = tmp_path / "HP8"
        (jeu / "pc").mkdir(parents=True)
        journaux = {"Application": [], "Defender": []}

        def lire(canal, _q, _n):
            return journaux["Application" if canal == "Application" else "Defender"]
        monkeypatch.setattr(dp, "_evenements", lire)
        return jeu, journaux

    def test_une_vraie_partie_sortie_normalement_ne_dit_rien(self, windows):
        jeu, journaux = windows
        journaux["Application"] = [dict(BRUIT)]
        journaux["Defender"] = [{"Path": f"file:_{jeu}\\pc\\paul.dll"}]
        assert dp.apres_la_partie(jeu, "hp8.exe", 1, 0, datetime.now(), True) is None

    def test_lancement_rate_et_paul_dll_en_quarantaine(self, windows):
        jeu, journaux = windows
        journaux["Defender"] = [{"Path": f"file:_{jeu}\\pc\\paul.dll"}]
        c = dp.apres_la_partie(jeu, "hp8.exe", 1, 0, datetime.now(), False)
        assert c.genre == "antivirus" and c.fichiers == (r"pc\paul.dll",)

    def test_plantage_dans_le_correctif(self, windows):
        jeu, journaux = windows
        journaux["Application"] = [dict(BRUIT), dict(WRAPPER, ModulePath=f"{jeu}\\pc\\d3d9.dll")]
        c = dp.apres_la_partie(jeu, "hp8.exe", 0x31e8, 3221225477, datetime.now(), True)
        assert c.genre == "plantage"
        assert "installé avec le jeu" in c.cause and "d3d9.dll 1.2.0.0" in c.detail

    def test_lancement_rate_sans_rien_de_note(self, windows):
        jeu, _ = windows
        assert dp.apres_la_partie(jeu, "hp8.exe", 1, 0, datetime.now(), False) is None

    def test_hors_windows_rien(self, monkeypatch, tmp_path):
        monkeypatch.setattr(dp.sys, "platform", "linux")
        assert dp.apres_la_partie(tmp_path, "hp8.exe", 1, 3221225477, datetime.now(), False) is None


class TestSessionEtFenetre:
    def test_le_signal_part_d_un_fil_et_arrive_apres_terminee(self, qtbot, monkeypatch, tmp_path):
        from src.ui import game_session as gs
        game = SimpleNamespace(id="hp8", name="HP8", executable="HP8/pc/hp8.exe",
                               sauvegardes=None, post_install=None)
        manager = SimpleNamespace(
            config=SimpleNamespace(install_path=tmp_path, discord_presence=False),
            add_playtime=lambda *a: False, get_game_by_id=lambda _i: game,
            get_game_path=lambda _i: tmp_path / "HP8")
        session = gs.GameSession(manager)
        monkeypatch.setattr(gs.captures, "ramasser", lambda *_a: None)
        monkeypatch.setattr(gs.stats, "fermer_session", lambda: None)
        recu = []
        monkeypatch.setattr(gs.diagnostic_plantage, "apres_la_partie",
                            lambda *a: recu.append(a) or dp.Constat("plantage", "c", "d"))
        session._game_id, session._debut, session._pid = "hp8", datetime.now(), 42
        ordre = []
        session.terminee.connect(lambda *_a: ordre.append("terminee"))
        with qtbot.waitSignal(session.diagnostic, timeout=3000) as sig:
            session._on_game_exited("HP8", 3221225477, 3.0)
        assert ordre == ["terminee"]
        assert sig.args[0] == "hp8" and sig.args[1].genre == "plantage"
        assert recu[0][1:] == ("hp8.exe", 42, 3221225477, recu[0][4], False)
        assert session._pid is None

    @pytest.mark.parametrize("constat, boutons", [
        (dp.Constat("antivirus", "", fichiers=(r"pc\paul.dll",)), ()),
        (dp.Constat("plantage", "La cause.", "hp8.exe · 0xc0000005"),
         ("Copier le rapport", "Fermer")),
    ])
    def test_la_boite(self, qtbot, monkeypatch, constat, boutons):
        from src.ui import game_detail_handlers as h
        vues, copies = [], []
        monkeypatch.setattr(h, "_boite", lambda *a, **k: vues.append(a) or 0)
        monkeypatch.setattr(h, "copier_le_rapport", lambda v, en_tete="": copies.append(en_tete))
        notes = []
        vue = SimpleNamespace(notify=SimpleNamespace(emit=notes.append))
        h.signaler_plantage(vue, SimpleNamespace(name="HP8"), constat)
        texte = vues[0][3]
        if constat.genre == "antivirus":
            assert r"• pc\paul.dll" in texte and "Restaurer" in texte
            assert len(vues[0]) == 4                                 # un simple constat
        else:
            assert "La cause." in texte and "hp8.exe · 0xc0000005" in texte
            assert vues[0][4] == boutons
            # Le rapport complet, et en tête ce que la boîte vient de montrer.
            assert copies == ["HP8 — hp8.exe · 0xc0000005"]
