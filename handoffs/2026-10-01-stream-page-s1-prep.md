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

**Plan (committed first, in case this run is cancelled):**

1. `dfqueue/feed_status.py`: a read-only equivalent of `store.project_status`
   (and a `list_project_ids`-reading helper), opening the queue db with the
   same `file:...?mode=ro` URI `feed.load_records_readonly` already uses,
   reusing `store`'s pure/private helpers (`step_status`,
   `_current_steps_and_version`, `_step_has_executed_record`,
   `PROJECT_ABANDONED`, `QueueError`) by import rather than duplicating their
   logic, since those take a plain `sqlite3.Connection` and have no write
   side effects themselves. Tests beside it.
2. `scripts/stream_publisher.py`: the publisher script. Reads
   `dfqueue.feed`/`dfqueue.feed_status` read-only, writes `data/public/` and
   `data/operator/` to a local staging dir (`feed.write_feed`, extended with
   per-project step counts from task 1), then pushes to the relay with
   `rsync -e ssh` over a restricted key. Push-on-change via a content hash of
   the staged tree, a minimum interval floor, three kill-switch checks
   (`design §4.6`: a local `PUBLIC_DISABLED` file, `public_enabled: false` in
   its own config, and never touching the automatic/Cloudflare layers, which
   are not this script's job), safe on restart (cursor file, rebuildable).
3. `infra/` examples: systemd unit + timer or `Restart=always` loop service
   for the publisher, the relay's static server config stanza (Caddy or
   nginx, loopback-bound, one block per hostname/data-root), the restricted
   `authorized_keys` line template for the push key.
4. `web/stream/README.md`: a "Slice S1: operator live" runbook section.
5. Tests for the publisher's own logic (change detection, kill switch,
   restart/cursor, and a static assertion that it never imports or calls
   anything in `dfqueue.store`'s write path).

Order: task 1 first (feed_status.py), since the publisher step needs it;
then the publisher; then infra examples and the runbook describe what task 2
produces; tests throughout, committed after each piece.

**Built, as planned, in five commits** (`bc0ae93` plan, `579ef33`
`feed_status.py`, `9379cde` the publisher, `6049d37` infra, `5ba6ff0`
the runbook). One deviation from the plan worth flagging: `infra/` task 3
ended up as a timer+oneshot service (matching `dfseries-import`'s own
existing convention) rather than a `Restart=always` loop, since
`stream_publisher.py --once` already gives a clean single-cycle entry point
and a crashed cycle under a timer never blocks the next tick the way a
long-lived loop process restarting under `Restart=always` would need extra
care to guarantee.

**`dfqueue/feed_status.py`** (`dfqueue/tests/test_feed_status.py`, 9 tests):
`project_status_readonly`, `list_project_ids_readonly`,
`all_project_statuses_readonly`. Opens the queue with the same
`file:...?mode=ro` URI `feed.load_records_readonly` uses, never
`store._connect`. Reuses `store`'s own `step_status`,
`_current_steps_and_version`, `_step_has_executed_record`,
`PROJECT_ABANDONED` and `QueueError` by import (all pure/read-only against
a plain `sqlite3.Connection`) rather than re-deriving the computation, so it
cannot drift from `store.project_status`'s own logic. Every test but the
read-only/missing-database guards asserts byte-for-byte parity against
`store.project_status` itself, built via the real writer
(`store.append`) against a throwaway db. `store.py` and `schema.py` were
read only, never edited.

