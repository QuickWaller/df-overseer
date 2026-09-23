# DFHack environment — verified truths

What was checked against the local install on 2026-08-25, and what it implies.
Re-verify after any DF or DFHack update; the v50 transition invalidated a lot
of older community knowledge and several tools are shipped-but-disabled.

**This file describes the local Windows install.** The fortress VM runs the
same DFHack version on Linux against DF Classic; see
[`infra/local.df-vm-install.md`](infra/local.df-vm-install.md) for that install's paths and layout,
which differ. The availability findings below were audited against it on
2026-08-27 and hold, with two corrections: the tool is `cleaners`, not `clean`,
and 105 tool docs carry the `unavailable` tag rather than the ~51 implied here.

## Versions and paths

| | |
|---|---|
| Dwarf Fortress | Steam appid **975370** |
| DFHack | **53.16-r1.1**, Steam appid **2346660** |
| DF path | `C:\Program Files (x86)\Steam\steamapps\common\Dwarf Fortress` |
| DFHack path | `C:\Program Files (x86)\Steam\steamapps\common\DFHack` |

DFHack installs to its **own folder**, not into the DF directory — the newer
`dfhooks` model (`dfhooks_dfhack.ini` points at `hack/dfhooks_dfhack.dll`).
Launch via the DFHack Steam app or `hack/launchdf.exe`, not the DF app.

**As of the check, DFHack had not been run**: no `dfhack-config/` and no
`stderr.log` in the DF folder. `dfhack-config/` is created on first launch —
several things below (including `remote-server.json`) do not exist until then.

Offline docs are at `hack/docs/docs/` as greppable `.txt`. The
`Lua API.txt` is ~6900 lines. **Grep the local docs before trusting web results
or memory** — they are version-exact.

## Scripts live outside the game folder

`dfhack-config/script-paths.txt` registers extra script directories:

```
+C:/website-projects/df-automation/scripts
```

`+` searches before the stock scripts (so you can override them), `-` after,
`#` comments. Relative paths resolve against the DF root. Read at startup only,
but paths can also be added at runtime via the Lua API. **No junction or
symlink needed** — the repo stays outside the install.

## Remote interface

Protobuf over TCP, **port 5000**, local-only by default. Config lives in
`dfhack-config/remote-server.json` (`allow_remote`, `port`). Core methods:
`BindMethod` (id 0), `RunCommand` (id 1). `RemoteFortressReader.plug.dll` is
present, so structured map/unit reads work out of the box.

`RemoteFortressReader`'s own doc is only ~26 lines; the real RPC surface was
extracted from the plugin DLL with `strings`. Message *names* are DLL-verified
(high confidence); field layouts came from a single upstream source (moderate).

**The field-level detail underneath this summary now exists and is
implemented, 2026-09-12.** `research/2026-09-12-dfhack-rpc-client.md` settles
the handshake bytes, the 8-byte header layout, the reply-id set and the
message field numbers at this install's own version, and `dfmcp/dfhack_client.py`
implements them with no `protobuf` dependency. Nothing there contradicts this
section. Three things it adds that matter to anyone using this interface:
**a connection carries one request at a time**, so concurrency needs a pool;
**`BindMethod` is not needed** for running commands, since `RunCommand` is a
hardcoded id on every connection; and **`RunCommand` is refused from any peer
but loopback even when `allow_remote` is set** (reported by the brief, not
independently confirmed), which if it holds means the remote config option
does not open the path this project actually uses.

## Availability — check before assuming

DFHack ships docs for tools that are **not available in this build**. They are
tagged `Tags: unavailable` in `hack/docs/docs/tools/`. Grep for that string
before designing around any tool.

**Available and load-bearing:** `deteriorate`, `autobutcher`, `combine`,
`logistics`, `cleanowned`, `clean`/`cleaners`, `tailor`, `suspendmanager`,
`timestream`, `spectate`, `stonesense`, `quickfort`, `blueprint`, `orders`,
`prospector`, `probe`, `pathable`, `burrow`, `eventful`, `unretire-anyone`,
`bodyswap`, `lair`, `gui/embark-anywhere`, `gui/control-panel`.

