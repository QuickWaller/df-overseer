"""Runs the REAL scripts/dfhack/df-overseer-zone.lua (assign-owner and
clear-owner) against a fake DFHack world (tests/lua_stubs/dfhack_zone_world.lua)
using lupa.

handoffs/2026-09-24-zone-owner-assign.md. It proves the file's own logic: every
named refusal, the dry run that writes nothing, that a real run leaves BOTH
directions of the owner link in the fake world (zone.assigned_unit_id and the
unit's owned_buildings), that a fake setOwner which writes only one direction is
reported as one-directional rather than as success, and the tri-state
read-back. It proves nothing about what the real dfhack.buildings.setOwner
does: that is the live check in the handoff Result.

Skipped when lupa is not installed (it is not a repo dependency).
"""

import os
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

REPO_ROOT = Path(__file__).resolve().parent.parent
LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-zone.lua"
STUB = REPO_ROOT / "tests" / "lua_stubs" / "dfhack_zone_world.lua"


def _py(v):
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    keys = list(v.keys())
    if keys and all(isinstance(k, int) for k in keys) and keys == list(range(1, len(keys) + 1)):
        return [_py(v[k]) for k in keys]
    return {str(k): _py(v[k]) for k in keys}


class World:
    def __init__(self):
        self.lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(STUB.read_text(encoding="utf-8"))
        load = self.lua.eval("function(src) return load(src, 'zone.lua') end")
        chunk = load(LUA.read_text(encoding="utf-8"))
        assert not isinstance(chunk, tuple), chunk
        self.lua.eval("function(f) f() end")(chunk)
        self.g = self.lua.globals()

    def call(self, name, *args):
        r = self.g[name](*args)
        if isinstance(r, tuple):
            r = r[0]
        return _py(r)

    def run(self, code):
        return self.lua.execute(code)

    def eval(self, code):
        return _py(self.lua.eval(code))

    def assigned(self, zone_id):
        return self.eval(f"zone_assigned({zone_id})")

    def owned(self, unit_id):
        return self.eval(f"unit_owned_ids({unit_id})") or []

    def set_calls(self):
        return self.eval("SET_OWNER_CALLS") or []


@pytest.fixture
def w():
    world = World()
    world.run("add_unit(345); add_unit(400); add_unit(500, false, true); add_unit(501, true, false)")
    world.run("add_zone(10, 'Office'); add_zone(11, 'Office', 345); add_zone(12, 'MeetingHall'); add_zone(13, 'Office')")
    world.run("add_workshop(99)")
    world.run("set_positions({{code='MANAGER', id=1, required_office=1, holder_unit=345}})")
    return world


def test_dry_run_reports_the_links_and_writes_nothing(w):
    r = w.call("assign_owner", 13, 400)
    assert "refused" not in r
    assert r["dry_run"] is True and r["applied"] is False
    assert r["calls"] == ["dfhack.buildings.setOwner(zone 13, unit 400)"]
    assert any("assigned_unit_id" in x for x in r["would_write"])
    assert any("owned_buildings" in x for x in r["would_write"])
    assert w.assigned(13) == -1 and w.owned(400) == []
    assert w.set_calls() == []


def test_dry_run_is_the_default_and_only_an_explicit_false_writes(w):
    w.call("assign_owner", 13, 400, "true")
    w.call("assign_owner", 13, 400, "yes")
    assert w.set_calls() == []


def test_real_run_sets_both_directions_and_the_read_back_confirms_them(w):
    w.run("set_positions({{code='MANAGER', id=1, required_office=1, holder_unit=400}})")
    r = w.call("assign_owner", 13, 400, "false")
    assert r["applied"] is True, r
    # BOTH directions of the link, read from the fake world itself, not the tool
    assert w.assigned(13) == 400
    assert w.owned(400) == [13]
    assert r["links_confirmed"]["zone_side"] is True and r["links_confirmed"]["unit_side"] is True
    assert r["after"]["unit_side_holds_zone"] == "yes"
    h = r["holder"]
    assert h["holder_link_resolves"] == "resolved"
    assert h["positions_asking_this_room_value"] == ["MANAGER"]
    assert h["unit_holds_a_position_asking_this_room_value"] == "yes"
    # an empty quality word still reads not_met: the link is not the gap
    assert h["room_value_status"] == "not_met"
    assert not r["read_failures"]


def test_room_value_met_when_the_room_has_a_quality_word(w):
    w.run("ROOM_DESC = 'Meager Quarters'")
    r = w.call("assign_owner", 13, 400, "false")
    assert r["holder"]["room_value_status"] == "met"


