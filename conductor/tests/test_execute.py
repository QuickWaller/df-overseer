"""conductor/execute.py: the execute phase over a scripted tool caller."""

import re
from dataclasses import replace

import pytest

from conductor.execute import ExecuteState, ExecuteStore, run_execute
from conductor.mcp_client import MCPToolError
from conductor.ore_watch import OreExposure, OreRead
from conductor.policy import ExecutionPolicy

pytestmark = pytest.mark.asyncio

POLICY = ExecutionPolicy(ore_hold_phase=re.compile(r"(_finish|_zone|_build)$"))


class Script:
    """A tool caller: `state` is what queue.execution_state returns (a dict, or a
    list consumed one per read); every other tool answers from `answers`."""

    def __init__(self, state=None, answers=None):
        self.states = state if isinstance(state, list) else [state or {}]
        self.answers = dict(answers or {})
        self.calls = []

    async def __call__(self, tool, args):
        self.calls.append((tool, dict(args)))
        if tool == "queue.execution_state":
            return self.states.pop(0) if len(self.states) > 1 else self.states[0]
        ans = self.answers.get(tool)
        if ans is None:
            raise MCPToolError(f"{tool}: no answer scripted")
        return ans(args) if callable(ans) else ans

    def names(self):
        return [t for t, _ in self.calls]


def _ready(n, urgency="normal", **extra):
    return {"project_id": "project-0001", "step_id": f"project-0001/s{n}", "urgency": urgency, **extra}


def _proj(role="architect", **kw):
    return {"project_id": "project-0001", "role": role, "steps_open": 1, "phases_remaining": 2, **kw}


async def _run(script, state=None, **kw):
    state = state or ExecuteState()
    kw.setdefault("game_tick", 10000)
    kw.setdefault("policy", POLICY)
    policy = kw.pop("policy")
    report = await run_execute(script, policy, state, **kw)
    return report, state


SUCCESS = {"class": "success", "handle": "site-1"}


async def test_ready_steps_run_by_urgency_then_age_up_to_the_cap_after_one_quicksave():
    ready = [_ready(1), _ready(2, "high"), _ready(3), _ready(4), _ready(5), _ready(6, "high")]
    script = Script({"open_projects": [_proj()], "ready_steps": ready}, {"queue.run_step": SUCCESS})
    saves = []

    async def quicksave():
        saves.append(1)

    report, _ = await _run(script, quicksave=quicksave)
    ran = [a["step_id"] for t, a in script.calls if t == "queue.run_step"]
    assert ran == ["project-0001/s2", "project-0001/s6", "project-0001/s1", "project-0001/s3"]
    assert report.steps_run == 4 and len(saves) == 1
    assert any(a["kind"] == "cap" for a in report.actions)


async def test_no_quicksave_when_nothing_runs():
    saves = []

    async def quicksave():
        saves.append(1)

    await _run(Script({"ready_steps": []}), quicksave=quicksave)
    assert not saves


async def test_an_uncertain_run_is_resolved_before_any_step_runs_and_its_project_waits_if_unsettled():
    held_state = {
        "open_projects": [_proj()], "ready_steps": [_ready(2)],
        "unresolved_runs": [{"run_id": 7, "project_id": "project-0001", "step_id": "project-0001/s1"}],
    }
    script = Script(held_state, {"queue.resolve_uncertain": {"class": "uncertain"}, "queue.run_step": SUCCESS})
    report, state = await _run(script)
    assert script.names().index("queue.resolve_uncertain") < len(script.names())
    assert "queue.run_step" not in script.names()  # the project still has an unresolved run
    assert state.uncertain == {"7": 1}


async def test_a_resolved_run_lets_the_project_run_in_the_same_pass():
    first = {"open_projects": [_proj()], "ready_steps": [],
             "unresolved_runs": [{"run_id": 7, "project_id": "project-0001", "step_id": "project-0001/s1"}]}
    second = {"open_projects": [_proj()], "ready_steps": [_ready(1)], "unresolved_runs": []}
    script = Script([first, second], {"queue.resolve_uncertain": {"class": "transient"}, "queue.run_step": SUCCESS})
    await _run(script)
    names = script.names()
    assert names.index("queue.resolve_uncertain") < names.index("queue.run_step")


