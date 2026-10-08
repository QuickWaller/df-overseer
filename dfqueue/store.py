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

from . import plan, routing
from .schema import (
    ABANDON, ABANDONED, ACCEPT, AMEND, ANSWER, ASK, CLOSE, CLOSE_COMPLETED,
    CLOSE_NOT_DONE, DONE, EXECUTED, FAILED, FORT_PLAN, GUARDS_DEFAULT, HELD, ISSUED,
    PLAN_CHANGE, PLAN_ROLE,
    OBSERVATION, OBS_CONSISTENT, OBSERVATION_ROLE, PROJECT, PROPOSAL,
    PUBLIC_RATIONALE_MAX, READY, REJECT, RULING, SUCCESS, FAILURE,
    TRIGGER_ALL_DONE, TRIGGER_ALL_SUCCESS, WAITING, ask_addressee, executor, fort_name,
    near_duplicate_reason, normalize_project, sole_writer, step_identity, validate,
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

SCHEMA_VERSION = 3

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

-- Added handoffs/2026-09-28-dfqueue-project-step-schema.md: the
-- target-level state fold (design §4.4/§4.5), materialised the same way
-- `predictions` already is -- append-only records in `records` remain the
-- single source of truth; this table is a derived, updated-in-place
-- projection of them, rebuildable from `records` alone if it were ever
-- dropped. One row per (project, step, target). `last_tick` is the `cycle`
-- of the `executed` record that last set this row's state -- what
-- `rollback_drift` below compares against the fort's current tick.
CREATE TABLE IF NOT EXISTS step_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES records(id),
    step_id TEXT NOT NULL,
    target TEXT NOT NULL,
    state TEXT NOT NULL,
    reason TEXT,
    last_tick INTEGER,
    UNIQUE(project_id, step_id, target)
);

CREATE INDEX IF NOT EXISTS idx_step_targets_project ON step_targets(project_id);

-- Added handoffs/2026-10-05-stage-2a.md (docs/CONDUCTOR-EXECUTION.md 6.1).
-- `meta` holds the cutovers (`cutover:<group>` -> ruling id). `step_runs` is
-- the executor's write-ahead marker for one real call: written `issuing`
-- before the call, `recorded` once its `executed` record is appended. A row
-- left `issuing` is an Uncertain run (4.1, 4.2). `step_id` is a step id, or
-- `cleanup:<handle>` for an abandon cleanup call (4.4).
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS step_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    status TEXT NOT NULL,
    outcome TEXT,
    tick INTEGER NOT NULL,
    baseline TEXT,
    handle TEXT,
    executed_id TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_step_runs_step ON step_runs(project_id, step_id);
CREATE INDEX IF NOT EXISTS idx_step_runs_status ON step_runs(status);
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
    # v2 -> v3 only adds the `meta` and `step_runs` tables, which
    # `_SCHEMA_SQL`'s `CREATE TABLE IF NOT EXISTS` already created on open.
    2: "SELECT 1;",
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


@contextmanager
def _locked(path: str | Path) -> Iterator[sqlite3.Connection]:
    """A connection holding the write lock (`BEGIN IMMEDIATE`) for a whole
    read-decide-write: two executor calls can never both read the same base
    (P2-L1, "reads and appends under the one write lock"). Commits on
    success, rolls back on any exception."""
    with _connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.rollback()
            raise
        else:
            conn.commit()


@contextmanager
def _write_txn(conn: sqlite3.Connection, commit: bool) -> Iterator[None]:
    """`with conn:` when `commit`, else no-op (the caller holds `_locked`
    and commits once, so the record and its bookkeeping are one unit)."""
    if commit:
        with conn:
            yield
    else:
        yield


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


def _duplicate_of_already_flagged(errors: list[str]) -> bool:
    """Same idea again, for a proposal's own `duplicate_of`."""
    return any(e.startswith("record.duplicate_of:") for e in errors)


def _from_ruling_already_flagged(errors: list[str]) -> bool:
    """Same idea again, for a `project`'s own `from_ruling`."""
    return any(e.startswith("record.from_ruling:") for e in errors)


def _project_step_ids_already_flagged(errors: list[str]) -> bool:
    """Same idea again, for `executed`'s own `step_id` and `observation`'s
    own `project_id`/`step_id`."""
    return any(
        e.startswith("record.step_id:") or e.startswith("record.project_id:")
        for e in errors
    )


def _find_project_for_ruling(conn: sqlite3.Connection, ruling_id: str) -> dict | None:
    """The `project` record whose `from_ruling` names `ruling_id`, or
    `None`. `records.type` is not populated for a `project` (it is not a
    `proposal`), so this is a `json_extract` scan over `kind = project`
    rows -- the same shape `_find_duplicate_proposal` already uses for a
    field the store has no dedicated indexed column for."""
    row = conn.execute(
        "SELECT payload FROM records WHERE kind = ? AND "
        "json_extract(payload, '$.from_ruling') = ?",
        (PROJECT, ruling_id),
    ).fetchone()
    return json.loads(row["payload"]) if row is not None else None


def _step_ids(project: dict) -> set:
    return _step_ids_list(project.get("steps", []))


def _step_ids_list(steps: list) -> set:
    return {s["id"] for s in steps if isinstance(s, dict) and "id" in s}


def _canonical_step_json(step: dict) -> str:
    """Canonical JSON of one step, for `amend`'s own byte-identical reuse
    check (user's call, 2026-10-01, closing the target-seeding gap this
    handoff first only flagged): a step id kept from the previous version
    is accepted only if its own definition (`tool`/`args`/`targets`/
    `requires`/`trigger`/`prefer_after`/`guards`/`id`, whatever the schema
    defines) did not change at all. `sort_keys=True` makes key order
    irrelevant; a nested list still compares positionally, which is correct
    here (`requires` is an ordered edge list, not a set, and reordering it
    is itself a real change worth catching).

    **`label` is excluded from this comparison** (executor's call,
    `handoffs/2026-10-02-queue-display-fields.md`): it is cosmetic display
    text, never read by the reconciler or by `_seed_step_targets`, so a
    step whose only change is a reworded `label` must not be forced to take
    a fresh id -- the fresh-id rule exists to keep `step_targets` rows from
    silently being reinterpreted under a changed `targets`/`tool`/`args`,
    which a label can never cause."""
    comparable = {k: v for k, v in step.items() if k != "label"}
    return json.dumps(comparable, sort_keys=True, ensure_ascii=False)


def _project_id_already_flagged(errors: list[str]) -> bool:
    """Same idea as `_from_ruling_already_flagged`, for `amend`'s and
    `abandon`'s own `project_id` (reuses the same error prefix as
    `executed`'s/`observation`'s `project_id`, see
    `_project_step_ids_already_flagged`, so this is really just a
    differently-named wrapper for readability at each call site)."""
    return _project_step_ids_already_flagged(errors)


def _amends_for_project(conn: sqlite3.Connection, project_id: str) -> list[dict]:
    """Every `amend` record naming `project_id`, oldest first (insertion
    order) -- the append-only history of plan revisions
    (`research/2026-09-30-goal-tree-red-team.md` F-3). Never edited, only
    ever appended to."""
    rows = conn.execute(
        "SELECT payload FROM records WHERE kind = ? AND "
        "json_extract(payload, '$.project_id') = ? ORDER BY rowid ASC",
        (AMEND, project_id),
    ).fetchall()
    return [json.loads(r["payload"]) for r in rows]


def _current_steps_and_version(conn: sqlite3.Connection, project: dict) -> tuple[list, int]:
    """The steps in effect for `project` right now, and that version's
    number: the original `project`'s own `steps` is version 1; the Nth
    `amend` record (oldest first) replaces it wholesale with its own
    `steps`, as version N+1. Never a diff applied to the previous version --
    each `amend`'s `steps` is read as the complete, authoritative current
    plan (see `dfqueue.schema`'s own docstring on `amend`), so a step this
    version drops simply is not in the list read back here; no special-casing
    needed to exclude a dropped step from "is this project done" below.
    """
    amends = _amends_for_project(conn, project["id"])
    if not amends:
        return project.get("steps", []), 1
    return amends[-1]["steps"], len(amends) + 1


def _find_duplicate_proposal(conn: sqlite3.Connection, record: dict) -> tuple[str, str] | None:
    """The first still-open proposal of the same `type` as `record` that
    `schema.near_duplicate_reason` judges a near-duplicate of it, as
    `(existing_id, reason)`, or `None`.

    "Still open" is exactly `pending_proposals`'s own definition (no ruling
    with a FINAL decision -- accept/reject -- yet; a proposal ruled only
    `defer` is still a live duplicate candidate, same as it is still a live
    ruling candidate). `records.type` is already its own indexed column
    (`_insert_record`), so this is a plain column filter, not a
    `json_extract` scan. Oldest first, so two proposals both duplicating a
    third are each flagged against the original, not against each other.
    """
    rows = conn.execute(
        "SELECT r.id, r.payload FROM records r WHERE r.kind = ? AND r.type = ? "
        "AND NOT EXISTS (SELECT 1 FROM records r2 WHERE r2.kind = ? AND "
        "r2.proposal_id = r.id AND json_extract(r2.payload, '$.decision') IN (?, ?)) "
        "ORDER BY r.ts ASC, r.rowid ASC",
        (PROPOSAL, record.get("type"), RULING, *FINAL_DECISIONS),
    ).fetchall()
    mine = set(record.get("serves") or [])
    for row in rows:
        existing = json.loads(row["payload"])
        if mine and mine & set(existing.get("serves") or []):
            # Parallel proposals serving the same plan target are the point
            # of a target with room for more than one in flight (design 2.5).
            continue
        reason = near_duplicate_reason(record, existing)
        if reason:
            return row["id"], reason
    return None


#: A proposal in one of these states is still live: filing the same action again
#: would duplicate it (the same set a briefing always shows).
_LIVE_FILING_STATUSES = ("pending", "accepted", "deferred", "in_project")


def _find_structural_duplicate(conn: sqlite3.Connection, record: dict) -> str | None:
    """The refusal text when `record` asks for the same action (type, step tool
    and identifying arguments, `schema.step_identity`) as a proposal that is
    still live, from any role, or `None`. A follow-up to a project
    (`project_id` or `after_step`) is the next step of existing work, never a
    duplicate. Oldest first, so the refusal names the original."""
    if record.get("project_id") or record.get("after_step"):
        return None
    key = step_identity(record)
    if key is None:
        return None
    rows = conn.execute(
        "SELECT payload FROM records WHERE kind = ? AND type = ? ORDER BY ts ASC, rowid ASC",
        (PROPOSAL, record.get("type")),
    ).fetchall()
    for row in rows:
        existing = json.loads(row["payload"])
        if existing.get("id") == record.get("id") or step_identity(existing) != key:
            continue
        status = _filing_row(conn, existing)["status"]
        if status in _LIVE_FILING_STATUSES:
            return (
                f"already proposed as {existing['id']} by the {existing.get('role')}, {status}: "
                f"the same {key[1]} action ({existing.get('summary')!r}). Do not file it again; "
                "if it needs a change, file a follow-up on its project or wait for its ruling"
            )
    return None


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

    with _connect(path) as conn:
        return _append_in_conn(conn, record, game_tick)


