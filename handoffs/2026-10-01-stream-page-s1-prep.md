# Handoff: stream page slice S1, prepared offline (publisher and operator view)

Date: 2026-10-01. **Executor, Sonnet, worktree. Offline only: build and test
everything S1 needs, deploy nothing.** The orchestrator deploys after the
user's go-ahead.

## Why

S0 is merged (`web/stream/`, `dfqueue/feed.py`). S1 (design
`research/2026-10-01-stream-page-design.md` §4, §5, §8) puts the operator
view live: a read-only publisher on VM 103 pushing the operator and public
JSON outward to the relay, served beside the existing viewer, the operator
page on the existing admin address behind the user's Cloudflare Access
login (register 2026-10-01 rows: hosted on the relay; operator page on the
admin address; run detail kept 90 days).

## Tasks, in order (commit after each)

1. A publisher script (name it in repo idiom): runs on VM 103 under
   systemd, reads the queue read-only (as `feed.py` does), writes the
   projections to a local staging folder, and pushes them outward to the
   relay with `rsync` over a key restricted to one directory (`rrsync` or a
   forced command; design §4). Push on change, a minimum interval, a kill
   switch file that stops all publishing, safe on restart. Also a read-only
   equivalent of `dfqueue.store.project_status` for step-level progress
   (S0's named gap), in a new module, without touching `store.py`.
2. `infra/` examples: the systemd unit, the relay's static server config
   for the page beside the viewer (loopback, behind the existing tunnel),
   the restricted key's `authorized_keys` line template; placeholders only.
3. A runbook in `web/stream/README.md`: exact deploy steps for VM 103 and
   the relay, how to verify each hop, how to stop it (all three kill
   switches from design §4.6), how to roll back.
4. Tests for the publisher (change detection, kill switch, restart, never
   writing to the queue).

## Rules

- First step: `git merge --ff-only main`. Commit your plan early, then
  after each task; agents here get cancelled mid-run.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `dfqueue/schema.py`, `dfqueue/store.py` or anything under `conductor/`.
- This repo is public: placeholders only for hosts, addresses, keys and
  remote paths (`<relay-vm-ip>` style, as in `infra/`).
- No em dashes in prose. No attribution lines in any commit.
- Tests: ambient `python -m pytest` and `dfmcp/tests` with the main
  checkout's `.venv-dfmcp`; report both counts.
- Stop and report on any permission refusal.

## Touched surfaces

A new publisher script, `infra/` example files, `web/stream/README.md`, a new
read-only module beside `dfqueue/feed.py`, tests.

## Result

(fill in, with the deploy steps the user must approve)
