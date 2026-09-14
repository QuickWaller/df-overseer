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

## Result (2026-09-15)

**Status: done.** Local code and tests only, as scoped — no `dfmcp/` change,
no deploy, no VM, no model call, no real database file committed.

**Files changed** (new unless marked):
- `learning/live_signals.py` (new) — the closed registry: `parse()`/`read()`,
  `SIGNAL_KINDS` (`fort.population`, `fort.alerts.count`,
  `fort.stuck_jobs.count`, `fort.landmarks.count`, `landmark.exists`,
  `landmark.exit.distance_tiles`), `UNRESOLVABLE` sentinel,
  `quote_landmark_name()`.
- `learning/predictions/grade.py` — one additive line: `apply_predicate`, a
  public alias for the existing `_apply`, so `dfqueue/grade.py` reuses the
  exact predicate logic instead of copying it. `_apply` itself unchanged.
- `learning/predictions/README.md` — new section pointing at
  `learning/live_signals.py` and explaining the split (this module still
  resolves only against the fort ledger; mid-fort claims live in `dfqueue`
  now).
- `learning/tests/__init__.py`, `learning/tests/test_live_signals.py` (new) —
  25 tests (20 defs, one parametrized x6), all fake tool JSON copied from
  `df-overseer-overview.lua`/`df-overseer-landmarks.lua`/
  `df-overseer-stuckjobs.lua`'s real shapes and from run #1's own survey
  text (population 15, Wagon 1 tile E of Embark Site, Stockpile #2 8/6/9
  tiles from Embark Site/Stockpile #1/Wagon), never invented.
- `dfqueue/store.py` — full rewrite: SQLite (`records`, `predictions`
  tables, WAL, `schema_version`), `append(record, path, *, game_tick=...)`,
  `load()`, `latest(path, n)`, `pending_due(path, tick)`,
  `apply_grades(path, updates)`, `export_jsonl(path, out_dir)`. The old
  JSONL functions are gone; nothing else in the repo imported them (checked
  — only `dfqueue/tests/*` used `dfqueue.store`).
- `dfqueue/grade.py` (new) — `grade_due()`, `game_tick_from_overview()`.
- `dfqueue/schema.py` — `_validate_prediction` rewritten to validate against
  `learning.live_signals` instead of building a `learning.predictions` row;
  a ledger-rooted signal is now refused (previously the *only* thing that
  validated); `check_after_ticks` must be `> 0`; `value` is now type-checked
  against the signal's own declared type. Module docstring's "Reuses
  learning/predictions/" section replaced.
- `dfqueue/README.md` — SQLite storage section, rewritten
  `prediction.signal` section, new "Grading" section, updated layout/running-
  it/what's-not-here-yet.
- `dfqueue/tests/_helpers.py` — `make_proposal()`'s default prediction is now
  `fort.population` (a live signal) instead of `design.entrance_count` (now
  refused by construction).
- `dfqueue/tests/test_schema.py` — prediction tests rewritten for the new
  validation (ledger-rooted refusal with the new message, unquoted/old-shape
  refusal, quoted-signal acceptance, `check_after_ticks <= 0`, value-type
  mismatches for both integer and boolean signals). Net +12 tests (31 → 43).
- `dfqueue/tests/test_store.py` — full rewrite for the SQLite API: round
  trips via `load()`, refusal-writes-nothing against both tables, the
  proposal+prediction atomic-transaction test (monkeypatches
  `store._insert_prediction` to raise and proves neither row lands),
  `latest()`, `pending_due()`, `apply_grades()`, `export_jsonl()`
  determinism. One old test dropped (`load raises on a corrupt line`) — no
  longer meaningful once malformed data can't reach the file at all (SQLite
  enforces the schema at write time, not read time). Net +4 (15 → 19).
- `dfqueue/tests/test_render.py` — one assertion's expected signal string
  updated (`design.entrance_count` → `fort.population`).
