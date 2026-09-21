# DFHack tool classification, summary

Written 2026-09-21 by a researcher agent from `docs/DFHACK-INVENTORY.md`, DFHack's own tool docs, `scripts/dfhack/TOOLS.yaml`, the role charters in `agents/*/role.md` and the repo's own notes. Data: `research/2026-09-21-dfhack-tool-classification.yaml` (443 entries, one per tool, inventory order). **Everything here is a documentation read: no tool was run, no VM or live game was touched, and nothing is presented as verified.** Where the docs were vague the entry says so.

> **Synced 2026-09-21 by the orchestrator to the user's armok rulings** (`docs/ARMOK-RULINGS.md`): 14 entries changed (`lever`, `caravan`, `diplomacy`, `justice`, `locate-ore`, `pref-adjust`, `assign-preferences`, `prospector`, `showmood`, `geld`, `cursecheck`, `lair`, `cleaners`, `clear-smoke`), each with a `RULING` note. **Counts after the sync: 63 `will`, 43 `grey`, 337 `wont`** (89 of them `armok`). The text below is the agent's original report and still says 60, 46 and 337.

## Result in one paragraph

All 443 tools are classified. **60 `will`, 46 `grey`, 337 `wont`.** Of the `wont`, 105 are `unavailable` (DFHack's own tag) and 89 are `armok` (the user's capability ruling: a power a player lacks, or information the game hides), leaving 143 that are developer tooling (55), on-screen dialogs (38), interface or cosmetic (23), adventure or embark (3) or other (24). The 60 `will` cluster in five places: work orders and labor, stockpiles and items, farming and animals, construction and digging, and DFHack housekeeping (`enable`, `disable`, `repeat`, `quicksave`, `setfps`, `fpause`, `plug`, `help`). The 46 `grey` are mostly conditional bug fixes and rule tweaks, each with a one-line question below. Ten of the 99 armok-tagged tools were judged on what they do and did not get the armok ban (see the armok section). **None of the project's own scripts that I could find calls an armok-tagged tool.**

## Coverage against the minimum bar

Why this file exists: research toward the openclaw agent design, to learn what DFHack already gives us and what we must build. For each minimum-bar need below: the DFHack tools that provide it (with the verdict in this file), whether they are enough, and where nothing exists. **Every claim rests on DFHack's tool docs and this repo's own notes; nothing was run.** "Ours" means a tool already in `scripts/dfhack/TOOLS.yaml`. Where the docs were unclear I say so.

