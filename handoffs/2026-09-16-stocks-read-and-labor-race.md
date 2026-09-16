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
