# Handoff: reserve tiles for specific planned rooms

Date: 2026-09-30. **Executor, Sonnet, worktree.**

## Context

User's call, 2026-09-30: agents need a way to hold ground for a planned
room so other work cannot take it (a workshop landing where the bedrooms
were meant to go, a corridor dug through a planned farm). **Scope is
specific planned rooms only.** Broad districts ("this region is
residential") are explicitly out: they belong to the owed Opus + user
zoning design session (`Working.md`, memory `zoning-design-session-owed`).

Nothing does this today. `df-overseer-blueprint.lua`'s `site-N` handles
exist only after a real dig has been designated, so they record work
started, not ground held. The game's own zones claim tiles only for things
already built.

Read first: `research/2026-09-28-job-dependency-graph.md` (the guard
model; a reservation check is one more guard in its closed vocabulary),
`scripts/dfhack/df-overseer-blueprint.lua` (site handles, footprint and
orientation resolution, `dfhack.persistent.getSiteData`/`saveSiteData` at
about line 398), and `scripts/dfhack/df-overseer-construction.lua`'s
`apply_keeps_access_guard`/`held` bucket (the pattern for a named hold).

## Design decisions already made (do not reopen)

1. **Storage is DFHack per-site persistent state**, the same mechanism
   blueprint site handles use, not dfqueue. dfqueue filters coordinates
   out on purpose and the Lua tools cannot read its SQLite; the tile set
   must live where the checking tools run. Agents only ever see a handle
   (`res-N`), a purpose string, footprint size and nearest landmark with
   direction and distance. **Never a tile position**, in any output.
2. **A reservation is a planned room's footprint**, resolved exactly the
   way `blueprint preview`/`apply` resolve a template at a site (template,
   landmark or handle, level, rank, radius, orientation with the access
   gate). Reuse blueprint.lua's resolution code; do not write a second
   footprint resolver. Adding `reserve`, `reservations` and `unreserve`
   verbs to `df-overseer-blueprint.lua` is the expected shape; a small
   shared module holding the store and the check (for example
   `df-overseer-reservations.lua`) is fine if other scripts need to
   `reqscript` it.
3. **One shared check, every designating tool.** Any tool that designates
   dig, builds, places a zone or stockpile, or applies a blueprint on map
   tiles refuses (or holds, where the tool already has a `held` bucket)
   any tile inside a reservation it does not hold. The refusal names the
   handle, its purpose and nearest landmark, never the tiles. Enumerate
   every `effect: mutate` command in `scripts/dfhack/TOOLS.yaml` and
   report in your Result which ones you wired and which you exempted and
   why (labor, orders, clock, nobles and the like are not map
   designation and are exempt).
4. **Holding a reservation.** `blueprint apply` of the same template on a
   reserved site is the holder: it proceeds, and the issued `site-N`
   handle records the `res-N` it came from. Other tools can pass an
   explicit reservation handle argument only if that is cheap to add;
   otherwise they simply refuse, and say so in your Result.
5. **No overlaps.** `reserve` refuses a footprint that overlaps another
   reservation or an existing blueprint site, naming the conflict.
6. **Lifecycle:** reserved, then in use (a site was issued from it), then
   released by explicit `unreserve`. No automatic expiry. `reservations`
   reports each one's age in ticks and whether any work has started, so a
   stale plan is visible and the overseer decides.
7. **Hidden tiles** may fall inside a reservation. Nothing about their
   contents is ever reported or counted (no-armok rule).
8. **Roles:** `reserve`/`unreserve` real runs are overseer only (the
   roster's sole writer), dry runs and `reservations` also for the
   architect, matching how `blueprint apply` is granted. Wire them through
   `TOOLS.yaml`, the registry and `agents/*/tools.yaml` the same way the
   existing blueprint verbs are, and update any tool-count tests that pin
   role totals.
9. `DRY_RUN` defaults to true on `reserve` and `unreserve`.

## Out of scope

- Districts or regions, auto-sizing, choosing where rooms go.
- dfqueue schema changes (a project step may later name a `res-N`; not now).
- Any deploy to VM 103 or live mutation. Read-only live checks are
  welcome if credentials exist in your worktree; the orchestrator does the
  live verification after merge.

## Rules

- `git merge --ff-only main` first (main has unpushed commits your
  worktree needs, including the construction.lua guards).
- Offline `lupa` tests for: reserve then a conflicting build/dig refused
  with the handle named and no coordinate leaked; the holder's own
  `blueprint apply` allowed; overlap refused; unreserve frees the tiles;
  hidden tiles not reported. Model stubs on the real DFHack API shapes
  (the repo has twice shipped stubs that modelled the wrong field; say in
  your Result how you checked each stubbed API).
- Ambient `python -m pytest` (lupa on `PYTHONPATH`) and `dfmcp/tests` in
  `.venv-dfmcp` stay green; report both counts.
- Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`.
- No em dashes in prose. No attribution lines in any commit.
- Commit as you go. Stop and report on any permission refusal.
- Fill in this handoff's Result section: what was built, which tools were
  wired or exempted, test counts, anything unverified.

## Result

(to be filled in by the executor)
