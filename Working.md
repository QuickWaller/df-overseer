# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.

## HANDOVER - 2026-09-11 (end of session, `perception-layer-experiments`
worktree at `../df-automation-perception`, separate from `main`)

The prior handover (the second fort's founding, the first fort's lost save,
the seed-landmark bootstrap) is archived wholesale —
[`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md),
superseded by this one: exceeded the ~400-line threshold, not superseded by
new narrative on the same topics. **This session's result: the entire
spatial/perception build order (`docs/PURPOSE.md` items 2-8) is built and
verified live against the real Uniboslan fort, all 8 commits pushed to
`origin/perception-layer-experiments`.**

### State at a glance

- **Six new DFHack Lua scripts exist** (`scripts/dfhack/df-overseer-*.lua`),
  each deployed via `install_df.py ui-install` and tested against the live
  fort, not just written: `df-overseer-landmarks.lua` (real burrow/building
  enumeration + adjacency graph, extending the prior session's seed-only
  slice), `df-overseer-connectivity.lua` (named-landmark `check`,
  `near_landmark`-enriched `report`), `df-overseer-overview.lua`
  (`get_overview`, tier0/1/2), `df-overseer-diff.lua` (`get_diff_since` via
  `eventful`), `df-overseer-openarea.lua` (`find_open_area`, terrain=built),
  `df-overseer-chokepoints.lua` (`find_chokepoints`), and
  `df-overseer-stuckjobs.lua` (`get_stuck_jobs`).
- **Two real bugs in the research doc's own prototype sketch were caught
  before shipping**, both fixed and documented in the scripts' own
  comments: `dfhack.buildings.getSize()`'s `cx,cy` are local to the
  building's own box, not absolute map coordinates (would have collapsed
  every building's centroid onto nonsense points); `df.global.world.
  burrows.all` doesn't exist, the correct path is
  `df.global.plotinfo.burrows.list`.
- **`get_stuck_jobs`'s "unverified locally" flag from the research doc is
  resolved** — found three real, shipped stock-script uses of
  `utils.listpairs(df.global.world.jobs.list)` on this exact install,
  stronger confirmation than the research doc itself had.
- **Two live-unpause tests, both with the user's explicit go-ahead each
  time**, closed the two honest gaps that couldn't be verified read-only:
  `get_diff_since`'s real `eventful`→callback wiring (a real dig, a real
  `JOB_COMPLETED` event, correct cursor), and `get_stuck_jobs`'s
  `JOB_INITIATED` tracking (real jobs, real tracked start ticks) — though
  the actual "no worker assigned" window itself was too fast to catch live
  both times (an idle miner grabbed the test digs in under a second of
  unpaused time). Re-paused and quicksaved immediately after each,
  verifying via real `world.sav` mtimes, not exit codes.
- **A real, previously-undocumented save-mechanics wrinkle surfaced**:
  `save/current` is transient staging, not an addressable save — see
  durable traps.
- **Cross-session coordination confirmed clean**: another session,
  `df-automation-7d`, worked `main` concurrently on independent per-viewer
  pan/Z-level camera control via `RemoteFortressReader` — no data-path
  overlap confirmed directly with them (this session never reads RFR/raw
  tile geometry; theirs never touches `dfhack.buildings`/`dfhack.burrows`).
- **A real gap in the whole project's plan was found and fixed on `main`**,
  not this branch: `docs/PURPOSE.md`'s numbered build order (0-9) is
  entirely spatial/perception work — nothing covers dwarf/labor management
  (skills, happiness, labor assignment). Dwarf Therapist doesn't fit this
  project (GUI-only; the fort runs headless/unattended); DFHack's own
  equivalent, `manipulator`, is tagged `unavailable` on this install;
  `autolabor` (a different, available plugin) does fit. Added as a
  `ROADMAP.md` Later-bucket item, committed and pushed to `main` directly
  (`f2103c8`) since it's whole-project planning, not perception-branch work.
- **This branch's own copies of `docs/PURPOSE.md`/`ROADMAP.md` are stale
  relative to `main`** (predate the fort's founding entirely) — flagged
  in-place in `docs/PURPOSE.md`'s own status banner rather than silently
  left misleading. The build order section itself has been kept current
  incrementally this session and is accurate for the perception layer
  specifically.

### Next

1. **`rank_candidate_sites`** (second half of build order item 7) —
   genuinely blocked, not skipped: needs `resource_summary` and
   threat-exposure data that don't exist yet. Building it now would mean
   fabricating placeholder scoring terms, which this session's pattern
   has consistently avoided.
2. **`find_open_area` (terrain="cavern")**, build order item 9 —
   deliberately last, needs a genuinely different distance-transform/
   clustering algorithm, not a rectangle scan.
3. **The research spec's `via` (path-type, e.g. "corridor") exit field**
   is deliberately not implemented on any landmark's exits. Would need
   real path-tracing this session's slices don't attempt.
4. **Dwarf/labor management** (`get_unit_status` + a labor-assignment
   action tool, `autolabor` as baseline) — real gap, tracked in
   `ROADMAP.md`'s Later bucket on `main`, not started.
5. **Not done this session, still open from an earlier handover**: the
   `find_mm_*` Y-axis transform mystery (cheap, read-only, not blocking).
6. **Worth deciding, not urgent**: whether to pull an actual
   `install_df.py backup` of Uniboslan's save now that this project found
   out the hard way (losing Artobcatten) that none had ever been taken of
   a fort-bearing save.
7. **Whether/when to merge `perception-layer-experiments` into `main`** —
   still the user's call to make, not assumed. All 8 commits are pushed to
   the branch on origin; nothing has been proposed for merge.

### Durable traps, still true (additions marked NEW)

Embark-screen automation mechanics (coordinate frames, `xdotool`
calibration, dead input paths, dialog handling, the click tool's known
flaws) are the permanent, living content of `docs/DF-UI-AUTOMATION.md` —
not duplicated here, confirmed still current on this branch. This list is
everything else: infra, project-wide gotchas, and this session's findings.

- NEW: **Directly changing a live fort's pause state
  (`dfhack.world.SetPauseState(false)`) is blocked by Claude Code's own
  auto-mode classifier by default**, not something a bare mid-conversation
  "go ahead" reliably satisfies. The first time this session, it rejected
  the identical call twice even after explicit conversational approval
  each time, and only went through once the user actually adjusted a
  permission setting. A second, later instance (new session) was blocked
  again on the first attempt but went through on retry after asking
  specifically and getting a fresh explicit yes, with no further settings
  change visible. Net guidance: don't assume a general "continue"/"lets do
  it" earlier in a conversation covers this specific action — ask right
  before the call, get an explicit answer to that exact question, and if
  it's still blocked after that, say so plainly and let the user adjust
  settings rather than retrying blind or routing around it with an
  equivalent raw struct write.
- NEW: **`quickfort run <file>` resolves a plain filename relative to
  `dfhack-config/blueprints/`, not the working directory or an absolute
  path** — `quickfort run /opt/df/foo.csv` fails with `"failed to open
  dfhack-config/blueprints//opt/df/foo.csv"` (the two paths get
  concatenated, not replaced). Write ad-hoc blueprints directly into that
  directory.
