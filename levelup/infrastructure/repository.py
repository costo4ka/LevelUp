"""Repository: весь SQL и транзакции. Все пользовательские значения — параметрами."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from typing import Iterator

from .db import rollback


@dataclass(frozen=True)
class Profile:
    base_id: str
    style_id: str
    timezone_id: str
    onboarding_done: bool
    last_seen_date: date


@dataclass(frozen=True)
class Settings:
    overlay_enabled: bool
    overlay_x: int | None
    overlay_y: int | None
    screen_name: str | None
    schema_version: int


@dataclass(frozen=True)
class HabitRecord:
    id: str
    title: str
    sort_order: int
    created_at_utc: str
    start_date: date
    archived_date: date | None
    category: str


def _habit(row: sqlite3.Row) -> HabitRecord:
    archived = row["archived_date"]
    return HabitRecord(
        row["id"],
        row["title"],
        row["sort_order"],
        row["created_at_utc"],
        date.fromisoformat(row["start_date"]),
        date.fromisoformat(archived) if archived else None,
        row["category"],
    )


_HABIT_COLUMNS = "id, title, sort_order, created_at_utc, start_date, archived_date, category"


class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """BEGIN IMMEDIATE ... COMMIT; при любой ошибке (в т.ч. COMMIT) — ROLLBACK."""
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.conn.execute("COMMIT")
        except BaseException:
            rollback(self.conn)
            raise

    # --- профиль и настройки -------------------------------------------------
    def get_profile(self) -> Profile:
        r = self.conn.execute(
            "SELECT base_id, style_id, timezone_id, onboarding_done, last_seen_date FROM profile WHERE id = 1"
        ).fetchone()
        return Profile(
            r["base_id"], r["style_id"], r["timezone_id"], bool(r["onboarding_done"]), date.fromisoformat(r["last_seen_date"])
        )

    def finish_onboarding(self, base_id: str, timezone_id: str, last_seen: date) -> None:
        self.conn.execute(
            "UPDATE profile SET base_id = ?, timezone_id = ?, onboarding_done = 1, last_seen_date = ? WHERE id = 1",
            (base_id, timezone_id, last_seen.isoformat()),
        )

    def set_last_seen(self, day: date) -> None:
        self.conn.execute("UPDATE profile SET last_seen_date = ? WHERE id = 1", (day.isoformat(),))

    def get_settings(self) -> Settings:
        r = self.conn.execute(
            "SELECT overlay_enabled, overlay_x, overlay_y, screen_name, schema_version FROM app_settings WHERE id = 1"
        ).fetchone()
        return Settings(bool(r["overlay_enabled"]), r["overlay_x"], r["overlay_y"], r["screen_name"], r["schema_version"])

    def save_overlay(self, enabled: bool, x: int | None, y: int | None, screen_name: str | None) -> None:
        self.conn.execute(
            "UPDATE app_settings SET overlay_enabled = ?, overlay_x = ?, overlay_y = ?, screen_name = ? WHERE id = 1",
            (int(enabled), x, y, screen_name),
        )

    # --- привычки -------------------------------------------------------------
    def active_habits(self) -> list[HabitRecord]:
        rows = self.conn.execute(
            f"SELECT {_HABIT_COLUMNS} FROM habit WHERE archived_date IS NULL ORDER BY sort_order, created_at_utc, id"
        ).fetchall()
        return [_habit(r) for r in rows]

    def get_habit(self, habit_id: str) -> HabitRecord | None:
        r = self.conn.execute(f"SELECT {_HABIT_COLUMNS} FROM habit WHERE id = ?", (habit_id,)).fetchone()
        return _habit(r) if r else None

    def count_active(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM habit WHERE archived_date IS NULL").fetchone()[0]

    def count_all(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM habit").fetchone()[0]

    def next_sort_order(self) -> int:
        return self.conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM habit").fetchone()[0]

    def insert_habit(
        self, habit_id: str, title: str, category: str, sort_order: int, created_at_utc: str, start_date: date
    ) -> None:
        self.conn.execute(
            "INSERT INTO habit (id, title, category, sort_order, created_at_utc, start_date) VALUES (?, ?, ?, ?, ?, ?)",
            (habit_id, title, category, sort_order, created_at_utc, start_date.isoformat()),
        )

    def archive_habit(self, habit_id: str, day: date) -> None:
        self.conn.execute("UPDATE habit SET archived_date = ? WHERE id = ?", (day.isoformat(), habit_id))

    # --- отметки ----------------------------------------------------------------
    def insert_completion(self, habit_id: str, day: date, completed_at_utc: str, xp: int) -> bool:
        """True, если отметка создана; существующая не трогается и не награждается повторно."""
        cur = self.conn.execute(
            "INSERT INTO completion (habit_id, local_date, completed_at_utc, xp_awarded) VALUES (?, ?, ?, ?)"
            " ON CONFLICT (habit_id, local_date) DO NOTHING",
            (habit_id, day.isoformat(), completed_at_utc, xp),
        )
        return cur.rowcount == 1

    def delete_completion(self, habit_id: str, day: date) -> bool:
        cur = self.conn.execute(
            "DELETE FROM completion WHERE habit_id = ? AND local_date = ?", (habit_id, day.isoformat())
        )
        return cur.rowcount == 1

    def completed_ids(self, day: date) -> set[str]:
        rows = self.conn.execute("SELECT habit_id FROM completion WHERE local_date = ?", (day.isoformat(),))
        return {r[0] for r in rows}

    def totals(self) -> tuple[int, int]:
        """(сумма xp_awarded, число отметок)."""
        r = self.conn.execute("SELECT COALESCE(SUM(xp_awarded), 0), COUNT(*) FROM completion").fetchone()
        return r[0], r[1]

    def category_points(self) -> dict[str, int]:
        """Очки категорий: число отметок, включая привычки, которые потом архивировали."""
        rows = self.conn.execute(
            "SELECT h.category, COUNT(*) FROM completion c JOIN habit h ON h.id = c.habit_id GROUP BY h.category"
        )
        return {category: n for category, n in rows}

    # --- данные для серии -------------------------------------------------------
    def habit_ranges(self) -> list[tuple[date, date | None]]:
        rows = self.conn.execute("SELECT start_date, archived_date FROM habit")
        return [
            (date.fromisoformat(s), date.fromisoformat(a) if a else None) for s, a in ((r[0], r[1]) for r in rows)
        ]

    def planned_completion_counts(self) -> dict[date, int]:
        """Число отметок по дням, учитывая только привычки, запланированные в этот день."""
        rows = self.conn.execute(
            "SELECT c.local_date, COUNT(*) FROM completion c JOIN habit h ON h.id = c.habit_id"
            " WHERE c.local_date >= h.start_date AND (h.archived_date IS NULL OR c.local_date < h.archived_date)"
            " GROUP BY c.local_date"
        )
        return {date.fromisoformat(d): n for d, n in rows}