**Audit 2026-09-21: "load-bearing" above means present and documented, not cleared
for use.** Six of these are tagged `armok` by DFHack (`prospector`,
`clean`/`cleaners`, `unretire-anyone`, `bodyswap`, `lair`,
`gui/embark-anywhere`), and so are `caravan` and `diplomacy` in the additions
below. The user's rule (`CLAUDE.md`, "No armok capabilities") bans powers a
player lacks and information the game hides, and `docs/ARMOK-RULINGS.md` records
each ruling: `prospect` (default mode), `caravan list` and `diplomacy` (list
only) are allowed; `cleaners`, `lair`, `unretire-anyone`, `bodyswap` and
`gui/embark-anywhere` are banned (the first two open for later). The tag is
only a pointer, so check a tool against the rule, not against the tag.

**ADDED 2026-09-12**, confirmed present by direct source read at the matching
version tag (53.16-r1.1) while verifying capabilities the agent architecture
depends on, and load-bearing enough to belong in this list:
`overlay` (the widget framework, render-loop-gated so it needs no human input),
`workorder` (a real callable Lua module with `create_orders()`, and currently
the **only** route to manager work orders, since `stocks` and `workflow` are
both unavailable), and `setfps` (writes `df.global.enabler.fps`, the runtime
frame-cap control). → `research/2026-09-12-dfhack-capability-checks.md`.

**ADDED 2026-09-16**, each confirmed available by `dfhack-run help <tool>`
against the live paused fort by the orchestrating session, not taken on a
subagent's report: `caravan` (adjust caravans on the map; `caravan list` and
`caravan extend` are pure-read and headless-write respectively), `diplomacy`,
`force`, and `logistics` was already listed above but had never been checked
live. The trade research found all four while answering whether an agent can
close a trade. → `research/2026-09-16-trade-execution-api.md`.

**Also corrected 2026-09-16, and it invalidates older docs:**
**`viewscreen_tradegoodsst` does not exist in this build.** Confirmed live
(`df.viewscreen_tradegoodsst == nil`). Trade moved into
`df.global.game.main_interface.trade` with the v50 rewrite. Anything in this
repo that reasons about "the trade viewscreen" by that name is reasoning about
a struct that is not there.

**Unavailable in 53.16 (present as docs/files, tagged unavailable):** `mode`,
`gui/advfort`, `stocks`, `zone`, `workflow`, `follow`, `load-save`, `linger`,
`embark-assistant`, `dwarfmonitor`, `labormanager`, and ~40 others.

`mode` being unavailable is the practically important one: **DFHack cannot
script game-mode switching in this version**, which blocks automating
retire/unretire/embark. `dfhack.world.isFortressMode()` / `isAdventureMode()`
exist as read-only checks; there is no retire/abandon/embark function in the
Lua API. `mode`'s own doc also warns that most mode combinations corrupt saves.

## Reference implementations worth reading

- `hack/scripts/warn-stranded.lua` — connectivity analysis via
  `dfhack.maps.getWalkableGroup`, DF's own pre-computed connected-component
  cache. Copy this for `check_reachable`.
- `hack/scripts/prioritize.lua` — event-driven updates via the `eventful`
  plugin.

## quickfort

