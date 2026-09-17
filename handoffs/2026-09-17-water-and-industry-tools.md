# Handoff: water and early-industry tools (zones, tree felling, workshops, work orders, well)

**Dispatched** 2026-09-17 by the orchestrating session. **Agent:** `executor`,
Sonnet, worktree-isolated. **User go-ahead:** "yeah true. we need all these
tools" (2026-09-17). Local code only: no deploy, no fort mutation.

## Why this stream exists

The fort has no drink it can reach. Each pond is a basin of 6-7/7 water in
ramps at z168 with open air above at z169 (`research/2026-09-17-pool-reachability.md`,
**read its CORRECTION note first**). The user's plan, in order: a Water Source
zone on the water; if that fails, a ramp to reach the water level; if that
fails, a well. No agent tool can do any of it, nor the industry the well
depends on. Verified live by the orchestrator today:

- `df.civzone_type.WaterSource` (82) exists; quickfort `#zone` symbol `w`
  places it (`hack/scripts/internal/quickfort/zone.lua`). The fort has 0 zones.
- **Well:** quickfort `#build` symbol `l`, valid on an `EMPTY` or `RAMP_TOP`
  tile that is floor-adjacent (`is_tile_empty_and_floor_adjacent`,
  `internal/quickfort/build.lua`), so a well on a pond-edge ramp top next to
  surface floor is valid without a bridge.
  `dfhack.buildings.getFiltersByType({}, df.building_type.Well, -1, -1)`
  returns **BLOCKS, BUCKET, CHAIN, TRAPPARTS** (a mechanism), one each.
- **Fort stock** (fort-owned, visible tiles): bucket 3, chain 3, logs 3,
  boulders 0, blocks 0, mechanisms 0; about 1,593 visible trees. Block and
  mechanism need stone, so stone must be dug (z167 and below; z168 is soil).

A water-source zone test is **running live right now** (another executor,
`handoffs/2026-09-17-water-source-zone-test.md`): the fort may be unpaused
while you start. Do not pause, unpause or write anything; keep probes light;
don't assume the fort is paused until that test's Result is appended.

## Read first

`CLAUDE.md`, `docs/TRAPS.md`, `memory/dfhack-environment.md` (the `workorder`
note), `research/2026-09-16-food-and-drink-logistics.md` (its proposed
`manager.*` tool shapes, §4), `research/2026-09-16-player-visibility.md`
(bottom line), the act/sense rule (register 2026-09-16, "acting on hidden tiles
is allowed, sensing them is not"), `handoffs/2026-09-16-farm-and-still-tools.md`
and its Result (the idiom to copy: landmark-relative targeting, `quickfort run
-c`, dry-run default, requirements report, JSON out, no coordinates to the
model), and the existing `df-overseer-farm.lua`, `-workshop.lua`,
`-openarea.lua`, `-landmarks.lua`, `-stocks.lua`.

## Build

Every write defaults to **dry run** (resolve, validate, report exactly what it
would do); a real write needs an explicit flag. Every command reports its
prerequisites as data (labors and citizens holding them, tools like an axe,
materials by fort-owned count), so a caller can see why something cannot
happen yet. No coordinates cross the model boundary.

1. **Zones** (`df-overseer-zone.lua`, new): `zone.find KIND near LANDMARK` and
   `zone.place`. At least `water_source`, targeting **revealed water tiles**
   (report depth and stagnant/salt, which a player sees), with the z-level
   chosen from where the water actually is. Structure it so pasture, meeting
   area and others are a table entry later, not a rewrite. Placed zones become
   addressable by name, as landmarks do for buildings.
2. **Tree felling** (`df-overseer-trees.lua`, new): `trees.find near LANDMARK`
   (count, distance band, reachable; revealed trees only) and `trees.fell N
   near LANDMARK` (designate the nearest N for chopping; verify which API or
   quickfort `#dig` symbol this build uses). Report axes owned and woodcutting
   labor holders.
3. **Workshops:** extend `df-overseer-workshop.lua` with `mason`, `mechanic`
   and `carpenter`, reusing its existing find/build and requirements report
   (building material: logs or boulders, whichever the game accepts; verify).
4. **Work orders** (`df-overseer-orders.lua`, new): `orders.list` and
   `orders.create JOB AMOUNT` for at least stone blocks, mechanisms, barrels
   and brew drink, via `workorder.lua`'s `create_orders()` (verify the call
   shape on this install). Verify from source and a live read whether orders
   need an appointed manager or workshop profile in this build, and report it
   as a prerequisite. `orders.cancel ID` for reversibility.
