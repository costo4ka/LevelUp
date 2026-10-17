"""Общая палитра и шрифты: единый источник цветов для темы, сцены и виджетов."""
from __future__ import annotations

import logging

from PyQt6.QtGui import QFont, QFontDatabase

from ..config import ASSETS_DIR

log = logging.getLogger("levelup.ui")

INK = "#2a211c"
INK_2 = "#6b5a4d"
BG = "#e6dcc3"
PANEL = "#f5eedd"
SUNKEN = "#ddd0b3"
LINE_SOFT = "#bfae8c"
MOSS = "#5a8a4a"
MOSS_DARK = "#3f6636"
GOLD = "#e0a82e"
GOLD_DARK = "#a8741a"
BRICK = "#a83d33"  # чуть темнее исходного #b5443a: контраст текста ошибок на bg 3,99 -> 4,55
CATEGORY_COLORS = {"sport": "#d0613a", "work": "#3f73a8", "study": "#7d5ea6", "social": "#c4587c"}

PIXEL_FILE = "ArkPixel10-Latin.ttf"  # Ark Pixel Font 10px proportional (SIL OFL): честная кириллица в пиксельном стиле
PIXEL_UNIT = 10  # родной размер шрифта: кегль кратен 10 (10, 20, 30), иначе пиксели «плывут»
_FALLBACK_FAMILY = "Sans Serif"
_loaded_family: str | None = None


def load_fonts() -> str:
    """Подключает пиксельный шрифт из assets/fonts (один раз); возвращает имя семейства."""
    global _loaded_family
    if _loaded_family is None:
        family = _FALLBACK_FAMILY
        font_id = QFontDatabase.addApplicationFont(str(ASSETS_DIR / "fonts" / PIXEL_FILE))
        if font_id >= 0 and (families := QFontDatabase.applicationFontFamilies(font_id)):
            family = families[0]
        else:
            log.warning("code=ASSET_MISSING op=load_fonts detail=%s", PIXEL_FILE)
        _loaded_family = family
    return _loaded_family


def pixel_font(pixel_size: int) -> QFont:
    """Пиксельный шрифт для названия, стадии, чисел и подписей. Размер в пикселях округляется до кратного 10."""
    font = QFont(load_fonts())
    font.setPixelSize(max(PIXEL_UNIT, int(pixel_size / PIXEL_UNIT + 0.5) * PIXEL_UNIT))
    return font
