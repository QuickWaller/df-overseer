# Blueprints

`quickfort` blueprint source files (`.csv`, `#dig`/`#place`/`#build` modes),
the "Blueprint library" scope item from `docs/PURPOSE.md`. Chosen over raw
DFHack designation writes deliberately: design commitment #4 says the model
picks a named template and an anchor, never generated coordinates, and
`quickfort` (a mature, stock DFHack tool) is the real mechanism for that —
see `decisions/DECISIONS.md` 2026-09-10 ("Played Uniboslan forward for
real").

**Status: eleven starter files, hand-authored, not yet templated for
reuse.** The first four were built and applied once each, live, against
Uniboslan's actual first room; the three added
`handoffs/2026-09-16-farm-and-still-tools.md` (farm plot, still, kitchen)
were deployed and build-tested live by
`handoffs/2026-09-17-farm-tools-deploy.md` (dry runs only; no real build
exercised yet). The four added
`handoffs/2026-09-17-water-and-industry-tools.md` (well, mason, mechanic,
carpenter) are hand-authored the same way, from `#build` symbols read
directly from this install's own
`hack/scripts/internal/quickfort/build.lua`, but **not yet deployed or
build-tested live** — see that handoff's report for what was and wasn't
exercised.

| File | Mode | Purpose |
|---|---|---|
| `starter-entrance-1x1.csv` | `#dig` | One downstair tile from the surface |
| `starter-connector-1x1.csv` | `#dig` | One upstair tile linking the entrance to the room below — required; a plain floor dig directly beneath a stair never becomes a job, see the durable traps in `Working.md`/`working-archive/` |
| `starter-room-5x5.csv` | `#dig` | The room itself |
| `starter-stockpile-5x5.csv` | `#place` | A matching general stockpile over the dug room |
| `starter-farmplot-5x5.csv` | `#build` | A 5x5 farm plot (`p` symbol), zero-material, filled full-footprint like the stockpile above — for `df-overseer-farm.lua`'s `build` command |
| `starter-still-3x3.csv` | `#build` | A 3x3 Still workshop (`wl` symbol) — for `df-overseer-workshop.lua`'s `build` command, `KIND=still` |
| `starter-kitchen-3x3.csv` | `#build` | A 3x3 Kitchen workshop (`wz` symbol) — same tool, `KIND=kitchen` |
| `starter-well-1x1.csv` | `#build` | One Well tile (`l` symbol) — for `df-overseer-well.lua`'s `build` command |
| `starter-mason-3x3.csv` | `#build` | A 3x3 Mason's Workshop (`wm` symbol) — `df-overseer-workshop.lua`, `KIND=mason` |
| `starter-mechanic-3x3.csv` | `#build` | A 3x3 Mechanic's Workshop (`wt` symbol) — same tool, `KIND=mechanic` |
| `starter-carpenter-3x3.csv` | `#build` | A 3x3 Carpenter's Workshop (`wc` symbol) — same tool, `KIND=carpenter` |

**No static file for `zone.place`.** Unlike every other `build`/`dig`
tool here, `df-overseer-zone.lua`'s water-source zone is not a rectangle a
caller can specify in advance — pond sizes and shapes vary (4 to 31+
tiles this session, `research/2026-09-17-pool-reachability.md`). Its real
(non-dry-run) path generates a throwaway `#zone` blueprint CSV in code,
shaped to the chosen water body's own tile membership, writes it into this
directory on the guest, runs it, then deletes it — see that file's own
header for the exact mechanism and what was/wasn't verified live.

**Deploy path**: plain `scp` into the guest's `dfhack-config/blueprints/`
(quickfort's own player-blueprint directory), not through
`install_df.py`'s script-deploy mechanism — these are quickfort data
files, not DFHack Lua scripts. Applied headlessly via
`quickfort run <file> -c x,y,z`, which needs no interactive map cursor.
Confirmed live this session (read-only `ls`): the guest's
`dfhack-config/blueprints/` today holds only the original four files —
the three new ones must be `scp`'d there (matching the existing four's
own flat layout, no subdirectory) before any `farm.build`/`workshop.build`
call naming them can do anything but fail on a missing file. This stream
did not deploy them (no deploy, per every handoff in this project) — the
tools' own `BLUEPRINT_FILE` argument is a bare filename resolved by
quickfort itself, the same established idiom `openarea.build`/
`diggable.dig` already use, so no code depends on where in this repo the
file physically lives.

**Not yet handled here**: grass-covered surface tiles can't take a
downstair designation (confirmed live, `quickfort` reports 0 tiles
designated with no error) — any anchor point picked automatically rather
than by hand needs to check the actual tile type first, or scan for a
non-grass tile within the target footprint. None of these files do that
check themselves yet; the entrance's coordinates were hand-picked after
manually confirming the tile type this time.
