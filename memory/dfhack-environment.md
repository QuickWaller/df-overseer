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

## Availability — check before assuming

DFHack ships docs for tools that are **not available in this build**. They are
tagged `Tags: unavailable` in `hack/docs/docs/tools/`. Grep for that string
before designing around any tool.

**Available and load-bearing:** `deteriorate`, `autobutcher`, `combine`,
`logistics`, `cleanowned`, `clean`/`cleaners`, `tailor`, `suspendmanager`,
`timestream`, `spectate`, `stonesense`, `quickfort`, `blueprint`, `orders`,
`prospector`, `probe`, `pathable`, `burrow`, `eventful`, `unretire-anyone`,
`bodyswap`, `lair`, `gui/embark-anywhere`, `gui/control-panel`.

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
