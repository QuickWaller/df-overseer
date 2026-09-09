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

## The reusable tool

`scripts/dfhack/df-overseer-ui.lua`, deployed onto the guest with
`python scripts/install_df.py ui-install`, then callable directly:

```
./dfhack-run df-overseer-ui type          # print the current real viewscreen type
./dfhack-run df-overseer-ui click "TEXT"  # buffer-scan for TEXT, click its center, retry, verify
./dfhack-run df-overseer-ui dump          # print every non-blank row of the character buffer
```

Re-run `ui-install` any time the script changes — it's a plain overwrite,
idempotent, no state to preserve.

**What `click` actually does**, so its limits are clear: scans the full
character buffer for an exact text match (never a pixel/image guess — the
`gui/kitchen-info.lua` label-locator idiom, confirmed live 2026-09-09), sets
`df.global.gps.mouse_x/mouse_y` to the match's center, fires
`gui.simulateInput(scr, '_MOUSE_L')`, then re-scans for the same text as a
success proxy (its disappearance suggests something changed). Retries up to
3 times, because these clicks are genuinely flaky for reasons not yet fully
understood (see "Known unresolved problem" below).

**What it cannot do yet**: click anything that doesn't render as scannable
character-buffer text — the actual map viewport (world overview, embark
site-selection map) renders via a texture-blit path invisible to
`dfhack.screen.readTile` (confirmed 2026-09-09, the same finding that
required real screenshots rather than buffer stats to verify Steam graphics
were rendering). Clicking a map location today still means guessing a pixel
position from a screenshot and converting to grid coordinates by hand — see
the queued task in `Working.md` for the specific case (the final embark
placement click) this blocks.

## Known unresolved problem: off-center clicks don't register

Confirmed 2026-09-10: every click attempt near horizontal/vertical
screen-center succeeded (with retries) — title screen buttons, the mode
picker, Site Finder's own panel controls. Every off-center click attempt
failed outright, even after many retries and several different techniques —
the embark screen's own "Embark" button (bottom-right) and direct clicks on
the map itself (large, mostly off-center). Not yet root-caused. The leading
untested-to-completion lead: `df.global.gps.precise_mouse_x/y`, a **second**
mouse-position field distinct from `gps.mouse_x/y`, found sitting at a fixed
`(640, 360)` — the exact center of a 1280×720 frame — all night regardless
of `gps.mouse_x/y` writes succeeding. Setting both together did not fix it
either, so either the coordinate-space conversion tried was wrong, or this
isn't the actual mechanism. Full detail and concrete next steps to try are
in `Working.md`'s queued task — read that before spending more time here,
so failed approaches aren't repeated.

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
| `find_mm_sx/sy/ex/ey` | the ONE current best-fit Site Finder match, in embark-tile coordinates (`mm` = min/max, confirmed via DFHack's own `df-structures` naming convention — `research/2026-09-10-site-finder-internals.md`) |
| `find_cur_best_value` | that match's internal score |
| `neighbor_hover_mm_sx/sy/ex/ey` | the currently-hovered rectangle (the light-blue square on screen) — **confirmed a render-derived output, not a settable input**: writing it directly does not move anything on screen |
| `warn_mm_startx/endx/starty/endy` | the rectangle being committed as the embark choice; `-1,-1,-1,-1` means nothing committed yet |
| `warn_flags.GENERIC` | setting `true` (alongside `warn_mm_*`) is `gui/embark-anywhere.lua`'s `force_embark()` idiom — flips the UI into "Click 'Embark' to place your fortress," confirmed working for that much, but the final Embark click itself is the open problem above |
| `find_param[2]` | Savagery criterion; `0` = Calm (the value used this session) — set directly, not via a `+`/`-` button click, which is more robust per 2026-09-09's finding |

Sequence confirmed live, in order: land on this screen zoomed out
(`zoomed_in = false`) → click `"Find embark location"` to open the Site
Finder criteria panel → set the desired `find_param[...]` fields directly →
click `"Begin"` → `"Match found!"` appears with `find_mm_*` populated →
commit via `warn_mm_*` + `warn_flags.GENERIC = true` → the screen needs
`zoomed_in = true` for the local map/Embark-button sub-mode to actually show
(writing this flag directly did work, unlike `neighbor_hover_mm_*`) → click
`"Embark"` (**the still-open problem**).

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

## Sources

`decisions/DECISIONS.md` 2026-09-09 and 2026-09-10 rows carry the full
evidence trail (exact test sequences, screenshots referenced, what was
tried and ruled out) behind every claim above. `Working.md`'s handover has
the concrete queued task for the one open problem. `research/2026-09-08-
embark-automation.md` and `research/2026-09-10-site-finder-internals.md`
are the primary-source research this was built on. This file is the
living summary; when a claim here and a decisions-register row disagree,
the decisions register is the more detailed, dated source of truth — fix
this file to match it, not the other way around.
