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

STATUS: done (offline). Branch worktree-agent-af90224fd38052906. Nothing deployed, no game write.

### What was learned (read on the live install, read-only)

- DFHack's order library is `hack/data/orders/` on the install (basic,
  furnace, glassstock, military, rockstock, smelting: 228 orders). Copied byte
  for byte to `tests/fixtures/dfhack_orders/`.
- It never issues a materialless item order. Per job: stone furniture, blocks,
  mechanisms, goblets carry `"material": "INORGANIC"` (some also a GLASS_GREEN
  twin); wood jobs (bed, bin, crutch, splint, bucket, cage) carry
  `material_category: ["wood"]`; leather, strand and metal jobs carry leather,
  strand or one `INORGANIC:<METAL>` per order; reactions and raw processing
  (charcoal, ash, lye, plants, sand, meal, dye, melt) carry none.
- `workorder.lua` writes `mat_type/mat_index` from `matinfo.find(material)`
  ("INORGANIC" gives type 0, index -1, i.e. any stone) and flags from
  `material_category`; it also sets `item_subtype`, `item_type`, `art`,
  `hist_figure`, `item_category` and richer item_condition fields. Our tool
  never set a material by itself, which is the whole defect.
- Not derived from the game's own job definitions: `df.job_type.attrs` has a
  `material` attribute but reading it needs live Lua, out of scope, so the
  policy is data reduced from the library. Follow-up: a live read of
  `df.job_type.attrs[x].material` to cross-check the table.

### What changed

- `scripts/dfhack/df-overseer-orders.lua`: `ORDER_MATERIAL_POLICY`, a data
  table of job types (material default, category default, none, or
  requires). `create_order`: caller material or category wins; otherwise a
  reaction stays bare, a `material`/`category` entry is filled in
  (`material_defaulted: true` in the result), and a `requires` job or one
  absent from the table is refused with a named message. `describe_order`
  (so `orders.list` and the post-create readback) adds `material` and
  `invalid_material` (+ `invalid_material_reason`) for a job whose policy
  needs a material and whose order has mat_type < 0 and no category flag.
- MakeBarrel is not in the library; it defaults to wood by analogy with its
  library sibling MakeBucket (marked `inferred`).
- `scripts/dfhack/TOOLS.yaml`: MATERIAL, MATERIAL_CATEGORY, list returns and a
  dated note updated; the stale "missing announcement" comment annotated.
- Tests: `tests/test_orders_library_parity.py` (10 tests) plus mat_type /
  mat_index support in `tests/lua_stubs/dfhack_orders_world.lua`. For all 129
  library orders without an item_subtype, the tool's dry-run order has the
  same job, reaction, material, material_category and frequency; every policy
  entry is checked against the library (a default is a value the library uses
  for that job, `none` jobs have no material anywhere in the library,
  `requires` jobs have more than one variant); every library job has a policy
  entry; list flags a bare order and not a set one.

### Not covered (honest limits)

- 99 library orders carry `item_subtype` (weapons, armour, tools, ...); the
  tool has no ITEM_SUBTYPE argument, so those jobs are `requires` and cannot
  be ordered fully specified. Needs its own tool change.
- Library item_conditions with flags, reaction_product and so on are not
  compared (the tool's condition syntax is narrower).
- A fake world cannot show the game then works the order. That is the live
  repair below.

### Tests

- Ambient `python -m pytest` (lupa 2.8 importable): 3625 passed, 3 skipped, 0
  failed (the known date-sensitive wiki test did not fail today).
- `dfmcp/tests` in `.venv-dfmcp`: 983 passed.
- `tests/test_orders_conditions_lua_logic.py` unchanged and green (38).

### Exact live repair (orchestrator, supervised; NOT run)

Live queue as read 2026-10-07: id 0 ConstructBlocks x1 OneTime, id 1
ConstructMechanisms x1 OneTime, id 2 BREW_DRINK_FROM_PLANT x8 (bare, which is
the library's own shape, validated true: KEEP), id 3 ConstructThrone x1
OneTime, id 4 MakeBarrel x2 Daily with item condition AtMost 20 BARREL.

0. Gated: deploy the merged `df-overseer-orders.lua` (git archive,
   core.autocrlf=false). Without the deploy, step 3 still works on the old
   code by passing MATERIAL / MATERIAL_CATEGORY explicitly (the explicit
   forms below).
1. Fort stays paused. `orders.list`: expect ids 0, 1, 3, 4 with
   `invalid_material: true`, id 2 false (new code only).
2. Cancel the four, each dry-run first, then real: `orders.cancel 0`, `1`,
   `3`, `4`. Cancel is an inferred erase+delete, never proven by a live
   removal; if it misbehaves, the user cancels them in the in-game manager
   screen instead.
3. Recreate, dry-run then `DRY_RUN=false`, amounts as before. With the new
   code the material is defaulted; the explicit form is identical:
   - `orders.create ConstructBlocks 1` (= MATERIAL INORGANIC)
   - `orders.create ConstructMechanisms 1` (= MATERIAL INORGANIC)
   - `orders.create ConstructThrone 1` (= MATERIAL INORGANIC)
   - `orders.create MakeBarrel 2 Daily "" "" "" "" "AtMost:20:BARREL"`
     (= MATERIAL_CATEGORY wood, the old order's condition reproduced)
   Each result should show `material_defaulted: true` and a read-back
   `material` or `material_category` set, `invalid_material: false`.
4. `orders.list`: five orders, none `invalid_material`. The user checks the
   manager screen: the orders should read as rock blocks, rock mechanisms,
   rock throne and wooden barrels, not "unknown material".
5. Unpause for a bounded run and watch whether the manager validates them and
   jobs appear. The diagnosis also named an unproven second cause (the manager
   has no organizer skill and never validated anything; Study icon unread). If
   the new orders still sit `validated: false`, that is a different problem,
   not a failure of this repair.
