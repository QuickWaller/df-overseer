# Research: clearing self-pausing popups with nobody watching

Date: 2026-10-01. Researcher, Sonnet, read-only, no live access. Sources:
DFHack GitHub source at tag `53.16-r1` (`DFHack/dfhack`), its `scripts`
submodule (commit `7549711a993e03bef19e90b27427096c1099853e`) and its
`library/xml` submodule, i.e. `DFHack/df-structures` (commit
`1dd01aad64219afa0578f1328cf15bd0c6006d5a`), fetched as tarballs of those
exact commits and grepped locally; the DF wiki's `Announcements.txt` page
(fetched live, `action=raw`). Answers
`handoffs/2026-10-01-unattended-popups-research.md`. No DF process, no VM,
no rendered screen was read to produce this; text-buffer scanning is
mentioned only as something the repo's *existing, already-deployed*
`df-overseer-ui.lua` does at the Lua/game layer, never anything shown to a
model.

## Short answer

There are at least **three structurally different classes** of "the fort
stopped and nobody clicked anything," and they need three different
answers, not one handler:

1. **A native DF "mega" popup (`BOX`/`DO_MEGA`)**: a real box requiring an
   Okay/More click, structurally detectable and safe to auto-dismiss the
   way a player would, because dismissing it changes no game state beyond
   closing the box. **Recommend: automate this one, including inside the
   unattended conductor loop.**
2. **A native DF `PAUSE`-flagged report with no popup at all**: `pause_state`
   flips true, no dialog exists to click, and resuming is the entire fix
   (`scripts/supervised-unpause.sh` already does this correctly). This
   already includes the one *confirmed* live case,
   `FORT_POSITION_SUCCESSION`. **Recommend: keep this supervised-only, per
   the standing rule** (`decisions/DECISIONS.md` 2026-09-28, `Working.md`
   2026-09-28) — resuming here can unpause a real emergency this project's
   own tripwire vocabulary hasn't been taught to recognise yet, and nothing
   in the source read for this report changes that risk calculus.
3. **A genuinely stuck modal viewscreen** (the 2026-09-16 pattern: an
   undismissed dialog, `pause_state` sometimes even reading `false` while
   the game is still frozen). This class is real but, on the primary
   sources read for this report, appears to be rare and mostly tied to
   one-time screens (the founding/welcome dialog) rather than anything that
   recurs during ordinary fortress play. `df-overseer-ui.lua`'s existing
   `type`/`click`/`dump` tools already cover it generically; no new
   mechanism is needed, only using what exists.

The class this project actually hit live (`FORT_POSITION_SUCCESSION`) is
class 2, not class 1 or 3 — confirmed by `handoffs/2026-09-28-noble-
succession-popup-research.md`'s own live resume-and-verify test. That
means the CLAUDE.md status line's framing of it as "a dialog [whose] buffer
scan cannot see that dialog's text" describes an earlier, superseded
diagnosis: the 2026-09-28 research found no dialog was ever present
(`viewscreen_dwarfmodest`, the ordinary play screen, both before and after
the mutation test) — there was nothing there for a buffer scan to find.
This report does not re-litigate that finding, it is carried forward as
settled, but it is worth naming plainly since the still-current status line
text could otherwise be read as still-open.

---

## Q1: Which popups can pause or block an unattended v50 fort?

**A full enumerable list of every popup source was not fully obtainable
without live game data (`data/init/announcements.txt`'s actual PAUSE column
on this install is not in DFHack's own source, see "Not verified" below),
but the *mechanisms* are fully enumerable from source, and there are
exactly three:**

### 1a. `BOX`/`DO_MEGA` — the native mega-popup queue

Confirmed from the DF wiki's `Announcements.txt` page (fetched raw
2026-10-01): the `BOX` (or `DO_MEGA`) announcements.txt option "causes a
box to appear in the middle of the screen, requiring a click on the Okay
button to close it. If multiple boxes are displayed at the same time, the
button says More and displays the next box." `[C-Wiki]`, current.

