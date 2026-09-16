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
