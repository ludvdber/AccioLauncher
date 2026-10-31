"""La taille du texte de HP1 et HP2 : ses polices regravées à la taille de l'écran.

Demande de Ludo (2026-10-25) : un réglage d'accessibilité qui s'adapte à toutes
les définitions (1080p, 1440p, 4K), automatique par défaut, que la personne peut
agrandir ou réduire.

**Pourquoi regraver, LU dans la source de HP1 (2026-10-22)** : le moteur met
toute l'interface à l'échelle `GUIScale = hauteur / 480`, mais dessine le texte
avec des polices BITMAP de 2001 à leur taille en pixels. À 1440p, les cadres
sont trois fois plus grands, le texte non. Chaque police (`Font`) est une table
de 256 glyphes posés sur 8 pages `Texture` en 256 couleurs, dont deux servent :
0 transparent, l'autre l'encre. Des pages regravées à 3× donnent un texte 3×
plus grand et net, sans toucher au code du jeu. Polices concernées : les
InkFont (HUD, dialogues, folio), `FontHPMenuLarge`/`Medium` (menus) et les
Tahoma des options. VU en jeu à 2,25× le 2026-10-22 (atelier
`polices_bitmap_hp12.py`, dont ce module est le portage).

**Ce qui est écrit, et ce qui ne l'est jamais** : dans un paquet regravé, les
noms, les imports et TOUS les autres objets restent à l'octet et à la même
position (les tableaux paresseux des textures portent une position absolue) ;
les objets regravés sont ajoutés à la fin des données, les tables d'imports et
d'exports réécrites derrière. Le paquet d'origine est gardé dans le cache
(`cache_pour`) avant la première écriture ; un paquet remis par une mise à jour
ou « Vérifier / réparer » est reconnu (son empreinte n'est pas celle que nous
avons écrite) et devient la nouvelle source. Un paquet dont les polices ne
sont plus celles de 2001 (pages de plus de 256 px : regravé par un autre
outil) n'est pas touché.

Glyphes redessinés avec Liberation Serif Bold et Liberation Sans Bold (SIL OFL,
`assets/fonts`), mêmes métriques que Times New Roman et Arial, à la hauteur de
capitale d'origine × le facteur ; les cases sans caractère (codes de contrôle,
0x80-0x9F) sont agrandies au plus proche voisin. Appelé à chaque lancement
après la résolution : rien n'est réécrit tant que le facteur ne change pas.
"""

import hashlib
import json
import logging
import shutil
import struct
from dataclasses import dataclass
from pathlib import Path

from src.core.config import Config, cache_pour
from src.core.ecriture_atomique import ecrire_atomique, ecrire_octets_atomique
from src.core.game_data import GameData

log = logging.getLogger(__name__)

_SIGNATURE = 0x9E2A83C1
_FONTS = Path(__file__).resolve().parents[2] / "assets" / "fonts"
SERIF = _FONTS / "LiberationSerif-Bold.ttf"
SANS = _FONTS / "LiberationSans-Bold.ttf"
SEUIL = 110            # niveau de gris à partir duquel un pixel lissé devient de l'encre
PAGE_ORIGINE = 256     # largeur des pages de 2001 : au-delà, déjà regravé ailleurs
FACTEUR_MAX = 6.0      # pages de 2048 px au plus

_INK = ("TinyInkFont", "SmallInkFont", "MedInkFont", "BigInkFont", "HugeInkFont")
_TAHOMA = ("Tahoma10", "TahomaB10")


@dataclass(frozen=True)
class PaquetPolices:
    chemin: str                 # relatif au dossier du jeu
    polices: tuple[str, ...]
    serif: bool = True


# Relevé le 2026-10-21/22 dans les archives hp1-v1.2 et hp2 (atelier, notes HP1/HP2).
PAQUETS: dict[str, tuple[PaquetPolices, ...]] = {
    "hp1": (PaquetPolices("System/HPBase.u", _INK),
            PaquetPolices("System/UWindow.u", ("FontHPMenuLarge",)),
            PaquetPolices("Textures/UWindowFonts.utx", _TAHOMA, serif=False)),
    "hp2": (PaquetPolices("system/hgame.u", _INK),
            PaquetPolices("system/UWindow.u", ("FontHPMenuMedium", "FontHPMenuLarge")),
            PaquetPolices("Textures/UWindowFonts.utx", _TAHOMA, serif=False)),
}

