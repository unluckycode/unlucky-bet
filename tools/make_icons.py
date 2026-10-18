"""Generuje ikony PWA (wymaga Pillow: pip install pillow). Uruchom: python tools/make_icons.py"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "unluckybet" / "static" / "icons"
BG_TOP, BG_BOTTOM = (19, 40, 74), (11, 17, 32)
GREEN = (34, 197, 94)


def font(size):
    for name in ("DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_icon(size, maskable=False, rounded=True):
    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    grad = Image.new("RGBA", (s, s))
    gd = ImageDraw.Draw(grad)
    for y in range(s):
        t = y / s
        gd.line([(0, y), (s, y)], fill=tuple(int(BG_TOP[i] * (1 - t) + BG_BOTTOM[i] * t) for i in range(3)) + (255,))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22) if rounded else 0, fill=255)
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    pad = s * (0.22 if maskable else 0.14)
    d.ellipse([pad, pad, s - pad, s - pad], outline=GREEN, width=int(s * 0.055))
    f = font(int(s * (0.42 if maskable else 0.5)))
    d.text((s / 2, s / 2 + s * 0.01), "X", font=f, fill=(230, 236, 247), anchor="mm")
    return img.resize((size, size), Image.LANCZOS)


def draw_badge(size=96):
    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([s * 0.08, s * 0.08, s * 0.92, s * 0.92], outline=(255, 255, 255, 255), width=int(s * 0.08))
    d.text((s / 2, s / 2), "X", font=font(int(s * 0.5)), fill=(255, 255, 255, 255), anchor="mm")
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    draw_icon(192).save(OUT / "icon-192.png")
    draw_icon(512).save(OUT / "icon-512.png")
    draw_icon(512, maskable=True, rounded=False).save(OUT / "icon-maskable-512.png")
    draw_icon(180, rounded=False).convert("RGB").save(OUT / "apple-touch-icon.png")
    draw_badge().save(OUT / "badge-96.png")
    print("Zapisano ikony w", OUT)
