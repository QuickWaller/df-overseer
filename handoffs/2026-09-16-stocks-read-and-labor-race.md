# Handoff: fort-owned stocks read tool, its live signal, and the `set_labor`/`autolabor` race

**Dispatched** 2026-09-16 by the orchestrating session. **Agent:** `executor`,
Sonnet, worktree-isolated. **Status:** dispatched.

## Why this stream exists

The fort has **zero fort-owned food and zero fort-owned drink** and nobody
could see it. On 2026-09-16 the orchestrator counted 234 food and 50 drink on
the map and reported the fort fed; every one of those items was
`flags.foreign`, sitting in merchant wagons. The user caught it from the
screen. Re-verified live by the orchestrator today, fort paused: food own=0,
drink own=0, 15 citizens.

Two independent research passes have now named the same thing as the sharpest
gap in the project:

- `research/2026-09-16-food-and-drink-logistics.md`: the biggest missing
  **read** tool is one that distinguishes fort-owned stores from foreign goods.
- `research/2026-09-16-opening-priority-ladder.md`: the opening ladder's most
  valuable predictions ("fort-owned drink rises above zero") are **unwritable
  today**, because `learning/live_signals.py`'s closed registry has no
  `stocks.*` signal. Verified at source by the orchestrator: `SIGNAL_KINDS` has
  exactly six entries, all population/alerts/stuck-jobs/landmark.

So this is not one tool, it is the gate on the whole learning loop. Without it
the architect cannot make a food-or-drink prediction, the grader cannot score
one, and the ladder cannot branch on the fort's actual stores.

The second item in this stream is small and is here because it shares
`scripts/dfhack/` with the first (this repo's rule: two streams must never list
the same file under touched surfaces).

## Item 1 — the stocks read tool

Build `scripts/dfhack/df-overseer-stocks.lua`, in the idiom of the existing
tools in that directory. Read the neighbouring scripts first and match them:
JSON out, no coordinates in any model-facing field, landmark-relative where
position matters at all.

Subcommands, as a starting proposal rather than a specification (argue for
better if the live structs suggest better):

- `food-drink` — fort-owned counts, separated from foreign, broken down enough
  to be useful for a decision (at minimum: drink, prepared meals, raw edibles,
  and whether anything is rotten or unreachable).
- `seeds` — fort-owned seed counts by plant, since the ladder's farm rungs
  branch on it and the fort has 119 seeds recorded.
- Design for the caller who has to decide "can we eat next week", not for a
  stock screen.

**The load-bearing detail is ownership.** `flags.foreign` is what caught this
bug, but do not assume it is the whole answer: check against the live fort what
distinguishes items the fort owns from merchant goods, items still in a wagon,
items owned by a specific dwarf, and items in a claimed stockpile. Verify each
claim against the running game before writing it into the tool. If
`flags.foreign` turns out insufficient or misleading, say so loudly, in the
tool's own comments and in your report.

Then register it the way the existing tools are registered: `TOOLS.yaml`, the
`dfmcp` registry and tool schema, and the per-role allowlists under `agents/`.
It is a **read** tool: it belongs in the read-only roles too.

## Item 2 — the `stocks.*` live signal

