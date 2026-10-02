# Deploy and drift: the runbook

Built 2026-10-02 (`handoffs/2026-10-02-deploy-and-drift-system.md`), after
drift between this repo's docs, its code, the website and what is actually
deployed on the VMs had bitten three separate times
(`docs/DRIFT-AUDIT-2026-09-28.md`, stale tool counts in `CLAUDE.md`, several
ad-hoc deploys with no record of which commit went where). See that file's
"Why" section for the prior art this follows (GitOps reconciliation,
Terraform/Ansible dry-run, docs-as-code).

## The one command

```
python scripts/deploy.py --target <name> --dry-run   # ALWAYS safe, review this first
python scripts/deploy.py --target <name> --yes       # the real thing, after review
python scripts/deploy.py --all --dry-run             # every target in infra/deploy-manifest.yaml
```

Target names come from `infra/deploy-manifest.yaml`: `vm103-dfmcp`,
`vm103-dfhack-scripts`, `vm103-stream-publisher`, `vm106-agents`,
`vm106-conductor`, `relay-web`, `relay-web-operator`, as of this writing.

`deploy.py` refuses to run for real (`--yes`) when:

- the working tree is dirty;
- the commit being deployed is not an ancestor of `origin/main` (deploy
  ships a reviewed, pushed commit, never a local-only one);
- a target names a `risk: high` restart (`conductor.service`,
  `df-fortress.service`) -- it copies the files and PRINTS the manual
  restart command plus the doc to read first, but never runs it. Restarting
  `df-fortress.service` reloads the live game process and carries real
  save-state risk (`docs/ARMOK-RULINGS.md`, `decisions/DECISIONS.md`
  2026-09-16's own procedure: quicksave, verify the slot by mtime, back it
  up, THEN restart, THEN confirm identity after). Restarting
  `conductor.service` is the one role allowed to pause/resume/quicksave the
  fort (`kind: system`, `agents/ROSTER.yaml`) and enabling it is a decision
  this repo's rules reserve for the user, not a deploy side effect.

After a real deploy, `deploy.py` writes a `DEPLOYED_COMMIT` stamp at the
target's destination and is meant to run `drift_check.py` for that target
immediately after (treat a dirty result as the deploy having failed, even
though the copy succeeded).

**Always read `--dry-run`'s output before a real deploy.** It lists every
file that would move, the stamp it would write, which services would
restart, and which high-risk ones it would refuse. Per `CLAUDE.md`'s "treat
git push and any deploy as outward-facing, needing explicit go-ahead each
time" rule, a real `--yes` run is never something to run without that
go-ahead, regardless of what an earlier session was told.

## Reading a drift report

```
python scripts/drift_check.py                 # every target, human report
python scripts/drift_check.py --target NAME    # one target
python scripts/drift_check.py --json           # machine-readable
python scripts/drift_check.py --write-state    # also regenerates docs/STATE.md
```

Entirely read-only (listings, `cat`, `sha256sum`, `systemctl show`), safe to
run any time, including by a human just checking. Four sections:

1. **Files**: `[clean]` or `[DRIFT]` per target, with per-file status
   (`match` / `differ` / `missing_on_host`). If the target has no
   `DEPLOYED_COMMIT` stamp yet (nothing has ever run `deploy.py --yes`
   against it), it compares against `origin/main` instead and says so --
   this is normal for a target that predates this tooling, not itself a
   finding.
2. **Live tool counts**: the repo's own registry + roster, computed
   offline, cross-checked against a live MCP probe (`scripts/ops/mcpcall.py`)
   when one is actually deployed on the host. As of 2026-10-02 it is not
   part of any manifest target, so this degrades to "offline count only" --
   see "Known gaps" below.
3. **Website**: the relay's static files, and the published
   `tools.json`/`agents.json` against what `dfqueue.site_data` would
   generate from the repo right now.