5. **Well** (`df-overseer-well.lua`, new): `well.find near LANDMARK` (valid
   pond-edge tiles by the rule above, only over revealed water) and
   `well.build`, with the BLOCKS/BUCKET/CHAIN/TRAPPARTS requirements report.
6. **Stone access, check only:** confirm the existing dig tools can propose a
   stair down from the z168 farm-room area into z167 stone under the act/sense
   rule. If they cannot, say what is missing; do not build it in this stream.

## Tagging, roles, tests

Tag every command with `knowledge_scope` in `scripts/dfhack/TOOLS.yaml` (the
registry refuses to load otherwise); expected `player_visible` or
`player_derivable`, justify each. **Finds and lists** go on the architect's
read list; **writes** on the Overseer's write list only (the pinned structural
property). Registry and roster tests must pass. Add tests where the existing
test suite covers tool registration.

## Verification without mutating the fort

Verify every find and every dry run live against the real fort, read-only.
Real zone placement, felling, building and order creation are **not** yours to
run: the orchestrator runs them with the user aware.

## Constraints

- Branch from **current `main`** (the audit stream broke `main` by branching
  early). Commit on your worktree branch as you go.
- Ambient suite on `main`: **291 passed, 1 skipped**; `.venv-dfmcp` `dfmcp/tests`
  **162**. `.venv-dfmcp` does not exist in your worktree: say which
  interpreter you used, and never report a count from a tree lacking today's
  merged work.
- Traps: `designation.liquid_type` is a boolean; items use `flags.trader` and
  `stack_size`; `getWalkableGroup` takes `xyz2pos(x,y,z)`; multi-line Lua goes
  in a file run with `dfhack-run lua -f` (inline `-e` with newlines fails);
  **never set DFHack globals** (`local` only). Delete `/tmp` probes; never
  leave files under DF's script paths.
- VM access: `.env` keys `DF_VM_IP` (strip any `/24`) and `DF_SSH_KEY`, user
  `df`, read those keys only. No hostnames, addresses or tokens in anything
  you write.
- Do not edit `Working.md`, `decisions/`, `ROADMAP.md`, `CLAUDE.md`, `memory/`,
  `research/`, `doctrine/`.

## Touched surfaces

`scripts/dfhack/df-overseer-{zone,trees,orders,well}.lua` (new),
`scripts/dfhack/df-overseer-workshop.lua`, `scripts/dfhack/TOOLS.yaml`,
`agents/architect/tools.yaml`, `agents/overseer/tools.yaml`, new blueprints
under `blueprints/` and `blueprints/README.md`, `tests/`, `dfmcp/` tests only if
needed, this doc.

## Report back

Per command: what it does, its tag and role placement, and its live read or dry
run result against the fort. What the game requires for orders (manager or
not), felling (axe, labor) and each workshop's building material, verified or
not. The stone-access answer. Test counts and interpreter. Branch name.

## Result

**Branch**: `worktree-agent-a5bb38947b02b37a1`, based on current `main`
(rebased via `git merge --ff-only main` before adding code, since the
worktree had been created before the farm-and-still-tools and
water-source-zone-test streams merged). Committed in small steps: tool
files, workshop.lua extension, TOOLS.yaml/allowlists, tests, blueprints.

Every command below was verified live against the real fort, read-only,
via `dfhack.internal.addScriptPath('/tmp/...')` shadowing a scoped `/tmp`
copy (the same technique `handoffs/2026-09-16-farm-and-still-tools.md`
used), never the real deploy path. **A real trap found this session**:
`reqscript`'s module cache is keyed by name across separate `dfhack-run`
invocations in the same DFHack process. The sibling stream had already
`reqscript('df-overseer-workshop')`'d the REAL deployed file earlier the
same day (building its own still), so shadowing that name via
`addScriptPath` silently returned the stale, pre-extension module —
`workshop.find mason` reported "unknown workshop kind" even though the
code on disk was correct. Re-verified by copying the same file under a
throwaway name (`df-overseer-workshoptest`) never reqscript'd before,
which loaded and behaved correctly. Anyone using this verification
technique after the real script has ever loaded once needs to know this.

The fort was also a genuinely moving target for part of this run (a
sibling stream built a farm plot and a Water Source zone, and ran a
supervised unpause, per the mid-run coordinator notice) — noted per
command below where it mattered.

