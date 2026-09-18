# Handoff: kill the silent-zero pattern in four tool functions

Date: 2026-09-19. **Offline build stream. No VM, no SSH, no deploy.**

Read `CLAUDE.md`, then `research/2026-09-19-unverified-claims-audit.md`
(finding 3, the one this fixes), then `docs/PRODUCTION-MODEL.md` §13's
correction block, then `scripts/dfhack/df-overseer-labor.lua`'s `set_labor`
(the pattern already fixed correctly once), then this.

## Why this stream exists

**This project already shipped this exact bug, wrote it up, and then left four
copies of it in place.**

The original: a probe reported `FEED_WATER_WOUNDED` enabled on "0 of 15". That
token **does not exist**. The probe looked the name up, skipped on failure, and
printed its untouched counter as `0`, so a missing field and a genuine zero
were indistinguishable in its output. Conclusions were drawn from that zero.
`docs/PRODUCTION-MODEL.md` §13 records it against itself, and the rule that
came out of it is: **a lookup that can silently miss must report the miss.**

`df-overseer-labor.lua`'s `set_labor` was rewritten to refuse on an unknown
name. **The fix never propagated.** A read-only audit found four call sites
still doing it, confirmed by reading the source:

| File | Function | Behaviour |
|---|---|---|
| `df-overseer-trees.lua:140-153` | `labor_enabled_count` | `local code = df.unit_labor[labor_name]; if not code then return 0 end` |
| `df-overseer-workshop.lua:178-190` | (per audit) | same shape |
| `df-overseer-workshop.lua:192-205` | (per audit) | same shape |
| `df-overseer-well.lua:206-218` | `count_fort_owned` | `if not ok or not vec then return 0 end` |

The first is **character for character the bug that caused the incident**, in a
tool the agents actually call.

**No evidence any of them is wrong today.** The hardcoded names look plausible.
That is exactly the point: nothing guards against the next typo, the next
DFHack version bump, or the next renamed enum, and the failure is silent and
produces a confident number.

## Deliverable

Make each of the four report the miss instead of returning a bare zero. Follow
`set_labor`'s existing approach rather than inventing a new one; the repo has
already decided what this looks like, and consistency matters more than your
preference here.

The distinction each caller must be able to draw:

- **"the lookup failed"** (the name or vector does not exist on this install)
- **"the lookup succeeded and the answer is zero"**

Existing precedent for the honest-gap idiom: `df-overseer-stuckjobs.lua`'s
`idle_ticks=null`, and `df-overseer-stocks.lua`'s treatment of an item whose
position cannot be resolved (counted in **neither** bucket). Prefer an existing
idiom over a new one.

Then **grep the whole of `scripts/dfhack/` for the same shape** and report any
further instances the audit missed. Four were found by one pass; treat that as
a lower bound, not a complete list.

## Rules that bite here

- **Do not change what any function returns on the success path.** This is a
  failure-path fix. If a caller currently gets a correct number, it must still
  get that number, unchanged.
- **Check every caller.** Making a function return something new on failure
  breaks any caller that assumed a number. Trace them and update them, or say
  why none needed it.
- **Verify the verification.** For each fix, state how you would tell the
  difference between "reports the miss" and "still silently zero" from the
  tool's actual output. If you cannot tell from the output, the fix is not
  done.