# Le choix de la personne → multiplicateur de l'automatique. Absent : automatique.
TAILLES: dict[str, float] = {"petit": 0.75, "grand": 1.25, "tres_grand": 1.5}
# L'automatique un peu sous la proportion de 640 × 480 (Ludo, 2026-10-31, menu de
# HP1 en 1440p : « le texte un peu trop gros par défaut ») : ×2,5 au lieu de ×3.
_AUTOMATIQUE = 0.85
ORIGINE = "origine"


def gere(game_id: str) -> bool:
    return game_id in PAQUETS


def facteur(hauteur: int, choix: str) -> float:
    """Le facteur de regravure pour une image de `hauteur` pixels.

    Automatique = hauteur / 480 (l'échelle que le moteur donne à ses cadres,
    la proportion du texte en 640 × 480) × `_AUTOMATIQUE`, un peu en dessous :
    à la proportion exacte, le texte paraissait trop gros. Arrondi au
    quart (deux réglages proches ne réécrivent pas tout), jamais sous 1
    (le texte de 2001) ni au-delà de `FACTEUR_MAX`.
    """
    if choix == ORIGINE or hauteur <= 0:
        return 1.0
    brut = hauteur / 480 * _AUTOMATIQUE * TAILLES.get(choix, 1.0)
    return min(FACTEUR_MAX, max(1.0, round(brut * 4) / 4))


# ---------------------------------------------------------------- paquet Unreal 1

def _lire_compact(d: bytes, i: int) -> tuple[int, int]:
    b = d[i]
    i += 1
    negatif, v, decalage, suite = b & 0x80, b & 0x3F, 6, b & 0x40
    while suite:
        if decalage > 27:
            raise ValueError("entier compact trop long")
        b = d[i]
        i += 1
        v |= (b & 0x7F) << decalage
        decalage += 7
        suite = b & 0x80
    return (-v if negatif else v), i


def _compact(v: int) -> bytes:
    negatif = v < 0
    v = abs(v)
    out = bytearray([(0x80 if negatif else 0) | (v & 0x3F) | (0x40 if v >= 0x40 else 0)])
    v >>= 6
    while v:
        out.append((v & 0x7F) | (0x80 if v >= 0x80 else 0))
        v >>= 7
    return bytes(out)


@dataclass
class _Export:
    cls: int
    sup: int
    outer: int
    nom: int
    drapeaux: int
    taille: int
    position: int


Glyphe = tuple[int, int, int, int]           # u, v, largeur, hauteur


@dataclass(frozen=True)
class _Page:
    debut_props: int
    fin_props: int
    positions: dict[str, int]                # propriété → position ABSOLUE de sa valeur
    largeur: int
    hauteur: int
    data: bytes