### `zone.find`/`zone.place` (new, `df-overseer-zone.lua`)

`knowledge_scope: player_derivable`. `find` on both architect and
overseer's read list (matching `farm.find`); `place` on overseer's write
only, denied to architect.

`zone.find water_source -1 "Embark Site" 30` (live): found **5 real water
bodies** matching `research/2026-09-17-pool-reachability.md`'s
independently-derived figures exactly — 27, 31, 4, 13, 24 tiles, depth
6-7/7, all stagnant, none salt. The nearest (27 tiles, `dims [7,7]`)
resolved `near_landmark` to **"Activity Zone #1"** — the sibling stream's
own Water Source zone, placed on the water tiles themselves (confirmed by
the coordinator's own mid-run notice: `is_valid_zone_tile` is hidden-only,
matching this file's own source-read). `zone.place` was only exercised
dry-run (mutation forbidden): resolves and reports correctly; the real
path (a dynamically generated throwaway `#zone` blueprint, `io` write
confirmed available in principle via a read-only open of an existing
file, never a write) is UNTESTED live.

### `trees.find`/`trees.fell` (new, `df-overseer-trees.lua`)

`knowledge_scope: player_derivable`. Same read/write split as above.

`trees.find 0 "Embark Site" 30` (live): 154 revealed trees within radius
30 (12/34/108 across three 10-tile bands), all 154 reachable, `CUTWOOD`
labor held by 1 citizen, 2 fort-owned axe-family weapons. **Felling
mechanism**: `dfhack.designations.markPlant`, the exact primitive
quickfort's own `#dig` `t` symbol (`do_chop`) calls — confirmed from this
install's own source, not invented. Unlike mining, `do_chop` refuses a
hidden tile outright (no blind-designate case), so no act/sense asymmetry
applies here. **Axe**: this install's weapon itemdefs contain no plain
"AXE" — only `ITEM_WEAPON_AXE_BATTLE`/`_GREAT`/`_TRAINING` — so "owns an
axe" is reported as any weapon whose itemdef id contains "AXE" (2
fort-owned), flagged rather than assumed to be one canonical subtype.
`trees.fell` dry-run only; the real `markPlant` call is UNTESTED live.

### `well.find`/`well.build` (new, `df-overseer-well.lua`)

`knowledge_scope: player_derivable`. Same read/write split.

