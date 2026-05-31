from pathlib import Path

from PIL import Image


root = Path(__file__).resolve().parent.parent
source = root / "assets" / "gps_app_icon.png"
output = root / ".pyinstaller-cache" / "gps_app_icon.png"

output.parent.mkdir(parents=True, exist_ok=True)
with Image.open(source) as image:
    image.convert("RGBA").save(output, format="PNG", optimize=True)

print(f"Prepared {output}")
