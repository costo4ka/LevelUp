"""Сборка внешнего вида: правила слоёв на синтетическом манифесте и проверка поставляемых спрайтов."""
import json
import struct

import pytest

from levelup.config import ASSETS_DIR, ConfigError
from levelup.look import check_sprite_files, compose_look, load_sprites


def layer(file, z, slot):
    return {"file": file, "z": z, "slot": slot}


@pytest.fixture
def sprites_dir(tmp_path, config):
    char = tmp_path / "sprites" / "character"
    room = tmp_path / "sprites" / "room"
    char.mkdir(parents=True)
    room.mkdir(parents=True)
    tiers = {c.id: {"1": [], "2": [], "3": []} for c in config.categories}
    tiers["sport"]["2"] = ["sneakers"]
    tiers["work"]["2"] = ["blazer"]
    tiers["work"]["3"] = ["formal_shoes", "tie"]
    base = {
        "title": "Он",
        "layers": {
            "body": layer("m/body.png", 10, "body"),
            "tee": layer("m/tee.png", 35, "torso"),
            "blazer": layer("m/blazer.png", 60, "jacket"),
            "tie": layer("m/tie.png", 45, "neck"),
            "shoes": layer("m/shoes.png", 15, "feet"),
            "sneakers": layer("m/sneakers.png", 15, "feet"),
            "formal_shoes": layer("m/formal.png", 15, "feet"),
            "hair_1": layer("m/h1.png", 120, "hair"),
            "hair_2": layer("m/h2.png", 120, "hair"),
        },
        "default": ["body", "shoes", "tee", "hair_1"],
        "stages": {"2": ["hair_2"]},
        "tiers": tiers,
    }
    (char / "character.json").write_text(json.dumps({"frame": 64, "bases": {"m": base, "w": base}}), encoding="utf-8")
    props = {
        "sport_1": {"file": "room/props/sport_1.png", "layer": "front", "order": 5},
        "work_1": {"file": "room/props/work_1.png", "layer": "back", "order": 20},
        "study_3": {"file": "room/props/study_3.png", "layer": "back", "order": 10},
    }
    room_json = {
        "scene": [192, 128], "character_anchor": [64, 56], "floor_y": 96, "compact_crop": [32, 32, 128, 96],
        "background": "room/background.png", "props": props, "lighting": {"social_3": "room/lighting_warm.png"},
    }
    (room / "room.json").write_text(json.dumps(room_json), encoding="utf-8")
    return tmp_path


def ids(look):
    return [item.id for item in look.character_layers]


def test_default_look_and_stage_replaces_hair(sprites_dir, config):
    manifest = load_sprites(config, sprites_dir)
    zero = {c: 0 for c in config.category_ids}
    assert ids(compose_look(manifest, "m", 1, zero)) == ["body", "shoes", "tee", "hair_1"]  # по возрастанию z
    assert ids(compose_look(manifest, "m", 5, zero)) == ["body", "shoes", "tee", "hair_2"]  # слот hair заменён


def test_tiers_replace_slots_in_category_order(sprites_dir, config):
    manifest = load_sprites(config, sprites_dir)
    tiers = {"sport": 2, "work": 2, "study": 0, "social": 0}
    assert ids(compose_look(manifest, "m", 1, tiers)) == ["body", "sneakers", "tee", "blazer", "hair_1"]
    both = compose_look(manifest, "m", 1, {"sport": 2, "work": 3, "study": 0, "social": 0})
    assert "formal_shoes" in ids(both) and "sneakers" not in ids(both)  # деловые туфли заменили кроссовки
    assert ids(both).index("tie") < ids(both).index("blazer")  # по z


def test_props_split_by_layer_and_sorted_and_lighting(sprites_dir, config):
    manifest = load_sprites(config, sprites_dir)
    look = compose_look(manifest, "m", 1, {"sport": 1, "work": 1, "study": 3, "social": 3})
    assert [p.id for p in look.props_back] == ["study_3", "work_1"]  # по order
    assert [p.id for p in look.props_front] == ["sport_1"]
    assert [p.name for p in look.lighting] == ["lighting_warm.png"]
    assert {"study_1", "study_2", "study_3", "social_3"} <= look.unlocked
    none = compose_look(manifest, "m", 1, {c: 0 for c in config.category_ids})
    assert none.props_back == none.props_front == () and none.lighting == () and none.unlocked == frozenset()


def test_loader_rejects_broken_manifests(sprites_dir, config):
    path = sprites_dir / "sprites" / "character" / "character.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["bases"]["m"]["default"].append("ghost")
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ConfigError, match="неизвестный слой"):
        load_sprites(config, sprites_dir)
    data["bases"]["m"]["default"].pop()
    data["bases"]["m"]["layers"]["body"]["file"] = "../../evil.png"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ConfigError, match="за каталог"):
        load_sprites(config, sprites_dir)


def png_size(path):
    head = path.read_bytes()[:24]
    return struct.unpack(">II", head[16:24])


def test_shipped_sprites_are_complete_and_consistent(config):
    manifest = load_sprites(config)
    assert check_sprite_files(manifest) == []
    assert manifest.scene == (192, 128) and manifest.frame == 64
    assert png_size(manifest.background) == manifest.scene
    for prop in manifest.props.values():
        assert png_size(prop.file) == manifest.scene, prop.id
    for path in manifest.lighting.values():
        assert png_size(path) == manifest.scene
    x, y, w, h = manifest.compact_crop
    assert 0 <= x and 0 <= y and x + w <= 192 and y + h <= 128
    for base in manifest.bases.values():
        for item in base.layers.values():
            assert png_size(item.file) == (64, 64), (base.id, item.id)
        # каждый предмет каталога что-то меняет (предмет комнаты, свет или слой персонажа)
        for category in config.categories:
            for k, unlock in enumerate(category.unlocks, start=1):
                visible = unlock.id in manifest.props or unlock.id in manifest.lighting or base.tiers[category.id][k]
                assert visible, (base.id, unlock.id)
        # стадии 2..N меняют причёску
        for stage in range(2, config.stage_count + 1):
            assert base.stages.get(stage), (base.id, stage)
    for category in config.categories:
        for unlock in category.unlocks:
            assert (ASSETS_DIR / "sprites" / "icons" / f"unlock_{unlock.id}.png").exists(), unlock.id
        assert (ASSETS_DIR / "sprites" / "icons" / f"cat_{category.id}.png").exists()
