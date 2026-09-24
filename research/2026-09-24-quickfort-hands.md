# What quickfort actually does: the Architect's hands

Date: 2026-09-24. Handoff: `handoffs/2026-09-24-blueprint-hands.md`.

Method: every claim below was read on VM 103 from the installed DFHack 53.16-r1.1
source (`/opt/df/game/hack/scripts/quickfort.lua` and
`/opt/df/game/hack/scripts/internal/quickfort/*.lua`) with `cat -n`, read-only, over
`scripts/vm-ssh.sh df`. Nothing was run in the game: no quickfort call, no dry run,
no designation. Cites are `file:line` inside `internal/quickfort/` unless a full path
is given. **VERIFIED** means the source text says it. **INFERRED** means it follows
from the source but nobody has watched it happen on this install. Runtime behaviour
(what a dry run really prints, whether `run_command_silent` captures stderr) is
INFERRED throughout and is the job of the live check in the handoff Result.

## 1. Entry points

- **CLI** `quickfort run FILE -c x,y,z [-d] [-n /LABEL] [-m ...] [-p N] [-q]`
  (`quickfort.lua:82-105`, `command.lua:257-333`). `-c` is required when there is no
  keyboard cursor (`command.lua:201-207`), so headless use always passes it. VERIFIED.
  The blueprint's top-left cell lands on `-c`; this project already paid for
  getting that wrong once (`df-overseer-diggable.lua`, the "BUG FOUND LIVE
  2026-09-11" note).
- **`-d` / `--dry-run`** sets `ctx.dry_run` (`command.lua:275`). VERIFIED. What it
  changes is in section 5.
- **Section names.** `-n` takes `sheet/label`. `parse_section_name` matches
  `^([^/]*)/?(%S*)` (`parse.lua:80-90`), so the bare word `bedroom_cell_v1_shell` is
  read as a **sheet name**, not a label. For a `.csv` (no sheets) the label must be
  written **`/bedroom_cell_v1_shell`**. VERIFIED from the pattern; this is a trap,
  the wrong form is a sheet lookup that finds nothing. Without `-n`, the default is
  `''`, i.e. the first section only (`command.lua:264`); a `.csv` with several
  `#mode` sections applies just the first unless `-n` or a `#meta` names the rest.
  INFERRED for the "first only" reading, from `section_names = {''}`.
- **Lua API.** `quickfort.apply_blueprint{mode=, data=, pos=, dry_run=, ...}`
  (`quickfort.lua:43-56`) takes the grid as a string or table, plus a `pos`, and
  returns `clean_stats(ctx.stats)`: a table keyed by stat id, each `{label, value}`.
  It calls `do_command_raw` for one mode and one z-level at a time and does **not**
  read a file, resolve a label, or run `#meta`. `params.dry_run` is passed through
  (`api.lua:41-55`, `make_ctx` at `command.lua:51-68`). VERIFIED. This is the only
  route that returns structured counts, but it needs the grid in memory and skips
  meta bundling and label lookup, so this project's verb does not use it (section 8).
- **Blueprint lookup.** A bare or sub-directory name resolves under
  `blueprints_user_dir` (`dfhack-config/blueprints` by default), then by
  `library/` and mod prefixes (`list.lua:26-48`). A file in a `templates/`
  subdirectory therefore resolves as `templates/<name>.csv`. VERIFIED.

## 2. `#dig` symbols (`dig.lua:527-576`)

| Symbol | Effect | Line | Notes |
|---|---|---|---|
| `d` | dig (mine) | 171 | Designates only WALL/FORTIFICATION; an already-open tile is an invalid tile. Hidden tiles are designated blindly (173) |
| `h` | channel | 194 | |
| `u` `j` `i` | up / down / up-down stair | 212-256 | |
| `r` | ramp | 258 | |
| `t` | chop tree | 183 | no-op on non-tree |
| `s` | **smooth** | 288-297 | See below |
| `e` | **engrave** | 299-307 | Only on an already **smooth** floor/wall with no existing engraving |
| `F` | fortification | 309 | Only on an already smooth wall |
| `T` / `trackN...` | carve track | 316-333, 561-594 | Only floor/ramp of a hard material |
| `on` `ol` `oh` `or` | **traffic** normal/low/high/restricted | 429-447, 556-559 | Any visible tile; hidden is refused (nil) |
| `n` | remove construction | 348 | |
| `x` | remove designation | 355 | |
| `bc bf bm bd bh ...` | item flags | 386-427 | claim/forbid/melt/dump/hide |

**Smooth is the constraint that matters** (`do_smooth`, `dig.lua:288-297`): the tile
is refused (returns nil, counted as *invalid*) if it is hidden, is a CONSTRUCTION,
is **not "hard"**, is already smooth, or is not FLOOR/WALL shape. "Hard" is
`hard_natural_materials` = STONE, FEATURE, LAVA_STONE, MINERAL, FROZEN_LIQUID
(`dig.lua:77-87`). **SOIL is not in that set**, so quickfort itself refuses to smooth
soil. That agrees with the surface layer's independent finding from the tiletype
table (no SOIL tiletype carries the SMOOTH special; `df-overseer-surface.lua`
header). VERIFIED twice, by two different sources.

**Engraving is smooth-then-engrave in two passes.** `e` is refused on an unsmoothed
tile (301-302), so a single blueprint cannot smooth and engrave the same tile in one
application: the smoothing must complete first. VERIFIED. `preserve_engravings`
(default Masterful) protects existing engravings from `d`/`h`/`u`/`j`/`i`/`r`/`F`/`T`
(`can_clobber_engravings`, 738-744). VERIFIED.

**Buildings block designation.** `s`/`e`/`T` skip a tile whose building occupancy is
above Passable and not Dynamic (`dig.lua:839-845`); `d` and the other dig verbs skip
any tile with a building (851-853). Traffic ignores buildings (846-849). The skip is a
silent `goto inner_continue`: it is **not counted** in `dig_invalid_tiles`.
VERIFIED. This matters: a tile with furniture on it that was asked to be smoothed
disappears from every counter.

Priority is the digit suffix or `-p`; `set_priority` writes the block's
priority event (`dig.lua:653-663`). Marker mode (`mb`) makes designations
"blueprint markers" that dwarves ignore until unmarked (679-683). VERIFIED.

## 3. `#build` and walls (`build.lua`)

- **`Cw` places a constructed wall** (`build.lua:939-941`,
  `type=Construction, subtype=Wall`). Its tile rule is
  `is_valid_tile_construction` (151-165) over `is_valid_tile_has_space_or_is_ramp`
  (121-124, 107-119): the tile must be visible, unbuilt, not deep liquid, and one of
  EMPTY/FLOOR/BOULDER/PEBBLES/RAMP_TOP/BROOK_TOP/TWIG/SAPLING/SHRUB or RAMP. **A
  WALL-shaped tile is not on that list.** So `Cw` can only be placed on tiles that
  are already open. VERIFIED.
- **Consequence for soil.** A standing soil wall can be neither smoothed (section 2)
  nor built over (`Cw` refuses WALL shape). The only route to a finished soil wall is
  two steps: dig the tile out (`d`), let the job complete, then `Cw` it. A one-shot
  blueprint cannot express that. The template README's "resolve as `Cw` where the
  tile is not standing rock" is correct for **already-open** tiles (a seam whose
  neighbour dug it out) but is **not** an answer for standing soil. This is the
  largest remaining gap. VERIFIED from the source; no live attempt.
