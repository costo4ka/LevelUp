"""Сцена: комната с персонажем и вся «обратная связь» наград. Рисует Look по снимку состояния, масштаб целый.

API, на который опираются окна (не менять без согласования):
    SceneWidget(manifest, config, compact=False, parent=None)
    set_snapshot(snap)             мгновенно, без анимации (первая отрисовка, обновление списка); отменяет эффекты
    play_reward(event)             награда за действие пользователя (анимации); event.before/after — снимки
                                   до и после. state_changed и reward приходят подряд в одном стеке вызовов,
                                   поэтому сцена вправе перекрыть то, что только что показал set_snapshot(after):
                                   снова показать event.before и перейти к event.after.
Для тестов и инструментов:
    effects_active()               идут ли эффекты награды
    skip_animations()              мгновенно завершить всё и показать итоговое состояние
    tick(ms)                       сдвинуть часы анимации (настоящий QTimer просто зовёт его с прошедшим временем)
    set_animations_enabled(bool)   выключено: play_reward = set_snapshot(event.after), без дыхания и мерцания
    snapshot, look                 итоговый снимок и Look, который нарисован сейчас (в покое это compose_look(snapshot))

Кадры (~60 к/с) идут только пока работают эффекты; в покое таймер просыпается раз в 350 мс (дыхание, аура стадии 5),
перерисовывая сцену только при смене дискретного состояния, а пока виджет скрыт — не работает вовсе. Статические
слои склеиваются один раз на вид и кэшируются; события поверх незаконченных доигрывают прежние мгновенно.
Эффекты и кэш спрайтов — в effects.py.
"""
from __future__ import annotations

import random
import zlib

from PyQt6.QtCore import QElapsedTimer, QPoint, QRect, QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import QBrush, QImage, QPainter
from PyQt6.QtWidgets import QSizePolicy, QWidget

from ..config import AppConfig
from ..domain.models import RewardEvent, Snapshot
from ..look import Look, Prop, SpriteManifest, compose_look
from . import palette
from .effects import (
    Banner, Confetti, Cue, Effect, Fade, Flash, Float, Frame, Hop, Pop, Puff, Ring, Sparkles, SpriteBank, Stars,
    Timeline,
)

FRAME_MS = 16  # шаг таймера, пока идут эффекты
IDLE_MS = 350  # шаг покоя: дыхание каждые два шага (700 мс), аура и искра — реже
MAX_STEP = 1000  # дольше этого за один тик не прокручиваем (сон, остановка цикла событий)
HOP_MS = 450
MAX_BANNERS = 3  # плашек на одно событие: показывается и стоит в очереди; остальные отбрасываются
SCORE_SIZE = 20  # «+10»: кегль в пикселях сцены; Ark Pixel рисуется на сетке 10 px, поэтому годятся только 10 и 20
TEXT_SIZE = 10  # плашки и «-10»
FEET, HEAD_Y, BODY_Y = 62, 20, 37  # строки кадра персонажа: под ступнями, центр головы, центр туловища
POP_MS, REVEAL_MS, LIGHT_MS = 450, 500, 600  # появление малого предмета, комнатного, света
ORIGIN = QPoint(0, 0)
AURA_SIZE = (64, 84)
AURA_RADII = (24, 33)
AURA_PULSE = (1.0, 1.05, 1.1, 1.05)  # дыхание ауры по фазам (каждая фаза — три шага покоя)
AURA_GOLD_LIGHT = "#eacb85"  # смесь GOLD и PANEL
# кольца ауры снаружи внутрь: (доля радиуса, плотность дизеринга из 4, цвет)
AURA_BANDS = ((1.0, 1, palette.GOLD), (0.86, 2, AURA_GOLD_LIGHT), (0.72, 3, AURA_GOLD_LIGHT))
SPARK_EVERY = 12  # редкая искра на ауре: раз в 12 шагов покоя, две ступени мерцания
SPARK_SPOTS = ((-22, -27), (25, -17), (-27, 4), (28, 14), (-18, 29), (21, 31))
CONFETTI_COLORS = (palette.GOLD, palette.MOSS, palette.BRICK, palette.PANEL, *palette.CATEGORY_COLORS.values())
NEW_LABEL = "Новое"
DAY_TEXT = "Все привычки выполнены!"


