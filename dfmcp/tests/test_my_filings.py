"""`queue.my_filings` (handoffs/2026-10-07-own-filings.md): a proposing role's
own filings with computed lifecycle status. Transport-free, like
test_queue_tools.py."""

from __future__ import annotations

import asyncio

import pytest

from dfmcp import queue_tools
from dfmcp.tests.test_queue_tools import _ok_call_dfhack, _project_args, _propose_args
from dfqueue import store

pytestmark = pytest.mark.asyncio


async def _call(tool, role, args, path):
    return await queue_tools.call(
        tool, role, args, db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
    )


async def _file(path, role="architect", ptype="workshop_siting", **kw):
    args = _propose_args(summary=kw.pop("summary", "Site a workshop near the Wagon."), **kw)
    if role == "quartermaster":
        args = _propose_args(
            type="work_order", summary=kw.pop("summary", "Brew more."),
            preconditions=[{"landmark": "Still", "state": "exists"}],
        )
    else:
        args["type"] = ptype
    _t, rec = await _call(queue_tools.QUEUE_PROPOSE, role, args, path)
    return rec


async def _rule(path, pid, decision, reason="Because."):
    _t, r = await _call(queue_tools.QUEUE_RULE, "overseer", {
        "proposal_id": pid, "decision": decision, "reason": reason, "public_rationale": "Ruled.",
    }, path)
    return r


async def _mine(path, role="architect", **args):
    return await _call(queue_tools.QUEUE_MY_FILINGS, role, args, path)


class TestStatuses:
    async def test_pending_then_accepted_the_1007_duplicate_shape(self, tmp_path):
        path = tmp_path / "q.sqlite3"
        p24 = await _file(path)
        _t, s = await _mine(path)
        assert [f["status"] for f in s["filings"]] == ["pending"]
        await _rule(path, p24["id"], "accept", "Worth doing.")
        text, s = await _mine(path)
        assert s["filings"][0]["id"] == p24["id"]
        assert s["filings"][0]["status"] == "accepted"
        assert s["filings"][0]["ruling"]["decision"] == "accept"
        assert "accepted" in text and "Worth doing." in text

    async def test_rejected(self, tmp_path):
        path = tmp_path / "q.sqlite3"
        p = await _file(path)
        await _rule(path, p["id"], "reject", "No.")
        _t, s = await _mine(path)
        assert s["filings"][0]["status"] == "rejected"

    async def test_deferred(self, tmp_path):
        path = tmp_path / "q.sqlite3"
        p = await _file(path)
        await _rule(path, p["id"], "defer", "Later.")
        _t, s = await _mine(path)
        assert s["filings"][0]["status"] == "deferred"
        assert s["filings"][0]["ruling"]["reason"] == "Later."

    async def test_in_project_and_completed_via_close(self, tmp_path):
        path = tmp_path / "q.sqlite3"
        p = await _file(path)
        r = await _rule(path, p["id"], "accept")
        _t, proj = await _call(queue_tools.QUEUE_PROJECT, "overseer", _project_args(r["id"]), path)
        _t, s = await _mine(path)
        f = s["filings"][0]
        assert f["status"] == "in_project"
        assert f["project_id"] == proj["id"]
        assert f["project_status"] == "active"
        store.close(path, target_id=proj["id"], outcome="completed", reason="All built.")
        _t, s = await _mine(path)
        assert s["filings"][0]["status"] == "closed"
        assert s["filings"][0]["close"]["outcome"] == "completed"

    async def test_completed_when_executed(self, tmp_path):
        path = tmp_path / "q.sqlite3"
        p = await _file(path)
        r = await _rule(path, p["id"], "accept")
        await _call(queue_tools.QUEUE_PROJECT, "overseer", {**_project_args(r["id"]), "steps": []}, path)
        await _call(queue_tools.QUEUE_EXECUTED, "overseer", {
            "ruling_id": r["id"], "actions": [{"tool": "workshop.build", "outcome": "success"}], "notes": "Built.",
        }, path)
        _t, s = await _mine(path)
        assert s["filings"][0]["status"] == "completed"

    async def test_closed_pending_proposal(self, tmp_path):
        path = tmp_path / "q.sqlite3"
        p = await _file(path)
        store.close(path, target_id=p["id"], outcome="superseded", reason="Overtaken.")
        _t, s = await _mine(path)
        assert s["filings"][0]["status"] == "closed"
        assert s["filings"][0]["close"]["reason"] == "Overtaken."


class TestIsolationAndFilters:
    async def test_a_role_never_sees_another_roles_filings(self, tmp_path):
        path = tmp_path / "q.sqlite3"
        a = await _file(path, "architect")
        q = await _file(path, "quartermaster")
        _t, sa = await _mine(path, "architect")
        _t, sq = await _mine(path, "quartermaster")
        assert [f["id"] for f in sa["filings"]] == [a["id"]]
        assert [f["id"] for f in sq["filings"]] == [q["id"]]
        # asking for the other's id by name returns nothing, not an error leak
        _t, s = await _mine(path, "architect", proposal_id=q["id"])
        assert s["filings"] == []

    async def test_no_role_argument_exists(self, tmp_path):
        path = tmp_path / "q.sqlite3"
        with pytest.raises(queue_tools.QueueToolError, match="unexpected argument"):
            await _call(queue_tools.QUEUE_MY_FILINGS, "architect", {"role": "quartermaster"}, path)

    async def test_newest_first_filters_and_caps(self, tmp_path):
        path = tmp_path / "q.sqlite3"
        ids = []
        for i in range(3):
            rec = await _file(path, summary=f"Distinct filing number {i} about different matters {i * 7}.",
                              rationale=f"Reason {i} unrelated entirely to others {i * 13}.")
            ids.append(rec["id"])
        await _rule(path, ids[0], "reject")
        _t, s = await _mine(path)
        assert [f["id"] for f in s["filings"]] == list(reversed(ids))
        _t, s = await _mine(path, limit=2)
        assert len(s["filings"]) == 2
        _t, s = await _mine(path, status="rejected")
        assert [f["id"] for f in s["filings"]] == [ids[0]]
        _t, s = await _mine(path, proposal_id=ids[1])
        assert [f["id"] for f in s["filings"]] == [ids[1]]
        with pytest.raises(queue_tools.QueueToolError):
            await _mine(path, limit=queue_tools.MY_FILINGS_MAX + 1)
        with pytest.raises(queue_tools.QueueToolError):
            await _mine(path, status="bogus")

    async def test_empty(self, tmp_path):
        text, s = await _mine(tmp_path / "q.sqlite3")
        assert s["count"] == 0 and text == "No filings match."


def test_granted_to_every_proposing_role_and_only_them():
    from pathlib import Path
    agents = Path(__file__).resolve().parents[2] / "agents"
    granted = {
        d.name for d in agents.iterdir()
        if (d / "tools.yaml").exists() and 'id: "queue.my_filings"' in (d / "tools.yaml").read_text(encoding="utf-8")
    }
    assert granted == {"architect", "quartermaster", "planner"}
