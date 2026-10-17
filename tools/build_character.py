"""Собирает слои персонажа (LevelUp v2) из Universal LPC Spritesheet Character Generator.

Результат (`character/`):

* levelup/assets/sprites/character/{m,w}/<layer_id>.png - RGBA 64x64, вид спереди;
* levelup/assets/sprites/character/character.json - слои, стадии, тиры;
* levelup/assets/sprites/character/CREDITS.md - авторы и лицензии использованных предметов LPC.

Источник: https://github.com/LiberatedPixelCup/Universal-LPC-Spritesheet-Character-Generator
(лицензии CC-BY-SA 3.0 / GPL 3.0 / OGA-BY 3.0 / CC0, нужна атрибуция). Каждый PNG - один кадр 64x64
из walk.png (колонка 0, строка 2: стоящая фигура лицом к зрителю), перекрашенный подменой палитры по
индексу цвета (точное совпадение RGB, допуск +-3 на «почти те же» цвета, альфа не трогается), без
масштабирования и перерисовки. Предметы, у которых автор выложил готовые цвета (walk/<цвет>.png),
берутся готовыми.

Запуск:

    python tools/build_character.py <каталог_LPC> [--preview [КАТАЛОГ]] [--out КАТАЛОГ] [--no-fetch]
    LPC_REPO=<каталог_LPC> python tools/build_character.py --preview /tmp/char
    python tools/build_character.py --skip-build --preview /tmp/char     # только превью готовых слоёв

Каталог LPC - клон репозитория (подходит «ленивый»). Скрипт сам докачивает нужные папки через
`git sparse-checkout add`. Если клона нет:

    git clone --filter=blob:none --no-checkout --sparse \\
        https://github.com/LiberatedPixelCup/Universal-LPC-Spritesheet-Character-Generator.git lpc
    git -C lpc sparse-checkout set sheet_definitions palette_definitions && git -C lpc checkout

Использованная версия: коммит 9bf06be193b053db256b2536824af426de046aa2 (октябрь 2026).

Слои и z (z у LPC в скобках, если мы его меняли):
  shadow 0, body 10, feet 15, legs 20, torso 35, jacket 55 (у кардигана LPC 35), wrists 70, neck 90,
  medal 92 (у LPC 81: медаль должна быть поверх галстука, а не под ним), head 100, face 115,
  hair 120, headwear 125. Глаза нарисованы прямо в спрайте головы LPC (перекрашены в карие),
  отдельного слоя `eyes` нет. «Задние» части причёсок (bg) в кадре лицом к зрителю пустые, не нужны.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "levelup" / "assets" / "sprites" / "character"
LPC_URL = "https://github.com/LiberatedPixelCup/Universal-LPC-Spritesheet-Character-Generator"
LPC_COMMIT = "9bf06be193b053db256b2536824af426de046aa2"

FRAME = 64
WALK_COL, WALK_ROW = 0, 2  # walk.png 9x4 кадров по 64 px: колонка 0, строка 2 = стоит лицом к зрителю
TOLERANCE = 3  # допуск по каналу при поиске «почти того же» цвета палитры

PALETTE_FILE = {
    "hair": "hair/hair_ulpc.json",
    "cloth": "cloth/cloth_ulpc.json",
    "body": "body/body_ulpc.json",
    "eye": "eye/eye_ulpc.json",
}
BASE_RAMP = {"hair": "orange", "cloth": "white", "body": "light", "eye": "blue"}

# Свои рампы: по 6 цветов, индексы выровнены с рампами LPC этого материала (0 контур ... 5 блик).
# Нужны там, где стандартные цвета LPC слишком яркие для тёплой приглушённой палитры приложения.
CUSTOM_RAMPS: dict[str, list[str]] = {
    "moss": ["#281820", "#2b4228", "#3b5d36", "#4f7a42", "#659058", "#86ac76"],  # футболка: мох
    "denim": ["#1a1b2e", "#27324f", "#33466f", "#3f5a8a", "#52709f", "#7390bb"],  # приглушённые джинсы
    "sport": ["#2a1a1f", "#5c2a22", "#8d3d28", "#b9532f", "#d0613a", "#e58a5e"],  # цвет категории sport
    "sneaker": ["#281820", "#4D4A5D", "#9c3f23", "#d0613a", "#E5E6C7", "#FFFFFF"],  # белые с акцентом
    "ink": ["#2a211c", "#4D4A5D", "#958080", "#C4B59F", "#E5E6C7", "#FFFFFF"],  # тень под ногами: ink UI
    # волосы (hair_ulpc)
    "chestnut_warm": ["#200C0D", "#3A130E", "#5c2410", "#7a3512", "#a04c1c", "#c06a2c"],
    "chestnut_warm_hi": ["#200C0D", "#3A130E", "#5c2410", "#7a3512", "#b0602a", "#d28a45"],
    "dark_brown_hi": ["#050100", "#160701", "#290E02", "#421603", "#6b2f0e", "#8f4a1c"],
}

# Мужские формальные брюки LPC (legs/formal/male/walk.png) нарисованы тремя зелёными тонами, а не
# рампой white. По числу пикселей и расположению они соответствуют индексам 1, 3 и 4 рампы.
FORMAL_MALE_BASE: list[str | None] = [None, "#182611", None, "#203416", "#314f22", None]

BODY_FOLDER = {"m": "male", "w": "female"}  # {b}
LEGS_FOLDER = {"m": "male", "w": "thin"}  # {l}: ноги, обувь, манжеты у женской фигуры лежат в thin
TITLES = {"m": "Он", "w": "Она"}
CATEGORIES = ("sport", "work", "study", "social")


# ----------------------------------------------------------------------------------------------
# Описание слоёв
# ----------------------------------------------------------------------------------------------
class Per:
    """Значение, разное для m и w."""

    def __init__(self, m: Any, w: Any) -> None:
        self.v = {"m": m, "w": w}


def pick(value: Any, base: str) -> Any:
    return value.v[base] if isinstance(value, Per) else value


def R(material: str, to: str | list[str], base: list[str | None] | None = None,
      stray: dict[tuple[int, int, int], int] | None = None) -> dict[str, Any]:
    """Подмена палитры: material - hair|cloth|body|eye, to - имя рампы LPC/своей или список из 6 цветов,
    base - своя исходная рампа (если спрайт нарисован не базовой), stray - {rgb: индекс} для одиночных
    «лишних» цветов."""
    return {"material": material, "to": to, "base": base, "stray": stray or {}}


@dataclass
class Item:
    id: str
    slot: str
    z: int
    src: Any  # папка предмета относительно spritesheets/; {b} -> male|female, {l} -> male|thin
    variant: Any = None  # готовый цвет автора: walk/<variant>.png вместо walk.png
    ops: Any = ()  # перекраски (список R) для walk.png
    back: Any = None  # папка «задней» части причёски: в кадре спереди должна быть пустой


SKIN = "light"
EYES = "brown"
HAIR_M, HAIR_M5 = "dark_brown", "dark_brown_hi"
HAIR_W, HAIR_W5 = "chestnut_warm", "chestnut_warm_hi"
WAVY_STRAY = {(75, 75, 75): 2}  # единственный серый пиксель в hair/wavy fg: делаем тоном 2 рампы

ITEMS: list[Item] = [
    Item("shadow", "shadow", 0, "shadow/adult", ops=[R("cloth", "ink")]),
    Item("body", "body", 10, "body/bodies/{b}", ops=[R("body", SKIN)]),
    Item("head", "head", 100, "head/heads/human/{b}", ops=[R("body", SKIN), R("eye", EYES)]),
    # --- причёски: стадии 1..5 (m: тёмно-каштановые, w: каштановые; на стадии 5 светлее блик) ---
    Item("hair_1", "hair", 120, Per("hair/messy1/adult", "hair/bedhead/adult"),
         ops=Per([R("hair", HAIR_M)], [R("hair", HAIR_W)])),
    Item("hair_2", "hair", 120, Per("hair/bedhead/adult", "hair/bob/adult"),
         ops=Per([R("hair", HAIR_M)], [R("hair", HAIR_W)])),
    Item("hair_3", "hair", 120, Per("hair/parted/adult", "hair/wavy/adult/fg"),
         back=Per(None, "hair/wavy/adult/bg"),
         ops=Per([R("hair", HAIR_M)], [R("hair", HAIR_W, stray=WAVY_STRAY)])),
    Item("hair_4", "hair", 120, Per("hair/cowlick/adult", "hair/bangs_bun/adult"),
         ops=Per([R("hair", HAIR_M)], [R("hair", HAIR_W)])),
    Item("hair_5", "hair", 120, Per("hair/cowlick_tall/adult", "hair/princess/adult/fg"),
         back=Per(None, "hair/princess/adult/bg"),
         ops=Per([R("hair", HAIR_M5)], [R("hair", HAIR_W5)])),
    # --- повседневная одежда (default) ---
    Item("tee", "torso", 35, "torso/clothes/shortsleeve/tshirt/{b}",
         ops=Per([R("cloth", "moss")], [R("cloth", "bluegray")])),
    Item("jeans", "legs", 20, "legs/pants/{l}", ops=[R("cloth", "denim")]),
    Item("shoes", "feet", 15, "feet/shoes/basic/{l}", ops=[R("cloth", "brown")]),
    # --- sport ---
    Item("sneakers", "feet", 15, "feet/shoes/sara/{l}", ops=[R("cloth", "sneaker")]),
    Item("headband", "headwear", 125, "hat/headband/thick/adult", ops=[R("cloth", "sport")]),
    Item("wristbands", "wrists", 70, "arms/wrists/cuffs/{l}", ops=[R("cloth", "sneaker")]),
    Item("medal", "medal", 92, "neck/charm/ring/{b}", variant="gold"),
    # --- work ---
    Item("shirt", "torso", 35, Per("torso/clothes/longsleeve/formal/male", "torso/clothes/blouse_longsleeve/female"),
         variant="white"),
    Item("blazer", "jacket", 55, Per("torso/jacket/collared/male",
                                      "torso/clothes/longsleeve/longsleeve2_cardigan/female"),
         variant=Per("charcoal", None), ops=Per([], [R("cloth", "charcoal")])),
    Item("tie", "neck", 90, "neck/tie/necktie/{b}", ops=[R("cloth", "maroon")]),
    Item("trousers", "legs", 20, "legs/formal/{l}",
         ops=Per([R("cloth", "charcoal", base=FORMAL_MALE_BASE)], [R("cloth", "charcoal")])),
    Item("dress_shoes", "feet", 15, "feet/shoes/revised/{l}", ops=[R("cloth", "black")]),
    # --- study ---
    Item("glasses", "face", 115, "facial/glasses/round/adult", variant="black"),
]

DEFAULT = ["shadow", "body", "head", "hair_1", "tee", "jeans", "shoes"]
STAGES = {2: ["hair_2"], 3: ["hair_3"], 4: ["hair_4"], 5: ["hair_5"]}
TIERS = {
    "sport": {1: [], 2: ["sneakers", "headband"], 3: ["medal", "wristbands"]},
    "work": {1: [], 2: ["shirt", "blazer"], 3: ["tie", "trousers", "dress_shoes"]},
    "study": {1: [], 2: ["glasses"], 3: []},
    "social": {1: [], 2: [], 3: []},
}

LICENSE_URLS = {
    "CC0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "CC-BY 3.0+": "https://creativecommons.org/licenses/by/3.0/",
    "CC-BY-SA 3.0": "https://creativecommons.org/licenses/by-sa/3.0/",
    "OGA-BY 3.0": "https://opengameart.org/content/oga-by-30-faq",
    "OGA-BY 3.0+": "https://opengameart.org/content/oga-by-30-faq",
    "GPL 3.0": "https://www.gnu.org/licenses/gpl-3.0.html",
    "GPL 2.0": "https://www.gnu.org/licenses/old-licenses/gpl-2.0.html",
}
# что берём из предложенных лицензий предмета: самую мягкую из доступных (предметы LPC мультилицензионные)
LICENSE_PREFERENCE = ["CC0", "OGA-BY 3.0", "OGA-BY 3.0+", "CC-BY 3.0+", "CC-BY-SA 3.0", "GPL 3.0", "GPL 2.0"]


def item_dir(item: Item, base: str) -> str:
    return pick(item.src, base).format(b=BODY_FOLDER[base], l=LEGS_FOLDER[base])


def back_dir(item: Item, base: str) -> str | None:
    folder = pick(item.back, base)
    return folder.format(b=BODY_FOLDER[base], l=LEGS_FOLDER[base]) if folder else None


# ----------------------------------------------------------------------------------------------
# Репозиторий LPC
# ----------------------------------------------------------------------------------------------
def needed_dirs() -> list[str]:
    dirs: set[str] = set()
    for item in ITEMS:
        for base in BODY_FOLDER:
            dirs.add("spritesheets/" + item_dir(item, base))
            back = back_dir(item, base)
            if back:
                dirs.add("spritesheets/" + back)
    return sorted(dirs)


def ensure_checkout(repo: Path, fetch: bool) -> None:
    """Докачивает недостающие папки (sparse-checkout) и проверяет, что всё на месте."""
    wanted = ["sheet_definitions", "palette_definitions"] + needed_dirs()
    missing = [d for d in wanted if not (repo / d).is_dir()]
    if missing and fetch and (repo / ".git").exists():
        print(f"git sparse-checkout add: {len(missing)} папок")
        subprocess.run(["git", "-C", str(repo), "sparse-checkout", "add", *missing], check=True)
        missing = [d for d in wanted if not (repo / d).is_dir()]
    if missing:
        sys.exit("нет папок LPC: " + ", ".join(missing[:6]) + (" ..." if len(missing) > 6 else "") +
                 f"\nСклонируйте {LPC_URL} (см. docstring) и передайте путь аргументом или в LPC_REPO.")


def git_commit(repo: Path) -> str:
    try:
        return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True,
                              text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return LPC_COMMIT


# ----------------------------------------------------------------------------------------------
# Пиксели
# ----------------------------------------------------------------------------------------------
def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


class Ramps:
    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self._cache: dict[str, dict[str, list[str]]] = {}

    def lpc(self, material: str, name: str) -> list[str]:
        if material not in self._cache:
            with open(self.repo / "palette_definitions" / PALETTE_FILE[material], encoding="utf-8") as handle:
                self._cache[material] = json.load(handle)
        return self._cache[material][name]

    def resolve(self, material: str, spec: str | list[str | None] | None) -> list[tuple[int, int, int] | None]:
        if spec is None:
            spec = BASE_RAMP[material]
        if isinstance(spec, str):
            spec = CUSTOM_RAMPS[spec] if spec in CUSTOM_RAMPS else self.lpc(material, spec)
        return [hex_rgb(c) if c else None for c in spec]


def recolor(img: Image.Image, ramps: Ramps, ops: list[dict[str, Any]]) -> int:
    """Подменяет цвета базовых рамп на целевые по индексу (все ops - за один проход по исходным
    цветам: у головы это кожа и глаза). Возвращает число непрозрачных пикселей, которые не нашли
    пары ни в одной рампе (остаются как есть)."""
    tables = []
    for op in ops:
        src = ramps.resolve(op["material"], op["base"])
        dst = ramps.resolve(op["material"], op["to"])
        assert len(src) == len(dst), (op["material"], op["to"])
        tables.append(([(s, d) for s, d in zip(src, dst) if s is not None],
                       {rgb: dst[i] for rgb, i in op["stray"].items()}))
    px = img.load()
    unmatched = 0
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = px[x, y]
            if not a:
                continue
            new = None
            for pairs, stray in tables:  # сначала точное совпадение, потом допуск
                new = stray.get((r, g, b)) or next((d for s, d in pairs if s == (r, g, b)), None)
                if new:
                    break
            for pairs, _ in tables if new is None else ():
                new = next((d for s, d in pairs if max(abs(s[0] - r), abs(s[1] - g), abs(s[2] - b)) <= TOLERANCE), None)
                if new:
                    break
            if new is None:
                unmatched += a == 255
            else:
                px[x, y] = (*new, a)
    return unmatched


def walk_front(repo: Path, folder: str, variant: str | None = None) -> Image.Image:
    path = repo / "spritesheets" / folder
    path = path / "walk" / f"{variant}.png" if variant else path / "walk.png"
    sheet = Image.open(path).convert("RGBA")
    assert sheet.size == (9 * FRAME, 4 * FRAME), (path, sheet.size)
    x, y = WALK_COL * FRAME, WALK_ROW * FRAME
    return sheet.crop((x, y, x + FRAME, y + FRAME))


def render_item(repo: Path, ramps: Ramps, item: Item, base: str, log: list[str]) -> Image.Image:
    folder = item_dir(item, base)
    variant = pick(item.variant, base)
    img = walk_front(repo, folder, variant)
    ops = [] if variant else pick(item.ops, base)
    left = recolor(img, ramps, ops) if ops else 0
    if left:
        log.append(f"  {base}/{item.id}: {left} непрозрачных пикс. вне рамп (оставлены как есть)")
    back = back_dir(item, base)
    if back and walk_front(repo, back).getbbox() is not None:
        raise SystemExit(f"{base}/{item.id}: задняя часть {back} не пуста в кадре спереди, нужен отдельный слой")
    return img


# ----------------------------------------------------------------------------------------------
# character.json
# ----------------------------------------------------------------------------------------------
def build_manifest() -> dict[str, Any]:
    bases: dict[str, Any] = {}
    for base in BODY_FOLDER:
        bases[base] = {
            "title": TITLES[base],
            "layers": {item.id: {"file": f"{base}/{item.id}.png", "z": item.z, "slot": item.slot} for item in ITEMS},
            "default": list(DEFAULT),
            "stages": {str(s): list(ids) for s, ids in STAGES.items()},
            "tiers": {cat: {str(k): list(ids) for k, ids in TIERS[cat].items()} for cat in CATEGORIES},
        }
    return {"frame": FRAME, "bases": bases}


def validate(out: Path, manifest: dict[str, Any]) -> list[str]:
    """Проверки контракта: файлы, размеры, ключи, слои без касания границ кадра."""
    problems: list[str] = []
    assert manifest["frame"] == FRAME
    for base_id, base in manifest["bases"].items():
        layers = base["layers"]
        for layer_id, layer in layers.items():
            path = out / layer["file"]
            if not path.is_file():
                problems.append(f"{base_id}/{layer_id}: нет файла")
                continue
            img = Image.open(path)
            if img.size != (FRAME, FRAME) or img.mode != "RGBA":
                problems.append(f"{base_id}/{layer_id}: {img.size} {img.mode}, нужно {FRAME}x{FRAME} RGBA")
                continue
            box = img.getbbox()
            if box is None:
                problems.append(f"{base_id}/{layer_id}: пустой слой")
            elif layer["slot"] != "shadow" and (box[0] == 0 or box[1] == 0 or box[2] == FRAME or box[3] == FRAME):
                problems.append(f"{base_id}/{layer_id}: касается границы кадра {box} (обрезка?)")
        refs = list(base["default"]) + [i for ids in base["stages"].values() for i in ids] + \
            [i for cat in base["tiers"].values() for ids in cat.values() for i in ids]
        problems += [f"{base_id}: неизвестный слой {i}" for i in refs if i not in layers]
        if sorted(base["stages"]) != ["2", "3", "4", "5"]:
            problems.append(f"{base_id}: стадии {sorted(base['stages'])}")
        for cat in CATEGORIES:
            if sorted(base["tiers"][cat]) != ["1", "2", "3"]:
                problems.append(f"{base_id}: tiers.{cat} {sorted(base['tiers'][cat])}")
        slots = [layers[i]["slot"] for i in base["default"]]
        if len(slots) != len(set(slots)):
            problems.append(f"{base_id}: в default два слоя с одним slot")
    return problems


# ----------------------------------------------------------------------------------------------
# CREDITS.md
# ----------------------------------------------------------------------------------------------
def index_definitions(repo: Path) -> dict[str, tuple[str, dict[str, Any]]]:
    """{папка спрайтов (без / на конце): (путь определения, определение)}"""
    index: dict[str, tuple[str, dict[str, Any]]] = {}
    root = repo / "sheet_definitions"
    for path in sorted(root.rglob("*.json")):
        if path.name.startswith("meta_"):
            continue
        with open(path, encoding="utf-8") as handle:
            definition = json.load(handle)
        for key, layer in definition.items():
            if key.startswith("layer_") and isinstance(layer, dict):
                for value in layer.values():
                    if isinstance(value, str):
                        index.setdefault(value.rstrip("/"), (str(path.relative_to(root)), definition))
    return index


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(v for v in values if v))


def layer_labels(ids: list[str], code: bool = False) -> list[str]:
    """['m/tee', 'w/tee', 'm/hair_2'] -> ['tee', 'hair_2 (m)']: пометка базы, если слой есть только у одной."""
    bases: dict[str, list[str]] = {}
    for full in _dedupe(ids):
        base, layer = full.split("/")
        bases.setdefault(layer, []).append(base)
    quote = "`" if code else ""
    return [f"{quote}{layer}{quote}" if len(b) == len(BODY_FOLDER) else f"{quote}{layer}{quote} ({'/'.join(b)})"
            for layer, b in bases.items()]


def credits_markdown(repo: Path) -> str:
    index = index_definitions(repo)
    used: dict[str, dict[str, Any]] = {}  # путь определения -> данные
    for item in ITEMS:
        for base in BODY_FOLDER:
            for folder in filter(None, (item_dir(item, base), back_dir(item, base))):
                if folder not in index:
                    raise SystemExit(f"нет определения листа для {folder}")
                rel, definition = index[folder]
                entry = used.setdefault(rel, {"definition": definition, "folders": [], "ids": []})
                entry["folders"].append(folder)
                entry["ids"].append(f"{base}/{item.id}")
    sections: list[str] = []
    table: list[str] = []
    share_alike: list[str] = []
    for rel, entry in sorted(used.items(), key=lambda kv: kv[1]["definition"].get("name", kv[0]).lower()):
        definition = entry["definition"]
        folders = _dedupe(entry["folders"])
        matched = [c for c in definition.get("credits", [])
                   if any(f == c["file"] or f.startswith(c["file"].rstrip("/") + "/") for f in folders)]
        matched = matched or list(definition.get("credits", []))
        authors = _dedupe([a for c in matched for a in c.get("authors", [])])
        licenses = _dedupe([l for c in matched for l in c.get("licenses", [])])
        urls = _dedupe([u for c in matched for u in c.get("urls", [])])
        notes = _dedupe([c.get("notes", "").strip() for c in matched])
        applied = next((l for l in LICENSE_PREFERENCE if l in licenses), licenses[0] if licenses else "?")
        name = definition.get("name", rel)
        if applied in ("CC-BY-SA 3.0", "GPL 3.0", "GPL 2.0"):
            share_alike.append(name)
        table.append(f"| {name} | {', '.join(layer_labels(entry['ids']))} | {', '.join(licenses)} | {applied} |")
        sections.append(
            "\n".join([
                f"### {name}",
                f"- Used as layers: {', '.join(layer_labels(entry['ids'], code=True))}",
                f"- LPC sheet definition: `sheet_definitions/{rel}`; sprite folders: "
                f"{', '.join(f'`{f}`' for f in folders)}",
                f"- Authors: {', '.join(authors)}",
                f"- Licenses offered: {', '.join(licenses)}; applied here: {applied}",
                f"- Sources: {', '.join(urls)}",
            ] + ([f"- Notes: {'; '.join(n for n in notes if n)}"] if any(notes) else []))
        )
    head = f"""# Credits and licenses: character sprites

