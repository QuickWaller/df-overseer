"""SQLite schema for the wiki mirror: DDL, version, migrations, FTS5 check.

`docs/CONSULTANT-WIKI.md` 8.2, amended by section 13 (the one-week hold).

Deviations from the 8.2 sketch, each on purpose:

* `pages` carries the SERVED revision (`revid`, `wikitext`, ...) and, apart
  from it, the LATEST SEEN revision (`latest_revid`, `latest_seen_at`,
  `latest_rev_timestamp`) plus `visible_after`, the earliest pending
  promotion time (NULL when nothing is held). Readers join on the served
  columns only.
* `held_changes` holds the not-yet-visible bodies, one row per fetched
  change, so two edits a day apart each become visible on their own clock
  (an edit fetched at T is visible at T + hold, ruling 13). It is keyed by
  its `changes` row.
* `pages.state` has a third value, `pending`: a page first seen after the
  baseline, whose only content is held. It has no served content and no
  reader can see it.
* `changes` has `state` (`held` or `visible`), `visible_after` and
  `made_visible_utc`, so the held to visible transition is recorded.
* `chunks_fts` is a plain FTS5 table (own content, rowid = chunk_id) with a
  `title` column, not an external-content table: the title lives on `pages`,
  and an external-content table can only index columns of its content table.
* `redirects` gains `from_page_id` (nullable) and its `to_*` may be NULL: the
  API returns redirect targets keyed by page id (`api.WikiClient.all_redirects`).

Silent degradation is the enemy: a missing FTS5 raises `Fts5UnavailableError`
with the remedy, never a fallback to LIKE.
"""

from __future__ import annotations

import sqlite3
from typing import Callable

SCHEMA_VERSION = 1


class SchemaError(RuntimeError):
    """Base class for schema problems."""


class Fts5UnavailableError(SchemaError):
    """This SQLite build has no FTS5 (or lacks the porter/unicode61 tokenizer)."""


class SchemaVersionError(SchemaError):
    """The database is newer than this code, or has no readable version."""


_FTS_TOKENIZE = "porter unicode61"

_DDL: tuple[str, ...] = (
    """CREATE TABLE meta (
        key   TEXT PRIMARY KEY,
        value TEXT
    )""",
    """CREATE TABLE pages (
        page_id              INTEGER PRIMARY KEY,
        source               TEXT    NOT NULL DEFAULT 'dfwiki',
        ns                   INTEGER NOT NULL,
        title                TEXT    NOT NULL,
        revid                INTEGER,
        rev_timestamp        TEXT,
        fetched_utc          TEXT,
        byte_length          INTEGER,
        sha256               TEXT,
        wikitext             TEXT,
        game_version         TEXT,
        is_current           INTEGER NOT NULL DEFAULT 1,
        kind                 TEXT    NOT NULL DEFAULT 'article'
                             CHECK (kind IN ('article','raw','script','editnotice')),
        state                TEXT    NOT NULL DEFAULT 'live'
                             CHECK (state IN ('live','deleted','pending')),
        deleted_utc          TEXT,
        reason               TEXT,
        latest_revid         INTEGER,
        latest_seen_at       TEXT,
        latest_rev_timestamp TEXT,
        visible_after        TEXT
    )""",
    # One live page per (source, ns, title): a move cannot double-serve a title.
    "CREATE UNIQUE INDEX pages_live_title ON pages(source, ns, title) WHERE state = 'live'",
    "CREATE INDEX pages_title_nocase ON pages(title COLLATE NOCASE)",
    """CREATE TABLE aliases (
        alias_title TEXT    NOT NULL,
        page_id     INTEGER NOT NULL,
        PRIMARY KEY (alias_title, page_id)
    )""",
    """CREATE TABLE redirects (
        from_title   TEXT    NOT NULL,
        from_ns      INTEGER NOT NULL,
        from_page_id INTEGER,
        to_title     TEXT,
        to_ns        INTEGER,
        PRIMARY KEY (from_title, from_ns)
    )""",
    """CREATE TABLE chunks (
        chunk_id     INTEGER PRIMARY KEY,
        page_id      INTEGER NOT NULL,
        ord          INTEGER NOT NULL,
        heading_path TEXT    NOT NULL,
        text         TEXT    NOT NULL,
        char_count   INTEGER NOT NULL
    )""",
    "CREATE INDEX chunks_page ON chunks(page_id, ord)",
    f"""CREATE VIRTUAL TABLE chunks_fts USING fts5(
        title, heading_path, text, tokenize = '{_FTS_TOKENIZE}'
    )""",
    """CREATE TABLE refresh_runs (
        run_id        TEXT PRIMARY KEY,
        mode          TEXT NOT NULL,
        started_utc   TEXT NOT NULL,
        finished_utc  TEXT,
        status        TEXT NOT NULL,
        requests      INTEGER NOT NULL DEFAULT 0,
        pages_fetched INTEGER NOT NULL DEFAULT 0,
        cursor_from   TEXT,
        cursor_to     TEXT,
        error_class   TEXT,
        error_detail  TEXT
    )""",
    """CREATE TABLE changes (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id           TEXT,
        seq              INTEGER,
        kind             TEXT NOT NULL,
        ns               INTEGER,
        title            TEXT,
        page_id          INTEGER,
        old_title        TEXT,
        new_title        TEXT,
        old_revid        INTEGER,
        new_revid        INTEGER,
        wiki_timestamp   TEXT,
        old_len          INTEGER,
        new_len          INTEGER,
        edit_summary     TEXT,
        source           TEXT,
        detected_utc     TEXT NOT NULL,
        state            TEXT NOT NULL DEFAULT 'visible'
                         CHECK (state IN ('held','visible')),
        visible_after    TEXT,
        made_visible_utc TEXT
    )""",
    "CREATE INDEX changes_page ON changes(page_id)",
    "CREATE INDEX changes_state ON changes(state, visible_after)",
    """CREATE TABLE held_changes (
        change_id      INTEGER PRIMARY KEY,
        page_id        INTEGER NOT NULL,
        op             TEXT NOT NULL CHECK (op IN ('new','edit','restore','move','delete')),
        title          TEXT,
        ns             INTEGER,
        revid          INTEGER,
        rev_timestamp  TEXT,
        fetched_utc    TEXT,
        byte_length    INTEGER,
        sha256         TEXT,
        wikitext       TEXT,
        chunks_json    TEXT,
        game_version   TEXT,
        is_current     INTEGER,
        kind           TEXT,
        reason         TEXT,
        seen_utc       TEXT NOT NULL,
        visible_after  TEXT NOT NULL
    )""",
    "CREATE INDEX held_page ON held_changes(page_id, seen_utc)",
    "CREATE INDEX held_due ON held_changes(visible_after)",
    """CREATE TABLE revision_archive (
        page_id      INTEGER NOT NULL,
        revid        INTEGER NOT NULL,
        sha256       TEXT,
        wikitext     TEXT,
        archived_utc TEXT NOT NULL,
        PRIMARY KEY (page_id, revid)
    )""",
)

