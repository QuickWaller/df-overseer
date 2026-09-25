"""The wiki mirror store: writes under the one-week hold rule, atomic promote of
a staged full pull, and the read-side helpers the reader and search tools call.

`docs/CONSULTANT-WIKI.md` 4.3, 4.5, 5, 8 and the user's rulings in 13.

The hold rule (13), as implemented:

* A BASELINE write (`apply_revision(..., baseline=True)`, used by the first full
  pull and a deliberate version-bump re-pull) is visible immediately.
* Any later change (`apply_revision`, `apply_move`, `apply_delete`) is stored as
  a `held_changes` row plus a `changes` row with `state = 'held'` and
  `visible_after = seen + hold` (default 7 days, configuration). Until then a
  reader keeps getting the previously served revision, or nothing for a page
  first seen after the baseline.
* `promote_due()` makes every change whose `visible_after` has passed visible,
  in fetch order, and records the transition on the `changes` row. It needs a
  writable connection: a `mode=ro` reader cannot promote, so a writer (every
  refresh run) must call it, and readers see `promotion_overdue` in
  `staleness()` if it has not happened.
* Readers only ever see the served columns of `pages`.

Fetched wikitext is data: stored and returned, never interpreted.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence

from wikimirror import schema
from wikimirror.api import PageRevision, history_url, permalink

HOLD_DAYS_DEFAULT = 7
RECENT_EDIT_HOURS = 48
MIN_FREE_BYTES_DEFAULT = 500 * 1024 * 1024
EDIT_SUMMARY_MAX = 500
LICENSE = "MIT and GFDL (Dwarf Fortress Wiki contributors)"
WIKI_NOTE = "Main-namespace wiki content can lag the game; recheck against game data."
NAMESPACES_PATH = Path(__file__).with_name("namespaces.yaml")

_KIND_SUFFIXES = (
    ("/raw", "raw"),
    ("/entity raw", "raw"),
    ("/script", "script"),
    ("/edit notice", "editnotice"),
)


# ---- errors -----------------------------------------------------------------


class StoreError(RuntimeError):
    """Base class for store problems."""


class NamespaceNotIngested(StoreError):
    """The namespace id is not on the allow-list (`namespaces.yaml`)."""


class StoreLockedError(StoreError):
    """The database is locked or unreadable past the timeout. Never an empty result."""


class PromoteError(StoreError):
    """A staged database failed a check and was NOT promoted."""

    def __init__(self, reasons: Sequence[str]):
        super().__init__("staged database not promoted: " + "; ".join(reasons))
        self.reasons = list(reasons)


class AmbiguousTitle(StoreError):
    def __init__(self, title: str, candidates: Sequence[str]):
        super().__init__(f"title {title!r} matches several pages case-insensitively: {list(candidates)}")
        self.candidates = list(candidates)


# ---- time and small helpers -------------------------------------------------


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_title(title: str) -> str:
    """MediaWiki-style: underscores are spaces, runs of spaces collapse, ends trimmed."""
    return re.sub(r"\s+", " ", title.replace("_", " ")).strip()


def classify_kind(title: str) -> str:
    """article | raw | script | editnotice, from the title suffix (design 8.3)."""
    low = title.lower()
    for suffix, kind in _KIND_SUFFIXES:
        if low.endswith(suffix):
            return kind
    return "article"


def _clean_summary(text: str) -> str:
    return "".join(ch for ch in text if ch.isprintable())[:EDIT_SUMMARY_MAX]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Chunk:
    heading_path: str
    text: str


def _as_chunk(item: Any) -> Chunk:
    if isinstance(item, Chunk):
        return item
    if isinstance(item, (tuple, list)) and len(item) == 2:
        return Chunk(str(item[0]), str(item[1]))
    raise TypeError(f"chunk must be Chunk or (heading_path, text), got {type(item).__name__}")


# ---- namespaces -------------------------------------------------------------


@dataclass(frozen=True)
class NamespaceRule:
    ns: int
    name: str
    ingest: bool
    is_current: int
    game_version: str | None
    from_template: str | None
    label: str
    reason: str | None


def load_namespaces(path: str | os.PathLike[str] | None = None) -> dict[int, NamespaceRule]:
    """Read `namespaces.yaml`. An excluded row must say why; a malformed file raises."""
    import yaml  # PyYAML: already a repo dependency (doctrine, dfmcp)

    doc = yaml.safe_load(Path(path or NAMESPACES_PATH).read_text(encoding="utf-8"))
    rows = (doc or {}).get("namespaces")
    if not isinstance(rows, dict) or not rows:
        raise StoreError("namespaces.yaml has no `namespaces` mapping")
    out: dict[int, NamespaceRule] = {}
    for key, row in rows.items():
        ns = int(key)
        ingest = bool(row.get("ingest"))
        if not ingest and not row.get("reason"):
            raise StoreError(f"namespace {ns} is excluded without a `reason`")
        if ingest and row.get("game_version") is None and not row.get("from_template"):
            raise StoreError(f"ingested namespace {ns} has neither game_version nor from_template")
        out[ns] = NamespaceRule(
            ns=ns,
            name=str(row.get("name", "")),
            ingest=ingest,
            is_current=int(row.get("is_current", 0)),
            game_version=row.get("game_version"),
            from_template=row.get("from_template"),
            label=str(row.get("label", "")),
            reason=row.get("reason"),
        )
    return out


def ingested_namespace_ids(rules: dict[int, NamespaceRule] | None = None) -> list[int]:
    rules = rules if rules is not None else load_namespaces()
    return sorted(ns for ns, r in rules.items() if r.ingest)


# ---- results ----------------------------------------------------------------


@dataclass(frozen=True)
class ApplyResult:
    """What a write did. `action` is one of: baseline, held, unchanged,
    not_in_mirror. `unchanged` means the revision was at or below the latest one
    already seen (idempotent re-run); it is a named outcome, not a silent skip."""

    action: str
    page_id: int
    change_id: int | None = None
    visible_after: str | None = None


@dataclass(frozen=True)
class Promotion:
    change_id: int
    page_id: int
    op: str
    title: str | None
    made_visible_utc: str


@dataclass(frozen=True)
class PromoteReport:
    live_path: str
    previous_path: str | None
    manifest_path: str
    page_count: int
    chunk_count: int
    sha256: str


# ---- the store --------------------------------------------------------------


class Store:
    """A connection plus the mirror's rules. Construct with `open` or `open_readonly`."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        path: str | None = None,
        hold: timedelta | None = None,
        clock: Callable[[], datetime] | None = None,
        namespaces: dict[int, NamespaceRule] | None = None,
        readonly: bool = False,
    ):
        self.conn = conn
        self.path = path
        self.hold = hold if hold is not None else timedelta(days=HOLD_DAYS_DEFAULT)
        self.clock = clock or _utcnow
        self._namespaces = namespaces
        self.readonly = readonly
        self._depth = 0

    # -- opening -------------------------------------------------------------

    @classmethod
    def open(
        cls,
        path: str | os.PathLike[str],
        *,
        create: bool = True,
        timeout: float = 30.0,
        **kw: Any,
    ) -> "Store":
        """Open read-write, creating the schema if `create` and the file is new.

        Raises `Fts5UnavailableError` (no FTS5) or `SchemaVersionError` (newer or
        unreadable database) rather than degrade.
        """
        p = str(path)
        if not create and not os.path.exists(p):
            raise StoreError(f"database not found: {p}")
        conn = sqlite3.connect(p, timeout=timeout, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            if create:
                schema.ensure_schema(conn)
            else:
                schema.check_fts5(conn)
                version = schema.read_schema_version(conn)
                if version != schema.SCHEMA_VERSION:
                    raise schema.SchemaVersionError(
                        f"database schema is {version}, code expects {schema.SCHEMA_VERSION}"
                    )
        except Exception:
            conn.close()
            raise
        return cls(conn, path=p, **kw)

    @classmethod
    def open_readonly(cls, path: str | os.PathLike[str], *, timeout: float = 5.0, **kw: Any) -> "Store":
        """Read-only URI open with a busy timeout (design 8.5). No promote, no writes."""
        p = Path(path)
        if not p.exists():
            raise StoreError(f"database not found: {p}")
        uri = f"file:{p.as_posix()}?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True, timeout=timeout, isolation_level=None)
            conn.row_factory = sqlite3.Row
            schema.check_fts5(conn)
            version = schema.read_schema_version(conn)
        except sqlite3.OperationalError as exc:
            raise StoreLockedError(f"cannot open {p} read-only: {exc}") from exc
        if version != schema.SCHEMA_VERSION:
            conn.close()
            raise schema.SchemaVersionError(
                f"database schema is {version}, code expects {schema.SCHEMA_VERSION}"
            )
        return cls(conn, path=str(p), readonly=True, **kw)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    @property
    def namespaces(self) -> dict[int, NamespaceRule]:
        if self._namespaces is None:
            self._namespaces = load_namespaces()
        return self._namespaces

    def now(self) -> datetime:
        return self.clock()

    # -- transactions --------------------------------------------------------

    @contextlib.contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """BEGIN IMMEDIATE ... COMMIT, rolled back on any exception. Re-entrant."""
        if self.readonly:
            raise StoreError("store is read-only")
        outer = self._depth == 0
        if outer:
            self.conn.execute("BEGIN IMMEDIATE")
        self._depth += 1
        try:
            yield self.conn
        except BaseException:
            self._depth -= 1
            if outer:
                self.conn.execute("ROLLBACK")
            raise
        else:
            self._depth -= 1
            if outer:
                self.conn.execute("COMMIT")

    # -- meta ----------------------------------------------------------------

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self._read("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return default if row is None else row[0]

    def set_meta(self, key: str, value: str | None) -> None:
        with self.transaction():
            self.conn.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def add_requests_today(self, n: int) -> int:
        """Count requests against the per-day budget (design 3.3); returns today's total."""
        today = self.now().strftime("%Y-%m-%d")
        with self.transaction():
            if self.get_meta("requests_today_date") != today:
                self.set_meta("requests_today_date", today)
                self.set_meta("requests_today_count", "0")
            total = int(self.get_meta("requests_today_count", "0") or 0) + int(n)
            self.set_meta("requests_today_count", str(total))
        return total

    def _read(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        try:
            return self.conn.execute(sql, params)
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc) or "busy" in str(exc):
                raise StoreLockedError(f"database locked: {exc}") from exc
            raise

    # -- runs ----------------------------------------------------------------

    def start_run(self, mode: str, *, cursor_from: str | None = None) -> str:
        started = iso(self.now())
        base = f"{started.replace('-', '').replace(':', '')}-{mode[:1]}"
        run_id, n = base, 1
        with self.transaction():
            while self.conn.execute("SELECT 1 FROM refresh_runs WHERE run_id = ?", (run_id,)).fetchone():
                n += 1
                run_id = f"{base}{n}"
            self.conn.execute(
                "INSERT INTO refresh_runs(run_id, mode, started_utc, status, cursor_from) "
                "VALUES (?, ?, ?, 'running', ?)",
                (run_id, mode, started, cursor_from),
            )
            self.set_meta("last_refresh_attempt_utc", started)
        return run_id

    def finish_run(
        self,
        run_id: str,
        status: str,
        *,
        requests: int = 0,
        pages_fetched: int = 0,
        cursor_to: str | None = None,
        error_class: str | None = None,
        error_detail: str | None = None,
    ) -> None:
        finished = iso(self.now())
        with self.transaction():
            cur = self.conn.execute(
                "UPDATE refresh_runs SET finished_utc=?, status=?, requests=?, pages_fetched=?, "
                "cursor_to=?, error_class=?, error_detail=? WHERE run_id=?",
                (finished, status, requests, pages_fetched, cursor_to, error_class, error_detail, run_id),
            )
            if cur.rowcount != 1:
                raise StoreError(f"unknown run {run_id!r}")
            self.set_meta("last_run_status", status)
            if status == "ok":
                self.set_meta("last_refresh_ok_utc", finished)
                self.set_meta("last_error_class", None)
            else:
                self.set_meta("last_error_class", error_class or status)

    # -- writes: the hold rule ------------------------------------------------

    def _rule_for(self, ns: int) -> NamespaceRule:
        rule = self.namespaces.get(ns)
        if rule is None or not rule.ingest:
            raise NamespaceNotIngested(
                f"namespace id {ns} is not on the ingest allow-list (namespaces.yaml)"
            )
        return rule

    def _held_min(self, page_id: int) -> str | None:
        row = self.conn.execute(
            "SELECT MIN(visible_after) FROM held_changes WHERE page_id = ?", (page_id,)
        ).fetchone()
        return row[0]

    def _refresh_page_visible_after(self, page_id: int) -> None:
        self.conn.execute(
            "UPDATE pages SET visible_after = ? WHERE page_id = ?",
            (self._held_min(page_id), page_id),
        )

    def _replace_chunks(self, page_id: int, title: str, chunks: Iterable[Any]) -> int:
        old = [r[0] for r in self.conn.execute("SELECT chunk_id FROM chunks WHERE page_id = ?", (page_id,))]
        for cid in old:
            self.conn.execute("DELETE FROM chunks_fts WHERE rowid = ?", (cid,))
        self.conn.execute("DELETE FROM chunks WHERE page_id = ?", (page_id,))
        n = 0
        for ordinal, item in enumerate(_as_chunk(c) for c in chunks):
            cur = self.conn.execute(
                "INSERT INTO chunks(page_id, ord, heading_path, text, char_count) VALUES (?,?,?,?,?)",
                (page_id, ordinal, item.heading_path, item.text, len(item.text)),
            )
            self.conn.execute(
                "INSERT INTO chunks_fts(rowid, title, heading_path, text) VALUES (?,?,?,?)",
                (cur.lastrowid, title, item.heading_path, item.text),
            )
            n += 1
        return n

    def _log_change(self, *, kind: str, state: str, now: str, visible_after: str | None, **f: Any) -> int:
        cur = self.conn.execute(
            "INSERT INTO changes(run_id, seq, kind, ns, title, page_id, old_title, new_title, "
            "old_revid, new_revid, wiki_timestamp, old_len, new_len, edit_summary, source, "
            "detected_utc, state, visible_after, made_visible_utc) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                f.get("run_id"), f.get("seq"), kind, f.get("ns"), f.get("title"), f.get("page_id"),
                f.get("old_title"), f.get("new_title"), f.get("old_revid"), f.get("new_revid"),
                f.get("wiki_timestamp"), f.get("old_len"), f.get("new_len"),
                _clean_summary(f["edit_summary"]) if f.get("edit_summary") else None,
                f.get("source"), now, state, visible_after,
                now if state == "visible" else None,
            ),
        )
        return int(cur.lastrowid)

    def apply_revision(
        self,
        rev: PageRevision,
        *,
        chunks: Iterable[Any] = (),
        source: str = "recentchanges",
        run_id: str | None = None,
        seq: int | None = None,
        baseline: bool = False,
        game_version: str | None = None,
    ) -> ApplyResult:
        """Ingest a fetched revision.

        `baseline=True`: visible now (first full pull, deliberate re-pull). The
        page must have no held changes. Otherwise the revision is HELD until
        `now + hold`. A revision at or below the latest seen one returns
        `action='unchanged'` (idempotent). `game_version` is required only for a
        namespace whose version comes from `Template:Current/version`.
        """
        rule = self._rule_for(rev.ns)
        gv = rule.game_version or game_version
        if gv is None:
            raise StoreError(
                f"namespace {rev.ns} takes its game_version from {rule.from_template}; pass game_version"
            )
        chunk_list = [_as_chunk(c) for c in chunks]
        now_dt = self.now()
        now = iso(now_dt)
        sha = _sha(rev.wikitext)
        kind = classify_kind(rev.title)
        with self.transaction():
            row = self.conn.execute("SELECT * FROM pages WHERE page_id = ?", (rev.page_id,)).fetchone()
            if baseline:
                if row is not None and self.conn.execute(
                    "SELECT 1 FROM held_changes WHERE page_id = ?", (rev.page_id,)
                ).fetchone():
                    raise StoreError(f"baseline write over page {rev.page_id} with held changes")
                self._write_served(rev, rule, gv, kind, sha, chunk_list, existing=row)
                cid = self._log_change(
                    kind="added" if row is None else "changed", state="visible", now=now,
                    visible_after=None, run_id=run_id, seq=seq, ns=rev.ns, title=rev.title,
                    page_id=rev.page_id, old_revid=None if row is None else row["revid"],
                    new_revid=rev.revid, wiki_timestamp=rev.timestamp, old_len=None if row is None else row["byte_length"],
                    new_len=rev.byte_length, edit_summary=rev.comment, source=source,
                )
                return ApplyResult("baseline", rev.page_id, cid)
            visible_after = iso(now_dt + self.hold)
            if row is None:
                self.conn.execute(
                    "INSERT INTO pages(page_id, source, ns, title, game_version, is_current, kind, state, "
                    "latest_revid, latest_seen_at, latest_rev_timestamp, visible_after) "
                    "VALUES (?, 'dfwiki', ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)",
                    (rev.page_id, rev.ns, rev.title, gv, rule.is_current, kind,
                     rev.revid, now, rev.timestamp, visible_after),
                )
                change_kind, op, old_revid, old_len, old_title = "added", "new", None, None, None
            else:
                latest = row["latest_revid"] or row["revid"] or 0
                if row["state"] == "deleted":
                    # A restored page keeps its revid, so the revid test cannot apply to a
                    # tombstone; only a restore already held for this revid is a repeat.
                    if self.conn.execute(
                        "SELECT 1 FROM held_changes WHERE page_id = ? AND op = 'restore' AND revid = ?",
                        (rev.page_id, rev.revid),
                    ).fetchone():
                        return ApplyResult("unchanged", rev.page_id)
                elif rev.revid <= latest:
                    return ApplyResult("unchanged", rev.page_id)
                if row["state"] == "deleted":
                    change_kind, op = "restored", "restore"
                else:
                    change_kind, op = "changed", "edit"
                old_revid, old_len = row["latest_revid"] or row["revid"], row["byte_length"]
                old_title = None
                if normalize_title(row["title"]) != normalize_title(rev.title):
                    change_kind, old_title = "moved", row["title"]
                self.conn.execute(
                    "UPDATE pages SET latest_revid=?, latest_seen_at=?, latest_rev_timestamp=? WHERE page_id=?",
                    (rev.revid, now, rev.timestamp, rev.page_id),
                )
            cid = self._log_change(
                kind=change_kind, state="held", now=now, visible_after=visible_after, run_id=run_id,
                seq=seq, ns=rev.ns, title=rev.title, page_id=rev.page_id, old_title=old_title,
                new_title=rev.title if old_title else None, old_revid=old_revid, new_revid=rev.revid,
                wiki_timestamp=rev.timestamp, old_len=old_len, new_len=rev.byte_length,
                edit_summary=rev.comment, source=source,
            )
            self.conn.execute(
                "INSERT INTO held_changes(change_id, page_id, op, title, ns, revid, rev_timestamp, "
                "fetched_utc, byte_length, sha256, wikitext, chunks_json, game_version, is_current, "
                "kind, seen_utc, visible_after) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cid, rev.page_id, op, rev.title, rev.ns, rev.revid, rev.timestamp, rev.fetched_utc,
                 rev.byte_length, sha, rev.wikitext,
                 json.dumps([[c.heading_path, c.text] for c in chunk_list]),
                 gv, rule.is_current, kind, now, visible_after),
            )
            self._refresh_page_visible_after(rev.page_id)
            return ApplyResult("held", rev.page_id, cid, visible_after)

    def _write_served(
        self, rev: PageRevision, rule: NamespaceRule, gv: str, kind: str, sha: str,
        chunk_list: list[Chunk], *, existing: sqlite3.Row | None,
    ) -> None:
        if existing is not None and normalize_title(existing["title"]) != normalize_title(rev.title):
            self.conn.execute(
                "INSERT OR IGNORE INTO aliases(alias_title, page_id) VALUES (?, ?)",
                (existing["title"], rev.page_id),
            )
        vals = (rev.ns, rev.title, rev.revid, rev.timestamp, rev.fetched_utc, rev.byte_length, sha,
                rev.wikitext, gv, rule.is_current, kind, rev.revid, rev.fetched_utc, rev.timestamp)
        if existing is None:
            self.conn.execute(
                "INSERT INTO pages(ns, title, revid, rev_timestamp, fetched_utc, byte_length, sha256, "
                "wikitext, game_version, is_current, kind, state, latest_revid, latest_seen_at, "
                "latest_rev_timestamp, page_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,'live',?,?,?,?)",
                vals + (rev.page_id,),
            )
        else:
            self.conn.execute(
                "UPDATE pages SET ns=?, title=?, revid=?, rev_timestamp=?, fetched_utc=?, byte_length=?, "
                "sha256=?, wikitext=?, game_version=?, is_current=?, kind=?, state='live', deleted_utc=NULL, "
                "reason=NULL, latest_revid=?, latest_seen_at=?, latest_rev_timestamp=?, visible_after=NULL "
                "WHERE page_id=?",
                vals + (rev.page_id,),
            )
        self._replace_chunks(rev.page_id, rev.title, chunk_list)

    def _hold_simple(
        self, page_id: int, op: str, *, title: str | None, ns: int | None, reason: str | None,
        run_id: str | None, seq: int | None, source: str, wiki_timestamp: str | None,
        edit_summary: str | None,
    ) -> ApplyResult:
        now_dt = self.now()
        now = iso(now_dt)
        visible_after = iso(now_dt + self.hold)
        with self.transaction():
            row = self.conn.execute("SELECT * FROM pages WHERE page_id = ?", (page_id,)).fetchone()
            if row is None or row["state"] == "deleted":
                return ApplyResult("not_in_mirror", page_id)
            dup = self.conn.execute(
                "SELECT 1 FROM held_changes WHERE page_id = ? AND op = ? AND IFNULL(title,'') = IFNULL(?,'')",
                (page_id, op, title),
            ).fetchone()
            if dup:
                return ApplyResult("unchanged", page_id)
            kind = "deleted" if op == "delete" else "moved"
            cid = self._log_change(
                kind=kind, state="held", now=now, visible_after=visible_after, run_id=run_id, seq=seq,
                ns=ns if ns is not None else row["ns"], title=row["title"], page_id=page_id,
                old_title=row["title"] if op == "move" else None,
                new_title=title if op == "move" else None,
                old_revid=row["latest_revid"] or row["revid"], new_revid=None,
                wiki_timestamp=wiki_timestamp, old_len=row["byte_length"], new_len=None,
                edit_summary=edit_summary, source=source,
            )
            if op == "delete" and reason:
                # `reason` rides on the held row; the changes row carries the kind.
                pass
            self.conn.execute(
                "INSERT INTO held_changes(change_id, page_id, op, title, ns, reason, seen_utc, visible_after) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (cid, page_id, op, title, ns, reason, now, visible_after),
            )
            self._refresh_page_visible_after(page_id)
            return ApplyResult("held", page_id, cid, visible_after)

    def apply_move(
        self, page_id: int, new_title: str, new_ns: int, *, run_id: str | None = None,
        seq: int | None = None, source: str = "logevents", wiki_timestamp: str | None = None,
        edit_summary: str | None = None,
    ) -> ApplyResult:
        """Hold a rename (design 4.5). The target namespace must be ingested; a move
        out of scope is `apply_delete(..., reason='left_scope')`."""
        self._rule_for(new_ns)
        return self._hold_simple(
            page_id, "move", title=new_title, ns=new_ns, reason=None, run_id=run_id, seq=seq,
            source=source, wiki_timestamp=wiki_timestamp, edit_summary=edit_summary,
        )

    def apply_delete(
        self, page_id: int, *, reason: str = "deleted", run_id: str | None = None,
        seq: int | None = None, source: str = "logevents", wiki_timestamp: str | None = None,
        edit_summary: str | None = None,
    ) -> ApplyResult:
        """Hold a delete (or `left_scope`). The page keeps being served until visible_after."""
        if reason not in ("deleted", "left_scope"):
            raise ValueError(f"unknown delete reason {reason!r}")
        return self._hold_simple(
            page_id, "delete", title=None, ns=None, reason=reason, run_id=run_id, seq=seq,
            source=source, wiki_timestamp=wiki_timestamp, edit_summary=edit_summary,
        )

    def cancel_held(self, page_id: int, ops: Sequence[str] = ("delete",)) -> int:
        """Drop held changes of the given ops for a page (e.g. a held delete when the
        page reappears). Their changelog rows never became visible and are removed with
        them. Returns how many were cancelled."""
        if not ops:
            return 0
        marks = ",".join("?" for _ in ops)
        with self.transaction():
            ids = [
                r["change_id"]
                for r in self.conn.execute(
                    f"SELECT change_id FROM held_changes WHERE page_id = ? AND op IN ({marks})",
                    (page_id, *ops),
                ).fetchall()
            ]
            for cid in ids:
                self.conn.execute("DELETE FROM held_changes WHERE change_id = ?", (cid,))
                self.conn.execute("DELETE FROM changes WHERE id = ? AND state = 'held'", (cid,))
            if ids and self.conn.execute("SELECT 1 FROM pages WHERE page_id = ?", (page_id,)).fetchone():
                self._refresh_page_visible_after(page_id)
            return len(ids)

    def replace_redirects(self, rows: Iterable[Sequence[Any]], ns_ids: Sequence[int]) -> int:
        """Replace the redirect rows whose `from_ns` is in `ns_ids` with `rows`, each
        `(from_title, from_ns, to_title, to_ns)`. One transaction (re-entrant)."""
        marks = ",".join("?" for _ in ns_ids)
        n = 0
        with self.transaction():
            self.conn.execute(f"DELETE FROM redirects WHERE from_ns IN ({marks})", list(ns_ids))
            for ft, fns, tt, tns in rows:
                self.conn.execute(
                    "INSERT OR REPLACE INTO redirects(from_title, from_ns, from_page_id, to_title, to_ns) "
                    "VALUES (?,?,?,?,?)", (ft, fns, None, tt, tns),
                )
                n += 1
        return n

    def archive_served_revision(self, page_id: int) -> bool:
        """Copy the served body to `revision_archive` (design 7.3). Caller decides when
        (a cited page); returns False if the page has no served body."""
        with self.transaction():
            row = self.conn.execute(
                "SELECT revid, sha256, wikitext FROM pages WHERE page_id = ? AND state = 'live'", (page_id,)
            ).fetchone()
            if row is None or row["wikitext"] is None:
                return False
            self.conn.execute(
                "INSERT OR IGNORE INTO revision_archive(page_id, revid, sha256, wikitext, archived_utc) "
                "VALUES (?,?,?,?,?)",
                (page_id, row["revid"], row["sha256"], row["wikitext"], iso(self.now())),
            )
            return True

    # -- promotion ------------------------------------------------------------

    def promote_due(self, now: datetime | None = None) -> list[Promotion]:
        """Make every change whose `visible_after` has passed visible, oldest first.

        One transaction per change, so a failure leaves earlier promotions in place
        and the failing one held (and raises).
        """
        now_dt = now or self.now()
        now_s = iso(now_dt)
        due = [
            r["change_id"]
            for r in self.conn.execute(
                "SELECT change_id FROM held_changes WHERE visible_after <= ? ORDER BY seen_utc, change_id",
                (now_s,),
            ).fetchall()
        ]
        out: list[Promotion] = []
        for cid in due:
            with self.transaction():
                h = self.conn.execute("SELECT * FROM held_changes WHERE change_id = ?", (cid,)).fetchone()
                page = self.conn.execute("SELECT * FROM pages WHERE page_id = ?", (h["page_id"],)).fetchone()
                if page is None:
                    raise StoreError(f"held change {cid} refers to missing page {h['page_id']}")
                try:
                    self._apply_held(h, page, now_s)
                except sqlite3.IntegrityError as exc:
                    raise StoreError(f"promotion of change {cid} conflicts: {exc}") from exc
                self.conn.execute(
                    "UPDATE changes SET state='visible', made_visible_utc=? WHERE id=?", (now_s, cid)
                )
                self.conn.execute("DELETE FROM held_changes WHERE change_id = ?", (cid,))
                if self.conn.execute("SELECT 1 FROM pages WHERE page_id = ?", (h["page_id"],)).fetchone():
                    self._refresh_page_visible_after(h["page_id"])
                out.append(Promotion(cid, h["page_id"], h["op"], h["title"], now_s))
        return out

    def _apply_held(self, h: sqlite3.Row, page: sqlite3.Row, now_s: str) -> None:
        pid, op = h["page_id"], h["op"]
        if op in ("new", "edit", "restore"):
            if page["state"] != "pending" and normalize_title(page["title"]) != normalize_title(h["title"]):
                self.conn.execute(
                    "INSERT OR IGNORE INTO aliases(alias_title, page_id) VALUES (?, ?)", (page["title"], pid)
                )
                self.conn.execute(
                    "DELETE FROM aliases WHERE page_id = ? AND alias_title = ?", (pid, h["title"])
                )
            self.conn.execute(
                "UPDATE pages SET ns=?, title=?, revid=?, rev_timestamp=?, fetched_utc=?, byte_length=?, "
                "sha256=?, wikitext=?, game_version=?, is_current=?, kind=?, state='live', "
                "deleted_utc=NULL, reason=NULL WHERE page_id=?",
                (h["ns"], h["title"], h["revid"], h["rev_timestamp"], h["fetched_utc"], h["byte_length"],
                 h["sha256"], h["wikitext"], h["game_version"], h["is_current"], h["kind"], pid),
            )
            self._replace_chunks(pid, h["title"], json.loads(h["chunks_json"] or "[]"))
        elif op == "move":
            self.conn.execute(
                "INSERT OR IGNORE INTO aliases(alias_title, page_id) VALUES (?, ?)", (page["title"], pid)
            )
            self.conn.execute("DELETE FROM aliases WHERE page_id = ? AND alias_title = ?", (pid, h["title"]))
            self.conn.execute("UPDATE pages SET title=?, ns=? WHERE page_id=?", (h["title"], h["ns"], pid))
            self.conn.execute("UPDATE chunks_fts SET title=? WHERE rowid IN "
                              "(SELECT chunk_id FROM chunks WHERE page_id=?)", (h["title"], pid))
        elif op == "delete":
            others = self.conn.execute(
                "SELECT 1 FROM held_changes WHERE page_id = ? AND change_id != ?", (pid, h["change_id"])
            ).fetchone()
            self._replace_chunks(pid, page["title"], [])
            if page["state"] == "pending" and not others:
                self.conn.execute("DELETE FROM pages WHERE page_id = ?", (pid,))
            else:
                self.conn.execute(
                    "UPDATE pages SET state='deleted', deleted_utc=?, reason=?, wikitext=NULL, sha256=NULL "
                    "WHERE page_id=?", (now_s, h["reason"] or "deleted", pid),
                )
        else:  # pragma: no cover - the CHECK constraint forbids it
            raise StoreError(f"unknown held op {op!r}")

    # -- reads -----------------------------------------------------------------

    def held_change_count(self, page_id: int) -> int:
        return int(self._read("SELECT COUNT(*) FROM held_changes WHERE page_id = ?", (page_id,)).fetchone()[0])

    def _view(self, row: sqlite3.Row, *, resolved_from: str | None = None) -> dict[str, Any]:
        now = self.now()
        recent = False
        if row["rev_timestamp"]:
            recent = now - parse_iso(row["rev_timestamp"]) < timedelta(hours=RECENT_EDIT_HOURS)
        deleted = row["state"] == "deleted"
        return {
            "page_id": row["page_id"],
            "title": row["title"],
            "ns": row["ns"],
            "source": row["source"],
            "state": row["state"],
            "kind": row["kind"],
            "game_version": row["game_version"],
            "is_current": bool(row["is_current"]),
            "revid": row["revid"],
            "rev_timestamp": row["rev_timestamp"],
            "fetched_utc": row["fetched_utc"],
            "byte_length": row["byte_length"],
            "sha256": row["sha256"],
            "wikitext": None if deleted else row["wikitext"],
            "deleted_utc": row["deleted_utc"],
            "delete_reason": row["reason"],
            "resolved_from": resolved_from,
            "recent_edit": recent,
            "held_changes": self.held_change_count(row["page_id"]),
            "latest_revid": row["latest_revid"],
            "latest_seen_at": row["latest_seen_at"],
            "visible_after": row["visible_after"],
            "permalink": permalink(row["title"], row["revid"]) if row["revid"] else None,
            "history_url": history_url(row["title"]),
            "license": LICENSE,
            "wiki_note": WIKI_NOTE if row["is_current"] else None,
        }

    def get_page(
        self, title: str, *, ns: int = 0, include_legacy: bool = False, source: str = "dfwiki"
    ) -> dict[str, Any] | None:
        """One SERVED page by title, or None. Resolution order: exact live title, case-
        insensitive live title, alias (old title after a move), redirect, tombstone.
        Never returns a never-served (`pending`) page, and hides `is_current = 0` pages
        unless `include_legacy`. A tombstone comes back with `state='deleted'` and no text
        so the caller can say so instead of "no such page"."""
        t = normalize_title(title)
        if not t:
            raise ValueError("empty title")

        def visible(row: sqlite3.Row | None) -> sqlite3.Row | None:
            if row is None or (not row["is_current"] and not include_legacy):
                return None
            return row

        q = "SELECT * FROM pages WHERE source=? AND ns=? AND state='live' AND title"
        row = self._read(q + " = ?", (source, ns, t)).fetchone()
        if row is None:
            rows = self._read(q + " = ? COLLATE NOCASE", (source, ns, t)).fetchall()
            if len(rows) > 1:
                raise AmbiguousTitle(t, [r["title"] for r in rows])
            row = rows[0] if rows else None
        if row is not None:
            row = visible(row)
            return None if row is None else self._view(row)
        alias = self._read(
            "SELECT p.* FROM aliases a JOIN pages p ON p.page_id = a.page_id "
            "WHERE a.alias_title = ? COLLATE NOCASE AND p.state='live' AND p.source=?", (t, source),
        ).fetchall()
        if len(alias) == 1 and visible(alias[0]):
            return self._view(alias[0], resolved_from=t)
        red = self._read(
            "SELECT to_title, to_ns FROM redirects WHERE from_title = ? COLLATE NOCASE AND from_ns = ?", (t, ns)
        ).fetchone()
        if red is not None:
            if red["to_title"] is None:
                return None
            target = self._read(
                "SELECT * FROM pages WHERE source=? AND ns=? AND state='live' AND title = ? COLLATE NOCASE",
                (source, red["to_ns"] if red["to_ns"] is not None else ns, red["to_title"]),
            ).fetchone()
            target = visible(target)
            if target is not None:
                return self._view(target, resolved_from=t)
            return None
        tomb = self._read(
            "SELECT * FROM pages WHERE source=? AND ns=? AND state='deleted' AND title = ? COLLATE NOCASE",
            (source, ns, t),
        ).fetchone()
        tomb = visible(tomb)
        return None if tomb is None else self._view(tomb)

    def list_pages(
        self, *, prefix: str = "", limit: int = 100, offset: int = 0,
        kinds: Sequence[str] = ("article",), include_legacy: bool = False, source: str = "dfwiki",
    ) -> list[dict[str, Any]]:
        """Served live pages ordered by title, prefix-filtered, with provenance."""
        marks = ",".join("?" for _ in kinds)
        sql = (
            "SELECT page_id, title, ns, kind, revid, rev_timestamp, fetched_utc, game_version, is_current "
            f"FROM pages WHERE source=? AND state='live' AND kind IN ({marks}) "
            "AND title LIKE ? ESCAPE '\\' "
        )
        params: list[Any] = [source, *kinds, _like_prefix(normalize_title(prefix))]
        if not include_legacy:
            sql += "AND is_current = 1 "
        sql += "ORDER BY title COLLATE NOCASE LIMIT ? OFFSET ?"
        params += [int(limit), int(offset)]
        return [dict(r) for r in self._read(sql, params).fetchall()]

    def get_chunks(self, page_id: int) -> list[dict[str, Any]]:
        """Chunks of the SERVED revision of a live page, in order."""
        return [
            dict(r)
            for r in self._read(
                "SELECT c.ord, c.heading_path, c.text, c.char_count FROM chunks c "
                "JOIN pages p ON p.page_id = c.page_id WHERE c.page_id = ? AND p.state='live' "
                "ORDER BY c.ord", (page_id,),
            ).fetchall()
        ]

    def search(
        self, query: str, *, limit: int = 10, include_raw: bool = False,
        include_legacy: bool = False, excerpt_chars: int = 600, source: str = "dfwiki",
    ) -> list[dict[str, Any]]:
        """Ranked FTS5 search over served chunks. Every token must match (AND), the title is
        boosted (bm25 weights title 8, heading 3, text 1). Raises ValueError on a query with
        no searchable token, and `StoreLockedError` on a locked file: never an empty list
        standing in for a failure."""
        tokens = re.findall(r"\w+", query, re.UNICODE)
        if not tokens:
            raise ValueError("query has no searchable tokens")
        match = " ".join(f'"{tok}"' for tok in tokens)
        sql = (
            "SELECT c.chunk_id, c.page_id, c.ord, c.heading_path, substr(c.text, 1, ?) AS excerpt, "
            "p.title, p.ns, p.kind, p.revid, p.rev_timestamp, p.fetched_utc, p.game_version, p.is_current, "
            "bm25(chunks_fts, 8.0, 3.0, 1.0) AS rank "
            "FROM chunks_fts JOIN chunks c ON c.chunk_id = chunks_fts.rowid "
            "JOIN pages p ON p.page_id = c.page_id "
            "WHERE chunks_fts MATCH ? AND p.state = 'live' AND p.source = ? "
        )
        params: list[Any] = [int(excerpt_chars), match, source]
        if not include_raw:
            sql += "AND p.kind = 'article' "
        if not include_legacy:
            sql += "AND p.is_current = 1 "
        sql += "ORDER BY rank LIMIT ?"
        params.append(int(limit))
        out = []
        for r in self._read(sql, params).fetchall():
            d = dict(r)
            d["permalink"] = permalink(d["title"], d["revid"])
            d["license"] = LICENSE
            d["held_changes"] = self.held_change_count(d["page_id"])
            out.append(d)
        return out

    def staleness(
        self, *, fresh_hours: float = 24.0, very_stale_days: float = 7.0, now: datetime | None = None,
    ) -> dict[str, Any]:
        """Freshness computed at read time from timestamps (design 5.2). The reference time
        is the later of the last successful refresh and the last full pull; nothing stored
        as a flag, so a dead timer reads the same as a failing one."""
        now = now or self.now()
        ok = self.get_meta("last_refresh_ok_utc")
        pull = self.get_meta("last_full_pull_utc")
        refs = [parse_iso(x) for x in (ok, pull) if x]
        reasons: list[str] = []
        if not refs:
            status, age_h = "very_stale", None
            reasons.append("never_pulled")
        else:
            age_h = (now - max(refs)).total_seconds() / 3600.0
            if age_h <= fresh_hours:
                status = "fresh"
            elif age_h <= very_stale_days * 24:
                status = "stale"
            else:
                status = "very_stale"
        vs = self.get_meta("version_status")
        if vs in ("wiki_ahead", "wiki_behind"):
            reasons.append("version_mismatch")
        last_status = self.get_meta("last_run_status")
        err = self.get_meta("last_error_class")
        if err in ("blocked", "budget"):
            reasons.append(err)
        elif err:
            reasons.append("last_run_failed")
        elif last_status in ("failed",):
            reasons.append("last_run_failed")
        overdue = int(
            self._read("SELECT COUNT(*) FROM held_changes WHERE visible_after <= ?", (iso(now),)).fetchone()[0]
        )
        return {
            "status": status,
            "age_hours": age_h,
            "last_refresh_ok_utc": ok,
            "last_full_pull_utc": pull,
            "last_refresh_attempt_utc": self.get_meta("last_refresh_attempt_utc"),
            "last_error_class": err,
            "version_status": vs,
            "reasons": reasons,
            "promotion_overdue": overdue,
        }

    def changes_since(
        self, *, since_utc: str | None = None, title: str | None = None, kind: str | None = None,
        state: str | None = None, limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Changelog rows (held and visible), newest first. Edit summaries are UNTRUSTED text."""
        sql, params = "SELECT * FROM changes WHERE 1=1", []
        if since_utc:
            sql += " AND detected_utc >= ?"
            params.append(since_utc)
        if title:
            sql += " AND (title = ? COLLATE NOCASE OR old_title = ? COLLATE NOCASE OR new_title = ? COLLATE NOCASE)"
            params += [normalize_title(title)] * 3
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        if state:
            sql += " AND state = ?"
            params.append(state)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(int(limit))
        out = []
        for r in self._read(sql, params).fetchall():
            d = dict(r)
            d["edit_summary_untrusted"] = True
            out.append(d)
        return out

    def counts(self) -> dict[str, int]:
        q = lambda s: int(self._read(s).fetchone()[0])  # noqa: E731
        return {
            "pages_live": q("SELECT COUNT(*) FROM pages WHERE state='live'"),
            "pages_pending": q("SELECT COUNT(*) FROM pages WHERE state='pending'"),
            "pages_deleted": q("SELECT COUNT(*) FROM pages WHERE state='deleted'"),
            "chunks": q("SELECT COUNT(*) FROM chunks"),
            "fts_rows": q("SELECT COUNT(*) FROM chunks_fts"),
            "held": q("SELECT COUNT(*) FROM held_changes"),
        }


def _like_prefix(prefix: str) -> str:
    esc = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return esc + "%"


# ---- atomic promote of a staged full pull (design 5.1) ------------------------


def promote_staged(
    staged: str | os.PathLike[str],
    live: str | os.PathLike[str],
    *,
    expected_page_count: int,
    probe_words: Sequence[str],
    tolerance: float = 0.01,
    min_free_bytes: int = MIN_FREE_BYTES_DEFAULT,
    free_bytes_fn: Callable[[str], int] | None = None,
    vacuum: bool = True,
    now: datetime | None = None,
) -> PromoteReport:
    """Verify a staged database and swap it in with `os.replace`. All-or-nothing.

    Checks (any failure raises `PromoteError` listing every reason, and touches
    neither file): the schema version and FTS5; `PRAGMA integrity_check` ok; live
    page count within `tolerance` of `expected_page_count`; no live page with a NULL
    body; chunk and FTS row counts equal; every `probe_words` word (give three) returns
    an FTS hit; free space at the destination of at least `min_free_bytes`. On success
    writes `<live>.manifest.json`, moves any existing live file to `<live>.prev`, and
    puts the staged file in place; if the second rename fails the previous file is
    restored. `expected_page_count` and `probe_words` are required so a caller cannot
    skip the check.
    """
    staged_p, live_p = Path(staged), Path(live)
    if not probe_words:
        raise ValueError("probe_words must name at least one known-good word (design says three)")
    if not staged_p.exists():
        raise PromoteError([f"staged file missing: {staged_p}"])
    reasons: list[str] = []
    free = (free_bytes_fn or (lambda p: shutil.disk_usage(p).free))(str(live_p.parent))
    if free < min_free_bytes:
        reasons.append(f"free space {free} bytes is under the {min_free_bytes} minimum")
    if reasons:  # abort before opening or vacuuming anything
        raise PromoteError(reasons)

    conn = sqlite3.connect(str(staged_p), isolation_level=None)
    conn.row_factory = sqlite3.Row
    page_count = chunk_count = 0
    try:
        conn.execute("PRAGMA schema_version").fetchone()  # fails fast on a non-database file
        schema.check_fts5(conn)
        version = schema.read_schema_version(conn)
        if version != schema.SCHEMA_VERSION:
            reasons.append(f"schema version {version}, expected {schema.SCHEMA_VERSION}")
        else:
            if vacuum:
                conn.execute("VACUUM")
            integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if integ != "ok":
                reasons.append(f"integrity_check: {integ}")
            page_count = conn.execute("SELECT COUNT(*) FROM pages WHERE state='live'").fetchone()[0]
            if expected_page_count <= 0 or abs(page_count - expected_page_count) > tolerance * expected_page_count:
                reasons.append(
                    f"live page count {page_count} not within {tolerance:.0%} of expected {expected_page_count}"
                )
            nulls = conn.execute("SELECT COUNT(*) FROM pages WHERE state='live' AND wikitext IS NULL").fetchone()[0]
            if nulls:
                reasons.append(f"{nulls} live pages have a NULL body")
            chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            fts_count = conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
            if chunk_count != fts_count:
                reasons.append(f"chunks {chunk_count} != fts rows {fts_count}")
            for word in probe_words:
                tok = re.findall(r"\w+", word, re.UNICODE)
                hit = conn.execute(
                    "SELECT 1 FROM chunks_fts WHERE chunks_fts MATCH ? LIMIT 1", (f'"{tok[0]}"' if tok else '""',)
                ).fetchone() if tok else None
                if hit is None:
                    reasons.append(f"FTS probe word {word!r} returned no rows")
    except schema.Fts5UnavailableError:
        raise
    except sqlite3.DatabaseError as exc:
        reasons.append(f"staged file is not a readable database: {exc}")
    finally:
        conn.close()
    if reasons:
        raise PromoteError(reasons)

    digest = hashlib.sha256(staged_p.read_bytes()).hexdigest()
    manifest = {
        "promoted_utc": iso(now or _utcnow()),
        "schema_version": schema.SCHEMA_VERSION,
        "page_count": page_count,
        "chunk_count": chunk_count,
        "expected_page_count": expected_page_count,
        "sha256": digest,
        "probe_words": list(probe_words),
    }
    manifest_tmp = Path(str(live_p) + ".manifest.json.tmp")
    manifest_final = Path(str(live_p) + ".manifest.json")
    manifest_tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    prev = Path(str(live_p) + ".prev")
    moved_prev = False
    try:
        if live_p.exists():
            os.replace(live_p, prev)
            moved_prev = True
        os.replace(staged_p, live_p)
    except OSError as exc:
        if moved_prev and not live_p.exists():
            os.replace(prev, live_p)
        manifest_tmp.unlink(missing_ok=True)
        raise PromoteError([f"swap failed, previous database restored: {exc}"]) from exc
    os.replace(manifest_tmp, manifest_final)
    return PromoteReport(str(live_p), str(prev) if moved_prev else None, str(manifest_final),
                         page_count, chunk_count, digest)
