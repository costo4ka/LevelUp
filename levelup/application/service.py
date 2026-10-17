"""AppService — единственное место правил: очки, дата, лимиты, идемпотентность.

И основное окно, и оверлей вызывают одни и те же команды. Ответ — Result {ok, data, error};
наружу не уходят исключения SQLite и пути к файлам пользователя. Qt здесь не используется.
"""
from __future__ import annotations

import logging
import sqlite3
import unicodedata
import uuid
from datetime import date
from functools import lru_cache
from typing import Any, Callable
from zoneinfo import ZoneInfo

from ..config import AppConfig
from ..domain import rules
from ..domain.clock import Clock
from ..domain.errors import AppError, ErrorCode, Result, make_error
from ..domain.models import CategoryView, HabitView, Snapshot
from ..infrastructure.repository import HabitRecord, Profile, Repository

log = logging.getLogger("levelup.service")

# команда: (обязательные поля, необязательные поля)
_COMMANDS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "create_habit": (("title", "category"), ()),
    "set_completion": (("habit_id", "expected_date", "completed"), ()),
    "get_snapshot": ((), ()),
    "archive_habit": (("habit_id",), ()),
    "save_overlay_settings": (("enabled",), ("x", "y", "screen_name")),
    "finish_onboarding": (("timezone_id", "title", "category"), ("base_id",)),
}
_COORD_LIMIT = 100_000
CALENDAR_DAYS = 35  # окно календаря: пять недель


@lru_cache(maxsize=8)
def _zone(key: str) -> ZoneInfo:
    return ZoneInfo(key)


def _validation(message: str, field: str | None = None) -> AppError:
    return make_error(ErrorCode.VALIDATION_ERROR, message, field)


