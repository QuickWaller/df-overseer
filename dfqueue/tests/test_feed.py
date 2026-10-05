"""`dfqueue.feed`: the stream page's public and operator projections.

The allowlist test matters most, same reason `test_render.py`'s does: this
is a second, distinct allowlist (a rendered chat *item*, not a raw record
view), and it must hold even as new fields get added to records the schema
does not gate yet. `test_find_unsafe_pattern_*` proves the withhold net
design §7.2 asks for actually catches the four named shapes (URL, address,
path, token) before any of that text could reach a public file.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from dfqueue import feed
from dfqueue.tests._helpers import (
    make_abandon, make_amend, make_answer, make_ask, make_escalation,
    make_executed, make_observation, make_pass, make_project, make_proposal,
    make_ruling,
)


# ---- game date --------------------------------------------------------------


def test_render_game_date_none_for_none_tick():
    assert feed.render_game_date(None) is None


def test_render_game_date_first_day_of_year_zero():
    assert feed.render_game_date(0) == "1 Granite, year 0"


def test_render_game_date_rolls_into_the_second_month():
    # 28 days (0-indexed day 28) is the first day of the second month.
    assert feed.render_game_date(28 * feed.TICKS_PER_DAY) == "1 Slate, year 0"


def test_render_game_date_stays_deterministic_for_a_real_cycle_value():
    # From the real exported record (evals/live/2026-09-15-overseer-first-ruling)
    result = feed.render_game_date(12274877)
    assert isinstance(result, str)
    assert "year" in result


def test_render_game_date_year_matches_the_forts_own_clock():
    # Real pair read live: cur_year 31, cur_year_tick 246921, abs_tick
    # 12,746,121 = 31 * 403,200 + 246,921. The feed once headed this
    # "year 32" (a +1 offset); the game's own year is 31.
    assert 31 * feed.TICKS_PER_YEAR + 246921 == 12746121
    # day 205 of the year = 7 full months (196 days) + day 10 -> 10 Sandstone
    assert feed.render_game_date(12746121) == "10 Sandstone, year 31"


# ---- reply_to / thread -------------------------------------------------------


def test_compute_reply_to_ruling_points_at_its_proposal():
    ruling = make_ruling(id="ruling-0001", proposal_id="proposal-0007")
    assert feed.compute_reply_to(ruling) == "proposal-0007"


def test_compute_reply_to_proposal_pass_ask_escalation_have_no_derivable_link():
    proposal = make_proposal(id="proposal-0001")
    passed = make_pass(id="pass-0001")
    ask = make_ask(id="ask-0001")
    escalation = make_escalation(id="escalation-0001")
    assert feed.compute_reply_to(proposal) is None
    assert feed.compute_reply_to(passed) is None
    assert feed.compute_reply_to(ask) is None  # no proposal_id given
    assert feed.compute_reply_to(escalation) is None


def test_compute_reply_to_ask_with_proposal_id_is_a_fact_check():
    ask = make_ask(id="ask-0002", proposal_id="proposal-0003")
    assert feed.compute_reply_to(ask) == "proposal-0003"


def test_compute_thread_follows_the_whole_chain_to_the_root_proposal():
    records = [
        make_proposal(id="proposal-0001"),
        make_ruling(id="ruling-0001", proposal_id="proposal-0001"),
        make_project(id="project-0001", from_ruling="ruling-0001"),
        make_executed(id="executed-0001", ruling_id="ruling-0001"),
        make_amend(id="amend-0001", project_id="project-0001"),
        make_abandon(id="abandon-0001", project_id="project-0001"),
    ]
    reply_to_by_id = {r["id"]: feed.compute_reply_to(r) for r in records}
    for rid in ("ruling-0001", "project-0001", "executed-0001", "amend-0001", "abandon-0001"):
        assert feed.compute_thread(rid, reply_to_by_id) == "proposal-0001"
    assert feed.compute_thread("proposal-0001", reply_to_by_id) == "proposal-0001"


def test_compute_thread_is_safe_against_a_cycle():
    reply_to_by_id = {"a": "b", "b": "a"}
    # Must terminate, not hang; exact winner is unspecified for a
    # (should-never-happen) cycle.
    assert feed.compute_thread("a", reply_to_by_id) in ("a", "b")


# ---- proposal badges ----------------------------------------------------------


def test_build_proposal_badges_pending_with_no_ruling():
    records = [make_proposal(id="proposal-0001")]
    assert feed.build_proposal_badges(records) == {}


def test_build_proposal_badges_reflects_the_latest_ruling():
    records = [
        make_proposal(id="proposal-0001"),
        make_ruling(id="ruling-0001", proposal_id="proposal-0001", decision="defer"),
        make_ruling(id="ruling-0002", proposal_id="proposal-0001", decision="accept"),
    ]
    assert feed.build_proposal_badges(records) == {"proposal-0001": "accepted"}


# ---- the unsafe-text withhold net (design §7.2) -----------------------------


@pytest.mark.parametrize("text", [
    "See https://example.com/status for details",
    # RFC 5737 TEST-NET-1 documentation address, not a real host -- chosen
    # deliberately so this fixture itself never trips
    # tests/test_no_leaked_addresses.py's private-IPv4 scan.
    "Reachable at 192.0.2.42 on the LAN",
    "The config lives at /etc/df-overseer/secrets.yaml",
    "Windows path C:\\Users\\someone\\secrets\\file.txt has it",
    "Contact admin@example.com for access",
    "The token is aGVsbG93b3JsZHRoaXNpc2FsbG9uZw123456",
    "It links <script>alert(1)</script> in the page",
    "A fenced dump:\n```\n{\"x\": 1}\n```",
    "Inline code still checked: `/etc/df-overseer/secrets.yaml`",
    "Quoted path: '/var/lib/dfmcp/x.sqlite3' leaks",
    "Inline code with an address: `192.0.2.42`",
    "A [link](https://example.com) in Markdown",
])
def test_find_unsafe_pattern_catches_leaky_shapes(text):
    assert feed.find_unsafe_pattern(text) is not None


@pytest.mark.parametrize("text", [
    "The fort is still entirely on the surface with no workshops.",
    "Siting the first workshop there raises the landmark count above four.",
    "5 tiles SE of Embark Site, in a 3x3 clearing.",
    # Live 2026-10-05: inline code spans withheld most of the Overseer's report.
    "Order #2 reads `validated=true, active=false`, the stuck pattern.",
    "Accept: drink is at 0, so `drink > 0` is the bar to clear.",
    None,
    "",
])
def test_find_unsafe_pattern_leaves_ordinary_prose_alone(text):
    assert feed.find_unsafe_pattern(text) is None


def test_build_public_item_withholds_text_matching_an_unsafe_pattern():
    record = make_ruling(
        id="ruling-0001", proposal_id="proposal-0001",
        public_rationale="See https://example.com/leak for the full report",
    )
    item = feed.build_public_item(
        record, seq=1, reply_to="proposal-0001", thread="proposal-0001",
        badge=None, ctx={},
    )
    assert item["text"] is None
    assert item["withheld"] is True
    assert item["withheld_reason"] == "url"
    # The withheld reason names a CATEGORY, never the leaked text itself.
    assert "example.com" not in json.dumps(item)


# ---- the public item allowlist ----------------------------------------------


ALL_MAKERS = {
    "proposal": lambda: make_proposal(id="proposal-0001"),
    "pass": lambda: make_pass(id="pass-0001"),
    "ruling": lambda: make_ruling(id="ruling-0001", proposal_id="proposal-0001"),
    "executed": lambda: make_executed(id="executed-0001", ruling_id="ruling-0001"),
    "ask": lambda: make_ask(id="ask-0001"),
    "answer": lambda: make_answer(id="answer-0001", ask_id="ask-0001"),
    "escalation": lambda: make_escalation(id="escalation-0001"),
    "project": lambda: make_project(id="project-0001", from_ruling="ruling-0001"),
    "observation": lambda: make_observation(id="observation-0001"),
    "amend": lambda: make_amend(id="amend-0001", project_id="project-0001"),
    "abandon": lambda: make_abandon(id="abandon-0001", project_id="project-0001"),
}


@pytest.mark.parametrize("kind, maker", list(ALL_MAKERS.items()))
def test_public_item_never_carries_a_field_outside_the_allowlist(kind, maker):
    record = maker()
    item = feed.build_public_item(
        record, seq=1, reply_to=None, thread=record["id"], badge=None, ctx={},
    )
    if item is None:
        assert kind == "observation"
        return
    assert set(item) <= feed.PUBLIC_ITEM_FIELDS


def test_public_item_never_carries_the_raw_record_or_its_private_fields():
    record = make_proposal(
        id="proposal-0001",
        rationale="This full technical rationale must never be public.",
    )
    item = feed.build_public_item(
        record, seq=1, reply_to=None, thread="proposal-0001", badge=None, ctx={},
    )
    dumped = json.dumps(item)
    assert "rationale" not in item
    assert "This full technical rationale" not in dumped
    assert "prediction" not in item
    assert "preconditions" not in item


def test_observation_never_produces_a_public_item():
    record = make_observation(id="observation-0001")
    item = feed.build_public_item(
        record, seq=1, reply_to="project-0001", thread="project-0001",
        badge=None, ctx={},
    )
    assert item is None


def test_project_amend_abandon_with_no_public_rationale_carry_no_public_text():
    # design §3.3 item 6's `public_rationale` is read when the Overseer
    # wrote one (see test_project_amend_abandon_public_rationale_becomes_
    # the_chat_text below); these fixtures do not set it, so the chat
    # item's own text stays None -- never a fallback to the private
    # summary/because/reason fields (those stay operator-only, and a
    # truncated `summary` is only ever used as projects.json's display
    # NAME, never as this chat line's body text).
    for record in (
        make_project(id="project-0001", from_ruling="ruling-0001", summary="private plan summary"),
        make_amend(id="amend-0001", project_id="project-0001", reason="private amend reason"),
        make_abandon(id="abandon-0001", project_id="project-0001", reason="private abandon reason"),
    ):
        item = feed.build_public_item(
            record, seq=1, reply_to=None, thread=record["id"], badge=None, ctx={},
        )
        assert item["text"] is None
        dumped = json.dumps(item)
        assert "private" not in dumped


def test_project_amend_abandon_public_rationale_becomes_the_chat_text():
    for record in (
        make_project(id="project-0001", from_ruling="ruling-0001", public_rationale="A new project."),
        make_amend(id="amend-0001", project_id="project-0001", public_rationale="The plan changed."),
        make_abandon(id="abandon-0001", project_id="project-0001", public_rationale="Giving up on this one."),
    ):
        item = feed.build_public_item(
            record, seq=1, reply_to=None, thread=record["id"], badge=None, ctx={},
        )
        assert item["text"] == record["public_rationale"]


def test_build_public_item_refuses_an_unrecognised_kind():
    with pytest.raises(ValueError):
        feed.build_public_item(
            {"kind": "wake", "id": "wake-0001", "role": "conductor"},
            seq=1, reply_to=None, thread="wake-0001", badge=None, ctx={},
        )


# ---- generated text for the always-generated kinds --------------------------


def test_executed_public_text_never_names_the_tool_or_arguments():
    record = make_executed(id="executed-0001", ruling_id="ruling-0001")
    item = feed.build_public_item(
        record, seq=1, reply_to="ruling-0001", thread="ruling-0001", badge=None, ctx={},
    )
    assert "workshop.build" not in item["text"]


# ---- build_items -------------------------------------------------------------


def test_build_items_public_skips_observations_and_keeps_order():
    records = [
        make_proposal(id="proposal-0001", ts="2026-09-14T00:00:00+00:00"),
        make_ruling(id="ruling-0001", proposal_id="proposal-0001", ts="2026-09-15T00:00:00+00:00"),
        make_project(id="project-0001", from_ruling="ruling-0001", ts="2026-09-15T00:01:00+00:00"),
        make_observation(id="observation-0001", project_id="project-0001", ts="2026-09-16T00:00:00+00:00"),
    ]
    items = feed.build_items(records, public=True)
    assert [i["id"] for i in items] == ["proposal-0001", "ruling-0001", "project-0001"]
    assert [i["seq"] for i in items] == [1, 2, 3]


def test_build_items_operator_keeps_every_kind_including_observation():
    records = [
        make_project(id="project-0001", from_ruling="ruling-0001"),
        make_observation(id="observation-0001", project_id="project-0001"),
    ]
    items = feed.build_items(records, public=False)
    assert [i["record"]["id"] for i in items] == ["project-0001", "observation-0001"]
    for item in items:
        assert item["run_id"] is None
        assert item["calls"] == []


def test_operator_item_carries_the_full_record():
    record = make_ruling(id="ruling-0001", proposal_id="proposal-0001")
    items = feed.build_items([record], public=False)
    assert items[0]["record"] == record


def test_operator_item_also_carries_the_flat_kind_dispatchable_shape():
    # Page code (the stream board's turned-down-proposal lookup, its
    # conversation renderer) reads kind/id/role/text the same way on both
    # projections -- it only reaches into `record` for an operator-only
    # detail. A bug where operator items had none of these (only a nested
    # `record`) silently emptied every kind-filtered list in operator mode.
    record = make_ruling(id="ruling-0001", proposal_id="proposal-0001")
    item = feed.build_items([record], public=False)[0]
    assert item["kind"] == "ruling"
    assert item["id"] == "ruling-0001"
    assert item["role"] == "overseer"
    assert item["text"] == feed.build_items([record], public=True)[0]["text"]


# ---- projects view ------------------------------------------------------------


def test_projects_view_maps_the_founding_proposal_thread_to_the_project():
    records = [
        make_proposal(id="proposal-0001"),
        make_ruling(id="ruling-0001", proposal_id="proposal-0001"),
        make_project(id="project-0001", from_ruling="ruling-0001"),
    ]
    view = feed.build_projects_view(records, public=True)
    assert view["thread_to_project"]["proposal-0001"] == "project-0001"
    assert view["projects"]["project-0001"]["version"] == 1
    assert view["projects"]["project-0001"]["abandoned"] is False


def test_projects_view_public_never_carries_the_private_abandon_reason():
    records = [
        make_proposal(id="proposal-0001"),
        make_ruling(id="ruling-0001", proposal_id="proposal-0001"),
        make_project(id="project-0001", from_ruling="ruling-0001"),
        make_abandon(id="abandon-0001", project_id="project-0001", reason="the secret real reason"),
    ]
    public_view = feed.build_projects_view(records, public=True)
    operator_view = feed.build_projects_view(records, public=False)
    assert public_view["projects"]["project-0001"]["abandoned"] is True
    assert "abandoned_reason" not in public_view["projects"]["project-0001"]
    assert "the secret real reason" not in json.dumps(public_view)
    assert operator_view["projects"]["project-0001"]["abandoned_reason"] == "the secret real reason"


def test_projects_view_counts_amend_versions():
    records = [
        make_proposal(id="proposal-0001"),
        make_ruling(id="ruling-0001", proposal_id="proposal-0001"),
        make_project(id="project-0001", from_ruling="ruling-0001"),
        make_amend(id="amend-0001", project_id="project-0001"),
        make_amend(id="amend-0002", project_id="project-0001"),
    ]
    view = feed.build_projects_view(records, public=True)
    assert view["projects"]["project-0001"]["version"] == 3


# ---- projects view: board fields (handoffs/2026-10-02-stream-board.md) -----


def _project_records(**project_overrides):
    return [
        make_proposal(id="proposal-0001"),
        make_ruling(id="ruling-0001", proposal_id="proposal-0001"),
        make_project(id="project-0001", from_ruling="ruling-0001", **project_overrides),
    ]


def test_projects_view_carries_status_links_and_steps():
    view = feed.build_projects_view(_project_records(), public=True)
    entry = view["projects"]["project-0001"]
    assert entry["status"] == "active"
    assert entry["ruling_id"] == "ruling-0001"
    assert entry["proposal_id"] == "proposal-0001"
    assert [s["id"] for s in entry["steps"]] == [
        "project-0001/s1", "project-0001/s2",
    ]


def test_projects_view_description_is_the_public_rationale():
    records = _project_records(public_rationale="Brewing the fort's first drink.")
    view = feed.build_projects_view(records, public=True)
    assert view["projects"]["project-0001"]["description"] == "Brewing the fort's first drink."
    assert view["projects"]["project-0001"]["description"] is not None


def test_projects_view_description_is_none_when_absent_no_summary_fallback():
    view = feed.build_projects_view(_project_records(), public=True)
    assert view["projects"]["project-0001"]["description"] is None


def test_projects_view_public_name_prefers_public_title_over_summary():
    view = feed.build_projects_view(
        _project_records(public_title="First workshop area"), public=True,
    )
    assert view["projects"]["project-0001"]["name"] == "First workshop area"


def test_projects_view_public_name_falls_back_to_a_truncated_summary():
    records = _project_records(summary="A " + "very " * 20 + "long private-audience summary.")
    view = feed.build_projects_view(records, public=True)
    name = view["projects"]["project-0001"]["name"]
    assert name is not None
    assert len(name) <= feed._DISPLAY_NAME_MAX
    assert name.endswith("…")


def test_projects_view_public_name_is_none_with_no_title_and_no_summary():
    records = _project_records(summary=None)
    view = feed.build_projects_view(records, public=True)
    assert view["projects"]["project-0001"]["name"] is None


def test_projects_view_urgency_sanitised_on_public_raw_on_operator():
    public_view = feed.build_projects_view(
        _project_records(urgency="urgent-ish"), public=True,
    )
    operator_view = feed.build_projects_view(
        _project_records(urgency="urgent-ish"), public=False,
    )
    assert public_view["projects"]["project-0001"]["urgency"] is None
    assert operator_view["projects"]["project-0001"]["urgency"] == "urgent-ish"


def test_projects_view_known_urgency_passes_through_on_both_sides():
    for which in (True, False):
        view = feed.build_projects_view(
            _project_records(urgency="high"), public=which,
        )
        assert view["projects"]["project-0001"]["urgency"] == "high"


def test_projects_view_public_steps_never_carry_held_detail():
    records = _project_records() + [
        make_executed(
            id="executed-0001", ruling_id="ruling-0001", cycle=9,
            step_id="project-0001/s1",
            actions=[{
                "tool": "construction.mine-vein", "outcome": "blocked",
                "targets": ["ring-13-ore-1"], "target_state": "held",
                "detail": "the private refusal text",
            }],
        ),
    ]
    public_view = feed.build_projects_view(records, public=True)
    operator_view = feed.build_projects_view(records, public=False)
    public_dump = json.dumps(public_view)
    assert "the private refusal text" not in public_dump
    operator_step = next(
        s for s in operator_view["projects"]["project-0001"]["steps"]
        if s["id"] == "project-0001/s1"
    )
    assert operator_step["held_detail"] == "the private refusal text"


def test_projects_view_public_hold_text_from_a_mapped_hold_code(tmp_path, monkeypatch):
    public_text_path = tmp_path / "public_text.yaml"
    public_text_path.write_text(
        "no_worker: No dwarf is free for this job.\n", encoding="utf-8",
    )
    original_load = feed.feed_status.load_public_text
    monkeypatch.setattr(
        feed.feed_status, "load_public_text",
        lambda *a, **k: original_load(public_text_path),
    )
    records = _project_records() + [
        make_executed(
            id="executed-0001", ruling_id="ruling-0001", cycle=9,
            step_id="project-0001/s1",
            actions=[{
                "tool": "construction.mine-vein", "outcome": "blocked",
                "targets": ["ring-13-ore-1"], "target_state": "held",
            }],
        ),
        make_observation(
            id="observation-0001", project_id="project-0001",
            step_id="project-0001/s1",
            results=[{
                "target": "ring-13-ore-1", "status": "not_observable",
                "reason": "no free miner", "hold_code": "no_worker",
            }],
        ),
    ]
    view = feed.build_projects_view(records, public=True)
    step = next(
        s for s in view["projects"]["project-0001"]["steps"]
        if s["id"] == "project-0001/s1"
    )
    assert step["state"] == "hold"
    assert step["hold_code"] == "no_worker"
    assert step["hold_text"] == "No dwarf is free for this job."


def test_projects_view_abandoned_project_status():
    records = _project_records() + [
        make_abandon(id="abandon-0001", project_id="project-0001"),
    ]
    view = feed.build_projects_view(records, public=True)
    assert view["projects"]["project-0001"]["status"] == "abandoned"


# ---- segmenting ---------------------------------------------------------------


def _fake_items(n):
    return [{"seq": i} for i in range(1, n + 1)]


def test_segment_items_splits_exact_multiples_with_nothing_open():
    closed, open_items = feed.segment_items(_fake_items(400), size=200)
    assert len(closed) == 2
    assert open_items == []
    assert closed[0][1]["first_seq"] == 1
    assert closed[0][1]["last_seq"] == 200
    assert closed[1][1]["first_seq"] == 201
    assert closed[1][1]["last_seq"] == 400


def test_segment_items_leaves_a_remainder_open():
    closed, open_items = feed.segment_items(_fake_items(250), size=200)
    assert len(closed) == 1
    assert [i["seq"] for i in open_items] == list(range(201, 251))


def test_segment_items_is_deterministic():
    items = _fake_items(200)
    closed_a, _ = feed.segment_items(items, size=200)
    closed_b, _ = feed.segment_items(items, size=200)
    assert closed_a[0][0] == closed_b[0][0]  # same content hash, same name


def test_segment_name_changes_if_content_changes():
    a = feed.segment_name(1, 1, 200, "body-a")
    b = feed.segment_name(1, 1, 200, "body-b")
    assert a != b


# ---- build_head ---------------------------------------------------------------


def test_build_head_reports_last_seq_and_state():
    items = _fake_items(5)
    head = feed.build_head(
        items, generation=1, closed_segment_names=[], open_segment_name="open.json",
        seasons_index_name="seasons/index.json", published_at="2026-10-01T00:00:00Z",
    )
    assert head["last_seq"] == 5
    assert head["state"] == "on"
    assert head["open_segment"] == "open.json"


def test_build_head_last_seq_zero_for_no_items():
    head = feed.build_head(
        [], generation=1, closed_segment_names=[], open_segment_name="open.json",
        seasons_index_name="seasons/index.json", published_at="2026-10-01T00:00:00Z",
    )
    assert head["last_seq"] == 0


def test_build_head_keeps_only_the_last_50_closed_segments():
    names = [f"seg-{i}.json" for i in range(60)]
    head = feed.build_head(
        _fake_items(1), generation=1, closed_segment_names=names,
        open_segment_name="open.json", seasons_index_name="seasons/index.json",
        published_at="2026-10-01T00:00:00Z",
    )
    assert len(head["closed_segments"]) == 50
    assert head["closed_segments"][-1] == names[-1]


# ---- write_feed (round trip through the filesystem) --------------------------


def test_write_feed_round_trips_head_open_and_projects(tmp_path):
    records = [
        make_proposal(id="proposal-0001", ts="2026-09-14T00:00:00+00:00"),
        make_ruling(id="ruling-0001", proposal_id="proposal-0001", ts="2026-09-15T00:00:00+00:00"),
    ]
    items = feed.build_items(records, public=True)
    projects = feed.build_projects_view(records, public=True)
    out_dir = tmp_path / "public"
    feed.write_feed(items, out_dir, projects=projects, published_at="2026-10-01T00:00:00Z")

    head = json.loads((out_dir / "head.json").read_text(encoding="utf-8"))
    assert head["last_seq"] == 2
    assert head["published_at"] == "2026-10-01T00:00:00Z"

    open_payload = json.loads((out_dir / "open.json").read_text(encoding="utf-8"))
    assert [i["id"] for i in open_payload["items"]] == ["proposal-0001", "ruling-0001"]

    written_projects = json.loads((out_dir / "projects.json").read_text(encoding="utf-8"))
    assert written_projects == projects

    assert not (out_dir / "status.json").exists()


def test_write_feed_writes_status_when_given(tmp_path):
    status = feed.build_placeholder_status()
    feed.write_feed([], tmp_path, projects={"thread_to_project": {}, "projects": {}}, status=status)
    written = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert written == status
    assert written["available"] is False


def test_write_feed_closed_segments_land_on_disk_with_matching_names(tmp_path):
    items = feed.build_items(
        [make_proposal(id=f"proposal-{i:04d}") for i in range(1, 201)], public=True,
    )
    feed.write_feed(items, tmp_path, projects={"thread_to_project": {}, "projects": {}})
    head = json.loads((tmp_path / "head.json").read_text(encoding="utf-8"))
    assert len(head["closed_segments"]) == 1
    seg_path = tmp_path / "seg" / head["closed_segments"][0]
    assert seg_path.exists()
    seg_payload = json.loads(seg_path.read_text(encoding="utf-8"))
    assert len(seg_payload["items"]) == 200


# ---- multiple forts (register 2026-10-02, "plan for more than one fort") --


def test_fort_feed_dir_shape():
    assert feed.fort_feed_dir("/data/public", "uniboslan") == Path("/data/public/forts/uniboslan")


def test_build_forts_index_marks_the_upserted_fort_current_and_others_not():
    existing = [
        {"id": "uniboslan", "name": "Ragwind", "status": "live", "current": True},
    ]
    forts = feed.build_forts_index(
        existing, {"id": "second-fort", "name": "Second Fort", "status": "live"},
    )
    by_id = {f["id"]: f for f in forts}
    assert by_id["second-fort"]["current"] is True
    assert by_id["uniboslan"]["current"] is False


def test_build_forts_index_updating_the_same_fort_again_keeps_one_entry():
    existing = [{"id": "uniboslan", "name": "Ragwind", "status": "live", "current": True}]
    forts = feed.build_forts_index(
        existing, {"id": "uniboslan", "name": "Ragwind", "status": "lost"},
    )
    assert len(forts) == 1
    assert forts[0]["status"] == "lost"
    assert forts[0]["current"] is True


def test_build_forts_index_is_sorted_by_id():
    existing = [{"id": "zzz-fort", "name": "Z", "status": "live", "current": True}]
    forts = feed.build_forts_index(existing, {"id": "aaa-fort", "name": "A", "status": "live"})
    assert [f["id"] for f in forts] == ["aaa-fort", "zzz-fort"]


def test_read_forts_index_missing_file_is_empty(tmp_path):
    assert feed.read_forts_index(tmp_path) == []


def test_write_fort_feed_writes_under_forts_subdir_and_updates_the_index(tmp_path):
    items = feed.build_items([make_proposal(id="proposal-0001")], public=True)
    feed.write_fort_feed(
        items, tmp_path, fort_id="uniboslan", fort_name="Ragwind", fort_status="live",
        projects={"thread_to_project": {}, "projects": {}},
    )
    fort_dir = tmp_path / "forts" / "uniboslan"
    assert (fort_dir / "head.json").exists()
    assert (fort_dir / "open.json").exists()

    forts_index = json.loads((tmp_path / "forts.json").read_text(encoding="utf-8"))
    assert forts_index == {
        "forts": [{"id": "uniboslan", "name": "Ragwind", "status": "live", "current": True}],
    }


def test_write_fort_feed_a_second_fort_is_added_without_losing_the_first(tmp_path):
    items = feed.build_items([make_proposal(id="proposal-0001")], public=True)
    feed.write_fort_feed(
        items, tmp_path, fort_id="uniboslan", fort_name="Ragwind", fort_status="live",
        projects={"thread_to_project": {}, "projects": {}},
    )
    feed.write_fort_feed(
        items, tmp_path, fort_id="second-fort", fort_name="Second Fort", fort_status="live",
        projects={"thread_to_project": {}, "projects": {}},
    )
    forts_index = json.loads((tmp_path / "forts.json").read_text(encoding="utf-8"))
    by_id = {f["id"]: f for f in forts_index["forts"]}
    assert set(by_id) == {"uniboslan", "second-fort"}
    assert by_id["second-fort"]["current"] is True
    assert by_id["uniboslan"]["current"] is False
    assert (tmp_path / "forts" / "uniboslan" / "head.json").exists()
    assert (tmp_path / "forts" / "second-fort" / "head.json").exists()


# ---- load_records_readonly never uses dfqueue.store._connect ---------------


def test_load_records_readonly_never_creates_a_database(tmp_path):
    missing = tmp_path / "does-not-exist.sqlite3"
    with pytest.raises(sqlite3.OperationalError):
        feed.load_records_readonly(missing)
    assert not missing.exists()


def test_load_records_readonly_reads_records_in_rowid_order(tmp_path):
    db_path = tmp_path / "test.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE records (id TEXT PRIMARY KEY, ts TEXT, kind TEXT, "
        "role TEXT, cycle INTEGER, type TEXT, proposal_id TEXT, payload TEXT)"
    )
    for i, kind in enumerate(("proposal", "ruling"), start=1):
        payload = json.dumps({"id": f"{kind}-000{i}", "kind": kind})
        conn.execute(
            "INSERT INTO records (id, ts, kind, role, cycle, payload) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (f"{kind}-000{i}", "2026-01-01T00:00:00Z", kind, "overseer", i, payload),
        )
    conn.commit()
    conn.close()

    records = feed.load_records_readonly(db_path)
    assert [r["kind"] for r in records] == ["proposal", "ruling"]


# ---- load_records_jsonl ------------------------------------------------------


def test_load_records_jsonl_reads_the_real_exported_shape(tmp_path):
    p = tmp_path / "records.jsonl"
    p.write_text(
        json.dumps({"id": "proposal-0001", "kind": "proposal"}) + "\n"
        + json.dumps({"id": "ruling-0001", "kind": "ruling"}) + "\n"
        + "\n",  # trailing blank line, as the real exports have
        encoding="utf-8",
    )
    records = feed.load_records_jsonl(p)
    assert [r["id"] for r in records] == ["proposal-0001", "ruling-0001"]



# ---- executed items name the job (board threads) -----------------------------


def _step_records(label="Dig shell", **action):
    steps = [{
        "id": "project-0001/s1", "tool": "construction.mine-vein", "args": {},
        "targets": {"set": ["a", "b", "c", "d"]}, "label": label,
    }]
    act = {"tool": "construction.mine-vein", "outcome": "success", "targets": ["a", "b"],
           "target_state": "issued"}
    act.update(action)
    return [
        make_project(id="project-0001", from_ruling="ruling-0001", steps=steps),
        make_executed(id="executed-0001", ruling_id="ruling-0001",
                      step_id="project-0001/s1", actions=[act]),
    ]


def _executed_item(records, public=True):
    items = feed.build_items(records, public=public)
    return next(i for i in items if i["kind"] == "executed")


def test_executed_public_item_carries_job_label_targets_and_total():
    item = _executed_item(_step_records())
    assert item["step_label"] == "Dig shell"
    assert item["step_targets"] == 2
    assert item["step_total"] == 4
    assert item["step_outcome"] == "started"
    assert "record" not in item


def test_executed_outcome_finished_and_failed():
    assert _executed_item(_step_records(target_state="done"))["step_outcome"] == "finished"
    assert _executed_item(_step_records(outcome="failed", target_state="failed"))["step_outcome"] == "failed"


def test_executed_step_label_goes_through_the_public_safety_net():
    item = _executed_item(_step_records(label="Fetch https://example.com/x"))
    assert item["step_label"] is None


def test_executed_without_a_step_has_no_label():
    item = _executed_item([make_executed(id="executed-0001", ruling_id="ruling-0001")])
    assert item["step_label"] is None
    assert item["step_total"] is None


def test_executed_step_label_follows_a_later_amend():
    records = _step_records()
    steps = [{"id": "project-0001/s1", "tool": "construction.mine-vein", "args": {},
              "targets": {"set": ["a"]}, "label": "Dig the deep shell"}]
    records.append(make_amend(id="amend-0001", project_id="project-0001", steps=steps))
    assert _executed_item(records)["step_label"] == "Dig the deep shell"


def test_operator_executed_item_carries_the_same_step_fields():
    item = _executed_item(_step_records(), public=False)
    assert item["step_label"] == "Dig shell" and item["record"]["step_id"] == "project-0001/s1"


# ---- titles that grow: proposal summary, project title, amend rename ---------


def test_proposal_item_title_is_a_safe_truncated_summary():
    long = make_proposal(id="proposal-0001", summary="Build a quiet bedroom wing. " * 10)
    item = feed.build_items([long], public=True)[0]
    assert item["title"] is not None and len(item["title"]) <= feed._DISPLAY_NAME_MAX
    unsafe = make_proposal(id="proposal-0002", summary="Open https://example.com/x now")
    assert feed.build_items([unsafe], public=True)[0]["title"] is None
    # the operator side is not safety-filtered
    assert feed.build_items([unsafe], public=False)[0]["title"].startswith("Open https")


def _title_records():
    return [
        make_proposal(id="proposal-0001"),
        make_ruling(id="ruling-0001", proposal_id="proposal-0001"),
        make_project(id="project-0001", from_ruling="ruling-0001", public_title="Dig the shell"),
    ]


def test_project_name_is_its_public_title():
    view = feed.build_projects_view(_title_records(), public=True)
    assert view["projects"]["project-0001"]["name"] == "Dig the shell"


def test_a_later_amend_with_a_public_title_renames_the_project():
    records = _title_records()
    steps = records[2]["steps"]
    records.append(make_amend(id="amend-0001", project_id="project-0001", steps=steps,
                              public_title="Dig the deep shell"))
    assert feed.build_projects_view(records, public=True)["projects"]["project-0001"]["name"] == "Dig the deep shell"
    records[3]["public_title"] = "see https://example.com/x"
    assert feed.build_projects_view(records, public=True)["projects"]["project-0001"]["name"] == "Dig the shell"


def test_ask_and_answer_show_their_real_text_and_the_ask_knows_its_answer():
    from dfqueue import feed as _feed
    recs = [
        {"id": "proposal-0004", "kind": "proposal", "role": "architect", "type": "dig_order",
         "summary": "Dig one down-stair.", "public_rationale": "Bedrooms need stone.", "cycle": 1, "ts": "2026-01-01T00:00:00+00:00"},
        {"id": "ask-0001", "kind": "ask", "role": "architect", "proposal_id": "proposal-0004",
         "question": "Can a bedroom be smoothed on this soil level?", "cycle": 1, "ts": "2026-01-01T00:00:01+00:00"},
        {"id": "answer-0001", "kind": "answer", "role": "consultant", "ask_id": "ask-0001",
         "answer": "No. Soil can't be smoothed; dig down to stone first.", "cycle": 1, "ts": "2026-01-01T00:00:02+00:00"},
        {"id": "ask-0002", "kind": "ask", "role": "quartermaster",
         "question": "See /opt/df/secret.txt for the stock list?", "cycle": 1, "ts": "2026-01-01T00:00:03+00:00"},
    ]
    items = {i["id"]: i for i in _feed.build_items(recs, public=True)}
    assert items["ask-0001"]["text"] == "Can a bedroom be smoothed on this soil level?"
    assert items["ask-0001"]["fact_check"] is True and items["ask-0001"]["answered"] is True
    assert items["ask-0001"]["answer_preview"].startswith("No. Soil can't be smoothed")
    assert items["answer-0001"]["text"] == "No. Soil can't be smoothed; dig down to stone first."
    # An unsafe question falls back to the generic line; it is not echoed.
    assert items["ask-0002"]["text"] == "The Quartermaster asked the Consultant a question."
    assert items["ask-0002"]["answered"] is False and items["ask-0002"]["fact_check"] is False


# ---- executed items' "Acted" list --------------------------------------------


def _executed_with(actions):
    return make_executed(id="executed-0001", ruling_id="ruling-0001", actions=actions)


def test_public_actions_carry_tool_name_target_count_and_outcome_but_never_target_ids():
    record = _executed_with([
        {"tool": "diggable.dig-stair", "outcome": "success", "targets": ["12,40,3", "13,40,3"]},
        {"tool": "workshop.build", "outcome": "failure", "targets": ["t1"],
         "detail": "Every barrel is full of plants."},
    ])
    item = feed.build_public_item(
        record, seq=1, reply_to="ruling-0001", thread="ruling-0001", badge=None, ctx={},
    )
    assert item["actions"] == [
        {"tool": "diggable.dig-stair", "name": "Diggable dig stair", "targets": 2,
         "outcome": "ok", "reason": None},
        {"tool": "workshop.build", "name": "Workshop build", "targets": 1,
         "outcome": "failed", "reason": "Every barrel is full of plants."},
    ]
    assert "12,40,3" not in json.dumps(item)


def test_public_action_reason_is_withheld_when_unsafe_but_the_operator_keeps_it():
    record = _executed_with([
        {"tool": "stocks.availability", "outcome": "failure", "targets": [],
         "detail": "see https://example.test/x for the cause"},
    ])
    public = feed.build_public_item(
        record, seq=1, reply_to="ruling-0001", thread="ruling-0001", badge=None, ctx={},
    )
    assert public["actions"][0]["reason"] is None
    assert public["actions"][0]["outcome"] == "failed"
    operator = feed.build_operator_item(
        record, seq=1, reply_to="ruling-0001", thread="ruling-0001", badge=None,
    )
    assert "example.test" in operator["actions"][0]["reason"]


def test_a_successful_action_never_carries_a_reason_and_long_reasons_are_cut():
    ok = feed.public_actions(_executed_with([
        {"tool": "trees.fell", "outcome": "success", "targets": ["a"], "detail": "fine"},
    ]))
    assert ok[0]["reason"] is None
    long = feed.public_actions(_executed_with([
        {"tool": "trees.fell", "outcome": "failure", "targets": [], "detail": "x " * 200},
    ]))
    assert len(long[0]["reason"]) <= feed.ACTION_REASON_MAX
