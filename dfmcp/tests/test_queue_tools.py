"""Direct, transport-free tests of `dfmcp.queue_tools`: the two things the
Phase A review found (2026-09-15) that `dfmcp/tests/test_server.py`'s
full-ASGI-app tests do not exercise well -- a storage-layer failure (an
unwritable queue directory, standing in for `ProtectSystem=strict` denying
a write on VM 103) reaching the caller as a refusal rather than a crash,
and the write-serialisation race that moving `dfqueue.store` calls onto
`asyncio.to_thread` introduced.

This module imports nothing from `mcp` (the SDK), only `dfmcp.queue_tools`
and `dfqueue.store` directly, so unlike `test_server.py` it runs under the
ambient environment too, not only `.venv-dfmcp`.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from dfmcp import queue_tools
from dfqueue import store

pytestmark = pytest.mark.asyncio

_OVERVIEW_JSON = {
    "tier1": {"population": 7},
    "tier2": {"in_game_date": "year 1, month 1, day 1, tick 500", "alerts": []},
}


async def _ok_call_dfhack(tool_id: str, arguments: dict):
    assert tool_id == "overview.get"
    return _OVERVIEW_JSON


def _propose_args(**overrides) -> dict:
    args = {
        "type": "workshop_siting",
        "summary": "Site the next workshop on open ground near the Wagon.",
        "rationale": "Shortest hauling path of the candidates offered.",
        "prediction": {"signal": "fort.population", "op": "gte", "value": 1, "check_after_ticks": 1200},
        "cost": {"estimate": 10, "unit": "dwarf_ticks"},
        "suggested_priority": 3,
        "preconditions": [{"landmark": "Wagon", "state": "exists"}],
        "public_rationale": "Puts the workshop near the wagon.",
    }
    args.update(overrides)
    return args


# ==========================================================================
# Storage errors: sqlite3.Error / OSError become QueueToolError, not a crash
# ==========================================================================


class TestStorageErrorsAreRefusals:
    async def test_propose_against_an_unwritable_directory_is_refused_not_a_crash(self, tmp_path):
        """A file where a directory needs to be, so `dfqueue.store._connect`'s
        own `p.parent.mkdir(parents=True, exist_ok=True)` raises a real
        `NotADirectoryError` (an `OSError` subclass) -- no mocking needed,
        this is the same class of failure `ProtectSystem=strict` denying a
        write would produce on VM 103 (this stream's own Phase B checklist
        flags exactly that gotcha)."""
        blocking_file = tmp_path / "not-a-directory"
        blocking_file.write_text("x", encoding="utf-8")
        bad_db_path = blocking_file / "sub" / "queue.sqlite3"

        with pytest.raises(queue_tools.QueueToolError) as exc:
            await queue_tools.call(
                queue_tools.QUEUE_PROPOSE, "architect", _propose_args(),
                db_path=bad_db_path, call_dfhack=_ok_call_dfhack,
                write_lock=asyncio.Lock(),
            )
        assert queue_tools.QUEUE_PROPOSE in str(exc.value)
        assert "queue database is unavailable" in str(exc.value)

    async def test_pending_against_an_unwritable_directory_is_refused_not_a_crash(self, tmp_path):
        blocking_file = tmp_path / "not-a-directory"
        blocking_file.write_text("x", encoding="utf-8")
        bad_db_path = blocking_file / "sub" / "queue.sqlite3"

        with pytest.raises(queue_tools.QueueToolError) as exc:
            await queue_tools.call(
                queue_tools.QUEUE_PENDING, "overseer", {},
                db_path=bad_db_path, call_dfhack=_ok_call_dfhack,
                write_lock=asyncio.Lock(),
            )
        assert "queue database is unavailable" in str(exc.value)

    async def test_a_sqlite_error_from_the_store_is_also_wrapped(self, tmp_path, monkeypatch):
        """Not every storage failure is a bad path -- a real sqlite3.Error
        (a locked file, a corrupt database) must be caught too, not just
        OSError. Simulated directly rather than by actually locking a file
        cross-process, which would be a flaky, platform-dependent test."""
        import sqlite3

        def boom(*args, **kwargs):
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(store, "append", boom)

        with pytest.raises(queue_tools.QueueToolError) as exc:
            await queue_tools.call(
                queue_tools.QUEUE_PROPOSE, "architect", _propose_args(),
                db_path=tmp_path / "queue.sqlite3", call_dfhack=_ok_call_dfhack,
                write_lock=asyncio.Lock(),
            )
        assert "database is locked" in str(exc.value)


# ==========================================================================
# Write serialisation: the _next_id race, forced deterministic and fixed
# ==========================================================================


class TestWriteSerialisation:
    async def test_concurrent_raw_appends_without_serialization_can_collide(self, tmp_path, monkeypatch):
        """THE FAILING CASE, run first so its failure is on record before
        the fix's own test claims to pass. Calls `dfqueue.store.append`
        directly through `asyncio.to_thread`, with no lock at all -- the
        exact shape `dfmcp.queue_tools`'s handlers would have if the
        Phase A review's fix were reverted. `store._next_id` is
        monkeypatched to sleep briefly so two concurrent calls are
        deterministically both mid-count when neither has inserted yet,
        rather than relying on timing luck to occasionally reproduce the
        race. This is the failure `_append_locked`'s `write_lock` exists to
        prevent -- see the next test for the same race, through the real
        call path, not reproducing it.
        """
        path = tmp_path / "queue.sqlite3"
        original_next_id = store._next_id

        def slow_next_id(conn, kind):
            time.sleep(0.05)
            return original_next_id(conn, kind)

        monkeypatch.setattr(store, "_next_id", slow_next_id)

        def make_record(i: int) -> dict:
            args = _propose_args(summary=f"Race probe {i}, distinct text so no other field collides.")
            return {
                "kind": "proposal", "role": "architect", "cycle": 1, "snapshot": "tick-1",
                **args,
            }

        async def append_one(i: int):
            return await asyncio.to_thread(store.append, make_record(i), path, game_tick=100)

        results = await asyncio.gather(*(append_one(i) for i in range(5)), return_exceptions=True)

        errors = [r for r in results if isinstance(r, BaseException)]
        oks = [r for r in results if isinstance(r, dict)]
        ids = [r["id"] for r in oks]

        # The race: two concurrent, unserialised appends can compute the
        # same id from `_next_id`'s COUNT(*) before either has inserted, so
        # the second write fails a real UNIQUE constraint (a raw
        # sqlite3.IntegrityError, not a friendly QueueError -- this is
        # `dfqueue.store` used the way it was never meant to be used
        # without an external lock, and this test is what proves that,
        # not an assumption).
        assert errors, (
            f"expected at least one concurrent append to fail on a raw id "
            f"collision without a lock, got {len(oks)} successes and 0 errors "
            f"(ids: {ids}) -- the race did not reproduce this run"
        )

    async def test_concurrent_proposes_through_queue_tools_get_distinct_ids_and_all_land(
        self, tmp_path, monkeypatch
    ):
        """THE PASSING CASE, same forced-slow `_next_id` as the failing case
        above, but now through the real `queue_tools.call` path, which
        serialises every `store.append` behind one shared `asyncio.Lock`
        (`_append_locked`). If this test is run without that lock (e.g. by
        temporarily making `_append_locked` call `store.append` directly,
        unguarded), it fails exactly the way the test above does -- checked
        by hand during this review fix, not asserted here (see this
        stream's report for how)."""
        path = tmp_path / "queue.sqlite3"
        original_next_id = store._next_id

        def slow_next_id(conn, kind):
            time.sleep(0.05)
            return original_next_id(conn, kind)

        monkeypatch.setattr(store, "_next_id", slow_next_id)

        write_lock = asyncio.Lock()

        async def propose_one(i: int):
            args = _propose_args(summary=f"Race probe {i}, distinct text so no other field collides.")
            return await queue_tools.call(
                queue_tools.QUEUE_PROPOSE, "architect", args,
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=write_lock,
            )

        results = await asyncio.gather(*(propose_one(i) for i in range(5)))

        ids = [structured["id"] for _text, structured in results]
        assert len(set(ids)) == 5, f"expected 5 distinct ids, got {ids}"

        written = store.load(path)
        assert len(written) == 5
        assert {r["id"] for r in written} == set(ids)

    async def test_the_write_lock_is_never_held_during_the_dfhack_stamping_call(self, tmp_path):
        """A slow (but eventually successful) call_dfhack must not block a
        second, independent propose from starting its own DFHack call --
        only the store.append portion is meant to serialise. Proven by a
        call_dfhack that blocks on an event the second call sets, then
        waits for both to have started before either finishes: if the lock
        wrongly wrapped the DFHack call too, the second propose's
        call_dfhack would never even start until the first finished
        entirely, and this test would hang until pytest-asyncio's own
        timeout (or deadlock outright under a stricter runner)."""
        path = tmp_path / "queue.sqlite3"
        first_started = asyncio.Event()
        second_started = asyncio.Event()

        async def slow_call_dfhack(tool_id: str, arguments: dict):
            if not first_started.is_set():
                first_started.set()
                # Wait for the second call's own call_dfhack to actually
                # start before letting the first proceed -- only possible
                # if the two DFHack calls run concurrently, i.e. the lock
                # is not held across them.
                await asyncio.wait_for(second_started.wait(), timeout=5)
            else:
                second_started.set()
            return _OVERVIEW_JSON

        write_lock = asyncio.Lock()

        async def propose_one(i: int):
            args = _propose_args(summary=f"Concurrency probe {i}, distinct text.")
            return await queue_tools.call(
                queue_tools.QUEUE_PROPOSE, "architect", args,
                db_path=path, call_dfhack=slow_call_dfhack, write_lock=write_lock,
            )

        results = await asyncio.wait_for(
            asyncio.gather(propose_one(0), propose_one(1)), timeout=5,
        )
        ids = {structured["id"] for _text, structured in results}
        assert len(ids) == 2


# ==========================================================================
# ask / answer / executed -- docs/AGENT-LOOP.md items 4 and 7
# ==========================================================================


async def _propose_and_rule(path, *, decision="accept"):
    """Test helper: write one proposal (architect) and rule on it
    (overseer), through the real queue_tools.call() path, and return
    `(proposal_text, proposal_structured, ruling_text, ruling_structured)`."""
    _p_text, proposal = await queue_tools.call(
        queue_tools.QUEUE_PROPOSE, "architect", _propose_args(),
        db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
    )
    _r_text, ruling = await queue_tools.call(
        queue_tools.QUEUE_RULE, "overseer",
        {
            "proposal_id": proposal["id"], "decision": decision,
            "reason": "Charter-clean and worth trying.",
            "public_rationale": "Approved.",
        },
        db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
    )
    return proposal, ruling


class TestExecuted:
    async def test_executed_arms_the_prediction_and_is_overseer_only(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        proposal, ruling = await _propose_and_rule(path)

        text, structured = await queue_tools.call(
            queue_tools.QUEUE_EXECUTED, "overseer",
            {
                "ruling_id": ruling["id"],
                "actions": [{"tool": "workshop.build", "outcome": "success"}],
                "notes": "Built as ruled.",
            },
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert "<executed" in text
        assert structured["ruling_id"] == ruling["id"]

        due = store.pending_due(path, structured["cycle"] + 1200)
        assert len(due) == 1
        assert due[0]["due_game_tick"] == structured["cycle"] + 1200

    async def test_executed_refuses_role_arguments(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _proposal, ruling = await _propose_and_rule(path)

        with pytest.raises(queue_tools.QueueToolError, match="unexpected argument"):
            await queue_tools.call(
                queue_tools.QUEUE_EXECUTED, "overseer",
                {
                    "ruling_id": ruling["id"], "role": "architect",
                    "actions": [{"tool": "workshop.build", "outcome": "success"}],
                    "notes": "Trying to smuggle a role argument.",
                },
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )

    async def test_executed_against_a_nonexistent_ruling_is_refused(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        with pytest.raises(queue_tools.QueueToolError, match="does not refer to an existing ruling"):
            await queue_tools.call(
                queue_tools.QUEUE_EXECUTED, "overseer",
                {
                    "ruling_id": "ruling-9999",
                    "actions": [{"tool": "workshop.build", "outcome": "success"}],
                    "notes": "No such ruling.",
                },
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )


class TestAskAnswer:
    async def test_a_lookup_ask_from_the_architect_and_the_consultants_answer(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        ask_text, ask = await queue_tools.call(
            queue_tools.QUEUE_ASK, "architect",
            {"question": "Does soil under a workshop ever stall construction?"},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert "<ask" in ask_text
        assert "proposal_id" not in ask

        # Before an answer, the Consultant's own queue.pending lists it.
        _pending_text, pending = await queue_tools.call(
            queue_tools.QUEUE_PENDING, "consultant", {},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert pending["ask_ids"] == [ask["id"]]

        answer_text, answer = await queue_tools.call(
            queue_tools.QUEUE_ANSWER, "consultant",
            {"ask_id": ask["id"], "answer": "No, only its own material requirements matter."},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert "<answer" in answer_text
        assert answer["ask_id"] == ask["id"]

        # Answered, so no longer open.
        _pending_text2, pending2 = await queue_tools.call(
            queue_tools.QUEUE_PENDING, "consultant", {},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert pending2["ask_ids"] == []

    async def test_queue_pending_for_a_non_consultant_role_is_unchanged(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _text, proposal = await queue_tools.call(
            queue_tools.QUEUE_PROPOSE, "architect", _propose_args(),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        _pending_text, pending = await queue_tools.call(
            queue_tools.QUEUE_PENDING, "overseer", {},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert pending["proposal_ids"] == [proposal["id"]]
        assert "ask_ids" not in pending

    async def test_a_fact_check_from_the_overseer_blocks_ruling_until_answered(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        _p_text, proposal = await queue_tools.call(
            queue_tools.QUEUE_PROPOSE, "architect", _propose_args(),
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        _ask_text, ask = await queue_tools.call(
            queue_tools.QUEUE_ASK, "overseer",
            {"question": "Is this hauling-distance claim right?", "proposal_id": proposal["id"]},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )

        with pytest.raises(queue_tools.QueueToolError, match="open fact-check"):
            await queue_tools.call(
                queue_tools.QUEUE_RULE, "overseer",
                {
                    "proposal_id": proposal["id"], "decision": "accept",
                    "reason": "Looks right.", "public_rationale": "Approved.",
                },
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )

        await queue_tools.call(
            queue_tools.QUEUE_ANSWER, "consultant",
            {"ask_id": ask["id"], "answer": "Confirmed against the live layout."},
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )

        _r_text, ruling = await queue_tools.call(
            queue_tools.QUEUE_RULE, "overseer",
            {
                "proposal_id": proposal["id"], "decision": "accept",
                "reason": "Looks right.", "public_rationale": "Approved.",
            },
            db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
        )
        assert ruling["decision"] == "accept"

    async def test_ask_refuses_role_argument_smuggling(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        with pytest.raises(queue_tools.QueueToolError, match="unexpected argument"):
            await queue_tools.call(
                queue_tools.QUEUE_ASK, "architect",
                {"question": "A question.", "role": "overseer"},
                db_path=path, call_dfhack=_ok_call_dfhack, write_lock=asyncio.Lock(),
            )