- `Cw` is a job that needs a **building material item** (a boulder/block/bar) and,
  with the `buildingplan` plugin enabled, is registered with it (`build.lua:1302-1311`).
  With buildingplan **disabled**, quickfort warns and the placed building "will
  disappear if you do not have required building materials in stock"
  (`build.lua:1326-1331`). VERIFIED (source text). Whether buildingplan is enabled on
  VM 103 is not established here.
- Furniture symbols: `b` bed (valid tile: `is_valid_tile_inside`, 757), `d` door
  (valid only on a floor tile next to a WALL/FORTIFICATION, 760-761,
  `is_tile_generic_and_wall_adjacent` 178-184), `c` seat, `t` table, `f` cabinet,
  `n` coffin, `h` container, `r` weapon rack, `y` glass window, and so on
  (`build.lua:754-835`). VERIFIED.
- **A door needs a wall next to it, so furniture order matters.** `d` is refused until
  a WALL/FORTIFICATION shape is orthogonally adjacent, which is true for a door in a
  carved shell but not for one in an open field. VERIFIED.
- **The user guide's ordering rule** (`quickfort-user-guide.txt` line 1242 per the
  bedroom template's own `sources`): furniture built before smoothing can block a
  dwarf's access to the wall behind it. Consistent with `dig.lua:839-845` skipping
  smoothing on building-occupied tiles. VERIFIED from the source that produces it.
