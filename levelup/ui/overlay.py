"""Оверлей: компактный виджет поверх окон. Показывает то же состояние и вызывает те же команды."""
from __future__ import annotations

from PyQt6.QtCore import QPoint, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QPainter, QShortcut
from PyQt6.QtWidgets import QHBoxLayout, QLayout, QVBoxLayout, QWidget

from ..domain.models import RewardEvent, Snapshot
from .geometry import current_screens, normalize_position
from .scene import SceneWidget
from .summary import CLOCK_WARNING_SHORT, DAY_DONE_TEXT, category_label, points_text, stage_progress, streak_text
from .theme import (
    BORDER, FONT_SMALL, INK, INK_2, MOSS_DARK, PANEL, PIXEL_SMALL, PIXEL_TEXT, SUNKEN, corner_mask, icon_label,
    make_label, paint_box, sprite,
)
from .widgets import HabitRow, PixelBar, PixelButton, SceneFrame, StatusStrip, same_habits

OVERLAY_SCALE = 2
PAD = 16


class DragHandle(QWidget):
    """Верхняя область: перетаскивание окна без переключения привычек."""

    released = pyqtSignal()

    def __init__(self, window: QWidget):
        super().__init__()
        self._window = window
        self._offset: QPoint | None = None
        self._dragged = False
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setFixedHeight(36)

    @property
    def dragging(self) -> bool:
        return self._offset is not None

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(SUNKEN))
        p.fillRect(0, self.height() - BORDER, self.width(), BORDER, QColor(INK))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._offset = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            self._dragged = False
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._offset)
            self._dragged = True

    def mouseReleaseEvent(self, event) -> None:
        if self._offset is not None:
            self._offset = None
            if self._dragged:
                self.released.emit()  # позиция сохраняется после отпускания мыши


