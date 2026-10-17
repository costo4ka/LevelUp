"""Сцена: вид по снимку, награды (эффекты), компактный режим и устойчивость. Время двигает tick(), таймеры не нужны."""
from __future__ import annotations

import dataclasses
import logging
import shutil

import pytest
from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from levelup.config import ASSETS_DIR
from levelup.domain.models import CategoryView, RewardEvent, Snapshot
from levelup.look import compose_look, load_sprites
from levelup.ui import palette
from levelup.ui.effects import Banner, Cue, SpriteBank, Timeline, circle, pop_scale, steps
from levelup.ui.scene import DAY_TEXT, FRAME_MS, IDLE_MS, MAX_BANNERS, NEW_LABEL, SCORE_SIZE, TEXT_SIZE, SceneWidget
from tests.helpers import ok


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="session")
def manifest(config):
    return load_sprites(config)


@pytest.fixture
def make_scene(qapp, manifest, config):
    """Фабрика видимых виджетов сцены; масштаб 2 (384x256) по умолчанию, чтобы кадры были маленькими."""
    scenes: list[SceneWidget] = []

    def make(compact: bool = False, size: tuple[int, int] | None = None, sprites=None) -> SceneWidget:
        scene = SceneWidget(sprites or manifest, config, compact=compact)
        scene.resize(*(size or ((256, 192) if compact else (384, 256))))
        scene.show()
        scenes.append(scene)
        return scene

    yield make
    for scene in scenes:
        scene.hide()
        scene.deleteLater()


@pytest.fixture
def base(onboarded):
    return Snapshot.from_dict(ok(onboarded.svc.get_snapshot()))


@pytest.fixture
def snap(base, config):
    """Снимок с нужной стадией и тирами категорий (порядок: sport, work, study, social)."""

    def make(stage: int = 1, tiers: tuple[int, ...] = (0, 0, 0, 0), base_id: str = "m", done: bool = False) -> Snapshot:
        points = [0, *config.category_tiers]
        cats = tuple(CategoryView(cid, points[tier], tier, None) for cid, tier in zip(config.category_ids, tiers))
        unlocked = tuple(f"{cid}_{k}" for cid, tier in zip(config.category_ids, tiers) for k in range(1, tier + 1))
        return dataclasses.replace(
            base, base_id=base_id, stage=stage, stage_name=config.stage_names[stage - 1], categories=cats,
            unlocked=unlocked, day_complete=done,
        )

    return make


def reward(kind: str, before: Snapshot, after: Snapshot, category: str = "sport", day: bool = False) -> RewardEvent:
    """То же, что собирает контроллер после успешной отметки."""
    was, now = set(before.unlocked), set(after.unlocked)
    return RewardEvent(
        kind=kind, habit_id="h1", category=category, xp_delta=10 if kind == "complete" else -10,
        new_unlocks=tuple(u for u in after.unlocked if u not in was),
        lost_unlocks=tuple(u for u in before.unlocked if u not in now),
        stage_before=before.stage, stage_after=after.stage, day_completed=day, before=before, after=after,
    )


def run_out(scene: SceneWidget, limit: int = 15_000, step: int = 25) -> int:
    """Прокручивает время, пока идут эффекты; возвращает, сколько мс прошло."""
    spent = 0
    while scene.effects_active():
        assert spent < limit, "эффекты не заканчиваются"
        scene.tick(step)
        spent += step
    return spent


def frozen_image(scene: SceneWidget):
    """Кадр без дыхания и мерцания: сравнивать сцены можно независимо от того, сколько часов у них прошло."""
    scene.set_animations_enabled(False)
    return scene.grab().toImage()