def _append_in_conn(
    conn: sqlite3.Connection, record: dict, game_tick: int | None = None, *, commit: bool = True,
) -> dict:
    """`append()` on an open connection. Everything `append()` documents
    applies; the split lets a caller that already holds the write lock
    (`BEGIN IMMEDIATE`, see `_locked`) read, decide and write as one unit."""
    record = dict(record)  # never mutate the caller's dict

    if not record.get("id"):
        record["id"] = _next_id(conn, record.get("kind"))
    if not record.get("ts"):
        record["ts"] = datetime.now(timezone.utc).isoformat()

    if record.get("kind") == PROJECT:
        # Design §5.3: "a proposal with no steps block is a one-step
        # project, so every existing proposal type keeps working
        # unchanged." Normalisation, not validation -- must run before
        # `validate()` below, once `id` is assigned (the implicit step's
        # own id is derived from the project's id).
        record = normalize_project(record)

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
        elif _proposal_is_covered_or_closed(conn, proposal_id):
            errors.append(
                f"record.proposal_id: {proposal_id!r} is covered or closed; "
                "it needs no ruling"
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
        _check_writer_vs_routing(conn, errors, record, _proposal_type_of_ruling(conn, record.get("ruling_id")))
        _check_executor_executed(conn, errors, record)
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

            # `step_id` added handoffs/2026-09-28-dfqueue-project-step-schema.md:
            # must name a real step of `ruling_id`'s own project. Only
            # checked once `ruling_id` itself resolves to something real.
            # Resolved against the CURRENT version of the project
            # (`_current_steps_and_version`, handoffs/2026-10-01-
            # queue-bugs-and-amend.md item 3) rather than only the
            # original `project` record's own `steps`, so a step added
            # by an `amend` is a legal `step_id` here too.
            #
            # 2026-10-05 (handoffs/2026-10-05-project-before-executed.md):
            # an accepted ruling with no project is refused outright, with
            # or without a `step_id`. A charter rule alone left the live
            # queue with zero projects; the server is the boundary. Older
            # accepted rulings stay executable: `queue.project` with
            # `from_ruling` works for any accepted ruling with no project,
            # whenever it was written. Once a project exists, `step_id` is
            # required: without it no step_targets row advances and the
            # job graph never moves. An implicit-step (legacy one-step)
            # project is the one exception: it has no step id to name.
            project = None
            if ruling_payload.get("decision") == ACCEPT:
                project = _find_project_for_ruling(conn, ruling_id)
                if project is None:
                    errors.append(
                        f"record.ruling_id: {ruling_id!r} is accepted but has no "
                        "project yet, so it cannot be recorded as executed. Call "
                        f"queue.project with from_ruling={ruling_id!r} first (one "
                        "step per action, 'requires' edges where one step needs "
                        "another done first; a one-action job is a one-step "
                        "project), then call queue.executed again naming that "
                        "step's id as step_id. This also applies to an accepted "
                        "proposal from before this rule: create its project now, "
                        "then execute"
                    )
                elif record.get("step_id") is None and not all(
                    st.get("implicit") for st in _current_steps_and_version(conn, project)[0]
                ):
                    errors.append(
                        f"record.step_id: required: {ruling_id!r} has project "
                        f"{project['id']!r}; name the step this execution carries "
                        "out (call queue.project_status to see its step ids)"
                    )
            if record.get("step_id") is not None and not _project_step_ids_already_flagged(errors):
                step_id = record["step_id"]
                if project is None:
                    errors.append(
                        f"record.step_id: {ruling_id!r} has no project yet "
                        "(write a 'project' record for this ruling first)"
                    )
                else:
                    current_steps, _version = _current_steps_and_version(conn, project)
                    if step_id not in _step_ids_list(current_steps):
                        errors.append(
                            f"record.step_id: {step_id!r} is not a step of "
                            f"{project['id']!r}, the project for {ruling_id!r}"
                        )
                    else:
                        # item 2: an `executed` record for a real step
                        # must actually match that step's own
                        # declaration, not just name it -- `queue.executed`
                        # used to accept any tool for any step_id, and to
                        # accept a step whose own `requires` were not yet
                        # satisfied.
                        step = next(s for s in current_steps if s.get("id") == step_id)
                        if step.get("tool") is not None:
                            for i, action in enumerate(record.get("actions", [])):
                                if isinstance(action, dict) and action.get("tool") != step["tool"]:
                                    errors.append(
                                        f"record.actions.{i}.tool: {action.get('tool')!r} "
                                        f"does not match step {step_id!r}'s own declared "
                                        f"tool {step['tool']!r}"
                                    )

                        target_rows = conn.execute(
                            "SELECT step_id, state FROM step_targets WHERE project_id = ?",
                            (project["id"],),
                        ).fetchall()
                        target_states_by_step: dict = {}
                        for r in target_rows:
                            target_states_by_step.setdefault(r["step_id"], []).append(r["state"])
                        if not step_prerequisites_satisfied(step, target_states_by_step):
                            errors.append(
                                f"record.step_id: {step_id!r}'s own 'requires' are not "
                                "yet satisfied (see queue.project_status); it cannot be "
                                "executed until its prerequisite steps finish"
                            )

    if kind == PROJECT and not _from_ruling_already_flagged(errors):
        _check_writer_vs_routing(conn, errors, record, _proposal_type_of_ruling(conn, record.get("from_ruling")))
        from_ruling = record.get("from_ruling")
        ruling_row = conn.execute(
            "SELECT payload FROM records WHERE id = ? AND kind = ?", (from_ruling, RULING)
        ).fetchone()
        if ruling_row is None:
            errors.append(
                f"record.from_ruling: {from_ruling!r} does not refer to an "
                "existing ruling in this queue"
            )
        else:
            ruling_payload = json.loads(ruling_row["payload"])
            if ruling_payload.get("decision") != ACCEPT:
                errors.append(
                    f"record.from_ruling: {from_ruling!r} is a ruling whose "
                    f"decision is {ruling_payload.get('decision')!r}, not "
                    f"{ACCEPT!r}; only an accepted proposal has a project"
                )
            elif _find_project_for_ruling(conn, from_ruling) is not None:
                # §9: the Overseer "writes its ordered plan... before
                # executing" -- once, not per retry. A second `project`
                # for the same ruling would leave `_find_project_for_ruling`
                # ambiguous about which one an `executed`/`observation`
                # record's `step_id` belongs to.
                errors.append(
                    f"record.from_ruling: {from_ruling!r} already has a "
                    "project; a ruling gets exactly one"
                )

    if kind == AMEND and not _project_id_already_flagged(errors):
        project_id = record.get("project_id")
        _check_writer_vs_routing(conn, errors, record, _proposal_type_of_project(conn, project_id))
        proj_row = conn.execute(
            "SELECT payload FROM records WHERE id = ? AND kind = ?", (project_id, PROJECT)
        ).fetchone()
        if proj_row is None:
            errors.append(
                f"record.project_id: {project_id!r} does not refer to an "
                "existing project in this queue"
            )
        else:
            project = json.loads(proj_row["payload"])
            if conn.execute(
                "SELECT 1 FROM records WHERE kind = ? AND "
                "json_extract(payload, '$.project_id') = ?",
                (ABANDON, project_id),
            ).fetchone() is not None:
                errors.append(
                    f"record.project_id: {project_id!r} is abandoned; an "
                    "abandoned project cannot be amended"
                )
            else:
                previous_steps, _version = _current_steps_and_version(conn, project)
                previous_step_ids = _step_ids_list(previous_steps)
                new_step_ids = _step_ids_list(record.get("steps") or [])
                for name in ("replaces", "drops"):
                    for sid in record.get(name) or []:
                        if sid not in previous_step_ids:
                            errors.append(
                                f"record.{name}: {sid!r} is not a step id in the "
                                f"previous version of {project_id!r}"
                            )
                for sid in record.get("adds") or []:
                    if sid not in new_step_ids:
                        errors.append(
                            f"record.adds: {sid!r} is not a step id in this "
                            "amendment's own steps"
                        )

                # Enforced, not merely conventional (user's call,
                # 2026-10-01): a step id kept from the previous version
                # must be byte-identical to it after canonical JSON, or
                # this call is refused naming the step id. Without this,
                # a step reusing its old id while quietly changing its
                # own `targets` would leave the OLD version's now-stale
                # target rows lingering in `step_targets` forever
                # (`_seed_step_targets` only ever adds rows, never
                # prunes one a later version stopped declaring) --
                # a changed step must take a fresh id and name the old
                # one in `replaces`/`drops` instead, so its old rows are
                # left behind cleanly rather than silently reinterpreted
                # under an id that no longer means what it used to.
                previous_steps_by_id = {
                    s["id"]: s for s in previous_steps
                    if isinstance(s, dict) and isinstance(s.get("id"), str) and s["id"]
                }
                for step in record.get("steps") or []:
                    if not (isinstance(step, dict) and isinstance(step.get("id"), str) and step["id"]):
                        continue
                    sid = step["id"]
                    prev_step = previous_steps_by_id.get(sid)
                    if prev_step is not None and _canonical_step_json(step) != _canonical_step_json(prev_step):
                        errors.append(
                            f"record.steps: {sid!r} reuses a step id from the "
                            "previous version but its own definition changed; "
                            "a changed step must take a fresh id and list the "
                            "old one in replaces/drops, never redefine an "
                            "existing id in place"
                        )

    if kind == AMEND and not _project_id_already_flagged(errors):
        _check_amend_base(conn, errors, record)

    if kind == CLOSE:
        _check_close(conn, errors, record)

    if kind == ABANDON and not _project_id_already_flagged(errors):
        project_id = record.get("project_id")
        proj_row = conn.execute(
            "SELECT 1 FROM records WHERE id = ? AND kind = ?", (project_id, PROJECT)
        ).fetchone()
        if proj_row is None:
            errors.append(
                f"record.project_id: {project_id!r} does not refer to an "
                "existing project in this queue"
            )
        elif conn.execute(
            "SELECT 1 FROM records WHERE kind = ? AND "
            "json_extract(payload, '$.project_id') = ?",
            (ABANDON, project_id),
        ).fetchone() is not None:
            errors.append(
                f"record.project_id: {project_id!r} is already abandoned"
            )

    if kind == OBSERVATION:
        project = None
        if not _project_step_ids_already_flagged(errors):
            project_id = record.get("project_id")
            row = conn.execute(
                "SELECT payload FROM records WHERE id = ? AND kind = ?",
                (project_id, PROJECT),
            ).fetchone()
            if row is None:
                errors.append(
                    f"record.project_id: {project_id!r} does not refer to an "
                    "existing project in this queue"
                )
            else:
                project = json.loads(row["payload"])
                step_id = record.get("step_id")
                if step_id not in _step_ids_list(_current_steps_and_version(conn, project)[0]):
                    errors.append(
                        f"record.step_id: {step_id!r} is not a step of "
                        f"{project_id!r}"
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
            "SELECT payload FROM records WHERE id = ? AND kind = ?", (ask_id, ASK)
        ).fetchone()
        if ask_row is not None:
            addressee = ask_addressee(json.loads(ask_row["payload"]))
            if record.get("role") != addressee:
                errors.append(
                    f"record.role: {ask_id!r} is addressed to {addressee!r}; "
                    f"only its addressee may answer it, got {record.get('role')!r}"
                )
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

    if kind == FORT_PLAN and not errors:
        _check_fort_plan(conn, errors, record, game_tick)

    duplicate_reason: str | None = None
    if kind == PROPOSAL:
        _check_proposal_routing(conn, errors, record)
        _check_serves(conn, errors, record)
        _check_plan_change_rate(conn, errors, record, game_tick)
        if isinstance(game_tick, bool) or not isinstance(game_tick, int):
            errors.append(
                "game_tick: a proposal must be appended with an integer "
                f"game_tick (its prediction's due_game_tick depends on it), got {game_tick!r}"
            )

        if not errors:
            structural = _find_structural_duplicate(conn, record)
            if structural is not None:
                errors.append(f"record.step: {structural}")

        if record.get("duplicate_of") is not None and not _duplicate_of_already_flagged(errors):
            # A caller (or a re-append) already set duplicate_of itself;
            # validate it the same way a ruling's proposal_id is
            # validated -- must name a real proposal already here.
            found = conn.execute(
                "SELECT 1 FROM records WHERE id = ? AND kind = ?",
                (record["duplicate_of"], PROPOSAL),
            ).fetchone()
            if found is None:
                errors.append(
                    f"record.duplicate_of: {record['duplicate_of']!r} does not "
                    "refer to an existing proposal in this queue"
                )
        elif "duplicate_of" not in record and not errors:
            # `handoffs/2026-09-28-queue-duplicate-proposal-check.md`:
            # never silently refuse a duplicate (unlike gotchas) -- still
            # write it, but flag it so the Overseer's ruling and the
            # history can see the relationship. Only run once the record
            # is otherwise valid: a malformed `type`/`summary` is
            # reported as its own error, not compared against anything.
            found_dup = _find_duplicate_proposal(conn, record)
            if found_dup is not None:
                dup_id, duplicate_reason = found_dup
                record["duplicate_of"] = dup_id

    if errors:
        raise QueueError("refusing to append an invalid record:\n  " + "\n  ".join(errors))

    with _write_txn(conn, commit):  # one transaction: commits on success, rolls back on any exception
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
            if record.get("proposal_id") is None:
                # Legacy rule (Overseer-written): the window starts at the
                # first execution. An executor step's proposal arms when the
                # step reaches `done` instead, never on a failure.
                _arm_prediction_on_first_execution(conn, record)
            _apply_executed_target_states(conn, record)
        elif kind == PROJECT:
            _seed_step_targets(conn, record["id"], record.get("steps", []))
        elif kind == AMEND:
            _seed_step_targets(conn, record["project_id"], record.get("steps", []))
        elif kind == OBSERVATION:
            _apply_observation(conn, record)
        elif kind == FORT_PLAN and record.get("ruling_id"):
            # The accepted plan_change this version cites is spent: closed
            # `completed` by the store (design F-9), so it is neither the
            # Overseer's to-do nor citable twice.
            _close_conn(
                conn, "ruling_id", record["ruling_id"], CLOSE_COMPLETED,
                f"filed as plan version {record['version']}", None, record["cycle"], record["snapshot"],
            )

    if duplicate_reason is not None:
        # The reason is reported to the caller of THIS append() so the
        # tool layer can surface it in the write's own result -- it is
        # not persisted (only `duplicate_of`, a real schema field, is:
        # see `_insert_record` above, called before this copy is made).
        return {**record, "duplicate_reason": duplicate_reason}
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


# ---- target-level state fold (design §4.4/§4.5) -----------------------------
#
# `handoffs/2026-09-28-dfqueue-project-step-schema.md` item 4: "fold from
# append-only records into a materialised table the same way `predictions`
# already works." `records` (the append-only log) stays the single source of
# truth; `step_targets` is a derived, updated-in-place projection of it,
# maintained incrementally inside the SAME transaction as the record that
# changes it -- exactly `predictions`'s own pattern, never a periodic
# rebuild.


def _seed_step_targets(conn: sqlite3.Connection, project_id: str, steps: list) -> None:
    """Called once, when a `project` record is inserted (`project_id` is its
    own id, `steps` its own `steps`), and again for each `amend` record
    (`project_id` is the ORIGINAL project's id it names, `steps` the
    amendment's own new steps -- `handoffs/2026-10-01-queue-bugs-and-amend.md`
    item 3): for every step whose `targets` is a literal `set` (not a
    `from_step`/query spec, which has no targets known yet -- design §4.3's
    dynamic-discovery case), insert one row per declared target at `ready`
    (no `requires`) or `waiting` (an unmet `requires` edge). `INSERT OR
    IGNORE` below is what makes calling this a second time for an amendment
    safe: a target already seeded by an earlier version (or already folded
    to some other state by an `executed` record) is left exactly as it is;
    only a target this call is the FIRST to mention gets a fresh `ready`/
    `waiting` row. A step's `requires` is checked against every OTHER step
    in the same project having at least one target row already
    `done`/`abandoned` -- but at seed time nothing new has run yet, so any
    step with a non-empty `requires` starts `waiting` unconditionally;
    `all_done` vs `all_success` and requires-satisfaction are evaluated at
    read time (`project_status`/`append`'s own `executed` validation below),
    not baked into the seed.
    """
    for step in steps:
        targets = step.get("targets", {})
        target_set = targets.get("set") if isinstance(targets, dict) else None
        if not target_set:
            continue  # dynamic (`from_step`) or the empty implicit-step set
        initial_state = WAITING if step.get("requires") else READY
        for target in target_set:
            conn.execute(
                "INSERT OR IGNORE INTO step_targets "
                "(project_id, step_id, target, state, reason, last_tick) "
                "VALUES (?, ?, ?, ?, NULL, NULL)",
                (project_id, step["id"], str(target), initial_state),
            )


def _apply_executed_target_states(conn: sqlite3.Connection, record: dict) -> None:
    """Called for every `executed` record that carries a `step_id`: each of
    its `actions` that names `targets` + `target_state` (schema.py's
    both-or-neither pair) upserts that target's row in `step_targets`,
    recording `record["cycle"]` (the execution tick) as `last_tick` --
    `rollback_drift` below compares this against the fort's current tick.
    An `executed` record with no `step_id` (every pre-existing record, and
    an implicit-step project's own executions) touches nothing here, which
    is deliberate: there is nothing at that granularity to fold.
    """
    step_id = record.get("step_id")
    if step_id is None:
        return
    project = _find_project_for_ruling(conn, record["ruling_id"])
    if project is None:  # pragma: no cover -- append() already refused this
        return
    project_id = project["id"]
    tick = record["cycle"]

    for action in record.get("actions", []):
        targets = action.get("targets")
        state = action.get("target_state")
        if not targets or state is None:
            continue
        reason = action.get("detail")
        for target in targets:
            conn.execute(
                "INSERT INTO step_targets "
                "(project_id, step_id, target, state, reason, last_tick) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(project_id, step_id, target) DO UPDATE SET "
                "state = excluded.state, reason = excluded.reason, "
                "last_tick = excluded.last_tick",
                (project_id, step_id, str(target), state, reason, tick),
            )


#: States that count as "finished, with any outcome" for an `all_done`
#: trigger (design §2.2). `held`/`issued`/`waiting`/`ready` do not.
_FINISHED_STATES = (DONE, FAILED, ABANDONED)


def step_prerequisites_satisfied(step: dict, target_states_by_step: dict) -> bool:
    """True if every step id in `step['requires']` counts as finished, per
    THIS step's own `trigger` (design §2.2: the trigger belongs to the
    dependent step, applied to its prerequisites) -- `all_success` (default)
    requires every one of a prerequisite's own targets to be `done`;
    `all_done` only requires each to have reached ANY finished state
    (`done`/`failed`/`abandoned`): "mine the vein" can end with some tiles
    unmineable and the wall step should still run on the ones that were.

    `target_states_by_step` maps a step id to the list of its targets'
    current state strings (`target_states()`'s own rows, grouped by
    `step_id`) -- a required step with no tracked targets at all yet (never
    seeded, or a `from_step` step whose predecessor has not run) is treated
    as NOT satisfied, never vacuously true.
    """
    trigger = step.get("trigger", TRIGGER_ALL_SUCCESS)
    for req in step.get("requires", []):
        states = target_states_by_step.get(req)
        if not states:
            return False
        if trigger == TRIGGER_ALL_DONE:
            if not all(s in _FINISHED_STATES for s in states):
                return False
        elif not all(s == DONE for s in states):
            return False
    return True


def target_states(path: str | Path, project_id: str) -> list[dict]:
    """Every `step_targets` row for `project_id`, in insertion order --
    "4 of 5 issued, 1 held" made queryable, per design §4.4's own example.
    """
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT step_id, target, state, reason, last_tick FROM step_targets "
            "WHERE project_id = ? ORDER BY id ASC",
            (project_id,),
        ).fetchall()
    return [
        {
            "step_id": r["step_id"], "target": r["target"], "state": r["state"],
            "reason": r["reason"], "last_tick": r["last_tick"],
        }
        for r in rows
    ]


