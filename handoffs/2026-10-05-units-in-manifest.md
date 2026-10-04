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

## Result

### Plan (committed first)

- Layout: `infra/units/<vm-ssh target>/<unit file>`, drop-ins at
  `infra/units/<target>/<unit>.d/<name>.conf`. The target directory name is
  the `vm-ssh.sh` host name (`df`, `openclaw`, `relay`), never an address, and
  mirrors how every manifest target already names its host. One manifest
  target per host (`vm103-units`, `vm106-units`, `relay-units`), destination
  `/etc/systemd/system`, `sudo: true`.
- New manifest/deploy options (generic, data-driven): `strip_prefix` (repo path
  minus a leading prefix, so `.d/` drop-in subdirectories survive, which
  `flatten` cannot do), `stamp: false` (no `DEPLOYED_COMMIT` file inside
  `/etc/systemd/system`), `daemon_reload: true` (run `systemctl daemon-reload`
  after the copy), `unmanaged_units` (host-only unit files deliberately kept
  out of the repo, each with a reason).
- Drift check: hashes every unit and drop-in, and lists installed regular
  files at the top of `/etc/systemd/system` plus every `*.d/*.conf`; any not in
  the repo and not declared `unmanaged_units` is reported as drift
  ("untracked unit" / "untracked drop-in").
- No automatic restarts of unit targets. `daemon-reload` only re-reads
  definitions; high-risk entries (`df-fortress.service`, `conductor.service`)
  are printed as manual-only.

### Inventory (read-only, 2026-10-05)

Files were read via `base64` over `vm-ssh.sh`, because its scrubber masks every
`df-*` name to `<host>` (names recovered with `sed 's/-/_/g'` remote-side).

| host | unit | repo counterpart before | installed vs example | decision |
|---|---|---|---|---|
| df | dfmcp-server.service | infra/dfmcp-server.service.example | differs: example is a long UNDEPLOYED/CHANGEME template; installed has `After=` df-fortress, `ReadWritePaths` for dfseries/dfgotchas, `StateDirectory=dfmcp` | commit installed |
| df | stream-publisher.service | stream-publisher.service.example | installed has filled paths; the 2026-10-02 fix lives in the drop-in | commit installed |
| df | stream-publisher.timer | stream-publisher.timer.example | comment-only difference | commit installed |
| df | stream-publisher.service.d/queue-wal.conf | none (example edited to match) | host-only until now | commit installed |
| df | dfseries-import.service / .timer | dfseries-import.*.example | filled-in/comment differences | commit installed |
| df | df-fortress.service | none (provision_vm.py / install_df.py) | n/a | commit installed |
| df | df-xvfb.service | none | n/a | commit installed |
| df | df-netwatch.service / .timer | none (script is scripts/guest-capture/df_netwatch.py) | identical to the VM 106 copy | commit installed |
| df | df-stream.service / .timer | none | n/a (runs `/opt/df/stream/capture-push.sh`, not in repo) | commit installed |
| df | df-vnc.service, df-vnc-control.service, df-webvnc.service | none | n/a | commit installed |
| df | df-vnc-tunnel.service, df-vnc-control-tunnel.service | none | contain a LAN address of the relay in `ExecStart` | NOT committed; `unmanaged_units` with reason |
| openclaw | conductor.service | conductor.service.example | installed has `SupplementaryGroups=docker`, `--dry-run`, real paths; disabled and inactive | commit installed, never auto-restart |
| openclaw | df-netwatch.service / .timer | none | identical to the VM 103 copy | commit installed |
| relay | df-webvnc.service, df-webvnc-control.service | none | n/a | commit installed |
| relay | cloudflared.service, cloudflared-update.service/.timer | vendor | not project-written | `unmanaged_units` |
| relay | cloudflared-admin.service | none | embeds a live tunnel token in `ExecStart` | NOT committed; `unmanaged_units`; token needs rotating and a move to `--token-file` (see report) |

Only one drop-in directory exists on any host (`stream-publisher.service.d`).
The `*.example` files stay: they carry the design commentary and deploy
checklists; the deployable copies under `infra/units/` are the source of truth
for what is installed.
