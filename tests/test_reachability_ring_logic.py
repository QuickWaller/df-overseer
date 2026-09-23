"""Regression for the ring-fallback reachability algorithm in
scripts/dfhack/df-overseer-reachability.lua, including the Well's exact
shape (handoffs/2026-09-23-landmark-reachability.md).

**What this test actually proves, stated plainly (per this project's own
verify-the-verification rule).** This environment has no Lua interpreter
(checked this session: no `lua`/`lua5.1`/`lua5.3`/`luajit` on PATH) and this
stream is offline-only (no VM, no live DFHack, no `dfhack-run`), so the real
`.lua` file's own bytes cannot be executed here. What follows is a
line-for-line Python PORT of `resolve_group`/`reachable_between`/
`group_matches`'s control flow (ring offsets, blind-spot shape check,
standable test, tri-state combination), copied by hand from
`scripts/dfhack/df-overseer-reachability.lua` -- NOT a mechanical extraction,
so it can silently drift from the real file if that file is edited later
without updating this port. `test_port_mirrors_lua_source_constants` below is
the one guard against silent drift: it re-reads the real .lua file's own
source text and asserts the constants this port hardcodes (ring radius, ring
offset count, shape names) still appear in it. This test suite proves the
ALGORITHM this handoff specifies is sound against the exact regression case
the orchestrating session read live (the Well's centre tile a RampTop,
group 0 to all 8 neighbours, 4 of those 8 reaching the Still) -- it does not
prove the deployed Lua bytes behave identically; that needs a live DFHack run,
which is out of scope for this offline stream (see the stream's own report).

The scenario below is built from the orchestrating session's own live read
(handoffs/2026-09-23-landmark-reachability.md "Why" section), not invented:
the Well's own centroid tile is a RAMP_TOP with walkable group 0 (nobody can
stand on it); of its 8 neighbours, 4 share the Still's own group and 4 do
not (modelled here as WALL tiles, group 0, genuinely not standable -- not
the RAMP/RAMP_TOP blind-spot shape, so no fallback rescues them either,
which is the correct, honest behaviour: a wall tile really isn't standable).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Set, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
REACHABILITY_LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-reachability.lua"

RING_RADIUS = 1
RING_OFFSETS = [
    (0, -1), (1, -1), (1, 0), (1, 1),
    (0, 1), (-1, 1), (-1, 0), (-1, -1),
]

BLIND_SPOT_SHAPES = {"RAMP", "RAMP_TOP"}

Coord = Tuple[int, int, int]


class World:
    """A tiny stand-in for the live map: an explicit {(x,y,z): (group, shape)}
    table. Any coordinate not listed reads group 0, shape None (matching the
    real file's own pcall-guarded fallback to group 0 / nil shape on a read
    that errors or returns nothing usable)."""

    def __init__(self, tiles: Optional[Dict[Coord, Tuple[int, str]]] = None):
        self.tiles = dict(tiles or {})

    def probe(self, x: int, y: int, z: int) -> Tuple[int, bool, bool]:
        group, shape = self.tiles.get((x, y, z), (0, None))
        standable = group != 0
        blind_spot = (group == 0) and (shape in BLIND_SPOT_SHAPES)
        return group, standable, blind_spot


def resolve_group(world: World, x: int, y: int, z: int):
    """Port of resolve_group(x, y, z) -> {group, how} | nil, reason."""
    group, standable, blind_spot = world.probe(x, y, z)
    if standable:
        return {"group": group, "how": "at"}, None

    for dx, dy in RING_OFFSETS:
        g, s, _ = world.probe(x + dx, y + dy, z)
        if s:
            return {"group": g, "how": "adjacent"}, None

    if blind_spot:
        return None, (
            "own tile reads walkable group 0 on a RAMP/RAMP_TOP shape, this "
            "build's own known blind spot; no standable tile found within "
            f"{RING_RADIUS} tile(s)"
        )
    return None, f"no standable tile found at the position or within {RING_RADIUS} tile(s) of it"


def reachable_between(world: World, a: Coord, b: Coord):
    """Port of reachable_between(ax,ay,az, bx,by,bz) -> {status, ...}."""
    ra, err_a = resolve_group(world, *a)
    rb, err_b = resolve_group(world, *b)

    if ra is None or rb is None:
        reasons = []
        if ra is None:
            reasons.append(f"from: {err_a}")
        if rb is None:
            reasons.append(f"to: {err_b}")
        return {"status": "unknown", "reason": "; ".join(reasons)}

    if ra["group"] == rb["group"]:
        return {"status": "reachable", "from_via": ra["how"], "to_via": rb["how"],
                "from_group": ra["group"], "to_group": rb["group"]}
    return {"status": "unreachable", "from_via": ra["how"], "to_via": rb["how"],
            "from_group": ra["group"], "to_group": rb["group"]}


def group_matches(world: World, x: int, y: int, z: int, target_groups: Set[int]):
    """Port of group_matches(x,y,z, target_groups) -> matched, how, group."""
    group, standable, _ = world.probe(x, y, z)
    if standable and group in target_groups:
        return True, "at", group

    for dx, dy in RING_OFFSETS:
        g, s, _ = world.probe(x + dx, y + dy, z)
        if s and g in target_groups:
            return True, "adjacent", g

    return False, None, group


# --------------------------------------------------------------------------
# The Well's exact shape, per handoffs/2026-09-23-landmark-reachability.md's
# "Why" section (the orchestrating session's own live read, quoted there):
#   - the Well's own centre tile is a RampTop, not standable;
#   - all eight tiles around the Well report canWalkBetween=false to the
#     Well tile itself (i.e. every one of the 8 neighbours' OWN reading is
#     what the old, centroid-only code compared against -- irrelevant here,
#     since the fix never compares against the Well's centroid directly);
#   - four tiles around the Well can walk to the Still.
# Modelled as: Well centroid group 0/RAMP_TOP; 4 of its 8 neighbours group 5
# (the Still's own group, standable floor); the other 4 neighbours group 0,
# shape WALL (genuinely not standable, not the blind-spot shape).
# --------------------------------------------------------------------------

WELL = (0, 0, 0)
STILL = (10, 10, 0)

WELL_WORLD = World({
    WELL: (0, "RAMP_TOP"),
    (0, -1, 0): (5, "FLOOR"),
    (1, -1, 0): (5, "FLOOR"),
    (1, 0, 0): (0, "WALL"),
    (1, 1, 0): (0, "WALL"),
    (0, 1, 0): (5, "FLOOR"),
    (-1, 1, 0): (0, "WALL"),
    (-1, 0, 0): (0, "WALL"),
    (-1, -1, 0): (5, "FLOOR"),
    STILL: (5, "FLOOR"),
})


def test_well_regression_resolves_reachable_via_adjacent_ring():
    """The regression case this whole stream exists for: a landmark whose
    centre tile is not standable, but whose surrounding tiles connect to
    the rest of the fort, must report reachable -- not the old false
    negative (walkable=false to every neighbour)."""
    result = reachable_between(WELL_WORLD, WELL, STILL)
    assert result["status"] == "reachable"
    assert result["from_via"] == "adjacent"  # resolved via the Well's own ring, not its centroid
    assert result["to_via"] == "at"          # the Still's own centroid is directly standable
    assert result["from_group"] == result["to_group"] == 5


def test_well_own_centroid_alone_is_not_standable():
    """Sanity check on the scenario itself: probing the Well's own centre
    tile directly (no ring fallback) is NOT standable -- confirms this test
    is actually exercising the fallback path, not accidentally passing
    because the centroid was fine all along."""
    group, standable, blind_spot = WELL_WORLD.probe(*WELL)
    assert standable is False
    assert blind_spot is True  # RAMP_TOP + group 0 = the known blind spot, not a real wall


def test_old_centroid_only_logic_would_have_reported_unreachable():
    """Reproduces the bug this stream fixes: comparing the two centroids
    DIRECTLY (the pre-fix behaviour, canWalkBetween(well_centroid,
    still_centroid) with no fallback) reads as not-same-group, because the
    Well's own centroid is group 0. This is the false negative
    (handoffs/2026-09-23-landmark-reachability.md's "Why" section) --
    kept here so a future change can't silently reintroduce it without this
    test also changing.
    """
    well_group, well_standable, _ = WELL_WORLD.probe(*WELL)
    still_group, still_standable, _ = WELL_WORLD.probe(*STILL)
    assert well_standable is False
    assert still_standable is True
    assert well_group != still_group  # 0 vs 5 -- the old code's false "not walkable"


def test_no_standable_tile_anywhere_nearby_is_unknown_not_unreachable():
    """A landmark whose centroid AND every one of its 8 neighbours are
    unstandable (e.g. sealed in solid rock) must report "unknown", never
    silently become "unreachable" -- the collapse this whole stream exists
    to stop."""
    isolated = (100, 100, 0)
    world = World({isolated: (0, "WALL")})  # every neighbour defaults to (0, None) too
    result = reachable_between(world, isolated, STILL)
    assert result["status"] == "unknown"
    assert "isolated" not in result  # sanity: no stray field name collision
    assert "reason" in result and result["reason"]


def test_two_standable_but_different_groups_is_unreachable_not_unknown():
    """Both sides resolve to a real standable tile, and the groups genuinely
    differ -- this is the one case that SHOULD say unreachable, and must
    not be softened into unknown just because the fix adds a fallback."""
    island = (50, 50, 0)
    world = World({island: (9, "FLOOR"), STILL: (5, "FLOOR")})
    result = reachable_between(world, island, STILL)
    assert result["status"] == "unreachable"
    assert result["from_group"] == 9
    assert result["to_group"] == 5


def test_group_matches_at_own_tile():
    matched, how, group = group_matches(WELL_WORLD, *STILL, {5})
    assert matched is True
    assert how == "at"
    assert group == 5


def test_group_matches_via_adjacent_ring_for_blind_spot_tile():
    """The threat.lua fix: a candidate standing exactly on the Well's own
    RAMP_TOP tile (group 0, blind spot) must still match the citizen group
    5 via the adjacent-ring fallback, not be silently dropped."""
    matched, how, group = group_matches(WELL_WORLD, *WELL, {5})
    assert matched is True
    assert how == "adjacent"
    assert group == 5


def test_group_matches_false_when_truly_isolated():
    isolated = (100, 100, 0)
    world = World({isolated: (0, "WALL")})
    matched, how, group = group_matches(world, *isolated, {5})
    assert matched is False
    assert how is None


# --------------------------------------------------------------------------
# Drift guard: if the real .lua file's own ring size, offset count or
# blind-spot shape names ever change, this port silently stops matching it.
# This does not re-derive correctness from the Lua source (impossible
# without a Lua interpreter); it only catches the case where someone edits
# the real constants and forgets this port exists.
# --------------------------------------------------------------------------

def test_port_mirrors_lua_source_constants():
    assert REACHABILITY_LUA.is_file(), f"expected the shared helper at {REACHABILITY_LUA}"
    text = REACHABILITY_LUA.read_text(encoding="utf-8")
    assert "local RING_RADIUS = 1" in text, (
        "RING_RADIUS changed in df-overseer-reachability.lua -- update "
        "RING_RADIUS/RING_OFFSETS in this port to match"
    )
    # The 8-neighbour ring, same coordinates this port hardcodes.
    for dx, dy in RING_OFFSETS:
        token = "{dx = %d, dy = %d}" % (dx, dy)
        assert token in text, f"expected ring offset {token!r} in df-overseer-reachability.lua"
    assert "df.tiletype_shape.RAMP" in text
    assert "df.tiletype_shape.RAMP_TOP" in text
    assert "function resolve_group(" in text
    assert "function reachable_between(" in text
    assert "function group_matches(" in text
