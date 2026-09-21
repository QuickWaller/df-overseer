"""The gotcha store: SQLite, append-only, one database per fort.

Backs `gotchas.get` / `gotchas.write` (`dfmcp/gotchas_tools.py`) and the
gotcha titles every DFHack-backed tool result carries
(`dfmcp/tool_guidance.py`). Design settled in `docs/BUILDING-TOOL.md`
(decisions 7 and 8, contract C3); this module is the storage and the
write-time validation, the same job `dfqueue/store.py` + `dfqueue/schema.py`
do for the proposal queue, and it follows the same pattern.

## Why a module in `dfmcp/`, and not `dfqueue/` or a new top-level package

The handoff said to keep it out of `dfqueue/`: a gotcha is not a proposal,
has no prediction, no ruling and no grader, and stuffing a second record kind
into the queue's tables would force its schema-version and validator to carry
both. A new top-level package (like `dfseries/`) is what a store used by
several callers earns; this one has exactly one caller, the MCP server, and
the streams that own the other top-level packages are not this one. So it is
two flat modules beside the tools that use it. If a second consumer appears
(a learning-role script that promotes gotchas), promoting this file to a
package is a move, not a redesign: nothing here imports `mcp`.

## Append-only

Nothing is ever edited or deleted. A new gotcha is an `entries` row; an
outcome ("worked" / "did_not_work") is an `outcomes` row on it; a status
change (`proposed` to `accepted` or `rejected`, who does that is an open,
parked question in the design note) is a `status_history` row plus an update
of the entry's `status` column, in one transaction. The `status` column is
the only mutable field anywhere, and `status_history` is its audit trail. No
tool exposes `set_status`: agents cannot accept their own gotchas, and
nothing in this repo does yet.

## Fails loudly

Reads and writes both refuse (`GotchaStoreError`) when the database file is
absent or is not a valid store of this schema version. `sqlite3.connect`
happily creates an empty file at any path, which would read as "this tool has
no gotchas" instead of "the store is missing"; the same reasoning
`dfmcp/series_tools.py` gives for `_require_db`. Creation is an explicit
act: `python -m dfmcp.gotchas_store init PATH`, run once at deploy time.

## Writes are serialised across processes

`BEGIN IMMEDIATE` takes the database write lock before the id is computed, so
two writers cannot both see the same "next id" (the race `dfqueue`'s docstring
documents for its COUNT-based ids). Ids are `<list>-NNNN` (`gotcha-0001`,
`unexplained-0002`, `vent-0003`): a per-list counter that reads well in a
prompt, chosen by the store, never by the caller.
"""

from __future__ import annotations

import difflib
import json
import re
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence

SCHEMA_VERSION = 1

# --------------------------------------------------------------------------
# Closed vocabularies (contract C3)
# --------------------------------------------------------------------------

LIST_GOTCHA = "gotcha"
LIST_UNEXPLAINED = "unexplained"
LIST_VENT = "vent"
LISTS = (LIST_GOTCHA, LIST_UNEXPLAINED, LIST_VENT)

STATUS_PROPOSED = "proposed"
STATUS_ACCEPTED = "accepted"
STATUS_REJECTED = "rejected"
STATUSES = (STATUS_PROPOSED, STATUS_ACCEPTED, STATUS_REJECTED)

RESULT_WORKED = "worked"
RESULT_DID_NOT_WORK = "did_not_work"
RESULTS = (RESULT_WORKED, RESULT_DID_NOT_WORK)

# --------------------------------------------------------------------------
# Write-time limits. Every number here is a judgement, not a measurement;
# they are constants so a test (and a later review) can see and change them
# in one place.
# --------------------------------------------------------------------------

TITLE_MIN_CHARS = 12
TITLE_MAX_CHARS = 120
BODY_MIN_CHARS = 20
BODY_MAX_CHARS = 1200
EXCERPT_MAX_CHARS = 300
NOTE_MAX_CHARS = 300
RUN_ID_MAX_CHARS = 200
KIND_MAX_CHARS = 60

#: New entries (gotcha, unexplained or vent) one run may write.
NEW_ENTRIES_PER_RUN = 3
#: Outcomes one run may record.
OUTCOMES_PER_RUN = 10

