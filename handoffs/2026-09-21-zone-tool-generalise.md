# Handoff: generalise the `zone` tool over every zone kind, with an optional owner

Date: 2026-09-21. **WRITTEN, gated: dispatch after the optional-and-variadic-args
stream merges** (both edit `scripts/dfhack/TOOLS.yaml`). Live but read-only on
VM 103 (fort paused, dry runs only); one real placement is a separate,
supervised step that needs the user's go-ahead.

Read `CLAUDE.md` (especially "Tools must be generalisable"),
`scripts/dfhack/df-overseer-zone.lua` (the water-source-only tool this
replaces), `scripts/dfhack/df-overseer-building.lua` (the pattern: kind read at
run time from quickfort's own table, blueprint generated in code, dry run by
default, the result carrying `requirements` and `validation`),
`docs/BUILDING-TOOL.md`, `handoffs/2026-09-21-nobles-appoint.md` (its report:
why this exists) and `docs/TRAPS.md`, then this.

## Why

The nobles test showed an appointed Manager did not start the queued orders in
three game days. The position's own data says the Manager needs an office
(`required_office` 1) and the fort has **no zones at all**. Rooms are also on the
user's minimum bar for openclaw (build workshops, rooms, furniture). Today
`zone.find/place` handles Water Source only. The file's own header says other
kinds should be a table entry, not a rewrite; quickfort already knows **17 zone
kinds** (`zone_db_raw` in `hack/scripts/internal/quickfort/zone.lua`: Meeting
Area, Bedroom, Dining Hall, Pen/Pasture, Pit/Pond, Water Source, Dungeon,
Fishing, Sand, **Office**, Dormitory, Barracks, Archery Range, Garbage Dump,
Animal Training, Tomb, Gather, Clay) and a zone can carry an `assigned_unit`
property that quickfort hands to `preserve-rooms` as a **position code**, which
reserves the room for whoever holds that role.

## Deliverables

1. **Zone kinds from the game, not from a branch.** Read the kind table at run
   time the way the building tool does (Lua upvalues of quickfort's zone
   module; fail loud naming the missing hop), expose `list-kinds`, and make
   `find`/`place` take the kind as an argument. **Per-kind policy lives in data**:
   Water Source keeps its existing water-body policy (its own candidate finder,
   unchanged in behaviour); every other kind is a rectangle the caller sizes
   (W H, optionally defaulted), placed on revealed, walkable, building-free
   floor near a landmark using the same site-selection the building tool uses,
   with quickfort's own tile rule for the kind. The next kind must cost one data
   entry, no new code. Existing `water_source` calls must keep working with the
   same output.
2. **An optional owner on placement.** Investigate and report **both** paths
   that exist on this install, then implement the one that matches what a
   player does (assigning a room to a unit or a position on the room's own
   screen): `preserve-rooms`' `assignToRole` with a position code, and
   `dfhack.buildings.setOwner` with a unit id. Verify by read-back after a real
   placement (the zone's `assigned_unit_id` or the role reservation), and refuse
   with a named reason for an unknown code, a dead or non-citizen unit, or a kind
   that cannot have an owner. Do not assume; say what each path did.
3. **What an office needs to count.** The Manager's `required_office` is a room
   value, and a bare zone may not reach it. From the game's own data (and the
   DFHack docs), find what makes an Office meet a required value (furniture in
   the room), and put it in the result's `requirements` (as the building tool
   does) or say plainly that the game does not expose it. Do not guess.
4. **Verify, read-only, on VM 103**: `list-kinds` (17 kinds), `find` and dry-run
   `place` for at least Office, Bedroom, Dining Hall and Water Source (which must
   match today's output), the error cases, and that pause state and tick are
   identical before and after. Quote the output. No real placement.
5. **Manifest**: entries in `scripts/dfhack/TOOLS.yaml` for the new commands
   (arguments in the forms the optional-args stream added), `knowledge_scope`
   chosen and justified (a player sees zones on their own map), and the proposed
   grants written into this doc's report for the orchestrator (do not edit
   `agents/**`).

## Rules

- You own `scripts/dfhack/df-overseer-zone.lua`, `scripts/dfhack/TOOLS.yaml`, its
  manifest tests, and this doc. Do not touch `dfmcp/**`, `production/**`,
  `agents/**` or `gotchas/**`.
