from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def load_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = (
        "C:/Windows/Fonts/arialbd.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    )
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.truetype("DejaVuSans-Bold.ttf", size)


root = Path(__file__).resolve().parent.parent
output = root / ".pyinstaller-cache" / "gps_app_icon.png"

background = (158, 93, 155, 255)
outline = (23, 14, 25, 255)
light = (236, 216, 235, 255)
shadow = (200, 168, 201, 255)

image = Image.new("RGBA", (512, 512), background)
draw = ImageDraw.Draw(image)

# Draw a compact inverted RC airplane mark with the wheels above the fuselage.
draw.polygon(((177, 151), (45, 213), (86, 248), (239, 177)), fill=light, outline=outline, width=10)
draw.polygon(((239, 177), (86, 248), (118, 221), (257, 190)), fill=shadow)
draw.line(((177, 151), (45, 213), (86, 248), (239, 177)), fill=outline, width=10, joint="curve")

draw.polygon(((118, 118), (144, 100), (387, 243), (372, 272), (333, 251), (105, 136)), fill=light, outline=outline, width=10)
draw.polygon(((132, 127), (372, 272), (333, 251), (164, 158)), fill=shadow)
draw.line(((118, 118), (144, 100), (387, 243), (372, 272), (333, 251), (105, 136), (118, 118)), fill=outline, width=10, joint="curve")

draw.polygon(((295, 217), (393, 199), (426, 218), (348, 258)), fill=light, outline=outline, width=10)
draw.polygon(((327, 252), (377, 304), (405, 267), (369, 238)), fill=light, outline=outline, width=10)
draw.polygon(((349, 258), (377, 304), (390, 285), (369, 238)), fill=shadow)
draw.line(((327, 252), (377, 304), (405, 267), (369, 238)), fill=outline, width=10, joint="curve")

draw.line(((156, 118), (154, 79)), fill=outline, width=10)
draw.line(((213, 151), (222, 96)), fill=outline, width=10)
for center in ((154, 74), (224, 89)):
    draw.ellipse((center[0] - 21, center[1] - 21, center[0] + 21, center[1] + 21), fill=outline)
    draw.ellipse((center[0] - 8, center[1] - 8, center[0] + 8, center[1] + 8), fill=light)

draw.ellipse((378, 218, 416, 256), fill=outline)
draw.ellipse((389, 229, 405, 245), fill=light)

font = load_font(148)
draw.text((256, 420), "GPS", anchor="mm", font=font, fill="white", stroke_width=6, stroke_fill=outline)

output.parent.mkdir(parents=True, exist_ok=True)
image.save(output, format="PNG", optimize=True)

print(f"Prepared {output}")
