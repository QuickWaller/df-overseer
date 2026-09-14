"""Reading and (append-only) writing the proposal queue: SQLite, one database
per fort.

Reverses part of the 2026-08-27 no-database call (`decisions/DECISIONS.md`)
for **live operational data only** — the fort ledger and the prediction log
stay JSONL, unchanged. The reversal is scoped to exactly the problem JSONL
doesn't solve here: `handoffs/2026-09-15-live-signals-sqlite.md` needs
concurrent writers (dfmcp, eventually, alongside this queue) and two real
queries (the latest N records for a feed, and every pending prediction whose
`due_game_tick` has arrived) that a full-file JSONL scan answers correctly
but not cheaply once the file is large and written from more than one
process. `export_jsonl()` below keeps the git-trackable, `cat`-able,
public-report-friendly form the 2026-08-27 decision cared about — it is
regenerated from SQLite, not hand-maintained.

One write path, deliberately, same as the JSONL version: `append()`. A
`ruling` is a new append that refers back to the `proposal` it decides, never
an edit of that proposal — nothing already written ever changes except a
prediction's own grading columns (`grade_due` in `grade.py`), and those are
`DERIVED`/`MECHANICAL` bookkeeping, never a record's own `payload`.

## Two tables

- `records` — one row per queue record (`proposal`/`pass`/`ruling`), keyed by
  the record's own string `id` (`"proposal-0001"`, matching the old JSONL
  scheme's `_next_id`). `payload` carries the full validated record as JSON,
  so nothing here needs its own copy of every field `schema.py` already
  knows about.
- `predictions` — one row per **proposal's** prediction (never a `pass` or
  `ruling`), `record_id` referencing `records.id`. Inserted in the *same*
  transaction as its proposal's `records` row: `append()` refuses to leave
  one without the other, proven in `dfqueue/tests/test_store.py` by
  simulating a failure between the two inserts.

## Atomicity

Every write in this module happens inside a `with conn:` block, which
Python's `sqlite3` module commits on success and rolls back on any
exception — including one raised by a monkeypatched internal function in a
test, not just a real database error. `append()` performs all of its
validation *before* opening that block, so a refused record still writes
nothing to either table, matching the JSONL version's contract exactly.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from learning.predictions.schema import PENDING

from .schema import ACCEPT, PROPOSAL, REJECT, RULING, fort_name, validate

#: A ruling's `decision` values that close a proposal for good. `defer`
#: ("decide later") is deliberately excluded: a proposal ruled only `defer`
#: must stay visible to `queue.pending`, and a further ruling on it (even
#: another `defer`, or now an accept/reject) is still allowed. Once a
#: FINAL ruling lands, no further ruling on that proposal is accepted.
FINAL_DECISIONS = (ACCEPT, REJECT)

SCHEMA_VERSION = 1

DEFAULT_DIR = Path(__file__).resolve().parent

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS records (
    id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    role TEXT NOT NULL,
    cycle INTEGER NOT NULL,
    type TEXT,
    proposal_id TEXT,
    payload TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_records_ts ON records(ts);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT NOT NULL REFERENCES records(id),
    signal TEXT NOT NULL,
    op TEXT NOT NULL,
    value TEXT,
    registered_game_tick INTEGER NOT NULL,
    due_game_tick INTEGER NOT NULL,
    status TEXT NOT NULL,
    actual_value TEXT,
    graded_at TEXT,
    grade_note TEXT
);

CREATE INDEX IF NOT EXISTS idx_predictions_pending_due ON predictions(status, due_game_tick);
"""


class QueueError(Exception):
    """Raised when a record would corrupt the queue. Never swallowed."""


def default_path(fort: str | None = None) -> Path:
    return DEFAULT_DIR / f"{fort or fort_name()}.sqlite3"


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_SQL)
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()
    elif row["version"] != SCHEMA_VERSION:
        raise QueueError(
            f"database is schema_version {row['version']}, this code is "
            f"{SCHEMA_VERSION}"
        )


@contextmanager
def _connect(path: str | Path) -> Iterator[sqlite3.Connection]:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)
        yield conn
    finally:
        conn.close()


def _next_id(conn: sqlite3.Connection, kind: str) -> str:
    row = conn.execute("SELECT COUNT(*) AS n FROM records WHERE kind = ?", (kind,)).fetchone()
    return f"{kind}-{row['n'] + 1:04d}"


def _proposal_id_already_flagged(errors: list[str]) -> bool:
    """True if validation already flagged `proposal_id` itself
    (missing/empty/wrong type) — in which case the dangling-reference check
    below would be checking a value already known to be junk."""
    return any(e.startswith("record.proposal_id:") for e in errors)


def _insert_record(conn: sqlite3.Connection, record: dict) -> None:
    conn.execute(
        "INSERT INTO records (id, ts, kind, role, cycle, type, proposal_id, payload) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            record["id"], record["ts"], record["kind"], record["role"], record["cycle"],
            record.get("type"), record.get("proposal_id"),
            json.dumps(record, sort_keys=True, ensure_ascii=False),
        ),
    )


