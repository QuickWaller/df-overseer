# Why a manager work order can be validated and still never produce jobs

Date: 2026-10-08. Researcher, offline (no VM access), read-only. Sources read this session: DFHack
`plugins/orders.cpp`, `plugins/autoclothing.cpp`, `plugins/autoslab.cpp`, `plugins/lua/stockflow.lua`,
`library/modules/Job.cpp`, `library/modules/Materials.cpp`, `data/orders/*.json` (develop branch), the
`scripts` repo (`workorder.lua`, `prioritize.lua`), `df-structures` (`df.workquota.xml`, `df.d_basics.xml`,
`df.plotinfo.xml`), the DF wiki (raw wikitext of Manager, Work orders, Still, Brewer, Organizer, Skill),
Steam discussion threads, and this repo's own `scripts/dfhack/df-overseer-orders.lua` and prior research.

Evidence tags: **[source]** read in code or data files this session; **[wiki]** DF wiki text;
**[community]** forum or Steam report; **[inference]** my reasoning, not shown by any source;
**[unverifiable]** the behaviour lives in the closed game engine.

## Answer up front

1. **Nothing public documents the engine's validated-to-jobs step.** The `validated` and `active` bits are
   just two flags on the order **[source: df.workquota.xml]**. DFHack never sets them except on import and
   `orders recheck`; the transition logic is in closed DF code **[unverifiable]**. Anything below about
   *when* the engine acts is inference.
2. **Our script-created orders are structurally the same shape DFHack's own autoclothing, autoslab and
   library imports use, and those are used in v50 without trouble [community-weak, source for the shape].**
   So "created by script" is not by itself the defect. The real differences from a UI order are (a) material
   fields (UI buttons always carry a material for item jobs), and (b) possibly engine-built state (`items`)
   that only exists after the game processes the order.
3. **The -1/-1 material is a real divergence from any UI-made item order, but a *source* does not show it
   stops job creation.** It does explain the "unknown material" label. It cannot explain the brew order,
   because a brew reaction order legitimately has no material.
4. **The user's observation (validation happens) and the zero-ORGANIZATION-skill reading can both be true;
   see section 6.**

Top suspects, in order, with the cheapest live test, are in the last section.

## 1. What `validated` and `active` mean, and when jobs appear

- `manager_order.status` is a two-bit bitfield `validated`, `active` (`df.workquota.xml`, struct
  `manager_order_status`) **[source]**. Other relevant fields: `items` (`job_reqst*`, original name `jbr`),
  `finished_year` / `finished_year_tick` (original names `next_check_year`, `next_check_season_count`),
  `workshop_id` (`forced_bld_id`), `max_workshops` (`maximum_active_bld`, "0 is unlimited") **[source]**.
- DFHack's own docs say `orders recheck` "sets the status to `Checking` (from `Active`)" and that it "makes
  the manager reevaluate its conditions" **[source: docs/plugins/orders.rst]**; the code implementing it
  clears **both** `active` and `validated`, only for orders that have `item_conditions` and are `active`
  (`orders.cpp` `orders_recheck_command`, `:1040-1050`) **[source]**. So in the UI the order status text is
  `Checking` while not active, `Active` once started. Orders with no conditions (our brew order, the three
  stone orders) are untouched by `recheck`.
- `workorder.lua` explicitly ignores `is_validated` / `is_active` when creating (`workorder.lua:278-279`
  comments, and docs: "ignored when generating new orders") **[source]**; stockflow likewise creates with both
  false and carries `-- Todo: Create in a validated state if the fortress is small enough?`
  (`stockflow.lua` create_orders) **[source]**. That comment is circumstantial evidence that the game itself
  creates UI orders already validated in small forts, matching the wiki: "once your fortress reaches 20
  citizens, work orders will not be performed until they are validated by the manager"; below 20 "orders
  execute without validation" **[wiki, Manager]**. Uniboslan has 22 alive, so it is over the line.
- Who validates: a `ManageWorkOrders` job (job type 195, skill ORGANIZATION, no `type` attribute) done by the
  manager in his office **[source: df.job.xml, from the 2026-10-01 research; wiki Manager "Office"]**. The
  wiki says validation is "fairly high priority" but the manager must have free time and not be "called far
  from the office" **[wiki]**. DFHack's `prioritize` default list names `ManageWorkOrders` under "ensure
  noble tasks never get starved" (`prioritize.lua:29`) **[source]**: DFHack's authors consider it
  starvable by labor jobs, which supports that a manager with enabled labors can be slow or late to validate.
- **Known engine bug [community]:** "if the manager starts the validate work orders task and gets
  interrupted, the job is never recreated"; workaround is to reduce interruptions and add new orders to
  reschedule it (Steam thread "Not validing orders - manager"). Not verified against code.
