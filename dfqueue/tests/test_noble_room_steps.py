"""2026-10-08, noble rooms: giving a noble the room their position needs is a
routed `zone.assign-owner` step, tacked onto an open room project as a follow-up
or filed alone as a one-step proposal. The queue already supports appending a
step to an accepted project (follow-up + `apply_followup`, an `amend`); what this
adds is that the duplicate refusal now covers such a follow-up, and
`open_step_calls`, the read the conductor's noble-room watch uses to know the
need is already covered."""

from __future__ import annotations

import pytest

from dfqueue import schema, store
from dfqueue.tests._helpers import make_proposal
from dfqueue.tests.test_stage2a import file, open_room, room, routed, rule  # noqa: F401 (routed is a fixture)


def assign(zone_id=13, unit_id=345, *, n=1, **extra):
    """A one-step zone.assign-owner proposal, worded freely."""
    rec = make_proposal(
        type="room_siting",
        summary=f"Give the manager the office, take {n}, zone {zone_id}",
        rationale=f"The manager has no office of their own; zone {zone_id} is unowned, take {n} {'r' * n}.",
        step={"tool": "zone.assign-owner", "args": {"zone_id": zone_id, "unit_id": unit_id}},
    )
    rec.update(extra)
    return rec


def assign_followup(proj, after, zone_id=13, unit_id=345, n=2, **extra):
    rec = assign(zone_id, unit_id, n=n, project_id=proj["id"], after_step=after, **extra)
    return rec


def test_an_assign_owner_step_can_be_appended_to_an_open_room_project(routed):
    _p, _r, proj = open_room(routed)
    s1 = proj["steps"][0]["id"]
    fp = file(routed, assign_followup(proj, s1))
    rule(routed, fp["id"])
    amend = store.apply_followup(routed, fp["id"])
    new = amend["steps"][-1]
    assert new["tool"] == "zone.assign-owner" and new["requires"] == [s1]
    assert new["args"] == {"zone_id": 13, "unit_id": 345}
    assert [s["id"] for s in amend["steps"]][0] == s1  # the whole plan is carried, the room step untouched


def test_a_standalone_one_step_assign_owner_proposal_files_and_opens_a_project(routed):
    p = file(routed, assign())
    r = rule(routed, p["id"])
    proj = store.open_project_from_ruling(routed, r["id"])
    assert [s["tool"] for s in proj["steps"]] == ["zone.assign-owner"]


def test_a_standalone_filing_is_refused_while_a_follow_up_for_the_same_zone_is_live(routed):
    _p, _r, proj = open_room(routed)
    file(routed, assign_followup(proj, proj["steps"][0]["id"]))
    with pytest.raises(store.QueueError, match="already proposed as"):
        file(routed, assign(n=3))


def test_a_follow_up_is_refused_while_a_standalone_filing_for_the_same_zone_is_live(routed):
    _p, _r, proj = open_room(routed)
    first = file(routed, assign())
    with pytest.raises(store.QueueError, match=rf"already proposed as {first['id']}"):
        file(routed, assign_followup(proj, proj["steps"][0]["id"]))


def test_two_projects_cannot_both_assign_the_same_zone(routed):
    _p, _r, proj1 = open_room(routed, 1)
    _p2, _r2, proj2 = open_room(routed, 2)
    file(routed, assign_followup(proj1, proj1["steps"][0]["id"]))
    with pytest.raises(store.QueueError, match="already proposed as"):
        file(routed, assign_followup(proj2, proj2["steps"][0]["id"], n=4))


def test_a_different_zone_is_a_different_action(routed):
    _p, _r, proj = open_room(routed)
    file(routed, assign_followup(proj, proj["steps"][0]["id"], zone_id=13))
    file(routed, assign(zone_id=14, n=5))


def test_a_rejected_filing_does_not_block_a_refile(routed):
    first = file(routed, assign())
    rule(routed, first["id"], "reject")
    file(routed, assign(n=6))


def test_other_tools_follow_ups_are_still_never_duplicates(routed):
    assert not schema.follow_up_checked("blueprint.apply")
    assert schema.follow_up_checked("zone.assign-owner")


def test_open_step_calls_lists_live_assign_owner_work_only(routed):
    assert store.open_step_calls(routed, ["zone.assign-owner"]) == []
    live = file(routed, assign(zone_id=13, unit_id=345))
    dead = file(routed, assign(zone_id=14, unit_id=346, n=7))
    rule(routed, dead["id"], "reject")
    file(routed, assign(zone_id=15, unit_id=347, n=8, step={"tool": "zone.place", "args": {"kind": "Office"}}))
    rows = store.open_step_calls(routed, ["zone.assign-owner"])
    assert [(r["proposal_id"], r["args"]["unit_id"], r["status"]) for r in rows] == [(live["id"], 345, "pending")]
    assert store.open_step_calls(routed, []) == []
