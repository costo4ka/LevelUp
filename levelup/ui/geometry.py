"""Положение виджета относительно экранов (чистая логика, без Qt-виджетов)."""
from __future__ import annotations

from dataclasses import dataclass

MARGIN = 24


@dataclass(frozen=True)
class ScreenArea:
    name: str
    x: int
    y: int
    w: int
    h: int
    primary: bool = False

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h


def _fit(value: int, low: int, size: int, span: int) -> int:
    return max(low, min(value, low + span - size))


def normalize_position(
    x: int | None,
    y: int | None,
    w: int,
    h: int,
    screens: list[ScreenArea],
    preferred_name: str | None = None,
) -> tuple[int, int, str | None]:
    """Возвращает (x, y, имя_экрана), при которых окно целиком в доступной области.

    Нет сохранённой позиции — правый нижний угол основного экрана. Центр окна вне всех экранов
    (монитор отключён) — возвращаем на сохранённый монитор, если он есть, иначе на основной.
    """
    if not screens:
        return (x or 0), (y or 0), None
    primary = next((s for s in screens if s.primary), screens[0])
    if x is None or y is None:
        return (
            _fit(primary.x + primary.w - w - MARGIN, primary.x, w, primary.w),
            _fit(primary.y + primary.h - h - MARGIN, primary.y, h, primary.h),
            primary.name,
        )
    target = next((s for s in screens if s.contains(x + w // 2, y + h // 2)), None)
    if target is None:
        target = next((s for s in screens if preferred_name and s.name == preferred_name), primary)
    return _fit(x, target.x, w, target.w), _fit(y, target.y, h, target.h), target.name


def current_screens() -> list[ScreenArea]:
    from PyQt6.QtGui import QGuiApplication

    primary = QGuiApplication.primaryScreen()
    areas = []
    for screen in QGuiApplication.screens():
        g = screen.availableGeometry()
        areas.append(ScreenArea(screen.name(), g.x(), g.y(), g.width(), g.height(), screen is primary))
    return areas
