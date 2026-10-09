"""The stateless stock check and the hold note (register 2026-10-09: "Stock checks go
stateless", "Item binding 3a").

No ledger and no promises. At execution a ready step that consumes counted stock
is checked against the live free stock; if it is short the step is held, nothing is
reserved or stored beyond a one-line note, and it retries next cycle. This module is the
pure part: what a step needs, whether stock covers it, the hold note's shape, whether
it should wake the Overseer, and the briefing line. `conductor/execute.py` does the reads.

Everything that differs per tool is policy data (`stock_check.consumers`); a tool with no
entry consumes nothing we can count and is never checked.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from conductor.policy import StockCheckPolicy, StockConsumer

MAX_HOLD_LINES = 5


def _arg(args: Mapping[str, Any], name: str) -> Any:
    """An argument by name, ignoring case (a step's keys are the tool's own spelling)."""
    for k, v in args.items():
        if str(k).lower() == name.lower():
            return v
    return None


def need_for(consumer: StockConsumer, args: Mapping[str, Any]) -> Optional[Tuple[str, int]]:
    """`(item type, units needed)` for one step, or None when it consumes nothing countable."""
    item = consumer.item
    if consumer.item_arg:
        raw = _arg(args, consumer.item_arg)
        if raw is None:
            return None
        raw = str(raw)
        if consumer.item_map:
            item = consumer.item_map.get(raw)
        else:
            item = item or raw
    if not item:
        return None
    count = 1.0
    if consumer.count_arg:
        raw = _arg(args, consumer.count_arg)
        try:
            count = float(raw)
        except (TypeError, ValueError):
            return None
    need = math.ceil(count * consumer.per_unit)
    return (str(item), need) if need > 0 else None


def required_with_margin(pol: StockCheckPolicy, need: int) -> int:
    """Need plus the margin: the larger of the fixed margin and a fraction of need."""
    return need + max(pol.margin, math.ceil(need * pol.margin_fraction))


def free_units(pol: StockCheckPolicy, read: Any) -> Optional[Tuple[int, Optional[int]]]:
    """`(free, held by other jobs or None)` from the stock read, or None when unusable
    (an unreadable stock never holds a step: the check fails open)."""
    if not isinstance(read, Mapping) or read.get("error"):
        return None
    free = read.get(pol.free_field)
    if isinstance(free, bool) or not isinstance(free, (int, float)):
        return None
    jobs = read.get(pol.in_job_field)
    return int(free), (int(jobs) if isinstance(jobs, (int, float)) and not isinstance(jobs, bool) else None)


def short_reason(item: str, need: int, required: int, free: int, in_jobs: Optional[int]) -> Optional[str]:
    """One line naming what is short, or None when stock covers need plus margin."""
    if free >= required:
        return None
    tail = f"; {in_jobs} more held by other jobs" if in_jobs else ""
    return f"short {item}: needs {need} (+{required - need} margin), {max(free, 0)} free{tail}"


def is_survival(pol: StockCheckPolicy, step: Mapping[str, Any]) -> bool:
    """Does this step serve food, drink or defence? Data: a policy regex over tool and arguments."""
    if pol.survival is None:
        return False
    args = step.get("args") if isinstance(step.get("args"), Mapping) else {}
    return bool(pol.survival.search(f"{step.get('tool')} {json.dumps(args, default=str)}"))


def wake_kind(pol: StockCheckPolicy, step: Mapping[str, Any], rec: Mapping[str, Any], tick: Optional[int],
              blocks_others: bool) -> Optional[str]:
    """Why this hold wakes the Overseer now (3a), or None: it is one briefing line only."""
    if is_survival(pol, step):
        return "survival"
    since = rec.get("since")
    if tick is not None and isinstance(since, int) and tick - since >= pol.wake_after_ticks:
        return "old"
    if blocks_others:
        return "blocks"
    return None


def hold_line(sid: str, rec: Mapping[str, Any]) -> str:
    since = rec.get("since")
    age = f", held since tick {since}" if isinstance(since, int) else ""
    return f"held step {rec.get('pid')}/{sid} ({rec.get('tool')}): {rec.get('why')}{age}; it retries each cycle"


def hold_lines(holds: Mapping[str, Mapping[str, Any]], cap: int = MAX_HOLD_LINES) -> List[str]:
    """The Overseer's briefing lines for the current holds, oldest first, capped."""
    items = sorted(holds.items(), key=lambda kv: (kv[1].get("since") if isinstance(kv[1].get("since"), int) else 1 << 60))
    lines = [hold_line(sid, rec) for sid, rec in items[:cap]]
    if len(items) > cap:
        lines.append(f"... and {len(items) - cap} more held steps")
    return lines


def survival_or_age_text(kind: str, pid: str, sid: str, why: str) -> str:
    cause = {"survival": "it serves food, drink or defence", "old": "it has been held over a game day",
             "blocks": "it blocks other steps in its project"}[kind]
    return (f"project {pid} step {sid} is held, not run ({cause}): {why}. Nothing was changed; it retries "
            f"each cycle. Free the stock (order it, or wait for it), or queue.pass naming {pid} to drop it.")
