"""Stage 2A: the executor's queue model (handoffs/2026-10-05-stage-2a.md,
docs/CONDUCTOR-EXECUTION.md section 6.1).

Nothing here touches DFHack. Routing is data (`dfqueue/action_tools.yaml`);
each test that needs a routed group points `routing.ACTION_TOOLS_PATH` at a
temp copy with the flags it needs.
"""

from __future__ import annotations

import socket

import pytest
import yaml

from dfqueue import routing, schema, store
from dfqueue.tests._helpers import (
    make_abandon, make_amend, make_executed, make_project, make_proposal,
    make_ruling,
)

REAL_YAML = routing.ACTION_TOOLS_PATH


# ---- fixtures and builders --------------------------------------------------------


def set_routing(monkeypatch, tmp_path, **rooms_flags):
    """Point routing at a temp copy of the real file with `rooms` flags set."""
    data = yaml.safe_load(REAL_YAML.read_text(encoding="utf-8"))
    data["groups"]["rooms"].update(rooms_flags)
    p = tmp_path / "action_tools.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    monkeypatch.setattr(routing, "ACTION_TOOLS_PATH", p)
    return p


def db(tmp_path):
    return tmp_path / "q.sqlite3"


STEP = {
    "tool": "blueprint.reserve",
    "args": {"template": "bedroom-cell-v1", "purpose": "bedroom row 1"},
    "label": "Reserve bedroom",
}
PHASES = {"tool": "blueprint.apply", "list": ["bedroom_cell_v1_shell", "bedroom_cell_v1_finish"]}


def room(n: int = 1, **kw):
    """A routed-room proposal (distinct text per n so no duplicate flag)."""
    rec = make_proposal(
        type="room_siting", step=dict(STEP), phases=dict(PHASES),
        summary=f"Reserve bedroom number {n} off the dining hall {'x' * n}",
        rationale=f"Dwarves sleep on the floor, bedroom number {n} fixes that {'y' * n}.",
    )
    rec.update(kw)
    return rec


def file(path, rec, tick=100):
    return store.append(rec, path, game_tick=tick)


def rule(path, proposal_id, decision="accept"):
    return store.append(make_ruling(proposal_id, decision=decision), path)


def legacy_ruling(path):
    """An old-style ruling (the proposal is step-less, filed while rooms are
    unrouted), written first so a cutover has something to point at."""
    legacy = make_proposal(type="room_siting", summary="Legacy room idea " + "z" * 3)
    p = file(path, legacy, tick=1)
    return p, rule(path, p["id"])


@pytest.fixture
def routed(tmp_path, monkeypatch):
    """A queue with `rooms` routed, cutover at ruling-0001 (a legacy one)."""
    path = db(tmp_path)
    legacy_ruling(path)  # proposal-0001 / ruling-0001, while unrouted
    set_routing(monkeypatch, tmp_path, routed=True)
    store.set_cutover(path, "rooms", "ruling-0001")
    return path


def open_room(path, n=1):
    p = file(path, room(n))
    r = rule(path, p["id"])
    proj = store.open_project_from_ruling(path, r["id"])
    return p, r, proj


def run_step_ok(path, project_id, step_id, handle="res-1", tick=200, tool=None):
    tool = tool or ("blueprint.reserve" if step_id.endswith("/s1") else "blueprint.apply")
    run = store.begin_step_run(path, project_id, step_id, tick=tick, baseline=[])
    return store.finish_step_run(
        path, run,
        {"actions": [{"tool": tool, "outcome": "success",
                      "targets": [step_id], "target_state": "issued",
                      "game_refs": [handle]}]},
    )


def legacy_executed(rid, proj, **kw):
    """An Overseer-style executed for a legacy project's first step."""
    step = proj["steps"][0]
    return make_executed(
        rid, step_id=step["id"],
        actions=[{"tool": step["tool"], "outcome": "success"}], **kw)


def state_of(path, project_id, step_id):
    return [t["state"] for t in store.target_states(path, project_id) if t["step_id"] == step_id]


# ---- routing data -----------------------------------------------------------------


def test_nothing_is_routed_by_default():
    assert routing.routed_groups() == []
    assert routing.routed_types() == [] and routing.routed_tools() == []
    assert not routing.is_routed("room_siting")


def test_group_lookups_and_unrouted_types():
    assert routing.group_of("room_siting") == "rooms"
    assert routing.group_of("work_order") == "orders"
    assert routing.group_of("stock_target") is None
    assert "blueprint.reserve" in routing.tools("rooms")
    assert routing.group_of_tool("zone.place") == "rooms"
    assert set(routing.unrouted_types()) >= {"room_siting", "work_order", "stockpile_siting"}


def test_routed_flag_moves_types_out_of_unrouted(tmp_path, monkeypatch):
    set_routing(monkeypatch, tmp_path, routed=True)
    assert routing.is_routed("corridor") and not routing.is_routed("work_order")
    assert "corridor" not in routing.unrouted_types()
    assert routing.routed_tools() == routing.tools("rooms")


def test_malformed_routing_file_is_refused(tmp_path, monkeypatch):
    p = tmp_path / "bad.yaml"
    p.write_text("groups: {a: {types: [x], tools: [t]}, b: {types: [x], tools: [u]}}\n")
    monkeypatch.setattr(routing, "ACTION_TOOLS_PATH", p)
    with pytest.raises(routing.RoutingError, match="type 'x'"):
        routing.groups()


def test_every_group_type_is_a_real_proposal_type():
    vocab = {t for ts in schema.TYPE_VOCAB_BY_ROLE.values() for t in ts}
    for g in routing.groups():
        for t in routing.types(g):
            assert t in vocab, (g, t)


def _tool_universe():
    from dfmcp import (
        conductor_tools, doctrine_tools, gotchas_tools, knowledge_tools,
        queue_tools, series_tools,
    )
    from dfmcp.registry import load_registry
    from dfmcp.roles import load_roster
    registry = load_registry(native_tools={
        **queue_tools.NATIVE_TOOLS, **doctrine_tools.NATIVE_TOOLS, **series_tools.NATIVE_TOOLS,
        **gotchas_tools.NATIVE_TOOLS, **knowledge_tools.NATIVE_TOOLS, **conductor_tools.NATIVE_TOOLS,
    })
    return registry, load_roster(registry)