def rollback_drift(path: str | Path, project_id: str, current_tick: int) -> list[dict]:
    """design §4.4, "Rollback": every target of `project_id` whose latest
    recorded `last_tick` is AFTER `current_tick` -- the fort's own absolute
    tick, read live and passed in by the caller; this function never calls
    out to DFHack itself (keeps the queue store's existing separation from
    any live-game access intact, per the handoff). Each entry is tagged
    `contradicted: world_rolled_back`, matching design §2.3/§4.4's
    three-valued observation vocabulary -- this is the code-computable half
    of that call; the fuller "and re-observe" half is the reconciler's job
    (out of scope here, see this handoff's Result section).
    """
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT step_id, target, state, last_tick FROM step_targets "
            "WHERE project_id = ? AND last_tick IS NOT NULL AND last_tick > ? "
            "ORDER BY id ASC",
            (project_id, current_tick),
        ).fetchall()
    return [
        {
            "step_id": r["step_id"], "target": r["target"],
            "recorded_state": r["state"], "recorded_tick": r["last_tick"],
            "current_tick": current_tick, "status": "contradicted",
            "reason": "world_rolled_back",
        }
        for r in rows
    ]


#: A project-level status distinct from `"active"`/`"done"`: an `abandon`
#: record exists for it (`handoffs/2026-10-01-queue-bugs-and-amend.md` item
#: 3). Reuses the `ABANDONED` target-state string on purpose -- both mean
#: "closed, not by finishing" -- rather than inventing a second constant
#: for the same idea at a different granularity.
PROJECT_ABANDONED = ABANDONED


def step_status(target_states_for_step: list, has_executed_record: bool) -> str:
    """One step's own status (design §6, extended by
    `handoffs/2026-10-01-queue-bugs-and-amend.md` item 1): `done` when it
    has tracked target rows and every one of them is `done`/`abandoned`, OR
    when it has NO target rows at all (an implicit step, whose `targets` is
    always the empty `{"set": []}`; or a real step whose `targets` is a
    dynamic `from_step` spec, never seeded -- design §4.3) but an `executed`
    record already covers it; `"active"` otherwise.

    This is deliberately never vacuously `"done"` on an empty list the way
    `project_status` used to compute it: `all(state in (DONE, ABANDONED)
    for state in [])` is `True` in Python, so a step never seeded at all
    used to read `done` by construction, and a project whose only OTHER
    steps had finished read `done` right along with it -- the exact bug
    item 1 fixes. A no-rows step reads `done` only from a positive signal
    (`has_executed_record`), never from the absence of rows to check.
    """
    if target_states_for_step:
        return DONE if all(s in (DONE, ABANDONED) for s in target_states_for_step) else "active"
    return DONE if has_executed_record else "active"


def _step_has_executed_record(conn: sqlite3.Connection, ruling_id: str, step: dict) -> bool:
    """Whether some `executed` record already covers `step` of the project
    whose ruling is `ruling_id` -- the positive signal `step_status` above
    needs for a step with no target rows yet. An implicit step (`design
    §5.3`'s legacy one-step project) is covered by ANY `executed` record
    naming this ruling, since those carry no `step_id` at all; a real step
    is covered only by an `executed` record naming its own `step_id`
    specifically."""
    if step.get("implicit"):
        row = conn.execute(
            "SELECT 1 FROM records WHERE kind = ? AND "
            "json_extract(payload, '$.ruling_id') = ?",
            (EXECUTED, ruling_id),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT 1 FROM records WHERE kind = ? AND "
            "json_extract(payload, '$.ruling_id') = ? AND "
            "json_extract(payload, '$.step_id') = ?",
            (EXECUTED, ruling_id, step.get("id")),
        ).fetchone()
    return row is not None


def project_status(path: str | Path, project_id: str) -> dict:
    """One project's status line, design §6: "the Overseer sees one line per
    active project (status, counts, the top blocker's reason)". Never the
    whole graph.

    `status` is computed per STEP (`step_status` above), then folded: `done`
    only when every step currently in the plan is itself `done`; `active`
    otherwise; `"abandoned"` (`PROJECT_ABANDONED`) once an `abandon` record
    exists for this project, regardless of step state -- checked first, and
    short-circuits the rest (`handoffs/2026-10-01-queue-bugs-and-amend.md`
    item 3). `counts`/`top_blocker` are read from the raw `step_targets`
    rows exactly as before and are NOT remapped on an abandoned project:
    they report what the game actually reached, not a retroactive rewrite
    of it (executed history stays untouched by an `abandon`, per that
    item's own wording; see this handoff's Result section for this call).

    The steps read are the CURRENT version's (`_current_steps_and_version`):
    the original `project`'s own `steps` if it has never been amended, else
    the latest `amend`'s own `steps` -- `version` in the returned dict names
    which one (1 for the original, 2 for the first amendment, and so on).
    A step a later amendment dropped is simply absent from that latest
    `steps` list, so it stops counting toward "is this project done" without
    any special-casing here.
    """
    with _connect(path) as conn:
        return _project_status_conn(conn, project_id)


def _project_status_conn(conn: sqlite3.Connection, project_id: str) -> dict:
    """`project_status` on an open connection (also used by `open_projects`
    and the legacy listing, which already hold one)."""
    proj_row = conn.execute(
        "SELECT payload FROM records WHERE id = ? AND kind = ?", (project_id, PROJECT)
    ).fetchone()
    if proj_row is None:
        raise QueueError(f"no such project: {project_id!r}")
    project = json.loads(proj_row["payload"])

    abandon_row = conn.execute(
        "SELECT payload FROM records WHERE kind = ? AND "
        "json_extract(payload, '$.project_id') = ?",
        (ABANDON, project_id),
    ).fetchone()

    steps, version = _current_steps_and_version(conn, project)

    rows = conn.execute(
        "SELECT id, step_id, target, state, reason FROM step_targets "
        "WHERE project_id = ? ORDER BY id ASC",
        (project_id,),
    ).fetchall()

    counts: dict[str, int] = {}
    top_blocker = None
    rows_by_step: dict = {}
    for r in rows:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
        rows_by_step.setdefault(r["step_id"], []).append(r["state"])
        if top_blocker is None and r["state"] == HELD:
            top_blocker = {"step_id": r["step_id"], "target": r["target"], "reason": r["reason"]}

    if abandon_row is not None:
        status = PROJECT_ABANDONED
        abandoned_reason = json.loads(abandon_row["payload"]).get("reason")
    else:
        abandoned_reason = None
        ruling_id = project["from_ruling"]
        all_done = True
        for step in steps:
            if not (isinstance(step, dict) and isinstance(step.get("id"), str) and step["id"]):
                continue
            own_rows = rows_by_step.get(step["id"], [])
            has_executed = own_rows == [] and _step_has_executed_record(conn, ruling_id, step)
            if step_status(own_rows, has_executed) != DONE:
                all_done = False
                break
        status = "done" if all_done else "active"

    result = {
        "project_id": project_id,
        "summary": project.get("summary"),
        "status": status,
        "version": version,
        "counts": counts,
        "top_blocker": top_blocker,
    }
    if abandoned_reason is not None:
        result["abandoned_reason"] = abandoned_reason
    return result


def list_project_ids(path: str | Path) -> list[str]:
    """Every `project` record's own id, oldest first (insertion order).

    Added `handoffs/2026-09-30-project-mcp-tools.md` for `queue.project_status`'s
    "one line per project" read (design §6) -- there is no separate index of
    project ids, and `project_status` above needs one project id at a time, so
    a caller wanting every project's line must enumerate ids first, then call
    `project_status` per id (the same two-step shape `queue.overview`'s own
    caller already uses for `pending_proposals`/`open_asks`, just against a
    kind with no dedicated "still open" predicate: a project's own `status`
    field, "active" or "done", is computed by `project_status`, not knowable
    from the raw record alone)."""
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT id FROM records WHERE kind = ? ORDER BY rowid ASC", (PROJECT,)
        ).fetchall()
    return [r["id"] for r in rows]


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


