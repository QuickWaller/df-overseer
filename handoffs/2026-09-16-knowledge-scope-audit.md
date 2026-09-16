# Handoff: knowledge-scope audit — agents know only what a vanilla player could know

**Dispatched** 2026-09-16 by the orchestrating session. **Agent:** `executor`,
Sonnet, worktree-isolated. **Status:** dispatched.

## Why this stream exists

The user decided (register, 2026-09-16, "Agents may only know what a vanilla
player could know") that agent tools are limited to `player_visible` and
`player_derivable`. **Existence may be known from the embark screen; location
only once uncovered.** The rule binds the role allowlists, not developer
diagnostics.

`research/2026-09-16-player-visibility.md` is your foundation. **Read it in
full first**, especially its bottom line, §1, §5, §9 and the preliminary
classification table. Its classification is preliminary: verify each row
against source before acting on it.

The orchestrator verified the research's load-bearing claims live before
dispatching this:

- `tile_designation.hidden` is a flat bool on this build: a surface tile reads
  `false`, deep undug rock and the magma sea read `true`, and it matches
  `dfhack.maps.isTileVisible` exactly.
- `dfhack.units.isHidden(unit)` is true for **29 of 75** active units, including
  **all 5** `DEMON_*` units that `unit-status hostile` reports through solid
  rock (register, 2026-09-11).

## The enforcement principle

StarCraft's bot ecosystem hit this exact problem. Its lesson: enforcement
belongs in the **referee layer**, not in bot self-restraint. BWAPI's
`CompleteMapInformation` is off by default and tournaments police it
server-side. Our referee layer is `dfmcp`'s registry and per-role allowlists,
which is already the real boundary (`docs/AGENT-ARCHITECTURE.md` principle 8).

So this stream has two halves: **make the boundary structural**, then **fix the
tools that currently leak**.

## Part 1 — make the boundary structural

1. Add a required `knowledge_scope` field to every tool entry in
   `scripts/dfhack/TOOLS.yaml`: `player_visible`, `player_derivable` or
   `omniscient`. Where one script's subcommands differ (e.g. `labor
   unit-status hostile` vs `labor labors`), tag at whatever granularity the
   registry actually allowlists.
2. Teach the `dfmcp` registry to load it and **refuse at load time** any role
   allowlist that grants an `omniscient` tool, in the same way it already
   refuses a mutating tool filed under `read`. A missing tag is also a load
   error. One failing-case test per rule, following the existing registry
   tests' pattern.
3. The tag describes the tool **after** your fixes below. A tool you cannot
   make safe is tagged `omniscient` and removed from every role's allowlist,
   with the loss stated in your report.

## Part 2 — fix the leaks

Verify each against source, then fix. **Measure the cost of every change on
the live fort** where a read can do it (a `find` is a read; a `dig`/`build` is
not and must not be run): candidate counts, units reported, findings returned,
before and after. The user wants the cost of the policy measured, not guessed.

- **`df-overseer-diggable.lua` `find`/`dig`** — omniscient today: no
  `designation.hidden` check, and it returns the `material` of unrevealed
  tiles, which can name an undiscovered vein. Require every tile in a
  candidate (interior, not just the ring) to be revealed, and never return
  material for a hidden tile. Measure candidates before/after.
- **`df-overseer-labor.lua` `unit-status hostile`** — omniscient today: no
  reachability, no `isHidden`. Filter with `dfhack.units.isHidden`. Expect the
  5 demons to disappear; confirm it.
- **`df-overseer-threat.lua` `scan`** — the hardest case. Its stated purpose is
  catching ambush/sneaking units that `INVASION` and `isDanger` miss, which is
  exactly what `isHidden` says a player cannot see. The user has already ruled
  that sneaking ambushers are not allowed, so **filter `isHidden` units out**
  rather than reporting them. Then say plainly what coverage is lost, and
  check whether the vanilla player's own equivalent exists: the announcement
  a player gets when an ambush is revealed. Name the announcement types if they
  exist in this build; do not build a new announcements tool in this stream.
- **`df-overseer-breach.lua` `check`** — scans every block regardless of
  visibility and reads liquid state on hidden tiles, relying on reachability
  as a proxy. Add an explicit `designation.hidden` check on each finding tile.
  Also note that `designation.liquid_type` is a **boolean** in this build, not
  the enum (see `docs/TRAPS.md`); check whether this tool has that bug.
- **`df-overseer-openarea.lua` and `df-overseer-chokepoints.lua`** —
  derivable in practice but not structurally guarded. Add the hidden check;
  measure whether it changes any result on this fort.
- **`df-overseer-diff.lua` `since`** — `UNIT_DEATH` fires engine-wide for any
  unit's death, including ones a player never sees; `UNIT_ATTACK` is
  unverified. Gate both on visibility (e.g. `isHidden` of the participants, or
  a matching report). Live event firing needs the clock to run, which it will
  not: verify by source reading, say so, and keep `JOB_COMPLETED` and the
  `REPORT` branch, which are player-visible.

Everything the research classifies as `player_visible` (landmarks, overview,
stuck jobs, labor idle/injured/military and `labors`/`set-labor`, `stocks`,
diff's report reads, ui): confirm and tag, no change expected.

## Constraints

- **The fort is paused and stays paused.** Read-only live access only. Do not
  run any mutating subcommand (`dig`, `build`, `set-labor`). Delete `/tmp`
  probes; never leave files under DF's script paths.
- **No deploy.** The orchestrator deploys.
- **Keep live probes light**: a whole-map Lua scan over 186 z-levels has been
  slow enough to drop SSH. Sample, or use the tools' own bounded searches.
- **Known traps, do not repeat:** `liquid_type` is a boolean; `flags.foreign`
  is origin not ownership; stocks count stack units; cross-check whole-map
  aggregates against `dfhack-run prospect all`. See `docs/TRAPS.md`.
- **No coordinates** cross the model boundary. Unchanged, non-negotiable.
- Commit on your worktree branch as you go.
- Ambient suite is **281 passed, 1 skipped** on `main`; `dfmcp/tests` in
  `.venv-dfmcp` is 152. Report both after your changes. Use `python`.
- Do **not** edit `Working.md`, `decisions/DECISIONS.md`, `ROADMAP.md`,
  `CLAUDE.md`, `memory/` or `research/`.

## Touched surfaces

`scripts/dfhack/TOOLS.yaml`, `scripts/dfhack/df-overseer-diggable.lua`,
`scripts/dfhack/df-overseer-labor.lua`, `scripts/dfhack/df-overseer-threat.lua`,
`scripts/dfhack/df-overseer-breach.lua`, `scripts/dfhack/df-overseer-openarea.lua`,
`scripts/dfhack/df-overseer-chokepoints.lua`, `scripts/dfhack/df-overseer-diff.lua`,
`dfmcp/` (registry and its tests), `agents/*/tools.yaml` (only if a tool must
leave an allowlist), `tests/`, this doc.

## Report back

Per tool: the final tag, what you changed, and the **measured** before/after.
What coverage the policy costs, stated plainly (threat detection especially).
The ambush-announcement types a player would get, if any. What you verified
live, what only by source, what not at all. Test counts. Your branch name.