def test_every_mutating_tool_is_routed_on_the_overseer_the_conductor_or_retired():
    registry, roster = _tool_universe()
    grouped = {t for g in routing.groups() for t in routing.tools(g)}
    held = set()
    for role in ("overseer", "conductor"):
        held |= set(roster.roles[role].read) | set(roster.roles[role].write)
    mutating = [i for i in registry.ids() if registry.get(i).mutates]
    stray = [m for m in mutating if m not in grouped and m not in held and m not in routing.retired()]
    assert stray == []
    for t in grouped | set(routing.retired()):
        assert t in registry.ids(), t


def test_a_routed_tool_must_have_left_the_overseer_allowlist(tmp_path, monkeypatch):
    """Stage 2E removed the rooms tools from the Overseer. With `rooms` routed
    none may remain; the same check must still be able to fail, so it is also
    run against a tool that is on the Overseer's allowlist."""
    registry, roster = _tool_universe()
    overseer = set(roster.roles["overseer"].read) | set(roster.roles["overseer"].write)
    set_routing(monkeypatch, tmp_path, routed=True)
    assert "blueprint.reserve" in routing.routed_tools()
    assert not [t for t in routing.routed_tools() if t in overseer]
    assert "construction.build" in overseer  # an unrouted tool the Overseer keeps
    assert "construction.build" not in routing.routed_tools()


# ---- schema -----------------------------------------------------------------------


def test_close_kind_and_its_role_and_shape():
    ok = {"kind": "close", "role": "conductor", "cycle": 1, "snapshot": "s",
          "ruling_id": "ruling-0001", "outcome": "not_done", "reason": "legacy sweep"}
    assert schema.validate(ok) == []
    assert any("executor" in e for e in schema.validate({**ok, "role": "overseer"}))
    assert any("exactly one" in e for e in schema.validate({**ok, "project_id": "project-0001"}))
    assert any("outcome" in e for e in schema.validate({**ok, "outcome": "done"}))
    assert any("exactly one" in e for e in schema.validate({k: v for k, v in ok.items() if k != "ruling_id"}))
    bad_cleanup = {**ok, "cleanup": [{"handle": "res-1"}]}
    assert any("cleanup.0.outcome" in e for e in schema.validate(bad_cleanup))


def test_roster_executor_may_write_project_executed_amend_but_not_ruling():
    assert schema.executor() == "conductor"
    proj = make_project(role="conductor")
    assert schema.validate(proj) == []
    assert any("sole_writer" in e for e in schema.validate(make_ruling(role="conductor")))
    assert any("executor" in e for e in schema.validate(make_project(role="architect")))
    assert schema.validate(make_executed(role="conductor", step_id="project-0001/s1",
                                         proposal_id="proposal-0001")) == []


def test_proposal_step_fields_validate():
    base = room()
    assert schema.validate({**base, "role": "architect", "cycle": 1, "snapshot": "s"}) == []
    assert any("not a real tool" in e for e in schema.validate(room(step={"tool": "nope.x", "args": {}})))
    assert any("args" in e for e in schema.validate(room(step={"tool": "blueprint.reserve"})))
    assert any("coordinate" in e for e in schema.validate(
        room(step={"tool": "blueprint.reserve", "args": {"at": "x=12"}})))
    assert any("phases" in e for e in schema.validate(room(phases={"tool": "blueprint.apply", "list": []})))
    assert any("once" in e for e in schema.validate(
        room(phases={"tool": "blueprint.apply", "list": ["a", "a"]})))
    assert any("both or neither" in e for e in schema.validate(room(project_id="project-0001")))
    assert any("follow-up needs a step" in e for e in schema.validate(
        {k: v for k, v in room(project_id="project-0001", after_step="project-0001/s1").items()
         if k not in ("step", "phases")}))
    assert any("only a first proposal" in e for e in schema.validate(
        room(project_id="project-0001", after_step="project-0001/s1")))
    assert any("only a follow-up" in e for e in schema.validate(room(covered_by="project-0001/s1")))


def test_step_label_and_proposal_id_in_a_project_step():
    step = {"id": "project-0001/s1", "tool": "blueprint.reserve", "args": {},
            "targets": {"set": ["project-0001/s1"]}, "proposal_id": "proposal-0001"}
    assert schema.validate(make_project(role="conductor", steps=[step])) == []
    step["proposal_id"] = ""
    assert any("proposal_id" in e for e in schema.validate(make_project(role="conductor", steps=[step])))


# ---- filing rules in the store -----------------------------------------------------


def test_step_refused_for_an_unrouted_type(tmp_path):
    path = db(tmp_path)
    with pytest.raises(store.QueueError, match="not routed yet"):
        file(path, room())


def test_step_refused_for_a_type_in_no_group(tmp_path):
    path = db(tmp_path)
    rec = make_proposal(role="quartermaster", type="stock_target", step=dict(STEP))
    with pytest.raises(store.QueueError, match="no routing group"):
        file(path, rec)


def test_routed_type_needs_a_step(routed):
    with pytest.raises(store.QueueError, match="needs an exact step"):
        file(routed, make_proposal(type="room_siting"))


def test_step_tool_must_belong_to_the_group(routed):
    bad = room(step={"tool": "orders.create", "args": {}})
    with pytest.raises(store.QueueError, match="not a tool of group"):
        file(routed, bad)


def test_frozen_group_refuses_stepless_with_the_freeze_message(tmp_path, monkeypatch):
    path = db(tmp_path)
    set_routing(monkeypatch, tmp_path, frozen=True)
    with pytest.raises(store.QueueError, match="next deploy; file after it"):
        file(path, make_proposal(type="room_siting"))
    # an unrelated type is untouched by the freeze
    file(path, make_proposal(role="quartermaster", type="work_order",
                             summary="Brew drinks " + "q" * 5))


def test_a_stepless_proposal_still_works_for_an_unrouted_type(tmp_path):
    path = db(tmp_path)
    p = file(path, make_proposal(type="room_siting"))
    assert "step" not in p and store.pending_proposals(path)[0]["id"] == p["id"]