Add the signals to `learning/live_signals.py` so a prediction like "fort-owned
drink greater than 0" can be written, stored and graded by the machinery that
already exists. The registry is deliberately closed and deliberately
mechanical (read straight off a read tool's own JSON, no judgement): keep both
properties. Follow `FORT_POPULATION` as the model. Unit-test it the way the
existing signals are tested.

Check `dfqueue`'s validation path accepts the new signal end to end, since it
validates at write time.

## Item 3 — the `set_labor`/`autolabor` race

A known single-writer violation already in production, found 2026-09-12 and
recorded in `decisions/DECISIONS.md` (the row beginning "Found and verified:
`set_labor` already races `autolabor`"), **fix not yet designed**:
`df-overseer-labor.lua`'s `set_labor` writes `unit.status.labors[code]`
directly with no coordination, and `autolabor` — enabled and confirmed actually
assigning jobs on this fort — reassigns on its own cycle, exempting only
military-duty and burrow-restricted units.

This matters now because the opening ladder's first rung is **fishing**, which
means assigning a fisherdwarf labor, which is exactly the losing side of this
race.

Read `autolabor`'s own documentation on this install before designing the fix.
It is believed to support marking individual labors as not managed by it; if
that is real, "exclude the labor from autolabor, then set it" is a far better
fix than either disabling autolabor wholesale or writing the bitfield and
hoping. Verify before building on it. If no clean mechanism exists, the honest
outcome is a `set_labor` that **refuses** with a clear reason rather than one
that silently loses, plus a written recommendation.

## Constraints

- **The fort is paused and stays paused.** Do not unpause, do not dismiss
  anything, do not write to the game. Read-only live access is expected and
  encouraged: verify every struct claim against the running fort rather than
  against the wiki or an older doc.
- **No deploy.** Nothing ships to VM 103 in this stream; the orchestrator
  handles deploys with the user's go-ahead, each time.
- **No coordinates** cross the model boundary, in any tool output. This is
  design commitment #1 and it is not negotiable.
- Mark **verified vs proposed** on every capability claim, and check
  `memory/dfhack-environment.md` before assuming a DFHack tool exists — several
  are present as files and tagged unavailable.
- Commit on your worktree branch **as you go**. Streams here have been killed
  mid-run twice; only committed work survived.
- Run the ambient suite (`python -m pytest`, expect 276 passed / 1 skipped as
  the baseline before your additions) and `dfmcp/tests` in `.venv-dfmcp` (152).
  Use `python`, not `py -3`.
- Do **not** edit `Working.md`, `decisions/DECISIONS.md`, `ROADMAP.md`,
  `CLAUDE.md` or `memory/` — the orchestrating session owns those. Do not touch
  anything under `research/`; a parallel research stream is live there.

## Touched surfaces

`scripts/dfhack/df-overseer-stocks.lua` (new), `scripts/dfhack/TOOLS.yaml`,
`scripts/dfhack/df-overseer-labor.lua`, `dfmcp/` (registry, tool schema and
their tests), `agents/*/tools.yaml`, `learning/live_signals.py`, `tests/`,
this doc.

## Report back

What you verified live and how, what you could not verify, whether
`flags.foreign` is really the right ownership test, the labor-race mechanism
you found and whether it is clean, and your branch name.

## Result (2026-09-16)

**Status: done.** All three items built, tested, and committed on
`worktree-agent-a18dd0bd0667ad108`. Fort left paused throughout (checked
before, during, and after); nothing deployed to VM 103; no fort mutation
issued.

**`flags.foreign` is NOT the right ownership test — a load-bearing
correction, not a minor caveat.** Live-verified against Uniboslan (SSH,
read-only `dfhack-run lua`/ad hoc `/tmp` scripts, never a file under DF's
own script paths until committed here): `flags.foreign` is an *origin* flag
(embark-outfitted or caravan-brought), not a *current-ownership* one. The
fort's own unclaimed starting barrels (on the ground, never in any wagon),
all 119 starting SEEDS items, and the fort's own already-built starting
wood all carry `foreign=true`. Using `not flags.foreign` would have zeroed
out the fort's own embark supplies, a worse bug than the one this tool
exists to fix. `flags.trader` is the real signal: confirmed a strict subset
of `foreign` in a full 1344-item sweep (565 foreign, 292 trader, 0
trader-without-foreign), and confirmed via each item's own `UNIT_HOLDER`
general_ref resolving to a real unit for which `dfhack.units.isMerchant()`
is true (checked on a caravan-held boulder). Concretely, of the 119 SEEDS
items, only 59 are fort-owned; the other 60 are the current caravan's own
seed varieties for sale — so even the earlier "119 seeds recorded" framing
already overcounted by roughly half. `df-overseer-stocks.lua`'s ownership
test is `not item.flags.trader`, and both the file and `TOOLS.yaml` say
why, loudly, per the brief's instruction.

**Item 1**: `scripts/dfhack/df-overseer-stocks.lua` (new) —
`stocks.food-drink` (drink/prepared_meals/raw_edibles buckets, each with
`count`, `foreign_total`, `rotten_count`, `unreachable_count`) and
`stocks.seeds` (`total` + `by_plant`). Mechanism live-verified via a
throwaway `/tmp` script over `dfhack-run lua` (deleted after); the file
itself was never placed on VM 103, per the no-deploy constraint. Registered
in `TOOLS.yaml` and granted to all three enabled roles (architect,
consultant, overseer) — it is read-only. Real counts read this session:
drink own=0/foreign=2, raw_edibles own=5/foreign=49, prepared_meals
own=0/foreign=0, seeds own=59/foreign=60.

**Item 2**: `learning/live_signals.py` gains `stocks.drink.count` /
`stocks.prepared_meals.count` / `stocks.raw_edibles.count` /
`stocks.seeds.count`, all `INTEGER`, following `FORT_POPULATION`'s shape.
Unit-tested in `learning/tests/test_live_signals.py` with fixture JSON
matching the real live counts above. Confirmed end to end against
`dfqueue.schema.validate()`: a proposal predicting `stocks.drink.count gt 0`
validates cleanly; a wrong-typed value is refused with a clear message.

**Item 3**: `df-overseer-labor.lua`'s `set_labor` no longer races
`autolabor` by default. It checks `plugins.autolabor.isEnabled()` (a real,
confirmed-live Lua API — returns `true` on Uniboslan today) and, for any
non-military unit while autolabor is enabled, runs `autolabor LABOR
disable` *before* writing the bitfield directly; if autolabor's enabled
state can't be determined at all, it now refuses with a clear reason
rather than guessing. **Mechanism is clean but not fully clean-per-unit**:
`autolabor <LABOR> disable` is fort-wide per labor, confirmed from
`autolabor`'s own shipped doc — there is no per-citizen exemption short of
military duty (already exempt by autolabor's own design) or a burrow
restriction (not used here, unverified as a clean alternative). Every
`set_labor` call says this plainly in its own return message when it
fires — never a silent side effect. **Verification boundary, stated
plainly**: `isEnabled()`, `CR_OK`, and the `df.unit_labor.FISH` == autolabor
`FISH:` name mapping were each confirmed live (read-only) this session. The
actual `autolabor LABOR disable` command was deliberately never executed
live — a real, persistent change to the running fort's automation config,
out of scope for a read-only, no-deploy stream. `TOOLS.yaml` marks
`labor.set-labor` `STALE` (old, racy code still on VM 103) rather than
claiming this fix is deployed.

**Tests**: ambient `python -m pytest` baseline was reproduced exactly (276
passed, 1 skipped) before any change; after all three items, 281 passed, 1
skipped (+5, the new live-signals tests). `dfmcp/tests` needed a fresh
`.venv-dfmcp` in this worktree (`python -m venv --system-site-packages
.venv-dfmcp` + `pip install -r dfmcp/requirements.txt`, the documented
fastmcp/mcp version-conflict warning appeared and is expected); it gives
152 passed, matching `CLAUDE.md`'s baseline exactly, and still 152 after
the new `stocks.*` tool ids were added to the registry (registry/roster
loading was re-checked directly, not just left to the test count).

**Not verified, named rather than hidden**: whether `flags.foreign` is ever
cleared later in a fort's life (this session only observed a first-year
fort); the exact text `autolabor list` prints for an already-disabled
labor (not needed, since the fix never parses that text); whether
`flags.owned` matters for anything here (checked, found false on every
sampled item, believed unrelated to fort-vs-caravan ownership but not
exhaustively confirmed).

**Open item for the orchestrator, not this stream's to resolve**: the
`stocks.*` tools and the labor fix are code-complete and test-covered but
**not deployed** — a future deploy pass needs to (a) place
`df-overseer-stocks.lua` on VM 103 and run `stocks.food-drink`/`stocks.seeds`
for real, (b) redeploy the fixed `df-overseer-labor.lua`, and (c) with
explicit go-ahead, actually exercise `autolabor LABOR disable` live at
least once to move item 3 from verified-by-mechanism to
verified-by-execution.

Branch: `worktree-agent-a18dd0bd0667ad108`. Commits: `19652eb` (stocks
tool), `1350b2e` (live signals), `337f74a` (labor race fix).
