import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # до любого импорта Qt

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from levelup.application.service import AppService
from levelup.config import load_config
from levelup.domain.clock import FixedClock
from levelup.infrastructure.db import open_database
from levelup.infrastructure.paths import AppPaths
from levelup.infrastructure.repository import Repository
from tests.helpers import ok

START = datetime(2026, 10, 11, 9, 0, tzinfo=timezone.utc)
FIRST_TITLE = "Учить английский 15 минут"


@pytest.fixture(scope="session")
def config():
    return load_config()


@pytest.fixture
def env(tmp_path, config):
    paths = AppPaths.for_dir(tmp_path)
    paths.ensure()
    conn = open_database(paths, config.db_busy_timeout_ms)
    clock = FixedClock(START)
    svc = AppService(Repository(conn), clock, config)
    yield SimpleNamespace(paths=paths, conn=conn, clock=clock, svc=svc, repo=svc.repo, config=config)
    conn.close()


@pytest.fixture
def onboarded(env):
    env.first_id = ok(env.svc.finish_onboarding("UTC", FIRST_TITLE, "sport"))["habit_id"]
    return env