def test_followup_filing_rules(routed):
    p, r, proj = open_room(routed)
    s1 = proj["steps"][0]["id"]
    ok = room(2, step={"tool": "blueprint.apply", "args": {"phase": "bedroom_cell_v1_shell", "site": "res-1"}},
              project_id=proj["id"], after_step=s1)
    ok.pop("phases")
    assert file(routed, ok)["project_id"] == proj["id"]

    def refused(match, **kw):
        rec = room(3, step={"tool": "blueprint.apply", "args": {}})
        rec.pop("phases")
        rec.update(project_id=proj["id"], after_step=s1)
        rec.update(kw)
        with pytest.raises(store.QueueError, match=match):
            file(routed, rec)

    refused("does not refer to an existing project", project_id="project-0099")
    refused("is not a step of", after_step="project-0001/s9")
    refused("not a project this role proposed", role="quartermaster", type="work_order")
    store.append(make_abandon(project_id=proj["id"]), routed)
    refused("closed or abandoned")


def test_followup_must_stay_in_its_projects_group(routed):
    p, r, proj = open_room(routed)
    rec = make_proposal(type="stockpile_siting", step={"tool": "stockpile.place", "args": {}},
                        project_id=proj["id"], after_step=proj["steps"][0]["id"],
                        summary="Stockpile follow " + "k" * 4)
    with pytest.raises(store.QueueError, match="not routed yet|stay in its project's group"):
        file(routed, rec)


def test_covered_by_needs_coverage_on(tmp_path, monkeypatch):
    path = db(tmp_path)
    legacy_ruling(path)
    set_routing(monkeypatch, tmp_path, routed=True)
    store.set_cutover(path, "rooms", "ruling-0001")
    p, r, proj = open_room(path)
    s1 = proj["steps"][0]["id"]

    def follow():
        rec = room(7, step={"tool": "blueprint.apply", "args": {"phase": "x"}},
                   project_id=proj["id"], after_step=s1, covered_by=s1)
        rec.pop("phases")
        return rec

    with pytest.raises(store.QueueError, match="coverage is not on"):
        file(path, follow())
    set_routing(monkeypatch, tmp_path, routed=True, coverage=True)
    covered = file(path, follow())
    assert covered["covered_by"] == s1
    assert covered["id"] not in [x["id"] for x in store.pending_proposals(path)]
    with pytest.raises(store.QueueError, match="covered or closed"):
        rule(path, covered["id"])


# ---- cutovers ---------------------------------------------------------------------


def test_cutover_is_raise_only_and_validated(tmp_path):
    path = db(tmp_path)
    for n in (1, 2):
        p = file(path, make_proposal(type="room_siting", summary=f"legacy {n} " + "w" * n))
        rule(path, p["id"])
    assert store.cutover(path, "rooms") is None
    store.set_cutover(path, "rooms", "ruling-0002")
    assert store.cutover(path, "rooms") == "ruling-0002"
    with pytest.raises(store.QueueError, match="only moves up"):
        store.set_cutover(path, "rooms", "ruling-0001")
    with pytest.raises(store.QueueError, match="not an existing ruling"):
        store.set_cutover(path, "rooms", "ruling-0099")
    with pytest.raises(store.QueueError, match="no such routing group"):
        store.set_cutover(path, "nope", "ruling-0001")
    store.set_cutover(path, "legacy", "ruling-0001")
    assert store.cutover(path, "legacy") == "ruling-0001"


def test_open_project_refuses_without_a_cutover(tmp_path, monkeypatch):
    path = db(tmp_path)
    set_routing(monkeypatch, tmp_path, routed=True)
    p = file(path, room())
    r = rule(path, p["id"])
    with pytest.raises(store.QueueError, match="no cutover is set"):
        store.open_project_from_ruling(path, r["id"])


# ---- open_project_from_ruling -----------------------------------------------------


def test_open_project_builds_one_step_with_its_proposal(routed):
    p, r, proj = open_room(routed)
    assert proj["role"] == "conductor" and proj["from_ruling"] == r["id"]
    (step,) = proj["steps"]
    assert step["id"] == f"{proj['id']}/s1" and step["targets"] == {"set": [step["id"]]}
    assert step["proposal_id"] == p["id"] and step["tool"] == "blueprint.reserve"
    assert step["args"] == STEP["args"] and step["label"] == "Reserve bedroom"
    assert state_of(routed, proj["id"], step["id"]) == ["ready"]
    assert proj["template"] == "bedroom-cell-v1"


def test_open_project_refusals(routed, tmp_path, monkeypatch):
    p, r, proj = open_room(routed)
    with pytest.raises(store.QueueError, match="already has a project"):
        store.open_project_from_ruling(routed, r["id"])
    # a ruling at or below the cutover
    with pytest.raises(store.QueueError, match="at or below the cutover"):
        store.open_project_from_ruling(routed, "ruling-0001")
    # a reject
    p2 = file(routed, room(2))
    rej = rule(routed, p2["id"], "reject")
    with pytest.raises(store.QueueError, match="not an accepting"):
        store.open_project_from_ruling(routed, rej["id"])
    # a follow-up never opens a project
    fol = room(3, step={"tool": "blueprint.apply", "args": {}}, project_id=proj["id"],
               after_step=proj["steps"][0]["id"])
    fol.pop("phases")
    fp = file(routed, fol)
    fr = rule(routed, fp["id"])
    with pytest.raises(store.QueueError, match="joins that project"):
        store.open_project_from_ruling(routed, fr["id"])
    # an unrouted type
    qp = file(routed, make_proposal(role="quartermaster", type="work_order",
                                    summary="Brew drinks " + "b" * 4))
    qr = rule(routed, qp["id"])
    with pytest.raises(store.QueueError, match="not routed"):
        store.open_project_from_ruling(routed, qr["id"])


def test_urgency_and_public_title_carry_to_the_project(routed):
    p = file(routed, room(1, public_title="Bedroom off the dining hall"))
    r = rule(routed, p["id"])
    proj = store.open_project_from_ruling(routed, r["id"], urgency="high")
    assert proj["urgency"] == "high" and proj["public_title"] == "Bedroom off the dining hall"


# ---- routed refusal for each sole-writer kind (P3-B1) -----------------------------


def test_sole_writer_project_refused_for_a_routed_ruling(routed):
    p = file(routed, room())
    r = rule(routed, p["id"])
    with pytest.raises(store.QueueError, match="routed proposal type"):
        store.append(make_project(from_ruling=r["id"]), routed)


