# DF menu/UI automation: what's known, and the reusable tool

**Why this file exists.** 2026-09-09/10's embark-flow work drove DF through
five real menu screens by hand-writing a fresh Lua script over SSH for
almost every single click, re-deriving the same buffer-scan-and-click
technique from scratch each time and scattering what was actually learned
about each screen across `decisions/DECISIONS.md` prose. That's slow, and it
throws away knowledge a future session has to re-earn. This file is the
antidote: a durable catalog of what's confirmed about each screen, plus
pointers to the one reusable tool (`scripts/dfhack/df-overseer-ui.lua`) that
should be used instead of writing another one-off script.

This is about **bootstrapping the game into a running fort** — title screen
through embark. It is not the perception/action layer `docs/PURPOSE.md`'s
build order describes for actually playing a founded fort (`get_overview`,
`find_open_area`, etc.), which is a separate, still-unbuilt system with its
own design commitments. Design commitment #1 (never show the model a
rendered map) is unaffected either way: everything here reads structured
fields and character-buffer text, never an image, for automation decisions.

The first real automation *past* this doc's scope — actually digging and
furnishing a founded fort, not bootstrapping into one — is
`quickfort`-driven, not covered here: see `blueprints/README.md` and
`decisions/DECISIONS.md` 2026-09-10 ("Played Uniboslan forward for real").

## Standing rule: flag every real-input (`xdotool`) fallback, out loud

DFHack's own fake input (`gui.simulateInput`, struct writes) cannot drive
everything — several screens (the map/embark hover, click-registration) only
respond to genuine X11 mouse/keyboard events, which is why this project's
automation falls back to `xdotool` sending real events into VM 103's Xvfb
display (`:99` locally; see the "map itself was unsteerable" section below
for why). **That fallback shares the exact same input channel as any human
VNC session connected to the same display** — there is no separation between
"the AI's simulated hand" and "a person's real hand" at the X11 level once
`xdotool` is involved; both are just events on the same virtual mouse and
keyboard. Once the authenticated personal-control VNC channel exists
(`decisions/DECISIONS.md`, live-viewing thread), a session driving `xdotool`
against VM 103 while a human is also connected would genuinely fight over the
same cursor and keyboard focus.

**Rule: any use of `xdotool` (or any other real-X11-input mechanism) against
VM 103 must be called out explicitly at the point it happens** — in the
session's own output, not buried in a script's stdout nobody reads — never
run silently as a routine implementation detail. This costs nothing when
nothing else is connected (true today — no autonomous agent plays the fort
yet) and is the one habit that keeps this safe once something else might be
watching or driving at the same time.

## The reusable tool

`scripts/dfhack/df-overseer-ui.lua`, deployed onto the guest with
`python scripts/install_df.py ui-install`, then callable directly:

```
./dfhack-run df-overseer-ui type               # print the current real viewscreen type
./dfhack-run df-overseer-ui click "TEXT"       # buffer-scan for TEXT, click its center, retry, verify
./dfhack-run df-overseer-ui dump               # print every non-blank row of the character buffer
./dfhack-run df-overseer-ui embark-mode        # click the real Embark button (row 57), enter choosing_embark
./dfhack-run df-overseer-ui leave-embark-mode  # LEAVESCREEN out of choosing_embark, no side effect
./dfhack-run df-overseer-ui hover              # read the live-hovered tile: neighbor_hover_mm_* + criteria flags
```

`embark-mode`/`leave-embark-mode`/`hover` are the 2026-09-10 (fifth pass) embark-site-sweep helpers — see
the sweep section below for how they're meant to be driven together.

Re-run `ui-install` any time the script changes — it's a plain overwrite,
idempotent, no state to preserve.

**What `click` actually does**, so its limits are clear: scans the full
character buffer for an exact text match (never a pixel/image guess — the
`gui/kitchen-info.lua` label-locator idiom, confirmed live 2026-09-09), sets
`df.global.gps.mouse_x/mouse_y` to the match's center, fires
`gui.simulateInput(scr, '_MOUSE_L')`, then re-scans for the same text as a
success proxy (its disappearance suggests something changed). Retries up to
3 times.

