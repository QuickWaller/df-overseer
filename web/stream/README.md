# The stream page (slice S0: local only; slice S1: prepared, not deployed)

Design: `research/2026-10-01-stream-page-design.md`. This directory is the
whole "everything that can be built and seen locally with no live access"
slice (design section 8, `handoffs/2026-10-01-stream-page-s0.md`). Plain
HTML, CSS and JavaScript, no build step, no framework, no external
requests. `dfqueue/feed.py` is the data layer this page reads; read that
module's docstring and its `GAPS` list before trusting any field the page
does not show — most of what design sections 3.3 and 6 describe (a real
`seq` column, `run_id`, step labels, the season goal, hold codes, the
"right now" line's real source) is not built yet, by this slice's own
scope, and the page says so in the small note at the bottom of the layout
rather than pretending otherwise.

Slice S1 (operator live, `handoffs/2026-10-01-stream-page-s1-prep.md`) is
built and tested but **not deployed**: the real publisher
(`scripts/stream_publisher.py`), the step-progress reader it needs
(`dfqueue/feed_status.py`), and the `infra/` templates it deploys from. See
"Slice S1: operator live" below for exactly what that would take and the
deploy steps still needing the user's go-ahead.

## Open it locally

1. Export some real past queue data into this directory's `data/` folder:

   ```
   python scripts/export_stream_feed.py \
       --records evals/live/2026-09-15-overseer-first-ruling/queue-export/records.jsonl \
       --out-dir web/stream/data
   ```

   Any `queue-export/records.jsonl` under `evals/live/` works (there are
   currently two: `2026-09-15-architect-third-charter` and
   `2026-09-15-overseer-first-ruling`). Or point `--db` at a real
   `dfqueue/<fort>.sqlite3` file if you have one locally — the script opens
   it strictly read-only and never migrates or creates it.

2. Serve this directory over HTTP (opening `index.html` directly as a
   `file://` URL will fail: browsers refuse `fetch()` of local JSON from a
   `file://` page). From `web/stream/`:

   ```
   python -m http.server 8934
   ```

3. Open <http://127.0.0.1:8934/index.html> for the public page, or
   <http://127.0.0.1:8934/operator.html> for the operator page (which reads
   `data/operator/` instead and has a "Showing: Operator / Public preview"
   toggle — design section 5's move of the mockup's Public/Operator switch
   off the public page entirely).

Re-run the export script and refresh the page to see a different export;
the page polls its own `head.json` every 5 seconds while the tab is
visible, so it also picks up a re-export live without a manual refresh.

## What is real here and what is a placeholder

- **Real**: the item stream (proposals, rulings, executed steps, asks,
  answers, passes, escalations, amends, abandons — everything already in
  the queue schema), the public-text allowlist per kind, the withhold net
  for URL/address/path/token-shaped text, reply quotes and thread
  resolution, the project-to-thread map, verdict badges, segmenting into
  200-item immutable files, and the read-only export from a real
  `records.jsonl`.
- **Placeholder**: the video frame (design's live view is not embedded —
  no relay, no noVNC locally), the status strip and "right now" line
  (`feed.status` does not exist yet — design section 3.1), the season goal
  card (no goal exists), step labels and per-step progress on the Projects
  tab (design section 3.3 item 6, slice S4), the Season/chronicle tab
  (slice S7), and history scrolling past the single open segment (design
  section 4.4's segment-fetching logic is not implemented client-side yet —
  a real fort's queue is far larger than the two-record test exports this
  slice ships with, so this was not yet exercised against real segment
  files).

## Slice S1: operator live (prepared offline, not deployed)

`handoffs/2026-10-01-stream-page-s1-prep.md` built everything S1 needs
offline: the real publisher (`scripts/stream_publisher.py`), a read-only
equivalent of `dfqueue.store.project_status` it needs for step-level
progress (`dfqueue/feed_status.py`), and the `infra/` templates below.
**Nothing in this section has been run against VM 103 or the relay.** Every
command is written out exactly so the orchestrator (or the user) can review
it before running it for real, per this repo's CLAUDE.md rule that any
change to live/VM state needs explicit go-ahead each time.