- **Validated to jobs.** Which workshop, how often and the exact checks (materials present, workshop free,
  worker with labor) are **[unverifiable]**. Documented inputs that the wiki and DFHack data imply:
  workshop must allow general orders (`max_general_orders`, `block_general_orders`, per-labor blocks;
  our 2026-10-07 read found all permissive), job-type-to-workshop match, enough job-item inputs of the
  required kind. DFHack's `orders sort` doc warns that repeating orders earlier in the list "prevent
  one-time orders from ever being completed" **[source]**, i.e. order position and per-workshop job caps
  matter, but our four workshops had 0 jobs.
- Wiki note that matters for material: "if ... the job is confirmed by the manager before you change [the
  material] then any material will be used for the job instead of the restricted material" **[wiki, Work
  orders, Bugs]**. This reads as: at validation the manager freezes the order's job inputs. It also reads as
  an unrestricted (any material) order *does* work in the UI. **[inference]** that the frozen state is
  `order.items`.

## 2. -1/-1 material: ours vs UI vs DFHack

- **What "Make unknown material blocks" means [source].** `dfhack.job.getManagerOrderName` builds the
  display text by copying the order's fields into an `interface_button_building_new_jobst`
  (`jobtype, itemtype, subtype, material=mat_type, matgloss=mat_index, specflag, job_item_flag=
  material_category, specdata, art_specifier ids`) and asking it for text (`Job.cpp:688-710`). The
  work-order "new order" list is built from the same button type, so **a UI-made order is a button's
  fields verbatim, and for stone/wood item jobs each button carries a concrete material or category.**
  An order with mat -1/-1 and an empty category has no button equivalent, hence "unknown material".
  **[inference]** from the shared struct; the UI list itself is closed code.
- **DFHack's reference values [source].** Library orders for ConstructBlocks, ConstructMechanisms,
  ConstructThrone etc. carry `"material": "INORGANIC"` (`data/orders/rockstock.json`, basic.json).
  `MaterialInfo::find("INORGANIC")` has one token, so it goes to `findBuiltin` and returns
  `decode(0, -1)`: **mat_type 0, mat_index -1** (`Materials.cpp:168-188`, `:210-228`). stockflow's `rock`
  material is `{mat_type = 0}` with mat_index defaulting -1 (`stockflow.lua`, `materials.rock.management`)
  and it deliberately overrides `mat_type = -1` for all other orders with the comment "These defaults differ
  from the newly created order's" **[source]**. Wood uses `material_category = {wood = true}`.
- **What workorder.lua does with no material [source].** `create_orders` only assigns `mat_type/mat_index`
  when the entry has `meal_ingredients` or `material` (`workorder.lua:230-243`), and categories only when
  `material_category` is present (`:260-265`). `fillin_defaults` only sets a metatable default of
  `frequency = 'OneTime'` (`:511-519`). **There is no material default.** So a bare entry leaves whatever
  `df.manager_order:new()` initialises. NOTE: in the current `df.workquota.xml`, `mat_type` has **no
  `init-value`** (only `mat_index` has `-1`), which would make a fresh order read 0/-1, not -1/-1; yet our
  live read of the old orders was -1/-1. Either the installed structures differ from master or the earlier
  tool path set them. **Not resolvable offline; worth one live `new()` read.**
- **Our code, `df-overseer-orders.lua` [source].** `ORDER_MATERIAL_POLICY` (`:233-260`) defaults
  `material = "INORGANIC"` for ConstructBlocks / ConstructMechanisms / ConstructThrone and
  `category = {"wood"}` for MakeBarrel (`:256`, marked `inferred`). `create_order` applies it when material
  and category are both blank and the job is not a reaction (`:758-775`), then calls
  `preprocess_orders`, `fillin_defaults`, `create_orders` (`:832-853`). `matinfo.find` is called on the
  caller's string (`:742-747`), so the log's "rock" must be the label for `INORGANIC`; the stored order should
  read mat_type 0, mat_index -1 with an empty category, identical to the library. **[source for the code,
  not live-confirmed for the stored values after the 2026-10-07 repair; read them back.]**
  MakeBarrel's category `wood` is by analogy with MakeBucket and is not in the library **[source, own comment
  `:231`]**.
- **Stone-use restriction [inference].** `df.d_basics.xml` defines job-item flag `non_economic`
  (original `WORTHLESS_STONE_ONLY`), and `plotinfo.economic_stone` (`stone_restriction`) is the per-stone
  Stone Use setting. Library blocks orders pair INORGANIC with a `non_economic` boulder condition. The
  2026-10-07 read counted "20 free boulders"; if all of those are economic stone (ores, gems-bearing) and
  the Stone Use setting forbids them for construction, "rock blocks" would have no valid input.
  **Plausible, unverified.** Community text: certain stones "may need to be enabled for economic use through
  the Labors menu > stone use" (Steam search result, **[community-weak]**).

