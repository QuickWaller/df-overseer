# Stream: reachability that means something, not "the middle tile is not standable"

**Written** 2026-09-23. **Status:** dispatched. **User go-ahead:** 2026-09-23,
"yeah id say so", after the Well read as unreachable from every direction.
**Offline only: do not touch VM 103 or VM 106.** A sibling stream
(`handoffs/2026-09-23-office-and-first-real-build.md`) is running the fort
right now and owns the live machine. Sonnet executor, worktree-isolated.
**No push. No attribution lines in any commit.**

## Why

`df-overseer-landmarks.lua` tags each exit with `walkable`, from
`dfhack.maps.canWalkBetween` on the two landmarks' **centroid** tiles. The
fort's Well reports `walkable: false` to all three of its neighbours. It is
not cut off. Live reads by the orchestrating session, 2026-09-23:

- the Well's own centre tile is a **RampTop**, which nobody can stand on, so
  every one of the eight tiles around it reports "cannot walk to the well
  tile";
- of the tiles around the Well, **four can walk to the Still**, so the Well is
  connected to the fort and is used the way wells are used, from a tile beside
  it.

So the flag currently answers "is the arbitrary middle tile standable and
connected", which is not the question any agent asks. Every landmark whose
centre tile is not standable is affected: anything over a channel, a stair, a
ramp, a bridge. The failure is the dangerous kind, a confident false negative:
an agent reading it would conclude the well is unreachable and dig a corridor
to reach something it can already reach. The file's own header already admits
the centroid may not be standable and that a failure is reported as
`walkable=false`; that admission is the bug.

## What to do

1. **Use walkable groups.** DFHack tags each tile with a walkable group id
   (`dfhack.maps.getWalkableGroup`, confirm the exact accessor against the
   installed DFHack's own lua and scripts before using it). Two standable
   tiles with the same non-zero group are connected; different non-zero groups
   are definitely not. This is cheaper and more exact than a path call. Verify
   what a group id of 0 means on this version and treat it honestly.
2. **Pick a tile that can actually be stood on.** For each landmark, choose a
   representative standable tile belonging to it, falling back to the tiles
   immediately around it (which is how a well, a stair or a bridge is really
   used), and only then to nothing. Report which case was used, so a reader
   can tell "reachable from beside it" from "reachable at it".
3. **Three states, not two.** `reachable`, `unreachable`, `unknown`, with a
   short reason on the last two. Never report "unknown" as "unreachable"
   again. Keep the old boolean field alongside only if something depends on
   it, and say what depends on it.
4. **One shared helper**, used by every tool that answers a reachability
   question: `df-overseer-landmarks.lua`, `df-overseer-connectivity.lua`,
   `df-overseer-threat.lua`'s reachability admission rule, and any other
   caller you find. Do not copy the logic per tool. Check whether the threat
   tool's own rule changes behaviour under the fix and say so plainly: that
   rule decides what the fort is told about hostiles, so a change there is a
   finding for the user, not a silent improvement.
5. **Keep it coordinate-free at the decision layer.** The tools may read
   tiles internally; their output must stay free of raw coordinates, per
   `CLAUDE.md` and `docs/PURPOSE.md` design commitment 1.
6. **Tests**, including a regression for the Well's exact shape: a landmark
   whose centre tile is not standable but whose surrounding tiles are
   connected must report reachable, not false. Both suites green: ambient
   `python -m pytest` (1266 passed / 3 skipped before you) and
   `.venv-dfmcp/Scripts/python -m pytest dfmcp/tests` (652 before). Report the
   new counts.
7. **Write down the limits you did not fix**, for the later design
   conversation: standing room at the destination, doors and hatches that can
   be locked or forbidden, a route that exists but is absurdly long, flooding
   and other state that changes reachability over time, and reachability for
   a specific unit rather than in general. Put this in the Result, not in new
   code.

## Hard lines

- **Offline only.** No ssh, no VM, no deploy, no live DFHack call. Deploy is a
  separate decision after the fort run finishes. Verify DFHack API claims
  against the installed copy's own source under
  `/opt/df/game/hack` **only if you can read it without touching the VM**;
  otherwise use upstream source and mark the claim as not install-confirmed.
- No model call. No armok capability, nothing a player could not know.
- Secrets by key only, never printed. Never print an IP or hostname.
- Do not write `Working.md`, `decisions/` or `memory/`. No em dashes.
- Commit as you go and fill in the Result section.

## Touched surfaces

`scripts/dfhack/df-overseer-landmarks.lua`,
`scripts/dfhack/df-overseer-connectivity.lua`,
`scripts/dfhack/df-overseer-threat.lua`, a new shared Lua helper if that is
the right shape, `TOOLS.yaml`, the matching dfmcp schema and tests, tests
under `tests/` and `dfmcp/tests/`, this doc.

## Result

(executor fills in)
