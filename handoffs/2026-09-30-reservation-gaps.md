# Handoff: close the reservation gaps (finders, workshop kinds, landmarks footprint, per-command descriptions)

Date: 2026-09-30. **Executor, Sonnet, worktree.** Follows
`handoffs/2026-09-30-room-reservations.md` and
`handoffs/2026-09-30-reservation-holding.md` (merged `d7215e7`, `3e6e35b`).
Read both Result sections and `scripts/dfhack/df-overseer-reservations.lua`
first.

## Codebase-wide rules (review has caught each of these being broken)

- A dry run never changes anything: no persistent state, no designation, no
  record. Mutations happen only on a real run, after success.
- No tile coordinate ever leaves a tool in any output or error.
- DFHack's `ReadCurrentTick` is the tick within the current year and resets
  at New Year. For ages or intervals use `reservations_mod.abs_tick()`.
- Per-kind detail comes from the game's own data or a data entry, never a
  hard-coded list of kinds in a tool (tools-must-be-generalisable rule).
- Test stubs must model the real DFHack API shape. Say how you checked each
  one against live-verified sibling code; this repo has shipped wrong-field
  stubs twice.
- A new trailing optional argument must stay reachable through dfmcp: every
  optional before it needs a declared default in `TOOLS.yaml` equal to what
  the Lua does when the argument is omitted.

## What to do

1. **Finders skip reserved ground everywhere.** `building.lua`, `zone.lua`,
   `farm.lua`, `well.lua` and `workshop.lua` rank candidate sites without
   skipping reserved ones (their build then refuses the chosen tile). Make
   each ranking call the shared `reservations_mod.filter_reserved` exactly
   as `diggable`/`openarea` already do, so RANK N never lands on reserved
   ground (with `RES_ID`, candidates inside that reservation are kept).
2. **Workshop kinds through the game's own kind table.** `workshop.lua`
   keeps its own lowercase kind keys (`still`, `mason`, ...), which do not
   match `building.lua`'s tokens (`Still`, `Masons`). Resolve workshop
   kinds through `building.lua`'s kind table (the same one
   `kind_token_for_key` uses), so the kind checked against a reservation's
   `allowed_kinds` is the same token a template's `#build` cell resolves
   to. Keep `workshop.build`'s existing accepted inputs working (map old
   keys to tokens if agents or tests use them; say which). If a genuinely
   per-workshop policy lives in that table (labor, reagents), leave it but
   key it by the building token.
3. **`landmarks.build` checks its full footprint.** It checks only its
   anchor tile because it never learns the blueprint's size.
   `df-overseer-blueprint.lua` already parses blueprint CSV cells (for
   `template_allowed_kinds`). Reuse that parsing, exported if needed, to
   get the footprint of `BLUEPRINT_FILE` and check every tile it will
   cover. No second CSV parser. If the file's footprint cannot be read,
   refuse rather than fall back to anchor-only.
4. **Per-command argument descriptions in dfmcp.** `dfmcp/tools.py` scopes
   argument descriptions per script, so `zone.place`'s `OVERRIDE` (a
   reservation exception reason) and `zone.assign-owner`'s `OVERRIDE` share
   one blended description. Add per-command scoping (for example a key like
   `zone.place.OVERRIDE`) that wins over per-script and bare entries, then
   split that description into its two meanings. Update the module's own
   docs for the lookup order, and test the precedence.

## Out of scope

- Project MCP tools (a separate brief, dispatched after this merges; it also
  edits `dfmcp/tools.py`).
- Any deploy or live mutation on VM 103. The orchestrator live-verifies
  after merge with real dry-run calls.

## Rules

- `git merge --ff-only main` first.
- Tests: each of the five finders drops a reserved candidate (at least one
  run through the real tool file where stubs exist; the rest may go through
  the shared helper, say which); a workshop kind resolves to the same token
  a `#build` cell gives; `landmarks.build` refused when any footprint tile
  is reserved, not just the anchor; description precedence (command over
  script over bare).
- Run ambient `python -m pytest` (lupa on `PYTHONPATH`) and `dfmcp/tests`
  with `C:/website-projects/df-automation/.venv-dfmcp/Scripts/python.exe -m
  pytest -q dfmcp/tests`; report both counts (baseline 2030/3 and 699).
- Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`.
- No em dashes in prose. No attribution lines in any commit.
- Commit as you go. Stop and report on any permission refusal.
- Fill in the Result section below.

## Result

(to be filled in by the executor)