**Known flaw in the success check, found 2026-09-10**: a whole-screen
top-to-bottom text scan matches the *first* occurrence of the target
string, which can be a mention in unrelated help/instructional text above
the real button (`"Embark"` on `viewscreen_choose_start_sitest` is a
concrete example — see the screen atlas entry below). The tool reports
`FAIL` whenever the scanned text is still present afterward even though
the click landed correctly and the screen moved on — this happened twice
live this session on `"Fortress"` and `"Skip tutorial"`/`"Okay"`, all of
which had actually worked; `type`/struct-field checks confirmed the real
outcome in each case. Treat a `FAIL` report from this tool as
inconclusive, not authoritative — verify with `type` or a targeted field
read before concluding a click didn't register. Not yet fixed in the
script itself.

**What it cannot do yet**: click anything that doesn't render as scannable
character-buffer text — the actual map viewport (world overview, embark
site-selection map) renders via a texture-blit path invisible to
`dfhack.screen.readTile` (confirmed 2026-09-09, the same finding that
required real screenshots rather than buffer stats to verify Steam graphics
were rendering). Clicking a map location today still means guessing a pixel
position from a screenshot and converting to grid coordinates by hand — see
the queued task in `Working.md` for the specific case (the final embark
placement click) this blocks.

## Resolved 2026-09-10: the "off-center clicks fail" theory was wrong

The prior session's click-on-"Embark" failures were a **duplicate-text
false match**, not a screen-center/off-center physics problem. A naive
top-to-bottom buffer scan for the literal string `"Embark"` on
`viewscreen_choose_start_sitest` matches the instructional sentence at row
52 (`Click "Embark" to place your fortress.`) before it ever reaches the
real button at row 57 — so a generic `click("Embark")` was very likely
clicking that sentence, not the button, every time. Once aimed at the
button's exact buffer-scanned coordinates (confirmed via an explicit
column search on row 57 specifically, not a whole-screen text scan), the
click registered correctly on the first try, confirmed live twice. The
button sits at roughly 71% across, 95% down a 160×60 grid — about as
off-center as this screen gets — directly disproving the center-proximity
theory.

`df.global.gps.precise_mouse_x/y` (a second mouse-position field distinct
from `gps.mouse_x/y`, found stuck at `(640, 360)`) is also now resolved,
via DFHack's own `df-structures` source (`df.g_src.graphics.xml`):
`mouse_x/y` is documented `'tile offset'` (the character grid);
`precise_mouse_x/y` is documented `'pixel offset'`, and `enabler` exposes a
`get_precise_mouse_coords` **vmethod** — meaning it's polled live from the
real OS/platform mouse backend every frame, not a durable struct field. In
headless Xvfb there's no real mouse device moving, so it just keeps
reporting the window's pixel center; any Lua write to it is clobbered by
the next poll before a click can use it. `scr.widgets` (the newer
button-framework sub-object, the other queued lead) is also a dead end on
this screen specifically: empty, no children — this viewscreen predates
that framework.

## The real mechanism: Embark has two more clicks after it, not zero

Reading `gui/embark-anywhere.lua` (the source of the `force_embark()`
struct-write idiom already in use) revealed the actual flow has two
*additional* clicks after committing `warn_mm_*`/`warn_flags.GENERIC`, not
one:

1. Click **"Embark"** (row 57 button) → `scr.choosing_embark` flips to
   `true`, and — important — `warn_mm_*` gets reset to `-1,-1,-1,-1` by the
   native game at this transition, discarding the earlier commit.
2. Click **anywhere on the local map** (any reasonable pixel inside the
   viewport, away from the button bar) → the native click handler runs;
   immediately re-set `warn_mm_*` to the desired rectangle and
   `warn_flags.GENERIC = true` again in the same call, mirroring exactly
   what `force_embark()` does inside `embark-anywhere.lua`'s own `onInput`
   in response to a real map click.
3. A **"Confirm / Abort" bar appears** (not previously documented) — click
   **"Confirm"**.

