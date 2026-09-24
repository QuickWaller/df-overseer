"""The final answer is read from every envelope shape openclaw has returned."""
import json

import pytest

from conductor.tests.test_runner import _FakeProcess, _fake_exec, _runner

# Shape of a real openclaw envelope (evals/live/2026-09-24-consultant-ghost/
# run-output.json, "raw"): the answer is under `final` and payloads[0].text,
# not `finalAnswer`. Structure only; the text is a stand-in.
_REAL_SHAPE_ENVELOPE = {
    "ok": True, "status": "ok", "final": "The answer text.",
    "payloads": [{"text": "The answer text.", "mediaUrl": None}],
    "costUsd": 0.034, "toolSummary": {"calls": 16, "tools": ["a"], "failures": 1},
}


async def _answer(tmp_path, envelope):
    runner = _runner(tmp_path, _fake_exec(_FakeProcess(json.dumps(envelope).encode())))
    return (await runner.run("consultant", "q", model="m")).final_answer


@pytest.mark.asyncio
async def test_the_real_final_key_yields_the_answer(tmp_path):
    assert await _answer(tmp_path, _REAL_SHAPE_ENVELOPE) == "The answer text."


@pytest.mark.asyncio
async def test_payload_text_is_the_fallback(tmp_path):
    env = {k: v for k, v in _REAL_SHAPE_ENVELOPE.items() if k != "final"}
    assert await _answer(tmp_path, env) == "The answer text."


@pytest.mark.asyncio
async def test_order_is_finalAnswer_then_final_answer_then_final(tmp_path):
    env = dict(_REAL_SHAPE_ENVELOPE, finalAnswer="A", final_answer="B")
    assert await _answer(tmp_path, env) == "A"
    env = dict(_REAL_SHAPE_ENVELOPE, final_answer="B")
    assert await _answer(tmp_path, env) == "B"


@pytest.mark.asyncio
async def test_no_answer_anywhere_is_none(tmp_path):
    assert await _answer(tmp_path, {"ok": True, "status": "ok", "payloads": []}) is None
