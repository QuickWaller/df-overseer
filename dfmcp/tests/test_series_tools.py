"""Direct, transport-free tests of `dfmcp.series_tools`, in the same style
as `dfmcp/tests/test_doctrine_tools.py`: this module imports nothing from
`mcp` (the SDK), only `dfmcp.series_tools` and `dfseries` directly, so it
runs under the ambient environment too, not only `.venv-dfmcp`.

Fixture data is hand-built JSONL, imported through the real
`dfseries.importer.import_file` (the same path production data takes), never
copied from a real sampler run -- `handoffs/2026-09-19-dfseries-resets.md`'s
own real-file numbers (unit:192's exact-tick thirst reset at abs_tick
12373521) are reused directly in one fixture as a cross-check, since that is
the exact answer `dfseries` itself already proved correct.

The property under test throughout, per this stream's brief
(`handoffs/2026-09-19-series-mcp-tools.md`): **every qualifier dfseries
produces survives to the tool's output unflattened** -- sample counts, tick
spans, skipped nulls, metric kind, exact_tick vs interval_bounded, an
unavailable reason never rendered as a number, a superseded read flagged,
and a null value never rendered as 0.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dfmcp import series_tools
from dfseries import importer, store

pytestmark = pytest.mark.asyncio


# --------------------------------------------------------------------------
# Fixture data: hand-written JSONL, imported through the real importer
# --------------------------------------------------------------------------


def _record(timeline_id, timeline_start_abs_tick, abs_tick, wall_utc, metrics_list):
    return {
        "v": 1,
        "timeline_id": timeline_id,
        "timeline_start_abs_tick": timeline_start_abs_tick,
        "abs_tick": abs_tick,
        "cur_year": 0,
        "cur_year_tick": abs_tick,
        "wall_utc": wall_utc,
        "sampler_version": "test",
        "metrics": metrics_list,
    }


def _build_db(tmp_path: Path, name: str, records: list[dict]) -> Path:
    """Write `records` as JSONL and import them into a fresh sqlite3 file at
    `tmp_path / name`, through the real `dfseries.importer.import_file` --
    never hand-inserted rows, so a fixture proves what a real sampler/
    importer run would actually produce."""
    jsonl = tmp_path / f"{name}.jsonl"
    jsonl.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    db_path = tmp_path / f"{name}.series.sqlite3"
    with store.connect(db_path) as conn:
        result = importer.import_file(conn, jsonl)
        assert not result.had_problems, result
    return db_path


@pytest.fixture()
def thirst_db(tmp_path) -> Path:
    """Three citizens over two samples 1200 ticks apart: unit:192 drinks
    (33722 -> 1085, the exact real numbers from
    handoffs/2026-09-19-dfseries-resets.md's real-file validation, reset
    dating to abs_tick 1200 - 1085 = 115 in this fixture's own tick space),
    unit:193 never resets (steady +1200/tick), unit:194 has only the first
    reading (a rate needs two, so this covers the too-few-samples case)."""
    return _build_db(tmp_path, "thirst", [
        _record("t1", 0, 0, "2026-09-19T08:00:00Z", [
            {"subject": "unit:192", "metric": "thirst_timer", "value": 33722, "unit": "ticks"},
            {"subject": "unit:193", "metric": "thirst_timer", "value": 500, "unit": "ticks"},
            {"subject": "unit:194", "metric": "thirst_timer", "value": 200, "unit": "ticks"},
        ]),
        _record("t1", 0, 1200, "2026-09-19T08:01:00Z", [
            {"subject": "unit:192", "metric": "thirst_timer", "value": 1085, "unit": "ticks"},
            {"subject": "unit:193", "metric": "thirst_timer", "value": 1700, "unit": "ticks"},
        ]),
    ])


@pytest.fixture()
def rollback_db(tmp_path) -> Path:
    """A rollback: t1 (wall 08:00) reaches abs_tick 2000, then t2 (wall
    09:00, later in real time) starts at abs_tick 1000, earlier than t1's
    last sample -- docs/TIMESERIES.md's exact definition of a rollback. t1's
    abs_tick=2000 sample becomes superseded; both timelines share a boundary
    sample at abs_tick=1000, where the tip (t2) wins the current-lineage tie
    (trend.py's own documented policy)."""
    return _build_db(tmp_path, "rollback", [
        _record("t1", 0, 0, "2026-09-19T08:00:00Z", [
            {"subject": "fort", "metric": "population", "value": 20, "unit": "citizens"},
        ]),
        _record("t1", 0, 1000, "2026-09-19T08:01:00Z", [
            {"subject": "fort", "metric": "population", "value": 21, "unit": "citizens"},
        ]),
        _record("t1", 0, 2000, "2026-09-19T08:02:00Z", [
            {"subject": "fort", "metric": "population", "value": 22, "unit": "citizens"},
        ]),
        _record("t2", 1000, 1000, "2026-09-19T09:00:00Z", [
            {"subject": "fort", "metric": "population", "value": 21, "unit": "citizens"},
        ]),
        _record("t2", 1000, 2000, "2026-09-19T09:01:00Z", [
            {"subject": "fort", "metric": "population", "value": 25, "unit": "citizens"},
        ]),
        _record("t2", 1000, 3000, "2026-09-19T09:02:00Z", [
            {"subject": "fort", "metric": "population", "value": 26, "unit": "citizens"},
        ]),
    ])


@pytest.fixture()
def failed_read_db(tmp_path) -> Path:
    """A single failed read: value null, error set, per
    docs/TIMESERIES.md's record format ('value is a number or null. null
    requires error.')."""
    return _build_db(tmp_path, "failed_read", [
        _record("t1", 0, 0, "2026-09-19T08:00:00Z", [
            {"subject": "item:DRINK", "metric": "stock", "value": None, "unit": "units",
             "error": "read failed: timeout"},
        ]),
    ])


@pytest.fixture()
def sleepiness_db(tmp_path) -> Path:
    """sleepiness_timer has no established between-reset rate
    (dfseries/metrics.py: rate_per_tick=None, "not established") -- an
    outright decrease is the only signal available, reported
    interval_bounded, never exact_tick."""
    return _build_db(tmp_path, "sleepiness", [
        _record("t1", 0, 0, "2026-09-19T08:00:00Z", [
            {"subject": "unit:192", "metric": "sleepiness_timer", "value": 49168, "unit": "ticks"},
        ]),
        _record("t1", 0, 1200, "2026-09-19T08:01:00Z", [
            {"subject": "unit:192", "metric": "sleepiness_timer", "value": 46048, "unit": "ticks"},
        ]),
    ])


async def _call(tool_id, role, arguments, *, series_db_path):
    return await series_tools.call(tool_id, role, arguments, series_db_path=series_db_path)


# ==========================================================================
# series.timelines
# ==========================================================================


class TestTimelines:
    async def test_single_timeline_is_the_tip(self, thirst_db):
        text, structured = await _call(series_tools.SERIES_TIMELINES, "overseer", {}, series_db_path=thirst_db)
        assert structured["count"] == 1
        tl = structured["timelines"][0]
        assert tl["timeline_id"] == "t1"
        assert tl["is_current_tip"] is True
        assert tl["cutoff_abs_tick"] is None
        assert 'is_current_tip="true"' in text

    async def test_rollback_marks_predecessor_not_tip_with_its_cutoff(self, rollback_db):
        _text, structured = await _call(series_tools.SERIES_TIMELINES, "overseer", {}, series_db_path=rollback_db)
        by_id = {t["timeline_id"]: t for t in structured["timelines"]}
        assert by_id["t1"]["is_current_tip"] is False
        assert by_id["t1"]["cutoff_abs_tick"] == 1000  # t2's start_abs_tick
        assert by_id["t2"]["is_current_tip"] is True
        assert by_id["t2"]["cutoff_abs_tick"] is None

    async def test_rejects_unexpected_argument(self, thirst_db):
        with pytest.raises(series_tools.SeriesToolError):
            await _call(series_tools.SERIES_TIMELINES, "overseer", {"subject": "fort"}, series_db_path=thirst_db)


# ==========================================================================
# series.get
# ==========================================================================


class TestGet:
    async def test_readings_carry_every_field_unflattened(self, thirst_db):
        _text, structured = await _call(
            series_tools.SERIES_GET, "overseer", {"subject": "unit:192", "metric": "thirst_timer"},
            series_db_path=thirst_db,
        )
        assert structured["metric_kind"] == "resetting_counter"
        assert structured["rate_per_tick"] == 1.0
        assert structured["reset_to_zero_verified"] is True
        assert "unit:192" in structured["rate_evidence"] or len(structured["rate_evidence"]) > 0
        readings = structured["readings"]
        assert [r["abs_tick"] for r in readings] == [0, 1200]
        assert readings[0]["value"] == 33722
        assert readings[1]["value"] == 1085
        for r in readings:
            assert set(r) == {"abs_tick", "value", "unit", "error", "timeline_id", "superseded"}

    async def test_a_null_value_is_never_rendered_as_zero(self, failed_read_db):
        text, structured = await _call(
            series_tools.SERIES_GET, "overseer", {"subject": "item:DRINK", "metric": "stock"},
            series_db_path=failed_read_db,
        )
        reading = structured["readings"][0]
        assert reading["value"] is None
        assert reading["error"] == "read failed: timeout"
        # Never silently coerced to 0 anywhere on the way to the wire.
        assert reading["value"] != 0
        assert 'value="null"' in text
        assert 'value="0"' not in text

    async def test_current_lineage_excludes_superseded_and_resolves_the_boundary_tie(self, rollback_db):
        _text, structured = await _call(
            series_tools.SERIES_GET, "overseer", {"subject": "fort", "metric": "population"},
            series_db_path=rollback_db,
        )
        assert structured["superseded_count"] == 0
        ticks = [r["abs_tick"] for r in structured["readings"]]
        assert ticks == [0, 1000, 2000, 3000]
        # abs_tick=1000: t2 (the tip) wins the boundary tie, per trend.py.
        boundary = next(r for r in structured["readings"] if r["abs_tick"] == 1000)
        assert boundary["timeline_id"] == "t2"
        assert boundary["value"] == 21

    async def test_all_lineage_surfaces_the_superseded_row_and_says_so(self, rollback_db):
        text, structured = await _call(
            series_tools.SERIES_GET, "overseer",
            {"subject": "fort", "metric": "population", "lineage": "all"},
            series_db_path=rollback_db,
        )
        assert structured["superseded_count"] == 1
        superseded_rows = [r for r in structured["readings"] if r["superseded"]]
        assert len(superseded_rows) == 1
        assert superseded_rows[0]["abs_tick"] == 2000
        assert superseded_rows[0]["timeline_id"] == "t1"
        assert 'superseded_count="1"' in text

    async def test_window_bounds_are_applied(self, thirst_db):
        _text, structured = await _call(
            series_tools.SERIES_GET, "overseer",
            {"subject": "unit:192", "metric": "thirst_timer", "start_abs_tick": 1200},
            series_db_path=thirst_db,
        )
        assert [r["abs_tick"] for r in structured["readings"]] == [1200]

    async def test_unknown_subject_returns_empty_not_an_error(self, thirst_db):
        _text, structured = await _call(
            series_tools.SERIES_GET, "overseer", {"subject": "unit:999", "metric": "thirst_timer"},
            series_db_path=thirst_db,
        )
        assert structured["readings"] == []

    async def test_missing_required_field_is_rejected(self, thirst_db):
        with pytest.raises(series_tools.SeriesToolError):
            await _call(series_tools.SERIES_GET, "overseer", {"subject": "unit:192"}, series_db_path=thirst_db)

    async def test_bad_lineage_is_rejected(self, thirst_db):
        with pytest.raises(series_tools.SeriesToolError) as exc:
            await _call(
                series_tools.SERIES_GET, "overseer",
                {"subject": "unit:192", "metric": "thirst_timer", "lineage": "some_branch"},
                series_db_path=thirst_db,
            )
        assert "lineage" in str(exc.value)

    async def test_wrong_type_for_start_abs_tick_is_rejected(self, thirst_db):
        with pytest.raises(series_tools.SeriesToolError):
            await _call(
                series_tools.SERIES_GET, "overseer",
                {"subject": "unit:192", "metric": "thirst_timer", "start_abs_tick": "0"},
                series_db_path=thirst_db,
            )

    async def test_unexpected_argument_is_rejected(self, thirst_db):
        with pytest.raises(series_tools.SeriesToolError) as exc:
            await _call(
                series_tools.SERIES_GET, "overseer",
                {"subject": "unit:192", "metric": "thirst_timer", "role": "overseer"},
                series_db_path=thirst_db,
            )
        assert "role" in str(exc.value)


# ==========================================================================
# series.latest
# ==========================================================================


class TestLatest:
    async def test_found_reading(self, thirst_db):
        _text, structured = await _call(
            series_tools.SERIES_LATEST, "overseer", {"subject": "unit:192", "metric": "thirst_timer"},
            series_db_path=thirst_db,
        )
        assert structured["found"] is True
        assert structured["reading"]["abs_tick"] == 1200
        assert structured["reading"]["value"] == 1085

    async def test_not_found_is_distinct_from_a_null_value(self, thirst_db, failed_read_db):
        _text, no_data = await _call(
            series_tools.SERIES_LATEST, "overseer", {"subject": "unit:999", "metric": "thirst_timer"},
            series_db_path=thirst_db,
        )
        assert no_data["found"] is False
        assert no_data["reading"] is None

        _text2, failed_read = await _call(
            series_tools.SERIES_LATEST, "overseer", {"subject": "item:DRINK", "metric": "stock"},
            series_db_path=failed_read_db,
        )
        assert failed_read["found"] is True  # a reading exists...
        assert failed_read["reading"]["value"] is None  # ...but its value is null
        assert failed_read["reading"]["error"] == "read failed: timeout"

    async def test_states_metric_kind(self, thirst_db):
        _text, structured = await _call(
            series_tools.SERIES_LATEST, "overseer", {"subject": "unit:193", "metric": "thirst_timer"},
            series_db_path=thirst_db,
        )
        assert structured["metric_kind"] == "resetting_counter"
        assert structured["rate_per_tick"] == 1.0


# ==========================================================================
# series.rate
# ==========================================================================


class TestRate:
    async def test_measured_rate_with_full_qualifiers(self, thirst_db):
        text, structured = await _call(
            series_tools.SERIES_RATE, "overseer", {"subject": "unit:193", "metric": "thirst_timer"},
            series_db_path=thirst_db,
        )
        assert structured["status"] == "measured"
        assert structured["value"] == pytest.approx(1.0)
        assert structured["sample_count"] == 2
        assert structured["tick_span"] == 1200
        assert structured["skipped_nulls"] == 0
        assert structured["segment"] == "endpoint"
        assert structured["metric_kind"] == "resetting_counter"
        assert 'sample_count="2"' in text

    async def test_unavailable_across_a_reset_is_never_a_number(self, thirst_db):
        text, structured = await _call(
            series_tools.SERIES_RATE, "overseer", {"subject": "unit:192", "metric": "thirst_timer"},
            series_db_path=thirst_db,
        )
        assert structured["status"] == "unavailable"
        assert structured["value"] is None
        assert structured["reason"] is not None and len(structured["reason"]) > 0
        assert 'value="null"' in text
        assert 'value="0"' not in text
        # sample_count and skipped_nulls still reported even when unavailable.
        assert structured["sample_count"] == 2

    async def test_too_few_samples_is_unavailable_with_a_reason(self, thirst_db):
        _text, structured = await _call(
            series_tools.SERIES_RATE, "overseer", {"subject": "unit:194", "metric": "thirst_timer"},
            series_db_path=thirst_db,
        )
        assert structured["status"] == "unavailable"
        assert structured["value"] is None
        assert structured["sample_count"] == 1
        assert "reason" in structured and structured["reason"]

    async def test_queried_all_timelines_flag(self, rollback_db):
        _text, current = await _call(
            series_tools.SERIES_RATE, "overseer", {"subject": "fort", "metric": "population"},
            series_db_path=rollback_db,
        )
        assert current["queried_all_timelines"] is False

        _text2, all_lineage = await _call(
            series_tools.SERIES_RATE, "overseer",
            {"subject": "fort", "metric": "population", "lineage": "all"},
            series_db_path=rollback_db,
        )
        assert all_lineage["queried_all_timelines"] is True


# ==========================================================================
# series.resets
# ==========================================================================


class TestResets:
    async def test_exact_tick_reset_matches_the_real_files_own_numbers(self, thirst_db):
        text, structured = await _call(
            series_tools.SERIES_RESETS, "overseer", {"subject": "unit:192", "metric": "thirst_timer"},
            series_db_path=thirst_db,
        )
        assert structured["metric_kind"] == "resetting_counter"
        assert structured["reset_to_zero_verified"] is True
        assert len(structured["events"]) == 1
        event = structured["events"][0]
        assert event["kind"] == "exact_tick"
        # This fixture's tick space is the real file's shifted to start at 0:
        # 1200 - 1085 = 115, the same arithmetic that dated the real reset
        # to 12374606 - 1085 = 12373521 in handoffs/2026-09-19-dfseries-resets.md.
        assert event["abs_tick"] == 115
        assert structured["anomalies"] == []
        assert 'kind="exact_tick"' in text

    async def test_no_reset_citizen_has_no_events(self, thirst_db):
        _text, structured = await _call(
            series_tools.SERIES_RESETS, "overseer", {"subject": "unit:193", "metric": "thirst_timer"},
            series_db_path=thirst_db,
        )
        assert structured["events"] == []
        assert structured["anomalies"] == []

    async def test_interval_bounded_for_an_unestablished_rate_metric(self, sleepiness_db):
        text, structured = await _call(
            series_tools.SERIES_RESETS, "overseer", {"subject": "unit:192", "metric": "sleepiness_timer"},
            series_db_path=sleepiness_db,
        )
        assert structured["metric_kind"] == "resetting_counter"
        assert structured["rate_per_tick"] is None
        assert len(structured["events"]) == 1
        event = structured["events"][0]
        assert event["kind"] == "interval_bounded"
        assert event["abs_tick"] is None  # never a guessed tick
        assert 'abs_tick="null"' in text

    async def test_level_metric_returns_empty_events_and_states_its_kind(self, rollback_db):
        _text, structured = await _call(
            series_tools.SERIES_RESETS, "overseer", {"subject": "fort", "metric": "population"},
            series_db_path=rollback_db,
        )
        assert structured["metric_kind"] == "level"
        assert structured["events"] == []
        assert structured["anomalies"] == []


# ==========================================================================
# series.dwarf_day_events
# ==========================================================================


class TestDwarfDayEvents:
    async def test_event_count_and_dwarf_days_are_prominent_and_a_caution_appears(self, thirst_db):
        text, structured = await _call(
            series_tools.SERIES_DWARF_DAY_EVENTS, "overseer", {"metric": "thirst_timer"},
            series_db_path=thirst_db,
        )
        assert structured["event_count"] == 1
        assert structured["exact_tick_events"] == 1
        assert structured["interval_bounded_events"] == 0
        assert structured["label"] == "drinking events per dwarf-day"
        assert structured["caution"] is not None
        assert "1" in structured["caution"]
        # event_count and dwarf_days_observed are the first two attributes.
        header = text.splitlines()[0]
        assert header.index("event_count") < header.index("label")

    async def test_events_per_dwarf_day_is_null_not_zero_when_no_dwarf_days_observed(self, failed_read_db):
        """failed_read_db has no unit:* subjects at all for thirst_timer, so
        dwarf_days_observed is 0 and events_per_dwarf_day must be null, per
        aggregate.py's own 'never a guess in its place' rule -- never 0,
        which would misreport as 'zero events per day' rather than 'no data
        to compute a rate from'."""
        text, structured = await _call(
            series_tools.SERIES_DWARF_DAY_EVENTS, "overseer", {"metric": "thirst_timer"},
            series_db_path=failed_read_db,
        )
        assert structured["dwarf_days_observed"] == 0
        assert structured["events_per_dwarf_day"] is None
        assert structured["events_per_dwarf_day_status"] == "unavailable"
        assert structured["events_per_dwarf_day_reason"]
        assert 'events_per_dwarf_day="null"' in text
        assert 'events_per_dwarf_day="0"' not in text


# ==========================================================================
# Database absent: fails loudly, never a silent empty result
# ==========================================================================


class TestDatabaseAbsent:
    async def test_missing_database_is_refused_loudly(self, tmp_path):
        missing = tmp_path / "does-not-exist.series.sqlite3"
        with pytest.raises(series_tools.SeriesToolError) as exc:
            await _call(series_tools.SERIES_TIMELINES, "overseer", {}, series_db_path=missing)
        assert "not found" in str(exc.value)
        assert str(missing) in str(exc.value)

    async def test_missing_database_is_not_silently_created(self, tmp_path):
        """The exact failure mode this refusal exists to prevent:
        dfseries.store.connect would otherwise create an empty, schema-valid
        database at any path that does not yet exist, which would then
        serve empty history indistinguishable from 'this fort has recorded
        nothing'."""
        missing = tmp_path / "does-not-exist.series.sqlite3"
        with pytest.raises(series_tools.SeriesToolError):
            await _call(series_tools.SERIES_TIMELINES, "overseer", {}, series_db_path=missing)
        assert not missing.exists()

    async def test_default_path_is_a_plain_string_not_a_windows_mangled_path(self):
        """See series_tools.py's own module docstring: this constant must
        stay a plain str (never wrapped in pathlib.Path at module load time)
        so it is never silently rewritten with backslashes on a Windows
        workstation."""
        assert isinstance(series_tools.DEFAULT_SERIES_DB_PATH, str)
        assert series_tools.DEFAULT_SERIES_DB_PATH.startswith("/var/lib/dfseries/")


# ==========================================================================
# Roster wiring: the real registry + roster, per-role grant/withhold
# ==========================================================================


class TestRosterWiring:
    """Proves the deliberate per-role choice recorded in agents/*/tools.yaml
    actually holds, through the real registry/roster boundary -- not just
    that this module's own functions work in isolation. Same pattern as
    test_doctrine_tools.py's own TestRosterWiring."""

    @pytest.fixture(scope="class")
    def registry(self):
        from dfmcp.doctrine_tools import NATIVE_TOOLS as DOCTRINE_NATIVE_TOOLS
        from dfmcp.gotchas_tools import NATIVE_TOOLS as GOTCHAS_NATIVE_TOOLS
        from dfmcp.queue_tools import NATIVE_TOOLS as QUEUE_NATIVE_TOOLS
        from dfmcp.registry import load_registry

        return load_registry(
            native_tools={**QUEUE_NATIVE_TOOLS, **DOCTRINE_NATIVE_TOOLS, **series_tools.NATIVE_TOOLS,
                **GOTCHAS_NATIVE_TOOLS}
        )

    @pytest.fixture(scope="class")
    def roster(self, registry):
        from dfmcp.roles import load_roster

        return load_roster(registry)

    @pytest.mark.parametrize("tool_id", series_tools.NATIVE_TOOL_IDS)
    async def test_overseer_is_granted_every_series_tool(self, roster, tool_id):
        allowed, _reason = roster.check("overseer", tool_id)
        assert allowed

    @pytest.mark.parametrize("tool_id", series_tools.NATIVE_TOOL_IDS)
    async def test_consultant_is_granted_every_series_tool(self, roster, tool_id):
        allowed, _reason = roster.check("consultant", tool_id)
        assert allowed

    @pytest.mark.parametrize("tool_id", series_tools.NATIVE_TOOL_IDS)
    async def test_architect_is_withheld_from_every_series_tool(self, roster, tool_id):
        allowed, reason = roster.check("architect", tool_id)
        assert not allowed
        assert "series" in reason.lower() or "allowlist" in reason.lower()

    @pytest.mark.parametrize("tool_id", series_tools.NATIVE_TOOL_IDS)
    async def test_no_series_tool_mutates_or_is_sole_writer_only(self, registry, tool_id):
        tool = registry.get(tool_id)
        assert tool.mutates is False
        assert tool.sole_writer_only is False

    @pytest.mark.parametrize("tool_id", series_tools.NATIVE_TOOL_IDS)
    async def test_every_series_tool_is_player_derivable_not_omniscient(self, registry, tool_id):
        """Deliberate, per this module's docstring: player_derivable, never
        omitted like doctrine.get's (these DO read live fort state) and
        never omniscient (which roles.py rule 7 would then refuse for every
        role, including the sole writer -- the whole point of this
        module)."""
        tool = registry.get(tool_id)
        assert tool.knowledge_scope == "player_derivable"
