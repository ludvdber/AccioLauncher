"""Les images des jeux EA (HP4 à HP6) : archives « BIGF », blocs « SHPI », DXT.

Qt ne lit pas le DXT (vérifié : rien de tel dans `QImageReader.supportedImageFormats`),
d'où ce petit décodeur, en Python pur : les images du folio sont peu nombreuses,
et un niveau de mip réduit (128 × 128) suffit à une vignette.

Un bloc SHPI (relevé le 2026-10-17 sur HP5 et HP6, notes « Format des images ») :

    0x00  « SHPI », taille, nombre d'images, « G354 »
    0x10  par image : nom court (4 octets), décalage de son en-tête depuis le bloc
    en-tête d'image : code (octet bas, bit 7 ignoré), saut vers le bloc attaché
          suivant (24 bits), largeur, hauteur (16 bits), …, mips (4 bits hauts
          de l'octet 15), puis les pixels, niveau 0 d'abord
    blocs attachés : même chaînage ; 0x70 porte le NOM COMPLET de l'image
          (« PT_BDG_POT_CLUBSTAR_CM »), 0x2A la palette d'une image 0x7B

Codes lus ici : 0x60 = DXT1, 0x62 = DXT5. Les pixels rendus sont en B, V, R, A,
l'ordre de `QImage.Format_ARGB32` en mémoire.
"""

from __future__ import annotations

import struct
from pathlib import Path

DXT1, DXT5 = 0x60, 0x62
_NOM = 0x70


def entree_big(chemin: Path, nom: str) -> bytes:
    """Le contenu d'une entrée d'une archive EA « BIGF » ; b"" si absente."""
    with open(chemin, "rb") as f:
        tete = f.read(16)
        if tete[:4] not in (b"BIGF", b"BIG4"):
            return b""
        nombre, taille_tete = struct.unpack(">II", tete[8:16])
        brut = f.read(max(0, taille_tete - 16))
        p, cible = 0, nom.lower().encode("latin-1")
        for _ in range(nombre):
            if p + 8 > len(brut):
                break
            debut, taille = struct.unpack_from(">II", brut, p)
            fin = brut.find(b"\0", p + 8)
            if fin < 0:
                break
            if brut[p + 8:fin].lower() == cible:
                f.seek(debut)
                return f.read(taille)
            p = fin + 1
    return b""


def images_nommees(flux: bytes) -> dict[str, int]:
    """Nom complet de chaque image des blocs SHPI du flux → position de son en-tête."""
    trouvees: dict[str, int] = {}
    p = flux.find(b"SHPI")
    while 0 <= p <= len(flux) - 16:
        nombre = struct.unpack_from("<I", flux, p + 8)[0]
        if 0 < nombre < 512 and p + 16 + 8 * nombre <= len(flux):
            for i in range(nombre):
                q = p + struct.unpack_from("<I", flux, p + 20 + 8 * i)[0]
                nom = _nom(flux, q)
                if nom:
                    trouvees.setdefault(nom, q)
        p = flux.find(b"SHPI", p + 4)
    return trouvees


def _nom(flux: bytes, q: int) -> str | None:
    """Le nom porté par le bloc attaché 0x70 de l'image dont l'en-tête est en q."""
    r = q
    for _ in range(8):
        if r + 16 > len(flux):
            return None
        saut = int.from_bytes(flux[r + 1:r + 4], "little")
        if r != q and flux[r] & 0x7F == _NOM:
            fin = flux.find(b"\0", r + 4, r + 260)
            if fin < 0:
                return None
            return flux[r + 4:fin].decode("latin-1")
        if not saut:
            return None
        r += saut
    return None