4. **Services**: active/enabled state for every named service, reported,
   never judged. `conductor.service` showing `inactive`/`disabled` is the
   documented state (`CLAUDE.md`'s status block), not a finding by itself.

### What to do on each kind of drift

| Finding | What it means | What to do |
|---|---|---|
| `differ` on a file | The live file's bytes don't match the compared commit | If compared against a stamp: redeploy that target. If compared against `origin/main` (no stamp): the host was likely touched by an ad-hoc deploy before this tooling existed -- decide whether to adopt the live bytes or overwrite them with a real deploy, don't assume automatically |
| `missing_on_host` | The manifest lists a file the host doesn't have under the path this tool expected | Check whether the manifest's path assumption is simply wrong before assuming a failed deploy (this happened twice building this tool itself -- see the Result section of the handoff that built it) |
| N commits behind `origin/main` | The target's stamped deploy predates N later commits to its own files | Redeploy if those commits touch this target's paths; otherwise informational |
| live tool count mismatch | The offline count (repo) disagrees with a live MCP probe | Redeploy `vm103-dfmcp` and restart `dfmcp-server.service` |
| service inactive/disabled | Exactly what it says, not evaluated | Compare against what the relevant doc SAYS the state should be; a mismatch there is a doc-audit finding, not a drift_check one |
| website `tools.json` mismatch | The relay's published counts disagree with what the repo would generate | Check whether `stream-publisher.timer` has actually run since the last relevant commit; redeploy `vm103-stream-publisher` if its code is what's stale |

## Standing cadence

- **Drift check at session start** (alongside the existing peer-check-in
  rule in `CLAUDE.md`) and **after every deploy**.
- **Doc audit** (`/doc-audit`, `.claude/commands/doc-audit.md`) **after
  every deploy and at least weekly** regardless.
- A number that keeps needing hand-correction belongs in `docs/STATE.md`
  instead of prose -- see `tests/test_doc_facts.py` for the one place this
  is mechanically enforced today (the "Role tool lists" sentence in
  `CLAUDE.md`/`Working.md`), and the handoff's Result section for every
  other hand-written number that should probably move there too.

## Daily drift check with a Telegram alert (written, NOT installed)

`scripts/drift_check_telegram_alert.py` runs `drift_check`'s full report and
sends ONE Telegram message to the user's existing private line
(`TELEGRAM_BOT_TOKEN` + `USER_TELEGRAM_ID` in `.env`, register 2026-10-01)
only when drift is found -- silent on a clean day. Written and tested
offline only; this stream did not install or enable it, per its own
"never deploy or install anything" constraint.

```
python scripts/drift_check_telegram_alert.py --dry-run   # preview the message, no send, no credentials needed
python scripts/drift_check_telegram_alert.py              # real run, needs both env vars set
```

To actually schedule it, a human runs ONE of the following (both outward
facing -- do not run either without deciding to, same as any deploy):

**Windows Task Scheduler** (this workstation, where `.env` and the repo
checkout already live):

```
schtasks /Create /SC DAILY /ST 08:00 /TN "df-overseer-drift-check" ^
  /TR "\"C:\Program Files\Git\bin\bash.exe\" -lc \"cd /c/website-projects/df-automation && python scripts/drift_check_telegram_alert.py\""
```

**systemd timer** (if run from a Linux host instead -- e.g. VM 103 itself,
which already has a working `.venv` and reaches every target this checks):
copy the pattern from `infra/stream-publisher.timer.example` and
`infra/stream-publisher.service.example` (`OnCalendar=daily` in the timer;
`ExecStart=<venv>/bin/python scripts/drift_check_telegram_alert.py` in the
service, `EnvironmentFile=` pointing at a `.env` with the two Telegram
variables set, same pattern as `stream-publisher.service`'s own
`EnvironmentFile=/etc/stream-publisher/env`).

Either way: run the `--dry-run` form by hand first and confirm the message
looks right before enabling the schedule.
