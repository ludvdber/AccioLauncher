"""Genere assets/accio_launcher.ico — eclair dore sur fond sombre.

Multi-resolution : 16, 32, 48, 64, 128, 256 px.
Utilise Pillow (pip install Pillow).
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZES = [16, 32, 48, 64, 128, 256]
BG_COLOR = (13, 13, 26)       # #0d0d1a
GOLD = (212, 160, 23)         # #d4a017
OUTPUT = Path(__file__).parent.parent / "assets" / "accio_launcher.ico"


def _draw_icon(size: int) -> Image.Image:
    """Dessine un eclair dore dans un cercle sur fond sombre."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Cercle de fond
    margin = max(1, size // 16)
    draw.ellipse(
        [margin, margin, size - margin - 1, size - margin - 1],
        fill=BG_COLOR,
    )

    # Eclair (polygone simplifie)
    cx, cy = size / 2, size / 2
    s = size / 256  # facteur d'echelle

    lightning = [
        (cx - 10 * s, cy - 90 * s),
        (cx + 35 * s, cy - 90 * s),
        (cx + 5 * s,  cy - 15 * s),
        (cx + 40 * s, cy - 15 * s),
        (cx - 20 * s, cy + 90 * s),
        (cx + 5 * s,  cy + 10 * s),
        (cx - 30 * s, cy + 10 * s),
    ]
    draw.polygon(lightning, fill=GOLD)

    # Contour cercle dore subtil
    draw.ellipse(
        [margin, margin, size - margin - 1, size - margin - 1],
        outline=(*GOLD, 120),
        width=max(1, size // 64),
    )

    return img


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    images = [_draw_icon(s) for s in SIZES]

    # Sauvegarde .ico multi-resolution
    images[0].save(
        str(OUTPUT),
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=images[1:],
    )
    print(f"Icone generee : {OUTPUT}  ({', '.join(str(s) for s in SIZES)} px)")


if __name__ == "__main__":
    main()
