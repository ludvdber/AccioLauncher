"""La taille du texte de HP1/HP2 : polices bitmap regravées à la hauteur de l'image.

Le paquet est FABRIQUÉ (aucun fichier du jeu dans le dépôt) : une `Font` de 256
glyphes sur une page de 256 × 64, comme celles de 2001, et un objet voisin qui
ne doit pas bouger d'un octet. Le rendu des glyphes passe par Qt (`qapp`).
"""
import struct
from types import SimpleNamespace

import pytest

from src.core import texte_ue1 as t
from src.core.config import Config

NOMS = ["None", "USize", "VSize", "UClamp", "VClamp", "UBits", "VBits", "Core", "Engine",
        "Package", "Class", "Texture", "Font", "Page0", "MaPolice", "Voisin"]
N = {nom: i for i, nom in enumerate(NOMS)}
CELLULE = 8              # glyphes de 8 × 8, 32 par rangée : page de 256 × 64


def _compact(v):
    return t._compact(v)


def _texture(largeur, hauteur, data, debut):
    """Blob d'une page ; `debut` = position absolue du blob dans le fichier."""
    props = b""
    for nom, val in (("USize", largeur), ("VSize", hauteur), ("UClamp", largeur), ("VClamp", hauteur)):
        props += _compact(N[nom]) + bytes([0x22]) + struct.pack("<i", val)
    for nom, val in (("UBits", (largeur - 1).bit_length()), ("VBits", (hauteur - 1).bit_length())):
        props += _compact(N[nom]) + bytes([0x01]) + bytes([val])
    props += _compact(N["None"])
    tete = props + _compact(1)
    fin = debut + len(tete) + 4 + len(_compact(len(data))) + len(data)
    return tete + struct.pack("<I", fin) + _compact(len(data)) + data + struct.pack(
        "<IIBB", largeur, hauteur, (largeur - 1).bit_length(), (hauteur - 1).bit_length())


