# Handoff: charter-write crash fix and the Overseer's misrouted-ask charter line

Date: 2026-09-25. **Executor, Sonnet, worktree-isolated. Code, tests and one charter line only. NO deploy, no VM, no live run.**

Read `evals/live/2026-09-25-first-real-conductor-cycle/README.md` (both cycles'
findings), then `conductor/runner.py` (`write_soul`, `cleanup_workspace`, `run`),
`conductor/tests/test_runner.py`, and `agents/overseer/role.md` with `agents/consultant/role.md`.

## Fixes
1. **A failing `write_soul` must not crash the service.** In the second real cycle
   `write_soul` raised `PermissionError` (the Consultant workspace was root-owned) and
   the whole `conductor.service` process died, which under `Restart=on-failure` would
   loop. `run()` already turns a subprocess launch failure into a recorded
   `RunResult(status="launch_failed", cost_usd=None ...)`. Make a failure in
   `write_soul`, and in `cleanup_workspace`, produce the same kind of recorded failed
   run (with the exception type and message in `error`), log it at ERROR, and let the
   cycle continue with the other roles. A failed run must still not advance any
   cursor (already fixed; keep it that way and test the interaction). Add tests.
2. **Overseer charter line.** In `agents/overseer/role.md` add one short rule: the
   Overseer reads the proposal queue itself with its own tools; the Consultant is for
   questions about the game and its tools' behaviour, never about queue contents. Cite
   the finding (the Consultant has no queue-read tool and could not answer
   ask-0001). Match the file's existing voice and structure; one to three lines, no
   rewrite. If the Consultant's charter should carry the mirror line, add one line
   there too.

## Also report (do not fix)
How a charter reaches runtime: does the conductor read `agents/<role>/role.md` from its
own checkout on the VM (so a redeploy of `agents/` is needed for the charter change to
take effect) or from a pinned config directory? Cite the code path
(`conductor/config.py` `pinned_config_dir`, `charters`, wherever they are loaded) and
say exactly what must be copied to the VM for fix 2 to take effect.

## Rules
- `git merge --ff-only main` first; this brief is committed on main.
- Touched surfaces: `conductor/runner.py` and its tests, `agents/overseer/role.md`,
  `agents/consultant/role.md`. Do NOT touch `dfmcp/`, `scripts/dfhack/` (another stream
  owns them), `Working.md`, `decisions/`, `memory/`, `handoffs/INDEX.md`.
- `python -m pytest conductor` before and after; also run whatever roster/charter
  validation tests exist for `agents/` and report counts.
- No em dashes in prose. **No attribution lines in commit messages.**
- Commit after each fix. Do not push. Stop and report on any permission refusal.
- Fill in the Result section.

## Result

(pending)
