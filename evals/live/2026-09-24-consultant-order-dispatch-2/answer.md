I have enough to answer definitively. Findings below are grounded in this install's own DFHack scripts (`<host>.lua`, `-nobles.lua`, `-workjob.lua`), which contain this exact fort's live-verified history.

## (1) What must be true, and API vs game-validated

Manager orders are a **queue that needs a Manager to approve** (verified — this install's `<host>.lua` header). For dispatch you need, in order: a citizen who actually holds the MANAGER position with a link that resolves to a live unit; that manager performing the **ManageWorkOrders job (type 195) in his office** — that job is what both *validates* the order and turns it into a real workshop job; a met office (chair in an owned Office zone); plus the workshop/labor/material conditions you've already confirmed.

**API-validated ≠ game-validated.** The `validated` bit on `manager_order` is just a field you can write. The project hand-set it `true` and ran tens of thousands of ticks with a matching workshop and material sitting available, and never saw the job become real (verified). The game's own validation is the manager's type-195 job, and the `manager_order` struct exposes *none* of what gates that dispatch (verified). So your three `validated=true` orders are not equivalent to a manager who actually validated them.

## (2) Top three causes, ranked

1. **No live Manager appointment.** This install's register (2026-09-19) records *zero citizens holding MANAGER*; an entity-scope scan found one filled assignment whose histfig's `unit_id` did not resolve to a live unit — likely a foreign site (verified). If unit 345's "hold" is that broken link, the game screen can show him while the engine sees no manager. This blocks validation *and* dispatch.
2. **The manager never ran his type-195 job.** You saw no ManageWorkOrders job and he only ate (your read). That is the proximate reason nothing dispatches — the validating/dispatching job itself never got scheduled.
3. **Manager stress/insanity.** Highest stress category + a haunting ghost; a stressed or insane dwarf won't sit in the office and do the job even if appointed (recall/standard practice).

The office is *unlikely* to be the blocker: `getRoomDescription` returning `""` is a known false alarm on this exact fort — the game's own nobles screen accepted the room (verified, 2026-09-24 room-proxy-fix). The throne order reading `validated=false` just confirms validation never ran *at all*, for any order.

## (3) Cheapest experiment

Two read-only steps, in order:

- **`nobles verify MANAGER`** (one call). `consistent=true` → appointment is fine, move to office/stress. `consistent=false` or vacant → appointment is the root cause; appoint a real manager and retest.
- **Behavioral split:** queue one *direct* job at the Mason's workshop via `<host>` (the "q→add job" path — no manager needed). If it dispatches and finishes within a few ticks while orders still don't → materials/labor/capacity are fine and the block is specifically the manager-validation queue. If even the direct job stalls → the problem is workshop/labor-side, not the manager.

## (4) Self-pausing link

Not explained by orders. Most plausible: your censuses run every ~100 ticks, so "paused ~110 ticks after resume" reads as the measurement tooling re-pausing after its run window, not a game event (hypothesis). No announcement rules out normal game pause reasons. I see no mechanism tying it to manager dispatch, and I **do not know** the true cause — check autopause/repeat config and the sampler.

## (5) Single first step

**Run `nobles verify MANAGER`.** Read-only, one call, and it directly decides whether unit 345 is a live, consistent manager or a broken/foreign link — the fork everything else depends on.

**Do not know:** whether the engine can dispatch with no manager at all (the project itself flagged this unverified — it can't advance time to test); the exact stress threshold that stops office work; and the real cause of the self-pauses.