class AppService:
    def __init__(self, repo: Repository, clock: Clock, config: AppConfig):
        self.repo, self.clock, self.config = repo, clock, config

    # ------------------------------------------------------------------ диспетчер
    def execute(self, command: str, payload: dict[str, Any] | None = None) -> Result:
        """Вызов по имени с проверкой полей: неизвестное или пропущенное поле — VALIDATION_ERROR."""
        spec = _COMMANDS.get(command) if isinstance(command, str) else None
        try:
            if spec is None:
                raise _validation("Неизвестная команда.")
            payload = {} if payload is None else payload
            if not isinstance(payload, dict):
                raise _validation("Параметры команды должны быть объектом.")
            required, optional = spec
            for name in payload:
                if name not in required and name not in optional:
                    raise _validation(f"Неизвестное поле: {name}.", str(name))
            for name in required:
                if name not in payload:
                    raise _validation(f"Не передано поле: {name}.", name)
        except AppError as exc:
            return Result.failure(exc.info())
        return getattr(self, command)(**payload)

    # ------------------------------------------------------------------ команды
    def get_snapshot(self) -> Result:
        def op() -> dict[str, Any]:
            return self._snapshot(self._local_date(self.repo.get_profile())).to_dict()

        return self._guard("get_snapshot", op)

    def create_habit(self, title: Any, category: Any) -> Result:
        def op() -> dict[str, Any]:
            clean = rules.normalize_title(title, self.config.title_max_length)
            kind = self._category(category)
            with self.repo.transaction():
                profile, today = self._begin()
                if not profile.onboarding_done:
                    raise _validation("Сначала завершите первичную настройку.")
                habit_id = self._insert_habit(clean, kind, today)
                self._touch_last_seen(profile, today)
            return {"habit_id": habit_id, "snapshot": self._snapshot(today).to_dict()}

        return self._guard("create_habit", op)

    def set_completion(self, habit_id: Any, expected_date: Any, completed: Any) -> Result:
        def op() -> dict[str, Any]:
            hid = rules.parse_uuid(habit_id, "habit_id")
            expected = rules.parse_iso_date(expected_date, "expected_date")
            if not isinstance(completed, bool):
                raise _validation("Поле completed должно быть true или false.", "completed")
            with self.repo.transaction():
                profile, today = self._begin()  # дата фиксируется в начале транзакции
                if expected != today:
                    raise make_error(ErrorCode.DATE_CHANGED)
                self._active_habit(hid, today)
                if completed:
                    changed = self.repo.insert_completion(
                        hid, today, self._utc_stamp(), self.config.xp_per_completion
                    )
                else:
                    changed = self.repo.delete_completion(hid, today)
                self._touch_last_seen(profile, today)
            return {"changed": changed, "snapshot": self._snapshot(today).to_dict()}

        return self._guard("set_completion", op)

    def archive_habit(self, habit_id: Any) -> Result:
        def op() -> dict[str, Any]:
            hid = rules.parse_uuid(habit_id, "habit_id")
            with self.repo.transaction():
                profile, today = self._begin()
                self._active_habit(hid, today)
                self.repo.delete_completion(hid, today)  # сегодняшняя отметка снимается в той же транзакции
                self.repo.archive_habit(hid, today)
                self._touch_last_seen(profile, today)
            return {"snapshot": self._snapshot(today).to_dict()}

        return self._guard("archive_habit", op)

    def save_overlay_settings(self, enabled: Any, x: Any = None, y: Any = None, screen_name: Any = None) -> Result:
        def op() -> dict[str, Any]:
            if not isinstance(enabled, bool):
                raise _validation("Поле enabled должно быть true или false.", "enabled")
            nx, ny = self._coordinate(x, "x"), self._coordinate(y, "y")
            if (nx is None) != (ny is None):
                raise _validation("Укажите обе координаты.", "x")
            name = self._screen_name(screen_name)
            with self.repo.transaction():
                self.repo.save_overlay(enabled, nx, ny, name)
            return {"snapshot": self._snapshot(self._local_date(self.repo.get_profile())).to_dict()}

        return self._guard("save_overlay_settings", op)

    def finish_onboarding(self, timezone_id: Any, title: Any, category: Any, base_id: Any = None) -> Result:
        def op() -> dict[str, Any]:
            if not isinstance(timezone_id, str):
                raise _validation("Выберите часовой пояс.", "timezone_id")
            try:
                tz = _zone(timezone_id)
            except (KeyError, ValueError, OSError):
                raise _validation("Неизвестный часовой пояс.", "timezone_id") from None
            base = self.config.default_base if base_id is None else base_id
            if not isinstance(base, str) or base not in self.config.character_bases:
                raise _validation("Выберите персонажа.", "base_id")
            clean = rules.normalize_title(title, self.config.title_max_length)
            kind = self._category(category)
            with self.repo.transaction():
                if self.repo.get_profile().onboarding_done:
                    raise _validation("Первичная настройка уже выполнена.")
                today = self.clock.now_utc().astimezone(tz).date()
                self.repo.finish_onboarding(base, timezone_id, today)
                habit_id = self._insert_habit(clean, kind, today)
            return {"habit_id": habit_id, "snapshot": self._snapshot(today).to_dict()}

        return self._guard("finish_onboarding", op)

    # ------------------------------------------------------------------ внутреннее
    def _guard(self, operation: str, fn: Callable[[], dict[str, Any]]) -> Result:
        try:
            return Result.success(fn())
        except AppError as exc:
            log.info("op=%s code=%s", operation, exc.code.value)
            return Result.failure(exc.info())
        except sqlite3.OperationalError as exc:
            text = str(exc).lower()
            code = ErrorCode.DATABASE_BUSY if ("locked" in text or "busy" in text) else ErrorCode.STORAGE_ERROR
            log.warning("op=%s code=%s detail=%s", operation, code.value, exc)
            return Result.failure(make_error(code).info())
        except (sqlite3.Error, OSError) as exc:
            log.error("op=%s code=STORAGE_ERROR detail=%s: %s", operation, type(exc).__name__, exc)
            return Result.failure(make_error(ErrorCode.STORAGE_ERROR).info())
        except Exception:  # noqa: BLE001 — интерфейс не должен получать необработанные исключения
            log.exception("op=%s code=STORAGE_ERROR unexpected", operation)
            return Result.failure(make_error(ErrorCode.STORAGE_ERROR).info())

    def _local_date(self, profile: Profile) -> date:
        return self.clock.now_utc().astimezone(_zone(profile.timezone_id)).date()

    def _begin(self) -> tuple[Profile, date]:
        """Начало записывающей транзакции: фиксирует дату и блокирует запись при откате часов."""
        profile = self.repo.get_profile()
        today = self._local_date(profile)
        if today < profile.last_seen_date:
            raise make_error(ErrorCode.CLOCK_ROLLBACK)
        return profile, today

    def _touch_last_seen(self, profile: Profile, today: date) -> None:
        if today > profile.last_seen_date:
            self.repo.set_last_seen(today)

    def _utc_stamp(self) -> str:
        return self.clock.now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")

    def _category(self, value: Any) -> str:
        if not isinstance(value, str) or value not in self.config.category_ids:
            raise _validation("Выберите категорию привычки.", "category")
        return value

    def _insert_habit(self, clean_title: str, category: str, today: date) -> str:
        """Проверка лимитов и дубля + вставка. Вызывается внутри транзакции."""
        cfg = self.config
        if self.repo.count_all() >= cfg.max_total_habits:
            raise make_error(
                ErrorCode.STORAGE_LIMIT, f"Достигнут предел истории: {cfg.max_total_habits} привычек."
            )
        if self.repo.count_active() >= cfg.max_active_habits:
            raise make_error(
                ErrorCode.HABIT_LIMIT,
                f"Можно вести не более {cfg.max_active_habits} активных привычек. Архивируйте одну из них.",
            )
        key = rules.title_key(clean_title)
        if any(rules.title_key(h.title) == key for h in self.repo.active_habits()):
            raise make_error(ErrorCode.DUPLICATE_TITLE, field="title")
        habit_id = str(uuid.uuid4())
        self.repo.insert_habit(habit_id, clean_title, category, self.repo.next_sort_order(), self._utc_stamp(), today)
        return habit_id

    def _active_habit(self, habit_id: str, today: date) -> HabitRecord:
        habit = self.repo.get_habit(habit_id)
        if habit is None:
            raise make_error(ErrorCode.NOT_FOUND)
        if habit.archived_date is not None:
            raise make_error(ErrorCode.HABIT_NOT_ACTIVE)
        if today < habit.start_date:  # защитная проверка: недостижима при корректном last_seen_date
            raise make_error(ErrorCode.CLOCK_ROLLBACK)
        return habit

    @staticmethod
    def _coordinate(value: Any, field: str) -> int | None:
        if value is None:
            return None
        if type(value) is not int:
            raise _validation("Координата должна быть целым числом.", field)
        return max(-_COORD_LIMIT, min(_COORD_LIMIT, value))

    @staticmethod
    def _screen_name(value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or any(unicodedata.category(c) == "Cc" for c in value):
            raise _validation("Некорректное имя монитора.", "screen_name")
        return value.strip()[:200] or None

    def _snapshot(self, today: date) -> Snapshot:
        repo, cfg = self.repo, self.config
        profile, settings = repo.get_profile(), repo.get_settings()
        done = repo.completed_ids(today)
        habits = tuple(HabitView(h.id, h.title, h.category, h.id in done) for h in repo.active_habits())
        total_xp, completions = repo.totals()
        stage = rules.stage_for(total_xp, cfg.stage_thresholds)
        nxt = rules.next_threshold(stage, cfg.stage_thresholds)
        ranges, counts = repo.habit_ranges(), repo.planned_completion_counts()
        points = repo.category_points()
        categories = []
        unlocked: list[str] = []
        for item in cfg.categories:
            earned = points.get(item.id, 0)
            tier = rules.category_tier(earned, cfg.category_tiers)
            categories.append(CategoryView(item.id, earned, tier, rules.next_tier_at(tier, cfg.category_tiers)))
            unlocked.extend(u.id for u in item.unlocks[:tier])
        full = rules.full_days(today, CALENDAR_DAYS, ranges, counts)
        return Snapshot(
            date=today.isoformat(),
            habits=habits,
            total_xp=total_xp,
            stage=stage,
            stage_count=cfg.stage_count,
            stage_name=cfg.stage_names[stage - 1],
            next_threshold=nxt,
            xp_to_next=rules.xp_to_next(total_xp, nxt),
            streak_days=rules.compute_streak(today, ranges, counts),
            all_time_completions=completions,
            categories=tuple(categories),
            unlocked=tuple(unlocked),
            day_complete=bool(full) and full[-1] == today,
            full_days=tuple(d.isoformat() for d in full),
            overlay_enabled=settings.overlay_enabled,
            overlay_x=settings.overlay_x,
            overlay_y=settings.overlay_y,
            screen_name=settings.screen_name,
            base_id=profile.base_id,
            onboarding_done=profile.onboarding_done,
            clock_rollback=today < profile.last_seen_date,
            max_active_habits=cfg.max_active_habits,
        )