- Live, read-only: **never unpause, never place for real**, never run an
  unbounded query (`docs/TRAPS.md`), bound every scan. Stop and report on any
  classifier refusal; do not route around it. SSH as `df`; read secrets by key
  only; no address, hostname or token in any tracked file. Deploy nothing (run
  scripts from a scratch script path and remove it afterwards, as the building
  stream did).
- Unknown is never zero. Do not write `Working.md`, `decisions/DECISIONS.md`,
  `memory/` or `handoffs/INDEX.md`. **Commit after each milestone** and extend
  this doc's report as you go. No em dashes in prose. Use the Write tool for
  scratch scripts rather than long inline shell heredocs.

## Done means

`zone` lists and dry-runs every kind quickfort has, `water_source` behaves as
before, an owner can be given by position code or unit (dry-run verified, real
read-back path written and reasoned), the office-value question is answered from
data or reported unknown, the manifest and tests agree, the suites pass
(report before and after), and the write-up says what a real Office placement
test needs.

---

## Report (executor, 2026-09-21)

**Status: built and verified read-only, with ONE gap: the dry-run `place` calls
were never run live, because the auto-mode classifier refused a live `place`
call and this run's rules say stop on a refusal.** Everything else in
"Done means" is met. Baseline: the worktree was fast-forwarded to `b4907ec` (the
`skippable` key and the `[W H]` group are documented in `TOOLS.yaml`).

### What was refused, and what was not

One command was refused ("Modify Shared Resources"): an `eval` loop over
`./dfhack-run df-overseer-zone find ...` and `place water_source ... true`
against the deployed tool. It was not retried in any form, and no `place`
(dry or real), no `quickfort` call and no unpause was run afterwards. Every
other live command ran without a refusal: copying and running read-only Lua
scripts, `find`, `list-kinds`, `check-owner`, and the deployed tool's read-only
`find` (for the baseline). Why the refused one was refused is not known; the
only difference I can see is the `place` verb on a live fort.

### Built

- `scripts/dfhack/df-overseer-zone.lua` rewritten: `list-kinds [FILTER]`,
  `find KIND [W H] [LEVEL] NEAR_LANDMARK [RADIUS_TILES]`, `check-owner KIND OWNER`
  (new, read only), `place KIND [W H] [LEVEL] NEAR_LANDMARK [RANK] [RADIUS_TILES]
  [DRY_RUN] [OWNER]`.
- **Kind table read from the game.** `zone_db_raw` is reached through upvalues by
  name: `do_run -> zone_db -> __index (custom_zone) -> parse_zone_config ->
  zone_db_raw`, every hop failing loud with its own name and each entry
  structurally checked. **18 kinds on this install, not 17** (the handoff's own
  list named 18): AnimalTraining, ArcheryRange, Barracks, Bedroom,
  ClayCollection, DiningHall, Dormitory, Dump, Dungeon, FishingArea, MeetingHall,
  Office, Pen, PlantGathering, Pond, SandCollection, Tomb, WaterSource. Tokens
  are the `df.civzone_type` names; the label, quickfort's key and the old
  `water_source` also resolve (matching ignores case, spaces, slashes and
  underscores).
- **Policy in data.** `ZONE_POLICY` in the Lua file is the only place a kind is
  special (default size, `prefer_indoors`, `owner`, `position_field`, `caveat`,
  and `finder = "water_body"` for WaterSource). A kind with no entry is a plain
  rectangle of 3x3 on walkable floor with no owner, so **the next kind costs a
  table entry, or none.** Sizes, `prefer_indoors` and caveats are this
  project's choices, not game data, and `list-kinds` says which kinds have an
  entry (`policy_source`). `tests/test_zone_tool_manifest.py` pins that no kind
  name appears in code outside that table (negative control: an injected
  `if s == "Office"` and an injected `k.token == x` were both detected).
