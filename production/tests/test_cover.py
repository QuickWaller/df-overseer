"""The days-of-cover calculator (`production/cover.py`), tested against
hand-built snapshots -- the same approach `test_blocker.py` takes, and for
the same reason: this module needs no fixture from `extract.py`, since it
walks a snapshot the caller already assembled, not the raw-derived graph.

None of the node ids below are real DF raw tokens; they are illustrative,
same status `test_blocker.py`'s own fixtures carry (see
`fixtures/PROVENANCE.md`: "ILLUSTRATIVE").

Handoff's five named tests (`handoffs/2026-09-18-days-of-cover.md`, "Tests
that matter more than coverage") map onto the sections below in the same
order.
"""

from __future__ import annotations

import pytest

from production import cover, schema

# ---- small builders ------------------------------------------------------------


def _item(node_id: str, *, in_job=False, owned=False, forbid=False, trader=False, rotten=False) -> dict:
    return {
        "node_id": node_id, "in_job": in_job, "owned": owned,
        "forbid": forbid, "trader": trader, "rotten": rotten,
    }


def _obs(subject_id: str, abs_tick: int, value: float, metric: str = schema.METRIC_STOCK) -> dict:
    return {"subject_id": subject_id, "metric": metric, "abs_tick": abs_tick, "value": value}


DURABILITY = {
    "DRINK:PLUMP_HELMET_WINE": schema.DURABLE,
    "PLANT:MUSHROOM_HELMET_PLUMP": schema.PERISHABLE,
}


# ---- 1. two observations give an exact rate; one gives unknown -----------------


def test_two_observations_give_a_measured_rate():
    obs = [
        _obs("class:FOOD", 1_000_000, 150),
        _obs("class:FOOD", 1_000_000 + cover.TICKS_PER_DAY, 130),
    ]
    rate = cover.depletion_rate_per_day(obs)
    assert rate.status == schema.MEASURED
    assert rate.value == pytest.approx(20.0)  # 20 units lost over exactly one day
    assert rate.reason is None


def test_one_observation_gives_unavailable_not_a_wiki_fallback():
    obs = [_obs("class:FOOD", 1_000_000, 150)]
    rate = cover.depletion_rate_per_day(obs)
    assert rate.status == schema.UNAVAILABLE
    assert rate.value is None
    assert rate.reason is not None and "two" in rate.reason.lower()


def test_zero_observations_also_gives_unavailable():
    rate = cover.depletion_rate_per_day([])
    assert rate.status == schema.UNAVAILABLE
    assert rate.value is None


def test_repeated_reads_at_the_same_tick_do_not_count_as_two():
    # Same abs_tick twice (e.g. a re-read that landed on an identical tick)
    # carries no time separation, so no rate is derivable -- still unavailable.
    obs = [_obs("class:FOOD", 1_000_000, 150), _obs("class:FOOD", 1_000_000, 149)]
    rate = cover.depletion_rate_per_day(obs)
    assert rate.status == schema.UNAVAILABLE


def test_mixed_subject_or_metric_rows_raise_rather_than_silently_average():
    obs = [
        _obs("class:FOOD", 1_000_000, 150),
        _obs("class:DRINK", 1_000_000 + cover.TICKS_PER_DAY, 40),
    ]
    with pytest.raises(ValueError):
        cover.depletion_rate_per_day(obs)


def test_per_dwarf_rate_needs_population_at_measurement():
    rate = cover.Figure(status=schema.MEASURED, value=20.0)
    fig = cover.per_dwarf_consumption_rate(rate, None)
    assert fig.status == schema.UNAVAILABLE
    assert fig.value is None


def test_per_dwarf_rate_propagates_unavailable_unchanged():
    rate = cover.depletion_rate_per_day([_obs("class:FOOD", 1_000_000, 150)])
    fig = cover.per_dwarf_consumption_rate(rate, 15)
    assert fig.status == schema.UNAVAILABLE
    assert fig.reason == rate.reason


# ---- 2. the unavailable lead-time path returns a usable report -----------------


