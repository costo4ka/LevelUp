"""Создаёт ТЕСТОВУЮ папку данных с готовой историей, чтобы сразу посмотреть стадии и предметы.

    .venv/bin/python tools/make_demo.py /tmp/levelup-demo --base w --days 8
    LEVELUP_DATA_DIR=/tmp/levelup-demo .venv/bin/python -m levelup

По одной привычке на категорию (или только на перечисленные в --habits), для каждой отмечены все
прошедшие дни, сегодняшний день свободен. Примерно: 3 дня — первый предмет, 7 — второй, 15 — третий
(по одной привычке на категорию); стадии: 10 дней при 4 привычках ≈ 400 очков. Папку, в которой уже
есть данные, и каталоги настоящих данных скрипт не трогает.
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from levelup.application.service import AppService  # noqa: E402
from levelup.config import load_config  # noqa: E402
from levelup.domain.clock import SystemClock  # noqa: E402
from levelup.infrastructure.db import open_database  # noqa: E402
from levelup.infrastructure.paths import AppPaths  # noqa: E402
from levelup.infrastructure.repository import Repository  # noqa: E402
from levelup.infrastructure.tz import detect_timezone  # noqa: E402

TITLES = {
    "sport": "Зарядка 10 минут",
    "work": "Одна важная рабочая задача",
    "study": "Читать 20 минут",
    "social": "Написать близким",
}


def real_data_dirs() -> list[Path]:
    dirs = [Path.home() / ".local" / "share" / "LevelUp"]
    if os.environ.get("LOCALAPPDATA"):
        dirs.append(Path(os.environ["LOCALAPPDATA"]) / "LevelUp")
    return [d.resolve() for d in dirs]


def main() -> int:
    config = load_config()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("directory")
    parser.add_argument("--base", choices=config.character_bases, default=config.default_base)
    parser.add_argument("--days", type=int, default=0, help="сколько прошедших дней заполнить (по умолчанию 0)")
    parser.add_argument("--habits", default=",".join(config.category_ids), help="категории привычек через запятую")
    args = parser.parse_args()
    root = Path(args.directory).resolve()
    kinds = [k for k in args.habits.split(",") if k]
    if root in real_data_dirs():
        print("Отказ: это каталог настоящих данных LevelUp. Укажите новую тестовую папку.")
        return 2
    if (root / "data.db").exists():
        print(f"Отказ: в {root} уже есть данные. Укажите новую папку или удалите эту.")
        return 2
    if not kinds or any(k not in config.category_ids for k in kinds) or not 0 <= args.days <= 3000:
        print(f"Нужны категории из {', '.join(config.category_ids)} и 0 <= --days <= 3000.")
        return 2

    paths = AppPaths.for_dir(root)
    paths.ensure()
    conn = open_database(paths, config.db_busy_timeout_ms)
    service = AppService(Repository(conn), SystemClock(), config)
    tz = detect_timezone() or "UTC"
    first = service.finish_onboarding(tz, TITLES[kinds[0]], kinds[0], args.base)
    if not first.ok:
        print(first.error.message)
        return 1
    for kind in kinds[1:]:
        result = service.create_habit(TITLES[kind], kind)
        if not result.ok:
            print(result.error.message)
            return 1
    repo = service.repo
    today = datetime.now(timezone.utc).astimezone(ZoneInfo(tz)).date()
    start = today - timedelta(days=args.days)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    habits = repo.active_habits()
    with repo.transaction():
        for habit in habits:
            conn.execute("UPDATE habit SET start_date = ? WHERE id = ?", (start.isoformat(), habit.id))
            for offset in range(args.days):
                repo.insert_completion(habit.id, start + timedelta(days=offset), stamp, config.xp_per_completion)
    snap = service.get_snapshot().data
    conn.close()
    tiers = ", ".join(f"{c['id']} {c['points']} (тир {c['tier']})" for c in snap["categories"])
    print(f"Готово: {root}\nСтадия {snap['stage']} из {snap['stage_count']} «{snap['stage_name']}», очков {snap['total_xp']}, серия {snap['streak_days']}.\n{tiers}")
    print(f"Запуск: LEVELUP_DATA_DIR={root} .venv/bin/python -m levelup")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
