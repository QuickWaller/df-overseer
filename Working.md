# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.

## HANDOVER - 2026-09-10 (end of session)

The full blow-by-blow of the 2026-09-09 session is archived wholesale —
[`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md).
This session's own detail lives in this session's tool history, not
archived separately (nothing here exceeded the length that would force
that yet). This handover is the tight, current-state version: what's true
right now, and the one concrete task queued next.

### State at a glance

- **VM 103** (`df-colony-01.internal`, `192.168.2.201`): running DF under
  systemd, idle at `viewscreen_choose_start_sitest` (zoomed in, on
  `region2`), with a confirmed valid Site Finder match (Savagery: Calm,
  `find_mm_sx/sy/ex/ey = 6,8,9,11`, `find_cur_best_value = 10066`) already
  committed into `warn_mm_*`/`warn_flags.GENERIC = true`, and the UI already
  showing "Click 'Embark' to place your fortress." **One click from the
  first fort** — see the queued task below, that click has not been made to
  register yet. Still no fort.
- **Graphics are now genuinely complete**, not just "confirmed rendering."
  2026-09-09's transplant only covered 8 of 10 real `data/vanilla` modules
  (`GRAPHICS_MODULES` in `scripts/install_df.py`). A user-reported missing
  UI panel (later confirmed via external search to be a real expected
  element) led to a full recursive file-manifest diff of *all* of
  `data/vanilla` between the user's Steam install and VM 103, not just
  spot-checks — this found two modules missed because they don't share the
  `_graphics` naming suffix the original list was built around:
  `vanilla_interface` (75 files — UI panel/chrome, including
  `interface_bits_embark.png`, the exact missing panel) and
  `vanilla_environment` (95 files — walls, floors, water, blood, fire,
  ramps: the core terrain tiles used throughout actual fortress-mode play,
  not just this embark screen — would have been a much worse blank-terrain
  bug to hit later). Both added to `GRAPHICS_MODULES` (now 10 entries),
  transplanted, DF restarted, confirmed visually fixed: proper bordered
  panels render everywhere now. `ART_FILES` (11 splash/title/logo assets
  in `data/art`, found missing the same night) also transplanted —
  cosmetic, not confirmed to fix anything specific, just completeness.
- **Public live viewing is fully live and public, not just "built."**
  `https://dwarf-fortress.willsmith.nz` is confirmed working end to end
  (Cloudflare Tunnel → relay → VM 103's noVNC), deliberately
  unauthenticated (`x11vnc -nopw`, still `-viewonly` — anyone with the link
  can watch, nobody can act) with the root URL auto-redirecting straight
  into the viewer. Linked live from `willsmith-portfolio`. Full detail
  already in `decisions/DECISIONS.md` 2026-09-09 rows; nothing more to do
  here.
- **Embark automation was re-driven live, end to end, tonight** — title
  screen → region list → mode select → site selection, confirming the full
  screen sequence exactly matches `research/2026-09-08-embark-automation.md`'s
  predicted chain (`viewscreen_titlest` → `viewscreen_adopt_regionst`
  (loading) → `viewscreen_choose_game_typest` → `viewscreen_update_regionst`
  (loading) → `viewscreen_choose_start_sitest`), plus one screen the
  research hadn't named (`viewscreen_choose_game_typest`, the
  Fortress/Adventurer/Legends picker). The `force_embark()` struct-write
  idiom (`warn_mm_*` = `find_mm_*`, `warn_flags.GENERIC = true`) **partially
  works**: it persists in memory and does flip the UI into the "click
  Embark" sub-mode, but three separate attempts to make the actual Embark
  click register all failed — see the queued task.

### Queued task for next session: make the final "click Embark" register

**Do not restart DF, do not re-run Site Finder, do not re-navigate the
menus.** The state described above (committed match, UI already in the
Embark sub-mode) is exactly where to resume from — confirm with a fresh
`dfhack.gui.getDFViewscreen(true)` field read before touching anything,
per this repo's "verify the verification" rule, since state may have
drifted if DF kept running.

**What's been tried, all unsuccessful, so don't re-attempt these first
without a new idea**:
1. Buffer-scan-and-click on the literal "Embark" button text (the
   technique that reliably works elsewhere on this same screen — Site
   Finder criteria panel, "Skip tutorial", "Okay", "Fortress" all worked
   with retries).
2. A real `_MOUSE_L` click at a screen-pixel position visually estimated
   from a screenshot to land on one of the map's green candidate squares
   (not buffer-verified — the map itself renders via a texture-blit path
   invisible to `dfhack.screen.readTile`, confirmed in the 2026-09-09
   graphics work, so this click's target coordinate was a guess, not a
   scan result).
3. Setting `df.global.gps.mouse_x/mouse_y` **and** a second,
   previously-undiscovered field, `df.global.gps.precise_mouse_x/y`,
   together before the click. `precise_mouse_x/y` was found sitting at a
   fixed `(640, 360)` — suspiciously exactly the center of a 1280×720
   frame — completely unmoved by any of tonight's `gps.mouse_x/y` writes
   despite those writes reading back correctly. This is the most promising
   untested-to-completion lead: **the working theory is that
   `gui.simulateInput`'s `_MOUSE_L` click reliability correlates with
   whether the target is near screen-center** (title screen buttons, mode
   picker: all roughly horizontally centered, worked with retries) **or
   off-center** (the Embark button is bottom-right, the map itself is
   large and mostly off-center: consistently failed) — but setting
   `precise_mouse_x/y` proportionally alongside `mouse_x/y` did NOT
   unblock the Embark click either, so either the scaling/coordinate-space
   conversion used was wrong, or this isn't the actual mechanism and
   something else is.

**Concrete next steps worth trying, not yet attempted**:
- Check whether `precise_mouse_x/y`'s coordinate space is something other
  than the guessed 1280×720 (e.g. a DPI-scaled or letterboxed frame) —
  read DFHack's own source/docs for `gps` rather than inferring from one
  data point.
- Check whether DF actually renders a visible mouse cursor sprite at all
  in this headless Xvfb setup — if it does, a screenshot showing exactly
  where the cursor icon appears vs. where it was set would directly
  confirm or rule out the coordinate-space theory, rather than inferring
  from click success/failure alone.
- Consider whether the map click needs to go through a *different* code
  path than a plain `_MOUSE_L` on `scr` — e.g. a click on a `widget`
  sub-object (`scr.widgets`, seen in the full field dump but never
  explored) rather than the top-level viewscreen.
- If struct-level automation continues to resist, the fallback is a
  genuinely interactive session: the user watching live and directing
  clicks in real time is not available on the current public feed (it's
  `-viewonly`) — re-enabling input for a **private, password-gated**
  session (not the public unauthenticated one) is possible but was not
  set up tonight and would need its own decision, given the security
  reasoning already on record for why the public feed stays view-only.

**Site Finder internals, resolved 2026-09-10, useful context for whoever
continues this**: `research/2026-09-10-site-finder-internals.md` confirms
via DFHack's own `df-structures` that `mm` means "min/max" (in embark
tiles), and via the current DF Wiki page that Site Finder tracks exactly
**one** best-fit candidate (`find_mm_*`/`find_cur_best_value`, scalars,
not a vector) while the map's broader green highlighting is a *separate*
"all acceptable sites" display layer — the other green squares on screen
are real, independently valid sites, just not tracked as a comparable
list anywhere in the struct.

