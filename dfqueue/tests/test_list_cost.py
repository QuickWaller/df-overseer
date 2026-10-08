"""Cost from tokens at DeepSeek list rates (dfqueue/deepseek_pricing.yaml)."""

from __future__ import annotations

from datetime import datetime

import pytest

from dfqueue import wake_metrics as wm

P = wm.load_pricing()
FLASH = "deepseek/deepseek-v4-flash"
PRO = "deepseek/deepseek-v4-pro"
TOK = {"input": 1_000_000, "cache_read": 1_000_000, "output": 1_000_000, "reasoning": 5}
# 2026-10-07 is a Wednesday; 2026-10-10 a Saturday.
OFF = "2026-10-07T12:00:00+00:00"
PEAK = "2026-10-07T07:30:00+00:00"


def test_flash_off_peak_per_million():
    assert wm.list_cost_usd(TOK, OFF, FLASH, P) == pytest.approx(0.15 + 0.003 + 0.60)


def test_pro_off_peak_per_million():
    assert wm.list_cost_usd(TOK, OFF, PRO, P) == pytest.approx(0.66 + 0.022 + 1.98)


def test_peak_is_double():
    assert wm.list_cost_usd(TOK, PEAK, PRO, P) == pytest.approx(2 * (0.66 + 0.022 + 1.98))


@pytest.mark.parametrize("ts,peak", [
    ("2026-10-07T00:59:00+00:00", False), ("2026-10-07T01:00:00+00:00", True),
    ("2026-10-07T03:59:00+00:00", True), ("2026-10-07T04:00:00+00:00", False),
    ("2026-10-07T05:59:00+00:00", False), ("2026-10-07T06:00:00+00:00", True),
    ("2026-10-07T09:59:00+00:00", True), ("2026-10-07T10:00:00+00:00", False),
    ("2026-10-10T07:00:00+00:00", False),      # Saturday
    ("2026-10-11T07:00:00+00:00", False),      # Sunday
    ("2026-10-07T23:30:00-05:00", False),      # 04:30 UTC Thursday, off-peak
    ("2026-10-08T02:00:00+13:00", False),      # 13:00 UTC Wednesday, off-peak
    ("2026-10-07T03:00:00-05:00", True),       # 08:00 UTC Wednesday, peak
])
def test_peak_window_edges(ts, peak):
    assert wm._is_peak(datetime.fromisoformat(ts), P) is peak


def test_unknown_inputs_give_none_never_zero():
    assert wm.list_cost_usd(None, OFF, FLASH, P) is None
    assert wm.list_cost_usd(TOK, OFF, "other/model", P) is None
    assert wm.list_cost_usd(TOK, None, FLASH, P) is None


def test_model_eras_and_explicit_model():
    assert wm.model_for({"started_at": "2026-09-20T00:00:00+00:00"}, P) == FLASH
    assert wm.model_for({"started_at": "2026-10-05T00:00:00+00:00"}, P) == PRO
    assert wm.model_for({"started_at": "2026-10-09T05:00:00+00:00"}, P) == FLASH
    assert wm.model_for({"started_at": OFF, "model": FLASH}, P) == FLASH


def test_every_era_model_has_rates():
    for era in P["model_eras"]:
        assert era["model"] in P["models"]
