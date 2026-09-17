# Handoff: let the dig tools propose a way down to stone

**Dispatched:** 2026-09-17, by the orchestrating session. **Executor:** Sonnet, worktree-isolated.
**Stream status:** see `handoffs/INDEX.md`.

## Why

Uniboslan can't reach stone, and that blocks a lot:
- **Blocks and mechanisms** can't be made, and so the **well** can't be built. The fort has 0 BLOCKS and 0 TRAPPARTS.
- **The still** has thin material: the fort owns only 3 logs.

The fort lives at z168 (the farm room). Stone is at z167. `df-overseer-diggable find 1 1 -2 "Embark Site"` returns `[]`, because `borders_walkable_network` only checks the ring of tiles on the **same** z-level as the candidate. z167 has no walkable tile yet, so nothing there can ever qualify. The tool's own header already calls this a v1 scope limit. Recorded in `handoffs/2026-09-17-water-and-industry-tools.md`, "Stone access (item 6)", and `Working.md` HANDOVER 2026-09-17 START HERE item 3.

## Goal

The Architect can discover, and the Overseer can designate, a real way from the existing walkable network down to diggable stone one level below. The usual shape is a stair: an up/down or down stair designated on a walkable tile at z168, with the matching up stair directly beneath it at z167, plus room to dig from there.

Read before designing:
- **Boundary-connectivity lesson** (the diggable header, and the register 2026-09-10): a floor dig beneath a stair never became a job because the connecting tile wasn't a matching stair type. The stair pair has to be designated correctly on both levels.
- **The act/sense split** (`docs/AGENT-ARCHITECTURE.md`): finds and lists go on the Architect's read list, and writes go on the Overseer's write list only. This split is pinned by tests.
- **Design commitment #1:** no raw coordinates leave the script. Candidates are named relative to landmarks, as the existing finders already do.

**Prefer extending the existing `diggable.find` / `diggable.dig`** (for example a vertical, stair-down candidate kind) over new tool ids. If a new tool id really is the cleaner design, you may add one. Update `scripts/dfhack/TOOLS.yaml` (with a `knowledge_scope` tag and its justification), `agents/architect/tools.yaml` and/or `agents/overseer/tools.yaml`, and the pinned role tool counts in the tests. State the new counts in your report, because CLAUDE.md quotes them.

## Verification without mutating the fort

- **Read-only checks against the live fort (VM 103) only.** A find must return a real candidate at the embark. A dig dry run must describe exactly which tiles it would designate on each level.
- **No real designation.** The orchestrator runs that later, with the user aware.
- **Leave the fort paused.** Confirm `dfhack.world.ReadPauseState()` is true before your first read and after your last. If it's ever false, stop and report.
- **Test your changed script without replacing the deployed one.** DFHack caches scripts by name, so run your version from a temporary, uniquely named copy in `/tmp` with `dfhack-run lua -f` or an equivalent, and delete it afterwards. Never leave files under DF's script paths.

## Constraints

- **Branch** from current `main` and commit on your worktree branch.
- **Test suites** on `main`: the ambient `python -m pytest` gives **306 passed, 1 skipped**, and `.venv-dfmcp` `dfmcp/tests` gives **165**. `.venv-dfmcp` won't exist in your worktree, so say which interpreter you used.
- **Traps:**
  - `dfhack-run lua -e` silently does nothing on this build; use `-f` with a file.
  - Every output line carries an ANSI prefix.
  - `getWalkableGroup` takes `xyz2pos(x,y,z)`.
  - Never set DFHack globals; use `local` only.
  - Check every `pcall` result.
- **VM access:**
  - Use the `.env` keys `DF_VM_IP` (strip any `/24`) and `DF_SSH_KEY`, user `df`.
  - **Read those keys only**, with `grep -E '^KEY=' .env`. Never `cat` or filter the whole file.
  - No hostnames, addresses or tokens in anything you write.
- **Don't edit** `Working.md`, `decisions/`, `ROADMAP.md`, `CLAUDE.md`, `memory/`, `research/`, `doctrine/`, or `docs/TRAPS.md`. Put any new traps in your report.
- **Don't deploy** to VM 103.

## Touched surfaces

