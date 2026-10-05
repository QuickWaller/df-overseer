# Handoff: a briefing that saves the agents their first ten lookups

Date: 2026-10-05. **Executor, Sonnet, worktree. Read-only on hosts; offline
build; no deploys.**

## Why (user agreed, 2026-10-05)

The Overseer's 2026-10-05 turn (run-0004) took 11 minutes. Its captured
thinking (`evals/live/2026-10-05-pause-safety/runs-public.json`) restates the
three proposals about four times and opens with a round of lookups (stock,
orders, a gotcha, landmarks, the Still's jobs, stuck jobs, labours) for facts
the conductor could have handed it. The briefing (`conductor/briefing.py`)
should carry what each role routinely looks up first, so turns start from the
facts instead of rediscovering them.

## Tasks, in order (commit after each)

1. **Measure first.** From the four runs in `runs-public.json` and VM 103's
   `dfmcp-server` journal for 2026-10-05 05:20 to 05:52 UTC (read-only:
   `scripts/vm-ssh.sh df 'sudo -n journalctl -u dfmcp-server --since ... --until ... --no-pager'`,
   `DF_ENV_FILE=c:/website-projects/df-automation/.env`), list per role
   which read tools were called, in what order, how often the same read
   repeated, and which of those results the briefing already carries. Write
   the table into this file's Result section. Do not copy addresses or
   hostnames from the journal into the repo.
2. **Plan.** Which facts go into each role's briefing (bounded, short lines,
   same caps style as the existing `stuck_jobs` block), where each comes from
   (the conductor's own MCP reads, as it already polls `stuckjobs.find` and
   `orders.list`), and the token cost. Prefer facts every role needs (drink,
   food, alive, worst hunger/thirst, stalled orders, stuck jobs, pending
   proposals with one line each) plus a small per-role extra, held as data
   in `conductor/policy.yaml` if it varies by role. Generic, never a rendered
   map (`docs/PURPOSE.md` commitment 1).
3. **Build** in `conductor/briefing.py` and its wiring; reads must be total
   (a failed read drops that line and the cycle carries on).
4. **Tests**, and the conductor's tool allowlist (`agents/conductor/tools.yaml`)
   if it needs a new read; update every hardcoded conductor tool count.
