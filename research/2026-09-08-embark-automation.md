# Driving an Unattended Embark via `gui.simulateInput`: Screens, Keys, Verification

Date: 2026-09-08
Scope: what a DFHack Lua script would need to drive DF v0.53.16 / DFHack 53.16-r1.1 from the title screen to a running fort with no rendered output, on `df-colony-01` (VM 103, `<df-vm-ip>`).
Status: **read-only reconnaissance.** No key was simulated, no click was sent, and no screen was advanced. Everything below comes from (a) reading the installed DFHack Lua source under `/opt/df/game/hack/scripts/`, (b) reading `/opt/df/game/hack/docs/docs/dev/Lua API.txt` and `/opt/df/game/hack/news*.rst`, (c) reading `/opt/df/game/data/init/interface.txt`, and (d) a handful of read-only Lua queries against the live DFHack RPC server (`dfhack-run lua "print(...)"`, and one enum dump to a temp file) that only inspect state — `dfhack.gui.getCurViewscreen()`, global enum values, and one full dump of the `interface_key` enum names. None of these mutate game state; several are quoted verbatim below with their exact command.

The single biggest finding: **the actual title→embark screen flow (Start → pick a region → new game vs. continue) could not be observed live**, because observing it means pressing keys, which was out of scope for this pass. Everything about that specific transition is inference from field names and script comments, not a confirmed trace. Section 8 flags this explicitly as the top follow-up.

---

## 1. The answer, up front

The three embark-flow viewscreen classes are confirmed by primary source, not guessed: `df.viewscreen_adopt_regionst` → `df.viewscreen_choose_start_sitest` → `df.viewscreen_setupdwarfgamest`, ending in `df.viewscreen_dwarfmodest`. This list comes verbatim from a real, shipped DFHack script's own state-machine logic (`deep-embark.lua`), not from documentation prose — see §3.

The keybinding picture is *not* what the task brief expected. `data/init/interface.txt` has **zero** named `[BIND:...]` entries for anything embark- or site-selection-specific — no `EMBARK`, `CHOOSE_START`, `SETUPDWARF`, or `SITE` binds exist anywhere in the file (confirmed by grep, §4). The screens are driven by (a) the same generic keys every DF list/menu screen uses (`SELECT`, `LEAVESCREEN`, `STANDARDSCROLL_*`, `CHANGETAB`), plus (b) for the one step that actually matters spatially — picking *where* to embark — **mouse input against screen fields, or direct field writes that bypass the mouse entirely**. The bundled `gui/embark-anywhere.lua` proves the second path works: it picks a site by writing `scr.warn_flags.GENERIC`, `scr.neighbor_hover_mm_sx/ex/sy/ey` etc. directly rather than simulating a click sequence. That is almost certainly the right model for an unattended embark script too, and it is a stronger, more DFHack-idiomatic answer than "figure out the click coordinates," because it never requires computing screen pixel/tile positions from a render at all — it fits design commitment #1 more comfortably than mouse simulation would.

The success check is not a proposal, it is copied from a real installed tool. `on-new-fortress.lua` — a genuine DFHack utility, not a demo — gates on exactly `dfhack.world.isFortressMode() and df.global.plotinfo.fortress_age == 0`, and its own doc text says this is "only true on the first tick after the initial embark." That is the strongest, most primary-source-grounded verification signal found (§7).

The weakest link is the first hop: **how you get from the title screen's main menu to a specific existing region and into a fresh embark (as opposed to continuing a save)**. No script in the installed `hack/scripts/` tree exercises this transition — everything downstream of `viewscreen_choose_start_sitest` has example code; nothing upstream of it does. This is the part a follow-up implementation script will have to feel its way through live, carefully, with `dfhack.gui.getCurViewscreen()` polling after every simulated key.

---

## 2. Current live state (verified read-only, 2026-09-08)

