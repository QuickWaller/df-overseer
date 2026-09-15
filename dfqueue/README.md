# dfqueue

The proposal queue: `docs/AGENT-ARCHITECTURE.md` §4's "one append-only record
per fort... Specialists write proposals to it; the Overseer writes plans and
decisions to it." Step 1 of the live-stream side panel
(`decisions/DECISIONS.md` 2026-09-14, "Live-stream side panel"; the fuller
build order is `handoffs/2026-09-14-proposal-queue.md`). **UPDATED
2026-09-15/16: step 1's MCP tools are built and live.** `dfmcp/queue_tools.py`
exposes `queue.propose`/`pass`/`rule`/`pending` as real MCP tools, deployed on
VM 103 since 2026-09-15; the architect has written a real proposal through it
(`proposal-0001`) and the Overseer has ruled on it (`ruling-0001`, accepted,
2026-09-16). **Still not built: the publisher and the feed page** (§8's steps
2 and 3) — no model call happens on a schedule, and nothing publishes to a
public page yet.

**Package name is `dfqueue`, never `queue`.** A local `queue/` directory
would shadow Python's own stdlib `queue` module for anything run from the
repo root — the exact trap `dfmcp/` is named to avoid (see the root
`CLAUDE.md`'s note on `dfmcp/` and the stdlib `mcp` package).

## Storage: SQLite, one database per fort

Built 2026-09-14 as append-only JSONL; rebuilt 2026-09-15
(`handoffs/2026-09-15-live-signals-sqlite.md`) onto **SQLite** — the fort
ledger and the prediction log (both in `learning/`) stay JSONL, unchanged;
this reversal is scoped to live operational data only
(`decisions/DECISIONS.md` 2026-09-15). Two things JSONL doesn't give this
queue for free: concurrent writers (dfmcp, eventually, alongside this queue,
without a full-file rewrite race) and two real queries — the latest N
records for a feed, and every pending prediction whose `due_game_tick` has
arrived, both backed by a real index instead of a full scan.

Default path: `dfqueue/<fort>.sqlite3` (gitignored, along with SQLite's own
`-wal`/`-shm` sidecar files — no real database file is ever committed).
Every write goes through one transaction (`with conn:` — commits on success,
rolls back on any exception), proven in `dfqueue/tests/test_store.py` by
monkeypatching a failure between a proposal's two inserts.

Two tables:

- **`records`** — one row per queue record, keyed by the record's own
  string `id` (`"proposal-0001"`, same scheme as before): `ts`, `kind`,
  `role`, `cycle`, `type` (nullable — only proposals have one),
  `proposal_id` (nullable — only rulings have one), `payload` (the full
  validated record, as JSON).
- **`predictions`** — one row per **proposal's** prediction, `record_id`
  referencing `records.id`, inserted in the *same transaction* as the
  proposal itself: `signal`, `op`, `value`, `registered_game_tick`,
  `due_game_tick` (`registered_game_tick + check_after_ticks`), `status`
  (`learning.predictions.schema`'s own `pending`/`graded_true`/
  `graded_false`/`unresolvable` constants, reused rather than a second
  vocabulary), `actual_value`, `graded_at`, `grade_note`.

`store.py`'s public surface: `append(record, path, *, game_tick=...)`
(a proposal requires `game_tick`; `pass`/`ruling` don't), `load(path)` (every
record, append order), `latest(path, n)` (the `n` most recent, newest
first — the feed's own query), `pending_due(path, tick)` (the grader's own
query), `pending_proposals(path, limit=...)` (added `handoffs/
2026-09-15-queue-into-dfmcp.md` for `queue.pending`; every proposal with no
**final** ruling yet — see "A ruling closes a proposal, but a defer does
not" below), `apply_grades(path, updates)` (one transaction per grading
pass), and `export_jsonl(path, out_dir)` — a deterministic dump of both
tables to `records.jsonl`/`predictions.jsonl`, regenerated from SQLite
rather than hand-maintained, keeping the git-trackable, `cat`-able,
public-report form the 2026-08-27 no-database decision cared about.

### A ruling closes a proposal, but a defer does not

Revised Phase A review, 2026-09-15, after the first cut of `pending_proposals`
made a proposal vanish from the Overseer's own view the moment it got
**any** ruling, `defer` included — wrong, because `defer` means "decide
later," not "done." `append()` and `pending_proposals()` now agree on the
same rule: `RULING_DECISIONS` splits into `store.FINAL_DECISIONS`
(`accept`, `reject` — closes the proposal for good) and `defer` (leaves it
open). `pending_proposals()` excludes a proposal once any ruling naming it
has a **final** decision; `append()` refuses a *second* ruling on a
proposal that already has a final one (a repeat accept/reject, or any
ruling — even another defer — after one), but allows a ruling, including
another `defer`, after a `defer`. Both read the decision via
`json_extract(payload, '$.decision')` rather than a new column, so this
needed no `SCHEMA_VERSION` bump; confirmed working against SQLite 3.45.3
in both interpreters this project runs from (ambient `python` and
`.venv-dfmcp`) — see this stream's report for how, and for the Phase B
note that VM 103's own SQLite (Ubuntu noble, Python 3.12) still wants a
live re-check before this is trusted there, not assumed from a local
match.

## What this is

Three record kinds, one append-only SQLite database per fort:

- **`proposal`** — an advisor's proposed action: `id`, `role`, `cycle`,
  `snapshot`, `type` (closed vocabulary, see below), `summary`, `rationale`,
  `prediction`, `cost`, `suggested_priority` (1-7), `preconditions`,
  `public_rationale`. This is §4's record, field for field.
- **`pass`** — an advisor explicitly declining to propose this cycle, with a
  `reason`. The architect's `role.md` makes this a valid, even encouraged,
  outcome ("A cycle with no proposal is a valid cycle"); recording it keeps
  that visible in the audit trail instead of silently vanishing.
- **`ruling`** — the Overseer's decision on one proposal: `decision`
  (`accept`/`reject`/`defer`), `proposal_id`, `reason`, `public_rationale`.
  Only the roster's `sole_writer` (currently `overseer`,
  `agents/ROSTER.yaml`) may write one.

