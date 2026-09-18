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
