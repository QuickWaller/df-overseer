"""handoffs/2026-10-01-labor-quota.md: df-overseer-labor.lua's new
`quota`/`quota-status` commands over autolabor.

Loads the REAL df-overseer-labor.lua against a fake DFHack world
(tests/lua_stubs/dfhack_labor_quota_world.lua), so labor name validation,
the autolabor-enabled refusal, the DRY_RUN validate-without-mutating path,
the `autolabor LABOR MIN MAX [POOL]` shell-out, and the
parse-`autolabor list`-into-a-status-table logic are all exercised against
the actual production code, not a re-description of it.

What this file does NOT prove (see the stub's own header): the fake
`autolabor list` output is a hand-formatted stand-in for the real plugin's
`print_labor` text, built from research/2026-10-01-quartermaster-levers.md
§2's cited source quote, never run against the real plugin. A live
`autolabor list` call against Uniboslan is the only thing that confirms the
real text matches this parser's regex byte for byte.

Skipped when lupa is not installed (it is not a repo dependency).
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts" / "dfhack"
STUBS = Path(__file__).resolve().parent / "lua_stubs"
LABOR_LUA = SCRIPTS / "df-overseer-labor.lua"
STUB = STUBS / "dfhack_labor_quota_world.lua"


class LaborQuotaWorld:
    def __init__(self):
        self.lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        load = self.lua.eval("function(src, name) return load(src, name) end")

        stub_chunk = load(STUB.read_text(encoding="utf-8"), "labor_quota_world")
        stub_chunk()

        labor_chunk = load(LABOR_LUA.read_text(encoding="utf-8"), "labor.lua")
        labor_chunk()

        g = self.lua.globals()
        self._labor_quota = g["labor_quota"]
        self._labor_quota_status = g["labor_quota_status"]
        self._set_autolabor_enabled = g["set_autolabor_enabled"]

    @staticmethod
    def _as_pair(raw):
        # lupa's unpack_returned_tuples=True hands back a bare python tuple
        # for a >1-value Lua return, but the SINGLE object itself for a
        # 1-value return (never wrapped) -- both functions here return
        # either (true, table) or (false, string), so `a, b = fn(...)` in
        # plain Python would wrongly try to iterate a lone value's own
        # pairs on some paths. Normalise to a real 2-tuple here instead.
        if isinstance(raw, tuple):
            if len(raw) >= 2:
                return raw[0], raw[1]
            if len(raw) == 1:
                return raw[0], None
            return None, None
        return raw, None

    def labor_quota(self, *args):
        return self._as_pair(self._labor_quota(*args))

    def labor_quota_status(self, names=None):
        arg = self.lua.table_from(names) if names else None
        return self._as_pair(self._labor_quota_status(arg))

    def set_autolabor_enabled(self, v):
        self._set_autolabor_enabled(v)

    def to_dict(self, v):
        if hasattr(v, "items"):
            d = {}
            for k, val in v.items():
                d[k] = self.to_dict(val)
            return d
        return v


@pytest.fixture
def world():
    return LaborQuotaWorld()


# --------------------------------------------------------------------------
# quota: validation
# --------------------------------------------------------------------------

def test_quota_rejects_unknown_labor(world):
    ok, err = world.labor_quota("NOT_A_LABOR", "1", "5")
    assert ok is False
    assert "unknown labor" in err


def test_quota_rejects_non_numeric_min(world):
    ok, err = world.labor_quota("MASON", "abc", "5")
    assert ok is False
    assert "MIN" in err


def test_quota_rejects_non_numeric_max(world):
    ok, err = world.labor_quota("MASON", "1", "xyz")
    assert ok is False
    assert "MAX" in err


def test_quota_rejects_min_greater_than_max(world):
    ok, err = world.labor_quota("MASON", "5", "1")
    assert ok is False
    assert "MIN" in err and "MAX" in err


def test_quota_rejects_negative_values(world):
    ok, err = world.labor_quota("MASON", "-1", "5")
    assert ok is False
    assert "non-negative" in err


def test_quota_rejects_bad_pool(world):
    ok, err = world.labor_quota("MASON", "1", "5", "not-a-number")
    assert ok is False
    assert "POOL" in err


# --------------------------------------------------------------------------
# quota: autolabor-enabled refusal (races the plugin exactly like set_labor)
# --------------------------------------------------------------------------

def test_quota_refuses_when_autolabor_disabled(world):
    world.set_autolabor_enabled(False)
    ok, err = world.labor_quota("MASON", "1", "5")
    assert ok is False
    assert "not enabled" in err


# --------------------------------------------------------------------------
# quota: DRY_RUN (default true) validates without mutating
# --------------------------------------------------------------------------

def test_quota_dry_run_by_default_does_not_call_autolabor(world):
    ok, payload = world.labor_quota("MASON", "2", "9", "40")
    assert ok is True
    d = world.to_dict(payload)
    assert d["dry_run"] is True
    assert d["would_set"] == {"minimum": 2, "maximum": 9, "pool": 40}
    # No CLI call at all -- a dry run must not touch autolabor's live state.
    assert world.to_dict(world.lua.globals()["AUTOLABOR_CALLS"]) == {}


def test_quota_explicit_dry_run_true_string_also_skips_the_call(world):
    ok, payload = world.labor_quota("MASON", "2", "9", None, "true")
    assert ok is True
    assert world.to_dict(payload)["dry_run"] is True


# --------------------------------------------------------------------------
# quota: a real write reads its own result back, never an echo
# --------------------------------------------------------------------------

def test_quota_real_write_reads_back_rather_than_echoing(world):
    # MASON starts at minimum=1, maximum=5, pool=50, currently=3 in the
    # stub's canned autolabor state. Ask for maximum=8 with NO pool -- the
    # real autolabor keeps its own prior/default pool when none is passed,
    # which an echo of the caller's own (nil) pool could never reproduce.
    ok, payload = world.labor_quota("MASON", "1", "8", None, "false")
    assert ok is True
    d = world.to_dict(payload)
    assert d["dry_run"] is False
    read_back = d["read_back"]
    assert read_back["mode"] == "automatic"
    assert read_back["minimum"] == 1
    assert read_back["maximum"] == 8
    # The stub's prior pool (50), never the caller's omitted value.
    assert read_back["pool"] == 50
    # The real CLI call actually happened, with the requested args, and a
    # SEPARATE `list` call happened afterward for the read-back -- two
    # calls, not one, is the whole point of "never an echo".
    calls = world.to_dict(world.lua.globals()["AUTOLABOR_CALLS"])
    assert calls[1] == {1: "MASON", 2: "1", 3: "8"}
    assert calls[2] == {1: "list"}


def test_quota_reports_autolabor_cli_failure(world):
    # MAX=999 is the stub's sentinel for a simulated non-OK CLI result.
    ok, err = world.labor_quota("MASON", "1", "999", None, "false")
    assert ok is False
    assert "non-OK" in err


# --------------------------------------------------------------------------
# quota-status
# --------------------------------------------------------------------------

def test_quota_status_one_labor_reports_target_and_two_independent_actuals(world):
    status, errors = world.labor_quota_status(["MASON"])
    status = world.to_dict(status)
    errors = world.to_dict(errors)
    assert errors == {}
    entry = status["MASON"]
    assert entry["mode"] == "automatic"
    assert entry["minimum"] == 1
    assert entry["maximum"] == 5
    assert entry["pool"] == 50
    # autolabor's own self-report...
    assert entry["autolabor_currently"] == 3
    # ...and the independently-read live roster (only 2 of 3 citizens have
    # MASON on in the stub) -- deliberately different, to prove these are
    # two real reads, not one value copied into two fields.
    assert entry["actual_enabled_count"] == 2


def test_quota_status_disabled_and_haulers_modes(world):
    status, _ = world.labor_quota_status(["BREWER", "HAUL_STONE"])
    status = world.to_dict(status)
    assert status["BREWER"]["mode"] == "disabled"
    assert status["HAUL_STONE"]["mode"] == "haulers"


def test_quota_status_unknown_labor_is_an_error_never_a_default(world):
    status, errors = world.labor_quota_status(["NOT_A_LABOR"])
    status = world.to_dict(status)
    errors = world.to_dict(errors)
    assert "NOT_A_LABOR" not in status
    assert "NOT_A_LABOR" in errors


def test_quota_status_labor_autolabor_never_mentions_is_an_error(world):
    # MINE is a real df.unit_labor name in the stub but has no entry in
    # autolabor's own `list` output -- the honest gap, never a guessed 0.
    status, errors = world.labor_quota_status(["MINE"])
    status = world.to_dict(status)
    errors = world.to_dict(errors)
    assert "MINE" not in status
    assert "no autolabor entry" in errors["MINE"]


def test_quota_status_with_no_labor_argument_reports_everything_autolabor_has(world):
    status, errors = world.labor_quota_status(None)
    status = world.to_dict(status)
    errors = world.to_dict(errors)
    assert set(status.keys()) == {"MASON", "BREWER", "HAUL_STONE"}
    assert errors == {}
