# Handoff: pause safety for unattended running (design, then build)

Date: 2026-10-05. **Executor, Sonnet, worktree. Offline build; read-only on
hosts; no unpause, no deploys.**

## Why

The goal is a conductor that runs the fort unattended. The fort can stop
itself in ways nobody is watching for: a vanilla event that self-pauses
(noble succession, 2026-09-28; `Working.md` "A fort can self-pause on a
vanilla event", `handoffs/2026-09-28-noble-succession-popup-research.md`,
`docs/TRAPS.md`), a stuck viewscreen or popup that needs a click
(2026-09-16), and a wedged command pipe that took a watchdog's own pause call
with it (`docs/AGENT-LOOP.md` around line 114).
`scripts/supervised-unpause.sh` handles one case by hand today. Read the
register first (2026-10-01 row superseding "must never move into
conductor.service", and the 2026-09-21 no-armok rows): dismissing a popup a
player could dismiss is fine; anything a player cannot do is not.

## Tasks, in order (commit after each)

1. **Inventory and design, written here before building.** Every way the
   fort can end up paused or stuck without the tripwire knowing, from the
   docs above and DFHack's own facilities (e.g. its popup or announcement
   handling, `pause_state` reads), each with: how to detect it, whether it
   is safe to clear automatically (a player could do the same), and what to
   do when it is not (stay paused, wake the Overseer, alert the human). A
   **pause watchdog** in the conductor: if the fort is paused and no
   tripwire or escalation explains it, act per the table; never unpause over
   a tripwire or an Overseer escalation. Say where each piece lives (a
   DFHack script on VM 103, a conductor check on VM 106) and what the
   conductor already does (`conductor/cycle.py` clock handling).
2. **Build** the pieces the design marks safe: a DFHack-side read that
   reports why the game is paused (popup, viewscreen, announcement, plain
   pause), a generic dismiss for popups a player can dismiss (data-driven:
   which popups are safe is a list, not branches), and the conductor
   watchdog with its decision table. Tests offline (Lua logic tests where
   the repo already has the pattern, conductor tests with fakes).
3. **Deploy plan for the orchestrator**: targets, the order, and a
   supervised live test plan (how to provoke or wait for each case safely).

## Rules

