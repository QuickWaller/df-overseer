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

## Write-up (done, offline, no VM touched)

Executed by a worktree-isolated stream, 2026-09-19, no VM contact, no
deploy. Test count: **548 passed / 1 skipped before, 552 passed / 1 skipped
after** (ambient `python -m pytest` at repo root; 4 new tests added, 0
removed, 0 newly failing).

### DFHack structure evidence gathered first

Fetched `df-structures`' own `df.item.xml` from upstream (GitHub, master)
rather than trusting memory or the earlier stream's summary. The base
`item` class carries exactly two flag words, `flags` (`item_flags`) and
`flags2` (`item_flags2`); there is no `flags3` on the base item type (the
"`flags3.hard`" reference in an earlier decision row is a workshop-reaction
spec field, unrelated to this stream). Relevant confirmed fields, quoted
from the XML's own comments:

- `in_building` -- "Part of a building (including mechanisms, bodies in
  coffins)" -- **live-confirmed** on Uniboslan (the three shale boulders).
- `construction` -- "Material used in construction" -- structurally
  confirmed, **not live-verified** (no construction has ever existed on
  this fort).
- `hostile` -- "Item owned by hostile".
- `in_inventory` -- "Item in a creature, workshop or container inventory".
- `dump` -- "Designated for dumping" (`DUMP_DESIGNATED`).
- `melt` -- "Designated for melting" (`MELT_DESIGNATED`).
- `rotten` -- "Rotten food" (already read by this file, informational only).
- `encased` -- "Item encased in ice or obsidian" (`IMBED`).
- `item_flags2.utterly_destroyed` -- `UTTERLY_DESTROYED_OR_TRANSFORMED`.

### What changed, per file

- **`scripts/dfhack/df-overseer-stocks.lua`**: `count_availability` now
  reads `in_building` and `construction` through `checked_flag`, the same
  helper `in_job`/`forbid`/`owned` already use (a read failure is an
  honest `unnetted` tally, never a silent `false`). The availability gate
  now requires all five marginal flags readable and false (was three).
  Two new output fields, `in_building_units`/`in_building_item_count` and
  `construction_units`/`construction_item_count`, alongside the existing
  per-flag breakdown -- a caller now sees "3 total, 3 in_building,
  0 available" instead of a bare 3. The file's header records the
  incident and lists every candidate flag considered and why it was or
  wasn't added (see below), plus notes that the earlier "four exact
  deductions" summary block is superseded, kept for honest history rather
  than rewritten.
- **`production/blocker.py`**: `DEDUCTION_FLAGS` grows from four entries to
  six: `("in_job", "owned", "forbid", "trader", "in_building",
  "construction")`. `available_quantity`'s docstring and the module's own
  "fifth case" comment (trade depot) were updated so the ordinal no longer
  collides with the two new deductions.
- **`production/snapshot.py`**: `UNNETTABLE_TODAY` grows the same way (now
  five entries), since `well.lua`'s and `workshop.lua`'s integer-only
  `fort_owned` counts still can't net either new flag -- and one of those
  two tools is exactly what read the false "3 available" this stream
  traces back to. Every docstring paragraph naming "four deductions" was
  updated to six. `translate_items`/`stock_from_items`/`items_for_cover`
  needed no logic change: they already iterate `DEDUCTION_FLAGS` from
  `blocker.py`, so the extension reaches them automatically.
- **`production/cover.py`**: **not touched**, and did not need to be.
  `split_stock` imports `DEDUCTION_FLAGS` directly from `blocker.py`
  (`from .blocker import DEDUCTION_FLAGS`), so its netting picked up
  `in_building`/`construction` for free. Confirmed by reading the import
  and the one call site (`for flag in DEDUCTION_FLAGS`); `test_cover.py`'s
  `_item()` builder uses `.get(flag)`-style construction with the two new
  flags defaulting to `False` when absent, so no existing cover test
  needed editing (verified: full suite green, no cover test touched).
- **`scripts/dfhack/TOOLS.yaml`**: the `availability TYPE` command's
  `notes` block updated -- the four-deduction summary marked "AT THE TIME"
  rather than rewritten, a new paragraph recording this stream's fix in
  the same voice as the existing "FIXED"/"SUPERSEDED" annotations
  elsewhere in this file, and the "Output per call" paragraph lists the
  two new fields. `live_deployed`/`verified` left as `false`/`unverified`
  -- still true, this stream made no VM contact.
- **`docs/PRODUCTION-MODEL.md` §7**: the deduction table grows to six rows;
  a new paragraph records the incident by name, in the section's own
  voice, explicitly saying the table itself was wrong for one day rather
  than describing this as a clean addition. The trade-depot "fifth case"
  line was reworded ("another case") since it's no longer the fifth. A new
  "candidate flags checked and not added" block lists all six candidates
  with the same reasoning as the Lua header. §17 gained two entries: the
  `construction`-unverified item, and a pointer to the candidate-flag
  list with `utterly_destroyed` named as the strongest follow-up.