class Paquet:
    """Lecteur et écrivain minimal d'un paquet UE1 (versions 68 à 79)."""

    def __init__(self, d: bytes) -> None:
        if len(d) < 56 or struct.unpack_from("<I", d, 0)[0] != _SIGNATURE:
            raise ValueError("pas un paquet Unreal")
        nn, on, ne, oe, ni, oi = struct.unpack_from("<IIIIII", d, 12)
        if not all(0 <= n <= len(d) for n in (nn, ne, ni)):
            raise ValueError("tables plus grandes que le paquet")
        self.d = d
        self.noms: list[str] = []
        i = on
        for _ in range(nn):
            n, i = _lire_compact(d, i)
            if not 0 < n <= 1024:
                raise ValueError("nom illisible")
            self.noms.append(d[i:i + n - 1].decode("latin-1"))
            i += n + 4
        self.imports: list[tuple[int, int, int, int]] = []
        i = oi
        for _ in range(ni):
            paq, i = _lire_compact(d, i)
            cls, i = _lire_compact(d, i)
            outer = struct.unpack_from("<i", d, i)[0]
            nom, i = _lire_compact(d, i + 4)
            self.imports.append((paq, cls, outer, nom))
        self.exports: list[_Export] = []
        i = oe
        for _ in range(ne):
            cls, i = _lire_compact(d, i)
            sup, i = _lire_compact(d, i)
            outer = struct.unpack_from("<i", d, i)[0]
            nom, i = _lire_compact(d, i + 4)
            drapeaux = struct.unpack_from("<I", d, i)[0]
            taille, i = _lire_compact(d, i + 4)
            position = 0
            if taille > 0:
                position, i = _lire_compact(d, i)
            self.exports.append(_Export(cls, sup, outer, nom, drapeaux, taille, position))
        self.oi, self.oe = oi, oe

    def _nom_ref(self, r: int) -> str:
        if r < 0:
            return self.noms[self.imports[-r - 1][3]]
        return self.noms[self.exports[r - 1].nom] if r > 0 else "Class"

    def export(self, nom: str, classe: str) -> int:
        for k, e in enumerate(self.exports, 1):
            if self.noms[e.nom] == nom and self._nom_ref(e.cls) == classe:
                return k
        raise KeyError(f"{nom} ({classe}) absent")

    def proprietes(self, k: int) -> tuple[int, dict[str, int]]:
        """Fin de la liste de propriétés de l'objet `k` (après `None`) et la
        position absolue de la valeur de chaque propriété scalaire."""
        d, e = self.d, self.exports[k - 1]
        i, fin = e.position, e.position + e.taille
        pos: dict[str, int] = {}
        while i < fin:
            n, i = _lire_compact(d, i)
            if self.noms[n] == "None":
                return i, pos
            info = d[i]
            i += 1
            genre, code = info & 15, (info >> 4) & 7
            if genre == 10:
                _, i = _lire_compact(d, i)
            if code < 5:
                taille = (1, 2, 4, 12, 16)[code]
            elif code == 5:
                taille, i = d[i], i + 1
            elif code == 6:
                taille, i = struct.unpack_from("<H", d, i)[0], i + 2
            else:
                taille, i = struct.unpack_from("<I", d, i)[0], i + 4
            if info & 0x80 and genre != 3:
                b = d[i]
                i += 1 if b < 0x80 else (2 if b < 0xC0 else 4)
            if not info & 0x80:
                pos[self.noms[n]] = i
            i += taille
        raise ValueError("propriétés sans fin")

    def police(self, k: int) -> tuple[list[tuple[int, list[Glyphe]]], bytes]:
        """Les pages (texture, glyphes) d'une `Font` et ce qui suit la table, tel quel."""
        d = self.d
        i, _ = self.proprietes(k)
        npages, i = _lire_compact(d, i)
        pages: list[tuple[int, list[Glyphe]]] = []
        for _ in range(npages):
            tex, i = _lire_compact(d, i)
            nc, i = _lire_compact(d, i)
            pages.append((tex, [struct.unpack_from("<iiii", d, i + 16 * c) for c in range(nc)]))
            i += 16 * nc
        e = self.exports[k - 1]
        return pages, d[i:e.position + e.taille]

    def page(self, k: int) -> _Page:
        d, e = self.d, self.exports[k - 1]
        fin_props, pos = self.proprietes(k)
        nm, i = _lire_compact(d, fin_props)
        if nm != 1:
            raise ValueError("page de police à plusieurs niveaux")
        seek = struct.unpack_from("<I", d, i)[0]
        cnt, i = _lire_compact(d, i + 4)
        data = d[i:i + cnt]
        i += cnt
        if seek != i:
            raise ValueError("position paresseuse inattendue")
        us, vs, ub, vb = struct.unpack_from("<IIBB", d, i)
        if i + 10 != e.position + e.taille or us * vs != cnt or (1 << ub) != us or (1 << vb) != vs:
            raise ValueError("page de police incohérente")
        if not {"USize", "VSize", "UClamp", "VClamp", "UBits", "VBits"} <= pos.keys():
            raise ValueError("propriétés de page absentes")
        return _Page(e.position, fin_props, pos, us, vs, data)

    def ecrire(self, remplacements: dict[int, tuple[bytes, list[tuple[int, int]]]]) -> bytes:
        """L'original jusqu'à la fin des données, les objets remplacés derrière,
        puis les tables. `fixups` : (position relative, fin relative) où écrire
        la position absolue de fin des données d'un tableau paresseux."""
        d = self.d
        fin_donnees = min(self.oi, self.oe)
        if fin_donnees < max(e.position + e.taille for e in self.exports):
            raise ValueError("tables avant les données : disposition non prévue")
        out = bytearray(d[:fin_donnees])
        exports = [_Export(**vars(e)) for e in self.exports]
        for k, (blob, fixups) in remplacements.items():
            debut = len(out)
            b = bytearray(blob)
            for rel, fin_rel in fixups:
                struct.pack_into("<I", b, rel, debut + fin_rel)
            out += b
            exports[k - 1].position = debut
            exports[k - 1].taille = len(b)
        oi = len(out)
        for paq, cls, outer, nom in self.imports:
            out += _compact(paq) + _compact(cls) + struct.pack("<i", outer) + _compact(nom)
        oe = len(out)
        for e in exports:
            out += _compact(e.cls) + _compact(e.sup) + struct.pack("<i", e.outer) + _compact(e.nom)
            out += struct.pack("<I", e.drapeaux) + _compact(e.taille)
            if e.taille > 0:
                out += _compact(e.position)
        struct.pack_into("<IIII", out, 20, len(self.exports), oe, len(self.imports), oi)
        return bytes(out)