- First step: `git merge --ff-only main`. Commit your plan early.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`.
- Touched surfaces: `scripts/dfhack/` (new or extended pause/popup script,
  its TOOLS.yaml entry only if it becomes an MCP tool), `conductor/`
  (watchdog; **not** `conductor/runner.py`'s thinking code), `dfmcp/` only to
  register a new conductor-only read tool if needed (not `dfmcp/gotchas_store.py`),
  `agents/conductor/tools.yaml`, `docs/TRAPS.md`, tests. **Not** `web/stream/`,
  `dfqueue/feed.py`, `dfqueue/live.py`.
- Tools must be generalisable; no armok powers.
- Use `DF_ENV_FILE=c:/website-projects/df-automation/.env` for
  `scripts/vm-ssh.sh` (read-only); read `.env` by key only. Public repo: no
  hostnames, IPs or tokens. No em dashes. No attribution lines in commits.
- Full ambient suite and `dfmcp/tests` (in `.venv-dfmcp`) green.

## Done when

The design table, the built pieces with tests, the deploy and live-test
plan, and a Result section here.

## Design (written before building, 2026-10-05)

### Findings that shape the design (read-only live probes on VM 103, 2026-10-05)

- `FORT_POSITION_SUCCESSION` carries the game's own **`DO_MEGA`** flag
  (`df.global.d_init.announcements.flags[type].DO_MEGA`; the flag names are
  `DO_MEGA`, `PAUSE`, `RECENTER`, `A_DISPLAY`, `D_DISPLAY`, `ALERT` and the
  combat-report flags). 35 announcement types are DO_MEGA on this install
  (succession, first caravan, monarch and mountainhome arrivals, megabeast
  and werebeast arrival, night attack, undead attack, the crime-witness
  types, endgame events, deity curse, emergency tactical control, artifact
  and deep-metal finds, and more). **Zero** types carry the `PAUSE` flag. So
  a game-forced pause on this install is a **mega popup**, not a bare
  `pause_state` flip. The 2026-09-28 "clean flip" reading is therefore
  doubtful: that resume test ran after the user had already clicked the box
  away on VNC (the handoff itself says so), which is exactly when
  `world.status.popups` is empty again and `resume` works. Not proven either
  way; the live test plan below provokes a real one.
- Mega popups live in `df.global.world.status.popups` (`popup_message`:
  `text`, `color`, `bright`, `portrait_hfid`), plus `world.status.mega_text`.
  The popup carries no announcement type, so the type comes from the newest
  report(s) of a DO_MEGA type at the current tick. The popup renders inside
  `viewscreen_dwarfmodest` (focus `dwarfmode/Default`), so neither the
  viewscreen type nor the focus string can see it; the vector must be read.
- Live state at probe time: `popups` empty, `help.open` false, paused, focus
  `dwarfmode/Default`.
- DFHack's `hide-tutorials.lua` closes the embark help box by clicking its
  button at a known position; the repo's `df-overseer-ui.lua` clicks by
  scanning the character buffer for a text. Both are player-equivalent.

### Inventory: every way the fort is paused or stuck, and the answer

Two separate questions per case. **Dismiss** (D): closing a box is
player-equivalent, changes no game state, and the text and announcement type
are recorded first, so it is always allowed. **Resume** (R): allowed only
when the cause is on the harmless list (data). Nothing here ever overrides a
latch.

| # | Case | Detect | Auto-clear? | Otherwise |
|---|---|---|---|---|
| 1 | Tripwire latch (death, hunger/thirst, reachable hostile, pause-level announcement) | `clock.status.tripwire` present | **No, never.** The existing tripwire branch only (Overseer run; resume only after a clean un-escalated run) | Stays paused, Overseer woken (exists) |
| 2 | Overseer escalated (`queue.escalate`), with or without a latch | Latch stays; an ordinary-cycle escalation pause is recorded in the watchdog state as `owned: escalation` | **No.** The watchdog does nothing while owned | Human alert (log, status) at the liveness limit |
| 3 | Mega popup pending (any DO_MEGA type) | `#world.status.popups > 0` (`pause.why`) | **Dismiss: yes** (D); data list of popup kinds, click the box's own button | Dismiss fails after the listed strategies: alert human, keep paused |
| 4 | Pause after dismissal, cause on the harmless list (succession, first caravan, monarch/holding/market arrivals, artifact or deep-metal finds, world-history notices) | Newest DO_MEGA/PAUSE reports at the current tick, by announcement type name | **Resume once and verify the tick advances** (R), once per pause episode | Tick does not move: stay paused, wake Overseer, alert human, no retry |
| 5 | Pause after dismissal, cause is a threat or unknown type (megabeast/werebeast arrival, night attack, undead attack, crime witness, endgame event, deity curse, emergency tactical control, any type on neither list) | Same read | **No** | Stay paused, wake the Overseer (new wake reason `unexplained_pause`, clock paused); a clean un-escalated run counts as the decision to resume (same convention as the tripwire branch), resume-and-verify once; escalation or a failed verify: alert human |
| 6 | Plain pause, no latch, no popup, no recent mega/pause report (a human on VNC, the supervised script mid-window, anything DFHack issued) | `paused` and nothing explains it | **Not at first**: a human may have done it. After a grace period (data, default 10 real minutes) treat as case 5 | Alert human at the liveness limit |
| 7 | Stuck modal viewscreen (2026-09-16 welcome dialog, load/save screens) | `pause.why.viewscreen_type` is not `viewscreen_dwarfmodest`, or `help.open` | Tutorial help box: dismiss (a kind in the list). Any other screen: **no** | Alert human at once; the Overseer cannot click |
| 8 | Frozen with `pause_state` false (2026-09-16: tick not advancing between cycles though not paused) | Not paused, `abs_tick` identical to the previous cycle's while real time passed more than a minimum (data) | As cases 3 and 7 after a `pause.why` read | Alert human |
| 9 | Wedged command pipe (2026-09-19) | `clock.status` errors or times out | **Nothing to do from here**: the in-game tripwire is the defence; the conductor already raises `CycleError` and retries next cycle | N consecutive failures alert human (data) |
| 10 | Any unresolved non-tripwire pause past the liveness limit | Paused, unowned or held, longer than the limit (data, default 30 real minutes) | n/a | **Alert the human**, repeat each limit ("no pause goes unowned", register 2026-10-01) |

