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

## 3. Real conductor cycle

Not run yet; the user paused the session after the popup test.