- Dry run in `#build`: `create_building(b, cache, ctx.dry_run)` is called for every
  building with a `pos`, and `build_designated` is incremented either way
  (`build.lua:1346-1350`); the tile check (`check_tiles_and_extents`,
  `building.lua:517-556`) runs first and clears `b.pos` for an invalid building, so
  invalid ones are counted under `Unsuitable tiles for building`
  (`build.lua:1323`) rather than designated. VERIFIED.

## 4. `#zone` (`zone.lua`)

`b` bedroom, `o` office, `m` meeting area, `h` dining hall, `D` dormitory, `B`
barracks, `T` tomb, and others (`zone.lua:105-127`). Stats: `Zones designated`,
`Zone tiles designated`, `Zone tiles skipped (tile occupied)` (388-395). A dry run
still counts `zone_tiles` and `zone_designated` (`create_zone` returns `ntiles`
before touching the map when `ctx.dry_run`, 358-359, 417-419). VERIFIED. The user
guide's "zones cannot apply to hidden tiles" (bedroom template `sources`) is a
reason a zone blueprint must follow the dig.

## 5. Dry run: what it does and reports

VERIFIED from source:
- `#dig`: the loop builds `action_fn` for every tile (this is where validity is
  decided), increments `dig_designated` for each tile that *would* be designated,
  `dig_invalid_tiles` for each that would not, and only calls `action_fn()` (the real
  write) and removes existing dig jobs when **not** `ctx.dry_run`
  (`dig.lua:856-880`). `dfhack.job.checkDesignationsNow()` is also skipped
  (`dig.lua:908-910`). A dry run of `#dig` is therefore a faithful "what would be
  designated" count with no write.
- `#build`, `#zone`: as in sections 3 and 4.
- `finish_commands` prints "Blueprint statistics:" then one line per stat with
  `value > 0` or `always` (`command.lua:183-196`), unless `-q`.
- A mode that ignores `-d` was not found in `dig`, `build` or `zone` (the three modes
  this project uses); `burrow`, `place`, `query` and `stockflow` were not read.

INFERRED (never observed on this install): that `dfhack.run_command_silent` returns
exactly that stdout. This project's `df-overseer-building.lua` already parses it with
the line pattern `^  ([^:]-): (%d+)%s*$` (`parse_quickfort_stats`), and its 2026-09-21
dry run and 2026-09-23 real run confirm the pattern for `#build` and `#zone`. The same
pattern for `#dig` stat lines ("Tiles designated for digging", "Tiles that could not
be designated for digging") is INFERRED from the same `print` at `command.lua:191`.

## 6. Tiles quickfort cannot act on, and how it says so

| Situation | How reported | Line |
|---|---|---|
| Off the map | `Tiles outside map boundary` counter | `dig.lua:826-831`, `command.lua:35` |
| Map edge (dig verbs `d h u j i r T`) | counted invalid | `dig.lua:172` etc. |
| Bad key sequence | `Invalid key sequences` counter, plus `dfhack.printerr` | `dig.lua:791-798` |
| Tile refused by the verb (e.g. `s` on soil, `d` on open floor) | `Tiles that could not be designated for digging` | `dig.lua:859-863` |
| Hidden tile, `s`/`e`/`n`/traffic | same counter (they return nil on hidden); `d`/`u`/`j`/`i`/`r`/`h` designate blindly | `dig.lua:173, 289, 300` |
| Building on the tile, `s`/`e`/`T` | **not counted at all** (`goto inner_continue`) | `dig.lua:842-844` |
| Building on the tile, other dig verbs | **not counted at all** | `dig.lua:852-854` |
| Invalid `#build` tile | `Unsuitable tiles for building` | `build.lua:1340-1343` |
| Occupied `#zone` tile | `Zone tiles skipped (tile occupied)` | `zone.lua:403-405` |

The two uncounted rows are the traps: a designation silently dropped because furniture
stands on the tile leaves no trace in the statistics, so an "all counters zero"
result does not prove every tile took. A verb wrapping quickfort should re-read the
game, not trust the counters alone.

## 7. Partial failure and what "success" means

- The CLI's exit is `CR_OK` whenever the script does not raise. Section errors in a
  `#meta` are caught with `pcall` and only `dfhack.printerr`'d (`meta.lua:106-113`);
  the meta then carries on with the next referenced blueprint and the run still
  finishes "successfully". VERIFIED. `Blueprints applied` (`meta.lua:83-85`,
  incremented only on success at 109-112) is the one counter that reveals a dropped
  sub-blueprint: compare it with the number of blueprints the meta names.
- Per-tile refusals (section 6) never raise. An entire blueprint that designates
  nothing still prints and returns OK. The existing `df-overseer-building.lua`
  already records this live: "quickfort returns success even when it designated
  nothing (negative control, live 2026-09-21)".
- **Not transactional.** Nothing is rolled back if a later section fails; the
  designations already written stay. `quickfort undo` exists (`command.lua:23-27`) but
  its own comment says it "isn't guaranteed to restore what was set on the tile
  before" (`dig.lua:139-141`); for `#dig` it sets a sensible default (No dig,
  smooth 0), it does not restore the prior designation. VERIFIED.