5. Result: what was built, the expected saving per role (lookups the
   briefing now answers), deploy targets.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early and after
  every milestone.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md`.
- Touched surfaces: `conductor/briefing.py`, `conductor/cycle.py` (wiring
  only), `conductor/policy.yaml`/`policy.py`, `agents/conductor/tools.yaml`,
  tests, docs that state the conductor's tool count, this handoff. Not the
  role charters, not `dfmcp/`, `dfqueue/`, `web/`, not `runner.py`'s
  thinking code, not `conductor/hold.py` or `pause_watch.py`.
- No armok powers. Public repo: no hostnames, IPs or tokens. No em dashes. No
  attribution lines in commits.
- Full ambient `python -m pytest` and `dfmcp/tests` (in `.venv-dfmcp`) green.

## Result

### 1. Measurement (journal 05:20 to 05:52 UTC, 133 tool calls, plus the four runs)

Four role runs in the window: run-0001 quartermaster (stalled_order, 483 s),
run-0002 architect (prediction_graded, 342 s), run-0003 quartermaster
(prediction_graded, 195 s), run-0004 overseer (queue_pending, 645 s). No
consultant run. Run durations are from `runs-public.json`; calls are from the
journal's `tools/call` lines, split by role and gap. (Captured thinking is
truncated to about 12k characters per run, so its opening lookups are the
reliable part.) The conductor's own 33 calls are the cycle's Tier 0 reads.

What the briefing carried then: vitals (alive, dead, worst hunger/thirst,
warning count), the diff, queue ids, the stuck-job lines past threshold, the
wake reason. It did not carry stocks, orders, or any per-item count.

Read calls per run (n = how often; "same" = repeats of an identical call):

| read | run-0001 QM | run-0003 QM | run-0002 arch | run-0004 over | in briefing? |
|---|---|---|---|---|---|
| stocks.food-drink | 1 | 1 | 1 | 1 | no (4 of 4 runs) |
| orders.list | 1 | 1 | 1 | 1 | no (conductor reads it, never passes it) |
| stuckjobs.find | 1 | 1 | 1 | 1 | partly (lines only past threshold) |
| overview.get | 1 | 1 | 1 | 0 | no (fort summary) |
| stocks.availability | 3 (BOULDER, BARREL, PLANT) | 3 (BARREL, DRINK, PLANT) | 0 | 2 (WOOD, BED) | no (7 calls; BARREL and PLANT asked in both QM runs) |
| stocks.seeds | 1 | 1 | 0 | 0 | no |
| gotchas.get | 6 | 6 | 2 | 4 | no (see below) |
| orders.check-duplicate | 3 | 1 (error) | 0 | 0 | no (a per-order check, not a fact) |
| workjob.list-jobs | 3 (2 errors; Still, same as overseer) | 0 | 0 | 1 (Still) | no |
| series.latest / series.get | 1 / 1 | 2 / 2 (two replies of 41k and 42k chars) | 0 | 0 | no |
| landmarks.list | 0 | 0 | 1 | 1 | no (names, not a figure) |
| labor.enabled-counts, zone.list, queue.project_status | 0 | 0 | zone.list, project_status 1 each | 1 each | no |
| queue.pending | 0 | 0 | 0 | 1 | ids yes, text no |

Repeats worth noting: `gotchas.get` with `{"general": true}` (a 115 char
reply, effectively empty) was called 4 times across 4 runs; gotcha-0002 (the
brew order that sits validated but inactive, 1781 chars) was fetched 3 times
across the three runs that touched the Still; the quartermaster asked for the
same BARREL and PLANT availability in both its runs; `stocks.food-drink`
was the first or second call of every run, identical each time (582 chars).
`workjob.list-jobs` for the Still (5316 chars) was read by both the
quartermaster and the overseer. Order of play was always: orders and stuck
jobs first, then gotchas, then stocks, which matches the handoff's opening
round of lookups.

Not coverable by a briefing: `gotchas.get` by tool/id (what is relevant
depends on what the model decides to do), `orders.check-duplicate`,
`series.*` history, `workjob.list-jobs` (one workshop's jobs, 5 KB), and
`blueprint.*` / `queue.*` working calls.

### 2. Plan

One new briefing key, `facts`, built once per cycle by the conductor (so the
reads are shared by every woken role) and passed to `build_briefing`:

- Every role: `stocks` (drink units and per citizen, prepared meals units,
  raw edibles units, unreachable units; from `stocks.food-drink`, fort-owned
  only), `orders` (count of orders and up to 5 one-line entries for those not
  progressing: `#2 BrewDrinkFromPlant validated, not active, 1 of 1 left`;
  from the `orders.list` read the cycle already makes, no new call),
  `manager_appointed`.
- Per-role extras as data in `conductor/policy.yaml` under `briefing_extras`:
  `availability: [ITEM_TYPE, ...]` (each read by `stocks.availability`, one
  line `BARREL: 2 free of 6, 1 in jobs`) and `seeds: true`. Quartermaster:
  availability BARREL, PLANT, DRINK, BOULDER and seeds; overseer: BED, WOOD;
  architect and consultant: none (the architect did none of these calls).
  The union of types across woken roles is read once per cycle.
- Reads are total: a failed read (an undeployed allowlist entry, a tool
  error, odd shape) logs and drops that line; no key is better than a wrong
  key. Every list capped (`MAX_ORDER_LINES` 5, `MAX_AVAILABILITY_LINES` 6,
  seeds top 3 plants). Tier 0 and O(1) in fort size; no coordinates, no map.
- Conductor allowlist gains `stocks.food-drink`, `stocks.seeds` and
  `stocks.availability` (all read-only, already live on VM 103); conductor
  count 21 to 24.
- Token cost estimate: about 150 to 300 tokens per briefing (a dozen short
  lines), against about 5 to 12 lookups saved per run, each costing a tool
  round trip of 5 to 30 s of wall clock in the measured runs.
- Not done, and why: one-line pending-proposal summaries. `queue.overview`
  returns only ids; the text is in `queue.pending`'s XML, which the
  conductor's client does not surface, and changing `queue.overview` is
  `dfmcp/`, outside this handoff's surfaces. Also no gotcha digest (what is
  relevant depends on the model's intent).

### 3. Built

- `conductor/briefing.py`: `build_briefing(..., facts=)` adds a `facts` key
  when non-empty. New pure functions `stock_facts`, `order_facts`,
  `availability_line`, `seed_facts`, `build_facts`, caps `MAX_ORDER_LINES` 5,
  `MAX_AVAILABILITY_LINES` 6, `MAX_SEED_PLANTS` 3. Each returns nothing on a
  wrong shape, so a bad read drops its line only. A 5000-order, 100-type,
  500-plant input stays under 2.5 KB (tested).
