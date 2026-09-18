"""The days-of-cover calculator: `docs/PRODUCTION-MODEL.md` §1 question 2,
§3, §10, §11; `handoffs/2026-09-18-days-of-cover.md`.

**A pure function over a snapshot plus doctrine-sourced targets, no live
calls inside** -- the same boundary `blocker.py` establishes (that module's
own docstring, and this one's handoff, "The caller assembles the snapshot").
The caller reads DFHack, nets stock, reads two `production_observation` rows
and hands them in; this module only does arithmetic over already-assembled
facts.

## What this answers, and how honestly

**Cover, in dwarf-days**, not days. Stock (a netted count, never total --
spec §7's four deductions) divided by a **measured per-dwarf consumption
rate**, in dwarf-days so a population change rescales the *interpretation*
of that figure without the rate ever needing to be re-measured
(`doctrine/seed.yaml` `cover-target-migration-headroom`: "Express cover in
dwarf-days, not days, so a population jump rescales the target
automatically without the formula itself ever reading population"). See
`days_at_population` below for exactly where population is allowed to enter.

**The rate needs two `production_observation` rows for the same subject and
metric at different `abs_tick`.** One observation is not enough, and the
answer to "not enough" is `unavailable`, never a per-dwarf wiki figure
substituted in its place -- a wiki number would be a `prior` masquerading as
a `measured` fact, and would hide that nobody has taken a second reading.
The handoff's own word for this state is "unknown"; this module has no
separate status for it, because the schema's vocabulary
(`schema.STATUS_VALUES`) has exactly four values and "a fact no file/read
states" is `schema.UNAVAILABLE` by definition (`schema.py` module
docstring). "Unknown" and `UNAVAILABLE` are the same thing here.

**Durable stock is split from perishable**, per `doctrine/seed.yaml`
`durability-splits-cover-target`: one blended number hides that part of the
stock is already flagged rotten. `production_node.durability` (Q1, raw- or
doctrine-classified) says which bucket a node falls in; a live `rotten` flag
per item (already surfaced by `df-overseer-stocks.lua`, per that doctrine
entry) says whether a *perishable* unit still counts as available cover.
Rotten stock is reported, never silently dropped and never silently counted.

**The resupply lead-time term is honestly unavailable.** Spec §11: plump
helmet's `growdur` reads 300 while live `grow_counter` values run in the tens
of thousands, so the tick unit relating the two is unsettled (candidates: a
quarter of a day, two and a half days, 250 days -- nothing read so far
settles which). `resupply_lead_time_days` below always returns
`UNAVAILABLE`, on purpose, regardless of what it is handed. When
`handoffs/2026-09-18-supervised-run-and-measure.md` settles the unit, this
function's body changes to a real conversion and returns `MEASURED`; nothing
else in this module needs to change, because every caller already treats a
`Figure` as something that might be unavailable.

**Every term is a `Figure`**: `status` (one of `schema.STATUS_VALUES`),
`value` (whatever this term means -- a rate, a day count, a band name -- or
`None` when unavailable), and `reason` (required when unavailable, optional
context otherwise). `compute_cover_report` never raises for a data gap: it
always returns a `CoverReport`, with individual `Figure`s reading
`unavailable` where the data does not support a number.

**Targets are never a constant in this file.** `CoverTargets` is supplied by
the caller, sourced from `doctrine/seed.yaml` (`material-policy-bands`,
`cover-target-migration-headroom`) -- this module holds no day count, no
percentage, and no wiki figure of its own. Bands are compared
lexicographically (`material-policy-bands`: "Bands are lexicographic, not
weighted"), never blended into one score.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from . import schema
from .blocker import DEDUCTION_FLAGS

# ---- engine constant, not a policy number (spec sec11, confirmed live) --------
#
# "1,200 ticks a day, 33,600 a month, 403,200 a year", confirmed live against
# announcement timestamps. This is a Q1 engine fact, the same kind of number
# `schema.TICKS_PER_YEAR` already hardcodes -- not a doctrine-owned target,
# so it belongs in code the same way that one does.

TICKS_PER_DAY = 1200


# ---- the universal result shape -------------------------------------------------


@dataclass(frozen=True)
class Figure:
    """One term in a cover report. `status` is always one of
    `schema.STATUS_VALUES`; `value` is `None` exactly when `status` is
    `schema.UNAVAILABLE` (never a placeholder number); `reason` explains an
    unavailable figure and may add context to an available one."""

    status: str
    value: Any = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in schema.STATUS_VALUES:
            raise ValueError(f"status: {self.status!r} is not in {schema.STATUS_VALUES}")
        if self.status == schema.UNAVAILABLE and self.value is not None:
            raise ValueError("an unavailable Figure must carry value=None, never a number")


def _unavailable(reason: str) -> Figure:
    return Figure(status=schema.UNAVAILABLE, value=None, reason=reason)


# ---- stock: netted and split, never total (spec sec7, doctrine durability-splits-cover-target) --


@dataclass(frozen=True)
class StockSplit:
    """Available (netted) stock, split by durability and, within
    perishable, by whether it is already flagged rotten. `available`
    (`Figure`-free, plain ints -- these are exact Q3 counts, not measured
    rates) never includes an item carrying any of `blocker.DEDUCTION_FLAGS`,
    and perishable-rotten items are counted here but never folded into
    `perishable_available`."""

    durable_available: int
    perishable_available: int      # perishable, netted, NOT flagged rotten
    perishable_rotten: int         # perishable, netted, flagged rotten -- reported, never hidden
    unclassified: int              # netted stock whose node has no durability classification at all

    @property
    def total_available(self) -> int:
        return self.durable_available + self.perishable_available


def split_stock(items: Iterable[Mapping], durability_by_node: Mapping[str, str]) -> StockSplit:
    """`items`: item-shaped dicts, the same shape `blocker.available_quantity`
    reads (may carry `in_job` / `owned` / `forbid` / `trader`, plus `node_id`
    and `rotten`). `durability_by_node`: `production_node.id` ->
    `schema.DURABLE`/`schema.PERISHABLE`, a simple projection of
    `production_node` rows the caller already has; this function does not
    need the full process/flow graph `blocker.ProductionGraph` carries, only
    this one column. No live call: every flag is already read."""
    durable = perishable_good = perishable_rotten = unclassified = 0
    for item in items:
        if any(item.get(flag) for flag in DEDUCTION_FLAGS):
            continue
        durability = durability_by_node.get(item.get("node_id"))
        if durability == schema.DURABLE:
            durable += 1
        elif durability == schema.PERISHABLE:
            if item.get("rotten"):
                perishable_rotten += 1
            else:
                perishable_good += 1
        else:
            unclassified += 1
    return StockSplit(
        durable_available=durable, perishable_available=perishable_good,
        perishable_rotten=perishable_rotten, unclassified=unclassified,
    )


# ---- rate: two observations or unavailable, never a wiki fallback -----------------


def depletion_rate_per_day(observations: Iterable[Mapping]) -> Figure:
    """`observations`: `production_observation`-shaped rows (needs
    `abs_tick` and `value`), already filtered by the caller to one
    `subject_id` and `metric=schema.METRIC_STOCK` -- this function does not
    query or filter, same boundary as everywhere else in this module.
    Returns units of stock lost per day, positive when stock is falling
    (`schema.MEASURED`). With fewer than two rows at distinct `abs_tick`,
    returns `schema.UNAVAILABLE`: **one observation gives unknown, not a
    wiki fallback** (handoff). Mixing rows from more than one subject or
    metric is a caller bug, not a data gap, so that raises rather than
    quietly averaging across incompatible series."""
    rows = list(observations)
    subjects = {r["subject_id"] for r in rows if "subject_id" in r}
    metrics = {r["metric"] for r in rows if "metric" in r}
    if len(subjects) > 1 or len(metrics) > 1:
        raise ValueError(
            f"depletion_rate_per_day expects rows for one subject and one "
            f"metric; got subjects={subjects!r} metrics={metrics!r}. The "
            "caller must filter before calling -- this function does not "
            "query the store."
        )
    distinct_ticks = {r["abs_tick"] for r in rows}
    if len(distinct_ticks) < 2:
        return _unavailable(
            f"{len(rows)} production_observation row(s) at {len(distinct_ticks)} "
            "distinct abs_tick; a rate needs two rows at different abs_tick. "
            "One observation gives unknown, not a wiki fallback."
        )
    ordered = sorted(rows, key=lambda r: r["abs_tick"])
    first, last = ordered[0], ordered[-1]
    dtick = last["abs_tick"] - first["abs_tick"]
    rate_per_tick = (first["value"] - last["value"]) / dtick
    return Figure(status=schema.MEASURED, value=rate_per_tick * TICKS_PER_DAY)


def per_dwarf_consumption_rate(rate: Figure, population_at_measurement: int | None) -> Figure:
    """Normalises a measured total depletion rate to a per-dwarf figure
    using the headcount at the time the two observations were taken (an
    exact Q3 read, `schema.METRIC_POPULATION`) -- **not** whatever the
    population is now; see `days_at_population` for where "now" enters.
    Propagates `rate`'s own status/reason unchanged when `rate` is not
    `measured`, so a missing second observation stays visible all the way
    through the report rather than being swallowed here."""
    if rate.status != schema.MEASURED:
        return rate
    if not population_at_measurement or population_at_measurement <= 0:
        return _unavailable(
            "a per-dwarf rate needs the headcount at the time of measurement, "
            f"and none usable was given (got {population_at_measurement!r})"
        )
    return Figure(status=schema.MEASURED, value=rate.value / population_at_measurement)


# ---- cover: dwarf-days, population-free by construction --------------------------


def cover_dwarf_days(available: int, rate: Figure) -> Figure:
    """`available / per-dwarf-rate`, in dwarf-days. Never reads a
    population figure -- that is the entire point of the dwarf-days unit
    (`cover-target-migration-headroom`). A non-positive rate (net stock
    growing, or flat) is reported as unbounded cover rather than a negative
    or infinite-looking day count that would read as a bug."""
    if rate.status != schema.MEASURED:
        return Figure(status=rate.status, value=None, reason=rate.reason)
    if rate.value <= 0:
        return Figure(
            status=schema.MEASURED, value=math.inf,
            reason="stock is not depleting at the last measured rate (rate <= 0/day)",
        )
    return Figure(status=schema.MEASURED, value=available / rate.value)


def days_at_population(cover: Figure, current_population: int | None) -> Figure:
    """The one place *today's* population is allowed to enter: converts a
    population-invariant dwarf-days cover figure into "how many days, for
    us, right now" by dividing by the current headcount. This is exactly
    the rescale the dwarf-days unit buys -- call this again with a new
    `current_population` and the answer updates correctly with **no**
    re-measurement of the underlying rate (`cover_dwarf_days` above never
    touched population at all)."""
    if cover.status != schema.MEASURED or not isinstance(cover.value, (int, float)):
        return Figure(status=cover.status, value=None, reason=cover.reason)
    if not current_population or current_population <= 0:
        return _unavailable(
            "current population is required to convert dwarf-days cover into "
            f"days; none usable was given (got {current_population!r})"
        )
    if math.isinf(cover.value):
        return Figure(status=schema.MEASURED, value=math.inf, reason=cover.reason)
    return Figure(status=schema.MEASURED, value=cover.value / current_population)


# ---- the term that is not computable yet: spec sec11 -----------------------------


def resupply_lead_time_days(growdur_ticks: float | None = None, grow_counter_ticks: float | None = None) -> Figure:
    """Deliberately ignores both arguments. `growdur` reads 300 for plump
    helmet on this install while live `grow_counter` values sit in the tens
    of thousands (18480, 18481, 18482, 21036), so the tick unit relating the
    two is unsettled; candidate conversions put a plump helmet's growth at a
    quarter of a day, two and a half days, or 250 days, and nothing read so
    far settles which (spec §11). **Do not pick one, do not use a wiki
    figure, do not interpolate** -- those are the handoff's own words. This
    function accepts the figures it will eventually convert so its call
    sites do not need to change shape once
    `handoffs/2026-09-18-supervised-run-and-measure.md` settles the unit;
    only this function's body will, and it will then return `MEASURED`."""
    return _unavailable(
        "growdur=300 vs live grow_counter values in the tens of thousands: the "
        "tick unit relating them is unsettled (candidates: a quarter day, 2.5 "
        "days, 250 days; spec PRODUCTION-MODEL.md §11). Needs a grow_counter "
        "read across two known ticks on a real crop to settle -- no conversion "
        "may be picked here."
    )


