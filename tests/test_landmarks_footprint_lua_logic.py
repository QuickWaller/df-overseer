"""handoffs/2026-09-30-reservation-gaps.md item 3: df-overseer-landmarks.lua's
build_at_landmark used to check only its own anchor tile against a
reservation, because it never learned BLUEPRINT_FILE's footprint size. The
fix reuses df-overseer-blueprint.lua's own quickfort-CSV parser, extracted to
the dependency-free df-overseer-blueprint-parse.lua leaf (see that file's own
header for why it could not simply reqscript df-overseer-blueprint.lua
directly: that file already reqscripts df-overseer-landmarks.lua, so the
reverse edge would close a two-way reqscript cycle).

This runs the REAL df-overseer-landmarks.lua against a small fake DFHack
world, with the REAL df-overseer-reservations.lua and the REAL
df-overseer-blueprint-parse.lua both loaded from source (dependency-free
leaves -- real integration, not a second parallel fake of either), matching
tests/lua_stubs/dfhack_blueprint_world.lua's own established pattern for
df-overseer-reservations.lua.

Skipped when lupa is not installed (it is not a repo dependency).
"""

import os
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts" / "dfhack"
STUBS = Path(__file__).resolve().parent / "lua_stubs"
LANDMARKS_LUA = SCRIPTS / "df-overseer-landmarks.lua"
RESERVATIONS_LUA = SCRIPTS / "df-overseer-reservations.lua"
PARSE_LUA = SCRIPTS / "df-overseer-blueprint-parse.lua"
STUB = STUBS / "dfhack_landmarks_footprint_world.lua"

ANCHOR = (5, 5, 5)


class LandmarksWorld:
    def __init__(self, tmp_path):
        guest = tmp_path / "guest"
        (guest / "dfhack-config" / "blueprints").mkdir(parents=True)
        self._old = os.getcwd()
        os.chdir(guest)

        self.lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("RESERVATIONS_LUA_PATH = %r" % str(RESERVATIONS_LUA))
        self.lua.execute("BLUEPRINT_PARSE_LUA_PATH = %r" % str(PARSE_LUA))
        self.lua.execute("HAZARD_LUA_PATH = %r" % str(PARSE_LUA.parent / "df-overseer-hazard.lua"))
        self.lua.execute("DIGCANCEL_LUA_PATH = %r" % str(PARSE_LUA.parent / "df-overseer-digcancel.lua"))
        self.lua.execute(STUB.read_text(encoding="utf-8"))
        load = self.lua.eval("function(src, name) return load(src, name) end")
        chunk = load(LANDMARKS_LUA.read_text(encoding="utf-8"), "landmarks.lua")
        assert not isinstance(chunk, tuple), chunk
        chunk()
        g = self.lua.globals()
        # get_landmark_centroid's real implementation depends on the full
        # embark-site/buildings/burrows machinery this stub does not model
        # (see the stub file's own header); overridden directly to the fixed
        # anchor this test's blueprint files are placed relative to.
        cx, cy, cz = ANCHOR
        g["get_landmark_centroid"] = self.lua.eval(
            "function(cx, cy, cz) return function(name) if name == 'Nowhere' then return nil end return cx, cy, cz end end"
        )(cx, cy, cz)
        self.build_at_landmark = g["build_at_landmark"]
        reqscript = g["reqscript"]
        self.reservations_mod = reqscript("df-overseer-reservations")
        # A single-Lua-value success return (`return {...}`) reaches lupa as
        # the bare table, not a 1-tuple -- unpacking it directly in Python
        # would iterate the TABLE's own contents instead of treating it as
        # one value. This wrapper normalises to always exactly two Lua
        # return values (result, err), matching real Lua's own "missing
        # values become nil" rule.
        self._call2 = self.lua.eval(
            "function(fn, name, bf, res_id, override) local a, b = fn(name, bf, res_id, override) return a, b end"
        )

    def close(self):
        os.chdir(self._old)

    def write_blueprint(self, filename, text):
        path = Path("dfhack-config") / "blueprints" / filename
        path.write_text(text, encoding="utf-8")

    def create_reservation(self, **rec):
        table = self.lua.table_from(rec)
        return self.reservations_mod.create(table)

    def build(self, name, blueprint_file, res_id=None, override=None):
        result, err = self._call2(self.build_at_landmark, name, blueprint_file, res_id, override)
        return result, err


