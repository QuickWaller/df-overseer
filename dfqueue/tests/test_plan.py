"""The fort plan: the `fort_plan` record, flags, the season interval, `serves`,
`plan_change` and the shortfall arithmetic
(handoffs/2026-10-07-planner-p1a.md, research/2026-10-07-planner-design.md 2).

The real roster has the planner disabled until stage P1b, so a fixture roster
enables it; `agents/ROSTER.yaml` is never edited by a test.
"""
from __future__ import annotations

import copy

import pytest

from dfqueue import plan, routing, schema, store, templates
from dfqueue.tests._helpers import make_pass, make_proposal, make_ruling

_REAL_ROSTER = schema._load_roster

SEASON = 100800
ZONE_KINDS = {"Bedroom", "DiningHall", "Office", "Tomb", "Barracks", "Dormitory"}
CTX = plan.PlanContext(zone_kinds=ZONE_KINDS, landmarks={"Dining Hall", "Wagon"})

BEDROOMS = {
    "id": "bedrooms", "signal": 'zones."Bedroom".furnished', "per": "alive",
    "want": 1.0, "reorder_gap": 2, "owner": "architect", "max_in_flight": 2,
}
DINING = {
    "id": "dining_seats", "signal": 'zones."DiningHall".furniture."Chair"', "per": "alive",
    "want": 1.0, "reorder": 0.7, "owner": "architect",
}


@pytest.fixture(autouse=True)
def planner_roster(monkeypatch):
    real = _REAL_ROSTER()
    roster = {
        **real,
        "roles": {**real["roles"], "planner": {**real["roles"]["planner"], "enabled": True}},
    }
    monkeypatch.setattr(schema, "_load_roster", lambda: roster)


@pytest.fixture
def db(tmp_path):
    return tmp_path / "queue.sqlite3"


def _plan_record(db, targets, tick, *, reason="Because the fort grew.", ruling_id=None, flags=None, **extra):
    """A fort_plan composed the way `plan.write` composes it: through
    `plan.compose`, `plan.diff_changes` and `plan.check_sections`."""
    active = store.active_plan(db)
    sections = plan.compose(active, {"targets": targets})
    changes = plan.diff_changes(store._plan_base_sections(active), sections)
    record = {
        "kind": "fort_plan", "role": "planner", "cycle": tick, "snapshot": f"tick-{tick}",
        "version": (active["version"] + 1) if active else 1,
        "supersedes": active["id"] if active else None,
        "season_index": plan.season_index(tick), "changes": changes,
        "flags": plan.check_sections(sections, CTX) if flags is None else flags,
        **sections,
    }
    if reason:
        record["reason"] = reason
    if ruling_id:
        record["ruling_id"] = ruling_id
    record.update(extra)
    return record


def _file(db, targets, tick, **kw):
    record = _plan_record(db, targets, tick, **kw)
    return store.append(record, db, game_tick=tick)


def _refused(db, targets, tick, **kw):
    with pytest.raises(store.QueueError) as exc:
        _file(db, targets, tick, **kw)
    return str(exc.value)


# ---- the season ----------------------------------------------------------------


def test_season_index_is_the_tick_over_the_policy_season():
    assert plan.season_index(0) == 0
    assert plan.season_index(SEASON - 1) == 0
    assert plan.season_index(SEASON) == 1
    assert plan.next_season_tick(SEASON + 5) == 2 * SEASON


# ---- writer, shape and coordinates (refusals) -------------------------------------


def test_only_the_planner_may_write_a_fort_plan(db):
    record = _plan_record(db, [BEDROOMS], 100)
    for role in ("architect", "overseer", "conductor"):
        errors = schema.validate({**record, "role": role})
        assert any("only 'planner' may write a fort_plan" in e for e in errors), role


def test_a_coordinate_is_refused_anywhere_in_the_plan(db):
    bad = {**BEDROOMS, "note": "build at x=12 y=4 z=-1"}
    msg = _refused(db, [bad], 100)
    assert "raw-coordinate" in msg
    msg = _refused(db, [BEDROOMS], 100, reason="put it at (4, 9, -2)")
    assert "raw-coordinate" in msg


def test_the_payload_must_be_the_schema_shape(db):
    with pytest.raises(plan.PlanShapeError, match="expected a list"):
        plan.compose(None, {"targets": {"id": "bedrooms"}})
    with pytest.raises(plan.PlanShapeError, match="expected an object"):
        plan.compose(None, {"targets": ["bedrooms"]})
    with pytest.raises(plan.PlanShapeError, match="expected an object mapping"):
        plan.compose(None, ["targets"])
    errors = schema.validate({**_plan_record(db, [BEDROOMS], 100), "targets": ["bedrooms"]})
    assert any("record.targets.0: expected an object" in e for e in errors)


