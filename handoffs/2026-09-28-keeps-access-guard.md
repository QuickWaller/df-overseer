# Handoff: `keeps_access` and haul-before-seal guards in `construction.build`

Date: 2026-09-28. **Executor, Sonnet, worktree.**

## Context

`research/2026-09-28-job-dependency-graph.md` (Opus design, committed `b0d3072`,
reviewed by the user) recommends a build order for generalising job
dependency tracking on this fort. **Item 1, cheapest and highest value, is
this handoff**: a `keeps_access` guard as a plain tool-layer refusal inside
`scripts/dfhack/df-overseer-construction.lua`'s `build_construction` function
(the `build` command). Read that research file's §0 point 5, §2.2's
`suspendmanager` section (lines ~199-209), §4.2 (the guard mechanism), and
§5.1 steps 6-9 (the worked example) before writing any code — this handoff
summarises but does not replace it.

**The live motivating case** (`Working.md`, still open): after
`construction.mine-vein 13` and `construction.build 13 wall` ran for real on
the Manager's Office, a wider scan found the hematite vein continues past
zone 13's ring. One of the 5 new wall buildings (id 22) sat directly next to
still-unmined, exposed ore; its build job was suspended by hand as a stopgap
because nothing in the tool itself would have refused it. **This handoff
builds the thing that should have refused it.**

**A second, related finding from the same day** (`Working.md`): the user
asked whether ore mined out of a tile needs to be hauled to a stockpile
before that tile gets walled over. Investigation found no ore was actually
produced this time (DF's vein tiles have only a 33% chance of dropping ore
per tile mined, confirmed via the DF wiki, not a bug), but the requirement is
real and general: **a build step must never proceed while an un-hauled
ore/valuable item sits on its target tile.** Build this as a second guard in
the same vocabulary.

## The two guards to build

Both live in the guard vocabulary the design proposes (§4.2): a closed,
data-listed predicate over the world, evaluated **per target, jointly over
the whole step** (not tile-by-tile independently — see below), returning
`pass`, `hold`, or `unknown` (never defaulting to `pass` on a read failure).

### 1. `keeps_access`

Before designating any of a `construction.build` call's wall targets, check
whether building **all of them together** would seal off any currently
reachable, exposed, economic (`isOre()`/`isGem()`, the classifier
`surface.vein-material` already uses) ore tile that is not itself hidden
(hidden tiles are outside every guard's scope, per the no-armok rule — do not
reproduce a "how much ore is nearby" count anywhere agent-facing). If sealing
some subset would cut off access and a different subset would not, hold only
the tiles needed to keep at least one approach open (the design's
`hold_policy: keep_orthogonal_approach_first`, though you may pick a
different deterministic tie-break if you can justify it — document your
choice).

