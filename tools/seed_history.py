"""Докидывает историю отметок в ТЕСТОВУЮ папку данных, чтобы быстро увидеть следующие стадии.

Использование (приложение должно быть закрыто):
    LEVELUP_DATA_DIR=/tmp/levelup-test .venv/bin/python -m levelup     # пройти онбординг и выйти
    .venv/bin/python tools/seed_history.py /tmp/levelup-test 30        # +30 прошедших дней по всем активным привычкам (очки идут в категории привычек)
    LEVELUP_DATA_DIR=/tmp/levelup-test .venv/bin/python -m levelup

Скрипт сдвигает start_date активных привычек назад и добавляет недостающие отметки за прошедшие
дни (до вчера); повторный запуск безопасен. Сегодняшний день не трогается. Не запускайте на своих
настоящих данных — для них скрипт откажется работать.
"""
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from levelup.config import load_config  # noqa: E402
from levelup.domain import rules  # noqa: E402
from levelup.infrastructure.db import open_database  # noqa: E402
from levelup.infrastructure.paths import AppPaths  # noqa: E402
from levelup.infrastructure.repository import Repository  # noqa: E402


def real_data_dirs() -> list[Path]:
    dirs = [Path.home() / ".local" / "share" / "LevelUp"]
    if os.environ.get("LOCALAPPDATA"):
        dirs.append(Path(os.environ["LOCALAPPDATA"]) / "LevelUp")
    return [d.resolve() for d in dirs]


def main() -> int:
    if len(sys.argv) != 3 or not sys.argv[2].isdigit() or int(sys.argv[2]) < 1:
        print(__doc__)
        return 2
    root, days = Path(sys.argv[1]).resolve(), int(sys.argv[2])
    if root in real_data_dirs():
        print("Отказ: это каталог настоящих данных LevelUp. Используйте отдельную тестовую папку.")
        return 2
    paths = AppPaths.for_dir(root)
    if not paths.db.exists():
        print(f"В {root} нет data.db. Сначала запустите приложение с LEVELUP_DATA_DIR={root} и пройдите онбординг.")
        return 2

    config = load_config()
    conn = open_database(paths, config.db_busy_timeout_ms)
    repo = Repository(conn)
    profile = repo.get_profile()
    if not profile.onboarding_done:
        print("Онбординг ещё не пройден: запустите приложение, добавьте первую привычку и закройте его.")
        return 2
    today = datetime.now(timezone.utc).astimezone(ZoneInfo(profile.timezone_id)).date()
    first = today - timedelta(days=days)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    habits = repo.active_habits()
    with repo.transaction():
        for habit in habits:
            repo.conn.execute(
                "UPDATE habit SET start_date = ? WHERE id = ?", (min(habit.start_date, first).isoformat(), habit.id)
            )
            for offset in range(days):  # first .. вчера
                repo.insert_completion(habit.id, first + timedelta(days=offset), stamp, config.xp_per_completion)
    total_xp, count = repo.totals()
    stage = rules.stage_for(total_xp, config.stage_thresholds)
    conn.close()
    points = repo.category_points()
    print(f"Готово: активных привычек {len(habits)}, отметок всего {count}, очков {total_xp}, стадия {stage} из {config.stage_count}.")
    print("Очки категорий: " + ", ".join(f"{c.id} {points.get(c.id, 0)}" for c in config.categories))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