def test_resupply_lead_time_is_always_unavailable_even_given_real_looking_numbers():
    # Handed the exact live figures from spec sec11 (growdur=300,
    # grow_counter=18480): still refuses to convert them. The function must
    # never pick a candidate unit, not even when it looks tempting.
    fig = cover.resupply_lead_time_days(growdur_ticks=300, grow_counter_ticks=18480)
    assert fig.status == schema.UNAVAILABLE
    assert fig.value is None
    assert fig.reason


def test_cover_report_with_unavailable_lead_time_does_not_raise_and_stays_useful():
    items = [_item("DRINK:PLUMP_HELMET_WINE") for _ in range(30)]
    obs = [
        _obs("DRINK:PLUMP_HELMET_WINE", 1_000_000, 150),
        _obs("DRINK:PLUMP_HELMET_WINE", 1_000_000 + cover.TICKS_PER_DAY, 130),
    ]
    targets = cover.CoverTargets(reserve_floor_dwarf_days=10, cover_target_dwarf_days=100)

    report = cover.compute_cover_report(
        "DRINK:PLUMP_HELMET_WINE", items, DURABILITY, obs, targets,
        population_at_measurement=15, current_population=15,
    )

    # No number ever appears for the lead-time term.
    assert report.resupply_lead_time_days.status == schema.UNAVAILABLE
    assert report.resupply_lead_time_days.value is None
    # The rest of the report is unaffected and stays useful.
    assert report.total_cover_dwarf_days.status == schema.MEASURED
    assert report.total_cover_dwarf_days.value == pytest.approx(30 / (20.0 / 15))
    assert report.verdict.status == schema.MEASURED


# ---- 3. durable and perishable reported separately; rotten never inflates cover -


def test_split_stock_separates_durable_perishable_and_rotten():
    items = (
        [_item("DRINK:PLUMP_HELMET_WINE") for _ in range(4)]
        + [_item("PLANT:MUSHROOM_HELMET_PLUMP") for _ in range(7)]
        + [_item("PLANT:MUSHROOM_HELMET_PLUMP", rotten=True) for _ in range(3)]
        + [_item("PLANT:MUSHROOM_HELMET_PLUMP", in_job=True) for _ in range(2)]  # claimed, excluded entirely
    )
    split = cover.split_stock(items, DURABILITY)
    assert split.durable_available == 4
    assert split.perishable_available == 7
    assert split.perishable_rotten == 3
    assert split.total_available == 11  # rotten and claimed both excluded


def test_entirely_perishable_stock_does_not_silently_inflate_cover():
    items = [_item("PLANT:MUSHROOM_HELMET_PLUMP") for _ in range(20)]
    obs = [
        _obs("class:FOOD", 1_000_000, 150),
        _obs("class:FOOD", 1_000_000 + cover.TICKS_PER_DAY, 130),
    ]
    targets = cover.CoverTargets(reserve_floor_dwarf_days=1, cover_target_dwarf_days=50)

    report = cover.compute_cover_report(
        "class:FOOD", items, DURABILITY, obs, targets,
        population_at_measurement=15, current_population=15,
    )

    assert report.stock.durable_available == 0
    assert report.durable_cover_dwarf_days.value == 0.0
    # Total is exactly the perishable figure -- no phantom durable stock
    # sneaking into the blended number.
    assert report.total_cover_dwarf_days.value == pytest.approx(report.perishable_cover_dwarf_days.value)


# ---- 4. a population change rescales cover without re-measuring the rate -------


def test_population_change_rescales_cover_without_remeasuring_rate():
    items = [_item("DRINK:PLUMP_HELMET_WINE") for _ in range(60)]
    obs = [
        _obs("DRINK:PLUMP_HELMET_WINE", 1_000_000, 150),
        _obs("DRINK:PLUMP_HELMET_WINE", 1_000_000 + cover.TICKS_PER_DAY, 130),
    ]
    targets = cover.CoverTargets(reserve_floor_dwarf_days=1, cover_target_dwarf_days=1)

    report_15 = cover.compute_cover_report(
        "DRINK:PLUMP_HELMET_WINE", items, DURABILITY, obs, targets,
        population_at_measurement=15, current_population=15,
    )
    report_30 = cover.compute_cover_report(
        "DRINK:PLUMP_HELMET_WINE", items, DURABILITY, obs, targets,
        population_at_measurement=15, current_population=30,
    )

    # Same observations, same population_at_measurement -> the measured
    # rate and the dwarf-days cover figure are identical: no re-measurement
    # happened just because "current" population differs.
    assert report_15.consumption_per_dwarf_per_day.value == report_30.consumption_per_dwarf_per_day.value
    assert report_15.total_cover_dwarf_days.value == report_30.total_cover_dwarf_days.value

    # But the population change instantly rescales the plain-days reading.
    assert report_15.days_at_current_population.value == pytest.approx(
        report_30.days_at_current_population.value * 2
    )


