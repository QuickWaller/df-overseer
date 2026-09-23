# Handoff: does a zone room have to be enclosed, and how is a higher room value reached

Date: 2026-09-24. **Researcher. Read-only.** No code that changes a tool, no
deploy, no fort mutation, no unpause. The fort is paused with a confirmed
quicksave and stays paused.

Read `CLAUDE.md` first, then `research/2026-09-23-room-and-zone-requirements.md`
(yesterday's pass, which this extends and may correct), the `rooms` entries in
`doctrine/seed.yaml`, and `doctrine/seed.yaml`'s header for the entry schema
and its provenance rules.

## Why, and what is already settled

Do not re-derive these; they are established and live-verified:

- A room in 53.16 is a **zone**, not a furniture-defined room.
- Room value comes from what is inside the zone's footprint. This fort's two
  Office zones are empty, the Chair sits outside both, and
  `nobles requirements MANAGER` reads `Office: required 1, status not_met`.
- Positions demand different values, read live from this fort's own entity:
  `MANAGER` and `BOOKKEEPER` 1, `SHERIFF` 100, `CAPTAIN_OF_THE_GUARD` and
  `DUNGEON_MASTER` 250, `MAYOR` 500. The last three also require a
  population of 50.
- DFHack exposes **no numeric room value**, only `getRoomDescription`'s
  quality word or empty.

## The questions

1. **Does a zone room have to be enclosed to count or to have value?**
   Yesterday's pass concluded, from a current-namespace wiki page, that an
   office "does not necessarily need to be enclosed", and this project has
   been treating enclosure as its own design preference rather than a game
   rule. **The user believes enclosure is in fact a requirement for
   zone-defined rooms.** Settle it against the install and the game's own
   data, not against the wiki alone. If the wiki is the only available source,
   say so and mark the doctrine entry `prior`, never `verified`.
2. **What does "enclosed" mean mechanically, if it means anything?** Walls on
   every side, a floor above, a door, no diagonal gap? Does a doorway count as
   a breach? Does a zone extending past its walls behave differently from one
   that stops at them? Be exact, because a checker will encode whatever you
   conclude.
3. **Does enclosure change the value even if it is not required?** Required
   and beneficial are different claims and this project has conflated them
   before (`prefer_indoors`). Answer both separately.
4. **How is a higher room value actually reached?** This is the practical
   half. `MAYOR` needs 500 against `MANAGER`'s 1. Enumerate every lever the
   game exposes and, where you can, their relative weight: furniture count,
   furniture quality, material value, room size, smoothing, engraving,
   contained goods, doors. Say which are cheap and which are expensive in dig
   and labour terms.
5. **What is the smallest office that satisfies each of those positions?**
   Even approximate guidance is useful, and honest uncertainty is fine. If the
   answer is "cannot be computed without the value formula", say that and say
   what would settle it.
6. **Is value the only gate?** Check whether a position can reject a room for
   any other reason (ownership, assignment, location, indoor status,
   population). If there is another gate, naming it is worth more than
   anything else in this brief.

## Sources, in order of authority

The install's own data outranks everything. Doctrine's rule stands: a wiki or
forum source makes a `prior`, never a `verified` entry; only a live read or
game data describing 53.16 can verify. The MANAGER contradiction (the wiki's
20-citizen story against the install's `requires_population=0`) is exactly why.

## What to produce

1. `research/2026-09-24-room-enclosure-and-value.md`, full findings with
   citations, honest about what could not be verified, leading with a verdict
   paragraph.
2. **Doctrine entries** appended to `doctrine/seed.yaml` under the existing
   `rooms` topic, following that file's schema exactly including provenance
   and `describes`. **If yesterday's entries are contradicted by what you
   find, do not silently edit them**: add the correction and mark the old
   entry `refuted`, which is what that status exists for.

## Rules

- **Read-only against the fort.** Bounded queries only, never an unbounded
  scan, nothing mutated, never unpaused. Prefer reading the install's files
  over live queries. Quote the command and its output for anything read live.
- Use `bash scripts/vm-ssh.sh df '<cmd>'` for every VM command. Do not write
  your own ssh wrapper and do not read an address out of `.env`: four agents
  have leaked a VM address doing exactly that.
- `git merge --ff-only main` first; this brief is committed on main.
- If you touch `doctrine/validate.py`, both `doctrine/tests` and the ambient
  suite must pass. Ambient baseline **1413 passed, 3 skipped**. Use `python`.
- You own the research file, `doctrine/seed.yaml`, and this doc's Result
  section. Not `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`.
- Keep output coordinate-free and never render or reconstruct a map.
- No em dashes in prose. **No attribution lines in any commit message.**
- Stop and report on any permission or classifier refusal. Never route around
  one through another agent or session.

## Done means

The enclosure question is answered as **game requirement** or **design
preference**, explicitly, with its evidence and with the confidence it
deserves, because a checker is about to encode the answer. The value levers
are enumerated with whatever weighting the sources support. Any contradiction
with yesterday's pass is stated rather than smoothed over.

## Result

**Enclosure is not a game requirement for a zone-defined room to count or
have value.** This corrects the user's working belief, stated plainly, not
smoothed over: no install data, DFHack API, or current-version source found
supports it. Confidence is `prior`, not `verified` (no install data can
settle a value question at all, per yesterday's Q3/Q6), but it is now
corroborated two independent ways rather than one: the Office wiki page
(re-fetched, fuller context) plus an informal but directly-described player
test in a Steam Community thread, both saying the same thing for the
mechanical reason yesterday's Q1 already established (rooms are zones,
valued by contents, not a walled-boundary scan).

The one source claiming an enclosure value *penalty* ("How do I increase
the value of a room") turned out, on closer reading, to carry its own
caveat that it was migrated from DF2014 and may not describe 53.16, and its
body text is written throughout for the pre-v50 furniture-defined room
mechanic. That is reported as its own doctrine entry
(`room-value-enclosure-bonus-claim-is-stale-page`) rather than silently
discarded, since "sits under a current-version URL" turned out not to mean
"describes the current version," which is worth keeping as a named trap.

No yesterday entry was contradicted; all four new entries build on
yesterday's `rooms` topic rather than refuting it (`rooms-are-zones-not-furniture`
predicted exactly this result). Value levers were enumerated
(`research/2026-09-24-room-enclosure-and-value.md` Q4: furniture volume,
quality, smoothing, engraving, size, weapon traps, levers/mechanisms,
artifacts, roughly cheap-to-expensive), all `prior`, from the same
stale-flagged page, so reported as folklore, not confirmed current
mechanics. "Smallest office per position" remains uncomputable, as the
brief allowed: no absolute per-tile or per-furniture-piece values exist in
any source read. Checked for a second gate beyond room value and found
none beyond the already-known population gate; that negative result is its
own doctrine entry.

Four new `doctrine/seed.yaml` entries under `rooms`:
`room-enclosure-not-required-to-count` (prior),
`room-value-enclosure-bonus-claim-is-stale-page` (prior),
`room-value-no-second-gate-found-beyond-population` (prior). `doctrine/tests`
14 passed; ambient suite 1413 passed, 3 skipped, matching the stated
baseline exactly. Full findings, sources and quotes:
`research/2026-09-24-room-enclosure-and-value.md`.

**For the layout checker this brief exists to inform: do not encode
enclosure as a requirement or as a value bonus/penalty.** If a checker
wants firmer ground than `prior`, the only route found is the live test
named in the research file's "What would settle it" (build one enclosed
and one open zone with matching contents, compare
`getRoomDescription`), which this read-only pass did not run.
