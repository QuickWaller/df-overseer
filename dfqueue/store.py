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

import argparse
import json
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from learning.predictions.schema import PENDING

from .schema import (
    ACCEPT, ANSWER, ASK, EXECUTED, PROPOSAL, REJECT, RULING, fort_name,
    sole_writer, validate,
)

#: A ruling's `decision` values that close a proposal for good. `defer`
#: ("decide later") is deliberately excluded: a proposal ruled only `defer`
#: must stay visible to `queue.pending`, and a further ruling on it (even
#: another `defer`, or now an accept/reject) is still allowed. Once a
#: FINAL ruling lands, no further ruling on that proposal is accepted.
FINAL_DECISIONS = (ACCEPT, REJECT)

#: A proposal's prediction status before any `executed` record has armed
#: it -- distinct from (and never confused with) `learning.predictions.
#: schema.PENDING`, which here means "armed and awaiting its due tick".
#: Never `_load_roster`'d or otherwise touched by `learning/predictions/`,
#: which this module deliberately does not extend (not a touched surface
#: of `handoffs/2026-09-22-loop-queue-quartermaster.md`); kept local to
#: `dfqueue` instead. See "Execution arms the prediction" below.
AWAITING_EXECUTION = "awaiting_execution"

#: A prediction's status once an admin voids it (`void_prediction` below):
#: `docs/AGENT-LOOP.md` §7, `decisions/DECISIONS.md` 2026-09-22
#: ("proposal-0001 is voided with a note before the loop first grades").
#: Never written by `append()` or any agent-reachable tool -- only by the
#: admin CLI at the bottom of this module, run by a human, never a role.
VOID = "void"

#: Statuses `void_prediction` will actually change. Voiding an
#: already-graded prediction (GRADED_TRUE/GRADED_FALSE/UNRESOLVABLE) is
#: refused: voiding exists to skip a grading that has not happened yet, not
#: to erase one that has. `AWAITING_EXECUTION` is included because a
#: proposal that was ruled but never executed (proposal-0001's own case)
#: never left that status.
_VOIDABLE_STATUSES = (AWAITING_EXECUTION, PENDING)

SCHEMA_VERSION = 2

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
    grade_note TEXT,
    check_after_ticks INTEGER
);

CREATE INDEX IF NOT EXISTS idx_predictions_pending_due ON predictions(status, due_game_tick);
"""

#: Schema migrations, keyed by the version they upgrade FROM. Applied in
#: order by `_ensure_schema` for any database opened below `SCHEMA_VERSION`.
#: See "Migrating a v1 database" below for what each one does and why a
#: migration, not a hard refusal, is the right shape here.
_MIGRATIONS: dict[int, str] = {
    1: """
    ALTER TABLE predictions ADD COLUMN check_after_ticks INTEGER;
    UPDATE predictions SET check_after_ticks = due_game_tick - registered_game_tick
        WHERE check_after_ticks IS NULL;
    """,
}


class QueueError(Exception):
    """Raised when a record would corrupt the queue. Never swallowed."""


def default_path(fort: str | None = None) -> Path:
    return DEFAULT_DIR / f"{fort or fort_name()}.sqlite3"


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the schema if this is a fresh database, or migrate an older
    one forward. `CREATE TABLE IF NOT EXISTS` above already gives a fresh
    database the current `predictions.check_after_ticks` column for free;
    the migration path below is what an EXISTING v1 database (already has
    `predictions`, without that column) actually needs.

    ## Migrating a v1 database

    `docs/AGENT-LOOP.md` item 4 changes what a proposal's prediction
    `status` means: `AWAITING_EXECUTION` (new, this stream) until a
    `queue.executed` record arms it, then `learning.predictions.schema.
    PENDING` with `due_game_tick` computed from the EXECUTION tick, not the
    proposal's own write tick. A v1 database's existing rows were written
    under the OLD rule (`due_game_tick` already computed at write time,
    `status` already `pending`/`graded_true`/`graded_false`/
    `unresolvable`) — this migration does not, and must not, reinterpret
    them: their `due_game_tick` keeps its original write-time meaning
    (a compatible default, not a reinterpretation, per this stream's own
    "keep existing records readable" requirement), and only NEWLY appended
    proposals get the new `AWAITING_EXECUTION`-until-armed behaviour. The
    migration's only job is to backfill `check_after_ticks` for old rows
    (`due_game_tick - registered_game_tick`, the value that was implicit
    in those two columns all along) so `store.append()`'s `EXECUTED`
    handling below has one column to read regardless of which schema
    version wrote a given prediction row.
    """
    conn.executescript(_SCHEMA_SQL)
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()
        return

    version = row["version"]
    if version < SCHEMA_VERSION:
        for v in range(version, SCHEMA_VERSION):
            conn.executescript(_MIGRATIONS[v])
        conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
        conn.commit()
    elif version != SCHEMA_VERSION:
        raise QueueError(
            f"database is schema_version {row['version']}, this code is "
            f"{SCHEMA_VERSION} (newer database, older code)"
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


def _ruling_id_already_flagged(errors: list[str]) -> bool:
    """Same idea as `_proposal_id_already_flagged`, for `executed`'s own
    `ruling_id`."""
    return any(e.startswith("record.ruling_id:") for e in errors)


def _ask_id_already_flagged(errors: list[str]) -> bool:
    """Same idea again, for `answer`'s own `ask_id`."""
    return any(e.startswith("record.ask_id:") for e in errors)


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
    registered_game_tick: int, due_game_tick: int, check_after_ticks: int,
) -> None:
    """A separate, monkeypatchable function on purpose: `dfqueue/tests/
    test_store.py` patches this to raise between the two inserts `append()`
    makes for a proposal, to prove the transaction is really atomic rather
    than just documented as such.

    `status` is always `AWAITING_EXECUTION` at insert time now (`docs/
    AGENT-LOOP.md` item 4): `due_game_tick` is stored as a same-shaped
    integer for the NOT NULL column and for anyone reading the row before
    it is armed, but it is provisional (`registered_game_tick +
    check_after_ticks`, i.e. computed as if execution happened
    immediately) until the first `executed` record referencing this
    proposal's ruling recomputes it from the real execution tick -- see
    "Execution arms the prediction" on `append()` below. `pending_due()`
    never returns a row whose status is `AWAITING_EXECUTION` regardless of
    what `due_game_tick` currently holds, since it filters on `status =
    PENDING` (`learning.predictions.schema`'s constant) — the provisional
    value is inert until arming flips the status.
    """
    conn.execute(
        "INSERT INTO predictions (record_id, signal, op, value, registered_game_tick, "
        "due_game_tick, status, actual_value, graded_at, grade_note, check_after_ticks) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            record_id, signal, op, json.dumps(value), registered_game_tick, due_game_tick,
            AWAITING_EXECUTION, None, None, None, check_after_ticks,
        ),
    )


