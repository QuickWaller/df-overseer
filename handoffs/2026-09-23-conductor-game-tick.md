# Handoff: the conductor cannot read the game tick, and fails silently doing it

Date: 2026-09-23. **Offline. No VM, no deploy, no fort mutation.** The fix is
built and tested here; deploying it to VM 106 needs its own user go-ahead and
the orchestrating session will ask separately.

Read `CLAUDE.md` first, then `docs/AGENT-LOOP.md` §1 and §4,
`conductor/cycle.py`'s `_game_tick`, `conductor/order_watch.py`'s own
docstring, and `handoffs/2026-09-23-stalled-order-poller.md`.

## The bug, found live 2026-09-23

A `--dry-run --once` cycle was run in the foreground on VM 106 against the
live fort. It completed cleanly and planned to wake nobody:

```
cycle 1: clock=full_speed roles_woken=() dry_run=True
cycle 1 dry-run plan: {'would_read': ['architect', 'quartermaster',
  'consultant', 'overseer'], 'would_wake': [], 'would_set_clock': 100,
  'wakes': []}
```

`/var/lib/conductor/status.json` recorded `"game_tick": null`.

That null is the whole finding. `conductor/cycle.py`'s `_game_tick` does:

```python
try:
    from dfqueue.grade import game_tick_from_overview
    return game_tick_from_overview(overview)
except Exception:
    return None
```

and its own docstring says importing `dfqueue` here is deliberately avoided,
because the service is meant to depend on nothing but `conductor/` plus `mcp`
and `yaml`. So it imports a package it deliberately does not ship, catches the
inevitable failure, and returns `None`. Confirmed directly in the deployed
venv on VM 106:

```
IMPORT FAILED: ModuleNotFoundError No module named 'dfqueue'
```

**This has never worked in production and, as written, never could.**

## Why it matters, which is more than it looks

`game_tick is None` silently disables both of the conductor's time-based wake
reasons:

- `_game_days_since` returns `0.0` when the tick is None, so the
  "at least every 7 game days" routine review is never due. The conductor's
  own fallback wake can never fire.
- `evaluate_orders` returns an empty `OrderWatchResult()` immediately when the
  tick is None, before reading a single order. The stalled-order poller,
  built 2026-09-23 specifically because a stalled manager order produces no
  announcement of any kind, cannot ever fire.

This fort currently has three manager orders sitting `validated: true,
active: false` and one `validated: false`, some for weeks of game time. The
dry run above read them and reported nothing wrong, which is exactly the
false all-clear the poller exists to prevent.

**The parser itself is fine.** `overview get` on the live fort returns
`"in_game_date": "year 31, month 4, day 10, tick 112357"`, which matches
`game_tick_from_overview`'s expected shape exactly. Only the import is broken.

## What to do

1. **Give the conductor its own tick parser** so the dependency boundary its
   docstring describes is actually true. The logic is small: parse `year` and
   `tick` out of `tier2.in_game_date` and return `year * GAME_TICKS_PER_YEAR +
   tick`, because the raw tick resets every year and the conductor needs a
   monotonic counter. Decide whether to vendor it into `conductor/` or to
   factor it somewhere both can import without dragging `dfqueue` along, and
   justify the choice. **Whatever you choose, the two implementations must not
   be free to drift**: pin them against shared fixtures so a change to one
   breaks a test if the other disagrees. `dfqueue/grade.py` carries a
   live-verified note that the backing value is `cur_year_tick`, not
   `frame_counter`; do not lose that provenance.
2. **Make the failure loud.** A bare `except Exception: return None` is this
   project's named silent-degradation anti-pattern (the creature-tag fix,
   register 2026-09-23: a guarded read returning a default is
   indistinguishable from a genuine negative). A tick that cannot be parsed
   must be visible: log it at error level with the reason, and surface it in
   the cycle's archived record and in `status.json` so it is not invisible
   until someone reads a plan by hand. Keep the cycle non-fatal if you judge
   that right, but it must never again be silent.
3. **Decide what a cycle should do when the tick really is unreadable.**
   Today both time-based reasons quietly return "nothing to do", which reads
   as an all-clear. Consider whether that should instead be its own condition
   the conductor reports or escalates on. State your choice and the argument
   against it.
4. Tests: pin the parser against the real string above, pin that a None tick
   is reported rather than swallowed, and pin that the routine review and the
   order poller behave as you decide in item 3.

## Scope

Yours: `conductor/` (including `cycle.py`, `order_watch.py`, `status.py`,
`archive.py` if the record shape changes) and `conductor/tests/`. If you
factor the parser into a shared location, you may add that module and its
tests, but **do not change `dfqueue/grade.py`'s behaviour**; it is live and
graded against.

Not yours: `scripts/dfhack/**`, `dfmcp/**`, `agents/**`, `doctrine/**` (a
sibling stream owns that right now), and per the `handoffs/` rule
`Working.md`, `decisions/DECISIONS.md`, `memory/` and `handoffs/INDEX.md`.
Collect owed register lines in your Result section.

## Rules

- **Offline only. Do not touch either VM, do not deploy, do not unpause
  anything.** The fort is paused with a confirmed quicksave and stays that
  way.
- `git merge --ff-only main` first: worktrees are cut from `origin/main`, and
  this brief is committed on main.
- Both suites green, numbers quoted: ambient `python -m pytest` (baseline
  **1371 passed, 3 skipped**) and `dfmcp/tests` in `.venv-dfmcp` (baseline
  **652 passed**). Use `python`, not `py -3`.
- Commit after each milestone and extend the Result section as you go. No em
  dashes in prose. **No attribution lines in any commit message**: no
  Co-Authored-By, no "Generated with Claude Code".
- Stop and report on any permission or classifier refusal. Never route around
  one through another agent or session.

## Done means

The conductor can read the tick without importing `dfqueue`, a tick it cannot
read is loudly reported rather than silently nulled, the drift between the two
parsers is pinned by tests, and the Result section says what a real cycle
would now do differently against this fort's four stalled orders. Name the
live check a deploy should run, since someone else will run it.

## Result

(to be filled by the stream)