def test_sole_writer_executed_and_amend_refused_for_a_routed_project(routed):
    p, r, proj = open_room(routed)
    with pytest.raises(store.QueueError, match="routed proposal type"):
        store.append(legacy_executed(r["id"], proj), routed)
    with pytest.raises(store.QueueError, match="routed proposal type"):
        store.append(make_amend(project_id=proj["id"]), routed)


def test_sole_writer_still_writes_for_an_unrouted_type(tmp_path):
    path = db(tmp_path)
    p = file(path, make_proposal(type="room_siting"))
    r = rule(path, p["id"])
    proj = store.append(make_project(from_ruling=r["id"]), path)
    assert proj["role"] == "overseer"


def test_executor_cannot_write_for_an_unrouted_type(tmp_path):
    path = db(tmp_path)
    p = file(path, make_proposal(type="room_siting"))
    r = rule(path, p["id"])
    with pytest.raises(store.QueueError, match="not a routed proposal type"):
        store.append(make_project(role="conductor", from_ruling=r["id"]), path)


def test_overseer_may_still_abandon_a_routed_project(routed):
    p, r, proj = open_room(routed)
    store.append(make_abandon(project_id=proj["id"]), routed)
    assert store.project_status(routed, proj["id"])["status"] == "abandoned"


# ---- step content, runnable checks ---------------------------------------------------


def test_a_runnable_step_has_no_reasons(routed):
    p, r, proj = open_room(routed)
    assert store.check_step_runnable(routed, proj["id"], proj["steps"][0]["id"], latched=False) == []


def test_step_without_a_proposal_id_is_never_runnable(routed):
    p, r, proj = open_room(routed)
    odd = make_project(role="conductor", from_ruling=r["id"])  # would be a second project
    with pytest.raises(store.QueueError):
        store.append(odd, routed)
    reasons = store.check_step_runnable(routed, "project-0099", "x", latched=False)
    assert "no such project" in reasons[0]


def test_step_content_that_differs_from_its_proposal_is_not_runnable(routed):
    """The store never writes such a step through the executor API, so write
    one as the executor would have to forge it: a project whose step args
    differ from the ruled proposal's step."""
    p = file(routed, room())
    r = rule(routed, p["id"])
    pid = "project-0002"
    forged = {
        "id": f"{pid}/s1", "tool": "blueprint.reserve",
        "args": {"template": "bedroom-cell-v1", "purpose": "something else entirely"},
        "targets": {"set": [f"{pid}/s1"]}, "proposal_id": p["id"],
    }
    store.append(make_project(role="conductor", from_ruling=r["id"], id=pid, steps=[forged]), routed)
    reasons = store.check_step_runnable(routed, pid, forged["id"], latched=False)
    assert any("differs from proposal" in x for x in reasons)
    with pytest.raises(store.QueueError, match="differs from proposal"):
        store.begin_step_run(routed, pid, forged["id"], tick=1, baseline=None)
    # the same tool with different args is caught too, and so is a different tool
    forged2 = {**forged, "id": "project-0003/s1", "targets": {"set": ["project-0003/s1"]}}
    forged2["tool"] = "blueprint.release"
    p2 = file(routed, room(2))
    r2 = rule(routed, p2["id"])
    forged2["proposal_id"] = p2["id"]
    store.append(make_project(role="conductor", from_ruling=r2["id"], id="project-0003", steps=[forged2]), routed)
    assert any("differs" in x for x in store.check_step_runnable(routed, "project-0003", forged2["id"], latched=False))


def test_overseer_authored_steps_are_not_runnable(tmp_path):
    """A project the Overseer wrote (no proposal_id on its step) never runs,
    whatever the routing says."""
    path = db(tmp_path)
    p = file(path, make_proposal(type="room_siting"))
    r = rule(path, p["id"])
    proj = store.append(make_project(from_ruling=r["id"]), path)
    reasons = store.check_step_runnable(path, proj["id"], proj["steps"][0]["id"], latched=False)
    assert any("not built by the executor" in x for x in reasons)


def test_tripwire_latch_blocks_unless_urgency_high(routed):
    p, r, proj = open_room(routed)
    sid = proj["steps"][0]["id"]
    assert any("tripwire" in x for x in store.check_step_runnable(routed, proj["id"], sid, latched=True))
    p2 = file(routed, room(2))
    r2 = rule(routed, p2["id"])
    hi = store.open_project_from_ruling(routed, r2["id"], urgency="high")
    assert store.check_step_runnable(routed, hi["id"], hi["steps"][0]["id"], latched=True) == []


def test_closed_and_abandoned_projects_are_not_runnable(routed):
    p, r, proj = open_room(routed)
    sid = proj["steps"][0]["id"]
    store.close(routed, target_id=proj["id"], outcome="superseded", reason="replaced")
    assert any("closed" in x for x in store.check_step_runnable(routed, proj["id"], sid, latched=False))
    p2, r2, proj2 = open_room(routed, 2)
    store.append(make_abandon(project_id=proj2["id"]), routed)
    assert any("abandoned" in x for x in store.check_step_runnable(
        routed, proj2["id"], proj2["steps"][0]["id"], latched=False))


# ---- step-run lifecycle -------------------------------------------------------------


def test_step_run_lifecycle_success(routed):
    p, r, proj = open_room(routed)
    sid = proj["steps"][0]["id"]
    run = store.begin_step_run(routed, proj["id"], sid, tick=200, baseline=["res-0"])
    assert [x["run_id"] for x in store.unresolved_step_runs(routed)] == [run]
    assert store.get_step_run(routed, run)["baseline"] == ["res-0"]
    # an unresolved run blocks the step
    assert any("unresolved" in x for x in store.check_step_runnable(routed, proj["id"], sid, latched=False))
    out = store.finish_step_run(
        routed, run,
        {"actions": [{"tool": "blueprint.reserve", "outcome": "success", "targets": [sid],
                      "target_state": "issued", "game_refs": ["res-7"]}]},
    )
    assert out["run"]["status"] == "recorded" and out["run"]["handle"] == "res-7"
    ex = out["executed"]
    assert ex["role"] == "conductor" and ex["ruling_id"] == r["id"]
    assert ex["step_id"] == sid and ex["proposal_id"] == p["id"] and ex["cycle"] == 200
    assert store.unresolved_step_runs(routed) == []
    assert state_of(routed, proj["id"], sid) == ["issued"]
    assert store.issued_handles(routed, proj["id"]) == ["res-7"]
    assert any("already succeeded" in x for x in store.check_step_runnable(routed, proj["id"], sid, latched=False))
    with pytest.raises(store.QueueError, match="not 'issuing'"):
        store.finish_step_run(routed, run, {"actions": []})


