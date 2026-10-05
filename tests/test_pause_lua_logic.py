"""handoffs/2026-10-05-pause-safety.md: df-overseer-pause.lua's `why` and
`dismiss`, loaded as the REAL script against a fake DFHack world
(tests/lua_stubs/dfhack_pause_world.lua).

Proves this project's own logic: the cause classification order, the
bounded report window, DO_MEGA flag lookup by announcement type, the
data-driven popup-kind registry (a new kind is a table entry), strategy
ordering and the disabled-strategy rule, and that dismiss never resumes the
game or touches a latch.

What this file does NOT prove: that clicking the real Okay button closes a
real mega popup on this install. The stub closes the popup when a click
lands on the cell where the label was drawn, which is the assumption. The
supervised live test in the handoff is what settles it.

Skipped when lupa is not installed (it is not a repo dependency).
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts" / "dfhack"
STUBS = Path(__file__).resolve().parent / "lua_stubs"
PAUSE_LUA = SCRIPTS / "df-overseer-pause.lua"
STUB = STUBS / "dfhack_pause_world.lua"


class PauseWorld:
    def __init__(self):
        self.lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        load = self.lua.eval("function(src, name) return load(src, name) end")
        load(STUB.read_text(encoding="utf-8"), "pause_world")()
        load(PAUSE_LUA.read_text(encoding="utf-8"), "pause.lua")()
        self.g = self.lua.globals()
        self.g["reset_world"]()

    def why(self, window=None):
        return self.to_py(self.g["pause_why"](window))

    def dismiss(self, cap=None):
        return self.to_py(self.g["pause_dismiss"](cap))

    def call(self, name, *args):
        return self.g[name](*args)

    def to_py(self, v):
        if hasattr(v, "items"):
            d = {k: self.to_py(val) for k, val in v.items()}
            if d and all(isinstance(k, int) for k in d):
                return [d[k] for k in sorted(d)]
            return d
        return v


@pytest.fixture
def world():
    return PauseWorld()


def _succession(world, tick=5000):
    world.call("add_report", 1, 0, "Meng has claimed the position of queen.", 100, tick)


# ---------------------------------------------------------------------------
# why: cause classification
# ---------------------------------------------------------------------------


def test_a_running_fort_reports_running(world):
    world.call("set_paused", False)
    out = world.why()
    assert out["cause"] == "running"
    assert out["popups_pending"] == 0


def test_a_plain_pause_with_nothing_explaining_it(world):
    out = world.why()
    assert out["paused"] is True
    assert out["cause"] == "plain_pause"
    assert not out["recent_reports"]


def test_a_pending_mega_popup_is_a_popup_cause_and_its_text_is_read(world):
    world.call("add_popup", "Meng Tiredpicks has claimed the position of queen.")
    out = world.why()
    assert out["cause"] == "popup"
    assert out["popups_pending"] == 1
    mega = next(k for k in out["popups"] if k["kind"] == "mega")
    assert mega["pending"] == 1
    assert "queen" in mega["texts"][0]


def test_a_recent_do_mega_report_with_no_popup_is_an_announcement_cause(world):
    _succession(world)
    out = world.why()
    assert out["cause"] == "announcement"
    rep = out["recent_reports"][0]
    assert rep["type"] == "FORT_POSITION_SUCCESSION"
    assert "DO_MEGA" in rep["flags"]


def test_a_report_whose_type_has_neither_flag_is_not_a_cause(world):
    world.call("add_report", 1, 2, "Migrants arrived.", 100, 5000)  # MIGRANT_ARRIVAL, no flags
    out = world.why()
    assert out["cause"] == "plain_pause"
    assert not out["recent_reports"]


def test_the_report_window_excludes_old_reports(world):
    _succession(world, tick=100)  # 4900 ticks before the current tick
    assert world.why()["cause"] == "plain_pause"
    assert world.why(window=10000)["cause"] == "announcement"


def test_threat_class_report_type_is_surfaced_by_name(world):
    world.call("add_report", 1, 1, "A megabeast arrives.", 100, 5000)
    out = world.why()
    assert out["recent_reports"][0]["type"] == "MEGABEAST_ARRIVAL"


def test_a_latched_tripwire_wins_over_every_other_cause(world):
    world.call("add_popup", "a box")
    trip = world.lua.table_from({"reason": "death", "tick": 1, "detail": "x"})
    world.call("set_tripwire", trip)
    out = world.why()
    assert out["cause"] == "tripwire"
    assert out["popups_pending"] == 1  # still reported, for the record


def test_a_non_dwarfmode_screen_is_a_modal_cause(world):
    world.call("set_viewscreen", "viewscreen_savegamest")
    out = world.why()
    assert out["cause"] == "modal_viewscreen"
    assert out["viewscreen_type"] == "viewscreen_savegamest"


def test_an_open_help_box_is_a_popup_of_its_own_kind(world):
    world.call("set_help_open", True)
    out = world.why()
    assert out["cause"] == "popup"
    help_kind = next(k for k in out["popups"] if k["kind"] == "tutorial_help")
    assert help_kind["pending"] == 1


def test_long_popup_text_is_truncated(world):
    world.call("add_popup", "x" * 1000)
    out = world.why()
    mega = next(k for k in out["popups"] if k["kind"] == "mega")
    assert len(mega["texts"][0]) < 300


# ---------------------------------------------------------------------------
# dismiss
# ---------------------------------------------------------------------------


def test_dismiss_closes_one_popup_with_the_okay_button_and_records_what_it_said(world):
    world.call("add_popup", "Meng has claimed the position of queen.")
    out = world.dismiss()
    assert out["ok"] is True
    assert out["remaining"] == 0
    assert world.call("popup_count") == 0
    done = out["dismissed"][0]
    assert done["kind"] == "mega" and done["strategy"] == "click_text"
    assert "queen" in done["said"]


def test_dismiss_walks_a_queue_of_boxes_through_more(world):
    world.call("add_popup", "first")
    world.call("add_popup", "second")
    world.call("add_popup", "third")
    out = world.dismiss()
    assert out["ok"] is True
    assert world.call("popup_count") == 0
    assert len(out["dismissed"]) == 3


def test_dismiss_respects_the_cap(world):
    for t in ("a", "b", "c"):
        world.call("add_popup", t)
    out = world.dismiss(cap=2)
    assert world.call("popup_count") == 1
    assert out["remaining"] == 1
    assert out["ok"] is False


def test_dismiss_reports_failure_when_the_click_does_nothing_and_never_force_removes(world):
    world.call("add_popup", "stubborn")
    world.call("set_buttons_close_popup", False)
    out = world.dismiss()
    assert out["ok"] is False
    assert out["remaining"] == 1
    assert world.call("popup_count") == 1  # the disabled pop_front strategy did not run
    strategies = [a["strategy"] for a in out["attempts"]]
    assert "pop_front" not in strategies


def test_dismiss_with_nothing_pending_does_nothing(world):
    out = world.dismiss()
    assert out["ok"] is True
    assert not out["dismissed"]
    assert world.call("click_count") == 0


def test_dismiss_closes_the_help_box_by_its_own_strategy(world):
    world.call("set_help_open", True)
    out = world.dismiss()
    assert out["ok"] is True
    assert out["dismissed"][0]["kind"] == "tutorial_help"
    assert world.why()["popups_pending"] == 0


def test_dismiss_rejects_a_zero_cap(world):
    out = world.dismiss(cap=0)
    assert out["ok"] is False


def test_dismiss_never_resumes_or_clears_a_latch(world):
    world.call("add_popup", "a box")
    trip = world.lua.table_from({"reason": "death", "tick": 1, "detail": "x"})
    world.call("set_tripwire", trip)
    world.dismiss()
    after = world.why()
    assert after["paused"] is True
    assert after["tripwire"] is not None


def test_a_new_popup_kind_is_a_table_entry_not_new_branches(world):
    # Register a kind from outside the script: detector + one strategy name.
    world.lua.execute(
        """
        local pending = 1
        table.insert(POPUP_KINDS, {
          id = "fake_kind",
          detect = function() return pending, { "fake" } end,
          strategies = { { name = "fake_close" } },
        })
        STRATEGIES.fake_close = function() pending = 0; return true, "closed fake" end
        """
    )
    out = world.dismiss()
    assert out["ok"] is True
    assert out["dismissed"][0]["kind"] == "fake_kind"
