#!/usr/bin/env python3
"""LevelUp v2 / ROOM: draws the scene background, props, lighting, icons and fx.

Run:  .venv/bin/python tools/build_room.py

Everything is defined in code (palette + small drawing helpers + ASCII art),
no external art. Output goes to levelup/assets/sprites/{room,icons,fx}.
Scene 192x128, character anchor (64,56), floor_y 96.
Light comes from the window, upper left: highlights top/left, shade bottom/right.
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SPR = ROOT / "levelup" / "assets" / "sprites"
W, H = 192, 128
FLOOR_Y = 96
ANCHOR = (64, 56)
FIG = (81, 68, 111, 118)          # character figure box, inclusive x0,y0,x1,y1
CROP = (32, 32, 128, 96)          # compact_crop x,y,w,h

# ---------------------------------------------------------------- palette ---
# One palette for the whole scene. Three tones per material (light / base /
# dark); the dark tone doubles as the outline, wood has a fourth, darker one.
PAL_HEX = {
    "sage_l": "#adc4b4", "sage_m": "#97b2a1", "sage_d": "#7b998d",      # wall
    "teal_l": "#7b998d", "teal_m": "#5f7f7a", "teal_d": "#4a6764",      # wainscot (teal_l == sage_d)
    "cream_l": "#f6eed6", "cream_m": "#e6d8b4", "cream_d": "#bfae88",   # trim, paper
    "floor_l": "#d6ae72", "floor_m": "#bd8c57", "floor_d": "#9d7044",
    "floor_dd": "#6e4a2d",                                              # floor + wood outline
    "pine_l": "#f0d8a8", "pine_m": "#d6ae72", "pine_d": "#b38951",      # furniture (pine_m == floor_l)
    "terra_l": "#dc9874", "terra_m": "#bd6d4d", "terra_d": "#8f4a39",   # terracotta
    "sky_m": "#aed0d9",
    "metal_l": "#b7bfc4", "metal_m": "#838c94", "metal_d": "#4f5860",
    "moss_l": "#84b06c", "moss_m": "#5a8a4a", "moss_d": "#3f6636",
    "gold_l": "#f4d474", "gold_m": "#dca93b", "gold_d": "#a8741a",
    "blue_l": "#7a9cc4", "blue_m": "#4c72a2", "blue_d": "#36527a",
    "plum_m": "#7d5e86", "plum_d": "#593f66",
}
PAL = {k: tuple(int(v[i:i + 2], 16) for i in (1, 3, 5)) + (255,) for k, v in PAL_HEX.items()}

# (light, base, shade, outline) per material
RAMP = {
    "pine": ("pine_l", "pine_m", "pine_d", "floor_dd"),
    "wood": ("floor_l", "floor_m", "floor_d", "floor_dd"),
    "metal": ("metal_l", "metal_m", "metal_d", "metal_d"),
    "terra": ("terra_l", "terra_m", "terra_d", "terra_d"),
    "moss": ("moss_l", "moss_m", "moss_d", "moss_d"),
    "gold": ("gold_l", "gold_m", "gold_d", "gold_d"),
    "blue": ("blue_l", "blue_m", "blue_d", "blue_d"),
    "plum": ("plum_m", "plum_m", "plum_d", "plum_d"),
    "teal": ("teal_l", "teal_m", "teal_d", "teal_d"),
    "cream": ("cream_l", "cream_m", "cream_d", "floor_dd"),
    "shade": ("cream_l", "gold_l", "gold_m", "gold_d"),   # lit lampshade
}
N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))


def col(c):
    """palette key | '#rrggbb' | rgba tuple -> rgba tuple"""
    if isinstance(c, str):
        if c in PAL:
            return PAL[c]
        if c.startswith("#"):
            return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) + (255,)
        raise KeyError(c)
    return c if len(c) == 4 else tuple(c) + (255,)


# ------------------------------------------------------------------ shapes ---
def R(x0, y0, x1, y1):
    """filled rectangle, inclusive corners"""
    return {(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)}


def E(cx, cy, rx, ry, th=0.0):
    """filled (rotated) ellipse; th in degrees (major axis rx turned by th, y down)"""
    t = math.radians(th)
    ct, st = math.cos(t), math.sin(t)
    m = int(max(rx, ry)) + 2
    out = set()
    for y in range(int(cy) - m, int(cy) + m + 1):
        for x in range(int(cx) - m, int(cx) + m + 1):
            dx, dy = x - cx, y - cy
            u, v = dx * ct + dy * st, -dx * st + dy * ct
            if (u / rx) ** 2 + (v / ry) ** 2 <= 1.0:
                out.add((x, y))
    return out


def D(cx, cy, r):
    return E(cx, cy, r, r)


def P(pts):
    """filled polygon"""
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, y0 = min(xs), min(ys)
    m = Image.new("1", (max(xs) - x0 + 1, max(ys) - y0 + 1), 0)
    ImageDraw.Draw(m).polygon([(x - x0, y - y0) for x, y in pts], fill=1)
    mp = m.load()
    return {(x0 + i, y0 + j) for j in range(m.height) for i in range(m.width) if mp[i, j]}


def LN(x0, y0, x1, y1):
    """1px line (Bresenham-ish by sampling)"""
    n = max(abs(x1 - x0), abs(y1 - y0), 1)
    return {(round(x0 + (x1 - x0) * i / n), round(y0 + (y1 - y0) * i / n)) for i in range(n + 1)}


class Cv:
    """RGBA canvas with pixel-exact helpers"""

    def __init__(self, w=W, h=H):
        self.w, self.h = w, h
        self.im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        self.px = self.im.load()

    def put(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[x, y] = col(c)

    def pts(self, pts, c):
        for x, y in pts:
            self.put(x, y, c)

    def rect(self, x0, y0, x1, y1, c):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.put(x, y, c)

    def hl(self, x0, x1, y, c):
        self.rect(x0, y, x1, y, c)

    def vl(self, x, y0, y1, c):
        self.rect(x, y0, x, y1, c)

    def art(self, rows, x, y, legend):
        """ASCII sprite; '.' and ' ' are transparent"""
        w = len(rows[0])
        for j, r in enumerate(rows):
            assert len(r) == w, f"ragged ascii row {j}: {len(r)} != {w}: {r!r}"
            for i, ch in enumerate(r):
                if ch not in ". ":
                    self.put(x + i, y + j, legend[ch])

    def paint(self, shape, ramp, shadow=True):
        """outline + 3 tones with light from the upper left"""
        hi, mid, lo, ol = RAMP[ramp] if isinstance(ramp, str) else ramp
        S = set(shape)
        B = {p for p in S if any((p[0] + dx, p[1] + dy) not in S for dx, dy in N4)}
        for (x, y) in S:
            if (x, y) in B:
                self.put(x, y, ol)
                continue
            up = (x, y - 1) in B or (x - 1, y) in B
            dn = (x, y + 1) in B or (x + 1, y) in B
            if up and not dn:
                k = hi
            elif dn and not up and shadow:
                k = lo
            else:
                k = mid
            self.put(x, y, k)

    def opaque(self):
        return {(x, y) for y in range(self.h) for x in range(self.w) if self.px[x, y][3] > 0}

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.im.save(path)


def floor_shadow(c, x0, x1, y):
    c.hl(x0, x1, y, "floor_d")


# ------------------------------------------------------------- background ---
def make_background() -> Cv:
    """Empty room: sage wall, teal wainscot, cream rail/baseboard, plank floor, window."""
    c = Cv()
    # wall + a very quiet wallpaper dot lattice
    c.rect(0, 0, W - 1, 95, "sage_m")
    for j, y in enumerate(range(9, 66, 8)):
        for x in range(2 + (4 if j % 2 else 0), W, 8):
            c.put(x, y, "sage_l")
    # crown moulding
    c.rect(0, 0, W - 1, 2, "cream_m")
    c.hl(0, W - 1, 0, "cream_l")
    c.hl(0, W - 1, 3, "cream_d")
    c.hl(0, W - 1, 4, "sage_d")
    # chair rail
    c.hl(0, W - 1, 68, "cream_l")
    c.rect(0, 69, W - 1, 70, "cream_m")
    c.hl(0, W - 1, 71, "cream_d")
    c.hl(0, W - 1, 72, "teal_d")
    # wainscot with raised panels
    c.rect(0, 73, W - 1, 90, "teal_m")
    c.hl(0, W - 1, 90, "teal_d")
    for i in range(8):
        x0, x1 = 24 * i + 3, 24 * i + 21
        c.rect(x0, 76, x1, 87, "teal_m")
        c.hl(x0, x1, 76, "teal_d")          # recessed panel: shade on top/left, light on bottom/right
        c.vl(x0, 76, 87, "teal_d")
        c.hl(x0 + 1, x1, 87, "teal_l")
        c.vl(x1, 77, 87, "teal_l")
    # baseboard
    c.hl(0, W - 1, 91, "cream_l")
    c.rect(0, 92, W - 1, 94, "cream_m")
    c.hl(0, W - 1, 95, "cream_d")
    _floor(c)
    _window(c)
    return c


def _floor(c: Cv):
    c.rect(0, FLOOR_Y, W - 1, H - 1, "floor_m")
    c.hl(0, W - 1, FLOOR_Y, "floor_dd")                 # contact shadow under the baseboard
    rnd = random.Random(11)
    rows = [(97, 104), (105, 112), (113, 120), (121, 127)]
    for r, (y0, y1) in enumerate(rows):
        c.hl(0, W - 1, y0, "floor_l")
        if y1 < H - 1 or r < 3:
            c.hl(0, W - 1, y1, "floor_d")
        step = 56
        for jx in range((r * 19) % step, W, step):
            c.vl(jx, y0, y1, "floor_d")
            c.vl(jx + 1, y0 + 1, y1 - 1, "floor_l")
        for _ in range(7):                                # wood grain dashes
            gx, gy = rnd.randrange(0, W - 6), rnd.randrange(y0 + 2, y1 - 1)
            c.hl(gx, gx + rnd.choice((2, 3, 4)), gy, rnd.choice(("floor_d", "floor_l")))
    # sunlight from the window falls on the floor (slanted, lighter planks, window bars as shadow)
    patch = P([(58, 99), (84, 99), (110, 127), (82, 127)])
    bars = LN(71, 99, 96, 127) | LN(72, 99, 97, 127) | R(0, 111, W, 112)
    for (x, y) in patch:
        if (x, y) not in bars and c.px[x, y] == PAL["floor_m"]:
            c.put(x, y, "floor_l")


def _window(c: Cv):
    # frame + glass
    c.rect(38, 35, 66, 60, "floor_dd")
    c.rect(39, 36, 65, 59, "cream_m")
    c.hl(39, 65, 36, "cream_l")
    c.vl(39, 36, 59, "cream_l")
    c.hl(40, 65, 59, "cream_d")
    c.vl(65, 37, 59, "cream_d")
    c.rect(41, 38, 63, 57, "floor_dd")
    c.rect(42, 39, 62, 56, "sky_m")
    # clouds and distant hills
    for (x, y, w) in ((44, 42, 5), (45, 41, 3), (55, 51, 5), (56, 50, 3), (56, 41, 4), (57, 40, 2)):
        c.hl(x, x + w - 1, y, "cream_l")
    for x in range(42, 63):
        top = 55 - (1 if (x % 9) in (2, 3, 4, 5) else 0)
        c.rect(x, top, x, 56, "moss_l" if top == 54 else "moss_m")
    # muntins (cross)
    c.rect(51, 39, 52, 56, "cream_m")
    c.rect(42, 47, 62, 48, "cream_m")
    c.vl(51, 39, 56, "cream_l")
    c.hl(42, 62, 47, "cream_l")
    c.hl(42, 62, 48, "cream_d")
    c.vl(52, 39, 56, "cream_d")
    # sill + shade under it
    c.rect(36, 61, 68, 63, "cream_m")
    c.hl(36, 68, 61, "cream_l")
    c.hl(36, 68, 63, "cream_d")
    c.vl(36, 61, 63, "floor_dd")
    c.vl(68, 61, 63, "floor_dd")
    c.hl(36, 68, 64, "floor_dd")
    c.hl(37, 70, 65, "sage_d")
    # curtain rod + finials
    c.hl(33, 71, 33, "floor_d")
    c.hl(33, 71, 34, "floor_dd")
    for fx in (32, 72):
        c.rect(fx, 32, fx, 35, "gold_m")
        c.put(fx, 32, "gold_l")
        c.put(fx, 35, "gold_d")
    # terracotta curtains, tied back with gold
    for x0 in (34, 63):
        for y in range(35, 63):
            if y == 35 or y == 62:
                row = "DDDDDDDD"
            elif y in (50, 51):
                row = "gGGGGGGg" if y == 50 else "dgggggGd"
            else:
                row = "DLmmDLmD"
            leg = {"D": "terra_d", "L": "terra_l", "m": "terra_m", "g": "gold_m", "G": "gold_l", "d": "gold_d"}
            for i, ch in enumerate(row):
                c.put(x0 + i, y, leg[ch])
    # tie-back gold fix (bottom row uses darker gold)
    for x0 in (34, 63):
        c.hl(x0, x0 + 7, 51, "gold_m")
        c.put(x0, 51, "gold_d")
        c.put(x0 + 7, 51, "gold_d")


# ----------------------------------------------------------------- props ---
# Every prop is a full-scene RGBA canvas (192x128), drawn in place. Opaque
# pixels only (no soft alpha) except lighting_warm.png.

def prop_sport_1() -> Cv:
    """pair of dumbbells lying on the floor, left of the character"""
    c = Cv()
    for (x, y) in ((49, 112), (53, 120)):
        c.art(DUMBBELL, x, y, DUMBBELL_LEG)
        floor_shadow(c, x + 1, x + 15, y + 7)
    return c


DUMBBELL = ["..dddd...dddd..",        # 15x7, steel outer plates, terracotta inner plates
            "dddxad...dxaddd",
            "dldxadddddxadld",
            "dmdxadlmmdxadmd",
            "dmdxadddddxadmd",
            "dddaad...daaddd",
            "..dddd...dddd.."]
DUMBBELL_LEG = dict(d="metal_d", l="metal_l", m="metal_m", x="terra_l", a="terra_m")


def prop_sport_3() -> Cv:
    """barbell on a squat rack against the wall, two plates per side (far left)"""
    c = Cv()
    floor_shadow(c, 9, 27, 101)
    for x0 in (10, 20):
        c.paint(R(x0, 66, x0 + 3, 100), "terra")         # uprights
    c.paint(R(10, 66, 23, 68), "terra")                   # top bar
    for x0 in (8, 18):
        c.paint(R(x0, 98, x0 + 7, 100), "terra")          # feet
    for y in range(72, 95, 4):                            # pin holes
        c.put(11, y, "terra_d")
        c.put(21, y, "terra_d")
    c.paint(R(14, 78, 16, 80), "terra")                   # J-hooks
    c.paint(R(17, 78, 19, 80), "terra")
    c.paint(R(2, 75, 31, 77), "metal")                    # bar
    c.hl(6, 27, 76, "metal_l")
    for box in ((5, 68, 8, 84), (25, 68, 28, 84), (2, 71, 4, 81), (29, 71, 31, 81)):
        c.paint(R(*box), "metal")                         # plates
    return c


def prop_work_1() -> Cv:
    """small pine desk with an open laptop (glowing screen), a mug and a stool"""
    c = Cv()
    floor_shadow(c, 38, 65, 106)
    floor_shadow(c, 67, 77, 112)
    c.paint(R(37, 90, 40, 105), "pine")                   # left leg
    c.paint(R(49, 90, 62, 104), "pine")                   # drawer pedestal
    c.rect(41, 90, 48, 91, "teal_d")                      # shade under the top
    c.paint(R(36, 84, 63, 89), "pine")                    # desk top
    for y0 in (92, 98):
        c.paint(R(51, y0, 60, y0 + 4), "pine")            # drawers
        c.hl(55, 56, y0 + 2, "gold_m")
        c.put(55, y0 + 2, "gold_l")
    # laptop 14x10: glowing screen, keyboard deck
    laptop = [".DDDDDDDDDDDD.",
              ".DSSSSSSSSSSD.",
              ".DSTTTTTSSSSD.",
              ".DSTTTSSSSSSD.",
              ".DSTTTTTTSSSD.",
              ".DSSSSSSSSSSD.",
              ".DDDDDDDDDDDD.",
              "DLLLLLLLLLLLLD",
              "DMLMLMLMLMLMMD",
              "DDDDDDDDDDDDDD"]
    c.art(laptop, 40, 74, dict(D="metal_d", L="metal_l", M="metal_m", S="cream_l", T="sky_m"))
    for (x, y) in ((40, 76), (40, 78), (40, 80), (53, 76), (53, 78), (53, 80), (43, 73), (45, 73), (47, 73), (49, 73), (51, 73)):
        c.put(x, y, "teal_l")                              # soft glow spilling onto the wall
    mug = ["dddd..",
           "dLmddd",
           "dmmd.d",
           "dddddd"]
    c.art(mug, 57, 80, dict(d="terra_d", L="terra_l", m="terra_m"))
    # stool with a cushion
    c.paint(R(66, 98, 76, 101), "terra")
    c.paint(R(67, 102, 75, 104), "pine")
    for x0 in (67, 73):
        c.paint(R(x0, 105, x0 + 2, 111), "pine")
    c.hl(70, 72, 107, "pine_d")
    c.hl(70, 72, 108, "floor_dd")
    return c


def prop_work_3() -> Cv:
    """briefcase standing on the floor in front of the desk's left leg"""
    c = Cv()
    floor_shadow(c, 34, 46, 117)
    case = ["....DDDDD....",
            "...DM...MD...",
            "...DM...MD...",
            "DDDDDDDDDDDDD",
            "DLLLLLLLLLLLD",
            "DMBMMMMMMMBMD",
            "DMBMMGGGMMBMD",
            "DMBMMGkGMMBMD",
            "DMBMMMMMMMBMD",
            "DDDDDDDDDDDDD"]
    c.art(case, 33, 107, dict(D="blue_d", L="blue_l", M="blue_m", B="blue_d", G="gold_m", k="gold_d"))
    return c