def test_a_section_with_no_home_yet_is_refused_by_name(db):
    with pytest.raises(plan.PlanShapeError, match=r"set\.districts: arrives at stage P2"):
        plan.compose(None, {"districts": []})
    with pytest.raises(plan.PlanShapeError, match="not a plan section"):
        plan.compose(None, {"villages": []})


def test_version_two_needs_a_reason_version_one_does_not(db):
    _file(db, [BEDROOMS], 100, reason=None)
    msg = _refused(db, [BEDROOMS, DINING], SEASON + 5, reason=None)
    assert "record.reason: required field is missing" in msg


# ---- base version, season interval, ruled and fix-only versions ---------------------


def test_version_one_composes_from_the_default_plan(db):
    # The default is the fort roadmap's first stage (plans/default-v1.yaml was retired).
    base = plan.compose(None, {})
    assert [t["id"] for t in base["targets"]] == ["dormitory_beds", "dining_tables"]
    assert all(t["roadmap_ref"] == t["id"] for t in base["targets"])
    rec = _file(db, base["targets"], 100, reason=None)
    assert rec["version"] == 1 and rec["changes"] == []   # an empty diff against the default
    assert rec["season_index"] == 0 and rec["id"] == "fort_plan-0001"


def test_a_stale_base_version_is_refused(db):
    _file(db, [BEDROOMS], 100, reason=None)
    stale = _plan_record(db, [BEDROOMS, DINING], SEASON + 1)
    stale["version"], stale["supersedes"] = 1, None  # a retry composed against base 0
    with pytest.raises(store.QueueError, match="stale base"):
        store.append(stale, db, game_tick=SEASON + 1)


def test_a_second_version_in_one_season_is_refused_naming_the_next_season(db):
    _file(db, [BEDROOMS], 100, reason=None)
    msg = _refused(db, [BEDROOMS, DINING], 5000)
    assert "season 0 already has plan version 1" in msg
    assert f"opens at tick {SEASON}" in msg
    assert "plan_change" in msg


def test_a_new_season_accepts_a_new_version(db):
    _file(db, [BEDROOMS], 100, reason=None)
    rec = _file(db, [BEDROOMS, DINING], SEASON + 1)
    assert rec["version"] == 2 and rec["season_index"] == 1
    assert rec["changes"] == [{"section": "targets", "id": "dining_seats", "op": "added"}]


def test_an_active_version_from_a_later_season_counts_as_elapsed(db):
    # A test-harness reload (docs/ARMOK-RULINGS.md): the tick went backwards.
    _file(db, [BEDROOMS], 3 * SEASON + 10, reason=None)
    rec = _file(db, [BEDROOMS, DINING], SEASON + 10)
    assert rec["version"] == 2 and rec["season_index"] == 1


def test_the_season_index_is_stamped_by_the_server_and_checked(db):
    record = _plan_record(db, [BEDROOMS], 100, reason=None)
    record["season_index"] = 7
    with pytest.raises(store.QueueError, match="record.season_index"):
        store.append(record, db, game_tick=100)


def test_changes_are_server_computed_and_checked(db):
    record = _plan_record(db, [BEDROOMS], 100, reason=None)
    record["changes"] = [{"section": "targets", "id": "x", "op": "added"}]
    with pytest.raises(store.QueueError, match="record.changes: server-computed"):
        store.append(record, db, game_tick=100)


def test_changes_name_added_removed_changed_and_reordered():
    old = {"targets": [BEDROOMS, DINING]}
    changed = {**BEDROOMS, "want": 1.2}
    assert plan.diff_changes(old, {"targets": [changed, DINING]}) == [
        {"section": "targets", "id": "bedrooms", "op": "changed", "fields": ["want"]},
    ]
    assert plan.diff_changes(old, {"targets": [BEDROOMS]}) == [
        {"section": "targets", "id": "dining_seats", "op": "removed"},
    ]
    assert plan.diff_changes(old, {"targets": [DINING, BEDROOMS]}) == [
        {"section": "targets", "id": None, "op": "reordered"},
    ]
    assert plan.diff_changes(old, old) == []


def test_a_version_that_changes_nothing_is_refused(db):
    _file(db, [BEDROOMS], 100, reason=None)
    msg = _refused(db, [BEDROOMS], SEASON + 1)
    assert "nothing changes" in msg


