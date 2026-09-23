# Live run: deploy the surface perception layer and the furniture-aware ranking fix

Date: 2026-09-24. User go-ahead for this deploy only. HEAD b0a919c, committed
bytes only (`git -c core.autocrlf=false show HEAD:<path>`). Each file hashed
locally, on arrival in `/tmp`, and at the installed path: **all three matched
for all seven.** Prior copies backed up with `cp -p` to
`/opt/df/deploy-backup-20260924-surface` (the new surface script had no prior).

| File | sha256 (first 16) |
|---|---|
| `scripts/dfhack/df-overseer-surface.lua` (new) | `26f6deb841fa4bea` |
| `scripts/dfhack/df-overseer-zone.lua` | `7eb89e4d8bc294fb` |
| `scripts/dfhack/TOOLS.yaml` | `6db2a2da69cef98d` |
| `dfmcp/tools.py` | `6597e9fb52ba4e84` |
| `agents/architect/tools.yaml` | `b27d2b11aefcf02b` |
| `agents/overseer/tools.yaml` | `69303e619ad4842d` |
| `agents/consultant/tools.yaml` | `ae8ef396a4725ae5` |

Tick check: `clock status` read `abs_tick 12611557`, `paused: true`, identical
to the last confirmed autosave tick, so no quicksave was needed. Same tick and
still paused after all checks. MCP server: `sudo -n systemctl restart
dfmcp-server`, `is-active` = active, zero `RoleValidationError` lines in the
journal since restart.

## Check 4a: furniture-aware ranking. FAILED, differs from expectation

`zone find Office 3 3 0 "shale Throne" 10 true`: `any_contains_furniture:
false`, all 5 returned sites `contains_qualifying_furniture: false`,
`furniture_building_ids: []`. Expected the Chair (building 9) at rank 1.
The search block reported `furniture_tiles_matched: 1` (so the Chair was
found), `fitting_sites: 174`, and `rejected.already_zoned_same_type: 18`.

Hypothesis, unverified: the Chair sits inside the existing Office zones 10/11,
so every 3x3 window containing it overlaps already-zoned tiles and is rejected
before ranking, which the ranking fix cannot influence. If so the "fix" is
correct but cannot surface this particular Chair; a 1x1 search (which the
previous deploy showed finding building 9) would still work. Needs a look at
where the window filter runs relative to the zoned-tile rejection.

## Check 4b: surface verbs, zones 10 and 11. Matched expectations

- enclosure: zone 10 `not_enclosed`, 16 gaps (all `open_floor_edge`), 0 wall
  tiles; zone 11 `not_enclosed`, 15 gaps, 1 wall-like tile.
- finish: floor 9/9 `rough_natural` in both (`floor_fraction_finished 0.0`);
  boundary walls: zone 10 none counted (fraction null), zone 11 1 tile
  rough_natural.
- material (boundary ring, 16 tiles): zone 10 GRASS_DARK 7, GRASS_LIGHT 2,
  PLANT 2, SOIL 2, STONE 2, AIR 1; zone 11 GRASS_DARK 6, GRASS_LIGHT 5, SOIL 2,
  AIR 2, TREE 1.
- traffic: both `all_normal: true`, Normal 9, no read failures.

## Check 4c: nobles

`nobles requirements MANAGER`: Office `status: not_met`, `required 1`,
`zone_ids [11]`. As expected.

Nothing reached game state; fort paused throughout.

## 4a diagnosis (offline code read plus three bounded live reads; nothing edited, 4a is UNFIXED)

**My "Chair inside an existing zone" hypothesis was wrong; the earlier belief
was right.** Live read: Chair (building 9) at (106,91,169), no civzone at that
tile. Zone 11 spans x103-105, y90-92; zone 10 spans x106-108, y92-94. The
Chair is outside both, touching each on a corner/edge. The 18 tiles counted in
`already_zoned_same_type` are just the two 9-tile zones.

Code path (`scripts/dfhack/df-overseer-zone.lua`): `zone_tile` (line 747)
runs the furniture match first (lines 764-777, increments `furniture_matched`,
which is why it reads 1), then the later legality gates, including the
walkable-group gate `if g == nil or g == 0 then ... not_walkable` and the zone
check. `ranked_rects` (line 817) only builds a candidate window when all w*h
tiles are eligible AND share one walkable group (lines ~850-870). Ranking
(furniture first) and the overlap filter/MAX_RESULTS cap run only on those
candidates, so they never see the Chair unless a legal window contains it.
The fix is fine; the window never exists.

Why no legal window: a 3x3 containing (106,91) must start x104-106, y89-91.
Every start except x106,y89 overlaps zone 10 or 11 (already-zoned tiles reject
the window). The one zone-free window, x106-108 y89-91, is illegal on tile
contents (live read): six tiles are RAMP_TOP with `getWalkableGroup == 0`
(the Well's ramp-top false negative noted in CLAUDE.md, rejected as
`not_walkable`), (106,90) holds building 18 (rejected as occupied), and only
the Chair tile and (108,91) are FLOOR in group 3478 (so it also fails the
single-group check). So the cause is not the overlap filter or the 5-result
cap, and not zoning of the Chair tile: the Chair's only possible 3x3 windows
are either overlapped by zones 10/11 or sit on the Well's ramp tops.
The 1x1 search still finds it (previous deploy README). Consequence for the
design: for a kind where the furniture already exists, a rect-around-furniture
search cannot succeed here; the fort's zones 10/11 were sited next to it, not
around it.
