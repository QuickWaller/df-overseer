# Embark Screen (`viewscreen_choose_start_sitest`): Zoom Rendering, Coordinate Frames, Overlay Gating, xdotool Reliability

Date: 2026-09-10
Scope: five follow-up questions from tonight's live embark/site-selection trial-and-error session on `df-colony-01` (VM 103, DF 0.53.16, DFHack 53.16-r1.1): what gates the local-view zoom render, whether `find_mm_*` is region-tile-local, what gates the "acceptable sites" green overlay, a reliable `xdotool` recipe, and why screenshot viewport bounds seemed to shift.
Status: **read-only.** No key or click was simulated, no field was written, no screen was advanced. All live checks were `dfhack-run lua` reads against the **already-open** `viewscreen_choose_start_sitest` (confirmed present before touching anything) — `pairs()`-style field reads only, same safe pattern used in `research/2026-09-08-embark-automation.md` and `research/2026-09-10-site-finder-internals.md`. Sources: a fresh shallow clone of `DFHack/df-structures` (`master`) read locally, plus live reads against the running game over SSH.

---

## 1. The answer, up front

1. **Zoom render gate**: `viewscreen_choose_start_sitest` has two timer fields sitting right next to `zoomed_in` in the struct — `setting_up_map_timer` and `animating_quick_start_timer` — that are not documented anywhere (no script references them) but are named exactly like a "local view isn't ready yet" gate. The live screen, currently sitting in a properly-rendered zoomed state, has both timers at a settled `0` and held there across four 300ms polls. This is **consistent with, but does not prove**, "flipping `zoomed_in` via a raw struct write doesn't trigger whatever code path kicks off `setting_up_map_timer`, so the renderer doesn't redraw until a real click drives the same input handler the game's own UI uses" — which matches tonight's pattern exactly (silent no-op on most raw toggles, one real render right after a genuine mousedown/hold/mouseup). **[I], well-grounded, not provable from a single live snapshot** — see §2 for the exact recommended A/B test that would confirm it without more guessing.
2. **`find_mm_*` vs `neighbor_hover_mm_*`/`warn_mm_*`**: this is now **directly confirmed, not inferred**. A live read this session found `neighbor_hover_mm_{sx,sy,ex,ey}` = `(150, 79, 153, 82)` and, in the same breath, the *committed* `location.embark_pos_min`/`embark_pos_max` struct (named `abs_mm_start`/`abs_mm_end` in the original game source) = `(150, 79)` / `(153, 82)` — **an exact match**. `neighbor_hover_mm_*`/`warn_mm_*` are confirmed world-absolute embark-tile coordinates. `find_mm_*`, read at the same moment, was `(6, 8, 9, 11)` — the exact small-number pattern the user described fighting with tonight — strongly suggesting **tonight's "same numbers, different locations" bug was `find_mm_*` (Site-Finder-local) being used/read where `neighbor_hover_mm_*`/`warn_mm_*` (absolute) was needed.** The precise transform between them could not be nailed down this session (see §3) because `doing_site_finder` is currently `false` and `find_block_x/y` sit at stale-looking values (`-1`, `0`), meaning the live `find_mm_*` snapshot is very likely leftover from an earlier, unrelated search and not time-aligned with the current hover position — comparing the two was not a valid test. **[C]** for the absolute-frame identity; **[I, explicitly unresolved]** for the find_mm transform.
3. **Overlay gating**: live right now, `doing_site_finder == false` while `find_results == 2` (`Suitable`) — i.e. **directly observed, not inferred**: the Site Finder's result data persists after `doing_site_finder` goes false. This is exactly the pattern tonight's session described ("green highlight disappeared... even though find_results/find_mm stayed intact") and is the strongest evidence available that **`doing_site_finder` (not `find_results`) is what gates the overlay paint**. The "we just panned away" alternative could not be ruled out from a static read (see §4) but is a *weaker* explanation given this is a real, live, current mismatch between a "done" value and a "not drawing" flag.
4. A concrete `xdotool` recipe and an exact, live-verified cross-check of `precise_mouse_x/y` against real X11 pointer state are given in §5, including a measured, explained offset (not just restated).
5. Viewport-shift: no direct evidence of window resize was found (character grid `gps.dimx/dimy` = `160x60`, matching the already-known 1280x720 geometry, stable), but the struct has a `page` field (`choose_start_site_view_mode`, 9 values: Biome/Neighbors/Civilization/Elevation/Cliffs/Reclaim/ReclaimDetails/Find/Notes) that plausibly drives a variable-width side panel. **This was not tested against a screenshot width this session** — flagged as the most likely explanation but genuinely unverified; see §6.

