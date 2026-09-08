# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.

## HANDOVER - 2026-09-08 (evening)

**State at a glance.** VM 103 (`df-colony-01`, `192.168.2.201`) is fully
installed, verified, and running DF under systemd with a generated world
(`POCKET ISLAND`, seed 658085253) — the first thing in this project to run
unattended. **No fort exists yet**; nobody has embarked. On top of that,
this session added two new capabilities: periodic screenshot capture
(verified working) and a start on scripted, blind embark automation
(genuinely unfinished, paused mid-test). Full detail on both is in
`decisions/DECISIONS.md`'s 2026-09-08 rows; the morning's VM-rebuild
narrative (identity retirement, clone, install, hostname convention fix) is
now archived — see the pointer at the bottom of this file — since it
completed and is superseded by everything below.

**Commit state.** Many local commits this session, ending at `91419d7`.
Working tree clean. **Not pushed anywhere**, in either `df-automation` or
`willsmith-portfolio` — publishing needs its own go-ahead per the Rules
section, every time.

**Embark-automation: researched, live-testing genuinely incomplete.**
`research/2026-09-08-embark-automation.md` nails the screen sequence,
keybindings for the confirmed part of the flow, and the success check, all
from primary sources (real shipped DFHack scripts), not guesses. The one
real gap — how "Start" on the title screen reaches a fresh embark, as
opposed to continuing/reclaiming — has no installed script to crib from and
needs live, polled testing. That testing started (`pre-embark-test-2026-09-08`
VM snapshot taken first) and got one `SELECT` sent to the title screen
before an unrelated infra incident (below) interrupted it. **DF's title
screen currently sits one level into the "Start" submenu**, not the bare
root menu — confirmed visually via a stream capture, not just inferred.
Harmless (no world loaded from there), but the next `simulateInput` call
needs to account for it rather than assume a fresh title screen. Next step:
resume live-testing from here, or roll back to the snapshot for a clean
baseline first.

**Incident: `df-xvfb.service` crash-looped for ~14 minutes (47+ restarts)
during the embark testing above, unrelated to it.** Root cause: an orphaned
Xvfb process from an earlier manual `install_df.py start` in this same
session, never cleaned up by `stop` (which only kills `dwarfort`), silently
poisoned every later systemd-managed Xvfb start. Fixed live (killed the
orphan) and verified stable with a full `install_df.py verify`, plus a
defensive `ExecStartPre` lock-cleanup landed in `scripts/install_df.py` for
the *stale-lock-only* version of this failure. No fort existed yet, so
nothing was lost. Full incident writeup and the sharpened durable-trap entry
are below. → `decisions/DECISIONS.md` 2026-09-08 incident row.

**Live-view screenshot capture: built, verified, working — ingest paused on
the user.** `research/2026-09-08-live-viewing.md` recommends periodic
screenshot push over VNC or video; `install_df.py stream` implements the
capture half, verified for real by pulling `latest.png` off the VM and
viewing it (genuine DF title screen, correct size). Two real bugs found and
fixed in the same pass (ImageMagick's silent PostScript-instead-of-PNG
extension trap, and a root-owned capture directory against a `User=df`
service) — both are now baked into the script, not just worked around by
hand. **Blocked on the ingest side**: willsmith.nz is a static GitHub Pages
site with no backend, so screenshots need somewhere else to land.
Cost-checked (should be $0/month) and the exact Cloudflare R2 setup steps
are recorded — see "What a next session should pick up" below — but the
user can't do the console work right now, so this is paused, not stuck. A
standalone viewer page exists at
`willsmith-portfolio/public/dwarf-fortress/index.html`, committed there
locally (not pushed), honestly showing "not wired up yet" rather than a
broken image.

**Cross-session: home-lab-43's `CLAUDE.md` addition was accepted and
committed.** Verified against home-lab's own 2026-08-27 decision before
accepting — see `decisions/DECISIONS.md`. It declares home-lab as source of
truth for estate IDs and sets an obligation: any future guest
create/delete/resize/re-address here must update `home-lab/inventory/` the
same turn. Nothing in this session triggered that obligation (no guest was
created/deleted/resized), so it's recorded but not currently owed.

### Durable traps, still true

- **DF ignores SIGTERM.** Quicksave before stop is mandatory once a fort is
  live; a bare stop takes the full timeout and ends in SIGKILL.
- **The manual (`start`/`stop`) and systemd-managed paths must not run at
  once — and `install_df.py stop` does not clean up after `start`.** Confirmed
  the hard way 2026-09-08: `start` launches Xvfb via `setsid nohup ... &`,
  outside systemd entirely, and `stop` only kills `dwarfort`, never that Xvfb.
  A manual Xvfb left running after `stop` becomes an orphan that silently
  poisons every later `systemd --start`: `df-xvfb.service` crash-loops
  forever against a real listener already on `:99` (not just a stale lock —
  `Restart=on-failure` retries a failure it can never fix on its own), and
  `df-fortress.service` cycles as its downstream dependency. Fix if it
  recurs: find and `kill` the orphaned Xvfb process (`ps aux | grep -i xvfb`,
  won't show up correctly in `systemctl status` since it's untracked), then
  `systemctl restart df-xvfb.service df-fortress.service`. A defensive
  `ExecStartPre` lock-file cleanup was added to `XVFB_UNIT` in
  `scripts/install_df.py` the same day, which self-heals the *stale-lock-only*
  version of this failure but not a live orphan. → `decisions/DECISIONS.md`
  2026-09-08 incident row.
