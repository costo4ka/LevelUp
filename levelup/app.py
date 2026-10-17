"""Точка входа: окружение, единственный экземпляр, worker и окна."""
from __future__ import annotations

import logging
import os
import sys

from . import __version__
from .config import ASSETS_DIR, ConfigError, load_config
from .infrastructure.tz import detect_timezone  # noqa: F401 — используется окнами и инструментами

log = logging.getLogger("levelup.app")


def log_unhandled(exc_type, exc, tb) -> None:
    """Исключение в слоте Qt: пишем в журнал и продолжаем. Без своего excepthook PyQt6 завершает процесс через qFatal."""
    log.critical("code=STORAGE_ERROR op=unhandled", exc_info=(exc_type, exc, tb))


def main(argv: list[str] | None = None) -> int:
    if sys.platform.startswith("linux") and "QT_QPA_PLATFORM" not in os.environ and os.environ.get("DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "xcb"  # Wayland не даёт окнам задавать позицию и «поверх всех»
    if os.environ.get("QT_QPA_PLATFORM") == "xcb":
        import ctypes.util

        if not ctypes.util.find_library("xcb-cursor"):  # без неё Qt 6.5+ не загружает плагин xcb
            print("Для запуска на Linux (X11) установите библиотеку: sudo apt install libxcb-cursor0", file=sys.stderr)
            return 1

    from PyQt6.QtCore import QLockFile
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication, QMessageBox

    from .application.worker import AppController
    from .infrastructure.logging_setup import setup_logging
    from .infrastructure.paths import AppPaths
    from .look import check_sprite_files, load_sprites
    from .ui.palette import load_fonts
    from .ui.shell import AppShell
    from .ui.theme import apply_theme

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("LevelUp")
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)  # закрытие основного окна не должно убивать работающий виджет
    load_fonts()
    apply_theme(app)  # Fusion, тёплая палитра, шрифт, стили
    icon = ASSETS_DIR / "icon.png"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    def fatal(text: str) -> int:
        QMessageBox.critical(None, "LevelUp", text)
        return 1

    try:
        paths = AppPaths.default()
        paths.ensure()
    except OSError:
        return fatal("Не удалось создать каталог данных. Проверьте права доступа к профилю пользователя.")
    setup_logging(paths.logs)
    sys.excepthook = log_unhandled

    lock = QLockFile(str(paths.lock))
    lock.setStaleLockTime(0)  # иначе второй экземпляр через 30 с сочтёт блокировку живого процесса устаревшей
    if not lock.tryLock(0):
        if lock.error() == QLockFile.LockError.LockFailedError:
            QMessageBox.information(None, "LevelUp", "LevelUp уже запущен. Найдите его виджет или значок на панели задач.")
            return 0
        return fatal("Не удалось создать файл блокировки в каталоге данных. Проверьте права записи.")

    try:
        config = load_config()
        manifest = load_sprites(config)
    except ConfigError as exc:
        log.error("code=VALIDATION_ERROR op=load_config detail=%s", exc)
        lock.unlock()
        return fatal(f"Поставка приложения повреждена: {exc}")
    for problem in check_sprite_files(manifest):
        log.warning("code=ASSET_MISSING op=check_sprites detail=%s", problem)

    controller = AppController(paths, config)
    shell = AppShell(app, controller, manifest, config, detect_timezone())
    app.aboutToQuit.connect(controller.shutdown)
    controller.start()
    code = app.exec()
    lock.unlock()
    del shell
    return code
