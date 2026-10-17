"""Первый запуск: герой («Он» / «Она» с настоящим превью), первая привычка с категорией, часовой пояс."""
from __future__ import annotations

from zoneinfo import available_timezones

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QAbstractButton,
    QDialog,
    QHBoxLayout,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig
from ..domain.errors import Result
from ..look import SpriteManifest, compose_look
from .dialogs import CategoryChooser, FieldFrame, PixelCombo, TitleInput, show_form_error
from .theme import (
    BRICK, FONT_BODY, FONT_SMALL, INK, INK_2, PIXEL_BRAND, PIXEL_TEXT, enlarge, icon_label, make_label, pixel_face,
    sprite,
)
from .widgets import KeyboardFocus, PixelButton, paint_choice_card

PREVIEW_SCALE = 4


def character_previews(manifest: SpriteManifest, base_ids) -> dict[str, QPixmap]:
    """Вид героя на стадии 1 без предметов: слои кадра 64x64, общая обрезка по фигуре, масштаб x4 без сглаживания."""
    frames: dict[str, QImage] = {}
    for base_id in base_ids:
        frame = QImage(manifest.frame, manifest.frame, QImage.Format.Format_ARGB32_Premultiplied)
        frame.fill(Qt.GlobalColor.transparent)
        p = QPainter(frame)
        for layer in compose_look(manifest, base_id, 1, {}).character_layers:
            p.drawImage(0, 0, QImage(str(layer.file)))
        p.end()
        frames[base_id] = frame
    box = QRect()
    for frame in frames.values():
        for y in range(frame.height()):
            for x in range(frame.width()):
                if frame.pixelColor(x, y).alpha():
                    box = box.united(QRect(x, y, 1, 1))
    box = box.adjusted(-2, -2, 2, 2).intersected(QRect(0, 0, manifest.frame, manifest.frame))
    return {base_id: enlarge(QPixmap.fromImage(frame.copy(box)), PREVIEW_SCALE) for base_id, frame in frames.items()}


