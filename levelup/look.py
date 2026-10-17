"""Внешний вид: какие слои персонажа и предметы комнаты показывать при данном состоянии.

Чистый Python без Qt: манифесты спрайтов (character.json, room.json) и сборка `Look`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .config import ASSETS_DIR, AppConfig, ConfigError, read_json, png_problem

SPRITES_DIR = "sprites"


@dataclass(frozen=True)
class Layer:
    id: str
    file: Path
    z: int
    slot: str


@dataclass(frozen=True)
class CharacterBase:
    id: str
    title: str
    layers: Mapping[str, Layer]
    default: tuple[str, ...]
    stages: Mapping[int, tuple[str, ...]]
    tiers: Mapping[str, Mapping[int, tuple[str, ...]]]


@dataclass(frozen=True)
class Prop:
    id: str  # идентификатор предмета: sport_1, social_3 ...
    file: Path  # PNG размером со сцену, предмет нарисован на своём месте
    layer: str  # "back" — до персонажа, "front" — после
    order: int


@dataclass(frozen=True)
class SpriteManifest:
    frame: int
    bases: Mapping[str, CharacterBase]
    scene: tuple[int, int]
    anchor: tuple[int, int]
    floor_y: int
    compact_crop: tuple[int, int, int, int]
    background: Path
    props: Mapping[str, Prop]
    lighting: Mapping[str, Path]
    root: Path

    def all_files(self) -> list[tuple[str, Path]]:
        files = [(f"{b.id}/{layer.id}", layer.file) for b in self.bases.values() for layer in b.layers.values()]
        files.append(("room/background", self.background))
        files.extend((f"prop/{p.id}", p.file) for p in self.props.values())
        files.extend((f"lighting/{key}", path) for key, path in self.lighting.items())
        return files


@dataclass(frozen=True)
class Look:
    character_layers: tuple[Layer, ...]  # снизу вверх
    props_back: tuple[Prop, ...]
    props_front: tuple[Prop, ...]
    lighting: tuple[Path, ...]  # оверлеи освещения поверх всей сцены
    unlocked: frozenset[str]


def _safe(root: Path, rel: object, base: str = "") -> Path:
    if not isinstance(rel, str) or not rel or Path(rel).is_absolute():
        raise ConfigError(f"спрайты: некорректный путь {rel!r}")
    path = (root / base / rel).resolve()
    if not path.is_relative_to(root):
        raise ConfigError(f"спрайты: путь выходит за каталог ресурсов: {rel}")
    return path


def _ints(value: object, count: int, name: str) -> tuple[int, ...]:
    if not isinstance(value, list) or len(value) != count or any(type(v) is not int for v in value):
        raise ConfigError(f"спрайты: {name} должно быть списком из {count} целых")
    return tuple(value)


def _layer_ids(value: object, layers: Mapping[str, Layer], where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(v, str) or v not in layers for v in value):
        raise ConfigError(f"character.json: {where} ссылается на неизвестный слой")
    return tuple(value)


def _base(base_id: str, raw: dict, root: Path, config: AppConfig) -> CharacterBase:
    layers: dict[str, Layer] = {}
    for layer_id, item in raw["layers"].items():
        z, slot = item["z"], item["slot"]
        if type(z) is not int or not isinstance(slot, str) or not slot:
            raise ConfigError(f"character.json: слой {base_id}/{layer_id} описан неверно")
        layers[layer_id] = Layer(layer_id, _safe(root, item["file"], "character"), z, slot)
    stages = {}
    for key, ids in raw.get("stages", {}).items():
        stage = int(key)
        if not 2 <= stage <= config.stage_count:
            raise ConfigError(f"character.json: стадия {key} вне диапазона 2..{config.stage_count}")
        stages[stage] = _layer_ids(ids, layers, f"{base_id}.stages.{key}")
    tiers: dict[str, dict[int, tuple[str, ...]]] = {}
    for category in config.categories:
        table = raw.get("tiers", {}).get(category.id)
        if not isinstance(table, dict) or set(table) != {str(k) for k in range(1, len(config.category_tiers) + 1)}:
            raise ConfigError(f"character.json: {base_id}.tiers.{category.id} должен содержать тиры 1..{len(config.category_tiers)}")
        tiers[category.id] = {int(k): _layer_ids(ids, layers, f"{base_id}.tiers.{category.id}.{k}") for k, ids in table.items()}
    return CharacterBase(
        base_id, str(raw["title"]), layers, _layer_ids(raw["default"], layers, f"{base_id}.default"), stages, tiers
    )


def load_sprites(config: AppConfig, assets_dir: Path = ASSETS_DIR) -> SpriteManifest:
    root = (assets_dir / SPRITES_DIR).resolve()
    character = read_json(root / "character" / "character.json")
    room = read_json(root / "room" / "room.json")
    try:
        bases = {bid: _base(bid, raw, root, config) for bid, raw in character["bases"].items()}
        missing = [b for b in config.character_bases if b not in bases]
        if missing:
            raise ConfigError(f"character.json: нет персонажей {', '.join(missing)}")
        unlock_ids = {u.id for c in config.categories for u in c.unlocks}
        props = {}
        for unlock_id, item in room["props"].items():
            if unlock_id not in unlock_ids or item["layer"] not in ("back", "front") or type(item["order"]) is not int:
                raise ConfigError(f"room.json: предмет {unlock_id} описан неверно")
            props[unlock_id] = Prop(unlock_id, _safe(root, item["file"]), item["layer"], item["order"])
        lighting = {}
        for unlock_id, rel in room.get("lighting", {}).items():
            if unlock_id not in unlock_ids:
                raise ConfigError(f"room.json: освещение для неизвестного предмета {unlock_id}")
            lighting[unlock_id] = _safe(root, rel)
        manifest = SpriteManifest(
            frame=int(character["frame"]),
            bases=bases,
            scene=_ints(room["scene"], 2, "scene"),  # type: ignore[arg-type]
            anchor=_ints(room["character_anchor"], 2, "character_anchor"),  # type: ignore[arg-type]
            floor_y=int(room["floor_y"]),
            compact_crop=_ints(room["compact_crop"], 4, "compact_crop"),  # type: ignore[arg-type]
            background=_safe(root, room["background"]),
            props=props,
            lighting=lighting,
            root=root,
        )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ConfigError(f"спрайты: неверная структура ({exc!r})") from exc
    return manifest


def check_sprite_files(manifest: SpriteManifest) -> list[str]:
    """Проблемы файлов спрайтов (не фатальны: недостающее просто не рисуется)."""
    return [f"{name}: {problem}" for name, path in manifest.all_files() if (problem := png_problem(path))]


def compose_look(manifest: SpriteManifest, base_id: str, stage: int, tiers: Mapping[str, int]) -> Look:
    """Слои персонажа и предметы для (персонаж, стадия, тиры категорий).

    Порядок применения: default, затем стадии 2..stage, затем тиры категорий в порядке `tiers`.
    Слой с тем же slot заменяет прежний; итог сортируется по z (при равных — по порядку добавления).
    """
    base = manifest.bases[base_id]
    chosen: dict[str, Layer] = {}

    def apply(ids: tuple[str, ...]) -> None:
        for layer_id in ids:
            layer = base.layers[layer_id]
            chosen.pop(layer.slot, None)
            chosen[layer.slot] = layer

    apply(base.default)
    for number in range(2, stage + 1):
        apply(base.stages.get(number, ()))
    unlocked: list[str] = []
    for category, tier in tiers.items():
        table = base.tiers.get(category, {})
        for k in range(1, tier + 1):
            apply(table.get(k, ()))
            unlocked.append(f"{category}_{k}")
    props = sorted((manifest.props[u] for u in unlocked if u in manifest.props), key=lambda p: (p.order, p.id))
    return Look(
        character_layers=tuple(sorted(chosen.values(), key=lambda layer: layer.z)),
        props_back=tuple(p for p in props if p.layer == "back"),
        props_front=tuple(p for p in props if p.layer == "front"),
        lighting=tuple(manifest.lighting[u] for u in unlocked if u in manifest.lighting),
        unlocked=frozenset(unlocked),
    )
