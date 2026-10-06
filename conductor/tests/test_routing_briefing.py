"""Stage 2D: the ruling ask and to-do line per routed type, and the freeze line
(`docs/CONDUCTOR-EXECUTION.md` 3 and 6.6)."""

from __future__ import annotations

from conductor.briefing import build_briefing, routing_from_state, ruling_ask
from conductor.tests.test_ruling_briefing import VITALS, WAKE, _build

ROUTING = {"routed_types": ["work_order"], "unrouted_types": ["room_siting"], "frozen_types": []}


def test_without_routing_the_briefing_is_unchanged():
    assert _build(routing=None) == _build()
    assert "ACCEPTED ROUTED WORK" not in _build()
    assert routing_from_state({"open_projects": []}) is None


def test_the_ask_names_only_unrouted_types_for_carry_out_and_says_the_conductor_runs_the_rest():
    ask = ruling_ask(ROUTING, 6)
    assert "carry out each proposal you accept of type room_siting" in ask
    assert "work_order are carried out by the conductor" in ask
    assert "queue.project" in ask  # the unrouted route is still named
    assert "Expected about 6 calls" in ask


def test_the_ask_with_nothing_unrouted_has_no_carry_out_instruction():
    ask = ruling_ask({"routed_types": ["room_siting", "work_order"], "unrouted_types": [], "frozen_types": []}, 2)
    assert "queue.project" not in ask and "carried out by the conductor" in ask


def test_a_routed_proposal_says_it_is_ruled_only_and_the_to_do_line_says_the_conductor_runs_it():
    text = _build(routing=ROUTING)
    assert "Routed: if you accept it, the conductor runs it. Rule only." in text
    assert "ACCEPTED ROUTED WORK: work_order proposals you accept are run by the conductor" in text
    assert text.splitlines()[-1].startswith("Rule on each pending proposal")


def test_routing_parses_defensively():
    assert routing_from_state({"routing": {"routed_types": ["a"], "frozen_types": "bad"}}) == {
        "routed_types": ["a"], "unrouted_types": [], "frozen_types": []}
    assert routing_from_state({"routing": "nope"}) is None
    assert routing_from_state(None) is None


def test_the_freeze_line_reaches_an_advisor_only_when_a_type_is_frozen():
    kw = dict(role="architect", game_tick=1, wake=WAKE, vitals=VITALS, diff_events=[], queue_summary={})
    assert "frozen" not in build_briefing(**kw)
    brief = build_briefing(frozen_types=["room_siting", "corridor"], **kw)
    assert brief["frozen"]["types"] == ["room_siting", "corridor"]
    assert "Skip this work" in brief["frozen"]["note"]