def test_first_failure_leaves_the_step_retryable(routed):
    p, r, proj = open_room(routed)
    sid = proj["steps"][0]["id"]
    run = store.begin_step_run(routed, proj["id"], sid, tick=200, baseline=None)
    out = store.finish_step_run(
        routed, run, {"actions": [{"tool": "blueprint.reserve", "outcome": "failure", "detail": "blocked"}]})
    assert out["run"]["outcome"] == "failure"
    assert state_of(routed, proj["id"], sid) == ["ready"]
    assert store.check_step_runnable(routed, proj["id"], sid, latched=False) == []
    assert len(store.step_runs(routed, proj["id"], sid)) == 1
    # second attempt fails for good
    run2 = store.begin_step_run(routed, proj["id"], sid, tick=210, baseline=None)
    store.finish_step_run(routed, run2, {"actions": [
        {"tool": "blueprint.reserve", "outcome": "failure", "targets": [sid], "target_state": "failed"}]})
    assert any("failed" in x for x in store.check_step_runnable(routed, proj["id"], sid, latched=False))


def test_executor_executed_cannot_claim_done_or_other_targets(routed):
    p, r, proj = open_room(routed)
    sid = proj["steps"][0]["id"]
    run = store.begin_step_run(routed, proj["id"], sid, tick=200, baseline=None)
    with pytest.raises(store.QueueError, match="only an observation makes a step"):
        store.finish_step_run(routed, run, {"actions": [
            {"tool": "blueprint.reserve", "outcome": "success", "targets": [sid], "target_state": "done"}]})
    with pytest.raises(store.QueueError, match="synthetic target"):
        store.finish_step_run(routed, run, {"actions": [
            {"tool": "blueprint.reserve", "outcome": "success", "targets": ["other"], "target_state": "issued"}]})
    # the failed attempts rolled back: still issuing
    assert [x["run_id"] for x in store.unresolved_step_runs(routed)] == [run]


def test_resolve_uncertain_run_success_transient_and_held(routed):
    p, r, proj = open_room(routed)
    sid = proj["steps"][0]["id"]
    # transient: nothing landed, run void, the step runs again
    run = store.begin_step_run(routed, proj["id"], sid, tick=200, baseline=[])
    out = store.resolve_step_run(routed, run, "transient")
    assert out["run"]["status"] == "void" and out["executed"] is None
    assert store.check_step_runnable(routed, proj["id"], sid, latched=False) == []
    # held: blocks the step, no longer listed as unresolved
    run2 = store.begin_step_run(routed, proj["id"], sid, tick=210, baseline=[])
    assert store.resolve_step_run(routed, run2, "held")["run"]["status"] == "held"
    assert store.unresolved_step_runs(routed) == []
    assert any("held" in x for x in store.check_step_runnable(routed, proj["id"], sid, latched=False))


def test_resolve_success_appends_executed_with_the_handle(routed):
    p, r, proj = open_room(routed)
    sid = proj["steps"][0]["id"]
    run = store.begin_step_run(routed, proj["id"], sid, tick=200, baseline=[])
    with pytest.raises(store.QueueError, match="needs the handle"):
        store.resolve_step_run(routed, run, "success")
    out = store.resolve_step_run(routed, run, "success", handle="res-9")
    assert out["run"]["status"] == "resolved" and out["executed"]["actions"][0]["game_refs"] == ["res-9"]
    assert state_of(routed, proj["id"], sid) == ["issued"]
    assert store.issued_handles(routed, proj["id"]) == ["res-9"]
    with pytest.raises(store.QueueError, match="resolve outcome"):
        store.resolve_step_run(routed, run, "maybe")


def test_cleanup_runs_use_the_marker_without_an_executed(routed):
    p, r, proj = open_room(routed)
    run = store.begin_step_run(routed, proj["id"], "cleanup:res-1", tick=300, baseline=None)
    out = store.finish_step_run(routed, run, {"actions": [{"tool": "blueprint.unreserve", "outcome": "success"}]})
    assert out["executed"] is None and out["run"]["status"] == "recorded"
    assert not [r for r in store.load(routed) if r["kind"] == "executed"]


# ---- prerequisites through synthetic targets, arming on done ---------------------------


def _followup(path, proj, n, after, tool="blueprint.apply", phase="bedroom_cell_v1_shell", site="res-1"):
    rec = room(n, step={"tool": tool, "args": {"phase": phase, "site": site}},
               project_id=proj["id"], after_step=after)
    rec.pop("phases")
    p = file(path, rec)
    r = rule(path, p["id"])
    return p, r


def test_followup_apply_amends_with_the_whole_plan_and_requires_after_step(routed):
    p, r, proj = open_room(routed)
    s1 = proj["steps"][0]["id"]
    fp, fr = _followup(routed, proj, 2, s1)
    amend = store.apply_followup(routed, fp["id"])
    assert amend["kind"] == "amend" and amend["role"] == "conductor"
    assert [s["id"] for s in amend["steps"]] == [s1, f"{proj['id']}/s2"]
    new = amend["steps"][1]
    assert new["requires"] == [s1] and new["proposal_id"] == fp["id"]
    assert new["targets"] == {"set": [new["id"]]} and amend["adds"] == [new["id"]]
    assert store.project_status(routed, proj["id"])["version"] == 2
    assert state_of(routed, proj["id"], new["id"]) == ["waiting"]
    with pytest.raises(store.QueueError, match="already applied"):
        store.apply_followup(routed, fp["id"])


