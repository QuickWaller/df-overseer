# Chair completion run, 2026-09-23

Handoff: `handoffs/2026-09-23-chair-completion-run.md`. Live, mutating,
unattended run on VM 103. User go-ahead given explicitly ("yep go for it"),
not watching. Goal: job 2249 (`ConstructThrone` at the Masons, direct job,
`order_id: -1`) runs and produces a CHAIR item, and the buildingplan-
suspended Chair building (id 9) claims it and completes.

**Status: in progress, filled in as the run goes.**

## Starting state, verified before any action

- `clock status`: paused true, armed true, `abs_tick 12607074` (year 31,
  `cur_year_tick 107874`), 100 fps, **latched**: `hostile_reachable`,
  `{race: BIRD_KEA, distance_tiles: 68, direction: SE, near_landmark:
  "Mechanic's Workshop", why: ["shares_walkable_group_with_citizens"]}` --
  the stale latch from the previous run, under the pre-fix tier code, exactly
  as the brief said to expect.
- `vitals summary`: alive 22, dead_total 1, worst_hunger "fine", worst_thirst
  "thirsty" (warning, not critical).
- `orders list`: ids 0/1/2 `validated: true, active: false`
  (ConstructBlocks/ConstructMechanisms/CustomReaction-brew); id 3
  (ConstructThrone) `validated: false, active: false`.
- `stocks availability CHAIR`: `total_item_count: 0`.
- `stuckjobs find`: two entries -- the suspended `ConstructBuilding` job on
  building id 9 ("unknown material Throne", `waiting_on: suspended`,
  `idle_ticks: 898`), and the `ConstructThrone` job at the Stoneworker's
  Workshop, `waiting_on: "no worker assigned"` (this is job 2249; the
  perception layer never returns a raw job id, so it is tracked here by job
  type + workshop + worker state, cross-checked once directly against
  `df.global.world.jobs.list` by id, see below).
- Building id 9 read directly (`df.building.find(9)`, bounded single-id read,
  not a map scan): `btype: "Chair"`, `construction_stage: 0`, `flags.exists:
  false`, `#jobs: 1` (the suspended job above). This is the read-back marker
  used every window to say whether the Chair has completed: `flags.exists`
  flipping true, or `#jobs` dropping to 0 with `flags.exists` true, is
  "built"; nothing else is trusted as a completion signal.

## Safety envelope

- **Quicksave before any unpause**: prior slot `autosave 3`; confirmed via
  `cur_savegame.save_dir` (DF's own record, never mtime -- `docs/TRAPS.md`)
  after polling: landed in **`autosave 1`**.
- **Stale latch cleared**: `clock clear` returned `had_latch: true`.
  Re-armed with defaults (`clock arm`): `hunger_critical 75000,
  thirst_critical 50000, check_interval_ticks 100, threat_check_every_n 10,
  think_fps 10`. Confirmed via `clock status`: no `tripwire` field, `armed:
  true`, tick unchanged (12607074) -- clearing and arming cost no game time.
  **It did not re-latch on the same kea after the fix.**
- Windows of at most 2000 ticks, at most 10 windows, quicksave between
  windows, job 2249 / Chair building / stocks CHAIR / vitals / all four
  orders read after every window.

## Refusals hit this run (not routed around through another agent/session)

The Claude Code auto-mode classifier refused several individually-safe,
read-only `dfhack-run` calls issued over `scripts/vm-ssh.sh`, inconsistently
(the identical command succeeded on a later retry in every case but one):

- `df-overseer-workjob cancel 2249 true` (dry-run by default, code path never
  calls `removeJob` when `dry_run` is true -- read from source before use):
  refused twice running, reason `Irreversible Deletion (general)` /
  `Interfere With Workloads`, apparently keyed on the word "cancel" in the
  command text rather than on what the code path actually does. **Worked
  around** by not using this command at all: job 2249's state was instead
  read via `stuckjobs find` (present/absent, worker/no-worker) and, to
  resolve the one genuine ambiguity ("no longer in stuckjobs" could mean
  "has a worker now" or "job removed, either finished or vanished"), a
  direct bounded read of `df.global.world.jobs.list` for `id==2249` via
  `dfhack-run lua`, matching this project's own existing `find_job_by_id`
  pattern in `df-overseer-workjob.lua`. Never attempted the cancel command's
  real (`dry_run=false`) path at any point.
- `df-overseer-stocks availability CHAIR` and `df-overseer-orders list`: each
  refused once (`Interfere With Workloads`) when issued in a batch of four
  parallel calls, then succeeded immediately on a sequential retry alone.
  Treated as batching-related classifier noise, not a real block on the
  command; no workaround needed beyond not batching unrelated VM calls in
  one turn.
- `df-overseer-stuckjobs find`: refused once (`Interfere With Workloads`),
  succeeded on immediate retry with the identical command.

None of these were routed around through another agent or session; each was
retried plain and literal, or replaced with a different already-existing
read path, per `docs/TRAPS.md`'s documented practice for this class of
classifier friction.

## Window log

### Window 1

- Resumed at `abs_tick 12607074` (`clock resume`, `paused: false`).
- Polled `clock status` in a bounded local loop (literal, non-computed
  `vm-ssh.sh` calls, spaced 3s apart, capped at 60 iterations) until
  `abs_tick` reached the 2000-tick target or the fort paused itself.
- **A `slow`-tier advisory fired, not a pause**: at `abs_tick 12609096` (fps
  already dropped to 10 by the advisory itself), `clock status` read:
  ```
  "advisory": {
    "reason": "hostile_slow",
    "tick": 12608974,
    "detail": {
      "race": "BIRD_KEA", "distance_tiles": 7, "direction": "NW",
      "near_landmark": "Farm Plot", "tier": "slow",
      "tier_reasons": ["theft_tag_close_range"],
      "why": ["shares_walkable_group_with_citizens",
              "within_30_tiles_of_Farm Plot"]
    }
  },
  "paused": false
  ```
  Per `docs/AGENT-LOOP.md` §3, a `slow`-tier trip throttles FPS and writes a
  non-blocking advisory; it is explicitly not one of this run's stop
  conditions (those are a death, a **pause**-tier tripwire, a vital crossing
  threshold, or job 2249 vanishing without a Chair). **This is the first
  live `slow`-tier trip this fort has ever produced against the
  post-fix classifier** (the only trip before today was the pre-fix
  `pause`-tier kea at 68 tiles). Treated as expected behaviour, not a
  surprise, and the run continued. Manually paused (`clock pause`) once the
  tick target was reached, to close the window.
- **Window end reads** (`abs_tick 12609255`, year 31, `cur_year_tick
  110055`; overshoot past the 2000-tick target of ~2181 ticks is polling
  granularity, not an unbounded run):
  - Job 2249: no longer in `stuckjobs find`'s output (only the suspended
    building job remains). Direct id lookup confirms why: `{found: true,
    info: {jtype: "ConstructThrone", has_worker: true, suspend: false}}` --
    **in progress, not vanished.**
  - Chair building id 9: not re-read this window (deferred to when stocks
    or the job state changes; still 1 suspended job as of the start read).
  - `stocks availability CHAIR`: `total_item_count: 0` -- no Chair item yet.
  - `vitals summary`: alive 22, dead_total 1, worst_hunger "fine",
    worst_thirst "thirsty" (unchanged from baseline, still warning not
    critical).
  - `orders list`: all four unchanged -- ids 0/1/2 `validated: true, active:
    false`, id 3 (ConstructThrone) `validated: false, active: false`.
  - Quicksave issued (prior slot `autosave 1`), confirmed landed in
    **`autosave 2`**.