class SceneWidget(QWidget):
    def __init__(
        self, manifest: SpriteManifest, config: AppConfig, compact: bool = False, parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.manifest, self.config, self.compact = manifest, config, compact
        self._bank = SpriteBank(manifest.root)
        self._looks: dict[tuple, Look] = {}
        self._target: Snapshot | None = None  # итоговое состояние
        self._shown: Snapshot | None = None  # что нарисовано сейчас (во время анимации отличается от итога)
        self._hidden: frozenset[str] = frozenset()  # предметы, которые сейчас рисует эффект: prop:<id>, light:<id>
        self._timeline = Timeline()
        self._time = 0.0
        self._animate = True
        self._idle_seen: tuple[int, int, int, int] | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer)
        self._elapsed = QElapsedTimer()
        crop = manifest.compact_crop if compact else (0, 0, *manifest.scene)
        self._crop = QRect(*crop)
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setMinimumSize(self._crop.width(), self._crop.height())

    # ------------------------------------------------------------------ API
    @property
    def snapshot(self) -> Snapshot | None:
        return self._target

    @property
    def look(self) -> Look | None:
        """Вид, который нарисован в данный момент (в покое это compose_look последнего снимка)."""
        return self._look(self._shown) if self._shown is not None else None

    def set_snapshot(self, snap: Snapshot) -> None:
        self._timeline = Timeline()
        self._target = self._shown = snap
        self._hidden = frozenset()
        self._sync_timer()
        self.update()

    def play_reward(self, event: RewardEvent) -> None:
        if not (self._animate and self.isVisible()) or self._shown is None or event.kind not in ("complete", "undo"):
            self.set_snapshot(event.after)  # скрытое окно или анимации выключены: просто итог
            return
        self.skip_animations()  # событие поверх незаконченного: прежнее доигрываем мгновенно
        self._target, self._shown, self._hidden = event.after, event.before, frozenset()
        self._timeline = Timeline(self._plan(event))
        self._timeline.advance(0)  # эффекты без задержки стартуют до первой отрисовки
        self._sync_timer()
        self.update()

    def effects_active(self) -> bool:
        return self._timeline.active

    def skip_animations(self) -> None:
        self._timeline.skip()
        self._settle()
        self.update()

    def tick(self, ms: float) -> None:
        self._time += ms
        if self._timeline.active:
            self._timeline.advance(ms)
            if not self._timeline.active:
                self._settle()
            self.update()
        elif (idle := self._idle()) != self._idle_seen:
            self._idle_seen = idle
            self.update()

    def set_animations_enabled(self, enabled: bool) -> None:
        self._animate = enabled
        self.skip_animations()
        self._sync_timer()

    # ------------------------------------------------------------------ геометрия
    def sizeHint(self) -> QSize:
        factor = 2 if self.compact else 3
        return QSize(self._crop.width() * factor, self._crop.height() * factor)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return width * self._crop.height() // self._crop.width()

    def _view(self) -> tuple[int, int, int]:
        """Целый масштаб (устройств. пикселей на пиксель сцены) и левый верхний угол кадра в устройств. пикселях."""
        dpr, crop = self.devicePixelRatioF(), self._crop
        width, height = round(self.width() * dpr), round(self.height() * dpr)
        scale = max(1, int(min(width / crop.width(), height / crop.height()) + 1e-6))
        return scale, (width - crop.width() * scale) // 2, (height - crop.height() * scale) // 2

    # ------------------------------------------------------------------ таймеры
    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self.skip_animations()
        self._sync_timer()

    def _sync_timer(self) -> None:
        if not (self._animate and self.isVisible()):
            self._timer.stop()
            return
        interval = FRAME_MS if self._timeline.active else IDLE_MS
        if not self._timer.isActive() or self._timer.interval() != interval:
            self._elapsed.restart()
            self._timer.start(interval)

    def _on_timer(self) -> None:
        self.tick(min(self._elapsed.restart(), MAX_STEP))

    def _settle(self) -> None:
        """Итоговое состояние: что бы ни случилось с эффектами, вид равен compose_look последнего снимка."""
        self._timeline = Timeline()
        self._shown, self._hidden = self._target, frozenset()
        self._sync_timer()

    def _idle(self) -> tuple[int, int, int, int]:
        """Дискретное состояние покоя по часам: (дыхание, фаза ауры, кадр искры, её место)."""
        shown = self._shown
        if not self._animate or shown is None:
            return 0, 0, 0, 0
        n = int(self._time // IDLE_MS)
        bob = n // 2 % 2
        if shown.stage < shown.stage_count:
            return bob, 0, 0, 0
        cycle = n % SPARK_EVERY
        twinkle = 1 if cycle == 0 else 2 if cycle == 1 else 0
        return bob, n // 3 % len(AURA_PULSE), twinkle, n // SPARK_EVERY % len(SPARK_SPOTS)

    # ------------------------------------------------------------------ сборка вида
    def _look(self, snap: Snapshot) -> Look:
        key = (snap.base_id, snap.stage, tuple(snap.tiers.items()))
        if key not in self._looks:
            self._looks[key] = compose_look(self.manifest, snap.base_id, snap.stage, snap.tiers)
        return self._looks[key]

    def _layers(self, look: Look) -> tuple[QImage, QImage | None, QImage | None]:
        """Слои комнаты без предметов, которые сейчас рисуют эффекты: (под персонажем, над ним, освещение)."""
        bank, scene, hidden = self._bank, self.manifest.scene, self._hidden
        back = [p.file for p in look.props_back if f"prop:{p.id}" not in hidden]
        front = [p.file for p in look.props_front if f"prop:{p.id}" not in hidden]
        light = [
            path for uid, path in self.manifest.lighting.items()
            if path in look.lighting and f"light:{uid}" not in hidden
        ]
        return (
            bank.stack([self.manifest.background, *back], scene),
            bank.stack(front, scene) if front else None,
            bank.stack(light, scene) if light else None,
        )

    def _aura(self, phase: int) -> QImage:
        def make() -> QImage:
            width, height = AURA_SIZE
            image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.setPen(Qt.PenStyle.NoPen)
            for k, level, color in AURA_BANDS:  # снаружи внутрь, каждое кольцо заменяет плотность предыдущего
                rx, ry = AURA_RADII[0] * k * AURA_PULSE[phase], AURA_RADII[1] * k * AURA_PULSE[phase]
                painter.setBrush(QBrush(self._bank.tile(level, color)))
                painter.drawEllipse(QRectF(width / 2 - rx, height / 2 - ry, 2 * rx, 2 * ry))
            painter.end()
            return image

        return self._bank.memo(("aura", phase), make)

    # ------------------------------------------------------------------ рисование
    def paintEvent(self, event) -> None:  # noqa: N802
        shown = self._shown
        if shown is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        scale, ox, oy = self._view()
        dpr, crop = self.devicePixelRatioF(), self._crop
        if dpr != 1.0:
            painter.scale(1 / dpr, 1 / dpr)  # дальше координаты — устройственные пиксели, масштаб целый
        painter.setClipRect(ox, oy, crop.width() * scale, crop.height() * scale)
        painter.translate(ox - crop.x() * scale, oy - crop.y() * scale)
        painter.scale(scale, scale)
        look, timeline, bank = self._look(shown), self._timeline, self._bank
        below, above, light = self._layers(look)
        bob, aura, spark, spot = self._idle()
        painter.drawImage(0, 0, below)
        timeline.paint(painter, "back", bank)
        if shown.stage >= shown.stage_count:
            cx, cy = self._body_center()
            image = self._aura(aura)
            painter.drawImage(cx - image.width() // 2, cy - image.height() // 2, image)
        self._paint_character(painter, look, timeline.frame(), bob)
        timeline.paint(painter, "front", bank)
        for layer in (above, light):
            if layer is not None:
                painter.drawImage(0, 0, layer)
        timeline.paint(painter, "light", bank)
        timeline.paint(painter, "fx", bank)
        if spark:
            self._paint_spark(painter, spark, spot)
        timeline.paint(painter, "hud", bank)

    def _body_center(self) -> tuple[int, int]:
        ax, ay = self.manifest.anchor
        return ax + self.manifest.frame // 2, ay + BODY_Y

    def _paint_character(self, painter: QPainter, look: Look, frame: Frame, bob: int) -> None:
        bank, ax, ay = self._bank, *self.manifest.anchor
        size = (self.manifest.frame, self.manifest.frame)
        shadow = [layer.file for layer in look.character_layers if layer.slot == "shadow"]
        body = bank.stack([layer.file for layer in look.character_layers if layer.slot != "shadow"], size)
        painter.drawImage(ax, ay, bank.stack(shadow, size))  # тень остаётся на полу
        w = h = round(size[0] * frame.pulse)
        lift = round(frame.lift) + bob
        target = QRect(ax + (size[0] - w) // 2, ay + FEET - lift - round(FEET * frame.pulse), w, h)
        painter.drawImage(target, body)
        if frame.flash and (glow := bank.dithered(bank.silhouette(body), frame.flash)) is not None:
            painter.drawImage(target, glow)

    def _paint_spark(self, painter: QPainter, frame: int, spot: int) -> None:
        spark, (cx, cy) = self._bank.fx("spark"), self._body_center()
        dx, dy = SPARK_SPOTS[spot]
        x, y = cx + dx - 2, cy + dy - 2
        if frame == 1:
            painter.drawImage(x, y, spark)
        else:
            painter.drawImage(QRect(x + 1, y + 1, 3, 3), spark, QRect(1, 1, 3, 3))

    # ------------------------------------------------------------------ хореография наград
    def _swap(self, snap: Snapshot, hidden: frozenset[str]) -> None:
        self._shown, self._hidden = snap, hidden

    def _reveal(self, token: str) -> None:
        self._hidden -= {token}

    def _art(self, uid: str) -> tuple[Prop, QImage, QRect] | None:
        """Предмет комнаты, его PNG и рамка непрозрачных пикселей; None, если предмета нет или файл не читается."""
        prop = self.manifest.props.get(uid)
        if prop is None:
            return None
        image = self._bank.image(prop.file)
        box = SpriteBank.bbox(image)
        return None if box.isEmpty() else (prop, image, box)

    def _small(self, box: QRect) -> bool:
        return box.width() * 2 < self.manifest.scene[0]

    def _appear(self, uid: str, at: float, rng: random.Random) -> list[Effect]:
        """Появление предмета: мелкий выскакивает с искрами, комнатный проявляется дизерингом, свет разгорается."""
        effects: list[Effect] = []
        end = 0.0
        if art := self._art(uid):
            prop, image, box = art
            if self._small(box):
                end = POP_MS
                effects += [Pop(at, image.copy(box), box, prop.layer, POP_MS), Sparkles(at + 80, box, rng)]
            else:
                end = REVEAL_MS
                effects.append(Fade(at, REVEAL_MS, image, ORIGIN, prop.layer, reverse=True))
        if uid in self.manifest.props:
            effects.append(Cue(at + end, lambda: self._reveal(f"prop:{uid}")))
        if path := self.manifest.lighting.get(uid):
            effects += [
                Fade(at, LIGHT_MS, self._bank.image(path), ORIGIN, "light", reverse=True, smooth=True),
                Cue(at + LIGHT_MS, lambda: self._reveal(f"light:{uid}")),
            ]
        return effects

    def _vanish(self, uid: str, rng: random.Random) -> list[Effect]:
        """Исчезновение потерянного предмета: растворяется дизерингом, мелкий ещё и облачком пыли."""
        effects: list[Effect] = []
        if art := self._art(uid):
            prop, image, box = art
            if self._small(box):
                centre = box.center()
                effects += [
                    Fade(0, 320, image.copy(box), box.topLeft(), prop.layer),
                    Puff(0, (centre.x(), centre.y()), rng),
                ]
            else:
                effects.append(Fade(0, 400, image, ORIGIN, prop.layer))
        if path := self.manifest.lighting.get(uid):
            effects.append(Fade(0, 450, self._bank.image(path), ORIGIN, "light", smooth=True))
        return effects

    def _banners(self, event: RewardEvent, start: float) -> list[Effect]:
        """Плашки одна за другой (не больше MAX_BANNERS): новые предметы, стадия, день выполнен."""
        specs: list[tuple[float, dict]] = []  # (не раньше чем, параметры плашки)
        for uid in event.new_unlocks:
            try:
                name = self.config.unlock(uid)[1].name
            except KeyError:
                continue
            specs.append((0, {"text": name, "label": NEW_LABEL, "icon": self._bank.icon(f"unlock_{uid}")}))
        if event.stage_after > event.stage_before:
            title = f"Стадия {event.stage_after}: {event.after.stage_name}"
            specs.append((0, {"text": title, "icon": self._bank.fx("star"), "zoom": 2}))
        if event.day_completed:
            specs.append((HOP_MS + 100, {"text": DAY_TEXT, "centered": True}))
        effects: list[Effect] = []
        t = start
        for earliest, spec in specs[:MAX_BANNERS]:
            effects.append(Banner(max(t, earliest), self._bank, self._crop, TEXT_SIZE, **spec))
            t = effects[-1].end
        return effects

    def _plan(self, event: RewardEvent) -> list[Effect]:
        bank, manifest = self._bank, self.manifest
        looks = self._look(event.before), self._look(event.after)
        rng = random.Random(zlib.crc32(f"{event.habit_id}:{event.after.total_xp}:{event.kind}".encode()))
        ax, ay = manifest.anchor
        cx, body = ax + manifest.frame // 2, self._body_center()
        complete = event.kind == "complete"
        effects: list[Effect] = []
        if complete:
            color = palette.CATEGORY_COLORS.get(event.category, palette.INK_2)
            score = bank.text(f"+{event.xp_delta}", color, SCORE_SIZE, palette.INK)
            effects += [
                Hop(0, 10, HOP_MS), Stars(0, (cx, ay + HEAD_Y), rng),
                Float(0, cx, ay - 6, score, bank.metrics(SCORE_SIZE), bank.icon(f"cat_{event.category}")),
            ]
        else:
            muted = bank.text(f"-{abs(event.xp_delta)}", palette.LINE_SOFT, TEXT_SIZE, palette.INK_2)
            effects.append(Float(0, cx, ay + 4, muted, bank.metrics(TEXT_SIZE), rise=10, duration=800))
        swap = HOP_MS / 2 if complete else 0  # новый вид — в верхней точке прыжка
        fresh = frozenset(
            [f"prop:{u}" for u in event.new_unlocks if u in manifest.props]
            + [f"light:{u}" for u in event.new_unlocks if u in manifest.lighting]
        )
        effects.append(Cue(swap, lambda: self._swap(event.after, fresh)))
        for i, uid in enumerate(event.new_unlocks):
            effects += self._appear(uid, swap + 160 * i, rng)
        for uid in event.lost_unlocks:
            effects += self._vanish(uid, rng)
        if looks[0].character_layers != looks[1].character_layers:
            effects.append(Flash(swap, 240, pulse=0.08) if complete else Flash(swap, 160, peak=2))
            if not complete:
                effects.append(Puff(0, body, rng))
        if event.stage_after > event.stage_before:
            effects += [Ring(swap, body, 6, 46, palette.GOLD), Ring(swap + 110, body, 4, 36, palette.PANEL)]
        if event.day_completed:
            floor = (manifest.floor_y + 2, manifest.scene[1] - 4)
            effects += [Hop(HOP_MS, 12, HOP_MS), Confetti(HOP_MS, self._crop, floor, rng, CONFETTI_COLORS)]
        if complete:
            effects += self._banners(event, swap)
        return effects
