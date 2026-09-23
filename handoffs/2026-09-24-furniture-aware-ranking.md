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

Done, offline, `scripts/dfhack/df-overseer-zone.lua` and
`scripts/dfhack/TOOLS.yaml` (`find` entry) and
`tests/test_zone_tool_manifest.py`. Commit `8b054c6`.

**Cause confirmed as argued.** `ranked_rects` sorted candidates by
`prefer_indoors`/`dist` only, then walked the sorted list greedily,
discarding any candidate that overlaps one already chosen
(`table.sort(candidates...)` at the top of the function, the
`overlaps(c, e, w, h)` loop below it). At 3x3 every window covering the
Chair's tile overlaps whichever window the old distance-only sort put
first, so once a closer empty window was chosen the Chair-containing one
was eliminated before the caller ever saw it, not merely ranked low. At
1x1 windows are small enough that this collision is rare, which is why the
Chair survived to rank 2 there. `test_overlap_filter_runs_after_the_
furniture_sort` pins that the sort still runs before the overlap walk, so
the fix (sorting furniture-containing sites first) works by construction:
whichever furniture-containing site is closest becomes the first chosen,
and nothing already chosen can make it overlap away.

**Fix.** `ranked_rects` now takes a `has_furniture` field per candidate
(`furniture_ids ~= nil and #furniture_ids > 0`, tracking
`furniture_building_ids` exactly) and sorts on it first, only when
`furniture_type_ids` is non-nil (find's own AROUND_FURNITURE path; `place`
never passes it). `furniture_kinds` in `ZONE_POLICY` is only ever set
alongside `position_field` (already pinned by
`test_furniture_kinds_are_only_on_the_owner_capable_room_kinds`), so
gating on `furniture_type_ids` is exactly "room_value_field present and
AROUND_FURNITURE true" as the brief asked, with no separate
`room_value_field` check needed. Existing indoor/distance ranking stays
the tiebreak inside each group. When `furniture_type_ids` is nil (every
default caller) `has_furniture` is false for every candidate, the new
branch never returns early, and the comparator is otherwise byte-for-byte
what it was; `test_default_ranking_is_unchanged_without_around_furniture`
and `test_furniture_sorts_before_distance_and_indoors` pin the ordering
and the gating.

**Top-level no-candidate report (item 3).** `find_zone_area` now wraps its
output as `{results: [...], any_contains_furniture: bool, furniture_note:
"..." }` (the note only present when false) whenever `AROUND_FURNITURE` was
requested; a plain `find` still returns the bare `results` array,
unchanged. AROUND_FURNITURE has never been deployed live (TOOLS.yaml:
"offline build only, not deployed or live-verified"), so changing its
shape now, before its first deploy, breaks no live caller.
`test_find_wraps_output_only_when_furniture_requested` and
`test_furniture_note_only_appears_when_no_candidate_has_furniture` pin
this.

**Tests.** `tests/test_zone_tool_manifest.py` gained 6 source-level tests
(same style as the rest of the file: the Lua cannot run without a live
DFHack process). Ambient `python -m pytest`: **1413 passed, 3 skipped**
(baseline 1407 passed / 3 skipped, +6 for the new tests, 0 regressions).
`dfmcp/tests` via `C:\website-projects\df-automation\.venv-dfmcp\Scripts\python.exe`:
**652 passed** (baseline 652, untouched — this stream did not touch
`dfmcp/**`).

**Live check a deploy should run** (not run here, offline only): the same
`find Office 3 3 0 "shale Throne" 10 true` that returned five
furniture-free sites. Expect `any_contains_furniture: true` at the top
level and the Chair-containing site (`furniture_building_ids: [9]`) at
rank 1, ahead of any furniture-free window.

**Owed register lines** (not written here, per the `handoffs/` rule --
the orchestrating session owns `Working.md`, `decisions/DECISIONS.md`,
`memory/` and `handoffs/INDEX.md`):
- `Working.md`: this handoff done, offline, awaiting the live check above
  before its next deploy.
- `decisions/DECISIONS.md`: a decision worth a row -- AROUND_FURNITURE's
  `find` response shape changed (bare array to a wrapped object) ahead of
  its first live deploy, so no live caller breaks; reason: the brief's
  item 3 (top-level no-candidate report) cannot be expressed inside an
  array without ambiguous JSON encoding, and a precedent already exists
  (`list_zones` wraps its own array the same way).
- `handoffs/INDEX.md`: flip this handoff's row to done.
