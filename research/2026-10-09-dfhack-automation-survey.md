# DFHack automation survey: what else are we missing? (2026-10-09)

Researcher, read-only. Sources: DFHack 53.16-r1.1 as installed on VM 103 (its own docs under `hack/docs`, its Lua
under `hack/scripts` and `hack/lua`, its control-panel registry), the live fort (paused, nothing changed), the world
save files on VM 103, DFHack C++ source at tag `53.16-r1` (fetched from upstream for `suspendmanager.cpp` and
`seedwatch.cpp`), and this repo's register, failure catalogue and research.

Confidence tags: **[live]** read from the running fort or its saves today; **[install]** read from the installed docs
or scripts; **[upstream]** read from DFHack source at the install's tag; **[repo]** read from this repo;
**[inferred]** my reasoning, not shown by a source.

## Answer up front

1. **The biggest "missing" items are not new tools. They are two state problems.**
   - **`ban-cooking all` is no longer in effect on Uniboslan [live].** The kitchen exclusion list holds exactly 110
     entries, all SEEDS, which is the embark baseline the register recorded before the ban (110 before, 1279 after,
     2026-09-18). The ban was almost certainly wiped by the 2026-09-19 rollback to a 2026-09-16 save [inferred; the
     register names the zone and farm plot as lost, not the ban, but the dates fit]. `memory/dfhack-environment.md`
     still says "Uniboslan has never run it", which is also stale against the register. Latent today (no Kitchen
     workshop exists) but live the moment one is built.
   - **Enabled state lives in the world save, and no save contains today's `suspendmanager` enable [live].** The three
     autosaves all store `suspendmanager/config` as enabled=0. A reload before the next save silently turns it off.
     Same exposure for anything else enabled by hand.
2. **`suspendmanager` (now on) will release our own deliberate suspensions [upstream].** Its cycle unsuspends every
   suspended `ConstructBuilding` job it has no reason for ("suspended for no reason"), including one a tool or a human
   suspended on purpose. This closes the register's open question (2026-10-09): the catalogue's hand-suspended wall
   beside unmined ore is NOT safe. Nothing in our design may use job suspension as a "hold".
3. **Most of the rest of DFHack's automation either needs buildings the fort does not have, or collides with a tool an
   agent already owns.** Four real conflicts: `autofarm` vs `farm.setcrop`, `autofish` vs `labor.set-labor`,
   `orders-sort` vs `orders.reorder`, `seedwatch` vs `ban-cooking` (both write the kitchen). Four items need the
   user's ruling rather than an engineering call: `prioritize`, `work-now`, `timestream`, `pop-control`.
4. **DFHack's own control panel recommends no automation by default.** In `registry.lua` the only `default=true`
   entries are bugfixes (the `fix/*` repeats, `preserve-tombs`, `fix/protect-nicks`, and tweaks). Every automation
   entry is opt-in, and `autolabor` is commented out of the panel with "hide until it works better" [install]. We run
   autolabor anyway (register 2026-09-11), so that choice is ours, not DFHack's recommendation.

### Ranked recommendations

| Rank | Item | Recommendation | Why |
|---|---|---|---|
| 1 | Persistence of enabled state | **Do now:** quicksave after any enable; put the intended set in `onMapLoad.init` | Silent revert already happened once to a kitchen ban; suspendmanager is exposed today |
| 2 | `ban-cooking all` | **Enable now:** run once, then weekly `repeat` | Seed and drink protection lost; one command; no agent owns the kitchen |
| 3 | `suspendmanager` | **Keep on;** tell agents it will undo suspensions | Confirmed by source, see above |
| 4 | `prioritize` (narrow: `ManageWorkOrders`, medical, food hauling) | **Needs the user's ruling,** then enable with config | Directly targets "validated orders never run" |
| 5 | `autofarm` vs `farm.setcrop` | **Design decision:** one writer, autofarm is the better engine at 3+ plots | Seasonal rotation is where an LLM loop is weakest |
| 6 | `autoslab` | **Enable now** | Event-driven, near-free, closes the ghost gap |
| 7 | `autochop` | **Leave to an agent** until a tree-farm burrow exists | Wood is short (13 logs), but unbounded felling raises agitation |
| 8 | `autobutcher` | **Enable with config** once a Butcher's Shop exists | 15 cats |
| 9 | `tailor` or `autoclothing` | **Later,** needs Clothier and Loom | Clothing wear is 1 level per 10 years, low value now |
| 10 | The rest | see the table | |

