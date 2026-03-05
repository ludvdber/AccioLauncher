"""Genere docs/social_preview.png — image social preview GitHub 1280x640."""

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1280, 640
BG_TOP = (6, 6, 17)        # #060611
BG_BOTTOM = (13, 13, 26)   # #0d0d1a
GOLD = (212, 160, 23)      # #d4a017
SUBTITLE_COLOR = (138, 138, 170)  # #8a8aaa

FONTS_DIR = Path(__file__).parent.parent / "assets" / "fonts"
OUTPUT = Path(__file__).parent.parent / "docs" / "social_preview.png"


def _lerp_color(c1: tuple, c2: tuple, t: float) -> tuple:
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def main() -> None:
    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)

    # Degrade vertical
    for y in range(HEIGHT):
        t = y / HEIGHT
        color = _lerp_color(BG_TOP, BG_BOTTOM, t)
        draw.line([(0, y), (WIDTH, y)], fill=color)

    # Particules dorees
    random.seed(42)
    for _ in range(80):
        x = random.randint(0, WIDTH)
        y = random.randint(0, HEIGHT)
        size = random.uniform(1.0, 3.5)
        alpha = random.randint(40, 140)
        # Dessiner sur une couche separee pour l'opacite
        r, g, b = GOLD
        draw.ellipse(
            [x - size, y - size, x + size, y + size],
            fill=(r, g, b, alpha) if img.mode == "RGBA" else (
                int(r * alpha / 255 + BG_BOTTOM[0] * (1 - alpha / 255)),
                int(g * alpha / 255 + BG_BOTTOM[1] * (1 - alpha / 255)),
                int(b * alpha / 255 + BG_BOTTOM[2] * (1 - alpha / 255)),
            ),
        )

    # Quelques particules plus grosses avec glow
    for _ in range(12):
        x = random.randint(100, WIDTH - 100)
        y = random.randint(80, HEIGHT - 80)
        for radius in range(12, 0, -2):
            alpha_frac = 0.03 * (12 - radius) / 12
            r = int(GOLD[0] * alpha_frac + BG_BOTTOM[0] * (1 - alpha_frac))
            g = int(GOLD[1] * alpha_frac + BG_BOTTOM[1] * (1 - alpha_frac))
            b = int(GOLD[2] * alpha_frac + BG_BOTTOM[2] * (1 - alpha_frac))
            draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=(r, g, b))
        draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill=GOLD)

    # Charger les polices
    try:
        title_font = ImageFont.truetype(str(FONTS_DIR / "CinzelDecorative-Bold.ttf"), 72)
    except OSError:
        title_font = ImageFont.load_default()

    try:
        subtitle_font = ImageFont.truetype(str(FONTS_DIR / "Cinzel-Variable.ttf"), 24)
    except OSError:
        subtitle_font = ImageFont.load_default()

    # Titre
    title = "Accio Launcher"
    bbox = draw.textbbox((0, 0), title, font=title_font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = (WIDTH - tw) // 2
    ty = (HEIGHT - th) // 2 - 40

    # Eclair emoji avant le titre
    lightning = "\u26a1 "
    try:
        # Dessiner le titre sans emoji (Cinzel n'a pas d'emoji)
        full_title = lightning + title
        # On dessine juste le titre en Cinzel
        draw.text((tx, ty), title, font=title_font, fill=GOLD)
    except Exception:
        draw.text((tx, ty), title, font=title_font, fill=GOLD)

    # Sous-titre
    subtitle = "Le launcher magique pour les jeux Harry Potter PC"
    bbox2 = draw.textbbox((0, 0), subtitle, font=subtitle_font)
    sw = bbox2[2] - bbox2[0]
    sx = (WIDTH - sw) // 2
    sy = ty + th + 30
    draw.text((sx, sy), subtitle, font=subtitle_font, fill=SUBTITLE_COLOR)

    # Ligne doree decorative sous le sous-titre
    line_w = 120
    line_y = sy + 50
    line_x = (WIDTH - line_w) // 2
    draw.line([(line_x, line_y), (line_x + line_w, line_y)], fill=(*GOLD, 80), width=1)

    # Sauvegarder
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(OUTPUT), format="PNG")
    print(f"Social preview generee : {OUTPUT} ({WIDTH}x{HEIGHT})")


if __name__ == "__main__":
    main()
