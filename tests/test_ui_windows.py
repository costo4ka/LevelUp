"""Окна: ближайшая награда, строки «Развития», календарь, награды в сцены, раскладка, фокус, закрытие."""
from dataclasses import replace
from datetime import date

from PyQt6.QtCore import QAbstractAnimation, QPoint, Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QWidget

from levelup.domain.errors import ErrorInfo
from levelup.ui import palette
from levelup.ui.collection import CollectionDialog
from levelup.ui.dialogs import AddHabitDialog
from levelup.ui.onboarding import OnboardingDialog
from levelup.ui.scene import SceneWidget
from levelup.ui.summary import CLOCK_WARNING, CLOCK_WARNING_SHORT
from levelup.ui.widgets import PixelBar
from tests.ui_support import focus_order, manifest, qapp, seed_marks, shell, stub_shell, wait_until  # noqa: F401


def test_hud_shows_nearest_reward_for_a_fresh_profile(shell):
    hud = shell.main.hud
    assert hud.reward_label.text() == "Ещё 3 отметки «Спорт» — откроются «Гантели»"  # ничья 3:3:3:3 — первая по конфигу
    assert hud.caption.text() == "Стадия 1 из 5" and hud.name_label.text() == "Старт"
    assert hud.xp_label.text() == "0 / 100" and hud.next_label.text() == "до стадии «Разгон»: 100"
    assert (hud.bar.value(), hud.bar.maximum()) == (0, 100)


def test_hud_reward_follows_progress_and_plural_forms(shell):
    hud = shell.main.hud
    seed_marks(shell, 2)  # у единственной привычки («Учёба») 2 очка из 3
    assert wait_until(lambda: shell.controller.snapshot.total_xp == 20)
    assert hud.reward_label.text() == "Ещё 1 отметка «Учёба» — откроется «Стопка книг»"
    seed_marks(shell, 5)  # тир 1 взят, до «Очков» ещё 2
    assert wait_until(lambda: shell.controller.snapshot.total_xp == 50)
    assert hud.reward_label.text() == "Ещё 2 отметки «Учёба» — откроются «Очки»"
    seed_marks(shell, 20)  # «Учёба» открыта целиком, ближе всех — «Спорт» (3 отметки), хотя привычек в нём нет
    assert wait_until(lambda: shell.controller.snapshot.category("study").next_at is None)
    assert hud.reward_label.text() == "Ещё 3 отметки «Спорт» — откроются «Гантели»"


def test_hud_final_text_when_everything_is_open(shell):
    c, main = shell.controller, shell.main
    for title, category in (("Зарядка", "sport"), ("Отчёт", "work"), ("Звонок", "social")):
        c.submit("create_habit", {"title": title, "category": category})
    assert wait_until(lambda: len(main._rows) == 4)
    seed_marks(shell, 15)
    assert wait_until(lambda: not any(v.next_at for v in c.snapshot.categories))
    assert main.hud.reward_label.text() == "Все предметы открыты — комната обставлена."
    assert main.hud.xp_label.text() == "600 очков" or main.hud.xp_label.text().startswith("600 /")
    assert all(row.pips.filled() == 3 and row.hint.toolTip() == "всё открыто" for row in main.development.rows.values())


def test_category_rows_show_tier_pips_bars_and_next_unlock(shell, config):
    rows = shell.main.development.rows
    assert list(rows) == ["sport", "work", "study", "social"]
    assert rows["study"].hint.toolTip() == "ещё 3 до «Стопка книг»" and rows["study"].pips.filled() == 0
    seed_marks(shell, 3)  # 3 очка «Учёба» = тир 1
    assert wait_until(lambda: shell.controller.snapshot.category("study").tier == 1)
    study = rows["study"]
    assert study.pips.filled() == 1 and study.points_label.text() == "3 очка"
    assert study.hint.toolTip() == "ещё 4 до «Очки»"
    assert (study.bar.value(), study.bar.maximum()) == (0, 4)  # отрезок после порога 3 до порога 7
    assert rows["sport"].pips.filled() == 0 and rows["sport"].hint.toolTip() == "ещё 3 до «Гантели»"
    seed_marks(shell, 20)  # 20 очков: все три предмета «Учёбы»
    assert wait_until(lambda: shell.controller.snapshot.category("study").tier == 3)
    assert study.pips.filled() == 3 and study.hint.toolTip() == "всё открыто"
    assert (study.bar.value(), study.bar.maximum()) == (1, 1) and study.bar.fraction() == 1.0


