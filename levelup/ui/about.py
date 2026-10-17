"""«О программе»: версия, авторы спрайтов (CREDITS.md как простой текст), лицензия шрифта."""
from __future__ import annotations

import logging

from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QPlainTextEdit, QVBoxLayout, QWidget

from .. import __version__
from ..config import ASSETS_DIR
from .theme import FONT_BODY, FONT_SMALL, INK_2, PIXEL_BRAND, icon_label, make_label, sprite
from .widgets import PixelButton

log = logging.getLogger("levelup.ui")

CREDITS_PATH = ASSETS_DIR / "sprites" / "character" / "CREDITS.md"
FONT_CREDIT = "Шрифт Ark Pixel Font © TakWolf, лицензия SIL Open Font License 1.1 (github.com/TakWolf/ark-pixel-font)"
SPRITE_NOTE = (
    "Герой собран из слоёв Universal LPC Spritesheet Character Generator (Liberated Pixel Cup). "
    "Изображения изменены: вырезан один кадр и перекрашены цвета. Лицензии CC-BY-SA 3.0, OGA-BY 3.0 и CC0 "
    "требуют указания авторов; полный список и условия — в тексте ниже."
)


def read_credits() -> str:
    try:
        return CREDITS_PATH.read_text(encoding="utf-8")
    except OSError:
        log.warning("code=ASSET_MISSING op=read_credits detail=%s", CREDITS_PATH.name)
        return "Файл CREDITS.md не найден. Он лежит рядом со спрайтами героя: levelup/assets/sprites/character/."


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("О программе")
        self.setModal(True)
        self.resize(640, 600)
        self.setMinimumSize(480, 420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(icon_label(sprite("star", "fx"), 3))
        head.addWidget(make_label("LevelUp", PIXEL_BRAND, pixel=True))
        head.addStretch(1)
        self.version = make_label(f"Версия {__version__}", FONT_SMALL, color=INK_2)
        head.addWidget(self.version)
        layout.addLayout(head)
        layout.addWidget(
            make_label(
                "Привычки, которые обставляют комнату. Все данные хранятся только на этом компьютере. "
                "Комната, предметы, значки и эффекты нарисованы специально для LevelUp.",
                FONT_BODY,
                wrap=True,
            )
        )
        layout.addSpacing(8)
        layout.addWidget(make_label("Спрайты героя", FONT_BODY, bold=True))
        layout.addWidget(make_label(SPRITE_NOTE, FONT_SMALL, color=INK_2, wrap=True))

        self.credits = QPlainTextEdit()
        self.credits.setReadOnly(True)
        self.credits.setAccessibleName("Авторы и лицензии спрайтов")
        font = QFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        font.setPixelSize(FONT_SMALL)
        self.credits.setFont(font)
        self.credits.setPlainText(read_credits())
        layout.addWidget(self.credits, 1)

        self.font_credit = make_label(FONT_CREDIT, FONT_SMALL, color=INK_2, wrap=True)
        layout.addWidget(self.font_credit)
        close = PixelButton("Закрыть", "primary")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        close.setFocus()
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)
