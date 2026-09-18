"""Fort-level aggregates built on top of `trend.py`'s per-subject reset
detection.

The handoff's deliverable 4: reset events per dwarf-day, aggregated across
every `unit:*` subject for one metric over a window. For `thirst_timer` this
is **drinking events per dwarf-day**, the demand-side figure
`production/cover.py` has wanted since the start and never had
(`docs/PRODUCTION-MODEL.md`). Named drinking **events**, not drink
**consumption**, deliberately: a thirst reset says only that the dwarf's
timer reset, never whether the dwarf drank water or booze, and never how
much.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from . import metrics as metric_kinds
from . import trend

# 1 game day, `docs/TIMESERIES.md` "Sample interval". Duplicated from
# `production/cover.py.TICKS_PER_DAY` rather than imported, so dfseries
# carries no runtime dependency on production/ -- the two packages'
# databases must never share a lifecycle (`dfseries/schema.py`'s module
# docstring), and importing across that boundary for one constant is not
# worth coupling the two.
TICKS_PER_DAY = 1200

_EVENT_LABELS = {
    "thirst_timer": "drinking events per dwarf-day",
}


def _label_for(metric: str) -> str:
    return _EVENT_LABELS.get(metric, f"{metric} reset events per dwarf-day")


@dataclass(frozen=True)
class DwarfDayRate:
    """`event_count`: total reset events (exact-tick plus interval-bounded)
    across every `unit:*` subject observed. `exact_tick_events` /
    `interval_bounded_events`: the same total split by kind -- an
    exact-tick count is a stronger claim than an interval-bounded one and a
    caller should be able to tell them apart rather than see one blended
    number. `anomaly_count`: reported alongside, never folded into
    `event_count` (an anomaly is not a reset). `subjects_observed`: how many
    distinct `unit:*` subjects had at least one non-null reading of `metric`
    in the window. `dwarf_days_observed`: the sum, across those subjects, of
    each one's own observed tick span (last usable reading's `abs_tick`
    minus first) divided by `TICKS_PER_DAY` -- not calendar days elapsed,
    and not population times window length, so a subject with only one
    reading (or none) contributes zero rather than a full day.
    `events_per_dwarf_day`: `None` when `dwarf_days_observed` is zero
    (never a division by zero, never a guess in its place)."""

    metric: str
    metric_kind: str
    rate_per_tick: float | None
    label: str
    event_count: int
    exact_tick_events: int
    interval_bounded_events: int
    anomaly_count: int
    subjects_observed: int
    dwarf_days_observed: float
    events_per_dwarf_day: float | None


def _unit_subjects(
    conn: sqlite3.Connection, metric: str, *,
    start_abs_tick: int | None, end_abs_tick: int | None, lineage: str,
) -> list[str]:
    """Every distinct `unit:*` subject with at least one row for `metric` in
    the window and lineage. Queries `sample_metrics`/`sample_events`
    directly rather than going through `trend.series()` per candidate
    subject, since this step only needs the subject list, not values."""
    clauses = ["m.metric = ?", "m.subject LIKE 'unit:%'"]
    params: list = [metric]
    if lineage == "current":
        clauses.append("e.superseded = 0")
    elif lineage != "all":
        raise ValueError(f"lineage must be 'current' or 'all', got {lineage!r}")
    if start_abs_tick is not None:
        clauses.append("e.abs_tick >= ?")
        params.append(start_abs_tick)
    if end_abs_tick is not None:
        clauses.append("e.abs_tick <= ?")
        params.append(end_abs_tick)

    query = (
        "SELECT DISTINCT m.subject FROM sample_metrics m "
        "JOIN sample_events e ON m.event_id = e.id "
        "WHERE " + " AND ".join(clauses)
    )
    rows = conn.execute(query, params).fetchall()
    return sorted(r["subject"] for r in rows)


def dwarf_day_reset_rate(
    conn: sqlite3.Connection, metric: str, *,
    start_abs_tick: int | None = None, end_abs_tick: int | None = None,
    lineage: str = "current",
) -> DwarfDayRate:
    """Reset events for `metric`, aggregated across every `unit:*` subject
    in the window, divided by citizen-days observed. Built entirely on
    `trend.series()` and `trend.resets()` per subject -- this module adds
    no new reset-detection logic of its own, only the aggregation across
    subjects. See `DwarfDayRate` for what each field means."""
    mk = metric_kinds.kind_of(metric)
    subjects = _unit_subjects(
        conn, metric, start_abs_tick=start_abs_tick, end_abs_tick=end_abs_tick, lineage=lineage,
    )

    exact = 0
    interval = 0
    anomaly_count = 0
    dwarf_days = 0.0
    subjects_observed = 0

    for subject in subjects:
        rows = trend.series(
            conn, subject, metric, start_abs_tick=start_abs_tick, end_abs_tick=end_abs_tick, lineage=lineage,
        )
        usable_ticks = sorted(r["abs_tick"] for r in rows if r["value"] is not None)
        if not usable_ticks:
            continue
        subjects_observed += 1
        dwarf_days += (usable_ticks[-1] - usable_ticks[0]) / TICKS_PER_DAY

        result = trend.resets(
            conn, subject, metric, start_abs_tick=start_abs_tick, end_abs_tick=end_abs_tick, lineage=lineage,
        )
        for event in result.events:
            if event.kind == trend.EXACT_TICK:
                exact += 1
            else:
                interval += 1
        anomaly_count += len(result.anomalies)

    event_count = exact + interval
    events_per_dwarf_day = (event_count / dwarf_days) if dwarf_days > 0 else None

    return DwarfDayRate(
        metric=metric, metric_kind=mk.kind, rate_per_tick=mk.rate_per_tick, label=_label_for(metric),
        event_count=event_count, exact_tick_events=exact, interval_bounded_events=interval,
        anomaly_count=anomaly_count, subjects_observed=subjects_observed,
        dwarf_days_observed=dwarf_days, events_per_dwarf_day=events_per_dwarf_day,
    )
