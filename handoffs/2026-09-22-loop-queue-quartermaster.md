# Stream: queue execution, ask/answer, and the Quartermaster (agent loop MVP, items 4, 5, 7)

**Written** 2026-09-22. **Status:** dispatched. **User go-ahead:** given
2026-09-22 ("go put a sonnet on those"). Offline only: **no VM, no deploy, no
model call.** Sonnet executor, worktree-isolated.

## Why

`docs/AGENT-LOOP.md` is the design; read it in full. This stream gives the
queue what an unattended loop needs and makes the Quartermaster a real role:

- **Item 4.** Nothing records that an accepted proposal was carried out, and
  a prediction's window runs from when it was written. That is how
  `proposal-0001`'s window elapsed before anything could act. **Windows must
  start at execution.**
- **Item 7.** Advisors may ask the Consultant (register 2026-09-15); the
  Overseer may send a proposal to the Consultant for fact-checking before
  ruling (register 2026-09-17). One ask, one answer, no threads.
- **Item 5.** The Quartermaster is enabled for the MVP (user's call
  2026-09-22). Its closed proposal-type vocabulary: **`work_order`** (a
  manager order or a direct workshop job, standing repeat orders included),
  **`crop_plan`** (what a farm plot grows, per season), **`stock_target`** (a
  par level or cover-day target, `docs/PRODUCTION-MODEL.md` §10). No labor
  proposals: `set_labor` still races `autolabor`.

## First

`git merge --ff-only main` in your worktree (worktrees are cut from
`origin/main`; local `main` is ahead).

## Read first

`docs/AGENT-LOOP.md`; `docs/AGENT-ARCHITECTURE.md` §4 (records, the closed
vocabulary, predictions, the consultant exception, the fact-check); `dfqueue/`
(all of it, plus `dfqueue/README.md`); `dfmcp/queue_tools.py` and its tests;
`learning/live_signals.py`; `agents/quartermaster/` (`role.md`, `tools.yaml`),
`agents/architect/`, `agents/overseer/`, `agents/consultant/tools.yaml`;
`agents/CONFIDENCE-LEGEND.md`; `scripts/dfhack/TOOLS.yaml` for the real ids
of `orders.*`, `workjob.*`, farm, `stocks.*` tools.

## What to build

1. **Execution record** (`queue.executed`, Overseer only): references the
   ruling, the game tick at execution, and what was done (tool ids called and
   their outcome, success or failure; a failed execution is a valid record).
   **The grader measures `check_after_ticks` from the execution tick**; an
   accepted but never-executed proposal is never graded as a miss, it is
   reported as unexecuted. Keep existing records readable (migration or a
   compatible default, tested).
2. **Grading on demand**: whatever entry point the conductor service will call
   once per cycle to grade everything now due (a function, and a CLI if cheap).
   It must be safe to call repeatedly (idempotent).
3. **Ask / answer / fact-check.** `queue.ask` (architect, quartermaster,
   overseer): a question, optional proposal reference. A fact-check is an ask
   from the Overseer referencing a proposal; while one is open, that proposal
   cannot be ruled on. `queue.answer` (consultant only) answers one open ask.
   The Consultant needs a way to list open asks (extend `queue.pending` per
   role, or a new read; your call, justified). Answers are hypotheses: nothing
   in them overrides a graded prediction.
4. **Quartermaster.** The three proposal types above in `dfqueue/schema.py`'s
   per-role vocabulary; live prediction signals it will need (stock counts or
   cover days for a named item class, order completion) added to
   `learning/live_signals.py`, each readable through an existing read tool,
   following how the architect's signals were added; `agents/quartermaster/`
   made complete: `role.md` updated for being enabled, `tools.yaml` with its
   reads plus `queue.propose`/`pass`/`ask`, and a `model.yaml` (DeepSeek, as
   the other roles run live; look at theirs). **Do not flip `enabled` in
   `ROSTER.yaml`**: another stream owns that file; the orchestrator flips it at
   merge. Make sure `dfmcp/roles.py` validation would pass once it is flipped
   (a test that loads a roster with it enabled is ideal).
5. **Allowlists**: `queue.ask` for architect and overseer, `queue.executed`
   for overseer, `queue.answer` for consultant. The Overseer must hold the
   write tools needed to carry out Quartermaster proposals (`orders.create`,
   `workjob.*`, farm crop setting); check which it already has and report.

