"""Le drapeau « Large Address Aware » des exes 32 bits (`memoire_4go`, 2026-10-26)."""

import os
import struct
import sys
from pathlib import Path

import pytest

from src.core import memoire_4go as m


def _exe(machine: int = 0x14C, caract: int = 0x010F, taille: int = 2048) -> bytes:
    """Un en-tête PE minimal : MZ, e_lfanew = 0x80, COFF, en-tête optionnel."""
    d = bytearray(taille)
    d[:2] = b"MZ"
    struct.pack_into("<I", d, 0x3C, 0x80)
    d[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", d, 0x84, machine)
    struct.pack_into("<H", d, 0x80 + 22, caract)
    for i in range(0x200, taille, 7):
        d[i] = i & 0xFF
    return bytes(d)


class TestDrapeau:
    def test_pose_puis_retire_le_bit_et_rien_d_autre(self, tmp_path):
        exe = tmp_path / "jeu.exe"
        exe.write_bytes(_exe())
        assert m.a_le_drapeau(exe) is False
        assert m.poser(exe) and m.a_le_drapeau(exe) is True
        avant, apres = _exe(), exe.read_bytes()
        differences = [i for i in range(len(avant)) if avant[i] != apres[i]]
        # Le bit (octet bas des caractéristiques) et les 4 octets de la somme.
        somme = 0x80 + 24 + 64
        assert set(differences) <= {0x80 + 22, *range(somme, somme + 4)}
        assert m.poser(exe, oui=False) and m.a_le_drapeau(exe) is False
        assert exe.read_bytes()[:somme] == avant[:somme]

    def test_la_somme_est_celle_du_fichier_modifie(self, tmp_path):
        exe = tmp_path / "jeu.exe"
        exe.write_bytes(_exe())
        m.poser(exe)
        d = exe.read_bytes()
        pos = 0x80 + 24 + 64
        assert struct.unpack_from("<I", d, pos)[0] == m.somme_de_controle(d, pos)

    @pytest.mark.parametrize("taille", [0, 1, 2, 3, 7, 64, 4097])
    def test_la_somme_rapide_vaut_la_somme_repliee(self, taille):
        """Grand audit du 2026-11-02 : la somme passe par un seul entier modulo
        0xFFFF au lieu d'un tuple de 9 millions d'entiers ; même résultat que
        l'algorithme de `CheckSumMappedFile`, mot par mot."""
        import random
        rng = random.Random(taille)
        for _ in range(50):
            d = bytes(rng.randrange(256) for _ in range(taille))
            pos = taille // 3 if taille >= 8 else 0
            t = bytearray(d)
            t[pos:pos + 4] = b"\0" * len(t[pos:pos + 4])
            t += b"\0" * (len(t) % 2)
            total = sum(struct.unpack(f"<{len(t) // 2}H", t))
            while total >> 16:
                total = (total & 0xFFFF) + (total >> 16)
            assert m.somme_de_controle(d, pos) == (total + taille) & 0xFFFFFFFF

    @pytest.mark.skipif(sys.platform != "win32", reason="un exe signé de Windows")
    def test_la_somme_d_un_vrai_exe_de_windows(self):
        """La somme que Windows a écrite dans un de ses exes signés."""
        d = (Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "notepad.exe").read_bytes()
        pos = struct.unpack_from("<I", d, 0x3C)[0] + 24 + 64
        assert struct.unpack_from("<I", d, pos)[0] == m.somme_de_controle(d, pos)

    def test_deja_pose_le_fichier_n_est_pas_reecrit(self, tmp_path):
        exe = tmp_path / "jeu.exe"
        exe.write_bytes(_exe(caract=0x012F))
        date = exe.stat().st_mtime_ns
        assert m.poser(exe)
        assert exe.stat().st_mtime_ns == date

    def test_un_exe_64_bits_ou_pas_un_exe_n_est_pas_touche(self, tmp_path):
        exe64 = tmp_path / "x64.exe"
        exe64.write_bytes(_exe(machine=0x8664))
        texte = tmp_path / "lisez-moi.exe"
        texte.write_bytes(b"pas un programme")
        assert not m.poser(exe64) and exe64.read_bytes() == _exe(machine=0x8664)
        assert not m.poser(texte) and m.a_le_drapeau(texte) is None
        assert not m.poser(tmp_path / "absent.exe")

    def test_seulement_les_jeux_vus_avec(self, tmp_path, monkeypatch):
        exe = tmp_path / "jeu.exe"
        exe.write_bytes(_exe())
        monkeypatch.setattr(m, "JEUX", frozenset({"essaye"}))
        m.appliquer("autre", exe)
        assert m.a_le_drapeau(exe) is False
        m.appliquer("essaye", exe)
        assert m.a_le_drapeau(exe) is True


class TestPasDeRelectureInutile:
    def test_un_exe_qui_a_deja_le_drapeau_n_est_pas_relu(self, tmp_path, monkeypatch):
        """Audit du 2026-10-29 : `poser` lisait l'exe entier à chaque lancement,
        même quand le drapeau était déjà là."""
        from pathlib import Path
        exe = tmp_path / "hp.exe"
        exe.write_bytes(_exe())
        m.poser(exe)

        def interdit(self):
            raise AssertionError("exe relu en entier")
        monkeypatch.setattr(Path, "read_bytes", interdit)
        m.appliquer("hp1", exe)
        assert m.a_le_drapeau(exe) is True
