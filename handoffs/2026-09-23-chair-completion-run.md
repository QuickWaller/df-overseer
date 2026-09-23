# Handoff: run the fort until job 2249 makes a Chair and the suspended Chair building finishes

Date: 2026-09-23. **Live, mutating, unattended.** User go-ahead given
explicitly for this run ("yep go for it"), knowing they are not watching.
The fort is expendable but worth saving; every bound below exists because
nobody is at the wheel.

Read `CLAUDE.md` first, then `docs/TRAPS.md`,
`evals/live/2026-09-23-workjob-deploy/README.md` (what was just deployed and
queued), `evals/live/2026-09-23-office-and-first-real-build/README.md` (the
previous unattended run, its bounds, and the Chair that is waiting), and
`docs/AGENT-LOOP.md` §3 (tripwires and the three attention tiers).

## Why

This would be the first time the loop closes end to end on this fort. A tool
queued a real job; the fort has never run since. The chain to prove:

1. Job **2249** (`ConstructThrone`, at the Masons, `order_id: -1`, a direct
   job with no manager order) runs and produces a **Chair item**.
2. The **Chair building** placed on 2026-09-23, currently buildingplan
   suspended for want of exactly that item, claims it and **completes**.

Everything before today either dry-ran, or built something that then sat
waiting. Nothing has ever been carried through to a finished thing.

**The job name looks wrong and is not.** The user challenged `ConstructThrone`
as the job for a Chair; it was checked against the install itself before this
brief was dispatched, and it is correct:

- Building id 9 (type `Chair`, `constructed=false`) holds one
  `ConstructBuilding` job, suspended, whose single requirement reads
  `item_type=CHAIR subtype=-1 qty=1`.
- `df.item_type.THRONE` **does not exist on this build**; `df.item_type.CHAIR`
  does. The job kept the legacy name, caption "Construct Throne".
- DFHack's own buildingplan plugin states the mapping outright:
  `[df.item_type.CHAIR] = 'ConstructThrone'`.

This is the same renaming pattern the workjob stream hit with `MECHANISM`,
which this build superseded with `TRAPPARTS`. Do not "fix" the job name.

## The state you start from, verified 2026-09-23

- Fort paused, year 31, tick 107874, 100 FPS, 22 alive, 1 dead.
- **A stale tripwire is latched** from the previous run: a kea, 68 tiles away,
  caught by the PRE-fix tier code. Under the corrected classifier a kea is
  `record_only` and must not stop anything. **Clear the latch before you
  start** (`clock.clear`), then confirm `clock.status` shows it cleared and
  armed. If it re-latches on the same kea after the fix, that is a genuine
  finding and a reason to stop and report, not something to clear repeatedly.
- Four manager orders exist, none ever active: ids 0, 1, 2 `validated: true,
  active: false`, id 3 (ConstructThrone, created through `orders.create`)
  `validated: false`.
- Thirst read "thirsty" at the last check. Watch it.

## What to do

1. **Quicksave first and confirm it.** Confirmation is
   `cur_savegame.save_dir` changing to a new slot, DF's own record. Never
   mtime (`docs/TRAPS.md`). Do not proceed on an unconfirmed save.
2. Clear the stale latch, arm the tripwires, then run the fort in **windows
   of at most 2000 ticks**, up to **10 windows**. Quicksave between windows.
3. **After every window**, read and record: job 2249's existence and state,
   the Chair building's state (still suspended, or built), `stocks` for CHAIR
   or THRONE, vitals (hunger, thirst, deaths), and all four manager orders'
   `validated`/`active`. Watch the orders even though they are not the point
   of this run: whether an order ever goes active is the open office question,
   and this is the first fort time they have had.
4. **Stop immediately, quicksave, and report** on any of: a citizen death, a
   pause-tier tripwire, a vital crossing its threshold, job 2249 vanishing
   without a Chair appearing, or anything you did not expect. A surprise is a
   reason to stop and write it down, not to investigate by running further.
5. **Stop successfully** when the Chair building reports built. Then quicksave,
   pause, and report. Do not keep running to see what happens next.

## Rules

- **Pause is the safe state.** Leave the fort paused at the end, whatever
  happened. If anything goes wrong and you are unsure, pause first and report
  second.
- Use `bash scripts/vm-ssh.sh df '<cmd>'` for every VM command. Do not write
  your own ssh wrapper and do not read the address out of `.env` yourself:
  four separate agents have leaked a VM address doing exactly that. No
  address, hostname or token in any tracked file, commit message or report.
- Bound every query. Never run an unbounded scan against live DFHack.
- **You own** `evals/live/2026-09-23-chair-completion-run/README.md` (new) and
  this handoff's Result section. Do not edit any `.lua`, `TOOLS.yaml`,
  `dfmcp/**`, `agents/**`, `Working.md`, `decisions/DECISIONS.md`, `memory/`
  or `handoffs/INDEX.md`. **Do not deploy anything**: the tools you need are
  already installed. If a tool turns out to be broken, stop and report it
  rather than fixing and deploying it mid-run.
- **Unknown is never zero.** Quote the actual tool output for every claim in
  your report. "The Chair completed" needs the read-back that shows it, not
  your inference from the job disappearing.
- Commit after each milestone and extend the Result section as you go. No em
  dashes in prose. **No attribution lines in any commit message**: no
  Co-Authored-By, no "Generated with Claude Code".
- Stop and report on any permission or classifier refusal. Never route around
  it through another agent or session.

## Done means

Either the Chair building reports built, with the read-back quoted and the
tick it happened at, or the run stopped on one of the bounds above and the
report says exactly which, at what tick, with what evidence, and what the
fort's state was left as. In both cases: the fort is paused, a confirmed
quicksave exists, and the manager orders' status across the whole run is
recorded, because that is the office question's first real evidence.

## Result

<!-- The stream fills this in as it goes. -->
