# Handoff: research, what every workshop and furnace kind needs

Date: 2026-09-21. **WRITTEN for review, not dispatched.** Research brief for a
`researcher` agent on Sonnet. Read-only. No fort changes, no live game calls.

Read `CLAUDE.md`, `docs/BUILDING-TOOL.md` (open questions 3 and 4),
`docs/PRODUCTION-MODEL.md` (installation is a process), and
`research/2026-09-19-unverified-claims-audit.md` (what "presented as measured"
looks like).

## The question

For **every workshop and furnace kind** in DFHack's quickfort table (about 30
workshops and 7 furnaces; the list is in
`hack/scripts/internal/quickfort/build.lua` on VM 103, readable over SSH as
`df`, read-only), answer briefly:

1. **What does it need to be built?** Materials by class (boulder, log, block,
   bar, other) and quantities, and whether DFHack's
   `dfhack.buildings.getFiltersByType` returns the game's own list (read the
   DFHack docs and scripts; **do not call the live game**).
2. **What does it need to be useful?** Inputs and containers, fuel or magma or
   water access, adjacent requirements, the labors involved, and anything that
   makes a built one silently idle.
3. **Known hazards**, each stated with its condition as a short title (for
   example "placing X in Y: Z"), because these seed the tool's gotcha list.

**Brief, per the user: a line or two per kind, not an essay.** Breadth over
depth.

## Output

`research/2026-09-21-building-requirements.md`: a table by kind, then a
machine-readable YAML block, one entry per kind, each field with its **source
and a confidence flag** (`verified` only against this install's files or
DFHack's own docs at the installed version; anything from the wiki or memory is
`prior`). State plainly what could not be checked. Nothing may be presented as
measured that was not.

## Rules

- Read-only; write only the one research file. Read secrets by key, never the
  whole `.env`. No addresses or hostnames in the file.
- Do not write `Working.md`, the register, `memory/` or `handoffs/INDEX.md`.
  Commit the file when done. No em dashes.

## Done means

Every kind in the table has an entry or an explicit "not found, and why", each
claim carries a source and a flag, and the file ends with what remains
unverified.
