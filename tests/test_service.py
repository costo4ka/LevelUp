import dataclasses
import sqlite3
import uuid
from datetime import datetime, timezone

from levelup.application.service import AppService
from tests.conftest import FIRST_TITLE
from tests.helpers import fail, ok


def today(env):
    return ok(env.svc.get_snapshot())["date"]


def mark(env, habit_id, completed=True, expected=None):
    return env.svc.set_completion(habit_id, expected or today(env), completed)


def play_days(env, count):
    """Каждый день отмечаем все активные привычки, затем наступает следующий день."""
    for _ in range(count):
        for habit in ok(env.svc.get_snapshot())["habits"]:
            ok(mark(env, habit["id"]))
        env.clock.advance(days=1)


def completions(env):
    return env.conn.execute("SELECT COUNT(*) FROM completion").fetchone()[0]


# ---------------------------------------------------------------- онбординг
def test_onboarding_creates_profile_and_first_habit(env):
    assert ok(env.svc.get_snapshot())["onboarding_done"] is False
    data = ok(env.svc.finish_onboarding("Europe/Moscow", FIRST_TITLE, "study", "w"))
    snap = data["snapshot"]
    assert snap["onboarding_done"] and snap["base_id"] == "w" and snap["habits"][0]["category"] == "study"
    assert [h["title"] for h in snap["habits"]] == [FIRST_TITLE]
    fail(env.svc.finish_onboarding("UTC", "Ещё одна", "sport"), "VALIDATION_ERROR")  # повторно нельзя


def test_onboarding_is_atomic_and_validated(env):
    fail(env.svc.finish_onboarding("UTC", "   ", "sport"), "VALIDATION_ERROR")
    fail(env.svc.finish_onboarding("Mars/Base", "x", "sport"), "VALIDATION_ERROR")
    fail(env.svc.finish_onboarding("../../etc/passwd", "x", "sport"), "VALIDATION_ERROR")
    fail(env.svc.finish_onboarding("UTC", "x", "sport", "zz"), "VALIDATION_ERROR")
    fail(env.svc.create_habit("x", "sport"), "VALIDATION_ERROR")  # до онбординга привычки не создаются
    snap = ok(env.svc.get_snapshot())
    assert snap["onboarding_done"] is False and snap["habits"] == []


# ---------------------------------------------------------------- привычки
def test_result_contract_has_exactly_one_of_data_and_error(onboarded):
    good, bad = onboarded.svc.get_snapshot().to_dict(), onboarded.svc.create_habit("   ", "sport").to_dict()
    assert good["ok"] and good["data"] and good["error"] is None
    assert not bad["ok"] and bad["data"] is None
    assert set(bad["error"]) == {"code", "message", "field", "retryable"} and bad["error"]["field"] == "title"


def test_invalid_titles_do_not_change_data(onboarded):
    svc = onboarded.svc
    for bad in ("   ", 42, None, "я" * 81, "a\x00b"):
        fail(svc.create_habit(bad, "sport"), "VALIDATION_ERROR")
    assert onboarded.repo.count_all() == 1


def test_limit_of_five_and_duplicates(onboarded):
    svc = onboarded.svc
    fail(svc.create_habit("  УЧИТЬ   английский 15 минут ", "sport"), "DUPLICATE_TITLE")
    for i in range(2, 6):
        ok(svc.create_habit(f"Привычка {i}", "sport"))
    fail(svc.create_habit("Шестая", "sport"), "HABIT_LIMIT")
    assert onboarded.repo.count_active() == 5


def test_storage_limit_counts_archived_habits(onboarded):
    small = AppService(
        onboarded.repo, onboarded.clock, dataclasses.replace(onboarded.config, max_total_habits=3)
    )
    ok(small.create_habit("Вторая", "sport"))
    ok(small.archive_habit(onboarded.first_id))
    ok(small.create_habit("Третья", "sport"))
    fail(small.create_habit("Четвёртая", "sport"), "STORAGE_LIMIT")
    assert onboarded.repo.count_all() == 3


def test_unknown_or_missing_fields_are_rejected(onboarded):
    svc, hid = onboarded.svc, onboarded.first_id
    fail(svc.execute("create_habit", {"title": "x", "extra": 1}), "VALIDATION_ERROR")
    fail(svc.execute("set_completion", {"habit_id": hid, "expected_date": today(onboarded)}), "VALIDATION_ERROR")
    fail(svc.execute("no_such_command", {}), "VALIDATION_ERROR")
    ok(svc.execute("get_snapshot"))