**Before implementing, resolve the design's own flagged unknown** (§5.1,
"what step 6 needs that does not exist today" and §7's "not confident about"
item 1): can `scripts/dfhack/df-overseer-reachability.lua`'s existing
tri-state reachability helper answer a hypothetical ("if these tiles became
walls, is this other tile still reachable") without mutating the map? Read
that file first. If yes, use it. If no, you have two honest choices and
should pick and document one, not invent a third without saying so:
(a) a narrower, conservative check — refuse a target if an exposed
economic ore tile's only open neighbours (checked live, not hidden ones) are
this step's own build targets, without a full pathfinding hypothetical; or
(b) designate-check-undo (build the construction, immediately verify with a
real reachability read, deconstruct and refuse the ones that fail). Prefer
(a): it never mutates the map to find out, matching this repo's read-then-act
discipline. State your reasoning either way in this handoff's Result section.

### 2. `item_present` (haul-before-seal)

Before designating a wall on any target tile, check whether an un-hauled
item sits on it (`dfhack.maps.getTileBlock`/an occupancy check, or iterate
`df.global.world.items.all` filtered to that tile the way earlier live
debugging in this stream already did — see `Working.md`'s boulder-yield
paragraph for the exact pattern). If an item is present, hold that target
with a reason naming the item (not a coordinate — this repo's coordinate
rule applies to every agent-facing string). This one is simpler and has no
open technical question; build it first if you want an early win before
tackling `keeps_access`'s reachability question.

## What "hold" means here, concretely

`build_construction` already has a `refused` list (tiles refused before
designation, e.g. "still a wall, not yet mined") and a per-target `results`
list. Add a third bucket, `held`, structurally different from `refused`:
`refused` means "this input is wrong, fix your call"; `held` means "this
input is fine, but designating it now would cause a specific, named harm, try
again once that changes." Both a dry run and a real run should report holds
identically (a hold is not a run-level failure, `ok` stays true, `CR_OK`);
only actually-held targets are skipped, the rest of the step proceeds
normally. Follow this file's own existing `apply_single_cell`/`nn`/`encode`
conventions rather than inventing new response shapes.

## Explicitly out of scope for this handoff

- The `from_step`/explicit-targets refactor (design §5.1 point 4's "doorway
  hazard": `build` today treats every open ring tile as a candidate, which
  would wall a room's own doorway). That needs the project/step data model
  from a separate, parallel stream (`handoffs/2026-09-28-dfqueue-project-step-schema.md`)
  to hand `build` its targets explicitly. Do not attempt it here. If you spot
  it live-testing, note it in your Result section, do not fix it.
- `dfqueue`, `conductor/`, `blueprints/templates/` — a parallel stream owns
  the schema; do not touch it, and do not add a project/step concept here.
  This handoff's guards are pure tool-layer refusals with no persistent
  record beyond the existing `held`/`refused` response shape.
- `building.build`'s own separate `economic_uses` bug — a third parallel
  stream owns that (`handoffs/2026-09-28-building-economic-uses-fix.md`).

## Rules

- `git merge --ff-only main` first.
- New offline `lupa` tests for both guards, extending
  `tests/lua_stubs/dfhack_surface_vein_world.lua`'s sibling stub for
  construction (check for an existing `tests/lua_stubs/dfhack_construction_*`
  file first) — cover: a build call that would seal reachable ore (held, with
  a reason), one that would not (all pass), an item present on a target
  (held), and the "no reachability answer" (`unknown`) case holding rather
  than guessing pass. This codebase's own established risk (`Working.md`,
  repeated twice already this stream) is a fake DFHack world modelling the
  wrong API shape and passing anyway — if you must guess at any DFHack API
  shape not already used elsewhere in this repo, mark it clearly as
  unverified in a comment, the same way `df-overseer-construction.lua`
  already does, and say so in your Result section so the orchestrator can
  live-verify before trusting it.
- No live mutation. If you want to confirm anything against the real fort
  (e.g. the reachability helper's actual signature), read-only
  `dfhack-run` calls only, via `scripts/vm-ssh.sh df '...'`. Do not touch
  buildings 18-22 or job 2705 (already handled, holding correctly).
- No em dashes in prose. No attribution lines in any commit.
- Ambient `python -m pytest` with `lupa` on `PYTHONPATH` should stay green;
  rerun and report the count.
- Commit as you go (`streams commit as they go`). Stop and report on any
  permission refusal.
- Fill in this handoff's own Result section: what you built, which of (a)/(b)
  you picked for `keeps_access` and why, test counts, anything you found but
  did not fix (list it plainly, do not silently drop it).

## Result

**Status: done.** Both guards built in `scripts/dfhack/df-overseer-construction.lua`'s
`build_construction`, as pure tool-layer refusals, no schema or `dfqueue`
change. Commit `f65d923` on this branch (`worktree-agent-a4614d85a3d5698a6`).

**What was built:**
- `item_present`: scans `df.global.world.items.all` for a fort-owned item
  (trader/garbage_collect/removed excluded, the same three-flag check
  `df-overseer-well.lua`'s `is_fort_owned_item` already uses) sitting on a
  candidate target's tile, via `dfhack.items.getPosition` (an
  already-verified call site elsewhere in this repo: stockpile.lua,
  stocks.lua, trees.lua, well.lua, workshop.lua, sampler.lua). Holds the
  target and names the item type, never a coordinate. A read failure on the
  item scan holds too (`unknown`, never a silent pass).
- `keeps_access`: for every exposed, not-hidden, still-WALL ore/gem tile
  orthogonally adjacent to any of the step's own build targets, reads that
  ore tile's own four orthogonal neighbours live. If at least one open
  neighbour is not one of this step's targets, the ore stays reachable
  regardless: pass. If every currently-open orthogonal neighbour of that ore
  tile IS a target, holds just one of them (fixed N,E,S,W tie-break) to keep
  one approach open; the rest of the step's other targets proceed. Diagonal
  neighbours are never trusted as an escape route or held against (see
  below). An unreadable (not hidden) neighbour holds defensively rather than
  assuming it is a safe escape.
- `held`, a new bucket in `build`'s result, structurally separate from
  `refused` (bad input) and `results` (designated): `"ring tile N: held
  (item_present|keeps_access) -- <reason>"`. Both guards run regardless of
  `dry_run` (they read live world state either way), so a dry run and a real
  run report holds identically. `item_present` runs first (no open technical
  question, cheaper), `keeps_access` second, over whatever survived
  `item_present`.

**(a) vs (b), and why (a):** picked **(a)**, the narrower conservative
check, no map mutation. Read `df-overseer-reachability.lua` in full first:
every exported function (`resolve_group`, `reachable_between`,
`group_matches`) resolves against the world's *own current*
`dfhack.maps.getWalkableGroup` cache. There is no parameter anywhere in that
file, or any hypothetical-obstacle pathfind call anywhere else in this repo,
for "pretend tile X is a wall, is Y still reachable". It genuinely cannot
answer the hypothetical the design's step 6 wanted, not without actually
building the wall and re-reading (option (b)), which would mean this exact
guard mutating the map to decide whether to mutate the map, contradicting
this same file's own header discipline ("ORDER IS ENFORCED BY WHAT `build`
READS, NOT BY BOOKKEEPING" -- never guess, but also never act-then-check).
So `keeps_access` does not call `df-overseer-reachability.lua` at all; it is
a self-contained live neighbour scan using only `tile_read`/`decode_vein_tile`
(reached via the existing `surface_hooks()` upvalue extraction, same as
`mine_vein`/`build_construction` already use).

**Deliberate narrowing versus the design's yaml sketch** (documented in the
code, `research/2026-09-28-job-dependency-graph.md` section 4.2): the
design's `protects:` list also names `pending_designations` (a queued dig/
channel/smooth/engrave elsewhere, mirroring `suspendmanager`'s
`ERASE_DESIGNATION`). Not built here -- it needs the project/step model the
parallel `dfqueue` schema stream owns, not a tool-layer read. Only the
ore/gem case this handoff asked for is built.

