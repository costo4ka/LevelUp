"""Сводки для интерфейса без Qt: русские формы слов, ближайшая награда, прогресс категорий, ячейки календаря."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from ..config import AppConfig, CategoryConfig, UnlockConfig
from ..domain.models import CategoryView, Snapshot

CALENDAR_WEEKS = 5
MARKS = ("отметка", "отметки", "отметок")
_MONTHS = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)
_WEEKDAYS = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
ALL_OPEN_TEXT = "Все предметы открыты — комната обставлена."
DAY_DONE_TEXT = "Всё выполнено"
CLOCK_WARNING = "Системные часы отстают от сохранённой даты — отметки временно заблокированы."
CLOCK_WARNING_SHORT = "Часы отстают — отметки заблокированы."


def plural(n: int, forms: tuple[str, str, str]) -> str:
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11:
        return forms[0]
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        return forms[1]
    return forms[2]


def format_date_ru(d: date) -> str:
    return f"{_WEEKDAYS[d.weekday()]}, {d.day} {_MONTHS[d.month - 1]}"


def format_day_ru(d: date) -> str:
    return f"{d.day} {_MONTHS[d.month - 1]}"


def streak_text(days: int) -> str:
    return f"Серия: {days} {plural(days, ('день', 'дня', 'дней'))}"


def points_text(points: int) -> str:
    return f"{points} {plural(points, ('очко', 'очка', 'очков'))}"


def marks_phrase(left: int, category_name: str) -> str:
    return f"Ещё {left} {plural(left, MARKS)} «{category_name}»"


def opens_verb(unlock_name: str) -> str:
    """«откроются» для названий во множественном числе («Гантели», «Штанга и медаль»), иначе «откроется»."""
    first = unlock_name.split()[0].lower()
    return "откроются" if " и " in unlock_name or first.endswith(("и", "ы")) else "откроется"


def category_label(config: AppConfig, category_id: str) -> str:
    try:
        return config.category(category_id).name
    except KeyError:
        return category_id


@dataclass(frozen=True)
class Reward:
    category: CategoryConfig
    unlock: UnlockConfig
    left: int  # сколько отметок осталось до предмета


def nearest_reward(snap: Snapshot, config: AppConfig) -> Reward | None:
    """Категория, у которой следующий предмет ближе всего (меньше осталось отметок); при ничьей — первая в конфиге."""
    best: Reward | None = None
    for view in snap.categories:
        if view.next_at is None:
            continue
        left = view.next_at - view.points
        if best is None or left < best.left:
            category = config.category(view.id)
            best = Reward(category, category.unlocks[view.tier], left)
    return best


def reward_text(reward: Reward | None) -> str:
    if reward is None:
        return ALL_OPEN_TEXT
    name = reward.unlock.name
    return f"{marks_phrase(reward.left, reward.category.name)} — {opens_verb(name)} «{name}»"


@dataclass(frozen=True)
class CategoryProgress:
    done: int  # очки внутри текущего отрезка (после прошлого порога)
    span: int  # длина отрезка до следующего предмета; при «всё открыто» равна done
    left: int | None  # сколько отметок осталось; None — всё открыто
    unlock: UnlockConfig | None  # следующий предмет


def category_progress(view: CategoryView, config: AppConfig) -> CategoryProgress:
    if view.next_at is None:
        return CategoryProgress(1, 1, None, None)
    tiers = config.category_tiers
    start = tiers[view.tier - 1] if view.tier else 0
    unlock = config.category(view.id).unlocks[view.tier]
    return CategoryProgress(view.points - start, view.next_at - start, view.next_at - view.points, unlock)


@dataclass(frozen=True)
class StageProgress:
    value: int  # очки внутри текущей стадии
    maximum: int  # размер стадии; на последней стадии 1 (полоска заполнена)
    next_name: str | None


def stage_progress(snap: Snapshot, config: AppConfig) -> StageProgress:
    if snap.next_threshold is None:
        return StageProgress(1, 1, None)
    floor = config.stage_thresholds[snap.stage - 1]
    return StageProgress(snap.total_xp - floor, snap.next_threshold - floor, config.stage_names[snap.stage])


@dataclass(frozen=True)
class DayCell:
    day: date
    full: bool
    today: bool
    future: bool


def calendar_cells(today: date, full_days: Iterable[str], weeks: int = CALENDAR_WEEKS) -> list[DayCell]:
    """Сетка «понедельник-воскресенье», последняя неделя содержит сегодня; ячейки идут по строкам-неделям."""
    full = set(full_days)
    start = today - timedelta(days=today.weekday() + 7 * (weeks - 1))
    days = (start + timedelta(days=i) for i in range(7 * weeks))
    return [DayCell(day, day.isoformat() in full, day == today, day > today) for day in days]