# ---- targets and the verdict: doctrine, never a constant here --------------------

BELOW_RESERVE_FLOOR = "below_reserve_floor"
BELOW_TARGET = "below_target"
ABOVE_TARGET = "above_target"
VERDICT_BANDS = (BELOW_RESERVE_FLOOR, BELOW_TARGET, ABOVE_TARGET)


@dataclass(frozen=True)
class CoverTargets:
    """Reserve floor and cover target, both in dwarf-days, so they compare
    directly against `cover_dwarf_days`'s output with no population term on
    either side. **The caller sources these two numbers from
    `doctrine/seed.yaml`** (`material-policy-bands` for the band shape,
    `cover-target-migration-headroom` for the >=50% migration-headroom
    padding that the cover target itself should already include) -- this
    dataclass is a plain carrier, and this module writes no day count or
    percentage of its own into either field."""

    reserve_floor_dwarf_days: float
    cover_target_dwarf_days: float


def classify_cover(cover: Figure, targets: CoverTargets) -> Figure:
    """Lexicographic, per `material-policy-bands`: below the reserve floor
    overrides even survival and is reported as such regardless of how close
    to target the figure otherwise is; there is no blended score. Below a
    non-measured `cover` (e.g. the rate was unavailable), the verdict
    itself is unavailable too -- a band cannot be named without a number."""
    if cover.status != schema.MEASURED or not isinstance(cover.value, (int, float)):
        return Figure(
            status=cover.status, value=None,
            reason=cover.reason or "cover is not a measured figure; no verdict can be given",
        )
    if cover.value < targets.reserve_floor_dwarf_days:
        band = BELOW_RESERVE_FLOOR
    elif cover.value < targets.cover_target_dwarf_days:
        band = BELOW_TARGET
    else:
        band = ABOVE_TARGET
    return Figure(status=schema.MEASURED, value=band)


