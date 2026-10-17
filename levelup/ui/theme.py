"""Тема «уютная комната»: шрифты, пиксельные иконки, примитивы рисования и стили Qt.

Всё рисуется без сглаживания и целыми пикселями: контур 2 px цвета ink, углы «лесенкой» вместо скругления,
иконки и спрайты увеличиваются только целым множителем и без интерполяции. Размеры шрифта: системного — 12 / 14,
пиксельного — 10 / 20 / 30 (он чёткий только при кегле, кратном 10, см. palette.pixel_font); отступы кратны 4.
"""
from __future__ import annotations

import logging
from functools import cache

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPalette, QPixmap, QPolygon, QRegion
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from ..config import ASSETS_DIR
from .palette import (  # noqa: F401 — цвета реэкспортируются окнам
    BG, BRICK, CATEGORY_COLORS, GOLD, GOLD_DARK, INK, INK_2, LINE_SOFT, MOSS, MOSS_DARK, PANEL, SUNKEN, pixel_font,
)

log = logging.getLogger("levelup.ui")

SPRITES_DIR = ASSETS_DIR / "sprites"
BORDER = 2
FONT_SMALL, FONT_BODY = 12, 14  # системный шрифт: подписи и основной текст
PIXEL_SMALL, PIXEL_TEXT, PIXEL_BRAND = 10, 20, 30  # пиксельный шрифт: мелкие подписи, заголовки/стадия/числа, название
SANS_FAMILIES = ["Segoe UI", "Noto Sans", "Ubuntu", "DejaVu Sans"]
KEYBOARD_REASONS = (
    Qt.FocusReason.TabFocusReason,
    Qt.FocusReason.BacktabFocusReason,
    Qt.FocusReason.ShortcutFocusReason,
)


# ---------------------------------------------------------------------- шрифты и подписи
def ui_font(size: int = FONT_BODY, bold: bool = False) -> QFont:
    """Системный шрифт без засечек для всего, кроме названия, стадий и чисел."""
    font = QFont()
    font.setFamilies(SANS_FAMILIES)
    font.setPixelSize(size)
    font.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
    return font


def pixel_face(size: int) -> QFont:
    """Пиксельный шрифт без сглаживания: края букв остаются чёткими (в том числе с ClearType на Windows)."""
    font = pixel_font(size)
    font.setStyleStrategy(QFont.StyleStrategy.NoAntialias)
    return font


def make_label(
    text: str = "",
    size: int = FONT_BODY,
    *,
    pixel: bool = False,
    bold: bool = False,
    color: str = INK,
    wrap: bool = False,
    parent: QWidget | None = None,
) -> QLabel:
    label = QLabel(text, parent)
    label.setFont(pixel_face(size) if pixel else ui_font(size, bold))
    set_text_color(label, color)
    label.setWordWrap(wrap)
    return label


def set_text_color(widget: QWidget, color: str) -> None:
    palette = widget.palette()
    palette.setColor(QPalette.ColorRole.WindowText, QColor(color))
    widget.setPalette(palette)


# ---------------------------------------------------------------------- пиксельные примитивы
def _corner(cut: int) -> list[tuple[int, int]]:
    points = [(0, cut)]
    for i in range(cut):
        points += [(i + 1, cut - i), (i + 1, cut - i - 1)]
    return points


def stair_polygon(rect: QRect, cut: int = 2) -> QPolygon:
    """Прямоугольник, у которого углы срезаны лесенкой в `cut` пикселей (радиус скругления 0..2)."""
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    tl = _corner(cut)
    points = [(x + a, y + b) for a, b in tl]
    points += [(x + w - a, y + b) for a, b in reversed(tl)]
    points += [(x + w - a, y + h - b) for a, b in tl]
    points += [(x + a, y + h - b) for a, b in reversed(tl)]
    return QPolygon([QPoint(a, b) for a, b in points])


def paint_box(
    p: QPainter, rect: QRect, fill: str | None, outline: str = INK, border: int = BORDER, cut: int = 2
) -> None:
    """Плоская заливка с контуром `border` px и углами лесенкой; без сглаживания."""
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(outline))
    p.drawPolygon(stair_polygon(rect, cut))
    if fill is not None:
        p.setBrush(QColor(fill))
        p.drawRect(rect.adjusted(border, border, -border, -border))


def dotted_line(p: QPainter, x1: int, x2: int, y: int, color: str = LINE_SOFT) -> None:
    for x in range(x1, x2, 2):
        p.fillRect(x, y, 1, 1, QColor(color))


def corner_mask(width: int, height: int, cut: int = 2) -> QRegion:
    """Маска окна без рамки: срезанные углы без полупрозрачности (работает и без композитинга)."""
    return QRegion(stair_polygon(QRect(0, 0, width, height), cut))


def text_width(font: QFont, text: str) -> int:
    return QFontMetrics(font).horizontalAdvance(text)


# ---------------------------------------------------------------------- пиксельные иконки
@cache
def sprite(name: str, folder: str = "icons") -> QPixmap:
    """Картинка из sprites/<folder>; нет файла — пустая (интерфейс работает дальше)."""
    pixmap = QPixmap(str(SPRITES_DIR / folder / f"{name}.png"))
    if pixmap.isNull():
        log.warning("code=ASSET_MISSING op=load_icon detail=%s/%s", folder, name)
    return pixmap