async def test_a_run_unreadable_three_times_is_held_and_the_proposer_told_once():
    s = {"open_projects": [_proj()], "unresolved_runs": [
        {"run_id": 7, "project_id": "project-0001", "step_id": "project-0001/s1"}]}
    state = ExecuteState(uncertain={"7": 2})
    script = Script(s, {"queue.resolve_uncertain": {"class": "uncertain"}})
    report, state = await _run(script, state)
    held_calls = [a for t, a in script.calls if t == "queue.resolve_uncertain" and a.get("hold")]
    assert held_calls == [{"run_id": 7, "hold": True}]
    assert [w.reason for w in report.wakes] == ["step_attention"]
    assert report.wakes[0].role == "architect"


async def test_a_run_that_was_never_confirmed_is_never_rerun_blind():
    # run_step answers uncertain: the pass records it and does not call run_step again.
    script = Script({"open_projects": [_proj()], "ready_steps": [_ready(1)]},
                    {"queue.run_step": {"class": "uncertain", "run_id": 9, "detail": "may have run"}})
    report, _ = await _run(script)
    assert script.names().count("queue.run_step") == 1
    assert any(a["kind"] == "uncertain" for a in report.actions)


async def test_step_done_wakes_the_proposer_once_per_step_across_both_routes():
    s = {"open_projects": [_proj(phases_remaining=1)],
         "done_since": [{"observation_id": "observation-0003", "project_id": "project-0001", "step_id": "project-0001/s1"}],
         "issued_steps": [{"project_id": "project-0001", "step_id": "project-0001/s1"}],
         "latest_observation_id": "observation-0003"}
    script = Script(s, {"queue.observe": {"state": "done", "observation_id": "observation-0004", "detail": "d"}})
    report, state = await _run(script)
    done = [w for w in report.wakes if w.reason == "step_done"]
    assert len(done) == 1 and done[0].role == "architect"
    assert "follow-up naming project project-0001 and step project-0001/s1" in done[0].text
    assert "1 declared phase(s) left" in done[0].text
    assert state.since == "observation-0003"
    report2, _ = await _run(Script(s, {"queue.observe": {"state": "done"}}), state)
    assert not [w for w in report2.wakes if w.reason == "step_done"]


async def test_stalled_and_blocked_go_to_the_proposer_once_per_cause():
    s = {"open_projects": [_proj()], "issued_steps": [{"project_id": "project-0001", "step_id": "project-0001/s1"}]}
    answers = {"queue.observe": {"state": "stalled", "detail": "dig stalled"}}
    report, state = await _run(Script(s, answers))
    assert [w.reason for w in report.wakes] == ["step_attention"]
    report2, _ = await _run(Script(s, answers), state)
    assert report2.wakes == []
    report3, _ = await _run(Script(s, {"queue.observe": {"state": "blocked_material", "detail": "no stone"}}), state)
    assert [w.reason for w in report3.wakes] == ["step_attention"]


async def test_unknown_reads_wake_only_on_the_third():
    s = {"open_projects": [_proj()], "issued_steps": [{"project_id": "project-0001", "step_id": "project-0001/s1"}]}
    answers = {"queue.observe": {"state": "unknown", "detail": "no read"}}
    state = ExecuteState()
    woke = []
    for _ in range(3):
        report, state = await _run(Script(s, answers), state)
        woke.append(len(report.wakes))
    assert woke == [0, 0, 1]


async def test_transient_third_time_needs_judgment_and_needs_judgment_wakes_once():
    s = {"open_projects": [_proj()], "ready_steps": [_ready(1)]}
    state = ExecuteState()
    counts = []
    for _ in range(3):
        report, state = await _run(Script(s, {"queue.run_step": {"class": "transient", "detail": "busy"}}), state)
        counts.append(len(report.wakes))
    assert counts == [0, 0, 1]
    nj = {"queue.run_step": {"class": "needs_judgment", "detail": "resolution changed"}}
    r1, st = await _run(Script(s, nj))
    r2, _ = await _run(Script(s, nj), st)
    assert len(r1.wakes) == 1 and r2.wakes == []


