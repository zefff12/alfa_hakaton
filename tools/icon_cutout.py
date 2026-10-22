"""Прозрачный фон у неоновых иконок продуктов (вырезаны из растрового макета Figma на тёмном фоне).

Фон — тёмная область, связанная с краем картинки (яркость ниже порога --limit).
Он заливается от краёв и становится прозрачным; только край неонового свечения
у самого порога остаётся полупрозрачным, поэтому иконка без «квадрата» и без
грязного ореола ложится на любую подложку. Тёмные детали внутри контура
(лист документа, корпус дрели) не трогаются: до них заливка не доходит.

    uv run --no-project --with pillow python tools/icon_cutout.py SRC DST [--limit 115] [--crop-bottom 0.08] [--size 256]
"""
import argparse
from collections import deque

from PIL import Image, ImageFilter


def cutout(src: str, dst: str, limit: int = 115, crop_bottom: float = 0.0, size: int = 256) -> None:
    im = Image.open(src).convert("RGB")
    if crop_bottom:
        im = im.crop((0, 0, im.width, int(im.height * (1 - crop_bottom))))
    if max(im.size) < size:  # мелкие вырезки увеличиваем до обработки — край получается мягче
        k = size / max(im.size)
        im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    w, h = im.size
    px = im.load()
    v = lambda p: max(p)  # яркость = максимум канала: неон яркий в любом цвете
    lo, hi = limit - 30, limit + 40  # ниже lo — прозрачно, выше hi — непрозрачно

    seen = bytearray(w * h)
    q = deque((x, y) for x in range(w) for y in (0, h - 1))
    q.extend((x, y) for y in range(h) for x in (0, w - 1))
    while q:
        x, y = q.popleft()
        i = y * w + x
        if seen[i] or v(px[x, y]) > limit:
            continue
        seen[i] = 1
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx]:
                q.append((nx, ny))

    out = Image.new("RGBA", (w, h))
    op = out.load()
    for y in range(h):
        for x in range(w):
            c = px[x, y]
            if not seen[y * w + x]:
                op[x, y] = (*c, 255)
                continue
            a = max(0.0, min(1.0, (v(c) - lo) / (hi - lo)))
            if a < 0.03:
                op[x, y] = (0, 0, 0, 0)
                continue
            # свечение на тёмном: цвет без примеси чёрного (обратное смешивание с чёрным)
            col = [min(255, round(c[k] / a)) for k in range(3)]
            op[x, y] = (*col, round(a * 255))
    out.putalpha(out.getchannel("A").filter(ImageFilter.GaussianBlur(0.5)))

    box = out.getchannel("A").point(lambda a: 255 if a > 12 else 0).getbbox() or (0, 0, w, h)
    out = out.crop(box)
    side = max(out.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(out, ((side - out.width) // 2, (side - out.height) // 2))
    canvas.thumbnail((size, size), Image.LANCZOS)
    canvas.save(dst, quality=92, method=6)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--limit", type=int, default=115)
    ap.add_argument("--crop-bottom", type=float, default=0.0)
    ap.add_argument("--size", type=int, default=256)
    args = ap.parse_args()
    cutout(args.src, args.dst, args.limit, args.crop_bottom, args.size)
