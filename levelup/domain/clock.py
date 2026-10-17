"""Источник времени. В тестах подменяется на FixedClock — часы ОС не трогаем."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Protocol


class Clock(Protocol):
    def now_utc(self) -> datetime: ...


class SystemClock:
    def now_utc(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock:
    def __init__(self, now: datetime):
        self.set(now)

    def set(self, now: datetime) -> None:
        if now.tzinfo is None:
            raise ValueError("нужен datetime с часовым поясом")
        self._now = now.astimezone(timezone.utc)

    def advance(self, **delta: float) -> None:
        self._now += timedelta(**delta)

    def now_utc(self) -> datetime:
        return self._now


def local_date(clock: Clock, tz: tzinfo) -> date:
    return clock.now_utc().astimezone(tz).date()
