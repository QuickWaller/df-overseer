# Live deploy: wikimirror to VM 103, first real full pull

Date 2026-09-24. HEAD at merge: 68b725e (fast-forwarded from origin/main in this
worktree). User's go-ahead given this session for the deploy and for the first
real pull. **This run covers all eight steps of
`handoffs/2026-09-24-wiki-first-pull.md`.** Steps 1 to 4 ran first and this
stream stopped at step 5 (recorded below) because `DFWIKI_UA_CONTACT` had not
been supplied yet; it was then resumed with the contact value and steps 6 to 8
completed in the same worktree. The contact value used is **a public project
URL** (the repo's own GitHub URL), never a personal address; it is written
only to `/etc/dfwiki.env` on VM 103 and appears nowhere in this file or any
commit. `dfmcp-server`, `df-fortress`, `df-xvfb` and the fort itself were not
touched at any point. No timer or unit file for wikimirror was created.

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
  (readable by `dfwiki`, not world-readable): at this point only
  `DFWIKI_DB=/var/lib/dfwiki/wiki.sqlite3`. No `DFWIKI_UA_CONTACT` line yet;
  nothing committed to the repo contains it, by construction (it has never
  been typed into this session).

  **Correction applied before the real pull (step 6):** `DFWIKI_DB` was
  changed to `/var/lib/dfwiki/df-wiki.sqlite3`, the name
  `docs/CONSULTANT-WIKI.md` section 10 specifies, so a later `dfmcp-server`
  switch-over matches the design doc rather than the placeholder name used
  for the dry run. `DFWIKI_UA_CONTACT` was added, set to a public project
  URL (this repo's own GitHub URL, not a personal email), by the same
  `sudo tee /etc/dfwiki.env` pattern. Verified structurally without
  printing the value into this transcript (`grep -c` on the expected
  prefixes, both matched once each) since `scripts/vm-ssh.sh`'s host-name
  scrubber otherwise mangles anything shaped like `df-...` in its display
  output (see "anything that looks wrong" below); the file's actual sha256
  was also recorded for the record but is not reproduced here since it is
  a hash of secret-bearing content.

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

## Step 5: stop point (now resolved)

Stopped here on the first pass, per the handoff's explicit gate: `DFWIKI_UA_CONTACT`
had not been supplied to this session. Resumed later in the same worktree once
the coordinator supplied a public project URL as the contact value (never a
personal address), with the `DFWIKI_DB` correction noted above applied first.

## Step 6: the real pull, watched

Command (contact value never echoed in full here; represented as
`<contact>`, a public project URL, in this write-up only):

```
sudo -u dfwiki env DFWIKI_DB=/var/lib/dfwiki/df-wiki.sqlite3 \
  DFWIKI_UA_CONTACT=<contact> PYTHONPATH=/opt/df/wikimirror \
  /opt/df/wikimirror/.venv/bin/python -m wikimirror pull --budget 800
```

Watched start to finish (batch progress printed every 50 titles, 89 batches).
Result:

- Start: 2026-09-24T11:17:53Z. End: 2026-09-24T11:22:50Z. **Duration: 4m57s**
  wall clock (`time`: 21.1s user, 0.9s sys; the rest was politeness sleeps
  between requests, as designed).
- Game version read: `53.16`.
- **Pages stored: 4,450 of 4,450 enumerated (0 missing).**
- **Requests used: 109** of the 800 budget (13.6%).
- Chunks: 15,251. **Degraded chunks: 204, on 129 pages** (out of 4,450 -
  2.9% of pages have at least one degraded chunk).
- Unlisted templates: 292 distinct (16,869 uses) - templates referenced in
  page text but not in the (currently `ingest: false`) template namespace,
  expected per `namespaces.yaml`'s v1 design (templates are off; their
  parameters render as readable `key: value` text per
  `wikimirror/text.py`/`template_policy.yaml` rather than being expanded).
- **Pages with `section_text_lost`: 2.** Text-stage failures: 0.
- Redirects: 2,486 total (312 unresolved, 13 dangling).
- No failure at any step; nothing needed to be kept staged or resumed.
- Promotion line: `promoted to /var/lib/dfwiki/df-wiki.sqlite3; report
  /var/lib/dfwiki/df-wiki.sqlite3.pull-report.json`.

The run promoted itself (the CLI only prints "promoted to ..." after
`wikimirror/store.py`'s section-5.1 checks pass internally: page count within
1% of enumerated - here exact, 0% off; no page with a null body; `PRAGMA
integrity_check` ok; an FTS query returning rows for three known-good words;
a manifest written). Re-verified independently after the fact (step 7).

## Step 7: post-pull verification

`wikimirror status`:

```json
{
  "age_hours": 0.0034863555555555556,
  "baseline_utc": "2026-09-24T11:22:49Z",
  "chunks": 15251,
  "database": "/var/lib/dfwiki/df-wiki.sqlite3",
  "game_version": "53.16",
  "held_changes": 0,
  "last_refresh_ok_utc": null,
  "pages": 4450,
  "promotion_overdue": 0,
  "staleness": "fresh",
  "staleness_reasons": []
}
```

**DB size: 59M** (`du -h /var/lib/dfwiki/df-wiki.sqlite3`).

Independent integrity check (not just trusting the CLI's own promotion
report), run directly against the promoted file:

```
sqlite3: PRAGMA integrity_check -> ('ok',)
sqlite3: select count(*) from pages -> (4450,)
```

Direct reads proving real content, by title, with revid and a real section of
body text (not the old JSON snapshot, not a placeholder):

| title | page_id | revid | rev_timestamp | byte_length | state |
|---|---|---|---|---|---|
| Office | 31961 | 314166 | 2026-01-16T05:46:40Z | 2262 | live |
| Tomb | 32432 | 315152 | 2026-02-25T23:26:47Z | 4866 | live |

First chunk of each (heading "Introduction", text truncated to 200 chars
here for the write-up; the stored chunk is the full section):

- Office: "An office (called a study in some game menus) is a zone required
  by certain nobles and administrators. Some higher-ranking nobles require a
  "throne room" - the same thing, just fancier. You can simply..."
- Tomb: "A tomb ( / [Raw Tile: 0; 0:0:1]) is a resting place for the dead.
  "Tomb" has several meanings in the game: it can refer to a site, a
  structure, or a zone."

## Step 7b: one manual refresh run

```
sudo -u dfwiki env DFWIKI_UA_CONTACT=<contact> PYTHONPATH=/opt/df/wikimirror \
  /opt/df/wikimirror/.venv/bin/python -m wikimirror.refresh \
  --db /var/lib/dfwiki/df-wiki.sqlite3
```

Start 2026-09-24T11:23:43Z, end 2026-09-24T11:24:22Z (39s). Result:

```json
{
  "status": "ok",
  "run_id": "20260924T112343Z-s",
  "mode": "sweep",
  "requests": 20,
  "error_class": null,
  "error_detail": null,
  "sweep": true,
  "sweep_reasons": ["no_cursor"],
  "counts": {
    "promoted": 0,
    "redirects_listed": 2486,
    "redirects_written": 2486,
    "sweep_absent_candidates": 0,
    "sweep_listed": 4450
  },
  "promoted": 0,
  "unlisted_templates_top25": {},
  "unlisted_templates_total": 0,
  "degraded_reasons": {},
  "warnings": ["install_version_unset"],
  "changelog": null,
  "digest": null
}
```

`mode: "sweep"` and `sweep_reasons: ["no_cursor"]` are correct and expected:
this database has never been refreshed before (`meta.rc_cursor_ts` unset),
so `docs/CONSULTANT-WIKI.md` 4.2's forced-sweep condition applies on the
first run rather than the cheaper recentchanges feed. 20 requests, `promoted:
0` (correct: the pull that seeded the database happened seconds earlier, so
the sweep found nothing newer). `redirects_listed`/`written`: 2,486, matching
the pull's own redirect count exactly. `warnings: ["install_version_unset"]`
is a pre-existing, unrelated config note (no fort install-version binding is
configured for this refresh invocation); it did not stop the run and is not
something this stream's scope covers fixing.

## Post-checks

- `dfmcp-server`: `MainPID=962879`, `ActiveState=active`, unchanged from step
  2 and re-checked identical after the deploy, the dry run, the real pull and
  the refresh.
- `df-fortress`, `df-xvfb`: both `ActiveState=active` throughout, not
  restarted at any point.
- No `*wiki*` systemd unit files or timers exist on the VM
  (`systemctl list-timers --all` / `list-unit-files`, both empty for `wiki`).
- Disk after the full pull: DB is 59M on a volume with 16G free before any of
  this work; negligible impact.
- `python -m pytest tests/test_no_leaked_addresses.py` re-run over this
  updated file before the final commit: 19 passed.

## Anything that looks wrong

Nothing found wrong with the deploy, the dry run, the real pull, or the
refresh. Two notes, neither blocking:

1. `scripts/vm-ssh.sh`'s output scrubber masks any 4-group dot-separated
   digit sequence as `<ip>`, and separately masks anything shaped like
   `df-[a-z0-9-]+` as `<host>`. Both are working as designed but produced
   two cosmetic false positives read over SSH in this run: two of
   `wikimirror/namespaces.yaml`'s legacy game-version strings ("40d", "23a")
   displayed as `<ip>d`/`<ip>a`, and the `df-wiki.sqlite3` filename and the
   `df-overseer` contact URL both displayed as `<host>...` when `cat`'d for
   inspection. None of this is a real leaked address; it is the scrubber
   correctly erring toward over-masking anything host-shaped. The database
   filename and the repo URL are not secrets (the filename is specified in
   `docs/CONSULTANT-WIKI.md` itself and the URL is the repo's own public
   address), so this is noted only so a future reader of an SSH transcript
   from this VM does not mistake a masked display artifact for a real
   redaction of something sensitive, or vice versa.
2. `section_text_lost: 2` and `degraded chunks: 204 on 129 pages` are the
   pull's own honest accounting of pages it could not fully clean (complex
   wikitext, likely tables or nested templates) rather than a failure; 2.9%
   of pages having at least one degraded chunk, out of 4,450, is consistent
   with a first real pull against a wiki with historical formatting
   variance and was not investigated further as out of this stream's scope.

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

All eight steps complete. The mirror is promoted and live on VM 103 at
`/var/lib/dfwiki/df-wiki.sqlite3`, 4,450 of 4,450 enumerated pages stored (0
missing), 109 requests used of an 800 budget for the pull, 5.1's promotion
checks passed (verified both by the CLI's own gate and independently
afterward: `PRAGMA integrity_check` ok, page count exact, direct reads of
known pages with real revids and body text). One manual refresh ran cleanly
(sweep mode, first run, 20 requests, 0 changes found, as expected seconds
after a fresh pull). `dfmcp-server`, `df-fortress`, `df-xvfb` and the fort
were untouched throughout; no timer exists. The switch-over and timer needs
are listed above, not built.