def test_collection_after_marks_matches_unlocked_items(shell, config):
    seed_marks(shell, 8)
    assert wait_until(lambda: shell.controller.snapshot.category("study").tier == 2)
    dialog = CollectionDialog(shell.controller.snapshot, config)
    assert {uid for uid, row in dialog.item_rows.items() if row.unlocked} == {"study_1", "study_2"}
    assert dialog.item_rows["study_3"].status_label.text() == "Ещё 7 отметок «Учёба»"


def test_calendar_marks_full_days_and_today(shell):
    grid = shell.main.calendar.grid
    cells = grid.cells()
    assert len(cells) == 35 and cells[-1].today and cells[-1].day == date(2026, 10, 11)
    assert not any(c.full for c in cells)
    shell.main._rows[0].mark.click()  # единственная привычка выполнена — сегодня полный день
    assert wait_until(lambda: shell.controller.snapshot.day_complete)
    assert [c.day for c in grid.cells() if c.full] == [date(2026, 10, 11)]
    assert grid.full_count() == 1 and "1 полный день" in shell.main.calendar.summary.text()
    assert shell.main.done_label.isVisibleTo(shell.main) and shell.overlay.done_label.isVisibleTo(shell.overlay)
    assert shell.main.done_label.text() == "Всё выполнено"
    shell.main._rows[0].mark.click()  # отмена возвращает незавершённый день
    assert wait_until(lambda: not shell.controller.snapshot.day_complete)
    assert not shell.main.done_label.isVisibleTo(shell.main) and not shell.overlay.done_label.isVisibleTo(shell.overlay)


def test_reward_event_reaches_both_scenes(shell, monkeypatch):
    received = []
    monkeypatch.setattr(SceneWidget, "play_reward", lambda self, event: received.append((self, event)))
    shell.main._rows[0].mark.click()
    assert wait_until(lambda: len(received) >= 2)
    assert {id(scene) for scene, _ in received} == {id(shell.main.scene), id(shell.overlay.scene)}
    event = received[0][1]
    assert (event.kind, event.xp_delta, event.category) == ("complete", 10, "study")
    assert event.before.total_xp == 0 and event.after.total_xp == 10
    shell.main._rows[0].mark.click()  # отмена тоже награда-событие: сцена сама решит, анимировать ли
    assert wait_until(lambda: len(received) >= 4)
    assert received[-1][1].kind == "undo"


def test_snapshots_reach_both_scenes_without_animation(shell, monkeypatch):
    seen = []
    monkeypatch.setattr(SceneWidget, "set_snapshot", lambda self, snap: seen.append((self, snap.total_xp)))
    shell.main._rows[0].mark.click()
    assert wait_until(lambda: {s for s, xp in seen if xp == 10} >= {shell.main.scene, shell.overlay.scene})


def test_scene_is_integer_scaled_and_dominates_the_window(shell, manifest):
    main = shell.main
    logical = manifest.scene
    for size, scale in (((1000, 660), 3), ((800, 560), 2)):
        main.resize(*size)
        wait_until(lambda: main.scene_frame.scale() == scale)
        assert main.scene_frame.scale() == scale
        assert (main.scene.width(), main.scene.height()) == (logical[0] * scale, logical[1] * scale)
        assert main.scene_frame.width() == main.scene.width() + 4  # рамка 2 px
        assert main.right.width() >= 336  # правая колонка не сжимается меньше минимума
    main.resize(1000, 660)
    wait_until(lambda: main.scene_frame.scale() == 3)
    assert 0.55 <= main.scene_frame.width() / main.width() <= 0.6  # сцена — главный блок экрана
    assert main.left.width() == main.scene_frame.width() == main.hud.width()  # подпись ровно под сценой
    top = QPoint(0, 0)
    assert main.today.mapTo(main, top).y() == main.scene_frame.mapTo(main, top).y()  # верхние края колонок на одной линии
    assert main.today.mapTo(main, top).x() == main.right.mapTo(main, top).x()  # без внутренней рамки у прокрутки
    assert main.minimumWidth() <= 800 and main.minimumHeight() <= 560