- `conductor/cycle.py` (wiring only): `_read_fact_sources` takes
  `stocks.food-drink` once, `stocks.availability` once per distinct item type
  across the roles that cycle, `stocks.seeds` once if any role wants it, all
  total (log and continue); `_facts_for` builds each role's block. Read lazily
  at the first role that runs, so a quiet cycle makes no extra reads. The
  orders line reuses the `orders.list` read the cycle already makes. The
  tripwire-wake Overseer briefing gets facts too; the paused-cycle
  (`unexplained_pause`) Overseer briefing does not (touching it is not in the
  surfaces, and the fort is frozen there).
- `conductor/policy.py` / `policy.yaml`: `briefing_extras` per role as data
  (quartermaster: BARREL, PLANT, DRINK, BOULDER, seeds; overseer: BED, WOOD).
  Adding an item type for a role is one line of YAML.
- `agents/conductor/tools.yaml`: three read grants (`stocks.food-drink`,
  `stocks.availability`, `stocks.seeds`); conductor count 21 to 24. Hardcoded
  count updated in `dfmcp/tests/test_gotchas_tools.py`.
- Tests: `conductor/tests/test_briefing_facts.py` (new, 10), two in
  `test_policy.py`, two in `test_cycle.py` (shared single read per cycle,
  per-role extras, failed reads drop lines and never fail the cycle).

### 4. Verification

- `python -m pytest` (ambient, no `lupa`, so the Lua-logic files skip as the
  3 skipped): 2763 passed, 3 skipped, 0 failed. The one known date-sensitive
  failure did not occur today.
- `dfmcp/tests` in the main checkout's `.venv-dfmcp`: 799 passed.
- Not run live (no deploy). The result shapes the parsers expect were taken
  from the Lua sources (`get_food_drink`, `count_availability`, `get_seeds`,
  `describe_order`), not from a live reply: `units`, `unreachable_units`,
  `total_units`, `available_units`, `in_job_units`, `by_plant_units`. First
  live cycle after deploy should confirm each line appears; a missing line
  means a shape mismatch, and the cycle still carries on.

### 5. Expected lookups saved

Calls in the four measured runs that the briefing now answers (of 100 role
calls in the window): run-0001 quartermaster 6 (food-drink, orders.list,
BARREL, PLANT, BOULDER availability, seeds), run-0003 quartermaster 6
(food-drink, orders.list, BARREL, DRINK, PLANT, seeds), architect 2
(food-drink, orders.list), overseer 4 (food-drink, orders.list, WOOD, BED),
consultant 0 (made none, it just gets the shared facts). Total 18 of 100,
about one in five, and they were all in the opening round. `stuckjobs.find`
(4 more calls) is only partly answered, since the briefing lists a stuck job
only once past its threshold; left alone. Not answered: gotchas (12 of the
QM's 44 calls, 4 the `general` call that returns almost nothing), the
`series.*` history reads (two of 41 KB each), per-order duplicate checks,
Still job lists, landmarks. A real saving also needs the roles' charters to
say "the briefing's `facts` already holds stocks and orders, do not re-read
them"; charters are outside this handoff.

Token cost: roughly 150 to 300 tokens per briefing, against 6 saved tool
round trips on a quartermaster run.

### 6. Deploy targets and owed items (for the orchestrator)

- `vm106-conductor`: `conductor/` (briefing.py, cycle.py, policy.py,
  policy.yaml). Conductor is disabled and run by hand, so no service restart.
- `vm103-dfmcp`: `agents/conductor/tools.yaml` (server-side allowlist; the
  server loads it at start, so restart `dfmcp-server`). Deploy this before
  the conductor change goes live, or the three stock reads are refused (they
  are caught and logged, nothing breaks, the facts just lack stocks).
- `vm106-agents`: its copy of `agents/` (no restart).
- `docs/STATE.md` still says conductor 21: it is generated from the live
  probe (`scripts/drift_check.py --write-state`); regenerate after deploy,
  expect 24. Not hand-edited here.
- Owed, outside these surfaces: one-line pending-proposal summaries (needs
  `queue.overview` to return them, `dfmcp/`); a charter line telling roles to
  trust `facts`; the paused-cycle Overseer briefing; a gotcha digest.