def prop_study_1() -> Cv:
    """stack of four books on the floor, right of the rug"""
    c = Cv()
    floor_shadow(c, 119, 132, 124)
    # bottom to top: (x0, x1, ramp)
    books = [(118, 131, "terra"), (120, 131, "moss"), (119, 129, "gold"), (121, 129, "plum")]
    for i, (xa, xb, r) in enumerate(books):
        yb = 123 - 3 * i                                   # bottom outline row of this book
        c.paint(R(xa, yb - 3, xb, yb), r)                  # 2 fill rows between outlines
    # spine bands on the bottom book, page edges on the second
    for x in (121, 128):
        c.vl(x, 121, 122, "gold_m")
    c.rect(129, 118, 130, 119, "cream_m")
    c.hl(129, 130, 119, "cream_d")
    c.hl(123, 127, 115, "cream_l")
    c.hl(123, 127, 112, "cream_m")
    return c


def _book(c, x, yb, w, h, r):
    hi, mid, lo, _ = RAMP[r]
    top = yb - h + 1
    c.rect(x, top, x + w - 1, yb, mid)
    if w >= 3:
        c.vl(x, top, yb, hi)
    c.vl(x + w - 1, top, yb, lo)
    c.hl(x, x + w - 1, top, hi)
    if h >= 6:
        c.hl(x, x + w - 1, yb - 2, "cream_m" if r != "cream" else "terra_m")   # spine label


