"""Снимок состояния, который сервис отдаёт интерфейсу (Python DTO = JSON-контракт)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HabitView:
    id: str
    title: str
    category: str
    done_today: bool


@dataclass(frozen=True)
class CategoryView:
    id: str
    points: int  # число отметок привычек этой категории (включая архивные)
    tier: int  # сколько предметов категории уже открыто (0..3)
    next_at: int | None  # очки, с которых откроется следующий предмет; None — всё открыто


@dataclass(frozen=True)
class Snapshot:
    date: str
    habits: tuple[HabitView, ...]
    total_xp: int
    stage: int
    stage_count: int
    stage_name: str
    next_threshold: int | None
    xp_to_next: int
    streak_days: int
    all_time_completions: int
    categories: tuple[CategoryView, ...]
    unlocked: tuple[str, ...]  # идентификаторы открытых предметов: sport_1, work_2 ...
    day_complete: bool  # все запланированные на сегодня привычки выполнены
    full_days: tuple[str, ...]  # ISO-даты полных дней за последние 35 дней (для календаря)
    overlay_enabled: bool
    overlay_x: int | None
    overlay_y: int | None
    screen_name: str | None
    base_id: str
    onboarding_done: bool
    clock_rollback: bool
    max_active_habits: int

    _NESTED = ("habits", "categories", "unlocked", "full_days")

    @property
    def tiers(self) -> dict[str, int]:
        return {c.id: c.tier for c in self.categories}

    def category(self, category_id: str) -> CategoryView | None:
        return next((c for c in self.categories if c.id == category_id), None)

    def to_dict(self) -> dict[str, Any]:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__ if k not in self._NESTED}
        d["habits"] = [
            {"id": h.id, "title": h.title, "category": h.category, "done_today": h.done_today} for h in self.habits
        ]
        d["categories"] = [
            {"id": c.id, "points": c.points, "tier": c.tier, "next_at": c.next_at} for c in self.categories
        ]
        d["unlocked"] = list(self.unlocked)
        d["full_days"] = list(self.full_days)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Snapshot":
        fields = {k: d[k] for k in cls.__dataclass_fields__ if k not in cls._NESTED}
        return cls(
            habits=tuple(HabitView(h["id"], h["title"], h["category"], h["done_today"]) for h in d["habits"]),
            categories=tuple(CategoryView(c["id"], c["points"], c["tier"], c["next_at"]) for c in d["categories"]),
            unlocked=tuple(d["unlocked"]),
            full_days=tuple(d["full_days"]),
            **fields,
        )


@dataclass(frozen=True)
class RewardEvent:
    """Что изменила успешная отметка или её отмена: по этому событию интерфейс рисует награду."""

    kind: str  # "complete" | "undo"
    habit_id: str
    category: str
    xp_delta: int
    new_unlocks: tuple[str, ...]
    lost_unlocks: tuple[str, ...]
    stage_before: int
    stage_after: int
    day_completed: bool  # эта отметка закрыла последнюю невыполненную привычку дня
    before: Snapshot  # состояние до действия
    after: Snapshot  # состояние после действия (то же, что только что пришло в state_changed)
