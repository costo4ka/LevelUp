"""Собирает значок приложения: icon.png (256x256) и icon.ico (16, 32, 48, 64, 128, 256).

    .venv/bin/python tools/make_icon.py

Берётся герой «m» на стадии 3 (слои LPC из levelup/assets/sprites), собранный в кадр 64x64; голова и плечи
вырезаются окном 32x32, увеличиваются целым множителем (x8) ближайшим соседом и ставятся на плоский тёплый
фон из палитры с контуром ink. Остальные размеры .ico получаются из мастера тем же ближайшим соседом.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw  # noqa: E402

from levelup.config import ASSETS_DIR, load_config  # noqa: E402
from levelup.look import compose_look, load_sprites  # noqa: E402
from levelup.ui.palette import GOLD, INK  # noqa: E402

BASE, STAGE = "m", 3
WINDOW = 32  # сторона вырезки в пикселях кадра: 32 * 8 = 256
SCALE = 8
SIZES = (16, 32, 48, 64, 128, 256)
BORDER = 2  # пикселей спрайта (16 px в значке)
MARGIN_TOP = 2  # сколько пустых рядов оставить над самой высокой точкой причёски


def hex_rgb(value: str) -> tuple[int, int, int]:
    return tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def compose_frame() -> Image.Image:
    config = load_config()
    manifest = load_sprites(config)
    look = compose_look(manifest, BASE, STAGE, {category: 0 for category in config.category_ids})
    frame = Image.new("RGBA", (manifest.frame, manifest.frame), (0, 0, 0, 0))
    for layer in look.character_layers:
        frame = Image.alpha_composite(frame, Image.open(layer.file).convert("RGBA"))
    return frame


def build_master() -> Image.Image:
    frame = compose_frame()
    left, top, right, _ = frame.getbbox()
    x = max(0, min((left + right) // 2 - WINDOW // 2, frame.width - WINDOW))  # фигура по центру окна
    y = max(0, top - MARGIN_TOP)
    crop = frame.crop((x, y, x + WINDOW, y + WINDOW))
    small = Image.new("RGBA", (WINDOW, WINDOW), hex_rgb(GOLD) + (255,))
    small.alpha_composite(crop)
    draw = ImageDraw.Draw(small)
    ink = hex_rgb(INK) + (255,)
    for i in range(BORDER):  # контур ink; углы срезаны «лесенкой», как у панелей интерфейса
        draw.rectangle((i, i, WINDOW - 1 - i, WINDOW - 1 - i), outline=ink)
    transparent = (0, 0, 0, 0)
    for corner_x, corner_y in ((0, 0), (WINDOW - 1, 0), (0, WINDOW - 1), (WINDOW - 1, WINDOW - 1)):
        small.putpixel((corner_x, corner_y), transparent)
    return small.resize((WINDOW * SCALE, WINDOW * SCALE), Image.Resampling.NEAREST)


def main() -> int:
    master = build_master()
    master.save(ASSETS_DIR / "icon.png", optimize=True)
    frames = [master.resize((s, s), Image.Resampling.NEAREST) for s in SIZES]
    master.save(ASSETS_DIR / "icon.ico", format="ICO", sizes=[(s, s) for s in SIZES], append_images=frames[:-1])
    print(f"icon.png {master.size}, icon.ico {SIZES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
