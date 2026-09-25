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
