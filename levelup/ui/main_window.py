"""Основное окно: сцена-герой слева, под ней стадия и награда; справа «Сегодня», «Развитие», календарь."""
from __future__ import annotations

from datetime import date

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QMenu, QScrollArea, QVBoxLayout, QWidget

from ..domain.models import RewardEvent, Snapshot
from .collection import CollectionDialog
from .dialogs import AddHabitDialog, confirm_archive
from .panels import CalendarSection, DevelopmentSection, StageHud
from .scene import SceneWidget
from .summary import CLOCK_WARNING, DAY_DONE_TEXT, category_label, format_date_ru, streak_text
from .theme import (
    BRICK, FLAME, FONT_BODY, FONT_SMALL, GOLD, INK_2, MOSS_DARK, PIXEL_BRAND, PIXEL_TEXT, icon_label, make_label, sprite,
)
from .widgets import HabitRow, Panel, PixelButton, PixelGlyph, RowList, SceneFrame, StatusStrip, same_habits

MARGIN, TOP_MARGIN = 16, 12  # поля окна: боковые и нижнее / верхнее
GAP, BAR_GAP, TOP_BAR = 16, 12, 44  # между колонками, под верхней полосой, высота верхней полосы
RIGHT_MIN, RIGHT_MAX = 336, 420
MIN_SIZE, DEFAULT_SIZE = (800, 560), (1000, 660)