async def test_a_second_failure_goes_to_the_proposer_a_retryable_one_does_not():
    s = {"open_projects": [_proj()], "ready_steps": [_ready(1)]}
    r1, _ = await _run(Script(s, {"queue.run_step": {"class": "failed", "retryable": True, "detail": "x"}}))
    r2, _ = await _run(Script(s, {"queue.run_step": {"class": "failed", "retryable": False, "detail": "x"}}))
    assert r1.wakes == [] and len(r2.wakes) == 1


async def test_open_and_apply_then_a_second_state_read():
    s1 = {"to_open": [{"ruling_id": "ruling-0040"}], "to_apply": [{"proposal_id": "proposal-0050"}]}
    s2 = {"open_projects": [_proj()], "ready_steps": [_ready(1)]}
    script = Script([s1, s2], {
        "queue.open_project": {"project_id": "project-0001", "step_ids": ["project-0001/s1"]},
        "queue.apply_followup": {"project_id": "project-0001", "step_id": "project-0001/s2"},
        "queue.run_step": SUCCESS,
    })
    report, _ = await _run(script)
    names = script.names()
    assert names.index("queue.open_project") < names.index("queue.run_step")
    assert names.count("queue.execution_state") == 2
    assert [a["kind"] for a in report.actions if a["kind"] in ("opened", "applied")] == ["opened", "applied"]


async def test_a_refused_open_is_tried_a_bounded_number_of_times():
    s = {"to_open": [{"ruling_id": "ruling-0040"}]}
    state = ExecuteState()
    for _ in range(5):
        await _run(Script(s, {}), state)  # queue.open_project has no answer: a refusal
    assert state.refused["ruling-0040"] == POLICY.refusal_limit


async def test_cleanup_runs_for_each_abandoned_project():
    s = {"awaiting_cleanup": [{"project_id": "project-0002", "handles": ["site-3"]}]}
    script = Script(s, {"queue.cleanup_project": {"released": ["site-3"], "unreserved": [], "failed": [], "close_id": "close-0009"}})
    report, state = await _run(script)
    assert script.names().count("queue.cleanup_project") == 1
    assert any(a["kind"] == "cleanup" and a["close_id"] == "close-0009" for a in report.actions)
    s2 = Script(s, {"queue.cleanup_project": {"released": [], "unreserved": [], "failed": [{"handle": "site-3"}]}})
    _r, state = await _run(s2, state)
    assert state.cleanup_failed == {"project-0002": 1}


async def test_idle_project_wakes_once_then_closes_completed_idle():
    s = {"open_projects": [_proj(steps_open=0, phases_remaining=1)]}
    state = ExecuteState()
    r0, state = await _run(Script(s), state, game_tick=1000)
    assert r0.wakes == []
    r1, state = await _run(Script(s), state, game_tick=1000 + POLICY.idle_wake_ticks)
    assert [w.reason for w in r1.wakes] == ["project_idle"]
    r1b, state = await _run(Script(s), state, game_tick=1000 + POLICY.idle_wake_ticks + 10)
    assert r1b.wakes == []
    closer = Script(s, {"queue.close": {"close_id": "close-0001"}})
    r2, state = await _run(closer, state, game_tick=1000 + POLICY.idle_wake_ticks + POLICY.idle_close_ticks)
    close = [a for t, a in closer.calls if t == "queue.close"]
    assert close and close[0]["outcome"] == "completed" and "idle" in close[0]["reason"]
    assert "project-0001" not in state.idle


async def test_a_project_that_gets_a_follow_up_leaves_idle_tracking():
    state = ExecuteState(idle={"project-0001": {"since": 1000, "woke": None}})
    s = {"open_projects": [_proj(steps_open=1)]}
    _r, state = await _run(Script(s), state, game_tick=2000)
    assert state.idle == {}


def _ore(site="site-5", unclassified=0, unreadable=()):
    exp = OreExposure(site, "HEMATITE", "ore", 2, "HEMATITE ore: 2 tiles") if site else None
    return OreRead((exp,) if exp else (), frozenset(unreadable), {site: unclassified} if unclassified else {})


def _finish(site="site-5", phase="bedroom_cell_v1_finish"):
    return _ready(2, tool="blueprint.apply", args={"site": site, "phase": phase})


