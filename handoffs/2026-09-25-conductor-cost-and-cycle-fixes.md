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

Tests: `python -m pytest conductor`, 178 passed before, 190 after. Nothing run against docker or a VM.

1. **Cost.** `RunResult.cost_usd` is now `Optional[float]`; `None` means unknown
   (timeout, launch_failed, no_output, bad_json, or an envelope with no numeric
   `costUsd`); a real `costUsd: 0` stays 0.0. The archive's daily total counts
   unknown runs separately (`unknown_runs`, `daily_unknown_runs`) instead of
   adding 0.0, and the per-run log line prints UNKNOWN plus the known daily
   total and the unknown count. Containers now carry `--name conductor-<role>-<id>`
   and a timeout runs best-effort `docker kill <name>`; before this, killing the
   `docker run` client left the container running and spending. The inner
   `agent exec --timeout` is now set to the role cap and the outer kill fires 60 s
   later, so openclaw can hit its own deadline first and print its envelope
   (UNVERIFIED that it does; if not, cost stays unknown).
   **1b, recovery from openclaw's records: not done.** The only recorded evidence
   (`evals/live/2026-09-14-architect-second-charter/README.md`) is that a headless
   `agent exec` persists nothing in `openclaw-agent.sqlite` (`transcript_events` and
   every transcript-shaped table had zero rows) and openclaw's aggregate
   `usage-cost` needs a running Gateway. Not re-checked on VM 106 (no VM this
   stream), so treat as "no reliable read-only source known", not proven absent.
   The tool-call side of a killed run is recoverable server-side from dfmcp's
   `tool-calls.jsonl` journal (role, tool, time), which is a separate join.
2. **Failed runs do not advance state.** `_drain_all_cursors` now only reads;
   a woken role's diff cursor commits only after an ok run, unwoken roles commit
   as before, and `__routine_review__` advances only when a role woken by
   `routine_review` ran ok. The per-role diff cursors had the same flaw (advanced
   at read time, losing a failed role's events); fixed, tripwire path included.
3. **Consultant wake.** `triage` already woke the Consultant for an open ask;
   the real cause is ordering. The queue is read once at cycle start and the ask
   was filed by an advisor during the cycle, so it could not be seen until the
   next cycle. The cycle now re-reads `queue.overview` once after the advisors
   run and wakes the Consultant (before the Overseer) for a newly open ask.
   Policy flag `consultant_rewake_after_advisors` (default true). Not done, noted:
   the same re-read could wake the Overseer for proposals filed mid-cycle; left
   alone as a cost decision.
4. **600 s cap.** The repo evidence cannot separate "too tight" from "lingers
   after its last write": the README has wall clocks (Architect 158 s, Quartermaster
   93 s, one proposal each) but no per-call timestamps for the Overseer, which
   ruled four proposals and made six failed calls. Note 600 s is also openclaw's
   own default deadline, so the two clocks raced. Set `role_timeout_seconds:
   overseer: 1200` in `policy.yaml` (per-role override, new) as a recommendation
   with headroom, flagged unmeasured. Next step: compare the Overseer's last
   tool-call time in the dfmcp journal with its wall clock.

Could not verify: the envelope on an inner-deadline timeout; openclaw state on VM 106.
