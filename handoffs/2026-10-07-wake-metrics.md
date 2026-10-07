# Handoff: the wake metrics script (notebook N0, red-team corrected)

Date: 2026-10-07. **Executor, Sonnet, worktree. Offline code; read-only
live data access allowed for the validation step only.** First: `git merge
--ff-only main`.

## Why

User's call 2026-10-07: measurable methods of improvement before any
notebook. Spec: `research/2026-10-07-notebook-design.md` section 2 (metrics)
as corrected by `research/2026-10-07-notebook-red-team.md` (section 3,
"before N0" changes, and findings 2, 3, 5, 9). Also feeds the user's tool
cuts (per-role tool usage).

## Scope

- `python -m dfqueue.wake_metrics` (read-only; opens SQLite with
  `mode=ro`): M1 repeat proposals, M2 repeat defers with nothing changed,
  M3 duplicates, R, M4 rounds per wake, M5/M5b re-reads, M6 pass rate, M7
  cost/tokens, M8 rounds to first write, plus per-role tool usage counts
  (map wire names like `<server>__queue__propose` to tool ids). Grouped by
  role, by day and by deploy epoch.
- Red-team fixes: R counted only on wakes where a repeat was possible;
  cluster-aware summaries (per episode, not only per wake); M1 within role,
  M3 across roles stated explicitly; accepted-without-project handled; a
  `charter/tools/policy hash` epoch key where runs carry it, else the
  deploy list; killed runs with no cost reported, not zeroed.
- **Validation:** hand-label the 2026-10-05/06 window (the nine
  Quartermaster drink runs, proposal-0017 and -0020's triple defers, the
  duplicate rejections in `research/2026-10-07-wake-audit.md`) as a fixture,
  and report M1/M2/M3 precision and recall against it. Copy the live DBs
  read-only to a local scratch path for this (VM 103:
  /var/lib/dfmcp/Uniboslan.sqlite3 and Uniboslan.runs.sqlite3, via
  `scripts/vm-ssh.sh df` with DF_ENV_FILE=c:/website-projects/df-automation/.env
  and python3 sqlite3 backup to /tmp then scp or base64; never write the
  live files; delete the copies after). Do not commit DB copies.
- Output: a plain-text and a JSON report; a first baseline committed to
  `evals/live/2026-10-07-wake-baseline/README.md` (numbers only, no
  hostnames).
- Tests on fixture DBs.

## Rules

Touched surfaces: new `dfqueue/wake_metrics.py`, its tests and fixtures,
`evals/live/2026-10-07-wake-baseline/`, this handoff. Public repo: no
hostnames, IPs or tokens. No em dashes. No attribution lines. Commit after
each milestone. Do not write Working.md, DECISIONS.md, memory or INDEX.md.
Full ambient `python -m pytest` (lupa on PYTHONPATH) green.

## Result

(executor fills this in: validation precision/recall, the baseline numbers)