def _insert_prediction(
    conn: sqlite3.Connection, *, record_id: str, signal: str, op: str, value,
    registered_game_tick: int, due_game_tick: int,
) -> None:
    """A separate, monkeypatchable function on purpose: `dfqueue/tests/
    test_store.py` patches this to raise between the two inserts `append()`
    makes for a proposal, to prove the transaction is really atomic rather
    than just documented as such."""
    conn.execute(
        "INSERT INTO predictions (record_id, signal, op, value, registered_game_tick, "
        "due_game_tick, status, actual_value, graded_at, grade_note) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            record_id, signal, op, json.dumps(value), registered_game_tick, due_game_tick,
            PENDING, None, None, None,
        ),
    )


def append(record: dict, path: str | Path, *, game_tick: int | None = None) -> dict:
    """Validate and append one record. Refuses a malformed record with every
    error listed, writing nothing to either table. Returns the record as
    written (with `id`/`ts` filled in if they were absent).

    `game_tick` is the fort's current absolute in-game tick
    (`grade.game_tick_from_overview`), required for a `proposal` (its
    prediction's `due_game_tick` is `game_tick + check_after_ticks`) and
    ignored for `pass`/`ruling`, which carry no prediction.

    Two checks need the rest of the queue and so cannot live in
    `schema.validate()`, which is stateless per record:
    - a fresh record's `id` must not collide with one already in the
      database;
    - a `ruling`'s `proposal_id` must name a `proposal` already there.
    Both are checked here, against the open connection, before anything is
    written — same contract as the JSONL version's `append()`.
    """
    if not isinstance(record, dict):
        raise QueueError("refusing to append a malformed record:\n  record: expected an object")

    record = dict(record)  # never mutate the caller's dict

    with _connect(path) as conn:
        if not record.get("id"):
            record["id"] = _next_id(conn, record.get("kind"))
        if not record.get("ts"):
            record["ts"] = datetime.now(timezone.utc).isoformat()

        errors = validate(record)

        existing = conn.execute(
            "SELECT 1 FROM records WHERE id = ?", (record["id"],)
        ).fetchone()
        if existing is not None:
            errors.append(f"record.id: {record['id']!r} is already in the queue")

        if record.get("kind") == RULING and not _proposal_id_already_flagged(errors):
            proposal_id = record.get("proposal_id")
            found = conn.execute(
                "SELECT 1 FROM records WHERE id = ? AND kind = ?", (proposal_id, PROPOSAL)
            ).fetchone()
            if found is None:
                errors.append(
                    f"record.proposal_id: {proposal_id!r} does not refer to an "
                    "existing proposal in this queue"
                )
            else:
                # A defer ("decide later") never closes a proposal, so a
                # ruling after a defer is fine; a second FINAL ruling
                # (accept/reject after an accept/reject, or a defer after
                # one) is refused -- the proposal is already closed. Uses
                # json_extract over the stored payload rather than a new
                # column, so this needs no schema_version bump; see this
                # module's own docstring, "Atomicity", for why payload is
                # already the single source of truth for a record's fields.
                already_final = conn.execute(
                    "SELECT 1 FROM records WHERE kind = ? AND proposal_id = ? "
                    "AND json_extract(payload, '$.decision') IN (?, ?)",
                    (RULING, proposal_id, *FINAL_DECISIONS),
                ).fetchone()
                if already_final is not None:
                    errors.append(
                        f"record.proposal_id: {proposal_id!r} already has a final "
                        "ruling (accept or reject); a proposal may be ruled on "
                        "again only if its only ruling(s) so far were defer"
                    )

        if record.get("kind") == PROPOSAL:
            if isinstance(game_tick, bool) or not isinstance(game_tick, int):
                errors.append(
                    "game_tick: a proposal must be appended with an integer "
                    f"game_tick (its prediction's due_game_tick depends on it), got {game_tick!r}"
                )

        if errors:
            raise QueueError("refusing to append an invalid record:\n  " + "\n  ".join(errors))

        with conn:  # one transaction: commits on success, rolls back on any exception
            _insert_record(conn, record)
            if record["kind"] == PROPOSAL:
                pred = record["prediction"]
                _insert_prediction(
                    conn,
                    record_id=record["id"],
                    signal=pred["signal"],
                    op=pred["op"],
                    value=pred.get("value"),
                    registered_game_tick=game_tick,
                    due_game_tick=game_tick + pred["check_after_ticks"],
                )

        return record


def load(path: str | Path) -> list[dict]:
    """Every record, in append order — the full audit trail, same shape and
    order as the old JSONL version's `load()`."""
    with _connect(path) as conn:
        rows = conn.execute("SELECT payload FROM records ORDER BY rowid ASC").fetchall()
    return [json.loads(r["payload"]) for r in rows]