"Alert the human" today means a CRITICAL log line, a `pause_watch` block in
`status.json` and in the cycle's archived summary. Telegram is designed and
not built (register 2026-10-01); the alert sink is one function the Telegram
stream can extend.

### Where each piece lives

| Piece | Where | Notes |
|---|---|---|
| `why` (read): pause cause report | `scripts/dfhack/df-overseer-pause.lua` on VM 103; MCP id `pause.why`, conductor-only | popup count and texts (bounded), viewscreen type, focus, `help.open`, latch, recent DO_MEGA/PAUSE reports with announcement type names, a derived `cause` |
| `dismiss` (mutate): generic popup dismiss | same script; MCP id `pause.dismiss`, added to `dfmcp/roles.py` `SYSTEM_CLASS_TOOL_IDS` (one line, flagged below) so only a `kind: system` role may hold it | a registry of popup KINDS (`mega`, `tutorial_help`), each with a detector and ordered dismiss strategies, all data at the top of the file; a new kind is a table entry. Verifies by re-reading the popup count. Never resumes |
| Decision table (pure function) | `conductor/pause_watch.py` plus `conductor/pause_policy.yaml` (harmless list, grace, liveness, caps as DATA) | no announcement or wake string is branched on in code |
| Watchdog state | `conductor/pause_watch.py` `PauseWatchStore`, one small JSON beside the cursors | atomic write like `cursors.py` |
| Wiring | `conductor/cycle.py`: one call after the tripwire branch and before triage; an `unexplained_pause` wake runs the Overseer through the same path the tripwire uses; the ordinary-cycle escalation pause records `owned: escalation` | does not touch `runner.py` |
| Wake reason | `conductor/policy.yaml`: `unexplained_pause` (clock paused, wakes overseer) | |
| Allowlist | `agents/conductor/tools.yaml`: `pause.why` (read), `pause.dismiss` (write) | |

What the conductor does today (`conductor/cycle.py`): it reads `clock.status`
each cycle; with a latch it quicksaves, wakes the Overseer, and clears and
resumes only after a clean un-escalated run; an ordinary-cycle
`queue.escalate` calls `clock.pause`. It has **no** handling for a paused
fort with no latch (the 2026-09-28 case), a pending popup, or liveness.
`scripts/supervised-unpause.sh` stays as the supervised-window tool; the
watchdog supersedes its "never in conductor.service" rule per register
2026-10-01 and reuses its resume-and-verify discipline.

### Decision order inside the watchdog (first match wins)

1. Not paused: end any episode; run the frozen-but-unpaused check (case 8).
2. Paused with a latch: do nothing (the tripwire branch owns it).
3. Paused and owned by the conductor's own escalation: do nothing except
   the liveness clock.
4. Paused, unowned, no latch: read `pause.why`; while a popup is pending and
   the dismiss cap (data, 5) is not reached, `pause.dismiss`, recording each
   box's text and type.
5. A non-dwarfmode screen, or a failed dismiss: alert human.
6. Recent causes all on the harmless list: resume once, re-read, verify the
   tick advanced; record.
7. A threat or unknown cause, or nothing explains it past the grace period:
   wake the Overseer with `unexplained_pause`, carrying the `why` report.
8. Over the liveness limit: alert human.

## Built (2026-10-05)

| Piece | File | Tests |
|---|---|---|
| `why` and `dismiss` (popup kinds and strategies as data) | `scripts/dfhack/df-overseer-pause.lua`; `TOOLS.yaml` entry (`pause.why` read, `pause.dismiss` mutate) | `tests/test_pause_lua_logic.py` (20, real script on a fake world, `tests/lua_stubs/dfhack_pause_world.lua`) |
| Decision table, executor, state, policy | `conductor/pause_watch.py`, `conductor/pause_policy.yaml` | `conductor/tests/test_pause_watch.py` (42: table, executor over a fake fort, state file, cycle integration) |
| Wiring | `conductor/cycle.py` (watchdog pass after the tripwire branch; `_paused_cycle_result`; ordinary-cycle escalation recorded as owned), `conductor/policy.yaml` (`unexplained_pause` wake reason), `conductor/status.py` (`pause_watch` block) | covered by the cycle tests above |
| Allowlist and system-class id | `agents/conductor/tools.yaml`, `dfmcp/roles.py` `SYSTEM_CLASS_TOOL_IDS` (+`pause.dismiss`) | `dfmcp/tests/test_gotchas_tools.py` baseline (conductor 17 to 19), `tests/test_drift_check.py` made count-agnostic |
| Docs | `docs/TRAPS.md` update under the self-pause section | |

