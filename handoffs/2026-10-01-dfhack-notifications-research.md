# Handoff: read DFHack's own fort-health notifications as wake reasons

Date: 2026-10-01. **Researcher, Sonnet, read-only. No code, no live access.**

## Why

On 2026-10-01 the user saw DFHack's "stranded citizens" notification on the
live view; it was the only thing that caught our own walls sealing two
citizens in (register 2026-10-01, the incident row). DFHack already computes
a set of fort-health warnings. The conductor could read that list each
cycle as wake reasons instead of the project re-implementing each check.

## Questions (DFHack `53.16-r1`, its scripts submodule at the pinned commit, the DFHack docs)

1. Where the notification list lives (the `notify` overlay, `gui/notify`,
   `internal/notify/notifications.lua` or wherever it is at this tag), what
   notifications exist, and for each: what condition it computes, how
   often, and whether it clears itself when the condition clears (the user
   asked: "unless it also auto goes away"). File and line.
2. How a script reads the current set of active notifications and their
   detail (which units, which items) without the UI, and how expensive that
   is per call.
3. For each notification: armok status (all should be reads of what a
   player can see; flag any that reveal hidden information), and which wake
   reason and role it should map to in `conductor/policy.yaml`, with which
   ones belong in the fixed floor the Overseer cannot turn off (register
   2026-10-01, the wake-tuning row).
4. A proposed read tool (generic over notification type), the conductor
   change, and a live test plan.

## Deliver

`research/2026-10-01-dfhack-notifications.md`, short answer up front,
verified versus unverified marked. Fill in this handoff's Result.

## Rules

- First step `git merge --ff-only main`; commit the plan early, then after
  each question.
- Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`.
- No em dashes in prose. No attribution lines in any commit.
- Stop and report on any permission refusal.

## Touched surfaces

`research/2026-10-01-dfhack-notifications.md` and this handoff only.

## Result

(fill in)