# (вид, стадия и тиры до, стадия и тиры после, день выполнен, категория)
CASES = {
    "plain complete": ("complete", (1, (0, 0, 0, 0)), (1, (0, 0, 0, 0)), False, "sport"),
    "room prop (sport_1)": ("complete", (1, (0, 0, 0, 0)), (1, (1, 0, 0, 0)), False, "sport"),
    "prop and layers (sport_3)": ("complete", (1, (2, 0, 0, 0)), (1, (3, 0, 0, 0)), False, "sport"),
    "character layers (work_2)": ("complete", (1, (0, 1, 0, 0)), (1, (0, 2, 0, 0)), False, "work"),
    "warm evening (social_3)": ("complete", (1, (0, 0, 0, 2)), (1, (0, 0, 0, 3)), False, "social"),
    "stage up": ("complete", (1, (1, 0, 0, 0)), (2, (1, 0, 0, 0)), False, "sport"),
    "stage 5 with aura": ("complete", (4, (1, 0, 0, 0)), (5, (1, 0, 0, 0)), False, "sport"),
    "day completed": ("complete", (1, (1, 0, 0, 0)), (1, (1, 0, 0, 0)), True, "sport"),
    "everything at once": ("complete", (4, (0, 1, 1, 2)), (5, (1, 2, 1, 3)), True, "study"),
    "undo": ("undo", (1, (0, 0, 0, 0)), (1, (0, 0, 0, 0)), False, "sport"),
    "undo lost prop": ("undo", (1, (1, 0, 0, 0)), (1, (0, 0, 0, 0)), False, "sport"),
    "undo lost layers": ("undo", (1, (0, 2, 0, 0)), (1, (0, 1, 0, 0)), False, "work"),
    "undo lost light": ("undo", (1, (0, 0, 0, 3)), (1, (0, 0, 0, 2)), False, "social"),
    "undo stage down": ("undo", (2, (0, 0, 0, 0)), (1, (0, 0, 0, 0)), False, "sport"),
}


def build(snap, case):
    kind, (stage_b, tiers_b), (stage_a, tiers_a), day, category = case
    return reward(kind, snap(stage_b, tiers_b), snap(stage_a, tiers_a, done=day), category, day)


def expected_look(manifest, snapshot):
    return compose_look(manifest, snapshot.base_id, snapshot.stage, snapshot.tiers)


# ---------------------------------------------------------------- вид и кэш
def test_look_equals_compose_look_and_is_cached(make_scene, manifest, snap):
    scene = make_scene()
    assert scene.look is None and scene.snapshot is None
    variants = (("m", 1, (0, 0, 0, 0)), ("w", 3, (1, 2, 0, 3)), ("m", 5, (3, 3, 3, 3)), ("w", 2, (0, 3, 0, 0)))
    for base_id, stage, tiers in variants:
        shot = snap(stage, tiers, base_id)
        scene.set_snapshot(shot)
        assert scene.snapshot is shot and not scene.effects_active()
        assert scene.look == expected_look(manifest, shot)
        assert scene.look is scene.look  # не пересобирается на каждый вызов
        assert not scene.grab().toImage().isNull()


def test_set_snapshot_cancels_running_effects(make_scene, manifest, snap):
    scene = make_scene()
    event = build(snap, CASES["room prop (sport_1)"])
    scene.set_snapshot(event.after)
    scene.play_reward(event)
    scene.tick(100)
    other = snap(3, (3, 3, 3, 3))
    scene.set_snapshot(other)
    assert not scene.effects_active() and scene.look == expected_look(manifest, other)


# ---------------------------------------------------------------- награды
@pytest.mark.parametrize("name", CASES)
def test_reward_plays_then_settles_to_final_look(name, make_scene, manifest, snap):
    event = build(snap, CASES[name])
    scene, fresh = make_scene(), make_scene()
    scene.set_snapshot(event.after)  # так делают окна: state_changed, затем сразу reward
    scene.play_reward(event)
    assert scene.effects_active()
    shown = event.after if event.kind == "undo" else event.before  # отметка: до прыжка виден прежний вид
    assert scene.look == expected_look(manifest, shown)
    assert not scene.grab().toImage().isNull()
    assert run_out(scene) > 400  # награда занимает заметное время
    assert scene.look == expected_look(manifest, event.after) and scene.snapshot is event.after
    fresh.set_snapshot(event.after)
    assert frozen_image(scene) == frozen_image(fresh)  # никаких остатков: предметы на местах, слои без артефактов