- **`quickfort run ... -c x,y,z` anchors a blueprint's top-left corner, not
  its center.** Confirmed against `hack/docs/docs/tools/quickfort.txt`
  ("the blueprint start position... is the upper left corner by default"),
  not recalled from memory. This is easy to get backwards when a candidate
  box is computed as (top-left, width, height) and a center coordinate gets
  derived for display purposes elsewhere (e.g. landmark direction/distance
  reporting): passing that center to `-c` silently shifts the real
  designation by `(floor((w-1)/2), floor((h-1)/2))` tiles away from wherever
  a reachability/adjacency check actually validated. Found live 2026-09-11
  after this exact mixup broke both `dig_diggable_area`
  (`df-overseer-diggable.lua`) and `build_open_area`
  (`df-overseer-openarea.lua`) on `perception-layer-experiments`; the build
  case happened to still work by luck (its candidates sit in broadly open
  space), while the dig case produced a real, silently-unreachable
  designation. Full trail: `decisions/DECISIONS.md` 2026-09-11 ("Root cause
  found and fixed..."). **Any future tool that resolves a ranked
  candidate box to a real coordinate for a `quickfort -c` call must pass the
  box's true top-left, never a computed center.**

## Game-side facts

- `prefs/init.txt` overrides `data/init/init_default.txt`. `FPS_CAP` and
  `G_FPS_CAP` are **separate**: cap the simulation low and leave rendering at
  50, and the world crawls while the UI stays smooth. **Match them by name.**
  They are lines 22 and 23 here and lines 71 and 75 on the VM's Linux install,
  so any script that seeks a line number will edit the wrong setting.
- One game year = 403,200 ticks (336 days x 1200).
- Existing saves are **15–19 MB** each — small worlds, short histories. Keep it
  that way; the 25 GB RAM horror stories are 250-year histories on large maps.
- DFHack persistent site data survives retire/unretire (*per Lua API docs*),
  which matters for the fort dossier.
- **`dfhack.buildings.getSize()`'s `cx,cy` are local to the building's own
  box, not absolute map coordinates.** Found live 2026-09-10 building the
  real burrow/building enumeration (`df-overseer-landmarks.lua`): using
  them directly as a centroid collapses every building's position onto
  nonsense points near the map origin. Add the building's own `x1,y1` (or
  equivalent origin field) before using them as a real coordinate.
- **`df.global.world.burrows.all` does not exist.** The correct path on
  this install is `df.global.plotinfo.burrows.list` — confirmed live, not
  guessed from a naming pattern.

**ADDED 2026-09-17**, from the water-source-zone test and the water/industry
tool builds:

- **`quickfort`'s `is_valid_zone_tile` checks only `getTileFlags(pos).hidden`,
  nothing about water, walls or floor**, so a `#zone` blueprint can be placed
  directly on a deep-water tile and `quickfort` will accept it without
  complaint. This is what let a `WaterSource` zone be placed *on* a pond at
  z168 rather than beside it, and it is why the fort's own founders then
  walked down to the water's own level to drink, the first self-serve
  drinking this project recorded. Read from `zone.lua` source, confirmed by
  the live placement succeeding.
- **A well needs BLOCKS, a BUCKET, a CHAIN (or rope), and TRAPPARTS
  (a mechanism), and is buildable on an `EMPTY` or `RAMP_TOP` tile that
  borders floor**, per quickfort's own `is_tile_empty_and_floor_adjacent`
  (`l` symbol) plus this project's own added rule that the tile directly
  below must be revealed water at least 3/7 deep (the wiki's stated minimum,
  version-matched). So a pond-edge well needs no bridge or dig to the
  water's own level, just those four items and a bordering dry tile.
- **A cautionary tale on trusting a partial live-adjacency check**: the same
  day, a first pass concluded `dfhack.maps.getWalkableGroup` was
  miscategorizing RAMP/RAMP_TOP tiles near a pond (74 of 98 checked read
  group 0 while directly touching group 11). A second, more careful
  full-box re-scan found this was wrong: every one of those tiles was
  genuinely underwater, and group 0 was the correct answer all along. The
  first pass's own adjacency check just hadn't looked at what the ramps
  actually held. Re-verify a surprising `getWalkableGroup` finding against
  the tiles themselves before trusting it, the same lesson as the
  `flags.foreign`/`flags.trader` mixup a day earlier.
- **The water/drink `df.job_type` values on this install**: `Drink` (19),
  `DrinkItem` (20), `FillWaterskin` (21), `FillWaterskinItem` (22),
  `GiveWater` (176), `GiveWaterPet` (178), `DrinkBlood` (221).