- **No coordinates in any output.** Hard commitment, `docs/PURPOSE.md` #1.
- **Do not deploy and do not touch the VM.** Another stream owns it.
- Do **not** write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`.
- No em dashes in prose.

## Touched surfaces

`scripts/dfhack/df-overseer-trees.lua`,
`scripts/dfhack/df-overseer-workshop.lua`,
`scripts/dfhack/df-overseer-well.lua`, and this handoff doc.

**Do not touch `scripts/dfhack/df-overseer-stocks.lua`,
`scripts/dfhack/TOOLS.yaml`, `agents/*/tools.yaml`, `dfmcp/tests/` or
`tests/`**: a parallel stream owns all of those. If your fix genuinely needs a
schema or allowlist change, **report it, do not make it.**

## Done means

All four report the miss, no further instances remain unreported, every caller
is accounted for, the full suite still passes (**380 passed / 1 skipped** right
now, report before and after), and the write-up says how each fix is
observable from output.

## Outcome, 2026-09-19

All four fixed, following `set_labor`'s existing `ok/value, err` return-pair
shape (not a new idiom): a failed lookup now returns `nil` for the count plus
a non-nil error string, instead of a bare `0`. A genuine zero is unchanged:
same integer, same success path, no error string.

- `df-overseer-trees.lua:150-163` `labor_enabled_count`: `code == nil or
  code < 0` (matching `set_labor`'s own check, not just `not code`) now
  returns `nil, "unknown labor: " .. name"`. Both callers
  (`find_trees:232`, `fell_trees:291`) updated to add a sibling
  `citizens_with_labor_error` field alongside the existing
  `citizens_with_labor` field.
- `df-overseer-workshop.lua:186-197` `count_fort_owned` and `:200-212`
  `labor_enabled_count`: same fix, same shape. `building_material_report`
  (BOULDER/WOOD/BLOCKS) and `requirements_for` (labor, and the container
  count when `needs_container` is set) each look their inputs up
  independently and now carry a `fort_owned_errors` table (only the entries
  that actually failed; the whole field is `nil`, not an empty table, when
  everything resolves) alongside `fort_owned`, plus
  `citizens_with_labor_error`/`fort_owned_containers_error` next to their
  respective counts.
- `df-overseer-well.lua:206-225` `count_fort_owned`: same fix. `requirements`
  (BLOCKS/BUCKET/CHAIN/TRAPPARTS) carries the same `fort_owned_errors`
  pattern as workshop.lua's `building_material_report`.

**Every caller checked**, not assumed: `labor_enabled_count` and
`count_fort_owned` are called from 7 sites total across the three files
(`grep -n` confirms: trees.lua 2, workshop.lua 5, well.lua 4 counting the
four `requirements()` calls), and every one now captures and threads the
second return value through to its own JSON output rather than discarding
it. No caller outside these three files calls either function (`reqscript`
is never used to import them elsewhere) and no caller assumed a bare
integer return that would now break on the (previously impossible) `nil`
case, because `nil` was never returned before.

`production/snapshot.py`'s `fort_owned_counts_to_stock` was checked as a
downstream consumer of exactly this shape (`well.lua`'s and `workshop.lua`'s
`fort_owned` dicts) since its own docstring names both tools by path and
line. It is not wired to any live tool call today, only exercised in
`production/tests/test_snapshot.py` against hand-built fixtures that never
touch the Lua source, so this fix cannot regress it. Its typed contract
(`Mapping[str, int]`, every present key a real int) is preserved on the
success path: a failed lookup **omits that key from `fort_owned` entirely**
rather than writing a JSON `null` into it (in Lua, assigning a table field
`nil` in a constructor is the same as never setting it, so `fort_owned =
{BOULDER = boulder}` with `boulder == nil` produces no `BOULDER` key at all,
not a null one) -- so if `fort_owned_counts_to_stock` is ever wired to live
output, a `for df_key, count in fort_owned.items()` loop still only ever
sees real integers, never `None`. This was flagged, not fixed, since
`production/snapshot.py` is out of this stream's touched surfaces; no schema
or allowlist change is needed there today, only a note for whoever wires it
live: check `fort_owned_errors` before trusting a `fort_owned` dict as
complete.

**Observable from output, per fix** (the "verify the verification" bar):
run any of the three tools' `find`/`build` command against a labor name or
item type edited to something that does not resolve (e.g. temporarily typo
`CUTWOOD_LABOR` to `CUTWOOOD` or a `KIND_INFO` labor to `MASONN`) and the
JSON now prints an explicit `*_error` string (`"unknown labor: CUTWOOOD"` or
`"unknown item type: BOULDERR"`) with the paired count field simply absent
from the object, never present as `0`. Before this fix, the same edit
printed a normal-looking `0` with no error field at all, i.e. identical
output to a real, resolved zero -- indistinguishable, which is exactly what
made the original `FEED_WATER_WOUNDED` incident possible. This was checked
by reading the code path directly (both branches of the new `if` are
mutually exclusive and one always sets the `_error` string), not run live,
per this stream's offline-only constraint.

## Further instances found, beyond the four

A grep pass across all 20 `scripts/dfhack/df-overseer-*.lua` files for the
same shape (`return 0` after a failed pcall/lookup, `df.X[NAME]` lookups,
`items.other[...]` lookups, every `local function ...count...` definition)
turned up no further **silent-zero** instances outside the four already
fixed. What it did turn up, reported per the handoff's own "lower bound, not
complete" framing:

- **Already correct, no action needed** (checked for calibration, not
  padding): `df-overseer-orders.lua`'s `workshop_exists_count` already
  returns `nil` (not `0`) on an unresolved `workshop_type`, threaded straight
  through to its `workshop_exists` output field. `df-overseer-stockpile.lua`'s
  `total_tiles` (returns `nil, false` if `containsTile` cannot be called at
  all) and `occupied_tiles` (returns `nil` if `getStockpileContents` fails)
  are both already honest. `df-overseer-stockpile.lua`'s `read_links` pairs
  every `count` with its own `resolved` boolean, so a `count = 0` from a
  failed vector lookup is never presented as trustworthy alone.
  `df-overseer-diff.lua:294`'s `df.announcement_type[rep.type] or
  tostring(rep.type)` is a display-label fallback to the raw numeric code,
  not a fabricated confident name, so it cannot be mistaken for a real
  measurement the way a bare `0` count can.
- **A related but different-shaped risk, not touched**: `df-overseer-
  trees.lua`'s own `count_fort_owned_axes` (line 188, inside this stream's
  touched surface but not one of the four named call sites) reads
  `df.global.world.items.other.WEAPON` with no `pcall` at all. If `WEAPON`
  ever stopped resolving, `#vec` on a `nil` vector would throw a hard Lua
  error visible in the console, not silently return `0` -- a louder, more
  honest failure than the bug this stream fixes, but still an unguarded
  hardcoded name with no graceful message. `df-overseer-stocks.lua` (not a
  touched surface here) has the identical unguarded-dot-access shape four
  times over (`items.other.DRINK`/`.FOOD`/`.ANY_EDIBLE_RAW`/`.SEEDS`,
  lines 260-286). Left for whichever stream next touches either file, since
  fixing it here would exceed this stream's scope and, for stocks.lua,
  cross into the parallel stream's owned surface.

## Test counts

Before: 380 passed, 1 skipped (`python -m pytest -q`, this worktree, ambient
Python 3.12 -- this repo's Python suite does not exercise the Lua tools at
all, so this is a no-regression check on everything else, not a check on
this fix itself).
After: 380 passed, 1 skipped, identical. No Lua interpreter was available in
this environment to run the `.lua` files directly (`luac`/`lua` not on
`PATH`); the fix was verified by direct code reading (both return paths of
each changed function, brace/paren balance checked file-by-file) and by
tracing every caller by `grep`, not by executing DFHack's Lua runtime, which
requires the live game process this stream is barred from touching.
