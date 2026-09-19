# Handoff: the fifth deduction, items built into a building

Date: 2026-09-19. **Offline build stream. No VM, no deploy.**

Read `CLAUDE.md`, `docs/PRODUCTION-MODEL.md` §7 (available is not total),
`decisions/DECISIONS.md`'s last three rows, then this.

## The bug

The design nets four exact deductions from total stock: `in_job`, `owned`
(+ `UNIT_HOLDER`), `forbid`, `trader`. **It missed a fifth.** On 2026-09-19 the
fort had three shale boulders, and `stocks.availability BOULDER` reported
**3 available**. All three were `flags.in_building=true`: the building
material of the still, the mason's workshop and the mechanic's workshop. A
blocks job was then cancelled "needs hard stone boulders", correctly, since no
free boulder existed, and an earlier stream had recorded "every precondition
satisfied" for 42 game days on the strength of that false 3.

## Deliverable

Add **`in_building`** as a deduction everywhere the four live, and
**`construction`** too (an item used in a built construction, a wall or
floor, is equally not available). Specifically:

- `scripts/dfhack/df-overseer-stocks.lua`'s `stocks.availability`: net both,
  through the same `checked_flag` helper (a missing field is a failure, never
  a `false`), and report per-flag counts alongside the existing ones, so a
  caller can see "3 total, 3 in buildings, 0 available".
- `production/blocker.py`'s `DEDUCTION_FLAGS` and `available_quantity`.
- `production/snapshot.py`, wherever it mirrors the flag list.
- `docs/PRODUCTION-MODEL.md` §7: the deduction list becomes six, with this
  incident as the reason, kept in the document's own voice of recording its
  errors rather than hiding them.

**Before adding, check whether any other item flag should be a deduction
too** (for example `in_inventory` on a hauled item, `dump`, `hostile`,
`rotten` for food, `in_chest`/container contents), and **report** what you
find with evidence from DFHack's own structure definitions. Add only the ones
you can justify; list the rest as candidates.

## Tests that matter

- The real case: three boulders, all `in_building`, give **0 available** and
  say why.
- A missing `in_building` field is an unnetted failure, never counted
  available.
- `blocker.find_blocker` on a goal needing a boulder returns BOULDER as the
  blocker when every boulder is in a building.

## Rules

- **Write as you go**: commit on your branch after each milestone and append to
  this file's write-up each time.
- Never write an IP address, hostname or port into a committed file. Do not
  write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`. No em dashes in prose.

## Touched surfaces

`scripts/dfhack/df-overseer-stocks.lua`, `scripts/dfhack/TOOLS.yaml` only if
the output shape note needs it, `production/blocker.py`,
`production/snapshot.py`, their tests, `docs/PRODUCTION-MODEL.md`, and this
handoff doc.

## Done means

Both deductions live in all three places with tests, the real case reads 0
available, other candidate flags are reported with evidence, the full suite
passes (**548 passed / 1 skipped** now, report before and after), and the
write-up says what the next deploy must verify live.
