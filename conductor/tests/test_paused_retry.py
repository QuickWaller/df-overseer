"""The paused-fort fallback (conductor/backoff.py `RetryClock`): tick-keyed
backoffs must still retry while the fort sits paused, and must not fire twice
once the tick moves again. Every test freezes the tick and drives a fake wall
clock."""

from __future__ import annotations

from conductor import backoff
from conductor.backoff import Backoff, RetryClock
from conductor.cursors import CursorStore
from conductor.plan_watch import PlanWatchState, REASON_STAGE, evaluate
from conductor.policy import load_policy
from conductor.tests.test_plan_watch import policy as plan_policy, status
from conductor.tests.test_roadmap_wake import rm, stage_wakes, with_roadmap

BASE = 12000
FROZEN = 12930359


class Wall:
    def __init__(self, t=1_000_000):
        self.t = t

    def __call__(self):
        return self.t


def clock(tmp_path, wall, seconds=900, ticks=BASE):
    return RetryClock(CursorStore(tmp_path / "cursors.json"), seconds, ticks, wall=wall)


def test_a_frozen_tick_does_not_advance_before_the_interval(tmp_path):
    w = Wall()
    c = clock(tmp_path, w)
    assert c.now(FROZEN) == FROZEN
    w.t += 899
    assert c.now(FROZEN) == FROZEN


def test_a_frozen_tick_advances_one_base_per_interval(tmp_path):
    w = Wall()
    c = clock(tmp_path, w)
    c.now(FROZEN)
    w.t += 900
    assert c.now(FROZEN) == FROZEN + BASE
    w.t += 900
    assert c.now(FROZEN) == FROZEN + 2 * BASE
    w.t += 100
    assert c.now(FROZEN) == FROZEN + 2 * BASE


def test_disabled_is_the_real_tick(tmp_path):
    w = Wall()
    c = clock(tmp_path, w, seconds=0)
    c.now(FROZEN)
    w.t += 10_000
    assert c.now(FROZEN) == FROZEN
    assert c.now(None) is None


def test_a_moving_tick_never_earns_offset_and_the_offset_never_goes_back(tmp_path):
    w = Wall()
    c = clock(tmp_path, w)
    c.now(FROZEN)
    w.t += 900
    assert c.now(FROZEN) == FROZEN + BASE            # paused: one bump
    w.t += 5000
    assert c.now(FROZEN + 50) == FROZEN + 50 + BASE  # resumed: monotone, no second bump
    w.t += 5000
    assert c.now(FROZEN + 100) == FROZEN + 100 + BASE


def test_a_tick_that_goes_backwards_resets_the_offset(tmp_path):
    w = Wall()
    c = clock(tmp_path, w)
    c.now(FROZEN)
    w.t += 900
    c.now(FROZEN)
    assert c.now(FROZEN - 5000) == FROZEN - 5000


def test_state_survives_between_cycles(tmp_path):
    w = Wall()
    clock(tmp_path, w).now(FROZEN)
    w.t += 900
    assert clock(tmp_path, w).now(FROZEN) == FROZEN + BASE


def test_a_dry_run_does_not_persist(tmp_path):
    w = Wall()
    store = CursorStore(tmp_path / "c.json")
    RetryClock(store, 900, BASE, wall=w).now(FROZEN)
    w.t += 900
    dry = RetryClock(store, 900, BASE, wall=w, persist=False)
    assert dry.now(FROZEN) == FROZEN + BASE
    assert dry.now(FROZEN) == FROZEN + BASE          # nothing saved, same answer
    assert RetryClock(store, 900, BASE, wall=w).now(FROZEN) == FROZEN + BASE


def test_the_shared_backoff_fires_on_the_retry_clock_with_the_tick_frozen(tmp_path):
    w = Wall()
    c = clock(tmp_path, w)
    rule = Backoff(BASE, 100800, 5)
    rec, due, _ = backoff.advance(None, c.now(FROZEN), rule)
    assert due and rec["wakes"] == 1
    fired = 0
    for _ in range(5):
        w.t += 900
        rec, due, _ = backoff.advance(rec, c.now(FROZEN), rule)
        fired += due
    # second wake after one base (one interval), third after two bases (two more)
    assert fired == 2 and rec["wakes"] == 3


def test_plan_watch_roadmap_retry_comes_while_paused_and_not_twice_when_the_tick_moves(tmp_path):
    w = Wall()
    c = clock(tmp_path, w)
    state = PlanWatchState()
    st = with_roadmap(status(), rm("hamlet"))

    def go(real):
        return evaluate(st, real, plan_policy(shortfall=False), state, None, retry_tick=c.now(real))

    assert len(stage_wakes(go(FROZEN))) == 1
    assert stage_wakes(go(FROZEN)) == []                 # same instant: no
    w.t += 900
    assert len(stage_wakes(go(FROZEN))) == 1             # paused for an interval: retry
    assert stage_wakes(go(FROZEN)) == []
    # the game resumes and a base's worth of real ticks pass: still inside the doubled wait
    w.t += 30
    assert stage_wakes(go(FROZEN + BASE)) == []
    assert state.roadmap.wakes == 2


def test_the_policy_file_turns_the_fallback_on():
    from pathlib import Path
    pol = load_policy(Path(__file__).resolve().parents[1] / "policy.yaml")
    assert pol.paused_retry_seconds > 0 and pol.paused_retry_ticks > 0