#: A candidate is a near-duplicate of an existing entry (same tool, same
#: list, any status including rejected) when either ratio reaches its bound.
TITLE_DUP_JACCARD = 0.75
TITLE_DUP_RATIO = 0.85
BODY_DUP_RATIO = 0.85

_KIND_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TITLE_FORBIDDEN_RE = re.compile(r"[<>\r\n\t\x00-\x1f\x7f]")
_WORD_RE = re.compile(r"[a-z0-9]+")


class GotchaStoreError(Exception):
    """A gotcha write is refused, or the store is absent or malformed.
    `dfmcp.gotchas_tools` turns it into an `isError` tool result carrying
    this message; `dfmcp.tool_guidance` turns it into an explicit
    `gotchas_unavailable` note on a tool result. Never swallowed into an
    empty list."""


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS entries (
    id TEXT PRIMARY KEY,
    tool TEXT NOT NULL,
    kind TEXT,
    list TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    written_by_role TEXT NOT NULL,
    run_id TEXT NOT NULL,
    call_excerpt TEXT
);
CREATE INDEX IF NOT EXISTS idx_entries_tool ON entries(tool, list, status);
CREATE INDEX IF NOT EXISTS idx_entries_run ON entries(run_id);

CREATE TABLE IF NOT EXISTS outcomes (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id TEXT NOT NULL REFERENCES entries(id),
    at TEXT NOT NULL,
    role TEXT NOT NULL,
    run_id TEXT NOT NULL,
    result TEXT NOT NULL,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_outcomes_entry ON outcomes(entry_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_run ON outcomes(run_id);

CREATE TABLE IF NOT EXISTS status_history (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id TEXT NOT NULL REFERENCES entries(id),
    at TEXT NOT NULL,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    by TEXT NOT NULL,
    note TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# Opening
# --------------------------------------------------------------------------


def init_store(path: str | Path) -> None:
    """Create the database and schema at `path`. The parent directory must
    already exist (a missing directory is a deploy mistake to surface, not to
    paper over with `mkdir -p`). Idempotent on a valid store; refuses a file
    that already exists but is not a store of this schema version."""
    p = Path(path)
    if not p.parent.is_dir():
        raise GotchaStoreError(f"gotcha store: directory {p.parent} does not exist; create it first")
    existed = p.is_file()
    conn = sqlite3.connect(p)
    try:
        conn.row_factory = sqlite3.Row
        if existed:
            try:
                _check_schema(conn, p)
            except GotchaStoreError:
                raise
            return
        conn.executescript(_SCHEMA_SQL)
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()
    except sqlite3.Error as exc:
        raise GotchaStoreError(f"gotcha store: cannot initialise {p}: {exc}") from exc
    finally:
        conn.close()


def _check_schema(conn: sqlite3.Connection, path: Path) -> None:
    try:
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        conn.execute("SELECT 1 FROM entries LIMIT 1").fetchall()
        conn.execute("SELECT 1 FROM outcomes LIMIT 1").fetchall()
        conn.execute("SELECT 1 FROM status_history LIMIT 1").fetchall()
    except sqlite3.DatabaseError as exc:
        raise GotchaStoreError(
            f"gotcha store at {path} is malformed (not a valid store of this schema): {exc}"
        ) from exc
    if row is None or row[0] != SCHEMA_VERSION:
        found = None if row is None else row[0]
        raise GotchaStoreError(
            f"gotcha store at {path} is schema_version {found}, this code is {SCHEMA_VERSION}"
        )


@contextmanager
def _connect(path: str | Path) -> Iterator[sqlite3.Connection]:
    p = Path(path)
    if not p.is_file():
        raise GotchaStoreError(
            f"gotcha store not found at {p} -- create it once with "
            "`python -m dfmcp.gotchas_store init PATH`, or set MCP_SERVER_GOTCHAS_DB to the "
            "real location. Refusing to open (sqlite would silently create an empty database "
            "that reads as 'no gotchas exist' instead of 'the store is missing')."
        )
    try:
        conn = sqlite3.connect(p, timeout=10, isolation_level=None)
    except sqlite3.Error as exc:
        raise GotchaStoreError(f"gotcha store at {p} cannot be opened: {exc}") from exc
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        _check_schema(conn, p)
        yield conn
    finally:
        conn.close()


def check_store(path: str | Path) -> None:
    """Raise `GotchaStoreError` unless `path` is a valid store. Used at server
    startup so a missing or malformed store stops the deploy loudly."""
    with _connect(path):
        pass


# --------------------------------------------------------------------------
# Validation (pure; no database)
# --------------------------------------------------------------------------


def _normalise(text: str) -> List[str]:
    return _WORD_RE.findall(text.lower())


def title_problems(title: Any) -> List[str]:
    """Why `title` is not an acceptable condition-titled gotcha title, or [].

    The user's rule (`docs/BUILDING-TOOL.md`): the title must state the
    condition, e.g. "placing a workshop in a desert biome: <hazard>", so an
    agent can tell from the title alone whether it applies. Mechanically that
    is `<condition>: <hazard>` on one line, both halves present, the
    condition at least two words, the whole thing short. This cannot judge
    whether the condition is a *good* one; it refuses the shapes that
    plainly are not (a bare label, a sentence with no condition, a paragraph).
    """
    problems: List[str] = []
    if not isinstance(title, str):
        return ["title must be a string"]
    stripped = title.strip()
    if len(stripped) < TITLE_MIN_CHARS:
        problems.append(f"title is too short ({len(stripped)} chars, minimum {TITLE_MIN_CHARS})")
    if len(stripped) > TITLE_MAX_CHARS:
        problems.append(
            f"title is too long ({len(stripped)} chars, maximum {TITLE_MAX_CHARS}): a title is a "
            "few-word condition plus the hazard, the detail belongs in the body"
        )
    if _TITLE_FORBIDDEN_RE.search(title):
        problems.append("title must be one plain line: no newlines, tabs, control characters, '<' or '>'")
    if ":" not in stripped:
        problems.append(
            "title must state the condition it applies under, in the form "
            "'<condition>: <hazard>' (for example 'placing a workshop in a desert biome: "
            "<what goes wrong>'), so a reader can tell from the title alone whether it applies"
        )
    else:
        condition, _, hazard = stripped.partition(":")
        if len(condition.split()) < 2:
            problems.append(
                "the part of the title before ':' must describe a condition in at least two words, "
                f"got {condition.strip()!r}"
            )
        if len(hazard.strip()) < 3:
            problems.append("the part of the title after ':' must state the hazard")
    return problems


def _text_problems(name: str, value: Any, minimum: int, maximum: int) -> List[str]:
    if not isinstance(value, str):
        return [f"{name} must be a string"]
    problems = []
    if len(value.strip()) < minimum:
        problems.append(f"{name} is too short ({len(value.strip())} chars, minimum {minimum})")
    if len(value) > maximum:
        problems.append(f"{name} is too long ({len(value)} chars, maximum {maximum})")
    if _CONTROL_RE.search(value):
        problems.append(f"{name} contains control characters")
    return problems


def validate_new_entry(record: Mapping[str, Any], known_tools: Iterable[str]) -> List[str]:
    """Every problem with a would-be new entry, or []. `record` carries the
    caller-supplied fields (`tool`, `kind`, `list`, `title`, `body`,
    `call_excerpt`) plus the server-stamped `written_by_role` and `run_id`."""
    problems: List[str] = []
    tool = record.get("tool")
    if not isinstance(tool, str) or not tool:
        problems.append("tool is required")
    elif tool not in set(known_tools):
        problems.append(
            f"tool {tool!r} is not a tool in this server's registry; a gotcha is written about a "
            "real tool id (see your tool list)"
        )
    kind = record.get("kind")
    if kind is not None:
        if not isinstance(kind, str) or not _KIND_RE.match(kind) or len(kind) > KIND_MAX_CHARS:
            problems.append(
                "kind, when given, must be a kind token (letters, digits, '_' or '-', starting "
                f"with a letter, at most {KIND_MAX_CHARS} chars), not a display label"
            )
    if record.get("list") not in LISTS:
        problems.append(f"list must be one of {list(LISTS)}, got {record.get('list')!r}")
    problems.extend(title_problems(record.get("title")))
    problems.extend(_text_problems("body", record.get("body"), BODY_MIN_CHARS, BODY_MAX_CHARS))
    excerpt = record.get("call_excerpt")
    if excerpt is not None:
        problems.extend(_text_problems("call_excerpt", excerpt, 0, EXCERPT_MAX_CHARS))
    for name in ("written_by_role", "run_id"):
        value = record.get(name)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{name} must be a non-empty string (stamped by the server)")
        elif len(value) > RUN_ID_MAX_CHARS:
            problems.append(f"{name} is too long")
    return problems


def near_duplicate_reason(candidate: Mapping[str, Any], existing: Mapping[str, Any]) -> Optional[str]:
    """Why `candidate` is a near-duplicate of `existing`, or None."""
    ct, et = _normalise(candidate["title"]), _normalise(existing["title"])
    if ct and ct == et:
        return "its title is identical (ignoring case and punctuation)"
    cs, es = set(ct), set(et)
    if cs and es:
        jaccard = len(cs & es) / len(cs | es)
        if jaccard >= TITLE_DUP_JACCARD:
            return f"its title shares {jaccard:.0%} of its words"
    if difflib.SequenceMatcher(None, " ".join(ct), " ".join(et)).ratio() >= TITLE_DUP_RATIO:
        return "its title is nearly the same text"
    cb, eb = " ".join(_normalise(candidate["body"])), " ".join(_normalise(existing["body"]))
    if difflib.SequenceMatcher(None, cb, eb).ratio() >= BODY_DUP_RATIO:
        return "its body is nearly the same text"
    return None


# --------------------------------------------------------------------------
# Rows to records (contract C3)
# --------------------------------------------------------------------------


def _outcomes_for(conn: sqlite3.Connection, entry_id: str) -> List[dict]:
    rows = conn.execute(
        "SELECT at, role, run_id, result, note FROM outcomes WHERE entry_id = ? ORDER BY seq ASC",
        (entry_id,),
    ).fetchall()
    return [
        {"at": r["at"], "role": r["role"], "run_id": r["run_id"], "result": r["result"], "note": r["note"]}
        for r in rows
    ]


def _record(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "tool": row["tool"],
        "kind": row["kind"],
        "list": row["list"],
        "title": row["title"],
        "body": row["body"],
        "status": row["status"],
        "created_at": row["created_at"],
        "written_by_role": row["written_by_role"],
        "run_id": row["run_id"],
        "call_excerpt": row["call_excerpt"],
        "outcomes": _outcomes_for(conn, row["id"]),
    }


_ENTRY_COLUMNS = (
    "id, tool, kind, list, title, body, status, created_at, written_by_role, run_id, call_excerpt"
)


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------


def get_entry(path: str | Path, entry_id: str) -> Optional[dict]:
    with _connect(path) as conn:
        row = conn.execute(f"SELECT {_ENTRY_COLUMNS} FROM entries WHERE id = ?", (entry_id,)).fetchone()
        return _record(conn, row) if row is not None else None


def entries_for_tool(
    path: str | Path,
    tool: str,
    *,
    kind: Optional[str] = None,
    lists: Optional[Sequence[str]] = None,
    statuses: Optional[Sequence[str]] = None,
    with_outcomes: bool = True,
) -> List[dict]:
    """A tool's entries, oldest first. `kind` given: entries for that kind
    **and** tool-wide entries (`kind` null), since a tool-wide gotcha applies
    to every kind. `kind` omitted: every entry for the tool, kind-specific
    ones included."""
    query = f"SELECT {_ENTRY_COLUMNS} FROM entries WHERE tool = ?"
    params: list = [tool]
    if kind is not None:
        query += " AND (kind IS NULL OR kind = ?)"
        params.append(kind)
    if lists:
        query += f" AND list IN ({','.join('?' * len(lists))})"
        params.extend(lists)
    if statuses:
        query += f" AND status IN ({','.join('?' * len(statuses))})"
        params.extend(statuses)
    query += " ORDER BY rowid ASC"
    with _connect(path) as conn:
        rows = conn.execute(query, params).fetchall()
        if with_outcomes:
            return [_record(conn, r) for r in rows]
        return [{**_record_no_outcomes(r), "outcomes": []} for r in rows]


def _record_no_outcomes(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}


def outcome_counts(path: str | Path, entry_ids: Sequence[str]) -> Dict[str, Dict[str, int]]:
    """{entry_id: {"worked": n, "did_not_work": m}} for every id asked about,
    zeros included, so a caller never mistakes a missing key for "unknown"."""
    counts = {i: {RESULT_WORKED: 0, RESULT_DID_NOT_WORK: 0} for i in entry_ids}
    if not entry_ids:
        return counts
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT entry_id, result, COUNT(*) AS n FROM outcomes "
            f"WHERE entry_id IN ({','.join('?' * len(entry_ids))}) GROUP BY entry_id, result",
            list(entry_ids),
        ).fetchall()
    for r in rows:
        counts[r["entry_id"]][r["result"]] = r["n"]
    return counts


def tool_index(path: str | Path) -> Dict[str, Dict[str, Dict[str, int]]]:
    """{tool: {list: {status: count}}} for every tool that has at least one
    entry. A tool absent here has none (or is not a real tool: the caller
    checks that separately)."""
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT tool, list, status, COUNT(*) AS n FROM entries GROUP BY tool, list, status"
        ).fetchall()
    index: Dict[str, Dict[str, Dict[str, int]]] = {}
    for r in rows:
        index.setdefault(r["tool"], {}).setdefault(r["list"], {})[r["status"]] = r["n"]
    return index


# --------------------------------------------------------------------------
# Writes
# --------------------------------------------------------------------------


def _next_id(conn: sqlite3.Connection, list_name: str) -> str:
    prefix = f"{list_name}-"
    rows = conn.execute("SELECT id FROM entries WHERE list = ?", (list_name,)).fetchall()
    highest = 0
    for r in rows:
        tail = r["id"][len(prefix):]
        if tail.isdigit():
            highest = max(highest, int(tail))
    return f"{prefix}{highest + 1:04d}"


def add_entry(
    path: str | Path,
    record: Mapping[str, Any],
    *,
    known_tools: Iterable[str],
    max_new_per_run: int = NEW_ENTRIES_PER_RUN,
) -> dict:
    """Validate and append one new entry, always `proposed`, with a store-chosen
    id and a store-chosen timestamp. Refuses with every problem listed and
    writes nothing when the record is malformed, a near-duplicate of an
    existing entry for the same tool and list (rejected ones included, so a
    rejected gotcha cannot simply be re-proposed), or over the per-run cap.
    Returns the record as written."""
    problems = validate_new_entry(record, known_tools)
    if problems:
        raise GotchaStoreError("refusing to write an invalid gotcha:\n  " + "\n  ".join(problems))

    with _connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            written = conn.execute(
                "SELECT COUNT(*) AS n FROM entries WHERE run_id = ?", (record["run_id"],)
            ).fetchone()["n"]
            if written >= max_new_per_run:
                raise GotchaStoreError(
                    f"refusing to write: this run has already written {written} entries and the "
                    f"per-run cap is {max_new_per_run}. Keep the rest for a later run, or record "
                    "an outcome on an existing entry instead (pass its id)."
                )
            same = conn.execute(
                f"SELECT {_ENTRY_COLUMNS} FROM entries WHERE tool = ? AND list = ?",
                (record["tool"], record["list"]),
            ).fetchall()
            for row in same:
                reason = near_duplicate_reason(record, row)
                if reason:
                    raise GotchaStoreError(
                        f"refusing to write a near-duplicate of {row['id']} ({row['status']}): "
                        f"{reason}. If that entry applies, record an outcome on it by passing its "
                        "id instead of writing a new one."
                    )
            new_id = _next_id(conn, record["list"])
            created = _now()
            conn.execute(
                "INSERT INTO entries (id, tool, kind, list, title, body, status, created_at, "
                "written_by_role, run_id, call_excerpt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id, record["tool"], record.get("kind"), record["list"],
                    record["title"].strip(), record["body"], STATUS_PROPOSED, created,
                    record["written_by_role"], record["run_id"], record.get("call_excerpt"),
                ),
            )
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        row = conn.execute(f"SELECT {_ENTRY_COLUMNS} FROM entries WHERE id = ?", (new_id,)).fetchone()
        return _record(conn, row)