def recent_rulings(path: str | Path, n: int) -> list[dict]:
    """The `n` most recent `ruling` records, newest first (the ruling
    briefing's "decided, do not redo" list)."""
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT payload FROM records WHERE kind = ? ORDER BY ts DESC, rowid DESC LIMIT ?",
            (RULING, n),
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
            "SELECT p.id, p.record_id, p.signal, p.op, p.value, p.registered_game_tick, "
            "p.due_game_tick, p.status, p.actual_value, p.graded_at, p.grade_note, "
            "r.role AS proposer FROM predictions p LEFT JOIN records r ON r.id = p.record_id "
            "WHERE p.status = ? AND p.due_game_tick <= ? ORDER BY p.due_game_tick ASC, p.id ASC",
            (PENDING, tick),
        ).fetchall()
    # `proposer`: the role that filed the proposal carrying the prediction (the
    # conductor wakes only that role on a miss, handoffs/2026-10-07-wake-cleanup.md).
    return [{**_prediction_row(r), "proposer": r["proposer"]} for r in rows]


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
        ") AND json_extract(r.payload, '$.covered_by') IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM records c WHERE c.kind = ? AND "
        "json_extract(c.payload, '$.proposal_id') = r.id) "
        "ORDER BY r.ts ASC, r.rowid ASC"
    )
    params: list = [PROPOSAL, RULING, *FINAL_DECISIONS, CLOSE]
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    with _connect(path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [json.loads(r["payload"]) for r in rows]


def open_asks(
    path: str | Path, limit: int | None = None, to: str | None = None,
) -> list[dict]:
    """Every `ask` record with no `answer` yet, oldest first -- the
    Consultant's own read (`dfmcp/queue_tools.py`'s `queue.pending`, for
    role `consultant`, branches to this instead of `pending_proposals`:
    the Consultant never proposes, so "what's pending for me" means open
    questions, not proposals). Same "no threads" contract `append()`
    enforces at write time: at most one `answer` per `ask`, so "open" here
    just means "answer count is zero", no defer-like open/closed
    distinction to track.

    `to` (an answerer role) keeps only asks addressed to it; an ask with no
    `to` is the Consultant's (`schema.ask_addressee`). `None` lists every
    open ask regardless of addressee (`queue.overview`, the conductor).
    """
    query = (
        "SELECT a.payload FROM records a WHERE a.kind = ? AND NOT EXISTS ("
        "SELECT 1 FROM records r WHERE r.kind = ? AND "
        "json_extract(r.payload, '$.ask_id') = a.id"
        ") ORDER BY a.ts ASC, a.rowid ASC"
    )
    params: list = [ASK, ANSWER]
    with _connect(path) as conn:
        rows = conn.execute(query, params).fetchall()
    asks = [json.loads(r["payload"]) for r in rows]
    if to is not None:
        asks = [a for a in asks if ask_addressee(a) == to]
    return asks[:limit] if limit is not None else asks


def unexecuted_accepted_proposals(path: str | Path) -> list[dict]:
    """Every proposal whose ruling was `accept` but that has no `executed`
    record yet, oldest proposal first. `docs/AGENT-LOOP.md` item 4: "an
    accepted but never-executed proposal is never graded as a miss, it is
    reported as unexecuted" -- this is that report. `dfqueue/grade.py`'s
    `run_grading_cycle` calls this every time it grades, alongside (never
    instead of) `pending_due`'s real misses/hits.

    `docs/CONDUCTOR-EXECUTION.md` 6.1 (P3-B1, P2-M3): **unrouted types only**
    (a routed proposal is the conductor's, never the Overseer's to-do), keyed
    by the proposal's own id (an `executed` covers it by `proposal_id`, or by
    its ruling's id for the Overseer's own records), excluding a follow-up's
    ruling (its step belongs to the parent project) and any ruling a `close`
    has closed (the 2a legacy sweep).

    Each entry is `{"proposal": <the proposal record>, "ruling_id": <the
    accepting ruling's id>}` -- the ruling id is what a caller would pass
    to `queue.executed` next, so it is handed over rather than making the
    caller re-derive it.
    """
    query = (
        "SELECT p.id AS proposal_id, p.payload AS proposal_payload, rl.id AS ruling_id "
        "FROM records p "
        "JOIN records rl ON rl.kind = ? AND rl.proposal_id = p.id "
        "AND json_extract(rl.payload, '$.decision') = ? "
        "WHERE p.kind = ? AND NOT EXISTS ("
        "SELECT 1 FROM records ex WHERE ex.kind = ? AND "
        "(json_extract(ex.payload, '$.ruling_id') = rl.id "
        "OR json_extract(ex.payload, '$.proposal_id') = p.id)"
        ") AND NOT EXISTS ("
        "SELECT 1 FROM records c WHERE c.kind = ? AND "
        "(json_extract(c.payload, '$.ruling_id') = rl.id "
        "OR json_extract(c.payload, '$.proposal_id') = p.id)"
        ") ORDER BY p.ts ASC, p.rowid ASC"
    )
    with _connect(path) as conn:
        rows = conn.execute(query, (RULING, ACCEPT, PROPOSAL, EXECUTED, CLOSE)).fetchall()
    out = []
    for r in rows:
        proposal = json.loads(r["proposal_payload"])
        if routing.is_routed(proposal.get("type")):
            continue
        if routing.is_ruling_only(proposal.get("type")):
            continue  # nothing executes it (design F-9); see `plan_changes_awaiting`
        if proposal.get("project_id") is not None:
            continue  # a follow-up: its step is the parent project's
        out.append({"proposal": proposal, "ruling_id": r["ruling_id"]})
    return out


#: Lifecycle states `own_filings` reports for a proposal. `in_project` is
#: reported with the project id and its step state beside it.
FILING_STATUSES = (
    "pending", "accepted", "rejected", "deferred", "closed", "completed", "in_project",
)


def _filing_row(conn: sqlite3.Connection, proposal: dict) -> dict:
    """One proposal's own-filing line: its lifecycle status computed from the
    records that name it (rulings, a project opened from its accepting ruling,
    an `executed`, a `close`), never from a stored flag."""
    pid = proposal["id"]
    rulings = [
        json.loads(r["payload"]) for r in conn.execute(
            "SELECT payload FROM records WHERE kind = ? AND proposal_id = ? ORDER BY rowid ASC",
            (RULING, pid),
        ).fetchall()
    ]
    latest = rulings[-1] if rulings else None
    final = next((r for r in rulings if r.get("decision") in FINAL_DECISIONS), None)
    row = {
        "id": pid, "type": proposal.get("type"), "summary": proposal.get("summary"),
        "urgency": proposal.get("suggested_priority") or proposal.get("urgency"),
        "ruling": ({"id": latest["id"], "decision": latest.get("decision"), "reason": latest.get("reason")}
                   if latest else None),
        "project_id": proposal.get("project_id"), "close": None,
    }
    project = None
    if final is not None and final.get("decision") == ACCEPT:
        project = _find_project_for_ruling(conn, final["id"])
    if project is None and proposal.get("project_id"):
        project = _get(conn, proposal["project_id"], PROJECT)
    if project is not None:
        row["project_id"] = project["id"]
        row["project_status"] = _project_status_conn(conn, project["id"])["status"]
    # A `close` names exactly one of the proposal, its accepting ruling or its
    # project; any of the three closes this filing.
    keys = [("proposal_id", pid)]
    if final is not None:
        keys.append(("ruling_id", final["id"]))
    if project is not None:
        keys.append(("project_id", project["id"]))
    close_row = None
    for field, value in keys:
        close_row = conn.execute(
            f"SELECT payload FROM records WHERE kind = ? AND json_extract(payload, '$.{field}') = ? "
            "ORDER BY rowid DESC", (CLOSE, value),
        ).fetchone()
        if close_row is not None:
            break
    if close_row is not None:
        c = json.loads(close_row["payload"])
        row["close"] = {"outcome": c.get("outcome"), "reason": c.get("reason")}
        row["status"] = "closed"
    elif final is None:
        row["status"] = "deferred" if latest is not None else "pending"
        if proposal.get("covered_by") is not None and project is None:
            row["status"] = "accepted"
    elif final.get("decision") == REJECT:
        row["status"] = "rejected"
    elif project is not None:
        row["status"] = "completed" if row["project_status"] == "done" else "in_project"
    elif _executed_exists(conn, final["id"]):
        row["status"] = "completed"
    else:
        row["status"] = "accepted"
    return row


def own_filings(
    path: str | Path, role: str, *, status: str | None = None,
    proposal_id: str | None = None, limit: int | None = None,
) -> list[dict]:
    """The proposals `role` itself filed, newest first, each with a computed
    lifecycle status (`FILING_STATUSES`). The role is the caller's, never a
    caller-chosen argument one layer up: this function filters on it so no
    other role's proposal can be returned. `status` keeps one state;
    `proposal_id` one record (still only if it is `role`'s own)."""
    where, params = "kind = ? AND role = ?", [PROPOSAL, role]
    if proposal_id is not None:
        where += " AND id = ?"
        params.append(proposal_id)
    with _connect(path) as conn:
        rows = conn.execute(
            f"SELECT payload FROM records WHERE {where} ORDER BY ts DESC, rowid DESC", params
        ).fetchall()
        out = []
        for r in rows:
            line = _filing_row(conn, json.loads(r["payload"]))
            if status is not None and line["status"] != status:
                continue
            out.append(line)
            if limit is not None and len(out) >= limit:
                break
    return out


def own_asks(path: str | Path, role: str, *, limit: int | None = None) -> list[dict]:
    """The asks `role` itself filed, newest first, each with its answer's text
    when it has one: `{id, to, question, proposal_id, status, answer_id,
    answer}`, `status` `open` or `answered`. Filtered on `role` here, so no
    other role's ask (or the answer to it) can be returned."""
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT payload FROM records WHERE kind = ? AND role = ? ORDER BY ts DESC, rowid DESC",
            (ASK, role),
        ).fetchall()
        out = []
        for r in rows:
            ask = json.loads(r["payload"])
            ans = conn.execute(
                "SELECT payload FROM records WHERE kind = ? AND json_extract(payload, '$.ask_id') = ? "
                "ORDER BY rowid ASC", (ANSWER, ask["id"]),
            ).fetchone()
            answer = json.loads(ans["payload"]) if ans is not None else None
            out.append({
                "id": ask["id"], "to": ask_addressee(ask), "question": ask.get("question"),
                "proposal_id": ask.get("proposal_id"),
                "status": "answered" if answer is not None else "open",
                "answer_id": answer["id"] if answer else None,
                "answer": answer.get("answer") if answer else None,
            })
            if limit is not None and len(out) >= limit:
                break
    return out


#: Statuses a briefing always carries regardless of age: work the role can
#: still duplicate (accepted or in a project but not done, deferred, pending).
FILINGS_ALWAYS_SHOWN = ("pending", "accepted", "deferred", "in_project")


def briefing_filings(path: str | Path, role: str, recent: int) -> list[dict]:
    """The filings a role's briefing shows: its `recent` newest, plus every
    one in `FILINGS_ALWAYS_SHOWN` however old. Newest first, no repeats."""
    rows = own_filings(path, role)
    keep = [f for i, f in enumerate(rows) if i < recent or f["status"] in FILINGS_ALWAYS_SHOWN]
    return keep


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
# Stage 2A: the executor's queue model (handoffs/2026-10-05-stage-2a.md,
# docs/CONDUCTOR-EXECUTION.md section 6.1).
#
# What this adds, in one place: routed-type checks at write time, the
# executor's own writes (`open_project_from_ruling`, `apply_followup`,
# `begin/finish/resolve_step_run`, `record_observation`, `close`), the legacy
# cutover and sweep (`set_cutover`, `legacy_targets`, `close_legacy`), and the
# one definition of an open project (`open_projects`). Nothing here calls
# DFHack. Nothing is routed until `dfqueue/action_tools.yaml` says so.
#
# Completion rule (one rule, both readers agree): a routed step has one
# synthetic target, the step's own id. `executed` moves it `issued` (or
# `held`/`failed`), and only an `observation` with `done: true` moves it
# `done`, which is what `step_prerequisites_satisfied` and `step_status`
# already read.
# ---------------------------------------------------------------------------

LEGACY = routing.LEGACY_GROUP

#: Statuses of a `step_runs` row (docs/CONDUCTOR-EXECUTION.md 4.1, 4.2).
RUN_ISSUING = "issuing"      # marker written, the real call may or may not have landed
RUN_RECORDED = "recorded"    # the call returned and its `executed` record is appended
RUN_RESOLVED = "resolved"    # an Uncertain run settled as success by a `landed` read
RUN_VOID = "void"            # an Uncertain run settled as "nothing landed": retryable
RUN_HELD = "held"            # unreadable: blocks the step until a person or close
RUN_STATUSES = (RUN_ISSUING, RUN_RECORDED, RUN_RESOLVED, RUN_VOID, RUN_HELD)
#: What `resolve_step_run` accepts.
RESOLVE_OUTCOMES = ("success", "transient", "held")
CLEANUP_PREFIX = "cleanup:"


def _num(record_id: str) -> int:
    """The number in `ruling-0007` (queue order of rulings)."""
    try:
        return int(str(record_id).rsplit("-", 1)[1])
    except (IndexError, ValueError):
        raise QueueError(f"not a queue id: {record_id!r}") from None


def _get(conn: sqlite3.Connection, record_id, kind: str) -> dict | None:
    if not isinstance(record_id, str):
        return None
    row = conn.execute(
        "SELECT payload FROM records WHERE id = ? AND kind = ?", (record_id, kind)
    ).fetchone()
    return json.loads(row["payload"]) if row is not None else None


def _proposal_of_ruling(conn: sqlite3.Connection, ruling_id) -> dict | None:
    ruling = _get(conn, ruling_id, RULING)
    return _get(conn, ruling["proposal_id"], PROPOSAL) if ruling else None


def _proposal_type_of_ruling(conn: sqlite3.Connection, ruling_id) -> str | None:
    p = _proposal_of_ruling(conn, ruling_id)
    return p.get("type") if p else None


def _proposal_type_of_project(conn: sqlite3.Connection, project_id) -> str | None:
    project = _get(conn, project_id, PROJECT)
    return _proposal_type_of_ruling(conn, project["from_ruling"]) if project else None


def _is_closed(conn: sqlite3.Connection, field: str, record_id: str) -> bool:
    return conn.execute(
        f"SELECT 1 FROM records WHERE kind = ? AND json_extract(payload, '$.{field}') = ?",
        (CLOSE, record_id),
    ).fetchone() is not None


def _is_abandoned(conn: sqlite3.Connection, project_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM records WHERE kind = ? AND json_extract(payload, '$.project_id') = ?",
        (ABANDON, project_id),
    ).fetchone() is not None


def _proposal_is_covered_or_closed(conn: sqlite3.Connection, proposal_id: str) -> bool:
    p = _get(conn, proposal_id, PROPOSAL)
    if p is not None and p.get("covered_by") is not None:
        return True
    return _is_closed(conn, "proposal_id", proposal_id)


