# Handoff: the Architect has eyes but no hands for carving, smoothing and furnishing

Date: 2026-09-24. **Offline build. No deploy, no VM mutation, no fort change.**
Live reads are allowed only where this brief names them, bounded and read-only,
and the fort stays paused. A deploy and the first real build each need their
own go-ahead, which the orchestrating session will ask for separately.

Read `CLAUDE.md` first, then `Working.md` (START HERE), the register rows
dated 2026-09-24 (quickfort already covers smoothing, engraving and traffic;
soil cannot be smoothed; the Architect stays propose-only), `blueprints/README.md`,
`blueprints/templates/bedroom-cell-v1.*`, `scripts/dfhack/df-overseer-surface.lua`
(the read side this verb pairs with) and the Architect's `proposal-0003` in
`evals/live/2026-09-24-architect-rematch/`.

## The gap

The Architect now proposes a sound room (stair, carve, smooth, furnish, zone)
but nothing can carry it out. The generic `building` tool places furniture and
`zone.place` places zones. Nothing carves rooms, smooths or engraves
surfaces, sets traffic, or constructs a wall where the material cannot be
smoothed (soil, ore). The register already records that quickfort's `#dig`
mode covers smoothing, carving, engraving and traffic designation; it has
never been read for what it exactly does or run.

## What to build

1. **Read quickfort from the installed source, not memory.** On the VM
   (read-only, no changes): `hack/docs`, `hack/scripts/quickfort.lua` and
   `hack/scripts/internal/quickfort/*`. Establish, with file and line cites:
   the `#dig` symbols for carve, smooth, engrave, track/traffic; how `#build`
   places walls; whether a dry run exists and what it reports; the Lua entry
   point and its arguments; what it returns on partial failure; how it handles
   tiles it cannot designate. Write it up as
   `research/2026-09-24-quickfort-hands.md`, marking verified vs inferred.
2. **One generic verb**, `scripts/dfhack/df-overseer-blueprint.lua`, wrapping
   quickfort. It takes a template id (from `blueprints/templates/`) or a named
   blueprint plus a site reference, dry run by default, real run only when
   asked. It must return what quickfort reported, then re-read the result
   with the surface layer's own reads (enclosure, finish, material) so a
   caller sees whether the room actually came out enclosed and finished,
   not just that designations were queued.
3. **Site reference without model-facing coordinates.** The verb must not ask a
   model to emit a raw coordinate and must not print one. Work out how a site
   is named (a handle from an existing find tool, a zone id, a landmark plus an
   offset) and say why. If quickfort needs an absolute start tile, resolve it
   inside the tool.
4. **Enforce the soil rule in data, not branches**: where a finish is required
   and the material cannot be smoothed, the verb reports that rather than
   silently leaving rough soil. Use the tile classification the surface layer
   already has.
5. **Generic by rule.** Any template, any blueprint, no per-room branches.
   Cost of the next room type must be one data entry.

## Scope

Yours: `scripts/dfhack/df-overseer-blueprint.lua` (new), `scripts/dfhack/TOOLS.yaml`,
`dfmcp/tools.py` and the matching schema, the allowlist for the **architect**
only (write verbs are not granted to the other advisors), tests, and
`research/2026-09-24-quickfort-hands.md`. Not yours: any other `.lua`,
`conductor/**`, `doctrine/**`, `dfqueue/**`, and per the `handoffs/` rule
`Working.md`, `decisions/DECISIONS.md`, `memory/` and `handoffs/INDEX.md`.
Collect owed register lines in your Result.

## Rules

- `git merge --ff-only main` first; this brief is committed on main.
- Both suites green with numbers quoted: ambient `python -m pytest` (baseline
  **1423 passed, 3 skipped**) and `dfmcp/tests` in `.venv-dfmcp` (baseline
  **652 passed**). Use `python`.
- pcall-guarded reads that return defaults hide failures: use the
  `read_failures` plus `dfhack.printerr` pattern.
- Bounded footprints and rings only, never an unbounded live query. Coordinate
  free output. No rendered map. No armok capability. No em dashes in prose.
  **No attribution lines in any commit message.** Commit as you go.
- Stop and report on any permission or classifier refusal. Never route around
  one through another agent or session.

## Done means

Given a template and a site, the verb's dry run states what would be
designated and what could not be, and its real run reports designations
queued plus a surface re-read. The research doc says exactly what quickfort
does and does not cover, so the next stream knows which gaps remain (wall
construction, furniture placement order). The Result names the live check a
deploy should run against a throwaway site and what the check cannot see.

## Result

(to be filled by the executor)