## 1. Persistence across a save reload (asked explicitly)

**How it works [upstream + live, both confirmed].**
- Each plugin keeps a persistent entry `<name>/config` inside the world save, in `dfhack-entity-*.dat` in the save
  folder. For `suspendmanager`, `plugin_enable` calls `config.set_bool(CONFIG_IS_ENABLED, ...)` and
  `plugin_load_site_data` restores it on load (`suspendmanager.cpp` lines 804 and 839, tag `53.16-r1`).
- I read that entry in all three autosaves on VM 103. Pattern across plugins matches the live `enable` list:
  `autolabor/config = [1]` (on), `preserve-tombs/config = [1]` (on), `preserve-rooms/config = [1,1]` (on),
  `seedwatch/config = [0]`, `tailor/config = [0,...]`, `autochop/config = [0,...]` (all off),
  `suspendmanager/config = [0,1]` (off, prevent-blocking on). Slot 0 is the enabled bit.
- `autolabor`'s own doc states it "stays enabled until you explicitly disable it, even if you save and reload", and
  the register (2026-09-11) verified it with a real quicksave.

**What this means for us.**
- The newest save (2026-10-08 03:27) predates today's `enable suspendmanager`. **Until a save is written after the
  enable, a reload loses it.** The conductor's quicksave and the 7-day `overseer-autosave` repeat will fix this
  eventually; a manual quicksave fixes it now. [live + upstream]
- **The control panel's autostart does not help this fort.** `control-panel` stores `autostart_done = true` in the
  save's site data [live]; `apply_fort_loaded_config` only applies autostart when that flag is absent
  (`control-panel.lua` lines 36-39 [install]). Autostart changes only affect NEW forts. The legacy
  `dfhack.control-panel-*.init` files on VM 103 contain only the "no longer used" banner.
- **Repeat-style items persist separately:** `control-panel-repeats` in the save records which `fix/*` repeats are on.
  Live `repeat --list` shows ten `control-panel/fix/*` repeats running plus our three (`overseer-sampler`,
  `overseer-tripwire`, `overseer-autosave`). [live]
- **The robust layer is an init file.** Our clock, sampler and autosave already go through
  `dfhack-config/init/onMapLoad.init`, which re-runs on every map load, including a load of an older save, so it
  survives rollbacks. Putting `enable suspendmanager` and a weekly `ban-cooking all` repeat there would have survived
  the 2026-09-19 rollback. Caveat: that file is edited on the host and is not shipped by `scripts/deploy.py`
  (grep of `scripts/` finds no deploy of it) [repo], so it is exactly the "drift" class the doc-audit exists for.
  Options: have deploy manage it, or accept one more host-only file and record it in `docs/STATE.md`.
- **Plugins with no saved enabled bit:** `burrow`, `logistics` and `overlay` are on with no matching enabled flag in
  their save entries (`logistics/config = [0]` is not an enabled flag, since logistics is on). They come on at every
  load by themselves; I did not establish why for each. [live; cause not verified]

## 2. What is already on (so it is not re-recommended)

`autolabor` (register 2026-09-11), `buildingplan`, `burrow`, `logistics`, `overlay`, `preserve-rooms`,
`preserve-tombs`, `fix/protect-nicks`, ten `fix/*` repeats (`dead-units`, `dry-buckets`, `empty-wheelbarrows`,
`engravings`, `general-strike`, `noexert-exhaustion`, `ownership`, `stuck-instruments`, `stuck-squad`,
`stuck-worship`), and eight tweaks (`flask-contents`, `named-codices`, `reaction-gloves`, `adamantine-cloth-wear`,
`eggs-fertile`, `craft-age-wear`, `fast-heat`, `partial-items`) [live]. `suspendmanager` joined today.

## 3. Live fort facts that drive the recommendations [live, fort paused, year 32]

- 24 citizens (4 children), 25 fort-controlled animals of which **15 are cats**, 3 dogs, 2 yaks.
- Workshops: **Carpenters, Masons, Mechanics, Still only.** No Kitchen, Butcher's Shop, Farmer's Workshop, Craftsdwarf,
  Loom, Clothier. One farm plot. One Well. One manager order (an 8-count CustomReaction with conditions).
