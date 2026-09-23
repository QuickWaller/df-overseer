# Handoff: give the `slow` attention tier a way to clear

Date: 2026-09-23. **Offline. No VM, no deploy.** Build and test only; the
deploy needs its own user go-ahead and the orchestrating session will ask for
it separately.

Read `CLAUDE.md` first, then `docs/TRAPS.md`, `docs/AGENT-LOOP.md` §2 and §3,
and `evals/live/2026-09-23-chair-completion-run/README.md` (the live run that
exposed this).

## The bug, with its live example

The three attention tiers went in on 2026-09-23. `pause` latches the clock and
pauses; `record_only` only feeds the ledger; `slow` drops FPS to `think_fps`
(default 10) and writes a non-blocking advisory. Two of the three have a way
back. `slow` does not.

In `scripts/dfhack/df-overseer-clock.lua`, the slow branch inside the threat
step calls `clock_set_speed(think_fps)` and `write_advisory({...})`. Nothing in
the file ever restores the previous FPS or empties the advisory again except
`clock_arm`, which does both on re-arm. In particular `clock_clear` clears the
latch file only, and its return value does not mention the advisory at all.

The first live `slow`-tier trip happened during the Chair completion run: a
kea, `theft_tag_close_range`, correctly classified `slow` and correctly never
escalated. The advisory then stayed latched and unchanging across all three
windows on that same kea, right through to the final paused read. The fort was
left throttled. Every unattended run from here would end the same way, and the
conductor's triage would keep seeing a stale reason to be careful long after
the bird had gone.

This is a real bug with a live example, not a design worry. It was recorded as
owed in `decisions/DECISIONS.md` on 2026-09-23 and in `Working.md`.

## What to work out, not just what to type

The shape of the fix is a judgement call and it is yours to make and justify in
the Result section. The questions the orchestrator would want answered:

1. **What does the fort go back to?** `think_fps` is a floor the tripwire
   imposes; the FPS before it was imposed is not recorded anywhere. Decide
   where the restore target comes from (captured at arm time, captured at the
   moment of the drop, a configured normal, or the existing `MAX_FPS`/default)
   and say why. A restore that silently changes the fort's speed to something
   nobody chose is worse than the bug.
2. **What counts as cleared?** The obvious answer is "no candidate in this
   scan is `slow` tier". Note that the current code only inspects
   `threats[1]`, so a slow-tier candidate sitting below a record_only top
   entry is already handled inconsistently. Decide whether clearing looks at
   the whole candidate list, and whether `#threats == 0` clears too.
3. **Where does the check live?** The threat step runs only every
   `threat_check_every_n` fires. Clearing on a different cadence than
   setting would be surprising. State the cadence you chose.
4. **Should clearing be sticky or immediate?** A creature stepping in and out
   of range would otherwise flap the FPS every scan. If you add hysteresis,
   it must be visible in `clock.status`, not hidden.
5. **Does `clock_clear` clear the advisory too?** It currently does not. It
   arguably should, since it is the human's "I have seen this, carry on"
   verb, but that changes an existing tool's contract. Decide and say why; if
   you change it, the return value must report what was cleared.

**Do not invent a new tool or a new command for this.** The tiers already
exist; this is the missing half of one of them.

## Scope

Yours to change:

- `scripts/dfhack/df-overseer-clock.lua` (the fix itself)
- `scripts/dfhack/TOOLS.yaml`, the `clock` entries only, if a return field or a
  command's behaviour changes
- `tests/` for the clock and tier logic
- `docs/AGENT-LOOP.md` §3, the paragraph describing the tiers: it currently
  describes a tier that sets FPS and writes an advisory and never mentions
  that it must also come back. Write the clearing rule into the design doc, do
  not just fix the code under it.
- This doc's Result section.

Not yours, at all: `df-overseer-threat.lua`, `df-overseer-ledger.lua`,
`df-overseer-announcement-levels.lua`, `conductor/**`, `dfmcp/**`,
`agents/**`, any other `.lua`, and per the `handoffs/` rule `Working.md`,
`decisions/DECISIONS.md`, `memory/` and `handoffs/INDEX.md`. Collect any
register or memory lines you think are owed in your Result section and the
orchestrator will write them.

## Rules

- **Offline only. Do not touch VM 103, do not deploy, do not unpause
  anything.** The fort is paused at year 31 with a confirmed quicksave and it
  stays that way. If you believe a live read is needed to decide something,
  stop and say so in the Result rather than taking it.
- `git merge --ff-only main` first: worktrees are cut from `origin/main`.
- Both suites must be green before you call it done, with the numbers quoted:
  ambient `python -m pytest` (baseline **1362 passed, 3 skipped**) and
  `dfmcp/tests` in `.venv-dfmcp` (baseline **652 passed**). `py -3` here is a
  3.13 without pytest: use `python`.
- A pcall-guarded read that returns a default on failure is indistinguishable
  from a genuine negative. If you add one, it reports through
  `read_failures` plus `dfhack.printerr`, the pattern the creature-tag fix
  established.
- Commit after each milestone and extend the Result section as you go. No em
  dashes in prose. **No attribution lines in any commit message**: no
  Co-Authored-By, no "Generated with Claude Code".
- Stop and report on any permission or classifier refusal. Never route around
  one through another agent or session.

## Done means

The clearing rule exists in the code, is pinned by tests that would fail if it
regressed, and is written into `docs/AGENT-LOOP.md` §3 as a rule rather than an
implementation note. The Result section states the five judgement calls above
and why, quotes both suite numbers, and names exactly what a live deploy check
should look for, since someone else will run it.

## Result

(to be filled by the stream)
