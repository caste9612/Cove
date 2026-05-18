"""Genera icon.ico (multi-res) e icon.png per il logo Cove.

Design: cerchio arancione con 'audio waves' bianche che si propagano da sinistra
verso destra (puntino + 3 archi crescenti). Evoca: suono che emana, caletta
con onde concentriche.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent

# Palette Cove
ORANGE      = (255, 138, 61, 255)    # #ff8a3d - accent primario
ORANGE_DK   = (230, 110, 30, 255)    # bordo / shadow
CREAM       = (255, 244, 232, 255)   # #fff4e8 - onde


def render(size: int) -> Image.Image:
    # Lavoriamo a doppia risoluzione per anti-aliasing
    scale = 4 if size <= 64 else 2
    w = size * scale
    img = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    pad = max(2, w // 22)
    cx = cy = w // 2
    r = (w - 2 * pad) // 2

    # Sfondo: cerchio arancione + bordo leggero per profondità
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=ORANGE)
    # Bordo sottile più scuro
    border_w = max(2, w // 80)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=ORANGE_DK, width=border_w)

    # Punto bianco a sinistra-centro (origine delle onde)
    dot_r = max(3, w // 16)
    dot_cx = cx - r // 2
    dot_cy = cy
    d.ellipse(
        (dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r),
        fill=CREAM,
    )

    # 3 archi bianchi che si espandono a destra dell'origine
    wave_w = max(3, w // 22)
    radii = [int(r * 0.42), int(r * 0.62), int(r * 0.82)]
    for ar in radii:
        bbox = (dot_cx - ar, dot_cy - ar, dot_cx + ar, dot_cy + ar)
        d.arc(bbox, start=-55, end=55, fill=CREAM, width=wave_w)

    # Downscale con filtro lanczos per anti-aliasing
    if scale != 1:
        img = img.resize((size, size), Image.LANCZOS)
    return img


def main() -> None:
    out_ico = ROOT / "icon.ico"
    out_png = ROOT / "icon.png"

    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [render(s) for s in ico_sizes]
    # Salva ICO multi-res
    images[0].save(
        out_ico,
        format="ICO",
        sizes=[(s, s) for s in ico_sizes],
        append_images=images[1:],
    )
    # PNG grande per README/store
    render(512).save(out_png, format="PNG")

    print(f"Written: {out_ico}")
    print(f"Written: {out_png}")


if __name__ == "__main__":
    main()