def test_overlay_is_narrow_and_compact_scene_is_scaled_by_two(shell, manifest):
    overlay = shell.overlay
    crop = manifest.compact_crop
    assert overlay.width() <= 300
    assert (overlay.scene.width(), overlay.scene.height()) == (crop[2] * 2, crop[3] * 2)
    assert overlay.scene.compact


def test_tab_order_marks_menus_add_then_top_buttons(shell):
    main, c = shell.main, shell.controller
    c.submit("create_habit", {"title": "Зарядка", "category": "sport"})
    assert wait_until(lambda: len(main._rows) == 2 and len(shell.overlay._rows) == 2)
    assert wait_until(lambda: all(r.mark.isVisibleTo(main) for r in main._rows))  # новые строки показываются позже
    assert wait_until(lambda: all(r.mark.isVisibleTo(shell.overlay) for r in shell.overlay._rows))
    first = main._rows[0].mark
    expected = [first, main._rows[0].menu_btn, main._rows[1].mark, main._rows[1].menu_btn,
                main.add_btn, main.collection_btn, main.overlay_btn, main.quit_btn]
    assert focus_order(first, main) == expected
    overlay = shell.overlay
    first = overlay.open_btn
    assert focus_order(first, overlay) == [overlay.open_btn, overlay.hide_btn, overlay._rows[0].mark, overlay._rows[1].mark]


def test_space_keeps_focus_on_the_mark_while_saving(shell):
    main = shell.main
    main.activateWindow()
    assert QTest.qWaitForWindowActive(main)
    mark = main._rows[0].mark
    mark.setFocus(Qt.FocusReason.TabFocusReason)
    QTest.keyClick(mark, Qt.Key.Key_Space)
    assert mark.is_busy() and mark.isEnabled()  # во время записи отметка бледнеет, но не отключается
    assert wait_until(lambda: shell.controller.snapshot.total_xp == 10 and not mark.is_busy())
    assert mark.isChecked() and mark.hasFocus() and mark.keyboard_focus  # фокус не потерян


def test_error_strip_with_retry_and_clock_warning(shell):
    main, overlay = shell.main, shell.overlay
    error = ErrorInfo("STORAGE_ERROR", "Не удалось сохранить. Проверьте доступ к диску и повторите", None, True)
    shell.controller.error_occurred.emit(error)
    assert main.strip._label.text() == error.message and main.strip.retry_button.isVisibleTo(main)
    shell.controller.error_cleared.emit()
    assert not main.strip.retry_button.isVisibleTo(main)
    snap = replace(shell.controller.snapshot, clock_rollback=True)
    main.apply_snapshot(snap)
    overlay.apply_snapshot(snap)
    assert main.strip._label.text() == CLOCK_WARNING and overlay.strip._label.text() == CLOCK_WARNING_SHORT
    main.apply_snapshot(shell.controller.snapshot)
    assert main.strip._label.text() == ""


def test_long_title_is_elided_with_tooltip_and_unknown_category_is_safe(shell):
    main, c = shell.main, shell.controller
    title = "Очень длинное название привычки, которое не поместится в строку списка целиком — " + "и ещё " * 3
    c.submit("create_habit", {"title": title[:80], "category": "work"})
    assert wait_until(lambda: len(main._rows) == 2)
    row = main._rows[1]
    main.show()
    wait_until(lambda: row.label.width() > 50)
    assert row.label.text().endswith("…") and row.label.text() != title[:80]
    assert title[:80] in row.toolTip() and "Работа" in row.toolTip()
    assert len(row.label.text()) < len(title[:80])


def test_closing_main_window_hides_it_while_widget_is_visible_otherwise_quits(shell, monkeypatch):
    quits = []
    monkeypatch.setattr(type(shell), "quit", lambda self: quits.append(1))
    assert shell.overlay_visible()
    shell.main.close()
    assert not shell.main.isVisible() and quits == []
    shell.hide_overlay()  # «Скрыть» возвращает основное окно
    assert shell.main.isVisible() and not shell.overlay_visible()
    shell.main.close()
    assert quits == [1]


