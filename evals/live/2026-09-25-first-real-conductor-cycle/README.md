# First real conductor cycle, 2026-09-25

**Status: done, one cycle, fort paused throughout.** The first non-dry-run
`conductor --once` against the live fort (Uniboslan, year 31, tick 174297).
The user's go-ahead: "yes lets see what happens", after being told the queue
held two stale proposals and that the Overseer might or might not catch them.

## Attempt 1 failed harmlessly, and why

Run from a plain SSH shell as the service account, every role failed in about
17 ms with `agent exec --json printed nothing` and cost 0. Cause: Docker
access was granted to the `conductor.service` unit only
(`SupplementaryGroups=docker`, 2026-09-22), not to the account's login shell,
so `docker run` got "permission denied". Side effects: one real quicksave, and
the routine-review cursor advanced as if a review had happened (a failed run
still advances it). The cursor key was removed (file backed up first) to
restore "due now".

## Attempt 2: a transient systemd unit mirroring the approved unit

Same user, group, `SupplementaryGroups=docker`, sandboxing and read-write
paths as the installed unit, plus `--once`, via `sudo -n systemd-run`. No new
access was granted. All three roles woke: Architect (routine review), Quartermaster
(routine review), Overseer (queue pending).

| Role | Result | Cost | Wall clock |
|---|---|---|---|
| Architect | ok, filed `proposal-0004`, one `ask`, wrote a gotcha | $0.018 | 158 s |
| Quartermaster | ok, filed `proposal-0005`, wrote a gotcha | $0.019 | 93 s |
| Overseer | **timed out at the 600 s cap**, after ruling and executing | not recorded | 600 s |

## What the Overseer decided

- **`proposal-0002` and `proposal-0003` (stale, both about the Manager's
  office): rejected, with reasons from live reads** (the Manager already owns
  Office zone 13 near the shale Throne, which holds a chair). The charter's
  "never act on a stale proposal" held under a real run.
- **`proposal-0004` (down-stair beside the Farm Plot into stone): accepted and
  executed for real.** Down-stair and up-stair designated, quickfort ok. The fort
  is paused, so nothing has been dug yet. Its reason cites 22 dwarves, no
  bedroom or dining hall, and soil windows that quickfort cannot smooth.
- **`proposal-0005` (brew a batch at the Still by direct workshop job):
  accepted, execution failed.** `workjob.queue` refuses the brew reactions
  because their container reagent is a wildcard-matched empty barrel, which the
  tool will not guess. Drink is still 0 (dwarves drink at the Well).

## Findings worth acting on

1. **Tool gap:** `workjob.queue` cannot specify a container for reactions with
   a wildcard reagent, so direct brewing is impossible. Generalisable fix: take
   the item as an argument.