def test_removing_every_target_in_a_new_season_needs_no_ruling(db):
    # Guardrail 2 (a built room's binding) is vacuous in P1: a plan holds
    # targets only, which bind nothing built, so no target change is ever a
    # binding change and the only gate is the season.
    _file(db, [BEDROOMS, DINING], 100, reason=None)
    rec = _file(db, [], SEASON + 1)
    assert rec["targets"] == [] and "ruling_id" not in rec
    assert {c["op"] for c in rec["changes"]} == {"removed"}


def test_a_fix_only_version_is_exempt_from_the_interval(db):
    typo = {**BEDROOMS, "signal": 'zones."Bedrom".furnished'}
    first = _file(db, [typo, DINING], 100, reason=None)
    assert any(f["code"] == "unknown_kind" and f["id"] == "bedrooms" for f in first["flags"])
    fixed = _file(db, [BEDROOMS, DINING], 200)            # same season, only the flagged entry
    assert fixed["version"] == 2 and fixed["flags"] == []


def test_fixing_one_flagged_entry_and_touching_an_unflagged_one_is_not_exempt(db):
    typo = {**BEDROOMS, "signal": 'zones."Bedrom".furnished'}
    _file(db, [typo, DINING], 100, reason=None)
    msg = _refused(db, [BEDROOMS, {**DINING, "want": 2.0}], 200)
    assert "already has plan version 1" in msg


def test_adding_an_entry_beside_a_fix_is_not_exempt(db):
    typo = {**BEDROOMS, "signal": 'zones."Bedrom".furnished'}
    _file(db, [typo], 100, reason=None)
    msg = _refused(db, [BEDROOMS, DINING], 200)
    assert "already has plan version 1" in msg


def test_fix_only_helper_needs_every_change_to_be_a_flagged_entry():
    flags = [{"section": "targets", "id": "a", "code": "bad_signal", "inert": True}]
    ch = lambda op, i="a": {"section": "targets", "id": i, "op": op}  # noqa: E731
    assert plan.fix_only([ch("changed")], flags)
    assert plan.fix_only([ch("removed")], flags)
    assert not plan.fix_only([ch("added")], flags)
    assert not plan.fix_only([ch("changed", "b")], flags)
    assert not plan.fix_only([{"section": "targets", "id": None, "op": "reordered"}], flags)
    assert not plan.fix_only([], flags)
    info = [{"section": "plan", "id": None, "code": "kinds_unchecked", "inert": False}]
    assert not plan.fix_only([ch("changed")], info)


# ---- accept and flag ------------------------------------------------------------------


def _codes(flags, eid=None):
    return {f["code"] for f in flags if eid is None or f.get("id") == eid}


def test_a_kind_typo_is_accepted_flagged_with_the_nearest_token_and_inert(db):
    typo = {**BEDROOMS, "signal": 'zones."Bedrom".furnished'}
    rec = _file(db, [typo], 100, reason=None)           # stored, not refused
    assert rec["targets"][0]["signal"] == 'zones."Bedrom".furnished'
    flag = next(f for f in rec["flags"] if f["code"] == "unknown_kind")
    assert flag["nearest"] == "Bedroom" and "Bedroom" in flag["message"] and flag["inert"] is True
    assert ("targets", "bedrooms") in plan.inert_keys(rec["flags"])


def test_an_unknown_landmark_is_flagged():
    t = {**BEDROOMS, "signal": 'landmark."Dinning Hall".exists'}
    flags = plan.check_sections({"targets": [t]}, CTX)
    f = next(f for f in flags if f["code"] == "unknown_landmark")
    assert f["nearest"] == "Dining Hall"
    ok = plan.check_sections({"targets": [{**t, "signal": 'landmark."Dining Hall".exit."Wagon".distance_tiles'}]}, CTX)
    assert "unknown_landmark" not in _codes(ok)


def test_a_malformed_or_non_numeric_signal_is_flagged():
    flags = plan.check_sections({"targets": [{**BEDROOMS, "signal": "zones.Bedroom"}]}, CTX)
    assert "bad_signal" in _codes(flags)
    flags = plan.check_sections({"targets": [{**BEDROOMS, "signal": 'landmark."Wagon".exists'}]}, CTX)
    assert "bad_signal_type" in _codes(flags)


def test_thresholds_are_checked_and_exactly_one_reorder_rule_is_needed():
    both = {**BEDROOMS, "reorder": 0.5}
    neither = {k: v for k, v in BEDROOMS.items() if k != "reorder_gap"}
    for t in (both, neither, {**BEDROOMS, "want": 0}, {**BEDROOMS, "reorder_gap": -1}, {**DINING, "reorder": 5}):
        assert "bad_threshold" in _codes(plan.check_sections({"targets": [t]}, CTX)), t


