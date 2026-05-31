from pathlib import Path
from urllib.request import urlopen

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "inverted_aviators_rc_source.png"
OUTPUT = ROOT / "assets" / "gps_app_icon.png"
SOURCE_URL = "https://avatars.githubusercontent.com/u/166849796?v=4&s=1024"
SIZE = 1024
BACKGROUND = "#9a6099"
TEXT = "#f8f1fb"
OUTLINE = "#17101b"


def _font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def main() -> None:
    if not SOURCE.exists():
        SOURCE.parent.mkdir(parents=True, exist_ok=True)
        SOURCE.write_bytes(urlopen(SOURCE_URL, timeout=30).read())

    source = Image.open(SOURCE).convert("RGBA")
    canvas = Image.new("RGBA", (SIZE, SIZE), BACKGROUND)

    logo = source.resize((820, 820), Image.Resampling.LANCZOS)
    canvas.alpha_composite(logo, ((SIZE - logo.width) // 2, 4))

    draw = ImageDraw.Draw(canvas)
    label = "GPS"
    font = _font(190)
    bounds = draw.textbbox((0, 0), label, font=font, stroke_width=8)
    text_width = bounds[2] - bounds[0]
    draw.text(
        ((SIZE - text_width) // 2, 784),
        label,
        font=font,
        fill=TEXT,
        stroke_width=8,
        stroke_fill=OUTLINE,
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(OUTPUT, optimize=True)
    print("Created {}".format(OUTPUT))


if __name__ == "__main__":
    main()