def prop_study_3() -> Cv:
    """tall bookshelf (far right) full of muted books, a small globe on top"""
    c = Cv()
    floor_shadow(c, 165, 191, 99)
    c.vl(191, 56, 98, "sage_d")
    c.paint(R(164, 54, 190, 98), "pine")
    shelves = [
        [(3, 7, "terra"), (2, 6, "cream"), (3, 7, "blue"), (2, 7, "gold"), (3, 6, "moss"), (2, 7, "plum"), (3, 7, "terra"), (2, 5, "teal")],
        [(2, 6, "plum"), (3, 7, "cream"), (2, 7, "moss"), (3, 6, "terra"), (2, 7, "blue"), (3, 5, "gold")],
        [(3, 7, "blue"), (2, 6, "gold"), (2, 7, "plum"), (3, 7, "moss"), (2, 5, "terra"), (3, 6, "cream")],
        [(3, 6, "terra"), (3, 7, "plum"), (2, 7, "blue"), (3, 6, "gold"), (2, 5, "moss"), (3, 7, "cream"), (2, 6, "teal")],
    ]
    for k, seq in enumerate(shelves):
        y0 = 57 + 10 * k
        yb = y0 + 7
        c.rect(167, y0, 187, yb, "floor_d")                # back panel
        c.hl(167, 187, y0, "floor_dd")                     # shade under the board above
        c.vl(167, y0, yb, "floor_dd")
        x = 168
        for (w, h, r) in seq:
            _book(c, x, yb, w, h, r)
            x += w
        if k < 3:
            c.hl(165, 189, yb + 1, "pine_l")               # divider top (light) and underside
            c.hl(165, 189, yb + 2, "pine_d")
    # lying books + a tiny plant on the shelves
    _book_flat = lambda xa, xb, yb, r: (c.rect(xa, yb - 1, xb, yb, RAMP[r][1]), c.hl(xa, xb, yb - 1, RAMP[r][0]))
    _book_flat(183, 187, 74, "terra")
    _book_flat(184, 187, 72, "moss")
    c.paint(R(183, 81, 186, 84), "terra")
    c.pts({(184, 79), (185, 80), (183, 80), (184, 80), (186, 79), (185, 79)}, "moss_m")
    c.pts({(184, 79), (185, 79)}, "moss_l")
    # globe on top: sphere, two continents, gold meridian arc on the left, small base
    c.pts({p for p in E(173, 48, 5.8, 5.8) - E(173, 48, 4.7, 4.7) if p[0] <= 172 and p[1] >= 45}, "gold_m")
    c.paint(D(173, 48, 4), "blue")
    c.pts({(171, 46), (172, 46), (171, 47), (172, 47), (175, 49), (176, 49), (175, 50), (174, 50)}, "moss_m")
    c.pts({(171, 46), (172, 46)}, "moss_l")
    c.pts({(171, 53), (172, 53), (173, 53), (174, 53), (175, 53)}, "gold_d")
    c.pts({(172, 53), (173, 53)}, "gold_m")
    return c