# ---- the report -------------------------------------------------------------------


@dataclass(frozen=True)
class CoverReport:
    """Every term status-carrying (spec §4); nothing here is a bare number
    without provenance. Produced only by `compute_cover_report`, which never
    raises for a data gap -- individual `Figure`s read `unavailable`
    instead, and the report is still useful for whatever *is* measured."""

    subject: str
    stock: StockSplit
    consumption_per_dwarf_per_day: Figure
    total_cover_dwarf_days: Figure
    durable_cover_dwarf_days: Figure
    perishable_cover_dwarf_days: Figure
    days_at_current_population: Figure
    resupply_lead_time_days: Figure
    verdict: Figure


def compute_cover_report(
    subject: str,
    items: Iterable[Mapping],
    durability_by_node: Mapping[str, str],
    observations: Iterable[Mapping],
    targets: CoverTargets,
    *,
    population_at_measurement: int | None = None,
    current_population: int | None = None,
) -> CoverReport:
    """The one entry point. Pure: every input is already-assembled data (an
    item list, a durability projection, a pair of `production_observation`
    rows, doctrine-sourced targets, two population reads) and every output
    is a `CoverReport` -- no DFHack call, no coordinate, and no exception
    for a data gap. `population_at_measurement` and `current_population` are
    deliberately two separate parameters: the first only normalises the
    measured rate (fixed at measurement time), the second only converts the
    resulting population-invariant dwarf-days figure into "days, for us,
    right now" (`days_at_population`) -- conflating them would make the
    dwarf-days figure re-depend on population, defeating the whole point of
    the unit."""
    stock = split_stock(items, durability_by_node)
    total_rate = depletion_rate_per_day(list(observations))
    rate = per_dwarf_consumption_rate(total_rate, population_at_measurement)

    total_cover = cover_dwarf_days(stock.total_available, rate)
    durable_cover = cover_dwarf_days(stock.durable_available, rate)
    perishable_cover = cover_dwarf_days(stock.perishable_available, rate)
    days_now = days_at_population(total_cover, current_population)
    lead_time = resupply_lead_time_days()
    verdict = classify_cover(total_cover, targets)

    return CoverReport(
        subject=subject, stock=stock, consumption_per_dwarf_per_day=rate,
        total_cover_dwarf_days=total_cover, durable_cover_dwarf_days=durable_cover,
        perishable_cover_dwarf_days=perishable_cover, days_at_current_population=days_now,
        resupply_lead_time_days=lead_time, verdict=verdict,
    )
