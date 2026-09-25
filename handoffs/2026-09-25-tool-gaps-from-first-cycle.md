# Handoff: tool gaps from the first real cycle (workjob container reagent, positional arguments)

Date: 2026-09-25. **Executor, Sonnet, worktree-isolated. Code and tests only. NO deploy, no VM, no live game call.**

Read `evals/live/2026-09-25-first-real-conductor-cycle/README.md` first, then
`scripts/dfhack/df-overseer-workjob.lua` (around lines 410-440, the wildcard
refusal), `dfmcp/tools.py` (around line 827, the "cannot supply" refusal), and
this repo's `CLAUDE.md` rules "Tools must be generalisable" and "No armok
capabilities".

## Fixes

1. **`workjob.queue` cannot queue brewing (and any reaction with a tag-matched
   container reagent).** The three brew reactions carry a wildcard "empty food
   storage container" reagent (`item_type == -1`), which the tool refuses to
   guess, so the Overseer's accepted brew proposal could not execute and drink
   stays 0. Make it work **generally, not for brewing only** (the repo rule): the
   tool should be able to take the concrete item (or pick from candidates the
   game's own data offers, reporting which it chose and why) for any wildcard
   reagent, with per-reagent policy in data, not branches. It must use only what a
   player could do (choose an existing empty barrel or pot); no item creation.
   Keep the existing safe default (refuse rather than guess silently) as the
   behaviour when no choice is given, and make the refusal say exactly what
   argument would resolve it.
2. **Positional optional arguments cost the Overseer six failed calls.** The MCP
   layer refuses "cannot supply `dry_run` without also supplying the earlier
   optional argument `level`" (`dfmcp/tools.py`), because the DFHack CLI is
   positional. Let an agent supply optional arguments by name in any combination:
   fill skipped earlier optional slots with the tool's own documented defaults
   (declared in data, not guessed in code), and refuse only when a skipped slot
   has no declared default. Read `TOOLS.yaml` for how arguments and defaults are
   declared; extend that data rather than special-casing tools. Every currently
   working call must behave identically.

## Rules
- `git merge --ff-only main` first; this brief is committed on main.
- Touched surfaces: `scripts/dfhack/df-overseer-workjob.lua`, `scripts/dfhack/TOOLS.yaml`
  entries you must change, `dfmcp/` (server side of item 2) and their tests. Do NOT
  touch `conductor/` (another stream), `wikimirror/`, `Working.md`, `decisions/`,
  `memory/`, `handoffs/INDEX.md`.
- Tests: ambient `python -m pytest` (a `lupa` install on PYTHONPATH per `CLAUDE.md`
  makes the Lua-logic tests run) and `dfmcp/tests` in `.venv-dfmcp`; report counts
  before and after.
- Do not call the live fort. Verify with the repo's offline test patterns; say
  plainly what is only verified offline and needs a live check after deploy.
- No em dashes in prose. **No attribution lines in commit messages.**
- Commit after each fix. Do not push. Stop and report on any permission refusal.
- Fill in the Result section: what changed, test counts, what needs a live check.

## Result

Branch `worktree-agent-aa7c31b8951b82735`, two commits, not pushed, nothing deployed, no live call.

**Fix 2 (named optionals), commit 2cdb6b0.** TOOLS.yaml gained script-level `arg_defaults` (per-command `defaults` overrides), a quoted map of optional placeholder to its documented default (LEVEL 0, RANK 1, RADIUS_TILES 30, DRY_RUN true, REPEAT false, COUNT 1, VERSION minimal, AROUND_FURNITURE false), each checked against the Lua's own `x or default`. `dfmcp/registry.py` parses and validates it (`Tool.defaults`); `dfmcp/tools.py` `argv_for_call` fills a skipped optional that precedes a supplied one from it, and still refuses (now saying no default is declared) when there is none (zone.place OWNER; blueprint LEVEL/RANK/RADIUS are deliberately not declared, since the Lua treats a non-nil value there differently). Calls that worked before are unchanged (nothing is filled unless a later optional is supplied). Four tests that pinned the old refusal now pin the fill.

**Fix 1 (wildcard reagent).** `queue` gained a trailing `[REAGENT_CHOICE...]`: `N:ITEM_ID` or `N:auto`. Candidates are free fort items satisfying every flag on the reagent, decided by a per-flag check table in the Lua (empty, food_storage): data, one entry per new tag. A flag with no check is refused, never guessed. The chosen item's type/subtype narrows the job_item and the result reports chosen id and why. No choice still refuses, now naming the exact words to pass plus candidates. `list-jobs` shows wildcard candidates.

**Tests.** Ambient (lupa on PYTHONPATH): 1848 passed 3 skipped before, 1860 passed 3 skipped after. dfmcp/tests: 692 before, 695 after. New: `tests/test_workjob_wildcard_lua_logic.py` (9, fake world).

**Live check owed after deploy:** the real item flags and `isFoodStorage`/`getContainedItems` reads; that DF accepts a job_item narrowed to a barrel/pot type with the recipe's flags and the brew job actually runs (only type/subtype is pinned, not the instance); list-jobs on the Still; the MCP server needs redeploy for fix 2, the fort for fix 1.