def test_owner_must_propose_and_be_able_to_serve_the_signal_family():
    flags = plan.check_sections({"targets": [{**BEDROOMS, "owner": "overseer"}]}, CTX)
    assert "owner_unknown" in _codes(flags)
    flags = plan.check_sections({"targets": [{**BEDROOMS, "owner": "quartermaster"}]}, CTX)
    assert "owner_cannot_serve" in _codes(flags)
    flags = plan.check_sections({"targets": [BEDROOMS]}, CTX)
    assert _codes(flags) == set()


def test_unknown_fields_duplicate_ids_and_long_text_are_flagged():
    flags = plan.check_sections({"targets": [
        {**BEDROOMS, "colour": "red"}, {**BEDROOMS}, {**DINING, "note": "x" * 161},
    ]}, CTX)
    assert {"unknown_field", "duplicate_id", "text_too_long"} <= _codes(flags)


def test_an_oversized_section_is_flagged_inert_never_refused_or_dropped(db):
    many = [{**BEDROOMS, "id": f"t{i}"} for i in range(19)]
    rec = _file(db, many, 100, reason=None)
    assert len(rec["targets"]) == 19
    over = [f for f in rec["flags"] if f["code"] == "over_cap"]
    assert [f["id"] for f in over] == ["t16", "t17", "t18"]


def test_unreadable_zone_kinds_leave_one_info_flag_not_an_inert_entry():
    flags = plan.check_sections({"targets": [BEDROOMS]}, plan.PlanContext(zone_kinds=None))
    assert _codes(flags) == {"kinds_unchecked"}
    assert plan.inert_keys(flags) == set()


def test_plan_level_text_is_flagged_when_too_long_or_a_bad_signal_is_cited():
    flags = plan.check_text_fields("r" * 200, "p" * 400, [{"signal": "nope"}, {"tool": "x"}], CTX)
    assert {"text_too_long", "bad_signal", "bad_field"} <= _codes(flags)
    assert plan.check_text_fields("ok", "ok", [{"signal": "fort.population"}], CTX) == []
    assert "over_cap" in _codes(plan.check_text_fields("ok", "ok", [{"signal": "fort.population"}] * 7, CTX))


# ---- plan_change: ruling-only, rate-limited, closed by the citing version -------------


def _plan_change(db, tick, **kw):
    return store.append(make_proposal(
        role="planner", type="plan_change", cycle=tick,
        summary=kw.pop("summary", "Raise the dining seat target after the migrant wave."),
        **kw,
    ), db, game_tick=tick)


def _accept(db, proposal_id, tick=1):
    return store.append(make_ruling(proposal_id, cycle=tick), db)


def test_plan_change_is_a_ruling_only_type_of_the_planner():
    assert schema.TYPE_VOCAB_BY_ROLE["planner"] == ("plan_change",)
    assert routing.is_ruling_only("plan_change") and not routing.is_routed("plan_change")
    assert "plan_change" not in routing.unrouted_types()
    assert routing.ruling_only_types() == ["plan_change"]


def test_an_accepted_plan_change_is_not_unexecuted_but_awaits_the_planner(db):
    _file(db, [BEDROOMS], 100, reason=None)
    pc = _plan_change(db, 500)
    ruling = _accept(db, pc["id"])
    assert store.unexecuted_accepted_proposals(db) == []
    awaiting = store.plan_changes_awaiting(db)
    assert [(a["proposal"]["id"], a["ruling_id"]) for a in awaiting] == [(pc["id"], ruling["id"])]


def test_a_version_citing_the_ruling_is_mid_season_exempt_and_closes_it(db):
    _file(db, [BEDROOMS], 100, reason=None)
    pc = _plan_change(db, 500)
    ruling = _accept(db, pc["id"])
    rec = _file(db, [BEDROOMS, DINING], 900, ruling_id=ruling["id"])    # same season 0
    assert rec["version"] == 2 and rec["ruling_id"] == ruling["id"]
    closes = [r for r in store.load(db) if r["kind"] == "close" and r.get("ruling_id") == ruling["id"]]
    assert len(closes) == 1 and closes[0]["outcome"] == "completed"
    assert store.plan_changes_awaiting(db) == []
    # one ruling authorises one version
    msg = _refused(db, [BEDROOMS, DINING, {**DINING, "id": "more"}], 950, ruling_id=ruling["id"])
    assert "already authorised" in msg


