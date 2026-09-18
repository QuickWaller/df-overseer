# Handoff: the live snapshot assembler

Date: 2026-09-19. Offline stream. **No VM, no SSH, no DFHack, no fort.** You
build the translation layer and test it against recorded output shapes; a later
stream points it at the live fort.

Read `CLAUDE.md`, then `docs/PRODUCTION-MODEL.md` §7 (the live layer) and §13,
then `production/blocker.py` and `production/cover.py` **including their
docstrings**, then this.

## Why this stream exists

`blocker.py` and `cover.py` are pure functions over a snapshot **the caller
assembles**. That boundary was deliberate and correct: it is what makes them
testable and keeps the live-read layer joined rather than merged (spec §7).

But **nobody wrote the caller.** So the graph has never been pointed at
Uniboslan, and every test either module has is against a synthetic snapshot.
Meanwhile the fort is in a real crisis whose diagnosis is exactly the shape
`blocker.py` returns:

```
drink -> WELL -> BLOCKS + TRAPPARTS -> stone -> stair to z167 -> not dug
```

That chain was walked **by hand, in chat**. This stream is what makes the code
able to walk it.

## Deliverable

`production/snapshot.py` plus `production/tests/test_snapshot.py`. A pure
translation layer: **tool output in, `find_blocker`/`compute_cover_report`
input out.** No live calls from inside it, same rule as the modules it feeds.

### The contract you are targeting

From `find_blocker`'s own docstring: `stock` maps
`node_id -> {"available": int, "status": str}`, **already netted** on the
caller's side. You are that caller. `available_quantity()` in `blocker.py`
already does the arithmetic over the four deduction flags
(`in_job`, `owned`, `forbid`, `trader`); your job is to feed it correctly
shaped item dicts and map DF's vocabulary onto node ids.

`compute_cover_report` takes its own snapshot shape; read its docstring for the
two distinct population parameters and do not conflate them.

## The gap you will hit, and how to handle it

`scripts/dfhack/df-overseer-stocks.lua` nets **fort ownership** (`trader`,
`garbage_collect`, `removed`) and it is well-commented about why, but as far as
this stream can tell it does **not** expose per-item `in_job`, `owned` or
`forbid`. `blocker.py` needs all four, and the spec is emphatic that this
matters: the fort has already demonstrated the exact failure a totals-based
walk misses, **three empty buckets present and water still undelivered.**

**Do not paper over this.** Do not assume the flags are absent-therefore-false,
because that silently inflates availability, which is the one error this whole
deduction exists to prevent. Instead:

1. Read the tool scripts and establish **exactly** what each does and does not
   return. State your evidence.
2. Where a flag is genuinely unavailable from current tool output, the
   assembler must mark that stock entry's status **`unavailable`**, or carry an
   explicit "unnetted" marker, so a downstream blocker result cannot be
   mistaken for a netted one.
3. Write up precisely what a tool would need to expose to close it. That
   write-up becomes the next tool stream's handoff.

**You may not edit the Lua tools or deploy anything.** A parallel stream owns
the VM and the fort right now.

## Tests that matter more than coverage

- **The four deductions survive translation.** An item flagged `in_job` does
  not count toward available, end to end from tool-shaped input.
- **An unnetted flag never reads as a clean zero.** If `forbid` cannot be
  determined, the result says so rather than implying full availability.
- **The well chain assembles.** Build a snapshot from the real recorded figures
  (BUCKET 3, CHAIN 3, BLOCKS 0, TRAPPARTS 0, logs 3, boulders 0) and assert
  `find_blocker` on a well goal returns BLOCKS or TRAPPARTS as the blocker,
  not something further up. This is the test that proves the stream worked.
- **Unknown node ids are an error, not a silent skip.** A material the graph
  does not know about must surface, never vanish.

## Rules

