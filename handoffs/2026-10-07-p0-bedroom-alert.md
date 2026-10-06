# Handoff: P0, a bedrooms-per-citizen alert that wakes the Architect

Date: 2026-10-07. **Executor, Sonnet, worktree. Offline; no deploys.**
First: `git merge --ff-only main`.

## Why

User's call 2026-10-07: ship P0 now, before the Planner exists, so the
supervised bedroom can run. After the rooms cutover nothing wakes the
Architect to start a room. Design: `research/2026-10-07-planner-design.md`
section 7 ("Stage P0") and section 8 ("P0. Bedroom alert"); follow it.

## Scope

1. `zone.list` on `agents/conductor/tools.yaml` (one allowlist line), plus
   the conductor tool-count updates (docs/STATE.md by hand, count tests).
2. The `bedrooms_per_citizen` threshold alert in `conductor/policy.yaml` as
   the design gives it; check the read args against the real `zone.list`
   signature in `scripts/dfhack/TOOLS.yaml`, do not trust the design's args.
3. `bedrooms_per_citizen` in `lane_triggers.architect.alerts`.
4. The one code change: a generic optional per-alert `missing` default in
   `conductor/policy.py` and the alert evaluation (`conductor/briefing.py`
   `evaluate_threshold_alerts`): when the field is absent from a successful
   read, use `missing`; a failed read still drops the line. Not a bedroom
   branch.
5. Tests: zero when the key is absent; crosses below one per citizen; wakes
   the Architect once per edge (`conductor/lanes.py` `apply_alert_edges`);
   a failed read still drops the line; policy validation of `missing`.

## Rules

Touched surfaces: `conductor/policy.yaml`, `conductor/policy.py`,
`conductor/briefing.py`, `agents/conductor/tools.yaml`, `docs/STATE.md`
(conductor count only), conductor tests and the tool-count tests (another
stream is changing the Overseer count in the same count tests: change only
the conductor line), this handoff. Public repo: no hostnames, IPs or tokens.
No em dashes. No attribution lines. Commit after each milestone. Do not
write Working.md, DECISIONS.md, memory or INDEX.md. Full ambient
`python -m pytest` (lupa on PYTHONPATH) and `dfmcp/tests` in `.venv-dfmcp`
green.

## Result

(executor fills this in, including the deploy targets: vm106-conductor, and
vm103-dfmcp for the conductor allowlist)
