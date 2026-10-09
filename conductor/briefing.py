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
MAX_ORE_LINES = 5
MAX_SPACE_LINES = 3

#: The block's standing instruction (after the stable prefix, before the ask).
FILINGS_NOTE = (
    "Check this before filing. Do not re-file what is accepted or already in a "
    "project; a rejected or deferred one needs a new reason, not a repeat."
)
MAX_FILING_LINES = 30

#: The freeze line (docs/CONDUCTOR-EXECUTION.md 6.6, 2b).
FREEZE_LINE = (
    "Proposals of these types move to exact actions at the next deploy and wait until it. "
    "Skip this work now: do not file proposals of these types."
)


def _field(result: Any, path: str) -> Any:
    node = result
    for part in path.split("."):
        if isinstance(node, list):
            node = node[int(part)]
        elif isinstance(node, Mapping):
            node = node[part]
        else:
            raise TypeError(part)
    return node


def _leaf_default(alert: Any, result: Any) -> Optional[Any]:
    """The alert's `missing_leaf` default, or `None` when it does not apply.
    It applies only to the last path segment: the read must be a mapping with
    no `error` key and the parent of the leaf must exist as a mapping, so an
    error-shaped or malformed result never reads as zero."""
    default = getattr(alert, "missing_leaf", None)
    if default is None or not isinstance(result, Mapping) or "error" in result:
        return None
    parts = alert.field.split(".")
    try:
        parent = _field(result, ".".join(parts[:-1])) if len(parts) > 1 else result
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    if not isinstance(parent, Mapping) or parts[-1] in parent:
        return None
    return default


def evaluate_threshold_alerts(alerts: Sequence[Any], read_results: Mapping[Any, Any], alive: Any) -> List[str]:
    """Alert lines for the thresholds currently crossed. `alerts` are
    `conductor.policy.ThresholdAlert`s; `read_results` maps `alert.name` to the
    parsed result of its read (absent or `None` when the read failed). Total: a
    missing result, a missing field (unless the alert declares a `missing_leaf`
    default and the read is well formed, which then stands in for it), a non-number or an unusable `alive` simply
    drops that alert's line."""
    lines: List[str] = []
    for alert in alerts:
        result = read_results.get(alert.name)
        if result is None:
            continue
        try:
            value = _field(result, alert.field)
        except (KeyError, IndexError):
            value = _leaf_default(alert, result)
            if value is None:
                continue
        except (TypeError, ValueError):
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        measured = float(value)
        per_value: Optional[float] = None
        if alert.per == "alive":
            if isinstance(alive, bool) or not isinstance(alive, (int, float)) or alive <= 0:
                continue
            # Compare the unrounded ratio; round only for the text (21 of 22
            # is 0.95 and must cross below 1).
            measured_for_test = measured / float(alive)
            per_value = round(measured_for_test, 2)
        else:
            measured_for_test = measured
        if measured_for_test < alert.below:
            lines.append(alert.text.format_map({
                "value": value, "per_value": per_value if per_value is not None else value,
                "threshold": alert.below if alert.below != int(alert.below) else int(alert.below),
            }))
    return lines


PAUSED_TAIL = (
    "A paused fort is not broken: no job, haul or crop progresses and no tick passes "
    "until it resumes, so do not read stalled figures as faults."
)