`scripts/dfhack/df-overseer-diggable.lua`, `scripts/dfhack/TOOLS.yaml`, `agents/architect/tools.yaml`, `agents/overseer/tools.yaml`, `dfmcp/tests/` and `tests/` (only as far as tool registration and role counts require), and this doc. **Not** `scripts/dfhack/df-overseer-farm.lua` (another stream owns it today).

## Report

- The design you chose, and the alternatives you rejected.
- What you changed.
- What you verified live, with the command for each check.
- What only a real designation can prove, written as a short test plan.
- Tool-count changes, if any.
- New traps.
- Suite counts and the interpreter you used.
- Your branch name and commit hashes.

## Result

**Design chosen.** Extended `df-overseer-diggable.lua` (not a new file) with
a second, narrower candidate kind alongside the existing `find`/`dig` box
scan: `find-stair [LEVEL] NEAR_LANDMARK [RADIUS_TILES]` and
`dig-stair [LEVEL] NEAR_LANDMARK [RANK] [RADIUS_TILES] [DRY_RUN]`. The box
scan (`find`) can never return a candidate at a level with no walkable
tile yet -- v1's own `borders_walkable_network` scope limit, checked on the
same z as the candidate -- which is exactly Uniboslan's situation at z167
under the walkable z168 farm room. `find-stair` looks for a single
WALKABLE column on the network at the landmark's own level whose
directly-below tile is diggable (reusing `is_diggable` unchanged, so the
2026-09-16 knowledge-scope/act-sense fixes apply identically); `dig-stair`
designates both halves of that pair -- a downstair at the walkable level
and the matching upstair directly beneath it -- in one call, so the
boundary-connectivity lesson (2026-09-10: a floor dig beneath a stair
never becomes a job unless the tile below is *also* designated as the
matching stair type) is satisfied by construction, not by caller care.

**Alternatives rejected:**
- *A `KIND` argument on the existing `find`/`dig` W H signature* (e.g.
  `find W H LEVEL NEAR_LANDMARK stair`) instead of new subcommands. Rejected
  because a stair pair is inherently a 1x1 column, not a WxH rectangle --
  forcing W/H into the stair call's signature would be dead arguments on
  every call, and the two shapes' ranking/candidate logic genuinely differ
  (single-point scan vs. rectangle scan with overlap dedup). Two
  subcommands in the same file is one new tool id per role (not two new
  files), which matches the handoff's "prefer extending... if a new tool id
  really is the cleaner design, you may add one."
- *A tool that also digs the room at the lower level in the same call*
  (closer to the Goal's literal "plus room to dig from there"). Rejected:
  once `dig-stair` designates the pair and it's carved, the upstair tile
  itself becomes walkable, which is exactly the missing ingredient the
  *existing* `find`/`dig` box scan needs to succeed at z167 on a later
  call. Chaining two already-live-verified primitives is narrower and
  reuses proven code instead of building one primitive that does both a
  point search and an area search.
- *Filtering candidates by upper-tile material* (excluding grass, per the
  recorded-but-unconfirmed "grass tile can't take a downstair" trap).
  Rejected: this file's own header already found no confirming mechanism
  for that trap by reading `dig.lua`'s source (a grass floor tile's SHAPE
  satisfies `is_diggable_floor` the same as any other floor). Silently
  excluding grass would be guessing in the opposite, equally unverified,
  direction. Instead each candidate reports its own `upper_tile_material`
  (informational, since a walkable tile is by definition revealed/
  player-visible) so a caller can choose to avoid grass until the question
  is actually settled by a live designation test, without this tool
  asserting either answer.
- *Giving the Overseer a paired `diggable.find-stair` read*, matching the
  newer farm/zone/trees/well "read before write" convention. Rejected for
  consistency within this one file: `diggable.find`/`diggable.dig` already
  established the OLDER asymmetric pairing (Overseer acts, Architect
  discovers, no Overseer read) and that split is pinned by
  `dfmcp/tests/test_roles.py::test_the_overseer_can_act_but_cannot_discover`.
  Introducing the newer pattern for only *half* of this one file's tools
  would leave `diggable.dig`/`diggable.dig-stair` inconsistent with each
  other for no stated reason. Noted as a real, deliberate design call, not
  an oversight -- a future stream could revisit it.

