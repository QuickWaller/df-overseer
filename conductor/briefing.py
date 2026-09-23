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

from typing import Any, Dict, Mapping, Optional, Sequence

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
    if ledger_digest is not None:
        briefing["ledger"] = _capped(ledger_digest, MAX_LEDGER_ROWS)
    return briefing