Confirmed from DFHack source, `library/modules/Gui.cpp:2011-2027`
(`Gui::showPopupAnnouncement`): this is backed by a real, readable
structure. It allocates a `df::popup_message` (df-structures'
`popup_message`, `original-name='mega_announcementst'`,
`df.announcement.xml:72-77`) and does
`world->status.popups.push_back(popup)` — `world.status.popups` is
`df.announcement.xml:182`'s `<stl-vector pointer-type='popup_message'
name='popups' original-name='mega'/>`, a field of `announcement_handlerst`,
which is `df.world.xml:543`'s `world.status`
(`original-name='announcement'`). So the same push this DFHack function
performs is exactly what the vanilla BOX/DO_MEGA path does to trigger the
box; `[C++ source, cross-checked against the struct definition]`, high
confidence that this vector is the mega-popup queue. **Not independently
verified live**: that a real BOX-flagged vanilla event actually populates
this vector on this install (no VM access this pass); inferred from the
DFHack function that shares the exact same code path (`showPopupAnnouncement`
literally exists so DFHack scripts can synthesize the same vanilla popup).

### 1b. `PAUSE`/`P` — a pure `pause_state` flip, no popup

Confirmed from the wiki: `PAUSE`/`P` "pauses the game when the announcement
occurs" — no box, no click required, distinct from `BOX`. `[C-Wiki]`.
`pause_state` itself is `df.game_v.xml:181`'s
`<global-object type-name='bool' name='pause_state' original-name='paused'/>`,
a single global bool — confirmed from source, high confidence.

**This project's live-confirmed case is here, and it does not go through
the announcements.txt PAUSE column at all.** `handoffs/2026-09-28-noble-
succession-popup-research.md`'s Result section already established, live:
`FORT_POSITION_SUCCESSION` set `pause_state` true with
`df-overseer-announcement-levels level FORT_POSITION_SUCCESSION` reading
`not_pause_or_slow` and absent from `pause-ids` — i.e. neither this
project's own curated tripwire table (`scripts/dfhack/df-overseer-
announcement-levels.lua`, built from `research/data/2026-09-23-
announcement-severity.yaml`) nor (by strong implication) the live
install's actual announcements.txt PAUSE column caused it. The resume test
(`clock resume` → tick advanced 690 in ~3s → `clock pause`) proved it was a
clean flip with no dialog. **This report's contribution beyond the
2026-09-28 finding**: DFHack's own `Gui.cpp` (§method above) shows no
`getFocusStrings` handler ever emits a focus string for the mega-popup
case either (`add_main_interface_focus_strings`, `Gui.cpp:343-900`, has
entries for `Designate`, `Announcements` (the side-panel list, not a
popup), `Info`, and squads, but nothing for `popups`/`mega`) — so **neither
viewscreen type nor focus string can distinguish "ordinary play" from "a
mega popup is showing over ordinary play,"** because mega popups render as
an overlay within the *same* `viewscreen_dwarfmodest`, not a separate
screen. This means the 2026-09-28 test's `df-overseer-ui type` check
(`viewscreen_dwarfmodest`) ruled out a *stuck separate viewscreen*, but
would not by itself have ruled out a *mega popup coexisting with* ordinary
dwarfmode — the tick-resume test is what actually proved this, independent
of that screen-type read. Worth recording so a future session doesn't treat
"screen type is dwarfmodest" as proof no mega popup is pending; the
`popups` vector must be read directly for that (see Q2).

**Not verified**: the actual engine trigger for `FORT_POSITION_SUCCESSION`'s
pause. It is not in DFHack's own C++ (which does not implement vanilla game
logic, only exposes/reads it), and df-structures' `df.announcement.xml`
carries no per-type PAUSE flag at all (that table lives in vanilla's own
`data/init/announcements.txt`, game data, not DFHack source — inaccessible
without a live install, per this task's no-VM-access constraint). Most
likely, per the 2026-09-28 research and unchanged by this pass: a small set
of "notable, one-time" vanilla events force-pause outside the configurable
per-type system entirely. Unverified, flagged as such in both reports.

### 1c. Stuck/undismissed modal viewscreens

The 2026-09-16 case (`decisions/DECISIONS.md`, `docs/TRAPS.md`: "A founded
fort's own welcome dialog silently blocks all citizen activity even when
`pause_state` reads `false`") is the one confirmed live instance of this
class. From df-structures, the actual population of distinct
`viewscreen_*` types is small (`df.d_interface.xml`, 22 types total for
the whole non-adventure UI, including `viewscreen_dwarfmodest`,
`viewscreen_titlest`, `viewscreen_choose_start_sitest`,
`viewscreen_dungeon_monsterstatusst`, `viewscreen_loadgamest`/
`savegamest`) — there is no separate `viewscreen_meetingst` or
`viewscreen_popupst` type in this source at all. **This is itself a
finding**: most of what a pre-v50 player would call "a popup dialog"
(noble meetings, petitions, the report list) was folded into the single
`viewscreen_dwarfmodest`'s widget tree in the v50 UI rewrite, not kept as
separate screens. So the *screen-swap* failure mode (1c) is structurally
rare in v50 by construction — mostly confined to one-time screens
(founding/embark, load/save) rather than anything that recurs mid-fort.
`[C-XML structural survey]`, moderate-high confidence for "the type list is
this short"; **not verified**: whether every one of the 22 types can
actually freeze in the 2026-09-16 sense, only the welcome-dialog case has
been observed doing so.

### Bottom line for Q1

No single fixed list of "every popup" exists to hand over, because the
per-type PAUSE/BOX assignment is vanilla game data this pass had no access
to (see Not Verified). What is fully enumerable from source is the
**mechanism** set: exactly three (mega-popup queue, bare pause flip, stuck
viewscreen), and the live-confirmed incident is mechanism 2, not 1 or 3.

---

## Q2: How to detect one from a script, without reading the rendered screen

Three independent, cheap, structural reads, one per mechanism above, none
of them a screen render:

| Signal | Read | Tells you |
|---|---|---|
| Mega-popup pending | `#df.global.world.status.popups > 0` (`df.world.xml:543`, `df.announcement.xml:182`) | Mechanism 1a: a Box/More popup is queued, needs a click |
| Bare engine pause | `df.global.pause_state == true` with this project's own tripwire-latch file empty (per `scripts/dfhack/df-overseer-clock.lua`'s existing latch, already how the 2026-09-28 test distinguished "us" from an untracked pause) | Mechanism 1b: something paused the game outside this project's own tripwire and outside the mega-popup queue |
| Stuck viewscreen | `dfhack.gui.getCurViewscreen()._type` != the expected type for the current phase (already `df-overseer-ui.lua`'s `type` command) | Mechanism 1c |

**Telling "paused by us" from "paused by a popup" from "paused by the
tripwire"**, per the table: read all three signals together, in this
order, since they are not mutually exclusive as bit flags but this project
already has one piece of the puzzle (the tripwire latch) — extend, don't
replace:

1. Tripwire latch present → paused by us, on purpose, not a popup at all.
2. Tripwire latch absent, `popups` count > 0 → mechanism 1a, dismiss it.
3. Tripwire latch absent, `popups` count 0, `pause_state` true, viewscreen
   type ordinary → mechanism 1b, the `FORT_POSITION_SUCCESSION` case.
4. Tripwire latch absent, `popups` count 0, viewscreen type not the
   expected one for this phase → mechanism 1c.

This is a direct, additive extension of the check the 2026-09-28 handoff
already ran by hand (`clock status` + `df-overseer-ui type`) — the only new
piece is reading `#world.status.popups`, which that research did not do
(not needed for the question it was answering, but needed for full
coverage of mechanism 1a, which it never encountered).

**Not verified**: whether `df.global.world.status.popups` is reachable
by that exact Lua path on the live 53.16-r1.1 install (this project's
installed version) without error — reasoned from a clean submodule
join (df-structures cloned at the DFHack tag's own pinned commit, so
version-matched by construction, same method `research/2026-09-23-
announcement-severity.md` used and verified worked), but not read live.
`docs/TRAPS.md`'s own accumulated lessons (wrong field paths that only
surfaced live, e.g. `tile_bitmask.bits[y%16]` not `:get(x,y)`) are reason
enough to flag this as needing a live read before trusting it, not before
trying it.