def prop_social_1() -> Cv:
    """framed photo on the wall, a tiny two-person silhouette inside"""
    c = Cv()
    c.vl(134, 38, 53, "sage_d")
    c.hl(116, 134, 53, "sage_d")
    c.paint(R(114, 36, 133, 52), "pine")
    c.rect(117, 39, 130, 49, "cream_l")
    c.hl(117, 130, 39, "cream_m")
    c.vl(117, 39, 49, "cream_m")
    c.rect(118, 40, 129, 48, "sky_m")
    c.rect(118, 46, 129, 48, "moss_m")
    c.hl(118, 129, 46, "moss_l")
    # person A (taller) and person B
    c.rect(121, 41, 123, 41, "floor_dd")
    c.rect(121, 42, 123, 43, "terra_l")
    c.rect(120, 44, 124, 48, "blue_m")
    c.vl(124, 44, 48, "blue_d")
    c.rect(126, 43, 128, 43, "floor_d")
    c.rect(126, 44, 128, 45, "terra_l")
    c.rect(125, 46, 129, 48, "terra_m")
    c.vl(129, 46, 48, "terra_d")
    c.put(121, 42, "floor_dd")
    return c


def prop_social_2() -> Cv:
    """potted plant on the floor, right of the character"""
    c = Cv()
    floor_shadow(c, 135, 147, 120)
    # oval leaves, back to front: (cx, cy, half length, half width, angle)
    for (cx, cy, rx, ry, th) in [(136, 108, 4.2, 2.8, 20), (144, 108, 4.2, 2.8, -20),
                                 (136, 101, 5.6, 3.0, 55), (144, 101, 5.6, 3.0, -55),
                                 (137.5, 96, 3.8, 2.3, 62), (143, 95, 3.6, 2.3, -66),
                                 (140, 98.5, 8.0, 2.8, -90)]:
        c.paint(E(cx, cy, rx, ry, th), "moss")
    c.pts({(140, 94), (140, 96), (140, 98), (140, 100)}, "moss_l")   # centre vein
    c.paint(R(134, 111, 145, 113), "terra")               # rim
    c.paint(P([(135, 114), (144, 114), (143, 119), (136, 119)]), "terra")
    c.hl(136, 143, 112, "terra_l")
    return c