# ---------------------------------------------------------------- отметки
def test_mark_is_idempotent_and_awards_once(onboarded):
    first = ok(mark(onboarded, onboarded.first_id))
    assert first["changed"] is True and first["snapshot"]["total_xp"] == 10
    again = ok(mark(onboarded, onboarded.first_id))
    assert again["changed"] is False and again["snapshot"]["total_xp"] == 10
    assert completions(onboarded) == 1


def test_cancel_restores_points_and_is_idempotent(onboarded):
    ok(mark(onboarded, onboarded.first_id))
    cancelled = ok(mark(onboarded, onboarded.first_id, completed=False))
    assert cancelled["changed"] is True and cancelled["snapshot"]["total_xp"] == 0
    assert ok(mark(onboarded, onboarded.first_id, completed=False))["changed"] is False


def test_invalid_input_never_changes_data(onboarded):
    svc, hid, day = onboarded.svc, onboarded.first_id, today(onboarded)
    fail(svc.set_completion("not-a-uuid", day, True), "VALIDATION_ERROR")
    fail(svc.set_completion(hid, "11.10.2026", True), "VALIDATION_ERROR")
    fail(svc.set_completion(hid, day, 1), "VALIDATION_ERROR")
    fail(svc.set_completion(hid, day, "true"), "VALIDATION_ERROR")
    fail(svc.set_completion(str(uuid.uuid4()), day, True), "NOT_FOUND")
    fail(svc.execute("set_completion", {"habit_id": hid, "expected_date": day, "completed": True, "x": 1}), "VALIDATION_ERROR")
    assert completions(onboarded) == 0


def test_stale_expected_date_is_rejected_without_changes(onboarded):
    fail(mark(onboarded, onboarded.first_id, expected="2026-10-10"), "DATE_CHANGED")
    assert completions(onboarded) == 0


def test_points_and_stage_boundaries(onboarded):
    snap = ok(onboarded.svc.get_snapshot())
    assert (snap["stage"], snap["next_threshold"], snap["xp_to_next"]) == (1, 100, 100)
    play_days(onboarded, 9)
    snap = ok(onboarded.svc.get_snapshot())
    assert (snap["total_xp"], snap["stage"]) == (90, 1)
    play_days(onboarded, 1)
    assert ok(onboarded.svc.get_snapshot())["stage"] == 2  # 100 очков — порог
    play_days(onboarded, 3)
    snap = ok(onboarded.svc.get_snapshot())
    assert (snap["total_xp"], snap["stage"], snap["next_threshold"], snap["xp_to_next"]) == (130, 2, 300, 170)
    assert snap["all_time_completions"] == 13 and snap["stage"] == 2


def test_top_stage_has_no_next_threshold(onboarded):
    play_days(onboarded, 100)
    snap = ok(onboarded.svc.get_snapshot())
    assert (snap["total_xp"], snap["stage"], snap["next_threshold"], snap["xp_to_next"]) == (1000, 5, None, 0)
    assert snap["stage_name"] == "Лучшая версия"
    play_days(onboarded, 1)
    snap = ok(onboarded.svc.get_snapshot())
    assert (snap["total_xp"], snap["stage"]) == (1010, 5)  # счёт растёт, стадия остаётся максимальной


def test_missed_days_do_not_reduce_points(onboarded):
    ok(mark(onboarded, onboarded.first_id))
    onboarded.clock.advance(days=3)
    snap = ok(onboarded.svc.get_snapshot())
    assert snap["total_xp"] == 10 and snap["streak_days"] == 0 and snap["habits"][0]["done_today"] is False


# ---------------------------------------------------------------- серия
def test_streak_scenarios_through_service(onboarded):
    play_days(onboarded, 3)  # дни 11, 12, 13; сегодня 14, ещё не отмечено
    assert ok(onboarded.svc.get_snapshot())["streak_days"] == 3
    ok(mark(onboarded, onboarded.first_id))
    assert ok(onboarded.svc.get_snapshot())["streak_days"] == 4
    ok(onboarded.svc.create_habit("Зарядка", "sport"))  # новая привычка делает сегодняшний день неполным
    assert ok(onboarded.svc.get_snapshot())["streak_days"] == 3
    zaryadka = ok(onboarded.svc.get_snapshot())["habits"][1]["id"]
    ok(onboarded.svc.archive_habit(zaryadka))  # архивирована сегодня — исключается из сегодняшнего плана
    assert ok(onboarded.svc.get_snapshot())["streak_days"] == 4


