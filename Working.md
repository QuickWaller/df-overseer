# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.

## HANDOVER - 2026-09-10 (end of session, fifth handover today)

The prior handover from earlier the same day is archived wholesale —
[`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md),
superseded by this one. **This session's result: a second fort was
founded ("Uniboslan, 'Ragwind'"), but the first fort's save ("Artobcatten")
was lost as a side effect — an unrecoverable incident, not a close call.**
The text-only sweep also got built and a real Windows SSH bug got fixed
along the way.

### State at a glance

- **A second fort exists and is running normally: "Uniboslan, 'Ragwind'"**,
  founded via the text-only sweep, confirmed via the in-game founding
  message and `gametype==0`. Quicksaved, transitioned off the diagnostic
  gdb-wrapped process (used as the crash workaround, see below) onto
  normal `df-fortress.service` systemd supervision, reloaded via the
  title screen's "Continue active game" button, verified via
  `viewscreen_dwarfmodest`'s own header. `df.global.world.cur_savegame.save_dir`
  is `autosave 2`.
- **The first fort, "Artobcatten, Combinedchannel," is gone.** Its actual
  save data lived in `save/autosave 1` (this repo already knew DF doesn't
  name a fort's save after its region — see the durable traps). Founding
  Uniboslan overwrote it: `save/autosave 1/world.sav` and
  `save/autosave 2/world.sav` are now byte-for-byte identical (confirmed
  via `md5sum`), both holding Uniboslan's data. `save/current` is empty,
  `region1`/`region2` are confirmed (again) pure world-gen-history with no
  player-fort data, and this repo's `backups/` directory has never
  actually been used (empty) — no recovery path was found. Told the user
  directly before doing anything else; **the user chose to accept the
  loss and move forward with Uniboslan** rather than pursue a
  Proxmox-snapshot recovery check. Full incident trail:
  `decisions/DECISIONS.md` 2026-09-10 ("second fort was founded, but the
  first fort's save was lost").
- **Extended `df-overseer-ui.lua`** with `embark-mode`, `leave-embark-mode`,
  `hover` — see the durable traps section for the mechanics these
  depend on. Deployed via `install_df.py ui-install`, confirmed working
  live and used to actually find and commit Uniboslan's site.
- **Found and fixed a real, previously-latent Windows-specific SSH bug**
  while deploying the above script: Git's MSYS-linked `ssh.exe` truncates
  a command-line argument to ~8182 characters when spawned by Python's
  `subprocess` (a native Win32 process) but not when spawned by bash.
  Fixed: `provision_vm.ssh_guest` gained `input_data` (pipes a payload
  over stdin instead), `install_df.remote()` uses it. `provision_relay.py`
  inherits the fix for free.
- **A crash, same signature as the first fort's "Confirm" race, recurred
  at a different step** (the map-click step, not Confirm) on the first
  commit attempt for Uniboslan's site — `code=exited, status=1`, no core
  dump, no save created, nothing lost by the crash itself. The known `gdb`
  workaround (run `dwarfort` directly under `gdb` with a `catch syscall
  exit_group` batch script, matching systemd's exact environment) avoided
  it again on retry, same as for the first fort.
- **New finding while retrying under `gdb`**: a real `xdotool` click on a
  genuinely valid, placeable tile went straight through to
  `viewscreen_setupdwarfgamest` with no `warn_mm_*` force-write and no
  separate Confirm click needed at all — unlike the first fort's
  documented flow. Not fully explained; possibly the force-write/Confirm
  dance was compensating for something specific to DFHack's fake input,
  not an inherent property of the flow. Worth revisiting if a third embark
  is ever attempted.
- **New finding, load-bearing for any future second embark**: restarting
  the embark flow from the title screen ("Start new game in existing
  world") did **not** return to the same world/coordinate frame as the
  stale mid-navigation state this session started in — it landed in
  `region1`, not `region2`. The stale `neighbor_hover_mm_*` numbers from
  before the crash pointed at real mountain terrain in this different
  world (DF's own validation correctly flagged it unplaceable), not the
  forest found earlier — a coincidence of matching numbers across
  different worlds, not a bug in the coordinate frame itself. The sweep
  had to be re-run fresh in the world actually reached this time.
- **Then built the first real perception-layer code**:
  `check_reachable`/`get_connectivity_report`, `docs/PURPOSE.md` build
  order item 2, done. `scripts/dfhack/df-overseer-connectivity.lua`
  (`./dfhack-run df-overseer-connectivity <report|check A B>`) reuses
  `warn-stranded.lua`'s own `getStrandedGroups()` via `reqscript` rather
  than reimplementing it — confirmed live against Uniboslan (7 citizens,
  one walk group, matches `warn-stranded status`'s own output exactly).
  `install_df.py ui-install` generalized to deploy every
  `df-overseer-*.lua` file, not just one hardcoded name, now that a second
  script exists. `check_reachable()` is an explicit stopgap: takes two raw
  unit ids, not landmark names, since named-endpoint resolution needs
  `get_landmark` (build order item 3, not built) — flagged in the script's
  own comments to replace, not left as a silent permanent API.
  `near_landmark` omitted from the stranded-groups output rather than
  stubbed with raw coordinates, matching the research spec's own reasoning
  for that field's existence. JSON key order is deterministic for free:
  DFHack's `json.encode` delegates to a C++ (jsonxx-derived) encoder,
  confirmed stable across repeated fresh processes — satisfies build item
  4's requirement early, no manual sort needed. Live-tested three cases
  (empty report, two reachable citizens, one nonexistent unit id) — see
  `decisions/DECISIONS.md` 2026-09-10.
- **User raised a real gap in build order item 3 before it was built**:
  every downstream tool that expresses results relative to a named
  landmark has nothing to anchor to on a virgin embark, since burrows/
  buildings only exist once something's been dug or built — the build
  order never said how the first landmark gets created. Also asked
  whether a full 3D world representation would be readable by the model;
  answered from evidence already in this repo (`evals/perception/`
  deliberately never built a full-grid arm, and the cross-domain research
  behind it — BALROG, NLE, Voyager, robotics scene graphs — already found
  transformers don't reliably reconstruct spatial adjacency from a
  flattened grid regardless of encoding) rather than re-litigating it from
  scratch. **User's call: try a fix, explicitly framed as experimental, not
  settled.** Built `scripts/dfhack/df-overseer-landmarks.lua`
  (`list`/`get NAME`): seeds one landmark, "Embark Site," from the
  citizen-position centroid (a wagon-based anchor was checked and ruled
  out — `world.vehicles.all` is confirmed empty for this embark),
  persisted via `dfhack.persistent.saveSiteData`. **Verified live**:
  computed `(96, 96, 169)` matching a hand-computed centroid, confirmed
  stable across repeated calls, and — the real test — confirmed it
  survives a full quicksave + systemd stop/start + "Continue active game"
  reload (genuine save-file persistence, not an in-memory cache). Found
  and fixed a real bug in the process: querying `list` immediately after
  triggering a reload (before the map had finished loading) crashed inside
  `json.encode` because the error path's two return values got splatted
  positionally into a function where the second argument means something
  else entirely (`options`, not "error message") — fixed by destructuring
  explicitly at the call site. This is one bootstrap node only, not the
  real burrow/building enumeration + adjacency-graph system build order
  item 3 still calls for.

### HANDOVER - 2026-09-10 (new session, `perception-layer-experiments`
worktree at `../df-automation-perception`, separate from `main`'s own
Working.md and its own "sixth pass" quickfort/blueprint session)

Picked up the item below as the queued next step. **The real burrow/
building enumeration + adjacency graph is built and verified live**,
extending `df-overseer-landmarks.lua` past its seed-only first slice.
Every call now merges the persisted seed landmark with a fresh
enumeration of `df.global.world.buildings.all` (filtered to a non-empty
`dfhack.buildings.getName()`) and `df.global.plotinfo.burrows.list`, and
computes a nearest-3 exits graph per landmark (direction, distance, and a
live-verified `walkable` bool from `dfhack.maps.canWalkBetween`).

**Two real bugs were found and fixed by verifying live against Uniboslan
rather than trusting the research doc's prototype sketch**, both
documented in the script's own comments:
1. `df.global.world.burrows.all` does not exist as a field
   (`"Cannot read field world.burrows: not found"`). The correct path is
   `df.global.plotinfo.burrows.list`.
2. `dfhack.buildings.getSize(building)`'s returned `cx,cy` are local to
   the building's own bounding box, not absolute map coordinates
   (confirmed: a 3x3 Wagon building returned `cx=1,cy=1`; a 5x5 stockpile
   returned `cx=2,cy=2`). Would have silently collapsed every building's
   centroid onto nonsense points if the research doc's prototype had been
   used as written. Absolute centroid is `(x1+x2)/2, (y1+y2)/2, z` instead.

Also found live: the embark wagon genuinely is a first-class `building`
object (`building_type` "Wagon") with a real default name. The
seed-landmark session's conclusion that no wagon object exists at all
checked `world.vehicles.all` (empty for this embark), not `buildings.all`:
that was the wrong list to check, not a true absence of a wagon object.

Deployed via `install_df.py ui-install` and tested live against the real
Uniboslan fort: `list` returns three landmarks ("Embark Site", "Wagon",
"Stockpile #1") each with correctly directed, distance-labeled,
walkability-verified exits; `get NAME` matches; a missing name returns a
clean `{error: "not found"}`. Full detail: `decisions/DECISIONS.md`
2026-09-10 (latest row).

**Cross-session coordination, this session**: another session,
`df-automation-7d`, is working the same repo concurrently on `main` (its
own worktree), building independent per-viewer pan/Z-level camera control
for the public live-view feed via `RemoteFortressReader`. Confirmed
directly with them: no data-path overlap (this session's work never reads
RFR or raw tile geometry, theirs never touches `dfhack.buildings`/
`dfhack.burrows`), and flagged that both sides' scripts share the same
`dfhack-run`/RPC server on VM 103, so either side should tell the user
before deploying anything that runs continuously.

### Next

1. **DONE (same session): `check_reachable`'s stopgap replaced with named
   landmark endpoints, and `near_landmark` wired into
   `get_connectivity_report`.** `df-overseer-landmarks.lua` now exports
   `get_landmark_centroid(name)`/`nearest_landmark(x,y,z)` via `reqscript`
   (needed an undocumented-locally `--@module = true` directive, found by
   reading how `warn-stranded.lua` declares itself reqscript-able).
   `df-overseer-connectivity.lua`'s `check FROM TO` now takes landmark
   names (old unit-id form kept as `check-units A B` for debugging), and
   stranded groups in `report` carry `near_landmark`/`direction`/
   `distance_tiles`. Verified live against Uniboslan: named `check`
   works both ways (found and not-found), `check-units` still works.
   **Honest gap**: `near_landmark` enrichment's actual code path (not
   just the empty-list case) is unverified live — Uniboslan has no
   stranded citizens to test against, and manufacturing one felt too
   disruptive to the live fort just for a query-tool test. →
   `decisions/DECISIONS.md` 2026-09-10 (latest row).
2. **DONE (same session): `get_overview()`/context tiering built, build
   order item 4.** New `df-overseer-overview.lua`, composing
   `list_landmarks()` (tier1) and `get_connectivity_report()` (tier2
   alerts, rendered as real sentences) via `reqscript`. Found and fixed a
   second real `reqscript` requirement: loading a module ran its CLI
   dispatch code too, printing stray "usage: ..." lines ahead of the
   JSON, because the module-load call passes an internal table as `...`
   that matches none of the CLI's expected subcommands. Fixed with the
   `dfhack_flags.module` early-return guard `warn-stranded.lua` already
   uses. Also fixed: `list_landmarks()` now sorts landmarks and their
   exits by name, not engine iteration order, for turn-to-turn JSON
   stability. Verified live: `df-overseer-overview get` returns clean
   JSON, zero stray lines. **Deliberately not implemented, flagged not
   faked**: `resource_summary` (needs a real prospect-equivalent scan)
   and `get_diff_since`/event-driven tier2 (build order item 5, separate
   later work). → `decisions/DECISIONS.md` 2026-09-10 (latest row).
3. **DONE (same session): `get_diff_since()` built via `eventful`, build
   order item 5.** New `df-overseer-diff.lua`: registers
   `JOB_COMPLETED`/`UNIT_DEATH` handlers once per DF process lifetime,
   appends to an in-memory `_G` ring buffer with a monotonic id, `since
   CURSOR` drains past it. Verified a load-bearing assumption live first:
   a plain Lua global genuinely persists across separate `dfhack-run`
   invocations within the same running DF process (two independent calls
   incrementing a counter returned 1 then 2), then the log/cursor logic
   itself (synthetic entries first). **Gap closed later the same
   session**: with the user's explicit go-ahead, briefly unpaused the
   fort (~15s real time), designated and watched a real wall tile get
   dug, and confirmed `since` returned the genuine resulting
   `JOB_COMPLETED` event with correct tick/cursor — the actual
   eventful→callback wiring, not just synthetic injection. Re-paused and
   quicksaved immediately after; verified the quicksave actually landed
   via `world.sav` mtime, not just the call's exit code. Two harmless
   "TEST:"-labeled entries remain in the in-memory log from the earlier
   synthetic test, cleared on next DF restart. Build order item 5 is now
   fully verified, no remaining gap. →
   `decisions/DECISIONS.md` 2026-09-10 rows.
4. **DONE (2026-09-11, resumed session): `find_open_area` (terrain=
   "built") built, build order item 6.** New
   `df-overseer-openarea.lua`: a `near`-landmark-anchored, radius-capped
   (hard cap 60, clamped in code) scan for WxH windows of free tiles
   (walkable, no building on it), ranked by distance to the anchor and
   deduplicated to non-overlapping placements, each described via its own
   nearest landmark. A plain per-window check, not the histogram/stack
   algorithm the research doc sketches — simpler to verify correctly and
   cheap enough at this project's actual room scale. Verified live: a
   findable 1x1 (the earlier test dig), a correctly-empty 5x5 (the room
   is entirely covered by its own stockpile — a real "whole area is one
   building" case), 5 distinct non-overlapping 2x2 surface candidates
   near "Wagon", and an explicit not-found error for a bad landmark name.
   → `decisions/DECISIONS.md` 2026-09-11.
5. **Not done in this pass**: the research spec's `via` (path-type
   classification, e.g. "corridor") exit field is deliberately not
   implemented. Would need real path-tracing this slice doesn't attempt.
6. **Not done this session, still open from an earlier handover**: the
   `find_mm_*` Y-axis transform mystery (cheap, read-only, not blocking).
7. **Worth deciding, not urgent**: whether to pull an actual
   `install_df.py backup` of Uniboslan's save now that this session found
   out the hard way that none had ever been taken of a fort-bearing save.
8. **Not pushed**: committed locally to `perception-layer-experiments`,
   per this repo's rule, needs explicit go-ahead before `git push`.

### Durable traps, still true (additions marked NEW)

- NEW: **Directly changing a live fort's pause state (`dfhack.world.SetPauseState(false)`) is blocked by Claude Code's own auto-mode classifier**, categorically — it rejected the identical call twice even after explicit conversational "go ahead" from the user each time, and only went through once the user changed a Bash permission setting (exited auto mode / adjusted `.claude/settings.json`). Conversational approval alone does not satisfy this gate for this class of action; don't retry the same call expecting a different result after a chat-level "yes," and don't try to route around it with an equivalent raw struct write — surface it and wait for the user to actually adjust the permission.
- NEW: **`quickfort run <file>` resolves a plain filename relative to `dfhack-config/blueprints/`, not the working directory or an absolute path** — `quickfort run /opt/df/foo.csv` fails with `"failed to open dfhack-config/blueprints//opt/df/foo.csv"` (the two paths get concatenated, not replaced). Write ad-hoc blueprints directly into that directory.
- **VM 103 is running DF unattended with no network isolation boundary.**
  home-lab's `memory/tailscale-architecture.md` assigns `df-fortress`/
  `df-colony-01` to `tag:ai-sandbox` — "unattended, possibly LLM-driven,
  lowest trust that isn't internet-facing" — but `runbooks/tailscale-topology.md`
  Phase 5 (the actual hard gate) is still unchecked. **Not this repo's to
  fix** — host-level Tailscale/ACL work, forbidden to any agent by
  home-lab's own rule.
- **DF ignores SIGTERM.** Quicksave before stop is mandatory once a fort
  is live; a bare stop takes the full timeout and ends in SIGKILL. **This
  is now load-bearing, not theoretical** — a real fort has existed since
  2026-09-10 and must be quicksaved before any future stop.
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
- **`gui.simulateInput`'s generic keys don't work on DF v50+'s native
  button-style menus, and this extends to WASD map-panning and all four
  `CURSOR_*` directions too** — confirmed dead (pixel-identical
  before/after, and unchanged struct fields) on `choose_start_sitest`'s
  camera panning and cursor movement specifically, alongside the
  already-known title-screen/region-list menu cases. Mouse clicks
  (buffer-scan for text, compute coordinate, `_MOUSE_L`) remain the only
  confirmed-working input method for menu-style screens. **Note the
  exception found this session**: real `xdotool`-driven WASD (not
  DFHack's fake input) does work for camera panning, including while
  `choosing_embark` is `true`.
- **`find_mm_*` (Site Finder's match output) and
  `neighbor_hover_mm_*`/`warn_mm_*` (the real, committable embark
  rectangle) are two different coordinate frames — never write `find_mm_*`
  directly into `warn_mm_*`.** `warn_mm_*`/`neighbor_hover_mm_*` are
  confirmed world-absolute (live-matched exactly against
  `location.embark_pos_min/max`, real names `abs_mm_start`/`abs_mm_end`);
  `find_mm_*` is not. See `research/2026-09-10-embark-screen-rendering-and-coordinates.md`.
- **`df.global.gps.precise_mouse_x/y` (real pixel-level mouse state) works
  in headless Xvfb via `xdotool`** (`DISPLAY=:99 xdotool mousemove/keydown/keyup`)
  — the fix for map hover-info, map clicks, and WASD camera panning, none
  of which DFHack's fake `gui.simulateInput` can drive. Calibration: DF
  window sits at `+0,+40` within the virtual display; `precise_mouse_x =
  real_X11_X`, `precise_mouse_y = real_X11_Y - 40`.
- **`xdotool`'s `click` action has no default inter-step delay in this
  version** — a bare `mousemove X Y click 1` is flaky. Use explicit
  `mousemove` → `sleep 0.3` → `mousedown 1` → `sleep 0.2` → `mouseup 1`.
- **There is no rendered mouse cursor sprite anywhere in this setup** —
  the only visual position feedback is DF's native ~2×2 blue hover-square
  overlay, confirmed pure native closed-source DF rendering, not settable
  or readable from any source available to this project.
- **`code=exited, status=1` in `systemctl status` means the process called
  `exit(1)` itself, not a signal death** — a core dump will never fire for
  it. Distinguish from `code=killed, status=SIGxxx`.
- **The title screen gains a "Continue active game" button, above "Start
  new game in existing world," once any save exists** — the reliable
  signal a fort has actually been founded.
- **A founded fort's real save directory is not necessarily "region2"**
  (or whatever `cur_savegame.save_dir` said pre-embark) — check
  `df.global.world.cur_savegame.save_dir` on the live fort itself.
- **`df-overseer-ui.lua`'s `click` self-reported `FAIL` on clicks that had
  actually worked** — its success check (does the scanned text disappear)
  is unreliable when the same screen persists with the text still present,
  or a duplicate match exists elsewhere. Verify with `type` or a field
  read. Not yet fixed in the script.
- **Writes to `neighbor_hover_mm_*` alone, and `gps.mouse_x/y` alone
  without an accompanying click in the same call, do not move anything
  visually** — these behave like render-loop-derived outputs, not
  authoritative inputs. **Refined this session**: `neighbor_hover_mm_*`
  specifically only live-updates from real mouse *movement* (no click
  needed) while `scr.choosing_embark` is `true`; during ordinary zoomed
  browsing it's frozen regardless. `zoomed_in` is the opposite case — it
  CAN be set directly and does affect which screen renders next.
- **DF's "Re-run finder" confirmation dialog offers only "P: Pause this
  confirmation" or "Enter: Yes, proceed" — no plain cancel.** `CUSTOM_P`
  dismisses it without losing the existing match.
- **A full-tree file-manifest diff must tab-separate size and path**
  (`find ... -printf '%s\t%P\n'`, split with `awk -F'\t'`), not
  space-separate.
- **`dfhack-run lua -f script.lua ARG1 ARG2` passes arguments via Lua
  varargs (`local x, y = ...`), not a global `arg` table.**
- **Site Finder's "Begin" needs at least one non-N/A criterion set, or it
  silently no-ops forever.**
- **`load-save.lua`'s `sel_menu_line`-on-`viewscreen_titlest` approach
  does not apply to this build.** Tagged `unavailable`, don't re-attempt.
- **A checksum must never pass through an LLM-summarized web fetch** —
  fetch it directly with `curl` and compare byte-for-byte.
- **`.env` appends must check for a trailing newline first** —
  `install_df.py`'s `_append_env_var()` helper does this.
- NEW: **`LEAVESCREEN` cleanly cancels `viewscreen_choose_start_sitest`'s
  `choosing_embark` mode with no side effect** (`warn_mm_*` stays
  `-1,-1,-1,-1`) as long as the local map itself was never clicked — a
  safe way to test or abort a placement attempt without committing
  anything.
- NEW: **A long payload embedded directly in an SSH command string
  silently truncates at ~8182 characters when Git's MSYS-linked `ssh.exe`
  is spawned by a native Win32 process (Python's `subprocess`) rather than
  a POSIX one (bash)** — no error, exit 0, the remote side just runs a
  truncated command. `provision_vm.ssh_guest` now takes `input_data` to
  pipe a payload over stdin instead; `install_df.remote()` uses it. Never
  embed an unbounded-size payload directly in an SSH command string again
  — see `provision_vm.ssh_guest`'s docstring and
  `decisions/DECISIONS.md` 2026-09-10 for the full mechanism.
- NEW, **the costly one — read before ever founding another fort while
  one already exists**: **DF's save-slot names (`autosave 1`, `autosave 2`,
  `current`) are a shared generic pool, not scoped per fort.** Founding
  Uniboslan overwrote Artobcatten's actual save data, which lived in
  `autosave 1` — confirmed via `md5sum`, `autosave 1/world.sav` and
  `autosave 2/world.sav` are now byte-for-byte identical, both holding
  Uniboslan's state, with no trace of Artobcatten's left anywhere
  (`current` empty, `region1`/`region2` are pure world-gen history, no
  backup ever taken). **Before founding any future additional fort**: pull
  an `install_df.py backup` of every existing save first, since this
  install's save naming gives no guarantee that an existing fort's slot
  survives a new one being founded.
- NEW: **A crash matching the first fort's "Confirm" signature
  (`code=exited, status=1`, no core dump) can also trigger at the
  map-click step, not just Confirm** — same `gdb`-wrapped-launch
  workaround applies (see the RESOLVED entry above), just don't assume the
  race is scoped to one specific click.
- NEW: **Restarting the embark flow from the title screen does not
  reliably return to the same world/coordinate frame as wherever a stale,
  not-yet-committed embark attempt was sitting** — this session's fresh
  "Start new game in existing world" landed in `region1`, not the `region2`
  the stale mid-navigation state (and its `neighbor_hover_mm_*` numbers)
  belonged to. Re-verify the actual world/region reached (region name text
  on the embark screen, not just numeric coordinates matching a prior
  session) before reusing any previously-found coordinates.
- NEW: **A real `xdotool` click on a genuinely valid, placeable tile can
  go straight through the whole embark-placement flow to
  `viewscreen_setupdwarfgamest`**, with no `warn_mm_*` force-write and no
  separate Confirm click at all — different from the first fort's
  documented sequence. Not fully explained (possibly the force-write/
  Confirm dance was compensating for something specific to DFHack's fake
  input on an earlier attempt, not an inherent property of the flow).
  Worth confirming if a third embark is ever attempted.
- NEW: **The tutorial intro dialogs ("Quick start and short tutorial?",
  "On your own!") render as overlays on `viewscreen_choose_start_sitest`
  itself, not as separate viewscreen types** — they do reappear on each
  fresh embark attempt (this session briefly assumed otherwise after they
  didn't show up in the very first `type` check, before actually dumping
  the screen and finding them present).

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

- Sections for the week of 2026-08-24 moved to
  [`working-archive/Working_archive-2026-08-24.md`](working-archive/Working_archive-2026-08-24.md).
- 2026-08-27 through 2026-09-08: provisioning build, host-RAM blocker,
  perception eval, fort ledger, VM-start, provisioning-hardening,
  DF-install-scripting, systemd-unit handovers — all moved wholesale to
  [`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md)
  as each was superseded or reported itself finished.
