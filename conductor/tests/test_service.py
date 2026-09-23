"""conductor/service.py: load_charters against the real repo, and
run_forever's own loop/status/--once logic over a fully fake CycleDeps.
build_deps/main are never exercised here (they construct the real
StreamableHTTPMCPClient/DockerOpenClawRunner and would need a live
dfmcp server and real docker -- hard line: no VM, no Docker run)."""

from __future__ import annotations

import json

import pytest

from conductor.archive import CycleArchive
from conductor.cursors import CursorStore
from conductor.cycle import CycleDeps
from conductor.mcp_client import FakeToolCaller
from conductor.policy import load_policy
from conductor.runner import FakeRoleRunner
from conductor.service import ROLES, load_charters, run_forever
from conductor.triage import ADVISORS, CONSULTANT, OVERSEER


def _quiet_tools():
    return {
        "vitals.summary": {
            "ok": True, "alive": 20, "dead_total": 0,
            "worst_hunger_status": "fine", "worst_thirst_status": "fine", "warning_count": 0,
        },
        "clock.status": {
            "paused": False, "fps": 100, "cur_year": 1, "cur_year_tick": 1000,
            "abs_tick": 403200 + 1000, "armed": True, "tripwire": None,
        },
        "overview.get": {
            "tier1": {"population": 20},
            "tier2": {"in_game_date": "year 1, month 1, day 1, tick 1000", "alerts": []},
        },
        "queue.overview": {
            "proposals": {"count": 0, "proposal_ids": []},
            "asks": {"count": 0, "ask_ids": []},
        },
        "diff.since": lambda args: {"cursor": str(args.get("cursor", 0)), "events": []},
        "orders.list": {"orders": [], "manager_appointed": True},
        "queue.grade": {
            "current_game_tick": 403200 + 1000, "graded_at": "x",
            "graded_count": 0, "graded": [], "unexecuted_count": 0, "unexecuted": [],
        },
    }


def _deps(tmp_path, *, dry_run=False):
    cursor_store = CursorStore(tmp_path / "cursors.json")
    cursor_store.set("__routine_review__", 403200 + 1000)  # avoid a spurious routine review
    return CycleDeps(
        tool_caller=FakeToolCaller(_quiet_tools()),
        role_runner=FakeRoleRunner(),
        policy=load_policy(),
        cursor_store=cursor_store,
        archive=CycleArchive(tmp_path / "cycles"),
        charters={role: f"# {role}" for role in ROLES},
        models={role: "deepseek/deepseek-v4-flash" for role in ROLES},
        dry_run=dry_run,
    )


# ---------------------------------------------------------------------------
# load_charters: against the real, committed agents/ directory
# ---------------------------------------------------------------------------


def test_load_charters_reads_the_real_role_md_for_every_role():
    charters = load_charters()
    assert set(charters) == set(ROLES)
    for role, text in charters.items():
        assert text.strip(), f"{role}'s role.md is empty"


# ---------------------------------------------------------------------------
# run_forever: --once, status writes, and the loop itself
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_forever_once_runs_exactly_one_cycle(tmp_path):
    deps = _deps(tmp_path)
    status_path = tmp_path / "status.json"

    cycles_run = await run_forever(deps, status_path=status_path, cycle_interval_seconds=999, once=True)

    assert cycles_run == 1
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["last_cycle"]["cycle_index"] == 1


@pytest.mark.asyncio
async def test_run_forever_writes_a_starting_status_before_the_first_cycle(tmp_path):
    deps = _deps(tmp_path)
    status_path = tmp_path / "status.json"

    # A sleep that raises after the first iteration, so this test proves
    # the loop actually intends to continue (reaches sleep) without really
    # looping forever.
    calls = {"n": 0}

    async def _stop_after_one(_seconds):
        calls["n"] += 1
        raise SystemExit("stop the loop")

    with pytest.raises(SystemExit):
        await run_forever(
            deps, status_path=status_path, cycle_interval_seconds=0.001,
            once=False, sleep=_stop_after_one,
        )
    assert calls["n"] == 1
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["last_cycle"]["cycle_index"] == 1  # the cycle before the sleep did complete


@pytest.mark.asyncio
async def test_run_forever_loops_multiple_cycles_when_not_once(tmp_path):
    deps = _deps(tmp_path)
    status_path = tmp_path / "status.json"

    calls = {"n": 0}

    async def _stop_after_three(_seconds):
        calls["n"] += 1
        if calls["n"] >= 3:
            raise SystemExit("stop")

    with pytest.raises(SystemExit):
        await run_forever(
            deps, status_path=status_path, cycle_interval_seconds=0.001,
            once=False, sleep=_stop_after_three,
        )
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["last_cycle"]["cycle_index"] == 3


@pytest.mark.asyncio
async def test_run_forever_dry_run_still_writes_status_each_cycle(tmp_path):
    deps = _deps(tmp_path, dry_run=True)
    status_path = tmp_path / "status.json"

    await run_forever(deps, status_path=status_path, cycle_interval_seconds=999, once=True)

    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["last_cycle"]["dry_run"] is True
    # A dry run archives nothing, but the cycle itself still ran and wrote status.
    assert not (deps.archive.root).exists() or list(deps.archive.root.glob("cycle-*")) == []