def test_a_ruling_that_is_not_an_accepted_plan_change_does_not_authorise(db):
    _file(db, [BEDROOMS], 100, reason=None)
    pc = _plan_change(db, 500)
    rejected = store.append(make_ruling(pc["id"], decision="reject"), db)
    msg = _refused(db, [BEDROOMS, DINING], 900, ruling_id=rejected["id"])
    assert "not an accepting ruling" in msg
    msg = _refused(db, [BEDROOMS, DINING], 900, ruling_id="ruling-0099")
    assert "does not refer to an existing ruling" in msg
    other = store.append(make_proposal(), db, game_tick=10)
    other_ruling = store.append(make_ruling(other["id"]), db)
    msg = _refused(db, [BEDROOMS, DINING], 900, ruling_id=other_ruling["id"])
    assert "not a ruling on a plan_change" in msg
    # and the interval still applies when the citation is bad
    assert "already has plan version 1" in msg


def test_plan_change_requests_are_rate_limited_by_cooldown_and_season_cap(db):
    _file(db, [BEDROOMS], 100, reason=None)
    _plan_change(db, 1000)
    with pytest.raises(store.QueueError, match="cooldown is 12000 ticks"):
        _plan_change(db, 5000, summary="Lower the bedroom reorder gap for the winter.")
    _plan_change(db, 13000, summary="Lower the bedroom reorder gap for the winter.")
    with pytest.raises(store.QueueError, match="already has 2 plan_change requests"):
        _plan_change(db, 30000, summary="Drop dining seats entirely until the hall exists.")
    # the next season is a fresh cap, and a tick that went backwards (a reload) is elapsed
    _plan_change(db, SEASON + 50000, summary="A different request in the second season entirely.")


def test_a_rejected_plan_change_still_counts_against_the_limit(db):
    _file(db, [BEDROOMS], 100, reason=None)
    pc = _plan_change(db, 1000)
    store.append(make_ruling(pc["id"], decision="reject"), db)
    with pytest.raises(store.QueueError, match="cooldown"):
        _plan_change(db, 2000, summary="Ask again straight after the rejection happened.")


def test_a_planner_pass_records_the_review_tick_beside_the_plan(db):
    assert store.plan_last_reviewed_tick(db) is None
    _file(db, [BEDROOMS], 100, reason=None)
    assert store.plan_last_reviewed_tick(db) == 100
    store.append(make_pass(role="planner", cycle=777), db)
    store.mark_plan_reviewed(db, 777)
    assert store.plan_last_reviewed_tick(db) == 777


# ---- serves -----------------------------------------------------------------------------


def _serving(db, role, ptype, serves, summary, **kw):
    return store.append(make_proposal(role=role, type=ptype, serves=serves, summary=summary, **kw), db, game_tick=10)


def test_serves_needs_an_active_plan_and_a_real_target(db):
    with pytest.raises(store.QueueError, match="no active plan yet"):
        _serving(db, "architect", "stockpile_siting", ["bedrooms"], "Site a bedroom block near the hall.")
    _file(db, [BEDROOMS], 100, reason=None)
    with pytest.raises(store.QueueError, match="'beds' is not a target of plan version 1"):
        _serving(db, "architect", "stockpile_siting", ["beds"], "Site a bedroom block near the hall.")


def test_serves_accepts_the_target_owner_and_the_input_owner_and_refuses_others(db):
    _file(db, [BEDROOMS], 100, reason=None)
    ok = _serving(db, "architect", "stockpile_siting", ["bedrooms"], "Site a bedroom block near the hall.")
    assert ok["serves"] == ["bedrooms"]
    # the bed is the Quartermaster's: derived from the bedroom template's `requires`
    qm = _serving(db, "quartermaster", "work_order", ["bedrooms"], "Keep a small buffer of beds in stock.")
    assert qm["serves"] == ["bedrooms"]
    with pytest.raises(store.QueueError, match="may not serve 'bedrooms'"):
        _serving(db, "planner", "plan_change", ["bedrooms"], "The planner may not serve its own target.")


def test_serves_is_checked_for_shape():
    errors = schema.validate(make_proposal(serves=[]))
    assert any("record.serves: expected a non-empty list" in e for e in errors)
    errors = schema.validate(make_proposal(serves=["a", "a"]))
    assert any("may be listed once" in e for e in errors)
    errors = schema.validate(make_proposal(serves=["a", "b", "c", "d", "e"]))
    assert any("at most 4" in e for e in errors)