| Need | DFHack provides | Enough? | Nothing exists / we build it |
|---|---|---|---|
| **Building workshops** | `quickfort` (will): its doc says blueprints "build buildings"; `quickfort orders` queues the manager orders for a blueprint's materials. `blueprint` (will) records a built layout. `buildingplan` (grey) places before materials exist. `build-now` is banned (instant completion). | Placement: yes, and our `workshop.build` already wraps quickfort with a kind argument. | No DFHack tool picks a site, or reports that the workshop finished. Site choice (`workshop.find`) and the per-kind blueprint are ours. |
| **Rooms and zones** | `quickfort` "marks zones" per its doc; which zone kinds it supports is in an external blueprint guide I did not have. `burial` (will) makes tomb zones over coffins. `preserve-rooms` (will) keeps assignments. `zone` (pastures, cages, animal zones) is **unavailable**. `gui/room-list` unavailable. | Partly. Tomb zones yes; the rest unclear. | Water source zone is ours (`zone.place`). Pasture, cage and meeting-area zones and bedroom or dining-room assignment: nothing found in the docs. |
| **Placing and assigning furniture** | Placing: `quickfort` (furniture is a building), `buildingplan` (grey). Ownership repair only: `fix/ownership` (will), `cleanowned` (will), `store-owned` (wont). | Placing yes; assigning no. | **Assigning a bed, chair or room to a dwarf: no tool in the 443 docs.** We would write it against the Lua API, or leave dwarves to claim furniture themselves. |
| **Assessing dwarves** (skills, needs, stress, health) | Needs: `allneeds` (will). Syndromes, age and body facts: `gui/unit-syndromes` and `gui/unit-info-viewer` (both gui-only, no command form). Cause of death: `deathcause` (will). Migration history: `list-waves` (will). Skills and labor screens: `manipulator`, `gui/manipulator`, `dwarfmonitor` are **unavailable**. Setting skills or stress is banned (`assign-skills`, `remove-stress`). | Needs only. | **Skill levels, stress values and injuries: no usable DFHack tool.** Our `labor.unit-status` already reads citizen state (idle, injured, military); anything more is ours to build on the Lua API. `probe`/`cprobe` dump a unit but need a cursor selection (wont). |
| **Growing food end to end** | Crop choice per plot: `autofarm` (will). Seed protection: `seedwatch` (will), `ban-cooking` (will). Wild gathering: `getplants` (will). Fish: `autofish` (will). Livestock and butchering: `autobutcher`, `animal-control`, `autonestbox` (will). Dairy: `autocheese`, `husbandry` (grey). Production steps (brew, cook): `workorder` and `orders` (will), needing a Manager. `growcrops` unavailable; `plant` banned. | The decision layer yes; the chain no. | Nothing checks that a plot was planted, that seeds reached it or that harvest happened. Plot building, seed assignment and stock reads are ours (`farm.*`, `stocks.*`). Every order-based step is blocked while no Manager is appointed. |
| **Wells and water** | No dedicated tool. `quickfort` can place a well building (ours: `well.build`). `fix/dry-buckets` (will) repairs stuck buckets that block wells. `flows` (will) counts leaking liquid blocks. `aquifer`, `liquids`, `source` are banned (they alter the world). `zone` is unavailable. | Mostly no. | Finding a water body, choosing a well site, the Water Source zone and confirming drinking: all ours (`zone.find/place`, `well.find/build`). |
| **Stockpile creation and configuration** | Creation: `quickfort` "places stockpiles". Accepted items: `stockpiles` (will; import, export and a library of named settings; acts on a selected stockpile unless an id is given). Automation: `logistics` (will), `combine` (will). Hauling routes: `assign-minecarts` (grey, needs routes made in the UI). `gui/quantum` gui-only. `stocks` unavailable. | Creation and settings: yes on paper. | Stockpile links (give and take) are read by ours (`stockpile.links`); whether quickfort or DFHack sets them I could not confirm from the docs. Our stockpile tools are read-only, so a write wrapper for `stockpiles import` is the missing piece. |
| **Appointing a Manager and nobles** | **Nothing.** I searched all 443 docs for appointing officials and found none. Nearby: `preserve-rooms` (keeps noble rooms when roles change hands), `fix/symbol-unstick`, `emigration` (can send nobles away), and `make-monarch` (armok, banned). | No. | **We must build Manager appointment ourselves** (Lua on the fort's positions). This is the blocker behind every manager-order tool (`orders`, `workorder`, `tailor`, `autoclothing`, `autoslab`); `df-overseer-workjob` is the current workaround for one-off jobs. |
| **Confirming a building or job completed** | Nothing reports completion. `eventful` (developer plugin, wont) is the event library our `diff` and `stuckjobs` scripts already use; its doc here only points to the Lua API docs, which I did not read. `suspendmanager` (will), `fix/general-strike` (will) and `warn-stranded` (will) repair or flag problems. `gui/notify` shows alerts to a person (gui-only). | No. | Ours: `diff.since` and `stuckjobs.find` are the existing pieces. A completion check (job or building id to done) is to be built on the event library. |
| **Controlling the game clock** | Pause: `fpause` (will). Speed: `setfps` (will; frame-rate cap), `timestream` (grey), `work-now` (grey). Scheduling: `repeat` (will). `fastdwarf` banned. | Pause yes; unpause and speed only partly. | **No documented unpause command**: the docs mention unpausing only as a UI action, or as `spectate`'s `auto-unpause` setting. Pausing and unpausing over the remote channel is not in `TOOLS.yaml` or any role allowlist (searched); the project's frame-cap reasoning is in `memory/agent-architecture-and-safety.md`. |
| **Quicksave** | `quicksave` (will): doc says it "immediately" autosaves and the game keeps the last 3 autosaves. | Yes, with a caution. | `research/2026-09-11-quicksave-silent-noop.md` (2026-09-11) found `quicksave` runs through an overlay that may act tens of seconds later, so a save should be verified by the save directory, not by the command's return. No MCP wrapper is listed in `TOOLS.yaml`. |
| **Defence** (burrows, squads, alerts) | Burrows: `burrow` (will; edits the tiles and members of an existing burrow, and auto-extends burrows named with a trailing `+`; how to create one is not in the doc). Civilian alert: `gui/civ-alert` (grey; the doc says the function is vanilla and the tool restores its UI, so a wrapper may be able to set the vanilla state directly, unverified). Training: `autotraining`, `uniform-unstick`, `fix/stuck-squad` (all grey). Repairs: `fix/loyaltycascade` (will). Access control: `filltraffic` (will). `gui/siegemanager` gui-only; `siege-engine`, `gui/choose-weapons`, `gui/clone-uniform` unavailable. | Burrows and the alert: partly. | **Creating or commanding squads, equipment and uniforms: nothing usable in the docs.** **Threat detection: nothing** (the marshal role's known blocker, `agents/marshal/role.md`); `cursecheck` and `exterminate` are banned. Our `threat.scan`, `breach.check` and `chokepoints.find` are the current pieces. |

**Reading the table.** DFHack is strongest where a decision can be made once and left running (crop choice, seed protection, butchering, labor balance, stockpile settings) and where one blueprint tool places most structures. It is weakest exactly where the minimum bar needs a closed loop: assigning furniture and offices, appointing a Manager and nobles, checking that something finished, unpausing and squad control. Those are the things we must build ourselves, and they are the same gaps the repo already knows about for the Manager and the threat signal.

## Counts

**By use verdict:** will 60, grey 46, wont 337.

**Wont by reason:** unavailable 105, armok 89, developer 55, gui-only 38, other 24, interface 19, cosmetic 4, adventure-or-embark 3.

**By read or write:** read 79, write 301, both 63.

Among the 60 `will`: read 10, write 23, both 27. Among the 46 `grey`: read 2, write 33, both 11.

**By broad category** (total, and will / grey / wont):

| Broad category | Total | will | grey | wont |
|---|---|---|---|---|
| developer | 93 | 0 | 1 | 92 |
| cheat | 72 | 0 | 0 | 72 |
| interface | 46 | 0 | 0 | 46 |
| bugfix | 33 | 12 | 16 | 5 |
| map-and-digging | 23 | 3 | 3 | 17 |
| units-and-health | 22 | 4 | 5 | 13 |
| construction | 21 | 5 | 2 | 14 |
| game-control | 19 | 8 | 1 | 10 |
| items-and-materials | 15 | 4 | 2 | 9 |
| other | 15 | 0 | 1 | 14 |
| animals | 15 | 3 | 6 | 6 |
| military-and-defence | 13 | 1 | 4 | 8 |
| work-orders | 11 | 5 | 0 | 6 |
| labor-and-jobs | 11 | 2 | 1 | 8 |
| inspection | 11 | 4 | 0 | 7 |
| plants-and-farming | 9 | 4 | 0 | 5 |
| stockpiles-and-logistics | 7 | 3 | 1 | 3 |
| food-and-drink | 5 | 2 | 1 | 2 |
| trade-and-diplomacy | 2 | 0 | 2 | 0 |

**Role appearances** (a tool can name several roles; only `will` and `grey` tools name any): overseer 102, quartermaster 31, architect 10, marshal 6, chronicler 3, consultant 3. Overseer dominates because it is the sole writer. Quartermaster (31) is all work orders, stock, food, animals and items, so it is the role whose wrapper list would grow most if it were enabled. Marshal (6), chronicler (3) and consultant (3) are thin: the marshal's entries are the civilian alert, burrows and conditional military fixes, the chronicler's are `deathcause`, `list-waves` and `exportlegends`, and the consultant's are the three documentation lookups (`help`, `ls`, `tags`).

**The `will` list:** `allneeds`, `animal-control`, `autobutcher`, `autochop`, `autoclothing`, `autofarm`, `autofish`, `autolabor`, `autonestbox`, `autoslab`, `ban-cooking`, `blueprint`, `burial`, `burrow`, `cleanowned`, `combine`, `control-panel`, `deathcause`, `dig`, `disable`, `enable`, `filltraffic`, `fix/corrupt-jobs`, `fix/dead-units`, `fix/dry-buckets`, `fix/empty-wheelbarrows`, `fix/general-strike`, `fix/loyaltycascade`, `fix/occupancy`, `fix/ownership`, `fix/stuck-worship`, `fix/stuckdoors`, `flows`, `forbid`, `fpause`, `getplants`, `help`, `item`, `lever`, `list-agreements`, `list-waves`, `logistics`, `ls`, `orders`, `plug`, `preserve-rooms`, `preserve-tombs`, `prioritize`, `quickfort`, `quicksave`, `repeat`, `seedwatch`, `setfps`, `stockpiles`, `suspendmanager`, `tags`, `tailor`, `unforbid`, `warn-stranded`, `workorder`.

## Fine-category vocabulary (63 values; `null` for unavailable tools)

Unavailable tools carry `category_fine: null` on purpose (rule 2). The count of tools using each value is in brackets. Some fine categories span two broad categories because the fine list describes the job and the broad list the domain. I first wrote about 96 fine values and merged them down to keep the vocabulary small.

- `adventure-mode` (7): tools for adventure mode only.
- `animal-automation` (5): background plugins that manage livestock and egg or milk production.
- `animal-management` (7): reading or changing individual animals or animal populations, including breeding and taming edits.
- `automation-scheduling` (4): running commands on a timer or at game start.
- `blueprint-application` (1): placing a blueprint file onto the fort.
- `blueprint-recording` (1): recording part of the fort into a blueprint file.
- `bugfix-items` (5): repairs for stuck or corrupt items.
- `bugfix-jobs-and-state` (4): repairs for stuck jobs and for bad global game state (dead-unit list, population cap).
- `bugfix-map` (5): repairs for map tiles, doors, occupancy, webs, wildlife.
- `bugfix-military` (3): repairs for squads, uniforms and military equipment.
- `bugfix-trade` (3): repairs for caravans, merchants and the civ relation behind them.
- `bugfix-units` (8): repairs for stuck or misbehaving units, ownership and room assignment.
- `building-config` (3): changing built mechanisms (levers, plates, track stops).
- `building-jobs` (4): placing buildings and managing construction jobs, including instant completion.
- `burrow-management` (2): burrows, and the civilian alert that uses them.
- `caravan-and-diplomacy` (2): trade caravans and relations with other civilizations.
- `cheat-events` (5): forcing game events or killing things.
- `cheat-liquid-and-fire` (4): creating liquids or fire.
- `cheat-spawn` (3): creating items or units from nothing.
- `cosmetic-naming` (3): names, nicknames and purely cosmetic effects.
- `dev-memory-debug` (8): memory and game-structure debugging for DFHack developers.
- `dev-modding-api` (13): Lua libraries and triggers for mod authors.
- `dev-tooling` (30): other developer helpers, monitors and examples.
- `dfhack-config` (8): enabling, disabling, loading and configuring DFHack itself.
- `dfhack-docs` (5): looking up what DFHack commands exist and how they work.
- `dfhack-shell` (8): console conveniences (aliases, window hiding, the launcher).
- `dig-designation` (3): designating digging, including instant digging.
- `embark-setup` (7): choices made before or at embark.
- `farming-automation` (2): picking crops and protecting seeds from cooking.
- `food-supply-automation` (3): keeping fish, cheese and cookable stock in balance.
- `fort-status-view` (3): read-only overview screens and lists of fort status.
- `fps-tuning` (4): frame-rate maintenance and simulation-speed compensation.
- `game-pacing` (4): pause, save, frame cap and exit.
- `game-rule-tweaks` (8): changing game rules or difficulty, including the `tweak` collection.
- `interface-config` (6): settings for interface, overlays, keys and confirmations.
- `interface-dialog` (20): on-screen dialogs (mostly the `gui/` front ends to other tools).
- `interface-tweak` (11): cosmetic or convenience changes to the game screens, and map notes.
- `item-bulk-ops` (3): filtering items and applying a flag or action (forbid, dump, melt).
- `item-cleanup` (6): tidying items, containers and stockpile stacks.
- `item-editing` (6): editing or teleporting items (mostly armok).
- `item-inspection` (2): looking at item properties.
- `job-priority` (2): changing how quickly jobs are picked up.
- `labor-automation` (1): assigning labors automatically.
- `legends-worldinfo` (2): world history (legends) export and viewing.
- `map-cleanup` (4): removing smoke, webs, spatter and fire from the map.
- `map-editing` (19): changing map terrain, liquids, discovery flags, plants or weather (mostly armok).
- `map-inspection` (3): reading map state without showing a map to a model (counts, biome and render views).
- `pathing-reachability` (2): which tiles or citizens can reach which.
- `plant-gathering` (2): designating trees to fell and wild plants to gather.
- `raw-data-inspection` (2): low-level dumps of tile, building, unit or raw data.
- `recipes-and-mods` (2): civ recipes and mod support.
- `resource-survey` (2): finding ores and summarising map resources.
- `squad-management` (2): squads, training, uniforms and siege engines.
- `stockpile-automation` (2): automatic marking and routing of items between stockpiles and hauling routes.
- `stockpile-config` (2): which items a stockpile accepts, including quantum stockpiles.
- `tomb-zones` (2): tomb zones and burial.
- `traffic-designation` (1): setting pathing cost (traffic) on tiles.
- `unit-editing` (31): changing a unit's attributes, skills, mind, gear or status (mostly armok).
- `unit-history` (2): reading how units arrived or died.
- `unit-inspection` (6): reading facts about units.
- `unit-needs-mood` (4): unit needs, thoughts and stress.
- `work-order-automation` (3): background tools that generate manager orders.
- `work-order-manual` (3): creating and managing manager orders by hand.

Broad category `other` (15 tools) holds tools that fit nothing else: adventure-mode stubs, cosmetic naming, the legends export, embark helpers and `emigration`. No new broad category was needed.

## Grey list (46), with each question

- `add-recipe` (overseer, quartermaster): Is granting recipes the civ did not roll a legitimate fix or the same kind of rule change as an armok tool?
- `agitation-rebalance` (overseer): Is softening vanilla agitation an acceptable stability fix or an unwanted change to the game's challenge?
- `assign-minecarts` (overseer, quartermaster): Does any headless path create hauling routes, or does this tool have nothing to act on?
- `autocheese` (overseer, quartermaster): Does it work when no Manager is appointed, and is a dairy line in scope before the fort is stable?
- `autotraining` (overseer, marshal): Are training squads part of the current plan, given no military tools exist yet?
- `buildingplan` (overseer, architect): Does the project need placement decoupled from material availability, and can that be driven headless (quickfort blueprints can use it) rather than through the overlay?
- `caravan` (overseer, quartermaster): Would a wrapper expose only `list` and `unload`, leaving `extend`, `happy` and `leave` (powers a player lacks) out?
- `cleanconst` (overseer): Is frame-rate maintenance on the tool list, and who decides when it is worth running?
- `deteriorate` (overseer): Is deliberately deleting items for performance acceptable, and would it undercut stock counts the tools rely on?
- `diplomacy` (overseer, quartermaster): Would a wrapper expose only the no-argument report, leaving relationship changes out?
- `dwarfvet` (overseer): Is animal treatment wanted before the fort has valuable livestock and a working hospital?
- `exportlegends` (chronicler): Would the chronicler use the exported legends file, and can legends mode be entered headless?
- `fix/archery-practice` (overseer): Is it worth wiring for a bug the doc says the game fixed?
- `fix/blood-del` (overseer): Does the fort trade yet, so that caravan manifests matter?
- `fix/civil-war` (overseer): Is this a fix to keep in reserve for when caravans stop arriving, or noise?
- `fix/codex-pages` (overseer): Is any written-works issue plausible for this fort, or is this cosmetic?
- `fix/drop-webs` (overseer): Is floating-web cleanup worth a tool before it has been seen?
- `fix/engravings` (overseer): Is engraving in scope yet?
- `fix/noexert-exhaustion` (overseer): Would the fort ever hold such units?
- `fix/population-cap` (overseer): Does the project set a population cap?
- `fix/retrieve-units` (overseer, marshal): Is forcing stuck arrivals in safe for an unattended fort?
- `fix/stable-temp` (overseer): Is frame-rate maintenance in scope, and who decides when it is worth running?
- `fix/stuck-instruments` (overseer): Does the fort have performances yet?
- `fix/stuck-merchants` (overseer): Does the fort trade yet?
- `fix/stuck-squad` (overseer, marshal): Are squads sent on missions at all?
- `fix/wildlife` (overseer): Is wildlife-wave maintenance worth wiring before hunting or trapping matters?
- `geld` (overseer, quartermaster): Does instant gelding by script count as an ordinary action or as skipping a cost, given animal-control already marks animals for gelding the ordinary way?
- `gui/civ-alert` (overseer, marshal): Would the marshal want a civilian-alert action, and would a wrapper have to reimplement the script's logic because there is no command mode?
- `husbandry` (overseer, quartermaster): Is a wool and milk economy in scope, and does it work with no Manager since it creates jobs directly?
- `idle-crafting` (overseer): Can workshops be marked recreational by command, or only by clicking the workshop's toggle?
- `infinite-sky` (overseer): Is building above the map's top level ever needed, and is the cave-in risk acceptable?
- `justice` (overseer): Does any role need the convict list, with `pardon` left out of the wrapper?
- `locate-ore` (overseer, architect): Can a wrapper be limited to discovered veins only, with `--all` excluded?
- `nestboxes` (overseer): Does the fort keep egg-laying breeders?
- `pet-uncapper` (overseer): Does the fort want livestock breeding beyond vanilla's population limits, given the game's own limit is a design choice?
- `pop-control` (overseer): Should the fort limit migrant waves, or take all migrants?
- `pref-adjust` (overseer, quartermaster): Do the roles need preference data, with the change commands left out?
- `prospector` (overseer, architect): Can a wrapper be limited to the visible-only default, and does the visible scan still add anything over our overview and diggable tools?
- `region-pops` (overseer): Should the read-only list be allowed while the change commands are treated like armok tools?
- `showmood` (overseer): Does the game already show a player every item the active strange mood needs, so this repeats visible information?
- `starvingdead` (overseer): Does the fort face undead, and is an enable-once rule tweak acceptable?
- `suspend` (overseer): Is a blunt suspend-all ever wanted when suspendmanager exists?
- `timestream` (overseer): Does the project want frame-rate compensation, given the sampler and cycle timing count game ticks?
- `tweak` (overseer): Which individual tweaks, if any, does the project want on, and who decides?
- `uniform-unstick` (overseer, marshal): Is there a military yet?
- `work-now` (overseer): Is nudging idle dwarves a legitimate throughput fix or a rule change like fastdwarf?

Patterns: 15 are conditional bug fixes (14 `fix/*` including `fix/stable-temp`, and `uniform-unstick`) that matter only once a feature (trade, military, performances, engraving) is in use; `tweak` is a collection where each named tweak is its own choice; about 8 are rule or difficulty changes (`agitation-rebalance`, `pet-uncapper`, `pop-control`, `starvingdead`, `work-now`, `add-recipe`, `region-pops`, `infinite-sky`); 4 are frame-rate tools (`cleanconst`, `deteriorate`, `fix/stable-temp`, `timestream`) that share one question, whether the project wants performance maintenance and who triggers it; 8 are armok-tagged tools whose read form is ordinary and whose tag is coarse (`caravan`, `diplomacy`, `geld`, `justice`, `locate-ore`, `pref-adjust`, `prospector`, `showmood`); and a few are real design questions (`buildingplan`, `gui/civ-alert`, `assign-minecarts`, `exportlegends`). `autocheese` and `husbandry` create jobs directly and might sidestep the missing Manager: unverified.

## Armok-tagged tools under the capability rule

**The rule as corrected by the user (2026-09-21):** the ban is on the capability, not the tag. Banned: powers a player lacks (heal, teleport, spawn, skip costs, alter the world) and information the game hides. Reading something a player can already see is fine however it is implemented. I therefore judged each of the 99 armok-tagged tools on what it does. **89 stay `wont` with `wont_reason: armok`** (the tag fits: each grants a power or reveals hidden information, and its `use_reason` says which). **10 do not**, so the tag points at them wrongly or only partly:

- `caravan` (grey): Would a wrapper expose only `list` and `unload`, leaving `extend`, `happy` and `leave` (powers a player lacks) out?
- `diplomacy` (grey): Would a wrapper expose only the no-argument report, leaving relationship changes out?
- `geld` (grey): Does instant gelding by script count as an ordinary action or as skipping a cost, given animal-control already marks animals for gelding the ordinary way?
- `justice` (grey): Does any role need the convict list, with `pardon` left out of the wrapper?
- `lever` (will): the tag is coarse: listing levers and queueing a pull is what a player does; only `--instant` is a power, so a wrapper must not expose it.
- `locate-ore` (grey): Can a wrapper be limited to discovered veins only, with `--all` excluded?
- `machine-toggle` (wont, gui-only): an overlay for pressure plates and gear assemblies after building; gui-only, with a mild extra power (settings the normal screen does not allow).
- `pref-adjust` (grey): Do the roles need preference data, with the change commands left out?
- `prospector` (grey): Can a wrapper be limited to the visible-only default, and does the visible scan still add anything over our overview and diggable tools?
- `showmood` (grey): Does the game already show a player every item the active strange mood needs, so this repeats visible information?

Each has `armok: true` and a note saying why the tag is coarse for it. The one clean `will` is `lever`: listing levers and queueing a dwarf to pull one is what a player does, and only `--instant` is a power, so a wrapper must not expose that option. The eight `grey` need a decision about which sub-commands a wrapper may expose (a read-only subset in each case). `machine-toggle` is `wont` for `gui-only` (it is an overlay), not for `armok`.

**Tools that stay banned and where a fair use was considered.** `cleaners`, `clear-smoke`, `clear-webs`, `extinguish`, `build-now`, `dig-now`, `deramp` and `autodump` stay banned because they do instantly what a player pays labor or time for (frame-rate cleanup is at most a harness job, which is the user's call); `full-heal`, `tame`, `ungeld`, `weather`, `regrass`, `lair`, `force` and `migrants-now` grant powers a player lacks; `cursecheck`, `feature`, `aquifer` and `gui/gm-editor` also touch hidden information (a cursed creature's true identity, undiscovered features, unrevealed tiles, any game data). `colonies` and `assign-preferences` stay banned because their documented main function is editing, though their read forms might be ordinary. About 9 of the banned tools reveal hidden information (`cursecheck`, `feature`, `gui/adv-finder`, `gui/gm-editor`, `gui/reveal`, `reveal-adv-map`, `reveal-hidden-sites`, `reveal-hidden-units`, `reveal`). The rest grant powers.

**Our own scripts and armok tools: none found.** I searched every `scripts/dfhack/df-overseer-*.lua`, `scripts/*.py`, `dfmcp/*.py` and `scripts/guest-capture/` for each of the 99 armok tool names used as a command, a `reqscript` target, a `dfhack-run` argument or an `enable`. There were three text hits and none is a call (`aquifer` as a substring of a tile-flag name in `df-overseer-ui.lua`, and `force` as an installer option name, twice). The DFHack commands our scripts actually run are `quickfort` and `autolabor`; they also load the `workorder` and `warn-stranded` scripts and the `eventful` plugin as libraries, and the installer runs `quicksave` and `enable spectate`, and the sampler registers through `repeat`. None of these is armok-tagged. Limits of the check: it looks for command use, not for our Lua reading the same game state a tool would (our scripts use the Lua API directly, which the armok tag does not govern); and `docs/DFHACK-INVENTORY.md` lists `df-overseer-embark` among our scripts but no such file exists under `scripts/dfhack/` in the repo, so I could not check it.

## Tools that overlap ours

Tool names are from `scripts/dfhack/TOOLS.yaml` (the `sampler` row is a script, not a listed command).

| DFHack tool | Verdict | Our tool | Relationship |
|---|---|---|---|
| `autochop` | will | `trees.fell` | complement |
| `autoclothing` | will | `orders.create` | complement |
| `autofarm` | will | `farm.set-crop` | complement |
| `autofish` | will | `labor.set-labor` | complement |
| `autolabor` | will | `labor.set-labor` | complement |
| `ban-cooking` | will | `stocks.seeds` | complement |
| `blueprint` | will | `landmarks.build` | complement |
| `buildingplan` | grey | `workshop.build` | complement |
| `burial` | will | `zone.place` | complement |
| `burrow` | will | `landmarks.list` | complement |
| `dig` | will | `diggable.dig` | complement |
| `fix/general-strike` | will | `stuckjobs.find` | complement |
| `forbid` | will | `stocks.availability` | complement |
| `getplants` | will | `trees.fell` | complement |
| `gui/design` | wont | `diggable.dig` | complement |
| `gui/dfstatus` | wont | `overview.get` | complement |
| `gui/pathable` | wont | `connectivity.check` | replacement |
| `gui/quickfort` | wont | `workshop.build` | wraps quickfort |
| `gui/unit-info-viewer` | wont | `labor.unit-status` | complement |
| `item` | will | `stocks.availability` | complement |
| `logistics` | will | `stockpile.list` | complement |
| `orders` | will | `orders.list` | complement |
| `pathable` | wont | `connectivity.check` | replacement |
| `prioritize` | will | `stuckjobs.find` | complement |
| `quickfort` | will | `openarea.build` | wraps it |
| `repeat` | will | `sampler` | wraps it |
| `seedwatch` | will | `stocks.seeds` | complement |
| `stockpiles` | will | `stockpile.list` | complement |
| `stocks` | wont | `stocks.food-drink` | replacement |
| `suspendmanager` | will | `stuckjobs.find` | complement |
| `tailor` | will | `orders.create` | complement |
| `unforbid` | will | `stocks.availability` | complement |
| `warn-stranded` | will | `connectivity.report` | wraps it |
| `workorder` | will | `orders.create` | wraps it |
| `zone` | wont | `zone.place` | replacement |

Reading the table: **wraps** means our tool calls that DFHack tool (`quickfort`, `workorder`, `warn-stranded`, and the sampler through `repeat`); **complement** means the DFHack tool does something adjacent that ours does not (mostly automation or bulk writes beside our one-shot reads); **replacement** means ours does the job of a DFHack tool that is unavailable or screen-only (`zone`, `stocks`, `gui/pathable`, `pathable`). No DFHack tool was found that fully replaces one of our working tools. Gaps our tools do not cover and a DFHack tool does: mining by vein or ore (`dig`), stockpile settings (`stockpiles`; our stockpile tools are read-only), bulk item actions (`item`, `forbid`, `unforbid`), and a general blueprint apply (`quickfort`, which our build tools each call in a different fixed shape).

Generalisability notes (rule 9), only where the docs show them: `quickfort` takes a blueprint (the general form of our build tools); `workorder` takes a job type; `item` takes filters and an action; `autobutcher`, `seedwatch`, `autofarm` and `stockpiles` take a race, plant or setting name; `getplants`, `tweak` and `add-recipe` take a kind or name. Where several tools do one job for different kinds: `forbid`, `unforbid` and `item` overlap; `tailor` and `autoclothing` overlap; `seedwatch` and `ban-cooking` overlap; each `gui/*` tool duplicates a command.

## Investigator-role candidates (read-only inspection)

The handoff mentions a future investigator role. These are `wont` today but are read-only inspection tools such a role might reasonably ask for, listed together so the user can look at them at once. None was decided.

- `probe` (with `bprobe` and `cprobe`), `troubleshoot-item`, `devel/query` (generic structure search), `gui/gm-editor` (armok, read side), `gui/unit-syndromes`, `gui/unit-info-viewer`, `necronomicon`. Already `will`: `deathcause`, `list-waves`, `list-agreements`, `flows`, `warn-stranded`.
- The first group needs a UI selection or a coordinate, so a wrapper would have to take an id.

## Things I could not classify well, and why

- **UI-selection dependence.** Many tools act on 'the selected unit, item or stockpile' or the keyboard cursor (`allneeds`, `deathcause`, `probe`, `troubleshoot-item`, `stockpiles`, `logistics`, `filltraffic`, `dig`, `blueprint`, `burrow` tile edits). The docs sometimes show an id or coordinate option and sometimes do not. I marked them `will` where a wrapper could plausibly take an id, and noted it; I could not confirm any runs headless without a UI. A wrapper for a cursor-based tool also has to satisfy the project's no-raw-coordinates rule (use a landmark).
- **Manager dependence.** `autoclothing`, `tailor`, `autoslab`, `orders` and `workorder` produce manager orders, which this fort never runs without an appointed Manager (`CLAUDE.md` status). I kept them `will` and flagged it in notes rather than downgrading them, since appointing a Manager is a fort-state fact, not a tool property. `autocheese` and `husbandry` create jobs directly and might sidestep this; unverified, grey.
- **Read-or-write splits.** `rw: both` is taken from the doc's usage lines (a `status`, `list` or `--dry-run` form beside a changing form). Some `rw_detail` lists are partial where I did not open the whole usage section (for example `autolabor`). A `--dry-run` or `dryrun` form counted as a read form.
- **How much I read.** I opened roughly 150 of the 443 full docs (all `will` and `grey` candidates I was unsure of, the armok exception candidates, the `fix/*` set, several `gui/*`). The other roughly 290 were classified from DFHack's one-line summary, the tags and general knowledge of DFHack, which is the likeliest place for a wrong claim, and it is concentrated in `wont` entries (developer, unavailable, most `gui/*`, most `modtools/*`). Descriptions of unavailable tools rest on the one-line summary and say so. **Disclosure:** while checking the research directory I opened the first 2,500 characters of `research/2026-09-21-armok-review.md` (its verdict table) before the instruction not to read it reached me. I had already written my armok verdicts from the docs, and I re-judged them under the corrected rule from the docs alone; I did not use that file.
- **Unavailable tags in the inventory.** `gui/workorder-details` and `gui/workshop-job` show tags in the inventory but are marked unavailable; I treated them as unavailable, as the tag rule says. `zone`, `stocks` and `workflow` are unavailable in DFHack even though the project relies on the ideas (our `zone` and `stocks` tools replace them).
- **Doc and behaviour mismatches to watch.** `kill-lua` is documented as the recovery for a stuck script but `docs/TRAPS.md` (2026-09-12) records it hanging twice against a real runaway script, so I marked it `wont`; that rests on one recorded incident, not a re-test. `fix/archery-practice` remains a tool although its own doc says the game fixed the underlying bug in 53.01. `autolabor`'s doc warns it has not been updated for DF v50.
- **`setfps`, `repeat`, `quicksave`, `fpause`.** Their `will` verdicts follow the project's own notes (`memory/dfhack-environment.md`, `memory/agent-architecture-and-safety.md`), which describe them as levers the design uses; I did not re-verify how the fort is paused today. No pause or unpause tool exists in `TOOLS.yaml` or any role allowlist (searched), which is itself worth a look.
- **Fine-category shape.** Because merges were done after the entries were written, a few fine values now cover mixed neighbours (`map-editing` holds terrain, plants and weather edits; `item-cleanup` holds `combine`). The broad category is the reliable grouping.

## What I would check next

1. **Run the read-only `will` tools once against the paused fort** (`allneeds`, `deathcause`, `flows`, `list-waves`, `list-agreements`, `warn-stranded status`, `plug`, `orders list`, `stockpiles list`, `autolabor status`) to confirm each works headless with an id rather than a UI selection. That turns documentation into evidence and is the first real filter on the wrapper list.
2. **Settle the Manager question** (appoint one, or route order generators through `workjob`): five `will` tools depend on it (`autoclothing`, `tailor`, `autoslab`, `orders`, `workorder`).
3. **Confirm the ten armok re-judgements** (`lever` will; `caravan`, `diplomacy`, `geld`, `justice`, `locate-ore`, `pref-adjust`, `prospector`, `showmood` grey; `machine-toggle` gui-only) and, for each grey one, which read-only sub-commands a wrapper may expose.
4. **Decide whether frame-rate maintenance is in scope** (one question covers `cleanconst`, `deteriorate`, `fix/stable-temp`, `timestream`), and whether `setfps` becomes a role lever.
5. **Read the full docs for the `wont` entries I only summarised** if the wrapper list is going to be built from this file; spot-check ten at random first.
6. **The four gaps** our tools do not cover and DFHack does: mining a vein or ore (`dig`, via a landmark), stockpile settings (`stockpiles`), bulk item flags (`item`), and `quickfort` as one general tool. These are the highest-value wrappers on this list under the project's generalisability rule.

