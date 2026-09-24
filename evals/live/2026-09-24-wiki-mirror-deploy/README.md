# Live deploy: wikimirror to VM 103, dry run of the first full pull

Date 2026-09-24. HEAD at merge: 68b725e (fast-forwarded from origin/main in this
worktree). User's go-ahead given this session for the deploy and, separately,
for the first real pull. **This run covers steps 1 to 4 of
`handoffs/2026-09-24-wiki-first-pull.md` only.** `DFWIKI_UA_CONTACT` was not
supplied, so per the handoff's step 5 this stream stops before the real pull.
`dfmcp-server`, `df-fortress`, `df-xvfb` and the fort itself were not touched.
No timer or unit file for wikimirror was created.

## Step 1: check-in

Orchestrator confirmed via `ListAgents` before dispatch that no other
df-automation session was running; this executor has no `ListAgents` tool of
its own, so it relied on that check rather than re-running it.

## Step 2: VM state read before any change

Read via `scripts/vm-ssh.sh df`, addresses masked throughout:

- Python: 3.12.3
- FTS5: present (`pragma compile_options` includes an `FTS5` entry), settling
  the "unknown" in `docs/CONSULTANT-WIKI.md` section 10 for this VM.
- Disk: 24G total, 7.9G used, 16G available, 34% used before any change.
- `dfwiki` user: did not exist before this run.
- `/var/lib/dfwiki/`: existed, owned `df:df`, contained only the old 30-page
  JSON snapshot (`snapshot.json`, 569128 bytes).
- `dfmcp-server`: runs as user `df`, `MainPID=962879`, `ActiveState=active`
  (systemd, `dfmcp-server.service`). Not restarted, not reconfigured, at any
  point in this run; its `MainPID` and `ActiveState` were re-checked identical
  after every later step.

## Step 3: deploy

- Built `git -c core.autocrlf=false archive --format=tar HEAD wikimirror`
  (committed bytes only). Local sha256 of the tar:
  `56ac916d2f1ceec81945bc6f9b2bc6f99ee5433fba3f584a71cd86c1e1b73971`.
- Copied via `scripts/vm-ssh.sh df --copy` to `/tmp/wikimirror.tar` on the VM.
  Remote sha256 matched exactly (same 64 hex digits).