# ---------------------------------------------------------------- glyphes

def _puissance2(n: int) -> int:
    return 1 << (max(1, n) - 1).bit_length()


def _encre(lignes: list[bytes]) -> tuple[int, int] | None:
    """(première, dernière) ligne contenant de l'encre, ou None."""
    ys = [y for y, ligne in enumerate(lignes) if any(ligne)]
    return (ys[0], ys[-1]) if ys else None


class _Dessinateur:
    """Une police TrueType embarquée, à la taille voulue (Qt, sans police du système)."""

    def __init__(self, ttf: Path) -> None:
        from PyQt6.QtGui import QRawFont
        self._donnees = ttf.read_bytes()
        self._raw = QRawFont(self._donnees, 32.0)
        if not self._raw.isValid():
            raise ValueError(f"police illisible : {ttf.name}")

    def ajuster(self, capitale: float) -> None:
        """La taille en pixels dont le « H » a cette hauteur."""
        meilleur: tuple[float, float] | None = None
        for s in range(4, 400):
            self._raw.setPixelSize(float(s))
            h = self._hauteur_h()
            if meilleur is None or abs(h - capitale) < abs(meilleur[1] - capitale):
                meilleur = (float(s), h)
            if h > capitale + 2:
                break
        if meilleur is not None:
            self._raw.setPixelSize(meilleur[0])

    def _hauteur_h(self) -> float:
        g = self._raw.glyphIndexesForString("H")
        return self._raw.boundingRect(g[0]).height() if g else 0.0

    def glyphe(self, car: str, hauteur: int, base: int, encre: int) -> tuple[int, list[bytes]] | None:
        """(largeur, lignes d'octets 0/encre) du caractère, ligne de base en `base`."""
        from PyQt6.QtCore import QPointF
        from PyQt6.QtGui import QColor, QGlyphRun, QImage, QPainter
        index = self._raw.glyphIndexesForString(car)
        if not index or index[0] == 0:
            return None
        avance = self._raw.advancesForGlyphIndexes(index)[0].x()
        bb = self._raw.boundingRect(index[0])
        dx = max(0.0, -bb.left())
        largeur = max(1, round(avance + dx), int(bb.right() + dx + 0.999))
        image = QImage(largeur, hauteur, QImage.Format.Format_Grayscale8)
        image.fill(0)
        run = QGlyphRun()
        run.setRawFont(self._raw)
        run.setGlyphIndexes(index[:1])
        run.setPositions([QPointF(0, 0)])
        p = QPainter(image)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setPen(QColor(255, 255, 255))
        p.drawGlyphRun(QPointF(dx, base), run)
        p.end()
        table = bytes(encre if v >= SEUIL else 0 for v in range(256))
        ligne = image.bytesPerLine()
        brut = image.constBits()
        if brut is None:
            return None
        donnees: bytes = brut.asstring(image.sizeInBytes())
        return largeur, [donnees[y * ligne:y * ligne + largeur].translate(table) for y in range(hauteur)]


def deja_regravee(paq: Paquet, nom: str) -> bool:
    """Les pages de cette police ne sont plus celles de 2001."""
    pages, _ = paq.police(paq.export(nom, "Font"))
    return any(paq.page(tex).largeur > PAGE_ORIGINE for tex, _ in pages)