**Not built yet: a `plan` record.** §9's write-ahead-log record ("writes its
ordered plan to the queue before executing... marks each step done as it
goes") is the natural next kind, once the Overseer actually executes
anything. Recorded here so it isn't lost, not designed.

## Running it

```bash
python -m pytest dfqueue          # this package's own tests
python -m pytest                  # the whole repo's ambient suite
python -m pytest learning/tests   # learning.live_signals's own tests
```

There is no `selftest.py`/`report.py` pair like `learning/predictions/` and
`learning/ledger/` have — this brief asked for pytest tests instead. There is
now a grading loop (`grade.py`), but no scheduler that calls it yet — see
"What is deliberately not here yet" below.

## Layout

```
schema.py       record kinds, the closed vocabularies, write-time validation
store.py        SQLite, one database per fort, append()/load()/latest()/pending_due()/export_jsonl()
grade.py        grade_due() -- mechanical live-signal grading, game_tick_from_overview()
render.py       to_xml() (the §4 prompt form) and public_view() (the §8 allowlist)
tests/          pytest, including run #1's real proposal as a fixture
```

`learning/live_signals.py` (outside this package, see the section above)
is the signal registry both `schema.py` and `grade.py` depend on; its own
tests live in `learning/tests/test_live_signals.py`.

## The closed `type` vocabulary, keyed by role

`schema.TYPE_VOCAB_BY_ROLE` maps each role to the only proposal `type`s it
may use, drafted from that role's `role.md` "Owns" section:

| Role | Types |
|---|---|
| `architect` | `room_siting`, `workshop_siting`, `stockpile_siting`, `corridor`, `smoothing`, `dig_order` |
| `overseer` | none — it rules on proposals, it never writes one |
| `consultant` | none — `role.md`: "Does NOT own: Any fort-specific decision... Do not propose a build" |
| `quartermaster`, `marshal`, `chronicler` | none — disabled in `agents/ROSTER.yaml`, no tool surface yet |

A role can only use its own types **by construction**: a proposal is refused
if `type` isn't in its author's vocabulary, so `agents/ROSTER.yaml` gaining a
new enabled role or a role's charter changing is the only way this table goes
stale, and it is a one-line edit when it does. This is what makes a
per-role, per-type hit rate (§10) meaningful instead of accidental — a
bespoke or borrowed type would never accumulate a comparable sample.