- Re-applying a `#dig` blueprint is safe: with a real run, an existing dig job at the
  tile is removed and the designation re-set (`dig.lua:870-876`), a `#build` over an
  existing same-shape construction is refused for idempotency (`build.lua:145-165`).
  VERIFIED.

## 8. What quickfort does not cover

1. **Wall construction over standing soil or ore** (section 3): needs dig then `Cw`,
   two applications with a completed dig between them.
2. **Sequencing.** Nothing in quickfort waits for a dig to finish. `#meta` applies
   its sections back to back in the same tick (`meta.lua:88-117`), so a `#meta` that
   bundles `#dig` then `#build` designates a door or a bed on tiles that are still
   solid, and the bed/door is refused (`Unsuitable tiles`). The bedroom template's
   `finish` meta correctly bundles zone and build only and leaves the dig to a
   separate earlier application. A wrapping verb must enforce the order.
3. **Whether the work is done.** Quickfort queues designations; it says nothing about
   whether dwarves finished them, whether a wall came out smooth, or whether the room
   is enclosed. The surface layer (`df-overseer-surface.lua`) is the
   only read for that.
4. **Materials.** `Cw` and every `#build` consume items; quickfort does not check
   stock (the `buildingplan` route defers to it, section 3).
5. **Entrance orientation.** A blueprint has no notion of "faces the corridor".
   `-t` (transform: rotate/flip, `command.lua:301-303`) exists but choosing it needs
   knowledge of which side of the site borders the walkable network. The site finder
   (`diggable.find`) only guarantees that the ring borders the network somewhere,
   not that the template's entrance edge is that side.
6. **Engraving needs an existing smooth surface**, so smooth and engrave are two
   applications a completed smooth apart.
7. **Room value.** Whether the finished room is good enough for a noble is answered
   by `nobles.requirements`, not quickfort.

## 9. How this shaped the verb

- Use the CLI route through `dfhack.run_command_silent`, as
  `df-overseer-building.lua` and `df-overseer-zone.lua` already do, with `-n
  /LABEL`, because it resolves labels and runs `#meta` (the API route does neither).
- Parse stats with the existing line pattern and check `Blueprints applied` against the
  number of blueprints a `#meta` names.
- Never trust the counters alone: re-count outstanding designations in the site
  rectangle (real run) and re-read enclosure, finish and material with the surface
  layer's own functions.
- Decide the soil rule before applying, from the same tile classification, and report
  it (a `#dig` `s` cell on soil is refused and counted; the verb says so up front and
  in words, and names the remedy, rather than leaving the caller to infer it from a
  counter).
- Refuse to run a build/zone phase while the site still has outstanding dig
  designations or an un-dug `d` cell, since quickfort will not.


## 9. Addendum 2026-09-24 (blueprint-access): orientation, undo, and why a dig can stall

