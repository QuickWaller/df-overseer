# Manager work orders: what they can express, and what actually runs

Date: 2026-09-18. Read-only research. Primary sources: this install's own
`workorder.lua`, the `orders` plugin's docs and shipped order-library JSON
files, and live `dfhack-run lua` enum/count reads against the paused
Uniboslan fort on VM 103 (`df@`, key from `.env`, `DF_VM_IP` stripped of
`/24`). `dfhack.world.ReadPauseState()` returned `true` immediately before
the first live read and again after the last; nothing was created,
cancelled, or modified, no unpause, no deploy. Pairs with
`research/2026-09-18-production-graph.md`.

## Bottom line

**Manager work orders are far more capable than this repo's own
`df-overseer-orders.lua` currently uses, and the capability that matters
most for Uniboslan already exists as a DFHack-shipped, pre-written order:
`orders import library/basic` queues a conditioned, repeating,
self-regulating brew order** (brew while raw plant ≥ 15 and an empty
food-storage container is free, stop once drink ≥ 3000, rechecked daily) in
one command, with no struct-writing needed at all. The project's existing
`workorder.lua` wrapper is the right layer for tool-specific one-shot orders
(blocks, mechanisms) but is the wrong tool for anything needing real
conditions, because `workorder.lua`'s own `create_orders` silently ignores
`is_validated`/`is_active` on write and has no import-time validation the
compiled `orders` plugin has. **Recommendation: use both**, in different
roles (see §7 below), not one instead of the other.

