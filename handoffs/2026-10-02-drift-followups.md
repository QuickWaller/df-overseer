# Handoff: drift system follow-ups (doc audit, daily alert, live tool check)

Date: 2026-10-02. **Executor, Sonnet, worktree.** May install one scheduled
task on this workstation (task 2). No VM writes and no deploys: the
orchestrator deploys after merging.

## Why

`handoffs/2026-10-02-deploy-and-drift-system.md` built the deploy command,
the drift check and a doc-audit brief; the first deploy through them ran
clean (`evals/live/2026-10-02-site-and-tools-deploy/`). Three follow-ups,
user's go-ahead 2026-10-02.

## Tasks, in order (commit after each)

1. **First doc audit.** Follow `.claude/commands/doc-audit.md` exactly. Known
   items to include: `web/stream/README.md` still calls slice S1 "prepared
   offline, not deployed" (it is deployed, with board, site and per-fort
   data); CLAUDE.md's status block has stale deploy and tool-count facts
   (the user parked moving fort-level facts to the site, so leave fort facts
   such as population in place, but point non-fort counts and deploy state at
   `docs/STATE.md`). Fix plain factual drift; list judgment calls in the
   Result without making them. You may edit CLAUDE.md for this task only, and
   only its status block's factual sentences; never its Rules sections.
2. **Daily drift alert.** Install a Windows Task Scheduler task on this
   workstation that runs `python scripts/drift_check_telegram_alert.py` once a
   day (09:00 local, and "run as soon as possible after a missed start" so a
   sleeping machine still checks), working directory the repo root. Use the
   instructions in `docs/RUNBOOK-DEPLOY.md`; fix them if they are wrong. Run
   the script once with `--dry-run` to prove it works from the task's
   context; do not trigger a real send. The script is silent on a clean run;
   confirm that an unreachable host also alerts rather than passing silently,
   and fix it if not. Record the exact task name and how to remove it in the
   runbook.
3. **Live tool lists.** Add `scripts/ops/mcpcall.py` (and anything it needs)
   to the `vm103-dfmcp` target in `infra/deploy-manifest.yaml` and make
   `scripts/drift_check.py` compare per-role live tool ids from the running
   server against the allowlists once it is deployed (it degrades to offline
   counts today). Read how `mcpcall.py` authenticates first; per-role tokens
   stay where they are (read by key, never printed). Test offline.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`.
- Read `.env` by key only. Public repo: no hostnames, IPs or tokens. No em
  dashes. No attribution lines in commits.

## Done when

The audit's commits and its judgment-call list, the scheduled task's name
and a `--dry-run` from it, the live-check change with tests, and a Result
section here.
