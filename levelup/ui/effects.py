"""Пиксельные эффекты сцены: кэш спрайтов и текста, шкала времени и сами эффекты.

Всё считается в логических пикселях сцены (192x128) и рисуется через преобразование целого масштаба,
поэтому спрайты не размываются. Состояние эффекта — чистая функция локального времени t (мс): кадры не
зависят от частоты таймера, а tick() в тестах детерминирован. Плавность только там, где она нужна
(движение); прозрачность и вспышки идут ступенями или дизерингом.
"""
from __future__ import annotations

import functools
import logging
import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QBitmap, QBrush, QColor, QFont, QFontMetrics, QImage, QPainter, QRegion

from . import palette

log = logging.getLogger("levelup.ui")

STEPS = 4  # ступеней дизеринга: 0 — ничего, STEPS — целиком
WHITE = palette.PANEL  # «белый» вспышек: самый светлый цвет палитры
_BAYER = ((0, 0), (1, 1), (1, 0), (0, 1))  # порядок заполнения клетки 2x2 по ступеням
PROBE = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя0123456789+-:!«»"  # всё, что рисуем
_ARGB = QImage.Format.Format_ARGB32_Premultiplied


def out_cubic(u: float) -> float:
    return 1 - (1 - u) ** 3


def parabola(u: float) -> float:
    return 4 * u * (1 - u)


def steps(left: float, fade: float) -> float:
    """Остаток жизни (1..0) → прозрачность четвертями: целиком до порога fade, затем 1, 0.75, 0.5, 0.25."""
    return math.ceil(min(1.0, max(0.0, left) / fade) * STEPS) / STEPS


def pop_scale(u: float) -> float:
    """Появление предмета: 0 → 1.15 → 1."""
    if u >= 1:
        return 1.0
    if u < 0.6:
        return 1.15 * out_cubic(u / 0.6)
    x = (u - 0.6) / 0.4
    return 1.15 - 0.15 * x * x * (3 - 2 * x)


@functools.lru_cache(maxsize=64)
def circle(r: int) -> tuple[tuple[int, int], ...]:
    """Точки окружности радиуса r (алгоритм средней точки), без повторов."""
    points: set[tuple[int, int]] = set()
    x, y, err = r, 0, 1 - r
    while x >= y:
        points.update(((x, y), (y, x), (-y, x), (-x, y), (-x, -y), (-y, -x), (y, -x), (x, -y)))
        y += 1
        if err < 0:
            err += 2 * y + 1
        else:
            x -= 1
            err += 2 * (y - x) + 1
    return tuple(sorted(points))


class Metrics(NamedTuple):
    cap: int  # высота заглавных, px
    desc: int  # глубина нижних выносных, px
    lead: int  # строк от верха картинки текста до верха заглавных: поле под контур и место под «Ё», «Й»


