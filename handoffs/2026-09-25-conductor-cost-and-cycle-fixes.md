# Handoff: conductor fixes from the first real cycle (cost on timeout, cursor, Consultant wake, timeout cap)

Date: 2026-09-25. **Executor, Sonnet, worktree-isolated. Code and tests only. NO deploy, no VM, no live run.**

Read `evals/live/2026-09-25-first-real-conductor-cycle/README.md` first (it
has the findings and the evidence), then `conductor/runner.py`,
`conductor/cycle.py`, `conductor/archive.py`, `conductor/policy.yaml`.

## Fixes, in priority order

1. **Cost must be recorded, including on a timeout. The user's explicit ask:
   "i want the cost next time."** Today `RunResult.cost_usd` comes only from the
   `costUsd` field of the JSON `agent exec --json` prints on completion, and a
   timeout (runner.py, the `TimeoutError` branch) kills the process and hard-codes
   `cost_usd=0.0`, which is indistinguishable from "free" and undercounts the daily
   total. Do two things: (a) make an unknown cost `None`/unknown everywhere it is
   recorded and summed (RunResult, the archive JSON, the daily cost total in the
   log), never 0.0, with the daily total saying how many runs had unknown cost;
   (b) investigate whether the cost and the tool summary of a killed run can be
   recovered afterwards from openclaw's own session/usage records in its state dir
   (`CONDUCTOR_OPENCLAW_STATE_DIR`; read `research/2026-09-18-openclaw-capabilities.md`),
   and if it can be done reliably and read-only, do it. If it cannot, say so and
   keep (a) only. Also make sure the timeout kills the container, not just the
   `docker run` client (check the command for `--name`/`docker kill`; a leftover
   container would keep spending): verify by reading the code and test it with the
   existing fake-subprocess pattern; do not run real docker.
2. **A failed run must not advance state.** A run with `ok=False` (launch_failed,
   no_output, timeout) currently still lets the routine-review cursor
   (`__routine_review__`) advance, which silently skips the next review for 7 game
   days. Advance it only when the wake actually ran. Also check the per-role diff
   cursors for the same flaw.
3. **An open `ask` for the Consultant must wake it.** The Overseer filed
   `ask-0001` and the Consultant was not woken. `queue_state` asks are read
   (`open_ask_for_consultant`) but the plan did not wake it; find out why (policy
   data, triage, or a wake condition) and fix it, data-first per the repo's
   "policy as data" rule.
4. **The Overseer timed out at the 600 s role cap after finishing its work.**
   Determine from the archive/tool-call evidence in the README whether the cap is
   simply too tight for a multi-decision wake or whether the run lingers after its
   last write. Recommend a cap and, if it is a policy value, set it in data. Do not
   guess: cite what you found.

## Rules
- `git merge --ff-only main` first; this brief is committed on main.
- Touched surfaces: `conductor/` and its tests only. Do NOT touch `dfmcp/`,
  `scripts/dfhack/`, `wikimirror/` or `Working.md`, `decisions/`, `memory/`,
  `handoffs/INDEX.md` (another stream owns dfmcp and the Lua tools).
- Tests: `python -m pytest conductor` before and after, report counts.
- No em dashes in prose. **No attribution lines in commit messages.**
- Commit after each fix. Do not push. Stop and report on any permission refusal.
- Fill in the Result section: what changed, what you found for items 1b and 4,
  test counts, and anything you could not verify.

## Result

(pending)
