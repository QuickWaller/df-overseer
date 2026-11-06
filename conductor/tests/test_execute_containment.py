"""Execute containment (research/2026-10-09-gateway-sessions-v1.md 15.9): the conductor runs a
step only if the ruling its project came from was written inside an Overseer activation the
conductor opened. Anything else is not run and is named once."""

from __future__ import annotations

import pytest

from conductor.cycle import run_cycle
from conductor.execute import ExecuteState, ExecuteStore, contained_record_ids, record_activation, run_execute
from conductor.policy import ExecutionPolicy
from conductor.runner import FakeRoleRunner
from conductor.tests.contain import contained_state
from conductor.tests.test_cycle import _deps
from conductor.tests.test_cycle_execute import _names, _tools
from conductor.tests.test_execute import Script, SUCCESS, _proj, _ready

pytestmark = pytest.mark.asyncio


def _snap(ruling="ruling-0009"):
    return {"open_projects": [_proj(ruling_id=ruling)], "ready_steps": [_ready(1)]}


async def _run(script, state):
    return await run_execute(script, ExecutionPolicy(), state, game_tick=10)


async def test_a_ruling_outside_every_activation_is_not_run_and_named_once():
    script = Script(_snap(), {"queue.run_step": SUCCESS})
    state = ExecuteState()
    first = await _run(script, state)
    assert "queue.run_step" not in script.names()
    assert first.steps_run == 0
    assert len(first.errors) == 1 and "ruling-0009" in first.errors[0] and "project-0001/s1" in first.errors[0]
    second = await _run(script, state)
    assert second.errors == [] and "queue.run_step" not in script.names()


async def test_a_ruling_inside_an_overseer_activation_runs():
    script = Script(_snap(), {"queue.run_step": SUCCESS})
    report = await _run(script, contained_state("ruling-0009"))
    assert script.names().count("queue.run_step") == 1 and report.errors == []


async def test_an_activation_of_another_role_contains_nothing():
    state = ExecuteState()
    record_activation(state, activation_id="a", role="architect", run_id="run-1", opened_at="t",
                      closed_at="t", records=["ruling-0009"])
    script = Script(_snap(), {"queue.run_step": SUCCESS})
    await _run(script, state)
    assert "queue.run_step" not in script.names() and contained_record_ids(state) == set()


async def test_an_activation_whose_records_were_unreadable_contains_nothing():
    state = ExecuteState()
    record_activation(state, activation_id="a", role="overseer", run_id="run-1", opened_at="t",
                      closed_at="t", records=None)
    script = Script(_snap(), {"queue.run_step": SUCCESS})
    await _run(script, state)
    assert "queue.run_step" not in script.names()


async def test_a_server_that_names_no_ruling_fails_closed():
    snap = {"open_projects": [{"project_id": "project-0001", "role": "overseer", "steps_open": 1,
                               "phases_remaining": 0}], "ready_steps": [_ready(1)]}
    script = Script(snap, {"queue.run_step": SUCCESS})
    report = await _run(script, contained_state())
    assert "queue.run_step" not in script.names() and "did not say" in report.errors[0]


async def test_an_uncontained_step_does_not_block_a_contained_one():
    snap = {"open_projects": [_proj(ruling_id="ruling-0009"),
                              {**_proj(ruling_id="ruling-0001"), "project_id": "project-0002"}],
            "ready_steps": [_ready(1), {**_ready(1), "project_id": "project-0002", "step_id": "project-0002/s1"}]}
    script = Script(snap, {"queue.run_step": SUCCESS})
    await _run(script, contained_state())
    ran = [a["step_id"] for t, a in script.calls if t == "queue.run_step"]
    assert ran == ["project-0002/s1"]


async def test_the_store_round_trips_activations(tmp_path):
    store = ExecuteStore(tmp_path / "s.json")
    store.save(contained_state("ruling-0004"))
    assert contained_record_ids(store.load()) == {"ruling-0004"}


# ---- the cycle: a one-shot Overseer run is one activation -------------------------------


