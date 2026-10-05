"""handoffs/2026-10-05-ore-exposed-signal.md: exposed ore wakes the Architect,
edge triggered. Shaped on the live case: hematite in the corners of two dug
bedrooms (site-5 and site-6). The poll parser, the edge rule in lanes.py, and
a real `run_cycle` over the fakes (no VM, no model)."""

from __future__ import annotations

import json

import pytest

from conductor import lanes
from conductor.cycle import run_cycle
from conductor.ore_watch import ore_read_from_sites
from conductor.policy import load_policy
from conductor.tests.test_cycle import _base_tools, _deps

POLICY = load_policy()
RENOTIFY = POLICY.ore_renotify_ticks


def _row(handle, materials=None, **extra):
    row = {
        "handle": handle, "blueprint": "bedroom-cell-v1", "phases_applied": ["shell"],
        "footprint": {"width": 5, "height": 5},
        "near_landmark": "Activity Zone #5", "direction": "N", "distance_tiles": 4,
        "ore_exposed": {
            "total_tiles": sum(m["tiles"] for m in (materials or [])),
            "materials": materials or [],
            "unclassified_tiles": 0, "mine_with": "construction.mine-vein",
        },
    }
    row.update(extra)
    return row


HEM2 = [{"mineral_name": "HEMATITE", "kind": "ore", "tiles": 2}]
HEM1 = [{"mineral_name": "HEMATITE", "kind": "ore", "tiles": 1}]
TWO_SITES = [_row("site-5", HEM2), _row("site-6", HEM1)]


# --- the parser --------------------------------------------------------------


def test_one_exposure_per_site_and_material_with_a_line_naming_the_mining_tool():
    read = ore_read_from_sites(TWO_SITES)
    assert [e.key for e in read.exposures] == ["site-5:HEMATITE", "site-6:HEMATITE"]
    line = read.exposures[0].line
    assert line.startswith("HEMATITE ore: 2 tiles exposed on site-5's room walls")
    assert "4 tiles N of Activity Zone #5" in line
    assert line.endswith("mine with construction.mine-vein-site site-5")
    assert "1 tile exposed" in read.exposures[1].line
    for forbidden in ("x=", "y=", "z="):
        assert forbidden not in line


def test_a_site_with_no_ore_has_no_exposure_and_empty_tables_in_either_json_shape():
    assert ore_read_from_sites([_row("site-1")]).exposures == ()
    row = _row("site-1")
    row["ore_exposed"]["materials"] = {}  # an empty Lua table can serialise as {}
    assert ore_read_from_sites([row]).exposures == ()


def test_unreadable_sites_are_named_not_read_as_clear():
    rows = [
        _row("site-1", ore_exposed=None),
        _row("site-2", ore_exposed={"unreadable": True, "skipped": "no zone section"}),
        _row("site-3", ore_exposed={"unreadable": True, "error": "boom"}),
    ]
    read = ore_read_from_sites(rows)
    assert read.exposures == ()
    assert read.unreadable_handles == {"site-1", "site-2", "site-3"}


def test_a_poll_that_is_not_a_list_is_none_never_an_empty_read():
    assert ore_read_from_sites(None) is None
    assert ore_read_from_sites({"error": "no"}) is None
    assert ore_read_from_sites("garbage") is None
    assert ore_read_from_sites({"sites": TWO_SITES}).exposures


# --- the edge rule ------------------------------------------------------------


def _state_after(reads_and_ticks, state=None):
    state = state or lanes.LaneState()
    for rows, tick in reads_and_ticks:
        lanes.apply_ore_edges(POLICY, state, ore_read_from_sites(rows), tick)
    return state


def test_first_sight_owes_the_architect_one_wake_per_vein_and_nobody_else():
    state = _state_after([(TWO_SITES, 1000)])
    assert set(state.pending) == {"architect"}
    assert set(state.pending["architect"]) == {"ore:site-5:HEMATITE", "ore:site-6:HEMATITE"}
    wakes = lanes.lane_wakes(POLICY, state, {})
    assert [(w.reason, w.roles) for w in wakes] == [("ore_exposed", ("architect",))]
    assert "site-5" in wakes[0].detail and "site-6" in wakes[0].detail


def test_a_still_exposed_vein_does_not_wake_again_once_served():
    state = _state_after([(TWO_SITES, 1000)])
    lanes.clear_served(state, "architect")
    state = _state_after([(TWO_SITES, 1000 + 600)], state)
    assert lanes.lane_wakes(POLICY, state, {}) == ()


def test_a_vein_that_is_mined_clears_and_wakes_afresh_if_ore_reappears():
    state = _state_after([(TWO_SITES, 1000)])
    lanes.clear_served(state, "architect")
    state = _state_after([([_row("site-5", HEM2), _row("site-6")], 1600)], state)  # site-6 mined
    assert set(state.ore) == {"site-5:HEMATITE"}
    assert lanes.lane_wakes(POLICY, state, {}) == ()
    state = _state_after([(TWO_SITES, 2200)], state)
    wakes = lanes.lane_wakes(POLICY, state, {})
    assert len(wakes) == 1 and "site-6" in wakes[0].detail and "site-5" not in wakes[0].detail