## 3. Brewing order inputs

- Reaction code `BREW_DRINK_FROM_PLANT`; DFHack's library version carries conditions `unrotten` PLANT with
  `reaction_product DRINK_MAT` at least 15, `empty` + `food_storage` items at least 5, DRINK at most 3000
  (`data/orders/basic.json`) **[source]**. The reaction takes `PLANT` items, not fruit; fruit/growths are the
  separate `BREW_DRINK_FROM_PLANT_GROWTH`. Conditions are optional; ours has none, which is allowed.
- Inputs: a Still, a brewable plant, and "one empty barrel or water-tight pot per job", and a dwarf with the
  Brewing labor **[wiki, Brewer / Still]**.
- Known reasons a brew sits idle **[wiki, Brewer troubleshooting]**: no item the kitchen screen counts as
  brewable (z, Kitchen tab); no free barrels/glazed pots (barrels are filled with food by stockpiles first);
  Still linked to stockpiles lacking components; Still inside a restricted burrow; items in a container with
  an active "store item" job are unavailable (bug 9004); embark-bought fruit in bags can't be brewed
  (bug 7423); no idle dwarf with Brewing enabled; no path; brewer in a burrow excluding the Still (bug 2262).
  The wiki says the **Still's own task button turns red text when the game decides resources are missing**.
- Therefore a brew order with unknown plant stock is the most likely *inactive-forever* case regardless of
  material or validation. **Our 2026-10-07 read established barrels (27) but not that any is empty, nor that
  any brewable PLANT exists, nor that someone has BREWER enabled** (the README lists labors only for the
  manager).
- Also note: the 46-day run's `drink 0` is consistent with "no job ever created" but equally with "job
  created then no one took it"; the 2026-10-07 job list (6 jobs, none with `order_id`) argues for the
  former **[source: README]**.

## 4. Pinning orders to a workshop

- `manager_order.workshop_id` exists (`forced_bld_id`) and DFHack imports/exports it (`orders.cpp:397-399`,
  `:677-688`; `workorder.lua:286-292`) **[source]**. The wiki confirms UI support: orders made from the
  individual workshop's Work orders tab apply only to that workshop **[wiki, Manager]**.
- DFHack's `orders sort` places workshop-tied orders first (`orders_compare`, `orders.cpp:1013-1018`;
  changelog) **[source]**.
- Behaviour when the pinned workshop is wrong, busy or blocked is **[unverifiable]**. Our tool exposes it
  (`df-overseer-orders.lua:778-788`, rejects a non-existent building id only). Pinning is a cheap diagnostic
  lever (a bypass for "which workshop does the engine choose?") and a UI-parity test: the UI workshop tab
  creates exactly such orders. `max_general_orders` and "block general orders" are bypassed or not for
  pinned orders is **unknown**; the wiki says an explicit "general work orders allowed 0" stops the manager
  assigning *general* tasks, which suggests pinned ones are exempt **[wiki, inference]**.

## 5. Tools that show why an order isn't producing

None gives a reason string. Closest, all read-only **[source unless noted]**:
- `dfhack.job.getManagerOrderName(order)` (Lua): the UI's own label for an order; use it to prove a stored
  order renders as "rock blocks" and not "unknown material".
- Direct field dump of every `manager_order` field including `items`, `specflag`, `specdata`, `art_spec`,
  `finished_year*`, `item_conditions`, and a diff of a UI-made order against ours (no tool does this; a Lua
  loop does).
- `devel/jobwatch unit <id>|all`: prints job transitions per unit per tick; shows when the manager takes
  `ManageWorkOrders` and when a workshop job appears (`jobwatch.rst`; verbose adds job id and `do_now`).
- Job link: any job with `job.order_id ~= -1` or `flags.by_manager` is order-spawned (`df.job.xml`, from
  the 2026-10-01 research) **[source]**; `prioritize.lua` uses `job.order_id` the same way (`:582-590`).
- `orders recheck [this]`: forces re-evaluation, only for orders with conditions.
- `gui/workorder-details`, `gui/workshop-job`: edit input items/materials; both tagged `unavailable` in v50
  docs.
- `gui/notify`: overlay of important events; does not itemise orders (not read in detail).
- The vanilla Still/workshop task list colours (red = resources missing) is the only in-game "why" for
  inputs **[wiki]**.

## 6. The ORGANIZATION skill reading vs the user's observation

- The wiki says XP is granted at validation, not completion, and that it is "trivially easy" to train
  **[wiki, Manager]**. The 2026-10-07 inference ("zero skill so never validated") assumed the skill entry
  must exist after one validation. That assumption is untested: skill entries in `current_soul.skills` only
  exist after XP, but nothing I found documents the XP amount or conditions for `ManageWorkOrders`
  **[unverifiable]**.
