"""Convertit assets/accio_launcher.png en assets/accio_launcher.ico multi-resolution."""

from pathlib import Path

from PIL import Image

SIZES = [16, 32, 48, 64, 128, 256]
SRC = Path(__file__).parent.parent / "assets" / "accio_launcher.png"
OUTPUT = Path(__file__).parent.parent / "assets" / "accio_launcher.ico"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    src = Image.open(SRC).convert("RGBA")
    images = [src.resize((s, s), Image.Resampling.LANCZOS) for s in SIZES]

    # Pillow ICO: save largest first, append the rest
    images[-1].save(
        str(OUTPUT),
        format="ICO",
        append_images=images[:-1],
    )
    print(f"Icone generee : {OUTPUT}  ({', '.join(str(s) for s in SIZES)} px)")


if __name__ == "__main__":
    main()