- **Site search** (rectangle kinds): every tile of the window is revealed, passes
  quickfort's own `is_valid_tile_fn` for the kind (called, not copied), has no
  building, no liquid, is walkable, sits in one walkable group and is not
  already a zone of the same type. A summed-area table makes any size one
  bounded pass over at most 121 x 121 tiles; W and H are capped at 31; `search`
  reports why tiles were rejected, so "no site" can be told from a broken
  check. `prefer_indoors` kinds rank fully indoor windows first (the tile's
  `outside` flag, the test quickfort's Bed rule uses). Duplicated from the
  building tool because its search is a local function of a file this stream
  may not edit.
- **WaterSource unchanged:** its flood fill, ranking, dry run and real path are
  the old code, moved into `find_water`/`place_water`.

### Verified live on VM 103 (read only, fort paused)

Run from a scratch copy in a temporary directory on the guest through a small
wrapper (`dfhack-run lua -f run.lua PATH ARGS`, which supplies `dfhack_flags`,
absent under `lua -f`). The directory is removed, the deployed
`df-overseer-zone` is still the old water-only tool (its usage text has no
`list-kinds`), and no `_tmp-zone-*` blueprint exists on the guest.

- **Pause state and tick, before and after:** `paused=true year=31
  cur_year_tick=296552 frame_counter=106974` both times (the first read is
  before any tool ran, the last after the last).
- **`list-kinds`: 18 rows.** `max` is the string `"unbounded"` for all (quickfort
  says `math.huge`; null would read as unknown). `list-kinds office` gives one
  row, `list-kinds zzz` gives `[]`.
- **`find Office "Embark Site"`: 5 sites**, 3x3, rank 1 `Embark Site` E 2 tiles,
  `search` `{tiles_checked 3721, eligible_tiles 3391, fitting_sites 2042,
  rejected {occupied 35, liquid 0, not_walkable 295, already_zoned 0}}`, none
  fully indoor. `find Office 1 1 ...`: 5 sites, **all `indoors: true`, ranked
  ahead of outdoor tiles even at distance 6 versus 1**, which shows the indoor
  preference works. `find Bedroom` and `find DiningHall 5 6` (30 tiles) gave 5
  sites each. `find Office -1 "Embark Site"` (underground) gave `no site for
  Office (3x3) near Embark Site; search: 3721 tiles checked, 25 eligible, 0
  check errors; rejected: 68 occupied, 142 liquid, 239 not walkable, 0 already
  zoned` (matches the building tool's 24 to 25 eligible underground tiles).
- **`find WaterSource` and `find water_source -1 "Embark Site" 60`: the same five
  bodies as the deployed water-only tool's `find water_source -1 "Embark Site"
  60`** (27, 31, 4, 13 and 24 tiles; dims 7x7, 5x9, 2x3, 4x6, 5x8; depth 6 to 7;
  stagnant), field for field, plus one new `token: "WaterSource"` key. Level 0
  gave `[]` from both.
- **Error cases** (all `{"error": ...}`): `Widget` gave `unknown zone kind:
  Widget (run list-kinds)`; `Offic` adds `did you mean: Office`; `Office 0 0`
  gave `footprint 0x0 is outside the game's allowed width 1..inf, height
  1..inf`; `Office 40 40` gave `larger than this tool's limit of 31 per side`;
  `WaterSource 3 3` gave `takes no W H: its footprint follows the water body`;
  an unknown landmark; `Office 99` gave `level 99 from Embark Site is outside
  the map`; no landmark gave the usage line.
- **Owner checks (`check-owner`, the same code `place` runs first):**
  `Office manager` gave the position path, group `[MANAGER]`, holder `[345]`,
  not vacant; `Office SHERIFF` gave group `[SHERIFF, CAPTAIN_OF_THE_GUARD]`,
  vacant, with the preserve-rooms consequence stated; `Office mayor` gave group
  `[EXPEDITION_LEADER, MAYOR]`, holder `[198]`; `Office 345` and `Bedroom 455`
  (a child) took the unit path. Refusals: `wizard` (lists the 23 known codes),
  unit 454 `is not alive`, 519 (a live non-citizen) `is not a citizen of this
  fortress`, 99999 `no unit with id 99999`, `Dump 345` and `water_source
  manager` `cannot have an owner (kinds marked owner in ZONE_POLICY: Bedroom,
  DiningHall, Office, Tomb)`, `bad;code` `OWNER must be a unit id (digits) or a
  position code`.
- The fort has **0 zones** (`ACTIVITY_ZONE` count 0) and 22 citizens.

### Deliverable 2, the two owner paths (investigated; behaviour on a real zone unproven)

1. **Position code: `require('plugins.preserve-rooms').assignToRole(code,
   zone)`.** It is what quickfort's own `assigned_unit=` zone property calls
   (`internal/quickfort/zone.lua create_zone`, after `constructBuilding`). The
   plugin is loaded, both features (`track-roles`, `track-missions`) are
   enabled, `stats.nobles` and `stats.reservations` are both 0, and its
   `code_lookup` holds 23 codes including `manager` (required value 1). Per its
   docs the zone follows whoever holds the role, including a later change of
   holder; a vacant role leaves it reserved and suspended; it applies to
   bedrooms, dining halls, offices and tombs (the four screens its overlay
   appears on). **`assignToRole` prints an error for an unknown code and then
   calls the C++ side with nil**, so the tool checks the code itself first.
2. **Unit id: `dfhack.buildings.setOwner(zone, unit)`** (documented: "Returns
   false in case of error", nil clears). It is the vanilla equivalent of
   picking the owner on the room's own screen; nothing follows a role.

**Both are implemented behind one `OWNER` argument** (digits = unit, letters =
position code), not one, because the room's own screen on this install offers
both and the position path is the one an agent can use without knowing who
holds the role today. If the orchestrator wants exactly one, delete the other
branch of `resolve_owner`/`apply_owner`. **What a dry run proves and does not:**
quickfort's `-d` returns from `create_zone` before it reaches the assignment
(read in the source), so a dry run proves the kind, code and unit checks and
never the assignment. **Read-back, written and unrun:** after a real placement
the tool finds the new zone (the newest civzone of that type over the window's
centre, id above the pre-run maximum) and reports `read_back` (`zone_found`,
`type_matches`, `id`, the game's `getRoomDescription`) and, for an owner,
`owner_result` (`applied`, `error`, `assigned_unit_id`, the `getOwner` unit id,
the plugin's `stats.nobles` before and after for the position path, and a note
that a `-1` may just mean the plugin has not cycled). `preserve-rooms now` is
the documented immediate update and is deliberately NOT run by the tool.

### Deliverable 3, what an office needs to count (the office-value question)

- **What the game's own data says:** the Manager position has `required_office
  1` (and 0 for bedroom, dining, tomb, boxes, cabinets, racks and stands). So the
  Manager needs an **office worth at least 1**. Bookkeeper is the same; the
  other office positions on this fort ask 100 (Sheriff), 250 (Captain of the
  Guard, Dungeon Master) and 500 (Mayor), the last three not yet reachable by
  population. The plugin's own required value for `manager` is 1. The fort has
  MANAGER held (unit 345) and no office at all.
- **What counts toward a room's value: the game does not expose it.** The zone
  struct has no value field, DFHack has no room-value function (a grep of
  `hack/scripts`, `hack/lua` and the docs finds only `required_office` in the
  preserve-rooms plugin and this repo's nobles tool), and the only read is
  `dfhack.buildings.getRoomDescription(zone)`, the quality word the room's
  screen shows. **The result says exactly this** in
  `requirements.room_value.what_counts`, with the external account marked
  unverified: the DF2014 (0.47) wiki 'Room' page says value is the floor and
  walls (smoothing and engraving add value) plus furniture and other
  constructions inside, with quality words starting at 1 (Meager), 100, 250,
  500, 1000, 1500, 2500 and 10000 (Royal). That page is for an older version and
  gives no noble requirements. **Unknown, and the first thing a real test should
  measure:** whether a bare, unsmoothed office floor is worth 0 on this version
  (then a required 1 needs a chair, table or smoothed floor) or already meets 1.
  Read `getRoomDescription` on the new zone straight after placement; it names
  the tier.
- The tool reports position rows (`code`, `required_value`, `vacant`,
  `holder_unit_ids`, `population_requirement_met`) for every kind with a
  position field, and `applies: false` with a reason for kinds no position asks
  a value of.

### Not done, needs the orchestrator or the user

1. **The dry-run `place` calls (part of Deliverable 4).** Read only in effect
   (the tool's only side effect is a scratch blueprint file it removes), but
   they are the refused action, so they are handed back. Copy
   `scripts/dfhack/df-overseer-zone.lua` and a wrapper to a scratch directory on
   the guest, then, for each of Office, Bedroom, DiningHall and WaterSource:
   `cd <game dir> && ./dfhack-run lua -f <scratch>/run.lua <scratch>/zone-new.lua
   place Office 3 3 'Embark Site' 1 30 true MANAGER`. Expected for Office:
   `dry_run true`, a `validation` block whose `ok` is true with `Zones
   designated: 1` and `Zone tiles designated: 9`, `blueprint.removed true`, an
   `owner` block. For WaterSource: the old body fields plus `would_zone_tiles`
   and `dry_run true`, no `validation`. **These are expectations, not
   results.** The wrapper is nine lines: take PATH and the args from `...`, set
   the global `dfhack_flags = {module = false}`, `loadfile(PATH)`, call it under
   `pcall` with the args, restore `dfhack_flags`, print any error. Check pause
   state and tick before and after.
2. **A real Office placement test** needs, in order: the user's go-ahead; a
   quicksave with the save slot's mtime checked (docs/TRAPS.md); the wrapper as
   above; `place Office 3 3 'Embark Site' 1 30 false MANAGER` (or `... 345`);
   read `read_back` and `owner_result` for the fields above, then
   `getRoomDescription` and whether `assigned_unit_id` is 345. If it is -1, run
   `preserve-rooms now` (documented, changes only managed rooms) and re-read.
   Then a **supervised unpause** with the existing watchdog to see whether the
   three queued orders start; the previous test saw none in about three game
   days without an office. Also decide whether the room needs furniture first:
   `building.find Chair` and `Table` pick their own sites near a landmark and
   **there is no argument that puts furniture inside a given zone**. Landmarks
   do include live zones (an "Activity Zone #1" landmark was seen on
   2026-09-17), so a landmark-relative build can get close but cannot promise
   "inside". That gap is real and unsolved here.
3. **`dfmcp/tools.py` argument text** (not touched, outside this stream's
   surfaces): `zone.KIND` still says "Only water_source exists so far", and
   `zone.OWNER` and `zone.FILTER` have no description. Proposed: `zone.KIND`:
   "The zone kind, as zone.list-kinds gives it in its `token` field (Office,
   Bedroom, DiningHall, WaterSource), or quickfort's key such as o. Never the
   display label. The old water_source still works."; `zone.W` and `zone.H`:
   "Width or height in tiles of the zone. Optional; give both or neither. Leave
   both out for the kind's default size (zone.list-kinds shows it). Refused for
   WaterSource, whose shape follows the water."; `zone.OWNER`: "Optional. A unit
   id (digits) or a position code (MANAGER, BOOKKEEPER, SHERIFF). A code
   reserves the room for whoever holds the role now or later; a vacant role
   leaves it suspended. Only Bedroom, DiningHall, Office and Tomb can have an
   owner. Check first with zone.check-owner. Needs RANK, RADIUS_TILES and
   DRY_RUN given before it."; `zone.FILTER`: "Optional substring of a kind's
   token or label." `dfmcp/tests/test_tools.py` line 852 asserts "water_source"
   appears in the `zone.find` kind description, so a new description needs that
   line changed.
4. **Grants (proposed; `agents/**` untouched).** `zone.find` and `zone.place`
   are already granted (architect and overseer per the current
   `agents/*/tools.yaml`); their ids are unchanged but their arguments grew
   (`W H`, `OWNER`). New: **`zone.list-kinds` and `zone.check-owner` (read) for
   architect, overseer and consultant**; `zone.place` stays a write grant for the
   roles that have it. `knowledge_scope`: `list-kinds` and `check-owner` are
   `player_visible` (the zone menu, and the Nobles screen's positions and
   holders); `find` and `place` are `player_derivable` (a candidate search over
   revealed tiles only, the tag the water-only tool carried).
5. **Deploy** (not done, needs a go-ahead each time): the file is not on the
   guest. The old tool remains live there, so until it is deployed `zone.find`
   and `zone.place` over MCP still speak the old grammar (`find KIND [LEVEL]
   ...`), which the new manifest no longer matches.

### Tests

Ambient `python -m pytest`: **818 passed / 2 skipped before, 834 passed / 2
skipped after** (+16, all in the new `tests/test_zone_tool_manifest.py`).
`dfmcp/tests` in `.venv-dfmcp`: **475 passed before and after**.

### What remains unknown

- **Whether the dry-run `place` works as written** (the blueprint accepted by
  quickfort `-d`, the stats labels `Zones designated` and `Zone tiles
  designated` parsed, `ok` true): the labels come from `zone.lua`'s source, not
  from a live run.
- **The whole real path:** quickfort on a generated `#zone` blueprint, the
  read-back, both owner assignments. Never run, by this or any stream.
- Whether `assignToRole` assigns immediately or only on the plugin's cycle.
- Whether a bare office floor is worth at least 1 on this version, and what
  furniture or smoothing raises it.
- Whether a Manager with a qualifying office starts validating the queued work
  orders (still the leading, untested suspect from the nobles stream).
- Fully indoor 3x3 sites near "Embark Site": none at level 0 (only 1x1 and
  small windows are indoors), so an Office there would be open-air. Whether the
  game penalises an outdoor office is unknown.