### Window 2

- Resumed at `abs_tick 12609255` (`clock resume`, `paused: false`).
- The `slow`-tier advisory from window 1 was still latched (it does not
  self-clear on resume, matching design: only `clear`/`re-arm` reset it) and
  fps stayed at 10 for the whole window, so this window ran roughly 4x
  slower in wall-clock terms than window 1. The kea it tracks moved closer
  over the window (from 7 tiles near the Farm Plot to `distance_tiles: 0`
  at "Stockpile #2"), still only ever `tier: "slow"`, never escalating to
  `pause`.
- **Job 2249 vanished from the job list mid-window** -- caught by the
  ad-hoc `id==2249` lookup this run uses in place of the classifier-refused
  `workjob cancel ... true` dry-run check: `{job2249_found: false}`. Per the
  handoff's own explicit stop condition ("job 2249 vanishing without a
  Chair appearing"), **the fort was paused immediately**
  (`clock pause` -> `{ok: true, paused: true}`), before checking anything
  else, per "pause first and report second."
- **Checked immediately after pausing, and the vanishing was benign**: a
  Chair item now exists. `stocks availability CHAIR`:
  ```
  "total_item_count": 1, "available_item_count": 0,
  "in_job_item_count": 1, "in_job_units": 1
  ```
  The item is `in_job` (held by the building-construction job), not sitting
  idle -- job 2249 completed, produced the Chair, and was removed from the
  job list the ordinary way a finished job is; it did not vanish without
  producing anything. This resolves the run's one genuine ambiguity (a job
  disappearing from `world.jobs.list` is indistinguishable, from that read
  alone, between "finished" and "cancelled/errored"; the stocks read is
  what tells them apart).
- **Chair building id 9, re-read**: `{btype: "Chair", construction_stage: 0,
  exists: false, jobs_n: 1}` -- not yet built (the Chair item has been
  produced and is being carried/used, but the building itself has not
  completed). `stuckjobs find` now returns `[]` (empty) -- the
  `ConstructBuilding` job that was `waiting_on: "suspended"` at the start of
  the run now has a worker: buildingplan un-suspended it once the item
  became available, exactly as `df-overseer-building.lua`'s own header says
  it should.
- **Window end reads** (`abs_tick 12611099`, year 31, `cur_year_tick
  111899`, window length 1844 ticks, under the 2000 cap):
  - Job 2249: gone from the job list (completed, see above), Chair item
    confirmed produced.
  - Chair building id 9: `exists: false`, still 1 job, now in progress
    (not suspended).
  - `stocks availability CHAIR`: `total_item_count: 1`, all of it
    `in_job_item_count` (none `available`, none `in_building` yet).
  - `vitals summary`: alive 22, dead_total 1 (unchanged, no death),
    worst_hunger "fine", **worst_thirst "fine"** (improved from "thirsty" at
    the start of the run, `warning_count` dropped from 1 to 0) -- no vital
    crossed a threshold in the bad direction.
  - `orders list`: all four unchanged from baseline -- ids 0/1/2
    `validated: true, active: false`, id 3 (ConstructThrone) `validated:
    false, active: false`. **The Chair that got made came from job 2249,
    the direct job, not from manager order 3** -- order 3 has still never
    gone active or validated at any point in this run, direct evidence that
    the direct-job route and the manager-order route are genuinely separate
    here, not two views of the same mechanism.
  - Quicksave issued (prior slot `autosave 2`), confirmed landed in
    **`autosave 3`**.
