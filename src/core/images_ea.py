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


# 5 et 6 bits → 8 bits, une fois pour toutes. Décodeur revu le 2026-10-31 : les
# textures des personnages de HP5-HP6 (512 × 512) passaient 85 % de leur
# chargement ici ; mêmes octets, 1,8 fois plus vite.
_B5 = tuple((v << 3) | (v >> 2) for v in range(32))
_B6 = tuple((v << 2) | (v >> 4) for v in range(64))
# Les quatre teintes d'une paire de couleurs : les blocs voisins les répètent.
_TEINTES: dict[int, list[bytes]] = {}
# Plafonné et vidé quand il est plein : 65 536 entrées pesaient ~24 Mo gardés à vie.
_TEINTES_MAX = 4096


def _bvr(c: int) -> tuple[int, int, int]:
    return _B5[c & 31], _B6[(c >> 5) & 63], _B5[c >> 11]


def _couleurs(c0: int, c1: int, quatre: bool) -> list[bytes]:
    """Les quatre teintes d'un bloc, en B V R A."""
    cle = (c0 << 17) | (c1 << 1) | quatre
    t = _TEINTES.get(cle)
    if t is not None:
        return t
    b0, v0, r0 = _B5[c0 & 31], _B6[(c0 >> 5) & 63], _B5[c0 >> 11]
    b1, v1, r1 = _B5[c1 & 31], _B6[(c1 >> 5) & 63], _B5[c1 >> 11]
    if quatre:
        t = [bytes((b0, v0, r0, 255)), bytes((b1, v1, r1, 255)),
             bytes(((2 * b0 + b1) // 3, (2 * v0 + v1) // 3, (2 * r0 + r1) // 3, 255)),
             bytes(((b0 + 2 * b1) // 3, (v0 + 2 * v1) // 3, (r0 + 2 * r1) // 3, 255))]
    else:
        t = [bytes((b0, v0, r0, 255)), bytes((b1, v1, r1, 255)),
             bytes(((b0 + b1) // 2, (v0 + v1) // 2, (r0 + r1) // 2, 255)), bytes(4)]
    if len(_TEINTES) >= _TEINTES_MAX:
        _TEINTES.clear()
    _TEINTES[cle] = t
    return t


def _rangees(sortie: bytearray, ligne: int, pas: int, t: list[bytes], indices: int) -> None:
    """Les quatre rangées de quatre pixels d'un bloc (2 bits par pixel)."""
    for _ in range(4):
        sortie[ligne:ligne + 16] = b"".join((t[indices & 3], t[(indices >> 2) & 3],
                                             t[(indices >> 4) & 3], t[(indices >> 6) & 3]))
        indices >>= 8
        ligne += pas


def dxt1(donnees: bytes, largeur: int, hauteur: int) -> bytes:
    """Pixels B V R A d'une image DXT1 (largeur et hauteur multiples de 4)."""
    sortie = bytearray(largeur * hauteur * 4)
    pas = largeur * 4
    blocs = struct.iter_unpack("<HHI", donnees[:largeur * hauteur // 2])
    for by in range(0, hauteur, 4):
        base = by * pas
        for bx in range(0, pas, 16):
            c0, c1, indices = next(blocs)
            _rangees(sortie, base + bx, pas, _couleurs(c0, c1, c0 > c1), indices)
    return bytes(sortie)


def _alphas(a0: int, a1: int) -> list[int]:
    if a0 > a1:
        return [a0, a1] + [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
    return [a0, a1] + [((5 - i) * a0 + i * a1) // 5 for i in range(1, 5)] + [0, 255]


def dxt5(donnees: bytes, largeur: int, hauteur: int) -> bytes:
    """Pixels B V R A d'une image DXT5 (largeur et hauteur multiples de 4)."""
    sortie = bytearray(largeur * hauteur * 4)
    pas = largeur * 4
    k = 0
    for by in range(0, hauteur, 4):
        base = by * pas
        for bx in range(0, pas, 16):
            a0, a1 = donnees[k], donnees[k + 1]
            ia = int.from_bytes(donnees[k + 2:k + 8], "little")
            c0, c1, indices = struct.unpack_from("<HHI", donnees, k + 8)
            k += 16
            # Les couleurs d'abord, opaques ; l'alpha ensuite, seulement si le
            # bloc n'est pas tout opaque (le cas courant).
            debut = base + bx
            _rangees(sortie, debut, pas, _couleurs(c0, c1, True), indices)
            if a0 == 255 and ia == 0:
                continue
            alphas = _alphas(a0, a1)
            for n in range(16):
                sortie[debut + (n >> 2) * pas + 4 * (n & 3) + 3] = alphas[(ia >> (3 * n)) & 7]
    return bytes(sortie)