async def test_a_finish_phase_waits_on_ore_wakes_once_and_releases_at_zero():
    s = {"open_projects": [_proj()], "ready_steps": [_finish()]}
    script = Script(s, {"queue.run_step": SUCCESS})
    r1, state = await _run(script, ore_read=_ore())
    assert "queue.run_step" not in script.names()
    assert len(r1.wakes) == 1 and "waiting on ore: HEMATITE" in r1.wakes[0].text
    assert "construction.mine-vein-site site-5" in r1.wakes[0].text
    script2 = Script(s, {"queue.run_step": SUCCESS})
    r2, state = await _run(script2, state, ore_read=_ore())
    assert r2.wakes == [] and "queue.run_step" not in script2.names()
    script3 = Script(s, {"queue.run_step": SUCCESS})
    r3, state = await _run(script3, state, ore_read=OreRead())
    assert "queue.run_step" in script3.names()
    assert any(a["kind"] == "ore_released" for a in r3.actions) and state.ore_held == {}


async def test_unclassified_tiles_hold_a_finish_phase_too():
    s = {"open_projects": [_proj()], "ready_steps": [_finish()]}
    script = Script(s, {"queue.run_step": SUCCESS})
    await _run(script, ore_read=OreRead((), frozenset(), {"site-5": 3}))
    assert "queue.run_step" not in script.names()


async def test_a_shell_phase_is_not_held_by_ore():
    s = {"open_projects": [_proj()], "ready_steps": [_finish(phase="bedroom_cell_v1_shell")]}
    script = Script(s, {"queue.run_step": SUCCESS})
    await _run(script, ore_read=_ore())
    assert "queue.run_step" in script.names()


async def test_an_unavailable_ore_read_holds_a_finish_phase_without_a_wake():
    s = {"open_projects": [_proj()], "ready_steps": [_finish()]}
    script = Script(s, {"queue.run_step": SUCCESS})
    report, _ = await _run(script, ore_read=None)
    assert "queue.run_step" not in script.names() and report.wakes == []


async def test_latched_runs_only_high_urgency_and_skips_cleanup_and_observe():
    s = {"open_projects": [_proj()], "ready_steps": [_ready(1), _ready(2, "high")],
         "awaiting_cleanup": [{"project_id": "project-0002"}],
         "issued_steps": [{"project_id": "project-0001", "step_id": "project-0001/s9"}]}
    script = Script(s, {"queue.run_step": SUCCESS})
    await _run(script, latched=True)
    assert [a["step_id"] for t, a in script.calls if t == "queue.run_step"] == ["project-0001/s2"]
    assert "queue.cleanup_project" not in script.names() and "queue.observe" not in script.names()


async def test_an_unreadable_execution_state_runs_nothing_and_says_so():
    script = Script(None, {})
    script.states = [None]

    async def boom(tool, args):
        raise MCPToolError("queue.execution_state: down")

    report = await run_execute(boom, POLICY, ExecuteState(), game_tick=1)
    assert not report.ran and "could not be read" in report.skipped


async def test_the_phase_never_touches_the_clock():
    s = {"open_projects": [_proj()], "ready_steps": [_ready(1)]}
    script = Script(s, {"queue.run_step": SUCCESS})
    await _run(script)
    assert not [t for t in script.names() if t.startswith("clock.") or t.startswith("pause.")]


async def test_wakes_fall_back_to_the_lane_roles_when_the_proposer_is_unknown():
    s = {"open_projects": [{"project_id": "project-0001", "steps_open": 1, "phases_remaining": 0}],
         "done_since": [{"observation_id": "observation-0001", "project_id": "project-0001", "step_id": "project-0001/s1"}]}
    report, _ = await _run(Script(s), fallback_roles=("architect",))
    assert [w.role for w in report.wakes] == ["architect"]


def test_state_store_round_trips(tmp_path):
    store = ExecuteStore(tmp_path / "execute_state.json")
    assert store.load() == ExecuteState()
    st = ExecuteState(since="observation-0002", sent=["a/s1"], idle={"p": {"since": 1, "woke": None}})
    store.save(st)
    assert store.load() == st