---

## 2. What gates the zoom render

### 2.1 New fields found, not previously in this repo's memory

`df.d_interface.xml` (cloned `df-structures` master, `viewscreen_choose_start_sitest`, lines 6657–6764):

```xml
<int32_t name='animating_quick_start_timer'/>
<int32_t name='setting_up_map_timer'/>

<int32_t name='region_cent_x'/>
<int32_t name='region_cent_y'/>
<bool name='mouse_scrolling_map'/>
<int32_t name='mouse_anchor_mx'/>
<int32_t name='mouse_anchor_my'/>
<int32_t name='mouse_anchor_pmx'/>
<int32_t name='mouse_anchor_pmy'/>
...
<bool name='zoomed_in'/>
<int32_t name='zoom_cent_x'/>
<int32_t name='zoom_cent_y'/>
```

Neither timer, nor `region_cent_*`/`zoom_cent_*`/`mouse_anchor_*`, is referenced by any installed DFHack Lua script (`grep -rl` across `/opt/df/game/hack/` on the VM found zero source hits — only the compiled `libdfhack.so`, which is expected since these are read via struct reflection, not named Lua symbols). **[C-XML]** for the fields existing; no comment explains their semantics, so the interpretation below is **[I]**.

### 2.2 Live read (current state, screen already zoomed in and genuinely rendering)

```
$ dfhack-run lua "local scr=dfhack.gui.getCurViewscreen(); print(scr.zoomed_in, scr.setting_up_map_timer, scr.animating_quick_start_timer, scr.region_cent_x, scr.region_cent_y, scr.zoom_cent_x, scr.zoom_cent_y, scr.page)"
zoomed_in              true
setting_up_map_timer   0
animating_quick_start_timer  0
region_cent_x          0
region_cent_y          0
zoom_cent_x            251
zoom_cent_y            216
page                   0   (= Biome)
```

Polled four more times at 300ms intervals: both timers held stable at `0`, `zoomed_in` held `true`. **[C]**, directly observed.

### 2.3 Reading

