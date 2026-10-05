# Handoff: a stuck-job watch the conductor can actually fire

Date: 2026-10-05. **Executor, Sonnet, worktree. Offline build; read-only on
hosts; no unpause, no deploys.**

## Why

The 2026-10-05 diagnosis (`handoffs/2026-10-05-why-jobs-sit-unclaimed.md`,
`evals/live/2026-10-05-stuck-jobs-diagnosis/`) found a Bed, two digs, a brew
and a Wall stuck for days with nothing able to notice:

- `stuck_job` in `conductor/policy.yaml` can never fire: `conductor/cycle.py`
  maps a `job_stalled` diff event to it, and nothing emits that event
  (`diff.lua` emits JOB_COMPLETED, UNIT_DEATH, REPORT, announcement_slow,
  UNIT_ATTACK only).
- The briefing (`conductor/briefing.py`) says it carries stuck jobs and does
  not.
- The Quartermaster, the only role `stuck_job` wakes, has no
  `stuckjobs.find` (Architect and Overseer do).

Stalled manager orders had the same "no event ever fires" shape and were
solved by polling: `conductor/order_watch.py`. Copy that pattern.

## Tasks, in order (commit after each)

1. **Plan, written here.** Read `conductor/order_watch.py`, its wiring in
   `cycle.py`, `conductor/briefing.py`, `scripts/dfhack/` stuckjobs tool output
   shape, and the new `conductor/pause_watch.py` (merged today; keep its
   early-return behaviour intact). Decide: what counts as stuck (unclaimed or
   suspended past a threshold in ticks, in `policy.yaml` as data), renotify
   cadence, how a job is keyed across cycles, and which role wakes (the
   Quartermaster for production jobs is the precedent; say if a dig or
   construction should wake someone else, and why).
2. **Build `conductor/job_watch.py`**: polls `stuckjobs.find` each cycle
   (no new game-side read unless the tool lacks a field you need; if so, say
   so and stop at the plan for that part), diffs against saved state, emits
   `stuck_job` wakes with a short detail line ("Bed construction suspended
   for 3 game days"). Remove or repoint the dead `job_stalled` mapping.
3. **Briefing digest**: a capped Tier 0 count and up to N short stuck-job
   lines in `build_briefing`, bounded like its other lists.
4. **Allowlist**: `stuckjobs.find` on `agents/quartermaster/tools.yaml`;
   update every hardcoded per-role tool count the tests and docs carry
   (grep for the Quartermaster's current 25).
5. **Wake title**: if you add a wake reason, give it a plain-English title in
   `web/stream/site-text.yaml` `wake_reasons` (that file only, nothing else
   in `web/`).

## Rules

- First step: `git merge --ff-only main`. Commit your plan early and after
  every milestone; rate-limit cutoffs are routine.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md`.
- Touched surfaces: `conductor/` (not `runner.py`'s thinking code, not
  `pause_watch.py` beyond wiring order), `agents/quartermaster/tools.yaml`,
  `web/stream/site-text.yaml` (wake title only), tests, docs that state tool
  counts. Not `dfqueue/feed.py`, `dfqueue/live.py`, `scripts/dfhack/`
  (unless the plan proves a field is missing, and then stop and report).
- Set intent, let the game execute: the watch reports and wakes; it never
  unsuspends, reassigns or cancels anything itself. No armok powers.
- Public repo: no hostnames, IPs or tokens. No em dashes. No attribution
  lines in commits.
- Full ambient suite and `dfmcp/tests` (in `.venv-dfmcp`) green.

## Done when

The watch, digest and allowlist built with tests, the deploy targets listed
(expect `vm106-conductor`, `vm106-agents`, `vm103-dfmcp` for the allowlist,
and the web target if a wake title was added), and a Result section here.

## Result

### Plan (written before building)

Findings from reading the code:

- `stuckjobs.find` returns a bare JSON array of workerless jobs, each
  `{job_type, detail, building, waiting_on ("suspended" | "no worker
  assigned"), idle_ticks (int or null), near_landmark, direction,
  distance_tiles, order_id, from_order}`. **It carries no job id and no
  coordinates.** Not a blocker (the handoff's stop condition is a missing
  field the watch cannot do without): the key below is a composite, and
  adding a `job_id` to the Lua tool later is a one-line key upgrade, listed
  as a follow-up, not done here (out of touched surfaces).
- `idle_ticks` is null for any job that predates the Lua tool's JOB_INITIATED
  handler (every job after a DF restart), so age cannot rely on it alone.
- The conductor calls tools as its own `conductor` role, so
  `stuckjobs.find` must be on `agents/conductor/tools.yaml` as well as the
  Quartermaster's (the handoff names only the latter; the conductor entry is
  required for the poll to work at all, same as `orders.list` already is).

What counts as stuck: a job in `stuckjobs.find` (no worker) that has been
seen in that state continuously for at least a threshold of game ticks.
Age = the larger of (now minus first-seen tick) and the tool's own
`idle_ticks` when known, so a long-sitting job is caught on the first
cycle rather than one threshold later. Two classes, both in `policy.yaml`
as data: `unclaimed` (no worker, not suspended) and `suspended`. Same
default threshold (2400 ticks, two game days; a fresh job is routinely
unclaimed for hours of game time) but separate keys because suspended is
more likely a deliberate wait (buildingplan holds a job until an item
attaches), so it can be tuned without touching the other. Renotify 12000
ticks (ten game days): a stuck job wakes once, then once per window, never
every cycle.

Keying across cycles: `job_type|detail|building|near_landmark|direction|
distance_tiles|order_id`, plus an occurrence index so two identical jobs
at one spot stay distinct. Distance and direction from the nearest landmark
stand in for position. Weakness: a job whose landmark-relative position
shifts (a new nearer landmark) looks new and restarts its clock; accepted
and documented, fixed properly by a job id.

State: its own small JSON file beside the cursors (`job_watch.json`, same
atomic write pattern as `PauseWatchStore`), one write per cycle, rather than
one `CursorStore` write per job. Keys absent from a poll are dropped, so a
job that clears and later re-sticks starts a fresh clock. Dry run reads
state but never writes it.

Which role wakes: the Quartermaster, per the `stuck_job` precedent in
`policy.yaml`, for every kind. A dig or construction stuck on a missing tool
or item is a supply problem (a pick, a bed, a block) that the Quartermaster's
orders and stock proposals address; the Architect already has
`stuckjobs.find` and sees the digest in its own briefing if it wakes for any
other reason. No second role is woken, because the watch only reports.

Wake detail names the oldest few jobs ("Bed construction suspended for 3
game days; ..."), capped. The generic `stuck_job` triage detail is replaced
by that line. The dead `job_stalled` -> `stuck_job` mapping is removed from
`EVENT_TYPE_TO_SIGNAL`. The `stuck_job` wake title already exists in
`web/stream/site-text.yaml`, so no web change is needed.

Briefing: a capped `stuck_jobs` block (count plus up to 5 short lines)
for every role, from the same poll (all age-qualified jobs, not only the
ones due to notify). The pause watchdog's early return is untouched: the
job poll runs only in the ordinary path after it.
