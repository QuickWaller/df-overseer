# Stream: game clock, tripwires and the `conductor` role (agent loop MVP, items 1-2)

**Written** 2026-09-22. **Status:** dispatched. **User go-ahead:** given
2026-09-22 ("go put a sonnet on those"). Offline only: **no VM, no deploy, no
model call.** Sonnet executor, worktree-isolated.

## Why

`docs/AGENT-LOOP.md` is the design; read it first, in full, especially §2
(the clock) and §3 (tripwires). In short: code, not a model, controls the game
clock. The fort runs at `base_fps` (100), is slowed to `think_fps` (10) while
an agent deliberates something time-sensitive, and pauses itself inside the
game on a tripwire. This stream builds the game-side half and the MCP role
the conductor service (a later stream) will hold.

## First

`git merge --ff-only main` in your worktree: worktrees are created from
`origin/main`, and local `main` is ahead of it with the design doc.

## Read first

`docs/AGENT-LOOP.md`; `docs/AGENT-ARCHITECTURE.md` §6 (throttling, the
`f·T + k` arithmetic, `df.global.enabler.fps`); `docs/TRAPS.md` (in
particular: the wedged command pipe that took the SSH watchdog down, no
unbounded queries against a live process, quicksave rotation and confirming
by slot mtime); `memory/dfhack-environment.md`; the `overseer-autosave`
`repeat` row in `decisions/DECISIONS.md` 2026-09-19 (in-game registration
that survives restart via `onMapLoad.init`); `scripts/dfhack/df-overseer-sampler.lua`
(the nearest existing in-game periodic script, and where vitals are read);
`scripts/dfhack/TOOLS.yaml`; `dfmcp/roles.py`, `dfmcp/auth.py`,
`agents/ROSTER.yaml`.

## What to build

1. **`scripts/dfhack/df-overseer-clock.lua`**, one tool with subcommands:
   - `set-speed FPS`: set the simulation frame cap (`df.global.enabler.fps`);
     refuse values outside a sane range; return the old and new value.
   - `pause` / `resume`: set pause state. `resume` must refuse while a
     tripwire is latched (below) unless explicitly cleared.
   - `status`: paused or not, current fps, current tick, latched tripwire (if
     any, with reason and tick), whether the watcher is armed.
   - `arm` / `disarm`: the in-game **tripwire watcher**, a periodic check
     scheduled with DFHack's in-game timers (ticks, not wall clock), cheap and
     bounded. On a trip it pauses the game and latches `{reason, tick,
     detail}` where `status` can read it. Tripwires, v1: a citizen death since
     arming; any citizen's hunger or thirst past a critical threshold; a
     hostile admitted by the same reachability logic as
     `df-overseer-threat.lua` (reuse via `reqscript`, do not copy; if that is
     too expensive per check, run it at a lower cadence and say so). Thresholds
     are arguments with defaults, not constants in code. **Source the
     hunger/thirst critical values** from DFHack/df-structures or game data and
     say where each came from; if you cannot source one, make it a required
     argument rather than guess.
   - `clear`: clear a latched tripwire (the conductor does this after the
     Overseer has handled it).
   Perception-layer rules hold: no raw coordinates in output.
2. **`fort.quicksave`**, a tool that runs `quicksave` and reports the slot
   written, confirmed by the slot's mtime changing (the rotation trap). It may
   live in the same script or its own; your call, justified.
3. **`vitals.summary`**: Tier 0 figures only (alive, dead since a tick, worst
   hunger and thirst with their thresholds, count of citizens past a warning
   level). Reuse the sampler's reads rather than writing new ones. O(1) in fort
   size in its output.
4. **Manifest entries** in `TOOLS.yaml` for each, following existing
   entries' fields; `live_deployed: false`, `verified` stating what was
   actually checked (offline) and nothing more.
5. **The `conductor` role.** `agents/conductor/` (charter, `tools.yaml`) and
   a `ROSTER.yaml` entry. It is **code, never an agent**: its token is held by
   the conductor service only. Its allowlist: the clock tool, `fort.quicksave`,
   `vitals.summary`, and read tools the briefing will need (`overview.get`,
   `queue.pending` if role scoping allows). **`dfmcp/roles.py` currently
   refuses any mutating tool to a role other than `sole_writer`.** Clock
   control mutates game state but is not a fort decision, so add a narrow,
   explicit, tested exception (for example a `clock` class of tool granted
   only to a role of a new `kind: system`), never a general loosening. The
   Overseer must **not** gain `resume`: its charter says never unpause. Token
   variable `MCP_ROLE_TOKEN_CONDUCTOR` (the existing scheme in `dfmcp/auth.py`).
6. **Tests** for everything testable offline: manifest resolution, the
   role-scoping exception (conductor may, overseer may not resume, advisors
   may not touch the clock), argument validation. Lua logic you cannot run
   offline: say so plainly, and write down the exact live checks the deploy
   stream should run.

## Touched surfaces (yours only)

`scripts/dfhack/df-overseer-clock.lua` (new; any other new
`scripts/dfhack/df-overseer-*.lua` you justify), `scripts/dfhack/TOOLS.yaml`,
`agents/conductor/` (new), `agents/ROSTER.yaml`, `dfmcp/roles.py`,
`dfmcp/auth.py` (only if needed), `dfmcp/tests/test_roles.py`, other new test
files you add, `infra/local.example.env`, this doc, its `handoffs/INDEX.md` row.

**Not yours** (other streams own them): `dfqueue/`, `dfmcp/queue_tools.py`,
`dfmcp/server.py`, `dfmcp/registry.py`, any `agents/*/` directory other than
`agents/conductor/`, `dfmcp/README.md` (put the README lines you would add in
your report instead).

## Hard lines

- No VM, no SSH, no deploy, no model call. No push.
- Do not write `Working.md`, `decisions/` or `memory/`.
- No em dashes in prose.
- **Commit after each milestone**, and extend this doc's Result section as you
  go; rate-limit deaths are routine and the next agent must be able to resume.

## Done when

Both suites pass (`python -m pytest` ambient; `dfmcp/tests` in
`.venv-dfmcp`) with the counts reported against the baseline (891 passed / 3
skipped; 537), and the Result section lists: what was built, what was verified
offline and how, what needs a live check (as exact commands), and the README
lines to add.

## Result

(executor fills in)