Test results: ambient `python -m pytest` 2656 passed, 3 skipped, 1 failed, the
failure being the documented deliberate race
(`test_concurrent_raw_appends_without_serialization_can_collide`, it ran while
a second pytest was loading the machine; 3 of 3 pass alone straight after).
`dfmcp/tests` in `.venv-dfmcp`: 789 passed. `lupa` was already installed, so
the Lua logic tests ran rather than skipped.

Verification of the verification: mutation checks on `pause_watch.py`. Removing
the tripwire guard in `decide` fails `test_a_latched_tripwire_wins_over_everything...`;
removing the owned-escalation guard fails 5 tests (decide, executor, two cycle
tests, liveness); removing the tick-did-not-move branch fails
`test_a_resume_whose_tick_does_not_move_pauses_again_alerts_and_never_retries`.
(The executor also checks the latch itself, so the tripwire guard is double.)

### Decisions and flags for the orchestrator

- **The 2026-09-28 reading is probably wrong.** `FORT_POSITION_SUCCESSION` is
  `DO_MEGA`; no announcement type on this install has `PAUSE`. The pause was
  most likely a mega popup the user clicked away before the resume test. The
  design handles both readings (a popup is dismissed; a bare flip falls to the
  announcement or plain-pause rows). The supervised test settles it.
- **Dismiss is separated from resume.** Closing a box is player-equivalent and
  always allowed (its text is recorded first); resuming needs a cause on the
  harmless list. A threat popup is closed but the fort stays paused for the
  Overseer.
- **Clean Overseer run on an `unexplained_pause` = the decision to resume**
  (resume-and-verify once), copying the tripwire branch's convention; the
  register says the Overseer "decides (resume, act, or escalate)" but it has no
  `clock.resume` (and must not). Say if you want a different mechanism.
- **A held pause now stops ordinary cycles.** While a pause is owned or held,
  the cycle returns early (no advisors woken over a frozen fort). Before, a
  non-latched escalation pause let the next cycle run advisors against a paused
  fort.
- **One edit to `dfmcp/roles.py`** (one id in `SYSTEM_CLASS_TOOL_IDS`): the
  handoff allowed `dfmcp/` only for a read tool, but a mutating tool for the
  conductor cannot load without it. Also touched `conductor/status.py` and
  `conductor/policy.yaml` (inside `conductor/`), and two tests whose hardcoded
  conductor tool count (17) the new grants change.
- **Not built, said plainly.** Case 9 (N consecutive failed reads alert the
  human) is not implemented: `CycleError` is already logged and retried, and
  the service loop is where a counter would live. Telegram is not built; the
  alert sink is the single `_alert` function. `docs/STATE.md` (generated tool
  counts) was not regenerated: run `scripts/drift_check.py --write-state` after
  the deploy. If `pause.why` is not deployed when the conductor is, the
  watchdog degrades to waiting then a liveness alert and never resumes.
- **Unverified live (honest list):** that clicking the box's Okay button closes
  a real mega popup (the strategy order in `POPUP_KINDS` is a hypothesis);
  the real text of any popup other than the succession one; whether a DO_MEGA
  announcement pauses the game by itself; `popup_message.text` shape and
  `world.status.mega_text` semantics (the script tolerates string or vector).
- Hygiene: my read-only probes copied one scratch file to the fort VM's temp
  directory and ran read-only `dfhack-run lua` expressions; the file was
  removed. No VM state was changed; the fort stayed paused.

## Deploy plan (for the orchestrator; every step needs the user's go-ahead)

Order: VM 103 first (tools exist before anything calls them), VM 106 second.

1. **VM 103, DFHack side.** Ship `scripts/dfhack/df-overseer-pause.lua` to
   `hack/scripts/` the way the other `df-overseer-*.lua` files go (use
   `git -c core.autocrlf=false archive`). The script is a module with no side
   effects on load, so no restart is needed.
