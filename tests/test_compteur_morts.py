"""Le compteur de morts : le format exact que `FormatLine` (source/onelife.h du correctif) écrit."""
from src.core import compteur_morts as cm


def _ligne(evenement: str, carte: str = "Lev_Tut1", detail: str = "baseHarry", quand: str = "2026-11-08T14:03:09") -> str:
    return f"{quand}\t{evenement}\t{carte}\t{detail}\n"


class TestAnalyser:
    def test_compte_chaque_evenement(self):
        texte = _ligne("mort") + _ligne("mort", "Hub1") + _ligne("chute_balai", "Quidditch") + _ligne("une_vie_fin", "", "812")
        r = cm.analyser(texte)
        assert (r.morts, r.chutes_balai, r.fins_une_vie) == (2, 1, 1)

    def test_cartes_les_plus_meurtrieres_d_abord(self):
        texte = _ligne("mort", "B") + _ligne("mort", "A") + _ligne("mort", "C") + _ligne("mort", "C")
        assert cm.analyser(texte).par_carte == (("C", 2), ("A", 1), ("B", 1))

    def test_une_chute_n_entre_pas_dans_les_cartes(self):
        assert cm.analyser(_ligne("chute_balai", "Quidditch")).par_carte == ()

    def test_mort_sans_carte_comptee_sans_carte(self):
        r = cm.analyser(_ligne("mort", ""))
        assert (r.morts, r.par_carte) == (1, ())

    def test_lignes_coupees_ignorees(self):
        texte = _ligne("mort") + "2026-11-08T14:03" + "\n" + "pas une date\tmort\tX\tY\n"
        assert cm.analyser(texte).morts == 1


class TestLire:
    def test_absent_vide(self, tmp_path):
        assert cm.lire(tmp_path) == cm.Releve()

    def test_lit_le_fichier_de_la_dll(self, tmp_path):
        (tmp_path / cm.FICHIER).write_bytes(_ligne("mort", "Défi").encode("utf-8"))
        assert cm.lire(tmp_path).par_carte == (("Défi", 1),)

    def test_gros_fichier_premiere_ligne_coupee_ecartee(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cm, "_OCTETS_MAX", 60)
        (tmp_path / cm.FICHIER).write_bytes((_ligne("mort", "Ancienne") * 3 + _ligne("mort", "Recente")).encode("utf-8"))
        r = cm.lire(tmp_path)
        assert r.morts == 1
        assert r.par_carte == (("Recente", 1),)
