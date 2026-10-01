"""Tests for `dfqueue.site_data`: the Agents/Tools/Forts page data layer
(`handoffs/2026-10-02-site-agents-tools.md`).

The two load-bearing guarantees this file exists to prove:

1. The public gotcha projection never carries `call_excerpt`, and never
   carries withheld title/body text -- the exact safety-net property the
   handoff's "Done when" names.
2. `agents.json`'s per-role tool counts equal the real, live-enforced
   allowlists `dfmcp.roles.load_roster` computes -- the same roster every
   MCP server load uses, not a hand-kept copy that could drift.
"""

from __future__ import annotations

import json

import pytest

from dfqueue import feed, site_data
from dfmcp import gotchas_store


FIXTURE = "web/stream/fixtures/board-demo.jsonl"


@pytest.fixture(scope="module")
def records():
    return feed.load_records_jsonl(FIXTURE)


@pytest.fixture(scope="module")
def registry():
    return site_data._default_registry()


@pytest.fixture(scope="module")
def roster(registry):
    return site_data._default_roster(registry)


# ---------------------------------------------------------------------------
# agents.json
# ---------------------------------------------------------------------------


def test_agents_json_tool_counts_match_the_live_roster(registry, roster, records):
    """The number this test asserts is not a magic constant: it is read
    from the exact same `load_roster` call the MCP server itself makes at
    start-up (dfmcp/tests/test_roles.py's own `registry` fixture, same
    merge of native tool modules). If an allowlist changes, this test's
    expectation changes with it -- it can never silently drift from the
    real enforced boundary."""
    agents = site_data.build_agents_json(records, registry=registry, roster=roster)
    for role, perms in roster.roles.items():
        expected = len(perms.read) + len(perms.write)
        assert agents["roles"][role]["tool_count"] == expected
        assert len(agents["roles"][role]["tools"]) == expected
        assert set(agents["roles"][role]["tools"]) == set(perms.read) | set(perms.write)


def test_agents_json_enabled_roles_match_roster_yaml(records, roster):
    agents = site_data.build_agents_json(records, roster=roster)
    assert set(agents["role_order"]) == set(roster.roles)
    # Disabled-but-defined roles still appear, as planned, with no tools.
    assert "marshal" in agents["planned_order"]
    assert "chronicler" in agents["planned_order"]
    assert agents["roles"]["marshal"]["enabled"] is False
    assert agents["roles"]["marshal"]["tools"] == []
    assert agents["roles"]["marshal"]["blocked_on"]  # real prose from ROSTER.yaml, not invented


def test_agents_json_conductor_is_code_not_a_model(records, roster):
    agents = site_data.build_agents_json(records, roster=roster)
    conductor = agents["roles"]["conductor"]
    assert conductor["kind"] == "system"
    assert conductor["model"] is None
    assert conductor["name"] == "System"


def test_agents_json_track_record_from_real_records(records, roster):
    """board-demo.jsonl has 5 rulings (4 architect-proposed + 1
    quartermaster-proposed), one rejected, one overseer ask, one consultant
    answer -- counted, never invented."""
    agents = site_data.build_agents_json(records, roster=roster)
    overseer = agents["roles"]["overseer"]["record"]
    assert overseer["ruled"] == 5
    assert overseer["accepted"] == 4
    assert overseer["rejected"] == 1
    assert overseer["asks"] == 1

    architect = agents["roles"]["architect"]["record"]
    assert architect["proposals"] == 4
    assert architect["accepted"] == 3
    assert architect["rejected"] == 1

    consultant = agents["roles"]["consultant"]["record"]
    assert consultant["answers"] == 1


def test_agents_json_omits_wake_counts_never_invents_them(records, roster):
    """Wake-ups are slice S2 and nothing in the queue records them -- the
    conductor's spoke must show no number, never a guess."""
    agents = site_data.build_agents_json(records, roster=roster)
    assert agents["spokes"]["conductor"]["out"] == ["wakes", None]


def test_charter_changes_are_real_git_history(records, roster):
    agents = site_data.build_agents_json(records, roster=roster)
    changes = agents["roles"]["overseer"]["charter_changes"]
    assert changes, "expected at least one real commit touching agents/overseer/role.md"
    for date, message in changes:
        assert date and message


