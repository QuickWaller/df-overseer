# Handoff: systemd unit files into the deploy manifest and the drift check

Date: 2026-10-05. **Executor, Sonnet, worktree. Offline build plus read-only
host reads; no VM writes, no deploys** (the orchestrator deploys).

## Why

On 2026-10-02 the stream publisher on VM 103 froze the public site: its unit
made the queue directory read-only, and the queue is SQLite WAL, so even a
`mode=ro` reader must create the `-shm` file beside it. The orchestrator fixed
it live with a drop-in, `/etc/systemd/system/stream-publisher.service.d/queue-wal.conf`
(`ReadOnlyPaths=` reset, `ReadOnlyPaths=/opt/df/dfmcp-smoke`,
`ReadWritePaths=/var/lib/dfmcp`), and updated
`infra/stream-publisher.service.example` to match. But unit files are not in
`infra/deploy-manifest.yaml` or `scripts/drift_check.py`, so that drop-in, and
every other installed unit, is host-only state nobody would notice drifting.
The rule since 2026-10-02 is "deploy only through `scripts/deploy.py`; never
edit files on a host directly"; this closes the gap that forced an exception.

## Tasks, in order (commit after each)

1. **Inventory, read-only.** For each host (`scripts/vm-ssh.sh df|openclaw|relay`),
   list the project's installed units, timers and drop-ins (`systemctl cat`
   shows the file paths and contents): at least `dfmcp-server`,
   `stream-publisher` (service, timer, drop-in), `df-fortress` or whatever runs
   the game, `conductor.service`, and anything else project-owned you find.
   Compare each with its `infra/*.example` counterpart. Write the table into
   this handoff. Hostnames and addresses never go in the repo: the helper
   masks them, keep it that way.
2. **Real unit files in the repo.** For each project unit, commit the exact
   installed content as a deployable file (not a `CHANGEME` example), under a
   layout you choose and justify (e.g. `infra/units/<host>/...`). Anything
   host-specific that must stay out of a public repo (an address) stays in an
   env file, never the unit. If a unit differs from its example only by
   filled-in paths, the deployable file replaces the need to hand-fill the
   example; say whether the examples should stay.
3. **Manifest and deploy.** Add the units to `infra/deploy-manifest.yaml` so
   `scripts/deploy.py` ships them (they live under `/etc/systemd/system`, so
   they need the target's `sudo` option, and a `systemctl daemon-reload` after
   copying). Restarts follow the existing low-risk / high-risk rule: never
   restart `conductor.service` or the game's unit automatically, and note that
   `conductor.service` must stay disabled and inactive. `--dry-run` must show
   the plan; do not run it for real.
4. **Drift check.** `scripts/drift_check.py` must hash installed unit files
   and drop-ins against the committed ones, and report an installed drop-in
   that the repo does not know about as drift. Regenerate `docs/STATE.md`
   (read-only check) and report what it shows.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`.
- Touched surfaces: `infra/` (units and the manifest), `scripts/deploy.py`,
  `scripts/deploy_common.py`, `scripts/drift_check.py`, `docs/STATE.md`,
  `docs/RUNBOOK-DEPLOY.md`, tests. Not `web/`, `dfqueue/`, `conductor/`,
  `scripts/stream_publisher.py`.
- Read `.env` by key only. Public repo: no hostnames, IPs or tokens. No em
  dashes. No attribution lines in commits.
- Full ambient suite green before done.

## Done when

Inventory table, committed units, a reviewed `--dry-run` plan for each new
unit target, the drift check covering units with tests, and a Result section
here.
