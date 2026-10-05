"""The per-cycle briefing: `docs/AGENT-LOOP.md` item 6.

"Tier 0 figures only (vitals, cover days, stuck jobs, the role's diff, queue
state), placed in the prompt. Nothing that grows with the fort." Tier 0 is
`docs/AGENT-ARCHITECTURE.md` §5's own definition: "Numbers and booleans
only... O(1) in fort size."

`build_briefing` is a pure function: given already-read Tier 0 data (vitals,
this role's own drained diff events, the queue's own pending summary, and
why this role was woken), it returns one small, bounded dict -- never a
prose paragraph and never anything requiring a further DFHack read. Every
list inside it is capped (`MAX_DIFF_EVENTS`, `MAX_QUEUE_IDS`), so the
briefing's own size is independent of the fort's population, map size, or
how many events piled up since a role last woke -- the safety net this
stream's own report calls out, on top of `diff.since`'s already-bounded
per-call event list, precisely because nothing yet proves that list itself
is always small in the worst case (a role that slept for a very long time).
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from conductor.triage import Wake

#: Caps that make the briefing's size independent of fort size, regardless
#: of how large diff.since's own event list or the queue's own pending list
#: happen to be this cycle. Picked as "enough to be useful, small enough to
#: never dominate a prompt" -- not measured against a real run (no VM this
#: stream); worth revisiting once real cycle sizes are observed.
MAX_DIFF_EVENTS = 20
MAX_QUEUE_IDS = 20

#: handoffs/2026-09-23-stalled-order-poller.md item 5: the sibling in-game
#: stream's observation ledger (creature race + outcome, aggregated, never
#: acted on -- see that stream's own Result section) MAY be worth a digest
#: in the briefing. Capped the same way every other list here is, so its
#: presence never makes the briefing's own size depend on how many rows the
#: ledger has accumulated. Rows past this cap are dropped in ROW ORDER as
#: handed in (the caller is expected to have already sorted "most worth
#: seeing first" -- this function does not re-sort, matching every other
#: `_capped()` use here), never re-ranked by this function.
MAX_LEDGER_ROWS = 10

#: Stuck-job lines shown per briefing (handoffs/2026-10-05-stuck-job-watch.md);
#: the count is always the full figure, the lines are the oldest few.
MAX_STUCK_JOB_LINES = 5


#: handoffs/2026-10-05-better-briefing.md: the first lookups every role made
#: in the 2026-10-05 runs (stock, orders, per-item availability, seeds), put in
#: the briefing so a turn starts from the facts. All capped, all numbers or
#: short lines, never coordinates and never a map.
MAX_ORDER_LINES = 5
MAX_AVAILABILITY_LINES = 6
MAX_SEED_PLANTS = 3


def _capped(items: Sequence[Any], cap: int) -> Dict[str, Any]:
    items = list(items)
    return {
        "items": items[:cap],
        "count": len(items),
        "truncated": len(items) > cap,
    }


def build_briefing(
    *, role: str, game_tick: int, wake: Wake, vitals: Mapping[str, Any],
    diff_events: Sequence[Mapping[str, Any]], queue_summary: Mapping[str, Any],
    ledger_digest: Optional[Sequence[Mapping[str, Any]]] = None,
    stuck_jobs: Optional[Sequence[str]] = None,
    facts: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """One role's briefing for this cycle. `vitals` is `vitals.summary`'s own
    result, passed through as-is (already Tier 0 by construction -- see
    `scripts/dfhack/df-overseer-vitals.lua`). `diff_events` is this role's
    own drained `diff.since` events (already scoped to its cursor). `wake`
    carries why this role was woken this cycle -- never omitted, so a role
    never has to guess why it was disturbed.

    `ledger_digest`: `None` (the default) omits the `"ledger"` key entirely
    -- no caller today has a ledger read verb to supply one, since the
    sibling in-game stream's observation ledger
    (handoffs/2026-09-23-attention-tiers-ingame.md item 4) had not landed a
    read tool at the time this was written. When a caller does have rows to
    show, they are capped exactly like every other list in this function
    (`MAX_LEDGER_ROWS`) -- this parameter exists so `conductor/cycle.py` can
    start passing real rows the moment that read exists, with no further
    change to this function. **The ledger is read-only input here, same as
    everywhere else in this package: nothing about receiving or capping it
    ever pauses the fort or wakes anyone by itself** -- that is decided
    entirely by `conductor/triage.py`'s own reasons, never by what shows up
    in a briefing.
    """
    briefing: Dict[str, Any] = {
        "role": role,
        "game_tick": game_tick,
        "wake_reason": wake.reason,
        "wake_detail": wake.detail,
        "clock": wake.clock,
        "vitals": {
            "alive": vitals.get("alive"),
            "dead_total": vitals.get("dead_total"),
            "worst_hunger_status": vitals.get("worst_hunger_status"),
            "worst_thirst_status": vitals.get("worst_thirst_status"),
            "warning_count": vitals.get("warning_count"),
        },
        "diff_since_last_wake": _capped(diff_events, MAX_DIFF_EVENTS),
        "queue": {
            "count": queue_summary.get("count", 0),
            "ids": _capped(
                queue_summary.get("proposal_ids") or queue_summary.get("ask_ids") or (),
                MAX_QUEUE_IDS,
            ),
        },
    }
    if stuck_jobs is not None:
        # Tier 0: a count plus a few short lines, bounded like every other list.
        briefing["stuck_jobs"] = _capped([str(s)[:160] for s in stuck_jobs], MAX_STUCK_JOB_LINES)
    if facts:
        briefing["facts"] = dict(facts)
    if ledger_digest is not None:
        briefing["ledger"] = _capped(ledger_digest, MAX_LEDGER_ROWS)
    return briefing


# ---------------------------------------------------------------------------
# Facts: what each role used to look up first. Pure functions over reads the
# conductor already made; each returns None (or nothing) when its input is
# missing or the wrong shape, so a failed read drops that line only.
# ---------------------------------------------------------------------------

def _int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def stock_facts(food_drink: Any, alive: Any) -> Optional[Dict[str, Any]]:
    """From `stocks.food-drink` (fort-owned units; caravan goods excluded by
    the tool). `drink_per_citizen` is a plain division, one decimal."""
    if not isinstance(food_drink, Mapping):
        return None
    out: Dict[str, Any] = {}
    for bucket in ("drink", "prepared_meals", "raw_edibles"):
        row = food_drink.get(bucket)
        units = _int(row.get("units")) if isinstance(row, Mapping) else None
        if units is not None:
            out[f"{bucket}_units"] = units
            unreachable = _int(row.get("unreachable_units"))
            if unreachable:
                out[f"{bucket}_unreachable_units"] = unreachable
    if not out:
        return None
    citizens = _int(alive)
    if citizens and "drink_units" in out:
        out["drink_per_citizen"] = round(out["drink_units"] / citizens, 1)
    return out


def order_facts(orders_state: Any) -> Optional[Dict[str, Any]]:
    """From the `orders.list` read the cycle already makes. Lists only orders
    not progressing (validated but inactive, or not validated), the same two
    conditions as `conductor/order_watch.py`; the total is always given."""
    if not isinstance(orders_state, Mapping) or not isinstance(orders_state.get("orders"), list):
        return None
    orders = [o for o in orders_state["orders"] if isinstance(o, Mapping)]
    lines = []
    for o in orders:
        validated, active = o.get("validated"), o.get("active")
        if validated is False:
            state = "not validated"
        elif validated is True and active is False:
            state = "validated, not active"
        else:
            continue
        name = str(o.get("job") or o.get("reaction") or "order")
        left, total = _int(o.get("amount_left")), _int(o.get("amount_total"))
        amount = f", {left} of {total} left" if left is not None and total is not None else ""
        lines.append(f"#{o.get('id')} {name} {state}{amount}"[:120])
    out: Dict[str, Any] = {"total": len(orders), "not_progressing": _capped(lines, MAX_ORDER_LINES)}
    if "manager_appointed" in orders_state:
        out["manager_appointed"] = orders_state.get("manager_appointed")
    return out


def availability_line(item_type: str, row: Any) -> Optional[str]:
    """One line from `stocks.availability`: `BARREL: 2 free of 6, 1 in jobs`."""
    if not isinstance(row, Mapping):
        return None
    total, free = _int(row.get("total_units")), _int(row.get("available_units"))
    if total is None or free is None:
        return None
    line = f"{item_type}: {free} free of {total}"
    in_job = _int(row.get("in_job_units"))
    if in_job:
        line += f", {in_job} in jobs"
    return line


def seed_facts(seeds: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(seeds, Mapping):
        return None
    total = _int(seeds.get("total_units"))
    if total is None:
        return None
    by_plant = seeds.get("by_plant_units")
    top: List[str] = []
    if isinstance(by_plant, Mapping):
        ranked = sorted(
            ((str(k), _int(v)) for k, v in by_plant.items() if _int(v) is not None),
            key=lambda kv: (-kv[1], kv[0]),
        )
        top = [f"{name} {n}" for name, n in ranked[:MAX_SEED_PLANTS]]
    return {"total_units": total, "top_plants": top}


def build_facts(
    *, vitals: Mapping[str, Any], food_drink: Any = None, orders_state: Any = None,
    availability: Optional[Mapping[str, Any]] = None, seeds: Any = None,
    want_availability: Sequence[str] = (), want_seeds: bool = False,
) -> Dict[str, Any]:
    """One role's `facts` block. `availability` maps item type to its raw
    `stocks.availability` row; only the types this role asked for
    (`want_availability`, from `policy.yaml`'s `briefing_extras`) are shown.
    Keys with no usable input are omitted."""
    facts: Dict[str, Any] = {}
    stocks = stock_facts(food_drink, vitals.get("alive"))
    if stocks:
        facts["stocks"] = stocks
    orders = order_facts(orders_state)
    if orders:
        facts["orders"] = orders
    lines = [
        line for line in (
            availability_line(t, (availability or {}).get(t)) for t in want_availability
        ) if line
    ]
    if lines:
        facts["availability"] = _capped(lines, MAX_AVAILABILITY_LINES)
    if want_seeds:
        seed = seed_facts(seeds)
        if seed:
            facts["seeds"] = seed
    return facts