class SpriteBank:
    """Кэш картинок: PNG, силуэты, дизеринг, пиксельный текст. Нет файла — рисуется «ничего», в журнал один раз."""

    LIMIT = 400

    def __init__(self, root: Path):
        self.root = root  # каталог sprites/ (fx/, icons/)
        self._png: dict[Path, QImage] = {}
        self._derived: dict[tuple, QImage] = {}
        self._missing: set[Path] = set()
        self._metrics: dict[int, Metrics] = {}

    def image(self, path: Path) -> QImage:
        if path not in self._png:
            image = QImage(str(path))
            if image.isNull():
                if path not in self._missing:
                    self._missing.add(path)
                    log.warning("code=ASSET_MISSING op=scene_image detail=%s", path.name)
            else:
                image = image.convertToFormat(_ARGB)
            self._png[path] = image
        return self._png[path]

    def fx(self, name: str) -> QImage:
        return self.image(self.root / "fx" / f"{name}.png")

    def icon(self, name: str) -> QImage:
        return self.image(self.root / "icons" / f"{name}.png")

    def memo(self, key: tuple, make: Callable[[], QImage]) -> QImage:
        image = self._derived.get(key)
        if image is None:
            if len(self._derived) >= self.LIMIT:
                self._derived.clear()
            image = self._derived[key] = make()
        return image

    def stack(self, files: Sequence[Path], size: tuple[int, int]) -> QImage:
        """Склеивает PNG одного размера в одну картинку."""

        def make() -> QImage:
            image = QImage(size[0], size[1], _ARGB)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            for path in files:
                painter.drawImage(0, 0, self.image(path))
            painter.end()
            return image

        return self.memo(("stack", tuple(files), size), make)

    @staticmethod
    def bbox(image: QImage) -> QRect:
        """Рамка непрозрачных пикселей (пустая у пустой картинки)."""
        if image.isNull():
            return QRect()
        return QRegion(QBitmap.fromImage(image.createAlphaMask())).boundingRect()

    def silhouette(self, image: QImage, color: str = WHITE) -> QImage:
        def make() -> QImage:
            out = image.copy()
            painter = QPainter(out)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(out.rect(), QColor(color))
            painter.end()
            return out

        return self.memo(("sil", image.cacheKey(), color), make)

    def tile(self, level: int, color: str = "#000000") -> QImage:
        """Клетка 2x2 для дизеринга: level из 4 пикселей закрашено."""

        def make() -> QImage:
            tile = QImage(2, 2, _ARGB)
            tile.fill(Qt.GlobalColor.transparent)
            for x, y in _BAYER[:level]:
                tile.setPixelColor(x, y, QColor(color))
            return tile

        return self.memo(("tile", level, color), make)

    def dithered(self, image: QImage, level: int) -> QImage | None:
        """Картинка, оставленная на level/STEPS упорядоченным дизерингом (None — ничего не видно)."""
        if level <= 0 or image.isNull():
            return None
        if level >= STEPS:
            return image

        def make() -> QImage:
            mask = QImage(image.size(), _ARGB)
            mask.fill(Qt.GlobalColor.transparent)
            painter = QPainter(mask)
            painter.fillRect(mask.rect(), QBrush(self.tile(level)))
            painter.end()
            out = image.copy()
            painter = QPainter(out)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            painter.drawImage(0, 0, mask)
            painter.end()
            return out

        return self.memo(("dither", image.cacheKey(), level), make)

    @staticmethod
    def _font(size: int) -> QFont:
        font = palette.pixel_font(size)  # Ark Pixel рисуется на сетке 10 px: годятся только кегли 10 и 20
        font.setStyleStrategy(QFont.StyleStrategy.NoAntialias)
        font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
        return font

    def metrics(self, size: int) -> Metrics:
        """Размеры строки этого кегля: меряются по настоящим глифам, а не по таблицам шрифта."""
        if size not in self._metrics:
            font = self._font(size)
            fm = QFontMetrics(font)
            base = 2 + fm.ascent()
            probe = QImage(fm.horizontalAdvance(PROBE) + 4, fm.height() + 4, _ARGB)

            def ink(text: str) -> QRect:
                probe.fill(Qt.GlobalColor.transparent)
                painter = QPainter(probe)
                painter.setFont(font)
                painter.drawText(2, base, text)
                painter.end()
                return self.bbox(probe)

            cap, box = ink("Н").height(), ink(PROBE)
            self._metrics[size] = Metrics(cap, box.bottom() + 1 - base, 1 + base - box.top() - cap)
        return self._metrics[size]

    def width(self, text: str, size: int) -> int:
        """Ширина строки по шрифту (с пикселем промежутка после последней буквы)."""
        return QFontMetrics(self._font(size)).horizontalAdvance(text)

    def wrap(self, text: str, limit: int, size: int) -> list[str]:
        """Перенос по словам под ширину limit; слово, не влезающее само, рубится по буквам."""
        lines: list[str] = []
        for word in text.split():
            if lines and self.width(f"{lines[-1]} {word}", size) <= limit:
                lines[-1] += f" {word}"
                continue
            while len(word) > 1 and self.width(word, size) > limit:
                cut = max((n for n in range(1, len(word)) if self.width(word[:n], size) <= limit), default=1)
                lines.append(word[:cut])
                word = word[cut:]
            lines.append(word)
        return lines or [""]

    def text(self, text: str, color: str, size: int, outline: str | None = None) -> QImage:
        """Строка пиксельным шрифтом в масштабе сцены: верх заглавных на строке lead, слева поле 1 px под контур."""

        def make() -> QImage:
            m = self.metrics(size)
            image = QImage(self.width(text, size) + 1, m.lead + m.cap + m.desc + 1, _ARGB)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setFont(self._font(size))
            base = m.lead + m.cap
            if outline:
                painter.setPen(QColor(outline))
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        painter.drawText(1 + dx, base + dy, text)
            painter.setPen(QColor(color))
            painter.drawText(1, base, text)
            painter.end()
            return image

        return self.memo(("text", text, color, size, outline), make)


