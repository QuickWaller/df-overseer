"""handoffs/2026-10-07-wake-cleanup.md items 6 and 8: a missed prediction wakes
only its proposer; an answered ask wakes its asker once (when the lane opts in)."""

from __future__ import annotations

import dataclasses

import pytest

from conductor import lanes
from conductor.cycle import run_cycle
from conductor.policy import load_policy
from conductor.tests.test_cycle import _base_tools, _deps, _grade_result

POLICY = load_policy()


def _miss(proposer):
    row = {"id": 1, "status": "graded_false"}
    if proposer is not None:
        row["proposer"] = proposer
    return _grade_result(graded_count=1, graded=[row])


@pytest.mark.asyncio
async def test_a_miss_wakes_only_its_proposer(tmp_path):
    tools = _base_tools(**{"queue.grade": _miss("quartermaster")})
    result = await run_cycle(1, _deps(tmp_path, tools=tools))
    assert result.roles_woken == ("quartermaster",)


@pytest.mark.asyncio
async def test_a_miss_with_no_named_proposer_falls_back_to_both_advisors(tmp_path):
    tools = _base_tools(**{"queue.grade": _miss(None)})
    result = await run_cycle(1, _deps(tmp_path, tools=tools))
    assert result.roles_woken == ("architect", "quartermaster")


@pytest.mark.asyncio
async def test_a_miss_by_a_role_this_build_does_not_run_wakes_nobody(tmp_path):
    tools = _base_tools(**{"queue.grade": _miss("ghostrole")})  # a role no build runs
    result = await run_cycle(1, _deps(tmp_path, tools=tools))
    assert result.roles_woken == ()


def test_the_store_names_the_proposer_on_a_due_prediction(tmp_path):
    from dfqueue import store
    from dfqueue.tests._helpers import make_proposal
    from dfqueue.tests.test_store import _accept_and_execute

    path = tmp_path / "q.sqlite3"
    written = store.append(make_proposal(), path, game_tick=0)
    _accept_and_execute(path, written["id"], execution_cycle=0)
    due = store.pending_due(path, 10**6)
    assert [r["proposer"] for r in due] == ["architect"]


def _asking_policy():
    lt = dict(POLICY.lane_triggers)
    lt["architect"] = dataclasses.replace(lt["architect"], answers=True)
    return dataclasses.replace(POLICY, lane_triggers=lt)


def test_an_answered_ask_wakes_its_asker_once_when_enabled():
    pol, state = _asking_policy(), lanes.LaneState()
    known = lanes.attribute_new_asks(state, "architect", set(), ["ask-0001"])
    assert known == {"ask-0001"} and state.askers == {"ask-0001": "architect"}
    lanes.apply_answers(pol, state, ["ask-0001"])  # still open
    assert not state.pending
    lanes.apply_answers(pol, state, [])  # answered
    assert list(state.pending["architect"]) == ["answer:ask-0001"]
    assert [w.reason for w in lanes.lane_wakes(pol, state, {})] == ["answer_ready"]
    state.pending.clear()
    lanes.apply_answers(pol, state, [])  # not again
    assert not state.pending


def test_an_answer_wakes_nobody_when_the_lane_flag_is_off():
    lt = dict(POLICY.lane_triggers)
    lt["architect"] = dataclasses.replace(lt["architect"], answers=False)
    policy = dataclasses.replace(POLICY, lane_triggers=lt)
    state = lanes.LaneState()
    lanes.attribute_new_asks(state, "architect", set(), ["ask-0001"])
    lanes.apply_answers(policy, state, [])
    assert not state.pending and not state.askers