def _latest_cycle(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MAX(cycle) AS c FROM records").fetchone()
    return int(row["c"] or 0)


def _canon(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _has_final_ruling(conn: sqlite3.Connection, proposal_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM records WHERE kind = ? AND proposal_id = ? "
        "AND json_extract(payload, '$.decision') IN (?, ?)",
        (RULING, proposal_id, *FINAL_DECISIONS),
    ).fetchone() is not None


def _accepting_ruling(conn: sqlite3.Connection, proposal_id: str) -> dict | None:
    row = conn.execute(
        "SELECT payload FROM records WHERE kind = ? AND proposal_id = ? "
        "AND json_extract(payload, '$.decision') = ? ORDER BY rowid ASC",
        (RULING, proposal_id, ACCEPT),
    ).fetchone()
    return json.loads(row["payload"]) if row is not None else None


# ---- checks run inside `_append_in_conn` ----------------------------------------


def _check_writer_vs_routing(conn, errors: list[str], record: dict, ptype) -> None:
    """P3-B1: the sole writer may not write a `project`, `executed` or
    `amend` for a routed type; the executor may write them only for one.
    Skipped when the proposal type cannot be resolved (a dangling reference
    is already its own error)."""
    if ptype is None:
        return
    role = record.get("role")
    routed = routing.is_routed(ptype)
    writer, runner = sole_writer(), executor()
    if role == writer and role != runner and routed:
        errors.append(
            f"record.role: {ptype!r} is a routed proposal type; the conductor "
            f"runs it, so the {writer!r} may not write a {record.get('kind')} for it "
            "(docs/CONDUCTOR-EXECUTION.md 1, P3-B1)"
        )
    if role == runner and role != writer and not routed:
        errors.append(
            f"record.role: {ptype!r} is not a routed proposal type; the "
            f"{runner!r} writes a {record.get('kind')} only for a routed one"
        )


def _check_executor_executed(conn, errors: list[str], record: dict) -> None:
    """An executor-written `executed` is one step's real call: it names the
    step and that step's own `proposal_id`, and its actions may only move
    the step's synthetic target to `issued`, `held` or `failed` (only an
    observation makes it `done`)."""
    if record.get("role") != executor() or executor() == sole_writer():
        return
    project = _find_project_for_ruling(conn, record.get("ruling_id"))
    step_id = record.get("step_id")
    if project is None or step_id is None:
        return  # reported by the existing project/step_id checks
    step = next(
        (st for st in _current_steps_and_version(conn, project)[0] if st.get("id") == step_id),
        None,
    )
    if step is None:
        return
    if step.get("proposal_id") is None:
        errors.append(
            f"record.step_id: {step_id!r} was not built by the executor (it carries "
            "no proposal_id), so the executor may not record it"
        )
    elif record.get("proposal_id") != step["proposal_id"]:
        errors.append(
            f"record.proposal_id: must be the step's own proposal "
            f"{step['proposal_id']!r}, got {record.get('proposal_id')!r}"
        )
    for i, action in enumerate(record.get("actions") or []):
        if not isinstance(action, dict):
            continue
        state = action.get("target_state")
        if state is None:
            continue
        if state not in (ISSUED, HELD, FAILED):
            errors.append(
                f"record.actions.{i}.target_state: an executor records {ISSUED!r}, "
                f"{HELD!r} or {FAILED!r}; only an observation makes a step {DONE!r}"
            )
        if action.get("targets") != [step_id]:
            errors.append(
                f"record.actions.{i}.targets: must be exactly [{step_id!r}] (the "
                "step's synthetic target)"
            )


def _check_amend_base(conn, errors: list[str], record: dict) -> None:
    """P2-L1: an amend is a whole plan, so one built from a stale base would
    silently drop a step. Every step of the previous version must be kept
    or named in `drops` or `replaces`."""
    project = _get(conn, record.get("project_id"), PROJECT)
    if project is None or not isinstance(record.get("steps"), list):
        return
    previous = _step_ids_list(_current_steps_and_version(conn, project)[0])
    kept = _step_ids_list(record["steps"])
    named = set(record.get("drops") or []) | set(record.get("replaces") or [])
    for sid in sorted(previous - kept - named):
        errors.append(
            f"record.steps: omits step {sid!r} of the previous version without "
            "naming it in drops or replaces (an amend carries the whole plan; "
            "re-read the project and build from its latest version)"
        )


def _check_close(conn, errors: list[str], record: dict) -> None:
    for field in ("project_id", "proposal_id", "ruling_id"):
        if field not in record:
            continue
        tid = record[field]
        if not isinstance(tid, str) or not tid:
            return
        if field == "project_id":
            if _get(conn, tid, PROJECT) is None:
                errors.append(f"record.project_id: {tid!r} does not refer to an existing project")
        elif field == "proposal_id":
            if _get(conn, tid, PROPOSAL) is None:
                errors.append(f"record.proposal_id: {tid!r} does not refer to an existing proposal")
            elif _has_final_ruling(conn, tid):
                errors.append(
                    f"record.proposal_id: {tid!r} already has a final ruling; close "
                    "its ruling_id instead"
                )
        else:
            ruling = _get(conn, tid, RULING)
            if ruling is None:
                errors.append(f"record.ruling_id: {tid!r} does not refer to an existing ruling")
            elif ruling.get("decision") != ACCEPT:
                errors.append(f"record.ruling_id: {tid!r} is not an accepting ruling")
        if _is_closed(conn, field, tid):
            errors.append(f"record.{field}: {tid!r} is already closed")


def _check_proposal_routing(conn, errors: list[str], record: dict) -> None:
    """A proposal's routed-type rules (docs/CONDUCTOR-EXECUTION.md 1, 2.2
    items 1 and 6, the freeze in 6.6). The per-tool parts of filing (the dry
    run, argument shape, cited handles) are the server's, 2C."""
    ptype = record.get("type")
    if not isinstance(ptype, str):
        return
    group = routing.group_of(ptype)
    has_step = "step" in record
    follow = "project_id" in record
    if group is None:
        if has_step:
            errors.append(
                f"record.step: {ptype!r} is in no routing group "
                "(dfqueue/action_tools.yaml), so it takes no step"
            )
        return
    routed = routing.is_routed(ptype)
    if has_step and not routed:
        errors.append(
            f"record.step: {ptype!r} is not routed yet (group {group!r}); a step is "
            "refused and the Overseer acts on the proposal as before"
        )
    if routed and not has_step:
        errors.append(
            f"record.step: {ptype!r} is routed to the executor, so a proposal needs an "
            "exact step (one tool, exact arguments)"
        )
    if not has_step and routing.is_frozen(ptype):
        errors.append(
            f"record.step: {group!r} proposals move to exact actions at the next "
            "deploy; file after it"
        )
    if has_step and isinstance(record["step"], dict):
        tool = record["step"].get("tool")
        if isinstance(tool, str) and tool not in routing.tools(group):
            errors.append(
                f"record.step.tool: {tool!r} is not a tool of group {group!r} "
                f"({routing.tools(group)})"
            )
    phases = record.get("phases")
    if isinstance(phases, dict) and isinstance(phases.get("tool"), str):
        if phases["tool"] not in routing.tools(group):
            errors.append(f"record.phases.tool: {phases['tool']!r} is not a tool of group {group!r}")

    if follow and isinstance(record.get("project_id"), str):
        project = _get(conn, record["project_id"], PROJECT)
        if project is None:
            errors.append(
                f"record.project_id: {record['project_id']!r} does not refer to an "
                "existing project"
            )
        else:
            if _is_closed(conn, "project_id", project["id"]) or _is_abandoned(conn, project["id"]):
                errors.append(f"record.project_id: {project['id']!r} is closed or abandoned")
            root = _proposal_of_ruling(conn, project["from_ruling"])
            if root is None or root.get("role") != record.get("role"):
                errors.append(
                    f"record.project_id: {project['id']!r} is not a project this role proposed"
                )
            elif routing.group_of(root.get("type")) != group:
                errors.append(
                    f"record.type: a follow-up must stay in its project's group "
                    f"({routing.group_of(root.get('type'))!r}), got {group!r}"
                )
            steps = _current_steps_and_version(conn, project)[0]
            after = record.get("after_step")
            if isinstance(after, str) and after not in _step_ids_list(steps):
                errors.append(
                    f"record.after_step: {after!r} is not a step of {project['id']!r}"
                )
            covered = record.get("covered_by")
            if covered is not None:
                if not routing.coverage_on(ptype):
                    errors.append(
                        f"record.covered_by: coverage is not on for group {group!r}"
                    )
                elif covered not in _step_ids_list(steps):
                    errors.append(
                        f"record.covered_by: {covered!r} is not a step of {project['id']!r}"
                    )
    elif "covered_by" in record and not follow:
        pass  # the schema already refused it


# ---- the fort plan (handoffs/2026-10-07-planner-p1a.md) ---------------------------


def _active_plan_conn(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute(
        "SELECT payload FROM records WHERE kind = ? ORDER BY rowid DESC LIMIT 1", (FORT_PLAN,)
    ).fetchone()
    return json.loads(row["payload"]) if row is not None else None


def _plan_base_sections(active: dict | None, base: dict | None = None) -> dict:
    """The sections a new version is diffed against: the active version's, or
    for version 1 `base` (the current stage's roadmap targets) when given,
    else the first roadmap stage's."""
    src = active if active is not None else (base if base is not None else plan.default_plan())
    return {s: list(src.get(s) or []) for s in plan.policy()["open_sections"]}


def _check_fort_plan(conn, errors: list[str], record: dict, game_tick) -> None:
    """The stateful checks on a `fort_plan` (design 2.1, 2.4): the base
    version (optimistic concurrency, so a retry after a timeout is safe), the
    stamped season, the server-computed diff, the season interval and the
    cited ruling. Content mistakes are never an error here: they are flags
    (`dfqueue/plan.py`)."""
    active = _active_plan_conn(conn)
    expected = 1 if active is None else int(active["version"]) + 1
    if record["version"] != expected:
        errors.append(
            f"record.version: the active plan is "
            f"{'version ' + str(active['version']) if active else 'absent'}, so the next version "
            f"is {expected}, got {record['version']} (a stale base; re-read plan.read and file "
            "against the active version)"
        )
    if (active["id"] if active else None) != record.get("supersedes"):
        errors.append(
            f"record.supersedes: must be the active version's id "
            f"({active['id'] if active else None!r}), got {record.get('supersedes')!r}"
        )
    if isinstance(game_tick, bool) or not isinstance(game_tick, int):
        errors.append("game_tick: a fort_plan must be appended with an integer game_tick (its season)")
        return
    if record["season_index"] != plan.season_index(game_tick):
        errors.append(
            f"record.season_index: {record['season_index']} is not the season of tick {game_tick} "
            f"({plan.season_index(game_tick)}); the server stamps it"
        )
    new_sections = {s: list(record.get(s) or []) for s in plan.policy()["open_sections"]}
    stage_id = record.get("roadmap_stage") if isinstance(record.get("roadmap_stage"), str) else None
    base = plan.default_plan(stage_id) if active is None and stage_id else None
    changes = plan.diff_changes(_plan_base_sections(active, base), new_sections)
    if record.get("changes") != changes:
        errors.append("record.changes: server-computed; it does not match the diff against the base")
    if active is not None and not changes:
        errors.append("record: nothing changes against the active version; there is nothing to file")

    rid = record.get("ruling_id")
    ruling_ok = False
    if rid:
        problem = _plan_ruling_problem(conn, rid)
        if problem:
            errors.append(f"record.ruling_id: {problem}")
        else:
            ruling_ok = True
    verdict = plan.guardrail(
        active, game_tick, changes, rid if ruling_ok else None,
        adopt_stage=plan.fort_roadmap.adopts_stage(active, changes, new_sections, stage_id),
    )
    if not verdict["ok"]:
        errors.append("record: " + verdict["refusal"])


def _plan_ruling_problem(conn, rid: str) -> str | None:
    """Why `rid` cannot authorise a mid-season plan version, or `None` when it
    can: an accepting ruling on a Planner `plan_change`, not yet cited by a
    version and not closed (it authorises exactly one)."""
    ruling = _get(conn, rid, RULING)
    prop = _get(conn, ruling["proposal_id"], PROPOSAL) if ruling else None
    if ruling is None:
        return f"{rid!r} does not refer to an existing ruling"
    if ruling.get("decision") != ACCEPT:
        return f"{rid!r} is not an accepting ruling"
    if prop is None or prop.get("type") != PLAN_CHANGE or prop.get("role") != PLAN_ROLE:
        return f"{rid!r} is not a ruling on a {PLAN_CHANGE} proposal"
    if conn.execute(
        "SELECT 1 FROM records WHERE kind = ? AND json_extract(payload, '$.ruling_id') = ?",
        (FORT_PLAN, rid),
    ).fetchone() is not None:
        return f"{rid!r} already authorised a plan version; it authorises one"
    if _is_closed(conn, "ruling_id", rid):
        return f"{rid!r} is closed"
    return None


def plan_ruling_problem(path: str | Path, rid: str) -> str | None:
    """Read-only `_plan_ruling_problem`, for a dry run."""
    with _connect(path) as conn:
        return _plan_ruling_problem(conn, rid)


def _check_serves(conn, errors: list[str], record: dict) -> None:
    """`serves` (design 2.5): every id names a target of the active plan, and
    the proposer owns the target or one of its derived inputs (F-1)."""
    if "serves" not in record or any(e.startswith("record.serves") for e in errors):
        return
    active = _active_plan_conn(conn)
    if active is None:
        errors.append("record.serves: there is no active plan yet, so no target to serve")
        return
    by_id = {t.get("id"): t for t in active.get("targets") or [] if isinstance(t, dict)}
    for tid in record["serves"]:
        t = by_id.get(tid)
        if t is None:
            errors.append(
                f"record.serves: {tid!r} is not a target of plan version {active['version']} "
                f"(targets: {sorted(i for i in by_id if isinstance(i, str))})"
            )
        elif not plan.may_serve(t, record.get("role")):
            errors.append(
                f"record.serves: {record.get('role')!r} may not serve {tid!r}; only its owner "
                f"({t.get('owner')!r}) or the owner of one of its derived inputs may"
            )


def _check_plan_change_rate(conn, errors: list[str], record: dict, game_tick) -> None:
    """The server rate-limits `plan_change` requests (design Q2): a cooldown
    between requests and a cap per season index, policy data. A rejected
    request still counts. A tick that went backwards (a reload) is elapsed."""
    if record.get("type") != PLAN_CHANGE or isinstance(game_tick, bool) or not isinstance(game_tick, int):
        return
    pol = plan.policy()["plan_change"]
    ticks = [
        r["cycle"] for r in conn.execute(
            "SELECT cycle FROM records WHERE kind = ? AND type = ?", (PROPOSAL, PLAN_CHANGE)
        ).fetchall()
    ]
    if not ticks:
        return
    since = game_tick - max(ticks)
    if 0 <= since < pol["cooldown_ticks"]:
        errors.append(
            f"record.type: a {PLAN_CHANGE} was requested {since} ticks ago; the cooldown is "
            f"{pol['cooldown_ticks']} ticks (ask again after tick {max(ticks) + pol['cooldown_ticks']})"
        )
    season = plan.season_index(game_tick)
    in_season = sum(1 for t in ticks if plan.season_index(t) == season)
    if in_season >= pol["per_season_cap"]:
        errors.append(
            f"record.type: season {season} already has {in_season} {PLAN_CHANGE} requests "
            f"(the cap is {pol['per_season_cap']}); wait for the next season or the ruling on one"
        )


def active_plan(path: str | Path) -> dict | None:
    """The latest `fort_plan`, or `None` before version 1."""
    with _connect(path) as conn:
        return _active_plan_conn(conn)


def plan_version(path: str | Path, version: int) -> dict | None:
    with _connect(path) as conn:
        row = conn.execute(
            "SELECT payload FROM records WHERE kind = ? AND json_extract(payload, '$.version') = ?",
            (FORT_PLAN, version),
        ).fetchone()
    return json.loads(row["payload"]) if row is not None else None


def plan_history(path: str | Path, n: int) -> list[dict]:
    """The last `n` plan versions, newest first."""
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT payload FROM records WHERE kind = ? ORDER BY rowid DESC LIMIT ?", (FORT_PLAN, n)
        ).fetchall()
    return [json.loads(r["payload"]) for r in rows]


def plan_changes_awaiting(path: str | Path) -> list[dict]:
    """Accepted `plan_change` proposals no plan version has cited yet: the
    Planner's to do, never the Overseer's (design F-9). `{proposal, ruling_id}`,
    oldest first."""
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT p.payload AS pp, rl.id AS rid FROM records p "
            "JOIN records rl ON rl.kind = ? AND rl.proposal_id = p.id "
            "AND json_extract(rl.payload, '$.decision') = ? "
            "WHERE p.kind = ? AND p.type = ? AND NOT EXISTS ("
            "SELECT 1 FROM records f WHERE f.kind = ? AND json_extract(f.payload, '$.ruling_id') = rl.id"
            ") AND NOT EXISTS (SELECT 1 FROM records c WHERE c.kind = ? AND "
            "json_extract(c.payload, '$.ruling_id') = rl.id) ORDER BY p.rowid ASC",
            (RULING, ACCEPT, PROPOSAL, PLAN_CHANGE, FORT_PLAN, CLOSE),
        ).fetchall()
    return [{"proposal": json.loads(r["pp"]), "ruling_id": r["rid"]} for r in rows]


_PLAN_REVIEWED_KEY = "plan:last_reviewed_tick"


def mark_plan_reviewed(path: str | Path, tick: int) -> None:
    """Record that the Planner reviewed the plan at `tick` and filed nothing
    (a review that ends in `queue.pass`), so a pass is visible (design 2.4)."""
    with _connect(path) as conn:
        with conn:
            conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (_PLAN_REVIEWED_KEY, str(int(tick))),
            )