@dataclass
class Frame:
    """Что эффекты делают с персонажем на этом кадре."""

    lift: float = 0.0  # подъём над полом, px
    pulse: float = 1.0  # масштаб от ступней
    flash: int = 0  # ступень белой вспышки, 0..STEPS


class Effect:
    """Эффект на шкале времени: живёт [delay, delay + duration) мс, слой отрисовки задаёт layer."""

    layer = "fx"  # back/front — на слое предметов, light — освещение, fx — частицы, hud — плашки

    def __init__(self, delay: float, duration: float = 0.0):
        self.delay, self.duration = delay, duration
        self.started = False

    @property
    def end(self) -> float:
        return self.delay + self.duration

    def begin(self) -> None:
        """Один раз, когда время дошло до delay."""

    def apply(self, t: float, frame: Frame) -> None:
        """Влияние на персонажа."""

    def paint(self, p: QPainter, t: float, bank: SpriteBank) -> None:
        """Рисование в координатах сцены; t — локальное время, bank — кэш спрайтов."""


class Timeline:
    def __init__(self, effects: Sequence[Effect] = ()):
        self.effects = sorted(effects, key=lambda e: e.delay)
        self.time = 0.0

    @property
    def active(self) -> bool:
        return bool(self.effects)

    def advance(self, ms: float) -> None:
        self.time += ms
        self._run(False)

    def skip(self) -> None:
        """Мгновенно проходит всё оставшееся (действия-метки выполняются по порядку)."""
        self._run(True)

    def _run(self, everything: bool) -> None:
        for effect in list(self.effects):
            if not effect.started and (everything or self.time >= effect.delay):
                effect.started = True
                effect.begin()
            if everything or self.time >= effect.end:
                self.effects.remove(effect)

    def frame(self) -> Frame:
        frame = Frame()
        for effect in self.effects:
            if effect.started:
                effect.apply(self.time - effect.delay, frame)
        return frame

    def paint(self, p: QPainter, layer: str, bank: SpriteBank) -> None:
        for effect in self.effects:
            if effect.started and effect.layer == layer:
                effect.paint(p, min(self.time - effect.delay, effect.duration), bank)


class Cue(Effect):
    """Мгновенное действие в заданный момент: смена вида, показ предмета."""

    def __init__(self, delay: float, action: Callable[[], None]):
        super().__init__(delay)
        self.action = action

    def begin(self) -> None:
        self.action()


class Hop(Effect):
    """Прыжок персонажа по параболе; тень остаётся на полу."""

    def __init__(self, delay: float, height: float, duration: float):
        super().__init__(delay, duration)
        self.height = height

    def apply(self, t: float, frame: Frame) -> None:
        frame.lift += self.height * parabola(min(1.0, t / self.duration))


class Flash(Effect):
    """Белая вспышка персонажа (дизерингом, ступень за ступенью) и необязательный пульс."""

    def __init__(self, delay: float, duration: float, pulse: float = 0.0, peak: int = STEPS):
        super().__init__(delay, duration)
        self.pulse, self.peak = pulse, peak

    def apply(self, t: float, frame: Frame) -> None:
        u = min(1.0, t / self.duration)
        frame.flash = max(frame.flash, round(self.peak * (1 - u)))
        frame.pulse *= 1 + self.pulse * math.sin(math.pi * u)