SKIPPED = ["room prop (sport_1)", "warm evening (social_3)", "everything at once", "undo lost prop"]


@pytest.mark.parametrize("name", SKIPPED)
def test_skip_animations_shows_final_state_immediately(name, make_scene, manifest, snap):
    event = build(snap, CASES[name])
    scene, fresh = make_scene(), make_scene()
    scene.set_snapshot(event.after)
    scene.play_reward(event)
    scene.tick(300)
    scene.skip_animations()
    assert not scene.effects_active() and scene.look == expected_look(manifest, event.after)
    fresh.set_snapshot(event.after)
    assert frozen_image(scene) == frozen_image(fresh)


def test_new_event_finishes_previous_one(make_scene, manifest, snap):
    first = build(snap, CASES["warm evening (social_3)"])
    second = reward("undo", first.after, first.before, "social")
    scene = make_scene()
    scene.set_snapshot(first.after)
    scene.play_reward(first)
    scene.tick(200)
    scene.set_snapshot(second.after)  # окна: state_changed второго события
    scene.play_reward(second)
    assert scene.effects_active()
    run_out(scene)
    assert scene.look == expected_look(manifest, second.after) and scene.snapshot is second.after


def test_banner_queue_is_limited(make_scene, snap):
    event = build(snap, CASES["everything at once"])  # 3 предмета, стадия и день: плашек больше предела
    assert len(event.new_unlocks) + 2 > MAX_BANNERS
    scene = make_scene()
    scene.set_snapshot(event.after)
    scene.play_reward(event)
    spent = run_out(scene)
    assert MAX_BANNERS * Banner.TOTAL <= spent <= 225 + MAX_BANNERS * Banner.TOTAL + 400


def test_real_service_events_play(onboarded, config, make_scene, manifest):
    """Событие из настоящих снимков сервиса: третья отметка за три дня открывает гантели и закрывает день."""
    svc, snapshots = onboarded.svc, []
    for _ in range(3):
        day = ok(svc.get_snapshot())["date"]
        snapshots.append(Snapshot.from_dict(ok(svc.get_snapshot())))
        snapshots.append(Snapshot.from_dict(ok(svc.set_completion(onboarded.first_id, day, True))["snapshot"]))
        onboarded.clock.advance(days=1)
    before, after = snapshots[4], snapshots[5]
    event = reward("complete", before, after, day=after.day_complete)
    assert event.new_unlocks == ("sport_1",) and event.day_completed
    scene = make_scene()
    scene.set_snapshot(after)
    scene.play_reward(event)
    assert scene.effects_active()
    run_out(scene)
    assert scene.look == expected_look(manifest, after)


# ---------------------------------------------------------------- видимость, таймеры, выключенные анимации
def test_props_are_handed_over_to_static_layers_when_their_effect_ends(make_scene, manifest, snap):
    event = build(snap, CASES["room prop (sport_1)"])
    scene = make_scene()
    scene.set_snapshot(event.after)
    scene.play_reward(event)
    scene.tick(224)  # до верхней точки прыжка виден прежний вид
    assert scene.look == expected_look(manifest, event.before) and not scene._hidden
    scene.tick(1)  # в верхней точке: новый вид, предмет рисует эффект
    assert scene.look == expected_look(manifest, event.after) and scene._hidden == {"prop:sport_1"}
    scene.tick(449)
    assert scene._hidden == {"prop:sport_1"}  # выскакивает ещё кадр
    scene.tick(2)
    assert not scene._hidden and scene.effects_active()  # дальше он в статическом слое, а плашка ещё висит