def _swag(x0, x1, y0, sag):
    """wire points of a sagging string between two hooks"""
    pts = []
    for x in range(x0, x1 + 1):
        t = (x - x0) / (x1 - x0)
        pts.append((x, round(y0 + sag * (1 - (2 * t - 1) ** 2))))
    return pts


BULBS = []        # (x, y) of every string-light bulb, also used by the lighting overlay
RUG = (96, 116, 20, 7)     # round rug under the feet: centre x, y, radii


def prop_social_3() -> Cv:
    """round rug under the feet, floor lamp, string of warm lights along the top of the wall"""
    c = Cv()
    BULBS.clear()
    # rug
    rug = E(*RUG)
    B = {p for p in rug if any((p[0] + dx, p[1] + dy) not in rug for dx, dy in N4)}
    for (x, y) in rug:
        d = math.hypot((x - RUG[0]) / RUG[2], (y - RUG[1]) / RUG[3])
        if (x, y) in B:
            k = "terra_d"
        elif d > 0.80:
            k = "terra_m"
        elif d > 0.70:
            k = "cream_l"
        elif d > 0.52:
            k = "terra_l"
        else:
            k = "cream_m"
        c.put(x, y, k)
    # floor lamp
    floor_shadow(c, 149, 159, 108)
    c.vl(152, 58, 104, "gold_m")
    c.vl(153, 58, 104, "gold_d")
    c.vl(152, 58, 64, "gold_l")
    c.paint(R(149, 105, 156, 107), "gold")
    c.put(151, 106, "gold_l")
    c.paint(P([(149, 46), (156, 46), (159, 57), (146, 57)]), "shade")
    c.vl(150, 49, 55, "cream_l")
    c.rect(152, 44, 153, 45, "gold_d")
    # string lights: three swags along the top of the wall
    for (xa, xb) in ((5, 69), (70, 128), (129, 187)):
        wire = _swag(xa, xb, 6, 7)
        c.pts(wire, "floor_dd")
        for hx in (xa, xb):
            c.rect(hx, 5, hx, 6, "gold_d")
        n = 7
        for i in range(n):
            bx, by = wire[int((i + 0.5) * len(wire) / n)]
            BULBS.append((bx, by + 2))
            c.put(bx, by + 1, "gold_d")
            c.put(bx, by + 2, "gold_l")
            c.put(bx + 1, by + 2, "gold_m")
            c.put(bx, by + 3, "gold_m")
            c.put(bx + 1, by + 3, "gold_d")
    return c


def make_lighting() -> Cv:
    """warm overlay for social_3: soft banded glow, strongest at the lamp shade, alpha <= 35%"""
    c = Cv()
    colr = (255, 176, 92)
    lamp = (152.5, 52.0)
    bayer = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))   # 4x4 ordered dither
    amax = int(0.35 * 255)                      # 89
    steps = 7
    for y in range(H):
        for x in range(W):
            d = math.hypot(x - lamp[0], (y - lamp[1]) * 1.25)
            f = max(0.0, 1 - d / 92.0) ** 1.5
            for (bx, by) in BULBS:
                db = math.hypot(x - bx, y - by)
                f = max(f, 0.55 * max(0.0, 1 - db / 7.0) ** 1.2)
            a = (0.20 + 0.80 * f) * amax * (1.0 if y < 100 else 0.9)
            lvl = int(a / amax * steps + (bayer[y % 4][x % 4] + 0.5) / 16)
            alpha = min(amax, round(lvl * amax / steps))
            if alpha > 0:
                c.px[x, y] = colr + (alpha,)
    return c


