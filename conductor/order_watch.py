"""Stalled and blocked manager orders: `research/2026-09-23-announcement-
severity.md` §C, the report's own sharpest finding -- a manager order that
never dispatches a job produces **no announcement of any kind**, because DF's
event pipeline only fires for things that happen. This fort has had three
orders sitting `validated: true, active: false` for weeks, a fourth added
2026-09-23, all silent. The only way to see this class of failure is to poll
`orders.list` and diff its own status fields across cycles.

`scripts/dfhack/df-overseer-orders.lua`'s `list_orders()` (deployed
2026-09-23, `evals/live/2026-09-23-order-job-attribution/`) already reports,
per order: `id`, `validated`, `active`, `amount_left`, `amount_total`,
`frequency`, `finished_year`. This module reads only those fields -- no new
game-side read, per this stream's own hard line.

## Two distinct conditions (handoffs/2026-09-23-stalled-order-poller.md
## item 3: "distinguish stalled from blocked")

- **stalled**: `validated: true, active: false`. The Manager accepted the
  order as fulfillable but nothing is dispatching it. This fort's own three
  orders are exactly this shape (`CLAUDE.md`'s status line: "the queued
  manager orders still do not run", leading suspect the missing Office).
- **blocked**: `validated: false`. The Manager could not even validate the
  order -- a more fundamental failure than a stall, and worth a distinct
  reason name rather than folding it into "stalled", even though this build
  reads both from fields already on hand (cheap: no second tool call, no
  extra parsing -- see this stream's Result section for which distinctions
  in the handoff's item 3 were cheap and which were not).

Both conditions use the same threshold and renotify cadence
(`conductor/policy.yaml`'s `stalled_order_threshold_ticks`/
`stalled_order_renotify_ticks`) -- whether DF leaves a brief, harmless
`validated: false` window right after order creation (before the Manager has
had a chance to look at it) was not checked live this stream (no VM), so the
conservative choice is to apply the same "has this held for a while" gate to
both rather than firing `blocked` the instant an order is created.

## Not waking every cycle for the same known stall

An order enters the returned result only once **both**:

1. it has held its condition (stalled or blocked) continuously for at least
   `threshold_ticks` -- an order that is merely between cycles, not really
   stuck, never fires; and
2. it has not already been notified within the last `renotify_ticks` -- a
   genuinely stuck order wakes its role once, then again only after the
   renotify window elapses, never every single cycle. This is the
   handoff's own requirement: "how not to wake every cycle for the same
   order stalled for a known reason."

Bookkeeping (per-order first-seen tick, per-order last-notified tick) is
kept in the same small JSON file `conductor/cursors.py`'s `CursorStore`
already owns for per-role diff cursors -- one more integer per order id,
under a reserved key prefix no real role name can collide with, rather than
a second state file. An order that stops being a stall/block candidate (it
finishes, is cancelled, or genuinely starts running) has its bookkeeping
reset, so a LATER stall on the same id starts its own threshold clock again
rather than firing instantly off stale history.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Mapping, Optional, Tuple

from conductor.cursors import CursorStore

#: Reserved CursorStore key prefixes. No real role name can collide with
#: these (role names are bare identifiers like "architect"; these always
#: carry a numeric order id after the prefix).
_FIRST_SEEN_PREFIX = "__order_first_seen_"
_LAST_NOTIFIED_PREFIX = "__order_last_notified_"

STALLED = "stalled"
BLOCKED = "blocked"


def _finished(order: Mapping) -> bool:
    """`finished_year` is -1 while an order has never finished
    (`df-overseer-orders.lua`'s own `order_status_fields`); any other value
    (including 0) means DF recorded a real completion year."""
    fy = order.get("finished_year")
    return fy is not None and fy != -1


def _has_work_left(order: Mapping) -> bool:
    """`amount_total == 0` is this project's own tool's convention for an
    infinite/repeating order (`df-overseer-orders.lua create_order`'s own
    "0 = infinite"), which always still has work left. An unread
    `amount_left` (None, a defensive pcall miss) is treated as "still has
    work" -- the safe direction, since the alternative (treating an unread
    field as finished) would silently stop watching a genuinely stalled
    order."""
    amount_total = order.get("amount_total")
    if amount_total == 0:
        return True
    amount_left = order.get("amount_left")
    if amount_left is None:
        return True
    return amount_left > 0


def _condition(order: Mapping) -> Optional[str]:
    """`STALLED`, `BLOCKED`, or `None` (not a candidate: finished, no work
    left, or genuinely running)."""
    if _finished(order) or not _has_work_left(order):
        return None
    validated = order.get("validated")
    active = order.get("active")
    if validated is False:
        return BLOCKED
    if validated is True and active is False:
        return STALLED
    return None  # active (dispatched) or validated is unread (None): not a candidate


@dataclass(frozen=True)
class OrderWatchResult:
    stalled_ids: Tuple[int, ...] = ()
    blocked_ids: Tuple[int, ...] = ()

    @property
    def any_due(self) -> bool:
        return bool(self.stalled_ids or self.blocked_ids)


def evaluate_orders(
    orders: Iterable[Mapping],
    *,
    game_tick: Optional[int],
    threshold_ticks: int,
    renotify_ticks: int,
    cursor_store: CursorStore,
    dry_run: bool,
) -> OrderWatchResult:
    """One call per cycle, over `orders.list`'s own `orders` array. Reads
    (and, for a real cycle, writes) per-order bookkeeping via
    `cursor_store` -- see this module's own docstring. A dry run reads the
    same state a real cycle would see but never advances it, matching
    `conductor/cycle.py`'s `_drain_all_cursors` own dry-run contract for
    the per-role diff cursors.

    `game_tick=None` (the tick could not be parsed this cycle,
    `conductor/cycle.py`'s own `_game_tick` is best-effort) always returns
    an empty result rather than guessing an age for every order.
    """
    if game_tick is None:
        return OrderWatchResult()

    stalled: List[int] = []
    blocked: List[int] = []

    for order in orders:
        order_id = order.get("id")
        if order_id is None:
            continue
        first_key = f"{_FIRST_SEEN_PREFIX}{order_id}"
        notified_key = f"{_LAST_NOTIFIED_PREFIX}{order_id}"
        condition = _condition(order)

        if condition is None:
            if not dry_run:
                cursor_store.set(first_key, 0)
                cursor_store.set(notified_key, 0)
            continue

        first_seen = cursor_store.get(first_key)
        if first_seen == 0:
            first_seen = game_tick
            if not dry_run:
                cursor_store.set(first_key, first_seen)

        ticks_in_state = max(0, game_tick - first_seen)
        if ticks_in_state < threshold_ticks:
            continue

        last_notified = cursor_store.get(notified_key)
        if last_notified != 0 and (game_tick - last_notified) < renotify_ticks:
            continue

        if not dry_run:
            cursor_store.set(notified_key, game_tick)

        (stalled if condition == STALLED else blocked).append(int(order_id))

    return OrderWatchResult(stalled_ids=tuple(stalled), blocked_ids=tuple(blocked))
