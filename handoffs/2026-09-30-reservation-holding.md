# Handoff: reservations are permanent; the room's own contents may build inside; one-off overseer overrides

Date: 2026-09-30. **Executor, Sonnet, worktree.** Follows
`handoffs/2026-09-30-room-reservations.md` (merged `d7215e7`); read its
Result section and `scripts/dfhack/df-overseer-reservations.lua` first.

## Context

Today only `blueprint apply SITE=res-N` can hold a reservation. Every other
designating tool refuses any reserved tile, so once a room is dug, a bed or
a bedroom zone inside it is refused until someone unreserves it, which
would leave the finished room unprotected. User's calls, 2026-09-30:

- A reservation stays for the room's whole life, so nobody builds a tavern
  on a bedroom. Only an explicit `unreserve` ends it, and the overseer
  always keeps the right to unreserve.
- Work the room is meant to have is allowed inside it.
- Anything else is refused, unless the overseer overrides. **An override is
  a one-off exception**: the room keeps its purpose, that one call is
  allowed, and the override is recorded on the reservation with a reason.
  Re-purposing a whole room is unreserve plus a new reservation, never an
  override.

## What to build

1. **Record what belongs in the room at reserve time.** Templates already
   declare it (`blueprints/templates/bedroom-cell-v1.yaml`: `kind: bedroom`,
   `requires: [bed]`, its own zone/build phases). At `reserve`, store on the
   reservation the template's `kind` and the building/zone kinds its own
   phases and `requires` list imply, so the check never re-reads template
   files at build time. Find how `df-overseer-blueprint.lua` loads template
   metadata today and reuse that; if the VM cannot read the YAML, say so and
   propose the smallest data path, do not invent a second template parser.
   Allowed kinds must come from template data, never a hard-coded
   bedroom list in Lua (tools-must-be-generalisable rule).
2. **Optional `RES_ID` on every designating tool wired in the last stream**
   (`building.build`, `zone.place`, `workshop.build`, `farm.build`,
   `well.build`, `openarea.build`, `diggable.dig`/`dig-stair`,
   `construction.mine-vein`/`build`, `landmarks.build`). With it, a tile in
   that reservation is allowed only if the call's kind is one the
   reservation lists; otherwise refused, naming the handle, its purpose and
   the kinds it allows. Without it, behaviour is unchanged (refuse).
   A tile in any OTHER reservation is still refused. Shared-wall rule
   unchanged.
3. **One-off override.** An `OVERRIDE` argument taking a reason string,
   valid only together with `RES_ID`. Allows that one call regardless of
   kind, and appends `{tick (absolute, use abs_tick), tool, kind, reason}`
   to an `overrides` list on the reservation. It never changes the
   reservation's purpose or allowed kinds. `blueprint reservations` shows
   the override count and the most recent reason. Overseer only (it is the
   sole writer already; confirm no other role can reach these tools).
4. **Finders skip reserved ground.** Candidate search in `diggable`,
   `openarea` and any other `find`/ranked-pick path that feeds a
   designating command must drop candidates overlapping a reservation the
   call does not hold (with `RES_ID`, keep candidates inside that
   reservation), so RANK N never lands on reserved ground and then refuses.
   Report which finders you changed.
5. Update `TOOLS.yaml` and `dfmcp/tools.py` arg descriptions for
   `RES_ID`/`OVERRIDE`.

## Out of scope

- `landmarks.build`'s anchor-tile-only check (known gap; leave it, but it
  still gets `RES_ID`).
- Re-purposing, auto-expiry, districts.
- Any deploy or live mutation on VM 103.

## Rules

- `git merge --ff-only main` first.
- Offline `lupa` tests: a bed and a bedroom zone inside a bedroom
  reservation with `RES_ID` allowed; a workshop there refused naming the
  allowed kinds; the same workshop with `OVERRIDE` allowed and recorded,
  purpose unchanged, a second workshop without `OVERRIDE` still refused;
  `OVERRIDE` without `RES_ID` rejected; a finder never ranks a reserved
  candidate. Model stubs on real DFHack API shapes and say how you checked.
- Ambient `python -m pytest` (lupa on `PYTHONPATH`) and `dfmcp/tests` in
  `.venv-dfmcp` stay green; report both counts.
- Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`.
- No em dashes in prose. No attribution lines in any commit.
- Commit as you go. Stop and report on any permission refusal.
- Fill in the Result section below.

## Result

(to be filled in by the executor)
