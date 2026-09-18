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


@dataclass(frozen=True)
class RateResult:
    """`value`: change per tick (`(last - first) / dtick`), `None` when
    unavailable. `sample_count`: how many non-null readings were found in
    the window (not just the two endpoints the slope uses) -- what makes a
    two-point rate visibly weaker than a forty-point one. `tick_span`: the
    number of ticks between the first and last reading actually used.
    `skipped_nulls`: readings in the window excluded because their value was
    `None`. `reason`: required when `status` is `unavailable`."""

    status: str
    value: float | None
    sample_count: int
    tick_span: int | None
    skipped_nulls: int
    reason: str | None = None


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
    reading gives unknown, never a guess."""
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
        )

    ordered = sorted(usable, key=lambda r: r["abs_tick"])
    first, last = ordered[0], ordered[-1]
    tick_span = last["abs_tick"] - first["abs_tick"]
    value = (last["value"] - first["value"]) / tick_span
    return RateResult(
        status=MEASURED, value=value, sample_count=len(usable), tick_span=tick_span,
        skipped_nulls=skipped_nulls, reason=None,
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