def paused_line(
    clock_status: Optional[Mapping[str, Any]], hold: Any = None, *, still_paused: bool = True,
) -> Optional[str]:
    """One compact line saying the fort is paused at wake time and why, or
    `None` when it is not (or the state is unknown). Reasons come from what the
    cycle already read: an operator hold (with its reason), a latched tripwire
    (which one), a blocking panel (its name), else a plain pause. Total."""
    if not isinstance(clock_status, Mapping) or not still_paused or not clock_status.get("paused"):
        return None
    causes: List[str] = []
    if getattr(hold, "held", False):
        reason = getattr(hold, "reason", None)
        causes.append(f"operator hold ({reason})" if reason else "operator hold")
    tripwire = clock_status.get("tripwire")
    if isinstance(tripwire, Mapping) and tripwire:
        causes.append(f"tripwire stop ({tripwire.get('reason')})")
    panel = clock_status.get("blocking_panel")
    if isinstance(panel, Mapping) and panel.get("name"):
        causes.append(f"blocking panel ({panel.get('name')}) a player must close")
    why = "; ".join(causes) if causes else "plain pause (likely a player or the save)"
    return f"FORT PAUSED: {why}. {PAUSED_TAIL}"[:500]


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
    alerts: Optional[Sequence[str]] = None,
    ore_exposed: Optional[Sequence[str]] = None,
    frozen_types: Optional[Sequence[str]] = None,
    own_filings: Optional[Sequence[str]] = None,
    roadmap_line: Optional[str] = None,
    utilisation: Optional[Mapping[str, Any]] = None,
    paused: Optional[str] = None,
    unused_space: Optional[Sequence[str]] = None,
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
        **(
            {"your_recent_filings": {"note": FILINGS_NOTE, "items": _capped(own_filings, MAX_FILING_LINES)}}
            if own_filings is not None else {}
        ),
        "wake_reason": wake.reason,
        "wake_detail": wake.detail,
        "clock": wake.clock,
        **({"fort_paused": str(paused)} if paused else {}),
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
    if alerts:
        # Only while a policy threshold is crossed; absent otherwise.
        briefing["alerts"] = [str(a)[:200] for a in alerts][:MAX_ALERT_LINES]
    if ore_exposed:
        # One line per standing exposure (handoffs/2026-10-05-ore-exposed-signal.md),
        # only for a role whose lane carries ore; absent when nothing is exposed.
        briefing["ore_exposed"] = _capped([str(s)[:200] for s in ore_exposed], MAX_ORE_LINES)
    if unused_space:
        # Register 2026-10-09: new sizeable dug space nobody uses (conductor/space_watch.py).
        # Information only, never a wake reason; absent when nothing is new.
        briefing["unused_dug_space"] = _capped([str(s)[:220] for s in unused_space], MAX_SPACE_LINES)
    if frozen_types:
        # docs/CONDUCTOR-EXECUTION.md 6.6 (2b): a group frozen ahead of its cutover.
        # Skipped, not refused (the user's call): the role does not file these types.
        briefing["frozen"] = {"types": [str(t) for t in frozen_types][:MAX_QUEUE_IDS], "note": FREEZE_LINE}
    if ledger_digest is not None:
        briefing["ledger"] = _capped(ledger_digest, MAX_LEDGER_ROWS)
    if roadmap_line:
        # Fort roadmap V1: the stage and its top targets, one compact line.
        briefing["roadmap"] = str(roadmap_line)[:MAX_ROADMAP_LINE_CHARS]
    if utilisation:
        # The Planner's learning signal: peak and p90 concurrent sleepers, diners
        # and drinkers per alive citizen over the recent series (conductor/utilisation.py).
        briefing["utilisation"] = dict(utilisation)
    return briefing


# ---------------------------------------------------------------------------
# The Overseer's ruling briefing (docs/CONDUCTOR-EXECUTION.md 3.3)
# ---------------------------------------------------------------------------

MAX_ALERT_LINES = 6
MAX_ROADMAP_LINE_CHARS = 400

#: The ask, last. Cited facts are refreshed by the server; the Overseer judges
#: reasoning and does not re-read them. Until a proposal type is routed to the
#: executor (docs/CONDUCTOR-EXECUTION.md stage 2), nothing else carries out an
#: accepted proposal, so the ask must say to execute it (live 2026-10-05:
#: "stop when each has a ruling" left an accepted brew unexecuted).
RULING_ASK = (
    "Rule on each pending proposal: accept, reject, or defer naming what would "
    "change your mind. Cited facts are checked and refreshed; judge the reasoning. "
    "Then carry out each proposal you accept, following your charter's Execution "
    "steps (queue.project, act, queue.executed with step_id). Stop when each has "
    "a ruling and every accepted one is carried out. On an accept, give an urgency when it is "
    "not normal. Expected about {calls} calls."
)


