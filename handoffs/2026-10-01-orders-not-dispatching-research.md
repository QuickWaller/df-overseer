# Handoff: why the Manager does not dispatch orders on this fort

Date: 2026-10-01. **Researcher, Sonnet, read-only. No code, no live access**
(the orchestrator runs any live read you propose).

## Why

Live, 2026-10-01 (`evals/live/2026-10-01-queue-and-material-deploy/README.md`,
last section): a new repeating order (MakeBarrel, AtMost 20 BARREL, 17 in
stock) stayed `validated: false` through about 2.5 game days of a supervised
unpause; three older orders have sat `validated: true, active: false` for
weeks; one was never validated. A Manager is appointed and has an office
accepted by the game. The user reports manager orders work in their own
play, and a direct workshop job (`workjob.queue`) did produce barrels here.
Read `research/2026-10-01-quartermaster-levers.md` §1,
`research/2026-09-23-announcement-severity.md` §C, the register rows of
2026-09-21 to 2026-09-24 about orders and the Manager, and
`scripts/dfhack/df-overseer-orders.lua` first.

## Questions

1. In v50 (DF 53.x), what exactly moves an order from unvalidated to
   validated and from validated to active: which dwarf job does the Manager
   perform (and what does it need: office, time, labour enabled, not busy,
   burrow access), how often, and what the wiki and DFHack source say about
   each bit (`df.workquota.xml`, the `orders` plugin, DF wiki "Manager",
   "Work order").
2. What keeps a validated order inactive: missing workshop of the right
   kind, the workshop's own profile or order limits, max_workshops,
   conditions, materials, labour, the order's own frequency start.
3. For each candidate cause, a **read-only** check the orchestrator can run
   on VM 103 (a `dfhack-run lua` read of named fields, or an existing tool),
   in the order most likely to find it.
4. Anything our own tools do that could cause it (for example orders created
   by `workorder.lua` differing from UI-made ones in a field DF needs).

## Deliver

`research/2026-10-01-orders-not-dispatching.md`, short answer up front,
verified versus unverified marked, and the ordered list of live read-only
checks. Fill in this handoff's Result (about 200 words).

## Rules

- First step `git merge --ff-only main`; commit the plan early, then after
  each question.
- Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`.
- No em dashes in prose. No attribution lines in any commit.
- Do not guess DF behaviour; say "unverified".
- Stop and report on any permission refusal.

## Touched surfaces

`research/2026-10-01-orders-not-dispatching.md` and this handoff only.

## Result

(fill in)
