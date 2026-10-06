# Handoff: conductor-executes stage T, the tripwire sequence

Date: 2026-10-06. **Executor, Sonnet, worktree. Offline build; read-only on
hosts; no deploys.** User's calls: register 2026-10-05, "the user's answers to
the revision-2 questions" items 3 and 4.

## Scope

`docs/CONDUCTOR-EXECUTION.md` revision 4, section 6.6 item T and 4.5:

- `tripwire_owners` as data in `conductor/policy.yaml`: thirst and hunger wake
  the Quartermaster; hostiles wake the Overseer until a military role exists.
  An unknown cause wakes the Overseer.
- After a tripwire the fort resumes **only** on an explicit Overseer
  `pause.verdict` with `resume: true` from that run (the same verdict path the
  unexplained-pause branch already uses, `conductor/pause_watch.py`
  `finish_after_overseer`), never on a clean run. Today's tripwire branch in
  `conductor/cycle.py` clears the latch and resumes after a clean,
  non-escalated Overseer run: that changes. The owner's run (Quartermaster for
  thirst) happens first and may file proposals; the Overseer then rules and
  gives the verdict.
- A per-cause repeat counter: the same cause re-latching N times in a window
  escalates to the human alert instead of re-running the sequence (data in
  policy). Check whether the in-game tripwire watcher has hysteresis
  (`scripts/dfhack/` clock/tripwire script, read only) and say so.
- The operator hold still suppresses every resume; a pause the watchdog owns
  is unchanged.
- Overseer charter: one line on giving the verdict after a tripwire.

## Tasks (commit after each)

1. Plan in the Result section: today's tripwire branch, exactly what changes,
   how the owner wake and the Overseer verdict sequence within one cycle.
2. Build. 3. Tests: thirst wakes the Quartermaster then the Overseer; no
   verdict keeps the fort paused and alerts; `resume: true` resumes once with
   the tick verified; `false` keeps paused; hold suppresses resume; a repeat
   escalates; hostiles wake only the Overseer. 4. Result with deploy targets
   (vm106-conductor, vm106-agents) and the live check (a forced test tripwire
   on the paused fort, described step by step for the orchestrator, not run).

## Rules

- First step: `git merge --ff-only main` (fall back to `git fetch origin &&
  git merge --ff-only origin/main`). Commit plan early and after each
  milestone.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md`, `docs/CONDUCTOR-EXECUTION*.md`.
- Touched surfaces: `conductor/cycle.py` (tripwire branch), `conductor/pause_watch.py`
  (only to reuse the verdict path), `conductor/policy.*`, `conductor/triage.py`
  if owners need it, `conductor/tests/`, `agents/overseer/role.md` (one line),
  this handoff. Not `dfmcp/` (stage 2C is building there), not `dfqueue/`,
  not `scripts/dfhack/` (read only).
- Public repo: no hostnames, IPs or tokens. No em dashes. No attribution lines
  in commits. Do not touch the live fort.
- Full ambient `python -m pytest` and `dfmcp/tests` green.

## Result

(executor fills this in)