def plan_last_reviewed_tick(path: str | Path) -> int | None:
    """The later of the last explicit review (`mark_plan_reviewed`) and the
    tick of the active version, or `None` with no plan and no review."""
    with _connect(path) as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (_PLAN_REVIEWED_KEY,)).fetchone()
        active = _active_plan_conn(conn)
    ticks = []
    if row is not None:
        ticks.append(int(row["value"]))
    if active is not None:
        ticks.append(int(active["cycle"]))
    return max(ticks) if ticks else None


def serving_work(path: str | Path) -> dict:
    """In-flight work per plan target id: `{target_id: [{proposal_id, type,
    role, state}]}`. A root proposal (not a follow-up) naming the target in
    `serves` is in flight while it is **pending** (no final ruling),
    **accepted** (ruled, no project yet) or **building** (its project is
    open, `open_projects`); rejected, closed, abandoned and finished work is
    not. Follow-ups join their project and are not counted again."""
    open_ids = {o["project_id"] for o in open_projects(path)}
    out: dict = {}
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT id, payload FROM records WHERE kind = ? "
            "AND json_extract(payload, '$.serves') IS NOT NULL ORDER BY rowid ASC", (PROPOSAL,)
        ).fetchall()
        for row in rows:
            p = json.loads(row["payload"])
            if p.get("project_id") is not None or _is_closed(conn, "proposal_id", row["id"]):
                continue
            if not _has_final_ruling(conn, row["id"]):
                state = "pending"
            else:
                accepting = _accepting_ruling(conn, row["id"])
                if accepting is None or _is_closed(conn, "ruling_id", accepting["id"]):
                    continue
                proj = _find_project_for_ruling(conn, accepting["id"])
                if proj is None:
                    state = "accepted"
                elif proj["id"] in open_ids:
                    state = "building"
                else:
                    continue
            for tid in p.get("serves") or []:
                out.setdefault(tid, []).append({
                    "proposal_id": row["id"], "type": p.get("type"), "role": p.get("role"), "state": state,
                })
    return out


# ---- cutovers (meta table) ------------------------------------------------------


def cutover(path: str | Path, group: str) -> str | None:
    """The ruling id at or below which a group's old work is legacy, or
    `None` if no cutover has been set. `"legacy"` is a group (deploy 2a)."""
    with _connect(path) as conn:
        return _cutover_conn(conn, group)


def _cutover_conn(conn: sqlite3.Connection, group: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (f"cutover:{group}",)).fetchone()
    return row["value"] if row is not None else None


def set_cutover(path: str | Path, group: str, ruling_id: str) -> None:
    """Record a group's cutover. Raise-only: a cutover never moves down, so
    closing is never undone. `ruling_id` must be an existing ruling."""
    if group != LEGACY and group not in routing.groups():
        raise QueueError(f"no such routing group: {group!r}")
    with _locked(path) as conn:
        if _get(conn, ruling_id, RULING) is None:
            raise QueueError(f"cutover: {ruling_id!r} is not an existing ruling")
        current = _cutover_conn(conn, group)
        if current is not None and _num(ruling_id) < _num(current):
            raise QueueError(
                f"cutover for {group!r} is {current!r}; it only moves up, not to {ruling_id!r}"
            )
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (f"cutover:{group}", ruling_id),
        )


def highest_ruling(path: str | Path) -> str | None:
    """The id of the latest ruling (what a `--check` lists up to)."""
    with _connect(path) as conn:
        return _highest_ruling_conn(conn)


def _highest_ruling_conn(conn: sqlite3.Connection) -> str | None:
    rows = conn.execute("SELECT id FROM records WHERE kind = ?", (RULING,)).fetchall()
    return max((r["id"] for r in rows), key=_num, default=None)


def _effective_cutover_num(conn: sqlite3.Connection, group: str | None) -> int | None:
    """The larger of the legacy cutover and the group's own; `None` if
    neither is set."""
    nums = []
    for g in {LEGACY, group} - {None}:
        c = _cutover_conn(conn, g)
        if c is not None:
            nums.append(_num(c))
    return max(nums) if nums else None


# ---- the executor's writes ------------------------------------------------------


def _fail(errors: list[str]) -> None:
    raise QueueError("refusing: " + "; ".join(errors))


def _build_step(project_id: str, n: int, proposal: dict, requires: list[str]) -> dict:
    sid = f"{project_id}/s{n}"
    step = {
        "id": sid,
        "tool": proposal["step"]["tool"],
        "args": json.loads(_canon(proposal["step"].get("args") or {})),
        "targets": {"set": [sid]},
        "requires": list(requires),
        "trigger": TRIGGER_ALL_SUCCESS,
        "prefer_after": [],
        "guards": GUARDS_DEFAULT,
        "proposal_id": proposal["id"],
    }
    label = proposal["step"].get("label")
    if label:
        step["label"] = label
    return step


def open_project_from_ruling(
    path: str | Path, ruling_id: str, *, urgency: str | None = None,
    tick: int | None = None, snapshot: str = "executor",
) -> dict:
    """The executor opens the project for an accepted routed proposal: one
    step (`<project id>/s1`, its own synthetic target, the proposal's tool
    and arguments, `proposal_id` set). Refuses: a ruling that is not an
    accept, a follow-up (it joins its parent, `apply_followup`), an
    unrouted type, a proposal with no step, a ruling at or below the group's
    cutover (or with no cutover set: unset means nothing may open), a closed
    ruling, and a ruling that already has a project (P2-M3, P3-B1).
    `urgency` is the project's (`normal` if omitted); the record's `cycle`
    is `tick`, or the ruling's own. Returns the `project` record."""
    with _locked(path) as conn:
        errors: list[str] = []
        ruling = _get(conn, ruling_id, RULING)
        proposal = None
        if ruling is None:
            _fail([f"{ruling_id!r} is not a ruling"])
        if ruling.get("decision") != ACCEPT:
            errors.append(f"{ruling_id!r} is not an accepting ruling")
        proposal = _get(conn, ruling["proposal_id"], PROPOSAL)
        group = routing.group_of(proposal.get("type")) if proposal else None
        if proposal is not None:
            if proposal.get("project_id") is not None:
                errors.append(
                    f"{proposal['id']!r} is a follow-up of {proposal['project_id']!r}; it "
                    "joins that project (apply_followup), it never opens one"
                )
            if group is None or not routing.is_routed(proposal["type"]):
                errors.append(f"type {proposal['type']!r} is not routed")
            if "step" not in proposal:
                errors.append(f"{proposal['id']!r} has no step")
        if group is not None:
            cut = _effective_cutover_num(conn, group)
            if cut is None:
                errors.append(f"no cutover is set for group {group!r}, so nothing may open")
            elif _num(ruling_id) <= cut:
                errors.append(f"{ruling_id!r} is at or below the cutover (legacy work)")
        if _is_closed(conn, "ruling_id", ruling_id):
            errors.append(f"{ruling_id!r} is closed")
        if _find_project_for_ruling(conn, ruling_id) is not None:
            errors.append(f"{ruling_id!r} already has a project")
        if errors:
            _fail(errors)

        pid = _next_id(conn, PROJECT)
        record = {
            "id": pid, "kind": PROJECT, "role": executor(),
            "cycle": ruling["cycle"] if tick is None else tick,
            "snapshot": snapshot,
            "from_ruling": ruling_id,
            "summary": proposal["summary"],
            "because": proposal["rationale"],
            "steps": [_build_step(pid, 1, proposal, [])],
        }
        if urgency is not None:
            record["urgency"] = urgency
        if proposal.get("public_title"):
            record["public_title"] = proposal["public_title"]
        if proposal.get("public_rationale"):
            record["public_rationale"] = proposal["public_rationale"][:PUBLIC_RATIONALE_MAX]
        tmpl = record["steps"][0]["args"].get("template")
        if isinstance(tmpl, str) and tmpl:
            record["template"] = tmpl
        return _append_in_conn(conn, record, commit=False)


def apply_followup(
    path: str | Path, proposal_id: str, *, tick: int | None = None,
    snapshot: str = "executor",
) -> dict:
    """Apply an accepted (or covered) follow-up: one `amend` that carries
    the project's whole current plan plus the new step
    (`<project id>/s<N>`, `requires: [after_step]`). Reads and writes under
    one lock, so two follow-ups cannot build from the same base (P2-L1);
    the store's own amend base check backs it. Refuses a follow-up that is
    not ruled accept or covered, one already applied, a closed or abandoned
    project, and an `after_step` that is not in the plan."""
    with _locked(path) as conn:
        errors: list[str] = []
        proposal = _get(conn, proposal_id, PROPOSAL)
        if proposal is None:
            _fail([f"{proposal_id!r} is not a proposal"])
        project = _get(conn, proposal.get("project_id"), PROJECT)
        if project is None:
            _fail([f"{proposal_id!r} is not a follow-up of an existing project"])
        if proposal.get("covered_by") is None and _accepting_ruling(conn, proposal_id) is None:
            errors.append(f"{proposal_id!r} is neither accepted nor covered")
        if _is_closed(conn, "project_id", project["id"]) or _is_abandoned(conn, project["id"]):
            errors.append(f"{project['id']!r} is closed or abandoned")
        if _is_closed(conn, "proposal_id", proposal_id):
            errors.append(f"{proposal_id!r} is closed")
        steps, _version = _current_steps_and_version(conn, project)
        if proposal.get("after_step") not in _step_ids_list(steps):
            errors.append(f"after_step {proposal.get('after_step')!r} is not in the plan")
        if any(st.get("proposal_id") == proposal_id for st in steps):
            errors.append(f"{proposal_id!r} is already applied")
        if "step" not in proposal:
            errors.append(f"{proposal_id!r} has no step")
        if errors:
            _fail(errors)

        n = 1 + max(
            (int(str(st["id"]).rsplit("/s", 1)[1]) for st in steps
             if "/s" in str(st.get("id")) and str(st["id"]).rsplit("/s", 1)[1].isdigit()),
            default=0,
        )
        new_step = _build_step(project["id"], n, proposal, [proposal["after_step"]])
        record = {
            "kind": AMEND, "role": executor(),
            "cycle": _latest_cycle(conn) if tick is None else tick,
            "snapshot": snapshot,
            "project_id": project["id"],
            "steps": [*steps, new_step],
            "adds": [new_step["id"]],
            "reason": f"follow-up {proposal_id}",
        }
        if proposal.get("public_rationale"):
            record["public_rationale"] = proposal["public_rationale"][:PUBLIC_RATIONALE_MAX]
        return _append_in_conn(conn, record, commit=False)


def _step_of(conn, project: dict, step_id: str) -> dict | None:
    return next(
        (st for st in _current_steps_and_version(conn, project)[0] if st.get("id") == step_id),
        None,
    )


