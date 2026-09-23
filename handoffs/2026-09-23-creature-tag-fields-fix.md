# Stream: fix the creature tag reads in df-overseer-threat.lua's class_flags()

**Written and executed** 2026-09-23. **Status:** done, offline. **Offline
code and tests only. No deploy, no VM, no unpausing.** The fort is paused
and stays paused. Sonnet executor, worktree-isolated.
**No push. No attribution lines in any commit.** No em dashes.

## Why

`evals/live/2026-09-23-attention-deploy/README.md`'s "CRITICAL CHECK" section
found, live, that `class_flags()` in the deployed `df-overseer-threat.lua`
read every one of its six raw creature tags at the wrong struct level, with
two further errors on top:

- The reads used `df.global.world.raws.creatures.all[unit.race].flags.<NAME>`
  -- the creature level. Verified live against a real kea (unit 513,
  `BIRD_KEA`, DFHack 53.16-r1.1), twice (once by the deploy agent, once
  independently by the orchestrating session): that level has no per-tag
  members at all, only aggregates (`HAS_ANY_LARGE_PREDATOR`,
  `HAS_ANY_CURIOUS_BEAST`, `HAS_ANY_BENIGN`, `HAS_ANY_MISCHIEVOUS`, no
  building-destroyer aggregate at all). `cr.flags.CURIOUSBEAST_ITEM` errors
  "not found", it does not read false.
- The correct level is the caste: `cr.caste[unit.caste].flags.<NAME>`.
- The deployed spelling `CURIOUSBEAST_ITEM`/`_EATER`/`_GUZZLER` (no
  underscore between CURIOUS and BEAST) is not a member either. The correct
  spellings are `CURIOUS_BEAST_ITEM`/`_EATER`/`_GUZZLER`.
- `BUILDINGDESTROYER` is not a flag bit anywhere. It is
  `cr.caste[unit.caste].misc.buildingdestroyer`, a plain integer, so the
  correct test is `> 0`.

Net effect the deploy's own postmortem named: because the deployed code
always read `is_curiousbeast_item` as `false` regardless of the truth, a real
kea closing in on the fort could never escalate past `record_only` to the
`slow` tier `research/2026-09-23-wildlife-threat-classes.md` S:E1 designs for
exactly that case -- a silent miss that survived only because none of the
wrongly-read tags happen to gate the `pause` tier.

## What this stream did

### 1. Corrected `class_flags()` in `scripts/dfhack/df-overseer-threat.lua`

All six reads now go through the caste level with the right spellings:

- `craw.caste[unit.caste]` resolves the caste first (pcall-guarded, `nil` on
  any failure, same as the existing `craw` resolution).
- `safe_caste_flag(caste, name)` reads `caste.flags[name]` for
  `LARGE_PREDATOR`, `CURIOUS_BEAST_ITEM`, `CURIOUS_BEAST_EATER`,
  `CURIOUS_BEAST_GUZZLER`, `BENIGN`, `MISCHIEVOUS`.
- `safe_caste_buildingdestroyer(caste)` reads `caste.misc.buildingdestroyer`
  and tests `> 0`, not a flag bit.

### 2. A failed read is now distinguishable from a genuine false

This was the explicit ask, and the reason the bug went undetected through a
whole deploy: the old code's `pcall`-guard collapsed *every* failure mode
(wrong level, wrong spelling, a genuinely absent tag) to the same `false`,
indistinguishable from "checked and it's false."

Fix: each `safe_caste_*` helper now returns `(value, ok)` -- `ok` is `false`
only when the read itself failed (wrong field name, nil caste, etc.), never
when the field legitimately reads false. `class_flags()` collects every
failing field name into a `read_failures` array. What a caller now sees on a
failed read:

- **In the tool's own JSON output** (`scan`'s per-candidate `class_flags`
  object): a non-empty `read_failures` array naming exactly which caste
  fields could not be read this call. A genuinely false field is absent from
  that array and reads `false` as before -- so "false" and "unreadable" are
  now visibly different things in the same output, not conflated.
