# Live run: deploy the blueprint hands verb, dry-run and read checks only

Date: 2026-09-24. HEAD d5e33be, committed bytes only. User go-ahead for this
deploy and read-only/dry-run checks. No real apply, no unpause, no commit.
Each file hashed at source, on arrival in /tmp, and at the installed path: all
three matched for all six. Prior copies backed up with `cp -p` to
`/opt/df/deploy-backup-20260924-blueprint` (tools.py, TOOLS.yaml, both
tools.yaml; the .lua and the .csv were new).

| File | sha256 (first 16) |
|---|---|
| `scripts/dfhack/df-overseer-blueprint.lua` (new) | `77bc5f1749f010fb` |
| `blueprints/templates/bedroom-cell-v1.csv` (new) | `5773336bbb503e2a` |
| `scripts/dfhack/TOOLS.yaml` | `78b1a31c3ff89a10` |
| `dfmcp/tools.py` | `698bdcf5795ea8e9` |
| `agents/architect/tools.yaml` | `fb8457923594a6ca` |
| `agents/overseer/tools.yaml` | `1b2e57d9fdae9fa8` |

Template location: `dfhack-config/blueprints/` existed but its `templates/`
subdirectory did not; I created it (`mkdir -p`) and put the .csv there.
Guest .lua went to `/opt/df/game/hack/scripts/`; dfmcp files under
`/opt/df/dfmcp-smoke/` mirroring the repo layout.

Tick check: before, `clock status` abs_tick 12611557, paused true (equals the
last autosave tick). After all checks: same tick, still paused.
dfmcp-server: `sudo -n systemctl restart`, `is-active` = active, 0
`RoleValidationError` lines in the journal since restart.
buildingplan: `buildingplan` prints "buildingplan is enabled" (use blocks yes,
boulders yes, logs yes, bars no).

Route: `./dfhack-run df-overseer-blueprint <cmd> ...` in `/opt/df/game` via
`scripts/vm-ssh.sh df`. No permission refusal occurred.

## Results

The Lua loaded and ran under real DFHack with no error on any call.

- `plan bedroom-cell-v1`: footprint 5x5, room 3x3, finish_required_cells 15,
  four phases (shell dig 25, zone 9, build 1, finish meta 2 applying zone and
  build), needs_dug_shell false/true/true/true. Matches the expectation.
- `sites`: `[]` (correct, nothing applied).
- Landmark and level: the handoff's example level 0 finds nothing (`preview ...
  Well 0 1` returns `no candidate at rank 1 (found 0 near Well ...)`; the
  `diggable find 5 5 0 Well` read also returns `[]` at radius 20/40/80). LEVEL
  is relative to the landmark; -1 finds sites (levels -2 partly, -3 and +1
  none). Checks below use LEVEL -1, radius 40.
- `preview bedroom_cell_v1_shell`, dry run, ranks 1 to 3 near Still (stone):
  rank 1 (NE 2, Stockpile #2) and rank 2 (E 5, Activity Zone #1): 15
  designated, quickfort "Tiles that could not be designated for digging: 10",
  finish_plan hidden 10, smoothable 5, blocked_by_material {}. Rank 3 (E 2):
  14 designated, 11 not, hidden 11, smoothable 4. `ok: false` in all three
  (quickfort's non-progress counter is nonzero), `interior_fully_revealed:
  false`, `finish_required_met: false`.
- Near Well (soil), ranks 1 to 3: 10 designated, quickfort not-designated 15;
  finish_plan hidden 10, blocked_by_material {"SOIL": 5}, smoothable 0, and a
  `remedy` text citing dig.lua:77-87 and build.lua:107-165.
- blocked_by_material vs quickfort: agrees. Soil sites: quickfort's 15 =
  hidden 10 + SOIL 5. Stone sites: quickfort's 10 = hidden 10, blocked 0. (One
  caveat: quickfort reports a single undifferentiated counter, so the
  agreement is on the sum, not on per-cause attribution.) The copied
  smoothable set is consistent with quickfort's on the 6 sites read; no site
  had a tile that only one of them would reject.
- Coordinates: none in any output (site is direction, distance, landmark,
  rank, handle null).
- Preview writes nothing: pending dig designations (bounded read of
  `world.map.map_blocks` designation.dig != 0) 35 before, 35 after six
  previews.
- Negative controls: made-up handle `preview ... site-99` returns
  `{"error": "no site 'site-99' (see sites)"}`; same for the finish phase and
  for `status site-99`. Finish and build phases with a landmark return
  `a new site can only be found for a phase that starts by digging; give a
  site-N handle for phase 'bedroom_cell_v1_finish'`. Bad template name returns
  a named error listing both looked-for paths.

## Not checked

- The order guard (finish/build refused with `blocked` while dig designations
  are outstanding) needs a real handle, which exists only after a real apply.
  The landmark-for-later-phase refusal above is a different, earlier guard.
- The rectangle shim (`surface` read_back), `designations_landed`, and `status`
  on a real handle: all require a real apply.
- The stone sites' hidden 10 tiles mean the shell would only partly designate
  now; a real apply would need an interior that is revealed.