- **`dfhack.units.getNoblePositions` is how to check whether any citizen
  holds the Manager position** (needed before `workorder.lua`'s
  `create_orders` can matter in practice). Uniboslan has nobody in that
  role; `create_orders` itself has no manager check in its own source, so
  whether the engine will actually turn a manager order into a job with
  nobody appointed is unverified, not enforced by any tool here.
- **`dfhack.buildings.getFiltersByType` returns an identical generic
  `flags2.building_material` filter for every workshop kind**, mason,
  carpenter, mechanic, still and kitchen alike, no `item_type`/`mat_type`
  restriction at all. In practice this means boulder, wood and blocks are
  all interchangeable building material for any workshop, not something to
  special-case per kind.
- **Manager work-order `df.job_type` values used by `orders.lua`**:
  `blocks` = 80 (`ConstructBlocks`), `mechanisms` = 139
  (`ConstructMechanisms`), `barrels` = 125 (`MakeBarrel`), `brew_drink` = 209
  (`CustomReaction` with `reaction_name = BREW_DRINK_FROM_PLANT`; brewing is
  a reaction, not its own job type, so no job type literally named "Brew*"
  exists).

- **Kitchen restrictions need no UI automation** (verified 2026-09-18, live
  read of the install). `ban-cooking.lua` ships with this DFHack and writes
  `df.global.plotinfo.kitchen` directly, the same struct the
  `never-cook-seed-items` doctrine entry was verified against. Usage:
  `ban-cooking <type|all>`, with types including `seeds`, `brew`, `booze`
  and `fruit`, plus `--unban`. Its own docs call `ban-cooking all` a
  sensible first action in a new fort, and it bans types not yet in stock,
  which clicking the Kitchen screen cannot do. **Uniboslan has never run
  it.** So "protect the seed stock" is a one-command write, not a settings
  screen, and doctrine's seed rules are actionable today.

**ADDED 2026-09-18**, from the production-model live-state audit
(`research/2026-09-18-schema-extraction-live.md`), read-only, fort paused
throughout, `ReadCurrentTick()` unchanged before and after:

- **`item.flags.in_job` is the exact, cheap job-claim signal for an item.**
  A real per-item bool, live-matched to a real job's `job.items[i].item`
  (job 372's `job.items[0].item.id` resolved to item 67, which itself read
  `flags.in_job == true`). No job-table scan is needed to ask "is this item
  claimed": check the item directly.
- **`item.flags.owned` plus the item's `UNIT_HOLDER` general_ref is
  confirmed exact for dwarf ownership**, not just believed. 5 sampled
  `owned=true` items all resolved via `UNIT_HOLDER` to unit 192, and
  `dfhack.units.isMerchant(unit)` read `false` for that unit, a real
  citizen, not a trader. This closes `df-overseer-stocks.lua`'s own
  previously-open question on this field.
- **A live plant instance carries its own growth counter**,
  `grow_counter` on `df.global.world.plants.all[i]`, a materially better
  harvest-clock anchor than catching a `PlantSeeds` job's completion,
  because it works even if nobody was watching the planting. Its exact
  direction and post-maturity behaviour are **unconfirmed**, since nothing
  is planted on Uniboslan to observe (9,100 live plant instances exist
  map-wide, all wild). Any tool reading `world.plants.all` needs the same
  `dfhack.maps.isTileVisible` guard this project already applies elsewhere,
  since the vector is naively omniscient.
- **`df.global.cur_season` is exact and already the convention this
  project's other tools use** (Spring=0..Winter=3); `cur_season_tick`
  reads as `cur_year_tick` minus the season's start tick, divided by 10.
- **The 1,200 / 33,600 / 403,200 tick conversions (day/month/year) are
  confirmed live, not just cited**: two real `SEASON_*` announcement `time`
  fields landed at exactly `403200/4` and `403200/2`. The per-month figure
  (33,600) stays arithmetic-only; DF does not announce month boundaries the
  same way.
