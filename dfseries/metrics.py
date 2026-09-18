"""The metric-kind registry: which metrics are `level` readings and which
are `resetting_counter`s, plus, for each resetting counter, its measured
between-reset rate and the evidence for it, or "not established".

`docs/TIMESERIES.md` "Timers reset: a rate across a reset is meaningless"
found that `thirst_timer`, `hunger_timer` and `sleepiness_timer` are
counters that reset (a drink, a meal, a sleep), not levels, and that
`trend.rate()`'s old endpoint slope produced a confident, meaningless number
across a reset (`unit:192`: -2.133056/tick over the run where it actually
drank once). This module is where that distinction lives so every other
module (`trend.py`'s `resets()` and `rate()`, `aggregate.py`) reads it from
one place instead of re-guessing per call site.

**The key fact, and its limit** (`handoffs/2026-09-19-dfseries-resets.md`):
a timer that rises *exactly* 1 per tick equals "ticks since the last
reset", which is what makes exact-tick reset dating possible. That exactness
is a property of the specific counter, not of "being a resetting counter" in
general, so it must be measured per metric before being relied on --
**a metric-kind entry with `kind=RESETTING_COUNTER` and `rate_per_tick=None`
is exactly as valid an entry as one with a measured rate**; it says "this
resets, but we do not yet know its between-reset rate well enough to date a
reset to an exact tick."

**Unknown metrics default to `LEVEL`** (`kind_of` never raises): a metric
nobody has classified yet is safer treated as an ordinary level, where the
existing endpoint-slope `rate()` behaviour already applies, than silently
assumed to reset.

The evidence strings below were measured against the first real sampler run,
`tl-20260918T213057Z-688464.jsonl` (10 samples, 9 intervals, 23 citizens,
207 citizen-intervals per metric), read-only from the scratchpad per the
handoff -- the file itself is game data and is never committed here.
"""

from __future__ import annotations

from dataclasses import dataclass

LEVEL = "level"
RESETTING_COUNTER = "resetting_counter"


@dataclass(frozen=True)
class MetricKind:
    """`kind`: `LEVEL` or `RESETTING_COUNTER`. `rate_per_tick`: the
    established between-reset rate for a resetting counter, or `None` when
    not established (meaningless for `LEVEL`, always `None` there).
    `evidence`: free text saying how the rate was measured, or why it is not
    established -- every trend output that uses a metric's kind carries this
    through so a caller never has to take the classification on faith."""

    kind: str
    rate_per_tick: float | None
    evidence: str


_NOT_CLASSIFIED = MetricKind(
    kind=LEVEL,
    rate_per_tick=None,
    evidence="not in the registry; unknown metrics default to level, per this module's docstring",
)

REGISTRY: dict[str, MetricKind] = {
    "thirst_timer": MetricKind(
        kind=RESETTING_COUNTER,
        rate_per_tick=1.0,
        evidence=(
            "Measured against tl-20260918T213057Z-688464.jsonl (23 citizens, "
            "9 intervals each, 207 citizen-intervals total): 206 of 207 rose "
            "by exactly the tick gap. The one exception, unit:192 (33722 at "
            "abs_tick 12373406 to 1085 at abs_tick 12374606), is a real drink "
            "dating exactly to abs_tick 12373521 = 12374606 - 1085, and every "
            "other citizen's thirst shows no reset in that window. See "
            "handoffs/2026-09-19-sampler.md and "
            "handoffs/2026-09-19-dfseries-resets.md."
        ),
    ),
    "hunger_timer": MetricKind(
        kind=RESETTING_COUNTER,
        rate_per_tick=1.0,
        evidence=(
            "Measured against the same run: 207 of 207 citizen-intervals rose "
            "by exactly the tick gap, the identical signature thirst_timer "
            "showed on its 206 non-reset intervals. But zero resets occurred "
            "for any citizen in this window, so while the between-reset rate "
            "(1/tick) is as well supported as thirst's, the reset-dating "
            "formula itself (v1 < v0 + dt implies a reset at t1 - v1) has "
            "never been tested against a real hunger reset. Treated as "
            "established by analogy to thirst's identical signature; a "
            "future run that ever produces a hunger reset should be checked "
            "against this formula before it is trusted further."
        ),
    ),
    "sleepiness_timer": MetricKind(
        kind=RESETTING_COUNTER,
        rate_per_tick=None,
        evidence=(
            "Not established -- confirms the handoff's suspicion. In the same "
            "run, sleepiness_timer rises by exactly the tick gap while a "
            "citizen is awake (matching thirst/hunger's signature), but then "
            "*decreases* over one or more later intervals rather than "
            "resetting to a low value in a single tick: unit:192 fell "
            "49168 -> 46048 -> 23248 -> 448 across three consecutive "
            "1200-tick gaps, at -2.6/tick then -19.0/tick then -19.0/tick -- "
            "not a constant rate. This is a sleep-drain dynamic (the timer "
            "eases while asleep rather than snapping to zero), so neither a "
            "single between-reset rate nor exact-tick reset dating applies. "
            "Only interval-bounded reset detection is available for this "
            "metric until its drain dynamics are understood."
        ),
    ),
}


def kind_of(metric: str) -> MetricKind:
    """The `MetricKind` for `metric`. Never raises: an unregistered metric
    gets `_NOT_CLASSIFIED` (kind `LEVEL`), per this module's "unknown
    metrics default to level" rule."""
    return REGISTRY.get(metric, _NOT_CLASSIFIED)
