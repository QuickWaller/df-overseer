"""conductor/archive.py: one directory per cycle, the daily cost total."""

from __future__ import annotations

import json

import pytest

from conductor.archive import CycleArchive


def test_write_cycle_creates_the_expected_files(tmp_path):
    archive = CycleArchive(tmp_path / "cycles")
    cycle_dir = archive.write_cycle(
        1,
        summary={"game_tick": 1000, "clock": "full_speed", "roles_woken": ["architect"]},
        briefings={"architect": {"role": "architect", "wake_reason": "migrant_wave"}},
        clock_changes=[{"tool": "clock.set-speed", "args": {"fps": 100}}],
        role_runs=[{"role": "architect", "ok": True, "cost_usd": 0.01}],
        started_at="20260922T120000Z",
    )
    assert cycle_dir.name == "cycle-000001-20260922T120000Z"
    assert (cycle_dir / "summary.json").is_file()
    assert (cycle_dir / "briefings.json").is_file()
    assert (cycle_dir / "clock_changes.json").is_file()
    assert (cycle_dir / "run-architect.json").is_file()

    summary = json.loads((cycle_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["game_tick"] == 1000

    run = json.loads((cycle_dir / "run-architect.json").read_text(encoding="utf-8"))
    assert run["cost_usd"] == 0.01


def test_write_cycle_with_no_role_runs_still_writes_the_cycle_files(tmp_path):
    archive = CycleArchive(tmp_path / "cycles")
    cycle_dir = archive.write_cycle(
        1, summary={"clock": "full_speed"}, briefings={}, clock_changes=[], role_runs=[],
    )
    assert (cycle_dir / "summary.json").is_file()
    assert list(cycle_dir.glob("run-*.json")) == []


def test_cycle_dir_names_are_distinct_across_different_started_at(tmp_path):
    archive = CycleArchive(tmp_path / "cycles")
    a = archive.cycle_dir(1, started_at="20260922T120000Z")
    b = archive.cycle_dir(1, started_at="20260922T120005Z")  # a restart re-using index 1
    assert a != b


def test_append_daily_cost_accumulates(tmp_path):
    archive = CycleArchive(tmp_path / "cycles")
    total1 = archive.append_daily_cost("2026-09-22", 0.006843)
    assert total1 == 0.006843
    total2 = archive.append_daily_cost("2026-09-22", 0.003)
    assert total2 == pytest.approx(0.009843)
    assert archive.daily_cost("2026-09-22") == pytest.approx(0.009843)


def test_daily_cost_of_an_untouched_date_is_zero(tmp_path):
    archive = CycleArchive(tmp_path / "cycles")
    assert archive.daily_cost("2026-01-01") == 0.0


def test_daily_cost_is_scoped_per_date(tmp_path):
    archive = CycleArchive(tmp_path / "cycles")
    archive.append_daily_cost("2026-09-22", 1.0)
    archive.append_daily_cost("2026-09-23", 5.0)
    assert archive.daily_cost("2026-09-22") == 1.0
    assert archive.daily_cost("2026-09-23") == 5.0


def test_unknown_cost_is_counted_not_recorded_as_zero(tmp_path):
    archive = CycleArchive(tmp_path / "cycles")
    assert archive.append_daily_cost("2026-09-25", 0.02) == pytest.approx(0.02)
    assert archive.append_daily_cost("2026-09-25", None) == pytest.approx(0.02)
    assert archive.daily_cost("2026-09-25") == pytest.approx(0.02)
    assert archive.daily_unknown_runs("2026-09-25") == 1
    assert archive.daily_unknown_runs("2026-01-01") == 0


def test_a_none_cost_serialises_as_null_in_the_run_file(tmp_path):
    archive = CycleArchive(tmp_path / "cycles")
    d = archive.write_cycle(
        1, summary={}, briefings={}, clock_changes=[],
        role_runs=[{"role": "overseer", "ok": False, "cost_usd": None}],
    )
    assert json.loads((d / "run-overseer.json").read_text(encoding="utf-8"))["cost_usd"] is None