def add_outcome(
    path: str | Path,
    entry_id: str,
    *,
    result: Any,
    note: Any,
    role: str,
    run_id: str,
    max_per_run: int = OUTCOMES_PER_RUN,
) -> dict:
    """Append one outcome to an existing entry; never overwrites, never
    edits. Refused for an unknown id, an entry that is not a `gotcha` (the
    experiment protocol is for gotchas), a `rejected` entry, a second outcome
    from the same run on the same entry, or a run over its outcome cap.
    Returns the entry as it stands after the append."""
    problems: List[str] = []
    if result not in RESULTS:
        problems.append(f"result must be one of {list(RESULTS)}, got {result!r}")
    if note is not None:
        problems.extend(_text_problems("note", note, 0, NOTE_MAX_CHARS))
    for name, value in (("role", role), ("run_id", run_id)):
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{name} must be a non-empty string (stamped by the server)")
    if problems:
        raise GotchaStoreError("refusing to record an invalid outcome:\n  " + "\n  ".join(problems))

    with _connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(f"SELECT {_ENTRY_COLUMNS} FROM entries WHERE id = ?", (entry_id,)).fetchone()
            if row is None:
                raise GotchaStoreError(f"no gotcha entry with id {entry_id!r}")
            if row["list"] != LIST_GOTCHA:
                raise GotchaStoreError(
                    f"{entry_id} is in the {row['list']!r} list; outcomes are recorded only on "
                    "gotchas (the try-it-and-mark-it protocol), not on unexplained errors or vents"
                )
            if row["status"] == STATUS_REJECTED:
                raise GotchaStoreError(f"{entry_id} was rejected; outcomes are no longer recorded on it")
            already = conn.execute(
                "SELECT 1 FROM outcomes WHERE entry_id = ? AND run_id = ?", (entry_id, run_id)
            ).fetchone()
            if already is not None:
                raise GotchaStoreError(
                    f"this run has already recorded an outcome on {entry_id}; one per run per entry"
                )
            used = conn.execute(
                "SELECT COUNT(*) AS n FROM outcomes WHERE run_id = ?", (run_id,)
            ).fetchone()["n"]
            if used >= max_per_run:
                raise GotchaStoreError(
                    f"this run has already recorded {used} outcomes; the per-run cap is {max_per_run}"
                )
            conn.execute(
                "INSERT INTO outcomes (entry_id, at, role, run_id, result, note) VALUES (?, ?, ?, ?, ?, ?)",
                (entry_id, _now(), role, run_id, result, note),
            )
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        return _record(conn, row)


