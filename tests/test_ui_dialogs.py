"""Диалоги: выбор категории, добавление привычки, онбординг, коллекция, «О программе»."""
from dataclasses import replace

import pytest
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog

from levelup import __version__
from levelup.config import ASSETS_DIR
from levelup.domain.errors import ErrorInfo, Result
from levelup.domain.models import CategoryView, Snapshot
from levelup.ui import about as about_module
from levelup.ui.about import AboutDialog
from levelup.ui.collection import CollectionDialog
from levelup.ui.dialogs import AddHabitDialog, CategoryChooser, confirm_archive
from levelup.ui.onboarding import OnboardingDialog, character_previews
from levelup.ui.widgets import PixelButton
from tests.helpers import ok
from tests.ui_support import FakeController, manifest, qapp, stub_shell  # noqa: F401


def failure(code, message, field=None):
    return Result.failure(ErrorInfo(code, message, field))


# ---------------------------------------------------------------------- выбор категории
def test_chooser_has_four_cards_first_selected_by_default(qapp, config):
    chooser = CategoryChooser(config)
    assert list(chooser.cards) == ["sport", "work", "study", "social"]
    assert chooser.category() == "sport"
    card = chooser.cards["study"]
    assert "Курсы, чтение, языки" in card.accessibleName() and card.first_unlock.name == "Стопка книг"
    assert card.accessibleDescription() == "Первым откроется: Стопка книг"


def test_chooser_click_and_keyboard_change_the_single_selection(qapp, config):
    chooser = CategoryChooser(config)
    changes = []
    chooser.changed.connect(changes.append)
    chooser.show()
    chooser.activateWindow()
    assert QTest.qWaitForWindowActive(chooser)  # стрелки работают у окна с фокусом
    chooser.cards["social"].click()
    assert chooser.category() == "social" and changes == ["social"]
    assert sum(card.isChecked() for card in chooser.cards.values()) == 1  # радиокнопки: выбрана ровно одна
    chooser.cards["social"].click()  # повторный клик не снимает выбор: категория обязательна
    assert chooser.category() == "social"

    chooser.cards["sport"].click()
    chooser.cards["sport"].setFocus()
    QTest.keyClick(chooser.cards["sport"], Qt.Key.Key_Right)  # стрелка вправо: следующая карточка в ряду
    assert chooser.category() == "work"
    QTest.keyClick(chooser.cards["work"], Qt.Key.Key_Down)  # вниз: карточка под ней
    assert chooser.category() == "social"
    chooser.hide()


def test_chooser_group_is_one_tab_stop(qapp, config):
    dialog = AddHabitDialog(FakeController(), config)
    dialog.show()
    dialog.activateWindow()
    assert QTest.qWaitForWindowActive(dialog)
    card = dialog.chooser.cards["study"]
    card.click()
    card.setFocus(Qt.FocusReason.TabFocusReason)
    QTest.keyClick(card, Qt.Key.Key_Tab)  # Tab уходит из группы карточек, а не к соседней карточке
    assert QApplication.focusWidget() in (dialog.cancel, dialog.ok)
    QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Backtab)  # Shift+Tab возвращается на выбранную
    assert QApplication.focusWidget() is card and card.keyboard_focus
    dialog.hide()


# ---------------------------------------------------------------------- добавление привычки
def test_add_dialog_sends_create_habit_with_title_and_category(qapp, config):
    controller = FakeController()
    dialog = AddHabitDialog(controller, config)
    dialog.show()
    assert dialog.chooser.category() == "sport"  # по умолчанию первая
    dialog.field.edit.setText("Читать на ночь")
    dialog.chooser.cards["study"].click()
    dialog.ok.click()
    assert controller.calls == [("create_habit", {"title": "Читать на ночь", "category": "study"})]
    assert not dialog.field.edit.isEnabled() and dialog.status.text() == "Сохраняем…"  # пока идёт запись, поля заблокированы
    controller.callback(Result.success({"habit_id": "x"}))
    assert dialog.result() == QDialog.DialogCode.Accepted


@pytest.mark.parametrize(
    "error",
    [
        failure("VALIDATION_ERROR", "Введите название привычки."),
        failure("VALIDATION_ERROR", "Название должно быть не длиннее 80 символов."),
        failure("DUPLICATE_TITLE", "Привычка с таким названием уже есть."),
        failure("HABIT_LIMIT", "Достигнут лимит активных привычек. Архивируйте одну из них."),
    ],
)
def test_add_dialog_shows_controller_errors_inline(qapp, config, error):
    controller = FakeController()
    dialog = AddHabitDialog(controller, config)
    dialog.show()
    dialog.ok.click()
    controller.callback(error)
    assert dialog.field.error.text() == error.error.message  # ошибка рядом с полем, диалог остаётся открытым
    assert dialog.isVisible() and dialog.field.edit.isEnabled() and dialog.ok.isEnabled()
    dialog.field.edit.setText("Другое")  # ввод очищает ошибку
    assert dialog.field.error.text() == ""
    dialog.hide()


