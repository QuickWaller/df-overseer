"""Regression for the wildlife/threat tier logic in
scripts/dfhack/df-overseer-threat.lua (classify_tier, TIER_ESCALATIONS),
handoffs/2026-09-23-attention-tiers-ingame.md item 1, over
research/2026-09-23-wildlife-threat-classes.md S:E1's rule.

**What this test actually proves, stated plainly** (per this project's own
verify-the-verification rule, and the same honest framing
tests/test_reachability_ring_logic.py already uses). This environment has
no Lua interpreter and this stream is offline (no VM, no live DFHack), so
`df-overseer-threat.lua`'s own bytes cannot be executed here. What follows
is a line-for-line Python PORT of classify_tier's control flow, copied by
hand -- NOT a mechanical extraction, so it can silently drift from the real
file if that file is edited later without updating this port.
`test_port_mirrors_lua_source` below is the guard against that: it re-reads
the real .lua file's own source text and asserts the tier names and the
specific escalation conditions this port hardcodes still appear in it.

The scenarios below are the handoff's own explicit list (item 7): a
kea-shaped candidate does not pause; a large predator that has reached the
citizens does; an unreachable invader slows rather than pauses; plus the
concrete kea-at-68-tiles verdict research doc S:E1 states by name.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
THREAT_LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-threat.lua"

DEFAULT_CLOSE_RANGE_TILES = 10

TIER_RANK = {"record_only": 1, "slow": 2, "pause": 3}

# Mirrors TIER_ESCALATIONS in the .lua file.
TIER_ESCALATIONS = [
    ("is_large_predator", "pause"),
    ("is_buildingdestroyer", "pause"),
]


def empty_flags(**overrides) -> Dict[str, bool]:
    flags = {
        "is_large_predator": False,
        "is_buildingdestroyer": False,
        "is_curiousbeast_item": False,
        "is_curiousbeast_eater": False,
        "is_curiousbeast_guzzler": False,
        "is_benign": False,
        "is_mischievous": False,
    }
    flags.update(overrides)
    return flags


def worst_tier(a: str, b: str) -> str:
    return a if TIER_RANK[a] >= TIER_RANK[b] else b


def classify_tier(
    flags: Dict[str, bool],
    is_invader: bool,
    shares_group: bool,
    within_radius: bool,
    distance_tiles: Optional[float],
    prior_closest_distance_tiles: Optional[float],
    close_range_tiles: float = DEFAULT_CLOSE_RANGE_TILES,
) -> Tuple[str, List[str]]:
    reachable = shares_group or within_radius
    if not reachable:
        return "record_only", ["not_reachable"]

    tier = "record_only"
    reasons: List[str] = []

    for flag_name, escalate_to in TIER_ESCALATIONS:
        if flags[flag_name]:
            tier = worst_tier(tier, escalate_to)
            reasons.append(flag_name)

    if is_invader:
        if shares_group:
            tier = worst_tier(tier, "pause")
            reasons.append("invader_reachable")
        else:
            tier = worst_tier(tier, "slow")
            reasons.append("invader_visible_not_yet_reachable")

    if flags["is_curiousbeast_item"] or flags["is_curiousbeast_eater"]:
        close = distance_tiles is not None and distance_tiles <= close_range_tiles
        closing = (
            distance_tiles is not None
            and prior_closest_distance_tiles is not None
            and distance_tiles < prior_closest_distance_tiles
        )
        if close or closing:
            tier = worst_tier(tier, "slow")
            reasons.append("theft_tag_close_range" if close else "theft_tag_closing_in")

    if not reasons:
        reasons.append("no_pause_or_slow_condition_met")
    return tier, reasons


# ----------------------------------------------------------------------------
# handoffs/2026-09-23-attention-tiers-ingame.md item 7's own required cases.

def test_kea_shaped_candidate_at_68_tiles_does_not_pause_or_slow():
    """research/2026-09-23-wildlife-threat-classes.md S:E1's own explicit
    verdict: a BIRD_KEA reachable at any distance, no dangerous tag, no
    closing-in evidence yet -- must land in record_only, not pause or slow."""
    kea_flags = empty_flags(is_curiousbeast_item=True, is_curiousbeast_eater=True)
    tier, reasons = classify_tier(
        kea_flags, is_invader=False, shares_group=True, within_radius=True,
        distance_tiles=68, prior_closest_distance_tiles=None,
    )
    assert tier == "record_only"
    assert reasons == ["no_pause_or_slow_condition_met"]


def test_large_predator_that_has_reached_the_citizens_pauses():
    flags = empty_flags(is_large_predator=True)
    tier, reasons = classify_tier(
        flags, is_invader=False, shares_group=True, within_radius=False,
        distance_tiles=5, prior_closest_distance_tiles=None,
    )
    assert tier == "pause"
    assert "is_large_predator" in reasons


def test_buildingdestroyer_reachable_only_by_landmark_radius_still_pauses():
    """Pause is triggered by reachability at all (shares_group OR
    within_radius), not specifically the walkable-group criterion -- matches
    S:E1's "reachable AND (LARGE_PREDATOR OR BUILDINGDESTROYER OR ...)"."""
    flags = empty_flags(is_buildingdestroyer=True)
    tier, _ = classify_tier(
        flags, is_invader=False, shares_group=False, within_radius=True,
        distance_tiles=20, prior_closest_distance_tiles=None,
    )
    assert tier == "pause"


