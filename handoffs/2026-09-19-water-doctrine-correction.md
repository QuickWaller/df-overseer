# Handoff: correct the water doctrine and spec §12 from the undiggable-pond finding

Date: 2026-09-19. Offline stream. **No VM, no SSH, no DFHack, no fort.**

Read `CLAUDE.md`, then `docs/PRODUCTION-MODEL.md` §12, then `Working.md`'s
section "The fort cannot drink, and the pond cannot be dug to", then
`doctrine/seed.yaml`'s `water-source-zone-for-ponds` and
`bedridden-need-water-brought`, then this.

## Why this stream exists

**Two load-bearing claims in this repo are disproven, and the disproof is a
real piece of game knowledge that nothing currently records.**

`docs/PRODUCTION-MODEL.md` §12 says, plainly:

> "For an able dwarf the chain is solved: the `WaterSource` zone got the
> founders drinking."

It did not. Measured 2026-09-19 across two exact reads: **delta tick 6,303
equalled delta thirst 6,303 across all 15 citizens**, so `thirst_timer`
increments exactly 1 per tick and **nobody drank at all** over that interval.
The zone is active (`spec_sub_flag.active = true`), the water is 27 tiles all
at least 3 deep, and it is **unreachable**.

The doctrine entry `water-source-zone-for-ponds` encodes the same wrong
lesson, and it is `status: verified` or near it. Check and fix that.

## The finding, which is the valuable part

**A `WaterSource` zone on water is not sufficient. The water must have a
walkable neighbour at its own z-level.**

Measured tile shapes at Uniboslan:

- **z168** (the water): 142 WALL, 26 RAMP, 1 FLOOR, **0 walkable**. All 27 wet
  tiles have **zero walkable neighbours**.
- **z169** (above): 134 walkable, 100 FLOOR, 26 RAMP_TOP, **0 wet**.

So the pond is a **sunken bowl**: a basin of submerged ramps whose rim is a
wall ring, with dry floor a level above. A dwarf standing at z169 is adjacent
to the water diagonally in 3D but cannot drink from it.

**And digging to it does not work, which was established by digging, not by
argument.** A Channel was designated at z169 on a FLOOR tile with 3 walkable
neighbours, directly above a waterline wall, adjacent to 6/7 water. Under one
supervised unpause it was dug. Result: **z168 wet went 27 to 28; z168 walkable
stayed 0.** The newly opened tile simply filled with water and became another
unwalkable wet tile. A first attempt had also been designated one z-level too
low, and investigation showed z168 has no walkable tile a miner could even
stand on, so that designation could never have been dug either.

**The generalisable rule:** opening a tile adjacent to a body of water at the
water's own level converts the new tile into more water, so you cannot dig a
standing spot *into* a full basin. The remedy is a **well**, which draws
upward from a dry tile above.

## Deliverable

1. **Correct `docs/PRODUCTION-MODEL.md` §12.** The "solved for an able dwarf"
   claim goes. Replace it with the reachability condition and the sunken-basin
   case. Keep the section's existing honest self-correction about the buckets
   and the sleeping miner; **do not delete corrections, this document's habit
   of keeping its own errors visible is deliberate.** Add the new one in the
   same voice.
2. **Correct or supersede `water-source-zone-for-ponds`** in
   `doctrine/seed.yaml`, and add the new entries the finding earns. Candidates,
   name them as you judge best:
   - a **water reachability** rule: a source is only a source if it has a
     walkable neighbour at its own z-level, and this is checkable before a zone
     is ever placed;
   - a **sunken basin** rule: how to recognise one (wet tiles, zero walkable
     neighbours, walkable floor one z above) and that it is a well case, not a
     digging case;
   - a **do not dig into a full basin** rule, with the measured evidence.
3. **Add a `docs/TRAPS.md` entry** if one fits: a `WaterSource` zone reporting
   active tells you nothing about whether anyone can reach it, and thirst is
   the only real check.

## Rules that bite here

- **Nothing may be marked `verified` that this stream did not verify.** The
  measurements above are real and you may cite them as measured; anything you
  add from the wiki or from general DF knowledge is `prior`. Run
  `doctrine/validate.py` and its tests.
- **Do not invent a number.** This project has already had an illustrative
  "11 days" come back as apparent data within a day. If you want a figure for
  well depth limits, bucket travel, or anything else, and you cannot source it,
  say it is unavailable and why.
- **Verify the verification.** State what each new entry's evidence actually
  proves, and what it does not. Specifically: we proved *this* pond is
  unreachable and that *one* channel flooded. We did **not** prove that no dig
  anywhere could ever reach it, and the entries should not claim we did.
- Do **not** write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`.
- No em dashes in prose.

## Touched surfaces

`doctrine/seed.yaml`, `doctrine/validate.py` and `doctrine/tests/` only if a
format change is genuinely required, `docs/PRODUCTION-MODEL.md`,
`docs/TRAPS.md`, and this handoff doc.

**Do not touch** anything under `production/`, `scripts/`, `CLAUDE.md` or
`ROADMAP.md`: other streams and the orchestrator own those.

## Done means

§12 no longer claims the water chain is solved, the doctrine carries the
reachability rule and the sunken-basin case with honest statuses, the doctrine
tests pass, the full suite still passes (364 passed / 1 skipped right now,
report before and after), and the write-up at the bottom of this file states
exactly what was proven versus inferred.