def set_status(path: str | Path, entry_id: str, to_status: str, *, by: str, note: Optional[str] = None) -> dict:
    """Change an entry's status, with an audit row. **Not exposed as a tool**:
    who may accept a gotcha is an open, parked design question. This is the
    one call a maintainer or a later learning-role script uses."""
    if to_status not in STATUSES:
        raise GotchaStoreError(f"status must be one of {list(STATUSES)}, got {to_status!r}")
    with _connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(f"SELECT {_ENTRY_COLUMNS} FROM entries WHERE id = ?", (entry_id,)).fetchone()
            if row is None:
                raise GotchaStoreError(f"no gotcha entry with id {entry_id!r}")
            conn.execute("UPDATE entries SET status = ? WHERE id = ?", (to_status, entry_id))
            conn.execute(
                "INSERT INTO status_history (entry_id, at, from_status, to_status, by, note) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (entry_id, _now(), row["status"], to_status, by, note),
            )
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        row = conn.execute(f"SELECT {_ENTRY_COLUMNS} FROM entries WHERE id = ?", (entry_id,)).fetchone()
        return _record(conn, row)


def export_jsonl(path: str | Path, out_dir: str | Path) -> None:
    """Deterministic dump to `out_dir/gotchas.jsonl`, one entry per line in id
    order with its outcomes, git-trackable (accepted entries are committed to
    the repo). Same purpose as `dfqueue.store.export_jsonl`."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with _connect(path) as conn:
        rows = conn.execute(f"SELECT {_ENTRY_COLUMNS} FROM entries ORDER BY id ASC").fetchall()
        records = [_record(conn, r) for r in rows]
    with (out / "gotchas.jsonl").open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")


def _main(argv: Sequence[str]) -> int:
    usage = "usage: python -m dfmcp.gotchas_store init PATH | export PATH OUT_DIR"
    if len(argv) >= 2 and argv[0] == "init" and len(argv) == 2:
        init_store(argv[1])
        print(f"gotcha store ready at {argv[1]}")
        return 0
    if len(argv) == 3 and argv[0] == "export":
        export_jsonl(argv[1], argv[2])
        print(f"exported to {argv[2]}")
        return 0
    print(usage, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