def test_hidden_widget_does_not_animate(make_scene, manifest, snap):
    event = build(snap, CASES["prop and layers (sport_3)"])
    scene = make_scene()
    scene.set_snapshot(event.before)
    scene.hide()
    scene.play_reward(event)
    assert not scene.effects_active() and scene.snapshot is event.after
    assert scene.look == expected_look(manifest, event.after)
    scene.show()
    assert not scene.effects_active()


def test_hiding_finishes_running_effects(make_scene, manifest, snap):
    event = build(snap, CASES["room prop (sport_1)"])
    scene = make_scene()
    scene.set_snapshot(event.after)
    scene.play_reward(event)
    scene.hide()
    assert not scene.effects_active() and scene.look == expected_look(manifest, event.after)


def test_timers_run_only_while_visible_and_idle_rate_is_low(make_scene, snap):
    event = build(snap, CASES["plain complete"])
    scene = make_scene()
    scene.set_snapshot(event.after)
    assert scene._timer.isActive() and scene._timer.interval() == IDLE_MS and 1000 / IDLE_MS <= 4  # покой: несколько Гц
    scene.play_reward(event)
    assert scene._timer.interval() == FRAME_MS  # кадры идут только пока работают эффекты
    run_out(scene)
    assert scene._timer.interval() == IDLE_MS
    scene.hide()
    assert not scene._timer.isActive()
    scene.show()
    assert scene._timer.isActive()


