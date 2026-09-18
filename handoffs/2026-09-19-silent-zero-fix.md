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
