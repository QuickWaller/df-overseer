# Handoff: is the Well a working water supply, and what does the tripwire do

Date: 2026-09-25. **Executor, Sonnet. READ-ONLY on the live fort. No files written except this doc's Result.**

Context: fort-owned drink is 0 (known since 2026-09-16). The user believes the
Well is now running but nobody has verified it. Read `decisions/DECISIONS.md`
entries on the Well, the pond/pools and the survival clock (2026-09-16/17,
2026-09-23/24) and `docs/TRAPS.md` before you start. Reach the fort as the
vitals check did: `scripts/vm-ssh.sh df`, then `/opt/df/game/dfhack-run` with
read verbs only. Read secrets by single key only.

## Answer, with evidence
1. Is the Well built, complete, and holding water? Depth/fill of the well
   cistern, whether it is connected to a water source that is actually
   supplying it, and any building state flags. Use the `well` tool's read verbs
   and direct struct reads.
2. Can dwarves reach it? Use the shared tri-state reachability helper's
   answer (reachable / unreachable / unknown); note the known false negative
   at the Well's own centre tile (ramp top) and do not be fooled by it.
3. Is anything assigned to draw from it? Are there buckets, a hauling/drink
   job pattern, or a still, or is drink demand unmet? A paused fort cannot
   show live behaviour, so say which parts are inference.
4. Tripwire: what thresholds and actions does it have configured (read, do not
   change), and would it fire on a thirst crisis before a death?
Say for each: verified directly, inferred, or not checkable while paused.

## Hard limits
Do not unpause, save, reload, place, dig, order, assign, or change anything in
the game. Do not restart any service or VM. Do not run the conductor. If the
only way in is a write, stop and report. No em dashes. Commit nothing.

## Report
Under 300 words: a verdict on "the Well is (or is not) a working water supply",
the evidence behind each of the four answers, and what a short supervised
unpause would still need to settle. Stop and report on any permission refusal.

## Result

(pending)
