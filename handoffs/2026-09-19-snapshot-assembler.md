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
