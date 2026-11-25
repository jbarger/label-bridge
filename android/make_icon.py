"""Draws the Label Bridge icon (a little shipping label with a barcode).

    python make_icon.py                 # Android launcher icons into res/mipmap-*/
    python make_icon.py --ico FILE      # Windows .ico (16-256 px)
    python make_icon.py --png FILE N    # one N x N PNG (e.g. 512 for the Play Store)
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SIZES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}


def draw(n: int) -> Image.Image:
    s = 4  # supersample
    N = n * s
    im = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, N - 1, N - 1), radius=N // 5, fill=(255, 112, 40, 255))
    lx0, ly0, lx1, ly1 = N * .24, N * .14, N * .76, N * .86
    d.rounded_rectangle((lx0, ly0, lx1, ly1), radius=N // 28, fill="white")
    w = lx1 - lx0
    for i, frac in enumerate((.70, .45, .55)):  # address lines
        y = ly0 + N * (.08 + i * .07)
        d.rectangle((lx0 + w * .12, y, lx0 + w * (.12 + frac * .76), y + N * .03), fill=(60, 60, 60, 255))
    bars = [3, 1, 2, 1, 1, 3, 1, 2, 2, 1, 3, 1, 1, 2]
    unit = (w * .76) / (sum(bars) * 1.6)
    x = lx0 + w * .12
    for i, b in enumerate(bars):
        if i % 2 == 0:
            d.rectangle((x, ly0 + N * .36, x + b * unit, ly1 - N * .08), fill="black")
        x += b * unit * 1.6
    return im.resize((n, n), Image.Resampling.LANCZOS)


def main(argv: list[str]) -> None:
    if argv[:1] == ["--ico"]:
        draw(256).save(argv[1], sizes=[(n, n) for n in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
    elif argv[:1] == ["--png"]:
        n = int(argv[2])
        im = draw(n)
        if n >= 512:  # Play Store icons must be opaque; it rounds the corners itself
            bg = Image.new("RGBA", im.size, (255, 112, 40, 255))
            bg.alpha_composite(im)
            im = bg.convert("RGB")
        im.save(argv[1])
    else:
        for dens, px in SIZES.items():
            out = HERE / "app" / "src" / "main" / "res" / f"mipmap-{dens}" / "ic_launcher.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            draw(px).save(out)
    print("icons written")


if __name__ == "__main__":
    main(sys.argv[1:])
