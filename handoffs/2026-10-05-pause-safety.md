# Handoff: pause safety for unattended running (design, then build)

Date: 2026-10-05. **Executor, Sonnet, worktree. Offline build; read-only on
hosts; no unpause, no deploys.**

## Why

The goal is a conductor that runs the fort unattended. The fort can stop
itself in ways nobody is watching for: a vanilla event that self-pauses
(noble succession, 2026-09-28; `Working.md` "A fort can self-pause on a
vanilla event", `handoffs/2026-09-28-noble-succession-popup-research.md`,
`docs/TRAPS.md`), a stuck viewscreen or popup that needs a click
(2026-09-16), and a wedged command pipe that took a watchdog's own pause call
with it (`docs/AGENT-LOOP.md` around line 114).
`scripts/supervised-unpause.sh` handles one case by hand today. Read the
register first (2026-10-01 row superseding "must never move into
conductor.service", and the 2026-09-21 no-armok rows): dismissing a popup a
player could dismiss is fine; anything a player cannot do is not.

## Tasks, in order (commit after each)

1. **Inventory and design, written here before building.** Every way the
   fort can end up paused or stuck without the tripwire knowing, from the
   docs above and DFHack's own facilities (e.g. its popup or announcement
   handling, `pause_state` reads), each with: how to detect it, whether it
   is safe to clear automatically (a player could do the same), and what to
   do when it is not (stay paused, wake the Overseer, alert the human). A
   **pause watchdog** in the conductor: if the fort is paused and no
   tripwire or escalation explains it, act per the table; never unpause over
   a tripwire or an Overseer escalation. Say where each piece lives (a
   DFHack script on VM 103, a conductor check on VM 106) and what the
   conductor already does (`conductor/cycle.py` clock handling).
2. **Build** the pieces the design marks safe: a DFHack-side read that
   reports why the game is paused (popup, viewscreen, announcement, plain
   pause), a generic dismiss for popups a player can dismiss (data-driven:
   which popups are safe is a list, not branches), and the conductor
   watchdog with its decision table. Tests offline (Lua logic tests where
   the repo already has the pattern, conductor tests with fakes).
3. **Deploy plan for the orchestrator**: targets, the order, and a
   supervised live test plan (how to provoke or wait for each case safely).

## Rules

- First step: `git merge --ff-only main`. Commit your plan early.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`.
- Touched surfaces: `scripts/dfhack/` (new or extended pause/popup script,
  its TOOLS.yaml entry only if it becomes an MCP tool), `conductor/`
  (watchdog; **not** `conductor/runner.py`'s thinking code), `dfmcp/` only to
  register a new conductor-only read tool if needed (not `dfmcp/gotchas_store.py`),
  `agents/conductor/tools.yaml`, `docs/TRAPS.md`, tests. **Not** `web/stream/`,
  `dfqueue/feed.py`, `dfqueue/live.py`.
- Tools must be generalisable; no armok powers.
- Use `DF_ENV_FILE=c:/website-projects/df-automation/.env` for
  `scripts/vm-ssh.sh` (read-only); read `.env` by key only. Public repo: no
  hostnames, IPs or tokens. No em dashes. No attribution lines in commits.
- Full ambient suite and `dfmcp/tests` (in `.venv-dfmcp`) green.

## Done when

The design table, the built pieces with tests, the deploy and live-test
plan, and a Result section here.
