# Handoff: a site that contains the furniture should outrank one that does not

Date: 2026-09-24. **Offline. No VM, no deploy, no fort mutation, no unpause.**
The deploy needs its own go-ahead and the orchestrating session will ask
separately.

Read `CLAUDE.md` first, then
`evals/live/2026-09-24-zone-nobles-deploy/README.md` (the deploy that found
this, check 3), `scripts/dfhack/df-overseer-zone.lua`'s `ranked_rects` and
`ZONE_POLICY`, and `handoffs/2026-09-23-zone-inventory-and-validity.md`'s
Result section (the `AROUND_FURNITURE` design you are extending, not
replacing).

## The gap, measured live

`AROUND_FURNITURE=true` works and resolves the right building. At a 1x1
footprint near the fort's Chair it returns 5 candidates and rank 2 reads
`contains_qualifying_furniture: true, furniture_building_ids: [9]`.

At a realistic **3x3** office footprint, the same search returns 5 candidates
and **every one reads `contains_qualifying_furniture: false`**. The
chair-containing site is either not a legal window at that size or ranks below
the cut. Either way the caller never sees it.

For a kind with a `room_value_field`, a site containing qualifying furniture
is strictly more useful than one without, because that furniture is the entire
source of the room's value. An empty rectangle for such a kind is the failure
this whole line of work exists to prevent, and right now it is what ranks
first.

The flag informing rather than refusing is correct and stays. Informing only
helps when the useful candidate is visible.

## What to do

1. **Rank furniture-containing sites above furniture-free ones**, for kinds
   with a `room_value_field`, when `AROUND_FURNITURE` is true. Keep the
   existing ranking (landmark, distance, walkable group, indoor preference) as
   the tiebreak within each group rather than replacing it. A kind with no
   `room_value_field` must rank exactly as it does today.
2. **The likely cause is the overlap filter, not the result cap.** The
   orchestrating session traced this before dispatching, so do not re-derive
   it, but do confirm it from the code. After sorting, `ranked_rects` walks
   candidates greedily and discards any that overlaps one already chosen,
   stopping at `MAX_RESULTS`. That dedup is right in itself (it stops five
   near-identical rectangles one tile apart) but it means a chair-containing
   3x3 window is not merely ranked low, it is **eliminated** once a slightly
   closer window is chosen first, because every 3x3 window containing that
   tile overlaps it. At 1x1 the windows are small enough that overlap is rare,
   which is exactly why the Chair survives to rank 2 there and vanishes at
   3x3. Item 1 fixes this as a side effect: sorting furniture-containing sites
   first makes one of them the first chosen, so nothing can overlap it away.
   Confirm that reasoning holds and say so in the Result; if the code says
   otherwise, say that instead and fix what is actually wrong.
3. **If a caller asks for furniture-aware siting for a room-value kind and no
   candidate contains any, say so explicitly** in the returned structure, at
   the top level rather than only per row. A caller scanning rank 1 should not
   have to infer it from five false values. Do not refuse, and do not invent a
   site.

Keep it small. This is a ranking and reporting change, not a redesign, and
`zone.place` stays untouched.

## Scope

Yours: `scripts/dfhack/df-overseer-zone.lua`, `scripts/dfhack/TOOLS.yaml` (the
`find` entry only), `tests/test_zone_tool_manifest.py` and any other zone
tests, and this doc's Result section.

Not yours: `df-overseer-nobles.lua`, `dfmcp/**`, `agents/**` (no new tool, so
no new grant), `conductor/**`, `doctrine/**`, any other `.lua`, and per the
`handoffs/` rule `Working.md`, `decisions/DECISIONS.md`, `memory/` and
`handoffs/INDEX.md`. Collect owed register lines in your Result.

## Rules

- **Offline only.** The fort is paused and stays paused. The live facts you
  need are in the eval README named above; do not read the fort yourself.
- `git merge --ff-only main` first; this brief is committed on main.
- Both suites green, numbers quoted: ambient `python -m pytest` (baseline
  **1407 passed, 3 skipped**) and `dfmcp/tests` in `.venv-dfmcp` (baseline
  **652 passed**). Use `python`, not `py -3`.
- Existing callers that do not pass `AROUND_FURNITURE` must get byte-for-byte
  identical ranking. Pin that with a test.
- Keep output coordinate-free and never render a map.
- No em dashes in prose. **No attribution lines in any commit message.**
- Stop and report on any permission or classifier refusal. Never route around
  one through another agent or session.

## Done means

For a room-value kind with `AROUND_FURNITURE=true`, a site containing
qualifying furniture ranks above one that does not, the no-candidate case is
stated at the top level, the reason no 3x3 window contained the Chair is
explained, and default ranking is provably unchanged. The Result names the
live check a deploy should run: the same `find Office 3 3 0 "shale Throne" 10
true` that returned five furniture-free sites.

## Result

(to be filled by the stream)
