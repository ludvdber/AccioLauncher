"""`core/classement` (1.5) : le classement Accio publié à côté du catalogue. Lecture stricte (une entrée mal
formée sautée, un fichier illisible ignoré), texte venu du réseau borné, vidéo seulement sur un hôte connu,
cache qui survit à un fichier refusé, place d'un temps. Logique pure."""

import json

import pytest

from src.core import classement


def _octets(jeux: object, fmt: object = classement.FORMAT) -> bytes:
    return json.dumps({"format": fmt, "jeux": jeux}).encode("utf-8")


def _course(joueur: object = "Ludo", temps: object = "31:04.512", jour: object = "2026-12-01", **reste: object):
    return {"joueur": joueur, "temps": temps, "date": jour, **reste}


class TestTemps:
    @pytest.mark.parametrize(("texte", "us"), [
        ("31:04.512", 1_864_512_000), ("1:02:03.456", 3_723_456_000), ("0:59.000", 59_000_000),
        (" 2:00.001 ", 120_001_000)])
    def test_lus(self, texte, us):
        assert classement.temps_us(texte) == us

    @pytest.mark.parametrize("texte", ["", "31:04", "31:04.5", "1:60:00.000", "61:00.000", "abc", "1:2:3.456",
                                       "-1:00.000"])
    def test_refuses(self, texte):
        assert classement.temps_us(texte) is None


class TestLire:
    def test_trie_par_temps_puis_par_jour(self):
        lu = classement.lire(_octets({"hp2": {"Any%": [
            _course("B", "31:00.000", "2026-12-02"), _course("A", "30:00.000"), _course("C", "31:00.000")]}}))
        assert lu is not None
        assert [e.joueur for e in lu.de("hp2", "Any%")] == ["A", "C", "B"], "à égalité, le plus ancien d'abord"
        assert lu.de("hp2", "100%") == () and lu.de("hp9", "Any%") == ()
        assert lu.categories("hp2") == ("Any%",)

    def test_entree_mal_formee_sautee_les_autres_restent(self):
        lu = classement.lire(_octets({"hp2": {"Any%": [
            _course(), _course(joueur=""), _course(joueur="x" * 41), _course(joueur="A‮B"),
            _course(joueur="A\nB"), _course(temps="vite"), _course(temps=1800), _course(jour="hier"),
            _course(jour="2026-13-01"), "pas un objet", _course(joueur=42)]}}))
        assert lu is not None and [e.joueur for e in lu.de("hp2", "Any%")] == ["Ludo"]

    def test_categorie_et_jeu_inconnus_ignores(self):
        lu = classement.lire(_octets({"hp2": {"Any%": [_course()], "Tout%": [_course()]},
                                      "../hp2": {"Any%": [_course()]}, "hp3": []}))
        assert lu is not None and set(lu.jeux) == {"hp2"} and lu.categories("hp2") == ("Any%",)

    @pytest.mark.parametrize("brut", [b"", b"pas du json", b"[]", _octets({}, fmt=2), _octets([]),
                                      b"\xff\xfe", b"[" * 100_000 + b"]" * 100_000])
    def test_fichier_illisible(self, brut):
        assert classement.lire(brut) is None

    def test_trop_gros(self):
        assert classement.lire(b" " * (classement.OCTETS_MAX + 1)) is None

    def test_au_plus_cent_par_categorie(self):
        lu = classement.lire(_octets({"hp2": {"Any%": [_course(f"J{i}") for i in range(150)]}}))
        assert lu is not None and len(lu.de("hp2", "Any%")) == classement.PAR_CATEGORIE_MAX

    def test_code_garde_seulement_s_il_est_valable(self):
        lu = classement.lire(_octets({"hp2": {"Any%": [_course(code="7KQ2-M4XP"), _course("B", code="<b>")]}}))
        assert lu is not None and {e.joueur: e.code for e in lu.de("hp2", "Any%")} == {"Ludo": "7KQ2-M4XP", "B": ""}


class TestVideo:
    @pytest.mark.parametrize("url", ["https://youtu.be/abc", "https://www.youtube.com/watch?v=abc",
                                     "https://www.twitch.tv/videos/1", "https://www.speedrun.com/hp1pc/run/x"])
    def test_hotes_connus(self, url):
        lu = classement.lire(_octets({"hp2": {"Any%": [_course(video=url)]}}))
        assert lu is not None and lu.de("hp2", "Any%")[0].video == url

    @pytest.mark.parametrize("url", ["http://youtu.be/abc", "https://youtu.be.exemple.com/x", "https://exemple.com",
                                     "https://moi:secret@youtu.be/x", "javascript:alert(1)", "https://youtu.be/a b",
                                     "https://youtu.be:8080/x", "https://youtu.be:abc/x", 42,
                                     "https://youtu.be/" + "a" * 300])
    def test_refusees_la_course_reste(self, url):
        lu = classement.lire(_octets({"hp2": {"Any%": [_course(video=url)]}}))
        assert lu is not None and lu.de("hp2", "Any%")[0].video == ""


class TestCache:
    def test_garder_puis_relire(self):
        assert classement.en_cache() == classement.VIDE, "rien encore reçu"
        assert classement.garder(_octets({"hp2": {"Any%": [_course()]}}))
        assert classement.en_cache().de("hp2", "Any%")[0].joueur == "Ludo"
        assert not classement.garder(b"pas du json"), "un fichier refusé"
        assert classement.en_cache().de("hp2", "Any%")[0].joueur == "Ludo", "le cache d'avant reste"
        classement.chemin_cache().write_bytes(b"abime")
        assert classement.en_cache() == classement.VIDE


def test_rang():
    lu = classement.lire(_octets({"hp2": {"Any%": [_course("A", "30:00.000"), _course("B", "40:00.000")]}}))
    assert lu is not None
    entrees = lu.de("hp2", "Any%")
    assert [classement.rang(entrees, us) for us in (1, 30 * 60_000_000, 35 * 60_000_000, 50 * 60_000_000)] \
        == [1, 2, 2, 3], "à égalité, derrière"
    assert classement.rang((), 5) == 1