**What changed:**
- `scripts/dfhack/df-overseer-diggable.lua`: added `ranked_stair_candidates`,
  `describe_stair_candidate`, `find_stair_down`, `dig_stair_down`,
  `truthy_dry_run`, the `DOWNSTAIR_BLUEPRINT`/`UPSTAIR_BLUEPRINT` constants
  (reusing `blueprints/starter-entrance-1x1.csv`/
  `starter-connector-1x1.csv`, this fort's own already-working
  entrance/connector pair -- no new blueprint files), and the `find-stair`/
  `dig-stair` CLI subcommands. `dig_stair_down` takes a `DRY_RUN` argument
  (default true, added after the live find-stair test below, matching the
  farm/workshop/zone/trees/well precedent rather than `diggable.dig`'s own
  switch-less shape -- explained above and in the code comment).
- `scripts/dfhack/TOOLS.yaml`: two new command entries under
  `df-overseer-diggable.lua`, both `live_deployed: false` (no deploy this
  stream), `knowledge_scope: player_derivable`.
- `agents/architect/tools.yaml`: `diggable.find-stair` added to `read`;
  `diggable.dig-stair` added to `deny` ("Advisors do not act. Propose it.",
  matching `diggable.dig`'s existing entry).
- `agents/overseer/tools.yaml`: `diggable.dig-stair` added to `write`, no
  matching read (see rejected alternatives above).
- `dfmcp/tests/test_roles.py`: extended
  `test_the_overseer_can_act_but_cannot_discover` to also assert
  `diggable.dig-stair in overseer.write` and
  `diggable.find-stair` in the not-granted-to-overseer discovery tuple --
  locking in the design decision above as a visible, pinned assertion
  rather than leaving it to fall out of what the YAML happens to say.

**Verified live**, all against Uniboslan (VM 103, paused throughout,
read-only): a modified copy of the file was scp'd to
`/tmp/digdown_diggable_test.lua` and run via a small sandboxed harness,
`/tmp/digdown_stair_probe.lua` (both deleted after use). The harness was
needed because `dfhack-run lua -f` (`hack/scripts/lua.lua`'s `-f` path) is
a bare `loadfile()` with no script-loader injection -- unlike a real
`dfhack-run <scriptname>` invocation -- so the file's own unconditional
`if dfhack_flags.module then return end` guard (unchanged, shared by every
`df-overseer-*.lua` file) indexes a nil global and crashes. Confirmed live
that the real global `dfhack_flags` is nil in that context
(`DIGDOWN_MODULE_FLAG=nil`, via `dfhack_flags and dfhack_flags.module`
short-circuiting rather than erroring). Setting the real global (even to
the "safe" `false`) would itself violate "never set DFHack globals; use
local only" and the standing 2026-09-16 trap (a leaked
`dfhack_flags.module = true` silently disabled every guarded script for
the rest of the live process) -- so the harness instead calls
`loadfile(path, 'bt', sandbox_env)` with a private
`setmetatable({dfhack_flags = {module = false}}, {__index = _G})`
environment: `dfhack_flags.module` reads from the sandbox, every other
name (`dfhack`, `df`, `reqscript`, `xyz2pos`, `CR_OK`, `json`, ...) falls
through to the real `_G` unchanged, and nothing is ever written to the
real global environment. **New trap, recording here per the constraints
(not in `docs/TRAPS.md`, which this stream may not edit): a locally-scripted
`dfhack-run lua -f` copy of any `df-overseer-*.lua` file crashes on its own
`dfhack_flags.module` guard unless something upstream in the same live
process already ran it through the real script loader first, or the test
harness supplies a private (non-global) `dfhack_flags` table via a
sandboxed `loadfile` environment.**

Commands run (all read-only or dry-run; IPs/keys never appear in output):
- `dfhack.world.ReadPauseState()` + `df.global.cur_year_tick` via
  `/tmp/digdown_pause_check.lua`, before and after every other check:
  `DIGDOWN_PAUSED=true`, `DIGDOWN_TICK=227008` both times, unchanged.
- `./dfhack-run lua -f /tmp/digdown_stair_probe.lua find-stair "Farm Plot"`
  -- real positive: **5 ranked candidates**, all `upper_tile_material:
  "SOIL"` (the z168 farm-room floor), all `lower_tile_hidden: true` (z167
  has never been revealed on this fort, so `lower_tile_material` is
  correctly omitted -- the act/sense rule admitting a hidden tile
  unconditionally), all `borders_walkable_network: true`, nearest ones at
  `distance_tiles: 0` from "Farm Plot"/"Stockpile #2".
- `./dfhack-run lua -f /tmp/digdown_stair_probe.lua dig-stair "Farm Plot"`
  (DRY_RUN default) -- rank 1's exact candidate, `dry_run: true`,
  `would_run_downstair_blueprint: "starter-entrance-1x1.csv"`,
  `would_run_upstair_blueprint: "starter-connector-1x1.csv"`, no quickfort
  call made.
- `./dfhack-run lua -f /tmp/digdown_stair_probe.lua find-stair "Nonexistent Place"`
  -- `{"error": "landmark not found: Nonexistent Place"}`.
- `./dfhack-run lua -f /tmp/digdown_stair_probe.lua dig-stair "Farm Plot" 99`
  -- `{"error": "no candidate at rank 99 (found 5 near Farm Plot)"}`.
- `./dfhack-run lua -f /tmp/digdown_stair_probe.lua find-stair -2 "Farm Plot"`
  -- `[]` (two levels down, where no walkable tile exists at either z167
  or z166 for the ring/anchor check to match -- correct, not a crash or a
  false positive).

**What only a real designation can prove** (short test plan for the
orchestrator's next supervised run):
1. Call `dig-stair "Farm Plot" 1 30 false` (an explicit `DRY_RUN=false`)
   against the live, paused-then-briefly-unpaused fort, with the user
   aware, matching this project's existing mutation-gate discipline.
2. Confirm both `quickfort_ok`-equivalent fields (`downstair_ok`,
   `upstair_ok`) are true and `quickfort_stats` on each shows exactly 1
   tile designated.
3. Unpause briefly and confirm via `stuckjobs.find`/`connectivity.check`
   (or a direct `dfhack.maps.getWalkableGroup` read at the resolved z167
   tile) that a dwarf actually claims and completes both halves of the
   job -- the real proof the boundary-connectivity fix works, not just
   that two designations were queued. A completed dig should also make the
   `find`/`dig` box-scan tools succeed at z167 for the first time (the
   "room to dig from there" half of the Goal, deliberately left to those
   existing tools rather than duplicated here).
4. The grass-tile question remains genuinely open (see the file's original
   header and the rejected-alternative above): if the chosen candidate's
   `upper_tile_material` happens to be GRASS_LIGHT/GRASS_DARK on some
   future fort, that real designation would be the first live evidence
   either way.

**Tool-count changes:** architect 19 -> **20** (+1: `diggable.find-stair`,
read). overseer 32 -> **33** (+1: `diggable.dig-stair`, write). consultant
unchanged at **4**. Confirmed programmatically against the real registry +
roster (not just by counting YAML lines):
`architect 20 overseer 33 consultant 4`. CLAUDE.md's "architect 19,
overseer 32, consultant 4" status line is now one stream stale -- flagging
per this doc's own don't-edit-CLAUDE.md constraint, not fixing it here.

**New traps:** the `dfhack_flags.module` / bare `lua -f` crash above. No
others found.

**Suite counts:** `python -m pytest` (repo root): **306 passed, 1
skipped**, both before and after this stream's changes -- interpreter
`C:\Users\wills\AppData\Local\Programs\Python\Python312\python`, Python
3.12.4. `.venv-dfmcp` does not exist in this worktree, per the handoff's
own note; not run separately (the same 165 `dfmcp/tests` are included in
and pass within the 306 ambient total, confirmed via
`pytest --collect-only`).

**Branch and commits:** branch `digdown-resume` (this worktree was
recreated mid-stream after the original worktree-isolated branch was
auto-cleaned for having no commits yet -- see the stream's first message
for why; `digdown-resume` branches directly from `main` at `eeb58af`, a
pure ancestor relationship, confirmed via
`git merge-base --is-ancestor eeb58af HEAD`).
- `a1619c9` -- diggable: add find-stair/dig-stair, a vertical stair-down
  candidate kind
- `0ae7ad2` -- diggable: give dig-stair a DRY_RUN default, matching newer
  write tools