# ---------------------------------------------------------------- архив
def test_archive_frees_slot_and_keeps_history(onboarded):
    svc, hid = onboarded.svc, onboarded.first_id
    ok(mark(onboarded, hid))
    onboarded.clock.advance(days=1)
    ok(mark(onboarded, hid))
    snap = ok(svc.archive_habit(hid))["snapshot"]
    assert snap["habits"] == [] and snap["total_xp"] == 10  # сегодняшняя отметка снята, вчерашняя осталась
    fail(mark(onboarded, hid), "HABIT_NOT_ACTIVE")
    fail(svc.archive_habit(hid), "HABIT_NOT_ACTIVE")
    ok(svc.create_habit(FIRST_TITLE, "sport"))  # название архивной привычки можно использовать снова
    for i in range(4):
        ok(svc.create_habit(f"Новая {i}", "sport"))
    fail(svc.create_habit("Лишняя", "sport"), "HABIT_LIMIT")
    assert completions(onboarded) == 1


# ---------------------------------------------------------------- дата и часы
def test_midnight_boundary_in_profile_timezone(env):
    env.clock.set(datetime(2026, 10, 11, 20, 59, 59, tzinfo=timezone.utc))  # 23:59:59 по Москве
    hid = ok(env.svc.finish_onboarding("Europe/Moscow", FIRST_TITLE, "sport"))["habit_id"]
    assert today(env) == "2026-10-11"
    ok(mark(env, hid))
    env.clock.advance(seconds=1)  # полночь прошла
    fail(env.svc.set_completion(hid, "2026-10-11", False), "DATE_CHANGED")
    assert completions(env) == 1
    snap = ok(env.svc.get_snapshot())
    assert snap["date"] == "2026-10-12" and snap["habits"][0]["done_today"] is False
    assert ok(env.svc.set_completion(hid, "2026-10-12", True))["changed"] is True


def test_clock_rollback_blocks_writes_but_not_reads(onboarded):
    onboarded.clock.advance(days=1)
    ok(mark(onboarded, onboarded.first_id))  # last_seen_date = 12 октября
    onboarded.clock.advance(days=-1)
    snap = ok(onboarded.svc.get_snapshot())
    assert snap["clock_rollback"] is True and snap["date"] == "2026-10-11"
    fail(mark(onboarded, onboarded.first_id, completed=False), "CLOCK_ROLLBACK")
    fail(onboarded.svc.create_habit("Новая", "sport"), "CLOCK_ROLLBACK")
    fail(onboarded.svc.archive_habit(onboarded.first_id), "CLOCK_ROLLBACK")
    onboarded.clock.advance(days=1)  # часы исправлены
    ok(mark(onboarded, onboarded.first_id, completed=False))


# ---------------------------------------------------------------- сбои хранилища
def test_storage_failure_rolls_back_and_awards_nothing(onboarded, monkeypatch):
    onboarded.clock.advance(days=1)  # сегодня > last_seen_date, значит будет запись last_seen внутри транзакции

    def broken(*_args):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(onboarded.repo, "set_last_seen", broken)
    err = fail(mark(onboarded, onboarded.first_id), "STORAGE_ERROR")
    assert err.retryable and "Не удалось сохранить" in err.message and "sqlite" not in err.message.lower()
    assert completions(onboarded) == 0
    monkeypatch.undo()
    assert ok(mark(onboarded, onboarded.first_id))["changed"] is True


def test_locked_database_returns_busy_and_can_be_retried(onboarded):
    other = sqlite3.connect(str(onboarded.paths.db), isolation_level=None)
    other.execute("BEGIN IMMEDIATE")  # чужая запись удерживает блокировку
    onboarded.conn.execute("PRAGMA busy_timeout=50")
    err = fail(mark(onboarded, onboarded.first_id), "DATABASE_BUSY")
    assert err.retryable
    other.execute("ROLLBACK")
    other.close()
    assert ok(mark(onboarded, onboarded.first_id))["changed"] is True
    assert completions(onboarded) == 1


