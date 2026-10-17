"""Коллекция: стадии героя и 12 предметов комнаты по категориям; закрытые — серые, с подсказкой «Ещё N отметок»."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPalette
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from ..config import AppConfig
from ..domain.models import Snapshot
from .about import AboutDialog
from .summary import marks_phrase, points_text
from .theme import (
    FONT_BODY, FONT_SMALL, GOLD_DARK, INK, INK_2, LINE_SOFT, MOSS_DARK, PANEL, PIXEL_TEXT, category_icon, icon_label,
    locked_icon, make_label, paint_box, unlock_icon,
)
from .widgets import Panel, PixelButton, paint_tick_box


class StatusBox(QWidget):
    """Квадрат 20x20: с галочкой — выполнено, пустой — ещё нет."""

    def __init__(self, done: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.done = done
        self.setFixedSize(20, 20)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        if self.done:
            paint_tick_box(p, self.rect())
        else:
            paint_box(p, self.rect(), PANEL, LINE_SOFT, cut=1)


class StageRow(QWidget):
    def __init__(
        self, number: int, name: str, threshold: int, reached: bool, current: bool, parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.number, self.reached, self.current = number, reached, current
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        color = INK if reached else INK_2
        self.name_label = make_label(f"{number}  {name}", PIXEL_TEXT, pixel=True, color=color)
        status = "сейчас" if current else f"с {points_text(threshold)}"
        self.status_label = make_label(status, FONT_SMALL, bold=current, color=MOSS_DARK if current else INK_2)
        layout.addWidget(StatusBox(reached))
        layout.addWidget(self.name_label, 1)
        layout.addWidget(self.status_label)
        self.setFixedHeight(28)


class ItemRow(QWidget):
    def __init__(
        self, config: AppConfig, category_id: str, index: int, unlocked: bool, left: int, parent: QWidget | None = None
    ):
        super().__init__(parent)
        category = config.category(category_id)
        unlock = category.unlocks[index]
        self.unlock_id, self.unlocked = unlock.id, unlocked
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        icon = locked_icon(f"unlock_{unlock.id}") if not unlocked else unlock_icon(unlock.id)
        self.name_label = make_label(unlock.name, FONT_BODY, bold=True, color=INK if unlocked else INK_2)
        self.hint_label = make_label(unlock.hint, FONT_SMALL, color=INK_2, wrap=True)
        self.status_label = make_label(
            "" if unlocked else marks_phrase(left, category.name), FONT_SMALL, bold=True, color=INK
        )
        texts = QVBoxLayout()
        texts.setSpacing(0)
        texts.addWidget(self.name_label)
        texts.addWidget(self.hint_label)
        if not unlocked:
            texts.addWidget(self.status_label)
        layout.addWidget(icon_label(icon, 2), 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(texts, 1)
        layout.addWidget(StatusBox(unlocked), 0, Qt.AlignmentFlag.AlignTop)


class CollectionDialog(QDialog):
    def __init__(self, snap: Snapshot, config: AppConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Коллекция")
        self.setModal(True)
        self.resize(560, 660)
        self.setMinimumSize(480, 420)
        self.stage_rows: list[StageRow] = []
        self.item_rows: dict[str, ItemRow] = {}

        content = QWidget()
        content.setAutoFillBackground(True)
        palette = content.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(PANEL))
        content.setPalette(palette)
        column = QVBoxLayout(content)
        column.setContentsMargins(20, 16, 20, 16)
        column.setSpacing(8)
        column.addWidget(make_label("Стадии героя", PIXEL_TEXT, pixel=True))
        for number, (name, threshold) in enumerate(zip(config.stage_names, config.stage_thresholds), start=1):
            row = StageRow(number, name, threshold, snap.stage >= number, snap.stage == number)
            self.stage_rows.append(row)
            column.addWidget(row)
        column.addSpacing(8)
        column.addWidget(make_label("Предметы комнаты", PIXEL_TEXT, pixel=True))
        for category in config.categories:
            view = snap.category(category.id)
            points = view.points if view else 0
            column.addSpacing(8)
            tier = view.tier if view else 0
            column.addLayout(self._group_header(category.id, category.name, points, tier, len(category.unlocks)))
            for index, unlock in enumerate(category.unlocks):
                unlocked = unlock.id in snap.unlocked
                left = max(0, config.category_tiers[index] - points)
                row = ItemRow(config, category.id, index, unlocked, left)
                self.item_rows[unlock.id] = row
                column.addWidget(row)
        column.addStretch(1)

        scroll = QScrollArea()
        scroll.setStyleSheet(  # рамка фокуса прокрутки: клавиатурные стрелки листают список
            "QScrollArea { border: 2px solid transparent; } "
            f"QScrollArea:focus {{ border: 2px solid {GOLD_DARK}; }}"
        )
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        frame = Panel(margins=(2, 2, 2, 2))
        frame.body.addWidget(scroll)

        self.about_btn = PixelButton("О программе")
        close = PixelButton("Закрыть", "primary")
        close.setDefault(True)
        footer = QHBoxLayout()
        footer.setSpacing(8)
        footer.addWidget(self.about_btn)
        footer.addStretch(1)
        footer.addWidget(close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(8)
        layout.addWidget(make_label("Коллекция", PIXEL_TEXT, pixel=True))
        layout.addWidget(make_label("Что уже открыто в комнате и что ждёт впереди.", FONT_SMALL, color=INK_2))
        layout.addSpacing(4)
        layout.addWidget(frame, 1)
        layout.addSpacing(4)
        layout.addLayout(footer)
        close.clicked.connect(self.accept)
        close.setFocus()  # первый фокус не на списке, чтобы вокруг него не горела рамка фокуса
        self.about_btn.clicked.connect(lambda: AboutDialog(self).exec())

    @staticmethod
    def _group_header(category_id: str, name: str, points: int, tier: int, total: int) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(icon_label(category_icon(category_id), 2))
        row.addWidget(make_label(name, PIXEL_TEXT, pixel=True))
        row.addWidget(make_label(f"{points_text(points)} · открыто {tier} из {total}", FONT_SMALL, color=INK_2), 1)
        return row