- **In the DFHack log/journal**: a non-empty `read_failures` triggers one
  `dfhack.printerr` call (itself `pcall`-wrapped so a partially-stubbed or
  offline `dfhack` table can't turn logging into a crash) naming the race,
  caste index, and the failing field names.

The gating default on a failed read is still `false` (the safe direction --
a failed read never invents a `true` that could wrongly escalate a tier),
but it is no longer silent. A future rename of any of these six fields will
show up in both the JSON output and the log the moment a live scan runs it,
instead of quietly reclassifying every candidate as harmless the way this
bug did.

### 3. Tests, `tests/test_wildlife_tier_logic.py`

Nineteen tests now pass (thirteen pre-existing, six new):

- `test_class_flags_reads_caste_level_not_creature_level`: pins
  `craw.caste[unit.caste]`, `caste.flags[name]`, and
  `caste.misc.buildingdestroyer` as required source substrings.
- `test_class_flags_uses_correct_curious_beast_spelling`: pins the correct
  `CURIOUS_BEAST_ITEM`/`_EATER`/`_GUZZLER` spellings present, and the old
  `"CURIOUSBEAST_ITEM"`/etc. (quoted, i.e. used as a live flag-name argument,
  not just mentioned in an explanatory comment) absent.
- `test_class_flags_tests_buildingdestroyer_as_integer_not_flag_bit`: pins
  the `> 0` integer test.
- `test_class_flags_surfaces_read_failures_distinct_from_false`: pins
  `read_failures` and `dfhack.printerr` both present.
- `test_live_kea_values_slow_tier_when_closing_in` and
  `test_live_kea_values_record_only_when_not_closing`: feed the live kea's
  own recorded caste values (`LARGE_PREDATOR=false`,
  `CURIOUS_BEAST_ITEM=true`, `BENIGN=false`, `MISCHIEVOUS=false`,
  `buildingdestroyer=0`) through the existing `classify_tier` Python port and
  confirm the corrected reads land that kea in `slow` when closing in
  (68 -> 40 tiles) and `record_only` otherwise (68 tiles, first sighting,
  outside close range) -- both required acceptance criteria for this task.

These are still a hand-copied Python **port** of `classify_tier`'s control
flow (this environment has no Lua interpreter, same limitation the prior
in-game stream flagged), not an execution of the real `.lua` bytes. The
existing `test_port_mirrors_lua_source` drift guard and the four new
source-pinning tests above are the only defence against the port silently
diverging from the real file; they were not previously sufficient to catch a
wrong field name/level because that lived entirely inside the untested
`class_flags`/`safe_creature_flag` functions, which the port never modeled.
This stream's new tests close that specific gap for these six fields, but
the port as a whole is still not a substitute for a live re-run.

### 4. Other files checked for the same wrong-level pattern

Searched every `scripts/dfhack/*.lua` for `raws.creatures.all`,
`creature_raw`, `caste_raw`, and bracket-indexed `.flags[...]` reads. Two
other files use bracket-indexed flag reads: `df-overseer-stocks.lua`
(`item.flags[flag_name]`, an item struct, unrelated) and
`df-overseer-workjob.lua` (`job.flags['repeat']`, a job struct, unrelated).
Neither touches `df.global.world.raws.creatures.all` or any creature/caste
raw struct. **`df-overseer-threat.lua` is the only file in this repo that
reads creature raw tags**, so no migration outside it was needed or done.

### 5. Documentation updated

`scripts/dfhack/TOOLS.yaml`'s `df-overseer-threat.lua` entry updated: the
`class_flags` field list now shows the correct spellings and the
caste/integer read, and a new dated note records the live-found bug, the
fix, and that it is **still not re-verified live** (this was another offline
stream).

## What a deployer must re-verify live

This stream is offline, same hard line as the one that introduced the bug.
The corrected `class_flags()` has **not** been executed against a live game.
Before trusting a live run's tier assignment, re-run the exact check the
deploy agent and the orchestrating session already used once each:

```
:lua =df.global.world.raws.creatures.all[SOME_KEA_UNIT.race].caste[SOME_KEA_UNIT.caste].flags
:lua =df.global.world.raws.creatures.all[SOME_KEA_UNIT.race].caste[SOME_KEA_UNIT.caste].misc.buildingdestroyer
```

against a real kea (unit 513 if it's still on the map) and confirm
`class_flags()`'s own output now reads `is_curiousbeast_item = true` for it
(the deployed code before this fix always read `false` here), with an empty
`read_failures` array. Also worth deliberately breaking one field name
temporarily to confirm `read_failures` and the `dfhack.printerr` log line
actually appear as designed, since that path has only been exercised by the
Python port's source-pinning tests, never by a real failing read against
live game data.

## Hard lines (respected)

- Offline only: no ssh, no VM, no deploy, no live DFHack call, no unpausing.
- No model call. No armok capability. No map, coordinate-free output
  (unchanged from the existing file; this stream touched only the six raw
  reads and their surrounding tests/docs).
- Did not touch `conductor/`.
- Did not write `Working.md`, `decisions/DECISIONS.md`, or `memory/`.
- No attribution lines in any commit. No em dashes.

## Touched surfaces

`scripts/dfhack/df-overseer-threat.lua`, `scripts/dfhack/TOOLS.yaml`,
`tests/test_wildlife_tier_logic.py`, this doc.

## Result

**Status: done, offline.** Branch: `worktree-agent-a8c675eafc23aaf30`,
commit `6cee5fc` on top of `main` (merged clean via `git merge --ff-only
main`, no conflicts).

Both suites green:

- Ambient `python -m pytest`: **1348 passed, 3 skipped** (was 1342 passed / 3
  skipped before this stream; +6 net, the six new tests above).
- `.venv-dfmcp` (venv lives in the main checkout, not this worktree; invoked
  as `/c/website-projects/df-automation/.venv-dfmcp/Scripts/python -m pytest
  dfmcp/tests` from inside the worktree) `dfmcp/tests`: **652 passed**,
  unchanged (this stream did not touch `dfmcp/`).

Not fixed or touched: `DEFAULT_CLOSE_RANGE_TILES`'s own unresearched
10-tile placeholder (unrelated to this bug, still flagged in the file's own
header), the flying/swimming reachability blind spot, and anything under
`conductor/`.
