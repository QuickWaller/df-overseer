# Stonesense as a Headless, Per-Z-Level Renderer for the Public Pan/Zoom Viewer

Date: 2026-09-10
Scope: whether DFHack's bundled `stonesense` plugin (present and tagged "available and load-bearing" in `memory/dfhack-environment.md`, DFHack 53.16-r1.1, DF Classic 53.16, `df-colony-01`/VM 103) can serve as the renderer for a new feature — a periodic server-side capture job that renders each z-level (or the whole map) to an image, so each public web visitor can pan/zoom and switch z-levels client-side, independent of the shared live VNC camera.
Status: **desk research only.** No SSH access to VM 103 was used and no live infra was touched, per the task's explicit instruction. Everything below is either (a) read directly from this repo's own already-verified files (`memory/dfhack-environment.md`, `docs/DF-UI-AUTOMATION.md`, `scripts/install_df.py`, `decisions/DECISIONS.md`), (b) read directly from DFHack's local offline docs (`hack/docs/docs/...` on the Windows install, already-verified version-exact per this repo's own convention), or (c) read directly from the `DFHack/stonesense` GitHub repository's actual source files and issue tracker via the GitHub API/WebFetch — source over docs wherever they could be compared, with every disagreement between them named explicitly rather than silently resolved.

---

## 1. Bottom line, up front