class _Report:
    """A `conductor.report` stand-in: start gives a run id, end names the records the run wrote."""

    def __init__(self, ids):
        self.ids = ids

    def __call__(self, args):
        if args.get("phase") == "start":
            return {"run_id": "run-0042", "started_at": "t"}
        return {"run_id": "run-0042", "ended_at": "t", "records": len(self.ids), "record_ids": self.ids}


def _overseer_tools(ids):
    tools = _tools()
    tools["queue.overview"] = {"proposals": {"count": 1, "proposal_ids": ["proposal-0001"]},
                               "asks": {"count": 0, "ask_ids": []}}
    tools["conductor.report"] = _Report(ids)
    return tools


async def test_a_one_shot_overseer_run_opens_an_activation_that_contains_its_ruling(tmp_path):
    deps = _deps(tmp_path, tools=_overseer_tools(["ruling-0001"]), runner=FakeRoleRunner())
    result = await run_cycle(1, deps)
    assert "queue.run_step" in _names(deps) and result.execute["steps_run"] == 1
    saved = ExecuteStore(tmp_path / "execute_state.json").load()
    act = saved.activations["act-run-0042"]
    assert act["role"] == "overseer" and act["run_id"] == "run-0042" and act["records"] == ["ruling-0001"]
    assert act["opened_at"] and act["closed_at"]


async def test_a_one_shot_run_reports_its_transport_and_activation_id(tmp_path):
    deps = _deps(tmp_path, tools=_overseer_tools(["ruling-0001"]), runner=FakeRoleRunner())
    await run_cycle(1, deps)
    ends = [a for t, a in deps.tool_caller.calls if t == "conductor.report" and a.get("phase") == "end"]
    assert ends and all(e["transport"] == "one_shot" and e["activation_id"] == "act-run-0042" for e in ends)


async def test_a_ruling_the_overseer_run_did_not_write_is_alerted_not_run(tmp_path):
    deps = _deps(tmp_path, tools=_overseer_tools(["ruling-0007"]), runner=FakeRoleRunner())
    result = await run_cycle(1, deps)
    assert "queue.run_step" not in _names(deps)
    assert result.execute["steps_run"] == 0
    assert any("ruling-0001" in e and "containment" in e for e in result.execute["errors"])


async def test_a_ruling_with_no_overseer_run_at_all_is_not_run(tmp_path):
    deps = _deps(tmp_path, tools=_tools())
    result = await run_cycle(1, deps)
    assert "queue.run_step" not in _names(deps) and result.execute["errors"]


# ---- the one-time grandfather ------------------------------------------------------------


async def test_rulings_present_at_first_run_are_grandfathered_later_ones_are_not():
    snap = {**_snap("ruling-0003"), "ruling_ids": ["ruling-0001", "ruling-0003"]}
    state = ExecuteState()
    script = Script(snap, {"queue.run_step": SUCCESS})
    report = await _run(script, state)
    assert script.names().count("queue.run_step") == 1 and report.errors == []
    assert state.grandfathered and state.activations["legacy"]["records"] == ["ruling-0001", "ruling-0003"]
    # a ruling made after cutover is in no activation: not run, alerted
    later = Script({**_snap("ruling-0005"), "ruling_ids": ["ruling-0001", "ruling-0003", "ruling-0005"]},
                   {"queue.run_step": SUCCESS})
    again = await _run(later, state)
    assert "queue.run_step" not in later.names() and "ruling-0005" in again.errors[0]
    assert state.activations["legacy"]["records"] == ["ruling-0001", "ruling-0003"]


async def test_no_ruling_ids_from_the_server_grandfathers_nothing_and_legacy_survives_pruning(tmp_path):
    state = ExecuteState()
    await _run(Script(_snap(), {"queue.run_step": SUCCESS}), state)
    assert not state.grandfathered and "legacy" not in state.activations
    await _run(Script({**_snap(), "ruling_ids": ["ruling-0009"]}, {"queue.run_step": SUCCESS}), state)
    for i in range(250):
        record_activation(state, activation_id=f"a{i}", role="overseer", run_id=None, opened_at="t",
                          closed_at="t", records=[])
    assert "legacy" in state.activations
    store = ExecuteStore(tmp_path / "s.json")
    store.save(state)
    assert store.load().grandfathered