Read from the installed source (`/opt/df/game/hack/scripts/internal/quickfort/`,
read-only over ssh), not run.

- **Transform.** `-t` takes names `rotcw|cw`, `rotccw|ccw`, `fliph`, `flipv`, comma,
  semicolon or space separated (`transform.lua:57-68`, `parse.lua:345-358`). Every cell
  is rotated about the CURSOR (`-c`), not the blueprint's centre (`transform.lua:40-49`,
  `command.lua:109-131`). DF's y axis is inverted, so `rotcw` sends (dx,dy) to
  (-dy,dx): a south-facing entrance ends up on the WEST edge, `rotccw` puts it on
  the east, `rotcw,rotcw` on the north. A rotated blueprint lands up and left of
  the cursor, so the cursor must be moved to the site's corner: for a blueprint of
  bw x bh cells and site top-left (sx,sy): rotcw -> (sx+bh-1, sy), rot180 ->
  (sx+bw-1, sy+bh-1), rotccw -> (sx, sy+bw-1). The verb's cell mapping is the
  matching closed form. VERIFIED from source; the mapping is tested offline (each
  open side picks the rotation whose entrance faces it), never yet run live.
- **Why a dig stalls.** DF makes a dig job for a designated tile only if a dwarf
  can path next to it. A designation on unrevealed or enclosed solid rock with no
  walkable neighbour is accepted by quickfort (`Tiles designated` counts it) and
  never gets a job. INFERRED from the live run (`evals/live/2026-09-24-office-build`).
- **Undo.** `quickfort undo` runs the same mode code with `values_undo`
  (`dig.lua:142-160`, `917-921`): dig designation No, smooth 0, and in a real run
  `dig.lua:870-876` removes an existing job at each tile first. `-c`, `-n`, `-t` and
  `-d` all apply. It "just sets a sensible default" (`dig.lua:139-141`): it cannot
  restore a prior designation, and it cannot un-dig a tile or un-smooth a wall
  already worked. VERIFIED from source, not run. Undo of a `#zone` or `#build`
  would remove real zones and buildings, so `release` refuses any site that has
  had a non-dig phase applied.
- **Releasing site-1 (the stalled office site).** With the verb deployed: `status
  site-1` should report `dig.state: stalled`; `release site-1` (dry run) shows the
  undo it would run; `release site-1 false` withdraws the 10 blind dig
  designations. It cannot undo the 5 north-ring walls already smoothed (they stay
  smooth, harmless). Without the verb: `quickfort undo templates/office-room-v1.csv
  -c X,Y,Z -n /office_room_v1_shell` with the site's own coordinates and no
  transform (site-1 was applied unrotated). Both paths need their own go-ahead.

## Addendum 2026-09-24: two status misreads found live, and the rule that replaces them

Both came from reading DF state through a proxy instead of the thing itself.

- **A dig flag is not a job.** DF clears a tile's dig designation flag once it
  has made a job for that tile, so counting flagged tiles undercounts work in
  flight. Site-2's entrance gap had a real, unclaimed Dig job with the flag
  clear, while its 9 interior cells were flagged, job-less and blind until the
  gap was dug; status read `stalled`. Rule now: a site with any dig, carve or
  smooth job in it is never `stalled`; `dig` reports `jobs_in_site` and
  `jobs_claimed_by_a_worker`. `stalled` is only for a site with no job at all
  whose designations are all blind, or startable ones past the grace period.
- **Completion is per-cell, not a count.** `shell_done` read true with 11 of 15
  ring tiles rough and undesignated, because it tested "no outstanding
  designations and no solid carve cells", which is also true of a shell nobody
  ever designated the smoothing of. Rule now: `shell_done` is computed from the
  cells the template requires, read directly (carve cells dug, `s` cells smoothed
  or constructed), and `status.shell_cells` returns the counts so a caller sees
  why: `carve_required/dug/solid`, `smooth_required/done`, `rough`,
  `undesignated`, `hidden`, `unreadable`.

Tests: `tests/test_blueprint_lua_logic.py` (five new, all failing on the prior
file). Unverified: `dfhack.job.getWorker` on the live build (a failed read is
reported as unknown, never as unclaimed).