- 2026-09-09: the 2026-09-08 (evening) handover moved wholesale to the
  same archive file.
- 2026-09-09 (end of session): this session's full handover (title-screen
  bootstrap resolution, the entire live-viewing/relay/tunnel build, the
  tileset investigation, and the Site Finder "Begin" resolution) moved
  wholesale to the same archive file — exceeded the ~400-line threshold,
  not superseded. The handover above is the tight current-state summary;
  the archive has the full detail.
- 2026-09-10: the 2026-09-09 (end of session) handover moved wholesale to
  the same archive file, superseded by this session's own handover above
  (Cloudflare Tunnel completion, the graphics-completeness fix, and the
  live embark-flow attempt).
- 2026-09-10 (second handover today): that session's own handover moved
  wholesale to the same archive file, superseded by this session's handover
  above (the click-registration mystery resolved, the real embark mechanism
  found, and the new "Confirm" crash).
- 2026-09-10 (third handover today): that session's own handover moved
  wholesale to the same archive file, superseded by this session's handover
  above — **the first fort was founded**, and the "Confirm" crash resolved
  empirically via gdb.
- 2026-09-10 (fourth handover today): that session's own handover moved
  wholesale to the same archive file, superseded by this session's handover
  above — the `find_mm_*`/`warn_mm_*` coordinate-frame bug found, and
  `xdotool` real-input fix for headless map/hover interaction discovered
  and validated.
- 2026-09-10 (fifth handover today): that session's own handover moved
  wholesale to the same archive file, superseded by the handover at the top
  of this file — the text-only sweep built and run, a Windows-specific SSH
  command-line truncation bug found and fixed in `provision_vm.ssh_guest`/
  `install_df.remote()`, and a strong second-site candidate found
  (`sx=128 sy=84 ex=131 ey=87`), left uncommitted for the user's call.
