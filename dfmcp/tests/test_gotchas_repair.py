"""The v1 to v2 migration must leave `outcomes` and `status_history` pointing
at `entries`, and a store the first version of the migration already broke
(references to the dropped `entries_v1_old`, live on 2026-10-02) must be
repaired on open. Every row survives both."""

from __future__ import annotations

import sqlite3

import pytest

from dfmcp import gotchas_store as gs
from dfmcp.tests.test_gotchas_store import _make_v1_store


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "gotchas.sqlite3"
    gs.init_store(path)
    return path


def _break_like_live(path):
    """Reproduce the live store's damage: run the OLD v1 to v2 migration (rename
    `entries` aside, rebuild, drop the renamed copy), which makes SQLite
    rewrite the child tables' foreign keys to the dropped `entries_v1_old`."""
    conn = sqlite3.connect(path, isolation_level=None)
    conn.execute("BEGIN")
    conn.execute("ALTER TABLE entries RENAME TO entries_v1_old")
    conn.execute(gs._ENTRIES_V2_SQL)
    conn.execute(
        "INSERT INTO entries SELECT id, tool, kind, list, title, body, status, created_at, "
        "written_by_role, run_id, call_excerpt FROM entries_v1_old"
    )
    conn.execute("DROP TABLE entries_v1_old")
    conn.execute("CREATE INDEX idx_entries_tool ON entries(tool, list, status)")
    conn.execute("CREATE INDEX idx_entries_run ON entries(run_id)")
    conn.execute("UPDATE schema_version SET version = 2")
    conn.execute("COMMIT")
    conn.close()


def _child_sql(path):
    conn = sqlite3.connect(path)
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE name IN ('outcomes', 'status_history')"
    ).fetchall()
    conn.close()
    return dict(rows)


def _new_outcome(path, entry_id="gotcha-0001", run_id="run-new"):
    return gs.add_outcome(path, entry_id, result="did_not_work", note="again", role="overseer", run_id=run_id)


def _dump(path):
    conn = sqlite3.connect(path)
    out = {
        t: conn.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()
        for t in ("entries", "outcomes", "status_history")
    }
    conn.close()
    return out


def test_the_old_migration_really_breaks_a_store(tmp_path):
    # Guards the fixture: if SQLite stops rewriting references this fails and
    # the repair tests below would be vacuous.
    path = tmp_path / "broken.sqlite3"
    _make_v1_store(path)
    _break_like_live(path)
    assert all("entries_v1_old" in sql for sql in _child_sql(path).values())
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    with pytest.raises(sqlite3.OperationalError, match="entries_v1_old"):
        conn.execute(
            "INSERT INTO outcomes (entry_id, at, role, run_id, result) "
            "VALUES ('gotcha-0001', 'x', 'r', 'r', 'worked')"
        )
    conn.close()


def test_v1_store_migrates_with_correct_references_and_accepts_outcome_and_status(tmp_path):
    path = tmp_path / "v1.sqlite3"
    _make_v1_store(path)
    before = _dump(path)
    gs.check_store(path)
    assert not any("entries_v1_old" in sql for sql in _child_sql(path).values())
    assert _dump(path) == before
    _new_outcome(path)
    gs.set_status(path, "vent-0001", "accepted", by="maintainer")
    conn = sqlite3.connect(path)
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM status_history").fetchone()[0] == 2
    conn.close()


def test_broken_store_is_repaired_on_open_and_keeps_every_row(tmp_path):
    path = tmp_path / "broken.sqlite3"
    _make_v1_store(path)
    _break_like_live(path)
    before = _dump(path)

    gs.check_store(path)  # repair runs on open

    assert not any("entries_v1_old" in sql for sql in _child_sql(path).values())
    assert _dump(path) == before
    conn = sqlite3.connect(path)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()
    assert {"idx_outcomes_entry", "idx_outcomes_run", "idx_entries_tool", "idx_entries_run"} <= names
    assert not any(n.endswith("_new") for n in names)

    _new_outcome(path)
    gs.set_status(path, "vent-0001", "accepted", by="maintainer")
    got = gs.entries_for_tool(path, "building.build")[0]
    assert [o["result"] for o in got["outcomes"]] == ["worked", "did_not_work"]
    conn = sqlite3.connect(path)
    assert [r[0] for r in conn.execute("SELECT seq FROM outcomes ORDER BY seq")] == [1, 2]
    conn.close()


def test_explicit_migrate_command_repairs_a_broken_store_and_is_idempotent(tmp_path):
    path = tmp_path / "broken.sqlite3"
    _make_v1_store(path)
    _break_like_live(path)
    assert gs.migrate_store(path) == 2
    assert gs.migrate_store(path) == 2
    assert not any("entries_v1_old" in sql for sql in _child_sql(path).values())
    _new_outcome(path)


def test_repair_is_a_no_op_on_a_healthy_store(db):
    before = _child_sql(db)
    gs.migrate_store(db)
    assert _child_sql(db) == before
