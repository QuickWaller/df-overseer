# Blueprints

`quickfort` blueprint source files (`.csv`, `#dig`/`#place`/`#build` modes),
the "Blueprint library" scope item from `docs/PURPOSE.md`. Chosen over raw
DFHack designation writes deliberately: design commitment #4 says the model
picks a named template and an anchor, never generated coordinates, and
`quickfort` (a mature, stock DFHack tool) is the real mechanism for that —
see `decisions/DECISIONS.md` 2026-09-10 ("Played Uniboslan forward for
real").

**Status: four starter files, hand-authored, not yet templated for reuse.**
Built and applied once each, live, against Uniboslan's actual first room:

| File | Mode | Purpose |
|---|---|---|
| `starter-entrance-1x1.csv` | `#dig` | One downstair tile from the surface |
| `starter-connector-1x1.csv` | `#dig` | One upstair tile linking the entrance to the room below — required; a plain floor dig directly beneath a stair never becomes a job, see the durable traps in `Working.md`/`working-archive/` |
| `starter-room-5x5.csv` | `#dig` | The room itself |
| `starter-stockpile-5x5.csv` | `#place` | A matching general stockpile over the dug room |

**Deploy path**: plain `scp` into the guest's `dfhack-config/blueprints/`
(quickfort's own player-blueprint directory), not through
`install_df.py`'s script-deploy mechanism — these are quickfort data
files, not DFHack Lua scripts. Applied headlessly via
`quickfort run <file> -c x,y,z`, which needs no interactive map cursor.

**Not yet handled here**: grass-covered surface tiles can't take a
downstair designation (confirmed live, `quickfort` reports 0 tiles
designated with no error) — any anchor point picked automatically rather
than by hand needs to check the actual tile type first, or scan for a
non-grass tile within the target footprint. None of these files do that
check themselves yet; the entrance's coordinates were hand-picked after
manually confirming the tile type this time.
