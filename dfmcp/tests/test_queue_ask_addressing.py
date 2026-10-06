"""`queue.ask`'s `to`, addressee-only answers and per-addressee
`queue.pending` / `queue.overview` (handoffs/2026-10-07-ask-addressing.md).

A fixture roster adds an answering `logistics` role; the real roster is never
edited. Runs under the ambient environment and `.venv-dfmcp` alike.
"""
from __future__ import annotations

import asyncio

import pytest

from dfmcp import queue_tools
from dfqueue import schema

pytestmark = pytest.mark.asyncio

_REAL_ROSTER = schema._load_roster


async def _dfhack(tool_id: str, arguments: dict):
    return {
        "tier1": {"population": 7},
        "tier2": {"in_game_date": "year 1, month 1, day 1, tick 500", "alerts": []},
    }


@pytest.fixture(autouse=True)
def logistics_roster(monkeypatch):
    real = _REAL_ROSTER()
    roster = {
        **real,
        "roles": {
            **real["roles"],
            "logistics": {"enabled": True, "dir": "logistics", "kind": "advisor", "answerer": True},
        },
    }
    monkeypatch.setattr(schema, "_load_roster", lambda: roster)


async def _call(tool, role, args, path):
    return await queue_tools.call(
        tool, role, args, db_path=path, call_dfhack=_dfhack, write_lock=asyncio.Lock(),
    )


GOOD_SPEC = [{"purpose": "output", "classes": ["furniture"], "tiles": 6, "adjacent_to": "workshop"}]


async def test_an_ask_to_logistics_is_pending_only_for_logistics(tmp_path):
    path = tmp_path / "queue.sqlite3"
    _t, to_logistics = await _call(
        queue_tools.QUEUE_ASK, "architect",
        {"question": "How much floor does a new still need beside it?", "to": "logistics"}, path,
    )
    _t, default = await _call(
        queue_tools.QUEUE_ASK, "architect", {"question": "Does soil stall construction?"}, path,
    )
    assert to_logistics["to"] == "logistics"
    assert "to" not in default

    _t, for_logistics = await _call(queue_tools.QUEUE_PENDING, "logistics", {}, path)
    _t, for_consultant = await _call(queue_tools.QUEUE_PENDING, "consultant", {}, path)
    assert for_logistics["ask_ids"] == [to_logistics["id"]]
    assert for_consultant["ask_ids"] == [default["id"]]


async def test_only_the_addressee_may_answer_through_the_tool(tmp_path):
    path = tmp_path / "queue.sqlite3"
    _t, ask = await _call(
        queue_tools.QUEUE_ASK, "architect",
        {"question": "How much floor does a new still need beside it?", "to": "logistics"}, path,
    )
    with pytest.raises(queue_tools.QueueToolError, match="addressed to 'logistics'"):
        await _call(queue_tools.QUEUE_ANSWER, "consultant", {"ask_id": ask["id"], "answer": "Six tiles."}, path)
    _t, answer = await _call(
        queue_tools.QUEUE_ANSWER, "logistics",
        {"ask_id": ask["id"], "answer": "Six tiles of output.", "pile_spec": GOOD_SPEC}, path,
    )
    assert answer["pile_spec"] == GOOD_SPEC
    assert "<pile_spec>" in _t


async def test_an_ask_to_a_non_answerer_is_refused(tmp_path):
    path = tmp_path / "queue.sqlite3"
    with pytest.raises(queue_tools.QueueToolError, match="not an answerer role"):
        await _call(queue_tools.QUEUE_ASK, "architect", {"question": "A question?", "to": "overseer"}, path)


async def test_a_positional_pile_spec_is_refused_through_the_tool(tmp_path):
    path = tmp_path / "queue.sqlite3"
    _t, ask = await _call(
        queue_tools.QUEUE_ASK, "architect", {"question": "A question?", "to": "logistics"}, path,
    )
    bad = [{"purpose": "output", "classes": ["stone"], "tiles": 4, "x": 3, "y": 4}]
    with pytest.raises(queue_tools.QueueToolError, match="not a field"):
        await _call(
            queue_tools.QUEUE_ANSWER, "logistics",
            {"ask_id": ask["id"], "answer": "Here.", "pile_spec": bad}, path,
        )


async def test_overview_reports_open_asks_per_addressee(tmp_path):
    path = tmp_path / "queue.sqlite3"
    _t, a = await _call(queue_tools.QUEUE_ASK, "architect", {"question": "Default addressee question?"}, path)
    _t, b = await _call(
        queue_tools.QUEUE_ASK, "architect", {"question": "Question for logistics?", "to": "logistics"}, path,
    )
    _t, overview = await _call(queue_tools.QUEUE_OVERVIEW, "conductor", {}, path)
    assert overview["asks"]["count"] == 2
    assert overview["asks"]["to"] == {"consultant": [a["id"]], "logistics": [b["id"]]}
