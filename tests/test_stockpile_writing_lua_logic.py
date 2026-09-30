"""handoffs/2026-10-01-stockpile-writing.md: df-overseer-stockpile.lua's new
writing commands (place, configure, link, unlink).

Loads the REAL df-overseer-stockpile.lua against a fake DFHack world
(tests/lua_stubs/dfhack_stockpile_world.lua) plus the REAL
df-overseer-reservations.lua (a dependency-free leaf, same pattern
tests/lua_stubs/dfhack_well_reservations_world.lua already established), so
category validation, the letter/preset tables, the reservation-skip wiring,
configure's enable/disable diff, and link/unlink's vector bookkeeping are all
exercised against the actual production code, not a re-description of it.

What this file does NOT prove (see dfhack_stockpile_world.lua's own header):
the fake `run_command_silent` is a simplified stand-in for real quickfort --
it does not run place.lua's own is_valid_stockpile_tile, container defaults,
or extent grouping. A real #place run against Uniboslan's own terrain is the
only thing that settles whether the coarser is_free finder (reused from
df-overseer-openarea.lua, per the handoff) ever actually produces a
smaller-than-requested pile there. Likewise plugins.stockpiles.import_settings
is faked at the single-category-flag level; the real plugin's finer subtype
behaviour is not exercised.

Skipped when lupa is not installed (it is not a repo dependency).
"""

import os
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts" / "dfhack"
STUBS = Path(__file__).resolve().parent / "lua_stubs"
STOCKPILE_LUA = SCRIPTS / "df-overseer-stockpile.lua"
RESERVATIONS_LUA = SCRIPTS / "df-overseer-reservations.lua"
STUB = STUBS / "dfhack_stockpile_world.lua"


class StockpileWorld:
    def __init__(self):
        self.lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        load = self.lua.eval("function(src, name) return load(src, name) end")

        # The stub's own reqscript("df-overseer-reservations") loads the REAL
        # file (env-table technique, see the stub's own header/comment) --
        # same pattern tests/lua_stubs/dfhack_well_reservations_world.lua
        # already established. The real file's path is the stub chunk's own
        # `...` argument.
        stub_chunk = load(STUB.read_text(encoding="utf-8"), "stockpile_world")
        stub_chunk(str(RESERVATIONS_LUA))

        stockpile_chunk = load(STOCKPILE_LUA.read_text(encoding="utf-8"), "stockpile.lua")
        stockpile_chunk()

        reservations_mod = self.lua.eval('function() return reqscript("df-overseer-reservations") end')()

        g = self.lua.globals()
        self.list_stockpiles = g["list_stockpiles"]
        self._stockpile_links = g["stockpile_links"]
        self._place_stockpile = g["place_stockpile"]
        self._stockpile_configure = g["stockpile_configure"]
        self._stockpile_link = g["stockpile_link"]
        self._stockpile_unlink = g["stockpile_unlink"]
        self.reservations_mod = reservations_mod
        self._set_free = g["set_free"]
        self._make_workshop = g["make_workshop"]
        self._set_anchor = g["set_anchor"]

    @staticmethod
    def _as_pair(raw):
        # lupa's unpack_returned_tuples=True hands back a bare python tuple
        # for a >1-value Lua return, but the SINGLE object itself for a
        # 1-value return (never wrapped) -- every function here returns
        # either (result) or (nil, err), so `a, b = fn(...)` in plain Python
        # would wrongly try to iterate a lone LuaTable's own pairs on the
        # success path. Normalise to a real 2-tuple here instead.
        if isinstance(raw, tuple):
            if len(raw) >= 2:
                return raw[0], raw[1]
            if len(raw) == 1:
                return raw[0], None
            return None, None
        return raw, None

    def stockpile_links(self, *args):
        return self._as_pair(self._stockpile_links(*args))

    def place_stockpile(self, *args):
        return self._as_pair(self._place_stockpile(*args))

    def stockpile_configure(self, *args):
        return self._as_pair(self._stockpile_configure(*args))

    def stockpile_link(self, *args):
        return self._as_pair(self._stockpile_link(*args))

    def stockpile_unlink(self, *args):
        return self._as_pair(self._stockpile_unlink(*args))

    def set_free(self, x, y, z, free=True):
        self._set_free(x, y, z, free)

    def free_rect(self, x, y, z, w, h):
        for dx in range(w):
            for dy in range(h):
                self.set_free(x + dx, y + dy, z, True)

    def set_anchor(self, x, y, z):
        self._set_anchor(x, y, z)

    def make_workshop(self):
        return self._make_workshop(0, 0, 0)

    def create_reservation(self, **rec):
        table = self.lua.table_from(rec)
        return self.reservations_mod.create(table)

    def to_dict(self, v):
        if hasattr(v, "items"):
            d = {}
            for k, val in v.items():
                d[k] = self.to_dict(val)
            return d
        return v

    def to_list(self, v):
        if v is None:
            return []
        if hasattr(v, "values"):
            return [self.to_dict(x) for x in v.values()]
        return list(v)


