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

Done. `dfqueue/wake_metrics.py` (CLI `python -m dfqueue.wake_metrics` and the
pure `compute(queue_db, runs_db, since=None, until=None, roles=None,
epochs=None) -> dict`), `dfqueue/wake_epochs.yaml` (hand-kept deploy epochs,
used only while runs carry no charter/tools/policy hash; none do yet),
`dfqueue/tests/test_wake_metrics.py` (23 tests) with
`dfqueue/tests/fixtures/wake_window_2026_10_05.json` (the real window, trimmed,
plus hand labels), baseline in `evals/live/2026-10-07-wake-baseline/`
(README, `metrics.json`, `per_wake.jsonl`). Full ambient suite: 3473 passed,
3 skipped.

**Validation (13 proposals and the rulings, 2026-10-05..07, hand labels in the
fixture).** M3 precision 1.00, recall 1.00 (2 of 2). M2 precision 1.00, recall
1.00 (5 of 5; needs no epoch boundary between the two defers, so the seeded
epoch list holds only the 2026-10-05 lane change). **M1 text (the server's own
rule): 0 flagged of 5 true, recall 0.** The roles paraphrase every wake. M1-wide
(signal and operator): precision 0.50, recall 0.80. New M1-struct (same signal
and operator and mostly the same precondition landmarks): precision 0.57,
recall 0.80, fitted on this window so optimistic. Consequence for N1: use M2
and M3 as R's reliable parts and a hand-labelled or M1-struct repeat count.

**Baseline** (24 wakes, 3 days, hand-run `--once` sweeps; only 3 wakes have a
transcript): R 7 (5 repeat defers, 2 duplicate rejections) over 18 at-risk
wakes, 0.33 per at-risk wake, 1.75 events per episode; overseer 1.25 per
at-risk wake, quartermaster 0.11, architect 0. Mean cost 0.051 USD over 22
costed wakes (2 architect timeouts reported as killed, no cost). Power
projection for a 50% cut in R: about 203 at-risk wakes per arm, about 68 days
at this volume. Redundant re-reads 0 of 62 read calls in the 3 transcribed
wakes. Wire names mapped with 0 unmapped calls on run-0022, -0023, -0024.
Findings worth routing: `runs.cycle` is 1 on every `--once` run so it cannot
cluster; the module derives a sweep (runs less than 120 s apart); M2 cannot see
an ask about a proposal because asks carry no `proposal_id`; the 0.5 Jaccard
landmark rule links a barrel proposal to the drink one (precision cost).

**Published schema `wake_metrics/1`** (for the Board stream; documented in the
module docstring, additions are non-breaking, bump the integer on breaking
changes). Top-level keys: `schema`, `generated_at`, `since`, `until`,
`definitions` (fixed one-line texts), `totals`, `by_role {role: group}`,
`by_day {YYYY-MM-DD: {role: group}}`, `by_epoch {epoch_id: {role: group}}`
(sorted keys, chart-ready series), `episodes {role: events, episodes,
events_per_episode}`, `interval {role: r_per_at_risk_wake: mean, lo90, hi90,
clusters}` (bootstrap by sweep, seed fixed), `power`, `tool_usage {role:
wakes_with_transcript, calls {tool_id: n}, unmapped_calls, never_called}`,
`wakes [per-wake row]`, `unattributed`, `notes`. A group holds counts (`wakes`,
`killed`, `at_risk_wakes`, `m1`, `m1_wide`, `m1_struct`, `m2`, `m3`,
`m3_cross_role`, `r`), rates (`r_per_wake`, `r_per_at_risk_wake`,
`reread_rate`, `pass_rate`), `{n, mean, median, sum}` summaries (`cost`,
`rounds`, `rounds_to_first_write`, `orientation_reads`), `tokens`,
`with_transcript`, `truncated`. A per-wake row holds `run_id`, `role`, `day`,
`epoch`, `wake_reason` (conductor keyword), `sweep`, `status`, `killed`,
`at_risk`, the counts, `cost_usd`, `rounds`, `first_write_round`, `read_calls`,
`redundant_reads`, `tokens`, `passed`, `source`. Every string is an id, role,
day, keyword or tool id; no tool arguments or results, proposal text, ruling
reasons or thinking. A test asserts this over a populated report.