def fabriquer():
    """Un paquet UE1 : la page, la police, un voisin. Le « H » a de l'encre."""
    page = bytearray(256 * 64)
    glyphes = []
    for c in range(256):
        u, v = (c % 32) * CELLULE, (c // 32) * CELLULE
        glyphes.append((u, v, CELLULE - 2, CELLULE))
        if c in (0x48, 0x41):            # H et A : deux barres et une traverse
            for y in range(1, 7):
                page[(v + y) * 256 + u + 1] = page[(v + y) * 256 + u + 4] = 1
            for x in range(1, 5):
                page[(v + 4) * 256 + u + x] = 1
    entete = 56 + 8
    noms = b"".join(_compact(len(n) + 1) + n.encode() + b"\0" + struct.pack("<I", 0) for n in NOMS)
    pos_tex = entete + len(noms)
    tex = _texture(256, 64, bytes(page), pos_tex)
    font = _compact(N["None"]) + _compact(1) + _compact(1) + _compact(256)
    font += b"".join(struct.pack("<iiii", *g) for g in glyphes)
    font += struct.pack("<i", 0) + _compact(0) + struct.pack("<i", 0)
    voisin = _compact(N["None"]) + b"donnees du voisin, a garder telles quelles"
    pos_font = pos_tex + len(tex)
    pos_voisin = pos_font + len(font)
    imports = [(N["Core"], N["Package"], 0, N["Engine"]),
               (N["Core"], N["Class"], -1, N["Texture"]),
               (N["Core"], N["Class"], -1, N["Font"])]
    exports = [(-2, 0, 0, N["Page0"], 0, len(tex), pos_tex),
               (-3, 0, 0, N["MaPolice"], 0, len(font), pos_font),
               (-2, 0, 0, N["Voisin"], 0, len(voisin), pos_voisin)]
    pos_imports = pos_voisin + len(voisin)
    bloc_imports = b"".join(_compact(a) + _compact(b) + struct.pack("<i", c) + _compact(d)
                            for a, b, c, d in imports)
    pos_exports = pos_imports + len(bloc_imports)
    bloc_exports = b"".join(_compact(c) + _compact(s) + struct.pack("<i", o) + _compact(n)
                            + struct.pack("<I", f) + _compact(ta) + _compact(p)
                            for c, s, o, n, f, ta, p in exports)
    tete = struct.pack("<IHHIIIIIII", 0x9E2A83C1, 69, 0, 0, len(NOMS), entete,
                       len(exports), pos_exports, len(imports), pos_imports)
    tete += b"\x11" * 16 + struct.pack("<I", 1) + struct.pack("<II", len(exports), len(NOMS))
    return tete + noms + tex + font + voisin + bloc_imports + bloc_exports


class TestFacteur:
    @pytest.mark.parametrize(("hauteur", "choix", "attendu"), [
        # L'automatique à 0,85 de la proportion de 640 × 480 (Ludo, 2026-10-31).
        (1080, "", 2.0), (1440, "", 2.5), (2160, "", 3.75), (1440, "petit", 2.0),
        (1440, "grand", 3.25), (1440, "tres_grand", 3.75), (1440, "origine", 1.0),
        (2880, "tres_grand", t.FACTEUR_MAX), (480, "petit", 1.0), (0, "", 1.0),
        (1200, "", 2.0), (1440, "inconnu", 2.5)])
    def test_facteur(self, hauteur, choix, attendu):
        assert t.facteur(hauteur, choix) == attendu


class TestRegravure:
    def test_paquet_relu_et_voisin_intact(self, qapp):
        d = fabriquer()
        avant = t.Paquet(d)
        nouveau = t.regraver(d, ("MaPolice",), 2.0, t.SERIF)
        apres = t.Paquet(nouveau)
        assert apres.noms == avant.noms and apres.imports == avant.imports
        voisin_a, voisin_b = avant.exports[2], apres.exports[2]
        assert (voisin_a.position, voisin_a.taille) == (voisin_b.position, voisin_b.taille)
        assert nouveau[voisin_b.position:voisin_b.position + voisin_b.taille] == \
            d[voisin_a.position:voisin_a.position + voisin_a.taille]
        # Seules les positions des tables changent dans l'en-tête ; le reste est à l'octet.
        assert nouveau[36:voisin_a.position] == d[36:voisin_a.position]
        pages, queue = apres.police(apres.export("MaPolice", "Font"))
        assert queue == avant.police(avant.export("MaPolice", "Font"))[1]
        page = apres.page(pages[0][0])
        assert page.largeur == 512 and page.hauteur >= 128
        assert all(u + w <= page.largeur and v + h <= page.hauteur for u, v, w, h in pages[0][1])
        assert len(pages[0][1]) == 256 and {h for *_, h in pages[0][1]} == {16}
        u, v, w, h = pages[0][1][0x48]
        assert any(page.data[(v + y) * page.largeur + u + x] for y in range(h) for x in range(w))
        assert set(page.data) <= {0, 1}

    def test_deja_regravee_laissee(self, qapp):
        nouveau = t.regraver(fabriquer(), ("MaPolice",), 2.0, t.SERIF)
        assert t.deja_regravee(t.Paquet(nouveau), "MaPolice")
        assert t.regraver(nouveau, ("MaPolice",), 2.0, t.SERIF) is None

    def test_paquet_qui_n_en_est_pas_un(self):
        with pytest.raises(ValueError):
            t.Paquet(b"\0" * 100)


@pytest.fixture
def jeu(tmp_path, monkeypatch):
    monkeypatch.setitem(t.PAQUETS, "hp1", (t.PaquetPolices("System/HPBase.u", ("MaPolice",)),))
    config = Config(install_path=tmp_path / "Jeux")
    game = SimpleNamespace(id="hp1", executable="HP1/System/HP.exe")
    paquet = tmp_path / "Jeux" / "HP1" / "System" / "HPBase.u"
    paquet.parent.mkdir(parents=True)
    original = fabriquer()
    paquet.write_bytes(original)
    return game, config, paquet, original


class TestAuLancement:
    # 1700 px : ×3 avec l'automatique à 0,85 (1700 / 480 × 0,85 = 3,01).
    def test_pose_puis_ne_reecrit_pas(self, qapp, jeu):
        game, config, paquet, original = jeu
        assert t.appliquer(game, config, 1700) == 3.0
        pose = paquet.read_bytes()
        assert pose != original and t.Paquet(pose).page(1).largeur == 1024
        garde = config.install_path / "_Launcher" / "cache" / "texte" / "hp1" / "System" / "HPBase.u"
        assert garde.read_bytes() == original
        avant = paquet.stat().st_mtime_ns
        assert t.appliquer(game, config, 1700) == 3.0
        assert paquet.stat().st_mtime_ns == avant

    def test_autre_facteur_repart_de_l_original(self, qapp, jeu):
        game, config, paquet, original = jeu
        t.appliquer(game, config, 1700)
        assert t.appliquer(game, config, 1080) == 2.0
        assert paquet.read_bytes() == t.regraver(original, ("MaPolice",), 2.0, t.SERIF)

    def test_origine_remet_le_paquet(self, qapp, jeu):
        game, config, paquet, original = jeu
        t.appliquer(game, config, 1700)
        config.taille_texte["hp1"] = t.ORIGINE
        assert t.appliquer(game, config, 1440) == 1.0
        assert paquet.read_bytes() == original

    def test_paquet_remis_par_une_mise_a_jour(self, qapp, jeu):
        game, config, paquet, original = jeu
        t.appliquer(game, config, 1700)
        nouvelle = original.replace(b"donnees du voisin", b"DONNEES DU VOISIN")
        paquet.write_bytes(nouvelle)              # l'archive suivante, autre contenu
        assert t.appliquer(game, config, 1700) == 3.0
        garde = config.install_path / "_Launcher" / "cache" / "texte" / "hp1" / "System" / "HPBase.u"
        assert garde.read_bytes() == nouvelle
        assert b"DONNEES DU VOISIN" in paquet.read_bytes()

    def test_regrave_ailleurs_laisse_tel_quel(self, qapp, jeu):
        game, config, paquet, original = jeu
        autre = t.regraver(original, ("MaPolice",), 2.25, t.SERIF)
        paquet.write_bytes(autre)                 # l'atelier est passé avant
        assert t.appliquer(game, config, 1440) is None
        assert paquet.read_bytes() == autre

    def test_sans_hauteur_ou_autre_jeu(self, jeu):
        game, config, paquet, original = jeu
        assert t.appliquer(game, config, None) is None
        assert t.appliquer(SimpleNamespace(id="hp3", executable="HP3/system/x.exe"), config, 1440) is None
        assert paquet.read_bytes() == original

    def test_paquet_absent(self, qapp, jeu):
        game, config, paquet, _ = jeu
        paquet.unlink()
        assert t.appliquer(game, config, 1440) is None

    def test_paquet_illisible_ne_leve_pas(self, qapp, jeu):
        game, config, paquet, _ = jeu
        paquet.write_bytes(b"pas un paquet" * 10)
        assert t.appliquer(game, config, 1440) is None


def test_config_garde_la_taille(tmp_path, monkeypatch):
    from src.core import config as module
    monkeypatch.setattr(module, "CONFIG_FILE_PATH", tmp_path / "config.json")
    c = Config(install_path=tmp_path)
    c.taille_texte["hp2"] = "grand"
    c.save()
    assert Config.load().taille_texte == {"hp2": "grand"}


def test_polices_embarquees():
    assert t.SERIF.is_file() and t.SANS.is_file()
    assert (t.SERIF.parent / "Liberation-OFL.txt").is_file()
