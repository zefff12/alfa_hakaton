"""Удаление белого фона с изображений Альфика (фон → прозрачность, тень → полупрозрачная)."""
import sys
from collections import deque

from PIL import Image, ImageFilter


def cutout(src: str, dst: str, size: int = 640) -> None:
    im = Image.open(src).convert("RGB")
    im.thumbnail((size, size), Image.LANCZOS)
    w, h = im.size
    px = im.load()

    def bg_like(p):
        r, g, b = p
        # светлые пиксели (фон, тень, блики на полу), связанные с краем изображения
        return min(r, g, b) > 196 or (max(r, g, b) - min(r, g, b) < 22 and min(r, g, b) > 150)

    mask = [[False] * w for _ in range(h)]
    q = deque((x, y) for x in range(w) for y in (0, h - 1))
    q.extend((x, y) for y in range(h) for x in (0, w - 1))
    while q:
        x, y = q.popleft()
        if mask[y][x] or not bg_like(px[x, y]):
            continue
        mask[y][x] = True
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not mask[ny][nx]:
                q.append((nx, ny))

    out = Image.new("RGBA", (w, h))
    op = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if mask[y][x]:
                # color-to-alpha относительно белого: тень становится полупрозрачной, сохраняя оттенок
                a = max(255 - r, 255 - g, 255 - b) / 255
                a = 0.0 if a < 0.035 else min(1.0, (a - 0.035) * 1.6)
                if a <= 0:
                    op[x, y] = (0, 0, 0, 0)
                else:
                    c = [max(0, min(255, int(255 - (255 - v) / a))) for v in (r, g, b)]
                    op[x, y] = (c[0], c[1], c[2], int(a * 255))
            else:
                op[x, y] = (r, g, b, 255)
    # сглаживаем край, чтобы не было «лесенки»
    alpha = out.getchannel("A").filter(ImageFilter.GaussianBlur(0.6))
    out.putalpha(alpha)
    out.save(dst, optimize=True)


if __name__ == "__main__":
    cutout(sys.argv[1], sys.argv[2])