## `prediction.signal`: a **live signal**, never a ledger field

Rebuilt 2026-09-15 (`handoffs/2026-09-15-live-signals-sqlite.md`). A
proposal's `prediction` field (`signal`, `op`, `value`, `check_after_ticks`
— the §4 XML shape) is **no longer** built into a `learning.predictions` row.
`learning/predictions/` can only grade against the fort ledger, which is one
row per fort written mostly at embark and at the end — it has no
`landmarks`, no live perception state, no mid-fort signal at all, and run #1's
real proposal (`landmarks.new_workshop.exit_to_Wagon.distance_tiles`) proved
that gap for real (see the previous version of this section, and
`dfqueue/tests/test_run1_fixture.py`'s first two tests, which still document
the exact old refusal).

`dfqueue/schema.py` now validates `prediction.signal` against
**`learning/live_signals.py`**, a small, closed registry of mid-fort signals
each read mechanically from an existing DFHack read tool (`fort.population`,
`fort.alerts.count`, `fort.stuck_jobs.count`, `fort.landmarks.count`,
`landmark."NAME".exists`, `landmark."NAME".exit."TO".distance_tiles` — see
that module's own docstring for the quoting rule, `#`/space-safe, needed
because a landmark name is a live DF string like `"Stockpile #2"`). `op` is
still checked against `learning.predictions.schema.PREDICATE_OPS` (the same
closed vocabulary, reused rather than duplicated), and `value` is now
type-checked against the *signal's own* declared type (integer or boolean),
which `learning.predictions.schema.validate()` never did since it doesn't
know what any given ledger field's type is meant to be beyond its own
generic "any" typing for `predicate_value`.

**A ledger-rooted (end-of-fort) signal is refused, on purpose, with a
message naming the right module.** `design.entrance_count`, `outcome.status`
and the like are real, gradeable `learning/ledger` fields — they are simply
not what a `dfqueue` *proposal* may predict about: those are fort-level
claims, and belong in `learning/predictions/`. `dfqueue` detects this
specifically (`learning.ledger.store.field_source(signal) is not None`) so
the refusal reads as "wrong module for this claim," not as an unexplained
typo — see `dfqueue/tests/test_schema.py`'s
`test_prediction_signal_pointing_at_a_ledger_field_is_refused` and its
`_also_refused` sibling (proving even a *gradeable* ledger field is still
refused here).