def test_closing_the_widget_hides_it_and_brings_the_main_window_back(shell):
    shell.main.hide()
    assert shell.overlay_visible()
    shell.overlay.close()  # Alt+F4 на виджете
    assert not shell.overlay_visible() and shell.main.isVisible()


def test_overlay_position_is_clamped_to_screens(shell):
    overlay = shell.overlay
    committed = []
    overlay.position_committed.connect(lambda x, y, name: committed.append((x, y, name)))
    overlay.move(-5000, -5000)
    overlay.commit_position()
    screen = QGuiApplication.primaryScreen().availableGeometry()
    x, y, _ = committed[-1]
    assert screen.x() <= x <= screen.x() + screen.width() - overlay.width()
    assert screen.y() <= y <= screen.y() + screen.height() - overlay.height()
    assert (overlay.x(), overlay.y()) == (x, y)


def test_focus_scrolls_the_right_column_into_view(shell):
    main, c = shell.main, shell.controller
    for title, category in (("Зарядка", "sport"), ("Отчёт", "work"), ("Звонок", "social"), ("Дневник", "study")):
        c.submit("create_habit", {"title": title, "category": category})
    assert wait_until(lambda: len(main._rows) == 5 and all(r.mark.isVisibleTo(main) for r in main._rows))
    main.right.setMaximumHeight(160)  # очень низкое окно: список привычек не помещается
    main.activateWindow()
    assert QTest.qWaitForWindowActive(main)
    assert wait_until(lambda: main.right.viewport().height() <= 160)
    bar = main.right.verticalScrollBar()
    assert bar.maximum() > 0 and bar.value() == 0
    mark = main._rows[-1].mark
    mark.setFocus(Qt.FocusReason.TabFocusReason)
    assert wait_until(lambda: bar.value() > 0)
    viewport = main.right.viewport()
    assert viewport.rect().contains(mark.mapTo(viewport, mark.rect().center()))  # отметка с фокусом видна


def test_progress_bar_value_is_immediate_and_the_move_is_short(qapp):
    bar = PixelBar()
    bar.show()
    bar.set_progress(10, 100, animate=False)
    assert bar.fraction() == 0.1 and bar._anim.state() == QAbstractAnimation.State.Stopped
    bar.set_progress(60, 100)
    assert (bar.value(), bar.maximum(), bar.fraction()) == (60, 100, 0.6)  # цель известна сразу
    assert bar._anim.state() == QAbstractAnimation.State.Running and PixelBar.DURATION_MS <= 300
    assert wait_until(lambda: bar._anim.state() == QAbstractAnimation.State.Stopped, timeout=1.0)
    assert bar._shown == 0.6
    bar.set_progress(5, 20)  # другой масштаб (новая стадия): без «обратного хода», сразу на место
    assert bar._anim.state() == QAbstractAnimation.State.Stopped and bar._shown == 0.25
    bar.hide()


def test_font_sizes_stay_on_the_scale(shell, config, manifest):
    """Пиксельный шрифт рисуется только на своей сетке (10 / 20 / 30), системный — 12 и 14."""
    windows = [
        shell.main, shell.overlay, AddHabitDialog(shell.controller, config),
        CollectionDialog(shell.controller.snapshot, config), OnboardingDialog(stub_shell(config, manifest)),
    ]
    pixel_sizes, sans_sizes = set(), set()
    for window in windows:
        for widget in [window, *window.findChildren(QWidget)]:
            font = widget.font()
            (pixel_sizes if font.family() == palette.load_fonts() else sans_sizes).add(font.pixelSize())
    assert pixel_sizes == {10, 20, 30}, pixel_sizes
    assert sans_sizes <= {12, 14}, sans_sizes


def test_stale_click_after_midnight_gives_notice_and_new_day_without_error_or_reward(shell):
    c, notes, errors, rewards = shell.controller, [], [], []
    c.notice.connect(notes.append)
    c.error_occurred.connect(errors.append)
    c.reward.connect(rewards.append)
    shell.clock.advance(days=1)
    shell.main._rows[0].mark.click()  # снимок ещё вчерашний
    assert wait_until(lambda: notes and c.snapshot.date == "2026-10-12")
    assert not errors and not rewards
    assert not c.snapshot.habits[0].done_today and not c.busy