---

## Q3: How to dismiss one the way a player would

**Mechanism 1a (mega popup): reuse `df-overseer-ui.lua`'s existing
`click_text` exactly as built**, no new mechanism needed. The wiki
confirms dismissal is "a click on the Okay button" (or "More" if more than
one is queued) — ordinary text rendered directly in the character buffer,
which is exactly what `find_text`/`click_text`
(`scripts/dfhack/df-overseer-ui.lua:39-83`) already locates and clicks,
the same technique already live-verified for title-screen and embark-flow
automation. The only gap is that today it is invoked ad hoc with a
caller-supplied string; it needs a thin wrapper that (1) checks
`#world.status.popups > 0` first (Q2's structural signal, not a screen
guess), (2) calls `click_text("Okay")`, retrying `click_text("More")` if
`Okay` isn't found (per the wiki's own stated behavior for multiple
queued boxes), and (3) verifies success by re-reading the vector's length,
not just text disappearance — a stronger, structural verification than
`click_text`'s own text-absence proxy, and cheap since the same read Q2
already does.

This is a real player-legal action (a click on a button the game itself
rendered), not an armok mutation: nothing about `charter rules/No armok
capabilities` is implicated, since it exercises the same input path a
human would use and changes no game state beyond closing the box the
player would otherwise have to close to keep playing at all.