**The old check_after_ticks/check_at_year translation gap this section used
to flag no longer exists.** `dfqueue`'s prediction never becomes a
`learning.predictions` row now, so there is nothing to translate: a
proposal's `check_after_ticks` is added straight to the fort's current
absolute tick (`dfqueue/grade.py`'s `game_tick_from_overview`) to get
`due_game_tick`, stored and compared in the very same unit throughout.

**Concretely, today, run #1's real proposal (`evals/live/
2026-09-14-architect-first-charter/run.json`) fails verbatim** (its raw,
unquoted signal string predates this grammar) **but passes once its signal
is rewritten into the quoted-landmark form**,
`landmark."new_workshop".exit."Wagon".distance_tiles` — and then grades
`graded_true`/`graded_false`/`unresolvable` correctly depending on what a
later `landmarks.get` call reports, all proven in `dfqueue/tests/
test_run1_fixture.py`.

## Grading: `dfqueue/grade.py`

`grade_due(db, current_game_tick, call_tool, graded_at)` reads every pending
prediction whose `due_game_tick` has arrived (`store.pending_due`), reads its
signal through `learning.live_signals.read()` (via the same injected
`call_tool` the registry itself takes — no DFHack/MCP import in this
package either), applies the exact same predicate logic
`learning/predictions/grade.py` uses (`apply_predicate`, a public alias for
that module's own `_apply`, the brief's one allowed additive change to
`learning/`), and writes every result — `status`, `actual_value`,
`graded_at`, `grade_note` — in one transaction (`store.apply_grades`).
Idempotent by construction: a graded row is no longer `pending`, so
`pending_due` never hands it back on a later call.

`game_tick_from_overview(overview_json)` turns `overview.get`'s
`tier2.in_game_date` string into one absolute, monotonic tick: `T` in that
string is `dfhack.world.ReadCurrentTick()`, which reads
`df.global.cur_year_tick` (verified live on VM 103 2026-09-15: both 178877
at year 30, while `world.frame_counter` was 44275), so ticks **within the
current in-game year**, resetting to 0 every
year boundary, not a running total since world creation. So
`year * 403200 + tick` (DF's fortress-mode calendar is fixed: 1200
ticks/day x 28 days/month x 12 months/year = 403,200 ticks/year, per the
[DF Wiki's "Time" article](https://dwarffortresswiki.org/index.php/DF2014:Time))
is what actually stays comparable turn to turn. Both figures were checked
this session against DFHack's published docs and the DF Wiki via WebFetch,
not against a live VM — see the handoff report for the exact citations.

## Coordinates

Every free-text field (`summary`, `rationale`, `public_rationale`, `reason`)
is scanned for a raw-coordinate pattern (`x=12`, `z=-3`, a bracketed or
parenthesised numeric triple like `(4, 9, -2)`) and refused if one appears —
`docs/PURPOSE.md` design commitment #1, "the model is never shown a map,"
applies just as much to a coordinate leaking into an advisor's own rationale
as to a rendered tile grid. The regex is deliberately conservative: it does
not flag ordinary named-landmark/relative-direction prose ("5 tiles SE of
Embark Site", "3x3", "level -1", "priority 4"), because a filter that also
catches normal prose trains advisors to write around it.

## The public-view allowlist

`render.public_view(record)` returns **only** `id`, `ts`, `kind`, `role`,
`type`, `public_rationale`, `decision` and `suggested_priority` — §8's
published-field list plus the three identity fields this brief added so a
future feed can order and thread items. It is an allowlist, not a redaction:
`dfqueue/tests/test_render.py` proves this by adding a brand-new field to a
record and checking it never appears in the view, not just that today's
known-sensitive fields are absent. Everything else on a record — `rationale`
(as opposed to `public_rationale`), `prediction`, `cost`, `preconditions`,
`cycle`, `snapshot`, a ruling's `reason` and `proposal_id` — never reaches
this function's return value.

## What is deliberately not here yet

- **A `plan` record kind** (see above).
- **A grader schedule.** `grade.grade_due()` exists and is tested end to
  end, but nothing calls it on a timer or after a real DFHack poll yet: that
  needs a live `call_tool` wired to `dfmcp` or a direct DFHack RPC call.
- **The publisher** (step 2): an allowlisted-field publisher reading
  `render.public_view()` on a delay, per §8.
- **The feed page** (step 3).
- **A `plan`-aware write-ahead recovery reader.** §9's crash-consistency
  story ("a crash mid-plan is then recoverable and re-application is
  detectable") needs the `plan` kind above first.

**The `propose`/`pass`/`rule`/`pending` MCP tools are now built**, as of
`handoffs/2026-09-15-queue-into-dfmcp.md`: `dfmcp/queue_tools.py` is the
tool layer, four native (non-DFHack) tools merged into `dfmcp`'s registry.
`dfqueue/store.py` grew one additive query (`pending_proposals`) for
`queue.pending`, and `agents/architect/tools.yaml` and
`agents/overseer/tools.yaml` grant the real calls.

**UPDATED 2026-09-15: Phase B deployed this to VM 103, no longer local-only.**
The queue DB lives at `/var/lib/dfmcp/Uniboslan.sqlite3`
(`MCP_SERVER_QUEUE_DB`, a `StateDirectory=dfmcp` path outside the code
checkout, per Phase B's design). Architect run #3 called `queue.propose`
through the live service and wrote the first real record, `proposal-0001`
(`handoffs/2026-09-15-queue-live-deploy.md`). **UPDATED 2026-09-16:** a
second openclaw agent, the Overseer, called `queue.rule` and accepted it as
`ruling-0001` (`handoffs/2026-09-15-overseer-first-ruling.md`). **The fort
was kept paused at tick 12274877 under the user's standing rule until
2026-09-15 23:03 UTC (register)**, so neither executing the proposal nor
grading its prediction could happen during that window, and no grader
schedule exists yet regardless (see "What is deliberately not here yet").
