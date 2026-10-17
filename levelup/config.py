"""Поставляемая конфигурация: config.json (правила, категории, предметы)."""
from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass
from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
MAX_PNG_SIDE = 2048
MAX_PNG_BYTES = 2 * 1024 * 1024
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_ID_RE = re.compile(r"[a-z][a-z0-9]{0,15}")


class ConfigError(Exception):
    """Поставка повреждена (config.json / character.json / room.json): запуск невозможен."""


@dataclass(frozen=True)
class UnlockConfig:
    id: str
    name: str
    hint: str


@dataclass(frozen=True)
class CategoryConfig:
    id: str
    name: str
    blurb: str
    unlocks: tuple[UnlockConfig, ...]  # по одному на каждый порог category_tiers


@dataclass(frozen=True)
class AppConfig:
    max_active_habits: int
    max_total_habits: int
    title_max_length: int
    xp_per_completion: int
    stage_thresholds: tuple[int, ...]
    stage_names: tuple[str, ...]
    character_bases: tuple[str, ...]
    default_base: str
    category_tiers: tuple[int, ...]
    categories: tuple[CategoryConfig, ...]
    date_poll_seconds: int
    db_busy_timeout_ms: int

    @property
    def stage_count(self) -> int:
        return len(self.stage_thresholds)

    @property
    def category_ids(self) -> tuple[str, ...]:
        return tuple(c.id for c in self.categories)

    def category(self, category_id: str) -> CategoryConfig:
        for item in self.categories:
            if item.id == category_id:
                return item
        raise KeyError(category_id)

    def unlock(self, unlock_id: str) -> tuple[CategoryConfig, UnlockConfig]:
        for item in self.categories:
            for unlock in item.unlocks:
                if unlock.id == unlock_id:
                    return item, unlock
        raise KeyError(unlock_id)


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"{path.name}: не удалось прочитать ({exc})") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name}: ожидался JSON-объект")
    return data


def _increasing_ints(value: object, first_zero: bool, name: str) -> tuple[int, ...]:
    if (
        not isinstance(value, list)
        or len(value) < (2 if first_zero else 1)
        or any(type(t) is not int for t in value)
        or (first_zero and value[0] != 0)
        or (not first_zero and value[0] < 1)
        or any(b <= a for a, b in zip(value, value[1:]))
    ):
        start = "начинающийся с 0" if first_zero else "положительных"
        raise ConfigError(f"config.json: {name} — возрастающий список целых, {start}")
    return tuple(value)


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"config.json: {name} должно быть непустой строкой")
    return value


def _categories(raw: object, tiers: tuple[int, ...]) -> tuple[CategoryConfig, ...]:
    if not isinstance(raw, list) or not raw:
        raise ConfigError("config.json: categories — непустой список")
    result: list[CategoryConfig] = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not _ID_RE.fullmatch(item["id"]):
            raise ConfigError("config.json: у категории должен быть id из латинских букв и цифр")
        cid = item["id"]
        if any(c.id == cid for c in result):
            raise ConfigError(f"config.json: категория {cid} повторяется")
        unlocks_raw = item.get("unlocks")
        if not isinstance(unlocks_raw, list) or len(unlocks_raw) != len(tiers):
            raise ConfigError(f"config.json: у категории {cid} должно быть {len(tiers)} предмета")
        unlocks = []
        for k, u in enumerate(unlocks_raw, start=1):
            if not isinstance(u, dict) or u.get("id") != f"{cid}_{k}":
                raise ConfigError(f"config.json: предмет {k} категории {cid} должен иметь id {cid}_{k}")
            unlocks.append(
                UnlockConfig(u["id"], _text(u.get("name"), f"{cid}_{k}.name"), _text(u.get("hint"), f"{cid}_{k}.hint"))
            )
        result.append(
            CategoryConfig(cid, _text(item.get("name"), f"{cid}.name"), str(item.get("blurb", "")), tuple(unlocks))
        )
    return tuple(result)


def load_config(assets_dir: Path = ASSETS_DIR) -> AppConfig:
    raw = read_json(assets_dir / "config.json")

    def integer(name: str, low: int = 1, high: int | None = None) -> int:
        value = raw.get(name)
        if type(value) is not int or value < low or (high is not None and value > high):
            raise ConfigError(f"config.json: поле {name} должно быть целым числом не меньше {low}")
        return value

    thresholds = _increasing_ints(raw.get("stage_thresholds"), True, "stage_thresholds")
    names = raw.get("stage_names")
    if not isinstance(names, list) or len(names) != len(thresholds):
        raise ConfigError("config.json: stage_names должен содержать по названию на каждую стадию")
    stage_names = tuple(_text(n, "stage_names") for n in names)
    tiers = _increasing_ints(raw.get("category_tiers"), False, "category_tiers")
    bases = raw.get("character_bases")
    if not isinstance(bases, list) or not bases or any(not isinstance(b, str) or not _ID_RE.fullmatch(b) for b in bases):
        raise ConfigError("config.json: character_bases — непустой список идентификаторов")
    default_base = raw.get("default_base")
    if default_base not in bases:
        raise ConfigError("config.json: default_base должен входить в character_bases")
    xp = integer("xp_per_completion")
    if xp != 10:
        raise ConfigError("config.json: правила версии 1 поддерживают только xp_per_completion = 10")
    max_active = integer("max_active_habits")
    max_total = integer("max_total_habits")
    if max_total < max_active:
        raise ConfigError("config.json: max_total_habits не может быть меньше max_active_habits")
    return AppConfig(
        max_active_habits=max_active,
        max_total_habits=max_total,
        title_max_length=integer("title_max_length", 1, 80),
        xp_per_completion=xp,
        stage_thresholds=thresholds,
        stage_names=stage_names,
        character_bases=tuple(bases),
        default_base=default_base,
        category_tiers=tiers,
        categories=_categories(raw.get("categories"), tiers),
        date_poll_seconds=integer("date_poll_seconds"),
        db_busy_timeout_ms=integer("db_busy_timeout_ms"),
    )


def png_problem(path: Path) -> str | None:
    """None, если PNG существует и укладывается в 2048x2048 и 2 МБ; иначе описание проблемы."""
    try:
        size = path.stat().st_size
        with open(path, "rb") as handle:
            head = handle.read(24)
    except OSError:
        return "файл не найден или недоступен"
    if size > MAX_PNG_BYTES:
        return f"файл больше {MAX_PNG_BYTES // (1024 * 1024)} МБ"
    if len(head) < 24 or head[:8] != _PNG_SIGNATURE or head[12:16] != b"IHDR":
        return "это не PNG"
    width, height = struct.unpack(">II", head[16:24])
    if width > MAX_PNG_SIDE or height > MAX_PNG_SIDE:
        return f"размер {width}x{height} больше {MAX_PNG_SIDE}x{MAX_PNG_SIDE}"
    return None