class Stars(Effect):
    """Звёзды из головы: баллистика с гравитацией, затем ступенчатое угасание."""

    GRAVITY = 150.0  # px/с²

    def __init__(self, delay: float, origin: tuple[float, float], rng: random.Random, life: float = 900.0):
        super().__init__(delay, life + 100)
        self.parts = []
        for _ in range(rng.randint(6, 10)):
            angle, speed = math.radians(rng.uniform(-155, -25)), rng.uniform(42, 78)
            self.parts.append((
                origin[0] + rng.uniform(-4, 4), origin[1] + rng.uniform(-3, 2),
                speed * math.cos(angle), speed * math.sin(angle), rng.uniform(0, 100), life * rng.uniform(0.72, 1.0),
            ))

    def paint(self, p: QPainter, t: float, bank: SpriteBank) -> None:
        star = bank.fx("star")
        for x0, y0, vx, vy, start, life in self.parts:
            age = t - start
            if 0 <= age < life:
                s = age / 1000
                p.setOpacity(steps(1 - age / life, 0.4))
                p.drawImage(round(x0 + vx * s) - 3, round(y0 + vy * s + self.GRAVITY * s * s / 2) - 3, star)
        p.setOpacity(1.0)


class Float(Effect):
    """Всплывающая надпись (с иконкой слева): поднимается и гаснет ступенями."""

    def __init__(self, delay: float, x: int, y: int, text: QImage, m: Metrics, icon: QImage | None = None,
                 rise: int = 14, duration: float = 1000.0):
        super().__init__(delay, duration)
        icon = None if icon is None or icon.isNull() else icon  # нет файла иконки — надпись без неё
        gap = icon.width() + 2 if icon is not None else 0
        self.y, self.rise, self.icon, self.text = y, rise, icon, text
        self.left = x - (gap + text.width() - 2) // 2
        self.text_dx = gap - 1
        self.text_dy = ((icon.height() if icon is not None else m.cap) - m.cap) // 2 - m.lead

    def paint(self, p: QPainter, t: float, bank: SpriteBank) -> None:
        u = t / self.duration
        y = self.y - round(self.rise * out_cubic(u))
        p.setOpacity(steps(1 - u, 0.45))
        if self.icon is not None:
            p.drawImage(self.left, y, self.icon)
        p.drawImage(self.left + self.text_dx, y + self.text_dy, self.text)
        p.setOpacity(1.0)


class Pop(Effect):
    """Предмет «выскакивает»: масштаб 0 → 1.15 → 1 от нижнего центра рамки, в начале белая вспышка."""

    def __init__(self, delay: float, image: QImage, box: QRect, layer: str, duration: float = 450.0):
        super().__init__(delay, duration)
        self.image, self.box, self.layer = image, box, layer

    def paint(self, p: QPainter, t: float, bank: SpriteBank) -> None:
        u = t / self.duration
        k, box = pop_scale(u), self.box
        w, h = round(box.width() * k), round(box.height() * k)
        if w < 1 or h < 1:
            return
        target = QRect(round(box.x() + box.width() / 2 - w / 2), box.y() + box.height() - h, w, h)
        p.drawImage(target, self.image)
        glow = bank.dithered(bank.silhouette(self.image), round(STEPS * (1 - u / 0.45)))
        if glow is not None:
            p.drawImage(target, glow)


class Fade(Effect):
    """Картинка проявляется или растворяется: дизерингом по ступеням, а плавно — только для света."""

    def __init__(self, delay: float, duration: float, image: QImage, pos: QPoint, layer: str,
                 reverse: bool = False, smooth: bool = False):
        super().__init__(delay, duration)
        self.image, self.pos, self.layer, self.reverse, self.smooth = image, pos, layer, reverse, smooth

    def paint(self, p: QPainter, t: float, bank: SpriteBank) -> None:
        u = t / self.duration
        k = u if self.reverse else 1 - u
        if self.smooth:
            p.setOpacity(k)
            p.drawImage(self.pos, self.image)
            p.setOpacity(1.0)
        elif (shown := bank.dithered(self.image, round(k * STEPS))) is not None:
            p.drawImage(self.pos, shown)