def test_add_dialog_category_error_goes_under_the_chooser(qapp, config):
    controller = FakeController()
    dialog = AddHabitDialog(controller, config)
    dialog.show()
    dialog.ok.click()
    controller.callback(failure("VALIDATION_ERROR", "Неизвестная категория.", "category"))
    assert dialog.chooser.error.text() == "Неизвестная категория." and dialog.field.error.text() == ""
    dialog.hide()


def test_add_dialog_counter_turns_on_overlong_title(qapp, config):
    dialog = AddHabitDialog(FakeController(), config)
    dialog.field.edit.setText("а" * 81)
    assert dialog.field.counter.text() == "81/80"


# ---------------------------------------------------------------------- онбординг
def test_onboarding_sends_base_category_title_and_timezone(qapp, config, manifest):
    shell = stub_shell(config, manifest)
    dialog = OnboardingDialog(shell)
    dialog.show()
    assert dialog.base_id() == config.default_base == "m" and dialog.heroes["m"].isChecked()
    assert dialog.zone.currentData() == "Europe/Moscow" and dialog.chooser.category() == "sport"
    assert dialog.pages.currentIndex() == 0 and dialog.next.isVisible() and not dialog.start.isVisible()

    dialog.heroes["w"].click()
    dialog.next.click()
    assert dialog.pages.currentIndex() == 1 and dialog.start.isVisible() and dialog.back.isVisible()
    dialog.field.edit.setText("Бегать по утрам")
    dialog.chooser.cards["social"].click()
    dialog.zone.setCurrentIndex(dialog.zone.findData("Asia/Tokyo"))
    dialog.start.click()
    assert shell.controller.calls == [
        (
            "finish_onboarding",
            {"timezone_id": "Asia/Tokyo", "title": "Бегать по утрам", "category": "social", "base_id": "w"},
        )
    ]
    shell.controller.callback(Result.success({"habit_id": "x"}))
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_onboarding_back_keeps_choices_and_title_error_stays_inline(qapp, config, manifest):
    shell = stub_shell(config, manifest)
    dialog = OnboardingDialog(shell)
    dialog.show()
    dialog.heroes["w"].click()
    dialog.next.click()
    dialog.back.click()
    assert dialog.pages.currentIndex() == 0 and dialog.base_id() == "w"
    dialog.next.click()
    dialog.start.click()
    shell.controller.callback(failure("VALIDATION_ERROR", "Введите название привычки.", "title"))
    assert dialog.field.error.text() == "Введите название привычки." and dialog.error.text() == ""
    assert dialog.isVisible() and dialog.start.isEnabled()
    dialog.hide()


def test_onboarding_without_detected_timezone_requires_a_choice(qapp, config, manifest):
    shell = stub_shell(config, manifest, detected=None)
    dialog = OnboardingDialog(shell)
    dialog.show()
    dialog.next.click()
    assert dialog.zone.currentData() is None and dialog.zone_hint.isVisible()
    dialog.field.edit.setText("Бег")
    dialog.start.click()
    assert dialog.error.text() == "Выберите часовой пояс." and shell.controller.calls == []
    dialog.zone.setCurrentIndex(dialog.zone.findData("UTC"))
    dialog.start.click()
    assert shell.controller.calls[0][1]["timezone_id"] == "UTC"
    dialog.hide()


def test_hero_previews_are_real_x4_crops_of_the_composed_character(qapp, config, manifest):
    previews = character_previews(manifest, config.character_bases)
    assert set(previews) == {"m", "w"}
    m, w = previews["m"], previews["w"]
    assert m.size() == w.size() and m.width() % 4 == 0 and m.height() % 4 == 0  # одинаковая обрезка, масштаб x4
    assert m.width() <= 64 * 4 and m.height() <= 64 * 4 and m.width() > 20 * 4
    image_m, image_w = m.toImage(), w.toImage()
    assert image_m != image_w  # это настоящие разные спрайты, а не заглушка
    assert any(image_m.pixelColor(x, y).alpha() for x in range(0, m.width(), 4) for y in range(0, m.height(), 4))
    for x in range(0, m.width() - 4, 4):  # блоки 4x4 одного цвета: ближайший сосед без сглаживания
        assert image_m.pixel(x, 0) == image_m.pixel(x + 3, 3)
    titles = [dialog_card.accessibleName() for dialog_card in OnboardingDialog(stub_shell(config, manifest)).heroes.values()]
    assert titles == ["Он", "Она"]