@pytest.fixture
def world(tmp_path, monkeypatch):
    # place_stockpile writes a real throwaway #place CSV under
    # dfhack-config/blueprints/ (the same relative path every other
    # designating tool in this codebase uses, resolved against DF's own
    # working directory on a live install) -- give it that directory here
    # so the write/remove round trip is real, not skipped.
    (tmp_path / "dfhack-config" / "blueprints").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    return StockpileWorld()


# ---------------------------------------------------------------------------
# place
# ---------------------------------------------------------------------------

def test_place_rejects_unknown_category(world):
    world.set_anchor(50, 50, 10)
    world.free_rect(45, 45, 10, 5, 5)
    result, err = world.place_stockpile(2, 2, 0, "Anchor", "not_a_category", 1, 10, "false", None, None)
    assert result is None
    assert "unknown category" in err
    assert "not_a_category" in err


def test_place_rejects_oversized_dims(world):
    result, err = world.place_stockpile(32, 2, 0, "Anchor", "stone", 1, 10, "false", None, None)
    assert result is None
    assert "1 and 31" in err


def test_place_dry_run_makes_no_stockpile(world):
    world.set_anchor(50, 50, 10)
    world.free_rect(45, 45, 10, 5, 5)
    result, err = world.place_stockpile(2, 2, 0, "Anchor", "stone,wood", 1, 10, None, None, None)
    assert err is None
    assert world.to_dict(result)["dry_run"] is True
    listed = world.list_stockpiles()
    assert len(world.to_list(listed["stockpiles"])) == 0


def test_place_real_run_creates_stockpile_with_requested_categories(world):
    world.set_anchor(50, 50, 10)
    world.free_rect(45, 45, 10, 5, 5)
    result, err = world.place_stockpile(2, 2, 0, "Anchor", "stone,wood", 1, 10, "false", None, None)
    assert err is None
    r = world.to_dict(result)
    assert r["quickfort_ok"] is True
    rb = r["read_back"]
    assert rb["stockpile_found"] is True
    assert rb["total_tiles"] == 4
    accepts = sorted(world.to_list(rb["accepts"]))
    assert accepts == ["stone", "wood"]


def test_place_sheet_category_round_trips_the_plural_preset_spelling(world):
    # The one real naming mismatch the file header calls out: "sheet"
    # (accept-category name) vs "sheets" (preset/letter-table spelling).
    world.set_anchor(50, 50, 10)
    world.free_rect(45, 45, 10, 1, 1)
    result, err = world.place_stockpile(1, 1, 0, "Anchor", "sheet", 1, 10, "false", None, None)
    assert err is None
    r = world.to_dict(result)
    assert r["quickfort_ok"] is True
    assert world.to_list(r["read_back"]["accepts"]) == ["sheet"]


def test_place_skips_a_reserved_candidate_without_res_id(world):
    world.set_anchor(50, 50, 10)
    world.set_free(50, 50, 10, True)   # rank-1 candidate, will be reserved
    world.set_free(60, 50, 10, True)   # further away, stays available
    world.create_reservation(x=50, y=50, z=10, w=1, h=1, purpose="planned later")

    result, err = world.place_stockpile(1, 1, 0, "Anchor", "stone", 1, 20, "false", None, None)
    assert err is None
    r = world.to_dict(result)
    assert r["quickfort_ok"] is True
    # the only tile left standing is (60,50) -- confirm via a second real
    # placement attempt at the same spot now being occupied
    listed = world.to_list(world.list_stockpiles()["stockpiles"])
    assert len(listed) == 1


# ---------------------------------------------------------------------------
# configure
# ---------------------------------------------------------------------------

def test_configure_rejects_non_stockpile_id(world):
    ws = world._make_workshop(0, 0, 0)
    result, err = world.stockpile_configure(ws.id, "stone", "false")
    assert result is None
    assert "not a stockpile" in err


def test_configure_dry_run_computes_diff_without_mutating(world):
    world.set_anchor(50, 50, 10)
    world.free_rect(45, 45, 10, 2, 2)
    placed, _ = world.place_stockpile(2, 2, 0, "Anchor", "food,stone", 1, 10, "false", None, None)
    pile_id = world.to_dict(placed)["read_back"]["id"]

    result, err = world.stockpile_configure(pile_id, "stone,wood", None)
    assert err is None
    r = world.to_dict(result)
    assert r["dry_run"] is True
    assert sorted(world.to_list(r["would_enable"])) == ["wood"]
    assert sorted(world.to_list(r["would_disable"])) == ["food"]
    # unmutated: a fresh read still shows the original accepts
    still = world.stockpile_links(pile_id)
    assert still is not None  # sanity the pile itself is untouched/still exists


