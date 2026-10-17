"""Рисует состояния интерфейса без экрана (offscreen) в PNG — для проверки вёрстки глазами.

    .venv/bin/python tools/make_demo.py /tmp/demo-w8 --base w --days 8
    .venv/bin/python tools/screenshots.py /tmp/shots --data /tmp/demo-w8 --prefix w8_ --size 1000x660 --check

Главное окно, виджет, диалог добавления, коллекция, «О программе» берут данные из --data (папка make_demo);
онбординг данных не требует. --only выбирает окна, --check печатает подозрительные места (обрезанный текст).
--done N отмечает первые N привычек через контроллер, --state error|warning показывает ошибку с «Повторить» или
предупреждение о часах: оба режима меняют данные в --data, берите копию. Каталоги настоящих данных LevelUp
инструмент не трогает: --data — только тестовая папка.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QCoreApplication, Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget  # noqa: E402

from levelup.application.worker import AppController  # noqa: E402
from levelup.config import load_config  # noqa: E402
from levelup.domain.errors import ErrorInfo  # noqa: E402
from levelup.infrastructure.paths import AppPaths  # noqa: E402
from levelup.look import load_sprites  # noqa: E402
from levelup.ui.about import AboutDialog  # noqa: E402
from levelup.ui.collection import CollectionDialog  # noqa: E402
from levelup.ui.dialogs import AddHabitDialog, CategoryCard, TitleInput  # noqa: E402
from levelup.ui.onboarding import OnboardingDialog  # noqa: E402
from levelup.ui.shell import AppShell  # noqa: E402
from levelup.ui.theme import FONT_SMALL, INK_2, apply_theme, make_label  # noqa: E402
from levelup.ui.widgets import (  # noqa: E402
    CheckMark, ElidedLabel, HabitRow, PixelBar, PixelButton, StatusStrip, TierPips,
)

SAVE_ERROR = "Не удалось сохранить. Проверьте доступ к диску и повторите"
ALL = ("main", "overlay", "add", "collection", "about", "onboarding", "states")


def pump(seconds: float = 0.05) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        time.sleep(0.005)


def problems(root: QWidget) -> list[str]:
    """Подписи и кнопки, которым не хватило места: текст обрезан или не умещается по высоте."""
    found = []
    for widget in root.findChildren(QWidget):
        if not widget.isVisible():
            continue
        name = f"{type(widget).__name__}({getattr(widget, 'text', lambda: '')()!r:.40})"
        if isinstance(widget, ElidedLabel):
            if widget.text() != widget.toolTip() and widget.toolTip():
                found.append(f"сокращено: {widget.toolTip()!r}")
        elif isinstance(widget, QLabel) and widget.text():
            if widget.wordWrap():
                if widget.heightForWidth(widget.width()) > widget.height() + 1:
                    found.append(f"не влезает по высоте: {name} {widget.size().width()}x{widget.height()}")
            elif widget.sizeHint().width() > widget.width():
                found.append(f"обрезано по ширине: {name} {widget.width()} < {widget.sizeHint().width()}")
        elif isinstance(widget, PixelButton) and widget.minimumWidth() != widget.maximumWidth():
            if widget.sizeHint().width() > widget.width():
                found.append(f"кнопка уже текста: {name}")
    return found


def states_sheet(config) -> QWidget:
    """Образцы элементов во всех состояниях: кнопки, отметки, полоски, строки, строка состояния, карточки."""
    sheet = QWidget()
    column = QVBoxLayout(sheet)
    column.setContentsMargins(16, 12, 16, 12)
    column.setSpacing(8)

    def row(caption: str, *widgets: QWidget) -> None:
        line = QHBoxLayout()
        line.setSpacing(12)
        line.addWidget(make_label(caption, FONT_SMALL, color=INK_2))
        line.itemAt(0).widget().setFixedWidth(96)
        for widget in widgets:
            line.addWidget(widget)
        line.addStretch(1)
        column.addLayout(line)

    pressed, focused, checked = PixelButton("Нажата"), PixelButton("Фокус"), PixelButton("Включена")
    pressed.setDown(True)
    focused.keyboard_focus = True
    checked.setCheckable(True)
    checked.setChecked(True)
    off = PixelButton("Недоступна")
    off.setEnabled(False)
    kinds = (
        PixelButton("Обычная"), PixelButton("Главная", "primary"), PixelButton("Мини", "mini"), PixelButton("···", "ghost")
    )
    row("кнопки", *kinds, off)
    row("состояния", pressed, focused, checked)
    marks = []
    for done, kb, busy in (
        (False, False, False), (True, False, False), (False, True, False), (True, True, False), (True, False, True)
    ):
        mark = CheckMark()
        mark.setChecked(done)
        mark.keyboard_focus = kb
        mark.set_busy(busy)
        marks.append(mark)
    row("отметки", *marks)
    bars = [PixelBar(parent=None) for _ in range(3)]
    for bar, (value, maximum) in zip(bars, ((0, 100), (35, 100), (100, 100))):
        bar.set_progress(value, maximum, animate=False)
        bar.setFixedWidth(120)
    pips = []
    for filled in range(4):
        pip = TierPips()
        pip.set_state(filled, "#d0613a")
        pips.append(pip)
    row("полоски", *bars)
    row("тиры", *pips)
    for habit, title, done in (("a", "Зарядка 10 минут", False), ("b", "Прочитать главу и выписать цитаты " * 3, True)):
        item = HabitRow(habit, title.strip(), "sport" if habit == "a" else "study", done, "Спорт")
        item.setFixedWidth(360)
        row("строка", item)
    compact = HabitRow("c", "Компактная строка виджета", "work", False, "Работа", compact=True)
    compact.setFixedWidth(260)
    row("виджет", compact)
    strips = []
    for state in ("saving", "error", "notice", "warning"):
        strip = StatusStrip()
        strip.setFixedWidth(260)
        if state == "saving":
            strip.set_saving(True)
        elif state == "error":
            strip.set_error(ErrorInfo("STORAGE_ERROR", SAVE_ERROR, None, True))
        elif state == "notice":
            strip.show_notice("Наступил новый день. Отметьте выполнение снова")
        else:
            strip.set_warning("clock", "Часы отстают — отметки заблокированы.")
        strips.append(strip)
    row("состояние", *strips)
    cards = [CategoryCard(config.categories[i]) for i in (0, 1, 2)]
    cards[1].setChecked(True)
    cards[2].setChecked(True)
    cards[2].keyboard_focus = True
    row("карточки", *cards)
    fields = [TitleInput(80, "Название") for _ in range(2)]
    fields[1].edit.setText("Привычка")
    fields[1].show_error("Привычка с таким названием уже есть.")
    for field in fields:
        field.setFixedWidth(260)
    row("поля", *fields)
    sheet.setMinimumHeight(sheet.layout().totalHeightForWidth(1216) if sheet.layout().hasHeightForWidth() else 640)
    return sheet


def save(widget: QWidget, out: Path, name: str, check: bool) -> None:
    pump()
    path = out / f"{name}.png"
    widget.grab().save(str(path))
    print(path, f"{widget.width()}x{widget.height()}")
    if check:
        for line in problems(widget):
            print("  !", line)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out")
    parser.add_argument("--data", help="папка данных, созданная tools/make_demo.py")
    parser.add_argument("--prefix", default="")
    parser.add_argument("--size", default="1000x660", help="размер основного окна, например 800x560")
    parser.add_argument("--only", default=",".join(ALL))
    parser.add_argument("--focus", action="store_true", help="поставить на первую отметку клавиатурный фокус")
    parser.add_argument("--done", type=int, default=0, help="отметить первые N привычек")
    parser.add_argument("--state", choices=("error", "warning"), help="ошибка с «Повторить» или предупреждение о часах")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    only = set(args.only.split(","))

    app = QApplication([])
    apply_theme(app)
    config = load_config()
    manifest = load_sprites(config)

    if only & {"onboarding"}:
        stub = SimpleNamespace(config=config, manifest=manifest, detected_timezone="Europe/Moscow", controller=None)
        dialog = OnboardingDialog(stub)
        dialog.show()
        save(dialog, out, f"{args.prefix}onboarding_1_{dialog.base_id()}", args.check)
        dialog.heroes["w"].click()
        dialog._go(0)
        save(dialog, out, f"{args.prefix}onboarding_1_w", args.check)
        dialog._go(1)
        save(dialog, out, f"{args.prefix}onboarding_2", args.check)
        dialog.close()

    if "states" in only:
        sheet = states_sheet(config)
        sheet.show()
        save(sheet, out, f"{args.prefix}states", args.check)

    if not args.data or not only & {"main", "overlay", "add", "collection", "about"}:
        return 0
    paths = AppPaths.for_dir(args.data)
    controller = AppController(paths, config)
    shell = AppShell(app, controller, manifest, config, "UTC")
    controller.start()
    end = time.monotonic() + 10
    while shell.main is None and time.monotonic() < end:
        pump(0.02)
    if shell.main is None:
        print("окна не появились: проверьте --data", file=sys.stderr)
        return 1
    main_window, overlay = shell.main, shell.overlay
    for habit in controller.snapshot.habits[: args.done]:
        controller.toggle_habit(habit.id, True)
    end = time.monotonic() + 5
    while sum(h.done_today for h in controller.snapshot.habits) < args.done and time.monotonic() < end:
        pump(0.02)
    if args.state == "error":
        controller.error_occurred.emit(ErrorInfo("STORAGE_ERROR", SAVE_ERROR, None, True))
    elif args.state == "warning":
        snapshot = replace(controller.snapshot, clock_rollback=True)
        main_window.apply_snapshot(snapshot)
        overlay.apply_snapshot(snapshot)
    width, height = (int(v) for v in args.size.split("x"))
    main_window.resize(width, height)
    main_window.show()
    if "main" in only:
        if args.focus and main_window._rows:
            main_window._rows[0].mark.setFocus(Qt.FocusReason.TabFocusReason)
        save(main_window, out, f"{args.prefix}main_{width}x{height}", args.check)
    if "overlay" in only:
        overlay.restore_position(controller.snapshot)
        overlay.show()
        save(overlay, out, f"{args.prefix}overlay", args.check)
    if "add" in only:
        dialog = AddHabitDialog(controller, config)
        dialog.show()
        dialog.field.edit.setText("Читать по вечерам")
        dialog.chooser.set_category("study")
        save(dialog, out, f"{args.prefix}add", args.check)
    if "collection" in only:
        dialog = CollectionDialog(controller.snapshot, config)
        dialog.show()
        save(dialog, out, f"{args.prefix}collection", args.check)
    if "about" in only:
        dialog = AboutDialog()
        dialog.show()
        save(dialog, out, f"{args.prefix}about", args.check)
    controller.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