def test_days_at_population_requires_a_current_population():
    cover_fig = cover.Figure(status=schema.MEASURED, value=90.0)
    fig = cover.days_at_population(cover_fig, None)
    assert fig.status == schema.UNAVAILABLE
    assert fig.value is None


# ---- 5. below-target, below-floor and above-target are distinct verdicts -------


def test_verdict_bands_are_distinct_and_lexicographic():
    targets = cover.CoverTargets(reserve_floor_dwarf_days=10, cover_target_dwarf_days=50)

    below_floor = cover.classify_cover(cover.Figure(status=schema.MEASURED, value=5), targets)
    below_target = cover.classify_cover(cover.Figure(status=schema.MEASURED, value=20), targets)
    above_target = cover.classify_cover(cover.Figure(status=schema.MEASURED, value=50), targets)

    assert below_floor.value == cover.BELOW_RESERVE_FLOOR
    assert below_target.value == cover.BELOW_TARGET
    assert above_target.value == cover.ABOVE_TARGET
    assert len({below_floor.value, below_target.value, above_target.value}) == 3


def test_verdict_is_unavailable_when_cover_itself_is_unavailable():
    targets = cover.CoverTargets(reserve_floor_dwarf_days=10, cover_target_dwarf_days=50)
    unmeasured_cover = cover.Figure(status=schema.UNAVAILABLE, value=None, reason="no rate")
    verdict = cover.classify_cover(unmeasured_cover, targets)
    assert verdict.status == schema.UNAVAILABLE
    assert verdict.value is None


# ---- Figure itself: an unavailable figure never carries a number ---------------


def test_figure_rejects_a_number_alongside_unavailable_status():
    with pytest.raises(ValueError):
        cover.Figure(status=schema.UNAVAILABLE, value=5)


def test_figure_rejects_an_out_of_vocabulary_status():
    with pytest.raises(ValueError):
        cover.Figure(status="probably-fine")


# ---- non-depleting stock reads as unbounded cover, not a negative number -------


def test_growing_stock_reads_as_unbounded_cover_not_negative():
    obs = [
        _obs("DRINK:PLUMP_HELMET_WINE", 1_000_000, 100),
        _obs("DRINK:PLUMP_HELMET_WINE", 1_000_000 + cover.TICKS_PER_DAY, 120),  # stock rose
    ]
    rate = cover.per_dwarf_consumption_rate(cover.depletion_rate_per_day(obs), 15)
    fig = cover.cover_dwarf_days(50, rate)
    assert fig.status == schema.MEASURED
    assert fig.value == float("inf")


# ---- end to end: a full report never raises -------------------------------------


def test_full_report_does_not_raise_and_every_field_carries_a_status():
    items = (
        [_item("DRINK:PLUMP_HELMET_WINE") for _ in range(12)]
        + [_item("PLANT:MUSHROOM_HELMET_PLUMP") for _ in range(9)]
        + [_item("PLANT:MUSHROOM_HELMET_PLUMP", rotten=True) for _ in range(2)]
    )
    obs = [
        _obs("class:FOOD", 1_000_000, 40),
        _obs("class:FOOD", 1_000_000 + 3 * cover.TICKS_PER_DAY, 25),
    ]
    targets = cover.CoverTargets(reserve_floor_dwarf_days=20, cover_target_dwarf_days=200)

    report = cover.compute_cover_report(
        "class:FOOD", items, DURABILITY, obs, targets,
        population_at_measurement=15, current_population=15,
    )

    for figure in (
        report.consumption_per_dwarf_per_day, report.total_cover_dwarf_days,
        report.durable_cover_dwarf_days, report.perishable_cover_dwarf_days,
        report.days_at_current_population, report.resupply_lead_time_days, report.verdict,
    ):
        assert figure.status in schema.STATUS_VALUES