def test_parallel_proposals_serving_one_target_are_not_flagged_as_duplicates(db):
    _file(db, [BEDROOMS], 100, reason=None)
    same = "Site a bedroom block beside the dining hall."
    a = _serving(db, "architect", "stockpile_siting", ["bedrooms"], same)
    b = _serving(db, "architect", "stockpile_siting", ["bedrooms"], same)
    assert "duplicate_of" not in a and "duplicate_of" not in b
    c = store.append(make_proposal(role="architect", type="stockpile_siting", summary=same), db, game_tick=10)
    assert c["duplicate_of"] == a["id"]            # without `serves` the check still runs


# ---- in-flight work -----------------------------------------------------------------------


def test_serving_work_counts_pending_and_accepted_not_rejected_or_closed(db):
    _file(db, [BEDROOMS], 100, reason=None)
    pending = _serving(db, "architect", "stockpile_siting", ["bedrooms"], "Site a bedroom block near the hall.")
    rejected = _serving(db, "architect", "stockpile_siting", ["bedrooms"], "Site another block beside the well.")
    accepted = _serving(db, "architect", "stockpile_siting", ["bedrooms"], "Site a third block under the stair.")
    store.append(make_ruling(rejected["id"], decision="reject"), db)
    ruling = store.append(make_ruling(accepted["id"]), db)
    work = store.serving_work(db)["bedrooms"]
    assert {(w["proposal_id"], w["state"]) for w in work} == {(pending["id"], "pending"), (accepted["id"], "accepted")}
    store.close(db, target_id=ruling["id"], outcome="completed", reason="finished and counted on hand")
    assert [w["proposal_id"] for w in store.serving_work(db)["bedrooms"]] == [pending["id"]]


# ---- the arithmetic ---------------------------------------------------------------------


def _pos(target, on_hand, in_flight=0, alive=10):
    return plan.target_position(target, on_hand, in_flight, alive)


def test_reorder_gap_opens_exactly_at_the_gap_and_quiet_inside_the_band():
    # want 1.0 per alive, 10 alive: 10 wanted, gap 2
    assert _pos(BEDROOMS, 8)["state"] == "open"      # exactly 2 short
    assert _pos(BEDROOMS, 9)["state"] == "quiet"     # 1 short: inside the band
    assert _pos(BEDROOMS, 9)["below_want"] is True
    assert _pos(BEDROOMS, 10)["below_want"] is False


def test_a_one_unit_gap_is_never_hidden_by_rounding():
    tight = {**BEDROOMS, "reorder_gap": 1}
    assert _pos(tight, 9)["state"] == "open"
    assert _pos({**tight, "want": 0.95}, 9, alive=10)["state"] == "quiet"   # 9.5 wanted, 0.5 short
    assert _pos({**tight, "want": 0.95}, 8, alive=10)["state"] == "open"    # 1.5 short


def test_a_ratio_reorder_opens_below_the_level_per_citizen():
    assert _pos(DINING, 6)["state"] == "open"        # 6 < 0.7 * 10
    assert _pos(DINING, 7)["state"] == "quiet"       # 7 is not below 7
    assert _pos(DINING, 6, in_flight=1)["state"] == "quiet"


def test_in_flight_work_counts_toward_the_position():
    pos = _pos(BEDROOMS, 6, in_flight=2)
    assert pos["position"] == 8 and pos["state"] == "open"
    assert _pos(BEDROOMS, 6, in_flight=3)["state"] == "quiet"


def test_an_unreadable_signal_or_alive_count_is_unresolved_never_a_shortfall():
    assert _pos(BEDROOMS, None)["state"] == "unresolved"
    assert plan.target_position(BEDROOMS, 3, 0, None)["state"] == "unresolved"
    assert plan.target_position(BEDROOMS, 3, 0, 0)["state"] == "unresolved"
    flat = {"id": "w", "signal": "fort.population", "want": 5, "reorder_gap": 1, "owner": "architect"}
    assert plan.target_position(flat, 2, 0, None)["state"] == "open"        # not per alive: no alive needed


def test_a_zero_reads_as_zero_not_unresolved():
    pos = _pos(BEDROOMS, 0)
    assert pos["state"] == "open" and pos["short_units"] == 10


# ---- templates and derived inputs ----------------------------------------------------------


def test_the_bedroom_template_provides_one_furnished_bedroom_and_requires_a_bed():
    tpl = templates.serving('zones."Bedroom".furnished')
    assert tpl["id"] == "bedroom-cell" and tpl["units"] == 1 and tpl["requires"] == ["bed"]
    assert templates.serving('zones."Nonsense".furnished') is None