def _runnable_reasons(conn, project_id: str, step_id: str, latched: bool) -> list[str]:
    project = _get(conn, project_id, PROJECT)
    if project is None:
        return [f"no such project {project_id!r}"]
    if _is_closed(conn, "project_id", project_id):
        return [f"project {project_id!r} is closed"]
    if _is_abandoned(conn, project_id):
        return [f"project {project_id!r} is abandoned"]
    ruling = _get(conn, project["from_ruling"], RULING)
    if ruling is None or ruling.get("decision") != ACCEPT:
        return ["the project's ruling is not accepted"]
    step = _step_of(conn, project, step_id)
    if step is None:
        return [f"{step_id!r} is not a step of the current plan"]
    pid = step.get("proposal_id")
    if pid is None:
        return ["the step carries no proposal_id: it was not built by the executor (P3-B1)"]
    proposal = _get(conn, pid, PROPOSAL)
    if proposal is None or "step" not in proposal:
        return [f"the step's proposal {pid!r} has no step"]
    reasons: list[str] = []
    if (
        step.get("tool") != proposal["step"].get("tool")
        or _canon(step.get("args") or {}) != _canon(proposal["step"].get("args") or {})
    ):
        reasons.append(
            f"the step's content differs from proposal {pid!r}'s step; the executor runs "
            "only what was proposed and ruled"
        )
    if proposal.get("project_id") is None:
        if proposal.get("id") != _proposal_of_ruling(conn, project["from_ruling"]).get("id"):
            reasons.append(f"proposal {pid!r} is not the project's own")
    else:
        if proposal["project_id"] != project_id:
            reasons.append(f"proposal {pid!r} belongs to {proposal['project_id']!r}")
        if proposal.get("covered_by") is None and _accepting_ruling(conn, pid) is None:
            reasons.append(f"follow-up {pid!r} is neither accepted nor covered")
    states: dict = {}
    for r in conn.execute(
        "SELECT step_id, state FROM step_targets WHERE project_id = ?", (project_id,)
    ).fetchall():
        states.setdefault(r["step_id"], []).append(r["state"])
    if not step_prerequisites_satisfied(step, states):
        reasons.append("the step's prerequisites are not done")
    own = states.get(step_id, [])
    if any(s in (ISSUED, DONE) for s in own):
        reasons.append("the step already succeeded")
    if any(s == FAILED for s in own):
        reasons.append("the step failed")
    open_run = conn.execute(
        "SELECT status FROM step_runs WHERE project_id = ? AND step_id = ? AND status IN (?, ?)",
        (project_id, step_id, RUN_ISSUING, RUN_HELD),
    ).fetchone()
    if open_run is not None:
        reasons.append(f"an earlier run of the step is unresolved ({open_run['status']})")
    if latched and project.get("urgency") != "high":
        reasons.append("the tripwire is latched and the project is not urgency high")
    return reasons


def check_step_runnable(
    path: str | Path, project_id: str, step_id: str, *, latched: bool,
) -> list[str]:
    """Every reason the step may not run now; `[]` means runnable
    (docs/CONDUCTOR-EXECUTION.md 4.1 step 1): ruling accepted, project open,
    step in the current plan, prerequisites done, not succeeded, no
    unresolved run, the tripwire not latched unless the project's urgency is
    `high`, and **the step's content equals its `proposal_id`'s `step`**
    (P3-B1). A step with no `proposal_id` (anything the Overseer wrote) is
    never runnable."""
    with _connect(path) as conn:
        return _runnable_reasons(conn, project_id, step_id, latched)


def begin_step_run(
    path: str | Path, project_id: str, step_id: str, *, tick: int, baseline,
) -> int:
    """Write the `issuing` marker for one real call, before it is made
    (4.1 step 3). `baseline` is the JSON-able `landed` baseline (for a
    reserve, the set of reservation handles). `step_id` may be
    `cleanup:<handle>` for an abandon cleanup call (4.4), which is not
    checked against the plan. Re-checks runnability under the lock (the
    tripwire excepted: that is the caller's call) and returns the run id."""
    with _locked(path) as conn:
        if step_id.startswith(CLEANUP_PREFIX):
            if _get(conn, project_id, PROJECT) is None:
                _fail([f"no such project {project_id!r}"])
        else:
            reasons = _runnable_reasons(conn, project_id, step_id, latched=False)
            if reasons:
                _fail(reasons)
        cur = conn.execute(
            "INSERT INTO step_runs (project_id, step_id, status, tick, baseline, started_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, step_id, RUN_ISSUING, int(tick), json.dumps(baseline),
             datetime.now(timezone.utc).isoformat()),
        )
        return cur.lastrowid


def _run_row(conn, run_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM step_runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise QueueError(f"no such step run: {run_id!r}")
    return row


def _run_dict(row: sqlite3.Row) -> dict:
    return {
        "run_id": row["id"], "project_id": row["project_id"], "step_id": row["step_id"],
        "status": row["status"], "outcome": row["outcome"], "tick": row["tick"],
        "baseline": json.loads(row["baseline"]) if row["baseline"] is not None else None,
        "handle": row["handle"], "executed_id": row["executed_id"],
        "started_at": row["started_at"], "ended_at": row["ended_at"],
    }


def get_step_run(path: str | Path, run_id: int) -> dict:
    with _connect(path) as conn:
        return _run_dict(_run_row(conn, run_id))


def step_runs(path: str | Path, project_id: str, step_id: str | None = None) -> list[dict]:
    """Every run of a project (or one step), oldest first: what the
    conductor counts retries from (`void` and `recorded` failures)."""
    q, params = "SELECT * FROM step_runs WHERE project_id = ?", [project_id]
    if step_id is not None:
        q, params = q + " AND step_id = ?", [*params, step_id]
    with _connect(path) as conn:
        return [_run_dict(r) for r in conn.execute(q + " ORDER BY id ASC", params).fetchall()]


def _first_handle(executed: dict) -> str | None:
    for a in executed.get("actions") or []:
        for ref in (a or {}).get("game_refs") or []:
            if isinstance(ref, str) and ref:
                return ref
    return None


def finish_step_run(
    path: str | Path, run_id: int, executed: dict, *, handle: str | None = None,
) -> dict:
    """The real call returned: append the step's `executed` record and mark
    the run `recorded`, in one transaction (4.1 step 5). `executed` carries
    `actions` (each `{tool, outcome, detail?, game_refs?}`; to move the
    step's target add `targets: [<step id>]` and `target_state` `issued`,
    `held` or `failed`; **leave both off for a first failure, so the step
    stays retryable**), `notes` (defaults to a one-line note), and
    optionally `cycle` (default: the run's tick) and `snapshot`. The store
    fills `role`, `ruling_id`, `step_id` and `proposal_id`. `handle` is the
    handle the call issued (default: the first string in `game_refs`); it is
    what `issued_handles` returns. A `cleanup:<handle>` run appends no
    `executed`. Returns `{"run": ..., "executed": <record or None>}`."""
    with _locked(path) as conn:
        row = _run_row(conn, run_id)
        if row["status"] != RUN_ISSUING:
            _fail([f"run {run_id} is {row['status']!r}, not {RUN_ISSUING!r}"])
        handle = handle or _first_handle(executed)
        written = None
        now = datetime.now(timezone.utc).isoformat()
        if not row["step_id"].startswith(CLEANUP_PREFIX):
            project = _get(conn, row["project_id"], PROJECT)
            step = _step_of(conn, project, row["step_id"])
            record = {
                **{k: v for k, v in executed.items() if k not in ("kind", "role")},
                "kind": EXECUTED, "role": executor(),
                "ruling_id": project["from_ruling"], "step_id": step["id"],
                "proposal_id": step["proposal_id"],
            }
            record.setdefault("cycle", row["tick"])
            record.setdefault("snapshot", "executor")
            record.setdefault("notes", f"run {run_id} of {step['id']}")
            written = _append_in_conn(conn, record, commit=False)
        conn.execute(
            "UPDATE step_runs SET status = ?, outcome = ?, handle = ?, executed_id = ?, "
            "ended_at = ? WHERE id = ?",
            (RUN_RECORDED,
             "success" if all((a or {}).get("outcome") == SUCCESS for a in executed.get("actions") or [])
             else "failure",
             handle, written["id"] if written else None, now, run_id),
        )
        return {"run": _run_dict(_run_row(conn, run_id)), "executed": written}


def unresolved_step_runs(path: str | Path) -> list[dict]:
    """Runs left `issuing` (an Uncertain outcome, 4.2), oldest first. A run
    the conductor settled as `held` is not listed (it needs a person)."""
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT * FROM step_runs WHERE status = ? ORDER BY id ASC", (RUN_ISSUING,)
        ).fetchall()
    return [_run_dict(r) for r in rows]


def resolve_step_run(
    path: str | Path, run_id: int, outcome: str, handle: str | None = None,
    *, tick: int | None = None, notes: str | None = None,
) -> dict:
    """Settle an `issuing` run after its `landed` read (4.2 Uncertain).
    `success` (a handle is required): the call did land; appends the step's
    `executed` (success, target `issued`, `game_refs` the handle), run
    `resolved`. `transient`: nothing landed; run `void`, the step may run
    again. `held`: unreadable; run `held`, the step is blocked until the
    project is closed. A `cleanup:` run appends no record."""
    if outcome not in RESOLVE_OUTCOMES:
        raise QueueError(f"resolve outcome {outcome!r} is not in {RESOLVE_OUTCOMES}")
    if outcome == "success" and not handle:
        raise QueueError("resolving as success needs the handle the call issued")
    with _locked(path) as conn:
        row = _run_row(conn, run_id)
        if row["status"] != RUN_ISSUING:
            _fail([f"run {run_id} is {row['status']!r}, not {RUN_ISSUING!r}"])
        now = datetime.now(timezone.utc).isoformat()
        written = None
        if outcome == "success" and not row["step_id"].startswith(CLEANUP_PREFIX):
            project = _get(conn, row["project_id"], PROJECT)
            step = _step_of(conn, project, row["step_id"])
            record = {
                "kind": EXECUTED, "role": executor(),
                "cycle": row["tick"] if tick is None else tick, "snapshot": "executor",
                "ruling_id": project["from_ruling"], "step_id": step["id"],
                "proposal_id": step["proposal_id"],
                "actions": [{
                    "tool": step["tool"], "outcome": SUCCESS,
                    "detail": "settled as landed by a read against the baseline",
                    "targets": [step["id"]], "target_state": ISSUED,
                    "game_refs": [handle],
                }],
                "notes": notes or f"run {run_id} settled as success by its landed read",
            }
            written = _append_in_conn(conn, record, commit=False)
        status = {"success": RUN_RESOLVED, "transient": RUN_VOID, "held": RUN_HELD}[outcome]
        conn.execute(
            "UPDATE step_runs SET status = ?, outcome = ?, handle = ?, executed_id = ?, "
            "ended_at = ? WHERE id = ?",
            (status, outcome, handle, written["id"] if written else None, now, run_id),
        )
        return {"run": _run_dict(_run_row(conn, run_id)), "executed": written}


def issued_handles(path: str | Path, project_id: str) -> list[str]:
    """The handles this project's real calls issued, oldest first (2.2
    item 6: a follow-up may cite only a handle its project issued)."""
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT handle FROM step_runs WHERE project_id = ? AND handle IS NOT NULL "
            "AND status IN (?, ?) ORDER BY id ASC",
            (project_id, RUN_RECORDED, RUN_RESOLVED),
        ).fetchall()
    seen: list[str] = []
    for r in rows:
        if r["handle"] not in seen:
            seen.append(r["handle"])
    return seen


def _apply_observation(conn: sqlite3.Connection, record: dict) -> None:
    """An `observation` with `done: true` is the completion rule's only way
    to `done`: it flips the step's synthetic target and, for a step carrying
    a `proposal_id`, arms that proposal's prediction (prediction arming on
    the proposal's own step reaching `done`, never a failure; 6.1). An
    observation without `done`, or `done: false`, touches nothing."""
    if record.get("done") is not True:
        return
    project = _get(conn, record["project_id"], PROJECT)
    step = _step_of(conn, project, record["step_id"]) if project else None
    if step is None:
        return
    tick = record["game_tick"]
    targets = (step.get("targets") or {}).get("set") or []
    for target in targets:
        conn.execute(
            "INSERT INTO step_targets (project_id, step_id, target, state, reason, last_tick) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(project_id, step_id, target) DO UPDATE SET "
            "state = excluded.state, reason = excluded.reason, last_tick = excluded.last_tick",
            (project["id"], step["id"], str(target), DONE, "observed done", tick),
        )
    proposal_id = step.get("proposal_id")
    if proposal_id is None:
        return
    pred = conn.execute(
        "SELECT id, check_after_ticks FROM predictions WHERE record_id = ? AND status = ?",
        (proposal_id, AWAITING_EXECUTION),
    ).fetchone()
    if pred is not None:
        conn.execute(
            "UPDATE predictions SET status = ?, due_game_tick = ? WHERE id = ?",
            (PENDING, tick + pred["check_after_ticks"], pred["id"]),
        )


def record_observation(
    path: str | Path, project_id: str, step_id: str, *, tick: int, done: bool,
    detail: dict, snapshot: str = "executor",
) -> dict:
    """Write one `observation` for a step at a game tick. `done: true` is
    the executor's completion verdict (the game says so, 4.3): the step's
    target becomes `done` and its proposal's prediction arms. `detail` is a
    bounded object (the status read, counts); `detail["status"]`
    (`consistent`, `contradicted`, `not_observable`, default `consistent`),
    `detail["reason"]` and `detail["hold_code"]` fill the one result line.
    A step must be `issued` (or already `done`, which only re-records) to be
    observed `done`."""
    status = detail.get("status", OBS_CONSISTENT)
    reason = detail.get("reason") or ("phase done" if done else "in progress")
    result = {"target": step_id, "status": status, "reason": reason}
    if detail.get("hold_code"):
        result["hold_code"] = detail["hold_code"]
    rest = {k: v for k, v in detail.items() if k not in ("status", "reason", "hold_code")}
    record = {
        "kind": OBSERVATION, "role": OBSERVATION_ROLE, "cycle": int(tick), "snapshot": snapshot,
        "project_id": project_id, "step_id": step_id, "game_tick": int(tick),
        "results": [result], "done": bool(done),
    }
    if rest:
        record["detail"] = rest
    with _locked(path) as conn:
        if done:
            states = [
                r["state"] for r in conn.execute(
                    "SELECT state FROM step_targets WHERE project_id = ? AND step_id = ?",
                    (project_id, step_id),
                ).fetchall()
            ]
            if states and not all(s in (ISSUED, DONE) for s in states):
                _fail([f"{step_id!r} is {sorted(set(states))}; only an issued step is observed done"])
            if not states:
                _fail([f"{step_id!r} has no tracked target; nothing to observe done"])
        return _append_in_conn(conn, record, commit=False)


