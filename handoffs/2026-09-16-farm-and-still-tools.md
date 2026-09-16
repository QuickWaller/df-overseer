# Handoff: farm plot and still tools, and the dig finder's act/sense correction

**Dispatched** 2026-09-16 by the orchestrating session. **Agent:** `executor`,
Sonnet, worktree-isolated. **Status:** dispatched.

## Why this stream exists

The fort (Uniboslan, 15 citizens) owns 24 units of food and **no drink**, and
has no farm plot, still, kitchen or workshop. The user approved building farm
tools next. The agents' write surface today is dig, open-area build, landmark
build and labor set, so no agent can make the fort produce food.

Three facts verified live by the orchestrator today reshape what "farm tools"
has to mean:

1. **All six seed types the fort owns are subterranean crops**
   (`SUBTERRANEAN_WATER` biome in their plant raws): plump helmet, pig tail,
   cave wheat, sweet pod, quarry bush, dimple cup. **None grows on an outdoor
   plot.** A farm on the open surface grows nothing this fort can plant.
2. **Terrain:** the surface floor is **z169** (outside). **z168 is a single
   level of SOIL wall** (not outside, not yet revealed). **z167 and below is
   stone.** So a room dug into z168 is an underground, soil-floored space:
   the valid farm for these crops, and the user's own habitual method ("dig
   into soil and put a farm there").
3. The knowledge-scope audit deployed today made `find_diggable_area` require
   **every candidate tile to be visible**. z168 is entirely unrevealed, so the
   finder currently cannot propose the farm room at all.

A parallel researcher is producing `research/2026-09-16-food-clock-and-farm-lead-time.md`
(consumption rate against farm lead time). Do not wait for it; do not touch it.

## Read first

`CLAUDE.md`, `docs/TRAPS.md`, `research/2026-09-16-player-visibility.md`
(bottom line, §1, §4, §9), `research/2026-09-16-food-and-drink-logistics.md`
(its proposed tool shapes, §4), `research/2026-09-16-opening-priority-ladder.md`
(the farm rung), `handoffs/2026-09-16-knowledge-scope-audit.md` and its
Result, and the existing `scripts/dfhack/df-overseer-diggable.lua`,
`df-overseer-openarea.lua` and `df-overseer-landmarks.lua` for the idioms
(landmark-relative targeting, `quickfort run -c`, JSON out, no coordinates to
the model).

## Part 1 — correct the dig finder: acting on hidden tiles is allowed, sensing them is not