def regraver_police(paq: Paquet, nom: str, f: float, dessin: _Dessinateur
                    ) -> dict[int, tuple[bytes, list[tuple[int, int]]]]:
    """Les objets réécrits d'une police (sa `Font` et ses pages) au facteur `f`."""
    k_font = paq.export(nom, "Font")
    pages, queue = paq.police(k_font)
    textures = {tex: paq.page(tex) for tex, _ in pages}
    indices = set().union(*(set(textures[tex].data) for tex, _ in pages)) - {0}
    if len(indices) != 1:
        raise ValueError(f"{nom} : police lissée ({len(indices)} niveaux d'encre)")
    encre = indices.pop()
    origine: list[tuple[int, int, list[bytes]]] = []     # (largeur, hauteur, lignes)
    for tex, glyphes in pages:
        t = textures[tex]
        for (u, v, w, h) in glyphes:
            # Des rectangles d'origine dépassent leur page (importateur d'époque) : transparent.
            origine.append((w, h, [bytes(t.data[(v + y) * t.largeur + u + x]
                                         if v + y < t.hauteur and u + x < t.largeur else 0
                                         for x in range(w)) for y in range(h)]))
    if len(origine) != 256:
        raise ValueError(f"{nom} : {len(origine)} glyphes")
    h0 = origine[0x48][1]
    ligne_h = _encre(origine[0x48][2])
    if ligne_h is None:
        raise ValueError(f"{nom} : pas de H")
    haut, bas = ligne_h
    H = round(h0 * f)
    base = round((bas + 1) * f)
    dessin.ajuster((bas - haut + 1) * f)
    absent = origine[0][2]
    nouveaux: list[tuple[int, list[bytes]]] = []
    for c, (w, h, lignes) in enumerate(origine):
        car = bytes([c]).decode("cp1252", "replace")
        dessine = None
        if not (lignes == absent or c < 32 or 0x80 <= c <= 0x9F or car == "�"):
            if _encre(lignes) is None:
                W = max(1, round(w * f))
                nouveaux.append((W, [bytes(W)] * H))
                continue
            dessine = dessin.glyphe(car, H, base, encre)
        if dessine is None:   # même glyphe, agrandi au plus proche voisin
            W = round(w * f)
            nouveaux.append((W, [bytes(lignes[min(int(y / f), h - 1)][min(int(x / f), w - 1)]
                                       for x in range(W)) if h else bytes(W) for y in range(H)]))
        else:
            nouveaux.append(dessine)
    remplacements: dict[int, tuple[bytes, list[tuple[int, int]]]] = {}
    table: list[tuple[int, list[Glyphe]]] = []
    code = 0
    for tex, glyphes in pages:
        t = textures[tex]
        PW, PH = _puissance2(round(t.largeur * f)), _puissance2(round(t.hauteur * f))
        x, y = 0, 1
        places: list[Glyphe] = []
        for c in range(code, code + len(glyphes)):
            W = nouveaux[c][0]
            if x + W > PW:
                x, y = 0, y + H + 1
            places.append((x, y, W, H))
            x += W + 1
        while y + H > PH:
            PH *= 2
        page = bytearray(PW * PH)
        for c, (px, py, W, _) in zip(range(code, code + len(glyphes)), places, strict=True):
            for yy, ligne in enumerate(nouveaux[c][1]):
                debut = (py + yy) * PW + px
                page[debut:debut + W] = ligne
        table.append((tex, places))
        props = bytearray(paq.d[t.debut_props:t.fin_props])
        for cle, valeur in (("USize", PW), ("VSize", PH), ("UClamp", PW), ("VClamp", PH)):
            struct.pack_into("<i", props, t.positions[cle] - t.debut_props, valeur)
        props[t.positions["UBits"] - t.debut_props] = (PW - 1).bit_length()
        props[t.positions["VBits"] - t.debut_props] = (PH - 1).bit_length()
        blob = bytes(props) + _compact(1)
        fixup = len(blob)
        blob += b"\0\0\0\0" + _compact(len(page))
        fin = len(blob) + len(page)
        blob += bytes(page) + struct.pack("<IIBB", PW, PH, (PW - 1).bit_length(), (PH - 1).bit_length())
        remplacements[tex] = (blob, [(fixup, fin)])
        code += len(glyphes)
    i, _ = paq.proprietes(k_font)
    fb = bytearray(paq.d[paq.exports[k_font - 1].position:i]) + _compact(len(table))
    for tex, places in table:
        fb += _compact(tex) + _compact(len(places))
        for glyphe in places:
            fb += struct.pack("<iiii", *glyphe)
    remplacements[k_font] = (bytes(fb + queue), [])
    return remplacements


