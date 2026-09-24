"""Schema creation, versioning, migration and the FTS5 check."""

from __future__ import annotations

import sqlite3

import pytest

from wikimirror import schema
from wikimirror.store import Store


class NoFts5:
    """A connection stand-in whose SQLite has no FTS5 (delegates everything else)."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, *a):
        if "fts5" in sql.lower():
            raise sqlite3.OperationalError("no such module: fts5")
        return self._conn.execute(sql, *a)

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, *a):
        return self._conn.__exit__(*a)


def tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_create_schema_makes_every_table_and_records_the_version():
    conn = sqlite3.connect(":memory:")
    assert schema.ensure_schema(conn) == schema.SCHEMA_VERSION
    assert {"meta", "pages", "aliases", "redirects", "chunks", "chunks_fts", "refresh_runs",
            "changes", "held_changes", "revision_archive"} <= tables(conn)
    assert schema.read_schema_version(conn) == schema.SCHEMA_VERSION


def test_pages_keep_served_and_latest_seen_revision_apart():
    conn = sqlite3.connect(":memory:")
    schema.ensure_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(pages)")}
    assert {"revid", "wikitext", "latest_revid", "latest_seen_at", "visible_after"} <= cols
    ccols = {r[1] for r in conn.execute("PRAGMA table_info(changes)")}
    assert {"state", "visible_after", "made_visible_utc"} <= ccols


def test_ensure_schema_is_idempotent():
    conn = sqlite3.connect(":memory:")
    schema.ensure_schema(conn)
    conn.execute("INSERT INTO meta(key, value) VALUES ('k', 'v')")
    schema.ensure_schema(conn)
    assert conn.execute("SELECT value FROM meta WHERE key='k'").fetchone()[0] == "v"


def test_a_newer_database_is_refused():
    conn = sqlite3.connect(":memory:")
    schema.ensure_schema(conn)
    conn.execute("UPDATE meta SET value = '99' WHERE key = 'schema_version'")
    with pytest.raises(schema.SchemaVersionError):
        schema.ensure_schema(conn)


def test_unreadable_version_is_refused_not_ignored():
    conn = sqlite3.connect(":memory:")
    schema.ensure_schema(conn)
    conn.execute("UPDATE meta SET value = 'abc' WHERE key = 'schema_version'")
    with pytest.raises(schema.SchemaVersionError):
        schema.read_schema_version(conn)


def test_migrations_run_in_order(monkeypatch):
    conn = sqlite3.connect(":memory:")
    schema.ensure_schema(conn)
    monkeypatch.setattr(schema, "SCHEMA_VERSION", 2)
    monkeypatch.setitem(schema.MIGRATIONS, 1, lambda c: c.execute("CREATE TABLE added_in_v2(x)"))
    assert schema.ensure_schema(conn) == 2
    assert "added_in_v2" in tables(conn) and schema.read_schema_version(conn) == 2


def test_missing_migration_step_is_an_error(monkeypatch):
    conn = sqlite3.connect(":memory:")
    schema.ensure_schema(conn)
    monkeypatch.setattr(schema, "SCHEMA_VERSION", 3)
    with pytest.raises(schema.SchemaVersionError):
        schema.ensure_schema(conn)


def test_fts5_present_in_this_python():
    """Fails loudly, by design, on an interpreter whose sqlite3 lacks FTS5."""
    schema.check_fts5(sqlite3.connect(":memory:"))


def test_missing_fts5_raises_a_clear_error_and_creates_nothing():
    real = sqlite3.connect(":memory:")
    with pytest.raises(schema.Fts5UnavailableError) as e:
        schema.ensure_schema(NoFts5(real))
    assert "FTS5" in str(e.value) and "no fallback" in str(e.value)
    assert tables(real) == set()


def test_store_open_refuses_without_fts5(tmp_path, monkeypatch):
    monkeypatch.setattr(
        schema, "check_fts5",
        lambda conn: (_ for _ in ()).throw(schema.Fts5UnavailableError("no fts5")),
    )
    with pytest.raises(schema.Fts5UnavailableError):
        Store.open(tmp_path / "x.sqlite3")


def test_one_live_page_per_title_is_enforced_by_the_schema():
    conn = sqlite3.connect(":memory:")
    schema.ensure_schema(conn)
    conn.execute("INSERT INTO pages(page_id, ns, title) VALUES (1, 0, 'Well')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO pages(page_id, ns, title) VALUES (2, 0, 'Well')")
    conn.execute("UPDATE pages SET state='deleted' WHERE page_id=1")
    conn.execute("INSERT INTO pages(page_id, ns, title) VALUES (2, 0, 'Well')")  # tombstone frees the title