- Jobs: 15 total, 1 suspended (a buildingplan-held Bed: `buildingplan` reports "waiting for 1 Bed").
- Stock units: 27 drink, 285 seeds, 17 wood (13 accessible logs per `autochop status`), 951 thread, 5 cloth.
  Clothing need per `autoclothing`: 24 dwarves lack headwear, 2 lack body, shoes, hands, legs.
- `combine all --dry-run`: 24 DRINK in 7 stacks into 2, 100 PLANT_GROWTH stacks into 24, 89 PLANT stacks into 23.
- Kitchen exclusions: 110, all SEEDS (see above).

## 4. Candidate table

Armok column: DFHack tag from `ls armok` on this install [live], then my read against the project rule (a power the
player lacks, or information the game hides). "Conflict" is against what our agents own: Quartermaster (orders,
stock, crops, stockpile config, labor quota), Architect (rooms, digging, zones, trees), Overseer (sole writer),
Logistics later (stockpiles and links). Recommendation vocabulary: ENABLE NOW, ENABLE WITH CONFIG, LEAVE TO AN AGENT,
NEEDS RULING, NEVER.

### 4a. Job and building flow

| Tool | What it does (own help) | Armok | Conflict | Would have prevented | Recommendation |
|---|---|---|---|---|---|
| `suspendmanager` (on) | Unsuspends construction jobs suspended for inaccessible materials, items in the way, scared workers; suspends constructions that would block another construction, collapse, sit on water, or sit on smoothing/engraving/track designations. Only `ConstructBuilding` jobs [upstream]. | No tag; no hidden info | **Undoes deliberate suspensions** (line 713 of upstream cycle). `construction.audit` can suspend; the catalogue's hand-suspended wall beside ore is released. Does not touch `buildingplan` jobs (kept suspended while waiting for items, reason BUILDINGPLAN, external) | Part of: "Chair buildingplan-suspended waiting" (it does not supply the missing Bed; that is an order problem); "Overseer deferred four bedroom proposals on 'no unsuspend tool'" (it supplies the unsuspend). Not the "Still unsuspended by hand ran to failure" class: it could repeat that [inferred; watch for the red X repeat-suspend marker] | **Keep on.** Tell agents; add a gotcha |
| `prioritize` | Sets `job.flags.do_now` on whole job types as jobs are created (`prioritize.lua`: `job.flags.do_now = true`). Default list: hauling, medical, noble tasks incl. `ManageWorkOrders`, `PullLever`, etc. Refuses dig and smooth types on its own. Persisted as site data. | No tag. **Grey:** vanilla offers per-job "do now" on workshop tasks but not on hauling or `ManageWorkOrders`; it grants no resource or information | Register 2026-09-30: "do now reserved for genuine problems", `prioritize` deferred with a measurement. Does not collide with a tool (we use designation priority and order sequence) | "Validated manager orders never run" (`research/2026-10-08-validated-orders-never-run.md`; DFHack's authors list `ManageWorkOrders` as starvable) | **NEEDS RULING.** If allowed, narrow set only: `ManageWorkOrders`, `DressWound`/`Suture`/`GiveFood`/`GiveWater`, `StoreItemInStockpile` with `--haul-labor Food`. Never the full default list |
| `work-now` | Pokes dwarves to pick a new job sooner after finishing one. Plugin, no options. | No tag. **Grey:** shortens an engine idle timer, a cousin of `fastdwarf` | None | Nothing in the catalogue. 19 of 24 citizens have no job right now, but jobs are scarce (15), so idleness is not the bottleneck | **NEEDS RULING / not yet.** The 2026-09-21 classification already asks this. Measure with `stuckjobs` idle ticks first |
| `timestream` | Decrements action counters faster per tick and advances the calendar proportionally, so the sim does more per frame. | No tag. **Grey:** alters the sim step, not a player action | Skews anything counting ticks against wall time (sampler, tripwire windows), liquids and armies do not scale | Nothing. Fort runs at the 100 FPS cap with 24 citizens | **LEAVE OFF** until FPS drops, same posture as the `clean` ruling. `timestream` is on the open question list |
| `infinite-sky` | Allocates extra sky z-levels as you build upward. Doc warns of cave-ins. | No tag. **Likely a power:** adds map height | Architect territory | None | **NEVER** (add to rulings if the user agrees) |
| `fastdwarf` | Citizens move and work instantly, optional teleport. | **armok** | n/a | n/a | **NEVER** (already banned in classification) |
| `buildingplan` (on) | Plans buildings without materials; attaches items later | No | Wrapped by our building tools | n/a | Keep. Settings are per fort and persisted |
| `burrow` (on) | Burrow edit and auto-expand for names ending `+` | No | Overseer owns burrows if used | n/a | Keep |

### 4b. Food, farms, kitchen

| Tool | What it does | Armok | Conflict | Would have prevented | Recommendation |
|---|---|---|---|---|---|
| `ban-cooking all` | Writes `plotinfo.kitchen` exclusions for booze, seeds, brewables, honey, tallow, oil, milk, including types not yet in stock. | No | None; no agent writes the kitchen. **Conflicts with `seedwatch`** (below) | Seed cooking (doctrine `never-cook-seed-items`, `cooking-plants-costs-seeds`); the 2026-09-19 starvation was a seeds-and-food crisis. Lost in rollback [live] | **ENABLE NOW:** run once, then a weekly repeat to catch new item types. Also fix the stale memory line |
| `seedwatch` | Per-plant seed targets (default 30); protects plants and seeds from cooking below target, allows again above target+20. Source calls `Kitchen::denyPlantSeedCookery` and `allowPlantSeedCookery` [upstream] | No | **Fights `ban-cooking`**: above target it re-allows cooking that the ban blocked | Same class as above | **NEVER alongside ban-cooking.** `ban-cooking` is the simpler, stateless choice |
| `autofarm` | Periodically assigns crops to all plots by stock vs per-crop threshold (default 50). | No | **Direct:** rewrites what `farm.setcrop` (QM, Architect, Overseer) sets, every cycle. One plot exists today | Starvation of 2026-09-19 had no farm plot at all (rollback), so not a direct fit. Real value is seasonal rotation, which a once-per-cycle LLM cannot do between wakes | **DESIGN DECISION.** At 1 plot keep `farm.setcrop`. At 3+ plots, make autofarm the engine and give agents a threshold tool; remove `farm.setcrop` from allowlists at the same time (single writer) |
| `autofish` | Toggles the fishing labor on and off by fish stock (default max 100, min 75). | No | **Direct with `labor.set-labor`** (FISH labor). autolabor shows FISH as `disabled` (taken out of its management, likely by our labor fix) | The `set_labor` vs autolabor race class (catalogue A17,A18,A20) | **LEAVE TO AN AGENT** for now; later candidate for the same "agent sets thresholds, tool executes" pattern |
| `autochop` | Designates trees to hold 160 to 200 logs; can restrict to a burrow and keep burrows clear. Persisted. | No | Overlaps `trees.fell` (Architect, Overseer). Duplicate designations are harmless; unbounded felling is not: surface agitation rises with trees felled | Wood shortage: 13 accessible logs, barrels need logs (register 2026-09-18). 1594 accessible trees | **LEAVE TO AN AGENT** until a tree-farm burrow exists, then ENABLE WITH CONFIG (`autochop chop <burrow>`, target ~60) |
| `autobutcher` | Slaughters livestock above per-race targets; protects named, war/hunt-trained, pregnant, caged-in-zone animals. | No | None (no agent owns animals) | 15 cats, no catalogue incident. Needs a Butcher's Shop to execute | **ENABLE WITH CONFIG** later: `autobutcher noautowatch` first (default autowatch adds every race at 4/2/4/2), then `autobutcher target <fk> <mk> <fa> <ma> CAT` |
| `husbandry`, `autonestbox`, `nestboxes`, `pet-uncapper`, `dwarfvet` | Milk/shear jobs; nestbox pasturing; egg protection; pet population; animal treatment at hospital | No | None | None | **LEAVE OFF:** no Farmer's Workshop, nestbox, hospital known, or egg layers of note. Revisit with a livestock policy |
| `combine` | Merges partial stacks in stockpiles (drink, food, meat, plant, seeds, fat, fish, ammo, powders, parts) | No | Merging deletes item entities, so a future "exact item" binding on food or drink pools could lose ids. Building materials are not in its type list | FPS and haul-job count only | **LEAVE OFF** now (dry run shows modest gain). If used, `--types` restricted and weekly, after the item-binding design is settled |
| `cleanowned` | Confiscates and dumps rotten or scattered owned items. | No | Overlaps `tailor` confiscation | None; dry run printed nothing | **LEAVE OFF** |

### 4c. Clothing, orders, ghosts

| Tool | What it does | Armok | Conflict | Would have prevented | Recommendation |
|---|---|---|---|---|---|
| `tailor` | Daily: confiscates tattered clothes, queues manager orders for replacements from on-hand materials | No | Writes the manager order table QM owns; its orders are not tagged as DFHack's, so `orders.check-duplicate` sees them as foreign | None. Wear is 1 level per 10 years in 53.16 (register 2026-09-18) | **LATER, ENABLE WITH CONFIG** (`tailor confiscate false`) once a Clothier and Loom exist. Without them the orders are the "queued but never runs" trap |
| `autoclothing` | Per-citizen clothing quotas as manager orders | No | Same as tailor | Same | Prefer it over `tailor` when you want explicit intent. Not now |
| `autoslab` | Queues a slab-engraving order per ghost lacking a memorial | No | Writes one order per ghost; negligible | Ghost saga: "no tool could queue EngraveSlab", coffin built outside any zone (catalogue E26,E31,C20,E32) | **ENABLE NOW.** Needs slabs on hand; `orders import library/rockstock` supplies a slab stock order |
| `orders-sort` (control-panel repeat of `orders sort`) | Re-sorts all manager orders daily: one-time first, then yearly...daily | No | **Direct with `orders.reorder`**: the 2026-09-30 decision makes order sequence a priority lever, and this would rewrite it daily | None | **NEVER** |
| `orders-reevaluate` (monthly `orders recheck`) | Clears active and validated on orders with item conditions | No | Overlaps `orders.recheck` (already in QM and Architect allowlists). Forcing re-validation depends on the Manager doing `ManageWorkOrders` | The "validated but never run" class; could also create it | **LEAVE TO AN AGENT** (tool exists) |
| `orders import library/*` | Imports vetted orders (basic has 45) | No | Overlaps QM; basic's brew order needs 5 empty containers the fort lacks (register 2026-09-18) | "Standing manager order that would never run" | **LEAVE TO AN AGENT:** import individual entries as data, not whole libraries |

### 4d. Population, difficulty and interface

| Tool | What it does | Armok | Conflict | Would have prevented | Recommendation |
|---|---|---|---|---|---|
| `pop-control` | Dynamically caps migrant wave size (default 10) and max pop (200) | No. Vanilla exposes population caps | None. Doc warns the cap leaks into the next loaded fort | 2026-09-19 starvation followed a population jump [inferred, not shown] | **NEEDS RULING:** a policy dial, not a fix |
| `emigration` | Stressed dwarves can leave; `emigration nobles` | No | None | None | **NEVER** for a survival goal (user may treat as a difficulty dial) |
| `misery` | Adds a negative thought to everyone | No | None | None | **NEVER** (hardship dial) |
| `hermit` | Blocks caravans, migrants, diplomats | No | Cuts trade and labor | None | **NEVER** |
| `agitation-rebalance` | Makes surface and cavern agitation attack once per provocation, caps hidden cavern invaders. `monitor` feature shows attack chances. | No tag, but **the monitor and `status` output show hidden irritation-derived chances**: do not enable `monitor`, and do not feed `status` numbers to agents | None | Wildlife incidents (kea, 2026-09-11) were ordinary wildlife, not agitation | **LEAVE OFF;** user's difficulty call. Never `monitor` |
| `deteriorate` | Rots away corpses, parts, clothes, food | No tag. Grey: deletes items | **Conflicts with burial**: its `corpses` category includes former fort members, so an unburied dwarf could rot away and the ghost could never be laid to rest [inferred from its doc] | Nothing; it would have caused the ghost saga | **NEVER the `corpses` category.** Otherwise leave off (items: 461 REMAINS, 25 CORPSE are not an FPS problem at this size) |
| `starvingdead`, `immortal-cravings` | Undead decay; immortals eat | No | None | None | **LEAVE OFF** (no undead or immortals) |
| `autotraining`, `idle-crafting` | Military training squad fill; craft needs at marked Craftsdwarf workshops (marked through a UI overlay) | No | idle-crafting needs a Craftsdwarf workshop (none) and is UI-only to configure | Stress ("14 distracted" craft need) | **LATER:** `idle-crafting` once a Craftsdwarf exists, if a non-UI way to mark it is found |
| `spectate` | Camera follows dwarves; optional tooltips; `auto-unpause` dismisses pause events | No | **`auto-unpause` defeats the paused-fort safety**; follow mode competes with `ui.*` and screen reads | None | **LEAVE OFF.** Never enable auto-unpause |
| `hide-tutorials` | Hides first-use tutorial popups (global service) | No | None | UI-automation blockers [inferred] | **ENABLE NOW, trivial,** if popups ever appear; unverified whether any remain |
| `edgescroll` | Mouse-edge scrolling | No | n/a | None | **NEVER** (headless) |

### 4e. One-shot fixes and armok control-panel entries

| Item | Verdict |
|---|---|
| `fix/*` bugfix repeats | Already running (ten). Nothing to add. |
| `fix/wildlife` | Not default. Moves stuck wildlife off the map so new waves enter. Reduces nothing we need. **LEAVE OFF.** |
| `fix/blood-del` | One-shot, run via autostart in new forts; harmless if run once. **Low value.** |
| `unsuspend` (suspendmanager command) | One-shot "release all" with `-f`: **never as a blanket**, same reason as above. |
| `aquifer drain`, `light-aquifers-only` | **armok** (alters the world). **NEVER.** |
| `gui/settings-manager load-standing-orders` | Loads vanilla standing orders from a saved file. **Not surveyed** (UI-saved input). |

## 5. Conflict map (single-writer view)

- **Two writers on one thing, a decision is needed:** crops (`autofarm` vs `farm.setcrop`), fishing labor (`autofish`
  vs `labor.set-labor`), order sequence (`orders-sort` vs `orders.reorder`), kitchen (`seedwatch` vs `ban-cooking`).
- **A silent undo of our own intent:** `suspendmanager` vs any deliberate job suspension.
- **Orders table has a second author if `tailor`, `autoclothing` or `autoslab` are on.** Their orders look like any
  other order to `orders.list` and `orders.check-duplicate`. If enabled, the QM gotcha should say so, or
  `orders.list` should mark DFHack-owned orders.
- **No conflict, good fits for "set intent, let the game execute":** `ban-cooking`, `autoslab`, `autobutcher` (after
  setup), `autochop` (burrow-limited), `autofarm` (once agents set thresholds).

## 6. Not verified, and why

- **`prioritize`'s actual effect on this install** was read from its Lua (`do_now = true`), not run. Whether the
  vanilla UI exposes "do now" for those job types is from memory of the game; the 2026-09-30 register row says the
  same thing is unconfirmed.
- **How `suspendmanager` treats a job suspended by a human or our tool** is read from upstream source at tag
  `53.16-r1`. The install is `53.16-r1.1`; I did not diff the two. A live negative control (suspend one harmless
  construction with the fort paused and unpaused briefly, watch for release) was not run: I may not change state.
- **Why `ban-cooking` was lost** is inferred from dates (ban 2026-09-18, rollback to the 2026-09-16 save on
  2026-09-19). The 110 count and all-SEEDS composition are directly read.
- **`work-now`, `timestream`, `pop-control`, `deteriorate`**: only their docs were read; I did not enable or measure
  any. Their effect on tick-counting tools is reasoning, not a test.
- **`autofish` overlap with FISH** rests on autolabor listing FISH as `disabled`; I did not establish who disabled it.
- **Population jump before the 2026-09-19 starvation** (for `pop-control`) is not shown by any source I read.
- **`seedwatch` interaction with `ban-cooking`** is read from upstream `seedwatch.cpp` (it calls the Kitchen module's
  allow and deny functions); I did not run both together.
- **I ran more than the literal read-only allowance in the brief**, all documented as non-mutating and with the fort
  paused throughout: `<tool> status` commands, `autolabor list`, `repeat --list`, `combine all --dry-run`,
  `cleanowned ... dryrun`, a `tweak` status read, and four short print-only `dfhack-run lua` scripts (written to the
  VM's temp directory and deleted; none under DF's script paths). `agitation-rebalance status` prints
  irritation-derived attack chances (all "None"); I did not use or record them as evidence.

## 7. Suggested next steps (for the orchestrator, none done by me)

1. Quicksave now (persists `suspendmanager`), via the existing harness path.
2. User go-ahead for `ban-cooking all` plus a weekly repeat; update `memory/dfhack-environment.md` line about "never run".
3. Decide where the persistent enable set lives (`onMapLoad.init` managed by deploy, or documented host-only).
4. Add a gotcha: suspendmanager releases suspended constructions; `construction.audit` suspend is not a hold.
5. User rulings: `prioritize` (narrow set), `work-now`, `timestream`, `pop-control`.
6. Put the `autofarm` vs `farm.setcrop` and `autofish` vs `labor.set-labor` writer choice on the districting/Quartermaster agenda.