**The manager-appointment question has a real, install-specific, moderate-
confidence answer that changes the plan: Uniboslan has 15 citizens, and the
wiki's own text ties the hard manager-validation requirement to a
20-citizen threshold** ("once your fortress reaches 20 citizens, work
orders will not be performed until they are validated by the manager" , 
Dwarf Fortress Wiki, "Manager" page, fetched this session). Below that
threshold the implication is jobs get assigned without a formal Manager.
This is wiki-sourced (community_prior, player-facing behaviour, exactly the
class of claim this project's rules allow the wiki for) and **not
confirmed against this install's own code or by a live unpause**, DFHack's
own scripts contain no population-gated manager check to read instead, so
there is no code-level way to verify this without running time forward.
Treat it as the single most important untested assumption in this report:
if true, Uniboslan can likely run orders today with nobody in the Manager
seat; if false, nothing will move until a citizen is appointed.

## 1. Does an order run without a manager?

**Order *creation* is unguarded at the code level, confirmed by reading
`create_orders` in full this session**: nothing in it checks
`getNoblePositions`, an entity's MANAGER slot, or a manager's office. Any
caller with Lua access (this project's own tool included) can insert a
`df.manager_order` into `world.manager_orders.all` with nobody appointed.
Confirmed live: `world.manager_orders.all` is empty (count 0,
`manager_order_next_id` 0) and no citizen holds the MANAGER noble position
on this fort (`memory/dfhack-environment.md`, re-confirmed by this session's
own read of `df-overseer-orders.lua`'s `manager_appointed()` helper, which
scans `dfhack.units.getNoblePositions` over every active unit and finds
none).

**Whether the *engine* then turns a validated-nothing order into a real
workshop job with nobody appointed is not answerable from source alone**,
and this session did not unpause to test it (out of scope, read-only). Two
data points bracket the answer:
- `create_orders`/the `orders` plugin write the same struct either way;
  nothing in the writable API distinguishes "will run" from "will sit".
- The wiki's 20-citizen threshold (above) is the only concrete signal found
  this session that engine-side validation might not gate a *small* fort's
  orders at all. Confidence: moderate, single wiki page, not cross-checked
  against a second source or code.

**A manager's office is a wiki-stated additional requirement once a citizen
is appointed** ("A manager only performs their duties in their office...
though they only require a meager office", same wiki page). This project
has no appointment tool and no office-building tool; appointing a manager
is a nobles-screen action with no headless DFHack path found this session
(consistent with `mode` and other UI-gated screens already flagged
unavailable in `memory/dfhack-environment.md`).

**Verified, not assumed:** the `manager_order` struct itself carries no
population or noble-count field of any kind (confirmed by the full field
list in §2), any gating the engine does happens outside the struct
entirely, in whatever code path processes the manager's queue each tick,
which is closed-source.

## 2. Conditions: what the struct actually supports

Read in full from `create_orders` (`/opt/df/game/hack/scripts/workorder.lua`
on VM 103) and cross-checked against three real shipped order-library files
(`hack/data/orders/{basic,rockstock,furnace}.json`), not invented from the
wiki. The wiki's own description of the in-game Conditions screen (§ above)
matches this struct field-for-field, which is itself useful corroboration
that the screen is a thin UI over exactly this data.

| Field (on `manager_order_condition_item`, one per `item_conditions` entry) | What it expresses | Verified how |
|---|---|---|
| `compare_type` (`df.logic_condition_type`: `AtLeast`, `AtMost`, `GreaterThan`, `LessThan`, `Exactly`, `Not`) | The comparison operator | Live enum read this session |
| `compare_val` | The threshold number | `create_orders` source |
| `item_type` / `item_subtype` | Restrict to one item type (e.g. `DRINK`, `PLANT`, `BOULDER`) | source + shipped examples |
| `material` / `material_category` (order-level) | Restrict to a material or class (e.g. `INORGANIC`) | source + `rockstock.json`'s `ConstructMechanisms` example (`AtLeast 50 BOULDER material INORGANIC`) |
| `flags1/2/3` (from a name list: `empty`, `unrotten`, `non_pressed`, `food_storage`, `soap`, `non_economic`, `hard`, `non_absorbent`, etc.) | Item-state adjectives ("empty container", "unrotten plant") | source `set_flags_from_list` + shipped examples |
| `bearing` (ore-bearing inorganic) | "this much ore of a metal-bearing rock" | source only, no shipped example checked |
| `reaction_class` / `reaction_product` / `has_material_reaction_product` | Ties the condition to a raw-defined reaction product class (e.g. `DRINK_MAT`), not a literal item type, this is how "enough brewable plant" is expressed without listing every plant | source + `basic.json`'s brew order (`reaction_product: DRINK_MAT`) |
| `has_tool_use` (`df.tool_uses`) | "a container usable as a liquid container", not a literal item type | source + `basic.json`'s `PRESS_HONEYCOMB`/`PRESS_OIL` orders (`tool: LIQUID_CONTAINER`) |
| `contains` (seen in shipped JSON, e.g. `"contains": ["honey"]`) | A material-contents condition (mead needs an item *containing* honey) | shipped `basic.json` (`MAKE_MEAD`), not independently re-derived from `create_orders` source (that function doesn't set `condition.contains`, it is read on import by the compiled `orders` plugin or by the engine itself, not by `workorder.lua`; **this is the one condition kind `workorder.lua`'s own `create_orders` cannot write**, a real gap, not a gloss) |

**`order_conditions`** (via `manager_order_condition_order`): a real,
struct-level dependency between two orders, "only activate if order X is
completed or activated" (`df.workquota_order_condition_type`:
`Activated`/`Completed`, live enum read this session). This is exactly a
Bill-of-Materials precedence edge and is expressible without a UI.

**Directly answers the brief's two example questions**: "brew while drink is
under 20" is one `item_conditions` row, `AtMost item_type=DRINK value=20`
(the shipped default uses 3000, not 20, but the mechanism is identical, a
number the caller chooses). "Only if a barrel is free" is
`AtLeast flags=[empty, food_storage] value=N`, this is exactly what the
shipped brew order already does (`value: 5`), and it uses `food_storage`
rather than a literal `BARREL` item type, so it also matches pots and other
food-storage containers, which is the correct generalization, not a
narrower one.

**What is UI-only sugar and what is not:** nothing found this session is UI-
only. Every condition kind seen in the shipped JSON round-trips through the
same struct fields `create_orders` writes (with the one exception above,
`contains`, which the compiled plugin can write on import but
`workorder.lua`'s own Lua path cannot). The in-game Conditions screen is a
thin editor over this struct, not a separate mechanism, this matches the
docs' own claim ("labor restrictions... is actually still the case [as a]
vanilla feature... the DFHack overlay simply provides a UI for the vanilla
feature hiding beneath the surface") applied to the sibling conditions
screen by the same evidence pattern.

## 3. Repeats and frequency

`order.frequency` is `df.workquota_frequency_type`, a plain 5-value enum,
live-read this session: `NONE(-1)`, `OneTime(0)`, `Daily(1)`, `Monthly(2)`,
`Seasonally(3)`, `Yearly(4)`. **Directly struct-writable**: `workorder.lua`'s
own `fillin_defaults` sets `OneTime` only as a default when the caller
doesn't specify one; any of the five is a plain field assignment, no UI
needed. Every shipped library order this session inspected uses `Daily`.
The frequency governs when `amount_left` resets toward `amount_total` and
when conditions are rechecked (`orders recheck` manually forces an
out-of-cycle recheck, confirmed from the plugin's own doc text, not
independently tested live).

## 4. What can be ordered at all

| Class | Job type | Hardcoded or `CustomReaction` | Manager-orderable | Verified how |
|---|---|---|---|---|
| Stone blocks | `ConstructBlocks` (80) | Hardcoded | Yes, shipped in `rockstock.json` | live enum + shipped JSON |
| Mechanisms | `ConstructMechanisms` (139) | Hardcoded | Yes, shipped in `basic.json` | live enum + shipped JSON |
| Barrels | `MakeBarrel` (125) | Hardcoded | Job type exists and `df-overseer-orders.lua` already targets it, but **no shipped library file orders it** (checked all six library JSON files this session, zero `MakeBarrel` entries) | live enum + grep across shipped JSON |
| Brewing | `CustomReaction` `BREW_DRINK_FROM_PLANT` / `BREW_DRINK_FROM_PLANT_GROWTH` (209 for the plant case) | `CustomReaction` (a raw reaction, not its own job type) | Yes, shipped in `basic.json`, fully conditioned | live enum + shipped JSON |
| Cooking | `PrepareMeal` (114) | Hardcoded | Job type exists; not checked against a shipped library file this session (out of the brief's core four, included for completeness) | live enum read only |
| Milling | `MillPlants` (106) | Hardcoded | Yes, shipped in `basic.json` (`AtLeast 20 millable unrotten PLANT`, `AtLeast 5 empty BAG`) | live enum + shipped JSON |
| Fish cleaning | `PrepareRawFish` (105) | Hardcoded | Job type exists; **zero shipped library entries found** (checked all six files) | live enum + grep, negative result |
| Charcoal | `MakeCharcoal` (184) | Hardcoded | Yes, shipped in `furnace.json`, conditioned on wood stock and coal-bar/ore ceilings | live enum + shipped JSON |

**Not manager-orderable at all, needs a designation or a direct build
instead** (carried from this project's own existing tools and
`memory/dfhack-environment.md`, not re-derived here): digging, farm plot
placement and crop assignment, zone placement, workshop construction
itself, well construction. A manager order can only ask an *existing*
workshop to run a job; it cannot build the workshop, which is exactly why
Uniboslan's still must be built (or its `ConstructBuilding` job unstuck)
before any `brew_drink` order can ever leave "queued."

## 5. Prerequisites and failure modes

From `create_orders`, `df-overseer-orders.lua`'s own header commentary
(already live-verified this project, re-read and confirmed this session
rather than re-derived), and the `orders` plugin doc:

| Failure mode | What it looks like | How a caller tells it apart |
|---|---|---|
| No manager appointed | Unknown at the engine level (§1); the struct itself never records "why" an order isn't running | `manager_appointed()` as `df-overseer-orders.lua` already computes it; not a proof of cause |
| No matching workshop built | Order sits with `amount_left == amount_total` forever, `is_active` stays false | `df-overseer-orders.lua`'s `workshop_exists_count`, already live-verified this project |
| Conditions never satisfied | Same signature as above: `is_active` false, no jobs spawned | Read `item_conditions` back against a live stock count (the production-graph's own live-read tools) |
| No labor holder / no tool (axe, container) | A job *can* spawn (order goes active) but never gets a worker, exactly the still's `ConstructBuilding` job today (id 366, unassigned across a full unpause per `Working.md`) | This is a job-level, not order-level, symptom, `dfhack.job.getName`/reading the spawned `df.job`'s own assignment, not readable off `manager_order` alone |
| Full/no free container | Expressible and preventable via an `AtLeast empty food_storage` condition (§2); without one, a job can spawn and then stall hunting for a container | Compare `item_conditions` presence against the goal |
| Suspended workshop | Not investigated this session (out of the brief's core scope); flagged as untested |
| Order was queued with `amount_total < 0` internally (workorder.lua's `__reduce_amount` logic under-subscribes) | `create_orders` silently `order:delete()`s it, no error, no trace | Only visible by diffing `list_orders()` before/after a create call |

**The one clean, struct-level "is it progressing" signal that exists
without a scheduler**: `amount_left` vs `amount_total`, read via
`list_orders()` (already built). A daily-frequency order whose
`amount_left` is below `amount_total` **right after** its own recheck point
proves at least one job spawned and was claimed; an order whose
`amount_left` never moves across a full day-boundary, with the matching
workshop confirmed built and the condition confirmed satisfied, is the
closest this project can get to "stuck" without reading the live `df.job`
list. This project has no engine-exposed `is_active`/`is_validated` read
path yet, `df-overseer-orders.lua`'s `list_orders()` does not currently
surface them (see gap in §8) even though `create_orders` shows the fields
exist on the struct (commented out on write, but readable).

## 6. Reading progress

**What exists to read, all confirmed from source, not assumed:**
- `order.amount_left` / `order.amount_total`, the only running counter on
  the order itself. No separate "completed count" field exists; completed
  = `amount_total - amount_left` for a one-time order, and resets each
  cycle for a repeating one, so a cumulative total needs the caller to sum
  across cycles itself.
- `order.status` (`validated`/`active` sub-fields, referenced but not
  written by `create_orders`, which comments them out entirely) and
  `finished_year`/`finished_year_tick` (also referenced, not written), a
  real read gap: this project's own tool can create the struct but has
  never read these fields back, and `create_orders`'s own choice to skip
  them on write means anything created via `workorder.lua` starts with
  whatever the struct's zero-value is for those fields, not necessarily a
  sane "not yet validated" state. **Worth a direct live read (a genuinely
  new probe, not run this session since it needs an existing order to
  inspect and none exist) before trusting them.**
- `dfhack.job.getManagerOrderName(order)`, a ready-made human-readable
  description, confirmed present in the Lua API docs this session.
- `JOB_COMPLETED` (via `eventful`), already wired in
  `scripts/dfhack/df-overseer-diff.lua` (`eventful.onJobCompleted`,
  confirmed by direct read this session, line ~187). **Currently it
  discards everything except a text name** (`dfhack.job.getName(job)`); the
  full `df.job` struct handed to the callback carries `job_type`,
  `reaction_name`, `mat_type`/`mat_index`, and the workshop reference, the
  exact fields needed to attribute a completion to a specific
  `production_process` row from the sibling research doc's schema. This is
  a small, well-scoped extension, not new plumbing.
- **Honest gap, carried from `research/2026-09-18-production-graph.md`
  unchanged, not re-litigated here**: job duration/timing is unavailable;
  `df.job` proves a completion happened, not how long it took.

**Answering the brief's question directly**: `JOB_COMPLETED` events,
extended to capture `job_type`/`reaction_name` instead of just a name
string, are enough to measure *produced per period* without a scheduler
running continuously, provided something polls or logs the event stream at
whatever cadence the fort actually runs (this project's existing
`df-overseer-diff.lua` ring-buffer mechanism already does this for other
event types). It is **not** enough on its own to measure *consumed* or
*in-flight* (an order that is "Active" but whose job hasn't completed yet)
without also diffing live stock, exactly what the production-graph doc's
own §4 measurement plan already concludes.

## 7. `workorder.lua` and the `orders` plugin: what each actually offers

**Two genuinely different tools exist on this install, both already
present, and this project has only used one of them:**

1. **`workorder.lua`** (`hack/scripts/workorder.lua`), a pure-Lua script,
   the one `df-overseer-orders.lua` already wraps. Exposes
   `preprocess_orders`/`fillin_defaults`/`create_orders` as reqscript-able
   functions (confirmed, this is exactly how this project's own tool calls
   it). **Can write `item_conditions`, `order_conditions`, `frequency`,
   `workshop_id`, `max_workshops`**, everything in §2 and §3 except the
   `contains` condition kind, which its own `create_orders` never sets.
   No import/export file format handling, no "recheck" support, no
   validation feedback beyond raising a Lua error (`qerror`) on a bad job
   name. **This project's current tool uses none of this beyond the bare
   `job`/`amount_total` pair**, the conditions, frequency, and dependency
   machinery are all unused capability already installed.

2. **The `orders` plugin** (`hack/plugins/orders.plug.so`, compiled C++;
   its Lua half at `hack/lua/plugins/orders.lua` is UI overlay code only,
   confirmed by reading it this session, `dialogs.ListBox`,
   `gui.widgets`, nothing headless-relevant). Exposes plain CLI commands,
   confirmed from its own doc text with no UI precondition stated for any
   of them (unlike some fortress-mode features gated behind a specific open
   screen elsewhere in this project's own history, not independently
   proven this session since running one would create a real order, but
   consistent with sibling headless plugins already verified in this
   project, `caravan`/`diplomacy`/`logistics`): `orders list`, `orders
   export <name>`, `orders import <name>`, `orders clear`, `orders recheck
   [this]`, `orders sort`. **Ships six ready-made, hand-tuned order-library
   files** at `hack/data/orders/{basic,furnace,military,rockstock,
   glassstock,smelting}.json`, importable by name (e.g.
   `dfhack.run_command('orders', 'import', 'library/basic')`).
   `library/basic`'s own brew order (§2, quoted in full) is a better-
   designed version of exactly what this project wants for Uniboslan's
   drink problem than anything `df-overseer-orders.lua` currently builds,
   and it costs one command, not a struct write.

**Recommendation: extend `df-overseer-orders.lua` to wrap both, in
different roles, rather than picking one:**
- Keep `workorder.lua` for **one-shot, uncondtioned amounts this project
  already needs** (a fixed number of blocks or mechanisms to unblock a
  build, where "make exactly N" is the actual intent, not an ongoing
  policy).
- Add a thin wrapper around **`orders import`/`orders export`/`orders
  recheck`** for anything that should run as a standing policy (brew,
  charcoal, mechanisms-from-boulders), reusing the shipped library files
  where their conditions already match this project's doctrine (the brew
  order's `AtMost DRINK value: 3000` ceiling should probably be doctrine-
  tuned down for a 15-citizen fort, but the *shape* of the order needs no
  invention). This also gets `is_validated`/`is_active` handling and
  `recheck` for free, which `workorder.lua`'s own `create_orders` does not
  give.
- **Writing the struct directly (bypassing both scripts) is not
  recommended.** Nothing found this session needs a capability neither
  script exposes except the `contains` condition (§2), which is a narrow,
  named gap, not a reason to abandon two already-working, already-deployed
  abstractions DFHack itself maintains.

## 8. The gap list for Uniboslan specifically

| Blocker | Solvable by orders alone? | What else is needed |
|---|---|---|
| No drink | **Partially.** `orders import library/basic` (or a hand-written equivalent order) can queue a correctly-conditioned `brew_drink` order today, struct-writable with no new tool code. But it produces nothing until the still exists (below) and cannot itself fix "nobody worked the still's construction job," which is a labor-assignment problem, not an order problem. | The still built; a citizen with the relevant labor actually taking the brewing job once it spawns (unverified, no manager appointed) |
| Still not built | **No.** Manager orders can only ask an existing workshop to run a job; building the workshop is the existing `df-overseer-workshop.lua`'s job (already has a `still` kind per `handoffs/2026-09-17-water-and-industry-tools.md`), and getting a worker to actually execute the pending `ConstructBuilding` job (id 366, unassigned across a full unpause per `Working.md`) is a labor/priority problem this research does not address | Diagnose why `ConstructBuilding` id 366 has no worker (suspended flag vs. never-assigned, per `Working.md`'s own open question) |
| No blocks | **Yes, once a Mason's Workshop exists.** `ConstructBlocks` is shipped, conditioned, ready to import (`rockstock.json`) | A Mason's Workshop (`df-overseer-workshop.lua` already supports `mason`) and boulders (stone access, i.e. digging to z167, flagged as a still-open gap in `decisions/DECISIONS.md` 2026-09-17: "the dig finder still cannot propose a dig two levels down") |
| No mechanisms | **Yes, once a Mechanic's Workshop exists**, same shape as blocks (`basic.json`'s `ConstructMechanisms` example) | A Mechanic's Workshop and boulders, same stone-access gap as blocks |

**None of Uniboslan's four named blockers is actually a work-order design
problem.** The order layer (conditions, frequency, amounts) is already more
capable than anything currently blocking this fort; every real blocker is
upstream of the manager (a workshop not built, a job not worked, stone not
reachable) or downstream of it (whether the engine runs an order with no
manager appointed, unverified). Building a more elaborate work-order tool
right now would not unblock Uniboslan; fixing the still's stuck build job
and the stone-access dig gap would.

## Deliverables

**What an order can express**, see the table in §2 (conditions) and the
frequency enum in §3; both struct-writable via `workorder.lua`, with the
single named exception of `contains`, writable only via the compiled
`orders` plugin's import path.

**Recommendation**, extend `df-overseer-orders.lua` to also wrap the
`orders` plugin's `import`/`export`/`recheck`/`list` commands alongside its
existing `workorder.lua` calls; do not hand-write `df.manager_order`
structs directly. Reason: both scripts are already installed, already
proven callable this project, and cover everything this brief asked for
except one narrow condition kind.

**"Progressing vs. stuck", concretely**: read `amount_left` vs
`amount_total` across a known recheck boundary (the frequency field tells
you when that boundary is), cross-checked against `workshop_exists_count`
(already built) and a live stock read against the order's own
`item_conditions` (comparable to what the production-graph's
`find_blocker` query already plans to do). Full certainty additionally
needs `status.validated`/`status.active` read back (not yet read by any
tool this project has, flagged as a real, small, next step) and
`JOB_COMPLETED` events attributed by `job_type`/`reaction_name` (needs a
one-line extension to `df-overseer-diff.lua`'s existing handler, not new
plumbing).

**Test plan for the first real order on Uniboslan (supervised session,
later)**:
1. Before touching anything: confirm live whether a citizen holds the
   Manager position (repeat this session's `manager_appointed()` check) and
   record the population (15, unless it has changed).
2. Read `world.manager_orders.all` (should still be empty) and
   `manager_order_next_id`, so a before/after diff is possible.
3. Create exactly one order: either `orders import library/basic`'s brew
   entry alone (best fidelity, DFHack-authored conditions) or the
   equivalent hand-built `workorder.lua` call this project's own tool
   already supports (`create JOB blocks/mechanisms AMOUNT`, since the still
   is not built yet, this is the more actionable first real test:
   `ConstructBlocks`, a small fixed amount, once a Mason's Workshop and
   boulders exist).
4. Read `world.manager_orders.all` immediately after: confirm the struct
   fields match what was requested (`job_type`, `amount_total`,
   `frequency`, `item_conditions` count).
5. **Supervised unpause**, short window (the project's existing 10 FPS
   throttle pattern), watching for: (a) does `amount_left` move at all,
   (b) does a real `df.job` appear at the matching workshop
   (`dfhack.job.getName` on `world.jobs.list` or the workshop's own job
   queue), (c) does `JOB_COMPLETED` fire and match the order's
   `job_type`/`reaction_name`.
6. Whatever the population/manager question resolves to (moves or doesn't),
   record it as a settled, live-tested fact in `memory/dfhack-environment.md`
  , this is the single biggest unresolved unknown this report leaves
   behind, and one supervised unpause answers it for good.

## What could not be verified

- **Whether Uniboslan's orders would actually run with no manager
  appointed, at 15 citizens.** No code-level gate was found to read
  instead; the wiki's 20-citizen threshold is the only lead, and it is a
  single wiki page (community_prior, not cross-checked against a second
  source), not tested live this session (would require an unpause, out of
  scope for a read-only brief).
- **What DF's own manager-order-processing code does each tick.** It is
  closed-source; every claim about it in this report is either a DFHack
  script's own silence (no gate found) or the wiki's player-facing
  description, never a direct read of the engine's own logic.
- **`order.status.validated`/`order.status.active`'s actual runtime
  values.** `create_orders` never sets them and this session found no
  existing order to read them from (the queue is empty). A live read
  against a real order, created in a future supervised session, is needed.
- **Whether `orders import`/`export`/`recheck`/`sort`/`clear` truly need no
  open screen.** Inferred from the doc's own plain CLI phrasing and this
  project's precedent with sibling headless plugins (`caravan`,
  `diplomacy`, `logistics`), not independently tested this session (any
  real test would create/modify orders, disallowed).
- **Suspended-workshop failure mode** (listed as untested in §5): not
  investigated, no example encountered live (Uniboslan has no still built
  yet to suspend).
- **Whether a spawned workshop `job` carries any field linking it back to
  its originating `manager_order`.** Not found in the docs or scripts read
  this session; `job_type`/`reaction_name`/workshop matching is the
  fallback this report recommends instead (§6), and it is sufficient for
  the stated measurement goal but is inference-by-matching, not a direct
  foreign key.
