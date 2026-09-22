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
        cycle_index=1, game_tick=1000, signals=Signals(), clock_level="full_speed",
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