def test_prerequisites_run_through_synthetic_targets(routed):
    p, r, proj = open_room(routed)
    s1 = proj["steps"][0]["id"]
    fp, fr = _followup(routed, proj, 2, s1)
    s2 = store.apply_followup(routed, fp["id"])["steps"][1]["id"]
    # s2 is not runnable while s1 is not done
    assert any("prerequisites" in x for x in store.check_step_runnable(routed, proj["id"], s2, latched=False))
    run_step_ok(routed, proj["id"], s1)
    # issued is not done
    assert any("prerequisites" in x for x in store.check_step_runnable(routed, proj["id"], s2, latched=False))
    store.record_observation(routed, proj["id"], s1, tick=300, done=True, detail={})
    assert state_of(routed, proj["id"], s1) == ["done"]
    assert store.check_step_runnable(routed, proj["id"], s2, latched=False) == []
    # the project is not done until s2 is
    assert store.project_status(routed, proj["id"])["status"] == "active"
    run_step_ok(routed, proj["id"], s2, handle="site-3", tick=310)
    store.record_observation(routed, proj["id"], s2, tick=400, done=True, detail={"counts": {"dug": 4}})
    assert store.project_status(routed, proj["id"])["status"] == "done"


def _prediction_status(path, proposal_id):
    import sqlite3
    c = sqlite3.connect(path)
    try:
        return c.execute("SELECT status, due_game_tick FROM predictions WHERE record_id = ?",
                         (proposal_id,)).fetchone()
    finally:
        c.close()


def test_prediction_arms_on_done_only(routed):
    p, r, proj = open_room(routed)
    sid = proj["steps"][0]["id"]
    assert _prediction_status(routed, p["id"])[0] == store.AWAITING_EXECUTION
    # a failed run does not arm
    run = store.begin_step_run(routed, proj["id"], sid, tick=200, baseline=None)
    store.finish_step_run(routed, run, {"actions": [{"tool": "blueprint.reserve", "outcome": "failure"}]})
    assert _prediction_status(routed, p["id"])[0] == store.AWAITING_EXECUTION
    # a successful executed (issued) does not arm either
    run_step_ok(routed, proj["id"], sid)
    assert _prediction_status(routed, p["id"])[0] == store.AWAITING_EXECUTION
    # an observation that is not done does not arm
    store.record_observation(routed, proj["id"], sid, tick=250, done=False, detail={})
    assert _prediction_status(routed, p["id"])[0] == store.AWAITING_EXECUTION
    # done arms from the observation tick
    store.record_observation(routed, proj["id"], sid, tick=300, done=True, detail={})
    status, due = _prediction_status(routed, p["id"])
    assert status == "pending" and due == 300 + 1200


def test_followup_proposals_prediction_arms_on_its_own_step_done(routed):
    p, r, proj = open_room(routed)
    s1 = proj["steps"][0]["id"]
    run_step_ok(routed, proj["id"], s1)
    store.record_observation(routed, proj["id"], s1, tick=300, done=True, detail={})
    fp, fr = _followup(routed, proj, 2, s1)
    s2 = store.apply_followup(routed, fp["id"])["steps"][1]["id"]
    assert _prediction_status(routed, fp["id"])[0] == store.AWAITING_EXECUTION
    run_step_ok(routed, proj["id"], s2, handle="site-3", tick=310)
    store.record_observation(routed, proj["id"], s2, tick=500, done=True, detail={})
    assert _prediction_status(routed, fp["id"]) == ("pending", 500 + 1200)


def test_legacy_executed_still_arms_the_old_way(tmp_path):
    path = db(tmp_path)
    p = file(path, make_proposal(type="room_siting"))
    r = rule(path, p["id"])
    proj = store.append(make_project(from_ruling=r["id"]), path)
    store.append(legacy_executed(r["id"], proj, cycle=500), path)
    assert _prediction_status(path, p["id"]) == ("pending", 500 + 1200)


def test_observation_done_needs_an_issued_step(routed):
    p, r, proj = open_room(routed)
    sid = proj["steps"][0]["id"]
    with pytest.raises(store.QueueError, match="only an issued step"):
        store.record_observation(routed, proj["id"], sid, tick=100, done=True, detail={})


def test_observation_can_name_an_amend_added_step(routed):
    p, r, proj = open_room(routed)
    s1 = proj["steps"][0]["id"]
    fp, fr = _followup(routed, proj, 2, s1)
    s2 = store.apply_followup(routed, fp["id"])["steps"][1]["id"]
    obs = store.record_observation(routed, proj["id"], s2, tick=100, done=False, detail={"reason": "waiting"})
    assert obs["results"][0]["reason"] == "waiting"


def test_observation_detail_is_bounded_and_coordinate_free(routed):
    p, r, proj = open_room(routed)
    sid = proj["steps"][0]["id"]
    with pytest.raises(store.QueueError, match="coordinate"):
        store.record_observation(routed, proj["id"], sid, tick=1, done=False, detail={"at": "x=4"})


# ---- amend base check -------------------------------------------------------------------


def test_amend_base_check_refuses_a_dropped_step_not_named(routed):
    p, r, proj = open_room(routed)
    s1 = proj["steps"][0]["id"]
    new = {"id": f"{proj['id']}/s2", "tool": "blueprint.apply", "args": {},
           "targets": {"set": [f"{proj['id']}/s2"]}, "requires": [], "proposal_id": p["id"]}
    base = {"kind": "amend", "role": "conductor", "cycle": 1, "snapshot": "s",
            "project_id": proj["id"], "reason": "test"}
    with pytest.raises(store.QueueError, match="omits step"):
        store.append({**base, "steps": [new]}, routed)
    # kept, or named in drops, passes
    store.append({**base, "steps": [proj["steps"][0], new], "adds": [new["id"]]}, routed)


def test_two_followups_cannot_build_from_the_same_stale_base(routed):
    p, r, proj = open_room(routed)
    s1 = proj["steps"][0]["id"]
    fp1, _ = _followup(routed, proj, 2, s1)
    fp2, _ = _followup(routed, proj, 3, s1, phase="bedroom_cell_v1_finish")
    a1 = store.apply_followup(routed, fp1["id"])
    a2 = store.apply_followup(routed, fp2["id"])
    assert [s["id"] for s in a2["steps"]] == [s1, a1["steps"][1]["id"], f"{proj['id']}/s3"]


def test_followup_apply_refuses_unruled_closed_and_unplanned(routed):
    p, r, proj = open_room(routed)
    s1 = proj["steps"][0]["id"]
    rec = room(2, step={"tool": "blueprint.apply", "args": {}}, project_id=proj["id"], after_step=s1)
    rec.pop("phases")
    fp = file(routed, rec)
    with pytest.raises(store.QueueError, match="neither accepted nor covered"):
        store.apply_followup(routed, fp["id"])
    rule(routed, fp["id"], "reject")
    with pytest.raises(store.QueueError, match="neither accepted nor covered"):
        store.apply_followup(routed, fp["id"])


