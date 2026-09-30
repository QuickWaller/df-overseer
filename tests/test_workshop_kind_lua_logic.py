"""handoffs/2026-09-30-reservation-gaps.md item 2: df-overseer-workshop.lua
used to keep its own lowercase kind keys (still/kitchen/mason/mechanic/
carpenter), which did not match df-overseer-building.lua's tokens
(Still/Kitchen/Masons/Mechanics/Carpenters) -- flagged as a real, live gap in
handoffs/2026-09-30-reservation-holding.md's own Result ("the kind checked
against a reservation's own allowed_kinds is this tool's own lowercase kind
key ... NOT df-overseer-building.lua's generic per-subtype token"). The fix,
`resolve_workshop_kind` (df-overseer-workshop.lua), resolves every kind
through a fake df-overseer-building.lua's own `list_kinds` (the SAME
function tests/test_construction_lua_logic.py's own
resolve_construction_kind tests already fake this way, since building.lua
itself needs the real game API and is not a touched surface this stream) --
proving the token workshop.lua ends up using is always whatever
building.lua's own kind table actually returns, never a hardcoded guess.

Skipped when lupa is not installed (it is not a repo dependency).
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts" / "dfhack"
STUBS = Path(__file__).resolve().parent / "lua_stubs"
WORKSHOP_LUA = SCRIPTS / "df-overseer-workshop.lua"
STUB = STUBS / "dfhack_workshop_kind_world.lua"

# The five real workshop kinds df-overseer-building.lua's own kind table
# resolves to on the live install (handoffs/2026-09-17-water-and-industry-
# tools.md item 3's own live verification), used here as the fake building
# module's KINDS list.
REAL_WORKSHOP_KINDS = [
    {"type": "Workshop", "subtype": "Still", "token": "Still", "key": "wl", "label": "Still"},
    {"type": "Workshop", "subtype": "Kitchen", "token": "Kitchen", "key": "wz", "label": "Kitchen"},
    {"type": "Workshop", "subtype": "Masons", "token": "Masons", "key": "wm", "label": "Mason's Workshop"},
    {"type": "Workshop", "subtype": "Mechanics", "token": "Mechanics", "key": "wt", "label": "Mechanic's Workshop"},
    {"type": "Workshop", "subtype": "Carpenters", "token": "Carpenters", "key": "wc", "label": "Carpenter's Workshop"},
]


def _upvalue_by_name(lua, fn, name):
    getter = lua.eval("""
        function(fn, name)
          local i = 1
          while true do
            local n, v = debug.getupvalue(fn, i)
            if n == nil then return nil end
            if n == name then return v end
            i = i + 1
          end
        end
    """)
    return getter(fn, name)


class WorkshopWorld:
    def __init__(self, kinds=REAL_WORKSHOP_KINDS):
        self.lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        load = self.lua.eval("function(src, name) return load(src, name) end")
        stub_chunk = load(STUB.read_text(encoding="utf-8"), "workshop_kind_world")
        stub_chunk()
        self.set_kinds(kinds)
        chunk = load(WORKSHOP_LUA.read_text(encoding="utf-8"), "workshop.lua")
        chunk()
        g = self.lua.globals()
        self.build_workshop = g["build_workshop"]
        self.resolve_workshop_kind = _upvalue_by_name(self.lua, self.build_workshop, "resolve_workshop_kind")
        assert self.resolve_workshop_kind is not None
        # A single-Lua-value success return (`return info_table`) reaches
        # lupa as the bare table, not a 1-tuple -- unpacking it directly in
        # Python would iterate the TABLE's own contents instead. This
        # wrapper normalises to always exactly two Lua return values (info,
        # err), matching real Lua's own "missing values become nil" rule,
        # so `unpack_returned_tuples` always hands Python a clean 2-tuple.
        self._call2 = self.lua.eval("function(fn, name) local a, b = fn(name) return a, b end")

    def set_kinds(self, kinds):
        table = self.lua.table_from([self.lua.table_from(k) for k in kinds])
        self.lua.globals()["set_kinds"](table)

    def resolve(self, name):
        info, err = self._call2(self.resolve_workshop_kind, name)
        return info, err


@pytest.mark.parametrize("old_key,expected_token", [
    ("still", "Still"),
    ("kitchen", "Kitchen"),
    ("mason", "Masons"),
    ("mechanic", "Mechanics"),
    ("carpenter", "Carpenters"),
])
def test_old_lowercase_key_resolves_to_buildings_own_token(old_key, expected_token):
    """workshop.build's existing accepted inputs (the five old lowercase
    keys) keep working, but the TOKEN used for reservation checks is now
    building.lua's own live-resolved value, not the old key itself."""
    w = WorkshopWorld()
    info, err = w.resolve(old_key)
    assert err is None
    assert info["token"] == expected_token
    assert info["labor"]  # policy fields still present, keyed by the token now


@pytest.mark.parametrize("token", ["Still", "Masons", "Mechanics", "Carpenters"])
def test_a_building_token_or_subtype_name_is_also_accepted_directly(token):
    """An agent (or test) naming the building.lua token/subtype directly
    (e.g. "Masons") resolves to itself -- resolve_workshop_kind tries the raw
    input before consulting the old-key alias table."""
    w = WorkshopWorld()
    info, err = w.resolve(token)
    assert err is None
    assert info["token"] == token


def test_case_insensitive_old_key_still_works():
    w = WorkshopWorld()
    info, err = w.resolve("MASON")
    assert err is None
    assert info["token"] == "Masons"


def test_unknown_kind_refused_naming_the_expected_inputs():
    w = WorkshopWorld()
    info, err = w.resolve("smelter")
    assert info is None
    assert "unknown workshop kind" in err
    assert "still/kitchen/mason/mechanic/carpenter" in err


def test_a_real_building_kind_with_no_policy_entry_is_refused_not_guessed():
    """If building.lua's own kind table resolves a token this tool's
    KIND_INFO has no labor/container policy for, this is reported honestly
    rather than silently treated as some other kind."""
    w = WorkshopWorld(kinds=REAL_WORKSHOP_KINDS + [
        {"type": "Workshop", "subtype": "Custom", "token": "Smelter", "key": "we", "label": "Smelter"},
    ])
    info, err = w.resolve("Smelter")
    assert info is None
    assert "Smelter" in err
    assert "no labor/container policy" in err


def test_a_token_collision_is_reported_not_silently_mismatched():
    """If building.lua ever had to disambiguate Masons into e.g.
    "Masons_wm" (a real token collision), the old key "mason" still matches
    that kind (its subtype name is still bare "Masons"), but this tool's own
    KIND_INFO (keyed "Masons") no longer matches the REAL token -- refused
    as "no policy for it yet" rather than silently applying the plain
    "Masons" policy under a token building.lua never actually produced for
    this install."""
    collided = [dict(k) for k in REAL_WORKSHOP_KINDS]
    for k in collided:
        if k["token"] == "Masons":
            k["token"] = "Masons_wm"
    w = WorkshopWorld(kinds=collided)
    info, err = w.resolve("mason")
    assert info is None
    assert "Masons_wm" in err
    assert "no labor/container policy" in err
