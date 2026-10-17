"""Чистые правила: нормализация названий, разбор входных значений, стадии, серия."""
from __future__ import annotations

import re
import unicodedata
from bisect import bisect_right
from datetime import date, timedelta
from typing import Iterable, Mapping, Sequence

from .errors import ErrorCode, make_error

_LINE_WS = "\t\n\r\v\f\x85"  # переносы и табуляция превращаются в пробел до проверки на управляющие
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_RAW_TITLE_LIMIT = 10_000


def normalize_title(raw: object, max_len: int = 80) -> str:
    """Название привычки: NFC, одиночные пробелы, без краевых пробелов, 1..max_len символов."""
    bad_length = make_error(
        ErrorCode.VALIDATION_ERROR, f"Введите название от 1 до {max_len} символов.", "title"
    )
    if not isinstance(raw, str) or len(raw) > _RAW_TITLE_LIMIT:
        raise bad_length
    chars: list[str] = []
    for ch in raw:
        category = unicodedata.category(ch)
        if ch in _LINE_WS or category in ("Zs", "Zl", "Zp"):
            chars.append(" ")
        elif category in ("Cc", "Cs"):
            raise make_error(ErrorCode.VALIDATION_ERROR, "Название содержит недопустимые символы.", "title")
        else:
            chars.append(ch)
    text = unicodedata.normalize("NFC", re.sub(r" +", " ", "".join(chars)).strip(" "))
    if not 1 <= len(text) <= max_len:
        raise bad_length
    return text


def title_key(title: str) -> str:
    """Ключ сравнения названий без учёта регистра."""
    return unicodedata.normalize("NFC", title.casefold())


def parse_uuid(value: object, field: str = "habit_id") -> str:
    if not isinstance(value, str) or not _UUID_RE.fullmatch(value):
        raise make_error(ErrorCode.VALIDATION_ERROR, "Некорректный идентификатор привычки.", field)
    return value.lower()


def parse_iso_date(value: object, field: str) -> date:
    if isinstance(value, str) and _DATE_RE.fullmatch(value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise make_error(ErrorCode.VALIDATION_ERROR, "Некорректная дата (нужен формат ГГГГ-ММ-ДД).", field)


def stage_for(total_xp: int, thresholds: Sequence[int]) -> int:
    """Номер стадии (с 1): наибольший достигнутый порог."""
    return max(1, bisect_right(thresholds, total_xp))


def next_threshold(stage: int, thresholds: Sequence[int]) -> int | None:
    return thresholds[stage] if stage < len(thresholds) else None


def xp_to_next(total_xp: int, nxt: int | None) -> int:
    return 0 if nxt is None else max(0, nxt - total_xp)


def category_tier(points: int, tiers: Sequence[int]) -> int:
    """Сколько порогов категории достигнуто (0..len(tiers))."""
    return bisect_right(tiers, points)


def next_tier_at(tier: int, tiers: Sequence[int]) -> int | None:
    """Очки, с которых откроется следующий предмет категории, или None, если всё открыто."""
    return tiers[tier] if tier < len(tiers) else None


def _planned_by_day(today: date, ranges: Iterable[tuple[date, date | None]]) -> tuple[date, list[int]] | None:
    """(первый день, число запланированных привычек на каждый день до today) или None, если привычек нет."""
    spans = [(s, a) for s, a in ranges if a is None or a > s]
    if not spans:
        return None
    first = min(s for s, _ in spans)
    if first > today:
        return None
    length = (today - first).days + 1
    delta = [0] * (length + 1)
    for start, archived in spans:
        i = (start - first).days
        if i >= length:
            continue
        delta[i] += 1
        if archived is not None:
            j = (archived - first).days
            if j < length:
                delta[j] -= 1
    planned: list[int] = []
    running = 0
    for k in range(length):
        running += delta[k]
        planned.append(running)
    return first, planned


def compute_streak(
    today: date,
    ranges: Iterable[tuple[date, date | None]],
    completed_counts: Mapping[date, int],
) -> int:
    """Число подряд идущих полных дней.

    ranges — (start_date, archived_date|None) всех привычек, включая архивные: привычка
    запланирована в день D, если start_date <= D < archived_date. Полный день — день, где
    запланировано хотя бы одно и выполнены все. Если сегодня не полный, счёт идёт со вчера.
    completed_counts — число отметок по дням только для запланированных привычек.
    """
    sweep = _planned_by_day(today, ranges)
    if sweep is None:
        return 0
    first, planned = sweep

    def is_full(k: int) -> bool:
        return planned[k] > 0 and completed_counts.get(first + timedelta(days=k), 0) >= planned[k]

    k = len(planned) - 1
    if not is_full(k):
        k -= 1
    streak = 0
    while k >= 0 and is_full(k):
        streak += 1
        k -= 1
    return streak


def full_days(
    today: date,
    window: int,
    ranges: Iterable[tuple[date, date | None]],
    completed_counts: Mapping[date, int],
) -> list[date]:
    """Полные дни за последние window дней (включая сегодня) по возрастанию — для календаря."""
    sweep = _planned_by_day(today, ranges)
    if sweep is None:
        return []
    first, planned = sweep
    result: list[date] = []
    for k in range(max(0, len(planned) - window), len(planned)):
        day = first + timedelta(days=k)
        if planned[k] > 0 and completed_counts.get(day, 0) >= planned[k]:
            result.append(day)
    return result