def test_an_implementation_setting_only_one_direction_is_reported_not_trusted(w):
    for mode in ("zone_only", "unit_only"):
        w.run("SET_OWNER_MODE = '%s'; ZONES[4].assigned_unit_id = -1" % mode)
        r = w.call("assign_owner", 13, 400, "false")
        assert r["applied"] is False, (mode, r)
        assert r["one_direction_only"] is True, r
        assert r["links_confirmed"]["zone_side"] != r["links_confirmed"]["unit_side"]
        w.run("clear_unit_items(400)")


def test_named_refusals(w):
    cases = [
        (("assign_owner", 999, 400), "zone_not_found"),
        (("assign_owner", 99, 400), "not_a_civzone"),
        (("assign_owner", 12, 400), "kind_has_no_owner"),
        (("assign_owner", "abc", 400), "bad_zone_id"),
        (("assign_owner", 13, "x"), "bad_unit_id"),
        (("assign_owner", 13, 999), "unit_not_found"),
        (("assign_owner", 13, 500), "unit_not_alive"),
        (("assign_owner", 13, 501), "unit_not_citizen"),
        (("assign_owner", 11, 400), "zone_has_other_owner"),
        (("assign_owner", 11, 345), "already_owner"),
        (("assign_owner", 13, 345), "unit_already_owns_kind_zone"),
        (("clear_owner", 13), "zone_has_no_owner"),
        (("clear_owner", 12), "kind_has_no_owner"),
        (("clear_owner", 999), "zone_not_found"),
    ]
    for args, name in cases:
        r = w.call(*args, "false")
        assert r["refused"] == name, (args, r)
        assert r["applied"] is False and r["reason"].startswith("refused: ")
    assert w.set_calls() == []  # no refusal ever wrote


def test_override_replaces_an_owner_and_releases_the_previous_owner(w):
    r = w.call("assign_owner", 11, 400, "false", "true")
    assert r["applied"] is True, r
    assert w.assigned(11) == 400
    assert w.owned(400) == [11]
    assert w.owned(345) == []           # the previous owner's side was released too
    assert r["previous_owner_unit_id"] == 345
    assert r["links_confirmed"]["previous_owner_released"] == "yes"
    assert [c["unit"] for c in w.set_calls()] == [False, 400]


def test_override_allows_a_second_room_of_a_kind(w):
    r = w.call("assign_owner", 13, 345, "false", "true")
    assert r["applied"] is True
    assert sorted(w.owned(345)) == [11, 13]
    assert r["overrides_used"] is True


def test_clear_owner_dry_then_real_and_returns_the_previous_owner(w):
    d = w.call("clear_owner", 11)
    assert d["applied"] is False and d["previous_owner_unit_id"] == 345 and d["cannot_undo"]
    assert w.assigned(11) == 345
    r = w.call("clear_owner", 11, "false")
    assert r["applied"] is True, r
    assert r["previous_owner_unit_id"] == 345
    assert w.assigned(11) == -1 and w.owned(345) == []
    assert r["links_confirmed"] == {"zone_side_cleared": True, "previous_owner_released": "yes"}


def test_clear_owner_with_a_one_way_setowner_is_not_reported_as_applied(w):
    w.run("SET_OWNER_MODE = 'zone_only'")
    r = w.call("clear_owner", 11, "false")
    assert r["applied"] is False
    assert r["links_confirmed"]["previous_owner_released"] == "no"


def test_a_failed_owner_read_refuses_and_is_logged_never_defaulted(w):
    w.run("GET_OWNER_FAILS = true")
    r = w.call("assign_owner", 13, 400, "false")
    assert r["refused"] in ("zone_owner_unreadable", "duplicate_check_unreadable")
    assert w.set_calls() == []
    assert r["read_failures"] or r["refused"] == "duplicate_check_unreadable"
    assert "getOwner" in w.eval("ERRS") or r["refused"] == "duplicate_check_unreadable"
    r2 = w.call("clear_owner", 11, "false")
    assert r2["refused"] == "zone_owner_unreadable"
    assert r2["before"]["zone_side"]["status"] == "cannot_tell"
    assert w.set_calls() == []


def test_a_failed_room_read_after_a_real_write_is_cannot_tell_with_a_failure_logged(w):
    w.run("DESC_FAILS = true")
    r = w.call("assign_owner", 13, 400, "false")
    assert r["applied"] is True
    assert r["holder"]["room_value_status"] == "cannot_tell"
    assert any("getRoomDescription" in f for f in r["read_failures"])
    assert "room_value_status read failure" in w.eval("ERRS")


def test_a_missing_fortress_entity_is_cannot_tell_for_the_position_link(w):
    w.run("df.global.plotinfo.main.fortress_entity = nil")
    r = w.call("assign_owner", 13, 400, "false")
    assert r["applied"] is True
    assert r["holder"]["unit_holds_a_position_asking_this_room_value"] == "cannot_tell"
    assert r["read_failures"]


def test_no_coordinate_reaches_the_result(w):
    r = w.call("assign_owner", 13, 400)
    assert "x" not in r and "y" not in r and "pos" not in r
