# Handoff: write the chosen material class into buildingplan's filter

Date: 2026-10-01. **Executor, Sonnet, worktree. Offline code only, no live
access** (the orchestrator live-verifies after merge).

## Why

The register's 2026-09-30 ruling: our layer chooses a material **class** (any
non-ore stone, any wood) and writes it into buildingplan's own filter; the
game picks the items. Today `building.build` and `construction.build` compute
a non-economic choice but only report it: the generated blueprint carries no
material (`blueprint_text` in `df-overseer-building.lua` writes the kind key
only), so buildingplan attaches the closest item, which can be ore
(`evals/live/2026-09-30-reservations-deploy/README.md`, correction). Read
`research/2026-09-30-policy-audit.md` (with its orchestrator corrections at
the top) and `research/2026-09-30-item-binding-design.md` first.

## Tasks, in order (commit after each)

1. **Find the real mechanism, from source at DFHack `53.16-r1`** (GitHub
   `DFHack/dfhack`, `plugins/buildingplan/`, `plugins/lua/buildingplan.lua`,
   and quickfort's material syntax in `docs/guides/quickfort-*`). Answer, with
   file and line: how a script sets buildingplan's material filter for a
   planned building (per building, or per building type as a default); whether
   quickfort `#build` cells can carry a material filter directly; what
   "not ore, not gem" can be expressed as (material mask, a category such as
   `stone`/`wood`, a specific-material list); what happens when no item
   matches (the building waits, the named hold we want, or falls back). Write
   this up in the Result; say "unverified" where source does not settle it.
2. **Implement** in `building.build` and `construction.build`: the chosen
   class goes into the filter by the mechanism found, so buildingplan can no
   longer pick ore or gem. Prefer a per-building filter over changing the
   fort-wide default; if only a default exists, set it for the call and
   restore it, and say so. The report states the filter actually written,
   not the intended one.
3. **Tests** in the existing lupa style, including a stub that fails if the
   filter call is missing. Note plainly which parts the stub cannot prove
   (the offline fake world has disagreed with the real API twice: vector
   indexing, `tile_bitmask`).

## Rules

- First step: `git merge --ff-only main`. Commit your plan early, then after
  each task.
- Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`.
- No em dashes in prose. No attribution lines in any commit.
- Generalisable: take the kind and class as arguments, no per-kind branches
  (`CLAUDE.md` project rules). No armok capabilities.
- Update `scripts/dfhack/TOOLS.yaml` entries for both commands.
- Tests: ambient `python -m pytest` and `dfmcp/tests` in `.venv-dfmcp`;
  report both counts.
- Stop and report on any permission refusal.

## Touched surfaces

`scripts/dfhack/df-overseer-building.lua`,
`scripts/dfhack/df-overseer-construction.lua`, `scripts/dfhack/TOOLS.yaml`,
their tests and lua stubs.

## Result

(fill in, about 200 words: the mechanism found with sources, what was built,
what only a live test can settle)