def test_the_highest_revision_serves_a_signal(tmp_path):
    for rev in (1, 3, 2):
        (tmp_path / f"office-v{rev}.yaml").write_text(
            f"id: office\nrevision: {rev}\nprovides:\n  - signal: 'zones.\"Office\".furnished'\n    units: {rev}\nrequires: [chair]\n",
            encoding="utf-8",
        )
    assert templates.serving('zones."Office".furnished', tmp_path)["units"] == 3
    (tmp_path / "junk.yaml").write_text("- not a mapping", encoding="utf-8")
    (tmp_path / "bad.yaml").write_text("id: x\nprovides:\n  - signal: 5\n  - {signal: s, units: -1}\n", encoding="utf-8")
    assert templates.serving("s", tmp_path) is None


def test_derived_inputs_come_from_the_template_and_go_to_the_item_owner():
    inputs = plan.derived_inputs(["bed"], 2.0, {"bed": 0})
    assert inputs == [{"item": "bed", "needed": 2.0, "available": 0, "owner": "quartermaster", "short": 2.0}]
    assert plan.derived_inputs(["bed"], 2.0, {"bed": None})[0]["short"] is None
    assert plan.derived_inputs(["bed"], 2.0, {"bed": 5})[0]["short"] == 0.0
    assert plan.item_type("bed") == "BED" and plan.item_type("chair") == "CHAIR"
    assert plan.input_owner_roles(BEDROOMS) == {"quartermaster"}
    assert plan.input_owner_roles(DINING) == set()      # no template provides a dining chair yet


def test_role_slices_show_a_role_only_its_lane():
    targets = [BEDROOMS, {**DINING, "owner": "architect"}, {
        "id": "drink", "signal": 'stocks.availability."DRINK".available_units', "want": 30,
        "reorder_gap": 5, "owner": "quartermaster",
    }]
    ids = lambda role: [t["id"] for t in plan.slice_for_role(targets, role)]  # noqa: E731
    assert ids("planner") == ids("overseer") == ids("conductor") == ["bedrooms", "dining_seats", "drink"]
    assert ids("architect") == ["bedrooms", "dining_seats"]
    assert ids("quartermaster") == ["bedrooms", "drink"]    # owns the bedroom's derived bed
    assert ids("consultant") == []


def test_a_fort_plan_in_the_queue_renders_in_the_feed_xml_and_public_view_without_leaking(db):
    """Found by an executor smoke test: before `fort_plan` was a known kind the
    stream feed raised on the first plan record, which would have stopped the
    publisher the moment the Planner filed version 1."""
    from dfqueue import feed, render
    rec = _file(db, [BEDROOMS, DINING], 100, reason=None, public_rationale="We plan a bed for everyone.")
    records = store.load(db)
    public = feed.build_items(records, public=True)
    operator = feed.build_items(records, public=False)
    assert public[0]["text"] == "Plan version 1. We plan a bed for everyone."
    assert public[0]["speaker"] == "Planner" and "targets" not in public[0]
    assert operator[0]["record"]["targets"][0]["id"] == "bedrooms"
    xml = render.to_xml(rec)
    assert xml.startswith("<fort_plan ") and "<version>1</version>" in xml and "bedrooms" in xml
    assert set(render.public_view(rec)) <= set(render.ALLOWED_PUBLIC_FIELDS)
    assert "targets" not in render.public_view(rec)
    # no rationale: a fixed line, never the reason or the changes
    nxt = _file(db, [BEDROOMS], SEASON + 1, reason="Dining waits, internal reasoning.")
    text = feed.build_items(store.load(db), public=True)[1]["text"]
    assert text == "Plan version 2 filed." and "internal" not in text
    assert nxt["version"] == 2


def test_the_default_plan_and_policy_pass_their_own_checks():
    base = plan.default_plan()
    assert plan.check_sections(base, CTX) == []
    pol = copy.deepcopy(plan.policy())
    assert set(pol["open_sections"]) <= set(pol["sections"]) and pol["season_ticks"] == SEASON


# ---- the mapping form of `want` -----------------------------------------------------------

MAPPED = {
    "id": "bedrooms", "signal": 'zones."Bedroom".furnished',
    "want": {"per_alive": 1.0, "plus": 3, "min": 10, "max": 60}, "reorder_gap": 2, "owner": "architect",
}


def _bad(target):
    return [f for f in plan.check_sections({"targets": [target]}, CTX) if f["code"] not in plan.INFO_CODES]


