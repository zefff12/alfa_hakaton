"""Неоновая графика на тёмном фоне → та же графика на прозрачном (для светлой темы).

Тёмный фон уходит в прозрачность, а цвет свечения восстанавливается обратным
смешиванием с чёрным, поэтому ленты и иллюстрации одинаково смотрятся
и на белом, и на тёмном фоне.

    uv run --no-project --with pillow python tools/glow_to_alpha.py SRC DST [--lo 30] [--hi 150]
"""
import argparse

from PIL import Image


def glow_to_alpha(src: str, dst: str, lo: int = 30, hi: int = 150) -> None:
    im = Image.open(src).convert("RGB")
    out = Image.new("RGBA", im.size)
    px, op = im.load(), out.load()
    for y in range(im.height):
        for x in range(im.width):
            c = px[x, y]
            a = max(0.0, min(1.0, (max(c) - lo) / (hi - lo)))  # ниже lo — фон, выше hi — непрозрачно
            if a < 0.02:
                op[x, y] = (0, 0, 0, 0)
            else:
                op[x, y] = (*(min(255, round(v / a)) for v in c), round(a * 255))
    out.save(dst, quality=90, method=6)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--lo", type=int, default=30)
    ap.add_argument("--hi", type=int, default=150)
    a = ap.parse_args()
    glow_to_alpha(a.src, a.dst, a.lo, a.hi)