def routing_from_state(state: Any) -> Optional[Dict[str, List[str]]]:
    """`queue.execution_state`'s optional `routing` block (which proposal types
    the conductor runs, which are still the Overseer's, which are frozen), or
    `None` when the server does not report one: every caller then behaves
    exactly as before routing existed. Total."""
    block = state.get("routing") if isinstance(state, Mapping) else None
    if not isinstance(block, Mapping):
        return None
    out: Dict[str, List[str]] = {}
    for key in ("routed_types", "unrouted_types", "frozen_types"):
        value = block.get(key)
        out[key] = [str(v) for v in value] if isinstance(value, list) else []
    return out


def ruling_ask(routing: Optional[Mapping[str, Sequence[str]]], calls: int) -> str:
    """The ask, last. Without routing it is the original ask. With it, the
    carry-out instruction names only the unrouted types and the routed ones are
    said to be the conductor's (docs/CONDUCTOR-EXECUTION.md 3, P3-M4)."""
    if not routing or not routing.get("routed_types"):
        return RULING_ASK.format(calls=calls)
    routed = ", ".join(routing["routed_types"])
    unrouted = ", ".join(routing.get("unrouted_types") or ())
    out = [
        "Rule on each pending proposal: accept, reject, or defer naming what would "
        "change your mind. Cited facts are checked and refreshed; judge the reasoning."
    ]
    if unrouted:
        out.append(
            f"Then carry out each proposal you accept of type {unrouted}, following your charter's "
            "Execution steps (queue.project, act, queue.executed with step_id)."
        )
    out.append(
        f"Accepted proposals of type {routed} are carried out by the conductor: rule only, and do not "
        "open a project or record execution for them."
    )
    tail = "Stop when each has a ruling" + (" and every accepted one of the other types is carried out." if unrouted else ".")
    out.append(f"{tail} On an accept, give an urgency when it is not normal. Expected about {calls} calls.")
    return " ".join(out)


def _fmt_cited(c: Mapping[str, Any]) -> str:
    args = c.get("args") or {}
    arg_text = ",".join(f"{k}={v}" for k, v in sorted(args.items()))
    name = f"{c.get('tool')}({arg_text}).{c.get('field')}" if arg_text else f"{c.get('tool')}.{c.get('field')}"
    line = f"{name} = {c.get('value')} at tick {c.get('tick')}"
    if "now" in c:
        line += f", now {c['now']}"
    elif c.get("now_unreadable"):
        line += ", now unreadable"
    return line


