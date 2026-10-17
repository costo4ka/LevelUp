"""Сквозная проверка интерфейса без экрана (offscreen): оба окна, worker, сигнал state_changed."""
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

from tests.ui_support import manifest, qapp, seed_marks, shell, wait_until  # noqa: F401


def test_mark_updates_both_windows_after_commit(shell):
    main, overlay, c = shell.main, shell.overlay, shell.controller
    assert overlay.isVisible() and main.isVisible()
    main_row, overlay_row = main._rows[0], overlay._rows[0]
    assert not main_row.mark.isChecked() and main.hud.xp_label.text() == "0 / 100"

    main_row.mark.click()
    assert not main_row.mark.isChecked()  # до COMMIT отметка не показывается
    assert c.is_habit_pending(main_row.habit_id) and main_row.mark.is_busy()
    assert wait_until(lambda: c.snapshot.total_xp == 10)
    assert main_row.mark.isChecked() and overlay_row.mark.isChecked()  # оба окна синхронны
    assert main.hud.xp_label.text() == "10 / 100" and overlay.xp_label.text() == "10 / 100"
    assert wait_until(lambda: not main_row.mark.is_busy())

    QTest.keyClick(overlay_row.mark, Qt.Key.Key_Space)  # клавиатура: Space переключает отметку
    assert wait_until(lambda: c.snapshot.total_xp == 0)
    assert not main_row.mark.isChecked() and not overlay_row.mark.isChecked()


def test_add_and_archive_habit_with_category(shell):
    c, main = shell.controller, shell.main
    assert c.snapshot.base_id == "w" and main._rows[0].category == "study"
    c.submit("create_habit", {"title": "Зарядка", "category": "sport"})
    assert wait_until(lambda: len(main._rows) == 2 and len(shell.overlay._rows) == 2)
    assert main.count_label.text() == "Активных привычек: 2 из 5"
    assert [r.category for r in main._rows] == ["study", "sport"]
    c.archive_habit(main._rows[1].habit_id)
    assert wait_until(lambda: len(main._rows) == 1)


def test_empty_state_keeps_progress(shell):
    c, main, overlay = shell.controller, shell.main, shell.overlay
    main._rows[0].mark.click()
    assert wait_until(lambda: c.snapshot.total_xp == 10)
    shell.clock.advance(days=1)  # отметка уходит в историю
    c.request_snapshot()
    assert wait_until(lambda: c.snapshot.date == "2026-10-12")
    c.archive_habit(main._rows[0].habit_id)
    assert wait_until(lambda: not main._rows and not overlay._rows)
    assert main.empty.isVisible() and overlay.empty_label.isVisible()
    assert c.snapshot.total_xp == 10 and main.hud.xp_label.text() == "10 / 100"  # очки и сцена сохраняются
    c.submit("create_habit", {"title": "Новая", "category": "work"})
    assert wait_until(lambda: len(main._rows) == 1 and len(overlay._rows) == 1)
    assert not main.empty.isVisible() and not overlay.empty_label.isVisible()


def test_hide_button_returns_main_window_and_persists(shell):
    shell.main.hide()
    shell.overlay.hide_btn.click()
    assert not shell.overlay.isVisible() and shell.main.isVisible()
    assert wait_until(lambda: shell.controller.snapshot.overlay_enabled is False)
    assert not shell.main.overlay_btn.isChecked()
    shell.main.overlay_btn.click()
    assert shell.overlay.isVisible() and shell.main.overlay_btn.isChecked()
    assert wait_until(lambda: shell.controller.snapshot.overlay_enabled is True)


def test_new_day_refreshes_list_and_shows_notice(shell):
    c = shell.controller
    shell.main._rows[0].mark.click()
    assert wait_until(lambda: c.snapshot.total_xp == 10)
    shell.clock.advance(days=1)
    c.request_snapshot()
    assert wait_until(lambda: c.snapshot.date == "2026-10-12")
    assert not shell.main._rows[0].mark.isChecked()
    assert "Наступил новый день" in shell.main.strip._label.text()
    assert shell.main.date_label.text() == "понедельник, 12 октября"


def test_stage_change_updates_hud_and_both_windows(shell):
    c, main, overlay = shell.controller, shell.main, shell.overlay
    assert main.hud.badge.number() == 1 and main.hud.name_label.text() == "Старт"
    seed_marks(shell, 10)  # 10 отметок = 100 очков = стадия 2
    assert wait_until(lambda: c.snapshot.stage == 2)
    assert main.hud.badge.number() == 2 and main.hud.name_label.text() == "Разгон"
    assert overlay.stage_label.text() == "Разгон" and overlay.xp_label.text() == "100 / 300"
    assert main.hud.next_label.text() == "до стадии «В ритме»: 200"
