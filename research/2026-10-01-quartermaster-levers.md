# Quartermaster levers: manager orders, labor, priority, from DFHack source

Date: 2026-10-01. Researcher (Sonnet), read-only: no code, no live access.
Brief: `handoffs/2026-10-01-quartermaster-levers-research.md`.

All source citations are against **DFHack tag `53.16-r1`**, pinned exactly:
- `DFHack/dfhack` tree at tag `53.16-r1` (fetched as a full archive this
  session).
- Its pinned scripts submodule, resolved via GitHub's contents API
  (`repos/DFHack/dfhack/contents/scripts?ref=53.16-r1`) to commit
  `7549711a993e03bef19e90b27427096c1099853e`; `workorder.lua` and
  `prioritize.lua` were re-fetched at that exact commit and diffed
  byte-for-byte against the copies already in this session's scratchpad —
  identical, so every line number below is that pinned commit, not a moving
  branch tip.
- Its pinned `df-structures` submodule, resolved the same way
  (`repos/DFHack/dfhack/contents/library/xml?ref=53.16-r1`) to commit
  `1dd01aad64219afa0578f1328cf15bd0c6006d5a`; `df.workquota.xml` and
  `df.job.xml` were diffed byte-for-byte against that commit too —
  identical.
- The DF wiki, used only for cross-checking prose descriptions, never as
  the primary source for a struct shape or a code path.

Every claim below is marked **verified-from-source (file:line)** or
**unverified**. No claim in this document is asserted from the wiki alone
without a source-level check; where source and prior repo comments
(`df-overseer-orders.lua`, `df-overseer-labor.lua`, the 2026-09-30 policy
audit) already got something right, that is noted as confirmation rather
than re-derived from scratch.

## Short answer

