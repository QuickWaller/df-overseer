"""Unsupplied buildings: polled from `workjob.unsupplied`, because nothing emits an event.

handoffs/2026-10-07-unsupplied-building-watch.md. A buildingplan-planned
building waits until an item of the kind it needs exists. Live 2026-10-07 the
fort's only Bed waited 38 game days for a BED item that never existed: BED
stock 0, a Carpenter's Workshop and wood on hand, and nobody ever queued
`ConstructBed` (evals/live/2026-10-07-stuck-bed/README.md). This watch wakes the
Quartermaster when that shape appears, one line per item kind.

The signal, per item kind X a planned building still needs
------------------------------------------------------------
- X has 0 free units (`available`), and
- no workshop job making X is queued right now (`jobs_queued_now`), and
- no manager order making X is **active and validated**.

`workjob.unsupplied` (scripts/dfhack/df-overseer-workjob.lua) reads the first
two and names, from the game's own job and reaction data, the jobs and workshop
kinds that make X (`producers`). Orders are joined here from `orders.list` by
job name (and reaction code): the read has no order access, and the cycle
already holds the order list. An order that exists for X but is inactive or
unvalidated does not count as supply (the stuck-bed read found all five live
orders inactive); it is named in the line, since that is a different fix from
"nobody asked for X".

What the read can and cannot say
--------------------------------
- A row whose `available` is null (its stock read failed), or any row when the
  order list could not be read, is in `unreadable`: that kind's edge state is
  kept and no line is made, never a wake on a guess. A whole poll that fails or
  is not a row list is `None`: all state kept.
- Only kinds a planned building names concretely appear; a material-class
  wildcard (any wood) names no kind and is not watched.
- The edge trigger, backoff and stalled state live in `conductor/lanes.py` with
  the rest of the lane state, data-driven from `policy.yaml`
  (`unsupplied_building`, `lane_triggers.<role>.unsupplied`).

This module never queues a job, creates an order or builds anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Tuple

from conductor.order_watch import _finished, _has_work_left

#: Tool the conductor polls (agents/conductor/tools.yaml).
POLL_TOOL = "workjob.unsupplied"

#: Wake lines are bounded like every other conductor line.
MAX_LINE_CHARS = 240

TICKS_PER_GAME_DAY = 1200

#: Producers named in a line before "+N more".
MAX_PRODUCERS_NAMED = 2


@dataclass(frozen=True)
class UnsuppliedItem:
    item: str
    buildings: int
    units: int
    #: (job, reaction or "", workshop kind), as the read names them.
    producers: Tuple[Tuple[str, str, str], ...]
    #: Orders for a producing job that exist but do not count as supply.
    inactive_orders: Tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return self.item

    def line(self, waiting_ticks: Optional[int] = None) -> str:
        noun = "building" if self.buildings == 1 else "buildings"
        wait = ""
        if waiting_ticks is not None and waiting_ticks >= 0:
            wait = f" {waiting_ticks // TICKS_PER_GAME_DAY}d"
        head = f"{self.item}: {self.buildings} planned {noun} waiting{wait}, 0 free"
        if self.producers:
            named = [
                f"{reaction or job} at {shop}" for job, reaction, shop in self.producers[:MAX_PRODUCERS_NAMED]
            ]
            more = len(self.producers) - MAX_PRODUCERS_NAMED
            made = "made by " + ", ".join(named) + (f" (+{more} more)" if more > 0 else "")
        else:
            made = "no built workshop offers a job making it"
        if self.inactive_orders:
            tail = "; " + "; ".join(self.inactive_orders)
        else:
            tail = "; no order or job is making it"
        return f"{head}; {made}{tail}"[:MAX_LINE_CHARS]


@dataclass(frozen=True)
class UnsuppliedRead:
    items: Tuple[UnsuppliedItem, ...] = ()
    #: Kinds polled but not judgeable this time: their edge state is kept.
    unreadable: FrozenSet[str] = frozenset()

    def get(self, item: str) -> Optional[UnsuppliedItem]:
        return next((i for i in self.items if i.item == item), None)


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _order_matches(order: Mapping, producers: Sequence[Tuple[str, str, str]]) -> bool:
    job = _text(order.get("job")).lower()
    reaction = _text(order.get("reaction")).lower()
    for pjob, preaction, _shop in producers:
        if job != pjob.lower():
            continue
        if preaction and reaction != preaction.lower():
            continue
        return True
    return False


def _order_state(order: Mapping) -> str:
    """`running` when the order is validated and active, else why it is not."""
    if order.get("validated") is False:
        return "unvalidated"
    if order.get("validated") is True and order.get("active") is True:
        return "running"
    if order.get("active") is False:
        return "inactive"
    return "not confirmed running"


def unsupplied_read(result: Any, orders: Optional[Iterable[Mapping]]) -> Optional[UnsuppliedRead]:
    """Parse `workjob.unsupplied` (a dict holding `unsupplied`, or the bare
    list) and join `orders` (`orders.list`'s `orders` array, or `None` when
    that read failed). `None` when `result` is not a row list at all."""
    rows = result
    if isinstance(result, Mapping):
        rows = next((result[k] for k in ("unsupplied", "result") if isinstance(result.get(k), list)), None)
        if rows is None and result.get("error") is None and "unsupplied" in result:
            rows = []  # an empty Lua table may serialise as {}
    if not isinstance(rows, list):
        return None
    order_list: Optional[List[Mapping]] = None
    if orders is not None:
        order_list = [o for o in orders if isinstance(o, Mapping) and not _finished(o) and _has_work_left(o)]

    items: List[UnsuppliedItem] = []
    unreadable: List[str] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        item = _text(row.get("item"))
        if not item:
            continue
        available = _int(row.get("available"))
        queued = _int(row.get("jobs_queued_now"))
        if available is None or queued is None or order_list is None:
            unreadable.append(item)
            continue
        if available > 0 or queued > 0:
            continue  # supplied, or a job is making it
        producers = tuple(
            (_text(p.get("job")), _text(p.get("reaction")), _text(p.get("workshop_kind")))
            for p in (row.get("producers") or [])
            if isinstance(p, Mapping) and _text(p.get("job"))
        )
        matching = [o for o in order_list if _order_matches(o, producers)] if producers else []
        if any(_order_state(o) == "running" for o in matching):
            continue  # a standing order is live: the game is supplying it
        notes = tuple(
            f"order #{o.get('id')} for it is {_order_state(o)}" for o in matching if o.get("id") is not None
        )
        items.append(UnsuppliedItem(
            item=item,
            buildings=_int(row.get("buildings_waiting")) or 0,
            units=_int(row.get("units_needed")) or 0,
            producers=producers,
            inactive_orders=notes,
        ))
    items.sort(key=lambda i: i.item)
    return UnsuppliedRead(tuple(items), frozenset(unreadable))