def append(record: dict, path: str | Path, *, game_tick: int | None = None) -> dict:
    """Validate and append one record. Refuses a malformed record with every
    error listed, writing nothing to either table. Returns the record as
    written (with `id`/`ts` filled in if they were absent).

    `game_tick` is the fort's current absolute in-game tick
    (`grade.game_tick_from_overview`), required for a `proposal` (its
    prediction's provisional `due_game_tick` is `game_tick +
    check_after_ticks` — see `_insert_prediction`) and ignored for every
    other kind, none of which carry a prediction of their own. An
    `executed` record's own execution tick is its `cycle` field (already
    stamped the same way every record's `cycle` is, by the caller — see
    `dfmcp/queue_tools.py`'s "cycle/snapshot" docstring section), not a
    second `game_tick` kwarg.

    Checks that need the rest of the queue and so cannot live in
    `schema.validate()`, which is stateless per record:
    - a fresh record's `id` must not collide with one already in the
      database;
    - a `ruling`'s `proposal_id` must name a `proposal` already there, and
      that proposal must not already have a final ruling;
    - a `ruling` may not be written while a fact-check (an `ask` from the
      Overseer naming this proposal) is still open;
    - an `executed`'s `ruling_id` must name a `ruling` already there, and
      that ruling's decision must be `accept`;
    - an `ask`'s `proposal_id`, when present, must name a `proposal`
      already there;
    - an `answer`'s `ask_id` must name an `ask` already there, and that
      `ask` must not already have an answer (one ask, one answer).
    All are checked here, against the open connection, before anything is
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
        kind = record.get("kind")

        existing = conn.execute(
            "SELECT 1 FROM records WHERE id = ?", (record["id"],)
        ).fetchone()
        if existing is not None:
            errors.append(f"record.id: {record['id']!r} is already in the queue")

        if kind == RULING and not _proposal_id_already_flagged(errors):
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

                # Fact-check gate (docs/AGENT-ARCHITECTURE.md, "Consultant
                # fact-check before ruling"; docs/AGENT-LOOP.md item 7):
                # an `ask` from the Overseer naming this proposal, with no
                # `answer` yet, blocks a ruling on it. A plain lookup ask
                # (role != overseer, or no proposal_id at all) never blocks
                # anything -- only role=overseer's own routed fact-check
                # does.
                open_fact_check = conn.execute(
                    "SELECT a.id FROM records a WHERE a.kind = ? AND a.role = ? "
                    "AND a.proposal_id = ? "
                    "AND NOT EXISTS (SELECT 1 FROM records r WHERE r.kind = ? "
                    "AND json_extract(r.payload, '$.ask_id') = a.id)",
                    (ASK, sole_writer(), proposal_id, ANSWER),
                ).fetchone()
                if open_fact_check is not None:
                    errors.append(
                        f"record.proposal_id: {proposal_id!r} has an open fact-check "
                        f"({open_fact_check['id']!r}, no answer yet); it cannot be "
                        "ruled on until the Consultant answers"
                    )

        if kind == EXECUTED and not _ruling_id_already_flagged(errors):
            ruling_id = record.get("ruling_id")
            ruling_row = conn.execute(
                "SELECT payload FROM records WHERE id = ? AND kind = ?", (ruling_id, RULING)
            ).fetchone()
            if ruling_row is None:
                errors.append(
                    f"record.ruling_id: {ruling_id!r} does not refer to an "
                    "existing ruling in this queue"
                )
            else:
                ruling_payload = json.loads(ruling_row["payload"])
                if ruling_payload.get("decision") != ACCEPT:
                    errors.append(
                        f"record.ruling_id: {ruling_id!r} is a ruling whose decision "
                        f"is {ruling_payload.get('decision')!r}, not {ACCEPT!r}; only "
                        "an accepted proposal may be executed"
                    )

        if kind == ASK and "proposal_id" in record and not _proposal_id_already_flagged(errors):
            proposal_id = record.get("proposal_id")
            found = conn.execute(
                "SELECT 1 FROM records WHERE id = ? AND kind = ?", (proposal_id, PROPOSAL)
            ).fetchone()
            if found is None:
                errors.append(
                    f"record.proposal_id: {proposal_id!r} does not refer to an "
                    "existing proposal in this queue"
                )

        if kind == ANSWER and not _ask_id_already_flagged(errors):
            ask_id = record.get("ask_id")
            ask_row = conn.execute(
                "SELECT 1 FROM records WHERE id = ? AND kind = ?", (ask_id, ASK)
            ).fetchone()
            if ask_row is None:
                errors.append(
                    f"record.ask_id: {ask_id!r} does not refer to an existing ask "
                    "in this queue"
                )
            else:
                already_answered = conn.execute(
                    "SELECT 1 FROM records WHERE kind = ? AND "
                    "json_extract(payload, '$.ask_id') = ?", (ANSWER, ask_id),
                ).fetchone()
                if already_answered is not None:
                    errors.append(
                        f"record.ask_id: {ask_id!r} already has an answer; one ask, "
                        "one answer, no threads"
                    )

        if kind == PROPOSAL:
            if isinstance(game_tick, bool) or not isinstance(game_tick, int):
                errors.append(
                    "game_tick: a proposal must be appended with an integer "
                    f"game_tick (its prediction's due_game_tick depends on it), got {game_tick!r}"
                )

        if errors:
            raise QueueError("refusing to append an invalid record:\n  " + "\n  ".join(errors))

        with conn:  # one transaction: commits on success, rolls back on any exception
            _insert_record(conn, record)
            if kind == PROPOSAL:
                pred = record["prediction"]
                _insert_prediction(
                    conn,
                    record_id=record["id"],
                    signal=pred["signal"],
                    op=pred["op"],
                    value=pred.get("value"),
                    registered_game_tick=game_tick,
                    due_game_tick=game_tick + pred["check_after_ticks"],
                    check_after_ticks=pred["check_after_ticks"],
                )
            elif kind == EXECUTED:
                _arm_prediction_on_first_execution(conn, record)

        return record


def _arm_prediction_on_first_execution(conn: sqlite3.Connection, record: dict) -> None:
    """`docs/AGENT-LOOP.md` item 4: "a prediction's window starts at
    execution, not at writing." Called from inside `append()`'s own
    transaction, immediately after an `executed` record's own row lands in
    `records`.

    Only the FIRST `executed` record naming a given `ruling_id` arms that
    ruling's proposal's prediction (flips `AWAITING_EXECUTION` ->
    `learning.predictions.schema.PENDING`, recomputes `due_game_tick` from
    THIS record's own `cycle` -- the execution tick -- plus the
    prediction's stored `check_after_ticks`). A second, later `executed`
    record for the same ruling (a retry after a failed first attempt, for
    instance) is still inserted into `records` as its own audit entry, but
    does not re-arm or move the window a second time: "a failed execution
    is a valid record" does not mean a failed execution should be able to
    restart -- or worse, on a later retry, silently shorten -- a window
    that already started counting down."""
    ruling_id = record["ruling_id"]

    earlier = conn.execute(
        "SELECT 1 FROM records WHERE kind = ? AND "
        "json_extract(payload, '$.ruling_id') = ? AND id != ?",
        (EXECUTED, ruling_id, record["id"]),
    ).fetchone()
    if earlier is not None:
        return  # not the first execution of this ruling; no re-arming

    ruling_row = conn.execute(
        "SELECT proposal_id FROM records WHERE id = ? AND kind = ?", (ruling_id, RULING)
    ).fetchone()
    if ruling_row is None:  # pragma: no cover -- append() already refused a dangling ruling_id
        return
    proposal_id = ruling_row["proposal_id"]

    pred_row = conn.execute(
        "SELECT id, check_after_ticks FROM predictions WHERE record_id = ? AND status = ?",
        (proposal_id, AWAITING_EXECUTION),
    ).fetchone()
    if pred_row is None:  # already armed, or (should not happen) no prediction row at all
        return

    execution_tick = record["cycle"]
    due_game_tick = execution_tick + pred_row["check_after_ticks"]
    conn.execute(
        "UPDATE predictions SET status = ?, due_game_tick = ? WHERE id = ?",
        (PENDING, due_game_tick, pred_row["id"]),
    )


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


def open_asks(path: str | Path, limit: int | None = None) -> list[dict]:
    """Every `ask` record with no `answer` yet, oldest first -- the
    Consultant's own read (`dfmcp/queue_tools.py`'s `queue.pending`, for
    role `consultant`, branches to this instead of `pending_proposals`:
    the Consultant never proposes, so "what's pending for me" means open
    questions, not proposals). Same "no threads" contract `append()`
    enforces at write time: at most one `answer` per `ask`, so "open" here
    just means "answer count is zero", no defer-like open/closed
    distinction to track.
    """
    query = (
        "SELECT a.payload FROM records a WHERE a.kind = ? AND NOT EXISTS ("
        "SELECT 1 FROM records r WHERE r.kind = ? AND "
        "json_extract(r.payload, '$.ask_id') = a.id"
        ") ORDER BY a.ts ASC, a.rowid ASC"
    )
    params: list = [ASK, ANSWER]
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    with _connect(path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [json.loads(r["payload"]) for r in rows]


def unexecuted_accepted_proposals(path: str | Path) -> list[dict]:
    """Every proposal whose ruling was `accept` but that has no `executed`
    record referencing that ruling yet, oldest proposal first. `docs/
    AGENT-LOOP.md` item 4: "an accepted but never-executed proposal is
    never graded as a miss, it is reported as unexecuted" -- this is that
    report. `dfqueue/grade.py`'s `run_grading_cycle` calls this every time
    it grades, alongside (never instead of) `pending_due`'s real misses/
    hits, so a caller sees both in one pass rather than only the graded
    half of the picture.

    Each entry is `{"proposal": <the proposal record>, "ruling_id": <the
    accepting ruling's id>}` -- the ruling id is what a caller would pass
    to `queue.executed` next, so it is handed over rather than making the
    caller re-derive it.
    """
    query = (
        "SELECT p.payload AS proposal_payload, rl.id AS ruling_id "
        "FROM records p "
        "JOIN records rl ON rl.kind = ? AND rl.proposal_id = p.id "
        "AND json_extract(rl.payload, '$.decision') = ? "
        "WHERE p.kind = ? AND NOT EXISTS ("
        "SELECT 1 FROM records ex WHERE ex.kind = ? AND "
        "json_extract(ex.payload, '$.ruling_id') = rl.id"
        ") ORDER BY p.ts ASC, p.rowid ASC"
    )
    with _connect(path) as conn:
        rows = conn.execute(query, (RULING, ACCEPT, PROPOSAL, EXECUTED)).fetchall()
    return [
        {"proposal": json.loads(r["proposal_payload"]), "ruling_id": r["ruling_id"]}
        for r in rows
    ]


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


# ---------------------------------------------------------------------------
# Voiding a prediction -- admin-only, by code, never an agent tool.
#
# `docs/AGENT-LOOP.md` §7 and `decisions/DECISIONS.md` 2026-09-22: the queue
# migration keeps a pre-migration proposal's prediction on its original,
# write-time `due_game_tick` (see `_ensure_schema`'s own docstring above), so
# the conductor's first grading cycle would otherwise record `proposal-0001`
# (ruled 2026-09-16, left ungraded on purpose) as a miss caused by
# ruling-to-execution latency, not by the proposal itself. The user chose to
# void it with a note rather than grade it. This is deliberately NOT a
# `dfqueue.schema` record kind and NOT reachable through `dfmcp.queue_tools`:
# no role's tools.yaml can ever grant it, because there is no MCP tool at
# all here to grant -- it is a direct `dfqueue.store` call, run by a human
# from the CLI at the bottom of this module, never inside a cycle.
# ---------------------------------------------------------------------------


def void_prediction(
    path: str | Path, proposal_id: str, note: str, *, voided_at: str | None = None,
) -> dict:
    """Mark `proposal_id`'s prediction `VOID` with a required, non-empty
    `note`. The proposal's own `records` row is untouched (still visible,
    still loadable via `load()`/`export_jsonl()`) -- only the prediction
    row's `status`/`grade_note`/`graded_at` change, so the record stays
    visible with its reason rather than being deleted. `dfqueue/grade.py`'s
    `pending_due` only ever selects `status = PENDING`, so a voided
    prediction is skipped by every future grading cycle for free, with no
    change needed there.

    Refuses (`QueueError`, nothing written):
    - an empty or whitespace-only `note` -- a void with no reason defeats
      the entire point of voiding rather than deleting;
    - a `proposal_id` not present in this queue, or one with no prediction
      row at all (should not happen: every `proposal` gets one atomically
      at `append()` time);
    - a prediction not in `_VOIDABLE_STATUSES` -- already graded, or
      already voided. Voiding is for skipping a grading that has not
      happened yet, not for erasing or re-doing one that already has.
    """
    if not isinstance(note, str) or not note.strip():
        raise QueueError("refusing to void: a note is required and must not be empty")
    if voided_at is None:
        voided_at = datetime.now(timezone.utc).isoformat()

    with _connect(path) as conn:
        proposal_row = conn.execute(
            "SELECT 1 FROM records WHERE id = ? AND kind = ?", (proposal_id, PROPOSAL)
        ).fetchone()
        if proposal_row is None:
            raise QueueError(f"refusing to void: {proposal_id!r} is not a proposal in this queue")

        pred_row = conn.execute(
            "SELECT id, status FROM predictions WHERE record_id = ?", (proposal_id,)
        ).fetchone()
        if pred_row is None:  # pragma: no cover -- append() always inserts one atomically
            raise QueueError(f"refusing to void: {proposal_id!r} has no prediction row")

        if pred_row["status"] not in _VOIDABLE_STATUSES:
            raise QueueError(
                f"refusing to void: {proposal_id!r}'s prediction is already "
                f"{pred_row['status']!r}; only an ungraded prediction "
                f"({', '.join(_VOIDABLE_STATUSES)}) may be voided"
            )

        with conn:
            conn.execute(
                "UPDATE predictions SET status = ?, grade_note = ?, graded_at = ? WHERE id = ?",
                (VOID, note, voided_at, pred_row["id"]),
            )

    return {
        "proposal_id": proposal_id, "status": VOID, "note": note, "voided_at": voided_at,
    }


def _cli_void(argv: list[str] | None = None) -> int:
    """`python -m dfqueue.store --db PATH --proposal-id ID --note "..."`.
    The module's only CLI action is a void -- there is deliberately no
    second subcommand here, since every other queue write goes through
    `dfmcp.queue_tools` (an agent-reachable MCP tool), never this file's
    own `__main__`.

    Offline and directly testable (`dfqueue/tests/test_store.py` calls
    `_cli_void` against a `tmp_path` database, never a real one). Per this
    repo's CLAUDE.md, running this against any real, deployed queue database
    is a live-state change and needs the user's explicit go-ahead each time
    -- this stream builds and tests the mechanism only; it is never run here
    against VM 103's own queue.
    """
    parser = argparse.ArgumentParser(
        prog="python -m dfqueue.store",
        description=(
            "Admin-only: void one proposal's prediction so it is never graded, "
            "keeping the record visible with a required reason. Never an agent "
            "tool -- run by a human. Destructive-adjacent (changes what a live "
            "queue will grade): confirm the target database with the user "
            "before running this against anything but a throwaway/test file."
        ),
    )
    parser.add_argument("--db", required=True, type=Path, help="path to the queue sqlite3 database")
    parser.add_argument("--proposal-id", required=True, help='e.g. "proposal-0001"')
    parser.add_argument("--note", required=True, help="why this proposal is voided rather than graded")
    args = parser.parse_args(argv)

    try:
        result = void_prediction(args.db, args.proposal_id, args.note)
    except QueueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover -- exercised via _cli_void() directly in tests
    sys.exit(_cli_void())