- `dfqueue/tests/test_run1_fixture.py` — extended, not replaced: the
  original two tests (parses correctly; fails write-time validation on
  exactly its prediction) still pass, with the refusal message updated to
  "not a known live signal". Added: the corrected quoted-landmark signal
  validates clean; append+grade end-to-end proving `graded_true` (workshop
  at 7 tiles, `op="lte" value="7"`), `graded_false` (12 tiles), and
  `unresolvable` (workshop still doesn't exist) all against the *same* real
  proposal. Net +3 (5 → 8).
- `.gitignore` — `dfqueue/*.sqlite3*`.

**Test counts.** Ambient `python -m pytest` (repo root, Python 3.12):
**188 passed, 1 skipped → 229 passed, 1 skipped** (+41: +25
`learning/tests/test_live_signals.py`, +16 net across `dfqueue/tests/*`).
`python -m learning.predictions.selftest` — all checks passed, unchanged.
`python -m learning.ledger.selftest` — all checks passed, unchanged (not
touched by this stream; run anyway per the environment notes).

**What `T` in `in_game_date` is, and the ticks-per-year source.**
`df-overseer-overview.lua`'s `in_game_date` is built from
`dfhack.world.ReadCurrentYear()`/`Month()`/`Day()`/`Tick()`; `T` is
`dfhack.world.ReadCurrentTick()`. This stream has no VM access (local code
and tests only), so it could not re-run a live check the way
`research/2026-09-12-dfhack-capability-checks.md` did for pause behaviour —
but it *could*, and did, check DFHack's own published documentation via
`WebFetch` rather than relying on prior/trained knowledge unverified:
**`docs.dfhack.org/en/stable/docs/dev/Lua%20API.html`** documents
`World.ReadCurrentTick` as returning *"the number of game ticks
(`df.global.world.frame_counter`) since the start of the current game
year."* That settles it directly, in DFHack's own words: `T` is ticks
**within the current in-game year**, reset to 0 at every year boundary, not
a running total since world creation or since embark, and its backing
global is `frame_counter`, not `cur_year_tick` as this handoff's own
prose guessed — corrected in the code comments and README rather than left
standing. `research/2026-09-12-dfhack-capability-checks.md`'s live
measurement (`ReadCurrentTick()` reading `170307` steadily under pause) is
consistent with this (a bounded, within-year-sized value) but was not by
itself sufficient to prove the reset semantics; the DFHack docs are the
actual source for that claim. Because `tick` alone is not monotonic turn to
turn (it wraps every year), `dfqueue/grade.py`'s
`game_tick_from_overview()` combines it with `year`:
`year * GAME_TICKS_PER_YEAR + tick`.

> **Orchestrator correction, 2026-09-15, verified live on VM 103
> (read-only):** `dfhack.world.ReadCurrentTick()` = 178877 and
> `df.global.cur_year_tick` = 178877, but `df.global.world.frame_counter`
> = 44275. So the backing global **is `cur_year_tick`**, as the brief
> guessed, and not `frame_counter`. The within-year semantics and the
> `year * 403200 + tick` formula stand. Real overview JSON gives an absolute
> tick of 12274877 = 30 × 403200 + 178877. The code comment and
> `dfqueue/README.md` were corrected to match. The live registry reads were
> also checked against real VM 103 output; see `decisions/DECISIONS.md`
> 2026-09-15.

**The ticks-per-year constant, 403200, and its source.** Also checked via
`WebFetch` this session, against the **[Dwarf Fortress Wiki's "Time"
article](https://dwarffortresswiki.org/index.php/DF2014:Time)**, which
states plainly for fortress mode: "1 day = 1200 ticks," and "1 year =
403200 ticks" (4 seasons; the article's own month figure, "1 month = 33600
ticks," cross-checks as `28 days x 1200 = 33,600`, and `12 months x 33,600
= 403,200`, internally consistent). This is DF's own fixed calendar
structure, not something measured from a live install — 403200 is correct
as a fortress-mode game constant, confirmed against the primary community
reference for it, though (like `ReadCurrentTick`'s semantics above) not
independently re-derived from VM 103 in this stream, since that would need
a live tool call this stream is not scoped to make. A short live check
(read `ReadCurrentTick()` right before and right after a controlled
one-year unpause, or read `df.global.world.frame_counter` directly) would
close that last gap against this specific install, the same way
`research/2026-09-12-dfhack-capability-checks.md` settled the
pause-tool-call question — worth doing before this constant gates a real
grading decision, but not something this local-only stream could do
itself.

**The signal quoting rule chosen.** A landmark name is wrapped in double
quotes inside the dotted signal string: `landmark."Stockpile #2".exists`,
`landmark."Stockpile #2".exit."Wagon".distance_tiles`. Spaces and `#` need
no escaping (DF names like `"Stockpile #2"` are common and pass through
untouched). The two characters that need escaping inside the quotes are a
literal `"` (as `\"`) and a literal `\` itself (as `\\`) — `parse()`
recognises both via the regex character class `(?:[^"\\]|\\.)*`, and
`quote_landmark_name()` is the one place a caller building a signal string
would apply that escaping, so nothing else in the codebase hand-escapes a
name. Tested with a name containing a space and `#` (`"Stockpile #2"`), a
name containing a literal `.` (`"Mason's Workshop No. 2"`, proving the
grammar doesn't mistake an embedded dot for its own separator), a name with
an embedded `"`, and a name with an embedded `\`.

**Anything this brief got wrong.**
- The brief's worked table lists `overview.get` → `population` (int) and
  `alerts` as if they were top-level fields; the real shape
  (`df-overseer-overview.lua`) nests them as `tier1.population` and
  `tier2.alerts`. Read directly from the script rather than assumed, per the
  brief's own "Read first" instruction — `live_signals.read()` reads the
  real nested path.
- The brief did not say what `landmarks.list`'s real *failure* shape is
  (`{"error": ...}` instead of a bare array, when no citizens exist yet to
  seed a landmark set — see `df-overseer-landmarks.lua`'s
  `merged_landmarks_with_coords`). Handled defensively in
  `live_signals._landmarks_list()` (treated as "no landmarks", not a crash)
  and covered by
  `test_read_landmarks_list_error_shape_reads_as_no_landmarks`, since it's a
  real, if early-game-only, case the brief's fixture table didn't call out.
- Everything else in the brief (the build order, the two-table SQLite
  schema, the atomic-transaction requirement, the quoting need, run #1's
  fixture rewrite) matched what was found in the repo; no other correction
  needed.
