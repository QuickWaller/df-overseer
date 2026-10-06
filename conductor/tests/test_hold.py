"""The operator hold (conductor/hold.py, handoffs/2026-10-05-operator-hold.md):
the store and CLI, and the watchdog rule over the same fake fort the pause
watchdog's own tests use. No VM, no model.
"""

from __future__ import annotations

import json
import logging

import pytest

from conductor.hold import HoldStore, describe, hold_path_for, main as hold_main
from conductor.mcp_client import tool_name
from conductor.pause_watch import PauseWatchStore, Verdict
from conductor.runner import FakeRoleRunner
from conductor.status import log_cycle, status_from_cycle
from conductor.cycle import run_cycle
from conductor.tests.test_pause_watch import (
    NOW, POLICY, FakeFort, _cycle_deps, _ok_run, _report,
)

PROPOSAL = {"queue.overview": {"proposals": {"count": 1, "proposal_ids": ["p1"]}, "asks": {"count": 0, "ask_ids": []}}}


def _hold(tmp_path, **kw):
    HoldStore(tmp_path / "hold.json").set("keeping the fort paused to plan", who="op", now=NOW, **kw)


# ---------------------------------------------------------------------------
# store and CLI
# ---------------------------------------------------------------------------


def test_no_file_is_no_hold_and_set_clear_round_trip(tmp_path):
    store = HoldStore(tmp_path / "hold.json")
    assert store.read(NOW).held is False
    state = store.set("  planning \n a bedroom  ", who="op", now=NOW)
    assert state.held and state.reason == "planning a bedroom" and state.who == "op" and state.since == NOW
    assert store.read(NOW + 10).held is True
    assert store.clear() is True and store.read(NOW).held is False and store.clear() is False
    assert not list(tmp_path.glob(".hold.json.*.tmp"))  # atomic write leaves no temp file


def test_a_hold_needs_a_reason(tmp_path):
    with pytest.raises(ValueError):
        HoldStore(tmp_path / "hold.json").set("   ")


def test_an_expired_hold_reads_as_no_hold_and_is_logged(tmp_path, caplog):
    store = HoldStore(tmp_path / "hold.json")
    store.set("short", who="op", now=NOW, expires_in_seconds=60)
    assert store.read(NOW + 30).held is True
    with caplog.at_level(logging.WARNING, logger="conductor.hold"):
        state = store.read(NOW + 61)
    assert state.held is False and state.expired is True
    assert "expired" in caplog.text
    assert "expired" in describe(state)


@pytest.mark.parametrize("content", [
    "{not json", "[]", "{}", '{"reason": "", "since": 1}', '{"reason": "x"}',
    '{"reason": "x", "since": 1, "expires_at": "soon"}', '\xff\xfe',
])
def test_a_corrupt_hold_file_reads_as_held(tmp_path, content):
    path = tmp_path / "hold.json"
    path.write_bytes(content.encode("latin-1"))
    state = HoldStore(path).read(NOW)
    assert state.held is True and state.corrupt is True
    assert "unreadable" in state.reason


def test_the_cli_sets_shows_and_clears(tmp_path, capsys):
    cursors = tmp_path / "cursors.json"
    assert hold_main(["--cursor-store", str(cursors), "set", "--reason", "planning", "--who", "will"]) == 0
    assert hold_path_for(cursors).is_file() and hold_path_for(cursors).parent == tmp_path
    capsys.readouterr()
    assert hold_main(["--cursor-store", str(cursors), "show"]) == 0
    out = capsys.readouterr().out
    assert "HELD" in out and "planning" in out and "will" in out
    assert hold_main(["--cursor-store", str(cursors), "clear"]) == 0
    capsys.readouterr()
    assert hold_main(["--cursor-store", str(cursors), "show"]) == 0
    assert "no hold" in capsys.readouterr().out
    assert hold_main(["--cursor-store", str(cursors), "set", "--reason", " "]) == 2