Everything in `m/` and `w/` is derived from the **Universal LPC Spritesheet Character Generator**
({LPC_URL},
commit `{git_commit(repo)}`): the artwork of the Liberated Pixel Cup (LPC) community.
Each PNG is a single 64x64 frame (walk animation, standing, facing the viewer) cut out of an LPC
spritesheet and recolored by swapping palette entries. Nothing was scaled or redrawn. Layers are
produced by `tools/build_character.py`; the list of items below is generated from the `credits`
entries of the LPC sheet definitions.

## License summary

LPC items are multi-licensed: for each item you may choose any of the licenses it offers.

- **Attribution is mandatory** for every item except CC0. Keep this file with the sprites, show the
  authors (or a link to this file) in the app's credits/about screen, link the licenses, and state
  that the images were changed (cropped to one frame and recolored).
- **Share-alike** (CC-BY-SA 3.0 and GPL 3.0): if you redistribute these PNGs, or a modified/composed
  version of them, you must license them under the same license (CC-BY-SA 3.0 or GPL 3.0) and keep the
  attribution. Items that only offer CC-BY-SA / GPL are the ones this applies to: {', '.join(share_alike) or 'none'}.
  The licenses cover the artwork, not the application code that loads the PNGs.
- **OGA-BY 3.0 / CC-BY 3.0+**: attribution only, no share-alike. **CC0**: no conditions, credit is courtesy.
- Practical rule for redistribution: ship the whole `character/` folder under **CC-BY-SA 3.0** with this
  file; that satisfies every item below. (This is a summary, not legal advice.)