2. **VM 103, dfmcp.** Ship `scripts/dfhack/TOOLS.yaml`, `dfmcp/roles.py`,
   `agents/conductor/tools.yaml` and the test files; restart
   `dfmcp-server.service`. Check: conductor tool count 19, every other role's
   count unchanged (overseer 99, architect 53, consultant 29, quartermaster
   25), and `pause.dismiss` refused to the Overseer's token.
3. **VM 106, conductor files.** `conductor/cycle.py`, `pause_watch.py`,
   `pause_policy.yaml`, `policy.yaml`, `status.py`. The service stays disabled;
   nothing runs until a hand `--once`. Confirm no `CONDUCTOR_*` override
   changes the cursor path (the watchdog state sits beside it as
   `pause_watch.json`).

## Supervised live test plan (fort paused unless a step says otherwise)

Rollback for all of it: delete the Lua file, revert the dfmcp files, restart
dfmcp. Stay paused and at the recorded fps between steps.

1. **Read only.** `dfhack-run df-overseer-pause why` on the paused fort:
   expect `paused: true`, `popups_pending: 0`, `cause` `plain_pause` (or
   `announcement` if a flagged report is within 1200 ticks). Then the same over
   MCP as `pause.why` with the conductor token.
2. **Provoke a plain mega popup, fort paused.** Push one the way the game's own
   BOX path does: `dfhack-run lua "dfhack.gui.showPopupAnnouncement('pause-safety test', COLOR_WHITE)"`.
   `why` should say `cause: popup`, `popups_pending: 1`, the text. Ask the user
   to watch VNC. Then `df-overseer-pause dismiss`: expect `ok: true`,
   `remaining: 0`, the box gone on VNC, tick unchanged, still paused. **If it
   does not close:** `df-overseer-ui dump` for the real button label, edit the
   `click_text` arguments in `POPUP_KINDS`, redeploy the file, repeat; the
   inert `pop_front` strategy is the documented last resort and must be
   enabled deliberately.
3. **Provoke the real thing.** On the paused fort, fire the announcement
   through the game's own flag path:
   `dfhack-run lua "dfhack.gui.showAutoAnnouncement(df.announcement_type.FORT_POSITION_SUCCESSION, nil, 'test succession', COLOR_WHITE, true)"`
   (adjust the call to the install's signature if it errors). Read `why`:
   expect a popup and a `recent_reports` row naming `FORT_POSITION_SUCCESSION`.
   This answers whether DO_MEGA creates a popup. To learn whether the game
   pauses itself, repeat once inside a `scripts/supervised-unpause.sh` window at
   10 fps and see whether `pause_state` flips.
4. **The watchdog, harmless path.** With step 3's popup pending and the fort
   paused, run the conductor once on VM 106 through the transient unit
   mirroring the service (`--once`). Expect in the cycle archive:
   `pause_watch.verdict` after dismiss, a `clock.resume`, a status read with a
   higher tick, and the fort running; then re-pause it by hand, per the
   supervised-window rules.
5. **The hold path.** Repeat with `MEGABEAST_ARRIVAL` as the announcement type
   (text only; nothing spawns). First `--once --dry-run`: the plan should show
   `wake_overseer`, no resume. A real run costs one Overseer run; expect the
   briefing's `wake_reason` to be `unexplained_pause`. Optional, since it spends
   money.
6. **Guards, live.** A latched tripwire is covered by the offline tests and the
   existing tripwire live evidence; if the user wants it seen live, latch one
   deliberately in a supervised window and confirm `pause_watch` is `null` in
   the cycle archive and `pause.dismiss` is never called.
7. **Record** the real popup text and the strategy that worked in
   `evals/live/<date>-pause-safety/`, update `TOOLS.yaml` `verified:` for both
   commands, and extend `conductor/pause_policy.yaml` with any real
   harmless type text seen.

## Result

Status: built offline, tests green, nothing deployed, nothing committed to
`main`. The design table, the built pieces and the plans are above. Open
questions for the user: (a) whether a clean Overseer run on an unexplained
pause is the right "resume" decision (the Overseer cannot call `clock.resume`
itself); (b) whether the 600 second grace for a plain pause and the 1800 second
liveness limit are right for an unattended year; (c) how soon Telegram should
become the alert sink.