`well.find 0 "Embark Site" 30` (live): 5 real candidates, all near
"Activity Zone #1", depth 7/7, stagnant, not salt, `BUCKET` 3 / `CHAIN` 3
/ `BLOCKS` 0 / `TRAPPARTS` 0 fort-owned — matching the handoff's own
figures exactly. Mechanism: quickfort's own `is_tile_empty_and_floor_adjacent`
(`l` symbol, EMPTY/RAMP_TOP shape + floor-adjacent), read directly from
this install's `build.lua`, **plus** this project's own layered rule that
the tile directly below must be revealed water at least 3/7 deep (the
wiki's own well minimum, version-matched). `well.build` dry-run only; the
real quickfort call is UNTESTED live.

### `orders.list`/`orders.create`/`orders.cancel` (new, `df-overseer-orders.lua`)

`knowledge_scope: player_visible` (a manager-order list/queue is a real
screen a player sees, not derived geometry). `list` on both roles' read;
`create`/`cancel` overseer-write only, denied to architect.

`orders.list` (live): 0 orders queued, `manager_appointed: false`.
**Manager prerequisite, genuinely unresolved both ways**: `create_orders`
itself has no manager check in its own source at all, but
`dfhack.units.getNoblePositions` over every active unit found **zero
citizens holding the MANAGER position on Uniboslan today** (a
`world.entities.all` scan found a filled MANAGER assignment elsewhere, but
its histfig did not resolve to a live unit — an unrelated site, not this
fort). Whether DF's own engine validates an order into a real job with no
Manager appointed is **not verified** (would need an unpause, out of
scope). Reported as `manager_appointed` on every `list`/`create` call,
never enforced as a refusal. **Job types**, each live-verified against
the real `df.job_type` enum: `blocks`=80 `ConstructBlocks`,
`mechanisms`=139 `ConstructMechanisms`, `barrels`=125 `MakeBarrel`,
`brew_drink`=209 `CustomReaction` + `reaction_name=BREW_DRINK_FROM_PLANT`
(live-confirmed in `world.raws.reactions.reactions`' own `code` field — no
`job_type` named "Brew*" exists; brewing is a reaction, not its own job
type). `orders.create blocks 5`/`orders.create brew_drink 0` (both dry
run) resolved and reported correctly, `workshop_exists: 0` for both
(correct — no Mason's Workshop or Still exists yet). `orders.cancel
999999` (dry run) correctly refused "no manager order with id 999999".
The real `create_orders`/`erase`+`delete` calls are UNTESTED live; `cancel`'s
mechanism is inferred by convention (workorder.lua's own rollback pattern),
not independently proven.

### `workshop.find`/`workshop.build` extended (`df-overseer-workshop.lua`)

Same tags/roles as before (unchanged). `KIND` now also accepts
`mason`/`mechanic`/`carpenter` (`#build` symbols `wm`/`wt`/`wc`, labors
`MASON`/`MECHANIC`/`CARPENTER`, all read from source). **Building
material**: live-verified this session that
`dfhack.buildings.getFiltersByType` returns an identical generic
`flags2.building_material` filter (no `item_type`/`mat_type` at all) for
**all five** workshop kinds, not just the three new ones — this answers
the prior stream's own open "logs or boulders, whichever the game
accepts" question for real: **both, plus blocks, interchangeably**. Added
as a `building_material` field on every `requirements_for()` result
(`accepts`, `fort_owned` counts for `BOULDER`/`WOOD`/`BLOCKS`).
`workshop.find mason` at `LEVEL -1` near "Embark Site" returned `[]` —
**not a bug**: the sibling stream's own new 5x5 farm plot now occupies
that exact free floor. The same call at `LEVEL 0` (surface) returned 5
real candidates with a correct full report (`building_material`,
`labor: MASON`, `citizens_with_labor: 3`), confirming the extension end to
end. `workshop.build` for the three new kinds is dry-run-only verified,
same as still/kitchen already were.

### Stone access (item 6, check only — nothing built)

Live, read-only: `df-overseer-diggable find 1 1 -1 "Embark Site"` still
returns the same 5 SOIL candidates at z168 as the farm-and-still-tools
stream originally found (unchanged baseline). `df-overseer-diggable find
1 1 -2 "Embark Site"` (z167, the stone level under the farm room) returns
**`[]`**. **This is not a missing feature of the finder, it is a real
structural gap**: `borders_walkable_network`'s ring-adjacency check only
looks at the SAME z-level as the candidate box, and z167 has no walkable
tile anywhere yet (no stair has ever reached it), so nothing there can
ever satisfy that check regardless of how much diggable SOIL/STONE
material actually borders it. The existing dig tools have no notion of
"this tile is reachable because it sits directly beneath an already-
designated downstair" — a vertical-adjacency rule that simply does not
exist in `df-overseer-diggable.lua` today (its own header already names
this as v1's scope limit, "non-adjacent candidates are simply absent").
**What is missing, concretely**: either (a) a paired downstair(z168)/
upstair(z167) blueprint tool that designates both halves atomically and
trusts the pairing rather than re-checking z167's own (nonexistent)
network, mirroring the existing `starter-entrance-1x1`/`starter-connector-
1x1` pattern one level deeper, or (b) a vertical-adjacency rule added to
`borders_walkable_network` itself. Neither was built this stream, per the
brief's own instruction ("do not build it in this stream").

### Tests and interpreter

Ambient suite: **python 3.12.4** (no other interpreter available on this
worktree), **291 passed / 1 skipped → 294 passed / 1 skipped** (3 new
tests: registry mutates/knowledge_scope pins for all 9 new/extended ids,
and a role-allowlist test pinning the find/list read-both-roles,
write-overseer-only split). `.venv-dfmcp` does **not** exist in this
worktree (gitignored, created per-checkout) — no `dfmcp/tests` count is
reported from here; the constraint's own baseline (162) was not
re-verified and should not be assumed current for this tree without a
fresh venv build.

### Not done, by design

Real (non-dry-run) mutation of every write tool above: left to the
orchestrator, per the brief's own "Real zone placement, felling, building
and order creation are not yours to run." No deploy to VM 103. No
`ROSTER.yaml` change (the `quartermaster` role's own `blocked_on` note —
"Manager work orders... have no tool in this repo" — is now partly
stale, since `orders.lua` exists; flagging rather than editing, since
`ROSTER.yaml`/`Working.md`/`decisions/DECISIONS.md` are the
orchestrator's to update, not this stream's touched surfaces).
