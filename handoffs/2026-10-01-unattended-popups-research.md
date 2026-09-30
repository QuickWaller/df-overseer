# Handoff: research how to clear self-pausing popups with nobody watching

Date: 2026-10-01. **Researcher, Sonnet, read-only. No code, no live access.**

## Why

The minimal starting point (register 2026-10-01) is one game year with no
human hands on the fort. A vanilla popup that pauses the game and waits for a
click stops that run cold. Known case: `FORT_POSITION_SUCCESSION` (noble
succession) self-paused a window on 2026-09-28; `df-overseer-ui click` did
land but its buffer scan cannot see that dialog's text, so it reported failure
(`Working.md`, 2026-09-28 section; `docs/TRAPS.md`;
`handoffs/2026-09-28-noble-succession-popup-research.md` and its Result; the
2026-09-16 stuck-viewscreen case in the register). Read those first.

## Questions (DFHack `53.16-r1` source, df-structures, the DF wiki)

1. **Which popups can pause or block an unattended v50 fort?** Announcement
   popups (the `announcements.txt`-driven `PAUSE`/`BOX` flags and their v50
   equivalent), modal viewscreens, and anything else. A full list by type, or
   the rule that generates it.
2. **How to detect one from a script**, reliably and without reading the
   rendered screen: the structures that hold pending popups and the current
   viewscreen or v50 widget stack, and how to tell "paused by a popup" from
   "paused by us" or by the tripwire.
3. **How to dismiss one the way a player would** (the player's own click or
   key, not an armok change to game state): what DFHack offers (`gui` input
   simulation, existing scripts or plugins that dismiss or suppress
   announcements, `announcement-levels`-style settings that stop a type from
   popping up at all). Which is cleanest and generic over popup type.
4. Whether turning a type's popup off in the game's own announcement
   settings (so it goes to the log instead) is the better fix, and which
   types are safe to demote versus ones a human should always see.
5. A live test plan the orchestrator can run (read-only or reversible), and
   whether a supervised-only answer is the honest limit for some types.

## Deliver

`research/2026-10-01-unattended-popups.md`, short answer up front, verified
versus unverified marked, a recommended design for a generic popup handler
inside the conductor's cycle. Fill in this handoff's Result (about 200
words).

## Rules

- First step: `git merge --ff-only main`. Commit the plan early, then after
  each question.
- Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`.
- No em dashes in prose. No attribution lines in any commit.
- Never design anything that shows a model a rendered screen (`CLAUDE.md`).
- Do not guess DF behaviour; say "unverified".
- Stop and report on any permission refusal.

## Touched surfaces

`research/2026-10-01-unattended-popups.md` and this handoff only.

## Result

(fill in)