def regraver(d: bytes, polices: tuple[str, ...], f: float, ttf: Path) -> bytes | None:
    """Le paquet `d` aux polices regravées ; None si l'une a déjà été regravée ailleurs."""
    paq = Paquet(d)
    if any(deja_regravee(paq, nom) for nom in polices):
        return None
    dessin = _Dessinateur(ttf)
    remplacements: dict[int, tuple[bytes, list[tuple[int, int]]]] = {}
    for nom in polices:
        remplacements.update(regraver_police(paq, nom, f, dessin))
    return paq.ecrire(remplacements)


# ---------------------------------------------------------------- au lancement

def _md5(d: bytes) -> str:
    return hashlib.md5(d, usedforsecurity=False).hexdigest()


def _dossier_cache(game: GameData, config: Config) -> Path:
    return cache_pour(config.install_path) / "texte" / game.id


def appliquer(game: GameData, config: Config, hauteur: int | None) -> float | None:
    """Pose les polices au facteur voulu pour une image de `hauteur` pixels.

    Rend le facteur posé, ou None si rien n'a pu l'être (jeu non concerné,
    hauteur inconnue, paquet absent ou déjà regravé ailleurs). Ne lève
    jamais : un échec laisse le jeu tel quel et se lit dans le journal.
    """
    paquets = PAQUETS.get(game.id)
    if paquets is None or hauteur is None:
        return None
    f = facteur(hauteur, config.taille_texte.get(game.id, ""))
    racine = (config.install_path / game.executable).parent.parent
    cache = _dossier_cache(game, config)
    try:
        etat = json.loads((cache / "etat.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        etat = {}
    if not isinstance(etat, dict):
        etat = {}
    pose: float | None = f
    for spec in paquets:
        try:
            pose = _poser(racine / spec.chemin, cache / spec.chemin, spec, f, etat) and pose
        except (OSError, ValueError, KeyError, struct.error) as exc:
            log.warning("Texte de %s : %s non regravé (%s)", game.id, spec.chemin, exc)
            pose = None
    try:
        cache.mkdir(parents=True, exist_ok=True)
        ecrire_atomique(cache / "etat.json", json.dumps(etat, indent=1))
    except OSError as exc:
        log.warning("Texte de %s : état non enregistré (%s)", game.id, exc)
    return pose


def _poser(cible: Path, source: Path, spec: PaquetPolices, f: float,
           etat: dict[str, object]) -> float | None:
    """Un paquet. `etat[chemin]` = {« source », « sortie », « facteur »} (empreintes)."""
    if not cible.is_file():
        return None
    actuel = cible.read_bytes()
    empreinte = _md5(actuel)
    connu = etat.get(spec.chemin)
    connu = connu if isinstance(connu, dict) else {}
    if empreinte == connu.get("sortie") and connu.get("facteur") == f:
        return f                                        # déjà posé à ce facteur
    if empreinte == connu.get("sortie") and source.is_file():
        d = source.read_bytes()                          # posé à un autre facteur : repartir de la source
        if _md5(d) != connu.get("source"):
            raise ValueError("source gardée altérée")
    else:
        # Paquet d'origine, ou remis par une mise à jour / une réparation : la nouvelle source.
        d = actuel
        if f == 1.0:
            etat[spec.chemin] = {"source": empreinte, "sortie": empreinte, "facteur": f}
            return f
        if any(deja_regravee(Paquet(d), nom) for nom in spec.polices):
            log.info("Texte : %s déjà regravé par un autre outil, laissé tel quel", spec.chemin)
            etat.pop(spec.chemin, None)
            return None
        source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cible, source)
    sortie = d if f == 1.0 else regraver(d, spec.polices, f, SERIF if spec.serif else SANS)
    if sortie is None:
        return None
    # Temporaire effacé sur un échec : un paquet de plusieurs Mo restait sinon
    # à côté de l'original (audit du 2026-10-29).
    ecrire_octets_atomique(cible, sortie, suffixe=".accio")
    etat[spec.chemin] = {"source": _md5(d), "sortie": _md5(sortie), "facteur": f}
    log.info("Texte : %s posé à %.2f×", spec.chemin, f)
    return f
