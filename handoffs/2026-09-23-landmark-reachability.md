# Stream: reachability that means something, not "the middle tile is not standable"

**Written** 2026-09-23. **Status:** dispatched. **User go-ahead:** 2026-09-23,
"yeah id say so", after the Well read as unreachable from every direction.
**Offline only: do not touch VM 103 or VM 106.** A sibling stream
(`handoffs/2026-09-23-office-and-first-real-build.md`) is running the fort
right now and owns the live machine. Sonnet executor, worktree-isolated.
**No push. No attribution lines in any commit.**

## Why

`df-overseer-landmarks.lua` tags each exit with `walkable`, from
`dfhack.maps.canWalkBetween` on the two landmarks' **centroid** tiles. The
fort's Well reports `walkable: false` to all three of its neighbours. It is
not cut off. Live reads by the orchestrating session, 2026-09-23:

- the Well's own centre tile is a **RampTop**, which nobody can stand on, so
  every one of the eight tiles around it reports "cannot walk to the well
  tile";
- of the tiles around the Well, **four can walk to the Still**, so the Well is
  connected to the fort and is used the way wells are used, from a tile beside
  it.

So the flag currently answers "is the arbitrary middle tile standable and
connected", which is not the question any agent asks. Every landmark whose
centre tile is not standable is affected: anything over a channel, a stair, a
ramp, a bridge. The failure is the dangerous kind, a confident false negative:
an agent reading it would conclude the well is unreachable and dig a corridor
to reach something it can already reach. The file's own header already admits
the centroid may not be standable and that a failure is reported as
`walkable=false`; that admission is the bug.

## What to do