**Stonesense is a real, live-maintained plugin whose own code confirms a documented, non-OpenGL software-rendering path exists (`[RENDERER:SOFTWARE]` in its own config), which is the single biggest reason to think headless Xvfb operation is plausible rather than a dead end.** But three separate, currently-open, primary-source-confirmed gaps mean the specific plan sketched in the task ("toggle single layer, set z, screenshot, increment z, repeat" against the plugin's own documented mechanisms) will not work as written, and needs a different concrete recipe than the one the doc text implies:

1. **`TOGGLE_SINGLE_LAYER` is confirmed broken upstream, not just undocumented** — GitHub issue [DFHack/stonesense#185](https://github.com/DFHack/stonesense/issues/185) (open, filed by a project maintainer): *"You can toggle it, and the OSD tells you when its on and thats literally all of its functionality."* There is no way, via the documented mechanism, to isolate exactly one z-level in the rendered view.
2. **Independent-camera mode (`TRACK_MODE:NONE`, what the local doc calls "moved independently" of the game view) is confirmed broken upstream** — [DFHack/stonesense#225](https://github.com/DFHack/stonesense/issues/225) (open, no comments, unresolved as of this research date): starting in that mode produces *"the viewport is centered on invalid coordinates"* — a blank screen.
3. **The full-map screenshot (`Ctrl+Shift+F5`) leaves the plugin unusable afterward**: the actual `.rst` source behind the docs site (not shown on the rendered HTML page, a real docs-vs-source gap — see §7) states plainly: *"Mega screenshots (Ctrl+Shift+F5) put the buffer into an invalid state after the screenshot is written to disk."* Stonesense must be closed and reopened after every full-map capture.

None of these are fatal, and a workaround for each is proposed in §4/§8 below, but the task's literal predicted mechanism does not survive contact with the actual plugin. The recommended concrete design — a per-z-level `SEGMENTSIZE_Z:1` walk using ordinary `F5` screenshots and DF's own already-tuned camera, not the megashot and not the single-layer toggle — is new to this research pass, marked **[proposed, not tested]** throughout, and is the single most load-bearing recommendation in this document.

**Licensing is a real, non-trivial caution, not a clean "yes."** Stonesense's code is Zlib-licensed (permissive), but its own `LICENSE` file states outright: *"Artwork (images and audio) remains copyright by their respective creators; they are licensed for use with Stonesense but require permission for other uses."* Publishing Stonesense-rendered screenshots publicly is very likely within the spirit of "use with Stonesense" (the plugin's own docs actively promote a screenshots thread and streaming setup), but it is not the unambiguous "yes" the task hoped to confirm — see §5.

---

## 2. Headless / software-rendering viability

**Verified from source, not inferred**: Stonesense renders via the **Allegro 5** graphics library (confirmed: `LICENSE` — *"Stonesense makes use of the Allegro 5 graphics libraries"*; confirmed independently in `CMakeLists.txt`, which links `allegro_primitives`, `allegro_font`, `allegro_color`, `allegro_image`, `allegro_ttf` and, on Linux, a prebuilt `liballegro.so.5.2` — DFHack ships Allegro as a binary dependency, not something built against the system's OpenGL/X11 dev packages). This is a different rendering stack from DF's own SDL2 window, so "DF's SDL rendering already works under Xvfb" is **not** direct proof Stonesense will — it is suggestive precedent (the same Xvfb display already hosts one working windowed renderer), not equivalent evidence, and this report does not conflate the two.

**The load-bearing finding**: Stonesense's own shipped config template exposes a renderer-selection key, confirmed by reading both the template and the code that consumes it:

- `configs/init.txt` (the upstream source for `dfhack-config/stonesense/init.txt`, confirmed identical purpose by the local doc's own reference to that path): `[RENDERER:ANY]` — *"Set the preferred renderer. Valid values are SOFTWARE, OPENGL, DIRECTX, and ANY."*
- `Config.cpp`'s parser, read directly:
  ```cpp
  if (line.find("[RENDERER") != string::npos) {
      string result = parseStrFromLine("RENDERER", line);
      config.opengl = (result == "OPENGL");
      config.software = (result == "SOFTWARE");
      config.directX = (result == "DIRECTX");
  }
  ```
- `main.cpp`'s display-creation call, read directly, only ever requests an OpenGL context when `config.opengl` is true:
  ```cpp
  al_set_new_display_flags(
      (ssConfig.config.Fullscreen && !ssConfig.overlay_mode ? ALLEGRO_FULLSCREEN : ALLEGRO_WINDOWED)
      |(ssConfig.overlay_mode ? 0 : ALLEGRO_RESIZABLE)
      |(ssConfig.overlay_mode ? ALLEGRO_MINIMIZED : 0)
      |(ssConfig.config.opengl ? ALLEGRO_OPENGL : 0)
      |(ssConfig.config.directX ? ALLEGRO_DIRECT3D_INTERNAL : 0));
  ```
  With `[RENDERER:SOFTWARE]`, neither `ALLEGRO_OPENGL` nor `ALLEGRO_DIRECT3D_INTERNAL` is ever set, so Allegro is never asked for a GL context at all — on Linux this should route to Allegro's plain Xlib/software display driver, the same category of "ask X11 for pixels, not a GPU" behavior DF's own SDL software path already uses successfully under this VM's Xvfb. **Confidence: [C] for the code path existing exactly as described (read directly, three independent files agreeing); [I] for "this will actually work well under Xvfb" — this is a reasoned inference from the code, not an empirical test.**

**Corroborating, build-time-only evidence**: this project's own local DFHack install docs confirm OpenGL is not even a hard build dependency: `hack/docs/docs/dev/compile/Dependencies.txt` lists *"OpenGL headers (**optional**: to build stonesense)"* — separate confirmation, from this project's own already-installed files, that a Stonesense build without OpenGL is a recognized, supported configuration, not something this report is guessing exists.

**What was searched for and not found**: no forum post, GitHub issue, wiki page, or blog post describing anyone actually running Stonesense under Xvfb, Docker, or for a wiki-screenshot-bot use case was located in this research pass, despite targeted searches (`stonesense headless Xvfb llvmpipe`, `stonesense screenshot wiki bot`, `stonesense docker`). The Dwarf Fortress Wiki's own "Screenshots thread" (linked from the plugin's own doc) is almost certainly hand-curated from players' own desktop sessions, not an automated pipeline — no evidence of the latter exists. **This means the "prior art" the task hoped for does not appear to exist**; this is itself a finding ("nobody really does this," stated plainly per this report's own conventions) rather than a search failure to paper over.

**Net assessment for Q1**: the `[RENDERER:SOFTWARE]` code path is real, documented, and specifically designed to avoid requesting hardware/GL acceleration — a materially better starting position than "the doc just says it needs graphics acceleration, hope for the best." But whether it actually produces correct, non-garbled output under this VM's specific Xvfb/Mesa stack is **explicitly unverified and needs an empirical test on the live VM** (out of scope for this desk-research pass) before any capture-job design should be finalized around it. The test is cheap and specific: set `[RENDERER:SOFTWARE]` in `dfhack-config/stonesense/init.txt`, run `stonesense` over the existing DFHack RPC/SSH access this project already has, and check whether `al_create_display` succeeds and whether an `F5` screenshot comes back as real pixels rather than blank/garbage — directly analogous to the exact diagnostic this project already used to prove/disprove the `USE_CLASSIC_ASCII` graphics bug (`research/2026-09-09-df-modern-graphics.md` Q2).

---

## 3. Automation/scripting surface

**Confirmed, directly from source: there is no scripted control surface for Stonesense's camera, z-level, or screenshot triggering — no CLI flags, no Lua API, no RPC.**

- **Lua API**: grepped this project's own local, version-exact `hack/docs/docs/dev/Lua API.txt` (the ~6900-line file `memory/dfhack-environment.md` already establishes as the authoritative, version-pinned reference) for `stonesense` — **zero matches**. Stonesense exposes nothing to DFHack's Lua layer at all.
- **RPC/protobuf**: the repo ships a `proto/` directory (suggesting a remote-interface surface might exist), but its only file, `proto/readme.txt`, reads in full: *"placeholder to fix build issues."* **[C]**, directly fetched — there is no real protobuf/RPC interface here despite the directory name.
- **Command-line arguments to the `stonesense`/`ssense` DFHack command itself**: read `main.cpp`'s actual command callback in full:
  ```cpp
  DFhackCExport command_result stonesense_command(color_ostream &out, std::vector<std::string> & params)
  {
      if(stonesense_started) {
          out.print("Stonesense already running.\n");
          return CR_OK;
      }
      stonesenseState.ssConfig.overlay_mode = false;
      if(params.size() > 0 ) {
          if(params[0] == "overlay"){
              //ssConfig.overlay_mode = true;
          } else {
              DumpInfo(out, params);
              return CR_OK;
          }
      }
      // ... initialization code ...
  }
  ```
  The only recognized parameter is the literal string `"overlay"` (and that branch is dead — the line that would set `overlay_mode = true` is commented out). Any other argument routes to `DumpInfo()`, read in full from `DumpInfo.cpp`:
  ```cpp
  void DumpInfo(DFHack::color_ostream & out, std::vector<std::string> & params)
  {
      std::string & p1 = params[0];
      if(p1 == "dumpitems") { ... DumpItemNamesToDisk("itemdump.txt"); ... }
      else if(p1 == "dumptiles") { ... DumpTileTypes("tiledump.txt"); ... }
      else if(p1 == "genterrain") { ... GenerateTerrainXml(...); ... }
      else { out.printerr("invalid argument\n"); }
  }
  ```
  These are one-shot debug data-dump commands (equipment names, tile types, a terrain XML template) — none of them touch the camera, z-level, or screenshot mechanism, and (per the guard clause above) `DumpInfo` is only ever reached when `stonesense_started` is still `false`, i.e. before/without actually running the visualizer. **Confirmed [C]: there is no command-line path to controlling a running Stonesense window.**

**Consequence: the only automation surface is real keyboard/mouse input to Stonesense's own window**, the same category of technique `docs/DF-UI-AUTOMATION.md` already proved out for DF's own map/embark screens (`xdotool` sending genuine X11 events to `DISPLAY=:99`, because DFHack's fake `gui.simulateInput` cannot drive anything that reads real OS mouse/keyboard state — confirmed there for DF's `precise_mouse_x/y`, and Stonesense's controls are **entirely** its own native Allegro input handling, not routed through DFHack's screen/viewscreen system at all, so the same category of limitation applies by construction, not by inference).

**What's different and genuinely new risk, not covered by the existing `docs/DF-UI-AUTOMATION.md` playbook**:
- Stonesense opens as **a second, separate window** on the same Xvfb display (confirmed: the plugin doc's own words, "Open the visualiser in a new window" — this is not a DF viewscreen, it is a distinct Allegro-owned X11 window). `docs/DF-UI-AUTOMATION.md`'s calibration (`+0,+40` window offset, `xwininfo -root -tree` confirmation) was performed against DF's single window on a display with **no window manager running**. With two windows on a WM-less display, keyboard input routing depends on X11 input-focus state that nothing currently manages explicitly — **this is a genuinely new, unverified risk**: without a WM to arbitrate focus, whichever window most recently received an X11 focus event (or the one still holding it from creation) gets keystrokes, and `xdotool windowactivate`/`xdotool windowfocus` (targeting Stonesense's window ID specifically, obtainable via `xdotool search --name` or `--class`) will very likely be a required addition to the existing recipe, not an optional nicety. **Not tested this session — flagged as the single highest-value live test for the automation side**, alongside the `[RENDERER:SOFTWARE]` check in §2.
- Stonesense's keybinds are configured through its own `dfhack-config/stonesense/keybinds.txt` (confirmed by both the local doc and the repo's `configs/keybinds.txt` template), a completely separate keymap namespace from DF's own interface keys — the existing `docs/DF-UI-AUTOMATION.md` catalog of DF-specific key facts (e.g. `CUSTOM_W/A/S/D`) does not transfer; Stonesense's pan keys are plain arrow keys by default (`DECR_Y:KEYS_UP`, etc., confirmed from the local doc and cross-checked against the live `UserInput.cpp` action list below), which is simpler, not harder, than DF's own custom-interface-key requirement.

**Full confirmed action-name list**, read directly from `UserInput.cpp` (more complete than the local doc's own keybind-file excerpt, useful for anyone extending the keybind config): `INCR_ROTATION`, `RELOAD_SEGMENT`, `PAINTBOARD`, `TOGGLE_STOCKPILES`, `TOGGLE_DESIGNATIONS`, `TOGGLE_ZONES`, `TOGGLE_OCCLUSION`, `TOGGLE_FOG`, `TOGGLE_CREATURE_MOOD`, `TOGGLE_CREATURE_PROF`, `TOGGLE_CREATURE_JOB`, `CHOP_WALL`, `CYCLE_TRACKING_MODE`, `RESET_SCREEN`, `DECR_SEGMENT_X/Y/Z`, `INCR_SEGMENT_X/Y/Z`, `TOGGLE_SINGLE_LAYER` (confirmed broken, §1/§4), `TOGGLE_SHADE_HIDDEN`, `TOGGLE_SHOW_HIDDEN`, `TOGGLE_CREATURE_NAMES`, `TOGGLE_OSD`, `TOGGLE_KEYBINDS`, `TOGGLE_ANNOUNCEMENTS`, `TOGGLE_DEBUG`, `INCR_ZOOM`, `DECR_ZOOM`, `SCREENSHOT`, `INCR_RELOAD_TIME`, `DECR_RELOAD_TIME`, `CREDITS`, `DECR_X/INCR_X/DECR_Y/INCR_Y`, `DECR_Z/INCR_Z`.

**Z-clamping, confirmed from source** (relevant to §4): `DECR_Z` clamps at a floor (`if(ssState.Position.z<1) { ssState.Position.z = 1; }`), but **`INCR_Z` has no corresponding upper-bound check** — a naive "increment until nothing changes" sweep has no natural stop condition from Stonesense's own state. §4 below covers the correct source for the real bound.

---

## 4. The "whole map at full resolution" screenshot (`Ctrl+Shift+F5`)

**Answer: no, it does not capture the whole explored map "regardless of current window size and zoom" — it captures whatever is in the currently-loaded segment, which is itself bounded by config and camera position.** This is a real correction to the framing in the task brief, made from reading the actual code, not an assumption.

Read directly from `UserInput.cpp`'s dispatcher:
```cpp
void action_screenshot(uint32_t keymod)
{
    if (keymod&ALLEGRO_KEYMOD_CTRL) {
        if (keymod&ALLEGRO_KEYMOD_SHIFT) { saveMegashot(true); }
        else { saveMegashot(false); }
    } else if (keymod&ALLEGRO_KEYMOD_ALT) { dumpSegment(); }
    else { saveScreenshot(); }
}
```
So `F5` → `saveScreenshot()`, `Ctrl+F5` → `saveMegashot(false)`, **`Ctrl+Shift+F5` → `saveMegashot(true)`** ("the whole map at full resolution").

`saveMegashot`'s actual sizing logic, read from `GUI.cpp`:
```cpp
ssState.ScreenW = ((ssState.RegionDim.x + ssState.RegionDim.y) * TILEWIDTH / 2) * ssConfig.scale;
if (tall) {
    ssState.ScreenH = ( ((ssState.RegionDim.x + ssState.RegionDim.y) * TILETOPHEIGHT / 2)
                         + (ssState.RegionDim.z * TILEHEIGHT) ) * ssConfig.scale;
} else {
    ssState.ScreenH = ( ((ssState.RegionDim.x + ssState.RegionDim.y) * TILETOPHEIGHT / 2)
                         + ((ssState.Size.z - 1) * TILEHEIGHT) ) * ssConfig.scale;
}
bigFile = al_create_bitmap(ssState.ScreenW, ssState.ScreenH);
```
`RegionDim.x/y/z` is genuinely computed from the actual map's block dimensions (`MapLoading.cpp`: `blockDimX *= BLOCKEDGESIZE; ssState.RegionDim.x = blockDimX;` etc.) — but the **segment that gets loaded in the first place is viewport/camera-relative**, per `MapLoading.cpp`'s own read logic (`firstTileToReadX = inState.Position.x; ... while (firstTileToReadX < inState.Position.x + inState.Size.x)`), not an unconditional whole-map load. This is exactly what the local doc's own hint — *"you may need to zoom out before taking very large screenshots"* — is describing: the megashot renders whatever segment is currently resident, and that segment's extent is governed by `SEGMENTSIZE_XY`/`SEGMENTSIZE_Z` (config, defaults `70` and `4` respectively, confirmed from `configs/init.txt`) and the camera's current position, not an omniscient "give me the whole revealed map" query. **For a fort deeper than 4 z-levels (essentially any real fort), `SEGMENTSIZE_Z` must be raised in `dfhack-config/stonesense/init.txt` before a `tall`/`Ctrl+Shift+F5` megashot will include the fort's full depth — this is a config change this project would need to make deliberately, not something that happens automatically from "zooming out."** **[C]**, read directly from three source files agreeing with each other and with the doc's own hint.

`tall` (`Ctrl+Shift+F5`) vs. not (`Ctrl+F5`): `tall` adds `RegionDim.z * TILEHEIGHT` to the image height (every loaded z-level stacked into one cutaway image); the non-tall variant adds only `(Size.z - 1) * TILEHEIGHT` (a single top level). Neither variant produces "one image per z-level" — both produce a single flattened isometric render, differing only in whether the lower levels are visible as a cutaway underneath the top one. **This directly matters for Q4 below: the megashot mechanism is not the right tool for a per-z-level image set at all**, regardless of the buffer-corruption issue.

**Format and save location, confirmed from source**: PNG, via `al_save_bitmap(filename.string().c_str(), bigFile)`. The filename comes from `getAvailableFilename()`, read in full from `GUI.cpp`:
```cpp
std::filesystem::path getAvailableFilename(std::string prefix, std::string suffix = ".png")
{
    int index = 1;
    while (true) {
        std::stringstream buf{};
        buf << prefix << index << suffix;
        std::filesystem::path filename{ buf.str() };
        if (!std::filesystem::exists(filename)) return filename;
        index++;
    }
}
```
**There is no directory-path logic anywhere in this function or its caller** — it is a bare relative filename (`screenshot1.png`, `screenshot2.png`, ...), resolved against whatever the Stonesense/DFHack process's **current working directory** happens to be at the moment it runs. Cross-referenced against this project's own `scripts/install_df.py` systemd unit template: `WorkingDirectory=%(game)s` (line 544, the game's own install directory — the same directory the `dfhack`/`dwarfort` binaries live in). **Conclusion, [C] by combining two independently-read primary sources**: on VM 103, Stonesense screenshots land directly in the DF install directory (**not** `~/.local/share/Bay 12 Games/Dwarf Fortress/save/`, which is only where *saves* live per `docs/PURPOSE.md`) — matching the plugin doc's vague "saved to the DF directory" exactly, and giving a concrete, actionable path for a capture job's file-collection step. Sequential numbering with no cleanup also means a long-running capture job must delete or rename prior `screenshotN.png` files itself, or the counter will climb forever and stale files will accumulate in the game's own install directory.

**The buffer-invalidation caveat, new to this research pass, not in the local doc**: `docs/Stonesense.rst`, the actual documentation source in the GitHub repo (not visible on the rendered `docs.dfhack.org` HTML page for this version — see §7's docs-vs-source note), states: *"Mega screenshots (Ctrl+Shift+F5) put the buffer into an invalid state after the screenshot is written to disk."* Practical reading: after every `Ctrl+Shift+F5`, Stonesense must be closed and relaunched before it can be used again — a real, repeated cost for any design that leans on the megashot specifically. **[C]**, quoted directly from the repo's own doc source.

---

## 5. Multi-z-level capture — the megashot is the wrong tool; a different recipe is proposed

Given §4 (megashot = one flattened multi-level image, not a per-z set, plus a forced-restart cost) and §1 (`TOGGLE_SINGLE_LAYER` confirmed non-functional), **the task's literal proposed sequence ("toggle single-layer, set z, screenshot, increment z, repeat") cannot work as written** — there is no working single-layer isolation to toggle.

**Proposed alternative, [proposed, not tested], reasoned directly from the confirmed config/code behavior above**: set `SEGMENTSIZE_Z:1` in `dfhack-config/stonesense/init.txt`. Per `MapLoading.cpp`'s segment-loading logic (§4), this constrains the *loaded* vertical range to a single z-level's worth of blocks around the current `Position.z`, independent of whether `TOGGLE_SINGLE_LAYER`'s rendering-side toggle works — this sidesteps the broken feature by constraining the data actually available to render, rather than trying to hide already-loaded data at render time. The per-z-level loop becomes:
1. Set `Position.z` to the desired level (`INCR_Z`/`DECR_Z`, or `KEYS_PGUP`/`KEYS_PGDN`/`KEY_0`/`KEY_9` per the default keybinds).
2. `RELOAD_SEGMENT` (`KEY_R`) to force a re-read at the new `Position.z` with the now-thin `SEGMENTSIZE_Z:1` window (`automatic_reload_time` config also exists for a polling reload, but an explicit reload after a z-change is more deterministic for a scripted loop).
3. Plain `F5` (`saveScreenshot()`, **not** the megashot) — this captures the current viewport at `ssState.ScreenW/ScreenH` (the configured window size), which now shows only the one loaded z-level's worth of geometry. This also avoids the megashot's buffer-invalidation cost entirely, since only `saveMegashot` is documented to corrupt the buffer.
4. Repeat, incrementing `Position.z`.

**Where to get the stopping bound, since Stonesense's own `INCR_Z` has no upper clamp (§3)**: use DFHack's own, already-confirmed-real Lua API, independent of Stonesense entirely — `dfhack.maps.getSize()` / `dfhack.maps.getTileSize()`, both confirmed present in this project's local `hack/docs/docs/dev/Lua API.txt` (*"Returns map size in blocks: x, y, z"* / *"Returns map size in tiles: x, y, z"*). This gives the map's total allocated z-extent (which includes open sky and any unrevealed cavern layers, not strictly "explored" depth specifically), so a capture loop should treat it as an upper bound to iterate up to and tolerate/skip all-blank output for levels with nothing built or visible, rather than expect it to exactly equal "the fort's explored depth." **[C]** for the API existing and its documented return shape; **[I]** for "this is definitely the right bound to use," since Stonesense's `RegionDim.z`/`Size.z` fields (populated from the same underlying block data per `MapLoading.cpp`) were not cross-checked live against `dfhack.maps.getSize()`'s output this session.

**Whether horizontal (X/Y) framing needs similar per-level handling**: not investigated in depth this pass — `SEGMENTSIZE_XY` (default `70`) governs the horizontal footprint loaded per segment, and a fort wider than that would need either a larger `SEGMENTSIZE_XY` or the same kind of tiled-capture approach the task is already designing for z-levels, applied to X/Y as well. Flagged as an open design question, not resolved here.

---

## 6. Sprite art licensing/provenance

**Confirmed, primary source, not assumed: Stonesense's bundled sprite art is a completely separate body of assets from the DF vanilla/Premium tileset this project already transplanted (`decisions/DECISIONS.md` 2026-09-09, "Official Steam-graphics transplant..."), and it carries its own, more restrictive licensing note.**

`LICENSE` (`DFHack/stonesense`, fetched and decoded directly, quoted in full where relevant):
> "Stonesense code and documentation is under the copyright of the authors - Japa, Caldfir, Peterix, Jonask, Solifuge and Kaypy on Bay12 forums, plus anyone in the Git history. It is distributed under the Zlib license (below), like DFHack. For historical reasons, you may also use the code under any version of the GNU General Public License, or under any version of the Perl Artistic License.
>
> **Artwork (images and audio) remains copyright by their respective creators; they are licensed for use with Stonesense but require permission for other uses.**
>
> Stonesense makes use of the Allegro 5 graphics libraries, which also uses the Zlib license (below). Allegro is 'Copyright © 2008-2010 the Allegro 5 Development Team'"

Reading this plainly: the **code** is unambiguously permissive (Zlib, with GPL/Artistic as alternatives). The **sprite/audio assets** are not — they remain under their original artists' copyright, explicitly scoped to "use with Stonesense," with "other uses" requiring separate permission. This is a materially different legal footing from the DF vanilla-tileset transplant, where the legitimacy basis recorded in `decisions/DECISIONS.md` rests on "the user's own purchased copy, copied for personal use... never redistributed" — that reasoning does not automatically carry over here, because Stonesense's assets were never purchased by anyone in this project; they are bundled, third-party-authored, DFHack-distributed art with an explicit "ask first for anything beyond running the tool" clause.

**Is running Stonesense and publishing its screenshots "use with Stonesense," or an "other use"?** This report cannot rule definitively — no case law or maintainer clarification was found — but offers a reasoned, explicitly-labeled **[I] inference**: Stonesense's own documentation actively promotes screenshot-sharing and streaming as normal, encouraged behavior — the local doc lists a *"Screenshots thread"* as an official community link, and a dedicated *"Streaming Stonesense on Windows"* section exists purely to help people broadcast it via OBS. A tool whose own maintainers document how to livestream it is hard to read as intending "screenshot" to fall outside "use with Stonesense." **This is meaningfully different, though, from extracting and reusing the raw sprite PNG files themselves** (e.g. building a custom compositor with Stonesense's own art assets rather than Stonesense's renderer) — that would be a much more clearly "other use," and this report does not recommend it. **Net: publishing Stonesense-rendered screenshots of this project's own fort is very likely fine by the spirit of the license and by the tool's own documented culture, but it is not the "unambiguously fine" confirmation the task asked for — it rests on an inference about intent, not explicit written permission, and should be treated by the user as a judgment call rather than a closed question.**

---

## 7. Known stability risks, performance, and version compatibility

**Beyond the already-known fort-reload crash** (local doc: *"you MUST close Stonesense before loading the new fort or the game will crash"*), this pass found:

**Confirmed-open, currently-unfixed bugs relevant to this design** (both already covered above, restated here for the stability-risk inventory): `TOGGLE_SINGLE_LAYER` no-op (#185), `TRACK_MODE:NONE` blank viewport (#225).

**Recent crash history — reassuring, not alarming**: querying the `DFHack/stonesense` issue tracker directly (`gh api repos/DFHack/stonesense/issues`, filtered for crash/segfault/memory keywords across all states and all time) turned up exactly **one** recent hit: [#255](https://github.com/DFHack/stonesense/issues/255)/closed 2026-07-12, "Fix segfault in lookupMaterialColor from unbounded color index" — and this fix is already reflected in the public changelog at **DFHack 53.15-r2** (*"fixed a crash when rendering materials with an out-of-range color index"*), one release series **before** this project's pinned 53.16-r1.1. **[C]**: this specific, recent crash is already fixed in the version this project runs. Older segfault reports found in general web search (OS X display-creation crashes from 2012-2014, a window-resize segfault, a "29 floor layers" crash from 2014) are all old enough (pre-v50, different OS, or both) that their relevance to the current Linux/53.16 build is genuinely uncertain — noted for completeness, not treated as current risk.

**Performance/memory**: **no documented CPU or RAM figures were found anywhere** — not in the plugin's own docs, not in the GitHub issues searched, not in general web search. The only performance-relevant facts found are qualitative: the plugin doc's *"we recommend at least a dual core CPU to avoid slowing down your game of DF"*, and two tuning knobs confirmed in `configs/init.txt` — `SEGMENTSIZE_XY` (default 70) and `SEGMENTSIZE_Z` (default 4) — which trade rendered-area size against performance, with the local doc's community guidance (found via web search, not this repo's own docs) suggesting lower values if "the window refresh rate is too low" on a large fortress. **This project's VM (4 vCPU, 4096 MB, single-core-clock-bound per `docs/PURPOSE.md`) has no empirical data point for Stonesense's actual cost, and this cannot be estimated responsibly from documentation alone — it needs a live measurement** (process RSS and `dfhack`'s own CPU-time delta, the same style of check `docs/PURPOSE.md` already used to measure the worldgen memory spike) before being treated as safe to run continuously alongside the live fort. **Flagged as the clearest "could not verify, needs empirical test" item in this whole report.**

**Version compatibility**: no open issue or discussion found specifically flagging 53.16/DFHack 53.16-r1.1 incompatibility. `memory/dfhack-environment.md`'s own availability audit (both the Windows Steam install and the Linux VM install, per that file's header) already lists `stonesense` as "available and load-bearing" for this exact version pair — the strongest evidence available, since it's this project's own direct confirmation the plugin loads and is enabled on the actual install in question, not a general claim about the DFHack project.

**Docs-vs-source discrepancy, named explicitly per this report's own standard**: the rendered `docs.dfhack.org/en/53.16-r1/docs/tools/stonesense.html` page (fetched directly) does **not** mention the megashot buffer-invalidation caveat that the actual `docs/Stonesense.rst` source in the `DFHack/stonesense` GitHub repo does contain verbatim. Per this report's evidence standard, **the source is treated as authoritative** and the caveat is included in §4/§1 above; the rendered docs site should be treated as possibly lagging its own source for at least this one detail.

---

## 8. What could not be verified (needs a live test on VM 103, explicitly out of scope here)

- **Whether `[RENDERER:SOFTWARE]` actually produces correct pixels under this VM's specific Xvfb/Mesa configuration** — the code path is confirmed to exist and to avoid requesting an OpenGL context, but no equivalent-environment report of it working was found anywhere, and this project's own precedent (`research/2026-09-09-df-modern-graphics.md`) shows that a rendering path can look correct on paper and still fail in a specific, environment-dependent way (the `USE_CLASSIC_ASCII:NO` blank-map bug) — this needs the same style of direct, screenshot-based verification, not a docs-based conclusion. **Single highest-priority live test.**
- **X11 focus/window-targeting behavior with two windows (DF's and Stonesense's) on a WM-less Xvfb display** — `docs/DF-UI-AUTOMATION.md`'s existing `xdotool` recipe was proven against exactly one window; whether `xdotool windowactivate`/`windowfocus` reliably steers keystrokes to Stonesense's window specifically, without a window manager present to arbitrate, is untested.
- **Whether `dfhack.maps.getSize().z` / `getTileSize().z` actually matches Stonesense's own `RegionDim.z`/`Size.z`** for a real fort — reasoned to be drawn from the same underlying block data, not cross-checked live.
- **Actual CPU/RAM cost of running Stonesense continuously (or even periodically) on the 4 vCPU/4096 MB VM alongside the live fort** — no documented figures exist anywhere found in this research; needs a direct measurement.
- **Whether the proposed `SEGMENTSIZE_Z:1` + per-level `RELOAD_SEGMENT` + `F5` loop actually produces clean, correctly-cropped single-level images in practice** — this is a reasoned design built from confirmed code behavior, not something run against a live fort. It could still have unforeseen edge cases (e.g. whether `RELOAD_SEGMENT` fully re-derives `RegionDim`/window sizing after a `SEGMENTSIZE_Z` change, or only reloads tile contents at the existing size).
- **Whether publishing Stonesense screenshots publicly is definitively within the bounds of "use with Stonesense"** — this is a licensing-intent question with no authoritative answer found; §6's reasoning is the best available inference, not a resolved fact.

---

## 9. Sources

- `DFHack/stonesense` GitHub repository (read directly via GitHub API/WebFetch, master branch, this research date): `LICENSE`, `README.md`, `CMakeLists.txt`, `main.cpp`, `GUI.cpp`, `GUI.h`, `Config.cpp`, `UserInput.cpp`, `MapLoading.cpp`, `DumpInfo.cpp`, `configs/init.txt`, `configs/keybinds.txt`, `docs/Stonesense.rst`, `proto/readme.txt`. Primary source, verified directly, highest confidence in this report.
- [DFHack/stonesense#185 — "Single Layer view literally does nothing"](https://github.com/DFHack/stonesense/issues/185) — open, unresolved. Primary source.
- [DFHack/stonesense#225 — "stonesense has blank viewport when starting in FOLLOW=NONE mode"](https://github.com/DFHack/stonesense/issues/225) — open, unresolved. Primary source.
- [DFHack/stonesense#255 — "Fix segfault in lookupMaterialColor from unbounded color index"](https://github.com/DFHack/stonesense/issues/255) — closed 2026-07-12, already shipped in 53.15-r2 per the public changelog. Primary source.
- [DFHack changelog / NEWS — docs.dfhack.org](https://docs.dfhack.org/en/stable/docs/NEWS.html) — stonesense-specific entries across versions, confirming recent, active maintenance and the 53.15-r2 fix. Primary source.
- [stonesense — DFHack 53.16-r1 documentation](https://docs.dfhack.org/en/53.16-r1/docs/tools/stonesense.html) — rendered docs for this project's exact pinned version; cross-checked against the repo's own `.rst` source, one discrepancy found and flagged (§7).
- This project's own already-verified local files: `memory/dfhack-environment.md` (availability audit, both installs), `hack/docs/docs/tools/stonesense.txt` and `hack/docs/docs/dev/Lua API.txt` and `hack/docs/docs/dev/compile/Dependencies.txt` (local Windows DFHack install, version-exact per this repo's convention), `docs/DF-UI-AUTOMATION.md` (existing `xdotool`/window-offset technique this report extends), `docs/PURPOSE.md` (VM spec, memory-measurement precedent), `scripts/install_df.py` (systemd `WorkingDirectory`), `decisions/DECISIONS.md` 2026-09-09 rows (the DF vanilla-tileset transplant, contrasted against Stonesense's separate licensing in §6).
- General web search (`WebSearch`) for headless/Docker/wiki-bot prior art and recent crash reports — searched, explicitly came back empty for the former (§2), reported as a finding rather than an omission.

---

## 10. Recommendation

**Stonesense is worth a small, cheap empirical spike before either committing to it or ruling it out — the evidence does not cleanly point to either "definitely build on this" or "definitely use the custom compositor instead."**

**The case for Stonesense**: it is the only route to genuine 3D isometric rendering with real sprite art without writing a renderer from scratch — building an equivalent custom compositor would mean reimplementing tile geometry, sprite selection, and material-to-color/sprite mapping essentially from zero, a large amount of net-new code this project does not currently have. The `[RENDERER:SOFTWARE]` path is real and specifically designed for exactly this no-GPU scenario, and the plugin is confirmed present, enabled, and load-bearing on this exact DFHack version already. The two broken features (`TOGGLE_SINGLE_LAYER`, `TRACK_MODE:NONE`) both have concrete, reasoned workarounds (§5's `SEGMENTSIZE_Z:1` loop; driving DF's own already-proven camera via `xdotool` before each capture rather than needing Stonesense's own independent-camera mode at all, since the capture job is periodic and offline rather than live per-viewer anyway).

**The case for caution**: three separate confirmed-open bugs in the exact mechanisms the task's design leaned on is a real signal, not noise — this is a smaller, less-resourced project than DFHack's core, and "the documented feature doesn't work, use this workaround we reasoned out from source" is a materially higher-maintenance starting position than "call an already-proven structured-data API." The automation surface requires extending the `xdotool` technique to a second, unfocused window on a WM-less display — new, unproven territory, not a copy-paste of the existing recipe. The licensing question (§6) is a real, if probably-low-risk, open item, whereas the already-completed DF-tileset transplant's legitimacy is airtight by comparison. And no performance data exists at all for a tool this project would be asking to run continuously on an already resource-modest VM.

**Concrete next step, not "more research"**: the two cheapest possible live tests would resolve almost all of the remaining uncertainty at once — (1) set `[RENDERER:SOFTWARE]`, launch `stonesense`, take one `F5` screenshot, and look at it (resolves §2's central unknown); (2) if that works, try `xdotool search --name`/`windowactivate` against Stonesense's window specifically and confirm a keypress reaches it rather than DF's window (resolves §3's new risk). Both are small, bounded, and would turn this report's [I]-tagged reasoning into [C]-tagged fact either way. If both succeed, the `SEGMENTSIZE_Z:1` per-level walk in §5 is the concrete design to build next. If either fails outright, the custom-compositor alternative remains fully available and loses nothing by having waited — it is built entirely on `RemoteFortressReader`/`dfhack.maps`, APIs this project has already confirmed present and working (`memory/dfhack-environment.md`), and does not depend on anything in this report panning out.

---

## 11. Relevant to

`ROADMAP.md`/`Working.md`'s live-viewing thread (the pan/zoom-per-viewer feature this research was commissioned for) and `docs/PURPOSE.md`'s *Streaming the fortress* section (the "human view and model view are different artifacts" commitment #6 — Stonesense is squarely a human-view-only tool, no bearing on design commitment #1). Also relevant to `decisions/DECISIONS.md`'s 2026-09-09 graphics-transplant row, which this report deliberately contrasts against in §6 rather than assumes the same legitimacy basis applies.