# ------------------------------------------------------------ icons + fx ---
# Category icons use the UI category colours.
CAT = {
    "sport": ("#e8895f", "#d0613a", "#a4472a", "#6e2c1a"),
    "work": ("#6a9bcb", "#3f73a8", "#2e5582", "#1e3652"),
    "study": ("#a287c8", "#7d5ea6", "#5c4382", "#3a2a55"),
    "social": ("#e386a5", "#c4587c", "#9a3d5c", "#64233b"),
}
PAPER = ("#fffaf0", "#f3ead2", "#d3c49c", "#6e4a2d")


def icon_cat_sport() -> Cv:
    c = Cv(16, 16)
    rows = ["................",
            "................",
            "..dddd....dddd..",
            "..dhhd....dhhd..",
            "dddhmd....dhmddd",
            "dhdhmd....dhmdmd",
            "dhdhmddddddhmdmd",
            "dhdhmdhmmmdhmdmd",
            "dhdhmdmmmldhmdmd",
            "dhdhmddddddhmdmd",
            "dhdhmd....dhmdmd",
            "dddhmd....dhmddd",
            "..dlld....dlld..",
            "..dddd....dddd..",
            "................",
            "................"]
    h, m, l, d = CAT["sport"]
    c.art(rows, 0, 0, dict(d=d, h=h, m=m, l=l))
    return c


def icon_cat_work() -> Cv:
    c = Cv(16, 16)
    rows = ["................",
            "................",
            "....dddddddd....",
            "....dh....md....",
            "....dh....md....",
            "." + "d" * 14 + ".",
            ".d" + "h" * 12 + "d.",
            ".dh" + "m" * 11 + "d.",
            ".d" + "l" * 4 + "GGGG" + "l" * 4 + "d.",
            ".dh" + "mmm" + "gkkg" + "mmmm" + "d.",
            ".dh" + "mmm" + "gggg" + "mmmm" + "d.",
            ".dh" + "m" * 11 + "d.",
            ".d" + "l" * 12 + "d.",
            "." + "d" * 14 + ".",
            "................",
            "................"]
    h, m, l, d = CAT["work"]
    c.art(rows, 0, 0, dict(d=d, h=h, m=m, l=l, G="#f6d36a", g="#e0a82e", k="#a8741a"))
    return c


def icon_cat_study() -> Cv:
    c = Cv(16, 16)
    c.paint(P([(0, 5), (7, 7), (8, 7), (15, 5), (15, 12), (8, 14), (7, 14), (0, 12)]), CAT["study"])
    c.paint(P([(2, 2), (7, 4), (7, 12), (2, 10)]), PAPER[:3] + (CAT["study"][3],))
    c.paint(P([(13, 2), (8, 4), (8, 12), (13, 10)]), PAPER[:3] + (CAT["study"][3],))
    for x0 in (3, 9):                                       # text lines on both pages
        for (y, w) in ((5, 4), (8, 4), (10, 3)):
            c.hl(x0, x0 + w - 1, y, CAT["study"][0])
    c.vl(7, 5, 13, CAT["study"][3])
    c.vl(8, 5, 13, CAT["study"][2])
    return c


def icon_cat_social() -> Cv:
    c = Cv(16, 16)
    heart = D(4.5, 5.5, 4.2) | D(10.5, 5.5, 4.2) | P([(1, 7), (14, 7), (8, 14), (7, 14)])
    c.paint(heart, CAT["social"])
    c.pts({(3, 4), (4, 3), (3, 5), (4, 4)}, "#f6b3c8")
    return c


def icon_unlock_sport_1() -> Cv:
    c = Cv(16, 16)
    c.art(DUMBBELL, 0, 0, DUMBBELL_LEG)
    c.art(DUMBBELL, 1, 8, DUMBBELL_LEG)
    return c


def icon_unlock_sport_2() -> Cv:
    c = Cv(16, 16)
    c.paint(P([(1, 3), (6, 3), (7, 6), (11, 7), (14, 9), (15, 11), (15, 12), (1, 12)]), PAPER)
    c.paint(R(1, 12, 15, 14), PAPER)
    c.hl(2, 14, 13, CAT["sport"][1])
    c.paint(R(1, 3, 3, 6), CAT["sport"])
    c.pts(LN(4, 8, 9, 10) | LN(4, 9, 9, 11), CAT["sport"][1])
    c.pts({(7, 6), (8, 7), (9, 7), (10, 8)}, "floor_dd")
    return c


def icon_unlock_sport_3() -> Cv:
    c = Cv(16, 16)
    c.paint(P([(3, 0), (7, 0), (10, 8), (6, 8)]), CAT["sport"])
    c.paint(P([(12, 0), (8, 0), (5, 8), (9, 8)]), CAT["work"])
    c.paint(D(8, 11, 4.4), "gold")
    c.paint(D(8, 11, 2.2), ("gold_m", "gold_m", "gold_l", "gold_d"))
    c.put(8, 11, "gold_l")
    return c


def icon_unlock_work_1() -> Cv:
    c = Cv(16, 16)
    c.paint(R(2, 2, 13, 10), "metal")
    c.rect(4, 4, 11, 8, "cream_l")
    c.hl(5, 8, 5, "sky_m")
    c.hl(5, 10, 7, "sky_m")
    c.paint(P([(0, 11), (15, 11), (14, 14), (1, 14)]), "metal")
    c.hl(3, 12, 12, "metal_l")
    return c


