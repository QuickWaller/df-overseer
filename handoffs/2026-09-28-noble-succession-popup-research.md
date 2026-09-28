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

(pending)