### Durable traps, still true (additions marked NEW)

- **VM 103 is running DF unattended with no network isolation boundary.**
  home-lab's `memory/tailscale-architecture.md` assigns `df-fortress`/
  `df-colony-01` to `tag:ai-sandbox` — "unattended, possibly LLM-driven,
  lowest trust that isn't internet-facing" — but `runbooks/tailscale-topology.md`
  Phase 5 (the actual hard gate) is still unchecked. **Not this repo's to
  fix** — host-level Tailscale/ACL work, forbidden to any agent by
  home-lab's own rule.
- **DF ignores SIGTERM.** Quicksave before stop is mandatory once a fort
  is live; a bare stop takes the full timeout and ends in SIGKILL.
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
- NEW: **A `_MOUSE_L` click's reliability appears to depend on whether the
  target is near screen-center or off-center** — unconfirmed as to why,
  but every off-center click attempt on `choose_start_sitest` (the Embark
  button, the map itself) failed tonight while every roughly-centered
  button elsewhere (title screen, mode picker, Site Finder panel) worked
  with retries. See the queued task above for the `precise_mouse_x/y`
  lead.
- NEW: **`df.global.gps.precise_mouse_x/y` is a second, separate
  mouse-position field from `gps.mouse_x/y`** — found sitting at a fixed
  `(640, 360)` all night regardless of `gps.mouse_x/y` writes succeeding.
  Not yet confirmed as load-bearing (setting both together did not fix the
  Embark click), but a real, previously-undocumented field worth
  understanding before more mouse-automation work on this or other
  screens.
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
