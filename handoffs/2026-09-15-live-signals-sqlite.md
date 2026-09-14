# Stream: live-state prediction signals, graded into a SQLite ledger

**Written** 2026-09-15. **Status:** dispatched. **User go-ahead:** agreed to
live-state signals ("it should form a ledger") and chose **SQLite on VM 103**
over a shared Postgres or JSONL with a derived copy
(`decisions/DECISIONS.md` 2026-09-15). **This stream is local code and tests
only**: no dfmcp wiring, no deploy, no VM, no model call.

## Why

`dfqueue/` (`handoffs/2026-09-14-proposal-queue.md`) validates predictions
through `learning/predictions/`, which accepts only **end-of-fort** ledger
fields. No mid-fort or spatial signal exists, so **every architect proposal
is refused**. Run #1's real proposal fails only on its signal,
`landmarks.new_workshop.exit_to_Wagon.distance_tiles`. The queue also stores
JSONL, which concurrent writes from dfmcp will make fragile, and the coming
feed and grader need queries.

## Read first

1. `dfqueue/` in full (schema, store, render, README, tests), including the
   `check_after_ticks` to `check_at_year` stand-in comment, which this stream
   removes.
2. `learning/predictions/schema.py`, `grade.py`, `README.md`, and
   `learning/ledger/store.py`'s `field_source` / `assert_gradeable`. The
   discipline to keep is: mechanical only, a falsifiable predicate, and never
   grading from the agent's own account.
3. Real tool output shapes, from the scripts rather than from memory:
   - `scripts/dfhack/df-overseer-overview.lua`: `population`, `alerts`,
     `landmarks`, and `in_game_date` "year Y, month M, day D, tick T". **Check
     what T is** (for example `cur_year_tick`) before building a clock on it.
   - `df-overseer-landmarks.lua` `get NAME` and `list`: `exits` entries
     with `to`, `direction`, `distance_tiles`, `walkable`.
   - `df-overseer-stuckjobs.lua` `find`, which returns a bare array.
   - `scripts/dfhack/TOOLS.yaml` for the tool ids and signatures.
4. `decisions/DECISIONS.md` rows 2026-08-27 (fort ledger JSONL) and
   2026-09-15 (this reversal, and its scope).

## Build

### 1. Live signal registry: `learning/live_signals.py` (new, additive)

A closed registry of **mid-fort signals, each read mechanically from an
existing read tool**. A signal is a dotted name built only from landmark
names and fixed words, never a coordinate. Each entry declares the tool id,
how to build its arguments from the name, how to extract the value from the
tool's JSON, the value type, and its source (`MECHANICAL`, reusing
`learning/`'s constants). The initial set:

| signal | tool | value |
|---|---|---|
| `fort.population` | `overview.get` | `population` (int) |
| `fort.alerts.count` | `overview.get` | `len(alerts)` |
| `fort.stuck_jobs.count` | `stuckjobs.find` | `len(result)` |
| `fort.landmarks.count` | `landmarks.list` | `len(result)` |
| `landmark.<A>.exists` | `landmarks.list` | bool: a landmark named A exists |
| `landmark.<A>.exit.<B>.distance_tiles` | `landmarks.get A` | the `distance_tiles` of the exit whose `to` is B |

Landmark names contain spaces and `#` ("Stockpile #2"), so define the
quoting rule explicitly (for example `landmark."Stockpile #2".exit."Wagon".distance_tiles`),
and test names with spaces, `#` and dots. Provide:
- `parse(signal) -> ParsedSignal | error`;
- `read(parsed, call_tool) -> value | UNRESOLVABLE`, where `call_tool(tool_id,
  arguments) -> parsed JSON` is injected, so no DFHack or MCP import appears
  here. A landmark that doesn't exist, or doesn't exist *yet*, is
  **unresolvable, not an error**: a proposal may predict about something it
  proposes to build.

Don't change existing `learning/` behaviour. If reusing `grade.py`'s
predicate logic (`_apply`) needs a public name, adding that alias is allowed
as the one additive change. Copying the logic is not.

### 2. SQLite store: replace `dfqueue/store.py`'s JSONL backend

- One database per fort, default `dfqueue/<fort>.sqlite3` (gitignore
  `dfqueue/*.sqlite3*`). Stdlib `sqlite3`, WAL mode, a `schema_version`
  table, and every write in a transaction.