- No new runtime dependency. No coordinates anywhere.
- **A lookup that can silently miss must report the miss.**
- **Verify the verification**: confirm your check could detect the problem.
- Do **not** write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`.
- No em dashes in prose.

## Touched surfaces

`production/snapshot.py` (new), `production/tests/test_snapshot.py` (new), and
this handoff doc. **Nothing else.**

**Do not touch** `production/extract.py`, `production/tests/test_extract.py`,
`production/tests/test_consumption.py` or `production/tests/fixtures/**`: a
parallel stream owns those. Treat `schema.py`, `store.py`, `blocker.py` and
`cover.py` as **read-only**. If you believe one of them must change, report it
rather than editing it.

## Done means

`production/snapshot.py` exists, the named tests pass, the full suite still
passes (364 passed / 1 skipped right now, report before and after), the well
chain assembles and returns the right blocker, and the write-up at the bottom
of this file states exactly which live flags are reachable today and which need
a tool change, with evidence.

## Write-up: which live flags are reachable today, with evidence

Built `production/snapshot.py` (translation functions only, no live calls) and
`production/tests/test_snapshot.py` (16 tests). Full suite: **364 passed / 1
skipped before, 380 passed / 1 skipped after** (16 new, 0 regressions),
`python -m pytest -q` from the repo root.

**Reachable today: `trader` only, one of the four.** Grepped every
`df-overseer-*.lua` for `in_job|forbid|flags.owned|UNIT_HOLDER`: the only hit
is `df-overseer-stocks.lua`, and only in its header comment recording that
`flags.owned` was checked and found to be *personal* (per-dwarf) ownership,
not fort-vs-caravan -- never read into a return value. All three tools that
report fort-owned counts (`df-overseer-stocks.lua` `is_fort_owned`,
`df-overseer-well.lua` `is_fort_owned_item`, `df-overseer-workshop.lua`'s
`count_fort_owned`) share one predicate, duplicated verbatim across the three
files (each file's own header says why -- "stocks.lua not a touched surface"):
`not flags.trader and not flags.garbage_collect and not flags.removed and not
is_on_hidden_tile(item)`. So of `blocker.DEDUCTION_FLAGS`
(`in_job`/`owned`/`forbid`/`trader`), only `trader` is netted by any shipped
tool, plus two extra exclusions neither module asks for
(`garbage_collect`/`removed`) and a project-specific hidden-tile guard.

**Not reachable today: `in_job`, `owned`, `forbid` — and not because nobody
looked, because the count is thrown away before it's returned.**
`count_fort_owned` (`df-overseer-well.lua` lines 206-218, duplicated in
`df-overseer-workshop.lua`) folds straight to an integer (`n = n + 1` per
passing item) and returns only that integer. `df-overseer-stocks.lua`'s
buckets are the same shape one level up: `units`/`item_count`/`rotten_units`/
`unreachable_units` sums, never a per-item record. There is no item list
downstream of either tool for a caller to net further — the information is
gone by the time the JSON prints, not merely unread.

**The flags themselves are readable in principle.** `df-overseer-orders.lua`'s
own header (tick 227160, correcting an earlier handoff's framing) reports "5
buckets exist, 3 fort-owned (ids 81, 149, 150), empty, unforbidden,
unclaimed, no holder" — `forbid` and job-claim state were read live, by hand,
via an ad hoc `dfhack-run lua` probe in a chat session. That is evidence the
underlying DFHack fields exist and resolve on this install, not evidence any
committed tool exposes them programmatically. Closing the gap needs a tool
change — a new command, or an extension of an existing one, that walks the
same item vectors `df-overseer-stocks.lua` already walks and additionally
returns `item.flags.in_job`, `item.flags.owned` (plus its `UNIT_HOLDER` ref,
per spec §7's own read instruction), and `item.flags.forbid` per item, not
folded into a sum. **This stream did not make that change** (Lua tools are
off-limits this stream, a parallel stream owns the VM); this paragraph is
the next tool stream's brief.

**How `snapshot.py` handles the gap rather than papering over it.** Two
paths, two honesty levels (full detail in the module's own docstring):

1. `fort_owned_counts_to_stock` — today's actual tool shape (a `DF_TYPE ->
   count` dict, exactly `well.lua`'s/`workshop.lua`'s `fort_owned` blocks).
   Every entry it produces is `status=schema.UNAVAILABLE` with an explicit
   `unnetted_flags=("in_job","owned","forbid")` marker and a `reason` string
   naming the source and what's missing — never `schema.MEASURED`, because
   that would claim a netting that didn't happen. The numeric count is still
   carried through unchanged (dropping it would be its own failure mode:
   under-by-everything instead of honestly-uncertain), so `blocker.py`'s
   arithmetic still runs correctly, only the provenance is downgraded.
2. `stock_from_items` / `items_for_cover` — the shape `blocker.py`/`cover.py`
   actually document (item dicts carrying all four deduction flags). No
   shipped tool returns this yet; these exist for the day one does, proven
   against hand-built tool-shaped fixtures now rather than only once a live
   tool exists.

Both paths route unknown DF types through `UnknownNodeError` (never a silent
skip), and `merge_stock` raises `StockConflictError` rather than silently
picking a side when two tool readings disagree on the same node id.

**The proof test.** `test_well_chain_assembles_and_blocker_names_blocks_or_trapparts`
(`production/tests/test_snapshot.py`) builds a minimal well graph (BLOCKS,
BUCKET, CHAIN, TRAPPARTS all AND-required, no producer modelled for any —
this stream proves the assembler, not the real production graph, which a
parallel stream owns), assembles stock from the real recorded figures
(`Working.md`, "The fort cannot drink, and the pond cannot be dug to": BUCKET
3, CHAIN 3, BLOCKS 0, TRAPPARTS 0, merged with logs 3/boulders 0 from
`df-overseer-workshop`'s `building_material_report`, via
`fort_owned_counts_to_stock` + `merge_stock`), and asserts
`blocker.find_blocker("BUILDING:WELL", graph, stock)` reports `blocked=True`
with `blocker.target` in `("BLOCKS", "TRAPPARTS")`, `quantity_available=0`,
`quantity_short=1`, and never `BUCKET`/`CHAIN` (both present) or the well
itself. It passes. A second test in the same file confirms the same graph
reads `blocked=False` once BLOCKS and TRAPPARTS are stocked, so the assertion
is not trivially true for any stock.

**Not touched, as instructed:** `schema.py`, `store.py`, `blocker.py`,
`cover.py` (all read-only; nothing here required changing them),
`production/extract.py`, its tests, or `production/tests/fixtures/**`.
