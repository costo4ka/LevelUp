"""Общие виджеты: панель, кнопка, отметка, строка привычки, полоски прогресса, календарь, строка состояния."""
from __future__ import annotations

from datetime import date

from PyQt6.QtCore import QEasingCurve, QEvent, QPoint, QRect, QSize, Qt, QTimer, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig, CategoryConfig
from ..domain.errors import ErrorInfo
from ..domain.models import CategoryView
from .summary import (
    CALENDAR_WEEKS, MARKS, DayCell, calendar_cells, category_progress, format_day_ru, plural, points_text,
)
from .theme import (
    BG, BORDER, BRICK, CATEGORY_COLORS, FONT_BODY, FONT_SMALL, GOLD, GOLD_DARK, INK, INK_2, KEYBOARD_REASONS,
    LINE_SOFT, MOSS, MOSS_DARK, PANEL, SUNKEN, TICK, bitmap_size, category_icon, dotted_line, draw_bitmap, icon_label,
    make_label, paint_box, set_text_color, text_width, ui_font,
)


class KeyboardFocus:
    """Запоминает, что фокус пришёл с клавиатуры: кольцо фокуса рисуется только в этом случае, не после клика."""

    keyboard_focus = False

    def focusInEvent(self, event) -> None:
        if event.reason() != Qt.FocusReason.ActiveWindowFocusReason:  # возвращение в окно не меняет способ фокуса
            self.keyboard_focus = event.reason() in KEYBOARD_REASONS
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        if event.reason() != Qt.FocusReason.ActiveWindowFocusReason:
            self.keyboard_focus = False
        super().focusOutEvent(event)


def paint_ring(p: QPainter, rect: QRect, color: str = GOLD_DARK, width: int = BORDER) -> None:
    for part in (
        QRect(rect.x(), rect.y(), rect.width(), width),
        QRect(rect.x(), rect.bottom() + 1 - width, rect.width(), width),
        QRect(rect.x(), rect.y() + width, width, rect.height() - 2 * width),
        QRect(rect.right() + 1 - width, rect.y() + width, width, rect.height() - 2 * width),
    ):
        p.fillRect(part, QColor(color))


