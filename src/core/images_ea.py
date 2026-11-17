"""Les images des jeux EA (HP4 à HP6) : archives « BIGF », blocs « SHPI », DXT.

Qt ne lit pas le DXT (vérifié : rien de tel dans `QImageReader.supportedImageFormats`),
d'où ce décodeur, sans dépendance. Il sert aux images du folio (512 px chez
HP4), aux textures des modèles 3D (512 px) et aux textures UE2 (jusqu'à
2048 px) ; il décode tous les blocs d'une image à la fois (plus bas).

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
from functools import lru_cache
from pathlib import Path

from src.core.signature import fiable

DXT1, DXT5 = 0x60, 0x62
_NOM = 0x70


def entree_big(chemin: Path, nom: str) -> bytes:
    """Le contenu d'une entrée d'une archive EA « BIGF » ; b"" si absente.

    L'index de l'archive (des milliers d'entrées dans `data.big` de 0,7 à 1,6 Go)
    se lit UNE fois tant que le fichier ne change pas : chaque image du folio de
    HP4 et HP5 le relisait et le réanalysait (data.big ×15, data2/3/4.big ×17 sur
    un parcours, banc de rapidité du 2026-11-13). Ensuite, une entrée = un
    déplacement et une lecture de SES octets.
    """
    signature = fiable(chemin.stat())     # une archive qui vient d'être écrite se relit
    index = _lire_index(str(chemin)) if signature is None else _index_big(str(chemin), *signature)
    place = index.get(nom.lower().encode("latin-1"))
    if place is None:
        return b""
    with open(chemin, "rb") as f:
        f.seek(place[0])
        return f.read(place[1])


@lru_cache(maxsize=8)
def _index_big(chemin: str, _mtime: int, _taille: int) -> dict[bytes, tuple[int, int]]:
    return _lire_index(chemin)


def _lire_index(chemin: str) -> dict[bytes, tuple[int, int]]:
    """Nom en minuscules → (début, taille) de chaque entrée ; vide si ce n'est pas une archive BIG."""
    index: dict[bytes, tuple[int, int]] = {}
    with open(chemin, "rb") as f:
        tete = f.read(16)
        if tete[:4] not in (b"BIGF", b"BIG4"):
            return index
        nombre, taille_tete = struct.unpack(">II", tete[8:16])
        brut = f.read(max(0, taille_tete - 16))
    p = 0
    for _ in range(nombre):
        if p + 8 > len(brut):
            break
        debut, taille = struct.unpack_from(">II", brut, p)
        fin = brut.find(b"\0", p + 8)
        if fin < 0:
            break
        index.setdefault(brut[p + 8:fin].lower(), (debut, taille))
        p = fin + 1
    return index


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
    dans `cote_max` : (largeur, hauteur, pixels B V R A), ou None.

    Les côtés sont des multiples de 4 (blocs DXT), au niveau rendu aussi : un
    côté de 6 faisait lever StopIteration ou IndexError au décodage, que les
    appelants n'attrapent pas (audit du 2026-11-02).
    """
    if q + 16 > len(flux):
        return None
    code = flux[q] & 0x7F
    if code not in (DXT1, DXT5):
        return None
    largeur, hauteur = struct.unpack_from("<HH", flux, q + 4)
    mips = flux[q + 15] >> 4
    if not (4 <= largeur <= 4096 and 4 <= hauteur <= 4096) or largeur % 4 or hauteur % 4:
        return None
    pas = 8 if code == DXT1 else 16
    debut = q + 16
    for _ in range(mips):
        if max(largeur, hauteur) <= cote_max or (largeur // 2) % 4 or (hauteur // 2) % 4:
            break
        debut += (largeur // 4) * (hauteur // 4) * pas
        largeur, hauteur = largeur // 2, hauteur // 2
    taille = (largeur // 4) * (hauteur // 4) * pas
    if debut + taille > len(flux):
        return None
    donnees = flux[debut:debut + taille]
    pixels = dxt1(donnees, largeur, hauteur) if code == DXT1 else dxt5(donnees, largeur, hauteur)
    return largeur, hauteur, pixels


# ── Le décodage DXT, tous les blocs à la fois ──
#
# Un bloc = deux couleurs 5-6-5, deux teintes déduites, 16 indices de 2 bits (et, en DXT5, deux
# alphas, six déduits, 16 indices de 3 bits). Décodé bloc par bloc en Python, c'était le gros de
# l'ouverture des Personnages : 2,4 s des 3,4 s de HP3, 1,2 s des 2,2 s de HP5 (2026-11-16, Ludo :
# « plus d'une seconde d'attente c'est trop long »). Ici aucune boucle ne parcourt les blocs :
# chaque champ de TOUS les blocs se prend d'une tranche à pas (`donnees[0::8]`), les tables de 256
# octets passent par `bytes.translate`, et l'arithmétique (interpolations, comparaisons, choix de
# la teinte) se fait sur des entiers longs dont chaque octet, ou chaque voie de 32 bits, est un
# bloc. Tout cela tourne en C ; les octets rendus sont les mêmes qu'avant, à l'octet près
# (`test_images_ea.TestDecodeurEnBloc`).

_B5 = tuple((v << 3) | (v >> 2) for v in range(32))
# Les deux octets d'une couleur 5-6-5 (bas, haut) vers ses canaux sur 8 bits. Le vert est à cheval
# sur les deux : ses morceaux ne se recouvrent pas, un OU les réunit.
_BLEU = bytes(_B5[o & 31] for o in range(256))
_ROUGE = bytes(_B5[o >> 3] for o in range(256))
_VERT_HAUT = bytes(((o & 7) << 5) | ((o & 7) >> 1) for o in range(256))
_VERT_BAS = bytes((o >> 5) << 2 for o in range(256))
# 255 là où le pixel p (2 bits) de l'octet d'indices vaut k ; là où l'indice d'alpha (3 bits) vaut j.
_EGAL2 = tuple(tuple(bytes(255 if (o >> 2 * p) & 3 == k else 0 for o in range(256)) for k in range(4))
               for p in range(4))
_EGAL3 = tuple(bytes(255 if o & 7 == j else 0 for o in range(256)) for j in range(8))
# x // 3, x // 7 et x // 5 par une multiplication et un décalage, exacts jusqu'à 3, 7 et 5 × 255.
_TIERS, _SEPTIEME, _CINQUIEME = (683, 11), (9363, 16), (13108, 16)

Teintes = tuple[int, int, int, int]      # les quatre teintes d'un canal, un octet par bloc


def _voies(octets: bytes) -> int:
    """Un octet par voie de 32 bits : la place des retenues d'une somme ou d'un produit."""
    large = bytearray(4 * len(octets))
    large[0::4] = octets
    return int.from_bytes(large, "little")


def _entier(voies: int, n: int) -> int:
    """L'octet bas de chacune des n voies, en entier d'un octet par bloc."""
    return int.from_bytes(voies.to_bytes(4 * n, "little")[0::4], "little")


def _plus_grand(v0: int, v1: int, bit: int, n: int) -> int:
    """255 pour chaque bloc où la valeur de v0 (moins de `bit` bits) dépasse celle de v1."""
    un = int.from_bytes(b"\x01\0\0\0" * n, "little")
    return _entier(((((v0 | (un << bit)) - v1 - un) >> bit) & un) * 255, n)


def _vert(bas: bytes, haut: bytes) -> bytes:
    vert = int.from_bytes(haut.translate(_VERT_HAUT), "little") | int.from_bytes(bas.translate(_VERT_BAS), "little")
    return vert.to_bytes(len(bas), "little")


def _teintes(couleurs: bytes, pas: int, n: int, dxt1: bool) -> tuple[list[Teintes], int]:
    """Les teintes de chaque canal (B, V, R) et le masque des blocs à QUATRE teintes : tous en
    DXT5 ; en DXT1, ceux où c0 > c1 (les autres ont une moyenne et un pixel transparent)."""
    bas0, haut0, bas1, haut1 = (couleurs[k::pas] for k in range(4))
    plein = (1 << (8 * n)) - 1
    quatre = plein
    if dxt1:
        quatre = _plus_grand(_voies(bas0) | (_voies(haut0) << 8), _voies(bas1) | (_voies(haut1) << 8), 16, n)
    canaux: list[Teintes] = []
    for e0, e1 in ((bas0.translate(_BLEU), bas1.translate(_BLEU)), (_vert(bas0, haut0), _vert(bas1, haut1)),
                   (haut0.translate(_ROUGE), haut1.translate(_ROUGE))):
        v0, v1 = _voies(e0), _voies(e1)
        t2 = _entier(((2 * v0 + v1) * _TIERS[0]) >> _TIERS[1], n)
        t3 = _entier(((v0 + 2 * v1) * _TIERS[0]) >> _TIERS[1], n)
        if quatre != plein:
            t2 = (t2 & quatre) | (_entier((v0 + v1) >> 1, n) & (plein ^ quatre))
            t3 &= quatre
        canaux.append((int.from_bytes(e0, "little"), int.from_bytes(e1, "little"), t2, t3))
    return canaux, quatre


def _decoder(donnees: bytes, largeur: int, hauteur: int, dxt1: bool) -> bytes:
    n = (largeur // 4) * (hauteur // 4)
    pas = 8 if dxt1 else 16
    if len(donnees) < n * pas:
        raise ValueError("image DXT tronquée")
    donnees = donnees[:n * pas]
    couleurs = donnees if dxt1 else donnees[8:]
    canaux, quatre = _teintes(couleurs, pas, n, dxt1)
    plein = (1 << (8 * n)) - 1
    # Une image par rangée de bloc (y = 0 à 3) : dans chacune, le pixel p du bloc b est à 16 b + 4 p,
    # un pas fixe d'un bout à l'autre. Les quatre s'entrelacent ligne à ligne à la fin.
    sous = [bytearray(16 * n) for _ in range(4)]
    for y in range(4):
        rangee = couleurs[4 + y::pas]
        for p in range(4):
            masques = [int.from_bytes(rangee.translate(table), "little") for table in _EGAL2[p]]
            for c, teintes in enumerate(canaux):
                valeur = ((teintes[0] & masques[0]) | (teintes[1] & masques[1])
                          | (teintes[2] & masques[2]) | (teintes[3] & masques[3]))
                sous[y][4 * p + c::16] = valeur.to_bytes(n, "little")
            if dxt1:    # opaque, sauf la quatrième teinte d'un bloc à trois
                sous[y][4 * p + 3::16] = (plein ^ (masques[3] & (plein ^ quatre))).to_bytes(n, "little")
    if not dxt1:
        _alphas(sous, donnees, n)
    ligne = largeur * 4
    return b"".join(sous[y][r:r + ligne] for r in range(0, 16 * n, ligne) for y in range(4))


def _alphas(sous: list[bytearray], donnees: bytes, n: int) -> None:
    """L'alpha d'une image DXT5 : huit valeurs par bloc (six interpolées si a0 > a1 ; sinon quatre,
    puis 0 et 255), choisies par 16 indices de 3 bits rangés sur six octets."""
    v0, v1 = _voies(donnees[0::16]), _voies(donnees[1::16])
    plein = (1 << (8 * n)) - 1
    huit = _plus_grand(v0, v1, 8, n)
    six = plein ^ huit
    valeurs = [int.from_bytes(donnees[0::16], "little"), int.from_bytes(donnees[1::16], "little")]
    for i in range(1, 7):
        alpha = _entier((((7 - i) * v0 + i * v1) * _SEPTIEME[0]) >> _SEPTIEME[1], n) & huit
        if i < 5:
            alpha |= _entier((((5 - i) * v0 + i * v1) * _CINQUIEME[0]) >> _CINQUIEME[1], n) & six
        elif i == 6:
            alpha |= six
        valeurs.append(alpha)
    bits = bytearray(8 * n)
    for o in range(6):
        bits[o::8] = donnees[2 + o::16]
    indices = int.from_bytes(bits, "little")
    for pixel in range(16):
        choisis = (indices >> (3 * pixel)).to_bytes(8 * n, "little")[0::8]
        alpha = 0
        for valeur, table in zip(valeurs, _EGAL3, strict=True):
            alpha |= valeur & int.from_bytes(choisis.translate(table), "little")
        sous[pixel >> 2][4 * (pixel & 3) + 3::16] = alpha.to_bytes(n, "little")


def dxt1(donnees: bytes, largeur: int, hauteur: int) -> bytes:
    """Pixels B V R A d'une image DXT1 (largeur et hauteur multiples de 4)."""
    return _decoder(donnees, largeur, hauteur, dxt1=True)


def dxt5(donnees: bytes, largeur: int, hauteur: int) -> bytes:
    """Pixels B V R A d'une image DXT5 (largeur et hauteur multiples de 4)."""
    return _decoder(donnees, largeur, hauteur, dxt1=False)
