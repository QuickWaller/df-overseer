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

**Status: built and tested offline. No VM, no ssh, no deploy, no unpause,
`scripts/dfhack/` untouched.** Branch `worktree-agent-aca2caf94a10bde00`
(this worktree's own branch), one commit so far (`wip: stalled/blocked order
poller and slow-announcement routing`).

### What was built

1. **`conductor/order_watch.py` (new).** `evaluate_orders()` reads
   `orders.list`'s own `orders` array (`id`, `validated`, `active`,
   `amount_left`, `amount_total`, `finished_year` -- exactly the fields
   `evals/live/2026-09-23-order-job-attribution/README.md` confirmed live)
   and distinguishes:
   - **stalled**: `validated: true, active: false` -- this fort's own three
     real orders' exact shape.
   - **blocked**: `validated: false` -- the Manager could not validate the
     order at all.
   Neither fires until it has held continuously for `stalled_order_threshold_ticks`
   (policy, 1200 = 1 game day), and neither re-fires within
   `stalled_order_renotify_ticks` of its own last notification (also 1200).
   Per-order bookkeeping (first-seen tick, last-notified tick) lives in the
   existing `CursorStore` JSON file, one more small integer per order id
   under a reserved key prefix -- no second state file.
2. **`conductor/policy.yaml`/`policy.py`**: `stalled_order_threshold_ticks`,
   `stalled_order_renotify_ticks` (both required, `PolicyError` if missing,
   matching every other policy value's discipline), plus three new
   `wake_reasons` entries: `stalled_order`, `blocked_order` (both `clock:
   slowed, wakes: [quartermaster]`), `slow_announcement` (`clock: slowed,
   wakes: []` -- see below for why that field is unused).
3. **`conductor/triage.py`**: `Signals` gained `stalled_order(_ids)`,
   `blocked_order(_ids)`, `slow_announcement(_roles/_detail)`. Three
   dedicated blocks in `triage()` (not the generic boolean-reason loop)
   build a `Wake` naming the actual order ids, or, for
   `slow_announcement`, the actual role list carried on the event rather
   than a policy-fixed one. **No ledger field exists on `Signals` at all**
   -- the hard rule ("a ledger row must never become a wake reason on its
   own") is enforced structurally, not by a runtime check:
   `test_a_ledger_row_alone_is_never_a_wake_reason` asserts the attribute
   doesn't exist.
4. **`conductor/cycle.py`**: added one more Tier 0 read, `orders.list`, next
   to the existing five; `evaluate_orders()` is called in the TRIAGE step
   with `deps.policy`'s two new values and `deps.cursor_store`.
   `_classify_slow_announcements()` scans every role's own drained
   `diff.since` events for a `type: "announcement_slow"` event (see
   "Slow-announcement interface" below), deduplicates by
   `(announcement_type, tick)` (the same underlying report can land in more
   than one role's own diff drain, since each role drains the same event
   log through its own cursor), and unions the `wake` role lists it
   carries.
5. **`conductor/briefing.py`**: `build_briefing()` gained an optional
   `ledger_digest` parameter, capped by a new `MAX_LEDGER_ROWS = 10`
   exactly like every other list in that function. **Not wired to a real
   read anywhere** -- no ledger tool id exists yet in this worktree (the
   sibling in-game stream owns building it). When it lands, `cycle.py`
   needs one more bounded Tier 0 read and to pass the result through; no
   other change to `briefing.py` itself. What gets dropped when the cap
   binds: rows past the 10th, in whatever order the caller handed them in
   -- this function does not re-rank, matching `_capped()`'s existing
   behaviour for diff events and queue ids.

### The threshold, and why

`stalled_order_threshold_ticks = 1200` (1 game day at DF's fixed
1200-ticks/day calendar), same value for `stalled_order_renotify_ticks`.
Reasoning: this fort's own real incident (three orders, `CLAUDE.md`'s
status line) sat stalled for **weeks**, so a one-day gate is conservative
in the direction of catching a genuine stall fast, without firing on an
order that simply hasn't been looked at yet this cycle (the conductor's own
cycle cadence is much shorter than a game day at `base_fps: 100`). The
renotify cooldown reuses the same figure: a stalled order is worth a daily
reminder while unresolved (not silently forgotten), never every single
cycle. Neither number was measured against a real run -- no VM this
stream, same caveat `conductor/briefing.py`'s own `MAX_DIFF_EVENTS` already
carries. Worth retuning once real cycle timing is observed.

### Stalled vs. blocked: which distinctions were cheap

**Cheap**: stalled-vs-blocked itself. `validated` and `active` are both
already on every `orders.list` row, read once, no extra tool call, no extra
parsing -- distinguishing them cost exactly one more `if` in
`_condition()`. This directly answers item 3's ask.

**Not cheap, and not attempted**: the handoff also named
`orders.check-duplicate` and the job-attribution fields (`order_id`,
origin) as available for a finer read. Not used here, on purpose: neither
adds information `stalled`/`blocked` doesn't already carry for THIS
fort's own known incident (all three real orders are `validated: true,
active: false` with no live job ever spawned -- `orders.check-duplicate`'s
own `jobs_in_flight: []` on this fort, per the deploy eval), and pulling in
a second tool call per order to cross-check would cost real per-cycle
latency for no signal this stream could verify improves triage. Left as a
documented "not attempted, and why" rather than built speculatively.

**Also not attempted, flagged as genuinely uncertain**: whether a brief,
harmless `validated: false` window exists right after order creation
(before the Manager has had a tick to look at it), which would make
`blocked_order` fire on a false positive if the threshold were too short.
No VM this stream to check live. The 1200-tick threshold is applied to
`blocked_order` too as the conservative default rather than inventing a
shorter, unverified figure for it.

### Slow-announcement interface: ASSUMED, not agreed live

This stream and `handoffs/2026-09-23-attention-tiers-ingame.md`'s executor
run as separate, independent agent sessions with no live channel between
them, so nothing here was actually confirmed with that stream while
building it. **The interface this code assumes**, stated plainly per this
handoff's own instruction:

A `slow`-level announcement, once that stream's fifth tripwire lands,
drains through `diff.since` as an event of this shape:
```json
{
  "type": "announcement_slow",
  "announcement_type": "AMBUSH_MISCHIEVOUS",
  "tick": 12607074,
  "wake": ["overseer"],
  "detail": "a mischief-class creature is closing in"
}
```
- `type` is the fixed literal `"announcement_slow"` (chosen to sit
  alongside `EVENT_TYPE_TO_SIGNAL`'s existing literal event-type strings,
  same style).
- `announcement_type` is the raw `df.announcement_type` name.
- `wake` is a list of this project's own role name strings, copied from
  `research/data/2026-09-23-announcement-severity.yaml`'s own per-type
  `wake` field for that id (may be empty -- some `slow` ids may carry no
  default role, matching `hostile_seen_unreachable`'s existing "slows the
  clock, wakes nobody" precedent).
- `detail` is a short human-readable gloss (the YAML's own `reason`
  field, or similar).

If the real build lands a different shape, `conductor/cycle.py`'s
`_classify_slow_announcements` (one function, clearly marked "not verified
against a real payload... recorded as an assumed interface") is the single
place to fix. This mirrors `EVENT_TYPE_TO_SIGNAL`'s own pre-existing
"unverified against a real diff.since payload" flag for the other four
event types -- this project already had exactly this kind of open
contract before this stream, not a new problem introduced here.

### Deviation from the listed touched surfaces

`agents/conductor/tools.yaml` was edited (added a read grant for
`orders.list` to the `conductor` role) -- **not** in this handoff's own
"touched surfaces" list (`conductor/`, `conductor/tests/`, this doc).
Necessary: without it, `conductor/cycle.py`'s new `call("orders.list", {})`
would be refused by the real server once deployed (the conductor's own
token had no grant for that id before this change). Checked against the
sibling stream's own touched surfaces
(`handoffs/2026-09-23-attention-tiers-ingame.md`: `scripts/dfhack/`,
a ledger module, `TOOLS.yaml`, "matching dfmcp schema and role allowlists"
for the LEDGER read verb) -- that stream's role-allowlist work is about a
different, not-yet-existing tool id (the ledger), never `orders.list` or
`agents/conductor/tools.yaml`, so this edit does not collide with anything
that stream owns. Flagged here rather than silently included, per this
handoff's own instruction.

### Tests and counts

New: `conductor/tests/test_order_watch.py` (12 tests: threshold gate,
renotify cooldown, stalled-vs-blocked, dispatched/finished/no-work-left
orders excluded, the infinite-order `amount_total: 0` case, bookkeeping
reset on recovery, dry-run non-advancement, missing `game_tick`, an order
missing its own `id`). Extended: `test_triage.py` (+7: stalled/blocked wake
correctly, a quiet order-watch wakes nobody, slow-announcement wakes its
named roles at `slowed` and never pauses, the ledger-absence assertion),
`test_cycle.py` (+5: a fresh stall doesn't wake early, a stall past
threshold does, a blocked order wakes distinctly, a slow announcement event
wakes its role, the same event seen by two roles' drains is deduplicated),
`test_policy.py` (helper updated for the two new required fields),
`test_service.py` (its own separate `_quiet_tools()` fixture needed
`orders.list` too, found by running the suite, not anticipated in advance).

**Ambient `python -m pytest`: 1304 passed, 3 skipped** (was 1281 passed / 3
skipped before this stream -- the 3 skips are the same pre-existing,
correct transport-SDK skips, unrelated to this work).
**`.venv-dfmcp` `python -m pytest dfmcp/tests`: 652 passed**, unchanged
from before (this stream touched no `dfmcp/*.py`; the `agents/conductor/
tools.yaml` edit is read at server start, not exercised by this offline
suite).

### Still wrong / owed

1. **The slow-announcement interface is assumed, not confirmed** (see
   above) -- the single largest open risk in this stream's own work. If the
   sibling stream's real event shape differs, `_classify_slow_announcements`
   needs a one-function fix, not a redesign, but it WILL currently silently
   see nothing (no crash, no wake) against whatever the real shape turns
   out to be, until that fix lands. This mirrors, rather than fixes,
   `EVENT_TYPE_TO_SIGNAL`'s own pre-existing same-shaped gap.
2. **The ledger digest is designed but entirely unwired** -- no ledger read
   tool exists in this worktree to call. `conductor/briefing.py` is ready
   for it; `conductor/cycle.py` is not, since there is nothing to read yet.
3. **Neither threshold was measured against a real run.** Both are reasoned
   defaults, flagged as such in `policy.yaml`'s own comments, same honesty
   level as this file's own pre-existing `expected_thinking_seconds`/
   `MAX_DIFF_EVENTS` figures.
4. **`agents/conductor/tools.yaml`'s new grant was never exercised against
   a live server** -- consistent with every other grant in that file
   (`status: exists`/`live_deployed: false` convention), but worth a live
   role-tool-count check (the same shape
   `evals/live/2026-09-23-order-job-attribution/README.md` already ran for
   the last batch) before this is trusted live.
5. **`CursorStore`'s per-order keys grow unboundedly** if orders are
   cancelled and recreated with new ids repeatedly over a long fort
   lifetime -- each id gets its own two small integer entries that are
   never pruned once an order is fully gone (only reset to 0, never
   deleted). Not addressed this stream: the existing file is already
   small and this matches `CursorStore`'s own existing single-writer,
   plain-JSON-file scope, but flagged as a real, if minor, growth path for
   a very long-running fort.