- **Tests added**: `production/tests/test_blocker.py` gained
  `test_available_quantity_ignores_in_building_and_construction_items`,
  `test_available_quantity_all_boulders_in_building_gives_zero` (the exact
  fort figure: three boulders, all `in_building`, nets to 0), and
  `test_find_blocker_names_boulder_when_every_boulder_is_in_a_building`
  (end-to-end: `available_quantity` nets three in_building boulders to 0,
  the resulting stock feeds `find_blocker`, and the well's mechanism still
  correctly names BOULDER as the blocker). `production/tests/
  test_snapshot.py` gained `test_stock_from_items_nets_in_building_the_
  fort_own_incident` and had `test_stock_from_items_nets_all_four_flags_
  independently` renamed/extended to `..._all_six_...` with the two new
  flags; `test_fort_owned_counts_never_claim_full_netting`'s
  `unnetted_flags` assertion was updated to the five-entry set.

### Candidates found, added vs not (see structure evidence above for the
### field-level facts)

**Added** (in scope, justified by direct DFHack structure evidence plus
the live incident): `in_building` (live-confirmed), `construction`
(structurally justified, unverified live).

**Not added**, each with reasoning recorded in three places (the Lua
header, the doc's §7, and here):

1. `hostile` -- same shape as `trader` (an ownership-exclusion, not a
   claim-on-fort-stock flag), plausible enough to fold into
   `is_fort_owned` someday, but no hostile-owned item has ever been
   sampled live on this install and this is an offline stream.
2. `in_inventory` -- explicitly **rejected**, not just parked. The
   handoff's own suggested framing ("in_inventory on a hauled item")
   undersells how broad this flag actually is: DFHack's own comment says
   it covers any item "in a creature, workshop or container inventory",
   which includes ordinary barrel/bin-stored stockpile goods. Netting on
   it would deduct most of the fort's correctly-stored food and drink from
   every count -- the same failure class ("a confident, specific, false
   number") this whole stream exists to fix, just inverted.
3. `dump` / `melt` -- plausible (vanilla DF is believed to exclude
   forbidden items from job material selection, and dump/melt-designated
   items are believed to behave the same way), unverified, and this fort
   has never had one to sample.
4. `rotten` as a hard deduction -- deliberately left alone. This project
   already computes `rotten_units` informationally
   (`df-overseer-stocks.lua`, unchanged by this stream) but has never
   folded it into `available`. Whether rotten food should count as
   unavailable is a doctrine question (some game states still permit
   eating it), not a pure structural fact like the other five deductions,
   so it does not belong in this stream's mechanical fix.
5. `encased` -- likely already shows up as `unreachable` via the existing
   walkable-group check, since an item embedded in ice or obsidian cannot
   sit on an ordinarily-walkable tile. Unconfirmed live. Also worth
   noting precisely: `unreachable_units` (like `rotten_units`) is
   informational only in this tool today and has never been subtracted
   from `available_units` either, in either the four-flag or the new
   six-flag gate -- reachability and ownership/claim status are kept as
   two separate questions by this design, on purpose, not an oversight
   this stream should silently fix.
6. `item_flags2.utterly_destroyed` -- the strongest remaining candidate.
   Structurally identical to the already-implemented `garbage_collect`/
   `removed` "this item is already gone" exclusion in `is_fort_owned`,
   just on the item's second flags word instead of the first. Not added
   this stream, to keep the change to exactly what was asked plus what
   could be justified from the structure definitions alone without a live
   check; flagged as the first thing a live-access follow-up should try.

### What the next deploy must verify live

1. **The headline fix**: redeploy `df-overseer-stocks.lua` to VM 103 and
   run `dfhack-run df-overseer-stocks availability BOULDER` against
   Uniboslan's current state. Expect `available_units: 0`,
   `in_building_units: 3` (or whatever the live boulder count is by then --
   a mining stream was dispatched alongside this one), and
   `flag_read_errors: []` (confirms `in_building`/`construction` are real,
   readable fields on this DFHack build, not just present in the XML
   source this stream read).
2. **`construction`'s live behavior is still completely unverified.** If
   Uniboslan ever gets a construction (a wall, floor, or similar), rerun
   `availability` on the material used and confirm `construction_units`
   reads nonzero and matches DFHack's own construction-material accounting
   -- this stream could not test this at all, offline.
3. Re-verify `owned_ref_check.verified_offline` still reads `true` after
   redeploy (unrelated to this stream's change, but worth a sanity check
   since the same file was touched).
4. If a live session has spare time: sample one `hostile=true` item and
   one `flags2.utterly_destroyed=true` item, if either can be found or
   provoked safely, to move those two candidates from "structurally
   justified" to "live-confirmed or ruled out" -- see the candidate list
   above.
