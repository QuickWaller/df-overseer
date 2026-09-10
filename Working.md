# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.

## HANDOVER - 2026-09-10 (end of session, fifth handover today)

The prior handover from earlier the same day is archived wholesale —
[`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md),
superseded by this one. **This session's result: the text-only sweep is
built and working, a real Windows-specific SSH deployment bug got fixed
along the way, and a genuinely strong second-site candidate was found —
nothing committed, that decision is left for the user.**

### State at a glance

- **DF is idle at `viewscreen_choose_start_sitest`, `zoomed_in=true`,
  `choosing_embark=false`, `warn_mm_startx=-1` (nothing committed).**
  Camera is currently centered near `zoom_cent≈151,86` (moved there this
  session from the prior idle position, deep in open ocean, to search near
  the original Site Finder match area). The first fort ("Artobcatten,
  Combinedchannel," `region2`, `save/autosave 1`) is untouched, safely
  saved, not currently loaded. `df-fortress.service` is `active`.
- **Committed the prior session's own doc updates** (they'd been left
  uncommitted) as `169fc21`, then did this session's work on top. Nothing
  pushed — local commits only, per the push-needs-explicit-go-ahead rule.
- **Extended `df-overseer-ui.lua`** with `embark-mode` (click the real
  Embark button, row 57), `leave-embark-mode` (`LEAVESCREEN`, no side
  effect), and `hover` (read `neighbor_hover_mm_*` plus buffer-scanned
  ocean/aquifer/soil/biome/trees flags in one call). Deployed via
  `install_df.py ui-install`, all three confirmed working live.
- **Found and fixed a real, previously-latent Windows-specific SSH bug**
  while deploying the above: the first `ui-install` attempt reported
  success but silently failed to update the file (Git's MSYS-linked
  `ssh.exe` truncates a command-line argument to ~8182 characters when
  spawned by Python's `subprocess`, a native Win32 process, but not when
  spawned by bash) — see the durable-traps section and
  `decisions/DECISIONS.md` for the full mechanism and fix
  (`provision_vm.ssh_guest`'s new `input_data` param, `install_df.remote()`
  now pipes its payload over stdin). `provision_relay.py` inherits the fix
  for free.
- **New mechanic found, not in the prior research doc**:
  `neighbor_hover_mm_*` only live-updates from real mouse movement while
  `scr.choosing_embark` is `true` — during ordinary zoomed browsing it's
  frozen, even though the text-panel hover info updates live in both
  modes. A sweep has to enter `choosing_embark` mode and stay there
  throughout. Also confirmed: `LEAVESCREEN` cleanly cancels
  `choosing_embark` with no side effect, and WASD panning keeps working
  while `choosing_embark` is `true` — no need to leave the mode to pan
  between samples.
- **Ran the sweep live**: navigated the camera from its idle position
  (deep ocean) back toward the original Site Finder match's neighborhood
  (`region_pos 9,5`, absolute `~150,79`) using WASD taps toward the
  target, checking `zoom_cent_x/y` between taps. A 5×5-point raster there
  found real land immediately — no ocean anywhere in that viewport,
  mostly `Temperate Shrubland`/`Temperate Conifer Forest`/`Mountain`,
  several points with no aquifer.
- **Found a genuinely strong candidate, full-detail-checked, nothing
  committed**: absolute embark rectangle **`sx=128 sy=84 ex=131 ey=87`**
  (`neighbor_hover_mm_*`, the confirmed world-absolute frame — this is
  exactly what would go into `warn_mm_*` to actually commit it). Temperate
  Conifer Forest, Warm, Heavily Forested, Thick other vegetation, **DF's
  own "Recommended size" flag present**, Deep soil (Clay/Sand — better
  than the first fort's "Little soil"), no aquifer, full mineral suite
  (Iron/Gold/Silver/Copper/Nickel/Zinc/Platinum/Tin/Lead) plus a Flux
  stone layer (steel-capable). One real caution: hostile Goblins "a short
  trip east" (closer than ideal, not disqualifying). Left the screen
  clean afterward — `leave-embark-mode` confirmed, nothing committed.

### Next: the user's call on this candidate, then the fort's fate

1. **This session deliberately did not commit the candidate above.**
   Founding a second fort is exactly the kind of decision
   `Working.md`/`ROADMAP.md` have been flagging as needing the user, not
   an auto-execute — surface `sx=128 sy=84 ex=131 ey=87` and ask.
2. To actually commit it: enter `embark-mode`, `xdotool mousemove` to a
   pixel within that rectangle (`px≈280,360` at the current camera
   position — recompute if the camera has moved since), a real click sets
   `warn_mm_*` correctly (confirmed this session that a real click
   produces correct world-absolute values, same mechanism as the first
   fort's placement), then re-set `warn_flags.GENERIC=true` if needed,
   click through to "Confirm" (watch for the known timing/race crash — run
   under `gdb` if it recurs) → "Play now!" → a second real fort.
3. Once a good second fort exists (or the user decides the first,
   "Artobcatten," is good enough after all, or to abandon one): decide
   whether to keep both, abandon one, or move on. The fort(s) are still
   standing, not being played — no perception layer, no agent exists yet.
   `docs/PURPOSE.md`'s build order (`check_reachable`/`get_connectivity_report`
   first) is the next real code to write regardless, unchanged by this
   session — see `ROADMAP.md`'s "Next" bucket.
4. **Not done this session, still open from the prior handover**: the
   `find_mm_*` Y-axis transform mystery (cheap, read-only, not blocking —
   the sweep found a candidate without needing it).

### Durable traps, still true (additions marked NEW)

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