# A 3x3 #build blueprint (top-left at the landmark's own anchor, per
# build_at_landmark's own top-left-anchoring rule) -- its footprint covers
# tiles (5..7, 5..7) when anchored at ANCHOR (5,5,5), NOT just the (5,5,5)
# anchor tile itself.
BLUEPRINT_3X3 = "\n".join([
    "#build",
    "a,a,a",
    "a,a,a",
    "a,a,a",
]) + "\n"


@pytest.fixture
def world(tmp_path):
    w = LandmarksWorld(tmp_path)
    yield w
    w.close()


def test_a_reservation_inside_the_footprint_but_off_the_anchor_is_now_caught(world):
    """The real, live gap this item fixes: a reservation covering (6,6,5),
    inside the 3x3 footprint but not the (5,5,5) anchor tile itself, used to
    be invisible to the old anchor-only check. It must now refuse."""
    world.write_blueprint("shed.csv", BLUEPRINT_3X3)
    handle = world.create_reservation(x=6, y=6, z=5, w=1, h=1, purpose="a planned pantry")
    assert handle == "res-1"

    result, err = world.build("Anchor", "shed.csv")
    assert result is None
    assert "res-1" in err
    assert "a planned pantry" in err


def test_a_reservation_outside_the_footprint_is_not_touched(world):
    world.write_blueprint("shed.csv", BLUEPRINT_3X3)
    world.create_reservation(x=40, y=40, z=5, w=1, h=1, purpose="somewhere else")

    result, err = world.build("Anchor", "shed.csv")
    assert err is None
    assert result["quickfort_ok"] is True


def test_res_id_with_override_holds_the_whole_footprint_not_just_the_anchor(world):
    """landmarks.build has no KIND concept (checked against the fixed
    literal "landmark_build", which no template ever declares as an allowed
    kind -- by construction always refused inside a reservation unless
    OVERRIDE). With RES_ID + OVERRIDE naming the reservation that covers a
    footprint tile, the build proceeds -- the override applies across the
    full footprint check, not only the anchor tile."""
    world.write_blueprint("shed.csv", BLUEPRINT_3X3)
    handle = world.create_reservation(x=6, y=6, z=5, w=1, h=1, purpose="a planned pantry")

    result, err = world.build("Anchor", "shed.csv", res_id=handle, override="testing the footprint hold")
    assert err is None
    assert result["quickfort_ok"] is True


def test_res_id_without_override_still_refused_by_kind(world):
    """Confirms the above isn't succeeding for the wrong reason: RES_ID
    alone (no OVERRIDE) still refuses, since "landmark_build" is never on
    any reservation's own allowed_kinds by construction."""
    world.write_blueprint("shed.csv", BLUEPRINT_3X3)
    handle = world.create_reservation(x=6, y=6, z=5, w=1, h=1, purpose="a planned pantry")

    result, err = world.build("Anchor", "shed.csv", res_id=handle)
    assert result is None
    assert "OVERRIDE" in err


def test_unparseable_blueprint_file_is_refused_not_treated_as_anchor_only(world):
    """No fallback to the old anchor-only behaviour: if the footprint can't
    be read at all, this refuses outright."""
    result, err = world.build("Anchor", "does-not-exist.csv")
    assert result is None
    assert "footprint" in err


def test_footprint_wider_than_advertised_still_gets_the_full_check(world):
    """A 2x1 blueprint anchored at (5,5,5): the SECOND tile (6,5,5) is
    reserved, the anchor itself is not -- still caught, proving this is a
    real per-tile footprint check, not merely a bigger single-tile check at
    a different point."""
    world.write_blueprint("hall.csv", "#build\na,a\n")
    handle = world.create_reservation(x=6, y=5, z=5, w=1, h=1, purpose="a planned corridor")

    result, err = world.build("Anchor", "hall.csv")
    assert result is None
    assert handle in err
