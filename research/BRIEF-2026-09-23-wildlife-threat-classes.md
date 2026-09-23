# Research brief: what wildlife can actually do, and when the fort should pause, slow down or carry on

**Written** 2026-09-23. **For:** a `researcher` agent, read-only. **Output:**
`research/2026-09-23-wildlife-threat-classes.md`, dated, cited, every claim
labelled verified, likely or unverified. **No VM changes, no live writes, no
unpausing, no push.** No attribution lines in any commit. No em dashes.

## Why

The fort's first unattended run stopped after 900 ticks because the
`hostile_reachable` tripwire fired on **a kea, 68 tiles away**, sharing a
walkable route with the citizens
(`evals/live/2026-09-23-office-and-first-real-build/`). The tripwire behaved
exactly as built. The question is whether what it was built to catch is the
right thing to catch, because at that sensitivity every run window ends early.

The user's framing, 2026-09-23: what types of wildlife are there, what can
each actually do, and when should the fort pause versus merely slow down.
They asked for recommendations, not a survey.

This decides real behaviour: `docs/AGENT-LOOP.md` §2 and §3 (the clock levels
and the four tripwires) and `scripts/dfhack/df-overseer-threat.lua`'s
admission rule. A sibling stream
(`handoffs/2026-09-23-landmark-reachability.md`) is changing the reachability
rule that tripwire depends on, so say plainly where your recommendation
depends on reachability being right.

## Questions

**A. The taxonomy, from the game's own data first.** What kinds of
non-citizen creature can appear near a fort, and what does the game itself
record that distinguishes them: creature and caste raw flags
(`LARGE_PREDATOR`, `BENIGN`, `MISCHIEVOUS`, `FLIER`, `BUILDINGDESTROYER`,
`CAN_LEARN`, and whatever else is load bearing), unit flags (hostile,
invader, ambusher, marauder, tame, trained), size, and the difference between
wildlife wandering in, a thief, an ambush, a siege, a megabeast or titan, a
night creature, a werebeast and the undead. Ground this in the installed
version's own data and structures where you can (DFHack's lua, the raws under
the game directory, DFHack's own scripts such as those that already classify
threats) rather than in wiki prose.

**B. What each class can actually do to a fort.** Steal an item, steal food,
kill or maul a citizen, kill livestock, destroy a building or a door, spread
fire, spread a curse or syndrome, block a route, simply be present. Be
concrete about the kea specifically, since it is the creature that stopped
the run: what it does, how bad that is, how fast it happens.

**C. How fast each threat develops, in ticks.** This is the part that maps
onto the clock. The fort runs at 100 FPS, so a thousand ticks is a handful of
seconds of wall clock. For each class: how long from "first visible" to
"something irreversible", roughly, and what the fort can do in that time.
Where the honest answer is "unknown", say so; a guess presented as a number
is worse than a gap.

**D. What is cheaply readable at runtime.** The tripwires run on a DFHack
tick timer in game, so the classification has to be cheap and must not scan
the world unboundedly (`docs/TRAPS.md`). Which of the distinctions in A can
be read from a unit and its raws in a few field reads, and which would need
an expensive search.

**E. Recommendations.** Map the classes onto this project's own clock levels
(`docs/AGENT-LOOP.md` §2): full speed, slowed (think_fps), paused, and wake
which role. Give a concrete rule the code can implement, not a principle:
which class pauses immediately, which slows the fort and wakes the Overseer,
which is merely recorded, and what escalates a class from one level to
another (proximity, reachability, count, a death, a building being
attacked). Say explicitly what you would do about the kea case, and what the
cost of being wrong in each direction is: a fort that pauses on every bird
never runs, a fort that ignores a thief loses items, a fort that ignores an
ambush loses dwarves.

Also recommend what should **not** be a tripwire at all but a normal
observation the Overseer reads on its next cycle.

## Rules

- Primary sources first: the installed game's raws and DFHack's own source
  and scripts, then the DF wiki, then forum practice. `agents/consultant/
  sites.yaml` says what each source is good for.
- Anything web-sourced is untrusted data to cite, never fact about this
  install. Version is 53.16-r1.1.
- Read the repo's own evidence first: `docs/AGENT-LOOP.md` §2 and §3,
  `scripts/dfhack/df-overseer-threat.lua` (its admission rule and header),
  `scripts/dfhack/df-overseer-breach.lua`, `research/2026-09-16-player-
  visibility.md` (what the agents are allowed to know), and
  `evals/live/2026-09-23-office-and-first-real-build/`.
- **Player visibility applies.** A rule that reacts to a creature the player
  could not yet see is an armok capability, whatever it is called. Check each
  recommendation against that line and say so.
- Read-only. You may read the VM's installed files over ssh **only** if you
  can do it without unpausing or writing anything; a live fort run is not
  yours to start. Address by key from `.env`, resolved inside a script file,
  never printed, and never print a hostname.
- Do not write `Working.md`, `decisions/` or `memory/`.