def category_icon(category_id: str) -> QPixmap:
    return sprite(f"cat_{category_id}")


def unlock_icon(unlock_id: str) -> QPixmap:
    return sprite(f"unlock_{unlock_id}")


def enlarge(pixmap: QPixmap, factor: int) -> QPixmap:
    """Целочисленное увеличение «ближайшим соседом»."""
    return pixmap.scaled(
        pixmap.width() * factor,
        pixmap.height() * factor,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.FastTransformation,
    )


@cache
def locked_icon(name: str) -> QPixmap:
    """Серая полупрозрачная версия иконки для ещё не открытого предмета."""
    image = sprite(name).toImage().convertToFormat(QImage.Format.Format_ARGB32)
    for y in range(image.height()):
        for x in range(image.width()):
            c = image.pixelColor(x, y)
            grey = round(0.3 * c.red() + 0.59 * c.green() + 0.11 * c.blue())
            image.setPixelColor(x, y, QColor(grey, grey, grey, c.alpha() // 2))
    return QPixmap.fromImage(image)


def icon_label(pixmap: QPixmap, factor: int = 1, parent: QWidget | None = None) -> QLabel:
    label = QLabel(parent)
    big = enlarge(pixmap, factor)
    label.setPixmap(big)
    label.setFixedSize(big.size())
    label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    return label


# Мелкие пиксельные картинки, нарисованные кодом: '#' — основной цвет, 'o' — внешний, 'i' — внутренний.
TICK = ("......#", ".....##", "#...##.", "##.##..", ".###...", "..#....")
FLAME = (
    "...o...",
    "..oo...",
    "..ooo.o",
    ".ooooo.",
    ".ooiioo",
    "ooiiioo",
    "ooiiioo",
    ".oiiio.",
    "..ooo..",
)


def draw_bitmap(p: QPainter, rows: tuple[str, ...], x: int, y: int, scale: int, colors: dict[str, str]) -> None:
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch in colors:
                p.fillRect(x + i * scale, y + j * scale, scale, scale, QColor(colors[ch]))


def bitmap_size(rows: tuple[str, ...], scale: int) -> tuple[int, int]:
    return len(rows[0]) * scale, len(rows) * scale


# ---------------------------------------------------------------------- тема приложения
def app_palette() -> QPalette:
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: BG,
        QPalette.ColorRole.WindowText: INK,
        QPalette.ColorRole.Base: PANEL,
        QPalette.ColorRole.AlternateBase: SUNKEN,
        QPalette.ColorRole.Text: INK,
        QPalette.ColorRole.Button: PANEL,
        QPalette.ColorRole.ButtonText: INK,
        QPalette.ColorRole.ToolTipBase: PANEL,
        QPalette.ColorRole.ToolTipText: INK,
        QPalette.ColorRole.Highlight: GOLD,
        QPalette.ColorRole.HighlightedText: INK,
        QPalette.ColorRole.PlaceholderText: INK_2,
        QPalette.ColorRole.Light: PANEL,
        QPalette.ColorRole.Mid: LINE_SOFT,
        QPalette.ColorRole.Dark: INK_2,
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(LINE_SOFT))
    return palette


_QSS = """
QToolTip { background: @panel; color: @ink; border: 2px solid @ink; padding: 4px 8px; }
QMenu { background: @panel; border: 2px solid @ink; padding: 4px; }
QMenu::item { padding: 8px 20px; }
QMenu::item:selected { background: @gold; color: @ink; }
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: @sunken; width: 12px; margin: 0; border-left: 2px solid @line; }
QScrollBar::handle:vertical { background: @panel; border: 2px solid @ink; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: @gold; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QPlainTextEdit {
    background: @panel; border: 2px solid @ink; padding: 8px; selection-background-color: @gold; selection-color: @ink;
}
QLineEdit { background: transparent; border: none; padding: 0 8px; selection-background-color: @gold; selection-color: @ink; }
QComboBox { background: transparent; border: none; padding: 0 32px 0 10px; }
QComboBox::drop-down { width: 0; border: none; }
QComboBox::down-arrow { image: none; width: 0; }
QComboBox QAbstractItemView {
    background: @panel; border: 2px solid @ink; outline: 0; selection-background-color: @gold; selection-color: @ink;
}
QMessageBox QPushButton { background: @panel; border: 2px solid @ink; padding: 6px 16px; min-width: 64px; }
QMessageBox QPushButton:default { background: @gold; }
QMessageBox QPushButton:pressed { background: @sunken; }
"""
_COLOR_NAMES = {"ink": INK, "panel": PANEL, "sunken": SUNKEN, "line": LINE_SOFT, "gold": GOLD}


def stylesheet() -> str:
    qss = _QSS
    for name, value in _COLOR_NAMES.items():
        qss = qss.replace(f"@{name}", value)
    return qss


def apply_theme(app: QApplication) -> None:
    """Fusion + тёплая палитра + шрифт + стили; вызывается один раз при создании QApplication."""
    app.setStyle("Fusion")
    app.setFont(ui_font())
    app.setPalette(app_palette())
    app.setStyleSheet(stylesheet())
