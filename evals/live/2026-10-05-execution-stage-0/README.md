# 2026-10-05: conductor-executes stage 0, live baseline

Deployed `76c4bfd` (vm103-dfmcp, vm106-conductor; drift-clean, conductor 21
tools, `conductor.service` still disabled and inactive). Dry run clean (`hold:
None`, pause watchdog `wait` on the paused fort). Supervised window
`scripts/supervised-unpause.sh 10 1200 30`: tick 259043 to 270830, 22 alive,
0 warnings, hunger and thirst fine throughout, tripwire never fired, re-paused
and 100 FPS restored by the trap.

## Per-run usage (new in stage 0)

| Cycle | Role | Rounds | Wall s | Cost $ | Input | Cache read | Output | Reasoning |
|---|---|---|---|---|---|---|---|---|
| 1 (08:24) | quartermaster | 9 | 293 | 0.035 | 31,219 | 292,096 | 23,303 | 21,247 |
| 2 (08:31) | quartermaster | 9 | 342 | 0.038 | 28,426 | 285,440 | 28,204 | 26,183 |
| 2 (08:31) | overseer | 13 | 323 | 0.054 | 63,332 | 875,008 | 26,354 | 23,725 |

- About 90 to 93% of input tokens are cache reads: caching works well within a
  run.
- Reasoning is 91 to 93% of output; a round costs about 25 to 33 s, mostly
  generating about 2,400 reasoning tokens. Shorter turns mean fewer rounds and
  less reasoning per round, not less input.
- **Cross-run cache: inconclusive.** The Quartermaster's uncached input fell
  only from 31k to 28k between its two runs. Totals cannot show whether the
  first round hit the cache; per-round usage is needed (openclaw's session
  transcript may carry it).
- Day total so far: $0.40 for seven runs.

## What the agents did

- Quartermaster (both runs): drink at 4 for 22, only two empty barrels, the
  manager's barrel order stuck; proposed direct barrel jobs at the Carpenter's
  Workshop (proposal-0015, proposal-0016).
- Overseer: rejected both (ruling-0016, ruling-0017), correctly, because no
  tool could address the workshop.

## Finding: workshops with an apostrophe are unreachable by name

The MCP server refuses the apostrophe as a shell metacharacter
(`dfmcp/tools.py`, `_SHELL_METACHAR_RE`), and the game script refuses
"Carpenters Workshop" as unknown. Every landmark with an apostrophe
(Carpenter's, Stoneworker's, Mechanic's Workshop) is unreachable through every
name-taking tool, which is why barrels, and so brewing, are stuck. Fix
dispatched: `handoffs/2026-10-05-landmark-name-punctuation.md`.

The project rule (deployed earlier today) was not exercised: nothing was
accepted.

## Stage 1 and the apostrophe fix, live (deployed 97ae95c)

All four targets drift-clean; live counts overseer 97, conductor 23.
`workjob list-jobs` resolves "Carpenter's Workshop", "Carpenters Workshop" and
"carpenters workshop" alike (45 jobs). Window `10 1500 30`: tick 270870 to
285626, 22 alive, 0 warnings, tripwire never fired, re-paused by the trap.

| Cycle | Role | Rounds | Wall s | Cost $ | Input | Cache read | Output | Reasoning |
|---|---|---|---|---|---|---|---|---|
| 1 (09:13) | architect | 7 | 361 | 0.047 | 47,769 | 309,760 | 28,308 | 26,676 |
| 1 | quartermaster | 7 | 178 | 0.027 | 33,434 | 140,416 | 13,904 | 12,058 |
| 2 (09:22) | architect | 6 | 607 | 0.056 | 46,731 | 163,712 | 40,893 | 40,108 |
| 2 | quartermaster | 7 | 208 | 0.038 | 53,595 | 198,784 | 16,299 | 14,740 |
| 2 | overseer | 5 | 189 | 0.046 | 71,912 | 254,720 | 16,169 | 14,475 |

- **Cited facts work.** proposal-0017 (Architect) and proposal-0018
  (Quartermaster) carry server-read `cited` values with ticks. The
  Quartermaster's prose said "~1 unit" of drink; the server read 0.
- **The Overseer's ruling turn:** 5 rounds, 189 s (against 645 s and 37 calls
  this morning), 13 tool calls, zero `stocks.*` calls. Rulings: accept the
  brew (0018), reject a duplicate (0019), defer the bedrooms (0017) because
  "furnishing is blocked until the fort can produce beds".
- **Regression found:** it accepted the brew and did not execute it. Stage 1's
  ask ended "Stop when each has a ruling", correct once the executor exists
  (stage 2) but wrong before it. Fixed in `942ae36` (the ask says to carry out
  accepted proposals per the charter until types are routed), not yet deployed.
- The Architect's turns are the longest (361 s and 607 s), mostly reasoning,
  and it re-proposed bedrooms already accepted and dug this morning. Wake
  strictness (wake a role only when something in its lane changed) is the
  next cheap lever.
- Drink is 0 but thirst reads fine (dwarves drink from the Well). The binding
  constraint is empty barrels (2); nobody has yet proposed barrels now that the
  Carpenter's Workshop is reachable.
