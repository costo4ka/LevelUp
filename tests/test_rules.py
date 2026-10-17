from datetime import date, timedelta

import pytest

from levelup.domain import rules
from levelup.domain.errors import AppError

THRESHOLDS = (0, 100, 300, 600, 1000)
TIERS = (3, 7, 15)
D = date(2026, 10, 11)


def days(*offsets):
    return {D + timedelta(days=o): 1 for o in offsets}


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("  Учить   английский\t15\nминут ", "Учить английский 15 минут"),
        ("Café", "Café"),  # NFC
        ("a", "a"),
        ("я" * 80, "я" * 80),
        ("🏃‍♀️ Бег", "🏃‍♀️ Бег"),
    ],
)
def test_normalize_title_ok(raw, expected):
    assert rules.normalize_title(raw) == expected


@pytest.mark.parametrize("raw", ["   ", "", 42, None, b"x", "я" * 81, "a\x00b", "a\x07b", " ", "x" * 20_000])
def test_normalize_title_invalid(raw):
    with pytest.raises(AppError) as exc:
        rules.normalize_title(raw)
    assert exc.value.code.value == "VALIDATION_ERROR" and exc.value.field == "title"


def test_title_key_ignores_case():
    assert rules.title_key("ЗАРЯДКА") == rules.title_key("зарядка")


@pytest.mark.parametrize("value", ["", "abc", 5, None, "550e8400-e29b-41d4-a716-44665544000", "550e8400e29b41d4a716446655440000"])
def test_parse_uuid_rejects(value):
    with pytest.raises(AppError):
        rules.parse_uuid(value)


def test_parse_uuid_ok_and_dates():
    assert rules.parse_uuid("550E8400-E29B-41D4-A716-446655440000") == "550e8400-e29b-41d4-a716-446655440000"
    assert rules.parse_iso_date("2026-10-11", "d") == D
    for bad in ("2026-13-01", "11.10.2026", "2026-1-1", 20261011, None, "٢٠٢٦-١٠-١١"):
        with pytest.raises(AppError):
            rules.parse_iso_date(bad, "d")


@pytest.mark.parametrize(
    "xp, stage",
    [(0, 1), (90, 1), (99, 1), (100, 2), (299, 2), (300, 3), (599, 3), (600, 4), (999, 4), (1000, 5),
     (1001, 5), (99999, 5)],
)
def test_stage_boundaries(xp, stage):
    assert rules.stage_for(xp, THRESHOLDS) == stage


def test_progress_to_next_stage():
    stage = rules.stage_for(130, THRESHOLDS)
    nxt = rules.next_threshold(stage, THRESHOLDS)
    assert (stage, nxt, rules.xp_to_next(130, nxt)) == (2, 300, 170)
    top = rules.stage_for(1000, THRESHOLDS)
    assert rules.next_threshold(top, THRESHOLDS) is None and rules.xp_to_next(1000, None) == 0


def test_streak_full_today():
    assert rules.compute_streak(D, [(D - timedelta(2), None)], days(-2, -1, 0)) == 3


def test_streak_incomplete_today_counts_from_yesterday():
    assert rules.compute_streak(D, [(D - timedelta(2), None)], days(-2, -1)) == 2


def test_streak_broken_by_missed_yesterday():
    assert rules.compute_streak(D, [(D - timedelta(3), None)], days(-3, -2, 0)) == 1
    assert rules.compute_streak(D, [(D - timedelta(3), None)], days(-3, -2)) == 0


def test_streak_day_without_habits_breaks():
    a = (D - timedelta(6), D - timedelta(3))  # план: D-6..D-4
    b = (D - timedelta(1), None)  # с D-1; D-3 и D-2 — дни без привычек
    assert rules.compute_streak(D, [a, b], days(-6, -5, -4, -1, 0)) == 2


def test_streak_new_habit_participates_from_creation_day():
    ranges = [(D - timedelta(3), None), (D, None)]
    done = {D - timedelta(3): 1, D - timedelta(2): 1, D - timedelta(1): 1, D: 1}  # новая привычка сегодня не отмечена
    assert rules.compute_streak(D, ranges, done) == 3


def test_streak_habit_archived_today_is_excluded_from_today():
    ranges = [(D - timedelta(2), None), (D - timedelta(2), D)]
    done = {D - timedelta(2): 2, D - timedelta(1): 2, D: 1}
    assert rules.compute_streak(D, ranges, done) == 3


def test_streak_without_habits_is_zero():
    assert rules.compute_streak(D, [], {}) == 0
    assert rules.compute_streak(D, [(D, D)], {}) == 0  # создана и архивирована в один день


@pytest.mark.parametrize(
    "points, tier, next_at",
    [(0, 0, 3), (2, 0, 3), (3, 1, 7), (6, 1, 7), (7, 2, 15), (14, 2, 15), (15, 3, None), (99, 3, None)],
)
def test_category_tier_boundaries(points, tier, next_at):
    assert rules.category_tier(points, TIERS) == tier
    assert rules.next_tier_at(tier, TIERS) == next_at


def test_full_days_window_and_planned_counts():
    ranges = [(D - timedelta(5), None), (D - timedelta(3), None)]  # вторая привычка появилась позже
    counts = {D - timedelta(5): 1, D - timedelta(4): 1, D - timedelta(3): 2, D - timedelta(2): 1, D - timedelta(1): 2, D: 2}
    result = rules.full_days(D, 35, ranges, counts)
    assert result == [D - timedelta(5), D - timedelta(4), D - timedelta(3), D - timedelta(1), D]
    assert rules.full_days(D, 2, ranges, counts) == [D - timedelta(1), D]  # окно в два дня
    assert rules.full_days(D, 35, [], {}) == []
    assert rules.full_days(D, 35, [(D + timedelta(1), None)], {}) == []  # привычка из будущего