- Tables:
  - `records`: `id` PK, `ts`, `kind`, `role`, `cycle`, `type` nullable,
    `proposal_id` nullable FK, `payload` JSON (the full validated record);
  - `predictions`: `id` PK, `record_id` FK, `signal`, `op`, `value` JSON,
    `registered_game_tick`, `due_game_tick`, `status`, `actual_value` JSON,
    `graded_at`, `grade_note`;
  - indexes for the two real queries: latest N records by `ts`, and pending
    predictions with `due_game_tick` at or before a given tick.
- `append(record, *, game_tick)` validates first. **A refused record writes
  nothing to either table**, with every error listed as before. A proposal's
  prediction row is inserted in the **same transaction**, with
  `due_game_tick = game_tick + check_after_ticks`. Keep the `load()` / query
  helpers the feed will need: `latest(n)` and `pending_due(tick)`.
- `export_jsonl(out_dir)`: a deterministic dump of both tables, in stable
  order, git-trackable, for the public-report goal (the 2026-09-15 decision
  keeps that).

### 3. Validation change: `dfqueue/schema.py`

- A proposal's `prediction.signal` must be a **live signal** (it parses in
  the registry). Validate the op against `learning.predictions.schema.PREDICATE_OPS`,
  the value against the signal's type (a presence op carries no value, as
  in `learning/`), and `check_after_ticks` as an integer > 0.
- **Remove the tick-as-year stand-in.** An end-of-fort ledger signal in a
  proposal is refused with a message saying fort-level claims belong in
  `learning/predictions/`. Proposals are about mid-fort effects.

### 4. Grader: `dfqueue/grade.py`

`grade_due(db, current_game_tick, call_tool, graded_at)` does four things:
- reads every pending prediction that is due;
- reads its signal through the registry;
- applies the shared predicate logic;
- writes `status` (`graded_true`, `graded_false` or `unresolvable`, using
  `learning.predictions`' constants), `actual_value`, `graded_at` and
  `grade_note`, all in one transaction.

It is pure apart from the db and the injected `call_tool`. Also write
`game_tick_from_overview(overview_json)`, deriving an absolute tick from
`in_game_date` with a DF year of 403200 ticks. **Verify that constant and
what T is from the script and DFHack docs, and state your source.**

### 5. Tests

- **Registry:** parsing, including names with spaces and `#`; each signal
  read against fake tool JSON **copied from real output shapes** in the
  scripts, never invented. Missing landmark and missing exit are
  unresolvable.
- **Store:** append and read round-trip; a refused record leaves both tables
  unchanged; the proposal and its prediction commit atomically (simulate a
  failure between the two inserts and prove neither lands); a dangling
  ruling is refused; `latest`, `pending_due` and deterministic
  `export_jsonl`.
- **Grader:** true, false and unresolvable; not-yet-due stays pending;
  idempotent re-run.
- **Run #1's real proposal**, with its signal rewritten as
  `landmark."<workshop name>".exit."Wagon".distance_tiles` (the fixture may
  name the workshop), now **passes**. A later fake read showing the workshop
  7 tiles from the Wagon grades `lte 7` as true.
- The existing `dfqueue` tests are updated rather than deleted, and
  `public_view` is still allowlisted.

### 6. Docs

Update `dfqueue/README.md`: SQLite, the tables, the live signals and how to
add one, grading, the export, and what is deliberately not here yet (the
dfmcp `propose` tool, a grader schedule, the feed publisher). Add a short
live-signals section to `learning/predictions/README.md` pointing to the new
registry, since this is additive to `learning/`.

## Hard lines

- No change to `dfmcp/`, no deploy, no VM, no model call, and no real database
  file committed.
- `learning/` changes are limited to the new `live_signals.py`, an optional
  public alias for the predicate function, and the README pointer. Existing
  `learning/` tests must still pass unchanged.
- No commits (the orchestrator reviews and commits). Don't edit
  `Working.md`, `decisions/`, `memory/`, `CLAUDE.md`, `docs/` or other
  handoff docs. Add a Result section here and your row in `handoffs/INDEX.md`.

## Report

Executor shape, plus:
- files changed;
- test counts before and after (ambient `python -m pytest` is `188 passed,
  1 skipped` before), and `python -m learning.predictions.selftest` still
  passing;
- what T in `in_game_date` actually is, and the ticks-per-year source;
- the signal quoting rule chosen;
- anything this brief got wrong.