# ---------------------------------------------------------------- виджет
def test_overlay_settings_roundtrip_and_validation(onboarded):
    snap = ok(onboarded.svc.save_overlay_settings(False, 120, 80, "HDMI-1"))["snapshot"]
    assert (snap["overlay_enabled"], snap["overlay_x"], snap["overlay_y"], snap["screen_name"]) == (False, 120, 80, "HDMI-1")
    fail(onboarded.svc.save_overlay_settings("yes", 1, 1, None), "VALIDATION_ERROR")
    fail(onboarded.svc.save_overlay_settings(True, "1", 1, None), "VALIDATION_ERROR")
    fail(onboarded.svc.save_overlay_settings(True, 1, None, None), "VALIDATION_ERROR")
    assert ok(onboarded.svc.get_snapshot())["overlay_x"] == 120


# ---------------------------------------------------------------- категории и предметы
def cat(snapshot, category_id):
    return next(c for c in snapshot["categories"] if c["id"] == category_id)


def test_create_habit_requires_a_known_category(onboarded):
    fail(onboarded.svc.create_habit("Новая", "cooking"), "VALIDATION_ERROR")
    fail(onboarded.svc.create_habit("Новая", None), "VALIDATION_ERROR")
    fail(onboarded.svc.execute("create_habit", {"title": "Новая"}), "VALIDATION_ERROR")
    assert ok(onboarded.svc.create_habit("Новая", "work"))["snapshot"]["habits"][1]["category"] == "work"


def test_points_go_to_the_habit_category_and_open_items_independently(onboarded):
    svc = onboarded.svc
    ok(svc.create_habit("Книга", "study"))  # первая привычка — «sport»
    play_days(onboarded, 3)
    snap = ok(svc.get_snapshot())
    assert (cat(snap, "sport")["points"], cat(snap, "sport")["tier"], cat(snap, "sport")["next_at"]) == (3, 1, 7)
    assert (cat(snap, "study")["points"], cat(snap, "study")["tier"]) == (3, 1)
    assert cat(snap, "work") == {"id": "work", "points": 0, "tier": 0, "next_at": 3}
    assert snap["unlocked"] == ["sport_1", "study_1"] and snap["total_xp"] == 60
    # отдельная прокачка спорта не трогает остальные категории
    ok(svc.archive_habit(snap["habits"][1]["id"]))
    play_days(onboarded, 4)
    snap = ok(svc.get_snapshot())
    assert (cat(snap, "sport")["tier"], cat(snap, "study")["tier"]) == (2, 1)
    assert snap["unlocked"] == ["sport_1", "sport_2", "study_1"]  # очки архивной привычки остаются


def test_undo_takes_the_point_and_the_item_back(onboarded):
    play_days(onboarded, 2)
    ok(mark(onboarded, onboarded.first_id))
    snap = ok(onboarded.svc.get_snapshot())
    assert cat(snap, "sport")["tier"] == 1 and "sport_1" in snap["unlocked"]
    snap = ok(mark(onboarded, onboarded.first_id, completed=False))["snapshot"]
    assert cat(snap, "sport")["points"] == 2 and snap["unlocked"] == []


def test_day_complete_and_calendar_days(onboarded):
    svc = onboarded.svc
    ok(svc.create_habit("Чтение", "study"))
    play_days(onboarded, 2)  # два полных дня
    snap = ok(svc.get_snapshot())
    assert snap["day_complete"] is False and snap["full_days"] == ["2026-10-11", "2026-10-12"]
    ok(mark(onboarded, snap["habits"][0]["id"]))
    assert ok(svc.get_snapshot())["day_complete"] is False
    snap = ok(mark(onboarded, snap["habits"][1]["id"]))["snapshot"]
    assert snap["day_complete"] is True and snap["full_days"][-1] == snap["date"]
    assert snap["streak_days"] == 3


def test_unhandled_exception_hook_logs_instead_of_aborting(caplog):
    """Без sys.excepthook PyQt6 убивает процесс на любом исключении в слоте: хук должен лишь писать в журнал."""
    from levelup.app import log_unhandled

    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        with caplog.at_level("CRITICAL", logger="levelup.app"):
            log_unhandled(type(exc), exc, exc.__traceback__)
    assert any(r.exc_info and str(r.exc_info[1]) == "boom" for r in caplog.records)
