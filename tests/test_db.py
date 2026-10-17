import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from levelup.domain.errors import ErrorCode
from levelup.infrastructure import db
from levelup.infrastructure.db import DatabaseOpenError, open_database
from levelup.infrastructure.paths import AppPaths
from tests.helpers import ok


CURRENT = db.MIGRATIONS[-1][0]


def test_fresh_database_and_reopen(tmp_path):
    paths = AppPaths.for_dir(tmp_path)
    paths.ensure()
    conn = open_database(paths)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == CURRENT
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL
    assert conn.execute("SELECT schema_version FROM app_settings").fetchone()[0] == CURRENT
    conn.close()
    open_database(paths).close()
    assert list(paths.backups.glob("*.db")) == []  # пустая БД копий не требует


def test_constraints(onboarded):
    conn, hid = onboarded.conn, onboarded.first_id
    ok(onboarded.svc.set_completion(hid, "2026-10-11", True))
    with pytest.raises(sqlite3.IntegrityError):  # RESTRICT: привычку с историей удалить нельзя
        conn.execute("DELETE FROM habit WHERE id = ?", (hid,))
    with pytest.raises(sqlite3.IntegrityError):  # единственная строка профиля
        conn.execute("INSERT INTO profile (id, base_id, style_id, timezone_id, last_seen_date) VALUES (2, 'm', 'c', 'UTC', '2026-01-01')")
    with pytest.raises(sqlite3.IntegrityError):  # повторная награда за день запрещена ключом
        conn.execute("INSERT INTO completion VALUES (?, '2026-10-11', 'x', 10)", (hid,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO completion VALUES (?, '2026-10-12', 'x', 11)", (hid,))
    with pytest.raises(sqlite3.IntegrityError):  # неизвестная привычка
        conn.execute("INSERT INTO completion VALUES ('00000000-0000-4000-8000-000000000000', '2026-10-12', 'x', 10)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE habit SET start_date = '11.10.2026' WHERE id = ?", (hid,))
    with pytest.raises(sqlite3.IntegrityError):  # категория — только из списка
        conn.execute("UPDATE habit SET category = 'cooking' WHERE id = ?", (hid,))


def _seed_current(paths):
    conn = open_database(paths)
    conn.execute("UPDATE profile SET onboarding_done = 1, timezone_id = 'Europe/Berlin'")
    conn.close()


def _add_note(conn):
    conn.execute("ALTER TABLE habit ADD COLUMN note TEXT")


def test_migration_makes_backup_first(tmp_path, monkeypatch):
    paths = AppPaths.for_dir(tmp_path)
    paths.ensure()
    _seed_current(paths)
    monkeypatch.setattr(db, "MIGRATIONS", [*db.MIGRATIONS, (CURRENT + 1, _add_note)])
    conn = open_database(paths)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == CURRENT + 1
    assert conn.execute("SELECT schema_version FROM app_settings").fetchone()[0] == CURRENT + 1
    assert "note" in [r[1] for r in conn.execute("PRAGMA table_info(habit)")]
    conn.close()
    (backup,) = paths.backups.glob(f"data-*-v{CURRENT}.db")
    old = sqlite3.connect(str(backup))
    assert old.execute("PRAGMA user_version").fetchone()[0] == CURRENT  # копия сделана до миграции
    assert old.execute("SELECT timezone_id FROM profile").fetchone()[0] == "Europe/Berlin"
    old.close()


def test_failed_migration_keeps_original_database(tmp_path, monkeypatch):
    paths = AppPaths.for_dir(tmp_path)
    paths.ensure()
    _seed_current(paths)

    def broken(conn):
        _add_note(conn)
        raise RuntimeError("boom")

    original = db.MIGRATIONS
    monkeypatch.setattr(db, "MIGRATIONS", [*original, (CURRENT + 1, broken)])
    with pytest.raises(DatabaseOpenError) as exc:
        open_database(paths)
    assert exc.value.code is ErrorCode.MIGRATION_FAILED
    assert exc.value.backup_path.exists() and str(exc.value.backup_path) in exc.value.user_message
    monkeypatch.setattr(db, "MIGRATIONS", original)
    conn = open_database(paths)  # исходная БД цела: прежняя версия, колонки нет
    assert conn.execute("PRAGMA user_version").fetchone()[0] == CURRENT
    assert "note" not in [r[1] for r in conn.execute("PRAGMA table_info(habit)")]
    assert conn.execute("SELECT timezone_id FROM profile").fetchone()[0] == "Europe/Berlin"
    conn.close()


def test_only_last_three_backups_are_kept(tmp_path):
    paths = AppPaths.for_dir(tmp_path)
    paths.ensure()
    conn = open_database(paths)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(5):
        db._backup(conn, paths, 1, start + timedelta(hours=i))
    names = sorted(p.name for p in paths.backups.glob("data-*.db"))
    assert len(names) == 3 and names[0].startswith("data-20260101-020000")
    conn.close()


def test_database_from_newer_version_is_refused(tmp_path):
    paths = AppPaths.for_dir(tmp_path)
    paths.ensure()
    open_database(paths).close()
    raw = sqlite3.connect(str(paths.db))
    raw.execute("PRAGMA user_version = 99")
    raw.close()
    with pytest.raises(DatabaseOpenError) as exc:
        open_database(paths)
    assert exc.value.code is ErrorCode.MIGRATION_FAILED


def test_corrupt_database_is_never_replaced(tmp_path):
    paths = AppPaths.for_dir(tmp_path)
    paths.ensure()
    garbage = b"this is definitely not a sqlite database" * 50
    paths.db.write_bytes(garbage)
    with pytest.raises(DatabaseOpenError) as exc:
        open_database(paths)
    assert exc.value.code is ErrorCode.STORAGE_ERROR and "не заменяет" in exc.value.user_message
    assert paths.db.read_bytes() == garbage


def test_v1_database_gets_category_column_with_data_intact(tmp_path, monkeypatch):
    paths = AppPaths.for_dir(tmp_path)
    paths.ensure()
    all_migrations = db.MIGRATIONS
    monkeypatch.setattr(db, "MIGRATIONS", all_migrations[:1])  # создаём базу версии 1, какой она была раньше
    conn = open_database(paths)
    hid = "11111111-1111-4111-8111-111111111111"
    conn.execute("UPDATE profile SET onboarding_done = 1, last_seen_date = '2026-10-11'")
    conn.execute("INSERT INTO habit (id, title, sort_order, created_at_utc, start_date) VALUES (?, 'Бег', 0, 'x', '2026-10-01')", (hid,))
    conn.execute("INSERT INTO completion VALUES (?, '2026-10-02', 'x', 10)", (hid,))
    conn.close()
    monkeypatch.setattr(db, "MIGRATIONS", all_migrations)
    conn = open_database(paths)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    assert conn.execute("SELECT title, category FROM habit").fetchone()[:] == ("Бег", "sport")
    assert conn.execute("SELECT COUNT(*) FROM completion").fetchone()[0] == 1
    conn.close()
    assert len(list(paths.backups.glob("data-*-v1.db"))) == 1
