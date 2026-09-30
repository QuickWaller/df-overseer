# Handoff: stockpile writing (place, configure, link)

Date: 2026-10-01. **Executor, Sonnet, worktree. Offline code only, no live
access** (the orchestrator live-verifies after merge).

## Why

The minimal starting point (register 2026-10-01): the agents run the fort one
game year hands-off. Today they can only read stockpiles
(`scripts/dfhack/df-overseer-stockpile.lua`: `list`, `links`). Without
writing, food spoils, hauling stalls and refuse piles up. Principle (register
2026-09-30): set intent, let the game execute; a stockpile's settings and
links are exactly the native lever DF gives a player.

## Tasks, in order (commit after each)

1. **Mechanism, from DFHack `53.16-r1` source** (GitHub `DFHack/dfhack`:
   quickfort `#place` mode and its stockpile settings syntax,
   `plugins/stockpiles` and its Lua API, `library/modules/Buildings.cpp` for
   links). Answer with file and line: how a script places a stockpile of a
   given size; how its accepted categories (and finer settings) are set;
   whether presets exist and what they cover; how give/take links to a
   workshop or another stockpile are written. Say "unverified" where source
   does not settle it.
2. **`stockpile.place`**: KIND-free and generalisable: size W H, level,
   `NEAR_LANDMARK`, rank and radius like every other finder (reuse
   `df-overseer-openarea.lua`'s finder rather than a new one; skip reserved
   ground via `df-overseer-reservations.lua`'s `filter_reserved`), the
   categories to accept as an argument, `DRY_RUN` default true, `RES_ID` and
   `OVERRIDE` exactly as the other designating tools take them.
3. **`stockpile.configure ID CATEGORIES`**: change what an existing pile
   accepts. **`stockpile.link ID TARGET_ID give|take`** and **`unlink`**: to
   a workshop or pile, by id. Both `DRY_RUN` default true.
4. Reports state what the game now holds (read back), not what was asked.
5. `TOOLS.yaml` entries (mutating commands tagged as the others are), and
   tests in the existing lupa style. Note plainly what the stub cannot prove
   (the offline fake world has disagreed with the real API twice).

## Rules

- First step: `git merge --ff-only main`. Commit your plan early, then after
  each task; agents here get cancelled mid-run.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`, or any
  `agents/*/tools.yaml` (the orchestrator grants roles after merge; say in
  the Result which role should get which command).
- No em dashes in prose. No attribution lines in any commit.
- Generalisable, no armok capabilities, never a rendered map (`CLAUDE.md`).
- Tests: ambient `python -m pytest`, and `dfmcp/tests` with the main
  checkout's `.venv-dfmcp`; report both counts.
- Stop and report on any permission refusal.

## Touched surfaces

`scripts/dfhack/df-overseer-stockpile.lua`, `scripts/dfhack/TOOLS.yaml`,
tests and lua stubs. Read-only use of openarea and reservations.

## Result

(fill in, about 200 words)
