"""Общие фикстуры и помощники для тестов интерфейса (offscreen): окна с настоящим worker и БД во временной папке."""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QApplication, QWidget

from levelup.application.service import AppService
from levelup.application.worker import AppController
from levelup.domain.clock import FixedClock
from levelup.infrastructure.db import open_database
from levelup.infrastructure.paths import AppPaths
from levelup.infrastructure.repository import Repository
from levelup.look import load_sprites
from levelup.ui.shell import AppShell
from levelup.ui.theme import apply_theme
from tests.helpers import ok

NOW = datetime(2026, 10, 11, 9, 0, tzinfo=timezone.utc)  # воскресенье
FIRST_HABIT = "Английский"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    return app


@pytest.fixture(scope="session")
def manifest(config):
    return load_sprites(config)


def wait_until(predicate, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return False


@pytest.fixture
def shell(qapp, tmp_path, config, manifest):
    """Оба окна поверх настоящего контроллера: героиня «w», первая привычка «Английский» в категории «Учёба»."""
    paths = AppPaths.for_dir(tmp_path)
    paths.ensure()
    clock = FixedClock(NOW)
    conn = open_database(paths, config.db_busy_timeout_ms)
    ok(AppService(Repository(conn), clock, config).finish_onboarding("UTC", FIRST_HABIT, "study", "w"))
    conn.close()
    controller = AppController(paths, config, clock)
    shell = AppShell(qapp, controller, manifest, config, "UTC")
    shell.clock, shell.paths = clock, paths
    controller.start()
    assert wait_until(lambda: shell.main is not None), "окна не появились"
    yield shell
    shell.main.hide()
    shell.overlay.hide()
    controller.shutdown()


def seed_marks(shell, count: int, first_day: date = date(2026, 6, 1)) -> None:
    """Гарантирует каждой привычке `count` прошедших отметок (вторым соединением к той же базе) и обновляет снимок."""
    conn = open_database(shell.paths, 1000)
    conn.execute("UPDATE habit SET start_date = ?", (first_day.isoformat(),))
    rows = [
        (habit_id, (first_day + timedelta(days=i)).isoformat(), "2026-06-01T00:00:00Z", 10)
        for (habit_id,) in conn.execute("SELECT id FROM habit").fetchall()
        for i in range(count)
    ]
    conn.executemany("INSERT OR IGNORE INTO completion VALUES (?, ?, ?, ?)", rows)
    conn.close()
    shell.controller.request_snapshot()


class FakeController:
    """Записывает команды диалогов; callback вызывается тестом вручную, как это делал бы контроллер."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.callback = None

    def submit(self, command, payload=None, *, callback=None, habit_id=None, quiet=False):
        self.calls.append((command, dict(payload or {})))
        self.callback = callback
        return len(self.calls)


def stub_shell(config, manifest, detected="Europe/Moscow"):
    return SimpleNamespace(config=config, manifest=manifest, detected_timezone=detected, controller=FakeController())


def focus_order(first: QWidget, window: QWidget) -> list[QWidget]:
    """Виджеты, до которых доходит Tab, начиная с `first` и до возвращения к нему."""
    order = [first]
    widget = first.nextInFocusChain()
    while widget is not first and len(order) < 200:
        if (
            widget.focusPolicy() & Qt.FocusPolicy.TabFocus
            and widget.isEnabled()
            and widget.isVisibleTo(window)
            and window.isAncestorOf(widget)
        ):
            order.append(widget)
        widget = widget.nextInFocusChain()
    return order