# ---------------------------------------------------------------------- коллекция и «О программе»
@pytest.fixture
def sample_snapshot(onboarded):
    snap = Snapshot.from_dict(ok(onboarded.svc.get_snapshot()))
    categories = (
        CategoryView("sport", 8, 2, 15),
        CategoryView("work", 1, 0, 3),
        CategoryView("study", 3, 1, 7),
        CategoryView("social", 0, 0, 3),
    )
    return replace(
        snap, stage=3, total_xp=120, categories=categories, unlocked=("sport_1", "sport_2", "study_1")
    )


def test_collection_lists_five_stages_and_twelve_items(qapp, config, sample_snapshot):
    dialog = CollectionDialog(sample_snapshot, config)
    assert [row.name_label.text() for row in dialog.stage_rows] == [
        "1  Старт", "2  Разгон", "3  В ритме", "4  Уверенный", "5  Лучшая версия"
    ]
    assert [row.reached for row in dialog.stage_rows] == [True, True, True, False, False]
    assert [row.current for row in dialog.stage_rows] == [False, False, True, False, False]
    assert [row.status_label.text() for row in dialog.stage_rows] == [
        "с 0 очков", "с 100 очков", "сейчас", "с 600 очков", "с 1000 очков"
    ]
    assert len(dialog.item_rows) == 12
    assert {uid for uid, row in dialog.item_rows.items() if row.unlocked} == {"sport_1", "sport_2", "study_1"}
    assert dialog.item_rows["sport_1"].name_label.text() == "Гантели"
    assert dialog.item_rows["sport_1"].hint_label.text() == "Рядом появятся гантели"


def test_collection_locked_items_say_how_many_marks_are_left(qapp, config, sample_snapshot):
    dialog = CollectionDialog(sample_snapshot, config)
    assert dialog.item_rows["sport_3"].status_label.text() == "Ещё 7 отметок «Спорт»"
    assert dialog.item_rows["work_1"].status_label.text() == "Ещё 2 отметки «Работа»"
    assert dialog.item_rows["work_3"].status_label.text() == "Ещё 14 отметок «Работа»"
    assert dialog.item_rows["social_1"].status_label.text() == "Ещё 3 отметки «Отношения»"
    assert dialog.item_rows["study_2"].status_label.text() == "Ещё 4 отметки «Учёба»"
    assert dialog.item_rows["sport_1"].status_label.text() == ""  # у открытых подсказки нет


def test_collection_opens_about_dialog(qapp, config, sample_snapshot, monkeypatch):
    opened = []
    monkeypatch.setattr(AboutDialog, "exec", lambda self: opened.append(self) or 0)
    dialog = CollectionDialog(sample_snapshot, config)
    dialog.about_btn.click()
    assert len(opened) == 1 and isinstance(opened[0], AboutDialog)


def test_about_dialog_shows_version_credits_and_font_license(qapp):
    dialog = AboutDialog()
    text = dialog.credits.toPlainText()
    assert dialog.credits.isReadOnly()
    assert text.startswith("# Credits and licenses") and "License summary" in text
    assert "CC-BY-SA" in text and "OGA-BY" in text and "Attribution is mandatory" in text
    assert text.index("License summary") < text.index("Items at a glance")  # сводка лицензий — в самом начале
    assert dialog.version.text() == f"Версия {__version__}"
    credit = dialog.font_credit.text()
    assert "Ark Pixel Font" in credit and "TakWolf" in credit and "SIL Open Font License 1.1" in credit
    assert "Pixelify" not in credit
    assert (ASSETS_DIR / "fonts" / "OFL-ArkPixel.txt").exists()  # текст лицензии шрифта лежит рядом с ним


def test_about_dialog_survives_missing_credits_file(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(about_module, "CREDITS_PATH", tmp_path / "нет.md")
    assert "CREDITS.md" in AboutDialog().credits.toPlainText()


# ---------------------------------------------------------------------- подтверждение архивирования
def test_confirm_archive_returns_the_clicked_choice(qapp):
    def press(label):
        dialog = QApplication.activeModalWidget()
        next(b for b in dialog.findChildren(PixelButton) if b.text() == label).click()

    QTimer.singleShot(50, lambda: press("Архивировать"))
    assert confirm_archive(None, "Зарядка") is True
    QTimer.singleShot(50, lambda: press("Отмена"))
    assert confirm_archive(None, "Зарядка") is False
