"""conductor/briefing.py: Tier 0 only, and size independent of fort size."""

from __future__ import annotations

from conductor.briefing import MAX_DIFF_EVENTS, MAX_QUEUE_IDS, build_briefing
from conductor.triage import Wake

_WAKE = Wake("migrant_wave", "a migrant wave arrived", ("architect", "quartermaster"), "full_speed")
_VITALS = {
    "alive": 22, "dead_total": 1, "worst_hunger_status": "fine",
    "worst_thirst_status": "fine", "warning_count": 0,
}


def test_build_briefing_carries_the_wake_reason_and_vitals():
    briefing = build_briefing(
        role="architect", game_tick=178877, wake=_WAKE, vitals=_VITALS,
        diff_events=[], queue_summary={"count": 0, "proposal_ids": []},
    )
    assert briefing["role"] == "architect"
    assert briefing["wake_reason"] == "migrant_wave"
    assert briefing["clock"] == "full_speed"
    assert briefing["vitals"]["alive"] == 22
    assert briefing["vitals"]["dead_total"] == 1


def test_briefing_size_is_independent_of_the_number_of_diff_events():
    """The safety net: however many events piled up since this role last
    woke, the briefing itself stays small."""
    few_events = [{"id": i, "type": "REPORT"} for i in range(3)]
    many_events = [{"id": i, "type": "REPORT"} for i in range(5000)]

    small = build_briefing(
        role="quartermaster", game_tick=1, wake=_WAKE, vitals=_VITALS,
        diff_events=few_events, queue_summary={"count": 0},
    )
    large = build_briefing(
        role="quartermaster", game_tick=1, wake=_WAKE, vitals=_VITALS,
        diff_events=many_events, queue_summary={"count": 0},
    )

    assert len(small["diff_since_last_wake"]["items"]) == 3
    assert len(large["diff_since_last_wake"]["items"]) == MAX_DIFF_EVENTS
    assert large["diff_since_last_wake"]["truncated"] is True
    assert large["diff_since_last_wake"]["count"] == 5000
    assert not small["diff_since_last_wake"]["truncated"]


def test_briefing_size_is_independent_of_the_queue_size():
    huge_queue = {"count": 9000, "proposal_ids": [f"proposal-{i:04d}" for i in range(9000)]}
    briefing = build_briefing(
        role="overseer", game_tick=1, wake=_WAKE, vitals=_VITALS,
        diff_events=[], queue_summary=huge_queue,
    )
    assert len(briefing["queue"]["ids"]["items"]) == MAX_QUEUE_IDS
    assert briefing["queue"]["ids"]["truncated"] is True
    assert briefing["queue"]["count"] == 9000


def test_briefing_uses_ask_ids_for_the_consultant():
    queue_summary = {"count": 2, "ask_ids": ["ask-0001", "ask-0002"]}
    briefing = build_briefing(
        role="consultant", game_tick=1, wake=_WAKE, vitals=_VITALS,
        diff_events=[], queue_summary=queue_summary,
    )
    assert briefing["queue"]["ids"]["items"] == ["ask-0001", "ask-0002"]


def test_briefing_never_carries_a_raw_coordinate_shaped_field():
    """Belt and braces, matching this project's own coordinate-free
    discipline elsewhere: nothing this function adds is x/y/z-shaped."""
    briefing = build_briefing(
        role="architect", game_tick=1, wake=_WAKE, vitals=_VITALS,
        diff_events=[{"id": 1, "type": "REPORT", "near_landmark": "Wagon"}],
        queue_summary={"count": 0},
    )
    assert "x" not in briefing
    assert "y" not in briefing
    assert "z" not in briefing
