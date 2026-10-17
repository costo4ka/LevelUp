"""Тексты и сводки интерфейса без Qt: падежи, ближайшая награда, прогресс категорий, сетка календаря."""
from dataclasses import replace
from datetime import date

import pytest

from levelup.domain.models import CategoryView, Snapshot
from levelup.ui.summary import (
    ALL_OPEN_TEXT, StageProgress, calendar_cells, category_progress, format_date_ru, marks_phrase, nearest_reward,
    opens_verb, plural, points_text, reward_text, stage_progress, streak_text,
)
from tests.helpers import ok


@pytest.fixture
def snap(onboarded):
    """Снимок после онбординга: у всех категорий 0 очков, стадия 1, сегодня воскресенье 11 октября 2026."""
    return Snapshot.from_dict(ok(onboarded.svc.get_snapshot()))


def with_points(snap, **points):
    """Снимок, в котором у категорий заданы очки (тир и next_at считаются по порогам 3 / 7 / 15)."""
    tiers = (3, 7, 15)
    views = []
    for view in snap.categories:
        p = points.get(view.id, 0)
        tier = sum(p >= t for t in tiers)
        views.append(CategoryView(view.id, p, tier, tiers[tier] if tier < len(tiers) else None))
    return replace(snap, categories=tuple(views))


def test_plural_forms():
    forms = ("отметка", "отметки", "отметок")
    assert [plural(n, forms) for n in (1, 2, 4, 5, 11, 12, 14, 21, 22, 25, 101, 111)] == [
        "отметка", "отметки", "отметки", "отметок", "отметок", "отметок", "отметок", "отметка", "отметки", "отметок",
        "отметка", "отметок",
    ]
    assert streak_text(1) == "Серия: 1 день" and streak_text(3) == "Серия: 3 дня" and streak_text(0) == "Серия: 0 дней"
    assert points_text(21) == "21 очко" and points_text(320) == "320 очков"


def test_date_text():
    assert format_date_ru(date(2026, 10, 18)) == "воскресенье, 18 октября"
    assert format_date_ru(date(2026, 3, 2)) == "понедельник, 2 марта"


def test_opens_verb_for_every_shipped_item(config):
    plural_items = {"Гантели", "Кроссовки и повязка", "Штанга и медаль", "Очки"}
    for category in config.categories:
        for unlock in category.unlocks:
            expected = "откроются" if unlock.name in plural_items else "откроется"
            assert opens_verb(unlock.name) == expected, unlock.name


def test_nearest_reward_text_is_plural_aware(snap, config):
    assert reward_text(nearest_reward(with_points(snap, sport=1), config)) == "Ещё 2 отметки «Спорт» — откроются «Гантели»"
    text = reward_text(nearest_reward(with_points(snap, sport=2), config))
    assert text == "Ещё 1 отметка «Спорт» — откроются «Гантели»"
    assert marks_phrase(5, "Учёба") == "Ещё 5 отметок «Учёба»"
    assert marks_phrase(21, "Работа") == "Ещё 21 отметка «Работа»"


def test_nearest_reward_picks_fewest_points_left_and_config_order_on_tie(snap, config):
    tie = nearest_reward(with_points(snap, sport=1, work=1, study=1, social=1), config)
    assert (tie.category.id, tie.unlock.id, tie.left) == ("sport", "sport_1", 2)  # ничья — первая по конфигу
    closest = nearest_reward(with_points(snap, sport=0, work=2, study=1, social=2), config)
    assert (closest.category.id, closest.unlock.id, closest.left) == ("work", "work_1", 1)
    later_tier = nearest_reward(with_points(snap, sport=14, work=2, study=2, social=2), config)
    assert (later_tier.category.id, later_tier.unlock.id, later_tier.left) == ("sport", "sport_3", 1)
    assert reward_text(later_tier) == "Ещё 1 отметка «Спорт» — откроются «Штанга и медаль»"
    assert reward_text(nearest_reward(with_points(snap, work=6, study=6, social=6, sport=6), config)).startswith("Ещё 1 ")


def test_nearest_reward_when_everything_is_open(snap, config):
    full = with_points(snap, sport=15, work=20, study=15, social=99)
    assert nearest_reward(full, config) is None
    assert reward_text(None) == ALL_OPEN_TEXT == "Все предметы открыты — комната обставлена."


def test_category_progress_counts_from_previous_threshold(snap, config):
    view = with_points(snap, sport=5).category("sport")
    progress = category_progress(view, config)
    assert (progress.done, progress.span, progress.left, progress.unlock.name) == (2, 4, 2, "Кроссовки и повязка")
    fresh = category_progress(with_points(snap).category("work"), config)
    assert (fresh.done, fresh.span, fresh.left, fresh.unlock.name) == (0, 3, 3, "Ноутбук")
    done = category_progress(with_points(snap, study=30).category("study"), config)
    assert (done.done, done.span, done.left, done.unlock) == (1, 1, None, None)


def test_stage_progress_inside_current_stage(snap, config):
    assert stage_progress(snap, config) == StageProgress(0, 100, "Разгон")
    mid = replace(snap, stage=3, total_xp=320, next_threshold=600)
    assert stage_progress(mid, config) == StageProgress(20, 300, "Уверенный")
    last = replace(snap, stage=5, total_xp=1600, next_threshold=None)
    assert stage_progress(last, config) == StageProgress(1, 1, None)


def test_calendar_cells_are_monday_aligned_and_cover_five_weeks():
    today = date(2026, 10, 14)  # среда
    full = ["2026-10-12", "2026-10-13", "2026-09-30", "2026-08-01"]  # последняя дата вне сетки — игнорируется
    cells = calendar_cells(today, full)
    assert len(cells) == 35
    assert cells[0].day == date(2026, 9, 14) and cells[0].day.weekday() == 0  # первая ячейка — понедельник
    assert cells[28].day == date(2026, 10, 12) and cells[28].day.weekday() == 0  # последняя неделя начинается в понедельник
    assert [c.day for c in cells if c.today] == [today]
    assert [c.day for c in cells if c.full] == [date(2026, 9, 30), date(2026, 10, 12), date(2026, 10, 13)]
    future = [date(2026, 10, 15), date(2026, 10, 16), date(2026, 10, 17), date(2026, 10, 18)]
    assert [c.day for c in cells if c.future] == future
    assert all(cells[i].day.weekday() == i % 7 for i in range(35))


def test_calendar_sunday_is_last_cell_and_snapshot_window_is_covered(snap):
    today = date.fromisoformat(snap.date)
    cells = calendar_cells(today, snap.full_days)
    assert today.weekday() == 6 and cells[-1].day == today and not any(c.future for c in cells)
    assert cells[0].day == date(2026, 9, 7)  # окно снимка (35 дней назад) целиком попадает в сетку