class Sparkles(Effect):
    """Россыпь искр вокруг рамки: разлетаются, мерцают (целая → маленькая → нет)."""

    def __init__(self, delay: float, box: QRect, rng: random.Random, count: int = 8, life: float = 520.0):
        super().__init__(delay, 200 + life)
        cx, cy = box.x() + box.width() / 2, box.y() + box.height() / 2
        reach = math.hypot(box.width(), box.height()) / 2
        self.life, self.parts = life, []
        for i in range(count):
            angle = 2 * math.pi * (i + rng.uniform(-0.3, 0.3)) / count
            r0, start = reach * 0.55 + rng.uniform(2, 8), rng.uniform(0, 200)
            self.parts.append((cx, cy, math.cos(angle), math.sin(angle), r0, start))

    def paint(self, p: QPainter, t: float, bank: SpriteBank) -> None:
        spark = bank.fx("spark")
        for cx, cy, dx, dy, r0, start in self.parts:
            u = (t - start) / self.life
            if 0 <= u < 0.85:
                r = r0 + 9 * out_cubic(u)
                x, y = round(cx + dx * r) - 2, round(cy + dy * r) - 2
                if u < 0.6:
                    p.drawImage(x, y, spark)
                else:
                    p.drawImage(QRect(x + 1, y + 1, 3, 3), spark, QRect(1, 1, 3, 3))


class Puff(Effect):
    """Облачко пыли: квадратики 3 → 2 → 1 px разлетаются и пропадают."""

    COLORS = (palette.PANEL, palette.LINE_SOFT)

    def __init__(self, delay: float, center: tuple[float, float], rng: random.Random, count: int = 7,
                 life: float = 480.0):
        super().__init__(delay, life)
        self.center, self.parts = center, []
        for i in range(count):
            angle = 2 * math.pi * (i + rng.uniform(-0.3, 0.3)) / count
            self.parts.append((math.cos(angle), math.sin(angle), rng.uniform(8, 14), QColor(self.COLORS[i % 2])))

    def paint(self, p: QPainter, t: float, bank: SpriteBank) -> None:
        u = t / self.duration
        size = 3 if u < 0.4 else 2 if u < 0.75 else 1
        for dx, dy, reach, color in self.parts:
            r = reach * out_cubic(u)
            p.fillRect(round(self.center[0] + dx * r), round(self.center[1] + dy * r - 5 * u), size, size, color)


class Ring(Effect):
    """Расширяющееся пиксельное кольцо (смена стадии): сначала толщиной 2 px, затем 1, гаснет ступенями."""

    def __init__(self, delay: float, center: tuple[int, int], r0: int, r1: int, color: str, duration: float = 650.0):
        super().__init__(delay, duration)
        self.center, self.r0, self.r1, self.color = center, r0, r1, QColor(color)

    def paint(self, p: QPainter, t: float, bank: SpriteBank) -> None:
        u = t / self.duration
        r = round(self.r0 + (self.r1 - self.r0) * out_cubic(u))
        p.setOpacity(steps(1 - u, 0.5))
        for radius in (r, r - 1) if u < 0.5 else (r,):
            for dx, dy in circle(radius):
                p.fillRect(self.center[0] + dx, self.center[1] + dy, 1, 1, self.color)
        p.setOpacity(1.0)


class Confetti(Effect):
    """Квадратики конфетти сыплются сверху кадра, ложатся на пол и мигают напоследок."""

    REST = 0.3  # сколько секунд лежит

    def __init__(self, delay: float, crop: QRect, floor: tuple[int, int], rng: random.Random, colors: Sequence[str],
                 count: int = 24, duration: float = 1900.0):
        super().__init__(delay, duration)
        top = crop.y() - 3
        self.parts = []
        for _ in range(count):
            speed, land = rng.uniform(110, 145), rng.randint(max(floor[0], top + 20), floor[1])
            self.parts.append((
                rng.randint(crop.x() + 10, crop.right() - 12), top, speed, land, rng.uniform(0, 0.45),
                rng.uniform(0, 6.3), rng.choice((2, 3, 3, 4)), QColor(rng.choice(colors)),
            ))

    def paint(self, p: QPainter, t: float, bank: SpriteBank) -> None:
        for x0, y0, speed, land, start, phase, size, color in self.parts:
            s = t / 1000 - start
            if s < 0:
                continue
            fall = (land - y0) / speed
            if s < fall:
                p.fillRect(round(x0 + 2 * math.sin(6 * s + phase)), round(y0 + speed * s), size, size, color)
            elif s < fall + self.REST and (s < fall + 0.18 or int((s - fall) * 24) % 2 == 0):
                p.fillRect(round(x0 + 2 * math.sin(6 * fall + phase)), land, size, size, color)