- NEW: **`save/current` is transient staging, not itself an addressable
  save.** A quicksave briefly writes a fresh `world.sav` there, then DF
  moves it into the actual numbered slot (`autosave N`, whichever
  `df.global.world.cur_savegame.save_dir` names) within moments, leaving
  `current` empty again. Checking `save/current`'s mtime instead of the
  slot `cur_savegame.save_dir` actually names can read a just-written save
  as apparently vanished when it has simply already moved — a new,
  concrete instance of the already-known "quicksave lands with a delay"
  trap, not a separate bug.
- NEW: **`reqscript`-loading a `df-overseer-*.lua` file requires a
  `--@module = true` directive as one of its leading comment lines**, or
  `reqscript` refuses it outright ("Cannot be used as a module") — found
  by reading how `warn-stranded.lua` declares itself reqscript-able.
  Separately, a module-loaded script's own top-level CLI-dispatch code
  still runs during that load unless explicitly guarded (`if
  dfhack_flags.module then return end`, same pattern `warn-stranded.lua`
  uses) — without it, loading a module prints its own "usage: ..." text
  ahead of whatever the actual caller wanted.
- **VM 103 is running DF unattended with no network isolation boundary.**
  home-lab's `memory/tailscale-architecture.md` assigns `df-fortress`/
  `df-colony-01` to `tag:ai-sandbox` — "unattended, possibly LLM-driven,
  lowest trust that isn't internet-facing" — but `runbooks/tailscale-topology.md`
  Phase 5 (the actual hard gate) is still unchecked. **Not this repo's to
  fix** — host-level Tailscale/ACL work, forbidden to any agent by
  home-lab's own rule.
- **DF ignores SIGTERM.** Quicksave before stop is mandatory once a fort
  is live; a bare stop takes the full timeout and ends in SIGKILL.
  **Load-bearing, not theoretical** — a real fort exists and must be
  quicksaved before any future stop.
- **The manual (`start`/`stop`) and systemd-managed paths must not run at
  once** — `install_df.py stop` does not clean up a manually-started
  Xvfb. See archive for the full incident/fix.
- **`-gen` fails silently** roughly a quarter of the time. Success is the
  region directory existing, never the exit code.
- **Saves live at the XDG path**, not in the game directory.
- **Never convert a booted VM to a template without sealing it.**
- **The published hostname is exposed.** The user chose not to rename it.
- **`willsmith.nz` is deliberate**, not a leak: the intended public face.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **DF replay determinism is unverified.**
- **`hypothesis_id` has no registry.**
- **`openclaw` vs `hermes-agent` still deferred.**
- **Tarball checksums are pinned and enforced.**
- **PVE's cloud-init takes only the first label of the VM `name`** —
  `install_df.py`'s `step_hostname` (reused for the relay too) is the only
  workable route to a suffixed guest hostname.
- **Hostname convention has one canonical source: home-lab's `CLAUDE.md`,
  Conventions section.** Cite it, do not restate it here.
