"""conductor/status.py: the status JSON snapshot, written atomically, and
that a real escalation logs loudly at ERROR."""

from __future__ import annotations

import json
import logging

from conductor.cycle import CycleResult
from conductor.status import log_cycle, status_from_cycle, write_status
from conductor.triage import Signals


def _result(**overrides) -> CycleResult:
    base = dict(
        cycle_index=1, game_tick=1000, game_tick_error=None, signals=Signals(),
        clock_level="full_speed",
        roles_woken=(), clock_changes=[], role_runs=[], tripwire=None, escalated=False,
        unexecuted=[], archived_path=None, dry_run=False,
    )
    base.update(overrides)
    return CycleResult(**base)


def test_status_from_cycle_carries_the_expected_fields():
    status = status_from_cycle(_result(roles_woken=("architect",)), state="running")
    assert status["state"] == "running"
    assert status["last_cycle"]["cycle_index"] == 1
    assert status["last_cycle"]["roles_woken"] == ["architect"]
    assert status["tripwire"] is None
    assert status["escalated"] is False
    assert status["updated_at"]


def test_write_status_round_trips(tmp_path):
    path = tmp_path / "status.json"
    status = status_from_cycle(_result())
    write_status(path, status)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["last_cycle"]["cycle_index"] == 1


def test_write_status_creates_the_parent_directory(tmp_path):
    path = tmp_path / "nested" / "status.json"
    write_status(path, {"state": "running"})
    assert path.is_file()


def test_write_status_leaves_no_stray_temp_file(tmp_path):
    path = tmp_path / "status.json"
    write_status(path, {"state": "running"})
    leftovers = [p for p in tmp_path.iterdir() if p != path]
    assert leftovers == []


def test_write_status_overwrites_cleanly(tmp_path):
    path = tmp_path / "status.json"
    write_status(path, {"state": "starting"})
    write_status(path, {"state": "running"})
    assert json.loads(path.read_text(encoding="utf-8"))["state"] == "running"


def test_log_cycle_escalation_logs_at_error(caplog):
    result = _result(
        tripwire={"reason": "hunger_critical", "tick": 1, "detail": "x"}, escalated=True,
    )
    with caplog.at_level(logging.ERROR, logger="conductor.status"):
        log_cycle(result)
    assert any(rec.levelno == logging.ERROR and "ESCALATION" in rec.message for rec in caplog.records)


def test_log_cycle_a_handled_tripwire_logs_at_warning_not_error(caplog):
    result = _result(
        tripwire={"reason": "hunger_critical", "tick": 1, "detail": "x"}, escalated=False,
    )
    with caplog.at_level(logging.WARNING, logger="conductor.status"):
        log_cycle(result)
    assert any(rec.levelno == logging.WARNING for rec in caplog.records)
    assert not any(rec.levelno == logging.ERROR for rec in caplog.records)


def test_log_cycle_an_ordinary_cycle_logs_at_info_only(caplog):
    result = _result(roles_woken=("architect",))
    with caplog.at_level(logging.INFO, logger="conductor.status"):
        log_cycle(result)
    assert any(rec.levelno == logging.INFO for rec in caplog.records)
    assert not any(rec.levelno >= logging.WARNING for rec in caplog.records)


def test_status_from_cycle_carries_game_tick_error():
    """handoffs/2026-09-23-conductor-game-tick.md: a null tick must be
    distinguishable, from status.json alone, from "the tick genuinely could
    not be read this cycle" vs "the tick really is None" -- the old code
    made those look identical."""
    status = status_from_cycle(_result(game_tick=None, game_tick_error="in_game_date missing"))
    assert status["last_cycle"]["game_tick"] is None
    assert status["last_cycle"]["game_tick_error"] == "in_game_date missing"


def test_status_from_cycle_game_tick_error_is_none_on_a_normal_cycle():
    status = status_from_cycle(_result())
    assert status["last_cycle"]["game_tick_error"] is None


def test_log_cycle_an_unreadable_tick_logs_at_error(caplog):
    result = _result(game_tick=None, game_tick_error="in_game_date does not match")
    with caplog.at_level(logging.ERROR, logger="conductor.status"):
        log_cycle(result)
    assert any(
        rec.levelno == logging.ERROR and "game_tick could not be read" in rec.message
        for rec in caplog.records
    )


def test_log_cycle_an_unreadable_tick_logs_error_even_on_an_otherwise_quiet_cycle(caplog):
    """An unreadable tick must be loud even when nothing else about the
    cycle would have warranted more than INFO -- it silently disables both
    time-based wake reasons, so it is never allowed to hide behind an
    otherwise-quiet cycle's own INFO line."""
    result = _result(game_tick=None, game_tick_error="boom", roles_woken=())
    with caplog.at_level(logging.INFO, logger="conductor.status"):
        log_cycle(result)
    assert any(rec.levelno == logging.ERROR for rec in caplog.records)


def test_log_cycle_an_ordinary_cycle_escalation_with_no_tripwire_logs_at_error(caplog):
    """Fix 3, handoffs/2026-09-22-loop-conductor-fixes.md: conductor/cycle.py
    can now pause the fort from an escalation during an ORDINARY cycle (no
    tripwire latched), which must not silently fall through to the INFO
    branch just because result.tripwire is None."""
    result = _result(tripwire=None, escalated=True, roles_woken=("overseer",))
    with caplog.at_level(logging.ERROR, logger="conductor.status"):
        log_cycle(result)
    assert any(rec.levelno == logging.ERROR and "ESCALATION" in rec.message for rec in caplog.records)
