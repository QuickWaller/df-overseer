# Handoff: one deploy command and a drift check (repo, docs, VMs, website)

Date: 2026-10-02. **Executor, Sonnet, worktree. Read-only on the VMs and
the relay; no deploys, no writes, no restarts.** The orchestrator runs the
first real deploy with what you build.

## Why

The user, 2026-10-02: drift between this repo's docs, its code, the
website and what is deployed on the VMs must stop being something they
worry about, "a systemised way, even if it costs tokens". It has bitten
already: `docs/DRIFT-AUDIT-2026-09-28.md` found files on VM 103 a week
behind the repo; CLAUDE.md's tool counts were stale for days; several
deploys were ad-hoc copies with no record of which commit is live where.

Prior art, follow its shape: GitOps (Argo CD, Flux): the repo is the
desired state, every deploy is from a commit, and a reconciler reports any
difference between desired and live ("drift"). Ansible's check mode and
Terraform plan: a dry comparison that changes nothing. Docs-as-code:
numbers a script can compute are generated, never hand-copied.

## What to build

1. **`infra/deploy-manifest.yaml`**: the single list of what goes where.
   Per target (`vm103-dfmcp`, `vm103-dfhack-scripts`, `vm106-agents`,
   `relay-web`, and any other you find in use): host id (the `vm-ssh.sh`
   target name, never an address), destination root, the repo paths or
   globs it carries, files to leave alone, services to restart after, and
   post-deploy steps (for example the gotcha store migration in
   `handoffs/2026-10-02-general-gotchas.md`'s Result). Build it from what is
   actually deployed: read `evals/live/*/README.md` deploy records, the
   handoffs' deploy steps, `web/stream/README.md`'s runbook, and read-only
   listings on each host (`scripts/vm-ssh.sh df|openclaw|relay '...'`).
   Hostnames, addresses and tokens never go in the file (public repo);
   anything secret stays in gitignored `infra/local.*`.
2. **`scripts/deploy.py`**: deploys one commit to one or all targets from
   the manifest. Refuses a dirty tree or a commit not on `origin/main`.
   Ships committed bytes only (`git -c core.autocrlf=false archive`, the
   CRLF trap in CLAUDE.md). Runs post-deploy steps, restarts the named
   services, writes a stamp on each target (`DEPLOYED_COMMIT` with the
   commit, time and manifest hash), then runs the drift check for that
   target and fails loudly if it is not clean. `--dry-run` prints exactly
   what it would copy, run and restart, and touches nothing. Write the
   code and test it offline (fakes for ssh); do not run it for real.
3. **`scripts/drift_check.py`** (read-only, safe to run any time):
   - files: sha256 of every manifest file on each target against the
     committed bytes at that target's stamped commit and at `origin/main`
     (so it can say "VM 103 is 4 commits behind" as well as "file X was
     edited in place");
   - live behaviour: per-role MCP tool lists from the running server
     against the allowlists (counts and ids), using the existing probe
     approach in the repo (find it; do not invent a second one);
   - website: the relay's page asset version and file hashes against the
     repo, and the published `tools.json`/`agents.json` against what the
     repo would generate (tool count per role, roles);
   - services: each named service active, and the conductor's
     enabled/disabled state reported (not judged).
   Output: a short human report plus `--json`. Exit non-zero on drift.
   Never prints an address (reuse `vm-ssh.sh`'s masking).
4. **Generated state, not hand-copied numbers**: `docs/STATE.md`, written
   by `python scripts/drift_check.py --write-state`: deployed commit per
   target, per-role tool counts, test counts if cheaply known, the last
   check's result and time. Then a test (`tests/test_doc_facts.py`) that
   fails when CLAUDE.md, Working.md or `agents/*/role.md` state a per-role
   tool count that differs from the allowlists. List in the Result every
   other hand-written number in CLAUDE.md that should move to STATE.md;
   do not edit CLAUDE.md yourself.
5. **A doc-audit command**: `.claude/commands/doc-audit.md`, a reusable
   brief for a Sonnet agent: read the docs (CLAUDE.md, Working.md,
   ROADMAP.md, `docs/*`, `agents/*/role.md`, READMEs) against the code and
   `docs/STATE.md`, fix plain factual drift in a commit, and list judgment
   calls for the orchestrator without changing them. It respects the
   repo's rules (register and memory are the orchestrator's).
6. **`docs/RUNBOOK-DEPLOY.md`**: how to deploy (one command), how to read
   the drift report, what to do on each kind of drift, and the standing
   cadence: drift check at session start and after every deploy; doc audit
   after every deploy and at least weekly. A scheduled daily drift check
   that alerts through the Telegram bot (`TELEGRAM_BOT_TOKEN`,
   `USER_TELEGRAM_ID` in `.env`, read by key) is wanted: write the script
   and the Windows Task Scheduler or systemd-timer instructions, but do
   not install or enable it.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early, then
  after each task.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `CLAUDE.md`.
- **Touched surfaces:** `infra/deploy-manifest.yaml`, `scripts/deploy.py`,
  `scripts/drift_check.py`, `docs/STATE.md`, `docs/RUNBOOK-DEPLOY.md`,
  `.claude/commands/doc-audit.md`, `tests/test_doc_facts.py` and tests for
  the scripts, `infra/local.example.env`. Not `web/stream/*`,
  `scripts/dfhack/TOOLS.yaml`, `dfmcp/` (other streams are editing them).
- VMs and relay: read-only commands only, through `scripts/vm-ssh.sh`.
  Read secrets by key, never a whole file. No em dashes. No attribution
  lines in commits.

## Done when

Tests green; `scripts/drift_check.py` run for real (read-only) against
every target with its report pasted into the Result (addresses masked);
`scripts/deploy.py --dry-run` output for every target pasted in; a Result
section here with what is drifted right now and anything unverified.
