"""handoffs/2026-10-07-wake-cleanup.md: the wake reasons that re-fired every
cycle, each exercised through a real `run_cycle` over the fakes (no VM, no
model), plus the pure pieces in `conductor/lanes.py`."""

from __future__ import annotations

import pytest

from conductor import lanes
from conductor.cycle import run_cycle
from conductor.policy import load_policy
from conductor.tests.test_cycle import _base_tools, _deps, _queue_overview

pytestmark = pytest.mark.asyncio

POLICY = load_policy()


def _tools(proposal_ids, ask_ids=()):
    tools = _base_tools()
    tools["queue.overview"] = _queue_overview(
        proposals={"count": len(proposal_ids), "proposal_ids": list(proposal_ids)},
        asks={"count": len(ask_ids), "ask_ids": list(ask_ids), "to": {"consultant": list(ask_ids)} if ask_ids else {}},
    )
    return tools


# ---------------------------------------------------------------------------
# Item 1: queue_pending is an edge
# ---------------------------------------------------------------------------


async def test_a_deferred_proposal_does_not_rewake_the_overseer(tmp_path):
    first = await run_cycle(1, _deps(tmp_path, tools=_tools(["proposal-0001"])))
    assert "overseer" in first.roles_woken
    # Same pending list next cycle: the Overseer saw it and left it (a defer).
    second = await run_cycle(2, _deps(tmp_path, tools=_tools(["proposal-0001"])))
    assert "overseer" not in second.roles_woken


async def test_a_new_proposal_wakes_the_overseer_again(tmp_path):
    await run_cycle(1, _deps(tmp_path, tools=_tools(["proposal-0001"])))
    second = await run_cycle(2, _deps(tmp_path, tools=_tools(["proposal-0001", "proposal-0002"])))
    assert "overseer" in second.roles_woken


async def test_an_answered_ask_open_at_the_defer_wakes_the_overseer(tmp_path):
    await run_cycle(1, _deps(tmp_path, tools=_tools(["proposal-0001"], ["ask-0001"])))
    # The ask was answered meanwhile (nothing open now).
    third = await run_cycle(2, _deps(tmp_path, tools=_tools(["proposal-0001"], [])))
    assert "overseer" in third.roles_woken


async def test_a_deferred_proposal_wakes_again_after_the_recheck_window(tmp_path):
    await run_cycle(1, _deps(tmp_path, tools=_tools(["proposal-0001"])))
    n = POLICY.overseer_defer_recheck_cycles
    woken = []
    for i in range(2, n + 3):
        r = await run_cycle(i, _deps(tmp_path, tools=_tools(["proposal-0001"])))
        woken.append("overseer" in r.roles_woken)
    assert woken[:n - 1] == [False] * (n - 1)
    assert woken[n - 1] is True


def test_a_proposal_past_the_briefing_cap_is_never_recorded_as_seen():
    state = lanes.LaneState()
    ids = [f"proposal-{i:04d}" for i in range(1, 11)]
    lanes.record_overseer_seen(state, ids, [])
    assert set(state.overseer_seen) == set(ids[:lanes.OVERSEER_BRIEF_CAP])
    fresh, quiet = lanes.split_pending_for_overseer(POLICY, state, ids, [])
    assert fresh == ids[lanes.OVERSEER_BRIEF_CAP:]
    assert [q[0] for q in quiet] == ids[:lanes.OVERSEER_BRIEF_CAP]


def test_ids_that_left_the_pending_list_are_forgotten():
    state = lanes.LaneState()
    lanes.record_overseer_seen(state, ["proposal-0001", "proposal-0002"], [])
    lanes.record_overseer_seen(state, ["proposal-0002"], [])
    assert set(state.overseer_seen) == {"proposal-0002"}


def test_overseer_seen_and_cycles_survive_a_save_and_load(tmp_path):
    store = lanes.LaneStore(tmp_path / "lane_state.json")
    state = lanes.LaneState(cycles=4)
    lanes.record_overseer_seen(state, ["proposal-0001"], ["ask-0001"])
    store.save(state)
    loaded = store.load()
    assert loaded.cycles == 4 and loaded.overseer_seen == state.overseer_seen