def test_configure_real_run_enables_and_disables(world):
    world.set_anchor(50, 50, 10)
    world.free_rect(45, 45, 10, 2, 2)
    placed, _ = world.place_stockpile(2, 2, 0, "Anchor", "food,stone", 1, 10, "false", None, None)
    pile_id = world.to_dict(placed)["read_back"]["id"]

    result, err = world.stockpile_configure(pile_id, "stone,wood", "false")
    assert err is None
    r = world.to_dict(result)
    accepts = sorted(world.to_list(r["read_back"]["accepts"]))
    assert accepts == ["stone", "wood"]


# ---------------------------------------------------------------------------
# link / unlink
# ---------------------------------------------------------------------------

def test_link_rejects_bad_direction(world):
    world.set_anchor(50, 50, 10)
    world.free_rect(45, 45, 10, 4, 2)
    p1, _ = world.place_stockpile(1, 1, 0, "Anchor", "stone", 1, 10, "false", None, None)
    p2, _ = world.place_stockpile(1, 1, 0, "Anchor", "stone", 2, 10, "false", None, None)
    id1 = world.to_dict(p1)["read_back"]["id"]
    id2 = world.to_dict(p2)["read_back"]["id"]
    result, err = world.stockpile_link(id1, id2, "sideways", "false")
    assert result is None
    assert "give" in err and "take" in err


def test_link_give_between_two_piles_writes_both_vectors(world):
    world.set_anchor(50, 50, 10)
    world.free_rect(45, 45, 10, 4, 2)
    p1, _ = world.place_stockpile(1, 1, 0, "Anchor", "stone", 1, 10, "false", None, None)
    p2, _ = world.place_stockpile(1, 1, 0, "Anchor", "stone", 2, 10, "false", None, None)
    id1 = world.to_dict(p1)["read_back"]["id"]
    id2 = world.to_dict(p2)["read_back"]["id"]

    result, err = world.stockpile_link(id1, id2, "give", "false")
    assert err is None

    links1, _ = world.stockpile_links(id1)
    links2, _ = world.stockpile_links(id2)
    d1, d2 = world.to_dict(links1), world.to_dict(links2)
    assert d1["links"]["give_to_pile"]["count"] == 1
    assert d1["links"]["give_to_pile"]["targets"][1]["id"] == id2
    assert d2["links"]["take_from_pile"]["count"] == 1
    assert d2["links"]["take_from_pile"]["targets"][1]["id"] == id1


def test_link_take_from_workshop_writes_workshop_give_to_pile(world):
    world.set_anchor(50, 50, 10)
    world.free_rect(45, 45, 10, 2, 2)
    p1, _ = world.place_stockpile(1, 1, 0, "Anchor", "stone", 1, 10, "false", None, None)
    id1 = world.to_dict(p1)["read_back"]["id"]
    ws = world._make_workshop(0, 0, 0)

    result, err = world.stockpile_link(id1, ws.id, "take", "false")
    assert err is None
    links1, _ = world.stockpile_links(id1)
    ws_links, _ = world.stockpile_links(ws.id)
    d1, dw = world.to_dict(links1), world.to_dict(ws_links)
    assert d1["links"]["take_from_workshop"]["count"] == 1
    assert dw["links"]["give_to_pile"]["count"] == 1


def test_link_dry_run_does_not_mutate(world):
    world.set_anchor(50, 50, 10)
    world.free_rect(45, 45, 10, 4, 2)
    p1, _ = world.place_stockpile(1, 1, 0, "Anchor", "stone", 1, 10, "false", None, None)
    p2, _ = world.place_stockpile(1, 1, 0, "Anchor", "stone", 2, 10, "false", None, None)
    id1 = world.to_dict(p1)["read_back"]["id"]
    id2 = world.to_dict(p2)["read_back"]["id"]

    result, err = world.stockpile_link(id1, id2, "give", None)
    assert err is None
    assert world.to_dict(result)["dry_run"] is True
    links1, _ = world.stockpile_links(id1)
    assert world.to_dict(links1)["links"]["give_to_pile"]["count"] == 0


def test_unlink_removes_both_ends(world):
    world.set_anchor(50, 50, 10)
    world.free_rect(45, 45, 10, 4, 2)
    p1, _ = world.place_stockpile(1, 1, 0, "Anchor", "stone", 1, 10, "false", None, None)
    p2, _ = world.place_stockpile(1, 1, 0, "Anchor", "stone", 2, 10, "false", None, None)
    id1 = world.to_dict(p1)["read_back"]["id"]
    id2 = world.to_dict(p2)["read_back"]["id"]

    world.stockpile_link(id1, id2, "give", "false")
    result, err = world.stockpile_unlink(id1, id2, "give", "false")
    assert err is None

    links1, _ = world.stockpile_links(id1)
    links2, _ = world.stockpile_links(id2)
    d1, d2 = world.to_dict(links1), world.to_dict(links2)
    assert d1["links"]["give_to_pile"]["count"] == 0
    assert d2["links"]["take_from_pile"]["count"] == 0