- `region_cent_x/y` and `zoom_cent_x/y` are two **separate** camera-center fields — one for the wide region view, one for the zoomed local view. This answers part of the original viewport question directly: the screen does *not* reuse one center field for both zoom levels, so a script that pans in wide view and then flips `zoomed_in` should not expect the zoomed view to be centered on the same point unless it also writes `zoom_cent_x/y` itself. **[C-XML]**, not live-tested against a pan this session (read-only constraint).
- `setting_up_map_timer` sitting at a settled `0` right now, on a screen that is genuinely showing the detailed local render, is **consistent with** "this timer runs down to 0 when the local terrain is ready to paint, and the renderer doesn't draw the real close-up until it hits 0" — but a single static snapshot of a screen that's already settled cannot distinguish that from "this field is irrelevant and happens to be 0 by coincidence." **A live A/B test would settle this cleanly and is the single highest-value follow-up for question 1**: from the title/wide view, (a) write `zoomed_in = true` via a raw Lua field write with no real click, read `setting_up_map_timer` immediately after and once more ~1s later, and diff screenshots; then (b) repeat but trigger zoom via a real `xdotool` click on the zoom control, and do the same reads/diff. If (a) leaves `setting_up_map_timer` at 0 the whole time and never re-renders, while (b) shows it move off 0 and then settle, that is a clean confirmed answer. This was **not run** tonight's task scope excludes touching the live screen.
- This also reframes the "toggling `zoomed_in` sometimes does nothing" mystery in a more falsifiable way than "DF needs to generate local terrain" (the task's original hypothesis): the fields suggest a **UI-state timer gate tied to genuine input handling**, not necessarily an expensive async terrain-generation step — the "local view" on this screen is a render of already-existing world-gen biome/elevation data (confirmed separately: `show_cliffs`, `show_elevation`, `biome_idx` sit alongside `zoomed_in` as sibling display-mode toggles, not generation flags), not a full local-map simulation (that only exists after actual embark, a separate, later screen). **[I]**, but a more specific and more testable hypothesis than the task's original framing.

---

## 3. Coordinate frames: `neighbor_hover_mm_*`/`warn_mm_*` are absolute; `find_mm_*` is not, but its transform is unresolved

### 3.1 Direct confirmation (new, not in `research/2026-09-10-site-finder-internals.md`, which called this `[I]`)

`df.plotinfo.xml:506`, the struct committed once a site is actually chosen:

```xml
<struct-type type-name='embark_location' original-name='starter_infost'>
    <compound type-name='coord2d' name='region_pos' original-name='start'/>
    <int16_t name="reclaim_site" original-name='start_id' ref-target='world_site'/>
    <int16_t name="reclaim_idx" original-name='start_index'/>
    <compound type-name='coord2d' name='embark_pos_min' original-name='abs_mm_start'/>
    <compound type-name='coord2d' name='embark_pos_max' original-name='abs_mm_end'/>
</struct-type>
```

The original (decompiled) field names are **`abs_mm_start`/`abs_mm_end`** — "abs" spelled out, not inferred from type size this time. Live read, same moment as §2.2's screen state:

```
neighbor_hover_mm   sx=150 sy=79 ex=153 ey=82
location.region_pos          x=9   y=5
location.embark_pos_min      x=150 y=79
location.embark_pos_max      x=153 y=82
```

`embark_pos_min/max` (the struct's own `abs_mm_start`/`abs_mm_end`) is **exactly equal**, field for field, to `neighbor_hover_mm_{sx,sy,ex,ey}`. This is a live, direct, reproducible observation, not a type-size analogy: **`neighbor_hover_mm_*` is the world-absolute embark-tile rectangle**, full stop. Since `gui/embark-anywhere.lua`'s `force_embark()` (quoted in full in `research/2026-09-08-embark-automation.md` §4.3) copies `neighbor_hover_mm_*` straight into `warn_mm_*` with zero transform, `warn_mm_*` is the same absolute frame. **[C]**, upgraded from the prior research pass's `[I]`.

### 3.2 `find_mm_*`: confirmed different magnitude, transform not resolved this session

Same live read:

```
find_mm           sx=6  sy=8  ex=9  ey=11
find_ax, find_ay        = 0, 11
find_block_x, find_block_y   = -1, 0
find_block_dx, find_block_dy = 0, 0
find_cur_best_value     = 10066
find_results             = 2      (Suitable)
doing_site_finder        = false
```

`(6, 8, 9, 11)` is the exact pattern of small numbers described in tonight's task background as having been forced and producing wildly different real locations across attempts. That is a strong circumstantial match for "this is the field that was actually being read/written, under the mistaken belief it behaved like `warn_mm_*`."

**What this session could and could not establish:**
- Tried the obvious hypothesis (`find_mm_* ` is local to `location.region_pos * 16`, per the Wiki's "16×16 grid of local view tiles per region tile"): `region_pos.x * 16 + find_mm_sx = 9*16 + 6 = 150`, which matches `neighbor_hover_mm_sx` exactly, and `region_pos.x*16 + find_mm_ex = 144+9=153` also matches `neighbor_hover_mm_ex` exactly. **The X axis lines up perfectly.**
- The same formula on Y does **not** line up: `region_pos.y*16 + find_mm_sy = 5*16+8 = 88`, vs. actual `neighbor_hover_mm_sy = 79` — a 9-tile mismatch, and `5*16+11=91` vs. `neighbor_hover_mm_ey=82`, also off by 9 (consistently off by 9 on both Y bounds, interestingly, not a random mismatch — but not zero either).
- **Conclusion: not resolved, and I am not going to force a clean story past what the data supports.** `doing_site_finder` is currently `false`, and `find_block_x = -1` looks exactly like an uninitialized/reset sentinel (matching the XML's own `init-value='-1'` on the sibling `find_block_dx` field) — both signs that `find_mm_*`/`find_block_*` are **stale, leftover from a previous, separate Site Finder run**, not data describing the currently-hovered tile. Comparing a stale `find_mm_*` snapshot against a *current* `neighbor_hover_mm_*`/`region_pos` reading is not a valid test of the transform, which is almost certainly why X coincidentally lined up (possibly true relationship, possibly luck with small numbers) while Y did not. **The consistent off-by-9 on Y is itself a clue** (if this were pure coincidence/staleness with no relationship at all, there'd be no reason for both Y bounds to be off by exactly the same amount) but I am explicitly flagging I cannot responsibly turn "off by 9 on both bounds" into a confirmed rule without a time-aligned sample.
- **Recommended live test** (the single most valuable follow-up from this whole report): run the Site Finder fresh ("Begin"), **immediately** read `find_mm_*`, `find_block_x/y`, `find_ax/ay`, and `location.region_pos`/`neighbor_hover_mm_*` for the tile it lands on, all in the *same* `dfhack-run lua` call (one atomic read, no time gap). Compute the offset directly from that one time-aligned sample. This is a read-only, zero-risk test — no click or write needed, since `find_mm_*` already updates from the stock "Find embark location" UI flow.

### 3.3 `embark_dx`/`embark_dy`: confirmed, simple

```xml
<int32_t name='embark_dx'/>
<int32_t name='embark_dy'/>
```
Live: `4, 4`. `neighbor_hover_mm_ex - neighbor_hover_mm_sx = 153-150 = 3`, `+1 = 4`, matching `embark_dx` exactly (bounds are inclusive min/max, size = max-min+1). **[C]**, trivial but worth having confirmed exactly rather than assumed.

---

## 4. The green "acceptable sites" overlay: directly-observed gating evidence

Live read, same session:

```
doing_site_finder   false
find_results        2      (Suitable)
find_cur_best_value 10066
biome_highlighted   true
find_select         0
warn_flags.GENERIC  false
```

This is a **direct, live observation** of exactly the pattern the task asked about: `find_results` still reports `Suitable` (a completed, successful search) while `doing_site_finder` is `false`. Per `research/2026-09-10-site-finder-internals.md` §5 (struct-shape argument, confirmed there too), there is **no stored vector of "currently highlighted squares" anywhere in the struct** — `find_cur_best_value`, `find_mm_*`, and `find_results` are all scalars. That means the green highlight overlay cannot be a persisted list the renderer is reading from memory; **it has to be computed live, per visible tile, at render time**, gated by some condition. Given `find_results`/`find_mm_*` evidently persist after the overlay (per tonight's observation) stops appearing, and `doing_site_finder` is the one obviously-named "are we currently in finder mode" flag on the struct, **`doing_site_finder` is the best-supported candidate gate** — directly consistent with tonight's behavioral observation (overlay reliably appeared right after "Begin," which plausibly sets `doing_site_finder = true`; disappeared after further interaction, which plausibly sets it back to `false`).

**What was not, and could not be, ruled out from a static read**: the task's own alternative hypothesis — that the overlay was never gone, and the session had simply panned the camera away from the highlighted tiles between screenshots. Since the overlay (if gated by `doing_site_finder`) is drawn per-visible-tile at render time, a camera pan alone, with `doing_site_finder` genuinely unchanged, *could* also produce "no highlight visible in this screenshot." **Both explanations are consistent with everything observed so far**, and distinguishing them needs a live test: re-pan the camera back to a tile confirmed (via `find_mm_*` or a known prior match) to have been highlighted, and read `doing_site_finder` at that exact moment. If the tile is back in view and still unhighlighted while `doing_site_finder` reads `true`, the gate hypothesis is wrong; if it's unhighlighted and `doing_site_finder` reads `false`, the gate hypothesis holds. This was not run this session (would require driving the camera, out of scope for read-only research).

---

## 5. `xdotool` reliability and the `precise_mouse_x/y` cross-check

### 5.1 Installed version and defaults

```
$ xdotool --version
xdotool version 3.20160805.1
```

Man-page-documented defaults relevant to tonight's flakiness (read directly, not recalled from memory):
- `--delay` default for `key`/`type` is **12ms** between keystrokes — not directly the click path, but confirms this `xdotool` build's baseline timing assumption is in the low tens of milliseconds, not zero.
- The `click` command's own `--delay` (time between repeated clicks when `--repeat` > 1) is **not used at all when `--repeat` is left at its default of 1** — i.e., a single `xdotool mousemove X Y click 1` has **no built-in settle delay between the move and the click** unless you insert one yourself. This directly supports tonight's empirical finding that bare `mousemove ... click 1` was unreliable and the explicit `mousemove` → `sleep` → `mousedown` → `sleep` → `mouseup` sequence was not just superstition — there genuinely is no default inter-step delay to rely on in this tool version.

### 5.2 Live cross-check: `xdotool getmouselocation` vs. DFHack's `precise_mouse_x/y`

```
$ DISPLAY=:99 xdotool getmouselocation --shell
X=240
Y=200
SCREEN=0
WINDOW=2097160

$ dfhack-run lua "print(df.global.gps.precise_mouse_x, df.global.gps.precise_mouse_y, df.global.gps.mouse_x, df.global.gps.mouse_y)"
240  160  30  13
```

This is a clean, **live, exact** confirmation of the already-established window offset, worked through with real numbers instead of restated as a rule:
- X: real X11 `240` vs. DFHack `precise_mouse_x` `240` — **exact match, zero offset**, consistent with the window's `+0` X origin from `xwininfo`.
- Y: real X11 `200` vs. DFHack `precise_mouse_y` `160` — **differs by exactly 40**, consistent with the window's documented `+40` Y origin. `200 - 40 = 160`. Confirmed exact, not approximate.
- Character grid cross-check: `precise_mouse_x / 8 = 240/8 = 30 = gps.mouse_x` exactly; `precise_mouse_y / 12 = 160/12 = 13.33`, floors to `13 = gps.mouse_y` exactly. Both conversions hold precisely against the already-established 8px/12px grid.

**Answer to the task's Q4 ask**: yes, `xdotool getmouselocation --shell` is a valid, independent cross-check of `precise_mouse_x/y`, and the correct conversion formula, confirmed live this session, is:
```
precise_mouse_x = real_X11_X        (no offset)
precise_mouse_y = real_X11_Y - 40   (window Y-offset, matches xwininfo's +40)
```
Use `DISPLAY=:99` explicitly in any non-interactive shell (an SSH session without it returned `Error: Can't open display: (null)` — the display env var is not inherited automatically over SSH the way it might be in an interactive login shell with `DISPLAY` exported in `.bashrc`).

### 5.3 What was not established

- **Minimum reliable hold/settle timings** were not characterized this session (would require sending real clicks to the live embark screen, out of scope for read-only research). Tonight's empirical 0.3s move-settle + 0.2s mousedown hold worked; whether that can be shortened is untested. The only primary-source fact found is that `xdotool`'s own click path inserts **no** default delay — so any reliability tonight's longer holds bought is coming from DF's own input/render loop, not from xdotool. `prefs/init.txt` has `G_FPS_CAP:50` (confirmed, line 75 on this Linux install per `memory/dfhack-environment.md`), i.e. DF's render tick is nominally ~20ms; a hold shorter than roughly one render frame is the most plausible lower bound worth testing first, but this is **[I]**, not measured.

---

## 6. Viewport pixel-bounds instability: inconclusive, best lead identified

Checked:
```
gps.dimx = 160, gps.dimy = 60
```
— the character grid is stable and matches the already-known 1280x720 @ 8px/12px geometry, with no evidence of a window resize at the moment of this read. DF is launched `WINDOWED:YES` under Xvfb with **no window manager** (confirmed in `research/2026-09-08-vm-provisioning.md`'s predecessor material / this session's own environment notes) — there is no WM-driven resize mechanism present, which rules out the most common real-world cause of a window silently changing size between screenshots.

The one concrete, structurally-supported lead not yet tested: `page` (`choose_start_site_view_mode`, live value `0` = `Biome`) has **nine** distinct values — `Biome, Neighbors, Civilization, Elevation, Cliffs, Reclaim, ReclaimDetails, Find, Notes` — each plausibly driving a different-width side info panel (a "Neighbors" list, a "Find"/Site-Finder criteria list, and a "Notes" text-entry box are very unlikely to all need the same sidebar width). If the map's rendered area is simply "whatever's left after the current side panel," then two screenshots taken with different `page` values (e.g. one while hovering a neighbor civ, which plausibly flips `page` to `Neighbors`, versus one with no hover) would show genuinely different visible-map pixel widths **by design**, not from any nondeterminism. **This was not verified against actual pixel measurements this session** (would require comparing `scr.page` to a screenshot's measured map width at the moment of capture, which needs live interaction) — flagged as the best available lead, not a confirmed answer. The task's own instinct to ask "is it possible we just panned away" generalizes here too: re-examining tonight's own screenshots (if still available) for what `page`/hover-state was likely active at each capture, rather than assuming a new live test is required, is the cheapest next step.

---

## 7. What could not be verified, and why

- **§2's zoom-timer gating**: plausible and specific, but unproven — needs the exact A/B live test described in §2.3 (raw write vs. real click), explicitly not run here (read-only constraint, screen already mid-use by the live session).
- **§3.2's `find_mm_*` transform**: the X-axis match (`region_pos.x*16 + find_mm_sx`) may be real or coincidental; the Y-axis mismatch (consistently off by 9, not zero) is reported honestly rather than explained away. The data needed to resolve this (`find_mm_*` and `neighbor_hover_mm_*`/`region_pos` read in one atomic call immediately after a fresh Site Finder run) was not available this session because the live screen's Site Finder state looked stale/inactive at read time.
- **§4's overlay gate**: `doing_site_finder` is the best-supported candidate by elimination and by a real live mismatch against `find_results`, but the "camera panned away" alternative was not ruled out, and doing so needs camera control this task excluded.
- **§5.3's minimum click timing**: no primary source found (the installed `xdotool` inserts no default delay; DF's own C++ input handling is closed-source). The `G_FPS_CAP:50` render-tick figure is offered as the most plausible order-of-magnitude floor, explicitly flagged as inference, not a measured minimum.
- **§6's viewport-width hypothesis**: structurally plausible (nine `page` values, each needing the map to share screen space with a different panel) but not checked against any actual screenshot or pixel measurement this session.
- **DF's own C++ source is not public**; every claim about *why* the renderer behaves a given way (as opposed to *what the struct fields are and what their live values currently read*) is bounded by that — `df-structures` documents field layout, not game logic, and several of its own enum/field comments here are explicitly self-flagged by DFHack's maintainers as reconstructed rather than decompiled (e.g. `find_results`'s `not a real enum` tag, carried over from the 2026-09-10 site-finder research).

---

## 8. Net assessment

Two of the five questions now have meaningfully stronger answers than a guess: **the absolute-vs-local coordinate split (Q2) moved from a type-size inference to a live, exact, reproducible confirmation** (`neighbor_hover_mm_*` == the committed site's own `abs_mm_start/end`, read live, same values), and **the overlay-gating question (Q3) now has a real, live, currently-observed mismatch** between `find_results` (still `Suitable`) and `doing_site_finder` (`false`) that is hard to explain any other way than "the overlay paint is gated on `doing_site_finder`, and this screen is currently sitting in exactly the state where that would produce the vanishing-overlay symptom described." The `xdotool`/`precise_mouse_x/y` cross-check (Q4) is now a worked, exact, live-verified formula rather than a restated assumption. The zoom-render gate (Q1) and the viewport-width instability (Q5) each have a specific, falsifiable, struct-grounded hypothesis (`setting_up_map_timer`'s gating; `page`-dependent panel width) that this pass could not close out without touching the live screen — both are handed off as concrete, cheap, specific next tests rather than "investigate further."

**Single highest-value next step**, if the live session wants to resolve the thing that actually broke tonight: run the Site Finder fresh and read `find_mm_*` + `neighbor_hover_mm_*` + `location.region_pos` in one atomic call immediately after. That one read either confirms or kills the "local-to-region-tile" hypothesis for `find_mm_*`, which is the coordinate confusion most directly implicated in tonight's "same numbers, different locations" failure.