**`scripts/stream_publisher.py`** (`tests/test_stream_publisher.py`, 23
tests, plus a hands-on smoke run against a seeded db -- see Verified
below): config from env/`.env`/CLI flags (same three-layer precedence
`dfmcp/server.py`'s own `ServerConfig`/`config_from_env` uses), a content
hash over items/projects/status that deliberately excludes any wall-clock
field (so "nothing changed" is a real property, not an artifact of
`published_at` always differing), the two kill switches (a file that stops
both sides outright; `public_enabled=false` that stops and `rsync --delete`s
only the public side, keeping the operator side running), a heartbeat push
floor so a quiet fort's `head.json.published_at` still proves the publisher
alive, and a JSON cursor file for restart safety (missing or corrupt costs
one extra push of identical bytes, never a crash -- tested both ways). The
real push (`_rsync_push`) is an injectable function; every test but one
supplies a recording fake instead, so no test ever shells out to a real
`rsync`/`ssh`. The one test that does not inject a fake instead makes the
on-disk queue file read-only via `os.chmod` (not just the SQLite URI mode
the module already uses) and runs a full cycle against it successfully --
the strongest available proof this script never attempts a queue write.

Also merges `feed_status`'s per-project `counts` into both projections and
`top_blocker` into the operator projection only (its `reason` is free text
a tool wrote, never for an audience, per design §3.3 item 7 -- stays private
until hold codes exist in slice S4), closing the `dfqueue/feed.py` `GAPS`
entry naming this exact deficiency.

**`infra/`**: `stream-publisher.service.example` + `.timer.example`
(oneshot + 5s timer, mirroring `dfseries-import`'s own committed pattern),
`stream-publisher-push-key-authorized-keys.example` (one `rrsync`+
`restrict` line, restricted to a single parent directory covering both
`data/public/` and `data/operator/`, with the two verification `rsync`
commands to prove the restriction holds before trusting it), a Caddy
config template (`relay-stream-caddy.example.Caddyfile`, two loopback-bound
server blocks, the operator one reachable only via the admin tunnel, and
structurally incapable of serving `/data/operator/` from the public block
since it has no such directory at all), and a new `STREAM_PUBLISHER_*`
section in `infra/local.example.env`. All placeholders
(`<relay-vm-ip>`, `CHANGEME`), all UNDEPLOYED, same header convention as
`infra/dfmcp-server.service.example`.

**`web/stream/README.md`**: a full "Slice S1: operator live" section --
what the user must approve first, the deploy order across both hosts
(generate the key on VM 103, verify the restriction on the relay BEFORE
wiring the publisher's relay variables, a manual `--once` cycle checked
by hand before the timer is ever enabled, tunnels repointed last), a
per-hop verification table, all three kill switches (including the
Cloudflare one, which stays the user's own dashboard work, decision 6 in
design §10), and rollback (disable the timer; nothing else needs undoing,
since every file either host holds is fully rebuildable from the queue).

**Verified**:
- `python -m pytest` (ambient, this worktree, no `lupa`): **2295 passed, 3
  skipped** (includes this stream's 9 + 23 new tests; CLAUDE.md's own
  1845/3 figure is from 2026-09-25 and the gap is the repo's growth since,
  not a regression -- re-ran `tests/test_no_leaked_addresses.py` on its own
  too, 19 passed, confirming none of this stream's new `infra/` files trip
  the real-address guard).
- `dfmcp/tests`, run with the **main checkout's** `.venv-dfmcp` interpreter
  against this worktree's tree (`dfmcp/` itself untouched by this stream):
  **722 passed**, 0 skipped.
- A hands-on smoke run (not part of the automated suite): seeded a throwaway
  queue db via `store.append` (one proposal, ruling, two-step project, one
  `executed` record), then ran `python scripts/stream_publisher.py --once`
  against it three times: once with no relay configured (wrote local
  `data/public/`/`data/operator/`, confirmed `head.json`/`projects.json`
  content, including the merged `counts`), once with
  `--kill-switch-file` pointed at a file that existed (both sides reported
  `"reason": "kill_switch_file"`, nothing written to an rsync target since
  none was configured anyway), and once with `--public-disabled` (ran
  clean). No real VM, relay or `rsync`/`ssh` was touched at any point.

**Not done, out of this handoff's scope**: the real safety layers 3/4
(design §7.2's write-time field refusal in `schema.py` and the publish-time
canary against real secrets) -- `dfqueue/feed.py`'s existing
`find_unsafe_pattern` withhold net is the only safety net this publisher
relies on, same as slice S0. `feed.status` (a real per-cycle fort-status
push) does not exist; `status.json` is still `feed.build_placeholder_status()`'s
placeholder (slice S2). No `seq`/`run_id` columns, so ordering is still
`rowid`/append order (slice S2).

**Deploy steps the user must approve** (the orchestrator runs these only
after explicit go-ahead; full detail and verification commands are in
`web/stream/README.md`'s new "Slice S1: operator live" section):

1. Deploy this repo's code to VM 103 (`git -c core.autocrlf=false archive`).
2. Generate the directory-restricted push key **on VM 103**
   (`infra/stream-publisher-push-key-authorized-keys.example`'s own
   `ssh-keygen` command).
3. Add the `STREAM_PUBLISHER_DB`/`STAGING_DIR`/`KILL_SWITCH_FILE` variables
   to VM 103's `.env`; install `stream-publisher.{service,timer}` but do
   **not** enable the timer yet.
4. Run one manual `--once` cycle on VM 103 (no relay variables set yet) and
   inspect the staged files by hand.
5. On the relay: create the `stream-pub` account, install `rrsync`, add the
   one `authorized_keys` line, and run the two verification `rsync`
   commands (one must succeed inside `/srv/stream/data`, one must fail
   outside it) **before** trusting the key with anything real.
6. Install Caddy from the template, loopback-bound, **without** repointing
   either Cloudflare tunnel yet; confirm with `curl 127.0.0.1:<port>/...`
   from the relay itself.
7. Fill in the eight `STREAM_PUBLISHER_{PUBLIC,OPERATOR}_RELAY_*`
   variables on VM 103, re-run the manual cycle, and confirm the relay
   actually received the push (`cat /srv/stream/data/.../head.json`).
8. Only once 6 and 7 both check out: repoint each Cloudflare tunnel's
   ingress at Caddy, and `systemctl enable --now stream-publisher.timer`.
9. Separately: confirm the admin hostname's Cloudflare Access application
   covers the whole hostname (unverified per design §11) before relying on
   it to gate the operator page the same way it gates full control today.

None of the above has been run. No live VM or relay access was used at any
point in this stream.

