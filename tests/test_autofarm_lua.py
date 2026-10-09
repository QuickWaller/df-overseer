"""scripts/dfhack/df-overseer-autofarm.lua: the conductor-only autofarm writer (register
2026-10-09). Runs the real file in a Lua VM with a recording `dfhack.run_command_silent`.
Skipped when lupa is not installed. Not live-verified: the plugin itself is untested here."""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "dfhack" / "df-overseer-autofarm.lua"


def make(fail_on=None):
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute("""
        calls = {}
        FAIL = nil
        dfhack_flags = {module = true}
        function require(name) return {encode = function(v) return 'json' end} end
        dfhack = {run_command_silent = function(...)
            local parts = {...}
            local line = table.concat(parts, ' ')
            calls[#calls + 1] = line
            if FAIL and string.find(line, FAIL, 1, true) then return 'bad', 1 end
            return 'ok: ' .. line, 0
        end}
    """)
    if fail_on:
        lua.execute(f"FAIL = {fail_on!r}".replace("'", '"'))
    lua.execute(SCRIPT.read_text(encoding="utf-8"))
    return lua


def calls(lua):
    return [lua.eval("calls")[i] for i in range(1, len(lua.eval("calls")) + 1)]


def test_sets_default_each_crop_then_enables_and_reads_status():
    lua = make()
    r, err = lua.eval("function() local a, b = autofarm_set('0', 'MUSHROOM_HELMET_PLUMP=60,POD_SWEET_POD=0'); return a, b end")()
    assert err is None and r["ok"] is True and r["default"] == 0 and r["enabled"] is True
    assert calls(lua) == [
        "autofarm default 0", "autofarm threshold 60 MUSHROOM_HELMET_PLUMP",
        "autofarm threshold 0 POD_SWEET_POD", "enable autofarm", "autofarm status",
    ]


@pytest.mark.parametrize("default,levels", [
    ("-1", None), ("x", None), ("1.5", None), ("5", "plump=3"), ("5", "A=B"), ("5", "A=-1"), ("5", "A=1;rm"),
])
def test_bad_numbers_and_tokens_are_refused_before_anything_runs(default, levels):
    lua = make()
    arg = "nil" if levels is None else repr(levels)
    r, err = lua.eval(f"function() local a, b = autofarm_set({default!r}, {arg}); return a, b end")()
    assert r is None and err
    assert calls(lua) == []


def test_a_failing_command_stops_the_sequence():
    lua = make(fail_on="threshold 5 B")
    r, err = lua.eval("function() local a, b = autofarm_set('1', 'A=2,B=5,C=9'); return a, b end")()
    assert r is None and "B" in err
    assert not any("C" in c for c in calls(lua)) and not any(c.startswith("enable") for c in calls(lua))


def test_default_only_still_enables():
    lua = make()
    r, err = lua.eval("function() local a, b = autofarm_set('0', nil); return a, b end")()
    assert err is None and calls(lua)[:2] == ["autofarm default 0", "enable autofarm"]
