# Handoff: get a well built at Uniboslan

Date: 2026-09-18. **Live-fort stream. You have full authority to change the VM
and the fort** (user's standing grant, `Working.md` START HERE). The fort is
expendable; rescuing it is worth trying for the tools it forces us to build.

Read `CLAUDE.md`, then `Working.md` START HERE and its live fort state block,
then this.

## The situation

**The fort cannot drink.** Measured exactly: `thirst_timer` increments 1 per
tick and nobody has drunk in 6,303 ticks. Top thirst 31,899. Fifteen citizens,
zero deaths, drink stock 0.

The pond is a sunken bowl. At z168 the water sits in 26 submerged RAMP tiles
with **zero walkable neighbours**; z169 above is 134 walkable tiles of floor
and ramp-top. A channel dug at z169 toward the water simply flooded, confirmed
empirically (wet tiles 27 -> 28, walkable still 0). So no dig reaches the
water. The user's call, which is correct: **build a well.**

## The known blocker

`df-overseer-well find 1 "Activity Zone #1" 20` returns a viable site one tile
from the zone, water depth 6, not salt, **stagnant true**. Requirements against
fort-owned stock:

| Need | Owned |
|---|---|
| BUCKET | 3 |
| CHAIN | 3 |
| BLOCKS | **0** |
| TRAPPARTS (mechanism) | **0** |

Fort owns **3 logs and 0 boulders**. Stone is at z167; the stair down to it is
half-designated and never dug (orphan UpStair at z167, no DownStair above).

## The one fact that decides the route, and you must settle it first

**Can a mechanism be made from wood on this install?** Do not answer from
memory or from the wiki alone. Check this install's own raws and job data:
grep the raws for reactions producing `TRAPPARTS`, and inspect the mechanic's
workshop job. Wooden *blocks* from logs are almost certainly fine; mechanisms
are the question.

- If **yes**: 3 logs is plausibly enough for blocks plus a mechanism. Take that
  route. Count log consumption carefully; 3 is not much margin.
- If **no**: the well needs stone, so the route is **finish the stair to z167,
  mine boulders, then mason's and mechanic's workshops**. Longer, but it
  unblocks everything stone-shaped permanently.

Report which you found and the evidence, before acting on it.

## Rules that bite here

- **A lookup that can silently miss must report the miss.** This project has
  already shipped a probe that reported "0 of 15" for a labour token that does
  not exist. If you look up a name and it is absent, print
  `TOKEN_DOES_NOT_EXIST`, never a zero.
- **Verify the verification.** Before reporting an all-clear, confirm the check
  you ran could have detected the problem. State what was verified and how.
- **Check live state before escalating.** Two accurate facts can support a
  false emergency. An illustrative number must never stand in for a
  measurement.
- The fort is **paused at tick 235668** and paused is the safe state. If you
  unpause to let jobs run, do it **supervised, with a remote watchdog** that
  re-pauses, the way the water attempt did:
  `nohup sh -c "sleep N; /opt/df/game/dfhack-run lua -f /tmp/pause.lua"`.
  Use absolute paths; a backgrounded `cd` has bitten this before.
- `DF_VM_IP` in `.env` carries a **CIDR suffix that must be stripped**. Read
  secrets by the key you need (`grep -E '^KEY=' .env`), never `cat .env`.
- `ipairs` over `df.global.world.jobs.list` returns nothing; it is a linked
  list, walk `.next`.
- Do **not** write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`. The orchestrating session owns those.
- No em dashes in prose.

## Touched surfaces

This handoff doc, and the live VM/fort. Nothing else in the repo.

## Done means

Either a well is built and dwarves are drinking (verified by thirst_timer
falling across two reads, not by the well merely existing), or you have got as
far as the materials allow and this file's write-up states exactly which
blocker stopped you, what stock exists now, and the single next concrete step.

Note the stagnant water: a well drawing on it gives unhappy thoughts.
Survivable, worth recording, not a reason to stop.
