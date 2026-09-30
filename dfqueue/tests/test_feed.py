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


def test_render_game_date_first_day_of_year_one():
    assert feed.render_game_date(0) == "1 Granite, year 1"


def test_render_game_date_rolls_into_the_second_month():
    # 28 days (0-indexed day 28) is the first day of the second month.
    assert feed.render_game_date(28 * feed.TICKS_PER_DAY) == "1 Slate, year 1"


def test_render_game_date_stays_deterministic_for_a_real_cycle_value():
    # From the real exported record (evals/live/2026-09-15-overseer-first-ruling)
    result = feed.render_game_date(12274877)
    assert isinstance(result, str)
    assert "year" in result


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
    "Reachable at 192.168.1.42 on the LAN",
    "The config lives at /etc/df-overseer/secrets.yaml",
    "Windows path C:\\Users\\wills\\secrets\\file.txt has it",
    "Contact admin@example.com for access",
    "The token is aGVsbG93b3JsZHRoaXNpc2FsbG9uZw123456",
    "It links <script>alert(1)</script> in the page",
])
def test_find_unsafe_pattern_catches_leaky_shapes(text):
    assert feed.find_unsafe_pattern(text) is not None


@pytest.mark.parametrize("text", [
    "The fort is still entirely on the surface with no workshops.",
    "Siting the first workshop there raises the landmark count above four.",
    "5 tiles SE of Embark Site, in a 3x3 clearing.",
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


def test_project_amend_abandon_carry_no_public_text_yet_named_gap():
    # design §3.3 item 6 (public_title/public_rationale) is not stored yet;
    # these must read text: None, never fall back to the private
    # summary/because/reason fields.
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


def test_build_public_item_refuses_an_unrecognised_kind():
    with pytest.raises(ValueError):
        feed.build_public_item(
            {"kind": "wake", "id": "wake-0001", "role": "conductor"},
            seq=1, reply_to=None, thread="wake-0001", badge=None, ctx={},
        )


# ---- generated text for the always-generated kinds --------------------------


def test_ask_public_text_never_carries_the_real_question():
    record = make_ask(id="ask-0001", question="Does a workshop on soil ever stall?")
    item = feed.build_public_item(
        record, seq=1, reply_to=None, thread="ask-0001", badge=None, ctx={},
    )
    assert item["text"] == "The Architect asked the Consultant a question."
    assert "soil" not in item["text"]


def test_answer_public_text_never_carries_the_real_answer():
    ask = make_ask(id="ask-0001", role="quartermaster")
    answer = make_answer(id="answer-0001", ask_id="ask-0001", answer="Yes, on peat specifically.")
    ctx = {"records_by_id": {"ask-0001": ask}}
    item = feed.build_public_item(
        answer, seq=2, reply_to="ask-0001", thread="ask-0001", badge=None, ctx=ctx,
    )
    assert item["text"] == "The Consultant answered the Quartermaster's question."
    assert "peat" not in item["text"]


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
