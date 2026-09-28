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

