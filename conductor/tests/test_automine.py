"""The automine pass (conductor/automine.py, research/2026-10-09-auto-mine.md):
the plumbing around `automine.scan`, its gating in the cycle, the policy switch
and the cavern note's trip into the Overseer's next briefing. No VM, no model."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from conductor.automine import AutomineStore, run_automine
from conductor.briefing import build_briefing, build_ruling_briefing
from conductor.cycle import run_cycle
from conductor.hold import HoldStore, hold_path_for
from conductor.mcp_client import MCPToolError
from conductor.policy import AutominePolicy, PolicyError, load_policy
from conductor.runner import FakeRoleRunner
from conductor.tests.test_cycle import _base_tools, _deps
from conductor.triage import Wake

pytestmark = pytest.mark.asyncio

POLICY_YAML = Path(__file__).resolve().parent.parent / "policy.yaml"
SCAN = {"ok": True, "designated": 3, "in_reservation": 1, "by_mineral": {"HEMATITE": 3}}
CAVERN = dict(SCAN, cavern={"breaches": 1, "cleared_tiles": 4, "note": "Cavern breach reported by the game."})


def _names(deps):
    return [c[0] for c in deps.tool_caller.calls]


def _on(deps):
    return dataclasses.replace(deps.policy, automine=AutominePolicy(enabled=True, max_per_call=25))


class Caller:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    async def __call__(self, tool, args):
        self.calls.append((tool, dict(args)))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


# ---------------------------------------------------------------- run_automine


async def test_a_scan_reports_its_counts_and_passes_the_bound():
    c = Caller(SCAN)
    rep = await run_automine(c, enabled=True, held=False, escalated=False, store=None, max_per_call=25)
    assert rep.ran and rep.designated == 3 and rep.in_reservation == 1
    assert c.calls == [("automine.scan", {"max": 25})]


@pytest.mark.parametrize("kw,why", [
    ({"enabled": False}, "disabled in policy"),
    ({"held": True}, "operator hold"),
    ({"escalated": True}, "an escalation this cycle"),
])
async def test_the_scan_is_not_called_when_gated(kw, why):
    c = Caller(SCAN)
    args = dict(enabled=True, held=False, escalated=False, store=None)
    args.update(kw)
    rep = await run_automine(c, **args)
    assert not rep.ran and rep.skipped == why and c.calls == []


async def test_a_tool_error_or_a_bad_reply_is_a_skip_never_a_raise():
    for reply in (MCPToolError("unknown tool automine.scan"), {"ok": False, "error": "no"}, "text"):
        rep = await run_automine(Caller(reply), enabled=True, held=False, escalated=False, store=None)
        assert not rep.ran and rep.skipped


async def test_a_cavern_note_is_stored_once_and_taken_once(tmp_path):
    store = AutomineStore(tmp_path / "automine_state.json")
    rep = await run_automine(Caller(CAVERN), enabled=True, held=False, escalated=False, store=store)
    assert rep.cavern_breaches == 1 and rep.notes
    await run_automine(Caller(CAVERN), enabled=True, held=False, escalated=False, store=store)
    assert store.take() == ["Cavern breach reported by the game."]    # the same note is not stacked
    assert store.take() == []


async def test_an_unreadable_store_reads_empty(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{not json", encoding="utf-8")
    assert AutomineStore(p).take() == []


# ---------------------------------------------------------------------- policy


async def test_the_shipped_policy_turns_it_on_and_a_hand_built_one_leaves_it_off():
    shipped = load_policy(POLICY_YAML)
    assert shipped.automine.enabled is True and shipped.automine.max_per_call == 40
    assert AutominePolicy().enabled is False


async def test_a_bad_automine_block_is_refused(tmp_path):
    bad = tmp_path / "policy.yaml"
    bad.write_text(POLICY_YAML.read_text(encoding="utf-8") + "\nautomine:\n  enabled: maybe\n", encoding="utf-8")
    with pytest.raises(PolicyError):
        load_policy(bad)


# ----------------------------------------------------------------------- cycle


async def test_the_cycle_runs_the_pass_once_when_enabled(tmp_path):
    tools = _base_tools()
    tools["automine.scan"] = SCAN
    deps = _deps(tmp_path, tools=tools)
    deps.policy = _on(deps)
    result = await run_cycle(1, deps)
    assert _names(deps).count("automine.scan") == 1
    assert result.automine["ran"] and result.automine["designated"] == 3


async def test_an_operator_hold_blocks_the_pass_even_with_allow_execution(tmp_path):
    tools = _base_tools()
    tools["automine.scan"] = SCAN
    deps = _deps(tmp_path, tools=tools)
    deps.policy = _on(deps)
    HoldStore(hold_path_for(deps.cursor_store.path)).set("keep paused", who="t", allow_execution=True)
    result = await run_cycle(1, deps)
    assert "automine.scan" not in _names(deps)
    assert result.automine["skipped"] == "operator hold"


async def test_a_dry_run_and_a_disabled_policy_make_no_call(tmp_path):
    tools = _base_tools()
    tools["automine.scan"] = SCAN
    dry = _deps(tmp_path / "a", tools=tools, dry_run=True)
    dry.policy = _on(dry)
    await run_cycle(1, dry)
    off = _deps(tmp_path / "b", tools=tools)
    off.policy = dataclasses.replace(off.policy, automine=AutominePolicy(enabled=False))
    await run_cycle(1, off)
    assert "automine.scan" not in _names(dry) and "automine.scan" not in _names(off)


async def test_a_failing_scan_never_stops_the_cycle(tmp_path):
    deps = _deps(tmp_path, tools=_base_tools())     # automine.scan not configured: raises MCPToolError
    deps.policy = _on(deps)
    result = await run_cycle(1, deps)
    assert result.automine["ran"] is False and result.automine["skipped"]


def _overseer_tools():
    tools = _base_tools()
    tools["queue.overview"] = {"proposals": {"count": 1, "proposal_ids": ["proposal-0001"]},
                               "asks": {"count": 0, "ask_ids": []}}
    return tools


async def test_the_scan_stores_a_cavern_note_for_the_next_cycle(tmp_path):
    tools = _overseer_tools()
    tools["automine.scan"] = CAVERN
    deps = _deps(tmp_path, tools=tools, runner=FakeRoleRunner())
    deps.policy = _on(deps)
    await run_cycle(1, deps)
    # the Overseer already ran this cycle, before the scan: it was not told yet
    ran = [c["prompt"] for c in deps.role_runner.calls if c["role"] == "overseer"]
    assert ran and "Cavern breach" not in ran[0]
    store = AutomineStore(deps.cursor_store.path.with_name("automine_state.json"))
    assert store.load() == ["Cavern breach reported by the game."]


async def test_a_stored_cavern_note_reaches_the_overseers_briefing_once(tmp_path):
    deps = _deps(tmp_path, tools=_overseer_tools(), runner=FakeRoleRunner())
    store = AutomineStore(deps.cursor_store.path.with_name("automine_state.json"))
    store.add("Cavern breach reported by the game.")
    await run_cycle(1, deps)
    prompts = [c["prompt"] for c in deps.role_runner.calls if c["role"] == "overseer"]
    assert prompts and "NOTE Cavern breach reported by the game." in prompts[0]
    assert store.load() == []                                  # taken: said once


# -------------------------------------------------------------------- briefing


async def test_both_briefings_carry_the_note_only_when_given():
    wake = Wake("routine_review", "d", ("overseer",), "full_speed")
    vitals = {"alive": 5}
    plain = build_briefing(role="overseer", game_tick=1, wake=wake, vitals=vitals, diff_events=[],
                           queue_summary={"count": 0})
    assert "automine" not in plain
    noted = build_briefing(role="overseer", game_tick=1, wake=wake, vitals=vitals, diff_events=[],
                           queue_summary={"count": 0}, automine_notes=["a" * 500])
    assert len(noted["automine"][0]) == 240
    text = build_ruling_briefing(game_tick=1, wake=wake, vitals=vitals, alerts=[], pending_brief=None,
                                 automine_notes=["Cavern breach."])
    assert "NOTE Cavern breach." in text
    assert "NOTE" not in build_ruling_briefing(game_tick=1, wake=wake, vitals=vitals, alerts=[], pending_brief=None)
