# Handoff: manager orders with conditions, repeat and material class, generic over job type

Date: 2026-10-01. **Executor, Sonnet, worktree. Offline code only, no live
access** (the orchestrator live-verifies after merge).

## Why

Standing goals are manager orders with conditions and repeat (register
2026-09-30 and 2026-10-01: set intent, let the game execute; the Manager
works, per the user). `df-overseer-orders.lua` today creates orders for a
hardcoded table of 12 jobs, with an amount only. The mechanism is settled
from source in `research/2026-10-01-quartermaster-levers.md` §1 (read it in
full, with its file and line citations, first).

## Tasks, in order (commit after each)

1. `orders.create` generic over job type: any live `df.job_type` name (and
   reaction name for custom reactions), per-kind detail read from the game or
   data, never a per-job branch (`CLAUDE.md`, tools must be generalisable).
   Keep the existing duplicate check and `DRY_RUN` default true.
2. Optional arguments, each through the `workorder` JSON path the research
   verified: frequency (OneTime, Daily, Monthly, Seasonally, Yearly), item
   conditions (item type, material or material class, comparison op, value),
   order conditions (another order id and its Activated or Completed state),
   and material category (the class filter; stone and wood for building
   materials by default, matching `DEFAULT_CLASS_CATEGORIES` in
   `df-overseer-building.lua`). Arguments stay flat strings the model can
   write (design a compact syntax and document it); refuse malformed ones
   with a named reason.
3. `orders.reorder ID POSITION` and `orders.recheck ID`, per the research's
   shapes (§1), `DRY_RUN` default true.
4. Reports read back the order as the game holds it (conditions, frequency,
   validated and active bits), never an echo of the request.
5. `TOOLS.yaml` entries, and tests in the existing lupa style; a stub that
   rejects what the real `workorder` path would reject. Say plainly what the
   stub cannot prove.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early, then after
  each task.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `agents/*/tools.yaml` (say in the Result which role gets which command).
- No em dashes in prose. No attribution lines in any commit. No armok
  capabilities.
- Tests: ambient `python -m pytest` and `dfmcp/tests` with the main
  checkout's `.venv-dfmcp`; report both counts.
- Stop and report on any permission refusal.

## Touched surfaces

`scripts/dfhack/df-overseer-orders.lua`, `scripts/dfhack/TOOLS.yaml`, tests
and stubs.

## Result

`orders.create` is now generic over job type: JOB resolves first as a live
`df.job_type` name, else as a reaction code from
`world.raws.reactions.reactions`, replacing the twelve-entry `JOB_INFO`
table (a breaking change: "blocks" etc. no longer work, use
"ConstructBlocks"). Added, as flat-string optional arguments, all validated
live and refused by name on both the dry-run and real-write path:
FREQUENCY, MATERIAL, MATERIAL_CATEGORY (comma list, validated against a
throwaway `df.manager_order`'s own bitfield keys since DFHack ships no
source definition of `job_material_category`'s flag names at all),
WORKSHOP_ID, MAX_WORKSHOPS, ITEM_CONDITIONS
("COND:VALUE[:ITEM_TYPE[:MATERIAL]]", ";"-separated), ORDER_CONDITIONS
("ORDER_ID:STATE", ";"-separated, must reference an order already in the
queue). Added `orders.reorder ID POSITION` (direct vector splice, no
native "move to N" exists) and `orders.recheck ID`, which corrects the
research's own proposal: the native `orders recheck` command takes no ID
at all, so this reproduces its exact gate (conditioned and active)
scoped to one order. Every read (`list`, a real `create`, `check-duplicate`)
goes through one shared `describe_order`, so a real create reads the order
back from the queue rather than echoing the request. `check-duplicate` now
resolves JOB the same generic way. All existing roles (overseer, architect,
quartermaster) already hold `orders.create`/`cancel`/`list`/`check-duplicate`
in their own `tools.yaml` (not edited by this stream, per the handoff's own
rule) and should get `orders.reorder`/`orders.recheck` too, matching that
existing symmetry; `conductor` holds only `orders.list` today and does not
need the new writes. Tests: 37 new lupa cases
(`tests/test_orders_conditions_lua_logic.py` against
`tests/lua_stubs/dfhack_orders_world.lua`) cover job/reaction resolution,
every argument's validation and refusal wording, the real-create readback,
and reorder/recheck's vector mechanics; the stub's own header states
plainly what it cannot prove (workorder.lua's real qerror text,
`job_material_category`'s real flag names, and anything about DF's closed
engine actually dispatching an order). The existing manifest test
(`tests/test_order_job_attribution_manifest.py`) was extended for the two
new command ids and the new `create` signature. Ambient `python -m
pytest`: 2185 passed, 3 skipped (this repo's baseline count has grown well
past the 2026-09-25 measurement in `CLAUDE.md` from unrelated streams since
then; nothing here regressed it). `dfmcp/tests` under the main checkout's
`.venv-dfmcp`: 722 passed. No live access this stream; every "real mutation"
path (`create_order` with `dry_run=false`, `reorder_order`, `recheck_order`)
is UNTESTED against the actual game, same status as the pre-existing
`cancel_order` write path.

Role grants recommended for the orchestrator (not applied here, since
`agents/*/tools.yaml` is out of scope for this stream): give
`orders.reorder` and `orders.recheck` to overseer, architect and
quartermaster, the same three roles that already hold the rest of the
orders lifecycle; leave conductor at `orders.list` only.

**Live test that would confirm this**, on a supervised unpause (matching
the register's 2026-09-30 item-8/9 rows and
`research/2026-10-01-quartermaster-levers.md` §4's own table): queue one
real order with a repeat frequency and one item condition, e.g. `orders
create MakeBarrel 0 Daily "" "" "" "" "AtMost:20:BARREL" "" false`, confirm
`orders.list` reports it back with `frequency: Daily`, the item condition
present, and `validated`/`active` starting `false`/`false`; watch it over a
few ticks to see `validated` flip once the Manager (if appointed) assesses
it; then call `orders.recheck` on its id while it is `active` and confirm
`validated`/`active` both clear; then `orders.reorder` it to position 1 and
confirm `orders.list`'s `queue_position` changes with no other order lost;
cancel it afterwards for cleanup. A second, separate check: create one
order by its reaction code (`BREW_DRINK_FROM_PLANT`) to confirm the
JOB-as-reaction-code resolution path works against the real raws, not just
the fake one this stream's stub modelled.
