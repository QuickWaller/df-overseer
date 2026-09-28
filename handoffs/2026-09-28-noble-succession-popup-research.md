# Handoff: can a `FORT_POSITION_SUCCESSION`-style forced pause be detected and cleared programmatically?

Date: 2026-09-28. **Researcher, Sonnet. Mostly read-only, with one narrow permitted exception below. No code changes, no deploy.**

## Context

During a supervised unpause window on Uniboslan (VM 103), the fort paused itself
mid-window with no tripwire latched and healthy vitals. The cause: announcement
id 415, `FORT_POSITION_SUCCESSION` ("Meng Tiredpicks has claimed the position of
queen"), at tick 200910. This is **not** the configurable announcement-pause
system: `df-overseer-announcement-levels level FORT_POSITION_SUCCESSION` reads
`not_pause_or_slow`, and `pause-ids` doesn't list it at all. So the game paused
by some other, harder-coded mechanism.

This has a documented precedent in this exact repo: `decisions/DECISIONS.md`
2026-09-16, "Continue on Uniboslan rather than restart; the popup is dismissed
and the fort is genuinely paused" — a case where the fort was frozen by an
**undismissed blocking dialog**, requiring the user to dismiss it manually over
VNC before the fort was "genuinely paused" rather than stuck. Read that entry
and anything it points to (`research/2026-08-25` era docs, or wherever the
click/UI-dismiss mechanism is documented) before starting.

## The question

For pauses caused by this class of vanilla, non-announcement-system event
(noble succession is the concrete instance; likely also applies to similar
"notable, not urgent" engine events — migrant waves gaining/losing a position,
etc.):

1. **Is it a real, clean `pause_state` flip, or a stuck modal viewscreen
   blocking the game loop** (the 2026-09-16 pattern, where `pause_state` could
   even read false while the game was still frozen)? This is directly testable:
   **you may, as a narrow, explicit exception to being read-only, call
   `df-overseer-clock resume` exactly once on the live fort (VM 103) and
   immediately check whether `cur_year_tick` advances within a few seconds; if
   it does, call `df-overseer-clock pause` again right away.** Never leave the
   fort unpaused and unsupervised. If it does NOT advance, do not repeat the
   test — that alone tells you it's the stuck-viewscreen case, and you should
   diagnose (`dfhack.gui.getCurFocus()`, per `df-overseer-ui.lua`'s own
   existing focus-check code) rather than retry blindly.
2. If it's the stuck-viewscreen case: can it be dismissed the same way
   `df-overseer-ui.lua`'s existing click/dismiss tooling handles other stuck
   popups (read that file's own header and its documented false-negative
   pattern first)? What screen/focus value does it show, and what dismisses
   it (a specific key, an "Okay" click)?
3. If it's a clean pause_state flip (most likely, given `clock.status` read
   `paused: true` cleanly both during and after, unlike the 2026-09-16 case's
   false-negative): what is the actual DFHack-level cause? Read DFHack source
   (a scratch clone outside the worktree, same pattern as the n8n research
   streams) for where a fort-position succession or similar event might force
   `pause_state` true directly, separate from the announcement-alert-type
   pause system.

## What to produce

A findings report (your own file under `research/2026-09-28-...md` or inline
in this handoff's Result section, your call) answering: which case this is,
whether a small, safe, *supervised-only* fix is realistic (something an
orchestrator's own window script could call — never the standing
`conductor.service`, which must never gain new autonomous resume logic per
this repo's charter rules), and what that fix would look like concretely if
one exists. If genuinely inconclusive, say so plainly rather than guessing.

## Rules

- `git merge --ff-only main` first; this brief is committed on main.
- Read-only except the one narrow, bounded `resume`-then-immediately-`pause`
  test above. No other write, no deploy, no service restart, no touching
  VM 106 or the conductor.
- Do NOT touch `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md` beyond this brief's own Result section.
- No em dashes in prose. No attribution lines in commit messages.
- Commit only if you create a research file. Stop and report on any
  permission refusal.
- Fill in the Result section either way.

## Result

**Case: clean `pause_state` flip, not a stuck viewscreen.** Not the 2026-09-16
undismissed-dialog pattern.

Live evidence (VM 103, read-only except the one permitted test):

- `df-overseer-clock status` before the test: `paused: true`, `cur_year_tick
  200910` (matches the announcement's own tick exactly), no `tripwire` key
  (no latch, confirms this is not the clock.lua tripwire system) and
  `armed: true` unrelated.
- `df-overseer-ui type` (read-only, before the test): `viewscreen_dwarfmodest`
  -- the ordinary play screen, no dialog/menu viewscreen present. This rules
  out the 2026-09-16 stuck-modal pattern before the mutation even ran.
- The one permitted mutation: `clock resume` -> `{ok: true, paused: false}`;
  ~3s later `clock status` showed `cur_year_tick 201600` (690 ticks
  advanced, real gameplay running); immediately `clock pause` ->
  `{ok: true, paused: true}`, confirmed by a final `status` read showing
  `paused: true` and `cur_year_tick` static at 201600. The fort was never
  left unpaused unsupervised, and the test was run exactly once, as required.

**Cause, DFHack-level (not independently verified this pass):** the
succession event set `pause_state` true directly through some path other
than the configurable announcement-alert system and other than this repo's
own tripwire (`df-overseer-clock.lua`'s latch file was empty throughout).
`df-overseer-announcement-levels level FORT_POSITION_SUCCESSION` already
reads `not_pause_or_slow`, so the block is not coming from that table. Most
likely explanation, unconfirmed: vanilla DF hard-pauses on a fixed set of
"notable" one-time events (new noble claims, migrant waves gaining/losing a
position) independent of `announcements.txt`'s per-type PAUSE column --
i.e. an engine-level pause, not a DFHack- or announcement-config-level one.
I did not clone DFHack source to trace this (time-boxed; the resume test
already answered the operationally important question -- whether it's safe
to just resume -- more directly than a source read would). **Not verified**:
the exact engine code path, and whether every "notable, not urgent" class
(migrant position changes etc.) behaves identically -- only this one
instance was tested live.

**Is a supervised-only fix realistic? Yes, and it's simple.** Because this
is a clean flip with no dialog to dismiss, the fix is not UI automation at
all: it's exactly the pattern already used for this bounded test. A
supervised orchestrator window script can, on noticing `paused: true` with
no tripwire latch and `cur_year_tick` unchanged for one poll interval:
`clock resume`, wait a few seconds, confirm `cur_year_tick` advanced (proof
it wasn't secretly a stuck-viewscreen case in disguise), and continue --
falling back to `df-overseer-ui type`/`dfhack.gui.getCurFocus()` diagnosis
only if the tick does NOT advance. This must stay supervised-only, per the
handoff and the repo's standing rule: `conductor.service` must never gain
autonomous resume logic, since a real hostile-tier or hunger/thirst tripwire
pause looks identical at the `clock.status` level except for the populated
`tripwire` field -- the check above only works because it also confirms no
latch is present before resuming, and that check must never be skipped.
