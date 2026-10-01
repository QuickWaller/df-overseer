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

Done. `research/2026-10-01-dfhack-notifications.md` has the full answer;
summary here.

**Q1**: the list lives in `scripts/internal/notify/notifications.lua`
(the scripts submodule), `NOTIFICATIONS_BY_IDX`, lines 425-737, 19 entries
(16 fort-relevant, 3 adventure-only). All 19 are self-clearing by
construction, not by any clear-on-resolve logic: `gui/notify.lua`'s overlay
rebuilds its choice list from empty every poll and only keeps entries whose
function currently returns non-nil, so there is nothing stored as "active"
to go stale. Confirmed by direct, verbatim, line-numbered source read (via
`curl`/CDN mirror of the pinned commit, not WebFetch's own summarizer,
which silently truncated this 777-line file and needs flagging as
unreliable past roughly line 480 for a file this size).

**Q2**: `reqscript('internal/notify/notifications')` from any script
context, then call `entry.dwarf_fn or entry.fn` per entry directly, no
overlay or visible screen needed, ignoring the player's own
enabled/disabled toggle. Cheap: at most a few dozen O(active-units) scans,
same order of cost as the project's own `df-overseer-vitals.lua`. One minor
side effect: first load writes `dfhack-config/notify.json` once (a settings
file, no game-state mutation).

**Q3**: all 16 fort-relevant notifications read player-visible or
player-derivable facts, with one flagged exception (`missing_nemesis`,
savegame-corruption internals no vanilla screen shows — recommend an
explicit ruling before wiring it in, not decided here). Important
correction found: DFHack's own `invader_count`/`hostile_count` use exactly
the `isDanger`/`isInvader` flags this project's own `df-overseer-threat.lua`
already proved an unreliable reachability signal (its header cites a kea
reachable-but-unflagged and demons flagged-but-unreachable) — recommend NOT
wiring these straight into the fixed floor's "reachable hostile" item, only
as a cheap pre-check ahead of the existing reachability tool. `warn_stranded`
(the exact 2026-09-28 incident's own catch) is recommended for the fixed
floor; a handful of others (`injured`, `mandates_expiring`/
`petitions_agreed`, `moody_status`, `save-reminder`) are proposed as
ordinary tunable wake reasons. Also found, as a bonus cross-check: DFHack's
`warn_starving` thresholds (75000 hunger / 50000 thirst) are byte-identical
to `df-overseer-vitals.lua`'s own `HUNGER_CRITICAL`/`THIRST_CRITICAL`,
both ultimately from DFHack's `full-heal.lua`; DFHack's version adds a
`sleepiness_timer > 150000` check `df-overseer-vitals.lua` is currently
missing, worth a small separate follow-up.

**Q4**: one generic tool, `df-overseer-notify status`, iterating the
module's own table (no per-notification branches, so DFHack's next release
costs nothing); wired into the conductor's per-cycle read step next to
`vitals.summary`; new `policy.yaml` wake reasons per the Q3 mapping table.
Live test plan: a module-load smoke test, a functional check on
`warn_stranded`/`save-reminder` against known-good current state, a
several-cycle diff watch, a supervised reproduction of a real stranding to
prove the floor reason fires and self-clears, and an explicit live check
that the reachability tool still gets the final word over the raw
`invader_count`/`hostile_count` pre-check.

No code written, no live access, no permission refusals encountered. One
methodology note worth a future researcher's attention: WebFetch is not
reliable for verbatim/line-numbered reads of files over roughly 400-500
lines; switching to a direct `curl` fetch of a CDN mirror
(`cdn.jsdelivr.net/gh/<owner>/<repo>@<commit>/<path>`) plus the ordinary
file-read tool gave genuine byte-for-byte content instead.
