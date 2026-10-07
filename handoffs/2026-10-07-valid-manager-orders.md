# Handoff: the orders tool issues valid manager orders

Date: 2026-10-07. **Executor, Sonnet, worktree. Offline; no deploys, no
live writes.** First: `git fetch origin && git merge --ff-only origin/main`.

## Why

`evals/live/2026-10-07-manager-orders/README.md`: all five live orders were
issued by our tool with mat_type -1, mat_index -1 and an empty
material_category; the game shows them as "Make unknown material ...". In
46+ running game days none made anything. The user (who plays DF) believes
the orders were invalid as issued; in-game the office is fine. DFHack's own
order library (hack/data/orders/*.json) sets material INORGANIC on
ConstructBlocks/Mechanisms/Throne. `scripts/dfhack/df-overseer-orders.lua`
sets material only when the caller passes MATERIAL (about lines 626-641).

## Scope

1. Read DFHack's shipped order library and `orders import` code (in the
   DFHack install on VM 103 read-only, or the DFHack source on GitHub at the
   installed version) and derive, from the game's own job definitions where
   possible, which job types need a material or material_category for a
   valid order (item jobs like ConstructBlocks, MakeBarrel, ConstructBed,
   ConstructThrone, ConstructMechanisms) and which do not (reactions such as
   BREW_DRINK_FROM_PLANT, which carry none).
2. `orders.create`: for a job that needs one, **require** a material or
   material category, or default it from data (per job type: e.g. stone
   jobs INORGANIC, wood jobs material_category wood), never per-instance
   code; refuse with a clear message when it cannot pick one. Match every
   field an order created by `orders import` for the same job has.
3. `orders.list`: flag any order whose material is unset on a job that
   needs one (`invalid_material: true` with a reason), so agents and the
   conductor can see bad orders.
4. A dry-run comparison test: for each job type in DFHack's library that
   our tool supports, the order our tool builds has the same fields as the
   library's (lupa fake world).
5. Write in the Result the exact live repair (which of the five live
   orders to cancel and what to create in their place), for the
   orchestrator to run supervised. Do not run it.

## Rules

Touched surfaces: `scripts/dfhack/df-overseer-orders.lua`, a per-job data
file if needed, `scripts/dfhack/TOOLS.yaml` (orders section), tests, this
handoff. Read-only live access to VM 103 only to read DFHack's order
library files (`scripts/vm-ssh.sh df` with
DF_ENV_FILE=c:/website-projects/df-automation/.env). Public repo: no
hostnames, IPs or tokens. No em dashes. No attribution lines. Commit after
each milestone. Do not write Working.md, DECISIONS.md, memory or INDEX.md.
Full ambient `python -m pytest` (lupa on PYTHONPATH) and `dfmcp/tests` in
`.venv-dfmcp` green.

## Result

(executor fills this in)