- **ImageMagick's `import` infers output format from the file extension.**
  Use an explicit `format:` prefix (`png:path`).
- **On a screen with an actual map viewport, never do a blanket
  full-screen `dfhack.screen.readTile` dump.** Scope scans to the specific
  rows/columns a label search actually needs.
- **`code=exited, status=1` in `systemctl status` means the process called
  `exit(1)` itself, not a signal death** — a core dump will never fire for
  it. Distinguish from `code=killed, status=SIGxxx`.
- **`dfhack-run lua -f script.lua ARG1 ARG2` passes arguments via Lua
  varargs (`local x, y = ...`), not a global `arg` table.**
- **A checksum must never pass through an LLM-summarized web fetch** —
  fetch it directly with `curl` and compare byte-for-byte.
- **`.env` appends must check for a trailing newline first** —
  `install_df.py`'s `_append_env_var()` helper does this.
- **A full-tree file-manifest diff must tab-separate size and path**
  (`find ... -printf '%s\t%P\n'`, split with `awk -F'\t'`), not
  space-separate.
- **A long payload embedded directly in an SSH command string silently
  truncates at ~8182 characters when Git's MSYS-linked `ssh.exe` is
  spawned by a native Win32 process (Python's `subprocess`) rather than a
  POSIX one (bash)** — no error, exit 0, the remote side just runs a
  truncated command. `provision_vm.ssh_guest` now takes `input_data` to
  pipe a payload over stdin instead; never embed an unbounded-size
  payload directly in an SSH command string again — see
  `provision_vm.ssh_guest`'s docstring.
- **The costly one — read before ever founding another fort while one
  already exists**: **DF's save-slot names (`autosave 1`, `autosave 2`,
  `current`) are a shared generic pool, not scoped per fort.** Founding
  Uniboslan overwrote Artobcatten's save, confirmed via `md5sum` (both
  slots byte-identical afterward). **Before founding any future
  additional fort**: pull an `install_df.py backup` of every existing
  save first.
- **A founded fort's own "A Dwarven Outpost..." welcome message (with an
  "Okay" button) silently blocks all citizen activity** even though
  `df.global.pause_state` reads `false`. Always dump the screen and check
  for this dialog before concluding a fort is "stuck."
- **A downward-staircase (`j`) dig designation cannot be placed on a
  grass-covered surface tile** — confirmed, `quickfort` reports "0 tiles
  designated" with no error. Works on other floor types.
- **A plain `d` (floor) dig designation directly beneath an
  already-completed downstair does not become an assignable job unless
  the connecting tile is itself a matching stair type** (`u`, upstair).
- **The fortress-wide job list is `df.global.world.jobs.list`, traversed
  via `utils.listpairs(...)`** — not `df.global.job_list` (confirmed not
  to exist) and not manual `.next`/`.item` walking (works, but
  `utils.listpairs` is the canonical, stock-confirmed idiom).
- **DF Classic's 2D engine (`PRINT_MODE:2D`) does have real zoom** —
  `[`/`]` keys, confirmed working live via `xdotool`.
- **`install_df.py backup` is a genuine, verified substitute safety net**
  when a Proxmox snapshot is blocked by cluster quorum issues.
- **A `quicksave` RPC call can return and log "The game should autosave
  now" before the file actually lands on disk** — wait a few seconds and
  recheck (and check the slot `cur_savegame.save_dir` names, not
  `save/current` — see the NEW entry above).

### Other open items, carried forward

- **Design commitment #1's absolute wording vs. its actual evidence
  base** — still queued for a `decisions/DECISIONS.md` entry, deliberately
  not written yet (user's call on timing).
- **Live-view ingest (the public screenshot-push leg), still waiting on
  the user.** Once Cloudflare R2 credentials arrive: wire
  `DF_STREAM_INGEST_URL` in `.env`, convert `curl -F` to an S3-compatible
  signed PUT, fill in `IMAGE_BASE` in
  `willsmith-portfolio/public/dwarf-fortress/index.html`, commit, ask
  before pushing/deploying either repo.

**Style note:** the user does not want em dashes in prose. Commas, colons,
semicolons or full stops instead. Fine as structural separators.

## Archived

- Sections through 2026-09-10 (fifth handover) — provisioning build,
  perception eval, fort ledger, systemd units, title-screen bootstrap,
  live-viewing/relay/tunnel, the tileset investigation, Site Finder
  resolution, the embark-flow saga through both forts founded, and the
  seed-landmark bootstrap — all moved wholesale to
  [`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md)
  across several prior handovers, each superseded or exceeding the
  ~400-line threshold. See that file's own tail for the full list.
- 2026-09-11 (this handover): the two-session arc building the entire
  spatial/perception build order (items 2-8: landmarks, named
  reachability, `get_overview`, `get_diff_since`, `find_open_area`,
  `find_chokepoints`, `get_stuck_jobs`) moved wholesale to the same
  archive file — exceeded the ~400-line threshold, not superseded. The
  handover above is the tight current-state summary; the archive has the
  full narrative, decision-by-decision, including the exact live
  verification steps and bugs caught along the way.