### What S1 needs from the user, before any of this runs

1. **Go-ahead to deploy to VM 103 and the relay** (design
   `research/2026-10-01-stream-page-design.md` §8's own S1 row).
2. **Confirmation the admin hostname's Cloudflare Access application covers
   the whole hostname**, not just noVNC's current path (design §5,
   flagged unverified in §11) -- otherwise the operator page could be
   reachable without Access at all once it is added beside noVNC.
3. **A peer check-in** (CLAUDE.md's session-start/before-touching-a-VM
   rule) before either host is touched, independent of the go-ahead above.

### Deploy steps (for the orchestrator, after the go-ahead above)

**On VM 103** (the fort's own VM):

1. Deploy this repo's code the same way `dfmcp-server.service` already is
   (`git -c core.autocrlf=false archive`, per this repo's CLAUDE.md "traps"
   section -- this workstation's `core.autocrlf=true` otherwise ships CRLF).
2. Generate the directory-restricted push key **on VM 103**, never on the
   relay: see `infra/stream-publisher-push-key-authorized-keys.example`'s
   own header for the exact `ssh-keygen` command and path convention.
3. Add the `STREAM_PUBLISHER_*` block to VM 103's real `.env` (template:
   `infra/local.example.env`'s own "stream page publisher" section) --
   `STREAM_PUBLISHER_DB` (the live queue's real path, **outside** the code
   checkout), `STREAM_PUBLISHER_STAGING_DIR` and
   `STREAM_PUBLISHER_KILL_SWITCH_FILE` (both under
   `/var/lib/stream-publisher/`, systemd's own `StateDirectory=`, see
   `infra/stream-publisher.service.example`), and the eight
   `STREAM_PUBLISHER_{PUBLIC,OPERATOR}_RELAY_*` variables once step 5
   below exists.
4. Install `infra/stream-publisher.service.example` and
   `infra/stream-publisher.timer.example` to
   `/etc/systemd/system/stream-publisher.{service,timer}`, filling in every
   `CHANGEME` per the service file's own header checklist. **Do not enable
   the timer yet** -- first verify a single manual cycle:
   ```
   sudo -u <stream-publisher-user> \
       /CHANGEME/df-automation/.venv-dfmcp/bin/python \
       /CHANGEME/df-automation/scripts/stream_publisher.py --once
   ```
   This is safe to run with only `STREAM_PUBLISHER_DB`/`STAGING_DIR` set
   (no relay variables yet): it writes the local staging files and reports
   `"reason": "no_relay_configured"` for both sides, pushing nothing --
   confirm the staged `data/public/` and `data/operator/` look right
   (`cat <staging-dir>/public/head.json`, same shape `write_feed` produces
   locally) before any network step.

**On the relay:**

5. Create the `stream-pub` account and `/srv/stream/data` directory;
   install `rrsync` and add the one `authorized_keys` line from
   `infra/stream-publisher-push-key-authorized-keys.example`, filling in
   the real public key. **Verify the restriction before trusting it** --
   that file's own "Verify after installing" section has the exact two
   `rsync` commands (one that must succeed inside `/srv/stream/data`, one
   that must fail outside it).
6. Install Caddy (or nginx) using
   `infra/relay-stream-caddy.example.Caddyfile` as the template, filling in
   the `CHANGEME` ports and the relay's own checkout path for `web/stream/`.
   **Do not repoint either Cloudflare tunnel's ingress yet.**
7. Start Caddy bound to loopback only, and confirm **from the relay itself**
   (`curl 127.0.0.1:<public-caddy-port>/data/public/head.json` --
   if step 4's manual cycle has not pushed yet, this 404s, which is
   expected and fine) before touching the tunnels.

**Back on VM 103, now with the relay side of the key verified:**

8. Fill in the eight `STREAM_PUBLISHER_{PUBLIC,OPERATOR}_RELAY_*` variables
   in `.env` and re-run the manual `--once` cycle from step 4. Confirm it
   reports `"pushed": true` for both sides, then confirm **on the relay**
   that `/srv/stream/data/public/head.json` and
   `/srv/stream/data/operator/head.json` both exist and match what step 4
   staged locally.
9. Only once 7 and 8 both check out: repoint each Cloudflare tunnel's
   ingress from websockify's own port to Caddy's (per
   `infra/relay-stream-caddy.example.Caddyfile`'s own header), and enable
   the timer: `sudo systemctl enable --now stream-publisher.timer`.

### Verifying each hop

| Hop | How to check |
|---|---|
| Publisher reads the queue | `--once`'s own JSON summary on stdout (journald, once the timer runs): `kill_switch_active`, and `"reason"`/`"pushed"` per side |
| Local staging is correct | `cat <staging-dir>/public/head.json` and `.../projects.json` on VM 103 |
| The restricted key is actually restricted | the two `rsync` commands in `infra/stream-publisher-push-key-authorized-keys.example`'s "Verify after installing" section, run from VM 103 |
| The relay actually received the push | `cat /srv/stream/data/public/head.json` on the relay, compared to VM 103's staged copy |
| Caddy serves it, loopback only | `curl 127.0.0.1:<port>/data/public/head.json` on the relay itself; the same URL from off-host must fail until a tunnel points at it |
| The operator path never leaks publicly | confirm the PUBLIC server block's Caddyfile stanza has no `/data/operator/` `handle_path` at all (not a rule that denies it -- the absence itself) |
| End to end | load the public hostname, confirm the page polls `head.json` and shows real items; load the admin hostname behind Access, confirm it shows the operator projection including `top_blocker` text the public page never gets |

### How to stop it (all three kill switches, design §4.6)

1. **Cloudflare, from a phone** (fastest, independent of both VMs): the
   custom rule blocking `/data/public/` on the public hostname -- this is
   dashboard-only, not built by this slice (design §10 decision 6 is still
   open).
2. **The kill-switch file, on VM 103**: `touch <STREAM_PUBLISHER_KILL_SWITCH_FILE>`
   stops BOTH sides from pushing on the very next cycle (at most 5 seconds
   under the timer); `rm` it to resume. Local staging keeps being written
   either way, so nothing needs rebuilding on resume.
3. **`STREAM_PUBLISHER_PUBLIC_ENABLED=false` in `.env`, then
   `systemctl restart stream-publisher.timer`** (or just wait for the next
   tick to pick up the env change, since `EnvironmentFile=` is re-read per
   invocation under a `oneshot` unit): stops and clears only the public
   side (`rsync --delete`), keeps the operator side running. Flip back to
   `true` to resume.

### Rolling back

Disable the timer (`sudo systemctl disable --now stream-publisher.timer`);
nothing else needs undoing -- the publisher never wrote to the queue, and
every file it ever wrote (locally or on the relay) is fully rebuildable
from the queue at any time (design §4.1's own "given the same records the
publisher writes the same bytes"). If the Cloudflare ingress was already
repointed at Caddy (deploy step 9), repoint it back at websockify's own
port to fully revert the relay's public surface to pre-S1 shape.

## Known gaps in this slice, beyond `dfqueue/feed.py`'s own `GAPS` list

- No JS test suite for `app.js` — `dfqueue/tests/test_feed.py` covers the
  data layer thoroughly (that is where the safety-relevant logic lives:
  the allowlist and the withhold net); the rendering layer is exercised
  manually per the steps above, not automated. A future slice could add a
  headless-browser smoke test if that seems worth the dependency.
- No closed-segment or season-file fetching client-side (see above).
- No focus-trapping project drawer — the Projects tab lists cards but does
  not open the mockup's full drawer with a step timeline and its own
  conversation thread; that needs step labels and target counts
  (`dfqueue.store.project_status`, not available to a read-only-records
  reader — see `dfqueue/feed.py`'s own `GAPS`).
- No dark/light theme switch (the design says the video frame stays dark
  regardless; the chrome could follow `prefers-color-scheme`, not wired up
  here).
- Accessibility: role names are always shown as text (never colour alone),
  and new items announce politely via `aria-live="polite"` on the messages
  list, but this has not been tested with a real screen reader.
