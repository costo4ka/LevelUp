"""Qt-worker и контроллер.

Все обращения к SQLite (запись, миграции и чтение снимка) выполняются последовательно в одном
отдельном потоке: соединение создаётся и используется только там. Интерфейс живёт в потоке GUI,
отправляет команды через AppController и получает результат сигналами. Сигнал state_changed
уходит обоим окнам только после COMMIT.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from PyQt6.QtCore import QMetaObject, QObject, Qt, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QGuiApplication

from ..config import AppConfig
from ..domain.clock import Clock, SystemClock
from ..domain.errors import ErrorCode, ErrorInfo, Result, make_error
from ..domain.models import RewardEvent, Snapshot
from ..infrastructure.db import DatabaseOpenError, open_database
from ..infrastructure.paths import AppPaths
from ..infrastructure.repository import Repository
from .service import AppService

log = logging.getLogger("levelup.worker")

DAY_CHANGED_TEXT = "Наступил новый день. Отметьте выполнение снова"


class ServiceWorker(QObject):
    initialized = pyqtSignal(object)  # Result первого get_snapshot
    init_failed = pyqtSignal(str)
    command_finished = pyqtSignal(int, str, object)  # request_id, command, Result

    def __init__(self, paths: AppPaths, config: AppConfig, clock: Clock):
        super().__init__()
        self._paths, self._config, self._clock = paths, config, clock
        self._conn = None
        self._service: AppService | None = None

    @pyqtSlot()
    def initialize(self) -> None:
        try:
            self._conn = open_database(self._paths, self._config.db_busy_timeout_ms)
            self._service = AppService(Repository(self._conn), self._clock, self._config)
            result = self._service.get_snapshot()
        except DatabaseOpenError as exc:
            self.init_failed.emit(exc.user_message)
            return
        except Exception:  # noqa: BLE001
            log.exception("code=STORAGE_ERROR op=initialize")
            self.init_failed.emit("Не удалось запустить приложение. Подробности — в журнале.")
            return
        if result.ok:
            self.initialized.emit(result)
        else:
            self.init_failed.emit(result.error.message)

    @pyqtSlot(int, str, object)
    def run(self, request_id: int, command: str, payload: object) -> None:
        if self._service is None:
            result = Result.failure(make_error(ErrorCode.STORAGE_ERROR).info())
        else:
            result = self._service.execute(command, payload)  # type: ignore[arg-type]
        self.command_finished.emit(request_id, command, result)

    @pyqtSlot()
    def close_db(self) -> None:
        if self._conn is not None:
            self._conn.close()
        self._conn, self._service = None, None


@dataclass
class _Pending:
    command: str
    payload: dict[str, Any]
    callback: Callable[[Result], None] | None
    habit_id: str | None
    quiet: bool  # без «Сохраняем…» и без баннера ошибки (опрос даты, позиция виджета, диалоги)


class AppController(QObject):
    ready = pyqtSignal(object)  # первый подтверждённый Snapshot
    startup_failed = pyqtSignal(str)
    state_changed = pyqtSignal(object)  # Snapshot, подтверждённый записью
    reward = pyqtSignal(object)  # RewardEvent: после state_changed, только для успешной отметки или отмены
    pending_changed = pyqtSignal()
    saving_changed = pyqtSignal(bool)
    notice = pyqtSignal(str)
    error_occurred = pyqtSignal(object)  # ErrorInfo
    error_cleared = pyqtSignal()
    _request = pyqtSignal(int, str, object)

    def __init__(
        self,
        paths: AppPaths,
        config: AppConfig,
        clock: Clock | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.config = config
        self.snapshot: Snapshot | None = None
        self._pending: dict[int, _Pending] = {}
        self._next_id = 0
        self._saving = False
        self._last_failed: tuple[str, dict[str, Any], str | None] | None = None

        self._thread = QThread()
        self._worker = ServiceWorker(paths, config, clock or SystemClock())
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.initialize)
        self._worker.initialized.connect(self._on_initialized)
        self._worker.init_failed.connect(self.startup_failed)
        self._worker.command_finished.connect(self._on_finished)
        self._request.connect(self._worker.run)

        self._timer = QTimer(self)
        self._timer.setInterval(config.date_poll_seconds * 1000)
        self._timer.timeout.connect(self.request_snapshot)
        app = QGuiApplication.instance()
        if app is not None:  # возвращение в приложение (в т.ч. после сна) — сразу проверяем дату
            app.applicationStateChanged.connect(self._on_app_state)

    # ------------------------------------------------------------------ жизненный цикл
    def start(self) -> None:
        self._thread.start()

    def shutdown(self) -> None:
        self._timer.stop()
        if self._thread.isRunning():
            QMetaObject.invokeMethod(self._worker, "close_db", Qt.ConnectionType.BlockingQueuedConnection)
            self._thread.quit()
            self._thread.wait(5000)

    # ------------------------------------------------------------------ команды
    def submit(
        self,
        command: str,
        payload: dict[str, Any] | None = None,
        *,
        callback: Callable[[Result], None] | None = None,
        habit_id: str | None = None,
        quiet: bool = False,
    ) -> int:
        self._next_id += 1
        request_id = self._next_id
        data = dict(payload or {})
        self._pending[request_id] = _Pending(command, data, callback, habit_id, quiet)
        self._refresh_pending()
        self._request.emit(request_id, command, data)
        return request_id

    def toggle_habit(self, habit_id: str, completed: bool) -> None:
        if self.snapshot is None or self.is_habit_pending(habit_id):
            return  # повторные клики во время операции блокируются
        self.submit(
            "set_completion",
            {"habit_id": habit_id, "expected_date": self.snapshot.date, "completed": completed},
            habit_id=habit_id,
        )

    def archive_habit(self, habit_id: str) -> None:
        if not self.is_habit_pending(habit_id):
            self.submit("archive_habit", {"habit_id": habit_id}, habit_id=habit_id)

    def save_overlay(self, enabled: bool, x: int | None, y: int | None, screen_name: str | None) -> None:
        self.submit(
            "save_overlay_settings",
            {"enabled": enabled, "x": x, "y": y, "screen_name": screen_name},
            quiet=True,
        )

    def request_snapshot(self) -> None:
        if not any(p.command == "get_snapshot" for p in self._pending.values()):
            self.submit("get_snapshot", quiet=True)

    def retry_last(self) -> None:
        if self._last_failed is not None:
            command, payload, habit_id = self._last_failed
            self._last_failed = None
            self.error_cleared.emit()
            self.submit(command, payload, habit_id=habit_id)

    # ------------------------------------------------------------------ состояние
    @property
    def busy(self) -> bool:
        return bool(self._pending)

    def is_habit_pending(self, habit_id: str) -> bool:
        return any(p.habit_id == habit_id for p in self._pending.values())

    def _refresh_pending(self) -> None:
        saving = any(not p.quiet for p in self._pending.values())
        if saving != self._saving:
            self._saving = saving
            self.saving_changed.emit(saving)
        self.pending_changed.emit()

    def _apply(self, snap: Snapshot) -> None:
        old = self.snapshot
        if old is not None and snap.date != old.date:
            self.notice.emit(DAY_CHANGED_TEXT)
        if snap != old:
            self.snapshot = snap
            self.state_changed.emit(snap)

    def _emit_reward(self, before: Snapshot, after: Snapshot | None, pending: _Pending) -> None:
        habit = next((h for h in before.habits if h.id == pending.payload.get("habit_id")), None)
        if habit is None or after is None:
            return
        completed = bool(pending.payload.get("completed"))
        was, now = set(before.unlocked), set(after.unlocked)
        self.reward.emit(
            RewardEvent(
                kind="complete" if completed else "undo",
                habit_id=habit.id,
                category=habit.category,
                xp_delta=after.total_xp - before.total_xp,
                new_unlocks=tuple(u for u in after.unlocked if u not in was),
                lost_unlocks=tuple(u for u in before.unlocked if u not in now),
                stage_before=before.stage,
                stage_after=after.stage,
                day_completed=completed and after.day_complete and not before.day_complete,
                before=before,
                after=after,
            )
        )

    @pyqtSlot(object)
    def _on_initialized(self, result: Result) -> None:
        self.snapshot = Snapshot.from_dict(result.data)  # type: ignore[arg-type]
        self._timer.start()
        self.ready.emit(self.snapshot)

    @pyqtSlot(int, str, object)
    def _on_finished(self, request_id: int, command: str, result: Result) -> None:
        pending = self._pending.pop(request_id, None)
        if pending is None:
            return
        if result.ok:
            data = result.data or {}
            raw = data.get("snapshot", data if "habits" in data else None)
            before = self.snapshot
            if raw is not None:
                self._apply(Snapshot.from_dict(raw))
            if pending.command == "set_completion" and data.get("changed") and before is not None:
                self._emit_reward(before, self.snapshot, pending)
            if not pending.quiet:
                self._last_failed = None
                self.error_cleared.emit()
        else:
            error: ErrorInfo = result.error  # type: ignore[assignment]
            if error.code == ErrorCode.DATE_CHANGED.value:
                self.request_snapshot()  # новый снимок покажет список нового дня и сообщение
            elif not pending.quiet:
                self._last_failed = (pending.command, pending.payload, pending.habit_id) if error.retryable else None
                self.error_occurred.emit(error)
        self._refresh_pending()
        if pending.callback is not None:
            pending.callback(result)

    @pyqtSlot(Qt.ApplicationState)
    def _on_app_state(self, state: Qt.ApplicationState) -> None:
        if state == Qt.ApplicationState.ApplicationActive and self.snapshot is not None:
            self.request_snapshot()