def test_a_sound_mapping_want_raises_no_flag():
    assert _bad(MAPPED) == []
    assert _bad({**MAPPED, "want": {"plus": 5}}) == []
    assert _bad({**MAPPED, "want": {"per_alive": 0.5}}) == []
    assert _bad({**MAPPED, "want": {"per_alive": 1, "plus": -2, "min": 4}}) == []   # only plus may be negative


def test_a_mapping_want_is_not_a_bad_threshold_where_the_old_code_flagged_it():
    # The old check flagged any non-number want as bad_threshold.
    assert "bad_threshold" not in _codes(plan.check_sections({"targets": [MAPPED]}, CTX))


@pytest.mark.parametrize("want", [
    {},                                         # neither per_alive nor plus
    {"min": 5, "max": 9},                       # neither per_alive nor plus
    {"per_alive": 1.0, "min": 9, "max": 5},     # min above max
    {"per_alive": -1.0},                        # negative
    {"plus": 1, "min": -1},                     # negative min
    {"plus": 1, "max": -1},                     # negative max
    {"per_alive": float("inf")},                # not finite
    {"plus": float("nan")},
    {"per_alive": "1"},                         # not a number
    {"per_alive": True},                        # bool is not a number
    {"plus": 1, "bonus": 2},                    # unknown key
])
def test_bad_mapping_wants_are_flagged_with_repair_text_and_go_inert(want):
    flags = _bad({**MAPPED, "want": want})
    th = [f for f in flags if f["code"] == "bad_threshold"]
    assert th and all(f["id"] == "bedrooms" for f in th)
    assert all("want:" in f["message"] for f in th)
    assert ("targets", "bedrooms") in plan.inert_keys(flags)


def test_per_with_a_mapping_want_is_flagged():
    flags = _bad({**MAPPED, "per": "alive"})
    assert any(f["code"] == "bad_field" and "per" in f["message"] for f in flags)


def test_a_scalar_want_that_is_not_finite_is_flagged():
    assert "bad_threshold" in _codes(plan.check_sections({"targets": [{**BEDROOMS, "want": float("inf")}]}, CTX))


def test_a_mapping_reorder_above_max_is_flagged_and_the_text_says_absolute():
    t = {k: v for k, v in MAPPED.items() if k != "reorder_gap"}
    t["reorder"] = 99
    flags = _bad(t)
    assert any(f["code"] == "bad_threshold" and "absolute" in f["message"] for f in flags)
    t["reorder"] = 40
    assert _bad(t) == []


def test_mapping_want_computes_the_clamped_level():
    for alive, level in ((2, 10), (10, 13), (30, 33), (100, 60)):
        pos = plan.target_position(MAPPED, 0, 0, alive)
        assert pos["want_units"] == level, (alive, pos)


def test_mapping_reorder_gap_compares_against_the_computed_level_in_units():
    # 10 alive: level 13, gap 2 opens at position 11
    assert plan.target_position(MAPPED, 11, 0, 10)["state"] == "open"
    assert plan.target_position(MAPPED, 12, 0, 10)["state"] == "quiet"
    assert plan.target_position(MAPPED, 12, 0, 10)["below_want"] is True
    assert plan.target_position(MAPPED, 13, 0, 10)["below_want"] is False


def test_mapping_reorder_is_an_absolute_level_not_scaled_by_alive():
    t = {k: v for k, v in MAPPED.items() if k != "reorder_gap"}
    t["reorder"] = 12
    assert plan.target_position(t, 11, 0, 10)["state"] == "open"
    assert plan.target_position(t, 12, 0, 10)["state"] == "quiet"
    assert plan.target_position(t, 11, 0, 30)["state"] == "open"   # still 12, not 12 * 30


def test_a_plus_only_want_needs_no_alive_count_but_per_alive_does():
    flat = {**MAPPED, "want": {"plus": 5}}
    assert plan.target_position(flat, 1, 0, None)["state"] == "open"
    assert plan.target_position(flat, 1, 0, None)["want_units"] == 5
    assert plan.target_position(MAPPED, 1, 0, None)["state"] == "unresolved"
    assert plan.want_uses_alive(MAPPED) and not plan.want_uses_alive(flat)


def test_the_scalar_forms_are_unchanged():
    assert plan.target_position(BEDROOMS, 8, 0, 10)["want_units"] == 10
    assert plan.want_uses_alive(BEDROOMS)
    assert plan.target_position({"id": "w", "signal": "x", "want": 5, "reorder_gap": 1}, 2, 0, None)["want_units"] == 5