**Mechanism 1b (bare pause, no popup): there is nothing to dismiss.**
`scripts/supervised-unpause.sh` (referenced in `Working.md`'s 2026-09-28
section) already implements the correct action: `clock resume`, wait, and
verify the tick moved. Nothing in DFHack's or df-structures' source
suggests any "dismiss" action exists for this mechanism, because there is
no dialog — the fix is resuming, not clicking.

**Mechanism 1c (stuck viewscreen): `df-overseer-ui.lua`'s `click`/`dump`
tools, generically**, exactly as they already exist; this handoff's
research did not find any DFHack-native alternative (no dedicated
"auto-dismiss" script or plugin exists in either the `dfhack` or `scripts`
repos at this tag — searched both trees for `pause`, `dismiss`, `announce`,
`popup`, `autoclick`; the closest hits, `gui/notify.lua` and
`gui/confirm.lua`, are unrelated: `gui/notify.lua` is a non-blocking
overlay indicator for player-facing notifications, and `gui/confirm.lua`
adds *extra* confirmation prompts before risky actions, the opposite of
what's needed here). **Finding: DFHack has no generic "dismiss whatever
dialog is on screen" tool; this project's own `df-overseer-ui.lua` is
already the closest thing that exists anywhere in this source tree**, not
a gap this project failed to notice.

---

## Q4: Is demoting a type's announcement-settings pause the better fix?

**No, not as the primary fix, for a structural reason found this pass: this
project's own pause behavior already does not run through the live
install's announcements.txt PAUSE column.** `df-overseer-clock.lua`'s fifth
tripwire (per `scripts/dfhack/df-overseer-announcement-levels.lua`'s own
header) pauses on a **curated 25-id table this project built itself**
(`research/data/2026-09-23-announcement-severity.yaml`), read off the
*report stream*, independent of whatever the live install's actual
`prefs/announcements.txt` says. Demoting a type in the game's own
announcement settings would only affect mechanisms this project doesn't
currently rely on for its own tripwire (a native PAUSE flip on some id this
project didn't curate, e.g. the still-unverified engine-level cause of
`FORT_POSITION_SUCCESSION`) — it would not touch this project's own
tripwire table at all, since that table doesn't read the settings file.

So the two levers are genuinely separate:

- **This project's own tripwire table** (already exists, already the
  right place to add/remove ids, already tested against a generator with
  a regression test) governs what *this project* decides is worth pausing
  for.