def test_no_agent_surface_can_set_a_hold():
    """The hold is a file only the operator's CLI writes: no tool id, in the MCP
    registry or any role allowlist, mentions it."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    for sub in ("dfmcp", "agents"):
        for path in (root / sub).rglob("*"):
            if path.is_file() and path.suffix in {".py", ".yaml", ".md"} and "tests" not in path.parts:
                assert "conductor.hold" not in path.read_text(encoding="utf-8", errors="ignore"), path
                assert "hold.json" not in path.read_text(encoding="utf-8", errors="ignore"), path


# ---------------------------------------------------------------------------
# the watchdog rule, through the real cycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_held_plain_pause_takes_the_ordinary_path_even_past_the_grace(tmp_path):
    fort = FakeFort()
    _hold(tmp_path)
    store = PauseWatchStore(tmp_path / "pause_watch.json")
    state = store.load()
    state.episode_started = NOW - 10 * POLICY.plain_pause_grace_seconds  # long past the grace
    store.save(state)
    runner = FakeRoleRunner({"overseer": _ok_run(tools=[])})
    deps = _cycle_deps(tmp_path, fort, runner=runner, extra=PROPOSAL)
    result = await run_cycle(1, deps)
    assert result.pause_watch["verdict"] == "ordinary_held"
    assert result.pause_watch["held_by_operator"] is True
    called = [c[0] for c in deps.tool_caller.calls]
    assert "stuckjobs.find" in called and "queue.grade" in called   # the ordinary path ran
    assert [c["role"] for c in runner.calls] == ["overseer"]        # woken on its usual signal
    prompt = runner.calls[0]["prompt"]  # the ruling briefing (text), not an unexplained_pause wake
    assert "WAKE unexplained_pause" not in prompt and prompt.startswith("WAKE ")
    assert fort.resume_calls == 0 and fort.paused is True
    assert not result.pause_watch["alerts"]


@pytest.mark.asyncio
async def test_held_plain_pause_with_nothing_to_do_wakes_nobody_and_never_resumes(tmp_path):
    fort = FakeFort()
    _hold(tmp_path)
    deps = _cycle_deps(tmp_path, fort)
    result = await run_cycle(1, deps)
    assert deps.role_runner.calls == []
    assert "stuckjobs.find" in [c[0] for c in deps.tool_caller.calls]
    assert fort.resume_calls == 0 and fort.paused is True
    assert result.pause_watch["verdict"] == "ordinary_held"


@pytest.mark.asyncio
async def test_held_harmless_notice_is_dismissed_but_not_resumed(tmp_path):
    fort = FakeFort(popups=1, reports=[_report()])
    _hold(tmp_path)
    deps = _cycle_deps(tmp_path, fort)
    result = await run_cycle(1, deps)
    called = [c[0] for c in deps.tool_caller.calls]
    assert "pause.dismiss" in called and fort.popups == 0   # closing a notice is not resuming
    assert fort.resume_calls == 0 and fort.paused is True
    assert result.pause_watch["verdict"] == "ordinary_held" and result.pause_watch["resumed"] is False
    # And again next cycle, with the report now stale: still not escalated, still paused.
    fort.tick += 100000
    result2 = await run_cycle(2, _cycle_deps(tmp_path, fort))
    assert result2.pause_watch["verdict"] == "ordinary_held" and fort.resume_calls == 0


@pytest.mark.asyncio
async def test_held_threat_wakes_the_overseer_as_today_but_a_resume_true_verdict_does_not_resume(tmp_path):
    fort = FakeFort(reports=[_report("MEGABEAST_ARRIVAL")], verdict={"resume": True, "reason": "fine"})
    _hold(tmp_path)
    deps = _cycle_deps(tmp_path, fort)
    result = await run_cycle(1, deps)
    assert [c["role"] for c in deps.role_runner.calls] == ["overseer"]
    assert json.loads(deps.role_runner.calls[0]["prompt"])["wake_reason"] == "unexplained_pause"
    assert fort.resume_calls == 0 and fort.paused is True
    assert result.pause_watch["resumed"] is False
    assert any(a.get("suppressed") == "clock.resume" for a in result.pause_watch["actions"])
    assert result.pause_watch["held_by_operator"] is True


@pytest.mark.asyncio
async def test_held_tripwire_goes_through_the_tripwire_branch_minus_resume(tmp_path):
    fort = FakeFort(
        tripwire={"reason": "death", "tick": 1, "detail": "x"}, verdict={"resume": True, "reason": "fine"},
    )
    _hold(tmp_path)
    runner = FakeRoleRunner({"overseer": _ok_run(tools=[])})  # clean, no escalation
    deps = _cycle_deps(tmp_path, fort, runner=runner)
    result = await run_cycle(1, deps)
    assert result.tripwire is not None and result.escalated is False
    called = [c[0] for c in deps.tool_caller.calls]
    assert "clock.clear" in called and "clock.resume" not in called
    assert fort.resume_calls == 0 and fort.paused is True
    assert result.pause_watch["verdict"] == "held" and result.pause_watch["resumed"] is False
    assert result.hold["reason"]


@pytest.mark.asyncio
async def test_without_a_hold_the_same_tripwire_still_resumes(tmp_path):
    fort = FakeFort(
        tripwire={"reason": "death", "tick": 1, "detail": "x"}, verdict={"resume": True, "reason": "fine"},
    )
    runner = FakeRoleRunner({"overseer": _ok_run(tools=[])})
    deps = _cycle_deps(tmp_path, fort, runner=runner)
    await run_cycle(1, deps)
    assert "clock.resume" in [c[0] for c in deps.tool_caller.calls]


@pytest.mark.asyncio
async def test_clearing_the_hold_restores_todays_behaviour(tmp_path):
    fort = FakeFort(popups=1, reports=[_report()])
    _hold(tmp_path)
    r1 = await run_cycle(1, _cycle_deps(tmp_path, fort))
    assert fort.resume_calls == 0 and r1.pause_watch["verdict"] == "ordinary_held"
    HoldStore(tmp_path / "hold.json").clear()
    fort.tick += 100  # report still recent enough to be the pause's cause
    r2 = await run_cycle(2, _cycle_deps(tmp_path, fort))
    assert r2.hold is None and r2.pause_watch["held_by_operator"] is False
    assert fort.resume_calls == 1 and fort.paused is False and r2.pause_watch["resumed"] is True


@pytest.mark.asyncio
async def test_clearing_the_hold_on_a_plain_pause_restarts_the_grace_not_wakes_the_overseer(tmp_path):
    fort = FakeFort()
    _hold(tmp_path)
    await run_cycle(1, _cycle_deps(tmp_path, fort))
    HoldStore(tmp_path / "hold.json").clear()
    deps = _cycle_deps(tmp_path, fort)
    result = await run_cycle(2, deps)
    assert result.pause_watch["verdict"] == "wait" and deps.role_runner.calls == []


@pytest.mark.asyncio
async def test_a_corrupt_hold_file_never_resumes(tmp_path):
    fort = FakeFort(popups=1, reports=[_report()])
    (tmp_path / "hold.json").write_text("{garbage", encoding="utf-8")
    result = await run_cycle(1, _cycle_deps(tmp_path, fort))
    assert fort.resume_calls == 0 and fort.paused is True
    assert result.hold["corrupt"] is True


@pytest.mark.asyncio
async def test_dry_run_reports_the_hold_and_writes_nothing(tmp_path):
    fort = FakeFort()
    _hold(tmp_path)
    before = (tmp_path / "hold.json").read_bytes()
    deps = _cycle_deps(tmp_path, fort)
    deps.dry_run = True
    result = await run_cycle(1, deps)
    assert result.plan["hold"]["reason"] == "keeping the fort paused to plan"
    assert result.pause_watch["verdict"] == "ordinary_held"
    assert (tmp_path / "hold.json").read_bytes() == before
    assert not (tmp_path / "pause_watch.json").exists()
    assert fort.resume_calls == 0 and deps.role_runner.calls == []


@pytest.mark.asyncio
async def test_the_hold_reaches_the_status_block_and_the_log_line(tmp_path, caplog):
    fort = FakeFort()
    _hold(tmp_path)
    result = await run_cycle(1, _cycle_deps(tmp_path, fort))
    block = status_from_cycle(result)["pause_watch"]
    assert block["held"]["reason"] == "keeping the fort paused to plan"
    assert block["held"]["who"] == "op" and block["held"]["since"] == NOW
    assert block["verdict"] == "ordinary_held"
    with caplog.at_level(logging.INFO, logger="conductor.status"):
        log_cycle(result)
    assert "operator HOLD in force" in caplog.text and "keeping the fort paused to plan" in caplog.text


@pytest.mark.asyncio
async def test_with_no_hold_the_status_block_is_unchanged(tmp_path):
    fort = FakeFort(paused=False)
    result = await run_cycle(1, _cycle_deps(tmp_path, fort))
    assert result.hold is None
    assert "held" not in status_from_cycle(result)["pause_watch"]