- Candidate reconciliations, none confirmed: (a) the validations the user saw were done by a different
  unit (earlier manager, or the `MANAGER` assignment changed hands; the repo's own 2026-10-01 scan found a
  `MANAGER` assignment resolving to no live unit, `research/2026-10-01-orders-not-dispatching.md` short
  answer) so unit 345's list legitimately lacks the skill; (b) orders 0-2 were created while the fort was
  under 20 citizens and arrived validated, with the user's sighting being of other orders; (c) validation
  occurred but ORGANIZATION XP is not granted, or is gated (the wiki Skill page notes facets can block
  certain social skills' XP altogether, **[wiki]**, applied to Organizer only by analogy); (d) the skill
  check read the wrong unit or struct. The user says he watched it; treat that as ground truth and use
  (a) and (c) to explain the number, not to question the observation.
- Observation that strengthens "validation works": orders 3 and 4 (and 5-8 after repair) are the only ones
  not validated; the user's testimony covers 0-2.

## 7. Our code against the findings

| Item | Finding |
|---|---|
| Stone item orders carry INORGANIC (type 0, idx -1) | Matches DFHack library and stockflow `rock` [source]. |
| Wood barrel uses `material_category wood` | Matches how DFHack/stockflow express wood [source]; barrel itself not in library [source]. |
| We never set `validated`/`active` | Same as every DFHack creator; correct [source]. |
| Brew order with no material, no conditions | Valid shape; library adds conditions but they are optional [source]. |
| `finished_year`/`tick` | Left at struct default -1; same as other creators; irrelevant for OneTime [source]. |
| Reading `order.items` | **Not done anywhere in our tool.** It is the most direct "has the engine processed this order" signal [inference]. |
| Documented knobs `max_workshops 0` | Correct ("0 is unlimited", df.workquota.xml comment) [source]. |
| README line "Masons 5 / Still 4..." ruled-out profile refusals | Stands; still worth recheck after unpausing, since profile values were read while paused [source: README]. |

## 8. Top suspects and cheapest live tests

1. **The brew order has no valid inputs or no taker (plant stock, empty barrel, BREWER labor, kitchen
   exclusion).** Highest prior; explains the one order the material theory cannot. Cheapest test, read-only
   and 30 seconds in game: open the Still, add a task, look at the "Brew drink from plant" colour (red =
   game says resources missing). In Lua: count unrotten PLANT items with DRINK_MAT product not forbidden or
   in a store job, count empty barrels/pots, and list units with BREWER enabled.
2. **Script-created orders differ from UI-made ones in some field the engine needs (material is the visible
   one; `items` is the hidden one).** Cheapest test: have the user add one "Make rock blocks" order in the
   UI beside our `ConstructBlocks` order, then dump all fields of both (including `items`, `specflag`,
   `specdata`, `art_spec`, `finished_year*`, `item_type`, `item_subtype`) and `getManagerOrderName` for each,
   and diff. Also record whether `order.items` is non-nil on a validated order (null on 0-2 would mean the
   engine never finished processing them). Needs unpausing only if you want the UI order to validate; the
   dump is read-only.
3. **Validation or dispatch is starved or interrupted (manager busy with MASON/STONE_CRAFT labors, the
   "interrupted, never recreated" bug), or stone-use restricts rock blocks to unavailable stone.**
   Cheapest tests: run `devel/jobwatch unit 345` while briefly unpaused and watch for `ManageWorkOrders`
   (and check whether `prioritize` is enabled); for stone, list the 20 boulders' materials against
   `plotinfo.economic_stone` and the `non_economic` rule. A fourth, mutating lever if the above show a
   stuck order: clear `validated`/`active` on one order so the manager re-evaluates (this is what
   `orders recheck` does, but it skips orders without conditions) or create the same order pinned to the
   workshop (`WORKSHOP_ID`) as the UI workshop tab does; both need the user's go-ahead.

## Not verified

- The engine's validated-to-jobs logic, cadence, and failure behaviour (closed source). No source or wiki
  page states them.
- Whether -1/-1 material by itself blocks job creation. Only the "unknown" label and the shared
  button-struct are verified.
- The initial `mat_type` of `df.manager_order:new()` on the installed version (master XML says 0 or
  unspecified, our live read said -1).
- The XP rule for `ManageWorkOrders` and the identity of the validating unit.
- Live plant/barrel/labor state, stone-use settings, and the stored values of the 2026-10-07 replacement
  orders (all need the VMs, which were unreachable).
- Whether workshop-pinned orders bypass general-order limits.
- The Gamepur guide and the DF bug tracker could not be fetched this session (403 and connection refused);
  their content was not used.
- Steam threads were read through a summarising fetcher, so wording is paraphrase.
