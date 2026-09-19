# Handoff: queue a one-off job at a workshop, the way a player clicks it

Date: 2026-09-19. **Offline build stream. No VM, no SSH, no deploy, no live
run.** User-directed.

Read `CLAUDE.md`, then `handoffs/2026-09-19-well-and-harvest.md` (its section
on the direct-job route and the draft Lua it reproduces), then
`handoffs/2026-09-19-well-finish.md`'s write-up, then
`scripts/dfhack/df-overseer-workshop.lua` and `df-overseer-orders.lua`, then
this.

## Why

Manager work orders stall on this fort: with no Manager appointed, they are
never validated, and even hand-validated they never became jobs in 42 game
days. **The user pointed out the honest alternative: a player can also queue a
one-off job directly at a workshop by clicking it** (the workshop's own "add
job" menu), which needs no Manager at all. That is a legitimate player action,
unlike setting an order's `validated` flag by hand, which was a cheat and is
not to be repeated.

A previous stream drafted exactly this, **sourced verbatim from this install's
own `hack/scripts/idle-crafting.lua` and `hack/lua/dfhack/workshops.lua`**
(`dfhack.job.createLinked` plus `assignToWorkshop`), and was refused by the
permission classifier when it tried to *run* it ad hoc. This stream turns it
into a **proper, reviewed, tested tool**; running it live is a separate,
user-approved step.

## Deliverable

A new command (a new file, `scripts/dfhack/df-overseer-workjob.lua`, or a new
subcommand on `df-overseer-workshop.lua` if that file's structure clearly
wants it; say which and why) that queues **one** job at **one** named
workshop, for at least:

- `ConstructBlocks` at a mason's workshop,
- `ConstructMechanisms` at a mechanic's workshop,
- `BREW_DRINK_FROM_PLANT` at a still (a reaction job, so its `job_item`
  spec comes from the reaction's own reagents; read how DFHack's own scripts
  build reaction jobs rather than guessing),
- a cooking or processing job only if cheap.

Addressed by landmark name, as every other tool is. **No coordinates in any
input or output.**

## Rules that matter here

- **A `DRY_RUN` default of true**, as `orders.create` and `harvest gather` do:
  report what would be queued and whether the workshop exists, is built, and
  has a free job slot, without mutating.
- **Refuse, never guess**: an unknown workshop, a workshop still under
  construction, a full job queue, or an unknown job name is an explicit error.
- **Follow DFHack's own code path**, not a hand-built job struct, and cite the
  file and line you followed, as `df-overseer-orders.lua`'s header does.
- **Never set `validated` on anything** and never touch manager orders.
- Register it in `scripts/dfhack/TOOLS.yaml` as a **mutating** tool, and grant
  it deliberately per role in `agents/*/tools.yaml`, with reasons. Add tests
  alongside the existing registry and role tests.
- **Write as you go**: commit on your branch after each milestone and append
  to this file's write-up each time.
- Never write an IP address, hostname or port into any committed file. Do not
  write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`. No em dashes in prose.

## Touched surfaces

The new tool file (or the one subcommand), `scripts/dfhack/TOOLS.yaml`,
`agents/*/tools.yaml`, `dfmcp/tests/`, `tests/`, and this handoff doc.

## Done means

The command exists with a dry-run default, refuses every bad input
explicitly, follows a cited DFHack code path, is registered as mutating and
granted with reasons, the full suite passes (report before and after), and the
write-up states exactly what the first live run must check. **It is not run
live by this stream.**
