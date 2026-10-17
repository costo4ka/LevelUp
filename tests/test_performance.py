import random
import time
from datetime import date, datetime, timedelta, timezone

from levelup.application.service import AppService
from levelup.domain.clock import FixedClock
from levelup.infrastructure.db import open_database
from levelup.infrastructure.paths import AppPaths
from levelup.infrastructure.repository import Repository
from tests.helpers import ok


def test_click_to_confirmed_update_p95_under_200ms_on_20k_completions(tmp_path, config):
    paths = AppPaths.for_dir(tmp_path)
    paths.ensure()
    conn = open_database(paths, config.db_busy_timeout_ms)
    clock = FixedClock(datetime(2026, 10, 11, 9, 0, tzinfo=timezone.utc))
    svc = AppService(Repository(conn), clock, config)
    ok(svc.finish_onboarding("UTC", "Привычка 0", "sport"))
    for i in range(1, 5):
        ok(svc.create_habit(f"Привычка {i}", "sport"))
    first = date(2015, 1, 1)
    conn.execute("UPDATE habit SET start_date = ?", (first.isoformat(),))
    habits = [r[0] for r in conn.execute("SELECT id FROM habit")]
    span = (date(2026, 10, 10) - first).days + 1
    rows = [
        (hid, (first + timedelta(days=d)).isoformat(), "2026-01-01T00:00:00Z", 10)
        for hid in habits
        for d in range(span)
    ]
    conn.execute("BEGIN")
    conn.executemany("INSERT INTO completion VALUES (?, ?, ?, ?)", rows)
    conn.execute("COMMIT")
    assert len(rows) >= 20_000

    snap = ok(svc.get_snapshot())
    assert snap["streak_days"] == span  # серия по всей истории считается быстро и верно

    timings, state = [], random.Random(1)
    for i in range(100):
        started = time.perf_counter()
        ok(svc.set_completion(state.choice(habits), snap["date"], i % 2 == 0))
        timings.append(time.perf_counter() - started)
    p95 = sorted(timings)[94]
    assert p95 < 0.2, f"p95 = {p95 * 1000:.0f} мс"
    conn.close()
