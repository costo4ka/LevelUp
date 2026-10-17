"""Часовой пояс системы."""
from __future__ import annotations

from zoneinfo import ZoneInfo


def detect_timezone() -> str | None:
    """IANA-имя системного часового пояса или None, если распознать не удалось."""
    try:
        import tzlocal

        name = tzlocal.get_localzone_name()
        if name:
            ZoneInfo(name)
            return name
    except Exception:  # noqa: BLE001 — любое сбойное распознавание = пользователь выберет сам
        pass
    return None
