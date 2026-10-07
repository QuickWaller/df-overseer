# Handoff: wake the Quartermaster when a planned building waits on an item nobody makes

Date: 2026-10-07. **Executor, Sonnet, worktree. Offline; no deploys.**
First: `git merge --ff-only main`. **Dispatch after the P0 bedroom alert
merges** (both touch `conductor/policy.yaml`).

## Why

`evals/live/2026-10-07-stuck-bed/README.md`: the fort's only Bed is a
buildingplan-planned building waiting 38 game days for a BED item that never
existed. Nobody ever queued `ConstructBed`, although a Carpenter's Workshop,
24 wood and 2 carpenters were there. The Overseer deferred four bedroom
proposals meanwhile. User's call 2026-10-07: add a general signal, not a bed
fix.

## Scope

A conductor watch modelled on `conductor/ore_watch.py` (and
`order_watch.py`/stuck-job watch for the polling pattern):

- **Signal:** a planned building (buildingplan) needs item kind X, X has 0
  available (free) in the fort, and no active job or manager order produces
  X. Wake the **Quartermaster** with reason `unsupplied_building`, one line
  per item kind: the kind, how many buildings wait, the longest wait, and
  the producing job(s) and workshop kind the game data names (for BED:
  ConstructBed at a Carpenter's Workshop).
- **Generalisable:** item kind to producing job/workshop comes from game data
  (the job/reaction product tables `workjob.list-jobs` already reads), never
  a per-item table in code. If a needed read does not exist (for example a
  list of planned buildings with their unmet item filters), add it to the
  right Lua tool as a read-only command with TOOLS.yaml data, coordinate-free.
- Edge-triggered like the lane alerts (wake once when it appears, again
  only after it clears and re-appears). The operator hold gates no wake
  today (research/2026-10-07-wake-audit.md finding 5), so do not suppress
  it under a hold; follow the audit's backoff advice (stalled after 3).
- Quartermaster charter: one line naming the wake and the expected
  response. User's call 2026-10-07: the preferred response is a **standing
  manager order with an item condition that keeps a small buffer** (for
  example, make beds while fewer than 2 are in stock; `orders.create`
  ITEM_CONDITIONS, repeat), so the game keeps supply itself; a one-off job
  only when a standing order cannot express it. The wake line should say
  when a standing order for X exists but is inactive or unvalidated (the
  stuck-bed read found all five live orders inactive), since that is a
  different fix.
- Add a gotcha/doctrine-style note only if there is an existing home for
  "BED 0 plus a suspended Bed means missing supply"; do not invent a store.
- Tests: fires for a planned building with no supply; silent when a job or
  order produces the item, or when the item is available; edge behaviour;
  an unreadable read drops the line rather than waking.

## Rules

Touched surfaces: new `conductor/<name>_watch.py`, `conductor/cycle.py`
(wiring), `conductor/policy.yaml`/`policy.py` (if it needs policy),
`scripts/dfhack/` (one read command if needed) and `TOOLS.yaml`,
`agents/conductor/tools.yaml` (if a new read), `agents/quartermaster/role.md`
(one line), tool-count docs/tests, tests, this handoff. Public repo: no
hostnames, IPs or tokens. No em dashes. No attribution lines. Commit after
each milestone. Do not write Working.md, DECISIONS.md, memory or INDEX.md.
Full ambient `python -m pytest` (lupa on PYTHONPATH) and `dfmcp/tests` in
`.venv-dfmcp` green.

## Result

Done offline. Branch `worktree-agent-af6b39cf3eed2ca3b`.

- **New read** `workjob.unsupplied` (`scripts/dfhack/df-overseer-workjob.lua`,
  `unsupplied_buildings`, TOOLS.yaml entry, read-only, coordinate-free): per item
  kind a buildingplan-planned building still needs (concrete `item_type` in its
  `job_items`), buildings and units waiting, `available` (stocks'
  `get_availability`), `producers` (job, reaction, workshop kind from `getJobs`
  over BUILT workshops and furnaces), `jobs_queued_now`. Added to
  `agents/conductor/tools.yaml` (conductor 35 to 36; STATE.md and two count tests).
- **Watch** `conductor/unsupplied_watch.py`: joins `orders.list` here (an order
  counts as supply only if active and validated; an inactive or unvalidated one is
  named in the line: "order #7 for it is inactive"). Unreadable stock or order
  list drops the line and keeps state. `lanes.apply_unsupplied_edges`: wake once
  on first sight, then base 6000 ticks doubling to a cap of 100800, stalled after 3
  wakes, cleared when supplied. Not gated by the operator hold (tested).
  Own `unsupplied_building:` block at the end of `policy.yaml` plus a
  `wake_reasons` entry and `lane_triggers.quartermaster.unsupplied: true`;
  `policy.py` `UnsuppliedPolicy`. Wired in `cycle.py` (`_unsupplied_watch`).
- **Charter**: one paragraph in `agents/quartermaster/role.md` (standing order with
  an ITEM_CONDITIONS buffer preferred; inactive-order case is a different fix).
- No gotcha store entry: no existing home for it, none invented.
- **Tests**: `conductor/tests/test_unsupplied_watch.py` (24),
  `tests/test_workjob_unsupplied_lua_logic.py` (13, real Lua over a fake world),
  two manifest tests updated. Ambient `python -m pytest` (lupa installed): 3487
  passed, 3 skipped. `dfmcp/tests` in `.venv-dfmcp`: 970 passed. Merged
  origin/main (P1b's policy.yaml touch merged clean) before the final run.
- **Unverified live** (all in the TOOLS.yaml note): `plugins.buildingplan.
  isPlannedBuilding` and `job.job_items.elements` field names; the
  job-name-to-product rule (verb stripped, plus `JOB_PRODUCT_ALIASES` for
  ConstructThrone to CHAIR and ConstructChest to BOX), reactions read their own
  products. A job whose product cannot be named is simply not matched, so the line
  reads "no built workshop offers a job making it".
- **Deploy targets (owed, not done)**: `df-overseer-workjob.lua` to VM 103 and the
  MCP server restarted (new tool, conductor allowlist), then the conductor on VM
  106. First live check: run `workjob.unsupplied` read-only on the paused fort and
  expect one BED row with ConstructBed at Carpenters.
- Known gap: a planned building held for a *material* (wildcard filter) is not
  watched; only concrete item kinds.
