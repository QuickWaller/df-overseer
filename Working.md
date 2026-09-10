# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.

## HANDOVER - 2026-09-10 (end of session, fourth handover today)

The prior handover from earlier the same day is archived wholesale —
[`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md),
superseded by this one. **This session's big result: the actual root
cause of the whole night's map-navigation struggle, found and fixed.**

### State at a glance

- **The first fort ("Artobcatten, Combinedchannel," `region2`,
  `save/autosave 1`) still exists, safely saved, currently not loaded.**
  Not touched this session. DF is instead sitting mid-navigation on a
  **second, not-yet-committed** embark attempt: `viewscreen_choose_start_sitest`,
  `zoomed_in=true`, `choosing_embark=false`, `warn_mm_* = -1,-1,-1,-1`
  (nothing committed), `location.region_pos = (9,5)`, `find_results=2`
  (stale, from an earlier search). This is a safe, non-fragile idle state
  — nothing will progress or crash on its own while left here. `df-fortress.service`
  is `active` under systemd.
- **Root cause found: two different coordinate frames were being treated
  as one, and that's what actually broke navigation all night, not a
  camera/rendering bug.** `neighbor_hover_mm_*`/`warn_mm_*` are confirmed
  **world-absolute** embark-tile coordinates (live-matched, exactly, against
  `location.embark_pos_min/max`, whose real decompiled names are literally
  `abs_mm_start`/`abs_mm_end`). `find_mm_*` (Site Finder's own match
  output) is a **different, smaller-magnitude, non-absolute** coordinate.
  Every time earlier tonight `warn_mm_*` was force-written directly from
  `find_mm_*` (e.g. `(6,8,9,11)`), that was writing nonsense-scale
  coordinates near the map's origin corner, not the intended site — this
  is *the* explanation for "the same forced numbers landed in wildly
  different real places every time," not a camera/zoom/rendering issue as
  suspected for most of the session. Full trail, live-verified via direct
  struct reads (not inference): `research/2026-09-10-embark-screen-rendering-and-coordinates.md`.
  One sub-question is still open: the wiki's "one region tile = 16×16
  embark tiles" fact gives `region_pos.x*16 + find_mm_sx` matching
  `neighbor_hover_mm_sx` exactly, but the same formula on Y is off by a
  consistent, unexplained 9 (the sample wasn't time-aligned —
  `doing_site_finder` was already `false` when read). **Single recommended
  test, cheap and read-only**: run Site Finder fresh ("Begin"), immediately
  read `find_mm_*` + `neighbor_hover_mm_*` + `location.region_pos` in one
  atomic `dfhack-run lua` call. Not blocking — see below.
- **Separately, and just as important: found why the map itself was
  fundamentally unsteerable all night, and fixed it.** `df.global.gps.precise_mouse_x/y`
  (the real, pixel-level mouse state that map hover-info, map clicks, and
  WASD camera panning all actually depend on, as opposed to
  `gps.mouse_x/y`, the coarse character-grid position DFHack's fake
  `gui.simulateInput` *can* set and which only text buttons need) is
  polled live from the real OS mouse every frame — confirmed via DFHack's
  own `enabler.get_precise_mouse_coords` vmethod. Headless Xvfb has no
  real mouse, so it sat permanently frozen all night regardless of any
  Lua write. **Fix**: install `xdotool` (`apt-get install -y xdotool`,
  not present by default) and drive REAL X11 input against the Xvfb
  display directly — `DISPLAY=:99 xdotool mousemove/keydown/keyup` —
  which genuinely updates `precise_mouse_x/y`, unblocks real hover-info
  readouts, real map clicks, and real WASD panning, none of which
  DFHack's fake input path can ever drive. Calibration, live-confirmed
  exact: the DF window sits at `+0,+40` within the virtual display (no
  window manager; `xwininfo` gives this directly), so
  `precise_mouse_x = real_X11_X` and `precise_mouse_y = real_X11_Y - 40`.
  `xdotool getmouselocation --shell` (needs `DISPLAY=:99` set explicitly —
  not inherited over SSH) is a valid independent cross-check.
- **`xdotool` click reliability**: a bare `mousemove X Y click 1` is
  flaky — confirmed via `xdotool`'s own docs that this build's `click`
  path has **no default inter-step delay**. What worked reliably all
  night: explicit `mousemove` → `sleep 0.3` → `mousedown 1` → `sleep 0.2`
  → `mouseup 1`. Minimum viable hold time was not characterized (untested
  whether shorter holds work); DF's own `G_FPS_CAP:50` (~20ms/frame) is
  offered only as a plausible order-of-magnitude floor, not measured.
- **WASD panning via `xdotool keydown`/`keyup` genuinely works** (unlike
  DFHack's fake-input WASD, confirmed dead again this session, pixel-identical
  screenshots before/after) — but panning speed for this specific tiny
  17×17-embark-tile "pocket" world is very fast relative to hold-time: a
  0.5s hold overshot the entire visible island into open ocean; ~0.05s
  taps gave small, controllable increments. Not calibrated to an exact
  tiles-per-second figure.
- **The visual "green = Site Finder match / red = existing site, can't
  settle / no highlight = valid but not a Finder pick" overlay legend
  was confirmed live by the user watching the actual feed** (matches the
  DF Wiki's "Site finder" page too, pasted in this session). The green
  overlay reliably appeared right after Site Finder's "Begin" but seemed
  to stop rendering after further interaction even though `find_results`/
  `find_mm_*` stayed intact underneath — `doing_site_finder` is the
  best-supported (live-observed, not proven) gate candidate; "we just
  panned away and it was still there" was not ruled out. There is also
  **no rendered mouse cursor sprite at all** in this setup (confirmed by
  the user watching live) — the only visual position feedback is DF's own
  native ~2×2 blue hover-square overlay, confirmed (via a subagent's
  GitHub-code-search of the entire DFHack C++ source, zero hits for
  `neighbor_hover_mm_*`/`warn_mm_*`/`find_mm_*`/`warn_flags` anywhere) to
  be **pure native, closed-source DF engine rendering** — not a DFHack
  overlay, not settable, not readable from any source this project has
  access to. This is a confirmed hard limit, not a gap to keep digging at.
- **Decided approach going forward, agreed with the user**: don't chase
  the visual overlay or try to reproduce `find_mm_*`'s exact transform.
  Since a real `xdotool` click already produces a correct, world-absolute
  `warn_mm_*` directly (confirmed working), do a **text-only sweep**:
  move the real cursor to successive candidate tiles (panning the camera
  to keep pace, so the sweep is also visible to anyone watching the live
  feed — the user specifically wants viewers to see the AI's search
  happening, not just infer it from logs), read the hover-info side panel
  and the placement-warning dialog (both plain character-buffer text,
  already proven 100% reliable all night, zero image dependency, squarely
  within design commitment #1's "never decide from a rendered map" rule),
  and commit the first candidate that matches desired criteria and comes
  back clean (no salt water / aquifer / mountain / "another site" warning).
  **Not yet implemented** — this is the concrete next step.
- **`docs/DF-UI-AUTOMATION.md`'s screen atlas now covers the full chain**
  through `viewscreen_setupdwarfgamest` ("Play now!") and
  `viewscreen_dwarfmodest` (fortress mode), plus the title screen's new
  "Continue active game" button that appears once a save exists.

### Next: implement the text-only sweep, then decide the fort's fate

Two independent threads, in order:
1. **Optionally**, run the one atomic read described above to settle the
   `find_mm_*` transform's Y-axis mystery — cheap, read-only, not
   blocking anything.
2. **Build and run the text-sweep** (see above) to find and commit a
   genuinely good second site — camera panning in sync with the sweep so
   it's visible on the live feed, not just log output.
3. Once a good second fort exists (or if the first one, "Artobcatten," is
   judged good enough after all — it was never actually re-examined
   in detail beyond "mostly ocean, bad"), decide whether to keep both,
   abandon one, or just carry on: the fort is still standing, not being
   played — no perception layer, no agent exists yet. `docs/PURPOSE.md`'s
   build order (`check_reachable`/`get_connectivity_report` first) is the
   next real code to write, unchanged by tonight, see `ROADMAP.md`'s
   "Next" bucket.

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
  confirmed-working input method for menu-style screens.
- **RESOLVED, was flagged NEW last session**: the "off-center clicks don't
  register" theory is disproven — the real cause was a whole-screen text
  scan false-matching an earlier occurrence of the target string. See
  `docs/DF-UI-AUTOMATION.md`. Whenever scanning for button text, scope the
  scan to the specific row/region the real button is known to be on if
  the same or similar text could appear elsewhere on screen first.
- **RESOLVED, was flagged NEW last session**: `df.global.gps.precise_mouse_x/y`
  is a live OS-polled pixel-space mouse position (`enabler`'s
  `get_precise_mouse_coords` vmethod, confirmed via DFHack's own
  `df-structures` source), not a writable struct field — it's clobbered
  by the next poll before a Lua write can affect anything. Don't try
  writing it again for mouse automation; `gps.mouse_x/y` (the character-grid
  position) is the real input.
- **RESOLVED, was flagged NEW earlier today**: The Embark button (row 57)
  resets `warn_mm_*` to `-1,-1,-1,-1` and flips `choosing_embark` to
  `true` when clicked — the committed Site Finder match does not survive
  that click and must be re-applied (along with `warn_flags.GENERIC`)
  after the subsequent map click, not just once up front. Still true and
  load-bearing, just no longer "new."
- **RESOLVED, was flagged NEW earlier today**: clicking "Confirm" crashed
  DF/DFHack outright, three times reproduced, two other hypotheses ruled
  out (a skipped native accept step; a rectangle mismatch). The real cause
  is a **timing/race condition** — running under `gdb` avoided it
  entirely, though the exact mechanism is unconfirmed (the gdb catchpoint
  never actually fired). If this crash recurs on a future embark, running
  it under gdb again is the known workaround. See
  `decisions/DECISIONS.md` 2026-09-10 ("First fort founded") and
  `docs/DF-UI-AUTOMATION.md` for the full trail.
- NEW: **`find_mm_*` (Site Finder's match output) and
  `neighbor_hover_mm_*`/`warn_mm_*` (the real, committable embark
  rectangle) are two different coordinate frames — never write `find_mm_*`
  directly into `warn_mm_*`.** `warn_mm_*`/`neighbor_hover_mm_*` are
  confirmed world-absolute (live-matched exactly against
  `location.embark_pos_min/max`, real names `abs_mm_start`/`abs_mm_end`);
  `find_mm_*` is not. This was the actual cause of "the same forced
  coordinates landed in wildly different real locations" all night, not a
  camera bug. See `research/2026-09-10-embark-screen-rendering-and-coordinates.md`.
- NEW: **`df.global.gps.precise_mouse_x/y` (real pixel-level mouse state)
  can be made to actually work in headless Xvfb by installing `xdotool`
  and sending it real X11 input** (`DISPLAY=:99 xdotool mousemove/keydown/keyup`
  against the Xvfb display) — this is the fix for map hover-info, map
  clicks, and WASD camera panning, none of which DFHack's fake
  `gui.simulateInput` can ever drive (confirmed: that fake path only
  updates the coarse character-grid `gps.mouse_x/y`, which text buttons
  need but the map does not). Calibration: the DF window sits at `+0,+40`
  within the virtual display (no window manager, `xwininfo` gives this
  directly) — `precise_mouse_x = real_X11_X`, `precise_mouse_y = real_X11_Y - 40`.
  `xdotool getmouselocation --shell` cross-checks this independently
  (needs `DISPLAY=:99` set explicitly, not inherited over SSH).
- NEW: **`xdotool`'s `click` action has no default inter-step delay in
  this version** — a bare `mousemove X Y click 1` is flaky. Use explicit
  `mousemove` → `sleep 0.3` → `mousedown 1` → `sleep 0.2` → `mouseup 1`
  instead; this was empirically reliable all night. Minimum viable hold
  time not characterized.
- NEW: **There is no rendered mouse cursor sprite anywhere in this setup**
  (confirmed live by the user watching the actual feed) — the only visual
  position feedback is DF's native ~2×2 blue hover-square overlay, which
  is confirmed (GitHub-code-search of the entire DFHack C++ source: zero
  hits for `neighbor_hover_mm_*`/`warn_mm_*`/`find_mm_*`/`warn_flags`
  anywhere) to be pure native, closed-source DF rendering — not settable,
  not readable from any source available to this project. Don't spend
  more time trying to locate or drive it directly; use the hover-info
  panel text and placement-warning text instead, both of which are
  reliable and buffer-scannable.
- NEW: **`code=exited, status=1` in `systemctl status` means the process
  called `exit(1)` itself — not a signal death — so a core dump will
  never fire for it.** Distinguish this from `code=killed, status=SIGxxx`
  before spending time on core-dump tooling. Confirmed by reading the
  `./dfhack` wrapper script itself: it captures `dwarfort`'s real exit
  code in `ret=$?` immediately after it exits, and an unrelated `tput
  sgr0` cosmetic call (which fails harmlessly on every shutdown under
  systemd's unset `$TERM`, clean or crashed) does not touch `$ret` before
  the final `exit $ret`.
- NEW: **The title screen gains a "Continue active game" button, above
  "Start new game in existing world," once any save exists** — the
  reliable signal to check for whether a fort has actually been founded,
  rather than inferring it from screen type alone.
- NEW: **A founded fort's real save directory is not necessarily
  "region2" (or whatever `cur_savegame.save_dir` said pre-embark)** — DF
  named it `"autosave 1"` this time. Check
  `df.global.world.cur_savegame.save_dir` on the live fort itself rather
  than assuming it matches the world it was founded in; `region1`/`region2`
  remain pure world-history folders (they gain `unit-*.dat`/`world.dat`
  from worldgen's own history simulation, not from a player fort — don't
  mistake that for fort save data).
- NEW: **`df-overseer-ui.lua`'s `click` self-reported `FAIL` twice this
  session on clicks that had actually worked** (`"Fortress"`,
  `"Skip tutorial"`, `"Okay"`) — its success check (does the scanned text
  disappear) is unreliable when the same screen persists with the text
  still present, or a duplicate match exists elsewhere. Verify with
  `type` or a field read, don't trust its FAIL/PASS report alone. Not yet
  fixed in the script.
- NEW: **Writes to `neighbor_hover_mm_*` alone, and `gps.mouse_x/y` alone
  without an accompanying click in the same call, do not move anything
  visually** — confirmed by direct write-then-screenshot tests. These
  behave like render-loop-derived outputs in practice for at least some
  fields, not authoritative inputs; `zoomed_in` is the opposite case — it
  CAN be set directly and does affect which screen renders next (regional
  vs. local map). Which fields are real inputs vs. render-derived outputs
  is inconsistent and not yet mapped out systematically.
- NEW: **DF's "Re-run finder" confirmation dialog** (triggered by clicking
  "Begin" again once a match already exists) **offers only "P: Pause this
  confirmation" or "Enter: Yes, proceed" — no plain cancel.** `CUSTOM_P`
  dismisses it without losing the existing match (confirmed: `find_mm_*`
  unchanged afterward). Don't press Enter here unless you actually want to
  discard the current match and re-search.
- NEW: **A full-tree file-manifest diff must tab-separate size and path**
  (`find ... -printf '%s\t%P\n'`, split with `awk -F'\t'`), not
  space-separate — `data/vanilla`'s own `examples and notes/` and
  `interaction examples/` folders have spaces in their names and silently
  corrupt a naive `awk '{print $2}'` split, producing false "missing file"
  entries for an unrelated stray word. Both are non-module reference/example
  docs outside the `vanilla_*` naming convention, not real content, so this
  didn't hide a real gap this time, but would have been easy to miss.
- NEW: **`dfhack-run lua -f script.lua ARG1 ARG2` passes arguments via Lua
  varargs (`local x, y = ...`) inside the script, not a global `arg`
  table** — `arg` is nil in this execution context.
- **Site Finder's "Begin" needs at least one non-N/A criterion set, or it
  silently no-ops forever.** Solved 2026-09-09, see archive for the full
  A/B test.
- **`load-save.lua`'s `sel_menu_line`-on-`viewscreen_titlest` approach
  does not apply to this build.** Tagged `unavailable`, don't re-attempt.
- **A checksum must never pass through an LLM-summarized web fetch** —
  fetch it directly with `curl` and compare byte-for-byte.
- **`.env` appends must check for a trailing newline first** —
  `install_df.py`'s `_append_env_var()` helper does this; never use a bare
  `open(path, "a")` again.

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
