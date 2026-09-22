# Stream: `diff` listeners re-register on a new version, and `fort.quicksave` reports the slot it really wrote

**Written** 2026-09-22. **Status:** dispatched. **User go-ahead:** 2026-09-22,
"yes", answering "shall I have a Sonnet do the re-register and quicksave
fixes?". **Offline code, then a redeploy to VM 103, fort kept paused.**
Sonnet executor, worktree-isolated. **No push. No attribution lines in any
commit** (no Co-Authored-By, no "Generated with Claude Code").

## Why

Two findings from `handoffs/2026-09-22-loop-game-text-encoding.md` (Result;
`evals/live/2026-09-22-loop-game-text-encoding/README.md`):

1. `scripts/dfhack/df-overseer-diff.lua` registers its `eventful` listeners
   once per DF process, guarded by `_G.__df_overseer_diff_registered`. A
   redeploy never replaces them, so the live listeners are still the
   pre-encoding-fix closures: new events keep logging raw CP437 and only the
   Python backstop keeps `diff.since` working. The same trap will hit every
   future change to a listener. Fix it so a deploy takes effect without
   restarting DF.
2. `fort.quicksave` (`scripts/dfhack/df-overseer-fort.lua`) predicted
   `autosave 1` while the save landed in `autosave 2`. The conductor and the
   deploy rules trust the quicksave step, so its report must name the slot
   actually written, confirmed, not guessed.

## First

`git merge --ff-only main` in your worktree. Read `CLAUDE.md`,
`docs/TRAPS.md` (quicksave and unbounded-query traps), `memory/dfhack-environment.md`,
both scripts in full, `conductor/cycle.py`'s quicksave use, and the encoding
stream's eval README (its deploy mechanics and refusals). Check how
`eventful` stores handlers in the installed DFHack (keyed tables, e.g.
`eventful.onUnitDeath[key] = fn`, or append-only): read
`/opt/df/game/hack/lua/plugins/eventful.lua` or the local copy. Mark what
you verified versus assumed.

## What to do

1. **Version-keyed registration in `diff.lua`.** Replace the boolean guard
   with a version (a constant in the script, bumped whenever listener code
   changes, or a hash of it). If the registered version differs, replace
   every listener under the same stable keys so the old closures stop firing,
   with no duplicate handlers and without losing the existing event log or
   the id counter (the conductor's cursors depend on ids). If `eventful`'s
   storage makes clean replacement impossible, stop and report instead of
   layering handlers. Tests for the guard logic where the Lua can be
   exercised, plus a static check that the version constant exists.
2. **Log entries already in CP437.** The 13 legacy entries (first id 19)
   stay raw. Decide whether to convert them once during re-registration
   (only entries recorded by the old version, marked so, never a second
   conversion of a UTF-8 entry) or leave them to the backstop, and say why.
   Converting a UTF-8 string with `df2utf` mangles it, so any conversion
   must know which entries are raw.
3. **Quicksave slot truth.** Make `fort.quicksave`'s confirmation report the
   slot actually written, found by reading, bounded, the save directories'
   mtimes after the save (or DF's own record of the save), not a
   prediction. Keep the existing confirm-by-second-call shape the conductor
   uses; check `conductor/cycle.py` still reads the result correctly and
   update it plus its tests if the fields change. Tests.
4. Both suites green: ambient `python -m pytest` (1212 passed / 3 skipped
   before you) and `.venv-dfmcp/Scripts/python -m pytest dfmcp/tests` (630
   before). Commit before any VM work.

**VM 103** (ssh key `C:/Users/wills/.ssh/df_overseer_ed25519`, user `df`,
address from `.env` `DF_VM_IP` read by key, quotes and any `/24` stripped;
**never print it**, not even while debugging)

5. Read the fort's state (paused, tick, alive/dead). Quicksave, confirm by
   mtime. Stop if it did not land.
6. Deploy the changed files from committed bytes
   (`git -c core.autocrlf=false archive`), hash-verify, back up replaced files
   under `/opt/df/deploy-backup-2026-09-22-diff-reregister/`. Restart
   `dfmcp-server` if Python changed.
7. Trigger the re-registration with one bounded `diff.since` call. Check,
   read-only: the registered version is the new one; listeners are
   replaced, not duplicated (count them under the keys); the event log and
   next id are intact; `diff.since 0` over MCP as the conductor still
   succeeds. Real new events need game time, which this stream cannot spend:
   record "a new event logs UTF-8" as owed, checked in the first supervised
   run, with the exact command.
8. Run `fort.quicksave` over MCP as the conductor and confirm that the slot
   it reports is the one whose mtime changed.
9. Re-read the fort state: paused, same tick.

## Hard lines

- **The fort stays paused.** Never `clock.resume`, never unpause.
- No DF process restart. No unbounded query against live DFHack.
- No model call. Do not touch VM 106 or `conductor.service`.
- Secrets by key only, never printed. Never print an IP or hostname.
- Classifier refusals: follow `CLAUDE.md`; never route through another
  session.
- Do not write `Working.md`, `decisions/` or `memory/`. No em dashes.
- Commit as you go: code, then the Result section here and
  `evals/live/2026-09-22-loop-diff-reregister-quicksave-slot/README.md`.

## Touched surfaces

`scripts/dfhack/df-overseer-diff.lua`, `scripts/dfhack/df-overseer-fort.lua`,
`conductor/cycle.py` and its tests only if the quicksave fields change,
related tests under `tests/`, `dfmcp/tests/`, `conductor/tests/`, this doc,
`evals/live/2026-09-22-loop-diff-reregister-quicksave-slot/` (new); live: VM
103 `/opt/df/` scripts.

## Result

(executor fills in)