# ---- unexecuted, pending, closing --------------------------------------------------------


def test_unexecuted_excludes_routed_followups_and_closed(routed, tmp_path):
    # unrouted accepted work with no executed record is listed...
    qp = file(routed, make_proposal(role="quartermaster", type="work_order",
                                    summary="Brew drinks " + "u" * 4))
    qr = rule(routed, qp["id"])
    p, r, proj = open_room(routed)
    fp, fr = _followup(routed, proj, 2, proj["steps"][0]["id"])
    listed = {e["proposal"]["id"] for e in store.unexecuted_accepted_proposals(routed)}
    assert listed == {qp["id"]}  # the legacy room ruling is closed? no: see next assert
    # ...the legacy room proposal (proposal-0001) is routed now, so excluded
    assert "proposal-0001" not in listed
    # closing the ruling removes it
    store.close(routed, target_id=qr["id"], outcome="not_done", reason="test")
    assert store.unexecuted_accepted_proposals(routed) == []


def test_unexecuted_is_keyed_by_the_proposal_id(tmp_path):
    path = db(tmp_path)
    p = file(path, make_proposal(type="room_siting"))
    r = rule(path, p["id"])
    assert [e["ruling_id"] for e in store.unexecuted_accepted_proposals(path)] == [r["id"]]
    proj = store.append(make_project(from_ruling=r["id"]), path)
    store.append(legacy_executed(r["id"], proj), path)
    assert store.unexecuted_accepted_proposals(path) == []


def test_pending_proposals_excludes_closed(tmp_path):
    path = db(tmp_path)
    p = file(path, make_proposal(type="room_siting"))
    assert [x["id"] for x in store.pending_proposals(path)] == [p["id"]]
    store.set_cutover(path, "rooms", rule(path, file(path, make_proposal(
        type="room_siting", summary="Another legacy room " + "m" * 6))["id"])["id"])
    store.close(path, target_id=p["id"], outcome="not_done", reason="re-file as an exact action")
    assert p["id"] not in [x["id"] for x in store.pending_proposals(path)]
    with pytest.raises(store.QueueError, match="already closed"):
        store.close(path, target_id=p["id"], outcome="not_done", reason="again")


def test_close_refusals(routed):
    with pytest.raises(store.QueueError, match="cannot tell"):
        store.close(routed, target_id="thing-1", outcome="not_done", reason="x")
    with pytest.raises(store.QueueError, match="does not refer to an existing project"):
        store.close(routed, target_id="project-0099", outcome="not_done", reason="x")
    with pytest.raises(store.QueueError, match="final ruling"):
        store.close(routed, target_id="proposal-0001", outcome="not_done", reason="x")
    with pytest.raises(store.QueueError, match="outcome"):
        store.close(routed, target_id="ruling-0001", outcome="finished", reason="x")


def test_close_project_carries_cleanup_results(routed):
    p, r, proj = open_room(routed)
    rec = store.close(routed, target_id=proj["id"], outcome="abandoned", reason="Overseer abandoned",
                      cleanup=[{"handle": "res-1", "tool": "blueprint.unreserve", "outcome": "released"}])
    assert rec["project_id"] == proj["id"] and rec["cleanup"][0]["handle"] == "res-1"
    assert store.open_projects(routed) == []


def test_projects_awaiting_cleanup_lists_abandoned_routed_projects(routed):
    p, r, proj = open_room(routed)
    run_step_ok(routed, proj["id"], proj["steps"][0]["id"], handle="res-5")
    assert store.projects_awaiting_cleanup(routed) == []
    store.append(make_abandon(project_id=proj["id"]), routed)
    assert store.projects_awaiting_cleanup(routed) == [{"project_id": proj["id"], "handles": ["res-5"]}]
    store.close(routed, target_id=proj["id"], outcome="abandoned", reason="cleaned up")
    assert store.projects_awaiting_cleanup(routed) == []


# ---- close_legacy and the legacy sweep -----------------------------------------------------


def test_close_legacy_computes_completed_or_not_done_and_makes_no_dfhack_call(tmp_path, monkeypatch):
    path = db(tmp_path)
    done_p = file(path, make_proposal(type="room_siting", summary="Built long ago " + "d" * 3))
    done_r = rule(path, done_p["id"])
    done_proj = store.append(make_project(from_ruling=done_r["id"]), path)
    store.append(legacy_executed(done_r["id"], done_proj), path)
    open_p = file(path, make_proposal(type="room_siting", summary="Never carried out " + "n" * 5))
    open_r = rule(path, open_p["id"])
    store.set_cutover(path, "legacy", open_r["id"])

    def no_network(*a, **k):
        raise AssertionError("close_legacy must make no network call")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    listed = store.legacy_targets(path, "legacy")
    assert [(t["id"], t["executed"]) for t in listed] == [(done_r["id"], True), (open_r["id"], False)]
    a = store.close_legacy(path, done_r["id"], reason="deploy 2a legacy sweep")
    b = store.close_legacy(path, open_r["id"], reason="deploy 2a legacy sweep")
    assert (a["outcome"], b["outcome"]) == ("completed", "not_done")
    assert a["role"] == "conductor" and a["ruling_id"] == done_r["id"]
    assert store.legacy_targets(path, "legacy") == []
    with pytest.raises(store.QueueError, match="already closed"):
        store.close_legacy(path, open_r["id"], reason="again")


def test_close_legacy_refused_above_the_legacy_cutover(tmp_path):
    path = db(tmp_path)
    ids = []
    for n in range(1, 4):
        p = file(path, make_proposal(type="room_siting", summary=f"Idea number {n} " + "v" * n))
        ids.append(rule(path, p["id"])["id"])
    with pytest.raises(store.QueueError, match="above its cutover"):
        store.close_legacy(path, ids[0], reason="no cutover yet")
    store.set_cutover(path, "legacy", ids[1])
    store.close_legacy(path, ids[1], reason="ok")
    with pytest.raises(store.QueueError, match="above its cutover"):
        store.close_legacy(path, ids[2], reason="too new")


