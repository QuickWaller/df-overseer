# The stream page (slice S0/S2: local only; slice S1: prepared, not deployed)

Design: `research/2026-10-01-stream-page-design.md`. The board's look is
`research/2026-10-02-stream-board-mockup.html` (option E, split layout;
register 2026-10-02 "Stream page look"; built per
`handoffs/2026-10-02-stream-board.md`). This directory is the whole
"everything that can be built and seen locally with no live access" slice
(design section 8, `handoffs/2026-10-01-stream-page-s0.md`). Plain HTML,
CSS and JavaScript, no build step, no framework, no external requests
(except Google Fonts for JetBrains Mono, with a system-monospace fallback
if that request is blocked). `dfqueue/feed.py` and `dfqueue/feed_status.py`
are the data layer this page reads; read `feed.py`'s docstring and its
`GAPS` list before trusting any field the page does not show — a real `seq`
column, `run_id`, the season goal, and the "right now" status line's real
source are still not built, and the page says so in its own gaps note
rather than pretending otherwise. Step labels, public titles/rationales,
urgency and hold codes (design §3.3 items 6/7) ARE read now, with the exact
honest fallback named in each case (see "What is real" below).

## Multiple forts

The published data is organised per fort (register 2026-10-02, "plan for
more than one fort"): `<out-dir>/public/forts.json` lists every fort a
given export root has ever been given (`id`, `name`, `status` — `live` or
`lost` — `current`), and each fort's own feed lives under
`<out-dir>/public/forts/<fort-id>/` (`head.json`, `open.json`,
`projects.json`, `status.json`, `seg/`, `seasons/` — the same shape
`dfqueue.feed.write_feed` always produced, just no longer at the root). The
page reads `forts.json` first and follows whichever fort is marked
`current`; it never hard-codes a fort id. `dfqueue.feed.fort_feed_dir`,
`build_forts_index`, `read_forts_index`/`write_forts_index` and
`write_fort_feed` (the one call `scripts/export_stream_feed.py` makes) are
the whole of this layer — see their docstrings in `dfqueue/feed.py`.
Project-wide data that is not any one fort's (agents, tools, known gotchas)
has no home built yet, but belongs at `<out-dir>/public/`, a SIBLING of
`forts/`, never inside it — this layout already leaves that room.

If `forts.json` is missing (an older export, before this existed), the page
falls back to treating the projection root itself as one fort's feed
directly — the pre-multi-fort layout — rather than failing to load.

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
   `2026-09-15-overseer-first-ruling`), or
   `web/stream/fixtures/board-demo.jsonl` (hand-built, covers every board
   state: done, active, waiting/ready, on hold with a hold_code, an amended
   plan with an added step tagged `v2`/`v3`, and a turned-down proposal —
   not run through `store.append`, since this is a plain `records.jsonl`,
   same convention `dfqueue/tests/_helpers.py` uses). Or point `--db` at a
   real `dfqueue/<fort>.sqlite3` file if you have one locally — the script
   opens it strictly read-only and never migrates or creates it.

   The export names a fort (see "Multiple forts" above): `--fort-id`
   defaults to the `--db` file's own stem, or `uniboslan` for a `--records`
   export; override it, and `--fort-name`/`--fort-status` (`live`/`lost`),
   with explicit flags.

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

- **Real**: the board (split layout, Under way/On hold/Done/Turned down,
  a card's mini job graph and "N of M steps" label, urgency pill, the
  details panel's full job graph with dependency edges, done/active/ready/
  waiting/hold states, `v2`/`v3` tags on an amendment's added step, and the
  conversation grouped by game day), both themes (Terminal 2 default, Stone
  2 behind the header toggle, remembered in `localStorage`), multiple forts
  (`forts.json`, see above), the item stream (proposals, rulings, executed
  steps, asks, answers, passes, escalations, amends, abandons), public
  titles/rationales/urgency/step labels/hold codes when the Overseer wrote
  them (with the named fallback below when it did not), the public-text
  allowlist per kind, the withhold net for URL/address/path/token-shaped
  text, reply quotes and thread resolution, the project-to-thread map,
  verdict badges, segmenting into 200-item immutable files, and the
  read-only export from a real `records.jsonl`.
- **Honest fallbacks, not placeholders** (handoff item 7): a project's
  board name falls back to its own `summary`, truncated, when no
  `public_title` was written; a step's label falls back to its tool id,
  humanized, when it has no `label`; a project with no urgency written (or
  an unrecognised value) shows no urgency pill at all, never a guess; a
  held step with no `hold_code`, or a code `dfqueue/public_text.yaml` does
  not map, still shows "on hold" with no reason text, never a guessed one.
- **Placeholder**: the video frame (design's live view is not embedded —
  no relay, no noVNC locally; it stays black in both themes either way),
  the status strip and "right now" line (`feed.status` does not exist yet
  — design section 3.1), the season goal strip (no goal exists), the
  Season/chronicle view (slice S7), and history scrolling past the single
  open segment (design section 4.4's segment-fetching logic is not
  implemented client-side yet — a real fort's queue is far larger than the
  small test exports this slice ships with, so this was not yet exercised
  against real segment files).

## Slice S1: operator live (prepared offline, not deployed)

