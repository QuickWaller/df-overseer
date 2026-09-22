# Stream: game text reaches the tools as UTF-8 (the `diff.since` CP437 crash), then redeploy to VM 103

**Written** 2026-09-22. **Status:** dispatched. **User go-ahead:** 2026-09-22,
"yeah put some sonnets on things", answering "shall I have a Sonnet do the
encoding fix (and redeploy) now, and come back before anything unpauses?".
**Offline code, then live work on VM 103, then one dry run on VM 106.** Sonnet
executor, worktree-isolated. **No push. No attribution lines in any commit**
(no Co-Authored-By, no "Generated with Claude Code": the user's instruction).

## Why

The loop MVP deploy (`handoffs/2026-09-22-loop-mvp-deploy.md`, Result;
`evals/live/2026-09-22-loop-mvp-deploy/README.md`) found that `diff.since`
crashes with `'utf-8' codec can't decode byte 0x96` on a dwarf name holding a
CP437 character, reproduced with a direct `dfhack-run` call, no MCP involved.
DF stores game text in CP437; the scripts emit it raw inside JSON, and the
Python side decodes UTF-8. The conductor's first real cycle reads
`diff.since 0` for every role, so this blocks the first start. It is not one
tool's bug: **no script under `scripts/dfhack/` calls `dfhack.df2utf`**, so
every tool that prints a name, a job, an item description, an announcement or
any other game string can hit it.

## First

`git merge --ff-only main` in your worktree. Read, in full: `CLAUDE.md`;
`docs/TRAPS.md`; `memory/dfhack-environment.md`;
`handoffs/2026-09-22-loop-mvp-deploy.md` and its eval README (the deploy
mechanics this stream repeats, the backup layout, the refusals met).
Confirm `dfhack.df2utf` exists in the installed DFHack (the local docs or
the source root on VM 103, `/opt/df/game/hack`), and how it behaves on
strings that are already ASCII. Mark what you verified against the install
versus assumed.

## What to do

1. **Find every game-text output.** Every place a `scripts/dfhack/*.lua` tool
   puts game-originated text into its output: `dfhack.TranslateName`,
   `dfhack.units.getReadableName`, item and job descriptions, announcement
   and report text, building and zone names, noble position titles, anything
   read from a `df.*` string field. List them in your Result. Strings the
   script itself writes (keys, enum names) do not need converting, but say
   how you told them apart.
2. **One shared helper, used everywhere.** Convert game text to UTF-8 at the
   source with `dfhack.df2utf`, through one helper every script uses (in the
   shared module the scripts already load, or a new one alongside it,
   deployed the same way). No per-script copies. This follows the
   generalisable-tools rule: the next tool that prints a name gets it by
   calling the helper, not by rediscovering the bug.
3. **A backstop on the Python side**, found wherever `dfmcp` turns DFHack
   output bytes into text (`dfmcp/dfhack_client.py` around
   `_decode_text_fragment_text`, and wherever else tool output is decoded):
   if a UTF-8 decode still fails, decode that output as CP437 rather than
   crashing, and log at WARNING which tool did it, so a missed call site is
   found and fixed, not silently papered over. Do not use
   `errors="replace"` for game text: it loses the name.
4. **Tests.** A regression test reproducing the exact failure (byte 0x96 in
   a name) through the Python path; tests for the backstop's warning; a test
   or static check that fails if a script emits a known game-text accessor
   without the helper (a grep-style test over `scripts/dfhack/` is fine).
   Both suites green: ambient `python -m pytest` (1202 passed / 3 skipped
   before you) and `.venv-dfmcp/Scripts/python -m pytest dfmcp/tests` (623
   before). Report the new counts.
5. **Commit** the code and tests before any VM work.

**VM 103** (live; ssh as in the deploy stream's README: key
`C:/Users/wills/.ssh/df_overseer_ed25519`, user `df`, address from `.env`
`DF_VM_IP` read by key, stripped of quotes and any `/24`, **never printed**)

6. Read the fort's state first (paused, tick, alive/dead, worst hunger and
   thirst). Quicksave, confirm it landed by the slot mtime. Stop if it did
   not.
7. Deploy the changed files from committed bytes
   (`git -c core.autocrlf=false archive`), hash-verify every file on arrival,
   back up each replaced file first under
   `/opt/df/deploy-backup-2026-09-22-encoding/`. Restart `dfmcp-server`,
   confirm active.
8. Live checks, all bounded, all read-only: the exact `dfhack-run` call that
   crashed now returns valid UTF-8 JSON and the affected name reads
   correctly; `diff.since 0` over a real MCP client as the conductor
   succeeds; every role's tool count over MCP is unchanged (overseer 60,
   architect 35, consultant 21, quartermaster 21, conductor 13); a sample of
   the other tools you changed each return cleanly.
9. Re-read the fort's state: paused, same tick.

**VM 106** (address from `.env` `OPENCLAW_VM_IP`, same handling)

10. Run the conductor `--dry-run --once` by hand **from its real initial
    cursor** (no seeded cursor this time; the deploy stream's seed was
    removed), and capture what it read, who it would wake and why, and the
    clock level it would choose. No model call, no clock change. Do not touch
    Docker group membership or the unit: a sibling stream
    (`handoffs/2026-09-22-loop-conductor-docker-access.md`) owns that.

## Hard lines

- **The fort is paused and stays paused.** Never call `clock.resume`, never
  unpause, not even briefly.
- No unbounded query against the live DFHack process (`docs/TRAPS.md`).
- No model call (`agent exec`). Do not enable or start `conductor.service`.
- Secrets by key only (`grep -E '^KEY='`), never a whole file; never print
  one, never put one in argv, a tracked file, a log or a report. Never print
  an IP or hostname, in the transcript or the repo.
- If the auto-mode classifier refuses something, follow `CLAUDE.md`'s
  refusal rule: never route it through another session; stop and report if
  it guards something irreversible or widens access.
- Do not write `Working.md`, `decisions/` or `memory/`. No em dashes.
- Commit as you go: code, then the report in this doc's Result section and
  `evals/live/2026-09-22-loop-game-text-encoding/README.md`.

## Touched surfaces

`scripts/dfhack/*.lua` and any shared Lua module they load, `TOOLS.yaml` only
if a new module needs listing, `dfmcp/dfhack_client.py` and other `dfmcp/`
decode sites, tests under `dfmcp/tests/` and `tests/`, this doc,
`evals/live/2026-09-22-loop-game-text-encoding/` (new); live: VM 103
`/opt/df/` scripts and dfmcp install, VM 106 conductor dry run (read-only).

## Report (Result section)

Every call site converted and how you found them; what you verified about
`df2utf` against the install; test counts; each file deployed and its hash
result; the backup location; fort state before and after; each live check's
result; the dry-run output; every refusal verbatim; anything still wrong.

## Result

(executor fills in)
