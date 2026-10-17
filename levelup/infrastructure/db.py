"""SQLite: подключение, миграции и резервные копии (SQLite Backup API)."""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..domain.errors import ErrorCode
from .paths import AppPaths

log = logging.getLogger("levelup.db")

BACKUPS_TO_KEEP = 3
_DATE = "GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'"


class DatabaseOpenError(Exception):
    """База не открыта, запуск невозможен. user_message показывается пользователю при старте."""

    def __init__(self, user_message: str, code: ErrorCode = ErrorCode.STORAGE_ERROR, backup_path: Path | None = None):
        super().__init__(f"{code.value}: {user_message}")
        self.user_message, self.code, self.backup_path = user_message, code, backup_path


def _migrate_v1(conn: sqlite3.Connection) -> None:
    statements = (
        f"""CREATE TABLE profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            base_id TEXT NOT NULL,
            style_id TEXT NOT NULL,
            timezone_id TEXT NOT NULL,
            onboarding_done INTEGER NOT NULL DEFAULT 0 CHECK (onboarding_done IN (0, 1)),
            last_seen_date TEXT NOT NULL CHECK (last_seen_date {_DATE})
        )""",
        """CREATE TABLE app_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            overlay_enabled INTEGER NOT NULL DEFAULT 1 CHECK (overlay_enabled IN (0, 1)),
            overlay_x INTEGER,
            overlay_y INTEGER,
            screen_name TEXT,
            schema_version INTEGER NOT NULL
        )""",
        f"""CREATE TABLE habit (
            id TEXT PRIMARY KEY CHECK (length(id) = 36),
            title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 80),
            sort_order INTEGER NOT NULL CHECK (sort_order >= 0),
            created_at_utc TEXT NOT NULL,
            start_date TEXT NOT NULL CHECK (start_date {_DATE}),
            archived_date TEXT CHECK (archived_date IS NULL OR archived_date {_DATE})
        )""",
        f"""CREATE TABLE completion (
            habit_id TEXT NOT NULL REFERENCES habit (id) ON DELETE RESTRICT,
            local_date TEXT NOT NULL CHECK (local_date {_DATE}),
            completed_at_utc TEXT NOT NULL,
            xp_awarded INTEGER NOT NULL CHECK (xp_awarded = 10),
            PRIMARY KEY (habit_id, local_date)
        )""",
        "CREATE INDEX idx_completion_date ON completion (local_date)",
        "INSERT INTO profile (id, base_id, style_id, timezone_id, onboarding_done, last_seen_date)"
        " VALUES (1, 'm', 'classic', 'UTC', 0, '1970-01-01')",
        "INSERT INTO app_settings (id, overlay_enabled, schema_version) VALUES (1, 1, 1)",
    )
    for statement in statements:
        conn.execute(statement)


def _migrate_v2(conn: sqlite3.Connection) -> None:
    """Категория привычки. Привычки из версии 1 получают «sport» — единственная неизбежная догадка."""
    conn.execute(
        "ALTER TABLE habit ADD COLUMN category TEXT NOT NULL DEFAULT 'sport'"
        " CHECK (category IN ('sport', 'work', 'study', 'social'))"
    )


# (версия, функция). Каждая миграция выполняется в одной транзакции вместе с PRAGMA user_version.
MIGRATIONS: list[tuple[int, Callable[[sqlite3.Connection], None]]] = [(1, _migrate_v1), (2, _migrate_v2)]


def rollback(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("ROLLBACK")
    except sqlite3.Error:  # транзакция уже завершена SQLite
        pass


def connect(path: Path, busy_timeout_ms: int) -> sqlite3.Connection:
    """Соединение живёт и используется только в потоке, который его создал."""
    conn = sqlite3.connect(str(path), timeout=busy_timeout_ms / 1000, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        conn.close()
        raise DatabaseOpenError("Эта сборка SQLite не поддерживает внешние ключи.")
    conn.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
    conn.execute("PRAGMA synchronous=FULL")
    return conn


def _backup(conn: sqlite3.Connection, paths: AppPaths, version: int, now: datetime | None) -> Path:
    paths.backups.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    dest = paths.backups / f"data-{stamp}-v{version}.db"
    counter = 1
    while dest.exists():
        dest = paths.backups / f"data-{stamp}-{counter}-v{version}.db"
        counter += 1
    target = sqlite3.connect(str(dest))
    try:
        conn.backup(target)
    except BaseException:
        target.close()
        dest.unlink(missing_ok=True)
        raise
    target.close()
    for old in sorted(paths.backups.glob("data-*.db"))[:-BACKUPS_TO_KEEP]:
        old.unlink(missing_ok=True)
    return dest


def _migrate(conn: sqlite3.Connection, current: int) -> None:
    for version, step in MIGRATIONS:
        if version <= current:
            continue
        conn.execute("BEGIN IMMEDIATE")
        try:
            step(conn)
            conn.execute("UPDATE app_settings SET schema_version = ? WHERE id = 1", (version,))
            conn.execute(f"PRAGMA user_version = {int(version)}")
            conn.execute("COMMIT")
        except BaseException:
            rollback(conn)
            raise


def open_database(paths: AppPaths, busy_timeout_ms: int = 1000, now: datetime | None = None) -> sqlite3.Connection:
    """Открывает БД, при необходимости делает копию и миграции. Повреждённую БД не заменяет пустой."""
    conn: sqlite3.Connection | None = None
    try:
        conn = connect(paths.db, busy_timeout_ms)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version >= 1:
            verdict = conn.execute("PRAGMA quick_check(1)").fetchone()[0]
            if verdict != "ok":
                raise sqlite3.DatabaseError(f"quick_check: {verdict}")
    except sqlite3.Error as exc:
        if conn:
            conn.close()
        log.error("code=STORAGE_ERROR op=open_database detail=%s", exc)
        raise DatabaseOpenError(
            "Не удалось открыть базу данных: файл повреждён или недоступен. "
            f"Приложение не заменяет его пустым.\nФайл: {paths.db}\nРезервные копии: {paths.backups}"
        ) from exc

    target = MIGRATIONS[-1][0]
    if version > target:
        conn.close()
        raise DatabaseOpenError(
            "База данных создана более новой версией LevelUp. Обновите приложение.", ErrorCode.MIGRATION_FAILED
        )
    if version < target:
        backup: Path | None = None
        try:
            if version >= 1:
                backup = _backup(conn, paths, version, now)
            _migrate(conn, version)
        except Exception as exc:
            conn.close()
            log.error("code=MIGRATION_FAILED op=migrate from=%s to=%s detail=%s", version, target, exc)
            where = f"\nРезервная копия: {backup}" if backup else ""
            raise DatabaseOpenError(
                f"Не удалось обновить базу данных. Исходные данные сохранены без изменений.{where}",
                ErrorCode.MIGRATION_FAILED,
                backup,
            ) from exc
        log.info("op=migrate from=%s to=%s", version, target)
    return conn
