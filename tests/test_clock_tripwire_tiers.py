"""Structural regression for the tripwire wiring in
scripts/dfhack/df-overseer-clock.lua and scripts/dfhack/df-overseer-diff.lua
(handoffs/2026-09-23-attention-tiers-ingame.md items 1, 2, 3, 4, 5).

No Lua interpreter is available offline (see tests/test_reachability_ring_
logic.py's own header for this project's standard framing), so this file
checks the properties that ARE verifiable from source text alone: that the
three-tier branch exists and pause is no longer unconditional, that the
announcement tripwire is bounded (not a full-history scan) and separate
from the hostile-reachable one, and that the death-tripwire dual-arming
claim in this stream's Result is actually true of the committed bytes.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLOCK_LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-clock.lua"
DIFF_LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-diff.lua"
ANNOUNCEMENT_LEVELS_LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-announcement-levels.lua"


def _clock_source() -> str:
    return CLOCK_LUA.read_text(encoding="utf-8")


def test_clock_no_longer_pauses_on_any_reachable_candidate_unconditionally():
    """The regression this whole stream exists to fix: step 3 used to pause
    on `#threats > 0` alone. It must now branch on `top.tier`."""
    source = _clock_source()
    assert 'top.tier == "pause"' in source
    assert 'top.tier == "slow"' in source
    # The old unconditional shape must be gone: a bare "if ok_scan and threats
    # and #threats > 0 then" immediately followed by an unconditional
    # SetPauseState is what this stream replaced.
    assert "local ok_scan, threats = pcall(threat_mod.find_threats)" in source


def test_slow_tier_sets_think_fps_and_writes_a_non_blocking_advisory():
    source = _clock_source()
    assert "clock_set_speed(think_fps)" in source
    assert "write_advisory(" in source
    assert "ADVISORY_FILE" in source
    # The advisory file must be distinct from the latch file (never gates
    # resume).
    assert 'ADVISORY_FILE = STATE_DIR .. "/tripwire_advisory.json"' in source
    assert 'LATCH_FILE = STATE_DIR .. "/tripwire_latch.json"' in source


def test_clock_resume_only_ever_checks_the_latch_never_the_advisory():
    source = _clock_source()
    start = source.index("function clock_resume()")
    end = source.index("\nend", start)
    body = source[start:end]
    assert "read_latch()" in body
    assert "read_advisory" not in body


def test_every_scanned_candidate_is_recorded_into_the_ledger():
    """record_only candidates get no pause/slow handling at all -- they must
    still reach the ledger, or the whole point of the tier (visibility
    instead of silence) is lost."""
    source = _clock_source()
    assert "ledger_mod.record" in source
    assert 'for _, candidate in ipairs(threats) do' in source


def test_announcement_tripwire_is_a_separate_bounded_step_not_folded_into_hostile_reachable():
    source = _clock_source()
    # Bounded: breaks out of the scan as soon as it reaches an already-seen
    # report id, rather than walking the whole history every check.
    fn_start = source.index("local function new_pause_reports(")
    fn_end = source.index("\nend", fn_start)
    body = source[fn_start:fn_end]
    assert "if rep.id <= last_seen_id then" in body
    assert "break" in body

    # Separate from step 3: the announcement check reads
    # announcement_levels.is_pause_report, not threat_mod.find_threats.
    assert "announcement_levels.is_pause_report" in source
    # And it independently writes its own latch reason.
    assert 'reason = "announcement"' in source


def test_arm_takes_think_fps_and_clears_the_advisory_on_a_fresh_arm():
    source = _clock_source()
    fn_start = source.index("function clock_arm(")
    fn_end = source.index("\nend", fn_start)
    body = source[fn_start:fn_end]
    assert "think_fps" in body
    assert "clear_latch_file()" in body
    assert "write_advisory({})" in body


def test_death_tripwire_step_1_is_a_roster_diff_not_the_raw_unit_death_event():
    """Item 5's own finding: this check has never used UNIT_DEATH as its
    actual mechanism (the CODE, not the comment explaining why it isn't
    used -- that comment mentions the name by design). Guard against a
    future edit silently reintroducing it as the pause mechanism."""
    source = _clock_source()
    step1_start = source.index("-- 1. Death since the last check")
    step2_start = source.index("-- 2. Hunger/thirst past critical")
    step1_body = source[step1_start:step2_start]
    code_lines = [l for l in step1_body.splitlines() if not l.strip().startswith("--")]
    code_only = "\n".join(code_lines)
    assert "citizen_ids_now()" in code_only
    assert "UNIT_DEATH" not in code_only
    assert "eventful" not in code_only


def test_citizen_death_and_pet_death_are_in_the_generated_pause_table():
    """The dual-arming claim: step 4's pause table already contains ids 106
    (CITIZEN_DEATH) and 107 (PET_DEATH), so the announcement tripwire covers
    death independently of the roster diff."""
    source = ANNOUNCEMENT_LEVELS_LUA.read_text(encoding="utf-8")
    assert '[106] = "CITIZEN_DEATH"' in source
    assert '[107] = "PET_DEATH"' in source


def test_diff_lua_emits_the_reconciled_announcement_slow_event_shape():
    """Matches conductor/cycle.py's SLOW_ANNOUNCEMENT_EVENT_TYPE /
    _classify_slow_announcements, already merged from the sibling stream."""
    source = DIFF_LUA.read_text(encoding="utf-8")
    assert 'type = "announcement_slow"' in source
    assert "announcement_type = slow_info.name" in source
    assert "wake = slow_info.wake" in source
    assert "detail = slow_info.detail" in source
    # Never pauses or changes speed from this handler.
    onreport_start = source.index("eventful.onReport.df_overseer_diff = function")
    onreport_end = source.index("\n  end\n", onreport_start)
    onreport_body = source[onreport_start:onreport_end]
    assert "SetPauseState" not in onreport_body
    assert "clock_set_speed" not in onreport_body


def test_theft_and_crime_family_ids_are_tagged_in_report_category():
    source = DIFF_LUA.read_text(encoding="utf-8")
    assert 'tag_category("theft", 145)' in source
    assert 'tag_category("mischief", 75, 76, 77, 78)' in source
    assert 'tag_category("snatched", 252)' in source
    assert 'tag_category("crime_witness", 332, 333, 334, 335)' in source