**Orthogonal-only, on purpose:** the design's own section 7 point 2 flags
"whether a miner can dig from a diagonal neighbour" as unverified. This
guard never relies on that assumption in either direction -- it only ever
trusts, or proposes holding, an orthogonal neighbour of an ore tile, never a
diagonal one. This also means the guard is deliberately less thorough than
a full 8-neighbour check would be (a diagonal-only escape route would not be
recognised as one, and diagonal ore exposure this step doesn't touch is
never scanned at all); flagging this rather than silently claiming full
coverage.

**Unverified DFHack API shapes used, flagged per the handoff's instruction:**
`dfhack.items.getPosition` and the `item.flags.{trader,garbage_collect,
removed}` triad are NOT new here -- both are already live call sites
elsewhere in this repo (see above), so this stream treats them as
established, not fresh guesses. `df.item_type[item:getType()]` (the ordinal
-> token-name round trip `item_present`'s reason text uses) mirrors
`df-overseer-construction.lua`'s own pre-existing, already-flagged-unverified
`decode_item_material`/`dfhack.matinfo.decode` caveat in spirit, but was not
independently re-verified live this stream either; if it reads wrong on the
real install, only the item's *name in a hold reason* is affected, not
whether the hold fires (the hold fires on flag state alone).

**Tests:** extended `tests/lua_stubs/dfhack_construction_world.lua` with a
fake item world (`ITEMS`, `add_item`, `df.global.world.items.all`,
`dfhack.items.getPosition`, `df.item_type` enum) and added 5 new lupa tests
to `tests/test_construction_lua_logic.py` (14 total in that file, all
passing): a build held by `keeps_access` with a named-mineral reason, a
build kept clear because a second open approach survives, an `item_present`
hold naming the item type (and asserting no coordinate leaks into the
reason string), a trader/garbage-collect item correctly ignored so the build
still proceeds, and an unreadable ore-neighbour holding rather than guessing
pass. Ambient `python -m pytest` (repo root, `lupa` importable): **1935
passed, 3 skipped** (up from the `Working.md`-cited 1845/3 baseline by
exactly the 90 tests other already-committed work since 2026-09-25 added
plus this stream's own 5; nothing here reduced the count). `dfmcp/tests` was
not touched and was not re-run (out of scope, no `dfmcp` file touched).

**Found but not fixed, noted per the handoff's instruction, not silently
dropped:**
- The `from_step`/explicit-targets refactor (the doorway hazard: `build`
  still treats every currently-open ring tile as a candidate, which would
  wall a room's own doorway) is unchanged. Explicitly out of scope per this
  handoff; needs the project/step data model from the parallel `dfqueue`
  schema stream.
- `building.build`'s own separate `economic_uses` bug is untouched (a third
  parallel stream owns it).
- No live VM verification was performed or attempted (out of scope per the
  handoff's "no live mutation" rule; only read-only `dfhack-run` calls were
  even permitted, and none were needed since nothing here required
  confirming an API shape not already used elsewhere in this repo). The
  orchestrator should live-verify `item_present`'s and `keeps_access`'s
  actual behaviour against the real fort before trusting either guard on a
  real `build` call, per the handoff's own caution about a fake world
  modelling the wrong API shape and passing anyway.