```
$ /opt/df/game/dfhack-run lua "print(dfhack.gui.getCurViewscreen()._type) print(df.global.gametype) print(dfhack.world.isFortressMode())"
type: viewscreen_titlest
12
false
```

```
$ /opt/df/game/dfhack-run lua "print(df.game_type[df.global.gametype]) print(df.global.gametype)"
NONE
12
```

```
$ /opt/df/game/dfhack-run lua "print(df.game_mode[df.global.gamemode]) print(df.global.gamemode) print(dfhack.isWorldLoaded()) print(dfhack.isMapLoaded())"
NONE
3
false
false
```

So, confirmed and current as of this session:

- The top of the viewscreen stack is `viewscreen_titlest`, with `viewscreen_initial_prepst` as its parent (from a `pairs()` field dump, see below) — i.e. DF is sitting at the outer main menu, nothing more.
- `df.global.gametype` (enum `game_type`) and `df.global.gamemode` (enum `game_mode`) are **two separate globals**, both currently `NONE`, but with different underlying numeric values (12 vs 3 respectively) — do not confuse them in state-check code. `game_mode` is the one the DFHack Lua API's own persistence-pattern example (`Lua API.txt`, ~line 6856) checks against (`df.global.gamemode ~= df.game_mode.DWARF`), which is worth following as the idiomatic choice.
- `dfhack.isWorldLoaded()` and `dfhack.isMapLoaded()` are both `false` — the previously-generated world (memory's "world 1, POCKET ISLAND") exists on disk but is **not** currently loaded into memory. It shows up as one entry in the title screen's own `region_choice` list (below), not as a loaded world.

A field dump of the current `viewscreen_titlest` (via `for k,v in pairs(scr) do ... end`, not `printall` — `printall` on this screen actually broke the RPC connection once during this session, see §8) confirmed, among 64 fields:

- `mode = 0`, `selected = 0`, `selected_r = 0` — page state and current-selection cursor(s). `selected` is almost certainly the highlighted index into `menu_line_id` (the six main-menu entries below); `selected_r` is plausibly the cursor into `region_choice`, by naming convention only — **not independently confirmed**.
- `menu_line_id` — a `vector<main_choice_type>` of length 6. Enumerated live:

  ```
  0  Start
  1  NewWorld
  2  TestingArena
  3  Settings
  4  AboutDF
  5  Quit
  ```

- `region_choice` — a `vector<region_headerst*>` of length **1** (the existing POCKET ISLAND world).
- `savegame_header_world`, `savegame_header_game` — both length 0 (no existing fort save under that world yet, consistent with "no fort embarked" in memory).
- `parent = <viewscreen_initial_prepst: ...>` — confirms the screen directly beneath the title screen on the stack.

---

## 3. The confirmed screen sequence

Source: `/opt/df/game/hack/scripts/deep-embark.lua`, function `inEmbarkMode()` (read in full):

```lua
function inEmbarkMode()
    if df.global.gametype ~= df.game_type.DWARF_MAIN then -- is always set at fortress mode setup
        return false
    end
    local embarkViewScreens = {
        df.viewscreen_adopt_regionst, -- onLoad.init kicks in early; this is the viewscreen present at this stage
                                       -- (the 'loading world' viewscreen is also present at adventure mode setup
                                       -- and legends mode, hence the game_type check above)
        df.viewscreen_choose_start_sitest,
        df.viewscreen_setupdwarfgamest
    }
    ...
```

This is a real, currently-shipped DFHack tool's own definition of "we are somewhere in the embark flow" — high confidence, it is not documentation prose, it is the logic a working script actually branches on. It gives the ordered class list directly:

**`viewscreen_adopt_regionst` → `viewscreen_choose_start_sitest` → `viewscreen_setupdwarfgamest`**

with the important caveat baked into the comment: `viewscreen_adopt_regionst` is *not* embark-specific by itself — the same "loading world" screen also appears when starting adventure mode or entering legends mode, which is why `deep-embark.lua` additionally checks `df.global.gametype == df.game_type.DWARF_MAIN` before trusting it. An embark-driving script needs the same double-check.

Downstream of `viewscreen_setupdwarfgamest`, fortress mode itself runs on `viewscreen_dwarfmodest` — confirmed indirectly: `deep-embark.lua`'s `DeepEmbarkMonitor` state machine explicitly checks `view._type == df.viewscreen_dwarfmodest` as the "we're in game" terminal state, and treats reaching it *without* having passed through `choose_start_sitest` first as "this was a save load, not an embark, abort":

```lua
elseif view._type == df.viewscreen_dwarfmodest then -- we're in game. If we got here then we never got
                                                       -- an embark screen, so this is loading a save and we abort.
```

**What is not confirmed**: the exact transition *before* `viewscreen_adopt_regionst` — i.e. how selecting "Start" then a region on the title screen actually gets you there (does `viewscreen_titlest` stay on the stack and just change `mode`, or does an intermediate viewscreen class appear for "new game vs. continue" within a region?). No installed script drives or documents this hop. This is called out again in §8 as the top unresolved item.

---

## 4. Keybindings

### 4.1 `data/init/interface.txt` has no embark-specific binds

```
$ grep -inE 'EMBARK|CHOOSE_START|SETUPDWARF|SITE_FIND|SETUP_INIT|D_INIT|PLAY_NOW|NEW_ARENA|NEW_FORT|CREATE_WORLD|WORLDGEN' data/init/interface.txt
(no output)
```

Zero matches. The file (963-line `interface_key` enum backs it, see below) binds generic UI keys only. Relevant confirmed bindings actually present, read from the top of the file:

| Bind | Key(s) |
|---|---|
| `SELECT` | Enter / Numpad Enter |
| `SEC_SELECT` | Shift+Enter / Shift+Numpad Enter |
| `DESELECT` | z |
| `LEAVESCREEN` | Esc |
| `OPTIONS` | Esc |
| `CHANGETAB` / `SEC_CHANGETAB` | Tab / Shift+Tab |
| `STANDARDSCROLL_UP/DOWN/LEFT/RIGHT` | numpad 8/2/4/6 and arrow keys |
| `ZOOM_IN` / `ZOOM_OUT` | `[` / `]`, plus mousewheel |
| `FILTER` | Shift+f |

These are the same generic keys every DF list screen uses; there is no reason to expect the title menu or the embark screens deviate from them, but this is inference, not a direct observation of those specific screens.

### 4.2 The full `interface_key` enum was dumped (read-only, 963 entries)

Because no interface.txt binds named anything embark-specific, the next question was whether the *enum itself* (which interface.txt binds map onto, and which is also what `gui.simulateInput` and `df.interface_key[...]` consume directly, bind or no bind) has relevant unbound entries. This required only enumerating a global type's registered names — no key was sent, no screen touched:

```
$ dfhack-run lua "local f=io.open('/tmp/interface_keys.txt','w')
   for i=0,6000 do local nm=df.interface_key[i]; if nm then f:write(i..' '..nm..'\n') end end
   f:close(); print('done')"
```

963 names came back (indices run non-contiguously up to 962, `KEYBINDING_COMPLETE` being the last). Grepping it for the flow found:

- **`CURSOR_UP/DOWN/LEFT/RIGHT`** and diagonal/fast variants (indices 29–44), plus a parallel **`KEYBOARD_CURSOR_*`** family (indices 51–70) — these are the generic map-cursor-movement keys, confirmed to exist as a documented pair with `dfhack.screen.paintMapPortTile`'s doc text: "the interface texpos layer of a map port (e.g., the world map or the zoomed-in map for embark selection)" (`Lua API.txt:2599`) — i.e. DF itself has a "map port" concept that explicitly includes the embark-selection map, and the `CURSOR_*` keys are the generic way to move a cursor across any map port. **Not independently confirmed that `choose_start_sitest` actually listens to these specific key names** — inferred from the map-port doc language plus the absence of any more specific candidate.
- **`EMBARKKEY_START`** (index 485) — the only interface_key with "EMBARK" in its name anywhere in the enum. `grep -rn 'EMBARKKEY_START' hack/` returns **zero** matches in any installed DFHack script. Nobody has needed to simulate it, which makes sense — scripts like `embark-skills.lua` and `points.lua` assume a human is about to press whatever the "confirm and go" key is; they only tweak state ahead of that keypress. This is the strongest *candidate* for the final "commit to the embark you configured" key on `viewscreen_setupdwarfgamest`, purely by its name — genuinely untested, flagged in §9 as the single highest-value thing for a follow-up script to verify live.
- No `SETUP_*`, `CHOOSE_*`, `NEW_GAME*`, or `PLAY_*` (besides irrelevant `PLAY_MACRO`) names exist at all — reinforcing that these screens are not driven by screen-specific named keys the way, say, the trade screen is (`internal/confirm/specs.lua` intercepts `LEAVESCREEN` and `_MOUSE_R` on `dwarfmode/Trade/Default` by name).

### 4.3 Site selection is mouse-driven, not keyboard-driven, in the reference implementation

`gui/embark-anywhere.lua` (read in full) is the clearest evidence available for what the actual site-selection screen listens to. Its `onInput` handler:

```lua
function EmbarkAnywhereScreen:onInput(keys)
    local scr = dfhack.gui.getDFViewscreen(true)
    if keys.LEAVESCREEN and not scr.zoomed_in then
        self.defocused = false
    elseif keys._MOUSE_L and scr.choosing_embark and
        not self.subviews.main:getMouseFramePos() and
        not self:clicked_on_panel_mask()
    then
        force_embark(scr)
    end
    return EmbarkAnywhereScreen.super.onInput(self, keys)
end
```

and its actual site-acceptance logic does not simulate a click at all — it writes the screen's own fields directly:

```lua
local function force_embark(scr)
    scr.warn_mm_startx = scr.neighbor_hover_mm_sx
    scr.warn_mm_endx = scr.neighbor_hover_mm_ex
    scr.warn_mm_starty = scr.neighbor_hover_mm_sy
    scr.warn_mm_endy = scr.neighbor_hover_mm_ey
    -- setting any warn_flag will cause the accept embark panel to be shown
    -- clicking accept on that panel will accept the embark, regardless of
    -- how inappropriate it is
    scr.warn_flags.GENERIC = true
end
```

This is confirmed, working, shipped code, not a proposal — and it demonstrates that `viewscreen_choose_start_sitest` can be driven entirely through direct struct-field writes for the spatial-selection part, with `simulateInput` reserved only for the generic confirm/cancel keys layered on top. This sidesteps needing mouse pixel coordinates, screen rendering, or `df.global.gps.mouse_x/y` math altogether for the one step that is inherently "spatial" — which matters a great deal given commitment #1.

Corroborating evidence that the *vanilla* (non-DFHack) path is mouse-first: `news.rst:2590` — `prospect: can now give you an estimate of resources from the embark screen. hover the mouse over a potential embark area and run prospect` — confirms the stock UX for evaluating a site is mouse hover, not keyboard.

**One hypothesis ruled out during this pass**: `hack/scripts/toggle-kbd-cursor.lua` looked promising by name (a DFHack-provided keyboard-cursor toggle) but on reading it in full, it only toggles `df.global.d_init.feature.flags.KEYBOARD_CURSOR` for the **fortress-mode/adventure-mode map designation cursor** (via `gui.dwarfmode`'s `guidm.setCursorPos`/`clearCursorPos`), and separately handles adventure-mode "look" via a totally different branch. It has no code path touching `choose_start_sitest`. Initially considered as a way to make site selection keyboard-drivable; it is not that, and is not part of the embark flow at all.

---

## 5. Confirmed struct fields, by viewscreen

All of the following are field or method names read directly out of real, working scripts — not invented, not guessed from DF-wiki-style community knowledge (none was consulted for field names).

**`viewscreen_choose_start_sitest`**
| Field | Source | Notes |
|---|---|---|
| `choosing_embark`, `choosing_reclaim` | `deep-embark.lua` | booleans distinguishing a fresh embark from a reclaim |
| `zoomed_in` | `gui/embark-anywhere.lua` | whether the screen is on the zoomed local-map view vs. the world/region view |
| `warn_flags.GENERIC` (and other `warn_flags`) | `gui/embark-anywhere.lua` | setting any warn flag surfaces the "accept anyway" panel |
| `warn_mm_startx/endx/starty/endy` | `gui/embark-anywhere.lua` | the accepted embark rectangle, in whatever coordinate space `neighbor_hover_mm_*` uses |
| `neighbor_hover_mm_sx/ex/sy/ey` | `gui/embark-anywhere.lua` | the currently-hovered candidate rectangle |
| `start_civ`, `start_civ_nem_num`, `start_civ_entpop_num`, `start_civ_site_num` | `embark-anyone.lua` | parallel vectors describing the list of origin civs offered |
| `find_results`, nested type `T_find_results` (with a `.None` member) | `internal/confirm/specs.lua` (`embark-site-finder` confirm spec, `context='choose_start_site/SiteFinder'`) | state of the built-in automated site finder |

**`viewscreen_setupdwarfgamest`**
| Field | Source | Notes |
|---|---|---|
| `points_remaining` | `points.lua` | embark points left to spend; script writes it directly: `scr.points_remaining = tonumber(...)` |
| `dwarf_info` (indexable, element type `startup_charactersheetst`) | `embark-skills.lua` | per-dwarf character sheets |
| `selected_u`, `s_unit` | `embark-skills.lua`, `startdwarf.lua`'s bundled overlay | current selection index and unit list, on the "Dwarves" tab |
| `skill_picks_left` | `embark-skills.lua` | per-dwarf, `dwf.skill_picks_left` |
| `skilllevel[...]` | `embark-skills.lua` | per-dwarf skill table, settable to any `df.skill_rating` |

Confirmed via `dfhack.gui.matchFocusString('setupdwarfgame/Dwarves', scr)` (`embark-skills.lua`) that the focus-string convention for this screen's tab is `setupdwarfgame/Dwarves` — directly usable with `dfhack.gui.matchFocusString` to confirm not just "which viewscreen" but "which tab of it."

**Direct globals, bypassing any screen entirely** (highest-confidence path for embark-prep values, since it needs no `simulateInput` at all once the right screen is merely *present*):
- `df.global.start_dwarf_count` — set directly by `startdwarf.lua`: `df.global.start_dwarf_count = num`. Script's own help text: works "before reaching the embark prep screen" per this repo's existing memory note, consistent with what's read here.
- `df.global.world.worldgen.worldgen_parms.embark_points` — set by `points.lua`, guarded by `dfhack.isWorldLoaded()`.
- `df.global.plotinfo.fortress_age` — read (not written) by `on-new-fortress.lua`; the success signal, see §7.

**`viewscreen_adopt_regionst`** — no script in the installed tree accesses its fields directly (it is treated purely as a marker class to wait through). One weak corroborating data point: `hack/docs/docs/about/History.txt:1512` notes a past rename — `"viewscreen_loadgamest": renamed "cur_step" enumeration to match style of "viewscreen_adopt_regionst" and "viewscreen_savegamest"` — implying it has (or had, as of that changelog entry) a `cur_step` stage-enum field, plausibly `adopt_region_stage_type` (which does appear as a real enum name elsewhere in `news.rst`'s "added NONE entries to many enum types" list). **Low confidence** — this is a changelog entry about a past API change, not a field observed in current use, and not independently verified against the live 53.16 build.

---

## 6. Polling primitives (for a script's own control flow)

All three confirmed directly from `Lua API.txt`, quoted:

- **`dfhack.gui.matchFocusString(focus_string[, viewscreen])`** (`Lua API.txt:1099`) — "Returns true if the given focus_string is found in the current focus strings, or as a prefix to any of the focus strings... Matching is case insensitive." Used by real scripts with values `'choose_start_site'` (`gui/embark-anywhere.lua`) and `'setupdwarfgame/Dwarves'` (`embark-skills.lua`) and `'choose_start_site/SiteFinder'` (`internal/confirm/specs.lua`) — confirming the focus-string naming convention is lowercase-with-slashes and screen-specific.
- **`dfhack.gui.getViewscreenByType(type[, depth])`** (`Lua API.txt:1108`) — "Returns the topmost viewscreen out of the top depth viewscreens with the specified type (e.g., df.viewscreen_titlest), or nil if none match." A direct, one-line way to poll "have we reached `viewscreen_setupdwarfgamest` yet" without wiring an event hook.
- **`dfhack.gui.getDFViewscreen([skip_dismissed[, viewscreen]])`** (`Lua API.txt:1111`) — "Returns the topmost viewscreen not owned by DFHack." Used throughout the reference scripts (`embark-anyone.lua`, `points.lua`, `embark-anywhere.lua`) in preference to `getCurViewscreen()` specifically to skip DFHack's own overlay screens when checking "what is the *game's* current screen."

For event-driven (rather than polled) control flow, `deep-embark.lua` is a complete, working reference implementation of exactly this kind of state machine — see §7.

---

## 7. Verifying success without rendering

**The primary signal**, taken verbatim from a real installed tool (`on-new-fortress.lua`, full source):

```lua
if not (dfhack.world.isFortressMode() and df.global.plotinfo.fortress_age == 0) then return end
```

and its doc text (`hack/docs/docs/tools/on-new-fortress.txt`):

> This utility command checks to see if the current fortress has just been created (that is, the "age" of the fortress is 0, which is only true on the first tick after the initial embark).

This is about as strong as evidence gets in this codebase: it's the exact condition a shipped tool uses for "did a fort just start," worded by the DFHack maintainers themselves.

**Supporting/earlier-stage signals**, each confirmed independently this session:
- `dfhack.isWorldLoaded()` — false right now; should flip true once a region is loaded (before site selection even begins).
- `dfhack.isMapLoaded()` — false right now; should flip true once the embark map is loaded.
- `df.global.gametype` (enum `game_type`) — currently `NONE`; `deep-embark.lua` treats `df.game_type.DWARF_MAIN` as the confirmed value once embarking as a fort (checked defensively alongside the viewscreen class, since `viewscreen_adopt_regionst` alone is ambiguous between fort/adventure/legends). Other enum members seen in the wild (`gui/load-screen.lua`'s `gametypeMap`): `NONE`, `DWARF_MAIN`, `DWARF_RECLAIM`, `DWARF_UNRETIRE`, `ADVENTURE_MAIN` (plus `DWARF_ARENA`/`ADVENTURE_ARENA`, referenced elsewhere in that same file's `gametypeString`).
- `df.global.gamemode` (enum `game_mode`, a **separate** field from the above) — currently also `NONE`; this is the one `Lua API.txt`'s own canonical persistence-pattern example checks (`df.global.gamemode ~= df.game_mode.DWARF`), so it's the idiomatic one to gate persistent state loading on, per DFHack's own documented convention.

**Event-driven monitoring** — `dfhack.onStateChange` fires these codes (`Lua API.txt:3287`, confirmed exact list): `SC_WORLD_LOADED`, `SC_WORLD_UNLOADED`, `SC_MAP_LOADED`, `SC_MAP_UNLOADED`, `SC_VIEWSCREEN_CHANGED`, `SC_CORE_INITIALIZED`. `deep-embark.lua` is a complete, working reference for driving an embark-adjacent state machine off these:

```lua
dfhack.onStateChange.DeepEmbarkMonitor = function(event)
    if event == SC_VIEWSCREEN_CHANGED then
        local view = dfhack.gui.getCurViewscreen()
        ...
        elseif view._type == df.viewscreen_choose_start_sitest then
            if view.choosing_embark or view.choosing_reclaim then
                deepEmbark(args.depth, args.blockDemons)
                dfhack.onStateChange.DeepEmbarkMonitor = nil
            end
        elseif view._type == df.viewscreen_dwarfmodest then
            dfhack.onStateChange.DeepEmbarkMonitor = nil
        end
    elseif event == SC_WORLD_UNLOADED then
        dfhack.onStateChange.DeepEmbarkMonitor = nil
    end
end
```

This is directly reusable as a skeleton for an embark-driving script's own control flow (swap the payload in each branch for "send the next input" instead of "do the deep-embark teleport").

---

## 8. Known failure modes and traps

- **No `simulateInput`-specific gotcha turned up in `hack/news.rst` / `hack/news-dev.rst`** — grepped both for `simulateinput` and `embark` case-insensitively; the only direct hit was a historical bugfix: *"`gui.simulateInput`: do not generate spurious keycode from `_STRING` key inputs"* (DFHack 50.13-r4 era). The installed version is 53.16-r1.1, well past that fix. This is an absence-of-evidence finding, not a confirmed "there are no gotchas" — flagged as such rather than silently treated as clean.
- **A real, documented timing gotcha exists for state-change events near embark**, from `deep-embark.lua`'s own comment: *"I initially tried using SC_MAP_LOADED, but the map appears to be loaded too early when reclaiming sites"* — i.e. `SC_MAP_LOADED` fired before the state the script needed was actually valid, on at least one embark-adjacent path (reclaiming). `SC_VIEWSCREEN_CHANGED` was used instead in the finished script. Any embark-driving script should default to `SC_VIEWSCREEN_CHANGED` + explicit field checks rather than trusting `SC_MAP_LOADED` timing.
- **`printall()` on the live `viewscreen_titlest` broke the RPC connection** during this session — a `dfhack-run lua "local scr=dfhack.gui.getCurViewscreen(); printall(scr)"` call returned `Could not connect to localhost:5000` where a `pairs()`-based field listing on the same screen worked fine seconds later (and the connection was confirmed alive again immediately after with a trivial `print('ok')`). This was not investigated further — it is not clear whether `printall`'s deep recursion into large/self-referential structures is inherently risky against this screen, or whether it was a one-off. **Practical takeaway for implementation**: prefer shallow, explicit field reads (`scr.some_field`) or `pairs()` over `printall()` when inspecting live viewscreens, and don't assume a `dfhack-run` disconnection means the DF process died — it reconnected cleanly.
- **The `mode` tool's "mode combination" corruption warning** (mentioned in project memory) could not be re-checked this session — `mode` is tagged `unavailable` in this build per `memory/dfhack-environment.md`, and its docs were not located under `hack/docs/docs/tools/` in this pass (not specifically searched for by filename; a targeted `find` for `mode.txt` was not run). Treat the corruption warning as unconfirmed-but-plausibly-inapplicable to a plain single-player embark (which doesn't combine modes), pending an actual look at that doc file.
- **The title→region→fresh-embark transition is entirely unverified** — see §1 and §3. This is not a "trap" so much as the acknowledged hole in this research: nothing in the installed scripts exercises it, so a follow-up script will need to discover it live, one `simulateInput` + `getCurViewscreen()` poll at a time, ideally against a throwaway/snapshotted VM state given the stack's own rule about hard-to-reverse actions.
- **`EMBARKKEY_START` is an inference, not a confirmed final-commit key** — see §4.2. If it's wrong, the likely failure mode is simply "nothing happens" (an unbound/unhandled key), which is a safe failure to test for, rather than a destructive one — but it hasn't been tried.

---

## 9. Ordered candidate steps for a follow-up implementation script

Confidence is flagged per step. **C** = confirmed by primary source (a real script, doc, or this session's live read-only query). **I** = inference from field/key naming or adjacent evidence, needs live testing. Nothing below has been executed.

1. **[C]** Precondition check: `dfhack.gui.getCurViewscreen()._type == df.viewscreen_titlest` and `dfhack.isWorldLoaded() == false`. (Matches the live state confirmed in §2.)
2. **[I]** `gui.simulateInput(titlescreen, 'SELECT')` while `scr.selected == 0` (the `Start` entry in `menu_line_id`, confirmed present at index 0 today) — expected to enter whatever "Start" leads to. **Untested**: does this change `scr.mode` in place, or push a new viewscreen? Poll `dfhack.gui.getCurViewscreen()._type` and `scr.mode` immediately after to find out live.
3. **[I]** Navigate to the existing region in `region_choice` (length 1 today) — plausibly via `STANDARDSCROLL_UP/DOWN` moving `scr.selected_r`, then `SELECT`. Field name for the cursor is inferred from naming only, not confirmed.
4. **[I]** Choose "new fortress in this region" over "continue"/"reclaim" — no confirmed key or field for this distinction was found anywhere in the installed scripts. This is the least-understood step in the whole sequence and is the highest-priority thing to resolve live.
5. **[C, monitoring only]** Once triggered, the screen becomes `viewscreen_adopt_regionst` (loading). Poll with `dfhack.gui.getViewscreenByType(df.viewscreen_choose_start_sitest)` (or hook `SC_VIEWSCREEN_CHANGED`, per `deep-embark.lua`'s pattern) until it clears, double-checking `df.global.gametype == df.game_type.DWARF_MAIN` per `deep-embark.lua`'s own defensive check (this screen is shared with adventure-mode/legends-mode setup).
6. **[C]** On `viewscreen_choose_start_sitest`, with `scr.choosing_embark == true`: pick a site by writing fields directly rather than simulating clicks — `scr.neighbor_hover_mm_sx/ex/sy/ey` then `scr.warn_flags.GENERIC = true` (verbatim pattern from `gui/embark-anywhere.lua`'s `force_embark()`), then `simulateInput(scr, 'SELECT')` to accept the resulting confirm panel. Exact key(s) for that final accept panel are **[I]**, untested — `embark-anywhere.lua` handles it via a widget click, not a raw key, so the equivalent `simulateInput` key/sequence needs live discovery.
7. **[C]** On `viewscreen_setupdwarfgamest`: configure directly via struct/global writes, all confirmed real patterns — `df.global.start_dwarf_count = N` (`startdwarf.lua`), `scr.points_remaining = N` (`points.lua`), per-dwarf `dwf.skill_picks_left` / `dwf.skilllevel[skill]` (`embark-skills.lua`). No `simulateInput` needed for any of this.
8. **[I]** Final "embark now" key on `viewscreen_setupdwarfgamest` — strongest candidate is `df.interface_key.EMBARKKEY_START` (index 485) by name alone; **zero corroborating usage found in any installed script**, so this is a guess worth testing first, not a confirmed value. `SELECT` is the fallback guess if that fails.
9. **[C]** Verify success by polling (not events, for simplicity) `dfhack.world.isFortressMode() and df.global.plotinfo.fortress_age == 0` — verbatim `on-new-fortress.lua`'s own gate. Cross-check with `dfhack.gui.getViewscreenByType(df.viewscreen_dwarfmodest) ~= nil` and `df.global.gamemode == df.game_mode.DWARF`.

**Net assessment**: roughly half of this sequence (screen classes, success check, embark-prep field writes, site-selection field writes) rests on primary-source-confirmed code from this install. The other half — the title-menu-to-region hop and the two specific confirm keys in steps 2, 3, 4, 6, and 8 — is untested inference and is exactly the set of things a live, carefully-polled (and ideally VM-snapshotted first, given the repo's stance on hard-to-reverse actions) test run needs to nail down before this is a real script.
