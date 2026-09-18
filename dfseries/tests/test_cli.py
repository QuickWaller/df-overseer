"""A smoke test for `dfseries/cli.py`: import a fixture file through the
real CLI entry point, then read it back through `series`, `latest`, `rate`
and `timelines`. Not exhaustive (the layers underneath already have their
own tests); this only proves the CLI wiring itself works end to end.
"""

from __future__ import annotations

import json

import pytest

from dfseries import cli


def _write(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def _record(abs_tick, value):
    return {
        "v": 1, "timeline_id": "t1", "timeline_start_abs_tick": 0, "abs_tick": abs_tick,
        "cur_year": 0, "cur_year_tick": abs_tick, "wall_utc": "2026-09-19T08:00:00Z",
        "sampler_version": "test",
        "metrics": [{"subject": "fort", "metric": "population", "value": value, "unit": "citizens"}],
    }


def test_cli_import_series_latest_rate_timelines(tmp_path, capsys):
    db = tmp_path / "cli.series.sqlite3"
    jsonl = tmp_path / "sample.jsonl"
    _write(jsonl, [_record(1000, 14), _record(2000, 15)])

    rc = cli.main(["import", str(db), str(jsonl)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "2 event(s)" in out

    rc = cli.main(["timelines", str(db)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "t1" in out and "current tip" in out

    rc = cli.main(["series", str(db), "fort", "population"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "1000: 14" in out
    assert "2000: 15" in out

    rc = cli.main(["latest", str(db), "fort", "population"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "2000: 15" in out

    rc = cli.main(["rate", str(db), "fort", "population"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "sample(s) used" in out


def test_cli_reports_no_data(tmp_path, capsys):
    db = tmp_path / "empty.series.sqlite3"
    rc = cli.main(["latest", str(db), "fort", "population"])
    assert rc == 0
    assert "no data" in capsys.readouterr().out


def _thirst_record(abs_tick, value):
    return {
        "v": 1, "timeline_id": "t1", "timeline_start_abs_tick": 0, "abs_tick": abs_tick,
        "cur_year": 0, "cur_year_tick": abs_tick, "wall_utc": "2026-09-19T08:00:00Z",
        "sampler_version": "test",
        "metrics": [{"subject": "unit:192", "metric": "thirst_timer", "value": value, "unit": "ticks"}],
    }


def test_cli_resets_reports_an_exact_tick_reset(tmp_path, capsys):
    db = tmp_path / "cli.series.sqlite3"
    jsonl = tmp_path / "thirst.jsonl"
    _write(jsonl, [_thirst_record(12373406, 33722), _thirst_record(12374606, 1085)])

    rc = cli.main(["import", str(db), str(jsonl)])
    assert rc == 0
    capsys.readouterr()

    rc = cli.main(["resets", str(db), "unit:192", "thirst_timer"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "resetting_counter" in out
    assert "reset at abs_tick 12373521" in out


def test_cli_rate_refuses_to_straddle_a_reset(tmp_path, capsys):
    db = tmp_path / "cli.series.sqlite3"
    jsonl = tmp_path / "thirst.jsonl"
    _write(jsonl, [_thirst_record(12373406, 33722), _thirst_record(12374606, 1085)])

    rc = cli.main(["import", str(db), str(jsonl)])
    assert rc == 0
    capsys.readouterr()

    rc = cli.main(["rate", str(db), "unit:192", "thirst_timer"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "unavailable" in out
    assert "12373521" in out


def test_cli_dwarf_day_reports_drinking_events_label(tmp_path, capsys):
    db = tmp_path / "cli.series.sqlite3"
    jsonl = tmp_path / "thirst.jsonl"
    _write(jsonl, [_thirst_record(12373406, 33722), _thirst_record(12374606, 1085)])

    rc = cli.main(["import", str(db), str(jsonl)])
    assert rc == 0
    capsys.readouterr()

    rc = cli.main(["dwarf-day", str(db), "thirst_timer"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "drinking events per dwarf-day" in out
    assert "1 event(s) (1 exact-tick" in out