2. **Tool ergonomics cost real calls:** positional optional arguments ("cannot
   supply `dry_run` without also supplying `level`") caused three failed
   `diggable.dig-stair` and three failed `workjob.queue` calls before success.
3. **Overseer timeout, resolved from the MCP journal:** 600 s was too tight, not
   lingering. Its 25 calls ran 02:36:48 to 02:46:20 with 1 to 3 minute model-thinking
   gaps; the last write came at about 583 s and the kill 17 s later. The cap is now
   1200 s for the Overseer (`conductor/policy.yaml`).
4. **The Overseer filed an `ask` to the Consultant** (`ask-0001`) but the
   Consultant was not woken this cycle. An open ask should wake it next cycle.
5. **A failed run still advances the routine-review cursor**, which would
   silently skip reviews for 7 game days.
6. **Docker access is unit-scoped**, so a manual real run must go through a
   transient unit that mirrors it, not a bare SSH shell.

## Verification

After the cycle the fort was re-read independently: paused, tick 174297 (no
game time passed), 22 alive, 0 warnings, worst hunger and thirst "fine", the
tripwire armed on defaults. The queue rows above were read from the queue
database directly, not taken from the roles' own reports.

## Second cycle, same day: crashed before the Consultant ran

After deploying the conductor fixes (16 files hash-verified, old copy backed up), a dry run planned one wake, the Consultant for the open `ask-0001` (the re-wake fix works). The real run then **crashed** with `PermissionError` writing `SOUL.md` into the Consultant's workspace directory, which is owned by root while the other three role workspaces are owned by the service account. Fort untouched (paused, tick 174297), no containers, cursors not advanced.

Two findings: (1) the Consultant workspace ownership is drift from the other roles and blocks its first real run; (2) **`write_soul` in `conductor/runner.py` sits outside the runner's `launch_failed` handling**, so a charter write failure crashes the whole service instead of being recorded as a failed run, and under `Restart=on-failure` that would loop. Cost recording for a successful run is still unobserved.

## Second cycle, retried after chowning the Consultant workspace: worked

Only the Consultant woke (`open_ask`, the ask filed mid-cycle by the Overseer; the re-wake fix works). **Cost recorded: $0.0076, 49 s, 23 tool calls (1 failure)**, daily total $0.0448 known, 0 runs with unknown cost. (The first cycle's Overseer cost stays unknown: it predates the fix.) The Consultant answered the ask (`answer-0001`). Fort re-read: paused, tick 174297, no containers left.

What it said: it **could not** describe `proposal-0002`/`0003` because its toolset has no queue-read tool (`queue.pending` gave it only the ask itself), searched DFHack's own source for the words, found nothing, and **refused to invent contents**, naming the blocker. That is the honest behaviour we want. It also shows the Overseer **misrouted the ask**: the Overseer reads the queue itself, and the Consultant is for game knowledge, so an ask about queue contents was outside its remit and cost about 20 pointless source searches. Worth a line in the Overseer's charter (`agents/overseer/role.md`): ask the Consultant about the game, never about the queue.

## After the fixes: deploy, live tool check, and the stair

Deployed the same day (peer heads-up sent, backups first, sha256-verified against committed bytes): VM 103 got `dfmcp/registry.py`, `dfmcp/tools.py`, `TOOLS.yaml`, the Overseer charter and `df-overseer-workjob.lua`, with only `dfmcp-server` restarted (clean start, 0 restarts, game services untouched); VM 106 got `conductor/` and both charters. Merged main first passed 1875 ambient (3 skipped) and 695 dfmcp tests.

**Live check of the new `workjob` reagent code (read-only `list-jobs` on the Still):** the flag reads work with no errors, plants to brew exist (108 plant items, 120 growths), but **`free_candidate_count` is 0 for the empty food-storage container: the fort has no free empty barrel or pot.** So brewing was blocked by a real missing barrel, not only by the tool's old refusal. The fort needs barrels made (the `barrels` direct job exists) before any brew can run.

**Supervised unpause, 10 FPS, 600 s wall (tick 174297 to 180206, about 4.9 game days), tripwire on defaults, restore trap:** the down-stair the Overseer designated **was dug** (`CarveDownwardStaircase` and `CarveUpwardStaircase` jobs appeared and cleared), 24 `PlantSeeds` job-polls (the farm plot got planted), 4 polls with `Drink` jobs, all 22 alive, 0 warnings, worst hunger and thirst fine, thirst timers peaked about 17.7k. Re-read after: paused, tick 180208, no stuck jobs.

**Pre-existing deploy drift found and deliberately not touched:** five Lua scripts (`chokepoints`, `diggable`, `openarea`, `stockpile`, `ui`) and, on VM 103's MCP tree, `ROSTER.yaml`, the conductor, quartermaster and consultant role files, `consultant/sites.yaml` and `dfmcp/README.md` differ from the repo. They predate today; deploying them would have shipped unrelated earlier changes. Worth a separate drift audit.

## Third and fourth cycles: the team found the barrel problem on its own, and asked for a go-ahead

Nothing was suggested to the agents. The routine review was made due (cursor key removed, backed up) and two `--once` cycles ran on the fixed conductor, fort paused.

**Cycle A (Architect, Quartermaster, then Consultant via the re-wake fix):** $0.0158 (140 s), $0.0077 (81 s), $0.0309 (106 s). The Architect filed `proposal-0006` (site a Carpenter's Workshop, because carpentry is missing so no barrels or furniture can be made). The Quartermaster noticed that the workshop tool's 0 free empty containers conflicted with `stocks.availability`'s 15 barrels, asked the Consultant about it (`ask-0002`) and filed `proposal-0007` (queue brewing directly). The Consultant explained the two tools count different things (all fort-owned barrels versus empty, food-storage, unheld ones) and flagged a stale note (the Manager prerequisite is now met).

**Cycle B (Overseer):** $0.0623, 540 s, ok. **Accepted `proposal-0006`** after verifying live that no carpentry exists, 2 citizens hold the carpenter labor, 5 sites qualify and blocks and boulders are on hand. **Deferred `proposal-0007`** because the 15 barrels all hold the fort's 147 raw plants, so the tool would refuse; the true blocker is empty containers, which need carpentry then wood. It then ran a **dry-run** of `building.build` and **stopped short of the real build, asking for the user's go-ahead**, because the tool requires it for the first real build of a kind the project has never built. (Orchestrator note: the orchestrator first misread the dry-run's ok as a real placement and corrected it after checking that no Carpenter's Workshop building existed.) It filed no `queue.executed` record, correctly, since nothing was executed. Day total $0.162, 0 unknown-cost runs.

**Supervised unpause afterwards (10 FPS, 600 s, tick 180208 to 186326):** nothing built, as expected; the dwarves slept, ate and drank (9 polls with `Drink` jobs), 22 alive, 0 warnings, re-paused, no stuck jobs.

**Finding:** the Overseer's final answer, which is a question for the user, is delivered nowhere except the run archive. An escalation to the human needs a delivery path (the agent activity feed, `ROADMAP.md` Later, or a notification).

## Fifth cycle, 2026-09-28: bedroom dig accepted and executed; a genuine duplicate-proposal gap found

Fort untouched since the last window (paused, tick 192334, 22 alive). Dry run showed the routine review was due on its own (10.1 game days) plus stalled/blocked manager orders (0, 1, 2); ran for real, all four roles woke, cost recorded throughout (day total $0.121, 0 unknown).

**Architect** ($0.024, 170s): filed `proposal-0008`, the first bedroom cell's dig shell near the Farm Plot, reasoning that 22 dwarves have no beds or bedroom zone. Asked the Consultant what `proposal-0007` (still open from 2026-09-25, deferred not rejected) asks for.

**Quartermaster** ($0.017, 101s): asked the Consultant to report the whole queue (a queue-read tool it does not have). **Filed `proposal-0009`, a near-duplicate of the still-open `proposal-0007`** (queue brewing directly at the Still), without checking that an equivalent proposal already existed, and got a specific fact wrong: it described the barrels as already empty, when they hold the fort's plant stock.

**Consultant** ($0.023, 115s): correctly refused both queue-content questions (no queue-read tool, by design), and for the Architect's second question gave a real, correct read of what's missing (no bedrooms, etc).

**Overseer** ($0.057, 343s): **rejected `proposal-0007`** (deferred since cycle B) and **rejected `proposal-0009`**, both for the same live-verified reason (`workjob.list-jobs` container reagent has 0 free candidates), and for 0009 explicitly caught the Quartermaster's wrong claim that barrels were empty. **Accepted and executed `proposal-0008`**: previewed the bedroom shell (10/10 tiles reachable, no unsmoothable material), verified labor (2 miners, 2 masons, 3 stonecutters) and 0 beds/bedrooms in stock, then designated the dig for real (`blueprint.apply`, 12 tiles, `designations_landed: true`).

**Finding: a real duplicate-proposal gap, not just staleness.** The Quartermaster filed `proposal-0009` without checking `proposal-0007` was still open, and it also introduced a factual error the earlier proposal didn't have. `orders.check-duplicate` (gotcha-0002) only covers manager orders; there is no equivalent check against the architect/quartermaster's own open proposals before filing a new one. Worth a queue-side duplicate check, generalisable across proposal types, not specific to brewing.

Fort re-read after: paused, tick 192334 unchanged (fps left at 10 by the conductor's own clock policy, not a manual change), stuck-job list shows the same lone unassigned `FellTree` from the prior window (only one woodcutter).