def test_legacy_check_before_a_cutover_lists_up_to_the_highest_ruling(tmp_path):
    path = db(tmp_path)
    for n in range(1, 4):
        p = file(path, make_proposal(type="room_siting", summary=f"Check idea {n} " + "c" * n))
        rule(path, p["id"], "accept" if n != 2 else "reject")
    got = [t["id"] for t in store.legacy_targets(path, "legacy")]
    assert got == ["ruling-0001", "ruling-0003"]  # accepted only, nothing set
    assert store.cutover(path, "legacy") is None
    assert store.highest_ruling(path) == "ruling-0003"


def test_group_sweep_lists_rulings_projects_and_pending_proposals(tmp_path, monkeypatch):
    path = db(tmp_path)
    # an accepted room ruling with an open Overseer project, a pending room proposal, an unrelated order
    a = file(path, make_proposal(type="room_siting", summary="Accepted room " + "a" * 4))
    ar = rule(path, a["id"])
    proj = store.append(make_project(from_ruling=ar["id"]), path)
    pend = file(path, make_proposal(type="corridor", summary="Pending corridor " + "p" * 4))
    o = file(path, make_proposal(role="quartermaster", type="work_order", summary="Brew " + "o" * 6))
    rule(path, o["id"])
    kinds = sorted((t["kind"], t["id"]) for t in store.legacy_targets(path, "rooms"))
    assert kinds == sorted([("ruling", ar["id"]), ("project", proj["id"]), ("proposal", pend["id"])])
    assert all(t["group"] == "rooms" for t in store.legacy_targets(path, "rooms"))
    # close the pending proposal needs the group cutover
    with pytest.raises(store.QueueError, match="no cutover"):
        store.close_legacy(path, pend["id"], reason="freeze")
    store.set_cutover(path, "rooms", ar["id"])
    done = [store.close_legacy(path, t["id"], reason="rooms cutover")
            for t in store.legacy_targets(path, "rooms")]
    assert sorted(d["outcome"] for d in done) == ["not_done"] * 3
    assert store.legacy_targets(path, "rooms") == []
    assert [x["id"] for x in store.pending_proposals(path)] == []


def test_close_legacy_refuses_an_executor_project_and_a_proposal_with_a_step(routed):
    p, r, proj = open_room(routed)
    with pytest.raises(store.QueueError, match="executor project"):
        store.close_legacy(routed, proj["id"], reason="x")
    with pytest.raises(store.QueueError, match="carries a step"):
        store.close_legacy(routed, p["id"], reason="x")


# ---- the one WIP definition ------------------------------------------------------------------


def test_open_projects_is_the_one_wip_definition(routed):
    assert store.open_projects(routed) == []
    p, r, proj = open_room(routed)
    (entry,) = store.open_projects(routed)
    assert entry["project_id"] == proj["id"] and entry["steps_open"] is True
    assert entry["phases_remaining"] == 2 and entry["urgency"] == "normal"
    # a finished first step with phases still declared: not yet applied, still open
    s1 = proj["steps"][0]["id"]
    run_step_ok(routed, proj["id"], s1)
    store.record_observation(routed, proj["id"], s1, tick=300, done=True, detail={})
    (entry,) = store.open_projects(routed)
    assert entry["steps_open"] is False and entry["phases_remaining"] == 2
    # apply both declared phases and finish them: no longer open
    prev = s1
    for n, phase in ((2, "bedroom_cell_v1_shell"), (3, "bedroom_cell_v1_finish")):
        fp, _ = _followup(routed, proj, n, prev, phase=phase)
        prev = store.apply_followup(routed, fp["id"])["steps"][-1]["id"]
        run_step_ok(routed, proj["id"], prev, handle=f"site-{n}", tick=300 + n)
        store.record_observation(routed, proj["id"], prev, tick=400 + n, done=True, detail={})
    assert store.open_projects(routed) == []


def test_open_projects_excludes_closed_abandoned_and_legacy(routed):
    p, r, proj = open_room(routed)
    p2, r2, proj2 = open_room(routed, 2)
    store.append(make_abandon(project_id=proj2["id"]), routed)
    assert [e["project_id"] for e in store.open_projects(routed)] == [proj["id"]]
    store.close(routed, target_id=proj["id"], outcome="superseded", reason="x")
    assert store.open_projects(routed) == []


def test_open_projects_counts_everything_before_any_cutover(tmp_path):
    path = db(tmp_path)
    p = file(path, make_proposal(type="room_siting"))
    r = rule(path, p["id"])
    store.append(make_project(from_ruling=r["id"]), path)
    assert len(store.open_projects(path)) == 1  # unchanged behaviour before 2a
    store.set_cutover(path, "legacy", r["id"])
    assert store.open_projects(path) == []  # nixed by the legacy cutover


# ---- store housekeeping ----------------------------------------------------------------------


def test_v2_database_migrates_to_the_new_tables(tmp_path):
    import sqlite3
    path = db(tmp_path)
    store.append(make_proposal(type="room_siting"), path, game_tick=1)
    c = sqlite3.connect(path)
    c.executescript("DROP TABLE meta; DROP TABLE step_runs; UPDATE schema_version SET version = 2;")
    c.commit()
    c.close()
    assert store.cutover(path, "legacy") is None  # reopening migrates and recreates
    c = sqlite3.connect(path)
    try:
        assert c.execute("SELECT version FROM schema_version").fetchone()[0] == store.SCHEMA_VERSION
        c.execute("SELECT * FROM step_runs").fetchall()
    finally:
        c.close()


def test_feed_knows_the_close_kind():
    from dfqueue import feed
    assert "close" in feed.KNOWN_KINDS


def test_close_record_renders_in_the_feed_and_the_prompt_xml():
    from dfqueue import feed, render
    rec = {"id": "close-0001", "ts": "2026-10-05T00:00:00+00:00", "kind": "close",
           "role": "conductor", "cycle": 5, "snapshot": "s", "ruling_id": "ruling-0001",
           "outcome": "not_done", "reason": "legacy sweep, secret reason"}
    assert schema.validate(rec) == []
    assert feed.compute_reply_to(rec) == "ruling-0001"
    item = feed.build_public_item(rec, seq=1, reply_to="ruling-0001", thread="proposal-0001",
                                  badge=None, ctx={})
    assert item["text"] == "Closed without being carried out."  # never the reason
    assert "secret" not in str(item)
    xml = render.to_xml(rec)
    assert "<outcome>not_done</outcome>" in xml and "<ruling_id>ruling-0001</ruling_id>" in xml