The audit's rule conflated **acting** with **knowing**. A vanilla player
designates digs into unrevealed ground constantly; what they cannot do is see
what is inside it first. The policy (register 2026-09-16, "Agents may only
know what a vanilla player could know") is about knowledge. The orchestrator's
reading, flagged to the user for confirmation:

- **Allowed:** proposing and designating a dig that includes hidden tiles.
- **Not allowed:** using any property of a hidden tile to choose, rank,
  filter or describe a candidate: its material, its shape (whether it is
  wall or an open cavern), its contents. A candidate whose interior is hidden
  must be described only by what a player could know: its size, its position
  relative to a landmark and to revealed ground, its z offset from the
  surface, and whatever the embark screen lets a player know exists (e.g.
  "the site has soil").

Change `df-overseer-diggable.lua` accordingly. Returned `material` must be
omitted or `unknown` for hidden tiles. Anchoring must still come from revealed
ground (a candidate must be reachable from the revealed walkable network, by a
stair or ramp). Keep `knowledge_scope: player_derivable`, and update its notes
to state the act/sense rule. **Measure** candidate counts before/after, and
specifically whether a room one level below the surface (z168, near a surface
landmark) is now proposable.

Also check `TRAPS.md`: **a downstair cannot be designated on a grass tile.**
Work out, from source and a live read (not by designating anything), how a
player actually gets from a z169 grass surface down into z168 soil, and make
the dig path handle it (e.g. a channel or a ramp, or a stair on a non-grass
tile), stating what you verified and what you did not.

## Part 2 — farm plot tool

New file, e.g. `scripts/dfhack/df-overseer-farm.lua`, in the existing idiom:

- **`farm.find`** (read): candidate plot areas on revealed, dug, soil or mud
  floor, near a named landmark. Report for each whether it is **outside or
  inside** (a player sees light versus dark, so this is player-visible on a
  revealed tile), size, and landmark-relative position. No coordinates.
- **`farm.build`** (write): place a farm plot on a chosen candidate (e.g. via
  `quickfort` `#build` with the farm-plot key, or the struct API if that is
  cleaner; verify which works in this build).
- **`farm.set-crop`** (write): assign a crop per season to a named plot.
  **Validate against the game's own rules rather than reimplementing them:**
  refuse an underground crop on an outside plot and vice versa, with a clear
  reason, and refuse a crop the fort holds no seed for. Expose the fort's
  valid crops for a given plot as part of `farm.find` or a separate read.
- Plots should become addressable afterwards (a landmark, or a stable name),
  matching how `landmarks` already names buildings.

## Part 3 — still (drink) and the minimum workshop surface

Plump helmet, pig tail, cave wheat and sweet pod are all brewable. Drink needs
a **still** and a brewer. Build:

- **`workshop.find`/`workshop.build`** for at least the **still**, and a
  **kitchen** if it falls out of the same code cheaply, landmark-relative, on
  revealed free floor. A 3x3 footprint. Reuse `openarea`'s free-floor logic
  rather than duplicating it.
- Report what the workshop needs to actually operate (labors, e.g. brewing;
  barrels or pots for drink storage) as data the caller can act on, and check
  against `df-overseer-stocks` whether the fort has containers. Do not build
  manager orders in this stream.

## Tagging and allowlists

Tag every new command with `knowledge_scope` (the registry refuses to load
otherwise). Follow the existing role pattern: **finds** go to the architect's
read list; **builds and set-crop** go to the Overseer's write list only (the
Overseer can act but not discover, a pinned structural property with a test).
The registry and roster tests must still pass.

## Verification without mutating the fort

The fort is paused and must stay paused, and **you must not mutate it**: do not
designate, build or assign anything live. Give every write command a
**dry-run mode** that resolves the target, validates everything (the
tile states, crop validity, seed availability, grass-tile stair rule) and
returns exactly what it would do, and verify the dry run live against the real
fort. The orchestrator will run the real mutations afterwards, with the user
aware, and they are reversible (cancel a designation, remove a building).

## Constraints

- Fort paused, read-only live access, no mutations, no deploy. Delete `/tmp`
  probes; never leave files under DF's script paths. Keep probes light.
- **Heed `docs/TRAPS.md`**: `designation.liquid_type` is a boolean; items use
  `flags.trader` for ownership and `stack_size` for units; `dfhack.maps.getTileFlags`
  misled one probe (read block designations directly); a Lua global set in one
  `dfhack-run` call persists in the live process (the audit's executor
  accidentally left `dfhack_flags.module = true` and silently disabled every
  guarded script). Do not set DFHack globals in probes.
- **No coordinates** cross the model boundary.
- Commit on your worktree branch as you go. Ambient suite on `main` is **291
  passed, 1 skipped**; `.venv-dfmcp` `dfmcp/tests` is **162**. `.venv-dfmcp` is
  gitignored and will not exist in your worktree: say which interpreter you
  used, and do not report a count from a tree that lacks today's merged work.
  **Base your branch on current `main`**: the last stream branched early and
  broke `main` on merge.
- Do **not** edit `Working.md`, `decisions/DECISIONS.md`, `ROADMAP.md`,
  `CLAUDE.md`, `memory/` or `research/`.

## Touched surfaces

`scripts/dfhack/df-overseer-diggable.lua`, `scripts/dfhack/df-overseer-farm.lua`
(new), `scripts/dfhack/df-overseer-workshop.lua` (new),
`scripts/dfhack/df-overseer-openarea.lua` (only if its free-floor logic is
factored for reuse), `scripts/dfhack/TOOLS.yaml`, `agents/*/tools.yaml`,
`dfmcp/` tests only if new schemas need them, `tests/`, this doc.

## Report back

The act/sense change and its measured effect (is the z168 farm room now
proposable?). How a player gets from grass at z169 into z168, and what you
verified. Each new command, its tag, its role placement, and its dry run
against the live fort. What the still needs to operate, and whether the fort
has it. Test counts and the interpreter used. Your branch name.