1. **Use walkable groups.** DFHack tags each tile with a walkable group id
   (`dfhack.maps.getWalkableGroup`, confirm the exact accessor against the
   installed DFHack's own lua and scripts before using it). Two standable
   tiles with the same non-zero group are connected; different non-zero groups
   are definitely not. This is cheaper and more exact than a path call. Verify
   what a group id of 0 means on this version and treat it honestly.
2. **Pick a tile that can actually be stood on.** For each landmark, choose a
   representative standable tile belonging to it, falling back to the tiles
   immediately around it (which is how a well, a stair or a bridge is really
   used), and only then to nothing. Report which case was used, so a reader
   can tell "reachable from beside it" from "reachable at it".
3. **Three states, not two.** `reachable`, `unreachable`, `unknown`, with a
   short reason on the last two. Never report "unknown" as "unreachable"
   again. Keep the old boolean field alongside only if something depends on
   it, and say what depends on it.
4. **One shared helper**, used by every tool that answers a reachability
   question: `df-overseer-landmarks.lua`, `df-overseer-connectivity.lua`,
   `df-overseer-threat.lua`'s reachability admission rule, and any other
   caller you find. Do not copy the logic per tool. Check whether the threat
   tool's own rule changes behaviour under the fix and say so plainly: that
   rule decides what the fort is told about hostiles, so a change there is a
   finding for the user, not a silent improvement.
5. **Keep it coordinate-free at the decision layer.** The tools may read
   tiles internally; their output must stay free of raw coordinates, per
   `CLAUDE.md` and `docs/PURPOSE.md` design commitment 1.
6. **Tests**, including a regression for the Well's exact shape: a landmark
   whose centre tile is not standable but whose surrounding tiles are
   connected must report reachable, not false. Both suites green: ambient
   `python -m pytest` (1266 passed / 3 skipped before you) and
   `.venv-dfmcp/Scripts/python -m pytest dfmcp/tests` (652 before). Report the
   new counts.
7. **Write down the limits you did not fix**, for the later design
   conversation: standing room at the destination, doors and hatches that can
   be locked or forbidden, a route that exists but is absurdly long, flooding
   and other state that changes reachability over time, and reachability for
   a specific unit rather than in general. Put this in the Result, not in new
   code.

## Hard lines

- **Offline only.** No ssh, no VM, no deploy, no live DFHack call. Deploy is a
  separate decision after the fort run finishes. Verify DFHack API claims
  against the installed copy's own source under
  `/opt/df/game/hack` **only if you can read it without touching the VM**;
  otherwise use upstream source and mark the claim as not install-confirmed.
- No model call. No armok capability, nothing a player could not know.
- Secrets by key only, never printed. Never print an IP or hostname.
- Do not write `Working.md`, `decisions/` or `memory/`. No em dashes.
- Commit as you go and fill in the Result section.

## Touched surfaces

`scripts/dfhack/df-overseer-landmarks.lua`,
`scripts/dfhack/df-overseer-connectivity.lua`,
`scripts/dfhack/df-overseer-threat.lua`, a new shared Lua helper if that is
the right shape, `TOOLS.yaml`, the matching dfmcp schema and tests, tests
under `tests/` and `dfmcp/tests/`, this doc.

## Result

**Status: done, offline, not deployed.** Branch: this worktree's local
history (see the executor's own report for the exact commits); no push, no
VM touched.

**What changed.** New shared library `scripts/dfhack/df-overseer-
reachability.lua` (module-only, no CLI surface, so no TOOLS.yaml entry --
same convention as `df-overseer-textutil.lua`), exporting three functions:
`resolve_group(x,y,z)` (a raw position in, `{group, how}` or `nil, reason`
out, never a coordinate in the result: tries the position itself, falls back
to its immediate 8-neighbour ring, else gives an honest "unknown" reason),
`reachable_between(ax,ay,az, bx,by,bz)` (tri-state `status` of "reachable" /
"unreachable" / "unknown", with `reason` on the last two and `from_via`/
`to_via` reporting "at" vs "adjacent" per item 2's instruction to say which
case was used), and `group_matches(x,y,z, target_groups)` (for threat.lua's
"does this exact unit tile touch one of these groups" question, which can't
substitute a neighbour tile for the answer the way landmark anchoring can).

Wired into all three named files:
- `df-overseer-landmarks.lua`'s `build_exits`: each exit's `walkable` bool
  (from `canWalkBetween` on the two CENTROID tiles) replaced with
  `reachability` (tri-state string) + `reachability_reason` + `from_via`/
  `to_via`.
- `df-overseer-connectivity.lua`'s `check_reachable`/`check_reachable_units`:
  `{reachable: bool, from_group, to_group}` replaced with the tri-state
  result shape directly from `reachable_between`.
- `df-overseer-threat.lua`'s `citizen_groups()` and the candidate scan loop:
  both now resolve via `resolve_group`/`group_matches` instead of a bare
  `getWalkableGroup(x,y,z) ~= 0` on the exact tile.

Old boolean fields were **removed, not kept alongside** the new tri-state
fields: grepped the whole repo (`scripts/dfhack/`, `dfmcp/`, `tests/`,
`docs/`, `research/`) for `.walkable`/`exit.walkable`/`"walkable"` and for
any Python code reading `check_reachable`'s `reachable`/`from_group`/
`to_group` fields -- nothing in this repo depends on either, including
`df-overseer-overview.lua` (which passes `list_landmarks()`'s output through
wholesale, no field-specific logic). Per the handoff's own instruction
("keep the old boolean alongside only if something depends on it, and say
what"): nothing does, so nothing was kept. A model-facing consumer outside
this repo (a prompt template, an agent's own learned expectations) could in
principle have depended on the field name/type, but nothing in-repo records
or enforces such a dependency.

**DFHack API verification, stated precisely.** Offline stream, no VM, no
live DFHack call -- nothing here is freshly install-confirmed this session.
But nothing here is a NEW accessor either: `dfhack.maps.canWalkBetween`,
`dfhack.maps.getWalkableGroup`, `dfhack.maps.getTileType` and
`df.tiletype.attrs[t].shape` were all already live-verified call sites in
this repo before this stream (connectivity/openarea/diggable/chokepoints/
threat for the first two; well/farm/diggable for the second two), and
`df.tiletype_shape.RAMP`/`.RAMP_TOP` are exactly the enum members
`research/2026-09-17-pool-reachability.md`'s own live probe (against this
exact install, DFHack 53.16-r1.1) used to classify tiles. This stream
reorganised already-verified primitives into one shared file; it did not
invent or newly confirm an accessor. `dfhack.maps.getWalkableGroup`
returning 0 for RAMP/RAMP_TOP regardless of true walkability is that same
research doc's own live-verified finding (74/98 tiles directly adjacent to
a group-11 tile yet reading group 0 themselves), reused here as the second,
independent motivation for the ring fallback, not re-derived.

**Threat tool's reachability rule: yes, it changes, and it is a real
finding, not a silent improvement (per item 4's explicit instruction).**
`citizen_groups()` previously called `getWalkableGroup` on each citizen's
own tile directly and silently dropped any citizen whose tile read group 0
-- which, per the research doc, includes ordinary RAMP tiles (any dwarf on
a ramp between two floors, not an edge case). Now every citizen's real group
is resolved via the neighbour-ring fallback before being dropped. This can
only ADD groups to the citizen-group set (never remove one), and the
candidate scan loop's `shares_group` check can only gain matches the same
way (`group_matches`'s own ring fallback). **Net effect: `threat.lua scan`
becomes strictly more permissive about `shares_walkable_group_with_citizens`
-- it can now flag a reachable hostile it previously missed (the same
"reachable but unflagged" failure class the kea-attack incident this file
was built for), it cannot newly exclude one it previously caught.** Each
affected result entry now also carries `reachable.shares_walkable_group_via`
("at"/"adjacent") and a `"(via_adjacent_tile)"` suffix in `why`, so a reader
can tell which case applied. This has **not been run against the live
fort** (offline stream) -- whether Uniboslan currently has any citizen or
threat candidate actually standing on a RAMP/RAMP_TOP tile at scan time,
and so whether this changes `scan`'s real output right now, is unknown and
untested; the change is in the code, not yet observed live.

**Tests.** No Lua interpreter is available in this environment (checked:
no `lua`/`lua5.1`/`lua5.3`/`luajit` on PATH), so nothing here executes the
real `.lua` file's bytes -- consistent with this repo's own existing
precedent (`tests/test_game_text_utf8_helper.py` is grep-style for the same
reason). Two new files:
- `tests/test_reachability_helper_usage.py`: structural guard, same pattern
  as the game-text helper test -- the three named files reqscript the
  shared helper and no longer call the raw `canWalkBetween`/
  `getWalkableGroup` primitives themselves (a positive control confirms the
  helper itself still does, so the check isn't vacuous), plus shape-change
  assertions (`walkable = ...` gone, `reachability`/`reachable_between(`/
  `resolve_group(`/`group_matches(` present).
- `tests/test_reachability_ring_logic.py`: a hand-written Python PORT of
  `resolve_group`/`reachable_between`/`group_matches`'s control flow
  (explicitly labelled as a port, not an execution, with a drift guard that
  re-reads the real .lua file's own constants), exercising the Well's exact
  regression shape from this handoff's own "Why" section (centroid a
  RAMP_TOP/group 0, 4 of 8 neighbours sharing the Still's group, 4 genuinely
  not standable) plus the unknown-vs-unreachable distinction and the
  threat-tool ring fallback. **What this proves and doesn't**: that the
  ALGORITHM this handoff specifies is sound against the stated regression
  case; it does NOT prove the deployed Lua bytes behave identically (that
  needs a live DFHack run, out of scope offline). Read this file's own
  docstring before trusting it further.

Both suites green, new counts: ambient `python -m pytest` **1281 passed, 3
skipped** (was 1266/3, +15 new tests, all in the two new files above,
nothing else changed count). `.venv-dfmcp` did not exist in this fresh
worktree; created it per `dfmcp/requirements.txt`'s own instructions
(`python -m venv --system-site-packages .venv-dfmcp` +
`pip install -r dfmcp/requirements.txt`, all local/offline, no VM touched)
and confirmed the baseline first (**652 passed**, matching the handoff's
stated pre-count exactly) before and after this stream's changes (dfmcp/
was not touched, so the count is unchanged at **652 passed**).

**Not deployed, marked as such.** `TOOLS.yaml`'s `landmarks.list`,
`landmarks.get`, `connectivity.check`, `connectivity.check-units` and
`threat.scan` entries were updated: `live_deployed: false` and `verified:
unverified` where the result shape changed (landmarks/connectivity), plus an
UPDATE note on `threat.scan` describing the behaviour change -- VM 103's
deployed copies still run the pre-fix code and old field shapes. Deploy is
explicitly a separate, later decision per the handoff's own hard line.

**Limits deliberately not fixed here, for the later design conversation
(per item 7):**
- **Standing room at the destination.** `resolve_group`/`reachable_between`
  only ask "is there a standable, correctly-grouped tile here or beside
  it" -- never whether a unit can actually fit/act there (occupied by
  another unit, a built object, insufficient floor for a multi-tile job).
- **Doors and hatches that can be locked or forbidden.** Not modelled at
  all; a tile behind a forbidden door reads the same as an open one here,
  because `getWalkableGroup` itself doesn't distinguish that state from
  this project's own prior research (not re-checked this stream).
- **A route that exists but is absurdly long.** `reachable_between` answers
  yes/no on shared group membership, never a path length or cost -- two
  landmarks in the same group could be connected only by a route around
  the entire map.
- **Flooding and other state that changes reachability over time.**
  `getWalkableGroup` is a live pathing cache ("only updated while the game
  is unpaused", already documented in this codebase); nothing here freshens
  it, caches it, or accounts for it going stale between a read and an
  action.
- **Reachability for a specific unit**, rather than in general. Neither
  `resolve_group` nor `group_matches` account for burrow restrictions,
  civilization/caste movement rules, or an individual unit's own
  capabilities (flying, swimming, caged) -- `threat.lua`'s own still-open
  "BLIND SPOT" note on flying/swimming creatures (group 0 in open air/deep
  water, not rescued by the ring fallback since neighbouring tiles there
  are typically also group 0) is the concrete instance already on record.
- **Other callers of the same raw pattern, found but explicitly NOT
  migrated this stream** (outside the handoff's own touched-surfaces list,
  so left alone rather than risking untested scope creep in a single
  offline stream): `df-overseer-breach.lua`, `df-overseer-harvest.lua`,
  `df-overseer-trees.lua`, `df-overseer-openarea.lua`,
  `df-overseer-diggable.lua`, `df-overseer-chokepoints.lua`,
  `df-overseer-building.lua`, `df-overseer-zone.lua` and
  `df-overseer-stocks.lua` all call `dfhack.maps.getWalkableGroup` directly
  (confirmed by grep this session) and could have the same RAMP/RAMP_TOP
  blind spot on their own reachability-adjacent logic. A real follow-up,
  not chased here.
- **RING_RADIUS is fixed at 1** (the immediate 8-neighbour ring only), per
  the handoff's own "immediately around it" wording -- deliberately not a
  flood-fill or wider search, so a landmark whose nearest standable tile is
  2+ tiles from its centroid (unusual, but possible for an oddly-shaped
  burrow) still reports "unknown" rather than "reachable". Not tuned
  against a live fort this stream.
