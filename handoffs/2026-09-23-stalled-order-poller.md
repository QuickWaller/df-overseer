# Stream: the conductor half, a poller for what no announcement can report

**Written** 2026-09-23. **Status:** dispatched. **User go-ahead:** 2026-09-23,
"agreed". **Offline code and tests only. No deploy, no VM, no unpausing.** A
sibling stream (`handoffs/2026-09-23-attention-tiers-ingame.md`) owns
`scripts/dfhack/` and the in-game tripwires; **you own `conductor/`**. Sonnet
executor, worktree-isolated. **No push. No attribution lines.** No em dashes.

## Why

`research/2026-09-23-announcement-severity.md`'s sharpest finding: a stalled
manager order produces **no announcement of any kind**, because the channel
only reports things that happen, not things that fail to happen. This fort has
had three orders sitting unrun for weeks and a fourth added 2026-09-23, all
`validated = true, active = false`, in silence. No tripwire can catch this. It
has to be polled.

`conductor/triage.py` already computes reasons of exactly this shape
(`stuck_job`, `stock_below_target`). This is one more, plus the routing for
the announcement levels the sibling stream exposes.

## What to do

1. **A stalled-order reason in `conductor/triage.py`.** An order that stays
   unstarted across a threshold of ticks wakes a role. Decide and justify: the
   threshold, which role (the Quartermaster proposes orders, the Overseer is
   the only writer), and how not to wake every cycle for the same order
   stalled for a known reason. Numbers go in `conductor/policy.yaml`, not in
   code.
2. **Read what is already deployed.** `orders.list` now reports `validated`,
   `active`, `amount_left`/`amount_total`, `frequency` and `finished_year`
   (deployed 2026-09-23, `evals/live/2026-09-23-order-job-attribution/`). Use
   those fields. Do not invent a new game-side read; if you genuinely need
   one, stop and report, because the sibling stream owns that surface.
3. **Distinguish stalled from blocked.** An order waiting on a missing
   material differs from one the Manager cannot validate at all, and this fort
   has both. `orders.check-duplicate` and the job attribution fields
   (`order_id`, origin) are available. Report which distinctions were cheap
   and which were not.
4. **Route the `slow` announcement level.** The sibling stream exposes the 23
   `slow` announcement ids rather than pausing on them. Consume that as a wake
   reason through the existing machinery, at the slowed clock level. **Agree
   the field shape with that stream and record the contract in both Result
   sections.** If it is not settled when you need it, define the interface you
   expect and say so.
5. **The observation ledger is read, never acted on.** The sibling stream
   builds it. If the briefing should carry a digest, add it to
   `conductor/briefing.py` under its existing size cap, and say what gets
   dropped when the cap binds. A ledger row must never become a wake reason by
   itself.
6. Tests, including: a stalled order raises the reason once, not every cycle;
   the threshold comes from policy, not code; a `slow` announcement wakes at
   the slowed level and never pauses; the briefing digest respects its cap.
   Both suites green: ambient `python -m pytest` (1281 passed / 3 skipped
   before you) and `.venv-dfmcp/Scripts/python -m pytest dfmcp/tests` (652
   before). Report the new counts.

## Hard lines

- **Offline only.** No ssh, no VM, no deploy, no live call, no unpausing.
- **Do not touch `scripts/dfhack/`**: the sibling stream owns it.
- No model call. Do not start `conductor.service`.
- Player visibility applies: a reason computed from something the player could
  not know is out.
- Secrets by key only, never printed. Never print an IP or hostname.
- Do not write `Working.md`, `decisions/` or `memory/`.
- Commit as you go and fill in the Result section.

## Touched surfaces

`conductor/` (`triage.py`, `policy.py`, `policy.yaml`, `briefing.py`,
`cycle.py` as needed), `conductor/tests/`, this doc.

## Result

(executor fills in)