def image(flux: bytes, q: int, cote_max: int = 128) -> tuple[int, int, bytes] | None:
    """L'image DXT dont l'en-tête est en q, au premier niveau de mip qui tient
    dans `cote_max` : (largeur, hauteur, pixels B V R A), ou None."""
    if q + 16 > len(flux):
        return None
    code = flux[q] & 0x7F
    if code not in (DXT1, DXT5):
        return None
    largeur, hauteur = struct.unpack_from("<HH", flux, q + 4)
    mips = flux[q + 15] >> 4
    if not (4 <= largeur <= 4096 and 4 <= hauteur <= 4096):
        return None
    pas = 8 if code == DXT1 else 16
    debut = q + 16
    for _ in range(mips):
        if max(largeur, hauteur) <= cote_max or min(largeur, hauteur) <= 4:
            break
        debut += (largeur // 4) * (hauteur // 4) * pas
        largeur, hauteur = largeur // 2, hauteur // 2
    taille = (largeur // 4) * (hauteur // 4) * pas
    if debut + taille > len(flux):
        return None
    donnees = flux[debut:debut + taille]
    pixels = dxt1(donnees, largeur, hauteur) if code == DXT1 else dxt5(donnees, largeur, hauteur)
    return largeur, hauteur, pixels


def _bvr(c: int) -> tuple[int, int, int]:
    r, v, b = (c >> 11) & 31, (c >> 5) & 63, c & 31
    return (b << 3) | (b >> 2), (v << 2) | (v >> 4), (r << 3) | (r >> 2)


def _couleurs(c0: int, c1: int, quatre: bool) -> list[bytes]:
    """Les quatre teintes d'un bloc, en B V R A."""
    a, b = _bvr(c0), _bvr(c1)
    if quatre:
        c = tuple((2 * x + y) // 3 for x, y in zip(a, b, strict=True))
        d = tuple((x + 2 * y) // 3 for x, y in zip(a, b, strict=True))
        return [bytes((*a, 255)), bytes((*b, 255)), bytes((*c, 255)), bytes((*d, 255))]
    m = tuple((x + y) // 2 for x, y in zip(a, b, strict=True))
    return [bytes((*a, 255)), bytes((*b, 255)), bytes((*m, 255)), bytes(4)]


def dxt1(donnees: bytes, largeur: int, hauteur: int) -> bytes:
    """Pixels B V R A d'une image DXT1 (largeur et hauteur multiples de 4)."""
    sortie = bytearray(largeur * hauteur * 4)
    k = 0
    for by in range(0, hauteur, 4):
        for bx in range(0, largeur, 4):
            c0, c1, indices = struct.unpack_from("<HHI", donnees, k)
            k += 8
            t = _couleurs(c0, c1, c0 > c1)
            ligne = (by * largeur + bx) * 4
            for _ in range(4):
                r = indices & 0xFF     # une rangée de 4 pixels : 2 bits chacun
                sortie[ligne:ligne + 16] = t[r & 3] + t[(r >> 2) & 3] + t[(r >> 4) & 3] + t[r >> 6]
                indices >>= 8
                ligne += largeur * 4
    return bytes(sortie)


def _alphas(a0: int, a1: int) -> list[int]:
    if a0 > a1:
        return [a0, a1] + [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
    return [a0, a1] + [((5 - i) * a0 + i * a1) // 5 for i in range(1, 5)] + [0, 255]


def dxt5(donnees: bytes, largeur: int, hauteur: int) -> bytes:
    """Pixels B V R A d'une image DXT5 (largeur et hauteur multiples de 4)."""
    sortie = bytearray(largeur * hauteur * 4)
    k = 0
    for by in range(0, hauteur, 4):
        for bx in range(0, largeur, 4):
            alphas = _alphas(donnees[k], donnees[k + 1])
            ia = int.from_bytes(donnees[k + 2:k + 8], "little")
            c0, c1, indices = struct.unpack_from("<HHI", donnees, k + 8)
            k += 16
            teintes = _couleurs(c0, c1, True)
            for y in range(4):
                ligne = ((by + y) * largeur + bx) * 4
                for x in range(4):
                    n = 4 * y + x
                    o = ligne + 4 * x
                    sortie[o:o + 3] = teintes[(indices >> (2 * n)) & 3][:3]
                    sortie[o + 3] = alphas[(ia >> (3 * n)) & 7]
    return bytes(sortie)
