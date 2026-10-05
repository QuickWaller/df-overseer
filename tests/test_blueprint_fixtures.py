"""Fixture outputs of the blueprint verbs (docs/CONDUCTOR-EXECUTION.md 6.2,
P3-M2), saved under dfmcp/tests/fixtures/blueprint/ for the server's verdict
tests (stage 2C).

They are derived from the Lua SOURCE and the REAL templates, run through the
fake DFHack world, not observed on a live fort: the first real outputs come
from the supervised bedroom, which records them and re-runs the dependent
test. This test regenerates every fixture in memory and compares it with the
file, so a change to the Lua that alters an output fails here until the
fixtures are regenerated:

    BLUEPRINT_FIXTURES_UPDATE=1 python -m pytest tests/test_blueprint_fixtures.py

JSON null is the Lua NULL sentinel mapped back to None, so the files look
like the real `dfhack-run` output.
"""

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("lupa")

from tests.test_blueprint_lua_logic import DIG_OK, World  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "dfmcp" / "tests" / "fixtures" / "blueprint"
NULL = "\x00"

# per template: dig phases (labels), the meta/furnish phases in order, the
# tile of each furnishing and the zone tiles, all in the stub's site at (10,10)
SCENARIOS = {
    "bedroom-cell-v1": {
        "shell": "bedroom_cell_v1_shell",
        "phases": ["bedroom_cell_v1_shell", "bedroom_cell_v1_zone", "bedroom_cell_v1_build", "bedroom_cell_v1_finish"],
        "output": {
            "dig": DIG_OK,
            "zone": "Blueprint statistics:\n  Zones designated: 1\n  Zone tiles designated: 9\n",
            "build": "Blueprint statistics:\n  Buildings designated: 1\n",
            "meta": ("Blueprint statistics:\n  Zones designated: 1\n  Zone tiles designated: 9\n"
                     "  Buildings designated: 1\n  Blueprints applied: 2\n"),
        },
        "furniture": (11, 11),
    },
    "office-room-v2": {
        "shell": "office_room_v2_shell",
        "phases": ["office_room_v2_shell", "office_room_v2_floor", "office_room_v2_build",
                   "office_room_v2_zone", "office_room_v2_finish"],
        "output": {
            "dig": DIG_OK,
            "zone": "Blueprint statistics:\n  Zones designated: 1\n  Zone tiles designated: 9\n",
            "build": "Blueprint statistics:\n  Buildings designated: 1\n",
            "meta": ("Blueprint statistics:\n  Zones designated: 1\n  Zone tiles designated: 9\n"
                     "  Buildings designated: 1\n  Blueprints applied: 2\n"),
        },
        "furniture": (12, 12),
    },
}


def _clean(v):
    if v == NULL:
        return None
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    return v


def _mode_of(world, bp, phase):
    plan, _ = world.call("plan_template", bp)
    return next(p["mode"] for p in plan["phases"] if p["label"] == phase)


def _generate(tmp_path, bp):
    sc = SCENARIOS[bp]
    out = {}
    w = World(tmp_path)
    try:
        def rec(name, pair):
            r, err = pair
            out[name] = _clean({"error": err} if err else r)

        w.stone_block(10, 10)
        rec("reserve_dry_run", w.call("reserve_site", bp, "fixture room", "Well"))
        rec("reserve_success", w.call("reserve_site", bp, "fixture room", "Well", "false"))
        rec("reserve_refusal_overlap", w.call("reserve_site", bp, "second room", "Well", "false"))
        rec("reservations", (w.call("list_reservations")[0], None))
        # the first phase, on the reservation
        shell = sc["shell"]
        w.qf_output(sc["output"]["dig"])
        rec("apply_%s_dry_run" % shell, w.call("apply_phase", bp, shell, "res-1"))
        rec("apply_%s_success" % shell, w.call("apply_phase", bp, shell, "res-1", "false"))
        rec("sites", (w.call("list_sites")[0], None))
        rec("status_no_phase_after_shell_apply", w.call("site_status", "site-1"))
        # later phases are refused until the shell is dug and smoothed
        for phase in sc["phases"][1:]:
            mode = _mode_of(w, bp, phase)
            if mode != "dig":
                rec("apply_%s_refused_shell_pending" % phase, w.call("apply_phase", bp, phase, "site-1", "false"))
        w.carve_and_smooth()
        for phase in sc["phases"][1:]:
            mode = _mode_of(w, bp, phase)
            w.qf_output(sc["output"][mode])
            rec("apply_%s_dry_run" % phase, w.call("apply_phase", bp, phase, "site-1"))
            rec("apply_%s_success" % phase, w.call("apply_phase", bp, phase, "site-1", "false"))
        # status per phase: shell dug, furniture pending, zone absent
        w.lua.execute("set_building(%d, %d, 5, 7, 0, 3)" % sc["furniture"])
        for phase in sc["phases"]:
            rec("status_%s_furniture_pending" % phase, w.call("site_status", "site-1", phase))
        # status per phase: floor smoothed, furniture complete, zone present
        w.lua.execute("for x = 11, 13 do for y = 11, 13 do set_tile(x, y, 5, 'FLOOR', 'STONE', 'SMOOTH'); "
                      "set_zone(x, y, 5, true) end end")
        w.lua.execute("set_building(%d, %d, 5, 7, 3, 3)" % sc["furniture"])
        for phase in sc["phases"]:
            rec("status_%s_complete" % phase, w.call("site_status", "site-1", phase))
        rec("release_any_pending_dry_run", w.call("release_site", "site-1", None, "true"))
    finally:
        w.close()
    return out


@pytest.mark.parametrize("bp", sorted(SCENARIOS))
def test_fixtures_match_the_lua_source(tmp_path, bp):
    generated = _generate(tmp_path, bp)
    path = FIXTURE_DIR / (bp + ".json")
    text = json.dumps(generated, indent=2, sort_keys=True) + "\n"
    if os.environ.get("BLUEPRINT_FIXTURES_UPDATE"):
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    assert path.exists(), "run once with BLUEPRINT_FIXTURES_UPDATE=1 to create " + str(path)
    assert json.loads(path.read_text(encoding="utf-8")) == json.loads(text), (
        "blueprint fixtures are stale; regenerate with BLUEPRINT_FIXTURES_UPDATE=1")


@pytest.mark.parametrize("bp", sorted(SCENARIOS))
def test_fixtures_hold_the_fields_stage_2c_declares(tmp_path, bp):
    data = json.loads((FIXTURE_DIR / (bp + ".json")).read_text(encoding="utf-8"))
    sc = SCENARIOS[bp]
    assert data["reserve_dry_run"]["would_reserve"] is True
    assert data["reserve_dry_run"]["level"] == 0 and "finish_plan" in data["reserve_dry_run"]
    assert data["reserve_success"]["handle"] == "res-1"
    assert data["reserve_refusal_overlap"]["refused"] is True
    shell = sc["shell"]
    assert data["apply_%s_dry_run" % shell]["dry_run"] is True
    ok = data["apply_%s_success" % shell]
    assert ok["site"]["handle"] == "site-1" and ok["site"]["level"] == 0
    assert ok["designated"]["dig_tiles"] == 25
    last = sc["phases"][-1]
    assert data["status_%s_complete" % last]["phase"]["done"] is True
    assert data["status_%s_furniture_pending" % last]["phase"]["done"] is False