## Touched surfaces (yours only)

`dfqueue/` (all), `dfmcp/queue_tools.py`, `dfmcp/tests/test_queue_tools.py`,
`learning/live_signals.py`, `learning/tests/`, `agents/quartermaster/`,
`agents/architect/tools.yaml`, `agents/architect/role.md`,
`agents/overseer/tools.yaml`, `agents/overseer/role.md`, this doc, its
`handoffs/INDEX.md` row.

**Not yours:** `agents/ROSTER.yaml`, `agents/consultant/tools.yaml` and
`agents/consultant/role.md` (report the lines to add for answering asks), `dfmcp/roles.py`, `dfmcp/server.py`,
`dfmcp/registry.py`, `scripts/dfhack/`, `dfmcp/README.md` (report lines).

## Hard lines

- No VM, no SSH, no deploy, no model call. No push.
- Do not write `Working.md`, `decisions/` or `memory/`.
- No em dashes in prose.
- **Commit after each milestone** and extend the Result section as you go.

## Done when

Both suites pass (ambient `python -m pytest`, baseline 891 passed / 3
skipped; `dfmcp/tests` in `.venv-dfmcp`, baseline 537), counts reported, and
the Result section lists what was built, how it was verified, the lines owed
to files you do not own, and anything in the design you found wrong.

## Result

**Status: done, offline, no VM/SSH/deploy/model call/push.** Branch
`worktree-agent-a8b083089d2956a1d`, commits `c359a79`, `cea079e`, `714af73`,
`7dd56cc`, `ac705e6`, `88187f3` (each a milestone; see their own messages
for what each contains). Both suites pass: ambient `python -m pytest`
**963 passed, 3 skipped** (baseline 891/3); `dfmcp/tests` in `.venv-dfmcp`
**547 passed** (baseline 537). The `.venv-dfmcp` this worktree needed did
not exist inside it (worktrees don't carry a sibling venv); ran it via the
main checkout's `.venv-dfmcp` interpreter with cwd in this worktree
(`/c/website-projects/df-automation/.venv-dfmcp/Scripts/python.exe -m
pytest dfmcp/tests`), which correctly imports this worktree's own
`dfmcp`/`dfqueue` packages, not the main checkout's.

### What was built

**Item 1, execution record (`dfqueue/schema.py`, `dfqueue/store.py`).** A
new `executed` record kind (`ruling_id`, `actions` — one `{tool, outcome,
detail?}` per call, `outcome` in `success`/`failure` — and free-text
`notes`), Overseer-only (reuses the `ruling`/sole-writer restriction). A
proposal's prediction now starts `AWAITING_EXECUTION` (a new, `dfqueue`-
local status, never confused with `learning.predictions.schema.PENDING`)
and is armed — flipped to `PENDING`, `due_game_tick` recomputed from the
**executing record's own `cycle`**, never the proposal's write-time tick —
only by the *first* `executed` record referencing its accepted ruling. A
second execution attempt for the same ruling (a retry) is still logged but
does not re-arm or move the window a second time. `store.
unexecuted_accepted_proposals()` lists every accepted proposal with no
execution yet, for reporting rather than mis-grading. `dfqueue/grade.py`
gained `run_grading_cycle(db, call_tool)` (item 2, "grading on demand"):
reads the current tick, grades everything due, and returns the unexecuted
list alongside it, idempotent by construction; `python -m dfqueue.grade
--db --replay` is a thin, fully offline-testable CLI wired to a captured-
response JSON file rather than a live DFHack process (a real conductor
wires `call_tool` to `dfmcp` instead — that plumbing is conductor work,
`docs/AGENT-LOOP.md` item 3, not built, no VM this stream).

**Schema migration.** `dfqueue.store.SCHEMA_VERSION` 1→2: `predictions`
gains `check_after_ticks` (needed to recompute `due_game_tick` at
execution time). `_ensure_schema` now migrates a v1 database forward
(`ALTER TABLE ... ADD COLUMN` plus a backfill: `check_after_ticks =
due_game_tick - registered_game_tick`) instead of refusing it outright. A
migrated database's **pre-existing** rows keep their original, write-time-
computed `due_game_tick` and status verbatim — a compatible default, not a
reinterpretation: only proposals appended by the new code get the new
awaiting-execution behaviour. Proven against a hand-built v1-shaped SQLite
file (`dfqueue/tests/test_store.py::test_a_v1_database_migrates_and_keeps_
its_old_pending_row_readable` and its sibling for a freshly-appended
proposal on the same migrated database) — no real `dfqueue/*.sqlite3` is
committed to the repo (gitignored) or reachable offline, so this is the
closest honest proof available without a VM.

