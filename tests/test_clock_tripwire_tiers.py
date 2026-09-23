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


# ----------------------------------------------------------------------------
# handoffs/2026-09-23-slow-tier-clearing.md: the missing half of the slow
# tier. Live example: the Chair completion run's kea (theft_tag_close_range)
# stayed latched, unchanging, across all three windows, right through to the
# final paused read (evals/live/2026-09-23-chair-completion-run/README.md).


def _step3_body() -> str:
    source = _clock_source()
    start = source.index("-- 3. Hostile reachable")
    end = source.index("\n    -- 4. A newly-arrived announcement")
    return source[start:end]


def test_step3_clears_a_stale_slow_advisory_when_nothing_slow_or_worse_remains():
    """The regression this stream exists to fix: a slow-tier advisory that
    outlives the threat that set it. Clearing must be reachable both when
    the top candidate has downgraded to record_only and when the scan finds
    no candidates at all -- `top` is nil in that second case, so the branch
    must not require `top` to be truthy to fire."""
    body = _step3_body()
    assert 'elseif read_advisory() then' in body
    assert "clock_set_speed(read_base_fps())" in body
    assert "write_advisory({})" in body
    # The clearing branch must come after the pause/slow branches in the
    # same if/elseif chain (same scan, same cadence), not a separate check.
    pause_idx = body.index('top and top.tier == "pause"')
    slow_idx = body.index('top and top.tier == "slow"')
    clear_idx = body.index('elseif read_advisory() then')
    assert pause_idx < slow_idx < clear_idx


def test_step3_no_longer_requires_threats_nonempty_to_reach_the_tier_branch():
    """#threats == 0 must clear too (judgement call 2): the old `if #threats
    > 0 then` gate is gone, and `top` is looked up unconditionally so a
    nil top (no candidates) still reaches the clearing branch."""
    body = _step3_body()
    assert "if #threats > 0 then" not in body
    assert "local top = threats[1]" in body


def test_clearing_runs_at_the_same_cadence_as_setting_not_a_separate_one():
    """Judgement call 3: no second `fire_count %` gate anywhere in the
    clearing logic -- it lives inside the same `threat_check_every_n`
    branch that sets the advisory."""
    source = _clock_source()
    step3_start = source.index("-- 3. Hostile reachable")
    step4_start = source.index("\n    -- 4. A newly-arrived announcement")
    between = source[step3_start:step4_start]
    assert between.count("fire_count %") == 1


def test_base_fps_is_persisted_to_its_own_state_file_not_a_lua_local():
    """Judgement call 1: base_fps is captured once at arm time and read
    from a file (BASE_FPS_FILE), the same discipline LATCH_FILE/
    ADVISORY_FILE already use, and for the same reason (the header's own
    'why the latch is a file, not a Lua global') -- clock_clear runs as a
    separate CLI invocation and cannot see a value the check closure
    captured."""
    source = _clock_source()
    assert 'BASE_FPS_FILE = STATE_DIR .. "/base_fps.json"' in source
    assert "local function read_base_fps()" in source
    assert "local function write_base_fps(base_fps)" in source
    assert "DEFAULT_BASE_FPS = 100" in source


def test_clock_arm_takes_and_persists_base_fps():
    source = _clock_source()
    fn_start = source.index("function clock_arm(")
    header_end = source.index("\n", fn_start)
    assert "base_fps" in source[fn_start:header_end]
    fn_end = source.index("\nend", fn_start)
    body = source[fn_start:fn_end]
    assert "write_base_fps(base_fps)" in body
    # Persisted before the check_fn closure is created, and passed into it.
    write_idx = body.index("write_base_fps(base_fps)")
    check_fn_idx = body.index("make_check_fn(")
    assert write_idx < check_fn_idx
    assert "make_check_fn(hunger_critical, thirst_critical, threat_check_every_n, think_fps, base_fps)" in body


def test_clock_arm_validates_base_fps_range():
    source = _clock_source()
    fn_start = source.index("function clock_arm(")
    fn_end = source.index("\nend", fn_start)
    body = source[fn_start:fn_end]
    assert "base_fps < MIN_FPS or base_fps > MAX_FPS" in body


def test_clock_clear_also_clears_the_advisory_and_reports_both():
    """Judgement call 5: clear() now clears the slow-tier advisory too and
    restores base_fps, and its return value names what was actually
    cleared (had_latch, had_advisory) rather than only had_latch as
    before."""
    source = _clock_source()
    fn_start = source.index("function clock_clear()")
    fn_end = source.index("\nend", fn_start)
    body = source[fn_start:fn_end]
    assert "had_advisory" in body
    assert "read_advisory() ~= nil" in body
    assert "clock_set_speed(read_base_fps())" in body
    assert "write_advisory({})" in body
    assert "had_latch = had_latch, had_advisory = had_advisory" in body


def test_clock_status_exposes_base_fps():
    source = _clock_source()
    fn_start = source.index("function clock_status()")
    fn_end = source.index("\nend", fn_start)
    body = source[fn_start:fn_end]
    assert "base_fps = read_base_fps()" in body


def test_cli_dispatch_passes_base_fps_through_to_arm():
    source = _clock_source()
    assert 'clock_arm(args[2], args[3], args[4], args[5], args[6], args[7])' in source
    assert "BASE_FPS" in source
