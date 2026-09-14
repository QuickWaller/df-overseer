# dfqueue

The proposal queue: `docs/AGENT-ARCHITECTURE.md` §4's "one append-only record
per fort... Specialists write proposals to it; the Overseer writes plans and
decisions to it." Step 1 of the live-stream side panel
(`decisions/DECISIONS.md` 2026-09-14, "Live-stream side panel"; the fuller
build order is `handoffs/2026-09-14-proposal-queue.md`). **Local code and
tests only: no MCP tool, no publisher, no feed page, no model call.** Those
are steps 2 and 3, not built here.

**Package name is `dfqueue`, never `queue`.** A local `queue/` directory
would shadow Python's own stdlib `queue` module for anything run from the
repo root — the exact trap `dfmcp/` is named to avoid (see the root
`CLAUDE.md`'s note on `dfmcp/` and the stdlib `mcp` package).

## What this is

Three record kinds, one append-only JSONL file per fort:

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
```

There is no `selftest.py`/`report.py` pair like `learning/predictions/` and
`learning/ledger/` have — this brief asked for pytest tests instead, and
there is no grading loop yet for a report to summarise.

## Layout

```
schema.py       record kinds, the closed vocabularies, write-time validation
store.py        append-only JSONL, one file per fort, load()/append()
render.py       to_xml() (the §4 prompt form) and public_view() (the §8 allowlist)
tests/          pytest, including run #1's real proposal as a fixture
```

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

## `prediction`: validated through `learning/predictions/`, not a copy

A proposal's `prediction` field (`signal`, `op`, `value`, `check_after_ticks`
— the §4 XML shape) is built into a real `learning.predictions.schema` row
(via that module's own `new_prediction()`) and run through that module's own
`validate()`. **dfqueue does not maintain a second falsifiability gate.**
That means dfqueue inherits exactly what that module currently accepts —
and, deliberately, exactly what it currently refuses.

**What it currently accepts.** `learning.predictions.schema.validate()`
resolves `signal` as a dotted path against
`learning/ledger/schema.py`'s `FORT_FIELDS` and only accepts a signal whose
declared `source` is `MECHANICAL` or `DERIVED`. Concretely, that means the
top-level path segment must be one of: `embark`, `design`, `milestones`,
`threat_log`, `outcome`, `observations`, `experiment` (the ledger's
one-row-per-fort schema), and the leaf field it names must not be `HUMAN`- or
`AGENT`-sourced (e.g. `notes`, or any `observation`/`contributing_factor`
prose field). `predicate_op` is the same small closed vocabulary as that
module's (`eq`/`ne`/`gte`/`lte`/`gt`/`lt`/`in`/`contains`/`exists`/
`not_exists`).

**What it currently refuses, and why this matters right now.** The ledger is
one row per fort, written mostly at embark and at the end — it has **no
`landmarks`, no live perception state, no mid-fort hauling/distance
signals.** A prediction like `landmarks.<name>.exit_to_<name>.distance_tiles`
or `hauling.still_to_food.tiles` (§4's own worked example!) does not resolve
to *any* top-level ledger field, and is refused with "does not resolve to a
known ledger field" — the exact same refusal an unrelated typo would get.
**This is not a bug in dfqueue and was not loosened to make anything pass**:
`learning/predictions/README.md` already documents this as the known,
deliberate gap ("The scope this is deliberately built at... Not yet
expressible: the design doc's own headline example"), gated on a **fort
dossier** module that does not exist yet (`ROADMAP.md`).

**Concretely, today, a real architect proposal (run #1,
`evals/live/2026-09-14-architect-first-charter/run.json`) cannot pass
write-time validation**, because its only falsifiable claim is spatial
(`landmarks.new_workshop.exit_to_Wagon.distance_tiles`). `dfqueue/tests/
test_run1_fixture.py` parses that real proposal into a record and proves
this is the *only* thing wrong with it: role, type, cost, priority,
preconditions and every text field (no raw coordinates leaked) all pass
clean. Until a dossier exists and a ledger/dossier field carries something
like exit distance, no architect proposal whose prediction is spatial can be
recorded — only proposals predicting against `design`/`outcome`/`threat_log`
fields (e.g. "seal the caverns by year 3") can.

**A known translation gap, honestly flagged rather than papered over:** the
§4 wire shape carries `check_after_ticks` (a tick count), but
`learning.predictions` grades against `check_at_year` (an in-game year).
There is no tick-to-year conversion available here — that needs the fort
dossier's current-year context, which doesn't exist yet either
(`docs/AGENT-ARCHITECTURE.md` §14 item 6). `schema._validate_prediction`
currently reuses the tick count as the year integer purely so the
underlying validator's *type* and *falsifiability* checks actually run; it
is not a claim that tick 1200 means year 1200. Fix properly once the
dossier exists and a real conversion is possible.

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
- **The `propose` MCP tool.** `dfmcp/roles.py` already reserves the shape
  for it (its `planned` entries note "the queue, the sentry endpoint... not
  checked against the registry"); this stream did not touch `dfmcp/` at all.
- **The publisher** (step 2): an allowlisted-field publisher reading
  `render.public_view()` on a delay, per §8.
- **The feed page** (step 3).
- **A `plan`-aware write-ahead recovery reader.** §9's crash-consistency
  story ("a crash mid-plan is then recoverable and re-application is
  detectable") needs the `plan` kind above first.