def test_a_vein_mined_before_the_wake_was_served_drops_the_owed_wake():
    state = _state_after([(TWO_SITES, 1000), ([_row("site-5"), _row("site-6")], 1100)])
    assert lanes.lane_wakes(POLICY, state, {}) == ()
    assert state.ore == {}


def test_the_renotify_window_is_the_backstop_for_a_ruled_but_unmined_vein():
    state = _state_after([(TWO_SITES, 1000)])
    lanes.clear_served(state, "architect")
    state = _state_after([(TWO_SITES, 1000 + RENOTIFY - 1)], state)
    assert lanes.lane_wakes(POLICY, state, {}) == ()
    state = _state_after([(TWO_SITES, 1000 + RENOTIFY)], state)
    assert len(lanes.lane_wakes(POLICY, state, {})) == 1


def test_a_failed_poll_changes_nothing():
    state = _state_after([(TWO_SITES, 1000)])
    lanes.clear_served(state, "architect")
    before = dict(state.ore)
    lanes.apply_ore_edges(POLICY, state, None, 5000)
    assert state.ore == before and lanes.lane_wakes(POLICY, state, {}) == ()


def test_an_unreadable_site_keeps_its_state_so_it_is_not_taken_for_mined():
    state = _state_after([(TWO_SITES, 1000)])
    lanes.clear_served(state, "architect")
    state = _state_after([([_row("site-5", HEM2), _row("site-6", ore_exposed=None)], 1500)], state)
    assert "site-6:HEMATITE" in state.ore
    state = _state_after([(TWO_SITES, 1700)], state)
    assert lanes.lane_wakes(POLICY, state, {}) == ()


def test_a_reloaded_save_rearms_the_edge():
    state = _state_after([(TWO_SITES, 90000)])
    lanes.clear_served(state, "architect")
    state = _state_after([(TWO_SITES, 500)], state)  # the tick went backwards
    assert len(lanes.lane_wakes(POLICY, state, {})) == 1


def test_lane_state_round_trips_the_ore_edge(tmp_path):
    state = _state_after([(TWO_SITES, 1000)])
    store = lanes.LaneStore(tmp_path / "s.json")
    store.save(state)
    assert store.load() == state


def test_no_lane_with_ore_means_no_pending_wake():
    from dataclasses import replace

    quiet = replace(POLICY, lane_triggers={r: replace(l, ore=False) for r, l in POLICY.lane_triggers.items()})
    state = lanes.LaneState()
    lanes.apply_ore_edges(quiet, state, ore_read_from_sites(TWO_SITES), 1000)
    assert state.pending == {}


# --- through a real cycle -------------------------------------------------------

@pytest.mark.asyncio
async def test_exposed_ore_wakes_only_the_architect_once_and_its_briefing_has_one_line_each(tmp_path):
    deps = _deps(tmp_path, tools=_base_tools(**{"blueprint.sites": TWO_SITES}))
    result = await run_cycle(1, deps)
    assert result.roles_woken == ("architect",)
    brief = json.loads((result.archived_path / "briefings.json").read_text(encoding="utf-8"))["architect"]
    assert brief["wake_reason"] == "ore_exposed"
    assert brief["ore_exposed"]["count"] == 2
    assert [l.split(":")[0] for l in brief["ore_exposed"]["items"]] == ["HEMATITE ore", "HEMATITE ore"]

    # Next cycle, still exposed and served: nobody wakes, edge consumed.
    result2 = await run_cycle(2, deps)
    assert result2.roles_woken == ()


@pytest.mark.asyncio
async def test_a_failed_ore_poll_does_not_stop_the_cycle(tmp_path):
    tools = _base_tools()
    tools.pop("blueprint.sites", None)  # the allowlist entry is not deployed yet
    result = await run_cycle(1, _deps(tmp_path, tools=tools))
    assert result.roles_woken == ()


@pytest.mark.asyncio
async def test_a_woken_architect_with_no_ore_has_no_ore_key_in_its_briefing(tmp_path):
    from conductor.tests.test_cycle import _diff_sequence

    dig = [{"id": 1, "type": "JOB_COMPLETED", "detail": "Dig"}]
    tools = _base_tools(**{"blueprint.sites": [_row("site-1")], "diff.since": _diff_sequence([dig, []])})
    result = await run_cycle(1, _deps(tmp_path, tools=tools))
    assert result.roles_woken == ("architect",)
    brief = json.loads((result.archived_path / "briefings.json").read_text(encoding="utf-8"))["architect"]
    assert "ore_exposed" not in brief