# version -> callable(conn) that migrates FROM that version to version + 1.
# Empty at version 1; the framework and its test exist so the first real
# migration is a dict entry, not a redesign.
MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {}


def check_fts5(conn: sqlite3.Connection) -> None:
    """Raise `Fts5UnavailableError` unless FTS5 with our tokenizer works here."""
    try:
        conn.execute(
            f"CREATE VIRTUAL TABLE temp._fts5_probe USING fts5(x, tokenize = '{_FTS_TOKENIZE}')"
        )
        conn.execute("DROP TABLE temp._fts5_probe")
    except sqlite3.OperationalError as exc:
        msg = str(exc).lower()
        if not ("fts5" in msg or "tokenizer" in msg or "no such module" in msg):
            raise  # a lock or I/O problem is not "FTS5 is missing"
        raise Fts5UnavailableError(
            f"SQLite {sqlite3.sqlite_version} has no usable FTS5 ({exc}). The wiki mirror "
            "needs FTS5 with the porter and unicode61 tokenizers; there is no fallback. "
            "Use a Python whose sqlite3 was built with SQLITE_ENABLE_FTS5."
        ) from exc


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table') AND name = ?", (name,)
    ).fetchone()
    return row is not None


def read_schema_version(conn: sqlite3.Connection) -> int | None:
    """The stored schema version, or None for a database with no `meta` table."""
    if not _has_table(conn, "meta"):
        return None
    row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    if row is None:
        raise SchemaVersionError("meta table exists but has no schema_version row")
    try:
        return int(row[0])
    except (TypeError, ValueError) as exc:
        raise SchemaVersionError(f"unreadable schema_version {row[0]!r}") from exc


def create_schema(conn: sqlite3.Connection) -> None:
    """Create the version-1 schema in an empty database."""
    check_fts5(conn)
    with conn:
        for stmt in _DDL:
            conn.execute(stmt)
        conn.execute(
            "INSERT INTO meta(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),)
        )


def ensure_schema(conn: sqlite3.Connection) -> int:
    """Create or migrate to `SCHEMA_VERSION`; return the resulting version.

    Refuses (with `SchemaVersionError`) a database from a newer schema.
    """
    check_fts5(conn)
    version = read_schema_version(conn)
    if version is None:
        create_schema(conn)
        return SCHEMA_VERSION
    if version > SCHEMA_VERSION:
        raise SchemaVersionError(
            f"database schema {version} is newer than this code ({SCHEMA_VERSION})"
        )
    while version < SCHEMA_VERSION:
        step = MIGRATIONS.get(version)
        if step is None:
            raise SchemaVersionError(f"no migration from schema {version}")
        with conn:
            step(conn)
            conn.execute(
                "UPDATE meta SET value = ? WHERE key = 'schema_version'", (str(version + 1),)
            )
        version += 1
    return version
