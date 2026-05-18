"""Genera icon.ico (multi-res) e icon.png per il logo Cove.

Design: flat moderno (no effetti retro). Cerchio arancio pieno con "C"
cream centrale, terminazioni arrotondate. Nessun bordo, glow, highlight
o ornamenti — pulito e leggibile a tutte le risoluzioni.
"""
import math
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent

ORANGE = (255, 138, 61, 255)   # #ff8a3d
CREAM  = (255, 244, 232, 255)


def render(size: int) -> Image.Image:
    # Supersample x4 per anti-aliasing pulito alle piccole dimensioni
    scale = 4 if size <= 64 else 2
    w = size * scale
    img = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    cx = cy = w // 2
    pad = max(1, w // 64)
    r = (w - 2 * pad) // 2

    # Cerchio arancio pieno
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=ORANGE)

    # "C" cream — un arco con cap arrotondati
    c_outer = int(r * 0.80)
    arc_w = int(c_outer * 0.30)
    bbox_arc = (cx - c_outer + arc_w // 2, cy - c_outer + arc_w // 2,
                cx + c_outer - arc_w // 2, cy + c_outer - arc_w // 2)
    d.arc(bbox_arc, start=40, end=320, fill=CREAM, width=arc_w)

    # Cap arrotondati alle terminazioni
    cap_r = arc_w // 2
    radius_mid = c_outer - arc_w // 2
    for angle_deg in (40, 320):
        a = math.radians(angle_deg)
        ex = cx + int(radius_mid * math.cos(a))
        ey = cy + int(radius_mid * math.sin(a))
        d.ellipse((ex - cap_r, ey - cap_r, ex + cap_r, ey + cap_r), fill=CREAM)

    if scale != 1:
        img = img.resize((size, size), Image.LANCZOS)
    return img


def main() -> None:
    out_ico = ROOT / "icon.ico"
    out_png = ROOT / "icon.png"
    ico_sizes = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
    images = [render(s) for s in ico_sizes]
    images[0].save(
        out_ico,
        format="ICO",
        sizes=[(s, s) for s in ico_sizes],
        append_images=images[1:],
    )
    render(512).save(out_png, format="PNG")
    # Preview multi-res per controllo qualità
    preview = Image.new("RGBA", (520, 96), (40, 40, 44, 255))
    x = 6
    for sz in (16, 24, 32, 48, 64, 96, 128):
        ic = render(sz)
        preview.paste(ic, (x, (96 - sz) // 2), ic)
        x += sz + 8
    preview.save(ROOT / "icon_preview.png")
    print(f"Written: {out_ico}")
    print(f"Written: {out_png}")
    print(f"Preview multi-res: {ROOT / 'icon_preview.png'}")


if __name__ == "__main__":
    main()