License texts: {', '.join(f'[{k}]({v})' for k, v in LICENSE_URLS.items() if k in ('CC-BY-SA 3.0', 'OGA-BY 3.0', 'GPL 3.0', 'CC0', 'CC-BY 3.0+'))}.

Our own changes: choice of items, recolors (the custom palettes are defined in `tools/build_character.py`),
crop to the 64x64 standing frame, splitting into layers, `character.json`.

## Items at a glance

| LPC item | Our layer ids | Licenses offered | Applied |
|---|---|---|---|
"""
    return head + "\n".join(table) + "\n\n## Details\n\n" + "\n\n".join(sections) + "\n"


# ----------------------------------------------------------------------------------------------
# Превью: правило сборки слоёв
# ----------------------------------------------------------------------------------------------
def resolve_layers(manifest: dict[str, Any], base_id: str, stage: int, tiers: dict[str, int]) -> list[str]:
    """default -> стадии 2..stage -> тиры sport, work, study, social; тот же slot заменяет слой;
    сортировка по z (при равных - по порядку добавления)."""
    base = manifest["bases"][base_id]
    layers = base["layers"]
    chosen: dict[str, str] = {}

    def apply(ids: list[str]) -> None:
        for layer_id in ids:
            slot = layers[layer_id]["slot"]
            chosen.pop(slot, None)
            chosen[slot] = layer_id

    apply(base["default"])
    for number in range(2, stage + 1):
        apply(base["stages"].get(str(number), []))
    for cat in CATEGORIES:
        for k in range(1, tiers.get(cat, 0) + 1):
            apply(base["tiers"][cat][str(k)])
    return sorted(chosen.values(), key=lambda layer_id: layers[layer_id]["z"])


def compose(out: Path, manifest: dict[str, Any], base_id: str, stage: int, tiers: dict[str, int]) -> Image.Image:
    canvas = Image.new("RGBA", (FRAME, FRAME))
    for layer_id in resolve_layers(manifest, base_id, stage, tiers):
        canvas.alpha_composite(Image.open(out / manifest["bases"][base_id]["layers"][layer_id]["file"]).convert("RGBA"))
    return canvas


def preview(out: Path, target: Path) -> None:
    """Контактные листы: на каждого персонажа три ряда по x4 на нейтральном фоне:
    1) стадии 1..5 без предметов; 2) комбинации; 3) каждая причёска со sport 2 + study 2
    (повязка и очки поверх всех причёсок)."""
    with open(out / "character.json", encoding="utf-8") as handle:
        manifest = json.load(handle)
    target.mkdir(parents=True, exist_ok=True)
    scale, crop, pad, head = 4, (8, 4, 56, 64), 6, 14
    bg = (230, 220, 195)
    tw, th = (crop[2] - crop[0]) * scale, (crop[3] - crop[1]) * scale
    t = lambda **kw: {c: kw.get(c, 0) for c in CATEGORIES}  # noqa: E731
    sheets = []
    for base_id in manifest["bases"]:
        rows = [
            [(f"stage {s}", compose(out, manifest, base_id, s, t())) for s in range(1, 6)],
            [("sport3 + work3 (st.3)", compose(out, manifest, base_id, 3, t(sport=3, work=3))),
             ("work3 + study2 (st.3)", compose(out, manifest, base_id, 3, t(work=3, study=2))),
             ("everything (st.5)", compose(out, manifest, base_id, 5, t(sport=3, work=3, study=3, social=3))),
             ("nothing (st.1)", compose(out, manifest, base_id, 1, t())),
             ("work2 + sport2 (st.2)", compose(out, manifest, base_id, 2, t(work=2, sport=2)))],
            [(f"st.{s} sport2+study2", compose(out, manifest, base_id, s, t(sport=2, study=2))) for s in range(1, 6)],
        ]
        sheet = Image.new("RGB", (5 * (tw + pad) + pad, len(rows) * (th + head + pad) + pad), bg)
        draw = ImageDraw.Draw(sheet)
        for r, row in enumerate(rows):
            for c, (label, img) in enumerate(row):
                x, y = pad + c * (tw + pad), pad + r * (th + head + pad)
                tile = Image.new("RGBA", (tw, th), (*bg, 255))
                tile.alpha_composite(img.crop(crop).resize((tw, th), Image.NEAREST))
                sheet.paste(tile.convert("RGB"), (x, y + head))
                draw.text((x + 1, y + 1), f"{base_id}: {label}", fill=(42, 33, 28))
        sheet.save(target / f"preview_{base_id}.png")
        sheets.append(sheet)
    contact = Image.new("RGB", (sheets[0].width, sum(s.height for s in sheets)), bg)
    y = 0
    for sheet in sheets:
        contact.paste(sheet, (0, y))
        y += sheet.height
    contact.save(target / "contact_sheet.png")
    print(f"превью: {target}/preview_m.png, preview_w.png, contact_sheet.png")


# ----------------------------------------------------------------------------------------------
def build(repo: Path, out: Path, fetch: bool) -> None:
    ensure_checkout(repo, fetch)
    ramps = Ramps(repo)
    log: list[str] = []
    for base in BODY_FOLDER:
        (out / base).mkdir(parents=True, exist_ok=True)
        for item in ITEMS:
            img = render_item(repo, ramps, item, base, log)
            img.save(out / base / f"{item.id}.png", optimize=True)
    with open(out / "character.json", "w", encoding="utf-8", newline="\n") as handle:
        json.dump(build_manifest(), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    (out / "CREDITS.md").write_text(credits_markdown(repo), encoding="utf-8", newline="\n")
    print("\n".join(log) or "все пиксели нашли пару в рампах")
    problems = validate(out, build_manifest())
    if problems:
        sys.exit("проблемы:\n" + "\n".join(problems))
    print(f"готово: {len(ITEMS)} слоёв x {len(BODY_FOLDER)} персонажей -> {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("repo", nargs="?", help="клон Universal LPC Spritesheet Character Generator (или LPC_REPO)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="куда писать (по умолчанию каталог ресурсов)")
    parser.add_argument("--preview", nargs="?", const=Path(tempfile.gettempdir()) / "levelup_character_preview",
                        type=Path, metavar="КАТАЛОГ", help="после сборки записать контактные листы")
    parser.add_argument("--skip-build", action="store_true", help="не пересобирать, только превью готовых слоёв")
    parser.add_argument("--no-fetch", action="store_true", help="не запускать git sparse-checkout add")
    args = parser.parse_args()
    if not args.skip_build:
        repo_arg = args.repo or os.environ.get("LPC_REPO")
        if not repo_arg:
            parser.error("укажите каталог LPC аргументом или в LPC_REPO")
        build(Path(repo_arg).expanduser().resolve(), args.out, not args.no_fetch)
    if args.preview:
        preview(args.out, args.preview)


if __name__ == "__main__":
    main()