def icon_unlock_work_2() -> Cv:
    c = Cv(16, 16)
    c.paint(P([(2, 3), (5, 1), (7, 2), (9, 2), (11, 1), (14, 3), (15, 6), (14, 14), (2, 14), (1, 6)]), "blue")
    c.paint(P([(6, 2), (10, 2), (8, 8)]), PAPER[:3] + ("blue_d",))
    c.pts(LN(5, 2, 8, 9) | LN(10, 2, 8, 9), "blue_d")
    c.pts({(4, 3), (5, 4), (6, 5)}, "blue_l")
    c.vl(8, 9, 14, "blue_d")
    c.pts({(7, 11), (7, 13)}, "gold_m")
    c.pts(LN(4, 7, 4, 13) | LN(12, 7, 12, 13), "blue_d")
    return c


def icon_unlock_work_3() -> Cv:
    c = Cv(16, 16)
    c.paint(P([(0, 1), (7, 1), (7, 6)]), PAPER)
    c.paint(P([(15, 1), (8, 1), (8, 6)]), PAPER)
    c.paint(R(6, 1, 9, 4), "blue")
    c.paint(P([(6, 5), (9, 5), (11, 12), (8, 15), (4, 12)]), "blue")
    c.pts(LN(6, 8, 10, 8) | LN(6, 11, 9, 11), "blue_l")
    return c


def icon_unlock_study_1() -> Cv:
    c = Cv(16, 16)
    for i, (xa, xb, r) in enumerate([(1, 14, "terra"), (2, 14, "moss"), (1, 12, "gold")]):
        yb = 14 - 4 * i
        c.paint(R(xa, yb - 4, xb, yb), r)
    c.rect(11, 6, 12, 8, "cream_m")
    c.vl(13, 6, 8, "moss_d")
    c.pts({(3, 11), (3, 12), (4, 11), (4, 12)}, "gold_m")
    c.hl(4, 9, 3, "cream_l")
    return c


def icon_unlock_study_2() -> Cv:
    c = Cv(16, 16)
    for cx in (4.5, 11.5):
        c.paint(D(cx, 8, 4.4), "plum")
        c.pts(D(cx, 8, 2.4), "sky_m")
        c.put(int(cx) - 1, 7, "cream_l")
    c.pts({(7, 7), (8, 7), (7, 8), (8, 8)}, "plum_d")
    c.pts({(0, 6), (1, 6), (14, 6), (15, 6), (0, 5), (15, 5)}, "plum_d")
    return c


def icon_unlock_study_3() -> Cv:
    c = Cv(16, 16)
    c.paint(R(1, 1, 14, 14), "pine")
    seq = [[(2, 6, "terra"), (2, 5, "cream"), (2, 6, "blue"), (2, 6, "gold")], [(2, 5, "plum"), (2, 6, "moss"), (3, 5, "terra"), (2, 4, "cream")]]
    for k, row in enumerate(seq):
        y0 = 3 + 6 * k
        c.rect(3, y0, 12, y0 + 5, "floor_d")
        c.hl(3, 12, y0, "floor_dd")
        x = 4
        for (w, h, r) in row:
            _book(c, x, y0 + 5, w, min(h, 5), r)
            x += w
    c.hl(2, 13, 9, "pine_l")
    return c


def icon_unlock_social_1() -> Cv:
    c = Cv(16, 16)
    c.paint(R(0, 1, 15, 14), "pine")
    c.rect(3, 4, 12, 11, "sky_m")
    c.rect(3, 10, 12, 11, "moss_m")
    c.rect(5, 5, 6, 6, "terra_l")
    c.rect(4, 7, 7, 11, "blue_m")
    c.rect(9, 6, 10, 7, "terra_l")
    c.rect(8, 8, 11, 11, "terra_m")
    c.vl(7, 7, 11, "blue_d")
    c.vl(11, 8, 11, "terra_d")
    c.hl(3, 12, 3, "floor_d")
    c.vl(3, 4, 11, "floor_d")
    return c


def icon_unlock_social_2() -> Cv:
    c = Cv(16, 16)
    for (cx, cy, rx, ry, th) in [(4.5, 8, 3.4, 2.4, 20), (11.5, 8, 3.4, 2.4, -20), (5.5, 4.5, 4.4, 2.5, 55),
                                 (10.5, 4.5, 4.4, 2.5, -55), (8, 5, 5.5, 2.7, -90)]:
        c.paint(E(cx, cy, rx, ry, th), "moss")
    c.paint(R(3, 10, 12, 11), "terra")
    c.paint(P([(4, 12), (11, 12), (10, 15), (5, 15)]), "terra")
    return c


def icon_unlock_social_3() -> Cv:
    c = Cv(16, 16)
    c.vl(7, 8, 13, "gold_m")
    c.vl(8, 8, 13, "gold_d")
    c.paint(P([(5, 1), (10, 1), (13, 8), (2, 8)]), "shade")
    c.vl(5, 3, 6, "cream_l")
    c.paint(R(4, 13, 11, 15), "gold")
    return c


STAR = ["...a...",
        "...b...",
        "..bcb..",
        "abcccba",
        "..bcb..",
        "...b...",
        "...a..."]
SPARK = ["..a..",
         "..w..",
         "awwwa",
         "..w..",
         "..a.."]
HEART = [".hp.pp.",
         "hpppppd",
         "ppppppd",
         "ppppppd",
         ".pppdd.",
         "..pdd..",
         "...d..."]


def fx_star() -> Cv:
    c = Cv(7, 7)
    c.art(STAR, 0, 0, dict(a="#d99a24", b="#f0c040", c="#fff4b8"))
    return c


def fx_spark() -> Cv:
    c = Cv(5, 5)
    c.art(SPARK, 0, 0, dict(a="#f3ecd8", w="#ffffff"))
    return c


def fx_heart() -> Cv:
    c = Cv(7, 7)
    c.art(HEART, 0, 0, dict(h="#f4a0b8", p="#d9608a", d="#a8406a"))
    return c