- Extracted to `/opt/df/wikimirror/wikimirror/` (root, then chowned).
- Created the unprivileged system user `dfwiki` (`useradd --system
  --no-create-home --home-dir /var/lib/dfwiki --shell /usr/sbin/nologin`).
  `groups dfwiki` -> `dfwiki` only, no membership in `df`'s groups (`df adm
  cdrom sudo dip lxd`), so no group-based path to the fort's saves.
- Backed up the existing snapshot before touching the directory:
  `sudo cp -a /var/lib/dfwiki/snapshot.json
  /var/lib/dfwiki/backup-2026-09-24/snapshot.json.bak`, sha256 verified
  identical to the original both before and after (`11e63e23d5b896b2...`).
  Nothing in `/var/lib/dfwiki/` was deleted.
- `chown dfwiki:dfwiki /var/lib/dfwiki` and `/opt/df/wikimirror`;
  `chmod 750 /var/lib/dfwiki` (dfwiki and root only; the backup subdirectory
  is root-owned, `750`, for good measure).
- Built a dedicated venv, `/opt/df/wikimirror/.venv`, owned by `dfwiki`, with
  `pyyaml==6.0.3` (the same pin already verified live on this VM for
  `dfmcp/requirements.txt`; wikimirror's only third-party dependency,
  everything else in `wikimirror/*.py` is stdlib `urllib`/`sqlite3`/`json`).
  Import check: `pyyaml 6.0.3`.
- Environment file `/etc/dfwiki.env`, root-owned, mode `640`, group `dfwiki`
  (readable by `dfwiki`, not world-readable): currently only
  `DFWIKI_DB=/var/lib/dfwiki/wiki.sqlite3`. No `DFWIKI_UA_CONTACT` line yet;
  nothing committed to the repo contains it, by construction (it has never
  been typed into this session).

## Step 4: dry run

Ran as the `dfwiki` user, env supplied inline (no shell needed to source a
file), against the live public wiki:

```
sudo -u dfwiki env DFWIKI_DB=/var/lib/dfwiki/wiki.sqlite3 \
  PYTHONPATH=/opt/df/wikimirror /opt/df/wikimirror/.venv/bin/python \
  -m wikimirror pull --dry-run
```

Output:

```json
{
  "dry_run": true,
  "fetch_batches": 89,
  "namespaces": [0],
  "note": "version read and redirect enumeration are not run in a dry run; the projection counts them at their minimum. Nothing was written.",
  "pages": 4450,
  "pages_per_namespace": {"0": 4450},
  "projected_total_requests": 101,
  "requests_used_for_enumeration": 9
}
```

4,450 main-namespace pages, matching `docs/CONSULTANT-WIKI.md` 3.2's measured
figure exactly. Projected total 101 requests against the full-pull budget of
800 (12.6%), close to the design doc's own ~110-request estimate. Only
namespace 0 is ingested; `wikimirror/namespaces.yaml` on the VM (landed
byte-identical, part of the same archive) confirms template namespace 10 is
still `ingest: false` for v1, as designed. `--dry-run` writes nothing (code
path in `wikimirror/pull.py`/`__main__.py`: `plan_pull` only calls
`enumerate_pages`, no store write) and does not require
`DFWIKI_UA_CONTACT` (only a real, non-dry-run pull calls
`pull.require_contact`); it did make 9 real anonymous read requests to the
public wiki API to enumerate pages, which is within the acquisition rules in
section 3 (anonymous, read-only, well under the rate limit).

## Post-checks

- `dfmcp-server`: `MainPID=962879`, `ActiveState=active`, unchanged from step 2.
- `df-fortress`, `df-xvfb`: both `ActiveState=active`, not restarted.
- No `*wiki*` systemd unit files or timers exist on the VM
  (`systemctl list-timers --all` / `list-unit-files`, both empty for `wiki`).
- Disk after the venv build: 24G total, 7.9G used, 16G available, 35% used
  (venv + pip cache added under 1% usage).

## Anything that looks wrong

Nothing found wrong with the deploy or the dry run itself. One cosmetic note
about this write-up process, not the deploy: `scripts/vm-ssh.sh`'s output
scrubber masks any 4-group dot-separated digit sequence as `<ip>`, which also
caught two of `wikimirror/namespaces.yaml`'s legacy game-version strings
(the "40d" and "23a" namespace rows) when that file was `cat`'d over SSH for
inspection. That's the scrubber doing its job on shapes that only coincidentally
look IP-like, not a real address; those two rows' actual game-version text
should be read from the source file in the repo, not from SSH transcripts, if
it is ever needed verbatim.

## What the `dfmcp-server` switch-over and timers would still need

Not done in this run (out of scope per the handoff):

- A `MCP_SERVER_WIKI_SNAPSHOT`-style environment addition for `dfmcp-server`
  to point the Consultant's `knowledge.wiki_search`/`wiki_lookup` at
  `/var/lib/dfwiki/wiki.sqlite3` instead of (or alongside) the old
  `snapshot.json`, plus a restart of that service to pick it up, both of
  which are outward-facing-enough live changes that they should be their own
  explicitly-scoped, explicitly-confirmed step, not folded into this one.
- A refresh timer (`docs/CONSULTANT-WIKI.md` 4.2: every 6 hours, randomised
  delay) and a weekly sweep timer, both currently absent by design (this
  handoff's explicit "no timers" limit) and both needing their own unit
  files, `dfwiki`-scoped, with the same politeness/backoff budgets already
  built into `wikimirror/pull.py`/`refresh.py`.
- Read permission for whichever user runs the Consultant role's tool process
  to read `/var/lib/dfwiki/wiki.sqlite3` (currently `750`, `dfwiki`-owned);
  today `dfmcp-server` runs as `df`, which is not in `dfwiki`'s group, so a
  switch-over needs either a group grant (`dfwiki` group added to `df`, or a
  dedicated read-only group) or a copy/symlink strategy, decided deliberately
  rather than defaulted.

## Result

Steps 1 to 4 complete. Stopped at step 5 per the handoff: `DFWIKI_UA_CONTACT`
was not supplied to this session. Waiting to be resumed with it before running
step 6 (the real pull).
