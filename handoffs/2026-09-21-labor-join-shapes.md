# Handoff: make the labor join read the building tool's real result shapes

Date: 2026-09-21. **Offline build stream** (worktree, Sonnet). No VM, no live
game, no deploy.

Read `CLAUDE.md`, `dfmcp/labor_join.py`, `dfmcp/tests/test_labor_join.py`,
`dfmcp/tests/test_gotchas_server.py` (the labor-join-over-the-wire class),
`scripts/dfhack/df-overseer-building.lua` (what `find` and `build` really
return), and the "two labor-join gaps" in the report of
`handoffs/2026-09-21-deploy-building-batch.md`, then this.

## Why

The deploy verified the join live against the real graph and found it reports
unknown, safely but uselessly, in two cases, because the server stream wrote the
join against a stub shape:

1. `building.find` returns an **array** of up to five candidates, each carrying
   its own `requirements` and `gaps`. The join looks for a top-level
   `requirements`, so every find says "the result carried no requirements
   block". For Well it shows top-level `gaps: []` beside a candidate that says
   `needs 1 of TRAPPARTS, 0 available`: an all-clear sitting next to a real gap,
   the exact failure class this repo forbids.
2. `building.build` returns its material requirement as `building_material.filters[]`
   (each with a need and stock); the join expects the workshop tool's older
   shape (`accepts` plus `fort_owned`, `needs_container` plus
   `fort_owned_containers`) and reports "present but not in a shape the server
   understands".

## Deliverables

1. Read the real shapes from the Lua tool (do not guess: quote the field names you
   rely on) and make `dfmcp/labor_join.py` handle them: take `requirements` from the
   candidates of an array result (say how you combine five candidates: all share
   one kind, so the kind's requirements are the same; but each candidate's own
   `gaps` differ and must not be dropped or contradicted), and read
   `filters[]` need and stock for the gap wording. The older shape must keep
   working.
2. **Never an all-clear beside a gap.** If any candidate reports a gap, the joined
   `gaps` must not be an empty list. Unknown stays null plus a reason, never `[]`.
3. Tests with the **real captured shapes** (build fixtures from the deploy report's
   live outputs for Masons, Well, Bed, FarmPlot and a `build` dry run), through the
   real server over a real MCP client as the server stream's tests do, including
   the Well case: candidate `needs 1 of TRAPPARTS, 0 available` must reach the
   agent as a gap.

## Rules

- You own `dfmcp/labor_join.py`, `dfmcp/tests/**` and this doc. Do not touch
  `scripts/dfhack/**`, `production/**`, `agents/**` or `gotchas/**`.
- No address, hostname or token in any tracked file. Do not write `Working.md`,
  `decisions/DECISIONS.md`, `memory/` or `handoffs/INDEX.md`. **Commit after each
  milestone** and extend this doc's report as you go. No em dashes in prose. Use
  the Write tool for scratch scripts rather than long inline shell heredocs.

## Done means

The join reads array `find` results and `build`'s `filters[]`, the Well gap
reaches the agent, no result shows an empty `gaps` beside a candidate gap, the
suites pass (baseline **834 passed / 2 skipped** ambient, **475 passed** in
`.venv-dfmcp`, report before and after), and the report says what a redeploy
needs (dfmcp only).