def close(
    path: str | Path, *, target_id: str, outcome: str, reason: str,
    cleanup: list | None = None, tick: int | None = None, snapshot: str = "executor",
) -> dict:
    """Write a `close` for a project (`project-N`), a pending proposal
    (`proposal-N`) or an accepted ruling (`ruling-N`); the id's prefix picks
    the field. `outcome` is `completed`, `not_done`, `abandoned` or
    `superseded`. `cleanup` lists an abandon cleanup's results
    (`{handle, tool?, outcome, detail?}`). Refuses a target already closed
    and a proposal that has a final ruling (close its ruling instead)."""
    field = {"project": "project_id", "proposal": "proposal_id", "ruling": "ruling_id"}.get(
        str(target_id).rsplit("-", 1)[0]
    )
    if field is None:
        raise QueueError(f"close: cannot tell what {target_id!r} is")
    with _locked(path) as conn:
        return _close_conn(conn, field, target_id, outcome, reason, cleanup, tick, snapshot)


def _close_conn(conn, field, target_id, outcome, reason, cleanup, tick, snapshot) -> dict:
    record = {
        "kind": CLOSE, "role": executor(),
        "cycle": _latest_cycle(conn) if tick is None else tick, "snapshot": snapshot,
        field: target_id, "outcome": outcome, "reason": reason,
    }
    if cleanup is not None:
        record["cleanup"] = cleanup
    return _append_in_conn(conn, record, commit=False)


def projects_awaiting_cleanup(path: str | Path) -> list[dict]:
    """Abandoned routed projects not yet closed (4.4): the Overseer
    abandoned them; the executor's next execute phase releases what they
    reserved, then `close`s them with the results. Each entry is
    `{project_id, handles}` (`issued_handles`)."""
    out = []
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT json_extract(a.payload, '$.project_id') AS pid FROM records a "
            "WHERE a.kind = ? ORDER BY a.rowid ASC", (ABANDON,)
        ).fetchall()
        for r in rows:
            pid = r["pid"]
            if _is_closed(conn, "project_id", pid):
                continue
            if not routing.is_routed(_proposal_type_of_project(conn, pid) or ""):
                continue
            hs = [
                x["handle"] for x in conn.execute(
                    "SELECT DISTINCT handle FROM step_runs WHERE project_id = ? "
                    "AND handle IS NOT NULL AND status IN (?, ?) ORDER BY id ASC",
                    (pid, RUN_RECORDED, RUN_RESOLVED),
                ).fetchall()
            ]
            out.append({"project_id": pid, "handles": hs})
    return out


# ---- legacy sweep (deploy 2a, 2b) -----------------------------------------------


def _executed_exists(conn, ruling_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM records WHERE kind = ? AND json_extract(payload, '$.ruling_id') = ?",
        (EXECUTED, ruling_id),
    ).fetchone() is not None


def _legacy_bound(conn, group: str) -> int:
    """What `legacy_targets` lists up to: the cutover if one is set, else
    the highest ruling (a `--check` before anything is set)."""
    c = _cutover_conn(conn, group)
    if c is not None:
        return _num(c)
    h = _highest_ruling_conn(conn)
    return _num(h) if h else 0


def legacy_targets(path: str | Path, group: str = LEGACY) -> list[dict]:
    """Everything a cutover would close, not yet closed, oldest first. Each
    entry is `{kind, id, group, ruling_id, proposal_id, executed, summary}`.
    For `"legacy"` (deploy 2a): every accepted ruling at or below the legacy
    cutover (or, before one is set, the highest ruling). For a routing group
    (2b): its accepted rulings, its open Overseer-written projects, and its
    pending step-less proposals. Lists only; writes nothing."""
    if group != LEGACY and group not in routing.groups():
        raise QueueError(f"no such routing group: {group!r}")
    out: list[dict] = []
    with _connect(path) as conn:
        bound = _legacy_bound(conn, group)
        rulings = conn.execute(
            "SELECT payload FROM records WHERE kind = ? ORDER BY rowid ASC", (RULING,)
        ).fetchall()
        for r in rulings:
            ruling = json.loads(r["payload"])
            if ruling.get("decision") != ACCEPT or _num(ruling["id"]) > bound:
                continue
            proposal = _get(conn, ruling["proposal_id"], PROPOSAL) or {}
            g = routing.group_of(proposal.get("type"))
            if group != LEGACY and g != group:
                continue
            if _is_closed(conn, "ruling_id", ruling["id"]):
                continue
            out.append({
                "kind": "ruling", "id": ruling["id"], "group": g or LEGACY,
                "ruling_id": ruling["id"], "proposal_id": proposal.get("id"),
                "executed": _executed_exists(conn, ruling["id"]),
                "summary": proposal.get("summary"),
            })
        if group != LEGACY:
            for pid in [x["id"] for x in conn.execute(
                "SELECT id FROM records WHERE kind = ? ORDER BY rowid ASC", (PROJECT,)
            ).fetchall()]:
                project = _get(conn, pid, PROJECT)
                if project.get("role") == executor() and executor() != sole_writer():
                    continue  # an executor project is live work, not legacy
                if _num(project["from_ruling"]) > bound:
                    continue
                proposal = _proposal_of_ruling(conn, project["from_ruling"]) or {}
                if routing.group_of(proposal.get("type")) != group:
                    continue
                if _is_closed(conn, "project_id", pid) or _is_abandoned(conn, pid):
                    continue
                if _project_status_conn(conn, pid)["status"] == "done":
                    continue
                out.append({
                    "kind": "project", "id": pid, "group": group,
                    "ruling_id": project["from_ruling"], "proposal_id": proposal.get("id"),
                    "executed": _executed_exists(conn, project["from_ruling"]),
                    "summary": project.get("summary"),
                })
            for p in conn.execute(
                "SELECT payload FROM records WHERE kind = ? ORDER BY rowid ASC", (PROPOSAL,)
            ).fetchall():
                proposal = json.loads(p["payload"])
                if routing.group_of(proposal.get("type")) != group or "step" in proposal:
                    continue
                if _has_final_ruling(conn, proposal["id"]) or _is_closed(conn, "proposal_id", proposal["id"]):
                    continue
                out.append({
                    "kind": "proposal", "id": proposal["id"], "group": group,
                    "ruling_id": None, "proposal_id": proposal["id"], "executed": False,
                    "summary": proposal.get("summary"),
                })
    return out


def close_legacy(
    path: str | Path, target_id: str, *, reason: str, tick: int | None = None,
    snapshot: str = "executor",
) -> dict:
    """Close a ruling, a project or a pending step-less proposal that is at
    or below its cutover, under the executor's name, **touching no game
    state** (this module makes no DFHack call). The outcome is computed:
    `completed` if an `executed` record exists (for a project: the project
    reads `done`; see the Result note), else `not_done`. Refused when the
    target is above its cutover, when no cutover applies, or already
    closed. A ruling or project is checked against the larger of the legacy
    cutover and its group's; a pending proposal against its group's."""
    prefix = str(target_id).rsplit("-", 1)[0]
    with _locked(path) as conn:
        if prefix == "ruling":
            ruling = _get(conn, target_id, RULING)
            if ruling is None:
                _fail([f"{target_id!r} is not a ruling"])
            proposal = _get(conn, ruling["proposal_id"], PROPOSAL) or {}
            group = routing.group_of(proposal.get("type"))
            cut = _effective_cutover_num(conn, group)
            if cut is None or _num(target_id) > cut:
                _fail([f"{target_id!r} is above its cutover; close_legacy only closes legacy work"])
            done = _executed_exists(conn, target_id)
            field = "ruling_id"
        elif prefix == "project":
            project = _get(conn, target_id, PROJECT)
            if project is None:
                _fail([f"{target_id!r} is not a project"])
            if project.get("role") == executor() and executor() != sole_writer():
                _fail([f"{target_id!r} is an executor project, not legacy work"])
            proposal = _proposal_of_ruling(conn, project["from_ruling"]) or {}
            cut = _effective_cutover_num(conn, routing.group_of(proposal.get("type")))
            if cut is None or _num(project["from_ruling"]) > cut:
                _fail([f"{target_id!r} is above its cutover; close_legacy only closes legacy work"])
            done = _project_status_conn(conn, target_id)["status"] == "done"
            field = "project_id"
        elif prefix == "proposal":
            proposal = _get(conn, target_id, PROPOSAL)
            if proposal is None:
                _fail([f"{target_id!r} is not a proposal"])
            group = routing.group_of(proposal.get("type"))
            if group is None or _cutover_conn(conn, group) is None:
                _fail([f"{target_id!r} has no cutover for its group; nothing to close it under"])
            if "step" in proposal:
                _fail([f"{target_id!r} carries a step, so it is not legacy work"])
            done = False
            field = "proposal_id"
        else:
            raise QueueError(f"close_legacy: cannot tell what {target_id!r} is")
        outcome = CLOSE_COMPLETED if done else CLOSE_NOT_DONE
        return _close_conn(conn, field, target_id, outcome, reason, None, tick, snapshot)


# ---- the one definition of an open project --------------------------------------


def open_projects(path: str | Path) -> list[dict]:
    """The one WIP definition (design section 3, P3-M3), shared by the cap
    and `queue.pending_brief`: a project that is not closed and not
    abandoned, from a ruling above the larger of the legacy cutover and its
    group's (no cutover set counts everything, so nothing changes before
    2a), and with a step not done **or** a declared phase not yet applied.
    Each entry: `{project_id, from_ruling, group, role, urgency, summary,
    status, steps_open, phases_remaining}`; oldest first."""
    out = []
    with _connect(path) as conn:
        for row in conn.execute(
            "SELECT id FROM records WHERE kind = ? ORDER BY rowid ASC", (PROJECT,)
        ).fetchall():
            pid = row["id"]
            project = _get(conn, pid, PROJECT)
            if _is_closed(conn, "project_id", pid) or _is_abandoned(conn, pid):
                continue
            proposal = _proposal_of_ruling(conn, project["from_ruling"]) or {}
            group = routing.group_of(proposal.get("type"))
            cut = _effective_cutover_num(conn, group)
            if cut is not None and _num(project["from_ruling"]) <= cut:
                continue
            status = _project_status_conn(conn, pid)
            steps = _current_steps_and_version(conn, project)[0]
            declared = len(((proposal.get("phases") or {}).get("list")) or [])
            remaining = max(0, declared - max(0, len(steps) - 1))
            steps_open = status["status"] != "done"
            if not steps_open and remaining == 0:
                continue
            out.append({
                "project_id": pid, "from_ruling": project["from_ruling"], "group": group,
                "role": proposal.get("role"), "urgency": project.get("urgency") or "normal",
                "summary": project.get("summary"), "status": status["status"],
                "steps_open": steps_open, "phases_remaining": remaining,
            })
    return out


def openable_rulings(path: str | Path) -> list[dict]:
    """Read-only: the accepted rulings the conductor should open a project for
    (`open_project_from_ruling` would accept them now): an accepting ruling of
    a routed, non-follow-up proposal that has a step, above its group's
    cutover (none set means none), not closed, with no project yet. Oldest
    first; `{ruling_id, proposal_id, role}` where `role` is the proposer."""
    out = []
    with _connect(path) as conn:
        for row in conn.execute(
            "SELECT id, payload FROM records WHERE kind = ? AND "
            "json_extract(payload, '$.decision') = ? ORDER BY rowid ASC", (RULING, ACCEPT),
        ).fetchall():
            ruling = json.loads(row["payload"])
            proposal = _get(conn, ruling.get("proposal_id"), PROPOSAL)
            if proposal is None or proposal.get("project_id") is not None or "step" not in proposal:
                continue
            ptype = proposal.get("type")
            group = routing.group_of(ptype)
            if group is None or not routing.is_routed(ptype):
                continue
            cut = _effective_cutover_num(conn, group)
            if cut is None or _num(row["id"]) <= cut:
                continue
            if _is_closed(conn, "ruling_id", row["id"]) or _find_project_for_ruling(conn, row["id"]):
                continue
            out.append({"ruling_id": row["id"], "proposal_id": proposal["id"], "role": proposal.get("role")})
    return out


def applicable_followups(path: str | Path) -> list[dict]:
    """Read-only: the follow-ups `apply_followup` would accept now: a proposal
    naming an existing, open, not abandoned project, accepted or covered, not
    closed, with a step, whose `after_step` is in the plan and which no step of
    the plan carries yet. Oldest first; `{proposal_id, project_id}`."""
    out = []
    with _connect(path) as conn:
        for row in conn.execute(
            "SELECT id, payload FROM records WHERE kind = ? AND "
            "json_extract(payload, '$.project_id') IS NOT NULL ORDER BY rowid ASC", (PROPOSAL,),
        ).fetchall():
            proposal = json.loads(row["payload"])
            project = _get(conn, proposal.get("project_id"), PROJECT)
            if project is None or "step" not in proposal:
                continue
            if proposal.get("covered_by") is None and _accepting_ruling(conn, row["id"]) is None:
                continue
            if _is_closed(conn, "project_id", project["id"]) or _is_abandoned(conn, project["id"]):
                continue
            if _is_closed(conn, "proposal_id", row["id"]):
                continue
            steps, _version = _current_steps_and_version(conn, project)
            if proposal.get("after_step") not in _step_ids_list(steps):
                continue
            if any(st.get("proposal_id") == row["id"] for st in steps):
                continue
            out.append({"proposal_id": row["id"], "project_id": project["id"]})
    return out


def current_plan_steps(path: str | Path, project_id: str) -> list[dict]:
    """Read-only: the project's current plan (its `project` record's steps, or
    the latest `amend`'s). `[]` for an unknown project."""
    with _connect(path) as conn:
        project = _get(conn, project_id, PROJECT)
        return list(_current_steps_and_version(conn, project)[0]) if project else []


def issued_step_ids(path: str | Path, project_id: str) -> list[str]:
    """Read-only: the project's step ids with at least one target in `issued`
    (the executor's call went through and completion is not yet observed),
    in first-seen order."""
    seen: list[str] = []
    for row in target_states(path, project_id):
        if row["state"] == ISSUED and row["step_id"] not in seen:
            seen.append(row["step_id"])
    return seen


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
