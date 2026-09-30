# Handoff: research the native levers for orders, labor and priority

Date: 2026-10-01. **Researcher, Sonnet, read-only. No code, no live access.**

## Why

The minimal starting point (register 2026-10-01) needs three tools that set
intent through DF's own machinery (register 2026-09-30, "set intent, let the
game execute"): manager orders with conditions and repeat (standing goals
such as "keep drinks between 50 and 100"), `labor.quota` (per-labor targets
over autolabor), and a priority tool (designation priority and order
sequence). The offline test world has disagreed with the real API twice, so
this time the mechanism is settled from source before any build. Read
`research/2026-09-30-policy-audit.md` (with its corrections at the top), the
register's 2026-09-30 and 2026-10-01 rows, and
`scripts/dfhack/df-overseer-orders.lua` and `df-overseer-labor.lua` first.

## Questions (from DFHack `53.16-r1` source, df-structures, the DF wiki)

1. **Manager orders.** How a script creates an order with item conditions
   (the `workorder` script's JSON, `orders import`, the `manager_order`
   struct's `item_conditions`), repeat frequency, and material or reagent
   choice; how order sequence (list position) is changed; what the Manager
   must validate and how a script can tell validated, active and blocked
   apart. Propose the argument shape of `orders.create` extended, generic
   over job type.
2. **Labor in v50.** Is DFHack's `autolabor` actually functional at
   `53.16-r1` on v50 (the plugin, `labormanager`, and how both interact with
   v50 work details)? How are per-labor minimum and maximum dwarves set from
   a script? If autolabor is not the right engine on v50, what is (work
   details set from a script, or `autolabor` still), with sources. Propose
   `labor.quota`'s shape.
3. **Priority.** How designation priority (1 to 7) is set on dig and other
   designations (tile occupancy/designation flags, quickfort's priority
   syntax); and what DFHack `prioritize` really does: does it set `do_now`
   on jobs, on whole job types, and is it persistent? This settles the
   register's deferred measurement (2026-09-30, last row).
4. For each: armok status (is it something a player can do in the vanilla
   UI?), and the live test that would confirm it (read-only or reversible
   steps; the orchestrator runs it).

## Deliver

`research/2026-10-01-quartermaster-levers.md`, short answer up front, every
claim marked verified-from-source (file and line) or unverified; proposed
tool shapes for the three tools; the live test plan. Fill in this handoff's
Result (about 200 words).

## Rules

- First step: `git merge --ff-only main`. Commit the plan early, then after
  each question.
- Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`.
- No em dashes in prose. No attribution lines in any commit.
- Do not guess DF behaviour; say "unverified".
- Stop and report on any permission refusal.

## Touched surfaces

`research/2026-10-01-quartermaster-levers.md` and this handoff only.

## Result

(fill in)