- **`-gen` fails silently** roughly a quarter of the time. Success is the
  region directory existing, never the exit code.
- **Saves live at the XDG path**, not in the game directory.
- **Never convert a booted VM to a template without sealing it** (`cloud-init
  clean`, remove SSH host keys, truncate `machine-id`). The code that enforced
  this went with the bake on 2026-09-08, because a template that is never
  booted has nothing to seal. If anyone reintroduces a boot-before-convert
  step, the seal has to come back with it.
- **The published hostname is exposed.** The user chose not to rename it.
- **`willsmith.nz` is deliberate**, not a leak: the intended public face.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **DF replay determinism is unverified.**
- **`hypothesis_id` has no registry.**
- **`openclaw` vs `hermes-agent` still deferred.**
- **Tarball checksums are pinned and enforced** as of 2026-09-08;
  `bzip2 -t` catches truncation, the sha256 catches substitution.
- **PVE's cloud-init takes only the first label of the VM `name` and discards
  everything after the first dot.** `install_df.py`'s `step_hostname` is the
  only workable route to a suffixed guest hostname, not merely the tidier
  one. → `decisions/DECISIONS.md` 2026-09-08 rows on the `.internal`
  convention.
- **Hostname convention has one canonical source: home-lab's `CLAUDE.md`,
  Conventions section, "Hostnames: `.internal`, on the OS hostname only."**
  Cite it, do not restate it here or in `DECISIONS.md`.
- **ImageMagick's `import` infers output format from the file extension.**
  A temp filename without a recognized extension (e.g. `.tmp`) silently
  produces the wrong format (PostScript, observed) with no error. Use an
  explicit `format:` prefix (`png:path`) rather than relying on the
  extension, especially for a temp-then-`mv` pattern.

### What a next session should pick up

`ROADMAP.md`'s Now bucket is the canonical list. Two genuinely open threads:

1. **Embark live-testing.** Resume from DF's current state (one level into
   the title screen's "Start" submenu — verify first, don't assume) or roll
   back to `pre-embark-test-2026-09-08` for a clean baseline, then continue
   the ordered step list in `research/2026-09-08-embark-automation.md` §9.
2. **Live-view ingest, waiting on the user.** Once Cloudflare R2 credentials
   (Account ID, Access Key ID, Secret Access Key, bucket name) arrive: wire
   `DF_STREAM_INGEST_URL` in `.env`, convert the capture script's `curl -F`
   to an S3-compatible signed PUT (R2 doesn't accept plain multipart POST —
   `aws s3 cp` via `awscli` is the simplest route), fill in `IMAGE_BASE` in
   `willsmith-portfolio/public/dwarf-fortress/index.html`, commit, and ask
   before pushing/deploying either repo.

**Style note:** the user does not want em dashes in prose. Commas, colons,
semicolons or full stops instead. Fine as structural separators.

## Archived

- Sections for the week of 2026-08-24 (the design phase, the access-layer
  build, and the host-RAM blocker) moved to
  [`working-archive/Working_archive-2026-08-24.md`](working-archive/Working_archive-2026-08-24.md).
- 2026-08-27: the provisioning-build handover and the 2026-08-26 storage-blocker
  detail (both finished/superseded) moved to the same archive file.
- 2026-08-27 (evening): the afternoon perception-eval section (it reported
  itself finished) and the afternoon handover (superseded by the one above)
  moved to the same archive file.
- 2026-08-27 (late evening): the fort-ledger section and the VM-start
  section, both finished, moved to the same archive file.
- 2026-08-27 (evening): the late-evening handover, superseded by the
  provisioning-hardening handover above, moved to the same archive file.
- 2026-08-27 (night): the provisioning-hardening handover, superseded by the
  handover above, moved to the same archive file.
- 2026-08-28: the 2026-08-27 night handover (DF installed on VM 104), superseded by
  the handover above, moved to the same archive file.
- 2026-08-28 (evening): the morning handover (superseded by the one
  above) and the DF-install-scripting section (it reports itself
  finished: the script shipped and was verified against VM 104) moved
  to the same archive file.
- 2026-08-30: the 2026-08-28 (evening) handover, superseded by the handover
  above (systemd units built, tested through a real guest reboot, and
  `onboot` set), moved to the same archive file.
- 2026-09-08: the 2026-08-30 handover moved wholesale to
  [`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md).
  Not superseded content so much as overtaken by events: VM 104 and template
  101 were deleted 2026-09-01 while this repo sat quiet, so the handover
  describing them is now history rather than current state.
- 2026-09-08 (evening): the morning/afternoon rebuild handover (VM rebuild,
  identity retirement, install, hostname-convention fix) moved wholesale to
  the same archive file — it completed and was superseded by worldgen, the
  Xvfb incident, embark-automation research, and the live-view capture build,
  all captured in the handover above.
