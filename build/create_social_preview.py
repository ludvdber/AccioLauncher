"""Genere docs/social_preview.png — l'image de partage du depot, 1280x640.

C'est la vignette que GitHub, Discord et les reseaux affichent quand on colle
le lien du depot (a televerser dans Settings > Social preview). Refaite le
2026-09-19 : l'ancienne ecrivait le nom en police de titre sur un semis de
points, sans le logo de la marque ni rien qui montre de quoi il s'agit. Elle
pose desormais le logo officiel (`assets/accio_logo_horizontal.png`), une
accroche, et les huit jaquettes — ce qu'on comprend en un coup d'oeil.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RACINE = Path(__file__).parent.parent
SORTIE = RACINE / "docs" / "social_preview.png"
LARGEUR, HAUTEUR = 1280, 640
FOND_HAUT = (6, 6, 17)        # #060611
FOND_BAS = (13, 13, 26)       # #0d0d1a
OR = (214, 167, 44)           # #d6a72c, l'or du pack de marque
TEXTE = (200, 200, 222)
JEUX = ("hp1", "hp2", "hp3", "hp4", "hp5", "hp6", "hp7a", "hp7b")
ACCROCHE = "Les huit jeux Harry Potter PC, installés et lancés en un clic"


def _degrade() -> Image.Image:
    img = Image.new("RGB", (LARGEUR, HAUTEUR))
    trait = ImageDraw.Draw(img)
    for y in range(HAUTEUR):
        t = y / HAUTEUR
        trait.line([(0, y), (LARGEUR, y)],
                   fill=tuple(int(a + (b - a) * t) for a, b in zip(FOND_HAUT, FOND_BAS)))
    return img


def _jaquette(gid: str, hauteur: int) -> Image.Image:
    """Jaquette en 2:3 : les fichiers n'ont pas tous le meme rapport (trois
    sont carres), on recadre au centre plutot que de les deformer."""
    img = Image.open(RACINE / "assets" / "covers" / f"{gid}_cover.jpg").convert("RGB")
    largeur = round(hauteur * 2 / 3)
    echelle = max(largeur / img.width, hauteur / img.height)
    img = img.resize((round(img.width * echelle), round(img.height * echelle)),
                     Image.Resampling.LANCZOS)
    x, y = (img.width - largeur) // 2, (img.height - hauteur) // 2
    return img.crop((x, y, x + largeur, y + hauteur))


def main() -> None:
    img = _degrade()

    logo = Image.open(RACINE / "assets" / "accio_logo_horizontal.png").convert("RGBA")
    lg = 640
    logo = logo.resize((lg, round(logo.height * lg / logo.width)), Image.Resampling.LANCZOS)
    img.paste(logo, ((LARGEUR - lg) // 2, 40), logo)

    try:
        police = ImageFont.truetype(str(RACINE / "assets" / "fonts" / "Cinzel-Variable.ttf"), 30)
    except OSError:
        police = ImageFont.load_default()
    trait = ImageDraw.Draw(img)
    boite = trait.textbbox((0, 0), ACCROCHE, font=police)
    trait.text(((LARGEUR - (boite[2] - boite[0])) // 2, 262), ACCROCHE, font=police, fill=TEXTE)

    # Les huit jaquettes, en rang, avec un filet d'or dessous.
    haut, ecart = 204, 12
    jaquettes = [_jaquette(g, haut) for g in JEUX]
    total = sum(j.width for j in jaquettes) + ecart * (len(jaquettes) - 1)
    x, y = (LARGEUR - total) // 2, 336
    for j in jaquettes:
        img.paste(j, (x, y))
        x += j.width + ecart
    trait.line([((LARGEUR - total) // 2, y + haut + 16),
                ((LARGEUR + total) // 2, y + haut + 16)], fill=OR, width=2)

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    img.save(SORTIE, format="PNG", optimize=True)
    print(f"Image de partage generee : {SORTIE} ({LARGEUR}x{HAUTEUR})")


if __name__ == "__main__":
    main()