- **The live install's native announcements.txt** governs what *vanilla DF
  itself* pauses for, independently, and can still fire mechanism 1b for
  an id this project never curated (exactly what appears to have happened
  with `FORT_POSITION_SUCCESSION`, which the project's own table already
  marks `not_pause_or_slow`).

Demoting `FORT_POSITION_SUCCESSION` (or any id) in the live
announcements.txt might stop the *native* pause from recurring for that
specific id — genuinely worth trying, since it is reversible (edit
`prefs/announcements.txt`, a config file, not a game-state mutation) and
directly addresses the one mechanism (1b) that has no dismiss action at
all. **But it cannot be evaluated as "safe to demote" from source alone**:
this pass found no per-type severity data in DFHack's own source (the
`alert_type` enum-attribute `research/2026-09-23-announcement-severity.md`
already read is a UI-grouping label, not a severity judgment, as that
report itself says). The types that should never be demoted are exactly
the ones this project's own 2026-09-23 research already marked `pause`
(the 25-id table) for a named, reasoned consequence
(`CITIZEN_SNATCHED`, `MEGABEAST_ARRIVAL`, etc.) — demoting any of those in
the live file would silence something a human should always see, and nothing
in this pass's source reading changes that report's own judgment on which
25 those are.

**Recommendation**: leave the curated tripwire table as the primary
mechanism (already built, tested, and this project's own to control).
Treat demoting `FORT_POSITION_SUCCESSION`'s native pause as a narrow,
separate, low-risk experiment worth trying specifically *because* mechanism
1b has no automatable dismiss action and stays supervised-only regardless —
demoting it removes the interruption at the source rather than needing a
human to keep manually resuming it. Do not extend this to any id this
project's own severity research already marked `pause`.

---

## Q5: Live test plan, and where a supervised-only answer is honest

All three mechanisms need a *live* read before any of this is trusted,
per this project's own repeated experience that a struct path read
correctly from source still needs a live confirmation
(`docs/TRAPS.md`'s tile_bitmask and `matinfo.decode` lessons, both found
only by testing against the real process). Ordered cheapest/safest first:

1. **Read-only, no risk**: `dfhack-run lua "print(#df.global.world.status.popups)"`
   (or a small wrapper) on VM 103, at any time, paused or not. Confirms the
   field path resolves at all on this exact install before anything else
   is built on it. Zero risk, answers the biggest "not verified" item in
   Q2.
2. **Read-only, over time**: watch that same read across the fort's normal
   unattended windows. If it stays 0 across a long stretch, mechanism 1a
   has simply never fired on Uniboslan yet (consistent with the register:
   no BOX-class event has been observed live), and the dismiss tool (item
   4 below) has nothing to prove itself against yet — worth knowing before
   claiming the feature "works," since untested-because-never-triggered is
   a different state than verified-working.
3. **Reversible, one-shot, matches the 2026-09-28 pattern exactly**: the
   next time `pause_state` is true with no tripwire latch and
   `#world.status.popups == 0` (mechanism 1b), run the same bounded
   resume-then-verify-then-repause test that handoff already ran once,
   supervised, to build a second data point on whether this class always
   behaves the same way. This is not new: it is asking the orchestrator to
   repeat an already-approved, already-safe test the next time the
   opportunity arises, not to automate it.
4. **Supervised functional test of the new mega-popup dismiss tool**: this
   cannot be tested without a real BOX-class event, which has not yet
   occurred on this fort. Two honest options, neither one settled by
   source reading: (a) wait for one to occur naturally and have a human
   watching over VNC the first time the new tool fires, ready to take over
   if the click misses or the vector count doesn't drop; or (b) if DFHack
   exposes `Gui::showPopupAnnouncement`-equivalent to a live `dfhack-run
   lua` call on the actual install (plausible, since it is a public
   `Gui::` module function, but not confirmed reachable from a
   `dfhack-run` command line without a wrapper script — **not verified**
   this pass), synthesize a low-stakes test popup deliberately, supervised,
   to exercise the dismiss path on demand rather than waiting on a natural
   occurrence. Either way: **supervised the first time, every time a new
   popup subtype is seen for the first time** — a generic dismiss-by-text
   click is safe in principle but has zero live track record yet.
5. **Never move to unattended for mechanism 1b.** Restated because it is
   the one place a genuinely honest answer is "this must stay
   supervised-only, not because the mechanism is unclear, but because the
   two things that look identical from the clock's own status
   (`FORT_POSITION_SUCCESSION`-style flip vs. a real tripwire miss) can
   only be told apart today by a human's judgment about whether resuming
   is safe, and nothing found in DFHack's or df-structures' source this
   pass closes that gap.**

---

## Recommended handler design

A single new capability, additive to `df-overseer-ui.lua` (not a new
script — the existing file already owns buffer-scan/click, and this is the
same mechanism, just pointed at a structurally-detected target instead of
a caller-supplied string), plus one read used by the conductor's own cycle:

```
df-overseer-ui popup-status
  -> {mega_pending: N}          -- #world.status.popups, read-only

df-overseer-ui dismiss-popups [--max N]
  -> while mega_pending > 0 and attempts < N:
       click_text("Okay") or click_text("More")
       re-read mega_pending, verify it decreased
     return {ok, dismissed: K, remaining: mega_pending}
```

Generic over popup type by construction, per the repo's own generalisability
rule: it does not branch on *which* announcement type queued the box
(`AMBUSH_SNATCHER`-flavoured mega-text and a narrative-event mega-text are
clicked identically), so the next BOX-flagged type the game ever queues
costs nothing new — the rule this repo already holds tools to
(`CLAUDE.md`, "Tools must be generalisable").

Wiring: the conductor's per-cycle read step (`conductor/cycle.py`, per the
2026-09-23 research's own description of where this class of thing
belongs) calls `popup-status` before triage; if `mega_pending > 0`, calls
`dismiss-popups` immediately, before anything else, since this is a
required interaction with no judgment call in it (equivalent to a player
clicking through a box before they can do anything else at all). **This is
the one part of this design safe to actually place inside the unattended
loop**, unlike mechanism 1b's resume action, because dismissing a mega
popup changes no game state a human would have chosen differently — the
player has to click it too, eventually, to keep playing.

