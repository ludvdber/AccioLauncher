"""Prépare les médailles de la rubrique Défis à partir des images sources (1024 px).

    python tools/preparer_medailles.py [dossier_source] [--planche fichier.png]

- Bases (`medaille-<métal>.png`) : le disque de chaque médaille est ramené au MÊME
  diamètre et à la MÊME place. La verrouillée n'a pas de ruban : sans ça, son disque
  paraîtrait plus grand que les autres.
- Emblèmes (`embleme-<famille>.png`) : rognés à leur silhouette, recentrés sur un carré.
- Le tout en 256 px dans `assets/medailles/`. `--planche` écrit en plus chaque emblème
  posé sur chaque métal, sur le fond du launcher, pour juger l'ensemble.

Une image source tronquée (téléchargement interrompu) est signalée et sautée.
"""
import argparse
from pathlib import Path

from PIL import Image

RACINE = Path(__file__).resolve().parent.parent
CIBLE = RACINE / "assets" / "medailles"
COTE = 256
# Cadre commun, en pixels du 1024 d'origine : disque de 724 centré en (512, 630).
DIAMETRE, CX, CY = 724, 512, 630
METAUX = ("bronze", "argent", "or", "verrouillee")
# Teinte posée sur l'emblème (gris étain) selon le métal, et sa force.
TEINTES = {"bronze": ((176, 112, 62), 0.42), "argent": ((200, 202, 208), 0.10),
           "or": ((222, 172, 60), 0.45), "verrouillee": ((40, 40, 44), 0.55)}
EMBLEME_SUR_DISQUE = 0.50


def ouvrir(f: Path) -> Image.Image | None:
    im = Image.open(f)
    try:
        im.load()
    except OSError:
        print("tronquée, sautée :", f.name)
        return None
    return im.convert("RGBA")


def boite(im: Image.Image) -> tuple[int, int, int, int]:
    b = im.getchannel("A").point(lambda v: 255 if v > 16 else 0).getbbox()
    if b is None:
        raise ValueError("image entièrement transparente")
    return b


def base(f: Path, verrouillee: bool) -> Image.Image | None:
    im = ouvrir(f)
    if im is None:
        return None
    x0, y0, x1, y1 = boite(im)
    d = x1 - x0
    # Avec un ruban, le disque est le bas de l'image ; sans, il en est le centre.
    cy = (y0 + y1) / 2 if verrouillee else y1 - d / 2
    cx = (x0 + x1) / 2
    k = DIAMETRE / d
    grande = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    toile = Image.new("RGBA", (1024, 1024))
    toile.alpha_composite(grande, (round(CX - cx * k), round(CY - cy * k)))
    return toile


def embleme(f: Path) -> Image.Image | None:
    im = ouvrir(f)
    if im is None:
        return None
    im = im.crop(boite(im))
    c = max(im.size)
    carre = Image.new("RGBA", (c, c))
    carre.alpha_composite(im, ((c - im.width) // 2, (c - im.height) // 2))
    return carre


def assembler(b: Image.Image, e: Image.Image, metal: str) -> Image.Image:
    taille = round(DIAMETRE * EMBLEME_SUR_DISQUE)
    e = e.resize((taille, taille), Image.LANCZOS)
    couleur, force = TEINTES[metal]
    plein = Image.new("RGBA", e.size, (*couleur, 255))
    plein.putalpha(e.getchannel("A"))
    out = b.copy()
    out.alpha_composite(Image.blend(e, plein, force), (CX - taille // 2, CY - taille // 2))
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("source", nargs="?", type=Path,
                   default=RACINE / "Accio_Medailles" / "assets" / "medailles")
    p.add_argument("--planche", type=Path)
    args = p.parse_args()

    CIBLE.mkdir(exist_ok=True)
    bases = {}
    for metal in METAUX:
        f = args.source / f"medaille-{metal}.png"
        b = base(f, metal == "verrouillee") if f.exists() else None
        if b is not None:
            bases[metal] = b
            b.resize((COTE, COTE), Image.LANCZOS).save(CIBLE / f.name, optimize=True)
    emblemes = {}
    for f in sorted(args.source.glob("embleme-*.png")):
        e = embleme(f)
        if e is not None:
            emblemes[f.stem.removeprefix("embleme-")] = e
            e.resize((COTE, COTE), Image.LANCZOS).save(CIBLE / f.name, optimize=True)
    print("bases :", ", ".join(bases), "| emblèmes :", ", ".join(emblemes))

    if args.planche and bases and emblemes:
        v = 150
        planche = Image.new("RGB", (len(emblemes) * v + 10, len(bases) * v + 10), (6, 6, 17))
        for j, metal in enumerate(bases):
            for i, e in enumerate(emblemes.values()):
                a = assembler(bases[metal], e, metal).resize((v - 6, v - 6), Image.LANCZOS)
                planche.paste(a, (5 + i * v, 5 + j * v), a)
        planche.save(args.planche)


if __name__ == "__main__":
    main()
