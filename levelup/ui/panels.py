"""Блоки основного окна: стадия и ближайшая награда, «Развитие», календарь."""
from __future__ import annotations

from datetime import date

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..config import AppConfig
from ..domain.models import Snapshot
from .summary import nearest_reward, plural, points_text, reward_text, stage_progress
from .theme import (
    FONT_BODY, FONT_SMALL, GOLD, INK, INK_2, PIXEL_TEXT, enlarge, make_label, paint_box, pixel_face, sprite,
    unlock_icon,
)
from .widgets import CalendarGrid, CategoryRow, Panel, PixelBar, Rule


class StageBadge(QWidget):
    """Золотой квадрат с номером стадии (пиксельный шрифт)."""

    SIZE = 40

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._number = 1
        self.setFixedSize(self.SIZE, self.SIZE)

    def number(self) -> int:
        return self._number

    def set_number(self, number: int) -> None:
        self._number = number
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        paint_box(p, self.rect(), GOLD)
        p.setFont(pixel_face(PIXEL_TEXT))
        p.setPen(QColor(INK))
        p.drawText(QRect(0, 0, self.width(), self.height() - 2), Qt.AlignmentFlag.AlignCenter, str(self._number))


class StageHud(Panel):
    """Стадия, полоска очков и ближайшая награда: подпись к сцене."""

    def __init__(self, config: AppConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self._config = config
        self.body.setSpacing(4)
        self.badge = StageBadge()
        self.caption = make_label("", FONT_SMALL, color=INK_2)
        self.name_label = make_label("", PIXEL_TEXT, pixel=True)
        self.xp_label = make_label("", PIXEL_TEXT, pixel=True)
        self.bar = PixelBar()
        self.bar.setAccessibleName("Очки до следующей стадии")
        self.next_label = make_label("", FONT_SMALL, color=INK_2)
        self.reward_icon = QLabel()
        self.reward_icon.setFixedSize(32, 32)
        self.reward_caption = make_label("Ближайшая награда", FONT_SMALL, color=INK_2)
        self.reward_label = make_label("", FONT_BODY, wrap=True)

        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(self.caption)
        names.addWidget(self.name_label)
        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(self.badge)
        top.addLayout(names)
        top.addStretch(1)
        top.addWidget(self.xp_label, 0, Qt.AlignmentFlag.AlignBottom)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        texts.addWidget(self.reward_caption)
        texts.addWidget(self.reward_label)
        reward = QHBoxLayout()
        reward.setSpacing(12)
        reward.addWidget(self.reward_icon, 0, Qt.AlignmentFlag.AlignVCenter)
        reward.addLayout(texts, 1)

        self.body.addLayout(top)
        self.body.addSpacing(4)
        self.body.addWidget(self.bar)
        self.body.addWidget(self.next_label)
        self.body.addSpacing(4)
        self.body.addWidget(Rule())
        self.body.addSpacing(4)
        self.body.addLayout(reward)

    def apply(self, snap: Snapshot, animate: bool = True) -> None:
        progress = stage_progress(snap, self._config)
        self.badge.set_number(snap.stage)
        self.caption.setText(f"Стадия {snap.stage} из {snap.stage_count}")
        self.name_label.setText(snap.stage_name)
        self.bar.set_progress(progress.value, progress.maximum, animate)
        if progress.next_name is None:
            self.xp_label.setText(points_text(snap.total_xp))
            self.next_label.setText("Это последняя стадия — очки продолжают копиться")
        else:
            self.xp_label.setText(f"{snap.total_xp} / {snap.next_threshold}")
            self.next_label.setText(f"до стадии «{progress.next_name}»: {snap.xp_to_next}")
        reward = nearest_reward(snap, self._config)
        icon = enlarge(unlock_icon(reward.unlock.id), 2) if reward else enlarge(sprite("star", "fx"), 4)
        self.reward_icon.setPixmap(icon)
        self.reward_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.reward_label.setText(reward_text(reward))
        self.setAccessibleName(f"Стадия {snap.stage} из {snap.stage_count}: {snap.stage_name}")


class DevelopmentSection(QWidget):
    """«Развитие»: четыре строки по категориям."""

    def __init__(self, config: AppConfig, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(make_label("Развитие", PIXEL_TEXT, pixel=True))
        self.rows = {c.id: CategoryRow(c, config) for c in config.categories}
        for row in self.rows.values():
            layout.addWidget(row)

    def apply(self, snap: Snapshot, animate: bool = True) -> None:
        for view in snap.categories:
            if view.id in self.rows:
                self.rows[view.id].apply(view, animate)


class CalendarSection(QWidget):
    """«Дни без пропусков»: пять недель, полные дни закрашены."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        self.title = make_label("Дни без пропусков", FONT_BODY, bold=True)
        self.summary = make_label("", FONT_SMALL, color=INK_2, wrap=True)
        self.grid = CalendarGrid()
        texts = QVBoxLayout()
        texts.setSpacing(4)
        texts.addWidget(self.title)
        texts.addWidget(self.summary)
        texts.addStretch(1)
        layout.addLayout(texts, 1)
        layout.addWidget(self.grid, 0, Qt.AlignmentFlag.AlignTop)

    def apply(self, snap: Snapshot) -> None:
        self.grid.set_data(date.fromisoformat(snap.date), snap.full_days)
        full = self.grid.full_count()
        self.summary.setText(
            f"За пять недель: {full} {plural(full, ('полный день', 'полных дня', 'полных дней'))}. "
            "День полный, когда выполнены все привычки."
        )
        self.grid.setAccessibleName(f"Календарь: {full} полных дней за пять недель")