class HeroCard(KeyboardFocus, QAbstractButton):
    """Карточка героя: превью x4 и подпись. Выбор — как у радиокнопок (стрелки меняют, Tab проходит группу)."""

    MIN_WIDTH = 208

    def __init__(self, title: str, preview: QPixmap, parent: QWidget | None = None):
        super().__init__(parent)
        self._title, self._preview = title, preview
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setMinimumWidth(self.MIN_WIDTH)
        self.setFixedHeight(preview.height() + 12 + 8 + 28 + 12)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setAccessibleName(title)

    def sizeHint(self) -> QSize:
        return QSize(self.MIN_WIDTH, self.height())

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        r = self.rect()
        paint_choice_card(p, r, self.isChecked(), self.underMouse(), self.keyboard_focus)
        p.drawPixmap((r.width() - self._preview.width()) // 2, 12, self._preview)
        p.setPen(QColor(INK))
        p.setFont(pixel_face(PIXEL_TEXT))
        p.drawText(QRect(0, r.height() - 12 - 28, r.width(), 28), Qt.AlignmentFlag.AlignCenter, self._title)


class OnboardingDialog(QDialog):
    """Два шага: герой, затем первая привычка и часовой пояс. Онбординг завершается только вместе с первой привычкой."""

    def __init__(self, shell, parent: QWidget | None = None):
        super().__init__(parent)
        self.shell = shell
        cfg: AppConfig = shell.config
        self.setWindowTitle("LevelUp — первый запуск")
        self.setModal(True)
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(icon_label(sprite("star", "fx"), 3), 0, Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(make_label("LevelUp", PIXEL_BRAND, pixel=True))
        head.addStretch(1)
        self.step_label = make_label("", FONT_SMALL, color=INK_2)
        head.addWidget(self.step_label, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(head)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._hero_page(shell))
        self.pages.addWidget(self._habit_page(shell))
        layout.addWidget(self.pages)

        self.error = make_label("", FONT_SMALL, color=BRICK, wrap=True)
        self.back = PixelButton("Назад")
        self.next = PixelButton("Дальше", "primary")
        self.start = PixelButton("Начать", "primary")
        footer = QHBoxLayout()
        footer.setSpacing(8)
        footer.addWidget(self.error, 1)
        footer.addWidget(self.back)
        footer.addWidget(self.next)
        footer.addWidget(self.start)
        layout.addSpacing(4)
        layout.addLayout(footer)

        self.back.clicked.connect(lambda: self._go(0))
        self.next.clicked.connect(lambda: self._go(1))
        self.start.clicked.connect(self._submit)
        self._go(0)
        # Переносимые подписи делают высоту зависимой от ширины: фиксируем достаточную высоту явно.
        width = self.minimumWidth()
        height = max(self.sizeHint().height(), layout.totalHeightForWidth(width))
        self.setMinimumHeight(height)
        self.resize(width, height)

    # ------------------------------------------------------------------ страницы
    def _hero_page(self, shell) -> QWidget:
        cfg, manifest = shell.config, shell.manifest
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(12)
        box.addWidget(make_label("Кто будет жить в комнате?", PIXEL_TEXT, pixel=True))
        names = cfg.stage_names
        box.addWidget(
            make_label(
                f"За каждую отметку — {cfg.xp_per_completion} очков. Они растят героя от стадии «{names[0]}» "
                f"до «{names[-1]}», а привычки открывают предметы в комнате и меняют его одежду.",
                FONT_BODY,
                color=INK_2,
                wrap=True,
            )
        )
        previews = character_previews(manifest, manifest.bases)
        self.heroes: dict[str, HeroCard] = {}
        cards = QHBoxLayout()
        cards.setSpacing(8)
        for base_id, base in manifest.bases.items():
            card = HeroCard(base.title, previews[base_id])
            card.setChecked(base_id == cfg.default_base)
            self.heroes[base_id] = card
            cards.addWidget(card)
        box.addLayout(cards)
        box.addStretch(1)
        return page

    def _habit_page(self, shell) -> QWidget:
        cfg = shell.config
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)
        box.addWidget(make_label("Первая привычка", PIXEL_TEXT, pixel=True))
        self.field = TitleInput(cfg.title_max_length, "Например: Учить английский 15 минут")
        box.addWidget(self.field)
        box.addWidget(make_label("Что она развивает", FONT_BODY, bold=True))
        self.chooser = CategoryChooser(cfg)
        box.addWidget(self.chooser)
        box.addWidget(make_label("Часовой пояс", FONT_BODY, bold=True))
        self.zone = PixelCombo()
        self.zone.setMaxVisibleItems(14)
        self.zone.setAccessibleName("Часовой пояс")
        zones = sorted(available_timezones()) or ["UTC"]
        detected = shell.detected_timezone
        if detected not in zones:
            self.zone.addItem("— выберите часовой пояс —", None)
        for name in zones:
            self.zone.addItem(name, name)
        if detected in zones:
            self.zone.setCurrentIndex(zones.index(detected))
        box.addWidget(FieldFrame(self.zone))
        self.zone_hint = make_label(
            "" if detected in zones else "Не удалось определить часовой пояс автоматически — выберите его вручную.",
            FONT_SMALL,
            color=BRICK,
            wrap=True,
        )
        self.zone_hint.setVisible(detected not in zones)
        box.addWidget(self.zone_hint)
        box.addStretch(1)
        return page

    # ------------------------------------------------------------------ шаги
    def _go(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.step_label.setText(f"Шаг {index + 1} из 2")
        self.error.setText("")
        self.back.setVisible(index == 1)
        self.next.setVisible(index == 0)
        self.start.setVisible(index == 1)
        default = self.next if index == 0 else self.start
        default.setDefault(True)
        if index == 1:
            self.field.edit.setFocus()
        else:
            next(card for card in self.heroes.values() if card.isChecked()).setFocus()

    def base_id(self) -> str:
        return next(base_id for base_id, card in self.heroes.items() if card.isChecked())

    def _set_busy(self, busy: bool) -> None:
        for widget in (self.field.edit, self.zone, self.start, self.back, *self.chooser.cards.values()):
            widget.setEnabled(not busy)
        self.error.setText("Сохраняем…" if busy else "")

    def _submit(self) -> None:
        zone = self.zone.currentData()
        if zone is None:
            self.error.setText("Выберите часовой пояс.")
            return
        self._set_busy(True)
        payload = {
            "timezone_id": zone,
            "title": self.field.text(),
            "category": self.chooser.category(),
            "base_id": self.base_id(),
        }
        self.shell.controller.submit("finish_onboarding", payload, callback=self._done, quiet=True)

    def _done(self, result: Result) -> None:
        self._set_busy(False)
        if result.ok:
            self.accept()
        elif result.error.field in ("title", "category"):
            show_form_error(result.error, self.field, self.chooser)
        else:
            self.error.setText(result.error.message)