def latest(path: str | Path, n: int) -> list[dict]:
    """The `n` most recently appended records, newest first — the query the
    feed (`handoffs/2026-09-14-proposal-queue.md` step 3) actually needs,
    backed by `idx_records_ts`."""
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT payload FROM records ORDER BY ts DESC, rowid DESC LIMIT ?", (n,)
        ).fetchall()
    return [json.loads(r["payload"]) for r in rows]


def _prediction_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "record_id": row["record_id"],
        "signal": row["signal"],
        "op": row["op"],
        "value": json.loads(row["value"]) if row["value"] is not None else None,
        "registered_game_tick": row["registered_game_tick"],
        "due_game_tick": row["due_game_tick"],
        "status": row["status"],
        "actual_value": json.loads(row["actual_value"]) if row["actual_value"] is not None else None,
        "graded_at": row["graded_at"],
        "grade_note": row["grade_note"],
    }


def pending_due(path: str | Path, tick: int) -> list[dict]:
    """Every prediction still `pending` whose `due_game_tick` is at or
    before `tick` — the grader's own query, backed by
    `idx_predictions_pending_due`."""
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT id, record_id, signal, op, value, registered_game_tick, due_game_tick, "
            "status, actual_value, graded_at, grade_note FROM predictions "
            "WHERE status = ? AND due_game_tick <= ? ORDER BY due_game_tick ASC, id ASC",
            (PENDING, tick),
        ).fetchall()
    return [_prediction_row(r) for r in rows]


def pending_proposals(path: str | Path, limit: int | None = None) -> list[dict]:
    """Every `proposal` record with no FINAL ruling yet, oldest first --
    added `handoffs/2026-09-15-queue-into-dfmcp.md` for `queue.pending`
    (`dfmcp/queue_tools.py`), revised the same day (Phase A review) once a
    `defer`-only proposal was found to vanish from this query for good.

    "Pending" means: no `ruling` naming this proposal has `decision` in
    `FINAL_DECISIONS` (accept/reject). A proposal ruled only `defer` --
    "decide later" -- stays pending, exactly as `append()`'s own
    second-final-ruling refusal above treats it: still open to a further
    ruling. Every ruling's `proposal_id` is already its own indexed column
    (see `_insert_record`), and `json_extract(payload, '$.decision')` reads
    the decision straight out of the stored record rather than a second
    column -- no schema_version bump needed. json1 is confirmed available
    in every interpreter this project runs SQLite from (see this stream's
    report for how); VM 103 (Ubuntu noble, Python 3.12) ships a SQLite new
    enough for it too, but that is a Phase B fact to re-confirm live, not
    assumed here.
    """
    query = (
        "SELECT r.payload FROM records r WHERE r.kind = ? AND NOT EXISTS ("
        "SELECT 1 FROM records r2 WHERE r2.kind = ? AND r2.proposal_id = r.id "
        "AND json_extract(r2.payload, '$.decision') IN (?, ?)"
        ") ORDER BY r.ts ASC, r.rowid ASC"
    )
    params: list = [PROPOSAL, RULING, *FINAL_DECISIONS]
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    with _connect(path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [json.loads(r["payload"]) for r in rows]


def apply_grades(path: str | Path, updates: list[dict]) -> None:
    """Persist a grading pass's results, all in one transaction. Each entry
    in `updates` is `{"id", "status", "actual_value", "graded_at",
    "grade_note"}`, exactly `grade.grade_due`'s own per-prediction shape.
    Called from `grade.py`, not from `append()`."""
    if not updates:
        return
    with _connect(path) as conn:
        with conn:
            for u in updates:
                conn.execute(
                    "UPDATE predictions SET status = ?, actual_value = ?, graded_at = ?, "
                    "grade_note = ? WHERE id = ?",
                    (
                        u["status"], json.dumps(u["actual_value"]), u["graded_at"],
                        u["grade_note"], u["id"],
                    ),
                )


def export_jsonl(path: str | Path, out_dir: str | Path) -> None:
    """A deterministic dump of both tables to `out_dir/records.jsonl` and
    `out_dir/predictions.jsonl`, git-trackable — the public-report goal the
    2026-08-27 no-database decision cared about (`decisions/DECISIONS.md`),
    kept even though the system of record for live data is now SQLite. Rows
    are re-serialized with `sort_keys=True` and read back in `id ASC` order,
    so two exports of the same database content are byte-identical."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with _connect(path) as conn:
        records = conn.execute("SELECT payload FROM records ORDER BY id ASC").fetchall()
        predictions = conn.execute(
            "SELECT id, record_id, signal, op, value, registered_game_tick, due_game_tick, "
            "status, actual_value, graded_at, grade_note FROM predictions ORDER BY id ASC"
        ).fetchall()

    with (out_dir / "records.jsonl").open("w", encoding="utf-8") as fh:
        for r in records:
            row = json.loads(r["payload"])
            fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")

    with (out_dir / "predictions.jsonl").open("w", encoding="utf-8") as fh:
        for p in predictions:
            fh.write(json.dumps(_prediction_row(p), sort_keys=True, ensure_ascii=False) + "\n")