`handoffs/2026-10-01-stream-page-s1-prep.md` built everything S1 needs
offline: the real publisher (`scripts/stream_publisher.py`), a read-only
equivalent of `dfqueue.store.project_status` it needs for step-level
progress (`dfqueue/feed_status.py`), and the `infra/` templates below.
**Nothing in this section has been run against VM 103 or the relay.** Every
command is written out exactly so the orchestrator (or the user) can review
it before running it for real, per this repo's CLAUDE.md rule that any
change to live/VM state needs explicit go-ahead each time.

**Paths below reflect the multi-fort layout** (register 2026-10-02):
`scripts/stream_publisher.py` now calls `dfqueue.feed.write_fort_feed`, so
every `.../data/public/head.json` path quoted in this section actually
lands at `.../data/public/forts/<fort-id>/head.json`, with
`.../data/public/forts.json` alongside it (`<fort-id>` defaults to
`STREAM_PUBLISHER_DB`'s own file stem; see "Known gaps" above for the
env vars that configure it). Caddy and the `rrsync` push key need NO
changes either way, since both already serve/accept the whole
`data/public`/`data/operator` directory tree recursively, not a named file
inside it.

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
   (`cat <staging-dir>/public/forts.json` and
   `<staging-dir>/public/forts/<fort-id>/head.json`, same shape
   `write_fort_feed` produces locally) before any network step.

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
   (`curl 127.0.0.1:<public-caddy-port>/data/public/forts.json` --
   if step 4's manual cycle has not pushed yet, this 404s, which is
   expected and fine) before touching the tunnels.

**Back on VM 103, now with the relay side of the key verified:**

8. Fill in the eight `STREAM_PUBLISHER_{PUBLIC,OPERATOR}_RELAY_*` variables
   in `.env` and re-run the manual `--once` cycle from step 4. Confirm it
   reports `"pushed": true` for both sides, then confirm **on the relay**
   that `/srv/stream/data/public/forts.json` and
   `/srv/stream/data/operator/forts.json` both exist and match what step 4
   staged locally.
9. Only once 7 and 8 both check out: repoint each Cloudflare tunnel's
   ingress from websockify's own port to Caddy's (per
   `infra/relay-stream-caddy.example.Caddyfile`'s own header), and enable
   the timer: `sudo systemctl enable --now stream-publisher.timer`.

### Verifying each hop

| Hop | How to check |
|---|---|
| Publisher reads the queue | `--once`'s own JSON summary on stdout (journald, once the timer runs): `kill_switch_active`, and `"reason"`/`"pushed"` per side |
| Local staging is correct | `cat <staging-dir>/public/forts.json` and `.../forts/<fort-id>/projects.json` on VM 103 |
| The restricted key is actually restricted | the two `rsync` commands in `infra/stream-publisher-push-key-authorized-keys.example`'s "Verify after installing" section, run from VM 103 |
| The relay actually received the push | `cat /srv/stream/data/public/forts.json` on the relay, compared to VM 103's staged copy |
| Caddy serves it, loopback only | `curl 127.0.0.1:<port>/data/public/forts.json` on the relay itself; the same URL from off-host must fail until a tunnel points at it |
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

- No JS test suite for `app.js` — `dfqueue/tests/test_feed.py` and
  `test_feed_status.py` cover the data layer thoroughly (that is where the
  safety-relevant logic lives: the allowlist, the withhold net, step-state
  derivation); the rendering layer is exercised manually (this stream's own
  Result section records exactly what was screenshotted, in both themes, at
  desktop and 375px) rather than automated. A future slice could add a
  headless-browser smoke test if that seems worth the dependency.
- No closed-segment or season-file fetching client-side (see above).
- A step with a dynamic `{"from_step": ...}` target spec (design §4.3)
  shows no "N of M" count at all (not fabricated) and only ever reads
  `ready`/`waiting`/`hold` from whether ANY `executed` record covers it, not
  partial progress — this slice's `dfqueue.feed_status.step_board_states`
  only derives per-target counts for a step's own literal `targets.set`.
- `scripts/stream_publisher.py` now calls `dfqueue.feed.write_fort_feed`
  (this gap is closed): `STREAM_PUBLISHER_FORT_ID` (defaults to
  `STREAM_PUBLISHER_DB`'s own file stem), `STREAM_PUBLISHER_FORT_NAME`
  (default `Ragwind`) and `STREAM_PUBLISHER_FORT_STATUS` (default `live`)
  mirror the export script's own `--fort-id`/`--fort-name`/`--fort-status`.
  **What the first real deploy of this change does on the relay**: before
  it, nothing has ever pushed the multi-fort layout there, so there is
  nothing to go stale on a from-scratch install. If a relay somehow already
  has old flat `data/public/head.json`-style files from an even earlier,
  pre-multi-fort build of this script, they become stale and inert once
  `forts.json` lands beside them: the page (see "Multiple forts" above)
  reads `forts.json` first and only falls back to treating the projection
  root as one flat fort's feed when `forts.json` is entirely ABSENT, so a
  stale flat file sitting next to a real `forts.json` is simply never read
  again. No manual cleanup is required on the relay; deleting the old flat
  files there is optional and harmless.
- Accessibility: role names are always shown as text (never colour alone),
  but this has not been tested with a real screen reader. The theme toggle
  and board cards are plain buttons (keyboard-reachable, `aria-pressed`
  where relevant) but no explicit focus-trapping exists in the details
  panel.