def test_unreachable_invader_never_appears_record_only_by_construction():
    """A candidate that clears neither reachability criterion never reaches
    df-overseer-threat.lua's candidate list at all (the outer `if shares_group
    or within_radius then` gate in find_threats) -- classify_tier's own
    not-reachable branch exists for completeness/defence in depth."""
    flags = empty_flags()
    tier, reasons = classify_tier(
        flags, is_invader=True, shares_group=False, within_radius=False,
        distance_tiles=200, prior_closest_distance_tiles=None,
    )
    assert tier == "record_only"
    assert reasons == ["not_reachable"]


def test_invader_visible_but_not_yet_reachable_slows_not_pauses():
    """The handoff's own required case: 'an unreachable invader slows
    rather than pauses'. Reachable here means it cleared the landmark-radius
    criterion (visible/near) but NOT the walkable-group criterion (not yet
    actually able to reach a citizen) -- S:E1's precise distinction."""
    flags = empty_flags()
    tier, reasons = classify_tier(
        flags, is_invader=True, shares_group=False, within_radius=True,
        distance_tiles=25, prior_closest_distance_tiles=None,
    )
    assert tier == "slow"
    assert reasons == ["invader_visible_not_yet_reachable"]


def test_invader_that_has_reached_the_citizens_pauses():
    flags = empty_flags()
    tier, reasons = classify_tier(
        flags, is_invader=True, shares_group=True, within_radius=False,
        distance_tiles=3, prior_closest_distance_tiles=None,
    )
    assert tier == "pause"
    assert reasons == ["invader_reachable"]


def test_theft_tag_closing_in_slows():
    flags = empty_flags(is_curiousbeast_item=True)
    tier, reasons = classify_tier(
        flags, is_invader=False, shares_group=True, within_radius=False,
        distance_tiles=40, prior_closest_distance_tiles=68,
    )
    assert tier == "slow"
    assert reasons == ["theft_tag_closing_in"]


def test_theft_tag_close_range_slows_even_on_first_sighting():
    flags = empty_flags(is_curiousbeast_eater=True)
    tier, reasons = classify_tier(
        flags, is_invader=False, shares_group=True, within_radius=False,
        distance_tiles=4, prior_closest_distance_tiles=None,
    )
    assert tier == "slow"
    assert reasons == ["theft_tag_close_range"]


def test_theft_tag_far_and_not_closing_stays_record_only():
    """First sighting (no prior), far away: must NOT escalate. This is
    what makes the kea's own case (test above) correct in general, not just
    for the one 68-tile number."""
    flags = empty_flags(is_curiousbeast_item=True)
    tier, reasons = classify_tier(
        flags, is_invader=False, shares_group=True, within_radius=False,
        distance_tiles=55, prior_closest_distance_tiles=None,
    )
    assert tier == "record_only"


def test_benign_and_guzzler_never_escalate_regardless_of_reachability():
    """research doc S:E4: BENIGN and CURIOUSBEAST_GUZZLER should never
    reach the clock-policy code path at all."""
    for flags in (empty_flags(is_benign=True), empty_flags(is_curiousbeast_guzzler=True)):
        tier, _ = classify_tier(
            flags, is_invader=False, shares_group=True, within_radius=True,
            distance_tiles=1, prior_closest_distance_tiles=None,
        )
        assert tier == "record_only"


def test_mischievous_alone_never_escalates():
    """research doc S:D/E2: this project has no legal way to gate a
    DECISION on MISCHIEVOUS (that would reproduce the isHidden violation) --
    classify_tier must never read it."""
    flags = empty_flags(is_mischievous=True)
    tier, _ = classify_tier(
        flags, is_invader=False, shares_group=True, within_radius=True,
        distance_tiles=1, prior_closest_distance_tiles=None,
    )
    assert tier == "record_only"


def test_pause_always_dominates_slow_conditions_in_the_same_candidate():
    flags = empty_flags(is_large_predator=True, is_curiousbeast_item=True)
    tier, _ = classify_tier(
        flags, is_invader=False, shares_group=True, within_radius=False,
        distance_tiles=2, prior_closest_distance_tiles=None,
    )
    assert tier == "pause"


# ----------------------------------------------------------------------------
# Drift guard: the real .lua file must still carry the tier names and the
# specific per-flag escalations this port hardcodes.

def test_port_mirrors_lua_source():
    source = THREAT_LUA.read_text(encoding="utf-8")
    for tier_name in ("pause", "slow", "record_only"):
        assert f'"{tier_name}"' in source, f"tier name {tier_name!r} missing from threat.lua"
    for flag_name in (
        "is_large_predator", "is_buildingdestroyer", "is_curiousbeast_item",
        "is_curiousbeast_eater", "is_curiousbeast_guzzler", "is_benign", "is_mischievous",
    ):
        assert flag_name in source, f"raw-tag flag {flag_name!r} missing from threat.lua"
    assert "TIER_ESCALATIONS" in source
    assert "classify_tier" in source
    assert "class_flags" in source
    # The two per-flag pause escalations this port hardcodes.
    assert '{ flag = "is_large_predator", tier = "pause" }' in source
    assert '{ flag = "is_buildingdestroyer", tier = "pause" }' in source