def paint_tick_box(p: QPainter, box: QRect, fill: str = MOSS, outline: str = INK) -> None:
    """Квадрат с пиксельной галочкой: «выполнено», «выбрано»."""
    paint_box(p, box, fill, outline, cut=1)
    w, h = bitmap_size(TICK, 2)
    draw_bitmap(p, TICK, box.x() + (box.width() - w) // 2, box.y() + (box.height() - h) // 2, 2, {"#": PANEL})


def paint_choice_card(p: QPainter, rect: QRect, selected: bool, hover: bool, keyboard_focus: bool) -> None:
    """Фон карточки выбора: выбранная — зелёное кольцо и галочка в углу, с клавиатурным фокусом — золотое кольцо."""
    paint_box(p, rect, SUNKEN if hover and not selected else PANEL)
    if selected:
        paint_ring(p, rect.adjusted(2, 2, -2, -2), MOSS)
        paint_tick_box(p, QRect(rect.right() - 12 - 20 + 1, 12, 20, 20))
    if keyboard_focus:
        paint_ring(p, rect.adjusted(4, 4, -4, -4), GOLD_DARK)


# ---------------------------------------------------------------------- панель и кнопки
class Panel(QFrame):
    """Бумажная панель: плоская заливка, контур 2 px ink, углы лесенкой."""

    def __init__(
        self, parent: QWidget | None = None, fill: str = PANEL, margins: tuple[int, int, int, int] = (16, 12, 16, 12)
    ):
        super().__init__(parent)
        self._fill = fill
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(*margins)
        self.body.setSpacing(8)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        paint_box(p, self.rect(), self._fill)


class Rule(QWidget):
    """Пунктирная линия-разделитель."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(BORDER)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        dotted_line(p, 0, self.width(), 0)
        dotted_line(p, 1, self.width(), 1)


class PixelButton(KeyboardFocus, QPushButton):
    """Кнопка с контуром 2 px и «ножкой» снизу; при нажатии шапка опускается на 2 px.

    kind: normal, primary (главное действие), mini (мелкая), ghost (без рамки до наведения).
    """

    def __init__(self, text: str = "", kind: str = "normal", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.kind = kind
        self.setFont(ui_font(FONT_SMALL if kind == "mini" else FONT_BODY, bold=True))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(24 if kind == "mini" else 32)

    def sizeHint(self) -> QSize:
        pad = {"primary": 20, "mini": 10}.get(self.kind, 16)
        return QSize(max(text_width(self.font(), self.text()) + 2 * pad + 2 * BORDER, 40), self.minimumHeight())

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def _colors(self) -> tuple[str | None, str, str | None, str]:
        """(заливка шапки, цвет «ножки», контур, цвет текста)."""
        down = self.isDown() or self.isChecked()
        hover = self.underMouse()
        if not self.isEnabled():
            return SUNKEN, SUNKEN, LINE_SOFT, LINE_SOFT
        if self.kind == "primary":
            return (MOSS if hover else MOSS_DARK), INK, INK, PANEL
        if self.kind == "ghost":
            if down:
                return LINE_SOFT, LINE_SOFT, LINE_SOFT, INK
            return (SUNKEN, SUNKEN, LINE_SOFT, INK) if hover else (None, BG, None, INK_2)
        return (SUNKEN if down else BG if hover else PANEL), LINE_SOFT, INK, INK

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        face, side, outline, text = self._colors()
        r = self.rect()
        down = (self.isDown() or self.isChecked()) and self.isEnabled()
        if outline is not None:
            paint_box(p, r, side, outline, cut=1)
        cap = r.adjusted(BORDER, BORDER + (2 if down else 0), -BORDER, -BORDER - (0 if down else 2))
        if face is not None:
            p.fillRect(cap, QColor(face))
        if self.keyboard_focus and self.isEnabled():
            paint_ring(p, r.adjusted(BORDER, BORDER, -BORDER, -BORDER))
        p.setPen(QColor(text))
        p.setFont(self.font())
        p.drawText(cap, Qt.AlignmentFlag.AlignCenter, self.text())


class CheckMark(KeyboardFocus, QAbstractButton):
    """Квадратная отметка с пиксельной галочкой. Состояние меняется только после подтверждённой записи."""

    toggle_requested = pyqtSignal(bool)
    SIZE = 28
    BOX = 20

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._busy = False
        self.setCheckable(True)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def is_busy(self) -> bool:
        return self._busy

    def set_busy(self, busy: bool) -> None:
        """Пока идёт запись, отметка бледнеет и не реагирует; фокус при этом остаётся на ней."""
        self._busy = busy
        self.setCursor(Qt.CursorShape.BusyCursor if busy else Qt.CursorShape.PointingHandCursor)
        self.update()

    def nextCheckState(self) -> None:  # вызывается при клике и по Space; состояние сменит только подтверждённая запись
        if not self._busy:
            self.toggle_requested.emit(not self.isChecked())

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        inset = (self.SIZE - self.BOX) // 2
        box = QRect(inset, inset, self.BOX, self.BOX)
        enabled = self.isEnabled() and not self._busy
        outline = INK if enabled else LINE_SOFT
        if self.isChecked():
            paint_tick_box(p, box, MOSS if enabled else LINE_SOFT, outline)
        else:
            paint_box(p, box, SUNKEN if self.underMouse() and enabled else PANEL, outline, cut=1)
        if self.keyboard_focus:
            paint_ring(p, self.rect())


class ElidedLabel(QLabel):
    """Однострочная подпись с «…»; полный текст — в подсказке."""

    def __init__(
        self,
        text: str = "",
        size: int = FONT_BODY,
        bold: bool = False,
        color: str = INK,
        tooltip: bool = True,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._full, self._tooltip = "", tooltip
        self.setFont(ui_font(size, bold))
        set_text_color(self, color)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self.set_full_text(text)

    def set_full_text(self, text: str) -> None:
        self._full = text
        if self._tooltip:
            self.setToolTip(text)
        self._elide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        elided = self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight, max(8, self.width()))
        if elided != self.text():
            super().setText(elided)


# ---------------------------------------------------------------------- привычки
class HabitRow(QWidget):
    toggle_requested = pyqtSignal(str, bool)  # habit_id, желаемое состояние
    menu_requested = pyqtSignal(str, QPoint)

    def __init__(
        self,
        habit_id: str,
        title: str,
        category: str,
        done: bool,
        category_name: str = "",
        compact: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.habit_id, self.title, self.category = habit_id, title, category
        self.menu_btn: PixelButton | None = None
        self._color = CATEGORY_COLORS.get(category, INK_2)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFixedHeight(32)
        self.setToolTip(f"{title} · {category_name}" if category_name else title)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 0 if compact else 4, 0)
        layout.setSpacing(8)

        self.mark = CheckMark()
        self.mark.setAccessibleName(f"Отметка: {title}")
        self.mark.toggle_requested.connect(lambda desired: self.toggle_requested.emit(self.habit_id, desired))
        self.label = ElidedLabel(title, tooltip=False)  # подсказку показывает вся строка: название и категория
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.mark)
        layout.addWidget(self.label, 1)

        if not compact:
            layout.addWidget(icon_label(category_icon(category)))
            self.menu_btn = PixelButton("···", "ghost")
            self.menu_btn.setFixedWidth(32)
            self.menu_btn.setToolTip("Действия с привычкой")
            self.menu_btn.setAccessibleName(f"Действия: {title}")
            self.menu_btn.clicked.connect(self._menu_from_button)
            layout.addWidget(self.menu_btn)
            self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.customContextMenuRequested.connect(
                lambda pos: self.menu_requested.emit(self.habit_id, self.mapToGlobal(pos))
            )
        self.set_done(done)

    def _menu_from_button(self) -> None:
        corner = self.menu_btn.mapToGlobal(QPoint(0, self.menu_btn.height()))
        self.menu_requested.emit(self.habit_id, corner)

    def set_done(self, done: bool) -> None:
        self.mark.setChecked(done)
        font = self.label.font()
        font.setStrikeOut(done)  # смысл «выполнено» передаётся не только цветом
        self.label.setFont(font)
        set_text_color(self.label, INK_2 if done else INK)

    def set_busy(self, busy: bool) -> None:
        self.mark.set_busy(busy)
        if self.menu_btn is not None:
            self.menu_btn.setEnabled(not busy)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        if self.underMouse():
            p.fillRect(self.rect(), QColor(SUNKEN))
        p.fillRect(0, 6, 4, self.height() - 12, QColor(self._color))  # метка категории

    def mouseReleaseEvent(self, event) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and not self.mark.is_busy()
            and self.rect().contains(event.position().toPoint())
        ):
            self.mark.click()
        super().mouseReleaseEvent(event)


def same_habits(rows: list[HabitRow], habits) -> bool:
    """Показаны ли уже именно эти привычки (тогда достаточно обновить отметки, не пересобирая строки)."""
    return [(r.habit_id, r.title, r.category) for r in rows] == [(h.id, h.title, h.category) for h in habits]


class RowList(QWidget):
    """Колонка строк привычек с пунктиром между ними."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.column = QVBoxLayout(self)
        self.column.setContentsMargins(0, 0, 0, 0)
        self.column.setSpacing(BORDER)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        rows = [self.column.itemAt(i).widget() for i in range(self.column.count())]
        for row in rows[:-1]:
            dotted_line(p, 8, self.width() - 8, row.geometry().bottom() + 1)


class PixelGlyph(QWidget):
    """Маленькая пиксельная картинка, нарисованная кодом (по строкам-маске)."""

    def __init__(self, rows: tuple[str, ...], scale: int, colors: dict[str, str], parent: QWidget | None = None):
        super().__init__(parent)
        self._rows, self._scale, self._colors = rows, scale, colors
        self.setFixedSize(*bitmap_size(rows, scale))

    def paintEvent(self, _event) -> None:
        draw_bitmap(QPainter(self), self._rows, 0, 0, self._scale, self._colors)


class StatusStrip(QWidget):
    """Строка состояния: «Сохраняем…», ошибка с «Повторить», краткие уведомления, предупреждения."""

    retry_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._label = make_label("", FONT_SMALL, wrap=True)
        self.retry_button = PixelButton("Повторить", "mini")
        self.retry_button.hide()
        self.retry_button.clicked.connect(self.retry_requested)
        layout.addWidget(self._label, 1)
        layout.addWidget(self.retry_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.setMinimumHeight(24)
        self._saving = False
        self._error: ErrorInfo | None = None
        self._notice = ""
        self._warnings: dict[str, str] = {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self._expire_notice)
        self._render()

    def bind(self, controller) -> None:
        controller.saving_changed.connect(self.set_saving)
        controller.notice.connect(self.show_notice)
        controller.error_occurred.connect(self.set_error)
        controller.error_cleared.connect(self.clear_error)
        self.retry_requested.connect(controller.retry_last)

    def set_saving(self, saving: bool) -> None:
        self._saving = saving
        self._render()

    def show_notice(self, text: str) -> None:
        self._notice = text
        self._timer.start()
        self._render()

    def set_error(self, info: ErrorInfo) -> None:
        self._error = info
        self._render()

    def clear_error(self) -> None:
        self._error = None
        self._render()

    def set_warning(self, key: str, text: str | None) -> None:
        if text:
            self._warnings[key] = text
        else:
            self._warnings.pop(key, None)
        self._render()

    def _expire_notice(self) -> None:
        self._notice = ""
        self._render()

    def _render(self) -> None:
        retry = False
        if self._saving:
            text, color = "Сохраняем…", INK_2
        elif self._error is not None:
            text, color, retry = self._error.message, BRICK, self._error.retryable
        elif self._warnings:
            text, color = next(iter(self._warnings.values())), BRICK
        elif self._notice:
            text, color = self._notice, INK
        else:
            text, color = "", INK_2
        self._label.setText(text)
        set_text_color(self._label, color)
        self.retry_button.setVisible(retry)


# ---------------------------------------------------------------------- полоски прогресса
class PixelBar(QWidget):
    """Плоская полоска: контур 2 px, ступенчатая заливка; значение меняется коротким (≤ 300 мс) движением."""

    DURATION_MS = 240

    def __init__(
        self,
        fill: str = GOLD,
        edge: str | None = GOLD_DARK,
        height: int = 16,
        outline: str = INK,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._fill, self._edge, self._outline = fill, edge, outline
        self._value, self._maximum, self._shown = 0, 1, 0.0
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(self.DURATION_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)

    def value(self) -> int:
        return self._value

    def maximum(self) -> int:
        return self._maximum

    def fraction(self) -> float:
        return min(1.0, self._value / self._maximum)

    def set_progress(self, value: int, maximum: int, animate: bool = True) -> None:
        """Цель задаётся сразу (value() отдаёт её же), на экране полоска доезжает за DURATION_MS."""
        same_scale = maximum == self._maximum
        self._value, self._maximum = value, max(1, maximum)
        target = self.fraction()
        self._anim.stop()
        if animate and same_scale and self.isVisible() and target != self._shown:
            self._anim.setStartValue(self._shown)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self._shown = target
            self.update()

    def _on_anim(self, value) -> None:
        self._shown = float(value)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        paint_box(p, self.rect(), SUNKEN, self._outline, cut=1)
        inner = self.rect().adjusted(BORDER, BORDER, -BORDER, -BORDER)
        width = round(inner.width() * self._shown / 2) * 2  # шаг 2 px: ступенчатый край
        if width > 0:
            p.fillRect(inner.x(), inner.y(), width, inner.height(), QColor(self._fill))
            if self._edge and inner.height() >= 8:
                p.fillRect(inner.x(), inner.bottom() - 1, width, 2, QColor(self._edge))


class TierPips(QWidget):
    """Три квадратика: сколько предметов категории уже открыто."""

    PIP, GAP = 10, 4

    def __init__(self, count: int = 3, parent: QWidget | None = None):
        super().__init__(parent)
        self._count, self._filled, self._color = count, 0, INK_2
        self.setFixedSize(count * self.PIP + (count - 1) * self.GAP, self.PIP)

    def filled(self) -> int:
        return self._filled

    def set_state(self, filled: int, color: str) -> None:
        self._filled, self._color = filled, color
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        for i in range(self._count):
            box = QRect(i * (self.PIP + self.GAP), 0, self.PIP, self.PIP)
            paint_box(p, box, self._color if i < self._filled else PANEL, INK if i < self._filled else LINE_SOFT, cut=1)


class CategoryRow(QWidget):
    """Строка «Развития»: иконка x2, название, очки, тонкая полоска до следующего предмета, три отметки тиров."""

    BAR_WIDTH = 112

    def __init__(self, category: CategoryConfig, config: AppConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self.category_id, self._category, self._config = category.id, category, config
        self._color = CATEGORY_COLORS.get(category.id, INK_2)
        self.setFixedHeight(36)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(0)
        self.name_label = make_label(category.name, FONT_BODY, bold=True)
        self.points_label = make_label("", FONT_SMALL, color=INK_2)
        self.hint = ElidedLabel("", FONT_SMALL, color=INK_2)
        self.pips = TierPips(len(config.category_tiers))
        self.bar = PixelBar(self._color, None, 8, LINE_SOFT)
        self.bar.setFixedWidth(self.BAR_WIDTH)
        names = QHBoxLayout()
        names.setSpacing(8)
        names.addWidget(self.name_label)
        names.addWidget(self.points_label)
        names.addStretch(1)
        icon = icon_label(category_icon(category.id), 2)
        grid.addWidget(icon, 0, 0, 2, 1, Qt.AlignmentFlag.AlignVCenter)
        grid.addLayout(names, 0, 1)
        grid.addWidget(self.hint, 1, 1)
        grid.addWidget(self.pips, 0, 2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(self.bar, 1, 2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.setColumnStretch(1, 1)

    def apply(self, view: CategoryView, animate: bool = True) -> None:
        progress = category_progress(view, self._config)
        self.points_label.setText(points_text(view.points))
        self.pips.set_state(view.tier, self._color)
        self.bar.set_progress(progress.done, progress.span, animate)
        if progress.unlock is None:
            self.hint.set_full_text("всё открыто")
            tip = f"{self._category.name}: открыты все предметы."
        else:
            self.hint.set_full_text(f"ещё {progress.left} до «{progress.unlock.name}»")
            marks = plural(progress.left, MARKS)
            tip = f"{self._category.name}: ещё {progress.left} {marks} до «{progress.unlock.name}»."
        self.setToolTip(tip)
        total = len(self._config.category_tiers)
        self.setAccessibleName(f"{self._category.name}, {points_text(view.points)}, открыто {view.tier} из {total}")


# ---------------------------------------------------------------------- календарь
class CalendarGrid(QWidget):
    """Сетка «понедельник-воскресенье» за пять недель: полные дни закрашены, сегодняшний обведён."""

    CELL, GAP, HEAD = 12, 4, 16
    WEEKDAYS = "ПВСЧПСВ"

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._cells: list[DayCell] = []
        pitch = self.CELL + self.GAP
        self.setFixedSize(7 * pitch - self.GAP, self.HEAD + CALENDAR_WEEKS * pitch - self.GAP)

    def cells(self) -> list[DayCell]:
        return self._cells

    def set_data(self, today: date, full_days) -> None:
        self._cells = calendar_cells(today, full_days)
        self.update()

    def full_count(self) -> int:
        return sum(cell.full for cell in self._cells)

    def _rect(self, index: int) -> QRect:
        pitch = self.CELL + self.GAP
        row, col = divmod(index, 7)
        return QRect(col * pitch, self.HEAD + row * pitch, self.CELL, self.CELL)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setFont(ui_font(FONT_SMALL))
        p.setPen(QColor(INK_2))
        for col, letter in enumerate(self.WEEKDAYS):
            r = self._rect(col)
            p.drawText(QRect(r.x(), 0, r.width(), self.HEAD - 2), Qt.AlignmentFlag.AlignCenter, letter)
        for i, cell in enumerate(self._cells):
            r = self._rect(i)
            if cell.future:
                p.fillRect(r.center().x() - 1, r.center().y() - 1, 2, 2, QColor(LINE_SOFT))
            else:
                p.fillRect(r, QColor(MOSS if cell.full else SUNKEN))
            if cell.today:
                paint_ring(p, r, INK)

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            pos = event.pos()
            for i, cell in enumerate(self._cells):
                if self._rect(i).contains(pos):
                    state = "будущий день" if cell.future else "все привычки выполнены" if cell.full else "есть пропуск"
                    QToolTip.showText(event.globalPos(), f"{format_day_ru(cell.day)}: {state}", self)
                    return True
            QToolTip.hideText()
            return True
        return super().event(event)



class SceneFrame(QWidget):
    """Сцена в рамке 2 px ink. Размер всегда кратен логическому размеру сцены: масштаб целый, без сглаживания."""

    def __init__(self, scene: QWidget, logical: tuple[int, int], parent: QWidget | None = None):
        super().__init__(parent)
        self.scene = scene
        self._logical = logical
        self._scale = 0
        scene.setParent(self)
        scene.move(BORDER, BORDER)
        self.set_scale(2)

    def scale(self) -> int:
        return self._scale

    def frame_size(self, scale: int) -> QSize:
        return QSize(self._logical[0] * scale + 2 * BORDER, self._logical[1] * scale + 2 * BORDER)

    def set_scale(self, scale: int) -> None:
        if scale == self._scale:
            return
        self._scale = scale
        self.scene.setFixedSize(self._logical[0] * scale, self._logical[1] * scale)
        self.setFixedSize(self.frame_size(scale))

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        paint_box(p, self.rect(), INK, INK)