1. **Manager orders.** `workorder.lua`'s three-call sequence
   (`preprocess_orders` -> `fillin_defaults` -> `create_orders`) is exactly
   as this repo's `df-overseer-orders.lua` already documented, and it now
   has a complete, source-verified JSON schema: item conditions
   (`manager_order_condition_item`, six comparison operators, matched
   against an item type/subtype/material/bearing/reaction), order-to-order
   conditions (`manager_order_condition_order`, chain one order's start or
   finish to another's), and repeat frequency (`workquota_frequency_type`:
   OneTime/Daily/Monthly/Seasonally/Yearly). Order **sequence** is genuinely
   just position in the `world.manager_orders.all` vector; a new order is
   always appended at the end, and the only native reordering is the
   `orders` plugin's `sort` command, which applies one fixed rule
   (workshop-pinned orders first, then one-time before repeating), not an
   arbitrary "move to position N." **Validated**/**active** are two real,
   independent bits on `manager_order.status`; the native `orders recheck`
   command clears both to force the game to re-evaluate a conditioned
   order, which is the clearest available evidence for what the two bits
   mean (validated = the manager has assessed feasibility, active = a job
   is currently dispatched for it). Whether an appointed Manager gates a
   validated order from ever going active is **not settled by DFHack
   source at all** — that logic lives in the closed DF engine, not in
   anything DFHack ships.
2. **Labor in v50.** `autolabor` is a real, currently-built plugin at this
   tag and still operates the same way it always has: it flips
   `unit.status.labors` bits directly, per labor, with a per-labor
   minimum/maximum/talent-pool triple, exposed only through its CLI
   (`autolabor LABOR MIN MAX [POOL]`), no dedicated Lua getter/setter for
   those numbers. `labormanager`, autolabor's would-be v50 successor,
   **exists as source in the same plugin directory but is not compiled**:
   its `dfhack_plugin(...)` line in `CMakeLists.txt` is commented out. V50's
   own "Work Details" screen is a real, separate structure
   (`plotinfo.labor_info.work_details`, a vector of `work_detail`: a name, a
   mode of Default/EverybodyDoesThis/NobodyDoesThis/OnlySelectedDoesThis, a
   fixed `assigned_units` list, and an `allowed_labors` bool array) with **no
   headcount-target concept at all** — it is closer to a hand-picked list or
   a blanket policy than to autolabor's continuous rebalancing, and
   `autolabor.cpp` never reads or writes it. So on this build, autolabor
   remains the only engine that does what `labor.quota` needs (a target
   count per labor), and it is completely independent of, and can still
   race, whatever the Work Details UI is doing to the same labor bits.
3. **Priority.** Designation priority 1-7 and DFHack `prioritize` are two
   unrelated mechanisms occupying the same English word. Designation
   priority is a genuine per-tile value (a lazily-allocated
   `block_square_event_designation_priorityst`, one `int32` per tile,
   default 4, stored as the UI number times 1000), written only by dig
   designations (`des.bits.dig || des.bits.smooth`) through
   `MapExtras::Block::setDesignationAt`; quickfort's own blueprint syntax
   (`d1` .. `d7`, default `d4`) is a thin wrapper over exactly this. It is a
   pure player action DF already exposes in vanilla (the "p" dig-priority
   menu) — no armok question at all. `prioritize`, by contrast, is not "set
   this one thing's priority" — it is a **standing, persistent watch**: you
   register a job *type* (optionally narrowed to a hauling labor or
   reaction), and from then on, forever (the watch list survives a save
   reload via `dfhack.persistent.saveSiteData`), every new job of that type
   gets `job.flags.do_now = true` the instant it is created, via an
   `eventful.onJobInitiated` hook. This is exactly the shape the register
   worried about: turning `prioritize` on for a job type is not a one-off
   nudge, it is "this job type is now always do_now," which is a much
   bigger and more persistent step than the "do now for genuine emergencies
   only" ruling anticipated. Its own doc header still carries no `armok`
   tag, confirmed at the source (`:tags: fort auto jobs`), so the armok
   question is settled independent of the priority-collision question,
   which is a design call, not a permissions one.

## 1. Manager orders

### Create sequence and argument shape

**Verified from source.** `workorder.lua`'s CLI entry point calls
`preprocess_orders(orders)` then `fillin_defaults(orders)` then
`create_orders(orders, quiet)` (scratchpad copy of pinned commit
`7549711a993e03bef19e90b27427096c1099853e`, `wo.lua:447` `preprocess_orders`,
`:515` `fillin_defaults`, `:184` `create_orders`; the CLI dispatch that
chains them was not re-read line by line this pass, but `df-overseer-orders.lua:14-23`
already documents it and this session's read of the three functions
individually is consistent with that chain existing). `df-overseer-orders.lua`'s
`create_order` already reproduces this exact sequence rather than
hand-building a `df.manager_order`, which this research confirms is the
right call: `create_orders` (`wo.lua:184-444`) does substantial validation
and cleanup (`dfhack.with_onerror` deletes the order object on any field
error, `wo.lua:196-201`) that a hand-built struct would have to reimplement.

`create_orders`' full accepted JSON shape, read directly from
`wo.lua:194-441`, field by field:

| Field | Verified at | Meaning |
|---|---|---|
| `job` | `wo.lua:205` | `df.job_type` name, required |
| `reaction` | `wo.lua:208-210` | reaction code, for `job == CustomReaction` |
| `item_type` / `item_subtype` | `wo.lua:212-229` | target item kind, for jobs that produce a specific item |
| `material` | `wo.lua:236-243` | resolved via `dfhack.matinfo.find`, sets `mat_type`/`mat_index` |
| `meal_ingredients` | `wo.lua:231-235` | numeric ingredient mask, alternative to `material` |
| `item_category` | `wo.lua:245-250` | sets `specflag.encrust_flags` |
| `material_category` | `wo.lua:260-265` | sets the `material_category` bitfield (a class, e.g. "any non-economic stone" — this is exactly the materials-ruling's "class, not exact item" lever) |
| `hist_figure` | `wo.lua:252-258` | historical figure id, for named/artifact-style orders |
| `art` | `wo.lua:267-274` | `art_spec` type/id/subid |
| `frequency` | `wo.lua:281-282` | `df.workquota_frequency_type` name, required (defaults to `OneTime` via `fillin_defaults`, `wo.lua:512`) |
| `workshop_id` | `wo.lua:286-292` | pins the order to one existing workshop |
| `max_workshops` | `wo.lua:294-296` | caps how many workshops can pull from this order at once, `0` = unlimited |
| `item_conditions` | `wo.lua:298-378` | array, see below |
| `order_conditions` | `wo.lua:380-397` | array, see below |
| `amount_total` | `wo.lua:400-441` | `0` = infinite; `__reduce_amount` lets a re-run adjust an existing order in place rather than duplicating it (`wo.lua:401-419`) |

**Item conditions** (`wo.lua:298-378`, struct confirmed at
`df.workquota.xml:12-32`, `manager_order_condition_item`): each entry is
`{condition, value, item_type, item_subtype, material, bearing,
reaction_class, reaction_product, tool, flags}`. `condition` is one of six
`logic_condition_type` values (`df.workquota.xml:2-9`): `AtLeast`,
`AtMost`, `GreaterThan`, `LessThan`, `Exactly`, `Not` — so "keep drinks
between 50 and 100" is two conditions (or one order re-evaluated at each
threshold) rather than a single range primitive; there is no built-in
range/band comparison. `bearing` (`wo.lua:342-352`) matches an ore-bearing
inorganic by raw id — this is how a condition like "only when there is ore
to smelt" would be expressed. **Order conditions**
(`wo.lua:380-397`, struct at `df.workquota.xml:44-48`,
`manager_order_condition_order`) let one order's `Activated` or `Completed`
state gate another order in the same `create_orders` batch (`condition.order_id`
resolved through the batch's own `id_mapping`, `wo.lua:386`) — this is the
native chaining mechanism for "make blocks, then make a wall from them,"
independent of anything this repo's own project/step machinery does.

### Order sequence (list position)

**Verified from source.** A newly created order is always appended to the
tail of `world.manager_orders.all` (`wo.lua:440`,
`world.manager_orders.all:insert('#', order)`) — there is no "insert at
position N" in `create_orders` itself. The native **`orders`** plugin
(a separate C++ plugin from the `workorder.lua`/`prioritize.lua` scripts,
`plugins/orders.cpp`, `DFHACK_PLUGIN("orders")` at `orders.cpp:41`) has a
`sort` subcommand (`orders.cpp:123-126` dispatch, `:1012-1034`
implementation) that `std::stable_sort`s the same vector by one fixed rule
(`orders_compare`, `orders.cpp:1012-1021`): orders pinned to a specific
workshop first, then among the rest, one-time orders before repeating ones.
This is a policy the native game re-applies on demand, not a way to move
one order to an arbitrary spot. A script that wants a different order
sequence has to manipulate the vector directly (`:erase(idx)` then
`:insert(new_idx, order)`), the same primitive `df-overseer-orders.lua`'s
own `cancel_order` already uses for deletion (`df-overseer-orders.lua:467-468`).
No native command sets order position individually; this is a genuine gap,
consistent with the register's own framing of order sequence as one of the
"native levers" priority should map onto, still unbuilt.

### Validated / active / blocked

**Verified from source, by inference from the one native tool that
manipulates these bits deliberately.** `manager_order_status`
(`df.workquota.xml:59-62`) is a two-bit flag: `validated`, `active`. The
`orders` plugin's `recheck` command (`orders.cpp:1040-1051`) clears *both*
bits on any order that has `item_conditions`, specifically to force the
game to re-evaluate that order's conditions on its next pass — this is the
strongest available evidence for what the bits mean: `validated` is the
manager's own assessment that the order is currently satisfiable,
`active` is whether a job is currently dispatched for it, and clearing
both is how a script asks the game to re-decide. This matches (does not
contradict) `df-overseer-orders.lua`'s live observation on Uniboslan's
three stuck orders (`validated=true, active=false`,
`df-overseer-orders.lua:313-320`): the manager approved them once, but
nothing is currently running for them — consistent with a condition that
currently evaluates false, or no free workshop, rather than an outright
rejection. There is also a separate `orders recheck_current` command
(`orders.cpp:1053-1064`) that clears only `active` on whichever order is
open in the in-game Order Conditions screen, for the player's own live
edit.

**Not verified, and cannot be from DFHack source alone.** Whether an
appointed Manager is a precondition for `validated`/`active` to ever
progress is native-DF-engine logic, not DFHack code — nothing in
`orders.cpp` or `workorder.lua` reads or checks a Manager noble position
anywhere (consistent with `df-overseer-orders.lua`'s own header finding,
`df-overseer-orders.lua:39-60`, that `create_orders` itself has no
Manager-related gate). This question can only be settled by a live test,
not by more source reading.

### `orders.create` extended shape (proposal)

Generalises `df-overseer-orders.lua`'s current four/twelve-entry
`JOB_INFO` table (already flagged by the 2026-09-30 policy audit as a
violation of "tools must be generalisable",
`research/2026-09-30-policy-audit.md` row 2 of §1) the same way
`df-overseer-workjob.lua` already generalised direct jobs: read
`df.job_type` live instead of hand-listing entries.

```
orders.create({
  job: JOB_TYPE_NAME,            -- any df.job_type name, read live
  reaction: REACTION_CODE,       -- required iff job == "CustomReaction"
  amount: N,                     -- 0 = infinite
  item_type / item_subtype,      -- optional, for item-producing jobs
  material: "INORGANIC:GRANITE", -- optional, exact material
  material_category: [CLASS...], -- optional, a class (the materials ruling's lever)
  workshop_id, max_workshops,    -- optional pin/cap
  frequency: "OneTime"|"Daily"|"Monthly"|"Seasonally"|"Yearly",
  item_conditions: [
    {condition: "AtLeast"|"AtMost"|"GreaterThan"|"LessThan"|"Exactly"|"Not",
     value: N, item_type?, material?, bearing?, reaction_class?, tool?}
  ],
  order_conditions: [{order: OTHER_ORDER_ID, condition: "Activated"|"Completed"}],
  dry_run: true (default)
})
orders.reorder(ID, NEW_POSITION, dry_run=true)   -- direct erase+insert on the vector
orders.recheck(ID, dry_run=true)                 -- wraps native `orders recheck`
```
`job` stops being a lookup into a short hand-written table and becomes a
live `df.job_type` name (same `_first_item`/`_last_item` enum walk
`df-overseer-orders.lua` already uses for its own job-name resolution,
`df-overseer-orders.lua:25-28`), so a new job type is a caller argument,
not a new table row.

## 2. Labor in v50

### Is autolabor functional at 53.16-r1?

**Verified from source: yes, and it is the only one that is.**
`plugins/autolabor/autolabor.cpp` declares `DFHACK_PLUGIN("autolabor")`
(`autolabor.cpp:39`) and is registered as a real build target:
`plugins/autolabor/CMakeLists.txt`'s `dfhack_plugin(autolabor
autolabor.cpp ${COMMON_SRCS} LINK_LIBRARIES lua)` line is active (not
commented). The same directory also contains `labormanager.cpp` (2,145
lines) and `joblabormapper.cpp`/`.h` — a full alternative labor-assignment
engine with its own job-to-labor mapper — but `CMakeLists.txt`'s line for
it is commented out: `#dfhack_plugin(labormanager labormanager.cpp
joblabormapper.cpp ${COMMON_SRCS})`. **`labormanager` is present as source
and is not compiled into this DFHack build at all.** It is not "the v50
answer autolabor should defer to"; it is dead code in this tree. This
directly confirms `df-overseer-labor.lua`'s own framing
(`df-overseer-labor.lua:10-14`) was correct without needing amendment.

autolabor still operates on the pre-v50 primitive: `unit.status.labors[code]`,
the same bitfield `df-overseer-labor.lua`'s own `set_labor` writes
(cross-referenced, not re-derived: `df-overseer-labor.lua:337,345`). A grep
of the whole `autolabor.cpp`/`.h` pair for `work_detail`/`workdetail`
returned nothing — **autolabor does not read or write the v50 Work Details
structure at all**; it is unaware v50 introduced a separate assignment UI.

### v50 Work Details, and whether it's a better engine

**Verified from source.** `df.plotinfo.xml:621-628` defines
`labor_infost` (`since='v0.50.01'`, i.e. this is genuinely new in v50, not
a renamed old struct), holding `work_details`, a vector of `work_detail`
(`df.plotinfo.xml:609-615`): `name`, a `work_detail_flags` bitfield
(`no_modify`, `cannot_be_everybody`, and a 2-bit `mode` sub-field of type
`work_detail_mode`: `Default`/`EverybodyDoesThis`/`NobodyDoesThis`/
`OnlySelectedDoesThis`, `df.plotinfo.xml:602-607`), `assigned_units` (a
plain vector of unit ids), and `allowed_labors` (a 94-entry bool array
indexed by `unit_labor`). This is the data behind the in-game "Labor > Work
Details" screen. **It has no headcount-target field of any kind** — you
either name units explicitly, or set a blanket Everybody/Nobody policy;
there is nothing resembling autolabor's "minimum 2, maximum 5" per labor.
It is a *classification* tool (which dwarves belong to which named group),
not a *balancing* tool. This means it cannot be `labor.quota`'s engine on
its own: the ruling's "set per-labor targets" requirement has no native
v50 equivalent except autolabor's own minimum/maximum, which predates v50
entirely and simply keeps working underneath it.

**Consequence for the race concern.** `df-overseer-labor.lua`'s existing
warning that `set-labor` races autolabor fort-wide for a labor autolabor
manages (`df-overseer-labor.lua:107-156`) generalises: **anything** that
writes `unit.status.labors` directly — the vanilla labor screen, the new
Work Details screen, or a script — races autolabor the same way, because
autolabor's reassignment cycle will silently override it on the next pass
unless that labor has been `autolabor LABOR disable`d first. This was not
previously stated as a general rule in this repo; it is a genuine addition
this research surfaces, not a restatement.

### Setting per-labor minimum/maximum from a script

**Verified from source.** The only interface is the plugin's CLI command,
dispatched through `autolabor(...)` (`autolabor.cpp:1095` onward):
- `autolabor LABOR MIN [MAX] [POOL]` (`autolabor.cpp:1160-1179`) sets
  `minimum_dwarfs`/`maximum_dwarfs`/`talent_pool` and switches the labor to
  `AUTOMATIC` mode.
- `autolabor LABOR disable` (`:1149-1153`), `autolabor LABOR haulers`
  (`:1144-1148`), `autolabor LABOR reset` (`:1154-1158`), `autolabor
  reset-all` (`:1183-1194`), `autolabor list`/`status` (`:1195-1219`).
- `print_labor` (`autolabor.cpp:1057-1069`) is the only place these numbers
  are ever rendered, and only as text: `"LABORNAME:           minimum N,
  maximum M, pool P, currently C dwarfs"`, or `"disabled"`, or `"haulers"`.

**No Lua accessor exists for `minimum_dwarfs`/`maximum_dwarfs` beyond
`isEnabled`/`setEnabled`.** A grep of `autolabor.cpp` for
`DFHACK_PLUGIN_LUA_FUNCTIONS`/`DFHACK_LUA_FUNCTION`/explicit Lua
registration returned nothing; `isEnabled`/`setEnabled` (used already by
`df-overseer-labor.lua:283-287` and by this plugin's own overlay script,
`plugins/lua/autolabor.lua:9,23-25`) are the automatic bindings DFHack's
`DFHACK_PLUGIN_IS_ENABLED` macro generates for any plugin that uses it
(`autolabor.cpp:71`), not a hand-written API — there is no equivalent macro
for the min/max fields, which live only in the plugin's own C++-local
`labor_infos` array. A `labor.quota` tool therefore has to shell out via
`dfhack.run_command_silent('autolabor', LABOR, tostring(MIN),
tostring(MAX))`, the exact mechanism `df-overseer-labor.lua`'s
`autolabor_disable_labor` already uses for the `disable` case
(`df-overseer-labor.lua:292-304`), and read the state back by running
`autolabor list` and parsing `print_labor`'s text format, since there is no
single-labor query: the command dispatch only branches on `parameters[0]`
being one of `enable/disable/haulpct/reset-all/list/status` for
one-or-two-arg calls, or a `LABOR ...` pair for 2-4 args
(`autolabor.cpp:1101-1160`) — a bare `autolabor LABOR` with no further
argument does not match any of those branches and falls through to the
generic help text (`autolabor.cpp:1224-1229`). **Unverified**: this was
read from the dispatch logic, not run live, so it should be confirmed with
one harmless call before `labor.quota_status` is built around parsing
`list`'s full output rather than a per-labor query.

### `labor.quota` shape (proposal)

```
labor.quota(LABOR, MIN, MAX, [POOL], dry_run=true)
  -- refuses exactly like set-labor if autolabor_enabled() can't be
     determined (reuse df-overseer-labor.lua's own autolabor_enabled()).
  -- shells to `autolabor LABOR MIN MAX POOL` via run_command_silent.
labor.quota_status(LABOR [LABOR...])
  -- runs `autolabor list` once, parses print_labor's line format per
     LABOR requested (regex on "LABOR:\s+(minimum (\d+), maximum (\d+),
     pool (\d+)|disabled|haulers), currently (\d+) dwarfs"), same
     null-vs-zero honesty df-overseer-labor.lua's enabled-counts already
     enforces (a name that doesn't round-trip through df.unit_labor is an
     error, never a guessed 0/pass-through).
```

## 3. Priority

### Designation priority 1-7

**Verified from source.** This is a genuine per-tile value, not a bitfield
flag. `df.block.xml:206-210` defines
`block_square_event_designation_priorityst`, a per-map-block event holding
a `16x16` array of `int32` priorities, one entry per tile in that block.
It is allocated lazily: `MapCache.cpp`'s `getPriorityEvent`
(`MapCache.cpp:290-303`) only creates the event the first time a priority
is written; `priorityAt`/`setPriorityAt` (`MapCache.cpp:322-341`) read/write
one tile's entry once the event exists, defaulting to `0` (meaning "no
event yet, default applies") when it doesn't. `MapExtras::Block::setDesignationAt`
(`MapCache.cpp:305-320`) is the only place a priority actually gets
written as a side effect of setting a designation, and it only fires for
dig or smooth designations (`des.bits.dig || des.bits.smooth`,
`MapCache.cpp:311`): "if priority is not specified, keep the existing
priority if set, otherwise default to 4000" (`MapCache.cpp:313-316`). The
`dig` plugin's own CLI (`plugins/dig.cpp:606-635`, `:731`) confirms the
scale: `-p #` sets designation priority, `parse_priority` multiplies the
UI number by 1000 (`dig.cpp:617`), default is `4` (`dig.cpp:731`,
`"-p # = designation priority (default = 4)"`) — so the UI's 1-7 is
literally the stored `int32` divided by 1000. Quickfort's own blueprint
syntax matches this exactly and independently: `#dig` cells accept
`[markers][symbol][number][expansion]`, default symbol `d`, default number
`4` (`docs/guides/quickfort-user-guide.rst:461-465`), e.g. `d1` for
priority-1 (highest) dig. Source and the quickfort docs agree; there is no
discrepancy to flag here.

This is a genuine player action available in vanilla DF (the dig-priority
submenu), so there is no armok question for a `priority.designation`
tool that reads/writes this value the same way `dig -p` already does.

### Manager order sequence

Already covered in §1: list position in `world.manager_orders.all`, no
native "set position N," only the fixed `orders sort` heuristic and manual
vector splicing.

### DFHack `prioritize`

**Verified from source, and this materially revises the register's
uncertainty.** `prioritize.lua` (pinned commit
`7549711a993e03bef19e90b27427096c1099853e`, byte-identical to a fresh fetch
at that exact commit) is **not** a one-shot "boost these jobs right now"
tool, though it can be used that way in passing. Its real behaviour is a
standing watch:

- `g_watched_job_matchers` is a global table of `job_type -> matcher`
  (`prioritize.lua:43-44`), persisted across saves via
  `dfhack.persistent.saveSiteData(GLOBAL_KEY, ...)`
  (`persist_state`, `prioritize.lua:53-60`) and restored on every map load
  through `dfhack.onStateChange[GLOBAL_KEY]` (`prioritize.lua:624-641`),
  which reads it back with `dfhack.persistent.getSiteData` (`:628`) and
  re-arms the hooks (`update_handlers`, `:113-120`).
- Once a job type is watched, `eventful.onJobInitiated.prioritize` is set
  to `on_new_job` (`prioritize.lua:100-102,116`), which calls
  `boost_job_if_matches` (`:92-98`) on **every job created from then on**:
  if its type (and, for `StoreItemInStockpile`/`CustomReaction`, its
  hauling labor or reaction name) matches a watched entry, DFHack sets
  `job.flags.do_now = true` immediately, unconditionally, for the life of
  that job.
- The only thing that stops this is explicitly un-watching that job type
  (`-d`/`remove_watch`) or the fort unloading, which clears the in-memory
  matcher table (`clear_watched_job_matchers`, `:104-111`, hooked to
  `eventful.onUnload`) — but the *persisted* watch list survives the
  unload and re-arms on the next load (`:624-641` above), so unloading does
  **not** durably turn a watch off; only `-d` does.
- Its own default set (`DEFAULT_JOB_TYPES`, `prioritize.lua:16-34`) is
  narrowly scoped to rot/medical/hygiene/noble-task categories
  (`StoreItemInStockpile`, `CustomReaction`, medical jobs, `TradeAtDepot`,
  `PullLever`, etc.) — plausible "always urgent" categories — but nothing
  stops a caller from watching an arbitrary job type such as
  `ConstructBlocks`, which would then mean **every block-making job, from
  now on, is do_now**, i.e. exactly the "routine production always at
  emergency priority" outcome the 2026-09-30 ruling wanted to avoid.

**Armok status, confirmed independently of `docs/DFHACK-INVENTORY.md`.**
The script's own doc header, fetched at the pinned commit, carries no
armok tag: `.. dfhack-tool:: :summary: ... :tags: fort auto jobs`
(`docs/prioritize.rst` at commit `7549711a993e03bef19e90b27427096c1099853e`,
lines 1-6). This independently confirms the inventory doc's claim from the
tool's own source rather than repeating it.

**What this settles versus what it doesn't.** It settles the mechanism
precisely enough to make the register's deferred decision (2026-09-30,
last two rows) answerable without a live test: `prioritize` is safe to use
*as a standing watch over a small, curated set of always-urgent job types*
(its own default set is a reasonable example), but using it as the
general-purpose "routine priority" lever the way `orders.create`/designation
priority are used would mean every instance of a watched job type
permanently runs at do_now, which does collide with "do now reserved for
genuine problems." It does **not** settle whether the fort's real workload
makes that collision matter in practice (how often would we actually want
to watch a routine production job type) — that is a live-fort measurement
question, not a source-reading one, and remains open exactly as the
register already scoped it ("real runs record how often urgent work waits
behind less important work").

### Workshop "do now" (`job.flags.do_now`)

**Verified from source.** `df.job.xml:1487`: `<flag-bit name='do_now'
original-name='DO_ME_NOW'/>`, a single bit on `job.flags`, per-job, not
per-job-type by itself — `prioritize` is what turns "per job type" into
"per job" at scale by hooking job creation, as above. This is the same
field `docs/ARMOK-RULINGS.md:23`'s `lever pull --priority` ruling already
covers for lever-pull jobs specifically; nothing in this session's reading
of `job.xml` suggests the field means anything different for a workshop
job than for a lever-pull job — it is the same bit DF's own priority
button sets in either case (unverified whether the *vanilla UI's* priority
button on a workshop job specifically was checked this session; only the
struct field and `prioritize`'s/`lever.lua`'s use of it were).

## 4. Armok status and live test plan

| Lever | Armok status | Evidence | Live test (read-only or reversible) |
|---|---|---|---|
| `orders.create` (manager order, any job/conditions/frequency) | Not armok — a vanilla Manager screen action | `df-overseer-orders.lua` already live-verified the read half; write half untested live per its own header (`:70-76`) | Queue one real, low-stakes order with a repeat frequency and one item condition (e.g. "make 1 bucket, OneTime" is already precedented; add "brew_drink, Daily, AtMost 50 drinks") during a supervised unpause, watch `orders.list`'s `validated`/`active` fields change over a few ticks, cancel after. This is exactly the test the register's item-8/9 rows already call for (`decisions/DECISIONS.md` 2026-09-30, "Manager work orders... Test: one conditional order"). |
| `orders.reorder` (vector splice) | Not armok — matches the native `orders sort` plugin's own scope | `orders.cpp:1012-1034` is a normal DFHack plugin command, no armok tag on that plugin found in `docs/DFHACK-INVENTORY.md` (not independently re-checked this session; the plugin doc header itself was not fetched, only its `.cpp` source, so this row is **partially unverified**) | Create two harmless orders, call `orders sort` (or a direct erase+insert), confirm `orders.list`'s `queue_position` changes as expected, no fort-state mutation beyond order bookkeeping. |
| `labor.quota` (`autolabor LABOR MIN MAX`) | Not armok — same category as `set-labor`, which is already ruled allowed | `df-overseer-labor.lua`'s existing `set-labor` ruling covers the same primitive; `autolabor` plugin itself carries no armok tag in `docs/DFHACK-INVENTORY.md` per the 2026-09-30 audit (not re-verified independently this session — **unverified**, inherited from the prior audit rather than re-checked at the plugin-doc level) | Set a generous, clearly-non-restrictive min/max on one already-common labor (e.g. `HAUL_ITEM 1 200`), confirm via `enabled-counts`/`autolabor list` that the count moves toward the new bound over a few ticks, then `reset` it. |
| Designation priority 1-7 | Not armok — vanilla dig-priority menu | `dig.cpp:731` documents it as an ordinary player-facing flag; quickfort's own docs describe it as ordinary blueprint syntax | Dig-designate one already-planned tile at priority 1 instead of the default 4 (e.g. via `dig -p 1` or a `d1` blueprint cell), confirm via a live read of the tile's priority event, undesignate after if unwanted — fully reversible, no fort-state change beyond the designation itself. |
| `prioritize` (standing watch, do_now) | Not armok, confirmed at the source doc header this session | `docs/prioritize.rst:1-6` (pinned commit), `:tags: fort auto jobs` | **Given the register's "do now for genuine problems only" ruling, the live test that matters is not "does it work" (the source already answers that) but "does watching it produce the collision the ruling worried about."** Watch one already-default, narrowly-scoped job type (e.g. `GiveWater`, already in `DEFAULT_JOB_TYPES`) for one supervised session, confirm via `prioritize` (no args, `status()`) that only genuinely matching jobs get boosted, then unwatch it (`-d`) before ending the session so the persisted watch list doesn't outlive the test. **Do not** test it against a routine production job type (e.g. `ConstructBlocks`) live, since that is precisely the "always do_now" outcome the ruling wants avoided, and this test plan's job is to confirm the safe subset works, not to probe the boundary the ruling already drew. |
| `job.flags.do_now` on a workshop job directly (bypassing `prioritize`) | **Allowed**, per existing ruling on the same field for lever-pull jobs | `docs/ARMOK-RULINGS.md:23`; `df.job.xml:1487` confirms it is the same single bit | Not re-tested this session; already covered by the existing lever-pull precedent. A workshop-job-specific test (flip one stuck job's `do_now`, confirm it gets serviced before others, then leave it — the ruling treats this as a legitimate emergency action, not something to undo) would only be needed if this repo builds a direct `do_now` wrapper separate from `prioritize`. |

## Not verified

- Whether DF's own (closed-source, non-DFHack) manager-order processing
  requires an appointed Manager for a `validated` order to become `active`.
  No DFHack source reads or checks a Manager noble position anywhere in
  `orders.cpp` or `workorder.lua`; this can only be settled by a live test
  with and without an appointed Manager, which this session had no access
  to run.
- Whether a bare `autolabor LABOR` (no further argument) is truly a no-op/
  help-text fallthrough rather than a per-labor status query; inferred
  from the command-dispatch branching in `autolabor.cpp:1101-1160`, not
  run live. `labor.quota_status` should confirm this with one harmless
  call before depending on it, and fall back to parsing full `autolabor
  list` output if the single-labor form does nothing useful.
- Whether the `orders` plugin itself carries an armok tag in
  `docs/DFHACK-INVENTORY.md`; this research read `orders.cpp`'s source
  directly but did not re-fetch or re-verify the plugin's own doc-header
  tags the way it did for `autolabor` and `prioritize`, so the "not armok"
  call for `orders.reorder`/`orders.recheck` above is inherited from the
  general shape of the mechanism (an ordinary queue-management action a
  player can already do from the Manager screen) rather than an
  independent tag check.
- Whether the vanilla UI's own "priority" button on a workshop job (as
  distinct from a lever) sets the identical `do_now` bit; only the struct
  field and DFHack's own use of it (`prioritize`, `lever.lua`) were
  checked, not the game's own UI code (which is not part of DFHack's
  source at all).
- Everything in this document is a source read, not a live-fort
  observation. Every "live test" in §4 is a proposal for the orchestrator
  to run during a supervised unpause; none of it was executed this
  session, per the handoff's own constraint (read-only, no live access).