def test_idle_redraws_only_when_the_picture_changes(make_scene, snap):
    scene = make_scene()
    scene.set_snapshot(snap(5))  # самый «живой» покой: дыхание, пульс ауры, искра
    redraws = []
    scene.update = lambda *args: redraws.append(1)
    for _ in range(12_000 // IDLE_MS):  # 12 секунд покоя тем же шагом, что у таймера
        scene.tick(IDLE_MS)
    assert 0 < len(redraws) <= 3 * 12  # не чаще нескольких раз в секунду


def test_real_timer_drives_the_clock(make_scene, snap):
    event = build(snap, CASES["plain complete"])
    scene = make_scene()
    scene.set_snapshot(event.after)
    scene.play_reward(event)
    QTest.qWait(150)
    assert 50 < scene._timeline.time < 1000  # QTimer сам двигает время по часам


def test_disabled_animations_are_a_plain_snapshot(make_scene, manifest, snap):
    event = build(snap, CASES["room prop (sport_1)"])
    scene = make_scene()
    scene.set_animations_enabled(False)
    assert not scene._timer.isActive()
    scene.play_reward(event)
    assert not scene.effects_active() and scene.look == expected_look(manifest, event.after)
    before = scene.grab().toImage()
    scene.tick(700)
    assert scene.grab().toImage() == before  # и дыхания тоже нет
    scene.set_animations_enabled(True)
    assert scene._timer.isActive()


def test_breathing_bob_is_one_pixel_every_700_ms(make_scene, snap):
    scene = make_scene()
    scene.set_snapshot(snap(2))
    rest = scene.grab().toImage()
    scene.tick(699)
    assert scene.grab().toImage() == rest
    scene.tick(1)
    risen = scene.grab().toImage()
    assert risen != rest
    scene.tick(700)
    assert scene.grab().toImage() == rest


def test_stage_five_has_pulsing_aura_and_lower_stages_do_not(make_scene, snap):
    five, four = make_scene(), make_scene()
    five.set_snapshot(snap(5))
    four.set_snapshot(snap(4))

    def left_of_figure(scene):  # здесь, левее фигуры, на пустой комнате может быть только свечение
        return scene.grab().toImage().copy(2 * 70, 2 * 80, 2 * 9, 2 * 20)

    rest, plain = left_of_figure(five), left_of_figure(four)
    assert rest != plain
    five.tick(2100)
    four.tick(2100)
    assert left_of_figure(five) != rest  # пульсирует
    assert left_of_figure(four) == plain
    five.tick(2100)
    assert left_of_figure(five) == rest  # цикл замкнулся


# ---------------------------------------------------------------- геометрия и компактный режим
def test_compact_geometry_and_crop(make_scene, manifest, snap):
    x, y, w, h = manifest.compact_crop
    full, small = make_scene(size=(2 * 192, 2 * 128)), make_scene(compact=True, size=(2 * w, 2 * h))
    assert small.sizeHint() == QSize(2 * w, 2 * h) and full.sizeHint() == QSize(3 * 192, 3 * 128)
    assert small.minimumSize() == QSize(w, h) and full.minimumSize() == QSize(192, 128)
    assert small.heightForWidth(2 * w) == 2 * h and full.heightForWidth(384) == 256
    shot = snap(3, (2, 2, 1, 0))
    for scene in (full, small):
        scene.set_snapshot(shot)
    assert frozen_image(small) == frozen_image(full).copy(2 * x, 2 * y, 2 * w, 2 * h)  # компактный вид — вырезка сцены


def test_integer_scale_nearest_and_centered(make_scene, snap):
    shot = snap(3, (1, 1, 1, 1))
    exact, odd = make_scene(size=(384, 256)), make_scene(size=(500, 400))  # 500/192 = 2.6, 400/128 = 3.1: масштаб 2
    for scene in (exact, odd):
        scene.set_snapshot(shot)
    expected = frozen_image(exact)
    assert frozen_image(odd).copy((500 - 384) // 2, (400 - 256) // 2, 384, 256) == expected


def banner_specs(bank, config):
    """Все тексты плашек, которые показывает сцена: предметы каталога, стадии и «день выполнен»."""
    specs = [
        (unlock.name, NEW_LABEL, bank.icon(f"unlock_{unlock.id}"), 1, False)
        for category in config.categories for unlock in category.unlocks
    ]
    specs += [(f"Стадия {n}: {name}", None, bank.fx("star"), 2, False) for n, name in enumerate(config.stage_names, 1)]
    return specs + [(DAY_TEXT, None, None, 1, True)]


@pytest.mark.parametrize("compact", [True, False], ids=["compact", "full"])
def test_banners_fit_the_visible_crop_and_stay_clear_of_the_head(compact, make_scene, manifest, config):
    scene = make_scene(compact=compact)
    bank, crop = scene._bank, scene._crop
    head = manifest.anchor[1] + 12  # макушка в сцене
    for text, label, icon, zoom, centered in banner_specs(bank, config):
        banner = Banner(0, bank, crop, TEXT_SIZE, text, label, icon, zoom, centered)
        image = QImage(crop.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.translate(-crop.x(), -crop.y())
        banner.paint(painter, Banner.IN + 100, bank)  # плашка на месте
        painter.end()
        ink = SpriteBank.bbox(image)
        assert (ink.width(), ink.height()) == (banner.w, banner.h), text  # ничего не торчит из панели
        assert ink.left() >= Banner.MARGIN and ink.right() <= crop.width() - 1 - Banner.MARGIN, text
        assert crop.y() + ink.bottom() < head, text


def test_long_text_wraps_by_words_to_the_crop_width(make_scene, manifest):
    scene = make_scene(compact=True)
    bank, crop = scene._bank, scene._crop
    compact_day = Banner(0, bank, crop, TEXT_SIZE, DAY_TEXT, centered=True)
    full_day = Banner(0, bank, QRect(0, 0, 192, 128), TEXT_SIZE, DAY_TEXT, centered=True)
    assert (len(compact_day.rows), len(full_day.rows)) == (2, 1)  # в компактной сцене в строку не влезает
    texts = (DAY_TEXT, "Очень длинное название предмета, которого нет в каталоге", "Н" * 60, "", "я")
    for text in texts:
        for size in (10, 20):
            for limit in (24, 60, 111):
                lines = bank.wrap(text, limit, size)
                assert lines and all(bank.width(line, size) <= limit or len(line) == 1 for line in lines), (text, limit)
                assert "".join(lines).replace(" ", "") == "".join(text.split())  # ни одной буквы не потеряно
    absurd = Banner(0, bank, crop, TEXT_SIZE, "Разрывнеслово" * 12, label=NEW_LABEL, icon=bank.icon("unlock_sport_1"))
    assert absurd.w <= crop.width() - 2 * Banner.MARGIN  # даже слово без пробелов не раздвигает плашку


def test_text_is_drawn_on_the_font_grid(make_scene):
    bank = make_scene()._bank
    for size in (TEXT_SIZE, Banner.LABEL_SIZE, SCORE_SIZE):
        assert size % palette.PIXEL_UNIT == 0 and palette.pixel_font(size).pixelSize() == size  # кегль не округляется
        for outline in (None, palette.INK):
            image = bank.text("Все привычки выполнены! +10 -10", palette.INK_2, size, outline)
            alphas = {image.pixelColor(x, y).alpha() for x in range(image.width()) for y in range(image.height())}
            assert alphas <= {0, 255}  # без сглаживания: пиксели шрифта целые, ничего не «плывёт»
    assert bank.metrics(2 * TEXT_SIZE).cap == 2 * bank.metrics(TEXT_SIZE).cap


# ---------------------------------------------------------------- устойчивость к потерянным файлам
def test_missing_sprites_never_break_painting(tmp_path, config, make_scene, snap, caplog):
    shutil.copytree(ASSETS_DIR / "sprites", tmp_path / "sprites")
    missing = ["room/props/sport_1.png", "fx/star.png", "icons/unlock_sport_1.png", "icons/cat_sport.png",
               "character/m/hair_2.png", "room/lighting_warm.png", "room/props/social_3.png"]
    for rel in missing:
        (tmp_path / "sprites" / rel).unlink()
    broken = load_sprites(config, tmp_path)
    scene = make_scene(sprites=broken)
    names = ("room prop (sport_1)", "stage up", "warm evening (social_3)", "undo lost light")
    events = [build(snap, CASES[name]) for name in names]
    with caplog.at_level(logging.WARNING, logger="levelup.ui"):
        for _ in range(2):
            for event in events:
                scene.set_snapshot(event.after)
                scene.play_reward(event)
                scene.grab()
                run_out(scene)
                assert scene.look == expected_look(broken, event.after)
                scene.grab()
    logged = [record.getMessage() for record in caplog.records if "ASSET_MISSING" in record.getMessage()]
    assert sorted(logged) == sorted(set(logged))  # каждый файл — в журнале один раз
    assert any("hair_2.png" in line for line in logged) and any("star.png" in line for line in logged)


# ---------------------------------------------------------------- примитивы эффектов
def test_effect_primitives():
    assert pop_scale(0) == 0 and pop_scale(1) == 1
    assert max(pop_scale(i / 100) for i in range(101)) == pytest.approx(1.15, abs=0.01)
    assert steps(1.0, 0.4) == 1.0 and steps(0.0, 0.4) == 0.0 and steps(0.15, 0.4) == 0.5  # четвертями
    for r in (3, 8, 20):
        points = set(circle(r))
        assert all((-x, y) in points and (y, x) in points for x, y in points)  # симметрия
        assert all(abs((x * x + y * y) ** 0.5 - r) < 1 for x, y in points)


def test_timeline_runs_cues_in_order_and_skip_finishes_everything():
    log: list[str] = []
    cues = ((300, "c"), (0, "a"), (100, "b"))
    timeline = Timeline([Cue(at, lambda name=name: log.append(name)) for at, name in cues])
    timeline.advance(0)
    assert log == ["a"] and timeline.active
    timeline.advance(150)
    assert log == ["a", "b"]
    timeline.skip()
    assert log == ["a", "b", "c"] and not timeline.active