def test_humanize_model_id():
    assert site_data.humanize_model_id("deepseek/deepseek-v4-pro") == "DeepSeek V4 Pro"
    assert site_data.humanize_model_id("anthropic/claude-haiku-4-5-20251001") == "Claude Haiku 4 5 20251001"
    assert site_data.humanize_model_id(None) is None


# ---------------------------------------------------------------------------
# tools.json
# ---------------------------------------------------------------------------


def test_tools_json_every_tool_has_an_area(registry, roster):
    tools = site_data.build_tools_json(registry, roster)
    for tool in tools["tools"]:
        assert tool["area"]
        assert tool["confidence"]["level"] in ("full", "medium", "low")


def test_tools_json_role_dots_match_roster(registry, roster):
    tools = site_data.build_tools_json(registry, roster)
    by_id = {t["id"]: t for t in tools["tools"]}
    # queue.rule is sole-writer-only: only the overseer should ever show up.
    assert by_id["queue.rule"]["roles"] == ["overseer"]


def test_area_of_unknown_prefix_is_other():
    assert site_data.area_of("madeup.verb") == "Other"


# ---------------------------------------------------------------------------
# gotchas.json
# ---------------------------------------------------------------------------


@pytest.fixture
def gotcha_db(tmp_path):
    path = tmp_path / "gotchas.sqlite3"
    gotchas_store.init_store(path)
    gotchas_store.add_entry(
        path,
        {
            "tool": "zone.place",
            "list": "gotcha",
            "title": "furniture already in the area: placing a zone fails without a flag",
            "body": "Placing a zone over a coffin or bed fails unless the call allows furniture.",
            "written_by_role": "architect",
            "run_id": "run-1",
            "call_excerpt": "zone.place Tomb 3 3 1 NEAR_Coffin#12 AROUND_FURNITURE",
        },
        known_tools=["zone.place"],
    )
    gotchas_store.add_entry(
        path,
        {
            "tool": "orders.create",
            "list": "vent",
            "title": "repeated failures: contact support@example.com if this keeps happening",
            "body": "An unsafe body naming a URL https://example.com/internal and a token ABCDEFGHIJKLMNOPQRSTUVWX01.",
            "written_by_role": "quartermaster",
            "run_id": "run-2",
            "call_excerpt": "orders.create work_order drink 40",
        },
        known_tools=["zone.place", "orders.create"],
    )
    return path


def test_public_gotchas_never_carry_call_excerpt(gotcha_db):
    entries = site_data.load_gotchas_readonly(gotcha_db)
    public = site_data.build_gotchas_json(entries, public=True)
    assert len(public) == 2
    for item in public:
        assert "call_excerpt" not in item
        assert "run_id" not in item


def test_public_gotchas_withhold_unsafe_text_never_edit_it(gotcha_db):
    entries = site_data.load_gotchas_readonly(gotcha_db)
    public = site_data.build_gotchas_json(entries, public=True)
    by_tool = {item["tool"]: item for item in public}
    safe = by_tool["zone.place"]
    assert safe["withheld"] is False
    assert safe["title"] == "furniture already in the area: placing a zone fails without a flag"

    unsafe = by_tool["orders.create"]
    assert unsafe["withheld"] is True
    assert unsafe["title"] is None
    assert unsafe["body"] is None


def test_operator_gotchas_carry_call_excerpt_and_full_text(gotcha_db):
    entries = site_data.load_gotchas_readonly(gotcha_db)
    operator = site_data.build_gotchas_json(entries, public=False)
    by_tool = {item["tool"]: item for item in operator}
    assert by_tool["zone.place"]["call_excerpt"].startswith("zone.place")
    unsafe = by_tool["orders.create"]
    assert unsafe["withheld"] is False
    assert unsafe["title"] == "repeated failures: contact support@example.com if this keeps happening"
    assert "call_excerpt" in unsafe


def test_gotchas_readonly_never_creates_a_missing_store(tmp_path):
    missing = tmp_path / "does-not-exist.sqlite3"
    with pytest.raises(Exception):
        site_data.load_gotchas_readonly(missing)
    assert not missing.exists()


def test_public_gotchas_json_round_trips_through_json(gotcha_db):
    entries = site_data.load_gotchas_readonly(gotcha_db)
    public = site_data.build_gotchas_json(entries, public=True)
    # Would raise on anything non-serialisable (e.g. a stray Row object).
    json.dumps(public)