**Item 3, ask/answer/fact-check.** Two new record kinds, `ask` (`question`,
optional `proposal_id`; writable by `architect`/`quartermaster`/`overseer`)
and `answer` (`ask_id`, `answer`; writable by `consultant` only, one answer
per ask, enforced at write time). An `ask` from the Overseer that names a
`proposal_id` **is** a fact-check: `store.append()` refuses a `ruling` on
that proposal while the fact-check has no `answer` yet, and a plain
lookup ask (any other role, or no `proposal_id`) never blocks anything —
both proven directly in `dfqueue/tests/test_store.py` and end-to-end
through the real MCP tool-call path in `dfmcp/tests/test_queue_tools.py`.
For the Consultant's own read: **`queue.pending` is now role-dependent** —
for `consultant` (which never proposes) it returns `store.open_asks()`
instead of `store.pending_proposals()`, structured under a new `ask_ids`
key rather than repurposing `proposal_ids` for a different meaning. This
was the "extend `queue.pending` per role, or a new read" choice the brief
left to my judgement: one tool id, kept coherent per caller, rather than a
second read tool id that every role's allowlist would then need a fresh
grant decision about.

**Item 4, Quartermaster.** `dfqueue.schema.TYPE_VOCAB_BY_ROLE["quartermaster"]`
is now `(work_order, crop_plan, stock_target)`, drafted ahead of the
`ROSTER.yaml` enable flip exactly like every other role's vocabulary here.
Two new live signals in `learning/live_signals.py`: `order."ID".exists`
(boolean, via `orders.list`, for a `work_order` predicting an order
completes — DF removes a completed/cancelled order from its own list) and
`stocks.availability."TYPE".available_units` (integer, via
`stocks.availability`, generalising the four fixed `stocks.*.units`
signals to any item class that tool already knows, for a `stock_target`).
**Deliberately not added: a cover-days signal** — no existing read tool
computes a consumption rate, and this module's own rule is that every
signal reads an *existing* tool; flagged as a real gap, not built around.
`agents/quartermaster/` made complete: `role.md` rewritten for being
enabled (three proposal types, both `work_order` routes, refusals, a
worked XML example), `tools.yaml` extended with the reads those three
types need (`orders.list`, `workjob.list`, `farm.find`/`list`,
`stocks.availability`/`food-drink`/`seeds`) plus
`queue.propose`/`pass`/`ask`, and a new `model.yaml` (`deepseek/
deepseek-v4-flash`, set as the direct default per the handoff's own
instruction rather than the Claude-default-plus-live-deviation-note shape
the other three roles' `model.yaml` files use). **`agents/ROSTER.yaml`
was not touched** — `dfmcp/tests/test_quartermaster_roster_enabled.py`
(new) copies the real, committed `agents/overseer/` and
`agents/quartermaster/` directories into a synthetic roster with
`quartermaster: enabled: true` and proves `dfmcp.roles.load_roster`
accepts them cleanly, so flipping the real flag at merge is a config
change, not a fresh validation risk.

**Item 5, allowlists.** `queue.ask` added to `agents/architect/tools.yaml`
and `agents/overseer/tools.yaml` (`write:`, both `status: exists`);
`queue.executed` added to `agents/overseer/tools.yaml` (`write:`,
`sole_writer_only=True`, same mechanism `queue.rule` already uses). **The
Overseer already held every write tool needed to carry out a Quartermaster
proposal**, unchanged by this stream: `orders.create`/`orders.cancel`
(the manager-order half of `work_order`), `workjob.queue` (the direct-
workshop-job half), `farm.set-crop` (`crop_plan`) — all `status: exists`
in `agents/overseer/tools.yaml`'s `write:` section already. `stock_target`
needs no execution-side write tool at all: it sets a threshold, which
`docs/AGENT-ARCHITECTURE.md`'s own "Strategy" layer description frames as
target-setting distinct from the priced action that responds to it, and
nothing in this handoff or `docs/PRODUCTION-MODEL.md` §10 asks for a
doctrine-write tool yet.

### How it was verified

Every behaviour above has a direct test, not just an indirect one:
`dfqueue/tests/test_store.py` (arming on first execution, no re-arming on
a second, refusals for a nonexistent/rejected ruling, the fact-check gate
both ways, ask/answer round-trip and the "one answer" refusal, the v1
migration); `dfqueue/tests/test_schema.py` (every new kind's required
fields, role restrictions, coordinate scanning, the Quartermaster type
vocabulary isolated from the disabled-role check via a monkeypatched
`schema.enabled_roles`); `dfqueue/tests/test_run1_fixture.py` (rewritten:
the pre-existing grading tests now accept-and-execute before grading, since
they exercised exactly the write-time-window behaviour this stream
deliberately changes); `dfqueue/tests/test_grade_cycle.py` (new: the
grading-cycle function and its CLI, including idempotency);
`learning/tests/test_live_signals.py` (both new signals, parse and read,
against fixture JSON shaped from the real `.lua` headers, matching this
file's own established discipline of never inventing a fake shape);
`dfmcp/tests/test_queue_tools.py` (all three new tools through the real
`queue_tools.call()` path, including the fact-check blocking a real
`queue.rule` call and the Consultant's `queue.pending` branch);
`dfmcp/tests/test_quartermaster_roster_enabled.py` (the real on-disk role
files loading cleanly once enabled).

### Existing records stay readable

Two senses. (1) **Schema-level**: the v1→v2 SQLite migration above is
additive and backward-compatible — a pre-existing database opens, loads,
and grades its already-pending rows exactly as before; nothing already
written changes meaning. (2) **Vocabulary-level**: no existing record kind
(`proposal`/`pass`/`ruling`) had a field removed, renamed or
reinterpreted; the three new kinds are pure additions to `KINDS`, and
`render.to_xml`/`render.public_view` were extended, never rewritten, for
them (proven for `public_view` the same way the original allowlist test
does: adding a field to an `executed` record and checking it does not
leak).

### Lines owed to files this stream does not own

**`agents/consultant/tools.yaml`** — add a `write:` section (none exists
today) with:
```yaml
write:
  - id: "queue.answer"
    status: exists
    note: >-
      Added handoffs/2026-09-22-loop-queue-quartermaster.md (docs/
      AGENT-LOOP.md item 7). Answers one open ask; one answer per ask,
      enforced at write time (dfqueue.store). Answers are hypotheses,
      never overriding a graded prediction.
```
and add to `read:`:
```yaml
  - id: "queue.pending"
    status: exists
    note: >-
      Added handoffs/2026-09-22-loop-queue-quartermaster.md. For this role
      specifically, returns open asks (no answer yet), not pending
      proposals -- dfmcp/queue_tools.py's _pending branches on role.
```
The file's own top-of-file `write_authority: none` line should be revised
the way `agents/architect/tools.yaml`'s own comment already reads
("enforced: this role has no FORT-mutating action tool at all... ARE
writes, but to dfqueue's own ledger, never to the fort").

**`agents/consultant/role.md`** — a short new section, e.g. after "Does
NOT own":
```markdown
## Answering an ask

Any advisor may ask you a lookup question (`queue.ask`); the Overseer may
also route a specific proposal to you for fact-checking before ruling on
it. `queue.pending` lists what is open for you -- open asks, not
proposals, since you never propose. Answer with `queue.answer`, naming
the `ask_id`. One answer per ask, no threads. Your answer is a
hypothesis, never a decision: it never overrides a graded prediction, and
for a fact-check specifically, it is what lets the Overseer's
`queue.rule` on that proposal go through at all (refused while the
fact-check has no answer yet).
```

**`dfmcp/README.md`** — the native-tool count and the "Four MCP tools"
line (currently: `queue.propose`/`pass`/`rule`/`pending`) both need
updating to seven, naming `queue.ask`/`queue.answer`/`queue.executed` and
summarising what each does (execution starts the grading window at the
execution tick; ask/answer is the one-ask-one-answer Consultant channel
including the Overseer's fact-check routing; `queue.pending` is now
role-dependent). Exact drafted text is in this stream's final report to
the orchestrator, not duplicated here to avoid two slightly-diverging
copies.

**`agents/ROSTER.yaml`** — one line, `quartermaster.enabled: true`
(orchestrator's job at merge, per this handoff's own instruction; not
touched here).

### A necessary touch of a file also listed under a sibling stream

`dfmcp/tests/test_roles.py` is listed as a touched surface of
**both** this stream and `2026-09-22-loop-clock-conductor-role.md`. I
edited one pinned assertion in it
(`test_only_the_sole_writer_has_fort_mutating_write_entries`, which
asserted the exact set of `architect.write` tool ids) because granting
`queue.ask` to the architect — squarely this stream's own item 5 — made
that pinned assertion fail against the real, on-disk roster; the fix is
one line (add `"queue.ask"` to the expected set) and touches nothing the
clock/conductor stream would plausibly also change on that same line. I
did not touch `dfmcp/roles.py` itself (not this stream's file) or any
other part of that test file. Flagging this explicitly since the two
streams' surface lists overlap on this one file — the orchestrator should
expect a possible (small, mechanical) merge conflict here when both
branches land, not a silent collision.

### Anything in the design I think is wrong or worth a second look

- **A failed execution still starts the grading window, and I think that
  is the right call but it is a real judgement, not dictated by the
  design doc.** `docs/AGENT-LOOP.md` item 4 says "a failed execution is a
  valid record" but does not say whether the window should still start on
  one. I chose: any `executed` record, regardless of whether every
  individual `action` inside it succeeded, arms the window — because the
  alternative (only a fully-successful execution arms it) would let a
  proposal with a partially-failed execution sit forever `AWAITING_
  EXECUTION`, never graded, never reported as unexecuted either (since it
  *was* executed, just not cleanly) — a silent third bucket the "reported
  as unexecuted" language does not anticipate. The cost of my choice: the
  grader cannot currently distinguish "the proposal was wrong" from "the
  execution failed" when a prediction grades false after a failed action.
  That distinction matters for calibration (§10) and is not solvable
  inside this stream's scope (it would need the grader to read `executed`
  records, not just `predictions` rows) — worth a design note before the
  Quartermaster's hit rate is trusted for anything.
- **One execution record arms the window for good; a retry after failure
  cannot re-arm it.** This protects against a proposal's window silently
  restarting or shrinking on a later retry, but it also means a genuinely
  slow, multi-attempt execution (queue a manager order, discover it never
  runs, switch to the direct-workshop-job route, as this fort's own
  history shows happening) gets graded against the FIRST attempt's tick,
  which may be well before the proposal's real effect actually landed.
  Given this fort's own documented history (manager orders queued and
  never converting into jobs), I think this will bite the Quartermaster's
  own `work_order` proposals specifically, soon. Not fixed here since the
  design doc gives no guidance on retries and any fix (e.g. "the LAST
  execution arms it" vs "the FIRST") is a real tradeoff, not an omission
  to quietly patch over.
- **`order."ID".exists` predicts on a documented-but-unwitnessed engine
  behaviour.** I built it on `df-overseer-orders.lua`'s own header
  comment (a completed/cancelled order is removed from
  `world.manager_orders.all` via `erase(idx)`), which this project has
  never independently watched happen live end-to-end (no Manager has
  successfully processed an order yet, per `Working.md`). A `work_order`
  proposal predicting `op="not_exists"` is honest about what it is
  checking (the signal genuinely reads the live order list every time),
  but the FIRST time this actually grades true or false live is also the
  first time this specific engine behaviour gets checked for real. Said
  plainly rather than left implicit.
- **`stock_target`'s "no write tool needed" finding is a scope
  observation, not a design gap I am flagging as wrong** — but it does
  mean a `stock_target` proposal, once accepted and "executed" (there is
  nothing to actually call), only ever changes what future proposals are
  measured against, never the fort directly. That is consistent with
  `docs/AGENT-ARCHITECTURE.md`'s own strategy-layer description, but it is
  worth the Overseer's `role.md` (which I did extend) being explicit that
  `queue.executed` on a `stock_target` proposal can legitimately have an
  empty-of-real-effect `actions` list (e.g. a single `{"tool":
  "queue.executed", "outcome": "success"}` bookkeeping entry, since
  `actions` requires at least one item) — I did not add a special case
  for this in the schema since the field's own minimum-one-item
  requirement already accepts a bookkeeping-only entry without any code
  change, but a real Overseer run will need to know this is intended, not
  a workaround.
