"""Диалоги: добавление привычки, выбор категории, подтверждение архивирования."""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig, CategoryConfig
from ..domain.errors import ErrorInfo, Result
from .theme import (
    BRICK, FONT_BODY, FONT_SMALL, INK, INK_2, PANEL, PIXEL_TEXT, category_icon, make_label, paint_box,
    set_text_color, ui_font, unlock_icon,
)
from .widgets import KeyboardFocus, PixelButton, paint_choice_card, paint_ring

FIELD_HEIGHT = 36
LEFT_CENTER = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
TOP_WRAP = Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap


class FieldFrame(QWidget):
    """Рамка поля ввода: бумажная заливка, контур 2 px, при фокусе внутри — золотое кольцо."""

    def __init__(self, inner: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        self.inner = inner
        self.error = False
        self.setFixedHeight(FIELD_HEIGHT)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(inner)
        inner.installEventFilter(self)

    def set_error(self, error: bool) -> None:
        self.error = error
        self.update()

    def eventFilter(self, _obj, event) -> bool:
        if event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            self.update()
        return False

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        paint_box(p, self.rect(), PANEL, BRICK if self.error else INK, cut=1)
        if self.inner.hasFocus():
            paint_ring(p, self.rect().adjusted(2, 2, -2, -2))


class PixelCombo(QComboBox):
    """Выпадающий список без рамки (её рисует FieldFrame) со своей пиксельной стрелкой."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFont(ui_font(FONT_BODY))

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        x, y = self.width() - 24, self.height() // 2 - 3
        for row in range(4):  # стрелка вниз: ряды по 2 px, сужаются к низу
            p.fillRect(x + row * 2, y + row * 2, 14 - row * 4, 2, QColor(INK))


class TitleInput(QWidget):
    """Поле названия со счётчиком символов и областью для текста ошибки."""

    def __init__(self, max_len: int, placeholder: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.max_len = max_len
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.edit = QLineEdit()
        self.edit.setFont(ui_font(FONT_BODY))
        self.edit.setPlaceholderText(placeholder)
        self.edit.setAccessibleName("Название привычки")
        self.frame = FieldFrame(self.edit)
        self.counter = make_label("", FONT_SMALL, color=INK_2)
        self.error = make_label("", FONT_SMALL, color=BRICK, wrap=True)
        self.error.setMinimumHeight(16)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.error, 1)
        row.addWidget(self.counter, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.frame)
        layout.addLayout(row)
        self.edit.textChanged.connect(self._changed)
        self._changed("")

    def text(self) -> str:
        return self.edit.text()

    def show_error(self, message: str) -> None:
        self.error.setText(message)
        self.frame.set_error(bool(message))

    def _changed(self, text: str) -> None:
        self.show_error("")
        over = len(text) > self.max_len
        self.counter.setText(f"{len(text)}/{self.max_len}")
        set_text_color(self.counter, BRICK if over else INK_2)


class CategoryCard(KeyboardFocus, QAbstractButton):
    """Карточка категории: иконка x2, название, описание и то, что откроется первым. Выбор — как у радиокнопок."""

    MIN_WIDTH, HEIGHT = 208, 120

    def __init__(self, category: CategoryConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self.category = category
        self.first_unlock = category.unlocks[0]
        self.setCheckable(True)
        self.setAutoExclusive(True)  # стрелки меняют выбор, Tab проходит группу целиком
        self.setMinimumWidth(self.MIN_WIDTH)
        self.setFixedHeight(self.HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setAccessibleName(f"{category.name}. {category.blurb}")
        self.setAccessibleDescription(f"Первым откроется: {self.first_unlock.name}")
        items = ", ".join(f"«{unlock.name}»" for unlock in category.unlocks)
        self.setToolTip(f"{category.name}: за отметки откроются {items}")

    def sizeHint(self) -> QSize:
        return QSize(self.MIN_WIDTH, self.HEIGHT)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        r = self.rect()
        paint_choice_card(p, r, self.isChecked(), self.underMouse(), self.keyboard_focus)
        p.drawPixmap(QRect(12, 12, 32, 32), category_icon(self.category.id))
        p.setPen(QColor(INK))
        p.setFont(ui_font(FONT_BODY, bold=True))
        p.drawText(QRect(52, 12, r.width() - 52 - 40, 32), LEFT_CENTER, self.category.name)
        p.setPen(QColor(INK_2))
        p.setFont(ui_font(FONT_SMALL))
        p.drawText(QRect(12, 52, r.width() - 24, 32), TOP_WRAP, self.category.blurb)
        p.drawPixmap(QRect(12, r.height() - 28, 16, 16), unlock_icon(self.first_unlock.id))
        p.setPen(QColor(INK))
        first = f"Первым откроется: {self.first_unlock.name}"
        text = p.fontMetrics().elidedText(first, Qt.TextElideMode.ElideRight, r.width() - 44)
        p.drawText(QRect(32, r.height() - 30, r.width() - 44, 20), LEFT_CENTER, text)


class CategoryChooser(QWidget):
    """Четыре карточки категорий 2x2. Категория обязательна, по умолчанию выбрана первая."""

    changed = pyqtSignal(str)

    def __init__(self, config: AppConfig, columns: int = 2, parent: QWidget | None = None):
        super().__init__(parent)
        self.cards: dict[str, CategoryCard] = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, category in enumerate(config.categories):
            card = CategoryCard(category)
            card.toggled.connect(lambda on, cid=category.id: self.changed.emit(cid) if on else None)
            self.cards[category.id] = card
            grid.addWidget(card, i // columns, i % columns)
        self.error = make_label("", FONT_SMALL, color=BRICK, wrap=True)
        outer.addLayout(grid)
        outer.addWidget(self.error)
        next(iter(self.cards.values())).setChecked(True)

    def category(self) -> str:
        return next(cid for cid, card in self.cards.items() if card.isChecked())

    def set_category(self, category_id: str) -> None:
        self.cards[category_id].setChecked(True)

    def show_error(self, message: str) -> None:
        self.error.setText(message)


class AddHabitDialog(QDialog):
    def __init__(self, controller, config: AppConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Новая привычка")
        self.setModal(True)
        self.setMinimumWidth(540)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(8)
        self.field = TitleInput(config.title_max_length, "Например: Учить английский 15 минут")
        self.chooser = CategoryChooser(config)
        self.status = make_label("", FONT_SMALL, color=INK_2)
        self.cancel = PixelButton("Отмена")
        self.ok = PixelButton("Добавить", "primary")
        self.ok.setDefault(True)  # Enter подтверждает диалог
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(self.status, 1)
        buttons.addWidget(self.cancel)
        buttons.addWidget(self.ok)
        layout.addWidget(make_label("Новая привычка", PIXEL_TEXT, pixel=True))
        layout.addSpacing(4)
        layout.addWidget(make_label("Название", FONT_BODY, bold=True))
        layout.addWidget(self.field)
        layout.addWidget(make_label("Что она развивает", FONT_BODY, bold=True))
        layout.addWidget(self.chooser)
        layout.addSpacing(4)
        layout.addLayout(buttons)
        self.cancel.clicked.connect(self.reject)
        self.ok.clicked.connect(self._submit)
        self.field.edit.setFocus()

    def _set_busy(self, busy: bool) -> None:
        for widget in (self.field.edit, self.ok, self.cancel, *self.chooser.cards.values()):
            widget.setEnabled(not busy)
        self.status.setText("Сохраняем…" if busy else "")

    def _submit(self) -> None:
        self._set_busy(True)
        payload = {"title": self.field.text(), "category": self.chooser.category()}
        self.controller.submit("create_habit", payload, callback=self._done, quiet=True)

    def _done(self, result: Result) -> None:
        self._set_busy(False)
        if result.ok:
            self.accept()
        else:
            show_form_error(result.error, self.field, self.chooser)
            self.field.edit.setFocus()


def show_form_error(error: ErrorInfo, field: TitleInput, chooser: CategoryChooser) -> None:
    """Ошибка команды рядом с тем полем, к которому она относится (по умолчанию — под названием)."""
    (chooser if error.field == "category" else field).show_error(error.message)


def confirm_archive(parent: QWidget, title: str) -> bool:
    shown = title if len(title) <= 60 else title[:57] + "…"
    dialog = QDialog(parent)
    dialog.setWindowTitle("Архивировать привычку")
    dialog.setMinimumWidth(420)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(24, 20, 24, 20)
    layout.setSpacing(8)
    layout.addWidget(make_label(f"Архивировать привычку «{shown}»?", FONT_BODY, bold=True, wrap=True))
    layout.addWidget(
        make_label(
            "Она исчезнет из списка и освободит место. Сегодняшняя отметка будет удалена "
            "(очки за неё вернутся назад), прошлая история сохранится.",
            FONT_BODY,
            color=INK_2,
            wrap=True,
        )
    )
    layout.addSpacing(8)
    cancel, yes = PixelButton("Отмена"), PixelButton("Архивировать", "primary")
    yes.setDefault(True)
    row = QHBoxLayout()
    row.setSpacing(8)
    row.addStretch(1)
    row.addWidget(cancel)
    row.addWidget(yes)
    layout.addLayout(row)
    cancel.clicked.connect(dialog.reject)
    yes.clicked.connect(dialog.accept)
    return dialog.exec() == QDialog.DialogCode.Accepted
