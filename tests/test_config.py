import json
import shutil

import pytest

from levelup.config import ASSETS_DIR, ConfigError, load_config, png_problem


@pytest.fixture
def assets_copy(tmp_path):
    shutil.copy(ASSETS_DIR / "config.json", tmp_path / "config.json")
    return tmp_path


def edit(path, fn):
    data = json.loads(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_shipped_config_is_valid(config):
    assert config.stage_thresholds == (0, 100, 300, 600, 1000) and config.stage_count == 5
    assert config.stage_names[0] == "Старт" and len(config.stage_names) == 5
    assert (config.max_active_habits, config.max_total_habits, config.xp_per_completion) == (5, 1000, 10)
    assert config.category_ids == ("sport", "work", "study", "social") and config.category_tiers == (3, 7, 15)
    assert config.character_bases == ("m", "w") and config.default_base == "m"
    assert [u.id for u in config.category("work").unlocks] == ["work_1", "work_2", "work_3"]
    assert config.unlock("study_2")[0].id == "study" and config.unlock("study_2")[1].name == "Очки"
    with pytest.raises(KeyError):
        config.category("cooking")


@pytest.mark.parametrize(
    "patch",
    [
        {"xp_per_completion": 20},
        {"stage_thresholds": [0, 100, 100, 600]},
        {"stage_thresholds": [10, 100]},
        {"stage_names": ["Старт"]},
        {"category_tiers": [3, 3, 15]},
        {"category_tiers": []},
        {"character_bases": []},
        {"default_base": "x"},
        {"categories": []},
        {"max_active_habits": 0},
        {"title_max_length": 200},
        {"max_total_habits": 2},
    ],
)
def test_config_rejects_bad_values(assets_copy, patch):
    edit(assets_copy / "config.json", lambda d: d.update(patch))
    with pytest.raises(ConfigError):
        load_config(assets_copy)


def test_config_rejects_inconsistent_unlock_ids(assets_copy):
    edit(assets_copy / "config.json", lambda d: d["categories"][0]["unlocks"][1].update(id="sport_9"))
    with pytest.raises(ConfigError, match="sport_2"):
        load_config(assets_copy)
    shutil.copy(ASSETS_DIR / "config.json", assets_copy / "config.json")
    edit(assets_copy / "config.json", lambda d: d["categories"][1].update(id="sport"))
    with pytest.raises(ConfigError):
        load_config(assets_copy)


def test_png_problem_reports_missing_and_oversized(tmp_path):
    assert "не найден" in png_problem(tmp_path / "nope.png")
    fake = tmp_path / "big.png"
    fake.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (3000).to_bytes(4, "big") + (100).to_bytes(4, "big"))
    assert "3000x100" in png_problem(fake)
    fake.write_bytes(b"not a png at all, just text.....")
    assert png_problem(fake) == "это не PNG"
