"""Per-tool execution data (dfmcp/action_data.py) against the real TOOLS.yaml
declarations and the blueprint fixture outputs (dfmcp/tests/fixtures/blueprint/,
generated from the Lua source by tests/test_blueprint_fixtures.py).

The fixture test is the one design 2.3 and P3-M2 ask for: every path a
declaration relies on must exist in a real output, so a wrong path fails here
and not on the live fort. The fixtures are built from the source until the
supervised bedroom records real ones.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dfmcp import action_data as ad
from dfmcp.registry import load_registry

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "blueprint"
TEMPLATES = {
    "bedroom-cell-v1": {"shell": "bedroom_cell_v1_shell", "meta": "bedroom_cell_v1_finish",
                        "leaves": ["bedroom_cell_v1_zone", "bedroom_cell_v1_build"]},
    "office-room-v2": {"shell": "office_room_v2_shell", "meta": "office_room_v2_finish",
                       "leaves": ["office_room_v2_build", "office_room_v2_zone"]},
}


@pytest.fixture(scope="module")
def registry():
    return load_registry()


@pytest.fixture(scope="module")
def specs(registry):
    return ad.load_all(registry)


def fx(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


# ---- parsing --------------------------------------------------------------------


def test_the_room_tools_declare_execution_data(specs):
    assert {"blueprint.reserve", "blueprint.apply", "blueprint.release", "blueprint.unreserve"} <= set(specs)


def _ok_block(**over):
    block = {"verdict": {"ok": "ok"}, "dry_run_echo": "dry_run"}
    block.update(over)
    return block


@pytest.mark.parametrize("bad, match", [
    ({"nonsense": 1}, "unknown key"),
    ({"verdict": None}, "verdict is required"),
    ({"verdict": {"bogus": "x"}}, "unknown key"),
    ({"verdict": {"reason": "why"}}, "nothing that can refuse or pass"),
    ({"dry_run_echo": None}, "dry_run_echo is required"),
    ({"nothing_applied": {"maybe": 1}}, "nothing_applied"),
    ({"landed": [{"kind": "guess"}]}, "landed"),
    ({"landed": [{"kind": "new_row", "read": {"tool": "x", "rows": "result"}}]}, "handle_field"),
    ({"progress": {"done_field": "x"}}, "progress needs"),
    ({"phases": {"arg": "a"}}, "phases needs"),
    ({"cleanup": {"handle_prefix": "x-"}}, "cleanup needs"),
])
def test_a_malformed_declaration_is_a_load_error(bad, match):
    block = _ok_block(**bad)
    block = {k: v for k, v in block.items() if v is not None}
    with pytest.raises(ad.ActionDataError, match=match):
        ad.parse("x.y", block)


def test_a_tool_without_dry_run_cannot_declare_execution():
    with pytest.raises(ad.ActionDataError, match="DRY_RUN"):
        ad.parse("x.y", _ok_block(), takes_dry_run=False)


def test_every_declaring_tool_takes_dry_run(registry, specs):
    for tool_id in specs:
        assert any("DRY_RUN" in a for a in registry.get(tool_id).args), tool_id


# ---- every declared path exists in a real output ----------------------------------


@pytest.mark.parametrize("bp", sorted(TEMPLATES))
def test_every_declared_path_exists_in_a_fixture_output(specs, bp):
    data = fx(bp)
    shell = TEMPLATES[bp]["shell"]
    outputs = {
        "blueprint.reserve": {"dry": data["reserve_dry_run"], "real": data["reserve_success"],
                              "refusal": data["reserve_refusal_overlap"]},
        "blueprint.apply": {"dry": data[f"apply_{shell}_dry_run"], "real": data[f"apply_{shell}_success"],
                            "refusal": data[f"apply_{TEMPLATES[bp]['meta']}_refused_shell_pending"]},
    }
    for tool_id, by_kind in outputs.items():
        paths = ad.declared_paths(specs[tool_id])
        for kind, plist in paths.items():
            for path in plist:
                if kind == "real" and path == "dry_run":
                    continue
                found, _ = ad.get_path(by_kind[kind], path)
                assert found, f"{tool_id}: {path!r} is not in the {kind} fixture"


def test_progress_landed_phases_and_cleanup_paths_exist_in_fixtures(specs):
    data = fx("bedroom-cell-v1")
    apply = specs["blueprint.apply"]
    status = data["status_bedroom_cell_v1_build_complete"]
    p = apply.progress
    for path in [p["done_field"]] + [c["path"] for c in (p["not_done_if"], p["stalled_if"], p["blocked_if"])]:
        assert ad.get_path(status, path)[0], path
    assert ad.get_path(data["plan"], apply.phases["source"]["rows"])[0]
    plan_rows = data["plan"]["phases"]
    assert all(apply.phases["source"]["label_field"] in r for r in plan_rows)
    assert any(apply.phases["source"]["applies_field"] in r for r in plan_rows)
    reservations = ad.unwrap(data["reservations"])["result"]
    sites = ad.unwrap(data["sites"])["result"]
    reserve_landed = specs["blueprint.reserve"].landed[0]
    assert reserve_landed["handle_field"] in reservations[0] and reserve_landed["match"]["field"] in reservations[0]
    carve, on_site = apply.landed
    assert carve["find"]["field"] in reservations[0] and carve["field"] in reservations[0]
    assert on_site["find"]["field"] in sites[0] and on_site["field"] in sites[0]
    # the read tools the declarations name are real tools, and every cleanup tool takes its args
    for tool_id in ("blueprint.release", "blueprint.unreserve"):
        assert specs[tool_id].cleanup["handle_prefix"]


# ---- verdicts ----------------------------------------------------------------------


@pytest.mark.parametrize("bp", sorted(TEMPLATES))
def test_judge_on_the_fixtures(specs, bp):
    data = fx(bp)
    reserve, apply = specs["blueprint.reserve"], specs["blueprint.apply"]
    shell, meta = TEMPLATES[bp]["shell"], TEMPLATES[bp]["meta"]
    assert ad.judge(reserve, data["reserve_dry_run"], dry=True).ok
    assert ad.judge(reserve, data["reserve_success"], dry=False).ok
    refused = ad.judge(reserve, data["reserve_refusal_overlap"], dry=False)
    assert refused.kind == "refused" and "overlaps" in refused.reason
    assert ad.judge(apply, data[f"apply_{shell}_dry_run"], dry=True).ok
    assert ad.judge(apply, data[f"apply_{shell}_success"], dry=False).ok
    blocked = ad.judge(apply, data[f"apply_{meta}_refused_shell_pending"], dry=False)
    assert blocked.kind == "refused" and "shell is not finished" in blocked.reason
    assert ad.issued_handle(apply, data[f"apply_{shell}_success"]) == "site-1"
    assert ad.issued_handle(reserve, data["reserve_success"]) == "res-1"
    assert ad.issued_handle(reserve, data["reserve_dry_run"]) is None


def test_a_dry_run_that_did_not_echo_dry_is_invalid_and_a_real_one_that_echoed_dry_too(specs):
    data = fx("bedroom-cell-v1")
    reserve = specs["blueprint.reserve"]
    assert ad.judge(reserve, data["reserve_success"], dry=True).kind == "invalid"
    assert ad.judge(reserve, data["reserve_dry_run"], dry=False).kind == "invalid"
    no_echo = {k: v for k, v in data["reserve_dry_run"].items() if k != "dry_run"}
    v = ad.judge(reserve, no_echo, dry=True)
    assert v.kind == "invalid" and "dry_run" in v.missing


def test_an_absent_positive_field_is_invalid_never_a_pass(specs):
    data = fx("bedroom-cell-v1")
    out = {k: v for k, v in data["reserve_dry_run"].items() if k != "would_reserve"}
    v = ad.judge(specs["blueprint.reserve"], out, dry=True)
    assert v.kind == "invalid" and v.missing == ("would_reserve",)
    out = {k: v for k, v in data["apply_bedroom_cell_v1_shell_dry_run"].items() if k != "ok"}
    assert ad.judge(specs["blueprint.apply"], out, dry=True).kind == "invalid"


def test_a_script_error_object_is_a_refusal_with_its_message(specs):
    v = ad.judge(specs["blueprint.apply"], {"error": "no template 'x'"}, dry=True)
    assert v.kind == "refused" and "no template" in v.reason
    assert ad.judge(specs["blueprint.apply"], ["not", "an", "object"], dry=True).kind == "invalid"


def test_nothing_applied(specs):
    data = fx("bedroom-cell-v1")
    apply, reserve = specs["blueprint.apply"], specs["blueprint.reserve"]
    # a refusal before quickfort ran carries no `designated` group: nothing applied
    assert ad.nothing_applied(apply, data["apply_bedroom_cell_v1_zone_refused_shell_pending"]) is True
    assert ad.nothing_applied(apply, {"designated": {"dig_tiles": 3, "zones": 0, "buildings": 0}}) is False
    assert ad.nothing_applied(apply, {"designated": {"dig_tiles": "many"}}) is None
    assert ad.nothing_applied(reserve, data["reserve_refusal_overlap"]) is True
    assert ad.nothing_applied(specs["blueprint.release"], {}) is None  # nothing declared: cannot tell


def test_resolution_fields_come_from_the_dry_run(specs):
    data = fx("bedroom-cell-v1")
    vals, missing = ad.resolution(specs["blueprint.reserve"], data["reserve_dry_run"])
    assert missing == [] and vals["near_landmark"] == "Well" and vals["level"] == 0
    assert vals == ad.resolution(specs["blueprint.reserve"], data["reserve_success"])[0]
    _, missing = ad.resolution(specs["blueprint.reserve"], {"near_landmark": "Well"})
    assert "level" in missing


def test_purpose_gets_the_proposal_id_appended_once(specs):
    reserve = specs["blueprint.reserve"]
    args = {"template": "t", "purpose": "bedroom row 1", "site": "Well"}
    once = ad.apply_append(reserve, args, {"proposal_id": "proposal-0007"})
    assert once["purpose"] == "bedroom row 1 proposal-0007"
    assert ad.apply_append(reserve, once, {"proposal_id": "proposal-0007"})["purpose"] == once["purpose"]
    assert ad.apply_append(specs["blueprint.apply"], args, {"proposal_id": "p"}) == args


# ---- progress ----------------------------------------------------------------------


@pytest.mark.parametrize("bp", sorted(TEMPLATES))
def test_progress_per_phase_on_the_fixtures(specs, bp):
    data = fx(bp)
    apply = specs["blueprint.apply"]
    shell, meta = TEMPLATES[bp]["shell"], TEMPLATES[bp]["meta"]
    # furniture pending: the shell is done without furniture; the meta phase is not
    assert ad.judge_progress(apply, data[f"status_{shell}_furniture_pending"])["state"] == "done"
    assert ad.judge_progress(apply, data[f"status_{meta}_furniture_pending"])["state"] == "issued"
    assert ad.judge_progress(apply, data[f"status_{meta}_complete"])["state"] == "done"


def test_progress_states(specs):
    apply = specs["blueprint.apply"]
    base = {"phase": {"done": True}, "dig": {"state": "none_pending"}, "finish_state": {"blocked_total": 0}}
    assert ad.judge_progress(apply, base)["state"] == "done"
    assert ad.judge_progress(apply, {**base, "dig": {"state": "in_progress"}})["state"] == "issued"
    assert ad.judge_progress(apply, {**base, "phase": {"done": False}, "dig": {"state": "stalled"}})["state"] == "stalled"
    assert ad.judge_progress(apply, {**base, "phase": {"done": False},
                                     "finish_state": {"blocked_total": 2}})["state"] == "blocked_material"
    # a null or absent read is never done
    assert ad.judge_progress(apply, {**base, "phase": {"done": None}})["state"] == "unknown"
    assert ad.judge_progress(apply, {"dig": {}})["state"] == "unknown"
    assert ad.judge_progress(apply, {"error": "no site"})["state"] == "unknown"


def test_a_tool_with_no_progress_read_is_done_once_issued(specs):
    assert ad.judge_progress(specs["blueprint.reserve"], {})["state"] == "done"
    assert ad.progress_request(specs["blueprint.reserve"], {}) is None
    tool, args = ad.progress_request(specs["blueprint.apply"], {"phase": "p", "handle": "site-4"})
    assert tool == "blueprint.status" and args == {"site_id": "site-4", "phase": "p"}


# ---- landed ------------------------------------------------------------------------


def test_landed_new_row_for_a_reserve(specs):
    reserve = specs["blueprint.reserve"]
    entry = ad.landed_entry(reserve, {"purpose": "x"})
    before = {"result": [{"handle": "res-1", "purpose": "old room proposal-0001"}]}
    ctx = {"proposal_id": "proposal-0009"}
    base = ad.landed_baseline(entry, before, ctx)
    assert base == {"handles": ["res-1"]}
    after = {"result": [*before["result"], {"handle": "res-2", "purpose": "bedroom proposal-0009"}]}
    assert ad.landed_resolve(entry, base, after, ctx) == ("success", "res-2")
    assert ad.landed_resolve(entry, base, before, ctx) == ("nothing", None)
    # someone else's new reservation is not ours
    other = {"result": [*before["result"], {"handle": "res-3", "purpose": "other proposal-0004"}]}
    assert ad.landed_resolve(entry, base, other, ctx) == ("nothing", None)
    twice = {"result": [*after["result"], {"handle": "res-4", "purpose": "again proposal-0009"}]}
    assert ad.landed_resolve(entry, base, twice, ctx)[0] == "unreadable"
    assert ad.landed_resolve(entry, base, {"error": "x"}, ctx)[0] == "unreadable"
    assert ad.landed_baseline(entry, {"nope": 1}, ctx) is None


def test_landed_for_an_apply_by_the_kind_of_site_argument(specs):
    apply = specs["blueprint.apply"]
    carve = ad.landed_entry(apply, {"site": "res-3"})
    on_site = ad.landed_entry(apply, {"site": "site-8"})
    assert carve["kind"] == "field_set" and on_site["kind"] == "list_gains"
    assert ad.landed_entry(apply, {"site": "Well"}) is None
    ctx = {"site": "res-3", "phase": "p_shell"}
    before = {"result": [{"handle": "res-3", "site_handle": None}]}
    base = ad.landed_baseline(carve, before, ctx)
    after = {"result": [{"handle": "res-3", "site_handle": "site-8"}]}
    assert ad.landed_resolve(carve, base, after, ctx) == ("success", "site-8")
    assert ad.landed_resolve(carve, base, before, ctx) == ("nothing", None)
    ctx = {"site": "site-8", "phase": "p_zone"}
    before = {"result": [{"handle": "site-8", "phases_applied": ["p_shell"]}]}
    base = ad.landed_baseline(on_site, before, ctx)
    after = {"result": [{"handle": "site-8", "phases_applied": ["p_shell", "p_zone"]}]}
    assert ad.landed_resolve(on_site, base, after, ctx) == ("success", "site-8")
    assert ad.landed_resolve(on_site, base, before, ctx) == ("nothing", None)
    gone = {"result": []}
    assert ad.landed_resolve(on_site, base, gone, ctx)[0] == "unreadable"


def test_landed_with_the_real_fixture_shapes(specs):
    data = fx("bedroom-cell-v1")
    carve = specs["blueprint.apply"].landed[0]
    ctx = {"site": "res-1", "phase": "bedroom_cell_v1_shell"}
    base = ad.landed_baseline(carve, data["reservations"] if isinstance(data["reservations"], dict)
                              else {"result": data["reservations"]}, ctx)
    after = {"result": data["reservations_after_shell_apply"]}
    assert ad.landed_resolve(carve, base, after, ctx) == ("success", "site-1")


# ---- phases ------------------------------------------------------------------------


@pytest.mark.parametrize("bp", sorted(TEMPLATES))
def test_declared_phases_against_the_real_plan(specs, bp):
    t = TEMPLATES[bp]
    plan = ad.plan_phases(specs["blueprint.apply"], fx(bp)["plan"])
    labels = [p["label"] for p in plan]
    assert t["shell"] in labels and t["meta"] in labels
    assert ad.check_declared_phases(plan, [t["shell"], t["meta"]], None) == []
    # a meta together with one of its own leaves would apply the leaf twice
    twice = ad.check_declared_phases(plan, [t["leaves"][0], t["meta"]], None)
    assert twice and "twice" in twice[0]
    assert any("twice" in e for e in ad.check_declared_phases(plan, [t["meta"]], t["leaves"][1]))
    assert any("not a phase" in e for e in ad.check_declared_phases(plan, ["nope"], None))
    assert any("order" in e for e in ad.check_declared_phases(plan, [t["meta"], t["shell"]], None))


# ---- cleanup -----------------------------------------------------------------------


def test_cleanup_is_chosen_by_handle_prefix_from_the_tools_own_data(registry):
    tool, args, spec = ad.cleanup_for(registry, "site-4")
    assert tool == "blueprint.release" and args == {"site_id": "site-4", "dry_run": "false", "any_pending": "true"}
    assert spec.cleanup["report_as"] == "released"
    tool, args, _ = ad.cleanup_for(registry, "res-2")
    assert tool == "blueprint.unreserve" and args == {"res_id": "res-2", "dry_run": "false"}
    assert ad.cleanup_for(registry, "zone-9") is None


def test_substitute_refuses_a_missing_variable():
    assert ad.substitute({"a": ["x-$h"]}, {"h": "1"}) == {"a": ["x-1"]}
    with pytest.raises(ad.ActionDataError):
        ad.substitute("$nope", {})


def test_the_fixture_check_can_fail(specs):
    """Verify the verification: a declaration naming a path no output has must
    be caught by the same check the fixture tests use."""
    data = fx("bedroom-cell-v1")
    wrong = ad.parse("x.y", {"verdict": {"dry_ok": "would_reserv"}, "dry_run_echo": "dry_run"})
    missing = [p for p in ad.declared_paths(wrong)["dry"] if not ad.get_path(data["reserve_dry_run"], p)[0]]
    assert missing == ["would_reserv"]