ICONS = {
    "cat_sport": icon_cat_sport, "cat_work": icon_cat_work, "cat_study": icon_cat_study, "cat_social": icon_cat_social,
    "unlock_sport_1": icon_unlock_sport_1, "unlock_sport_2": icon_unlock_sport_2, "unlock_sport_3": icon_unlock_sport_3,
    "unlock_work_1": icon_unlock_work_1, "unlock_work_2": icon_unlock_work_2, "unlock_work_3": icon_unlock_work_3,
    "unlock_study_1": icon_unlock_study_1, "unlock_study_2": icon_unlock_study_2, "unlock_study_3": icon_unlock_study_3,
    "unlock_social_1": icon_unlock_social_1, "unlock_social_2": icon_unlock_social_2, "unlock_social_3": icon_unlock_social_3,
}
FX = {"star": fx_star, "spark": fx_spark, "heart": fx_heart}


# ------------------------------------------------------- layout + output ---
# id: (builder, layer, order). 'back' is drawn before the character, 'front' after.
PROPS = {
    "sport_3": (prop_sport_3, "back", 10),
    "work_1": (prop_work_1, "back", 20),
    "study_3": (prop_study_3, "back", 30),
    "social_1": (prop_social_1, "back", 40),
    "social_3": (prop_social_3, "back", 50),
    "sport_1": (prop_sport_1, "front", 10),
    "work_3": (prop_work_3, "front", 20),
    "study_1": (prop_study_1, "front", 30),
    "social_2": (prop_social_2, "front", 40),
}


def verify(bg: Cv, props: dict, light: Cv) -> bool:
    """layout rules: no overlaps, character box free, palette size"""
    ok = True
    sets = {k: v.opaque() for k, v in props.items()}
    for k, cv in props.items():
        soft = sum(1 for y in range(H) for x in range(W) if cv.px[x, y][3] not in (0, 255))
        if soft:
            ok = False
            print(f"FAIL {k}: {soft} semi-transparent pixels")
    names = list(props)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            inter = sets[a] & sets[b]
            if inter:
                ok = False
                print(f"FAIL overlap {a} x {b}: {len(inter)} px, e.g. {sorted(inter)[:4]}")
    fx0, fy0, fx1, fy1 = FIG
    box = {(x, y) for x in range(fx0, fx1 + 1) for y in range(fy0, fy1 + 1)}
    rug = E(*RUG)
    for k, s in sets.items():
        hit = s & box
        if k == "social_3":
            hit -= rug
        if hit:
            ok = False
            print(f"FAIL {k} intrudes into the character box: {len(hit)} px, e.g. {sorted(hit)[:4]}")
    cx, cy, cw, ch = CROP
    if not (cx <= fx0 and fx1 < cx + cw and cy <= fy0 and fy1 < cy + ch):
        ok = False
        print("FAIL compact_crop does not contain the character box")
    amax = max(light.px[x, y][3] for y in range(H) for x in range(W))
    print(f"lighting max alpha {amax}/255 = {amax / 255:.0%}")
    if amax > 0.36 * 255:
        ok = False
        print("FAIL lighting too strong")
    comp = bg.im.copy()
    for cv in props.values():
        comp.alpha_composite(cv.im)
    n = len(comp.getcolors(1 << 16))
    print(f"unique colours in the all-unlocked scene (no lighting): {n}")
    for k, (_, layer, order) in PROPS.items():
        xs = [p[0] for p in sets[k]]
        ys = [p[1] for p in sets[k]]
        print(f"  {k:9s} {layer:5s} {order:2d}  bbox x {min(xs)}..{max(xs)}  y {min(ys)}..{max(ys)}")
    return ok


def manifest_text() -> str:
    """room.json layout (props listed in draw order)"""
    order = sorted(PROPS.items(), key=lambda kv: (kv[1][1] != "back", kv[1][2]))
    props = ",\n".join(
        f'    "{pid}": {json.dumps({"file": f"room/props/{pid}.png", "layer": layer, "order": o})}'
        for pid, (_, layer, o) in order)
    return ("{\n"
            f'  "scene": {json.dumps([W, H])},\n'
            f'  "character_anchor": {json.dumps(list(ANCHOR))},\n'
            f'  "floor_y": {FLOOR_Y},\n'
            f'  "compact_crop": {json.dumps(list(CROP))},\n'
            '  "background": "room/background.png",\n'
            '  "props": {\n' + props + "\n  },\n"
            '  "lighting": {"social_3": "room/lighting_warm.png"}\n'
            "}\n")


def main() -> int:
    room = SPR / "room"
    bg = make_background()
    bg.save(room / "background.png")
    props = {}
    for pid, (fn, layer, order) in PROPS.items():
        cv = fn()
        cv.save(room / "props" / f"{pid}.png")
        props[pid] = cv
    light = make_lighting()
    light.save(room / "lighting_warm.png")
    (room / "room.json").write_text(manifest_text(), encoding="utf-8")
    small = {}
    for name, fn in ICONS.items():
        small[("icons", name)] = fn()
    for name, fn in FX.items():
        small[("fx", name)] = fn()
    sizes = {"icons": (16, 16), "star": (7, 7), "spark": (5, 5), "heart": (7, 7)}
    ok = True
    for (folder, name), cv in small.items():
        cv.save(SPR / folder / f"{name}.png")
        want = sizes["icons"] if folder == "icons" else sizes[name]
        soft = [p for p in ((x, y) for y in range(cv.h) for x in range(cv.w)) if cv.px[p][3] not in (0, 255)]
        if (cv.w, cv.h) != want or soft or not cv.opaque():
            ok = False
            print(f"FAIL {folder}/{name}: size {(cv.w, cv.h)} want {want}, soft px {len(soft)}")
    ok = verify(bg, props, light) and ok
    print("layout OK" if ok else "LAYOUT PROBLEMS")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