class MainWindow(QMainWindow):
    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.controller = shell.controller
        self._rows: list[HabitRow] = []
        self.setWindowTitle("LevelUp")
        self.setMinimumSize(*MIN_SIZE)

        self.scene = SceneWidget(shell.manifest, shell.config)
        self.scene_frame = SceneFrame(self.scene, shell.manifest.scene)
        self.hud = StageHud(shell.config)
        self.development = DevelopmentSection(shell.config)
        self.calendar = CalendarSection()
        self.strip = StatusStrip()
        self.strip.bind(self.controller)
        self.collection_btn = PixelButton("Коллекция")
        self.collection_btn.setToolTip("Стадии героя и предметы комнаты")
        self.overlay_btn = PixelButton("Виджет")
        self.overlay_btn.setCheckable(True)
        self.quit_btn = PixelButton("Выйти")
        self.quit_btn.setToolTip("Выйти из приложения (Ctrl+Q)")

        self.content = QWidget()
        column = QVBoxLayout(self.content)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(BAR_GAP)
        column.addWidget(self._top_bar())
        columns = QHBoxLayout()
        columns.setSpacing(GAP)
        self.left = QWidget()
        left = QVBoxLayout(self.left)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(8)
        left.addWidget(self.scene_frame)
        left.addWidget(self.hud)
        left.addStretch(1)
        self.right = self._right_column()
        columns.addWidget(self.left, 0, Qt.AlignmentFlag.AlignTop)
        columns.addWidget(self.right)
        column.addLayout(columns, 1)

        root = QWidget()
        outer = QHBoxLayout(root)
        outer.setContentsMargins(MARGIN, TOP_MARGIN, MARGIN, MARGIN)
        outer.addStretch(1)
        outer.addWidget(self.content)
        outer.addStretch(1)
        self.setCentralWidget(root)
        self.resize(*DEFAULT_SIZE)

        self.add_btn.clicked.connect(self.open_add_dialog)
        self.collection_btn.clicked.connect(self.open_collection)
        self.overlay_btn.clicked.connect(self.shell.toggle_overlay)
        self.quit_btn.clicked.connect(self.shell.quit)
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.shell.quit)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.open_add_dialog)
        self.controller.state_changed.connect(self.apply_snapshot)
        self.controller.reward.connect(self._on_reward)
        self.controller.pending_changed.connect(self._sync_busy)
        self.shell.overlay_visibility_changed.connect(self._sync_overlay_button)
        QApplication.instance().focusChanged.connect(self._reveal_focus)
        self._sync_overlay_button()
        self.apply_snapshot(self.controller.snapshot)
        self._set_tab_order()

    # ------------------------------------------------------------------ сборка
    def _top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(TOP_BAR)  # строка состояния укладывается в две строки даже при ширине окна 800
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(icon_label(sprite("star", "fx"), 3), 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(make_label("LevelUp", PIXEL_BRAND, pixel=True), 0, Qt.AlignmentFlag.AlignVCenter)
        row.addSpacing(8)
        row.addWidget(self.strip, 1, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.collection_btn)
        row.addWidget(self.overlay_btn)
        row.addWidget(self.quit_btn)
        return bar

    def _right_column(self) -> QScrollArea:
        self.today = Panel()
        self.today.body.setSpacing(4)
        head = QHBoxLayout()
        head.addWidget(make_label("Сегодня", PIXEL_TEXT, pixel=True))
        head.addStretch(1)
        self.date_label = make_label("", FONT_SMALL, color=INK_2)
        head.addWidget(self.date_label, 0, Qt.AlignmentFlag.AlignBottom)
        self.streak_label = make_label("", FONT_BODY, bold=True)
        self.count_label = make_label("", FONT_SMALL, color=INK_2)
        streak = QHBoxLayout()
        streak.setSpacing(8)
        streak.addWidget(PixelGlyph(FLAME, 2, {"o": BRICK, "i": GOLD}))
        streak.addWidget(self.streak_label)
        streak.addStretch(1)
        streak.addWidget(self.count_label)
        self.rows_list = RowList()
        self.empty = QWidget()
        empty = QVBoxLayout(self.empty)
        empty.setContentsMargins(0, 8, 0, 8)
        empty.setSpacing(4)
        xp = self.shell.config.xp_per_completion
        empty.addWidget(make_label("Здесь пока пусто", FONT_BODY, bold=True))
        hint = f"Добавьте привычку и отмечайте её каждый день: за отметку +{xp} очков."
        empty.addWidget(make_label(hint, FONT_SMALL, color=INK_2, wrap=True))
        self.add_btn = PixelButton("Добавить привычку", "primary")
        self.add_btn.setToolTip("Новая привычка (Ctrl+N)")
        self.done_label = make_label(DAY_DONE_TEXT, FONT_SMALL, bold=True, color=MOSS_DARK)
        add_row = QHBoxLayout()
        add_row.addWidget(self.add_btn)
        add_row.addStretch(1)
        add_row.addWidget(self.done_label)
        self.today.body.addLayout(head)
        self.today.body.addLayout(streak)
        self.today.body.addSpacing(4)
        self.today.body.addWidget(self.rows_list)
        self.today.body.addWidget(self.empty)
        self.today.body.addSpacing(4)
        self.today.body.addLayout(add_row)

        inner = QWidget()
        stack = QVBoxLayout(inner)
        stack.setContentsMargins(0, 0, 0, 4)
        stack.setSpacing(12)
        stack.addWidget(self.today)
        stack.addWidget(self.development)
        stack.addWidget(self.calendar)
        stack.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Tab ходит по привычкам и кнопкам, а не по самой прокрутке
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(inner)
        return scroll

    # ------------------------------------------------------------------ раскладка
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_scene()

    def _fit_scene(self) -> None:
        """Сцена всегда в целый масштаб: берём наибольший, при котором влезают и сцена с подписью, и правая колонка."""
        width = self.width() - 2 * MARGIN
        height = self.height() - TOP_MARGIN - MARGIN - TOP_BAR - BAR_GAP
        scale = 2
        for candidate in (4, 3):
            size = self.scene_frame.frame_size(candidate)
            hud = self.hud.body.totalHeightForWidth(size.width())
            if size.width() + GAP + RIGHT_MIN <= width and size.height() + 8 + hud <= height:
                scale = candidate
                break
        self.scene_frame.set_scale(scale)
        left = self.scene_frame.width()
        right = min(RIGHT_MAX, width - left - GAP)
        self.left.setFixedWidth(left)
        self.right.setFixedWidth(right)
        self.content.setFixedWidth(left + GAP + right)

    def _reveal_focus(self, _old, new) -> None:
        if new is not None and self.right.widget().isAncestorOf(new):
            self.right.ensureWidgetVisible(new, 0, 16)

    # ------------------------------------------------------------------ обновление
    def apply_snapshot(self, snap: Snapshot) -> None:
        animate = self.isVisible()
        self.scene.set_snapshot(snap)
        self.hud.apply(snap, animate)
        self.development.apply(snap, animate)
        self.calendar.apply(snap)
        self.strip.set_warning("clock", CLOCK_WARNING if snap.clock_rollback else None)
        self.date_label.setText(format_date_ru(date.fromisoformat(snap.date)))
        self.streak_label.setText(streak_text(snap.streak_days))
        self.count_label.setText(f"Активных привычек: {len(snap.habits)} из {snap.max_active_habits}")
        full = len(snap.habits) >= snap.max_active_habits
        self.add_btn.setEnabled(not full)
        self.add_btn.setToolTip(
            "Достигнут лимит активных привычек: архивируйте одну из них." if full else "Новая привычка (Ctrl+N)"
        )
        self._sync_rows(snap)
        self.empty.setVisible(not snap.habits)
        self.done_label.setVisible(snap.day_complete)
        self._sync_busy()
        self._fit_scene()

    def _on_reward(self, event: RewardEvent) -> None:
        self.scene.play_reward(event)

    def _sync_rows(self, snap: Snapshot) -> None:
        if same_habits(self._rows, snap.habits):
            for row, habit in zip(self._rows, snap.habits):
                row.set_done(habit.done_today)
            return
        for row in self._rows:
            self.rows_list.column.removeWidget(row)
            row.deleteLater()
        self._rows = []
        for habit in snap.habits:
            name = category_label(self.shell.config, habit.category)
            row = HabitRow(habit.id, habit.title, habit.category, habit.done_today, name)
            row.toggle_requested.connect(self.controller.toggle_habit)
            row.menu_requested.connect(self._row_menu)
            self.rows_list.column.addWidget(row)
            self._rows.append(row)
        self._set_tab_order()

    def _set_tab_order(self) -> None:
        """Сначала привычки (отметка, меню), затем «Добавить», затем кнопки верхней полосы."""
        order: list[QWidget] = []
        for row in self._rows:
            order += [row.mark, row.menu_btn]
        order += [self.add_btn, self.strip.retry_button, self.collection_btn, self.overlay_btn, self.quit_btn]
        for first, second in zip(order, order[1:]):
            QWidget.setTabOrder(first, second)

    def _sync_busy(self) -> None:
        for row in self._rows:
            row.set_busy(self.controller.is_habit_pending(row.habit_id))

    def _sync_overlay_button(self, *_: object) -> None:
        visible = self.shell.overlay_visible()
        self.overlay_btn.setChecked(visible)
        self.overlay_btn.setToolTip("Скрыть виджет" if visible else "Показать виджет поверх окон")

    # ------------------------------------------------------------------ действия
    def open_add_dialog(self) -> None:
        if self.add_btn.isEnabled():
            AddHabitDialog(self.controller, self.shell.config, self).exec()

    def open_collection(self) -> None:
        CollectionDialog(self.controller.snapshot, self.shell.config, self).exec()

    def _row_menu(self, habit_id: str, pos: QPoint) -> None:
        habit = next((h for h in self.controller.snapshot.habits if h.id == habit_id), None)
        if habit is None:
            return
        menu = QMenu(self)
        archive = menu.addAction("Архивировать…")
        if menu.exec(pos) is archive and confirm_archive(self, habit.title):
            self.controller.archive_habit(habit_id)

    def closeEvent(self, event) -> None:
        """Закрытие окна не останавливает работающий виджет; без виджета приложение завершается."""
        if self.shell.overlay_visible():
            event.ignore()
            self.hide()
        else:
            event.accept()
            self.shell.quit()
