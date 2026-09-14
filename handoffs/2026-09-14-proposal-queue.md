# Stream: the proposal queue (write-time validated), step 1 of the live-stream feed

**Written** 2026-09-14. **Status:** dispatched. **User go-ahead:** "go ahead",
in reply to the plan below. **Local code and tests only**: no MCP exposure, no
deploy, no VM.

## Why

The user wants a scrolling feed beside the live game stream showing advisor
proposals and Overseer rulings (`decisions/DECISIONS.md` 2026-09-14, "Live-stream
side panel"). Nothing produces that feed yet. `docs/AGENT-ARCHITECTURE.md` §4
already specifies the channel: **one append-only queue per fort, written by
tool calls with typed fields, validated at write time, where a malformed
proposal is refused.** Architect run #2
(`evals/live/2026-09-14-architect-second-charter/`) showed why this has to be
enforced in code: told to use the record format, the model wrote prose instead.

Build order: (1) **this stream**, (2) a publisher of allowlisted fields
(`role`, `type`, `public_rationale`, decision, priority; the user waived §8's
30-60s delay for now), (3) the stream page. Steps 2 and 3 are not in scope.

## Read first

1. `docs/AGENT-ARCHITECTURE.md` §4 ("The queue is the channel", "Writes are
   tool calls; reads are XML", the proposal record and its four fields) and
   the §9/§10 references to the queue as write-ahead log and to hit rates by
   `type`.
2. `learning/predictions/` (`schema.py`, `store.py`, `selftest.py`,
   `README.md`): the **existing** prediction record, its write-time
   validation, the ledger-backed signal check, and the append-only JSONL
   store pattern. Reuse it; do not write a second prediction validator.
3. `learning/ledger/schema.py`: the vocabulary and `unrecorded` conventions.
   Match that house style.
4. `agents/ROSTER.yaml` and `agents/*/role.md`.
5. `dfmcp/roles.py` around its comment on non-DFHack tools ("the queue, the
   sentry endpoint"). Read only, to know what the later `propose` tool will
   plug into. Don't change it.

## What to build

A package **`dfqueue/`** at the repo root. **Not `queue/`**: that shadows
Python's stdlib `queue` for anything run from the repo root, which is the same
trap `dfmcp/` is named to avoid. Say so in its README.

1. **Schema** (`dfqueue/schema.py`), following `learning/`'s style:
   - **Record kinds:** `proposal` (an advisor), `pass` (an advisor
     explicitly declining this cycle, with a reason, since `role.md` makes
     that a valid outcome), and `ruling` (the Overseer only: `accept`,
     `reject` or `defer`, plus `proposal_id`, `reason` and `public_rationale`).
     No `plan` record yet. Note it as the next kind in the README.
   - **Proposal fields** exactly as §4's record: `id`, `role`, `cycle`,
     `snapshot`, `type`, `summary`, `rationale`, `prediction`, `cost`
     (`estimate` > 0, `unit` from a small vocabulary starting
     `dwarf_ticks`), `suggested_priority` (1-7), `preconditions` (a list of
     `{landmark|area, state}`), `public_rationale`. Every text field must be
     non-empty.
   - **The closed `type` vocabulary**, drafted from the architect's `role.md`
     "Owns" and to be revised as roles are added: `room_siting`,
     `workshop_siting`, `stockpile_siting`, `corridor`, `smoothing`,
     `dig_order`. Put it in one table **keyed by role**, so a role can only
     use its own types. The consultant answers questions and doesn't propose,
     so give it no proposal types, and state that reasoning in a comment.
   - **Role checks**: a record's `role` must be an enabled role in
     `agents/ROSTER.yaml`; only the roster's `sole_writer` may write a
     `ruling`; a ruling's `proposal_id` must refer to an existing proposal in
     the same queue.
   - **`prediction`**: build and validate it **through
     `learning/predictions/`'s own validation**, not a copy. If that
     validator refuses spatial signals such as
     `landmarks.<name>.exit_to_<name>.distance_tiles` (run #1's prediction),
     **do not loosen it**. Report exactly which signals it currently accepts,
     because that decides whether any architect proposal can pass today.
   - **Coordinates**: refuse any text field matching a raw-coordinate pattern
     (`x=12`, a bracketed or parenthesised numeric triple, `z=-3`), in line
     with design commitment #1. Keep the regex conservative, and test that
     phrases like "5 tiles SE of Embark Site", "3x3", "level -1" and
     "priority 4" pass.
2. **Store** (`dfqueue/store.py`): append-only JSONL, one file per fort,
   default path `dfqueue/<fort>.jsonl` from the roster's `fort`; tests use a
   temp path. `append(record)` validates and **refuses a malformed record
   with every error listed**, writing nothing. It assigns `id` and a UTC
   `ts` if absent. Also `load()`. Match `learning/predictions/store.py`.
   Don't commit a real queue file.
3. **Rendering** (`dfqueue/render.py`): `to_xml(record)`, the prompt form
   from §4, with values XML-escaped; and `public_view(record)`, which returns
   **only** `role`, `type`, `public_rationale`, the ruling's decision (for a
   ruling) and `suggested_priority`, plus `id`, `ts` and `kind` so the feed
   can order and thread items. Step 2 publishes from this function, so its
   allowlist test matters: add a field to a record and prove it never
   appears.
4. **Tests** (`dfqueue/tests/`, pytest):
   - a valid proposal, pass and ruling round-trip through append, load and
     `to_xml`;
   - each refusal:
     - unknown kind or field;
     - missing or empty required field;
     - `type` not in the role's vocabulary;
     - consultant proposal;
     - non-Overseer ruling;
     - dangling `proposal_id`;
     - priority out of range;
     - cost ≤ 0;
     - coordinate in the rationale;
     - bad prediction.
   - the file is unchanged after any refusal;
   - the public-view allowlist.

   Include **run #1's real proposal**
   (`evals/live/2026-09-14-architect-first-charter/run.json`, the `final`
   field's XML) as a fixture, parsed into a record. Report whether it passes,
   and if not, exactly which checks refuse it.
5. **README** (`dfqueue/README.md`): what it is, the record kinds, the
   vocabulary and how to extend it, the public-view allowlist, and what is
   deliberately not here yet (`plan` records, the `propose` MCP tool, the
   publisher, the feed page).

## Hard lines

- No MCP exposure, no change to `dfmcp/`, no deploy, no VM, no model call.
- Don't change `learning/` behaviour. If reusing it needs a small, genuinely
  additive helper, stop and report it instead of making the change.
- No commits (the orchestrator reviews and commits). Don't edit
  `Working.md`, `decisions/`, `memory/`, `CLAUDE.md`, `docs/` or other
  handoff docs. Add a Result section here and your row in `handoffs/INDEX.md`.

## Report

Executor shape, plus:
- files created;
- the test count, and that the existing suite still passes (ambient
  `python -m pytest`: 127 passed, 1 skipped before; the venv
  `.venv-dfmcp` for `dfmcp/tests` if it matters);
- which prediction signals are currently accepted;
- whether run #1's proposal passes and why;
- anything this brief got wrong.

## Result

```
STREAM: 2026-09-14-proposal-queue   STATUS: done
DID: Built dfqueue/ (schema.py, store.py, render.py, README.md, tests/).
  Three record kinds (proposal/pass/ruling), the closed type-vocab-by-role
  table, write-time validation with every error listed, append-only JSONL
  store per fort, to_xml/public_view rendering. Reused
  learning.predictions.schema.validate() unmodified for the prediction
  field rather than duplicating its falsifiability gate. No dfmcp/, no
  learning/, no ROSTER.yaml, no CLAUDE.md/docs/ changes. No commits.
VERIFIED: `python -m pytest dfqueue -q` -> 61 passed. Ambient
  `python -m pytest` from repo root -> 188 passed, 1 skipped (was 127
  passed, 1 skipped; rose by exactly the 61 new tests, nothing else moved).
  `git status --porcelain learning/ agents/ dfmcp/` empty throughout.
  Confirmed no stray dfqueue/<fort>.jsonl was left in the working tree
  after the run (`find dfqueue -name "*.jsonl"` empty).
DOCS UPDATED: this file (this Result section), handoffs/INDEX.md (new row).
  Working.md, decisions/DECISIONS.md, memory/ deliberately left untouched,
  per this brief's hard lines -- the orchestrator owns those.
BLOCKED/HANDBACK: none.
NEXT: step 2 (the allowlisted-field publisher, reading render.public_view()
  on a delay per AGENT-ARCHITECTURE.md §8) and step 3 (the feed page) are
  still out of scope. Before either lands for real: (a) a fort dossier
  module is the actual gate on any architect proposal whose prediction is
  spatial -- see the two open items below; (b) dfqueue/README.md names the
  check_after_ticks -> check_at_year translation as a known gap to fix once
  a dossier exists.
```

### Files created

```
dfqueue/__init__.py
dfqueue/schema.py
dfqueue/store.py
dfqueue/render.py
dfqueue/README.md
dfqueue/tests/__init__.py
dfqueue/tests/_helpers.py           # record builders, not a test module
dfqueue/tests/test_schema.py        # 33 tests: every refusal + vocab + coordinate regex
dfqueue/tests/test_store.py         # 15 tests: append/load round trip, refusal-writes-nothing
dfqueue/tests/test_render.py        # 8 tests: to_xml well-formedness, public_view allowlist
dfqueue/tests/test_run1_fixture.py  # 5 tests: run #1's real proposal, parsed and validated
```

### Test count and ambient suite

`python -m pytest dfqueue -q` -> **61 passed**. Ambient `python -m pytest`
from the repo root: **188 passed, 1 skipped** (baseline was 127 passed, 1
skipped; the rise is exactly the 61 tests added here, confirmed by running
`dfqueue`'s suite alone and diffing the counts). Did not need
`.venv-dfmcp`: `dfqueue` imports nothing from `dfmcp` or the MCP SDK
(`grep -rn "import mcp\|from mcp\|import dfmcp\|from dfmcp" dfqueue/` is
empty), and the ambient Python 3.12 interpreter already has `pyyaml` and
`pytest` installed, which is everything `dfqueue` needs.

### Which prediction signals are currently accepted, exactly

`dfqueue.schema._validate_prediction` builds a row via
`learning.predictions.schema.new_prediction()` and validates it via that
module's own `validate()`, unmodified. That function resolves `signal`
(a dotted path) against `learning/ledger/schema.py`'s `FORT_FIELDS` and
requires the resolved field's declared `source` to be `MECHANICAL` or
`DERIVED` (never `HUMAN` or `AGENT`). Concretely, **today, a signal is
accepted if and only if**:

1. its top-level path segment is one of `embark`, `design`, `milestones`,
   `threat_log`, `outcome`, `observations`, `experiment` (the seven
   sub-records of `FORT_FIELDS` in `learning/ledger/schema.py`), and
2. the leaf field that path resolves to is `MECHANICAL`- or
   `DERIVED`-sourced (checked field by field in `EMBARK_FIELDS`,
   `DESIGN_FIELDS`, etc. -- e.g. `design.entrance_count`,
   `design.caverns_sealed_year`, `outcome.total_deaths`,
   `threat_log.0.breach_location` all qualify; `notes`,
   `observations.0.rationale`, `contributing_factor.evidence` do not, being
   `AGENT`/`HUMAN`-sourced).

**Not accepted, structurally, until a fort dossier module exists**: anything
about live/mid-fort/spatial state -- landmarks, exit distances, hauling
paths, stockpile fill levels, idle counts. There is no top-level `landmarks`
or `hauling` (or similar) field in `FORT_FIELDS` at all, so any such signal
is refused with "does not resolve to a known ledger field," identically to
a typo. This is not new information -- `learning/predictions/README.md`
already documents it as "The scope this is deliberately built at... Not yet
expressible" -- but this stream is the first place it blocks a real,
already-produced architect output.

### Does run #1's real proposal pass? No -- one check, named exactly

`evals/live/2026-09-14-architect-first-charter/run.json`'s `final` field's
fenced `<proposal id="p-0001" ...>` block, parsed into a dfqueue record by
`test_run1_fixture.py` and run through `schema.validate()` for real (not a
paraphrase):

```
record.prediction -> learning.predictions: row.signal: 'landmarks.new_workshop.exit_to_Wagon.distance_tiles' does not resolve to a known ledger field
```

That is the **only** error. Everything else about the real proposal passes
clean: `role="architect"` is enabled and owns `type="workshop_siting"`;
`cost estimate="350" unit="dwarf_ticks"` is a positive number in the known
unit vocabulary; `suggested_priority="3"` is in 1-7; all three
`preconditions` (`landmark="Embark Site"`, `landmark="Wagon"`,
`area="open_ground_5x5_S_of_Embark_Site_5tiles"`, each with a `state`) fit
the `{landmark|area, state}` shape; and none of `summary`, `rationale` or
`public_rationale` trips the raw-coordinate regex despite being full of
distances ("5 tiles S", "9 tiles SW", "1 tile W" all read as relative
directions, not coordinates). `test_a_ledger_rooted_signal_in_the_same_
shape_would_have_passed` swaps only the signal for `design.entrance_count`
and confirms the same record then validates with zero errors -- proving the
refusal is specifically about the signal, not something else in the record
that happens to correlate with it.

### Anything this brief got wrong

One real gap, not a mistake so much as an unresolved seam the brief didn't
anticipate: **the §4 wire shape's `check_after_ticks` (a tick count) has no
matching field in `learning.predictions`, which grades against
`check_at_year` (an in-game year)**. There is no ticks-to-year conversion
available anywhere in this repo yet -- that needs the fort dossier's
current-year context, which doesn't exist (`docs/AGENT-ARCHITECTURE.md` §14
item 6). Rather than inventing a conversion or silently dropping the field,
`_validate_prediction` reuses the tick-count integer as the year integer
purely so the underlying validator's *type* and *falsifiability* checks
still run for real, with a comment and a README section both saying plainly
that this is a type-only stand-in, not a real ticks-to-year claim. Flagging
it here rather than treating it as quietly handled, since it's exactly the
kind of gap the brief's own "report anything this brief got wrong" line is
for.

Two smaller notes, not really "wrong," just choices made where the brief
left room: (1) the brief didn't specify a closed vocabulary for
precondition `state` values (`exists`/`unclaimed`/etc.) -- left as a
non-empty string rather than inventing an untested vocabulary, since
nothing in the brief's required test list needed one. (2) `id`/`ts`
auto-assignment uses a per-kind sequential counter (`proposal-0001`,
`pass-0001`, `ruling-0001`) rather than the `p-0142`-style short prefix in
§4's example XML, for readability; a caller (including the run #1 fixture)
can still supply its own `id` and it is preserved verbatim.