def build_ruling_briefing(
    *, game_tick: int, wake: Wake, vitals: Mapping[str, Any], alerts: Sequence[str],
    pending_brief: Optional[Mapping[str, Any]], diff_events: Sequence[Mapping[str, Any]] = (),
    stuck_jobs: Sequence[str] = (), to_carry_out: Sequence[str] = (),
    routing: Optional[Mapping[str, Sequence[str]]] = None,
    roadmap_line: Optional[str] = None,
    paused: Optional[str] = None,
) -> str:
    """The Overseer's prompt for an ordinary ruling wake, as text in a fixed
    order, stable material first and the ask last (cache-friendly, bounded):
    header, vitals plus threshold alerts, decided-do-not-redo, pending
    proposals, other open items, the ask. `pending_brief` is
    `queue.pending_brief`'s structured result; `None` (the read failed) is said
    plainly rather than dropped. Pure and total over its inputs."""
    out: List[str] = []
    head = f"WAKE {wake.reason}: {wake.detail}. Game tick {game_tick}. Clock {wake.clock}."
    out.append(head)
    if paused:
        out.append(str(paused))

    v = vitals
    out.append(
        "VITALS alive={a} dead_total={d} worst_hunger={h} worst_thirst={t} warnings={w}".format(
            a=v.get("alive"), d=v.get("dead_total"), h=v.get("worst_hunger_status"),
            t=v.get("worst_thirst_status"), w=v.get("warning_count"),
        )
    )
    for line in list(alerts)[:MAX_ALERT_LINES]:
        out.append(f"ALERT {line}")
    if roadmap_line:
        out.append(str(roadmap_line)[:MAX_ROADMAP_LINE_CHARS])

    out.append("DECIDED, DO NOT REDO")
    proposals: List[Mapping[str, Any]] = []
    if pending_brief is None:
        out.append("  (the queue read failed this cycle; call queue.pending for the proposals)")
    else:
        decided = pending_brief.get("decided") or {}
        projects = decided.get("open_projects") or []
        out.append(f"  Open projects: {decided.get('wip_count', len(projects))}")
        for pr in projects:
            blocker = f"; blocked: {pr['top_blocker']}" if pr.get("top_blocker") else ""
            out.append(f"  - {pr.get('id')} {pr.get('title')}: {pr.get('steps_done')}/{pr.get('steps_total')} steps done{blocker}")
        rulings = decided.get("recent_rulings") or []
        if rulings:
            out.append("  Last rulings:")
            for r in rulings:
                out.append(f"  - {r.get('id')} {r.get('decision')} {r.get('proposal_id')}: {r.get('reason')}")
        proposals = list(pending_brief.get("proposals") or [])

    count = (pending_brief or {}).get("count", 0)
    shown = len(proposals)
    out.append(f"PENDING PROPOSALS ({shown} shown of {count})")
    routed_types = set((routing or {}).get("routed_types") or ())
    for p in proposals:
        pred = p.get("prediction") or {}
        cost = p.get("cost") or {}
        out.append(f"- {p.get('id')} [{p.get('role')}, {p.get('type')}] priority {p.get('priority')}: {p.get('summary')}")
        if p.get("type") in routed_types:
            out.append("  Routed: if you accept it, the conductor runs it. Rule only.")
        out.append(f"  Rationale: {p.get('rationale')}")
        out.append(
            f"  Prediction: {pred.get('signal')} {pred.get('op')} {pred.get('value')} "
            f"within {pred.get('check_after_ticks')} ticks. Cost: {cost.get('estimate')} {cost.get('unit')}."
        )
        for c in p.get("cited") or []:
            out.append(f"  Cites: {_fmt_cited(c)}")
        if p.get("duplicate_of"):
            out.append(f"  Duplicate of {p['duplicate_of']}.")
        if p.get("overlaps"):
            out.append(f"  Overlaps {', '.join(p['overlaps'])}.")

    todo = [str(i) for i in to_carry_out][:MAX_QUEUE_IDS]
    if todo:
        out.append(
            "ACCEPTED, NOT YET CARRIED OUT: " + ", ".join(todo)
            + ". You accepted these; carry each out now (queue.project, act, queue.executed)."
        )

    if routed_types:
        out.append(
            "ACCEPTED ROUTED WORK: " + ", ".join(sorted(routed_types))
            + " proposals you accept are run by the conductor; nothing for you to carry out."
        )

    items: List[str] = []
    for line in list(stuck_jobs)[:MAX_STUCK_JOB_LINES]:
        items.append(f"stuck job: {str(line)[:160]}")
    for ev in list(diff_events)[:MAX_DIFF_EVENTS]:
        items.append(f"event: {str(dict(ev))[:160]}")
    out.append("OTHER OPEN ITEMS" + ("" if items else ": none"))
    out.extend(f"- {i}" for i in items)

    out.append(ruling_ask(routing, max(2, 4 * shown + 2) if shown else 2))
    return "\n".join(out)
