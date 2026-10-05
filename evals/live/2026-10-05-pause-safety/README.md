# 2026-10-05: pause safety, supervised live checks

The pause watchdog, the stuck-job watch and the safe-to-resume verdict were
deployed at `d76581a` (all seven targets drift-clean). This run checks them on
the live fort with the user watching VNC. Uniboslan stayed paused throughout.

## 1. Popup test (pass)

Goal: prove that `pause.dismiss` closes a real mega popup on screen, not just
in the game's own count, and that neither tool resumes the game.

Steps, run with `dfhack-run` on VM 103:

1. Raised a harmless test popup through DFHack's own popup call
   (`dfhack.gui.showPopupAnnouncement`, text "Overseer test popup. Nothing
   has happened, this is a test."). `world.status.popups` went to 1. **The user
   saw it on VNC.**
2. `df-overseer-pause why`: `cause: popup`, one `mega` popup pending with the
   exact text, `paused: true`, `cur_year_tick` 250046.
3. `df-overseer-pause dismiss`: strategy `click_text`, clicked "Okay", mega
   popups 1 to 0, `remaining: 0`, popup text recorded in `dismissed[].said`.
4. `df-overseer-pause why` again: `cause: plain_pause`, `popups_pending: 0`,
   `paused: true`, tick still 250046.
5. **The user confirmed on VNC: popup gone, game still paused.**

Findings:

- The tool's read and the screen agree, in both directions.
- Dismissing does not resume the game (the tick did not move).
- New DFHack scripts run by name were picked up without a game restart; the
  deploy tool's "new .lua needs a restart" note is wrong for this case.
- Not covered: a real game-raised mega popup (noble succession and the like)
  rather than one raised through DFHack; the dismissal path is the same
  `world.status.popups` queue and the same on-screen button.

## 2. Dry-run conductor cycle (pass, with a finding)

`/tmp/cycle.sh --dry-run` on VM 106 (transient unit mirroring
`conductor.service`; the service itself still disabled and inactive). Exit 0
in about 2 s. Plan: `would_read` all four roles, `would_wake` none,
`pause_watch` verdict `wait` ("a plain pause inside the grace period; a human
may have paused it"), cause `plain_pause`, `waiting_on_human: true`, no
actions, no alerts.

Finding: the watchdog does what it was built to do, and that means **a fort
we pause on purpose blocks every ordinary cycle**. The pause path returns
early, so no role wakes and the stuck-job poll never runs. A dry run never
writes the watchdog's state, so it always reads as a first sighting. A real
cycle run more than 600 s after the first one would wake the Overseer with
`unexplained_pause`, and a `resume: true` verdict would have the conductor
resume the fort. There is no "paused on purpose, carry on planning" hold for
the operator.

## 3. Real conductor cycles on a running fort

The user chose a running fort over a paused one for the real cycles (an
operator hold was also built for maintenance, `handoffs/2026-10-05-operator-hold.md`,
merged, not deployed). `scripts/supervised-unpause.sh 10 900 30` on VM 103:
10 FPS, tripwire armed, 900 s, tick 250046 to about 258990 (about 7.5 game
days). 22 alive and 0 warnings throughout, hunger and thirst fine, tripwire
never fired, re-paused and 100 FPS restored by the script's trap.

**Cycle 1** (05:23 UTC, 8 min, about $0.06): pause watchdog `idle` ("not
paused"), clock `slowed`. Woke the Quartermaster (`stalled_order`: manager
orders 0, 1, 2 validated but not dispatched). It filed proposal-0012 (brew at
the Still). The stuck-job watch's first poll recorded 5 workerless jobs:
the Bed and Wall constructions and three digs at Activity Zone #5.

**Cycle 2** (05:31 UTC, about 20 min, about $0.21; day total $0.27): woke the
Architect and Quartermaster (`prediction_graded`) and the Overseer
(`queue_pending`). The three digs had cleared during the window (dug); the Bed
and Wall passed the 2400-tick threshold and were notified (`last_notified`
12756017), so `stuck_job` fired for the first time live, but the wake was
shown under `prediction_graded` and the Quartermaster's proposal was about
drink, not the Bed. Records: proposal-0013 (Architect, five more bedrooms),
proposal-0014 (Quartermaster, brew, drink at 4 units for 22, matching the
user's "4 drinks made" on VNC). Overseer accepted 0013 and 0014, rejected
0012 as a duplicate, queued two brew jobs (2903, 2904, concrete barrels after
a dry run refused a wildcard reagent) and dug two bedroom shells (site-5,
site-6) with `blueprint.apply`.

Findings:

- **No project, again.** The Overseer accepted and executed without
  `queue.project`. The live queue has never held a project record, so the
  Board shows no job graph (the user spotted this). The charter rule
  (2026-10-02) did not change behaviour. Fix dispatched: the server refuses
  `queue.executed` without a project
  (`handoffs/2026-10-05-project-before-executed.md`).
- `stuck_job` fired but did not lead to action on the Bed (no bed item, no
  order to make one). Unknown whether the Quartermaster saw it as a reason;
  the wake shown was another signal.
- Pause safety stayed out of the way on a running fort, as designed. The
  Overseer's `pause.verdict` remains unexercised live.

## The Overseer's thinking (run-0004)

`runs-public.json` holds the four runs' public reports and captured thinking,
exactly as the site published them. Thinking is capped at 12000 chars (start
and end kept, middle cut, `conductor/runner.py` `THINKING_MAX_CHARS`), and the
full transcript in `/var/lib/conductor/thinking` is deleted after each run,
so the middle of this run's reasoning is gone. What survives explains the
missing project directly: "Since I didn't create a project for the bedroom
ruling, I'll just record a plain executed entry", and "I could create a
project. But honestly, I've already done the dig work". It read
`queue.project` as optional for multi-step work and unneeded for a simple
one. It did see the stuck-job digest (the suspended Bed and Wall) and noted
them for its next wake rather than acting. Most of its 11 minutes went on
re-deriving the same facts several times and siting bedrooms itself
(six previews, two applies), which it then judged was "overreaching".
