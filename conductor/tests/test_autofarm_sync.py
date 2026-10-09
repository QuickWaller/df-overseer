"""The autofarm sync phase (conductor/autofarm_sync.py, register 2026-10-09)."""
from __future__ import annotations

import asyncio

from conductor import autofarm_sync as af
from conductor.policy import load_policy


def row(tid, crop, units, state="synced"):
    return {"id": tid, "sync": "autofarm", "crop": crop, "want_units": units, "state": state}


STATUS = {"targets": [
    {"id": "bedrooms", "state": "open", "owner": "architect"},
    row("crop_default", "default", 10.0),
    row("crop_plump_helmet", "MUSHROOM_HELMET_PLUMP", 59.6),
    row("crop_sweet_pod", "POD_SWEET_POD", 0.0),
]}


class Caller:
    def __init__(self, status=STATUS, fail_set=False):
        self.calls, self.status, self.fail_set = [], status, fail_set

    async def __call__(self, tool, args):
        self.calls.append((tool, args))
        if tool == af.STATUS_TOOL:
            if self.status is None:
                raise RuntimeError("down")
            return self.status
        if self.fail_set:
            raise RuntimeError("refused")
        return {"ok": True}


def run(caller, **kw):
    enabled = kw.pop("enabled", True)
    kw.setdefault("held", False)
    return asyncio.run(af.run_autofarm_sync(caller, enabled, **kw))


def test_levels_come_from_synced_rows_rounded_with_the_default_target():
    rep = af.levels_from_status(STATUS)
    assert rep.default == 10 and rep.levels == {"MUSHROOM_HELMET_PLUMP": 60, "POD_SWEET_POD": 0}


def test_no_default_target_means_default_zero():
    rep = af.levels_from_status({"targets": [row("a", "X", 5)]})
    assert rep.default == 0 and rep.levels == {"X": 5}


def test_inert_unreadable_and_duplicate_rows_are_skipped_with_notes():
    rep = af.levels_from_status({"targets": [
        row("a", "X", 5), row("b", "X", 9), row("c", "Y", 1, state="inert"), row("d", "Z", None),
    ]})
    assert rep.levels == {"X": 5} and len(rep.notes) == 3


def test_the_sync_applies_levels_through_autofarm_set():
    c = Caller()
    rep = run(c)
    assert rep.ran and c.calls[-1] == (af.SET_TOOL, {"default": "10", "levels": "MUSHROOM_HELMET_PLUMP=60,POD_SWEET_POD=0"})


def test_nothing_is_written_until_a_crop_target_exists():
    c = Caller({"targets": [row("crop_default", "default", 50)]})
    rep = run(c)
    assert not rep.ran and rep.skipped and [t for t, _ in c.calls] == [af.STATUS_TOOL]


def test_an_operator_hold_or_policy_off_blocks_without_a_read():
    for kw in ({"held": True}, {"enabled": False}):
        c = Caller()
        rep = run(c, **kw)
        assert not rep.ran and c.calls == []


def test_a_failed_read_or_write_is_total():
    assert not run(Caller(None)).ran
    rep = run(Caller(fail_set=True))
    assert not rep.ran and rep.error == "refused"


def test_a_dry_run_writes_nothing():
    c = Caller()
    assert run(c, dry_run=True).skipped == "dry run" and all(t == af.STATUS_TOOL for t, _ in c.calls)


def test_policy_ships_the_sync_on():
    assert load_policy().autofarm_sync.enabled is True