The `pause_state`-with-no-popup case (mechanism 1b) gets no new automation
in this design: it keeps using `scripts/supervised-unpause.sh`,
unchanged, run by a human or a supervised window script, never
`conductor.service`, per the standing rule this report found no reason to
revisit.

---

## Not verified, and why

- **The live install's actual `announcements.txt` PAUSE/BOX column per
  type.** Vanilla game data, not in DFHack source, and this task had no VM
  access. Everything in Q1/Q4 about *which specific types* are PAUSE- or
  BOX-flagged on Uniboslan is therefore inferred from the wiki's mechanism
  description and this project's own prior live observation of exactly one
  id (`FORT_POSITION_SUCCESSION`), not read directly.
- **Whether `df.global.world.status.popups` resolves without error via
  `dfhack-run lua` on the actual 53.16-r1.1 install.** Reasoned from a
  version-matched submodule join (df-structures pinned to the exact commit
  DFHack's own tag references), the same method already trusted by
  `research/2026-09-23-announcement-severity.md`, but this project has hit
  real live-vs-source path mismatches before (`docs/TRAPS.md`) and this
  path has never been read live.
- **The exact engine trigger for `FORT_POSITION_SUCCESSION`'s hard pause.**
  Not in DFHack's own C++ (game logic, not DFHack's to expose), inherited
  as unverified from `handoffs/2026-09-28-noble-succession-popup-
  research.md` and not resolved by this pass either.
- **Whether `Gui::showPopupAnnouncement` (or an equivalent) is reachable
  from a live `dfhack-run lua` call** to synthesize a test popup on demand,
  needed for live-test-plan option 4(b). Only read as C++ source this
  pass; not tried against a running DFHack Lua environment.
- **Whether any BOX-class event has ever actually fired on Uniboslan.**
  The register/`Working.md` record no such incident to date; this may mean
  the mega-popup path (1a) is untested not because it's rare in general,
  but because this specific fort's event history hasn't happened to
  trigger one yet.
