"""Regression for scripts/dfhack/df-overseer-ledger.lua
(handoffs/2026-09-23-attention-tiers-ingame.md item 4).

Two kinds of coverage, per this project's own verify-the-verification rule:

1. A Python PORT of record()/read_ledger()'s aggregation logic (this
   environment has no Lua interpreter, same honest framing as
   tests/test_reachability_ring_logic.py) -- proves the aggregation,
   decay-at-read, and "outcome other than present never decays" rules are
   correct as specified.

2. A STATIC, SOURCE-TEXT guard on the real .lua file -- this is the actual
   hard rule ("the ledger's write path never pauses and never wakes") and
   does not need a Lua interpreter to check: it is a property of which
   names appear in the file's own text. This is the strongest test in this
   suite, not a stand-in for one: a future edit that accidentally wires a
   pause/wake call into this file fails THIS test, not just a review.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER_LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-ledger.lua"


# ----------------------------------------------------------------------------
# Part 1: Python port of the aggregation logic.

class Ledger:
    """Port of df-overseer-ledger.lua's rows table plus record()/read_ledger()."""

    def __init__(self) -> None:
        self.rows: Dict[str, Dict[str, Any]] = {}

    def closest_distance(self, race: str) -> Optional[float]:
        row = self.rows.get(race)
        return row["closest_distance_tiles"] if row else None

    def record(self, race: str, tick: Optional[int], distance_tiles: Optional[float],
               outcome: str = "present") -> Dict[str, Any]:
        if not race:
            return {"ok": False, "error": "record requires a race"}

        row = self.rows.get(race)
        if row is None:
            row = {
                "race": race,
                "first_seen_tick": tick,
                "last_seen_tick": tick,
                "sighting_count": 0,
                "closest_distance_tiles": distance_tiles,
                "outcomes": {},
            }
            self.rows[race] = row

        row["sighting_count"] += 1
        if tick is not None:
            if row["first_seen_tick"] is None:
                row["first_seen_tick"] = tick
            row["last_seen_tick"] = tick
        if distance_tiles is not None and (
            row["closest_distance_tiles"] is None or distance_tiles < row["closest_distance_tiles"]
        ):
            row["closest_distance_tiles"] = distance_tiles
        row["outcomes"][outcome] = row["outcomes"].get(outcome, 0) + 1

        return {"ok": True, "race": race, "row": row}

    def read(self, max_age_ticks: Optional[int], now_tick: Optional[int]) -> List[Dict[str, Any]]:
        out = []
        for row in self.rows.values():
            only_present = set(row["outcomes"].keys()) <= {"present"}
            stale = (
                max_age_ticks is not None and now_tick is not None
                and row["last_seen_tick"] is not None
                and (now_tick - row["last_seen_tick"]) > max_age_ticks
            )
            if not (only_present and stale):
                out.append(row)
        return sorted(out, key=lambda r: r["race"])


def test_repeated_sightings_of_the_same_race_aggregate_not_append():
    ledger = Ledger()
    for tick in (100, 200, 300):
        ledger.record("BIRD_KEA", tick, 68, "present")
    assert len(ledger.rows) == 1
    row = ledger.rows["BIRD_KEA"]
    assert row["sighting_count"] == 3
    assert row["first_seen_tick"] == 100
    assert row["last_seen_tick"] == 300
    assert row["outcomes"] == {"present": 3}


def test_closest_distance_tracks_the_minimum_not_the_latest():
    ledger = Ledger()
    ledger.record("BIRD_KEA", 100, 68, "present")
    ledger.record("BIRD_KEA", 200, 40, "present")
    ledger.record("BIRD_KEA", 300, 55, "present")  # moved back away
    assert ledger.rows["BIRD_KEA"]["closest_distance_tiles"] == 40


def test_ledger_closest_distance_read_is_a_pure_lookup_no_row_created():
    ledger = Ledger()
    assert ledger.closest_distance("BIRD_KEA") is None
    assert "BIRD_KEA" not in ledger.rows


def test_a_theft_outcome_graduates_and_a_present_only_row_decays():
    ledger = Ledger()
    ledger.record("BIRD_KEA", 100, 68, "present")           # present-only row
    ledger.record("GREMLIN", 100, 5, "theft")                # graduated row

    # Both fresh: neither decays.
    fresh = ledger.read(max_age_ticks=1000, now_tick=200)
    assert {r["race"] for r in fresh} == {"BIRD_KEA", "GREMLIN"}

    # Far in the future: the present-only row decays out, the theft row survives.
    later = ledger.read(max_age_ticks=1000, now_tick=50000)
    assert {r["race"] for r in later} == {"GREMLIN"}


def test_a_row_with_any_non_present_outcome_never_decays_even_mixed():
    ledger = Ledger()
    ledger.record("BIRD_KEA", 100, 68, "present")
    ledger.record("BIRD_KEA", 150, 40, "theft")
    later = ledger.read(max_age_ticks=1000, now_tick=50000)
    assert len(later) == 1
    assert later[0]["outcomes"] == {"present": 1, "theft": 1}


def test_no_window_returns_every_row_regardless_of_age():
    ledger = Ledger()
    ledger.record("BIRD_KEA", 100, 68, "present")
    assert len(ledger.read(max_age_ticks=None, now_tick=None)) == 1


def test_empty_race_is_a_tool_error_not_a_silent_no_op():
    ledger = Ledger()
    result = ledger.record("", 100, 5, "present")
    assert result["ok"] is False
    assert ledger.rows == {}


# ----------------------------------------------------------------------------
# Part 2: the structural "cannot pause or wake" guard, against the real file.

FORBIDDEN_CALL_SUBSTRINGS = [
    "SetPauseState",
    "clock_pause(",
    "clock_resume(",
    "clock_arm(",
    "clock_disarm(",
    "repeatUtil.",
    "repeat-util",
]


def test_ledger_source_never_references_pause_or_wake_machinery():
    source = LEDGER_LUA.read_text(encoding="utf-8")
    # Strip comment lines (-- ...) before scanning: this file's own header
    # DISCUSSES SetPauseState/clock_pause/repeatUtil by name (explaining
    # what it must never call) -- a real violation would be executable Lua,
    # not prose in a comment.
    code_lines = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        # Drop a trailing inline comment (`code -- comment`), conservative:
        # only split on " -- " (space-dash-dash-space), matching this
        # project's own comment style throughout df-overseer-*.lua.
        code_part = line.split(" -- ", 1)[0]
        code_lines.append(code_part)
    code_only = "\n".join(code_lines)

    for forbidden in FORBIDDEN_CALL_SUBSTRINGS:
        assert forbidden not in code_only, (
            f"df-overseer-ledger.lua's CODE (not comments) references "
            f"{forbidden!r} -- its write path must never pause or wake "
            f"anything (handoffs/2026-09-23-attention-tiers-ingame.md item 4)"
        )


def test_ledger_never_reqscripts_clock():
    source = LEDGER_LUA.read_text(encoding="utf-8")
    code_lines = [l for l in source.splitlines() if not l.strip().startswith("--")]
    code_only = "\n".join(code_lines)
    assert "reqscript('df-overseer-clock')" not in code_only
    assert 'reqscript("df-overseer-clock")' not in code_only


def test_ledger_exposes_record_and_read_ledger_and_a_closest_distance_lookup():
    source = LEDGER_LUA.read_text(encoding="utf-8")
    assert "function record(" in source
    assert "function read_ledger(" in source
    assert "function ledger_closest_distance(" in source