- **Stockpile give/take links are a real struct on both sides**:
  `building_stockpilest.links.{give,take}_{to,from}_{pile,workshop}` on the
  stockpile, and the mirrored `building.profile.links` on a workshop. Both
  read empty (0) on Uniboslan today (nothing configured), a real "not
  configured" rather than a read failure.
- **`dfhack.maps.getTileFlags(pos).traffic` decodes via the real
  `df.tile_traffic` enum** (`0=Normal, 1=Low, 2=High, 3=Restricted`,
  decoded live by direct numeric probing), the same call every other tool
  in `scripts/dfhack/` already uses for tile flags generally. The traffic
  *designation* is a live-readable per-tile field; the four cost weights
  themselves (1/2/5/25) are compiled into the binary, not raw-derivable,
  and are also a configurable default in-game, not a hardcoded constant.
- **A full vanilla raws set exists on the workstation, not only on the VM**
  (found 2026-09-19 by a background search that had been scoped to the repo
  and missed it): `C:\Program Files (x86)\Steam\steamapps\common\Dwarf
  Fortress\data\vanilla\`, with real `reaction_{other,dyes,smelter,
  adv_carpenter}.txt` and the `vanilla_{plants,materials,items,buildings}`
  directories. **Important caveat, and the reason this is a convenience
  rather than a source of truth: that is a Steam build, and the fort runs DF
  Classic plus DFHack on VM 103.** The version is unverified against the
  fort's. Anything claimed about Uniboslan must come from the VM's own raws;
  check `describes:` against the install version before citing a figure
  taken from the local copy.
- **The VM's raws are the authoritative copy and are cheap to pull**:
  `/opt/df/game/data/vanilla/` over SSH as user `df` (not `root`, which
  refuses with a login banner). The four reaction files hold **159
  reactions** total (adv_carpenter 22, dyes 68, other 46, smelter 23),
  matching `research/2026-09-18-schema-extraction-static.md` exactly, which
  is a useful integrity check that you pulled the same corpus the audit read.
  **Do not commit them**: this repo is public and they are game data. Stage
  them in a scratchpad and read in place.

## Added 2026-09-21 (building, nobles, zone and deploy work)

Each fact says how it is known. "Live" means read or run on VM 103 on 2026-09-21;
"source" means read from the install's files and not exercised.

**Nobles and positions**
- The fortress entity is `df.global.plotinfo.main.fortress_entity` (id 36 on
  Uniboslan). `positions.own` holds the position definitions (14: `code`, `id`,
  `flags`, `requires_population`, `number`, `required_office` / `required_bedroom` /
  `required_dining` / `required_tomb`, `description`); `positions.assignments` holds the
  slots (12: `id`, `histfig`, `histfig2`, `position_id`, `flags.active`). A vacant slot
  has `histfig` -1; a real holder has `histfig` and `histfig2` equal. (live)
- Position flags decide what can be appointed: `ELECTED` (the mayor), and
  `requires_population` with `HAS_MET_POP_REQ` (Dungeon Master, Captain of the Guard and
  Mayor need 50 and are unmet). MANAGER is appointed, `number` 1, `required_office` 1;
  its description says it must work in an office to validate work orders. (live)
- **Appointing works with the minimal write set** (live): set the assignment's `histfig`
  and `histfig2` to the figure's id, and insert a `histfig_entity_link_positionst`
  (`entity_id`, `link_strength` 100, `assignment_id`, `assignment_vector_idx` = the
  **0-based** index of the assignment in `positions.assignments`, `start_year`) into the
  figure's `entity_links`. Removing: erase that link, insert a
  `histfig_entity_link_former_positionst` (`start_year`, `end_year`), set both fields to
  -1. `dfhack.units.getNoblePositions(unit)` reflects both, and `getReadableName` shows
  the title ("manager"). No history event was needed; the version that also writes one
  (as `internal/emigration/unit-link-utils.lua` does on removal) is untested.
- **`ipairs` over a game vector starts at 0** (live), so `make-monarch.lua`'s use of the
  `ipairs` index as `assignment_vector_idx` is correct.
- An appointed Manager with **no Office did not start** three hand-validated queued
  orders in about 3,900 ticks (live, one fort). The user confirmed from play that an
  office is required. What makes a room meet a required value is not exposed by the game
  or DFHack (no room-value function; only `dfhack.buildings.getRoomDescription`).

**Zones and rooms**
- The zone vector is `df.global.world.buildings.other.ACTIVITY_ZONE` (`ZONE` does not
  exist). (live)
- quickfort's `zone_db_raw` has **18 zone kinds** on this install (AnimalTraining,
  ArcheryRange, Barracks, Bedroom, ClayCollection, DiningHall, Dormitory, Dump, Dungeon,
  FishingArea, MeetingHall, Office, Pen, PlantGathering, Pond, SandCollection, Tomb,
  WaterSource). (live, read through Lua upvalues)
- A zone's owner can be set two ways: quickfort's `assigned_unit` property calls
  `preserve-rooms` `assignToRole(position_code, zone)` (23 codes; the room follows the
  role's holder; only Bedroom, DiningHall, Office and Tomb), or `dfhack.buildings.setOwner`
  with a unit id. `quickfort --dry-run` returns before it assigns, so a dry run cannot
  prove an assignment. (source, dry-run checks live; no real assignment has run)

**Buildings and jobs**
- quickfort's `building_db_raw` and `zone_db_raw` are locals; reach them by Lua upvalues by
  name (`do_run` to the db to its metatable `__index` to the raw table) and fail loud
  naming the missing hop. 175 building kinds. (live)
- `dfhack.buildings.getFiltersByType` returns DFHack's **hand-written tables** in
  `hack/lua/dfhack/buildings.lua` for standard kinds; only the Soap Maker and Screw
  Press come from the game's raws. `quantity` is unset except for the Siege Workshop.
  (source)
- `quickfort --dry-run` can print "Unsuitable tiles" while returning `CR_OK`: judge
  validity from its statistics, not its return code. (live negative control)
- `dfhack.workshops.getJobs(building, workshop, custom)` (`hack/lua/dfhack/workshops.lua`)
  builds a workshop's job list: hard-coded definitions plus every reaction the raws attach
  to that building, each reagent converted to a `job_item` by `reagentToJobItem`. It
  covers hard-coded jobs for only 16 of 33 workshop and furnace kinds. (source, plus the
  Lua stream's dump)
- A job has flags `repeat`, `do_now`, `by_manager` and `suspend` (read from a fresh
  `df.job`); `repeat` is the workshop's own standing order. Setting it is untested.
- **The 145 `MAKE_ENT<n> <PART>` reactions** (instrument pieces; Craftsdwarfs 100, forges
  15, glass furnaces 13, Kiln 7, Leatherworks 6, Masons 3, Carpenters 1) are in no raw
  file: they are generated with the world and live in `world.raws.reactions.reactions`,
  each carrying `raw_strings`. Read them from the running game; a new world needs the
  read repeated. (live)
- Labor sources: `df.job_skill.attrs[i].labor` gives a labor for 68 skills (ids -1 to
  148); `plugins.orders.get_profile_labors` (the Workers tab) is non-empty for 17 kinds;
  the Mason's Workshop's list is STONECUTTER and STONE_CARVER, never MASON. (live)

**Units and saves**
- Hunger and thirst are `unit.counters2.hunger_timer` and `unit.counters2.thirst_timer`
  (`unit.counters` has no `hunger_timer`). (live)
- `quicksave` rotates slot directories (`autosave 1` to `3`); `save/current` is the
  game's working directory and can vanish after a rotation, so a check on its mtime alone
  can pass for the wrong reason. Confirm by every slot's `world.sav` mtime and
  `df.global.world.cur_savegame.save_dir`. (live)
- `dfhack-run lua -f file` does not provide `dfhack_flags`; a module-style script needs a
  small wrapper that sets it. (live)

**Creature raws, announcements and jobs (2026-09-23)**
- Per-tag creature flags live on the CASTE, not the creature:
  `creature.caste[unit.caste].flags.LARGE_PREDATOR` and so on. At creature level only
  aggregate `HAS_ANY_*` flags exist, and reading a per-tag name there raises. The
  spelling is `CURIOUS_BEAST_ITEM`/`_EATER`/`_GUZZLER`, with the underscore.
  `BUILDINGDESTROYER` is not a flag at all: `caste.misc.buildingdestroyer` is an integer
  (0, 1 or 2). (live, against a real kea, twice)
- `df.announcement_type` holds 357 fixed types on this install, ids -1 to 355. The full
  list is at `research/data/2026-09-23-announcement-types.tsv` and the levelling at
  `research/data/2026-09-23-announcement-severity.yaml`. A stalled manager order produces
  no announcement of any kind: the channel reports events, never their absence. (live)
- `df.job` has `order_id`, the link back to the manager order that spawned the job;
  DFHack's own `do-job-now.lua` matches on it. `manager_order.status` carries `validated`
  and `active`, and `finished_year`/`finished_year_tick`. (live)
- `job.flags['repeat']` is the repeating-job flag, used by this install's own
  `lever.lua` and `gui/workflow.lua`. (live)
- A well's centre tile is a RampTop, which no unit can stand on, so a walkability check
  from a landmark's centroid reports false for a well that is genuinely reachable from
  beside it. Resolve a landmark to a standable tile (itself, else its neighbour ring) and
  compare walkable groups. A unit standing on a ramp reads as group 0, so the old check
  could miss a hostile entirely. (live)
- `dfhack.df2utf` converts game text from CP437; no script used it before 2026-09-22, and
  a name with byte 0x96 crashed `diff.since`. (live)

- Burrows live at `df.global.plotinfo.burrows.list`, not `world.burrows` (that path does
  not resolve at all on this install: "Cannot read field world.burrows: not found").
  Uniboslan has 0 burrows. (live, 2026-09-23)
- Traffic is a per-tile designation (`tile_designation.traffic`, a 0-3 enum), not a zone
  and not a building. Every tile defaults to Normal, so the designation only carries
  intent where a player actually set one: 0 of 6,856,704 tiles are non-Normal on this
  fort. (live, 2026-09-23)
- `block.flags.update_liquid` DOES fire on this install: 3 of 26,784 blocks on a settled,
  paused map, traced to the fort's own Well, and DFHack's own `flows` tool agrees exactly.
  This contradicts `df-overseer-breach.lua`'s header, which records zero across 11 polls
  and concludes the gate might be dead; the gate works. The earlier reading is best
  explained as a snapshot artefact, which is reasoned, not confirmed. (live, 2026-09-23,
  re-verified independently by the orchestrator)
- `block.flags.designated` does NOT track live dig designations: 0 flagged blocks against
  36 genuinely designated tiles, and the job list held 0 dig-type jobs at the same moment.
  Both plausibly tick-gated on a paused fort; unconfirmed. Do not use it as a cheap
  block-level gate for the dig frontier without re-testing on a running fort. (live,
  2026-09-23)
- Item type `THRONE` does not exist on this build; the item is `CHAIR`. The JOB kept the
  legacy name `ConstructThrone` (caption "Construct Throne"), and DFHack's own
  buildingplan plugin states the mapping: `[df.item_type.CHAIR] = 'ConstructThrone'`. A
  Chair building's own job requirement reads `item_type=CHAIR`. Same renaming pattern as
  `MECHANISM`, which this build superseded with `TRAPPARTS` (found by the workjob stream,
  whose hard-coded traction bench job still cites the dead name). Expect more of these:
  a job name is not evidence of the item type it produces. (live, 2026-09-23)
- `job.job_items` is not directly iterable in Lua (`attempt to get length of a userdata
  value`); read `job.job_items.elements`. (live, 2026-09-23)
