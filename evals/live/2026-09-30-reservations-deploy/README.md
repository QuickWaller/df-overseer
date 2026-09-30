# 2026-09-30: deploy of guards, material fix and room reservations, live-verified

Deployed repo `36d9c67` to VM 103 and checked every merged-but-undeployed
change from 2026-09-28 to 2026-09-30 against the real fort, over a real MCP
client as the real roles. The fort was paused throughout and read
`cur_year_tick 209571` before and after; the only persistent write was one
reservation record, created and released within the run.

## Deploy

- 27 files differed from `HEAD` (15 DFHack Lua scripts including the new
  `df-overseer-reservations.lua` and `df-overseer-blueprint-parse.lua`;
  `dfmcp/tools.py`, `dfqueue/{schema,store,render}.py`, three
  `agents/*/tools.yaml`, `TOOLS.yaml`, and the 2026-09-24 doctrine S6 files,
  merged then but never deployed). Built with `git -c core.autocrlf=false
  archive`, hash-checked on arrival (`ARRIVAL_VERIFIED`, `NO_CRLF`), backed
  up to `/opt/df/deploy-backup-2026-09-30-reservations/` with the queue DB
  copied through SQLite's online backup, installed, hash-checked again at the
  install path (`INSTALL_VERIFIED`).
- Drift checked before overwriting: four VM scripts (`breach`,
  `chokepoints`, `stockpile`, `ui`) differed from the repo only by a trailing
  blank line from an older deploy, or (`breach`) an older header comment the
  repo corrected 2026-09-23. The repo was the newer side in every case.
- Before restart, in the server's own venv: every server module imported,
  the registry loaded 99 tools, `doctrine.validate` on `seed.yaml` returned
  no errors. `dfqueue`'s new `step_targets` table is created by `CREATE
  TABLE IF NOT EXISTS` on first open, so no migration step was needed.
- `dfmcp-server` restarted clean.
- VM 106 needed nothing: every pinned openclaw config allows the server's
  tools by wildcard, so the server's role allowlists are the only boundary.

## Role tool counts (live `tools/list`, each role's own token)

| role | 2026-09-25 | now | explained by (allowlist diff since then) |
|---|---|---|---|
| overseer | 79 | 85 | +`surface.vein-material`, `construction.mine-vein`, `construction.build`, `blueprint.reserve`, `blueprint.reservations`, `blueprint.unreserve` |
| architect | 49 | 51 | +`surface.vein-material`, `blueprint.reservations` |
| consultant | 28 | 29 | +`surface.vein-material` |
| quartermaster | 24 | 24 | none |
| conductor | 15 | 15 | none |

## Live checks

| check | result |
|---|---|
| `blueprint.reserve` dry, bedroom-cell-v1 near Stockpile #1 | `would_reserve`, `allowed_kinds: [Bed, Bedroom]` (the game's own tokens, read from the template's cells), no coordinate |
| real reserve | `res-1`, visible to the architect through `blueprint.reservations` with age, purpose, allowed kinds, no coordinate |
| `diggable.find` before and after | rank 1 was the reserved site before; after reserving it was skipped and the old rank 2 became rank 1; after release rank 1 returned |
| `blueprint.apply` preview with `SITE=res-1` (the holder) | allowed |
| `blueprint.apply office-room-v1` on `res-1` | refused: "reservation 'res-1' was reserved for 'bedroom-cell-v1', not 'office-room-v1'" |
| architect calls `blueprint.reserve` | refused by the allowlist ("Advisors do not act; propose it instead") |
| `zone.place` with `RES_ID=res-1` | no candidate at rank 1 (24 eligible tiles). **Corrected 2026-09-30:** this run first said `RES_ID` limits candidates to the reservation; it does not. `filter_reserved` only drops candidates in someone else's reservation, so `RES_ID` does not pin a site (red team F-1, `research/2026-09-30-goal-tree-red-team.md`). Why this call found no candidate was not established. The "allowed kind inside" and override paths need a dug room to test live |
| override on a dry run | `override_count` stayed 0 (dry runs record nothing) |
| `unreserve` dry then real | released, `still_held_by: []`, list empty |
| `construction.build 13 Wall` dry | `held`: ring tile 5 `item_present` (an unhauled PANTS on it), ring tile 15 `keeps_access` (would cut off exposed HEMATITE). Both guards fire on the real fort |
| `building.build Masons` dry (Farm Plot, level -1) | material 182 (hematite) classified economic and excluded, `chosen_material: WOOD`; the isOre/isGem fix holds on the item path |

## Found live, not fixed here

- **Landmark names with an apostrophe cannot be passed** ("Carpenter's
  Workshop" is refused by dfmcp's command-line character check). Older than
  this work; the fort has three such landmarks.
- **`blueprint.*` cannot take `RADIUS_TILES` without `RANK`.** Deliberate
  (handoffs/2026-09-25-tool-gaps-from-first-cycle.md: the Lua treats any
  value there as an error with a handle site), and the error message tells
  the caller to pass `rank`. Recorded, not changed.
- **Material names read as `material_0_182`** in `building.build`'s report,
  not the mineral's name. Cosmetic.
- **A pair of pants lies on office ring tile 5**, where a wall is designated.
  Whether DF hauls it off before building, or the wall job stalls, is
  unverified; worth watching in the next unpaused run.

## Follow-up deploy: project MCP tools (`7a85739`)

8 files, same script and checks (`ARRIVAL_VERIFIED`, `NO_CRLF`, DB backed up, `INSTALL_VERIFIED`, imports and registry load in the server venv before restart, clean restart with no errors in the journal). Live: role counts overseer 87, architect 52, consultant 29, quartermaster 24, conductor 16 (the +2/+1/+1 the stream predicted); `queue.project_status` returns "(no projects)" to the overseer and the architect; the architect calling `queue.project` is refused by the allowlist; the overseer calling it with a nonexistent ruling is refused by the store before any write. No project was written to the live queue.
