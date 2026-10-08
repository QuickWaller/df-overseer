"""2026-10-08, noble rooms: a position holder owns no room their position needs,
so the Architect is woken (`noble_room_unmet`) to file a routed zone.assign-owner
step. The poll parsers, the edge and backoff rule in lanes.py, and a real
`run_cycle` over the fakes. Shaped on the live case: MANAGER appointed with no
office owned (evals/live/2026-10-08-manager-appointment/README.md Phase D)."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from conductor import lanes, noble_room_watch as nrw
from conductor.cycle import run_cycle
from conductor.policy import load_policy
from conductor.tests.test_cycle import _base_tools, _deps

POLICY = load_policy()
NP = POLICY.noble_room


def _held(code="MANAGER", uid=345, name="Manager"):
    return {"code": code, "name": name, "vacant": False, "holder_unit_id": uid}


def _vacant(code="BROKER"):
    return {"code": code, "name": "Broker", "vacant": True, "holder_unit_id": None}


def _list(*rows):
    return {"entity_id": 1, "positions": list(rows)}


def _req(uid=345, *, office="not_met", office_zones=None, bedroom="not_required"):
    def one(status, zones):
        row = {"required": 1, "status": status}
        if zones is not None:
            row["zone_ids"] = zones
        return row
    return {
        "position": "MANAGER", "entity_id": 1, "read_failures": [],
        "assignments": [{
            "assignment_id": 1, "vacant": False, "holder_unit_id": uid,
            "room_value": {"Office": one(office, office_zones), "Bedroom": one(bedroom, None)},
            "furniture": {},
        }],
    }


def _zones(*ids):
    return {"summary": False, "matched": len(ids), "zones": [{"id": i, "kind": "Office"} for i in ids]}


# --- the parsers ----------------------------------------------------------------


def test_only_held_positions_with_a_unit_are_read():
    rows = nrw.held_positions(_list(_held(), _vacant(), _held("BOOKKEEPER", 12, "Bookkeeper")), 10)
    assert rows == [("MANAGER", 345, "Manager"), ("BOOKKEEPER", 12, "Bookkeeper")]


def test_the_position_read_is_bounded_by_policy():
    assert len(nrw.held_positions(_list(*[_held(f"P{i}", i) for i in range(20)]), 5)) == 5


def test_a_failed_list_is_none_not_an_empty_list():
    assert nrw.held_positions({"error": "x"}, 5) is None
    assert nrw.held_positions(_list(), 5) == []


def test_not_met_with_no_owned_zone_is_the_signal():
    assert nrw.unmet_kinds(_req(), 345, ("not_met",)) == ["Office"]


def test_an_owned_but_unfurnished_zone_is_a_building_matter_not_this_signal():
    assert nrw.unmet_kinds(_req(office_zones=[13]), 345, ("not_met",)) == []


def test_cannot_tell_and_met_never_signal():
    assert nrw.unmet_kinds(_req(office="cannot_tell"), 345, ("not_met",)) == []
    assert nrw.unmet_kinds(_req(office="met", office_zones=[13]), 345, ("not_met",)) == []
    assert nrw.unmet_kinds(_req(office="not_required"), 345, ("not_met",)) == []


def test_statuses_are_policy_data_not_code():
    assert nrw.unmet_kinds(_req(office="cannot_tell"), 345, ("not_met", "cannot_tell")) == ["Office"]


def test_another_holders_slot_is_ignored_and_a_bad_read_is_none():
    assert nrw.unmet_kinds(_req(uid=999), 345, ("not_met",)) == []
    assert nrw.unmet_kinds({"error": "unknown position code"}, 345, ("not_met",)) is None


def test_generic_over_kinds_a_bedroom_requirement_is_the_same_signal():
    assert nrw.unmet_kinds(_req(office="met", office_zones=[1], bedroom="not_met"), 345, ("not_met",)) == ["Bedroom"]


def test_the_line_names_position_holder_kind_and_the_unowned_zones():
    line = nrw.NobleRoomItem("MANAGER", 345, "Urist", "Office", (13, 17)).line()
    assert "MANAGER held by unit 345 (Urist) owns no Office zone" in line
    assert "unowned Office zone id(s): 13, 17" in line
    assert "no unowned Office zone exists" in nrw.NobleRoomItem("MANAGER", 345, "", "Office", ()).line()
    assert "could not be read" in nrw.NobleRoomItem("MANAGER", 345, "", "Office", None).line()


def test_coverage_reads_the_unit_id_of_open_assign_owner_steps_only():
    got = nrw.covered_unit_ids({"open_steps": [
        {"tool": "zone.assign-owner", "args": {"zone_id": 13, "UNIT_ID": 345}},
        {"tool": "zone.place", "args": {"unit_id": 999}},
    ]})
    assert got == frozenset({345})
    assert nrw.covered_unit_ids({"proposals": {}}) is None


# --- the edge rule and backoff -----------------------------------------------------


def _read(*, covered=(), codes=(), zones=(13,), uid=345):
    item = nrw.NobleRoomItem("MANAGER", uid, "Manager", "Office", tuple(zones))
    return nrw.NobleRoomRead(items=(item,), covered_units=frozenset(covered), unreadable_codes=frozenset(codes))


def _step(state, read, tick):
    lanes.apply_noble_room_edges(POLICY, state, read, tick)
    return state


def test_first_sight_owes_only_the_architect_one_wake_with_the_line():
    state = _step(lanes.LaneState(), _read(), 1000)
    assert set(state.pending) == {"architect"}
    (wake,) = lanes.lane_wakes(POLICY, state, {})
    assert (wake.reason, wake.roles) == ("noble_room_unmet", ("architect",))
    assert "MANAGER held by unit 345" in wake.detail and "13" in wake.detail


def test_not_resent_until_the_backoff_then_stalls_after_max_wakes():
    state = lanes.LaneState()
    t = 1000
    _step(state, _read(), t)
    lanes.clear_served(state, "architect")
    _step(state, _read(), t + NP.base_ticks - 1)
    assert lanes.lane_wakes(POLICY, state, {}) == ()
    t += NP.base_ticks
    _step(state, _read(), t)
    assert [w.reason for w in lanes.lane_wakes(POLICY, state, {})] == ["noble_room_unmet"]
    lanes.clear_served(state, "architect")
    t += 2 * NP.base_ticks
    _step(state, _read(), t)
    key = "MANAGER:345:Office"
    assert state.noble_rooms[key]["wakes"] == NP.max_wakes and state.noble_rooms[key]["stalled"]
    lanes.clear_served(state, "architect")
    _step(state, _read(), t + NP.cap_ticks * 10)
    assert lanes.lane_wakes(POLICY, state, {}) == ()


def test_an_open_assign_owner_step_for_the_holder_means_no_wake():
    state = _step(lanes.LaneState(), _read(covered=(345,)), 1000)
    assert state.pending == {} and lanes.lane_wakes(POLICY, state, {}) == ()


def test_a_cover_that_lands_after_the_wake_drops_the_unserved_wake():
    state = _step(lanes.LaneState(), _read(), 1000)
    _step(state, _read(covered=(345,)), 1500)
    assert lanes.lane_wakes(POLICY, state, {}) == ()


def test_it_clears_when_met_and_wakes_afresh_if_it_recurs():
    state = _step(lanes.LaneState(), _read(), 1000)
    _step(state, nrw.NobleRoomRead(), 2000)
    assert state.noble_rooms == {} and not state.pending.get("architect")
    _step(state, _read(), 3000)
    assert [w.reason for w in lanes.lane_wakes(POLICY, state, {})] == ["noble_room_unmet"]


def test_a_new_holder_is_a_new_fact():
    state = _step(lanes.LaneState(), _read(), 1000)
    lanes.clear_served(state, "architect")
    _step(state, _read(uid=400), 1100)
    assert [w.reason for w in lanes.lane_wakes(POLICY, state, {})] == ["noble_room_unmet"]
    assert set(state.noble_rooms) == {"MANAGER:400:Office"}


def test_a_failed_poll_or_an_unreadable_position_keeps_the_state():
    state = _step(lanes.LaneState(), _read(), 1000)
    lanes.clear_served(state, "architect")
    _step(state, None, 2000)
    assert "MANAGER:345:Office" in state.noble_rooms
    _step(state, nrw.NobleRoomRead(unreadable_codes=frozenset({"MANAGER"})), 3000)
    assert "MANAGER:345:Office" in state.noble_rooms
    assert lanes.lane_wakes(POLICY, state, {}) == ()


def test_state_survives_the_store_round_trip(tmp_path):
    state = _step(lanes.LaneState(), _read(), 1000)
    store = lanes.LaneStore(tmp_path / "s.json")
    store.save(state)
    assert store.load() == state


def test_no_lane_with_noble_rooms_means_no_pending_wake():
    quiet = replace(POLICY, lane_triggers={r: replace(l, noble_rooms=False) for r, l in POLICY.lane_triggers.items()})
    state = lanes.LaneState()
    lanes.apply_noble_room_edges(quiet, state, _read(), 1000)
    assert state.pending == {}


# --- through a real cycle ---------------------------------------------------------


def _tools(**over):
    base = {
        "nobles.list": _list(_held(), _vacant()),
        "nobles.requirements": _req(),
        "zone.list": _zones(13),
    }
    base.update(over)
    return _base_tools(**base)


@pytest.mark.asyncio
async def test_an_appointed_manager_with_no_office_wakes_only_the_architect_once(tmp_path):
    deps = _deps(tmp_path, tools=_tools())
    result = await run_cycle(1, deps)
    assert result.roles_woken == ("architect",)
    brief = json.loads((result.archived_path / "briefings.json").read_text(encoding="utf-8"))["architect"]
    assert brief["wake_reason"] == "noble_room_unmet"
    calls = [c for c in deps.tool_caller.calls if c[0] == "zone.list" and c[1].get("owner_filter") == "unowned"]
    assert calls and calls[0][1]["kind_filter"] == "Office"
    result2 = await run_cycle(2, deps)  # served, edge consumed, backoff not elapsed
    assert result2.roles_woken == ()


@pytest.mark.asyncio
async def test_a_manager_who_owns_the_office_wakes_nobody(tmp_path):
    tools = _tools(**{"nobles.requirements": _req(office="met", office_zones=[13])})
    result = await run_cycle(1, _deps(tmp_path, tools=tools))
    assert result.roles_woken == ()


@pytest.mark.asyncio
async def test_an_open_assign_owner_step_keeps_the_cycle_quiet(tmp_path):
    def overview(args):
        base = _base_tools()["queue.overview"]
        if args.get("open_steps_for"):
            return {**base, "open_steps": [
                {"proposal_id": "proposal-9", "tool": "zone.assign-owner", "args": {"zone_id": 13, "unit_id": 345}},
            ]}
        return base
    result = await run_cycle(1, _deps(tmp_path, tools=_tools(**{"queue.overview": overview})))
    assert result.roles_woken == ()


@pytest.mark.asyncio
async def test_a_failed_coverage_read_does_not_hide_the_need(tmp_path):
    def overview(args):
        if args.get("open_steps_for"):
            from conductor.mcp_client import MCPToolError
            raise MCPToolError("boom")
        return _base_tools()["queue.overview"]
    result = await run_cycle(1, _deps(tmp_path, tools=_tools(**{"queue.overview": overview})))
    assert result.roles_woken == ("architect",)


@pytest.mark.asyncio
async def test_an_undeployed_allowlist_does_not_stop_the_cycle(tmp_path):
    tools = _base_tools()
    result = await run_cycle(1, _deps(tmp_path, tools=tools))  # no nobles.* configured
    assert result.roles_woken == ()
