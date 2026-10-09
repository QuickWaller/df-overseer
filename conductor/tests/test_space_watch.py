"""The Architect's unused-dug-space briefing line (conductor/space_watch.py,
policy `space_survey`, register 2026-10-09): filtering by size and squareness,
new-since-last-wake memory, the policy block, the briefing key, and the cycle
wiring (a line for a new region once, never a wake reason)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from conductor import space_watch
from conductor.briefing import build_briefing
from conductor.cycle import run_cycle
from conductor.policy import PolicyError, load_policy
from conductor.tests import test_cycle as tc
from conductor.triage import Wake


def _region(rid, tiles=20, rect=0.8, near="Well", off=-1):
    return {
        "id": rid, "tiles": tiles, "bbox": {"w": 5, "h": 4}, "rectangularity": rect,
        "tiles_to_square": 0, "touches_corridor": True,
        "nearest_landmarks": [{"name": near, "distance_tiles": 9, "level_offset": off}],
    }


def test_filters_by_size_and_squareness():
    rep = {"regions": [_region("a"), _region("b", tiles=11), _region("c", rect=0.59), _region("d", tiles=12, rect=0.6)]}
    assert [r["id"] for r in space_watch.qualifying(rep, 12, 0.6)] == ["a", "d"]
    assert space_watch.qualifying({"error": "x"}, 12, 0.6) == []
    assert space_watch.qualifying(None, 12, 0.6) == []


def test_new_lines_only_for_unseen_and_set_is_current_qualifiers():
    rep = {"regions": [_region("aaa"), _region("bbb")]}
    lines, seen = space_watch.new_lines(rep, {"aaa"}, 12, 0.6)
    assert len(lines) == 1 and "bbb" in lines[0] and "aaa" not in lines[0]
    assert seen == {"aaa", "bbb"}
    lines, seen = space_watch.new_lines({"regions": [_region("bbb")]}, seen, 12, 0.6)
    assert lines == [] and seen == {"bbb"}


def test_line_has_numbers_names_and_no_grid():
    line = space_watch.line_for(_region("region-0000aa"))
    assert "region-0000aa" in line and "20 tiles" in line and "5x4" in line
    assert "1 level(s) below Well" in line and "touches a corridor" in line


def test_memory_roundtrip_and_corrupt_file(tmp_path):
    p = tmp_path / "space_survey.json"
    assert space_watch.load_seen(p) == set()
    space_watch.save_seen(p, {"x", "y"})
    assert space_watch.load_seen(p) == {"x", "y"}
    p.write_text("not json")
    assert space_watch.load_seen(p) == set()


def test_policy_ships_enabled_and_validates(tmp_path):
    pol = load_policy()
    assert pol.space_survey.enabled is True
    assert (pol.space_survey.min_tiles, pol.space_survey.min_rectangularity) == (12, 0.6)
    bad = tmp_path / "p.yaml"
    src = (Path(__file__).resolve().parent.parent / "policy.yaml").read_text(encoding="utf-8")
    bad.write_text(src.replace("min_rectangularity: 0.6", "min_rectangularity: 2"), encoding="utf-8")
    with pytest.raises(PolicyError):
        load_policy(bad)


def test_briefing_key_only_when_lines():
    wake = Wake("stuck_job", "x", ("architect",), "full_speed")
    kw = dict(role="architect", game_tick=1, wake=wake, vitals={}, diff_events=[], queue_summary={})
    assert "unused_dug_space" not in build_briefing(**kw)
    assert "unused_dug_space" not in build_briefing(**kw, unused_space=[])
    b = build_briefing(**kw, unused_space=["one", "two", "three", "four"])
    assert b["unused_dug_space"]["count"] == 4 and len(b["unused_dug_space"]["items"]) == 3


@pytest.mark.asyncio
async def test_cycle_shows_a_new_region_once_and_never_wakes_by_itself(tmp_path):
    tools = tc._base_tools()
    tools["openarea.survey"] = {"regions": [_region("region-00000a")]}
    deps = tc._deps(tmp_path, tools=tools)
    quiet = await run_cycle(1, deps)
    assert quiet.roles_woken == ()  # the survey alone wakes nobody

    tc._wake_both_advisors(tools)
    deps = tc._deps(tmp_path, tools=tools)
    result = await run_cycle(2, deps)
    brief = json.loads((result.archived_path / "briefings.json").read_text(encoding="utf-8"))
    assert "region-00000a" in json.dumps(brief["architect"]["unused_dug_space"])
    assert "unused_dug_space" not in brief["quartermaster"]

    tools["diff.since"] = tc._diff_sequence([[{"id": 1, "type": "JOB_COMPLETED", "detail": "Dig"}], []])
    deps = tc._deps(tmp_path, tools=tools)
    result = await run_cycle(3, deps)
    brief = json.loads((result.archived_path / "briefings.json").read_text(encoding="utf-8"))
    assert "unused_dug_space" not in brief["architect"]


@pytest.mark.asyncio
async def test_disabled_policy_makes_no_read(tmp_path):
    pol = load_policy()
    pol = dataclasses.replace(pol, space_survey=dataclasses.replace(pol.space_survey, enabled=False))
    tools = tc._base_tools()
    tools["openarea.survey"] = {"regions": [_region("region-00000a")]}
    tc._wake_both_advisors(tools)
    deps = tc._deps(tmp_path, tools=tools, policy=pol)
    result = await run_cycle(1, deps)
    brief = json.loads((result.archived_path / "briefings.json").read_text(encoding="utf-8"))
    assert "unused_dug_space" not in brief["architect"]