class OverlayWidget(QWidget):
    position_committed = pyqtSignal(int, int, str)

    def __init__(self, shell):
        super().__init__(
            None,
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.shell = shell
        self.controller = shell.controller
        self._rows: list[HabitRow] = []
        self.setWindowTitle("LevelUp")
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.shell.quit)

        crop = shell.manifest.compact_crop
        self.scene = SceneWidget(shell.manifest, shell.config, compact=True)
        self.scene_frame = SceneFrame(self.scene, (crop[2], crop[3]))
        self.scene_frame.set_scale(OVERLAY_SCALE)
        self.setFixedWidth(self.scene_frame.width() + 2 * PAD + 2 * BORDER)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(BORDER, BORDER, BORDER, BORDER)
        outer.setSpacing(0)
        outer.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)  # высота следует за числом привычек

        self.handle = DragHandle(self)
        head = QHBoxLayout(self.handle)
        head.setContentsMargins(PAD, 0, 8, BORDER)
        head.setSpacing(8)
        head.addWidget(icon_label(sprite("star", "fx"), 2))
        head.addWidget(make_label("LevelUp", PIXEL_TEXT, pixel=True))
        head.addStretch(1)
        self.open_btn = PixelButton("Открыть", "mini")
        self.open_btn.setToolTip("Показать основное окно")
        self.hide_btn = PixelButton("Скрыть", "mini")
        self.hide_btn.setToolTip("Убрать виджет и вернуть основное окно")
        head.addWidget(self.open_btn)
        head.addWidget(self.hide_btn)
        outer.addWidget(self.handle)

        body = QVBoxLayout()
        body.setContentsMargins(PAD, 12, PAD, 12)
        body.setSpacing(8)
        self.stage_label = make_label("", PIXEL_TEXT, pixel=True)
        self.xp_label = make_label("", PIXEL_SMALL, pixel=True, color=INK_2)
        stage_row = QHBoxLayout()
        stage_row.addWidget(self.stage_label)
        stage_row.addStretch(1)
        stage_row.addWidget(self.xp_label, 0, Qt.AlignmentFlag.AlignBottom)
        self.bar = PixelBar(height=12)
        self.bar.setAccessibleName("Очки до следующей стадии")
        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(0)
        self.empty_label = make_label(
            "Привычек пока нет. Добавьте первую в основном окне: кнопка «Открыть».", FONT_SMALL, color=INK_2, wrap=True
        )
        self.streak_label = make_label("", FONT_SMALL, color=INK_2)
        self.done_label = make_label(DAY_DONE_TEXT, FONT_SMALL, bold=True, color=MOSS_DARK)
        streak_row = QHBoxLayout()
        streak_row.addWidget(self.streak_label)
        streak_row.addStretch(1)
        streak_row.addWidget(self.done_label)
        self.strip = StatusStrip()
        self.strip.bind(self.controller)
        body.addWidget(self.scene_frame, 0, Qt.AlignmentFlag.AlignHCenter)
        body.addLayout(stage_row)
        body.addWidget(self.bar)
        body.addLayout(self.rows_layout)
        body.addWidget(self.empty_label)
        body.addLayout(streak_row)
        body.addWidget(self.strip)
        outer.addLayout(body)

        self.open_btn.clicked.connect(self.shell.show_main)
        self.hide_btn.clicked.connect(self.shell.hide_overlay)
        self.handle.released.connect(self.commit_position)
        self.controller.state_changed.connect(self.apply_snapshot)
        self.controller.reward.connect(self._on_reward)
        self.controller.pending_changed.connect(self._sync_busy)
        self.apply_snapshot(self.controller.snapshot)

    # ------------------------------------------------------------------ рисование
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        paint_box(p, self.rect(), PANEL)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.setMask(corner_mask(self.width(), self.height()))
        if self.isVisible():  # высота выросла (добавлена привычка): низ не должен уйти за экран
            QTimer.singleShot(0, self._keep_inside)

    def closeEvent(self, event) -> None:
        """Alt+F4 на виджете = «Скрыть»: иначе оба окна пропали бы, а процесс остался без интерфейса."""
        event.ignore()
        self.shell.hide_overlay()

    def _keep_inside(self) -> None:
        if self.isVisible() and not self.handle.dragging:
            screens = current_screens()
            x, y, _ = normalize_position(self.x(), self.y(), self.width(), self.height(), screens, self._screen_name())
            if (x, y) != (self.x(), self.y()):
                self.move(x, y)
                self.commit_position()

    def _screen_name(self) -> str | None:
        snap = self.controller.snapshot
        return snap.screen_name if snap else None

    # ------------------------------------------------------------------ состояние
    def apply_snapshot(self, snap: Snapshot) -> None:
        animate = self.isVisible()
        self.scene.set_snapshot(snap)
        self.strip.set_warning("clock", CLOCK_WARNING_SHORT if snap.clock_rollback else None)
        progress = stage_progress(snap, self.shell.config)
        self.stage_label.setText(snap.stage_name)
        last = progress.next_name is None
        self.xp_label.setText(points_text(snap.total_xp) if last else f"{snap.total_xp} / {snap.next_threshold}")
        self.bar.set_progress(progress.value, progress.maximum, animate)
        self.streak_label.setText(streak_text(snap.streak_days))
        self.done_label.setVisible(snap.day_complete)
        self._sync_rows(snap)
        self._sync_busy()

    def _on_reward(self, event: RewardEvent) -> None:
        self.scene.play_reward(event)

    def _sync_rows(self, snap: Snapshot) -> None:
        self.empty_label.setVisible(not snap.habits)
        if same_habits(self._rows, snap.habits):
            for row, habit in zip(self._rows, snap.habits):
                row.set_done(habit.done_today)
            return
        for row in self._rows:
            self.rows_layout.removeWidget(row)
            row.deleteLater()
        self._rows = []
        for habit in snap.habits:
            name = category_label(self.shell.config, habit.category)
            row = HabitRow(habit.id, habit.title, habit.category, habit.done_today, name, compact=True)
            row.toggle_requested.connect(self.controller.toggle_habit)
            self.rows_layout.addWidget(row)
            self._rows.append(row)
        chain: list[QWidget] = [self.open_btn, self.hide_btn] + [r.mark for r in self._rows] + [self.strip.retry_button]
        for first, second in zip(chain, chain[1:]):
            QWidget.setTabOrder(first, second)

    def _sync_busy(self) -> None:
        for row in self._rows:
            row.set_busy(self.controller.is_habit_pending(row.habit_id))

    # ------------------------------------------------------------------ положение
    def restore_position(self, snap: Snapshot) -> None:
        self.adjustSize()
        x, y, _ = normalize_position(
            snap.overlay_x, snap.overlay_y, self.width(), self.height(), current_screens(), snap.screen_name
        )
        self.move(x, y)

    def commit_position(self) -> None:
        """Возвращает окно в доступную область экрана и сообщает итоговую позицию для сохранения."""
        screens = current_screens()
        x, y, name = normalize_position(
            self.x(), self.y(), self.width(), self.height(), screens, self._screen_name()
        )
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)
        self.position_committed.emit(x, y, name or "")
