"""The read side: a subject's series, its latest value, a rate over a
window, and rows shaped for `production/cover.py`.

**Every query here defaults to the current lineage** (`sample_events.
superseded = 0`), per `docs/TIMESERIES.md`: "Trend queries default to the
current lineage. Asking across a superseded branch must be an explicit
choice." Pass `lineage="all"` to reach superseded samples explicitly; there
is no third option, so a caller cannot silently ask for "some" superseded
data.

**Nulls are never silently dropped or treated as zero.** `series()` returns
a null value exactly as stored, with its `error`. `rate()` excludes null
rows from the slope calculation (a null cannot be a point on a line) but
reports how many it excluded, per the handoff: "a rate over a window
containing nulls says how many it skipped."

**A known contract edge case, resolved here and reported rather than
silently guessed at**: at the exact tick where a rollback's successor
timeline begins, "the newest timeline" (full) and "a predecessor's samples
at or before the tick where its successor began" can both contribute a row
for the same subject/metric/abs_tick -- the predecessor's boundary sample
and the successor's own first sample. `docs/TIMESERIES.md` does not say
which wins if they disagree. **This module's policy**: in the default
(`lineage="current"`) view, when two rows tie on `abs_tick`, the row
belonging to the current tip timeline (the one with no successor) wins --
the surviving branch's own reading is preferred over the discarded branch's
last one at that exact instant. `lineage="all"` returns both, undeduplicated,
since it exists precisely to show the raw overlap. See the handoff write-up
for why this was chosen over leaving the tie unresolved.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from . import metrics as metric_kinds


def _lineage_clause(lineage: str) -> str:
    if lineage == "current":
        return "AND e.superseded = 0"
    if lineage == "all":
        return ""
    raise ValueError(f"lineage must be 'current' or 'all', got {lineage!r}")


def _window_clause(start_abs_tick: int | None, end_abs_tick: int | None) -> tuple[str, list]:
    clauses = []
    params: list = []
    if start_abs_tick is not None:
        clauses.append("e.abs_tick >= ?")
        params.append(start_abs_tick)
    if end_abs_tick is not None:
        clauses.append("e.abs_tick <= ?")
        params.append(end_abs_tick)
    return (" AND " + " AND ".join(clauses) if clauses else ""), params


def series(
    conn: sqlite3.Connection, subject: str, metric: str, *,
    start_abs_tick: int | None = None, end_abs_tick: int | None = None,
    lineage: str = "current",
) -> list[dict]:
    """A subject's readings of one metric over a tick window, oldest first.
    Every row: `abs_tick`, `value` (may be `None`), `unit`, `error` (set
    exactly when `value` is `None`), `timeline_id`, `superseded`.

    In the default lineage, a tie at the same `abs_tick` between a
    predecessor's boundary sample and its successor's first sample is
    resolved in favour of the successor (the current tip) -- see this
    module's docstring, "A known contract edge case". `lineage="all"` skips
    this dedup and returns every row."""
    window_sql, window_params = _window_clause(start_abs_tick, end_abs_tick)
    query = (
        "SELECT e.abs_tick, m.value, m.unit, m.error, e.timeline_id, e.superseded, e.id AS event_id, "
        "(t.cutoff_abs_tick IS NULL) AS is_tip "
        "FROM sample_metrics m JOIN sample_events e ON m.event_id = e.id "
        "JOIN timelines t ON e.timeline_id = t.id "
        "WHERE m.subject = ? AND m.metric = ? " + _lineage_clause(lineage) + window_sql +
        " ORDER BY e.abs_tick ASC, e.id ASC"
    )
    rows = conn.execute(query, [subject, metric, *window_params]).fetchall()

    if lineage == "current":
        by_tick: dict[int, list[sqlite3.Row]] = {}
        for r in rows:
            by_tick.setdefault(r["abs_tick"], []).append(r)
        picked = []
        for tick in sorted(by_tick):
            group = by_tick[tick]
            if len(group) == 1:
                picked.append(group[0])
            else:
                tip_rows = [g for g in group if g["is_tip"]]
                picked.append(tip_rows[0] if tip_rows else group[-1])
        rows = picked

    return [
        {
            "abs_tick": r["abs_tick"], "value": r["value"], "unit": r["unit"],
            "error": r["error"], "timeline_id": r["timeline_id"], "superseded": bool(r["superseded"]),
        }
        for r in rows
    ]


def latest(conn: sqlite3.Connection, subject: str, metric: str, *, lineage: str = "current") -> dict | None:
    """The most recent reading (by `abs_tick`) of one metric for one
    subject, or `None` if there is none in this lineage. Built on `series()`
    so it applies the same boundary-tie resolution (see module docstring)."""
    rows = series(conn, subject, metric, lineage=lineage)
    return rows[-1] if rows else None


UNAVAILABLE = "unavailable"
MEASURED = "measured"

EXACT_TICK = "exact_tick"
INTERVAL_BOUNDED = "interval_bounded"


@dataclass(frozen=True)
class ResetEvent:
    """One reset detected between two consecutive readings `(t0, v0)` and
    `(t1, v1)`. `kind`: `EXACT_TICK` when the metric's established
    `rate_per_tick` lets the reset be dated to one tick (`abs_tick` set), or
    `INTERVAL_BOUNDED` when only "a reset happened somewhere in `(t0, t1]`"
    can be said (`abs_tick` is `None`; use `window_start_abs_tick` /
    `window_end_abs_tick`). Per the handoff: "the last one happened at
    exactly `t1 - v1`" for an exact-tick metric -- a gap can contain more
    than one reset, and only the last is dated; earlier ones in the same gap
    are not separately reported, since nothing in a two-point reading can
    distinguish them."""

    subject: str
    metric: str
    kind: str
    abs_tick: int | None
    window_start_abs_tick: int
    window_end_abs_tick: int
    from_value: float
    to_value: float


@dataclass(frozen=True)
class Anomaly:
    """A reading that is impossible for an established resetting counter:
    it rose by *more* than its established rate over the gap, which a
    reset-only counter can never do. Reported, never absorbed into a
    reset event or silently dropped -- only possible when the metric's rate
    is established, since without a known rate nothing is "impossible"."""

    subject: str
    metric: str
    window_start_abs_tick: int
    window_end_abs_tick: int
    from_value: float
    to_value: float
    reason: str


@dataclass(frozen=True)
class ResetsResult:
    """`docs/TIMESERIES.md`-facing states-its-assumption output: every field
    needed to know what was assumed about `metric` before trusting
    `events`. `metric_kind`: `metrics.LEVEL` or `metrics.RESETTING_COUNTER`
    (a `LEVEL` metric always returns empty `events`/`anomalies` -- resets
    are not a concept that applies to it). `rate_per_tick` /
    `rate_evidence`: carried straight from the registry so a caller never
    has to look it up separately."""

    metric_kind: str
    rate_per_tick: float | None
    rate_evidence: str
    events: list[ResetEvent]
    anomalies: list[Anomaly]


def resets(
    conn: sqlite3.Connection, subject: str, metric: str, *,
    start_abs_tick: int | None = None, end_abs_tick: int | None = None,
    lineage: str = "current",
) -> ResetsResult:
    """Reset events for one subject's metric over a window, per
    `docs/TIMESERIES.md` "Timers reset" and the handoff's key fact:

    - `v1 == v0 + rate*(t1-t0)`: no reset (only checked when `rate` is
      established).
    - `v1 < v0 + rate*(t1-t0)`: at least one reset, the last dated to
      exactly `t1 - v1/rate` (an `EXACT_TICK` event).
    - `v1 > v0 + rate*(t1-t0)`: impossible for the counter; reported as an
      `Anomaly`, never absorbed into `events`.

    When the metric's rate is **not established** (`metrics.kind_of(...)
    .rate_per_tick is None`), none of the above can be computed -- there is
    no "expected" value to compare against. The only signal available
    without a known rate is an outright decrease (`v1 < v0`), which is
    reported as an `INTERVAL_BOUNDED` event ("a reset somewhere in
    `(t0, t1]`"), never dated to a tick. A rise, even a slow one, says
    nothing either way for an unestablished metric and produces neither an
    event nor an anomaly -- there is no basis to call it either.

    Null readings are excluded first (a null is not a point on this line,
    same rule as `rate()`). A `LEVEL` metric always returns empty
    `events`/`anomalies`: resets are not a concept that applies to it."""
    mk = metric_kinds.kind_of(metric)
    if mk.kind == metric_kinds.LEVEL:
        return ResetsResult(
            metric_kind=mk.kind, rate_per_tick=mk.rate_per_tick, rate_evidence=mk.evidence,
            events=[], anomalies=[],
        )

    rows = series(conn, subject, metric, start_abs_tick=start_abs_tick, end_abs_tick=end_abs_tick, lineage=lineage)
    usable = sorted((r for r in rows if r["value"] is not None), key=lambda r: r["abs_tick"])

    events: list[ResetEvent] = []
    anomalies: list[Anomaly] = []

    for a, b in zip(usable, usable[1:]):
        t0, v0 = a["abs_tick"], a["value"]
        t1, v1 = b["abs_tick"], b["value"]
        dt = t1 - t0
        if dt == 0:
            continue  # two readings at the same tick (a lineage-boundary tie already resolved by series()) is not a gap to reason over

        if mk.rate_per_tick is not None:
            expected = v0 + mk.rate_per_tick * dt
            if v1 == expected:
                continue
            if v1 < expected:
                # Detection uses the established rate. Dating to one tick
                # also needs reset-to-zero verified for this metric; without
                # it the event is honestly bounded to the interval.
                if mk.reset_to_zero_verified:
                    reset_tick = round(t1 - v1 / mk.rate_per_tick)
                    events.append(ResetEvent(
                        subject=subject, metric=metric, kind=EXACT_TICK, abs_tick=reset_tick,
                        window_start_abs_tick=t0, window_end_abs_tick=t1, from_value=v0, to_value=v1,
                    ))
                else:
                    events.append(ResetEvent(
                        subject=subject, metric=metric, kind=INTERVAL_BOUNDED, abs_tick=None,
                        window_start_abs_tick=t0, window_end_abs_tick=t1, from_value=v0, to_value=v1,
                    ))
            else:
                anomalies.append(Anomaly(
                    subject=subject, metric=metric,
                    window_start_abs_tick=t0, window_end_abs_tick=t1, from_value=v0, to_value=v1,
                    reason=(
                        f"value rose from {v0} to {v1} over {dt} tick(s), more than the "
                        f"established rate of {mk.rate_per_tick}/tick allows without a reset -- "
                        f"impossible for a resetting counter, never absorbed as a reset"
                    ),
                ))
        else:
            if v1 < v0:
                events.append(ResetEvent(
                    subject=subject, metric=metric, kind=INTERVAL_BOUNDED, abs_tick=None,
                    window_start_abs_tick=t0, window_end_abs_tick=t1, from_value=v0, to_value=v1,
                ))
            # v1 >= v0 with no established rate: no basis to call this a
            # reset or rule one out, so neither an event nor an anomaly.

    return ResetsResult(
        metric_kind=mk.kind, rate_per_tick=mk.rate_per_tick, rate_evidence=mk.evidence,
        events=events, anomalies=anomalies,
    )


@dataclass(frozen=True)
class RateResult:
    """`value`: change per tick (`(last - first) / dtick`), `None` when
    unavailable. `sample_count`: how many non-null readings were found in
    the window (not just the two endpoints the slope uses) -- what makes a
    two-point rate visibly weaker than a forty-point one. `tick_span`: the
    number of ticks between the first and last reading actually used.
    `skipped_nulls`: readings in the window excluded because their value was
    `None`. `reason`: required when `status` is `unavailable`.

    `metric_kind`: `metrics.LEVEL` or `metrics.RESETTING_COUNTER` -- every
    result states which kind it assumed, per the handoff. `segment`: `None`
    for a `LEVEL` metric or an unavailable result; for a resetting counter,
    `"endpoint"` when the window contained no reset (the endpoint slope
    *is* the between-reset slope there) or `"between_reset"` when a reset
    was found and the value was recomputed from after the last one --
    `rate()` never returns the raw endpoint slope across a reset, per the
    handoff's "never the endpoint slope". `used_start_abs_tick`: the
    `abs_tick` the returned slope actually starts from, which differs from
    the window's own `start_abs_tick` exactly when `segment ==
    "between_reset"`."""

    status: str
    value: float | None
    sample_count: int
    tick_span: int | None
    skipped_nulls: int
    reason: str | None = None
    metric_kind: str = metric_kinds.LEVEL
    segment: str | None = None
    used_start_abs_tick: int | None = None


def rate(
    conn: sqlite3.Connection, subject: str, metric: str, *,
    start_abs_tick: int | None = None, end_abs_tick: int | None = None,
    lineage: str = "current",
) -> RateResult:
    """A rate over a window, defaulting to the current lineage so a rate
    computed across a rollback (mixing a superseded branch with its
    successor) never happens by default -- the handoff's own required test.
    Needs at least two readings at distinct `abs_tick` with a non-null
    value; with fewer, returns `UNAVAILABLE`, same rule
    `production/cover.py.depletion_rate_per_day` already applies: one
    reading gives unknown, never a guess.

    **For a `resetting_counter` metric** (`metrics.kind_of(metric).kind`),
    this refuses to let the endpoint slope straddle a reset
    (`docs/TIMESERIES.md` "Timers reset: a rate across a reset is
    meaningless"). If `resets()` finds no reset in the window, the endpoint
    slope is safe and is returned as-is (`segment="endpoint"`). If it finds
    one or more, the raw endpoint slope is never returned: this recomputes
    the slope using only the readings from the last reset's `abs_tick`
    onward (`segment="between_reset"`), or, if fewer than two such readings
    remain, returns `UNAVAILABLE` with a reason naming the reset and
    pointing at `resets()`. `LEVEL` metrics (and any not in the registry)
    keep the original endpoint-slope behaviour unchanged, `segment=
    "endpoint"`."""
    mk = metric_kinds.kind_of(metric)
    rows = series(conn, subject, metric, start_abs_tick=start_abs_tick, end_abs_tick=end_abs_tick, lineage=lineage)
    skipped_nulls = sum(1 for r in rows if r["value"] is None)
    usable = [r for r in rows if r["value"] is not None]
    distinct_ticks = sorted({r["abs_tick"] for r in usable})

    if len(distinct_ticks) < 2:
        return RateResult(
            status=UNAVAILABLE, value=None, sample_count=len(usable), tick_span=None,
            skipped_nulls=skipped_nulls,
            reason=(
                f"{len(usable)} non-null reading(s) at {len(distinct_ticks)} distinct abs_tick "
                f"in this window; a rate needs two at different abs_tick "
                f"({skipped_nulls} null reading(s) skipped)."
            ),
            metric_kind=mk.kind,
        )

    if mk.kind != metric_kinds.RESETTING_COUNTER:
        ordered = sorted(usable, key=lambda r: r["abs_tick"])
        first, last = ordered[0], ordered[-1]
        tick_span = last["abs_tick"] - first["abs_tick"]
        value = (last["value"] - first["value"]) / tick_span
        return RateResult(
            status=MEASURED, value=value, sample_count=len(usable), tick_span=tick_span,
            skipped_nulls=skipped_nulls, reason=None,
            metric_kind=mk.kind, segment="endpoint", used_start_abs_tick=first["abs_tick"],
        )

    # resetting_counter: refuse to straddle a reset.
    reset_result = resets(conn, subject, metric, start_abs_tick=start_abs_tick, end_abs_tick=end_abs_tick, lineage=lineage)
    ordered = sorted(usable, key=lambda r: r["abs_tick"])
    first, last = ordered[0], ordered[-1]

    if not reset_result.events:
        tick_span = last["abs_tick"] - first["abs_tick"]
        value = (last["value"] - first["value"]) / tick_span
        return RateResult(
            status=MEASURED, value=value, sample_count=len(usable), tick_span=tick_span,
            skipped_nulls=skipped_nulls, reason=None,
            metric_kind=mk.kind, segment="endpoint", used_start_abs_tick=first["abs_tick"],
        )

    last_event = reset_result.events[-1]
    if last_event.kind == EXACT_TICK:
        where = f"a reset at abs_tick {last_event.abs_tick}"
        segment_start = last_event.abs_tick
    else:
        where = f"a reset somewhere between abs_tick {last_event.window_start_abs_tick} and {last_event.window_end_abs_tick}"
        segment_start = last_event.window_end_abs_tick

    segment_rows = [r for r in ordered if r["abs_tick"] >= segment_start]
    segment_ticks = sorted({r["abs_tick"] for r in segment_rows})

    if len(segment_ticks) < 2:
        return RateResult(
            status=UNAVAILABLE, value=None, sample_count=len(usable), tick_span=None,
            skipped_nulls=skipped_nulls,
            reason=(
                f"window contains {where}; the endpoint slope would straddle it "
                f"(never returned for a resetting counter -- see resets()), and too few "
                f"readings remain after the reset for a between-reset slope instead."
            ),
            metric_kind=mk.kind,
        )

    seg_first, seg_last = segment_rows[0], segment_rows[-1]
    tick_span = seg_last["abs_tick"] - seg_first["abs_tick"]
    value = (seg_last["value"] - seg_first["value"]) / tick_span
    return RateResult(
        status=MEASURED, value=value, sample_count=len(segment_rows), tick_span=tick_span,
        skipped_nulls=skipped_nulls,
        reason=(
            f"window contains {where}; this is the between-reset slope from abs_tick "
            f"{seg_first['abs_tick']} onward, not the endpoint slope (see resets())."
        ),
        metric_kind=mk.kind, segment="between_reset", used_start_abs_tick=seg_first["abs_tick"],
    )


def cover_rows(
    conn: sqlite3.Connection, subject: str, metric: str, *,
    start_abs_tick: int | None = None, end_abs_tick: int | None = None,
    lineage: str = "current",
) -> list[dict]:
    """Rows shaped for `production.cover.depletion_rate_per_day`, which
    reads `subject_id`, `metric`, `abs_tick` and `value` from each row and
    subtracts values directly -- so a `None` value must never reach it. Null
    readings and superseded samples (by default) are excluded here rather
    than left for the caller to filter."""
    rows = series(conn, subject, metric, start_abs_tick=start_abs_tick, end_abs_tick=end_abs_tick, lineage=lineage)
    return [
        {"subject_id": subject, "metric": metric, "abs_tick": r["abs_tick"], "value": r["value"], "unit": r["unit"]}
        for r in rows
        if r["value"] is not None
    ]