def panel(p: QPainter, x: int, y: int, w: int, h: int, border: str, fill: str) -> None:
    """Плоская панель: контур 1 px, срезанные угловые пиксели, без теней."""
    p.fillRect(x + 1, y, w - 2, h, QColor(border))
    p.fillRect(x, y + 1, w, h - 2, QColor(border))
    p.fillRect(x + 2, y + 1, w - 4, h - 2, QColor(fill))
    p.fillRect(x + 1, y + 2, w - 2, h - 4, QColor(fill))


class Banner(Effect):
    """Плашка сверху кадра: выезжает, держится, уезжает. Иконка слева, текст справа или по центру.

    Ширина плашки — по настоящей ширине текста, длинная строка переносится по словам под видимый кадр.
    """

    layer = "hud"
    IN, HOLD, OUT = 220.0, 1600.0, 200.0
    TOTAL = IN + HOLD + OUT
    MARGIN, PAD_X, PAD_Y, GAP, GAP_LINES, LABEL_SIZE = 4, 4, 3, 4, 2, 10

    def __init__(self, delay: float, bank: SpriteBank, crop: QRect, size: int, text: str, label: str | None = None,
                 icon: QImage | None = None, zoom: int = 1, centered: bool = False):
        super().__init__(delay, self.TOTAL)
        icon = None if icon is None or icon.isNull() else icon
        self.crop, self.icon, self.centered = crop, icon, centered
        self.icon_w, self.icon_h = (icon.width() * zoom, icon.height() * zoom) if icon is not None else (0, 0)
        self.gap = self.GAP if icon is not None else 0
        pad = 2 * self.PAD_X - 1  # справа на пиксель меньше: после последней буквы шрифт и так оставляет промежуток
        limit = crop.width() - 2 * self.MARGIN - 2 - pad - self.icon_w - self.gap
        wrapped = bank.wrap(text, limit, size)
        lines = []  # длинное название, перенесённое на две строки, идёт без подписи
        if label and len(wrapped) == 1:
            lines.append((label, palette.INK_2, self.LABEL_SIZE))
        lines += [(line, palette.INK, size) for line in wrapped]
        self.rows, top = [], 0  # (картинка, где её верх относительно текстового блока, ширина строки)
        for line, color, row_size in lines:
            m = bank.metrics(row_size)
            self.rows.append((bank.text(line, color, row_size), top - m.lead, bank.width(line, row_size)))
            top += m.cap + m.desc + self.GAP_LINES
        self.text_w, self.text_h = max(row[2] for row in self.rows), top - self.GAP_LINES
        self.w = 2 + pad + self.icon_w + self.gap + self.text_w
        self.h = 2 + 2 * self.PAD_Y + max(self.icon_h, self.text_h)

    def y_at(self, t: float) -> int:
        rest, hidden = self.crop.y() + 3, self.crop.y() - self.h
        if t < self.IN:
            return round(hidden + (rest - hidden) * out_cubic(t / self.IN))
        if t < self.IN + self.HOLD:
            return rest
        u = (t - self.IN - self.HOLD) / self.OUT
        return round(rest + (hidden - rest) * u * u * u)

    def paint(self, p: QPainter, t: float, bank: SpriteBank) -> None:
        x, y = self.crop.x() + (self.crop.width() - self.w) // 2, self.y_at(t)
        panel(p, x, y, self.w, self.h, palette.INK, palette.PANEL)
        inner_h, left = self.h - 2, x + 1 + self.PAD_X
        if self.icon is not None:
            p.drawImage(QRect(left, y + 1 + (inner_h - self.icon_h) // 2, self.icon_w, self.icon_h), self.icon)
        text_x, text_y = left + self.icon_w + self.gap, y + 1 + (inner_h - self.text_h) // 2
        for image, dy, advance in self.rows:
            dx = (self.text_w - advance) // 2 if self.centered else 0
            p.drawImage(text_x + dx - 1, text_y + dy, image)