Confirmed live twice, including a full fresh re-drive (title →
`"Start new game in existing world"` → Fortress mode → the two intro
dialogs, `"Skip tutorial"` then `"Okay"` — both must be dismissed first on
a fresh embark attempt, or the Embark-button click lands on the dialog
instead and `choosing_embark` never flips → re-committing the known-good
Site Finder rectangle directly, since the world/seed is unchanged, rather
than re-running Site Finder's own search).

## Resolved 2026-09-10 (second pass): the "Confirm" crash was a timing/race condition

Both hypotheses above (rectangle mismatch, arbitrary-pixel-vs-committed
mismatch) were disproven by direct test: copying the *real*,
engine-computed `neighbor_hover_mm_*` into `warn_mm_*` — the literal
`gui/embark-anywhere.lua` idiom, eliminating any mismatch — still crashed
identically on a throwaway test site. `systemctl status` consistently
showed `code=exited, status=1`, not `code=killed, status=SIGSEGV` —
confirmed via the `./dfhack` wrapper script's own source that this really
is `dwarfort` calling `exit(1)` itself (the wrapper's `ret=$?` captures
`dwarfort`'s exit code immediately after it exits, and passes it through
unchanged after an unrelated `tput sgr0` cosmetic call that fails
harmlessly on every shutdown, clean or crashed, regardless of `$TERM`) —
meaning a traditional core dump would never fire for this.

**The fix that actually worked**: running `dwarfort` directly under `gdb`
(installed fresh via `apt-get install gdb`, not present by default),
matching the exact environment `/proc/<pid>/environ` showed systemd using,
with a `catch syscall exit_group` batch script. The identical crash
sequence did **not** crash under gdb — it reached
`viewscreen_setupdwarfgamest` ("Play now!" / "Prepare for the journey
carefully") for the first time, then a real founded fort
(`viewscreen_dwarfmodest`). The catchpoint never actually fired (the
process never called `exit_group` this time), so the exact race is still
unidentified — gdb's `ptrace` overhead evidently changes timing enough to
avoid whatever it is, not fixes it. **Practical implication**: if a future
embark attempt hits this same crash again, running it under gdb (or
otherwise slowing the process — even an extra `sleep` between the map
click and the Confirm click might work, untested) is the known workaround,
not a real fix. Root-causing the actual race (verbose DFHack logging, or a
breakpoint on the real crash path rather than gdb's overhead merely
avoiding it) is worth doing if it recurs, but wasn't necessary to get the
first fort founded. Full evidence trail, including the two ruled-out
hypotheses that preceded this, in `decisions/DECISIONS.md` 2026-09-10 (the
row titled "First fort founded").

**A genuine fort now exists**: "Artobcatten, Combinedchannel" on
`region2`, confirmed via the in-game founding message, `gametype == 0`
(`DWARF_MAIN`), and a real save directory (`save/autosave 1`, containing
`world.sav`). **Superseded 2026-09-10 (fifth pass): this fort's save was
overwritten founding a second fort and no longer exists** — see
`decisions/DECISIONS.md` 2026-09-10 ("second fort was founded, but the
first fort's save was lost") and the new save-slot-naming trap in
`Working.md`. After quicksaving, the ad-hoc gdb-wrapped process was
stopped cleanly and the fort was reloaded under normal `df-fortress.service`
systemd supervision via the title screen's new "Continue active game"
button (present for the first time once a save exists) — verified
identical via screenshot. This reload is a routine, well-trodden DF code
path, distinct from the embark-finalization race above, so it was judged
safe to do despite the race being unresolved.

## Resolved 2026-09-10 (second pass): the map itself was unsteerable, and why

The first fort above landed on a bad site (mostly ocean/aquifer) because
`warn_mm_*` was force-written from `find_mm_*` directly — plausible at the
time, wrong in hindsight (see the corrected field table above). Fixing
this properly required first fixing something more fundamental: **the map
viewport, hover-info panel, and WASD panning cannot be driven by
DFHack's fake input at all**, only by real input. Two confirmed, distinct
mouse-state fields are load-bearing here, not one:

- `gps.mouse_x/y` — coarse character-grid position (160×60 cells). This
  is what `gui.simulateInput` sets, and it's genuinely sufficient for text
  buttons and dialogs (everything the "reusable tool" section above
  covers).
- `gps.precise_mouse_x/y` — real pixel-level position (1280×720), which
  the map viewport, hover-info side panel, and camera panning actually
  read. Confirmed via DFHack's own source (`enabler.get_precise_mouse_coords`
  vmethod) to be **polled live from the real OS mouse every frame** — in
  headless Xvfb, with no real mouse, this sits permanently frozen
  regardless of any Lua write. This is why the map never responded, the
  hover-info panel always showed the same stale reading, and WASD panning
  (even via the correct `CUSTOM_W/A/S/D` interface keys, not just generic
  `STANDARDSCROLL_*`) never moved the camera.

**The fix**: install `xdotool` (`apt-get install -y xdotool`, not present
by default) and send REAL X11 input directly to the Xvfb display —
`DISPLAY=:99 xdotool mousemove X Y`, and `keydown`/`sleep`/`keyup` for
held keys. This is indistinguishable from genuine hardware input to
DF/SDL, and confirmed live to: update `precise_mouse_x/y` correctly, make
the hover-info panel show real, dynamically-changing terrain data, make
real map clicks produce correct `warn_mm_*`/`neighbor_hover_mm_*` values,
and make WASD camera panning actually move the view (confirmed via
before/after screenshots — DFHack's fake WASD is pixel-identical no-op,
`xdotool`'s is not).

**Calibration** (exact, live-verified, not approximate): the DF window
sits at `+0,+40` within the virtual display — confirmed via `xwininfo -root -tree`
on `DISPLAY=:99` (no window manager is running, so this offset is fixed,
not something a WM could move). `precise_mouse_x = real_X11_X` (no
offset); `precise_mouse_y = real_X11_Y - 40`. `xdotool getmouselocation --shell`
is a valid independent cross-check of `precise_mouse_x/y` — set
`DISPLAY=:99` explicitly, it is not inherited automatically over SSH.

**Click reliability**: a bare `xdotool mousemove X Y click 1` is flaky —
confirmed via this `xdotool` build's own docs that its `click` action has
no default inter-step delay. What worked reliably all session: explicit
`mousemove` → `sleep 0.3` → `mousedown 1` → `sleep 0.2` → `mouseup 1`.
Minimum viable hold time was not characterized.

**Panning speed**: WASD panning via `xdotool keydown`/`keyup` works, but
this project's test world is a tiny 17×17-embark-tile "pocket" world, and
panning is fast relative to it — a 0.5s hold overshot the entire visible
island into open ocean; ~0.05s taps gave small, controllable increments.
Not calibrated to an exact tiles-per-second figure, and this will differ
on a larger world.

**The blue hover-cursor square itself remains a hard limit, confirmed, not
a gap to keep digging at**: a subagent's GitHub code search across the
entire `DFHack/dfhack` C++ source found zero references anywhere to
`neighbor_hover_mm_*`, `warn_mm_*`, `find_mm_*`, or `warn_flags` (control
queries for other, known-present strings confirmed the search itself
wasn't failing silently). The one DFHack plugin that does hook this exact
screen's render (`plugins/embark-assistant/overlay.cpp`, via
`VTableInterpose`) draws its own, different overlay (a match-result grid)
and never touches these fields. The hover square is pure native,
closed-source DF engine rendering — not settable, not readable, not a
DFHack overlay. Don't spend more time trying to locate or drive it
directly.

**Practical consequence for site selection going forward**: since a real
`xdotool` click already produces correct, world-absolute `warn_mm_*`
directly, there is no need to reconstruct `find_mm_*`'s exact transform
or chase the visual "acceptable sites" overlay (green = Site Finder
match, red = existing/unsettleable site, no highlight = valid-but-not-a-Finder-pick,
confirmed against the DF Wiki's own "Site finder" page and live by the
user watching the feed) at all. The plan is a **text-only sweep**: move
the real cursor across candidate tiles, read the hover-info panel and the
placement-warning dialog (both plain character-buffer text, already
proven completely reliable, zero image dependency — the warning text
correctly named "salt water," "light aquifer," "another site," and
"Recommended size" every single time it was tested), and commit the first
candidate that matches desired criteria and comes back clean. Full
research trail: `research/2026-09-10-embark-screen-rendering-and-coordinates.md`.

## Built 2026-09-10 (fifth pass): the sweep, and a new mechanic it depends on

**New finding, not in the research doc above**: `neighbor_hover_mm_*` only
live-updates from real mouse movement while `scr.choosing_embark` is
`true`. During ordinary zoomed browsing (`choosing_embark` false) it sits
frozen regardless of real `xdotool` mouse moves or clicks, even though the
hover-info text panel on the right (biome, temperature, trees, soil,
minerals) updates live in *both* modes. The research doc's earlier live
confirmation of `neighbor_hover_mm_*` tracking the real cursor came from
an actual embark-placement click, which is inside `choosing_embark` mode
— this wasn't previously generalized to casual hovering, and it doesn't
hold there. **Practical consequence: a sweep must enter `choosing_embark`
mode first and stay in it throughout**, using the text panel plus
`neighbor_hover_mm_*` together for every sample.

Two more things confirmed live while building this: **`LEAVESCREEN`
cleanly cancels `choosing_embark`** (back to ordinary browsing, `warn_mm_*`
still `-1,-1,-1,-1`, no side effect) as long as the local map itself is
never clicked — a safe way to test/abort without committing anything. And
**WASD camera panning keeps working while `choosing_embark` is `true`** —
no need to leave the mode to pan the camera between sweep samples.

`hover` reads `neighbor_hover_mm_sx/sy/ex/ey` plus a few buffer-scanned
criteria flags (`ocean`, `aquifer`, `no_soil`, raw `biome`/`trees` text) in
one call, printed as one grep-friendly `HOVER ...` line. **Panel layout
differs between browsing and `choosing_embark` mode**: row 4 gains a
leading "N x N" embark-size indicator ahead of the biome name once
`choosing_embark` is `true`, not present during plain browsing — `hover`'s
`ocean` check has to scan the whole row for "Ocean," not assume the biome
name is the row's only content, since the size prefix pushes it to a
variable column.

The actual sweep loop (enter `embark-mode` once, pan with `xdotool
keydown/keyup` toward a region worth checking, raster a grid of
`xdotool mousemove` + `hover` calls, `leave-embark-mode` when done) was
driven by hand over SSH this session, not yet wrapped into its own
script/subcommand — see `Working.md`'s handover for the concrete
candidate rectangle it found and the recommended shape for that script if
it's built out further.

### A Windows-specific SSH transport bug, found deploying this

`install_df.py ui-install` failed **silently** deploying the larger
updated script: exit 0, "deployed" logged, but the file on the guest was
untouched and the remote command's stdout was the literal, un-decoded
base64 payload instead of the expected `installed` echo. Root cause,
confirmed by reproduction: `remote()`'s `echo <payload> | base64 -d |
bash -s` pattern embeds the whole payload directly in the SSH
command-line argument, and Git's MSYS-linked `ssh.exe` silently truncates
that argument to **~8182 characters** when spawned by a native Win32
process (Python's `subprocess`, which must flatten argv into one
`CreateProcess` command-line string) — but not when spawned by a POSIX
process (bash, execing the real argv array directly, no re-serialization).
This was a latent bug the whole time; every earlier `remote()` payload
happened to stay under ~8KB. **Fixed**: `provision_vm.ssh_guest` gained an
`input_data` parameter that pipes the payload over the child's stdin
instead, and `install_df.remote()` now uses it — never embed a
payload of unbounded size directly in an SSH command string again.
`provision_relay.py` gets the fix for free, since it reuses the same
`remote()`. See `provision_vm.ssh_guest`'s docstring for the full
mechanism.

## Founded a second fort with the sweep — three more findings, one costly

Used the sweep above to actually commit a second embark. Three things
worth recording that weren't true of the first fort's flow:

**The tutorial intro dialogs render as overlays on
`viewscreen_choose_start_sitest` itself, not as a separate viewscreen
type**, and do reappear on every fresh embark attempt (a `type` check
right after reaching the embark screen can miss them if the dump isn't
also checked — they don't change `_type`).

**A real `xdotool` click on a genuinely valid, placeable tile went
straight through the entire remaining flow to
`viewscreen_setupdwarfgamest`** — no `warn_mm_*` force-write, no separate
map-click-then-Confirm sequence needed at all, unlike the three-click
mechanism documented above for the first fort. Not fully explained; the
force-write/Confirm dance documented above may have been compensating for
something specific to DFHack's fake input rather than being an inherent
property of the flow. The first commit attempt this session *did* still
hit the documented crash signature (`code=exited, status=1`, same `gdb`
workaround), but at the map-click step rather than Confirm — so the race
isn't scoped to one specific click either.

**The costly one**: restarting the embark flow from the title screen does
not reliably return to the same world as wherever a stale, uncommitted
embark attempt was sitting — this session's fresh "Start new game in
existing world" landed in `region1`, not the `region2` a stale
mid-navigation state (and its `neighbor_hover_mm_*` numbers) belonged to.
Reusing those stale numbers pointed at real mountain terrain in the new
world (DF's own "cannot embark entirely on water or mountains" validation
caught it, no harm done) — but more importantly, **DF's save-slot names
(`autosave 1`, `autosave 2`, `current`) turned out to be a shared generic
pool, not scoped per fort**: founding this second fort overwrote the
first fort's actual save (which lived in `autosave 1`, not a
region-named folder), confirmed via `md5sum` — `autosave 1/world.sav` and
`autosave 2/world.sav` are now byte-identical, both holding the new
fort's data, with no backup ever taken and no recovery found. **Pull an
`install_df.py backup` of every existing save before founding any future
additional fort.** Full incident: `decisions/DECISIONS.md` 2026-09-10.

## Screen atlas

Each entry: DFHack viewscreen type (`dfhack.gui.getDFViewscreen(true)._type`),
what it's for, confirmed navigation, and anything screen-specific worth
knowing. "Confirmed" means actually driven live this session, not inferred
from research.

### `viewscreen_titlest` — title / main menu

The very first screen, and also what a bare `df-fortress.service` restart
returns to. Real character-buffer text, `click` works reliably here.

- Buttons confirmed clickable by text: `"Start new game in existing world"`,
  `"Create new world"`, `"Object testing arena"`, `"Settings"`, `"About DF"`,
  `"Quit"`.
- The `"Histories of X and Y"` line above the buttons is a per-session
  random flavor phrase, unrelated to any specific save — don't read
  anything into it changing between restarts.
- Confirmed dead: `CUSTOM_S` (a literal 's' keypress), all four
  `CURSOR_UP/DOWN/LEFT/RIGHT` directions, generic `SELECT`/`MENU_CONFIRM`/
  `STANDARDSCROLL_DOWN`. No keyboard path exists into this screen's main
  menu at all — confirmed both by exhaustive live keypress testing and by
  the complete absence of any bracketed/colored hotkey letter in the
  character buffer (`pen.fg` dumps, not just a visual glance).

### (loading) `viewscreen_adopt_regionst`

Appears twice in the flow: once after picking a world from the list (world
history load), once after picking a game mode (region-to-fortress-start
load, shown on screen as "Loading world to start new game... Loading object
files..." with a progress bar). Not embark-specific by itself — the same
screen type also appears for adventure mode and legends mode; check
`df.global.gametype == df.game_type.DWARF_MAIN` if that distinction ever
matters. No interaction needed, just wait (a few seconds) and re-check
`type` until it moves on.

### `viewscreen_choose_game_typest` — Fortress/Adventurer/Legends picker

Not named in `research/2026-09-08-embark-automation.md`'s predicted
sequence — a real screen the research missed, confirmed live 2026-09-10.
Appears after picking a world, before the region-to-fortress load.

- Text: `"Select a game type to begin!"`, buttons `"Fortress"`,
  `"Adventurer"`, `"Legends"`, `"Back to title menu"`.
- `click("Fortress")` confirmed working (with retries).

### (loading) `viewscreen_update_regionst`

Brief world-history-catchup loading screen between picking Fortress mode
and reaching the embark map. No interaction needed, wait and re-check
`type`.

### `viewscreen_choose_start_sitest` — world overview / Site Finder / embark map

The big one — several distinct sub-states share this one viewscreen type,
distinguished by struct fields, not `_type`:

| Field | Meaning |
|---|---|
| `zoomed_in` | `false` = wide regional map ("Click the map to embark location... press wasd to recenter"); `true` = local 4x4-tile close-up map |
| `doing_site_finder` | Site Finder criteria panel is open |
| `find_results` | scalar status (confirmed 2 = "Match found!"; a `T_find_results` enum, not a count) |
| `find_mm_sx/sy/ex/ey` | the ONE current best-fit Site Finder match (`mm` = min/max, confirmed via DFHack's own `df-structures` naming convention — `research/2026-09-10-site-finder-internals.md`) — **confirmed 2026-09-10 (second pass) to be a DIFFERENT, smaller-magnitude, non-absolute coordinate frame from `warn_mm_*`/`neighbor_hover_mm_*` below. Never write it directly into `warn_mm_*`** — doing so all night produced nonsense-scale coordinates near the map's origin corner, not the intended site (the actual cause of that session's "same forced numbers, wildly different real locations" bug, not a camera/rendering issue as first suspected). `location.region_pos.x*16 + find_mm_sx` matched the correct absolute X exactly in one live test (consistent with the DF Wiki's "one region tile = 16×16 embark tiles"), but the same formula on Y was off by a consistent, unexplained 9 from a non-time-aligned sample — see `research/2026-09-10-embark-screen-rendering-and-coordinates.md` for the full trail and the one cheap atomic-read test that would settle it. |
| `find_cur_best_value` | that match's internal score |
| `neighbor_hover_mm_sx/sy/ex/ey` | the currently-hovered rectangle (DF's native ~2×2 blue hover-square, confirmed pure closed-source engine rendering — not a DFHack overlay, see 2026-09-10 second-pass section below) — **confirmed a render-derived output, not a settable input**: writing it directly does not move anything on screen. **Confirmed 2026-09-10 (second pass) to be WORLD-ABSOLUTE embark-tile coordinates** — live-matched exactly against `location.embark_pos_min/max` (real decompiled field names `abs_mm_start`/`abs_mm_end`). Only ever updates from a genuine mouse-over-map event; DFHack's fake `gui.simulateInput` never triggers it (see the `precise_mouse_x/y`/`xdotool` section below) — a real `xdotool` click does. |
| `warn_mm_startx/endx/starty/endy` | the rectangle being committed as the embark choice; `-1,-1,-1,-1` means nothing committed yet. **Same world-absolute frame as `neighbor_hover_mm_*`** (confirmed together, same live read) — safe to copy from `neighbor_hover_mm_*` (the `gui/embark-anywhere.lua` idiom), never safe to copy from `find_mm_*` directly. |
| `warn_flags.GENERIC` | setting `true` (alongside `warn_mm_*`) is `gui/embark-anywhere.lua`'s `force_embark()` idiom — gets consumed/reset by each of the two further clicks below, so must be re-set after each one, not just once |
| `find_param[2]` | Savagery criterion; `0` = Calm (the value used this session) — set directly, not via a `+`/`-` button click, which is more robust per 2026-09-09's finding |
| `choosing_embark` | `true` once the "Embark" button (row 57) has been clicked — the screen is now waiting for a click on the local map itself. Resets `warn_mm_*` to `-1,-1,-1,-1` at this transition |
| (no struct field found yet) | the **"Confirm / Abort"** bar that appears after the map click + re-committed `warn_mm_*`/`warn_flags.GENERIC` — detected via buffer text only so far, not yet traced to a struct flag |

Sequence confirmed live, in order: land on this screen zoomed out
(`zoomed_in = false`) → click `"Find embark location"` to open the Site
Finder criteria panel → set the desired `find_param[...]` fields directly →
click `"Begin"` → `"Match found!"` appears with `find_mm_*` populated →
**do NOT commit `warn_mm_* = find_mm_*` directly — see the corrected field
table above and the 2026-09-10 (second pass) section below; this produced
a real but badly-placed fort.** The screen needs `zoomed_in = true` for
the local map/Embark-button sub-mode to actually show (writing this flag
directly did work, unlike `neighbor_hover_mm_*`) → click
**"Embark"** at its exact buffer-scanned position, row 57 (a whole-screen
text scan for `"Embark"` will false-match the help sentence at row 52
first — scope the scan to row 57) → `choosing_embark` flips `true`,
`warn_mm_*` resets to `-1,-1,-1,-1` → click anywhere on the local map
viewport, then in the same call re-set `warn_mm_*` to the desired
rectangle and `warn_flags.GENERIC = true` again → a **"Confirm / Abort"**
bar appears → click **"Confirm"** at its buffer-scanned position → a
**"Play now!" / "Prepare for the journey carefully"** screen
(`viewscreen_setupdwarfgamest`) → click **"Play now!"** for default
supplies → **fortress mode** (`viewscreen_dwarfmodest`), a real founded
fort. This last click was flaky (a timing/race condition, resolved below,
not a permanent blocker) on its first several attempts.

Two dialogs appear on a fresh embark attempt, both dismissed the normal way:
`"Quick start and short tutorial?"` (`"Skip tutorial"` button) and
`"On your own!"` (`"Okay"` button).

**DF's own "Re-run finder" confirmation** (triggered by clicking `"Begin"`
again once a match already exists) only offers `"P: Pause this
confirmation"` or `"Enter: Yes, proceed"` — no plain cancel.
`gui.simulateInput(scr, "CUSTOM_P")` dismisses it without discarding the
existing match (confirmed: `find_mm_*` unchanged afterward). Never press
Enter here unless discarding the current match and re-searching is actually
wanted.

Also confirmed dead on this screen specifically (beyond the title screen's
already-dead set): WASD camera panning, all four `CURSOR_*` directions for
cursor movement. The map viewport itself renders via a texture-blit path
invisible to `dfhack.screen.readTile` — same as the "map viewport" caveat
already recorded for verifying Steam graphics — so no amount of buffer
scanning will ever find the green "acceptable site" highlighting or read
the map's actual pixels; only the plain-text side panel (criteria list,
`"Match found!"`, button labels) is buffer-scannable.

### `viewscreen_setupdwarfgamest` — starting supplies

Appears once, right after a successful "Confirm" on the embark screen.
Buttons: `"Play now!"` (default skills/equipment/animals) and
`"Prepare for the journey carefully"` (custom loadout, not yet exercised).
`click("Play now!")` confirmed working. Leads directly into
`viewscreen_dwarfmodest`.

### `viewscreen_dwarfmodest` — fortress mode

Real gameplay. Confirmed reachable 2026-09-10 as the endpoint of the full
embark chain above. Not otherwise explored yet — the perception/action
layer `docs/PURPOSE.md`'s build order describes for actually playing a
founded fort is a separate, still-unbuilt system.

### Title screen gains a "Continue active game" button once a save exists

Not present on a fresh boot with no save; appears as the first button,
above `"Start new game in existing world"`, once one does. Loads straight
into `viewscreen_loadgamest` (a brief loading screen, same wait-and-recheck
pattern as the other loading screens), then `viewscreen_dwarfmodest`.

## Sources

`decisions/DECISIONS.md` 2026-09-09 and 2026-09-10 rows carry the full
evidence trail (exact test sequences, screenshots referenced, what was
tried and ruled out) behind every claim above, including the "First fort
founded" row and the `find_mm_*`/coordinate-frame row. `Working.md`'s
handover has the current state and next steps. `research/2026-09-08-embark-automation.md`,
`research/2026-09-10-site-finder-internals.md`, and
`research/2026-09-10-embark-screen-rendering-and-coordinates.md` are the
primary-source research this was built on. This file is the living
summary; when a claim
here and a decisions-register row disagree, the decisions register is the
more detailed, dated source of truth — fix this file to match it, not the
other way around.
